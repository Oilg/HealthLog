import asyncio
from datetime import datetime, timedelta

import health_log.api.v1.users as users_api
from health_log.analysis.engine import HealthRiskAnalyzer
from health_log.analysis.models import TimeWindow
from health_log.analysis.rules import (
    assess_illness_onset_risk,
    assess_sleep_apnea_risk,
    assess_tachycardia_risk,
    build_sleep_apnea_event_rows,
)
from health_log.repositories.auth import AuthUser, PublicUser
from health_log.repositories.v1 import tables


def test_sleep_apnea_risk_uses_multi_signal_evidence():
    now = datetime(2026, 2, 26, 2, 0, 0)
    respiratory = []
    heart = []
    hrv = []

    for i in range(60):
        ts = now - timedelta(minutes=60 - i)
        rr = 13 if i % 10 else 7
        hr = 72 if i % 10 else 95
        hrv_v = 40 if i % 10 else 24
        respiratory.append((ts, rr))
        heart.append((ts, hr))
        hrv.append((ts, hrv_v))

    assessment = assess_sleep_apnea_risk(respiratory, heart, hrv, window=TimeWindow.NIGHT)

    assert assessment.score > 0.4
    assert assessment.confidence > 0.3
    assert assessment.severity in {"medium", "high"}


def test_tachycardia_risk_detects_frequent_high_hr():
    now = datetime(2026, 2, 26, 10, 0, 0)
    heart = [(now - timedelta(minutes=i), 105 if i < 20 else 78) for i in range(80)]

    assessment = assess_tachycardia_risk(heart, window=TimeWindow.WEEK)

    assert assessment.score > 0.2
    assert assessment.severity in {"low", "medium", "high"}


def test_sleep_apnea_event_builder_returns_insertable_rows():
    base = datetime(2026, 2, 26, 1, 0, 0)
    respiratory = [
        (base, 12),
        (base + timedelta(seconds=15), 7),
        (base + timedelta(seconds=45), 13),
    ]
    heart = [
        (base + timedelta(seconds=15), 95),
        (base + timedelta(seconds=45), 72),
    ]
    hrv = [
        (base + timedelta(seconds=15), 25),
        (base + timedelta(seconds=45), 40),
    ]

    events = build_sleep_apnea_event_rows(respiratory, heart, hrv)

    assert len(events) == 1
    event = events[0]
    assert event["start_time"] == base
    assert event["end_time"] == base + timedelta(seconds=15)
    assert event["detected_by"] == "rule_engine_v1"


def test_illness_onset_risk_detects_hr_up_and_hrv_down_trend():
    now = datetime(2026, 2, 26, 10, 0, 0)
    heart = []
    hrv = []
    resp = []
    sleep = []

    for day_idx in range(70):
        day = now - timedelta(days=69 - day_idx)
        sleep_start = day.replace(hour=23, minute=0, second=0, microsecond=0) - timedelta(days=1)
        sleep_end = day.replace(hour=7, minute=0, second=0, microsecond=0)
        sleep.append((sleep_start, sleep_end))
        for m in range(24):
            ts = day + timedelta(minutes=20 * m)
            if day_idx < 67:
                heart_val = 62 + (m % 3)
                hrv_val = 58 - (m % 2)
                resp_val = 13 + (m % 2) * 0.2
            else:
                heart_val = 72 + (m % 3)
                hrv_val = 40 - (m % 2)
                resp_val = 15 + (m % 2) * 0.2
            heart.append((ts, heart_val))
            hrv.append((ts, hrv_val))
            resp.append((ts, resp_val))

    assessment = assess_illness_onset_risk(
        heart,
        hrv,
        respiratory_rows=resp,
        sleep_rows=sleep,
        window=TimeWindow.WEEK,
    )

    assert assessment.score >= 0.5
    assert assessment.confidence > 0.5
    assert assessment.severity in {"medium", "high"}


def test_health_risk_analyzer_uses_extended_history_for_illness_onset():
    now = datetime(2026, 2, 26, 10, 0, 0)
    heart = []
    hrv = []
    resp = []
    sleep = []

    for day_idx in range(70):
        day = now - timedelta(days=69 - day_idx)
        sleep_start = day.replace(hour=23, minute=0, second=0, microsecond=0) - timedelta(days=1)
        sleep_end = day.replace(hour=7, minute=0, second=0, microsecond=0)
        sleep.append((sleep_start, sleep_end))
        for m in range(24):
            ts = day + timedelta(minutes=20 * m)
            if day_idx < 67:
                heart_val = 62 + (m % 3)
                hrv_val = 58 - (m % 2)
                resp_val = 13 + (m % 2) * 0.2
            else:
                heart_val = 72 + (m % 3)
                hrv_val = 40 - (m % 2)
                resp_val = 15 + (m % 2) * 0.2
            heart.append((ts, heart_val))
            hrv.append((ts, hrv_val))
            resp.append((ts, resp_val))

    analyzer = HealthRiskAnalyzer(connection=None, user_id=1)  # type: ignore[arg-type]
    analyzer._user_sex = "female"
    call_ranges: list[tuple[str, datetime, datetime]] = []

    async def fake_fetch_rows(table, start: datetime, end: datetime):
        call_ranges.append((table.name, start, end))
        if table.name == tables.heart_rate.name:
            return heart
        if table.name == tables.heart_rate_variability.name:
            return hrv
        if table.name == tables.respiratory_rate.name:
            return resp
        return []

    async def fake_sleep_segments(start: datetime, end: datetime):
        call_ranges.append((tables.sleep_analysis.name, start, end))
        return sleep

    analyzer._fetch_rows = fake_fetch_rows  # type: ignore[assignment]
    analyzer._fetch_sleep_segments = fake_sleep_segments  # type: ignore[assignment]

    result = asyncio.run(analyzer.analyze_window(TimeWindow.WEEK, now=now))
    illness = next(a for a in result["assessments"] if a.condition == "illness_onset_risk")

    min_required_start = now - timedelta(days=63)
    assert any(
        name == tables.heart_rate.name and start <= min_required_start for name, start, _ in call_ranges
    )
    assert illness.severity in {"medium", "high"}


def test_health_risk_analyzer_skips_menstrual_signal_for_male() -> None:
    now = datetime(2026, 2, 26, 10, 0, 0)
    analyzer = HealthRiskAnalyzer(connection=None, user_id=1)  # type: ignore[arg-type]
    analyzer._user_sex = "male"

    async def fake_fetch_rows(table, start: datetime, end: datetime):
        return []

    async def fake_sleep_segments(start: datetime, end: datetime):
        return []

    analyzer._fetch_rows = fake_fetch_rows  # type: ignore[assignment]
    analyzer._fetch_sleep_segments = fake_sleep_segments  # type: ignore[assignment]

    result = asyncio.run(analyzer.analyze_window(TimeWindow.WEEK, now=now))
    conditions = {assessment.condition for assessment in result["assessments"]}
    assert "menstrual_cycle_forecast" not in conditions


def test_health_risk_analyzer_adds_menstrual_signal_for_female() -> None:
    now = datetime(2026, 2, 26, 10, 0, 0)
    analyzer = HealthRiskAnalyzer(connection=None, user_id=1)  # type: ignore[arg-type]
    analyzer._user_sex = "female"

    period_starts = [
        datetime(2025, 10, 1, 8, 0, 0),
        datetime(2025, 10, 29, 8, 0, 0),
        datetime(2025, 11, 26, 8, 0, 0),
        datetime(2025, 12, 24, 8, 0, 0),
    ]
    menstrual_rows = [(start + timedelta(hours=12), 1) for start in period_starts]

    async def fake_fetch_rows(table, start: datetime, end: datetime):
        if table.name == tables.menstrual_flow.name:
            return menstrual_rows
        return []

    async def fake_sleep_segments(start: datetime, end: datetime):
        return []

    analyzer._fetch_rows = fake_fetch_rows  # type: ignore[assignment]
    analyzer._fetch_sleep_segments = fake_sleep_segments  # type: ignore[assignment]

    result = asyncio.run(analyzer.analyze_window(TimeWindow.MONTH, now=now))
    conditions = {assessment.condition for assessment in result["assessments"]}
    assert "menstrual_cycle_forecast" in conditions


def test_patch_me_sex_enables_menstrual_forecast(monkeypatch) -> None:
    state = {"sex": "male"}
    now = datetime(2026, 2, 26, 10, 0, 0)

    class FakeUsersRepository:
        def __init__(self, conn) -> None:
            self.conn = conn

        async def update_me(self, user_id: int, **kwargs):
            if kwargs.get("sex") is not None:
                state["sex"] = kwargs["sex"]
            return PublicUser(
                id=user_id,
                first_name="Jane",
                last_name="Doe",
                sex=state["sex"],
                email="jane@example.com",
                phone="+70000000001",
                is_active=True,
                created_at=datetime(2026, 1, 1, 10, 0, 0),
            )

    class FakeConnection:
        async def execute(self, query):
            class Result:
                def scalar_one_or_none(self):
                    return state["sex"]

            return Result()

    async def fake_sleep_segments(start: datetime, end: datetime):
        return []

    period_starts = [
        datetime(2025, 10, 1, 8, 0, 0),
        datetime(2025, 10, 29, 8, 0, 0),
        datetime(2025, 11, 26, 8, 0, 0),
        datetime(2025, 12, 24, 8, 0, 0),
    ]
    menstrual_rows = [(start + timedelta(hours=12), 1) for start in period_starts]

    async def fake_fetch_rows(table, start: datetime, end: datetime):
        if table.name == tables.menstrual_flow.name:
            return menstrual_rows
        return []

    fake_conn = FakeConnection()
    analyzer_before = HealthRiskAnalyzer(connection=fake_conn, user_id=1)  # type: ignore[arg-type]
    analyzer_before._fetch_rows = fake_fetch_rows  # type: ignore[assignment]
    analyzer_before._fetch_sleep_segments = fake_sleep_segments  # type: ignore[assignment]

    before_result = asyncio.run(analyzer_before.analyze_window(TimeWindow.MONTH, now=now))
    before_conditions = {assessment.condition for assessment in before_result["assessments"]}
    assert "menstrual_cycle_forecast" not in before_conditions

    monkeypatch.setattr(users_api, "UsersRepository", FakeUsersRepository)
    current_user = AuthUser(
        id=1,
        first_name="Jane",
        last_name="Doe",
        sex="male",
        email="jane@example.com",
        phone="+70000000001",
        password_hash="hash",
        is_active=True,
    )
    payload = users_api.UpdateMeRequest(sex="female")
    updated = asyncio.run(users_api.update_me(payload, current_user=current_user, conn=fake_conn))
    assert updated.sex == "female"

    analyzer_after = HealthRiskAnalyzer(connection=fake_conn, user_id=1)  # type: ignore[arg-type]
    analyzer_after._fetch_rows = fake_fetch_rows  # type: ignore[assignment]
    analyzer_after._fetch_sleep_segments = fake_sleep_segments  # type: ignore[assignment]
    after_result = asyncio.run(analyzer_after.analyze_window(TimeWindow.MONTH, now=now))
    after_conditions = {assessment.condition for assessment in after_result["assessments"]}
    assert "menstrual_cycle_forecast" in after_conditions
