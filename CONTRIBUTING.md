# Contributing

This repo implements the architecture in [plan2.md](plan2.md), built in order via
[plans/](plans/). Read plan2.md §8 before touching the layout.

## Standing rules (from plans/00_INDEX.md — apply to every PR, forever)

1. **`core/` never gains an implementation or site knowledge.** Contracts and
   coordination only. import-linter enforces the boundary in CI on every PR:
   - `core` imports nothing from `components`, `plugins`, or `cli`.
   - `components` may import only `core.contracts`, `core.models`, `core.errors`.
   - `plugins` may import only that same core surface plus `components` — and
     never each other.
2. **Every new component ships with contract-conformance tests in the same PR.**
   Subclass the relevant suite in `tests/contract/base_suites.py`.
3. **Every extraction spec ships with a stored sample page/response and a config
   test** (`tests/config_specs/`).
4. **No plugin targets a source that hasn't passed the legal gate**
   (`docs/source_approval.md`, defined in Plan 06).
5. **A plan is done when its Definition of Done checkboxes are all true** — not
   when the code "basically works".

## Architecture invariants

- **One middleware mechanism.** Every cross-cutting concern around the fetch is a
  `Middleware` (plan2.md §6). If you're proposing a "preprocessor chain", "fetch
  hook", or decorator — the answer is a middleware.
- **No BaseScraper, ever.** Extension is composition only (plan2.md §7): implement
  a small contract, register it, reference it in config. Shared workflow shape
  lives in config presets, not superclasses.
- **`Document.select()` returns `list[str | Mapping]` only.** Parser-native nodes
  (lxml elements, etc.) must never leak out of a Document (plan2.md §5).
- **Contract changes require an ADR** in `docs/adr/` explaining what assumption
  broke and why the amendment benefits all implementations.

## Workflow

```bash
uv sync --dev            # set up
uv run pytest            # tests
uv run ruff check .      # lint
uv run mypy              # types (strict on core)
uv run lint-imports --config importlinter.ini   # boundary
uv run pre-commit install --install-hooks       # once, mirrors CI locally
```

CI runs all four checks; each one blocks merge.
