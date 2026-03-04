"""Tests for structured logging module."""

from __future__ import annotations

import json
import logging

from reeln.core.log import HumanFormatter, JsonFormatter, get_logger, setup_logging


def test_json_formatter_basic() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="hello", args=(), exc_info=None
    )
    output = formatter.format(record)
    data = json.loads(output)
    assert data["level"] == "INFO"
    assert data["logger"] == "test"
    assert data["message"] == "hello"
    assert "timestamp" in data


def test_json_formatter_extra_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="hello", args=(), exc_info=None
    )
    record.correlation_id = "abc-123"  # type: ignore[attr-defined]
    output = formatter.format(record)
    data = json.loads(output)
    assert data["correlation_id"] == "abc-123"


def test_json_formatter_exception() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="", lineno=0, msg="fail", args=(), exc_info=exc_info
    )
    output = formatter.format(record)
    data = json.loads(output)
    assert "exception" in data
    assert any("ValueError" in line for line in data["exception"])


def test_human_formatter() -> None:
    formatter = HumanFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="hello", args=(), exc_info=None
    )
    output = formatter.format(record)
    assert "INFO" in output
    assert "test" in output
    assert "hello" in output


def test_setup_logging_human() -> None:
    setup_logging(log_format="human")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, HumanFormatter)


def test_setup_logging_json() -> None:
    setup_logging(log_format="json")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_setup_logging_replaces_handlers() -> None:
    setup_logging(log_format="human")
    setup_logging(log_format="json")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_setup_logging_level() -> None:
    setup_logging(level=logging.DEBUG, log_format="human")
    root = logging.getLogger()
    assert root.level == logging.DEBUG


def test_get_logger() -> None:
    logger = get_logger("reeln.test")
    assert logger.name == "reeln.test"
    assert isinstance(logger, logging.Logger)
