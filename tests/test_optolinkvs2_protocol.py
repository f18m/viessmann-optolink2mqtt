#!/usr/bin/env python3

"""
Hardware-in-the-loop test: talks to a real Viessmann device through an Optolink
adapter. It is skipped unless the serial port is given explicitly, e.g.:

    OPTOLINK2MQTT_TEST_SERIAL_PORT=/dev/ttyUSB0 pytest tests/test_optolinkvs2_protocol.py

The tests in test_optolinkvs2_protocol_*.py cover the protocol with a mocked port.
"""

import os
import sys

import pytest
import serial

# load most updated code living in the parent dir ../src/optolink2mqtt
THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)
from optolink2mqtt.optolinkvs2_protocol import OptolinkVS2Protocol  # noqa: E402

PORT = os.environ.get("OPTOLINK2MQTT_TEST_SERIAL_PORT")

# device identification: present on every VS2 device
DEVICE_IDENT_ADDRESS = 0x00F8
DEVICE_IDENT_LENGTH = 8


@pytest.mark.skipif(
    not PORT, reason="set OPTOLINK2MQTT_TEST_SERIAL_PORT to run against a real device"
)
def test_datapoint_read():
    assert os.path.exists(PORT), f"serial port {PORT} does not exist"

    ser = serial.Serial(
        PORT, baudrate=4800, bytesize=8, parity="E", stopbits=2, timeout=0
    )
    proto = OptolinkVS2Protocol(ser, show_opto_rx=True)
    try:
        assert proto.init_vs2(), f"VS2 protocol initialization failed on {PORT}"

        for _ in range(4):
            rxdata = proto.read_datapoint_ext(DEVICE_IDENT_ADDRESS, DEVICE_IDENT_LENGTH)
            assert rxdata.is_successful(), (
                f"reading datapoint 0x{DEVICE_IDENT_ADDRESS:04X} failed with "
                f"{rxdata.receive_code!r}"
            )
            assert len(rxdata.data) == DEVICE_IDENT_LENGTH
    finally:
        # re-init KW protocol, so other tools can talk to the device afterwards
        ser.write(bytes([0x04]))
        ser.close()
