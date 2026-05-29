from health_log.analysis.detectors.illness.constants import (
    MIN_VALID_DAYS_FOR_SIGNAL,
    RECENT_DAYS,
    TEMP_ELEVATED_DELTA_THRESHOLD,
    TEMP_NOTABLY_LOW_THRESHOLD,
    TEMP_STABLE_DELTA_THRESHOLD,
)
from health_log.analysis.detectors.illness.features import TrendSnapshot


def build_insufficient_data_summary(days_available: int) -> str:
    return (
        f"Недостаточно валидных дней (HR≥12 и HRV≥3 точек за сутки). "
        f"Доступно: {days_available}, требуется минимум: {MIN_VALID_DAYS_FOR_SIGNAL}."
    )


def build_summary(snapshot: TrendSnapshot) -> str:
    hr_delta = snapshot.recent_rest_hr - snapshot.baseline_rest_hr
    base = (
        f"За последние периоды: пульс в покое в последних {RECENT_DAYS} валидных днях "
        f"относительно baseline выше на {hr_delta:.1f} уд/мин; "
        f"HRV ниже относительного baseline; подтверждающих дней из {RECENT_DAYS}: {snapshot.confirmed_days}."
    )
    if (
        snapshot.wrist_temp_delta is not None
        and snapshot.wrist_temp_delta > TEMP_ELEVATED_DELTA_THRESHOLD
    ):
        base += f" Температура запястья во сне выше личного baseline на {snapshot.wrist_temp_delta:+.2f}°C."
        base += " Это может соответствовать изменению физиологии на фоне простуды или воспаления."
    elif (
        snapshot.wrist_temp_delta is not None
        and snapshot.wrist_temp_delta <= TEMP_NOTABLY_LOW_THRESHOLD
    ):
        # «Заметно ниже» и «стабильна» дают одинаковый эффект для оценки
        # (scoring применяет TEMP_STABLE_PENALTY ко всему диапазону delta <= 0).
        # Слово «аналогично» явно сигнализирует пользователю об эквивалентности
        # эффекта, чтобы фраза не имплицировала более сильное подавление.
        base += (
            f" Температура запястья во сне заметно ниже личного baseline "
            f"({snapshot.wrist_temp_delta:+.2f}°C) — аналогично снижает вероятность "
            f"воспалительного процесса."
        )
    elif (
        snapshot.wrist_temp_delta is not None
        and snapshot.wrist_temp_delta <= TEMP_STABLE_DELTA_THRESHOLD
    ):
        base += (
            f" Температура запястья во сне стабильна "
            f"({snapshot.wrist_temp_delta:+.2f}°C к baseline) — это снижает вероятность воспалительного процесса."
        )
    elif snapshot.wrist_temp_delta is not None:
        base += (
            f" Температура запястья во сне незначительно отклоняется от baseline "
            f"({snapshot.wrist_temp_delta:+.2f}°C) и не влияет на оценку."
        )
    else:
        base += " Это может соответствовать изменению физиологии на фоне простуды или воспаления."
    return base


def build_recommendation() -> str:
    return (
        "Если сигнал держится несколько дней и есть симптомы (слабость, ломота, температура), "
        "снизь нагрузку и при необходимости обратись к врачу."
    )


def build_data_quality_disclaimer() -> str:
    return (
        "Сигнал отражает изменение физиологических метрик относительно вашей обычной динамики. "
        "Он может быть искажен недосыпом, алкоголем, стрессом, текущей инфекцией, сменой часового пояса, "
        "нерегулярным сном или неполными данными."
    )
