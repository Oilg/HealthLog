from __future__ import annotations

from pathlib import Path

import pytest

from health_log.repositories.v1.tables import TYPE_TABLE_MAP
from health_log.services.apple_health_parser import AppleHealthXmlParser
from tests.integration.conftest import requires_db

FIXTURE_PATH = Path("tests/fixtures/apple_health_extended_types.xml")

_EXTENDED_QUANTITY_TYPES = [
    "HKQuantityTypeIdentifierOxygenSaturation",
    "HKQuantityTypeIdentifierBloodPressureSystolic",
    "HKQuantityTypeIdentifierBloodPressureDiastolic",
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature",
    "HKQuantityTypeIdentifierWalkingHeartRateAverage",
    "HKQuantityTypeIdentifierWalkingSpeed",
    "HKQuantityTypeIdentifierWalkingStepLength",
    "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage",
    "HKQuantityTypeIdentifierWalkingSteadiness",
    "HKQuantityTypeIdentifierEnvironmentalAudioExposure",
    "HKQuantityTypeIdentifierHeadphoneAudioExposure",
    "HKQuantityTypeIdentifierBodyMass",
    "HKQuantityTypeIdentifierBodyMassIndex",
    "HKQuantityTypeIdentifierBodyFatPercentage",
    "HKQuantityTypeIdentifierLeanBodyMass",
    "HKQuantityTypeIdentifierWaistCircumference",
    "HKQuantityTypeIdentifierStepCount",
    "HKQuantityTypeIdentifierAppleExerciseTime",
    "HKQuantityTypeIdentifierAppleAFibBurden",
]

_EXTENDED_CATEGORY_TYPES = [
    "HKCategoryTypeIdentifierLowHeartRateEvent",
    "HKCategoryTypeIdentifierIrregularHeartRhythmEvent",
    "HKCategoryTypeIdentifierIntermenstrualBleeding",
]

_ALL_EXTENDED_TYPES = _EXTENDED_QUANTITY_TYPES + _EXTENDED_CATEGORY_TYPES


def _parse_fixture():
    return AppleHealthXmlParser.parse_xml_content(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_extended_types_are_parsed_from_xml():
    records = _parse_fixture()
    parsed_types = {r.record_type for r in records}
    for record_type in _ALL_EXTENDED_TYPES:
        assert record_type in parsed_types, f"Record type not found in fixture: {record_type}"


def test_extended_types_exist_in_type_table_map():
    for record_type in _ALL_EXTENDED_TYPES:
        assert record_type in TYPE_TABLE_MAP, (
            f"Record type '{record_type}' is missing from TYPE_TABLE_MAP. "
            "Add it to health_log/repositories/v1/tables.py"
        )


def test_extended_quantity_records_have_correct_fixture_values():
    records = _parse_fixture()
    for record_type in _EXTENDED_QUANTITY_TYPES:
        matching = [r for r in records if r.record_type == record_type]
        assert len(matching) >= 1, f"No records found for {record_type}"
        for r in matching:
            assert r.attrs.get("sourceName"), f"Missing sourceName for {record_type}"
            assert r.attrs.get("startDate"), f"Missing startDate for {record_type}"
            assert r.attrs.get("endDate"), f"Missing endDate for {record_type}"
            assert r.attrs.get("value") is not None, f"Missing value for {record_type}"


def test_extended_category_records_have_correct_fixture_values():
    records = _parse_fixture()
    for record_type in _EXTENDED_CATEGORY_TYPES:
        matching = [r for r in records if r.record_type == record_type]
        assert len(matching) >= 1, f"No records found for {record_type}"
        for r in matching:
            assert r.attrs.get("sourceName"), f"Missing sourceName for {record_type}"
            assert r.attrs.get("startDate"), f"Missing startDate for {record_type}"
            assert r.attrs.get("endDate"), f"Missing endDate for {record_type}"


@requires_db
@pytest.mark.asyncio
async def test_extended_quantity_records_are_inserted_into_expected_tables(db_conn, test_user_id):
    from sqlalchemy import select

    from health_log.repositories.repository import RecordsRepository

    uid = test_user_id
    records = _parse_fixture()
    repo = RecordsRepository(db_conn)

    for record_type in _EXTENDED_QUANTITY_TYPES:
        table = TYPE_TABLE_MAP[record_type]
        await repo.insert_records_for_type(
            user_id=uid,
            record_type=record_type,
            table=table,
            record_list=records,
        )
        result = await db_conn.execute(
            select(table).where(table.c.user_id == uid)
        )
        rows = result.fetchall()
        assert len(rows) >= 1, (
            f"No rows in table '{table.name}' for record_type '{record_type}' after insert. "
            "Check TYPE_TABLE_MAP and table column definitions."
        )
        row = rows[0]
        assert row.sourceName, f"Empty sourceName in {table.name}"
        assert row.startDate is not None, f"Null startDate in {table.name}"
        assert row.endDate is not None, f"Null endDate in {table.name}"


@requires_db
@pytest.mark.asyncio
async def test_extended_category_records_are_inserted_into_expected_tables(db_conn, test_user_id):
    from sqlalchemy import select

    from health_log.repositories.repository import RecordsRepository

    uid = test_user_id
    records = _parse_fixture()
    repo = RecordsRepository(db_conn)

    for record_type in _EXTENDED_CATEGORY_TYPES:
        table = TYPE_TABLE_MAP[record_type]
        await repo.insert_records_for_type(
            user_id=uid,
            record_type=record_type,
            table=table,
            record_list=records,
        )
        result = await db_conn.execute(
            select(table).where(table.c.user_id == uid)
        )
        rows = result.fetchall()
        assert len(rows) >= 1, (
            f"No rows in table '{table.name}' for record_type '{record_type}' after insert. "
            "Check TYPE_TABLE_MAP and table column definitions."
        )
        row = rows[0]
        assert row.sourceName, f"Empty sourceName in {table.name}"
        assert row.startDate is not None, f"Null startDate in {table.name}"
