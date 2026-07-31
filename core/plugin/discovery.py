"""Plugin discovery strategies (plan2.md §10): directory scan and entry points."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PluginCandidate:
    """One place a plugin might live: its folder and its manifest file."""

    name: str
    path: Path
    manifest_path: Path


MANIFEST_NAME = "plugin.yaml"

#: Folder names that are never plugins, so a missing manifest is not worth
#: reporting for them.
_NOT_PLUGINS = frozenset({"__pycache__", ".git", ".ipynb_checkpoints", ".pytest_cache"})


def scan_directory(root: Path) -> list[PluginCandidate]:
    """Returns every subfolder of `root` that could be a plugin.

    A subfolder *without* a plugin.yaml is still returned, with `manifest_path`
    pointing at where the file should be; the PluginManager then quarantines it
    with a readable reason. Skipping such folders silently — the old behaviour —
    meant a plugin whose manifest was named `manifest.yaml` did not exist as far
    as the framework was concerned: not loaded, not quarantined, and absent from
    `list-components` with no warning. Being invisible is precisely the outcome
    the quarantine design exists to prevent.
    """
    if not root.is_dir():
        return []
    candidates = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in _NOT_PLUGINS:
            continue
        candidates.append(
            PluginCandidate(name=child.name, path=child, manifest_path=child / MANIFEST_NAME)
        )
    return candidates


def entry_point_candidates(
    group: str = "scraper_framework.plugins",
    entry_points: Sequence[metadata.EntryPoint] | None = None,
) -> list[PluginCandidate]:
    """Finds plugins installed as pip packages: each entry point names a package
    whose folder contains a plugin.yaml. `entry_points` is injectable for tests."""
    eps = entry_points if entry_points is not None else metadata.entry_points(group=group)
    candidates = []
    for ep in eps:
        module = ep.load()
        paths = list(getattr(module, "__path__", []))
        if not paths:
            continue  # not a package — nothing to scan
        folder = Path(paths[0])
        manifest = folder / "plugin.yaml"
        if manifest.is_file():
            candidates.append(PluginCandidate(name=ep.name, path=folder, manifest_path=manifest))
    return candidates
