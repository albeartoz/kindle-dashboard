from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml


@dataclass(frozen=True, slots=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8787


@dataclass(frozen=True, slots=True)
class DashboardConfig:
    width: int = 600
    height: int = 800
    timezone: str = "America/New_York"
    title: str = "Home"
    output_path: Path = Path("data/dashboard.png")

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass(frozen=True, slots=True)
class HomeConfig:
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True, slots=True)
class WeatherConfig:
    enabled: bool = True
    refresh_seconds: int = 1800
    api_key_env: str = "OPENWEATHER_API_KEY"
    request_timeout_seconds: float = 20.0

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "")


@dataclass(frozen=True, slots=True)
class GoogleConfig:
    enabled: bool = False
    refresh_seconds: int = 600
    client_secret_file: Path = Path("data/client_secret.json")
    token_file: Path = Path("data/token.json")
    calendar_ids: list[str] = field(default_factory=lambda: ["primary"])
    task_list_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MbtaConfig:
    enabled: bool = False
    refresh_seconds: int = 45
    api_key_env: str = "MBTA_API_KEY"
    stop_id: str = ""
    stop_ids: dict[int, str] = field(default_factory=dict)
    route_id: str = ""
    direction_ids: list[int] = field(default_factory=lambda: [0, 1])
    arrivals_per_direction: int = 2

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "")

    @property
    def direction_stop_ids(self) -> dict[int, str]:
        if self.stop_ids:
            return {
                direction_id: self.stop_ids[direction_id]
                for direction_id in self.direction_ids
                if direction_id in self.stop_ids and self.stop_ids[direction_id]
            }
        if self.stop_id:
            return {direction_id: self.stop_id for direction_id in self.direction_ids}
        return {}


@dataclass(frozen=True, slots=True)
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    home: HomeConfig = field(default_factory=HomeConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    mbta: MbtaConfig = field(default_factory=MbtaConfig)


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    return value if isinstance(value, dict) else {}


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _string_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return default
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _int_string_dict(value: Any) -> dict[int, str]:
    if not isinstance(value, dict):
        return {}
    return {int(key): str(item) for key, item in value.items() if item is not None}


def load_config(path: str | os.PathLike[str] | None = None) -> AppConfig:
    defaults = AppConfig()
    config_path = Path(path or os.getenv("KINDLE_DASHBOARD_CONFIG", "config.yaml"))
    raw: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                raw = loaded

    server = _section(raw, "server")
    dashboard = _section(raw, "dashboard")
    home = _section(raw, "home")
    weather = _section(raw, "weather")
    google = _section(raw, "google")
    mbta = _section(raw, "mbta")

    return AppConfig(
        server=ServerConfig(
            host=str(server.get("host", defaults.server.host)),
            port=int(server.get("port", defaults.server.port)),
        ),
        dashboard=DashboardConfig(
            width=int(dashboard.get("width", defaults.dashboard.width)),
            height=int(dashboard.get("height", defaults.dashboard.height)),
            timezone=str(dashboard.get("timezone", defaults.dashboard.timezone)),
            title=str(dashboard.get("title", defaults.dashboard.title)),
            output_path=_path(dashboard.get("output_path", defaults.dashboard.output_path)),
        ),
        home=HomeConfig(
            latitude=_optional_float(home.get("latitude")),
            longitude=_optional_float(home.get("longitude")),
        ),
        weather=WeatherConfig(
            enabled=bool(weather.get("enabled", defaults.weather.enabled)),
            refresh_seconds=int(weather.get("refresh_seconds", defaults.weather.refresh_seconds)),
            api_key_env=str(weather.get("api_key_env", defaults.weather.api_key_env)),
            request_timeout_seconds=float(
                weather.get(
                    "request_timeout_seconds",
                    defaults.weather.request_timeout_seconds,
                )
            ),
        ),
        google=GoogleConfig(
            enabled=bool(google.get("enabled", defaults.google.enabled)),
            refresh_seconds=int(google.get("refresh_seconds", defaults.google.refresh_seconds)),
            client_secret_file=_path(
                google.get("client_secret_file", defaults.google.client_secret_file)
            ),
            token_file=_path(google.get("token_file", defaults.google.token_file)),
            calendar_ids=_string_list(google.get("calendar_ids"), defaults.google.calendar_ids),
            task_list_ids=_string_list(google.get("task_list_ids"), defaults.google.task_list_ids),
        ),
        mbta=MbtaConfig(
            enabled=bool(mbta.get("enabled", defaults.mbta.enabled)),
            refresh_seconds=int(mbta.get("refresh_seconds", defaults.mbta.refresh_seconds)),
            api_key_env=str(mbta.get("api_key_env", defaults.mbta.api_key_env)),
            stop_id=str(mbta.get("stop_id", defaults.mbta.stop_id)),
            stop_ids=_int_string_dict(mbta.get("stop_ids", defaults.mbta.stop_ids)),
            route_id=str(mbta.get("route_id", defaults.mbta.route_id)),
            direction_ids=[
                int(value) for value in mbta.get("direction_ids", defaults.mbta.direction_ids)
            ],
            arrivals_per_direction=int(
                mbta.get("arrivals_per_direction", defaults.mbta.arrivals_per_direction)
            ),
        ),
    )
