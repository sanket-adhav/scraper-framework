"""Runtime parameter validation and coercion against a plugin's declared contract.

The caller passes a raw parameter bag (typically strings off a CLI or a dict);
this module checks it against the plugin's `params` declaration, rejects unknown
or missing-required parameters, coerces each value to its declared type, and
fills in defaults. The output is a clean, typed value map ready for template
substitution. No website knowledge lives here — only the generic type rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from core.errors.exceptions import ParamError
from core.plugin.manifest import ParamSpec


def validate_params(
    contract: Mapping[str, ParamSpec], supplied: Mapping[str, Any]
) -> dict[str, Any]:
    """Validates `supplied` against the plugin's `contract` and returns the
    coerced, defaulted values.

    Rules, all generic:
      * a supplied parameter not in the contract is an error (catches typos);
      * a required parameter with no supplied value is an error;
      * a supplied value is coerced to its declared type (raising on bad input);
      * a parameter with a default and no supplied value takes the default;
      * an optional parameter with neither value nor default is simply omitted —
        the template renders it as empty, which is how "scrape everything" works.
    """
    unknown = set(supplied) - set(contract)
    if unknown:
        raise ParamError(
            f"unknown parameter(s) {sorted(unknown)}; "
            f"this plugin accepts {sorted(contract) or 'none'}"
        )

    resolved: dict[str, Any] = {}
    for name, spec in contract.items():
        if name in supplied and supplied[name] is not None:
            resolved[name] = _coerce(name, spec, supplied[name])
        elif spec.default is not None:
            resolved[name] = _coerce(name, spec, spec.default)
        elif spec.required:
            raise ParamError(f"required parameter {name!r} was not supplied")
        # else: optional, no default → omitted (renders to empty string)
    return resolved


def _coerce(name: str, spec: ParamSpec, value: Any) -> Any:
    """Coerces one value to its declared type, raising ParamError on bad input."""
    param_type = spec.type
    try:
        if param_type == "string":
            return str(value)
        if param_type == "integer":
            return int(value)
        if param_type == "number":
            return float(value)
        if param_type == "boolean":
            return _coerce_bool(value)
        if param_type == "date":
            return _coerce_date(value, spec.format)
    except (ValueError, TypeError) as err:
        raise ParamError(f"parameter {name!r} is not a valid {param_type}: {value!r}") from err
    raise ParamError(f"parameter {name!r} has unknown type {param_type!r}")


def _coerce_bool(value: Any) -> bool:
    """Accepts real bools and the usual string spellings; rejects anything else."""
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    raise ValueError(value)


def _coerce_date(value: Any, fmt: str | None = None) -> str:
    """Validates an ISO date (YYYY-MM-DD) and returns it as a normalised string.
    If fmt is provided, it uses strftime to format the output.

    Kept as a string, not a date object, so it substitutes cleanly into URLs and
    validator values; the point of the type is to reject malformed input early."""
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        d = date.fromisoformat(str(value).strip())

    if fmt:
        return d.strftime(fmt)
    return d.isoformat()
