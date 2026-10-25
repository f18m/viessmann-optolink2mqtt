import os
import queue
import sys
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)


def test_rejected_connection_does_not_publish_or_subscribe(caplog):
    from optolink2mqtt.mqtt_client import MqttClient

    client = MqttClient(
        queue.Queue(),
        "test-client",
        False,
        "optolink2mqtt/test/",
        "optolink2mqtt/request/",
        0,
        False,
        5,
        "homeassistant/status",
    )
    client._mqttc = Mock()

    client.on_connect(
        client._mqttc,
        client,
        Mock(),
        5,
        None,
    )

    assert "MQTT broker rejected connection" in caplog.text
    client._mqttc.publish.assert_not_called()
    client._mqttc.subscribe.assert_not_called()
