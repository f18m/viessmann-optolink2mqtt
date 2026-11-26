import os
import queue
import sys
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.mqtt_client import MqttClient  # noqa: E402
from optolink2mqtt.optolinkvs2_protocol import (  # noqa: E402
    ErrorCode,
    OptolinkVS2Protocol,
)


def test_protocol_stats_before_any_frame():
    protocol = OptolinkVS2Protocol(Mock())

    assert protocol.get_human_friendly_stats() == "no Optolink VS2 frames received yet"


def test_protocol_stats_after_frames():
    protocol = OptolinkVS2Protocol(Mock())
    protocol.get_stats()[ErrorCode.Success] = 3
    protocol.get_stats()[ErrorCode.CRCError] = 1

    assert protocol.get_human_friendly_stats().startswith("75.0% of 4 ")


def test_mqtt_stats_before_any_publish(monkeypatch):
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=Mock())
    )
    client = MqttClient(
        queue.Queue(), "test-client", False, "prefix/", "", 0, False, 5, ""
    )

    assert "0.0% of 0 successful MQTT published msgs" in (
        client.get_human_friendly_stats()
    )
