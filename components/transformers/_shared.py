"""Shared helper for transformers: rebuild a Record with updated data, immutably."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from core.models.record import Record


def with_data(record: Record, data: Mapping[str, Any]) -> Record:
    """Returns a copy of the record carrying the new data, same version/provenance."""
    return replace(record, data=dict(data))
