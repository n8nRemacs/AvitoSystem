from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    stmt = select(User).where(User.username == username, User.is_active.is_(True))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        return None
    if not verify_password(user.password_hash, password):
        return None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        await session.flush()
    return user


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
    return (await session.execute(stmt)).scalar_one_or_none()
