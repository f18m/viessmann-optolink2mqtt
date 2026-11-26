import os
import queue
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.mqtt_client import MqttClient  # noqa: E402

HA_STATUS_TOPIC = "homeassistant/status"
COMMAND_TOPIC = "optolink2mqtt/test/dhw_temperature_set/set"


def make_client(monkeypatch, request_topic, ha_status_topic=HA_STATUS_TOPIC):
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=Mock())
    )
    message_queue = queue.Queue()
    client = MqttClient(
        message_queue,
        "test-client",
        False,
        "optolink2mqtt/test/",
        request_topic,
        0,
        False,
        5,
        ha_status_topic,
    )
    return client, message_queue


@pytest.mark.parametrize("request_topic", ["", "optolink2mqtt/request/"])
def test_command_messages_are_queued(monkeypatch, request_topic):
    client, message_queue = make_client(monkeypatch, request_topic)
    msg = Mock(topic=COMMAND_TOPIC, payload=b"45")

    client.on_message(None, None, msg)

    assert message_queue.get_nowait() is msg


@pytest.mark.parametrize("request_topic", ["", "optolink2mqtt/request/"])
def test_ha_status_online_requests_discovery(monkeypatch, request_topic):
    client, message_queue = make_client(monkeypatch, request_topic)

    client.on_message(None, None, Mock(topic=HA_STATUS_TOPIC, payload=b"online"))

    assert client.get_and_reset_ha_discovery_messages_requested_flag() is True
    assert message_queue.empty()


def test_request_topic_messages_are_not_queued(monkeypatch):
    client, message_queue = make_client(monkeypatch, "optolink2mqtt/request/")

    client.on_message(None, None, Mock(topic="optolink2mqtt/request/foo", payload=b"x"))

    assert message_queue.empty()


def test_disabled_ha_status_topic_does_not_swallow_messages(monkeypatch):
    client, message_queue = make_client(monkeypatch, "", ha_status_topic="")
    msg = Mock(topic=COMMAND_TOPIC, payload=b"45")

    client.on_message(None, None, msg)

    assert message_queue.get_nowait() is msg
