from health_log.analysis.engine import _build_data_points


class TestBuildDataPoints:
    # ── Метаболизм ──────────────────────────────────────────────────────────

    def test_metabolic_syndrome_with_all_metrics(self):
        metrics = {
            "bmi": 32.1,
            "mass_kg": 95.2,
            "waist_cm": 102.0,
            "sbp": 135.0,
            "dbp": 87.0,
            "steps_per_day": 3200.0,
        }
        points = _build_data_points("metabolic_syndrome_risk", metrics)
        labels = [p["label"] for p in points]
        assert "ИМТ" in labels
        assert "Масса тела" in labels
        assert "Обхват талии" in labels
        assert "Артериальное давление" in labels
        assert "Шагов в день" in labels

    def test_metabolic_syndrome_bmi_format(self):
        points = _build_data_points("metabolic_syndrome_risk", {"bmi": 32.1})
        bmi_point = next(p for p in points if p["label"] == "ИМТ")
        assert bmi_point["value"] == "32.1"

    def test_metabolic_syndrome_blood_pressure_format(self):
        points = _build_data_points("metabolic_syndrome_risk", {"sbp": 135.0, "dbp": 87.0})
        bp = next(p for p in points if p["label"] == "Артериальное давление")
        assert "135" in bp["value"] and "87" in bp["value"] and "мм рт.ст." in bp["value"]

    def test_metabolic_syndrome_missing_metrics_skipped(self):
        points = _build_data_points("metabolic_syndrome_risk", {"bmi": 31.0, "steps_per_day": None})
        labels = [p["label"] for p in points]
        assert "ИМТ" in labels
        assert "Шагов в день" not in labels

    def test_obesity_risk_bmi(self):
        points = _build_data_points("obesity_risk", {"bmi": 33.5})
        assert points[0]["label"] == "ИМТ" and "33.5" in points[0]["value"]

    def test_overweight_risk_bmi(self):
        points = _build_data_points("overweight_risk", {"bmi": 27.5})
        assert points[0]["label"] == "ИМТ"

    def test_abdominal_obesity_waist(self):
        points = _build_data_points("abdominal_obesity_risk", {"waist_cm": 102.0})
        assert (
            points[0]["label"] == "Обхват талии"
            and "102" in points[0]["value"]
            and "см" in points[0]["value"]
        )

    def test_high_body_fat(self):
        points = _build_data_points("high_body_fat_risk", {"body_fat_pct": 32.5})
        assert (
            points[0]["label"] == "Процент жира"
            and "32.5" in points[0]["value"]
            and "%" in points[0]["value"]
        )

    def test_sedentary_lifestyle(self):
        points = _build_data_points("sedentary_lifestyle_risk", {"median_daily_steps": 3500.0})
        assert points[0]["label"] == "Шагов в день" and "3500" in points[0]["value"]

    def test_insufficient_activity(self):
        points = _build_data_points("insufficient_activity_risk", {"median_daily_steps": 6500.0})
        assert points[0]["label"] == "Шагов в день"

    def test_lean_mass_decline(self):
        metrics = {"baseline_lean_kg": 65.5, "recent_lean_kg": 61.2, "decline_pct": 6.5}
        points = _build_data_points("lean_mass_decline_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Безжировая масса (базовая)" in labels
        assert "Безжировая масса (текущая)" in labels
        assert "Снижение" in labels

    def test_weight_trend(self):
        metrics = {"start_weight_kg": 78.5, "end_weight_kg": 86.3, "change_pct": 10.0}
        points = _build_data_points("weight_trend_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Масса тела (начало)" in labels and "Масса тела (сейчас)" in labels

    def test_fat_mass_trend(self):
        metrics = {"fat_mass_start_kg": 22.5, "fat_mass_end_kg": 25.8, "change_pct": 14.7}
        points = _build_data_points("fat_mass_trend_risk", metrics)
        assert any("Жировая масса" in p["label"] for p in points)
        assert any("Изменение" in p["label"] for p in points)

    def test_body_composition_trend(self):
        metrics = {"weight_change_pct": 1.2, "fat_pct_point_change": 3.5, "lean_decline_pct": 5.2}
        points = _build_data_points("body_composition_trend_risk", metrics)
        assert len(points) == 3

    def test_cardiometabolic_profile(self):
        metrics = {"bmi": 28.5, "median_steps_60d": 4200.0}
        points = _build_data_points("cardiometabolic_profile_risk", metrics)
        labels = [p["label"] for p in points]
        assert "ИМТ" in labels
        assert "Шагов/день (медиана, 60 дн.)" in labels

    def test_cardiometabolic_profile_without_steps(self):
        points = _build_data_points(
            "cardiometabolic_profile_risk", {"bmi": 28.5, "median_steps_60d": None}
        )
        assert len(points) == 1
        assert points[0]["label"] == "ИМТ"

    def test_cardiometabolic_profile_extended_fields(self):
        metrics = {
            "bmi": 27.0,
            "median_steps_60d": 5000.0,
            "body_fat_pct": 24.5,
            "vo2max": 38.2,
            "resting_hr": 68.0,
            "sbp": 128.0,
        }
        points = _build_data_points("cardiometabolic_profile_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Процент жира" in labels
        assert "VO₂ max" in labels
        assert "ЧСС в покое" in labels
        assert "Систолическое АД" in labels

    def test_cardiometabolic_profile_extended_fields_none_omitted(self):
        metrics = {
            "bmi": 27.0,
            "median_steps_60d": None,
            "body_fat_pct": None,
            "vo2max": None,
            "resting_hr": None,
            "sbp": None,
        }
        points = _build_data_points("cardiometabolic_profile_risk", metrics)
        labels = [p["label"] for p in points]
        assert labels == ["ИМТ"]

    def test_cardiovascular_obesity(self):
        metrics = {"bmi": 32.0, "median_steps": 3800.0}
        points = _build_data_points("cardiovascular_obesity_risk", metrics)
        labels = [p["label"] for p in points]
        assert "ИМТ" in labels
        assert "Шагов в день" in labels

    def test_fitness_weight_gain(self):
        metrics = {"weight_change_pct": 8.5, "vo2max_decline_pct": 12.0, "walking_hr_delta": 11.0}
        points = _build_data_points("fitness_weight_gain_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Изменение веса" in labels
        assert "Снижение VO₂ max" in labels
        assert "Прирост пульса при ходьбе" in labels

    def test_recovery_obesity(self):
        metrics = {"bmi": 30.5, "median_daily_steps": 3200.0}
        points = _build_data_points("recovery_obesity_risk", metrics)
        labels = [p["label"] for p in points]
        assert "ИМТ" in labels
        assert "Шагов в день" in labels

    # ── Давление ────────────────────────────────────────────────────────────

    def test_hypertension_blood_pressure(self):
        points = _build_data_points("hypertension_risk", {"avg_sbp": 145.0, "avg_dbp": 92.0})
        assert len(points) == 1
        assert (
            "145" in points[0]["value"]
            and "92" in points[0]["value"]
            and "мм рт.ст." in points[0]["value"]
        )

    def test_hypotension_sbp_and_hr(self):
        points = _build_data_points("hypotension_risk", {"avg_sbp": 88.0, "avg_resting_hr": 96.0})
        labels = [p["label"] for p in points]
        assert "Систолическое АД" in labels
        assert "ЧСС в покое" in labels

    # ── Кардио / ритм ───────────────────────────────────────────────────────

    def test_bradycardia(self):
        metrics = {"median_rest_hr": 48.0, "min_rest_hr": 42.0}
        points = _build_data_points("bradycardia_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Мин. ЧСС в покое" in labels and "Медиана ЧСС в покое" in labels
        assert "уд/мин" in points[0]["value"]

    def test_irregular_rhythm(self):
        points = _build_data_points("irregular_rhythm_risk", {"events_90d": 5, "events_30d": 2})
        labels = [p["label"] for p in points]
        assert "Событий за 90 дней" in labels and "Событий за 30 дней" in labels

    def test_atrial_fibrillation(self):
        metrics = {"avg_burden_pct": 3.2, "max_burden_pct": 5.8, "irregular_events_30d": 3}
        points = _build_data_points("atrial_fibrillation_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Средний AFib burden" in labels
        assert "%" in points[0]["value"]

    # ── SpO₂ ────────────────────────────────────────────────────────────────

    def test_low_oxygen_saturation(self):
        metrics = {"min_spo2": 88.5, "median_spo2": 94.2, "count_below_94": 5, "count_below_92": 2}
        points = _build_data_points("low_oxygen_saturation_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Мин. SpO₂" in labels
        assert "Медиана SpO₂" in labels
        assert "%" in points[0]["value"]

    # ── Фитнес ──────────────────────────────────────────────────────────────

    def test_overload_recovery(self):
        metrics = {"baseline_resting_hr": 65.0, "baseline_hrv": 42.5, "baseline_sleep_hours": 7.2}
        points = _build_data_points("overload_recovery_risk", metrics)
        labels = [p["label"] for p in points]
        assert "ЧСС в покое (базовая)" in labels
        assert "HRV (базовая)" in labels
        assert "Сон (базовый)" in labels

    def test_hrr_decline(self):
        metrics = {"baseline_walking_hr_bpm": 82.0, "recent_walking_hr_bpm": 94.0, "rise_bpm": 12.0}
        points = _build_data_points("hrr_decline_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Пульс при ходьбе (базовый)" in labels
        assert "Пульс при ходьбе (текущий)" in labels

    def test_vo2max_decline(self):
        metrics = {"baseline_median_vo2max": 48.2, "recent_vo2max": 42.5, "decline_pct": 11.8}
        points = _build_data_points("vo2max_decline_risk", metrics)
        labels = [p["label"] for p in points]
        assert "VO₂ max (базовый)" in labels
        assert "VO₂ max (текущий)" in labels
        assert "мл/кг/мин" in points[0]["value"]

    def test_walking_tolerance_decline(self):
        metrics = {"baseline_walking_hr": 72.0, "recent_walking_hr": 85.0, "delta_bpm": 13.0}
        points = _build_data_points("walking_tolerance_decline_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Пульс при ходьбе (базовый)" in labels
        assert "Прирост" in labels

    def test_respiratory_function_decline(self):
        metrics = {"rr_delta_pct": 12.5, "spo2_below_94_count": 3, "spo2_below_92_count": 1}
        points = _build_data_points("respiratory_function_decline_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Изменение ЧД" in labels
        assert "Измерений SpO₂ <94%" in labels

    # ── Мобильность ─────────────────────────────────────────────────────────

    def test_fall_risk(self):
        metrics = {
            "steadiness_decline_pct": 15.5,
            "speed_decline_pct": 22.0,
            "step_length_decline_pct": 18.5,
        }
        points = _build_data_points("fall_risk", metrics)
        labels = [p["label"] for p in points]
        assert "Снижение устойчивости" in labels
        assert "%" in points[0]["value"]

    def test_fall_risk_partial_metrics(self):
        points = _build_data_points(
            "fall_risk", {"steadiness_decline_pct": 10.0, "speed_decline_pct": None}
        )
        assert len(points) == 1

    # ── Шум ─────────────────────────────────────────────────────────────────

    def test_noise_exposure(self):
        points = _build_data_points("noise_exposure_risk", {"max_db_30d": 92.0, "avg_db_7d": 78.5})
        assert len(points) == 2
        assert "дБ" in points[0]["value"]

    # ── Edge cases ───────────────────────────────────────────────────────────

    def test_unknown_condition_returns_empty(self):
        assert _build_data_points("unknown_condition", {"some_metric": 42.0}) == []

    def test_empty_metrics_returns_empty(self):
        assert _build_data_points("metabolic_syndrome_risk", {}) == []

    def test_none_values_are_skipped(self):
        points = _build_data_points(
            "bradycardia_risk", {"median_rest_hr": None, "min_rest_hr": 42.0}
        )
        labels = [p["label"] for p in points]
        assert "Медиана ЧСС в покое" not in labels
        assert "Мин. ЧСС в покое" in labels

    # ── Reference values ─────────────────────────────────────────────────────

    def test_bmi_has_reference(self):
        points = _build_data_points("obesity_risk", {"bmi": 33.5})
        assert points[0].get("reference") == "18.5–24.9"

    def test_steps_has_reference(self):
        points = _build_data_points("sedentary_lifestyle_risk", {"median_daily_steps": 3000.0})
        assert points[0].get("reference") == "≥7 500"

    def test_blood_pressure_has_reference(self):
        points = _build_data_points("hypertension_risk", {"avg_sbp": 145.0, "avg_dbp": 92.0})
        assert points[0].get("reference") == "<120/80 мм рт.ст."

    def test_spo2_has_reference(self):
        points = _build_data_points(
            "low_oxygen_saturation_risk",
            {"min_spo2": 88.0, "median_spo2": 93.0, "count_below_94": 4, "count_below_92": 1},
        )
        spo2_points = [p for p in points if "SpO₂" in p["label"] and "Мин" in p["label"]]
        assert spo2_points[0].get("reference") == "≥95%"

    def test_bradycardia_has_reference(self):
        points = _build_data_points(
            "bradycardia_risk", {"min_rest_hr": 48.0, "median_rest_hr": 52.0}
        )
        min_point = next(p for p in points if "Мин." in p["label"])
        assert min_point.get("reference") == "≥60 уд/мин"

    def test_noise_exposure_has_reference(self):
        points = _build_data_points("noise_exposure_risk", {"max_db_30d": 92.0, "avg_db_7d": 78.0})
        assert points[0].get("reference") == "<85 дБ"
        assert points[1].get("reference") == "<70 дБ"

    def test_lean_mass_decline_reference_on_decline_only(self):
        metrics = {"baseline_lean_kg": 65.0, "recent_lean_kg": 61.0, "decline_pct": 6.1}
        points = _build_data_points("lean_mass_decline_risk", metrics)
        decline_point = next(p for p in points if p["label"] == "Снижение")
        assert decline_point.get("reference") == "<3%"
        baseline_point = next(p for p in points if "базовая" in p["label"])
        assert "reference" not in baseline_point

    def test_waist_has_reference(self):
        points = _build_data_points("abdominal_obesity_risk", {"waist_cm": 102.0})
        assert "<94 см" in points[0].get("reference", "")

    def test_irregular_rhythm_events_reference_zero(self):
        points = _build_data_points("irregular_rhythm_risk", {"events_90d": 5, "events_30d": 2})
        assert all(p.get("reference") == "0" for p in points)

    def test_no_reference_for_mass_kg(self):
        points = _build_data_points("metabolic_syndrome_risk", {"mass_kg": 95.0})
        mass_point = next(p for p in points if p["label"] == "Масса тела")
        assert "reference" not in mass_point
