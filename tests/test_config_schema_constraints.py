import os
import sys

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.config import Config  # noqa: E402
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402

SCHEMA = os.path.realpath(SRC_DIR + "/optolink2mqtt/schema/optolink2mqtt.schema.yaml")


def load(tmp_path, mqtt_extra="", broker="    port: 1883\n", registers=None):
    if registers is None:
        registers = """
  - name: external_temperature
    sampling_period_seconds: 10
    register: 0x0101
    length: 2
"""
    text = (
        "config_version: 2\noptolink:\n  serial_port: /dev/null\n"
        "mqtt:\n  broker:\n    host: localhost\n"
        + broker
        + mqtt_extra
        + "registers_poll_list:"
        + registers
    )
    config_file = tmp_path / "optolink2mqtt.yaml"
    config_file.write_text(text)
    config = Config()
    config.load(str(config_file), SCHEMA)
    return config.config


def test_broker_port_is_optional_and_defaults_to_1883(tmp_path):
    cfg = load(tmp_path, broker="")

    assert cfg["mqtt"]["broker"]["port"] == 1883
    assert cfg["mqtt"]["broker"]["tls"] is False


@pytest.mark.parametrize("port", [0, 65536])
def test_broker_port_out_of_range_is_rejected(tmp_path, port):
    with pytest.raises(ValueError, match="port"):
        load(tmp_path, broker=f"    port: {port}\n")


@pytest.mark.parametrize("qos", [0, 1, 2])
def test_valid_qos_is_accepted(tmp_path, qos):
    assert load(tmp_path, mqtt_extra=f"  qos: {qos}\n")["mqtt"]["qos"] == qos


@pytest.mark.parametrize("qos", [-1, 3])
def test_invalid_qos_is_rejected(tmp_path, qos):
    with pytest.raises(ValueError, match="qos"):
        load(tmp_path, mqtt_extra=f"  qos: {qos}\n")


@pytest.mark.parametrize("length", [0, -1, 251])
def test_invalid_register_length_is_rejected(tmp_path, length):
    registers = f"""
  - name: r
    sampling_period_seconds: 10
    register: 0x0101
    length: {length}
"""
    with pytest.raises(ValueError, match="length"):
        load(tmp_path, registers=registers)


ENUM_REGISTER = """
  - name: mode
    sampling_period_seconds: 10
    register: 0xB000
    length: 1
    type: enum
    enum:
{entries}
"""


def test_enum_with_integer_keys_is_accepted(tmp_path):
    cfg = load(
        tmp_path,
        registers=ENUM_REGISTER.format(entries='      0: "Off"\n      0x01: "On"'),
    )

    reg = OptolinkVS2Register(cfg["registers_poll_list"][0], "prefix")
    assert reg.get_value_from_rawdata(bytearray([1])) == "On"
    assert reg.get_rawdata_from_value("Off") == bytearray([0])


@pytest.mark.parametrize(
    "entries",
    [
        # a quoted key is a string: it would never match the integer raw value
        '      "0": "Off"',
        # an unquoted On is a boolean in YAML, not a label
        "      1: On",
    ],
)
def test_enum_with_non_integer_key_or_non_string_label_is_rejected(tmp_path, entries):
    with pytest.raises(ValueError, match="enum"):
        load(tmp_path, registers=ENUM_REGISTER.format(entries=entries))


SPLIT_REGISTER = """
  - name: low_byte
    sampling_period_seconds: 10
    register: 0x0101
    length: 2
    {filter_low}
  - name: high_byte
    sampling_period_seconds: 10
    register: 0x0101
    length: 2
    {filter_high}
"""


def test_same_address_with_byte_filters_is_accepted(tmp_path):
    cfg = load(
        tmp_path,
        registers=SPLIT_REGISTER.format(
            filter_low='byte_filter: "b:0:0"', filter_high='byte_filter: "b:1:1"'
        ),
    )

    assert [r["name"] for r in cfg["registers_poll_list"]] == ["low_byte", "high_byte"]


@pytest.mark.parametrize(
    "filter_low, filter_high",
    [("", ""), ('byte_filter: "b:0:0"', "")],
)
def test_same_address_without_byte_filter_is_rejected(
    tmp_path, filter_low, filter_high
):
    with pytest.raises(ValueError, match="0x0101 is present more than once"):
        load(
            tmp_path,
            registers=SPLIT_REGISTER.format(
                filter_low=filter_low, filter_high=filter_high
            ),
        )
