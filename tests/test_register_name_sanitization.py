import os
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402


def make_register_def(name: str, address: int = 0x1000) -> dict:
    return {
        "name": name,
        "sampling_period_seconds": 60,
        "register": address,
        "length": 1,
        "signed": False,
        "writable": False,
        "scale_factor": 1.0,
        "byte_filter": None,
        "enum": None,
        "type": "int",
        "ha_discovery": None,
    }


@pytest.mark.parametrize(
    "name,expected",
    [
        # unchanged from the previous implementation
        ("Test Register", "test_register"),
        ("Name-With-Dashes", "name_with_dashes"),
        ("Außentemperatur", "auentemperatur"),
        ("Flow (°C)", "flow_c"),
        ('"Quoted" [x]', "quoted_x"),
        # runs of 3+ separators used to leave "__"
        ("Flow (°C) / Return-Temp.", "flow_c_return_temp"),
        ("a - b", "a_b"),
        ("a___b", "a_b"),
        # MQTT wildcards and other characters were not sanitized at all
        ("Pump #1", "pump_1"),
        ("Mode +/- offset", "mode_offset"),
        ("Valve 100%", "valve_100"),
        ("A&B*C", "a_b_c"),
    ],
)
def test_sanitized_name(name, expected):
    reg = OptolinkVS2Register(make_register_def(name), "home")
    assert reg.sanitized_name == expected
    assert reg.get_mqtt_state_topic() == f"home/{expected}"


@pytest.mark.parametrize("name", ["", "°°°", " - ", "()"])
def test_name_without_usable_characters_is_rejected(name):
    with pytest.raises(ValueError):
        OptolinkVS2Register(make_register_def(name), "home")


def run_setup(monkeypatch, register_defs):
    config = Mock()
    config.config = {
        "mqtt": {
            "ha_discovery": {},
            "publish_topic_prefix": "prefix/",
            "clientid": "test",
            "request_topic": "",
            "qos": 0,
            "retain": False,
            "reconnect_period_sec": 1,
        },
        "optolink": {
            "serial_port": "/dev/null",
            "show_received_bytes": False,
            "reconnect_period_sec": 1,
            "reconnect_timeout_sec": 1,
            "max_consecutive_failures_before_reinit": 3,
            "timezone": None,
        },
        "logging": {"report_status_period_sec": 0},
        "registers_poll_list": register_defs,
    }
    config_class = Mock(return_value=config)
    config_class.get_default_config_file_name.return_value = ["optolink2mqtt.yaml"]
    monkeypatch.setattr("optolink2mqtt.optolink2mqtt_app.Config", config_class)
    monkeypatch.setattr("optolink2mqtt.optolink2mqtt_app.EnhancedMqttClient", Mock())
    monkeypatch.setattr(
        Optolink2MqttApp, "get_embedded_version", staticmethod(lambda: "test")
    )
    monkeypatch.setattr(sys, "argv", ["optolink2mqtt"])
    app = Optolink2MqttApp()
    return app, app.setup()


@pytest.mark.parametrize(
    "first,second",
    [("Boiler Temp", "Boiler Temp"), ("Boiler Temp", "boiler-temp.")],
)
def test_setup_rejects_registers_with_colliding_topics(
    monkeypatch, caplog, first, second
):
    _, ret = run_setup(
        monkeypatch,
        [make_register_def(first, 0x1000), make_register_def(second, 0x2000)],
    )

    assert ret == 4
    assert "prefix/boiler_temp" in caplog.text


def test_setup_accepts_registers_with_distinct_topics(monkeypatch):
    app, ret = run_setup(
        monkeypatch,
        [make_register_def("Boiler Temp", 0x1000), make_register_def("Flow", 0x2000)],
    )

    assert ret == 0
    assert len(app.register_list_by_cmd_topic) == 2
