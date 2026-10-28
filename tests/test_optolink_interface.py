import os
import sys
from unittest.mock import Mock

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolink_interface import (  # noqa: E402
    OptolinkInterface,
    OptolinkReinitializationRequired,
)
from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402
from optolink2mqtt.optolinkvs2_protocol import (  # noqa: E402
    ErrorCode,
    OptolinkVS2RxData,
)


def create_interface():
    interface = OptolinkInterface(
        "/dev/null",
        False,
        2,
        5,
        max_consecutive_failures_before_reinit=3,
    )
    interface.protocol = Mock()
    interface.protocol.get_total_errors.return_value = 1
    return interface


def failed_read():
    return OptolinkVS2RxData(ErrorCode.Timeout, 0x2000, bytearray())


def test_consecutive_failures_raise_without_reinitializing_protocol():
    interface = create_interface()
    interface.protocol.read_datapoint_ext.return_value = failed_read()
    register = Mock(name="test_register", address=0x2000, length=1)

    assert interface.sample_register(register) is None
    assert interface.sample_register(register) is None

    try:
        interface.sample_register(register)
    except OptolinkReinitializationRequired:
        pass
    else:
        raise AssertionError("Expected VS2 reinitialization to be requested")

    interface.protocol.init_vs2.assert_not_called()
    assert interface.consecutive_failures == 3


def test_successful_read_resets_consecutive_failure_count():
    interface = create_interface()
    register = Mock(address=0x2000, length=1)
    interface.protocol.read_datapoint_ext.return_value = failed_read()
    interface.sample_register(register)
    interface.protocol.read_datapoint_ext.return_value = OptolinkVS2RxData(
        ErrorCode.Success, 0x2000, bytearray()
    )
    register.get_value_from_rawdata.return_value = 1

    assert interface.sample_register(register) == 1
    assert interface.consecutive_failures == 0


def test_reconnect_timeout_limits_wait_before_giving_up(monkeypatch):
    interface = create_interface()
    elapsed = [0.0]
    monkeypatch.setattr(
        "optolink2mqtt.optolink_interface.time.monotonic",
        lambda: elapsed[0],
    )
    monkeypatch.setattr(
        "optolink2mqtt.optolink_interface.time.sleep",
        lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    )

    assert interface.handle_serial_error(RuntimeError("failure")) == 2
    assert elapsed[0] == 0
    elapsed[0] += 2
    assert interface.handle_serial_error(RuntimeError("failure")) == 2
    elapsed[0] += 2
    assert interface.handle_serial_error(RuntimeError("failure")) == 1
    elapsed[0] += 1
    assert interface.handle_serial_error(RuntimeError("failure")) is None
    assert elapsed[0] == 5


def test_reconnect_timeout_shorter_than_period_is_not_exceeded(monkeypatch):
    interface = create_interface()
    interface.reconnect_timeout_sec = 1
    elapsed = [0.0]
    monkeypatch.setattr(
        "optolink2mqtt.optolink_interface.time.monotonic",
        lambda: elapsed[0],
    )
    monkeypatch.setattr(
        "optolink2mqtt.optolink_interface.time.sleep",
        lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    )

    assert interface.handle_serial_error(RuntimeError("failure")) == 1
    assert elapsed[0] == 0
    elapsed[0] += 1
    assert interface.handle_serial_error(RuntimeError("failure")) is None
    assert elapsed[0] == 1


def test_zero_reconnect_timeout_retries_forever_at_configured_period(monkeypatch):
    interface = create_interface()
    interface.reconnect_timeout_sec = 0
    elapsed = [0.0]
    monkeypatch.setattr(
        "optolink2mqtt.optolink_interface.time.monotonic",
        lambda: elapsed[0],
    )
    error = RuntimeError("failure")

    for attempt in range(1, 4):
        interface.protocol = Mock()
        assert interface.handle_serial_error(error) == 2
        assert interface.protocol is None
        assert interface.reconn_attempts == attempt
        elapsed[0] += 2


def test_run_handles_reinitialization_exception_through_reconnect_path(monkeypatch):
    app = Optolink2MqttApp()
    app.config = Mock()
    app.config.config = {
        "mqtt": {
            "broker": {
                "host": "localhost",
                "port": 1883,
                "username": None,
                "password": None,
            }
        }
    }
    app.enhanced_mqtt_client = Mock()
    app.optolink_interface = Mock()
    app.optolink_interface.connect.return_value = True
    app.optolink_interface.get_total_errors.return_value = 3
    app.register_list_by_cmd_topic = {}
    app._sample_all_registers = Mock()
    app._publish_connection_status = Mock()
    app.log_status = Mock()
    app.optolink_interface.handle_serial_error.return_value = 2
    sleep = Mock()
    monkeypatch.setattr("optolink2mqtt.optolink2mqtt_app.time.sleep", sleep)
    core_loop_calls = [0]

    def core_loop():
        if core_loop_calls[0] == 0:
            core_loop_calls[0] += 1
            raise OptolinkReinitializationRequired("reinitialize")
        app.keep_running = False

    app._core_loop = core_loop

    assert app.run() == 0

    app.optolink_interface.handle_serial_error.assert_called_once()
    app.enhanced_mqtt_client.publish_status_metrics.assert_called_once_with(3)
    assert app.optolink_interface.connect.call_count == 2
    sleep.assert_called_once_with(2)
