from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.db import engine
from health_log.repositories.auth import AuthTokenRepository, AuthUser
from health_log.security import token_hash

security = HTTPBearer(auto_error=False)


async def db_connect() -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as conn:
        yield conn


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    conn: AsyncConnection = Depends(db_connect),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")

    token_repo = AuthTokenRepository(conn)
    user = await token_repo.get_user_by_active_token(
        token_hash=token_hash(credentials.credentials),
        token_type="access",
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный access token")
    return user
