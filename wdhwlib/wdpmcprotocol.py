#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Western Digital PMC Controller Interface Protocol Implementation.

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


import logging
import re
import serial
import threading

from messagequeue import Message
from messagequeue.threaded import Handler

from threadedserial import SerialConnectionManager, TerminatedPacketProcessor


_logger = logging.getLogger(__name__)


# PMC serial interface configuration
PMC_UART_PORT_DEFAULT = "/dev/ttyS0"
_PMC_UART_BAUDRATE = 9600
_PMC_UART_DATABITS = serial.EIGHTBITS
_PMC_UART_PARITY = serial.PARITY_NONE
_PMC_UART_STOPBITS = serial.STOPBITS_ONE

# PMC serial protocol transmission line coding
_PMC_LINE_ENCODING = "ascii"
_PMC_LINE_TERMINATOR = b'\r'
_PMC_LINE_STRIP_BYTES = b' \n\t'
_PMC_LINE_STRIP_CHARS = str(_PMC_LINE_STRIP_BYTES, _PMC_LINE_ENCODING)

# PMC serial protocol responses
_PMC_RESPONSE_TIMEOUT = 5.0
_PMC_RESPONSE_ACKNOWLEDGE = "ACK"
_PMC_RESPONSE_FAILURE = "ERR"
_PMC_RESPONSE_INTERRUPT = "ALERT"

_PMC_REGEX_NUMBER_HEX = re.compile(r"^([a-fA-F0-9]+)$")
#_PMC_REGEX_NUMBER_DEC = re.compile(r"^([0-9]+)$")

# PMC serial protocol commands
_PMC_COMMAND_VERSION = "VER"
_PMC_COMMAND_CONFIGURATION = "CFG"
_PMC_COMMAND_STATUS = "STA"
_PMC_COMMAND_LED_STATUS = "LED"
_PMC_COMMAND_LED_BLINK = "BLK"
_PMC_COMMAND_LED_PULSE = "PLS"
_PMC_COMMAND_LCD_BACKLIGHT = "BKL"
_PMC_COMMAND_LCD_TEXT_N = "LN{:d}"
_PMC_COMMAND_TEMPERATURE = "TMP"
_PMC_COMMAND_FAN_RPM = "RPM"
_PMC_COMMAND_FAN_SPEED = "FAN"
_PMC_COMMAND_DRIVEBAY_DRIVE_ENABLED = "DE0"
_PMC_COMMAND_DRIVEBAY_DRIVE_PRESENT = "DP0"
_PMC_COMMAND_DRIVEBAY_POWERUP_SET = "DLS"
_PMC_COMMAND_DRIVEBAY_POWERUP_CLEAR = "DLC"
_PMC_COMMAND_INTERRUPT_MASK = "IMR"
_PMC_COMMAND_INTERRUPT_STATUS = "ISR"
_PMC_COMMAND_DLB = "DLB"

#PMC interrrupts
PMC_INTERRUPT_MASK_NONE              = 0b00000000
PMC_INTERRUPT_MASK_ALL               = 0b11111111
PMC_INTERRUPT_POWER_2_STATE_CHANGED  = 0b00000010
PMC_INTERRUPT_POWER_1_STATE_CHANGED  = 0b00000100
PMC_INTERRUPT_DRIVE_PRESENCE_CHANGED = 0b00010000

#PMC power-up status
PMC_STATUS_POWER_2_UP = 0b00000010
PMC_STATUS_POWER_1_UP = 0b00000100

#PMC LED status
PMC_LED_NONE                     = 0b00000000
PMC_LED_POWER_BLUE               = 0b00000001
PMC_LED_POWER_RED                = 0b00000010
PMC_LED_POWER_GREEN              = 0b00000100
PMC_LED_POWER_PURPLE             = PMC_LED_POWER_BLUE | PMC_LED_POWER_RED
PMC_LED_POWER_TURQUOIS           = PMC_LED_POWER_BLUE | PMC_LED_POWER_GREEN
PMC_LED_POWER_YELLOW             = PMC_LED_POWER_RED  | PMC_LED_POWER_GREEN
PMC_LED_POWER_WHITE              = PMC_LED_POWER_BLUE | PMC_LED_POWER_RED | PMC_LED_POWER_GREEN
PMC_LED_POWER_MASK               = PMC_LED_POWER_BLUE | PMC_LED_POWER_RED | PMC_LED_POWER_GREEN
PMC_LED_USB_RED                  = 0b00001000
PMC_LED_USB_BLUE                 = 0b00010000
PMC_LED_USB_PURPLE               = PMC_LED_USB_RED | PMC_LED_USB_BLUE
PMC_LED_USB_MASK                 = PMC_LED_USB_RED | PMC_LED_USB_BLUE


class PMCCommandException(Exception):
    """Base exception class for WD PMC protocol errors.
    """
    pass


class PMCCommandTimeoutError(PMCCommandException):
    """Exception class to signal communication timeouts.
    """
    pass


class PMCUnexpectedResponseError(PMCCommandException):
    """Exception class to signal reception of unexpected responses.
    """
    pass


class PMCCommandRejectedException(PMCCommandException):
    """Exception class to signal failure (rejection) of a command.
    """
    pass


class PMCInterruptCallback(object):
    """Callback interface for out-of-sequence message callbacks.
    """
    
    def interruptReceived(self):
        """Callback for receiving an interrupt notification from the PMC.
        
        This callback is invoked on a dedicated interrupt handler thread and
        may be blocked for processing the interrupt. Fresh PMC commands (such
        as querying the interrupt status) may be issued directly on this
        thread.
        """
        pass
    
    def sequenceError(self, code, value):
        """Callback invoked when receiving an out-of-sequence message.
        
        This callback is invoked on a dedicated interrupt handler thread and
        may be blocked for processing. Fresh PMC commands may be issued
        directly on this thread.
        
        Args:
            code (str): The response code of the received message.
            value (str): The response argument of the received message.
        """
        pass
    
    def connectionClosed(self, error):
        """Callback invoked when the underlying connection to the PMC was closed.
        
        This callback is invoked on a dedicated interrupt handler thread and
        may be blocked for processing.
        
        Args:
            error (Exception): If not ``None``, the communication ended due to this
                ``Exception``.
        """
        pass


class PMCInterruptHandler(Handler):
    """Message queue handler for receiving interrupts and other out-of-sequence messages.
    """
    
    MSG_INTERRUPT = Handler.NEXT_MSG_ID
    MSG_OUTOFSEQUENCE = MSG_INTERRUPT + 1
    MSG_CONNECTION_CLOSED = MSG_OUTOFSEQUENCE + 1
    NEXT_MSG_ID = MSG_CONNECTION_CLOSED + 1
    
    def __init__(self, interrupt_callback):
        """Initializes a new interrupt queue handler.
        
        Args:
            interrupt_callback (PMCInterruptCallback): The associated callback
                implementation that consumes interrupts.
        """
        super().__init__(True)
        self.__callback = interrupt_callback
    
    def handleMessage(self, msg):
        if msg.what == PMCInterruptHandler.MSG_INTERRUPT:
            self.__callback.interruptReceived()
        elif msg.what == PMCInterruptHandler.MSG_OUTOFSEQUENCE:
            self.__callback.sequenceError(msg.obj[0], msg.obj[1])
        elif msg.what == PMCInterruptHandler.MSG_CONNECTION_CLOSED:
            self.__callback.connectionClosed(msg.obj)
        else:
            super().handleMessage(msg)


class PMCProcessor(TerminatedPacketProcessor):
    """A packet processor that transceives WD PMC protocol frames.
    """
    
    def __init__(self, interrupt_handler):
        """Initializes a new WD PMC protocol frame processor."""
        super().__init__(terminator = _PMC_LINE_TERMINATOR,
                         strip = _PMC_LINE_STRIP_BYTES)
        self.__interrupt_handler = interrupt_handler
        self.__response = None
        self.__response_pending = False
        self.__response_condition = threading.Condition()
        self.__command_sequence_lock = threading.RLock()
    
    def connectionOpened(self, serial_connection_manager):
        self.__interrupt_handler.start()
        super().connectionOpened(serial_connection_manager)
    
    def connectionClosed(self, error):
        super().connectionClosed(error)
        self.__interrupt_handler.sendMessage(
            Message(PMCInterruptHandler.MSG_CONNECTION_CLOSED, error))
        self.__interrupt_handler.join()
    
    def packetReceived(self, packet):
        with self.__response_condition:
            response = self.__decodeResponse(packet)
            (response_code, response_value) = response
            if response_code == _PMC_RESPONSE_INTERRUPT:
                # ALERT received
                _logger.debug("%s: Interrupt '%s' received",
                              type(self).__name__,
                              response_code)
                self.__interrupt_handler.sendMessage(
                    Message(PMCInterruptHandler.MSG_INTERRUPT))
            elif self.__response_pending:
                # command response received
                self.__response = response
                self.__response_pending = False
                self.__response_condition.notifyAll()
            else:
                # unexpected packet received (this is probably the response to
                # a command that timed out)
                _logger.error("%s: Unexpected out-of-order response '%s'",
                              type(self).__name__,
                              response_code)
                self.__interrupt_handler.sendMessage(
                    Message(PMCInterruptHandler.MSG_OUTOFSEQUENCE, response))
    
    def __encodeCommand(self, command):
        """Internal method to encode a command string for transmission over the serial line.
        
        Args:
            command (str): The command as string.
        
        Returns:
            bytearray: The encoded command packet.
        """
        _logger.debug("%s: Encoding command '%s'",
                      type(self).__name__,
                      command)
        return command.encode(_PMC_LINE_ENCODING, 'ignore')
        
    def __decodeResponse(self, response_packet):
        """Internal method to decode a response packet received over the serial line.
        
        Args:
            response_packet (bytearray): The response packet as byte array.
        
        Returns:
            tuple(str, str): A tuple (response_code, response_value) containing the
            decoded response code string and, if any, the decoded response argument
            string. response_value is None if the response does not have a response
            argument string.
        """
        response = response_packet.decode(_PMC_LINE_ENCODING, 'ignore')
        _logger.debug("%s: Decoding response '%s'",
                      type(self).__name__,
                      response)
        (response_code, separator, response_value) = response.partition("=")
        response_code = response_code.strip(_PMC_LINE_STRIP_CHARS).upper()
        if len(separator) > 0:
            response_value = response_value.strip(_PMC_LINE_STRIP_CHARS)
        else:
            response_value = None
        return (response_code, response_value)
    
    def __sendCommandAndWaitForResponse(self, command):
        """Internal method to send a command to the PMC and wait for the response.
        
        The method blocks until a response is received or the response
        timeout expires.
        
        Args:
            command (str): The command as string.
        
        Returns:
            tuple(str, str): A tuple (response_code, response_value) containing the
            received response split into the response code response_code and the
            response argument response_value. response_value is None if the response
            does not have a response argument.
        
        Raises:
            PMCCommandTimeoutError: The response timeout was reached before
                receiving a response.
        """
        with self.__command_sequence_lock:
            with self.__response_condition:
                self.__response = None
                self.__response_pending = True
                self.sendPacket(self.__encodeCommand(command))
                self.__response_condition.wait(_PMC_RESPONSE_TIMEOUT)
                if self.__response is None:
                    self.__response_pending = False
                    raise PMCCommandTimeoutError("No response received before "
                                                 "timeout was reached")
                return self.__response
    
    def transceiveCommand(self, command_code, command_value=None):
        """Send a command to the PMC and wait for the corresponding response.
        
        The method blocks until a response is received or the response
        timeout expires.
        
        Args:
            command_code (str): The command code as string.
            command_value (str): The command argument as string.
        
        Returns:
            str: For setter commands (commands that are simply acknowledged with
            an ACK packet), this method returns None on success. For getter
            commands (commands that are acknowledged with the command code and a
            response argument), this method returns the response argument string.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        command = command_code
        if command_value is not None:
            command = "{0}={1}".format(command_code, command_value)
        (response_code, response_value) = self.__sendCommandAndWaitForResponse(command)
        if response_code == _PMC_RESPONSE_ACKNOWLEDGE:
            # ACK received
            return None
        elif response_code == _PMC_RESPONSE_FAILURE:
            # ERR received
            raise PMCCommandRejectedException()
        elif response_code == command_code:
            # data received
            return response_value
        else:
            # unexpected response received
            raise PMCUnexpectedResponseError("Unexpected response '{0}' "
                                             "received".format(response_code))


class PMCCommands(PMCInterruptCallback):
    """Implements a high-level interface to the Western Digital PMC.
    """
    
    def __init__(self):
        """Initializes a new instance of the PMC high-level interface."""
        super().__init__()
    
    def connect(self, port_name=PMC_UART_PORT_DEFAULT):
        """Connect to the PMC chip.
        
        Args:
            port_name (str): The name of the serial port that the PMC is attached to.
        """
        serial_port = serial.Serial(port = port_name,
                                    baudrate = _PMC_UART_BAUDRATE,
                                    bytesize = _PMC_UART_DATABITS,
                                    parity = _PMC_UART_PARITY,
                                    stopbits = _PMC_UART_STOPBITS)
        self.__processor = PMCProcessor(PMCInterruptHandler(self))
        self.__conn_manager = SerialConnectionManager(
                serial_port,
                self.__processor)
    
    def close(self):
        """Close the connection to the PMC chip.
        
        This method blocks until cleanup completed.
        """
        self.__conn_manager.close()
        self.__processor = None
        self.__conn_manager = None
    
    def getVersion(self):
        """Get the PMC version information.
        
        Returns:
            str: This method returns the full version string (which is expected to
            be in the format r"WD PMC v\d+").
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: VER
        # Response: VER=WD PMC v[[:digit:]]+
        #   - Observed value (always): "WD PMC v17"
        return self.__processor.transceiveCommand(_PMC_COMMAND_VERSION)
    
    def getConfiguration(self):
        """Get PMC configuration register.
        
        Returns:
            int: Configuration register value.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: CFG
        # Response: CFG=[[:xdigit:]]+
        #   - Observed values:
        #       - Upon power-up: "03"
        #   - Interpretation: See setConfiguration()
        config_field = self.__processor.transceiveCommand(_PMC_COMMAND_CONFIGURATION)
        match = _PMC_REGEX_NUMBER_HEX.match(config_field)
        if match is not None:
            config_mask = int(match.group(1), 16)
            return config_mask
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(config_field))
    
    def setConfiguration(self, configuration):
        """Set PMC configuration register.
        
        Args:
            configuration (int): New configuration register value.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: CFG=%X
        #   - Parameter (1 byte):
        #       - Bit 0: automatic HDD power enable based on presence detection
        #       - Bit 1: ??? (set upon power-up)
        #       - Bit 2-7: ??? (cleared upon power-up)
        # Response: ACK | ERR
        configuration_mask = configuration
        configuration_field = "{0:02X}".format(configuration_mask & 0x0FF)
        self.__processor.transceiveCommand(_PMC_COMMAND_CONFIGURATION, status_field)
    
    def getStatus(self):
        """Get the PMC power-up status information.
        
        Returns:
            int: Power-up status register value.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: STA
        # Response: STA=[[:xdigit:]]+
        #   - Observed values:
        #       - Powered up with power adapter at socket 1 plugged in: "6c"
        #       - Powered up with power adapter at socket 2 plugged in: "6a"
        #       - Powered up with power adapters at sockets 1 and 2 plugged in: "6e"
        #       - Powered up with only drive in bay 0 (right) inserted: "6c"
        #       - Powered up with only drive in bay 1 (left) inserted: "6c"
        #       - Powered up with no drives inserted (not properly verified!): "4c"
        #       - Powered up with both drives inserted: "6c"
        #   - Interpretation: bitmask for power-up (?) status
        #       - Bit 0: ??? (cleared upon power-up)
        #       - Bit 1: Power adapter at socket 2 plugged in
        #       - Bit 2: Power adapter at socket 1 plugged in
        #       - Bit 3: ??? (set upon power-up)
        #       - Bit 4: ??? (cleared upon power-up)
        #       - Bit 5-6: ??? (set upon power-up)
        #       - Bit 7: ??? (cleared upon power-up)
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_STATUS)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            status_mask = int(match.group(1), 16)
            return status_mask
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def getTemperature(self):
        """Get the PMC temperature reading.
        
        Returns:
            int: The temperature in degrees Celsius.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: TMP
        # Response: TMP=[[:xdigit:]]+
        #   - Observed values: "1f", "28", "2f", "2e", etc.
        #   - Interpretation: Hexadecimal value representing the temperature in degrees Celsius
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_TEMPERATURE)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            temperature = int(match.group(1), 16)
            return temperature
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def getLEDStatus(self):
        """Get the LED steady status.
        
        Returns:
            int: A combination of ``PMC_LED_*`` flags indicating the LED and color
                that is turned on.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: LED
        # Response: LED=[[:xdigit:]]+
        #   - Observed values:
        #       - Upon power-up: "00"
        #   - Interpretation: See setLEDStatus()
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_LED_STATUS)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            status_mask = int(match.group(1), 16)
            return status_mask
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def setLEDStatus(self, on_mask):
        """Set the LED steady status.
        
        Args:
            on_mask (int): A combination of ``PMC_LED_*`` flags indicating the LED
                and color to turn on.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: LED=%X
        #   - Parameter (1 byte):
        #       - 0b00000000: all LEDs off
        #       - 0b00000001: power LED blue
        #       - 0b00000010: power LED red
        #       - 0b00000011: power LED purple (blue+red)
        #       - 0b00000100: power LED green
        #       - 0b00000101: power LED turquois (blue+green)
        #       - 0b00000110: power LED yellowish (red+green)
        #       - 0b00000111: power LED white (blue+red+green)
        #       - 0b00001000: USB button LED red
        #       - 0b00010000: USB button LED blue
        #       - 0b00011000: USB button LED purple (red+blue)
        # Response: ACK | ERR
        status_field = "{0:02X}".format(on_mask & 0x01F)
        self.__processor.transceiveCommand(_PMC_COMMAND_LED_STATUS, status_field)
    
    def getLEDBlink(self):
        """Get the LED blinking status.
        
        Returns:
            int: A combination of ``PMC_LED_*`` flags indicating the LED and color
                that blinks.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: BLK
        # Response: BLK=[[:xdigit:]]+
        #   - Observed values:
        #       - Upon power-up: "01"
        #   - Interpretation: See setLEDBlink()
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_LED_BLINK)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            status_mask = int(match.group(1), 16)
            return status_mask
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def setLEDBlink(self, blink_mask):
        """Set the LED blinking status.
        
        Args:
            blink_mask (int): A combination of ``PMC_LED_*`` flags indicating the
                LED and color to blink.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: BLK=%X
        #   - Parameter (1 byte):
        #       - 0b00000000: no blink
        #       - 0b00000001: power LED blink blue
        #       - 0b00000010: power LED blink red
        #       - 0b00000011: power LED blink purple or toggle blue/red (depends on steady LED state)
        #       - 0b00000100: power LED blink green
        #       - 0b00000101: power LED blink turquois or toggle blue/green (depends on steady LED state)
        #       - 0b00000110: power LED blink yellowish or toggle red/green (depends on steady LED state)
        #       - 0b00000111: power LED blink white or toggle two combinations of blue/red/green (depends on steady LED state)
        #       - 0b00001000: USB button LED blink red
        #       - 0b00010000: USB button LED blink blue
        #       - 0b00011000: USB button LED blink purple or toggle blue/red (depends on steady LED state)
        # Response: ACK | ERR
        status_field = "{0:02X}".format(blink_mask & 0x01F)
        self.__processor.transceiveCommand(_PMC_COMMAND_LED_BLINK, status_field)
    
    def getPowerLEDPulse(self):
        """Is the power LED pulsing?
        
        Returns:
            bool: If ``True``, pulsing is turned on.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: PLS
        # Response: PLS=[[:xdigit:]]+
        #   - Observed values:
        #       - Upon power-up: "00"
        #   - Interpretation: See setPowerLEDPulse()
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_LED_PULSE)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            status_value = int(match.group(1), 16)
            return status_value != 0
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def setPowerLEDPulse(self, pulse):
        """Turn power LED pulsing on or off.
        
        Args:
            pulse (bool): If ``True``, pulsing is turned on.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: PLS=%X
        #   - Parameter (1 byte):
        #       - 0b00000000: no pulse
        #       - 0b00000001: power LED pulse blue
        # Response: ACK | ERR
        pulse_mask = PMC_LED_NONE
        if pulse: pulse_mask = PMC_LED_POWER_BLUE
        status_field = "{0:02X}".format(pulse_mask & 0x001)
        self.__processor.transceiveCommand(_PMC_COMMAND_LED_PULSE, status_field)

    def getLCDBacklightIntensity(self):
        """Get LCD backlight intensity.
        
        Returns:
            int: The LCD backlight intensity in percent.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: BKL
        # Response: BKL=[[:xdigit:]]+
        #   - Observed values:
        #       - Upon power-up: "64" -> 100%
        #   - Interpretation: Hexadecimal representation (1 byte) of the LCD backlight intensity in percent
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_LCD_BACKLIGHT)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            backlight_value = int(match.group(1), 16)
            return backlight_value
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))

    def setLCDBacklightIntensity(self, intensity):
        """Set LCD backlight intensity.
        
        Args:
            intensity (int): The LCD backlight intensity in percent.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: BKL=%X
        #   - Parameter (1 byte): LCD backlight intensity in percent
        # Response: ACK | ERR
        if intensity < 0:
            intensity = 0
        elif intensity > 100:
            intensity = 100
        intensity_field = "{0:02X}".format(intensity)
        self.__processor.transceiveCommand(_PMC_COMMAND_LCD_BACKLIGHT, intensity_field)
    
    def setLCDText(self, line, value):
        """Set a line of text on the LCD.
        
        Args:
            line (int): The line number.
            value (str): The text to be displayed on the given line.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: LN%d=%s
        # Response: ACK | ERR
        if line < 0:
            line = 0
        if line > 9:
            line = 0
        command_field = _PMC_COMMAND_LCD_TEXT_N.format(line)
        # TODO: Check value for valid characters!
        text_field = value
        self.__processor.transceiveCommand(command_field, text_field)
    
    def getFanRPM(self):
        """Get the measured fan speed in RPM.
        
        Returns:
            int: The fan speed in RPM.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: RPM
        # Response: RPM=[[:xdigit:]]+
        #   - Observed values:
        #       - "10E0" at FAN=50 -> 4320 RPM with fan at 80%
        #       - "0726" at FAN=1f -> 1830 RPM with fan at 31%
        #   - Interpretation: Hexadecimal value (2 bytes) representing the fan speed in RPM
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_FAN_RPM)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            speed_rpm = int(match.group(1), 16)
            return speed_rpm
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def getFanSpeed(self):
        """Get the configured fan speed in percent.
        
        Returns:
            int: The fan speed in percent.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: FAN
        # Response: FAN=[[:xdigit:]]+
        #   - Observed values:
        #       - Upon power-up: "50" -> fan at 80%
        #   - Interpretation: Hexadecimal value (1 byte) representing the fan speed in percent
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_FAN_SPEED)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            speed = int(match.group(1), 16)
            return speed
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def setFanSpeed(self, speed):
        """Set the fan speed in percent.
        
        Args:
            speed (int): The fan speed in percent (valid range 0 <= speed <= 100).
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: FAN=%X
        #   - Parameter (1 byte): fan speed in percent (from 0% to 99%)
        # Response: ACK | ERR
        if speed < 0:
            speed = 0
        elif speed > 99:
            # WD's wdhws seems to enforce this limit so we should probably do this too!
            speed = 99
        speed_field = "{0:02X}".format(speed)
        self.__processor.transceiveCommand(_PMC_COMMAND_FAN_SPEED, speed_field)
    
    def getDriveEnabledMask(self):
        """Get drive bay power-up status information.
        
        Returns:
            int: Drive bay power-up status mask.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: DE0
        # Response: DE0=[[:xdigit:]]+
        #   - Observed values:
        #       - Only drive in bay 0 (right) powered-up: "f1"
        #       - Only drive in bay 1 (left) powered-up: "f2"
        #       - Drives in both bays powered-up: "f3"
        #       - Value changes as a result of DLS/DLC
        #   - Interpretation: bitmask (1 byte) for drive bays
        #       - Bit 0: set when drive in bay 0 (right) is powered-up, cleared when drive is absent or powered-down
        #       - Bit 1: set when drive in bay 1 (left) is powered-up, cleared when drive is absent or powered-down
        #       - Bit 2-3: ??? (always observed as cleared; may indicate presence for the two non-existent drive bays, cf. DL4100)
        #       - Bit 4-7: ??? (always observed as set)
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_DRIVEBAY_DRIVE_ENABLED)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            drivebay_mask = int(match.group(1), 16)
            return drivebay_mask
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def getDrivePresenceMask(self):
        """Get drive presence status information.
        
        Returns:
            int: Drive presence status mask.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: DP0
        # Response: DP0=[[:xdigit:]]+
        #   - Observed values:
        #       - Only drive in bay 0 (right) inserted: "8d"
        #       - Only drive in bay 1 (left) inserted: "8e"
        #       - Drives in both bays inserted: "8c"
        #       - Value does NOT change as a result of DLS/DLC
        #   - Interpretation: bitmask (1 byte) for drive bays
        #       - Bit 0: cleared when drive in bay 0 (right) is present, set when drive is absent
        #       - Bit 1: cleared when drive in bay 1 (left) is present, set when drive is absent
        #       - Bit 2-3: ??? (always observed as set; may indicate presence for the two non-existent drive bays, cf. DL4100)
        #       - Bit 4-6: ??? (always observed as cleared)
        #       - Bit 7: ??? (always observed as set)
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_DRIVEBAY_DRIVE_PRESENT)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            drivebay_mask = int(match.group(1), 16)
            return drivebay_mask
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def setDriveEnabled(self, bay_number, enable):
        """Change drive bay power state.
        
        Args:
            bay_number (int): The drive bay to change the power-up state for.
            enable (bool): A boolean flag indicating the new power-up state.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        drivebay_mask_field = "{0:02X}".format(1 << bay_number)
        if enable:
            # Command: DLS=%X
            #   - Parameter (1 byte): bitmask for drive bays
            #       - 0b00000001: Bay 0 (right)
            #       - 0b00000010: Bay 1 (left)
            # Response: ACK | ERR
            self.__processor.transceiveCommand(_PMC_COMMAND_DRIVEBAY_POWERUP_SET,
                                               drivebay_mask_field)
        else:
            # Command: DLC=%X
            #   - Parameter (1 byte): bitmask for drive bays
            #       - 0b00000001: Bay 0 (right)
            #       - 0b00000010: Bay 1 (left)
            # Response: ACK | ERR
            self.__processor.transceiveCommand(_PMC_COMMAND_DRIVEBAY_POWERUP_CLEAR,
                                               drivebay_mask_field)

    def setInterruptMask(self, mask=PMC_INTERRUPT_MASK_ALL):
        """Set the interrupt mask in order to enable/request interrupts.
        
        Args:
            mask (int): Interrupt mask value.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: IMR=FF
        #   - Parameter (1 byte): See getInterruptStatus()
        # Response: ACK | ERR
        mask_field = "{0:02X}".format(mask)
        self.__processor.transceiveCommand(_PMC_COMMAND_INTERRUPT_MASK,
                                           mask_field)
    
    def getInterruptStatus(self):
        """Get the pending interrupt status.
        
        Returns:
            int: Interrupt status register value.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: ISR
        # Response: ISR=[[:xdigit:]]+
        #   - Observed values:
        #       - Upon power-up: "00"
        #       - With IMR=FF and after receiving ALERT:
        #           - After unplugging and re-plugging power adapter (at socket 1) while powered off: "6c" (same value as STA)
        #           - After unplugging and re-plugging power adapter (at socket 2) while powered off: "6a" (same value as STA)
        #           - After unplugging and re-plugging power adapter (at both sockets) while powered off: "6e" (same value as STA)
        #           - After unplugging or (re-)plugging power adapter (at socket 1) while powered on: "04"
        #           - After unplugging or (re-)plugging power adapter (at socket 2) while powered on: "02"
        #           - After inserting or removing any drive: "10"
        #   - Original firmware operation:
        #       - result = ~(STA & 0x68) & ISR;
        #   - Interpretation: bitmask (1 byte) for pending interrupts
        #       - Bit 0: ??? (never observed as set)
        #       - Bit 1: Power adapter state changed on socket 2
        #       - Bit 2: Power adapter state changed on socket 1
        #       - Bit 3: ??? (never observed as set except on ISR==STA interrupt; ignored by original firmware)
        #       - Bit 4: Drive presence changed
        #       - Bit 5-6: ??? (never observed as set except on ISR==STA interrupt; ignored by original firmware)
        #       - Bit 7: ??? (never observed as set)
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_INTERRUPT_STATUS)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            interrupt_mask = int(match.group(1), 16)
            return interrupt_mask
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def getDLB(self):
        """TODO: What does DLB do???
        
        Returns:
            int: ???.
        
        Raises:
            PMCCommandRejectedException: If the PMC refused the command with
                an ERR packet.
            PMCCommandTimeoutError: If the response timeout was reached before
                receiving a response.
            PMCUnexpectedResponseError: If the received response does not
                match the sent command.
        """
        # Command: DLB
        # Response: DLB=[[:xdigit:]]+
        #   - Observed values:
        #       - Upon power-up: "00"
        #   - Original firmware operation:
        #         result = ((DLB >> (??? + 4)) & 1) != 0;
        #   - Interpretation: ???
        status_field = self.__processor.transceiveCommand(_PMC_COMMAND_DLB)
        match = _PMC_REGEX_NUMBER_HEX.match(status_field)
        if match is not None:
            status_value = int(match.group(1), 16)
            return status_value
        else:
            raise PMCUnexpectedResponseError("Response argument '{0}' "
                                             "does not match expected "
                                             "format".format(status_field))
    
    def interruptReceived(self):
        pass
    
    def sequenceError(self, code, value):
        pass
    
    def connectionClosed(self, error):
        pass


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

