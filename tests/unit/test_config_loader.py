"""Tests for the layered config loader: precedence, presets, fingerprint,
secrets rules, and the load-time name + capability checks."""

import pytest

from components.parsers.html_parser import HtmlParser
from components.parsers.json_parser import JsonParser
from components.secrets.env_provider import EnvSecretsProvider
from core.config.capability_check import CapabilityError
from core.config.loader import load_config, resolve_secret_refs
from core.contracts.secrets_provider import SecretNotFoundError
from core.errors.exceptions import ConfigError
from core.registry.registry import Registry, UnknownComponentError
from tests.fakes import FakeStage


def make_registry() -> Registry:
    """Builds a registry with the standard stub stages and two real parsers."""
    registry = Registry()
    for name in ["fetch", "parse", "extract", "validate", "transform", "persist"]:
        registry.register("stage", name, lambda n=name: FakeStage(n, []))
    registry.register("parser", "html", HtmlParser)
    registry.register("parser", "json", JsonParser)
    return registry


class TestLayering:
    def test_later_layers_win_per_key(self):
        result = load_config(
            [
                {"engine": {"max_requests": 10}, "parser": "html"},
                {"engine": {"max_requests": 99}},
            ]
        )
        assert result.data["engine"]["max_requests"] == 99
        assert result.data["parser"] == "html"  # untouched key survives from the lower layer

    def test_nested_dicts_merge_instead_of_replace(self):
        result = load_config(
            [
                {"stage_timeouts": {"fetch": 30, "parse": 5}},
                {"stage_timeouts": {"fetch": 60}},
            ]
        )
        assert result.data["stage_timeouts"] == {"fetch": 60, "parse": 5}

    def test_yaml_file_layers(self, tmp_path):
        base = tmp_path / "base.yaml"
        base.write_text("pipeline: [fetch]\nengine: {max_requests: 5}\n")
        override = tmp_path / "override.yaml"
        override.write_text("engine: {max_requests: 7}\n")
        result = load_config([base, override])
        assert result.data["pipeline"] == ["fetch"]
        assert result.data["engine"]["max_requests"] == 7

    def test_missing_file_fails_clearly(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config([tmp_path / "nope.yaml"])


class TestPresets:
    def test_preset_is_a_base_the_layer_overrides(self, tmp_path):
        (tmp_path / "crawl.yaml").write_text("pipeline: [fetch, parse]\nparser: html\n")
        result = load_config(
            [{"preset": "crawl", "parser": "json"}],
            presets_dir=tmp_path,
        )
        assert result.data["pipeline"] == ["fetch", "parse"]  # from the preset
        assert result.data["parser"] == "json"  # layer wins over preset

    def test_unknown_preset_fails_clearly(self, tmp_path):
        with pytest.raises(ConfigError, match="preset 'nope'"):
            load_config([{"preset": "nope"}], presets_dir=tmp_path)


class TestFingerprint:
    def test_same_config_same_fingerprint(self):
        a = load_config([{"pipeline": ["fetch"], "engine": {"max_requests": 5}}])
        b = load_config([{"engine": {"max_requests": 5}, "pipeline": ["fetch"]}])
        assert a.fingerprint == b.fingerprint  # key order must not matter

    def test_any_change_changes_fingerprint(self):
        a = load_config([{"pipeline": ["fetch"]}])
        b = load_config([{"pipeline": ["fetch", "parse"]}])
        assert a.fingerprint != b.fingerprint


class TestSecrets:
    def test_plaintext_credential_fails_load(self):
        with pytest.raises(ConfigError, match="auth.password"):
            load_config([{"auth": {"password": "hunter2"}}])

    def test_secret_reference_is_accepted(self):
        result = load_config([{"auth": {"password": "secret://env/SHOP_PASSWORD"}}])
        assert result.data["auth"]["password"] == "secret://env/SHOP_PASSWORD"

    def test_fingerprint_never_sees_resolved_secrets(self, monkeypatch):
        monkeypatch.setenv("SHOP_PASSWORD", "s3cret-value")
        result = load_config([{"auth": {"password": "secret://env/SHOP_PASSWORD"}}])
        assert "s3cret-value" not in str(result.data)

    def test_resolve_secret_refs_via_env(self, monkeypatch):
        monkeypatch.setenv("SHOP_PASSWORD", "s3cret-value")
        resolved = resolve_secret_refs(
            {"auth": {"password": "secret://env/SHOP_PASSWORD", "user": "bot"}},
            EnvSecretsProvider(),
        )
        assert resolved["auth"]["password"] == "s3cret-value"
        assert resolved["auth"]["user"] == "bot"

    def test_missing_env_secret_fails_clearly(self, monkeypatch):
        monkeypatch.delenv("NO_SUCH_SECRET", raising=False)
        with pytest.raises(SecretNotFoundError, match="NO_SUCH_SECRET"):
            resolve_secret_refs("secret://env/NO_SUCH_SECRET", EnvSecretsProvider())


class TestRegistryValidation:
    def test_unknown_stage_name_fails_load(self):
        with pytest.raises(UnknownComponentError, match="nosuch"):
            load_config([{"pipeline": ["fetch", "nosuch"]}], registry=make_registry())

    def test_unknown_parser_fails_load(self):
        with pytest.raises(UnknownComponentError, match="pdf"):
            load_config([{"pipeline": ["fetch"], "parser": "pdf"}], registry=make_registry())

    def test_empty_pipeline_fails_when_registry_given(self):
        with pytest.raises(ConfigError, match="no pipeline"):
            load_config([{"parser": "html"}], registry=make_registry())


class TestCapabilityWiring:
    def test_xpath_spec_against_json_parser_fails_load(self):
        config = {
            "pipeline": ["fetch", "parse", "extract"],
            "parser": "json",
            "extract": {"spec": {"price": {"kind": "xpath", "query": "//span"}}},
        }
        with pytest.raises(CapabilityError, match="'price'"):
            load_config([config], registry=make_registry())

    def test_matching_spec_loads_fine(self):
        config = {
            "pipeline": ["fetch", "parse", "extract"],
            "parser": "html",
            "extract": {"spec": {"title": {"kind": "css", "query": "h1"}}},
        }
        load_config([config], registry=make_registry())

    def test_against_url_fields_skip_document_check(self):
        """A regex matched against the URL is fine even for kinds the doc can't run."""
        config = {
            "pipeline": ["fetch", "parse", "extract"],
            "parser": "json",
            "extract": {
                "spec": {"sku": {"kind": "regex", "query": "/dp/(\\w+)", "against": "url"}}
            },
        }
        load_config([config], registry=make_registry())


class TestShapeValidation:
    def test_bad_shape_fails_clearly(self):
        with pytest.raises(ConfigError, match="invalid config shape"):
            load_config([{"pipeline": "not-a-list"}])

    def test_unknown_extract_keys_rejected(self):
        with pytest.raises(ConfigError, match="invalid config shape"):
            load_config([{"extract": {"spec": {}, "surprise": 1}}])
