from __future__ import annotations

from datetime import datetime
from typing import Any

import requests
from dateutil.parser import isoparse

from app.config import MbtaConfig

MBTA_BASE_URL = "https://api-v3.mbta.com"


def fetch_mbta(config: MbtaConfig, now: datetime) -> dict[str, Any]:
    direction_stop_ids = config.direction_stop_ids
    if not direction_stop_ids or not config.route_id:
        raise RuntimeError("mbta.route_id and mbta.stop_ids are required")

    route = _get_json(f"{MBTA_BASE_URL}/routes/{config.route_id}", config.api_key)
    direction_names = route.get("data", {}).get("attributes", {}).get("direction_names") or []

    predictions = _fetch_predictions(config, direction_stop_ids)
    schedules: dict[int, list[dict[str, Any]]] | None = None

    directions: list[dict[str, Any]] = []
    for direction_id, stop_id in direction_stop_ids.items():
        label = (
            direction_names[direction_id]
            if direction_id < len(direction_names)
            else f"Direction {direction_id}"
        )
        upcoming = _upcoming_arrivals(
            predictions.get(direction_id, []), now, config.arrivals_per_direction
        )
        if not upcoming:
            if schedules is None:
                schedules = _fetch_schedules(config, direction_stop_ids)
            upcoming = _upcoming_arrivals(
                schedules.get(direction_id, []), now, config.arrivals_per_direction
            )
        directions.append(
            {
                "direction_id": direction_id,
                "stop_id": stop_id,
                "name": label,
                "arrivals": [_format_arrival(item, now) for item in upcoming],
            }
        )

    return {
        "route_id": config.route_id,
        "stop_id": config.stop_id,
        "stop_ids": direction_stop_ids,
        "directions": directions,
    }


def _fetch_predictions(
    config: MbtaConfig,
    direction_stop_ids: dict[int, str],
) -> dict[int, list[dict[str, Any]]]:
    return _fetch_arrivals(config, direction_stop_ids, endpoint="predictions", source="prediction")


def _fetch_schedules(
    config: MbtaConfig,
    direction_stop_ids: dict[int, str],
) -> dict[int, list[dict[str, Any]]]:
    return _fetch_arrivals(config, direction_stop_ids, endpoint="schedules", source="schedule")


def _fetch_arrivals(
    config: MbtaConfig,
    direction_stop_ids: dict[int, str],
    endpoint: str,
    source: str,
) -> dict[int, list[dict[str, Any]]]:
    arrivals: dict[int, list[dict[str, Any]]] = {direction_id: [] for direction_id in direction_stop_ids}
    for direction_id, stop_id in direction_stop_ids.items():
        response = _get_json(
            f"{MBTA_BASE_URL}/{endpoint}",
            config.api_key,
            params={
                "filter[stop]": stop_id,
                "filter[route]": config.route_id,
                "sort": "departure_time",
                "include": "trip,stop,route",
            },
        )
        grouped = _group_arrival_data(response.get("data", []), source=source)
        arrivals[direction_id].extend(grouped.get(direction_id, []))
    return arrivals


def _get_json(
    url: str,
    api_key: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/vnd.api+json"}
    if api_key:
        headers["x-api-key"] = api_key
    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _group_arrival_data(items: list[dict[str, Any]], source: str) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        attributes = item.get("attributes", {})
        direction_id = attributes.get("direction_id")
        if direction_id is None:
            continue
        grouped.setdefault(int(direction_id), []).append(
            {
                "arrival_at": attributes.get("arrival_time"),
                "departure_at": attributes.get("departure_time"),
                "status": attributes.get("status") or "",
                "source": source,
            }
        )
    return grouped


def _upcoming_arrivals(
    arrivals: list[dict[str, Any]],
    now: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    sorted_arrivals = sorted(
        arrivals,
        key=lambda item: item["arrival_at"] or item["departure_at"] or "",
    )
    return [
        item
        for item in sorted_arrivals
        if item["arrival_at"] or item["departure_at"]
        if _parse_time(item["arrival_at"] or item["departure_at"], now) >= now
    ][:limit]


def _format_arrival(item: dict[str, Any], now: datetime) -> dict[str, Any]:
    when = _parse_time(item["arrival_at"] or item["departure_at"], now)
    minutes = max(0, round((when - now).total_seconds() / 60))
    return {
        "time": when.strftime("%-I:%M %p"),
        "minutes": minutes,
        "status": item["status"],
        "source": item["source"],
    }


def _parse_time(value: str | None, now: datetime) -> datetime:
    if not value:
        return now
    return isoparse(value).astimezone(now.tzinfo)
