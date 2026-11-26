import logging
import os
import sys
import time
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402

CONFIG = """
optolink:
  serial_port: /dev/ttyUSB0
mqtt:
  broker:
    host: localhost
    port: 1883
registers_poll_list:
  - name: outside_temperature
    sampling_period_seconds: 60
    register: 0x0800
    length: 2
"""


@pytest.fixture
def restore_root_logger():
    # Optolink2MqttApp.setup() reconfigures the root logger
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    yield
    root.setLevel(level)
    root.handlers[:] = handlers


def test_scheduler_uses_monotonic_clock(tmp_path, monkeypatch, restore_root_logger):
    cfg = tmp_path / "optolink2mqtt.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    monkeypatch.setenv("OPTOLINK2MQTT_CONFIG", str(cfg))
    monkeypatch.setattr(sys, "argv", ["optolink2mqtt"])
    monkeypatch.setattr(
        Optolink2MqttApp, "get_embedded_version", staticmethod(lambda: "test")
    )
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=Mock())
    )

    app = Optolink2MqttApp()
    assert app.setup() == 0

    assert app.scheduler.timefunc is time.monotonic
