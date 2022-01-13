#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Western Digital Hardware Controller Daemon.

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


import grp
import logging
import os
import os.path
import subprocess

import daemonize.config
import daemonize.daemon

from wdhwlib.fancontroller import FanController, FanControllerCallback
from wdhwlib.temperature import TemperatureReader
from wdhwlib.wdpmcprotocol import PMCCommands
from wdhwlib import temperature, wdpmcprotocol

import wdhwdaemon.server
import wdhwdaemon


_logger = logging.getLogger(__name__)


DAEMON_EXIT_CONFIG_ERROR = 10
DAEMON_EXIT_PERMISSION_ERROR = 11


class PMCCommandsImpl(PMCCommands):
    """Western Digital PMC Manager implementation.
    """
    
    def __init__(self, hw_daemon):
        """Initializes a new PMC manager.
        
        Args:
            hw_daemon (WdHwDaemon): The parent hardware controller daemon.
        """
        self.__hw_daemon = hw_daemon
        super().__init__()
    
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
    
    def __init__(self, hw_daemon, pmc, temperature_reader):
        """Initializes a new fan controller.
        
        Args:
            hw_daemon (WdHwDaemon): The parent hardware controller daemon.
            pmc (PMCCommands): An instance of the PMC interface.
            temperature_reader (TemperatureReader): An instance of the temperature reader.
        """
        self.__hw_daemon = hw_daemon
        super().__init__(pmc, temperature_reader)
    
    def controllerStarted(self):
        _logger.debug("%s: Fan controller started",
                      type(self).__name__)
        self.__hw_daemon.setLEDNormalState()
    
    def controllerStopped(self):
        _logger.debug("%s: Fan controller stopped",
                      type(self).__name__)
        self.__hw_daemon.setFanBootState()
        self.__hw_daemon.setLEDWarningState()
        if self.__hw_daemon.is_running:
            self.__hw_daemon.shutdown()
    
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


class ConfigFileImpl(daemonize.config.AbstractConfigFile):
    """Hardware controller daemon configuration holder.
    
    Attributes:
        user (str): User name or ID to drop privileges to during normal operation.
        group (str): Group name or ID to drop privileges to during normal operation.
        pmc_port (str): Name of the serial port that the PMC is attached to (leave empty
            for automatic discovery).
        socket_path (str): Path of the UNIX domain socket for controlling the hardware
            controller daemon.
        socket_max_clients (int): Maximum number of clients that can concurrently connect
            to the UNIX domain socket.
        log_file (str): The log file name; may be ``None`` to disable file-based logging.
        log_level (int): The log verbosity level for logging to the log file.
        system_up_command (str): The command to execute when the daemon starts.
        system_down_command (str): The command to execute when the daemon exits.
        drive_presence_changed_command (str): The command to execute when the drive bay
            presence status changed.
        drive_presence_changed_args (List(str)): A list of arguments passed to the
            command ``drive_presence_changed_command`` (the placeholders "{drive_bay}",
            "{drive_name}",  and "{status}" may be used).
        power_supply_changed_command (str): The command to execute when the power supply
            power-up status changed.
        power_supply_changed_args (List(str)): A list of arguments passed to the
            command ``power_supply_changed_command`` (the placeholders "{socket}" and
            "{status}" may be used).
        temperature_changed_command (str): The command to execute when the temperature
            level changed.
        temperature_changed_args (List(str)): A list of arguments passed to the
            command ``temperature_changed_command`` (the placeholders "{new_level}" and
            "{old_level}" may be used).
    """
    
    def __init__(self, config_file):
        super().__init__(config_file)
        SECTION = "wdhwd"
        self.declareOption(SECTION, "pmc_port", default=None)
        self.declareOption(SECTION, "socket_path", default=wdhwdaemon.DAEMON_SOCKET_FILE_DEFAULT)
        self.declareOption(SECTION, "socket_group", default=None)
        self.declareOption(SECTION, "socket_max_clients", default=10, parser=self.parseInteger)
        self.declareOption(SECTION, "log_file", default=None)
        self.declareOption(SECTION, "logging", default=None, parser=self.parseLogSpec)
        self.declareOption(SECTION, "system_up_command", default=None)
        #self.declareOption(SECTION, "system_up_args", default=[], parser=self.parseArray)
        self.declareOption(SECTION, "system_down_command", default=None)
        #self.declareOption(SECTION, "system_down_args", default=[], parser=self.parseArray)
        self.declareOption(SECTION, "drive_presence_changed_command", default=None)
        self.declareOption(SECTION, "drive_presence_changed_args", default=["{drive_bay}", "{state}"], parser=self.parseArray)
        self.declareOption(SECTION, "power_supply_changed_command", default=None)
        self.declareOption(SECTION, "power_supply_changed_args", default=["{socket}", "{state}"], parser=self.parseArray)
        self.declareOption(SECTION, "temperature_changed_command", default=None)
        self.declareOption(SECTION, "temperature_changed_args", default=["{new_level}", "{old_level}"], parser=self.parseArray)


class WdHwDaemon(daemonize.daemon.AbstractDaemon):
    """Hardware controller daemon.
    
    Attributes:
        pmc: The current PMC manager implementation instance.
        pmc_version: The version of the connected PMC.
        temperature_reader: The current temperature reader instance.
        fan_controller: The current fan controller implementation instance.
    """
    
    def __init__(self):
        """Initializes a new hardware controller daemon."""
        super().__init__()
        self.__debug_mode = False
        self.__pmc = None
        self.__pmc_version = ""
        self.__pmc_initial_status = 0
        self.__pmc_status = 0
        self.__pmc_drive_presence_mask = 0
        self.__pmc_num_drivebays = 0
        self.__temperature_reader = None
        self.__fan_controller = None
        self.__server = None
    
    @property
    def command_description(self):
        return wdhwdaemon.DAEMON_DESCRIPTION
    
    @property
    def command_epilog(self):
        return wdhwdaemon.DAEMON_EPILOG
    
    @property
    def command_version(self):
        return wdhwdaemon.DAEMON_VERSION
    
    @property
    def config_file_default(self):
        return wdhwdaemon.DAEMON_CONFIG_FILE_DEFAULT
    
    @property
    def config_file_class(self):
        return ConfigFileImpl
    
    def prepareArgParse(self, cmdparser):
        cmdparser.add_argument(
                '-d', '--debug', action='store_true',
                help='enables debug mode commands')
        return cmdparser
    
    @property
    def debug_mode(self):
        """bool: Is debug mode enabled?"""
        return self.__debug_mode
    
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
    
    def getPowerSupplyState(self):
        """Get the current power supply state.
        
        Returns:
            list(bool): The power supply state.
        """
        return [
            (self.__pmc_status & wdpmcprotocol.PMC_INTERRUPT_POWER_1_STATE_CHANGED) != 0,
            (self.__pmc_status & wdpmcprotocol.PMC_INTERRUPT_POWER_2_STATE_CHANGED) != 0,
        ]
    
    def getPowerSupplyBootupState(self):
        """Get the bootup power supply state.
        
        Returns:
            list(bool): The power supply state.
        """
        return [
            (self.__pmc_initial_status & wdpmcprotocol.PMC_INTERRUPT_POWER_1_STATE_CHANGED) != 0,
            (self.__pmc_initial_status & wdpmcprotocol.PMC_INTERRUPT_POWER_2_STATE_CHANGED) != 0,
        ]
    
    def initiateImmediateSystemShutdown(self):
        """Initiate an immediate system shutdown."""
        _logger.info("%s: Initiating immediate system shutdown",
                     type(self).__name__)
        if not self.debug_mode:
            result = subprocess.call(["/usr/bin/sudo", "-n", "/sbin/shutdown", "-P", "now"])
        else:
            _logger.warning("%s: System shutdown not initiated in debug mode!",
                            type(self).__name__)
    
    def initiateDelayedSystemShutdown(self, grace_period=60):
        """Initiate a delayed system shutdown.
        
        Args:
            grace_period (int): The grace period before the system actually shuts down (in
                minutes).
        """
        _logger.info("%s: Scheduled system shutdown in %d minutes",
                     type(self).__name__,
                     grace_period)
        if not self.debug_mode:
            result = subprocess.call(["/usr/bin/sudo", "-n", "/sbin/shutdown", "-P", "+{0}".format(grace_period)])
        else:
            _logger.warning("%s: System shutdown not scheduled in debug mode!",
                            type(self).__name__)
    
    def cancelPendingSystemShutdown(self):
        """Cancel any pending system shutdown."""
        _logger.info("%s: Cancelling pending system shutdown",
                     type(self).__name__)
        if not self.debug_mode:
            result = subprocess.call(["/usr/bin/sudo", "-n", "/sbin/shutdown", "-c"])
        else:
            _logger.warning("%s: System shutdown not scheduled in debug mode!",
                            type(self).__name__)
    
    def notifySystemUp(self):
        """Notify hardware controller daemon start completed.
        """
        cmd = self.getConfig("system_up_command")
        if cmd is not None:
            cmd = [cmd]
            #for arg in self.getConfig("system_up_args"):
            #    cmd.append(arg.format())
            result = subprocess.call(cmd)
        
    def notifySystemDown(self):
        """Notify hardware controller daemon stopping.
        """
        cmd = self.getConfig("system_down_command")
        if cmd is not None:
            cmd = [cmd]
            #for arg in self.getConfig("system_down_args"):
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
        cmd = self.getConfig("temperature_changed_command")
        if cmd is not None:
            cmd = [cmd]
            for arg in self.getConfig("temperature_changed_args"):
                cmd.append(arg.format(new_level=str(new_level),
                                      old_level=str(old_level)))
            result = subprocess.call(cmd)
        
    def notifyDrivePresenceChanged(self, bay_number, present):
        """Notify change of drive presence state.
        
        Args:
            bay_number (int): The drive bay that changed its presence state.
            present (bool): A boolean flag indicating the new presence state.
        """
        _logger.info("%s: Drive presence changed for bay %d to %s",
                     type(self).__name__,
                     bay_number, "present" if present else "absent")
        cmd = self.getConfig("drive_presence_changed_command")
        if cmd is not None:
            cmd = [cmd]
            for arg in self.getConfig("drive_presence_changed_args"):
                cmd.append(arg.format(drive_bay=str(bay_number),
                                      drive_name="",
                                      state="1" if present else "0"))
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
        cmd = self.getConfig("power_supply_changed_command")
        if cmd is not None:
            cmd = [cmd]
            for arg in self.getConfig("power_supply_changed_args"):
                cmd.append(arg.format(socket=str(socket_number),
                                      state="1" if powered_up else "0"))
            result = subprocess.call(cmd)
    
    def notifyUSBCopyButton(self, down_up):
        """Notify change of USB copy button pressed state.
        
        Args:
            down_up (bool): A boolean flag indicating if the button was pressed (True) or released (False).
        """
        _logger.info("%s: USB copy button pressed state changed for to %s",
                     type(self).__name__,
                     "pressed" if down_up else "released")
    
    def notifyLCDUpButton(self, down_up):
        """Notify change of LCD up button pressed state.
        
        Args:
            down_up (bool): A boolean flag indicating if the button was pressed (True) or released (False).
        """
        _logger.info("%s: LCD up button pressed state changed for to %s",
                     type(self).__name__,
                     "pressed" if down_up else "released")
    
    def notifyLCDDownButton(self, down_up):
        """Notify change of LCD down button pressed state.
        
        Args:
            down_up (bool): A boolean flag indicating if the button was pressed (True) or released (False).
        """
        _logger.info("%s: LCD down button pressed state changed for to %s",
                     type(self).__name__,
                     "pressed" if down_up else "released")
    
    def receivedPMCInterrupt(self, isr):
        """Notify reception of a pending PMC interrupt.
        
        Args:
            isr (int): The interrupt status register value.
        """
        if isr != self.__pmc_status:
            # toggle recorded PMC status (except upon initial interrupt)
            self.__pmc_status ^= isr
        
        # test for drive presence changes
        if (isr & wdpmcprotocol.PMC_INTERRUPT_DRIVE_PRESENCE_CHANGED) != 0:
            presence_mask = self.__pmc.getDrivePresenceMask()
            presence_delta = presence_mask ^ self.__pmc_drive_presence_mask
            for drive_bay in range(0, self.__pmc_num_drivebays):
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
        
        # test for button presses
        if (isr & wdpmcprotocol.PMC_INTERRUPT_USB_COPY_BUTTON) != 0:
            down_up = (self.__pmc_status & wdpmcprotocol.PMC_INTERRUPT_USB_COPY_BUTTON) != 0
            self.notifyUSBCopyButton(down_up)
        if (isr & wdpmcprotocol.PMC_INTERRUPT_LCD_UP_BUTTON) != 0:
            down_up = (self.__pmc_status & wdpmcprotocol.PMC_INTERRUPT_LCD_UP_BUTTON) != 0
            self.notifyLCDUpButton(down_up)
        if (isr & wdpmcprotocol.PMC_INTERRUPT_LCD_DOWN_BUTTON) != 0:
            down_up = (self.__pmc_status & wdpmcprotocol.PMC_INTERRUPT_LCD_DOWN_BUTTON) != 0
            self.notifyLCDDownButton(down_up)
    
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
            except Exception:
                pass
        return None
    
    def _resolveGroupName(self, group):
        """Resolve the group name for a given group name or ID.
        
        Args:
            group (str): Name or ID of the group to resolve the group name for.
        
        Returns:
            str: Resolved group name; or None.
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
                    return group_info.gr_name
            except Exception:
                pass
        return None
    
    def startup(self):
        if self.getArgument("debug"):
            self.__debug_mode = True
        
        socket_path = self.getConfig("socket_path")
        socket_group = self.getConfig("socket_group")
        socket_max_clients = self.getConfig("socket_max_clients")
        socket_gid = None
        if socket_path:
            if socket_group:
                socket_gid = self._resolveGroupId(socket_group)
                if socket_gid is None:
                    _logger.error("%s: Could not resolve group '%s'",
                                  type(self).__name__,
                                  socket_group)
                    self.setExitStatus(DAEMON_EXIT_CONFIG_ERROR)
                    self.shutdown()
                    return
            # create path (if necessary)
            try:
                self._createDir(os.path.dirname(socket_path), gid=socket_gid)
            except OSError as e:
                serr = None
                try:
                    serr = os.strerror(e.errno)
                except Exception:
                    pass
                _logger.error("%s: Failed to create socket path '%s' owned by group %s (ID %s): %d (%s)",
                              type(self).__name__,
                              os.path.dirname(socket_path),
                              self._resolveGroupName(socket_gid), str(socket_gid),
                              e.errno, str(serr))
                self.setExitStatus(DAEMON_EXIT_PERMISSION_ERROR)
                self.shutdown()
                return
        
        pmc_port = self.getConfig("pmc_port")
        _logger.debug("%s: Starting PMC manager for PMC at '%s'",
                      type(self).__name__,
                      pmc_port if pmc_port else "[autodiscover]")
        pmc = PMCCommandsImpl(self)
        self.__pmc = pmc
        pmc.connect(pmc_port)
        _logger.debug("%s: Connected to PMC at '%s'",
                      type(self).__name__,
                      pmc.port_name)
        
        pmc_version = pmc.getVersion()
        self.__pmc_version = pmc_version
        _logger.info("%s: Detected PMC version %s",
                     type(self).__name__,
                     pmc_version)
        
        self.__pmc_initial_status = pmc.getStatus()
        self.__pmc_status = self.__pmc_initial_status
        self.__pmc_drive_presence_mask = pmc.getDrivePresenceMask()
        self.__pmc_num_drivebays = 2
        if (self.__pmc_drive_presence_mask & wdpmcprotocol.PMC_DRIVEPRESENCE_4BAY_INDICATOR) != 0:
            self.__pmc_num_drivebays = 4
        _logger.debug("%s: This is a %d bay device",
                      type(self).__name__,
                      self.__pmc_num_drivebays)
        
        if self.__debug_mode:
            _logger.debug("%s: PMC test mode: executing all getter commands",
                          type(self).__name__)
            pmc.getConfiguration()
            pmc.getTemperature()
            pmc.getLEDStatus()
            pmc.getLEDBlink()
            pmc.getPowerLEDPulse()
            pmc.getLCDBacklightIntensity()
            pmc.getFanRPM()
            pmc.getFanTachoCount()
            pmc.getFanSpeed()
            pmc.getDriveEnabledMask()
            pmc.getDrivePresenceMask()
            pmc.getDriveAlertLEDBlinkMask()
        
        _logger.debug("%s: Enabling all PMC interrupts",
                      type(self).__name__)
        pmc.setInterruptMask(wdpmcprotocol.PMC_INTERRUPT_MASK_ALL)
        
        self.setLEDBootState()
        
        _logger.debug("%s: Starting temperature reader",
                      type(self).__name__)
        temperature_reader = TemperatureReader()
        self.__temperature_reader = temperature_reader
        temperature_reader.connect()
        
        num_cpus = temperature_reader.getNumCPUCores()
        _logger.info("%s: Discovered %d CPU cores",
                     type(self).__name__,
                     num_cpus)
        
        _logger.debug("%s: Starting fan controller (system = %s, CPUs = %d)",
                      type(self).__name__,
                      pmc_version, num_cpus)
        fan_controller = FanControllerImpl(self,
                                           pmc,
                                           temperature_reader)
        self.__fan_controller = fan_controller
        fan_controller.start()
        
        _logger.debug("%s: Starting controller socket server at %s (group = %d, max-clients = %d)",
                      type(self).__name__,
                      socket_path,
                      socket_gid if socket_gid is not None else -1,
                      socket_max_clients)
        server = wdhwdaemon.server.WdHwServer(self,
                                              socket_path,
                                              socket_gid,
                                              socket_max_clients)
        self.__server = server
        
        self.notifySystemUp()
        
    def cleanup(self):
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
