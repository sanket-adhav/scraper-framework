"""The plugin.yaml manifest schema (plan2.md §10, §12).

Every plugin declares who it is, its anti-bot difficulty tier, which source
approval covers it (the §13 legal gate), which config files it ships, and any
Python components it contributes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from core.errors.exceptions import PluginError


class PluginManifest(BaseModel):
    """Everything a plugin declares about itself in plugin.yaml."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(min_length=1)
    description: str = ""
    tier: Literal["open", "defended", "hostile"] = "open"
    source_approval: str = Field(min_length=1)  # e.g. "docs/source_approval.md#SRC-0001"
    config_files: list[str] = Field(default_factory=lambda: ["config/extraction.yaml"])
    components: dict[str, dict[str, str]] = Field(default_factory=dict)
    """Contributed Python components: kind → {name: "file.py:ClassName"}."""


def load_manifest(path: Path) -> PluginManifest:
    """Reads and validates one plugin.yaml, raising PluginError with clear detail."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        raise PluginError(f"cannot read manifest {path}: {err}") from err
    if not isinstance(raw, dict):
        raise PluginError(f"manifest {path} must be a mapping")
    try:
        return PluginManifest.model_validate(raw)
    except PydanticValidationError as err:
        raise PluginError(f"invalid manifest {path}:\n{err}") from err
