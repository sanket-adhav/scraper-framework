"""Test bootstrap.

Real-service tests (the Postgres repository contract, the queue, distributed
rate limiting) run against a live database. They are opt-in.

**They deliberately do not read `DATABASE_URL`.** This file used to load the
repo's `.env` into the environment, which meant `pytest` on a developer machine
silently armed those suites against whatever database `.env` pointed at — and
they `DROP TABLE`. A routine test run should never be able to touch a real
database by accident.

To run them, set `SCRAPER_TEST_DATABASE_URL` explicitly to a throwaway database:

    SCRAPER_TEST_DATABASE_URL=postgresql://localhost/scraper_test uv run pytest
"""

from __future__ import annotations

import os

import pytest

#: Opt-in DSN for tests that need a live Postgres. Intentionally distinct from
#: `DATABASE_URL` so a production value in the environment cannot arm them.
TEST_DATABASE_URL_ENV = "SCRAPER_TEST_DATABASE_URL"


def test_database_url() -> str | None:
    """The opt-in test database DSN, or None when real-service tests are off."""
    return os.environ.get(TEST_DATABASE_URL_ENV)


requires_postgres = pytest.mark.skipif(
    not os.environ.get(TEST_DATABASE_URL_ENV),
    reason=f"set {TEST_DATABASE_URL_ENV} to a throwaway database to run real-Postgres tests",
)
