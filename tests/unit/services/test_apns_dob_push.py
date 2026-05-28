"""Unit-тесты для send_dob_request_push."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import health_log.services.apns as apns_module
from health_log.services.apns import send_dob_request_push


@pytest.fixture
def apns_configured(monkeypatch):
    """Patch settings so _apns_configured() returns True."""
    monkeypatch.setattr(apns_module.settings, "apns_key_id", "KEYID")
    monkeypatch.setattr(apns_module.settings, "apns_team_id", "TEAMID")
    monkeypatch.setattr(apns_module.settings, "apns_auth_key_path", "/tmp/fake.p8")
    monkeypatch.setattr(apns_module.settings, "apns_bundle_id", "com.example.app")
    monkeypatch.setattr(apns_module.settings, "apns_use_sandbox", True)


class TestSendDobRequestPushUnconfigured:
    def test_returns_false_when_apns_not_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(apns_module.settings, "apns_key_id", "")
        monkeypatch.setattr(apns_module.settings, "apns_team_id", "")
        monkeypatch.setattr(apns_module.settings, "apns_auth_key_path", "")
        monkeypatch.setattr(apns_module.settings, "apns_bundle_id", "")

        result = asyncio.run(send_dob_request_push("a" * 64))
        assert result is False


class TestSendDobRequestPushPayload:
    def test_sends_alert_push_with_open_profile_action(
        self, apns_configured, monkeypatch
    ) -> None:
        captured_request = {}

        async def fake_make_client():
            client = MagicMock()
            result = MagicMock()
            result.is_successful = True
            result.description = "ok"
            client.send_notification = AsyncMock(return_value=result)
            return client

        async def fake_send_notification(self_, request):
            captured_request["request"] = request
            r = MagicMock()
            r.is_successful = True
            return r

        # Patch _make_client to return a controllable client.
        client = MagicMock()
        result = MagicMock()
        result.is_successful = True
        result.description = "ok"

        async def send_capture(req):
            captured_request["request"] = req
            return result

        client.send_notification = send_capture

        async def make_client_replacement():
            return client

        monkeypatch.setattr(apns_module, "_make_client", make_client_replacement)

        ok = asyncio.run(send_dob_request_push("b" * 64))

        assert ok is True
        req = captured_request["request"]
        assert req.device_token == "b" * 64
        # Проверяем payload structure
        msg = req.message
        assert msg["aps"]["alert"]["title"] == "Уточните ваш возраст"
        assert "возраст" in msg["aps"]["alert"]["body"]
        assert msg["type"] == "dob_request"
        assert msg["action"] == "open_profile"

    def test_returns_false_when_apns_rejects(self, apns_configured, monkeypatch) -> None:
        client = MagicMock()
        rejected = MagicMock()
        rejected.is_successful = False
        rejected.description = "BadDeviceToken"

        async def send_reject(req):
            return rejected

        client.send_notification = send_reject

        async def make_client_replacement():
            return client

        monkeypatch.setattr(apns_module, "_make_client", make_client_replacement)

        ok = asyncio.run(send_dob_request_push("c" * 64))
        assert ok is False

    def test_returns_false_on_exception(self, apns_configured, monkeypatch) -> None:
        async def make_client_replacement():
            raise RuntimeError("network down")

        monkeypatch.setattr(apns_module, "_make_client", make_client_replacement)

        ok = asyncio.run(send_dob_request_push("d" * 64))
        assert ok is False
