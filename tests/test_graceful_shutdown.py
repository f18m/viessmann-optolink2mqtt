import os
import signal
import sys
import threading
import time
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.mqtt_client import MqttClient  # noqa: E402
from optolink2mqtt.optolink_interface import OptolinkConnectionFailed  # noqa: E402
from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402


def create_app():
    app = Optolink2MqttApp()
    app.config = Mock()
    app.config.config = {
        "mqtt": {
            "reconnect_period_sec": 60,
            "broker": {
                "host": "localhost",
                "port": 1883,
                "username": None,
                "password": None,
                "tls": False,
                "ca_certs": None,
                "certfile": None,
                "keyfile": None,
            },
        }
    }
    app.enhanced_mqtt_client = Mock()
    app.enhanced_mqtt_client.consume_disconnect_notification.return_value = False
    app.optolink_interface = Mock()
    app.optolink_interface.get_total_errors.return_value = 0
    app.register_list_by_cmd_topic = {}
    app._sample_all_registers = Mock()
    app._publish_connection_status = Mock()
    app.log_status = Mock()
    return app


def assert_clean_shutdown(app):
    names = [c[0] for c in app.enhanced_mqtt_client.method_calls]
    assert "disconnect" in names
    assert "loop_stop" in names
    # the broker must be told we're leaving before the network loop is stopped
    assert names.index("disconnect") < names.index("loop_stop")
    app.log_status.assert_called_once()


def test_sigterm_stops_run_and_disconnects_cleanly():
    app = create_app()
    app.scheduler = Mock()
    # next register sample is far away: the core loop would otherwise wait 10 minutes
    app.scheduler.run.return_value = 600

    timer = threading.Timer(0.3, os.kill, (os.getpid(), signal.SIGTERM))
    timer.start()
    start = time.monotonic()
    try:
        assert app.run() == 0
    finally:
        timer.cancel()

    assert time.monotonic() - start < 5
    assert_clean_shutdown(app)
    # the previous SIGTERM handler is restored
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_sigterm_interrupts_mqtt_reconnect_wait():
    app = create_app()

    def core_loop():
        raise OSError("MQTT client disconnected")

    app._core_loop = core_loop

    timer = threading.Timer(0.3, os.kill, (os.getpid(), signal.SIGTERM))
    timer.start()
    start = time.monotonic()
    try:
        assert app.run() == 0
    finally:
        timer.cancel()

    # reconnect_period_sec is 60: the wait must not run to completion
    assert time.monotonic() - start < 5
    assert_clean_shutdown(app)


def test_stop_during_optolink_reconnect_wait_exits_without_reconnecting():
    app = create_app()
    app.optolink_interface.connect.side_effect = OptolinkConnectionFailed("no device")
    app.optolink_interface.handle_serial_error.return_value = 30

    timer = threading.Timer(0.3, app.request_stop, ("test",))
    timer.start()
    start = time.monotonic()
    try:
        assert app.run() == 0
    finally:
        timer.cancel()

    assert time.monotonic() - start < 5
    app.optolink_interface.connect.assert_called_once()
    assert_clean_shutdown(app)


def test_fatal_optolink_error_still_disconnects_cleanly():
    app = create_app()
    app.optolink_interface.connect.side_effect = OptolinkConnectionFailed("no device")
    app.optolink_interface.handle_serial_error.return_value = None

    assert app.run() == 2
    assert_clean_shutdown(app)


def make_mqtt_client(monkeypatch, connected):
    transport = Mock()
    transport.is_connected.return_value = connected
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=transport)
    )
    client = MqttClient(
        Mock(),
        "test-client",
        False,
        "optolink2mqtt/test/",
        "",
        1,
        False,
        5,
        "",
    )
    return client, transport


def test_mqtt_disconnect_publishes_offline_status_first(monkeypatch):
    client, transport = make_mqtt_client(monkeypatch, connected=True)

    client.disconnect()

    transport.publish.assert_called_once_with(
        "optolink2mqtt/test/optolink2mqtt_status",
        MqttClient.LAST_WILL_PAYLOAD,
        qos=1,
        retain=True,
    )
    transport.publish.return_value.wait_for_publish.assert_called_once()
    names = [c[0] for c in transport.method_calls]
    assert names.index("publish") < names.index("disconnect")


def test_mqtt_disconnect_when_not_connected_skips_publish(monkeypatch):
    client, transport = make_mqtt_client(monkeypatch, connected=False)

    client.disconnect()

    transport.publish.assert_not_called()
    transport.disconnect.assert_called_once()
