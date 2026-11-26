import os
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolinkvs2_protocol import (  # noqa: E402
    MAX_DATA_LEN,
    ErrorCode,
    MessageIdentifier,
    OptolinkVS2Protocol,
)

VS2_ACK = 0x06


def make_telegram(msgid: int, addr: int, data: bytes) -> bytes:
    payload = bytes([msgid, 0x01, (addr >> 8) & 0xFF, addr & 0xFF, len(data)]) + bytes(
        data
    )
    telegram = bytearray([0x41, len(payload)]) + payload
    telegram.append(OptolinkVS2Protocol.calc_crc(telegram))
    return bytes([VS2_ACK]) + bytes(telegram)


def make_protocol(monkeypatch, incoming: bytes) -> OptolinkVS2Protocol:
    monkeypatch.setattr("optolink2mqtt.optolinkvs2_protocol.time.sleep", Mock())
    ser = Mock()
    ser.write.side_effect = len
    ser.read_all.side_effect = [incoming] + [b""] * 1000
    return OptolinkVS2Protocol(ser)


def test_read_accepts_response_for_requested_address(monkeypatch):
    proto = make_protocol(
        monkeypatch, make_telegram(MessageIdentifier.ResponseMessage, 0x0800, b"\x2a")
    )

    rx_data = proto.read_datapoint_ext(0x0800, 1)

    assert rx_data.receive_code == ErrorCode.Success
    assert rx_data.data == bytearray(b"\x2a")


@pytest.mark.parametrize(
    "request_fn",
    [
        lambda p: p.read_datapoint_ext(0x0800, 1),
        lambda p: p.write_datapoint_ext(0x0800, b"\x2a"),
        lambda p: p.do_request(1, 0x0800, 1),
    ],
)
def test_response_for_another_address_is_rejected(monkeypatch, request_fn):
    # e.g. a late response to a previous request that timed out
    proto = make_protocol(
        monkeypatch, make_telegram(MessageIdentifier.ResponseMessage, 0x0802, b"\x2a")
    )

    rx_data = request_fn(proto)

    assert rx_data.receive_code == ErrorCode.AddressMismatch
    assert not rx_data.is_successful()
    assert proto.get_stats()[ErrorCode.AddressMismatch] == 1
    assert proto.get_total_errors() == 1


@pytest.mark.parametrize(
    "msgid", [MessageIdentifier.RequestMessage, MessageIdentifier.UNACKDMessage]
)
def test_telegram_that_is_not_a_response_is_rejected(monkeypatch, msgid):
    proto = make_protocol(monkeypatch, make_telegram(msgid, 0x0800, b"\x2a"))

    rx_data = proto.read_datapoint_ext(0x0800, 1)

    assert rx_data.receive_code == ErrorCode.MessageIdError
    assert proto.get_stats()[ErrorCode.MessageIdError] == 1


def test_error_message_is_still_reported_as_such(monkeypatch):
    proto = make_protocol(
        monkeypatch, make_telegram(MessageIdentifier.ErrorMessage, 0x0800, b"\x2a")
    )

    assert proto.read_datapoint_ext(0x0800, 1).receive_code == ErrorCode.ErrorMessage


@pytest.mark.parametrize(
    "request_fn",
    [
        lambda p: p.read_datapoint_ext(0x0800, MAX_DATA_LEN + 1),
        lambda p: p.read_datapoint_ext(0x0800, -1),
        lambda p: p.read_datapoint_ext(0x10000, 1),
        lambda p: p.write_datapoint_ext(0x0800, b"\x00" * (MAX_DATA_LEN + 1)),
        lambda p: p.write_datapoint_ext(-1, b"\x00"),
        lambda p: p.do_request(1, 0x0800, 256),
        lambda p: p.do_request(2, 0x0800, 1, b"\x00" * (MAX_DATA_LEN + 1)),
    ],
)
def test_request_that_cannot_be_encoded_is_not_sent(monkeypatch, request_fn):
    proto = make_protocol(monkeypatch, b"")

    rx_data = request_fn(proto)

    assert rx_data.receive_code == ErrorCode.InvalidRequest
    proto.ser.write.assert_not_called()
    assert proto.get_stats()[ErrorCode.InvalidRequest] == 1
    assert proto.get_total_errors() == 1


def test_largest_encodable_request_is_sent(monkeypatch):
    proto = make_protocol(monkeypatch, b"")

    proto.write_datapoint_ext(0xFFFF, b"\x00" * MAX_DATA_LEN)

    sent = proto.ser.write.call_args.args[0]
    assert sent[1] == 0xFF
    assert len(sent) == MAX_DATA_LEN + 8
