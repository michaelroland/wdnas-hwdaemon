#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thread-based Serial Interface.

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


__version__ = "1.0"
__author__  = "Michael Roland"


import serial
import threading

from threadedserial.dataprocessors import *


class SerialConnectionManager(object):
    """A manager for performing threaded IO operations on a serial port.
    
    Attributes:
        processor (BasicSerialDataProcessor): The serial data processor associated
            with this manager.
        is_running (bool): Is the reader thread in running state?
        is_open (bool): Is the associated serial port open?
    """

    SERIAL_TIMEOUT = 5
    
    def __init__(self, serial_port, processor):
        """Initializes a new serial connection manager.
        
        Args:
            serial_port (serial.Serial): An opened instance of ``serial.Serial`` for
                the port to be managed.
            processor (BasicSerialDataProcessor): An instance of a
                ``BasicSerialDataProcessor`` to use for sending and receiving data
                on the serial port.
        """
        super(SerialConnectionManager, self).__init__()
        if not isinstance(serial_port, serial.Serial):
            raise TypeError("'serial_port' is not an instance of serial.Serial")
        if not isinstance(processor, BasicSerialDataProcessor):
            raise TypeError("'processor' is not an instance of BasicSerialDataProcessor")
        self.__lock = threading.RLock()
        self.__serial_port = serial_port
        #if not hasattr(self.__serial_port, 'cancel_read'):
        #    self.__serial_port.timeout = SerialConnectionManager.SERIAL_TIMEOUT
        self.__serial_port.timeout = SerialConnectionManager.SERIAL_TIMEOUT
        self.__processor = processor
        self.__reader_thread = threading.Thread(target=self.__runReader)
        self.__reader_thread.daemon = True
        self.__running = True
        self.__reader_thread.start()
    
    def __runReader(self):
        """Runnable target of the reader thread."""
        self.__processor.connectionOpened(self)
        error = None
        while self.__running and self.__serial_port.isOpen():
            try:
                bytes_to_read = self.__serial_port.inWaiting()
                if bytes_to_read <= 0:
                    bytes_to_read = 1
                data = self.__serial_port.read(bytes_to_read)
            except serial.SerialException as e:
                error = e
                break
            except serial.portNotOpenError:
                # expected if port was closed immediately before reading
                break
            else:
                if data:
                    try:
                        self.__processor.dataReceived(data)
                    except Exception as e:
                        error = e
                        break
                
        
        self.__running = False
        if self.__serial_port.isOpen():
            self.__serial_port.close()
        self.__processor.connectionClosed(error)
    
    @property
    def processor(self):
        """BasicSerialDataProcessor: The serial data processor associated with this manager."""
        return self.__processor
    
    def _write(self, data, flush=False):
        """Internal method to write binary data to the serial port.
        
        Args:
            data (bytearray): A byte array of binary data to send, may be ``None``
                to skip the write operation (to flush without writing).
            flush (bool): If ``True``, the write buffer of the serial port is
                flushed immediately after writing the data.
        """
        with self.__lock:
            if self.__running and self.__serial_port.isOpen():
                if data is not None: self.__serial_port.write(data)
                if flush: self.__serial_port.flush()
    
    def close(self):
        """Close the serial port and make sure the reader thread ends.
        """
        with self.__lock:
            if self.__running:
                self.__running = False
                #if hasattr(self.__serial_port, 'cancel_read'):
                #    self.__serial_port.cancel_read()
                self.__reader_thread.join()
    
    @property
    def is_running(self):
        """bool: Is the reader thread in running state?"""
        with self.__lock:
            return self.__running
    
    @property
    def is_open(self):
        """bool: Is the associated serial port open?"""
        with self.__lock:
            return self.__serial_port.isOpen()


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

