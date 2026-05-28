from __future__ import annotations

from datetime import date, datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.api.v1.auth import _validate_date_of_birth, _validate_timezone
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
    date_of_birth: date | None = None
    timezone: str | None = None


class UpdateMeRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    sex: Literal["male", "female"] | None = None
    email: str | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    timezone: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_non_blank_names(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Имя и фамилия не могут быть пустыми")
        return cleaned

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, value: date | None) -> date | None:
        return _validate_date_of_birth(value)

    @field_validator("timezone")
    @classmethod
    def validate_tz(cls, value: str | None) -> str | None:
        return _validate_timezone(value)


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
        date_of_birth=user.date_of_birth,
        timezone=user.timezone,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UpdateMeRequest,
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
) -> UserResponse:
    users_repo = UsersRepository(conn)

    # Поле date_of_birth подразумевает "установить" семантику: передавать только если есть значение.
    # Пустое значение (None) явно не обнуляет — для очистки нужно отдельное действие в будущем.
    update_dob = "date_of_birth" in payload.model_fields_set and payload.date_of_birth is not None
    # Аналогично — timezone обновляется только если ключ был явно передан и не пуст.
    update_tz = "timezone" in payload.model_fields_set and payload.timezone is not None

    try:
        user = await users_repo.update_me(
            current_user.id,
            first_name=payload.first_name.strip() if payload.first_name else None,
            last_name=payload.last_name.strip() if payload.last_name else None,
            sex=payload.sex,
            email=_normalize_email(payload.email),
            phone=_normalize_phone(payload.phone),
            date_of_birth=payload.date_of_birth if update_dob else None,
            update_date_of_birth=update_dob,
            timezone=payload.timezone if update_tz else None,
            update_timezone=update_tz,
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email или телефон уже используется"
        ) from exc

    return UserResponse(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        sex=cast(Literal["male", "female"], user.sex),
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        created_at=user.created_at,
        date_of_birth=user.date_of_birth,
        timezone=user.timezone,
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_me(
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
) -> None:
    users_repo = UsersRepository(conn)
    token_repo = AuthTokenRepository(conn)

    await users_repo.deactivate(current_user.id)
    await token_repo.revoke_all_user_tokens(user_id=current_user.id)
