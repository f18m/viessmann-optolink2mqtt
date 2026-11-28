"""
Tests for the register "encoding" and "formatter" attributes, and for entries sharing
the same read via "same_read_as" (issue #49).
"""

import os
import sys
from unittest.mock import Mock, call

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.config import Config  # noqa: E402
from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402
from optolink2mqtt.optolinkvs2_register import OptolinkVS2Register  # noqa: E402

SCHEMA = os.path.realpath(SRC_DIR + "/optolink2mqtt/schema/optolink2mqtt.schema.yaml")

# the 8-byte device identification block of a Vitodens 200-W, as reported in issue #49
DEVICE_IDENTIFICATION = bytearray([0x20, 0xCB, 0x04, 0x60, 0x00, 0x00, 0x01, 0x0A])


def make_register(**overrides) -> OptolinkVS2Register:
    reg = {
        "name": "device_identification",
        "sampling_period_seconds": 60,
        "register": 0x00F8,
        "length": 8,
        "signed": False,
        "writable": False,
        "scale_factor": 1.0,
        "byte_filter": None,
        "encoding": "little_endian",
        "formatter": None,
        "enum": None,
        "type": "int",
        "ha_discovery": None,
    }
    reg.update(overrides)
    return OptolinkVS2Register(reg, "prefix/")


#
# encoding
#


def test_little_endian_is_the_default_byte_order():
    reg = make_register(byte_filter="b:0:1")
    assert reg.get_value_from_rawdata(DEVICE_IDENTIFICATION) == 0xCB20


@pytest.mark.parametrize(
    "byte_filter,expected",
    [("b:0:1", 0x20CB), ("b:2:2", 0x04), ("b:3:3", 0x60), ("b:6:7", 0x010A)],
)
def test_big_endian_keeps_the_address_order(byte_filter, expected):
    reg = make_register(byte_filter=byte_filter, encoding="big_endian")
    assert reg.get_value_from_rawdata(DEVICE_IDENTIFICATION) == expected


def test_big_endian_signed_float():
    reg = make_register(
        length=2, type="float", scale_factor=0.1, signed=True, encoding="big_endian"
    )
    assert reg.get_value_from_rawdata(bytearray([0xFF, 0x9C])) == -10.0


def test_big_endian_enum():
    reg = make_register(
        length=2, type="enum", enum={0x0102: "on"}, encoding="big_endian"
    )
    assert reg.get_value_from_rawdata(bytearray([0x01, 0x02])) == "on"


def test_big_endian_write_round_trip():
    reg = make_register(length=2, writable=True, encoding="big_endian")
    rawdata = reg.get_rawdata_from_value("266")
    assert rawdata == bytearray([0x01, 0x0A])
    assert reg.get_value_from_rawdata(rawdata) == 266


def test_big_endian_write_bounds_use_the_register_byte_order():
    reg = make_register(
        length=2,
        writable=True,
        encoding="big_endian",
        ha_discovery={"name": "n", "platform": "number", "min": 0, "max": 300},
    )
    assert reg.is_within_write_bounds(reg.get_rawdata_from_value("266"))
    assert not reg.is_within_write_bounds(reg.get_rawdata_from_value("301"))


def test_invalid_encoding_is_rejected():
    with pytest.raises(ValueError, match="encoding"):
        make_register(encoding="middle_endian")


def test_datetime_bcd_rejects_big_endian():
    with pytest.raises(ValueError, match="encoding"):
        make_register(type="datetime_bcd", encoding="big_endian")


#
# formatter
#


@pytest.mark.parametrize(
    "byte_filter,formatter,expected",
    [
        ("b:0:1", "{{ '%04X' | format(x) }}", "20CB"),
        ("b:2:2", "0x{{ '%02X' | format(x) }}", "0x04"),
        ("b:4:4", "0x{{ '%02X' | format(x) }}", "0x00"),
        ("b:6:7", "0x{{ '%04X' | format(x) }}", "0x010A"),
        ("b:2:2", "{{ x * 10 }}", "40"),
        ("b:3:3", "{{ 'high' if x > 0x50 else 'low' }}", "high"),
    ],
)
def test_formatter_renders_the_decoded_value(byte_filter, formatter, expected):
    reg = make_register(
        byte_filter=byte_filter, encoding="big_endian", formatter=formatter
    )
    assert reg.get_value_from_rawdata(DEVICE_IDENTIFICATION) == expected


def test_formatter_receives_enum_labels():
    reg = make_register(
        length=1, type="enum", enum={1: "on"}, formatter="state={{ x | upper }}"
    )
    assert reg.get_value_from_rawdata(bytearray([1])) == "state=ON"


def test_formatter_receives_scaled_floats():
    reg = make_register(
        length=2, type="float", scale_factor=0.1, formatter="{{ '%.1f' | format(x) }}"
    )
    assert reg.get_value_from_rawdata(bytearray([0xD7, 0x00])) == "21.5"


@pytest.mark.parametrize(
    "formatter,match",
    [
        ("{{ x ", "invalid formatter"),  # syntax error
        ("{{ x | | int }}", "invalid formatter"),  # the typo in the issue example
        ("{{ x | no_such_filter }}", "invalid formatter"),
        ("{{ y }}", "undefined variable"),
    ],
)
def test_invalid_formatter_is_rejected_at_startup(formatter, match):
    with pytest.raises(ValueError, match=match):
        make_register(formatter=formatter)


def test_formatter_on_writable_register_is_rejected():
    with pytest.raises(ValueError, match="writable"):
        make_register(writable=True, formatter="{{ x }}")


def test_formatter_failing_at_runtime_returns_none(caplog):
    # a string format applied to an integer: only detectable when rendering
    reg = make_register(length=1, formatter="{{ '%s %s' | format(x) }}")
    assert reg.get_value_from_rawdata(bytearray([1])) is None
    assert "formatter" in caplog.text


def test_formatter_cannot_escape_the_sandbox(caplog):
    reg = make_register(length=1, formatter="{{ x.__class__.__mro__ }}")
    assert reg.get_value_from_rawdata(bytearray([1])) is None


def test_formatter_is_not_applied_to_undecodable_values():
    reg = make_register(type="datetime_bcd", formatter="date: {{ x }}")
    assert reg.get_value_from_rawdata(bytearray([0xFF] * 8)) is None


#
# configuration: same_read_as, defaults and coherency checks
#

CONFIG_TEMPLATE = """
config_version: 2
optolink:
  serial_port: /dev/null
mqtt:
  broker:
    host: localhost
  publish_topic_prefix: prefix
registers_poll_list:
{registers}
"""

DEVICE_IDENTIFICATION_CONFIG = """
  - name: device_code
    sampling_period_seconds: 3600
    register: 0x00F8
    length: 8
    byte_filter: "b:0:1"
    encoding: big_endian
    formatter: "{{ '%04X' | format(x) }}"
    ha_discovery:
      name: Device code
      platform: sensor
  - name: hardware_index
    sampling_period_seconds: 3600
    same_read_as: device_code
    byte_filter: "b:2:2"
    formatter: "0x{{ '%02X' | format(x) }}"
  - name: developer_version
    sampling_period_seconds: 3600
    same_read_as: device_code
    byte_filter: "b:6:7"
    encoding: big_endian
    formatter: "0x{{ '%04X' | format(x) }}"
  - name: outside_temperature
    sampling_period_seconds: 60
    register: 0x0800
    length: 2
    type: float
    scale_factor: 0.1
"""


def write_config(tmp_path, registers: str) -> str:
    config_file = tmp_path / "optolink2mqtt.yaml"
    config_file.write_text(CONFIG_TEMPLATE.format(registers=registers))
    return str(config_file)


def load_config(tmp_path, registers: str) -> Config:
    config = Config()
    config.load(write_config(tmp_path, registers), SCHEMA)
    return config


def test_same_read_as_copies_register_and_length(tmp_path):
    regs = load_config(tmp_path, DEVICE_IDENTIFICATION_CONFIG).config[
        "registers_poll_list"
    ]

    assert [(r["name"], r["register"], r["length"]) for r in regs] == [
        ("device_code", 0x00F8, 8),
        ("hardware_index", 0x00F8, 8),
        ("developer_version", 0x00F8, 8),
        ("outside_temperature", 0x0800, 2),
    ]
    # each entry keeps its own decoding attributes
    assert regs[1]["encoding"] == "little_endian"
    assert regs[2]["encoding"] == "big_endian"


def test_new_register_keys_have_defaults(tmp_path):
    reg = load_config(tmp_path, DEVICE_IDENTIFICATION_CONFIG).config[
        "registers_poll_list"
    ][3]

    assert reg["encoding"] == "little_endian"
    assert reg["formatter"] is None
    assert reg["same_read_as"] is None


def test_formatted_sensor_gets_no_default_state_class(tmp_path):
    # a formatter may produce a non-numeric string, which HA refuses for measurements
    reg = load_config(tmp_path, DEVICE_IDENTIFICATION_CONFIG).config[
        "registers_poll_list"
    ][0]

    assert "state_class" not in reg["ha_discovery"]


@pytest.mark.parametrize(
    "registers,match",
    [
        (
            """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
""",
            "has no 'length'",
        ),
        (
            """
  - name: a
    sampling_period_seconds: 60
""",
            "has no 'register' and no 'length'",
        ),
        (
            """
  - name: a
    sampling_period_seconds: 60
    same_read_as: missing
""",
            "no entry has that name",
        ),
        (
            """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 8
    byte_filter: "b:0:0"
  - name: b
    sampling_period_seconds: 60
    same_read_as: a
    register: 0x00F8
    byte_filter: "b:1:1"
""",
            "also 'register' or 'length'",
        ),
        (
            """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 8
    byte_filter: "b:0:0"
  - name: b
    sampling_period_seconds: 60
    same_read_as: a
    byte_filter: "b:1:1"
  - name: c
    sampling_period_seconds: 60
    same_read_as: b
    byte_filter: "b:2:2"
""",
            "must name an entry that defines",
        ),
        (
            """
  - name: a
    sampling_period_seconds: 60
    same_read_as: a
""",
            "must name an entry that defines",
        ),
        (
            """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 8
    byte_filter: "b:0:0"
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 8
    byte_filter: "b:1:1"
  - name: b
    sampling_period_seconds: 60
    same_read_as: a
    byte_filter: "b:2:2"
""",
            "2 entries have that name",
        ),
        (
            # entries sharing a read must share the sampling period
            """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 8
    byte_filter: "b:0:0"
  - name: b
    sampling_period_seconds: 3600
    same_read_as: a
    byte_filter: "b:1:1"
""",
            r"same 'sampling_period_seconds' \(found \[60, 3600\]\)",
        ),
        (
            # same address and length without same_read_as is a shared read too
            """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 8
    byte_filter: "b:0:0"
  - name: b
    sampling_period_seconds: 30
    register: 0x00F8
    length: 8
    byte_filter: "b:1:1"
""",
            "same 'sampling_period_seconds'",
        ),
        (
            # the existing rule still applies: duplicates need a byte_filter
            """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 8
  - name: b
    sampling_period_seconds: 60
    same_read_as: a
""",
            "every entry for that address has a 'byte_filter'",
        ),
        (
            """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 8
    encoding: middle_endian
""",
            "does not conform to schema",
        ),
    ],
)
def test_incoherent_register_definitions_are_rejected(tmp_path, registers, match):
    with pytest.raises(ValueError, match=match):
        load_config(tmp_path, registers)


def test_same_address_with_different_lengths_and_periods_is_accepted(tmp_path):
    regs = load_config(
        tmp_path,
        """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 8
    byte_filter: "b:0:0"
  - name: b
    sampling_period_seconds: 30
    register: 0x00F8
    length: 2
    byte_filter: "b:1:1"
""",
    ).config["registers_poll_list"]
    assert len(regs) == 2


def test_reference_config_is_valid():
    config = Config()
    config.load(os.path.realpath(THIS_SCRIPT_DIR + "/../optolink2mqtt.yaml"), SCHEMA)
    regs = {r["name"]: r for r in config.config["registers_poll_list"]}
    assert regs["device_hardware_index"]["register"] == 0x00F8
    assert regs["device_hardware_index"]["length"] == 8


#
# app: one read per group of entries sharing the same address and length
#


def setup_app(monkeypatch, tmp_path, registers: str) -> Optolink2MqttApp:
    monkeypatch.setenv("OPTOLINK2MQTT_CONFIG", write_config(tmp_path, registers))
    monkeypatch.setenv("OPTOLINK2MQTT_CONFIGSCHEMA", SCHEMA)
    monkeypatch.setattr("optolink2mqtt.optolink2mqtt_app.EnhancedMqttClient", Mock())
    monkeypatch.setattr(
        Optolink2MqttApp, "get_embedded_version", staticmethod(lambda: "test")
    )
    monkeypatch.setattr(sys, "argv", ["optolink2mqtt"])
    # setup() would set the level of the root logger, leaking it into other tests
    monkeypatch.setattr(Config, "apply_logging_config", lambda self: None)
    app = Optolink2MqttApp()
    assert app.setup() == 0
    app.optolink_interface = Mock()
    app.enhanced_mqtt_client = Mock()
    return app


def test_shared_register_is_read_once_and_published_for_each_entry(
    monkeypatch, tmp_path
):
    app = setup_app(monkeypatch, tmp_path, DEVICE_IDENTIFICATION_CONFIG)
    app.optolink_interface.sample_register_rawdata.side_effect = lambda reg: (
        DEVICE_IDENTIFICATION if reg.address == 0x00F8 else b"\xd7\x00"
    )

    app._sample_all_registers()

    read_addresses = [
        c.args[0].address
        for c in app.optolink_interface.sample_register_rawdata.call_args_list
    ]
    assert sorted(read_addresses) == [0x00F8, 0x0800]
    app.enhanced_mqtt_client.publish.assert_has_calls(
        [
            call("prefix/device_code", "20CB"),
            call("prefix/hardware_index", "0x04"),
            call("prefix/developer_version", "0x010A"),
            call("prefix/outside_temperature", 21.5),
        ],
        any_order=True,
    )
    assert app.enhanced_mqtt_client.publish.call_count == 4


def test_one_timer_per_shared_read(monkeypatch, tmp_path):
    app = setup_app(monkeypatch, tmp_path, DEVICE_IDENTIFICATION_CONFIG)

    timers = [
        e for e in app.scheduler.queue if e.action == Optolink2MqttApp.on_schedule_timer
    ]
    groups = sorted([r.name for r in e.argument[1]] for e in timers)
    assert groups == [
        ["device_code", "hardware_index", "developer_version"],
        ["outside_temperature"],
    ]


def test_failed_shared_read_publishes_nothing(monkeypatch, tmp_path):
    app = setup_app(monkeypatch, tmp_path, DEVICE_IDENTIFICATION_CONFIG)
    app.optolink_interface.sample_register_rawdata.return_value = None

    app._sample_all_registers()

    app.enhanced_mqtt_client.publish.assert_not_called()
    app.enhanced_mqtt_client.publish_status_metrics.assert_called()


def test_entry_failing_to_format_does_not_block_the_others(monkeypatch, tmp_path):
    app = setup_app(
        monkeypatch,
        tmp_path,
        """
  - name: a
    sampling_period_seconds: 60
    register: 0x00F8
    length: 2
    byte_filter: "b:0:0"
    formatter: "{{ '%s %s' | format(x) }}"
  - name: b
    sampling_period_seconds: 60
    same_read_as: a
    byte_filter: "b:1:1"
""",
    )
    app.optolink_interface.sample_register_rawdata.return_value = bytearray([1, 2])

    app._sample_all_registers()

    app.enhanced_mqtt_client.publish.assert_called_once_with("prefix/b", 2)


def test_write_reads_back_the_whole_shared_read(monkeypatch, tmp_path):
    app = setup_app(
        monkeypatch,
        tmp_path,
        """
  - name: mode
    sampling_period_seconds: 60
    register: 0x2000
    length: 2
    byte_filter: "b:0:1"
    writable: true
  - name: mode_high_byte
    sampling_period_seconds: 60
    same_read_as: mode
    byte_filter: "b:1:1"
""",
    )
    app.scheduler = Mock()
    mode = app.register_list_by_cmd_topic["prefix/mode/set"]

    app._process_received_mqtt_message(
        Mock(topic=mode.get_mqtt_command_topic(), payload=b"258")
    )

    app.optolink_interface.write_register.assert_called_once()
    args = app.scheduler.enter.call_args.args
    assert args[2] == app._sample_read_group
    assert [r.name for r in args[3][0]] == ["mode", "mode_high_byte"]
