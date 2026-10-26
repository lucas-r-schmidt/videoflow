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
})
