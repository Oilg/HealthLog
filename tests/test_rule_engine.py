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
    base = datetime(2026, 2, 26, 22, 0, 0)
    sleep_end = base + timedelta(hours=6)
    segments = [(base, sleep_end)]
    respiratory = []
    heart = []
    hrv = []
    # 30 normal points at 10-min intervals (~5 h of coverage, well above 20-point minimum)
    for i in range(30):
        ts = base + timedelta(minutes=10 * i)
        respiratory.append((ts, 13.0))
        heart.append((ts, 68.0))
        hrv.append((ts, 42.0))
    # 3 confirmed anomalous points within a 6-min window
    anomaly_start = base + timedelta(hours=3)
    for k in range(3):
        ts = anomaly_start + timedelta(minutes=3 * k)
        respiratory.append((ts, 7.0))   # RR < 10
        heart.append((ts, 82.0))        # 82 >= 68 + 12 = 80 → supported_by_hr
        hrv.append((ts, 32.0))          # 32 <= 42 * 0.8 = 33.6 → supported_by_hrv

    assessment = assess_sleep_apnea_risk(
        respiratory, heart, hrv, sleep_segments=segments, window=TimeWindow.NIGHT
    )

    assert assessment.score > 0
    assert assessment.confidence > 0.3
    assert assessment.severity in {"low", "medium", "high"}


def test_tachycardia_ignores_daytime_exercise_hr_when_sleep_context_exists():
    sleep_start = datetime(2026, 2, 26, 22, 0, 0)
    sleep_end = datetime(2026, 2, 27, 6, 0, 0)
    day = datetime(2026, 2, 27, 14, 0, 0)
    heart = []
    t = sleep_start
    while t < sleep_end:
        heart.append((t, 62.0))
        t += timedelta(minutes=5)
    for k in range(20):
        heart.append((day + timedelta(minutes=k * 3), 125.0))

    assessment = assess_tachycardia_risk(
        heart, sleep_segments=[(sleep_start, sleep_end)], window=TimeWindow.WEEK
    )
    assert assessment.score == 0
    assert assessment.severity == "none"


def test_tachycardia_single_high_point_in_sleep_not_an_episode():
    sleep_start = datetime(2026, 2, 26, 23, 0, 0)
    sleep_end = datetime(2026, 2, 27, 7, 0, 0)
    heart = []
    t = sleep_start
    while t < sleep_end:
        if t == sleep_start + timedelta(hours=2):
            heart.append((t, 102.0))
        else:
            heart.append((t, 58.0))
        t += timedelta(minutes=4)

    assessment = assess_tachycardia_risk(
        heart, sleep_segments=[(sleep_start, sleep_end)], window=TimeWindow.WEEK
    )
    assert assessment.score == 0


def test_tachycardia_valid_night_episode_seven_minutes():
    sleep_start = datetime(2026, 2, 26, 23, 0, 0)
    sleep_end = datetime(2026, 2, 27, 7, 0, 0)
    heart = []
    t = sleep_start
    while t < sleep_start + timedelta(hours=1):
        heart.append((t, 58.0))
        t += timedelta(minutes=5)
    ep_t0 = sleep_start + timedelta(hours=1, minutes=5)
    for j in range(5):
        heart.append((ep_t0 + timedelta(minutes=2 * j), 108.0))
    t2 = ep_t0 + timedelta(minutes=25)
    while t2 < sleep_end:
        heart.append((t2, 58.0))
        t2 += timedelta(minutes=5)

    assessment = assess_tachycardia_risk(
        heart, sleep_segments=[(sleep_start, sleep_end)], window=TimeWindow.WEEK
    )
    assert assessment.score > 0
    assert "эпизод" in assessment.summary.lower()


def test_tachycardia_fallback_confidence_lower_without_sleep():
    # Normal points stop before ep_t0 and resume 25 min after the episode, so
    # the 5-point spike cluster is fully isolated (gaps >120 s on both sides)
    # and passes the 70% check.  With sleep segments the episode is detected
    # and confidence is high; without sleep the sparse 5-min normal points never
    # form a rest-like cluster, so the fallback path returns confidence=0.
    sleep_start = datetime(2026, 2, 26, 23, 0, 0)
    sleep_end = datetime(2026, 2, 27, 7, 0, 0)
    ep_t0 = sleep_start + timedelta(hours=1, minutes=5)

    heart = []
    t = sleep_start
    while t < sleep_start + timedelta(hours=1):
        heart.append((t, 58.0))
        t += timedelta(minutes=5)
    for j in range(5):
        heart.append((ep_t0 + timedelta(minutes=2 * j), 108.0))
    t2 = ep_t0 + timedelta(minutes=25)
    while t2 < sleep_end:
        heart.append((t2, 58.0))
        t2 += timedelta(minutes=5)
    heart.sort(key=lambda x: x[0])

    a_sleep = assess_tachycardia_risk(
        heart, sleep_segments=[(sleep_start, sleep_end)], window=TimeWindow.WEEK
    )
    a_fb = assess_tachycardia_risk(heart, sleep_segments=[], window=TimeWindow.WEEK)

    assert a_sleep.score > 0
    assert a_sleep.confidence > a_fb.confidence


def test_sleep_apnea_event_builder_returns_insertable_rows():
    base = datetime(2026, 2, 26, 22, 0, 0)
    segments = [(base, base + timedelta(hours=6))]
    respiratory = []
    heart = []
    hrv = []
    # 30 normal points at 10-min intervals
    for i in range(30):
        ts = base + timedelta(minutes=10 * i)
        respiratory.append((ts, 13.0))
        heart.append((ts, 68.0))
        hrv.append((ts, 42.0))
    # 3 confirmed anomalous points (same parameters as apnea risk test)
    anomaly_start = base + timedelta(hours=3)
    for k in range(3):
        ts = anomaly_start + timedelta(minutes=3 * k)
        respiratory.append((ts, 7.0))
        heart.append((ts, 82.0))
        hrv.append((ts, 32.0))

    events = build_sleep_apnea_event_rows(
        respiratory, heart, hrv, sleep_segments=segments
    )

    assert len(events) >= 1
    event = events[0]
    assert event["detected_by"] == "rule_engine_v1"
    assert event["point_count"] >= 2
    assert event["support_level"] in {"strong", "medium"}
    assert event["confidence"] is not None
    assert event["baseline_rr"] is not None


def test_sleep_apnea_gap_six_minutes_splits_episodes():
    base = datetime(2026, 2, 26, 22, 0, 0)
    seg = [(base, base + timedelta(hours=6))]
    respiratory = []
    heart = []
    hrv = []
    for i in range(20):
        ts = base + timedelta(minutes=15 * i)
        respiratory.append((ts, 12.0))
        heart.append((ts, 68.0))
        hrv.append((ts, 42.0))
    t_a = base + timedelta(minutes=200)
    t_b = t_a + timedelta(minutes=6)
    for ts in (t_a, t_b):
        respiratory.append((ts, 7.0))
        heart.append((ts, 88.0))
        hrv.append((ts, 28.0))

    events = build_sleep_apnea_event_rows(respiratory, heart, hrv, sleep_segments=seg)
    assert len(events) == 0


def test_sleep_apnea_two_points_four_minutes_merge():
    base = datetime(2026, 2, 26, 22, 0, 0)
    seg = [(base, base + timedelta(hours=6))]
    respiratory = []
    heart = []
    hrv = []
    for i in range(20):
        ts = base + timedelta(minutes=15 * i + 1)
        respiratory.append((ts, 12.0))
        heart.append((ts, 68.0))
        hrv.append((ts, 42.0))
    t0 = base + timedelta(hours=3)
    t1 = t0 + timedelta(minutes=4)
    for ts in (t0, t1):
        respiratory.append((ts, 7.0))
        heart.append((ts, 88.0))
        hrv.append((ts, 28.0))

    events = build_sleep_apnea_event_rows(respiratory, heart, hrv, sleep_segments=seg)
    assert len(events) >= 1


def test_sleep_apnea_insufficient_without_sleep():
    base = datetime(2026, 2, 26, 22, 0, 0)
    respiratory = [(base + timedelta(minutes=i), 12.0) for i in range(25)]
    heart = [(base + timedelta(minutes=i), 68.0) for i in range(25)]
    hrv = [(base + timedelta(minutes=i), 40.0) for i in range(25)]
    a = assess_sleep_apnea_risk(respiratory, heart, hrv, sleep_segments=[], window=TimeWindow.NIGHT)
    assert a.score == 0
    assert a.severity == "unknown"


def test_sleep_apnea_insufficient_short_night():
    base = datetime(2026, 2, 26, 22, 0, 0)
    seg = [(base, base + timedelta(hours=2))]
    respiratory = [(base + timedelta(minutes=i * 5), 12.0) for i in range(25)]
    heart = [(base + timedelta(minutes=i * 5), 68.0) for i in range(25)]
    hrv = [(base + timedelta(minutes=i * 5), 40.0) for i in range(25)]
    a = assess_sleep_apnea_risk(respiratory, heart, hrv, sleep_segments=seg, window=TimeWindow.NIGHT)
    assert a.severity == "unknown"


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
    menstrual_keys = {
        "menstrual_cycle_start_forecast",
        "menstrual_cycle_delay_risk",
        "ovulation_window_forecast",
    }
    assert menstrual_keys.isdisjoint(conditions)


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
    assert "menstrual_cycle_start_forecast" in conditions
    assert "menstrual_cycle_delay_risk" in conditions
    assert "ovulation_window_forecast" in conditions


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
    assert "menstrual_cycle_start_forecast" not in before_conditions

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
    assert "menstrual_cycle_start_forecast" in after_conditions
