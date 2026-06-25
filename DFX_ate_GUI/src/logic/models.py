"""Domain models for limits, parsed test steps, and result payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypedDict


@dataclass(frozen=True, slots=True)
class TestLimit:
    """Specification limits for a named test (legacy JSON-driven format)."""

    test_name: str
    min_val: float
    max_val: float
    unit: str


@dataclass(slots=True)
class TestStep:
    """One parsed step from a `.tst` script.

    `commands` is a list of `{"cmd": str, "args": list[str]}` dicts. A step
    with `min_val` / `max_val` set is a measured test; otherwise it is a
    setup/teardown block whose pass/fail is determined solely by whether all
    commands ran without raising.
    """

    name: str
    commands: list[dict] = field(default_factory=list)
    min_val: float | None = None
    max_val: float | None = None
    unit: str = ""
    is_critical: bool = False
    retry_count: int = 0  # extra attempts beyond the first

    @property
    def has_limits(self) -> bool:
        return self.min_val is not None and self.max_val is not None


@dataclass
class ScriptDocument:
    """Parsed script payload: preamble metadata and executable steps."""

    metadata: dict[str, str] = field(default_factory=dict)
    steps: list[TestStep] = field(default_factory=list)


class TestResultPayload(TypedDict):
    """Structured row data emitted from the test thread to the UI."""

    value: float
    min: float
    max: float
    unit: str
    passed: bool
    is_measurement: bool


_VALID_ROLES: frozenset[str] = frozenset({"Operator", "Technician", "Admin"})


def normalize_role(raw: str) -> str:
    """Normalize a role string to Title Case and validate it.

    Raises ValueError for unknown roles so callers get a single consistent
    error message without duplicating the role list.
    """
    normalized = raw.strip().title()
    if normalized not in _VALID_ROLES:
        raise ValueError(
            f"Invalid role {raw!r}. Expected one of: {', '.join(sorted(_VALID_ROLES))}"
        )
    return normalized


@dataclass
class TestRunRecord:
    """Final payload for one completed test run before database insertion."""

    operator: str
    part_number: str
    serial_number: str
    overall_passed: bool = True
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
