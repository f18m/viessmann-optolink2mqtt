"""
optolinkvs2_register.py
----------------

Copyright 2026 Francesco Montorsi

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

    def __init__(
        self,
        name: str = "external_temperature",
        sampling_period_sec: int = 1,
        address: int = 0x0101,
        length: int = 2,
        signed: bool = False,
        ha_discovery: Optional[Dict[str, Any]] = None,
    ):
        # basic metadata
        self.name = name
        self.sampling_period_sec = sampling_period_sec

        # register definition
        self.address = address
        self.length = length
        self.signed = signed

        # optional Home Assistant discovery configuration
        self.ha_discovery = ha_discovery

    def get_next_occurrence_in_seconds(self) -> float:
        return self.sampling_period_sec
