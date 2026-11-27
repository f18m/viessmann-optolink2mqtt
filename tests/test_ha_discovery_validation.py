import os
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402


def make_register_def(writable: bool, platform: str) -> dict:
    return {
        "name": "test_register",
        "sampling_period_seconds": 60,
        "register": 0x1000,
        "length": 1,
        "signed": False,
        "writable": writable,
        "scale_factor": 1.0,
        "byte_filter": None,
        "enum": None,
        "type": "int",
        "ha_discovery": {"name": "Test", "platform": platform},
    }


@pytest.mark.parametrize(
    "writable,platform", [(True, "sensor"), (False, "number"), (False, "")]
)
def test_invalid_ha_discovery_raises_value_error(writable, platform):
    with pytest.raises(ValueError):
        OptolinkVS2Register(make_register_def(writable, platform), "prefix/")


def test_setup_exits_cleanly_on_invalid_ha_discovery(monkeypatch):
    config = Mock()
    config.config = {
        "mqtt": {"ha_discovery": {}, "publish_topic_prefix": "prefix/"},
        "optolink": {
            "serial_port": "/dev/null",
            "show_received_bytes": False,
            "reconnect_period_sec": 1,
            "reconnect_timeout_sec": 1,
            "max_consecutive_failures_before_reinit": 3,
            "timezone": None,
        },
        "registers_poll_list": [make_register_def(True, "sensor")],
    }
    config_class = Mock(return_value=config)
    config_class.get_default_config_file_name.return_value = ["optolink2mqtt.yaml"]
    monkeypatch.setattr("optolink2mqtt.optolink2mqtt_app.Config", config_class)
    monkeypatch.setattr(
        Optolink2MqttApp, "get_embedded_version", staticmethod(lambda: "test")
    )
    monkeypatch.setattr(sys, "argv", ["optolink2mqtt"])

    assert Optolink2MqttApp().setup() == 4
