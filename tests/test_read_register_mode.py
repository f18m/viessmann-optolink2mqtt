"""
Tests for the CLI modes and the "read-register" mode.
"""

import errno
import os
import sys
import threading
from unittest.mock import Mock

import pytest
import serial

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt import read_register  # noqa: E402
from optolink2mqtt.cli import MODE_READ_REGISTER, MODE_RUN, parse_args  # noqa: E402
from optolink2mqtt.optolink_interface import OptolinkInterface  # noqa: E402
from optolink2mqtt.optolinkvs2_protocol import (  # noqa: E402
    ErrorCode,
    OptolinkVS2Protocol,
    OptolinkVS2RxData,
)

#
# CLI parsing
#


def test_no_mode_defaults_to_run():
    args = parse_args([])
    assert args.mode == MODE_RUN
    assert args.version is False


def test_version_flag_without_mode():
    assert parse_args(["-V"]).version is True


def test_run_mode():
    assert parse_args(["run"]).mode == MODE_RUN


def test_read_register_minimal_arguments_use_defaults():
    args = parse_args(["read-register", "0x00F8", "2"])
    assert args.mode == MODE_READ_REGISTER
    assert args.address == 0x00F8
    assert args.length == 2
    assert args.signed is False
    assert args.scale_factor == 1.0
    assert args.byte_filter is None
    assert args.serial_port is None


def test_read_register_all_arguments():
    args = parse_args(
        [
            "read-register",
            "--serial-port",
            "/dev/ttyUSB1",
            "2048",
            "4",
            "signed",
            "0.1",
            "b:0:1",
        ]
    )
    assert args.address == 2048
    assert args.length == 4
    assert args.signed is True
    assert args.scale_factor == 0.1
    assert args.byte_filter == "b:0:1"
    assert args.serial_port == "/dev/ttyUSB1"


@pytest.mark.parametrize(
    "argv",
    [
        ["read-register", "zz", "2"],
        ["read-register", "0x10", "0"],
        ["read-register", "0x10", "2", "maybe"],
        ["read-register", "0x10", "2", "false", "0"],
        ["read-register", "0x10", "2", "false", "nan"],
        ["read-register", "0x10"],
    ],
)
def test_read_register_invalid_arguments(argv):
    with pytest.raises(SystemExit) as e:
        parse_args(argv)
    assert e.value.code == 2


def test_invalid_byte_filter_is_rejected_before_opening_the_port(monkeypatch):
    connect = Mock()
    monkeypatch.setattr(read_register, "connect_exclusively", connect)
    args = parse_args(
        ["read-register", "--serial-port", "/dev/x", "0x10", "2", "0", "1", "b:0:5"]
    )

    assert read_register.run_read_register(args) == read_register.EXIT_INVALID_REGISTER
    connect.assert_not_called()


#
# Serial port busy detection
#


def test_find_processes_using_detects_other_processes(tmp_path):
    device = tmp_path / "ttyUSB0"
    device.write_text("")
    proc = tmp_path / "proc"
    for pid, target in (
        (101, device),
        (102, tmp_path / "other"),
        (os.getpid(), device),
    ):
        (proc / str(pid) / "fd").mkdir(parents=True)
        os.symlink(target, proc / str(pid) / "fd" / "3")
        (proc / str(pid) / "cmdline").write_bytes(b"optolink2mqtt\0run\0")
    (proc / "self").mkdir()

    users = read_register.find_processes_using(str(device), str(proc))

    # our own process is never reported
    assert users == [(101, "optolink2mqtt run")]


def test_find_processes_using_without_proc(tmp_path):
    assert read_register.find_processes_using("/dev/x", str(tmp_path / "none")) == []


def test_lock_failure_is_reported_as_busy(monkeypatch):
    monkeypatch.setattr(read_register, "find_processes_using", lambda dev: [])
    interface = Mock(serial_port="/dev/ttyUSB0")
    interface.connect.side_effect = serial.SerialException(
        errno.EAGAIN, "Could not exclusively lock port /dev/ttyUSB0"
    )

    with pytest.raises(read_register.SerialPortBusy):
        read_register.connect_exclusively(interface)


def test_other_serial_errors_are_not_reported_as_busy(monkeypatch):
    monkeypatch.setattr(read_register, "find_processes_using", lambda dev: [])
    interface = Mock(serial_port="/dev/ttyUSB0")
    interface.connect.side_effect = serial.SerialException(
        errno.ENOENT, "could not open port /dev/ttyUSB0"
    )

    with pytest.raises(serial.SerialException):
        read_register.connect_exclusively(interface)


def test_process_holding_the_port_is_reported_as_busy(monkeypatch):
    monkeypatch.setattr(
        read_register,
        "find_processes_using",
        lambda dev: [(42, "optolink2mqtt run")],
    )
    interface = Mock(serial_port="/dev/ttyUSB0")

    with pytest.raises(read_register.SerialPortBusy, match="PID 42"):
        read_register.connect_exclusively(interface)
    interface.connect.assert_not_called()


#
# Report
#


def make_register(*argv):
    return read_register.build_register(parse_args(["read-register", *argv]))


def test_report_of_a_successful_read():
    reg = make_register("0x0800", "2", "signed", "0.1")
    rx = OptolinkVS2RxData(ErrorCode.Success, 0x0800, bytearray(b"\x2a\xff"))

    report = read_register.format_register_details(reg, rx, 0.05)

    assert "0x0800 (2048)" in report
    assert "2a ff" in report
    assert "Success" in report
    # 0xFF2A signed little-endian = -214, scaled by 0.1
    assert "with the given parameters: -21.4" in report
    assert "unsigned little-endian:      65322" in report
    assert "unsigned big-endian:         11007" in report
    assert "register: 0x0800" in report
    assert "signed: true" in report


def test_report_of_a_failed_read_has_no_decoded_value():
    reg = make_register("0x0800", "2")
    rx = OptolinkVS2RxData(ErrorCode.Timeout, 0x0800, bytearray())

    report = read_register.format_register_details(reg, rx, 0.05)

    assert "Timeout" in report
    assert "Decoded value" not in report


#
# End to end, against a fake VS2 device on a pseudo terminal
#


class FakeVS2Device(threading.Thread):
    """Answers the VS2 handshake and a Virtual_READ of a single register."""

    def __init__(self, master_fd: int, data: bytes):
        super().__init__(daemon=True)
        self.fd = master_fd
        self.data = data
        self.stop = False

    def run(self):
        buf = b""
        while not self.stop:
            try:
                buf += os.read(self.fd, 64)
            except OSError:
                return
            while buf:
                if buf[0] == 0x04:  # EOT
                    os.write(self.fd, b"\x05")
                    buf = buf[1:]
                elif buf.startswith(b"\x16\x00\x00"):  # START_VS2
                    os.write(self.fd, b"\x06")
                    buf = buf[3:]
                elif buf[0] == 0x41 and len(buf) >= 8:  # read request
                    addr_hi, addr_lo = buf[4], buf[5]
                    payload = (
                        bytes([0x01, 0x01, addr_hi, addr_lo, len(self.data)])
                        + self.data
                    )
                    telegram = bytes([0x41, len(payload)]) + payload
                    telegram += bytes(
                        [OptolinkVS2Protocol.calc_crc(telegram + b"\x00")]
                    )
                    os.write(self.fd, b"\x06" + telegram)
                    buf = buf[8:]
                elif buf[0] == 0x41:
                    break  # wait for the rest of the telegram
                else:
                    buf = buf[1:]


@pytest.fixture
def fake_device():
    pty = pytest.importorskip("pty")
    master, slave = pty.openpty()
    device = FakeVS2Device(master, b"\x2a\x01")
    device.start()
    yield os.ttyname(slave)
    device.stop = True
    os.close(slave)
    os.close(master)


def test_read_register_end_to_end(fake_device, capsys):
    args = parse_args(
        [
            "read-register",
            "--serial-port",
            fake_device,
            "0x0800",
            "2",
            "unsigned",
            "0.1",
        ]
    )

    assert read_register.run_read_register(args) == read_register.EXIT_OK

    out = capsys.readouterr().out
    assert fake_device in out
    assert "4800 baud, 8E2" in out
    assert "exclusive lock:      acquired" in out
    assert "2a 01" in out
    assert "with the given parameters: 29.8" in out


def test_read_register_bails_out_when_the_port_is_locked(fake_device, monkeypatch):
    # an optolink2mqtt "run" instance holds the port with an exclusive lock;
    # the /proc scan cannot see it since it is our own process
    other = OptolinkInterface(fake_device, False, 0, 0)
    other.connect()
    try:
        args = parse_args(
            ["read-register", "--serial-port", fake_device, "0x0800", "2"]
        )
        assert (
            read_register.run_read_register(args) == read_register.EXIT_SERIAL_PORT_BUSY
        )
    finally:
        other.disconnect()
