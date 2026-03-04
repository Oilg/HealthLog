from health_log.analysis.detectors.menstrual_cycle.constants import MENSTRUAL_LOOKBACK_DAYS
from health_log.analysis.detectors.menstrual_cycle.features import MenstrualTrend


def build_insufficient_cycles_summary(starts_count: int) -> str:
    return (
        f"Найдено циклов: {starts_count}. Для стабильного прогноза нужно минимум 3 цикла "
        f"за последние {MENSTRUAL_LOOKBACK_DAYS} дней."
    )


def build_summary(trend: MenstrualTrend) -> str:
    return (
        f"Типичная длина цикла (с акцентом на последние месяцы): ~{trend.typical_cycle} дн.; "
        f"ожидаемое окно начала следующих месячных: {trend.predicted_earliest.isoformat()} - "
        f"{trend.predicted_latest.isoformat()}; "
        f"ориентировочное окно овуляции: {trend.ovulation_from.isoformat()} - {trend.ovulation_to.isoformat()}."
    )


def build_recommendation() -> str:
    return (
        "Прогноз является ориентировочным. Если цикл заметно меняется, есть боль или длительные задержки, "
        "обратись к гинекологу."
    )
