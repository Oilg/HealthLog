import asyncio
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

import health_log.api.v1.auth as auth_api
import health_log.api.v1.users as users_api
from health_log.api.v1.auth import LoginRequest, RegisterRequest
from health_log.repositories.auth import AuthUser, PublicUser


def _mock_request() -> Request:
    """Minimal Starlette Request mock that satisfies slowapi's isinstance check."""
    scope = {"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""}
    mock = MagicMock(spec=Request)
    mock.scope = scope
    mock.headers = {}
    mock.url = MagicMock()
    mock.url.path = "/"
    mock.client = MagicMock()
    mock.client.host = "127.0.0.1"
    return mock


class FakeUsersRepository:
    def __init__(self, email_user=None, phone_user=None, public_user=None):
        self.email_user = email_user
        self.phone_user = phone_user
        self.public_user_obj = public_user
        self.restore_called = False
        self.create_called = False

    async def get_auth_user_by_email(self, email: str, *, include_inactive: bool = False):
        return self.email_user

    async def get_auth_user_by_phone(self, phone: str, *, include_inactive: bool = False):
        return self.phone_user

    async def restore_user(self, user_id: int, **kwargs):
        self.restore_called = True
        return self.public_user_obj

    async def create_user(self, **kwargs):
        self.create_called = True
        return self.public_user_obj

    async def get_auth_user_by_email_or_phone(self, login: str, *, include_inactive: bool = False):
        return self.email_user

    async def get_public_user(self, user_id: int):
        return self.public_user_obj


@pytest.mark.parametrize(
    "model,field",
    [
        (RegisterRequest, "first_name"),
        (RegisterRequest, "last_name"),
    ],
)
def test_register_rejects_blank_names(model, field):
    payload = {
        "first_name": "Ivan",
        "last_name": "Ivanov",
        "sex": "male",
        "email": "a@a.com",
        "phone": "+70000000000",
        "password": "StrongPass123",
    }
    payload[field] = "   "
    with pytest.raises(ValidationError):
        model(**payload)


@pytest.mark.parametrize("field", ["first_name", "last_name"])
def test_update_me_rejects_blank_names(field):
    payload = {field: "   "}
    with pytest.raises(ValidationError):
        users_api.UpdateMeRequest(**payload)


def _valid_register_payload(**overrides) -> dict:
    payload = {
        "first_name": "Ivan",
        "last_name": "Ivanov",
        "sex": "male",
        "email": "a@a.com",
        "phone": "+70000000000",
        "password": "StrongPass123",
    }
    payload.update(overrides)
    return payload


class TestRegisterDateOfBirthValidation:
    def test_no_dob_accepted(self):
        req = RegisterRequest(**_valid_register_payload())
        assert req.date_of_birth is None

    def test_valid_dob_accepted(self):
        req = RegisterRequest(**_valid_register_payload(date_of_birth="1990-01-15"))
        assert req.date_of_birth == date(1990, 1, 15)

    def test_dob_too_young_rejected(self):
        # 4 года — меньше минимума 5
        too_young = (date.today() - timedelta(days=4 * 365)).isoformat()
        with pytest.raises(ValidationError):
            RegisterRequest(**_valid_register_payload(date_of_birth=too_young))

    def test_dob_in_future_rejected(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        with pytest.raises(ValidationError):
            RegisterRequest(**_valid_register_payload(date_of_birth=future))

    def test_dob_too_old_rejected(self):
        # 131 год — больше максимума 130
        too_old = (date.today() - timedelta(days=131 * 366)).isoformat()
        with pytest.raises(ValidationError):
            RegisterRequest(**_valid_register_payload(date_of_birth=too_old))

    def test_dob_boundary_5_years_accepted(self):
        # 5 лет ровно (с запасом 1 день)
        five_years = (date.today() - timedelta(days=5 * 365 + 30)).isoformat()
        req = RegisterRequest(**_valid_register_payload(date_of_birth=five_years))
        assert req.date_of_birth is not None


class TestUpdateMeDateOfBirthValidation:
    def test_no_dob_field_accepted(self):
        req = users_api.UpdateMeRequest()
        assert req.date_of_birth is None
        assert "date_of_birth" not in req.model_fields_set

    def test_valid_dob_accepted(self):
        req = users_api.UpdateMeRequest(date_of_birth="1985-06-20")
        assert req.date_of_birth == date(1985, 6, 20)
        assert "date_of_birth" in req.model_fields_set

    def test_dob_too_young_rejected(self):
        too_young = (date.today() - timedelta(days=4 * 365)).isoformat()
        with pytest.raises(ValidationError):
            users_api.UpdateMeRequest(date_of_birth=too_young)


def test_register_restores_inactive_account(monkeypatch):
    inactive_user = AuthUser(
        id=10,
        first_name="Old",
        last_name="User",
        sex="female",
        email="old@example.com",
        phone="+71111111111",
        password_hash="hash",
        is_active=False,
    )
    restored_public = PublicUser(
        id=10,
        first_name="Ivan",
        last_name="Petrov",
        sex="female",
        email="new@example.com",
        phone="+72222222222",
        is_active=True,
        created_at=auth_api.datetime.utcnow(),
    )
    fake_repo = FakeUsersRepository(
        email_user=inactive_user, phone_user=inactive_user, public_user=restored_public
    )

    monkeypatch.setattr(auth_api, "UsersRepository", lambda conn: fake_repo)

    async def fake_issue_tokens(conn, user):
        return auth_api.TokenResponse(access_token="a", refresh_token="r")

    monkeypatch.setattr(auth_api, "_issue_tokens", fake_issue_tokens)

    payload = RegisterRequest(
        first_name="Ivan",
        last_name="Petrov",
        sex="female",
        email="new@example.com",
        phone="+72222222222",
        password="StrongPass123",
    )

    result = asyncio.run(auth_api.register(_mock_request(), payload, conn=object()))

    assert fake_repo.restore_called is True
    assert fake_repo.create_called is False
    assert result.user.id == 10


def test_login_returns_401_for_invalid_password_format(monkeypatch):
    auth_user = AuthUser(
        id=1,
        first_name="Ivan",
        last_name="Ivanov",
        sex="male",
        email="x@example.com",
        phone="+70000000000",
        password_hash="broken",
        is_active=True,
    )
    public_user = PublicUser(
        id=1,
        first_name="Ivan",
        last_name="Ivanov",
        sex="male",
        email="x@example.com",
        phone="+70000000000",
        is_active=True,
        created_at=auth_api.datetime.utcnow(),
    )
    fake_repo = FakeUsersRepository(email_user=auth_user, public_user=public_user)
    monkeypatch.setattr(auth_api, "UsersRepository", lambda conn: fake_repo)

    def broken_verify_password(password: str, encoded: str):
        raise auth_api.InvalidPasswordFormat("bad")

    monkeypatch.setattr(auth_api, "verify_password", broken_verify_password)

    payload = LoginRequest(login="x@example.com", password="StrongPass123")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_api.login(_mock_request(), payload, conn=object()))

    assert exc.value.status_code == 401
