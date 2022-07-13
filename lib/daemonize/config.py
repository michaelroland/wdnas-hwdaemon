#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration file handling.

Copyright (c) 2017-2022 Michael Roland <mi.roland@gmail.com>

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

import configparser
import json
import logging


_logger = logging.getLogger(__name__)


class ConfigFileError(Exception):
    pass


class AbstractConfigFile(object):
    """Configuration holder.
    
    """
    
    def __init__(self, config_file):
        """Initializes a configuration holder.
        
        Args:
            config_file (str): The configuration file to load into this configuration
                holder.
        """
        super().__init__()
        self.__file = config_file
        self.__cfg = configparser.RawConfigParser()
        try:
            self.__file = self.__cfg.read(config_file)
            if len(self.__file) <= 0:
                _logger.error("%s: Configuration file '%s' not found",
                              type(self).__name__,
                              config_file)
                #raise ConfigFileError(f"Configuration file '{config_file}' not found")
        except ConfigFileError:
            raise
        except Exception as e:
            raise ConfigFileError(f"{type(e).__name__} while parsing configuration file '{config_file}'") from e
    
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
            raise ConfigFileError(f"Invalid value for option {option_name}"
                                  f" (in section {option_section} of {self.__file}):"
                                  f" {type(e).__name__}") from e
    
    @staticmethod
    def parseBoolean(value):
        value = value.lower()
        if value in ["1", "true", "yes", "y", "on"]:
            return True
        elif value in ["0", "false", "no", "n", "off"]:
            return False
        else:
            raise ValueError(f"'{value}' is not a valid boolean value")
    
    @staticmethod
    def parseInteger(value):
        return int(value)
    
    @staticmethod
    def parseLogLevel(value):
        value = value.strip().lower()
        if value.isnumeric():
            return int(value)
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
        elif value in ["all", "any", "a", "true"]:
            return logging.NOTSET
        elif value in ["none", "no", "n", "off", "false"]:
            return 2 * logging.CRITICAL
        else:
            raise ValueError(f"'{value}' is not a valid log level")
    
    @staticmethod
    def parseLogSpec(value):
        global_log_level = AbstractConfigFile.parseLogLevel("none")
        module_log_levels = {}
        for log_spec_entry in value.split(";"):
            log_target = ""
            log_level = "none"
            if ":" in log_spec_entry:
                (log_target, log_level) = log_spec_entry.split(":", 1)
                log_target = log_target.strip()
            else:
                log_level = log_spec_entry
            log_level = AbstractConfigFile.parseLogLevel(log_level)
            module_log_levels[log_target] = log_level
            if global_log_level > log_level:
                global_log_level = log_level
        if global_log_level == logging.NOTSET:
            global_log_level += 1
        return (global_log_level, module_log_levels)
    
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
            raise ValueError(f"'{value}' is not a valid array value") from e
    
    @staticmethod
    def parseJson(value):
        try:
            parsed_value = json.loads(value)
            return parsed_value
        except ValueError as e:
            raise ValueError(f"'{value}' is not a valid JSON value") from e


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

