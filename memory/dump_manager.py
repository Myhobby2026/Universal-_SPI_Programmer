"""
Dump Manager - Manages in-memory buffers for different memory types
"""

import threading
from typing import Dict, Optional, Any
import hashlib


class DumpManager:
    """Manages memory dumps for different memory regions"""

    def __init__(self):
        self._dumps: Dict[str, bytes] = {}  # memory_type -> data
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def set_dump(self, memory_type: str, data: bytes, metadata: Dict[str, Any] = None):
        """Store a dump"""
        with self._lock:
            self._dumps[memory_type] = bytes(data)  # copy
            if metadata:
                self._metadata[memory_type] = dict(metadata)
            else:
                # Auto-generate metadata
                self._metadata[memory_type] = {
                    'size': len(data),
                    'sha256': hashlib.sha256(data).hexdigest(),
                    'md5': hashlib.md5(data).hexdigest(),
                }

    def get_dump(self, memory_type: str) -> Optional[bytes]:
        with self._lock:
            return self._dumps.get(memory_type)

    def has_dump(self, memory_type: str) -> bool:
        with self._lock:
            return memory_type in self._dumps

    def get_metadata(self, memory_type: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._metadata.get(memory_type)

    def get_all_types(self):
        with self._lock:
            return list(self._dumps.keys())

    def clear(self, memory_type: str = None):
        with self._lock:
            if memory_type:
                self._dumps.pop(memory_type, None)
                self._metadata.pop(memory_type, None)
            else:
                self._dumps.clear()
                self._metadata.clear()

    def get_size(self, memory_type: str) -> int:
        with self._lock:
            data = self._dumps.get(memory_type)
            return len(data) if data else 0

    def get_sha256(self, memory_type: str) -> Optional[str]:
        with self._lock:
            meta = self._metadata.get(memory_type)
            if meta and 'sha256' in meta:
                return meta['sha256']
            data = self._dumps.get(memory_type)
            if data:
                return hashlib.sha256(data).hexdigest()
            return None

    def get_combined_info(self) -> Dict[str, Any]:
        """Get summary of all dumps"""
        with self._lock:
            info = {}
            for mem_type, data in self._dumps.items():
                meta = self._metadata.get(mem_type, {})
                info[mem_type] = {
                    'size': len(data),
                    'sha256': meta.get('sha256', hashlib.sha256(data).hexdigest()[:16] + "..."),
                    'has_data': True
                }
            return info
