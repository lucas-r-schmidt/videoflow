from celery import Celery
from config import settings

celery_app = Celery(
    "video_automation",
    broker=settings.CELERY_BROKER_URL,
    include=["workers.pipeline_task"],
)

celery_app.config_from_object({
    "result_backend":                    settings.CELERY_RESULT_BACKEND,
    "task_serializer":                   "json",
    "result_serializer":                 "json",
    "accept_content":                    ["json"],
    "task_track_started":                True,
    "task_acks_late":                    True,      # só confirma após conclusão
    "worker_prefetch_multiplier":        1,         # 1 task por vez — econômico em RAM
    "task_soft_time_limit":              1800,      # 30 min soft limit
    "task_time_limit":                   2100,      # 35 min hard limit
    "broker_connection_retry_on_startup": True,
    "task_default_queue":                "celery",
    "beat_schedule": {
        "channel-watcher-every-6-hours": {
            "task": "workers.pipeline_task.watch_channels_task",
            "schedule": 6 * 3600.0, # A cada 6 horas
        },
        "cleanup-orphan-files-daily": {
            "task": "workers.pipeline_task.cleanup_old_files_task",
            "schedule": 12 * 3600.0, # A cada 12 horas
        },
    },
})
