# ADR-014: Single operator now, multi-user and RBAC ready

**Status:** Accepted · **Date:** 2026-11-14

## Decision
All owned entities carry `user_id`. Auth is email + password with Argon2, short-lived
JWT access tokens and rotating refresh tokens, plus optional TOTP. Roles (`owner`,
`trader`, `viewer`) exist from the first migration; v1 ships with one `owner` user created
by a CLI command. No public sign-up endpoint in v1.

## Consequences
- Row-level filtering by `user_id` is in the repository layer from day one.
