import sqlalchemy
from sqlalchemy import func

metadata = sqlalchemy.MetaData()

xml_uploads = sqlalchemy.Table(
    "xml_uploads",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
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
    sqlalchemy.UniqueConstraint("provider", "record_fingerprint", name="uq_raw_record_fingerprint"),
)

sleep_analysis = sqlalchemy.Table(
    "sleep_analysis",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("sourceName", "startDate", "endDate", name="uq_sleep_analysis_record"),
)

sleep_duration_goal = sqlalchemy.Table(
    "sleep_duration_goal",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("value", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("sourceName", "startDate", "endDate", name="uq_sleep_duration_goal_record"),
)

heart_rate = sqlalchemy.Table(
    "heart_rate",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("value", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("sourceName", "startDate", "endDate", name="uq_heart_rate_record"),
)

heart_rate_variability = sqlalchemy.Table(
    "heart_rate_variability",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("value", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("sourceName", "startDate", "endDate", name="uq_hrv_record"),
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
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("value", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("sourceName", "startDate", "endDate", name="uq_respiratory_rate_record"),
)

vo_2_max = sqlalchemy.Table(
    "vo_2_max",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("sourceName", sqlalchemy.String, nullable=False),
    sqlalchemy.Column("unit", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("value", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column("creationDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("startDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("endDate", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.UniqueConstraint("sourceName", "startDate", "endDate", name="uq_vo2max_record"),
)

sleep_apnea_events = sqlalchemy.Table(
    "sleep_apnea_events",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, sqlalchemy.Identity(), nullable=False, primary_key=True),
    sqlalchemy.Column("start_time", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("end_time", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("sleep_segment_id", sqlalchemy.Integer, nullable=True),
    sqlalchemy.Column("respiratory_rate_drop", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("heart_rate_spike", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("hrv_change", sqlalchemy.Float, nullable=True),
    sqlalchemy.Column("severity", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("detected_by", sqlalchemy.String, nullable=True),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=func.now(), nullable=False),
    sqlalchemy.UniqueConstraint("start_time", "end_time", "detected_by", name="uq_sleep_apnea_event"),
)

TYPE_TABLE_MAP = {
    "HKCategoryTypeIdentifierSleepAnalysis": sleep_analysis,
    "HKDataTypeSleepDurationGoal": sleep_duration_goal,
    "HKQuantityTypeIdentifierHeartRate": heart_rate,
    "HKQuantityTypeIdentifierRespiratoryRate": respiratory_rate,
    "HKQuantityTypeIdentifierVO2Max": vo_2_max,
}
