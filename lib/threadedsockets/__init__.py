#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thread-based Socket Library.

Copyright (c) 2017 Michael Roland <mi.roland@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""


__version__ = "0.9"
__author__  = "Michael Roland"


class SocketSecurityException(Exception):
    """Exception class for security errors related to sockets.
    """
    pass


class SocketConnectionBrokenError(IOError):
    """Exception class for failures on socket IO operations not indicated by other socket errors.
    """
    pass


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

