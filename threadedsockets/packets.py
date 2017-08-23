#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Simple Network Packet Protocol.

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


class IncompletePacketError(Exception):
    """Exception class for indicating parser errors caused by incomplete data in the buffer.
    """
    pass


class InvalidPacketError(Exception):
    """Exception class for indicating parser errors caused by invalid data in the buffer.
    """
    pass


class BasicPacket(object):
    """A basic serializable command/response protocol packet.
    
    Attributes:
        identifer: The identifier of the packet.
        parameter: The parameter value of the packet.
        flags: The flags of the packet.
    """
    
    PACKET_MAGIC_BYTE = 0x0FF
    FLAGS_FIELD_SIZE = 1
    IDENTIFIER_FIELD_SIZE = 2
    LENGTH_FIELD_SIZE = 2
    MAX_PARAMETER_FIELD_SIZE = 1 << (8 * LENGTH_FIELD_SIZE)
    CHECKSUM_FIELD_SIZE = 1
    
    def __init__(self, identifier, parameter=None, flags=0):
        """Initializes a new protocol packet.
        
        Args:
            identifer (int): The identifier of the packet.
            parameter (bytearray): The optional parameter value of the packet; may be
                ``None`` to indicate an empty parameter field.
            flags (int): The optional flags of the packet.
        
        Raises:
            InvalidPacketError: If the parameter is too large to fit into the packet.
        """
        super(BasicPacket, self).__init__()
        self.__identifier = identifier
        if parameter is not None:
            length = len(parameter)
            if length <= 0:
                parameter = None
            elif length > self.MAX_PARAMETER_FIELD_SIZE
                raise InvalidPacketError("Parameter length is above supported maximum length")
        self.__parameter = parameter
        self.__flags = flags
    
    @classmethod
    def parse(clazz, buffer, offset):
        """Parses a protocol packet object from ``buffer`` starting at ``offset``.
        
        Args:
            buffer (bytearray): A buffer containing a protocol packet object.
            offset (int): Start of the protocol packet object in ``buffer``.
        
        Returns:
            tuple(BasicPacket, int): A tuple (protocol packet, next offset)
                containing the parsed command packet object and the offset in buffer
                immediately following the object.
        
        Raises:
            IncompletePacketError: If there is an insufficient amount of data in buffer
                to completely parse the protocol packet.
            InvalidPacketError: If the buffer does not contain a valid protocol packet.
        """
        buffer_length = len(buffer)
        
        if offset >= buffer_length:
            raise IncompletePacketError("Insufficient amount of data in buffer")
        
        magic = buffer[offset]
        if magic != clazz.PACKET_MAGIC_BYTE:
            raise InvalidPacketError("Packet does not start with magic byte")
        
        packet_begin = offset
        
        flags = 0
        flags_size = clazz.FLAGS_FIELD_SIZE
        while flags_size > 0:
            offset += 1
            if offset >= buffer_length:
                raise IncompletePacketError("Insufficient amount of data in buffer")
            flags <<= 8
            flags |= buffer[offset]
            flags_size -= 1
        
        identifier = 0
        identifier_size = clazz.IDENTIFIER_FIELD_SIZE
        while identifier_size > 0:
            offset += 1
            if offset >= buffer_length:
                raise IncompletePacketError("Insufficient amount of data in buffer")
            identifier <<= 8
            identifier |= buffer[offset]
            identifier_size -= 1
        
        length = 0
        length_size = clazz.LENGTH_FIELD_SIZE
        while length_size > 0:
            offset += 1
            if offset >= buffer_length:
                raise IncompletePacketError("Insufficient amount of data in buffer")
            length <<= 8
            length |= buffer[offset]
            length_size -= 1
        
        offset += 1
        param_end = offset + length
        if length > clazz.MAX_PARAMETER_FIELD_SIZE:
            raise InvalidPacketError("Indicated packet length is above supported maximum length")
        if offset > buffer_length:
            raise IncompletePacketError("Insufficient amount of data in buffer")
        if param_end > buffer_length:
            raise IncompletePacketError("Insufficient amount of data in buffer")
        param = buffer[offset:param_end]
        
        packet_end = param_end + clazz.CHECKSUM_FIELD_SIZE
        if packet_end > buffer_length:
            raise IncompletePacketError("Insufficient amount of data in buffer")
        if not clazz.verifyChecksum(buffer, packet_begin, packet_end):
            raise InvalidPacketError("Checksum mismatch")
        
        return (clazz(identifier, parameter=param, flags=flags), end_offset)
    
    @classmethod
    def fillChecksum(clazz, buffer, offset_begin, offset_end):
        """Calculates and inserts the ckechsum into the packet given in buffer.
        
        Args:
            buffer (bytearray): Buffer containing a serialized protocol packet.
            offset_begin (int): Offset in ``buffer`` where the serialized protocol
                packet begins.
            offset_end (int): Offset in ``buffer`` immediately following the serialized
                protocol packet.
        
        Raises:
            InvalidPacketError: If the buffer is too small to hold the checksum.
            ValueError: If the checksum type is not supported.
        """
        if clazz.CHECKSUM_FIELD_SIZE == 0:
            return
        elif clazz.CHECKSUM_FIELD_SIZE != 1:
            raise ValueError("This implementation supports only a single-byte XOR checksum")
        
        offset_checksum = offset_end - 1
        if offset_begin > offset_checksum:
            raise InvalidPacketError("Not enough space for checksum")
        
        checksum = 0
        while offset_begin < offset_checksum:
            checksum ^= buffer[offset_begin]
            offset_begin += 1
        
        buffer[offset_checksum] = checksum & 0x0FF
    
    @classmethod
    def verifyChecksum(clazz, buffer, offset_begin, offset_end):
        """Verifies the checksum over the packet given in buffer.
        
        Args:
            buffer (bytearray): Buffer containing a serialized protocol packet.
            offset_begin (int): Offset in ``buffer`` where the serialized protocol
                packet begins.
            offset_end (int): Offset in ``buffer`` immediately following the serialized
                protocol packet.
        
        Returns:
            bool: ``True`` if verification succeedes, else ``False``.
        
        Raises:
            InvalidPacketError: If the buffer does not contain sufficient bytes for the
                checksum.
            ValueError: If the checksum type is not supported.
        """
        if clazz.CHECKSUM_FIELD_SIZE == 0:
            return True
        elif clazz.CHECKSUM_FIELD_SIZE != 1:
            raise ValueError("This implementation supports only a single-byte XOR checksum")
        
        if offset_begin >= offset_end:
            raise InvalidPacketError("Checksum missing")
        
        checksum = 0
        while offset_begin < offset_end:
            checksum ^= buffer[offset_begin]
            offset_begin += 1
        
        return (checksum & 0x0FF) == 0
    
    def serialize(self):
        """Assemble a bytearray from the protocol packet object.
        
        Returns:
            bytearray: The serialized protocol packet object.
        
        Raises:
            InvalidPacketError: If the parameter is too large to fit into the packet.
        """
        length = 0
        if self.__parameter is not None:
            length = len(self.__parameter)
        if length > self.MAX_PARAMETER_FIELD_SIZE:
            raise InvalidPacketError("Indicated packet length is above allowed maximum length")
        
        packet_size = 1 +
                      self.FLAGS_FIELD_SIZE +
                      self.IDENTIFIER_FIELD_SIZE +
                      self.LENGTH_FIELD_SIZE +
                      length +
                      self.CHECKSUM_FIELD_SIZE
        serialized = bytearray(packet_size)
        
        offset = 0
        serialized[offset] = self.PACKET_MAGIC_BYTE
        
        flags = self.__flags
        end_offset = offset + self.FLAGS_FIELD_SIZE
        for i in range(end_offset, offset, -1):
            serialized[i] = flags & 0x0FF
            flags >>= 8
        offset = end_offset
        
        identifier = self.__identifier
        end_offset = offset + self.IDENTIFIER_FIELD_SIZE
        for i in range(end_offset, offset, -1):
            serialized[i] = identifier & 0x0FF
            identifier >>= 8
        offset = end_offset
        
        length_field = length
        end_offset = offset + self.LENGTH_FIELD_SIZE
        for i in range(end_offset, offset, -1):
            serialized[i] = length_field & 0x0FF
            length_field >>= 8
        offset = end_offset
        
        offset += 1
        if length > 0:
            end_offset = offset + length
            serialized[offset:end_offset] = self.__parameter
            offset = end_offset
        
        offset += self.CHECKSUM_FIELD_SIZE
        self.fillChecksum(serialized, 0, offset)
        
        return serialized
    
    @property
    def identifier(self):
        """int: The identifier of this packet."""
        return self.__identifier
    
    @property
    def parameter(self):
        """bytearray: The parameter value of this packet."""
        return self.__parameter
    
    @property
    def flags(self):
        """int: The flags of this packet."""
        return self.__flags


if __name__ == "__main__":
    import sys
    sys.exit("This library is not intended to be run directly. Unit tests are not implemented.")

