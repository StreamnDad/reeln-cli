"""Tests for bandwidth rate limiter and upload lock."""

from __future__ import annotations

import io
from unittest.mock import patch

from reeln.core.throttle import ThrottledReader, upload_lock

# ---------------------------------------------------------------------------
# ThrottledReader — no limit
# ---------------------------------------------------------------------------


def test_throttled_reader_no_limit() -> None:
    data = b"hello world"
    f = io.BytesIO(data)
    reader = ThrottledReader(f, max_kbps=0)
    assert reader.read() == data


def test_throttled_reader_negative_kbps_unlimited() -> None:
    data = b"hello world"
    f = io.BytesIO(data)
    reader = ThrottledReader(f, max_kbps=-100)
    assert reader.read() == data


# ---------------------------------------------------------------------------
# ThrottledReader — with limit
# ---------------------------------------------------------------------------


def test_throttled_reader_with_limit() -> None:
    data = b"x" * 1024  # 1 KB
    f = io.BytesIO(data)
    reader = ThrottledReader(f, max_kbps=10000)  # very high limit for fast test
    result = reader.read()
    assert result == data


def test_throttled_reader_sleeps_when_too_fast() -> None:
    """Verify the sleep branch triggers when reading faster than the rate limit."""
    data = b"x" * 1024
    f = io.BytesIO(data)
    # 1 KB/s means reading 1 KB should require ~1s; we mock sleep
    reader = ThrottledReader(f, max_kbps=1)
    with patch("reeln.core.throttle.time.sleep") as mock_sleep:
        result = reader.read()
    assert result == data
    mock_sleep.assert_called_once()
    # Should sleep for roughly 1 second (read was near-instant)
    sleep_time = mock_sleep.call_args[0][0]
    assert sleep_time > 0


def test_throttled_reader_no_sleep_when_slow_enough() -> None:
    """When enough time has elapsed, no sleep is needed."""
    data = b"x"  # tiny data
    f = io.BytesIO(data)
    # Very high limit: 1 byte at 1000000 KB/s => expected_time ~= 0
    reader = ThrottledReader(f, max_kbps=1000000)
    # Pretend init was 1s ago so elapsed >> expected_time
    reader._start_time = reader._start_time - 1.0
    with patch("reeln.core.throttle.time.sleep") as mock_sleep:
        result = reader.read()
    assert result == data
    mock_sleep.assert_not_called()


def test_throttled_reader_empty_read() -> None:
    f = io.BytesIO(b"")
    reader = ThrottledReader(f, max_kbps=100)
    assert reader.read() == b""


def test_throttled_reader_partial_reads() -> None:
    data = b"0123456789"
    f = io.BytesIO(data)
    reader = ThrottledReader(f, max_kbps=0)
    assert reader.read(5) == b"01234"
    assert reader.read(5) == b"56789"
    assert reader.read(5) == b""


# ---------------------------------------------------------------------------
# ThrottledReader — seek, tell, close, len
# ---------------------------------------------------------------------------


def test_throttled_reader_seek_resets_counters() -> None:
    data = b"hello world"
    f = io.BytesIO(data)
    reader = ThrottledReader(f, max_kbps=0)
    reader.read(5)
    reader.seek(0)
    assert reader.read() == data


def test_throttled_reader_tell() -> None:
    data = b"hello world"
    f = io.BytesIO(data)
    reader = ThrottledReader(f, max_kbps=0)
    assert reader.tell() == 0
    reader.read(5)
    assert reader.tell() == 5


def test_throttled_reader_close() -> None:
    f = io.BytesIO(b"data")
    reader = ThrottledReader(f, max_kbps=0)
    reader.close()
    assert f.closed


def test_throttled_reader_len() -> None:
    data = b"0123456789"
    f = io.BytesIO(data)
    reader = ThrottledReader(f, max_kbps=0)
    assert len(reader) == 10
    # Position preserved after len
    assert reader.tell() == 0


def test_throttled_reader_len_preserves_position() -> None:
    data = b"0123456789"
    f = io.BytesIO(data)
    reader = ThrottledReader(f, max_kbps=0)
    reader.read(3)
    assert reader.tell() == 3
    assert len(reader) == 10
    assert reader.tell() == 3


# ---------------------------------------------------------------------------
# upload_lock
# ---------------------------------------------------------------------------


def test_upload_lock_context_manager() -> None:
    with upload_lock(timeout=1.0):
        pass  # Should not raise


def test_upload_lock_no_filelock_fallback() -> None:
    """When filelock is not installed, upload_lock is a no-op."""
    import builtins

    real_import = builtins.__import__

    def mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "filelock":
            raise ImportError("no filelock")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import), upload_lock(timeout=1.0):
        pass  # Should not raise
