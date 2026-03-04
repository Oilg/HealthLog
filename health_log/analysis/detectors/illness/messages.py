from health_log.analysis.detectors.illness.constants import MIN_DAYS_FOR_TREND, RECENT_DAYS
from health_log.analysis.detectors.illness.features import TrendSnapshot


def build_insufficient_data_summary(days_available: int) -> str:
    return (
        "Недостаточно истории для 60-дневного baseline. "
        f"Доступно дней: {days_available}, требуется: {MIN_DAYS_FOR_TREND}."
    )


def build_summary(snapshot: TrendSnapshot) -> str:
    return (
        f"Тренд за {len(snapshot.selected_days)} дней: пульс в состоянии покоя вырос на "
        f"{snapshot.hr_increase:.1f} уд/мин; HRV изменился на {snapshot.hrv_change_pct:.1f}%; "
        f"подтверждение в последних днях: {snapshot.confirmed_days}/{RECENT_DAYS}. "
        "Это может быть ранним признаком начала простуды или воспалительного процесса."
    )


def build_recommendation() -> str:
    return (
        "Если сигнал держится 2-3 дня подряд и есть симптомы (слабость, ломота, температура), "
        "снизь нагрузку, следи за самочувствием и при необходимости обратись к врачу."
    )
