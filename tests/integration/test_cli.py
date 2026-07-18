"""CLI tests (Plan 05 DoD): `scraper run` produces a CSV from one YAML with no
code written; `scraper validate` exits non-zero on each class of bad config."""

import csv
from pathlib import Path

import yaml
from typer.testing import CliRunner

from cli.main import app
from tests.helpers import FIXTURES_DIR

runner = CliRunner()
REPO_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def write_job(tmp_path: Path, csv_path: Path, **overrides) -> Path:
    """Writes a complete job YAML into tmp and returns its path."""
    job = {
        "pipeline": ["fetch", "parse", "extract", "validate", "transform", "persist"],
        "urls": ["file://sample_product.html"],
        "fetcher": "local_file",
        "fetcher_options": {"root": str(FIXTURES_DIR)},
        "parser": "html",
        "extract": {
            "schema_version": "1",
            "spec": {
                "title": {"kind": "css", "query": "h1#product-title span"},
                "price": {
                    "kind": "xpath",
                    "query": "//span[@class='price']/text()",
                    "cleanup": ["strip_currency", "to_float"],
                },
            },
        },
        "validate": {
            "validators": [
                {"name": "required_field", "options": {"fields": ["title", "price"]}}
            ]
        },
        "persist": {"repositories": [{"name": "csv", "options": {"path": str(csv_path)}}]},
        **overrides,
    }
    path = tmp_path / "job.yaml"
    path.write_text(yaml.safe_dump(job))
    return path


class TestRun:
    def test_one_yaml_produces_correct_csv_no_code_written(self, tmp_path):
        """THE Plan 05 headline DoD, via the real CLI entry point."""
        csv_path = tmp_path / "out.csv"
        job = write_job(tmp_path, csv_path)
        result = runner.invoke(app, ["run", str(job), "--config-dir", str(tmp_path / "none")])
        assert result.exit_code == 0, result.output
        assert "1 completed, 0 aborted" in result.output
        rows = list(csv.DictReader(csv_path.open(newline="")))
        assert rows[0]["title"] == "Aurora X2 Wireless Headphones"
        assert rows[0]["price"] == "4999.0"

    def test_works_with_shipped_default_config_dir(self, tmp_path):
        """The repo's own config/ defaults merge cleanly under a job file."""
        csv_path = tmp_path / "out.csv"
        job = write_job(
            tmp_path,
            csv_path,
            middleware_options={
                "rate_limit": {"rate": 10000.0, "burst": 100.0},
                "retry": {"max_attempts": 2, "base_delay_s": 0.0001, "max_delay_s": 0.001},
            },
        )
        result = runner.invoke(app, ["run", str(job), "--config-dir", str(REPO_CONFIG_DIR)])
        assert result.exit_code == 0, result.output
        assert csv_path.exists()


class TestValidate:
    def test_good_config_exits_zero(self, tmp_path):
        job = write_job(tmp_path, tmp_path / "o.csv")
        result = runner.invoke(app, ["validate", str(job), "--config-dir", str(tmp_path / "n")])
        assert result.exit_code == 0, result.output
        assert "ok" in result.output

    def test_bad_selector_kind_exits_nonzero(self, tmp_path):
        """DoD: jsonpath against the html parser fails validation."""
        job = write_job(
            tmp_path,
            tmp_path / "o.csv",
            extract={
                "schema_version": "1",
                "spec": {"title": {"kind": "jsonpath", "query": "$.title"}},
            },
        )
        result = runner.invoke(app, ["validate", str(job), "--config-dir", str(tmp_path / "n")])
        assert result.exit_code == 1
        assert "jsonpath" in result.output

    def test_unknown_component_name_exits_nonzero(self, tmp_path):
        """DoD: a validator name that isn't registered fails validation."""
        job = write_job(
            tmp_path,
            tmp_path / "o.csv",
            validate={"validators": [{"name": "no_such_validator"}]},
        )
        result = runner.invoke(app, ["validate", str(job), "--config-dir", str(tmp_path / "n")])
        assert result.exit_code == 1
        assert "no_such_validator" in result.output

    def test_missing_required_config_exits_nonzero(self, tmp_path):
        """DoD: a config with no pipeline can't pass."""
        path = tmp_path / "job.yaml"
        path.write_text(yaml.safe_dump({"urls": ["file://x.html"]}))
        result = runner.invoke(app, ["validate", str(path), "--config-dir", str(tmp_path / "n")])
        assert result.exit_code == 1
        assert "pipeline" in result.output


class TestDryRun:
    def test_prints_records_and_persists_nothing(self, tmp_path):
        csv_path = tmp_path / "out.csv"
        job = write_job(tmp_path, csv_path)
        result = runner.invoke(app, ["dry-run", str(job), "--config-dir", str(tmp_path / "n")])
        assert result.exit_code == 0, result.output
        assert "Aurora X2 Wireless Headphones" in result.output
        assert not csv_path.exists()  # nothing persisted


class TestListComponents:
    def test_lists_registry_by_kind(self):
        result = runner.invoke(app, ["list-components"])
        assert result.exit_code == 0
        assert "fetcher: http, local_file" in result.output
        assert "validator:" in result.output and "required_field" in result.output
        assert "repository: csv, jsonl" in result.output
