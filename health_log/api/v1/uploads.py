from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.dependencies import db_connect
from health_log.services.ingestion import ingest_content

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_health_data(
    provider: str = Form(..., description="Источник данных, например apple_health или mifitness"),
    data_format: str = Form(..., description="Формат данных, например xml/json/csv"),
    file: UploadFile = File(...),
    conn: AsyncConnection = Depends(db_connect),
):
    content_length = file.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл слишком большой. Лимит: {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ",
        )

    raw_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if not raw_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл пустой")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл слишком большой. Лимит: {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ",
        )

    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл должен быть в UTF-8",
        ) from exc

    try:
        result = await ingest_content(
            conn,
            provider=provider.strip().lower(),
            data_format=data_format.strip().lower(),
            filename=file.filename or "upload.dat",
            content=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "upload_id": result.upload_id,
        "is_new_upload": result.is_new_upload,
        "raw_records_count": result.raw_records_count,
        "normalized_counts": result.normalized_counts,
        "hrv_records_count": result.hrv_records_count,
        "hrv_bpm_count": result.hrv_bpm_count,
    }
