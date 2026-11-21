"""Paper strategy activations: the one stop path shared by the API and by protocols.

Stopping an activation only changes its row. The paper trader (apps/trader) notices on its
next refresh (about 10 s) and, when the activation still holds a position, squares it off
through the execution simulator, the same deterministic path as the session square-off.
Nothing here places or fills an order (CLAUDE.md rules 1 and 6)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import PaperAccount, StrategyActivation
from core.db.models._enums import ActivationStatus, ActorType
from core.models import TradingMode
from core.services.audit import write_audit
from core.time import utcnow

FLATTEN_SUFFIX = " (flatten)"


async def stop_activation(
    db: AsyncSession,
    activation: StrategyActivation,
    *,
    reason: str,
    flatten: bool,
    user_id: int | None,
    actor: ActorType = ActorType.USER,
) -> bool:
    """Mark a paper activation stopped and write the audit row. Returns False when it was
    already stopped (nothing changed). The caller commits."""
    if activation.status == ActivationStatus.STOPPED:
        return False
    activation.status = ActivationStatus.STOPPED
    activation.stopped_at = utcnow()
    activation.stop_reason = reason + (FLATTEN_SUFFIX if flatten else "")
    write_audit(
        db,
        user_id=user_id,
        action="paper.activation.stop",
        entity_type="strategy_activation",
        entity_id=activation.id,
        reason=reason,
        actor=actor,
    )
    return True


async def running_paper_activations(
    db: AsyncSession, user_id: int | None
) -> list[StrategyActivation]:
    """Active or paused paper activations; of one user's accounts, or of all when None."""
    q = (
        select(StrategyActivation)
        .join(PaperAccount, PaperAccount.id == StrategyActivation.paper_account_id)
        .where(
            StrategyActivation.trading_mode == TradingMode.PAPER,
            StrategyActivation.status != ActivationStatus.STOPPED,
        )
        .order_by(StrategyActivation.id)
    )
    if user_id is not None:
        q = q.where(PaperAccount.user_id == user_id)
    return list((await db.execute(q)).scalars().all())
