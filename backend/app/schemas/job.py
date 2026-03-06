import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.job import JobStatus, SourceType


class CreateJobRequest(BaseModel):
    source_type: SourceType
    source_url: HttpUrl | None = None
    task: str = "transcribe"
    language: str = "auto"
    output_formats: list[str] = Field(default_factory=lambda: ["txt", "srt", "vtt", "json"])
    engine_mode: str = "auto_fallback"
    model: str | None = None
    diarization: bool = False
    diarization_min_speakers: int | None = None
    diarization_max_speakers: int | None = None
    advanced: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task")
    @classmethod
    def validate_task(cls, value: str) -> str:
        if value not in {"transcribe", "translate"}:
            raise ValueError("task must be transcribe or translate")
        return value


class ArtifactResponse(BaseModel):
    id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobResponse(BaseModel):
    id: uuid.UUID
    source_type: SourceType
    source_url: str | None
    original_filename: str | None
    status: JobStatus
    progress: int
    progress_percent: int
    stage: str
    status_detail: str | None
    current_time_sec: float | None
    duration_sec: float | None
    eta_seconds: float | None
    task: str
    language: str
    output_formats: list[str]
    engine_mode: str
    model: str | None
    diarization: bool
    diarization_min_speakers: int | None
    diarization_max_speakers: int | None
    advanced: dict[str, Any]
    metadata_json: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    artifacts: list[ArtifactResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class JobCreatedResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
