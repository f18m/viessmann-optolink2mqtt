"""
cli.py
----------------
Command line interface of optolink2mqtt: the "run" and "read-register" modes
Copyright (C) 2026 Francesco Montorsi

Licensed under the GNU GENERAL PUBLIC LICENSE, Version 3 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.gnu.org/licenses/gpl-3.0.html

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import argparse
import os
from typing import Optional, Sequence

from .config import Config

MODE_RUN = "run"
MODE_READ_REGISTER = "read-register"


def _parse_address(text: str) -> int:
    """Parses a register address, in hexadecimal (0x prefix) or decimal notation."""
    try:
        return int(text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid address '{text}': use hexadecimal (e.g. 0x00F8) or decimal notation"
        )


def _parse_length(text: str) -> int:
    try:
        length = int(text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid length '{text}'")
    if length <= 0:
        raise argparse.ArgumentTypeError(
            f"invalid length '{text}': shall be greater than zero"
        )
    return length


_SIGNED_VALUES = {"true": True, "signed": True, "1": True, "yes": True}
_UNSIGNED_VALUES = {"false": False, "unsigned": False, "0": False, "no": False}


def _parse_signed(text: str) -> bool:
    key = text.lower()
    if key in _SIGNED_VALUES:
        return _SIGNED_VALUES[key]
    if key in _UNSIGNED_VALUES:
        return _UNSIGNED_VALUES[key]
    raise argparse.ArgumentTypeError(
        f"invalid signedness '{text}': use one of {sorted(_SIGNED_VALUES)} or {sorted(_UNSIGNED_VALUES)}"
    )


def _parse_scale_factor(text: str) -> float:
    try:
        scale = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid scale factor '{text}'")
    # NOTE: "not scale > 0" also rejects NaN
    if not scale > 0.0 or scale == float("inf"):
        raise argparse.ArgumentTypeError(
            f"invalid scale factor '{text}': shall be a finite number greater than zero"
        )
    return scale


def _parse_byte_filter(text: str) -> Optional[str]:
    # the format itself is validated by OptolinkVS2Register, which knows the register length
    return None if text.lower() == "none" else text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optolink2mqtt",
        description="Open source interface between a Viessmann device (heat pump, gas heater, etc) and MQTT",
        epilog="The configuration file is mandatory and it is searched in the following locations (in order):\n"
        + "  * the location pointed by the 'OPTOLINK2MQTT_CONFIG' environment variable\n  * "
        + "\n  * ".join(Config.get_default_config_file_name())
        + "\nWhen no mode is given, the 'run' mode is used."
        + "\nSee documentation at https://github.com/f18m/optolink2mqtt for configuration examples and the config reference guide.\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        help="Print version and exit",
        action="store_true",
        default=False,
    )

    modes = parser.add_subparsers(dest="mode", metavar="<mode>", title="modes")

    modes.add_parser(
        MODE_RUN,
        help="Poll the registers in the configuration file and bridge them to MQTT (default mode)",
        description="Poll the registers listed in the configuration file and bridge them to MQTT.",
    )

    read_reg = modes.add_parser(
        MODE_READ_REGISTER,
        help="Read a single register once and print all its details, to help reverse-engineering registers",
        description="Opens the Optolink serial port, reads a single register once, prints the raw data, "
        "its decoded value and other interpretations of the same bytes, then exits. "
        "Use it to reverse-engineer registers before adding them to the configuration file. "
        "The serial port is taken from the configuration file, unless --serial-port is given. "
        "Exits with an error if the serial port is already in use, e.g. by an optolink2mqtt "
        "instance started in 'run' mode.",
        epilog="Example:\n  optolink2mqtt read-register 0x0800 2 signed 0.1\n"
        "  optolink2mqtt read-register --serial-port /dev/ttyUSB0 0x2323 4 unsigned 1 b:0:1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    read_reg.add_argument(
        "address",
        type=_parse_address,
        help="Register address, in hexadecimal (e.g. 0x00F8) or decimal notation",
    )
    read_reg.add_argument("length", type=_parse_length, help="Number of bytes to read")
    read_reg.add_argument(
        "signed",
        type=_parse_signed,
        nargs="?",
        default=False,
        help="Decode the value as signed ('signed'/'true') or unsigned ('unsigned'/'false'). Default: unsigned",
    )
    read_reg.add_argument(
        "scale_factor",
        type=_parse_scale_factor,
        nargs="?",
        default=1.0,
        help="Factor the decoded integer is multiplied by (e.g. 0.1). Default: 1.0",
    )
    read_reg.add_argument(
        "byte_filter",
        type=_parse_byte_filter,
        nargs="?",
        default=None,
        help="Decode only the bytes 'b:<start>:<end>' (both inclusive) of the register. Default: none",
    )
    read_reg.add_argument(
        "--serial-port",
        help="Serial port of the Optolink adapter (e.g. /dev/ttyUSB0); "
        "when given, the configuration file is not read",
    )
    read_reg.add_argument(
        "--show-received-bytes",
        action="store_true",
        default=False,
        help="Log every byte received on the serial port, for debugging",
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """
    Parses the given command line arguments (sys.argv[1:] when None).
    When no mode is given, the "run" mode is selected, for backward compatibility.
    """
    if "COLUMNS" not in os.environ:
        os.environ["COLUMNS"] = "120"  # avoid too many line wraps
    args = build_parser().parse_args(argv)
    if args.mode is None:
        args.mode = MODE_RUN
    return args
