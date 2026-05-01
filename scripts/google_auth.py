#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_config
from app.google_client import authorize_google


def main() -> None:
    config = load_config()
    authorize_google(config.google)
    print(f"Google token written to {config.google.token_file}")


if __name__ == "__main__":
    main()
