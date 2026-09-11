"""
Protocol Base - Abstract base class for all programmer protocols
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable, List, Tuple
import threading


class ProtocolError(Exception):
    pass


class DeviceNotDetectedError(ProtocolError):
    pass


class ProtocolBase(ABC):
    """Common interface for all protocols"""

    def __init__(self, arduino_interface):
        self.interface = arduino_interface
        self.device_info: Optional[Dict[str, Any]] = None
        self._cancel_event = threading.Event()

    def cancel(self):
        """Request cancellation of current operation"""
        self._cancel_event.set()

    def clear_cancel(self):
        self._cancel_event.clear()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @abstractmethod
    def get_name(self) -> str:
        pass

    @abstractmethod
    def connect(self) -> bool:
        """Initialize protocol, enter programming mode if needed"""
        pass

    @abstractmethod
    def detect(self) -> Dict[str, Any]:
        """Detect target device, return device info"""
        pass

    @abstractmethod
    def read(self, memory_type: str = "flash", address: int = 0, length: int = None,
             progress_callback: Callable[[int, str], None] = None) -> bytes:
        """Read memory"""
        pass

    @abstractmethod
    def write(self, data: bytes, memory_type: str = "flash", address: int = 0,
              progress_callback: Callable[[int, str], None] = None) -> bool:
        """Write memory"""
        pass

    @abstractmethod
    def verify(self, data: bytes, memory_type: str = "flash", address: int = 0,
               progress_callback: Callable[[int, str], None] = None) -> Tuple[bool, Optional[Dict]]:
        """Verify memory against data, returns (success, mismatch_info)"""
        pass

    @abstractmethod
    def erase(self, memory_type: str = "all",
              progress_callback: Callable[[int, str], None] = None) -> bool:
        """Erase memory"""
        pass

    @abstractmethod
    def close(self):
        """Exit programming mode, cleanup"""
        pass

    def get_device_info(self) -> Optional[Dict[str, Any]]:
        return self.device_info

    def supports_memory_type(self, memory_type: str) -> bool:
        """Override in subclasses to list supported memory types"""
        return True
