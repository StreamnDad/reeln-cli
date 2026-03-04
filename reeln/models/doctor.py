"""Data structures for health check diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class CheckStatus(Enum):
    """Outcome status for a single health check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    """Result of a single health check."""

    name: str
    status: CheckStatus
    message: str
    hint: str = ""


class DoctorCheck(Protocol):
    """Extension point for plugin-contributed health checks."""

    name: str

    def run(self) -> list[CheckResult]: ...
