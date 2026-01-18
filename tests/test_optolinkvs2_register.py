#!/usr/bin/env python3
"""
Unit tests for OptolinkVS2Register class

Tests cover initialization, data conversion, MQTT topic generation,
and HomeAssistant discovery functionality.
"""

import sys
import os
import pytest
import json

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
            ("  Spaced  Out  ", "spaced__out"),
            ("UPPERCASE NAME", "uppercase_name"),
            ("Mixed Case_Name", "mixed_case_name"),
            ("Name-With-Dashes", "name-with-dashes"),
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



#
# core unit tests:
#

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

class TestOptolinkVS2RegisterHomeAssistant:
    """Tests for HomeAssistant discovery methods"""

    def test_check_ha_discovery_validity_sensor(self):
        """Test validation of valid sensor discovery configuration"""
        ha_discovery = {
            "name": "Living Room Temperature",
            "platform": "sensor",
            "device_class": "temperature",
            "unit_of_measurement": "°C",
            "state_class": "measurement",
            "icon": "mdi:thermometer",
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "payload_on": None,
            "payload_off": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        # Should not raise exception
        reg = OptolinkVS2Register(reg_data, "home/device")
        assert reg.ha_discovery is not None

    def test_check_ha_discovery_validity_switch_writable(self):
        """Test validation of valid switch discovery for writable register"""
        ha_discovery = {
            "name": "Heating Circuit Pump",
            "platform": "switch",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Pump",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": True,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")
        assert reg.writable is True

    def test_check_ha_discovery_invalid_missing_name(self):
        """Test validation fails when discovery name is missing"""
        ha_discovery = {
            "name": None,
            "platform": "sensor",
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "payload_on": None,
            "payload_off": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        
        with pytest.raises(Exception) as exc_info:
            OptolinkVS2Register(reg_data, "home/device")
        assert "invalid HA discovery 'name' property" in str(exc_info.value)

    def test_check_ha_discovery_invalid_missing_platform(self):
        """Test validation fails when discovery platform is missing"""
        ha_discovery = {
            "name": "Temperature",
            "platform": "",
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "payload_on": None,
            "payload_off": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        
        with pytest.raises(Exception) as exc_info:
            OptolinkVS2Register(reg_data, "home/device")
        assert "invalid HA discovery 'platform' property" in str(exc_info.value)

    def test_check_ha_discovery_invalid_writable_mismatch_read_only(self):
        """Test validation fails when read-only register has writable platform"""
        ha_discovery = {
            "name": "Status",
            "platform": "switch",  # switch requires writable
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Status",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": False,  # not writable!
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        
        with pytest.raises(Exception) as exc_info:
            OptolinkVS2Register(reg_data, "home/device")
        assert "incompatible HA discovery 'platform' property" in str(exc_info.value)

    def test_check_ha_discovery_invalid_writable_mismatch_writable(self):
        """Test validation fails when writable register has read-only platform"""
        ha_discovery = {
            "name": "Status",
            "platform": "sensor",  # sensor is read-only
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "payload_on": None,
            "payload_off": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Status",
            "sampling_period_seconds": 60,
            "register": 0x0000,
            "length": 1,
            "signed": False,
            "writable": True,  # writable!
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        
        with pytest.raises(Exception) as exc_info:
            OptolinkVS2Register(reg_data, "home/device")
        assert "incompatible HA discovery 'platform' property" in str(exc_info.value)

    def test_get_ha_unique_id(self):
        """Test HomeAssistant unique ID generation"""
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x00F8,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": None,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")
        
        unique_id = reg.get_ha_unique_id("MyHeater")
        assert unique_id == "MyHeater-temperature-f800"

    def test_get_ha_discovery_topic(self):
        """Test HomeAssistant discovery topic generation"""
        ha_discovery = {
            "name": "Room Temperature",
            "platform": "sensor",
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "payload_on": None,
            "payload_off": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x00F8,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")
        
        topic = reg.get_ha_discovery_topic("homeassistant", "MyHeater")
        assert "sensor" in topic
        assert "MyHeater" in topic
        assert "/config" in topic

    def test_get_ha_discovery_payload_sensor(self):
        """Test HomeAssistant discovery payload generation for sensor"""
        ha_discovery = {
            "name": "Room Temperature",
            "platform": "sensor",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
            "icon": "mdi:thermometer",
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "payload_on": None,
            "payload_off": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x00F8,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 0.1,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")
        
        device_dict = {
            "identifiers": ["MyHeater"],
            "name": "My Heater",
            "model": "Viessmann",
        }
        payload_str = reg.get_ha_discovery_payload(
            "MyHeater",
            "1.0.0",
            device_dict,
            3600
        )
        
        payload = json.loads(payload_str)
        assert payload["name"] == "Room Temperature"
        assert payload["unit_of_measurement"] == "°C"
        assert payload["device_class"] == "temperature"
        assert "command_topic" not in payload  # read-only

    def test_get_ha_discovery_payload_switch(self):
        """Test HomeAssistant discovery payload generation for switch"""
        ha_discovery = {
            "name": "Heating Pump",
            "platform": "switch",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Pump",
            "sampling_period_seconds": 60,
            "register": 0x0050,
            "length": 1,
            "signed": False,
            "writable": True,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")
        
        device_dict = {
            "identifiers": ["MyHeater"],
            "name": "My Heater",
        }
        payload_str = reg.get_ha_discovery_payload(
            "MyHeater",
            "1.0.0",
            device_dict,
            3600
        )
        
        payload = json.loads(payload_str)
        assert payload["command_topic"] == "home/device/pump/set"
        assert payload["payload_on"] == "ON"
        assert payload["payload_off"] == "OFF"

    def test_get_ha_discovery_payload_select_with_enum(self):
        """Test HomeAssistant discovery payload for select platform with enum"""
        enum_dict = {0: "OFF", 1: "HEATING", 2: "COOLING"}
        ha_discovery = {
            "name": "Heating Mode",
            "platform": "select",
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "payload_on": None,
            "payload_off": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
            "expire_after": None,
        }
        reg_data = {
            "name": "Mode",
            "sampling_period_seconds": 60,
            "register": 0x0020,
            "length": 1,
            "signed": False,
            "writable": True,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": enum_dict,
            "ha_discovery": ha_discovery,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")
        
        device_dict = {
            "identifiers": ["MyHeater"],
            "name": "My Heater",
        }
        payload_str = reg.get_ha_discovery_payload(
            "MyHeater",
            "1.0.0",
            device_dict,
            3600
        )
        
        payload = json.loads(payload_str)
        assert "options" in payload
        assert "OFF" in payload["options"]
        assert "HEATING" in payload["options"]
        assert "COOLING" in payload["options"]

    def test_get_ha_discovery_payload_with_expire_after(self):
        """Test HomeAssistant discovery payload includes expire_after"""
        ha_discovery = {
            "name": "Temperature",
            "platform": "sensor",
            "expire_after": 1800,
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "payload_on": None,
            "payload_off": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
        }
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x00F8,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")
        
        device_dict = {"identifiers": ["MyHeater"]}
        payload_str = reg.get_ha_discovery_payload(
            "MyHeater",
            "1.0.0",
            device_dict,
            3600
        )
        
        payload = json.loads(payload_str)
        assert payload["expire_after"] == 1800

    def test_get_ha_discovery_payload_with_default_expire_after(self):
        """Test HomeAssistant discovery payload uses default expire_after"""
        ha_discovery = {
            "name": "Temperature",
            "platform": "sensor",
            "expire_after": None,  # Not specified
            "device_class": None,
            "state_class": None,
            "unit_of_measurement": None,
            "icon": None,
            "payload_on": None,
            "payload_off": None,
            "availability_topic": None,
            "payload_available": None,
            "payload_not_available": None,
        }
        reg_data = {
            "name": "Temperature",
            "sampling_period_seconds": 60,
            "register": 0x00F8,
            "length": 2,
            "signed": False,
            "writable": False,
            "scale_factor": 1.0,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        }
        reg = OptolinkVS2Register(reg_data, "home/device")
        
        device_dict = {"identifiers": ["MyHeater"]}
        payload_str = reg.get_ha_discovery_payload(
            "MyHeater",
            "1.0.0",
            device_dict,
            7200  # default
        )
        
        payload = json.loads(payload_str)
        assert payload["expire_after"] == 7200


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
        assert reg.sanitized_name == "flow_(°c)_/_return-temp."
