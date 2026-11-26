import os
import sys

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.config import Config  # noqa: E402
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402

DEFAULT_CONFIG = os.path.realpath(THIS_SCRIPT_DIR + "/../optolink2mqtt.yaml")
SCHEMA = os.path.realpath(SRC_DIR + "/optolink2mqtt/schema/optolink2mqtt.schema.yaml")


def test_shipped_default_config_registers_are_all_valid():
    config = Config()
    config.load(DEFAULT_CONFIG, SCHEMA)

    registers = [
        OptolinkVS2Register(reg, config.config["mqtt"]["publish_topic_prefix"])
        for reg in config.config["registers_poll_list"]
    ]

    assert len(registers) == len(config.config["registers_poll_list"])
    assert all(r.ha_discovery is not None for r in registers)
