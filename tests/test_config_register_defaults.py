import os
import sys

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.config import Config  # noqa: E402

SCHEMA = os.path.realpath(SRC_DIR + "/optolink2mqtt/schema/optolink2mqtt.schema.yaml")

CONFIG_TEMPLATE = """
config_version: 2
optolink:
  serial_port: /dev/null
mqtt:
  broker:
    host: localhost
    port: 1883
registers_poll_list:
  - name: external_temperature
    register: 0x0101
    length: 2
{extra}
"""


def load_config(tmp_path, extra: str) -> Config:
    config_file = tmp_path / "optolink2mqtt.yaml"
    config_file.write_text(CONFIG_TEMPLATE.format(extra=extra))
    config = Config()
    config.load(str(config_file), SCHEMA)
    return config


def test_register_defaults_only_use_schema_keys(tmp_path):
    config = load_config(tmp_path, "    sampling_period_seconds: 10")

    reg = config.config["registers_poll_list"][0]
    assert reg["sampling_period_seconds"] == 10
    assert "sampling_period_sec" not in reg


def test_sampling_period_seconds_is_mandatory(tmp_path):
    with pytest.raises(ValueError, match="sampling_period_seconds"):
        load_config(tmp_path, "")
