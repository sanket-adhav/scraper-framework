# Scraper Framework

A config-driven scraping framework: a small stable core, swappable components,
and plugins written in YAML rather than Python.

Adding a new site normally means writing two YAML files. No base class to
subclass, no engine to modify, no deploy to change a selector.

```bash
scraper scaffold new-plugin my_site   # a working skeleton + a project to put it in
scraper run-plugin my_site            # it already scrapes its sample page
```

---

## Install

The package is distributed from this Git repository, not from PyPI. **Pin the
`package-v0.1.0` branch** — that is the curated distribution; `main` is the
development tree and lags behind.

```bash
pip install "git+https://github.com/sanket-adhav/scraper-framework.git@package-v0.1.0"
```

Requires **Python 3.12 or newer**. On an older interpreter pip reports a
confusing "unsatisfiable" error naming an unrelated PyPI project, so check
first:

```bash
python --version
```

If your target site needs a real browser (the `playwright` fetcher), install the
browser too — pip does not download it for you:

```bash
playwright install chromium
```

Confirm the install:

```bash
scraper list-components
```

You should get a list of every available fetcher, parser, validator and the
rest. That list is also the reference for what you may name in your YAML.

> The distribution is named `chistats-scraper-framework`; the command it
> installs is `scraper`. `scraper-framework` on PyPI is an unrelated project —
> do not install that one.

### Working on the framework itself

```bash
git clone -b package-v0.1.0 https://github.com/sanket-adhav/scraper-framework.git
cd scraper-framework
uv sync --dev
uv run pytest          # 435 passed, 37 skipped
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the architecture rules and the four
checks CI enforces.

---

## The 60-second version

```bash
mkdir my-scrapers && cd my-scrapers
scraper scaffold new-plugin my_site
```

One command lays out the whole project:

```
created plugins/my_site
  plugins/my_site/__init__.py
  plugins/my_site/config/extraction.yaml
  plugins/my_site/fixtures/sample.html
  plugins/my_site/plugin.yaml

project layout:
  ├── run.py                run scrapes from Python
  ├── .env                  secrets — never commit this
  ├── .gitignore            excludes .env and outputs
  ├── config/               optional: override framework defaults
  ├── output/               your scraped data lands here
  └── quarantine/           records that failed, for review
```

It already scrapes before you edit anything — the skeleton ships a sample HTML
page:

```bash
scraper run-plugin my_site
cat output/my_site.csv
```

```csv
title,schema_version,plugin_name,plugin_version,config_fingerprint,source_url,scraped_at
Sample product,1,my_site,0.1.0,61e4ccdbe66d...,file://sample.html?query=example,2026-08-01T08:23:14+00:00
```

You asked for one field and got six more free: that is **provenance**, stamped
on every record so any row can be traced back to the plugin version, source URL
and exact config that produced it.

From there change one thing at a time — point `urls` at your real source, swap
`fetcher: local_file` for `http`, fix the selectors — re-running after each
change.

Existing files are never overwritten, so scaffolding a second plugin creates
only the new plugin folder and leaves your `run.py` alone.

### Two starting shapes

```bash
scraper scaffold new-plugin my_site              # -t sample (default)
scraper scaffold new-plugin my_site -t http      # the shape a real scraper has
```

| Template | You get | Use when |
|---|---|---|
| `sample` | Manifest, config, and a stored fixture page | Learning. Runs offline immediately |
| `http` | Manifest and config only — HTTP fetcher, runtime params, pagination, error policy | Building against a live site |

`-t http` also takes `--url` to seed the starting address.

---

## How it fits together

A scrape is a **pipeline** of seven stages. Each stage is a small contract with
interchangeable implementations, chosen by name in YAML:

```
fetch → parse → discover → extract → validate → transform → persist
```

| Stage | Does | Swap it for |
|---|---|---|
| `fetch` | Gets the bytes | `http`, `playwright`, `local_file`, `authenticated_playwright` |
| `parse` | Bytes → a queryable Document | `html`, `json`, `xml`, `pdf`, `text`, `auto` |
| `discover` | Finds follow-up URLs (pagination) | a selector + a URL template |
| `extract` | Document → a record, by your spec | CSS, XPath, JSONPath, regex |
| `validate` | Rejects bad records | `required_field`, `type`, `schema`, `business_rule`, `duplicate` |
| `transform` | Normalises values | `date`, `currency`, `enum_mapper`, `text_cleaner`, … |
| `persist` | Writes them out | `csv`, `json`, `jsonl`, `file`, `postgres` |

Around the fetch sits a **middleware** stack — retry, rate limiting, block
detection and more. It is configured, not coded, and sensible defaults ship
inside the package, so every install rate-limits by default.

A record that fails a stage is **quarantined**, not lost: it goes to
`quarantine/` with the reason attached, and the rest of the job continues.

```bash
scraper quarantine list      # what failed and why
```

---

## A plugin is two files

```
my_site/
├── plugin.yaml               # identity + which parameters callers may pass
└── config/
    └── extraction.yaml       # the actual scraping instructions
```

`plugin.yaml` declares the plugin's public interface:

```yaml
name: my_site                 # what you pass to run-plugin — NOT the folder name
version: 0.1.0
description: "What this scrapes"
tier: open                    # open | defended | hostile
source_approval: "docs/source_approval.md#SRC-0001"   # required, non-empty

params:                       # optional: the runtime contract
  search_term:
    type: string              # string | integer | number | boolean | date
    required: false
    description: "Injected into the URL as ${search_term}"
```

Anything declared in `params` may appear as `${name}` anywhere in
`extraction.yaml` — a URL, a validator's expected value, a result cap. Callers
supply values at run time; the config on disk never changes:

```bash
scraper run-plugin my_site -p search_term="wireless headphones"
scraper run-plugin my_site -f params.yaml
scraper run-plugin my_site                      # omitted → matches everything
```

Three complete worked examples ship in this repo. They are deliberately
different shapes, and not one of them contains a line of Python:

| Example | Parser | Selectors | Pagination | Output |
|---|---|---|---|---|
| [`ecommerce_example`](plugins/ecommerce_example) | `html` | CSS + regex | next link | CSV |
| [`api_example`](plugins/api_example) | `json` | JSONPath | cursor in body | JSONL |
| [`news_feed`](plugins/news_feed) | `xml` | XPath | feed page link | JSONL |

Between them they cover optional fields, cleanup chains, enum mapping, date
normalisation, business rules, duplicate detection, constant enrichment, and a
per-plugin error-policy override.

Clone this repo and all three run offline against stored fixtures, with no
network and no credentials:

```bash
scraper run-plugin ecommerce_example
scraper run-plugin api_example
scraper run-plugin news_feed
```

Read them in that order — they are the fastest way to learn what the YAML can
express.

### Secrets

Credentials never go in the YAML — the loader rejects a plaintext value under
any credential-looking key at startup. Put the value in `.env` (the scaffold
writes one, and gitignores it) and reference it by name:

```yaml
persist:
  repositories:
    - name: postgres
      options:
        dsn: "secret://DATABASE_URL"
```

References resolve at component-build time, after the config fingerprint is
computed, so a secret never reaches the fingerprint stamped on your records.

---

## Running from Python

Use `cli.api`. It is the same composition root the CLI uses, so a scrape started
from Python behaves identically to one started from the terminal — same
middleware stack, same quarantine sink, same secrets provider.

The scaffold already wrote you a `run.py` wired to this:

```python
from cli.api import run_scraper

result = run_scraper("my_site", {"search_term": "headphones"})
if not result.ok:
    raise SystemExit(f"{result.aborted} aborted, {result.quarantined} quarantined")
```

**Check `result.ok`, not `result.aborted`.** A job in which every record failed
extraction aborts nothing — those records are quarantined — so `aborted == 0` on
its own is not a success signal.

Also available: `run_job_file`, `resolve_plugin` (preview a parameter set without
scraping) and `list_plugins` (what is available, and why anything is missing).

---

## Commands you will actually use

| Command | For |
|---|---|
| `scraper scaffold new-plugin <name> [-t http] [--url URL]` | Start from something that already works |
| `scraper run-plugin <name> -p k=v` | Run a plugin with runtime parameters |
| `scraper resolve <name> -p k=v` | Print the final config, scrape nothing. Use constantly |
| `scraper dry-run <config.yaml>` | Run through `extract`, print records, save nothing |
| `scraper run <config.yaml>` | Run a plain job file (no runtime parameters) |
| `scraper validate <config.yaml>` | Every load-time check. Built for CI |
| `scraper list-components` | What is registered, which plugins loaded, which quarantined |
| `scraper quarantine list` | What failed, and why |

`resolve` is the one to reach for while developing: it applies your parameters
and prints exactly what the engine would run, without touching the network.

> A config containing `${params}` must go through `run-plugin` or `resolve` —
> only those substitute parameters. `run` and `validate` take a plain job file
> and will say so clearly if handed a parameterised one.

---

## Documentation

| Document | Read it when |
|---|---|
| [docs/DEVELOPER_MANUAL.md](docs/DEVELOPER_MANUAL.md) | You are writing a plugin. Start here |
| [docs/USER_MANUAL.md](docs/USER_MANUAL.md) | You are running and operating scrapes |
| [docs/FRAMEWORK_GUIDE.md](docs/FRAMEWORK_GUIDE.md) | You want the architecture and the reasoning |
| [docs/source_approval.md](docs/source_approval.md) | Before pointing a plugin at any new site |
| [CONTRIBUTING.md](CONTRIBUTING.md) | You are changing the framework itself |

---

## Before you scrape a new site

Every plugin must name a `source_approval` entry. That is a deliberate gate, not
paperwork: it records that someone checked the target site's terms and that this
scrape is permitted. Add the entry in
[docs/source_approval.md](docs/source_approval.md) before a plugin goes live.

The `tier` field says how hard a site fights back (`open`, `defended`,
`hostile`) and selects a middleware profile to match. `hostile` additionally
needs proxies you supply yourself and a recorded cost sign-off.
