import os
import sys
from unittest.mock import Mock, call

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolinkvs2_protocol import (  # noqa: E402
    ErrorCode,
    OptolinkVS2Protocol,
)

EOT = bytes([0x04])
ENQ = b"\x05"
VS2_ACK = b"\x06"
START_VS2 = bytes([0x16, 0x00, 0x00])


def make_protocol(monkeypatch, read=(), read_all=()):
    monkeypatch.setattr("optolink2mqtt.optolinkvs2_protocol.time.sleep", Mock())
    ser = Mock()
    ser.write.side_effect = len
    ser.read.side_effect = list(read) + [b""] * 100
    ser.read_all.side_effect = list(read_all) + [b""] * 1000
    return OptolinkVS2Protocol(ser), ser


def written(ser):
    return [c.args[0] for c in ser.write.call_args_list]


#
# init_vs2() handshake: EOT -> wait ENQ -> START_VS2 -> wait ACK
#


def test_init_vs2_succeeds_after_enq_and_ack(monkeypatch):
    proto, ser = make_protocol(monkeypatch, read=[b"", ENQ, b"", VS2_ACK])

    assert proto.init_vs2() is True
    assert written(ser) == [EOT, START_VS2]
    assert ser.reset_input_buffer.call_count == 2


def test_init_vs2_fails_without_enq(monkeypatch):
    proto, ser = make_protocol(monkeypatch)

    assert proto.init_vs2() is False
    # START_VS2 is never sent if the device does not answer the EOT
    assert written(ser) == [EOT]


def test_init_vs2_fails_without_ack(monkeypatch):
    proto, ser = make_protocol(monkeypatch, read=[ENQ, b"\x15"])

    assert proto.init_vs2() is False
    assert written(ser) == [EOT, START_VS2]


#
# Telegram encoding: STX, length, msg id, function code, address, block length,
# [data], CRC = sum of the bytes from the length to the last data byte, mod 256
#


def test_read_request_telegram_encoding(monkeypatch):
    response = VS2_ACK + bytes.fromhex("41 07 01 01 08 00 02 2a 01 3e")
    proto, ser = make_protocol(monkeypatch, read_all=[response])

    rxdata = proto.read_datapoint_ext(0x0800, 2)

    # the well-known example telegram for reading 2 bytes at 0x0800
    assert written(ser) == [bytearray.fromhex("41 05 00 01 08 00 02 10")]
    assert rxdata.receive_code == ErrorCode.Success
    assert rxdata.address == 0x0800
    assert rxdata.data == bytearray(b"\x2a\x01")


def test_write_request_telegram_encoding(monkeypatch):
    response = VS2_ACK + bytes.fromhex("41 05 01 02 23 23 01 4f")
    proto, ser = make_protocol(monkeypatch, read_all=[response])

    rxdata = proto.write_datapoint_ext(0x2323, b"\x01")

    assert written(ser) == [bytearray.fromhex("41 06 00 02 23 23 01 01 50")]
    assert rxdata.receive_code == ErrorCode.Success
    assert ser.method_calls[:2] == [
        call.reset_input_buffer(),
        call.write(bytearray.fromhex("41 06 00 02 23 23 01 01 50")),
    ]


def test_nack_response_is_reported(monkeypatch):
    proto, _ = make_protocol(monkeypatch, read_all=[b"\x15"])

    rxdata = proto.write_datapoint_ext(0x2323, b"\x01")

    assert rxdata.receive_code == ErrorCode.NACK
    assert proto.get_total_errors() == 1
