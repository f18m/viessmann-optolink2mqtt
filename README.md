[![GitHub Tag](https://img.shields.io/github/v/tag/f18m/viessmann-optolink2mqtt)](https://github.com/f18m/viessmann-optolink2mqtt/releases)
[![PyPI - Version](https://img.shields.io/pypi/v/viessmann-optolink2mqtt)](https://pypi.org/project/viessmann-optolink2mqtt/)

# viessmann-optolink2mqtt

This project provides an open source interface between a [Viessmann](https://en.wikipedia.org/wiki/Viessmann) device (heat pump, gas heater, etc) and 
[MQTT](https://en.wikipedia.org/wiki/MQTT).

> [!IMPORTANT]
> This project is an independent work and is not associated with, sponsored by, or connected to the Viessmann company in any manner. Viessmann and all related trademarks, product names, and device names are trademarks or registered trademarks of Viessmann and remain the exclusive property of Viessmann.


## What is Optolink?

Some Viessmann devices (at least those manufactured before roughly year 2014) expose an optical interface
for communication with external devices named "_Optolink_".

This interface is typically located in the Vitotronic panel and officially supports a connection to the
[VitoConnect](https://www.viessmann.co.uk/en/products/control-system-and-connectivity/vitoconnect.html)
device.
On the other hand such interface also allows tinkerers to read and write registers of the Viessmann devices
to e.g. read telemetry data (temperatures, status of internal parts, etc) and write settings
(e.g. heating mode, target temperatures, etc).

This project allows you to take control of your Viessmann device by hooking into the Optolink interface
and sending all data to a local MQTT server, so that all your data is local and is never transiting 
the cloud of any vendor.


## Architecture

<img title="Setup" alt="Architecture" src="docs/architecture.png">

## Hardware Required

* A Single Board Computer (SBC) which is capable of running Python and has a USB-A connector
  (if you plan to use the original Viessmann Optolink USB cable). A typical choice is the [Raspberry](https://www.raspberrypi.com/products/raspberry-pi-5/); myself I've been using the [OLinuXino A64](https://www.olimex.com/Products/OLinuXino/A64/A64-OLinuXino/) as (slightly cheaper) alternative.
* The Optolink USB cable to read/write; you have two main options: a) buy the original Viessmann cable on specialized shops such as [https://www.loebbeshop.de/](https://www.loebbeshop.de/); see exact item [here](https://www.loebbeshop.de/viessmann/ersatzteil/anschlussleitung-usb-optolink-fuer-vitoconnetc-artikel-7856059/) or b) build your own cable, more details available from other tinkerers like [MyVitotronicLogger](https://github.com/Ixtalo/MyVitotronicLogger) or at [Optolink splitter readme](https://github.com/philippoo66/optolink-splitter)


## Software features

This project main features are:

* Written to be reliable and run 24/7: careful exception handling, reconnects automatically to the MQTT broker in case of transient network issues, etc.
* One-file configuration: configure all aspects of your Viessmann device from a single YAML config file (easy to backup and/or version in git); no need to hand-write HomeAssistant MQTT entity definitions!
* Read and write support: allows both to read from your Viessmann device and also to set writable registers to e.g. change heating mode, change target temperatures, etc.
* HomeAssistant friendly: although this project can be used with _any_ home automation platform; it provides a number of features that make it very HomeAssistant friendly: in particular MQTT discovery messages make it possible to magically have all your Viessmann entities appear in HomeAssistant.
* Easy installation via Pypi and docker

What this project does NOT have at this time:
* Compatibility with the VitoConnect: if you are interested in that I suggest you to look at the [Optolink Splitter](https://github.com/philippoo66/optolink-splitter) or [Optolink Bridge](https://github.com/kristian/optolink-bridge/)


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
    --restart=unless-stopped \
    ghcr.io/f18m/optolink2mqtt:latest

docker logs -f optolink2mqtt
```

Please note that the `--restart=unless-stopped` makes sure that the optolink2mqtt docker will 
be restarted after a reboot.

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

This makes it possible to build in your HomeAssistant dashboard visual representation of your Viessmann device.
E.g.. for my heat pump I was able to build the following dashboard:

<img title="HA dashboard" alt="HA dashboard" src="docs/home_assistant_dashboard2.png">


## Labelling of the HW

Most likely your Viessmann device will stay around for a lot of time (many years hopefully), 
and so will do the SBC that connects it to your home automation platform.
For this reason I suggest to provide some documentation for what is running on your SBC.
A simple approach I like is to print a QR code pointing at this page and stick it physically on the SBC,
to make it obvious to anybody inspecting it where to find the docs.

Here you can find a QR code I produced with the optimal [miniQR code generator](https://mini-qr-code-generator.vercel.app/):

<img title="QRCode" alt="QRCode" src="docs/qr-code.png">


## Related projects

* [Optolink Splitter](https://github.com/philippoo66/optolink-splitter): this is the original project that inspired this one
* [Optolink Bridge](https://github.com/kristian/optolink-bridge/): inspired from the "Optolink Splitter"; requires you to own a VitoConnect device and allows you to setup a "man in the middle" device
* [openv vcontrold](https://github.com/openv/vcontrold): seems abandoned but contains a C-based implementation of the VS1 and VS2 protocols apparently. Its [wiki](https://github.com/openv/openv/wiki/) has plenty of details although in German
* [VitoWiFi](https://github.com/bertmelis/VitoWiFi): a C++ implementation of VS1 (KW) and VS2 (P300) Optolink protocols, for use on ESP microcontrollers but also Linux systems

* [FloorHeatingController](https://github.com/f18m/floor-heating-controller): firmware for a controller of floor heating valves, to help replace physical thermostat with HomeAssistant virtual thermostats
