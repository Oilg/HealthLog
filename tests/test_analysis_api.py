"""Unit tests for health_log/api/v1/analysis.py — _format_report helper and schemas."""

from __future__ import annotations

from datetime import datetime

import pytest

from health_log.api.v1.analysis import _format_report
from health_log.schemas.weekly_progress import (
    WeeklyProgressItemSchema,
    WeeklyProgressResponseSchema,
)


def _make_row(
    analyzed_at=None,
    period_from=None,
    period_to=None,
    window="night",
    risks=None,
) -> dict:
    return {
        "analyzed_at": analyzed_at or datetime(2024, 1, 2, 5, 0, 0),
        "period_from": period_from or datetime(2024, 1, 1, 22, 0, 0),
        "period_to": period_to or datetime(2024, 1, 2, 5, 0, 0),
        "window": window,
        "risks": risks if risks is not None else [],
    }


def test_format_report_includes_all_fields():
    row = _make_row()
    result = _format_report(row)
    assert set(result.keys()) == {"analyzed_at", "period_from", "period_to", "window", "risks"}


def test_format_report_dates_are_iso_strings():
    row = _make_row(
        analyzed_at=datetime(2024, 1, 2, 5, 0, 0),
        period_from=datetime(2024, 1, 1, 22, 0, 0),
        period_to=datetime(2024, 1, 2, 5, 0, 0),
    )
    result = _format_report(row)
    assert result["analyzed_at"] == "2024-01-02T05:00:00"
    assert result["period_from"] == "2024-01-01T22:00:00"
    assert result["period_to"] == "2024-01-02T05:00:00"


def test_format_report_window_preserved():
    result = _format_report(_make_row(window="week"))
    assert result["window"] == "week"


def test_format_report_risks_passed_through():
    risks = [
        {"type": "sleep_apnea", "severity": "moderate", "confidence": 0.78, "description": "..."}
    ]
    result = _format_report(_make_row(risks=risks))
    assert result["risks"] == risks


def test_format_report_empty_risks():
    result = _format_report(_make_row(risks=[]))
    assert result["risks"] == []


def test_format_report_none_risks_becomes_empty_list():
    row = _make_row()
    row["risks"] = None
    result = _format_report(row)
    assert result["risks"] == []


def test_format_report_none_dates_become_none():
    row = _make_row()
    row["analyzed_at"] = None
    row["period_from"] = None
    row["period_to"] = None
    result = _format_report(row)
    assert result["analyzed_at"] is None
    assert result["period_from"] is None
    assert result["period_to"] is None


# --- Fix 6: response schemas ---


def test_weekly_progress_response_schema_validates_correctly():
    item = WeeklyProgressItemSchema(
        condition="tachycardia_risk",
        label="Тахикардия",
        current_severity="moderate",
        previous_severity="low",
        severity_delta=1,
        direction="worsened",
        current_confidence=0.82,
        previous_confidence=0.65,
    )
    response = WeeklyProgressResponseSchema(
        current_period_from="2026-01-01T00:00:00",
        current_period_to="2026-01-08T00:00:00",
        previous_period_from="2025-12-25T00:00:00",
        previous_period_to="2026-01-01T00:00:00",
        has_previous=True,
        items=[item],
    )
    assert response.has_previous is True
    assert response.items[0].condition == "tachycardia_risk"
    assert response.items[0].current_confidence == pytest.approx(0.82)


def test_weekly_progress_response_schema_allows_none_confidence():
    item = WeeklyProgressItemSchema(
        condition="x_risk",
        label="X",
        current_severity="none",
        previous_severity="none",
        severity_delta=0,
        direction="unchanged",
        current_confidence=None,
        previous_confidence=None,
    )
    assert item.current_confidence is None
    assert item.previous_confidence is None


def test_weekly_progress_response_schema_empty_items():
    response = WeeklyProgressResponseSchema(
        current_period_from=None,
        current_period_to=None,
        previous_period_from=None,
        previous_period_to=None,
        has_previous=False,
        items=[],
    )
    assert response.items == []
