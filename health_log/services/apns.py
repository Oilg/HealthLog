"""APNs (Apple Push Notification service) integration via aioapns."""
from __future__ import annotations

import logging

from health_log.settings import settings

logger = logging.getLogger(__name__)


async def _make_client():
    """Create and return a configured APNs client."""
    from aioapns import APNs, PushType  # noqa: F401
    return APNs(
        key=settings.apns_auth_key_path,
        key_id=settings.apns_key_id,
        team_id=settings.apns_team_id,
        topic=settings.apns_bundle_id,
        use_sandbox=settings.apns_use_sandbox,
    )


def _apns_configured() -> bool:
    return all([
        settings.apns_key_id,
        settings.apns_team_id,
        settings.apns_auth_key_path,
        settings.apns_bundle_id,
    ])


async def send_silent_push(device_token: str) -> bool:
    """Send a silent (background) push notification to trigger a sync.

    Returns True if delivery was accepted, False otherwise.
    Requires APNS_KEY_ID, APNS_TEAM_ID, APNS_AUTH_KEY_PATH and APNS_BUNDLE_ID
    to be set in settings.
    """
    if not _apns_configured():
        logger.warning("APNs не настроен — пропуск отправки push-уведомления")
        return False

    try:
        from aioapns import NotificationRequest, PushType

        client = await _make_client()

        request = NotificationRequest(
            device_token=device_token,
            message={"aps": {"content-available": 1}},
            push_type=PushType.BACKGROUND,
            priority=5,  # low priority for silent push
        )

        result = await client.send_notification(request)
        if result.is_successful:
            logger.info("Silent push отправлен: device=%s", device_token[:8] + "…")
            return True

        logger.warning("APNs отклонил push: %s — %s", device_token[:8] + "…", result.description)
        return False

    except ImportError:
        logger.error("aioapns не установлен. Добавьте его в зависимости.")
        return False
    except Exception as exc:
        logger.exception("Ошибка отправки APNs push: %s", exc)
        return False


async def send_analysis_ready_push(device_token: str) -> bool:
    """Send a visible push notification to tell the user new analysis results are ready."""
    if not _apns_configured():
        return False

    try:
        from aioapns import NotificationRequest, PushType

        client = await _make_client()

        request = NotificationRequest(
            device_token=device_token,
            message={
                "aps": {
                    "alert": {
                        "title": "HealthLog",
                        "body": "Готов новый анализ данных о здоровье",
                    },
                    "sound": "default",
                    "badge": 1,
                    "content-available": 1,
                },
                "type": "analysis_ready",
            },
            push_type=PushType.ALERT,
            priority=10,
        )

        result = await client.send_notification(request)
        if result.is_successful:
            logger.info("Analysis-ready push отправлен: device=%s", device_token[:8] + "…")
            return True

        logger.warning("APNs отклонил analysis push: %s — %s", device_token[:8] + "…", result.description)
        return False

    except ImportError:
        logger.error("aioapns не установлен.")
        return False
    except Exception as exc:
        logger.exception("Ошибка отправки analysis push: %s", exc)
        return False
