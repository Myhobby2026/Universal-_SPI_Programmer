"""
AVR ISP Protocol - Handles AVR microcontroller programming via ISP
Preserves original ArduinoISP functionality while adding new framed protocol support
"""

import time
import json
import os
from typing import Dict, Any, Callable, Optional, Tuple

from .protocol_base import ProtocolBase, ProtocolError, DeviceNotDetectedError
from hardware.arduino_interface import PROTOCOL_AVR_ISP


class AVRISPProtocol(ProtocolBase):
    """AVR ISP protocol implementation"""

    def __init__(self, arduino_interface, device_db_path: str = None):
        super().__init__(arduino_interface)
        self.device_db = {}
        self._load_device_db(device_db_path)

    def _load_device_db(self, db_path: str = None):
        """Load AVR device database"""
        if db_path is None:
            # Try default locations
            possible = [
                os.path.join(os.path.dirname(__file__), '..', 'devices', 'avr_devices.json'),
                os.path.join('devices', 'avr_devices.json'),
                'avr_devices.json'
            ]
            for p in possible:
                if os.path.exists(p):
                    db_path = p
                    break

        if db_path and os.path.exists(db_path):
            try:
                with open(db_path, 'r') as f:
                    data = json.load(f)
                    # Index by signature string "1E 95 0F"
                    for dev in data:
                        sig = dev.get('signature', '').upper().replace(' ', '')
                        if len(sig) == 6:
                            formatted = f"{sig[0:2]} {sig[2:4]} {sig[4:6]}"
                            self.device_db[formatted] = dev
                            self.device_db[sig] = dev
                        # Also index by name
                        self.device_db[dev['name'].lower()] = dev
            except Exception as e:
                print(f"Failed to load AVR DB: {e}")

    def get_name(self) -> str:
        return "AVR ISP"

    def connect(self) -> bool:
        """Select AVR protocol and enter programming mode"""
        try:
            self.interface.select_protocol(PROTOCOL_AVR_ISP)
            time.sleep(0.1)
            self.interface.avr_enter_prog()
            return True
        except Exception as e:
            raise ProtocolError(f"Failed to connect to AVR target: {e}") from e

    def detect(self) -> Dict[str, Any]:
        """Detect AVR device"""
        self.clear_cancel()
        try:
            # Try framed detect first
            try:
                sig_bytes, info = self.interface.avr_detect()
                sig_str = ' '.join(f"{b:02X}" for b in sig_bytes)
                sig_hex = ''.join(f"{b:02X}" for b in sig_bytes)
            except Exception:
                # Fallback to signature read
                sig_bytes = self.interface.avr_read_signature()
                sig_str = ' '.join(f"{b:02X}" for b in sig_bytes)
                sig_hex = ''.join(f"{b:02X}" for b in sig_bytes)
                info = {}

            if sig_bytes == b'\x00\x00\x00' or sig_bytes == b'\xFF\xFF\xFF':
                raise DeviceNotDetectedError(f"Invalid signature {sig_str} - check wiring and target power")

            # Lookup device
            device = None
            # Try different formats
            for key in [sig_str, sig_hex, sig_str.replace(' ', '')]:
                if key in self.device_db:
                    device = self.device_db[key]
                    break
                if key.upper() in self.device_db:
                    device = self.device_db[key.upper()]
                    break

            # Build info
            result = {
                'signature': sig_str,
                'signature_bytes': sig_bytes,
                'raw_info': info,
            }

            if device:
                result.update({
                    'name': device.get('name', 'Unknown'),
                    'manufacturer': device.get('manufacturer', 'Atmel/Microchip'),
                    'flash_size': device.get('flash_size', info.get('flash_size', 32768)),
                    'eeprom_size': device.get('eeprom_size', info.get('eeprom_size', 1024)),
                    'page_size': device.get('page_size', 128),
                    'device': device
                })
            else:
                # Unknown device, use info or defaults
                flash_size = info.get('flash_size', 32768)
                # If raw value looks like KB, convert
                if isinstance(flash_size, int) and flash_size < 1024:
                    flash_size = flash_size * 1024
                result.update({
                    'name': f'Unknown AVR ({sig_str})',
                    'manufacturer': 'Unknown',
                    'flash_size': flash_size if isinstance(flash_size, int) else 32768,
                    'eeprom_size': info.get('eeprom_size', 1024),
                    'page_size': 128,
                    'device': None
                })

            # Ensure sizes are sensible
            if result['flash_size'] == 0:
                result['flash_size'] = 32768
            if result['eeprom_size'] == 0:
                result['eeprom_size'] = 1024

            self.device_info = result
            return result

        except DeviceNotDetectedError:
            raise
        except Exception as e:
            raise ProtocolError(f"AVR detection failed: {e}") from e

    def read(self, memory_type: str = "flash", address: int = 0, length: int = None,
             progress_callback: Callable[[int, str], None] = None) -> bytes:
        """Read AVR memory"""
        self.clear_cancel()
        if not self.device_info:
            raise ProtocolError("Device not detected. Run detect first.")

        if length is None:
            if memory_type == "flash":
                length = self.device_info.get('flash_size', 32768)
            elif memory_type == "eeprom":
                length = self.device_info.get('eeprom_size', 1024)
            else:
                raise ProtocolError(f"Unsupported memory type: {memory_type}")

        # Validate
        if length <= 0:
            raise ProtocolError(f"Invalid length {length}")

        data = bytearray()
        chunk_size = 128 if memory_type == "flash" else 64
        total_chunks = (length + chunk_size - 1) // chunk_size

        try:
            for i in range(total_chunks):
                if self.is_cancelled():
                    raise ProtocolError("Operation cancelled by user")

                current_addr = address + i * chunk_size
                to_read = min(chunk_size, length - len(data))

                if memory_type == "flash":
                    chunk = self.interface.avr_read_flash(current_addr, to_read, chunk_size=chunk_size)
                elif memory_type == "eeprom":
                    chunk = self.interface.avr_read_eeprom(current_addr, to_read, chunk_size=chunk_size)
                else:
                    raise ProtocolError(f"Unsupported memory type {memory_type}")

                data.extend(chunk)

                if progress_callback:
                    percent = int((len(data) / length) * 100)
                    progress_callback(percent, f"Reading {memory_type} 0x{current_addr:06X} ({percent}%)")

            return bytes(data)

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise ProtocolError("Read cancelled") from e
            raise ProtocolError(f"Read {memory_type} failed: {e}") from e

    def write(self, data: bytes, memory_type: str = "flash", address: int = 0,
              progress_callback: Callable[[int, str], None] = None) -> bool:
        """Write AVR memory"""
        self.clear_cancel()
        if not self.device_info:
            raise ProtocolError("Device not detected")

        # Validate size
        max_size = self.device_info.get('flash_size', 32768) if memory_type == "flash" else self.device_info.get('eeprom_size', 1024)
        if len(data) > max_size:
            raise ProtocolError(f"Data size {len(data)} exceeds {memory_type} size {max_size}")

        page_size = self.device_info.get('page_size', 128) if memory_type == "flash" else 32
        total = len(data)
        offset = 0
        current_addr = address

        try:
            while offset < total:
                if self.is_cancelled():
                    raise ProtocolError("Operation cancelled by user")

                chunk = data[offset:offset+page_size]
                if memory_type == "flash":
                    self.interface.avr_write_flash(current_addr, chunk, page_size=page_size)
                elif memory_type == "eeprom":
                    self.interface.avr_write_eeprom(current_addr, chunk)
                else:
                    raise ProtocolError(f"Unsupported memory type {memory_type}")

                offset += len(chunk)
                current_addr += len(chunk)

                if progress_callback:
                    percent = int((offset / total) * 100)
                    progress_callback(percent, f"Writing {memory_type} 0x{current_addr:06X} ({percent}%)")

                # Small delay for EEPROM
                if memory_type == "eeprom":
                    time.sleep(0.01)

            return True

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise ProtocolError("Write cancelled") from e
            raise ProtocolError(f"Write {memory_type} failed: {e}") from e

    def verify(self, data: bytes, memory_type: str = "flash", address: int = 0,
               progress_callback: Callable[[int, str], None] = None) -> Tuple[bool, Optional[Dict]]:
        """Verify memory against provided data"""
        self.clear_cancel()
        try:
            if progress_callback:
                progress_callback(0, f"Verifying {memory_type}...")

            read_data = self.read(memory_type, address, len(data), progress_callback)

            if len(read_data) != len(data):
                return False, {
                    'error': f"Length mismatch: expected {len(data)}, read {len(read_data)}",
                    'address': 0,
                    'expected': len(data),
                    'actual': len(read_data)
                }

            # Find first mismatch
            for i in range(len(data)):
                if self.is_cancelled():
                    raise ProtocolError("Verify cancelled")
                if data[i] != read_data[i]:
                    # Count total differences
                    diff_count = sum(1 for a, b in zip(data, read_data) if a != b)
                    return False, {
                        'address': address + i,
                        'expected': data[i],
                        'actual': read_data[i],
                        'diff_count': diff_count,
                        'first_mismatch': address + i,
                        'data': data,
                        'read_data': read_data
                    }

            return True, None

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise ProtocolError("Verify cancelled") from e
            raise ProtocolError(f"Verify failed: {e}") from e

    def erase(self, memory_type: str = "all",
              progress_callback: Callable[[int, str], None] = None) -> bool:
        """Erase AVR chip"""
        self.clear_cancel()
        try:
            if progress_callback:
                progress_callback(0, "Erasing chip...")
            self.interface.avr_erase()
            if progress_callback:
                progress_callback(100, "Erase complete")
            return True
        except Exception as e:
            raise ProtocolError(f"Erase failed: {e}") from e

    def close(self):
        """Exit programming mode"""
        try:
            self.interface.avr_exit_prog()
        except Exception:
            pass

    def supports_memory_type(self, memory_type: str) -> bool:
        return memory_type in ["flash", "eeprom", "all"]
