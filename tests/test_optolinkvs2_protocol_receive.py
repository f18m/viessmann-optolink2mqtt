import os
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolinkvs2_protocol import (  # noqa: E402
    ErrorCode,
    MessageIdentifier,
    OptolinkVS2Protocol,
)

VS2_ACK = 0x06


def make_response_telegram(addr: int, data: bytes) -> bytearray:
    payload = bytes(
        [
            MessageIdentifier.ResponseMessage,
            0x01,  # Virtual_READ
            (addr >> 8) & 0xFF,
            addr & 0xFF,
            len(data),
        ]
    ) + bytes(data)
    telegram = bytearray([0x41, len(payload)]) + payload
    telegram.append(OptolinkVS2Protocol.calc_crc(telegram))
    return telegram


def receive(monkeypatch, incoming: bytes):
    monkeypatch.setattr("optolink2mqtt.optolinkvs2_protocol.time.sleep", Mock())
    ser = Mock()
    ser.read_all.side_effect = [incoming] + [b""] * 1000
    return OptolinkVS2Protocol(ser).receive_telegram(resptelegr=True, raw=False)


@pytest.mark.parametrize("trailing", [b"", b"\xff", b"\x00\x12\x34"])
def test_receive_telegram_ignores_trailing_bytes(monkeypatch, trailing):
    telegram = make_response_telegram(0x0101, b"\x2a\x01")

    rx_data = receive(monkeypatch, bytes([VS2_ACK]) + bytes(telegram) + trailing)

    assert rx_data.receive_code == ErrorCode.Success
    assert rx_data.address == 0x0101
    assert rx_data.data == bytearray(b"\x2a\x01")


def test_receive_telegram_detects_bad_crc(monkeypatch):
    telegram = make_response_telegram(0x0101, b"\x2a\x01")
    telegram[-1] ^= 0xFF

    rx_data = receive(monkeypatch, bytes([VS2_ACK]) + bytes(telegram) + b"\x00")

    assert rx_data.receive_code == ErrorCode.CRCError
