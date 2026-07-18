"""Repository tests: provenance columns, append vs upsert idempotency, both formats."""

import csv
import json

import pytest

from components.repositories.csv_repository import CsvRepository
from components.repositories.jsonl_repository import JsonlRepository
from tests.contract.base_suites import RepositoryContractSuite
from tests.helpers import make_record

PROVENANCE_COLUMNS = {
    "schema_version", "plugin_name", "plugin_version",
    "config_fingerprint", "source_url", "scraped_at",
}


class TestCsvRepositoryContract(RepositoryContractSuite):
    """Contract conformance for the CSV repository."""

    @pytest.fixture(autouse=True)
    def _tmp(self, tmp_path):
        self._path = tmp_path / "out.csv"

    def make_component(self):
        return CsvRepository(path=self._path)

    def make_record(self):
        return make_record()


class TestJsonlRepositoryContract(RepositoryContractSuite):
    """Contract conformance for the JSONL repository."""

    @pytest.fixture(autouse=True)
    def _tmp(self, tmp_path):
        self._path = tmp_path / "out.jsonl"

    def make_component(self):
        return JsonlRepository(path=self._path)

    def make_record(self):
        return make_record()


def read_csv(path) -> list[dict]:
    """Reads all CSV rows as dicts."""
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def read_jsonl(path) -> list[dict]:
    """Reads all JSONL rows as dicts."""
    return [json.loads(line) for line in path.read_text().splitlines() if line]


class TestProvenanceColumns:
    async def test_csv_carries_schema_version_and_full_provenance(self, tmp_path):
        """Plan 05 DoD: records carry schema_version + provenance into the repository."""
        path = tmp_path / "out.csv"
        await CsvRepository(path=path).save(make_record())
        row = read_csv(path)[0]
        assert set(row) >= PROVENANCE_COLUMNS
        assert row["schema_version"] == "1"
        assert row["plugin_name"] == "test_plugin"
        assert row["config_fingerprint"] == "cafe" * 16
        assert row["source_url"] == "https://shop.example/item/1"
        assert row["scraped_at"].startswith("2026-07-18")

    async def test_jsonl_carries_the_same(self, tmp_path):
        path = tmp_path / "out.jsonl"
        await JsonlRepository(path=path).save(make_record())
        row = read_jsonl(path)[0]
        assert set(row) >= PROVENANCE_COLUMNS


class TestWriteModes:
    async def test_append_mode_keeps_both_rows(self, tmp_path):
        repo = CsvRepository(path=tmp_path / "o.csv", mode="append")
        await repo.save(make_record({"sku": "A", "price": 1.0}))
        await repo.save(make_record({"sku": "A", "price": 2.0}))
        assert len(read_csv(tmp_path / "o.csv")) == 2

    async def test_upsert_mode_is_idempotent_by_key(self, tmp_path):
        """Re-running the same scrape must not duplicate rows — the newer row wins."""
        repo = CsvRepository(path=tmp_path / "o.csv", mode="upsert", key_fields=["sku"])
        await repo.save(make_record({"sku": "A", "price": 1.0}))
        await repo.save(make_record({"sku": "B", "price": 9.0}))
        await repo.save(make_record({"sku": "A", "price": 2.0}))  # replaces first A
        rows = {r["sku"]: r["price"] for r in read_csv(tmp_path / "o.csv")}
        assert rows == {"A": "2.0", "B": "9.0"}

    async def test_jsonl_upsert_is_idempotent_by_key(self, tmp_path):
        repo = JsonlRepository(path=tmp_path / "o.jsonl", mode="upsert", key_fields=["sku"])
        await repo.save(make_record({"sku": "A", "price": 1.0}))
        await repo.save(make_record({"sku": "A", "price": 2.0}))
        rows = read_jsonl(tmp_path / "o.jsonl")
        assert len(rows) == 1 and rows[0]["price"] == 2.0

    def test_upsert_without_keys_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="key_fields"):
            CsvRepository(path=tmp_path / "o.csv", mode="upsert")
