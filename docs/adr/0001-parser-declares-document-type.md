# ADR 0001 — Parser declares the Document type it produces

**Date:** 2026-07-17 · **Status:** accepted · **Plan:** 02

## Context

plan2.md §5 promises that a config using the wrong selector kind (e.g. XPath
against a JSON API) fails **at config load**, never mid-scrape. To check that,
the config loader must know which Document type a pipeline will produce —
before anything is fetched or parsed.

The §3 `Parser` protocol only declared `content_types`; the produced Document
type was implicit in the return value, which is invisible at config-load time.

## Decision

Add `document_type: type` to the `Parser` contract. Every parser declares the
concrete Document class it produces (e.g. `HtmlParser.document_type =
HtmlDocument`). The capability check reads `document_type.capabilities` and
validates every field's selector kind in the extraction spec against it.

## Consequences

- The load-time capability check (plan2.md §5 rule 2) is implementable purely
  from registry metadata — no parsing needed to validate a config.
- Every parser (including plugin-contributed ones) must set the attribute; the
  parser contract suite fails any parser that forgets it.
- Benefits all implementations equally — no parser is special-cased.
