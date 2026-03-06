import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class JobStatus(str, enum.Enum):
    queued = "queued"
    downloading = "downloading"
    processing = "processing"
    finalizing = "finalizing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class SourceType(str, enum.Enum):
    upload = "upload"
    url = "url"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_time_sec: Mapped[float | None] = mapped_column(nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(nullable=True)
    eta_seconds: Mapped[float | None] = mapped_column(nullable=True)

    task: Mapped[str] = mapped_column(String(32), default="transcribe", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    output_formats: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    engine_mode: Mapped[str] = mapped_column(String(32), default="auto_fallback", nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    diarization: Mapped[bool] = mapped_column(default=False, nullable=False)
    diarization_min_speakers: Mapped[int | None] = mapped_column(nullable=True)
    diarization_max_speakers: Mapped[int | None] = mapped_column(nullable=True)

    advanced: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
