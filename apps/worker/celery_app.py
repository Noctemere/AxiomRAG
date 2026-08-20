from celery import Celery

from apps.api.config import get_settings

settings = get_settings()
celery_app = Celery("axiomrag", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    timezone="UTC",
)
