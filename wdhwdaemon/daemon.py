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


import argparse
import ConfigParser
import grp
import json
import logging
import logging.handlers
import os
import os.path
import pwd
import signal
import stat
import subprocess
import threading

from wdhwlib.fancontroller import FanController, FanControllerCallback
from wdhwlib.temperature import TemperatureReader
from wdhwlib.wdpmcprotocol import PMCCommands
from wdhwlib import temperature, wdpmcprotocol

import wdhwdaemon.server
import wdhwdaemon


_logger = logging.getLogger(__name__)


WDHWD_SUPPLEMENTARY_GROUPS = ["i2c"]

WDHWD_EXIT_SUCCESS = 0
WDHWD_EXIT_CONFIG_ERROR = 10
WDHWD_EXIT_PERMISSION_ERROR = 11


class PMCCommandsImpl(PMCCommands):
    """Western Digital PMC Manager implementation.
    """
    
    def __init__(self, hw_daemon):
        """Initializes a new PMC manager.
        
        Args:
            hw_daemon (WdHwDaemon): The parent hardware controller daemon.
        """
        self.__hw_daemon = hw_daemon
        super(PMCCommandsImpl, self).__init__()
    
    def interruptReceived(self):
        isr = self.getInterruptStatus()
        _logger.info("%s: Received interrupt %X",
                     type(self).__name__,
                     isr)
        self.__hw_daemon.receivedPMCInterrupt(isr)
    
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
    """Fan controller implementation.
    """
    
    def __init__(self, hw_daemon, pmc, temperature_reader, disk_drives, num_dimms):
        """Initializes a new fan controller.
        
        Args:
            hw_daemon (WdHwDaemon): The parent hardware controller daemon.
            pmc (PMCCommands): An instance of the PMC interface.
            temperature_reader (TemperatureReader): An instance of the temperature reader.
            disk_drives (List(str)): A list of HDD device names to monitor.
            num_dimms (int): The number of memory DIMMs to monitor.
        """
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
        self.__hw_daemon.temperatureLevelChanged(new_level, old_level)


class ConfigFileError(Exception):
    pass


class ConfigFile(object):
    """Hardware controller daemon configuration holder.
    
    Attributes:
        pmc_port (str): Name of the serial port that the PMC is attached to.
        pmc_test_mode (bool): Enable PMC protocol testing mode?
        disk_drives (List(str)): List of disk drives in the drive bays (in the order of
            PMC drive bay flags).
        memory_dimms_count (int): Number of memory DIMMs to monitor.
        socket_path (str): Path of the UNIX domain socket for controlling the hardware
            controller daemon.
        socket_group_name (str): Group that is granted access to the UNIX domain socket.
        socket_max_clients (int): Maximum number of clients that can concurrently connect
            to the UNIX domain socket.
        log_file (str): The log file name; may be ``None`` to disable file-based logging.
        log_level (int): The log verbosity level for logging to the log file.
        drive_presence_changed_command (str): The command to execute when the drive bay
            presence status changed.
        drive_presence_changed_args (List(str)): A list of arguments passed to the
            command ``drive_presence_changed_command`` (the placeholders "{drive_bay}",
            "{drive_name}",  and "{status}" are may be used).
        power_supply_changed_command (str): The command to execute when the power supply
            power-up status changed.
        power_supply_changed_args (List(str)): A list of arguments passed to the
            command ``power_supply_changed_command`` (the placeholders "{socket}" and
            "{status}" may be used).
    """
    
    def __init__(self, config_file):
        """Initializes a new hardware controller daemon configuration holder.
        
        Args:
            config_file (str): The configuration file to load into this configuration
                holder.
        """
        super(ConfigFile, self).__init__()
        self.__file = config_file
        self.__cfg = ConfigParser.RawConfigParser()
        try:
            self.__file = self.__cfg.read(config_file)
            if len(self.__file) <= 0:
                _logger.error("%s: Configuration file '%s' not found",
                              type(self).__name__,
                              config_file)
                #raise ConfigFileError("Configuration file '{0}' not found".format(config_file))
        except ConfigFileError:
            raise
        except Exception as e:
            raise ConfigFileError("{0} while parsing configuration file '{2}': {1}".format(
                    type(e).__name__, e, config_file))
        SECTION = "wdhwd"
        self.declareOption(SECTION, "user", default=wdhwdaemon.WDHWD_USER_DEFAULT)
        self.declareOption(SECTION, "group", default=None)
        self.declareOption(SECTION, "pmc_port", default=wdpmcprotocol.PMC_UART_PORT_DEFAULT)
        self.declareOption(SECTION, "pmc_test_mode", default=False, parser=self.parseBoolean)
        self.declareOption(SECTION, "disk_drives", default=temperature.HDSMART_DISKS, parser=self.parseArray)
        self.declareOption(SECTION, "memory_dimms_count", default=2, parser=self.parseInteger)
        self.declareOption(SECTION, "socket_path", default=wdhwdaemon.WDHWD_SOCKET_FILE_DEFAULT)
        self.declareOption(SECTION, "socket_max_clients", default=10, parser=self.parseInteger)
        self.declareOption(SECTION, "log_file", default=None)
        self.declareOption(SECTION, "log_level", default=logging.WARNING, parser=self.parseLogLevel)
        self.declareOption(SECTION, "system_up_command", default=None)
        #self.declareOption(SECTION, "system_up_args", default=[], parser=self.parseArray)
        self.declareOption(SECTION, "system_down_command", default=None)
        #self.declareOption(SECTION, "system_down_args", default=[], parser=self.parseArray)
        self.declareOption(SECTION, "drive_presence_changed_command", default=None)
        self.declareOption(SECTION, "drive_presence_changed_args", default=["{drive_bay}", "{drive_name}", "{state}"], parser=self.parseArray)
        self.declareOption(SECTION, "power_supply_changed_command", default=None)
        self.declareOption(SECTION, "power_supply_changed_args", default=["{socket}", "{state}"], parser=self.parseArray)
        self.declareOption(SECTION, "temperature_changed_command", default=None)
        self.declareOption(SECTION, "temperature_changed_args", default=["{new_level}", "{old_level}"], parser=self.parseArray)
    
    def declareOption(self, option_section, option_name, attribute_name=None, default=None, parser=str, parser_args=None):
        if attribute_name is None:
            attribute_name = option_name
        if parser_args is None:
            parser_args = {}
        try:
            option_value = default
            if self.__cfg.has_option(option_section, option_name):
                option_raw_value = self.__cfg.get(option_section, option_name)
                option_value = parser(option_raw_value, **parser_args)
            setattr(self, attribute_name, option_value)
        except ValueError as e:
            raise ConfigFileError("Invalid value for option {2}"
                                  " (in section {1} of {0}): {3}".format(self.__file,
                                                                         option_section,
                                                                         option_name,
                                                                         e))
    
    @staticmethod
    def parseBoolean(value):
        value = value.lower()
        if value in ["1", "true", "yes", "on"]:
            return True
        elif value in ["0", "false", "no", "off"]:
            return False
        else:
            raise ValueError("'{0}' is not a valid boolean value".format(value))
    
    @staticmethod
    def parseInteger(value):
        return int(value)
    
    @staticmethod
    def parseLogLevel(value):
        value = value.lower()
        if value in ["critical", "crit", "c"]:
            return logging.CRITICAL
        elif value in ["error", "err", "e"]:
            return logging.ERROR
        elif value in ["warning", "warn", "w"]:
            return logging.WARNING
        elif value in ["info", "inf", "i"]:
            return logging.INFO
        elif value in ["debug", "dbg", "deb", "d"]:
            return logging.DEBUG
        elif value in ["all", "any", "a"]:
            return logging.NOTSET
        elif value in ["none", "no", "n", "off"]:
            return 2 * logging.CRITICAL
        else:
            raise ValueError("'{0}' is not a valid log level".format(value))
    
    @staticmethod
    def parseArray(value, parser=str, parser_args=None):
        if parser_args is None:
            parser_args = {}
        try:
            parsed_value = json.loads(value)
            if type(parsed_value) != list:
                raise ValueError()
            result = list()
            for element in parsed_value:
                result.append(parser(element, **parser_args))
            return result
        except ValueError as e:
            raise ValueError("'{0}' is not a valid array value: {1}".format(value, e))


class WdHwDaemon(object):
    """Hardware controller daemon.
    
    Attributes:
        is_running: Is daemon in running state?
        pmc: The current PMC manager implementation instance.
        pmc_version: The version of the connected PMC.
        temperature_reader: The current temperature reader instance.
        fan_controller: The current fan controller implementation instance.
    """
    
    def __init__(self):
        """Initializes a new hardware controller daemon."""
        super(WdHwDaemon, self).__init__()
        self.__lock = threading.RLock()
        self.__running = False
        self.__cfg = None
        self.__pmc = None
        self.__pmc_version = ""
        self.__pmc_status = 0
        self.__pmc_drive_presence_mask = 0
        self.__temperature_reader = None
        self.__fan_controller = None
        self.__server = None
    
    def __sigHandler(self, sig, frame):
        """Signal handler."""
        del frame
        if sig == signal.SIGTERM:
            self.shutdown()
        elif sig == signal.SIGINT:
            self.shutdown()
        elif sig == signal.SIGQUIT:
            self.shutdown()
        elif sig == signal.SIGALRM:
            pass
    
    def shutdown(self):
        """Shutdown this daemon instance."""
        with self.__lock:
            self.__running = False
            signal.alarm(1)
    
    @property
    def is_running(self):
        """bool: Is daemon in running state?"""
        with self.__lock:
            return self.__running
    
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
        """Set the fan speed to the initial boot-up state."""
        _logger.debug("%s: Setting fan to initial bootup speed",
                      type(self).__name__)
        self.__pmc.setFanSpeed(80)
    
    def setLEDBootState(self):
        """Set the LEDs to the initial boot-up state."""
        _logger.debug("%s: Setting LEDs to initial bootup state",
                      type(self).__name__)
        self.__pmc.setPowerLEDPulse(False)
        self.__pmc.setLEDStatus(wdpmcprotocol.PMC_LED_NONE)
        self.__pmc.setLEDBlink(wdpmcprotocol.PMC_LED_POWER_BLUE)
    
    def setLEDNormalState(self):
        """Set the LEDs to normal state indication."""
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
        """Set the LEDs to warning state indication."""
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
        """Set the LEDs to error state indication."""
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
        """Initiate an immediate system shutdown."""
        _logger.info("%s: Initiating immediate system shutdown",
                     type(self).__name__)
        result = subprocess.call(["/usr/bin/sudo", "-n", "/sbin/shutdown", "-P", "now"])
    
    def initiateDelayedSystemShutdown(self, grace_period=60):
        """Initiate a delayed system shutdown.
        
        Args:
            grace_period (int): The grace period before the system actually shuts down (in
                minutes).
        """
        _logger.info("%s: Scheduled system shutdown in %d minutes",
                     type(self).__name__,
                     grace_period)
        result = subprocess.call(["/usr/bin/sudo", "-n", "/sbin/shutdown", "-P", "+{0}".format(grace_period)])
    
    def cancelPendingSystemShutdown(self):
        """Cancel any pending system shutdown."""
        _logger.info("%s: Cancelling pending system shutdown",
                     type(self).__name__)
        result = subprocess.call(["/usr/bin/sudo", "-n", "/sbin/shutdown", "-c"])
    
    def notifySystemUp(self):
        """Notify hardware controller daemon start completed.
        """
        cmd = [self.__cfg.system_up_command]
        #for arg in self.__cfg.system_up_args:
        #    cmd.append(arg.format())
        result = subprocess.call(cmd)
        
    def notifySystemDown(self):
        """Notify hardware controller daemon stopping.
        """
        cmd = [self.__cfg.system_down_command]
        #for arg in self.__cfg.system_down_args:
        #    cmd.append(arg.format())
        result = subprocess.call(cmd)
        
    def temperatureLevelChanged(self, new_level, old_level):
        """Notify change of temperature level.
        
        Args:
            new_level (int): The new temperature level.
            old_level (int): The old temperature level.
        """
        if (old_level is None) and (new_level < FanController.LEVEL_HOT):
            return
        cmd = [self.__cfg.temperature_changed_command]
        for arg in self.__cfg.temperature_changed_args:
            cmd.append(arg.format(new_level=str(new_level),
                                  old_level=str(old_level)))
        result = subprocess.call(cmd)
        
    def notifyDrivePresenceChanged(self, bay_number, present):
        """Notify change of drive presence state.
        
        Args:
            bay_number (int): The drive bay that changed its presence state.
            present (bool): A boolean flag indicating the new presence state.
        """
        drive_name = ""
        if bay_number < len(self.__cfg.disk_drives):
            drive_name = self.__cfg.disk_drives[bay_number]
        _logger.info("%s: Drive presence changed for bay %d (disk = '%s') to %s",
                     type(self).__name__,
                     bay_number, drive_name, "present" if present else "absent")
        if self.__cfg.drive_presence_changed_command is not None:
            cmd = [self.__cfg.drive_presence_changed_command]
            for arg in self.__cfg.drive_presence_changed_args:
                cmd.append(arg.format(drive_bay=str(bay_number),
                                      drive_name=drive_name,
                                      status="1" if present else "0"))
            result = subprocess.call(cmd)
    
    def notifyPowerSupplyChanged(self, socket_number, powered_up):
        """Notify change of power supply state.
        
        Args:
            socket_number (int): The power supply socket that changed its power-up state.
            powered_up (bool): A boolean flag indicating the new power-up state.
        """
        _logger.info("%s: Power adapter status changed for socket %d to %s",
                     type(self).__name__,
                     socket_number, "powered up" if powered_up else "powered down")
        if self.__cfg.power_supply_changed_command is not None:
            cmd = [self.__cfg.power_supply_changed_command]
            for arg in self.__cfg.power_supply_changed_args:
                cmd.append(arg.format(socket=str(socket_number),
                                      status="1" if powered_up else "0"))
            result = subprocess.call(cmd)
    
    def receivedPMCInterrupt(self, isr):
        """Notify reception of a pending PMC interrupt.
        
        Args:
            isr (int): The interrupt status register value.
        """
        if isr != self.__pmc_status:
            # toggle recorded power adapter state (except upon initial interrupt)
            power_status_mask = (wdpmcprotocol.PMC_STATUS_POWER_1_UP |
                                 wdpmcprotocol.PMC_STATUS_POWER_2_UP)
            self.__pmc_status &= ~power_status_mask
            self.__pmc_status |= isr & power_status_mask
        
        # test for drive presence changes
        if (isr & wdpmcprotocol.PMC_INTERRUPT_DRIVE_PRESENCE_CHANGED) != 0:
            presence_mask = self.__pmc.getDrivePresenceMask()
            presence_delta = presence_mask ^ self.__pmc_drive_presence_mask
            for drive_bay in range(0, len(self.__cfg.disk_drives)):
                if (presence_delta & (1<<drive_bay)) != 0:
                    drive_present = (presence_mask & (1<<drive_bay)) != 0
                    self.notifyDrivePresenceChanged(drive_bay, drive_present)
            self.__pmc_drive_presence_mask = presence_mask
        
        # test for power status changes
        if (isr & wdpmcprotocol.PMC_INTERRUPT_POWER_1_STATE_CHANGED) != 0:
            power_up = (self.__pmc_status & wdpmcprotocol.PMC_INTERRUPT_POWER_1_STATE_CHANGED) != 0
            self.notifyPowerSupplyChanged(1, power_up)
        if (isr & wdpmcprotocol.PMC_INTERRUPT_POWER_2_STATE_CHANGED) != 0:
            power_up = (self.__pmc_status & wdpmcprotocol.PMC_INTERRUPT_POWER_2_STATE_CHANGED) != 0
            self.notifyPowerSupplyChanged(2, power_up)
    
    def _resolveUserInfo(self, user):
        """Resolve the user information for a given user name or ID.
        
        Args:
            user (str): Name or ID of the user to resolve the user info for.
        
        Returns:
            tuple(str, int, int): Tuple of resolved user name, numeric user ID, and
                numeric main group ID; or None.
        """
        if user is not None:
            try:
                user_info = None
                try:
                    uid = int(user)
                    user_info = pwd.getpwuid(uid)
                except ValueError:
                    user_info = pwd.getpwnam(user)
                if user_info is not None:
                    return (user_info.pw_name, user_info.pw_uid, user_info.pw_gid)
            except:
                pass
        return None
    
    def _resolveGroupId(self, group):
        """Resolve the numeric group ID for a given group name or ID.
        
        Args:
            group (str): Name or ID of the group to resolve to a numeric group ID.
        
        Returns:
            int: Resolved numeric group ID or None.
        """
        if group is not None:
            try:
                group_info = None
                try:
                    gid = int(group)
                    group_info = grp.getgrgid(gid)
                except ValueError:
                    group_info = grp.getgrnam(group)
                if group_info is not None:
                    return group_info.gr_gid
            except:
                pass
        return None
    
    def _resolveSupplementaryGroups(self, username):
        """Resolve all supplementary groups for a given user name.
        
        Args:
            username (str): Name of the user to resolve all supplementary groups for.
        
        Returns:
            List(int): List of numeric group IDs.
        """
        supplementary_gids = []
        for group in grp.getgrall():
            if username in group.gr_mem:
                supplementary_gids.append(g.gr_gid)
        return supplementary_gids
    
    def _resolveFileAccessGroups(self, filenames):
        """Resolve groups necessary for accessing given files.
        
        Args:
            filenames (List(str)): List of file names to assemble groups from.
        
        Returns:
            List(int): List of numeric group IDs.
        """
        file_access_gids = []
        for filename in filenames:
            try:
                stat_info = os.stat(filename)
                file_access_gids.append(stat_info.st_gid)
            except:
                pass
        return file_access_gids
    
    def _createDir(self, path, uid, gid=None):
        old_umask = os.umask(stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP |
                             stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH)
        create_components = []
        while not os.path.exists(path):
            create_components.insert(0, path)
            path = os.path.dirname(path)
        permissions = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        if uid is None:
            uid = -1
        if gid is None:
            gid = -1
        else:
            permissions |= stat.S_IRGRP | stat.S_IXGRP
        for p in create_components:
            os.mkdir(p)
            os.chown(p, uid, gid)
            os.chmod(p, permissions)
        os.umask(old_umask)
    
    def main(self, argv):
        """Main entrypoint of the hardware controller daemon.
        
        Args:
            argv (List(str)): List of command line arguments.
        
        Returns:
            int: Exit status code.
        """
        with self.__lock:
            self.__running = True
        
        cmdparser = argparse.ArgumentParser(
                description=wdhwdaemon.WDHWD_DESCRIPTION,
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
        self.__cfg = cfg
        
        if not cfg.user:
            _logger.error("%s: Target user not set",
                          type(self).__name__)
            return WDHWD_EXIT_CONFIG_ERROR
        target_user_info = self._resolveUserInfo(cfg.user)
        if target_user_info is None:
            _logger.error("%s: Could not resolve user '%s'",
                          type(self).__name__,
                          cfg.user)
            return WDHWD_EXIT_CONFIG_ERROR
        (target_user_name, target_uid, target_user_gid) = target_user_info
        target_gid = target_user_gid
        socket_gid = None
        if cfg.group:
            target_gid = self._resolveGroupId(cfg.group)
            socket_gid = target_gid
            if target_gid is None:
                _logger.error("%s: Could not resolve group '%s'",
                              type(self).__name__,
                              cfg.group)
                return WDHWD_EXIT_CONFIG_ERROR
        
        # create paths (if necessary)
        if cfg.socket_path:
            self._createDir(os.path.dirname(cfg.socket_path), target_uid, socket_gid)
        if cfg.log_file:
            self._createDir(os.path.dirname(cfg.log_file), target_uid, 0)
        
        # assemble list of supplementary groups
        target_supplementary_gids = self._resolveSupplementaryGroups(target_user_name)
        if target_user_gid not in target_supplementary_gids:
            target_supplementary_gids.append(target_user_gid)
        if target_gid not in target_supplementary_gids:
            target_supplementary_gids.append(target_gid)
        for file_access_gid in self._resolveFileAccessGroups([cfg.pmc_port]):
            if (file_access_gid != 0) and (file_access_gid not in target_supplementary_gids):
                target_supplementary_gids.append(file_access_gid)
        for additional_group in WDHWD_SUPPLEMENTARY_GROUPS:
            additional_gid = self._resolveGroupId(additional_group)
            if additional_gid is not None:
                target_supplementary_gids.append(additional_gid)
        
        # drop privileges
        try:
            os.setgroups(target_supplementary_gids)
        except OSError as e:
            serr = None
            try:
                serr = os.strerror(e.errno)
            except:
                pass
            _logger.error("%s: Failed to drop supplementary groups: %d (%s)",
                          type(self).__name__, e.errno, str(serr))
            #return
            pass
        try:
            os.setresgid(target_gid, target_gid, target_gid)
        except OSError as e:
            serr = None
            try:
                serr = os.strerror(e.errno)
            except:
                pass
            _logger.error("%s: Failed to set real/effective group ID to '%d': %d (%s)",
                          type(self).__name__,
                          target_gid, e.errno, str(serr))
            return WDHWD_EXIT_PERMISSION_ERROR
        try:
            os.setresuid(target_uid, target_uid, target_uid)
        except OSError as e:
            serr = None
            try:
                serr = os.strerror(e.errno)
            except:
                pass
            _logger.error("%s: Failed to set real/effective user ID to '%d': %d (%s)",
                          type(self).__name__,
                          target_uid, e.errno, str(serr))
            return WDHWD_EXIT_PERMISSION_ERROR
        _logger.debug("%s: Dropped privileges (user = %d, group = %d, supplementary_groups = %s)",
                      type(self).__name__,
                      target_uid, target_gid, repr(target_supplementary_gids))
        
        if log_level > cfg.log_level:
            log_level = cfg.log_level
            logger.setLevel(log_level)
        if cfg.log_file:
            filelog = logging.handlers.RotatingFileHandler(cfg.log_file, maxBytes=52428800, backupCount=3)
            filelog.setLevel(cfg.log_level)
            filelog.setFormatter(formatter)
            logger.addHandler(filelog)
        
        try:
            _logger.debug("%s: Starting PMC manager for PMC at '%s'",
                          type(self).__name__,
                          cfg.pmc_port)
            pmc = PMCCommandsImpl(self)
            pmc.connect(cfg.pmc_port)
            self.__pmc = pmc
            
            pmc_version = pmc.getVersion()
            self.__pmc_version = pmc_version
            _logger.info("%s: Detected PMC version %s",
                         type(self).__name__,
                         pmc_version)
            
            self.__pmc_status = pmc.getStatus()
            self.__pmc_drive_presence_mask = pmc.getDrivePresenceMask()
            
            if cfg.pmc_test_mode:
                _logger.debug("%s: PMC test mode: executing all getter commands",
                              type(self).__name__)
                pmc.getConfiguration()
                pmc.getTemperature()
                pmc.getLEDStatus()
                pmc.getLEDBlink()
                pmc.getPowerLEDPulse()
                pmc.getLCDBacklightIntensity()
                pmc.getFanRPM()
                pmc.getFanSpeed()
                pmc.getDriveEnabledMask()
                pmc.getDrivePresenceMask()
                pmc.getDLB()
            
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
                          pmc_version, num_cpus, cfg.disk_drives, cfg.memory_dimms_count)
            fan_controller = FanControllerImpl(self,
                                               pmc,
                                               temperature_reader,
                                               cfg.disk_drives,
                                               cfg.memory_dimms_count)
            fan_controller.start()
            self.__fan_controller = fan_controller
            
            _logger.debug("%s: Starting controller socket server at %s (group = %d, max-clients = %d)",
                          type(self).__name__,
                          cfg.socket_path,
                          socket_gid if socket_gid is not None else -1,
                          cfg.socket_max_clients)
            server = wdhwdaemon.server.WdHwServer(self,
                                                  cfg.socket_path,
                                                  socket_gid,
                                                  cfg.socket_max_clients)
            self.__server = server
            
            _logger.debug("%s: Setting up signal handlers",
                          type(self).__name__)
            signal.signal(signal.SIGTERM, self.__sigHandler)
            signal.signal(signal.SIGINT,  self.__sigHandler)
            signal.signal(signal.SIGQUIT, self.__sigHandler)
            signal.signal(signal.SIGALRM, self.__sigHandler)
            
            self.notifySystemUp()
            
            _logger.debug("%s: Daemonizing...waiting for shutdown signal",
                          type(self).__name__)
            while self.is_running:
                signal.pause()
            
            return WDHWD_EXIT_SUCCESS
        
        except Exception as e:
            _logger.error("%s: Daemon failed with %s: %s; exiting",
                    type(self).__name__,
                    type(e).__name__, str(e))
            raise
        
        finally:
            self.notifySystemDown()
            
            if self.__server is not None:
                _logger.debug("%s: Stopping controller socket server",
                              type(self).__name__)
                self.__server.close()
            if self.__fan_controller is not None:
                _logger.debug("%s: Stopping fan controller",
                              type(self).__name__)
                self.__fan_controller.join()
            if self.__temperature_reader is not None:
                _logger.debug("%s: Stopping temperature reader",
                              type(self).__name__)
                self.__temperature_reader.close()
            if self.__pmc is not None:
                _logger.debug("%s: Stopping PMC manager",
                              type(self).__name__)
                self.__pmc.close()
            _logger.debug("%s: Shutdown completed",
                          type(self).__name__)


if __name__ == "__main__":
    import sys
    d = WdHwDaemon()
    ret = d.main(sys.argv)
    sys.exit(ret)
