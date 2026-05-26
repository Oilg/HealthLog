"""Weekly progress/regress comparison between two consecutive weekly analysis reports.

Compares the latest week-window analysis report with the previous one and returns
per-detector deltas: did the risk improve, worsen, or stay unchanged.

For all risk detectors in HealthLog the convention is "lower severity = better health",
so the direction mapping is unambiguous:
  * risk disappeared or severity dropped -> improved
  * risk appeared or severity rose       -> worsened
  * same severity                         -> unchanged
"""

from __future__ import annotations

from typing import Any

# Severity ranks — keep aligned with detectors' severity vocabulary.
_SEVERITY_RANK: dict[str, int] = {
    "none": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
}

# Russian condition labels mirror the table in analysis/engine.py.
# Duplicated here to avoid an import cycle and to keep the API module decoupled
# from the heavy engine module.
CONDITION_LABELS: dict[str, str] = {
    "sleep_apnea_risk": "Апноэ сна",
    "tachycardia_risk": "Тахикардия",
    "illness_onset_risk": "Начало простуды",
    "bradycardia_risk": "Брадикардия",
    "irregular_rhythm_risk": "Нерегулярный ритм",
    "atrial_fibrillation_risk": "Фибрилляция предсердий",
    "low_oxygen_saturation_risk": "Низкий SpO₂",
    "hypertension_risk": "Повышенное давление",
    "hypotension_risk": "Пониженное давление",
    "temperature_shift_risk": "Температурный сдвиг",
    "vo2max_decline_risk": "Снижение VO₂ max",
    "hrr_decline_risk": "Ухудшение восстановления",
    "overload_recovery_risk": "Перегрузка / недосып",
    "walking_tolerance_decline_risk": "Переносимость нагрузки",
    "respiratory_function_decline_risk": "Дыхательная функция",
    "fall_risk": "Устойчивость ходьбы",
    "noise_exposure_risk": "Шумовое воздействие",
    "menstrual_irregularity_risk": "Нерегулярность цикла",
    "atypical_menstrual_bleeding_risk": "Атипичные кровотечения",
    "menstrual_cycle_start_forecast": "Прогноз начала менструации",
    "menstrual_cycle_delay_risk": "Задержка менструации",
    "ovulation_window_forecast": "Прогноз овуляции",
    "menstrual_start_forecast_with_temp": "Прогноз менструации (темп.)",
    "ovulation_forecast_with_temp": "Прогноз овуляции (темп.)",
    "overweight_risk": "Избыточная масса",
    "obesity_risk": "Ожирение",
    "high_body_fat_risk": "Высокий % жира",
    "abdominal_obesity_risk": "Абдоминальное ожирение",
    "lean_mass_decline_risk": "Снижение мышечной массы",
    "weight_trend_risk": "Тренд веса",
    "fat_mass_trend_risk": "Тренд жировой массы",
    "sedentary_lifestyle_risk": "Малоподвижный образ жизни",
    "insufficient_activity_risk": "Недостаточная активность",
    "cardiometabolic_profile_risk": "Кардиометаболический профиль",
    "metabolic_syndrome_risk": "Метаболический синдром",
    "cardiovascular_obesity_risk": "Сердечно-сосудистый риск",
    "fitness_weight_gain_risk": "Снижение формы / набор веса",
    "recovery_obesity_risk": "Восстановление / избыток массы",
    "body_composition_trend_risk": "Состав тела",
}


def _severity_rank(severity: str | None) -> int:
    """Map severity string to a comparable rank. Unknown values default to 0."""
    if severity is None:
        return 0
    return _SEVERITY_RANK.get(severity.lower(), 0)


def _index_risks(risks: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Index a risks list by condition string for O(1) lookup."""
    if not risks:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for risk in risks:
        condition = risk.get("condition")
        if isinstance(condition, str) and condition:
            out[condition] = risk
    return out


def _label_for(condition: str, risk: dict[str, Any] | None) -> str:
    """Pick a human-readable label for a condition.

    Priority: known russian label table -> interpretation from the risk payload
    -> raw condition string as last resort.
    """
    if condition in CONDITION_LABELS:
        return CONDITION_LABELS[condition]
    if risk is not None:
        interp = risk.get("interpretation")
        if isinstance(interp, str) and interp:
            return interp
    return condition


def _direction(current_rank: int, previous_rank: int) -> str:
    if current_rank < previous_rank:
        return "improved"
    if current_rank > previous_rank:
        return "worsened"
    return "unchanged"


def compute_weekly_progress(
    current_report: dict[str, Any] | None,
    previous_report: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute per-detector progress/regress between two weekly reports.

    Args:
        current_report: latest weekly analysis report dict (with ``risks`` list).
        previous_report: weekly analysis report immediately preceding ``current_report``.

    Returns a dict with shape::

        {
          "current_period_from": iso str | None,
          "current_period_to":   iso str | None,
          "previous_period_from": iso str | None,
          "previous_period_to":   iso str | None,
          "has_previous": bool,
          "items": [
            {
              "condition": str,
              "label": str,
              "current_severity": "none"|"low"|"moderate"|"high",
              "previous_severity": "none"|"low"|"moderate"|"high",
              "severity_delta": int,        # current_rank - previous_rank
              "direction": "improved"|"worsened"|"unchanged",
              "current_confidence": float | None,
              "previous_confidence": float | None,
            }, ...
          ]
        }

    Items are sorted with worsened first, improved second, unchanged last; inside each
    group by absolute severity delta desc, then by label asc.
    """

    current_risks = (current_report or {}).get("risks") if current_report else None
    previous_risks = (previous_report or {}).get("risks") if previous_report else None

    current_idx = _index_risks(current_risks)
    previous_idx = _index_risks(previous_risks)

    all_conditions = set(current_idx.keys()) | set(previous_idx.keys())

    items: list[dict[str, Any]] = []
    for condition in all_conditions:
        cur = current_idx.get(condition)
        prv = previous_idx.get(condition)

        cur_sev = (cur or {}).get("severity") or "none"
        prv_sev = (prv or {}).get("severity") or "none"
        cur_rank = _severity_rank(cur_sev)
        prv_rank = _severity_rank(prv_sev)

        items.append(
            {
                "condition": condition,
                "label": _label_for(condition, cur or prv),
                "current_severity": cur_sev,
                "previous_severity": prv_sev,
                "severity_delta": cur_rank - prv_rank,
                "direction": _direction(cur_rank, prv_rank),
                "current_confidence": (cur or {}).get("confidence"),
                "previous_confidence": (prv or {}).get("confidence"),
            }
        )

    _direction_order = {"worsened": 0, "improved": 1, "unchanged": 2}
    items.sort(
        key=lambda it: (
            _direction_order.get(it["direction"], 3),
            -abs(it["severity_delta"]),
            it["label"],
        )
    )

    def _iso(report: dict[str, Any] | None, key: str) -> str | None:
        if not report:
            return None
        value = report.get(key)
        if value is None:
            return None
        # Repository may already return datetime; api layer converts to iso.
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return {
        "current_period_from": _iso(current_report, "period_from"),
        "current_period_to": _iso(current_report, "period_to"),
        "previous_period_from": _iso(previous_report, "period_from"),
        "previous_period_to": _iso(previous_report, "period_to"),
        "has_previous": previous_report is not None,
        "items": items,
    }
