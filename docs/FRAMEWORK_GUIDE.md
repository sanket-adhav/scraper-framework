# Scraper Framework — A Simple Guide

**For:** engineering managers, product managers, tech leads, business analysts,
clients, and new team members. No knowledge of the code needed.

---

## 1. Introduction

**What is this project?**
A reusable system for collecting data from websites. "Scraping" means a program
opens a web page, reads it, picks out the useful information, and saves it in a
clean form — like copying details into a spreadsheet, but automatic and at scale.

**Why was it built?**
Companies need data that lives on websites: government circulars, product
prices, regulatory notices. Collecting it by hand doesn't scale, and writing a
separate program per website is expensive to maintain.

**What problem does it solve?**
Normally each website needs its own program — ten websites, ten programs, ten
sets of bugs. This framework flips that: **one shared engine does the work, and
each website supplies only a small settings file.**

**Who can use it?**

| Audience | Gets |
|---|---|
| Business teams | Reliable scheduled data, no technical work |
| Analysts | Clean, consistent data instead of messy pages |
| Developers | A new website added in hours, not days |
| Managers | One system to run and monitor, not dozens of scripts |

---

## 2. Why We Built This Framework

Traditional scrapers have five recurring problems:

- **The same code is written again and again.** Downloading, retrying, waiting
  politely, saving — written ten times means ten chances to get it wrong.
- **Every website needs a separate program**, even though 90% of the work is
  identical to the last one.
- **Hard to maintain.** Websites change layout often; in a traditional scraper
  that means editing code, testing, and re-releasing.
- **Hard to scale.** One script on one machine only goes so far, and spreading
  it across machines usually means a rewrite.
- **Slow to add websites.** Each one needs a developer and a full dev cycle.

**In short:** the old way builds a new vehicle for every delivery route. This
framework is one reliable truck that gets a different address list each day.

---

## 3. High-Level Architecture

Instead of one large program, the framework is built from small parts that each
do one job, plugged together. Three layers:

| Layer | What it is | Knows about websites? |
|---|---|---|
| **Core** | The engine, the step-by-step process, the rules every part follows | No — completely general |
| **Components** | The interchangeable workers: downloaders, readers, checkers, savers | No |
| **Plugins** | One small folder per website: its address, where data sits, what's valid | Yes — this is the only place |

**Why this is better:**

- **Write once, use everywhere** — retry logic is solved once; every website benefits.
- **Changes stay local** — a new website touches only its own folder.
- **Easy to test** — small parts are checked individually.
- **Easy to replace** — switching from file to database is a settings change.
- **Safe** — a broken plugin is set aside; the rest keep running.

---

## 4. Complete Workflow

```
                        User / Application
                                │
                                ▼
                         Start Scraping
                                │
                                ▼
              Load Plugin  ◄──────────  Plugin Manager
                                │       (finds and checks the website folder)
                                ▼
          Load Configuration  ◄──────  Configuration Loader
                                │      (merges settings, fills in runtime values)
                                ▼
                        Create Request
                                │
                                ▼
                         Run Pipeline  ◄──────  Registry
                                │               (supplies the right worker parts)
     ┌──────────────────────────┤
     │                          │
     ├──  Fetch Website  ◄────  Middleware
     │                          (retry, slow down, proxies, logins, cache)
     ├──  Parse Content
     │
     ├──  Discover Links  (optional)
     │
     ├──  Extract Data
     │
     ├──  Validate Data
     │
     ├──  Transform Data
     │
     └──  Save Data  ──────►  Repository
                                │        (file, CSV, JSON, or database)
                                ▼
                             Finish

        Event Bus listens to every step above and reports progress,
                  writes logs, and records statistics.
```

**The steps:**

1. **Start Scraping** — a person, a scheduled job, or an application asks for data.
2. **Load Plugin** — the framework finds the website's folder and checks it's valid.
3. **Load Configuration** — reads and combines the settings; any values supplied
   for this run (a keyword, a date range) are filled in here.
4. **Create Request** — builds the list of addresses to visit.
5. **Run Pipeline** — the request travels through the steps in order:
   - **Fetch** — downloads the page.
   - **Parse** — turns the raw page into something searchable.
   - **Discover** *(optional)* — finds more pages worth visiting and queues them.
   - **Extract** — picks out the wanted fields (title, date, price).
   - **Validate** — checks the result is complete and sensible.
   - **Transform** — tidies values into a standard shape.
   - **Save** — stores the finished record.
6. **Finish** — reports how many succeeded, were skipped, or need review.

**Where the supporting parts fit:**

| Part | Where | What it does there |
|---|---|---|
| **Plugin Manager** | Load Plugin | Finds website folders, checks them, quarantines broken ones so one bad plugin can't stop the others |
| **Configuration Loader** | Load Configuration | Merges settings layers and checks them; a bad setting stops the job at the start, not halfway through |
| **Registry** | Run Pipeline | The catalogue — settings ask for "the browser downloader" by name and get it |
| **Middleware** | Wraps Fetch | Retries, slows down, rotates addresses, handles logins, reuses cached pages |
| **Event Bus** | Every step | Parts announce what they're doing; listeners turn that into progress, logs, statistics. Observes only |
| **Repository** | Save Data | The destination: file, CSV, JSON, or database |

---

## 5. Project Structure

```
scraper_framework/
│
├── core/          The rules and the engine
├── components/    The interchangeable working parts
├── plugins/       One folder per website
├── config/        Framework-wide default settings
├── cli/           Terminal commands
├── tests/         Automated checks
├── docs/          Documentation
├── jobs/          Saved run settings
├── output/        Where collected data is written
└── quarantine/    Records that need human review
```

| Folder | Purpose | Contains | Why it exists |
|---|---|---|---|
| **core/** | The brain and rulebook | Engine, pipeline, part definitions, settings loader, plugin manager, registry, errors, events | Keeps general rules consistent and free of any website detail |
| **components/** | The workers | Downloaders, page readers, extractors, validators, cleaners, savers, middleware | These are the swappable pieces — choosing one is a settings change |
| **plugins/** | Website knowledge | One folder per website, each with a description file and settings | Adding a website never means touching the framework |
| **config/** | Sensible defaults | Default pipeline order, default middleware, profiles for easy vs. difficult sites | So each plugin states only what's different |
| **cli/** | The commands people type | Run a job, check settings, preview, list what's installed | A single consistent front door |
| **tests/** | Safety net | Checks for parts, for parts working together, and of each website's rules against a saved sample page | Catches breakage before production |
| **docs/** | Written explanations | This guide, decision records, approvals | Shared understanding |
| **jobs/**, **output/**, **quarantine/** | Working folders | Saved run settings, collected data, failures needing review | Keeps inputs, results, and problems separate |

---

## 6. Core Components

**Client** — whoever starts the work.
*In:* a website name and any run-time values. *Out:* a summary of what was collected.
*Example:* a person typing a command, or another application making a request.

**Scraper Engine** — manages one complete job. Sends each page through the
pipeline, collects newly discovered pages, and enforces the limit on how many
pages one job may fetch.
*In:* a job. *Out:* how many succeeded, failed, or were skipped.
*Example:* processes one SEBI listing page, finds six circulars, processes those too.

**Pipeline Engine** — runs the steps in order for a single page, applies time
limits, and decides what to do on failure: retry, skip, stop, or set aside.
*In:* one page's work-in-progress. *Out:* the finished result with a status.
*Example:* a page with no data is skipped, and the job continues.

**Pipeline Context** — the folder that travels with the work, carrying the
address, downloaded content, extracted record, and any new links found.
*In:* just the page address. *Out:* the complete record.
*Example:* like a form passed desk to desk, each desk filling in its section.

**Fetch** — downloads the page. *In:* an address. *Out:* raw content.

**Parse** — makes content searchable. *In:* raw content. *Out:* a structured document.

**Discover** — finds more pages. *In:* the document. *Out:* new addresses.

**Extract** — pulls out wanted fields. *In:* the document + field list. *Out:* a record.

**Validate** — checks the record. *In:* a record. *Out:* pass/fail with reasons.

**Transform** — tidies values. *In:* a record. *Out:* a cleaned record.

**Persist** — saves the record. *In:* a record. *Out:* confirmation it was stored.

**Repository** — the storage destination: file, CSV, JSON, JSON Lines, or
PostgreSQL. Several can be used at once.
*Example:* a circular saved to JSON *and* its PDF downloaded to disk.

**Plugin Manager** — scans the plugins folder, validates each one, registers
anything extra it provides, and sets aside broken ones with a reason.
*Example:* a plugin missing its settings file is quarantined; the other nine run.

**Registry** — the catalogue mapping friendly names to real parts.
*Example:* `fetcher: playwright` gets the browser-based downloader.

**Configuration Loader** — merges the settings layers, validates the result,
rejects unsafe values like plain-text passwords, and produces a fingerprint so
you can tell which settings produced a given record.
*Example:* a typo in a setting name stops the job at the start, not an hour in.

**Scheduler** — decides which jobs are due, and tracks what was already
collected so repeat runs can skip unchanged pages.
*In:* the current time. *Out:* the list of due jobs.

**Queue** — a shared to-do list so several machines can take from the same work.
Available in-memory or PostgreSQL-backed.
*Example:* one listing page produces fifty pages of work, shared among machines.

**Worker** — claims a job, runs it through the *same* engine, then confirms
success or reports failure. Discovered pages go back on the queue.
*Example:* four workers sharing a large collection — a settings choice, not code.

**Event Bus** — parts publish short messages ("job started", "record saved");
listeners react. A listener that crashes cannot fail the scrape.
*Out:* console progress, log entries, statistics.

**Middleware** — helpers wrapped around downloading (see §10).
*In/Out:* a request going out and a response coming back, either adjustable.

**Logging** — a structured trail of events, each carrying a tracking id so one
page's full history can be followed.
*Example:* checking afterwards why a page was skipped.

---

## 7. Pipeline Stages

| Stage | What it does | Receives | Produces | If removed |
|---|---|---|---|---|
| **Fetch** | Downloads the page | An address | Raw content | Nothing works — no data at all |
| **Parse** | Makes content searchable so you can ask for "the heading" | Raw content | A structured document | Extraction has nothing to search |
| **Discover** *(optional)* | Finds more addresses — most data sits behind a listing page | The document | New addresses, sent back to the engine | Only the starting pages are collected; a listing site returns almost nothing |
| **Extract** | Pulls out the wanted fields — the actual point of scraping | Document + field list | A record | Pages download but produce no useful data |
| **Validate** | Checks the record is complete; sites change and pages break | A record | Pass/fail with reasons | Bad records get saved and errors surface much later |
| **Transform** | Standardises values, since sites write dates and prices differently | A validated record | A cleaned record | Data saves in mixed formats, harder to use |
| **Persist** | Saves the record | The finished record | Stored data | Everything runs but nothing is kept |

**Note:** the stage list is a setting, so a job can use fewer stages — a preview
run stops after Extract and saves nothing.

---

## 8. Plugin System

**What is a plugin?** A small folder describing one website. It holds no general
scraping logic — only what makes that site different.

**Why plugins are used.** They separate *what the framework does* from *what a
website needs*. The framework knows how to scrape; the plugin knows where the
title sits on this page.

**How they keep the framework reusable.** All website details live in plugins,
so framework code never changes when a site is added. Ten websites, one engine.
A broken plugin is set aside on its own.

**Files inside a plugin:**

- **`plugin.yaml`** — the identity card: name, version, what it scrapes, its
  source approval, which settings files it uses, and any run-time values it accepts.
- **`config/extraction.yaml`** — the instructions: addresses to visit, where each
  field sits, what counts as valid, where to save.
- **`fixtures/`** *(optional)* — a saved sample page, used by tests to detect
  when the website changes.

```
plugins/sebi_circulars/
│
├── plugin.yaml                  name, version, accepted run-time values
├── config/
│   └── extraction.yaml          addresses, field locations, checks, storage
└── demo.py                      optional: run it locally for testing
```

**Adding a website:** create the folder, write the two settings files, run it.
The framework finds the plugin automatically — no framework code is edited and
nothing is re-released (see §11).

---

## 9. Configuration System

**Why settings files.** Settings live in **YAML** — a plain-text format designed
to be readable, using simple `name: value` lines. Anyone can edit them without
knowing how to program.

**What they store:** starting addresses · which downloader and page reader ·
which helpers to apply · where each field sits · what counts as valid · how
values are tidied · where results are saved · what to do when a step fails.

**Why settings beat code.** If a website moves its title, someone edits one
line. No programming, no rebuild, no release — the change can ship the same day.

**How they're loaded.** In **layers, later winning**: framework defaults, then
the plugin's settings, then anything supplied for this run. The result is then
checked — names must be real, required sections present, passwords never in
plain text. If anything is wrong, the job refuses to start.

**Run-time values.** A settings file can say "search for `${title}`", with the
keyword supplied when the job starts. So one plugin can search by keyword, by
date range, or collect everything — without editing any file.

---

## 10. Middleware

**What it is.** Helpers that wrap the download step. They see each request going
out and each response coming back, and may adjust either.

**Why it exists.** Every website needs the same protections. Middleware solves
each once, for all websites, switched on or off in settings — like airport
security layers every passenger passes through, whatever their destination.

| Helper | What it does | Like… |
|---|---|---|
| **Retry** | Tries again after a temporary failure, waiting longer each time | Redialling a busy number |
| **Proxy Rotation** | Sends requests through different network addresses in turn | A delivery company using several vans |
| **Authentication** | Handles logging in and keeps the session alive | Showing your pass at reception once |
| **Cookie Management** | Remembers the data sites use to recognise a returning visitor | A hand stamp letting you re-enter |
| **Rate Limiting** | Slows requests to a polite pace (a shared version covers several machines) | A queue letting people in a few at a time |
| **Caching** | Reuses a recently downloaded page instead of fetching again | Keeping a photocopy |
| **Logging / Observability** | Records how long each request took and whether it worked | A delivery log noting each drop-off |

Also included: **Block Detection** (notices a site refusing access), **Circuit
Breaker** (stops hammering a site that's down), **User-Agent Rotation** (varies
how the program identifies itself), and **Cost Tracker** (counts paid usage).

---

## 11. Adding a New Website

```
Create Plugin  →  Add Configuration  →  Framework Detects Plugin
                                                    │
                                                    ▼
                              Data Extracted  ←  Run Scraper
```

1. **Create Plugin** — a new folder under `plugins/` with a `plugin.yaml` giving
   its name, version, description, and any run-time values it accepts.
2. **Add Configuration** — write `config/extraction.yaml`: the starting address,
   where each field sits, what a valid record looks like, where to save.
3. **Framework Detects Plugin** — nothing to register. The next run scans the
   folder and checks the plugin; if something is missing it's quarantined with a
   clear reason rather than crashing anything.
4. **Run Scraper** — start the job, optionally passing values like a keyword or
   date range. Settings are combined, checked, and the pipeline runs.
5. **Data Extracted** — records are collected, checked, tidied, and saved, with a
   summary of what succeeded and what needs review.

**No framework code is changed at any point.**

---

## 12. Features

| Feature | Purpose | Benefit |
|---|---|---|
| Settings-driven pipeline | Steps and parts chosen in settings, not code | Change behaviour without programming |
| Plugin system | One folder per website | Add sites without touching the framework |
| Run-time values | Pass a keyword or date when starting a job | One plugin serves many different searches |
| Interchangeable parts | Swap downloaders, savers, checkers by name | Adapt to new needs quickly |
| Middleware helpers | Retry, rate limit, proxies, logins, cache | Reliable and polite by default |
| Multiple storage options | File, CSV, JSON, JSON Lines, PostgreSQL | Fits existing systems |
| Validation rules | Check records before saving | Bad data never reaches storage |
| Transformation rules | Standardise dates, text, numbers, categories | Consistent, ready-to-use data |
| Quarantine | Set aside failures for review | Nothing is silently lost |
| Plugin isolation | Broken plugins are parked, not fatal | One bad site can't stop the rest |
| Event system | Live progress, logs, statistics | Full visibility into every run |
| Queue and workers | Share work across machines | Handles large volumes |
| Error rules per step | Decide retry, skip, stop, or review | Sensible behaviour on failure |
| Settings fingerprint | Records which settings produced each result | Full traceability |
| Automated tests | Checks including saved sample pages | Website changes caught early |
| Approval requirement | Every plugin names its source approval | Built-in accountability |

---

## 13. Advantages

- **Reusable** — downloading, retrying, checking, and saving are written once and
  used by every website.
- **Easy maintenance** — most changes are one line in a settings file.
- **Easy testing** — parts are checked individually, and each website's rules are
  tested against a saved sample page, so layout changes are noticed early.
- **Easy to add new websites** — a folder with two settings files. No code
  changes, no release.
- **Scalable** — the same engine runs on one machine or many; scaling out is a
  settings choice, not a rewrite.
- **Configurable** — steps, parts, checks, storage, and failure behaviour are all
  settings.
- **Plugin based** — website knowledge stays in its own folder, so one broken
  site can't affect others.
- **Future ready** — because parts are chosen by name and follow agreed rules, a
  new storage type or downloader works immediately with every existing plugin.

---

## 14. Current Implementation

What exists and works today.

- **Engine and pipeline** — runs a job page by page, feeds newly discovered pages
  back in, runs the seven stages in order with time limits and per-step rules for
  handling failure.
- **Settings system** — layered loading with full start-up checking: names must be
  real, shape correct, page-location rules must suit the page type, no plain-text
  passwords. Each result carries a fingerprint of the settings that produced it.
- **Plugin system** — automatic discovery, validation, and quarantining of broken
  plugins. Plugins can contribute their own custom parts, checked before use.
- **Run-time values** — plugins declare which values they accept; those values are
  checked and filled in before the job starts, so one plugin can search by
  keyword, by date range, or collect everything.
- **Downloaders** — simple HTTP, a full browser for JavaScript-heavy pages, a
  browser with login support, and a local-file reader for testing.
- **Page readers** — HTML, JSON, XML, PDF, plain text, plus automatic selection
  based on the content received.
- **Data extraction** — a rules-driven extractor using CSS, XPath, or pattern
  matching with built-in cleanup, plus a table extractor.
- **Validators** — required fields, types, schema, duplicate detection, and
  business rules such as "price must be above zero".
- **Transformers** — dates, currency, text cleaning, unit conversion, category
  mapping, and adding fixed values.
- **Storage** — CSV, JSON, JSON Lines, plain files (including PDF downloads), and
  PostgreSQL. Several destinations can be used together.
- **Middleware** — retry, rate limiting (single and shared), proxy rotation,
  user-agent rotation, cookies, caching, authentication, block detection, circuit
  breaker, cost tracking, observability.
- **Events, logging, statistics** — a publish-and-listen system feeding live
  console progress, structured logs, and Prometheus-style counters, with a Grafana
  dashboard included. A failing listener cannot break a scrape.
- **Queue and workers** — in-memory for one machine, PostgreSQL for several, with
  workers that claim, process, and confirm jobs.
- **Error handling and quarantine** — a defined error list and settings deciding,
  per step and per error, whether to retry, skip, stop, or set aside. Quarantined
  items can be listed, inspected, retried, or discarded.
- **Command-line tools** — run a job, run a plugin with run-time values, preview
  final settings, validate, do a save-nothing trial run, list what's installed,
  manage the review pile, and generate a new plugin skeleton.
- **Live plugins** — SEBI circulars, SEBI gazette notifications, AMFI circulars,
  MAS circulars, Amazon best sellers, IMDb top movies, a local-government schemes
  site, an internal book-of-business report, and a test feed.
- **Tests** — unit, integration, contract, and failure-condition tests, plus
  automatic checks of every plugin's rules against saved sample pages.
- **Documentation** — framework docs, decision records, approval records, and
  workflow notes.

---

## 15. Final Architecture Overview

```
                              Client
                    (person, script, or application)
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │    CLI  /  Scheduler   │
                    └────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
 Plugin Manager        Configuration Loader           Registry
 (finds & checks       (merges settings,          (catalogue of
  website folders)      fills run-time values,      available parts)
        │               checks everything)              │
        └────────────────────────┼────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │     Scraper Engine     │ ◄──── Queue ──── Worker
                    │   (manages one job)    │      (shared    (extra
                    └────────────────────────┘       to-do      machines,
                                 │                   list)      same engine)
                                 ▼
                    ┌────────────────────────┐
                    │    Pipeline Engine     │
                    │  (runs steps in order, │
                    │   applies error rules) │
                    └────────────────────────┘
                                 │
                                 ▼
        ┌──────────────── Pipeline ────────────────┐
        │                                          │
        │   Fetch  ◄──── Middleware                │
        │                (retry, rate limit,       │
        │                 proxies, login,          │
        │                 cookies, cache)          │
        │   Parse                                  │
        │   Discover ──────► back to the engine    │
        │   Extract          as new pages to visit │
        │   Validate                               │
        │   Transform                              │
        │   Persist                                │
        │                                          │
        └──────────────────────┬───────────────────┘
                               │
                               ▼
                    ┌────────────────────────┐
                    │      Repository        │
                    │  file · CSV · JSON ·   │
                    │  JSON Lines · Postgres │
                    └────────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │  Event Bus — listens to every part above and produces live    │
  │  progress, log files, and statistics. Observes only; it can   │
  │  never change or break a scrape.                              │
  └──────────────────────────────────────────────────────────────┘
```

**How to read it.** A **Client** starts work through the **CLI** or a
**Scheduler**. Three parts prepare the ground: the **Plugin Manager** finds and
checks the website folder, the **Configuration Loader** merges and verifies the
settings, and the **Registry** supplies the working parts the settings named.

The **Scraper Engine** manages the job and hands each page to the **Pipeline
Engine**, which runs the steps in order. **Middleware** wraps Fetch.
**Discover** sends newly found pages back to the engine. Finished records go to
one or more **Repositories**.

For large volumes, jobs go on a **Queue** and several **Workers** take from it —
each running the identical engine, so scaling out changes settings, not code.
Throughout, the **Event Bus** carries announcements to the listeners producing
progress, logs, and statistics.

---

## Summary

This framework replaces "one program per website" with **one engine plus one
small settings folder per website**. The general work — downloading, retrying,
reading pages, checking data, saving results — is written once and shared;
everything website-specific lives in its own plugin folder.

The result: new websites are added quickly, most changes need no programming,
failures are contained and visible, and the same system runs on one machine or
many.
