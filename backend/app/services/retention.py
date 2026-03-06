from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.artifact import Artifact
from app.models.job import Job


def prune_expired_jobs() -> int:
    cutoff = datetime.utcnow() - timedelta(days=settings.job_retention_days)
    removed = 0

    with SessionLocal() as db:
        jobs = db.scalars(select(Job).where(Job.created_at < cutoff)).all()
        for job in jobs:
            artifacts = db.scalars(select(Artifact).where(Artifact.job_id == job.id)).all()
            for artifact in artifacts:
                try:
                    Path(artifact.file_path).unlink(missing_ok=True)
                except Exception:
                    pass
                db.delete(artifact)

            job_dir = Path(settings.upload_tmp_root) / str(job.id)
            shutil.rmtree(job_dir, ignore_errors=True)
            db.delete(job)
            removed += 1

        db.commit()

    return removed
