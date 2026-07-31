"""Plugin system tests: manifest validation, the quarantine lifecycle, namespaced
component registration, and discovery strategies."""

import pytest
import yaml

from core.errors.exceptions import PluginError
from core.plugin.discovery import scan_directory
from core.plugin.manager import PluginManager
from core.plugin.manifest import load_manifest
from core.registry.registry import Registry

GOOD_MANIFEST = {
    "name": "demo_site",
    "version": "1.0.0",
    "tier": "open",
    "source_approval": "docs/source_approval.md#SRC-0001",
    "config_files": ["config/extraction.yaml"],
}

GOOD_EXTRACTOR_PY = '''
from core.contracts.document import Document
from core.contracts.extractor import ExtractionSpec
from core.models.record import Record, Provenance
from datetime import datetime, UTC


class GoodExtractor:
    """A conforming custom extractor: satisfies the Extractor contract."""

    def extract(self, doc: Document, spec: ExtractionSpec, *, source_url: str = "") -> Record:
        """Returns a fixed record — enough to prove conformance."""
        return Record(
            data={"ok": True},
            schema_version="1",
            provenance=Provenance("demo_site", "1.0.0", "", source_url, datetime.now(UTC)),
        )
'''

BAD_EXTRACTOR_PY = '''
class NotAnExtractor:
    """Missing extract() — must fail the load-time conformance check."""

    def wrong_method(self):
        """Does nothing useful."""
        return None
'''


def write_plugin(root, name, manifest_extra=None, extractor_code=None):
    """Creates one plugin folder in tmp with a manifest, config, and optional code."""
    folder = root / name
    (folder / "config").mkdir(parents=True)
    manifest = {**GOOD_MANIFEST, "name": name, **(manifest_extra or {})}
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    (folder / "config" / "extraction.yaml").write_text(
        yaml.safe_dump({"parser": "html", "urls": [f"file://{name}.html"]})
    )
    if extractor_code is not None:
        (folder / "extractor.py").write_text(extractor_code)
    return folder


class TestManifest:
    def test_valid_manifest_loads(self, tmp_path):
        folder = write_plugin(tmp_path, "demo_site")
        manifest = load_manifest(folder / "plugin.yaml")
        assert manifest.name == "demo_site"
        assert manifest.tier == "open"

    def test_missing_source_approval_rejected(self, tmp_path):
        """The §13 legal gate is mechanical: no approval reference, no load."""
        folder = write_plugin(tmp_path, "demo_site", manifest_extra={"source_approval": ""})
        with pytest.raises(PluginError, match="source_approval"):
            load_manifest(folder / "plugin.yaml")

    def test_bad_tier_rejected(self, tmp_path):
        folder = write_plugin(tmp_path, "demo_site", manifest_extra={"tier": "impossible"})
        with pytest.raises(PluginError, match="tier"):
            load_manifest(folder / "plugin.yaml")

    def test_unknown_keys_rejected(self, tmp_path):
        folder = write_plugin(tmp_path, "demo_site", manifest_extra={"surprise": 1})
        with pytest.raises(PluginError, match="surprise"):
            load_manifest(folder / "plugin.yaml")


class TestDiscovery:
    def test_scan_reports_folders_without_a_manifest_instead_of_hiding_them(self, tmp_path):
        """A folder with no plugin.yaml is still a candidate, so the manager can
        quarantine it with a reason.

        Silently skipping such folders meant a plugin whose manifest was named
        `manifest.yaml` was invisible: not loaded, not quarantined, and absent
        from `list-components` with no warning at all.
        """
        write_plugin(tmp_path, "alpha")
        (tmp_path / "not_a_plugin").mkdir()
        (tmp_path / "__pycache__").mkdir()
        found = scan_directory(tmp_path)
        assert [c.name for c in found] == ["alpha", "not_a_plugin"]

    def test_folder_without_manifest_is_quarantined_with_a_readable_reason(self, tmp_path):
        from core.registry.registry import Registry

        write_plugin(tmp_path, "alpha")
        stray = tmp_path / "misnamed"
        stray.mkdir()
        (stray / "manifest.yaml").write_text("name: misnamed\n", encoding="utf-8")

        manager = PluginManager(Registry())
        manager.load_all(tmp_path)

        assert [p.manifest.name for p in manager.loaded] == ["alpha"]
        assert [q.name for q in manager.quarantined] == ["misnamed"]
        reason = manager.quarantined[0].reason
        assert "plugin.yaml" in reason
        assert "manifest.yaml" in reason  # names the misnamed file it did find

    def test_missing_root_is_empty(self, tmp_path):
        assert scan_directory(tmp_path / "nope") == []


class TestManagerLifecycle:
    def test_broken_plugins_quarantined_others_unaffected(self, tmp_path):
        """Phase-1 exit DoD: a broken plugin never takes the others down."""
        write_plugin(tmp_path, "good_one")
        # broken manifest: empty approval
        write_plugin(tmp_path, "bad_manifest", manifest_extra={"source_approval": ""})
        # failing conformance: declared extractor lacks extract()
        write_plugin(
            tmp_path,
            "bad_component",
            manifest_extra={
                "components": {"extractor": {"broken": "extractor.py:NotAnExtractor"}}
            },
            extractor_code=BAD_EXTRACTOR_PY,
        )
        manager = PluginManager(Registry())
        manager.load_all(tmp_path)
        assert [p.manifest.name for p in manager.loaded] == ["good_one"]
        quarantined = {q.name: q.reason for q in manager.quarantined}
        assert "source_approval" in quarantined["bad_manifest"]
        assert "contract" in quarantined["bad_component"]

    def test_conforming_component_registered_namespaced(self, tmp_path):
        write_plugin(
            tmp_path,
            "custom_site",
            manifest_extra={
                "components": {"extractor": {"fancy": "extractor.py:GoodExtractor"}}
            },
            extractor_code=GOOD_EXTRACTOR_PY,
        )
        registry = Registry()
        manager = PluginManager(registry)
        manager.load_all(tmp_path)
        assert manager.quarantined == []
        assert "custom_site.fancy" in registry.names("extractor")  # namespaced, collision-safe

    def test_duplicate_plugin_name_quarantines_second(self, tmp_path):
        write_plugin(tmp_path, "dir_a", manifest_extra={"name": "same_name"})
        write_plugin(tmp_path, "dir_b", manifest_extra={"name": "same_name"})
        manager = PluginManager(Registry())
        manager.load_all(tmp_path)
        assert len(manager.loaded) == 1
        assert len(manager.quarantined) == 1
        assert "collision" in manager.quarantined[0].reason

    def test_missing_declared_config_file_quarantines(self, tmp_path):
        folder = write_plugin(tmp_path, "no_config")
        (folder / "config" / "extraction.yaml").unlink()
        manager = PluginManager(Registry())
        manager.load_all(tmp_path)
        assert manager.quarantined[0].name == "no_config"
        assert "config file missing" in manager.quarantined[0].reason

    def test_config_for_returns_merged_plugin_config(self, tmp_path):
        write_plugin(tmp_path, "cfg_site")
        manager = PluginManager(Registry())
        manager.load_all(tmp_path)
        assert manager.config_for("cfg_site")["parser"] == "html"
        with pytest.raises(PluginError, match="no loaded plugin"):
            manager.config_for("ghost")
