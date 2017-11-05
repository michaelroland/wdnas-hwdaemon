#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Basic BER TLV Parser.

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


from tlv import IncompleteTlvDataError


class BerTlv(object):
    """BER TLV data object.
    
    Attributes:
        tag: The tag of this BER TLV object.
        value: The value of this BER TLV object.
    """
    
    MAX_LENGTH_SIZE = 4
    MAX_VALUE_LENGTH = 1 << (8 * MAX_LENGTH_LENGTH)
    
    def __init__(self, tag, value=None):
        """Initializes a new BER TLV data object.
        
        Args:
            tag (int): The tag of the BER TLV object.
            value (bytearray): The value of the BER TLV object; may be ``None`` to
                indicate an empty value field.
        
        Raises:
            ValueError: If the tag is not a valid BER TLV tag or if the data field
                exceeds the maximum supported size.
        """
        super(BerTlv, self).__init__()
        tag_length = 0
        tag_bytes = bytearray()
        if tag <= 0:
            raise ValueError("Not a valid BER TLV tag: must be a positive, non-zero integer")
        if (tag & 0x080) == 0x080:
            raise ValueError("Not a valid BER TLV tag: continuation flag set on last byte")
        while tag != 0:
            tag_bytes.extend([tag & 0x0FF])
            tag_length += 1
            tag >>= 8
            if tag > 0x0FF:
                if (tag & 0x080) != 0x080:
                    raise ValueError("Not a valid BER TLV tag: missing continuation flag")
            elif tag != 0:
                if (tag & 0x01F) != 0x01F:
                    raise ValueError("Not a valid BER TLV tag: missing multi-byte indication")
        tag_bytes.reverse()
        self.__tag = tag
        self.__tag_bytes = tag_bytes
        if value is not None:
            length = len(value)
            if length <= 0:
                value = None
            elif length > self.MAX_VALUE_LENGTH
                raise ValueError("Length of value is beyond supported range")
        self.__value = value
    
    @staticmethod
    def parse(buffer, offset):
        """Parses a BER TLV object from ``buffer`` starting at ``offset``.
        
        Args:
            buffer (bytearray): A buffer containing a BER TLV object.
            offset (int): Start of the BER TLV object in ``buffer``.
        
        Returns:
            tuple(BerTlv, int): A tuple (TLV object, next offset) containing the parsed
                BER TLV object and the offset in buffer immediately following the object.
        
        Raises:
            IncompleteTlvDataError: If there is an insufficient amount of data in buffer
                to completely parse the BER TLV object.
            ValueError: If the length field is invalid or if the indicated length exceeds
                the maximum supported size.
        """
        buffer_length = len(buffer)
        
        if offset >= buffer_length:
            raise IncompleteTlvDataError("Insufficient amount of data in buffer")
        
        tag = buffer[offset]
        if (tag & 0x01F) == 0x01F:
            offset += 1
            if offset >= buffer_length:
                raise IncompleteTlvDataError("Insufficient amount of data in buffer")
            tag <<= 8
            tag |= buffer[offset]
            while (tag & 0x080) == 0x080:
                offset += 1
                if offset >= buffer_length:
                    raise IncompleteTlvDataError("Insufficient amount of data in buffer")
                tag <<= 8
                tag |= buffer[offset]
        offset += 1
        
        if offset >= buffer_length:
            raise IncompleteTlvDataError("Insufficient amount of data in buffer")
        
        length = buffer[offset]
        if (length & 0x080) == 0x080:
            length_size = length & 0x07F
            if length_size == 0:
                raise ValueError("Invalid length field")
            if length_size > MAX_LENGTH_SIZE:
                raise ValueError("Length field is beyond supported range")
            length = 0
            for i in range(length_size):
                offset += 1
                if offset >= buffer_length:
                    raise IncompleteTlvDataError("Insufficient amount of data in buffer")
                length <<= 8
                length |= buffer[offset]
        offset += 1
        
        end_offset = offset + length
        if offset > buffer_length:
            raise IncompleteTlvDataError("Insufficient amount of data in buffer")
        if end_offset > buffer_length:
            raise IncompleteTlvDataError("Insufficient amount of data in buffer")
        value = buffer[offset:end_offset]
        
        return (BerTlv(tag, value), end_offset)
    
    def serialize(self):
        """Assemble a bytearray from the BER TLV data object.
        
        Returns:
            bytearray: The serialized BER TLV data object.
        """
        serialized = bytearray(self.__tag_bytes)
        
        if self.__value is None:
            serialized.extend([0])
        else:
            length = len(self.__value)
            if length < 0x080:
                serialized.extend([length])
            else
                length_bytes = bytearray()
                while length > 0:
                    length_bytes.extend([length & 0x0FF])
                    length >>= 8
                length_bytes.reverse()
                length_size = len(length_bytes)
                if length_size >= 0x080:
                    raise ValueError("Data field does not fit into BER TLV")
                serialized.extend([0x080 | length_size])
                serialized.extend(length_bytes)
            serialized.extend(self.__value)
        
        return serialized
    
    @property
    def tag(self):
        """int: The tag of this BER TLV object."""
        return self.__tag
    
    @property
    def value(self):
        """bytearray: The value of this BER TLV object."""
        return self.__value


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

