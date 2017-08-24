#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Western Digital Hardware Controller Server.

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

from threadedsockets.packets import BasicPacket
from threadedsockets.packetserver import PacketServerThread
from threadedsockets.socketserver import SocketListener
from threadedsockets.unixsockets import UnixSocketFactory

import wdhwdaemon.daemon


_logger = logging.getLogger(__name__)


class CloseConnectionWarning(Warning):
    """Exception class for indicating that an ongoing socket connection should be closed.
    """
    pass


class CommandPacket(BasicPacket):
    """Command packet implementation for the WD Hardware Controller Server.
    
    Attributes:
        keep_alive: Should the connection be kept alive after this command-response sequence?
    """
    
    # Flags
    FLAG_ERROR = 0b10000000
    FLAG_KEEP_ALIVE = 0b01000000
    
    # General commands
    CMD_VERSION_GET = 0x0001
    # Service administration commands
    CMD_DAEMON_SHUTDOWN = 0xFF01
    # PMC manager commands
    CMD_PMC_VERSION_GET = 0x0101
    CMD_PMC_STATUS_GET = 0x0103
    CMD_PMC_CONFIGURATION_SET = 0x0104
    CMD_PMC_CONFIGURATION_GET = 0x0105
    CMD_PMC_DLB_GET = 0x010B
    CMD_PMC_BLK_GET = 0x010D
    CMD_POWER_LED_SET = 0x0110
    CMD_POWER_LED_GET = 0x0111
    CMD_USB_LED_SET = 0x0112
    CMD_USB_LED_GET = 0x0113
    CMD_LCD_BACKLIGHT_INTENSITY_SET = 0x0114
    CMD_LCD_BACKLIGHT_INTENSITY_GET = 0x0115
    CMD_LCD_TEXT_SET = 0x0116
    CMD_PMC_TEMPERATURE_GET = 0x0121
    CMD_FAN_RPM_GET = 0x0123
    CMD_FAN_SPEED_SET = 0x0124
    CMD_FAN_SPEED_GET = 0x0125
    CMD_DRIVE_PRESENT_GET = 0x0131
    CMD_DRIVE_ENABLED_SET = 0x0132
    CMD_DRIVE_ENABLED_GET = 0x0133
    
    PACKET_MAGIC_BYTE = 0x0A5
    FLAGS_FIELD_SIZE = 1
    IDENTIFIER_FIELD_SIZE = 2
    LENGTH_FIELD_SIZE = 1
    
    def createResponse(self, parameter=None, more_flags=0, mirror_keep_alive=True):
        """Create a response packet for this command.
        
        Args:
            parameter (bytearray): The optional parameter value of the packet; may be
                ``None`` to indicate an empty parameter field.
            more_flags (int): The optional flags of the packet.
            mirror_keep_alive (bool): Use the keep-alive value from the command packet?
        
        Returns:
            ResponsePacket: The response packet.
        """
        flags = more_flags
        if mirror_keep_alive:
            if self.keep_alive:
                flags |= self.FLAG_KEEP_ALIVE
            else:
                flags &= ~self.FLAG_KEEP_ALIVE
        return ResponsePacket(self.identifier, parameter=parameter, flags=flags)
    
    def createErrorResponse(self, error_code, parameter=None, more_flags=0, mirror_keep_alive=True):
        """Create an error response packet for this command.
        
        Args:
            error_code (int): The error code associated with this error response packet.
            parameter (bytearray): The optional parameter value of the packet; may be
                ``None`` to indicate an empty parameter field.
            more_flags (int): The optional flags of the packet.
            mirror_keep_alive (bool): Use the keep-alive value from the command packet?
        
        Returns:
            ResponsePacket: The response packet.
        """
        flags = more_flags
        if mirror_keep_alive:
            if self.keep_alive:
                flags |= self.FLAG_KEEP_ALIVE
            else:
                flags &= ~self.FLAG_KEEP_ALIVE
        return ResponsePacket(self.identifier, error_code=error_code, parameter=parameter, flags=flags)
    
    @property
    def keep_alive(self):
        """bool: Should the connection be kept alive after this command-response sequence?"""
        return (self.flags & self.FLAG_KEEP_ALIVE) == self.FLAG_KEEP_ALIVE


class ResponsePacket(CommandPacket):
    """Response packet implementation for the WD Hardware Controller Server.
    
    Attributes:
        is_error: Does this packet indicate an error?
        error_code: The error code associated with this packet.
        parameter: The parameter value of this packet.
    """
    
    # Error codes
    ERR_NO_ERROR = 0x000
    ERR_NO_SUCH_COMMAND = 0x00C
    ERR_PARAMETER_LENGTH_ERROR = 0x07E
    ERR_COMMAND_NOT_IMPLEMENTED = 0x0C0
    ERR_EXECUTION_FAILED = 0x0EF
    
    # LED command format
    RESP_LED_OFFSET_RED = 0
    RESP_LED_OFFSET_GREEN = 1
    RESP_LED_OFFSET_BLUE = 2
    RESP_LED_CONST = 0b00000001
    RESP_LED_BLINK = 0b00000010
    RESP_LED_PULSE = 0b00000100
    
    PACKET_MAGIC_BYTE = 0x05A
    
    def __init__(self, identifier, parameter=None, flags=0, error_code=ResponsePacket.ERR_NO_ERROR):
        """Initializes a new protocol packet.
        
        Args:
            identifer (int): The identifier of the packet.
            error_code (int): Optional error code associated with this packet; may be
                any of the ``ResponsePacket.ERR_*`` constants; defaults to no error.
            parameter (bytearray): The optional parameter value of the packet; may be
                ``None`` to indicate an empty parameter field.
            flags (int): The optional flags of the packet.
        
        Raises:
            InvalidPacketError: If the parameter is too large to fit into the packet.
        """
        self.__error_code = error_code
        self.__parameter = parameter
        if error_code != ResponsePacket.ERR_NO_ERROR:
            flags |= self.FLAG_ERROR
            parameter = bytearray([error_code])
            parameter.extend(self.__parameter)
        else:
            flags &= ~self.FLAG_ERROR
        super(ResponsePacket, self).__init__(identifier, parameter, flags)
    
    @property
    def is_error(self):
        """bool: Does this packet indicate an error?"""
        return (self.flags & self.FLAG_ERROR) == self.FLAG_ERROR
    
    @property
    def error_code(self):
        """int: The error code associated with this packet."""
        return self.__error_code
    
    @property
    def parameter(self):
        """bytearray: The parameter value of this packet."""
        return self.__parameter


class ServerThreadImpl(PacketServerThread):
    """Socket server thread implementation for the WD Hardware Controller Server.
    """
    
    VERSION = "WDHWD v1.0"
    
    def __init__(self, listener):
        """Initializes a new socket server thread that processes packet-structured data.
        
        Args:
            listener (SocketListener): The parent socket listener instance.
        """
        self.__hw_daemon = listener.hw_daemon
        self.__COMMANDS = {
                # General commands
                CommandPacket.CMD_VERSION_GET:                 self.__commandVersionGet,
                # Service administration commands
                CommandPacket.CMD_DAEMON_SHUTDOWN:             self.__commandDaemonShutdown,
                # PMC manager commands
                CommandPacket.CMD_PMC_VERSION_GET:             self.__commandPMCVersionGet,
                CommandPacket.CMD_PMC_STATUS_GET:              self.__commandPMCStatusGet,
                CommandPacket.CMD_PMC_CONFIGURATION_SET:       self.__commandPMCConfigurationSet,
                CommandPacket.CMD_PMC_CONFIGURATION_GET:       self.__commandPMCConfigurationGet,
                CommandPacket.CMD_PMC_DLB_GET:                 self.__commandPMCDLBGet,
                CommandPacket.CMD_PMC_BLK_GET:                 self.__commandPMCBLKGet,
                CommandPacket.CMD_POWER_LED_SET:               self.__commandPowerLEDSet,
                CommandPacket.CMD_POWER_LED_GET:               self.__commandPowerLEDGet,
                CommandPacket.CMD_USB_LED_SET:                 self.__commandUSBLEDSet,
                CommandPacket.CMD_USB_LED_GET:                 self.__commandUSBLEDGet,
                CommandPacket.CMD_LCD_BACKLIGHT_INTENSITY_SET: self.__commandLCDBacklightIntensitySet,
                CommandPacket.CMD_LCD_BACKLIGHT_INTENSITY_GET: self.__commandLCDBacklightIntensityGet,
                CommandPacket.CMD_LCD_TEXT_SET:                self.__commandLCDTextSet,
                CommandPacket.CMD_PMC_TEMPERATURE_GET:         self.__commandPMCTemperatureGet,
                CommandPacket.CMD_FAN_RPM_GET:                 self.__commandFanRPMGet,
                CommandPacket.CMD_FAN_SPEED_SET:               self.__commandFanSpeedSet,
                CommandPacket.CMD_FAN_SPEED_GET:               self.__commandFanSpeedGet,
                CommandPacket.CMD_DRIVE_PRESENT_GET:           self.__commandDrivePresentGet,
                CommandPacket.CMD_DRIVE_ENABLED_SET:           self.__commandDriveEnabledSet,
                CommandPacket.CMD_DRIVE_ENABLED_GET:           self.__commandDriveEnabledGet,
        }
        super(ServerThreadImpl, self).__init__(listener, CommandPacket)
    
    def connectionOpened(self, remote_socket, remote_address):
        peercred = remote_socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        (pid, uid, gid) = unpack('LLL', peercred)
        _logger.debug("%s(%d): Accepting connection from PID=%d, UID=%d, GID=%d at '%s'",
                      type(self).__name__,
                      self.thread_id,
                      pid, uid, gid,
                      repr(remote_address))
        #raise SocketSecurityException(
        #        "Connection refused for process (PID={0}, UID={1}, GID={2}) at '{3}'.".format(
        #                pid, uid, gid, repr(remote_address)))
    
    def connectionClosed(self, error):
        pass
    
    def packetReceived(self, packet):
        cmd_code = packet.identifier
        try:
            try:
                cmd_func = self.__COMMANDS[cmd]
            except KeyError:
                self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_NO_SUCH_COMMAND))
            else:
                cmd_func(packet)
        finally:
            if not packet.keep_alive:
                raise CloseConnectionWarning("End of transmission")
    
    def __commandVersionGet(self, packet):
        self.sendPacket(packet.createResponse(bytearray(self.VERSION)))
    
    def __commandDaemonShutdown(self, packet):
        self.sendPacket(packet.createResponse(mirror_keep_alive=False))
        self.__hw_daemon.shutdown()
    
    def __commandPMCVersionGet(self, packet):
        self.sendPacket(packet.createResponse(bytearray(self.__hw_daemon.pmc_version)))
    
    def __commandPMCStatusGet(self, packet):
        try:
            status = self.__hw_daemon.pmc.getStatus()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([status])))
    
    def __commandPMCConfigurationSet(self, packet):
        if (packet.parameter is None) or (len(packet.parameter) != 1):
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_PARAMETER_LENGTH_ERROR))
        try:
            self.__hw_daemon.pmc.setConfiguration(packet.parameter[0])
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse())
    
    def __commandPMCConfigurationGet(self, packet):
        try:
            cfg = self.__hw_daemon.pmc.getConfiguration()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([cfg])))
    
    def __commandPMCDLBGet(self, packet):
        try:
            dlb = self.__hw_daemon.pmc.getDLB()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([dlb])))
    
    def __commandPMCBLKGet(self, packet):
        try:
            blk = self.__hw_daemon.pmc.getBLK()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([blk])))
    
    def __commandPowerLEDSet(self, packet):
        self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def __commandPowerLEDGet(self, packet):
        try:
            status = self.__hw_daemon.pmc.getLEDStatus()
            blink = self.__hw_daemon.pmc.getLEDBlink()
            pulse = self.__hw_daemon.pmc.getPowerLEDPulse()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            response = bytearray([0, 0, 0])
            if (status & wdpmcprotocol.PMC_LED_POWER_RED) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_RED] |= ResponsePacket.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_POWER_RED) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_RED] |= ResponsePacket.RESP_LED_BLINK
            if (status & wdpmcprotocol.PMC_LED_POWER_GREEN) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_GREEN] |= ResponsePacket.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_POWER_GREEN) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_GREEN] |= ResponsePacket.RESP_LED_BLINK
            if (status & wdpmcprotocol.PMC_LED_POWER_BLUE) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_BLUE] |= ResponsePacket.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_POWER_BLUE) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_BLUE] |= ResponsePacket.RESP_LED_BLINK
            if pulse:
                response[ResponsePacket.RESP_LED_OFFSET_BLUE] |= ResponsePacket.RESP_LED_PULSE
            self.sendPacket(packet.createResponse(response))
    
    def __commandUSBLEDSet(self, packet):
        self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def __commandUSBLEDGet(self, packet):
        try:
            status = self.__hw_daemon.pmc.getLEDStatus()
            blink = self.__hw_daemon.pmc.getLEDBlink()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            response = bytearray([0, 0, 0])
            if (status & wdpmcprotocol.PMC_LED_USB_RED) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_RED] |= ResponsePacket.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_USB_RED) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_RED] |= ResponsePacket.RESP_LED_BLINK
            if (status & wdpmcprotocol.PMC_LED_USB_BLUE) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_BLUE] |= ResponsePacket.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_USB_BLUE) != 0:
                response[ResponsePacket.RESP_LED_OFFSET_BLUE] |= ResponsePacket.RESP_LED_BLINK
            self.sendPacket(packet.createResponse(response))
    
    def __commandLCDBacklightIntensitySet(self, packet):
        self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def __commandLCDBacklightIntensityGet(self, packet):
        try:
            intensity = self.__hw_daemon.pmc.getLCDBacklightIntensity()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([intensity])))
    
    def __commandLCDTextSet(self, packet):
        self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def __commandPMCTemperatureGet(self, packet):
        try:
            temp = self.__hw_daemon.pmc.getTemperature()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([(temp >> 8) & 0x0FF, temp & 0x0FF])))
    
    def __commandFanRPMGet(self, packet):
        try:
            rpm = self.__hw_daemon.pmc.getFanRPM()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([(rpm >> 8) & 0x0FF, rpm & 0x0FF])))
    
    def __commandFanSpeedSet(self, packet):
        if (packet.parameter is None) or (len(packet.parameter) != 1):
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_PARAMETER_LENGTH_ERROR))
        try:
            self.__hw_daemon.pmc.setConfiguration(packet.parameter[0])
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse())
    
    def __commandFanSpeedGet(self, packet):
        try:
            speed = self.__hw_daemon.pmc.getFanSpeed()
        except:
            self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([speed])))
    
    def __commandDrivePresentGet(self, packet):
        self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def __commandDriveEnabledSet(self, packet):
        self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def __commandDriveEnabledGet(self, packet):
        self.sendPacket(packet.createErrorResponse(ResponsePacket.ERR_COMMAND_NOT_IMPLEMENTED))


class WdHwServer(SocketListener):
    """WD Hardware Controller Server.
    
    Attributes:
        hw_daemon: The parent hardware controller daemon.
    """
    
    def __init__(self, hw_daemon, socket_path, socket_group=None, max_clients=10):
        """Initializes a new hardware controller server.
        
        Args:
            hw_daemon (wdhwdaemon.daemon.WdHwDaemon): The parent hardware controller daemon.
            socket_path (str): File path of the named UNIX domain socket.
            socket_group (str): Optional name of a group that gets access to the socket (or
                None to grant no group permissions).
            max_clients (int): Maximum number of concurrent clients.
        """
        self.__hw_daemon = hw_daemon
        socket_factory = UnixSocketFactory(socket_path)
        server_socket = socket_factory.bindSocket(socket_group)
        super(WdHwServer, self).__init__(server_socket, max_clients, server_thread_class=ServerThreadImpl)
    
    @property
    def hw_daemon(self):
        """wdhwdaemon.daemon.WdHwDaemon: The parent hardware controller daemon."""
        return self.__hw_daemon


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

