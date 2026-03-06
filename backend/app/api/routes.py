from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.artifact import Artifact
from app.models.job import Job, JobStatus, SourceType
from app.schemas.job import ArtifactResponse, CreateJobRequest, JobCreatedResponse, JobResponse
from app.services.options import get_options
from app.workers.tasks import process_job_task

router = APIRouter(prefix="/api/v1", tags=["transcription"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/options")
def options():
    return get_options()


@router.post("/jobs", response_model=JobCreatedResponse)
async def create_job(
    source_type: SourceType = Form(...),
    source_url: str | None = Form(None),
    task: str = Form("transcribe"),
    language: str = Form("auto"),
    output_formats: str = Form("txt,srt,vtt,json"),
    engine_mode: str = Form(settings.default_engine_mode),
    model: str | None = Form(None),
    diarization: bool = Form(False),
    diarization_min_speakers: int | None = Form(None),
    diarization_max_speakers: int | None = Form(None),
    advanced: str | None = Form(None),
    metadata: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    advanced_obj = json.loads(advanced) if advanced else {}
    metadata_obj = json.loads(metadata) if metadata else {}
    formats = [f.strip() for f in output_formats.split(",") if f.strip()]

    payload = CreateJobRequest(
        source_type=source_type,
        source_url=source_url,
        task=task,
        language=language,
        output_formats=formats,
        engine_mode=engine_mode,
        model=model,
        diarization=diarization,
        diarization_min_speakers=diarization_min_speakers,
        diarization_max_speakers=diarization_max_speakers,
        advanced=advanced_obj,
        metadata=metadata_obj,
    )

    if payload.source_type == SourceType.upload and not file:
        raise HTTPException(status_code=400, detail="file is required for upload source_type")
    if payload.source_type == SourceType.url and not payload.source_url:
        raise HTTPException(status_code=400, detail="source_url is required for url source_type")

    job = Job(
        source_type=payload.source_type,
        source_url=str(payload.source_url) if payload.source_url else None,
        original_filename=file.filename if file else None,
        status=JobStatus.queued,
        progress=0,
        progress_percent=0,
        stage="queued",
        status_detail="Queued",
        eta_seconds=None,
        task=payload.task,
        language=payload.language,
        output_formats=payload.output_formats,
        engine_mode=payload.engine_mode,
        model=payload.model,
        diarization=payload.diarization,
        diarization_min_speakers=payload.diarization_min_speakers,
        diarization_max_speakers=payload.diarization_max_speakers,
        advanced=payload.advanced,
        metadata_json=payload.metadata,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if file:
        staged_upload = Path(settings.upload_tmp_root) / f"_incoming_{job.id}_{file.filename}"
        staged_upload.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        if len(content) > settings.max_upload_bytes:
            db.delete(job)
            db.commit()
            raise HTTPException(status_code=413, detail="File exceeds max upload size")
        staged_upload.write_bytes(content)

    async_result = process_job_task.delay(str(job.id))
    job.celery_task_id = async_result.id
    db.add(job)
    db.commit()

    return JobCreatedResponse(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.scalar(select(Job).where(Job.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    artifacts = db.scalars(select(Artifact).where(Artifact.job_id == job.id)).all()
    payload = JobResponse.model_validate(job).model_dump()
    payload["artifacts"] = [ArtifactResponse.model_validate(a).model_dump() for a in artifacts]
    return payload


@router.get("/jobs/{job_id}/artifacts", response_model=list[ArtifactResponse])
def list_artifacts(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.scalar(select(Job).where(Job.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    artifacts = db.scalars(select(Artifact).where(Artifact.job_id == job.id)).all()
    return artifacts


@router.get("/jobs/{job_id}/artifacts/{artifact_id}/download")
def download_artifact(job_id: uuid.UUID, artifact_id: uuid.UUID, db: Session = Depends(get_db)):
    artifact = db.scalar(select(Artifact).where(Artifact.id == artifact_id, Artifact.job_id == job_id))
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path=artifact.file_path, media_type=artifact.content_type, filename=artifact.file_name)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.scalar(select(Job).where(Job.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    artifacts = db.scalars(select(Artifact).where(Artifact.job_id == job.id)).all()
    for artifact in artifacts:
        Path(artifact.file_path).unlink(missing_ok=True)
        db.delete(artifact)

    shutil.rmtree(Path(settings.upload_tmp_root) / str(job.id), ignore_errors=True)
    shutil.rmtree(Path(settings.artifact_root) / str(job.id), ignore_errors=True)

    db.delete(job)
    db.commit()
    return {"deleted": str(job_id)}
