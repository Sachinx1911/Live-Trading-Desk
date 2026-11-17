"""Broker accounts and daily sessions (ADR-012).

Credentials are encrypted at rest with SecretBox; access tokens likewise. Nothing here
returns a secret to a caller: the API exposes status only, and providers receive a token
*getter* closure.
"""

from __future__ import annotations

import secrets as pysecrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Broker, BrokerAccount, BrokerSession
from core.db.models._enums import BrokerSessionStatus
from core.secrets import SecretBox
from core.settings import Settings
from core.time import utcnow

SUPPORTED = {"upstox", "dhan"}


class BrokerError(Exception):
    pass


@dataclass(frozen=True)
class SessionStatus:
    broker: str
    account_id: int | None
    client_code: str | None
    configured: bool  # api key + secret present
    status: str  # valid | expired | revoked | missing
    issued_at: datetime | None
    expires_at: datetime | None
    last_checked_at: datetime | None


class BrokerService:
    def __init__(self, db: AsyncSession, settings: Settings, box: SecretBox) -> None:
        self.db = db
        self.settings = settings
        self.box = box

    # -- accounts ----------------------------------------------------------------
    async def _broker(self, code: str) -> Broker:
        if code not in SUPPORTED:
            raise BrokerError(f"unsupported broker {code!r}")
        b = (await self.db.execute(select(Broker).where(Broker.code == code))).scalar_one_or_none()
        if b is None:
            raise BrokerError(f"broker {code!r} not seeded")
        return b

    async def get_account(self, user_id: int, code: str) -> BrokerAccount | None:
        b = await self._broker(code)
        res = await self.db.execute(
            select(BrokerAccount)
            .where(BrokerAccount.user_id == user_id, BrokerAccount.broker_id == b.id)
            .order_by(BrokerAccount.id)
        )
        return res.scalars().first()

    async def upsert_account(
        self,
        user_id: int,
        code: str,
        *,
        client_code: str,
        api_key: str | None,
        api_secret: str | None,
        label: str = "",
    ) -> BrokerAccount:
        b = await self._broker(code)
        acct = await self.get_account(user_id, code)
        if acct is None:
            acct = BrokerAccount(user_id=user_id, broker_id=b.id, client_code=client_code)
            self.db.add(acct)
        acct.client_code = client_code
        acct.label = label
        if api_key:
            acct.api_key_enc = self.box.encrypt(api_key).encode()
        if api_secret:
            acct.api_secret_enc = self.box.encrypt(api_secret).encode()
        await self.db.flush()
        return acct

    def credentials(self, acct: BrokerAccount) -> tuple[str, str]:
        if not acct.api_key_enc or not acct.api_secret_enc:
            raise BrokerError("broker API key/secret not configured")
        return (
            self.box.decrypt(acct.api_key_enc.decode()),
            self.box.decrypt(acct.api_secret_enc.decode()),
        )

    def redirect_uri(self, code: str) -> str:
        return f"{self.settings.api_base_url.rstrip('/')}/api/v1/brokers/{code}/callback"

    # -- sessions ----------------------------------------------------------------
    async def latest_session(self, account_id: int) -> BrokerSession | None:
        res = await self.db.execute(
            select(BrokerSession)
            .where(BrokerSession.broker_account_id == account_id)
            .order_by(BrokerSession.issued_at.desc())
        )
        return res.scalars().first()

    async def store_session(
        self, acct: BrokerAccount, access_token: str, expires_at: datetime
    ) -> BrokerSession:
        # Revoke previous valid sessions: one live token per account.
        res = await self.db.execute(
            select(BrokerSession).where(
                BrokerSession.broker_account_id == acct.id,
                BrokerSession.status == BrokerSessionStatus.VALID,
            )
        )
        now = utcnow()
        for old in res.scalars():
            old.status = BrokerSessionStatus.REVOKED
            old.last_checked_at = now
        sess = BrokerSession(
            broker_account_id=acct.id,
            access_token_enc=self.box.encrypt(access_token).encode(),
            issued_at=now,
            expires_at=expires_at,
            status=BrokerSessionStatus.VALID,
            last_checked_at=now,
        )
        self.db.add(sess)
        await self.db.flush()
        return sess

    async def valid_token(self, account_id: int) -> str | None:
        """Decrypted token if a valid, unexpired session exists; marks expiry otherwise."""
        sess = await self.latest_session(account_id)
        if sess is None or sess.status != BrokerSessionStatus.VALID:
            return None
        if sess.expires_at <= utcnow():
            sess.status = BrokerSessionStatus.EXPIRED
            sess.last_checked_at = utcnow()
            await self.db.flush()
            return None
        return self.box.decrypt(sess.access_token_enc.decode())

    async def status(self, user_id: int, code: str) -> SessionStatus:
        acct = await self.get_account(user_id, code)
        if acct is None:
            return SessionStatus(code, None, None, False, "missing", None, None, None)
        sess = await self.latest_session(acct.id)
        configured = bool(acct.api_key_enc and acct.api_secret_enc)
        if sess is None:
            return SessionStatus(
                code, acct.id, acct.client_code, configured, "missing", None, None, None
            )
        st = sess.status.value
        if st == "valid" and sess.expires_at <= utcnow():
            st = "expired"
        return SessionStatus(
            code,
            acct.id,
            acct.client_code,
            configured,
            st,
            sess.issued_at,
            sess.expires_at,
            sess.last_checked_at,
        )

    @staticmethod
    def new_state() -> str:
        return pysecrets.token_urlsafe(24)
