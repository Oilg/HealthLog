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

    assessment = assess_sleep_apnea_risk(respiratory, heart, hrv_values, window=TimeWindow.NIGHT)

    assert assessment.score >= 0
    assert assessment.clinical_safety_note.startswith("Это не медицинский диагноз")
