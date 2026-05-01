#!/usr/bin/env python
from __future__ import annotations

import os
import sys
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_config

MBTA_BASE_URL = "https://api-v3.mbta.com"


def main() -> None:
    config = load_config()
    if config.home.latitude is None or config.home.longitude is None:
        raise SystemExit("Set home.latitude and home.longitude in config.yaml first.")

    headers = {"Accept": "application/vnd.api+json"}
    api_key = os.getenv(config.mbta.api_key_env, "")
    if api_key:
        headers["x-api-key"] = api_key

    response = requests.get(
        f"{MBTA_BASE_URL}/stops",
        headers=headers,
        params={
            "filter[latitude]": config.home.latitude,
            "filter[longitude]": config.home.longitude,
            "filter[radius]": 0.75,
            "filter[route_type]": "0,1,2",
            "include": "route",
            "sort": "distance",
        },
        timeout=15,
    )
    response.raise_for_status()
    stops = response.json().get("data", [])
    for stop in stops[:20]:
        attrs = stop.get("attributes", {})
        distance = _distance_miles(
            config.home.latitude,
            config.home.longitude,
            attrs.get("latitude"),
            attrs.get("longitude"),
        )
        routes = ", ".join(_routes_for_stop(stop["id"], headers)[:6])
        print(f"{stop['id']:18} {distance:0.2f} mi  {attrs.get('name', '')}  [{routes}]")


def _routes_for_stop(stop_id: str, headers: dict[str, str]) -> list[str]:
    response = requests.get(
        f"{MBTA_BASE_URL}/routes",
        headers=headers,
        params={"filter[stop]": stop_id},
        timeout=15,
    )
    response.raise_for_status()
    return [route["id"] for route in response.json().get("data", [])]


def _distance_miles(lat1: float, lon1: float, lat2: float | None, lon2: float | None) -> float:
    if lat2 is None or lon2 is None:
        return 0
    earth_radius_miles = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return earth_radius_miles * 2 * atan2(sqrt(a), sqrt(1 - a))


if __name__ == "__main__":
    main()
