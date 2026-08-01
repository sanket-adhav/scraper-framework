"""The new-plugin scaffold generator (plan2.md §14's mitigation for
"overhead on tiny scrapes"): a working, validate-passing skeleton in seconds."""
# This scfaffold is used to create a new plugin
from __future__ import annotations

from pathlib import Path

MANIFEST_TEMPLATE = """\
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

CONFIG_TEMPLATE = """\
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

RUN_PY_TEMPLATE = '''\
"""Run a scraper from Python. Edit PARAMS, then: python run.py"""

from cli.api import run_scraper

PLUGINS_DIR = "{plugins_dir}"
PLUGIN = "{name}"

# Whatever the plugin declares under `params:` in its plugin.yaml.
PARAMS: dict[str, object] = {{
    "search_term": "example",
}}

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


def scaffold_plugin(name: str, plugins_dir: Path) -> Path:
    """Writes a complete plugin skeleton and returns its folder path."""
    root = plugins_dir / name
    if root.exists():
        raise FileExistsError(f"plugin folder already exists: {root}")
    (root / "config").mkdir(parents=True)
    (root / "fixtures").mkdir()
    (root / "plugin.yaml").write_text(MANIFEST_TEMPLATE.format(name=name), encoding="utf-8")
    (root / "config" / "extraction.yaml").write_text(
        CONFIG_TEMPLATE.format(name=name, root=(root / "fixtures").as_posix()),
        encoding="utf-8",
    )
    (root / "fixtures" / "sample.html").write_text(SAMPLE_FIXTURE, encoding="utf-8")
    (root / "__init__.py").write_text("", encoding="utf-8")
    return root


def scaffold_project(name: str, plugins_dir: Path) -> list[Path]:
    """Creates the surrounding project layout next to the plugins folder.

    Writes run.py, .env, .gitignore and the config/ output/ quarantine/ folders,
    so a fresh install has somewhere obvious to put everything. Anything that
    already exists is left untouched — re-running the scaffold for a second
    plugin never overwrites your edits. Returns only what it actually created."""
    project = plugins_dir.parent
    created: list[Path] = []

    files = {
        project / "run.py": RUN_PY_TEMPLATE.format(name=name, plugins_dir=plugins_dir.name),
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
