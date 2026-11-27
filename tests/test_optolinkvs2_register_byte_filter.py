import os
import sys

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402


def make_register(byte_filter, length=3):
    return OptolinkVS2Register(
        {
            "name": "test_register",
            "sampling_period_seconds": 60,
            "register": 0x01CD,
            "length": length,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": byte_filter,
            "enum": None,
            "type": "int",
            "ha_discovery": None,
        },
        "prefix/",
    )


def test_no_byte_filter_stays_none():
    reg = make_register(None)

    assert reg.byte_filter is None
    assert reg.get_value_from_rawdata(bytearray([0x01, 0x02, 0x03])) == 0x030201


def test_valid_byte_filter_is_applied():
    reg = make_register("b:0:1")

    assert reg.get_value_from_rawdata(bytearray([0x01, 0x02, 0x03])) == 0x0201


@pytest.mark.parametrize(
    "byte_filter",
    [
        "garbage",
        "x:0:1",
        "b:0",
        "b:0:1:2",
        "b:a:1",
        "b:1:0",  # start > end
        "b:0:3",  # end beyond register length
        "b:-1:1",
    ],
)
def test_invalid_byte_filter_is_rejected(byte_filter):
    with pytest.raises(ValueError, match="byte_filter"):
        make_register(byte_filter)
