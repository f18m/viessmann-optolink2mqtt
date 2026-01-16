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

from typing import Optional, Dict, Any

# import hashlib
import json


class OptolinkVS2Register:
    """
    A register to be read or written inside the Viessmann device, via the Optolink interface
    """

    MAX_DECIMALS = 2

    def __init__(
        self,
        name: str = "external_temperature",
        sampling_period_sec: int = 1,
        address: int = 0x0101,
        length: int = 2,
        signed: bool = False,
        scale_factor: float = 1.0,
        byte_filter: str = None,
        enum_dict: Optional[Dict[int, str]] = None,
        mqtt_base_topic: str = "",
        ha_discovery: Optional[Dict[str, Any]] = None,
    ):
        # basic metadata
        self.name = name
        self.sanitized_name = self.name.strip().replace(" ", "_").lower()
        self.sampling_period_sec = sampling_period_sec
        self.mqtt_base_topic = mqtt_base_topic
        if self.mqtt_base_topic.endswith("/"):
            self.mqtt_base_topic = self.mqtt_base_topic[:-1]

        # register definition
        self.address = address
        self.length = length
        self.signed = signed
        self.scale_factor = scale_factor
        self.byte_filter = byte_filter
        self.enum_dict = enum_dict

        # optional Home Assistant discovery configuration
        self.ha_discovery = ha_discovery

    def get_human_readable_description(self) -> str:
        """
        Returns a human-readable description for this register
        """
        return f"name=[{self.name}], addr=0x{self.address:04X}, len={self.length}, signed={self.signed}, scale={self.scale_factor}, byte_filter={self.byte_filter}, enum={self.enum_dict}"

    def get_next_occurrence_in_seconds(self) -> float:
        """
        Returns the sampling period in seconds
        """
        return self.sampling_period_sec

    def get_value(self, rawdata: bytearray) -> Any:
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

    #
    # MQTT helpers
    #

    def get_mqtt_topic(self) -> str:
        return f"{self.mqtt_base_topic}/{self.sanitized_name}"

    def get_mqtt_payload(self, rawdata: bytearray) -> str:
        return f"{self.get_value(rawdata)}"

    #
    # MQTT/HomeAssistant Discovery Message helpers
    #

    def get_ha_unique_id(self, device_name: str) -> str:
        """
        Returns a reasonable-unique ID to be used inside HA discovery messages
        """

        # concatenated = "".join([,])
        # hash_object = hashlib.sha256(concatenated.encode())
        # hash_hex = hash_object.hexdigest()
        # return f"{device_name}-{self.task_name}-{hash_hex[:12]}"
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
        Returns an HomeAssistant MQTT discovery message associated with this task.
        This method is only available for single-valued tasks, having their "ha_discovery" metadata
        populated in the configuration file.
        See https://www.home-assistant.io/integrations/mqtt/#discovery-messages
        """
        if self.ha_discovery is None:
            return None

        # required parameters
        if self.ha_discovery["name"] is None or self.ha_discovery["name"] == "":
            raise Exception(
                f"Register '{self.name}' has invalid HA discovery 'name' property."
            )

        msg = {
            "device": device_dict,
            "origin": {
                "name": "optolink2mqtt",
                "sw": optolink2mqtt_ver,
                "url": "https://github.com/f18m/viessmann-optolink2mqtt",
            },
            "unique_id": self.get_ha_unique_id(device_name),
            "state_topic": self.get_mqtt_topic(),
            "name": self.ha_discovery["name"],
        }

        # optional parameters
        # FIXME: should we add also "availability_topic", "payload_available", "payload_not_available" ?
        optional_parameters = [
            "icon",
            "device_class",
            "state_class",
            "unit_of_measurement",
            "payload_on",
            "payload_off",
        ]
        for o in optional_parameters:
            if o in self.ha_discovery and self.ha_discovery[o]:
                msg[o] = self.ha_discovery[o]

        if self.enum_dict is not None:
            msg["options"] = list(self.enum_dict.values())

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
        # see https://www.home-assistant.io/integrations/mqtt/#discovery-topic
        unique_id = self.get_ha_unique_id(device_name)
        return f"{ha_topic}/{self.ha_discovery['platform']}/{device_name}/{unique_id}/config"
