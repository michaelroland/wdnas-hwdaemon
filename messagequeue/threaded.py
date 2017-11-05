#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Message Queue based event processing across threads.

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


from Queue import Queue
import threading

from messagequeue import Message


class Handler(object):
    """A handler for posting and processing messages on a message queue thread.
    
    Attributes:
        is_running: Is the associated message queue thread in running state?
    """
    
    NEXT_MSG_ID = 0
    
    def __init__(self, daemonize=True):
        """Initializes a new message queue handler.
        
        Args:
            daemonize (bool): Should the associated thread be a daemon thread?
        """
        super(Handler, self).__init__()
        self.__lock = threading.RLock()
        self.__msg_queue = Queue()
        self.__running = False
        self.__handler_thread = None
        self.__daemonize = daemonize
    
    def prepareHandler(self):
        """Callback for preparations before message processing.
        
        This callback method that is invoked on the message queue thread when
        the handler was started, before processing the first message in the
        queue.
        """
        pass
        
    def cleanupHandler(self):
        """Callback for cleanup after message processing.
        
        This callback method that is invoked on the message queue thread when
        the handler is joined (stopped), right after processing the last
        message in the queue.
        """
        pass
    
    def handleMessage(self, msg):
        """Callback for processing a single message.
        
        This callback method that is invoked on the message queue thread to
        let the handler process one message from the queue.
        
        Args:
            msg (Message): The current ``Message`` to be processes.
        """
        pass
    
    def __run(self):
        """Runnable target of the message thread handler."""
        self.prepareHandler()
        try:
            while self.__running or not self.__msg_queue.empty():
                msg = self.__msg_queue.get()
                if msg is not None:
                    self.handleMessage(msg)
                self.__msg_queue.task_done()
        finally:
            self.cleanupHandler()
    
    def start(self):
        """Start the message handler thread.
        
        Raises:
            RuntimeError: When calling ``start()`` on a handler that is already
                running.
        """
        with self.__lock:
            if not self.__running:
                self.__handler_thread = threading.Thread(target=self.__run)
                self.__handler_thread.daemon = self.__daemonize
                self.__running = True
                self.__handler_thread.start()
            else:
                raise RuntimeError('start called when handler was already started')
    
    def join(self):
        """Join the message handler thread.
        
        This stops the message handler thread and waits for its completion.
        """
        with self.__lock:
            if self.__running:
                self.__running = False
                self.__msg_queue.join()
                self.__msg_queue.put(None)
                self.__handler_thread.join()
                self.__handler_thread = None
    
    @property
    def is_running(self):
        """bool: Is the associated message queue tread in running state?"""
        with self.__lock:
            return self.__running
    
    def sendMessage(self, msg):
        """Post a message to the end of the message queue.
        
        Args:
            msg (Message): The ``Message`` to be posted into the queue.
        
        Raises:
            RuntimeError: When the associated handler thread is not running.
        """
        with self.__lock:
            if not self.__running:
                raise RuntimeError('sendMessage called without a started handler')
            self.__msg_queue.put(msg)


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

