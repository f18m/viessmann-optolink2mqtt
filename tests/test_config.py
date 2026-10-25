import os
import sys

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

MINIMAL_CONFIG = """
optolink:
  serial_port: /dev/ttyUSB0
mqtt:
  broker:
    host: localhost
    port: 1883
    password: from_config
registers_poll_list: []
"""


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "optolink2mqtt.yaml"
    path.write_text(MINIMAL_CONFIG, encoding="utf-8")
    return path


def load_config(path):
    from optolink2mqtt.config import Config

    config = Config()
    config.load(str(path))
    return config


def test_mqtt_password_from_environment_overrides_config(config_file, monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_PASSWORD", "from_environment")
    monkeypatch.delenv("MQTT_BROKER_PASSWORD_FILE", raising=False)

    config = load_config(config_file)

    assert config.config["mqtt"]["broker"]["password"] == "from_environment"


def test_mqtt_password_from_file_strips_trailing_newline(
    config_file, tmp_path, monkeypatch
):
    password_file = tmp_path / "mqtt_password"
    password_file.write_text("from_file\r\n", encoding="utf-8")
    monkeypatch.delenv("MQTT_BROKER_PASSWORD", raising=False)
    monkeypatch.setenv("MQTT_BROKER_PASSWORD_FILE", str(password_file))

    config = load_config(config_file)

    assert config.config["mqtt"]["broker"]["password"] == "from_file"


def test_mqtt_password_environment_takes_precedence_over_file(
    config_file, tmp_path, monkeypatch
):
    password_file = tmp_path / "mqtt_password"
    password_file.write_text("from_file", encoding="utf-8")
    monkeypatch.setenv("MQTT_BROKER_PASSWORD", "from_environment")
    monkeypatch.setenv("MQTT_BROKER_PASSWORD_FILE", str(password_file))

    config = load_config(config_file)

    assert config.config["mqtt"]["broker"]["password"] == "from_environment"


def test_missing_mqtt_password_file_fails_config_load(
    config_file, tmp_path, monkeypatch
):
    password_file = tmp_path / "does_not_exist"
    monkeypatch.delenv("MQTT_BROKER_PASSWORD", raising=False)
    monkeypatch.setenv("MQTT_BROKER_PASSWORD_FILE", str(password_file))

    with pytest.raises(ValueError, match="Error reading MQTT broker password file"):
        load_config(config_file)
