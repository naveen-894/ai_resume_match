from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.util.db import get_session
from app.models import User
from app.auth import SECRET_KEY, ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def _user_from_token(token: str, session: AsyncSession) -> User:
    try:
        # Decode JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
            )

        # Get user from DB
        user = await session.get(User, int(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return user

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
):
    return await _user_from_token(token, session)


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional),
    session: AsyncSession = Depends(get_session),
):
    """Like get_current_user, but returns None for anonymous requests (no Authorization
    header) instead of raising 401. A present-but-invalid token still raises."""
    if token is None:
        return None
    return await _user_from_token(token, session)


async def get_guest_id(x_guest_id: str | None = Header(default=None)) -> str | None:
    """Opaque client-generated id identifying an anonymous guest, sent via X-Guest-Id."""
    return x_guest_id
