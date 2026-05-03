from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import requests

from app.config import AppConfig

OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_UNITS = "imperial"


def fetch_weather(config: AppConfig, _now: datetime) -> dict[str, Any]:
    if config.home.latitude is None or config.home.longitude is None:
        raise RuntimeError("home.latitude and home.longitude are required for weather")
    if not config.weather.api_key_env:
        raise RuntimeError(f"{config.weather.api_key_env} is required for weather")

    response = _get_json(
        OPENWEATHER_CURRENT_URL,
        params={
            "lat": f"{config.home.latitude:.4f}",
            "lon": f"{config.home.longitude:.4f}",
            "appid": config.weather.api_key_env,
            "units": OPENWEATHER_UNITS,
        },
        timeout_seconds=config.weather.request_timeout_seconds,
    )
    return _weather_summary(response)


def _get_json(
    url: str,
    params: dict[str, str],
    timeout_seconds: float,
    attempts: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None
    headers = {"Accept": "application/json"}
    for attempt in range(attempts):
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=(5, timeout_seconds),
            )
            if response.status_code >= 500 and attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
        except requests.HTTPError as exc:
            last_error = exc
            if exc.response is not None and exc.response.status_code >= 500 and attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise RuntimeError(f"Weather API request failed: {exc}") from exc

    raise RuntimeError(f"Weather API timed out after {attempts} attempts") from last_error


def _weather_summary(payload: dict[str, Any]) -> dict[str, Any]:
    main = payload.get("main") or {}
    weather = payload.get("weather") or []
    wind = payload.get("wind") or {}
    description = ""
    if isinstance(weather, list) and weather and isinstance(weather[0], dict):
        description = str(weather[0].get("description", ""))
    elif isinstance(weather, dict):
        description = str(weather.get("description", ""))

    return {
        "current": {
            "temperature": main.get("temp"),
            "temperature_unit": "F",
            "short_forecast": description,
            "wind_speed": _wind_speed(wind),
            "wind_direction": _wind_direction(wind),
        },
        "today": [],
        "daily_range": {
            "high": main.get("temp_max"),
            "low": main.get("temp_min"),
            "temperature_unit": "F",
        },
        "alerts": [],
    }


def _wind_speed(wind: dict[str, Any]) -> str:
    speed = wind.get("speed")
    if speed is None:
        return ""
    return f"{speed} mph"


def _wind_direction(wind: dict[str, Any]) -> str:
    degrees = wind.get("deg")
    if degrees is None:
        return ""
    compass_points = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    index = round(float(degrees) / 22.5) % len(compass_points)
    return compass_points[index]
