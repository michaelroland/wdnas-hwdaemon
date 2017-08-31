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
import logging
import logging.handlers
import signal
import subprocess
import threading

from wdhwlib.fancontroller import FanController, FanControllerCallback
from wdhwlib.temperature import TemperatureReader
from wdhwlib.wdpmcprotocol import PMCCommands
from wdhwlib import temperature, wdpmcprotocol

import wdhwdaemon.server
import wdhwdaemon


_logger = logging.getLogger(__name__)


class PMCCommandsImpl(PMCCommands):
    """Western Digital PMC Manager implementation.
    """
    
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


class ConfigFile(object):
    """Hardware controller daemon configuration holder.
    
    Attributes:
        pmc_port: Name of the serial port that the PMC is attached to.
        pmc_test: Enable PMC protocol testing mode?
        disk_drives: List of disk drives in the drive bays (in the order of PMC drive
            bay flags).
        memory_dimms: Number of memory DIMMs to monitor.
        socket_path: Path of the UNIX domain socket for controlling the hardware
            controller daemon.
        socket_group: Group that is granted access to the UNIX domain socket.
        socket_max_clients: Maximum number of clients that can concurrently connect to
            the UNIX domain socket.
        log_file: The log file name; may be ``None`` to disable file-based logging.
        log_level: The log verbosity level for logging to the log file.
    """
    
    def __init__(self, config_file):
        """Initializes a new hardware controller daemon configuration holder.
        
        Args:
            config_file (str): The configuration file to load into this configuration
                holder.
        """
        super(ConfigFile, self).__init__()
        self.__pmc_port = wdpmcprotocol.PMC_UART_PORT_DEFAULT
        self.__pmc_test = True
        self.__disk_drives = temperature.HDSMART_DISKS
        self.__memory_dimms = 2
        self.__socket_path = wdhwdaemon.WDHWD_SOCKET_FILE_DEFAULT
        self.__socket_group = None
        self.__socket_max_clients = 10
        self.__log_file = None
        self.__log_level = logging.WARNING
    
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
    
    @property
    def log_file(self):
        """str: The log file name; may be ``None`` to disable file-based logging."""
        return self.__log_file
    
    @property
    def log_level(self):
        """int: The log verbosity level for logging to the log file."""
        return self.__log_level


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
        self.__pmc = None
        self.__pmc_version = ""
        self.__temperature_reader = None
        self.__fan_controller = None
    
    def __sigHandler(self, sig, frame):
        """Signal handler."""
        del frame
        if sig == signal.SIGTERM:
            self.shutdown()
        elif sig == signal.SIGINT:
            self.shutdown()
        elif sig == signal.SIGQUIT:
            self.shutdown()
    
    def shutdown(self):
        """Shutdown this daemon instance."""
        with self.__lock:
            self.__running = False
    
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
        result = subprocess.call(["shutdown", "-P", "now"])
    
    def initiateDelayedSystemShutdown(self, grace_period=60):
        """Initiate a delayed system shutdown.
        
        Args:
            grace_period (int): The grace period before the system actually shuts down (in
                minutes).
        """
        _logger.info("%s: Scheduled system shutdown in %d minutes",
                     type(self).__name__,
                     grace_period)
        result = subprocess.call(["shutdown", "-P", "+{0}".format(grace_period)])
    
    def cancelPendingSystemShutdown(self):
        """Cancel any pending system shutdown."""
        _logger.info("%s: Cancelling pending system shutdown",
                     type(self).__name__)
        result = subprocess.call(["shutdown", "-c"])
    
    def main(self, argv):
        """Main loop of the hardware controller daemon."""
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
        if log_level > cfg.log_level:
            log_level = cfg.log_level
            logger.setLevel(log_level)
        if cfg.log_file is not None:
            filelog = logging.handlers.RotatingFileHandler(cfg.log_file, maxBytes=52428800, backupCount=3)
            filelog.setLevel(cfg.log_level)
            filelog.setFormatter(formatter)
            logger.addHandler(filelog)
        
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
        server = wdhwdaemon.server.WdHwServer(self, cfg.socket_path, cfg.socket_group, cfg.socket_max_clients)
        
        _logger.debug("%s: Setting up signal handlers",
                      type(self).__name__)
        signal.signal(signal.SIGTERM, self.__sigHandler)
        signal.signal(signal.SIGINT,  self.__sigHandler)
        signal.signal(signal.SIGQUIT, self.__sigHandler)

        _logger.debug("%s: Daemonizing...waiting for shutdown signal",
                      type(self).__name__)
        while self.is_running:
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
    import sys
    d = WdHwDaemon()
    d.main(sys.argv)
