[![GitHub Tag](https://img.shields.io/github/v/tag/f18m/viessmann-optolink2mqtt)](https://github.com/f18m/viessmann-optolink2mqtt/releases)
[![PyPI - Version](https://img.shields.io/pypi/v/viessmann-optolink2mqtt)](https://pypi.org/project/viessmann-optolink2mqtt/)

# viessmann-optolink2mqtt

Open source interface between a Viessmann device (heat pump, gas heater, etc) and 
[MQTT](https://en.wikipedia.org/wiki/MQTT).

## Architecture

<img title="Setup" alt="Architecture" src="docs/architecture.png">

## Hardware

* A Single Board Computer (SBC) which is capable of running Python and has a USB-A connector
  (if you plan to use the original Viessmann Optolink USB cable). A typical choice is the [Raspberry](https://www.raspberrypi.com/products/raspberry-pi-5/); myself I've been using the [OLinuXino A64](https://www.olimex.com/Products/OLinuXino/A64/A64-OLinuXino/) as (slightly cheaper) alternative.
* The Optolink USB cable to read/write; you have two main options: a) buy the original Viessmann cable on specialized shops such as [https://www.loebbeshop.de/](https://www.loebbeshop.de/); see exact item [here](https://www.loebbeshop.de/viessmann/ersatzteil/anschlussleitung-usb-optolink-fuer-vitoconnetc-artikel-7856059/) or b) build your own cable, more details available from other tinkerers like [MyVitotronicLogger](https://github.com/Ixtalo/MyVitotronicLogger) or at [Optolink splitter readme](https://github.com/philippoo66/optolink-splitter)

## Installation

This project supports 2 main installation methods: PyPi and Docker.
Both methods are meant to be used from a Linux Operating system which has the USB/DIY cable attached
(see "Hardware" section above).

### Pypi package

```sh
python3 -m venv optolink2mqtt-venv
source optolink2mqtt-venv/bin/activate
pip install viessmann-optolink2mqtt

optolink2mqtt --help
```

### Docker

When using Docker you will need to provide the YAML config file path in the `docker run` command and 
also provide the name of the serial port (e.g. `/dev/ttyUSB0` in the following example):

```sh
docker run -d -v <your config file>:/etc/optolink2mqtt/optolink2mqtt.yaml \
    --device=/dev/ttyUSB0 \
    --hostname $(hostname) \
    --name optolink2mqtt \
    ghcr.io/f18m/optolink2mqtt:latest

docker logs -f optolink2mqtt
```

The docker image of optolink2mqtt supports 3 main architectures: `amd64`, `armv7` and `arm64`.


## Configuration file

This software accepts a declarative configuration in YAML format.
Please look at the [optolink2mqtt.yaml](./optolink2mqtt.yaml) file as reference source for the syntax.


## How to discover register addresses

TO BE WRITTEN


## HomeAssistant Integration

This project allows a very easy integration with [HomeAssistant](https://www.home-assistant.io/).
It's enough to populae the `ha_discovery` section of each register defined in the [configuration file](./optolink2mqtt.yaml)
with some metadata specific for each sensor, to get the sensor automatically appear inside your HomeAssistant:

<img title="HA integration" alt="HA integration" src="docs/home_assistant_mqtt_device.png">


## Related projects

* [Optolink Splitter](https://github.com/philippoo66/optolink-splitter): this is the original project that inspired this one
* [Optolink Bridge](https://github.com/kristian/optolink-bridge/): inspired from the "Optolink Splitter"; requires you to own a VitoConnect device and allows you to setup a "man in the middle" device
* [openv vcontrold](https://github.com/openv/vcontrold): seems abandoned but contains a C-based implementation of the VS1 and VS2 protocols apparently. Its [wiki](https://github.com/openv/openv/wiki/) has plenty of details although in German
* [VitoWiFi](https://github.com/bertmelis/VitoWiFi): a C++ implementation of VS1 (KW) and VS2 (P300) Optolink protocols, for use on ESP microcontrollers but also Linux systems
