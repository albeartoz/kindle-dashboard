from __future__ import annotations

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

    points = _get_json(f"{NWS_BASE_URL}/points/{lat:.4f},{lon:.4f}", headers)
    properties = points["properties"]
    hourly = _get_json(properties["forecastHourly"], headers)
    daily = _get_json(properties["forecast"], headers)
    alerts = _get_json(f"{NWS_BASE_URL}/alerts/active?point={lat:.4f},{lon:.4f}", headers)

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


def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


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
