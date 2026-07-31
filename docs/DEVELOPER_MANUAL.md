# Developer Manual — Scraper Framework

**A practical guide for engineers building scrapers with this framework.**

You write two small YAML files and one Python file. The framework handles
downloading, retrying, parsing, checking, and saving. When YAML isn't enough, you
drop in your own Python — see [§6 Extending the Framework](#6-extending-the-framework).

---

## Contents

1. [Overview & Architecture](#1-overview--architecture)
2. [Installation & Quickstart](#2-installation--quickstart)
3. [The Files You Write](#3-the-files-you-write)
4. [Finding Your Selectors](#4-finding-your-selectors)
5. [Your `run.py` — Running a Scrape](#5-your-runpy--running-a-scrape)
6. [Extending the Framework](#6-extending-the-framework)
7. [Troubleshooting & Common Pitfalls](#7-troubleshooting--common-pitfalls)

---

## 1. Overview & Architecture

### The basic idea

Normally you'd write a Python script for every website. Ten sites, ten scripts,
ten sets of bugs.

Here the engine is **already written**. You describe your site in YAML:

- Which URL to start at
- Where the data sits on the page
- What counts as a valid record
- Where to save it

That's a **plugin**. Adding a site means adding a folder — you never touch
framework code.

### The pipeline

Every page travels through the same assembly line:

```
   fetch  →  parse  →  discover  →  extract  →  validate  →  transform  →  persist
     ↓         ↓          ↓            ↓           ↓            ↓            ↓
 download   make it   find more     pull out    check it     tidy it      save it
  the page  readable   pages         fields      is good      up
```

| Stage | What it does |
|---|---|
| **fetch** | Downloads the page |
| **parse** | Turns raw bytes into something you can query |
| **discover** | Finds more URLs and queues them |
| **extract** | Pulls out your fields |
| **validate** | Checks the record is sensible |
| **transform** | Standardises values (dates, currency) |
| **persist** | Saves it |

**You choose which stages run.** Skip `discover` if there's nothing to crawl,
skip `transform` if the data is already clean.

**Every stage is replaceable.** Don't like how something works? Write your own and
name it in the YAML — [§6](#6-extending-the-framework).

### The one thing that trips people up

**`discover` feeds URLs back to the start.** It doesn't scrape them itself — it
finds them and queues them. Each discovered URL then gets its own full trip
through the pipeline.

```
Listing page  →  discover finds 50 circular links
                        ↓
        Each of those 50 URLs starts over at fetch
                        ↓
        Each produces its own record
```

That's why your **listing page usually produces no record** — it has no title, no
PDF. That's expected, and you tell the framework to skip it. See
[§7.2](#72-error_policy--what-happens-when-something-fails).

---

## 2. Installation & Quickstart

### Install

The package is distributed from the Git repository, not from PyPI:

```bash
pip install "git+https://github.com/<org>/scraper_framework.git"
```

Requires Python 3.12+. On an older interpreter pip reports a confusing
"unsatisfiable" error naming an unrelated PyPI project called
`scraper-framework` — that is not this project. Check `python --version` first.

**One extra step** if your site needs a real browser (the `playwright` fetcher):

```bash
playwright install chromium
```

pip does **not** download the browser for you.

### Check it worked

```bash
scraper list-components
```

### The whole workflow

```
1. Install the package
        ↓
2. Create your plugin folder      →  plugin.yaml + config/extraction.yaml
        ↓
3. Find your selectors            →  browser inspect mode (§4)
        ↓
4. Create run.py                  →  pass your parameters here
        ↓
5. Run it                         →  python run.py
```

### Generate a starter plugin

```bash
mkdir -p my_plugins
scraper scaffold new-plugin my_site --plugins-dir my_plugins
scraper list-components --plugins-dir my_plugins
#   → plugin: my_site v0.1.0 [open] — ok
```

Always start from the scaffold — it already works, so you change one thing at a
time.

### CLI commands you'll use while developing

| Command | What it's for |
|---|---|
| `scraper resolve <plugin>` | Print the final config. No scraping. **Use constantly** |
| `scraper dry-run <config>` | Run up to `extract`, print records, save nothing |
| `scraper run-plugin <plugin> -p key=value` | Run it from the terminal |
| `scraper list-components` | Is my plugin loading? What components exist? |
| `scraper quarantine list` | What failed and why? |

Useful options: `--plugins-dir my_plugins`, `-p key=value`, `-f params.yaml`.

---

## 3. The Files You Write

Each plugin is a folder with **two files**:

```
my_plugins/
└── sebi_circulars/
    ├── plugin.yaml                 ← identity + which parameters it accepts
    └── config/
        └── extraction.yaml         ← the actual scraping instructions
```

---

### 3.1 `plugin.yaml` — identity and parameters

This declares who the plugin is and **what parameters callers may pass**.

```yaml
# ─── IDENTITY ────────────────────────────────────────────────────────────────
name: sebi_circulars              # Unique id for this plugin. Lowercase + underscores only.
                                  # This is what you pass to run_plugin("sebi_circulars").
                                  # NOT the folder name — this field is what counts.

version: 0.1.0                    # Bump when you change the scraping logic.
                                  # Stamped onto every record, so you can tell which
                                  # version of your scraper produced which data.

description: "Scrapes SEBI circulars from sebi.gov.in"
                                  # Free text for humans. Shows in `list-components`.

tier: open                        # How hard the site fights back: open | defended | hostile.
                                  # A hint for which middleware profile suits it.
                                  # 'open' = no defences. Defaults to 'open'.

source_approval: "docs/source_approval.md#SRC-0006"
                                  # REQUIRED and must be non-empty. A deliberate gate:
                                  # points at the record that someone approved scraping
                                  # this site. Leave it blank → plugin refuses to load.

config_files:                     # Which config files to load, in order.
  - config/extraction.yaml        # Later files override earlier ones, key by key.
                                  # Defaults to ["config/extraction.yaml"] if omitted.

# ─── RUNTIME PARAMETERS ──────────────────────────────────────────────────────
# The contract: what callers are allowed to pass. Anything not listed here is
# rejected with an error. Anything listed here can be used as ${name} in
# extraction.yaml.
params:

  title:
    type: string                  # Value must be text.
    required: false               # Caller may leave it out.
    description: "Keyword pre-filtered on SEBI's server (&search=) and matched against the title."
                                  # Shown to humans and in error messages.

  from_date:
    type: date                    # Caller passes ISO "2026-07-01"; framework validates it.
    required: false
    format: "%d-%m-%Y"            # How to RENDER it into the URL. SEBI wants 01-07-2026,
                                  # so the caller writes ISO and we convert. Omit this
                                  # and it stays ISO (2026-07-01).
    description: "Start date (YYYY-MM-DD)."

  to_date:
    type: date
    required: false
    format: "%d-%m-%Y"
    description: "End date (YYYY-MM-DD)."

  category_id:
    type: integer                 # Whole number only.
    required: false
    default: -1                   # Used when the caller doesn't pass one. -1 = all categories.
    description: "The SEBI Legal category to search. Defaults to -1 (All Categories).
                  Options: 1 (Acts), 2 (Rules), 3 (Regulations), 7 (Circulars)."

  max_results:
    type: integer
    default: 50                   # Safety net so a runaway crawl can't fetch 10,000 pages.
    description: "Cap on how many listing rows this run will follow."
```

#### Understanding `category_id` — where these numbers come from

This one confuses people, so here's the full story.

Look at SEBI's own listing URL:

```
https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0
                                                                        ↑↑↑↑↑
                                                       SEBI's internal category number
```

That `ssid=` number is how **SEBI's own website** filters its Legal section. Change
it in your browser and you get a different category of documents. It's their
number, not ours.

So in `extraction.yaml` we put a placeholder where that number goes:

```yaml
urls:
  - "...&sid=1&ssid=${category_id}&smid=0..."
```

And in `plugin.yaml` we expose it as a parameter with a friendly name:

```yaml
category_id:
  type: integer
  default: -1
```

**Result:** the caller picks a category without knowing anything about SEBI's URL
structure.

```python
run_plugin("sebi_circulars", {"category_id": 7})   # only Circulars
run_plugin("sebi_circulars", {"category_id": 3})   # only Regulations
run_plugin("sebi_circulars")                       # default -1 → everything
```

| Value | What you get |
|---|---|
| `-1` | All categories **(the default)** |
| `1` | Acts |
| `2` | Rules |
| `3` | Regulations |
| `7` | Circulars |

> **The general lesson:** when a site has a filter in its URL (a category, a page
> size, a sort order, a language), don't hardcode it — turn it into a parameter.
> That's how one plugin covers many jobs.
>
> **How to find these values yourself:** open the site, use its own filter
> dropdown, and watch the URL change. Whatever number moves is what you expose as
> a parameter.

#### Field reference

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Must be unique. Two plugins with the same name → one is quarantined |
| `version` | yes | Stamped onto every record |
| `source_approval` | yes | Must be non-empty — a deliberate compliance gate |
| `tier` | no | `open` / `defended` / `hostile`. Defaults to `open` |
| `config_files` | no | Defaults to `["config/extraction.yaml"]` |
| `params` | no | The runtime contract. No block = plugin takes no parameters |
| `components` | no | Your own Python classes — see [§6](#6-extending-the-framework) |

**Parameter keys:**

| Key | Meaning |
|---|---|
| `type` | `string`, `integer`, `number`, `boolean`, or `date` |
| `required` | `true` = caller must supply it. Default `false` |
| `default` | Used when the caller doesn't supply a value |
| `format` | Dates only — how to render into the URL (e.g. `"%d-%m-%Y"`) |
| `description` | For humans; appears in error messages |

**Why the contract matters:** the framework checks caller input against it
*before* anything runs. A typo'd name or a bad date fails instantly with a clear
message — never halfway through a scrape at 2am.

> Unknown keys are **rejected**. A typo quarantines the plugin and names the key.

---

### 3.2 `extraction.yaml` — the scraping instructions

Here's the SEBI one with every line explained.

#### Which stages to run

```yaml
pipeline: [fetch, parse, discover, extract, validate, persist]
#          │      │      │         │        │         │
#          │      │      │         │        │         └─ save the record
#          │      │      │         │        └─────────── check it's worth saving
#          │      │      │         └──────────────────── pull out title/date/pdf_link
#          │      │      └────────────────────────────── find the 50 circular links
#          │      └───────────────────────────────────── make the HTML queryable
#          └──────────────────────────────────────────── download the page
#
# 'transform' is omitted here — this data needs no cleanup beyond the
# per-field cleanups. Add it if you need date/currency normalising.
```

#### Where to start

```yaml
urls:
  # ${name} = a runtime parameter, filled in by whatever the caller passes.
  # This ONE url template covers every possible search this plugin can do.
  - "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=${category_id}&smid=0&search=${title}&fromDate=${from_date}&toDate=${to_date}"
  #                                                                        ↑              ↑                 ↑                ↑
  #                                                                    category       keyword          start date       end date
```

**The key behaviour:** if a parameter isn't supplied, its placeholder renders as an
**empty string**. So `&search=` (empty) returns SEBI's full unfiltered listing.
That's how "scrape everything" works without a second config file.

#### How to download

```yaml
fetcher: http                     # Plain HTTP. Fast (~10× faster than a browser).
                                  # Use this unless the page needs JavaScript to show data.

fetcher_options:
  timeout_s: 30                   # Give up on a single request after 30 seconds.

  default_headers:                # Sent with every request.
    User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                  # Identify as a normal browser. Many sites reject
                                  # requests with no/py-default User-Agent.
    Referer: "https://www.sebi.gov.in/"
                                  # Some sites (and their PDF links) check where you
                                  # came from and 403 if it's missing.
```

| Fetcher | Use when |
|---|---|
| `http` | The data is already in the raw HTML. **Always try this first** |
| `playwright` | The page needs a real browser to render the content |
| `authenticated_playwright` | You must log in first |
| `local_file` | Testing against saved HTML files — no network at all |

#### Helpers and safety cap

```yaml
middleware: [retry, rate_limit]   # Wrap every download with these helpers.
#            │      └─ don't hammer the site; space requests out politely
#            └──────── retry automatically on a temporary network failure
#
# Order matters: retry is OUTSIDE rate_limit, so each retry also waits its turn.

engine:
  max_requests: ${max_results}    # Hard ceiling on pages fetched in one run.
                                  # ⚠️ Counts the listing page too! max_results=5
                                  # means 1 listing + 4 circulars, not 5 circulars.
```

#### Who this plugin is

```yaml
plugin:
  name: sebi_circulars            # Stamped into every record's provenance,
  version: 0.1.0                  # so you can trace any row back to its source.
```

#### Finding more pages

```yaml
discover:
  next_url:
    kind: xpath                   # Query language for finding the links.
    query: "//table[@id='sample_1']//tr/td[2]/a/@href"
    #       │                       │        │  └─ /@href = give me the URL,
    #       │                       │        │      not the link's text
    #       │                       │        └──── the <a> inside that cell
    #       │                       └───────────── 2nd column of each row
    #       └───────────────────────────────────── the results table
    #
    # Every URL found here gets queued and runs the whole pipeline itself.
    # Relative URLs (/legal/x.html) are joined to the current page automatically.
```

#### Pulling out the fields

```yaml
extract:
  schema_version: "1"             # Your data's version. Bump if you change the
                                  # field set, so downstream consumers can adapt.
  spec:

    date:
      kind: css                   # CSS selector
      query: "div.date_value h5"  # the <h5> inside <div class="date_value">
      cleanup: [collapse_whitespace, strip]
                                  # squash newlines/tabs into single spaces, then
                                  # trim the ends. Runs in the order listed.

    title:
      kind: css
      query: "section.department-slider h1"
      cleanup: [collapse_whitespace, strip]
                                  # required defaults to TRUE — if this doesn't
                                  # match, the page raises ExtractionError.

    pdf_link:
      kind: xpath                 # XPath because we need an ATTRIBUTE.
      query: "//iframe/@src"      # the src of the embedded PDF viewer.
                                  # CSS can't return attributes — see §4.
```

**Field options:**

| Key | Meaning |
|---|---|
| `kind` | `css`, `xpath`, `regex`, `jsonpath`, or `text` |
| `query` | Your selector |
| `cleanup` | Optional tidy-up functions, applied in order |
| `required` | `true` (default) = no match is an error. `false` = you get `None` |
| `against` | Set to `url` to match the URL instead of the page content |

**Available cleanups:**

| Cleanup | Example |
|---|---|
| `strip` | `"  hi  "` → `"hi"` |
| `collapse_whitespace` | `"a\n\n  b"` → `"a b"` |
| `lower` / `upper` | case change |
| `strip_currency` | `"₹4,999.00"` → `"4999.00"` |
| `strip_trailing_dot` | `"179."` → `"179"` |
| `to_float` / `to_int` | text → number |
| `format_inr_price` | `"179."` → `"₹179"` |
| `short_title` | trims cluttered product titles |

> **Order matters.** `[strip_currency, to_float]` works. The reverse crashes —
> `"₹4,999"` isn't a number yet. **Clean the text first, convert last.**

#### Checking the data is good

```yaml
validate:
  validators:

    - name: required_field        # Reject records missing these fields.
      options:
        fields: [title, pdf_link] # A circular with no title or PDF isn't a circular
                                  # — it's the listing page. Drop it.

    - name: business_rule         # Your own conditions.
      options:
        rules:
          - field: title          # which field to check
            op: contains          # the comparison (case-insensitive)
            value: "${title}"     # what to compare against — the caller's keyword
                                  #
                                  # ✨ If no title was passed this becomes
                                  #    contains "" → matches EVERYTHING → the
                                  #    filter turns itself off. One plugin,
                                  #    both "search X" and "get all".
```

**Available validators:** `required_field`, `type`, `schema`, `business_rule`,
`duplicate`.

**`business_rule` operators:** `>` `>=` `<` `<=` `==` `!=` `in` `not_in`
`contains` `not_contains`

#### What to do when things fail

```yaml
error_policy:
  stages:
    extract:
      ExtractionError: skip       # A page with no title (i.e. the listing page)
                                  # is skipped, not fatal. THIS LINE IS ESSENTIAL
                                  # for crawls — without it the job dies on page 1.
      UnsupportedSelectorError: skip
    validate:
      ValidationError: discard    # Didn't match the caller's filter → drop it
                                  # silently. No error file, no noise.
    persist:
      PersistError: skip          # One failed save doesn't kill the run.
```

**This section matters more than it looks.** Full explanation in
[§7.2](#72-error_policy--what-happens-when-something-fails).

#### Where to save it

```yaml
persist:
  repositories:                   # As many destinations as you want — all run.

    - name: file                  # Downloads the actual binary (PDF/image).
      options:
        output_dir: "output/pdfs/sebi"   # where files land
        url_field: "pdf_link"            # which extracted field holds the URL
        filename_field: "title"          # what to name the file
        date_field: "date"               # optional prefix: 2026-07-21_Title.pdf

    - name: json                  # And save the metadata as JSON.
      options:
        path: "output/circulars.json"
        key_fields: [pdf_link]    # what makes a record unique
        mode: upsert              # update a matching record instead of appending
                                  # a duplicate. Re-running is now safe.
        indent: 2                 # pretty-print
```

**Available:** `json`, `jsonl`, `csv`, `file` (PDFs/images), `postgres`.
Need Redis, S3, or your own warehouse? [§6](#6-extending-the-framework).

---

## 4. Finding Your Selectors

You need to tell the framework *where* the data sits on the page. Here's the
fastest way to work that out.

### Step by step

**1. Open the page in Chrome** (or Firefox / Edge — same idea).

**2. Right-click the thing you want** — the title, the date, the price — and
choose **Inspect**. DevTools opens with that element highlighted in the HTML.

**3. Look at the highlighted line.** You're hunting for something stable to
identify it by:

```html
<section class="department-slider">
  <h1>Certification Requirements for SIFs</h1>     ← you want this
</section>
```

**4. Write the selector.** From the example above: `section.department-slider h1`.

**5. Test it before putting it in YAML.** In the DevTools **Console** tab:

```javascript
$$("section.department-slider h1")     // CSS — should return 1 element
$x("//iframe/@src")                     // XPath — should return your value
```

Empty result `[]` means the selector is wrong. Fix it here, where it's instant.

**6. Put it in `extraction.yaml`** and confirm with:

```bash
scraper dry-run my_plugins/my_site/config/extraction.yaml
```

This prints the extracted records without saving anything.

### The one framework rule you must know

**CSS selectors can only return text. They cannot return attributes.**

Every CSS match is converted to its text content. So if you need a link's URL, an
image's source, or an iframe's src, you **must** use XPath with `/@attribute`:

```yaml
# ❌ Returns the link's TEXT ("Download PDF")
pdf_link:
  kind: css
  query: "a.pdf-link"

# ✅ Returns the actual URL
pdf_link:
  kind: xpath
  query: "//a[@class='pdf-link']/@href"
```

Same for `discover` — a `next_url` without `/@href` gives you link text, and the
framework then tries to fetch a URL called "Click here". It fails silently.

**Rule of thumb:** text → CSS is fine. Attributes (`href`, `src`, `data-*`) →
XPath with `/@`.

### A tip on "Copy selector"

DevTools has a right-click → **Copy** → **Copy selector**. It's handy but it
often gives you something like:

```
#\32  > div:nth-child(2) > div > div.wrapper > div:nth-child(3) > span
```

That works *today*. It breaks the moment the site adds a banner, because
`nth-child(3)` becomes `nth-child(4)`. Use it as a starting point, then simplify
it to the nearest meaningful class or id.

### Which selector types work with which pages

The framework checks this at startup and refuses to run if you mismatch them:

| Page type | You can use |
|---|---|
| HTML | `css`, `xpath`, `regex`, `text` |
| XML | `xpath`, `regex`, `text` |
| JSON | `jsonpath`, `regex`, `text` |
| PDF / plain text | `regex`, `text` |

### If the page looks empty in the raw HTML

DevTools shows you the page **after** JavaScript has run. `fetcher: http` gets the
raw HTML, which can be completely different.

Check which one you're dealing with:

```bash
curl -s "https://the-site.com/page" | grep "the text you need"
```

- **Found it?** Stick with `fetcher: http` — it's much faster.
- **Not there?** The content is JavaScript-rendered. Switch to
  `fetcher: playwright`.

---

## 5. Running a Scrape from Python

Import `run_scraper` from `cli.api`. That is the same composition root the CLI
uses, so a scrape started from Python behaves identically to the same scrape
started from the terminal — the default middleware stack (rate limiting, retry,
block detection), the quarantine sink, and the secrets provider are all wired
for you.

```
my-project/
├── my_plugins/
│   └── sebi_circulars/
│       ├── plugin.yaml
│       └── config/extraction.yaml
└── run.py                    ← the file you create
```

### The file

```python
"""Run the SEBI circulars scraper. Edit PARAMS and run this file."""

from cli.api import run_scraper

PLUGINS_DIR = "my_plugins"

# ── 👇 THIS IS THE PART YOU EDIT ────────────────────────────────────────────
PLUGIN = "sebi_circulars"           # the `name:` from plugin.yaml

PARAMS = {
    "title": "Mutual Fund Regulations",   # keyword to search for
    "from_date": "2026-07-01",            # ISO format, always
    "to_date": "2026-07-28",
    "category_id": 7,                     # 7 = Circulars (see §3.1)
    "max_results": 10,                    # cap — counts the listing page
}
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run_scraper(PLUGIN, PARAMS, plugins_dir=PLUGINS_DIR)
    print(result)
    raise SystemExit(0 if result.ok else 1)
```

Run it:

```bash
python run.py
```

> **Check `result.ok`, not `result.aborted`.** A job in which every record
> failed extraction aborts nothing — those records are *quarantined* — so
> `aborted == 0` on its own is not a success signal. `result.ok` is False if
> anything aborted **or** was quarantined.
>
> Earlier versions of this manual printed a hand-assembled engine here, roughly
> thirty lines rebuilding what `cli.api` now does. That version omitted the
> quarantine sink and the secrets provider, so a failing record was destroyed
> with no on-disk trace and the run still printed zeros across the board. If you
> have a copy of it in a project, replace it with the four lines above.
>
> Do not import anything from `cli.main` that starts with an underscore — those
> are internal and will change. `cli.api` is the supported surface.

### The rest of the API

```python
from cli.api import run_scraper, run_job_file, resolve_plugin, list_plugins

resolve_plugin("sebi_circulars", {"title": "X"})   # preview, no scraping
run_job_file("jobs/nightly.yaml")                  # a config with no params
list_plugins("my_plugins")                         # .loaded / .quarantined
```

`run_scraper(..., dry_run=True)` stops after `extract` and persists nothing —
the fastest way to check selectors from a test.

### Passing different parameters

The whole point: **same plugin, different jobs, no YAML edits.**

```python
# Search by keyword
run_plugin("sebi_circulars", {"title": "Mutual Fund Regulations"})

# Search by date range
run_plugin("sebi_circulars", {"from_date": "2026-07-01", "to_date": "2026-07-28"})

# Only Circulars, capped at 20 pages
run_plugin("sebi_circulars", {"category_id": 7, "max_results": 20})

# Everything
run_plugin("sebi_circulars")
```

### What parameters can I pass?

Whatever the plugin declared in its `params:` block. For `sebi_circulars`:

| Parameter | Type | Example | What it does |
|---|---|---|---|
| `title` | string | `"Mutual Fund"` | Keyword search + keeps only matching titles |
| `from_date` | date | `"2026-07-01"` | Start of the date range |
| `to_date` | date | `"2026-07-28"` | End of the date range |
| `category_id` | integer | `7` | -1=all, 1=Acts, 2=Rules, 3=Regulations, 7=Circulars |
| `max_results` | integer | `20` | Cap on pages fetched (listing page counts) |

**Rules:**

- Dates are **ISO format**: `"2026-07-01"`, not `01/07/2026`. The plugin's
  `format:` handles converting it for the URL.
- Leave a parameter out → it's ignored, and any filter using it switches off.
- Typo a name → error listing the valid ones, **before** any network call.
- Wrong type → error before any network call.

### Checking parameters without scraping

**What this is for:** before you run a real scrape — which costs time, network
traffic, and load on someone else's server — you can ask the framework *"if I gave
you these parameters, what exactly would you do?"*

It runs the whole preparation step (load plugin → validate params → apply defaults
→ build the URL) and then **stops**. Nothing is fetched, nothing is saved.

```python
from pathlib import Path
from core.registry.registry import Registry
from core.runtime import JobResolver

# Load the plugins folder once
resolver = JobResolver.from_directory(Path("my_plugins"), Registry())

# Ask: what would these params actually produce?
resolved = resolver.resolve("sebi_circulars", {"title": "Mutual Fund"})

print(resolved.params)
# → {'title': 'Mutual Fund', 'category_id': -1, 'max_results': 50}
#   Note category_id and max_results appeared — those are the DEFAULTS
#   from plugin.yaml, filled in for you.

print(resolved.config["urls"][0])
# → https://www.sebi.gov.in/...&ssid=-1&search=Mutual Fund&fromDate=&toDate=
#   The real URL. Notice fromDate/toDate are EMPTY because you didn't pass them.
```

**Three things this catches instantly:**

| You'll spot | Because |
|---|---|
| A wrong URL | You can read the final URL and paste it into a browser to check |
| A parameter that didn't apply | It's missing from `resolved.params`, or blank in the URL |
| A bad parameter name or type | It raises `ParamError` right here, before any network call |

**When to use it:**

- Writing a new plugin — confirm your `${...}` placeholders land where you meant.
- A scrape returned nothing — check the URL before blaming your selectors.
- Adding a new parameter — verify it actually reaches the URL.

There's a CLI version too, which prints the entire final config:

```bash
scraper resolve sebi_circulars --plugins-dir my_plugins -p title="Mutual Fund"
```

> **Get in the habit.** It's free and instant. Most "my scraper isn't working"
> sessions end here, in about five seconds.

### What you get back

`run_plugin()` returns a `JobResult`:

| Field | Meaning |
|---|---|
| `completed` | Pages that made it all the way through and got saved |
| `aborted` | Pages that failed hard |
| `quarantined` | Pages set aside for review |
| `discarded` | Pages filtered out on purpose (didn't match your filter) |
| `results` | Per-page detail, if you need to dig in |

```python
result = run_plugin("sebi_circulars", {"title": "Mutual Fund"})

print(result.completed)    # 7   → seven circulars saved
print(result.discarded)    # 1   → one didn't match the title filter
print(result.aborted)      # 0   → nothing broke
```

> `discarded` is not a failure — it means your filter did its job.

### Handling errors

**Why bother:** if your `run.py` is called by a scheduler, an API, or a job queue,
you don't want a raw stack trace. You want to know *whose fault it was* — bad
input, a broken plugin, or the website — because each needs a different response.

Every error the framework raises inherits from **`ScraperError`**, so one `except`
can catch everything. But catching the specific ones tells you what to do:

```python
from core.errors.exceptions import ScraperError, ParamError, PluginError

try:
    result = run_plugin("sebi_circulars", {"title": "Mutual Fund"})

except ParamError as e:
    # YOUR INPUT is wrong: unknown parameter name, missing required one,
    # or a bad type/date. Nothing was fetched — it failed before the network.
    # → Fix the PARAMS dict. Safe to retry once corrected.
    print(f"Bad parameters: {e}")

except PluginError as e:
    # THE PLUGIN is wrong: not found, bad plugin.yaml, missing config file.
    # → Check the plugin name and --plugins-dir. Retrying won't help.
    print(f"Plugin problem: {e}")

except ScraperError as e:
    # SOMETHING ELSE during the scrape: network, parsing, saving, timeout.
    # → Often transient. This is the one worth retrying later.
    print(f"Scrape failed: {e}")
```

**The error family:**

| Exception | Means | Usually your fault? |
|---|---|---|
| `ParamError` | Bad parameters | ✅ Yes — fix `PARAMS` |
| `PluginError` | Plugin missing or broken | ✅ Yes — fix the plugin |
| `ConfigError` | Invalid YAML config | ✅ Yes — fix the YAML |
| `FetchError` | Download failed | ❌ Usually the site/network |
| `ParseError` | Couldn't read the response | ❌ Site changed format |
| `ExtractionError` | A required field didn't match | ⚠️ Site layout changed |
| `ValidationError` | Record failed your rules | ⚠️ Depends — could be intentional |
| `PersistError` | Save failed | ⚠️ Disk, permissions, or DB |
| `StageTimeoutError` | A stage took too long | ❌ Slow site |

**Practical pattern for scheduled jobs** — retry the transient stuff, don't retry
the stuff that will always fail:

```python
try:
    result = run_plugin(PLUGIN, PARAMS)
except (ParamError, PluginError) as e:
    alert_the_team(f"Scraper is misconfigured: {e}")   # a human must fix this
    raise
except ScraperError as e:
    schedule_retry_in(minutes=30)                      # probably temporary
    raise
```

> **Note:** most page-level problems never reach your `try` block at all —
> `error_policy` handles them inside the pipeline (skip, discard, quarantine).
> An exception escaping to here means something bigger went wrong. See
> [§7.2](#72-error_policy--what-happens-when-something-fails).

### Running from the terminal instead

Same thing, no Python file:

```bash
scraper run-plugin sebi_circulars \
  --plugins-dir my_plugins \
  -p title="Mutual Fund Regulations" \
  -p max_results=10
```

Or put the parameters in a file:

```yaml
# params.yaml
title: Mutual Fund Regulations
from_date: 2026-07-01
category_id: 7
max_results: 10
```

```bash
scraper run-plugin sebi_circulars -f params.yaml --plugins-dir my_plugins
```

---

## 6. Extending the Framework

YAML covers most cases. When it doesn't, **write a Python class and name it in the
YAML** — you don't fork the framework, and you don't lose any of the machinery
around your code.

### How it works

Every part of the pipeline is looked up **by name** in a catalogue. Your plugin can
add its own entries:

```
plugin.yaml declares it  →  framework imports + checks it  →  registered as
                                                              "<plugin>.<name>"
                                                                    ↓
                                                    reference it in extraction.yaml
```

Add a `components:` block to `plugin.yaml`:

```yaml
components:
  repository:                              # what KIND of thing it is
    my_store: "my_repo.py:MyRepository"    # nickname : file.py:ClassName
```

The framework then:

1. Imports the class from your plugin folder.
2. **Checks it satisfies the contract** for that kind — if not, the plugin is
   quarantined with a clear reason (it never breaks other plugins).
3. Registers it as `demo_site.my_store` — namespaced, so it can't clash with
   anyone else's.

Two rules:

- Your class must be constructible with **no arguments** (give every `__init__`
  parameter a default).
- Anything under `options:` in the YAML is passed as **keyword arguments**.

**Kinds you can contribute:** `fetcher`, `parser`, `document`, `extractor`,
`validator`, `transformer`, `repository`, `middleware`, `stage`, `login_provider`.

---

### Scenario 1: "I want to save to Redis instead of a JSON file"

The framework ships JSON, JSONL, CSV, file downloads, and PostgreSQL. Redis isn't
one of them — so write it.

**A repository only needs one method:** `async def save(self, record)`.

```python
# my_plugins/sebi_circulars/redis_repo.py
"""Saves each record into Redis as a JSON blob."""

import json
import redis.asyncio as redis
from core.models.record import Record


class RedisRepository:
    """Writes records to Redis. Options from YAML arrive as constructor kwargs."""

    def __init__(self, url: str = "redis://localhost:6379", prefix: str = "scrape") -> None:
        # Every argument needs a default — the framework constructs this
        # with no arguments at load time to verify the contract.
        self._client = redis.from_url(url)
        self._prefix = prefix

    async def save(self, record: Record) -> None:
        """Called once per scraped record."""
        key = f"{self._prefix}:{record.data.get('pdf_link')}"
        await self._client.set(key, json.dumps(dict(record.data), default=str))
```

**Declare it** in `plugin.yaml`:

```yaml
components:
  repository:
    redis: "redis_repo.py:RedisRepository"
```

**Use it** in `extraction.yaml`:

```yaml
persist:
  repositories:
    - name: sebi_circulars.redis      # <plugin name>.<nickname>
      options:
        url: "redis://localhost:6379"  # → passed to __init__ as url=
        prefix: "circular"             # → passed to __init__ as prefix=

    - name: json                       # built-ins still work alongside yours
      options:
        path: "output/circulars.json"
```

Both repositories run for every record. **Same pattern works for** S3, Elasticsearch,
Kafka, a REST API, or your internal warehouse — one `save()` method.

> **Already have PostgreSQL?** It's built in — just use
> `- name: postgres` with a `dsn` option. No custom class needed.

---

### Scenario 2: "I want to add computed fields during extraction"

You want everything the normal extractor does, **plus** a couple of extra fields —
a word count, the source domain, a checksum.

**Don't rewrite it — inherit from it.**

```python
# my_plugins/sebi_circulars/my_extractor.py
"""Standard extraction, plus a few computed fields."""

from components.extractors.spec_driven import SpecDrivenExtractor


class EnrichedExtractor(SpecDrivenExtractor):
    """Runs the built-in extractor, then adds fields the YAML can't express."""

    def extract(self, doc, spec, *, source_url=""):
        # 1. Let the normal extractor do all the selector work
        record = super().extract(doc, spec, source_url=source_url)

        # 2. Add whatever you like
        record.data["word_count"] = len(doc.text().split())
        record.data["source_domain"] = source_url.split("/")[2] if "//" in source_url else ""
        record.data["is_long"] = record.data["word_count"] > 500

        return record
```

**Declare it:**

```yaml
components:
  extractor:
    enriched: "my_extractor.py:EnrichedExtractor"
```

**Use it:**

```yaml
extractor: sebi_circulars.enriched     # top-level key — replaces the default
```

Your existing `extract.spec` still works exactly as before. You've only added to
the result.

> **Verified:** this exact pattern produces records like
> `{'title': 'Hello', 'word_count': 3, 'source_domain': 'example.com'}`.

**When to reach for this:** joining two fields, computing a hash for deduplication,
pulling something out of a `<script>` tag, or calling an internal API to enrich the
row.

---

### Scenario 3: "I need a validation rule the built-ins can't express"

`business_rule` handles comparisons. For real logic — a checksum, a lookup, a
regex across several fields — write a validator.

**A validator takes a record and returns a pass/fail result:**

```python
# my_plugins/sebi_circulars/my_validator.py
"""Rejects circulars whose reference number doesn't match our format."""

import re
from core.contracts.validator import FieldFailure, ValidationResult
from core.models.record import Record


class ReferenceFormatValidator:
    """Checks `reference` looks like CIR/ABC/12/2026."""

    def __init__(self, pattern: str = r"^CIR/[A-Z]+/\d+/\d{4}$") -> None:
        self._pattern = re.compile(pattern)

    def validate(self, record: Record) -> ValidationResult:
        value = record.data.get("reference")
        if value and not self._pattern.match(str(value)):
            return ValidationResult(
                valid=False,
                failures=(FieldFailure(field="reference",
                                       message=f"bad reference format: {value!r}"),),
            )
        return ValidationResult(valid=True, failures=())
```

```yaml
components:
  validator:
    ref_format: "my_validator.py:ReferenceFormatValidator"
```

```yaml
validate:
  validators:
    - name: required_field
      options: {fields: [title]}
    - name: sebi_circulars.ref_format     # yours runs alongside the built-ins
      options:
        pattern: "^CIR/[A-Z]+/\\d+/\\d{4}$"
```

---

### Scenario 4: "I need a transformation the built-ins don't cover"

Same shape. A transformer takes a record and returns a modified one:

```python
# my_plugins/sebi_circulars/my_transformer.py
"""Converts SEBI's date format into ISO."""

from datetime import datetime
from core.models.record import Record


class SebiDateTransformer:
    """Turns 'Jul 21, 2026' into '2026-07-21'."""

    def __init__(self, field: str = "date") -> None:
        self._field = field

    def transform(self, record: Record) -> Record:
        raw = record.data.get(self._field)
        if raw:
            record.data[self._field] = datetime.strptime(str(raw), "%b %d, %Y").date().isoformat()
        return record
```

```yaml
components:
  transformer:
    sebi_date: "my_transformer.py:SebiDateTransformer"
```

```yaml
pipeline: [fetch, parse, discover, extract, validate, transform, persist]
#                                                     ↑ add the stage

transform:
  transformers:
    - name: sebi_circulars.sebi_date
      options: {field: "date"}
```

> Check the built-in `date` transformer first — it handles most formats already.

---

### Scenario 5: "I need a whole new pipeline stage"

Rare, but supported. Say you want to OCR scanned PDFs between `parse` and
`extract`. A stage needs a `name`, an async `run(ctx)`, and an `on_error`:

```python
# my_plugins/sebi_circulars/ocr_stage.py
"""Runs OCR on scanned pages before extraction."""

from core.contracts.stage import ErrorAction


class OcrStage:
    name = "ocr"

    def __init__(self, language: str = "eng") -> None:
        self._language = language

    async def run(self, ctx):
        # ctx carries everything so far: ctx.request, ctx.response, ctx.document
        # ...do your OCR, attach the result...
        return ctx

    def on_error(self, ctx, err) -> ErrorAction:
        return ErrorAction.SKIP      # fallback when error_policy says nothing
```

```yaml
components:
  stage:
    ocr: "ocr_stage.py:OcrStage"
```

```yaml
pipeline: [fetch, parse, sebi_circulars.ocr, extract, validate, persist]
#                        ↑ slot it in wherever it belongs
```

---

### Registering components outside a plugin

If the component is shared across many plugins, register it straight onto the
registry in your `run.py`:

```python
from cli.composition import default_registry
from my_company.repositories import WarehouseRepository

registry = default_registry()
registry.register("repository", "warehouse", WarehouseRepository)

# Now `- name: warehouse` works in ANY plugin's YAML.
```

### Which approach should I use?

| Situation | Do this |
|---|---|
| Different storage backend | Custom **repository** (Scenario 1) |
| Extra/computed fields | Inherit the **extractor** (Scenario 2) |
| Complex validation logic | Custom **validator** (Scenario 3) |
| Custom data cleanup | Custom **transformer** (Scenario 4) |
| A brand-new processing step | Custom **stage** (Scenario 5) |
| Special auth / headers / proxies | Custom **middleware** or **fetcher** |
| Used by one plugin | Declare it in that plugin's `components:` |
| Used by many plugins | `registry.register(...)` in your `run.py` |

> **Check before you build.** `scraper list-components` prints everything that
> already exists. There's a decent chance it's in there.

---

## 7. Troubleshooting & Common Pitfalls

**This is the section you'll come back to.**

---

### 7.1 Playwright / Chromium isn't installed

**What you'll see:**

```
ModuleNotFoundError: No module named 'playwright'
```

```
playwright._impl._errors.Error: Executable doesn't exist at
.../ms-playwright/chromium-1234/chrome-mac/Chromium.app/...
```

**Why:** pip installs the Python library, but the actual browser is a separate
**~150MB download**.

**Fix:**

```bash
playwright install chromium
```

| Problem | Fix |
|---|---|
| `No module named 'playwright'` | Reinstall the framework |
| `Executable doesn't exist at ...` | `playwright install chromium` |
| Works locally, fails in Docker/CI | `RUN playwright install --with-deps chromium` |
| Linux: browser starts then dies | Missing system libs → use `--with-deps` |
| Works in terminal, fails in cron | Different user = different cache. Set `PLAYWRIGHT_BROWSERS_PATH` |

> **💡 Do you even need it?** Playwright is ~10× slower. Test first:
> ```bash
> curl -s "https://the-site.com/page" | grep "some text you need"
> ```
> If your data shows up, use `fetcher: http`.

---

### 7.2 `error_policy` — what happens when something fails

**The default is `abort`.** Without configuration, the first page that hiccups
kills your whole job. That's almost never what you want when crawling.

#### The structure

```yaml
error_policy:
  default: abort              # when nothing else matches
  max_retries: 2
  stages:
    fetch:
      FetchError: retry       # network blip → try again
    extract:
      ExtractionError: skip   # listing page has no fields → move on
    validate:
      ValidationError: discard # didn't match the filter → drop quietly
    persist:
      PersistError: skip
```

Read it as: **stage → error type → what to do.**

#### The five actions

| Action | What happens | Use it when |
|---|---|---|
| `retry` | Try again, up to `max_retries` | Temporary — network, timeouts |
| `skip` | Give up on this page, job continues | Expected — listing pages with no data |
| `discard` | Drop silently, nothing written | Deliberate filtering |
| `quarantine` | Save it for review, job continues | You want to inspect failures |
| `abort` | Stop everything | Something is genuinely broken |

#### Situation 1: a required field is missing → `ExtractionError`

You're crawling a listing page that links to 50 items. The listing page has no
title and no PDF, so extraction fails on it. **That's normal.**

```yaml
error_policy:
  stages:
    extract:
      ExtractionError: skip
```

Without this line your job dies on the very first page. **This is essentially
mandatory for any crawl.**

Two ways to handle a missing field:

```yaml
# Option A — the field is genuinely optional
rating:
  kind: css
  query: "span.rating"
  required: false            # missing → None, record still saves

# Option B — required, but some pages legitimately lack it
error_policy:
  stages:
    extract:
      ExtractionError: skip  # those pages get skipped
```

#### Situation 2: validation failed → `ValidationError`

Depends on *why*:

```yaml
ValidationError: discard      # I'm filtering on purpose — drop quietly
ValidationError: quarantine   # This shouldn't happen — save it so I can look
```

> **While developing, use `quarantine` instead of `discard`:**
> ```bash
> scraper quarantine list
> scraper quarantine inspect <trace-id>
> ```
> You'll see exactly which records failed and why. Switch to `discard` once the
> filter behaves.

#### A sensible starting policy

```yaml
error_policy:
  default: abort
  max_retries: 2
  stages:
    fetch:
      FetchError: retry
    extract:
      ExtractionError: skip
    validate:
      ValidationError: quarantine   # switch to 'discard' once you trust it
    persist:
      PersistError: retry
```

---

### 7.3 Parameter problems

| Message | Fix |
|---|---|
| `unknown parameter(s) ['titel']` | Typo — the message lists valid names |
| `required parameter 'x' was not supplied` | Pass it, or make it optional in `plugin.yaml` |
| `parameter 'from_date' is not a valid date: '01/07/2026'` | Use ISO: `2026-07-01` |
| `parameter 'max_results' is not a valid integer: 'lots'` | Pass a number |
| `config references ${x} but the plugin declares no such param` | Add it to `params:`, or fix the typo in the YAML |
| Params seem ignored | You ran `scraper run` (job file) instead of `run-plugin` |
| Filter returns nothing | A wrong value matches nothing; an empty one matches everything. Check spelling and case |

---

### 7.4 Plugin won't load

| Message | Fix |
|---|---|
| `no loaded plugin named 'x'` | Pass `--plugins-dir` / set `plugins_dir`; check with `list-components` |
| Plugin missing from `list-components` | No `plugin.yaml` in the folder — a folder without one is invisible |
| `QUARANTINED: <reason>` | Read the reason — it's specific |
| `plugin name 'x' is already loaded (collision)` | Two plugins share a `name:`. The folder name doesn't matter; `name:` does |
| `declared config file missing` | `config_files:` path is wrong |
| `source_approval` error | It's required — put a real reference in |
| Unknown key error | Typo in `plugin.yaml`; the message names the key |
| `cannot construct ... with no arguments` | Your custom component needs defaults on every `__init__` argument ([§6](#6-extending-the-framework)) |
| `does not satisfy the ... contract` | Your custom component is missing its required method |

> One broken plugin never stops the others — it's quarantined with a reason while
> everything else loads.

---

### 7.5 Config errors at startup

These all fire **before** any network request. Catch them with `scraper resolve`.

| Message | Fix |
|---|---|
| `field 'x' uses selector kind 'css', but PdfDocument only supports ['regex', 'text']` | Can't use CSS on a PDF — use `regex` |
| `unknown cleanup 'x'` | Typo — the error lists valid names |
| `config has no pipeline` | Add a `pipeline:` list |
| `pipeline has an extract stage but config has no 'extract' section` | Add the section, or remove the stage |
| `pipeline has a persist stage but no repositories are configured` | Add a repository |
| `pipeline has a discover stage but config has no 'discover.next_url'` | Add it, or remove `discover` |
| `unknown component name` | Check spelling against `scraper list-components` |
| `looks like a credential but is plaintext` | Use `secret://MY_ENV_VAR` |

---

### 7.6 Runtime problems

| Symptom | Likely cause | Fix |
|---|---|---|
| Job dies on the first page | No `error_policy` — default is `abort` | See [§7.2](#72-error_policy--what-happens-when-something-fails) |
| Only the starting URL scraped | `discover` found nothing (not treated as an error) | Check the `discover` selector and that `discover` is in your `pipeline:` list |
| Got exactly `max_results` records | Hit the cap — it counts the listing page | Raise it |
| Every field empty | Content is JavaScript-rendered | Use `fetcher: playwright` |
| Records vanish, no errors | `ValidationError: discard` is dropping them | Switch to `quarantine` and inspect |
| Output empty, run says success | Everything skipped or discarded | Check the summary counts |
| Fine at first, then all failures | Rate limited or blocked | Lower `rate_limit.rate`; add `block_detection` |
| `StageTimeoutError` | A stage took too long | Raise `stage_timeouts` (Playwright needs 60s+) |
| Duplicate records | Missing `mode: upsert` or wrong `key_fields` | Set both |

---

### 7.7 The general debugging recipe

**1. Check the config — instant, no network**

```bash
scraper resolve my_site --plugins-dir my_plugins
```

Look at the URL it produces. Is it what you expected?

**2. Shrink the job so iterations are fast**

```python
PARAMS = {"max_results": 2}
```

**3. See what you're actually extracting**

```bash
scraper dry-run my_plugins/my_site/config/extraction.yaml
```

Prints each record, saves nothing. Empty field here = extraction problem, so go
back to [§4](#4-finding-your-selectors).

**4. Make failures visible instead of silent**

```yaml
validate:
  ValidationError: quarantine
```

```bash
scraper quarantine list
scraper quarantine inspect <trace-id>
```

**5. Confirm the plugin loads**

```bash
scraper list-components --plugins-dir my_plugins
```

**6. Compare against what the server really sent**

```bash
curl -s "https://the-site.com/page" | grep "the-thing-you-want"
```

Not there? You need `playwright`.

---

## Quick reference

```bash
# Setup
pip install scraper-framework
playwright install chromium                              # only for JS sites
scraper scaffold new-plugin my_site --plugins-dir my_plugins

# Develop
scraper resolve <plugin> --plugins-dir my_plugins        # preview config
scraper dry-run <config.yaml>                            # see extracted records
scraper list-components --plugins-dir my_plugins         # is it loading?
scraper quarantine list                                  # what failed?

# Run
python run.py
scraper run-plugin <plugin> -p title="X" -p max_results=10
```

**What you create:**

| File | Purpose |
|---|---|
| `my_plugins/<name>/plugin.yaml` | Identity + which parameters callers may pass |
| `my_plugins/<name>/config/extraction.yaml` | URL, fields, validation, storage |
| `run.py` | Your parameters + the call that runs it |
| *(optional)* `my_plugins/<name>/*.py` | Custom repository / extractor / validator |

**Rules worth memorising:**

1. **`error_policy` defaults to `abort`** — set `ExtractionError: skip` for crawls.
2. **`discover` finding nothing is not an error** — it looks the same as finishing.
3. **CSS returns text only** — attributes need XPath with `/@href` or `/@src`.
4. **Cleanups run in order** — clean text first, convert to numbers last.
5. **`max_results` counts the listing page too** — budget for it.
6. **Empty parameter = matches everything** — that's the "scrape all" mechanism.
7. **`scraper resolve` is free** — run it constantly.
8. **Custom components need no-argument constructors** — give every `__init__`
   parameter a default.
