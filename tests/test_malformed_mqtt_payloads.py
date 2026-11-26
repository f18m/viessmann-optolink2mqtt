"""
Malformed MQTT payloads (non-UTF-8 bytes, non-numeric or out-of-range values)
must be rejected without raising, since an exception would either stop the paho
network thread or terminate the main loop of the daemon.
"""

import os
import queue
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.mqtt_client import MqttClient  # noqa: E402
from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402

HA_STATUS_TOPIC = "homeassistant/status"
INVALID_UTF8 = b"\xff\xfe\x80"


def make_register(length=1, signed=False, scale_factor=1.0, enum=None):
    return OptolinkVS2Register(
        {
            "name": "Test Register",
            "sampling_period_seconds": 60,
            "register": 0x6300,
            "length": length,
            "signed": signed,
            "writable": True,
            "scale_factor": scale_factor,
            "byte_filter": None,
            "enum": enum,
            "ha_discovery": None,
        },
        "optolink2mqtt/test",
    )


@pytest.mark.parametrize(
    "payload", ["", "abc", "nan", "inf", "-inf", "1e400", "10.5", "0x10"]
)
def test_non_numeric_payload_is_rejected_on_integer_register(payload):
    assert make_register().get_rawdata_from_value(payload) is None


@pytest.mark.parametrize("payload", ["", "abc", "nan", "inf", "-inf", "1e400"])
def test_non_numeric_payload_is_rejected_on_scaled_register(payload):
    reg = make_register(length=2, signed=True, scale_factor=0.1)
    assert reg.get_rawdata_from_value(payload) is None


@pytest.mark.parametrize(
    "length,signed,payload",
    [
        (1, False, "256"),
        (1, False, "-1"),
        (1, True, "128"),
        (1, True, "-129"),
        (2, False, "65536"),
        (2, False, "99999999999999999999999"),
    ],
)
def test_out_of_range_payload_is_rejected(length, signed, payload):
    reg = make_register(length=length, signed=signed)
    assert reg.get_rawdata_from_value(payload) is None


def test_out_of_range_payload_is_rejected_on_scaled_register():
    # 30.0 / 0.1 = 300, which does not fit in 1 unsigned byte
    reg = make_register(length=1, scale_factor=0.1)
    assert reg.get_rawdata_from_value("30.0") is None


def test_valid_payload_is_still_converted():
    assert make_register().get_rawdata_from_value("255") == bytearray([0xFF])
    reg = make_register(length=2, signed=True, scale_factor=0.1)
    assert reg.get_rawdata_from_value("-1.5") == bytearray([0xF1, 0xFF])


def make_mqtt_client(monkeypatch):
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=Mock())
    )
    message_queue = queue.Queue()
    client = MqttClient(
        message_queue,
        "test-client",
        False,
        "optolink2mqtt/test/",
        "",
        0,
        False,
        5,
        HA_STATUS_TOPIC,
    )
    return client, message_queue


def test_on_message_does_not_raise_on_invalid_utf8(monkeypatch):
    client, message_queue = make_mqtt_client(monkeypatch)
    msg = Mock(topic="optolink2mqtt/test/test_register/set", payload=INVALID_UTF8)

    client.on_message(None, None, msg)

    assert message_queue.get_nowait() is msg


def test_on_message_ignores_invalid_utf8_ha_status(monkeypatch):
    client, message_queue = make_mqtt_client(monkeypatch)

    client.on_message(None, None, Mock(topic=HA_STATUS_TOPIC, payload=INVALID_UTF8))

    assert client.get_and_reset_ha_discovery_messages_requested_flag() is False
    assert message_queue.empty()


def make_app():
    reg = make_register()
    app = Optolink2MqttApp()
    app.register_list_by_cmd_topic = {reg.get_mqtt_command_topic(): reg}
    app.optolink_interface = Mock()
    app.scheduler = Mock()
    app.enhanced_mqtt_client = Mock()
    return app, reg


@pytest.mark.parametrize("payload", [INVALID_UTF8, b"abc", b"nan", b"256"])
def test_app_does_not_write_or_raise_on_malformed_payload(payload):
    app, reg = make_app()

    app._process_received_mqtt_message(
        Mock(topic=reg.get_mqtt_command_topic(), payload=payload)
    )

    app.optolink_interface.write_register.assert_not_called()


def test_app_writes_valid_payload():
    app, reg = make_app()

    app._process_received_mqtt_message(
        Mock(topic=reg.get_mqtt_command_topic(), payload=b"42")
    )

    app.optolink_interface.write_register.assert_called_once_with(reg, bytearray([42]))
