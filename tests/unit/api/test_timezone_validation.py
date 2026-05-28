"""Unit-тесты для валидации поля timezone в API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

import health_log.api.v1.users as users_api
from health_log.api.v1.auth import RegisterRequest, _validate_timezone


def _valid_register_payload(**overrides) -> dict:
    payload = {
        "first_name": "Ivan",
        "last_name": "Ivanov",
        "sex": "male",
        "email": "tz@example.com",
        "phone": "+70000000099",
        "password": "StrongPass123",
    }
    payload.update(overrides)
    return payload


class TestValidateTimezone:
    def test_none_passes_through(self) -> None:
        assert _validate_timezone(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _validate_timezone("") is None
        assert _validate_timezone("   ") is None

    def test_utc_kept_as_is(self) -> None:
        assert _validate_timezone("UTC") == "UTC"
        assert _validate_timezone("utc") == "UTC"

    @pytest.mark.parametrize(
        "tz",
        ["Europe/Moscow", "Asia/Tokyo", "America/New_York", "Pacific/Auckland"],
    )
    def test_valid_iana_zones_accepted(self, tz: str) -> None:
        assert _validate_timezone(tz) == tz

    @pytest.mark.parametrize("bad", ["Not/A_Zone", "Mars/Phobos", "MSK+3", "random"])
    def test_invalid_zones_raise(self, bad: str) -> None:
        with pytest.raises(ValueError):
            _validate_timezone(bad)


class TestRegisterRequestTimezone:
    def test_no_timezone_field_accepted(self) -> None:
        req = RegisterRequest(**_valid_register_payload())
        assert req.timezone is None
        assert "timezone" not in req.model_fields_set

    def test_valid_timezone_stored(self) -> None:
        req = RegisterRequest(**_valid_register_payload(timezone="Europe/Moscow"))
        assert req.timezone == "Europe/Moscow"

    def test_invalid_timezone_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(**_valid_register_payload(timezone="Foo/Bar"))


class TestUpdateMeRequestTimezone:
    def test_no_field_default(self) -> None:
        req = users_api.UpdateMeRequest()
        assert req.timezone is None
        assert "timezone" not in req.model_fields_set

    def test_valid_timezone_accepted(self) -> None:
        req = users_api.UpdateMeRequest(timezone="Asia/Tokyo")
        assert req.timezone == "Asia/Tokyo"
        assert "timezone" in req.model_fields_set

    def test_invalid_timezone_rejected(self) -> None:
        with pytest.raises(ValidationError):
            users_api.UpdateMeRequest(timezone="Garbage/Zone")
