from pathlib import Path

from health_log.services.apple_health_parser import AppleHealthXmlParser, parse_datetime


def test_parse_xml_extracts_nested_hrv_bpm():
    fixture = Path("tests/fixtures/apple_health_small.xml")
    records = AppleHealthXmlParser.parse_xml_content(fixture.read_text(encoding="utf-8"))

    assert len(records) == 4

    hrv_record = next(r for r in records if r.record_type == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN")
    assert hrv_record.metadata["HKAlgorithmVersion"] == "2"
    assert len(hrv_record.hrv_bpm) == 2
    assert hrv_record.hrv_bpm[0]["bpm"] == "63"


def test_parse_datetime_handles_timezone_and_nbsp():
    dt = parse_datetime("2025-10-12 13:22:39 +0300")
    assert dt is not None
    assert dt.year == 2025

    dt_nbsp = parse_datetime("2025-10-12 13:22:39\u00A0+0300")
    assert dt_nbsp is not None
    assert dt_nbsp.minute == 22
