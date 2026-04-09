from health_log.analysis.detectors.illness.constants import MIN_VALID_DAYS_FOR_SIGNAL, RECENT_DAYS
from health_log.analysis.detectors.illness.features import TrendSnapshot


def build_insufficient_data_summary(days_available: int) -> str:
    return (
        f"Недостаточно валидных дней (HR≥12 и HRV≥3 точек за сутки). "
        f"Доступно: {days_available}, требуется минимум: {MIN_VALID_DAYS_FOR_SIGNAL}."
    )


def build_summary(snapshot: TrendSnapshot) -> str:
    return (
        f"За последние периоды: пульс в покое в последних {RECENT_DAYS} валидных днях "
        f"относительно baseline выше на {snapshot.recent_rest_hr - snapshot.baseline_rest_hr:.1f} уд/мин; "
        f"HRV ниже относительного baseline; подтверждающих дней из {RECENT_DAYS}: {snapshot.confirmed_days}. "
        "Это может соответствовать изменению физиологии на фоне простуды или воспаления."
    )


def build_recommendation() -> str:
    return (
        "Если сигнал держится несколько дней и есть симптомы (слабость, ломота, температура), "
        "снизь нагрузку и при необходимости обратись к врачу."
    )


def build_data_quality_disclaimer() -> str:
    return (
        "Сигнал отражает изменение физиологических метрик относительно вашей обычной динамики. "
        "Он может быть искажен недосыпом, алкоголем, стрессом, текущей инфекцией, сменой часового пояса "
        "или неполными данными. Сигнал может быть искажен текущей болезнью, стрессом, алкоголем, "
        "сменой часового пояса или нерегулярным сном."
    )
