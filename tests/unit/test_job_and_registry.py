"""Tests for ScrapeJob serialization (queue-readiness) and the component registry."""

import json

import pytest

from core.engine.job import ScrapeJob
from core.models import ScrapeRequest
from core.registry.factories import build_component
from core.registry.registry import DuplicateComponentError, Registry, UnknownComponentError


class TestScrapeJobSerialization:
    def test_dict_round_trip_preserves_everything(self):
        """Plan 09's queue depends on this exact property — prepaid here."""
        job = ScrapeJob(
            requests=(
                ScrapeRequest(url="https://a.example", headers={"A": "1"}, metadata={"p": 1}),
                ScrapeRequest(url="https://b.example", method="POST", priority=5),
            ),
            plugin="shopverse",
            config_overrides={"engine": {"max_requests": 3}},
            priority=7,
        )
        assert ScrapeJob.from_dict(job.to_dict()) == job

    def test_round_trip_survives_json(self):
        """The dict form must be plain enough for JSON — no exotic objects."""
        job = ScrapeJob(requests=(ScrapeRequest(url="https://a.example"),))
        assert ScrapeJob.from_dict(json.loads(json.dumps(job.to_dict()))) == job


class TestRegistry:
    def test_register_and_build(self):
        registry = Registry()
        registry.register("repository", "csv", dict)  # any callable works as a factory
        built = build_component(registry, "repository", "csv", {"a": 1})
        assert built == {"a": 1}

    def test_unknown_component_lists_known_names(self):
        registry = Registry()
        registry.register("stage", "fetch", object)
        with pytest.raises(UnknownComponentError, match=r"registered stages?: \['fetch'\]"):
            registry.factory("stage", "nosuch")

    def test_duplicate_registration_rejected(self):
        registry = Registry()
        registry.register("stage", "fetch", object)
        with pytest.raises(DuplicateComponentError):
            registry.register("stage", "fetch", object)

    def test_names_and_kinds(self):
        registry = Registry()
        registry.register("stage", "fetch", object)
        registry.register("stage", "parse", object)
        registry.register("parser", "html", object)
        assert registry.names("stage") == ["fetch", "parse"]
        assert registry.kinds() == ["parser", "stage"]
