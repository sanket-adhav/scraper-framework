# Book-of-Business MCP server

A stdio [MCP](https://modelcontextprotocol.io) server that exposes the AMS
Book-of-Business pipeline as tools, so **Claude can drive scrape → report from
chat** instead of a shell sequence.

The tools are a thin layer over the framework's existing, tested CLI verbs
(`cli.main run` / `dry-run`) and its authenticated Playwright fetcher — the MCP
server adds no second implementation of the scrape.

## The demo flow: draft → verify → run

For a **known** AMS (the local Quickfire demo), it's one call:

> "Pull the book from the AMS and generate a valuation report for Summit
> Brokerage Group." → `run_book_rolling_report(agency="Summit Brokerage Group")`
> → report path + `score 76/100 (Strong Buy)`.

For a **new** AMS, Claude can't guess selectors it hasn't seen, so it works in a
loop with a human in the room:

| Step | Tool | What it's for |
|---|---|---|
| **draft** | `scaffold_plugin` | Create a validate-passing plugin skeleton |
| **draft** | `fetch_rendered_html` | Log in and return the page's real (post-JS) DOM to write selectors against |
| **verify** | `verify_config` | Dry-run the config through *extract only* — shows what each selector matched, persists nothing |
| **run** | `run_config` | Run one config for real and report row counts |
| **run** | `run_book_rolling_report` | Scrape every config, then render the report |
| — | `list_plugin_configs` | Inspect what a plugin pulls before running |

## Tools

- **`list_plugin_configs(plugin="ams_book_rolling")`** — the plugin's configs,
  their URLs, and the collections each extracts.
- **`run_book_rolling_report(agency, prepared_for=…, as_of=…, skip_scrape=False)`**
  — the one-call path. Scrapes all configs, generates the HTML report, returns the
  path plus headline metrics (clients, policies, premium, revenue, score, verdict).
  `skip_scrape=True` re-renders from existing `output/ams` data without hitting the AMS.
- **`run_config(config_path)`** — run a single config; returns output file + row counts.
- **`verify_config(config_path, sample_rows=2)`** — dry-run; returns per-collection
  match counts and a small value sample. Persists nothing.
- **`fetch_rendered_html(url, login_url=…, wait_selector=…, max_chars=40000, …)`**
  — authenticated browser render of a page's DOM. `wait_selector` waits for content
  (e.g. a grid row) so you don't capture a spinner.
- **`scaffold_plugin(name)`** — write a new `plugins/<name>/` skeleton.

## Credentials

Credentials are **never** tool arguments. The server loads
`scraper_framework/.env` and the fetcher reads `AMS_EMAIL` / `AMS_PASSWORD` from
the environment, exactly as the CLI does:

```
AMS_BASE_URL=http://localhost:5577
AMS_EMAIL=admin@quickfire.local
AMS_PASSWORD=Password123!
```

## Running it

Registered for this repo in [`.mcp.json`](../.mcp.json). Claude Code picks it up
when the project is trusted (approve the server on first prompt). The paths there
are **absolute to this machine** — edit them if the repo moves.

Manual stdio launch (what Claude runs):

```bash
cd /Users/sanketadhav/scraper_framework
.venv/bin/python -m mcp_server.server
```

Prerequisites: the AMS running on `:5577` (see the repo `HANDOVER.md`), the demo
data seeded, and Playwright's Chromium installed (`playwright install chromium`).

## Design notes

- **Why subprocess, not in-process** — scrapes drive Playwright's own asyncio loop;
  shelling out to `cli.main` keeps that isolated from the MCP server's loop and
  reuses the exact tested code path. The report render is a subprocess too
  (`generate.py` is a script, not an importable module).
- **Path safety** — `run_config` / `verify_config` refuse any path outside the repo,
  and `scaffold_plugin` restricts names to `[a-z0-9_]`.
- **What it won't fabricate** — the tools only run the pipeline; every figure in the
  report still comes from scraped AMS data (see the report's "Disclosed limitations").
