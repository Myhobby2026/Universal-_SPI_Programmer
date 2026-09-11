"""
Serial Manager - Handles COM port detection and serial communication
with graceful error handling and timeout management.
"""

import sys
import time
import threading
from typing import List, Optional, Tuple

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


class SerialError(Exception):
    """Base serial communication error"""
    pass


class SerialTimeoutError(SerialError):
    """Serial timeout"""
    pass


class SerialManager:
    """Manages serial port connection and communication"""

    def __init__(self, timeout: float = 2.0):
        self._serial: Optional[serial.Serial] = None
        self._port: Optional[str] = None
        self._baud: int = 115200
        self._timeout = timeout
        self._lock = threading.RLock()
        self._last_error: Optional[str] = None

    @staticmethod
    def list_ports() -> List[Tuple[str, str]]:
        """
        Detect available COM ports
        Returns list of (port_name, description)
        """
        if serial is None:
            return []

        ports = []
        try:
            for p in serial.tools.list_ports.comports():
                # p.device like COM5 or /dev/ttyUSB0
                # p.description
                desc = f"{p.description} - {p.device}" if p.description else p.device
                ports.append((p.device, desc))
        except Exception as e:
            # Fallback - try common ports
            print(f"Port detection error: {e}", file=sys.stderr)
        return ports

    def connect(self, port: str, baud: int = 115200, timeout: float = None) -> bool:
        """
        Connect to Arduino on specified port
        """
        if serial is None:
            raise SerialError("pyserial not installed. Run pip install pyserial")

        with self._lock:
            if self._serial and self._serial.is_open:
                self.disconnect()

            if timeout is not None:
                self._timeout = timeout

            try:
                # For Arduino Uno, opening serial triggers reset via DTR
                # We handle this by waiting for bootloader to finish
                self._serial = serial.Serial(
                    port=port,
                    baudrate=baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self._timeout,
                    write_timeout=self._timeout,
                    xonxoff=False,
                    rtscts=False,
                    dsrdtr=False
                )
                # Critical: Arduino Uno resets on serial open and bootloader waits ~1-2 seconds
                # We need to wait for it to finish before communicating
                # Also need to handle both old bootloader (1.5s) and new (0.5s) and ESP32 (1s)
                time.sleep(0.5)
                # Clear any bootloader output or garbage
                try:
                    self._serial.reset_input_buffer()
                    self._serial.reset_output_buffer()
                except Exception:
                    pass

                # Wait for Arduino to be ready - total 2.5 seconds from open
                # This covers Uno reset + bootloader + firmware init
                time.sleep(2.0)

                # Flush again after boot
                try:
                    # Read and discard any boot garbage
                    self._serial.timeout = 0.5
                    while True:
                        data = self._serial.read(1024)
                        if not data:
                            break
                    self._serial.timeout = self._timeout
                    self._serial.reset_input_buffer()
                    self._serial.reset_output_buffer()
                except Exception:
                    pass

                self._port = port
                self._baud = baud
                self._last_error = None
                return True

            except serial.SerialException as e:
                self._last_error = str(e)
                self._serial = None
                raise SerialError(f"Failed to open {port}: {e}") from e
            except Exception as e:
                self._last_error = str(e)
                self._serial = None
                raise SerialError(f"Connection error on {port}: {e}") from e

    def disconnect(self):
        """Disconnect from serial port"""
        with self._lock:
            if self._serial:
                try:
                    if self._serial.is_open:
                        self._serial.close()
                except Exception:
                    pass
                finally:
                    self._serial = None
            self._port = None

    def is_connected(self) -> bool:
        """Check if connected"""
        with self._lock:
            return self._serial is not None and self._serial.is_open

    def get_port(self) -> Optional[str]:
        return self._port

    def get_baud(self) -> int:
        return self._baud

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    def write(self, data: bytes) -> int:
        """Write bytes to serial, thread-safe"""
        with self._lock:
            if not self.is_connected():
                raise SerialError("Not connected")
            try:
                return self._serial.write(data)
            except serial.SerialTimeoutException as e:
                raise SerialTimeoutError(f"Write timeout: {e}") from e
            except serial.SerialException as e:
                self._last_error = str(e)
                raise SerialError(f"Write error: {e}") from e

    def read(self, size: int = 1, timeout: float = None) -> bytes:
        """Read exactly size bytes or less if timeout"""
        with self._lock:
            if not self.is_connected():
                raise SerialError("Not connected")
            try:
                if timeout is not None:
                    original_timeout = self._serial.timeout
                    self._serial.timeout = timeout
                    try:
                        data = self._serial.read(size)
                    finally:
                        self._serial.timeout = original_timeout
                    return data
                else:
                    return self._serial.read(size)
            except serial.SerialException as e:
                self._last_error = str(e)
                raise SerialError(f"Read error: {e}") from e

    def read_until(self, terminator: bytes = b'\n', timeout: float = None) -> bytes:
        """Read until terminator"""
        with self._lock:
            if not self.is_connected():
                raise SerialError("Not connected")
            try:
                if timeout is not None:
                    orig = self._serial.timeout
                    self._serial.timeout = timeout
                    try:
                        return self._serial.read_until(terminator)
                    finally:
                        self._serial.timeout = orig
                else:
                    return self._serial.read_until(terminator)
            except serial.SerialException as e:
                raise SerialError(f"Read error: {e}") from e

    def read_available(self) -> bytes:
        """Read all available bytes without blocking"""
        with self._lock:
            if not self.is_connected():
                return b''
            try:
                waiting = self._serial.in_waiting
                if waiting > 0:
                    return self._serial.read(waiting)
                return b''
            except Exception:
                return b''

    def flush(self):
        """Flush input and output"""
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.reset_input_buffer()
                    self._serial.reset_output_buffer()
                except Exception:
                    pass

    def __del__(self):
        try:
            self.disconnect()
        except Exception:
            pass
