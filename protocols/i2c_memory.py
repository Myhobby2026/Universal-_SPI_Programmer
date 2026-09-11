"""
I2C Memory Protocol - Handles I2C EEPROM devices like 24Cxx series
"""

import json
import os
import time
from typing import Dict, Any, Callable, Optional, Tuple, List

from .protocol_base import ProtocolBase, ProtocolError, DeviceNotDetectedError
from hardware.arduino_interface import PROTOCOL_I2C_MEM


class I2CMemoryProtocol(ProtocolBase):
    """I2C EEPROM protocol"""

    def __init__(self, arduino_interface, device_db_path: str = None):
        super().__init__(arduino_interface)
        self.device_db: Dict[str, Dict] = {}
        self.device_list: List[Dict] = []
        self._load_device_db(device_db_path)
        self.selected_device: Optional[Dict] = None
        self.device_address: int = 0x50  # Default for 24Cxx
        self.addr_width: int = 2

    def _load_device_db(self, db_path: str = None):
        if db_path is None:
            possible = [
                os.path.join(os.path.dirname(__file__), '..', 'devices', 'i2c_devices.json'),
                os.path.join('devices', 'i2c_devices.json'),
                'i2c_devices.json'
            ]
            for p in possible:
                if os.path.exists(p):
                    db_path = p
                    break

        if db_path and os.path.exists(db_path):
            try:
                with open(db_path, 'r') as f:
                    data = json.load(f)
                    self.device_list = data
                    for dev in data:
                        self.device_db[dev['name'].lower()] = dev
                        self.device_db[dev.get('part_number', '').lower()] = dev
            except Exception as e:
                print(f"Failed to load I2C DB: {e}")

    def get_name(self) -> str:
        return "I2C Memory"

    def connect(self) -> bool:
        try:
            self.interface.select_protocol(PROTOCOL_I2C_MEM)
            time.sleep(0.1)
            return True
        except Exception as e:
            raise ProtocolError(f"Failed to connect to I2C target: {e}") from e

    def set_device_address(self, addr: int):
        """Set I2C device address (e.g., 0x50)"""
        self.device_address = addr & 0x7F

    def set_addr_width(self, width: int):
        """Set memory address width: 1 or 2 bytes"""
        if width not in [1, 2]:
            raise ProtocolError("Address width must be 1 or 2")
        self.addr_width = width

    def scan(self) -> List[int]:
        """Scan I2C bus for devices"""
        try:
            return self.interface.i2c_scan()
        except Exception as e:
            raise ProtocolError(f"I2C scan failed: {e}") from e

    def detect(self) -> Dict[str, Any]:
        """Detect I2C device by scanning"""
        self.clear_cancel()
        try:
            # Scan bus
            found = self.interface.i2c_scan()

            if not found:
                raise DeviceNotDetectedError("No I2C devices found - check wiring and pull-ups")

            # If our selected address is in found list, use it
            # Otherwise use first found
            if self.device_address not in found:
                # Prefer 0x50-0x57 range for EEPROMs
                eeprom_addrs = [a for a in found if 0x50 <= a <= 0x57]
                if eeprom_addrs:
                    self.device_address = eeprom_addrs[0]
                else:
                    self.device_address = found[0]

            # Try to detect specific device by reading
            # For now, we don't have JEDEC, so guess based on address and maybe size
            # Attempt to read 1 byte to confirm device responds
            try:
                self.interface.i2c_read(self.device_address, 0, 1, self.addr_width, chunk_size=1)
            except Exception as e:
                raise DeviceNotDetectedError(f"Device at 0x{self.device_address:02X} not responding: {e}")

            # Try to find matching device in DB based on address or default
            device = None
            # If user previously selected a device, keep it
            if self.selected_device:
                device = self.selected_device
            else:
                # Default to 24C256 if unknown
                for dev in self.device_list:
                    if dev.get('default', False):
                        device = dev
                        break
                if not device and self.device_list:
                    device = self.device_list[0]

            result = {
                'i2c_address': self.device_address,
                'i2c_address_str': f"0x{self.device_address:02X}",
                'found_devices': found,
                'found_str': ', '.join(f"0x{a:02X}" for a in found),
            }

            if device:
                result.update({
                    'name': device.get('name', f"I2C EEPROM @ 0x{self.device_address:02X}"),
                    'manufacturer': device.get('manufacturer', 'Unknown'),
                    'flash_size': device.get('capacity', 32*1024),
                    'page_size': device.get('page_size', 64),
                    'addr_width': device.get('addr_width', 2),
                    'device': device
                })
                self.addr_width = device.get('addr_width', 2)
            else:
                result.update({
                    'name': f'I2C EEPROM @ 0x{self.device_address:02X}',
                    'manufacturer': 'Unknown',
                    'flash_size': 32*1024,
                    'page_size': 64,
                    'addr_width': 2,
                    'device': None
                })

            self.device_info = result
            return result

        except DeviceNotDetectedError:
            raise
        except Exception as e:
            raise ProtocolError(f"I2C detection failed: {e}") from e

    def read(self, memory_type: str = "eeprom", address: int = 0, length: int = None,
             progress_callback: Callable[[int, str], None] = None) -> bytes:
        self.clear_cancel()
        if not self.device_info and length is None:
            raise ProtocolError("Device not detected. Run detect first or specify length.")

        if length is None:
            length = self.device_info.get('flash_size', 32*1024) if self.device_info else 32*1024

        data = bytearray()
        chunk_size = 32
        total_chunks = (length + chunk_size - 1) // chunk_size

        try:
            for i in range(total_chunks):
                if self.is_cancelled():
                    raise ProtocolError("Operation cancelled")

                current_addr = address + i * chunk_size
                to_read = min(chunk_size, length - len(data))

                chunk = self.interface.i2c_read(
                    self.device_address,
                    current_addr,
                    to_read,
                    self.addr_width,
                    chunk_size=chunk_size
                )
                data.extend(chunk)

                if progress_callback:
                    percent = int((len(data) / length) * 100)
                    progress_callback(percent, f"Reading I2C 0x{current_addr:04X} ({percent}%)")

            return bytes(data)

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise ProtocolError("Read cancelled") from e
            raise ProtocolError(f"I2C read failed: {e}") from e

    def write(self, data: bytes, memory_type: str = "eeprom", address: int = 0,
              progress_callback: Callable[[int, str], None] = None) -> bool:
        self.clear_cancel()
        max_size = self.device_info.get('flash_size', 32*1024) if self.device_info else 32*1024

        if len(data) > max_size:
            raise ProtocolError(f"Data size {len(data)} exceeds device size {max_size}")

        page_size = self.device_info.get('page_size', 32) if self.device_info else 32
        total = len(data)
        offset = 0
        current_addr = address

        try:
            while offset < total:
                if self.is_cancelled():
                    raise ProtocolError("Operation cancelled")

                # Ensure we don't cross page boundary
                page_offset = current_addr % page_size
                space_in_page = page_size - page_offset
                chunk_size = min(space_in_page, total - offset, page_size)
                chunk = data[offset:offset+chunk_size]

                self.interface.i2c_write(
                    self.device_address,
                    current_addr,
                    chunk,
                    self.addr_width,
                    page_size=page_size
                )

                offset += len(chunk)
                current_addr += len(chunk)

                if progress_callback:
                    percent = int((offset / total) * 100)
                    progress_callback(percent, f"Writing I2C 0x{current_addr:04X} ({percent}%)")

                # I2C EEPROM write cycle time ~5ms
                time.sleep(0.01)

            return True

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise ProtocolError("Write cancelled") from e
            raise ProtocolError(f"I2C write failed: {e}") from e

    def verify(self, data: bytes, memory_type: str = "eeprom", address: int = 0,
               progress_callback: Callable[[int, str], None] = None) -> Tuple[bool, Optional[Dict]]:
        self.clear_cancel()
        try:
            if progress_callback:
                progress_callback(0, "Verifying I2C...")

            read_data = self.read(memory_type, address, len(data), progress_callback)

            if len(read_data) != len(data):
                return False, {
                    'error': "Length mismatch",
                    'address': 0,
                    'expected': len(data),
                    'actual': len(read_data)
                }

            for i in range(len(data)):
                if self.is_cancelled():
                    raise ProtocolError("Verify cancelled")
                if data[i] != read_data[i]:
                    diff_count = sum(1 for a, b in zip(data, read_data) if a != b)
                    return False, {
                        'address': address + i,
                        'expected': data[i],
                        'actual': read_data[i],
                        'diff_count': diff_count,
                        'first_mismatch': address + i
                    }

            return True, None

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise ProtocolError("Verify cancelled") from e
            raise ProtocolError(f"I2C verify failed: {e}") from e

    def erase(self, memory_type: str = "all",
              progress_callback: Callable[[int, str], None] = None) -> bool:
        """Erase by writing 0xFF"""
        self.clear_cancel()
        try:
            size = self.device_info.get('flash_size', 32*1024) if self.device_info else 32*1024
            # Write 0xFF in chunks
            chunk = b'\xFF' * 64
            offset = 0
            while offset < size:
                if self.is_cancelled():
                    raise ProtocolError("Erase cancelled")
                to_write = min(len(chunk), size - offset)
                self.write(chunk[:to_write], address=offset,
                           progress_callback=lambda p, m: progress_callback(int((offset+to_write)/size*100), f"Erasing {int((offset+to_write)/size*100)}%") if progress_callback else None)
                offset += to_write

            if progress_callback:
                progress_callback(100, "Erase complete")

            return True

        except Exception as e:
            raise ProtocolError(f"I2C erase failed: {e}") from e

    def close(self):
        pass

    def get_available_devices(self) -> List[Dict]:
        return self.device_list
