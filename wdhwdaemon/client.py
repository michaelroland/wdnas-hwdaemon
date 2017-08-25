#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Western Digital Hardware Controller Client.

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
from threadedsockets.packetclient import BasicPacketClient
from threadedsockets.unixsockets import UnixSocketFactory

from wdhwdaemon.daemon import ConfigFile
from wdhwdaemon.server import CommandPacket, ResponsePacket
from wdhwdaemon.server import CloseConnectionWarning
from wdhwdaemon.server import LEDStatus


_logger = logging.getLogger(__name__)


class WdHwConnector(BasicPacketClient):
    """WD Hardware Controller Client Connector.
    """

    def __init__(self, socket_path):
        """Initializes a new hardware controller client connector.
        
        Args:
            socket_path (str): File path of the named UNIX domain socket.
        """
        socket_factory = UnixSocketFactory(socket_path)
        client_socket = socket_factory.connectSocket()
        super(WdHwConnector, self).__init__(client_socket, packet_class=ResponsePacket)
    
    def _executeCommand(self, command_code, parameter=None, keep_alive=True, more_flags=0):
        flags = more_flags
        if keep_alive:
            flags |= CommandPacket.FLAG_KEEP_ALIVE
        command = CommandPacket(command_code, parameter=parameter, flags=flags)
        _logger.debug("%s: Sending command '%02X' (%s)",
                      type(self).__name__,
                      command_code, repr(parameter))
        self.sendPacket(command)
        response = self.receivePacket()
        if response.identifier != command_code:
            # unexpected response
            _logger.error("%s: Received unexpected response '%02X' for command '%02X'",
                          type(self).__name__,
                          response.identifier, command_code)
            raise CloseConnectionWarning("Unexpected response '{:02X}' received".format(response.identifier))
        elif response.is_error:
            # error
            _logger.error("%s: Received error '%02X'",
                          type(self).__name__,
                          response.error_code)
            raise CloseConnectionWarning("Error '{:02X}' received".format(response.error_code))
        else:
            # success
            _logger.error("%s: Received successful response (%s)",
                          type(self).__name__,
                          repr(response.parameter))
            return response.parameter
    
    def getVersion(self):
        response = self._executeCommand(CommandPacket.CMD_VERSION_GET)
        return response.decode('utf_8', 'ignore')
    
    def daemonShutdown(self):
        response = self._executeCommand(CommandPacket.CMD_DAEMON_SHUTDOWN)
    
    def getPMCVersion(self):
        response = self._executeCommand(CommandPacket.CMD_PMC_VERSION_GET)
        return response.decode('utf_8', 'ignore')
    
    def getPMCStatus(self):
        response = self._executeCommand(CommandPacket.CMD_PMC_STATUS_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def setPMCConfiguration(self, config):
        response = self._executeCommand(CommandPacket.CMD_PMC_CONFIGURATION_SET,
                                        parameter=bytearray([config]))
    
    def getPMCConfiguration(self):
        response = self._executeCommand(CommandPacket.CMD_PMC_CONFIGURATION_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def getPMCDLB(self):
        response = self._executeCommand(CommandPacket.CMD_PMC_DLB_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def getPMCBLK(self, packet):
        response = self._executeCommand(CommandPacket.CMD_PMC_BLK_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def setPowerLED(self, led_status):
        response = self._executeCommand(CommandPacket.CMD_LED_POWER_SET,
                                        led_status.serialize())
    
    def getPowerLED(self):
        response = self._executeCommand(CommandPacket.CMD_LED_POWER_GET)
        return LEDStatus(response)
    
    def setUSBLED(self, led_status):
        response = self._executeCommand(CommandPacket.CMD_LED_USB_SET,
                                        led_status.serialize())
    
    def getUSBLED(self):
        response = self._executeCommand(CommandPacket.CMD_LED_USB_GET)
        return LEDStatus(response)
    
    def setLCDBacklightIntensity(self, intensity):
        response = self._executeCommand(CommandPacket.CMD_LCD_BACKLIGHT_INTENSITY_GET,
                                        parameter=bytearray([intensity]))
    
    def getLCDBacklightIntensity(self):
        response = self._executeCommand(CommandPacket.CMD_LCD_BACKLIGHT_INTENSITY_SET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def setLCDText(self, line, text):
        parameter = bytearray([line])
        parameter.extend(text.encode('us-ascii', 'ignore'))
        response = self._executeCommand(CommandPacket.CMD_LCD_TEXT_SET,
                                        parameter=parameter)
    
    def getPMCTemperature(self):
        response = self._executeCommand(CommandPacket.CMD_PMC_TEMPERATURE_GET)
        if len(response) > 1:
            return ((response[0] << 8) & 0x0FF00) | (response[1] & 0x0FF)
        else:
            raise ValueError("Invalid response format")
    
    def getFanRPM(self):
        response = self._executeCommand(CommandPacket.CMD_FAN_RPM_GET)
        if len(response) > 1:
            return ((response[0] << 8) & 0x0FF00) | (response[1] & 0x0FF)
        else:
            raise ValueError("Invalid response format")
    
    def setFanSpeed(self, speed):
        response = self._executeCommand(CommandPacket.CMD_FAN_SPEED_SET,
                                        parameter=bytearray([speed]))
    
    def getFanSpeed(self):
        response = self._executeCommand(CommandPacket.CMD_FAN_SPEED_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def getDrivePresentMask(self):
        response = self._executeCommand(CommandPacket.CMD_DRIVE_PRESENT_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def setDriveEnabled(self, drive_bay, enable):
        enable_val = 0
        if enable:
            enable_val = 1
        response = self._executeCommand(CommandPacket.CMD_DRIVE_ENABLED_SET,
                                        parameter=bytearray([drive_bay, enable_val]))
    
    def getDriveEnabledMask(self):
        response = self._executeCommand(CommandPacket.CMD_DRIVE_ENABLED_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")


WDHWC_COMMAND_DESCRIPTION = """
"""


class WdHwClient(object):
    """WD Hardware Controller Client.
    """
    
    def __init__(self):
        """Initializes a new hardware controller client."""
        super(WdHwClient, self).__init__()
    
    def main(self, argv):
        """Main loop of the hardware controller client."""
        cmdparser = argparse.ArgumentParser(
                description=wdhwdaemon.WDHWC_DESCRIPTION,
                epilog="{}{}".format(WDHWC_COMMAND_DESCRIPTION, wdhwdaemon.WDHWD_EPILOG),
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmdparser.add_argument(
                'command', action='store', metavar='COMMAND',
                help='command to execute')
        cmdparser.add_argument(
                'params', action='store', nargs='*', metavar='ARG',
                default=None,
                help='command arguments')
        cmdparser.add_argument(
                '-C', '--config', action='store', nargs='?', metavar='CONFIG_FILE',
                default=wdhwdaemon.WDHWD_CONFIG_FILE_DEFAULT,
                help='configuration file (default: {0})'.format(wdhwdaemon.WDHWD_CONFIG_FILE_DEFAULT))
        cmdparser.add_argument(
                '-v', '--verbose', action='count',
                default=0,
                help='sets the console logging verbosity level')
        cmdparser.add_argument(
                '-q', '--quiet', action='store_const',
                default=False, const=True,
                help='disables console logging output')
        cmdparser.add_argument(
                '-V', '--version', action='version',
                version=wdhwdaemon.WDHWD_VERSION,
                help='show version information and exit')
        args = cmdparser.parse_args(argv[1:])
        
        log_level = logging.ERROR
        if args.verbose > 3:
            log_level = logging.NOTSET
        elif args.verbose > 2:
            log_level = logging.DEBUG
        elif args.verbose > 1:
            log_level = logging.INFO
        elif args.verbose > 0:
            log_level = logging.WARNING
        logger = logging.getLogger("")
        logger.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        if not args.quiet:
            consolelog = logging.StreamHandler()
            consolelog.setLevel(log_level)
            consolelog.setFormatter(formatter)
            logger.addHandler(consolelog)
        
        _logger.debug("%s: Loading configuration file '%s'",
                      type(self).__name__,
                      args.config)
        cfg = ConfigFile(args.config)
        


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

