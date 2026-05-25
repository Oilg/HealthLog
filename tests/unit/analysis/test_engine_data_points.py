from health_log.analysis.engine import _build_data_points


class TestBuildDataPoints:
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
        metrics = {"bmi": 32.1}
        points = _build_data_points("metabolic_syndrome_risk", metrics)
        bmi_point = next(p for p in points if p["label"] == "ИМТ")
        assert bmi_point["value"] == "32.1"

    def test_metabolic_syndrome_blood_pressure_format(self):
        metrics = {"sbp": 135.0, "dbp": 87.0}
        points = _build_data_points("metabolic_syndrome_risk", metrics)
        bp_point = next(p for p in points if p["label"] == "Артериальное давление")
        assert "135" in bp_point["value"]
        assert "87" in bp_point["value"]
        assert "мм рт.ст." in bp_point["value"]

    def test_metabolic_syndrome_missing_metrics_skipped(self):
        metrics = {"bmi": 31.0, "steps_per_day": None}
        points = _build_data_points("metabolic_syndrome_risk", metrics)
        labels = [p["label"] for p in points]
        assert "ИМТ" in labels
        assert "Шагов в день" not in labels

    def test_hypertension_risk_blood_pressure(self):
        metrics = {"avg_sbp": 145.0, "avg_dbp": 92.0}
        points = _build_data_points("hypertension_risk", metrics)
        assert len(points) == 1
        assert "145" in points[0]["value"]
        assert "мм рт.ст." in points[0]["value"]

    def test_obesity_risk_bmi(self):
        metrics = {"bmi": 33.5}
        points = _build_data_points("obesity_risk", metrics)
        assert points[0]["label"] == "ИМТ"
        assert "33.5" in points[0]["value"]

    def test_noise_exposure_risk(self):
        metrics = {"max_db_30d": 92.0, "avg_db_7d": 78.5}
        points = _build_data_points("noise_exposure_risk", metrics)
        assert len(points) == 2
        assert "дБ" in points[0]["value"]

    def test_unknown_condition_returns_empty(self):
        points = _build_data_points("unknown_condition", {"some_metric": 42.0})
        assert points == []

    def test_empty_metrics_returns_empty(self):
        points = _build_data_points("metabolic_syndrome_risk", {})
        assert points == []
