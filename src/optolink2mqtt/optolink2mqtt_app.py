"""
optolink2mqtt_app.py
----------------
Optolink2Mqtt main application class
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

import argparse
import os
import queue
import sched
import socket
import logging
import sys
import platform
import time
import serial
import paho.mqtt.client as paho  # pip install paho-mqtt

from .config import Config
from .mqtt_client import MqttClient
from .optolinkvs2_register import OptolinkVS2Register
from .optolinkvs2_protocol import OptolinkVS2Protocol


class Optolink2MqttApp:

    MAX_PENDING_MESSAGES = 1000

    HIGH_SCHEDULER_PRIORITY = 1
    NORMAL_SCHEDULER_PRIORITY = 10
    LOW_SCHEDULER_PRIORITY = 100

    def __init__(self) -> None:
        # the app is composed by 4 major components:
        self.config = None  # instance of Config
        self.message_queue = queue.Queue(Optolink2MqttApp.MAX_PENDING_MESSAGES)
        self.mqtt_client = None  # instance of MqttClient
        self.scheduler = None  # instance of sched.scheduler
        self.optolink_interface = None  # instance of OptolinkVS2Protocol
        self.last_logged_status = (None, None, None)

        # dict of OptolinkVS2Register instances keyed by their COMMAND TOPIC
        self.register_list_by_cmd_topic = {}

    def log_status(self) -> None:
        """
        Logs summary of how well this app is running.
        """

        logging.info(
            f"optolink2mqtt status: "
            f"{self.mqtt_client.get_human_friendly_stats()}"
            f"{self.optolink_interface.get_human_friendly_stats()}"
        )

    @staticmethod
    def on_schedule_timer(app: "Optolink2MqttApp", reg: OptolinkVS2Register) -> None:
        """
        Callback invoked by the scheduler when it's time to read a register.
        Please note that this is a static method, so all data must be accessed
        through the 'app' parameter.
        """

        logging.debug(
            f"Optolink2MqttApp.on_schedule_timer(name={reg.name}, addr=0x{reg.address:02x})",
        )

        rx_data = app.optolink_interface.read_datapoint_ext(reg.address, reg.length)
        if rx_data.is_successful():
            # publish on MQTT the "value" obtained from the raw data
            app.mqtt_client.publish(
                reg.get_mqtt_state_topic(), reg.get_value_from_rawdata(rx_data.data)
            )
        else:
            logging.error(
                f"Failed to read register '{reg.name}' (addr=0x{reg.address:04x}): error code 0x{rx_data.return_code:02x}"
            )

        # reschedule next occurrence for this register
        app.scheduler.enter(
            reg.get_next_occurrence_in_seconds(),
            Optolink2MqttApp.NORMAL_SCHEDULER_PRIORITY,
            Optolink2MqttApp.on_schedule_timer,
            (app, reg),
        )
        return

    @staticmethod
    def on_log_timer(app: "Optolink2MqttApp") -> None:
        """
        Periodically prints the status of optolink2mqtt
        """

        new_status = (
            MqttClient.num_disconnects,
            app.optolink_interface.get_total_rx_frames(),
        )
        if new_status != app.last_logged_status:
            # publish status on MQTT
            status_topic = app.mqtt_client.get_optolink2mqtt_status_topic()
            app.mqtt_client.publish(
                status_topic + "/num_mqtt_disconnects", MqttClient.num_disconnects
            )
            app.mqtt_client.publish(
                status_topic + "/num_optolink_errors",
                app.optolink_interface.get_total_errors(),
            )

            # publish status on log
            app.log_status()

            app.last_logged_status = new_status

        # reschedule next occurrence for status log
        log_period_sec = int(app.config.config["logging"]["report_status_period_sec"])
        app.scheduler.enter(
            log_period_sec,
            Optolink2MqttApp.LOW_SCHEDULER_PRIORITY,
            Optolink2MqttApp.on_log_timer,
            tuple([app]),
        )
        return

    @staticmethod
    def get_embedded_version() -> str:
        """
        Returns the embedded version of optolink2mqtt, forged at build time
        by the "hatch-vcs" plugin.

        In particular the "hatch-vcs" plugin writes a _optolink2mqtt_version.py file
        that contains a 'version' variable with the version string.
        """

        from ._optolink2mqtt_version import version as __version__

        return __version__

    def _publish_ha_discovery_messages(self) -> int:
        """
        Publish MQTT discovery messages for HomeAssistant, from all registers that have been decorated
        with the "ha_discovery" metadata.
        Returns the number of MQTT discovery messages published.
        """

        ha_discovery_topic = self.config.config["mqtt"]["ha_discovery"]["topic"]
        ha_device_name = self.config.config["mqtt"]["ha_discovery"]["device_name"]
        optolink2mqtt_ver = Optolink2MqttApp.get_embedded_version()

        device_dict = {
            "ids": ha_device_name,
            "name": ha_device_name,
            "manufacturer": "f18m/viessmann-optolink2mqtt",
            # FIXME: maybe we should ask in the config file for the Viessmann device model instead of
            #        using the Linux OS platform for this sw?
            "sw_version": platform.system(),  # the OS name like 'Linux', 'Darwin', 'Java', 'Windows'
            "hw_version": platform.machine(),  # this is actually something like "x86_64"
            "model": platform.platform(
                terse=True
            ),  # on Linux this is a condensed summary of "uname -a"
            "configuration_url": "https://github.com/f18m/viessmann-optolink2mqtt",
            # "connections": [["mac", get_mac_address()]],
        }
        num_msgs = 0
        for reg in self.register_list_by_cmd_topic.values():
            # expire the sensor in HomeAssistant after a duration equal to 1.5 the usual interval;
            # also apply a lower bound of 10sec; this is a reasonable way to avoid that a single MQTT
            # message not delivered turns the entity into "not available" inside HomeAssistant;
            # on the other hand, if optolink2mqtt goes down or the MQTT broker goes down, the entity at some
            # point will be unavailable so the user will know that something is wrong.
            expire_time_sec = max(10, reg.sampling_period_sec * 1.5)
            payload = reg.get_ha_discovery_payload(
                ha_device_name, optolink2mqtt_ver, device_dict, expire_time_sec
            )
            if payload is not None:
                topic = reg.get_ha_discovery_topic(ha_discovery_topic, ha_device_name)
                logging.info(
                    f"Publishing an MQTT discovery messages on topic '{topic}'"
                )
                self.mqtt_client.publish(topic, payload)
                num_msgs += 1

        logging.info(
            f"Published a total of {num_msgs} MQTT discovery messages under the topic prefix '{ha_discovery_topic}' for the device '{ha_device_name}'. The HomeAssistant MQTT integration should now be showing {num_msgs} entities for the device '{ha_device_name}'."
        )
        return num_msgs

    def setup(self) -> int:
        """
        Application setup
        """

        # CLI interface
        parser = argparse.ArgumentParser(
            prog="optolink2mqtt",
            description="Open source interface between a Viessmann device (heat pump, gas heater, etc) and MQTT",
            epilog="The configuration file is mandatory and it is searched in the following locations (in order):\n"
            + "  * the location pointed by the 'OPTOLINK2MQTT_CONFIG' environment variable\n  * "
            + "\n  * ".join(Config.get_default_config_file_name())
            + "\nSee documentation at https://github.com/f18m/optolink2mqtt for configuration examples and the config reference guide.\n",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "-V",
            "--version",
            help="Print version and exit",
            action="store_true",
            default=False,
        )

        if "COLUMNS" not in os.environ:
            os.environ["COLUMNS"] = "120"  # avoid too many line wraps
        args = parser.parse_args()
        if args.version:
            print(f"Version: {Optolink2MqttApp.get_embedded_version()}")
            return -1

        # start with DEBUG logging level till we load the config file:
        logging.basicConfig(level=logging.DEBUG)

        # read config file:
        self.config = Config()
        try:
            self.config.load()
        except Exception as e:
            logging.error(f"Cannot load configuration: {e}. Aborting.")
            sys.exit(2)

        self.config.apply_logging_config()

        #
        # hello message
        #

        logging.info(
            f"Optolink2MqttApp version {Optolink2MqttApp.get_embedded_version()} starting"
        )

        #
        # create MqttClient
        #
        ha_status_topic = ""
        if self.config.config["mqtt"]["ha_discovery"]["enabled"]:
            ha_status_topic = (
                self.config.config["mqtt"]["ha_discovery"]["topic"] + "/status"
            )
        self.mqtt_client = MqttClient(
            self.message_queue,
            self.config.config["mqtt"]["clientid"],
            False,  # clean_session
            self.config.config["mqtt"]["publish_topic_prefix"],
            self.config.config["mqtt"]["request_topic"],
            self.config.config["mqtt"]["qos"],
            self.config.config["mqtt"]["retain"],
            self.config.config["mqtt"]["reconnect_period_sec"],
            ha_status_topic,
        )

        #
        # create OptolinkVS2Protocol interface
        #
        serial_port_name = self.config.config["optolink"]["serial_port"]
        try:
            ser = serial.Serial(
                serial_port_name,
                baudrate=4800,
                bytesize=8,
                parity="E",
                stopbits=2,
                timeout=0,
                exclusive=True,
            )
        except serial.SerialException as e:
            logging.error(f"Cannot open serial port {serial_port_name}: {e}. Aborting.")
            return 1

        self.optolink_interface = OptolinkVS2Protocol(
            ser,
            None,  # serial port to forward data to a Vitoconnect
            self.config.config["optolink"]["show_received_bytes"],
        )
        if not self.optolink_interface.init_vs2():
            logging.error("Cannot initialize Optolink VS2 protocol. Aborting.")
            return 2

        #
        # parse list of registers & build a schedule
        #
        register_list = self.config.config["registers_poll_list"]
        assert isinstance(register_list, list)
        if not register_list:
            logging.error("No registers to read and poll, exiting")
            return 3

        self.scheduler = sched.scheduler(time.time, time.sleep)
        i = 0
        for reg in register_list:
            try:
                register_instance = OptolinkVS2Register(
                    reg,
                    self.config.config["mqtt"]["publish_topic_prefix"],
                )
            except ValueError as e:
                logging.error(f"Cannot parse register definition #{i}: {e}. Aborting.")
                return 4

            logging.info(
                f"Definition of register#{i}: {register_instance.get_human_readable_description()}"
            )

            # upon startup optolink2mqtt will immediately run all scheduling rules, just
            # scattered 100ms one from each other:
            first_time_delay_sec = i + 0.1

            # include this in our scheduler:
            self.scheduler.enter(
                first_time_delay_sec,
                Optolink2MqttApp.NORMAL_SCHEDULER_PRIORITY,
                Optolink2MqttApp.on_schedule_timer,
                (self, register_instance),
            )
            i += 1

            # store the OptolinkVS2Register also locally, in a dict that helps later
            # to process incoming MQTT write requests:
            self.register_list_by_cmd_topic[
                register_instance.get_mqtt_command_topic()
            ] = register_instance

        # add periodic log to schedule
        log_period_sec = int(self.config.config["logging"]["report_status_period_sec"])
        if log_period_sec > 0:
            logging.info(
                f"optolink2mqtt status will be published on topic {self.mqtt_client.get_optolink2mqtt_status_topic()} every {log_period_sec}sec"
            )
            self.scheduler.enter(
                log_period_sec,
                Optolink2MqttApp.LOW_SCHEDULER_PRIORITY,
                Optolink2MqttApp.on_log_timer,
                tuple([self]),
            )
        # else: logging of the status has been disabled

        # success
        return 0

    def _check_if_time_to_send_ha_discovery_messages(self) -> None:
        """
        Checks whether HomeAssistant has (re)started and MQTT discovery messages
        must be sent again.
        """
        curr_conn_id = self.mqtt_client.get_connection_id()
        if curr_conn_id != self.last_ha_discovery_messages_connection_id:
            # looks like a new MQTT connection to the broker has (recently) been estabilished;
            # send out MQTT discovery messages
            logging.warning(
                f"New connection to the MQTT broker detected (id={curr_conn_id}), sending out MQTT discovery messages..."
            )
            self._publish_ha_discovery_messages()
            self.last_ha_discovery_messages_connection_id = curr_conn_id

        if self.mqtt_client.get_and_reset_ha_discovery_messages_requested_flag():
            # MQTT discovery messages have been requested...
            logging.warning(
                "Detected notification that Home Assistant just (re)started; phase 1: publishing MQTT discovery messages..."
            )
            self._publish_ha_discovery_messages()

            # TODO
            # logging.warning(
            #    "Detected notification that Home Assistant just (re)started; phase 2: publishing all sensor values (regardless of their schedule)..."
            # )
            # self.read_all_registers()

    def _process_received_mqtt_message(self, msg: paho.MQTTMessage) -> None:
        """
        Processes a message received over MQTT from the subscribed topics.
        """

        topic = msg.topic
        payload = msg.payload.decode("utf-8")

        if topic not in self.register_list_by_cmd_topic:
            logging.error(f"Received message from unknown topic: {topic}")
            return

        logging.debug(f"Processing received MQTT message on topic '{topic}'")

        reg = self.register_list_by_cmd_topic[topic]
        if not reg.writable:
            logging.error(
                f"Received a write request on topic '{topic}' but the associated register '{reg.name}' is not writable"
            )
            return

        # try to convert the payload into raw bytes to be written to the register
        try:
            raw_data = reg.get_rawdata_from_value(payload)
        except ValueError as e:
            logging.error(
                f"Cannot convert MQTT payload '{payload}' into raw data for register '{reg.name}': {e}"
            )
            raw_data = None
            # keep going -- need to schedule a read later anyway

        # perform the write operation
        if raw_data is not None:
            rx_data = self.optolink_interface.write_datapoint_ext(reg.address, raw_data)
            if rx_data.is_successful():
                logging.info(
                    f"Successfully wrote value [{raw_data.hex()}], obtained from MQTT payload '{payload}' to register '{reg.name}' (0x{reg.address:04x})"
                )
            else:
                logging.error(
                    f"Failed to write register '{reg.name}' (addr=0x{reg.address:04x}): error code 0x{rx_data.return_code:02x}"
                )
                # keep going -- need to schedule a read later anyway

        # now schedule to read back the register to publish the updated value on MQTT ASAP;
        # otherwise other MQTT clients will not see the updated value till the next
        # scheduled read which could be minutes later !!
        # This is useful to do even in case of write failure, because we need to inform ASAP
        # the other MQTT clients that the actual value of the register did not change !
        self.scheduler.enter(
            0.01,  # close-to-zero delay
            Optolink2MqttApp.HIGH_SCHEDULER_PRIORITY,
            Optolink2MqttApp.on_schedule_timer,
            (self, reg),
        )

    def _core_loop(self) -> None:
        """
        Runs the logic of optolink2mqtt application.
        Every "sleep quantum" the app wakes up and checks whether
        * it's time to read a register
        * some write request has been received over MQTT
        * MQTT discovery messages were requested
        * etc

        This function exits only in case an exception is thrown
        """
        sleep_quantum_sec = 0.5

        while self.keep_running:
            # execute all sampling operations waiting in the queue
            delay_for_next_register_sec = self.scheduler.run(blocking=False)

            # execute a sliced wait, so we reuse this thread to check for other occurrences
            # (instead of resorting to a multithread Python app)
            time_waited_sec = 0
            while (
                delay_for_next_register_sec > 0
                and time_waited_sec < delay_for_next_register_sec
            ):
                time.sleep(sleep_quantum_sec)
                time_waited_sec += sleep_quantum_sec

                if self.config.config["mqtt"]["ha_discovery"]["enabled"]:
                    self._check_if_time_to_send_ha_discovery_messages()

                try:
                    msg = self.message_queue.get_nowait()
                    self._process_received_mqtt_message(msg)
                except queue.Empty:
                    continue  # no message to process

    def run(self) -> int:
        """
        Start the main application loop.
        This function blocks the main thread till the application is stopped.
        Returns the exit code.
        """

        # estabilish a connection to the MQTT broker
        try:
            self.mqtt_client.connect(
                self.config.config["mqtt"]["broker"]["host"],
                self.config.config["mqtt"]["broker"]["port"],
                self.config.config["mqtt"]["broker"]["username"],
                self.config.config["mqtt"]["broker"]["password"],
            )
        except ConnectionRefusedError as e:
            logging.error(f"Cannot connect to MQTT broker: {e}. Retrying shortly.")
            # IMPORTANT: there's no need to abort here -- paho MQTT client loop_start() will keep trying to reconnect
            # so, if and when the MQTT broker will be available, the connection will be established
        except OSError as e:
            logging.error(f"Cannot connect to MQTT broker: {e}. Retrying shortly.")
            # IMPORTANT: there's no need to abort here -- paho MQTT client loop_start() will keep trying to reconnect
            # so, if and when the MQTT broker will be available, the connection will be established

        # if a register is writable, subscribe to its 'command' topic:
        for cmd_topic, reg in self.register_list_by_cmd_topic.items():
            if reg.writable:
                self.mqtt_client.subscribe(cmd_topic)
        logging.info(
            f"Executed {self.mqtt_client.num_subscriptions} MQTT subscriptions for writable registers."
        )

        self.last_ha_discovery_messages_connection_id = MqttClient.CONN_ID_INVALID

        # block the main thread on the MQTT client loop
        self.keep_running = True
        while self.keep_running:
            try:
                # restart the MQTT client secondary thread in case it was never started or failed for some reason
                self.mqtt_client.loop_start()

                # run till an exception is thrown:
                self._core_loop()

            # try to recover from exceptions:
            except socket.error:
                logging.error("socket.error caught, sleeping for 5 sec...")
                time.sleep(self.config.config["mqtt"]["reconnect_period_sec"])
            except KeyboardInterrupt:
                logging.warning("KeyboardInterrupt caught, exiting")
                break

        # gracefully stop the event loop of MQTT client
        self.mqtt_client.loop_stop()

        # log status one last time
        self.log_status()

        logging.warning("Exiting gracefully")

        return 0
