#!/usr/bin/env python
from __future__ import annotations

import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_config
from app.google_client import authorize_google


def main() -> None:
    config = load_config()
    if not config.google.client_secret_file.exists():
        raise SystemExit(
            "Missing Google OAuth client secret.\n"
            f"Save the downloaded desktop OAuth JSON as {config.google.client_secret_file}, "
            "then rerun this command."
        )
    oauth_port = int(os.getenv("GOOGLE_OAUTH_PORT", "8080"))
    _check_client_secret(config.google.client_secret_file, oauth_port)
    print("Starting Google OAuth flow...")
    print(f"Client secret: {config.google.client_secret_file}")
    print(f"Token output:  {config.google.token_file}")
    print(f"Redirect URI:  http://localhost:{oauth_port}/")
    authorize_google(config.google)
    print(f"Google token written to {config.google.token_file}")


def _check_client_secret(path: Path, oauth_port: int) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "installed" in payload:
        return

    redirect_uri = f"http://localhost:{oauth_port}/"
    configured = payload.get("web", {}).get("redirect_uris", [])
    if redirect_uri not in configured:
        raise SystemExit(
            "This looks like a Google OAuth web client, not a desktop client.\n"
            "Recommended fix: create an OAuth client with Application type 'Desktop app' "
            f"and save it as {path}.\n"
            "Web-client workaround: add this Authorized redirect URI in Google Cloud, "
            "download the updated JSON, and rerun this command:\n"
            f"{redirect_uri}"
        )


if __name__ == "__main__":
    main()
