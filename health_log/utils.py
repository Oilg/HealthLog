from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (tzinfo stripped).

    Replaces the deprecated ``datetime.utcnow()``.  All timestamps in this
    project are stored as naive UTC datetimes to stay consistent with the
    existing schema; callers that need an aware datetime should use
    ``datetime.now(timezone.utc)`` directly.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
