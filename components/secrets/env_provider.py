"""Secrets provider that reads `secret://env/NAME` references from environment variables."""

from __future__ import annotations

import os

from core.contracts.secrets_provider import SECRET_REF_PREFIX, SecretNotFoundError


class EnvSecretsProvider:
    """Resolves secret://env/NAME by looking up NAME in the process environment."""

    def resolve(self, ref: str) -> str:
        """Returns the environment variable named in the reference, or raises clearly."""
        prefix = f"{SECRET_REF_PREFIX}env/"
        if not ref.startswith(prefix):
            raise SecretNotFoundError(
                f"EnvSecretsProvider only handles {prefix}NAME references, got {ref!r}"
            )
        name = ref.removeprefix(prefix)
        value = os.environ.get(name)
        if value is None:
            raise SecretNotFoundError(f"environment variable {name!r} is not set (from {ref!r})")
        return value
