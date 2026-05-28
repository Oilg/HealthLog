"""Unit-тесты для latest_complete_day_end с поддержкой пользовательской таймзоны."""

from __future__ import annotations

from datetime import datetime

import pytest

from health_log.analysis.detectors.weight_activity.helpers import (
    latest_complete_day_end,
)


class TestLatestCompleteDayEndTimezone:
    def test_utc_default_returns_utc_midnight(self) -> None:
        # now=14:30 UTC → возвращает 00:00 UTC того же дня
        end = latest_complete_day_end(datetime(2026, 5, 27, 14, 30, 45))
        assert end == datetime(2026, 5, 27, 0, 0, 0)
        assert end.tzinfo is None

    def test_none_timezone_falls_back_to_utc(self) -> None:
        end = latest_complete_day_end(datetime(2026, 5, 27, 14, 30, 45), None)
        assert end == datetime(2026, 5, 27, 0, 0, 0)

    def test_empty_string_falls_back_to_utc(self) -> None:
        end = latest_complete_day_end(datetime(2026, 5, 27, 14, 30, 45), "")
        assert end == datetime(2026, 5, 27, 0, 0, 0)

    def test_utc_string_falls_back_to_utc(self) -> None:
        end = latest_complete_day_end(datetime(2026, 5, 27, 14, 30, 45), "UTC")
        assert end == datetime(2026, 5, 27, 0, 0, 0)
        end_lower = latest_complete_day_end(datetime(2026, 5, 27, 14, 30, 45), "utc")
        assert end_lower == datetime(2026, 5, 27, 0, 0, 0)

    def test_invalid_timezone_falls_back_to_utc(self) -> None:
        end = latest_complete_day_end(
            datetime(2026, 5, 27, 14, 30, 45), "Not/A_Real_Zone"
        )
        assert end == datetime(2026, 5, 27, 0, 0, 0)

    def test_moscow_timezone_shifts_three_hours_back(self) -> None:
        # Europe/Moscow = UTC+3 (без DST). now=10:00 UTC → 13:00 локально.
        # Локальная полночь сегодня = 00:00 MSK = 21:00 UTC вчера.
        now = datetime(2026, 5, 27, 10, 0, 0)
        end = latest_complete_day_end(now, "Europe/Moscow")
        assert end == datetime(2026, 5, 26, 21, 0, 0)
        assert end.tzinfo is None

    def test_moscow_before_local_midnight_uses_previous_day(self) -> None:
        # now=22:00 UTC = 01:00 MSK следующего дня. Локальная полночь = 21:00 UTC того же дня.
        now = datetime(2026, 5, 27, 22, 0, 0)
        end = latest_complete_day_end(now, "Europe/Moscow")
        assert end == datetime(2026, 5, 27, 21, 0, 0)

    def test_chukotka_far_east_shifts_twelve_hours_back(self) -> None:
        # Asia/Anadyr = UTC+12. now=05:00 UTC = 17:00 локально.
        # Локальная полночь = 12:00 UTC вчера.
        now = datetime(2026, 5, 27, 5, 0, 0)
        end = latest_complete_day_end(now, "Asia/Anadyr")
        assert end == datetime(2026, 5, 26, 12, 0, 0)

    def test_negative_offset_zone_returns_forward_utc(self) -> None:
        # America/New_York = UTC-4 (летнее время в мае 2026).
        # now=06:00 UTC = 02:00 EDT. Локальная полночь = 00:00 EDT = 04:00 UTC того же дня.
        now = datetime(2026, 5, 27, 6, 0, 0)
        end = latest_complete_day_end(now, "America/New_York")
        assert end == datetime(2026, 5, 27, 4, 0, 0)

    @pytest.mark.parametrize(
        "tz",
        [
            "Europe/Moscow",
            "Asia/Tokyo",
            "America/Los_Angeles",
            "Australia/Sydney",
            "Pacific/Auckland",
        ],
    )
    def test_real_zones_return_naive_utc(self, tz: str) -> None:
        end = latest_complete_day_end(datetime(2026, 5, 27, 12, 0, 0), tz)
        assert end.tzinfo is None
