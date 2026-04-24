from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.dependencies import db_connect, get_current_user
from health_log.limiter import limiter
from health_log.repositories.auth import AuthTokenRepository, AuthUser, PublicUser, UsersRepository
from health_log.security import (
    InvalidPasswordFormat,
    create_token,
    expires_in_days,
    expires_in_minutes,
    hash_password,
    token_hash,
    verify_password,
)
from health_log.settings import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    sex: Literal["male", "female"]
    email: str
    phone: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_non_blank_names(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Имя и фамилия не могут быть пустыми")
        return cleaned


class LoginRequest(BaseModel):
    login: str
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    sex: Literal["male", "female"]
    email: str
    phone: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: TokenResponse


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _normalize_phone(value: str) -> str:
    return value.strip()


def _to_user_response(user: PublicUser) -> UserResponse:
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


async def _issue_tokens(conn: AsyncConnection, user: AuthUser) -> TokenResponse:
    token_repo = AuthTokenRepository(conn)

    access_token = create_token()
    refresh_token = create_token()

    await token_repo.create_token(
        user_id=user.id,
        token_hash=token_hash(access_token),
        token_type="access",
        expires_at=expires_in_minutes(settings.auth_access_ttl_minutes),
    )
    await token_repo.create_token(
        user_id=user.id,
        token_hash=token_hash(refresh_token),
        token_type="refresh",
        expires_at=expires_in_days(settings.auth_refresh_ttl_days),
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthResponse)
@limiter.limit("10/hour")
async def register(request: Request, payload: RegisterRequest = Body(...), conn: AsyncConnection = Depends(db_connect)) -> AuthResponse:
    users_repo = UsersRepository(conn)

    email = _normalize_email(payload.email)
    phone = _normalize_phone(payload.phone)
    password_hash = hash_password(payload.password)
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
    sex = payload.sex

    email_user = await users_repo.get_auth_user_by_email(email, include_inactive=True)
    phone_user = await users_repo.get_auth_user_by_phone(phone, include_inactive=True)

    if (email_user and email_user.is_active) or (phone_user and phone_user.is_active):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Аккаунт уже активен. Используй вход в систему.",
        )

    restore_candidate_id: int | None = None
    if email_user is not None:
        restore_candidate_id = email_user.id
    if phone_user is not None:
        if restore_candidate_id is not None and restore_candidate_id != phone_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email и телефон принадлежат разным аккаунтам.",
            )
        restore_candidate_id = phone_user.id

    try:
        if restore_candidate_id is not None:
            public_user = await users_repo.restore_user(
                restore_candidate_id,
                first_name=first_name,
                last_name=last_name,
                sex=sex,
                email=email,
                phone=phone,
                password_hash=password_hash,
            )
        else:
            public_user = await users_repo.create_user(
                first_name=first_name,
                last_name=last_name,
                sex=sex,
                email=email,
                phone=phone,
                password_hash=password_hash,
            )
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email или телефон уже используется") from exc

    auth_user = AuthUser(
        id=public_user.id,
        first_name=public_user.first_name,
        last_name=public_user.last_name,
        sex=public_user.sex,
        email=public_user.email,
        phone=public_user.phone,
        password_hash=password_hash,
        is_active=public_user.is_active,
    )
    tokens = await _issue_tokens(conn, auth_user)
    return AuthResponse(user=_to_user_response(public_user), tokens=tokens)


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest = Body(...), conn: AsyncConnection = Depends(db_connect)) -> AuthResponse:
    users_repo = UsersRepository(conn)
    login_value = payload.login.strip().lower()

    user = await users_repo.get_auth_user_by_email_or_phone(login_value)
    if user is None:
        user = await users_repo.get_auth_user_by_email_or_phone(payload.login.strip())

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")

    try:
        is_valid = verify_password(payload.password, user.password_hash)
    except InvalidPasswordFormat as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль") from exc

    if not is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")

    public_user = await users_repo.get_public_user(user.id)
    if public_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    tokens = await _issue_tokens(conn, user)
    return AuthResponse(user=_to_user_response(public_user), tokens=tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, conn: AsyncConnection = Depends(db_connect)) -> TokenResponse:
    token_repo = AuthTokenRepository(conn)
    token_hash_value = token_hash(payload.refresh_token)

    user = await token_repo.get_user_by_active_token(token_hash=token_hash_value, token_type="refresh")
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token недействителен")

    await token_repo.revoke_token(token_hash=token_hash_value)
    return await _issue_tokens(conn, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
) -> None:
    token_repo = AuthTokenRepository(conn)
    await token_repo.revoke_all_user_tokens(user_id=current_user.id)
