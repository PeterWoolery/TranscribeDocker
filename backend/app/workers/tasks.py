from __future__ import annotations

import mimetypes
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from celery import shared_task
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.artifact import Artifact
from app.models.job import Job, JobStatus, SourceType
from app.services.artifacts import write_outputs
from app.services.downloader import copy_upload_to_job, download_from_url
from app.services.retention import prune_expired_jobs


def _format_time(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    value = max(0, int(seconds))
    hours = value // 3600
    minutes = (value % 3600) // 60
    secs = value % 60
    if hours > 0:
        return f"{hours:02}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"


def _compute_percent(current_time_sec: float | None, duration_sec: float | None, base: int, ceiling: int) -> int:
    if duration_sec is None or duration_sec <= 0 or current_time_sec is None:
        return base
    ratio = min(max(current_time_sec / duration_sec, 0.0), 1.0)
    return min(ceiling, max(base, int(base + (ceiling - base) * ratio)))


def _set_status(
    db,
    job: Job,
    status: JobStatus,
    progress_percent: int,
    stage: str,
    status_detail: str,
    current_time_sec: float | None = None,
    duration_sec: float | None = None,
    eta_seconds: float | None = None,
    error: str | None = None,
    force: bool = False,
    throttle_state: dict | None = None,
):
    now = time.monotonic()
    clamped_progress = max(0, min(100, int(progress_percent)))

    if throttle_state is not None and not force:
        last_progress = int(throttle_state.get("last_progress", -1))
        last_emit_ts = float(throttle_state.get("last_emit_ts", 0.0))
        enough_delta = abs(clamped_progress - last_progress) >= 1
        enough_time = (now - last_emit_ts) >= 1.5
        if not enough_delta and not enough_time:
            return

    job.status = status
    job.progress = clamped_progress
    job.progress_percent = clamped_progress
    job.stage = stage
    job.status_detail = status_detail
    job.current_time_sec = current_time_sec
    job.duration_sec = duration_sec
    job.eta_seconds = eta_seconds
    job.error_message = error
    if status in {JobStatus.completed, JobStatus.failed, JobStatus.cancelled}:
        job.completed_at = datetime.utcnow()

    db.add(job)
    db.commit()

    if throttle_state is not None:
        throttle_state["last_progress"] = clamped_progress
        throttle_state["last_emit_ts"] = now


def _store_debug_media(db, job: Job, media_path: Path, out_dir: Path) -> None:
    if not media_path.exists():
        return

    suffix = media_path.suffix or ".bin"
    debug_path = out_dir / f"debug-source{suffix}"
    shutil.copy2(media_path, debug_path)
    content_type = mimetypes.guess_type(str(debug_path))[0] or "application/octet-stream"
    db.add(
        Artifact(
            job_id=job.id,
            file_name=debug_path.name,
            file_path=str(debug_path),
            content_type=content_type,
            size_bytes=debug_path.stat().st_size,
        )
    )
    db.commit()


@shared_task(bind=True)
def process_job_task(self, job_id: str):
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.id == uuid.UUID(job_id)))
        if not job:
            return

        throttle_state = {"last_progress": -1, "last_emit_ts": 0.0}
        job_dir = Path(settings.upload_tmp_root) / str(job.id)
        out_dir = Path(settings.artifact_root) / str(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        media_path: Path | None = None

        try:
            _set_status(
                db,
                job,
                JobStatus.downloading,
                8,
                "preparing_input",
                "Preparing input",
                force=True,
                throttle_state=throttle_state,
            )

            if job.source_type == SourceType.url:
                _set_status(
                    db,
                    job,
                    JobStatus.downloading,
                    12,
                    "downloading_source",
                    "Downloading source",
                    force=True,
                    throttle_state=throttle_state,
                )
                media_path = download_from_url(job.source_url or "", job_dir)
            else:
                staged_upload = Path(settings.upload_tmp_root) / f"_incoming_{job.id}_{job.original_filename}"
                if not staged_upload.exists():
                    raise RuntimeError("Uploaded source was not found")
                media_path = copy_upload_to_job(staged_upload, job_dir)
                staged_upload.unlink(missing_ok=True)

            _set_status(
                db,
                job,
                JobStatus.processing,
                20,
                "probing_media",
                "Analyzing media",
                force=True,
                throttle_state=throttle_state,
            )
            from app.services.transcription import probe_duration_seconds, run_transcription

            duration_sec = probe_duration_seconds(media_path)

            progress_hint = max(job.progress_percent, 25)
            current_hint: float | None = None
            eta_hint: float | None = None
            eta_state = {"wall_start": None, "media_start": None}

            def on_local_progress(segment_end_sec: float) -> None:
                nonlocal progress_hint, current_hint, eta_hint
                current_hint = segment_end_sec
                progress_hint = _compute_percent(segment_end_sec, duration_sec, 25, 94)
                detail = "Transcribing"
                now_wall = time.monotonic()
                if eta_state["wall_start"] is None:
                    eta_state["wall_start"] = now_wall
                    eta_state["media_start"] = segment_end_sec
                elapsed_wall = max(0.001, now_wall - float(eta_state["wall_start"]))
                media_delta = max(0.0, segment_end_sec - float(eta_state["media_start"]))
                if duration_sec is not None and media_delta > 1.0:
                    media_rate = media_delta / elapsed_wall
                    remaining_media = max(0.0, duration_sec - segment_end_sec)
                    if media_rate > 0:
                        eta_hint = remaining_media / media_rate
                if duration_sec is not None:
                    detail = f"Transcribing {_format_time(segment_end_sec)} / {_format_time(duration_sec)}"
                if eta_hint is not None:
                    detail = f"{detail} (ETA {_format_time(eta_hint)})"
                _set_status(
                    db,
                    job,
                    JobStatus.processing,
                    progress_hint,
                    "transcribing_local",
                    detail,
                    current_time_sec=segment_end_sec,
                    duration_sec=duration_sec,
                    eta_seconds=eta_hint,
                    throttle_state=throttle_state,
                )

            if job.engine_mode == "openai_api":
                _set_status(
                    db,
                    job,
                    JobStatus.processing,
                    35,
                    "transcribing_openai",
                    "Uploading audio to OpenAI",
                    duration_sec=duration_sec,
                    eta_seconds=None,
                    force=True,
                    throttle_state=throttle_state,
                )
                _set_status(
                    db,
                    job,
                    JobStatus.processing,
                    55,
                    "transcribing_openai",
                    "Waiting for OpenAI transcription result",
                    duration_sec=duration_sec,
                    eta_seconds=None,
                    force=True,
                    throttle_state=throttle_state,
                )
                segments = run_transcription(
                    media_path=media_path,
                    task=job.task,
                    language=job.language,
                    engine_mode=job.engine_mode,
                    model=job.model,
                    advanced=job.advanced,
                )
            else:
                _set_status(
                    db,
                    job,
                    JobStatus.processing,
                    25,
                    "transcribing_local",
                    "Transcribing",
                    duration_sec=duration_sec,
                    eta_seconds=None,
                    force=True,
                    throttle_state=throttle_state,
                )

                def on_fallback() -> None:
                    _set_status(
                        db,
                        job,
                        JobStatus.processing,
                        max(progress_hint, 55),
                        "transcribing_openai",
                        "Local transcription failed, falling back to OpenAI",
                        current_time_sec=current_hint,
                        duration_sec=duration_sec,
                        eta_seconds=None,
                        force=True,
                        throttle_state=throttle_state,
                    )

                segments = run_transcription(
                    media_path=media_path,
                    task=job.task,
                    language=job.language,
                    engine_mode=job.engine_mode,
                    model=job.model,
                    advanced=job.advanced,
                    progress_callback=on_local_progress,
                    fallback_callback=on_fallback,
                )

            _set_status(
                db,
                job,
                JobStatus.finalizing,
                96,
                "finalizing_outputs",
                "Writing transcript outputs",
                current_time_sec=current_hint,
                duration_sec=duration_sec,
                eta_seconds=None,
                force=True,
                throttle_state=throttle_state,
            )
            files = write_outputs(
                base_dir=out_dir,
                base_name="transcript",
                segments=segments,
                formats=job.output_formats,
            )

            for f in files:
                content_type = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                db.add(
                    Artifact(
                        job_id=job.id,
                        file_name=f.name,
                        file_path=str(f),
                        content_type=content_type,
                        size_bytes=f.stat().st_size,
                    )
                )

            db.commit()
            _set_status(
                db,
                job,
                JobStatus.completed,
                100,
                "completed",
                "Completed",
                current_time_sec=duration_sec,
                duration_sec=duration_sec,
                eta_seconds=0,
                force=True,
                throttle_state=throttle_state,
            )

        except Exception as exc:
            if media_path is not None:
                _store_debug_media(db, job, media_path, out_dir)
            _set_status(
                db,
                job,
                JobStatus.failed,
                max(job.progress_percent, 1),
                "failed",
                "Failed",
                current_time_sec=job.current_time_sec,
                duration_sec=job.duration_sec,
                eta_seconds=job.eta_seconds,
                error=str(exc),
                force=True,
                throttle_state=throttle_state,
            )
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)


@shared_task
def prune_jobs_task():
    return prune_expired_jobs()
