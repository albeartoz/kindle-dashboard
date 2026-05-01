from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SourceStatus:
    ok: bool
    updated_at: datetime | None = None
    error: str | None = None


@dataclass(slots=True)
class DashboardPayload:
    generated_at: datetime
    calendar: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    weather: dict[str, Any] = field(default_factory=dict)
    mbta: dict[str, Any] = field(default_factory=dict)
    statuses: dict[str, SourceStatus] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "calendar": self.calendar,
            "tasks": self.tasks,
            "weather": self.weather,
            "mbta": self.mbta,
            "statuses": {
                name: {
                    "ok": status.ok,
                    "updated_at": status.updated_at.isoformat() if status.updated_at else None,
                    "error": status.error,
                }
                for name, status in self.statuses.items()
            },
        }

