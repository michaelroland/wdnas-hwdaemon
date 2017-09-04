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


import argparse
import logging

from threadedsockets.packets import BasicPacket
from threadedsockets.packetclient import BasicPacketClient
from threadedsockets.unixsockets import UnixSocketFactory

from wdhwdaemon.daemon import ConfigFile
from wdhwdaemon.server import CommandPacket, ResponsePacket
from wdhwdaemon.server import CloseConnectionWarning
from wdhwdaemon.server import LEDStatus
import wdhwdaemon


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
            _logger.debug("%s: Received successful response (%s)",
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
    
    def setPowerLED(self, led_status):
        response = self._executeCommand(CommandPacket.CMD_POWER_LED_SET,
                                        led_status.serialize())
    
    def getPowerLED(self):
        response = self._executeCommand(CommandPacket.CMD_POWER_LED_GET)
        return LEDStatus(response)
    
    def setUSBLED(self, led_status):
        response = self._executeCommand(CommandPacket.CMD_USB_LED_SET,
                                        led_status.serialize())
    
    def getUSBLED(self):
        response = self._executeCommand(CommandPacket.CMD_USB_LED_GET)
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
                epilog=wdhwdaemon.WDHWD_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmdparser.add_argument(
                '-C', '--config', action='store', nargs='?', metavar='CONFIG_FILE',
                default=wdhwdaemon.WDHWD_CONFIG_FILE_DEFAULT,
                help='configuration file (default: %(default)s)')
        cmdparser.add_argument(
                '-v', '--verbose', action='count',
                default=0,
                help='sets the console logging verbosity level')
        cmdparser.add_argument(
                '-q', '--quiet', action='store_true',
                help='disables console logging output')
        cmdparser.add_argument(
                '-V', '--version', action='version',
                version=wdhwdaemon.WDHWD_VERSION,
                help='show version information and exit')
        subparsers = cmdparser.add_subparsers(
                dest='command', metavar='COMMAND', title='available subcommands')
        cmd_version = subparsers.add_parser('version', help='get system version command',
                description="{}\nversion: get system version command".format(wdhwdaemon.WDHWC_DESCRIPTION),
                epilog=wdhwdaemon.WDHWD_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmd_led = subparsers.add_parser('led', help='LED control command',
                description="{}\nled: LED control command".format(wdhwdaemon.WDHWC_DESCRIPTION),
                epilog=wdhwdaemon.WDHWD_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmd_led_type = cmd_led.add_argument_group(title='LED type to control')
        cmd_led_type = cmd_led_type.add_mutually_exclusive_group(required=True)
        cmd_led_type.add_argument(
                '--power', '-P', dest='led_type', action='store_const',
                const="power",
                help='power LED')
        cmd_led_type.add_argument(
                '--usb', '-U', dest='led_type', action='store_const',
                const="usb",
                help='USB LED')
        cmd_led_action = cmd_led.add_argument_group(title='LED action mode')
        cmd_led_action = cmd_led_action.add_mutually_exclusive_group()
        cmd_led_action.add_argument(
                '-g', '--get', action='store_true',
                help='get current status (also the default if no mode is given)')
        cmd_led_action.add_argument(
                '-s', '--steady', action='store_true',
                help='set steady mode')
        cmd_led_action.add_argument(
                '-b', '--blink', action='store_true',
                help='set blinking mode')
        cmd_led_action.add_argument(
                '-p', '--pulse', action='store_true',
                help='set pulsing mode')
        cmd_led_color = cmd_led.add_argument_group(title='LED color')
        cmd_led_color.add_argument(
                '-R', '--red', action='store_true',
                help='red on (defaults to off when option is absent)')
        cmd_led_color.add_argument(
                '-G', '--green', action='store_true',
                help='green on (defaults to off when option is absent)')
        cmd_led_color.add_argument(
                '-B', '--blue', action='store_true',
                help='blue on (defaults to off when option is absent)')
        cmd_fan = subparsers.add_parser('fan', help='fan control command',
                description="{}\nfan: fan control command".format(wdhwdaemon.WDHWC_DESCRIPTION),
                epilog=wdhwdaemon.WDHWD_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmd_fan_action = cmd_fan.add_argument_group(title='fan action mode')
        cmd_fan_action = cmd_fan_action.add_mutually_exclusive_group()
        cmd_fan_action.add_argument(
                '-g', '--get', action='store_true',
                help='get current status (also the default if no mode is given)')
        cmd_fan_action.add_argument(
                '-s', '--set', action='store', type=int, dest='speed', metavar="SPEED",
                default=None,
                help='set fan speed in percent')
        cmd_temperature = subparsers.add_parser('temperature', help='get system temperature command',
                description="{}\ntemperature: get system temperature command".format(wdhwdaemon.WDHWC_DESCRIPTION),
                epilog=wdhwdaemon.WDHWD_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmd_drive = subparsers.add_parser('drive', help='drive bay control command',
                description="{}\ndrive: drive bay control command".format(wdhwdaemon.WDHWC_DESCRIPTION),
                epilog=wdhwdaemon.WDHWD_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmd_drive_action = cmd_drive.add_argument_group(title='drive bay action mode')
        cmd_drive_action = cmd_drive_action.add_mutually_exclusive_group()
        cmd_drive_action.add_argument(
                '-g', '--get', action='store_true',
                help='get current status (also the default if no mode is given)')
        cmd_drive_action.add_argument(
                '-e', '--enable', action='store', type=int, dest='drivebay_enable', metavar="DRIVE_BAY",
                default=None,
                help='set drive bay number %(metavar)s enabled')
        cmd_drive_action.add_argument(
                '-d', '--disable', action='store', type=int, dest='drivebay_disable', metavar="DRIVE_BAY",
                default=None,
                help='set drive bay number %(metavar)s disabled')
        cmd_shutdown = subparsers.add_parser('shutdown', help='daemon shutdown command',
                description="{}\nshutdown: daemon shutdown command".format(wdhwdaemon.WDHWC_DESCRIPTION),
                epilog=wdhwdaemon.WDHWD_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
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
        
        conn = WdHwConnector(cfg.socket_path)
        if args.command == "version":
            daemon_version = conn.getVersion()
            pmc_version = conn.getPMCVersion()
            print "Daemon version: {0}".format(daemon_version)
            print "PMC version: {0}".format(pmc_version)
        
        elif args.command == "led":
            if args.get or ((not args.steady) and (not args.blink) and (not args.pulse)):
                if args.led_type == "power":
                    led_status = conn.getPowerLED()
                    print "Power LED\t{0:5}\t{1:5}\t{2:5}".format(
                            "red", "green", "blue")
                    print "----------------------------------------"
                    if led_status.mask_const:
                        print "steady:  \t{0:5}\t{1:5}\t{2:5}".format(
                                "on" if led_status.red_const   else "off",
                                "on" if led_status.green_const else "off",
                                "on" if led_status.blue_const  else "off")
                    if led_status.mask_blink:
                        print "blink:   \t{0:5}\t{1:5}\t{2:5}".format(
                                "on" if led_status.red_blink   else "off",
                                "on" if led_status.green_blink else "off",
                                "on" if led_status.blue_blink  else "off")
                    if led_status.mask_pulse:
                        print "pulse:   \t{0:5}\t{1:5}\t{2:5}".format(
                                "on" if led_status.red_pulse   else "---",
                                "on" if led_status.green_pulse else "---",
                                "on" if led_status.blue_pulse  else "off")
                elif args.led_type == "usb":
                    led_status = conn.getUSBLED()
                    print "USB LED  \t{0:5}\t{1:5}\t{2:5}".format(
                            "red", "green", "blue")
                    print "----------------------------------------"
                    if led_status.mask_const:
                        print "steady:  \t{0:5}\t{1:5}\t{2:5}".format(
                                "on " if led_status.red_const   else "off",
                                "on " if led_status.green_const else "---",
                                "on " if led_status.blue_const  else "off")
                    if led_status.mask_blink:
                        print "blink:   \t{0:5}\t{1:5}\t{2:5}".format(
                                "on " if led_status.red_blink   else "off",
                                "on " if led_status.green_blink else "---",
                                "on " if led_status.blue_blink  else "off")
                    if led_status.mask_pulse:
                        print "pulse:   \t{0:5}\t{1:5}\t{2:5}".format(
                                "on " if led_status.red_pulse   else "---",
                                "on " if led_status.green_pulse else "---",
                                "on " if led_status.blue_pulse  else "---")
            else:
                led_status = LEDStatus()
                if args.steady:
                    led_status.mask_const = True
                    led_status.red_const = args.red
                    led_status.green_const = args.green
                    led_status.blue_const = args.blue
                elif args.blink:
                    led_status.mask_blink = True
                    led_status.red_blink = args.red
                    led_status.green_blink = args.green
                    led_status.blue_blink = args.blue
                elif args.pulse:
                    led_status.mask_pulse = True
                    led_status.red_pulse = args.red
                    led_status.green_pulse = args.green
                    led_status.blue_pulse = args.blue
                if args.led_type == "power":
                    conn.setPowerLED(led_status)
                elif args.led_type == "usb":
                    conn.setUSBLED(led_status)
        
        elif args.command == "fan":
            if args.get or (args.speed is None):
                fan_rpm = conn.getFanRPM()
                fan_speed = conn.getFanSpeed()
                print "Fan speed: {0} RPM at {1} %".format(fan_rpm, fan_speed)
            else:
                if (args.speed < 0) or (args.speed > 100):
                    cmdparser.error("Parameter SPEED is out of valid range (0 <= SPEED <= 100)")
                else:
                    conn.setFanSpeed(args.speed)
        
        elif args.command == "drive":
            if args.get or ((args.drivebay_enable is None) and (args.drivebay_disable is None)):
                present_mask = conn.getDrivePresentMask()
                enabled_mask = conn.getDriveEnabledMask()
                config_register = conn.getPMCConfiguration()
                status_register = conn.getPMCStatus()
                dlb = conn.getPMCDLB()
                print "Automatic HDD power-up on presence detection: {0}".format(
                        "on" if (config_register & 0x001) != 0 else "off")
                print "Drive bay\tDrive present\tDrive enabled"
                for drive_bay in range(0, len(cfg.disk_drives)):
                    print "{0:9d}\t{1:13}\t{2:13}".format(
                            drive_bay,
                            "no"  if (present_mask & (1<<drive_bay)) != 0 else "yes",
                            "yes" if (enabled_mask & (1<<drive_bay)) != 0 else "no")
            else:
                drive_bay = None
                enabled = True
                if args.drivebay_enable is not None:
                    enabled = True
                    drive_bay = args.drivebay_enable
                elif args.drivebay_disable is not None:
                    enabled = False
                    drive_bay = args.drivebay_disable
                else:
                    cmdparser.error("Must specify at least one drive command")
                if drive_bay is not None:
                    conn.setDriveEnabled(drive_bay, enabled)
                else:
                    cmdparser.error("Must specify at least one drive command")
        
        elif args.command == "temperature":
            pmc_temperature = conn.getPMCTemperature()
            print "PMC temperature: {0} °C".format(pmc_temperature)
        
        elif args.command == "shutdown":
            conn.daemonShutdown()
        
        conn.close()


if __name__ == "__main__":
    import sys
    c = WdHwClient()
    c.main(sys.argv)

