from __future__ import annotations

from pydantic import BaseModel


class WeeklyProgressItemSchema(BaseModel):
    condition: str
    label: str
    current_severity: str
    previous_severity: str
    severity_delta: int
    direction: str
    current_confidence: float | None
    previous_confidence: float | None


class WeeklyProgressResponseSchema(BaseModel):
    current_period_from: str | None
    current_period_to: str | None
    previous_period_from: str | None
    previous_period_to: str | None
    has_previous: bool
    items: list[WeeklyProgressItemSchema]
