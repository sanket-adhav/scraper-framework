"""Extractor for pages whose payload is one or more tables/lists rather than one entity.

`SpecDrivenExtractor` answers "what is this page about?" — it takes the first
match per field and yields a single flat Record. Report and grid pages ask a
different question: "what are all the rows on this page?".

This extractor keeps the one-Record-per-document contract (the pipeline's
`PipelineContext.record` is singular) and puts the repetition *inside* the
record instead:

    {"collections": {"by_carrier": [ {...}, {...} ]}, "row_counts": {...}}

Collections are declared in a top-level `extractor_options.collections` block,
because `ExtractConfigModel` forbids extra keys:

    extractor: table
    extractor_options:
      collections:
        by_carrier:
          rows: "table.billing-table:nth-of-type(2) tbody tr"
          columns: [carrier, statements, match_rate, expected, received, variance]

`columns` may be a list (positional `<td>` mapping) or a mapping of
`name -> css` evaluated relative to each row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from lxml import html as lxml_html

from components.extractors.cleanups import apply_chain
from core.contracts.document import Document
from core.contracts.extractor import ExtractionSpec
from core.errors.exceptions import ExtractionError
from core.models.record import Provenance, Record


class TableExtractor:
    """Collects every row of every declared table into a single Record."""

    def __init__(
        self,
        plugin_name: str = "",
        plugin_version: str = "",
        collections: Mapping[str, Any] | None = None,
        cleanup: Sequence[str] = ("collapse_whitespace", "strip"),
    ) -> None:
        """Remembers the owning plugin and the collection declarations from YAML."""
        self._plugin_name = plugin_name
        self._plugin_version = plugin_version
        self._collections: Mapping[str, Any] = collections or {}
        self._cleanup = list(cleanup)

    def extract(self, doc: Document, spec: ExtractionSpec, *, source_url: str = "") -> Record:
        """Parses the document once, then harvests each declared collection from it."""
        if not self._collections:
            raise ExtractionError(
                "table extractor needs `extractor_options.collections` in the plugin config"
            )
        try:
            root = lxml_html.fromstring(doc.raw())
        except Exception as err:  # noqa: BLE001 — normalize parser failures
            raise ExtractionError(f"could not parse document as HTML: {err}") from err

        collections: dict[str, list[dict[str, Any]]] = {}
        counts: dict[str, int] = {}
        for name, decl in self._collections.items():
            rows = self._harvest(root, name, decl)
            collections[name] = rows
            counts[name] = len(rows)

        return Record(
            data={"collections": collections, "row_counts": counts, "source_url": source_url},
            schema_version=spec.schema_version,
            provenance=Provenance(
                plugin_name=self._plugin_name,
                plugin_version=self._plugin_version,
                config_fingerprint="",  # stamped by the extract stage, which owns the context
                source_url=source_url,
                scraped_at=datetime.now(UTC),
            ),
        )

    def _harvest(self, root: Any, name: str, decl: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Selects a collection's row elements and maps each one into a dict."""
        row_query = decl.get("rows")
        if not row_query:
            raise ExtractionError(f"collection {name!r} is missing a `rows` selector")

        columns = decl.get("columns")
        if not columns:
            raise ExtractionError(f"collection {name!r} is missing `columns`")

        cell_query = decl.get("cell_selector", "td")
        skip_empty = bool(decl.get("skip_empty", True))
        cleanup = list(decl.get("cleanup", self._cleanup))

        elements = _select(root, row_query)
        out: list[dict[str, Any]] = []

        for el in elements:
            if isinstance(columns, Mapping):
                row = {
                    field: self._clean(_first_text(el, css), cleanup, field)
                    for field, css in columns.items()
                }
            else:
                cells = _select(el, cell_query) or [el]
                row = {}
                for i, field in enumerate(columns):
                    text = cells[i].text_content() if i < len(cells) else ""
                    row[str(field)] = self._clean(text, cleanup, str(field))

            if skip_empty and not any(v for v in row.values()):
                continue
            out.append(row)

        return out

    def _clean(self, text: str | None, chain: Sequence[str], field: str) -> str:
        """Applies the cleanup chain, tolerating a missing cell."""
        if text is None:
            return ""
        return str(apply_chain(text, list(chain), field))


def _select(node: Any, query: str) -> list[Any]:
    """Runs a CSS query, falling back to XPath when the query looks like a path."""
    if query.startswith(("/", "(", "./")):
        return list(node.xpath(query))
    return list(node.cssselect(query))


def _first_text(node: Any, query: str) -> str:
    """Text of the first match for a row-relative selector, or '' when absent."""
    found = _select(node, query)
    return found[0].text_content() if found else ""
