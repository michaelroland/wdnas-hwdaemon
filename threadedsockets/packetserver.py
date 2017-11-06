#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Packet-based Server-side Socket Interface.

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

import threadedsockets.packets as packets
import threadedsockets.socketserver as socketserver


class PacketServerThread(socketserver.SocketServerThread):
    """Base class to send and receive packet-structured data using a ``socket.SocketType``.
    """
    
    MAX_RECEIVE_BUFFER_SIZE = 0x4000000
    
    def __init__(self, listener, packet_class=packets.BasicPacket):
        """Initializes a new socket server thread that processes packet-structured data.
        
        Args:
            listener (SocketListener): The parent socket listener instance.
            packet_class (type(packets.BasicPacket)): A packet parser implementation.
        """
        self.__read_buffer = bytearray()
        self.__packet_class = packet_class
        super().__init__(listener)
    
    def connectionOpened(self, remote_socket, remote_address):
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
                try:
                    (packet, next_offset) = self.__packet_class.parse(self.__read_buffer, offset)
                except packets.InvalidPacketError:
                    offset += 1
                else:
                    offset = next_offset
                    self.packetReceived(packet)
        except packets.IncompletePacketError:
            pass
        finally:
            if offset > 0:
                self.__read_buffer[0:offset] = []
    
    def packetReceived(self, packet):
        """Callback for receiving a single protocol packet.
        
        This callback is invoked on the receiver thread and blocking may result
        in loss of incoming data in full-duplex communication.
        
        Args:
            packet (packets.BasicPacket): The received packet.
        """
        pass
    
    def sendPacket(self, packet):
        """Send a single protocol packet.
        
        Args:
            packet (packets.BasicPacket): The packet to send.
        """
        self.sendData(packet.serialize())


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

