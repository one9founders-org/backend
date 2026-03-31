import logging

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.core.management import call_command
from django_apscheduler.jobstores import DjangoJobStore, register_events

logger = logging.getLogger(__name__)


def run_news_pipeline_job():
    """Job to trigger the news automation pipeline every 2 hours."""
    logger.info("Scheduler: Starting scheduled news pipeline run...")
    try:
        # Call the management command we created earlier
        call_command("run_news_pipeline", limit=10, publish_limit=5)
        logger.info("Scheduler: News pipeline run completed successfully.")
    except Exception as e:
        logger.error(f"Scheduler: Error running news pipeline: {e}")


def start():
    """Initialize and start the background scheduler."""
    # Prevent multiple schedulers in dev with auto-reload or multi-worker production
    import os

    if settings.DEBUG and os.environ.get("RUN_MAIN") != "true":
        return

    scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
    scheduler.add_jobstore(DjangoJobStore(), "default")

    # Add the job to run every 120 minutes (2 hours)
    # Using 'interval' instead of 'cron' for simplicity and immediate first run
    scheduler.add_job(
        run_news_pipeline_job,
        trigger="interval",
        minutes=120,
        id="news_pipeline_job",
        max_instances=1,
        replace_existing=True,
    )

    register_events(scheduler)
    scheduler.start()
    logger.info("Scheduler: Started successfully and news_pipeline_job scheduled.")
