"""
Arduino Interface - Implements robust framed binary protocol for
communication with universal_programmer.ino firmware.

Protocol Frame:
  Host -> Device:
    [0xAA][0x55][CMD][SEQ][LEN_L][LEN_H][PAYLOAD...][CRC_L][CRC_H][0x55][0xAA]

  Device -> Host:
    Same structure, CMD = REQ_CMD | 0x80 for success, or 0xFF for error?
    Actually we use CMD = REQ_CMD | 0x80 for response, payload[0] = status.

CRC16-CCITT (poly 0x1021, init 0xFFFF) over CMD+SEQ+LEN_L+LEN_H+PAYLOAD

Commands:
  0x01 GET_VERSION
  0x02 GET_STATUS
  0x03 SELECT_PROTOCOL
  0x10 AVR_ENTER_PROG
  0x11 AVR_EXIT_PROG
  0x12 AVR_READ_SIGNATURE
  0x13 AVR_READ_FLASH
  0x14 AVR_READ_EEPROM
  0x15 AVR_WRITE_FLASH
  0x16 AVR_WRITE_EEPROM
  0x17 AVR_ERASE
  0x18 AVR_DETECT
  0x20 SPI_DETECT
  0x21 SPI_READ
  0x22 SPI_WRITE
  0x23 SPI_ERASE
  0x24 SPI_GET_STATUS
  0x25 SPI_WRITE_ENABLE
  0x30 I2C_SCAN
  0x31 I2C_READ
  0x32 I2C_WRITE
  0x33 I2C_DETECT
  0x40 PING
  0x41 RESET_TARGET
  0x42 SET_CONFIG

Status codes in response payload[0]:
  0x00 OK
  0x01 ERROR_GENERIC
  0x02 ERROR_NO_TARGET
  0x03 ERROR_TIMEOUT
  0x04 ERROR_INVALID_CMD
  0x05 ERROR_INVALID_PARAM
  0x06 ERROR_NOT_SUPPORTED
  0x07 ERROR_VERIFY_FAILED
  0x08 ERROR_BUSY
"""

import struct
import time
import threading
from typing import Optional, Tuple, List
from .serial_manager import SerialManager, SerialError, SerialTimeoutError


# Command definitions
CMD_GET_VERSION = 0x01
CMD_GET_STATUS = 0x02
CMD_SELECT_PROTOCOL = 0x03

CMD_AVR_ENTER_PROG = 0x10
CMD_AVR_EXIT_PROG = 0x11
CMD_AVR_READ_SIGNATURE = 0x12
CMD_AVR_READ_FLASH = 0x13
CMD_AVR_READ_EEPROM = 0x14
CMD_AVR_WRITE_FLASH = 0x15
CMD_AVR_WRITE_EEPROM = 0x16
CMD_AVR_ERASE = 0x17
CMD_AVR_DETECT = 0x18

CMD_SPI_DETECT = 0x20
CMD_SPI_READ = 0x21
CMD_SPI_WRITE = 0x22
CMD_SPI_ERASE = 0x23
CMD_SPI_GET_STATUS = 0x24
CMD_SPI_WRITE_ENABLE = 0x25

CMD_I2C_SCAN = 0x30
CMD_I2C_READ = 0x31
CMD_I2C_WRITE = 0x32
CMD_I2C_DETECT = 0x33

CMD_PING = 0x40
CMD_RESET_TARGET = 0x41
CMD_SET_CONFIG = 0x42

# Protocol constants
PROTOCOL_AVR_ISP = 0x01
PROTOCOL_SPI_MEM = 0x02
PROTOCOL_I2C_MEM = 0x03

# Status codes
STATUS_OK = 0x00
STATUS_ERROR_GENERIC = 0x01
STATUS_ERROR_NO_TARGET = 0x02
STATUS_ERROR_TIMEOUT = 0x03
STATUS_ERROR_INVALID_CMD = 0x04
STATUS_ERROR_INVALID_PARAM = 0x05
STATUS_ERROR_NOT_SUPPORTED = 0x06
STATUS_ERROR_VERIFY_FAILED = 0x07
STATUS_ERROR_BUSY = 0x08

# Frame markers
HEADER = b'\xAA\x55'
FOOTER = b'\x55\xAA'

MAX_PAYLOAD = 1024
MAX_RETRIES = 3


def crc16_ccitt(data: bytes, poly=0x1021, init=0xFFFF) -> int:
    """Calculate CRC16-CCITT"""
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


class ArduinoInterfaceError(Exception):
    pass


class ArduinoTimeoutError(ArduinoInterfaceError):
    pass


class ArduinoInterface:
    """
    High-level interface to universal programmer firmware
    Handles packet framing, CRC, retries, and command abstraction
    """

    def __init__(self, serial_manager: SerialManager):
        self.serial = serial_manager
        self._seq = 0
        self._lock = threading.RLock()
        self._version: Optional[str] = None

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    def _build_packet(self, cmd: int, payload: bytes = b'', seq: int = None) -> bytes:
        if seq is None:
            seq = self._next_seq()
        length = len(payload)
        len_bytes = struct.pack('<H', length)
        cmd_b = struct.pack('B', cmd)
        seq_b = struct.pack('B', seq)
        crc_data = cmd_b + seq_b + len_bytes + payload
        crc = crc16_ccitt(crc_data)
        crc_bytes = struct.pack('<H', crc)
        packet = HEADER + cmd_b + seq_b + len_bytes + payload + crc_bytes + FOOTER
        return packet

    def _read_packet(self, timeout: float = 2.0) -> Tuple[int, int, bytes]:
        """
        Read and parse a response packet
        Returns (cmd, seq, payload)
        Raises ArduinoInterfaceError on failure
        """
        start_time = time.time()
        buffer = bytearray()

        # State machine to find header
        while True:
            if time.time() - start_time > timeout:
                raise ArduinoTimeoutError("Timeout waiting for response header")

            # Read available data
            if self.serial.is_connected():
                # Try to read 1 byte at a time to sync
                chunk = self.serial.read(1, timeout=0.1)
                if not chunk:
                    continue
                buffer.extend(chunk)
            else:
                raise ArduinoInterfaceError("Not connected")

            # Look for header in buffer
            # Keep buffer limited to avoid growing infinitely
            if len(buffer) > 4096:
                # Discard oldest bytes, keep last 4
                del buffer[:-4]

            # Search for header 0xAA 0x55
            idx = -1
            for i in range(len(buffer) - 1):
                if buffer[i] == 0xAA and buffer[i+1] == 0x55:
                    idx = i
                    break

            if idx == -1:
                continue

            # Found header at idx, ensure we have enough for minimal packet
            # Minimal packet: HEADER(2) + CMD(1) + SEQ(1) + LEN(2) + CRC(2) + FOOTER(2) = 10
            if len(buffer) - idx < 10:
                continue

            # Parse length
            try:
                cmd = buffer[idx+2]
                seq = buffer[idx+3]
                len_l = buffer[idx+4]
                len_h = buffer[idx+5]
                payload_len = len_l | (len_h << 8)

                if payload_len > MAX_PAYLOAD + 256:  # sanity check
                    # Invalid length, discard this header and continue
                    del buffer[:idx+2]
                    continue

                total_len = 2 + 1 + 1 + 2 + payload_len + 2 + 2  # header+cmd+seq+len+payload+crc+footer

                if len(buffer) - idx < total_len:
                    # Need more data
                    # Read remaining bytes
                    remaining = total_len - (len(buffer) - idx)
                    # Try to read remaining in one go with timeout
                    more = self.serial.read(remaining, timeout=0.5)
                    if more:
                        buffer.extend(more)
                    if len(buffer) - idx < total_len:
                        continue

                # Now we have full packet candidate
                packet_start = idx
                payload_start = idx + 6
                payload_end = payload_start + payload_len
                crc_start = payload_end
                footer_start = crc_start + 2

                payload = bytes(buffer[payload_start:payload_end])
                crc_l = buffer[crc_start]
                crc_h = buffer[crc_start+1]
                received_crc = crc_l | (crc_h << 8)
                footer_b0 = buffer[footer_start]
                footer_b1 = buffer[footer_start+1]

                # Validate footer
                if footer_b0 != 0x55 or footer_b1 != 0xAA:
                    # Bad footer, discard header
                    del buffer[:idx+2]
                    continue

                # Validate CRC
                crc_data = bytes([cmd, seq, len_l, len_h]) + payload
                calc_crc = crc16_ccitt(crc_data)
                if calc_crc != received_crc:
                    # CRC mismatch, discard
                    del buffer[:idx+2]
                    continue

                # Valid packet!
                # Remove processed bytes from buffer
                del buffer[:packet_start+total_len]

                return cmd, seq, payload

            except IndexError:
                continue
            except Exception as e:
                # On any parsing error, discard header and continue
                if idx >= 0:
                    del buffer[:idx+2]
                continue

        # Should not reach here

    def _send_command(self, cmd: int, payload: bytes = b'', timeout: float = 2.0, retries: int = MAX_RETRIES) -> bytes:
        """
        Send command and wait for response
        Returns response payload (including status byte)
        """
        with self._lock:
            if not self.serial.is_connected():
                raise ArduinoInterfaceError("Not connected to Arduino")

            last_error = None
            for attempt in range(retries):
                seq = self._next_seq()
                packet = self._build_packet(cmd, payload, seq)

                try:
                    # Flush before sending
                    self.serial.flush()
                    self.serial.write(packet)

                    # Read response
                    resp_cmd, resp_seq, resp_payload = self._read_packet(timeout=timeout)

                    # Check if response matches our command (resp_cmd should be cmd|0x80)
                    expected_resp = cmd | 0x80
                    if resp_cmd != expected_resp and resp_cmd != 0xFF:
                        # Might be out-of-order or unrelated packet, but accept if seq matches?
                        # For simplicity, if seq matches, accept even if cmd differs slightly
                        if resp_seq != seq:
                            # Not our packet, try to read again quickly
                            # Give a short additional wait for correct packet
                            try:
                                resp_cmd2, resp_seq2, resp_payload2 = self._read_packet(timeout=0.5)
                                if resp_seq2 == seq:
                                    resp_cmd, resp_seq, resp_payload = resp_cmd2, resp_seq2, resp_payload2
                                else:
                                    # Still not matching, retry
                                    raise ArduinoInterfaceError(f"Unexpected response CMD {resp_cmd:02X} vs expected {expected_resp:02X}")
                            except ArduinoTimeoutError:
                                raise ArduinoInterfaceError(f"Unexpected response CMD {resp_cmd:02X}")

                    # Check status byte in payload
                    if len(resp_payload) < 1:
                        raise ArduinoInterfaceError("Empty response payload")

                    status = resp_payload[0]
                    if status != STATUS_OK:
                        # Map status to exception
                        status_messages = {
                            STATUS_ERROR_NO_TARGET: "Target not detected / no response",
                            STATUS_ERROR_TIMEOUT: "Target timeout",
                            STATUS_ERROR_INVALID_CMD: "Invalid command (firmware mismatch?)",
                            STATUS_ERROR_INVALID_PARAM: "Invalid parameter",
                            STATUS_ERROR_NOT_SUPPORTED: "Operation not supported",
                            STATUS_ERROR_VERIFY_FAILED: "Verification failed",
                            STATUS_ERROR_BUSY: "Device busy",
                            STATUS_ERROR_GENERIC: "Generic error from firmware"
                        }
                        msg = status_messages.get(status, f"Firmware error code {status}")
                        # Include any additional payload as info
                        if len(resp_payload) > 1:
                            try:
                                extra = resp_payload[1:].decode('ascii', errors='ignore')
                                msg += f" - {extra}"
                            except Exception:
                                pass
                        raise ArduinoInterfaceError(msg)

                    # Return payload without status byte
                    return resp_payload[1:]

                except ArduinoTimeoutError as e:
                    last_error = e
                    # Retry
                    time.sleep(0.1 * (attempt+1))
                    continue
                except ArduinoInterfaceError as e:
                    # For non-timeout errors, don't retry unless it's a sync issue
                    last_error = e
                    # If it's a target error, don't retry
                    if "Target" in str(e) or "Verification" in str(e):
                        raise
                    time.sleep(0.1)
                    continue
                except Exception as e:
                    last_error = e
                    time.sleep(0.1)
                    continue

            # All retries exhausted
            raise ArduinoTimeoutError(f"Command 0x{cmd:02X} failed after {retries} retries: {last_error}")

    # High-level commands

    def ping(self) -> bool:
        """Test communication with firmware"""
        try:
            resp = self._send_command(CMD_PING, b'PING', timeout=1.0, retries=2)
            return resp == b'PONG' or b'PING' in resp or len(resp) >= 0
        except Exception:
            return False

    def get_version(self) -> str:
        """Get firmware version string"""
        try:
            resp = self._send_command(CMD_GET_VERSION, b'', timeout=2.0)
            try:
                version = resp.decode('ascii', errors='ignore').strip('\x00').strip()
                self._version = version
                return version
            except Exception:
                return resp.hex()
        except Exception as e:
            raise ArduinoInterfaceError(f"Failed to get version: {e}") from e

    def get_status(self) -> dict:
        """Get firmware status"""
        try:
            resp = self._send_command(CMD_GET_STATUS, b'', timeout=2.0)
            # Expected payload: maybe 4 bytes status flags
            if len(resp) >= 4:
                flags = struct.unpack('<I', resp[:4])[0]
                return {"flags": flags, "raw": resp.hex()}
            return {"raw": resp.hex(), "flags": 0}
        except Exception as e:
            raise ArduinoInterfaceError(f"Failed to get status: {e}") from e

    def select_protocol(self, protocol_id: int) -> bool:
        """Select protocol: 1=AVR, 2=SPI, 3=I2C"""
        payload = struct.pack('B', protocol_id)
        try:
            self._send_command(CMD_SELECT_PROTOCOL, payload, timeout=2.0)
            return True
        except Exception as e:
            raise ArduinoInterfaceError(f"Failed to select protocol {protocol_id}: {e}") from e

    # AVR commands

    def avr_enter_prog(self) -> bool:
        try:
            self._send_command(CMD_AVR_ENTER_PROG, b'', timeout=3.0)
            return True
        except Exception as e:
            raise ArduinoInterfaceError(f"Failed to enter AVR programming mode: {e}") from e

    def avr_exit_prog(self) -> bool:
        try:
            self._send_command(CMD_AVR_EXIT_PROG, b'', timeout=2.0)
            return True
        except Exception as e:
            # Don't fail hard on exit
            return False

    def avr_read_signature(self) -> bytes:
        """Read 3-byte signature"""
        try:
            resp = self._send_command(CMD_AVR_READ_SIGNATURE, b'', timeout=2.0)
            if len(resp) < 3:
                raise ArduinoInterfaceError(f"Invalid signature length: {len(resp)}")
            return resp[:3]
        except Exception as e:
            raise ArduinoInterfaceError(f"Failed to read signature: {e}") from e

    def avr_detect(self) -> Tuple[bytes, dict]:
        """Detect AVR device, returns signature and info dict"""
        try:
            resp = self._send_command(CMD_AVR_DETECT, b'', timeout=3.0)
            if len(resp) < 3:
                raise ArduinoInterfaceError("Invalid detect response")
            sig = resp[:3]
            info = {}
            if len(resp) >= 7:
                # Try to parse flash size and eeprom size if provided
                try:
                    flash_size = struct.unpack('<H', resp[3:5])[0]
                    eeprom_size = struct.unpack('<H', resp[5:7])[0]
                    info['flash_size'] = flash_size * 1024 if flash_size < 1024 else flash_size
                    # Heuristic: if value small (<1024) treat as KB
                    # Actually firmware may send bytes directly
                    # We'll handle in higher layer
                    info['flash_size_raw'] = flash_size
                    info['eeprom_size'] = eeprom_size
                except Exception:
                    pass
            info['raw'] = resp.hex()
            return sig, info
        except Exception as e:
            raise ArduinoInterfaceError(f"AVR detect failed: {e}") from e

    def avr_read_flash(self, address: int, length: int, chunk_size: int = 128) -> bytes:
        """
        Read flash memory in chunks
        address is byte address, length in bytes
        """
        data = bytearray()
        remaining = length
        current_addr = address

        while remaining > 0:
            to_read = min(chunk_size, remaining)
            payload = struct.pack('<IH', current_addr, to_read)
            try:
                chunk = self._send_command(CMD_AVR_READ_FLASH, payload, timeout=3.0)
                if len(chunk) < to_read:
                    # Firmware may return less than requested at end
                    # Accept what we got
                    if len(chunk) == 0:
                        raise ArduinoInterfaceError(f"Read 0 bytes at address {current_addr:06X}")
                data.extend(chunk[:to_read])
                current_addr += to_read
                remaining -= to_read
            except Exception as e:
                raise ArduinoInterfaceError(f"Flash read failed at 0x{current_addr:06X}: {e}") from e

        return bytes(data)

    def avr_read_eeprom(self, address: int, length: int, chunk_size: int = 64) -> bytes:
        data = bytearray()
        remaining = length
        current_addr = address

        while remaining > 0:
            to_read = min(chunk_size, remaining)
            payload = struct.pack('<HH', current_addr, to_read)
            try:
                chunk = self._send_command(CMD_AVR_READ_EEPROM, payload, timeout=3.0)
                data.extend(chunk[:to_read])
                current_addr += to_read
                remaining -= to_read
            except Exception as e:
                raise ArduinoInterfaceError(f"EEPROM read failed at 0x{current_addr:04X}: {e}") from e

        return bytes(data)

    def avr_write_flash(self, address: int, data: bytes, page_size: int = 128) -> bool:
        """
        Write flash in pages
        """
        offset = 0
        total = len(data)
        current_addr = address

        while offset < total:
            chunk = data[offset:offset+page_size]
            # Payload: addr(4) + data
            payload = struct.pack('<I', current_addr) + chunk
            try:
                self._send_command(CMD_AVR_WRITE_FLASH, payload, timeout=5.0)
                current_addr += len(chunk)
                offset += len(chunk)
            except Exception as e:
                raise ArduinoInterfaceError(f"Flash write failed at 0x{current_addr:06X}: {e}") from e

        return True

    def avr_write_eeprom(self, address: int, data: bytes) -> bool:
        offset = 0
        current_addr = address
        chunk_size = 32  # EEPROM page typically smaller

        while offset < len(data):
            chunk = data[offset:offset+chunk_size]
            payload = struct.pack('<H', current_addr) + chunk
            try:
                self._send_command(CMD_AVR_WRITE_EEPROM, payload, timeout=3.0)
                current_addr += len(chunk)
                offset += len(chunk)
            except Exception as e:
                raise ArduinoInterfaceError(f"EEPROM write failed at 0x{current_addr:04X}: {e}") from e

        return True

    def avr_erase(self) -> bool:
        try:
            self._send_command(CMD_AVR_ERASE, b'', timeout=5.0)
            return True
        except Exception as e:
            raise ArduinoInterfaceError(f"Erase failed: {e}") from e

    # SPI Memory commands

    def spi_detect(self) -> bytes:
        """Read JEDEC ID (3 bytes)"""
        try:
            resp = self._send_command(CMD_SPI_DETECT, b'', timeout=2.0)
            return resp
        except Exception as e:
            raise ArduinoInterfaceError(f"SPI detect failed: {e}") from e

    def spi_read(self, address: int, length: int, chunk_size: int = 128) -> bytes:
        data = bytearray()
        remaining = length
        current_addr = address

        while remaining > 0:
            to_read = min(chunk_size, remaining)
            payload = struct.pack('<IH', current_addr, to_read)
            try:
                chunk = self._send_command(CMD_SPI_READ, payload, timeout=3.0)
                data.extend(chunk[:to_read])
                current_addr += to_read
                remaining -= to_read
            except Exception as e:
                raise ArduinoInterfaceError(f"SPI read failed at 0x{current_addr:06X}: {e}") from e

        return bytes(data)

    def spi_write(self, address: int, data: bytes, page_size: int = 256) -> bool:
        offset = 0
        current_addr = address

        while offset < len(data):
            chunk = data[offset:offset+page_size]
            payload = struct.pack('<I', current_addr) + chunk
            try:
                self._send_command(CMD_SPI_WRITE, payload, timeout=5.0)
                current_addr += len(chunk)
                offset += len(chunk)
            except Exception as e:
                raise ArduinoInterfaceError(f"SPI write failed at 0x{current_addr:06X}: {e}") from e

        return True

    def spi_erase(self, erase_type: int = 0xC7, address: int = 0) -> bool:
        """
        erase_type: 0xC7 chip erase, 0x20 sector 4K, 0xD8 block 64K
        """
        payload = struct.pack('<BI', erase_type, address)
        try:
            self._send_command(CMD_SPI_ERASE, payload, timeout=10.0)
            return True
        except Exception as e:
            raise ArduinoInterfaceError(f"SPI erase failed: {e}") from e

    # I2C commands

    def i2c_scan(self) -> List[int]:
        """Scan I2C bus, returns list of addresses found"""
        try:
            resp = self._send_command(CMD_I2C_SCAN, b'', timeout=3.0)
            # Response is list of bytes, each address
            return list(resp)
        except Exception as e:
            raise ArduinoInterfaceError(f"I2C scan failed: {e}") from e

    def i2c_detect(self, device_address: int = 0x50) -> bool:
        payload = struct.pack('B', device_address)
        try:
            self._send_command(CMD_I2C_DETECT, payload, timeout=2.0)
            return True
        except Exception:
            return False

    def i2c_read(self, device_address: int, mem_address: int, length: int, addr_width: int = 2, chunk_size: int = 32) -> bytes:
        data = bytearray()
        remaining = length
        current_addr = mem_address

        while remaining > 0:
            to_read = min(chunk_size, remaining)
            # Payload: devAddr(1) + memAddr(2) + addrWidth(1) + length(2)
            payload = struct.pack('<BHBH', device_address, current_addr, addr_width, to_read)
            try:
                chunk = self._send_command(CMD_I2C_READ, payload, timeout=3.0)
                data.extend(chunk[:to_read])
                current_addr += to_read
                remaining -= to_read
            except Exception as e:
                raise ArduinoInterfaceError(f"I2C read failed at 0x{current_addr:04X}: {e}") from e

        return bytes(data)

    def i2c_write(self, device_address: int, mem_address: int, data: bytes, addr_width: int = 2, page_size: int = 32) -> bool:
        offset = 0
        current_addr = mem_address

        while offset < len(data):
            chunk = data[offset:offset+page_size]
            # Payload: devAddr(1) + memAddr(2) + addrWidth(1) + data
            header = struct.pack('<BHB', device_address, current_addr, addr_width)
            payload = header + chunk
            try:
                self._send_command(CMD_I2C_WRITE, payload, timeout=5.0)
                current_addr += len(chunk)
                offset += len(chunk)
            except Exception as e:
                raise ArduinoInterfaceError(f"I2C write failed at 0x{current_addr:04X}: {e}") from e

        return True

    def reset_target(self, active: bool = True) -> bool:
        payload = struct.pack('B', 1 if active else 0)
        try:
            self._send_command(CMD_RESET_TARGET, payload, timeout=1.0)
            return True
        except Exception as e:
            raise ArduinoInterfaceError(f"Reset failed: {e}") from e
