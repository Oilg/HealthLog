from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.repositories.repository import IngestionRepository, RecordsRepository
from health_log.repositories.v1.tables import TYPE_TABLE_MAP
from health_log.services.apple_health_parser import AppleHealthXmlParser

SUPPORTED_PARSERS: dict[tuple[str, str], str] = {
    ("apple_health", "xml"): "apple_health_xml",
}


def _ensure_supported(provider: str, data_format: str) -> str:
    parser_name = SUPPORTED_PARSERS.get((provider, data_format))
    if parser_name is None:
        raise ValueError(
            f"Формат '{data_format}' для провайдера '{provider}' пока не поддерживается. "
            "Сейчас доступно: provider='apple_health', data_format='xml'."
        )
    return parser_name


@dataclass(slots=True)
class IngestionResult:
    upload_id: int
    is_new_upload: bool
    raw_records_count: int
    normalized_counts: dict[str, int]
    hrv_records_count: int
    hrv_bpm_count: int


def _parse_records(provider: str, data_format: str, content: str):
    parser_name = _ensure_supported(provider, data_format)
    if parser_name == "apple_health_xml":
        return AppleHealthXmlParser.parse_xml_content(content)
    return []


async def ingest_content(
    connection: AsyncConnection,
    *,
    user_id: int,
    provider: str,
    data_format: str,
    filename: str,
    content: str,
) -> IngestionResult:
    _ensure_supported(provider, data_format)

    ingestion_repo = IngestionRepository(connection)
    records_repo = RecordsRepository(connection)

    upload_id, is_new_upload = await ingestion_repo.create_upload(
        user_id=user_id,
        provider=provider,
        data_format=data_format,
        filename=filename,
        raw_payload=content,
    )

    raw_records_count = 0
    normalized_counts: dict[str, int] = {}
    hrv_records_count = 0
    hrv_bpm_count = 0

    if is_new_upload:
        parser_records = _parse_records(provider=provider, data_format=data_format, content=content)
        raw_records_count = await ingestion_repo.insert_raw_records(
            upload_id=upload_id,
            user_id=user_id,
            provider=provider,
            data_format=data_format,
            records=parser_records,
        )

        if provider == "apple_health" and data_format == "xml":
            for record_type, table in TYPE_TABLE_MAP.items():
                inserted_count = await records_repo.insert_records_for_type(
                    user_id=user_id,
                    record_type=record_type,
                    table=table,
                    record_list=parser_records,
                )
                normalized_counts[record_type] = inserted_count

            hrv_records_count, hrv_bpm_count = await records_repo.insert_hr_variability_records(
                user_id=user_id,
                records=parser_records,
            )

    return IngestionResult(
        upload_id=upload_id,
        is_new_upload=is_new_upload,
        raw_records_count=raw_records_count,
        normalized_counts=normalized_counts,
        hrv_records_count=hrv_records_count,
        hrv_bpm_count=hrv_bpm_count,
    )


async def ingest_xml_file(
    connection: AsyncConnection,
    file_path: str,
    *,
    user_id: int = 1,
    provider: str = "apple_health",
    data_format: str = "xml",
) -> IngestionResult:
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        content = f.read()

    return await ingest_content(
        connection,
        user_id=user_id,
        provider=provider,
        data_format=data_format,
        filename=path.name,
        content=content,
    )
