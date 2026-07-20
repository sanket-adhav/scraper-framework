"""Postgres unit tests: pure SQL builders, the repository over a fake connection,
and the pluggable seen-store. The real-database contract test lives separately
and runs against Postgres in CI."""

import pytest

from components.repositories._postgres_sql import (
    add_column_sql,
    create_table_sql,
    insert_sql,
    safe_identifier,
    unique_index_sql,
)
from components.repositories.postgres_repository import PostgresRepository
from components.validators.duplicate_detector import DuplicateDetectorValidator
from components.validators.seen_store import InMemorySeenStore, PostgresSeenStore
from core.errors.exceptions import PersistError
from tests.fake_postgres import (
    FakeAsyncConnection,
    FakeSyncConnection,
    async_connect_factory,
)
from tests.helpers import make_record


class TestSqlBuilders:
    def test_safe_identifier_rejects_injection(self):
        assert safe_identifier("products_v1") == "products_v1"
        for bad in ("drop table", "a;b", "1abc", 'a"b', "a-b"):
            with pytest.raises(ValueError, match="unsafe SQL identifier"):
                safe_identifier(bad)

    def test_create_table_includes_provenance_columns(self):
        sql = create_table_sql("products", ["title", "price"])
        assert "CREATE TABLE IF NOT EXISTS products" in sql
        assert "title TEXT" in sql and "price TEXT" in sql
        assert "schema_version TEXT" in sql and "config_fingerprint TEXT" in sql

    def test_insert_append_has_no_conflict_clause(self):
        sql = insert_sql("products", ["title", "sku"], key_fields=[])
        assert "ON CONFLICT" not in sql
        assert sql.count("%s") == 2

    def test_insert_upsert_updates_non_key_columns(self):
        sql = insert_sql("products", ["sku", "title", "price"], key_fields=["sku"])
        assert "ON CONFLICT (sku) DO UPDATE SET" in sql
        assert "title = EXCLUDED.title" in sql
        assert "sku = EXCLUDED.sku" not in sql  # never update the key itself

    def test_add_column_is_idempotent_migration(self):
        assert "ADD COLUMN IF NOT EXISTS stars TEXT" in add_column_sql("products", "stars")

    def test_unique_index_targets_key_fields(self):
        assert "CREATE UNIQUE INDEX IF NOT EXISTS" in unique_index_sql("products", ["sku"])


class TestPostgresRepositoryOverFake:
    async def test_first_save_creates_table_index_and_inserts(self):
        conn = FakeAsyncConnection()
        repo = PostgresRepository(
            "postgresql://x", "products", mode="upsert", key_fields=["sku"],
            connect=async_connect_factory(conn),
        )
        await repo.save(make_record({"sku": "A", "title": "Widget"}))
        statements = " | ".join(sql for sql, _ in conn.log)
        assert "CREATE TABLE IF NOT EXISTS products" in statements
        assert "CREATE UNIQUE INDEX" in statements
        assert "INSERT INTO products" in statements and "ON CONFLICT" in statements
        assert conn.commits == 1

    async def test_new_field_triggers_add_column(self):
        conn = FakeAsyncConnection()
        repo = PostgresRepository(
            "postgresql://x", "products", mode="append", connect=async_connect_factory(conn)
        )
        await repo.save(make_record({"sku": "A"}))
        await repo.save(make_record({"sku": "B", "stars": "★★★"}))  # new column appears
        assert any("ADD COLUMN IF NOT EXISTS stars" in sql for sql, _ in conn.log)

    async def test_operational_error_is_transient(self):
        class OperationalError(Exception):
            pass

        conn = FakeAsyncConnection(raise_on=OperationalError("server closed connection"))
        repo = PostgresRepository(
            "postgresql://x", "products", mode="append", connect=async_connect_factory(conn)
        )
        with pytest.raises(PersistError) as err:
            await repo.save(make_record())
        assert err.value.transient is True  # driver/connection failure → retryable

    async def test_data_error_is_permanent(self):
        class DataError(Exception):
            pass

        conn = FakeAsyncConnection(raise_on=DataError("bad value"))
        repo = PostgresRepository(
            "postgresql://x", "products", mode="append", connect=async_connect_factory(conn)
        )
        with pytest.raises(PersistError) as err:
            await repo.save(make_record())
        assert err.value.transient is False  # data problem → quarantine

    def test_upsert_without_keys_rejected(self):
        with pytest.raises(ValueError, match="key_fields"):
            PostgresRepository("postgresql://x", "products", mode="upsert")


class TestSeenStores:
    def test_in_memory_dedup(self):
        store = InMemorySeenStore()
        assert store.check_and_add("k1") is True
        assert store.check_and_add("k1") is False
        assert store.check_and_add("k2") is True

    def test_postgres_seen_store_over_fake(self):
        conn = FakeSyncConnection(seen=set())
        store = PostgresSeenStore("postgresql://x", connect=lambda dsn: conn)
        assert store.check_and_add("k1") is True
        assert store.check_and_add("k1") is False  # ON CONFLICT DO NOTHING → not new

    def test_duplicate_validator_uses_pluggable_store(self):
        conn = FakeSyncConnection(seen=set())
        store = PostgresSeenStore("postgresql://x", connect=lambda dsn: conn)
        validator = DuplicateDetectorValidator(key_fields=["sku"], store=store)
        assert validator.validate(make_record({"sku": "A"})).valid
        assert not validator.validate(make_record({"sku": "A"})).valid  # cross-store dedup
