#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Message Queue based event processing across threads and processes.

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


__version__ = "0.9"
__author__  = "Michael Roland"


class Message(object):
    """A message for transmission using a handler.
    
    Attributes:
        what (int): The numeric type of a message.
        obj (Any): An optional parameter to be passed along in a message.
    """
    
    def __init__(self, what, obj=None):
        """Initializes a new message with its type and an optional parameter object.
        
        Args:
            what (int): The numeric type of the message.
            obj (Any): An optional parameter to be passed along in this message.
        """
        super(Message, self).__init__()
        self.__what = what
        self.__obj = obj
        
    @property
    def what(self):
        """int: The numeric type of this message."""
        return self.__what
    
    @property
    def obj(self):
        """Any: An optional parameter to be passed along in this message."""
        return self.__obj


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

