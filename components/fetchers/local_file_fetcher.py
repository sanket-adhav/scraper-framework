"""Fetcher that serves file:// URLs from disk — keeps every integration test network-free."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

from core.errors.exceptions import FetchError
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


class LocalFileFetcher:
    """Reads file:// requests from the local filesystem, optionally inside one root folder."""

    def __init__(self, root: str | Path | None = None) -> None:
        """If a root is given, all paths resolve inside it and cannot escape it."""
        self._root = Path(root).resolve() if root is not None else None

    async def fetch(self, request: ScrapeRequest) -> Response:
        """Returns the file's bytes as a 200 Response with a guessed content type."""
        path = self._resolve(request.url)
        if not path.is_file():
            raise FetchError(f"local file not found: {path}", transient=False)
        content_type, _ = mimetypes.guess_type(str(path))
        return Response(
            status=200,
            headers={},
            body=path.read_bytes(),
            elapsed_ms=0.0,
            content_type=content_type,
        )

    def _resolve(self, url: str) -> Path:
        """Turns a file:// URL into a safe filesystem path."""
        parts = urlsplit(url)
        if parts.scheme != "file":
            raise FetchError(f"LocalFileFetcher only handles file:// URLs, got {url!r}")
        raw_path = unquote(parts.netloc + parts.path)
        if self._root is None:
            return Path(raw_path)
        candidate = (self._root / raw_path.lstrip("/")).resolve()
        if not candidate.is_relative_to(self._root):
            raise FetchError(f"path escapes the configured root: {url!r}")
        return candidate
