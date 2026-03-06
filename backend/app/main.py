from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import router
from app.core.config import settings
from app.db.session import Base, engine

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(router)


def ensure_job_progress_columns() -> None:
    statements = [
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stage VARCHAR(64) NOT NULL DEFAULT 'queued'",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS status_detail TEXT",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS current_time_sec DOUBLE PRECISION",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS duration_sec DOUBLE PRECISION",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS eta_seconds DOUBLE PRECISION",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


@app.on_event("startup")
def on_startup() -> None:
    Path(settings.artifact_root).mkdir(parents=True, exist_ok=True)
    Path(settings.upload_tmp_root).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    ensure_job_progress_columns()
