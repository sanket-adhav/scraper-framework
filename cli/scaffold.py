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
"""

CONFIG_TEMPLATE = """\
# {name} — start by pointing urls/fixtures at your source and filling in the spec.

pipeline: [fetch, parse, extract, validate, transform, persist]

urls:
  - "file://sample.html"

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
sample_url: "file://sample.html"
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
