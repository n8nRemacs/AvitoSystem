from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_sessionmaker
from app.db.models import User
from app.services.auth import get_user_by_id


async def db_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def current_user_optional(
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await get_user_by_id(session, user_id)


async def require_user(
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    user = await get_user_by_id(session, user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return user


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
