# Kindle Dashboard

A Flask backend that renders a `600x800` PNG for an 8th generation Kindle. The app is intended to run on a NAS in Docker and serve a fullscreen e-ink dashboard with Google Calendar, Google Tasks reminders, weather, and MBTA arrivals in both directions.

## Quick Start

1. Copy the example config:

   ```sh
   cp config.example.yaml config.yaml
   ```

2. Edit `config.yaml`:

   - Set `home.latitude` and `home.longitude`.
   - Set a real NWS `weather.user_agent` with contact info.
   - Enable `mbta` after choosing direction-specific `stop_ids` and a `route_id`.
   - Enable `google` after OAuth is configured.

3. Run locally:

   ```sh
   uv sync
   uv run flask --app app.main run --host 0.0.0.0 --port 8787
   ```

4. Run on the NAS:

   ```sh
   docker compose up -d --build
   ```

The rendered image is available at:

```text
http://NAS_IP:8787/dashboard.png
```

## MBTA Setup

Set your coordinates in `config.yaml`, then run:

```sh
uv run python scripts/discover_mbta_stop.py
```

Pick the useful platform stop IDs for each direction and the route ID, then enable MBTA:

```yaml
mbta:
  enabled: true
  route_id: Red
  stop_ids:
    0: place-example-north
    1: place-example-south
  direction_ids: [0, 1]
```

Use an MBTA API key for better rate limits:

```sh
export MBTA_API_KEY=...
```

## Google Setup

Create a Google Cloud OAuth desktop client with Calendar readonly and Tasks readonly access. Save the downloaded client file as:

```text
data/client_secret.json
```

Then run:

```sh
uv run python scripts/google_auth.py
```

This writes `data/token.json`. After that, set:

```yaml
google:
  enabled: true
```

## Kindle Loop

On the jailbroken Kindle, set `KINDLE_DASHBOARD_URL` to the NAS URL and run:

```sh
sh scripts/kindle-refresh.sh
```

The script downloads the latest PNG, clears the screen, displays it with `eips`, sleeps, and repeats.

## Endpoints

- `/dashboard.png`: Kindle image.
- `/`: minimal browser fallback with auto-refresh.
- `/debug.json`: current normalized data and source statuses.
- `/refresh`: manual refresh via `POST`.
- `/health`: health check.
