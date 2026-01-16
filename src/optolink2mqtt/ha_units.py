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

from enum import Enum
from typing import Final, List


#
# IMPORTANT: as of Feb 2025, there's no Python package that provides an up-to-date
# list of measurement units supported by Home Assistant. So this list is based on the
# https://github.com/home-assistant/core/blob/master/homeassistant/const.py
# file (might need to be updated in the future as new units are added to HA)
#


# Apparent power units
class UnitOfApparentPower(Enum):
    """Apparent power units."""

    VOLT_AMPERE = "VA"


# Power units
class UnitOfPower(Enum):
    """Power units."""

    MILLIWATT = "mW"
    WATT = "W"
    KILO_WATT = "kW"
    MEGA_WATT = "MW"
    GIGA_WATT = "GW"
    TERA_WATT = "TW"
    BTU_PER_HOUR = "BTU/h"


# Reactive power units
class UnitOfReactivePower(Enum):
    """Reactive power units."""

    VOLT_AMPERE_REACTIVE = "var"


# Energy units
class UnitOfEnergy(Enum):
    """Energy units."""

    JOULE = "J"
    KILO_JOULE = "kJ"
    MEGA_JOULE = "MJ"
    GIGA_JOULE = "GJ"
    MILLIWATT_HOUR = "mWh"
    WATT_HOUR = "Wh"
    KILO_WATT_HOUR = "kWh"
    MEGA_WATT_HOUR = "MWh"
    GIGA_WATT_HOUR = "GWh"
    TERA_WATT_HOUR = "TWh"
    CALORIE = "cal"
    KILO_CALORIE = "kcal"
    MEGA_CALORIE = "Mcal"
    GIGA_CALORIE = "Gcal"


# Electric_current units
class UnitOfElectricCurrent(Enum):
    """Electric current units."""

    MILLIAMPERE = "mA"
    AMPERE = "A"


# Electric_potential units
class UnitOfElectricPotential(Enum):
    """Electric potential units."""

    MICROVOLT = "µV"
    MILLIVOLT = "mV"
    VOLT = "V"
    KILOVOLT = "kV"
    MEGAVOLT = "MV"


# Degree units
DEGREE: Final = "°"

# Currency units
CURRENCY_EURO: Final = "€"
CURRENCY_DOLLAR: Final = "$"
CURRENCY_CENT: Final = "¢"


# Temperature units
class UnitOfTemperature(Enum):
    """Temperature units."""

    CELSIUS = "°C"
    FAHRENHEIT = "°F"
    KELVIN = "K"


# Time units
class UnitOfTime(Enum):
    """Time units."""

    MICROSECONDS = "μs"
    MILLISECONDS = "ms"
    SECONDS = "s"
    MINUTES = "min"
    HOURS = "h"
    DAYS = "d"
    WEEKS = "w"
    MONTHS = "m"
    YEARS = "y"


# Length units
class UnitOfLength(Enum):
    """Length units."""

    MILLIMETERS = "mm"
    CENTIMETERS = "cm"
    METERS = "m"
    KILOMETERS = "km"
    INCHES = "in"
    FEET = "ft"
    YARDS = "yd"
    MILES = "mi"
    NAUTICAL_MILES = "nmi"


# Frequency units
class UnitOfFrequency(Enum):
    """Frequency units."""

    HERTZ = "Hz"
    KILOHERTZ = "kHz"
    MEGAHERTZ = "MHz"
    GIGAHERTZ = "GHz"


# Pressure units
class UnitOfPressure(Enum):
    """Pressure units."""

    PA = "Pa"
    HPA = "hPa"
    KPA = "kPa"
    BAR = "bar"
    CBAR = "cbar"
    MBAR = "mbar"
    MMHG = "mmHg"
    INHG = "inHg"
    PSI = "psi"


# Sound pressure units
class UnitOfSoundPressure(Enum):
    """Sound pressure units."""

    DECIBEL = "dB"
    WEIGHTED_DECIBEL_A = "dBA"


# Volume units
class UnitOfVolume(Enum):
    """Volume units."""

    CUBIC_FEET = "ft³"
    CENTUM_CUBIC_FEET = "CCF"
    CUBIC_METERS = "m³"
    LITERS = "L"
    MILLILITERS = "mL"
    GALLONS = "gal"
    """Assumed to be US gallons in conversion utilities.

    British/Imperial gallons are not yet supported"""
    FLUID_OUNCES = "fl. oz."
    """Assumed to be US fluid ounces in conversion utilities.

    British/Imperial fluid ounces are not yet supported"""


# Volume Flow Rate units
class UnitOfVolumeFlowRate(Enum):
    """Volume flow rate units."""

    CUBIC_METERS_PER_HOUR = "m³/h"
    CUBIC_FEET_PER_MINUTE = "ft³/min"
    LITERS_PER_MINUTE = "L/min"
    GALLONS_PER_MINUTE = "gal/min"
    MILLILITERS_PER_SECOND = "mL/s"


class UnitOfArea(Enum):
    """Area units."""

    SQUARE_METERS = "m²"
    SQUARE_CENTIMETERS = "cm²"
    SQUARE_KILOMETERS = "km²"
    SQUARE_MILLIMETERS = "mm²"
    SQUARE_INCHES = "in²"
    SQUARE_FEET = "ft²"
    SQUARE_YARDS = "yd²"
    SQUARE_MILES = "mi²"
    ACRES = "ac"
    HECTARES = "ha"


# Mass units
class UnitOfMass(Enum):
    """Mass units."""

    GRAMS = "g"
    KILOGRAMS = "kg"
    MILLIGRAMS = "mg"
    MICROGRAMS = "µg"
    OUNCES = "oz"
    POUNDS = "lb"
    STONES = "st"


# Light units
LIGHT_LUX: Final = "lx"

# UV Index units
UV_INDEX: Final = "UV index"

# Percentage units
PERCENTAGE: Final = "%"

# Rotational speed units
REVOLUTIONS_PER_MINUTE: Final = "rpm"


# Irradiance units
class UnitOfIrradiance(Enum):
    """Irradiance units."""

    WATTS_PER_SQUARE_METER = "W/m²"
    BTUS_PER_HOUR_SQUARE_FOOT = "BTU/(h⋅ft²)"


class UnitOfVolumetricFlux(Enum):
    """Volumetric flux, commonly used for precipitation intensity.

    The derivation of these units is a volume of rain amassing in a container
    with constant cross section in a given time
    """

    INCHES_PER_DAY = "in/d"
    """Derived from in³/(in²⋅d)"""

    INCHES_PER_HOUR = "in/h"
    """Derived from in³/(in²⋅h)"""

    MILLIMETERS_PER_DAY = "mm/d"
    """Derived from mm³/(mm²⋅d)"""

    MILLIMETERS_PER_HOUR = "mm/h"
    """Derived from mm³/(mm²⋅h)"""


class UnitOfPrecipitationDepth(Enum):
    """Precipitation depth.

    The derivation of these units is a volume of rain amassing in a container
    with constant cross section
    """

    INCHES = "in"
    """Derived from in³/in²"""

    MILLIMETERS = "mm"
    """Derived from mm³/mm²"""

    CENTIMETERS = "cm"
    """Derived from cm³/cm²"""


# Concentration units
CONCENTRATION_MICROGRAMS_PER_CUBIC_METER: Final = "µg/m³"
CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER: Final = "mg/m³"
CONCENTRATION_MICROGRAMS_PER_CUBIC_FOOT: Final = "μg/ft³"
CONCENTRATION_PARTS_PER_CUBIC_METER: Final = "p/m³"
CONCENTRATION_PARTS_PER_MILLION: Final = "ppm"
CONCENTRATION_PARTS_PER_BILLION: Final = "ppb"


class UnitOfBloodGlucoseConcentration(Enum):
    """Blood glucose concentration units."""

    MILLIGRAMS_PER_DECILITER = "mg/dL"
    MILLIMOLE_PER_LITER = "mmol/L"


# Speed units
class UnitOfSpeed(Enum):
    """Speed units."""

    BEAUFORT = "Beaufort"
    FEET_PER_SECOND = "ft/s"
    INCHES_PER_SECOND = "in/s"
    METERS_PER_SECOND = "m/s"
    KILOMETERS_PER_HOUR = "km/h"
    KNOTS = "kn"
    MILES_PER_HOUR = "mph"
    MILLIMETERS_PER_SECOND = "mm/s"


# Signal_strength units
SIGNAL_STRENGTH_DECIBELS: Final = "dB"
SIGNAL_STRENGTH_DECIBELS_MILLIWATT: Final = "dBm"


# Data units
class UnitOfInformation(Enum):
    """Information units."""

    BITS = "bit"
    KILOBITS = "kbit"
    MEGABITS = "Mbit"
    GIGABITS = "Gbit"
    BYTES = "B"
    KILOBYTES = "kB"
    MEGABYTES = "MB"
    GIGABYTES = "GB"
    TERABYTES = "TB"
    PETABYTES = "PB"
    EXABYTES = "EB"
    ZETTABYTES = "ZB"
    YOTTABYTES = "YB"
    KIBIBYTES = "KiB"
    MEBIBYTES = "MiB"
    GIBIBYTES = "GiB"
    TEBIBYTES = "TiB"
    PEBIBYTES = "PiB"
    EXBIBYTES = "EiB"
    ZEBIBYTES = "ZiB"
    YOBIBYTES = "YiB"


# Data_rate units
class UnitOfDataRate(Enum):
    """Data rate units."""

    BITS_PER_SECOND = "bit/s"
    KILOBITS_PER_SECOND = "kbit/s"
    MEGABITS_PER_SECOND = "Mbit/s"
    GIGABITS_PER_SECOND = "Gbit/s"
    BYTES_PER_SECOND = "B/s"
    KILOBYTES_PER_SECOND = "kB/s"
    MEGABYTES_PER_SECOND = "MB/s"
    GIGABYTES_PER_SECOND = "GB/s"
    KIBIBYTES_PER_SECOND = "KiB/s"
    MEBIBYTES_PER_SECOND = "MiB/s"
    GIBIBYTES_PER_SECOND = "GiB/s"


class HomeAssistantMeasurementUnits:

    ALL_CONSTANTS = []

    @staticmethod
    def get_all_constants() -> List[str]:
        """
        Returns a list of unit_of_measurement values supported by HomeAssistant 2025.2
        """
        if len(HomeAssistantMeasurementUnits.ALL_CONSTANTS) == 0:
            constants = []

            # Extracting values from StrEnum classes
            for obj in globals().values():
                if isinstance(obj, type) and issubclass(obj, Enum):
                    constants.extend(obj._member_map_.values())

            # Extracting Final constants
            constants.extend(
                [
                    DEGREE,
                    CURRENCY_EURO,
                    CURRENCY_DOLLAR,
                    CURRENCY_CENT,
                    LIGHT_LUX,
                    UV_INDEX,
                    PERCENTAGE,
                    REVOLUTIONS_PER_MINUTE,
                    SIGNAL_STRENGTH_DECIBELS,
                    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
                    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
                    CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER,
                    CONCENTRATION_MICROGRAMS_PER_CUBIC_FOOT,
                    CONCENTRATION_PARTS_PER_CUBIC_METER,
                    CONCENTRATION_PARTS_PER_MILLION,
                    CONCENTRATION_PARTS_PER_BILLION,
                ]
            )

            HomeAssistantMeasurementUnits.ALL_CONSTANTS = [str(c) for c in constants]

        return HomeAssistantMeasurementUnits.ALL_CONSTANTS
