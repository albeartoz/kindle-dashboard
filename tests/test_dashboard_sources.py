from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import requests
from PIL import Image

from app.config import (
    AppConfig,
    DashboardConfig,
    GoogleConfig,
    HomeConfig,
    MbtaConfig,
    WeatherConfig,
    load_config,
)
from app.google_client import _calendar_items, fetch_google_day
from app.mbta import fetch_mbta
from app.models import DashboardPayload, SourceStatus
from app.render import render_dashboard
from app.service import DashboardService
from app.weather import _daily_temperature_range, _get_json, fetch_weather


class ConfigTests(unittest.TestCase):
    def test_load_config_uses_defaults_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(Path(tmp) / "missing.yaml")

        self.assertEqual(config.server.host, "0.0.0.0")
        self.assertEqual(config.server.port, 8787)
        self.assertEqual(config.dashboard.output_path, Path("data/dashboard.png"))
        self.assertEqual(config.google.calendar_ids, ["primary"])
        self.assertEqual(config.mbta.direction_ids, [0, 1])

    def test_load_config_parses_mbta_stop_ids_by_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "mbta:",
                        "  route_id: Red",
                        "  stop_ids:",
                        "    0: place-north",
                        "    1: place-south",
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)

        self.assertEqual(config.mbta.stop_ids, {0: "place-north", 1: "place-south"})
        self.assertEqual(
            config.mbta.direction_stop_ids,
            {0: "place-north", 1: "place-south"},
        )


class FakeRequest:
    def __init__(self, response: dict) -> None:
        self.response = response

    def execute(self) -> dict:
        return self.response


class FakeListResource:
    def __init__(self, pages: dict[str, dict]) -> None:
        self.pages = pages
        self.calls: list[dict] = []

    def list(self, **params) -> FakeRequest:
        self.calls.append(params)
        token = params.get("pageToken", "")
        return FakeRequest(self.pages[token])


class FakeCalendarService:
    def __init__(self, events: FakeListResource) -> None:
        self._events = events

    def events(self) -> FakeListResource:
        return self._events


class FakeTasksService:
    def __init__(self, tasklists: FakeListResource, tasks: FakeListResource) -> None:
        self._tasklists = tasklists
        self._tasks = tasks

    def tasklists(self) -> FakeListResource:
        return self._tasklists

    def tasks(self) -> FakeListResource:
        return self._tasks


class FakeWeatherResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code < 400:
            return
        error = requests.HTTPError("weather api error")
        error.response = self
        raise error


class GoogleClientTests(unittest.TestCase):
    def test_calendar_items_follows_next_page_token(self) -> None:
        events_resource = FakeListResource(
            {
                "": {"items": [{"summary": "First"}], "nextPageToken": "next"},
                "next": {"items": [{"summary": "Second"}]},
            }
        )
        service = FakeCalendarService(events_resource)
        now = datetime(2026, 5, 1, 9, tzinfo=ZoneInfo("America/New_York"))

        items = _calendar_items(service, "primary", now, now + timedelta(days=1))

        self.assertEqual([item["summary"] for item in items], ["First", "Second"])
        self.assertEqual(events_resource.calls[1]["pageToken"], "next")

    def test_fetch_google_day_filters_tasks_by_local_due_date(self) -> None:
        calendar_service = FakeCalendarService(FakeListResource({"": {"items": []}}))
        tasklists_resource = FakeListResource({"": {"items": [{"id": "default"}]}})
        tasks_resource = FakeListResource(
            {
                "": {
                    "items": [
                        {"title": "Today", "due": "2026-05-01T00:00:00.000Z"},
                        {"title": "Tomorrow", "due": "2026-05-02T00:00:00.000Z"},
                    ]
                }
            }
        )
        tasks_service = FakeTasksService(tasklists_resource, tasks_resource)
        config = GoogleConfig(enabled=True)
        now = datetime(2026, 5, 1, 9, tzinfo=ZoneInfo("America/New_York"))

        with (
            patch("app.google_client._load_or_create_credentials", return_value=object()),
            patch("app.google_client.build", side_effect=[calendar_service, tasks_service]),
        ):
            events, tasks = fetch_google_day(config, now)

        self.assertEqual(events, [])
        self.assertEqual([task["title"] for task in tasks], ["Today"])
        self.assertEqual(tasks_resource.calls[0]["dueMin"], "2026-05-01T00:00:00Z")
        self.assertEqual(tasks_resource.calls[0]["dueMax"], "2026-05-02T00:00:00Z")


class MbtaClientTests(unittest.TestCase):
    def test_fetch_mbta_queries_configured_stop_id_per_direction(self) -> None:
        now = datetime(2026, 5, 1, 9, tzinfo=ZoneInfo("America/New_York"))
        route_response = {
            "data": {
                "attributes": {
                    "direction_names": ["Northbound", "Southbound"],
                    "direction_destinations": ["Alewife", "Ashmont/Braintree"],
                }
            }
        }
        north_prediction = {
            "data": [
                {
                    "attributes": {
                        "direction_id": 0,
                        "arrival_time": "2026-05-01T09:05:00-04:00",
                        "departure_time": None,
                        "status": "",
                    }
                }
            ]
        }
        south_prediction = {
            "data": [
                {
                    "attributes": {
                        "direction_id": 1,
                        "arrival_time": "2026-05-01T09:07:00-04:00",
                        "departure_time": None,
                        "status": "",
                    }
                }
            ]
        }
        config = MbtaConfig(
            route_id="Red",
            stop_ids={0: "place-north", 1: "place-south"},
        )

        with patch(
            "app.mbta._get_json",
            side_effect=[route_response, north_prediction, south_prediction],
        ) as get_json:
            payload = fetch_mbta(config, now)

        self.assertEqual(
            get_json.call_args_list[1].kwargs["params"]["filter[stop]"],
            "place-north",
        )
        self.assertEqual(
            get_json.call_args_list[2].kwargs["params"]["filter[stop]"],
            "place-south",
        )
        self.assertEqual(payload["directions"][0]["stop_id"], "place-north")
        self.assertEqual(payload["directions"][1]["stop_id"], "place-south")
        self.assertEqual(payload["directions"][0]["terminal"], "Alewife")
        self.assertEqual(payload["directions"][1]["terminal"], "Ashmont/Braintree")
        self.assertEqual(payload["directions"][0]["arrivals"][0]["minutes"], 5)
        self.assertEqual(payload["directions"][1]["arrivals"][0]["minutes"], 7)

    def test_fetch_mbta_falls_back_to_schedules_per_missing_direction(self) -> None:
        now = datetime(2026, 5, 1, 9, tzinfo=ZoneInfo("America/New_York"))
        future_prediction = {
            "arrival_at": "2026-05-01T09:05:00-04:00",
            "departure_at": None,
            "status": "",
            "source": "prediction",
        }
        future_schedule = {
            "arrival_at": "2026-05-01T09:10:00-04:00",
            "departure_at": None,
            "status": "",
            "source": "schedule",
        }
        config = MbtaConfig(stop_id="place-test", route_id="Red", direction_ids=[0, 1])

        with (
            patch(
                "app.mbta._get_json",
                return_value={
                    "data": {
                        "attributes": {
                            "direction_names": ["Northbound", "Southbound"],
                            "direction_destinations": ["Alewife", "Ashmont/Braintree"],
                        }
                    }
                },
            ),
            patch("app.mbta._fetch_predictions", return_value={0: [future_prediction]}),
            patch("app.mbta._fetch_schedules", return_value={1: [future_schedule]}),
        ):
            payload = fetch_mbta(config, now)

        self.assertEqual(payload["directions"][0]["arrivals"][0]["source"], "prediction")
        self.assertEqual(payload["directions"][1]["arrivals"][0]["source"], "schedule")
        self.assertEqual(payload["directions"][0]["arrivals"][0]["minutes"], 5)
        self.assertEqual(payload["directions"][1]["arrivals"][0]["minutes"], 10)


class WeatherTests(unittest.TestCase):
    def test_get_json_retries_timeout_before_succeeding(self) -> None:
        with (
            patch(
                "app.weather.requests.get",
                side_effect=[
                    requests.Timeout("slow"),
                    FakeWeatherResponse({"ok": True}),
                ],
            ) as get,
            patch("app.weather.time.sleep"),
        ):
            payload = _get_json("https://api.weather.gov/test", {}, timeout_seconds=20)

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs["timeout"], (5, 20))

    def test_fetch_weather_keeps_forecast_when_alerts_timeout(self) -> None:
        now = datetime(2026, 5, 1, 9, tzinfo=ZoneInfo("America/New_York"))
        points = {
            "properties": {
                "forecastHourly": "https://api.weather.gov/hourly",
                "forecast": "https://api.weather.gov/daily",
            }
        }
        hourly = {
            "properties": {
                "periods": [
                    {
                        "startTime": "2026-05-01T09:00:00-04:00",
                        "endTime": "2026-05-01T10:00:00-04:00",
                        "temperature": 62,
                        "temperatureUnit": "F",
                        "shortForecast": "Mostly Sunny",
                    }
                ]
            }
        }
        daily = {
            "properties": {
                "periods": [
                    {
                        "name": "Today",
                        "startTime": "2026-05-01T06:00:00-04:00",
                        "endTime": "2026-05-01T18:00:00-04:00",
                        "isDaytime": True,
                        "temperature": 72,
                        "temperatureUnit": "F",
                    },
                    {
                        "name": "Tonight",
                        "startTime": "2026-05-01T18:00:00-04:00",
                        "endTime": "2026-05-02T06:00:00-04:00",
                        "isDaytime": False,
                        "temperature": 53,
                        "temperatureUnit": "F",
                    },
                ]
            }
        }
        config = AppConfig(
            home=HomeConfig(latitude=42.36, longitude=-71.06),
            weather=WeatherConfig(request_timeout_seconds=20),
        )

        with patch("app.weather._get_json", side_effect=[points, hourly, daily, RuntimeError("slow")]):
            payload = fetch_weather(config, now)

        self.assertEqual(payload["current"]["temperature"], 62)
        self.assertEqual(payload["daily_range"], {"high": 72, "low": 53, "temperature_unit": "F"})
        self.assertEqual(payload["alerts"], [])

    def test_daily_temperature_range_uses_today_day_and_night_periods(self) -> None:
        now = datetime(2026, 5, 1, 9, tzinfo=ZoneInfo("America/New_York"))
        periods = [
            {
                "startTime": "2026-05-01T06:00:00-04:00",
                "endTime": "2026-05-01T18:00:00-04:00",
                "isDaytime": True,
                "temperature": 72,
                "temperatureUnit": "F",
            },
            {
                "startTime": "2026-05-01T18:00:00-04:00",
                "endTime": "2026-05-02T06:00:00-04:00",
                "isDaytime": False,
                "temperature": 53,
                "temperatureUnit": "F",
            },
            {
                "startTime": "2026-05-02T06:00:00-04:00",
                "endTime": "2026-05-02T18:00:00-04:00",
                "isDaytime": True,
                "temperature": 80,
                "temperatureUnit": "F",
            },
        ]

        self.assertEqual(
            _daily_temperature_range(periods, now),
            {"high": 72, "low": 53, "temperature_unit": "F"},
        )


class RenderTests(unittest.TestCase):
    def test_render_dashboard_writes_grayscale_png_at_configured_size(self) -> None:
        now = datetime(2026, 5, 1, 9, tzinfo=ZoneInfo("America/New_York"))
        payload = DashboardPayload(
            generated_at=now,
            calendar=[
                {"time": "All day", "title": "Donation Pickup: City of Somerville"},
                {"time": "4:00 PM-5:00 PM", "title": "Haircut"},
            ],
            tasks=[{"title": "Take out recycling"}],
            weather={
                "current": {
                    "temperature": 62,
                    "temperature_unit": "F",
                    "short_forecast": "Mostly Sunny",
                    "wind_speed": "8 mph",
                    "wind_direction": "NW",
                    "precipitation": 10,
                },
                "daily_range": {"high": 72, "low": 53, "temperature_unit": "F"},
            },
            mbta={
                "directions": [
                    {
                        "name": "Northbound",
                        "terminal": "Alewife",
                        "arrivals": [{"minutes": 4, "time": "9:04 AM"}],
                    },
                    {
                        "name": "Southbound",
                        "terminal": "Ashmont/Braintree",
                        "arrivals": [{"minutes": 7, "time": "9:07 AM"}],
                    },
                ]
            },
            statuses={
                "google": SourceStatus(ok=True, updated_at=now),
                "weather": SourceStatus(ok=True, updated_at=now),
                "mbta": SourceStatus(ok=True, updated_at=now),
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "dashboard.png"
            config = AppConfig(
                dashboard=DashboardConfig(width=600, height=800, output_path=output_path)
            )
            rendered_path = render_dashboard(payload, config)

            self.assertEqual(rendered_path, output_path)
            self.assertTrue(output_path.exists())
            with Image.open(output_path) as image:
                self.assertEqual(image.size, (600, 800))
                self.assertEqual(image.mode, "L")


class DashboardServiceTests(unittest.TestCase):
    def test_weather_refresh_failure_preserves_previous_weather_payload(self) -> None:
        now = datetime(2026, 5, 1, 9, tzinfo=ZoneInfo("America/New_York"))
        previous_weather = {"current": {"temperature": 62}}
        service = DashboardService(AppConfig(weather=WeatherConfig(enabled=True)))
        service._payload = DashboardPayload(
            generated_at=now,
            weather=previous_weather,
            statuses={"weather": SourceStatus(ok=True, updated_at=now)},
        )

        with (
            patch("app.service.fetch_weather", side_effect=RuntimeError("Weather API timed out")),
            patch("app.service.render_dashboard"),
        ):
            payload = service.refresh_all()

        self.assertEqual(payload.weather, previous_weather)
        self.assertFalse(payload.statuses["weather"].ok)
        self.assertEqual(payload.statuses["weather"].error, "Weather API timed out")

    def test_refresh_due_fetches_only_due_sources(self) -> None:
        config = AppConfig(
            weather=WeatherConfig(enabled=True, refresh_seconds=100),
            mbta=MbtaConfig(
                enabled=True,
                refresh_seconds=45,
                stop_id="place-test",
                route_id="Red",
            ),
            google=GoogleConfig(enabled=True, refresh_seconds=100),
        )
        service = DashboardService(config)
        service._last_refresh = {"weather": 99, "mbta": 0, "google": 99}

        with (
            patch("app.service.time.monotonic", return_value=100),
            patch("app.service.fetch_weather") as fetch_weather,
            patch("app.service.fetch_google_day") as fetch_google_day,
            patch("app.service.fetch_mbta", return_value={"directions": []}) as fetch_mbta,
            patch("app.service.render_dashboard"),
        ):
            payload = service.refresh_due()

        fetch_weather.assert_not_called()
        fetch_google_day.assert_not_called()
        fetch_mbta.assert_called_once()
        self.assertTrue(payload.statuses["mbta"].ok)


if __name__ == "__main__":
    unittest.main()
