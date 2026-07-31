"""Encrypted-at-rest session store keyed by (plugin, account) — plan2.md Plan 07.

Sessions hold cookies/tokens, so they are encrypted on disk with Fernet
(AES-128). The key comes from config as a `secret://` reference, never plaintext.
Survives process restarts, so a login is not repeated every run.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from core.contracts.login_provider import Session
from core.errors.exceptions import AuthError


class EncryptedSessionStore:
    """Saves and loads Sessions as encrypted files, one per (plugin, account)."""

    def __init__(self, directory: str | Path, key: str) -> None:
        """Creates the store directory and prepares the Fernet cipher from the key."""
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        try:
            self._cipher = Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError) as err:
            raise AuthError(f"invalid session-store key: {err}") from err

    @staticmethod
    def generate_key() -> str:
        """Returns a fresh Fernet key string (store it as a secret, reuse it)."""
        return Fernet.generate_key().decode()

    def get(self, plugin: str, account: str) -> Session | None:
        """Loads and decrypts the saved session, or None if there isn't one."""
        path = self._path(plugin, account)
        if not path.is_file():
            return None
        try:
            raw = self._cipher.decrypt(path.read_bytes())
        except InvalidToken as err:
            raise AuthError(f"cannot decrypt session for {plugin}/{account} (wrong key?)") from err
        data = json.loads(raw)
        return Session(
            cookies=data["cookies"],
            headers=data["headers"],
            acquired_at=datetime.fromisoformat(data["acquired_at"]),
        )

    def put(self, plugin: str, account: str, session: Session) -> None:
        """Encrypts and writes the session for later runs."""
        payload = json.dumps(
            {
                "cookies": dict(session.cookies),
                "headers": dict(session.headers),
                "acquired_at": session.acquired_at.isoformat(),
            }
        ).encode()
        self._path(plugin, account).write_bytes(self._cipher.encrypt(payload))

    def _path(self, plugin: str, account: str) -> Path:
        """Builds the on-disk filename for one (plugin, account) session."""
        safe = f"{plugin}__{account}".replace("/", "_")
        return self._dir / f"{safe}.session"
