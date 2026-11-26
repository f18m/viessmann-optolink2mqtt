"""
MqttClient.on_message() runs in the paho network thread: it must not block when
the queue of pending messages is full, or the client stops servicing the
connection (keepalives, acks) until the main thread drains the queue.
"""

import os
import queue
import sys
import threading
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.mqtt_client import MqttClient  # noqa: E402

COMMAND_TOPIC = "optolink2mqtt/test/dhw_temperature_set/set"


def make_client(monkeypatch, maxsize):
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=Mock())
    )
    monkeypatch.setattr(MqttClient, "num_dropped_messages", 0)
    message_queue = queue.Queue(maxsize)
    client = MqttClient(
        message_queue, "test", False, "optolink2mqtt/test/", "", 0, False, 5, ""
    )
    return client, message_queue


def test_on_message_does_not_block_when_queue_is_full(monkeypatch):
    client, message_queue = make_client(monkeypatch, maxsize=1)
    first = Mock(topic=COMMAND_TOPIC, payload=b"40")
    second = Mock(topic=COMMAND_TOPIC, payload=b"41")
    client.on_message(None, None, first)

    # run in a separate thread, so that a regression makes the test fail instead of hanging
    t = threading.Thread(target=client.on_message, args=(None, None, second))
    t.daemon = True
    t.start()
    t.join(timeout=2)

    assert not t.is_alive(), "on_message() blocked on a full queue"
    assert message_queue.get_nowait() is first
    assert message_queue.empty()
    assert MqttClient.num_dropped_messages == 1
    assert "1 MQTT messages dropped" in client.get_human_friendly_stats()


def test_on_message_queues_when_there_is_room(monkeypatch):
    client, message_queue = make_client(monkeypatch, maxsize=2)
    msgs = [Mock(topic=COMMAND_TOPIC, payload=b"40") for _ in range(2)]

    for m in msgs:
        client.on_message(None, None, m)

    assert [message_queue.get_nowait() for _ in msgs] == msgs
    assert MqttClient.num_dropped_messages == 0
