#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Thread-based Client-side Socket Interface.

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


import socket
import threading

from threadedsockets import SocketConnectionBrokenError


class BasicSocketClient(object):
    """A basic client socket wrapper to send and receive binary data using a ``socket.SocketType``.
    """

    def __init__(self, client_socket):
        """Initializes a new client socket wrapper.
        
        Args:
            client_socket (socket.SocketType): A connected client socket.
        """
        super(BasicSocketClient, self).__init__()
        self._BYTES_TO_READ = 4096
        self.__send_lock = threading.RLock()
        self.__receive_lock = threading.RLock()
        self.__socket = client_socket
    
    def close(self):
        """Close the client-side socket connection.
        
        This method blocks until cleanup completed.
        """
        self._closeSocket()
    
    def _closeSocket(self):
        """Close the client-side socket."""
        with self.__send_lock, self.__receive_lock:
            try:
                self.__socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            self.__socket.close()
    
    def receiveData(self):
        """Receive incoming data from the remote socket connection.
        
        Returns:
            bytearray: A byte array of received data.
        
        Raises:
            socket.error: If sending failed.
            SocketConnectionBrokenError: If sending failed and the send method did not
                raise an exception.
        """
        with self.__receive_lock:
            data = self.__socket.recv(self._BYTES_TO_READ)
            if data:
                return data
            else:
                # no data received: connection broken?
                raise SocketConnectionBrokenError("socket.recv() returned {0}".format(data))
    
    def sendData(self, data):
        """Send data over the remote socket connection.
        
        Args:
            data (bytearray): A byte array of data to send.
        
        Raises:
            socket.error: If sending failed.
            SocketConnectionBrokenError: If sending failed and the send method did not
                raise an exception.
        """
        with self.__send_lock:
            bytes_to_send = len(data)
            offset = 0
            while offset < bytes_to_send:
                bytes_sent = self.__socket.send(data[offset:])
                if bytes_sent > 0:
                    offset += bytes_sent
                else:
                    # no data received: connection broken?
                    raise SocketConnectionBrokenError("socket.send() returned {0}".format(bytes_sent))


class ThreadedSocketClient(BasicSocketClient):
    """A client socket wrapper to send and receive binary data using a ``socket.SocketType``.
    
    Data is continously received using a receiver thread.
    
    Attributes:
        is_running: Is the socket connection handler thread in running state?
    """
    
    def __init__(self, client_socket):
        """Initializes a new client socket wrapper.
        
        Args:
            client_socket (socket.SocketType): A connected client socket.
        """
        super(ThreadedSocketClient, self).__init__(client_socket)
        self.__lock = threading.RLock()
        self.__running = True
        self.__thread = threading.Thread(target=self.__run)
        self.__thread.daemon = True
        self.__thread.start()
    
    def connectionClosed(self, error):
        """Callback invoked when the remote socket connection is closed.
        
        Args:
            error (Exception): If not ``None``, the communication ended due to this
                ``Exception``.
        """
        pass
    
    def dataReceived(self, data):
        """Callback for processing incoming data from the remote socket connection.
        
        This callback is invoked on the connection handler thread of ``ThreadedSocketClient``.
        Implementations must make sure that this thread is not extensively blocked due to
        further processing of incoming data.
        
        Args:
            data (bytearray): A byte array of received data.
        """
        pass
    
    def __run(self):
        """Runnable target of the client-side socket connection handler thread."""
        try:
            while self.__running:
                data = self.receiveData()
                self.dataReceived(data)
        except Exception as e:
            error = e
        
        self._closeSocket()
        self.connectionClosed(error)
    
    def close(self):
        with self.__lock:
            if self.__running:
                self.__running = False
                super(ThreadedSocketClient, self).close()
                self.__thread.join()
    
    @property
    def is_running(self):
        """bool: Is the socket connection handler thread in running state?"""
        with self.__lock:
            return self.__running


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

