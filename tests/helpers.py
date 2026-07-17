"""Small helpers shared by test modules."""

from pathlib import Path

from core.models import Response

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def fixture_response(name: str, content_type: str) -> Response:
    """Loads a stored fixture file and wraps it as a fake successful Response."""
    body = (FIXTURES_DIR / name).read_bytes()
    return Response(status=200, headers={}, body=body, elapsed_ms=0.0, content_type=content_type)
