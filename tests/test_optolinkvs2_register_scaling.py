import logging
import os
import sys

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402


def make_register(**overrides):
    reg = {
        "name": "test",
        "sampling_period_seconds": 60,
        "register": 0x0800,
        "length": 2,
        "signed": False,
        "writable": True,
        "scale_factor": 1.0,
        "byte_filter": None,
        "enum": None,
        "ha_discovery": None,
    }
    reg.update(overrides)
    return OptolinkVS2Register(reg, "optolink2mqtt/test")


def raw(val: int, length: int = 2) -> bytearray:
    return bytearray(val.to_bytes(length, byteorder="little"))


@pytest.mark.parametrize(
    "scale_factor, rawval, expected",
    [
        (0.001, 1234, 1.234),
        (0.0001, 12345, 1.2345),
        (0.1, 235, 23.5),
        (0.5, 3, 1.5),
        (10.0, 7, 70),
    ],
)
def test_scaled_value_keeps_the_register_resolution(scale_factor, rawval, expected):
    reg = make_register(scale_factor=scale_factor)

    assert reg.get_value_from_rawdata(raw(rawval)) == expected


@pytest.mark.parametrize(
    "scale_factor, payload, expected_raw",
    [
        # nearest raw value, not truncated
        (0.1, "2.35", 24),  # 23.5 -> 24
        (0.1, "2.38", 24),  # 23.8 -> 24
        (10.0, "17", 2),  # 1.7 -> 2
        (10.0, "14", 1),  # 1.4 -> 1
        (0.5, "1.4", 3),  # 2.8 -> 3
        (0.001, "1.2345", 1234),
        (0.1, "0.3", 3),  # 2.9999999999999996 -> 3
    ],
)
def test_written_value_is_rounded_to_nearest_raw_value(
    scale_factor, payload, expected_raw
):
    reg = make_register(scale_factor=scale_factor)

    assert reg.get_rawdata_from_value(payload) == raw(expected_raw)


@pytest.mark.parametrize("scale_factor", [0.001, 0.1, 0.5, 10.0])
def test_read_back_of_written_value_matches(scale_factor):
    reg = make_register(scale_factor=scale_factor)
    for rawval in range(0, 2000, 7):
        value = reg.get_value_from_rawdata(raw(rawval))
        assert reg.get_rawdata_from_value(str(value)) == raw(rawval)


def test_unsigned_warning_uses_the_filtered_length(caplog):
    # 1 byte extracted from a 4-byte register: 250 is close to the max of 1 byte
    reg = make_register(length=4, byte_filter="b:1:1")

    with caplog.at_level(logging.WARNING):
        assert reg.get_value_from_rawdata(bytearray([0x00, 250, 0x00, 0x00])) == 250

    assert "suspiciously close to the max possible value 255" in caplog.text


def test_unsigned_warning_is_logged_only_once(caplog):
    reg = make_register(length=1)

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert reg.get_value_from_rawdata(bytearray([240])) == 240

    assert caplog.text.count("suspiciously close") == 1


def test_enum_register_applies_byte_filter():
    reg = make_register(length=4, byte_filter="b:2:2", enum={0: "Off", 1: "On"})

    assert reg.get_value_from_rawdata(bytearray([0x05, 0x07, 0x01, 0x09])) == "On"
