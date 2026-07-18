"""Plan 05 DoD: the first complete scrape — local-file fetch → parse → extract →
validate → transform → persist to CSV, asserted row for row. Config only."""

import csv

from cli.composition import default_registry, register_default_stages
from core.config.loader import load_config
from core.engine.job import ScrapeJob
from core.engine.scraper_engine import ScraperEngine
from core.errors.policy import policy_from_config
from core.models import ScrapeRequest
from core.pipeline.builder import build_pipeline
from core.pipeline.runner import PipelineRunner
from tests.helpers import FIXTURES_DIR


def job_config(csv_path: str) -> dict:
    """The whole scrape as one config dict — this is what a job YAML holds."""
    return {
        "pipeline": ["fetch", "parse", "extract", "validate", "transform", "persist"],
        "urls": ["file://sample_product.html"],
        "fetcher": "local_file",
        "fetcher_options": {"root": str(FIXTURES_DIR)},
        "parser": "html",
        "plugin": {"name": "shopverse_demo", "version": "0.1.0"},
        "extract": {
            "schema_version": "1",
            "spec": {
                "title": {"kind": "css", "query": "h1#product-title span"},
                "price": {
                    "kind": "xpath",
                    "query": "//span[@class='price']/text()",
                    "cleanup": ["strip_currency", "to_float"],
                },
                "sku": {"kind": "xpath", "query": "//main[@id='product-page']/@data-sku"},
                "availability": {"kind": "css", "query": "span.stock"},
            },
        },
        "validate": {
            "validators": [
                {"name": "required_field", "options": {"fields": ["title", "price", "sku"]}},
                {"name": "business_rule", "options": {"rules": [
                    {"field": "price", "op": ">", "value": 0},
                ]}},
            ]
        },
        "transform": {
            "transformers": [
                {"name": "text_cleaner", "options": {}},
                {"name": "enum_mapper", "options": {"mappings": {
                    "availability": {"In stock": "in_stock"},
                }}},
                {"name": "field_enricher", "options": {"constants": {"source": "shopverse"}}},
            ]
        },
        "persist": {"repositories": [{"name": "csv", "options": {"path": csv_path}}]},
    }


async def run_job(config_data: dict) -> None:
    """Assembles engine from config and runs the job, exactly as the CLI does."""
    registry = default_registry()
    register_default_stages(registry, config_data)
    config = load_config([config_data], registry=registry)
    stages = build_pipeline(config.data["pipeline"], registry)
    runner = PipelineRunner(stages, policy_from_config(config.data))
    engine = ScraperEngine(runner, config)
    job = ScrapeJob(requests=tuple(ScrapeRequest(url=u) for u in config.data["urls"]))
    result = await engine.run(job)
    assert result.completed == 1, f"pipeline did not complete: {result}"


class TestFullPipeline:
    async def test_fixture_to_csv_row_for_row(self, tmp_path):
        csv_path = tmp_path / "products.csv"
        await run_job(job_config(str(csv_path)))

        with csv_path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        row = rows[0]
        # extracted + transformed data, exactly as configured
        assert row["title"] == "Aurora X2 Wireless Headphones"
        assert row["price"] == "4999.0"
        assert row["sku"] == "B0AURX2HDX"
        assert row["availability"] == "in_stock"  # enum-mapped
        assert row["source"] == "shopverse"  # enriched constant
        # schema version + full provenance (Plan 05 DoD)
        assert row["schema_version"] == "1"
        assert row["plugin_name"] == "shopverse_demo"
        assert row["plugin_version"] == "0.1.0"
        assert len(row["config_fingerprint"]) == 64  # a real SHA-256, stamped by the stage
        assert row["source_url"] == "file://sample_product.html"
        assert row["scraped_at"]

    async def test_rerun_with_upsert_stays_single_row(self, tmp_path):
        """Idempotent re-run: same scrape twice, upsert by sku, one row."""
        csv_path = tmp_path / "products.csv"
        config = job_config(str(csv_path))
        config["persist"]["repositories"][0]["options"] = {
            "path": str(csv_path), "mode": "upsert", "key_fields": ["sku"],
        }
        await run_job(config)
        await run_job(config)
        with csv_path.open(newline="") as f:
            assert len(list(csv.DictReader(f))) == 1
