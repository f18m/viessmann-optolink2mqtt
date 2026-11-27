"""
datetime_bcd.py
----------------
Encoding and decoding of the Viessmann "DateTimeBCD" register format
Copyright (C) 2026 Francesco Montorsi

Licensed under the GNU GENERAL PUBLIC LICENSE, Version 3 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.gnu.org/licenses/gpl-3.0.html

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

A DateTimeBCD register is 8 bytes long, each byte holding two BCD digits:

    byte:   0        1     2      3    4        5     6       7
    field:  century  year  month  day  weekday  hour  minute  second

e.g. 20 26 11 27 04 11 53 53 is Friday 2026-11-27 11:53:53.
The weekday is 0=Monday ... 6=Sunday, as read from the clock of a Vitocal heat pump.
The date and time are the local time of the Viessmann device, without timezone.
Viessmann uses 1970-01-01 00:00:00 to mean "not set" (e.g. for holiday programs);
its weekday byte is always 04, so it is kept as a constant.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DATETIME_BCD_LENGTH = 8

# the value Viessmann devices use for a date/time that is not set:
UNSET_RAWDATA = bytes.fromhex("1970010104000000")

# any decoded date before this year is considered "not set"
MIN_VALID_YEAR = 2000

# payload published on MQTT for a date/time that is not set; HomeAssistant shows it as "unknown"
UNSET_PAYLOAD = "None"


def parse_timezone(name: str | None) -> tzinfo | None:
    """
    Returns the tzinfo for the given IANA timezone name (e.g. "Europe/Berlin"),
    or None (meaning: the local timezone of the host) if name is None.
    Raises ValueError if the name is not a known timezone.
    """
    if name is None:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError(f"unknown timezone '{name}': {e}")


def _bcd_to_int(b: int) -> int:
    hi, lo = b >> 4, b & 0x0F
    if hi > 9 or lo > 9:
        raise ValueError(f"byte 0x{b:02X} is not a valid BCD value")
    return hi * 10 + lo


def _int_to_bcd(v: int) -> int:
    return ((v // 10) << 4) | (v % 10)


def decode(rawdata: bytes) -> datetime | None:
    """
    Decodes 8 bytes of DateTimeBCD into a naive datetime (device local time).
    Returns None if the date/time is "not set" (any year before MIN_VALID_YEAR).
    The weekday byte is ignored: the weekday is implied by the date, and some devices
    store a stale weekday byte.
    Raises ValueError if the bytes are not a valid DateTimeBCD value.
    """
    if len(rawdata) != DATETIME_BCD_LENGTH:
        raise ValueError(
            f"expected {DATETIME_BCD_LENGTH} bytes of DateTimeBCD, got {len(rawdata)}"
        )
    d = [_bcd_to_int(b) for b in rawdata]
    year = d[0] * 100 + d[1]
    if year < MIN_VALID_YEAR:
        return None
    # datetime() raises ValueError for out-of-range month/day/hour/etc
    return datetime(year, d[2], d[3], d[5], d[6], d[7])


def encode(dt: datetime | None) -> bytearray:
    """
    Encodes a naive datetime (device local time) into 8 bytes of DateTimeBCD.
    None, or any date before MIN_VALID_YEAR, is encoded as the "not set" value.
    """
    if dt is None or dt.year < MIN_VALID_YEAR:
        return bytearray(UNSET_RAWDATA)
    fields = [
        dt.year // 100,
        dt.year % 100,
        dt.month,
        dt.day,
        dt.weekday(),
        dt.hour,
        dt.minute,
        dt.second,
    ]
    return bytearray(_int_to_bcd(v) for v in fields)
