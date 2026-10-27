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
import serial

from .optolinkvs2_protocol import OptolinkVS2Protocol
from .optolinkvs2_register import OptolinkVS2Register


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
        self.reconn_attempts = 0
        self.consecutive_failures = 0

    def is_connected(self) -> bool:
        return self.protocol is not None

    def connect(self) -> bool:
        """
        Opens the serial port and initializes the VS2 protocol.
        Raises serial.SerialException (or termios.error) if the port cannot be opened.
        Returns False if the VS2 protocol initialization fails.
        """

        self.protocol = None
        ser = serial.Serial(
            self.serial_port,
            baudrate=4800,
            bytesize=8,
            parity="E",
            stopbits=2,
            timeout=0,
            exclusive=True,
        )

        protocol = OptolinkVS2Protocol(
            ser,
            None,  # serial port to forward data to a Vitoconnect
            self.show_received_bytes,
        )
        if not protocol.init_vs2():
            logging.error("Cannot initialize Optolink VS2 protocol.")
            return False

        self.protocol = protocol
        self.reconn_attempts = 0
        self.consecutive_failures = 0
        return True

    def handle_serial_error(self, e: Exception) -> bool:
        """
        To be invoked when a serial port error is caught: drops the current connection,
        sleeps for the reconnection period and tells whether a new attempt must be done.
        Returns False when the maximum number of reconnection attempts has been exceeded.
        """

        max_attempts = max(
            1, int(self.reconnect_timeout_sec / self.reconnect_period_sec)
        )
        self.reconn_attempts += 1
        if self.reconn_attempts > max_attempts:
            logging.error(
                f"serial port error caught: {e}; giving up after {max_attempts} reconnection attempts. Aborting."
            )
            return False
        logging.error(
            f"serial port error caught: {e}, sleeping for {self.reconnect_period_sec} sec "
            f"(reconnection attempt {self.reconn_attempts}/{max_attempts})..."
        )
        self.protocol = None
        time.sleep(self.reconnect_period_sec)
        return True

    def _track_result(self, rx_data) -> None:
        """
        Counts consecutive failures; after too many of them (e.g. the heat pump was
        power-cycled and lost the VS2 protocol state) the VS2 protocol is initialized again.
        """

        if rx_data.is_successful():
            self.consecutive_failures = 0
            return

        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures_before_reinit:
            logging.warning(
                f"{self.consecutive_failures} consecutive Optolink failures; re-initializing VS2 protocol..."
            )
            if self.protocol.init_vs2():
                self.consecutive_failures = 0

    def sample_register(self, reg: OptolinkVS2Register):
        """
        Reads a register from the device and returns its value, or None on failure.
        """

        rx_data = self.protocol.read_datapoint_ext(reg.address, reg.length)
        self._track_result(rx_data)
        if not rx_data.is_successful():
            # NOTE that the error is already logged inside OptolinkVS2Protocol
            #      which also maintains error counters
            logging.error(
                f"Failed to read register '{reg.name}' (addr=0x{reg.address:04x}): error code {int(rx_data.receive_code)} ({rx_data.receive_code.name})"
            )
            return None
        return reg.get_value_from_rawdata(rx_data.data)

    def write_register(self, reg: OptolinkVS2Register, raw_data: bytes) -> bool:
        """
        Writes raw bytes to a register. Returns True on success.
        """

        rx_data = self.protocol.write_datapoint_ext(reg.address, raw_data)
        self._track_result(rx_data)
        if rx_data.is_successful():
            return True
        logging.error(
            f"Failed to write register '{reg.name}' (addr=0x{reg.address:04x}): error code {int(rx_data.receive_code)} ({rx_data.receive_code.name})"
        )
        return False

    def get_total_rx_frames(self) -> int:
        return self.protocol.get_total_rx_frames() if self.protocol else 0

    def get_total_errors(self) -> int:
        return self.protocol.get_total_errors() if self.protocol else 0

    def get_human_friendly_stats(self) -> str:
        return self.protocol.get_human_friendly_stats() if self.protocol else ""
