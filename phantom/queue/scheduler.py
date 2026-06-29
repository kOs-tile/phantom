"""
PHANTOM Job Scheduler
APScheduler-based recurring scrape job management.
Integrates with TaskQueue to enqueue jobs on schedule.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from phantom.models import ScrapeJob, TaskPriority
from phantom.queue.task_queue import TaskQueue


class JobScheduler:
    """
    Manages recurring scrape jobs using APScheduler with async execution.

    Jobs are defined by a cron expression and a ScrapeJob configuration.
    When triggered, they enqueue a task in the TaskQueue.
    """

    def __init__(self, task_queue: TaskQueue) -> None:
        self._queue = task_queue
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._jobs: Dict[str, ScrapeJob] = {}

    def start(self) -> None:
        """Start the scheduler."""
        self._scheduler.start()
        logger.info("JobScheduler started")

    def stop(self) -> None:
        """Shut down the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("JobScheduler stopped")

    def add_job(
        self,
        scrape_job: ScrapeJob,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> str:
        """
        Register a recurring scrape job.

        Args:
            scrape_job: ScrapeJob configuration with schedule_cron set.
            handler: Async callable to invoke for each run.

        Returns:
            APScheduler job ID.
        """
        if not scrape_job.schedule_cron:
            raise ValueError("ScrapeJob must have schedule_cron set")

        job_id = scrape_job.job_id
        self._jobs[job_id] = scrape_job

        async def _trigger() -> None:
            logger.info("Scheduled job {} triggered for {}", job_id, scrape_job.url)
            await self._queue.enqueue(
                url=scrape_job.url,
                task_type="scrape",
                handler=handler,
                priority=scrape_job.priority,
            )

        self._scheduler.add_job(
            _trigger,
            trigger=CronTrigger.from_crontab(scrape_job.schedule_cron, timezone="UTC"),
            id=job_id,
            name=f"PHANTOM:{scrape_job.url[:40]}",
            replace_existing=True,
            misfire_grace_time=60,
        )

        logger.info(
            "Registered scheduled job {} cron='{}' url={}",
            job_id,
            scrape_job.schedule_cron,
            scrape_job.url,
        )
        return job_id

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        try:
            self._scheduler.remove_job(job_id)
            self._jobs.pop(job_id, None)
            logger.info("Removed scheduled job {}", job_id)
            return True
        except Exception as exc:
            logger.warning("Could not remove job {}: {}", job_id, exc)
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return list of registered scheduled jobs with their next run times."""
        result = []
        for job in self._scheduler.get_jobs():
            scrape_job = self._jobs.get(job.id)
            result.append({
                "job_id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "cron": self._jobs[job.id].schedule_cron if job.id in self._jobs else None,
                "url": scrape_job.url if scrape_job else None,
            })
        return result

    def get_job(self, job_id: str) -> Optional[ScrapeJob]:
        """Retrieve a ScrapeJob config by ID."""
        return self._jobs.get(job_id)

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is currently active."""
        return self._scheduler.running
