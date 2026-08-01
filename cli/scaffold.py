"""The new-plugin scaffold generator.

Two shapes, because the two situations are genuinely different:

  sample  a self-contained plugin with a stored fixture page. Runs offline the
          moment it is created, so a newcomer sees a green run before changing
          anything. Good for learning, and for regression fixtures.

  http    the shape a real scraper actually has: an HTTP fetcher pointed at a
          live URL, runtime parameters, pagination, and no fixtures directory.
          This is what a plugin like sebi_circulars looks like.
"""
# This scaffold is used to create a new plugin
from __future__ import annotations

from pathlib import Path

PLACEHOLDER_URL = "https://example.com/search?q=${search}&page=1"

# --------------------------------------------------------------------------- #
# template: sample — offline, runs immediately                                 #
# --------------------------------------------------------------------------- #

SAMPLE_MANIFEST = """\
name: {name}
version: 0.1.0
description: "TODO: what this plugin scrapes"
tier: open
source_approval: "docs/source_approval.md#PENDING-{name}"  # add a real SRC entry before go-live
config_files:
  - config/extraction.yaml

params:
  search_term:
    type: string
    required: false
    default: "example"
    description: "An example runtime parameter injected into the URL."
"""

SAMPLE_CONFIG = """\
# {name} — start by pointing urls/fixtures at your source and filling in the spec.

pipeline: [fetch, parse, extract, validate, transform, persist]

urls:
  # The ${{search_term}} variable is automatically populated from runtime params
  - "file://sample.html?query=${{search_term}}"

fetcher: local_file
fetcher_options:
  root: "{root}"

parser: html

plugin:
  name: {name}
  version: 0.1.0

extract:
  schema_version: "1"
  spec:
    title:
      kind: css
      query: "h1#title"
      cleanup: [collapse_whitespace]

validate:
  validators:
    - name: required_field
      options: {{fields: [title]}}

persist:
  repositories:
    - name: csv
      options:
        path: "output/{name}.csv"

# --- config-spec test wiring (auto-discovered by tests/config_specs) ---
fixture: sample.html
sample_url: "file://sample.html?query=example"
expect:
  title: "Sample product"
"""

SAMPLE_FIXTURE = """\
<!DOCTYPE html>
<html>
<head><title>Sample</title></head>
<body>
  <h1 id="title">Sample product</h1>
  <p>Replace this file with a real saved page from your (approved) source.</p>
</body>
</html>
"""

# --------------------------------------------------------------------------- #
# template: http — the shape a real scraper has                                #
# --------------------------------------------------------------------------- #

HTTP_MANIFEST = """\
name: {name}
version: 0.1.0
description: "TODO: what this plugin scrapes"
tier: open           # open | defended | hostile — how hard the site fights back
source_approval: "docs/source_approval.md#PENDING-{name}"  # real SRC entry before go-live
config_files:
  - config/extraction.yaml

# The plugin's public interface: what callers may pass at run time. Anything
# declared here can be used as ${{name}} anywhere in config/extraction.yaml.
# Anything NOT declared is rejected, which catches typos at the boundary.
params:
  search:
    type: string
    required: false
    description: "Keyword sent to the site's own search, and matched against results."

  from_date:
    type: date           # caller writes ISO (2026-07-01); validated on the way in
    required: false
    format: "%d-%m-%Y"   # how to RENDER it into the URL — set to the site's format
    description: "Start of the date range (YYYY-MM-DD)."

  to_date:
    type: date
    required: false
    format: "%d-%m-%Y"
    description: "End of the date range (YYYY-MM-DD)."

  max_results:
    type: integer
    default: 50
    description: "Safety cap on how many requests one run will make."
"""

HTTP_CONFIG = """\
# {name} — a real-site plugin. Work through the TODOs top to bottom.
#
# Iterate with `scraper resolve {name}` (prints the final config, touches no
# network), then `scraper run-plugin {name} -p max_results=2` once the URL looks
# right. Keep max_results small until the selectors are correct.

pipeline: [fetch, parse, discover, extract, validate, persist]

# TODO: the site's listing/search URL. Every ${{...}} here must be declared in
# plugin.yaml under params. An unsupplied parameter renders empty, which is how
# "no filter, fetch everything" works with no special-casing in the engine.
urls:
  - "{url}"

fetcher: http
fetcher_options:
  timeout_s: 30
  default_headers:
    User-Agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# retry sits outside rate_limit, so every retry also has to take a rate-limit
# token — that is what makes retry storms impossible.
middleware: [retry, rate_limit]

engine:
  max_requests: ${{max_results}}

plugin:
  name: {name}
  version: 0.1.0

# Pagination / crawling: each match becomes a follow-up request, and a page with
# no match simply ends the chain.
# TODO: point this at the site's "next page" link, or at its result-row links.
discover:
  next_url:
    kind: xpath
    query: "//a[@rel='next']/@href"

extract:
  schema_version: "1"
  spec:
    # TODO: replace these with your real selectors.
    # kind: css | xpath | regex | text   (jsonpath for JSON responses)
    title:
      kind: css
      query: "h1"
      cleanup: [collapse_whitespace, strip]
    date:
      kind: css
      query: "time"
      required: false
      cleanup: [strip]

validate:
  validators:
    - name: required_field
      options: {{fields: [title]}}
    # Keeps only rows whose title matches what the caller searched for. An empty
    # ${{search}} makes this match everything.
    - name: business_rule
      options:
        rules:
          - field: title
            op: contains
            value: "${{search}}"

# One bad listing page should not abort the whole run.
error_policy:
  stages:
    extract:
      ExtractionError: skip
    validate:
      ValidationError: discard

persist:
  repositories:
    - name: json
      options:
        path: "output/{name}.json"
        key_fields: [title]
        mode: upsert
        indent: 2
"""

TEMPLATES = ("sample", "http")


def _write_sample(root: Path, name: str) -> None:
    """Writes the offline, runs-immediately skeleton (with a stored fixture)."""
    (root / "fixtures").mkdir()
    (root / "plugin.yaml").write_text(SAMPLE_MANIFEST.format(name=name), encoding="utf-8")
    (root / "config" / "extraction.yaml").write_text(
        SAMPLE_CONFIG.format(name=name, root=(root / "fixtures").as_posix()),
        encoding="utf-8",
    )
    (root / "fixtures" / "sample.html").write_text(SAMPLE_FIXTURE, encoding="utf-8")


def _write_http(root: Path, name: str, url: str) -> None:
    """Writes the real-site skeleton: manifest + config only, no fixtures."""
    (root / "plugin.yaml").write_text(HTTP_MANIFEST.format(name=name), encoding="utf-8")
    (root / "config" / "extraction.yaml").write_text(
        HTTP_CONFIG.format(name=name, url=url), encoding="utf-8"
    )


RUN_PY_TEMPLATE = '''\
"""Run a scraper from Python. Edit PARAMS, then: python run.py"""

from cli.api import run_scraper

PLUGINS_DIR = "{plugins_dir}"
PLUGIN = "{name}"

# Whatever the plugin declares under `params:` in its plugin.yaml.
PARAMS: dict[str, object] = {{
{params}}}

if __name__ == "__main__":
    result = run_scraper(PLUGIN, PARAMS, plugins_dir=PLUGINS_DIR)
    print(result)
    # `ok` is False if anything aborted OR was quarantined — check this,
    # not `aborted`, or you will call a run with 300 failures a success.
    raise SystemExit(0 if result.ok else 1)
'''

ENV_TEMPLATE = """\
# Secrets for your scrapers. Referenced from YAML as secret://NAME.
# NEVER commit this file.
#
# Example — a Postgres destination:
#   DATABASE_URL=postgresql://user:password@localhost:5432/scrapes
# then in extraction.yaml:
#   persist:
#     repositories:
#       - name: postgres
#         options: {dsn: "secret://DATABASE_URL"}
"""

GITIGNORE_TEMPLATE = """\
.env
output/
quarantine/
__pycache__/
*.pyc
"""

PROJECT_LABELS = {
    "run.py": "run scrapes from Python",
    ".env": "secrets — never commit this",
    ".gitignore": "excludes .env and outputs",
    "config": "optional: override framework defaults",
    "output": "your scraped data lands here",
    "quarantine": "records that failed, for review",
}


# The PARAMS each template's manifest actually declares. run.py has to match,
# or the first `python run.py` fails with "unknown parameter(s)".
TEMPLATE_RUN_PARAMS = {
    "sample": '    "search_term": "example",\n',
    "http": '    "search": "example",\n    "max_results": 5,\n',
}


def scaffold_project(name: str, plugins_dir: Path, *, template: str = "sample") -> list[Path]:
    """Creates the surrounding project layout next to the plugins folder.

    Writes run.py, .env, .gitignore and the config/ output/ quarantine/ folders,
    so a fresh install has somewhere obvious to put everything. Anything that
    already exists is left untouched — scaffolding a second plugin never
    overwrites your edits. Returns only what it actually created."""
    project = plugins_dir.parent
    created: list[Path] = []

    run_py = RUN_PY_TEMPLATE.format(
        name=name,
        plugins_dir=plugins_dir.name,
        params=TEMPLATE_RUN_PARAMS.get(template, TEMPLATE_RUN_PARAMS["sample"]),
    )
    files = {
        project / "run.py": run_py,
        project / ".env": ENV_TEMPLATE,
        project / ".gitignore": GITIGNORE_TEMPLATE,
    }
    for path, body in files.items():
        if not path.exists():
            path.write_text(body, encoding="utf-8")
            created.append(path)

    for folder in ("config", "output", "quarantine"):
        path = project / folder
        if not path.exists():
            path.mkdir(parents=True)
            created.append(path)

    return created


def scaffold_plugin(
    name: str,
    plugins_dir: Path,
    *,
    template: str = "sample",
    url: str | None = None,
) -> Path:
    """Writes a plugin skeleton and returns its folder path.

    Args:
        name: The plugin name (also the folder name).
        plugins_dir: Where plugin folders live.
        template: "sample" for an offline skeleton with a stored fixture page,
            "http" for the real-site shape (no fixtures directory).
        url: Seed URL for the http template. Defaults to a placeholder.

    Raises:
        FileExistsError: the folder already exists.
        ValueError: unknown template name.
    """
    if template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r}; choose one of {list(TEMPLATES)}")
    root = plugins_dir / name
    if root.exists():
        raise FileExistsError(f"plugin folder already exists: {root}")
    (root / "config").mkdir(parents=True)
    if template == "http":
        _write_http(root, name, url or PLACEHOLDER_URL)
    else:
        _write_sample(root, name)
    (root / "__init__.py").write_text("", encoding="utf-8")
    return root
