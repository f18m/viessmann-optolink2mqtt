"""
optolinkvs2_register.py
----------------
Definition of OptolinkVS2Register class
Copyright 2026 Francesco Montorsi (object-oriented rewrite)
Copyright 2024 philippoo66 (get_value)

Licensed under the GNU GENERAL PUBLIC LICENSE, Version 3 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.gnu.org/licenses/gpl-3.0.html

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Dict, Any

# import hashlib
import json
import logging
import re

from . import datetime_bcd


class OptolinkVS2Register:
    """
    Represents a register to be read or written inside the Viessmann device, via the Optolink interface.
    Each register is defined by its metadata (name, address, length, signed/unsigned, scale factor, etc.)
    and possibly HomeAssistant discovery information.

    Notably, this class does NOT store a specific VALUE for the register itself; rather it provides methods
    to EXTRACT the value from raw data read from the device, or to CONVERT a value into raw data suitable
    to be written into the device.
    """

    MAX_DECIMALS = 2

    # supported values for the "type" register attribute:
    #  - int:          little-endian integer
    #  - float:        little-endian integer multiplied by the scale factor
    #  - enum:         little-endian integer mapped to a label by the "enum" dictionary
    #  - datetime_bcd: 8-byte Viessmann DateTimeBCD, published as ISO 8601
    TYPE_INT = "int"
    TYPE_FLOAT = "float"
    TYPE_ENUM = "enum"
    TYPE_DATETIME_BCD = "datetime_bcd"
    SUPPORTED_TYPES = (TYPE_INT, TYPE_FLOAT, TYPE_ENUM, TYPE_DATETIME_BCD)

    # characters removed from register names by _sanitize_name()
    _DROPPED_CHARS = re.compile(r"[()\[\]{}\"']")
    # runs of characters replaced by a single underscore by _sanitize_name()
    _SEPARATOR_CHARS = re.compile(r"[^a-z0-9]+")

    def __init__(
        self,
        reg: Dict[str, Any],
        mqtt_base_topic: str,
        device_timezone: tzinfo | None = None,
    ):
        """
        device_timezone is the timezone of the Viessmann device clock, used only by
        datetime_bcd registers; None means the local timezone of the host.
        """
        # basic metadata
        self.name = reg["name"]
        self.sanitized_name = self._sanitize_name(self.name)
        self.sampling_period_sec = reg["sampling_period_seconds"]
        self.mqtt_base_topic = mqtt_base_topic
        if self.mqtt_base_topic.endswith("/"):
            self.mqtt_base_topic = self.mqtt_base_topic[:-1]

        # register definition
        self.address = int(reg["register"])
        self.length = int(reg["length"])
        self.signed = bool(reg["signed"])
        self.writable = bool(reg["writable"])
        self.scale_factor = float(reg["scale_factor"])
        # byte_filter is either None or a string in the format "b:<start>:<end>" (inclusive)
        self.byte_filter = reg["byte_filter"]
        self._byte_filter_slice = self._parse_byte_filter(self.byte_filter)
        self.enum_dict = reg["enum"]
        self.type = reg["type"]
        self.device_timezone = device_timezone
        self.check_type_validity()

        # the type cannot change, so the decoder and encoder are chosen once here
        cls = OptolinkVS2Register
        codecs = {
            cls.TYPE_INT: (self._get_int_from_rawdata, self._get_rawdata_from_int),
            cls.TYPE_FLOAT: (
                self._get_float_from_rawdata,
                self._get_rawdata_from_float,
            ),
            cls.TYPE_ENUM: (self._get_enum_from_rawdata, self._get_rawdata_from_enum),
            cls.TYPE_DATETIME_BCD: (
                self._get_datetime_bcd_from_rawdata,
                self._get_rawdata_from_datetime_bcd,
            ),
        }
        self._value_from_rawdata, self._rawdata_from_value = codecs[self.type]

        # optional Home Assistant discovery configuration
        self.ha_discovery = reg["ha_discovery"]
        if self.ha_discovery is not None:
            self.check_ha_discovery_validity()

    def _sanitize_name(self, name: str) -> str:
        """
        Returns a sanitized version of the given name, suitable to be used as MQTT topic part
        or HomeAssistant unique ID part: only lowercase ASCII letters, digits and single
        underscores, never at the start or end.
        Brackets, quotes and non-ASCII characters are dropped; any other run of characters
        (spaces, punctuation, MQTT wildcards '+' and '#', ...) becomes a single underscore.
        Raises ValueError if nothing is left.
        """
        sanitized = name.lower()
        sanitized = OptolinkVS2Register._DROPPED_CHARS.sub("", sanitized)
        sanitized = sanitized.encode("ascii", errors="ignore").decode("ascii")
        sanitized = OptolinkVS2Register._SEPARATOR_CHARS.sub("_", sanitized).strip("_")
        if not sanitized:
            raise ValueError(
                f"Register name '{name}' contains no letters or digits usable in an MQTT topic"
            )
        return sanitized

    def _parse_byte_filter(self, byte_filter: str | None) -> slice | None:
        """
        Parses a byte filter in the format "b:<start>:<end>" (both indexes inclusive)
        into a slice. Returns None if no byte filter is configured.
        Raises ValueError if the byte filter is malformed or out of the register bounds.
        """
        if byte_filter is None:
            return None

        parts = str(byte_filter).split(":")
        try:
            if len(parts) != 3 or parts[0] != "b":
                raise ValueError("expected format 'b:<start>:<end>'")
            start = int(parts[1])
            end = int(parts[2])
        except ValueError as e:
            raise ValueError(
                f"Register '{self.name}' has invalid byte_filter '{byte_filter}': {e}"
            )
        if not 0 <= start <= end < self.length:
            raise ValueError(
                f"Register '{self.name}' has invalid byte_filter '{byte_filter}': "
                f"indexes must satisfy 0 <= start <= end < length ({self.length})"
            )
        return slice(start, end + 1)

    def check_type_validity(self) -> None:
        """
        Checks that the register "type" is coherent with the rest of the register definition.
        Raises ValueError if it is not.
        """
        cls = OptolinkVS2Register
        if self.type not in cls.SUPPORTED_TYPES:
            raise ValueError(
                f"Register '{self.name}' has invalid type '{self.type}'; expected one of {list(cls.SUPPORTED_TYPES)}"
            )

        if self.enum_dict is not None and self.type != cls.TYPE_ENUM:
            raise ValueError(
                f"Register '{self.name}' has an 'enum' dictionary but type '{self.type}'; "
                f"set 'type: {cls.TYPE_ENUM}'"
            )
        if self.type == cls.TYPE_ENUM and self.enum_dict is None:
            raise ValueError(
                f"Register '{self.name}' has type '{cls.TYPE_ENUM}' but no 'enum' dictionary"
            )

        if self.scale_factor != 1.0 and self.type != cls.TYPE_FLOAT:
            raise ValueError(
                f"Register '{self.name}' has scale_factor {self.scale_factor:g} but type '{self.type}'; "
                f"a scale factor is allowed only with 'type: {cls.TYPE_FLOAT}'"
            )

        if self.type == cls.TYPE_DATETIME_BCD:
            if self.length != datetime_bcd.DATETIME_BCD_LENGTH:
                raise ValueError(
                    f"Register '{self.name}' has type '{cls.TYPE_DATETIME_BCD}' but length {self.length}; "
                    f"expected {datetime_bcd.DATETIME_BCD_LENGTH}"
                )
            if self.signed or self.byte_filter is not None:
                raise ValueError(
                    f"Register '{self.name}' has type '{cls.TYPE_DATETIME_BCD}', "
                    "which cannot be combined with 'signed' or 'byte_filter'"
                )

    def get_human_readable_description(self) -> str:
        """
        Returns a human-readable description for this register
        """
        return f"name=[{self.name}], addr=0x{self.address:04X}, len={self.length}, type={self.type}, signed={self.signed}, scale={self.scale_factor}, byte_filter={self.byte_filter}, enum={self.enum_dict}, has HA discovery={self.ha_discovery is not None}"

    def get_next_occurrence_in_seconds(self) -> float:
        """
        Returns the sampling period in seconds
        """
        return self.sampling_period_sec

    def get_value_from_rawdata(self, rawdata: bytearray) -> str | int | float | None:
        """
        Returns the value of the register from the given raw data.
        NOTE: This function was named "bytesval" in original optolink-splitter codebase.

        This function will return a string for "enum" and "datetime_bcd" registers,
        an integer for "int" registers and a float for "float" registers.
        In case of invalid conversion, None is returned.
        """
        return self._value_from_rawdata(rawdata)

    def get_rawdata_from_value(self, str_value: str) -> bytearray | None:
        """
        Converts a generic string into raw data (bytearray) suitable to be written
        into the register of the Viessmann device.
        Returns None in case of conversion error.
        """
        return self._rawdata_from_value(str_value)

    #
    # Decoders: one per register type, selected in __init__
    #

    def _get_int_from_rawdata(self, rawdata: bytearray) -> int:
        """
        Decodes the register (or the bytes selected by its byte filter) as a little-endian integer.
        """
        if self._byte_filter_slice is not None:
            rawdata = rawdata[self._byte_filter_slice]

        val = int.from_bytes(rawdata, byteorder="little", signed=self.signed)

        if not self.signed:
            maxpossible_value = int.from_bytes(
                [0xFF] * self.length, byteorder="little", signed=False
            )
            if val > maxpossible_value * 0.9:
                logging.warning(
                    f"Register '{self.name}' read value {rawdata.hex()} is suspiciously close to the max possible value {maxpossible_value} for a {self.length}-long register, which might indicate a SIGNED value was read in a register declared as UNSIGNED. Did you forget to declare this register as SIGNED?"
                )
        return val

    def _get_float_from_rawdata(self, rawdata: bytearray) -> float:
        """
        Decodes the register as an integer multiplied by the scale factor.
        """
        return round(
            self._get_int_from_rawdata(rawdata) * self.scale_factor,
            OptolinkVS2Register.MAX_DECIMALS,
        )

    def _get_enum_from_rawdata(self, rawdata: bytearray) -> str:
        """
        Decodes the register as an integer and maps it to its label in the enum dictionary.
        """
        val = int.from_bytes(rawdata, byteorder="little", signed=self.signed)
        return self.enum_dict.get(val, f"Unknown ({val})")

    def _get_datetime_bcd_from_rawdata(self, rawdata: bytearray) -> str | None:
        """
        Decodes a DateTimeBCD register into an ISO 8601 string carrying the UTC offset
        of the device timezone, e.g. "2026-11-27T11:53:53+01:00".
        Returns "None" if the date/time is not set on the device, or None if the raw
        data is not a valid DateTimeBCD value.
        """
        try:
            naive = datetime_bcd.decode(bytes(rawdata))
        except ValueError as e:
            logging.error(
                f"Register '{self.name}' read value {bytes(rawdata).hex()} is not a valid DateTimeBCD: {e}"
            )
            return None
        if naive is None:
            return datetime_bcd.UNSET_PAYLOAD
        if self.device_timezone is not None:
            aware = naive.replace(tzinfo=self.device_timezone)
        else:
            aware = naive.astimezone()  # interpret as host local time
        return aware.isoformat()

    #
    # Encoders: one per register type, selected in __init__.
    # The payload comes from MQTT and cannot be trusted.
    #

    def _get_rawdata_from_int(self, str_value: str) -> bytearray | None:
        """
        Encodes an integer payload, e.g. "42".
        """
        try:
            val = int(str_value)
        except ValueError:
            return self._log_invalid_number(str_value)
        return self._int_to_rawdata(val, str_value)

    def _get_rawdata_from_float(self, str_value: str) -> bytearray | None:
        """
        Encodes a number payload, e.g. "21.5", dividing it by the scale factor.
        """
        # float() accepts "nan" and "inf", which cannot be converted to int
        try:
            val = int(
                round(
                    float(str_value) / self.scale_factor,
                    OptolinkVS2Register.MAX_DECIMALS,
                )
            )
        except (ValueError, OverflowError):
            return self._log_invalid_number(str_value)
        return self._int_to_rawdata(val, str_value)

    def _get_rawdata_from_enum(self, str_value: str) -> bytearray | None:
        """
        Encodes one of the labels of the enum dictionary.
        """
        reverse_enum = {v: k for k, v in self.enum_dict.items()}
        if str_value not in reverse_enum:
            logging.error(
                f"Invalid value '{str_value}' for register '{self.name}'; valid values are: {list(self.enum_dict.values())}"
            )
            return None
        return self._int_to_rawdata(reverse_enum[str_value], str_value)

    def _get_rawdata_from_datetime_bcd(self, str_value: str) -> bytearray | None:
        """
        Converts an ISO 8601 date/time into DateTimeBCD raw data.
        A date/time with a timezone (e.g. the UTC one sent by HomeAssistant) is converted
        to the device timezone; one without timezone is taken as device local time.
        An empty payload, "None", or any date before year 2000 clears the date/time.
        """
        s = str_value.strip()
        if s == "" or s.lower() == datetime_bcd.UNSET_PAYLOAD.lower():
            return datetime_bcd.encode(None)
        if s.endswith(("Z", "z")):
            # fromisoformat() accepts the "Z" suffix only since Python 3.11
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            logging.error(
                f"Invalid value '{str_value}' for register '{self.name}': not an ISO 8601 date/time"
            )
            return None
        if dt.tzinfo is not None:
            # astimezone(None) converts to the host local timezone
            dt = dt.astimezone(self.device_timezone).replace(tzinfo=None)
        return datetime_bcd.encode(dt.replace(microsecond=0))

    def _log_invalid_number(self, str_value: str) -> None:
        logging.error(
            f"Invalid value '{str_value}' for register '{self.name}': not a valid finite number"
        )
        return None

    def _int_to_rawdata(self, val: int, str_value: str) -> bytearray | None:
        """
        Returns the little-endian bytes of the given integer, or None if it does not fit
        the register length and signedness.
        """
        try:
            return bytearray(
                val.to_bytes(self.length, byteorder="little", signed=self.signed)
            )
        except OverflowError:
            logging.error(
                f"Value '{str_value}' for register '{self.name}' cannot be represented in {self.length} "
                f"{'signed' if self.signed else 'unsigned'} bytes."
            )
            return None

    def is_within_write_bounds(self, rawdata: bytearray) -> bool:
        """
        Returns True if the value encoded in the given raw data (as returned by
        get_rawdata_from_value()) respects the 'min' and 'max' limits configured
        in the HomeAssistant discovery metadata, if any.
        These limits are enforced here as well, since any MQTT client (not only
        HomeAssistant) can publish on the command topic.
        """
        if (
            self.type
            not in (OptolinkVS2Register.TYPE_INT, OptolinkVS2Register.TYPE_FLOAT)
            or self.ha_discovery is None
        ):
            return True

        # compare the value that will actually be written, after rounding to the
        # register resolution
        val = int.from_bytes(rawdata, byteorder="little", signed=self.signed)
        val = round(val * self.scale_factor, OptolinkVS2Register.MAX_DECIMALS)

        min_val = self.ha_discovery.get("min")
        max_val = self.ha_discovery.get("max")
        if (min_val is not None and val < min_val) or (
            max_val is not None and val > max_val
        ):
            logging.error(
                f"Value {val} for register '{self.name}' is outside the configured range "
                f"[{min_val if min_val is not None else '-inf'}, {max_val if max_val is not None else '+inf'}]"
            )
            return False
        return True

    #
    # MQTT helpers
    #

    def get_mqtt_state_topic(self) -> str:
        return f"{self.mqtt_base_topic}/{self.sanitized_name}"

    def get_mqtt_command_topic(self) -> str:
        return f"{self.mqtt_base_topic}/{self.sanitized_name}/set"

    #
    # MQTT/HomeAssistant Discovery Message helpers
    #

    def check_ha_discovery_validity(self) -> None:
        """
        Checks if HA discovery information are coherent with the register definition.
        Raises ValueError if they are not.
        """
        # ensure ha_discovery is a dict
        if not isinstance(self.ha_discovery, dict):
            raise ValueError(
                f"Register '{self.name}' has invalid HA discovery configuration."
            )

        # required parameters: name & platform
        if self.ha_discovery["name"] is None or self.ha_discovery["name"] == "":
            raise ValueError(
                f"Register '{self.name}' has invalid HA discovery 'name' property."
            )
        if self.ha_discovery["platform"] is None or self.ha_discovery["platform"] == "":
            raise ValueError(
                f"Register '{self.name}' has invalid HA discovery 'platform' property."
            )

        HA_PLATFORMS_WRITABLE = ["switch", "select", "number", "datetime"]

        if self.writable and self.ha_discovery["platform"] not in HA_PLATFORMS_WRITABLE:
            raise ValueError(
                f"Register '{self.name}' is writable but has incompatible HA discovery 'platform' property '{self.ha_discovery['platform']}'."
            )
        if not self.writable and self.ha_discovery["platform"] in HA_PLATFORMS_WRITABLE:
            raise ValueError(
                f"Register '{self.name}' is not writable but has incompatible HA discovery 'platform' property '{self.ha_discovery['platform']}'."
            )

        # the "datetime" platform publishes ISO 8601 date/times, which only datetime_bcd registers produce
        if (
            self.ha_discovery["platform"] == "datetime"
            and self.type != OptolinkVS2Register.TYPE_DATETIME_BCD
        ):
            raise ValueError(
                f"Register '{self.name}' uses HA discovery 'platform' property 'datetime', "
                f"which requires 'type: {OptolinkVS2Register.TYPE_DATETIME_BCD}' (found '{self.type}')."
            )

    def get_ha_unique_id(self, device_name: str) -> str:
        """
        Returns a reasonable-unique ID to be used inside HA discovery messages
        """
        sanitized_address = self.address.to_bytes(2, "little").hex()
        return f"{device_name}-{self.sanitized_name}-{sanitized_address}"

    def get_ha_discovery_payload(
        self,
        device_name: str,
        optolink2mqtt_ver: str,
        device_dict: Dict[str, str],
        default_expire_after: int,
    ) -> str:
        """
        Returns an HomeAssistant MQTT discovery message associated with this register.
        This method is only available for registers having their "ha_discovery" metadata
        populated in the configuration file.
        See https://www.home-assistant.io/integrations/mqtt/#discovery-messages
        """
        if self.ha_discovery is None:
            return None

        # basic MQTT discovery message structure:
        msg = {
            "name": self.ha_discovery["name"],
            "device": device_dict,
            "origin": {
                "name": "optolink2mqtt",
                "sw": optolink2mqtt_ver,
                "url": "https://github.com/f18m/viessmann-optolink2mqtt",
            },
            # unique_id is required when used with device-based discovery
            "unique_id": self.get_ha_unique_id(device_name),
            # the state topic is always populated as it's mandatory for all platforms
            "state_topic": self.get_mqtt_state_topic(),
        }

        # parameters that are optionals from optolink2mqtt perspective:
        # note that HomeAssistant might require some of them depending on the 'platform' used
        optional_parameters = [
            "icon",
            "device_class",
            "state_class",
            "unit_of_measurement",
            "entity_category",
            "payload_on",
            "payload_off",
            "availability_topic",
            "payload_available",
            "payload_not_available",
            "min",
            "max",
            "step",
            "mode",
            "optimistic",
            "value_template",
        ]
        for o in optional_parameters:
            # NOTE: compare against None, since falsy values like "optimistic: false"
            # or "min: 0" are meaningful and must be forwarded to HomeAssistant
            if self.ha_discovery.get(o) is not None:
                msg[o] = self.ha_discovery[o]

        # "options" field is populated only for "select" and "sensor" platform with enum_dict defined
        if (
            self.ha_discovery["platform"] == "select"
            or self.ha_discovery["platform"] == "sensor"
        ):
            if self.enum_dict is not None:
                msg["options"] = list(self.enum_dict.values())

        # "command_topic" is populated only for platforms that allow HomeAssistant to send commands / write values:
        if self.writable:
            msg["command_topic"] = self.get_mqtt_command_topic()

        # expire_after is populated with user preference or a meaningful default value:
        if self.ha_discovery.get("expire_after") is not None:
            msg["expire_after"] = self.ha_discovery["expire_after"]
        elif default_expire_after:
            msg["expire_after"] = default_expire_after

        return json.dumps(msg)

    def get_ha_discovery_topic(self, ha_topic: str, device_name: str) -> str:
        """
        Returns the TOPIC associated with the PAYLOAD returned by get_ha_discovery_payload()
        """
        # the topic shall be in format
        #   <discovery_prefix>/<component>/[<node_id>/]<object_id>/config
        # where
        #   "component" is the platform (sensor, switch, select, number, etc.)
        #   "node_id" is the name of the device that groups all the entities
        #   "object_id" is an ID unique inside the component
        # see https://www.home-assistant.io/integrations/mqtt/#discovery-topic
        unique_id = self.get_ha_unique_id(device_name)
        return f"{ha_topic}/{self.ha_discovery['platform']}/{device_name}/{unique_id}/config"
