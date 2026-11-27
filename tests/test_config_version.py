import os
import sys

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)
from optolink2mqtt.config import Config  # noqa: E402

REFERENCE_CONFIG = os.path.realpath(THIS_SCRIPT_DIR + "/../optolink2mqtt.yaml")

CONFIG_BODY = """
optolink:
  serial_port: /dev/ttyUSB0
mqtt:
  broker:
    host: localhost
registers_poll_list: []
"""


def load(tmp_path, version_line: str) -> Config:
    path = tmp_path / "optolink2mqtt.yaml"
    path.write_text(version_line + CONFIG_BODY, encoding="utf-8")
    config = Config()
    config.load(str(path))
    return config


def test_missing_config_version_is_version_1(tmp_path):
    config = load(tmp_path, "")
    assert config.config["config_version"] == 1


def test_supported_config_version_is_accepted(tmp_path):
    config = load(tmp_path, f"config_version: {Config.CONFIG_VERSION}\n")
    assert config.config["config_version"] == Config.CONFIG_VERSION


def test_newer_config_version_is_refused(tmp_path):
    newer = Config.CONFIG_VERSION + 1
    with pytest.raises(ValueError) as e:
        load(tmp_path, f"config_version: {newer}\n")
    msg = str(e.value)
    assert f"config_version {newer}" in msg
    assert "Upgrade optolink2mqtt" in msg


def test_newer_config_version_is_refused_before_schema_validation(tmp_path):
    # a newer file may use keys unknown to this release: the version error must win
    newer = Config.CONFIG_VERSION + 1
    with pytest.raises(ValueError) as e:
        load(tmp_path, f"config_version: {newer}\nsome_future_key: 1\n")
    assert "Upgrade optolink2mqtt" in str(e.value)


def test_older_config_version_points_to_the_upgrade_tool(tmp_path, monkeypatch):
    # with CONFIG_VERSION 1 no older version exists yet: simulate the next release
    monkeypatch.setattr(Config, "CONFIG_VERSION", 2)
    with pytest.raises(ValueError) as e:
        load(tmp_path, "config_version: 1\n")
    msg = str(e.value)
    assert "config_version 1" in msg
    assert Config.CONFIG_UPGRADE_URL in msg


def test_file_without_config_version_is_older_in_the_next_release(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(Config, "CONFIG_VERSION", 2)
    with pytest.raises(ValueError) as e:
        load(tmp_path, "")
    assert Config.CONFIG_UPGRADE_URL in str(e.value)


@pytest.mark.parametrize("value", ["0", "-1", "'1'", "1.5", "true", "null"])
def test_invalid_config_version_is_refused(tmp_path, value):
    with pytest.raises(ValueError) as e:
        load(tmp_path, f"config_version: {value}\n")
    assert "invalid 'config_version'" in str(e.value)


def test_reference_config_uses_the_supported_version():
    config = Config()
    config.load(REFERENCE_CONFIG)
    assert config.config["config_version"] == Config.CONFIG_VERSION
