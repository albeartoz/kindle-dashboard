from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any

import requests
from dateutil.parser import isoparse

from app.config import AppConfig

NWS_BASE_URL = "https://api.weather.gov"


def fetch_weather(config: AppConfig, now: datetime) -> dict[str, Any]:
    if config.home.latitude is None or config.home.longitude is None:
        raise RuntimeError("home.latitude and home.longitude are required for weather")

    headers = {
        "Accept": "application/geo+json",
        "User-Agent": config.weather.user_agent,
    }
    lat = config.home.latitude
    lon = config.home.longitude
    timeout_seconds = config.weather.request_timeout_seconds

    points = _get_json(f"{NWS_BASE_URL}/points/{lat:.4f},{lon:.4f}", headers, timeout_seconds)
    properties = points["properties"]
    hourly = _get_json(properties["forecastHourly"], headers, timeout_seconds)
    daily = _get_json(properties["forecast"], headers, timeout_seconds)
    alerts = _fetch_alerts(headers, lat, lon, timeout_seconds)

    current_period = _first_current_or_future(hourly["properties"].get("periods", []), now)
    daily_periods = daily["properties"].get("periods", [])
    today_periods = daily_periods[:2]
    alert_features = alerts.get("features", [])

    return {
        "current": _period_summary(current_period) if current_period else {},
        "today": [_period_summary(period) for period in today_periods],
        "daily_range": _daily_temperature_range(daily_periods, now),
        "alerts": [
            feature.get("properties", {}).get("event", "Weather alert")
            for feature in alert_features[:3]
        ],
    }


def _fetch_alerts(
    headers: dict[str, str],
    lat: float,
    lon: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        return _get_json(
            f"{NWS_BASE_URL}/alerts/active?point={lat:.4f},{lon:.4f}",
            headers,
            timeout_seconds,
        )
    except RuntimeError:
        return {"features": []}


def _get_json(
    url: str,
    headers: dict[str, str],
    timeout_seconds: float,
    attempts: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, headers=headers, timeout=(5, timeout_seconds))
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


def _first_current_or_future(periods: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    for period in periods:
        start = isoparse(period["startTime"]).astimezone(now.tzinfo)
        end = isoparse(period["endTime"]).astimezone(now.tzinfo)
        if start <= now <= end or start >= now:
            return period
    return periods[0] if periods else None


def _period_summary(period: dict[str, Any]) -> dict[str, Any]:
    precipitation = period.get("probabilityOfPrecipitation", {}) or {}
    return {
        "name": period.get("name", ""),
        "temperature": period.get("temperature"),
        "temperature_unit": period.get("temperatureUnit", "F"),
        "wind_speed": period.get("windSpeed", ""),
        "wind_direction": period.get("windDirection", ""),
        "short_forecast": period.get("shortForecast", ""),
        "precipitation": precipitation.get("value"),
    }


def _daily_temperature_range(periods: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    today = now.date()
    today_periods = [
        period
        for period in periods
        if _period_overlaps_date(period, today, now)
        and period.get("temperature") is not None
    ]
    if not today_periods:
        return {}

    daytime_temps = [
        period["temperature"] for period in today_periods if period.get("isDaytime") is True
    ]
    nighttime_temps = [
        period["temperature"] for period in today_periods if period.get("isDaytime") is False
    ]
    all_temps = [period["temperature"] for period in today_periods]
    unit = today_periods[0].get("temperatureUnit", "F")
    return {
        "high": max(daytime_temps or all_temps),
        "low": min(nighttime_temps or all_temps),
        "temperature_unit": unit,
    }


def _period_overlaps_date(period: dict[str, Any], target_date: date, now: datetime) -> bool:
    start = isoparse(period["startTime"]).astimezone(now.tzinfo)
    end = isoparse(period["endTime"]).astimezone(now.tzinfo)
    return start.date() <= target_date <= end.date()
