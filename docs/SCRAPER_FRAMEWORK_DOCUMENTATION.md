# Scraper Framework — Complete Technical Documentation

> **Version:** 0.1.0 | **Language:** Python 3.12+ | **Package Manager:** `uv`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Project Structure](#2-project-structure)
3. [How It Works — End-to-End Flow](#3-how-it-works--end-to-end-flow)
4. [Pipeline Stages](#4-pipeline-stages)
5. [Configuration System](#5-configuration-system)
6. [Plugins](#6-plugins)
7. [Components — Deep Dive](#7-components--deep-dive)
8. [Middleware Stack](#8-middleware-stack)
9. [Repositories (Storage)](#9-repositories-storage)
10. [Error Handling & Quarantine](#10-error-handling--quarantine)
11. [CLI Commands Reference](#11-cli-commands-reference)
12. [Writing a New Plugin](#12-writing-a-new-plugin)
13. [Real Examples](#13-real-examples)
14. [Technology Stack & Dependencies](#14-technology-stack--dependencies)
15. [Observability & Events](#15-observability--events)
16. [Jira / Confluence Context](#16-jira--confluence-context)

---

## 1. Overview

The **Scraper Framework** is a modular, config-driven web scraping system built in Python. It lets you scrape any website — HTML pages, JavaScript-heavy SPAs, PDFs, or authenticated portals — **without writing code**. All scraping logic is expressed entirely in YAML configuration files.

### Key Design Principles

| Principle | Description |
|-----------|-------------|
| **Config-driven** | Every scrape is defined in a YAML file — no per-site Python code needed |
| **Plugin-based** | Each target website is a self-contained plugin folder |
| **Pipeline architecture** | Data flows through ordered, composable stages: `fetch → parse → discover → extract → validate → transform → persist` |
| **Middleware onion** | Cross-cutting concerns (retries, rate limiting, auth, proxies) wrap the fetcher in configurable layers |
| **Multi-output** | Same scrape can write to JSON, CSV, JSONL, and PostgreSQL simultaneously |
| **Extensible** | New fetchers, parsers, extractors, validators, transformers, and repositories are registered via the registry without touching core code |

---

## 2. Project Structure

```
scraper_framework/
│
├── cli/                        # Command-line interface (Typer)
│   ├── main.py                 # Entry point: run, validate, dry-run, worker, quarantine
│   ├── composition.py          # Wires together registry, event bus, stages
│   └── scaffold.py             # Generates new plugin boilerplate
│
├── core/                       # Stable contracts & engine (never changes for new sites)
│   ├── config/                 # YAML config loading & layered merging
│   ├── contracts/              # Abstract interfaces: Fetcher, Parser, Extractor, etc.
│   ├── engine/                 # ScraperEngine: drives the job queue over the pipeline
│   ├── errors/                 # Custom exceptions, error policy, quarantine records
│   ├── events/                 # Event bus: emits lifecycle events for observability
│   ├── middleware_runner.py    # Composes middleware onion around a fetcher
│   ├── models/                 # Data models: ScrapeRequest, ScrapeJob, Record
│   ├── observability/          # Tracing spans (OpenTelemetry)
│   ├── pipeline/               # PipelineRunner, PipelineBuilder, Context
│   ├── plugin/                 # PluginManager: loads & validates plugin manifests
│   ├── registry/               # Registry: named lookup of all components
│   └── scheduler/              # Cron-style job scheduling
│
├── components/                 # Swappable implementations
│   ├── auth/                   # form_login.py, token_login.py, session_store.py
│   ├── documents/              # HTML document, JSON document wrappers
│   ├── extractors/             # CSS/XPath/JSONPath field extractors
│   ├── fetchers/               # http_fetcher.py, playwright_fetcher.py, local_file_fetcher.py
│   ├── listeners/              # Event listeners for logging & Prometheus metrics
│   ├── middleware/             # retry, rate_limit, block_detection, auth, proxy_rotation, etc.
│   ├── parsers/                # html_parser.py, pdf_parser.py, auto_parser.py
│   ├── quarantine/             # file_sink.py — stores failed records for review
│   ├── queue/                  # postgres_queue.py — distributed job queue
│   ├── repositories/           # json, csv, jsonl, postgres repositories
│   ├── scheduler/              # cron_scheduler.py
│   ├── secrets/                # env_provider.py — reads secrets from environment
│   ├── stages/                 # fetch_stage.py, parse_stage.py, … persist_stage.py
│   ├── transformers/           # Field transformation implementations
│   └── validators/             # required_field, regex, schema validators
│
├── plugins/                    # One folder per website to scrape
│   ├── imdb_movies/            # IMDb Top 250 movies
│   ├── amazon_products/        # Amazon product listings
│   ├── sebi_circulars/         # SEBI PDF circulars
│   ├── amfi_circulars/         # AMFI circulars
│   ├── mas_circulars/          # MAS circulars
│   ├── beedzp/                 # Beedzp schemes
│   └── news_feed/              # RSS/news feed scraper
│
├── config/                     # Global defaults (all plugins inherit these)
│   ├── pipeline.yaml           # Default stage order + error policy
│   ├── middleware.yaml         # Default middleware stack + options
│   ├── environments/           # Dev / staging / prod environment overrides
│   └── presets/                # Named config presets (reusable snippets)
│
├── output/                     # Default output directory for scraped data
│   ├── imdb_top_movies.json
│   ├── imdb_top_movies.csv
│   ├── amazon_bestsellers.json
│   ├── sebi_circulars.jsonl
│   └── pdfs/                   # Downloaded PDF files
│
├── quarantine/                 # Failed records saved here for manual review
├── tests/                      # Automated test suite (pytest)
├── pyproject.toml              # Dependencies, build system, tool config
└── .env                        # Secrets: API keys, DB DSNs (never committed)
```

---

## 3. How It Works — End-to-End Flow

Below is the complete journey of a single URL from command to output:

```
User runs:
  uv run scraper run plugins/imdb_movies/config/extraction.yaml
                            │
                    ┌───────▼───────┐
                    │  CLI (main.py) │
                    │  loads YAML    │
                    │  builds engine │
                    └───────┬───────┘
                            │ ScrapeJob (list of seed URLs)
                    ┌───────▼──────────┐
                    │  ScraperEngine   │
                    │  (core/engine)   │
                    │  dequeues URLs   │
                    └───────┬──────────┘
                            │ one URL at a time
                    ┌───────▼──────────────────────────────────────┐
                    │            PipelineRunner                     │
                    │  runs each stage in order on the Context      │
                    │                                               │
                    │  [FETCH] → [PARSE] → [DISCOVER]              │
                    │                          │                    │
                    │                 (new URLs → queue)            │
                    │  [EXTRACT] → [VALIDATE] → [TRANSFORM]         │
                    │                               │               │
                    │                          [PERSIST]            │
                    └──────────────────────────────────────────────┘
                                        │
                          ┌─────────────┼─────────────┐
                          ▼             ▼             ▼
                    output/*.json  output/*.csv  output/*.jsonl
                                  (or PostgreSQL)
```

### What Happens at Each Run

1. **CLI reads YAML** — merges global defaults + plugin config
2. **Engine creates a job** from the `urls` list in the YAML
3. **Each URL enters the pipeline** as a `Context` object
4. **Fetch Stage** — downloads the page (HTTP or Playwright browser)
5. **Parse Stage** — converts raw HTML/PDF bytes into a structured Document
6. **Discover Stage** (optional) — finds new links, pushes them to the queue
7. **Extract Stage** — pulls field values using CSS/XPath/JSONPath selectors
8. **Validate Stage** — checks required fields, regex patterns, custom rules
9. **Transform Stage** — normalizes / cleans field values
10. **Persist Stage** — writes the record to all configured repositories
11. **Errors** — routed per error policy: retry, skip, quarantine, or abort

---

## 4. Pipeline Stages

The pipeline is an **ordered list of stages**. Each stage receives a `Context` object, modifies it, and returns it.

```yaml
# in any plugin config:
pipeline: [fetch, parse, discover, extract, validate, transform, persist]
```

You can add, remove, or reorder stages (e.g., remove `discover` for single-page scrapes).

### Stage Reference

#### `fetch` — Downloads the Page

| Item | Detail |
|------|--------|
| **File** | `components/stages/fetch_stage.py` |
| **What it does** | Runs the configured fetcher through the middleware stack |
| **Input** | `ctx.request` (URL + headers + metadata) |
| **Output** | `ctx.response` (raw bytes, status code, headers) |
| **On error** | Transient `FetchError` → retry; permanent → abort |

**Config:**
```yaml
fetcher: playwright          # or: http, local_file
fetcher_options:
  timeout_s: 60
  user_agent: "Mozilla/5.0 ..."
  wait_after_s: 3.0          # wait for JS to render
```

#### `parse` — Converts Raw Bytes to a Document

| Item | Detail |
|------|--------|
| **File** | `components/stages/parse_stage.py` |
| **What it does** | Detects content type (HTML / PDF / JSON) and builds a queryable Document |
| **Parsers** | `auto` (detect automatically), `html`, `pdf` |
| **Input** | `ctx.response` |
| **Output** | `ctx.document` |

#### `discover` — Finds New URLs to Scrape

| Item | Detail |
|------|--------|
| **File** | `components/stages/discover_stage.py` |
| **What it does** | Runs an XPath/CSS/JSONPath query to extract links and pushes them into the engine queue |
| **Use case** | Listing pages → detail pages (e.g., IMDb chart → individual movie pages) |

**Config:**
```yaml
discover:
  next_url:
    kind: xpath
    query: "//a[contains(@href, '/title/tt') and contains(@href, 'ref_=chttp_t_')]/@href"
```

#### `extract` — Pulls Field Values

| Item | Detail |
|------|--------|
| **File** | `components/stages/extract_stage.py` |
| **What it does** | Applies each field's selector query and cleanup rules; builds a `Record` |
| **Selector kinds** | `css`, `xpath`, `jsonpath`, `regex` |
| **Input** | `ctx.document` |
| **Output** | `ctx.record` (dict of field → value) |

**Config:**
```yaml
extract:
  schema_version: "1"
  spec:
    title:
      kind: css
      query: "h1"
      cleanup: [collapse_whitespace, strip]
    rating:
      kind: css
      query: "div[data-testid='hero-rating-bar__aggregate-rating__score']"
      required: false
    director:
      kind: xpath
      query: "//li[@data-testid='title-pc-principal-credit']//a[1]/text()"
      required: false
```

**Cleanup functions:**

| Cleanup | Effect |
|---------|--------|
| `strip` | Remove leading/trailing whitespace |
| `collapse_whitespace` | Replace multiple spaces/newlines with single space |
| `lower` | Convert to lowercase |
| `upper` | Convert to uppercase |
| `replace_newlines` | Replace newlines with spaces |

#### `validate` — Ensures Data Quality

**Config:**
```yaml
validate:
  validators:
    - name: required_field
      options: {fields: [title, rating]}
```

Built-in validators: `required_field`, `regex`, `schema`

#### `transform` — Cleans & Normalizes Data

Applied after extraction — date formatting, unit conversion, value normalization.

#### `persist` — Saves the Record

**Config:**
```yaml
persist:
  repositories:
    - name: json
      options:
        path: "output/imdb_top_movies.json"
        mode: upsert
        key_fields: [title]
        indent: 2
    - name: csv
      options:
        path: "output/imdb_top_movies.csv"
        mode: upsert
        key_fields: [title]
```

---

## 5. Configuration System

### Layered Config Merging

```
config/pipeline.yaml        ← Global defaults (error policy, default stage list)
        +
config/middleware.yaml      ← Global middleware defaults
        +
plugins/<name>/config/extraction.yaml   ← Plugin-specific overrides
        =
ResolvedConfig (final merged config)
```

### Complete Config Key Reference

```yaml
pipeline: [fetch, parse, discover, extract, validate, transform, persist]
urls:
  - "https://example.com/page1"
fetcher: playwright          # http | playwright | local_file
fetcher_options:
  timeout_s: 60
  user_agent: "..."
  wait_after_s: 3.0
middleware: [retry, rate_limit, block_detection, observability]
middleware_options:
  retry:
    max_attempts: 3
    base_delay_s: 0.5
    max_delay_s: 30.0
  rate_limit:
    rate: 1.0               # requests per second per domain
    burst: 2
engine:
  max_requests: 11          # 1 listing + 10 detail pages
plugin:
  name: imdb_movies
  version: 0.1.0
discover:
  next_url:
    kind: xpath | css | jsonpath
    query: "..."
extract:
  schema_version: "1"
  spec:
    field_name:
      kind: css | xpath | jsonpath | regex
      query: "selector"
      cleanup: [strip, collapse_whitespace]
      required: true | false
validate:
  validators:
    - name: required_field
      options: {fields: [field1, field2]}
error_policy:
  default: abort
  max_retries: 2
  on_retry_exhausted: abort
  stages:
    extract:
      ExtractionError: skip
    validate:
      ValidationError: skip
    persist:
      PersistError: skip
persist:
  repositories:
    - name: json | csv | jsonl | postgres
      options:
        path: "output/filename.json"
        mode: upsert | append
        key_fields: [field1]
        indent: 2
```

### Config Fingerprint

Every merged config gets a **SHA-256 fingerprint** stamped into every scraped record so you can always trace which config version produced a record.

---

## 6. Plugins

### What is a Plugin?

A plugin is a **self-contained folder** under `plugins/` that targets one specific website:

```
plugins/my_plugin/
├── manifest.yaml              ← Plugin identity & capabilities
└── config/
    └── extraction.yaml        ← Full scraping config
```

### Plugin Manifest

```yaml
name: imdb_movies
version: 0.1.0
description: "IMDb Top Movies scraper plugin."
author: Scraper Framework Team
entrypoint: config/extraction.yaml
capabilities:
  - fetcher:playwright
  - parser:auto
  - repository:json
```

### Available Plugins

| Plugin | Target Site | Data Scraped | Output Format |
|--------|-------------|--------------|---------------|
| `imdb_movies` | IMDb Top 250 | Title, Rating, Year, Director, Summary, Poster | JSON + CSV |
| `amazon_products` | Amazon search results | Product name, Price, Rating, Reviews | JSON + CSV |
| `sebi_circulars` | SEBI website | Circular title, date, PDF content | JSONL |
| `amfi_circulars` | AMFI website | Regulatory notices | JSONL |
| `mas_circulars` | MAS website | Regulatory circulars | JSONL |
| `beedzp` | Beedzp | Scheme names, categories | JSON + CSV |
| `news_feed` | RSS/News feeds | Article titles, links, publish dates | JSON |

### Creating a New Plugin

```bash
uv run scraper scaffold new-plugin my_site
```

---

## 7. Components — Deep Dive

### 7.1 Fetchers

| Fetcher | Best For |
|---------|----------|
| `http` | Static HTML pages, APIs (no JavaScript) |
| `playwright` | JavaScript-rendered SPAs, dynamic pages (uses Chromium) |
| `local_file` | Testing with local HTML/PDF files |

### 7.2 Parsers

| Parser | Handles | Auto-detected from |
|--------|---------|-------------------|
| `html` | HTML pages | `Content-Type: text/html` |
| `pdf` | PDF documents | `.pdf` extension or `application/pdf` |
| `auto` | Either — detects automatically | — |

### 7.3 Extractors

| Kind | Syntax | Use Case |
|------|--------|----------|
| `css` | CSS selector string | HTML element text content |
| `xpath` | XPath 1.0 expression | HTML attributes, complex node paths |
| `jsonpath` | JSONPath (`$.key`) | JSON API responses |
| `regex` | Regular expression | Text pattern matching |

### 7.4 Auth Components

For websites requiring login:

| Auth Type | File | How it works |
|-----------|------|-------------|
| `form_login` | `components/auth/form_login.py` | Fills login form via Playwright, captures session cookies |
| `token_login` | `components/auth/token_login.py` | POSTs credentials to API, stores Bearer token |
| `session_store` | `components/auth/session_store.py` | Caches and reuses sessions across requests |

**Config:**
```yaml
auth:
  provider: form_login
  options:
    login_url: "https://example.com/login"
    username_field: "#username"
    password_field: "#password"
    submit_button: "button[type=submit]"
    username: "${SECRET_USERNAME}"    # from .env
    password: "${SECRET_PASSWORD}"
```

### 7.5 Validators

| Validator | Config Name | What it checks |
|-----------|-------------|----------------|
| Required Field | `required_field` | Named fields must have non-empty values |
| Regex | `regex` | Field value must match a regex pattern |
| Schema | `schema` | Field must conform to a Pydantic schema |

---

## 8. Middleware Stack

Middleware wraps the fetcher in an **onion pattern** — each layer processes every request and response.

### Default Stack Order (outermost → innermost)

```
retry
  └── rate_limit
        └── block_detection
              └── observability
                    └── [actual fetcher: HTTP or Playwright]
```

**Why this order:** `retry` is outermost so retried requests must re-enter `rate_limit` — prevents retry storms.

### Middleware Reference

| Middleware | What it does |
|-----------|-------------|
| `retry` | Retries on transient errors with exponential backoff |
| `rate_limit` | Token bucket — limits requests per second per domain |
| `block_detection` | Detects CAPTCHA pages, 403s, bot blocks → raises `FetchError(blocked=True)` |
| `observability` | One structured log line + Prometheus metrics per fetch attempt |
| `auth` | Attaches cookies/tokens from session store |
| `proxy_rotation` | Rotates through a proxy pool |
| `ua_rotation` | Rotates User-Agent strings |
| `circuit_breaker` | Opens per-domain after repeated failures (stops hammering dead hosts) |
| `caching` | Serves recent response from cache without fetching |
| `cost_tracker` | Tracks API/proxy cost per request |
| `distributed_rate_limiter` | Redis/Postgres-backed rate limit for multi-worker deployments |

---

## 9. Repositories (Storage)

### JSON Repository

```yaml
- name: json
  options:
    path: "output/my_data.json"
    mode: upsert
    key_fields: [title]
    indent: 2
```
Saves as a formatted JSON array. `upsert` updates existing records by key.

### CSV Repository

```yaml
- name: csv
  options:
    path: "output/my_data.csv"
    mode: upsert
    key_fields: [title]
```
Note: `indent` is not supported for CSV files.

### JSONL Repository

```yaml
- name: jsonl
  options:
    path: "output/my_data.jsonl"
    mode: append
```
One JSON object per line — ideal for large datasets and streaming.

### PostgreSQL Repository

```yaml
- name: postgres
  options:
    table: my_table
    mode: upsert
    key_fields: [source_url]
    dsn: "${DATABASE_URL}"
```

### Provenance Fields (Auto-added to Every Record)

| Field | Example Value | Description |
|-------|--------------|-------------|
| `schema_version` | `"1"` | Config schema version |
| `plugin_name` | `imdb_movies` | Which plugin produced this |
| `plugin_version` | `0.1.0` | Plugin version at time of scrape |
| `config_fingerprint` | `d3834b3b7...` | Exact config SHA-256 hash |
| `source_url` | `https://...` | Page URL the record came from |
| `scraped_at` | `2026-07-22T08:49:09Z` | ISO 8601 timestamp |

---

## 10. Error Handling & Quarantine

### Error Actions

| Action | Effect |
|--------|--------|
| `retry` | Re-run the stage (up to `max_retries` times with backoff) |
| `skip` | Drop this URL/record silently and continue to next |
| `quarantine` | Save failed record to `quarantine/` for manual review |
| `abort` | Stop the entire job immediately |

### Error Policy Config

```yaml
error_policy:
  default: abort
  max_retries: 2
  on_retry_exhausted: abort
  stages:
    fetch:
      FetchError: retry
    validate:
      ValidationError: skip
    extract:
      ExtractionError: skip
    persist:
      PersistError: retry
```

### Quarantine Record Format

```json
{
  "trace_id": "abc123...",
  "stage": "validate",
  "error_type": "ValidationError",
  "error_message": "required field 'title' is missing",
  "context_snapshot": {
    "url": "https://example.com/page",
    "has_response": true,
    "record": {"rating": "8.5/10"},
    "config_fingerprint": "d3834b..."
  }
}
```

### Managing Quarantined Records

```bash
uv run scraper quarantine list
uv run scraper quarantine inspect <trace-id>
uv run scraper quarantine retry --plugin imdb_movies
uv run scraper quarantine discard
```

---

## 11. CLI Commands Reference

### `run` — Full Scrape

```bash
uv run scraper run plugins/imdb_movies/config/extraction.yaml
```

### `validate` — Config Check (CI/CD)

```bash
uv run scraper validate plugins/imdb_movies/config/extraction.yaml
# output: ok (fingerprint abc12345...)
```

### `dry-run` — Preview Without Saving

```bash
uv run scraper dry-run plugins/imdb_movies/config/extraction.yaml
```
Runs through `extract` only, prints JSON to stdout — does not write to repositories.

### `scaffold new-plugin`

```bash
uv run scraper scaffold new-plugin my_new_site
```

### `list-components`

```bash
uv run scraper list-components
```

### `submit` + `worker` — Distributed Mode

```bash
uv run scraper submit plugins/imdb_movies/config/extraction.yaml
uv run scraper worker --once
uv run scraper worker          # run forever
```

---

## 12. Writing a New Plugin

### Step 1: Scaffold

```bash
uv run scraper scaffold new-plugin my_site
```

### Step 2: Edit `manifest.yaml`

```yaml
name: my_site
version: 0.1.0
description: "Scraper for MySite.com"
author: Your Name
entrypoint: config/extraction.yaml
capabilities:
  - fetcher:playwright
  - parser:auto
  - repository:json
```

### Step 3: Edit `config/extraction.yaml`

```yaml
pipeline: [fetch, parse, discover, extract, validate, transform, persist]

urls:
  - "https://mysite.com/listings"

fetcher: playwright
fetcher_options:
  timeout_s: 60
  wait_after_s: 2.0

middleware: [retry, rate_limit]
middleware_options:
  rate_limit:
    rate: 0.5

engine:
  max_requests: 50

plugin:
  name: my_site
  version: 0.1.0

discover:
  next_url:
    kind: css
    query: "a.item-link"

extract:
  schema_version: "1"
  spec:
    title:
      kind: css
      query: "h1.product-title"
      cleanup: [strip]
    price:
      kind: css
      query: "span.price"
      cleanup: [strip]
      required: false

validate:
  validators:
    - name: required_field
      options: {fields: [title]}

error_policy:
  stages:
    extract:
      ExtractionError: skip
    validate:
      ValidationError: skip

persist:
  repositories:
    - name: json
      options:
        path: "output/my_site.json"
        mode: upsert
        key_fields: [title]
        indent: 2
    - name: csv
      options:
        path: "output/my_site.csv"
        mode: upsert
        key_fields: [title]
```

### Step 4: Validate → Dry Run → Run

```bash
uv run scraper validate plugins/my_site/config/extraction.yaml
uv run scraper dry-run  plugins/my_site/config/extraction.yaml
uv run scraper run      plugins/my_site/config/extraction.yaml
```

---

## 13. Real Examples

### IMDb Top 10 Movies

```bash
uv run scraper run plugins/imdb_movies/config/extraction.yaml
```

Sample output (`output/imdb_top_movies.json`):
```json
[
  {
    "title": "The Shawshank Redemption",
    "rating": "9.3/10",
    "release_year": "1994",
    "director": "Frank Darabont",
    "summary": "Two imprisoned men bond over a number of years...",
    "poster_image": "https://m.media-amazon.com/images/M/...",
    "schema_version": "1",
    "plugin_name": "imdb_movies",
    "source_url": "https://www.imdb.com/title/tt0111161/",
    "scraped_at": "2026-07-22T08:49:09.674816+00:00"
  }
]
```

To change number of movies scraped — edit one line:
```yaml
engine:
  max_requests: 51   # 1 listing page + 50 movie pages
```

### SEBI Circulars (PDF Scraping)

The `sebi_circulars` plugin demonstrates the PDF parser: the framework auto-detects PDFs, uses PyMuPDF to extract text, and saves circular title + content to JSONL.

---

## 14. Technology Stack & Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| Python | ≥ 3.12 | Runtime language |
| uv | latest | Package manager & virtual env |
| playwright | ≥ 1.61 | Headless Chromium for JS-heavy sites |
| httpx | ≥ 0.28 | Async HTTP client for static pages |
| lxml | ≥ 6.1 | XPath & CSS selector evaluation |
| cssselect | ≥ 1.4 | CSS selector support for lxml |
| beautifulsoup4 | ≥ 4.12 | HTML parsing |
| pymupdf | ≥ 1.28 | PDF text extraction |
| pydantic | ≥ 2.13 | Data validation and schema enforcement |
| pyyaml | ≥ 6.0 | YAML config parsing |
| typer | ≥ 0.27 | CLI framework |
| jsonpath-ng | ≥ 1.8 | JSONPath expression evaluation |
| psycopg | ≥ 3.3 | PostgreSQL async client |
| opentelemetry-api/sdk | ≥ 1.44 | Distributed tracing |
| prometheus-client | ≥ 0.25 | Metrics exposition |
| cryptography | ≥ 49.0 | Auth token signing/verification |
| python-dotenv | ≥ 1.2 | `.env` file loading for secrets |

**Dev Tools:** `pytest`, `pytest-asyncio`, `ruff`, `mypy` (strict), `import-linter`, `pre-commit`

---

## 15. Observability & Events

### Event Bus

| Event | Fired when |
|-------|-----------|
| `stage.started` | A pipeline stage begins |
| `stage.completed` | A pipeline stage succeeds |
| `stage.failed` | A pipeline stage fails |
| `stage.retrying` | A stage is being retried |
| `record.extracted` | A record was successfully extracted |
| `record.saved` | A record was written to a repository |
| `record.quarantined` | A record was moved to quarantine |
| `validation.failed` | Validation failed (with per-field detail) |
| `block.detected` | A bot block or CAPTCHA was detected |

### Built-in Listeners

| Listener | What it does |
|----------|-------------|
| `LoggingListener` | Structured log lines to stdout for every event |
| `PrometheusListener` | Increments Prometheus counters/gauges for all events |

### Tracing

Every pipeline run gets a unique `trace_id` (OpenTelemetry span). This enables distributed tracing across multi-worker deployments.

---

## 16. Jira / Confluence Context

### What the Scraper Currently Does

- Scrapes any website via YAML config (no code needed per site)
- Supports JavaScript-heavy sites via Playwright headless browser
- Supports PDF scraping via PyMuPDF
- Multi-output: JSON, CSV, JSONL, PostgreSQL
- Rate limiting, retry with backoff, block detection
- Quarantine system for failed records
- Validated config with SHA-256 fingerprinting
- Plugin scaffolding for rapid new-site onboarding
- Distributed mode: Postgres queue + multiple workers

### What the Scraper Does NOT Currently Do

- No built-in dashboard (output is files or database)
- No scheduling UI (use cron or `scraper worker` for recurring runs)
- No login-wall support by default (auth middleware must be configured per plugin)
- No visual selector builder (selectors written manually in YAML)

### Typical Jira Story → Config Change Mapping

| Story Type | What to change |
|------------|----------------|
| Add new website to scrape | Create new plugin folder + `extraction.yaml` |
| Add new field to existing plugin | Add field under `extract.spec` in plugin config |
| Change output format | Add/modify entry under `persist.repositories` |
| Site is getting blocked | Enable `proxy_rotation` and `ua_rotation` middleware |
| Need login support | Configure `auth` middleware + form/token provider |
| Scale to many workers | Set `queue.dsn` and use `scraper worker` command |
| Recurring scheduled scrape | Use `scraper worker` with cron |

---

## Quick Reference Card

```bash
# Run a scrape
uv run scraper run plugins/<plugin>/config/extraction.yaml

# Validate config (use in CI)
uv run scraper validate plugins/<plugin>/config/extraction.yaml

# Preview data without saving
uv run scraper dry-run plugins/<plugin>/config/extraction.yaml

# Create a new plugin
uv run scraper scaffold new-plugin <name>

# List all registered components
uv run scraper list-components

# Quarantine management
uv run scraper quarantine list
uv run scraper quarantine inspect <trace-id>
uv run scraper quarantine retry --plugin <name>
uv run scraper quarantine discard

# Distributed mode
uv run scraper submit plugins/<plugin>/config/extraction.yaml
uv run scraper worker --once
uv run scraper worker          # run forever
```

---

*Last Updated: July 2026 | Maintainer: Scraper Framework Team*
