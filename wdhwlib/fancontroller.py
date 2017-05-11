#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Thermal Controller.

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

from messagequeue import Message
from messagequeue.threaded import Handler

from wdhwlib.temperature import TemperatureReader
from wdhwlib.wdpmcprotocol import PMCCommands


_logger = logging.getLogger(__name__)


class Condition(object):

    COMPARISON_LESSTHAN = 0
    COMPARISON_LESSEQUALTHAN = 1
    COMPARISON_GREATERTHAN = 2
    COMPARISON_GREATEREQUALTHAN = 3
    COMPARISON_ALWAYS_NOT_NONE = 4
    COMPARISON_ALWAYS = 5
    COMPARISON_NEVER = 6
    
    def __init__(self, output_level, comparison, limit):
        """Initializes a new thermal condition.
        
        Args:
            output_level (int): The output level associated with this condition.
            comparison (int): The type of comparison to apply between the test value
                and the limit.
            limit (float): The limit of the condition.
        """
        self.__output_level = output_level
        self.__comparison = comparison
        self.__limit = limit
    
    def test(self, value):
        """Tests the condition against a value.
        
        Args:
            value (float): The value to test the condition against.
        
        Returns:
            bool: True if the condition matches, else False.
        """
        if self.__comparison == Condition.COMPARISON_ALWAYS:
            return True
        elif value is None:
            return False
        elif self.__comparison == Condition.COMPARISON_LESSTHAN:
            return value < self.__limit
        elif self.__comparison == Condition.COMPARISON_GREATERTHAN:
            return value > self.__limit
        elif self.__comparison == Condition.COMPARISON_LESSEQUALTHAN:
            return value <= self.__limit
        elif self.__comparison == Condition.COMPARISON_GREATEREQUALTHAN:
            return value >= self.__limit
        elif self.__comparison == Condition.COMPARISON_ALWAYS_NOT_NONE:
            return True
        else:
            return False
    
    @property
    def level(self):
        """int: Condition output level."""
        return self.__output_level


class ThermalConditionMonitor(object):
    """Abstract monitor for thermal conditions.
    """
    
    def __init__(self, interval, log_variance, conditions):
        """Initializes a new thermal condition monitor.
        
        Args:
            interval (int): The interval between measurements of this monitor.
            log_variance (float): The minimum deviation between two subsequent
                measurements that causes log output.
            conditions (List[Condition]): An array of conditions to be checked
                (the list is checked in order of precedence).
        """
        super(ThermalConditionMonitor, self).__init__()
        self.__lock = threading.RLock()
        self.__level = None
        self.__temperature = None
        self.__interval = interval
        self.__conditions = conditions
        self.__log_variance = log_variance
        self._log_name = type(self).__name__
    
    def _getCurrentTemperature(self):
        """Get the current temperature reading of this monitor.
        
        This method must be implemented by classes implementing the thermal condition
        monitor.
        
        Returns:
            float: Current temperature reading of the sensor.
        """
        raise NotImplementedError('derived classes must implement this method')
    
    def __update(self, new_level, new_temperature):
        """Update the status of this monitor.
        
        Args:
            new_level (int): The new level of this monitor.
            new_temperature (float): The new temperature measured by this monitor.
        """
        with self.__lock:
            if new_temperature is not None:
                if new_level is None:
                    _logger.warning("%s: No condition matched for new temperature %.2f",
                                    self._log_name,
                                    new_temperature)
                elif self.__level is None:
                    _logger.info("%s: Level changed to %d (current temperature is %.2f)",
                                 self._log_name,
                                 new_level,
                                 new_temperature)
                elif new_level != self.__level:
                    _logger.info("%s: Level changed from %d to %d (current temperature is %.2f)",
                                 self._log_name,
                                 self.__level,
                                 new_level,
                                 new_temperature)
                elif self.__temperature is None:
                    _logger.info("%s: Temperature changed to %.2f (current level is %d)",
                                 self._log_name,
                                 new_temperature,
                                 new_level)
                elif abs(new_temperature - self.__temperature) >= log_variance:
                    _logger.info("%s: Temperature changed from %.2f to %.2f (current level is %d)",
                                 self._log_name,
                                 self.__temperature,
                                 new_temperature,
                                 new_level)
            elif (self.__temperature is not None) and (new_level is not None):
                _logger.warning("%s: No temperature reading available, level is %d",
                                self._log_name,
                                new_level)
                
            self.__level = new_level
            self.__temperature = new_temperature
    
    def __run(self):
        """Runnable target of the thermal condition monitor thread."""
        self.__update(None, None)
        
        while self.__running:
            temperature = _getCurrentTemperature()
            for condition in self.__conditions:
                if condition.test(temperature):
                    self.__update(condition.level, temperature)
                    break
            else:
                self.__update(None, temperature)
            
            time.sleep(self.__interval)
    
    def start(self):
        """Start the thermal condition monitor thread.
        
        Raises:
            RuntimeError: When calling ``start()`` on a thermal condition monitor
                that is already running.
        """
        with self.__lock:
            if not self.__running:
                self.__thread = threading.Thread(target=self.__run)
                self.__thread.daemon = True
                self.__running = True
                self.__thread.start()
            else:
                raise RuntimeError('start called when thermal condition monitor was already started')
    
    def join(self):
        """Join the thermal condition monitor thread.
        
        This stops the thermal condition monitor thread and waits for its completion.
        """
        with self.__lock:
            if self.__running:
                self.__running = False
                self.__thread.join()
                self.__thread = None
    
    @property
    def is_running(self):
        """bool: Is the thermal condition monitor thread in running state?"""
        with self.__lock:
            return self.__running
    
    @property
    def level(self):
        """int: Thermal condition level."""
        with self.__lock:
            return self.__level
    

class SystemTemperatureMonitor(ThermalConditionMonitor):
    """Monitor for system temperature.
    """
    
    def __init__(self, pmc):
        """Initializes a new system temperature monitor.
        
        Args:
            pmc (PMCCommands): An instance of the PMC interface.
        """
        if not isinstance(pmc, PMCCommands):
            raise TypeError("'pmc' is not an instance of PMCCommands")
        super(SystemTemperatureMonitor, self).__init__(
            30,
            5.0,
            [
                Condition(FanController.LEVEL_CRITICAL, Condition.COMPARISON_GREATERTHAN, 104.0),
                Condition(FanController.LEVEL_DANGER,   Condition.COMPARISON_GREATERTHAN,  94.0),
                Condition(FanController.LEVEL_HOT,      Condition.COMPARISON_GREATERTHAN,  89.0),
                Condition(FanController.LEVEL_WARM,     Condition.COMPARISON_GREATERTHAN,  84.0),
                Condition(FanController.LEVEL_NORMAL,   Condition.COMPARISON_GREATERTHAN,  74.0),
                Condition(FanController.LEVEL_COOL,     Condition.COMPARISON_GREATERTHAN,   1.0),
                Condition(FanController.LEVEL_UNDER,    Condition.COMPARISON_LESSEQUALTHAN, 1.0),
                Condition(FanController.LEVEL_CRITICAL, Condition.COMPARISON_ALWAYS, None),
            ])
        self.__pmc = pmc
    
    def _getCurrentTemperature(self):
        """Get the current temperature reading of this monitor.
        
        Returns:
            float: Current temperature reading of the sensor.
        """
        try:
            temperature = self.__pmc.getTemperature()
            if temperature is not None:
                return float(temperature)
        except:
            pass
        return None


class MemoryTemperatureMonitor(ThermalConditionMonitor):
    """Monitor for memory temperature.
    """
    
    def __init__(self, temperature_reader):
        """Initializes a new memory temperature monitor.
        
        Args:
            temperature_reader (TemperatureReader): An instance of the temperature reader.
        """
        if not isinstance(temperature_reader, TemperatureReader):
            raise TypeError("'temperature_reader' is not an instance of TemperatureReader")
        super(MemoryTemperatureMonitor, self).__init__(
            30,
            5.0,
            [
                Condition(FanController.LEVEL_CRITICAL, Condition.COMPARISON_GREATERTHAN,  94.0),
                Condition(FanController.LEVEL_DANGER,   Condition.COMPARISON_GREATERTHAN,  89.0),
                Condition(FanController.LEVEL_HOT,      Condition.COMPARISON_GREATERTHAN,  84.0),
                Condition(FanController.LEVEL_WARM,     Condition.COMPARISON_GREATERTHAN,  69.0),
                Condition(FanController.LEVEL_NORMAL,   Condition.COMPARISON_GREATERTHAN,  60.0),
                Condition(FanController.LEVEL_COOL,     Condition.COMPARISON_GREATERTHAN,   1.0),
                Condition(FanController.LEVEL_UNDER,    Condition.COMPARISON_LESSEQUALTHAN, 1.0),
                Condition(FanController.LEVEL_CRITICAL, Condition.COMPARISON_ALWAYS, None),
            ])
        self.__reader = temperature_reader
    
    def _getCurrentTemperature(self):
        """Get the current temperature reading of this monitor.
        
        Returns:
            float: Current temperature reading of the sensor.
        """
        try:
            return self.__reader.getMemoryTemperature()
        except:
            return None


class CPUTemperatureMonitor(ThermalConditionMonitor):
    """Monitor for CPU core temperature.
    """
    
    def __init__(self, temperature_reader):
        """Initializes a new CPU core temperature monitor.
        
        Args:
            temperature_reader (TemperatureReader): An instance of the temperature reader.
        """
        if not isinstance(temperature_reader, TemperatureReader):
            raise TypeError("'temperature_reader' is not an instance of TemperatureReader")
        super(CPUDeltaTemperatureMonitor, self).__init__(
            10,
            5.0,
            [
                Condition(FanController.LEVEL_NORMAL, Condition.COMPARISON_ALWAYS, 0.0),
            ])
        self.__reader = temperature_reader
    
    def _getCurrentTemperature(self):
        """Get the current temperature reading of this monitor.
        
        Returns:
            float: Current temperature reading of the sensor.
        """
        try:
            temperature = None
            for core in range(self.__reader.getNumCPUCores()):
                core_temperature = self.__reader.getCPUTemperature(core)
                if temperature is None:
                    temperature = core_temperature
                elif temperature < core_temperature:
                    temperature = core_temperature
            return temperature
        except:
            return None


class CPUDeltaTemperatureMonitor(ThermalConditionMonitor):
    """Monitor for CPU core delta temperature.
    """
    
    def __init__(self, temperature_reader):
        """Initializes a new CPU core delta temperature monitor.
        
        Args:
            temperature_reader (TemperatureReader): An instance of the temperature reader.
        """
        if not isinstance(temperature_reader, TemperatureReader):
            raise TypeError("'temperature_reader' is not an instance of TemperatureReader")
        super(CPUDeltaTemperatureMonitor, self).__init__(
            10,
            5.0,
            [
                Condition(FanController.LEVEL_CRITICAL, Condition.COMPARISON_LESSEQUALTHAN,  1.0),
                Condition(FanController.LEVEL_DANGER,   Condition.COMPARISON_LESSEQUALTHAN, 11.0),
                Condition(FanController.LEVEL_HOT,      Condition.COMPARISON_LESSEQUALTHAN, 16.0),
                Condition(FanController.LEVEL_WARM,     Condition.COMPARISON_LESSEQUALTHAN, 21.0),
                Condition(FanController.LEVEL_NORMAL,   Condition.COMPARISON_LESSEQUALTHAN, 30.0),
                Condition(FanController.LEVEL_COOL,     Condition.COMPARISON_LESSEQUALTHAN, 97.0),
                Condition(FanController.LEVEL_UNDER,    Condition.COMPARISON_GREATERTHAN,   97.0),
                Condition(FanController.LEVEL_CRITICAL, Condition.COMPARISON_ALWAYS, None),
            ])
        self.__reader = temperature_reader
    
    def _getCurrentTemperature(self):
        """Get the current temperature reading of this monitor.
        
        Returns:
            float: Current temperature reading of the sensor.
        """
        try:
            temperature = None
            for core in range(self.__reader.getNumCPUCores()):
                core_temperature = self.__reader.getCPUTemperatureDelta(core)
                if temperature is None:
                    temperature = core_temperature
                elif temperature > core_temperature:
                    temperature = core_temperature
            return temperature
        except:
            return None


class HardDiskDriveTemperatureMonitor(ThermalConditionMonitor):
    """Monitor for hard disk drive temperature.
    """
    
    def __init__(self, temperature_reader, drive):
        """Initializes a new hard disk drive temperature monitor.
        
        Args:
            temperature_reader (TemperatureReader): An instance of the temperature reader.
            drive (str): The hard disk drive to monitor.
        """
        if not isinstance(temperature_reader, TemperatureReader):
            raise TypeError("'temperature_reader' is not an instance of TemperatureReader")
        super(HardDiskDriveTemperatureMonitor, self).__init__(
            600,
            5.0,
            [
                Condition(FanController.LEVEL_CRITICAL, Condition.COMPARISON_GREATERTHAN,   74.0),
                Condition(FanController.LEVEL_SHUTDOWN, Condition.COMPARISON_GREATERTHAN,   71.0),
                Condition(FanController.LEVEL_DANGER,   Condition.COMPARISON_GREATERTHAN,   67.0),
                Condition(FanController.LEVEL_HOT,      Condition.COMPARISON_GREATERTHAN,   64.0),
                Condition(FanController.LEVEL_WARM,     Condition.COMPARISON_GREATERTHAN,   40.0),
                Condition(FanController.LEVEL_NORMAL,   Condition.COMPARISON_GREATERTHAN,   37.0),
                Condition(FanController.LEVEL_COOL,     Condition.COMPARISON_GREATERTHAN,    1.0),
                Condition(FanController.LEVEL_UNDER,    Condition.COMPARISON_LESSEQUALTHAN,  1.0),
                Condition(FanController.LEVEL_NORMAL,   Condition.COMPARISON_ALWAYS, None),
            ])
        self.__reader = temperature_reader
        self.__drive = drive
        self._log_name = "{0}({1})".format(type(self).__name__, drive)
    
    def _getCurrentTemperature(self):
        """Get the current temperature reading of this monitor.
        
        Returns:
            float: Current temperature reading of the sensor.
        """
        try:
            return self.__reader.getHDTemperature(self.__drive)
        except:
            return None


class FanController(object):
    """Fan controller.
    """
    
    INTERVAL = 10
    
	LEVEL_UNDER = 0
    LEVEL_COOL = 1
    LEVEL_NORMAL = 2
    LEVEL_WARM = 3
    LEVEL_HOT = 4
    LEVEL_DANGER = 5
    LEVEL_SHUTDOWN = 6
    LEVEL_CRITICAL = 7
    
    FAN_MIN = 20
    FAN_MAX = 100
    FAN_STEP_INC = 10
    FAN_STEP_DEC = 10
    FAN_RPM_MIN = 50
    
    def __init__(self, pmc, temperature_reader):
        """Initializes a new fan controller.
        
        Args:
            pmc (PMCCommands): An instance of the PMC interface.
            temperature_reader (TemperatureReader): An instance of the temperature reader.
        """
        super(FanController, self).__init__()
        self.__lock = threading.RLock()
        self.__running = False
        self.__thread = None
        self.__pmc = pmc
        self.__monitors = [
            SystemTemperatureMonitor(pmc),
            MemoryTemperatureMonitor(temperature_reader),
            CPUTemperatureMonitor(temperature_reader),
            CPUDeltaTemperatureMonitor(temperature_reader),
            HardDiskDriveTemperatureMonitor(temperature_reader, "/dev/sda"),
            HardDiskDriveTemperatureMonitor(temperature_reader, "/dev/sdb"),
            HardDiskDriveTemperatureMonitor(temperature_reader, "/dev/sdc"),
        ]
    
    def __run(self):
        """Runnable target of the fan controller thread."""
        last_global_level = LEVEL_UNDER
        while self.__running:
            global_level = LEVEL_UNDER
            for monitor in self.__monitors:
                level = monitor.level
                if global_level < level:
                    global_level = level
            
            fan_speed_change = False
            fan_speed = 0
            fan_rpm = 0
            try:
                fan_speed = self.__pmc.getFanSpeed()
                fan_rpm = self.__pmc.getFanRPM()
            except:
                # PMC or fan error
                fan_speed = FanController.FAN_MAX
                fan_speed_change = True
                #command_alert fan_not_working
            
            if fan_rpm < FanController.FAN_RPM_MIN:
                fan_speed = FanController.FAN_MAX
                fan_speed_change = True
                #command_alert fan_not_working
            
            if global_level >= FanController.LEVEL_HOT:
                if fan_speed < FanController.FAN_MAX:
                    fan_speed = FanController.FAN_MAX
                    fan_speed_change = True
            elif global_level > FanController.LEVEL_NORMAL:
                if fan_speed < FanController.FAN_MAX:
                    fan_speed += FanController.FAN_STEP_INC
                    fan_speed_change = True
            elif global_level < FanController.LEVEL_NORMAL:
                if fan_speed > FanController.FAN_MIN:
                    fan_speed -= FanController.FAN_STEP_DEC
                    fan_speed_change = True
            
            if fan_speed_change:
                if fan_speed > FanController.FAN_MAX:
                    fan_speed = FanController.FAN_MAX
                elif fan_speed < FanController.FAN_MIN:
                    fan_speed = FanController.FAN_MIN
                _logger.info("%s: Setting fan speed to %d percent",
                                 type(self).__name__,
                                 fan_speed)
                try:
                    self.__pmc.setFanSpeed(fan_speed)
                except:
                    # PMC or fan error
                    #command_alert fan_not_working
            
            if global_level != last_global_level:
                _logger.info("%s: Alert level changed from %d to %d",
                                 type(self).__name__,
                                 last_global_level,
                                 global_level)
                if global_level >= FanController.LEVEL_CRITICAL:
                    # shutdown immediately
                    #result = subprocess.call(["shutdown", "-P", "now"])
                elif global_level >= FanController.LEVEL_SHUTDOWN:
                    # schedule shutdown in 3600 seconds
                    #result = subprocess.call(["shutdown", "-P", "+60"])
                else:
                    # cancel pending shutdown
                    #result = subprocess.call(["shutdown", "-c"])
            
            last_global_level = global_level
            time.sleep(FanController.INTERVAL)
    
    def start(self):
        """Start the fan controller thread.
        
        Raises:
            RuntimeError: When calling ``start()`` on a fan controller that is
                already running.
        """
        with self.__lock:
            if not self.__running:
                for monitor in self.__monitors:
                    monitor.start()
                self.__thread = threading.Thread(target=self.__run)
                self.__thread.daemon = False
                self.__running = True
                self.__thread.start()
            else:
                raise RuntimeError('start called when fan controller was already started')
    
    def join(self):
        """Join the fan controller thread.
        
        This stops the fan controller thread and waits for its completion.
        """
        with self.__lock:
            if self.__running:
                self.__running = False
                self.__thread.join()
                self.__thread = None
                for monitor in self.__monitors:
                    monitor.join()
    
    @property
    def is_running(self):
        """bool: Is the fan controller thread in running state?"""
        with self.__lock:
            return self.__running


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

