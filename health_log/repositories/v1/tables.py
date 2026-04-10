import sqlalchemy
from sqlalchemy import func

metadata = sqlalchemy.MetaData()

users = sqlalchemy.Table(
    "users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("first_name", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("last_name", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("sex", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("email", sqlalchemy.String, nullable=False, unique=True),
    sqlalchemy.Column("phone", sqlalchemy.String, nullable=False, unique=True),
    sqlalchemy.Column("password_hash", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("is_active", sqlalchemy.Boolean, nullable=False, server_default=sqlalchemy.true()),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=func.now(), nullable=False),
    sqlalchemy.Column(
        "updated_at",
        sqlalchemy.DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
    sqlalchemy.CheckConstraint("sex in ('male', 'female')", name="ck_users_sex"),
)

auth_tokens = sqlalchemy.Table(
    "auth_tokens",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("token_hash", sqlalchemy.String(64), nullable=False, unique=True),
    sqlalchemy.Column("token_type", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("expires_at", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("revoked_at", sqlalchemy.DateTime, nullable=True),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=func.now(), nullable=False),
)

xml_uploads = sqlalchemy.Table(
    "xml_uploads",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("provider", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("data_format", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("filename", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("sha256", sqlalchemy.String(64), nullable=False, unique=True),
    sqlalchemy.Column("raw_xml", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=func.now(), nullable=False),
)

raw_health_records = sqlalchemy.Table(
    "raw_health_records",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("upload_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("xml_uploads.id"), nullable=False),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("provider", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("data_format", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("record_type", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=True),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=True),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=True),
    sqlalchemy.Column("record_fingerprint", sqlalchemy.String(64), nullable=False),
    sqlalchemy.Column("payload", sqlalchemy.JSON, nullable=False),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=func.now(), nullable=False),
    sqlalchemy.UniqueConstraint("user_id", "provider", "record_fingerprint", name="uq_raw_record_fingerprint"),
)

sleep_analysis = sqlalchemy.Table(
    "sleep_analysis",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name="uq_sleep_analysis_record"),
)

sleep_duration_goal = sqlalchemy.Table(
    "sleep_duration_goal",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("value", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint(
        "user_id",
        "sourceName",
        "startDate",
        "endDate",
        name="uq_sleep_duration_goal_record",
    ),
)

heart_rate = sqlalchemy.Table(
    "heart_rate",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("value", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name="uq_heart_rate_record"),
)

heart_rate_variability = sqlalchemy.Table(
    "heart_rate_variability",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("value", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name="uq_hrv_record"),
)

instantaneous_bpm = sqlalchemy.Table(
    "heart_rate_variability_bpm",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column(
        "hr_variability_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("heart_rate_variability.id"),
        nullable=False,
    ),
    sqlalchemy.Column("bpm", sqlalchemy.Integer, nullable=False),
    sqlalchemy.Column("time", sqlalchemy.String, nullable=False),
    sqlalchemy.UniqueConstraint("hr_variability_id", "time", name="uq_hrv_bpm_record"),
)

respiratory_rate = sqlalchemy.Table(
    "respiratory_rate",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("value", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name="uq_respiratory_rate_record"),
)

vo_2_max = sqlalchemy.Table(
    "vo_2_max",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("value", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name="uq_vo2max_record"),
)

menstrual_flow = sqlalchemy.Table(
    "menstrual_flow",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("value", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name="uq_menstrual_flow_record"),
)

def _quantity_table(name: str, unique_name: str) -> sqlalchemy.Table:
    return sqlalchemy.Table(
        name,
        metadata,
        sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
        sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
        sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
        sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
        sqlalchemy.Column("value", sqlalchemy.Text, nullable=True),
        sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
        sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
        sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
        sqlalchemy.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name=unique_name),
    )


def _category_table(name: str, unique_name: str) -> sqlalchemy.Table:
    return sqlalchemy.Table(
        name,
        metadata,
        sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
        sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
        sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
        sqlalchemy.Column("value", sqlalchemy.String, nullable=True),
        sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
        sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
        sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
        sqlalchemy.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name=unique_name),
    )


oxygen_saturation = _quantity_table("oxygen_saturation", "uq_oxygen_saturation_record")
blood_pressure_systolic = _quantity_table("blood_pressure_systolic", "uq_blood_pressure_systolic_record")
blood_pressure_diastolic = _quantity_table("blood_pressure_diastolic", "uq_blood_pressure_diastolic_record")
apple_sleeping_wrist_temperature = _quantity_table(
    "apple_sleeping_wrist_temperature", "uq_apple_sleeping_wrist_temperature_record"
)
walking_heart_rate_average = _quantity_table("walking_heart_rate_average", "uq_walking_heart_rate_average_record")
walking_speed = _quantity_table("walking_speed", "uq_walking_speed_record")
walking_step_length = _quantity_table("walking_step_length", "uq_walking_step_length_record")
walking_double_support_percentage = _quantity_table(
    "walking_double_support_percentage", "uq_walking_double_support_percentage_record"
)
walking_steadiness = _quantity_table("walking_steadiness", "uq_walking_steadiness_record")
environmental_audio_exposure = _quantity_table("environmental_audio_exposure", "uq_environmental_audio_exposure_record")
headphone_audio_exposure = _quantity_table("headphone_audio_exposure", "uq_headphone_audio_exposure_record")
body_mass = _quantity_table("body_mass", "uq_body_mass_record")
body_mass_index = _quantity_table("body_mass_index", "uq_body_mass_index_record")
body_fat_percentage = _quantity_table("body_fat_percentage", "uq_body_fat_percentage_record")
lean_body_mass = _quantity_table("lean_body_mass", "uq_lean_body_mass_record")
waist_circumference = _quantity_table("waist_circumference", "uq_waist_circumference_record")
step_count = _quantity_table("step_count", "uq_step_count_record")
apple_exercise_time = _quantity_table("apple_exercise_time", "uq_apple_exercise_time_record")
apple_afib_burden = _quantity_table("apple_afib_burden", "uq_apple_afib_burden_record")

low_heart_rate_event = _category_table("low_heart_rate_event", "uq_low_heart_rate_event_record")
irregular_heart_rhythm_event = _category_table(
    "irregular_heart_rhythm_event", "uq_irregular_heart_rhythm_event_record"
)
intermenstrual_bleeding = _category_table("intermenstrual_bleeding", "uq_intermenstrual_bleeding_record")

sleep_apnea_events = sqlalchemy.Table(
    "sleep_apnea_events",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False),
    sqlalchemy.Column("start_time", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("end_time", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("sleep_segment_id", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("respiratory_rate_drop", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("heart_rate_spike", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("hrv_change", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("severity", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("detected_by", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("point_count", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("support_level", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("confidence", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("baseline_rr", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("baseline_hr", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("baseline_hrv", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("sleep_hours_context", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=func.now(), nullable=False),
    sqlalchemy.UniqueConstraint("user_id", "start_time", "end_time", "detected_by", name="uq_sleep_apnea_event"),
)

TYPE_TABLE_MAP = {
    "HKCategoryTypeIdentifierSleepAnalysis": sleep_analysis,
    "HKDataTypeSleepDurationGoal": sleep_duration_goal,
    "HKQuantityTypeIdentifierHeartRate": heart_rate,
    "HKQuantityTypeIdentifierRespiratoryRate": respiratory_rate,
    "HKQuantityTypeIdentifierVO2Max": vo_2_max,
    "HKCategoryTypeIdentifierMenstrualFlow": menstrual_flow,
    "HKQuantityTypeIdentifierOxygenSaturation": oxygen_saturation,
    "HKQuantityTypeIdentifierBloodPressureSystolic": blood_pressure_systolic,
    "HKQuantityTypeIdentifierBloodPressureDiastolic": blood_pressure_diastolic,
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": apple_sleeping_wrist_temperature,
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": walking_heart_rate_average,
    "HKQuantityTypeIdentifierWalkingSpeed": walking_speed,
    "HKQuantityTypeIdentifierWalkingStepLength": walking_step_length,
    "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage": walking_double_support_percentage,
    "HKQuantityTypeIdentifierWalkingSteadiness": walking_steadiness,
    "HKQuantityTypeIdentifierEnvironmentalAudioExposure": environmental_audio_exposure,
    "HKQuantityTypeIdentifierHeadphoneAudioExposure": headphone_audio_exposure,
    "HKQuantityTypeIdentifierBodyMass": body_mass,
    "HKQuantityTypeIdentifierBodyMassIndex": body_mass_index,
    "HKQuantityTypeIdentifierBodyFatPercentage": body_fat_percentage,
    "HKQuantityTypeIdentifierLeanBodyMass": lean_body_mass,
    "HKQuantityTypeIdentifierWaistCircumference": waist_circumference,
    "HKQuantityTypeIdentifierStepCount": step_count,
    "HKQuantityTypeIdentifierAppleExerciseTime": apple_exercise_time,
    "HKQuantityTypeIdentifierAppleAFibBurden": apple_afib_burden,
    "HKCategoryTypeIdentifierLowHeartRateEvent": low_heart_rate_event,
    "HKCategoryTypeIdentifierIrregularHeartRhythmEvent": irregular_heart_rhythm_event,
    "HKCategoryTypeIdentifierIntermenstrualBleeding": intermenstrual_bleeding,
}
