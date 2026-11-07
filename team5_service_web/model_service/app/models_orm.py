from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, func

from app.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prediction_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    source = Column(String(20), nullable=False, index=True)
    model_version = Column(String(50), nullable=False)

    gender = Column(String(10), nullable=False)
    age = Column(Float, nullable=False)
    hypertension = Column(Integer, nullable=False)
    heart_disease = Column(Integer, nullable=False)
    ever_married = Column(String(5), nullable=False)
    work_type = Column(String(20), nullable=False)
    residence_type = Column(String(10), nullable=False)
    avg_glucose_level = Column(Float, nullable=False)
    bmi = Column(Float, nullable=True)
    smoking_status = Column(String(20), nullable=False)

    prediction = Column(Integer, nullable=False)
    prediction_proba = Column(Float, nullable=False)


class IngestionStat(Base):
    __tablename__ = "ingestion_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    source_filename = Column(String(255), nullable=False)
    criticality = Column(String(10), nullable=False, index=True)
    total_rows = Column(Integer, nullable=False)
    invalid_rows = Column(Integer, nullable=False)
    invalid_percentage = Column(Float, nullable=False)
    missing_column = Column(Boolean, nullable=False, default=False)


class IngestionErrorType(Base):
    __tablename__ = "ingestion_error_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ingestion_stat_id = Column(Integer, ForeignKey("ingestion_stats.id"), nullable=False, index=True)
    error_type = Column(String(50), nullable=False)
    error_count = Column(Integer, nullable=False)
