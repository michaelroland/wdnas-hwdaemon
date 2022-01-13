#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""System Component Temperature Readings.

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


import logging
import os
import os.path
import re
import smbus
import subprocess
import threading


_logger = logging.getLogger(__name__)


_CPUINFO_FILENAME = "/proc/cpuinfo"
_CPUINFO_REGEX_CORES = re.compile(r"^cpu\s+cores.*:\s*([0-9]+)\s*$")

_CORETEMP_DEVICES_PATH = "/sys/class/hwmon"
_CORETEMP_SENSORNAME_FILE = "name"
_CORETEMP_SENSORNAME_VALUE = "coretemp"
_CORETEMP_SENSOR_FILEBASE = "temp{0:d}_{1}"
_CORETEMP_CORE_OFFSET = 2
_CORETEMP_TYPE_JUNCTION_VALUE = "input"
_CORETEMP_TYPE_JUNCTION_REGULAR_MAX = "max"
_CORETEMP_TYPE_JUNCTION_CRITICAL_MAX = "crit"
_CORETEMP_TYPE_ALARM = "crit_alarm"
_CORETEMP_REGEX_VALUE = re.compile(r"^([0-9]+)[^0-9]*$")

_SMBUS_DEVICES_PATH = "/sys/bus/i2c/devices"
_SMBUS_REGEX_DEVICENAME = re.compile(r"^([0-9]+)-([0-9a-fA-F]+)$")
_SMBUS_DEVICENAME_FILE = "name"
_SMBUS_DEVICENAME_VALUE = "spd"
_SMBUS_MEMORY_SPD_EEPROM_ADDRESS = 0x50
_SMBUS_MEMORY_SPD_EEPROM_FILE = "eeprom"
_SMBUS_MEMORY_SPD_EEPROM_REG_TEMPSENSOR = 32
_SMBUS_MEMORY_SPD_EEPROM_FLAG_TEMPSENSOR = 0x080
_SMBUS_MEMORY_SPD_TEMP_ADDRESS = 0x18
_SMBUS_MEMORY_SPD_TEMP_REG_TEMPERATURE = 5

_HDSMART_DISCOVERY_COMMAND = ["lsblk", "-S", "-d", "-l", "-n", "-o", "NAME,TRAN"]
_HDSMART_DISCOVERY_REGEX = re.compile(r"^(\S+)\s+(\S*)$")
_HDSMART_DISCOVERY_TYPE = "sata"
_HDSMART_COMMAND1_BASE = ["sudo", "-n", "hddtemp", "-n", "-u", "C"]
_HDSMART_REGEX_TEMPERATURE1 = re.compile(r"^([0-9]+)[^0-9]*$")
_HDSMART_COMMAND2_BASE = ["sudo", "-n", "smartctl", "-A"]
_HDSMART_REGEX_TEMPERATURE2 = re.compile(r"^\s*194\s+.*\s+([0-9]+)\s*$")


class TemperatureReader(object):
    """Temperature measurement reader.
    """
    
    def __init__(self):
        """Initializes a new instance of the temperature reader."""
        super().__init__()
        self.__lock = threading.RLock()
        self.__running = False
        self.__CORETEMP = None
        self.__HDSMART_METHOD = None
    
    def connect(self):
        """Connect the temperature reader.
        """
        with self.__lock:
            if not self.__running:
                self.__CORETEMP = self.__findCoreTempSensor()
                self.__running = True
            else:
                raise RuntimeError('connect called when temperature reader was already connected')
    
    def close(self):
        """Close the temperature reader.
        """
        with self.__lock:
            if self.__running:
                self.__running = False
    
    @property
    def is_running(self):
        """bool: Is the temperature reader connected?"""
        with self.__lock:
            return self.__running
    
    def __findCoreTempSensor(self):
        """Find the coretemp sensor.
        
        Returns:
            str: This method returns the file name template for the coretemp sensor value files.
        """
        for device in os.listdir(_CORETEMP_DEVICES_PATH):
            device_abs = os.path.join(_CORETEMP_DEVICES_PATH, device)
            if not os.path.isdir(device_abs):
                continue
            
            name_file = os.path.join(device_abs, _CORETEMP_SENSORNAME_FILE)
            if not os.path.isfile(name_file):
                continue
            try:
                with open(name_file, 'rt', encoding='utf-8', errors='replace') as f:
                    raw_value = f.readline()
                    if _CORETEMP_SENSORNAME_VALUE not in raw_value:
                        continue
            except IOError as e:
                continue
            
            return os.path.join(device_abs, _CORETEMP_SENSOR_FILEBASE)
            
        return None
    
    def __readCoreTempValue(self, cpu_index, value_type):
        """Get the contents of a coretemp file.
        
        Args:
            cpu_index (int): Index of the CPU core.
            value_type (str): Type of value to read (e.g. "value", "crit").
        
        Returns:
            int: This method returns the raw value contained in the file.
        """
        if self.__CORETEMP is None:
            return None
        
        file_name = self.__CORETEMP.format(_CORETEMP_CORE_OFFSET + cpu_index,
                                           value_type)
        try:
            with open(file_name, 'rt', encoding='utf-8', errors='replace') as f:
                raw_value = f.readline()
                match = _CORETEMP_REGEX_VALUE.match(raw_value)
                if match is not None:
                    int_value = int(match.group(1))
                    return int_value
                else:
                    return None
        except IOError as e:
            return None
    
    def getNumCPUCores(self):
        """Get number of CPU cores.
        
        Returns:
            int: The number of CPU cores.
        """
        try:
            with open(_CPUINFO_FILENAME, 'rt', encoding='utf-8', errors='replace') as f:
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
        tj_value = self.__readCoreTempValue(cpu_index,
                                            _CORETEMP_TYPE_JUNCTION_VALUE)
        if tj_value is None:
            return None
        return float(tj_value) / 1000.0
    
    def getCPUTemperatureDelta(self, cpu_index):
        """Get the junction temperature as delta to the maximum for a given CPU core.
        
        Args:
            cpu_index (int): Index of the CPU core.
        
        Returns:
            float: The temperature delta in degrees Celsius.
        """
        tj_crit_max = self.__readCoreTempValue(cpu_index,
                                               _CORETEMP_TYPE_JUNCTION_CRITICAL_MAX)
        tj_value = self.__readCoreTempValue(cpu_index,
                                            _CORETEMP_TYPE_JUNCTION_VALUE)
        if (tj_crit_max is None) or (tj_value is None):
            return None
        return float(tj_crit_max - tj_value) / 1000.0
    
    def getCPUTemperatureMax(self, cpu_index):
        """Get the maximum junction temperature for a given CPU core.
        
        Args:
            cpu_index (int): Index of the CPU core.
        
        Returns:
            float: The maximum junction temperature in degrees Celsius.
        """
        tj_max = self.__readCoreTempValue(cpu_index,
                                          _CORETEMP_TYPE_JUNCTION_MAX)
        if tj_max is None:
            return None
        return float(tj_max) / 1000.0
    
    def getCPUTemperatureCriticalMax(self, cpu_index):
        """Get the critical maximum junction temperature for a given CPU core.
        
        Args:
            cpu_index (int): Index of the CPU core.
        
        Returns:
            float: The critical maximum junction temperature in degrees Celsius.
        """
        tj_crit_max = self.__readCoreTempValue(cpu_index,
                                               _CORETEMP_TYPE_JUNCTION_CRITICAL_MAX)
        if tj_crit_max is None:
            return None
        return float(tj_crit_max) / 1000.0
    
    def getCPUTemperatureOutOfSpec(self, cpu_index):
        """Get the junction temperature out-of-spec flag for a given CPU core.
        
        Args:
            cpu_index (int): Index of the CPU core.
        
        Returns:
            bool: The temperature out-of-spec flag.
        """
        crit_alarm = self.__readCoreTempValue(cpu_index,
                                              _CORETEMP_TYPE_ALARM)
        if crit_alarm is None:
            return False
        return (crit_alarm != 0)
    
    def findMemoryTemperatureSensors(self):
        """Find SMBus devices for reading the memory temperature.
        
        Returns:
            list(tuple(int, int)): A list of SMBus devices and DIMM indices.
        """
        for device in os.listdir(_SMBUS_DEVICES_PATH):
            device_abs = os.path.join(_SMBUS_DEVICES_PATH, device)
            if not os.path.isdir(device_abs):
                continue
            
            match = _SMBUS_REGEX_DEVICENAME.match(device)
            if match is None:
                continue
            device_idx = int(match.group(1))
            dimm_idx = int(match.group(2), 16) & (~_SMBUS_MEMORY_SPD_EEPROM_ADDRESS)
            
            name_file = os.path.join(device_abs, _SMBUS_DEVICENAME_FILE)
            if not os.path.isfile(name_file):
                continue
            try:
                with open(name_file, 'rt', encoding='utf-8', errors='replace') as f:
                    raw_value = f.readline()
                    if _SMBUS_DEVICENAME_VALUE not in raw_value:
                        continue
            except IOError as e:
                continue
            
            eeprom_file = os.path.join(device_abs, _SMBUS_MEMORY_SPD_EEPROM_FILE)
            if not os.path.isfile(eeprom_file):
                continue
            try:
                with open(vendor_id_file, 'rb') as f:
                    f.seek(_SMBUS_MEMORY_SPD_EEPROM_REG_TEMPSENSOR)
                    ts_support = f.read(1)
                    if (ts_support & _SMBUS_MEMORY_SPD_EEPROM_FLAG_TEMPSENSOR) == 0:
                        return continue
            except IOError as e:
                continue
            
            yield (device_idx, dimm_idx)
    
    def getMemoryTemperature(self, i2c_index, dimm_index):
        """Get the temperature of the memory DIMM.
        
        Args:
            i2c_index (int): Index of the I2C bus master.
            dimm_index (int): Index of the memory bank and DIMM.

        Returns:
            float: The temperature of the memory DIMM.
        """
        sb = smbus.SMBus(i2c_index)
        if sb is not None:
            try:
                raw_value = sb.read_word_data(_SMBUS_MEMORY_SPD_TEMP_ADDRESS + dimm_index,
                                              _SMBUS_MEMORY_SPD_TEMP_REG_TEMPERATURE)
            except IOError as e:
                pass
            else:
                temperature = (((raw_value & 0x0FF00) >> 8) |
                               ((raw_value & 0x000FF) << 8))
                return float(temperature) / 16.0
            finally:
                try:
                    sb.close()
                except Exception:
                    pass
        return None
    
    def findHardDiskDrives(self):
        """Find internal hard disk drives with temperature information.
        
        Returns:
            list(str): The hard disk drive device file.
        """
        try:
            result = subprocess.check_output(_HDSMART_DISCOVERY_COMMAND,
                                             encoding='utf-8', errors='replace',
                                             stderr=subprocess.DEVNULL)
            for line in result.splitlines():
                match = _HDSMART_DISCOVERY_REGEX.match(line)
                if match is not None:
                    if _HDSMART_DISCOVERY_TYPE == match.group(2):
                        hdd = os.path.join("/dev", match.group(1))
                        if self.getHDTemperature(hdd) is not None:
                            yield hdd
        except CalledProcessError:
            pass
    
    def __getHDTemperature1(self, hdd):
        """Get the temperature of the hard disk drive through hddtemp.
        
        Args:
            hdd (str): The device file of the hard disk.
        
        Returns:
            float: The temperature of the hard disk drive.
        """
        try:
            result = subprocess.check_output(_HDSMART_COMMAND1_BASE + [hdd],
                                             encoding='utf-8', errors='replace',
                                             stderr=subprocess.DEVNULL)
            match = _HDSMART_REGEX_TEMPERATURE1.match(result)
            if match is not None:
                temperature = int(match.group(1))
                return float(temperature)
        except CalledProcessError:
            pass
        return None
    
    def __getHDTemperature2(self, hdd):
        """Get the temperature of the hard disk drive through smartctl.
        
        Args:
            hdd (str): The device file of the hard disk.
        
        Returns:
            float: The temperature of the hard disk drive.
        """
        try:
            result = subprocess.check_output(_HDSMART_COMMAND2_BASE + [hdd],
                                             encoding='utf-8', errors='replace',
                                             stderr=subprocess.DEVNULL)
            for line in result.splitlines():
                match = _HDSMART_REGEX_TEMPERATURE2.match(result)
                if match is not None:
                    temperature = int(match.group(1))
                    return float(temperature)
        except CalledProcessError:
            pass
        return None
    
    def getHDTemperature(self, hdd):
        """Get the temperature of the hard disk drive.
        
        Args:
            hdd (str): The device file of the hard disk.
        
        Returns:
            float: The temperature of the hard disk drive.
        """
        if self.__HDSMART_METHOD == 1:
            return self.__getHDTemperature1(hdd)
        elif self.__HDSMART_METHOD == 2:
            return self.__getHDTemperature2(hdd)
        else:
            self.__HDSMART_METHOD = 1
            temperature = self.__getHDTemperature1(hdd)
            if temperature is None:
                self.__HDSMART_METHOD = 2
                temperature = self.__getHDTemperature2(hdd)
            if temperature is None:
                self.__HDSMART_METHOD = None
            return temperature


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

