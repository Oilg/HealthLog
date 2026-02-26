from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import insert, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.repositories.v1 import tables
from health_log.services.apple_health_parser import ParsedRecord, parse_datetime

BATCH_SIZE = 500

UPSERT_KEYS: dict[str, list[str]] = {
    "sleep_analysis": ["sourceName", "startDate", "endDate"],
    "sleep_duration_goal": ["sourceName", "startDate", "endDate"],
    "heart_rate": ["sourceName", "startDate", "endDate"],
    "heart_rate_variability": ["sourceName", "startDate", "endDate"],
    "heart_rate_variability_bpm": ["hr_variability_id", "time"],
    "respiratory_rate": ["sourceName", "startDate", "endDate"],
    "vo_2_max": ["sourceName", "startDate", "endDate"],
    "sleep_apnea_events": ["start_time", "end_time", "detected_by"],
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
    ) -> None:
        if not rows:
            return

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            stmt = pg_insert(table).values(batch)
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_columns)
            await self._connection.execute(stmt)

    @staticmethod
    def _record_to_table_values(record: ParsedRecord, table) -> dict[str, Any]:
        values: dict[str, Any] = {}
        attrs = record.attrs

        for col in table.columns:
            key = col.name
            if key not in attrs:
                continue

            value = attrs[key]
            if key in {"creationDate", "startDate", "endDate"}:
                value = parse_datetime(value)
            values[key] = value

        return values

    async def insert_records_for_type(self, record_type: str, table, record_list: list[ParsedRecord]) -> int:
        rows: list[dict[str, Any]] = []
        for record in record_list:
            if record.record_type != record_type:
                continue

            values = self._record_to_table_values(record, table)
            if values:
                rows.append(values)

        await self._upsert_in_batches(table, rows, UPSERT_KEYS[table.name])
        return len(rows)

    async def insert_hr_variability_records(self, records: list[ParsedRecord]) -> tuple[int, int]:
        hrv_table = tables.heart_rate_variability
        bpm_table = tables.instantaneous_bpm

        hrv_rows: list[dict[str, Any]] = []
        hrv_keys: list[tuple[str, datetime, datetime]] = []

        for record in records:
            if record.record_type != "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
                continue

            values = self._record_to_table_values(record, hrv_table)
            source_name = values.get("sourceName")
            start_date = values.get("startDate")
            end_date = values.get("endDate")
            if not (source_name and start_date and end_date):
                continue

            hrv_rows.append(values)
            hrv_keys.append((source_name, start_date, end_date))

        await self._upsert_in_batches(hrv_table, hrv_rows, UPSERT_KEYS[hrv_table.name])

        if not hrv_keys:
            return (len(hrv_rows), 0)

        existing_rows = (
            await self._connection.execute(
                select(
                    hrv_table.c.id,
                    hrv_table.c.sourceName,
                    hrv_table.c.startDate,
                    hrv_table.c.endDate,
                ).where(tuple_(hrv_table.c.sourceName, hrv_table.c.startDate, hrv_table.c.endDate).in_(hrv_keys))
            )
        ).fetchall()

        hrv_map = {(r.sourceName, r.startDate, r.endDate): r.id for r in existing_rows}

        bpm_rows: list[dict[str, Any]] = []
        for record in records:
            if record.record_type != "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
                continue

            source_name = record.attrs.get("sourceName")
            start_date = parse_datetime(record.attrs.get("startDate"))
            end_date = parse_datetime(record.attrs.get("endDate"))
            hrv_id = hrv_map.get((source_name, start_date, end_date))
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

        await self._upsert_in_batches(bpm_table, bpm_rows, UPSERT_KEYS[bpm_table.name])
        return (len(hrv_rows), len(bpm_rows))

    async def insert_sleep_apnea_events(self, events: list[dict[str, Any]]) -> int:
        await self._upsert_in_batches(
            tables.sleep_apnea_events,
            events,
            UPSERT_KEYS[tables.sleep_apnea_events.name],
        )
        return len(events)


class IngestionRepository(BaseRepository):
    async def create_upload(
        self,
        *,
        provider: str,
        data_format: str,
        filename: str,
        raw_payload: str,
    ) -> tuple[int, bool]:
        digest_src = f"{provider}:{data_format}:{raw_payload}"
        digest = sha256(digest_src.encode("utf-8")).hexdigest()

        stmt = (
            pg_insert(tables.xml_uploads)
            .values(
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
                select(tables.xml_uploads.c.id).where(tables.xml_uploads.c.sha256 == digest)
            )
        ).scalar_one()
        return existing_id, False

    async def insert_raw_records(
        self,
        *,
        upload_id: int,
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
            fingerprint_src = f"{provider}|{record_type}|{source_name}|{start_date_raw}|{end_date_raw}|{value_raw}"
            record_fingerprint = sha256(fingerprint_src.encode("utf-8")).hexdigest()

            rows.append(
                {
                    "upload_id": upload_id,
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
            stmt = pg_insert(tables.raw_health_records).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["provider", "record_fingerprint"])
            await self._connection.execute(stmt)
        return len(rows)
