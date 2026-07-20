# Third-plugin friction log (Plan 08, plan2.md §15 extensibility proof)

The `news_feed` plugin was built **through the public seams only** — scaffold,
`plugin.yaml`, `config/extraction.yaml`, stored fixtures — with **zero changes
to `core/` or `components/`**. Per the plan, the friction hit while building it
is the most valuable output: each item below is a real usability or capability
gap to fix, not a reason the plugin failed. The plugin runs green today.

## Findings

### F1 — Extraction is one-record-per-fetch; multi-item list/feed pages aren't supported (HIGH)
The first attempt modeled a real RSS feed: one XML page with many `<item>`
elements. `SpecDrivenExtractor` takes `select()[0]` per field, so it produces a
**single record per fetched document** — a feed page with 10 items yields 1
record and silently drops 9. There is no per-item fan-out: `discover` fans out
*requests*, not *records*.
**Workaround used:** reshaped the source to one product per page, paginated via
a `<nextpage>` link — valid, but it dodges the real need.
**Proposed fix:** a record fan-out mechanism — e.g. a spec `for_each:` root
selector that emits N records per document, or a stage that expands
`ctx.records`. Needs an engine/contract change, so it is filed, not hacked in.

### F2 — Auth/session can't be wired from pure config (MEDIUM)
Plan 07's `AuthMiddleware` needs a `LoginProvider` instance, which is Python,
not YAML. A spec-only plugin therefore cannot scrape a login-protected source —
the composition root has no config-driven way to build a provider + session
store and insert `auth` into the middleware list.
**Proposed fix:** register login providers by name and add an `auth:` config
section (provider name + `secret://` credential refs + session-store settings)
that the composition root wires, exactly like validators/transformers.

### F3 — `config_specs` fixture lookup was implicit (LOW)
The auto-discovery test resolves a spec's `fixture:` against the plugin's own
`fixtures/` dir, but that convention lived only in the discovery test, not in
docs. Every plugin authored so far had to copy the pattern by example.
**Proposed fix:** document the spec-file convention (fixture, sample_url,
expect) in CONTRIBUTING.md and have `scaffold new-plugin` emit it (it already
emits most of it).

### F4 — No first-class "list registered component options" (LOW)
`scraper list-components` shows component *names* but not their config options,
so writing a validator/transformer block means reading source. Not blocking,
but every field was written by looking at the class `__init__`.
**Proposed fix:** surface each component's option schema (the classes already
have typed constructors) in `list-components --verbose`.

## What worked with zero friction
- XML parser + XPath selectors, chosen entirely in YAML (no code).
- `discover`-stage pagination via an XPath `next_url` selector + `url_template`.
- Date normalization with explicit input formats; enum mapping; field enrichment.
- The **per-plugin error-policy override** (`error_policy.stages.transform`)
  merged over the framework default purely from the plugin's config — no code.
- Contract-conformance + `config_specs` fixture test picked the plugin up
  automatically on drop-in.
