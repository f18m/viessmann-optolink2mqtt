"""
read_register.py
----------------
The "read-register" mode: reads a single register once and prints all its details,
to help reverse-engineering registers before adding them to the configuration file
Copyright (C) 2026 Francesco Montorsi

Licensed under the GNU GENERAL PUBLIC LICENSE, Version 3 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.gnu.org/licenses/gpl-3.0.html

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import argparse
import errno
import logging
import os
import sys
import termios
import time
from typing import List, Tuple

import serial

from . import datetime_bcd
from .config import Config
from .optolink_interface import OptolinkConnectionFailed, OptolinkInterface
from .optolinkvs2_protocol import OptolinkVS2RxData
from .optolinkvs2_register import OptolinkVS2Register

# exit codes of the read-register mode
EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
EXIT_INVALID_REGISTER = 4
EXIT_SERIAL_PORT_BUSY = 5
EXIT_CONNECTION_FAILED = 6
EXIT_READ_FAILED = 7

# errno values raised by pyserial when its exclusive flock() on the port fails
_LOCK_ERRNOS = (errno.EAGAIN, errno.EWOULDBLOCK)


class SerialPortBusy(Exception):
    """Raised when the serial port is already in use by another process."""


def find_processes_using(device: str, proc_dir: str = "/proc") -> List[Tuple[int, str]]:
    """
    Returns (pid, command line) of the other processes that have the given device open.
    Best effort: only works where /proc exists (Linux), and only sees the processes
    whose file descriptors this user is allowed to inspect.
    """
    if not os.path.isdir(proc_dir):
        return []
    target = os.path.realpath(device)
    own_pid = os.getpid()
    users = []
    for entry in os.listdir(proc_dir):
        if not entry.isdigit() or int(entry) == own_pid:
            continue
        fd_dir = os.path.join(proc_dir, entry, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue  # process exited, or belongs to another user
        for fd in fds:
            try:
                if os.path.realpath(os.path.join(fd_dir, fd)) == target:
                    break
            except OSError:
                continue
        else:
            continue
        try:
            with open(os.path.join(proc_dir, entry, "cmdline"), "rb") as f:
                cmdline = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            cmdline = "?"
        users.append((int(entry), cmdline))
    return users


def _is_lock_failure(e: Exception) -> bool:
    return isinstance(e, serial.SerialException) and (
        getattr(e, "errno", None) in _LOCK_ERRNOS or "exclusively lock" in str(e)
    )


def connect_exclusively(interface: OptolinkInterface) -> None:
    """
    Opens the serial port (with an exclusive lock, like the "run" mode) and initializes
    the VS2 protocol. Raises SerialPortBusy if another process is using the port, so that
    the Optolink traffic of e.g. a running optolink2mqtt instance is never disturbed.
    """
    users = find_processes_using(interface.serial_port)
    if users:
        details = ", ".join(f"PID {pid} ({cmd})" for pid, cmd in users)
        raise SerialPortBusy(
            f"serial port '{interface.serial_port}' is already open by: {details}"
        )
    try:
        interface.connect()
    except serial.SerialException as e:
        if _is_lock_failure(e):
            raise SerialPortBusy(
                f"serial port '{interface.serial_port}' is locked by another process "
                f"(e.g. optolink2mqtt running in 'run' mode): {e}"
            )
        raise


def _resolve_serial_port(args: argparse.Namespace) -> Tuple[str, bool]:
    """
    Returns the serial port and the show_received_bytes flag, from the command line
    or else from the configuration file. Raises on configuration errors.
    """
    if args.serial_port:
        return args.serial_port, args.show_received_bytes
    config = Config()
    config.load()
    optolink = config.config["optolink"]
    return (
        optolink["serial_port"],
        args.show_received_bytes or optolink["show_received_bytes"],
    )


def build_register(args: argparse.Namespace) -> OptolinkVS2Register:
    """
    Builds the register to read from the command line arguments.
    Raises ValueError if they do not describe a valid register.
    """
    return OptolinkVS2Register(
        {
            "name": f"register_0x{args.address:04x}",
            "sampling_period_seconds": 60,
            "register": args.address,
            "length": args.length,
            "signed": args.signed,
            "writable": False,
            "type": "float" if args.scale_factor != 1.0 else "int",
            "scale_factor": args.scale_factor,
            "byte_filter": args.byte_filter,
            "encoding": "little_endian",
            "formatter": None,
            "enum": None,
            "ha_discovery": None,
        },
        mqtt_base_topic="",
    )


#
# Report formatting
#


def _fmt_number(val: float) -> str:
    return f"{val:g}" if isinstance(val, float) else str(val)


def _parity_name(parity: str) -> str:
    return {
        serial.PARITY_NONE: "none",
        serial.PARITY_EVEN: "even",
        serial.PARITY_ODD: "odd",
        serial.PARITY_MARK: "mark",
        serial.PARITY_SPACE: "space",
    }.get(parity, str(parity))


def format_serial_port_details(ser: serial.Serial, interface: OptolinkInterface) -> str:
    lines = [
        "Serial port",
        f"  device:              {ser.port}"
        + (
            f" -> {os.path.realpath(ser.port)}"
            if os.path.realpath(ser.port) != ser.port
            else ""
        ),
        f"  settings:            {ser.baudrate} baud, {ser.bytesize}{str(ser.parity)[0]}{_fmt_number(ser.stopbits)}"
        f" ({ser.bytesize} data bits, {_parity_name(ser.parity)} parity, {_fmt_number(ser.stopbits)} stop bits)",
        f"  exclusive lock:      {'acquired' if ser.exclusive else 'not requested'}",
        "  VS2 protocol:        initialized",
        f"  VS2 statistics:      {interface.get_human_friendly_stats()}, "
        f"{interface.get_total_errors()} errors",
    ]
    return "\n".join(lines)


def _interpretations(data: bytes) -> List[Tuple[str, str]]:
    """
    Returns other plausible interpretations of the raw bytes, to help guessing the
    register format.
    """
    rows = []
    for order in ("little", "big"):
        if len(data) == 1 and order == "big":
            break  # same as little-endian
        u = int.from_bytes(data, byteorder=order, signed=False)
        s = int.from_bytes(data, byteorder=order, signed=True)
        suffix = "" if len(data) == 1 else f" {order}-endian"
        rows.append(
            (f"unsigned{suffix}", f"{u}  (x0.1 = {u / 10:g}, x0.01 = {u / 100:g})")
        )
        rows.append(
            (f"signed{suffix}", f"{s}  (x0.1 = {s / 10:g}, x0.01 = {s / 100:g})")
        )
    ascii_text = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in data)
    rows.append(("ASCII", f"'{ascii_text}'"))
    if len(data) == datetime_bcd.DATETIME_BCD_LENGTH:
        try:
            dt = datetime_bcd.decode(data)
            rows.append(
                (
                    "DateTimeBCD",
                    (
                        "not set"
                        if dt is None
                        else f"{dt.isoformat()} (device local time)"
                    ),
                )
            )
        except ValueError:
            pass  # not a DateTimeBCD value
    return rows


def format_register_details(
    reg: OptolinkVS2Register, rx_data: OptolinkVS2RxData, elapsed_sec: float
) -> str:
    lines = [
        "Register",
        f"  address:             0x{reg.address:04X} ({reg.address})",
        f"  length:              {reg.length} byte(s)",
        f"  type:                {reg.type}",
        f"  signed:              {reg.signed}",
        f"  scale factor:        {_fmt_number(reg.scale_factor)}",
        f"  byte filter:         {reg.byte_filter or 'none'}",
        f"  read result:         {rx_data.receive_code.name} (code {int(rx_data.receive_code)})",
        f"  read duration:       {elapsed_sec * 1000:.0f} ms",
    ]
    if not rx_data.is_successful():
        return "\n".join(lines)

    data = bytes(rx_data.data)
    lines += [
        "",
        "Raw data",
        f"  hex:                 {data.hex(' ') if data else '(empty)'}",
        "  bytes:               index  hex  unsigned  signed  binary",
    ]
    for i, b in enumerate(data):
        s = b - 256 if b > 127 else b
        lines.append(
            f"                       {i:>5}  0x{b:02X}  {b:>8}  {s:>6}  {b:08b}"
        )

    lines += [
        "",
        "Decoded value",
        f"  with the given parameters: {reg.get_value_from_rawdata(bytearray(data))}",
        "",
        "Other interpretations of the raw data",
    ]
    lines += [f"  {name + ':':<29}{value}" for name, value in _interpretations(data)]

    lines += [
        "",
        "Configuration snippet for 'registers_poll_list' (adjust name and sampling period)",
        f"  - name: register_0x{reg.address:04x}",
        "    sampling_period_seconds: 60",
        f"    register: 0x{reg.address:04X}",
        f"    length: {reg.length}",
        f"    type: {reg.type}",
        f"    signed: {str(reg.signed).lower()}",
    ]
    if reg.scale_factor != 1.0:
        lines.append(f"    scale_factor: {_fmt_number(reg.scale_factor)}")
    if reg.byte_filter:
        lines.append(f'    byte_filter: "{reg.byte_filter}"')
    return "\n".join(lines)


#
# Entry point
#


def run_read_register(args: argparse.Namespace) -> int:
    """
    Reads a single register once and prints its details on stdout. Returns the exit code.
    Logs go to stderr, so stdout carries only the report.
    """
    logging.basicConfig(level=logging.WARNING)

    try:
        reg = build_register(args)
    except ValueError as e:
        logging.error(f"Invalid register definition: {e}")
        return EXIT_INVALID_REGISTER

    try:
        serial_port, show_received_bytes = _resolve_serial_port(args)
    except Exception as e:
        logging.error(
            f"Cannot load configuration: {e}. Use --serial-port to skip the configuration file."
        )
        return EXIT_CONFIG_ERROR
    if show_received_bytes:
        # the received bytes are logged at DEBUG level
        logging.getLogger().setLevel(logging.DEBUG)

    # no reconnection: a single attempt is made
    interface = OptolinkInterface(serial_port, show_received_bytes, 0, 0)
    try:
        connect_exclusively(interface)
    except SerialPortBusy as e:
        logging.error(f"{e}. Stop it before using read-register. Aborting.")
        return EXIT_SERIAL_PORT_BUSY
    except (OptolinkConnectionFailed, serial.SerialException, termios.error) as e:
        logging.error(f"Cannot connect to the Optolink device on '{serial_port}': {e}")
        return EXIT_CONNECTION_FAILED

    try:
        started = time.monotonic()
        rx_data = interface.read_register_rawdata(reg)
        elapsed_sec = time.monotonic() - started

        print(format_serial_port_details(interface.protocol.ser, interface))
        print()
        print(format_register_details(reg, rx_data, elapsed_sec))
        sys.stdout.flush()
    except (serial.SerialException, termios.error) as e:
        logging.error(f"Serial port error while reading the register: {e}")
        return EXIT_READ_FAILED
    finally:
        interface.disconnect()

    return EXIT_OK if rx_data.is_successful() else EXIT_READ_FAILED
