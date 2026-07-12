"""Celery task queue configuration"""
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "neuroweave",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minute hard limit
    task_soft_time_limit=25 * 60,  # 25 minute soft limit
)

# Day 7: MemoryEvolutionWorker schedule - hourly for active users,
# daily full sweep for everyone else. Manual trigger remains available via
# POST /memory/evolve regardless of this schedule.
celery_app.conf.beat_schedule = {
    "hourly-memory-evolution": {
        "task": "app.workers.tasks.hourly_memory_evolution",
        "schedule": crontab(minute=0),  # top of every hour
    },
    "daily-memory-evolution-sweep": {
        "task": "app.workers.tasks.daily_memory_evolution_sweep",
        "schedule": crontab(hour=3, minute=0),  # 03:00 UTC daily, off-peak
    },
    # Day 8: DreamScheduler ticks - hourly light-touch, daily broader sweep,
    # weekly deep consolidation, plus a frequent idle-triggered check that
    # only picks up users who are actually inactive right now.
    "hourly-dream-tick": {
        "task": "app.workers.tasks.hourly_dream_tick",
        "schedule": crontab(minute=15),  # offset from memory-evolution's :00
    },
    "daily-dream-tick": {
        "task": "app.workers.tasks.daily_dream_tick",
        "schedule": crontab(hour=4, minute=0),  # 04:00 UTC daily
    },
    "weekly-dream-tick": {
        "task": "app.workers.tasks.weekly_dream_tick",
        "schedule": crontab(hour=5, minute=0, day_of_week=0),  # Sunday 05:00 UTC
    },
    "idle-triggered-dream-tick": {
        "task": "app.workers.tasks.idle_triggered_dream_tick",
        "schedule": crontab(minute="*/15"),  # check every 15 minutes for idle users
    },
}
