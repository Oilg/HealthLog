"""Unit tests for health_log/api/v1/sync.py — models and helpers."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from health_log.api.v1.sync import (
    DaySchedule,
    InstantaneousBpm,
    ScheduleRequest,
    SyncRecord,
    SyncRequest,
    _record_to_parsed,
)
from health_log.services.apple_health_parser import parse_datetime

# ─── SyncRecord.metadata validator ──────────────────────────────────────────


def _minimal_record(**kwargs) -> dict:
    base = {
        "type": "HKQuantityTypeIdentifierHeartRate",
        "sourceName": "Apple Watch",
        "creationDate": "2024-01-01T12:00:00+03:00",
        "startDate": "2024-01-01T12:00:00+03:00",
        "endDate": "2024-01-01T12:00:01+03:00",
    }
    base.update(kwargs)
    return base


def test_sync_record_valid_minimal():
    r = SyncRecord(**_minimal_record())
    assert r.type == "HKQuantityTypeIdentifierHeartRate"
    assert r.metadata == {}
    assert r.instantaneous_bpm is None


def test_sync_record_valid_with_metadata():
    r = SyncRecord(**_minimal_record(metadata={"HKMetadataKeyTimeZone": "Europe/Moscow"}))
    assert r.metadata["HKMetadataKeyTimeZone"] == "Europe/Moscow"


def test_sync_record_metadata_too_many_keys():
    big = {f"key_{i}": "v" for i in range(51)}
    with pytest.raises(ValidationError, match="50"):
        SyncRecord(**_minimal_record(metadata=big))


def test_sync_record_metadata_exactly_50_keys_ok():
    ok = {f"key_{i}": "v" for i in range(50)}
    r = SyncRecord(**_minimal_record(metadata=ok))
    assert len(r.metadata) == 50


def test_sync_record_metadata_key_too_long():
    long_key = "k" * 257
    with pytest.raises(ValidationError, match="ключ"):
        SyncRecord(**_minimal_record(metadata={long_key: "value"}))


def test_sync_record_metadata_value_too_long():
    long_val = "v" * 1025
    with pytest.raises(ValidationError, match="значение"):
        SyncRecord(**_minimal_record(metadata={"key": long_val}))


def test_sync_record_metadata_key_max_length_ok():
    edge_key = "k" * 256
    r = SyncRecord(**_minimal_record(metadata={edge_key: "value"}))
    assert edge_key in r.metadata


def test_sync_record_metadata_value_max_length_ok():
    edge_val = "v" * 1024
    r = SyncRecord(**_minimal_record(metadata={"key": edge_val}))
    assert r.metadata["key"] == edge_val


# ─── SyncRequest.records limit ──────────────────────────────────────────────


def _make_record() -> dict:
    return _minimal_record(value="72", unit="count/min")


def test_sync_request_within_limit_ok():
    records = [SyncRecord(**_make_record()) for _ in range(100)]
    req = SyncRequest(sync_from="2024-01-01", sync_to="2024-01-02", records=records)
    assert len(req.records) == 100


def test_sync_request_exactly_at_limit_ok():
    records = [SyncRecord(**_make_record()) for _ in range(10_000)]
    req = SyncRequest(sync_from="2024-01-01", sync_to="2024-01-02", records=records)
    assert len(req.records) == 10_000


def test_sync_request_over_limit_raises():
    records = [SyncRecord(**_make_record()) for _ in range(10_001)]
    with pytest.raises(ValidationError, match="10000"):
        SyncRequest(sync_from="2024-01-01", sync_to="2024-01-02", records=records)


# ─── DaySchedule / ScheduleRequest validation ───────────────────────────────


def test_day_schedule_defaults_are_valid():
    s = DaySchedule()
    assert s.monday == "07:30"
    assert s.saturday == "09:00"


def test_day_schedule_custom_time_ok():
    s = DaySchedule(monday="06:00", tuesday="08:15")
    assert s.monday == "06:00"


def test_day_schedule_invalid_time_format():
    with pytest.raises(ValidationError, match="HH:MM"):
        DaySchedule(monday="7:30")  # missing leading zero


def test_day_schedule_invalid_time_hour_out_of_range():
    with pytest.raises(ValidationError):
        DaySchedule(wednesday="25:00")


def test_day_schedule_invalid_time_not_hhmm():
    with pytest.raises(ValidationError):
        DaySchedule(friday="noon")


def test_schedule_request_valid_timezone():
    req = ScheduleRequest(schedule=DaySchedule(), timezone="Europe/Moscow")
    assert req.timezone == "Europe/Moscow"


def test_schedule_request_utc_timezone():
    req = ScheduleRequest(schedule=DaySchedule(), timezone="UTC")
    assert req.timezone == "UTC"


def test_schedule_request_invalid_timezone():
    with pytest.raises(ValidationError, match="часовой пояс"):
        ScheduleRequest(schedule=DaySchedule(), timezone="Mars/Olympus")


def test_schedule_request_default_timezone_is_utc():
    req = ScheduleRequest(schedule=DaySchedule())
    assert req.timezone == "UTC"


# ─── _record_to_parsed ──────────────────────────────────────────────────────


def test_record_to_parsed_basic_fields():
    rec = SyncRecord(**_minimal_record(value="72", unit="count/min"))
    parsed = _record_to_parsed(rec)

    assert parsed.attrs["type"] == "HKQuantityTypeIdentifierHeartRate"
    assert parsed.attrs["sourceName"] == "Apple Watch"
    assert parsed.attrs["value"] == "72"
    assert parsed.attrs["unit"] == "count/min"
    assert parsed.metadata == {}
    assert parsed.hrv_bpm == []


def test_record_to_parsed_metadata_stringified():
    rec = SyncRecord(**_minimal_record(metadata={"key": "val", "num": 42}))
    parsed = _record_to_parsed(rec)
    assert parsed.metadata["key"] == "val"
    assert parsed.metadata["num"] == "42"


def test_record_to_parsed_hrv_bpm():
    rec = SyncRecord(
        **_minimal_record(
            type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
            instantaneous_bpm=[
                InstantaneousBpm(bpm=72, time="2024-01-01T12:00:01+03:00"),
                InstantaneousBpm(bpm=68, time="2024-01-01T12:00:02+03:00"),
            ],
        )
    )
    parsed = _record_to_parsed(rec)
    assert len(parsed.hrv_bpm) == 2
    assert parsed.hrv_bpm[0] == {"bpm": "72", "time": "2024-01-01T12:00:01+03:00"}
    assert parsed.hrv_bpm[1]["bpm"] == "68"


def test_record_to_parsed_dates_are_stored_as_strings():
    """parse_datetime is called downstream in repository, not here."""
    rec = SyncRecord(**_minimal_record())
    parsed = _record_to_parsed(rec)
    assert parsed.attrs["startDate"] == "2024-01-01T12:00:00+03:00"


def test_record_to_parsed_record_type_property():
    rec = SyncRecord(**_minimal_record())
    parsed = _record_to_parsed(rec)
    assert parsed.record_type == "HKQuantityTypeIdentifierHeartRate"


# ─── parse_datetime ISO 8601 (new formats) ──────────────────────────────────


def test_parse_datetime_iso_with_timezone_offset():
    dt = parse_datetime("2024-01-01T12:05:00+03:00")
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 1
    assert dt.hour == 12
    assert dt.minute == 5
    assert dt.tzinfo is None  # always stripped


def test_parse_datetime_iso_utc_offset():
    dt = parse_datetime("2024-06-15T08:30:00+00:00")
    assert dt is not None
    assert dt.hour == 8
    assert dt.minute == 30
    assert dt.tzinfo is None


def test_parse_datetime_iso_negative_offset():
    dt = parse_datetime("2024-03-20T22:00:00-05:00")
    assert dt is not None
    assert dt.hour == 22
    assert dt.tzinfo is None


def test_parse_datetime_iso_no_timezone():
    dt = parse_datetime("2024-01-01T12:05:00")
    assert dt is not None
    assert dt.hour == 12
    assert dt.tzinfo is None


def test_parse_datetime_original_space_format_still_works():
    dt = parse_datetime("2025-10-12 13:22:39 +0300")
    assert dt is not None
    assert dt.year == 2025


def test_parse_datetime_none_input():
    assert parse_datetime(None) is None


def test_parse_datetime_empty_string():
    assert parse_datetime("") is None


def test_parse_datetime_invalid_string():
    assert parse_datetime("not-a-date") is None
