"""The component registry: (kind, name) → factory (plan2.md §3, §8).

The engine never constructs a concrete class itself — it asks the registry.
Registration is manual for now; plugin auto-discovery arrives in Plan 06.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.errors.exceptions import ConfigError

Factory = Callable[..., Any]


class UnknownComponentError(ConfigError):
    """No component is registered under the requested kind and name."""


class DuplicateComponentError(ConfigError):
    """A component with this kind and name is already registered."""


class Registry:
    """Keeps every registered component factory, looked up by kind and name."""

    def __init__(self) -> None:
        """Starts empty; components are registered by hand or by the plugin manager."""
        self._factories: dict[tuple[str, str], Factory] = {}

    def register(self, kind: str, name: str, factory: Factory) -> None:
        """Adds one component factory (usually a class) under (kind, name)."""
        key = (kind, name)
        if key in self._factories:
            raise DuplicateComponentError(f"{kind} {name!r} is already registered")
        self._factories[key] = factory

    def factory(self, kind: str, name: str) -> Factory:
        """Returns the registered factory, or raises with the known names listed."""
        try:
            return self._factories[(kind, name)]
        except KeyError:
            known = sorted(n for k, n in self._factories if k == kind)
            raise UnknownComponentError(
                f"unknown {kind} {name!r}; registered {kind}s: {known}"
            ) from None

    def names(self, kind: str) -> list[str]:
        """Lists the registered names for one kind, sorted."""
        return sorted(name for k, name in self._factories if k == kind)

    def kinds(self) -> list[str]:
        """Lists every kind that has at least one registered component."""
        return sorted({kind for kind, _ in self._factories})
