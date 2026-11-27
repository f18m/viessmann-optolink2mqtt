import logging
import os
import sched
import sys
import threading
import time
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402

CONFIG_HEADER = """
config_version: 2
optolink:
  serial_port: /dev/ttyUSB0
mqtt:
  broker:
    host: localhost
    port: 1883
registers_poll_list:
"""

REGISTER = """
  - name: reg{i}
    sampling_period_seconds: 600
    register: {addr}
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


def test_initial_register_reads_are_staggered_by_100ms(
    tmp_path, monkeypatch, restore_root_logger
):
    cfg = tmp_path / "optolink2mqtt.yaml"
    cfg.write_text(
        CONFIG_HEADER
        + "".join(REGISTER.format(i=i, addr=0x0100 + i) for i in range(4)),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPTOLINK2MQTT_CONFIG", str(cfg))
    monkeypatch.setattr(sys, "argv", ["optolink2mqtt"])
    monkeypatch.setattr(
        Optolink2MqttApp, "get_embedded_version", staticmethod(lambda: "test")
    )
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=Mock())
    )
    real_scheduler = sched.scheduler
    # freeze the scheduler clock so that event times are exactly the delays
    monkeypatch.setattr(
        "optolink2mqtt.optolink2mqtt_app.sched.scheduler",
        lambda timefunc, delayfunc: real_scheduler(lambda: 0.0, delayfunc),
    )

    app = Optolink2MqttApp()
    assert app.setup() == 0

    register_events = [
        e
        for e in app.scheduler.queue
        if e.priority == Optolink2MqttApp.NORMAL_SCHEDULER_PRIORITY
    ]
    assert [round(e.time, 3) for e in register_events] == [0.1, 0.2, 0.3, 0.4]


def make_app():
    app = Optolink2MqttApp()
    app.enhanced_mqtt_client = Mock()
    app.enhanced_mqtt_client.consume_disconnect_notification.return_value = False
    app.enhanced_mqtt_client.check_if_time_to_send_discovery_messages.return_value = (
        False
    )
    app.optolink_interface = Mock()
    app.scheduler = sched.scheduler(time.monotonic, time.sleep)
    app.keep_running = True
    return app


def test_queued_messages_are_not_processed_one_per_quantum(monkeypatch):
    app = make_app()
    processed = []

    def process(msg):
        processed.append(msg)
        if len(processed) == 5:
            app.keep_running = False

    monkeypatch.setattr(app, "_process_received_mqtt_message", process)
    for i in range(5):
        app.message_queue.put(i)
    # next register read in a few seconds
    app.scheduler.enter(3, 1, lambda: None)

    start = time.monotonic()
    app._core_loop()

    assert processed == [0, 1, 2, 3, 4]
    # previously each message waited for a 0.5s sleep: at least 2.5s for 5 messages
    assert time.monotonic() - start < 0.5


def test_message_is_processed_as_soon_as_it_arrives(monkeypatch):
    app = make_app()
    processed = []

    def process(msg):
        processed.append((msg, time.monotonic()))
        app.keep_running = False

    monkeypatch.setattr(app, "_process_received_mqtt_message", process)
    app.scheduler.enter(3, 1, lambda: None)
    sent_at = []

    def send_later():
        time.sleep(0.05)
        sent_at.append(time.monotonic())
        app.message_queue.put("msg")

    t = threading.Thread(target=send_later)
    t.start()
    app._core_loop()
    t.join()

    assert processed[0][0] == "msg"
    assert processed[0][1] - sent_at[0] < 0.2
