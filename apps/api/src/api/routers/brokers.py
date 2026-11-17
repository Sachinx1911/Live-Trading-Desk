"""Broker accounts, daily OAuth login and session status (ADR-012)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from api.audit import audit
from api.deps import DB, State, User
from core.logging import get_logger
from core.services.brokers import SUPPORTED, BrokerError, BrokerService, SessionStatus

router = APIRouter(prefix="/brokers", tags=["brokers"])
log = get_logger(__name__)

OAUTH_STATE_TTL = 600


class AccountIn(BaseModel):
    client_code: str = Field(min_length=1, max_length=64)
    api_key: str | None = Field(default=None, max_length=256)
    api_secret: str | None = Field(default=None, max_length=256)
    label: str = ""


class SessionStatusOut(BaseModel):
    broker: str
    account_id: int | None
    client_code: str | None
    configured: bool
    status: str
    issued_at: str | None
    expires_at: str | None
    last_checked_at: str | None
    login_supported: bool


class LoginUrlOut(BaseModel):
    url: str
    state: str
    expires_in: int


def _out(s: SessionStatus) -> SessionStatusOut:
    return SessionStatusOut(
        broker=s.broker,
        account_id=s.account_id,
        client_code=s.client_code,
        configured=s.configured,
        status=s.status,
        issued_at=s.issued_at.isoformat() if s.issued_at else None,
        expires_at=s.expires_at.isoformat() if s.expires_at else None,
        last_checked_at=s.last_checked_at.isoformat() if s.last_checked_at else None,
        login_supported=s.broker == "upstox",
    )


def _svc(db: DB, state: State) -> BrokerService:
    if state.secret_box is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SECRETS_KEY not configured")
    return BrokerService(db, state.settings, state.secret_box)


@router.get("", response_model=list[SessionStatusOut])
async def list_brokers(db: DB, state: State, user: User) -> list[SessionStatusOut]:
    svc = _svc(db, state)
    return [_out(await svc.status(user.user_id, code)) for code in sorted(SUPPORTED)]


@router.put("/{code}/account", response_model=SessionStatusOut)
async def upsert_account(
    code: str, body: AccountIn, db: DB, state: State, user: User
) -> SessionStatusOut:
    svc = _svc(db, state)
    try:
        acct = await svc.upsert_account(
            user.user_id,
            code,
            client_code=body.client_code,
            api_key=body.api_key,
            api_secret=body.api_secret,
            label=body.label,
        )
    except BrokerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await audit(
        db,
        user_id=user.user_id,
        action="broker.account.upsert",
        entity_type="broker_account",
        entity_id=acct.id,
        after={"broker": code, "client_code": body.client_code, "key_set": bool(body.api_key)},
    )
    await db.commit()
    return _out(await svc.status(user.user_id, code))


@router.get("/{code}/login-url", response_model=LoginUrlOut)
async def login_url(code: str, db: DB, state: State, user: User) -> LoginUrlOut:
    if code != "upstox":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth login only implemented for upstox")
    svc = _svc(db, state)
    acct = await svc.get_account(user.user_id, code)
    if acct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "broker account not configured")
    try:
        key, secret = svc.credentials(acct)
    except BrokerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    from providers.upstox.auth import UpstoxAuth

    oauth_state = svc.new_state()
    await state.redis.set(
        f"broker_oauth:{oauth_state}", f"{user.user_id}:{acct.id}", ex=OAUTH_STATE_TTL
    )
    url = UpstoxAuth(key, secret, svc.redirect_uri(code)).login_url(oauth_state)
    return LoginUrlOut(url=url, state=oauth_state, expires_in=OAUTH_STATE_TTL)


@router.get("/{code}/callback", include_in_schema=False)
async def oauth_callback(
    code: str,
    db: DB,
    state: State,
    oauth_code: Annotated[str | None, Query(alias="code")] = None,
    oauth_state: Annotated[str | None, Query(alias="state")] = None,
) -> RedirectResponse:
    """Public endpoint hit by the broker after the user logs in. The `state` nonce ties the
    callback to the user who requested it; no bearer token is present on this request."""
    web = state.settings.web_base_url.rstrip("/")
    fail = f"{web}/settings/brokers?broker={code}&login=failed"
    if code != "upstox" or not oauth_code or not oauth_state:
        return RedirectResponse(fail + "&reason=missing_params", status_code=302)
    bound = await state.redis.getdel(f"broker_oauth:{oauth_state}")
    if not bound:
        return RedirectResponse(fail + "&reason=bad_state", status_code=302)
    user_id, account_id = (int(x) for x in bound.split(":"))
    svc = _svc(db, state)
    acct = await svc.get_account(user_id, code)
    if acct is None or acct.id != account_id:
        return RedirectResponse(fail + "&reason=account", status_code=302)
    from providers.upstox.auth import UpstoxAuth
    from providers.upstox.errors import UpstoxAuthError

    key, secret = svc.credentials(acct)
    try:
        token, expires_at = await UpstoxAuth(key, secret, svc.redirect_uri(code)).exchange_code(
            oauth_code
        )
    except UpstoxAuthError as exc:
        log.warning("broker.login_failed", broker=code, error=str(exc))
        return RedirectResponse(fail + "&reason=exchange", status_code=302)
    sess = await svc.store_session(acct, token, expires_at)
    state.broker_tokens[code] = token
    await audit(
        db,
        user_id=user_id,
        action="broker.session.login",
        entity_type="broker_session",
        entity_id=sess.id,
        after={"broker": code, "expires_at": expires_at.isoformat()},
    )
    await db.commit()
    log.info("broker.login_ok", broker=code, expires_at=expires_at.isoformat())
    return RedirectResponse(f"{web}/settings/brokers?broker={code}&login=ok", status_code=302)


@router.get("/{code}/status", response_model=SessionStatusOut)
async def session_status(code: str, db: DB, state: State, user: User) -> SessionStatusOut:
    if code not in SUPPORTED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown broker")
    svc = _svc(db, state)
    return _out(await svc.status(user.user_id, code))


@router.post("/{code}/logout", response_model=SessionStatusOut)
async def revoke_session(code: str, db: DB, state: State, user: User) -> SessionStatusOut:
    svc = _svc(db, state)
    acct = await svc.get_account(user.user_id, code)
    if acct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "broker account not configured")
    sess = await svc.latest_session(acct.id)
    if sess is not None:
        from core.db.models._enums import BrokerSessionStatus

        sess.status = BrokerSessionStatus.REVOKED
        state.broker_tokens.pop(code, None)
        await audit(
            db,
            user_id=user.user_id,
            action="broker.session.revoke",
            entity_type="broker_session",
            entity_id=sess.id,
        )
        await db.commit()
    return _out(await svc.status(user.user_id, code))
