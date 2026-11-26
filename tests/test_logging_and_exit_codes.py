import logging
import os
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.config import Config  # noqa: E402
from optolink2mqtt.optolink2mqtt_app import Optolink2MqttApp  # noqa: E402


@pytest.fixture
def root_logger():
    root = logging.getLogger()
    level = root.level
    handlers = list(root.handlers)
    yield root
    root.setLevel(level)
    root.handlers[:] = handlers


def apply_level(level):
    config = Config()
    config.config = {"logging": {"level": level}}
    config.apply_logging_config()


@pytest.mark.parametrize(
    "level,expected",
    [
        ("DEBUG", logging.DEBUG),
        ("INFO", logging.INFO),
        ("WARN", logging.WARNING),
        ("WARNING", logging.WARNING),
        ("ERR", logging.ERROR),
        ("ERROR", logging.ERROR),
        ("CRITICAL", logging.CRITICAL),
        ("info", logging.INFO),
    ],
)
def test_logging_level_is_applied(root_logger, level, expected):
    apply_level(level)
    assert root_logger.level == expected


def test_invalid_logging_level_falls_back_to_error(root_logger, caplog):
    apply_level("VERBOSE")
    assert root_logger.level == logging.ERROR
    assert "Invalid logging level 'VERBOSE'" in caplog.text


def test_apply_logging_config_keeps_existing_handlers(root_logger):
    handler = logging.NullHandler()
    root_logger.addHandler(handler)

    apply_level("INFO")

    assert handler in root_logger.handlers


def test_setup_returns_exit_code_when_config_cannot_be_loaded(monkeypatch):
    config = Mock()
    config.load.side_effect = FileNotFoundError("optolink2mqtt.yaml")
    config_class = Mock(return_value=config)
    config_class.get_default_config_file_name.return_value = ["optolink2mqtt.yaml"]
    monkeypatch.setattr("optolink2mqtt.optolink2mqtt_app.Config", config_class)
    monkeypatch.setattr(sys, "argv", ["optolink2mqtt"])

    assert Optolink2MqttApp().setup() == 2
