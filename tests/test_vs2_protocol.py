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

port = "/dev/ttyUSB0"
if len(sys.argv) > 1:
    port = sys.argv[1]

logging.basicConfig(level=logging.DEBUG, force=True)

ser = serial.Serial(port, baudrate=4800, bytesize=8, parity="E", stopbits=2, timeout=0)
proto = OptolinkVS2Protocol(ser, show_opto_rx=True)

try:
    if not ser.is_open:
        ser.open()
    if not proto.init_vs2():
        raise Exception("init_vs2 failed")

    logging.info(f"VS2 protocol successfully initialized on port {port}")

    # read test
    if True:
        while True:
            logging.info("Reading test datapoint 0x00F8...")
            rxdata = proto.read_datapoint_ext(0x00F8, 8)
            if rxdata.is_successful():
                logging.info(
                    f"Datapoint content is: {OptolinkVS2Protocol.readable_hex(rxdata.data)}"
                )
            else:
                logging.error(f"Error reading datapoint: code {rxdata.retcode:#02x}")
            time.sleep(0.5)

    # write test
    if False:
        buff = proto.read_datapoint(0x27D4, 1)
        currval = buff
        logging.info(
            "Niveau Ist",
            OptolinkVS2Protocol.readable_hex(buff),
            OptolinkVS2Protocol.bytesval(buff),
        )

        time.sleep(1)

        data = bytes([50])
        ret = proto.write_datapoint(0x27D4, data)
        logging.info("write succ", ret)

        time.sleep(2)

        buff = proto.read_datapoint(0x27D4, 1)
        logging.info(
            "Niveau neu",
            OptolinkVS2Protocol.readable_hex(buff),
            OptolinkVS2Protocol.bytesval(buff),
        )

        time.sleep(1)

        ret = proto.write_datapoint(0x27D4, currval)
        logging.info("write back succ", ret)

        time.sleep(2)

        buff = proto.read_datapoint(0x27D4, 1)
        logging.info(
            "Niveau read back",
            OptolinkVS2Protocol.readable_hex(buff),
            OptolinkVS2Protocol.bytesval(buff),
        )

except KeyboardInterrupt:
    logging.info("\nProgram ended.")
except Exception as e:
    logging.error(e)
finally:
    # Serial Port close
    if ser.is_open:
        logging.info("exit close")
        # re-init KW protocol
        ser.write(bytes([0x04]))
        ser.close()
