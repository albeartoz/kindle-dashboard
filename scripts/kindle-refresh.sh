#!/bin/sh

URL="${KINDLE_DASHBOARD_URL:-http://NAS_IP:8787/dashboard.png}"
OUT="/mnt/us/dashboard.png"
SLEEP_SECONDS="${KINDLE_DASHBOARD_SLEEP:-60}"

while true; do
  wget -q -O "$OUT.tmp" "$URL" && mv "$OUT.tmp" "$OUT"
  eips -c
  eips -g "$OUT"
  sleep "$SLEEP_SECONDS"
done

