import os
import queue
import sys
import threading
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.mqtt_client import MqttClient  # noqa: E402

HA_STATUS_TOPIC = "homeassistant/status"


def make_client(monkeypatch):
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=Mock())
    )
    return MqttClient(
        queue.Queue(),
        "test",
        False,
        "optolink2mqtt/test/",
        "",
        0,
        False,
        5,
        HA_STATUS_TOPIC,
    )


def test_counters_are_not_shared_between_instances(monkeypatch):
    first = make_client(monkeypatch)
    second = make_client(monkeypatch)

    first.publish("optolink2mqtt/test/a", "1")
    first.on_publish(None, None, 1, 0, None)
    first.on_message(None, None, Mock(topic="optolink2mqtt/test/a/set", payload=b"1"))

    assert first.num_published_total == 1
    assert first.num_published_successful == 1
    assert first.num_received_messages == 1
    assert second.num_published_total == 0
    assert second.num_published_successful == 0
    assert second.num_received_messages == 0
    assert not hasattr(MqttClient, "num_published_total")


def test_ha_online_notification_waits_while_flag_is_being_consumed(monkeypatch):
    client = make_client(monkeypatch)

    # simulate the main thread being in the middle of
    # get_and_reset_ha_discovery_messages_requested_flag(): the paho thread delivering
    # an "online" notification must wait, instead of setting a flag that is about to
    # be reset (which would lose the notification)
    with client._ha_discovery_lock:
        t = threading.Thread(
            target=client.on_message,
            args=(None, None, Mock(topic=HA_STATUS_TOPIC, payload=b"online")),
        )
        t.daemon = True
        t.start()
        t.join(timeout=0.2)
        assert t.is_alive(), "the HA flag was updated without holding the lock"

    t.join(timeout=2)
    assert not t.is_alive()
    assert client.get_and_reset_ha_discovery_messages_requested_flag() is True
    assert client.get_and_reset_ha_discovery_messages_requested_flag() is False
