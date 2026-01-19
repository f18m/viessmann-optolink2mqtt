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

from typing import Dict, Any

# import hashlib
import json


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

    def __init__(
        self,
        reg: Dict[str, Any],
        mqtt_base_topic: str,
    ):
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
        self.byte_filter = str(reg["byte_filter"])
        self.enum_dict = reg["enum"]

        # optional Home Assistant discovery configuration
        self.ha_discovery = reg["ha_discovery"]
        if self.ha_discovery is not None:
            self.check_ha_discovery_validity()

    def _sanitize_name(self, name: str) -> str:
        """
        Returns a sanitized version of the given name, suitable to be used as MQTT topic part
        or HomeAssistant unique ID part.
        """
        sanitized = name.lower()
        sanitized = sanitized.replace(" ", "_")
        sanitized = sanitized.replace("-", "_")
        sanitized = sanitized.replace("/", "_")
        sanitized = sanitized.replace("\\", "_")
        sanitized = sanitized.replace(".", "_")
        sanitized = sanitized.replace(",", "_")
        sanitized = sanitized.replace(";", "_")
        sanitized = sanitized.replace(":", "_")
        sanitized = sanitized.replace("(", "")
        sanitized = sanitized.replace(")", "")
        sanitized = sanitized.replace("[", "")
        sanitized = sanitized.replace("]", "")
        sanitized = sanitized.replace("{", "")
        sanitized = sanitized.replace("}", "")
        sanitized = sanitized.replace('"', "")
        sanitized = sanitized.replace("'", "")

        sanitized = sanitized.replace("__", "_")
        sanitized = sanitized.strip("_")

        # ensure only ASCII characters are present
        sanitized = sanitized.encode("ascii", errors="ignore").decode("ascii")
        return sanitized

    def get_human_readable_description(self) -> str:
        """
        Returns a human-readable description for this register
        """
        return f"name=[{self.name}], addr=0x{self.address:04X}, len={self.length}, signed={self.signed}, scale={self.scale_factor}, byte_filter={self.byte_filter}, enum={self.enum_dict}, has HA discovery={self.ha_discovery is not None}"

    def get_next_occurrence_in_seconds(self) -> float:
        """
        Returns the sampling period in seconds
        """
        return self.sampling_period_sec

    def get_value_from_rawdata(self, rawdata: bytearray) -> Any:
        """
        Returns the value of the register from the given raw data.
        This function was named "bytesval" in original optolink-splitter codebase
        """

        if self.enum_dict is not None:
            val = int.from_bytes(rawdata, byteorder="little", signed=self.signed)
            return self.enum_dict.get(val, f"Unknown ({val})")
        else:
            if self.byte_filter is not None:
                # apply byte filter
                parts = self.byte_filter.split(":")
                if parts[0] == "b" and len(parts) == 3:
                    start = int(parts[1])
                    end = int(parts[2]) + 1  # inclusive
                    rawdata = rawdata[start:end]

            val = int.from_bytes(rawdata, byteorder="little", signed=self.signed)
            if self.scale_factor != 1.0:
                val = round(val * self.scale_factor, OptolinkVS2Register.MAX_DECIMALS)
        return val

    def get_rawdata_from_value(self, str_value: str) -> bytearray:
        """
        Converts a generic string into raw data (bytearray) suitable to be written
        into the register of the Viessmann device.
        Raises ValueError in case of invalid value.
        """
        val = 0
        if self.enum_dict is not None:
            # reverse lookup in enum dict
            reverse_enum = {v: k for k, v in self.enum_dict.items()}
            if str_value not in reverse_enum:
                raise ValueError(
                    f"Invalid value '{str_value}' for register '{self.name}'; valid values are: {list(self.enum_dict.values())}"
                )
            val = reverse_enum[str_value]
        else:
            # normal numeric value
            if self.scale_factor != 1.0:
                val = int(
                    round(
                        float(str_value) / self.scale_factor,
                        OptolinkVS2Register.MAX_DECIMALS,
                    )
                )
            else:
                val = int(str_value)
        rawdata = val.to_bytes(self.length, byteorder="little", signed=self.signed)
        if len(rawdata) != self.length:
            raise ValueError(
                f"Value '{str_value}' for register '{self.name}' cannot be represented in {self.length} bytes."
            )

        return bytearray(rawdata)

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
        Checks if HA discovery information are coherent with the register definition
        """
        # ensure ha_discovery is a dict
        if not isinstance(self.ha_discovery, dict):
            raise Exception(
                f"Register '{self.name}' has invalid HA discovery configuration."
            )

        # required parameters: name & platform
        if self.ha_discovery["name"] is None or self.ha_discovery["name"] == "":
            raise Exception(
                f"Register '{self.name}' has invalid HA discovery 'name' property."
            )
        if self.ha_discovery["platform"] is None or self.ha_discovery["platform"] == "":
            raise Exception(
                f"Register '{self.name}' has invalid HA discovery 'platform' property."
            )

        HA_PLATFORMS_WRITABLE = ["switch", "select", "number"]

        if self.writable and self.ha_discovery["platform"] not in HA_PLATFORMS_WRITABLE:
            raise Exception(
                f"Register '{self.name}' is writable but has incompatible HA discovery 'platform' property '{self.ha_discovery['platform']}'."
            )
        if not self.writable and self.ha_discovery["platform"] in HA_PLATFORMS_WRITABLE:
            raise Exception(
                f"Register '{self.name}' is not writable but has incompatible HA discovery 'platform' property '{self.ha_discovery['platform']}'."
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
        ]
        for o in optional_parameters:
            if o in self.ha_discovery and self.ha_discovery[o]:
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
        if self.ha_discovery["expire_after"]:
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
