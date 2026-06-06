from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.dependencies import db_connect, get_current_user
from health_log.repositories.auth import AuthUser, UsersRepository

router = APIRouter(prefix="/api/v1/health", tags=["health"])


class HealthSyncStatusResponse(BaseModel):
    has_data: bool
    last_sync_at: str | None


@router.get("/sync/status", response_model=HealthSyncStatusResponse)
async def get_health_sync_status(
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
) -> HealthSyncStatusResponse:
    """Check whether the authenticated user has any health data on the server.

    Returns:
    - **has_data**: ``true`` if the user has synced at least once (health records exist).
    - **last_sync_at**: ISO 8601 UTC timestamp of the most recent sync, or ``null`` if never synced.
    """
    users_repo = UsersRepository(conn)
    data = await users_repo.get_health_sync_status(current_user.id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    last_sync_at = data["last_sync_at"]
    return HealthSyncStatusResponse(
        has_data=data["has_data"],
        last_sync_at=last_sync_at.isoformat() + "Z" if last_sync_at else None,
    )
