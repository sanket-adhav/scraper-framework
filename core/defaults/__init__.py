"""Framework defaults shipped *inside* the package.

These files used to live in a repo-root ``config/`` directory that was never
included in the built wheel. The result was a silent split-brain: a developer
running from a git checkout got the default middleware stack (rate limiting,
retry, block detection) while anyone who ``pip install``-ed the package got
none of it — same plugin, same command, no warning, and a scraper that hit
target sites at full speed.

Shipping the defaults as package data makes the two paths identical by
construction. ``resolve_default_layers`` raises if they are missing, so a
packaging regression fails loudly at startup instead of silently disabling
the middleware stack.
"""

from __future__ import annotations

from pathlib import Path

from core.errors.exceptions import ConfigError

DEFAULTS_DIR: Path = Path(__file__).resolve().parent

#: Default config files, in load order. Later layers win per key.
DEFAULT_LAYER_NAMES: tuple[str, ...] = ("pipeline.yaml", "middleware.yaml")


def resolve_default_layers() -> list[Path]:
    """Returns the packaged default config layers, in load order.

    Raises:
        ConfigError: if a shipped default is missing — that means the package
            was built without its data files, and every scrape from this
            install would silently run without the default middleware stack.
    """
    layers: list[Path] = []
    for name in DEFAULT_LAYER_NAMES:
        path = DEFAULTS_DIR / name
        if not path.is_file():
            raise ConfigError(
                f"packaged default config {name!r} is missing from {DEFAULTS_DIR}. "
                "The installed package is incomplete — reinstall it. Continuing "
                "would run scrapes with no rate limiting, retry, or block detection."
            )
        layers.append(path)
    return layers


def resolve_presets_dir() -> Path | None:
    """Returns the packaged presets directory, or None if it was not shipped."""
    presets = DEFAULTS_DIR / "presets"
    return presets if presets.is_dir() else None
