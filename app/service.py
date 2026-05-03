from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.config import AppConfig
from app.google_client import fetch_google_day
from app.mbta import fetch_mbta
from app.models import DashboardPayload, SourceStatus
from app.render import render_dashboard
from app.weather import fetch_weather

logger = logging.getLogger(__name__)


class DashboardService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        now = self._now()
        self._payload = DashboardPayload(
            generated_at=now,
            statuses={
                "google": SourceStatus(ok=False, error="disabled"),
                "weather": SourceStatus(ok=False, error="disabled"),
                "mbta": SourceStatus(ok=False, error="disabled"),
            },
        )
        self._last_refresh: dict[str, float] = {}

    @property
    def payload(self) -> DashboardPayload:
        with self._lock:
            return self._payload

    @property
    def output_path(self) -> Path:
        return self.config.dashboard.output_path

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.refresh_all()
        self._thread = threading.Thread(target=self._run, name="dashboard-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def refresh_all(self) -> DashboardPayload:
        return self._refresh({"weather", "mbta", "google"})

    def refresh_due(self) -> DashboardPayload:
        due_sources = self._due_sources()
        if not due_sources:
            return self.payload
        return self._refresh(due_sources)

    def _refresh(self, source_names: Iterable[str]) -> DashboardPayload:
        sources = set(source_names)
        now = self._now()
        payload = self.payload
        data = {
            "calendar": payload.calendar,
            "tasks": payload.tasks,
            "weather": payload.weather,
            "mbta": payload.mbta,
            "statuses": dict(payload.statuses),
        }

        if "weather" in sources and self.config.weather.enabled:
            weather_data, status = self._capture(
                "weather", lambda: fetch_weather(self.config, now)
            )
            if status.ok:
                data["weather"] = weather_data
            data["statuses"]["weather"] = status
        if "mbta" in sources and self.config.mbta.enabled:
            data["mbta"], data["statuses"]["mbta"] = self._capture(
                "mbta", lambda: fetch_mbta(self.config.mbta, now)
            )
        if "google" in sources and self.config.google.enabled:
            google_data, status = self._capture(
                "google", lambda: fetch_google_day(self.config.google, now)
            )
            if status.ok:
                data["calendar"], data["tasks"] = google_data
            data["statuses"]["google"] = status

        refreshed = DashboardPayload(
            generated_at=now,
            calendar=data["calendar"],
            tasks=data["tasks"],
            weather=data["weather"],
            mbta=data["mbta"],
            statuses=data["statuses"],
        )
        with self._lock:
            self._payload = refreshed
        render_dashboard(refreshed, self.config)
        return refreshed

    def _run(self) -> None:
        while not self._stop.wait(5):
            self.refresh_due()

    def _due_sources(self) -> set[str]:
        now = time.monotonic()
        intervals = {
            "weather": self.config.weather.refresh_seconds if self.config.weather.enabled else None,
            "mbta": self.config.mbta.refresh_seconds if self.config.mbta.enabled else None,
            "google": self.config.google.refresh_seconds if self.config.google.enabled else None,
        }
        due_sources: set[str] = set()
        for name, interval in intervals.items():
            if interval is None:
                continue
            last = self._last_refresh.get(name, 0)
            if now - last >= interval:
                due_sources.add(name)
        return due_sources

    def _capture(self, name: str, fetcher: Callable[[], object]) -> tuple[object, SourceStatus]:
        self._last_refresh[name] = time.monotonic()
        try:
            value = fetcher()
            return value, SourceStatus(ok=True, updated_at=self._now())
        except Exception as exc:
            logger.exception("%s refresh failed", name)
            return {}, SourceStatus(ok=False, updated_at=self._now(), error=str(exc))

    def _now(self) -> datetime:
        return datetime.now(self.config.dashboard.tzinfo)
