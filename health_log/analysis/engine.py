from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.analysis.detectors import (
    assess_abdominal_obesity_risk,
    assess_atrial_fibrillation_risk,
    assess_atypical_menstrual_bleeding_risk,
    assess_body_composition_trend_risk,
    assess_bradycardia_risk,
    assess_cardiometabolic_profile_risk,
    assess_cardiovascular_obesity_risk,
    assess_fall_risk,
    assess_fat_mass_trend_risk,
    assess_fitness_weight_gain_risk,
    assess_high_body_fat_risk,
    assess_hrr_decline_risk,
    assess_hypertension_risk,
    assess_hypotension_risk,
    assess_illness_onset_risk,
    assess_insufficient_activity_risk,
    assess_irregular_rhythm_risk,
    assess_lean_mass_decline_risk,
    assess_low_oxygen_saturation_risk,
    assess_menstrual_cycle_delay_risk,
    assess_menstrual_cycle_start_forecast,
    assess_menstrual_irregularity_risk,
    assess_menstrual_start_forecast_with_temp,
    assess_metabolic_syndrome_risk,
    assess_noise_exposure_risk,
    assess_obesity_risk,
    assess_overload_recovery_risk,
    assess_overweight_risk,
    assess_ovulation_forecast_with_temp,
    assess_ovulation_window_forecast,
    assess_recovery_obesity_risk,
    assess_respiratory_function_decline_risk,
    assess_sedentary_lifestyle_risk,
    assess_sleep_apnea_risk,
    assess_tachycardia_risk,
    assess_temperature_shift_risk,
    assess_vo2max_decline_risk,
    assess_walking_tolerance_decline_risk,
    assess_weight_trend_risk,
    build_sleep_apnea_event_rows,
)
from health_log.analysis.detectors.illness.constants import ILLNESS_TREND_LOOKBACK_DAYS
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.windows import resolve_window_range
from health_log.repositories.analysis import AnalysisReportsRepository
from health_log.repositories.repository import RecordsRepository
from health_log.repositories.v1 import tables
from health_log.utils import utcnow


class HealthRiskAnalyzer:
    def __init__(self, connection: AsyncConnection, user_id: int):
        self._connection = connection
        self._user_id = user_id
        self._user_sex: str | None = None
        self._records_repo = RecordsRepository(connection)
        self._reports_repo = AnalysisReportsRepository(connection)

    async def _fetch_rows(self, table, start: datetime, end: datetime):
        query = (
            select(table.c.startDate, table.c.value)
            .where(
                and_(
                    table.c.user_id == self._user_id,
                    table.c.startDate >= start,
                    table.c.startDate <= end,
                )
            )
            .order_by(table.c.startDate)
        )
        return (await self._connection.execute(query)).all()

    async def _fetch_sleep_segments(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        query = (
            select(tables.sleep_analysis.c.startDate, tables.sleep_analysis.c.endDate)
            .where(
                and_(
                    tables.sleep_analysis.c.user_id == self._user_id,
                    tables.sleep_analysis.c.startDate <= end,
                    tables.sleep_analysis.c.endDate >= start,
                )
            )
            .order_by(tables.sleep_analysis.c.startDate)
        )
        rows = (await self._connection.execute(query)).all()
        return [(r[0], r[1]) for r in rows]

    async def _fetch_user_sex(self) -> str:
        if self._user_sex is not None:
            return self._user_sex
        query = select(tables.users.c.sex).where(tables.users.c.id == self._user_id)
        sex = (await self._connection.execute(query)).scalar_one_or_none() or "male"
        self._user_sex = str(sex)
        return self._user_sex

    def _build_cardiac_assessments(
        self,
        *,
        heart_rows,
        sleep_segments,
        low_hr_event_rows,
        irregular_rhythm_rows,
        afib_burden_rows,
        window: TimeWindow,
        now: datetime,
    ) -> list[RiskAssessment]:
        low_hr_event_count = len(list(low_hr_event_rows))
        afib_burden_list = list(afib_burden_rows)
        afib_burden_pct: float | None = None
        if afib_burden_list:
            try:
                vals = [float(v) for _, v in afib_burden_list if v is not None]
                afib_burden_pct = max(vals) if vals else None
            except (TypeError, ValueError):
                afib_burden_pct = None

        return [
            assess_bradycardia_risk(
                heart_rows,
                sleep_segments=sleep_segments,
                low_hr_event_count=low_hr_event_count,
                window=window,
            ),
            assess_irregular_rhythm_risk(
                irregular_rhythm_rows,
                afib_burden_pct=afib_burden_pct,
                window=window,
                now=now,
            ),
            assess_atrial_fibrillation_risk(
                afib_burden_list,
                irregular_rhythm_event_rows=irregular_rhythm_rows,
                window=window,
                now=now,
            ),
        ]

    def _build_vitals_assessments(
        self,
        *,
        spo2_rows,
        sleep_segments,
        sbp_rows,
        dbp_rows,
        heart_rows,
        wrist_temp_rows,
        respiratory_rows,
        window: TimeWindow,
        now: datetime,
    ) -> list[RiskAssessment]:
        return [
            assess_low_oxygen_saturation_risk(
                spo2_rows,
                sleep_segments=sleep_segments,
                window=window,
                now=now,
            ),
            assess_hypertension_risk(
                sbp_rows,
                dbp_rows,
                window=window,
            ),
            assess_hypotension_risk(
                sbp_rows,
                dbp_rows=dbp_rows,
                heart_rows=heart_rows,
                window=window,
            ),
            assess_temperature_shift_risk(
                wrist_temp_rows,
                heart_rows=heart_rows,
                respiratory_rows=respiratory_rows,
                window=window,
                now=now,
            ),
        ]

    def _build_fitness_assessments(
        self,
        *,
        vo2max_rows,
        walking_hr_rows,
        sleep_segments,
        heart_rows,
        hrv_rows,
        respiratory_rows,
        spo2_rows,
        step_rows,
        window: TimeWindow,
        now: datetime,
    ) -> list[RiskAssessment]:
        return [
            assess_vo2max_decline_risk(
                vo2max_rows,
                window=window,
                now=now,
            ),
            assess_hrr_decline_risk(
                walking_hr_rows,
                vo2max_rows=vo2max_rows,
                window=window,
                now=now,
            ),
            assess_overload_recovery_risk(
                sleep_segments,
                heart_rows=heart_rows,
                hrv_rows=hrv_rows,
                window=window,
                now=now,
            ),
            assess_walking_tolerance_decline_risk(
                walking_hr_rows,
                step_rows=step_rows,
                window=window,
                now=now,
            ),
            assess_respiratory_function_decline_risk(
                respiratory_rows,
                spo2_rows=spo2_rows,
                walking_hr_rows=walking_hr_rows,
                vo2max_rows=vo2max_rows,
                window=window,
                now=now,
            ),
        ]

    def _build_mobility_assessments(
        self,
        *,
        steadiness_rows,
        walking_speed_rows,
        step_length_rows,
        double_support_rows,
        env_audio_rows,
        headphone_audio_rows,
        window: TimeWindow,
        now: datetime,
    ) -> list[RiskAssessment]:
        return [
            assess_fall_risk(
                steadiness_rows,
                walking_speed_rows=walking_speed_rows,
                step_length_rows=step_length_rows,
                double_support_rows=double_support_rows,
                window=window,
                now=now,
            ),
            assess_noise_exposure_risk(
                env_audio_rows,
                headphone_audio_rows=headphone_audio_rows,
                window=window,
                now=now,
            ),
        ]

    def _build_weight_activity_assessments(
        self,
        *,
        body_mass_rows,
        bmi_rows,
        fat_rows,
        lean_rows,
        waist_rows,
        step_rows,
        exercise_rows,
        vo2max_rows,
        heart_rows,
        sbp_rows,
        dbp_rows,
        sleep_segments,
        hrv_rows,
        walking_hr_rows,
        user_sex: str,
        window: TimeWindow,
        now: datetime,
    ) -> list[RiskAssessment]:
        return [
            assess_overweight_risk(
                body_mass_rows,
                bmi_rows=bmi_rows,
                window=window,
                now=now,
            ),
            assess_obesity_risk(
                body_mass_rows,
                bmi_rows=bmi_rows,
                body_fat_rows=fat_rows,
                step_rows=step_rows,
                window=window,
                now=now,
            ),
            assess_high_body_fat_risk(
                fat_rows,
                sex=user_sex,
                window=window,
                now=now,
            ),
            assess_abdominal_obesity_risk(
                waist_rows,
                sex=user_sex,
                window=window,
                now=now,
            ),
            assess_lean_mass_decline_risk(
                lean_rows,
                window=window,
                now=now,
            ),
            assess_weight_trend_risk(
                body_mass_rows,
                window=window,
                now=now,
            ),
            assess_fat_mass_trend_risk(
                body_mass_rows,
                fat_rows,
                window=window,
                now=now,
            ),
            assess_sedentary_lifestyle_risk(
                step_rows,
                exercise_time_rows=exercise_rows,
                window=window,
                now=now,
            ),
            assess_insufficient_activity_risk(
                step_rows,
                window=window,
                now=now,
            ),
            assess_cardiometabolic_profile_risk(
                body_mass_rows,
                bmi_rows=bmi_rows,
                body_fat_rows=fat_rows,
                waist_rows=waist_rows,
                step_rows=step_rows,
                vo2max_rows=vo2max_rows,
                heart_rows=heart_rows,
                sbp_rows=sbp_rows,
                sex=user_sex,
                window=window,
                now=now,
            ),
            assess_metabolic_syndrome_risk(
                waist_rows,
                sbp_rows=sbp_rows,
                dbp_rows=dbp_rows,
                body_mass_rows=body_mass_rows,
                bmi_rows=bmi_rows,
                step_rows=step_rows,
                sex=user_sex,
                window=window,
                now=now,
            ),
            assess_cardiovascular_obesity_risk(
                body_mass_rows,
                bmi_rows=bmi_rows,
                body_fat_rows=fat_rows,
                waist_rows=waist_rows,
                step_rows=step_rows,
                vo2max_rows=vo2max_rows,
                heart_rows=heart_rows,
                sbp_rows=sbp_rows,
                sex=user_sex,
                window=window,
                now=now,
            ),
            assess_fitness_weight_gain_risk(
                body_mass_rows,
                vo2max_rows=vo2max_rows,
                walking_hr_rows=walking_hr_rows,
                window=window,
                now=now,
            ),
            assess_recovery_obesity_risk(
                body_mass_rows,
                bmi_rows=bmi_rows,
                body_fat_rows=fat_rows,
                step_rows=step_rows,
                sleep_segments=sleep_segments,
                hrv_rows=hrv_rows,
                heart_rows=heart_rows,
                window=window,
                now=now,
            ),
            assess_body_composition_trend_risk(
                body_mass_rows,
                fat_rows,
                lean_mass_rows=lean_rows,
                window=window,
                now=now,
            ),
        ]

    def _build_menstrual_assessments(
        self,
        *,
        menstrual_rows,
        intermenstrual_rows,
        wrist_temp_rows,
        window: TimeWindow,
        now: datetime,
    ) -> list[RiskAssessment]:
        return [
            assess_menstrual_cycle_start_forecast(menstrual_rows, window=window, now=now),
            assess_menstrual_cycle_delay_risk(menstrual_rows, window=window, now=now),
            assess_ovulation_window_forecast(menstrual_rows, window=window, now=now),
            assess_menstrual_irregularity_risk(menstrual_rows, window=window, now=now),
            assess_atypical_menstrual_bleeding_risk(
                intermenstrual_event_rows=intermenstrual_rows,
                menstrual_rows=menstrual_rows,
                window=window,
                now=now,
            ),
            assess_menstrual_start_forecast_with_temp(
                menstrual_rows,
                wrist_temp_rows=wrist_temp_rows,
                window=window,
                now=now,
            ),
            assess_ovulation_forecast_with_temp(
                menstrual_rows,
                wrist_temp_rows=wrist_temp_rows,
                window=window,
                now=now,
            ),
        ]

    async def analyze_window(self, window: TimeWindow, now: datetime | None = None) -> dict[str, object]:
        now = now or utcnow()
        start, end = resolve_window_range(window, now)

        illness_start = end - timedelta(days=ILLNESS_TREND_LOOKBACK_DAYS)
        cycle_start = end - timedelta(days=180)
        extended_start = end - timedelta(days=180)
        fitness_baseline_start = end - timedelta(days=74)
        temperature_start = end - timedelta(days=16)
        mobility_start = end - timedelta(days=90)

        user_sex = await self._fetch_user_sex()

        # Window-bounded: used by window-specific detectors (sleep_apnea, tachycardia, bradycardia).
        heart_rows = await self._fetch_rows(tables.heart_rate, start, end)
        hrv_rows = await self._fetch_rows(tables.heart_rate_variability, start, end)
        respiratory_rows = await self._fetch_rows(tables.respiratory_rate, start, end)
        sleep_segments = await self._fetch_sleep_segments(start, end)

        # Extended: needed by baseline+recent detectors regardless of window size.
        heart_rows_180d = await self._fetch_rows(tables.heart_rate, extended_start, end)
        hrv_rows_74d = await self._fetch_rows(tables.heart_rate_variability, fitness_baseline_start, end)
        respiratory_rows_74d = await self._fetch_rows(tables.respiratory_rate, fitness_baseline_start, end)
        sleep_segments_74d = await self._fetch_sleep_segments(fitness_baseline_start, end)
        wrist_temp_rows_16d = await self._fetch_rows(tables.apple_sleeping_wrist_temperature, temperature_start, end)
        wrist_temp_rows = await self._fetch_rows(tables.apple_sleeping_wrist_temperature, cycle_start, end)

        vo2max_rows = await self._fetch_rows(tables.vo_2_max, extended_start, end)

        illness_heart_rows = await self._fetch_rows(tables.heart_rate, illness_start, end)
        illness_hrv_rows = await self._fetch_rows(tables.heart_rate_variability, illness_start, end)
        illness_respiratory_rows = await self._fetch_rows(tables.respiratory_rate, illness_start, end)
        illness_sleep_segments = await self._fetch_sleep_segments(illness_start, end)

        spo2_rows = await self._fetch_rows(tables.oxygen_saturation, end - timedelta(days=30), end)
        sbp_rows = await self._fetch_rows(tables.blood_pressure_systolic, start, end)
        dbp_rows = await self._fetch_rows(tables.blood_pressure_diastolic, start, end)
        walking_hr_rows = await self._fetch_rows(tables.walking_heart_rate_average, extended_start, end)
        walking_speed_rows = await self._fetch_rows(tables.walking_speed, mobility_start, end)
        step_length_rows = await self._fetch_rows(tables.walking_step_length, mobility_start, end)
        double_support_rows = await self._fetch_rows(tables.walking_double_support_percentage, mobility_start, end)
        steadiness_rows = await self._fetch_rows(tables.walking_steadiness, mobility_start, end)
        env_audio_rows = await self._fetch_rows(tables.environmental_audio_exposure, start, end)
        headphone_audio_rows = await self._fetch_rows(tables.headphone_audio_exposure, start, end)
        body_mass_rows = await self._fetch_rows(tables.body_mass, extended_start, end)
        bmi_rows = await self._fetch_rows(tables.body_mass_index, extended_start, end)
        fat_rows = await self._fetch_rows(tables.body_fat_percentage, extended_start, end)
        lean_rows = await self._fetch_rows(tables.lean_body_mass, extended_start, end)
        waist_rows = await self._fetch_rows(tables.waist_circumference, extended_start, end)
        step_rows = await self._fetch_rows(tables.step_count, extended_start, end)
        exercise_rows = await self._fetch_rows(tables.apple_exercise_time, extended_start, end)
        afib_burden_rows = await self._fetch_rows(tables.apple_afib_burden, extended_start, end)
        low_hr_event_rows = await self._fetch_rows(tables.low_heart_rate_event, extended_start, end)
        irregular_rhythm_rows = await self._fetch_rows(tables.irregular_heart_rhythm_event, extended_start, end)

        menstrual_rows = []
        intermenstrual_rows = []
        if user_sex == "female":
            menstrual_rows = await self._fetch_rows(tables.menstrual_flow, cycle_start, end)
            intermenstrual_rows = await self._fetch_rows(tables.intermenstrual_bleeding, extended_start, end)

        sleep_apnea_result = assess_sleep_apnea_risk(
            respiratory_rows,
            heart_rows,
            hrv_rows,
            sleep_segments=sleep_segments,
            window=window,
        )
        tachycardia_result = assess_tachycardia_risk(
            heart_rows,
            sleep_segments=sleep_segments,
            window=window,
        )
        illness_onset_result = assess_illness_onset_risk(
            illness_heart_rows,
            illness_hrv_rows,
            respiratory_rows=illness_respiratory_rows,
            sleep_rows=illness_sleep_segments,
            window=window,
        )

        cardiac_results = self._build_cardiac_assessments(
            heart_rows=heart_rows,
            sleep_segments=sleep_segments,
            low_hr_event_rows=low_hr_event_rows,
            irregular_rhythm_rows=irregular_rhythm_rows,
            afib_burden_rows=afib_burden_rows,
            window=window,
            now=now,
        )
        vitals_results = self._build_vitals_assessments(
            spo2_rows=spo2_rows,
            sleep_segments=sleep_segments,
            sbp_rows=sbp_rows,
            dbp_rows=dbp_rows,
            heart_rows=heart_rows_180d,
            wrist_temp_rows=wrist_temp_rows_16d,
            respiratory_rows=respiratory_rows_74d,
            window=window,
            now=now,
        )
        fitness_results = self._build_fitness_assessments(
            vo2max_rows=vo2max_rows,
            walking_hr_rows=walking_hr_rows,
            sleep_segments=sleep_segments_74d,
            heart_rows=heart_rows_180d,
            hrv_rows=hrv_rows_74d,
            respiratory_rows=respiratory_rows_74d,
            spo2_rows=spo2_rows,
            step_rows=step_rows,
            window=window,
            now=now,
        )
        mobility_results = self._build_mobility_assessments(
            steadiness_rows=steadiness_rows,
            walking_speed_rows=walking_speed_rows,
            step_length_rows=step_length_rows,
            double_support_rows=double_support_rows,
            env_audio_rows=env_audio_rows,
            headphone_audio_rows=headphone_audio_rows,
            window=window,
            now=now,
        )
        weight_activity_results = self._build_weight_activity_assessments(
            body_mass_rows=body_mass_rows,
            bmi_rows=bmi_rows,
            fat_rows=fat_rows,
            lean_rows=lean_rows,
            waist_rows=waist_rows,
            step_rows=step_rows,
            exercise_rows=exercise_rows,
            vo2max_rows=vo2max_rows,
            heart_rows=heart_rows_180d,
            sbp_rows=sbp_rows,
            dbp_rows=dbp_rows,
            sleep_segments=sleep_segments_74d,
            hrv_rows=hrv_rows_74d,
            walking_hr_rows=walking_hr_rows,
            user_sex=user_sex,
            window=window,
            now=now,
        )

        menstrual_assessments: list[RiskAssessment] = []
        if user_sex == "female":
            menstrual_assessments = self._build_menstrual_assessments(
                menstrual_rows=menstrual_rows,
                intermenstrual_rows=intermenstrual_rows,
                wrist_temp_rows=wrist_temp_rows,
                window=window,
                now=now,
            )

        inserted_events = 0
        if window == TimeWindow.NIGHT:
            events = build_sleep_apnea_event_rows(
                respiratory_rows,
                heart_rows,
                hrv_rows,
                sleep_segments=sleep_segments,
            )
            inserted_events = await self._records_repo.insert_sleep_apnea_events(self._user_id, events)

        assessments = [
            sleep_apnea_result,
            tachycardia_result,
            illness_onset_result,
            *cardiac_results,
            *vitals_results,
            *fitness_results,
            *mobility_results,
            *weight_activity_results,
            *menstrual_assessments,
        ]

        active_risks = [
            {
                "condition": a.condition,
                "severity": a.severity,
                "confidence": round(a.confidence, 4),
                "interpretation": _CONDITION_LABELS.get(a.condition, a.condition),
            }
            for a in assessments
            if a.score > 0
        ]

        try:
            if self._connection is not None:
                await self._reports_repo.save_report(
                    user_id=self._user_id,
                    analyzed_at=now,
                    period_from=start,
                    period_to=end,
                    window=window.value,
                    risks=active_risks,
                )
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Не удалось сохранить отчёт об анализе (user=%d, window=%s)",
                self._user_id,
                window.value,
                exc_info=True,
            )

        return {
            "window": window,
            "start": start,
            "end": end,
            "assessments": assessments,
            "inserted_sleep_apnea_events": inserted_events,
        }

    async def analyze_all_windows(self, now: datetime | None = None) -> dict[TimeWindow, dict[str, object]]:
        return {
            window: await self.analyze_window(window, now=now)
            for window in (TimeWindow.NIGHT, TimeWindow.WEEK, TimeWindow.MONTH)
        }


_CONDITION_LABELS: dict[str, str] = {
    "sleep_apnea_risk": "Подозрение на апноэ сна",
    "tachycardia_risk": "Подозрение на тахикардию",
    "illness_onset_risk": "Подозрение на начало простуды/воспалительного процесса",
    "menstrual_cycle_start_forecast": "Прогноз: скорое начало менструации",
    "menstrual_cycle_delay_risk": "Прогноз: возможная задержка менструации",
    "ovulation_window_forecast": "Прогноз: окно вероятной овуляции",
    "bradycardia_risk": "Подозрение на брадикардию",
    "irregular_rhythm_risk": "Подозрение на нерегулярный сердечный ритм",
    "atrial_fibrillation_risk": "Подозрение на фибрилляцию предсердий",
    "low_oxygen_saturation_risk": "Подозрение на снижение кислорода в крови",
    "hypertension_risk": "Подозрение на повышенное артериальное давление",
    "hypotension_risk": "Подозрение на пониженное артериальное давление",
    "temperature_shift_risk": "Подозрение на температурный сдвиг / лихорадку",
    "vo2max_decline_risk": "Снижение кардиофитнеса по VO2 max",
    "hrr_decline_risk": "Подозрение на ухудшение восстановления после нагрузки",
    "overload_recovery_risk": "Подозрение на перегрузку / недосып / недовосстановление",
    "walking_tolerance_decline_risk": "Подозрение на ухудшение переносимости нагрузки",
    "respiratory_function_decline_risk": "Подозрение на ухудшение дыхательной функции",
    "fall_risk": "Подозрение на ухудшение устойчивости ходьбы / риск падений",
    "noise_exposure_risk": "Подозрение на вредное шумовое воздействие",
    "menstrual_irregularity_risk": "Подозрение на нерегулярность менструального цикла",
    "atypical_menstrual_bleeding_risk": "Подозрение на атипичные менструальные кровотечения",
    "menstrual_start_forecast_with_temp": "Уточнённый прогноз менструации по температуре",
    "ovulation_forecast_with_temp": "Уточнённый прогноз овуляции по температуре",
    "overweight_risk": "Подозрение на избыточную массу тела",
    "obesity_risk": "Подозрение на ожирение",
    "high_body_fat_risk": "Подозрение на повышенный процент жира в организме",
    "abdominal_obesity_risk": "Подозрение на абдоминальное ожирение",
    "lean_mass_decline_risk": "Подозрение на снижение безжировой массы тела",
    "weight_trend_risk": "Подозрение на неблагоприятную динамику веса",
    "fat_mass_trend_risk": "Подозрение на неблагоприятную динамику жировой массы",
    "sedentary_lifestyle_risk": "Подозрение на малоподвижный образ жизни",
    "insufficient_activity_risk": "Подозрение на недостаточный объём повседневной активности",
    "cardiometabolic_profile_risk": "Подозрение на ухудшение кардиометаболического профиля",
    "metabolic_syndrome_risk": "Подозрение на повышенный риск метаболического синдрома",
    "cardiovascular_obesity_risk": "Подозрение на повышенный сердечно-сосудистый риск на фоне массы тела",
    "fitness_weight_gain_risk": "Подозрение на ухудшение физической формы на фоне набора веса",
    "recovery_obesity_risk": "Подозрение на неэффективное восстановление на фоне избытка массы",
    "body_composition_trend_risk": "Подозрение на неблагоприятный тренд состава тела",
}


def serialize_assessment(assessment: RiskAssessment) -> dict[str, object]:
    condition_label = _CONDITION_LABELS.get(assessment.condition, assessment.condition)
    final_message = (
        f"{condition_label}. Уровень риска: {assessment.score:.2f}, "
        f"достоверность сигнала: {assessment.confidence:.2f}. "
        f"{assessment.interpretation} {assessment.recommendation}"
    )

    result: dict[str, object] = {
        "condition": assessment.condition,
        "подозреваемое_состояние": condition_label,
        "window": assessment.window.value,
        "score": assessment.score,
        "confidence": assessment.confidence,
        "уровень_риска": assessment.score,
        "достоверность_сигнала": assessment.confidence,
        "severity": assessment.severity,
        "interpretation": assessment.interpretation,
        "summary": assessment.summary,
        "recommendation": assessment.recommendation,
        "итоговое_сообщение": final_message,
        "clinical_safety_note": assessment.clinical_safety_note,
        "supporting_metrics": assessment.supporting_metrics,
        "created_at": assessment.created_at.isoformat(),
    }
    if assessment.lifestyle_recommendations:
        result["lifestyle_recommendations"] = assessment.lifestyle_recommendations
    return result
