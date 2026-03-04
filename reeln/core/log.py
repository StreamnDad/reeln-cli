"""Structured logging with JSON and human-readable formatters."""

from __future__ import annotations

import json
import logging
import sys
import traceback
from typing import ClassVar


class JsonFormatter(logging.Formatter):
    """Single-line JSON log formatter."""

    _BASE_KEYS: ClassVar[set[str]] = {
        "name",
        "msg",
        "args",
        "created",
        "relativeCreated",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "pathname",
        "filename",
        "module",
        "thread",
        "threadName",
        "process",
        "processName",
        "levelname",
        "levelno",
        "message",
        "msecs",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        output: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }
        # Include extra fields
        for key, value in record.__dict__.items():
            if key not in self._BASE_KEYS:
                output[key] = value
        if record.exc_info and record.exc_info[1] is not None:
            output["exception"] = traceback.format_exception(*record.exc_info)
        return json.dumps(output, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable log formatter: ``HH:MM:SS LEVEL name: message``."""

    def __init__(self) -> None:
        super().__init__(fmt="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")


def setup_logging(level: int = logging.INFO, log_format: str = "human") -> None:
    """Configure the root logger with the specified format.

    Clears existing handlers and writes to stderr.
    """
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(HumanFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
