#!/usr/bin/env python

# optolink2mqtt main module
# Copyright (C) 2026

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys


class PlaceholderApp:
    def __init__(self):
        pass

    def setup(self) -> int:
        print("PlaceholderApp setup called")
        return 0

    def run(self) -> int:
        print("PlaceholderApp run called")
        return 0


def main() -> None:
    app = PlaceholderApp()
    ret = app.setup()
    if ret > 0:
        sys.exit(ret)
    if ret == -1:  # version has been requested (and already printed)
        sys.exit(0)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
