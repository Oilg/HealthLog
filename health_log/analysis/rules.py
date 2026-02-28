"""Compatibility facade for analysis rules.

The project now keeps each detector in its own module under
`health_log.analysis.detectors`.
This module re-exports public call sites to avoid breaking imports.
"""

from health_log.analysis.detectors import (
    assess_illness_onset_risk,
    assess_sleep_apnea_risk,
    assess_tachycardia_risk,
    build_sleep_apnea_event_rows,
)
from health_log.analysis.utils import build_score_confidence_interpretation
from health_log.analysis.windows import resolve_window_range

__all__ = [
    "assess_sleep_apnea_risk",
    "build_sleep_apnea_event_rows",
    "assess_tachycardia_risk",
    "assess_illness_onset_risk",
    "resolve_window_range",
    "build_score_confidence_interpretation",
]
