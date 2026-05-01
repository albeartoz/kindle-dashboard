from __future__ import annotations

from pathlib import Path
from textwrap import wrap
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.config import AppConfig
from app.models import DashboardPayload

BLACK = 0
DARK = 45
MID = 125
LIGHT = 225
WHITE = 255


def render_dashboard(payload: DashboardPayload, config: AppConfig) -> Path:
    width = config.dashboard.width
    height = config.dashboard.height
    image = Image.new("L", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    fonts = _fonts()

    margin = 24
    y = 18
    now = payload.generated_at

    draw.text((margin, y), config.dashboard.title, font=fonts["title"], fill=BLACK)
    date_text = now.strftime("%a, %b %-d")
    time_text = f"Updated {now.strftime('%-I:%M %p')}"
    _right_text(draw, width - margin, y + 4, date_text, fonts["body_bold"], BLACK)
    _right_text(draw, width - margin, y + 32, time_text, fonts["small"], MID)
    y += 72
    _line(draw, margin, y, width - margin)

    y = _draw_weather(draw, payload.weather, margin, y + 14, width - margin, fonts)
    y = _draw_mbta(draw, payload.mbta, margin, y + 14, width - margin, fonts)
    status_y = height - 54
    event_bottom = min(status_y - 132, y + 250)
    y = _draw_events(draw, payload.calendar, margin, y + 14, width - margin, fonts, event_bottom)
    y = _draw_tasks(draw, payload.tasks, margin, y + 14, width - margin, fonts, status_y - 12)
    _draw_statuses(draw, payload, margin, status_y, width - margin, fonts)

    output_path = config.dashboard.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return output_path


def _draw_weather(
    draw: ImageDraw.ImageDraw,
    weather: dict[str, Any],
    x: int,
    y: int,
    right: int,
    fonts: dict[str, ImageFont.ImageFont],
) -> int:
    _section_title(draw, "Weather", x, y, fonts)
    y += 28
    current = weather.get("current") or {}
    if not current:
        draw.text((x, y), "Weather unavailable", font=fonts["body"], fill=MID)
        return y + 36

    temp = current.get("temperature")
    unit = current.get("temperature_unit", "F")
    forecast = current.get("short_forecast", "")
    wind = " ".join(
        part
        for part in [current.get("wind_speed", ""), current.get("wind_direction", "")]
        if part
    )
    precip = current.get("precipitation")

    draw.text((x, y), f"{temp} {unit}", font=fonts["large"], fill=BLACK)
    range_text = _format_temperature_range(weather.get("daily_range") or {})
    temp_bottom = y + 40
    if range_text:
        draw.text((x, y + 42), range_text, font=fonts["small_bold"], fill=DARK)
        temp_bottom = y + 64

    summary_x = x + 124
    summary_y = y
    for line in _wrap_text(forecast, fonts["body_bold"], right - summary_x, max_lines=2):
        draw.text((summary_x, summary_y), line, font=fonts["body_bold"], fill=BLACK)
        summary_y += 25
    details = []
    if precip is not None:
        details.append(f"Rain {precip}%")
    if wind:
        details.append(f"Wind {wind}")
    if details:
        draw.text((summary_x, summary_y), "  ".join(details), font=fonts["small"], fill=DARK)
        summary_y += 22
    y = max(summary_y, temp_bottom)
    alerts = weather.get("alerts") or []
    if alerts:
        y += 28
        draw.rectangle((x, y, right, y + 26), fill=LIGHT)
        draw.text((x + 8, y + 4), f"Alert: {alerts[0]}", font=fonts["small_bold"], fill=BLACK)
        y += 30
    return y + 12


def _draw_mbta(
    draw: ImageDraw.ImageDraw,
    mbta: dict[str, Any],
    x: int,
    y: int,
    right: int,
    fonts: dict[str, ImageFont.ImageFont],
) -> int:
    _section_title(draw, "MBTA", x, y, fonts)
    y += 30
    directions = mbta.get("directions") or []
    if not directions:
        draw.text((x, y), "Train arrivals unavailable", font=fonts["body"], fill=MID)
        return y + 36

    column_gap = 12
    column_width = (right - x - column_gap) // 2
    start_y = y
    max_y = y
    for index, direction in enumerate(directions[:2]):
        left = x + index * (column_width + column_gap)
        box_right = left + column_width
        draw.rectangle((left, y, box_right, y + 108), outline=MID, width=2)
        name = direction.get("name", f"Direction {direction.get('direction_id', index)}")
        for line in _wrap_text(name, fonts["small_bold"], column_width - 16, max_lines=1):
            draw.text((left + 8, y + 8), line, font=fonts["small_bold"], fill=BLACK)
        arrivals = direction.get("arrivals") or []
        if not arrivals:
            draw.text((left + 8, y + 42), "No upcoming trains", font=fonts["small"], fill=MID)
        else:
            primary = arrivals[0]
            draw.text((left + 8, y + 36), f"{primary['minutes']} min", font=fonts["large"], fill=BLACK)
            draw.text((left + 8, y + 76), primary["time"], font=fonts["small"], fill=DARK)
            if len(arrivals) > 1:
                second = arrivals[1]
                _right_text(
                    draw,
                    box_right - 8,
                    y + 78,
                    f"next {second['minutes']}m",
                    fonts["small"],
                    DARK,
                )
        max_y = max(max_y, y + 108)
    return max_y + 12 if directions else start_y


def _format_temperature_range(range_data: dict[str, Any]) -> str:
    high = range_data.get("high")
    low = range_data.get("low")
    if high is None or low is None:
        return ""
    unit = range_data.get("temperature_unit", "F")
    return f"H {high} / L {low} {unit}"


def _draw_events(
    draw: ImageDraw.ImageDraw,
    events: list[dict[str, Any]],
    x: int,
    y: int,
    right: int,
    fonts: dict[str, ImageFont.ImageFont],
    bottom: int,
) -> int:
    _section_title(draw, "Calendar", x, y, fonts)
    y += 30
    if not events:
        draw.text((x, y), "No events today", font=fonts["body"], fill=MID)
        return y + 36

    rendered = 0
    for index, event in enumerate(events):
        if y + 28 > bottom:
            remaining = len(events) - index
            draw.text((x, y), f"+ {remaining} more", font=fonts["small_bold"], fill=MID)
            return bottom
        draw.text((x, y), event.get("time", ""), font=fonts["small_bold"], fill=BLACK)
        text_x = x + 112
        title = event.get("title", "(No title)")
        for line in _wrap_text(title, fonts["body"], right - text_x, max_lines=2):
            if y + 24 > bottom:
                draw.text((text_x, y), "...", font=fonts["body"], fill=MID)
                return bottom
            draw.text((text_x, y), line, font=fonts["body"], fill=BLACK)
            y += 24
        y += 4
        rendered += 1
        if rendered >= 7:
            remaining = len(events) - rendered
            if remaining > 0 and y + 20 <= bottom:
                draw.text((x, y), f"+ {remaining} more", font=fonts["small_bold"], fill=MID)
            break
    return y + 6


def _draw_tasks(
    draw: ImageDraw.ImageDraw,
    tasks: list[dict[str, Any]],
    x: int,
    y: int,
    right: int,
    fonts: dict[str, ImageFont.ImageFont],
    bottom: int,
) -> int:
    _section_title(draw, "Reminders", x, y, fonts)
    y += 30
    if not tasks:
        draw.text((x, y), "No reminders due today", font=fonts["body"], fill=MID)
        return y + 36

    rendered = 0
    for index, task in enumerate(tasks):
        if y + 26 > bottom:
            remaining = len(tasks) - index
            draw.text((x, y), f"+ {remaining} more", font=fonts["small_bold"], fill=MID)
            return bottom
        draw.ellipse((x, y + 6, x + 10, y + 16), outline=BLACK, width=2)
        for line in _wrap_text(task.get("title", "(Untitled task)"), fonts["body"], right - x - 22, 1):
            draw.text((x + 22, y), line, font=fonts["body"], fill=BLACK)
        y += 28
        rendered += 1
        if rendered >= 6:
            remaining = len(tasks) - rendered
            if remaining > 0 and y + 20 <= bottom:
                draw.text((x, y), f"+ {remaining} more", font=fonts["small_bold"], fill=MID)
            break
    return y


def _draw_statuses(
    draw: ImageDraw.ImageDraw,
    payload: DashboardPayload,
    x: int,
    y: int,
    right: int,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    _line(draw, x, y - 10, right)
    pieces = []
    for name, status in payload.statuses.items():
        if status.ok:
            pieces.append(f"{name}: ok")
        else:
            pieces.append(f"{name}: {status.error or 'off'}")
    text = "  |  ".join(pieces) if pieces else "No sources configured"
    for line in _wrap_text(text, fonts["tiny"], right - x, max_lines=2):
        draw.text((x, y), line, font=fonts["tiny"], fill=MID)
        y += 16


def _section_title(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    draw.text((x, y), text.upper(), font=fonts["small_bold"], fill=DARK)


def _line(draw: ImageDraw.ImageDraw, x1: int, y: int, x2: int) -> None:
    draw.line((x1, y, x2, y), fill=MID, width=2)


def _right_text(
    draw: ImageDraw.ImageDraw,
    right: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: int,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((right - (bbox[2] - bbox[0]), y), text, font=font, fill=fill)


def _wrap_text(
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    if not text:
        return [""]

    avg_char_width = max(6, int(font.getlength("ABCDEFGHIJKLMNOPQRSTUVWXYZ") / 26))
    width_chars = max(8, max_width // avg_char_width)
    lines: list[str] = []
    for line in wrap(text, width=width_chars):
        while font.getlength(line) > max_width and len(line) > 4:
            line = line[:-2].rstrip() + "."
        lines.append(line)
        if len(lines) == max_lines:
            break
    return lines or [text[:width_chars]]


def _fonts() -> dict[str, ImageFont.ImageFont]:
    font_path = _find_font()
    bold_font_path = _find_bold_font() or font_path
    if font_path:
        return {
            "title": ImageFont.truetype(font_path, 34),
            "large": ImageFont.truetype(font_path, 34),
            "body": ImageFont.truetype(font_path, 22),
            "body_bold": ImageFont.truetype(bold_font_path, 22),
            "small": ImageFont.truetype(font_path, 17),
            "small_bold": ImageFont.truetype(bold_font_path, 17),
            "tiny": ImageFont.truetype(font_path, 13),
        }
    default = ImageFont.load_default()
    return {name: default for name in ["title", "large", "body", "body_bold", "small", "small_bold", "tiny"]}


def _find_font() -> str | None:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _find_bold_font() -> str | None:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None
