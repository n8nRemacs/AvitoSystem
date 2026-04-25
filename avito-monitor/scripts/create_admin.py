"""Create or update an admin user.

Usage (inside the `app` container):
    python -m scripts.create_admin <username> <password>
"""
import asyncio
import sys

from sqlalchemy import select

from app.db.base import dispose_engine, get_sessionmaker
from app.db.models import User
from app.services.auth import hash_password


async def upsert_admin(username: str, password: str) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing is None:
            user = User(
                username=username,
                password_hash=hash_password(password),
                is_admin=True,
                is_active=True,
            )
            session.add(user)
            action = "created"
        else:
            existing.password_hash = hash_password(password)
            existing.is_admin = True
            existing.is_active = True
            action = "updated"
        await session.commit()
    print(f"Admin user '{username}' {action}.")


async def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.create_admin <username> <password>")
        sys.exit(2)
    username, password = sys.argv[1], sys.argv[2]
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(2)
    try:
        await upsert_admin(username, password)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
