"""Tests for the dynamic runtime-parameter system: parameter validation/coercion,
placeholder rendering, and the JobResolver that ties them to a plugin."""

import pytest
import yaml

from core.errors.exceptions import ParamError, PluginError
from core.plugin.manager import PluginManager
from core.plugin.manifest import ParamSpec
from core.registry.registry import Registry
from core.runtime.params import validate_params
from core.runtime.resolver import JobResolver
from core.runtime.template import render_template

CONTRACT = {
    "title": ParamSpec(type="string", required=False),
    "from_date": ParamSpec(type="date", required=False),
    "max_results": ParamSpec(type="integer", default=100),
    "min_price": ParamSpec(type="number", required=False),
    "active": ParamSpec(type="boolean", required=False),
}


class TestValidateParams:
    def test_defaults_applied_when_absent(self):
        assert validate_params(CONTRACT, {}) == {"max_results": 100}

    def test_supplied_value_coerced_to_type(self):
        out = validate_params(CONTRACT, {"max_results": "25", "min_price": "9.5"})
        assert out["max_results"] == 25 and isinstance(out["max_results"], int)
        assert out["min_price"] == 9.5 and isinstance(out["min_price"], float)

    def test_iso_date_validated_and_normalised(self):
        assert validate_params(CONTRACT, {"from_date": "2026-07-01"})["from_date"] == "2026-07-01"

    def test_boolean_spellings(self):
        assert validate_params(CONTRACT, {"active": "yes"})["active"] is True
        assert validate_params(CONTRACT, {"active": "0"})["active"] is False

    def test_unknown_param_rejected(self):
        with pytest.raises(ParamError, match="unknown parameter"):
            validate_params(CONTRACT, {"surprise": 1})

    def test_missing_required_rejected(self):
        contract = {"q": ParamSpec(type="string", required=True)}
        with pytest.raises(ParamError, match="required parameter 'q'"):
            validate_params(contract, {})

    def test_bad_type_rejected(self):
        with pytest.raises(ParamError, match="not a valid integer"):
            validate_params(CONTRACT, {"max_results": "lots"})

    def test_bad_date_rejected(self):
        with pytest.raises(ParamError, match="not a valid date"):
            validate_params(CONTRACT, {"from_date": "01/07/2026"})

    def test_optional_absent_is_omitted_not_none(self):
        out = validate_params(CONTRACT, {})
        assert "title" not in out  # omitted → renders empty → "scrape everything"


class TestRenderTemplate:
    def test_substitutes_declared_values(self):
        out = render_template("q=${title}", {"title": "abc"}, declared={"title"})
        assert out == "q=abc"

    def test_absent_declared_renders_empty(self):
        out = render_template("q=${title}", {}, declared={"title"})
        assert out == "q="

    def test_undeclared_placeholder_raises(self):
        with pytest.raises(ParamError, match="no such param"):
            render_template("q=${ghost}", {}, declared={"title"})

    def test_lone_placeholder_preserves_type(self):
        out = render_template("${n}", {"n": 42}, declared={"n"})
        assert out == 42 and isinstance(out, int)

    def test_walks_nested_dict_and_list(self):
        tmpl = {"urls": ["a=${x}"], "engine": {"max": "${n}"}}
        out = render_template(tmpl, {"x": "1", "n": 5}, declared={"x", "n"})
        assert out == {"urls": ["a=1"], "engine": {"max": 5}}

    def test_non_string_scalars_untouched(self):
        assert render_template(True, {}, declared=set()) is True
        assert render_template(7, {}, declared=set()) == 7


def _write_plugin(root, name, *, params=None, config=None):
    """Writes a minimal plugin folder with an optional params block and config."""
    folder = root / name
    (folder / "config").mkdir(parents=True)
    manifest = {
        "name": name,
        "version": "1.0.0",
        "tier": "open",
        "source_approval": "docs/source_approval.md#SRC-0001",
        "config_files": ["config/extraction.yaml"],
    }
    if params is not None:
        manifest["params"] = params
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    (folder / "config" / "extraction.yaml").write_text(
        yaml.safe_dump(config or {"parser": "html", "urls": [f"file://{name}.html"]})
    )
    return folder


class TestJobResolver:
    def test_resolves_title_date_and_everything(self, tmp_path):
        """The same plugin, unchanged, executes three different queries."""
        _write_plugin(
            tmp_path,
            "sebi_like",
            params={
                "title": {"type": "string", "required": False},
                "from_date": {"type": "date", "required": False},
                "max_results": {"type": "integer", "default": 50},
            },
            config={
                "parser": "html",
                "urls": ["https://x/search?q=${title}&from=${from_date}"],
                "engine": {"max_requests": "${max_results}"},
            },
        )
        resolver = JobResolver.from_directory(tmp_path, Registry())

        by_title = resolver.resolve("sebi_like", {"title": "SIF"})
        assert by_title.config["urls"][0] == "https://x/search?q=SIF&from="
        assert by_title.config["engine"]["max_requests"] == 50  # default, int-typed

        by_date = resolver.resolve("sebi_like", {"from_date": "2026-07-01"})
        assert by_date.config["urls"][0] == "https://x/search?q=&from=2026-07-01"

        everything = resolver.resolve("sebi_like", {})
        assert everything.config["urls"][0] == "https://x/search?q=&from="

    def test_backward_compatible_plugin_without_params(self, tmp_path):
        """A plugin with no params section resolves to its config unchanged."""
        _write_plugin(tmp_path, "legacy", config={"parser": "html", "urls": ["file://a.html"]})
        resolver = JobResolver.from_directory(tmp_path, Registry())
        resolved = resolver.resolve("legacy", {})
        assert resolved.params == {}
        assert resolved.config["urls"] == ["file://a.html"]

    def test_different_plugins_declare_different_params(self, tmp_path):
        """The framework is generic: an Amazon-shaped plugin uses its own params."""
        _write_plugin(
            tmp_path,
            "amazon_like",
            params={
                "keyword": {"type": "string", "required": True},
                "max_price": {"type": "number", "required": False},
            },
            config={"parser": "html", "urls": ["https://a/s?k=${keyword}&hi=${max_price}"]},
        )
        resolver = JobResolver.from_directory(tmp_path, Registry())
        out = resolver.resolve("amazon_like", {"keyword": "usb-c", "max_price": "30"})
        assert out.config["urls"][0] == "https://a/s?k=usb-c&hi=30.0"

    def test_unknown_plugin_raises(self, tmp_path):
        resolver = JobResolver.from_directory(tmp_path, Registry())
        with pytest.raises(PluginError, match="no loaded plugin"):
            resolver.resolve("ghost", {})

    def test_bad_param_surfaces_as_param_error(self, tmp_path):
        _write_plugin(
            tmp_path,
            "amazon_like",
            params={"keyword": {"type": "string", "required": True}},
            config={"parser": "html", "urls": ["https://a/s?k=${keyword}"]},
        )
        resolver = JobResolver.from_directory(tmp_path, Registry())
        with pytest.raises(ParamError, match="required parameter 'keyword'"):
            resolver.resolve("amazon_like", {})


def test_manager_get_returns_manifest_and_config(tmp_path):
    """PluginManager.get exposes the manifest the resolver needs (params live there)."""
    _write_plugin(tmp_path, "p", params={"title": {"type": "string"}})
    manager = PluginManager(Registry())
    manager.load_all(tmp_path)
    loaded = manager.get("p")
    assert "title" in loaded.manifest.params
    assert loaded.manifest.params["title"].type == "string"
