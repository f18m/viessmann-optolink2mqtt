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


class TestOptolinkVS2RegisterHomeAssistant:
    """Tests for HomeAssistant discovery methods"""

    def test_check_ha_discovery_validity_sensor(self):
        """Test validation of valid sensor discovery configuration"""
        ha_discovery = {
            "name": "Living Room Temperature",
            "platform": "sensor",
            "unit_of_measurement": "°C",
            "state_class": "measurement",
            "icon": "mdi:thermometer",
            "device_class": None,
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
            "MyHeater", "1.0.0", device_dict, 3600
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
            "MyHeater", "1.0.0", device_dict, 3600
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
            "MyHeater", "1.0.0", device_dict, 3600
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
            "MyHeater", "1.0.0", device_dict, 3600
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
            "MyHeater", "1.0.0", device_dict, 7200  # default
        )

        payload = json.loads(payload_str)
        assert payload["expire_after"] == 7200
