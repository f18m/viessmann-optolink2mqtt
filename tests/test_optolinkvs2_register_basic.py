#!/usr/bin/env python3
"""
Unit tests for OptolinkVS2Register class

Tests cover initialization, data conversion, MQTT topic generation,
and HomeAssistant discovery functionality.
"""

import sys
import os

# load code living in the parent dir ../src/optolink2mqtt
THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402

#
# trivial unit tests written by AI:
#


class TestOptolinkVS2RegisterInit:
    """Tests for OptolinkVS2Register initialization"""

    def test_basic_initialization(self):
        """Test basic register initialization with minimal parameters"""
        reg_data = {
            "name": "Test Register",
            "sampling_period_seconds": 60,
            "register": 0x1234,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        assert reg.name == "Test Register"
        assert reg.sanitized_name == "test_register"
        assert reg.sampling_period_sec == 60
        assert reg.address == 0x1234
        assert reg.length == 2
        assert reg.signed is False
        assert reg.writable is False
        assert reg.scale_factor == 1.0

    def test_sanitized_name_generation(self):
        """Test that register names are properly sanitized"""
        test_cases = [
            ("Test Register", "test_register"),
            ("  Spaced  Out  ", "spaced_out"),
            ("UPPERCASE NAME", "uppercase_name"),
            ("Mixed Case_Name", "mixed_case_name"),
            ("Name-With-Dashes", "name_with_dashes"),
        ]

        for original, expected in test_cases:
            reg_data = {
                "name": original,
                "sampling_period_seconds": 60,
                "register": 0x0000,
                "length": 1,
                "signed": False,
                "writable": False,
                "scale_factor": 1.0,
                "byte_filter": None,
                "enum": None,
                "ha_discovery": None,
            }
            reg = OptolinkVS2Register(reg_data, "home/device")
            assert reg.sanitized_name == expected

    def test_mqtt_base_topic_slash_handling(self):
        """Test that trailing slashes are removed from MQTT base topic"""
        reg_data = {
            "name": "Test",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }

        # Test with trailing slash
        reg1 = OptolinkVS2Register(reg_data, "home/device/")
        assert reg1.mqtt_base_topic == "home/device"

        # Test without trailing slash
        reg2 = OptolinkVS2Register(reg_data, "home/device")
        assert reg2.mqtt_base_topic == "home/device"

    def test_type_conversions(self):
        """Test that register attributes are properly type-converted"""
        reg_data = {
            "name": "Typed Register",
            "sampling_period_seconds": 30,
            "register": 0x5678,  # int
            "length": "4",  # string instead of int
            "signed": 1,  # truthy value
            "writable": 0,  # falsy value
            "scale_factor": "2.5",  # string instead of float
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        assert isinstance(reg.address, int)
        assert reg.address == 0x5678
        assert isinstance(reg.length, int)
        assert reg.length == 4
        assert isinstance(reg.signed, bool)
        assert reg.signed is True
        assert isinstance(reg.writable, bool)
        assert reg.writable is False
        assert isinstance(reg.scale_factor, float)
        assert reg.scale_factor == 2.5


class TestOptolinkVS2RegisterMQTT:
    """Tests for MQTT topic generation methods"""

    def test_get_mqtt_state_topic(self):
        """Test MQTT state topic generation"""
        reg_data = {
            "name": "Living Room Temperature",
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
        reg = OptolinkVS2Register(reg_data, "home/heater")

        topic = reg.get_mqtt_state_topic()
        assert topic == "home/heater/living_room_temperature"

    def test_get_mqtt_command_topic(self):
        """Test MQTT command topic generation"""
        reg_data = {
            "name": "Heating Mode",
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
        reg = OptolinkVS2Register(reg_data, "home/heater")

        topic = reg.get_mqtt_command_topic()
        assert topic == "home/heater/heating_mode/set"

    def test_mqtt_topics_with_trailing_slash(self):
        """Test MQTT topics with trailing slash in base topic"""
        reg_data = {
            "name": "Test Parameter",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device/")

        assert reg.get_mqtt_state_topic() == "home/device/test_parameter"


class TestOptolinkVS2RegisterEdgeCases:
    """Tests for edge cases and special scenarios"""

    def test_single_byte_register(self):
        """Test handling of single-byte register"""
        reg_data = {
            "name": "Byte Value",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        assert reg.get_value_from_rawdata(bytearray([0xFF])) == 255
        assert reg.get_rawdata_from_value("255") == bytearray([0xFF])

    def test_multi_byte_register(self):
        """Test handling of multi-byte register (8 bytes)"""
        reg_data = {
            "name": "Large Value",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 8,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        rawdata = bytearray([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
        value = reg.get_value_from_rawdata(rawdata)
        assert value == 0x0807060504030201

    def test_zero_scale_factor(self):
        """Test handling of zero value reading"""
        reg_data = {
            "name": "Zero Value",
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

        assert reg.get_value_from_rawdata(bytearray([0x00, 0x00])) == 0

    def test_large_scale_factor(self):
        """Test handling of large scale factor"""
        reg_data = {
            "name": "Large Scale",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 100.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")

        # 5 * 100.0 = 500.0
        rawdata = bytearray([0x05, 0x00])
        value = reg.get_value_from_rawdata(rawdata)
        assert value == 500.0

    def test_special_characters_in_name(self):
        """Test handling of special characters in register name"""
        reg_data = {
            "name": "Flow (°C) / Return-Temp.",
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

        # Special characters should be preserved or handled correctly
        assert reg.sanitized_name == "flow_c__return_temp"
