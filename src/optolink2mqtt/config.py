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

from .ha_units import HomeAssistantMeasurementUnits


class Config:
    """
    Config class validates and reads the optolink2mqtt YAML configuration file and reports to the
    rest of the application the data as a dictionary.
    """

    CONFIG_FILE_NAME = "optolink2mqtt.yaml"
    CONFIG_SCHEMA_FILE_NAME = "optolink2mqtt.schema.yaml"

    # FIXME, TODO: remove all these hardcoded Home Assistant constants that do not make sense for optolink2mqtt

    HA_SUPPORTED_PLATFORMS = ["sensor", "binary_sensor"]
    HA_SUPPORTED_DEVICE_CLASSES = {
        # see https://www.home-assistant.io/integrations/binary_sensor/#device-class
        "binary_sensor": [
            "battery",
            "battery_charging",
            "carbon_monoxide",
            "cold",
            "connectivity",
            "door",
            "garage_door",
            "gas",
            "heat",
            "light",
            "lock",
            "moisture",
            "motion",
            "moving",
            "occupancy",
            "opening",
            "plug",
            "power",
            "presence",
            "problem",
            "running",
            "safety",
            "smoke",
            "sound",
            "tamper",
            "update",
            "vibration",
            "window",
        ],
        # see https://www.home-assistant.io/integrations/sensor/#device-class
        "sensor": [
            "date",
            "enum",
            "timestamp",
            "apparent_power",
            "aqi",
            "area",
            "atmospheric_pressure",
            "battery",
            "blood_glucose_concentration",
            "carbon_monoxide",
            "carbon_dioxide",
            "conductivity",
            "current",
            "data_rate",
            "data_size",
            "distance",
            "duration",
            "energy",
            "energy_storage",
            "frequency",
            "gas",
            "humidity",
            "illuminance",
            "irradiance",
            "moisture",
            "monetary",
            "nitrogen_dioxide",
            "nitrogen_monoxide",
            "nitrous_oxide",
            "ozone",
            "ph",
            "pm1",
            "pm10",
            "pm25",
            "power_factor",
            "power",
            "precipitation",
            "precipitation_intensity",
            "pressure",
            "reactive_power",
            "signal_strength",
            "sound_pressure",
            "speed",
            "sulphur_dioxide",
            "temperature",
            "volatile_organic_compounds",
            "volatile_organic_compounds_parts",
            "voltage",
            "volume",
            "volume_storage",
            "volume_flow_rate",
            "water",
            "weight",
            "wind_speed",
        ],
    }

    # see https://developers.home-assistant.io/docs/core/entity/sensor/#long-term-statistics
    HA_SUPPORTED_STATE_CLASSES = ["measurement", "total", "total_increasing"]

    # see https://developers.home-assistant.io/docs/core/entity/sensor/#long-term-statistics
    HA_UNSUPPORTED_DEVICE_CLASSES_FOR_MEASUREMENTS = [
        "date",
        "enum",
        "energy",
        "gas",
        "monetary",
        "timestamp",
        "volume",
        "water",
    ]

    def __init__(self):
        self.config = None
        self.schema = None

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

        try:
            schema = yamale.make_schema(
                schema_filename
            )  # Assuming self.schema_path holds the path to the YAML schema
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

        # add default values for optional configuration parameters, if they're missing:
        self._fill_defaults_logging()
        self._fill_defaults_mqtt()

        # add default values for optional configuration parameters in registers_poll_list
        validated_registers = []
        for reg in self.config["registers_poll_list"]:
            validated_registers.append(self._fill_defaults_register(reg))
        self.config["registers_poll_list"] = validated_registers

        logging.info(
            f"Configuration file '{filename}' successfully loaded and validated against schema. It contains {len(self.config['registers_poll_list'])} registers to sample/poll."
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

    def _fill_defaults_register(self, reg: dict) -> dict:
        if "sampling_period_sec" not in reg:
            reg["sampling_period_sec"] = 1
        if "scale_factor" not in reg:
            reg["scale_factor"] = 1.0
        if "byte_filter" not in reg:
            reg["byte_filter"] = None
        if "enum" not in reg:
            reg["enum"] = None

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
            elif h["platform"] not in Config.HA_SUPPORTED_PLATFORMS:
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.platform' attribute in configuration file: {h['platform']}. Expected one of {Config.HA_SUPPORTED_PLATFORMS}"
                )
            if "device_class" not in h:
                h["device_class"] = None
            elif (
                h["device_class"]
                not in Config.HA_SUPPORTED_DEVICE_CLASSES[h["platform"]]
            ):
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.device_class' attribute in configuration file: {h['device_class']}. Expected one of {Config.HA_SUPPORTED_DEVICE_CLASSES}"
                )

            if (
                "unit_of_measurement" in h
                and h["unit_of_measurement"]
                not in HomeAssistantMeasurementUnits.get_all_constants()
            ):
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.unit_of_measurement' attribute in configuration file: {h['unit_of_measurement']}. Expected one of {HomeAssistantMeasurementUnits.get_all_constants()}"
                )

            if "state_class" not in h:
                # "measurement" is a good default since most of psutil/pySMART tasks represent measurements
                # of bytes, percentages, temperatures, etc.
                # We just make sure to never add "state_class" to some types of "device_class"es that will
                # trigger errors on the HomeAssistant side...
                if (
                    h["device_class"]
                    not in Config.HA_UNSUPPORTED_DEVICE_CLASSES_FOR_MEASUREMENTS
                ):
                    h["state_class"] = "measurement"
            elif (
                "state_class" in h
                and h["state_class"] not in Config.HA_SUPPORTED_STATE_CLASSES
            ):
                raise ValueError(
                    f"{reg['name']}: Invalid 'ha_discovery.state_class' attribute in configuration file: {h['state_class']}. Expected one of {Config.HA_SUPPORTED_STATE_CLASSES}"
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

    def apply_logging_config(self):
        # Apply logging config
        logl = self.config["logging"]["level"]
        logging.info(f"Setting log level to {logl}")
        if logl == "DEBUG":
            logging.basicConfig(level=logging.DEBUG, force=True)
        elif logl == "INFO":
            logging.basicConfig(level=logging.INFO, force=True)
        elif logl == "WARN" or logl == "WARNING":
            logging.basicConfig(level=logging.WARNING, force=True)
        elif logl == "ERR" or logl == "ERROR":
            logging.basicConfig(level=logging.ERROR, force=True)
        else:
            logging.error(
                f"Invalid logging level '{logl}' in config file. Defaulting to ERROR level."
            )
            logging.basicConfig(level=logging.ERROR, force=True)
