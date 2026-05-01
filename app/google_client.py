from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from dateutil.parser import isoparse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build

from app.config import GoogleConfig

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]


def authorize_google(config: GoogleConfig) -> None:
    creds = _load_or_create_credentials(config)
    if not creds.valid:
        raise RuntimeError("Google credentials could not be validated")


def fetch_google_day(
    config: GoogleConfig, now: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        creds = _load_or_create_credentials(config, interactive=False)
        calendar_service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        tasks_service = build("tasks", "v1", credentials=creds, cache_discovery=False)

        start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
        end = start + timedelta(days=1)
        task_due_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        task_due_end = task_due_start + timedelta(days=1)

        events: list[dict[str, Any]] = []
        for calendar_id in config.calendar_ids:
            for item in _calendar_items(calendar_service, calendar_id, start, end):
                events.append(_event_to_item(item, now))

        tasks: list[dict[str, Any]] = []
        for task_list_id in _task_list_ids(tasks_service, config.task_list_ids):
            for item in _task_items(tasks_service, task_list_id, task_due_start, task_due_end):
                if _task_due_date(item) == now.date().isoformat():
                    tasks.append(_task_to_item(item))

        return sorted(events, key=lambda value: value["sort_key"]), sorted(
            tasks, key=lambda value: value.get("title", "").lower()
        )
    except HttpError as exc:
        raise RuntimeError(_google_api_error(exc)) from exc


def _calendar_items(
    calendar_service: Any,
    calendar_id: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params = {
            "calendarId": calendar_id,
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": 20,
        }
        if page_token:
            params["pageToken"] = page_token
        response = calendar_service.events().list(**params).execute()
        items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return items


def _task_items(
    tasks_service: Any,
    task_list_id: str,
    due_start: datetime,
    due_end: datetime,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params = {
            "tasklist": task_list_id,
            "dueMin": due_start.isoformat().replace("+00:00", "Z"),
            "dueMax": due_end.isoformat().replace("+00:00", "Z"),
            "showCompleted": False,
            "showHidden": False,
            "maxResults": 20,
        }
        if page_token:
            params["pageToken"] = page_token
        response = tasks_service.tasks().list(**params).execute()
        items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return items


def _load_or_create_credentials(config: GoogleConfig, interactive: bool = True) -> Credentials:
    creds: Credentials | None = None
    token_file = Path(config.token_file)
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError("Google token is missing or invalid; run scripts/google_auth.py")
        if not Path(config.client_secret_file).exists():
            raise RuntimeError(f"Missing Google client secret: {config.client_secret_file}")
        flow = InstalledAppFlow.from_client_secrets_file(str(config.client_secret_file), SCOPES)
        oauth_port = int(os.getenv("GOOGLE_OAUTH_PORT", "8080"))
        creds = flow.run_local_server(port=oauth_port)

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _task_list_ids(tasks_service: Any, configured_ids: list[str]) -> list[str]:
    if configured_ids:
        return configured_ids

    ids: list[str] = []
    page_token: str | None = None
    while True:
        params = {"maxResults": 20}
        if page_token:
            params["pageToken"] = page_token
        response = tasks_service.tasklists().list(**params).execute()
        ids.extend(item["id"] for item in response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return ids


def _event_to_item(item: dict[str, Any], now: datetime) -> dict[str, Any]:
    start_raw = item.get("start", {})
    end_raw = item.get("end", {})
    all_day = "date" in start_raw

    if all_day:
        label = "All day"
        sort_key = f"{start_raw.get('date', '')}T00:00:00"
    else:
        start = isoparse(start_raw["dateTime"]).astimezone(now.tzinfo)
        end = isoparse(end_raw["dateTime"]).astimezone(now.tzinfo) if end_raw.get("dateTime") else None
        label = start.strftime("%-I:%M %p")
        if end:
            label = f"{label}-{end.strftime('%-I:%M %p')}"
        sort_key = start.isoformat()

    return {
        "title": item.get("summary", "(No title)"),
        "time": label,
        "location": item.get("location", ""),
        "sort_key": sort_key,
        "all_day": all_day,
    }


def _task_to_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title", "(Untitled task)"),
        "notes": item.get("notes", ""),
        "due": item.get("due", ""),
    }


def _task_due_date(item: dict[str, Any]) -> str:
    due = item.get("due", "")
    return due[:10] if len(due) >= 10 else ""


def _google_api_error(exc: HttpError) -> str:
    reason = getattr(exc, "reason", "") or "Google API request failed"
    if "has not been used" in reason and "disabled" in reason:
        return "Google API is disabled in this Cloud project"
    return reason
