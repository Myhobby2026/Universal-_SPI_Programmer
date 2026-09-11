"""
SPI Memory Protocol - Handles SPI Flash/EEPROM devices
Supports configurable device definitions
"""

import json
import os
import time
from typing import Dict, Any, Callable, Optional, Tuple, List

from .protocol_base import ProtocolBase, ProtocolError, DeviceNotDetectedError
from hardware.arduino_interface import PROTOCOL_SPI_MEM


class SPIMemoryProtocol(ProtocolBase):
    """SPI Memory protocol implementation"""

    def __init__(self, arduino_interface, device_db_path: str = None):
        super().__init__(arduino_interface)
        self.device_db: Dict[str, Dict] = {}
        self.device_list: List[Dict] = []
        self._load_device_db(device_db_path)
        self.selected_device: Optional[Dict] = None

    def _load_device_db(self, db_path: str = None):
        if db_path is None:
            possible = [
                os.path.join(os.path.dirname(__file__), '..', 'devices', 'spi_devices.json'),
                os.path.join('devices', 'spi_devices.json'),
                'spi_devices.json'
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
                        # Index by JEDEC ID
                        jedec = dev.get('jedec_id', '').upper().replace(' ', '')
                        if jedec:
                            self.device_db[jedec] = dev
                        # Index by name
                        self.device_db[dev['name'].lower()] = dev
                        self.device_db[dev.get('part_number', '').lower()] = dev
            except Exception as e:
                print(f"Failed to load SPI DB: {e}")

    def get_name(self) -> str:
        return "SPI Memory"

    def connect(self) -> bool:
        try:
            self.interface.select_protocol(PROTOCOL_SPI_MEM)
            time.sleep(0.1)
            return True
        except Exception as e:
            raise ProtocolError(f"Failed to connect to SPI target: {e}") from e

    def detect(self) -> Dict[str, Any]:
        """Detect SPI memory via JEDEC ID"""
        self.clear_cancel()
        try:
            jedec_bytes = self.interface.spi_detect()
            if len(jedec_bytes) < 3:
                raise DeviceNotDetectedError("Invalid JEDEC ID response")

            jedec_str = ' '.join(f"{b:02X}" for b in jedec_bytes[:3])
            jedec_hex = ''.join(f"{b:02X}" for b in jedec_bytes[:3])
            jedec_hex_nospace = jedec_hex.replace(' ', '')

            # Lookup
            device = None
            for key in [jedec_str, jedec_hex, jedec_hex_nospace, jedec_hex_nospace.upper()]:
                if key in self.device_db:
                    device = self.device_db[key]
                    break
                if key.upper() in self.device_db:
                    device = self.device_db[key.upper()]
                    break
                if key.lower() in self.device_db:
                    device = self.device_db[key.lower()]
                    break

            # Also try partial match (manufacturer + device)
            if not device and len(jedec_bytes) >= 2:
                man_id = f"{jedec_bytes[0]:02X}"
                # Search for devices with same manufacturer
                for dev in self.device_list:
                    if dev.get('jedec_id', '').upper().startswith(man_id):
                        # Use first match as fallback if no exact
                        if not device:
                            device = dev

            result = {
                'jedec_id': jedec_str,
                'jedec_bytes': jedec_bytes,
                'raw': jedec_bytes.hex(),
            }

            if device:
                result.update({
                    'name': device.get('name', f"SPI Flash {jedec_str}"),
                    'manufacturer': device.get('manufacturer', 'Unknown'),
                    'flash_size': device.get('capacity', 4096*1024),
                    'page_size': device.get('page_size', 256),
                    'sector_size': device.get('sector_size', 4096),
                    'device': device
                })
                self.selected_device = device
            else:
                # Unknown, guess size from JEDEC if possible
                # Third byte often indicates capacity: 2^n
                # e.g., 0x17 = 128Mbit = 16MB, 0x18 = 256Mbit = 32MB
                capacity = 4096*1024  # default 4MB
                if len(jedec_bytes) >= 3:
                    cap_code = jedec_bytes[2]
                    if 0x10 <= cap_code <= 0x20:
                        # Common: capacity = 2^cap_code
                        try:
                            capacity = (1 << cap_code)
                        except Exception:
                            pass

                result.update({
                    'name': f'Unknown SPI Flash ({jedec_str})',
                    'manufacturer': f'ID 0x{jedec_bytes[0]:02X}',
                    'flash_size': capacity,
                    'page_size': 256,
                    'sector_size': 4096,
                    'device': None
                })

            self.device_info = result
            return result

        except DeviceNotDetectedError:
            raise
        except Exception as e:
            raise ProtocolError(f"SPI detection failed: {e}") from e

    def read(self, memory_type: str = "flash", address: int = 0, length: int = None,
             progress_callback: Callable[[int, str], None] = None) -> bytes:
        self.clear_cancel()
        if not self.device_info and length is None:
            raise ProtocolError("Device not detected. Run detect first or specify length.")

        if length is None:
            length = self.device_info.get('flash_size', 4096*1024)

        data = bytearray()
        chunk_size = 128
        total_chunks = (length + chunk_size - 1) // chunk_size

        try:
            for i in range(total_chunks):
                if self.is_cancelled():
                    raise ProtocolError("Operation cancelled")

                current_addr = address + i * chunk_size
                to_read = min(chunk_size, length - len(data))

                chunk = self.interface.spi_read(current_addr, to_read, chunk_size=chunk_size)
                data.extend(chunk)

                if progress_callback:
                    percent = int((len(data) / length) * 100)
                    progress_callback(percent, f"Reading SPI 0x{current_addr:06X} ({percent}%)")

            return bytes(data)

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise ProtocolError("Read cancelled") from e
            raise ProtocolError(f"SPI read failed: {e}") from e

    def write(self, data: bytes, memory_type: str = "flash", address: int = 0,
              progress_callback: Callable[[int, str], None] = None) -> bool:
        self.clear_cancel()
        if not self.device_info:
            # Allow write without detect if user knows what they're doing
            max_size = 16*1024*1024
        else:
            max_size = self.device_info.get('flash_size', 16*1024*1024)

        if len(data) > max_size:
            raise ProtocolError(f"Data size {len(data)} exceeds device size {max_size}")

        page_size = self.device_info.get('page_size', 256) if self.device_info else 256
        total = len(data)
        offset = 0
        current_addr = address

        try:
            while offset < total:
                if self.is_cancelled():
                    raise ProtocolError("Operation cancelled")

                chunk = data[offset:offset+page_size]
                self.interface.spi_write(current_addr, chunk, page_size=page_size)

                offset += len(chunk)
                current_addr += len(chunk)

                if progress_callback:
                    percent = int((offset / total) * 100)
                    progress_callback(percent, f"Writing SPI 0x{current_addr:06X} ({percent}%)")

                # Small delay for write cycle
                time.sleep(0.005)

            return True

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise ProtocolError("Write cancelled") from e
            raise ProtocolError(f"SPI write failed: {e}") from e

    def verify(self, data: bytes, memory_type: str = "flash", address: int = 0,
               progress_callback: Callable[[int, str], None] = None) -> Tuple[bool, Optional[Dict]]:
        self.clear_cancel()
        try:
            if progress_callback:
                progress_callback(0, "Verifying SPI...")

            read_data = self.read(memory_type, address, len(data), progress_callback)

            if len(read_data) != len(data):
                return False, {
                    'error': f"Length mismatch",
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
            raise ProtocolError(f"SPI verify failed: {e}") from e

    def erase(self, memory_type: str = "all",
              progress_callback: Callable[[int, str], None] = None) -> bool:
        self.clear_cancel()
        try:
            if progress_callback:
                progress_callback(0, "Erasing SPI chip...")

            # Chip erase by default
            erase_type = 0xC7
            if memory_type == "sector":
                erase_type = 0x20
            elif memory_type == "block":
                erase_type = 0xD8

            self.interface.spi_erase(erase_type, 0)

            if progress_callback:
                progress_callback(100, "Erase complete")

            return True

        except Exception as e:
            raise ProtocolError(f"SPI erase failed: {e}") from e

    def close(self):
        pass

    def get_available_devices(self) -> List[Dict]:
        return self.device_list
