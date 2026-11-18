"""In-process registry of replay sessions (one API process owns them)."""

from __future__ import annotations

from datetime import timedelta

from api.replay.session import ReplaySession
from core.time import utcnow

MAX_PER_USER = 5
TTL = timedelta(minutes=30)


class ReplayManager:
    def __init__(self) -> None:
        self._sessions: dict[str, ReplaySession] = {}

    async def sweep(self) -> int:
        now = utcnow()
        dead = [s for s in self._sessions.values() if now - s.last_activity > TTL]
        for s in dead:
            await s.close()
            self._sessions.pop(s.session_id, None)
        return len(dead)

    def count_for(self, user_id: int) -> int:
        return sum(1 for s in self._sessions.values() if s.user_id == user_id)

    def add(self, s: ReplaySession) -> ReplaySession:
        if self.count_for(s.user_id) >= MAX_PER_USER:
            raise RuntimeError(f"at most {MAX_PER_USER} replay sessions per user")
        self._sessions[s.session_id] = s
        return s

    def get(self, session_id: str, user_id: int) -> ReplaySession | None:
        s = self._sessions.get(session_id)
        if s is None or s.user_id != user_id:
            return None
        return s

    async def remove(self, session_id: str, user_id: int) -> bool:
        s = self.get(session_id, user_id)
        if s is None:
            return False
        await s.close()
        del self._sessions[session_id]
        return True

    def list_for(self, user_id: int) -> list[ReplaySession]:
        return [s for s in self._sessions.values() if s.user_id == user_id]


manager = ReplayManager()
