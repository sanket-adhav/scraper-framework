"""Test bootstrap: load a local .env (gitignored) so real-service tests like the
Postgres contract test can read DATABASE_URL without exporting it by hand."""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).parent.parent / ".env"


def _load_dotenv() -> None:
    """Reads simple KEY=VALUE lines from .env into the environment (no override)."""
    if not _ENV_FILE.is_file():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()
