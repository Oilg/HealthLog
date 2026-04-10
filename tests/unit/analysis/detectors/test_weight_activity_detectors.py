from __future__ import annotations

from datetime import datetime, timedelta

from health_log.analysis.detectors.weight_activity import (
    assess_abdominal_obesity_risk,
    assess_body_composition_trend_risk,
    assess_cardiometabolic_profile_risk,
    assess_cardiovascular_obesity_risk,
    assess_fat_mass_trend_risk,
    assess_fitness_weight_gain_risk,
    assess_high_body_fat_risk,
    assess_insufficient_activity_risk,
    assess_lean_mass_decline_risk,
    assess_metabolic_syndrome_risk,
    assess_obesity_risk,
    assess_overweight_risk,
    assess_recovery_obesity_risk,
    assess_sedentary_lifestyle_risk,
    assess_weight_trend_risk,
    build_weight_activity_recommendations,
)
from health_log.analysis.models import TimeWindow

_WINDOW = TimeWindow.MONTH
_NOW = datetime(2026, 3, 15, 12, 0, 0)


def _ts(days_ago: float) -> datetime:
    return _NOW - timedelta(days=days_ago)


class TestBuildWeightActivityRecommendations:
    def test_empty_flags_returns_empty(self):
        recs = build_weight_activity_recommendations({})
        assert recs == []

    def test_weight_issue_includes_weight_and_nutrition(self):
        recs = build_weight_activity_recommendations({"weight_issue": True})
        text = " ".join(recs)
        assert "вес" in text.lower() or "питани" in text.lower()

    def test_no_duplicates(self):
        recs = build_weight_activity_recommendations({
            "weight_issue": True,
            "fat_issue": True,
            "lean_mass_issue": True,
            "low_activity": True,
            "sedentary": True,
            "metabolic_risk": True,
            "cardiovascular_symptom_risk": True,
            "persistent_weight_gain": True,
        })
        assert len(recs) == len(set(recs))

    def test_cardiovascular_risk_includes_cardiologist(self):
        recs = build_weight_activity_recommendations({"cardiovascular_symptom_risk": True})
        assert any("кардиолог" in r.lower() for r in recs)

    def test_metabolic_risk_includes_lab_checks(self):
        recs = build_weight_activity_recommendations({"metabolic_risk": True})
        combined = " ".join(recs).lower()
        assert "глюкоз" in combined or "lipid" in combined or "давлени" in combined


class TestOverweightRisk:
    def test_no_data_returns_unknown(self):
        result = assess_overweight_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_normal_bmi_returns_none(self):
        rows = [(_ts(i * 5), 70.0) for i in range(5)]
        result = assess_overweight_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_bmi_26_returns_low(self):
        rows = [(_ts(i * 5), 84.0) for i in range(5)]
        result = assess_overweight_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert result.severity == "low"
        assert result.score > 0

    def test_lifestyle_recommendations_present(self):
        rows = [(_ts(i * 5), 84.0) for i in range(5)]
        result = assess_overweight_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert isinstance(result.lifestyle_recommendations, list)
        if result.severity != "none":
            assert len(result.lifestyle_recommendations) > 0

    def test_obesity_category_deferred(self):
        rows = [(_ts(i * 5), 100.0) for i in range(5)]
        result = assess_overweight_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert "obesity_risk" in result.summary


class TestObesityRisk:
    def test_no_data_returns_unknown(self):
        result = assess_obesity_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_normal_bmi_returns_none(self):
        rows = [(_ts(i * 5), 70.0) for i in range(5)]
        result = assess_obesity_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_bmi_31_returns_low(self):
        rows = [(_ts(i * 5), 100.0) for i in range(5)]
        result = assess_obesity_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert result.severity in {"low", "medium"}

    def test_bmi_37_returns_medium(self):
        rows = [(_ts(i * 5), 120.0) for i in range(5)]
        result = assess_obesity_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert result.severity in {"medium", "high"}

    def test_bmi_42_returns_high(self):
        rows = [(_ts(i * 5), 136.0) for i in range(5)]
        result = assess_obesity_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert result.severity == "high"

    def test_lifestyle_recommendations_populated(self):
        rows = [(_ts(i * 5), 100.0) for i in range(5)]
        result = assess_obesity_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert len(result.lifestyle_recommendations) > 0


class TestHighBodyFatRisk:
    def test_insufficient_returns_unknown(self):
        result = assess_high_body_fat_risk([], sex="male", window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_normal_male_returns_none(self):
        rows = [(_ts(i * 5), 18.0) for i in range(5)]
        result = assess_high_body_fat_risk(rows, sex="male", window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_high_male_returns_signal(self):
        rows = [(_ts(i * 5), 28.0) for i in range(5)]
        result = assess_high_body_fat_risk(rows, sex="male", window=_WINDOW, now=_NOW)
        assert result.severity in {"low", "medium", "high"}
        assert result.score > 0

    def test_female_thresholds_differ(self):
        rows = [(_ts(i * 5), 28.0) for i in range(5)]
        male_result = assess_high_body_fat_risk(rows, sex="male", window=_WINDOW, now=_NOW)
        female_result = assess_high_body_fat_risk(rows, sex="female", window=_WINDOW, now=_NOW)
        assert male_result.severity in {"low", "medium", "high"}
        assert female_result.severity == "none"


class TestAbdominalObesityRisk:
    def test_no_data_returns_unknown(self):
        result = assess_abdominal_obesity_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_normal_male_returns_none(self):
        rows = [(_ts(i), 88.0) for i in range(5)]
        result = assess_abdominal_obesity_risk(rows, sex="male", window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_borderline_male_returns_low(self):
        rows = [(_ts(i), 95.0) for i in range(5)]
        result = assess_abdominal_obesity_risk(rows, sex="male", window=_WINDOW, now=_NOW)
        assert result.severity == "low"

    def test_high_male_returns_high(self):
        rows = [(_ts(i), 105.0) for i in range(5)]
        result = assess_abdominal_obesity_risk(rows, sex="male", window=_WINDOW, now=_NOW)
        assert result.severity == "high"

    def test_female_threshold_differs(self):
        rows = [(_ts(i), 85.0) for i in range(5)]
        male_result = assess_abdominal_obesity_risk(rows, sex="male", window=_WINDOW, now=_NOW)
        female_result = assess_abdominal_obesity_risk(rows, sex="female", window=_WINDOW, now=_NOW)
        assert male_result.severity == "none"
        assert female_result.severity in {"low", "high"}


class TestLeanMassDeclineRisk:
    def test_insufficient_returns_unknown(self):
        result = assess_lean_mass_decline_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_stable_lean_mass_returns_none(self):
        rows = [(_ts(i * 10), 55.0) for i in range(6)]
        result = assess_lean_mass_decline_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_3_pct_decline_returns_low(self):
        rows = [(_ts(i * 10), 55.0) for i in range(3)] + [(_ts(i * 5), 53.3) for i in range(1, 4)]
        result = assess_lean_mass_decline_risk(rows, window=_WINDOW, now=_NOW)
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}


class TestWeightTrendRisk:
    def test_insufficient_returns_unknown(self):
        result = assess_weight_trend_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_stable_weight_returns_none(self):
        rows = [(_ts(i), 75.0) for i in range(60)]
        result = assess_weight_trend_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_2_pct_gain_30d_returns_low(self):
        rows = [(_ts(i + 14), 75.0) for i in range(30)] + [(_ts(i), 76.6) for i in range(14)]
        result = assess_weight_trend_risk(rows, window=_WINDOW, now=_NOW)
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}


class TestSedentaryLifestyleRisk:
    def test_insufficient_returns_unknown(self):
        result = assess_sedentary_lifestyle_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_high_steps_returns_none(self):
        rows = [(_ts(i), 8500.0) for i in range(15)]
        result = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_very_low_steps_returns_high(self):
        rows = [(_ts(i), 2000.0) for i in range(15)]
        result = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "high"

    def test_exercise_time_low_boosts_score(self):
        rows = [(_ts(i), 4500.0) for i in range(15)]
        exercise = [(_ts(i), 5.0) for i in range(15)]
        without = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW)
        with_ex = assess_sedentary_lifestyle_risk(rows, exercise_time_rows=exercise, window=_WINDOW, now=_NOW)
        assert with_ex.score >= without.score

    def test_lifestyle_recommendations_present(self):
        rows = [(_ts(i), 2000.0) for i in range(15)]
        result = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW)
        assert len(result.lifestyle_recommendations) > 0


class TestInsufficientActivityRisk:
    def test_sufficient_steps_returns_none(self):
        rows = [(_ts(i), 9000.0) for i in range(15)]
        result = assess_insufficient_activity_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_low_steps_returns_signal(self):
        rows = [(_ts(i), 3500.0) for i in range(15)]
        result = assess_insufficient_activity_risk(rows, window=_WINDOW, now=_NOW)
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}


class TestCardiometabolicProfileRisk:
    def test_no_data_returns_unknown(self):
        result = assess_cardiometabolic_profile_risk(window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_good_profile_returns_low_score(self):
        mass = [(_ts(i), 70.0) for i in range(10)]
        steps = [(_ts(i), 9000.0) for i in range(10)]
        result = assess_cardiometabolic_profile_risk(
            body_mass_rows=mass, height_m=1.80, step_rows=steps, window=_WINDOW, now=_NOW
        )
        assert result.score < 0.5

    def test_bad_profile_returns_higher_score(self):
        mass = [(_ts(i), 110.0) for i in range(10)]
        steps = [(_ts(i), 1500.0) for i in range(10)]
        hr = [(_ts(i), 90.0) for i in range(10)]
        result = assess_cardiometabolic_profile_risk(
            body_mass_rows=mass,
            height_m=1.75,
            step_rows=steps,
            heart_rows=hr,
            window=_WINDOW,
            now=_NOW,
        )
        assert result.score >= 0.4

    def test_lifestyle_recommendations_present_for_bad_profile(self):
        mass = [(_ts(i), 110.0) for i in range(10)]
        steps = [(_ts(i), 1500.0) for i in range(10)]
        result = assess_cardiometabolic_profile_risk(
            body_mass_rows=mass, height_m=1.75, step_rows=steps, window=_WINDOW, now=_NOW
        )
        if result.severity not in {"none", "unknown"}:
            assert len(result.lifestyle_recommendations) > 0


class TestMetabolicSyndromeRisk:
    def test_no_data_returns_unknown(self):
        result = assess_metabolic_syndrome_risk(window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_single_criterion_returns_none(self):
        steps = [(_ts(i), 3000.0) for i in range(15)]
        result = assess_metabolic_syndrome_risk(step_rows=steps, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_two_criteria_returns_low(self):
        waist = [(_ts(i), 96.0) for i in range(5)]
        steps = [(_ts(i), 3000.0) for i in range(15)]
        result = assess_metabolic_syndrome_risk(
            waist_rows=waist, step_rows=steps, sex="male", window=_WINDOW, now=_NOW
        )
        assert result.severity in {"low", "medium", "high"}

    def test_four_criteria_returns_high(self):
        waist = [(_ts(i), 106.0) for i in range(5)]
        sbp = [(_ts(i * 3), 145.0) for i in range(7)]
        dbp = [(_ts(i * 3), 92.0) for i in range(7)]
        steps = [(_ts(i), 2000.0) for i in range(15)]
        mass = [(_ts(i * 5), 110.0) for i in range(5)]
        result = assess_metabolic_syndrome_risk(
            waist_rows=waist,
            sbp_rows=sbp,
            dbp_rows=dbp,
            step_rows=steps,
            body_mass_rows=mass,
            height_m=1.75,
            sex="male",
            window=_WINDOW,
            now=_NOW,
        )
        assert result.severity in {"medium", "high"}

    def test_no_labs_note_in_interpretation(self):
        waist = [(_ts(i), 96.0) for i in range(5)]
        steps = [(_ts(i), 3000.0) for i in range(15)]
        result = assess_metabolic_syndrome_risk(
            waist_rows=waist, step_rows=steps, sex="male", window=_WINDOW, now=_NOW
        )
        if result.severity != "none":
            assert "предварительная" in result.interpretation.lower()


class TestCardiovascularObesityRisk:
    def test_no_overweight_returns_none(self):
        mass = [(_ts(i * 5), 60.0) for i in range(5)]
        steps = [(_ts(i), 3000.0) for i in range(15)]
        result = assess_cardiovascular_obesity_risk(
            body_mass_rows=mass, height_m=1.80, step_rows=steps, window=_WINDOW, now=_NOW
        )
        assert result.severity == "none"

    def test_overweight_and_inactive_returns_low(self):
        mass = [(_ts(i * 5), 90.0) for i in range(5)]
        steps = [(_ts(i), 3500.0) for i in range(15)]
        result = assess_cardiovascular_obesity_risk(
            body_mass_rows=mass, height_m=1.80, step_rows=steps, window=_WINDOW, now=_NOW
        )
        assert result.severity in {"low", "medium", "high"}
        assert result.score > 0

    def test_additional_risk_factors_boost_severity(self):
        mass = [(_ts(i * 5), 110.0) for i in range(5)]
        steps = [(_ts(i), 2000.0) for i in range(15)]
        hr = [(_ts(i), 85.0) for i in range(15)]
        sbp = [(_ts(i * 3), 150.0) for i in range(7)]
        without = assess_cardiovascular_obesity_risk(
            body_mass_rows=mass, height_m=1.75, step_rows=steps, window=_WINDOW, now=_NOW
        )
        with_factors = assess_cardiovascular_obesity_risk(
            body_mass_rows=mass,
            height_m=1.75,
            step_rows=steps,
            heart_rows=hr,
            sbp_rows=sbp,
            window=_WINDOW,
            now=_NOW,
        )
        assert with_factors.score >= without.score


class TestFitnessWeightGainRisk:
    def test_insufficient_returns_unknown(self):
        result = assess_fitness_weight_gain_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_stable_weight_good_vo2max_returns_none(self):
        mass = [(_ts(i), 75.0) for i in range(90)]
        vo2 = [(_ts(i * 15), 42.0) for i in range(6)]
        result = assess_fitness_weight_gain_risk(mass, vo2, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_weight_up_vo2_down_returns_signal(self):
        mass = [(_ts(i + 14), 75.0) for i in range(76)] + [(_ts(i), 79.0) for i in range(14)]
        vo2 = [(_ts(i * 15 + 45), 42.0) for i in range(4)] + [(_ts(5), 37.0)]
        result = assess_fitness_weight_gain_risk(mass, vo2, window=_WINDOW, now=_NOW)
        assert result.score > 0


class TestRecoveryObesityRisk:
    def test_no_overweight_returns_none(self):
        mass = [(_ts(i * 5), 60.0) for i in range(5)]
        steps = [(_ts(i), 7000.0) for i in range(15)]
        result = assess_recovery_obesity_risk(
            body_mass_rows=mass, height_m=1.80, step_rows=steps, window=_WINDOW, now=_NOW
        )
        assert result.severity == "none"

    def test_overweight_inactive_with_hrv_drop_returns_signal(self):
        mass = [(_ts(i * 5), 90.0) for i in range(5)]
        steps = [(_ts(i), 3000.0) for i in range(15)]
        hrv_baseline = [(_ts(i + 15), 55.0) for i in range(45)]
        hrv_recent = [(_ts(i), 42.0) for i in range(14)]
        result = assess_recovery_obesity_risk(
            body_mass_rows=mass,
            height_m=1.80,
            step_rows=steps,
            hrv_rows=hrv_baseline + hrv_recent,
            window=_WINDOW,
            now=_NOW,
        )
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}


class TestBodyCompositionTrendRisk:
    def test_insufficient_returns_unknown(self):
        result = assess_body_composition_trend_risk([], [], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_stable_composition_returns_none(self):
        mass = [(_ts(i * 3), 75.0) for i in range(30)]
        fat = [(_ts(i * 3), 20.0) for i in range(30)]
        result = assess_body_composition_trend_risk(mass, fat, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_rising_fat_falling_lean_returns_signal(self):
        mass = [(_ts(i * 3), 75.0) for i in range(30)]
        fat_early = [(_ts(i * 3 + 14), 18.0) for i in range(25)]
        fat_recent = [(_ts(i), 22.5) for i in range(14)]
        lean_early = [(_ts(i * 3 + 14), 60.0) for i in range(25)]
        lean_recent = [(_ts(i), 57.0) for i in range(14)]
        result = assess_body_composition_trend_risk(
            mass, fat_early + fat_recent, lean_mass_rows=lean_early + lean_recent, window=_WINDOW, now=_NOW
        )
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}

    def test_lifestyle_recommendations_populated(self):
        mass = [(_ts(i * 3), 75.0) for i in range(30)]
        fat_early = [(_ts(i * 3 + 14), 18.0) for i in range(25)]
        fat_recent = [(_ts(i), 22.5) for i in range(14)]
        lean_early = [(_ts(i * 3 + 14), 60.0) for i in range(25)]
        lean_recent = [(_ts(i), 57.0) for i in range(14)]
        result = assess_body_composition_trend_risk(
            mass, fat_early + fat_recent, lean_mass_rows=lean_early + lean_recent, window=_WINDOW, now=_NOW
        )
        if result.severity not in {"none", "unknown"}:
            assert len(result.lifestyle_recommendations) > 0


class TestRiskAssessmentNewFields:
    def test_supporting_metrics_default_empty_dict(self):
        rows = [(_ts(i * 5), 84.0) for i in range(5)]
        result = assess_overweight_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert isinstance(result.supporting_metrics, dict)

    def test_lifestyle_recommendations_default_empty_list(self):
        rows = [(_ts(i * 5), 70.0) for i in range(5)]
        result = assess_overweight_risk(rows, height_m=1.80, window=_WINDOW, now=_NOW)
        assert isinstance(result.lifestyle_recommendations, list)

    def test_fat_mass_trend_requires_both_series(self):
        mass = [(_ts(i * 3), 75.0) for i in range(30)]
        result = assess_fat_mass_trend_risk(mass, [], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"
