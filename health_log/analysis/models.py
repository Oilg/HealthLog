from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TimeWindow(str, Enum):
    NIGHT = "night"
    WEEK = "week"
    MONTH = "month"


@dataclass(slots=True)
class SignalEvidence:
    low_respiratory_events: int = 0
    hr_spike_events: int = 0
    hrv_drop_events: int = 0
    data_points: int = 0


@dataclass(slots=True)
class RiskAssessment:
    condition: str
    window: TimeWindow
    score: float
    confidence: float
    severity: str
    interpretation: str
    summary: str
    recommendation: str
    clinical_safety_note: str
    created_at: datetime = field(default_factory=datetime.utcnow)
