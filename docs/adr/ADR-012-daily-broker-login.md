# ADR-012: Daily broker token renewal is a user workflow

**Status:** Accepted · **Date:** 2026-11-14

## Context
Upstox access tokens expire daily; Dhan tokens last 24 hours. Both require the user to
complete OAuth/TOTP. Automating this with browser scripts violates broker terms.

## Decision
`broker_sessions` tracks token validity per broker account. A scheduled job at 08:15 IST
checks validity and sends a Telegram/UI notification with the login link. The dashboard
shows a prominent session status. Live and paper engines refuse to start a session with an
expired token and surface it as `Disconnected`, never as stale data.

## Consequences
- Notification channel (Telegram bot) is part of Phase 2, not a later nicety.
