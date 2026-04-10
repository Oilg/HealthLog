from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import and_, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.repositories.v1 import tables
from health_log.services.apple_health_parser import ParsedRecord, parse_datetime

BATCH_SIZE = 500

_STANDARD_UPSERT_COLS = ["user_id", "sourceName", "startDate", "endDate"]

UPSERT_KEYS: dict[str, list[str]] = {
    "sleep_analysis": _STANDARD_UPSERT_COLS,
    "sleep_duration_goal": _STANDARD_UPSERT_COLS,
    "heart_rate": _STANDARD_UPSERT_COLS,
    "heart_rate_variability": _STANDARD_UPSERT_COLS,
    "heart_rate_variability_bpm": ["hr_variability_id", "time"],
    "respiratory_rate": _STANDARD_UPSERT_COLS,
    "vo_2_max": _STANDARD_UPSERT_COLS,
    "menstrual_flow": _STANDARD_UPSERT_COLS,
    "sleep_apnea_events": ["user_id", "start_time", "end_time", "detected_by"],
    "oxygen_saturation": _STANDARD_UPSERT_COLS,
    "blood_pressure_systolic": _STANDARD_UPSERT_COLS,
    "blood_pressure_diastolic": _STANDARD_UPSERT_COLS,
    "apple_sleeping_wrist_temperature": _STANDARD_UPSERT_COLS,
    "walking_heart_rate_average": _STANDARD_UPSERT_COLS,
    "walking_speed": _STANDARD_UPSERT_COLS,
    "walking_step_length": _STANDARD_UPSERT_COLS,
    "walking_double_support_percentage": _STANDARD_UPSERT_COLS,
    "walking_steadiness": _STANDARD_UPSERT_COLS,
    "environmental_audio_exposure": _STANDARD_UPSERT_COLS,
    "headphone_audio_exposure": _STANDARD_UPSERT_COLS,
    "body_mass": _STANDARD_UPSERT_COLS,
    "body_mass_index": _STANDARD_UPSERT_COLS,
    "body_fat_percentage": _STANDARD_UPSERT_COLS,
    "lean_body_mass": _STANDARD_UPSERT_COLS,
    "waist_circumference": _STANDARD_UPSERT_COLS,
    "step_count": _STANDARD_UPSERT_COLS,
    "apple_exercise_time": _STANDARD_UPSERT_COLS,
    "apple_afib_burden": _STANDARD_UPSERT_COLS,
    "low_heart_rate_event": _STANDARD_UPSERT_COLS,
    "irregular_heart_rhythm_event": _STANDARD_UPSERT_COLS,
    "intermenstrual_bleeding": _STANDARD_UPSERT_COLS,
}


class BaseRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection


class RecordsRepository(BaseRepository):
    async def _upsert_in_batches(
        self,
        table,
        rows: list[dict[str, Any]],
        conflict_columns: list[str],
        batch_size: int = BATCH_SIZE,
    ) -> int:
        if not rows:
            return 0

        inserted_total = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            stmt = pg_insert(table).values(batch).returning(table.c.id)
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_columns)
            result = await self._connection.execute(stmt)
            inserted_total += len(result.fetchall())
        return inserted_total

    @staticmethod
    def _record_to_table_values(record: ParsedRecord, table, *, user_id: int) -> dict[str, Any]:
        values: dict[str, Any] = {"user_id": user_id} if "user_id" in table.c else {}
        attrs = record.attrs

        for col in table.columns:
            key = col.name
            if key not in attrs:
                continue

            value: Any = attrs[key]
            if key in {"creationDate", "startDate", "endDate"}:
                value = parse_datetime(value)
            values[key] = value

        return values

    async def insert_records_for_type(
        self,
        *,
        user_id: int,
        record_type: str,
        table,
        record_list: list[ParsedRecord],
    ) -> int:
        rows: list[dict[str, Any]] = []
        for record in record_list:
            if record.record_type != record_type:
                continue

            values = self._record_to_table_values(record, table, user_id=user_id)
            if values:
                rows.append(values)

        inserted = await self._upsert_in_batches(table, rows, UPSERT_KEYS[table.name])
        return inserted

    async def insert_hr_variability_records(self, *, user_id: int, records: list[ParsedRecord]) -> tuple[int, int]:
        hrv_table = tables.heart_rate_variability
        bpm_table = tables.instantaneous_bpm

        hrv_rows: list[dict[str, Any]] = []
        hrv_keys: list[tuple[int, str, datetime, datetime]] = []

        for record in records:
            if record.record_type != "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
                continue

            values = self._record_to_table_values(record, hrv_table, user_id=user_id)
            source_name = values.get("sourceName")
            start_date = values.get("startDate")
            end_date = values.get("endDate")
            if not (source_name and start_date and end_date):
                continue

            hrv_rows.append(values)
            hrv_keys.append((user_id, source_name, start_date, end_date))

        inserted_hrv = await self._upsert_in_batches(hrv_table, hrv_rows, UPSERT_KEYS[hrv_table.name])

        if not hrv_keys:
            return (inserted_hrv, 0)

        existing_rows = (
            await self._connection.execute(
                select(
                    hrv_table.c.id,
                    hrv_table.c.user_id,
                    hrv_table.c.sourceName,
                    hrv_table.c.startDate,
                    hrv_table.c.endDate,
                ).where(
                    tuple_(
                        hrv_table.c.user_id,
                        hrv_table.c.sourceName,
                        hrv_table.c.startDate,
                        hrv_table.c.endDate,
                    ).in_(hrv_keys)
                )
            )
        ).fetchall()

        hrv_map = {(r.user_id, r.sourceName, r.startDate, r.endDate): r.id for r in existing_rows}

        bpm_rows: list[dict[str, Any]] = []
        for record in records:
            if record.record_type != "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
                continue

            source_name = record.attrs.get("sourceName")
            start_date = parse_datetime(record.attrs.get("startDate"))
            end_date = parse_datetime(record.attrs.get("endDate"))
            hrv_id = hrv_map.get((user_id, source_name, start_date, end_date))
            if not hrv_id:
                continue

            for entry in record.hrv_bpm:
                bpm_raw = entry.get("bpm")
                bpm_time = entry.get("time")
                if not bpm_raw or not bpm_time:
                    continue

                try:
                    bpm = int(float(bpm_raw))
                except ValueError:
                    continue

                bpm_rows.append(
                    {
                        "hr_variability_id": hrv_id,
                        "bpm": bpm,
                        "time": bpm_time,
                    }
                )

        inserted_bpm = await self._upsert_in_batches(bpm_table, bpm_rows, UPSERT_KEYS[bpm_table.name])
        return (inserted_hrv, inserted_bpm)

    async def insert_sleep_apnea_events(self, user_id: int, events: list[dict[str, Any]]) -> int:
        rows = []
        for event in events:
            row = dict(event)
            row["user_id"] = user_id
            rows.append(row)

        inserted = await self._upsert_in_batches(
            tables.sleep_apnea_events,
            rows,
            UPSERT_KEYS[tables.sleep_apnea_events.name],
        )
        return inserted


class IngestionRepository(BaseRepository):
    async def create_upload(
        self,
        *,
        user_id: int,
        provider: str,
        data_format: str,
        filename: str,
        raw_payload: str,
    ) -> tuple[int, bool]:
        digest_src = f"{user_id}:{provider}:{data_format}:{raw_payload}"
        digest = sha256(digest_src.encode("utf-8")).hexdigest()

        stmt = (
            pg_insert(tables.xml_uploads)
            .values(
                user_id=user_id,
                provider=provider,
                data_format=data_format,
                filename=filename,
                sha256=digest,
                raw_xml=raw_payload,
            )
            .on_conflict_do_nothing(index_elements=["sha256"])
            .returning(tables.xml_uploads.c.id)
        )
        result = await self._connection.execute(stmt)
        upload_id = result.scalar_one_or_none()

        if upload_id is not None:
            return upload_id, True

        existing_id = (
            await self._connection.execute(
                select(tables.xml_uploads.c.id).where(
                    and_(
                        tables.xml_uploads.c.user_id == user_id,
                        tables.xml_uploads.c.sha256 == digest,
                    )
                )
            )
        ).scalar_one()
        return existing_id, False

    async def insert_raw_records(
        self,
        *,
        upload_id: int,
        user_id: int,
        provider: str,
        data_format: str,
        records: list[ParsedRecord],
    ) -> int:
        rows: list[dict[str, Any]] = []
        for record in records:
            attrs = record.attrs
            payload = {
                "attrs": attrs,
                "metadata": record.metadata,
                "hrv_bpm": record.hrv_bpm,
            }
            source_name = attrs.get("sourceName") or ""
            record_type = attrs.get("type", "unknown")
            start_date_raw = attrs.get("startDate") or ""
            end_date_raw = attrs.get("endDate") or ""
            value_raw = attrs.get("value") or ""
            fingerprint_src = (
                f"{user_id}|{provider}|{record_type}|{source_name}|{start_date_raw}|{end_date_raw}|{value_raw}"
            )
            record_fingerprint = sha256(fingerprint_src.encode("utf-8")).hexdigest()

            rows.append(
                {
                    "upload_id": upload_id,
                    "user_id": user_id,
                    "provider": provider,
                    "data_format": data_format,
                    "record_type": record_type,
                    "sourceName": attrs.get("sourceName"),
                    "creationDate": parse_datetime(attrs.get("creationDate")),
                    "startDate": parse_datetime(attrs.get("startDate")),
                    "endDate": parse_datetime(attrs.get("endDate")),
                    "record_fingerprint": record_fingerprint,
                    "payload": payload,
                }
            )

        if rows:
            stmt = pg_insert(tables.raw_health_records).values(rows).returning(tables.raw_health_records.c.id)
            stmt = stmt.on_conflict_do_nothing(index_elements=["user_id", "provider", "record_fingerprint"])
            result = await self._connection.execute(stmt)
            return len(result.fetchall())
        return 0
