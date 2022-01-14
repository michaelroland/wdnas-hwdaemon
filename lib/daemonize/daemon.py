#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Abstract base classes for daemon processes.

Copyright (c) 2017-2019 Michael Roland <mi.roland@gmail.com>

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
import os
import os.path
import signal
import stat
import threading


_logger = logging.getLogger(__name__)


DAEMON_EXIT_SUCCESS = 0


class AbstractDaemon(object):
    """Abstract daemon handler.
    
    Attributes:
        is_running: Is daemon in running state?
    """
    
    def __init__(self):
        """Initializes a new daemon."""
        super().__init__()
        self.__lock = threading.RLock()
        self.__shutdown_condition = threading.Condition()
        self.__running = False
        self.__arg = None
        self.__cfg = None
        self.__exit_status = DAEMON_EXIT_SUCCESS
    
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
        with self.__shutdown_condition, self.__lock:
            self.__running = False
            self.__shutdown_condition.notify_all()
    
    def wait(self, timeout=None):
        with self.__shutdown_condition:
            try:
                self.__shutdown_condition.wait(timeout)
            except:
                pass
    
    def getArgument(self, name):
        """Get command line argument variable."""
        if self.__arg:
            return getattr(self.__arg, name, None)
        else:
            return None
    
    def getConfig(self, name):
        """Get configuration variable."""
        if self.__cfg:
            return getattr(self.__cfg, name, None)
        else:
            return None
    
    def setExitStatus(self, exist_status):
        """Set the exit status code."""
        with self.__lock:
            self.__exit_status = exist_status
    
    @property
    def exit_status(self):
        """int: Exit status code."""
        with self.__lock:
            return self.__exit_status

    @property
    def is_running(self):
        """bool: Is daemon in running state?"""
        with self.__lock:
            return self.__running

    @property
    def command_description(self):
        """str: Program description"""
        return ""
    
    @property
    def command_epilog(self):
        """str: Program description epilog"""
        return ""
    
    @property
    def command_version(self):
        """str: Program version information"""
        return ""
    
    @property
    def config_file_default(self):
        """str: Default configuration file name"""
        return None
    
    @property
    def config_file_class(self):
        """str: Configuration file class"""
        return None
    
    @property
    def log_file(self):
        """str: Log file name."""
        return self.getConfig('log_file')
    
    @property
    def log_spec(self):
        """tuple(int, dict): Log specification as tuple of global log level and
                            log levels per module."""
        return self.getConfig('logging')
    
    def prepareArgParse(self, cmdparser):
        """Implementations may customize command line argument parsing with this method.
        
        Args:
            cmdparser(argparse.ArgumentParser): Argument parser to customize.
        
        Returns:
            argparse.ArgumentParser: Customized argument parser.
        """
        return cmdparser
    
    def _createDir(self, path, uid=None, gid=None):
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
    
    def startup(self):
        """Implementations must override this method to implement daemon startup."""
        raise NotImplementedError("Abstract method not implemented")
    
    def cleanup(self):
        """Implementations may override this method to implement final daemon cleanup."""
        pass
    
    def main(self, argv):
        """Main entrypoint of the daemon.
        
        Args:
            argv (List(str)): List of command line arguments.
        
        Returns:
            int: Exit status code.
        """
        with self.__lock:
            self.__running = True
        
        cmdparser = argparse.ArgumentParser(
                description=self.command_description,
                epilog=self.command_epilog,
                formatter_class=argparse.RawDescriptionHelpFormatter)
        if self.config_file_class:
            cmdparser.add_argument(
                    '-C', '--config', action='store', nargs='?', metavar='CONFIG_FILE',
                    default=self.config_file_default,
                    help='configuration file (default: %(default)s)')
        cmdparser.add_argument(
                '-L', '--logging', action='store', nargs='?', metavar='LOG_SPEC',
                default=None,
                help='sets the global and per module logging levels')
        cmdparser.add_argument(
                '-v', '--verbose', action='count',
                default=0,
                help='sets the console logging verbosity level')
        cmdparser.add_argument(
                '-q', '--quiet', action='store_true',
                help='disables console logging output')
        cmdparser.add_argument(
                '-V', '--version', action='version',
                version=self.command_version,
                help='show version information and exit')
        cmdparser = self.prepareArgParse(cmdparser)
        self.__arg = cmdparser.parse_args(argv[1:])
        
        verbosity_level = logging.ERROR
        if self.getArgument('verbose') is not None:
            if self.getArgument('verbose') > 3:
                verbosity_level = logging.NOTSET
            elif self.getArgument('verbose') > 2:
                verbosity_level = logging.DEBUG
            elif self.getArgument('verbose') > 1:
                verbosity_level = logging.INFO
            elif self.getArgument('verbose') > 0:
                verbosity_level = logging.WARNING
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        rootlog = logging.getLogger("")
        rootlog.setLevel(verbosity_level)
        
        consolelog = None
        if not self.getArgument('quiet'):
            consolelog = logging.StreamHandler()
            consolelog.setLevel(verbosity_level)
            consolelog.setFormatter(formatter)
            rootlog.addHandler(consolelog)
        
        if self.getArgument('logging'):
            log_spec = AbstractConfigFile.parseLogSpec(self.getArgument('logging'))
            (global_log_level, module_log_levels) = log_spec
            for module_name, module_level in module_log_levels.items():
                logger = logging.getLogger(module_name)
                if logger:
                    logger.setLevel(module_level)
            if "" in module_log_levels or verbosity_level > global_log_level:
                verbosity_level = global_log_level
            if consolelog:
                consolelog.setLevel(verbosity_level)

        if self.config_file_class and self.getArgument('config'):
            _logger.debug("%s: Loading configuration file '%s'",
                          type(self).__name__,
                          self.getArgument('config'))
            cfg = self.config_file_class(self.getArgument('config'))
            self.__cfg = cfg
        
        if not self.getArgument('logging') and self.log_spec:
            (global_log_level, module_log_levels) = self.log_spec
            for module_name, module_level in module_log_levels.items():
                logger = logging.getLogger(module_name)
                if logger:
                    logger.setLevel(module_level)
            if "" in module_log_levels or verbosity_level > global_log_level:
                verbosity_level = global_log_level
            if consolelog:
                consolelog.setLevel(verbosity_level)
            
        if self.log_file:
            try:
                self._createDir(os.path.dirname(cfg.log_file))
            except OSError as e:
                serr = None
                try:
                    serr = os.strerror(e.errno)
                except Exception:
                    pass
                else:
                    _logger.error("%s: Failed to create log path '%s': %d (%s)",
                                  type(self).__name__,
                                  os.path.dirname(cfg.socket_path),
                                  e.errno, str(serr))
            filelog = logging.handlers.RotatingFileHandler(cfg.log_file, maxBytes=52428800, backupCount=3)
            filelog.setLevel(verbosity_level)
            filelog.setFormatter(formatter)
            rootlog.addHandler(filelog)
        
        try:
            _logger.debug("%s: Setting up signal handlers",
                          type(self).__name__)
            signal.signal(signal.SIGTERM, self.__sigHandler)
            signal.signal(signal.SIGINT,  self.__sigHandler)
            signal.signal(signal.SIGQUIT, self.__sigHandler)
            
            self.startup()
            
            if not self.is_running:
                return self.exit_status
            
            with self.__shutdown_condition:
                try:
                    self.__shutdown_condition.wait()
                except:
                    pass
            
            return self.exit_status
        
        except Exception as e:
            _logger.error("%s: Daemon failed with %s: %s; exiting",
                    type(self).__name__,
                    type(e).__name__, str(e))
            raise
        finally:
            self.cleanup()


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

