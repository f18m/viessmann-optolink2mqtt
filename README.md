[![GitHub Tag](https://img.shields.io/github/v/tag/f18m/viessmann-optolink2mqtt)](https://github.com/f18m/viessmann-optolink2mqtt/releases)
[![PyPI - Version](https://img.shields.io/pypi/v/viessmann-optolink2mqtt)](https://pypi.org/project/viessmann-optolink2mqtt/)

# viessmann-optolink2mqtt

<div align="center">

⭐ If you find this App useful, please star this repo - it helps others discover the project! ⭐

</div>

Open-source [MQTT](https://en.wikipedia.org/wiki/MQTT) bridge for [Viessmann](https://en.wikipedia.org/wiki/Viessmann) heating systems using the Optolink interface.

This project connects a [Viessmann](https://en.wikipedia.org/wiki/Viessmann) device such as a heat pump or gas boiler to a local [MQTT](https://en.wikipedia.org/wiki/MQTT) broker, allowing you to read live telemetry, control writable registers, and integrate everything into Home Assistant or any other MQTT-capable automation stack without sending data to a vendor cloud.

> [!IMPORTANT]
> This project is an independent work and is not associated with, sponsored by, or connected to the Viessmann company in any manner. Viessmann and all related trademarks, product names, and device names are trademarks or registered trademarks of Viessmann and remain the exclusive property of Viessmann.

## Table of contents

- [What is Optolink?](#what-is-optolink)
- [Architecture](#architecture)
- [Hardware requirements](#hardware-requirements)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Serial port naming](#serial-port-naming)
- [Home Assistant integration](#home-assistant-integration)
- [Labelling the hardware](#labelling-the-hardware)
- [Roadmap](#roadmap)
- [Related projects](#related-projects)

## 🧩 What is Optolink?

Some Viessmann devices, especially those manufactured before roughly 2014, expose an optical interface called Optolink for communication with third-party tools.

This interface is normally located in the Vitotronic panel and is officially intended for use with the VitoConnect device. But it also allows advanced users to read and write registers on the heating system to collect telemetry such as temperatures and component states, and to change settings such as heating mode or target temperatures.

This project lets you connect to that interface and publish the data to a local MQTT broker, keeping the information on your own network instead of routing it through a vendor cloud.

## 🏗️ Architecture

<img title="Setup" alt="Architecture" src="docs/architecture.png">

## 🛠️ Hardware requirements

- A small single-board computer (SBC) capable of running Python and exposing a USB-A port if you use the original Viessmann Optolink USB cable. A typical choice is a [Raspberry Pi](https://www.raspberrypi.com/products/raspberry-pi-5/); the author has also used an [OLinuXino A64](https://www.olimex.com/Products/OLinuXino/A64/A64-OLinuXino/) as a lower-cost alternative.
- An Optolink-to-USB cable. You can either:
  - buy the original Viessmann cable from a specialist vendor such as [Loebbe Shop](https://www.loebbeshop.de/), or
  - build a compatible cable yourself; more details are available from projects such as [MyVitotronicLogger](https://github.com/Ixtalo/MyVitotronicLogger) and the [Optolink Splitter project](https://github.com/philippoo66/optolink-splitter).

## ✨ Features

This project is designed to be:

- reliable and ready to run 24/7, with robust error handling, automatic reconnection to the MQTT broker, and serial-port recovery after transient failures
- easy to configure through a single YAML file for all device parameters and metadata
- capable of both reading values from the heating system and writing writable registers such as heating modes or target temperatures
- Home Assistant friendly, with MQTT discovery support to make entities appear automatically in Home Assistant
- straightforward to install via PyPI or Docker, with simple upgrade paths

Current limitation:

- compatibility with VitoConnect is not implemented; if you need that approach, check out [Optolink Splitter](https://github.com/philippoo66/optolink-splitter) or [Optolink Bridge](https://github.com/kristian/optolink-bridge/).

## 🚀 Installation

This project supports two main setup paths: PyPI and Docker. Both are intended for Linux systems with the USB cable connected to the Optolink interface.

### PyPI package

```sh
python3 -m venv optolink2mqtt-venv
source optolink2mqtt-venv/bin/activate
pip install viessmann-optolink2mqtt

optolink2mqtt --help
```

#### Python compatibility

The project aims to stay compatible with **Python 3.9**, to support **Debian 11 (bullseye) and its derivatives**, such as Raspberry Pi OS Legacy, which ship Python 3.9. The CI runs the unit tests on Python 3.9 (the oldest supported version), 3.11 and 3.15 (the latest release).

For this reason, dependencies are pinned to the last versions that still support Python 3.9. For example, `platformdirs` stays at 4.4.0, since later releases require Python 3.10 or 3.11.

On Debian 11, the `venv` module is in a separate package. Debian 11's pip (20.3) is old, so upgrade it inside the virtual environment before installing:

```sh
sudo apt install python3-venv
python3 -m venv optolink2mqtt-venv
source optolink2mqtt-venv/bin/activate
pip install --upgrade pip
pip install viessmann-optolink2mqtt
```

The Docker image ships its own Python, so it doesn't depend on the Python version of the host.

### Docker

When using Docker, provide the YAML config path and the serial port name in the command line. For example, `/dev/ttyUSB0`:

```sh
docker run -d -v <your config file>:/etc/optolink2mqtt/optolink2mqtt.yaml \
    --device=/dev/ttyUSB0 \
    --hostname $(hostname) \
    --name optolink2mqtt \
    --restart=unless-stopped \
    ghcr.io/f18m/optolink2mqtt:latest

docker logs -f optolink2mqtt
```

The `--restart=unless-stopped` option ensures the container is restarted after a system reboot.

The container runs as an unprivileged user that belongs to the `dialout` group (gid 20), which owns serial devices on Debian, Ubuntu and Raspberry Pi OS. If the serial device on your host belongs to another group (check with `ls -ln /dev/ttyUSB0`), add `--group-add <gid of that group>` to the `docker run` command.

The Docker image supports three architectures: `amd64`, `armv7`, and `arm64`.

If your MQTT broker requires authentication, set `MQTT_BROKER_PASSWORD` to provide the password as an environment variable. Alternatively, mount a Docker secret file and set `MQTT_BROKER_PASSWORD_FILE` to the file path:

```sh
docker run -d -v <your config file>:/etc/optolink2mqtt/optolink2mqtt.yaml \
    -v <path to secret file>:/run/secrets/mqtt_broker_password:ro \
    --env MQTT_BROKER_PASSWORD_FILE=/run/secrets/mqtt_broker_password \
    --device=/dev/ttyUSB0 \
    --hostname $(hostname) \
    --name optolink2mqtt \
    --restart=unless-stopped \
    ghcr.io/f18m/optolink2mqtt:latest
```

The broker username is configured in `mqtt.broker.username` in the YAML file. `MQTT_BROKER_PASSWORD` takes precedence over `MQTT_BROKER_PASSWORD_FILE`, and either environment variable overrides `mqtt.broker.password` in the YAML configuration. A trailing newline in the password file is ignored. The password is only sent when `mqtt.broker.username` is set too.

To connect over TLS, set `mqtt.broker.tls: true` (the default when `mqtt.broker.port` is 8883). The broker certificate is always verified, against the system CA store or the CA bundle in `mqtt.broker.ca_certs`; `mqtt.broker.certfile` and `mqtt.broker.keyfile` provide an optional client certificate. Without TLS, credentials are sent in plaintext.

### Docker Compose

If you prefer Docker Compose, use the provided [docker-compose.yml](./docker-compose.yml) file and adapt the serial port name to your system, for example replacing `/dev/ttyUSB0` with the actual port provided by your device.

## ⚙️ Configuration

This software accepts declarative configuration in YAML format. Use [optolink2mqtt.yaml](./optolink2mqtt.yaml) as the reference for the supported syntax and configuration structure.

### Register types

The `type` attribute of each register in `registers_poll_list` says how its bytes are decoded:

| `type` | Bytes | Published value |
|---|---|---|
| `int` (default) | little-endian integer, `signed` or not | integer, e.g. `42` |
| `float` | little-endian integer multiplied by `scale_factor` | number, e.g. `21.5` |
| `enum` | little-endian integer mapped to a label by the `enum` dictionary | label, e.g. `DHW only` |
| `datetime_bcd` | the 8-byte Viessmann DateTimeBCD format | ISO 8601 date/time, e.g. `2026-12-24T00:00:00+01:00` |

A `scale_factor` other than 1 requires `type: float`, and an `enum` dictionary requires `type: enum`. Configuration files written for older versions must add the `type` to these registers.

A `datetime_bcd` register is published as an ISO 8601 date/time, or as `None` when the date/time is not set on the device (Viessmann stores 1970-01-01 for that). The device clock has no timezone: set `optolink.timezone` to its IANA timezone, e.g. `Europe/Berlin`, otherwise the timezone of the host is used. Writing an ISO 8601 date/time sets the register, converting it to the device timezone if it carries a timezone; writing `None` clears it.
In Home Assistant, use the `datetime` platform for a writable register (Home Assistant 2026.5 or later), or the `sensor` platform with `device_class: timestamp` for a read-only one.

### Configuration version

The top-level `config_version` key says which version of the configuration format a file is written for. Each optolink2mqtt release accepts exactly one version and refuses to start (exit code 2) with any other, explaining why. Files without `config_version` are version 1.

When a release bumps the version, convert your file with the [configuration upgrade tool](https://f18m.github.io/viessmann-optolink2mqtt/config-upgrade/): paste the current file and copy the converted one, with the changes highlighted. It runs entirely in your browser.

## How to discover register addresses

Please check my translation of the [Viessmann register mappings](https://github.com/f18m/viessmann-parameters-english) to get a good starting point.

### Reading a single register with `read-register`

`optolink2mqtt` has two modes:

- `optolink2mqtt run` polls the registers in the configuration file and bridges them to MQTT. It is the default mode, used when no mode is given.
- `optolink2mqtt read-register <address> <length> [signed] [scale_factor] [byte_filter]` reads one register once, prints everything about it on stdout, and exits. No MQTT broker is needed.

Use `read-register` to try out a register before adding it to `registers_poll_list`. The arguments match the register keys of the configuration file:

| Argument | Meaning | Default |
|---|---|---|
| `address` | register address, hexadecimal (`0x0800`) or decimal | (required) |
| `length` | number of bytes to read | (required) |
| `signed` | `signed`/`true` or `unsigned`/`false` | `unsigned` |
| `scale_factor` | factor the decoded integer is multiplied by, e.g. `0.1` | `1.0` |
| `byte_filter` | decode only bytes `b:<start>:<end>` (both inclusive) | none |

The serial port is read from the configuration file. To skip the configuration file, pass `--serial-port /dev/ttyUSB0`. Add `--show-received-bytes` to log the raw serial traffic.

For example, to read the 2-byte signed outdoor temperature at `0x0800`, scaled by 0.1:

```sh
optolink2mqtt read-register --serial-port /dev/ttyUSB0 0x0800 2 signed 0.1
```

The output shows:

- the serial port settings, and whether the VS2 handshake succeeded;
- the raw bytes, one per line, in hex, decimal and binary;
- the value decoded with the given parameters;
- other ways to read the same bytes (signed/unsigned, little/big endian, scaled by 0.1 and 0.01, ASCII), which help you guess the format;
- a `registers_poll_list` snippet you can paste into the configuration file.

Only one program at a time can talk over the Optolink interface. `read-register` refuses to start, with exit code 5, if the serial port is already in use, for example by an `optolink2mqtt run` instance. Stop that instance first (e.g. `docker stop optolink2mqtt`) and restart it when you are done.

With Docker, run the mode in a temporary container:

```sh
docker run --rm --device=/dev/ttyUSB0 \
    ghcr.io/f18m/optolink2mqtt:latest \
    python -m src.main read-register --serial-port /dev/ttyUSB0 0x0800 2 signed 0.1
```

`read-register` exits with code 0 if the read succeeded. It exits with 2 if the configuration file cannot be loaded, 4 if the register arguments are invalid, 5 if the serial port is busy, 6 if the Optolink connection cannot be set up, and 7 if the read failed.


## 🔌 Serial port naming

A common issue on some Linux platforms is that a USB serial adapter may be re-enumerated by the kernel after a bus reset, causing the device name to change from `/dev/ttyUSB0` to `/dev/ttyUSB1` or similar. In that case, a config file that references the old device path will stop working.

The recommended solution is to create a stable [udev](https://en.wikipedia.org/wiki/Udev) symlink for the adapter and use that path instead.

1. Use `lsusb` to identify the Viessmann Optolink adapter details. For example:

```sh
Bus 002 Device 006: ID 1a86:7523 QinHeng Electronics CH340 serial converter
```

In this example, `1a86` is the vendor ID and `7523` is the product ID.

2. Create a udev rule:

```sh
sudo nano /etc/udev/rules.d/99_optolink_usb.rules
```

Then add a line like:

```sh
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="optolinkUSB"
```

3. Unplug and reconnect the Optolink cable.

4. Use `/dev/optolinkUSB` in [optolink2mqtt.yaml](./optolink2mqtt.yaml) and pass `--device=/dev/optolinkUSB` in Docker commands when needed.

## 🏠 Home Assistant integration

This project makes it easy to expose Viessmann entities to Home Assistant through MQTT discovery.

The `ha_discovery` section of each register in [optolink2mqtt.yaml](./optolink2mqtt.yaml) contains metadata that tells Home Assistant how to create entities automatically.

<img title="HA integration" alt="HA integration" src="docs/home_assistant_mqtt_device.png">

This makes it possible to build a Home Assistant dashboard that reflects the state of your Viessmann system. For example, the dashboard below was created for a heat pump:

<img title="HA dashboard" alt="HA dashboard" src="docs/home_assistant_dashboard2.png">

## Labelling the hardware

Your Viessmann device and the SBC used to monitor it may stay in service for many years. To make future maintenance easier, it's a good idea to document what is running where.

A simple approach is to print a QR code pointing to this project and attach it physically to the SBC so that anyone inspecting it can quickly find the relevant documentation.

Here's a QR code generated for that purpose:

<img title="QRCode" alt="QRCode" src="docs/qr-code.png">

## 🗺️ Roadmap

Planned work includes:

- Prometheus support for health statistics such as Optolink errors and network issues

If you are looking for a specific feature, open an [issue](https://github.com/f18m/viessmann-optolink2mqtt/issues).

## 🔗 Related projects

- [Optolink Splitter](https://github.com/philippoo66/optolink-splitter): the original project that inspired this one
- [Optolink Bridge](https://github.com/kristian/optolink-bridge/): an approach based on the Optolink Splitter idea that requires a VitoConnect device and creates a man-in-the-middle bridge
- [openv vcontrold](https://github.com/openv/vcontrold): an older C-based implementation of the VS1 and VS2 protocols; its wiki contains extensive protocol details in German
- [VitoWiFi](https://github.com/bertmelis/VitoWiFi): a C++ implementation of the VS1 (KW) and VS2 (P300) Optolink protocols for Linux and ESP-based systems
- [FloorHeatingController](https://github.com/f18m/floor-heating-controller): firmware for controlling floor-heating valves and replacing physical thermostats with Home Assistant virtual thermostats
