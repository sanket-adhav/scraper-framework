"""Unit tests for the core data models: frozen, no behavior, builder works."""

import dataclasses
from datetime import UTC, datetime

import pytest

from core.models import (
    Provenance,
    Record,
    Response,
    ScrapeRequest,
    ScrapeRequestBuilder,
    Selector,
    SelectorKind,
)


def make_record() -> Record:
    return Record(
        data={"title": "x"},
        schema_version="1",
        provenance=Provenance(
            plugin_name="example",
            plugin_version="0.1.0",
            config_fingerprint="deadbeef",
            source_url="https://example.com/item/1",
            scraped_at=datetime(2026, 7, 17, tzinfo=UTC),
        ),
    )


class TestFrozenness:
    @pytest.mark.parametrize(
        "instance",
        [
            ScrapeRequest(url="https://example.com"),
            Response(status=200),
            make_record(),
            make_record().provenance,
            Selector(kind=SelectorKind.CSS, query="h1"),
        ],
        ids=lambda i: type(i).__name__,
    )
    def test_models_are_immutable(self, instance):
        a_field = dataclasses.fields(instance)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, a_field, "mutated")


class TestScrapeRequest:
    def test_defaults(self):
        request = ScrapeRequest(url="https://example.com")
        assert request.method == "GET"
        assert request.headers == {}
        assert request.cookies == {}
        assert request.metadata == {}
        assert request.priority == 0
        assert request.attempt == 0

    def test_with_attempt_returns_new_instance(self):
        first = ScrapeRequest(url="https://example.com")
        retried = first.with_attempt(1)
        assert first.attempt == 0
        assert retried.attempt == 1
        assert retried.url == first.url

    def test_builder(self):
        request = (
            ScrapeRequestBuilder("https://example.com/search")
            .method("post")
            .header("Accept", "text/html")
            .cookie("session", "abc")
            .meta("page", 2)
            .priority(5)
            .build()
        )
        assert request.method == "POST"
        assert request.headers == {"Accept": "text/html"}
        assert request.cookies == {"session": "abc"}
        assert request.metadata == {"page": 2}
        assert request.priority == 5

    def test_builder_output_isolated_from_builder(self):
        builder = ScrapeRequestBuilder("https://example.com").header("A", "1")
        request = builder.build()
        builder.header("B", "2")
        assert request.headers == {"A": "1"}


class TestSelector:
    def test_kinds_match_plan(self):
        assert {k.value for k in SelectorKind} == {"css", "xpath", "jsonpath", "regex", "text"}


class TestRecord:
    def test_carries_schema_version_and_full_provenance(self):
        record = make_record()
        assert record.schema_version == "1"
        assert record.provenance.plugin_name == "example"
        assert record.provenance.config_fingerprint == "deadbeef"
        assert record.provenance.source_url.startswith("https://")
        assert record.provenance.scraped_at.tzinfo is not None
