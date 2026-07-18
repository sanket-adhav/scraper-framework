"""SecretsProvider contract — resolves `secret://` references at runtime (plan2.md §9).

Config never carries plaintext credentials; it carries references like
`secret://env/SHOP_PASSWORD`. Phase 1 resolves them from environment
variables; Plan 10 swaps in a real vault behind this same contract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.errors.exceptions import ConfigError

SECRET_REF_PREFIX = "secret://"


class SecretNotFoundError(ConfigError):
    """A secret reference could not be resolved by the configured provider."""


@runtime_checkable
class SecretsProvider(Protocol):
    """Anything that can turn a `secret://...` reference into the secret value."""

    def resolve(self, ref: str) -> str:
        """Returns the secret value for one full `secret://provider/key` reference."""
        ...
