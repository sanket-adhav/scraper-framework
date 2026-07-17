"""Parser that turns a JSON response into a JsonDocument."""

from __future__ import annotations

import json
from typing import ClassVar

from components.documents.json_document import JsonDocument
from components.parsers._hardening import DEFAULT_MAX_BODY_BYTES, checked_body
from core.contracts.parser import ParseError
from core.models.response import Response


class JsonParser:
    """Reads a JSON response body and produces a queryable JsonDocument."""

    content_types: ClassVar[frozenset[str]] = frozenset({"application/json"})
    document_type: ClassVar[type[JsonDocument]] = JsonDocument

    def __init__(self, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        """Remembers the body size limit this parser will enforce."""
        self._max_body_bytes = max_body_bytes

    def parse(self, response: Response) -> JsonDocument:
        """Checks safety limits, parses the JSON, and returns a JsonDocument."""
        body = checked_body(response, self._max_body_bytes)
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ParseError(f"could not parse JSON: {err}") from err
        return JsonDocument(data, body, response.content_type or "application/json")
