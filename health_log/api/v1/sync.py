from __future__ import annotations

import json
import uuid
from datetime import datetime
from health_log.utils import utcnow
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.dependencies import db_connect, get_current_user
from health_log.repositories.analysis import SyncScheduleRepository
from health_log.repositories.auth import AuthUser, UsersRepository
from health_log.repositories.repository import IngestionRepository, RecordsRepository
from health_log.repositories.v1.tables import TYPE_TABLE_MAP
from health_log.services.apple_health_parser import ParsedRecord

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


# ─── Request / Response models ──────────────────────────────────────────────


class InstantaneousBpm(BaseModel):
    bpm: int
    time: str


_METADATA_MAX_KEYS = 50
_METADATA_MAX_KEY_LEN = 256
_METADATA_MAX_VAL_LEN = 1024


class SyncRecord(BaseModel):
    type: str
    sourceName: str
    sourceVersion: str = ""
    creationDate: str
    startDate: str
    endDate: str
    value: str = ""
    unit: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    instantaneous_bpm: list[InstantaneousBpm] | None = None

    @validator("metadata")
    def validate_metadata(cls, v: dict) -> dict:
        if len(v) > _METADATA_MAX_KEYS:
            raise ValueError(f"metadata не может содержать более {_METADATA_MAX_KEYS} ключей")
        for key, val in v.items():
            if len(str(key)) > _METADATA_MAX_KEY_LEN:
                raise ValueError(f"ключ metadata слишком длинный (макс. {_METADATA_MAX_KEY_LEN} символов)")
            if len(str(val)) > _METADATA_MAX_VAL_LEN:
                raise ValueError(f"значение metadata слишком длинное (макс. {_METADATA_MAX_VAL_LEN} символов)")
        return v


class SyncRequest(BaseModel):
    sync_from: str
    sync_to: str
    records: list[SyncRecord]


def _validate_hhmm(value: str, field_name: str = "time") -> str:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        raise ValueError(f"Неверный формат {field_name}: '{value}'. Ожидается HH:MM")
    return value


class DaySchedule(BaseModel):
    monday: str = "07:30"
    tuesday: str = "07:30"
    wednesday: str = "07:30"
    thursday: str = "07:30"
    friday: str = "07:30"
    saturday: str = "09:00"
    sunday: str = "09:00"

    @validator("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", pre=True)
    def validate_time_format(cls, v: str, field) -> str:
        return _validate_hhmm(v, field.name)


class ScheduleRequest(BaseModel):
    schedule: DaySchedule
    timezone: str = "UTC"

    @validator("timezone")
    def validate_timezone(cls, v: str) -> str:
        import pytz
        if v not in pytz.all_timezones_set:
            raise ValueError(f"Неизвестный часовой пояс: '{v}'. Используйте IANA timezone (например, Europe/Moscow)")
        return v


# ─── Helpers ────────────────────────────────────────────────────────────────


def _record_to_parsed(record: SyncRecord) -> ParsedRecord:
    attrs = {
        "type": record.type,
        "sourceName": record.sourceName,
        "sourceVersion": record.sourceVersion,
        "creationDate": record.creationDate,
        "startDate": record.startDate,
        "endDate": record.endDate,
        "value": record.value,
        "unit": record.unit,
    }
    metadata = {str(k): str(v) for k, v in record.metadata.items()}
    hrv_bpm: list[dict[str, str]] = []
    if record.instantaneous_bpm:
        hrv_bpm = [{"bpm": str(entry.bpm), "time": entry.time} for entry in record.instantaneous_bpm]
    return ParsedRecord(attrs=attrs, metadata=metadata, hrv_bpm=hrv_bpm)


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def sync_health_data(
    body: SyncRequest,
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
):
    parsed_records = [_record_to_parsed(r) for r in body.records]

    raw_payload = json.dumps(
        {
            "sync_from": body.sync_from,
            "sync_to": body.sync_to,
            "records": [r.dict() for r in body.records],
        },
        ensure_ascii=False,
    )

    ingestion_repo = IngestionRepository(conn)
    records_repo = RecordsRepository(conn)

    upload_id, is_new_upload = await ingestion_repo.create_upload(
        user_id=current_user.id,
        provider="apple_health",
        data_format="json",
        filename=f"sync_{body.sync_from}_{body.sync_to}.json",
        raw_payload=raw_payload,
    )

    synced_count = 0

    if is_new_upload:
        raw_count = await ingestion_repo.insert_raw_records(
            upload_id=upload_id,
            user_id=current_user.id,
            provider="apple_health",
            data_format="json",
            records=parsed_records,
        )
        synced_count += raw_count

        for record_type, table in TYPE_TABLE_MAP.items():
            await records_repo.insert_records_for_type(
                user_id=current_user.id,
                record_type=record_type,
                table=table,
                record_list=parsed_records,
            )

        hrv_inserted, _ = await records_repo.insert_hr_variability_records(
            user_id=current_user.id,
            records=parsed_records,
        )

    users_repo = UsersRepository(conn)
    await users_repo.update_sync_status(
        current_user.id,
        last_sync_at=utcnow(),
        records_count=synced_count,
    )

    return {
        "sync_id": str(uuid.uuid4()),
        "synced_records": synced_count,
        "next_sync_from": body.sync_to,
    }


@router.get("/status")
async def get_sync_status(
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
):
    users_repo = UsersRepository(conn)
    status_data = await users_repo.get_sync_status(current_user.id)
    if status_data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    last_sync_at = status_data["last_sync_at"]
    return {
        "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
        "last_sync_records": status_data["last_sync_records_count"],
    }


@router.get("/schedule")
async def get_sync_schedule(
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
):
    repo = SyncScheduleRepository(conn)
    schedule = await repo.get_schedule(current_user.id)
    if schedule is None:
        default_schedule = {day: ("07:30" if day not in ("saturday", "sunday") else "09:00") for day in _DAYS}
        return {"schedule": default_schedule, "timezone": "UTC"}
    return schedule


@router.put("/schedule")
async def put_sync_schedule(
    body: ScheduleRequest,
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
):
    schedule_dict = body.schedule.dict()
    repo = SyncScheduleRepository(conn)
    await repo.upsert_schedule(current_user.id, schedule=schedule_dict, timezone=body.timezone)
    return {"schedule": schedule_dict, "timezone": body.timezone}
