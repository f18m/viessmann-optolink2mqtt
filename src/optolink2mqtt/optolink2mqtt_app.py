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
import logging
import os
import queue
import sched
import socket
import sys
import termios
import time

import paho.mqtt.client as paho  # pip install paho-mqtt
import serial

from .config import Config
from .enhanced_mqtt_client import EnhancedMqttClient
from .optolink_interface import OptolinkInterface, OptolinkReinitializationRequired
from .optolinkvs2_register import OptolinkVS2Register


class Optolink2MqttApp:

    MAX_PENDING_MESSAGES = 1000

    HIGH_SCHEDULER_PRIORITY = 1
    NORMAL_SCHEDULER_PRIORITY = 10
    LOW_SCHEDULER_PRIORITY = 100

    def __init__(self) -> None:
        # the app is composed by 4 major components:
        self.config = None  # instance of Config
        self.message_queue = queue.Queue(Optolink2MqttApp.MAX_PENDING_MESSAGES)
        self.enhanced_mqtt_client = None  # instance of EnhancedMqttClient
        self.scheduler = None  # instance of sched.scheduler
        self.optolink_interface = None  # instance of OptolinkInterface
        self.last_logged_status = (None, None, None)

        # dict of OptolinkVS2Register instances keyed by their COMMAND TOPIC
        self.register_list_by_cmd_topic = {}

    def log_status(self) -> None:
        """
        Logs summary of how well this app is running.
        """

        logging.info(
            f"optolink2mqtt status: "
            f"{self.enhanced_mqtt_client.get_human_friendly_stats()}"
            f"{self.optolink_interface.get_human_friendly_stats()}"
        )

    def _sample_register(self, reg: OptolinkVS2Register) -> bool:
        """
        Samples a single register and publishes its value on MQTT.
        """

        value = self.optolink_interface.sample_register(reg)
        if value is None:
            self.enhanced_mqtt_client.publish_status_metrics(
                self.optolink_interface.get_total_errors()
            )
            return False

        # publish on MQTT the "value" obtained from the raw data
        self.enhanced_mqtt_client.publish(reg.get_mqtt_state_topic(), value)
        return True

    def _sample_all_registers(self) -> None:
        """
        Samples all registers and publishes their values on MQTT.
        """

        nregs = 0
        for reg in self.register_list_by_cmd_topic.values():
            if self._sample_register(reg):
                nregs += 1
        logging.info(f"Sampled {nregs} registers successfully and published on MQTT")

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

        # reschedule next occurrence for this register
        app.scheduler.enter(
            reg.get_next_occurrence_in_seconds(),
            Optolink2MqttApp.NORMAL_SCHEDULER_PRIORITY,
            Optolink2MqttApp.on_schedule_timer,
            (app, reg),
        )

        # sample the register after scheduling the next occurrence
        app._sample_register(reg)
        return

    @staticmethod
    def on_log_timer(app: "Optolink2MqttApp") -> None:
        """
        Periodically prints the status of optolink2mqtt
        """

        new_status = (
            app.enhanced_mqtt_client.get_num_disconnects(),
            app.optolink_interface.get_total_rx_frames(),
            app.optolink_interface.get_total_errors(),
        )
        if new_status != app.last_logged_status:
            app.enhanced_mqtt_client.publish_status_metrics(new_status[2])

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

    def _publish_connection_status(self, force: bool = False) -> None:
        """
        Publishes (retained) the Optolink connection status when it changes
        or when a new MQTT connection was established.
        """
        self.enhanced_mqtt_client.publish_optolink_connection_status(
            self.optolink_interface.is_connected(), force
        )

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

        ha_discovery_config = self.config.config["mqtt"]["ha_discovery"]

        #
        # create OptolinkInterface (the serial port is opened later, in run())
        #
        self.optolink_interface = OptolinkInterface(
            self.config.config["optolink"]["serial_port"],
            self.config.config["optolink"]["show_received_bytes"],
            self.config.config["optolink"]["reconnect_period_sec"],
            self.config.config["optolink"]["reconnect_timeout_sec"],
            self.config.config["optolink"]["max_consecutive_failures_before_reinit"],
        )

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

        #
        # create enhanced MQTT client
        #
        self.enhanced_mqtt_client = EnhancedMqttClient(
            self.message_queue,
            self.config.config["mqtt"]["clientid"],
            False,  # clean_session
            self.config.config["mqtt"]["publish_topic_prefix"],
            self.config.config["mqtt"]["request_topic"],
            self.config.config["mqtt"]["qos"],
            self.config.config["mqtt"]["retain"],
            self.config.config["mqtt"]["reconnect_period_sec"],
            ha_discovery_config,
            self.register_list_by_cmd_topic.values(),
            Optolink2MqttApp.get_embedded_version(),
        )

        # add periodic log to schedule
        log_period_sec = int(self.config.config["logging"]["report_status_period_sec"])
        if log_period_sec > 0:
            logging.info(
                f"optolink2mqtt status metrics will be published every {log_period_sec}sec"
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
        raw_data = reg.get_rawdata_from_value(payload)

        # perform the write operation
        if raw_data is not None:
            if self.optolink_interface.write_register(reg, raw_data):
                logging.info(
                    f"Successfully wrote value [{raw_data.hex()}], obtained from MQTT payload '{payload}' to register '{reg.name}' (0x{reg.address:04x})"
                )
            else:
                self.enhanced_mqtt_client.publish_status_metrics(
                    self.optolink_interface.get_total_errors()
                )
            # on failure keep going -- need to schedule a read later anyway

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
            if self.enhanced_mqtt_client.consume_disconnect_notification():
                raise socket.error("MQTT client disconnected")

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

                if self.enhanced_mqtt_client.consume_disconnect_notification():
                    raise socket.error("MQTT client disconnected")

                self._publish_connection_status()

                if (
                    self.enhanced_mqtt_client is not None
                    and self.enhanced_mqtt_client.check_if_time_to_send_discovery_messages()
                ):
                    self._sample_all_registers()

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
            self.enhanced_mqtt_client.connect(
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
                self.enhanced_mqtt_client.subscribe(cmd_topic)
        logging.info(
            f"Executed {self.enhanced_mqtt_client.num_subscriptions} MQTT subscriptions for writable registers."
        )

        # at the start of the application we need to establish the Optolink connection
        # and that might be required later on as well in case of serial port errors
        new_optolink_conn_required = True

        # block the main thread on the MQTT client loop
        self.keep_running = True
        while self.keep_running:
            try:
                if new_optolink_conn_required:
                    if not self.optolink_interface.connect():
                        error = RuntimeError(
                            "Cannot initialize Optolink VS2 protocol"
                        )
                        reconnect_delay_sec = (
                            self.optolink_interface.handle_serial_error(error)
                        )
                        if reconnect_delay_sec is None:
                            return 2
                        time.sleep(reconnect_delay_sec)
                        continue

                    new_optolink_conn_required = False
                    self._publish_connection_status()

                    # immediately after a new Optolink connection is established,
                    # publish all registers to MQTT
                    logging.warning(
                        "New Optolink connection established; publishing all sensor values (regardless of their schedule)..."
                    )
                    self._sample_all_registers()

                # restart the MQTT client secondary thread in case it was never started or failed for some reason
                self.enhanced_mqtt_client.loop_start()

                # run till an exception is thrown:
                self._core_loop()

            # try to recover from NETWORK exceptions:
            except socket.error as e:
                reconn_period_sec = self.config.config["mqtt"]["reconnect_period_sec"]
                logging.error(
                    f"socket/network error caught: {e}, sleeping for {reconn_period_sec} sec..."
                )
                time.sleep(reconn_period_sec)

            # try to recover from SERIAL/OPTOLINK exceptions:
            except (
                OptolinkReinitializationRequired,
                termios.error,
                serial.SerialException,
            ) as e:
                # termios is used by the pyserial POSIX implementation
                # sometimes it throws errors when the serial port is disconnected
                # so catch them here and trigger a new serial-port reinitialization
                self.enhanced_mqtt_client.publish_status_metrics(
                    self.optolink_interface.get_total_errors()
                )
                reconnect_delay_sec = self.optolink_interface.handle_serial_error(e)
                if reconnect_delay_sec is None:
                    # exceeded max time for reconnecting... exit the application
                    return 1
                time.sleep(reconnect_delay_sec)
                new_optolink_conn_required = True
                self._publish_connection_status()
            except KeyboardInterrupt:
                logging.warning("KeyboardInterrupt caught, exiting")
                break

        # gracefully stop the event loop of MQTT client
        self.enhanced_mqtt_client.loop_stop()

        # log status one last time
        self.log_status()

        logging.warning("Exiting gracefully")

        return 0
