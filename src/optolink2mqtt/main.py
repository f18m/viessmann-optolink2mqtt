#!/usr/bin/env python

"""
main.py
----------------
Optolink2Mqtt main module
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

import sys

from .cli import MODE_READ_REGISTER, parse_args
from .optolink2mqtt_app import Optolink2MqttApp
from .read_register import run_read_register


def main() -> None:
    args = parse_args()
    if args.version:
        print(f"Version: {Optolink2MqttApp.get_embedded_version()}")
        sys.exit(0)

    if args.mode == MODE_READ_REGISTER:
        sys.exit(run_read_register(args))

    # "run" mode
    app = Optolink2MqttApp()
    ret = app.setup(args)
    if ret > 0:
        sys.exit(ret)
    if ret == -1:  # version has been requested (and already printed)
        sys.exit(0)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
