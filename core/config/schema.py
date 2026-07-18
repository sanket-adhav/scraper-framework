"""Pydantic models that validate resolved config at load time (plan2.md §9).

A bad config never starts a scrape: shape errors surface here, name/capability
errors surface in the loader's registry checks.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.contracts.stage import ErrorAction
from core.models.selector import SelectorKind


class FieldSpecModel(BaseModel):
    """One field in an extraction spec: which selector, and how to treat the result."""

    model_config = ConfigDict(extra="forbid")

    kind: SelectorKind
    query: str
    required: bool = True
    cleanup: list[str] = Field(default_factory=list)
    against: str | None = None  # e.g. "url": run the selector against the URL, not the document


class ExtractConfigModel(BaseModel):
    """The extract section: a schema version plus the per-field spec."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    spec: dict[str, FieldSpecModel]


class ErrorPolicyModel(BaseModel):
    """The error_policy section: default action, retry budget, per-stage overrides."""

    model_config = ConfigDict(extra="forbid")

    default: ErrorAction = ErrorAction.ABORT
    max_retries: int = 2
    on_retry_exhausted: ErrorAction = ErrorAction.ABORT
    stages: dict[str, dict[str, ErrorAction]] = Field(default_factory=dict)


class EngineConfigModel(BaseModel):
    """The engine section: safety limits for one job run."""

    model_config = ConfigDict(extra="forbid")

    max_requests: int = 1000


class ComponentRefModel(BaseModel):
    """One configured component: its registered name plus constructor options."""

    model_config = ConfigDict(extra="forbid")

    name: str
    options: dict[str, Any] = Field(default_factory=dict)


class ValidateSectionModel(BaseModel):
    """The validate section: which validators run, in order."""

    model_config = ConfigDict(extra="forbid")

    validators: list[ComponentRefModel] = Field(default_factory=list)


class TransformSectionModel(BaseModel):
    """The transform section: which transformers run, in order."""

    model_config = ConfigDict(extra="forbid")

    transformers: list[ComponentRefModel] = Field(default_factory=list)


class PersistSectionModel(BaseModel):
    """The persist section: which repositories records are saved to."""

    model_config = ConfigDict(extra="forbid")

    repositories: list[ComponentRefModel] = Field(default_factory=list)


class PluginInfoModel(BaseModel):
    """Which plugin this config belongs to — stamped into every record's provenance."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    version: str = ""


class ScraperConfigModel(BaseModel):
    """The whole merged config. Unknown top-level keys are allowed so components
    and plugins can carry their own sections without core knowing about them."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    pipeline: list[str] | None = None
    urls: list[str] = Field(default_factory=list)
    middleware: list[str] = Field(default_factory=list)
    parser: str | None = None
    extractor: str | None = None
    extract: ExtractConfigModel | None = None
    plugin: PluginInfoModel = Field(default_factory=PluginInfoModel)
    validate_: ValidateSectionModel | None = Field(default=None, alias="validate")
    transform_: TransformSectionModel | None = Field(default=None, alias="transform")
    persist_: PersistSectionModel | None = Field(default=None, alias="persist")
    error_policy: ErrorPolicyModel = Field(default_factory=ErrorPolicyModel)
    stage_timeouts: dict[str, float] = Field(default_factory=dict)
    engine: EngineConfigModel = Field(default_factory=EngineConfigModel)
