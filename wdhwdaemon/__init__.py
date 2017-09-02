#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Western Digital Hardware Controller Daemon Package.

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


WDHWD_VERSION = "%(prog)s v{version}".format(version=__version__)
WDHWD_DESCRIPTION = "Western Digital Hardware Controller Daemon"
WDHWC_DESCRIPTION = "Western Digital Hardware Controller Client"
WDHWD_EPILOG = """
Copyright (c) 2017 Michael Roland <mi.roland@gmail.com>
License GPLv3+: GNU GPL version 3 or later <http://www.gnu.org/licenses/>

This is free software: you can redistribute and/or modify it under the
terms of the GPLv3+.  There is NO WARRANTY; not even the implied warranty
of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
"""
WDHWD_PROTOCOL_VERSION = "WDHWD v{version}".format(version=__version__)
WDHWD_CONFIG_FILE_DEFAULT = "/etc/wdhwd.conf"
WDHWD_SOCKET_FILE_DEFAULT = "/var/run/wdhwd/hws.sock"


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")
