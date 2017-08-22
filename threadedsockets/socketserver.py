#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Thread-based Server-side Socket Interface.

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


from contextlib import contextmanager
import logging
import socket
from Queue import Queue
import threading

from threadedsockets import SocketConnectionBrokenError, SocketSecurityException


_logger = logging.getLogger(__name__)


class SocketServerThread(object):
    """Base class to send and receive binary data using a ``socket.SocketType``.
    
    Attributes:
        is_busy: Is the socket connection busy with an active connection?
        is_running: Is the socket connection handler thread in running state?
        thread_id: An identifier for the instance of the connection handler.
    """
    
    __NEXT_THREAD_ID = 0
    
    def __init__(self, listener):
        """Initializes a new socket server thread.
        
        Args:
            listener (SocketListener): The parent socket listener instance.
        """
        super(SocketServerThread, self).__init__()
        self.__thread_id = SocketServerThread.__NEXT_THREAD_ID
        SocketServerThread.__NEXT_THREAD_ID += 1
        self._BYTES_TO_READ = 4096
        self.__listener = listener
        self.__socket_lock = threading.RLock()
        self.__socket = None
        self.__lock = threading.RLock()
        self.__running = True
        self.__thread = threading.Thread(target=self.__run)
        self.__thread.daemon = True
        self.__thread.start()
    
    def connectionOpened(self, remote_address):
        """Callback invoked once a remote socket connection is opened and ready for transmission.
        
        The default implementation refuses all connections. Implementations must override
        this method to allow incoming connections.
        
        Args:
            remote_address (Any): The remote socket address (the exact type depends on
                the address family).
        
        Raises:
            SocketSecurityException: May raise a ``SocketSecurityException`` to refuse an
                incoming connection.
        """
        raise SocketSecurityException("The default implementation refuses all connections.")
    
    def connectionClosed(self, error):
        """Callback invoked when the remote socket connection is closed.
        
        Args:
            error (Exception): If not ``None``, the communication ended due to this
                ``Exception``.
        """
        pass
    
    def dataReceived(self, data):
        """Callback for processing incoming data from the remote socket connection.
        
        This callback is invoked on the connection handler thread of ``SocketServerThread``.
        Implementations must make sure that this thread is not extensively blocked due to
        further processing of incoming data.
        
        Args:
            data (bytearray): A byte array of received data.
        """
        pass
    
    def sendData(self, data):
        """Send data over the remote socket connection.
        
        Args:
            data (bytearray): A byte array of data to send.
        
        Raises:
            socket.error: If sending failed.
            SocketConnectionBrokenError: If sending failed and the send method did not
                raise an exception.
        """
        with self.__socket_lock:
            if self.__socket:
                bytes_to_send = len(data)
                offset = 0
                while offset < bytes_to_send:
                    bytes_sent = self.__socket.send(data[offset:])
                    if bytes_sent > 0:
                        offset += bytes_sent
                    else:
                        # no data received: connection broken?
                        raise SocketConnectionBrokenError("socket.send() returned {0}".format(bytes_sent))
    
    def __run(self):
        """Runnable target of the server-side socket connection handler thread."""
        while self.__running:
            _logger.debug("%s(%d): Ready to process incoming connections...",
                          type(self).__name__,
                          self.__thread_id)
            with self.__listener.getNextConnection() as connection
                if connection is not None:
                    (remote_socket, remote_address) = connection
                    _logger.debug("%s(%d): Accepting incoming connection from '%s'",
                                  type(self).__name__,
                                  self.__thread_id,
                                  repr(remote_address))
                    with self.__socket_lock:
                        self.__socket = remote_socket
                    
                    error = None
                    try:
                        self.connectionOpened(remote_socket, remote_address)
                        _logger.debug("%s(%d): Starting server task",
                                      type(self).__name__,
                                      self.__thread_id)
                        while self.__running:
                            data = remote_socket.recv(self._BYTES_TO_READ)
                            if data:
                                self.dataReceived(data)
                            else:
                                # no data received: connection broken?
                                raise SocketConnectionBrokenError("socket.recv() returned {0}".format(data))
                    except Exception as e:
                        error = e
                    
                    with self.__socket_lock:
                        _logger.debug("%s(%d): Closing connection to '%s'",
                                      type(self).__name__,
                                      self.__thread_id,
                                      repr(remote_address))
                        self._closeSocket()
                        self.__socket = None
                    
                    self.connectionClosed(error)
    
    def close(self):
        """Close the server-side socket connection handler.
        
        This method blocks until cleanup completed.
        """
        with self.__lock:
            if self.__running:
                self.__running = False
                self._closeSocket()
                self.__thread.join()
    
    def _closeSocket(self):
        """Close the current client connection socket."""
        with self.__socket_lock:
            if self.__socket:
                try:
                    self.__socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                self.__socket.close()
    
    @property
    def _socket(self):
        """socket.SocketType: The current remote socket endpoint."""
        with self.__socket_lock:
            return self.__socket
    
    @property
    def is_busy(self):
        """bool: Is the socket connection busy with an active connection?"""
        with self.__socket_lock:
            if self.__socket:
                return True
            else
                return False
    
    @property
    def is_running(self):
        """bool: Is the socket connection handler thread in running state?"""
        with self.__lock:
            return self.__running
    
    @property
    def thread_id(self):
        """int: An identifier for the instance of the connection handler."""
        return self.__thread_id


class SocketListener(object):
    """A server socket listener that spawns new threads for incoming connections.
    
    Attributes:
        is_running: Is the server-side socket handler thread in running state?
    """

    def __init__(self, server_socket, max_clients=10, server_thread_class=SocketServerThread):
        """Initializes a new server socket listener.
        
        Args:
            server_socket (socket.SocketType): A bound server socket.
            max_clients (int): Maximum number of concurrent clients.
            server_thread_class (Type[SocketServerThread]): A class implementing
                ``SocketServerThread``.
        """
        super(SocketListener, self).__init__()
        if not issubclass(server_thread_class, SocketServerThread):
            raise TypeError("'server_thread_class' is not a subclass of SocketServerThread")
        self.__server_thread_class = server_thread_class
        self.__lock = threading.RLock()
        self.__running = True
        self.__socket_lock = threading.RLock()
        self.__socket = server_socket
        self.__connection_queue = Queue(max_clients)
        self.__connection_thread_pool = []
        for i in range(0, max_clients):
            self.__connection_thread_pool.append(_spawnServerThread())
        self.__listener_thread = threading.Thread(target=self.__runListener)
        self.__listener_thread.daemon = False
        self.__listener_thread.start()
    
    def _spawnServerThread(self):
        """Method invoked to create a new server thread instance for handling incoming connections.
        
        Returns:
            SocketServerThread: A new socket connection handler thread object.
        """
        return self.__server_thread_class(self)
    
    def __runListener(self):
        """Runnable target of the listening server thread."""
        self.__socket.listen(1)
        
        try:
            while self.__running:
                _logger.debug("%s: Listener thread ready to accept incoming connections...",
                              type(self).__name__)
                connection = self.__socket.accept()
                if self.__running:
                    self.__connection_queue.put(connection)
        except:
            pass
        
        self.__running = False
        with self.__socket_lock:
            self.__closeSocket()
            self.__socket = None
        self.__connection_queue.join()
        # feed the queue with dummy tasks to gracefully end all threads in the pool
        for i in self.__connection_thread_pool:
            self.__connection_queue.put(None)
        # wait for all threads in the pool to consume a dummy task (if necessary) and end
        for i in self.__connection_thread_pool:
            i.close()
    
    def close(self):
        """Close the server-side socket connection handler.
        
        This method blocks until cleanup completed.
        """
        with self.__lock:
            if self.__running:
                self.__running = False
                self.__closeSocket()
                self.__listener_thread.join()
    
    def __closeSocket(self):
        """Close the server-side socket."""
        with self.__socket_lock:
            if self.__socket:
                try:
                    self.__socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                self.__socket.close()
    
    @contextmanager
    def getNextConnection(self):
        """Context manager for getting the next waiting incoming connection from a client.
        
        This method blocks until an incoming connection is available.
        
        Returns:
            contextmanager: A context manager yielding a ``tuple(socket.SocketType, Any)``
                containing the remote socket and the endpoint address or ``None``.
        """
        try:
            yield self.__connection_queue.get()
        finally:
            self.__connection_queue.task_done()
    
    @property
    def is_running(self):
        """bool: Is the server-side socket handler thread in running state?"""
        with self.__lock:
            return self.__running


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

