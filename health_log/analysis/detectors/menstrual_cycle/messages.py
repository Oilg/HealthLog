from health_log.analysis.detectors.menstrual_cycle.constants import (
    MAX_CYCLE_LENGTH_DAYS,
    MIN_CYCLE_LENGTH_DAYS,
    MIN_PERIOD_STARTS,
    MIN_VALID_CYCLE_INTERVALS,
    MENSTRUAL_LOOKBACK_DAYS,
)


def build_insufficient_starts_summary(starts_count: int) -> str:
    return (
        f"Найдено стартов менструации: {starts_count}. Нужно минимум {MIN_PERIOD_STARTS} "
        f"за период до {MENSTRUAL_LOOKBACK_DAYS} дней."
    )


def build_insufficient_intervals_summary() -> str:
    return (
        f"Недостаточно валидных интервалов цикла ({MIN_CYCLE_LENGTH_DAYS}–{MAX_CYCLE_LENGTH_DAYS} дн.). "
        f"Нужно минимум {MIN_VALID_CYCLE_INTERVALS}."
    )


CALENDAR_DISCLAIMER = "Прогноз календарный, а не диагностический."
