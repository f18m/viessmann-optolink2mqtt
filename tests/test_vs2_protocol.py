#!/usr/bin/env python

import sys
import time
import serial
from optolink2mqtt.optolinkvs2 import OptolinkVS2Protocol  # assumes you have the wheel installed

# --------------------
# main for test only
# --------------------
port = "/dev/ttyUSB0"  #'COM1'
if len(sys.argv) > 1:
    port = sys.argv[1]

ser = serial.Serial(port, baudrate=4800, bytesize=8, parity="E", stopbits=2, timeout=0)
proto = OptolinkVS2Protocol(ser)

try:
    if not ser.is_open:
        ser.open()
    if not proto.init_vs2():
        raise Exception("init_vs2 failed.")

    # read test
    if True:
        while True:
            buff = proto.read_datapoint(0x00F8, 8)
            print("0x00f8", OptolinkVS2Protocol.bbbstr(buff))
            time.sleep(0.1)

    # write test
    if False:
        buff = proto.read_datapoint(0x27D4, 1)
        currval = buff
        print(
            "Niveau Ist",
            OptolinkVS2Protocol.bbbstr(buff),
            OptolinkVS2Protocol.bytesval(buff),
        )

        time.sleep(1)

        data = bytes([50])
        ret = proto.write_datapoint(0x27D4, data)
        print("write succ", ret)

        time.sleep(2)

        buff = proto.read_datapoint(0x27D4, 1)
        print(
            "Niveau neu",
            OptolinkVS2Protocol.bbbstr(buff),
            OptolinkVS2Protocol.bytesval(buff),
        )

        time.sleep(1)

        ret = proto.write_datapoint(0x27D4, currval)
        print("write back succ", ret)

        time.sleep(2)

        buff = proto.read_datapoint(0x27D4, 1)
        print("Niveau read back", utils.bbbstr(buff), bytesval(buff))

except KeyboardInterrupt:
    print("\nProgram ended.")
except Exception as e:
    print(e)
finally:
    # Serial Port close
    if ser.is_open:
        print("exit close")
        # re-init KW protocol
        ser.write(bytes([0x04]))
        ser.close()
