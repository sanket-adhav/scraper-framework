"""Stdio MCP server that drives the scraper framework's Book-of-Business pipeline.

The tools follow the demo's **draft -> verify -> run** flow:

  draft   fetch_rendered_html, scaffold_plugin   see a new AMS's DOM, start a plugin
  verify  verify_config                          dry-run selectors, persist nothing
  run     run_config, run_book_rolling_report     scrape for real, generate the report
          list_plugin_configs                     inspect what a plugin pulls

Every tool shells out to the *same tested CLI verbs* the framework already ships
(`cli.main run` / `dry-run`) or reuses its authenticated fetcher, so the MCP layer
adds no second implementation of the scrape. Credentials are read from `.env`
(`AMS_EMAIL` / `AMS_PASSWORD`) and are never accepted as tool arguments in the clear.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import dotenv
import yaml
from mcp.server.fastmcp import FastMCP

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_PLUGIN = "ams_book_rolling"
REPORT_SCRIPT = PLUGINS_DIR / DEFAULT_PLUGIN / "report" / "generate.py"
REPORT_OUT = OUTPUT_DIR / "book_rolling_report.html"

# Load the framework's .env so in-process tools (the browser fetcher) see AMS_*.
# CLI subprocesses load it themselves, but loading here keeps both paths identical.
dotenv.load_dotenv(REPO_ROOT / ".env")

mcp = FastMCP("chistats-magic-connector")


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _subprocess(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Runs a child process from the repo root, capturing output. Blocking — callers
    on the event loop must wrap this in `asyncio.to_thread` so the loop stays free."""
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _cli(*args: str, timeout: float = 900.0) -> subprocess.CompletedProcess[str]:
    """Runs a framework CLI verb (`cli.main <verb> …`) in a child process."""
    return _subprocess([sys.executable, "-m", "cli.main", *args], timeout)


def _inside(root: Path, target: Path) -> bool:
    """True if `target` resolves to a path within `root` (blocks `..` traversal)."""
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _plugin_dir(plugin: str) -> Path:
    """Resolves and validates a plugin folder under plugins/."""
    root = PLUGINS_DIR.resolve()
    d = (PLUGINS_DIR / plugin).resolve()
    if not _inside(root, d) or not d.is_dir():
        raise ValueError(f"unknown plugin {plugin!r}")
    return d


def _config_files(plugin: str) -> list[Path]:
    """The config files a plugin's manifest lists, in order."""
    manifest_path = _plugin_dir(plugin) / "plugin.yaml"
    if not manifest_path.is_file():
        # Surface a readable error across the MCP boundary rather than letting a
        # bare FileNotFoundError (carrying an absolute server-side path) escape.
        raise ValueError(f"plugin {plugin!r} has no plugin.yaml — it is not a loadable plugin")
    manifest = yaml.safe_load(manifest_path.read_text()) or {}
    if not isinstance(manifest, dict):
        raise ValueError(f"plugin {plugin!r} has a malformed plugin.yaml (expected a mapping)")
    return [_plugin_dir(plugin) / cf for cf in manifest.get("config_files", [])]


def _resolve_config(config_path: str) -> Path:
    """Resolves a repo-relative (or absolute) config path, refusing anything outside the repo."""
    raw = Path(config_path)
    p = (raw if raw.is_absolute() else REPO_ROOT / raw).resolve()
    if not _inside(REPO_ROOT.resolve(), p):
        raise ValueError("config path must be inside the repository")
    if not p.is_file():
        raise FileNotFoundError(f"no config at {config_path}")
    return p


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def _persist_path(cfg: Path) -> Path | None:
    """The first output file a config's persist stage writes to, if any."""
    doc = yaml.safe_load(cfg.read_text()) or {}
    for repo in (doc.get("persist") or {}).get("repositories", []):
        path = (repo.get("options") or {}).get("path")
        if path:
            return REPO_ROOT / str(path)
    return None


def _merge_row_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    """Sums per-collection row_counts across every persisted record."""
    counts: dict[str, int] = {}
    for rec in records:
        for name, n in (rec.get("row_counts") or {}).items():
            counts[name] = counts.get(name, 0) + int(n)
    return counts


def _last_line(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _parse_report_stdout(text: str) -> dict[str, Any]:
    """Pulls the headline figures out of generate.py's summary lines."""
    metrics: dict[str, Any] = {}
    if g := re.search(r"clients (\d+) . policies (\d+) . premium (\$[\d,]+)", text):
        metrics |= {
            "clients": int(g[1]),
            "policies": int(g[2]),
            "premium_in_force": g[3],
        }
    if g := re.search(r"revenue FY(\d+) (\$[\d,]+) . score (\d+)/100 \(([^)]+)\)", text):
        metrics |= {
            "base_year": int(g[1]),
            "base_revenue": g[2],
            "score": int(g[3]),
            "verdict": g[4],
        }
    return metrics


async def _render(
    url: str,
    login_url: str | None,
    wait_selector: str | None,
    username_selector: str,
    password_selector: str,
    submit_selector: str,
) -> tuple[int, str]:
    """Logs in (if login_url given) and returns (status, rendered HTML) for one page."""
    from components.fetchers.authenticated_playwright_fetcher import (
        AuthenticatedPlaywrightFetcher,
    )
    from core.models.scrape_request import ScrapeRequest

    fetcher = AuthenticatedPlaywrightFetcher(
        login_url=login_url or "",
        username=os.environ.get("AMS_EMAIL", ""),
        password=os.environ.get("AMS_PASSWORD", ""),
        username_selector=username_selector,
        password_selector=password_selector,
        submit_selector=submit_selector,
        logged_out_selector=password_selector,
        wait_selector=wait_selector,
        wait_after_s=2.0,
    )
    try:
        resp = await fetcher.fetch(ScrapeRequest(url=url))
        return resp.status, resp.body.decode("utf-8", errors="replace")
    finally:
        await fetcher.aclose()


# --------------------------------------------------------------------------- #
# tools — run                                                                  #
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_plugin_configs(plugin: str = DEFAULT_PLUGIN) -> dict[str, Any]:
    """List a plugin's scrape configs and what each one pulls from the AMS.

    Start here to see the pieces the valuation report is built from before running
    anything. `plugin` defaults to the demo plugin, ams_book_rolling.
    """
    configs = []
    for cf in _config_files(plugin):
        doc = yaml.safe_load(cf.read_text()) or {}
        collections = list((doc.get("extractor_options") or {}).get("collections", {}))
        configs.append(
            {
                "config": _rel(cf),
                "urls": doc.get("urls", []),
                "collections": collections,
            }
        )
    return {"plugin": plugin, "config_count": len(configs), "configs": configs}


@mcp.tool()
async def run_config(config_path: str) -> dict[str, Any]:
    """Run one scrape config end to end and report what it persisted.

    `config_path` is repo-relative, e.g.
    `plugins/ams_book_rolling/config/policies.yaml`. Credentials come from `.env`;
    nothing sensitive is passed here. Returns the output file and per-collection row
    counts so you can reconcile them against the source.
    """
    cfg = _resolve_config(config_path)
    proc = await asyncio.to_thread(_cli, "run", _rel(cfg))
    result: dict[str, Any] = {
        "config": _rel(cfg),
        "ok": proc.returncode == 0,
        "summary": _last_line(proc.stdout),
        "stderr": proc.stderr.strip()[-2000:],
    }
    out = _persist_path(cfg)
    if out and out.exists():
        try:
            records = json.loads(out.read_text())
        except json.JSONDecodeError:
            records = []
        result["output"] = _rel(out)
        result["row_counts"] = _merge_row_counts(records)
    return result


@mcp.tool()
async def run_book_rolling_report(
    agency: str,
    prepared_for: str = "Prospective Buyer",
    as_of: str | None = None,
    plugin: str = DEFAULT_PLUGIN,
    skip_scrape: bool = False,
) -> dict[str, Any]:
    """Run the whole pipeline: scrape every config, then generate the valuation report.

    This is the one-call demo path. Returns the report file plus headline figures
    (clients, policies, premium in force, base-year revenue, score, verdict).

    - `agency` / `prepared_for` label the report header.
    - `as_of` (YYYY-MM-DD) overrides the report date; omit for today.
    - `skip_scrape=True` re-renders the report from already-scraped `output/ams`
      data without re-hitting the AMS — useful for iterating on the report itself.

    Credentials come from `.env`. The demo plugin's configs target the local
    Quickfire AMS; pointing at a different AMS means new configs (draft -> verify -> run).
    """
    steps: list[dict[str, Any]] = []
    if not skip_scrape:
        for cf in _config_files(plugin):
            proc = await asyncio.to_thread(_cli, "run", _rel(cf))
            steps.append(
                {
                    "config": cf.name,
                    "ok": proc.returncode == 0,
                    "summary": _last_line(proc.stdout or proc.stderr),
                }
            )

    args = [
        sys.executable,
        str(REPORT_SCRIPT),
        "--agency",
        agency,
        "--prepared-for",
        prepared_for,
        "--out",
        str(REPORT_OUT),
    ]
    if as_of:
        args += ["--as-of", as_of]
    gen = await asyncio.to_thread(_subprocess, args, 300.0)

    failed = [s["config"] for s in steps if not s["ok"]]
    return {
        "ok": gen.returncode == 0 and not failed,
        "report_path": _rel(REPORT_OUT) if REPORT_OUT.exists() else None,
        "metrics": _parse_report_stdout(gen.stdout),
        "scrape_steps": steps,
        "failed_configs": failed,
        "report_stdout": gen.stdout.strip(),
        "report_stderr": gen.stderr.strip()[-1000:],
    }


# --------------------------------------------------------------------------- #
# tools — verify                                                               #
# --------------------------------------------------------------------------- #
@mcp.tool()
async def verify_config(config_path: str, sample_rows: int = 2) -> dict[str, Any]:
    """Dry-run a config through extract only, persisting nothing.

    The **verify** step: it shows how many rows each collection's selectors matched
    plus a small sample of the values, so you can correct selectors against a new AMS
    before committing to a real `run_config`. `sample_rows` caps rows shown per
    collection.
    """
    cfg = _resolve_config(config_path)
    proc = await asyncio.to_thread(_cli, "dry-run", _rel(cfg))

    records: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    collections: dict[str, Any] = {}
    for rec in records:
        for name, rows in (rec.get("collections") or {}).items():
            rows = rows if isinstance(rows, list) else []
            collections[name] = {
                "matched": len(rows),
                "sample": rows[: max(0, sample_rows)],
            }

    return {
        "config": _rel(cfg),
        "ok": proc.returncode == 0,
        "row_counts": _merge_row_counts(records),
        "collections": collections,
        "stderr": proc.stderr.strip()[-2000:],
    }


# --------------------------------------------------------------------------- #
# tools — draft                                                                #
# --------------------------------------------------------------------------- #
@mcp.tool()
async def fetch_rendered_html(
    url: str,
    login_url: str | None = None,
    wait_selector: str | None = None,
    max_chars: int = 40000,
    username_selector: str = 'input[name="Input.Email"]',
    password_selector: str = 'input[name="Input.Password"]',
    submit_selector: str = 'button[type="submit"]',
) -> dict[str, Any]:
    """Log in and return a page's fully rendered HTML so you can write selectors for it.

    The **draft** step: Blazor/JS apps return an empty shell to plain HTTP, so this
    drives a real browser (reusing the framework's authenticated fetcher) and hands
    back the DOM you actually need to target.

    - `login_url` performs a form login first (omit for public pages).
    - `wait_selector` waits for that element before capturing (e.g. a grid row),
      so you see content, not a spinner.
    - `max_chars` caps the returned HTML; `truncated` tells you if it was cut.

    Credentials come from `.env` (`AMS_EMAIL` / `AMS_PASSWORD`). Login field selectors
    default to Quickfire's ASP.NET Identity form; override them for a different AMS.
    """
    status, html = await _render(
        url,
        login_url,
        wait_selector,
        username_selector,
        password_selector,
        submit_selector,
    )
    return {
        "url": url,
        "status": status,
        "length": len(html),
        "truncated": len(html) > max_chars,
        "html": html[:max_chars],
    }


@mcp.tool()
def scaffold_plugin(name: str) -> dict[str, Any]:
    """Create a new, validate-passing plugin skeleton to start a new AMS from.

    Writes `plugins/<name>/` with a manifest and a starter config. From there:
    use `fetch_rendered_html` to see the target's DOM, edit the config's selectors,
    `verify_config` to check them, then `run_config`.
    """
    from cli.scaffold import scaffold_plugin as _scaffold

    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError("plugin name must be lowercase letters, digits and underscores")
    try:
        root = _scaffold(name, PLUGINS_DIR)
    except FileExistsError as err:
        return {"ok": False, "error": str(err)}
    created = sorted(_rel(p) for p in root.rglob("*") if p.is_file())
    return {
        "ok": True,
        "plugin": name,
        "path": _rel(root),
        "files": created,
        "next": "Edit config/extraction.yaml, then verify_config on it.",
    }


def main() -> None:
    """Runs the server over stdio (the transport Claude Code / Desktop launch)."""
    mcp.run()


if __name__ == "__main__":
    main()
