#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BER TLV Packet-based Server-side Socket Interface.

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

import threadedsockets.socketserver as socketserver
import tlv.ber


class PacketServerThread(socketserver.SocketServerThread):
    """Base class to send and receive BER TLV packet-structured data using a ``socket.SocketType``.
    """
    
    MAX_RECEIVE_BUFFER_SIZE = 0x4000000
    
    def __init__(self, listener):
        """Initializes a new socket server thread that processes BER TLV packet-structured data.
        
        Args:
            listener (SocketListener): The parent socket listener instance.
        """
        self.__read_buffer = bytearray()
        super(PacketServerThread, self).__init__(listener)
    
    def connectionOpened(self, remote_address):
        raise SocketSecurityException("The default implementation refuses all connections.")
    
    def connectionClosed(self, error):
        pass
    
    def dataReceived(self, data):
        self.__read_buffer.extend(data)
        buffer_length = len(self.__read_buffer)
        
        if buffer_length > self.MAX_RECEIVE_BUFFER_SIZE:
            raise ValueError("Received data exceeds the maximum supported receive buffer size.")
        
        offset = 0
        try:
            while offset < buffer_length:
                (data_object, next_offset) = tlv.ber.BerTlv.parse(self.__read_buffer, offset)
                offset = next_offset
                self.packetReceived(data_object)
        except tlv.ber.IncompleteTlvDataError:
            pass
        finally:
            self.__read_buffer[0:offset] = []
    
    def packetReceived(self, data_object):
        """Callback for receiving a single BER TLV data packet.
        
        This callback is invoked on the receiver thread and blocking may result
        in loss of incoming data in full-duplex communication.
        
        Args:
            data_object (tlv.ber.BerTlv): The BER TLV data packet.
        """
        pass
    
    def sendPacket(self, data_object):
        """Send a BER TLV data packet.
        
        Args:
            data_object (tlv.ber.BerTlv): The BER TLV data packet.
        """
        self.sendData(data_object.serialize())


class PacketSocketListener(socketserver.SocketListener):
    """A server socket listener that spawns new ``PacketServerThread`` threads for incoming connections.
    """

    def __init__(self, server_socket, max_clients=10):
        """Initializes a new server socket listener.
        
        Args:
            server_socket (socket.SocketType): A bound server socket.
            max_clients (int): Maximum number of concurrent clients.
        """
        super(PacketSocketListener, self).__init__(server_socket, max_clients, PacketServerThread)


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

