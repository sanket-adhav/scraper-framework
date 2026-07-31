# ADR 0003 — Extractor.extract receives the source URL

**Date:** 2026-07-18 · **Status:** accepted · **Plan:** 05

## Context

plan2.md §5's spec example includes `item_id: { kind: regex, query: "/dp/...",
against: url }` — a field extracted from the request URL, not the document.
Records must also carry the source URL in their provenance (§9). The §3
`Extractor` signature `extract(doc, spec)` gave the extractor no way to know
the URL, and the Document deliberately doesn't carry one.

## Decision

Add a keyword argument with a default: `extract(doc, spec, *, source_url="")`.
The extract stage passes `ctx.request.url`; extractors that don't need it
ignore it. The config fingerprint is NOT passed — the stage stamps it onto the
record afterward, because fingerprints belong to config/context, not to
extraction logic.

## Consequences

- `against: url` fields work in the generic SpecDrivenExtractor for every format.
- Future extractors (e.g. LLM-based) get source context for free.
- Existing signatures stay compatible: the argument is keyword-only with a default.
