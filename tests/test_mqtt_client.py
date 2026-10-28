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
    transport = Mock()
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client",
        Mock(return_value=transport),
    )
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

    client.on_connect(
        transport,
        client,
        Mock(),
        5,
        None,
    )

    assert "MQTT broker rejected connection" in caplog.text
    transport.publish.assert_not_called()
    transport.subscribe.assert_not_called()
    transport.reconnect_delay_set.assert_called_once_with(
        min_delay=5,
        max_delay=5,
    )

    client.on_disconnect(
        transport,
        client,
        Mock(is_disconnect_packet_from_server=False),
        paho.convert_disconnect_error_code_to_reason_code(
            paho.MQTTErrorCode.MQTT_ERR_CONN_REFUSED
        ),
        None,
    )

    assert "OOOOPS!" not in caplog.text
    assert MqttClient.num_disconnects == disconnect_count
    assert client.consume_disconnect_notification() is True
    assert client.consume_disconnect_notification() is False
    transport.publish.assert_not_called()
    transport.subscribe.assert_not_called()
    assert client._connection_rejected is False
