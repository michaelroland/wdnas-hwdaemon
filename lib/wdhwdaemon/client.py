#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Western Digital Hardware Controller Client.

Copyright (c) 2017-2021 Michael Roland <mi.roland@gmail.com>

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
import os
import time

from threadedsockets.packets import BasicPacket
from threadedsockets.packetclient import BasicPacketClient
from threadedsockets.unixsockets import UnixSocketFactory

from wdhwdaemon.daemon import ConfigFileImpl
from wdhwdaemon.server import CommandPacket, ResponsePacket
from wdhwdaemon.server import CloseConnectionWarning
from wdhwdaemon.server import LEDStatus
import wdhwdaemon


_logger = logging.getLogger(__name__)


CLIENT_EXIT_SUCCESS = 0
CLIENT_EXIT_HELP = 1


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
        super().__init__(client_socket, packet_class=ResponsePacket)
    
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
        return response.decode('utf-8', 'ignore')
    
    def daemonShutdown(self):
        response = self._executeCommand(CommandPacket.CMD_DAEMON_SHUTDOWN)
        if len(response) > 3:
            return (((response[0] << 24) & 0x0FF000000) | 
                    ((response[1] << 16) & 0x000FF0000) | 
                    ((response[2] <<  8) & 0x00000FF00) | 
                     (response[3]        & 0x0000000FF))
        else:
            raise ValueError("Invalid response format")
    
    def getPMCVersion(self):
        response = self._executeCommand(CommandPacket.CMD_PMC_VERSION_GET)
        return response.decode('utf-8', 'ignore')
    
    def setPMCConfiguration(self, config):
        response = self._executeCommand(CommandPacket.CMD_PMC_CONFIGURATION_SET,
                                        parameter=bytearray([config]))
    
    def getPMCConfiguration(self):
        response = self._executeCommand(CommandPacket.CMD_PMC_CONFIGURATION_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def getPowerSupplyBootupStatus(self):
        response = self._executeCommand(CommandPacket.CMD_POWERSUPPLY_BOOTUP_STATUS_GET)
        if len(response) > 0:
            return [False if s == 0 else True for s in response]
        else:
            raise ValueError("Invalid response format")
    
    def getPowerSupplyStatus(self):
        response = self._executeCommand(CommandPacket.CMD_POWERSUPPLY_STATUS_GET)
        if len(response) > 0:
            return [False if s == 0 else True for s in response]
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
        response = self._executeCommand(CommandPacket.CMD_LCD_BACKLIGHT_INTENSITY_SET,
                                        parameter=bytearray([intensity]))
    
    def getLCDBacklightIntensity(self):
        response = self._executeCommand(CommandPacket.CMD_LCD_BACKLIGHT_INTENSITY_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def setLCDText(self, line, text):
        parameter = bytearray([line])
        parameter.extend(text.encode('ascii', 'ignore'))
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
    
    def getFanTachoCount(self):
        response = self._executeCommand(CommandPacket.CMD_FAN_TAC_GET)
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
    
    def setDriveAlertLED(self, drive_bay, enable):
        enable_val = 0
        if enable:
            enable_val = 1
        response = self._executeCommand(CommandPacket.CMD_DRIVE_ALERT_LED_SET,
                                        parameter=bytearray([drive_bay, enable_val]))
    
    def setDriveAlertLEDBlinkMask(self, mask):
        response = self._executeCommand(CommandPacket.CMD_DRIVE_ALERT_LED_BLINK_SET,
                                        parameter=bytearray([mask]))
    
    def getDriveAlertLEDBlinkMask(self):
        response = self._executeCommand(CommandPacket.CMD_DRIVE_ALERT_LED_BLINK_GET)
        if len(response) > 0:
            return response[0]
        else:
            raise ValueError("Invalid response format")
    
    def sendDebug(self, raw_command):
        response = self._executeCommand(CommandPacket.CMD_PMC_DEBUG,
                                        parameter=raw_command.encode('ascii', 'ignore'))


class WdHwClient(object):
    """WD Hardware Controller Client.
    """
    
    def __init__(self):
        """Initializes a new hardware controller client."""
        super().__init__()
    
    def main(self, argv):
        """Main loop of the hardware controller client.
        
        Args:
            argv (List(str)): List of command line arguments.
        
        Returns:
            int: Exit status code.
        """
        cmdparser = argparse.ArgumentParser(
                description=wdhwdaemon.CLIENT_DESCRIPTION,
                epilog=wdhwdaemon.DAEMON_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmdparser.add_argument(
                '-C', '--config', action='store', nargs='?', metavar='CONFIG_FILE',
                default=wdhwdaemon.DAEMON_CONFIG_FILE_DEFAULT,
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
                version=wdhwdaemon.DAEMON_VERSION,
                help='show version information and exit')
        subparsers = cmdparser.add_subparsers(
                dest='command', metavar='COMMAND', title='available subcommands')
        
        cmd_version = subparsers.add_parser('version', help='get system version command',
                description="{}\nversion: get system version command".format(wdhwdaemon.CLIENT_DESCRIPTION),
                epilog=wdhwdaemon.DAEMON_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        
        cmd_led = subparsers.add_parser('led', help='LED control command',
                description="{}\nled: LED control command".format(wdhwdaemon.CLIENT_DESCRIPTION),
                epilog=wdhwdaemon.DAEMON_EPILOG,
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
                description="{}\nfan: fan control command".format(wdhwdaemon.CLIENT_DESCRIPTION),
                epilog=wdhwdaemon.DAEMON_EPILOG,
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
                description="{}\ntemperature: get system temperature command".format(wdhwdaemon.CLIENT_DESCRIPTION),
                epilog=wdhwdaemon.DAEMON_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        
        cmd_lcd = subparsers.add_parser('lcd', help='LCD control command',
                description="{}\nlcd: LCD control command".format(wdhwdaemon.CLIENT_DESCRIPTION),
                epilog=wdhwdaemon.DAEMON_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmd_lcd_action = cmd_lcd.add_argument_group(title='LCD action mode')
        cmd_lcd_action.add_argument(
                '-t', '--text', action='store', nargs=2, type=str, dest='text', metavar=("LINE1", "LINE2"),
                default=None,
                help='set LCD text')
        cmd_lcd_action = cmd_lcd_action.add_mutually_exclusive_group()
        cmd_lcd_action.add_argument(
                '-g', '--get', action='store_true',
                help='get current LCD backlight intensity')
        cmd_lcd_action.add_argument(
                '-s', '--set', action='store', type=int, dest='backlight', metavar='BACKLIGHT',
                default=None,
                help='set LCD backlight intensity in percent')
        
        cmd_drive = subparsers.add_parser('drive', help='drive bay control command',
                description="{}\ndrive: drive bay control command".format(wdhwdaemon.CLIENT_DESCRIPTION),
                epilog=wdhwdaemon.DAEMON_EPILOG,
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
        cmd_drive_action.add_argument(
                '-a', '--alert', action='store', type=int, dest='drivebay_alert', metavar="DRIVE_BAY",
                default=None,
                help='enable alert LED for drive bay number %(metavar)s')
        cmd_drive_action.add_argument(
                '-b', '--alertblink', action='store', type=int, dest='drivebay_alertblink', metavar="DRIVE_BAY",
                default=None,
                help='blink alert LED for drive bay number %(metavar)s')
        cmd_drive_action.add_argument(
                '-n', '--noalert', action='store', type=int, dest='drivebay_noalert', metavar="DRIVE_BAY",
                default=None,
                help='disable alert LED for drive bay number %(metavar)s')
        
        cmd_power = subparsers.add_parser('power', help='get power supply status command',
                description="{}\npower: get power supply status command".format(wdhwdaemon.CLIENT_DESCRIPTION),
                epilog=wdhwdaemon.DAEMON_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        
        cmd_shutdown = subparsers.add_parser('shutdown', help='daemon shutdown command',
                description="{}\nshutdown: daemon shutdown command".format(wdhwdaemon.CLIENT_DESCRIPTION),
                epilog=wdhwdaemon.DAEMON_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        
        cmd_pmc_debug = subparsers.add_parser('pmc_debug', help='PMC debug command',
                description="{}\npmc_debug: PMC debug command".format(wdhwdaemon.CLIENT_DESCRIPTION),
                epilog=wdhwdaemon.DAEMON_EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        cmd_pmc_debug_action = cmd_pmc_debug.add_argument_group(title='PMC debug command')
        cmd_pmc_debug_action.add_argument(
                '-c', '--command', action='store', type=str, dest='pmc_command', metavar="PMC COMMAND",
                default=None,
                help='send raw command to PMC')
        
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
        
        if args.command is None or args.command == "":
            cmdparser.print_help()
            return CLIENT_EXIT_HELP
        
        _logger.debug("%s: Loading configuration file '%s'",
                      type(self).__name__,
                      args.config)
        cfg = ConfigFileImpl(args.config)
        
        conn = WdHwConnector(cfg.socket_path)
        try:
            if args.command == "version":
                daemon_version = conn.getVersion()
                pmc_version = conn.getPMCVersion()
                print("Daemon version: {0}".format(daemon_version))
                print("PMC version: {0}".format(pmc_version))
            
            elif args.command == "led":
                if args.get or ((not args.steady) and (not args.blink) and (not args.pulse)):
                    if args.led_type == "power":
                        led_status = conn.getPowerLED()
                        print("Power LED\t{0:5}\t{1:5}\t{2:5}".format(
                                "red", "green", "blue"))
                        print("----------------------------------------")
                        if led_status.mask_const:
                            print("steady:  \t{0:5}\t{1:5}\t{2:5}".format(
                                    "on" if led_status.red_const   else "off",
                                    "on" if led_status.green_const else "off",
                                    "on" if led_status.blue_const  else "off"))
                        if led_status.mask_blink:
                            print("blink:   \t{0:5}\t{1:5}\t{2:5}".format(
                                    "on" if led_status.red_blink   else "off",
                                    "on" if led_status.green_blink else "off",
                                    "on" if led_status.blue_blink  else "off"))
                        if led_status.mask_pulse:
                            print("pulse:   \t{0:5}\t{1:5}\t{2:5}".format(
                                    "on" if led_status.red_pulse   else "---",
                                    "on" if led_status.green_pulse else "---",
                                    "on" if led_status.blue_pulse  else "off"))
                    elif args.led_type == "usb":
                        led_status = conn.getUSBLED()
                        print("USB LED  \t{0:5}\t{1:5}\t{2:5}".format(
                                "red", "green", "blue"))
                        print("----------------------------------------")
                        if led_status.mask_const:
                            print("steady:  \t{0:5}\t{1:5}\t{2:5}".format(
                                    "on " if led_status.red_const   else "off",
                                    "on " if led_status.green_const else "---",
                                    "on " if led_status.blue_const  else "off"))
                        if led_status.mask_blink:
                            print("blink:   \t{0:5}\t{1:5}\t{2:5}".format(
                                    "on " if led_status.red_blink   else "off",
                                    "on " if led_status.green_blink else "---",
                                    "on " if led_status.blue_blink  else "off"))
                        if led_status.mask_pulse:
                            print("pulse:   \t{0:5}\t{1:5}\t{2:5}".format(
                                    "on " if led_status.red_pulse   else "---",
                                    "on " if led_status.green_pulse else "---",
                                    "on " if led_status.blue_pulse  else "---"))
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
                    fan_tac = conn.getFanTachoCount()
                    fan_speed = conn.getFanSpeed()
                    print("Fan speed: {0} RPM at {1} %".format(fan_rpm, fan_speed))
                    print("Fan tacho count: {0} pulses per second".format(fan_tac))
                else:
                    if (args.speed < 0) or (args.speed > 100):
                        cmdparser.error("Parameter SPEED is out of valid range (0 <= SPEED <= 100)")
                    else:
                        conn.setFanSpeed(args.speed)
            
            elif args.command == "lcd":
                if args.get or ((args.text is None) and (args.backlight is None)):
                    backlight_intensity = conn.getLCDBacklightIntensity()
                    print("LCD backlight intensity: {0} %".format(backlight_intensity))
                else:
                    if args.text:
                        conn.setLCDText(1, args.text[0])
                        conn.setLCDText(2, args.text[1])
                    if args.backlight:
                        if (args.backlight < 0) or (args.backlight > 100):
                            cmdparser.error("Parameter BACKLIGHT is out of valid range (0 <= BACKLIGHT <= 100)")
                        else:
                            conn.setLCDBacklightIntensity(args.backlight)
            
            elif args.command == "drive":
                if (args.drivebay_enable is not None) or (args.drivebay_disable is not None):
                    drive_bay = None
                    enabled = True
                    if args.drivebay_enable is not None:
                        enabled = True
                        drive_bay = args.drivebay_enable
                    elif args.drivebay_disable is not None:
                        enabled = False
                        drive_bay = args.drivebay_disable
                    if drive_bay is not None:
                        conn.setDriveEnabled(drive_bay, enabled)
                    else:
                        cmdparser.error("Must specify at least one drive command")
                elif (args.drivebay_alert is not None) or (args.drivebay_alertblink is not None) or (args.drivebay_noalert is not None):
                    if args.drivebay_alert is not None:
                        drive_bay = args.drivebay_alert
                        alert_blink_mask = conn.getDriveAlertLEDBlinkMask()
                        alert_blink_mask &= ~(1<<drive_bay) & 0x00F
                        conn.setDriveAlertLEDBlinkMask(alert_blink_mask)
                        conn.setDriveAlertLED(drive_bay, True)
                    elif args.drivebay_alertblink is not None:
                        drive_bay = args.drivebay_alertblink
                        conn.setDriveAlertLED(drive_bay, False)
                        alert_blink_mask = conn.getDriveAlertLEDBlinkMask()
                        alert_blink_mask |= (1<<drive_bay) & 0x00F
                        conn.setDriveAlertLEDBlinkMask(alert_blink_mask)
                    elif args.drivebay_noalert is not None:
                        drive_bay = args.drivebay_noalert
                        alert_blink_mask = conn.getDriveAlertLEDBlinkMask()
                        alert_blink_mask &= ~(1<<drive_bay) & 0x00F
                        conn.setDriveAlertLEDBlinkMask(alert_blink_mask)
                        conn.setDriveAlertLED(drive_bay, False)
                    else:
                        cmdparser.error("Must specify at least one drive command")
                else:
                    present_mask = conn.getDrivePresentMask()
                    enabled_mask = conn.getDriveEnabledMask()
                    alert_blink_mask = conn.getDriveAlertLEDBlinkMask()
                    config_register = conn.getPMCConfiguration()
                    num_drivebays = 2
                    if (present_mask & wdpmcprotocol.PMC_DRIVEPRESENCE_4BAY_INDICATOR) != 0:
                        num_drivebays = 4
                    print("Automatic HDD power-up on presence detection: {0}".format(
                            "on" if (config_register & 0x001) != 0 else "off"))
                    print("Drive bay\tDrive present\tDrive enabled\tAlert")
                    for drive_bay in range(0, num_drivebays):
                        print("{0:9d}\t{1:13}\t{2:13}".format(
                                drive_bay,
                                "no"  if (present_mask & (1<<drive_bay)) != 0 else "yes",
                                "yes" if (enabled_mask & (1<<drive_bay)) != 0 else "no",
                                "blinking" if (alert_blink_mask & (1<<drive_bay)) != 0 else "off" if (enabled_mask & (1<<(drive_bay+4))) != 0 else "on"))
            
            elif args.command == "power":
                powersupply_bootup_status = conn.getPowerSupplyBootupStatus()
                powersupply_status = conn.getPowerSupplyStatus()
                print("Power supply\tCurrent state\tOn bootup")
                for powersupply in range(0, 2):
                    print("{0:12d}\t{1:12}\t{2:12}".format(
                            powersupply + 1,
                            "connected" if powersupply_bootup_status[powersupply] else "disconnected",
                            "connected" if powersupply_status[powersupply] else "disconnected"))
            
            elif args.command == "temperature":
                pmc_temperature = conn.getPMCTemperature()
                print("PMC temperature: {0} °C".format(pmc_temperature))
            
            elif args.command == "shutdown":
                daemon_pid = conn.daemonShutdown()
                conn.close()
                for i in range(0, 60):
                    print(".", end='', flush=True)
                    try:
                        os.kill(daemon_pid, 0)
                        time.sleep(1)
                    except:
                        break
                print("", flush=True)
                print("Terminated.")
            
            elif args.command == "pmc_debug":
                conn.sendDebug(args.pmc_command)
        finally:
            conn.close()
        
        return CLIENT_EXIT_SUCCESS


if __name__ == "__main__":
    import sys
    c = WdHwClient()
    ret = c.main(sys.argv)
    sys.exit(ret)
