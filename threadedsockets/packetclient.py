#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BER TLV Packet-based Client-side Socket Interface.

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

import threadedsockets.socketclient as socketclient
import tlv.ber


class BasicPacketClient(socketclient.BasicSocketClient):
    """A basic client socket wrapper to send and receive BER TLV packet-structured data using a ``socket.SocketType``.
    """

    MAX_RECEIVE_BUFFER_SIZE = 0x4000000
    
    def __init__(self, client_socket):
        """Initializes a new client socket wrapper.
        
        Args:
            client_socket (socket.SocketType): A connected client socket.
        """
        self.__read_buffer = bytearray()
        super(BasicPacketClient, self).__init__(client_socket)
    
    def receivePacket(self):
        """Receive a single BER TLV data packet.
        
        Returns:
            tlv.ber.BerTlv: The BER TLV data packet.
        """
        while True:
            data = self.receiveData()
            self.__read_buffer.extend(data)
            buffer_length = len(self.__read_buffer)
        
            if buffer_length > self.MAX_RECEIVE_BUFFER_SIZE:
                raise ValueError("Received data exceeds the maximum supported receive buffer size.")
            
            offset = 0
            try:
                if offset < buffer_length:
                    (data_object, next_offset) = tlv.ber.BerTlv.parse(self.__read_buffer, offset)
                    offset = next_offset
                    return data_object
            except tlv.ber.IncompleteTlvDataError:
                pass
            finally:
                self.__read_buffer[0:offset] = []
    
    def sendPacket(self, data_object):
        """Send a BER TLV data packet.
        
        Args:
            data_object (tlv.ber.BerTlv): The BER TLV data packet.
        """
        self.sendData(data_object.serialize())


class ThreadedPacketClient(socketclient.ThreadedSocketClient):
    """A client socket wrapper to send and receive BER TLV packet-structured data using a ``socket.SocketType``.
    
    Data is continously received using a receiver thread.
    
    Attributes:
        is_running: Is the socket connection handler thread in running state?
    """
    
    def __init__(self, client_socket):
        """Initializes a new client socket wrapper.
        
        Args:
            client_socket (socket.SocketType): A connected client socket.
        """
        super(ThreadedPacketClient, self).__init__(client_socket)
    
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


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

