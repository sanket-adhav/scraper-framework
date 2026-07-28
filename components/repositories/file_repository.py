"""Repository that saves raw files (like PDFs) to a local directory.

Can save direct raw_body from the fetch stage, or dynamically resolve and
download from a specified URL field in the record data (including intermediate
HTML pages/iframes).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from core.errors.exceptions import PersistError
from core.models.record import Record

logger = logging.getLogger("scraper.file_repository")


class FileRepository:
    """Saves raw response bytes (PDFs, images, etc.) to a local directory."""

    def __init__(
        self,
        output_dir: str | Path = "output/pdfs",
        filename_field: str | None = None,
        url_field: str | None = None,
        date_field: str | None = None,
        resolve_intermediate: bool = True,
    ) -> None:
        """Configures where files are saved.

        Args:
            output_dir: Directory to save files into.
            filename_field: Optional field name to use for the file name.
            url_field: Optional field containing the URL to fetch/download the PDF from.
            date_field: Optional field containing the extracted circular date.
            resolve_intermediate: Whether to parse intermediate HTML pages for iframes.
        """
        self._output_dir = Path(output_dir)
        self._filename_field = filename_field
        self._url_field = url_field
        self._date_field = date_field
        self._resolve_intermediate = resolve_intermediate

    async def save(
        self,
        record: Record,
        raw_body: bytes | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> None:
        """Saves the raw file to disk and injects the `filepath` field."""
        try:
            body_to_write = raw_body

            # If url_field is configured, we dynamically fetch/resolve the file
            if self._url_field and self._url_field in record.data:
                source_url = record.data[self._url_field]
                if source_url:
                    logger.info("FileRepository: resolving link: %s", source_url)
                    body_to_write = await self._download_url_content(
                        source_url,
                        record.provenance.source_url,
                        headers=headers,
                        cookies=cookies,
                    )

            if body_to_write is None:
                logger.warning("FileRepository: no file content resolved, skipping save")
                return

            filename = self._build_filename(record)
            self._output_dir.mkdir(parents=True, exist_ok=True)
            filepath = self._output_dir / filename

            filepath.write_bytes(body_to_write)
            logger.info("FileRepository: saved %s (%d bytes)", filepath, len(body_to_write))

            # Inject filepath back into record.data
            if hasattr(record.data, '__setitem__'):
                record.data["filepath"] = str(filepath)
            else:
                mutable = dict(record.data)
                mutable["filepath"] = str(filepath)
                object.__setattr__(record, "data", mutable)

        except Exception as err:
            raise PersistError(
                f"FileRepository: failed to save file: {err}", transient=True
            ) from err

    async def _download_url_content(
        self,
        url: str,
        base_url: str,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> bytes | None:
        """Downloads the URL, resolving intermediate HTML pages/iframes if needed."""
        client_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": base_url,
        }
        if headers:
            client_headers.update(headers)

        async with httpx.AsyncClient(
            headers=client_headers,
            cookies=cookies or {},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            target_url = urljoin(base_url, url)

            # Try to resolve intermediate HTML pages/iframes first
            resolved_pdf_url = await self._resolve_pdf_url(client, target_url)
            if not resolved_pdf_url:
                logger.warning("FileRepository: could not resolve PDF URL for %s", target_url)
                return None

            logger.info("FileRepository: downloading resolved PDF: %s", resolved_pdf_url)
            # Update referer and accept headers for the resolved PDF request
            client.headers["Referer"] = target_url
            client.headers["Accept"] = "application/pdf, */*"
            resp = await client.get(resolved_pdf_url)
            logger.info(
                "FileRepository: requested=%s final=%s status=%d content_type=%s",
                resolved_pdf_url, resp.url, resp.status_code, resp.headers.get("Content-Type"),
            )
            if resp.status_code != 200:
                logger.error("FileRepository: failed to download PDF: HTTP %d", resp.status_code)
                return None

            content_type = resp.headers.get("Content-Type", "")
            if "application/pdf" not in content_type and len(resp.content) > 0:
                logger.warning(
                    "FileRepository: downloaded content is not PDF (Content-Type: %s)", content_type
                )
            return resp.content

    async def _resolve_pdf_url(self, client: httpx.AsyncClient, url: str) -> str | None:
        """Recursively resolves target URLs to direct PDF URLs."""
        parsed = urlparse(url)
        if parsed.path.lower().endswith(".pdf"):
            return url

        # Check if URL query contains a file param (e.g. ?file=foo.pdf)
        unwrapped = self._unwrap_file_param(url)
        if unwrapped:
            return await self._resolve_pdf_url(client, unwrapped)

        if not self._resolve_intermediate:
            return url

        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None

            content_type = resp.headers.get("Content-Type", "")
            if "application/pdf" in content_type:
                return url

            if "text/html" in content_type:
                soup = BeautifulSoup(resp.content, "html.parser")
                iframe = soup.find("iframe")
                if iframe and iframe.get("src"):
                    iframe_url = urljoin(url, str(iframe["src"]))
                    logger.debug("FileRepository: found iframe: %s", iframe_url)
                    return await self._resolve_pdf_url(client, iframe_url)

                # Look for fallback links in case of no iframe
                pdf_link = soup.find("a", href=re.compile(r"\.pdf", re.IGNORECASE))
                if pdf_link and pdf_link.get("href"):
                    link_url = urljoin(url, str(pdf_link["href"]))
                    logger.debug("FileRepository: found fallback PDF link: %s", link_url)
                    return await self._resolve_pdf_url(client, link_url)

        except Exception as e:
            logger.error("FileRepository: error resolving %s: %s", url, e)

        return None

    def _unwrap_file_param(self, url: str) -> str | None:
        """Extracts file URL from query parameters if present."""
        if "file=" in url:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            if "file" in qs:
                pdf_link = qs["file"][0].strip()
                if pdf_link.lower().endswith(".pdf") or pdf_link.startswith("http"):
                    return pdf_link
        return None

    def _build_filename(self, record: Record) -> str:
        """Derives a safe filename from the record's data and provenance."""
        if self._filename_field and self._filename_field in record.data:
            base = str(record.data[self._filename_field])
        else:
            raw_url = (
                record.data.get(self._url_field) if self._url_field
                else record.provenance.source_url
            )
            url_path = urlparse(str(raw_url or "")).path
            base = Path(url_path).stem if url_path else "document"

        date_str = None
        if self._date_field and self._date_field in record.data:
            raw_date = str(record.data[self._date_field])
            date_str = _parse_date_prefix(raw_date)

        if not date_str:
            date_str = record.provenance.scraped_at.strftime("%Y-%m-%d")

        safe_base = _safe_filename(base)

        ext = ".pdf"  # Default for compliance files
        return f"{date_str}_{safe_base}{ext}"


def _parse_date_prefix(raw_date: str) -> str | None:
    """Parses date strings like 'Jul 21, 2026' or '2026-07-21' into YYYY-MM-DD."""
    from datetime import datetime
    for fmt in ("%b %d, %Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(raw_date.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _safe_filename(text: str, max_len: int = 100) -> str:
    """Converts arbitrary text into a filesystem-safe filename slug."""
    safe = re.sub(r"[^\w\s.-]", "_", text)
    safe = re.sub(r"[\s_]+", "_", safe).strip("_")
    return safe[:max_len] if safe else "unnamed"

