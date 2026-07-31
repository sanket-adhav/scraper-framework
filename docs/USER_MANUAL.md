# Scraper Framework — Developer Manual

> **Package:** `scraper-framework` · **Version:** 0.1.0 · **Requires:** Python 3.12+
>
> **Console script:** `scraper` · **License:** see repository

A config-driven scraping framework you install as a dependency. You get the
engine, a component library, and a plugin system — you supply one YAML file per
target site.

---

## Quick Install

Embed the framework by installing the package — no repo checkout or source build
required:

| Tool | Install |
|---|---|
| **pip** (Git) | `pip install git+https://github.com/<org>/scraper-framework.git` |
| **pip** (wheel) | `pip install scraper_framework-0.1.0-py3-none-any.whl` |
| **pip** (index) | `pip install scraper-framework` |
| **uv** | `uv add scraper-framework` |

```bash
# One post-install step, only if you scrape JavaScript-rendered sites:
playwright install chromium

# Verify
scraper list-components
```

> **Status:** the package is not published yet. This manual describes how it is
> consumed once installed. Three gaps to close before shipping to other teams are
> listed in [Appendix A](#appendix-a-before-you-publish) — all verified against
> the current code.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Components](#3-components)
4. [Prerequisites & Install](#4-prerequisites--install)
5. [Filesystem Layout](#5-filesystem-layout)
6. [Quickstart](#6-quickstart)
7. [CLI Reference](#7-cli-reference)
8. [Python API](#8-python-api)
9. [Runtime Parameters](#9-runtime-parameters)
10. [Writing a Plugin](#10-writing-a-plugin)
11. [Configuration Reference](#11-configuration-reference)
12. [Component Catalogue](#12-component-catalogue)
13. [Tier Presets](#13-tier-presets)
14. [Environment & Secrets](#14-environment--secrets)
15. [Running at Scale](#15-running-at-scale)
16. [Troubleshooting](#16-troubleshooting)
17. [API Reference](#17-api-reference)
18. [Security Considerations](#18-security-considerations)
19. [Package Structure](#19-package-structure)
20. [Appendix A: Before You Publish](#appendix-a-before-you-publish)

---

## 1. Overview

The framework gives developers a single toolkit to:

- Build **scrapers as configuration** — declare selectors, validation, and
  storage in YAML instead of writing a program per site.
- Run the **same scraper by different query** at runtime — pass a keyword, a date
  range, or nothing at all, without editing files.
- Ship **site knowledge as plugins** — self-contained folders that the framework
  discovers, validates, and isolates from one another.
- Scale from **one process to many machines** by configuration, not a rewrite.

### The problem it solves

Most scraping work is solved one of two ways:

- **A script per website** — the same download / retry / parse / save logic
  rewritten each time, and ten sites means ten things to maintain.
- **A monolithic scraper with per-site branches** — one file that grows until
  nobody will touch it.

This framework takes a third path: **the engine is already written and shared.**
A plugin contributes only what makes its site different — the URL, the selectors,
the validation rules. Adding a site is adding a folder; no framework code changes
and nothing is re-released.

---

## 2. Architecture

```
Caller (CLI · your Python app · a scheduler · a queue worker)
                            |
                            v
JobResolver  ---- loads plugin, validates runtime params, renders ${placeholders}
                            |
                            v
Configuration Loader  ---- layers defaults -> preset -> plugin config -> overrides,
                           validates names/capabilities/secrets, fingerprints result
                            |
                            v
Scraper Engine  ---- manages one job; feeds discovered URLs back in
                            |
                            v
Pipeline Runner ---- runs the stages in order, applies per-stage error policy
                            |
        +-------------------+--------------------+
        |                                        |
   fetch  <---- Middleware (retry · rate limit · proxies · auth · cache)
   parse
   discover ------> new URLs back to the Engine (or onto the Queue)
   extract
   validate
   transform
   persist
        |
        v
Repositories ---- JSON · JSON Lines · CSV · files (PDF/binary) · PostgreSQL
```

**Flow:** a caller names a plugin and passes params → the resolver produces one
fully rendered config → the engine runs each URL through the pipeline →
records land in one or more repositories.

Two things run alongside every stage:

- **Event Bus** — stages publish events; listeners turn them into console
  progress, structured logs, and metrics. A listener that raises cannot fail a
  scrape.
- **Quarantine** — records that fail in a way you chose to keep are appended to a
  review file rather than lost.

**Two execution topologies, one engine.** With no queue, discovered URLs drain in
an in-process deque (single process). With a queue configured, discovered URLs are
handed off as new jobs so N workers share the crawl. This is a configuration
switch, not a different code path.

---

## 3. Components

| Component | Role | Surface |
|---|---|---|
| **`core`** | Engine, pipeline runner, plugin loader, config loader, registry, runtime resolver, error taxonomy, event bus | Python import |
| **`components`** | Fetchers, parsers, documents, extractors, validators, transformers, repositories, middleware, stages | Referenced by name in YAML |
| **`plugins`** | Reference plugins, bundled in the wheel | Folder per site |
| **`cli`** | Command implementations and the composition root | `scraper` console script |
| **JobResolver** | Turns *(plugin + params)* into a validated, rendered config | `core.runtime` |
| **Scraper Engine** | Runs one job; manages discovered-URL feedback and the request cap | `core.engine` |
| **Pipeline Runner** | Runs stages in order with timeouts and error policy | `core.pipeline` |
| **Registry** | Name → component catalogue; validated at startup | `core.registry` |
| **Plugin Manager** | Discovers, validates, and quarantines plugins | `core.plugin` |
| **Queue / Worker** | Shared to-do list for multi-machine runs (in-memory or PostgreSQL) | `components.queue`, `core.engine.worker` |
| **MCP server** | Optional stdio MCP server exposing pipeline verbs as tools | `mcp_server/` |

---

## 4. Prerequisites & Install

### Prerequisites

| Requirement | Version | Needed for |
|---|---|---|
| Python | 3.12+ | Everything (`requires-python = ">=3.12"`) |
| pip or uv | current | Install |
| Playwright browsers | Chromium | Only the `playwright` / `authenticated_playwright` fetchers |
| PostgreSQL | 12+ | Only the `postgres` repository, queue, or shared rate limiter |

Runtime dependencies (18, all installed automatically) include `httpx`,
`lxml`, `cssselect`, `beautifulsoup4`, `pydantic`, `pyyaml`, `typer`,
`playwright`, `pymupdf`, `jsonpath-ng`, `psycopg[binary]`,
`prometheus-client`, `opentelemetry-*`, `python-dotenv`, `cryptography`, `mcp`.

### Install

```bash
pip install scraper-framework
# or
uv add scraper-framework
```

### Post-install: browser binaries

The `playwright` fetcher needs browser binaries, which pip does not install:

```bash
playwright install chromium
```

Skip this if every target site works with the plain `http` fetcher.

### Verify

```bash
scraper --help
scraper list-components
```

`list-components` prints every registered component by kind plus the load status
of each discovered plugin. If that runs, you are ready.

### Building from source

```bash
git clone https://github.com/<org>/scraper-framework.git
cd scraper-framework
uv sync                      # or: pip install -e ".[dev]"
uv run pytest                # 255 unit tests
uv run ruff check .
uv run mypy                  # strict mode
```

---

## 5. Filesystem Layout

The framework touches four locations. Only the first is required; the rest have
defaults you can override.

| What lives here | Path | Who picks it | Notes |
|---|---|---|---|
| Your plugins | `./plugins/` | **You** — via `--plugins-dir` | Directory scan; the default is `./plugins` relative to your working directory |
| Collected data | Whatever `persist.repositories[].options.path` says | **You**, per plugin | Conventionally `output/` |
| Failed records | `./quarantine/quarantine.jsonl` | Default; override with `quarantine_dir` | One JSON object per line; created on demand |
| Framework defaults | `./config/` | Optional — via `--config-dir` | Defaults, presets, environment overlays |

### The plugin folder

```text
my_plugins/
+-- acme_products/
|   +-- plugin.yaml                 # identity, tier, source approval, params contract
|   +-- config/
|   |   +-- extraction.yaml         # URLs, selectors, validation, storage
|   +-- fixtures/                   # optional: saved sample pages for tests
|   +-- extractor.py                # optional: custom components
+-- acme_news/
    +-- plugin.yaml
    +-- config/
        +-- extraction.yaml
```

### The optional config folder

Only needed if you want framework-wide defaults, tier presets, or per-environment
overlays:

```text
config/
+-- pipeline.yaml            # default stage list, error policy, max_requests
+-- middleware.yaml          # default middleware stack and options
+-- presets/
|   +-- tier_open.yaml       # minimal, polite stack
|   +-- tier_defended.yaml   # + circuit breaker, UA rotation, cookies
|   +-- tier_hostile.yaml    # + proxy rotation, tightest limits
+-- environments/
    +-- dev.yaml             # e.g. lower max_requests, shorter timeouts
    +-- prod.yaml
```

> **You do not need a `config/` folder.** Framework defaults are optional layers —
> if `--config-dir` finds nothing, your plugin's YAML is used as-is. Verified: a
> directory containing only `my_plugins/` resolves and runs correctly.
>
> **But `config/` is not shipped in the wheel** (`packages = ["core",
> "components", "plugins", "cli"]`), so a pip install gives you no presets and no
> defaults. Using `preset: tier_open` without supplying the file yourself fails
> with `config references preset 'tier_open' but no presets dir is set`. See
> [Appendix A](#appendix-a-before-you-publish).

### Working layout for a consumer project

```text
my-scrapers/
+-- pyproject.toml              # depends on scraper-framework
+-- my_plugins/                 # your plugins  (--plugins-dir my_plugins)
+-- config/                     # optional: copied presets / defaults
+-- output/                     # collected data
+-- quarantine/                 # failed records needing review
+-- run.py                      # your Python entry point
```

---

## 6. Quickstart

Generate a plugin, confirm it loads, inspect what it would run, then run it:

```bash
mkdir -p my_plugins

# 1. generate a skeleton that already passes validation
scraper scaffold new-plugin my_site --plugins-dir my_plugins

# 2. confirm the framework found it
scraper list-components --plugins-dir my_plugins
#    -> plugin: my_site v0.1.0 [open] — ok

# 3. print the fully resolved config — every startup check runs, no network
scraper resolve my_site --plugins-dir my_plugins

# 4. edit my_plugins/my_site/config/extraction.yaml, then run
scraper run-plugin my_site --plugins-dir my_plugins
```

Starting from the scaffold means you begin with something that runs, then change
one thing at a time.

> **`--plugins-dir` matters.** Plugin discovery is a **directory scan** defaulting
> to `./plugins`. Packaging your plugins as a pip distribution does **not** make
> them discoverable — see [Appendix A](#appendix-a-before-you-publish).

---

## 7. CLI Reference

| Command | Purpose |
|---|---|
| `scraper run-plugin <name>` | Resolve a plugin with runtime params and run it |
| `scraper resolve <name>` | Print the fully resolved config — no scraping |
| `scraper run <job.yaml>` | Run a standalone job file (no plugin) |
| `scraper dry-run <config.yaml>` | Run through `extract`, print records, save nothing |
| `scraper validate <config.yaml>` | Run every startup check; exit 1 on failure (CI-friendly) |
| `scraper list-components` | List components and plugin load status |
| `scraper scaffold new-plugin <name>` | Generate a plugin skeleton |
| `scraper submit <job.yaml>` | Enqueue seed URLs onto the PostgreSQL queue |
| `scraper worker [--once]` | Run a queue worker |
| `scraper quarantine list` | List failed records (trace id, stage, error) |
| `scraper quarantine inspect <trace-id>` | Print one failure in full |
| `scraper quarantine retry [--plugin X]` | Re-queue failed URLs, then clear them |
| `scraper quarantine discard` | Clear the review pile |

**Shared options:** `--plugins-dir`, `--config-dir`, `-p/--param`,
`-f/--params-file`, `--params-json`.

### The two you will use most

```bash
# preview: every startup check runs, nothing is fetched
scraper resolve my_site --plugins-dir my_plugins -p keyword=laptop

# run it
scraper run-plugin my_site --plugins-dir my_plugins -p keyword=laptop
```

Wire `scraper validate` into CI so a broken YAML fails the build, not a
production run.

---

## 8. Python API

The stable entry point for embedding is `JobResolver` — it turns
*(plugin name + params)* into a validated, fully rendered config.

```python
from pathlib import Path
from core.registry.registry import Registry
from core.runtime import JobResolver

resolver = JobResolver.from_directory(Path("my_plugins"), Registry())
resolved = resolver.resolve("my_site", {"keyword": "laptop"})

resolved.plugin    # "my_site"
resolved.params    # validated + defaulted params
resolved.config    # the config the engine will execute
```

`resolve()` raises `PluginError` if the plugin is missing, `ParamError` if the
params break the plugin's declared contract. Both derive from `ScraperError`.

### Running the pipeline

Resolving does not scrape. To execute, build the engine from the resolved config:

```python
import asyncio
from pathlib import Path

from cli.composition import build_event_bus, default_registry, register_default_stages
from core.config.loader import load_config
from core.engine.scraper_engine import ScraperEngine
from core.errors.policy import policy_from_config
from core.models.job import ScrapeJob
from core.models.scrape_request import ScrapeRequest
from core.pipeline.builder import build_pipeline
from core.pipeline.runner import PipelineRunner
from core.runtime import JobResolver


def run(plugin: str, params: dict | None = None, plugins_dir: str = "my_plugins"):
    """Resolve a plugin with params and run the full pipeline."""
    registry = default_registry()
    resolved = JobResolver.from_directory(Path(plugins_dir), registry).resolve(
        plugin, params or {}
    )

    register_default_stages(registry, resolved.config)
    config = load_config([dict(resolved.config)], registry=registry)

    bus, _ = build_event_bus()
    runner = PipelineRunner(
        build_pipeline(config.data["pipeline"], registry),
        policy_from_config(config.data),
        bus=bus,
    )
    engine = ScraperEngine(runner, config, bus=bus)
    job = ScrapeJob(requests=tuple(ScrapeRequest(url=u) for u in config.data["urls"]))
    return asyncio.run(engine.run(job))


result = run("my_site", {"keyword": "laptop"})
print(result.completed, result.aborted, result.quarantined, result.discarded)
```

`JobResult` fields: `job_id`, `completed`, `aborted`, `quarantined`, `discarded`,
`results`.

> **Verified working**: this exact block runs `news_feed` to completion —
> 3 pages scraped, pagination followed, 0 aborted.

> **This boilerplate should be one call.** Packaging should add a public
> `run_plugin()` wrapper. Until then copy the block above into your project
> rather than importing the CLI's `_`-prefixed helpers, which are internal.

### Which layer to use

| Goal | Use |
|---|---|
| Validate params, inspect the final config | `JobResolver.resolve()` |
| Run a scrape from your app | the `run()` wrapper above |
| Shell out from a job runner | `subprocess` → `scraper run-plugin` |
| Custom stage order, listeners, or sinks | build `PipelineRunner` / `ScraperEngine` yourself |

---

## 9. Runtime Parameters

Params let one plugin serve many queries without editing YAML. The plugin
declares what it accepts; the caller supplies values.

**1 — Declare in `plugin.yaml`:**

```yaml
params:
  keyword:
    type: string
    required: false
    description: "Search keyword."
  from_date:
    type: date
    required: false
    format: "%d-%m-%Y"          # optional output format for the URL
  max_results:
    type: integer
    default: 50
```

**2 — Reference in `config/extraction.yaml`:**

```yaml
urls:
  - "https://example.com/search?q=${keyword}&from=${from_date}"

engine:
  max_requests: ${max_results}
```

**3 — Supply at call time:**

```bash
scraper run-plugin my_site -p keyword=laptop -p max_results=10
scraper run-plugin my_site -f params.yaml
scraper run-plugin my_site --params-json '{"keyword":"laptop"}'
```
```python
resolver.resolve("my_site", {"keyword": "laptop", "max_results": 10})
```

Precedence, low → high: **file → JSON string → `-p` pairs**, so one `-p` can
override a saved file.

### Types and rules

| Type | Accepts |
|---|---|
| `string` | any text |
| `integer` | whole number |
| `number` | decimal |
| `boolean` | `true/false`, `1/0`, `yes/no`, `on/off` |
| `date` | ISO `YYYY-MM-DD`; emitted as ISO, or per `format` |

| Situation | Behaviour |
|---|---|
| Unknown param supplied | `ParamError`, listing what the plugin accepts |
| Required param missing | `ParamError` |
| Wrong type | `ParamError` — before any network call |
| Optional and absent | Placeholder renders as **empty string** |
| Lone placeholder (`${max_results}`) | Keeps its real type (stays an `int`) |
| Undeclared `${x}` in YAML | `ParamError` — catches typos |
| No `params:` block at all | Plugin takes no params; fully backward compatible |

> **Empty-renders-to-nothing is the "scrape everything" mechanism.** With no
> params, `?q=${keyword}` becomes `?q=`, and a `contains: "${keyword}"` rule
> matches every record. One plugin covers both filtered and unfiltered runs with
> no engine special-casing.

---

## 10. Writing a Plugin

Plugins live in **your** repo, not inside the installed package.

### `plugin.yaml`

```yaml
name: acme_products              # lowercase, digits, underscores; must be unique
version: 0.1.0
description: "Acme product catalogue."
tier: open                       # open | defended | hostile
source_approval: "docs/source_approval.md#SRC-0001"   # required, non-empty
config_files:
  - config/extraction.yaml
params: {}                       # optional runtime contract (section 9)
components: {}                   # optional custom Python components
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Matches `^[a-z][a-z0-9_]*$`; collides → quarantined |
| `version` | yes | Stamped onto every record's provenance |
| `source_approval` | yes | Must be non-empty — a deliberate compliance gate |
| `tier` | no | Difficulty hint; defaults to `open` |
| `config_files` | no | Defaults to `["config/extraction.yaml"]`; merged in order |
| `params` | no | Runtime parameter contract |
| `components` | no | `kind → {name: "file.py:ClassName"}` |

> Unknown keys are **rejected** — a typo quarantines the plugin and names the
> offending key.

### Shipping custom Python components

When YAML is not enough, a plugin can contribute code:

```yaml
components:
  extractor:
    fancy: "extractor.py:FancyExtractor"
```

The class is imported from the plugin folder, checked against the contract for
its kind, and registered as `acme_products.fancy` — namespaced, so it cannot
collide. Reference it in YAML as `extractor: acme_products.fancy`.

Component kinds: `fetcher`, `parser`, `document`, `extractor`, `validator`,
`transformer`, `repository`, `middleware`, `stage`, `login_provider`.

> Custom components must construct with **no arguments** and satisfy their
> contract, or the plugin is quarantined at load time.

### Plugin isolation

A plugin failing any load step — bad manifest, missing config file, name
collision, non-conforming component — is **quarantined with a reason** while
every other plugin loads normally. Inspect with `scraper list-components`.

---

## 11. Configuration Reference

Everything below goes in `config/extraction.yaml`. Unknown top-level keys are
allowed, so components can carry their own sections.

### Pipeline and seeds

```yaml
# Stages to run, in order. Omit what you don't need.
pipeline: [fetch, parse, discover, extract, validate, transform, persist]

# Seed URLs — each starts its own pass through the pipeline.
urls:
  - "https://example.com/listing"

# Hard cap on pages per job. Counts listing pages too — always set it.
engine:
  max_requests: 50

# Stamped onto every record's provenance.
plugin:
  name: acme_products
  version: 0.1.0
```

### Fetching

```yaml
# http | playwright | authenticated_playwright | local_file
fetcher: http
fetcher_options:
  timeout_s: 30
  default_headers:
    User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    Referer: "https://example.com/"

# Playwright-only options:
#   wait_after_s: 3.0        # settle time after load
#   user_agent: "..."
```

| Fetcher | Use when | Speed |
|---|---|---|
| `http` | Data is present in the raw response | Fast |
| `playwright` | Page needs a browser to render content | Slow |
| `authenticated_playwright` | Login required first | Slow |
| `local_file` | Testing against saved fixtures | Instant |

### Middleware

```yaml
# First entry is the outermost layer. Retry sits outside rate_limit so every
# retry re-enters the stack and must take a rate-limit token.
middleware: [retry, rate_limit, block_detection, observability]

middleware_options:
  retry:      {max_attempts: 3, base_delay_s: 0.5, max_delay_s: 30.0}
  rate_limit: {rate: 1.0, burst: 2}       # tokens per second, per domain
```

### Parsing and discovery

```yaml
# auto (default, routes by content type) | html | json | xml | pdf | text
parser: auto

discover:
  next_url:
    kind: xpath
    query: "//table[@id='rows']//a/@href"
  url_template: "https://example.com{value}"   # optional wrapper; {value} substituted
  max_new: 100                                 # cap per page
```

> Relative URLs are joined to the current page automatically. A page yielding no
> match simply ends the chain — **this is not an error**, which is why a broken
> selector looks exactly like reaching the last page.

### Extraction

```yaml
extract:
  schema_version: "1"
  spec:
    title:
      kind: css                    # css | xpath | regex | jsonpath | text
      query: "h1"
      cleanup: [collapse_whitespace, strip]
      required: true               # default
    price:
      kind: css
      query: "span.price"
      cleanup: [strip_currency, to_float]
      required: false              # missing -> None, page still saved
    product_id:
      kind: regex
      query: "/p/(\\d+)"
      against: url                 # match the URL, not the document
```

**Selector kind must match the document type**, or startup fails naming the field:

| Document | Allowed kinds |
|---|---|
| HTML | `css`, `xpath`, `regex`, `text` |
| XML | `xpath`, `regex`, `text` |
| JSON | `jsonpath`, `regex`, `text` |
| PDF / text | `regex`, `text` |

**Cleanup functions**, applied in listed order: `strip`, `lower`, `upper`,
`collapse_whitespace`, `strip_currency`, `strip_trailing_dot`,
`format_inr_price`, `short_title`, `to_float`, `to_int`.

> Order matters: `[strip_currency, to_float]` works; the reverse fails because
> `"₹4,999"` is not yet numeric. Regex in YAML needs doubled backslashes (`\\d`).

### Validation and transformation

```yaml
validate:
  validators:
    - name: required_field
      options: {fields: [title, price]}
    - name: business_rule
      options:
        rules:
          - {field: price, op: ">", value: 0}
    - name: duplicate
      options: {key_fields: [product_id]}

transform:
  transformers:
    - name: date
      options: {fields: [published], input_formats: ["%d %B %Y"]}
    - name: field_enricher
      options: {constants: {source: acme}}
```

`business_rule` ops: `>` `>=` `<` `<=` `==` `!=` `in` `not_in` `contains`
`not_contains`. `contains` is case-insensitive; a field with no value is skipped,
not failed.

### Error policy

```yaml
error_policy:
  default: abort                 # fallback when no rule matches
  max_retries: 2
  on_retry_exhausted: abort
  stages:
    fetch:
      FetchError: retry
    extract:
      ExtractionError: skip
    validate:
      ValidationError: discard
    persist:
      PersistError: skip
```

Shape: **stage → exception class name → action**. Lookup walks the exception's
parent classes, so `ScraperError` catches everything beneath it.

| Action | Effect |
|---|---|
| `retry` | Retry up to `max_retries` |
| `skip` | Abandon this page, continue the job |
| `discard` | Drop silently — no quarantine file (use for filtering) |
| `quarantine` | Write the failure for review, continue |
| `abort` | Stop the whole job |

> **Set this explicitly.** The default is `abort`, so without a policy the first
> failing page kills the run. In a crawl, listing pages routinely fail `extract`,
> so `ExtractionError: skip` is nearly always required.

### Persistence

```yaml
persist:
  repositories:
    - name: json
      options:
        path: "output/products.json"
        mode: upsert               # update matching records instead of duplicating
        key_fields: [product_id]   # what makes a record unique
        indent: 2
    - name: file                   # download binaries (PDFs, images)
      options:
        output_dir: "output/pdfs"
        url_field: "pdf_link"      # field holding the URL to fetch
        filename_field: "title"
        date_field: "date"
    - name: postgres
      options:
        dsn: "secret://DATABASE_URL"
        table: "products"
```

Several repositories can run together. The `file` repository resolves links
recursively: a direct `.pdf`, a `?file=…pdf` wrapper, or an HTML page whose
`<iframe>` points at the real PDF.

### Other keys

```yaml
stage_timeouts: {fetch: 30, parse: 10}    # seconds per stage
quarantine_dir: "quarantine"              # where failures are written
preset: tier_open                         # inherit a middleware profile (section 13)
```

---

## 12. Component Catalogue

Names to use in YAML.

| Kind | Available names |
|---|---|
| **Fetchers** | `http`, `playwright`, `authenticated_playwright`, `local_file` |
| **Parsers** | `auto` (default), `html`, `json`, `xml`, `pdf`, `text` |
| **Extractors** | `spec_driven` (default), `table` |
| **Validators** | `required_field`, `type`, `schema`, `business_rule`, `duplicate` |
| **Transformers** | `date`, `currency`, `text_cleaner`, `unit_converter`, `enum_mapper`, `field_enricher` |
| **Repositories** | `json`, `jsonl`, `csv`, `file`, `postgres` |
| **Middleware** | `retry`, `rate_limit`, `distributed_rate_limit`, `cache`, `proxy_rotation`, `ua_rotation`, `cookie_manager`, `block_detection`, `circuit_breaker`, `observability`, `cost_tracker` |

### Registering your own

Outside a plugin, register directly against the registry:

```python
from cli.composition import default_registry

registry = default_registry()
registry.register("repository", "my_warehouse", MyWarehouseRepository)
```

`- name: my_warehouse` then works in YAML. Names are validated at startup, so a
typo fails immediately rather than mid-scrape.

---

## 13. Tier Presets

A preset is a named middleware profile matching a site's difficulty. Set
`preset:` in your config and the preset loads first, with your config merged on
top.

```yaml
preset: tier_defended
# your keys override anything the preset set
```

| Preset | Middleware stack | Rate | Use for |
|---|---|---|---|
| `tier_open` | retry, rate_limit, block_detection, observability | 2.0/s, burst 4 | Sites with no defences |
| `tier_defended` | + circuit_breaker, cache, ua_rotation, cookie_manager, cost_tracker | 0.5/s, burst 2 | Rate- or UA-sensitive sites |
| `tier_hostile` | + proxy_rotation | 0.25/s, burst 1 | Fingerprinting / CAPTCHA sites |

The presets correspond to the `tier` field in `plugin.yaml`. `tier_hostile`
requires supplying your own `proxy_rotation.proxies` list.

> **Presets need a `config/presets/` directory.** They are not in the wheel, so a
> pip install must supply them — otherwise `preset: tier_open` fails with
> `no presets dir is set`. Copy the three files from the repo, or inline the
> middleware you need.

---

## 14. Environment & Secrets

Never put credentials in YAML. Use a `secret://` reference:

```yaml
persist:
  repositories:
    - name: postgres
      options:
        dsn: "secret://DATABASE_URL"
```

Values resolve from the environment (`.env` is loaded automatically by the CLI) at
component-build time, so secrets never reach the config fingerprint or logs.

> **Enforced, not advisory.** Any key whose name looks credential-like
> (`password`, `token`, `api_key`, `secret`, `credential`, …) holding a plaintext
> value raises `ConfigError` at startup. Keys ending `_selector` are exempt, since
> a `password_selector` is a CSS selector, not a secret.

**Environment variables:** `DATABASE_URL` (PostgreSQL queue, repository, shared
rate limiter) plus whatever your own `secret://` refs name.

### Config layering

Later layers win, per key:

```
framework defaults (config/*.yaml)  ->  preset  ->  plugin config  ->  runtime params / overrides
```

The merged result is validated (shape, component names, selector capabilities, no
plaintext secrets) and gets a **SHA-256 fingerprint** recorded with every record,
so you can always tell which settings produced a given row.

---

## 15. Running at Scale

The same engine runs single-process or distributed — configuration, not code.

**Single process** (default): discovered URLs drain in an in-process deque.

**Distributed:** discovered URLs go to a PostgreSQL queue that many workers share.

```bash
export DATABASE_URL="postgresql://user:pass@host/db"

scraper submit job.yaml        # enqueue seed URLs
scraper worker                 # run a worker (repeat on other machines)
scraper worker --once          # drain the queue, then exit
```

Use `distributed_rate_limit` middleware so the whole fleet shares one budget
rather than each worker limiting independently.

**Observability:** the event bus publishes stage and job events. The CLI attaches
structured logging, console progress, and Prometheus-style metrics; a Grafana
dashboard ships in `observability/grafana_dashboard.json`.

---

## 16. Troubleshooting

### Install and import

| Symptom | Cause | Fix |
|---|---|---|
| `scraper: command not found` | Script dir not on `PATH`, or wrong venv | Activate the venv, or run `python -m cli.main` |
| `ModuleNotFoundError: playwright` | Browsers not installed | `playwright install chromium` |
| `Executable doesn't exist at .../chrome` | Same | `playwright install chromium` |
| `ModuleNotFoundError: core` | Not installed, or shadowed by your own `core/` folder | Reinstall; don't name a local package `core` |
| Requires Python 3.12 | Older interpreter | Upgrade |

### Plugin discovery

| Symptom | Cause | Fix |
|---|---|---|
| `no loaded plugin named 'x'` | Not found by the directory scan | Pass `--plugins-dir`; confirm with `list-components` |
| Plugin absent from `list-components` | Folder has no `plugin.yaml` | Add the manifest |
| `QUARANTINED: ...` | Failed a load step | Read the printed reason |
| `plugin name 'x' is already loaded (collision)` | Two manifests share a `name` | Rename one |
| `declared config file missing` | `config_files` path wrong | Fix the path |
| `source_approval` error | Field empty or absent | Provide a non-empty reference |
| Pip-installed plugin package ignored | Entry-point discovery is not wired in | Use `--plugins-dir` (Appendix A) |

### Parameters

| Symptom | Fix |
|---|---|
| `unknown parameter(s) [...]` | The message lists accepted names — check `plugin.yaml` |
| `required parameter 'x' was not supplied` | Supply it, or make it optional |
| `is not a valid integer/date` | Fix the value; dates are `YYYY-MM-DD` |
| `config references ${x} but the plugin declares no such param` | Declare it, or fix the typo |
| Params seem ignored | You ran `scraper run` (job file) instead of `run-plugin` |
| A filter matches nothing | Empty renders match everything; a wrong value matches nothing — check spelling and case |

### Startup validation

All of these fire **before** any network call. Catch them with `scraper resolve`
or `scraper validate`.

| Message | Fix |
|---|---|
| `field 'x' uses selector kind 'css', but PdfDocument only supports [...]` | Match kind to document type (§11) |
| `unknown cleanup 'x'` | The message lists valid names |
| `config has no pipeline` | Add a non-empty `pipeline` |
| `pipeline has an extract stage but config has no 'extract' section` | Add the section, or drop the stage |
| `pipeline has a persist stage but no repositories are configured` | Add a repository |
| `pipeline has a discover stage but config has no 'discover.next_url'` | Add it, or drop the stage |
| `unknown component name` | Check the catalogue (§12) or register yours |
| `looks like a credential but is plaintext` | Use `secret://` |
| `config references preset 'x' but no presets dir is set` | Supply `config/presets/` (§13) |

### Runtime

| Symptom | Cause | Fix |
|---|---|---|
| Job dies on the first page | No `error_policy`; default is `abort` | Add per-stage actions (§11) |
| Only seed URLs scraped | `discover` missing, or its selector matched nothing (**not an error** — looks like the last page) | Add the stage; verify the selector |
| Exactly `max_requests` records | Hit the cap — it counts listing pages too | Raise `engine.max_requests` |
| Every field empty | Content is JavaScript-rendered | Switch to `fetcher: playwright` |
| Records vanish silently | `ValidationError: discard` | Switch to `quarantine` while debugging |
| Output empty, no errors | Everything skipped or discarded | Check the run summary counts |
| Sudden failures mid-run | Rate limited or blocked | Lower `rate`; add `block_detection`, `circuit_breaker`, or a stricter preset |
| `PersistError` on a binary download | Link not resolvable | Verify the `url_field` holds a real URL |
| `StageTimeoutError` | Stage exceeded its limit | Raise `stage_timeouts` |

### Debugging order

1. **`scraper resolve <plugin>`** — catches config and param errors instantly.
2. **`engine.max_requests: 2`** — keep iterations fast.
3. **`scraper dry-run <config>`** — runs to `extract` and prints records; saves
   nothing. Best way to see what selectors actually return.
4. **Switch failures to `quarantine`**, then `scraper quarantine list` and
   `inspect <trace-id>` for the real reason.
5. **`scraper list-components`** — confirm the plugin loaded and nothing is
   quarantined.

---

## 17. API Reference

### `core.runtime`

```python
from core.runtime import JobResolver, ResolvedRuntimeConfig, render_template, validate_params
```

| Object | Signature / fields |
|---|---|
| `JobResolver(manager)` | Wraps a `PluginManager` |
| `JobResolver.from_directory(dir, registry)` | Loads plugins, returns a resolver |
| `.resolve(plugin, params=None)` | → `ResolvedRuntimeConfig`; raises `PluginError` / `ParamError` |
| `ResolvedRuntimeConfig` | `.plugin`, `.params`, `.config` |
| `validate_params(contract, supplied)` | → coerced dict |
| `render_template(value, values, declared=set())` | Placeholder substitution |

### Other entry points

| Import | Purpose |
|---|---|
| `core.plugin.manager.PluginManager` | `load_all(dir)`, `get(name)`, `.loaded`, `.quarantined` |
| `core.config.loader.load_config` | Layered load + validation → `ResolvedConfig` |
| `core.engine.scraper_engine.ScraperEngine` | `await run(job)` → `JobResult` |
| `core.models.job.ScrapeJob` | `to_dict()` / `from_dict()` — queue-safe |
| `cli.composition.default_registry` | Registry with all built-ins |
| `cli.composition.register_default_stages` | Wire the seven stages from config |

### Exceptions

All derive from `ScraperError`, so one `except ScraperError` catches everything:

`ConfigError` · `PluginError` · `ParamError` · `FetchError` · `ParseError` ·
`ExtractionError` · `ValidationError` · `TransformError` · `PersistError` ·
`AuthError` · `StageTimeoutError` · `CapabilityError`

`FetchError` carries `.transient` and `.blocked`; `ExtractionError` carries
`.field`.

---

## 18. Security Considerations

- **Credentials in config.** Never write secrets into YAML. Use `secret://ENV_VAR`;
  the loader rejects plaintext values under credential-looking keys at startup.
- **`.env` files.** The CLI loads `.env` automatically. Keep it out of version
  control and restrict file permissions.
- **Config fingerprints exclude secrets** by design — resolution happens after
  fingerprinting, so credentials never reach logs or record provenance.
- **Source approval is mandatory.** Every plugin must name a non-empty
  `source_approval`. This is a mechanical gate, not a convention — treat it as
  the record that scraping a given site was reviewed.
- **Respect target sites.** Keep `rate_limit` enabled, set a truthful
  `User-Agent`, and check the site's terms and `robots.txt`. Presets exist so the
  polite default is the easy default.
- **Proxy credentials** for `tier_hostile` / `proxy_rotation` belong in
  environment variables via `secret://`, never inline.
- **Quarantine files contain scraped payloads.** `quarantine/quarantine.jsonl`
  holds context snapshots that may include sensitive page content — secure or
  rotate it like any other data file.
- **PostgreSQL DSNs** must come from `secret://DATABASE_URL`, and the queue
  database should not be exposed publicly.

---

## 19. Package Structure

What the installed distribution contains:

```text
scraper-framework 0.1.0
+-- core/                          # engine + rules (no site knowledge)
|   +-- engine/                    # ScraperEngine, Worker
|   +-- pipeline/                  # Runner, Context, builder
|   +-- plugin/                    # manifest, discovery, manager
|   +-- config/                    # loader, schema, capability check
|   +-- runtime/                   # JobResolver, params, template
|   +-- registry/ contracts/ models/ errors/ events/ scheduler/ observability/
|
+-- components/                    # interchangeable parts, referenced by name
|   +-- fetchers/ parsers/ documents/ extractors/ validators/
|   +-- transformers/ repositories/ middleware/ stages/ listeners/
|   +-- queue/ auth/ secrets/ quarantine/ scheduler/
|
+-- plugins/                       # reference plugins (bundled)
|   +-- sebi_circulars/ sebi/ flipkart/ beedzp/
|   +-- news_feed/ ecommerce_example/            # loadable: have plugin.yaml
|   +-- amazon_products/ imdb_movies/ mas_circulars/   # manifest.yaml only — not discovered
|
+-- cli/                           # console script implementation
    +-- main.py                    # commands
    +-- composition.py             # composition root: registry + stage wiring
    +-- scaffold.py                # plugin generator

Console script:  scraper -> cli.main:app
```

**Not in the wheel** (repo-only): `config/` (defaults, presets, environments),
`tests/`, `docs/`, `observability/`, `mcp_server/`.

---

## Appendix A: Before You Publish

Three gaps worth closing before other teams depend on this package. All verified
against the current code.

**1. Plugin discovery only scans directories.**
`PluginManager.load_all()` calls `scan_directory()` only. A helper for
entry-point discovery exists — `core.plugin.discovery.entry_point_candidates`,
group `scraper_framework.plugins` — but **nothing calls it**. A consumer who
packages plugins as a pip distribution will find them silently ignored and must
pass `--plugins-dir` with a real filesystem path. Wiring that helper into
`load_all` would let plugins ship as packages.

**2. There is no public "run" function.**
`core.runtime` exports `JobResolver`, but running a scrape needs the ~15 lines in
§8. The CLI holds this logic in `cli.main._resolve_plugin` / `_build_engine` /
`_job_from_config` — private helpers consumers should not import. A public
`run_plugin(plugin, params, ...)` in `core.runtime`, with the CLI calling it too,
would give one supported code path for both.

**3. `config/` is not packaged.**
`packages = ["core", "components", "plugins", "cli"]` excludes `config/`, so a
pip install ships no default `pipeline.yaml` / `middleware.yaml` and no tier
presets. Plugin configs still work standalone (verified), but `preset:
tier_open` fails with `config references preset 'tier_open' but no presets dir is
set`. Either include `config/` in the wheel and resolve presets relative to the
package, or document that consumers must supply their own.

Also worth deciding at package time: the 18 runtime dependencies are all `>=`
floors — pin or cap them deliberately; document the `playwright install chromium`
step in the README; and confirm the reference plugins should ship in the
distribution (they do today). Note that `amazon_products`, `imdb_movies`, and
`mas_circulars` carry a `manifest.yaml` rather than a `plugin.yaml`, so the plugin
manager does not discover them — decide whether to convert or drop them before
publishing.
