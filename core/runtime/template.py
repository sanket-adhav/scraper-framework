"""Placeholder substitution for plugin configuration.

A plugin config carries `${name}` placeholders anywhere a runtime value belongs —
a search URL, a validator's expected value, a result cap. This renderer walks the
whole config (dicts, lists, strings) and substitutes resolved parameter values.

Two deliberate rules keep it predictable:
  * A placeholder for a declared-but-unsupplied parameter renders to empty string.
    An empty `search=` or an empty `contains ""` rule matches everything — that is
    exactly the "scrape everything" behaviour, achieved with no engine special-casing.
  * A placeholder for a name the plugin never declared is an authoring bug and
    raises, so typos surface at resolve time instead of producing silent garbage.

A string that is *only* a single placeholder keeps the value's real type
(`max_results: ${max_results}` stays an int), so downstream typed config still works.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from core.errors.exceptions import ParamError

# ${name} where name is a normal identifier. Escaped as $${name} to emit a literal.
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_WHOLE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def render_template(value: Any, values: Mapping[str, Any], *, declared: set[str]) -> Any:
    """Returns a copy of `value` with every `${name}` substituted.

    `values` holds the resolved parameters actually present; `declared` is the
    full set of names the plugin declared (so an absent-but-declared name renders
    empty, while an undeclared name raises)."""
    if isinstance(value, str):
        return _render_str(value, values, declared)
    if isinstance(value, Mapping):
        return {k: render_template(v, values, declared=declared) for k, v in value.items()}
    if isinstance(value, list):
        return [render_template(v, values, declared=declared) for v in value]
    return value


def _render_str(text: str, values: Mapping[str, Any], declared: set[str]) -> Any:
    """Substitutes placeholders in one string, preserving type for a lone placeholder."""
    whole = _WHOLE.match(text)
    if whole is not None:
        name = whole.group(1)
        _check_declared(name, declared)
        return values.get(name, "")  # lone ${x}: keep the real type (int, etc.)

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        _check_declared(name, declared)
        return str(values.get(name, ""))

    return _PLACEHOLDER.sub(_sub, text)


def _check_declared(name: str, declared: set[str]) -> None:
    """Rejects a placeholder that references a parameter the plugin never declared."""
    if name not in declared:
        raise ParamError(
            f"config references ${{{name}}} but the plugin declares no such param; "
            f"declared: {sorted(declared) or 'none'}"
        )
