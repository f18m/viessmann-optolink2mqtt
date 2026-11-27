"""
TLS to the MQTT broker must be configurable explicitly (not only implied by
port 8883), support custom CA and client certificates, and the configuration
must flag credentials that would be dropped or sent in plaintext.
"""

import logging
import os
import queue
import ssl
import sys
from unittest.mock import Mock

import pytest

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SRC_DIR = os.path.realpath(THIS_SCRIPT_DIR + "/../src")
sys.path.append(SRC_DIR)

from optolink2mqtt.config import Config  # noqa: E402
from optolink2mqtt.mqtt_client import MqttClient  # noqa: E402

CONFIG_TEMPLATE = """
config_version: 2
optolink:
  serial_port: /dev/ttyUSB0
mqtt:
  broker:
    host: localhost
{broker}
registers_poll_list: []
"""


@pytest.fixture(autouse=True)
def no_password_env(monkeypatch):
    monkeypatch.delenv("MQTT_BROKER_PASSWORD", raising=False)
    monkeypatch.delenv("MQTT_BROKER_PASSWORD_FILE", raising=False)


def load_broker_config(tmp_path, broker_lines):
    path = tmp_path / "optolink2mqtt.yaml"
    broker = "\n".join("    " + line for line in broker_lines)
    path.write_text(CONFIG_TEMPLATE.format(broker=broker), encoding="utf-8")
    config = Config()
    config.load(str(path))
    return config.config["mqtt"]["broker"]


@pytest.mark.parametrize("port,expected_tls", [(1883, False), (8883, True)])
def test_tls_defaults_to_port_8883(tmp_path, port, expected_tls):
    broker = load_broker_config(tmp_path, [f"port: {port}"])
    assert broker["tls"] is expected_tls
    assert broker["ca_certs"] is None
    assert broker["certfile"] is None
    assert broker["keyfile"] is None


def test_tls_can_be_forced_on_non_standard_port(tmp_path):
    broker = load_broker_config(
        tmp_path,
        ["port: 9883", "tls: true", "ca_certs: /etc/ca.pem", "certfile: /etc/c.pem"],
    )
    assert broker["tls"] is True
    assert broker["ca_certs"] == "/etc/ca.pem"
    assert broker["certfile"] == "/etc/c.pem"


def test_tls_can_be_disabled_on_port_8883(tmp_path):
    broker = load_broker_config(tmp_path, ["port: 8883", "tls: false"])
    assert broker["tls"] is False


def test_tls_options_without_tls_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="'tls' is false"):
        load_broker_config(tmp_path, ["port: 1883", "ca_certs: /etc/ca.pem"])


def test_keyfile_without_certfile_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="'keyfile' requires 'certfile'"):
        load_broker_config(tmp_path, ["port: 8883", "keyfile: /etc/k.pem"])


def test_password_without_username_warns(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        load_broker_config(tmp_path, ["port: 8883", "password: secret"])
    assert "will NOT be sent" in caplog.text


def test_password_without_tls_warns(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        load_broker_config(
            tmp_path, ["port: 1883", "username: user", "password: secret"]
        )
    assert "plaintext" in caplog.text
    assert "will NOT be sent" not in caplog.text


def test_credentials_over_tls_do_not_warn(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        load_broker_config(
            tmp_path, ["port: 8883", "username: user", "password: secret"]
        )
    assert caplog.text == ""


def make_client(monkeypatch):
    paho_client = Mock()
    paho_client.connect.return_value = 0
    monkeypatch.setattr(
        "optolink2mqtt.mqtt_client.paho.Client", Mock(return_value=paho_client)
    )
    client = MqttClient(
        queue.Queue(), "test", False, "optolink2mqtt/test/", "", 0, False, 5, ""
    )
    return client, paho_client


def test_connect_with_tls_on_any_port(monkeypatch):
    client, paho_client = make_client(monkeypatch)

    client.connect(
        "broker",
        9883,
        "user",
        "secret",
        tls=True,
        ca_certs="/etc/ca.pem",
        certfile="/etc/c.pem",
        keyfile="/etc/k.pem",
    )

    paho_client.tls_set.assert_called_once()
    kwargs = paho_client.tls_set.call_args.kwargs
    assert kwargs["ca_certs"] == "/etc/ca.pem"
    assert kwargs["certfile"] == "/etc/c.pem"
    assert kwargs["keyfile"] == "/etc/k.pem"
    assert kwargs["cert_reqs"] == ssl.CERT_REQUIRED
    # paho then picks ssl.PROTOCOL_TLS_CLIENT, instead of the deprecated ssl.PROTOCOL_TLS
    assert kwargs.get("tls_version") is None


@pytest.mark.parametrize("port", [1883, 8883])
def test_connect_without_tls(monkeypatch, port):
    client, paho_client = make_client(monkeypatch)

    client.connect("broker", port, None, None, tls=False)

    paho_client.tls_set.assert_not_called()
