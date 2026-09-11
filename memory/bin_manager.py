"""
BIN Manager - Handles saving and loading binary files with validation
"""

import os
import hashlib
from typing import Tuple, Optional, Dict, Any


class BinManagerError(Exception):
    pass


class BinManager:
    """Handles BIN file operations"""

    def __init__(self):
        self.last_directory: str = os.path.expanduser("~")

    def calculate_hashes(self, data: bytes) -> Dict[str, str]:
        """Calculate SHA256, MD5, etc."""
        return {
            'sha256': hashlib.sha256(data).hexdigest(),
            'md5': hashlib.md5(data).hexdigest(),
            'sha1': hashlib.sha1(data).hexdigest(),
            'size': len(data),
            'crc32': f"{self._crc32(data):08X}"
        }

    @staticmethod
    def _crc32(data: bytes) -> int:
        import zlib
        return zlib.crc32(data) & 0xFFFFFFFF

    def save_bin(self, filepath: str, data: bytes, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Save binary data to file
        Returns file info dict
        """
        try:
            # Ensure directory exists
            directory = os.path.dirname(os.path.abspath(filepath))
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            # Check if file exists - caller should handle confirmation
            # But we can still write

            with open(filepath, 'wb') as f:
                f.write(data)

            self.last_directory = directory

            hashes = self.calculate_hashes(data)

            info = {
                'filepath': filepath,
                'size': len(data),
                'directory': directory,
                **hashes
            }

            if metadata:
                info.update(metadata)

            return info

        except Exception as e:
            raise BinManagerError(f"Failed to save {filepath}: {e}") from e

    def load_bin(self, filepath: str, max_size: int = 16*1024*1024) -> Tuple[bytes, Dict[str, Any]]:
        """
        Load binary file
        Returns (data, info)
        Validates size
        """
        try:
            if not os.path.exists(filepath):
                raise BinManagerError(f"File not found: {filepath}")

            file_size = os.path.getsize(filepath)

            if file_size > max_size:
                raise BinManagerError(f"File too large: {file_size} bytes (max {max_size})")

            if file_size == 0:
                raise BinManagerError("File is empty")

            with open(filepath, 'rb') as f:
                data = f.read()

            self.last_directory = os.path.dirname(os.path.abspath(filepath))

            hashes = self.calculate_hashes(data)

            info = {
                'filepath': filepath,
                'size': len(data),
                'directory': self.last_directory,
                **hashes
            }

            return data, info

        except BinManagerError:
            raise
        except Exception as e:
            raise BinManagerError(f"Failed to load {filepath}: {e}") from e

    def validate_size(self, data: bytes, target_size: int, allow_smaller: bool = True) -> Tuple[bool, str]:
        """
        Validate data size against target memory size
        Returns (is_valid, message)
        """
        data_len = len(data)

        if data_len > target_size:
            return False, f"File size {data_len} bytes exceeds target size {target_size} bytes ({data_len - target_size} bytes too large). Will NOT truncate."

        if data_len < target_size and not allow_smaller:
            return False, f"File size {data_len} bytes is smaller than target size {target_size} bytes"

        if data_len < target_size:
            return True, f"File size {data_len} bytes is smaller than target {target_size} bytes. Remaining {target_size - data_len} bytes will be left as 0xFF or unwritten depending on protocol."

        return True, f"File size {data_len} bytes matches target size"

    def compare_bins(self, data_a: bytes, data_b: bytes) -> Dict[str, Any]:
        """Compare two binary dumps"""
        len_a = len(data_a)
        len_b = len(data_b)
        min_len = min(len_a, len_b)

        diff_count = 0
        first_mismatch = None
        last_mismatch = None
        differences = []  # List of (address, byte_a, byte_b)

        for i in range(min_len):
            if data_a[i] != data_b[i]:
                diff_count += 1
                if first_mismatch is None:
                    first_mismatch = i
                last_mismatch = i
                # Store first 100 differences for display
                if len(differences) < 100:
                    differences.append((i, data_a[i], data_b[i]))

        # If lengths differ, count extra bytes as differences
        if len_a != len_b:
            extra = abs(len_a - len_b)
            diff_count += extra
            if first_mismatch is None:
                first_mismatch = min_len
            last_mismatch = max(len_a, len_b) - 1

        return {
            'same': diff_count == 0 and len_a == len_b,
            'diff_count': diff_count,
            'len_a': len_a,
            'len_b': len_b,
            'first_mismatch': first_mismatch,
            'last_mismatch': last_mismatch,
            'differences': differences,
            'size_match': len_a == len_b
        }
