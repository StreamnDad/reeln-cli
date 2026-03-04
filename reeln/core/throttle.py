"""Bandwidth rate limiter and upload lock for plugin uploads."""

from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO

from reeln.core.config import data_dir


def _upload_lock_path() -> Path:
    """Return the path to the upload lock file."""
    lock_dir = data_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / ".upload.lock"


@contextmanager
def upload_lock(timeout: float = 600.0) -> Any:
    """Acquire a file lock for sequential uploads.

    Gracefully no-ops if ``filelock`` is not installed.
    """
    try:
        from filelock import FileLock
    except ImportError:
        yield
        return

    lock = FileLock(str(_upload_lock_path()), timeout=timeout)
    with lock:
        yield


class ThrottledReader:
    """File-like wrapper that limits read throughput to *max_kbps* KB/s.

    When *max_kbps* is ``0`` or negative, reads are unrestricted.
    """

    def __init__(self, fileobj: BinaryIO, max_kbps: int = 0) -> None:
        self._fileobj = fileobj
        self._max_bytes_per_sec = max_kbps * 1024 if max_kbps > 0 else 0
        self._bytes_read = 0
        self._start_time = time.monotonic()

    def read(self, size: int = -1) -> bytes:
        """Read up to *size* bytes, sleeping to maintain the rate limit."""
        data = self._fileobj.read(size)
        if not data or self._max_bytes_per_sec <= 0:
            return data
        self._bytes_read += len(data)
        expected_time = self._bytes_read / self._max_bytes_per_sec
        elapsed = time.monotonic() - self._start_time
        if elapsed < expected_time:
            time.sleep(expected_time - elapsed)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        """Seek and reset rate-limiter counters."""
        result = self._fileobj.seek(offset, whence)
        self._bytes_read = 0
        self._start_time = time.monotonic()
        return result

    def tell(self) -> int:
        """Return the current file position."""
        return self._fileobj.tell()

    def close(self) -> None:
        """Close the underlying file object."""
        self._fileobj.close()

    def __len__(self) -> int:
        """Return the total file size without moving the read position."""
        pos = self._fileobj.tell()
        self._fileobj.seek(0, 2)
        length = self._fileobj.tell()
        self._fileobj.seek(pos)
        return length
