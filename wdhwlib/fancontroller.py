#!/usr/bin/env python3
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
import threading

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
    
    Attributes:
        is_running: Is the thermal condition monitor thread in running state?
        level: Thermal condition level.
        temperature: Last observed temperature.
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
        super().__init__()
        self.__wait = threading.Condition()
        self.__lock = threading.RLock()
        self.__running = False
        self.__thread = None
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
                elif abs(new_temperature - self.__temperature) >= self.__log_variance:
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
        
        with self.__wait:
            while self.__running:
                temperature = self._getCurrentTemperature()
                for condition in self.__conditions:
                    if condition.test(temperature):
                        self.__update(condition.level, temperature)
                        break
                else:
                    self.__update(None, temperature)
                
                self.__wait.wait(self.__interval)
    
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
        thread = None
        with self.__wait, self.__lock:
            if self.__running:
                self.__running = False
                thread = self.__thread
                self.__thread = None
                self.__wait.notifyAll()
        if thread is not None:
            thread.join()
    
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
    
    @property
    def temperature(self):
        """int: Last observed temperature."""
        with self.__lock:
            return self.__temperature
    

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
        super().__init__(
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
        except Exception:
            pass
        return None


class MemoryTemperatureMonitor(ThermalConditionMonitor):
    """Monitor for memory temperature.
    """
    
    def __init__(self, temperature_reader, dimm_index):
        """Initializes a new memory temperature monitor.
        
        Args:
            temperature_reader (TemperatureReader): An instance of the temperature reader.
            dimm_index (int): Index of the memory bank and DIMM to monitor.
        """
        if not isinstance(temperature_reader, TemperatureReader):
            raise TypeError("'temperature_reader' is not an instance of TemperatureReader")
        super().__init__(
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
                Condition(FanController.LEVEL_NORMAL,   Condition.COMPARISON_ALWAYS, None),
            ])
        self.__reader = temperature_reader
        self.__dimm_index = dimm_index
    
    def _getCurrentTemperature(self):
        """Get the current temperature reading of this monitor.
        
        Returns:
            float: Current temperature reading of the sensor.
        """
        try:
            return self.__reader.getMemoryTemperature(self.__dimm_index)
        except Exception:
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
        super().__init__(
            10,
            5.0,
            [
                Condition(FanController.LEVEL_NORMAL, Condition.COMPARISON_ALWAYS, None),
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
        except Exception:
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
        super().__init__(
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
        except Exception:
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
        super().__init__(
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
        except Exception:
            return None


class FanControllerCallback(object):
    """Callback interface for fan controller status callbacks.
    """
    
    def controllerStarted(self):
        """Callback invoked when the fan controller is up and running.
        
        This callback is invoked on a dedicated message handler thread and
        may be blocked for processing the status message.
        """
        pass
    
    def controllerStopped(self):
        """Callback invoked when the fan controller was stopped.
        
        This callback is invoked on a dedicated message handler thread and
        may be blocked for processing the status message.
        """
        pass
    
    def fanError(self):
        """Callback invoked when the fan or the PMC does not work/respond.
        
        This callback is invoked on a dedicated message handler thread and
        may be blocked for processing the status message.
        """
        pass
    
    def shutdownRequestImmediate(self):
        """Callback invoked when the temperature level is critical and an immediate shutdown is necessary.
        
        This callback is invoked on a dedicated message handler thread and
        may be blocked for processing the status message.
        """
        pass
    
    def shutdownRequestDelayed(self):
        """Callback invoked when the temperature level is close to critical and a shutdown should be scheduled.
        
        This callback is invoked on a dedicated message handler thread and
        may be blocked for processing the status message.
        """
        pass
    
    def shutdownCancelPending(self):
        """Callback invoked when the temperature level is in the normal operation range and pending shutdowns should be canceled.
        
        This callback is invoked on a dedicated message handler thread and
        may be blocked for processing the status message.
        """
        pass
    
    def levelChanged(self, new_level, old_level):
        """Callback invoked when the temperature level changed.
        
        This callback is invoked on a dedicated message handler thread and
        may be blocked for processing the status message.
        """
        pass


class FanControllerCallbackHandler(Handler):
    """Message queue handler for processing fan controller status callbacks.
    """
    
    MSG_CTRL_STARTED = Handler.NEXT_MSG_ID
    MSG_CTRL_STOPPED = MSG_CTRL_STARTED + 1
    MSG_FAN_ERROR = MSG_CTRL_STOPPED + 1
    MSG_SHUTDOWN_IMMEDIATE = MSG_FAN_ERROR + 1
    MSG_SHUTDOWN_DELAYED = MSG_SHUTDOWN_IMMEDIATE + 1
    MSG_SHUTDOWN_CANCEL = MSG_SHUTDOWN_DELAYED + 1
    MSG_LEVEL_CHANGED = MSG_SHUTDOWN_CANCEL + 1
    NEXT_MSG_ID = MSG_LEVEL_CHANGED + 1
    
    def __init__(self, status_callback):
        """Initializes a new interrupt queue handler.
        
        Args:
            interrupt_callback (FanControllerCallback): The associated callback
                implementation that consumes status updates.
        """
        super().__init__(True)
        self.__callback = status_callback
    
    def handleMessage(self, msg):
        if msg.what == FanControllerCallbackHandler.MSG_CTRL_STARTED:
            self.__callback.controllerStarted()
        elif msg.what == FanControllerCallbackHandler.MSG_CTRL_STOPPED:
            self.__callback.controllerStopped()
        elif msg.what == FanControllerCallbackHandler.MSG_FAN_ERROR:
            self.__callback.fanError()
        elif msg.what == FanControllerCallbackHandler.MSG_SHUTDOWN_IMMEDIATE:
            self.__callback.shutdownRequestImmediate()
        elif msg.what == FanControllerCallbackHandler.MSG_SHUTDOWN_DELAYED:
            self.__callback.shutdownRequestDelayed()
        elif msg.what == FanControllerCallbackHandler.MSG_SHUTDOWN_CANCEL:
            self.__callback.shutdownCancelPending()
        elif msg.what == FanControllerCallbackHandler.MSG_LEVEL_CHANGED:
            self.__callback.levelChanged(msg.obj[0], msg.obj[1])
        else:
            super().handleMessage(msg)


class FanController(FanControllerCallback):
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
    
    FAN_DEFAULT = 30
    FAN_MIN = 20
    FAN_MAX = 100
    FAN_STEP_INC = 10
    FAN_STEP_DEC = 10
    FAN_RPM_MIN = 50
    
    def __init__(self, pmc, temperature_reader, disk_drives, num_dimms):
        """Initializes a new fan controller.
        
        Args:
            pmc (PMCCommands): An instance of the PMC interface.
            temperature_reader (TemperatureReader): An instance of the temperature reader.
            disk_drives (List(str)): A list of HDD device names to monitor.
            num_dimms (int): The number of memory DIMMs to monitor.
        """
        super().__init__()
        self.__status_handler = FanControllerCallbackHandler(self)
        self.__wait = threading.Condition()
        self.__lock = threading.RLock()
        self.__running = False
        self.__thread = None
        self.__pmc = pmc
        self.__monitors = [
            SystemTemperatureMonitor(pmc),
            CPUTemperatureMonitor(temperature_reader),
            CPUDeltaTemperatureMonitor(temperature_reader),
        ]
        for disk in disk_drives:
            self.__monitors.append(HardDiskDriveTemperatureMonitor(temperature_reader, disk))
        for dimm_index in range(0, num_dimms):
            self.__monitors.append(MemoryTemperatureMonitor(temperature_reader, dimm_index))
    
    def __run(self):
        """Runnable target of the fan controller thread."""
        last_global_level = FanController.LEVEL_UNDER
        pending_shutdown = False
        self.__status_handler.sendMessage(
                Message(FanControllerCallbackHandler.MSG_CTRL_STARTED))
        with self.__wait:
            try:
                while self.__running:
                    global_level = FanController.LEVEL_UNDER
                    for monitor in self.__monitors:
                        level = monitor.level
                        if level is not None:
                            if global_level < level:
                                global_level = level
                    
                    fan_speed_change = False
                    fan_speed = 0
                    fan_rpm = 0
                    try:
                        fan_speed = self.__pmc.getFanSpeed()
                        fan_rpm = self.__pmc.getFanRPM()
                    except Exception:
                        # PMC or fan error
                        fan_speed = FanController.FAN_MAX
                        fan_speed_change = True
                        self.__status_handler.sendMessage(
                                Message(FanControllerCallbackHandler.MSG_FAN_ERROR))
                    
                    if fan_rpm < FanController.FAN_RPM_MIN:
                        fan_speed = FanController.FAN_MAX
                        fan_speed_change = True
                        self.__status_handler.sendMessage(
                                Message(FanControllerCallbackHandler.MSG_FAN_ERROR))
                    
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
                    elif global_level == FanController.LEVEL_NORMAL:
                        if fan_speed != FanController.FAN_DEFAULT:
                            fan_speed = FanController.FAN_DEFAULT
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
                        except Exception:
                            # PMC or fan error
                            self.__status_handler.sendMessage(
                                Message(FanControllerCallbackHandler.MSG_FAN_ERROR))
                    
                    if global_level != last_global_level:
                        _logger.info("%s: Alert level changed from %d to %d",
                                     type(self).__name__,
                                     last_global_level,
                                     global_level)
                        if global_level >= FanController.LEVEL_CRITICAL:
                            pending_shutdown = True
                            self.__status_handler.sendMessage(
                                Message(FanControllerCallbackHandler.MSG_SHUTDOWN_IMMEDIATE))
                        elif global_level >= FanController.LEVEL_SHUTDOWN:
                            pending_shutdown = True
                            self.__status_handler.sendMessage(
                                Message(FanControllerCallbackHandler.MSG_SHUTDOWN_DELAYED))
                        else:
                            if pending_shutdown:
                                pending_shutdown = False
                                self.__status_handler.sendMessage(
                                    Message(FanControllerCallbackHandler.MSG_SHUTDOWN_CANCEL))
                        self.__status_handler.sendMessage(
                            Message(FanControllerCallbackHandler.MSG_LEVEL_CHANGED,
                                    (global_level, last_global_level)))
                    
                    last_global_level = global_level
                    self.__wait.wait(FanController.INTERVAL)
            finally:
                for monitor in self.__monitors:
                    monitor.join()
                self.__status_handler.sendMessage(
                        Message(FanControllerCallbackHandler.MSG_CTRL_STOPPED))
                self.__status_handler.join()
    
    def start(self):
        """Start the fan controller thread.
        
        Raises:
            RuntimeError: When calling ``start()`` on a fan controller that is
                already running.
        """
        with self.__lock:
            if not self.__running:
                self.__status_handler.start()
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
        thread = None
        with self.__wait, self.__lock:
            if self.__running:
                self.__running = False
                thread = self.__thread
                self.__thread = None
                self.__wait.notifyAll()
        if thread is not None:
            thread.join()
    
    @property
    def is_running(self):
        """bool: Is the fan controller thread in running state?"""
        with self.__lock:
            return self.__running
    
    def controllerStarted(self):
        pass
    
    def controllerStopped(self):
        pass
    
    def fanError(self):
        pass
    
    def shutdownRequestImmediate(self):
        pass
    
    def shutdownRequestDelayed(self):
        pass
    
    def shutdownCancelPending(self):
        pass
    
    def levelChanged(self, new_level, old_level):
        pass


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

