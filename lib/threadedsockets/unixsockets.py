#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UNIX Domain Sockets Helper.

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


import grp
import os
import os.path
import socket
import stat


class UnixSocketFactory(object):
    """Factory for binding and connecting named UNIX domain sockets.
    """
    
    def __init__(self, socket_path):
        """Initializes a new instance of the socket factory.
        
        Args:
            socket_path (str): File path of the named UNIX domain socket.
        """
        super().__init__()
        self.__socket_path = socket_path
        (dir_name, file_name) = os.path.split(socket_path)
        self.__socket_dir = dir_name
        self.__socket_name = file_name
    
    def deleteSocketFile(self):
        """Delete the socket file (if it exists)."""
        if os.path.exists(self.__socket_path):
            os.remove(self.__socket_path)
    
    def bindSocket(self, group=None):
        """Bind the named server socket and setup permissions.
        
        Args:
            group (int): Optional ID of a group that gets access to the socket (or
                None to grant no group permissions).
        
        Returns:
            socket.SocketType: The bound and configured server socket.
        """
        self.deleteSocketFile()
        
        old_umask = os.umask(stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP |
                             stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH)
        server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_socket.bind(self.__socket_path)
        os.umask(old_umask)
        
        permissions = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        if group is not None:
            os.chown(self.__socket_path, -1, group)
            permissions |= stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
        os.chmod(self.__socket_path, permissions)
        
        return server_socket

    def connectSocket(self):
        """Connect to the named server socket.
        
        Returns:
            socket.SocketType: The connected client socket.
        """
        client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_socket.connect(self.__socket_path)
        
        return client_socket

if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

