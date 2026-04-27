from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.dependencies import db_connect, get_current_user
from health_log.repositories.auth import AuthTokenRepository, AuthUser, UsersRepository

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    sex: Literal["male", "female"]
    email: str
    phone: str
    is_active: bool
    created_at: datetime


class UpdateMeRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    sex: Literal["male", "female"] | None = None
    email: str | None = None
    phone: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_non_blank_names(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Имя и фамилия не могут быть пустыми")
        return cleaned


def _normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().lower()


def _normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip()


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
) -> UserResponse:
    users_repo = UsersRepository(conn)
    user = await users_repo.get_public_user(current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return UserResponse(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        sex=cast(Literal["male", "female"], user.sex),
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UpdateMeRequest,
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
) -> UserResponse:
    users_repo = UsersRepository(conn)

    try:
        user = await users_repo.update_me(
            current_user.id,
            first_name=payload.first_name.strip() if payload.first_name else None,
            last_name=payload.last_name.strip() if payload.last_name else None,
            sex=payload.sex,
            email=_normalize_email(payload.email),
            phone=_normalize_phone(payload.phone),
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email или телефон уже используется") from exc

    return UserResponse(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        sex=cast(Literal["male", "female"], user.sex),
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        created_at=user.created_at,
    )


class DeviceTokenRequest(BaseModel):
    device_token: str


@router.put("/me/device-token", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def update_device_token(
    payload: DeviceTokenRequest,
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
) -> None:
    users_repo = UsersRepository(conn)
    try:
        await users_repo.update_apns_token(current_user.id, payload.device_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_me(
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
) -> None:
    users_repo = UsersRepository(conn)
    token_repo = AuthTokenRepository(conn)

    await users_repo.deactivate(current_user.id)
    await token_repo.revoke_all_user_tokens(user_id=current_user.id)
