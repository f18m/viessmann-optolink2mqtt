"""
config.py
----------------
Config file loader class
Copyright 2026 Francesco Montorsi

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

import os
import logging
import yaml
import yamale
from yamale import YamaleError
from platformdirs import PlatformDirs
import socket

from .datetime_bcd import parse_timezone
from .ha_units import HA_MEASUREMENT_UNITS
from .ha_support import (
    HA_SUPPORTED_DEVICE_CLASSES,
    HA_SUPPORTED_STATE_CLASSES,
    HA_SUPPORTED_PLATFORMS,
    HA_UNSUPPORTED_DEVICE_CLASSES_FOR_MEASUREMENTS,
)


class Config:
    """
    Config class validates and reads the optolink2mqtt YAML configuration file and reports to the
    rest of the application the data as a dictionary.
    """

    CONFIG_FILE_NAME = "optolink2mqtt.yaml"
    CONFIG_SCHEMA_FILE_NAME = "optolink2mqtt.schema.yaml"

    # Version of the configuration file format accepted by this release, set in the top-level
    # "config_version" key. Bump it on every change that makes existing configuration files
    # invalid, and add the matching conversion to the upgrade tool in docs/config-upgrade/.
    CONFIG_VERSION = 2
    CONFIG_UPGRADE_URL = (
        "https://f18m.github.io/viessmann-optolink2mqtt/config-upgrade/"
    )

    def __init__(self):
        self.config = None

    @staticmethod
    def get_default_config_file_name() -> list[str]:
        """
        Returns the default config file full paths where this software will look for the config file.
        """
        plat_dirs = PlatformDirs("optolink2mqtt", "f18m")
        cfgfile_paths = [
            # NOTE: the site_config_dir in Unix is returning /etc/xdg/optolink2mqtt but frankly that's very
            # unusual and not what I would expect. So we replace it with /etc/optolink2mqtt
            os.path.join(d, Config.CONFIG_FILE_NAME)
            for d in [
                plat_dirs.user_config_dir,
                plat_dirs.site_config_dir.replace("/etc/xdg/", "/etc/"),
            ]
        ]

        return cfgfile_paths

    def load(self, filename: str = None, schema_filename: str = None):
        """
        filename is a fully qualified path to the YAML config file.
        The YAML file is validated against the schema file provided as argument,
        and optional configuration parameters are populated with their default values.
        """

        if filename is None:
            # NOTE: a typical use case where OPTOLINK2MQTT_CONFIG is set is within the official Docker image of optolink2mqtt
            if os.getenv("OPTOLINK2MQTT_CONFIG", None) is not None:
                filename = os.getenv("OPTOLINK2MQTT_CONFIG")
            else:
                # first try the platform-specific, user-specific config directory:
                for attempt in Config.get_default_config_file_name():
                    if os.path.exists(attempt):
                        filename = attempt
                        break

                if filename is None:
                    raise ValueError(
                        f"Failed to find the configuration file '{Config.CONFIG_FILE_NAME}' in all default locations: {','.join(Config.get_default_config_file_name())}"
                    )

        if schema_filename is None:
            # NOTE: a typical use case where OPTOLINK2MQTT_CONFIGSCHEMA is set is within the official Docker image of optolink2mqtt
            if os.getenv("OPTOLINK2MQTT_CONFIGSCHEMA", None) is not None:
                schema_filename = os.getenv("OPTOLINK2MQTT_CONFIGSCHEMA")
            else:
                source_code_install_dir = os.path.dirname(os.path.abspath(__file__))
                schema_install_dir = os.path.join(source_code_install_dir, "schema")
                schema_filename_attempts = [
                    os.path.join(schema_install_dir, Config.CONFIG_SCHEMA_FILE_NAME),
                ]

                for attempt in schema_filename_attempts:
                    if os.path.exists(attempt):
                        schema_filename = attempt
                        break

                if schema_filename is None:
                    raise ValueError(
                        f"Failed to find the configuration file schema '{Config.CONFIG_SCHEMA_FILE_NAME}' in the directory '{schema_install_dir}'. Is the installation of optolink2mqtt corrupted?"
                    )

        logging.info(
            "Loading app config '%s' and its schema '%s'", filename, schema_filename
        )

        try:
            tuple_list = yamale.make_data(filename)
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing YAML file '{filename}': {e}")
        if len(tuple_list) != 1:
            raise ValueError(
                f"Error parsing YAML file '{filename}': expected a single document, got {len(tuple_list)}"
            )

        # check the version before the schema, which would otherwise report the first
        # incompatible key instead of the actual problem
        config_version = Config._get_config_version(filename, tuple_list[0][0])

        try:
            schema = yamale.make_schema(schema_filename)
            yamale.validate(schema, tuple_list)
        except YamaleError as e:
            raise ValueError(
                f"Configuration file '{filename}' does not conform to schema: {e}"
            )

        # extract just the validated dictionary and store it in self.config
        the_tuple = tuple_list[0]
        if len(the_tuple) != 2:
            raise ValueError(
                f"Error parsing YAML file '{filename}': invalid format from yamala library"
            )
        self.config = the_tuple[0]
        self.config["config_version"] = config_version

        # add default values for optional configuration parameters, if they're missing:
        self._fill_defaults_logging()
        self._fill_defaults_mqtt()
        self._fill_defaults_optolink()
        self._apply_mqtt_password_from_env()
        self._check_mqtt_broker_security()

        # add default values for optional configuration parameters in registers_poll_list
        validated_registers = []
        for reg in self.config["registers_poll_list"]:
            validated_registers.append(self._fill_defaults_register(reg))
        self.config["registers_poll_list"] = validated_registers

        # additional coherency check:
        # the same register address can be present more than once only to extract
        # different bytes of it, i.e. if all its entries have a byte_filter
        regs_by_address = {}
        for r in self.config["registers_poll_list"]:
            regs_by_address.setdefault(r["register"], []).append(r)
        for addr, regs in regs_by_address.items():
            if len(regs) > 1 and any(r["byte_filter"] is None for r in regs):
                raise ValueError(
                    f"Configuration file '{filename}' is invalid: the register address 0x{addr:04X} is present "
                    f"more than once in 'registers_poll_list' ({', '.join(r['name'] for r in regs)}); "
                    "this is allowed only if every entry for that address has a 'byte_filter'"
                )

        logging.info(
            f"Configuration file '{filename}' successfully loaded and validated against schema. It contains {len(self.config['registers_poll_list'])} registers to sample/poll."
        )

    @staticmethod
    def _get_config_version(filename: str, data) -> int:
        """
        Returns the "config_version" of the parsed configuration file, raising a ValueError
        unless it is the one supported by this release (Config.CONFIG_VERSION).
        """
        if not isinstance(data, dict):
            # not a mapping: let the schema validation report it
            return Config.CONFIG_VERSION

        # configuration files written before "config_version" existed are version 1
        version = data.get("config_version", 1)
        supported = Config.CONFIG_VERSION
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError(
                f"Configuration file '{filename}' has an invalid 'config_version' ({version!r}): "
                f"expected an integer; this release of optolink2mqtt supports config_version {supported}"
            )
        if version < supported:
            raise ValueError(
                f"Configuration file '{filename}' has config_version {version}, but this release of "
                f"optolink2mqtt supports only config_version {supported}. Convert the file with the "
                f"upgrade tool at {Config.CONFIG_UPGRADE_URL}"
            )
        if version > supported:
            raise ValueError(
                f"Configuration file '{filename}' has config_version {version}, which is newer than "
                f"config_version {supported} supported by this release of optolink2mqtt. Upgrade "
                f"optolink2mqtt, or use a configuration file written for config_version {supported}"
            )
        return version

    def _fill_defaults_optolink(self):
        m = self.config["optolink"]
        if "show_received_bytes" not in m:
            m["show_received_bytes"] = False
        if "reconnect_period_sec" not in m:
            m["reconnect_period_sec"] = 60
        if "reconnect_timeout_sec" not in m:
            m["reconnect_timeout_sec"] = 600
        if "max_consecutive_failures_before_reinit" not in m:
            m["max_consecutive_failures_before_reinit"] = 3
        if "timezone" not in m:
            # None means: the device clock uses the host timezone
            m["timezone"] = None
        else:
            try:
                parse_timezone(m["timezone"])
            except ValueError as e:
                raise ValueError(
                    f"Invalid 'optolink.timezone' attribute in configuration file: {e}"
                )

    def _fill_defaults_logging(self):
        # logging
        if "logging" not in self.config:
            self.config["logging"] = {"level": "ERROR"}
        if "level" not in self.config["logging"]:
            self.config["logging"]["level"] = "ERROR"
        if "report_status_period_sec" not in self.config["logging"]:
            self.config["logging"]["report_status_period_sec"] = 600

    def _fill_defaults_mqtt(self):
        m = self.config["mqtt"]

        # mqtt.broker object
        if "port" not in m["broker"]:
            m["broker"]["port"] = 1883
        if "username" not in m["broker"]:
            m["broker"]["username"] = None
        if "password" not in m["broker"]:
            m["broker"]["password"] = None
        if "tls" not in m["broker"]:
            # 8883 is the IANA port for MQTT over TLS
            m["broker"]["tls"] = m["broker"]["port"] == 8883
        for k in ["ca_certs", "certfile", "keyfile"]:
            if k not in m["broker"]:
                m["broker"][k] = None

        # other optional "mqtt" keys
        if "retain" not in m:
            m["retain"] = False
        if "clientid" not in m:
            m["clientid"] = "optolink2mqtt-%s" % os.getpid()
        if "qos" not in m:
            m["qos"] = 0
        if "reconnect_period_sec" not in m:
            m["reconnect_period_sec"] = 5
        if "publish_topic_prefix" not in m:
            hn = socket.gethostname()
            m["publish_topic_prefix"] = f"optolink2mqtt/{hn}/"
        else:
            # make sure the publish_topic_prefix ALWAYS ends with a slash,
            # to ensure separation from the topic that will be appended to it
            if m["publish_topic_prefix"][-1] != "/":
                m["publish_topic_prefix"] += "/"

        if "request_topic" not in m:
            m["request_topic"] = "request"

        # mqtt.ha_discovery object
        if "ha_discovery" not in m:
            m["ha_discovery"] = {"enabled": False, "topic": "homeassistant"}
        if "enabled" not in m["ha_discovery"]:
            m["ha_discovery"]["enabled"] = False
        if "topic" not in m["ha_discovery"]:
            m["ha_discovery"]["topic"] = "homeassistant"
        if "device_name" not in m["ha_discovery"]:
            m["ha_discovery"]["device_name"] = socket.gethostname()

        # enhance the original config with the one containing all settings:
        self.config["mqtt"] = m

    def _apply_mqtt_password_from_env(self):
        password = os.getenv("MQTT_BROKER_PASSWORD")
        if password is not None:
            self.config["mqtt"]["broker"]["password"] = password
            return

        password_file = os.getenv("MQTT_BROKER_PASSWORD_FILE")
        if password_file is None:
            return

        try:
            with open(password_file, encoding="utf-8") as file:
                password = file.read().rstrip("\r\n")
        except OSError as e:
            raise ValueError(
                f"Error reading MQTT broker password file '{password_file}': {e}"
            ) from e

        self.config["mqtt"]["broker"]["password"] = password

    def _check_mqtt_broker_security(self):
        b = self.config["mqtt"]["broker"]

        if not b["tls"]:
            tls_options = [k for k in ["ca_certs", "certfile", "keyfile"] if b[k]]
            if tls_options:
                raise ValueError(
                    f"Invalid 'mqtt.broker' configuration: {tls_options} are set but 'tls' is false"
                )
        if b["keyfile"] and not b["certfile"]:
            raise ValueError(
                "Invalid 'mqtt.broker' configuration: 'keyfile' requires 'certfile'"
            )

        if b["password"] is not None and not b["username"]:
            # the MQTT protocol does not allow a password without a username: paho
            # would silently connect without credentials
            logging.warning(
                "An MQTT broker password is configured but 'mqtt.broker.username' is not: "
                "the password will NOT be sent to the broker"
            )
        if b["password"] is not None and not b["tls"]:
            logging.warning(
                "MQTT broker credentials will be sent in plaintext since TLS is disabled; "
                "set 'mqtt.broker.tls: true' if the broker supports it"
            )

    def _fill_defaults_register(self, reg: dict) -> dict:
        # NOTE: "sampling_period_seconds" is mandatory in the schema, so it has no default
        if "signed" not in reg:
            reg["signed"] = False
        if "writable" not in reg:
            reg["writable"] = False
        if "scale_factor" not in reg:
            reg["scale_factor"] = 1.0
        else:
            # ensure scale_factor is a float
            if float(reg["scale_factor"]) <= 0.0:
                raise ValueError(
                    f"{reg['name']}: Invalid 'scale_factor' attribute in configuration file: shall be greater than zero"
                )

        if "byte_filter" not in reg:
            reg["byte_filter"] = None
        if "enum" not in reg:
            reg["enum"] = None
        if "type" not in reg:
            reg["type"] = "int"

        if "ha_discovery" not in reg:
            # HA discovery disabled for this task:
            reg["ha_discovery"] = None
        else:
            h = reg["ha_discovery"]

            # name is required and shall be non-empty
            if "name" not in h:
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.name' attribute in configuration file: missing"
                )
            if h["name"] == "":
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.name' attribute in configuration file: empty"
                )

            # optional parameters with defaults:

            if "platform" not in h:
                # most of psutil/pySMART tasks are sensors, so "sensor" is a good default:
                h["platform"] = "sensor"
            elif h["platform"] not in HA_SUPPORTED_PLATFORMS:
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.platform' attribute in configuration file: {h['platform']}. Expected one of {HA_SUPPORTED_PLATFORMS}"
                )
            if "device_class" not in h:
                h["device_class"] = None
            elif h["device_class"] not in HA_SUPPORTED_DEVICE_CLASSES[h["platform"]]:
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.device_class' attribute in configuration file: {h['device_class']}. Expected one of {HA_SUPPORTED_DEVICE_CLASSES}"
                )

            if (
                "unit_of_measurement" in h
                and h["unit_of_measurement"] not in HA_MEASUREMENT_UNITS
            ):
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.unit_of_measurement' attribute in configuration file: {h['unit_of_measurement']}. Expected one of {HA_MEASUREMENT_UNITS}"
                )

            if "state_class" not in h:
                # "measurement" is a good default since most of psutil/pySMART tasks represent measurements
                # of bytes, percentages, temperatures, etc.
                # We just make sure to never add "state_class" to some types of "device_class"es that will
                # trigger errors on the HomeAssistant side, and to platforms other than "sensor",
                # since "state_class" is a sensor-only attribute in HomeAssistant.
                # Only numeric registers can be measurements.
                if (
                    h["platform"] == "sensor"
                    and reg["type"] in ("int", "float")
                    and h["device_class"]
                    not in HA_UNSUPPORTED_DEVICE_CLASSES_FOR_MEASUREMENTS
                ):
                    h["state_class"] = "measurement"
            elif (
                "state_class" in h
                and h["state_class"] not in HA_SUPPORTED_STATE_CLASSES
            ):
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.state_class' attribute in configuration file: {h['state_class']}. Expected one of {HA_SUPPORTED_STATE_CLASSES}"
                )

            # optional parameters without defaults:

            optional_params = [
                "unit_of_measurement",
                "icon",
                "expire_after",
                "payload_on",
                "payload_off",
                "value_template",
            ]
            for o in optional_params:
                if o not in h:
                    # create the key but set its value to None
                    h[o] = None

            reg["ha_discovery"] = h

        return reg

    # values accepted for logging.level (WARN and ERR are kept for backward compatibility)
    LOGGING_LEVELS = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERR": logging.ERROR,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    def apply_logging_config(self):
        """
        Sets the level of the root logger from the 'logging.level' config value.
        The handlers already installed on the root logger are left untouched.
        """
        logl = self.config["logging"]["level"]
        logging.info(f"Setting log level to {logl}")
        level = Config.LOGGING_LEVELS.get(str(logl).upper())
        if level is None:
            logging.error(
                f"Invalid logging level '{logl}' in config file. Expected one of "
                f"{list(Config.LOGGING_LEVELS)}. Defaulting to ERROR level."
            )
            level = logging.ERROR
        logging.getLogger().setLevel(level)
