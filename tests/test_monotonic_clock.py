import logging
import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402
from optolink2mqtt.optolinkvs2_protocol import (  # noqa: E402
    ErrorCode,
    OptolinkVS2Protocol,
)

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


class SteppedClock:
    """
    Fake 'time' module: the monotonic clock advances by 10ms at every sleep, while the
    wall clock keeps jumping backwards (e.g. NTP correcting a clock that ran ahead).
    """

    def __init__(self):
        self.now = 0.0
        self.wall = 1_000_000.0
        self.calls = 0

    def sleep(self, sec):
        self.now += 0.01
        self.calls += 1
        if self.calls > 10_000:
            raise AssertionError("receive_fullraw() did not time out")

    def monotonic(self):
        return self.now

    def time(self):
        self.wall -= 3600.0
        return self.wall


def test_receive_fullraw_timeout_ignores_wall_clock_jumps(monkeypatch):
    clock = SteppedClock()
    monkeypatch.setattr(
        "optolink2mqtt.optolinkvs2_protocol.time",
        SimpleNamespace(sleep=clock.sleep, monotonic=clock.monotonic, time=clock.time),
    )
    ser = Mock()
    ser.read_all.return_value = b""

    code, data = OptolinkVS2Protocol(ser).receive_fullraw(eot_time=0.05, timeout=1.0)

    assert code == ErrorCode.Timeout
    assert data == bytearray()
    assert clock.now == pytest.approx(1.0, abs=0.05)
