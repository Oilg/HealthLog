from __future__ import annotations

BODY_FAT_THRESHOLDS_MALE = {"low": 25.0, "medium": 30.0, "high": 35.0}
BODY_FAT_THRESHOLDS_FEMALE = {"low": 32.0, "medium": 37.0, "high": 42.0}

WAIST_THRESHOLDS_MALE = {"low": 94.0, "high": 102.0}
WAIST_THRESHOLDS_FEMALE = {"low": 80.0, "high": 88.0}

BMI_UNDERWEIGHT = 18.5
BMI_UNDERWEIGHT_SEVERE = 17.0
BMI_OVERWEIGHT_LOW = 25.0
BMI_OVERWEIGHT_HIGH = 30.0
BMI_OBESITY_MEDIUM = 35.0
BMI_OBESITY_HIGH = 40.0

MIN_WEIGHT_MEASUREMENTS = 3
MIN_WEIGHT_DAYS = 30
MIN_FAT_MEASUREMENTS = 3
MIN_LEAN_MEASUREMENTS = 3

# Окно и минимум валидных дней для долгосрочных детекторов активности.
# Согласовано со спортивным врачом: Trost 2005, Tudor-Locke 2005.
MIN_ACTIVITY_DAYS = 14  # длина окна
MIN_ACTIVITY_DAYS_VALID = 10  # минимум дней с ненулевой суммой шагов в окне 14 дней

# Для краткосрочных детекторов восстановления.
MIN_ACTIVITY_DAYS_SHORT_WINDOW = 7
MIN_ACTIVITY_DAYS_SHORT_VALID = 4

# Целевые пороги шагов в день ("норма"), возрастно-зависимые.
# Источники: Paluch 2022 (Lancet Public Health), Saint-Maurice 2020 (JAMA).
# Подтверждено эндокринологом и спортивным врачом ДМН.
STEP_TARGET_DEFAULT = 7000  # < 60 лет или возраст неизвестен
STEP_TARGET_SENIOR = 6000  # 60-74 лет
STEP_TARGET_ELDERLY = 4000  # >= 75 лет

# Пороги явной гиподинамии (значительно ниже целевых) — для composite-детекторов
# (cardiometabolic_profile, metabolic_syndrome, cardiovascular_obesity, recovery_obesity,
# obesity_risk-усилитель). Это уровень, при котором сигнал inactive считается сработавшим.
STEP_INACTIVE_DEFAULT = 5000  # < 60 лет или возраст неизвестен
STEP_INACTIVE_SENIOR = 4000  # 60-74 лет
STEP_INACTIVE_ELDERLY = 3000  # >= 75 лет

# Границы возрастных категорий.
AGE_SENIOR_THRESHOLD = 60
AGE_ELDERLY_THRESHOLD = 75

# Severity-ступени для assess_sedentary_lifestyle_risk: пороги ниже целевого,
# относительные. STEP_LOW/MEDIUM/HIGH_SEDENTARY вычисляются от target_threshold_for_age.
# Эти константы остаются для обратной совместимости со старыми тестами и значения по умолчанию.
STEP_LOW_SEDENTARY = 3000
STEP_MEDIUM_SEDENTARY = 5000
STEP_HIGH_SEDENTARY = 7000

# Аналогично для assess_insufficient_activity_risk — пороги "недостаточной активности",
# ступенчатые относительно целевого. Эти значения тоже стали возрастно-зависимыми
# в детекторе и считаются от target_threshold_for_age.
STEP_INSUFFICIENT_HIGH = 4000
STEP_INSUFFICIENT_MEDIUM = 6000
STEP_INSUFFICIENT_LOW = 8000

EXERCISE_TIME_WEEKLY_MIN = 60


def target_threshold_for_age(age: int | None) -> int:
    """Целевой суточный порог шагов с учётом возраста.

    None или возраст < 60 → 7000 (общий взрослый).
    60-74 → 6000.
    >= 75 → 4000.
    Источники: Paluch 2022, Saint-Maurice 2020.
    """
    if age is None or age < AGE_SENIOR_THRESHOLD:
        return STEP_TARGET_DEFAULT
    if age < AGE_ELDERLY_THRESHOLD:
        return STEP_TARGET_SENIOR
    return STEP_TARGET_ELDERLY


def inactive_threshold_for_age(age: int | None) -> int:
    """Порог явной гиподинамии (значительно ниже целевого).

    Применяется в composite-детекторах: при медиане шагов ниже этого порога
    компонент "низкая активность" считается сработавшим.

    None или возраст < 60 → 5000.
    60-74 → 4000.
    >= 75 → 3000.
    """
    if age is None or age < AGE_SENIOR_THRESHOLD:
        return STEP_INACTIVE_DEFAULT
    if age < AGE_ELDERLY_THRESHOLD:
        return STEP_INACTIVE_SENIOR
    return STEP_INACTIVE_ELDERLY
