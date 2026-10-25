import os
import queue
import sys
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)


def test_rejected_connection_does_not_publish_or_subscribe(caplog, monkeypatch):
    import paho.mqtt.client as paho

    from optolink2mqtt.mqtt_client import MqttClient

    disconnect_count = MqttClient.num_disconnects
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

    retry_sleep = Mock()
    monkeypatch.setattr("optolink2mqtt.mqtt_client.time.sleep", retry_sleep)
    client.on_disconnect(
        client._mqttc,
        client,
        Mock(is_disconnect_packet_from_server=False),
        paho.convert_disconnect_error_code_to_reason_code(
            paho.MQTTErrorCode.MQTT_ERR_CONN_REFUSED
        ),
        None,
    )

    assert "OOOOPS!" not in caplog.text
    assert MqttClient.num_disconnects == disconnect_count
    retry_sleep.assert_called_once_with(client.reconnect_period_sec)
    client._mqttc.publish.assert_not_called()
    client._mqttc.subscribe.assert_not_called()
    assert client._connection_rejected is False
