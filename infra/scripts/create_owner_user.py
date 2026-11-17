"""Create (or reset the password of) the single owner user. v1 has no sign-up endpoint
(ADR-014). Usage:

    uv run python infra/scripts/create_owner_user.py you@example.com

The password is prompted (not echoed) and never printed. For non-interactive dev/CI use,
set OWNER_PASSWORD in the environment instead of typing it.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from api.security import hash_password
from core.db import session_scope
from core.db.models import Role, User


async def main(email: str) -> None:
    pw = os.environ.get("OWNER_PASSWORD") or getpass.getpass("Password (min 12 chars): ")
    if len(pw) < 12:
        print("password too short", file=sys.stderr)
        raise SystemExit(2)
    if "OWNER_PASSWORD" not in os.environ and pw != getpass.getpass("Repeat: "):
        print("passwords differ", file=sys.stderr)
        raise SystemExit(2)
    async with session_scope() as db:
        owner = (await db.execute(select(Role).where(Role.name == "owner"))).scalar_one()
        res = await db.execute(select(User).where(User.email == email.lower()))
        user = res.scalar_one_or_none()
        if user is None:
            user = User(email=email.lower(), password_hash=hash_password(pw), is_active=True)
            user.roles.append(owner)
            db.add(user)
            print(f"created owner {email}")
        else:
            user.password_hash = hash_password(pw)
            if owner not in user.roles:
                user.roles.append(owner)
            print(f"updated owner {email}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1]))
