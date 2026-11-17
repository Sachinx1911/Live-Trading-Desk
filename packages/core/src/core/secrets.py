"""Encryption at rest for broker credentials (CLAUDE.md rule 8). Fernet, key from SECRETS_KEY."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class SecretBox:
    def __init__(self, key: str) -> None:
        if key.startswith("CHANGE_ME"):
            raise ValueError("SECRETS_KEY is not configured; see .env.example")
        self._f = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._f.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:  # pragma: no cover - defensive
            raise ValueError("cannot decrypt secret: wrong key or corrupted value") from exc

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("ascii")
