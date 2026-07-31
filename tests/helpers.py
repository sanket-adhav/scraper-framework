"""Small helpers shared by test modules."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.models import Provenance, Record, Response

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def fixture_response(name: str, content_type: str) -> Response:
    """Loads a stored fixture file and wraps it as a fake successful Response."""
    body = (FIXTURES_DIR / name).read_bytes()
    return Response(status=200, headers={}, body=body, elapsed_ms=0.0, content_type=content_type)


def make_record(data: dict[str, Any] | None = None, schema_version: str = "1") -> Record:
    """Builds a Record with full provenance for validator/transformer/repository tests."""
    return Record(
        data=data if data is not None else {"title": "Aurora X2", "price": 4999.0},
        schema_version=schema_version,
        provenance=Provenance(
            plugin_name="test_plugin",
            plugin_version="0.1.0",
            config_fingerprint="cafe" * 16,
            source_url="https://shop.example/item/1",
            scraped_at=datetime(2026, 7, 18, tzinfo=UTC),
        ),
    )
