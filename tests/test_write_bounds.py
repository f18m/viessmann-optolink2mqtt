"""
Writes received over MQTT must respect the 'min'/'max' limits configured in the
HomeAssistant discovery metadata of the register: any MQTT client can publish on
the command topic, not only HomeAssistant, which enforces them in its UI.
"""

import os
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402


def make_register(min_val=20, max_val=60, scale_factor=0.1, signed=False):
    ha_discovery = {"name": "DHW Set Temperature", "platform": "number"}
    if min_val is not None:
        ha_discovery["min"] = min_val
    if max_val is not None:
        ha_discovery["max"] = max_val
    return OptolinkVS2Register(
        {
            "name": "dhw_temperature_set",
            "sampling_period_seconds": 60,
            "register": 0x6300,
            "length": 2,
            "signed": signed,
            "writable": True,
            "scale_factor": scale_factor,
            "byte_filter": None,
            "enum": None,
            "ha_discovery": ha_discovery,
        },
        "optolink2mqtt/test",
    )


def bounds_ok(reg, payload):
    return reg.is_within_write_bounds(reg.get_rawdata_from_value(payload))


@pytest.mark.parametrize("payload", ["20", "20.0", "45.5", "60"])
def test_values_within_bounds_are_accepted(payload):
    assert bounds_ok(make_register(), payload)


@pytest.mark.parametrize("payload", ["19.9", "0", "60.1", "100", "6553.5"])
def test_values_outside_bounds_are_rejected(payload):
    assert not bounds_ok(make_register(), payload)


def test_negative_value_below_min_is_rejected():
    reg = make_register(min_val=-10, max_val=10, signed=True)
    assert bounds_ok(reg, "-10")
    assert not bounds_ok(reg, "-10.1")


def test_only_min_configured():
    reg = make_register(max_val=None)
    assert not bounds_ok(reg, "19")
    assert bounds_ok(reg, "6000")


def test_only_max_configured():
    reg = make_register(min_val=None)
    assert bounds_ok(reg, "0")
    assert not bounds_ok(reg, "61")


def test_no_bounds_configured():
    reg = make_register(min_val=None, max_val=None)
    assert bounds_ok(reg, "0")
    assert bounds_ok(reg, "6553.5")


def test_min_zero_is_enforced():
    reg = make_register(min_val=0, max_val=10, signed=True)
    assert not bounds_ok(reg, "-0.1")


def make_app(reg):
    app = Optolink2MqttApp()
    app.register_list_by_cmd_topic = {reg.get_mqtt_command_topic(): reg}
    app.optolink_interface = Mock()
    app.scheduler = Mock()
    app.enhanced_mqtt_client = Mock()
    return app


def test_app_does_not_write_out_of_bounds_value():
    reg = make_register()
    app = make_app(reg)

    app._process_received_mqtt_message(
        Mock(topic=reg.get_mqtt_command_topic(), payload=b"95")
    )

    app.optolink_interface.write_register.assert_not_called()
    # the register is read back anyway, so MQTT clients see the unchanged value
    app.scheduler.enter.assert_called_once()


def test_app_writes_in_bounds_value():
    reg = make_register()
    app = make_app(reg)

    app._process_received_mqtt_message(
        Mock(topic=reg.get_mqtt_command_topic(), payload=b"45")
    )

    app.optolink_interface.write_register.assert_called_once_with(
        reg, bytearray((450).to_bytes(2, "little"))
    )
