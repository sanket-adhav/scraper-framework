"""Pydantic models that validate resolved config at load time (plan2.md §9).

A bad config never starts a scrape: shape errors surface here, name/capability
errors surface in the loader's registry checks.
"""

from __future__ import annotations

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


class ScraperConfigModel(BaseModel):
    """The whole merged config. Unknown top-level keys are allowed so components
    and plugins can carry their own sections without core knowing about them."""

    model_config = ConfigDict(extra="allow")

    pipeline: list[str] | None = None
    middleware: list[str] = Field(default_factory=list)
    parser: str | None = None
    extract: ExtractConfigModel | None = None
    error_policy: ErrorPolicyModel = Field(default_factory=ErrorPolicyModel)
    stage_timeouts: dict[str, float] = Field(default_factory=dict)
    engine: EngineConfigModel = Field(default_factory=EngineConfigModel)
