"""The config-spec test machinery (plan2.md §11): every spec in the repo is
auto-discovered and run against its stored sample fixture. This suite grows
with every plugin, forever — a selector typo or site drift fails here first.

Spec-file convention: parser, fixture, optional sample_url, extract (the spec),
expect (field → expected value).
"""

from pathlib import Path

import pytest
import yaml

from cli.composition import default_registry
from components.extractors.spec_driven import SpecDrivenExtractor
from core.config.capability_check import check_spec_against_capabilities
from core.config.schema import ExtractConfigModel
from tests.helpers import fixture_response

REPO_ROOT = Path(__file__).parent.parent.parent

# Every place specs live: framework demo specs now, plugin specs from Plan 06 on.
SPEC_GLOBS = [
    REPO_ROOT / "tests" / "config_specs" / "specs",
    REPO_ROOT / "plugins",
]


def discover_specs() -> list[Path]:
    """Finds every committed spec file (any yaml declaring an `extract` section)."""
    found: list[Path] = []
    for root in SPEC_GLOBS:
        if root.exists():
            found.extend(sorted(root.rglob("*.yaml")))
    specs = []
    for p in found:
        doc = yaml.safe_load(p.read_text())
        if isinstance(doc, dict) and "extract" in doc:
            specs.append(p)
    return specs


SPECS = discover_specs()


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda p: p.stem)
class TestEverySpecAgainstItsFixture:
    def test_spec_matches_document_capabilities(self, spec_path):
        """The load-time capability check must pass for the spec's own parser.
        A work-in-progress plugin that hasn't declared a `parser` yet is skipped —
        the check runs the moment the wiring is added."""
        doc = yaml.safe_load(spec_path.read_text())
        if "parser" not in doc:
            pytest.skip(f"{spec_path.name}: no `parser` yet (work in progress)")
        spec = ExtractConfigModel.model_validate(doc["extract"])
        parser_cls = default_registry().factory("parser", doc["parser"])
        field_kinds = {
            name: fs.kind for name, fs in spec.spec.items() if fs.against is None
        }
        check_spec_against_capabilities(
            field_kinds, parser_cls.document_type.capabilities, parser_cls.document_type.__name__
        )

    def test_spec_extracts_expected_values_from_fixture(self, spec_path):
        """Running the spec on its stored sample must yield the expected fields.
        A spec without `parser`/`fixture`/`expect` test wiring is skipped until
        its author adds them (the merge gate requires them before production)."""
        doc = yaml.safe_load(spec_path.read_text())
        if not all(k in doc for k in ("parser", "fixture", "expect")):
            pytest.skip(f"{spec_path.name}: no fixture/expect wiring yet (work in progress)")
        spec = ExtractConfigModel.model_validate(doc["extract"])
        registry = default_registry()
        parser = registry.factory("parser", doc["parser"])()
        content_type = next(iter(parser.content_types))
        document = parser.parse(_fixture_for(spec_path, doc["fixture"], content_type))
        record = SpecDrivenExtractor().extract(
            document, spec, source_url=doc.get("sample_url", "")
        )
        for field, expected in (doc.get("expect") or {}).items():
            assert record.data.get(field) == expected, f"field {field!r} mismatch"


def _fixture_for(spec_path: Path, name: str, content_type: str):
    """Loads a spec's sample fixture: from the plugin's own fixtures/ folder when
    the spec lives in a plugin, else from the shared tests/fixtures corpus."""
    plugin_fixture = spec_path.parent.parent / "fixtures" / name
    if plugin_fixture.is_file():
        from core.models import Response

        return Response(status=200, body=plugin_fixture.read_bytes(), content_type=content_type)
    return fixture_response(name, content_type)


def test_at_least_the_demo_and_plugin_specs_are_discovered():
    """The machinery itself must never silently discover nothing."""
    assert len(SPECS) >= 4  # two demo specs + two Phase-1 plugin specs
