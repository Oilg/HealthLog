"""Unit tests for health_log.analysis.weekly_progress.compute_weekly_progress."""

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from health_log.analysis.weekly_progress import (
    CONDITION_LABELS,
    _index_risks,
    _severity_rank,
    compute_weekly_progress,
)


def _risk(condition: str, severity: str, confidence: float = 0.8) -> dict:
    return {
        "condition": condition,
        "severity": severity,
        "confidence": confidence,
        "interpretation": "test interpretation",
    }


def _report(period_from: datetime, period_to: datetime, risks: list[dict]) -> dict:
    return {
        "analyzed_at": period_to,
        "period_from": period_from,
        "period_to": period_to,
        "window": "week",
        "risks": risks,
    }


def test_returns_empty_when_no_reports():
    result = compute_weekly_progress(None, None)
    assert result["items"] == []
    assert result["has_previous"] is False
    assert result["current_period_from"] is None


def test_single_report_marks_existing_risks_as_worsened():
    cur = _report(
        datetime(2026, 1, 1),
        datetime(2026, 1, 8),
        [_risk("tachycardia_risk", "moderate")],
    )
    result = compute_weekly_progress(cur, None)
    assert result["has_previous"] is False
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["condition"] == "tachycardia_risk"
    assert item["current_severity"] == "moderate"
    assert item["previous_severity"] == "none"
    assert item["direction"] == "worsened"
    assert item["severity_delta"] == 2


def test_risk_disappeared_marked_as_improved():
    prv = _report(datetime(2025, 12, 25), datetime(2026, 1, 1), [_risk("obesity_risk", "high")])
    cur = _report(datetime(2026, 1, 1), datetime(2026, 1, 8), [])
    result = compute_weekly_progress(cur, prv)
    assert result["has_previous"] is True
    item = result["items"][0]
    assert item["condition"] == "obesity_risk"
    assert item["direction"] == "improved"
    assert item["current_severity"] == "none"
    assert item["previous_severity"] == "high"
    assert item["severity_delta"] == -3


def test_severity_dropped_marked_as_improved():
    prv = _report(
        datetime(2025, 12, 25), datetime(2026, 1, 1), [_risk("hypertension_risk", "high")]
    )
    cur = _report(datetime(2026, 1, 1), datetime(2026, 1, 8), [_risk("hypertension_risk", "low")])
    item = compute_weekly_progress(cur, prv)["items"][0]
    assert item["direction"] == "improved"
    assert item["severity_delta"] == -2


def test_severity_rose_marked_as_worsened():
    prv = _report(datetime(2025, 12, 25), datetime(2026, 1, 1), [_risk("sleep_apnea_risk", "low")])
    cur = _report(
        datetime(2026, 1, 1), datetime(2026, 1, 8), [_risk("sleep_apnea_risk", "moderate")]
    )
    item = compute_weekly_progress(cur, prv)["items"][0]
    assert item["direction"] == "worsened"
    assert item["severity_delta"] == 1


def test_same_severity_marked_as_unchanged():
    prv = _report(datetime(2025, 12, 25), datetime(2026, 1, 1), [_risk("fall_risk", "moderate")])
    cur = _report(datetime(2026, 1, 1), datetime(2026, 1, 8), [_risk("fall_risk", "moderate")])
    item = compute_weekly_progress(cur, prv)["items"][0]
    assert item["direction"] == "unchanged"
    assert item["severity_delta"] == 0


def test_items_sorted_worsened_first_then_improved_then_unchanged():
    prv = _report(
        datetime(2025, 12, 25),
        datetime(2026, 1, 1),
        [
            _risk("obesity_risk", "high"),  # will improve (disappear)
            _risk("fall_risk", "moderate"),  # will stay unchanged
        ],
    )
    cur = _report(
        datetime(2026, 1, 1),
        datetime(2026, 1, 8),
        [
            _risk("fall_risk", "moderate"),
            _risk("tachycardia_risk", "high"),  # newly worsened
        ],
    )
    items = compute_weekly_progress(cur, prv)["items"]
    directions = [it["direction"] for it in items]
    assert directions == ["worsened", "improved", "unchanged"]


def test_label_uses_known_translation():
    cur = _report(
        datetime(2026, 1, 1), datetime(2026, 1, 8), [_risk("tachycardia_risk", "moderate")]
    )
    item = compute_weekly_progress(cur, None)["items"][0]
    assert item["label"] == CONDITION_LABELS["tachycardia_risk"]


def test_label_falls_back_to_interpretation_for_unknown_condition():
    cur = _report(
        datetime(2026, 1, 1),
        datetime(2026, 1, 8),
        [
            {
                "condition": "some_brand_new_risk",
                "severity": "low",
                "confidence": 0.5,
                "interpretation": "Какой-то новый риск",
            }
        ],
    )
    item = compute_weekly_progress(cur, None)["items"][0]
    assert item["label"] == "Какой-то новый риск"


def test_label_falls_back_to_condition_when_no_interpretation():
    cur = _report(
        datetime(2026, 1, 1),
        datetime(2026, 1, 8),
        [{"condition": "x_y_z", "severity": "low", "confidence": 0.1}],
    )
    item = compute_weekly_progress(cur, None)["items"][0]
    assert item["label"] == "x_y_z"


def test_dates_serialized_to_iso_strings():
    cur = _report(datetime(2026, 1, 1, 12, 0), datetime(2026, 1, 8, 12, 0), [])
    prv = _report(datetime(2025, 12, 25, 12, 0), datetime(2026, 1, 1, 12, 0), [])
    result = compute_weekly_progress(cur, prv)
    assert result["current_period_from"] == "2026-01-01T12:00:00"
    assert result["current_period_to"] == "2026-01-08T12:00:00"
    assert result["previous_period_from"] == "2025-12-25T12:00:00"
    assert result["previous_period_to"] == "2026-01-01T12:00:00"


def test_handles_none_risks_in_report():
    cur = {
        "analyzed_at": datetime(2026, 1, 8),
        "period_from": datetime(2026, 1, 1),
        "period_to": datetime(2026, 1, 8),
        "window": "week",
        "risks": None,
    }
    result = compute_weekly_progress(cur, None)
    assert result["items"] == []
    assert result["current_period_to"] == "2026-01-08T00:00:00"


def test_skips_risks_with_missing_condition():
    cur = _report(
        datetime(2026, 1, 1),
        datetime(2026, 1, 8),
        [
            {"severity": "low", "confidence": 0.5},  # no condition
            _risk("tachycardia_risk", "low"),
        ],
    )
    items = compute_weekly_progress(cur, None)["items"]
    assert len(items) == 1
    assert items[0]["condition"] == "tachycardia_risk"


@pytest.mark.parametrize(
    "severity_str,expected_rank",
    [
        ("none", 0),
        ("low", 1),
        ("moderate", 2),
        ("high", 3),
        ("HIGH", 3),  # case insensitive
        ("unknown_value", 0),  # unknown -> 0
    ],
)
def test_severity_rank_mapping(severity_str: str, expected_rank: int):
    # Indirect test through compute output severity_delta
    cur = _report(
        datetime(2026, 1, 1),
        datetime(2026, 1, 8),
        [_risk("tachycardia_risk", severity_str)],
    )
    item = compute_weekly_progress(cur, None)["items"][0]
    assert item["severity_delta"] == expected_rank


def test_confidence_pass_through():
    prv = _report(
        datetime(2025, 12, 25),
        datetime(2026, 1, 1),
        [_risk("obesity_risk", "moderate", confidence=0.55)],
    )
    cur = _report(
        datetime(2026, 1, 1),
        datetime(2026, 1, 8),
        [_risk("obesity_risk", "high", confidence=0.81)],
    )
    item = compute_weekly_progress(cur, prv)["items"][0]
    assert item["current_confidence"] == pytest.approx(0.81)
    assert item["previous_confidence"] == pytest.approx(0.55)


# --- Fix 2: _index_risks guards against non-list risks ---


def test_index_risks_returns_empty_dict_for_string_input():
    """If SQLAlchemy returns risks as a raw string, _index_risks must not iterate chars."""
    assert _index_risks('{"condition":"x"}') == {}  # type: ignore[arg-type]


def test_index_risks_returns_empty_dict_for_none():
    assert _index_risks(None) == {}


def test_index_risks_returns_empty_dict_for_empty_list():
    assert _index_risks([]) == {}


# --- Fix 5: unknown severity logs warning, returns 0 ---


def test_severity_rank_unknown_returns_zero_and_logs_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="health_log.analysis.weekly_progress"):
        rank = _severity_rank("critical")
    assert rank == 0
    assert "critical" in caplog.text


def test_severity_rank_none_returns_zero_without_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="health_log.analysis.weekly_progress"):
        rank = _severity_rank(None)
    assert rank == 0
    assert not caplog.records
