#!/usr/bin/env python3

"""
ParseNVRAM: a tool for extracting information from PinMAME's ".nv" files.
This program makes use of content from the PinMAME NVRAM Maps project.

Copyright (C) 2015-2025 by Tom Collins <tom@tomlogic.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import argparse
import json
import os

from curses.ascii import isprint
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional, Tuple, Union

MAPS_ROOT = os.path.join(os.path.dirname(__file__), 'maps')
HEX_DUMP_BYTES_PER_LINE = 16

class Nibble(Enum):
    BOTH = 0
    LOW = 1
    HIGH = 2


def get_nibble(value: Optional[str]) -> Nibble:
    if value is None or value == 'both':
        return Nibble.BOTH
    elif value == 'low':
        return Nibble.LOW
    elif value == 'high':
        return Nibble.HIGH
    else:
        raise ValueError("invalid `nibble` value")


def to_int(v: Union[int, str]) -> int:
    """Returns 'v' if already an int, otherwise assume a string and convert
    with a base of '0' (which handles leading 0 as octal and 0x as hex).
    """
    if type(v) is int:
        return v
    return int(v, 0)


def format_number(number: int) -> str:
    """
    Format large numbers with thousands separators based on the locale setting
    (i.e., ',' or '.').
    """
    return '{0:,}'.format(number)


def rom_name(rom: str) -> str:
    """Return the descriptive ROM name for a given ROM (e.g., fh_l9)."""
    with open(os.path.join(MAPS_ROOT, 'romnames.json')) as f:
        return json.load(f).get(rom, '(Unknown ROM %s)' % rom)


def map_for_rom(rom: str) -> Optional[str]:
    """Return full path to the mapfile for a given rom, or None if it isn't supported."""
    with open(os.path.join(MAPS_ROOT, 'index.json')) as f:
        map_file = json.load(f).get(rom)
        if map_file:
            return os.path.join(MAPS_ROOT, map_file)

    return None


def rom_for_nvpath(nvpath: str) -> str:
    """
    Return the ROM name (e.g., fh_l9) from a full path to a .nv file.  Strips
    off the leading path, file extension, and optional "-[suffix]" of what remains.
    :param nvpath: Pathname ending in a file that starts with a ROM name.
    :return: Bare ROM name.
    """
    (name, extension) = os.path.splitext(os.path.basename(nvpath))
    # remove anything after the first hyphen
    (rom, _, _) = name.partition('-')
    return rom


def find_map(nvpath: str) -> Optional[str]:
    """
    Find a map that will work with the ROM of the given nvram file.
    :param nvpath: Full pathname of a .nv file.
    :return: Path of .nv.json file or None if nothing matches <nvpath>.
    """
    return map_for_rom(rom_for_nvpath(nvpath))


def dipsw_get(nvram: bytes, index: int) -> bool:
    """
    Return state of a game's DIP switch.

    :param nvram: contents of .nv file
    :param index: DIP switch number (1 to n)
    :return: True if DIP switch is configured as "ON"
    """
    index -= 1  # switches start at 1 in file, 0 in memory
    bank = index // 8
    mask = 1 << (index % 8)
    # dip switches are last 6 bytes of file
    byte_value = nvram[-6 + bank]
    return (byte_value & mask) != 0


def dipsw_set(nvram: bytes, index: int, state: bool) -> None:
    """
    Set the state of a game's DIP switch.
    :param nvram: contents of .nv file
    :param index: DIP switch number (1 to n)
    :param state: True to set the switch to ON, False to set it to OFF.
    :return:
    """
    index -= 1  # switches start at 1 in file, 0 in memory
    bank = index // 8
    mask = 1 << (index % 8)
    # dip switches are last 6 bytes of file
    if state:
        nvram[-6 + bank] |= mask
    else:
        nvram[-6 + bank] &= ~mask


class SparseMemory(object):
    """
    Object representing memory contents for a portion of the full address space.
    """
    def __init__(self):
        self.pinmame_data = None
        self.memory = []

    def find_region(self, address: int) -> Optional[dict]:
        for region in self.memory:
            region_base = region['base_address']
            region_size = len(region['data'])
            if region_base <= address < region_base + region_size:
                return region
        return None

    def update_memory(self, address: int, data: Union[bytearray, list]) -> None:
        if type(data) is list:
            data = bytearray(data)
        region = self.find_region(address)
        if region:
            # updating an existing region
            region_base = region['base_address']
            region_size = len(region['data'])
            offset = address - region_base
            data_size = len(data)
            if address + data_size > region_base + region_size:
                raise ValueError('Update of %u bytes to 0x%X overflows region' % (data_size, address))
            region['data'][offset:offset + data_size] = data
        else:
            # new memory region
            self.memory.append({
                'base_address': address,
                'data': data
            })

    def get_byte(self, address: int) -> Optional[int]:
        """
        Return the byte at a given memory location, or None if it isn't represented.
        :param address: address for lookup
        :return: value of byte at address or None
        """
        for region in self.memory:
            region_base = region['base_address']
            region_size = len(region['data'])
            if region_base <= address < region_base + region_size:
                return region['data'][address - region_base]
        return None

    def set_pinmame_data(self, data: bytearray = None):
        self.pinmame_data = data

    def get_pinmame_data(self) -> Optional[bytearray]:
        return self.pinmame_data


class ChecksumMapping(object):
    """Simplified RamMapping object used for checksum values."""
    def __init__(self, start: int, end: int, label: str, checksum16: bool,
                 big_endian: bool):
        self.start = start
        self.end = end
        self.label = label
        self.big_endian = big_endian
        self.checksum16 = checksum16

    def offsets(self) -> List[int]:
        if self.checksum16:
            return [self.end - 1, self.end]
        return [self.end]

    def format_mapping(self, memory: SparseMemory) -> Tuple[str, str]:
        """Return a tuple of (label, value) for this entry for the given nvram data."""
        checksum = memory.get_byte(self.end)
        if self.checksum16:
            if self.big_endian:
                checksum += memory.get_byte(self.end - 1) << 8
            else:
                checksum = (checksum << 8) + memory.get_byte(self.end - 1)
            label = 'checksum16[%X:%X]' % (self.start, self.end - 1)
            value = '0x%04X' % checksum
        else:
            label = 'checksum8[%X:%X]' % (self.start, self.end)
            value = '0x%02X' % checksum

        if self.label:
            value += ' (%s)' % self.label
        return label, value


class RamMapping(object):
    """Object representing a single entry from a nvram mapping file."""
    def __init__(self,
                 entry: dict,
                 metadata: dict,
                 section: str = None,
                 group: str = None,
                 key: str = None):
        """
        :param entry: A dictionary, typically from a JSON file.
        :param metadata: Metadata from the ParseNVRAM object.
        :param section: Section of the file (e.g., 'audits', 'adjustments', 'game_state').
        :param group: Subgroup of the given section (e.g., 'Standard Audits').
        :param key: Key to use when sorting groups of a given section (e.g., '01', '02').
        """
        self.entry = entry
        self.metadata = metadata
        self.section = section
        self.group = group
        self.key = key
        self.sub_entry = {}
        for sub in ['initials', 'score', 'timestamp']:
            if sub in entry:
                self.sub_entry[sub] = RamMapping(entry[sub], metadata)

    def nvram_base_address(self) -> int:
        """
        Walk the memory_layout from metadata['platform'] to find the first
        nvram memory area and return its base address.
        :return: base address for NVRAM on this map's platform
        """
        for region in self.metadata['platform']['memory_layout']:
            if region['type'] == 'nvram':
                return region['address']
        return 0

    def offsets(self) -> List[int]:
        """Return a list of byte offsets based on the start/end/length/offsets attributes."""
        if self.sub_entry:
            # special-case handling for high score or other combined records
            o = []
            for key, sub in self.sub_entry.items():
                o += sub.offsets()
            return o

        if 'offsets' in self.entry:
            return list(map((lambda offset: to_int(offset)),
                            self.entry['offsets']))

        start = to_int(self.entry.get('start', 0))
        end = start
        if 'length' in self.entry:
            length = to_int(self.entry['length'])
            if length <= 0:
                raise AssertionError('invalid length (%s); must be > 0'
                                     % (self.entry['length']))
            end = start + length - 1
        elif 'end' in self.entry:
            end = to_int(self.entry['end'])
            if end < start:
                raise AssertionError('end (%s) is less than start (%s)'
                                     % (self.entry['end'], self.entry['start']))

        return list(range(start, end + 1))

    def get_bytes_unmasked(self, memory: SparseMemory) -> Optional[bytearray]:
        """
        Return the bytes from memory for a given RamMapping.

        :param memory: source of bytes
        :return: Returns None if <memory> doesn't include the byte range.
        Otherwise:
            - 'start' to 'end' bytes (inclusive), or
            - 'start' to 'start + length - 1' bytes (inclusive)
            - the single byte at 'start' if 'end' and 'length' are not specified
            - bytes from offsets in a list called 'offsets'
        """
        result = bytearray()
        for offset in self.offsets():
            byte = memory.get_byte(offset)
            if byte is None:
                return None
            result.append(byte)

        return result

    def get_bytes(self, memory: SparseMemory) -> Optional[bytearray]:
        """Same as get_bytes_unmasked() but:

        - reverses little-endian sequences for integer encodings (bcd, int, bits)
        - combines nibbles into complete bytes
        - if appropriate, applies a mask to each byte
        """
        encoding = self.entry.get('encoding')
        
        # special case handling for dip switches
        if encoding == 'dipsw':
            value = 0
            pinmame_data = memory.get_pinmame_data()
            if not pinmame_data:
                # didn't load from a PinMAME .nv file
                return None
            for bit in self.offsets():
                # shift current value one bit left and set LSB
                value = (value << 1) + dipsw_get(pinmame_data, bit)
            # might need to split into multiple list entries if value > 255
            return bytearray([value])
            
        ba = self.get_bytes_unmasked(memory)
        if ba is None:
            return None

        # convert certain byte sequences from little_endian to big endian
        if self.little_endian() and encoding in ['bcd', 'int', 'bits']:
            ba.reverse()

        # find the nibble setting for the first address of this entry
        nibble = self.nibble()
        if nibble != Nibble.BOTH:
            # combine nibbles of ba
            new_ba = bytearray()
            value = 0
            while ba:
                b = ba.pop(0)
                if nibble == Nibble.LOW:
                    b = b & 0x0F
                else:
                    b = b >> 4
                value = (value << 4) + b
                if len(ba) % 2 == 0:
                    # if remaining byte count is even, save new value
                    new_ba.append(value)
                    value = 0
            ba = new_ba

        if 'mask' in self.entry:
            mask = to_int(self.entry['mask'])
            ba = bytearray(map((lambda x: x & mask), ba))

        return ba

    @staticmethod
    def bcd(value: int) -> int:
        """Returns valid BCD value for a nibble, converting 0xA to 0xF to 0.

        Multiple machines display a space for 0xF, but this routine doesn't support that.
        """
        return 0 if value > 9 else value

    def nibble(self) -> Nibble:
        """Return Nibble.BOTH, Nibble.LOW, or Nibble.HIGH based on `nibble`
        attribute or the deprecated `packed` attribute.
        """
        if not self.entry.get('packed', True):
            # if entry has 'packed=false', replace file's default with 'nibble=low'
            return Nibble.LOW

        entry_nibble = self.entry.get('nibble')
        if entry_nibble:
            return get_nibble(entry_nibble)

        # use the memory region's `nibble` setting
        address = self.offsets()[0]
        for region in self.metadata['platform']['memory_layout']:
            region_start = region['address']
            region_end = region_start + region['size'] - 1
            if region_start <= address <= region_end:
                return region['nibble']

        # fall back on Nibble.BOTH
        return Nibble.BOTH

    def little_endian(self) -> bool:
        """Return True if this entry is little endian (LSB first)."""
        default = 'big' if self.metadata['big_endian'] else 'little'
        return self.entry.get('endian', default) == 'little'

    def get_value(self, memory: SparseMemory) -> Optional[int]:
        """Return the integer value for this entry using the provided nvram data.

        Handles multibyte integers (int), binary coded decimal (bcd) and
        single-byte enumerated (enum) values.  Returns None for unsupported
        encodings or mappings that aren't covered by <memory>.
        """
        value = None
        if 'encoding' in self.entry:
            encoding = self.entry['encoding']
            ba = self.get_bytes(memory)
            if ba is None:
                return None

            if encoding == 'bcd':
                value = 0
                for b in ba:
                    value = value * 100 + self.bcd(b >> 4) * 10 + self.bcd(b & 0x0F)
            elif encoding in ['int', 'bits', 'dipsw']:
                value = 0
                for b in ba:
                    value = value * 256 + b
            elif encoding == 'enum':
                value = ba[0]

            if value is not None:
                scale = self.entry.get('scale', 1)
                if type(scale) is float:
                    value *= scale
                else:
                    value *= to_int(scale)
                value += to_int(self.entry.get('offset', 0))

        return value

    def set_value(self, memory: SparseMemory,
                  value: Union[int, str, datetime]) -> None:
        """
        Undocumented and incomplete method to replace the entry's value stored in
        `nvram`.  Currently only works for sequential memory ranges.

        :param memory: SparseMemory object with contents of nvram
        :param value: replacement value with the appropriate type based on encoding:
            dipsw, bcd, int, enum: int
            ch: str
            wpc_rtc: datetime
        :return: None
        """
        encoding = self.entry['encoding']

        if encoding == 'dipsw':
            assert type(value) is int
            pinmame_data = memory.get_pinmame_data()
            if pinmame_data:
                # use reversed() to start with LSB in list of offsets
                for bit in reversed(self.offsets()):
                    dipsw_set(pinmame_data, bit, bool(value & 1))
                    value >>= 1
            return

        old_bytes = self.get_bytes(memory)
        if old_bytes is None:
            return

        start = to_int(self.entry['start'])
        # can now replace nvram[start:(start + len(old_bytes)]
        new_bytes = []

        # TODO: update to use char_map if present
        if encoding == 'ch':
            assert type(value) is str and len(value) == len(old_bytes)
            new_bytes = list(value)
        elif encoding == 'wpc_rtc':
            assert type(value) is datetime
            # for day of week 1=Sunday, 7=Saturday
            # isoweekday() returns 1=Monday 7=Sunday
            new_bytes = [value.year // 256, value.year % 256,
                         value.month, value.day, value.isoweekday() % 7 + 1,
                         value.hour, value.minute]
        elif encoding in ['bcd', 'int', 'enum']:
            # all formats where byte order applies
            if encoding == 'bcd':
                for _ in old_bytes:
                    b = value % 100
                    new_bytes.append(b % 10 + 16 * (b // 10))
                    value //= 100
            else:
                for _ in old_bytes:
                    b = value % 256
                    new_bytes.append(b)
                    value //= 256

            if not self.little_endian():
                new_bytes = reversed(new_bytes)
        else:
            raise ValueError('Unsupported encoding %s' % encoding)

        memory.update_memory(start, bytearray(new_bytes))

    def format_value(self, value: int) -> Optional[str]:
        """Format a multibyte integer using options in 'entry'."""

        if value is None:
            return None

        # `special_values` contains strings to use in place of `value`
        # commonly used at the low end of a range for off/disabled
        if 'special_values' in self.entry and str(value) in self.entry['special_values']:
            return self.entry['special_values'][str(value)]

        units = self.entry.get('units')
        if units == 'seconds':
            m, s = divmod(value, 60)
            h, m = divmod(m, 60)
            return "%d:%02d:%02d" % (h, m, s)
        elif units == 'minutes':
            return "%d:%02d:00" % divmod(value, 60)
        return format_number(value) + self.entry.get('suffix', '')

    def entry_values(self) -> List[str]:
        """Return a list of values for an entry with enum or dipsw encoding."""
        if self.entry['encoding'] not in ['enum', 'dipsw']:
            raise ValueError("Entry doesn't use enum/dipsw encoding.")
        values = self.entry['values']
        if isinstance(values, str):
            # look up a shared list of values
            values = self.metadata['values'].get(values, [])
        return values

    def format_entry(self, memory: SparseMemory) -> Optional[str]:
        """Format bytes from 'memory' for this entry."""
        if self.entry is None:
            return None
        if 'initials' in self.sub_entry or 'score' in self.sub_entry:
            return self.format_high_score(memory)
        if 'encoding' not in self.entry:
            return None

        ba = self.get_bytes(memory)
        if ba is None:
            return None

        encoding = self.entry['encoding']
        value = self.get_value(memory)
        if encoding in ['bcd', 'int']:
            return self.format_value(value)
        elif encoding == 'bits':
            values = self.entry.get('values', [])
            if values is None:
                return '0'
            if type(values[0]) is int:
                mask = 1
                bits_value = 0
                for b in values:
                    if value & mask:
                        bits_value += b
                    mask <<= 1
                return self.format_value(bits_value)
            elif type(values[0]) is str:
                mask = 1
                set_values = []
                for b in values:
                    if value & mask:
                        set_values.append(b)
                    mask <<= 1
                return ', '.join(set_values)
            else:
                raise ValueError('invalid value list', values)
        elif encoding in ['enum', 'dipsw']:
            values = self.entry_values()
            if value >= len(values):
                return '?' + str(value)
            return values[value]

        if encoding == 'ch':
            result = ''
            char_map = self.metadata.get('char_map')
            while ba:
                b = ba.pop(0)
                if char_map:
                    result += char_map[b]
                elif b == 0 and self.entry.get('null', 'ignore') != 'ignore':
                    # treat as null-terminated or truncated string
                    break
                else:
                    result += chr(b)
            if result == self.entry.get('default', '   '):
                return None
            return result
        elif encoding == 'raw':
            return ' '.join("%02x" % b for b in ba)
        elif encoding == 'wpc_rtc':
            # day of week is Sunday to Saturday indexed by [ba[4] - 1]
            return '%04u-%02u-%02u %02u:%02u' % (
                ba[0] * 256 + ba[1],
                ba[2], ba[3],
                ba[5], ba[6])
        return '[?' + encoding + '?]'

    def format_label(self, key: str = None, short_label: bool = False) -> Optional[str]:
        """
        Return a formatted string for the entry's label, or None if it doesn't have one.
        :param key: optional key to use as a prefix on the label
        :param short_label: prefer the entry's `short_label` attribute if present
        :return:
        """
        label = self.entry.get('label', '?')
        if label.startswith('_'):
            label = None
        if short_label:
            label = self.entry.get('short_label', label)
        if key:
            label = key + ' ' + label
        return label

    def format_high_score(self, memory: SparseMemory) -> Optional[str]:
        """Special method for formatting a High Score entry which might include one or
        more sub-elements of `initials`, `score`, and `timestamp`.
        """
        elements = []
        for sub in ['initials', 'score', 'timestamp']:
            if sub in self.sub_entry:
                # during high score entry on High Speed, `initials` returns None
                formatted = self.sub_entry[sub].format_entry(memory)
                if formatted:
                    elements.append(formatted)
        if elements:
            return ' '.join(elements)
        return None

    def format_mapping(self, memory: SparseMemory) -> Tuple[str, str]:
        """Return a tuple of (label, value) for this entry for the given nvram data.

        Only works for certain sections of the file:
            audits, adjustments, dip_switches, game_state, score_record
        """
        value = self.format_entry(memory)
        if self.section in ['audits', 'adjustments']:
            if value is None:
                value = self.entry.get('default', '')
            return self.format_label(self.key), value
        elif self.section in ['game_state', 'score_record', 'dip_switches']:
            return self.format_label(), value
        else:
            raise ValueError('Unrecognized section', self.section)


class ParseNVRAM(object):
    def __init__(self, nv_json: dict, nvram: Optional[bytearray] = None) -> None:
        self.nv_json = nv_json
        self.metadata: dict[str, Any] = {'big_endian': True, 'nibble': 'both'}
        self.mapping = []
        self.platform = {}
        if nv_json is not None:
            self.process_json()
        self.memory = SparseMemory()
        if nvram:
            self.set_nvram(nvram)

    def load_json(self, json_path: str) -> None:
        with open(json_path, 'r') as json_fh:
            self.nv_json = json.load(json_fh)
        self.process_json()

    def get_dot_nv(self):
        """
        Reconstruct contents of .nv file loaded with set_nvram() or ParseNVRAM
        constructor.  Combines nvram area and extra PinMAME data at end of file.
        """
        nvram_area = self.get_memory_area(mem_type='nvram')
        nvram_mem = self.memory.find_region(nvram_area['address'])
        dotnv = bytearray(nvram_mem['data'])
        pinmame_data = self.memory.get_pinmame_data()
        if pinmame_data:
            dotnv.extend(pinmame_data)

        return dotnv

    def set_nvram(self, nv_data: bytearray):
        """
        Set nvram contents from contents of PinMAME .nv file.
        """
        nvram_mem = self.get_memory_area(mem_type='nvram')
        base = nvram_mem.get('address', 0)
        length = nvram_mem.get('size', len(nv_data))
        if length > len(nv_data):
            length = len(nv_data)
        self.memory.update_memory(base, nv_data[:length])
        if length < len(nv_data):
            self.memory.set_pinmame_data(nv_data[length:])

    def get_memory_area(self, address: int = None, mem_type: str = None) -> Optional[dict]:
        """
        Return the matching memory_area dictionary for a given CPU address.  Dictionary
        has the following values:
            - label: string describing area
            - address: base address of area
            - size: number of bytes in area
            - type: 'ram', 'nvram', 'rom'
            - nibble: Nibble.BOTH, .HIGH, or .LOW
        :param address: address appropriate for the platform's configuration
        :param mem_type: type to match on
        :return: None if the address doesn't match an entry in the platform's configuration
        """
        for region in self.platform['memory_layout']:
            if address is not None:
                start = region['address']
                end = start + region['size'] - 1
                if not (start <= address <= end):
                    continue
            if mem_type and mem_type != region['type']:
                continue
            return region
        return None

    def load_platform(self, platform_name) -> None:
        """
        Load self.platform with the contents of the platform's JSON file.
        """
        if platform_name:
            with open(os.path.join(MAPS_ROOT, 'platforms', platform_name + '.json')) as platform_file:
                platform_json = json.load(platform_file)
                self.platform = {
                    'memory_layout': []
                }
                for attribute in ['cpu', 'endian']:
                    self.platform[attribute] = platform_json.get(attribute)

                for region_json in platform_json['memory_layout']:
                    # use default nibble of BOTH
                    region: dict[str, Union[Nibble, int, str]] = {
                        'nibble': Nibble.BOTH
                    }
                    for key, value in region_json.items():
                        if key in ['address', 'size']:
                            region[key] = to_int(value)
                        elif key == 'nibble':
                            region[key] = get_nibble(value)
                        else:
                            region[key] = value
                    self.platform['memory_layout'].append(region)
        else:
            # create a fake platform for files that lack one
            self.platform = {
                'cpu': 'unknown',
                'endian': self.metadata['endian'],
                'memory_layout': [
                    {
                        'label': 'undefined',
                        'address': 0,
                        'size': to_int(self.metadata.get('ramsize', 0xFFFF)),
                        'type': 'nvram',
                        'nibble': get_nibble(self.metadata.get('nibble'))
                    }
                ]
            }
        # TODO: should we have a separate platform property for RamMapping objects?
        self.metadata['platform'] = self.platform
        self.metadata['big_endian'] = self.platform.get('endian') != 'little'

    def process_json(self) -> None:
        """Process JSON file loaded into self.nv_json.  Sets self.big_endian and
        self.mapping, a normalized list of JSON entries as RamMapping objects.
        """
        json_metadata = self.nv_json.get('_metadata')
        if json_metadata:
            # processing fileformat 0.6 or later
            for key, value in json_metadata.items():
                self.metadata[key] = value
            self.load_platform(json_metadata.get('platform'))
        else:
            raise ValueError('Unsupported map file format -- update to v0.6 or later')

        self.mapping = []
        for section in ['audits', 'adjustments']:
            for group in sorted(self.nv_json.get(section, {}).keys()):
                if group.startswith('_'):
                    continue
                for entry in self.entry_list(section, group):
                    self.mapping.append(RamMapping(entry[1],
                                                   self.metadata,
                                                   section,
                                                   group,
                                                   entry[0]))

        groups = {
            'game_state': 'Game State',
            'dip_switches': 'DIP Switches'
        }
        for group, label in groups.items():
            if group in self.nv_json:
                for key, entries in self.nv_json[group].items():
                    if not isinstance(entries, list):
                        entries = [entries]
                    for entry in entries:
                        self.mapping.append(RamMapping(entry,
                                                       self.metadata,
                                                       group,
                                                       label,
                                                       key))
        
        player_num = 1
        for p in self.nv_json.get('last_game', []):
            entry = p.copy()
            entry['label'] = 'Player %u' % player_num
            entry['short_label'] = 'P%u' % player_num
            self.mapping.append(RamMapping(entry,
                                           self.metadata,
                                           'game_state',
                                           'Player Scores'))
            player_num += 1

        for group in ['high_scores', 'mode_champions']:
            for entry in self.nv_json.get(group, []):
                self.mapping.append(RamMapping(entry,
                                               self.metadata,
                                               'score_record',
                                               group))

    def load_nvram(self, nvram_path: str) -> None:
        """Set the nvram property of the ParseNVRAM object to the contents of an nvram file."""
        with open(nvram_path, 'rb') as nv_fh:
            self.set_nvram(bytearray(nv_fh.read()))

    def ram_mapping(self, entry: dict):
        """Legacy "glue" method to create RamMapping object on-demand."""
        return RamMapping(entry, self.metadata)

    def verify_checksum8(self, entry: dict,
                         verbose: bool = False,
                         fix: bool = False) -> bool:
        """
        Verify an entry from the checksum8 attribute of the map file.

        TODO: Update this to use RamMapping objects instead.  Requires
        updating verify_all_checksum8() as well.

        :param entry: dict from the JSON file (*not* a RamMapping object)
        :param verbose: Set to True to print errors for invalid checksums.
        :param fix: Set to True to fix any invalid checksums in self.nvram.
        :return: True if checksummed area(s) was/were valid
        """
        valid = True
        label = entry.get('label', '(unlabeled)')
        m = self.ram_mapping(entry)
        ba = m.get_bytes(self.memory)
        if ba is None:
            return True
        offset = to_int(entry['start'])
        grouping = entry.get('groupings', len(ba))
        if len(ba) % grouping:
            print("Error: checksum8 '%s' size not evenly divisible by groupings" % label)
        count = 0
        calc_sum = 0
        for b in ba:
            if count == grouping - 1:
                checksum = 0xFF - (calc_sum & 0xFF)
                if checksum != b:
                    valid = False
                    if verbose:
                        print("Error: %u bytes at 0x%04X '%s' checksum8 0x%02X != 0x%02X"
                              % (grouping, offset - count, label, checksum, b))
                    if fix:
                        self.memory.update_memory(offset, [checksum])
                count = calc_sum = 0
            else:
                calc_sum += b
                count += 1
            offset += 1
        return valid

    def verify_all_checksum8(self, verbose: bool = False, fix: bool = False) -> bool:
        """
        Verify all checksum8 entries from the map file.

        :param verbose: Set to True to print errors for invalid checksums.
        :param fix: Set to True to fix any invalid checksums in self.nvram.
        :return: True if checksummed areas were valid
        """
        valid = True
        for c in self.nv_json.get('checksum8', []):
            valid &= self.verify_checksum8(c, verbose, fix)
        return valid

    def verify_checksum16(self, entry: dict,
                          verbose: bool = False,
                          fix: bool = False) -> bool:
        """
        Verify an entry from the checksum16 attribute of the map file.

        TODO: Update this to use RamMapping objects instead.  Requires
        updating verify_all_checksum16() as well.

        :param entry: dict from the JSON file (*not* a RamMapping object)
        :param verbose: Set to True to print errors for invalid checksums.
        :param fix: Set to True to fix any invalid checksums in self.memory.
        :return: True if checksummed area was valid
        """
        m = self.ram_mapping(entry)
        ba = m.get_bytes(self.memory)
        if ba is None:
            return True

        # pop last two bytes as stored checksum16
        if self.metadata['big_endian']:
            stored_sum = ba.pop() + ba.pop() * 256
        else:
            stored_sum = ba.pop() * 256 + ba.pop()
        checksum_offset = to_int(entry['start']) + len(ba)
        calc_sum = 0xFFFF - (sum(ba) & 0xFFFF)
        if calc_sum != stored_sum:
            if verbose:
                print("checksum16 at %s: 0x%04X != 0x%04X %s" % (entry['start'],
                                                                 calc_sum, stored_sum, entry.get('label', '')))
            if fix:
                if self.metadata['big_endian']:
                    self.memory.update_memory(checksum_offset, [calc_sum // 256, calc_sum % 256])
                else:
                    self.memory.update_memory(checksum_offset, [calc_sum % 256, calc_sum // 256])
        return calc_sum == stored_sum

    def verify_all_checksum16(self, verbose: bool = False, fix: bool = False) -> bool:
        """
        Verify all checksum16 entries from the map file.

        :param verbose: Set to True to print errors for invalid checksums.
        :param fix: Set to True to fix any invalid checksums in self.nvram.
        :return: True if checksummed areas were valid
        """
        valid = True
        for c in self.nv_json.get('checksum16', []):
            valid &= self.verify_checksum16(c, verbose, fix)
        return valid

    def last_played(self) -> Optional[str]:
        """Return a timestamp if this map has a last_played entry, otherwise returns None."""
        lp = self.nv_json.get('last_played')
        if not lp:
            return None
        return self.ram_mapping(lp).format_entry(self.memory)

    def entry_list(self, section: str, group: str) -> List[Tuple[str, dict]]:
        """Return a list of entries for the given section and group of the mapping file.

        Correctly handles instances where the group is a List or a Dict.
        """
        entries = []
        audit_group = self.nv_json[section][group]
        if isinstance(audit_group, list):
            for audit in audit_group:
                entries.append((None, audit))
        elif isinstance(audit_group, dict):
            for audit_key in sorted(audit_group.keys()):
                if audit_key.startswith('_'):
                    continue
                entries.append((audit_key, audit_group[audit_key]))
        else:
            ValueError("Can't process %s/%s" % (section, group))
        return entries

    # section should be 'high_scores' or 'mode_champions'
    def high_scores(self, section: str = 'high_scores',
                    short_labels: bool = False) -> List[str]:
        """
        Return a list of formatted High Scores (or Mode Champions if
        section='mode_champions').

        :param section: A section from the map with a list of high scores.  Typically,
                        'high_scores' (default) or 'mode_champions'.
        :param short_labels: Use short labels for each entry (if available).
        :return:
        """
        scores = []
        for entry in self.mapping:
            if entry.group == section:
                score = entry.format_high_score(self.memory)
                if score is not None:
                    scores.append('%s: %s' %
                                  (entry.format_label(short_label=short_labels),
                                   score))
        return scores

    def dump(self, group: str = None, verify_checksums: bool = True) -> None:
        """
        Print out formatted values for all entries for this map/nvram data.

        :param group: Limit dump to a single group, based on it's formatted name
                      (e.g., "Game State" instead of "game_state").
        :param verify_checksums: If True (default) verify checksums in nvram data.
        :return: None
        """
        last_group = None
        for map_entry in self.mapping:
            if group is None or map_entry.group == group:
                if map_entry.group == 'DIP Switches' \
                        and not self.memory.get_pinmame_data():
                    # DIP switch values only available from loaded .nv file
                    continue
                if map_entry.group != last_group:
                    print('')
                    if map_entry.group is not None:
                        print(map_entry.group)
                        print('-' * len(map_entry.group))
                    last_group = map_entry.group

                print('%s: %s' % map_entry.format_mapping(self.memory))

        last_played = self.last_played()
        if last_played is not None:
            print('Last Played:', last_played)

        if verify_checksums:
            # Verify all checksums in the file.  Note that we can eventually re-use
            # that part of the memory map to update checksums if modifying nvram values.
            self.verify_all_checksum16(verbose=True)
            self.verify_all_checksum8(verbose=True)

    @staticmethod
    def hex_line(data: bytearray, nibble: Nibble, text: Optional[str] = None) -> str:
        b = []
        ch = []
        for value in data:
            if nibble == Nibble.LOW:
                b.append(' %1X' % (value & 0x0F))
            elif nibble == Nibble.HIGH:
                b.append('%1X ' % (value >> 4))
            else:
                b.append('%02X' % value)

            if nibble == Nibble.BOTH:
                # we can potentially have printable text
                if isprint(value):
                    ch.append(chr(value))
                else:
                    ch.append('.')
            else:
                ch.append(' ')

            if len(b) == HEX_DUMP_BYTES_PER_LINE:
                break

        while len(b) < HEX_DUMP_BYTES_PER_LINE:
            # padding
            b.append('  ')
            ch.append(' ')

        if not text:
            text = ''.join(ch)
        return "%s | %s" % (' '.join(b), text)

    def hex_dump(self):
        """
        Output a hex dump of the nvram section of the parser object.

        TODO: allow caller to specify an address range
        TODO: option to include/exclude PinMAME Data if present
        TODO: iterate over ALL memory areas and dump each separately
        """
        memory_area = self.get_memory_area(mem_type='nvram')
        nvram_start = memory_area['address']
        nv_data = self.memory.find_region(nvram_start)['data']
        nvram_size = memory_area['size']
        nibble = memory_area['nibble']

        # Create a dictionary of RamMapping objects using offset as the key.
        entry = {}
        for m in self.mapping:
            if m.section == 'dip_switches':
                # skip over dip_switches -- their offsets aren't memory addresses
                continue

            # sometimes offsets is a map(?) so convert it to a list
            offsets = list(m.offsets())
            entry[offsets[0]] = m

        # add fake entries for checksum8 and checksum16 values
        for checksum in ['checksum8', 'checksum16']:
            is_16 = (checksum == 'checksum16')
            for c in self.nv_json.get(checksum, []):
                start = to_int(c['start'])
                if 'end' in c:
                    end = to_int(c['end'])
                else:
                    end = start + to_int(c['length']) - 1
                grouping = c.get('groupings', end - start + 1)
                while start < end:
                    entry_end = start + grouping - 1
                    entry[entry_end - is_16] = ChecksumMapping(start, entry_end,
                                                               c.get('label'), is_16,
                                                               self.metadata['big_endian'])
                    start = entry_end + 1

        offset = 0
        while offset < nvram_size:
            # If this offset is in entry[], display it with its formatted value.
            mapping = entry.get(nvram_start + offset)
            if mapping:
                count = len(list(mapping.offsets()))
                (label, value) = mapping.format_mapping(self.memory)
                if label:
                    text = '%s: %s' % (label, value)
                else:
                    text = value
            else:
                # show printable ASCII characters for conversion
                text = None

                # Display up to BYTES_PER_LINE bytes, avoiding the next known entry
                count = 1
                while count < HEX_DUMP_BYTES_PER_LINE and not entry.get(nvram_start + offset + count):
                    count += 1
            if offset + count > nvram_size:
                count = nvram_size - offset

            print("%04X: %s" % (nvram_start + offset,
                                self.hex_line(nv_data[offset:offset + count], nibble, text)))
            offset += count

        # print hex dump of last bytes in file
        pinmame_data = self.memory.get_pinmame_data()
        if pinmame_data:
            print("\nPinMAME data in .nv file:")
            offset = 0
            while offset < len(pinmame_data):
                # Display up to BYTES_PER_LINE bytes, avoiding the next known entry
                count = 1
                while count < HEX_DUMP_BYTES_PER_LINE and offset + count < len(pinmame_data):
                    count += 1
                print("%04X: %s" % (offset, self.hex_line(pinmame_data[offset:offset + count],
                                                          Nibble.BOTH)))
                offset += count


def main() -> None:
    parser = argparse.ArgumentParser(description='PinMAME nvram Parser')
    parser.add_argument('--map',
                        help='use this map (typically ending in .nv.json)')
    parser.add_argument('--rom',
                        help='use default map for <rom> instead of one based on <nvram> filename')
    parser.add_argument('--nvram',
                        help='nvram file to parse')
    parser.add_argument('--dump',
                        help='dump the contents of <nvram> using <map>', action='store_true')
    args = parser.parse_args()

    if args.dump:
        nvpath = args.nvram
        basename = os.path.basename(nvpath)

        if nvpath.find('.nv', 0) == -1:
            parser.print_help()
            return
        with open(nvpath, 'rb') as f:
            nvram = bytearray(f.read())

        if not args.map:
            # find a JSON file for the given nvram file
            if not args.rom:
                args.rom = rom_for_nvpath(nvpath)
            args.map = map_for_rom(args.rom)

            if args.map:
                print("Using map %s for %s" %
                      (os.path.relpath(args.map), basename))
            else:
                print("Couldn't find a map for %s" % basename)
                return

        with open(args.map, 'r') as f:
            nv_json = json.load(f)

        print("Dumping known entries for %s [%s]..." % (basename, rom_name(rom_for_nvpath(nvpath))))
        p = ParseNVRAM(nv_json, nvram)
        p.dump()

    else:
        parser.print_help()
        return

def parse_and_dump(rom: str, nvram_path: str, do_dump: bool = True):
    """API function to be called from other scripts instead of subprocess."""
    basename = os.path.basename(nvram_path)

    with open(nvram_path, "rb") as f:
        nvram = bytearray(f.read())

    # Descobre o mapa do ROM
    map_path = map_for_rom(rom)
    if not map_path:
        raise FileNotFoundError(f"Couldn't find a map for ROM '{rom}'")

    with open(map_path, "r") as f:
        nv_json = json.load(f)

    parser = ParseNVRAM(nv_json, nvram)

    if do_dump:
        parser.dump()

    return parser 


if __name__ == '__main__':
    main()