"""The small library of per-field cleanup functions specs can chain (plan2.md §5).

Deliberately tiny — the spec's power budget is select + cleanup chain +
required/optional. Anything smarter belongs in a custom Extractor.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from core.errors.exceptions import ExtractionError

_CURRENCY_JUNK = re.compile(r"[₹$€£]|(?i:rs\.?|inr|usd|eur|gbp)|,|\s")


def strip(value: str) -> str:
    """Removes leading/trailing whitespace."""
    return value.strip()


def lower(value: str) -> str:
    """Lowercases the text."""
    return value.lower()


def upper(value: str) -> str:
    """Uppercases the text."""
    return value.upper()


def collapse_whitespace(value: str) -> str:
    """Squeezes any run of whitespace into a single space and trims the ends."""
    return re.sub(r"\s+", " ", value).strip()


def strip_currency(value: str) -> str:
    """Removes currency symbols/codes and thousands separators: '₹4,999.00' → '4999.00'."""
    return _CURRENCY_JUNK.sub("", value)


def to_float(value: str) -> float:
    """Converts the text to a float, or raises a typed extraction error."""
    try:
        return float(value)
    except ValueError as err:
        raise ExtractionError(f"cannot convert {value!r} to float") from err


def to_int(value: str) -> int:
    """Converts the text to an int, or raises a typed extraction error."""
    try:
        return int(float(value))
    except ValueError as err:
        raise ExtractionError(f"cannot convert {value!r} to int") from err


CLEANUPS: dict[str, Callable[[Any], Any]] = {
    "strip": strip,
    "lower": lower,
    "upper": upper,
    "collapse_whitespace": collapse_whitespace,
    "strip_currency": strip_currency,
    "to_float": to_float,
    "to_int": to_int,
}


def apply_chain(value: Any, chain: list[str], field: str) -> Any:
    """Runs the named cleanups over the value in order; unknown names fail clearly."""
    for name in chain:
        if name not in CLEANUPS:
            raise ExtractionError(
                f"unknown cleanup {name!r} on field {field!r}; known: {sorted(CLEANUPS)}",
                field=field,
            )
        value = CLEANUPS[name](value)
    return value
