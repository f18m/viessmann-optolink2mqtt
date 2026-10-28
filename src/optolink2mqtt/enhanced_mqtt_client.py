"""
enhanced_mqtt_client.py
----------------
MQTT client with HomeAssistant discovery support for optolink2mqtt
Copyright (C) 2026 Francesco Montorsi

Licensed under the GNU GENERAL PUBLIC LICENSE, Version 3 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.gnu.org/licenses/gpl-3.0.html

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

import json
import logging
import platform
import queue
from collections.abc import Iterable
from typing import Any

from .mqtt_client import MqttClient
from .optolinkvs2_register import OptolinkVS2Register

logger = logging.getLogger(__name__)


class EnhancedMqttClient:
    """Wraps MQTT transport and HomeAssistant discovery behavior."""

    NUM_MQTT_DISCONNECTS_TOPIC = "num_mqtt_disconnects"
    NUM_OPTOLINK_ERRORS_TOPIC = "num_optolink_errors"

    def __init__(
        self,
        message_queue: queue.Queue,
        client_id: str,
        clean_session: bool,
        topic_prefix: str,
        request_topic: str,
        qos: int,
        retain: bool,
        reconnect_period_sec: float,
        ha_discovery_config: dict[str, Any],
        registers: Iterable[OptolinkVS2Register],
        optolink2mqtt_version: str,
    ) -> None:
        self._mqtt_client = MqttClient(
            message_queue,
            client_id,
            clean_session,
            topic_prefix,
            request_topic,
            qos,
            retain,
            reconnect_period_sec,
            self._get_ha_status_topic(ha_discovery_config),
        )
        self.enabled = ha_discovery_config["enabled"]
        self.discovery_topic = ha_discovery_config["topic"]
        self.device_name = ha_discovery_config["device_name"]
        self.registers = registers
        self.optolink2mqtt_version = optolink2mqtt_version
        self.last_discovery_connection_id = MqttClient.CONN_ID_INVALID
        self._last_connection_status = None
        self._last_connection_status_connection_id = MqttClient.CONN_ID_INVALID

    @staticmethod
    def _get_ha_status_topic(ha_discovery_config: dict[str, Any]) -> str:
        """Return the HomeAssistant status topic, or an empty string when disabled."""
        if ha_discovery_config["enabled"]:
            return ha_discovery_config["topic"] + "/status"
        return ""

    def connect(
        self, mqtt_broker: str, mqtt_port: int, username: str, password: str | None
    ) -> bool:
        return self._mqtt_client.connect(mqtt_broker, mqtt_port, username, password)

    def publish(self, topic: str, payload: str) -> None:
        self._mqtt_client.publish(topic, payload)

    def publish_retained(self, topic: str, payload: str) -> None:
        self._mqtt_client.publish_retained(topic, payload)

    def subscribe(self, topic: str) -> bool:
        return self._mqtt_client.subscribe(topic)

    def loop_start(self) -> None:
        self._mqtt_client.loop_start()

    def loop_stop(self) -> None:
        self._mqtt_client.loop_stop()

    def is_connected(self) -> bool:
        return self._mqtt_client.is_connected()

    def get_connection_id(self) -> int:
        return self._mqtt_client.get_connection_id()

    @property
    def num_subscriptions(self) -> int:
        return MqttClient.num_subscriptions

    def get_num_disconnects(self) -> int:
        return MqttClient.num_disconnects

    def get_human_friendly_stats(self) -> str:
        return self._mqtt_client.get_human_friendly_stats()

    def get_optolink2mqtt_status_topic(self) -> str:
        return self._mqtt_client.get_optolink2mqtt_status_topic()

    def get_optolink_connection_status_topic(self) -> str:
        return self._mqtt_client.get_optolink_connection_status_topic()

    def publish_optolink_connection_status(
        self, optolink_connected: bool, force: bool = False
    ) -> None:
        if not self.is_connected():
            return

        conn_id = self.get_connection_id()
        status = (
            MqttClient.OPTOLINK_CONNECTED_PAYLOAD
            if optolink_connected
            else MqttClient.OPTOLINK_DISCONNECTED_PAYLOAD
        )
        if (
            force
            or status != self._last_connection_status
            or conn_id != self._last_connection_status_connection_id
        ):
            self.publish_retained(self.get_optolink_connection_status_topic(), status)
            self._last_connection_status = status
            self._last_connection_status_connection_id = conn_id

    def publish_status_metrics(self, num_optolink_errors: int) -> None:
        """Publish the diagnostic counters and their stable MQTT state topics."""
        self.publish_retained(
            self._get_status_metric_topic(self.NUM_MQTT_DISCONNECTS_TOPIC),
            str(self.get_num_disconnects()),
        )
        self.publish_retained(
            self._get_status_metric_topic(self.NUM_OPTOLINK_ERRORS_TOPIC),
            str(num_optolink_errors),
        )

    def _get_status_metric_topic(self, metric_name: str) -> str:
        return f"{self.get_optolink2mqtt_status_topic()}/{metric_name}"

    def _publish_status_sensor_discovery(
        self, device: dict[str, Any], metric_name: str, sensor_name: str
    ) -> None:
        unique_id = f"{self.device_name}-{metric_name.replace('_', '-')}"
        payload = {
            "name": sensor_name,
            "unique_id": unique_id,
            "device": device,
            "origin": {
                "name": "optolink2mqtt",
                "sw": self.optolink2mqtt_version,
                "url": "https://github.com/f18m/viessmann-optolink2mqtt",
            },
            "state_topic": self._get_status_metric_topic(metric_name),
            "state_class": "total_increasing",
            "entity_category": "diagnostic",
            "availability_topic": self.get_optolink2mqtt_status_topic(),
            "payload_available": MqttClient.NEW_CONN_PAYLOAD,
            "payload_not_available": MqttClient.LAST_WILL_PAYLOAD,
        }
        topic = (
            f"{self.discovery_topic}/sensor/" f"{self.device_name}/{unique_id}/config"
        )
        logger.info("Publishing an MQTT discovery message on topic '%s'", topic)
        self.publish(topic, json.dumps(payload))

    def _publish_connection_status_discovery(self, device: dict[str, Any]) -> None:
        unique_id = f"{self.device_name}-optolink-connection-status"
        payload = {
            "name": "Opto Connection Status",
            "unique_id": unique_id,
            "device": device,
            "state_topic": self.get_optolink_connection_status_topic(),
            "payload_on": MqttClient.OPTOLINK_CONNECTED_PAYLOAD,
            "payload_off": MqttClient.OPTOLINK_DISCONNECTED_PAYLOAD,
            "device_class": "connectivity",
            "entity_category": "diagnostic",
            "availability_topic": self.get_optolink2mqtt_status_topic(),
            "payload_available": MqttClient.NEW_CONN_PAYLOAD,
            "payload_not_available": MqttClient.LAST_WILL_PAYLOAD,
        }
        topic = (
            f"{self.discovery_topic}/binary_sensor/"
            f"{self.device_name}/{unique_id}/config"
        )
        logger.info("Publishing an MQTT discovery messages on topic '%s'", topic)
        self.publish(topic, json.dumps(payload))

    def publish_discovery_messages(self) -> int:
        """Publish discovery messages for configured registers and connection status."""
        device = {
            "ids": self.device_name,
            "name": self.device_name,
            "manufacturer": "f18m/viessmann-optolink2mqtt",
            # FIXME: maybe we should ask in the config file for the Viessmann device model instead of
            #        using the Linux OS platform for this sw?
            "sw_version": platform.system(),
            "hw_version": platform.machine(),
            "model": platform.platform(terse=True),
            "configuration_url": "https://github.com/f18m/viessmann-optolink2mqtt",
        }
        num_msgs = 0
        for reg in self.registers:
            # Expire after 1.5 sampling intervals, with a 10-second minimum, so a
            # missed MQTT message does not immediately make an entity unavailable.
            expire_time_sec = max(10, reg.sampling_period_sec * 1.5)
            payload = reg.get_ha_discovery_payload(
                self.device_name,
                self.optolink2mqtt_version,
                device,
                expire_time_sec,
            )
            if payload is not None:
                topic = reg.get_ha_discovery_topic(
                    self.discovery_topic, self.device_name
                )
                logger.info(
                    "Publishing an MQTT discovery messages on topic '%s'", topic
                )
                self.publish(topic, payload)
                num_msgs += 1

        self._publish_connection_status_discovery(device)
        num_msgs += 1
        self._publish_status_sensor_discovery(
            device, self.NUM_MQTT_DISCONNECTS_TOPIC, "MQTT Disconnects"
        )
        num_msgs += 1
        self._publish_status_sensor_discovery(
            device, self.NUM_OPTOLINK_ERRORS_TOPIC, "Optolink Errors"
        )
        num_msgs += 1

        logger.info(
            "Published a total of %s MQTT discovery messages under the topic "
            "prefix '%s' for the device '%s'. The HomeAssistant MQTT integration "
            "should now be showing %s entities for the device '%s'.",
            num_msgs,
            self.discovery_topic,
            self.device_name,
            num_msgs,
            self.device_name,
        )
        return num_msgs

    def check_if_time_to_send_discovery_messages(self) -> bool:
        """
        Publish discovery after a new broker connection or HA restart.

        Returns whether the caller should republish register values as well.
        """
        if not self.enabled:
            return False

        should_republish_registers = False
        curr_conn_id = self.get_connection_id()
        if curr_conn_id != self.last_discovery_connection_id:
            logger.warning(
                "New connection to the MQTT broker detected (id=%s); phase 1: "
                "sending out MQTT discovery messages...",
                curr_conn_id,
            )
            self.publish_discovery_messages()
            self.last_discovery_connection_id = curr_conn_id

            logger.warning(
                "New connection to the MQTT broker detected (id=%s); phase 2: "
                "sending out all sensor values (regardless of their schedule)...",
                curr_conn_id,
            )
            should_republish_registers = True

        if self._mqtt_client.get_and_reset_ha_discovery_messages_requested_flag():
            logger.warning(
                "Detected notification that Home Assistant just (re)started; "
                "phase 1: publishing MQTT discovery messages..."
            )
            self.publish_discovery_messages()

            logger.warning(
                "Detected notification that Home Assistant just (re)started; "
                "phase 2: publishing all sensor values (regardless of their "
                "schedule)..."
            )
            should_republish_registers = True

        return should_republish_registers
