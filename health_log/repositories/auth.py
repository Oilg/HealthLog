from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.repositories.v1 import tables


@dataclass(slots=True)
class AuthUser:
    id: int
    first_name: str
    last_name: str
    email: str
    phone: str
    password_hash: str
    is_active: bool


@dataclass(slots=True)
class PublicUser:
    id: int
    first_name: str
    last_name: str
    email: str
    phone: str
    is_active: bool
    created_at: datetime


class UsersRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def create_user(
        self,
        *,
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        password_hash: str,
    ) -> PublicUser:
        stmt = (
            pg_insert(tables.users)
            .values(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                password_hash=password_hash,
                is_active=True,
            )
            .returning(
                tables.users.c.id,
                tables.users.c.first_name,
                tables.users.c.last_name,
                tables.users.c.email,
                tables.users.c.phone,
                tables.users.c.is_active,
                tables.users.c.created_at,
            )
        )
        row = (await self._connection.execute(stmt)).one()
        return PublicUser(
            id=row.id,
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.email,
            phone=row.phone,
            is_active=row.is_active,
            created_at=row.created_at,
        )

    async def _select_auth_user(self, where_clause, *, include_inactive: bool = False) -> AuthUser | None:
        row = (
            await self._connection.execute(
                select(
                    tables.users.c.id,
                    tables.users.c.first_name,
                    tables.users.c.last_name,
                    tables.users.c.email,
                    tables.users.c.phone,
                    tables.users.c.password_hash,
                    tables.users.c.is_active,
                ).where(where_clause)
            )
        ).one_or_none()
        if row is None:
            return None
        if (not include_inactive) and (not row.is_active):
            return None
        return AuthUser(
            id=row.id,
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.email,
            phone=row.phone,
            password_hash=row.password_hash,
            is_active=row.is_active,
        )

    async def get_auth_user_by_email_or_phone(self, login: str, *, include_inactive: bool = False) -> AuthUser | None:
        return await self._select_auth_user(
            (tables.users.c.email == login) | (tables.users.c.phone == login),
            include_inactive=include_inactive,
        )

    async def get_auth_user_by_email(self, email: str, *, include_inactive: bool = False) -> AuthUser | None:
        return await self._select_auth_user(
            tables.users.c.email == email,
            include_inactive=include_inactive,
        )

    async def get_auth_user_by_phone(self, phone: str, *, include_inactive: bool = False) -> AuthUser | None:
        return await self._select_auth_user(
            tables.users.c.phone == phone,
            include_inactive=include_inactive,
        )

    async def get_public_user(self, user_id: int) -> PublicUser | None:
        row = (
            await self._connection.execute(
                select(
                    tables.users.c.id,
                    tables.users.c.first_name,
                    tables.users.c.last_name,
                    tables.users.c.email,
                    tables.users.c.phone,
                    tables.users.c.is_active,
                    tables.users.c.created_at,
                ).where(tables.users.c.id == user_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return PublicUser(
            id=row.id,
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.email,
            phone=row.phone,
            is_active=row.is_active,
            created_at=row.created_at,
        )

    async def update_me(
        self,
        user_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> PublicUser:
        values: dict[str, object] = {}
        if first_name is not None:
            values["first_name"] = first_name
        if last_name is not None:
            values["last_name"] = last_name
        if email is not None:
            values["email"] = email
        if phone is not None:
            values["phone"] = phone

        if values:
            await self._connection.execute(
                update(tables.users)
                .where(tables.users.c.id == user_id)
                .values(**values, updated_at=datetime.utcnow())
            )

        user = await self.get_public_user(user_id)
        if user is None:
            raise ValueError("User not found")
        return user

    async def deactivate(self, user_id: int) -> None:
        await self._connection.execute(
            update(tables.users)
            .where(tables.users.c.id == user_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )

    async def restore_user(
        self,
        user_id: int,
        *,
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        password_hash: str,
    ) -> PublicUser:
        await self._connection.execute(
            update(tables.users)
            .where(tables.users.c.id == user_id)
            .values(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                password_hash=password_hash,
                is_active=True,
                updated_at=datetime.utcnow(),
            )
        )
        user = await self.get_public_user(user_id)
        if user is None:
            raise ValueError("User not found")
        return user

    async def exists_by_email(self, email: str) -> bool:
        row = (
            await self._connection.execute(select(tables.users.c.id).where(tables.users.c.email == email))
        ).one_or_none()
        return row is not None

    async def exists_by_phone(self, phone: str) -> bool:
        row = (
            await self._connection.execute(select(tables.users.c.id).where(tables.users.c.phone == phone))
        ).one_or_none()
        return row is not None

    async def list_active_user_ids(self) -> list[int]:
        rows = (
            await self._connection.execute(
                select(tables.users.c.id).where(tables.users.c.is_active.is_(True)).order_by(tables.users.c.id)
            )
        ).all()
        return [row.id for row in rows]


class AuthTokenRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def create_token(
        self,
        *,
        user_id: int,
        token_hash: str,
        token_type: str,
        expires_at: datetime,
    ) -> None:
        await self._connection.execute(
            pg_insert(tables.auth_tokens).values(
                user_id=user_id,
                token_hash=token_hash,
                token_type=token_type,
                expires_at=expires_at,
            )
        )

    async def revoke_token(self, *, token_hash: str) -> None:
        await self._connection.execute(
            update(tables.auth_tokens)
            .where(tables.auth_tokens.c.token_hash == token_hash)
            .values(revoked_at=datetime.utcnow())
        )

    async def revoke_all_user_tokens(self, *, user_id: int) -> None:
        await self._connection.execute(
            update(tables.auth_tokens)
            .where(
                and_(
                    tables.auth_tokens.c.user_id == user_id,
                    tables.auth_tokens.c.revoked_at.is_(None),
                )
            )
            .values(revoked_at=datetime.utcnow())
        )

    async def get_user_by_active_token(self, *, token_hash: str, token_type: str) -> AuthUser | None:
        now = datetime.utcnow()
        row = (
            await self._connection.execute(
                select(
                    tables.users.c.id,
                    tables.users.c.first_name,
                    tables.users.c.last_name,
                    tables.users.c.email,
                    tables.users.c.phone,
                    tables.users.c.password_hash,
                    tables.users.c.is_active,
                )
                .select_from(
                    tables.auth_tokens.join(tables.users, tables.auth_tokens.c.user_id == tables.users.c.id)
                )
                .where(
                    and_(
                        tables.auth_tokens.c.token_hash == token_hash,
                        tables.auth_tokens.c.token_type == token_type,
                        tables.auth_tokens.c.revoked_at.is_(None),
                        tables.auth_tokens.c.expires_at > now,
                        tables.users.c.is_active.is_(True),
                    )
                )
            )
        ).one_or_none()
        if row is None:
            return None

        return AuthUser(
            id=row.id,
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.email,
            phone=row.phone,
            password_hash=row.password_hash,
            is_active=row.is_active,
        )
