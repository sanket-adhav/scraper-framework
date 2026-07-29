# Dynamic Plugin Parameters

Runtime parameters let one plugin scrape different things without editing any
YAML or code. A caller names a plugin and passes a parameter bag; the framework
validates it against the plugin's own contract, renders it into the plugin's own
templates, and hands the engine a fully resolved configuration.

```
scraper run-plugin sebi_circulars -p title="Mutual Fund Regulations"
scraper run-plugin sebi_circulars -p from_date=2026-07-01 -p to_date=2026-07-28
scraper run-plugin sebi_circulars            # no params → scrape everything
```

## Responsibilities (unchanged separation of concerns)

| Layer        | Knows about                                   | Never knows about                     |
|--------------|-----------------------------------------------|---------------------------------------|
| **Engine**   | how to execute a resolved config              | SEBI, Amazon, titles, dates, keywords |
| **Plugin**   | selectors, URLs, validators, its own params   | who is calling or with what values    |
| **Caller**   | the values it wants (title, date, keyword)    | selectors, parsing, validation rules  |
| **JobResolver** | how to bind caller values into a plugin    | any specific site's business meaning  |

The engine still receives a single `ResolvedConfig` and executes it. All
rendering happens in the `JobResolver`, before the engine is built.

## The three moving pieces

### 1. Parameter contract — declared in `plugin.yaml`

Each plugin optionally declares the parameters it accepts. This is the *only*
place a plugin's parameter surface is defined; core knows the shape, never the
meaning.

```yaml
params:
  title:       { type: string,  required: false }
  from_date:   { type: date,    required: false }
  to_date:     { type: date,    required: false }
  max_results: { type: integer, default: 50 }
```

Supported types: `string`, `integer`, `number`, `boolean`, `date` (ISO
`YYYY-MM-DD`). A plugin with no `params:` block accepts no parameters and behaves
exactly as before — full backward compatibility.

### 2. Templates — placeholders in `config/*.yaml`

Hardcoded business values become `${param}` placeholders, anywhere in the config:

```yaml
urls:
  - "https://www.sebi.gov.in/.../HomeAction.do?...&search=${title}&fromDate=${from_date}&toDate=${to_date}"

validate:
  validators:
    - name: business_rule
      options:
        rules:
          - { field: title, op: contains, value: "${title}" }

engine:
  max_requests: ${max_results}
```

Rendering rules, all generic and deterministic:

- **Provided / defaulted** → the value is substituted.
- **Declared but not provided** → renders to empty string. `&search=` with an
  empty value returns everything; `contains ""` matches every record. That is how
  *scrape everything* falls out with **no engine special-casing**.
- **A lone `${x}`** (whole string) keeps the value's real type, so
  `max_requests: ${max_results}` stays an `int`.
- **Undeclared `${x}`** → hard error at resolve time, catching plugin typos before
  a scrape ever starts.

### 3. JobResolver — the single seam

```
load plugin  →  validate params against contract  →  apply defaults
             →  render placeholders  →  ResolvedRuntimeConfig
```

`ResolvedRuntimeConfig` carries the plugin name, the validated parameters, and the
rendered config. The CLI layers that rendered config under the shipped defaults,
runs every existing load-time check (shape, component names, capabilities,
secrets), and builds the engine from the result.

## Execution flow

```
Receive request  (plugin name + params)
        │
        ▼
Resolve runtime configuration  (JobResolver: validate → default → render)
        │
        ▼
Execute pipeline  (generic engine runs the resolved config)
```

Because the config is resolved *per invocation*, the same plugin produces a
different runtime configuration every time — driven entirely by parameters, not by
edits to YAML or code.

## Future-proof by construction

Nothing in core, the engine, or the resolver mentions `title`, `date`, or
`keyword`. Each plugin defines its own parameter names and templates, so
completely different shapes work with no framework change:

- **SEBI** — `title`, `from_date`, `to_date`, `category`
- **Amazon** — `keyword`, `brand`, `min_price`, `max_price`
- **IMDb** — `movie`, `year`

## Parameterized plugins

Every live scraper now accepts runtime parameters. Two kinds of injection are used,
often together: **URL templating** (a value goes into the request URL, pre-filtering
server-side) and **client-side guards** (a `business_rule` keeps only matching
records; an empty param renders `contains ""`, which matches everything).

| Plugin            | URL params                     | Client-side filter | Always |
|-------------------|--------------------------------|--------------------|--------|
| `sebi_circulars`  | `title`, `from_date`, `to_date`| `title`            | `max_results` |
| `sebi_gazette`    | —                              | `title`, `category`| `max_results` |
| `amfi_circulars`  | —                              | `title`            | `max_results` |
| `beedzp`          | —                              | `title`            | `max_results` |
| `amazon_products` | `category`                     | `keyword`          | `max_results` |
| `imdb_movies`     | —                              | `title`            | `max_results` |
| `mas_circulars`   | `entity_type`, `content_type`  | `title`            | `max_results` |

`max_results` renders into `engine.max_requests` as a real integer (lone-placeholder
type preservation). Left intentionally untouched: **`ams_book_rolling`** (per request),
and **`news_feed`** / **`sebi`** (synthetic-fixture / skeleton plugins whose configs are
loaded directly by tests, so unrendered placeholders would break them).

## Commands

- `scraper run-plugin <plugin> [-p key=value ...] [--params-json '{...}']` — resolve and run.
- `scraper resolve <plugin> [-p key=value ...]` — print the fully resolved config without scraping (preview / debugging).
