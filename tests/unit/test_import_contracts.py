"""Guards the machine-enforced architecture boundary against silent rot.

`importlinter.ini`'s `plugins-independence` contract lists plugin modules by
hand. That list once named five plugins that had been deleted and none of the
plugins that existed, which made `lint-imports` abort with "Module ... does not
exist" *before* it evaluated any other contract. The layering rules looked
enforced in CI and were not: a real `core -> cli` violation sat undetected.

These tests keep the config honest, and assert that the package's own public
entry points import cleanly.
"""

from __future__ import annotations

import configparser
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGINS_DIR = REPO_ROOT / "plugins"
CONFIG = REPO_ROOT / "importlinter.ini"


def _declared_plugin_modules() -> set[str]:
    """The plugin modules named in the independence contract."""
    parser = configparser.ConfigParser()
    parser.read(CONFIG, encoding="utf-8")
    section = parser["importlinter:contract:plugins-independence"]
    return {
        line.strip().removeprefix("plugins.")
        for line in section["modules"].splitlines()
        if line.strip()
    }


def _plugin_folders() -> set[str]:
    """Every plugin folder on disk that carries a manifest."""
    return {
        d.name
        for d in PLUGINS_DIR.iterdir()
        if d.is_dir() and (d / "plugin.yaml").is_file()
    }


class TestImportContractConfig:
    def test_contract_lists_exactly_the_plugins_on_disk(self):
        """A plugin added or removed without updating importlinter.ini crashes
        the linter, which disables every other contract with it."""
        declared, on_disk = _declared_plugin_modules(), _plugin_folders()
        assert declared == on_disk, (
            f"importlinter.ini is out of sync with plugins/: "
            f"listed but missing={sorted(declared - on_disk)}, "
            f"on disk but unlisted={sorted(on_disk - declared)}"
        )

    def test_every_listed_module_is_importable(self):
        """`lint-imports` resolves each name as a module; an unimportable one
        aborts the run rather than failing a single contract."""
        for name in sorted(_declared_plugin_modules()):
            importlib.import_module(f"plugins.{name}")


class TestPublicEntryPoints:
    @pytest.mark.parametrize(
        "module", ["cli.main", "cli.api", "cli.composition", "core.defaults"]
    )
    def test_imports_cleanly(self, module):
        """`core/api.py` shipped for weeks raising ImportError on a name that had
        moved modules. Nothing imported it, so nothing caught it."""
        importlib.import_module(module)

    def test_api_exports_documented_surface(self):
        """The names the manual tells people to use must actually exist."""
        api = importlib.import_module("cli.api")
        for name in ("run_scraper", "run_job_file", "resolve_plugin", "list_plugins"):
            assert hasattr(api, name), f"cli.api.{name} is documented but missing"

    def test_core_does_not_import_cli(self):
        """Layering rule 1, spot-checked here so it fails fast in the unit suite
        as well as under lint-imports."""
        offenders = [
            path.relative_to(REPO_ROOT)
            for path in (REPO_ROOT / "core").rglob("*.py")
            if "import cli" in path.read_text(encoding="utf-8")
        ]
        assert not offenders, f"core must not import cli; offenders: {offenders}"
