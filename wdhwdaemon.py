#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Western Digital Hardware Controller Daemon.

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
import signal
import subprocess
import sys
import threading

import threadedsockets.packets
from threadedsockets.packetserver import PacketServerThread
from threadedsockets.socketserver import SocketListener
from threadedsockets.unixsockets import UnixSocketFactory
from threadedsockets import UnixSocketFactory

from wdhwlib.fancontroller import FanController, FanControllerCallback
from wdhwlib.temperature import TemperatureReader
from wdhwlib.wdpmcprotocol import PMCCommands
from wdhwlib import temperature, wdpmcprotocol


_logger = logging.getLogger(__name__)


class WdHwServerCloseConnectionWarning(Warning):
    """Exception class for indicating that an ongoing socket connection should be closed.
    """
    pass


class WdHwServerCommand(packets.BasicPacket):
    
    PACKET_MAGIC_BYTE = 0x0A5
    
    FLAGS_FIELD_SIZE = 1
    FLAG_ERROR = 0b10000000
    FLAG_KEEP_ALIVE = 0b01000000
    
    IDENTIFIER_FIELD_SIZE = 2
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
    
    LENGTH_FIELD_SIZE = 1
    
    def createResponse(self, parameter=None, more_flags=None, mirror_keep_alive=True):
        """Create a response packet for this command.
        
        """
        flags = more_flags
        if mirror_keep_alive:
            if self.keep_alive:
                flags |= self.FLAG_KEEP_ALIVE
            else:
                flags &= ~self.FLAG_KEEP_ALIVE
        return WdHwServerResponse(self.identifier, False, parameter, flags)
    
    def createErrorResponse(self, error_code, parameter=None, more_flags=None, mirror_keep_alive=True):
        """Create an error response packet for this command.
        
        """
        flags = more_flags
        if mirror_keep_alive:
            if self.keep_alive:
                flags |= self.FLAG_KEEP_ALIVE
            else:
                flags &= ~self.FLAG_KEEP_ALIVE
        error_param = bytearray([error_code])
        error_param.extend(parameter)
        return WdHwServerResponse(self.identifier, True, error_param, flags)
    
    @property
    def keep_alive(self):
        """bool: Should the connection be kept alive after this command-response sequence?"""
        return (self.flags & self.FLAG_KEEP_ALIVE) == self.FLAG_KEEP_ALIVE


class WdHwServerResponse(WdHwServerCommand):
    
    PACKET_MAGIC_BYTE = 0x05A
    
    ERR_NO_SUCH_COMMAND = 0x00C
    ERR_PARAMETER_LENGTH_ERROR = 0x07E
    ERR_COMMAND_NOT_IMPLEMENTED = 0x0C0
    ERR_EXECUTION_FAILED = 0x0EF
    
    RESP_LED_CONST = 0b00000001
    RESP_LED_BLINK = 0b00000010
    RESP_LED_PULSE = 0b00000100
    RESP_LED_OFFSET_RED = 0
    RESP_LED_OFFSET_GREEN = 1
    RESP_LED_OFFSET_BLUE = 2
    
    def __init__(self, identifier, is_error, parameter=None, flags=0):
        """Initializes a new protocol packet.
        
        Args:
            identifer (int): The identifier of the packet.
            is_error (bool): Does this packet indicate an error?
            parameter (bytearray): The optional parameter value of the packet; may be
                ``None`` to indicate an empty parameter field.
            flags (int): The optional flags of the packet.
        
        Raises:
            InvalidPacketError: If the parameter is too large to fit into the packet.
        """
        if is_error:
            flags |= self.FLAG_ERROR
        else:
            flags &= ~self.FLAG_ERROR
        super(WdHwServerResponse, self).__init__(identifier, parameter, flags)
    
    @property
    def is_error(self):
        """bool: Does this packet indicate an error?"""
        return (self.flags & self.FLAG_ERROR) == self.FLAG_ERROR


class WdHwServerThreadImpl(PacketServerThread):
    
    VERSION = "WDHWD v1.0"
    
    def __init__(self, listener):
        self.__hw_daemon = listener.hw_daemon
        self.__COMMANDS = {
                # General commands
                WdHwServerCommand.CMD_VERSION_GET: self.commandVersionGet,
                # Service administration commands
                WdHwServerCommand.CMD_DAEMON_SHUTDOWN: self.commandDaemonShutdown,
                # PMC manager commands
                WdHwServerCommand.CMD_PMC_VERSION_GET: self.commandPMCVersionGet,
                WdHwServerCommand.CMD_PMC_STATUS_GET: self.commandPMCStatusGet,
                WdHwServerCommand.CMD_PMC_CONFIGURATION_SET: self.commandPMCConfigurationSet,
                WdHwServerCommand.CMD_PMC_CONFIGURATION_GET: self.commandPMCConfigurationGet,
                WdHwServerCommand.CMD_PMC_DLB_GET: self.commandPMCDLBGet,
                WdHwServerCommand.CMD_PMC_BLK_GET: self.commandPMCBLKGet,
                WdHwServerCommand.CMD_POWER_LED_SET: self.commandPowerLEDSet,
                WdHwServerCommand.CMD_POWER_LED_GET: self.commandPowerLEDGet,
                WdHwServerCommand.CMD_USB_LED_SET: self.commandUSBLEDSet,
                WdHwServerCommand.CMD_USB_LED_GET: self.commandUSBLEDGet,
                WdHwServerCommand.CMD_LCD_BACKLIGHT_INTENSITY_SET: self.commandLCDBacklightIntensitySet,
                WdHwServerCommand.CMD_LCD_BACKLIGHT_INTENSITY_GET: self.commandLCDBacklightIntensityGet,
                WdHwServerCommand.CMD_LCD_TEXT_SET: self.commandLCDTextSet,
                WdHwServerCommand.CMD_PMC_TEMPERATURE_GET: self.commandPMCTemperatureGet,
                WdHwServerCommand.CMD_FAN_RPM_GET: self.commandFanRPMGet,
                WdHwServerCommand.CMD_FAN_SPEED_SET: self.commandFanSpeedSet,
                WdHwServerCommand.CMD_FAN_SPEED_GET: self.commandFanSpeedGet,
                WdHwServerCommand.CMD_DRIVE_PRESENT_GET: self.commandDrivePresentGet,
                WdHwServerCommand.CMD_DRIVE_ENABLED_SET: self.commandDriveEnabledSet,
                WdHwServerCommand.CMD_DRIVE_ENABLED_GET: self.commandDriveEnabledGet,
        }
        super(WdHwServerThreadImpl, self).__init__(listener, WdHwServerCommand)
    
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
                self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_NO_SUCH_COMMAND))
            else:
                cmd_func(packet)
        finally:
            if not packet.keep_alive:
                raise WdHwServerCloseConnectionWarning("End of transmission")
    
    def commandVersionGet(self, packet):
        self.sendPacket(packet.createResponse(bytearray(self.VERSION)))
    
    def commandDaemonShutdown(self, packet):
        self.sendPacket(packet.createResponse(mirror_keep_alive=False))
        self.__hw_daemon.shutdown()
    
    def commandPMCVersionGet(self, packet):
        self.sendPacket(packet.createResponse(bytearray(self.__hw_daemon.pmc_version)))
    
    def commandPMCStatusGet(self, packet):
        try:
            status = self.__hw_daemon.pmc.getStatus()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([status])))
    
    def commandPMCConfigurationSet(self, packet):
        if (packet.parameter is None) or (len(packet.parameter) != 1):
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_PARAMETER_LENGTH_ERROR))
        try:
            self.__hw_daemon.pmc.setConfiguration(packet.parameter[0])
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse())
    
    def commandPMCConfigurationGet(self, packet):
        try:
            cfg = self.__hw_daemon.pmc.getConfiguration()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([cfg])))
    
    def commandPMCDLBGet(self, packet):
        try:
            dlb = self.__hw_daemon.pmc.getDLB()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([dlb])))
    
    def commandPMCBLKGet(self, packet):
        try:
            blk = self.__hw_daemon.pmc.getBLK()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([blk])))
    
    def commandPowerLEDSet(self, packet):
        self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def commandPowerLEDGet(self, packet):
        try:
            status = self.__hw_daemon.pmc.getLEDStatus()
            blink = self.__hw_daemon.pmc.getLEDBlink()
            pulse = self.__hw_daemon.pmc.getPowerLEDPulse()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            response = bytearray([0, 0, 0])
            if (status & wdpmcprotocol.PMC_LED_POWER_RED) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_RED] |= WdHwServerResponse.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_POWER_RED) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_RED] |= WdHwServerResponse.RESP_LED_BLINK
            if (status & wdpmcprotocol.PMC_LED_POWER_GREEN) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_GREEN] |= WdHwServerResponse.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_POWER_GREEN) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_GREEN] |= WdHwServerResponse.RESP_LED_BLINK
            if (status & wdpmcprotocol.PMC_LED_POWER_BLUE) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_BLUE] |= WdHwServerResponse.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_POWER_BLUE) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_BLUE] |= WdHwServerResponse.RESP_LED_BLINK
            if pulse:
                response[WdHwServerResponse.RESP_LED_OFFSET_BLUE] |= WdHwServerResponse.RESP_LED_PULSE
            self.sendPacket(packet.createResponse(response))
    
    def commandUSBLEDSet(self, packet):
        self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def commandUSBLEDGet(self, packet):
        try:
            status = self.__hw_daemon.pmc.getLEDStatus()
            blink = self.__hw_daemon.pmc.getLEDBlink()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            response = bytearray([0, 0, 0])
            if (status & wdpmcprotocol.PMC_LED_USB_RED) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_RED] |= WdHwServerResponse.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_USB_RED) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_RED] |= WdHwServerResponse.RESP_LED_BLINK
            if (status & wdpmcprotocol.PMC_LED_USB_BLUE) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_BLUE] |= WdHwServerResponse.RESP_LED_CONST
            if (blink & wdpmcprotocol.PMC_LED_USB_BLUE) != 0:
                response[WdHwServerResponse.RESP_LED_OFFSET_BLUE] |= WdHwServerResponse.RESP_LED_BLINK
            self.sendPacket(packet.createResponse(response))
    
    def commandLCDBacklightIntensitySet(self, packet):
        self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def commandLCDBacklightIntensityGet(self, packet):
        try:
            intensity = self.__hw_daemon.pmc.getLCDBacklightIntensity()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([intensity])))
    
    def commandLCDTextSet(self, packet):
        self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def commandPMCTemperatureGet(self, packet):
        try:
            temp = self.__hw_daemon.pmc.getTemperature()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([(temp >> 8) & 0x0FF, temp & 0x0FF])))
    
    def commandFanRPMGet(self, packet):
        try:
            rpm = self.__hw_daemon.pmc.getFanRPM()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([(rpm >> 8) & 0x0FF, rpm & 0x0FF])))
    
    def commandFanSpeedSet(self, packet):
        if (packet.parameter is None) or (len(packet.parameter) != 1):
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_PARAMETER_LENGTH_ERROR))
        try:
            self.__hw_daemon.pmc.setConfiguration(packet.parameter[0])
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse())
    
    def commandFanSpeedGet(self, packet):
        try:
            speed = self.__hw_daemon.pmc.getFanSpeed()
        except:
            self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_EXECUTION_FAILED))
        else:
            self.sendPacket(packet.createResponse(bytearray([speed])))
    
    def commandDrivePresentGet(self, packet):
        self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def commandDriveEnabledSet(self, packet):
        self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_COMMAND_NOT_IMPLEMENTED))
    
    def commandDriveEnabledGet(self, packet):
        self.sendPacket(packet.createErrorResponse(WdHwServerResponse.ERR_COMMAND_NOT_IMPLEMENTED))


class WdHwServer(SocketListener):
    
    def __init__(self, hw_daemon, socket_path, socket_group=None, max_clients=10):
        """Initializes a new hardware controller server.
        
        Args:
            hw_daemon (WdHwDaemon): The parent hardware controller daemon.
            socket_path (str): File path of the named UNIX domain socket.
            socket_group (str): Optional name of a group that gets access to the socket (or
                None to grant no group permissions).
            max_clients (int): Maximum number of concurrent clients.
        """
        self.__hw_daemon = hw_daemon
        socket_factory = UnixSocketFactory(socket_path)
        server_socket = socket_factory.bindSocket(socket_group)
        super(WdHwServer, self).__init__(server_socket, max_clients, server_thread_class=WdHwServerThreadImpl)
    
    @property
    def hw_daemon(self):
        """WdHwDaemon: The parent hardware controller daemon."""
        return self.__hw_daemon


class PMCCommandsImpl(PMCCommands):
    
    def __init__(self):
        super(PMCCommandsImpl, self).__init__()
    
    def interruptReceived(self):
        isr = self.getInterruptStatus()
        _logger.info("%s: Received interrupt %X",
                     type(self).__name__,
                     isr)
    
    def sequenceError(self, code, value):
        _logger.error("%s: Out-of-sequence PMC message received (code = '%s', value = '%s')",
                     type(self).__name__,
                     code, value)
    
    def connectionClosed(self, error):
        if error is not None:
            _logger.error("%s: PMC connection closed due to error: %s",
                         type(self).__name__,
                         repr(error))


class FanControllerImpl(FanController):
    
    def __init__(self, hw_daemon, pmc, temperature_reader, disk_drives, num_dimms):
        self.__hw_daemon = hw_daemon
        super(FanControllerImpl, self).__init__(pmc, temperature_reader, disk_drives, num_dimms)
    
    def controllerStarted(self):
        _logger.debug("%s: Fan controller started",
                      type(self).__name__)
        self.__hw_daemon.setLEDNormalState()
    
    def controllerStopped(self):
        _logger.debug("%s: Fan controller stopped",
                      type(self).__name__)
        self.__hw_daemon.setFanBootState()
        self.__hw_daemon.setLEDWarningState()
    
    def fanError(self):
        _logger.error("%s: Fan error detected",
                      type(self).__name__)
        self.__hw_daemon.initiateImmediateSystemShutdown()
        self.__hw_daemon.setLEDErrorState()
    
    def shutdownRequestImmediate(self):
        _logger.error("%s: Overheat condition requires immediate shutdown",
                      type(self).__name__)
        self.__hw_daemon.initiateImmediateSystemShutdown()
        self.__hw_daemon.setLEDErrorState()
    
    def shutdownRequestDelayed(self):
        _logger.error("%s: Overheat condition requires shutdown with grace period",
                      type(self).__name__)
        self.__hw_daemon.initiateDelayedSystemShutdown()
        self.__hw_daemon.setLEDErrorState()
    
    def shutdownCancelPending(self):
        self.__hw_daemon.cancelPendingSystemShutdown()
        self.__hw_daemon.setLEDNormalState()
    
    def levelChanged(self, new_level, old_level):
        _logger.debug("%s: Temperature alert level changed from %d to %d",
                      type(self).__name__,
                      old_level, new_level)


class WdHwDaemonConfig(object):
    """Hardware controller daemon configuration holder.
    """
    
    def __init__(self):
        """Initializes a new hardware controller daemon configuration holder."""
        super(WdHwDaemonConfig, self).__init__()
        self.__pmc_port = wdpmcprotocol.PMC_UART_PORT_DEFAULT
        self.__pmc_test = True
        self.__disk_drives = temperature.HDSMART_DISKS
        self.__memory_dimms = 2
        self.__socket_path = "/tmp/wdhwdaemon"
        self.__socket_group = None
        self.__socket_max_clients = 10
    
    @property
    def pmc_port(self):
        """str: Name of the serial port that the PMC is attached to."""
        return self.__pmc_port
    
    @property
    def pmc_test(self):
        """bool: Enable PMC protocol testing mode?"""
        return self.__pmc_test
    
    @property
    def disk_drives(self):
        """List(str): List of disk drives in the drive bays (in the order of PMC drive bay flags)."""
        return self.__disk_drives
    
    @property
    def memory_dimms(self):
        """int: Number of memory DIMMs to monitor."""
        return self.__memory_dimms
    
    @property
    def socket_path(self):
        """str: Path of the UNIX domain socket for controlling the hardware controller daemon."""
        return self.__socket_path
    
    @property
    def socket_group(self):
        """str: Group that is granted access to the UNIX domain socket."""
        return self.__socket_group
    
    @property
    def socket_max_clients(self):
        """int: Maximum number of clients that can concurrently connect to the UNIX domain socket."""
        return self.__socket_max_clients


class WdHwDaemon(SocketListener):
    """Hardware controller daemon.
    """
    
    def __init__(self, config):
        """Initializes a new hardware controller daemon.
        
        Args:
            config (WdHwDaemonConfig): Configuration object.
        """
        super(WdHwDaemon, self).__init__()
        self.__config = config
        self.__lock = threading.RLock()
        self.__shutdown = False
        self.__pmc = None
        self.__pmc_version = ""
        self.__temperature_reader = None
        self.__fan_controller = None
    
    def __sigHandler(self, sig, frame):
        del frame
        if sig == signal.SIGTERM:
            self.shutdown()
        elif sig == signal.SIGINT:
            self.shutdown()
        elif sig == signal.SIGQUIT:
            self.shutdown()
    
    def shutdown(self):
        with self.__lock:
            self.__shutdown = True
    
    @property
    def is_shutdown(self):
        """bool: Is daemon in shutdown state?"""
        with self.__lock:
            return self.__shutdown
    
    @property
    def pmc(self):
        """PMCCommandsImpl: The current PMC manager implementation instance."""
        return self.__pmc
    
    @property
    def pmc_version(self):
        """str: The version of the connected PMC."""
        return self.__pmc_version
    
    @property
    def temperature_reader(self):
        """TemperatureReader: The current temperature reader instance."""
        return self.__temperature_reader
    
    @property
    def fan_controller(self):
        """FanControllerImpl: The current fan controller implementation instance."""
        return self.__fan_controller
    
    def setFanBootState(self):
        _logger.debug("%s: Setting fan to initial bootup speed",
                      type(self).__name__)
        self.__pmc.setFanSpeed(80)
    
    def setLEDBootState(self):
        _logger.debug("%s: Setting LEDs to initial bootup state",
                      type(self).__name__)
        pmc.setPowerLEDPulse(False)
        pmc.setLEDStatus(wdpmcprotocol.PMC_LED_NONE)
        pmc.setLEDBlink(wdpmcprotocol.PMC_LED_POWER_BLUE)
    
    def setLEDNormalState(self):
        _logger.debug("%s: Setting LEDs to normal state",
                      type(self).__name__)
        status = self.__pmc.getLEDStatus()
        status &= ~wdpmcprotocol.PMC_LED_POWER_MASK
        blink = self.__pmc.getLEDBlink()
        blink &= ~wdpmcprotocol.PMC_LED_POWER_MASK
        self.__pmc.setPowerLEDPulse(False)
        self.__pmc.setLEDBlink(blink | wdpmcprotocol.PMC_LED_NONE)
        self.__pmc.setLEDStatus(status | wdpmcprotocol.PMC_LED_POWER_BLUE)
    
    def setLEDWarningState(self):
        _logger.debug("%s: Setting LEDs to warning state",
                      type(self).__name__)
        status = self.__pmc.getLEDStatus()
        status &= ~wdpmcprotocol.PMC_LED_POWER_MASK
        blink = self.__pmc.getLEDBlink()
        blink &= ~wdpmcprotocol.PMC_LED_POWER_MASK
        self.__pmc.setPowerLEDPulse(False)
        self.__pmc.setLEDBlink(blink | wdpmcprotocol.PMC_LED_NONE)
        self.__pmc.setLEDStatus(status | wdpmcprotocol.PMC_LED_POWER_RED)
    
    def setLEDErrorState(self):
        _logger.debug("%s: Setting LEDs to error state",
                      type(self).__name__)
        status = self.__pmc.getLEDStatus()
        status &= ~wdpmcprotocol.PMC_LED_POWER_MASK
        blink = self.__pmc.getLEDBlink()
        blink &= ~wdpmcprotocol.PMC_LED_POWER_MASK
        self.__pmc.setPowerLEDPulse(False)
        self.__pmc.setLEDStatus(status | wdpmcprotocol.PMC_LED_NONE)
        self.__pmc.setLEDBlink(blink | wdpmcprotocol.PMC_LED_POWER_RED)
    
    def initiateImmediateSystemShutdown(self):
        _logger.info("%s: Initiating immediate system shutdown",
                     type(self).__name__)
        result = subprocess.call(["shutdown", "-P", "now"])
    
    def initiateDelayedSystemShutdown(self, grace_period=60):
        _logger.info("%s: Scheduled system shutdown in %d minutes",
                     type(self).__name__,
                     grace_period)
        result = subprocess.call(["shutdown", "-P", "+{0}".format(grace_period)])
    
    def cancelPendingSystemShutdown(self):
        _logger.info("%s: Cancelling pending system shutdown",
                     type(self).__name__)
        result = subprocess.call(["shutdown", "-c"])
    
    def main(self):
        """Main loop of the hardware controller daemon."""
        cfg = self.__config
        
        _logger.debug("%s: Starting PMC manager for PMC at '%s'",
                      type(self).__name__,
                      cfg.pmc_port)
        pmc = PMCCommandsImpl()
        pmc.connect(cfg.pmc_port)
        self.__pmc = pmc
        
        pmc_version = pmc.getVersion()
        self.__pmc_version = pmc_version
        _logger.info("%s: Detected PMC version %s",
                     type(self).__name__,
                     pmc_version)
        
        if cfg.pmc_test:
            _logger.debug("%s: PMC test mode: executing all getter commands",
                          type(self).__name__)
            pmc.getConfiguration()
            pmc.getStatus()
            pmc.getTemperature()
            pmc.getLEDStatus()
            pmc.getLEDBlink()
            pmc.getPowerLEDPulse()
            pmc.getLCDBacklightIntensity()
            pmc.getFanRPM()
            pmc.getFanSpeed()
            pmc.getDriveEnabledMask()
            pmc.getDrivePresenceMask()
            pmc.getInterruptStatus()
            pmc.getDLB()
            pmc.getBLK()
        
        _logger.debug("%s: Enabling all PMC interrupts",
                      type(self).__name__)
        pmc.setInterruptMask(wdpmcprotocol.PMC_INTERRUPT_MASK_ALL)
        
        self.setLEDBootState()
        
        _logger.debug("%s: Starting temperature reader",
                      type(self).__name__)
        temperature_reader = TemperatureReader()
        temperature_reader.connect()
        self.__temperature_reader = temperature_reader
        
        num_cpus = temperature_reader.getNumCPUCores()
        _logger.info("%s: Discovered %d CPU cores",
                     type(self).__name__,
                     num_cpus)
        
        _logger.debug("%s: Starting fan controller (system = %s, CPUs = %d, disks = %s, DIMMs = %d)",
                      type(self).__name__,
                      pmc_version, num_cpus, cfg.disk_drives, cfg.memory_dimms)
        fan_controller = FanControllerImpl(self,
                                           pmc,
                                           temperature_reader,
                                           cfg.disk_drives,
                                           cfg.memory_dimms)
        fan_controller.start()
        self.__fan_controller = fan_controller
        
        _logger.debug("%s: Starting controller socket server at %s (group = %s, max-clients = %d)",
                      type(self).__name__,
                      cfg.socket_path, repr(cfg.socket_group), cfg.socket_max_clients)
        server = WdHwServer(self, cfg.socket_path, cfg.socket_group, cfg.socket_max_clients)
        
        _logger.debug("%s: Setting up signal handlers",
                      type(self).__name__)
        signal.signal(signal.SIGTERM, self.__sigHandler)
        signal.signal(signal.SIGINT,  self.__sigHandler)
        signal.signal(signal.SIGQUIT, self.__sigHandler)

        _logger.debug("%s: Daemonizing...waiting for shutdown signal",
                      type(self).__name__)
        while not self.__shutdown:
            signal.pause()
        
        _logger.debug("%s: Stopping controller socket server",
                      type(self).__name__)
        server.close()
        _logger.debug("%s: Stopping fan controller",
                      type(self).__name__)
        fan_controller.join()
        _logger.debug("%s: Stopping temperature reader",
                      type(self).__name__)
        temperature_reader.close()
        _logger.debug("%s: Stopping PMC manager",
                      type(self).__name__)
        pmc.close()
        _logger.debug("%s: Shutdown completed",
                      type(self).__name__)


if __name__ == "__main__":
    logger = logging.getLogger("")
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    wdhwd = WdHwDaemon()
    wdhwd.main()

