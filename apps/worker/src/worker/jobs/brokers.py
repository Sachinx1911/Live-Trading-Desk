"""Daily broker session check (ADR-012): 08:15 IST and every 30 minutes during the session.
Expired or missing tokens produce a notification with the login page; never silent."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from core.db import get_session_factory
from core.db.models import Broker, BrokerAccount
from core.logging import get_logger
from core.notify import build_notifier
from core.secrets import SecretBox
from core.settings import get_settings
from core.time import utcnow

log = get_logger(__name__)


async def check_broker_sessions(ctx: dict[str, Any]) -> dict[str, str]:
    settings = get_settings()
    try:
        box = SecretBox(settings.secrets_key.get_secret_value())
    except ValueError:
        log.warning("broker_check.skipped", reason="SECRETS_KEY not configured")
        return {}
    from core.services.brokers import BrokerService  # service lives with the API package

    notifier = build_notifier(settings)
    result: dict[str, str] = {}
    async with get_session_factory()() as db:
        svc = BrokerService(db, settings, box)
        rows = await db.execute(
            select(BrokerAccount, Broker.code)
            .join(Broker, Broker.id == BrokerAccount.broker_id)
            .where(BrokerAccount.is_active.is_(True))
        )
        for acct, code in rows.all():
            tok = await svc.valid_token(acct.id)
            st = "valid" if tok else "expired"
            result[code] = st
            if not tok:
                link = f"{settings.web_base_url.rstrip('/')}/settings/brokers?broker={code}"
                await notifier.send(
                    f"{code.title()} session is not valid. Log in before market open: {link}",
                    level="warning",
                )
        await db.commit()
    await ctx["redis"].set("broker_sessions:last_check", utcnow().isoformat(), ex=24 * 3600)
    log.info("broker_check.done", result=result)
    return result
