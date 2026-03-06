from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "transcribedocker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_track_started=True,
    timezone="UTC",
    beat_schedule={
        "prune-expired-jobs": {
            "task": "app.workers.tasks.prune_jobs_task",
            "schedule": 60 * 60,
        }
    },
)

celery_app.autodiscover_tasks(["app.workers"])
