import os
import sys
from unittest.mock import Mock

import pytest
import serial

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolink_interface import (  # noqa: E402
    OptolinkConnectionFailed,
    OptolinkInterface,
)


def make_interface(monkeypatch, init_vs2):
    ser = Mock()
    monkeypatch.setattr(
        "optolink2mqtt.optolink_interface.serial.Serial", Mock(return_value=ser)
    )
    protocol = Mock(ser=ser)
    protocol.init_vs2.side_effect = init_vs2
    protocol.get_total_errors.return_value = 0
    monkeypatch.setattr(
        "optolink2mqtt.optolink_interface.OptolinkVS2Protocol",
        Mock(return_value=protocol),
    )
    return OptolinkInterface("/dev/null", False, 1, 0), ser


def test_serial_port_closed_when_vs2_init_fails(monkeypatch):
    interface, ser = make_interface(monkeypatch, init_vs2=lambda: False)

    with pytest.raises(OptolinkConnectionFailed):
        interface.connect()

    ser.close.assert_called_once()
    assert not interface.is_connected()


def test_serial_port_closed_when_vs2_init_raises(monkeypatch):
    def init_vs2():
        raise serial.SerialException("device disconnected")

    interface, ser = make_interface(monkeypatch, init_vs2=init_vs2)

    with pytest.raises(serial.SerialException):
        interface.connect()

    ser.close.assert_called_once()


def test_serial_port_closed_when_protocol_discarded(monkeypatch):
    interface, ser = make_interface(monkeypatch, init_vs2=lambda: True)
    interface.connect()
    ser.close.assert_not_called()

    interface.handle_serial_error(Exception("boom"))

    ser.close.assert_called_once()
    assert not interface.is_connected()


def test_close_errors_do_not_prevent_reconnect(monkeypatch):
    interface, ser = make_interface(monkeypatch, init_vs2=lambda: True)
    ser.close.side_effect = OSError("already gone")
    interface.connect()

    # reconnecting discards the previous protocol and must not propagate the close error
    interface.connect()

    assert interface.is_connected()
