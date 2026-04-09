from datetime import timedelta
from pathlib import Path

from health_log.analysis.models import TimeWindow
from health_log.analysis.rules import assess_sleep_apnea_risk
from health_log.services.apple_health_parser import AppleHealthXmlParser, parse_datetime


def test_regression_real_xml_chunk_parses_and_scores():
    fixture = Path("tests/fixtures/apple_health_regression_chunk.xml")
    records = AppleHealthXmlParser.parse_xml_content(fixture.read_text(encoding="utf-8"))

    assert len(records) == 3

    hrv = next(r for r in records if r.record_type == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN")
    assert hrv.attrs["sourceName"].startswith("Apple")
    assert len(hrv.hrv_bpm) == 3

    respiratory = []
    heart = []
    hrv_values = []

    for rec in records:
        ts = parse_datetime(rec.attrs.get("startDate"))
        value = rec.attrs.get("value")
        if ts is None:
            continue

        if rec.record_type == "HKQuantityTypeIdentifierRespiratoryRate":
            respiratory.append((ts, value))
        elif rec.record_type == "HKQuantityTypeIdentifierHeartRate":
            heart.append((ts, value))
        elif rec.record_type == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
            hrv_values.append((ts, value))

    anchor = parse_datetime(records[0].attrs.get("startDate"))
    assert anchor is not None
    sleep_start = anchor - timedelta(minutes=30)
    sleep_end = anchor + timedelta(hours=5)
    sleep_segments = [(sleep_start, sleep_end)]

    extra_rr = []
    extra_hr = []
    extra_hrv = []
    for i in range(25):
        t = sleep_start + timedelta(minutes=i * 10)
        extra_rr.append((t, 12.0))
        extra_hr.append((t, 68.0))
        extra_hrv.append((t, 45.0))

    assessment = assess_sleep_apnea_risk(
        respiratory + extra_rr,
        heart + extra_hr,
        hrv_values + extra_hrv,
        sleep_segments=sleep_segments,
        window=TimeWindow.NIGHT,
    )

    assert assessment.score >= 0
    assert assessment.clinical_safety_note.startswith("Это не медицинский диагноз")
