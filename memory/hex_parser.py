"""
Hex Parser - Intel HEX file support (optional) and hex utilities
"""

import os
from typing import Tuple, Dict, Any


class HexParserError(Exception):
    pass


class HexParser:
    """Intel HEX parser and hex utilities"""

    @staticmethod
    def parse_intel_hex(filepath: str) -> Tuple[bytes, Dict[str, Any]]:
        """
        Parse Intel HEX file
        Returns (binary_data, info)
        """
        try:
            data_dict = {}  # address -> byte
            max_addr = 0
            min_addr = None
            extended_addr = 0

            with open(filepath, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    if not line.startswith(':'):
                        raise HexParserError(f"Line {line_num}: Invalid HEX line (missing ':')")

                    # Parse record
                    try:
                        byte_count = int(line[1:3], 16)
                        address = int(line[3:7], 16)
                        record_type = int(line[7:9], 16)
                        data_str = line[9:9+byte_count*2]
                        checksum = int(line[9+byte_count*2:9+byte_count*2+2], 16)

                        # Validate checksum
                        total = byte_count + (address >> 8) + (address & 0xFF) + record_type
                        data_bytes = []
                        for i in range(0, len(data_str), 2):
                            b = int(data_str[i:i+2], 16)
                            data_bytes.append(b)
                            total += b
                        total = (total + checksum) & 0xFF
                        if total != 0:
                            raise HexParserError(f"Line {line_num}: Checksum error")

                        if record_type == 0:  # Data
                            full_addr = extended_addr + address
                            for i, b in enumerate(data_bytes):
                                addr = full_addr + i
                                data_dict[addr] = b
                                max_addr = max(max_addr, addr)
                                if min_addr is None:
                                    min_addr = addr
                                else:
                                    min_addr = min(min_addr, addr)

                        elif record_type == 1:  # EOF
                            break

                        elif record_type == 2:  # Extended Segment Address
                            if len(data_bytes) >= 2:
                                extended_addr = ((data_bytes[0] << 8) | data_bytes[1]) << 4

                        elif record_type == 4:  # Extended Linear Address
                            if len(data_bytes) >= 2:
                                extended_addr = ((data_bytes[0] << 8) | data_bytes[1]) << 16

                        # Other record types ignored for now

                    except ValueError as ve:
                        raise HexParserError(f"Line {line_num}: Parse error {ve}") from ve

            if not data_dict:
                raise HexParserError("No data found in HEX file")

            # Build contiguous binary from min to max, filling gaps with 0xFF
            if min_addr is None:
                min_addr = 0

            size = max_addr - min_addr + 1
            binary = bytearray([0xFF] * size)
            for addr, b in data_dict.items():
                binary[addr - min_addr] = b

            info = {
                'filepath': filepath,
                'size': size,
                'min_address': min_addr,
                'max_address': max_addr,
                'format': 'intel_hex'
            }

            return bytes(binary), info

        except HexParserError:
            raise
        except Exception as e:
            raise HexParserError(f"Failed to parse HEX file: {e}") from e

    @staticmethod
    def format_hex_dump(data: bytes, start_addr: int = 0, width: int = 16) -> str:
        """Format data as classic hex dump string"""
        lines = []
        for i in range(0, len(data), width):
            chunk = data[i:i+width]
            hex_bytes = ' '.join(f"{b:02X}" for b in chunk)
            # Pad hex_bytes to fixed width for alignment
            hex_padded = hex_bytes.ljust(width*3 - 1)
            ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
            lines.append(f"{start_addr + i:08X}  {hex_padded}  |{ascii_str}|")
        return '\n'.join(lines)
