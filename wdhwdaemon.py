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
import subprocess
import threading
import time

from wdhwlib.fancontroller import FanController, FanControllerCallback
from wdhwlib.temperature import TemperatureReader
from wdhwlib.wdpmcprotocol import PMCCommands
from wdhwlib import wdpmcprotocol


_logger = logging.getLogger(__name__)


class PMCCommandsImpl(PMCCommands):
    
    def __init__(self):
        super(PMCController, self).__init__()
    
    def interruptReceived(self):
        pass
    
    def sequenceError(self, code, value):
        pass
    
    def connectionClosed(self, error):
        pass


class FanControllerImpl(FanController):
    
    def __init__(self, pmc, temperature_reader):
        super(FanControllerImpl, self).__init__(pmc, temperature_reader)
        self.__pmc = pmc
    
    def controllerStarted(self):
        self.__pmc.setLEDStatus(wdpmcprotocol.PMC_LED_POWER_BLUE)
        self.__pmc.setLEDBlink(wdpmcprotocol.PMC_LED_NONE)
        pass
    
    def controllerStopped(self):
        self.__pmc.setLEDStatus(wdpmcprotocol.PMC_LED_POWER_RED)
        self.__pmc.setLEDBlink(wdpmcprotocol.PMC_LED_NONE)
        self.__pmc.setPowerLEDPulse(False)
        pass
    
    def fanError(self):
        # shutdown immediately???
        self.__pmc.setLEDStatus(wdpmcprotocol.PMC_LED_NONE)
        self.__pmc.setLEDBlink(wdpmcprotocol.PMC_LED_POWER_RED)
        self.__pmc.setPowerLEDPulse(False)
        pass
    
    def shutdownRequestImmediate(self):
        # shutdown immediately
        #result = subprocess.call(["shutdown", "-P", "now"])
        self.__pmc.setLEDStatus(wdpmcprotocol.PMC_LED_NONE)
        self.__pmc.setLEDBlink(wdpmcprotocol.PMC_LED_POWER_RED)
        self.__pmc.setPowerLEDPulse(False)
        pass
    
    def shutdownRequestDelayed(self):
        # schedule shutdown in 3600 seconds
        #result = subprocess.call(["shutdown", "-P", "+60"])
        self.__pmc.setLEDStatus(wdpmcprotocol.PMC_LED_POWER_RED)
        self.__pmc.setLEDBlink(wdpmcprotocol.PMC_LED_NONE)
        self.__pmc.setPowerLEDPulse(False)
        pass
    
    def shutdownCancelPending(self):
        # cancel pending shutdown
        #result = subprocess.call(["shutdown", "-c"])
        self.__pmc.setLEDStatus(wdpmcprotocol.PMC_LED_POWER_BLUE)
        self.__pmc.setLEDBlink(wdpmcprotocol.PMC_LED_NONE)
        pass
    
    def levelChanged(self, new_level, old_level):
        pass


class WdHwDaemon(object):
    """Hardware controller daemon.
    """
    
    def __init__(self):
        """Initializes a new hardware controller daemon."""
        super(WdHwDaemon, self).__init__()
        self.__lock = threading.RLock()
        self.__running = False
        self.__thread = None
    
    def __run(self):
        """Runnable target of the hardware controller daemon."""
        print "Starting PMC manager ..."
        pmc = PMCCommandsImpl()
        pmc.connect()
        
        pmc.setLEDStatus(wdpmcprotocol.PMC_LED_NONE)
        pmc.setLEDBlink(wdpmcprotocol.PMC_LED_POWER_BLUE)
        pmc.setPowerLEDPulse(False)
        
        pmc_version = pmc.getVersion()
        print "PMC manager connected to {1}.".format(pmc_version)
        
        print "Starting temperature reader ..."
        temperature_reader = TemperatureReader()
        temperature_reader.start()
        
        num_cpus = temperature_reader.getNumCPUCores()
        print "Discovered {1} CPU cores.".format(num_cpus)
        
        print "Starting fan controller ..."
        disks_to_monitor = [ "/dev/sda", "/dev/sdb", "/dev/sdc" ]
        fan_controller = FanControllerImpl(pmc,
                                           temperature_reader,
                                           disks_to_monitor)
        fan_controller.start()
        
        print ""
        while self.__running:
            sys.stdout.write("Command: ")
            cmd = sys.stdin.readline().lower()
            if (cmd == ""):
                sys.stdout.write("1: Get PMC version")
                sys.stdout.write("0: Exit")
            elif (cmd == "0"):
                self.__running = False
            elif (cmd == "1"):
                sys.stdout.write(pmc.getVersion())
        
        print "Stopping fan controller ..."
        fan_controller.join()
        print "Stopping temperature reader ..."
        temperature_reader.join()
        print "Stopping PMC manager ..."
        pmc.close()
        
    def start(self):
        """Start the hardware controller daemon.
        
        Raises:
            RuntimeError: When calling ``start()`` on a hardware controller daemon
                that is already running.
        """
        with self.__lock:
            if not self.__running:
                self.__thread = threading.Thread(target=self.__run)
                self.__thread.daemon = False
                self.__running = True
                self.__thread.start()
            else:
                raise RuntimeError('start called when hardware controller daemon was already started')
    
    def join(self):
        """Join the hardware controller daemon.
        
        This stops the hardware controller daemon and waits for its completion.
        """
        with self.__lock:
            if self.__running:
                self.__running = False
                self.__thread.join()
                self.__thread = None
    
    @property
    def is_running(self):
        """bool: Is the hardware controller daemon in running state?"""
        with self.__lock:
            return self.__running


if __name__ == "__main__":
    wdhwd = WdHwDaemon()
    wdhwd.start()

