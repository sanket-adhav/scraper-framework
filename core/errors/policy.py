"""Per-stage, per-error-class error policy loaded from config (plan2.md §10).

Config decides what happens when a stage fails; the stage's own on_error()
is only the fallback when config says nothing.

Example config:
    error_policy:
      default: abort
      max_retries: 2
      on_retry_exhausted: abort
      stages:
        fetch:    { FetchError: retry }
        validate: { ValidationError: quarantine }
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from core.contracts.stage import ErrorAction
from core.errors.exceptions import ConfigError, ScraperError


@dataclass(frozen=True, slots=True)
class ErrorPolicy:
    """Holds the configured error actions and answers 'what do we do with this failure?'."""

    default: ErrorAction = ErrorAction.ABORT
    max_retries: int = 2
    on_retry_exhausted: ErrorAction = ErrorAction.ABORT
    stages: Mapping[str, Mapping[str, ErrorAction]] = field(default_factory=dict)

    def action_for(self, stage_name: str, error: ScraperError) -> ErrorAction | None:
        """Returns the configured action for this stage + error class, walking the
        error's parent classes; None means config is silent (use the stage's fallback)."""
        stage_rules = self.stages.get(stage_name)
        if not stage_rules:
            return None
        for cls in type(error).__mro__:
            if cls.__name__ in stage_rules:
                return stage_rules[cls.__name__]
        return None


def policy_from_config(config: Mapping[str, Any]) -> ErrorPolicy:
    """Builds an ErrorPolicy from the `error_policy` section of resolved config."""
    section = config.get("error_policy") or {}
    try:
        stages = {
            stage: {err: ErrorAction(action) for err, action in rules.items()}
            for stage, rules in (section.get("stages") or {}).items()
        }
        return ErrorPolicy(
            default=ErrorAction(section.get("default", ErrorAction.ABORT)),
            max_retries=int(section.get("max_retries", 2)),
            on_retry_exhausted=ErrorAction(section.get("on_retry_exhausted", ErrorAction.ABORT)),
            stages=stages,
        )
    except ValueError as err:
        raise ConfigError(f"invalid error_policy: {err}") from err
