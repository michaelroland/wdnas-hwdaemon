#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Processors for Threaded Serial Interface.

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


import serial
import threading

from messagequeue import Message
from messagequeue.threaded import Handler

import threadedserial


class BasicSerialDataProcessor(object):
    """Base class to send and receive binary data using a ``threadedserial.SerialConnectionManager``.
    """
    
    def __init__(self):
        """Initializes a new serial data processor."""
        super(BasicSerialDataProcessor, self).__init__()
        self.__manager = None
        self.__manager_ready_condition = threading.Condition()
    
    def connectionOpened(self, serial_connection_manager):
        """Callback invoked once the serial connection is managed and ready for transmission.
        
        Args:
            serial_connection_manager (threadedserial.SerialConnectionManager): The associated
                serial connection manager.
        """
        if not isinstance(serial_connection_manager, threadedserial.SerialConnectionManager):
            raise TypeError("'serial_connection_manager' is not an instance of SerialConnectionManager")
        with self.__manager_ready_condition:
            self.__manager = serial_connection_manager
            self.__manager_ready_condition.notifyAll()
    
    def connectionClosed(self, error):
        """Callback invoked when the underlying serial connection is closed.
        
        Args:
            error (Exception): If not ``None``, the communication ended due to this
                ``Exception``.
        """
        with self.__manager_ready_condition:
            pass
    
    def dataReceived(self, data):
        """Callback for processing incoming data from the serial connection.
        
        This callback is invoked on the receiver thread of the
        ``threadedserial.SerialConnectionManager``. Implementations of processor
        must make sure that the receiver thread is not extensively blocked due to
        further processing of incoming data.
        
        Args:
            data (bytearray): A byte array of received data.
        """
        pass
    
    def sendData(self, data, flush=False):
        """Send data over the serial connection.
        
        Args:
            data (bytearray): A byte array of data to send.
            flush (bool): If ``True``, the send buffer of the serial port is flushed
                immediately after writing the data.
        """
        with self.__manager_ready_condition:
            if self.__manager is None: self.__manager_ready_condition.wait()
            self.__manager._write(data, flush)


class AbstractPacketProcessor(BasicSerialDataProcessor):
    """Abstract base class to send and receive packet-structured data.
    """
    
    def __init__(self):
        """Initializes a new packet processor."""
        super(AbstractPacketProcessor, self).__init__()
    
    def dataReceived(self, data):
        raise NotImplementedError("Implementations must override dataReceived")
    
    def packetReceived(self, packet):
        """Callback for receiving a single data packet from the serial connection.
        
        Args:
            packet (bytearray): The data packet.
        """
        pass
    
    def sendPacket(self, packet):
        """Send a data packet over the serial connection.
        
        Args:
            packet (bytearray): The data packet.
        """
        raise NotImplementedError("Implementations must override sendPacket")


class PacketHandler(Handler):
    """Message queue handler for passing received packets to their processor.
    """
    
    MSG_PACKET_RECEIVED = Handler.NEXT_MSG_ID
    NEXT_MSG_ID = MSG_PACKET_RECEIVED + 1
    
    def __init__(self, packet_processor):
        """Initializes a new packet receiving queue handler.
        
        Args:
            packet_processor (AbstractPacketProcessor): The associated packet processor
                that feeds and consumes this message queue.
        """
        if not isinstance(packet_processor, AbstractPacketProcessor):
            raise TypeError("'packet_processor' is not an instance of AbstractPacketProcessor")
        super(PacketHandler, self).__init__(True)
        self.__packet_processor = packet_processor
    
    def handleMessage(self, msg):
        if msg.what == PacketHandler.MSG_PACKET_RECEIVED:
            self.__packet_processor.packetReceived(msg.obj)
        else:
            super(PacketHandler, self).handleMessage(msg)


class TerminatedPacketProcessor(AbstractPacketProcessor):
    """A packet processor that transmits and receives packets that have a fixed end-marker.
    """
    
    def __init__(self, terminator=b'\0', strip=b''):
        """Initializes a new packet processor that identifies received packets based on an end-marker.
        
        Args:
            terminator (bytearray): The end-marker that follows each packet,
                defaults to a null-byte.
            strip (bytearray): An optional array of bytes to strip from the
                beginning and the end of each packet.
        """
        super(TerminatedPacketProcessor, self).__init__()
        self.__read_buffer = bytearray()
        self.__terminator = bytearray(terminator)
        self.__strip_bytes = bytearray(strip)
        self.__packet_handler = PacketHandler(self)
    
    def connectionOpened(self, serial_connection_manager):
        self.__packet_handler.start()
        super(TerminatedPacketProcessor, self).connectionOpened(serial_connection_manager)
    
    def connectionClosed(self, error):
        super(TerminatedPacketProcessor, self).connectionClosed(error)
        self.__packet_handler.join()
    
    def dataReceived(self, data):
        self.__read_buffer.extend(data)
        while self.__terminator in self.__read_buffer:
            (packet, self.__read_buffer) = self.__read_buffer.split(self.__terminator, 1)
            packet = packet.strip(self.__strip_bytes)
            self.__packet_handler.sendMessage(
                    Message(PacketHandler.MSG_PACKET_RECEIVED, packet))
    
    def packetReceived(self, packet):
        """Callback for receiving a single data packet from the serial connection.
        
        This callback is invoked on a dedicated packet handler thread and may
        be blocked for processing the packet.
        
        The terminator sequence is automatically sripped from each packet.
        
        Args:
            packet (bytearray): The data packet (without its terminator).
        """
        pass
    
    def sendPacket(self, packet):
        """Send a data packet (terminated) over the serial connection.
        
        The terminator sequence is automatically appended to each packet.
        The write buffer of the serial port gets flushed right after sending
        the packet.
        
        Args:
            packet (bytearray): The data packet (without its terminator).
        """
        packet_to_send = bytearray(packet)
        packet_to_send.extend(self.__terminator)
        self.sendData(packet_to_send, True)


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

