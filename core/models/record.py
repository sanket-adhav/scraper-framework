"""Record envelope — every record carries its schema version and provenance (plan2.md §9)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Provenance:
    """Which exact plugin, settings, and source produced this record."""

    plugin_name: str
    plugin_version: str
    config_fingerprint: str
    source_url: str
    scraped_at: datetime


@dataclass(frozen=True, slots=True)
class Record:
    data: Mapping[str, Any]
    schema_version: str
    provenance: Provenance
