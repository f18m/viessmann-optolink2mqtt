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
        mqtt_base_topic: str = "",
        ha_discovery: Optional[Dict[str, Any]] = None,
    ):
        # basic metadata
        self.name = name
        self.sampling_period_sec = sampling_period_sec
        self.mqtt_base_topic = mqtt_base_topic
        if self.mqtt_base_topic.endswith("/"):
            self.mqtt_base_topic = self.mqtt_base_topic[:-1]

        # register definition
        self.address = address
        self.length = length
        self.signed = signed
        self.scale_factor = scale_factor

        # optional Home Assistant discovery configuration
        self.ha_discovery = ha_discovery

    def get_human_readable_description(self) -> str:
        """
        Returns a human-readable description for this register
        """
        return f"name=[{self.name}], addr=0x{self.address:04X}, len={self.length}, signed={self.signed}, scale={self.scale_factor}"

    def get_next_occurrence_in_seconds(self) -> float:
        """
        Returns the sampling period in seconds
        """
        return self.sampling_period_sec

    def get_value(self, rawdata: bytearray):
        """
        Returns the value of the register from the given raw data.
        This function was named "bytesval" in original optolink-splitter codebase
        """
        val = int.from_bytes(rawdata, byteorder="little", signed=self.signed)
        if self.scale_factor != 1.0:
            val = round(val * self.scale_factor, OptolinkVS2Register.MAX_DECIMALS)
        return val

    #
    # MQTT helpers
    #

    def get_mqtt_topic(self) -> str:
        sanitized_name = self.name.strip().replace(" ", "_").lower()
        return f"{self.mqtt_base_topic}/{sanitized_name}"

    def get_mqtt_payload(self, rawdata: bytearray) -> str:
        return f"{self.get_value(rawdata)}"
