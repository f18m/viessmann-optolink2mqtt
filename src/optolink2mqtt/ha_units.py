"""
ha_units.py
----------------
Home Assistant units
Partially taken from HomeAssistant source code

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

from typing import List


class HomeAssistantMeasurementUnits:

    ALL_CONSTANTS = []

    @staticmethod
    def get_all_constants() -> List[str]:
        """
        Returns a list of unit_of_measurement values supported by HomeAssistant 2025.12
        """

        #
        # IMPORTANT: as of Feb 2025, there's no Python package that provides an up-to-date
        # list of measurement units supported by Home Assistant. So this list is based on the
        # https://github.com/home-assistant/core/blob/master/homeassistant/const.py
        # file (might need to be updated in the future as new units are added to HA)
        #
        units = [
            # Apparent power
            "mVA",
            "VA",
            "kVA",
            # Power
            "mW",
            "W",
            "kW",
            "MW",
            "GW",
            "TW",
            "BTU/h",
            # Reactive power
            "mvar",
            "var",
            "kvar",
            # Energy
            "J",
            "kJ",
            "MJ",
            "GJ",
            "mWh",
            "Wh",
            "kWh",
            "MWh",
            "GWh",
            "TWh",
            "cal",
            "kcal",
            "Mcal",
            "Gcal",
            # Reactive energy
            "varh",
            "kvarh",
            # Energy distance
            "kWh/100km",
            "Wh/km",
            "mi/kWh",
            "km/kWh",
            # Electric current
            "mA",
            "A",
            # Electric potential
            "μV",
            "mV",
            "V",
            "kV",
            "MV",
            # Degree
            "°",
            # Currency
            "€",
            "$",
            "¢",
            # Temperature
            "°C",
            "°F",
            "K",
            # Time
            "μs",
            "ms",
            "s",
            "min",
            "h",
            "d",
            "w",
            "m",
            "y",
            # Length
            "mm",
            "cm",
            "m",
            "km",
            "in",
            "ft",
            "yd",
            "mi",
            "nmi",
            # Frequency
            "Hz",
            "kHz",
            "MHz",
            "GHz",
            # Pressure
            "mPa",
            "Pa",
            "hPa",
            "kPa",
            "bar",
            "cbar",
            "mbar",
            "mmHg",
            "inHg",
            "inH₂O",
            "psi",
            # Sound pressure
            "dB",
            "dBA",
            # Volume
            "ft³",
            "CCF",
            "MCF",
            "m³",
            "L",
            "mL",
            "gal",
            "fl. oz.",
            # Volume flow rate
            "m³/h",
            "m³/min",
            "m³/s",
            "ft³/min",
            "L/h",
            "L/min",
            "L/s",
            "gal/h",
            "gal/min",
            "gal/d",
            "mL/s",
            # Area
            "m²",
            "cm²",
            "km²",
            "mm²",
            "in²",
            "ft²",
            "yd²",
            "mi²",
            "ac",
            "ha",
            # Mass
            "g",
            "kg",
            "mg",
            "μg",
            "oz",
            "lb",
            "st",
            # Conductivity
            "S/cm",
            "μS/cm",
            "mS/cm",
            # Light
            "lx",
            # UV index
            "UV index",
            # Percentage
            "%",
            # Rotational speed
            "rpm",
            # Irradiance
            "W/m²",
            "BTU/(h⋅ft²)",
            # Volumetric flux
            "in/d",
            "in/h",
            "mm/d",
            "mm/h",
            # Precipitation depth
            "in",
            "mm",
            "cm",
            # Concentration
            "g/m³",
            "mg/m³",
            "μg/m³",
            "μg/ft³",
            "p/m³",
            "ppm",
            "ppb",
            # Blood glucose concentration
            "mg/dL",
            "mmol/L",
            # Speed
            "Beaufort",
            "ft/s",
            "in/s",
            "m/min",
            "m/s",
            "km/h",
            "kn",
            "mph",
            "mm/s",
            # Signal strength
            "dB",
            "dBm",
            # Information
            "bit",
            "kbit",
            "Mbit",
            "Gbit",
            "B",
            "kB",
            "MB",
            "GB",
            "TB",
            "PB",
            "EB",
            "ZB",
            "YB",
            "KiB",
            "MiB",
            "GiB",
            "TiB",
            "PiB",
            "EiB",
            "ZiB",
            "YiB",
            # Data rate
            "bit/s",
            "kbit/s",
            "Mbit/s",
            "Gbit/s",
            "B/s",
            "kB/s",
            "MB/s",
            "GB/s",
            "KiB/s",
            "MiB/s",
            "GiB/s",
        ]

        return units
