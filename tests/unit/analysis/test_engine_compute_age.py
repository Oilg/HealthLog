"""Unit-тесты для HealthRiskAnalyzer._compute_age."""

from __future__ import annotations

from datetime import date, datetime

from health_log.analysis.engine import HealthRiskAnalyzer


def test_age_for_none_dob() -> None:
    assert HealthRiskAnalyzer._compute_age(None, datetime(2026, 5, 27, 12, 0)) is None


def test_age_full_year() -> None:
    # 1990-05-15 → возраст 36 на 2026-05-27 (день рождения в прошлом)
    assert HealthRiskAnalyzer._compute_age(date(1990, 5, 15), datetime(2026, 5, 27, 12, 0)) == 36


def test_age_before_birthday() -> None:
    # 1990-06-15 → на 2026-05-27 ещё не наступил день рождения → 35
    assert HealthRiskAnalyzer._compute_age(date(1990, 6, 15), datetime(2026, 5, 27, 12, 0)) == 35


def test_age_on_birthday() -> None:
    # 1990-05-27 → ровно 36 лет в день рождения
    assert HealthRiskAnalyzer._compute_age(date(1990, 5, 27), datetime(2026, 5, 27, 12, 0)) == 36


def test_age_one_day_before_birthday() -> None:
    # 1990-05-28 → 1 день до дня рождения → 35
    assert HealthRiskAnalyzer._compute_age(date(1990, 5, 28), datetime(2026, 5, 27, 12, 0)) == 35


def test_age_one_day_after_birthday() -> None:
    # 1990-05-26 → 1 день после дня рождения → 36
    assert HealthRiskAnalyzer._compute_age(date(1990, 5, 26), datetime(2026, 5, 27, 12, 0)) == 36


def test_age_leap_year_birthday() -> None:
    # 29 февраля високосного года → проверка что не ломаемся
    assert HealthRiskAnalyzer._compute_age(date(2000, 2, 29), datetime(2026, 3, 1, 12, 0)) == 26
    # 28 февраля 2026 — невисокосный, формально 25 лет ещё (29 февраля не наступило)
    assert HealthRiskAnalyzer._compute_age(date(2000, 2, 29), datetime(2026, 2, 28, 12, 0)) == 25


def test_age_never_negative() -> None:
    # На случай если DOB в будущем (теоретически — БД и API запрещают, но защита)
    future_dob = date(2099, 1, 1)
    assert HealthRiskAnalyzer._compute_age(future_dob, datetime(2026, 5, 27, 12, 0)) == 0


def test_age_with_timezone_ahead_of_utc() -> None:
    # UTC+12: 2026-05-28 00:30 local, тогда как UTC 2026-05-27 12:30
    # DOB = 1990-05-28: в UTC ещё не наступил → 35 лет, но локально уже 2026-05-28 → 36 лет
    dob = date(1990, 5, 28)
    now_utc = datetime(2026, 5, 27, 12, 30, tzinfo=__import__("datetime").timezone.utc)
    assert HealthRiskAnalyzer._compute_age(dob, now_utc, user_timezone=None) == 35
    assert HealthRiskAnalyzer._compute_age(dob, now_utc, user_timezone="Pacific/Auckland") == 36


def test_age_with_invalid_timezone_falls_back_to_utc() -> None:
    dob = date(1990, 5, 15)
    now_utc = datetime(2026, 5, 27, 12, 0, tzinfo=__import__("datetime").timezone.utc)
    # Невалидная таймзона — должна упасть на UTC без исключения
    assert HealthRiskAnalyzer._compute_age(dob, now_utc, user_timezone="Invalid/Zone") == 36
