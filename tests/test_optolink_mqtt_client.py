import json
import os
import sys
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.mqtt_client import MqttClient  # noqa: E402
from optolink2mqtt.optolink_mqtt_client import OptolinkMqttClient  # noqa: E402


def test_get_ha_status_topic():
    assert (
        OptolinkMqttClient.get_ha_status_topic(
            {"enabled": True, "topic": "homeassistant"}
        )
        == "homeassistant/status"
    )
    assert (
        OptolinkMqttClient.get_ha_status_topic(
            {"enabled": False, "topic": "homeassistant"}
        )
        == ""
    )


def test_discovery_messages_are_published_after_broker_connection():
    mqtt_client = Mock(spec=MqttClient)
    mqtt_client.get_connection_id.return_value = 1
    mqtt_client.get_and_reset_ha_discovery_messages_requested_flag.return_value = False
    mqtt_client.get_optolink_connection_status_topic.return_value = (
        "optolink2mqtt_status/optolink"
    )
    mqtt_client.get_optolink2mqtt_status_topic.return_value = "optolink2mqtt_status"

    register = Mock()
    register.sampling_period_sec = 20
    register.get_ha_discovery_payload.return_value = '{"name": "Temperature"}'
    register.get_ha_discovery_topic.return_value = (
        "homeassistant/sensor/device/temp/config"
    )

    discovery_client = OptolinkMqttClient(
        mqtt_client,
        {"enabled": True, "topic": "homeassistant", "device_name": "device"},
        [register],
        "1.2.3",
    )

    assert discovery_client.check_if_time_to_send_discovery_messages() is True
    register.get_ha_discovery_payload.assert_called_once()
    assert register.get_ha_discovery_payload.call_args.args[1] == "1.2.3"
    assert register.get_ha_discovery_payload.call_args.args[3] == 30
    assert mqtt_client.publish.call_count == 2

    connection_status_topic, connection_status_payload = (
        mqtt_client.publish.call_args_list[1].args
    )
    assert connection_status_topic == (
        "homeassistant/binary_sensor/device/" "device-optolink-connection-status/config"
    )
    assert json.loads(connection_status_payload)["name"] == "Opto Connection Status"

    assert discovery_client.check_if_time_to_send_discovery_messages() is False
    assert mqtt_client.publish.call_count == 2


def test_ha_restart_requests_discovery_and_register_refresh():
    mqtt_client = Mock(spec=MqttClient)
    mqtt_client.get_connection_id.side_effect = [1, 1]
    mqtt_client.get_and_reset_ha_discovery_messages_requested_flag.side_effect = [
        False,
        True,
    ]
    mqtt_client.get_optolink_connection_status_topic.return_value = (
        "optolink2mqtt_status/optolink"
    )
    mqtt_client.get_optolink2mqtt_status_topic.return_value = "optolink2mqtt_status"

    discovery_client = OptolinkMqttClient(
        mqtt_client,
        {"enabled": True, "topic": "homeassistant", "device_name": "device"},
        [],
        "1.2.3",
    )

    assert discovery_client.check_if_time_to_send_discovery_messages() is True
    assert discovery_client.check_if_time_to_send_discovery_messages() is True
    assert mqtt_client.publish.call_count == 2
