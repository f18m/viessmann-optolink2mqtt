"""
optolink_interface.py
----------------
Optolink interface: owns the serial port and the OptolinkVS2Protocol instance
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

import logging
import time
from typing import Optional

import serial

from .optolinkvs2_protocol import OptolinkVS2Protocol, OptolinkVS2RxData
from .optolinkvs2_register import OptolinkVS2Register


class OptolinkReinitializationRequired(Exception):
    """Raised when consecutive Optolink failures require reconnecting VS2."""


class OptolinkConnectionFailed(Exception):
    """Raised when the VS2 protocol cannot be initialized."""


class OptolinkInterface:
    """
    Wraps the OptolinkVS2Protocol and implements serial port opening,
    reconnection retries and register sampling/writing.
    """

    def __init__(
        self,
        serial_port: str,
        show_received_bytes: bool,
        reconnect_period_sec: float,
        reconnect_timeout_sec: float,
        max_consecutive_failures_before_reinit: int = 3,
    ) -> None:
        self.serial_port = serial_port
        self.show_received_bytes = show_received_bytes
        self.reconnect_period_sec = reconnect_period_sec
        self.reconnect_timeout_sec = reconnect_timeout_sec
        self.max_consecutive_failures_before_reinit = (
            max_consecutive_failures_before_reinit
        )

        self.protocol = None  # instance of OptolinkVS2Protocol
        self._previous_protocol_errors = 0
        self._failed_initializations = 0
        self.reconn_attempts = 0
        self.reconn_started_at: Optional[float] = None
        self.consecutive_failures = 0

    def is_connected(self) -> bool:
        return self.protocol is not None

    def connect(self) -> bool:
        """
        Opens the serial port and initializes the VS2 protocol.
        Raises serial.SerialException (or termios.error) if the port cannot be opened.
        Raises OptolinkConnectionFailed if VS2 protocol initialization fails.
        """

        self._discard_protocol()

        # the following ctor might raise serial.SerialException (or termios.error)
        # if the port cannot be opened -- we expect the caller to invoke our
        # handle_serial_error() method to deal with it if needed.
        ser = serial.Serial(
            self.serial_port,
            baudrate=4800,
            bytesize=8,
            parity="E",
            stopbits=2,
            timeout=0,
            exclusive=True,
        )

        protocol = OptolinkVS2Protocol(ser, self.show_received_bytes)
        try:
            initialized = protocol.init_vs2()
        except BaseException:
            # release the (exclusive) serial port, or the next reconnect cannot open it
            self._close_serial(ser)
            raise
        if not initialized:
            self._close_serial(ser)
            self._failed_initializations += 1
            logging.error("Cannot initialize Optolink VS2 protocol.")
            raise OptolinkConnectionFailed("Cannot initialize Optolink VS2 protocol")

        self.protocol = protocol
        self.reconn_attempts = 0
        self.reconn_started_at = None
        self.consecutive_failures = 0
        return True

    def disconnect(self) -> None:
        """
        Closes the serial port, if open, releasing its exclusive lock.
        """
        self._discard_protocol()

    def _discard_protocol(self) -> None:
        if self.protocol is not None:
            self._previous_protocol_errors += self.protocol.get_total_errors()
            self._close_serial(self.protocol.ser)
            self.protocol = None

    @staticmethod
    def _close_serial(ser: serial.Serial) -> None:
        """
        Closes the serial port, releasing its exclusive lock. Errors are only logged:
        the port is typically being closed because it already failed.
        """
        try:
            ser.close()
        except Exception as e:
            logging.warning(f"Error while closing Optolink serial port: {e}")

    def handle_serial_error(self, e: Exception) -> Optional[float]:
        """
        Records a serial error, drops the current connection, and returns the delay
        before retrying. A timeout of zero means retry indefinitely; otherwise returns
        None when the configured reconnection timeout expires.
        """

        if self.reconnect_timeout_sec == 0:
            self.reconn_attempts += 1
            logging.error(
                f"Optolink error caught: {e}; retrying in "
                f"{self.reconnect_period_sec} sec "
                f"(reconnection attempt {self.reconn_attempts}; timeout disabled)..."
            )
            self._discard_protocol()
            return self.reconnect_period_sec

        if self.reconn_started_at is None:
            self.reconn_started_at = time.monotonic()

        elapsed_sec = time.monotonic() - self.reconn_started_at
        remaining_sec = self.reconnect_timeout_sec - elapsed_sec
        if remaining_sec <= 0:
            logging.error(
                f"Optolink error caught: {e}; reconnect timeout of "
                f"{self.reconnect_timeout_sec} sec exceeded. Aborting."
            )
            return None

        self.reconn_attempts += 1
        delay_sec = min(self.reconnect_period_sec, remaining_sec)
        logging.error(
            f"Optolink error caught: {e}; retrying in {delay_sec} sec "
            f"(reconnection attempt {self.reconn_attempts}; timeout in "
            f"{remaining_sec} sec)..."
        )
        self._discard_protocol()
        return delay_sec

    def _track_result(self, rx_data) -> None:
        """
        Counts consecutive failures and requests a reconnect after too many of them.
        """

        if rx_data.is_successful():
            self.consecutive_failures = 0
            return

        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures_before_reinit:
            logging.warning(
                f"{self.consecutive_failures} consecutive Optolink failures; requesting VS2 re-initialization..."
            )
            raise OptolinkReinitializationRequired(
                f"{self.consecutive_failures} consecutive Optolink failures"
            )

    def read_register_rawdata(self, reg: OptolinkVS2Register) -> OptolinkVS2RxData:
        """
        Reads a register from the device and returns the received telegram,
        successful or not, with its raw (undecoded) data.
        """

        rx_data = self.protocol.read_datapoint_ext(reg.address, reg.length)
        if not rx_data.is_successful():
            # NOTE that the error is already logged inside OptolinkVS2Protocol
            #      which also maintains error counters
            logging.error(
                f"Failed to read register '{reg.name}' (addr=0x{reg.address:04x}): error code {int(rx_data.receive_code)} ({rx_data.receive_code.name})"
            )
        return rx_data

    def sample_register_rawdata(self, reg: OptolinkVS2Register) -> Optional[bytearray]:
        """
        Reads a register from the device and returns its raw data, or None on failure.
        The result is counted towards the consecutive failures.
        """

        rx_data = self.read_register_rawdata(reg)
        self._track_result(rx_data)
        if not rx_data.is_successful():
            return None
        return rx_data.data

    def write_register(self, reg: OptolinkVS2Register, raw_data: bytes) -> bool:
        """
        Writes raw bytes to a register. Returns True on success.
        """

        rx_data = self.protocol.write_datapoint_ext(reg.address, raw_data)
        if rx_data.is_successful():
            self._track_result(rx_data)
            return True
        logging.error(
            f"Failed to write register '{reg.name}' (addr=0x{reg.address:04x}): error code {int(rx_data.receive_code)} ({rx_data.receive_code.name})"
        )
        self._track_result(rx_data)
        return False

    def get_total_rx_frames(self) -> int:
        return self.protocol.get_total_rx_frames() if self.protocol else 0

    def get_total_errors(self) -> int:
        current_protocol_errors = (
            self.protocol.get_total_errors() if self.protocol else 0
        )
        return (
            self._previous_protocol_errors
            + self._failed_initializations
            + current_protocol_errors
        )

    def get_human_friendly_stats(self) -> str:
        return self.protocol.get_human_friendly_stats() if self.protocol else ""
