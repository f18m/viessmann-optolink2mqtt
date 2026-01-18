#!/usr/bin/env python3
"""
Unit tests for OptolinkVS2Register class

Tests cover initialization, data conversion, MQTT topic generation,
and HomeAssistant discovery functionality.
"""

import sys
import os
import pytest

# load code living in the parent dir ../src/optolink2mqtt
THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402


class TestOptolinkVS2RegisterValueConversion:
    """Tests for value conversion methods (get_value_from_rawdata, get_rawdata_from_value)"""

    def test_get_value_unsigned_no_scale(self):
        """Test reading unsigned integer without scaling"""
        reg_data = {
            "name": "Counter",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        # Test little-endian conversion
        rawdata = bytearray([0x34, 0x12])  # 0x1234 in little-endian
        value = reg.get_value_from_rawdata(rawdata)
        assert value == 0x1234

    def test_get_value_signed_no_scale(self):
        """Test reading signed integer without scaling"""
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": True,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        # Test negative value
        rawdata = bytearray([0xFF, 0xFF])  # -1 in two's complement
        value = reg.get_value_from_rawdata(rawdata)
        assert value == -1

    def test_get_value_with_scale_factor(self):
        """Test reading value with scale factor"""
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 0.1,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        # 100 * 0.1 = 10.0
        rawdata = bytearray([0x64, 0x00])  # 100 in little-endian
        value = reg.get_value_from_rawdata(rawdata)
        assert value == 10.0

    def test_get_value_with_byte_filter(self):
        """Test reading value with byte filter applied"""
        reg_data = {
            "name": "Filtered",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 4,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": "b:1:2",  # Use bytes 1-2 (inclusive)
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        # Input: [0xAA, 0xBB, 0xCC, 0xDD]
        # After filter "b:1:2": [0xBB, 0xCC]
        # Result: 0xCCBB
        rawdata = bytearray([0xAA, 0xBB, 0xCC, 0xDD])
        value = reg.get_value_from_rawdata(rawdata)
        assert value == 0xCCBB

    def test_get_value_with_enum(self):
        """Test reading enumerated value"""
        enum_dict = {0: "OFF", 1: "ON", 2: "STANDBY"}
        reg_data = {
            "name": "Status",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": enum_dict,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        assert reg.get_value_from_rawdata(bytearray([0x00])) == "OFF"
        assert reg.get_value_from_rawdata(bytearray([0x01])) == "ON"
        assert reg.get_value_from_rawdata(bytearray([0x02])) == "STANDBY"

    def test_get_value_with_enum_unknown_value(self):
        """Test reading unknown enumerated value"""
        enum_dict = {0: "OFF", 1: "ON"}
        reg_data = {
            "name": "Status",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": enum_dict,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        value = reg.get_value_from_rawdata(bytearray([0xFF]))
        assert value == "Unknown (255)"

    def test_get_rawdata_from_value_unsigned(self):
        """Test converting unsigned value to raw data"""
        reg_data = {
            "name": "Counter",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": False,
            "writable": True,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        rawdata = reg.get_rawdata_from_value("4660")  # 0x1234
        assert rawdata == bytearray([0x34, 0x12])

    def test_get_rawdata_from_value_signed(self):
        """Test converting signed value to raw data"""
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": True,
            "writable": True,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        rawdata = reg.get_rawdata_from_value("-1")
        assert rawdata == bytearray([0xFF, 0xFF])

    def test_get_rawdata_from_value_with_scale_factor(self):
        """Test converting value with scale factor to raw data"""
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": False,
            "writable": True,
            "scale_factor": 0.1,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        # Input 10.0 / 0.1 = 100
        rawdata = reg.get_rawdata_from_value("10.0")
        assert rawdata == bytearray([0x64, 0x00])

    def test_get_rawdata_from_value_with_enum(self):
        """Test converting enum value to raw data"""
        enum_dict = {0: "OFF", 1: "ON", 2: "STANDBY"}
        reg_data = {
            "name": "Status",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": True,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": enum_dict,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        assert reg.get_rawdata_from_value("OFF") == bytearray([0x00])
        assert reg.get_rawdata_from_value("ON") == bytearray([0x01])
        assert reg.get_rawdata_from_value("STANDBY") == bytearray([0x02])

    def test_get_rawdata_from_value_invalid_enum(self):
        """Test error handling for invalid enum value"""
        enum_dict = {0: "OFF", 1: "ON"}
        reg_data = {
            "name": "Status",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": True,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": enum_dict,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        with pytest.raises(ValueError) as exc_info:
            reg.get_rawdata_from_value("INVALID")
        assert "Invalid value" in str(exc_info.value)
        assert "INVALID" in str(exc_info.value)

    def test_get_rawdata_overflow_error(self):
        """Test error handling when value overflows the register length"""
        reg_data = {
            "name": "Byte",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": True,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        # 256 cannot fit in 1 byte - will raise OverflowError from int.to_bytes()
        with pytest.raises((ValueError, OverflowError)):
            reg.get_rawdata_from_value("256")
