"""Real-database Postgres contract test (Plan 08 DoD: Postgres passes the
repository contract incl. idempotency). Skips when DATABASE_URL is unset, so the
offline suite is unaffected; CI sets DATABASE_URL to a Postgres service container."""

import os
import uuid

import pytest

from components.repositories.postgres_repository import PostgresRepository
from tests.helpers import make_record

DATABASE_URL = os.environ.get("SCRAPER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="set SCRAPER_TEST_DATABASE_URL to a throwaway database to run these"
)


async def _fetch_all(table: str) -> list[dict]:
    """Reads every row of a table back as dicts (test helper)."""
    import psycopg

    async with (
        await psycopg.AsyncConnection.connect(DATABASE_URL) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(f"SELECT * FROM {table}")
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in await cur.fetchall()]


async def _drop(table: str) -> None:
    """Drops a test table if it exists."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"DROP TABLE IF EXISTS {table}")
        await conn.commit()


class TestRealPostgres:
    async def test_save_writes_row_with_provenance(self):
        table = f"t_{uuid.uuid4().hex[:12]}"
        repo = PostgresRepository(DATABASE_URL, table, mode="append")
        try:
            await repo.save(make_record({"sku": "A", "title": "Widget"}))
            rows = await _fetch_all(table)
            assert len(rows) == 1
            assert rows[0]["sku"] == "A"
            assert rows[0]["title"] == "Widget"
            assert rows[0]["plugin_name"] == "test_plugin"
            assert len(rows[0]["config_fingerprint"]) == 64
        finally:
            await _drop(table)

    async def test_upsert_is_idempotent_across_reruns(self):
        table = f"t_{uuid.uuid4().hex[:12]}"
        try:
            for price in (1.0, 2.0, 3.0):  # same key, three "runs"
                repo = PostgresRepository(DATABASE_URL, table, mode="upsert", key_fields=["sku"])
                await repo.save(make_record({"sku": "A", "price": price}))
            rows = await _fetch_all(table)
            assert len(rows) == 1  # one row, not three
            assert rows[0]["price"] == "3.0"  # newest value won
        finally:
            await _drop(table)

    async def test_schema_migrates_when_a_field_appears(self):
        table = f"t_{uuid.uuid4().hex[:12]}"
        repo = PostgresRepository(DATABASE_URL, table, mode="append")
        try:
            await repo.save(make_record({"sku": "A"}))
            await repo.save(make_record({"sku": "B", "stars": "★★★★"}))  # new column
            rows = {r["sku"]: r for r in await _fetch_all(table)}
            assert rows["B"]["stars"] == "★★★★"
            assert rows["A"]["stars"] is None  # old row NULL for the new column
        finally:
            await _drop(table)
