"""Outbound notifications (ADR-012). Telegram is the phone-side channel; everything else
also lands in the UI via the DB/Redis. Never include secrets in messages."""

from __future__ import annotations

from typing import Protocol

import httpx

from core.logging import get_logger
from core.settings import Settings

log = get_logger(__name__)


class Notifier(Protocol):
    async def send(self, text: str, *, level: str = "info") -> bool: ...


class NullNotifier:
    """Used when Telegram is not configured; logs instead of sending."""

    async def send(self, text: str, *, level: str = "info") -> bool:
        log.info("notify.skipped", level=level, text=text)
        return False


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, *, timeout: float = 10.0) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._timeout = timeout

    async def send(self, text: str, *, level: str = "info") -> bool:
        prefix = {"info": "[i]", "warning": "⚠️", "critical": "🛑", "success": "✅"}.get(level, "")
        payload = {
            "chat_id": self._chat_id,
            "text": f"{prefix} {text}".strip(),
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(self._url, json=payload)
                r.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.warning("notify.telegram_failed", error=str(exc))
            return False


def build_notifier(settings: Settings) -> Notifier:
    token = settings.telegram_bot_token.get_secret_value()
    if token and settings.telegram_chat_id:
        return TelegramNotifier(token, settings.telegram_chat_id)
    return NullNotifier()
