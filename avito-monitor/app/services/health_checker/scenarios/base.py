"""Common types for health-check scenarios."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ScenarioStatus = Literal["pass", "fail", "skip"]


@dataclass
class ScenarioResult:
    """Outcome of a single scenario run, persisted as a row in ``health_checks``."""

    scenario: str  # "A".."F"
    status: ScenarioStatus
    latency_ms: int
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "details": self.details,
        }
