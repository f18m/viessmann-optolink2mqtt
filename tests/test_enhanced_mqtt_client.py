import json
import os
import queue
import sys
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.enhanced_mqtt_client import EnhancedMqttClient  # noqa: E402


def create_client(monkeypatch, ha_discovery_config, registers):
    paho_client = Mock()
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=paho_client)
    )
    client = EnhancedMqttClient(
        queue.Queue(),
        "test-client",
        False,
        "optolink2mqtt/",
        "request",
        0,
        False,
        5,
        ha_discovery_config,
        registers,
        "1.2.3",
    )
    client._mqtt_client._connection_id = 1
    paho_client.is_connected.return_value = True
    return client, paho_client


def test_ha_status_topic_is_subscribed_only_when_discovery_enabled(monkeypatch):
    enabled_client, enabled_transport = create_client(
        monkeypatch,
        {"enabled": True, "topic": "homeassistant", "device_name": "device"},
        [],
    )
    assert enabled_client._mqtt_client.ha_status_topic == "homeassistant/status"
    enabled_client._mqtt_client.on_connect(
        enabled_transport, enabled_client._mqtt_client, Mock(), 0, None
    )
    assert enabled_transport.subscribe.call_args_list[1].args[0] == (
        "homeassistant/status"
    )

    disabled_client, disabled_transport = create_client(
        monkeypatch,
        {"enabled": False, "topic": "homeassistant", "device_name": "device"},
        [],
    )
    assert disabled_client._mqtt_client.ha_status_topic == ""
    disabled_client._mqtt_client.on_connect(
        disabled_transport,
        disabled_client._mqtt_client,
        Mock(),
        0,
        None,
    )
    disabled_transport.subscribe.assert_called_once_with(
        "request/#", disabled_client._mqtt_client.qos
    )


def test_discovery_messages_are_published_after_broker_connection(monkeypatch):
    register = Mock()
    register.sampling_period_sec = 20
    register.get_ha_discovery_payload.return_value = '{"name": "Temperature"}'
    register.get_ha_discovery_topic.return_value = (
        "homeassistant/sensor/device/temp/config"
    )
    discovery_client, paho_client = create_client(
        monkeypatch,
        {"enabled": True, "topic": "homeassistant", "device_name": "device"},
        [register],
    )

    assert discovery_client.check_if_time_to_send_discovery_messages() is True
    register.get_ha_discovery_payload.assert_called_once()
    assert register.get_ha_discovery_payload.call_args.args[1] == "1.2.3"
    assert register.get_ha_discovery_payload.call_args.args[3] == 30
    assert paho_client.publish.call_count == 2

    connection_status_topic, connection_status_payload = (
        paho_client.publish.call_args_list[1].args[:2]
    )
    assert connection_status_topic == (
        "homeassistant/binary_sensor/device/" "device-optolink-connection-status/config"
    )
    assert json.loads(connection_status_payload)["name"] == "Opto Connection Status"

    assert discovery_client.check_if_time_to_send_discovery_messages() is False
    assert paho_client.publish.call_count == 2


def test_ha_restart_requests_discovery_and_register_refresh(monkeypatch):
    discovery_client, paho_client = create_client(
        monkeypatch,
        {"enabled": True, "topic": "homeassistant", "device_name": "device"},
        [],
    )

    assert discovery_client.check_if_time_to_send_discovery_messages() is True
    discovery_client._mqtt_client._ha_discovery_messages_requested = True
    assert discovery_client.check_if_time_to_send_discovery_messages() is True
    assert paho_client.publish.call_count == 2


def test_optolink_connection_status_is_published_only_when_needed(monkeypatch):
    client, paho_client = create_client(
        monkeypatch,
        {"enabled": False, "topic": "homeassistant", "device_name": "device"},
        [],
    )

    client.publish_optolink_connection_status(True)
    client.publish_optolink_connection_status(True)
    client.publish_optolink_connection_status(False)

    assert paho_client.publish.call_count == 2
    assert paho_client.publish.call_args_list[0].args[:2] == (
        "optolink2mqtt/optolink2mqtt_status/optolink",
        "connected",
    )
    assert paho_client.publish.call_args_list[1].args[:2] == (
        "optolink2mqtt/optolink2mqtt_status/optolink",
        "disconnected",
    )
