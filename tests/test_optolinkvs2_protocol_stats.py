import os
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.optolinkvs2_protocol import (  # noqa: E402
    ErrorCode,
    OptolinkVS2Protocol,
)


def make_protocol_with_failing_writes() -> OptolinkVS2Protocol:
    ser = Mock()
    ser.write.return_value = 0  # nothing written: WriteFailure
    return OptolinkVS2Protocol(ser)


@pytest.mark.parametrize(
    "request_fn",
    [
        lambda p: p.read_datapoint_ext(0x0101, 2),
        lambda p: p.write_datapoint_ext(0x0101, b"\x01"),
        lambda p: p.do_request(1, 0x0101, 2),
    ],
)
def test_write_failure_is_counted(request_fn):
    protocol = make_protocol_with_failing_writes()

    rx_data = request_fn(protocol)

    assert rx_data.receive_code == ErrorCode.WriteFailure
    assert protocol.get_stats()[ErrorCode.WriteFailure] == 1
    assert protocol.get_total_errors() == 1


def test_every_error_code_is_counted_in_totals():
    protocol = OptolinkVS2Protocol(Mock())
    stats = protocol.get_stats()
    for code in range(ErrorCode.Success, ErrorCode.LastValue + 1):
        stats[code] = 1

    num_rx_errors = ErrorCode.LastRXError - ErrorCode.FirstRXError + 1
    num_tx_errors = ErrorCode.LastTXError - ErrorCode.FirstTXError + 1

    # Timeout (the last RX error) must be included
    assert protocol.get_total_rx_frames() == 1 + num_rx_errors
    # Timeout and WriteFailure (the last TX error) must be included
    assert protocol.get_total_errors() == num_rx_errors + num_tx_errors
