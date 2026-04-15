from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.dependencies import db_connect, get_current_user
from health_log.repositories.analysis import AnalysisReportsRepository
from health_log.repositories.auth import AuthUser

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def _format_report(row: dict) -> dict:
    return {
        "analyzed_at": row["analyzed_at"].isoformat() if row["analyzed_at"] else None,
        "period_from": row["period_from"].isoformat() if row["period_from"] else None,
        "period_to": row["period_to"].isoformat() if row["period_to"] else None,
        "risks": row["risks"] or [],
    }


@router.get("/latest")
async def get_latest_analysis(
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
):
    repo = AnalysisReportsRepository(conn)
    report = await repo.get_latest_report(current_user.id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Отчётов об анализе пока нет. Запустите анализ после синхронизации данных.",
        )
    return _format_report(report)


@router.get("/history")
async def get_analysis_history(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(db_connect),
):
    repo = AnalysisReportsRepository(conn)
    items, total = await repo.get_history(current_user.id, limit=limit, offset=offset)
    return {
        "items": [_format_report(item) for item in items],
        "total": total,
    }
