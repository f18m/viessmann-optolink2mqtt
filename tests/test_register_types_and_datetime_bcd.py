"""
Tests for the register "type" attribute and the Viessmann DateTimeBCD format.
"""

import json
import os
import sys
from datetime import datetime, timezone

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt import datetime_bcd, read_register  # noqa: E402
from optolink2mqtt.cli import parse_args  # noqa: E402
from optolink2mqtt.config import Config  # noqa: E402
from optolink2mqtt.optolinkvs2_protocol import (  # noqa: E402
    ErrorCode,
    OptolinkVS2RxData,
)
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402

SCHEMA = os.path.realpath(SRC_DIR + "/optolink2mqtt/schema/optolink2mqtt.schema.yaml")

BERLIN = datetime_bcd.parse_timezone("Europe/Berlin")

# real reading of register 0x08E0 (device clock) of a Vitocal, see GitHub issue #18:
# Friday 2026-11-27 11:53:53 with weekday byte 0x04
REAL_HW_SAMPLE = bytes.fromhex("2026112704115353")


def make_register(
    type_="datetime_bcd",
    length=8,
    writable=True,
    platform="datetime",
    tz=BERLIN,
    **overrides,
):
    reg = {
        "name": "holiday_program_start",
        "sampling_period_seconds": 60,
        "register": 0x2309,
        "length": length,
        "signed": False,
        "writable": writable,
        "type": type_,
        "scale_factor": 1.0,
        "byte_filter": None,
        "encoding": "little_endian",
        "formatter": None,
        "enum": None,
        "ha_discovery": (
            None
            if platform is None
            else {"name": "Holiday Program Start", "platform": platform}
        ),
    }
    reg.update(overrides)
    return OptolinkVS2Register(reg, "optolink2mqtt", tz)


#
# datetime_bcd codec
#


def test_decode_real_hw_sample_ignores_the_weekday_byte():
    assert datetime_bcd.decode(REAL_HW_SAMPLE) == datetime(2026, 11, 27, 11, 53, 53)


def test_decode_unset_value():
    assert datetime_bcd.decode(datetime_bcd.UNSET_RAWDATA) is None


@pytest.mark.parametrize(
    "hexdata",
    [
        "20261127041153",  # too short
        "2026112704115A53",  # 0x5A is not BCD
        "2026132704115353",  # month 13
        "2026023004115353",  # February 30th
        "2026112704245353",  # hour 24
    ],
)
def test_decode_invalid_data(hexdata):
    with pytest.raises(ValueError):
        datetime_bcd.decode(bytes.fromhex(hexdata))


def test_encode_weekday_is_monday_zero():
    # same bytes the device clock had on Friday 2026-11-27 11:53:53
    raw = datetime_bcd.encode(datetime(2026, 11, 27, 11, 53, 53))
    assert raw == REAL_HW_SAMPLE
    # 2026-11-29 is a Sunday
    assert datetime_bcd.encode(datetime(2026, 11, 29, 23, 59, 59))[4] == 0x06
    # 2026-11-30 is a Monday
    assert datetime_bcd.encode(datetime(2026, 11, 30))[4] == 0x00


def test_encode_none_and_old_dates_give_the_unset_value():
    assert datetime_bcd.encode(None) == datetime_bcd.UNSET_RAWDATA
    assert datetime_bcd.encode(datetime(1970, 1, 1)) == datetime_bcd.UNSET_RAWDATA


def test_encode_decode_roundtrip():
    dt = datetime(2099, 12, 31, 23, 59, 59)
    assert datetime_bcd.decode(datetime_bcd.encode(dt)) == dt


def test_parse_timezone():
    assert datetime_bcd.parse_timezone(None) is None
    assert str(datetime_bcd.parse_timezone("Europe/Rome")) == "Europe/Rome"
    with pytest.raises(ValueError, match="Mars/Olympus"):
        datetime_bcd.parse_timezone("Mars/Olympus")


#
# datetime_bcd registers: reading
#


def test_read_real_hw_sample_with_device_timezone():
    reg = make_register()
    assert reg.get_value_from_rawdata(bytearray(REAL_HW_SAMPLE)) == (
        "2026-11-27T11:53:53+01:00"
    )


def test_read_uses_daylight_saving_offset():
    reg = make_register()
    raw = datetime_bcd.encode(datetime(2026, 7, 1, 12, 0, 0))
    assert reg.get_value_from_rawdata(raw) == "2026-07-01T12:00:00+02:00"


def test_read_without_timezone_uses_the_host_timezone():
    reg = make_register(tz=None)
    value = reg.get_value_from_rawdata(bytearray(REAL_HW_SAMPLE))
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.replace(tzinfo=None) == datetime(2026, 11, 27, 11, 53, 53)


def test_read_unset_value_publishes_none():
    reg = make_register()
    assert reg.get_value_from_rawdata(bytearray(datetime_bcd.UNSET_RAWDATA)) == "None"


def test_read_invalid_data_returns_none():
    reg = make_register()
    assert reg.get_value_from_rawdata(bytearray.fromhex("2026FF2704115353")) is None


#
# datetime_bcd registers: writing
#


def test_write_utc_from_homeassistant_is_converted_to_device_time():
    reg = make_register()
    # 2026-12-24 09:30 UTC is 10:30 in Berlin; 2026-12-24 is a Thursday (weekday 03)
    raw = reg.get_rawdata_from_value("2026-12-24T09:30:00+00:00")
    assert raw.hex() == "2026122403103000"


def test_write_accepts_z_suffix_and_drops_microseconds():
    reg = make_register()
    raw = reg.get_rawdata_from_value("2026-12-24T09:30:00.123456Z")
    assert raw.hex() == "2026122403103000"


def test_write_crossing_midnight_changes_the_date():
    reg = make_register()
    # 23:30 UTC on Dec 31st is already January 1st in Berlin
    raw = reg.get_rawdata_from_value("2026-12-31T23:30:00+00:00")
    assert datetime_bcd.decode(raw) == datetime(2027, 1, 1, 0, 30, 0)


def test_write_naive_datetime_is_taken_as_device_time():
    reg = make_register()
    raw = reg.get_rawdata_from_value("2026-12-24 10:30:00")
    assert raw.hex() == "2026122403103000"


def test_write_date_only():
    reg = make_register()
    assert reg.get_rawdata_from_value("2026-12-24").hex() == "2026122403000000"


@pytest.mark.parametrize("payload", ["None", "none", "", "  ", "1970-01-01T00:00:00"])
def test_write_none_clears_the_datetime(payload):
    reg = make_register()
    assert reg.get_rawdata_from_value(payload) == datetime_bcd.UNSET_RAWDATA


@pytest.mark.parametrize("payload", ["tomorrow", "2026-13-01", "12345", "nan"])
def test_write_invalid_payload_is_rejected(payload):
    reg = make_register()
    assert reg.get_rawdata_from_value(payload) is None


def test_write_roundtrip_through_published_value():
    reg = make_register()
    published = reg.get_value_from_rawdata(bytearray(REAL_HW_SAMPLE))
    raw = reg.get_rawdata_from_value(published)
    assert raw == REAL_HW_SAMPLE


def test_write_bounds_do_not_apply_to_datetimes():
    reg = make_register()
    assert reg.is_within_write_bounds(bytearray(REAL_HW_SAMPLE))


#
# type validation
#


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"type_": "string"}, "invalid type"),
        ({"length": 4}, "length 4"),
        ({"signed": True}, "signed"),
        ({"byte_filter": "b:0:3"}, "byte_filter"),
        ({"scale_factor": 0.1}, "scale_factor"),
    ],
)
def test_invalid_datetime_bcd_definitions_are_rejected(kwargs, match):
    with pytest.raises(ValueError, match=match):
        make_register(**kwargs)


def test_int_type_rejects_a_scale_factor():
    with pytest.raises(ValueError, match="type: float"):
        make_register(type_="int", length=2, platform=None, scale_factor=0.1)


def test_enum_dictionary_requires_enum_type():
    with pytest.raises(ValueError, match="type: enum"):
        make_register(type_="int", length=1, platform=None, enum={0: "Off"})


def test_enum_type_requires_an_enum_dictionary():
    with pytest.raises(ValueError, match="no 'enum' dictionary"):
        make_register(type_="enum", length=1, platform=None)


def test_float_type_without_scale_factor_returns_floats():
    reg = make_register(type_="float", length=1, platform=None)
    value = reg.get_value_from_rawdata(bytearray([42]))
    assert value == 42.0 and isinstance(value, float)
    assert reg.get_rawdata_from_value("42.0") == bytearray([42])


def test_datetime_platform_requires_datetime_bcd_type():
    with pytest.raises(ValueError, match="requires 'type: datetime_bcd'"):
        make_register(type_="int", length=2, platform="datetime")


def test_read_only_datetime_bcd_cannot_use_datetime_platform():
    with pytest.raises(ValueError, match="not writable"):
        make_register(writable=False, platform="datetime")


def test_read_only_datetime_bcd_as_timestamp_sensor():
    reg = make_register(writable=False, platform="sensor")
    assert reg.get_value_from_rawdata(bytearray(REAL_HW_SAMPLE)).endswith("+01:00")


#
# HomeAssistant discovery
#


def test_ha_discovery_for_datetime_platform():
    reg = make_register()
    payload = json.loads(
        reg.get_ha_discovery_payload("vitocal", "1.0", {"name": "vitocal"}, 0)
    )
    assert payload["state_topic"] == "optolink2mqtt/holiday_program_start"
    assert payload["command_topic"] == "optolink2mqtt/holiday_program_start/set"
    assert "state_class" not in payload
    assert "timezone" not in payload  # the state carries the UTC offset
    assert reg.get_ha_discovery_topic("homeassistant", "vitocal").startswith(
        "homeassistant/datetime/vitocal/"
    )


#
# configuration file
#

DATETIME_REGISTER = """
  - name: holiday_program_start
    sampling_period_seconds: 600
    register: 0x2309
    length: 8
    type: datetime_bcd
    writable: true
    ha_discovery:
      name: "Holiday Program Start"
      platform: datetime
  - name: device_clock
    sampling_period_seconds: 600
    register: 0x08E0
    length: 8
    type: datetime_bcd
    ha_discovery:
      name: "Device Clock"
      platform: sensor
      device_class: timestamp
  - name: plain
    sampling_period_seconds: 600
    register: 0x0101
    length: 2
    ha_discovery:
      name: "Plain"
      platform: sensor
"""


def load(tmp_path, registers=DATETIME_REGISTER, optolink_extra=""):
    text = (
        "config_version: 2\noptolink:\n  serial_port: /dev/null\n"
        + optolink_extra
        + "mqtt:\n  broker:\n    host: localhost\n"
        + "registers_poll_list:"
        + registers
    )
    config_file = tmp_path / "optolink2mqtt.yaml"
    config_file.write_text(text)
    config = Config()
    config.load(str(config_file), SCHEMA)
    return config.config


def test_config_defaults(tmp_path):
    cfg = load(tmp_path)
    assert cfg["optolink"]["timezone"] is None
    regs = cfg["registers_poll_list"]
    assert [r["type"] for r in regs] == ["datetime_bcd", "datetime_bcd", "int"]
    # a date/time sensor is not a measurement, a numeric one is
    assert "state_class" not in regs[1]["ha_discovery"]
    assert regs[2]["ha_discovery"]["state_class"] == "measurement"
    for r in regs:
        OptolinkVS2Register(r, "prefix", BERLIN)


def test_config_timezone(tmp_path):
    cfg = load(tmp_path, optolink_extra='  timezone: "Europe/Berlin"\n')
    assert cfg["optolink"]["timezone"] == "Europe/Berlin"


def test_config_invalid_timezone_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="optolink.timezone"):
        load(tmp_path, optolink_extra='  timezone: "Mars/Olympus"\n')


def test_config_invalid_type_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="does not conform to schema"):
        load(
            tmp_path,
            registers="""
  - name: x
    sampling_period_seconds: 10
    register: 0x0101
    length: 2
    type: string
""",
        )


#
# read-register mode
#


def test_read_register_report_shows_datetime_bcd_interpretation():
    reg = read_register.build_register(parse_args(["read-register", "0x08E0", "8"]))
    rx = OptolinkVS2RxData(ErrorCode.Success, 0x08E0, bytearray(REAL_HW_SAMPLE))

    report = read_register.format_register_details(reg, rx, 0.05)

    assert "DateTimeBCD:" in report
    assert "2026-11-27T11:53:53 (device local time)" in report
    assert "type: int" in report


def test_read_register_with_scale_factor_is_a_float():
    reg = read_register.build_register(
        parse_args(["read-register", "0x0800", "2", "signed", "0.1"])
    )
    assert reg.type == "float"


def test_utc_constant_sanity():
    # guards the tests above against a broken tzdata installation
    assert (
        datetime(2026, 12, 24, 9, 30, tzinfo=timezone.utc).astimezone(BERLIN).hour == 10
    )
