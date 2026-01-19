#!/usr/bin/env python3

import sys
import time
import serial
import os
import logging

# load most updated code living in the parent dir ../src/optolink2mqtt
THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)
from optolink2mqtt.optolinkvs2_protocol import OptolinkVS2Protocol  # noqa: E402

# --------------------
# main for test only
# --------------------

PORT = "/dev/ttyUSB0"
logging.basicConfig(level=logging.DEBUG, force=True)


class OptolinkVS2ProtocolTest:

    def is_serial_port_avail():
        if os.path.isfile(PORT):
            return True
        else:
            return False

    def test_datapoint_read(self):
        if not OptolinkVS2ProtocolTest.is_serial_port_avail():
            # only execute this test if the serial port is available
            return

        ser = serial.Serial(
            PORT, baudrate=4800, bytesize=8, parity="E", stopbits=2, timeout=0
        )
        proto = OptolinkVS2Protocol(ser, show_opto_rx=True)
        try:
            if not ser.is_open:
                ser.open()
            if not proto.init_vs2():
                raise Exception("init_vs2 failed")

            logging.info(f"VS2 protocol successfully initialized on port {PORT}")

            # read test
            i = 0
            while i < 4:
                logging.info("Reading test datapoint 0x00F8...")
                rxdata = proto.read_datapoint_ext(0x00F8, 8)
                if rxdata.is_successful():
                    logging.info(f"Datapoint content is: {rxdata.data.hex()}")
                else:
                    logging.error(
                        f"Error reading datapoint: code {rxdata.retcode:#02x}"
                    )
                time.sleep(0.5)
                i += 1
        except Exception as e:
            logging.error(e)
        finally:
            if ser.is_open:
                logging.info("exit close")
                # re-init KW protocol
                ser.write(bytes([0x04]))
                ser.close()
