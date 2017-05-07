#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""System Component Temperature Readings.

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


import os
from os.path import isdir,join
import re
import subprocess


_CPUINFO_FILENAME = "/proc/cpuinfo"
_CPUINFO_REGEX_CORES = re.compile(r"^cpu\s+cores.*:\s*([0-9]+)\s*$")

_CORETEMP_FILENAME_BASE = "/sys/class/hwmon/hwmon0/temp{0:d}_{1}"
_CORETEMP_CORE_OFFSET = 2
_CORETEMP_TYPE_JUNCTION_VALUE = "value"
_CORETEMP_TYPE_JUNCTION_REGULAR_MAX = "max"
_CORETEMP_TYPE_JUNCTION_CRITICAL_MAX = "crit"
_CORETEMP_TYPE_ALARM = "crit_alarm"
_CORETEMP_REGEX_VALUE = re.compile(r"^([0-9]+)[^0-9]*$")

_SMBUS_DEVICES_PATH = "/sys/class/i2c-dev"
_SMBUS_REGEX_DEVICEINDEX = re.compile(r"^i2c-([0-9]+)$")
_SMBUS_REGEX_HEXID = re.compile(r"^\s*0x([0-9a-f]+)\s*$")
_SMBUS_VENDORID_FILE = "device/device/vendor"
_SMBUS_DEVICEID_FILE = "device/device/device"
_SMBUS_MEMORYTEMP_VENDORID = "8086"
_SMBUS_MEMORYTEMP_DEVICEID = "1f3c"
_SMBUS_MEMORYTEMP_ADDRESS = 25
_SMBUS_MEMORYTEMP_COMMAND = 5

_HDSMART_COMMAND_BASE = ["/usr/sbin/smartctl", "-A", "-d", "ata"]
_HDSMART_DISKS = ["/dev/sda", "/dev/sdb"]
_HDSMART_REGEX_TEMPERATURE = re.compile(r"^\s*194\s+\S+\s+[0-9a-fA-FxX]+\s+([0-9]+)\s+.*$")


class TemperatureReader(object):
    """Temperature measurement reader.
    """
    
    def __init__(self):
        """Initializes a new instance of the temperature reader."""
        super(TemperatureReader, self).__init__()
    
    def __readCoreTempValue(self, cpu_index, value_type):
        """Get the contents of a coretemp file.
        
        Args:
            cpu_index (int): Index of the CPU core.
            value_type (str): Type of value to read (e.g. "value", "crit").
        
        Returns:
            int: This method returns the raw value contained in the file.
        """
        file_name = _CORETEMP_FILENAME_BASE.format(_CORETEMP_CORE_OFFSET + cpu_index,
                                                   value_type)
        try:
            with open(file_name, "r") as f:
                raw_value = f.readline()
                match = _CORETEMP_REGEX_VALUE.match(raw_value)
                if match is not None:
                    int_value = int(match.group(1))
                    return int_value
                else:
                    return -1
        except IOError as e:
            return -1
    
    def getNumCPUCores(self):
        """Get number of CPU cores.
        
        Returns:
            int: The number of CPU cores.
        """
        try:
            with open(_CPUINFO_FILENAME, "r") as f:
                for line in f:
                    match = _CPUINFO_REGEX_CORES.match(line)
                    if match is not None:
                        num_cores = int(match.group(1))
                        return num_cores
        except IOError as e:
            pass
        return 0
    
    def getCPUTemperature(self, cpu_index):
        """Get the junction temperature for a given CPU core.
        
        Args:
            cpu_index (int): Index of the CPU core.
        
        Returns:
            float: The temperature in degrees Celsius.
        """
        tj_value = __readCoreTempValue(cpu_index,
                                       _CORETEMP_TYPE_JUNCTION_VALUE)
        if tj_value == -1:
            return -1.0
        return float(tj_value) / 1000.0
    
    def getCPUTemperatureDelta(self, cpu_index):
        """Get the junction temperature as delta to the maximum for a given CPU core.
        
        Args:
            cpu_index (int): Index of the CPU core.
        
        Returns:
            float: The temperature delta in degrees Celsius.
        """
        tj_crit_max = __readCoreTempValue(cpu_index,
                                          _CORETEMP_TYPE_JUNCTION_CRITICAL_MAX)
        tj_delta = __readCoreTempValue(cpu_index,
                                       _CORETEMP_TYPE_JUNCTION_VALUE)
        if (tj_crit_max == -1) or (tj_value == -1):
            return -1.0
        return float(tj_crit_max - tj_value) / 1000.0
    
    def getCPUTemperatureMax(self, cpu_index):
        """Get the maximum junction temperature for a given CPU core.
        
        Args:
            cpu_index (int): Index of the CPU core.
        
        Returns:
            float: The maximum junction temperature in degrees Celsius.
        """
        tj_max = __readCoreTempValue(cpu_index,
                                     _CORETEMP_TYPE_JUNCTION_MAX)
        if tj_max == -1:
            return -1.0
        return float(tj_max) / 1000.0
    
    def getCPUTemperatureCriticalMax(self, cpu_index):
        """Get the critical maximum junction temperature for a given CPU core.
        
        Args:
            cpu_index (int): Index of the CPU core.
        
        Returns:
            float: The critical maximum junction temperature in degrees Celsius.
        """
        tj_crit_max = __readCoreTempValue(cpu_index,
                                          _CORETEMP_TYPE_JUNCTION_CRITICAL_MAX)
        if tj_crit_max == -1:
            return -1.0
        return float(tj_crit_max) / 1000.0
    
    def getCPUTemperatureOutOfSpec(self, cpu_index):
        """Get the junction temperature out-of-spec flag for a given CPU core.
        
        Args:
            cpu_index (int): Index of the CPU core.
        
        Returns:
            bool: The temperature out-of-spec flag.
        """
        crit_alarm = __readCoreTempValue(cpu_index,
                                         _CORETEMP_TYPE_ALARM)
        return (crit_alarm != 0)
    
    def __openMemorySMBusDevice(self):
        """Open SMBus device for reading the memory temperature.
        
        Returns:
            smbus.SMBus: The SMBus device object.
        """
        for device in os.listdir(_SMBUS_DEVICES_PATH):
            device_abs = join(_SMBUS_DEVICES_PATH, device)
            if not isdir(device_abs):
                continue
            
            device_id_file = join(_SMBUS_DEVICES_PATH, device, _SMBUS_VENDORID_FILE)
            if not isfile(device_id_file):
                continue
            try:
                with open(device_id_file, "r") as f:
                    raw_value = f.readline()
                    match = _SMBUS_REGEX_HEXID.match(raw_value)
                    if match is None:
                        continue
                    if _SMBUS_MEMORYTEMP_VENDORID != match.group(1).lower():
                        continue
            except IOError as e:
                continue
            
            device_id_file = join(_SMBUS_DEVICES_PATH, device, _SMBUS_DEVICEID_FILE)
            if not isfile(device_id_file):
                continue
            try:
                with open(device_id_file, "r") as f:
                    raw_value = f.readline()
                    match = _SMBUS_REGEX_HEXID.match(raw_value)
                    if match is None:
                        continue
                    if _SMBUS_MEMORYTEMP_DEVICEID != match.group(1).lower():
                        continue
            except IOError as e:
                continue
            
            match = _SMBUS_REGEX_DEVICEINDEX.match(device)
            if match is not None:
                device_idx = int(match.group(1))
                return smbus.SMBus(device_idx)
            
        return None
    
    def getMemoryTemperature(self):
        """Get the temperature of the memory bank.
        
        Returns:
            float: The temperature of the memory bank.
        """
        sb = __openMemorySMBusDevice()
        if sb is not None:
            try:
                raw_value = sb.read_word_data(_SMBUS_MEMORYTEMP_ADDRESS,
                                              _SMBUS_MEMORYTEMP_COMMAND)
            except IOError:
                pass
            else:
                temperature = ((raw_value & 0x0FF00) >> 8) |
                              ((raw_value & 0x000FF) << 8)
                return float(temperature) / 16.0
            finally:
                try:
                    sb.close()
                except:
                    pass
        return -1.0
    
    def getHDTemperature(self, hdd):
        """Get the temperature of the memory bank.
        
        Args:
            hdd (str): The device file of the hard disk.
        
        Returns:
            float: The temperature of the hard disk drive.
        """
        try:
            result = subprocess.check_output(_HDSMART_COMMAND_BASE + [hdd])
            for line in result.splitlines():
                match = _HDSMART_REGEX_TEMPERATURE.match(line)
                if match is not None:
                    temperature = int(match.group(1))
                    return float(temperature)
        except CalledProcessError:
            pass
        return -1.0


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

