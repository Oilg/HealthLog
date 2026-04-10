from __future__ import annotations

_REC_WEIGHT_DYNAMICS = "Наблюдать динамику веса, а не разовые измерения."
_REC_FAT_AND_LEAN = "Контролировать динамику процента жира и безжировой массы."
_REC_STEPS = "Увеличить ежедневную ходьбу и общее число шагов."
_REC_ACTIVITY = "Повысить регулярность умеренной физической активности в течение недели."
_REC_SITTING = "Снизить долю длительного сидения и добавить движение в течение дня."
_REC_STRENGTH = "Добавить силовые тренировки для сохранения или роста безжировой массы."
_REC_NUTRITION = "Пересмотреть калорийность и качество питания."
_REC_WAIST = "Следить за окружностью талии, если такие данные доступны."
_REC_BP = "Проверить артериальное давление."
_REC_GLUCOSE = "Проверить глюкозу крови и/или HbA1c."
_REC_LIPIDS = "Проверить липидный профиль."
_REC_THERAPIST = (
    "Обратиться к терапевту при устойчивом наборе веса, высоком ИМТ "
    "или сочетании лишнего веса с низкой активностью."
)
_REC_ENDOCRINOLOGIST = (
    "Обратиться к эндокринологу, если набор веса выраженный, стойкий "
    "или сочетается с другими симптомами."
)
_REC_CARDIOLOGIST = (
    "Обратиться к кардиологу, если лишний вес сочетается с плохой переносимостью "
    "нагрузки, высоким пульсом, одышкой или давлением."
)

_ALL_RECS = [
    _REC_WEIGHT_DYNAMICS,
    _REC_FAT_AND_LEAN,
    _REC_STEPS,
    _REC_ACTIVITY,
    _REC_SITTING,
    _REC_STRENGTH,
    _REC_NUTRITION,
    _REC_WAIST,
    _REC_BP,
    _REC_GLUCOSE,
    _REC_LIPIDS,
    _REC_THERAPIST,
    _REC_ENDOCRINOLOGIST,
    _REC_CARDIOLOGIST,
]


def build_weight_activity_recommendations(flags: dict[str, bool]) -> list[str]:
    weight_issue = flags.get("weight_issue", False)
    fat_issue = flags.get("fat_issue", False)
    lean_mass_issue = flags.get("lean_mass_issue", False)
    low_activity = flags.get("low_activity", False)
    sedentary = flags.get("sedentary", False)
    waist_available = flags.get("waist_available", False)
    metabolic_risk = flags.get("metabolic_risk", False)
    cardiovascular_symptom_risk = flags.get("cardiovascular_symptom_risk", False)
    persistent_weight_gain = flags.get("persistent_weight_gain", False)

    recs: list[str] = []
    seen: set[str] = set()

    def add(rec: str) -> None:
        if rec not in seen:
            seen.add(rec)
            recs.append(rec)

    if weight_issue or persistent_weight_gain:
        add(_REC_WEIGHT_DYNAMICS)
        add(_REC_NUTRITION)

    if fat_issue or lean_mass_issue:
        add(_REC_FAT_AND_LEAN)

    if lean_mass_issue:
        add(_REC_STRENGTH)

    if low_activity or sedentary:
        add(_REC_STEPS)
        add(_REC_ACTIVITY)

    if sedentary:
        add(_REC_SITTING)

    if fat_issue:
        add(_REC_STRENGTH)
        add(_REC_NUTRITION)

    if waist_available:
        add(_REC_WAIST)

    if metabolic_risk:
        add(_REC_BP)
        add(_REC_GLUCOSE)
        add(_REC_LIPIDS)

    if metabolic_risk or persistent_weight_gain or weight_issue:
        add(_REC_THERAPIST)

    if metabolic_risk and persistent_weight_gain:
        add(_REC_ENDOCRINOLOGIST)

    if cardiovascular_symptom_risk:
        add(_REC_CARDIOLOGIST)
        add(_REC_BP)
        add(_REC_GLUCOSE)
        add(_REC_LIPIDS)

    return recs
