import json
import os
import sys

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.config import Config  # noqa: E402
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402

SCHEMA = os.path.realpath(SRC_DIR + "/optolink2mqtt/schema/optolink2mqtt.schema.yaml")

CONFIG = """
config_version: 2
optolink:
  serial_port: /dev/null
mqtt:
  broker:
    host: localhost
    port: 1883
registers_poll_list:
  - name: outside_temperature
    sampling_period_seconds: 10
    register: 0x0101
    length: 2
    ha_discovery:
      name: "Outside Temperature"
      platform: sensor
      device_class: temperature
      unit_of_measurement: "°C"
      value_template: "{{ value | float }}"
  - name: pump
    sampling_period_seconds: 10
    register: 0x0484
    length: 1
    ha_discovery:
      name: "Pump"
      platform: binary_sensor
      device_class: running
      payload_on: "1"
      payload_off: "0"
  - name: dhw_temperature_set
    sampling_period_seconds: 10
    register: 0x6000
    length: 2
    writable: true
    ha_discovery:
      name: "DHW Set Temperature"
      platform: number
      device_class: temperature
      min: 0
      max: 60
      optimistic: false
      expire_after: 0
"""


@pytest.fixture
def payloads(tmp_path):
    config_file = tmp_path / "optolink2mqtt.yaml"
    config_file.write_text(CONFIG)
    config = Config()
    config.load(str(config_file), SCHEMA)
    ret = {}
    for reg in config.config["registers_poll_list"]:
        register = OptolinkVS2Register(reg, "prefix/")
        ret[register.name] = json.loads(
            register.get_ha_discovery_payload("device", "1.0", {}, 120)
        )
    return ret


def test_state_class_defaults_only_for_sensors(payloads):
    assert payloads["outside_temperature"]["state_class"] == "measurement"
    assert "state_class" not in payloads["pump"]
    assert "state_class" not in payloads["dhw_temperature_set"]


def test_falsy_values_are_forwarded(payloads):
    number = payloads["dhw_temperature_set"]
    assert number["min"] == 0
    assert number["max"] == 60
    assert number["optimistic"] is False
    # an explicit expire_after of 0 disables expiration rather than using the default
    assert number["expire_after"] == 0


def test_unset_optional_values_are_omitted(payloads):
    sensor = payloads["outside_temperature"]
    for key in ["icon", "payload_on", "payload_off", "min", "optimistic"]:
        assert key not in sensor
    assert sensor["expire_after"] == 120


def test_value_template_is_forwarded(payloads):
    assert payloads["outside_temperature"]["value_template"] == "{{ value | float }}"
    assert "value_template" not in payloads["pump"]
