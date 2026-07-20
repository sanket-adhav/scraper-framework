"""Phase-1 exit tests (Plan 06 DoD): both plugins run green end-to-end with zero
core changes, a config-only selector change adds a field with no deploy, the
scaffold output validates immediately, and quarantine shows in list-components."""

import csv
import json
import os
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cli.composition import default_registry, register_default_stages
from cli.main import app
from core.config.loader import load_config
from core.engine.job import ScrapeJob
from core.engine.scraper_engine import ScraperEngine
from core.errors.policy import policy_from_config
from core.models import ScrapeRequest
from core.pipeline.builder import build_pipeline
from core.pipeline.runner import PipelineRunner

runner = CliRunner()
REPO_ROOT = Path(__file__).parent.parent.parent


def _cleanup_table(table: str) -> None:
    """Drops a test table from the Postgres database, keeping it clean."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()


async def run_plugin_config(config_path: Path, overlay: dict) -> int:
    """Runs a plugin's config through the real engine (with a test overlay for
    absolute paths) and returns how many requests completed."""
    registry = default_registry()
    base = load_config([config_path, overlay])
    register_default_stages(registry, base.data)
    config = load_config([config_path, overlay], registry=registry)
    stages = build_pipeline(config.data["pipeline"], registry)
    engine = ScraperEngine(PipelineRunner(stages, policy_from_config(config.data)), config)
    job = ScrapeJob(requests=tuple(ScrapeRequest(url=u) for u in config.data["urls"]))
    result = await engine.run(job)
    assert result.aborted == 0 and result.quarantined == 0, f"plugin run not green: {result}"
    return result.completed


def plugin_overlay(plugin: str, out_file: Path, repo_name: str) -> dict:
    """Builds the test overlay: absolute fixture root + tmp output path."""
    return {
        "fetcher_options": {"root": str(REPO_ROOT / "plugins" / plugin / "fixtures")},
        "persist": {
            "repositories": [
                {
                    "name": repo_name,
                    "options": {"path": str(out_file), "mode": "upsert", "key_fields": ["sku"]},
                }
            ]
        },
    }


class TestPluginAEcommerce:
    async def test_runs_green_end_to_end(self, tmp_path):
        out = tmp_path / "ecommerce.csv"
        completed = await run_plugin_config(
            REPO_ROOT / "plugins" / "ecommerce_example" / "config" / "extraction.yaml",
            plugin_overlay("ecommerce_example", out, "csv"),
        )
        assert completed == 2
        rows = {r["sku"]: r for r in csv.DictReader(out.open(newline=""))}
        assert rows["B0AURX2HDX"]["title"] == "Aurora X2 Wireless Headphones"
        assert rows["B0AURX2HDX"]["discount_pct"] == "23"
        assert rows["B0NIMBUSPD"]["price"] == "2199.0"
        assert rows["B0NIMBUSPD"]["discount_pct"] == ""  # optional field missing → None
        assert rows["B0NIMBUSPD"]["availability"] == "out_of_stock"  # enum-mapped
        assert all(r["plugin_name"] == "ecommerce_example" for r in rows.values())

    async def test_config_only_selector_change_adds_field_no_deploy(self, tmp_path):
        """Phase-1 exit DoD: edit the spec YAML, re-run, new field appears —
        the framework code is byte-for-byte the same."""
        plugin_dir = tmp_path / "edited_plugin"
        shutil.copytree(REPO_ROOT / "plugins" / "ecommerce_example", plugin_dir)
        spec_file = plugin_dir / "config" / "extraction.yaml"
        out = tmp_path / "out.csv"
        overlay = plugin_overlay("ecommerce_example", out, "csv")

        await run_plugin_config(spec_file, overlay)
        first_columns = csv.DictReader(out.open(newline="")).fieldnames
        assert "stars" not in first_columns

        edited = yaml.safe_load(spec_file.read_text())
        edited["extract"]["spec"]["stars"] = {"kind": "css", "query": "span.stars"}
        spec_file.write_text(yaml.safe_dump(edited))
        out.unlink()

        await run_plugin_config(spec_file, overlay)
        rows = list(csv.DictReader(out.open(newline="")))
        assert "stars" in rows[0]
        assert rows[0]["stars"] == "★★★★☆"


class TestPluginBApi:
    async def test_pagination_discovers_and_scrapes_both_pages(self, tmp_path):
        """Deliberately different shape: JSON parse, JSONPath spec, cursor pagination
        through the discover stage — same engine, zero core changes."""
        out = tmp_path / "api.jsonl"
        completed = await run_plugin_config(
            REPO_ROOT / "plugins" / "api_example" / "config" / "extraction.yaml",
            plugin_overlay("api_example", out, "jsonl"),
        )
        assert completed == 2  # page 1 + the discovered page 2
        rows = {json.loads(line)["sku"]: json.loads(line) for line in out.read_text().splitlines()}
        assert set(rows) == {"B0AURX2HDX", "B0NIMBUSPD"}
        assert rows["B0NIMBUSPD"]["brand"] == "Nimbus"
        assert all(r["source"] == "shopverse_api" for r in rows.values())
        assert all(r["plugin_name"] == "api_example" for r in rows.values())


class TestCliOnRealPlugins:
    @pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="ecommerce_example persists to Postgres; needs DATABASE_URL",
    )
    def test_scraper_run_plugin_a_writes_to_postgres(self, monkeypatch):
        """`scraper run` on the plugin's own config (Postgres-backed) runs green,
        resolving secret://env/DATABASE_URL and writing rows to the DB."""
        monkeypatch.chdir(REPO_ROOT)
        result = runner.invoke(
            app, ["run", str(Path("plugins/ecommerce_example/config/extraction.yaml"))]
        )
        assert result.exit_code == 0, result.output
        assert "2 completed, 0 aborted" in result.output
        _cleanup_table("ecommerce_example")

    def test_scraper_run_plugin_b_from_repo_root(self, monkeypatch):
        monkeypatch.chdir(REPO_ROOT)
        result = runner.invoke(
            app, ["run", str(Path("plugins/api_example/config/extraction.yaml"))]
        )
        assert result.exit_code == 0, result.output
        assert "2 completed, 0 aborted" in result.output
        out = REPO_ROOT / "output" / "api_example.jsonl"
        assert out.exists()
        out.unlink()

    def test_list_components_shows_loaded_and_quarantined(self, tmp_path, monkeypatch):
        """Phase-1 exit DoD: quarantined plugins are visible, loading continues."""
        plugins_dir = tmp_path / "plugins"
        shutil.copytree(REPO_ROOT / "plugins" / "api_example", plugins_dir / "api_example")
        broken = plugins_dir / "broken_one"
        (broken / "config").mkdir(parents=True)
        (broken / "plugin.yaml").write_text("name: broken_one\n")  # missing required fields
        result = runner.invoke(app, ["list-components", "--plugins-dir", str(plugins_dir)])
        assert result.exit_code == 0, result.output
        assert "plugin: api_example v1.0.0 [open] — ok" in result.output
        assert "plugin: broken_one — QUARANTINED" in result.output


class TestScaffold:
    def test_scaffold_output_passes_validate_immediately(self, tmp_path):
        """Phase-1 exit DoD: scaffold → validate, exit 0, no edits in between."""
        plugins_dir = tmp_path / "plugins"
        result = runner.invoke(
            app, ["scaffold", "new-plugin", "fresh_site", "--plugins-dir", str(plugins_dir)]
        )
        assert result.exit_code == 0, result.output
        spec = plugins_dir / "fresh_site" / "config" / "extraction.yaml"
        result = runner.invoke(
            app, ["validate", str(spec), "--config-dir", str(tmp_path / "none")]
        )
        assert result.exit_code == 0, result.output

    def test_scaffold_output_even_runs(self, tmp_path, monkeypatch):
        """Beyond the DoD: the skeleton scrapes its own sample page out of the box."""
        monkeypatch.chdir(tmp_path)
        plugins_dir = tmp_path / "plugins"
        runner.invoke(
            app, ["scaffold", "new-plugin", "fresh_site", "--plugins-dir", str(plugins_dir)]
        )
        spec = plugins_dir / "fresh_site" / "config" / "extraction.yaml"
        result = runner.invoke(app, ["run", str(spec), "--config-dir", str(tmp_path / "none")])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "output" / "fresh_site.csv").exists()

    def test_existing_folder_refused(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        runner.invoke(app, ["scaffold", "new-plugin", "twice", "--plugins-dir", str(plugins_dir)])
        result = runner.invoke(
            app, ["scaffold", "new-plugin", "twice", "--plugins-dir", str(plugins_dir)]
        )
        assert result.exit_code == 1
        assert "already exists" in result.output
