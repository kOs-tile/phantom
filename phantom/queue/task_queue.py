"""
PHANTOM Async Task Queue
Priority queue with concurrency limits, retry/backoff, and full status tracking.
Tasks flow: pending → running → done | failed | retrying
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional

from loguru import logger

from phantom.config import settings
from phantom.models import TaskPriority, TaskRecord, TaskStatus


# Priority → numeric weight for heapq (lower = higher priority)
_PRIORITY_WEIGHT: Dict[TaskPriority, int] = {
    TaskPriority.HIGH: 0,
    TaskPriority.MEDIUM: 1,
    TaskPriority.LOW: 2,
}


class _QueueItem:
    """Internal queue item with priority-aware comparison."""

    __slots__ = ("priority_weight", "enqueued_at", "record", "handler")

    def __init__(
        self,
        record: TaskRecord,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        self.priority_weight = _PRIORITY_WEIGHT[record.priority]
        self.enqueued_at = datetime.utcnow()
        self.record = record
        self.handler = handler

    def __lt__(self, other: "_QueueItem") -> bool:
        if self.priority_weight != other.priority_weight:
            return self.priority_weight < other.priority_weight
        return self.enqueued_at < other.enqueued_at


class TaskQueue:
    """
    Async priority task queue with:
    - HIGH / MEDIUM / LOW priority levels
    - Configurable max concurrency (default: 3)
    - Exponential backoff retry (max 3 attempts)
    - Full task lifecycle tracking
    """

    def __init__(
        self,
        max_concurrent: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self._max_concurrent = max_concurrent or settings.max_concurrent_tasks
        self._max_retries = max_retries or settings.max_retries
        self._backoff_base_ms = settings.retry_backoff_base_ms

        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._records: Dict[str, TaskRecord] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self, num_workers: Optional[int] = None) -> None:
        """Start worker coroutines."""
        n = num_workers or self._max_concurrent
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._running = True
        for _ in range(n):
            worker = asyncio.create_task(self._worker_loop())
            self._workers.append(worker)
        logger.info("TaskQueue started with {} workers", n)

    async def stop(self) -> None:
        """Stop all workers gracefully."""
        self._running = False
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("TaskQueue stopped")

    async def enqueue(
        self,
        url: str,
        task_type: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        priority: TaskPriority = TaskPriority.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskRecord:
        """
        Add a new task to the queue.

        Args:
            url: Target URL for the task
            task_type: Human-readable type label (browse, scrape, price, etc.)
            handler: Async callable that receives the TaskRecord and returns a result
            priority: Task priority level
            metadata: Optional extra data attached to the record

        Returns:
            The created TaskRecord (status=PENDING)
        """
        record = TaskRecord(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            status=TaskStatus.PENDING,
            priority=priority,
            url=url,
            max_attempts=self._max_retries,
        )

        async with self._lock:
            self._records[record.task_id] = record

        item = _QueueItem(record=record, handler=handler)
        await self._queue.put((item.priority_weight, item.enqueued_at, item))

        logger.debug(
            "Enqueued task {} type={} priority={} url={}",
            record.task_id,
            task_type,
            priority.value,
            url,
        )
        return record

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve a task record by ID."""
        return self._records.get(task_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
    ) -> List[TaskRecord]:
        """List task records, optionally filtered by status."""
        records = list(self._records.values())
        if status:
            records = [r for r in records if r.status == status]
        # Sort by created_at descending
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    @property
    def queue_depth(self) -> int:
        """Number of tasks currently in the queue (not yet running)."""
        return self._queue.qsize()

    @property
    def active_tasks(self) -> int:
        """Number of currently executing tasks."""
        return sum(1 for r in self._records.values() if r.status == TaskStatus.RUNNING)

    async def _worker_loop(self) -> None:
        """Worker coroutine: pulls items from the queue and executes them."""
        while self._running:
            try:
                _, _, item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if self._semaphore:
                async with self._semaphore:
                    await self._execute_task(item)
            else:
                await self._execute_task(item)

            self._queue.task_done()

    async def _execute_task(self, item: _QueueItem) -> None:
        """Execute a single task with retry logic."""
        record = item.record
        record.attempt += 1
        record.status = TaskStatus.RUNNING
        record.started_at = datetime.utcnow()

        async with self._lock:
            self._records[record.task_id] = record

        logger.info(
            "Executing task {} attempt={}/{} type={} url={}",
            record.task_id,
            record.attempt,
            record.max_attempts,
            record.task_type,
            record.url,
        )

        try:
            result = await item.handler(record)
            record.status = TaskStatus.DONE
            record.result = result
            record.completed_at = datetime.utcnow()
            logger.info("Task {} completed successfully", record.task_id)

        except Exception as exc:
            logger.error("Task {} failed (attempt {}): {}", record.task_id, record.attempt, exc)
            record.error = str(exc)

            if record.attempt < record.max_attempts:
                # Exponential backoff
                backoff_ms = self._backoff_base_ms * (2 ** (record.attempt - 1))
                record.status = TaskStatus.RETRYING
                record.next_retry_at = datetime.utcnow() + timedelta(milliseconds=backoff_ms)

                logger.info(
                    "Task {} will retry in {}ms (attempt {}/{})",
                    record.task_id,
                    backoff_ms,
                    record.attempt,
                    record.max_attempts,
                )

                async with self._lock:
                    self._records[record.task_id] = record

                # Re-enqueue after backoff delay
                await asyncio.sleep(backoff_ms / 1000)
                new_item = _QueueItem(record=record, handler=item.handler)
                await self._queue.put((new_item.priority_weight, new_item.enqueued_at, new_item))
                return
            else:
                record.status = TaskStatus.FAILED
                record.completed_at = datetime.utcnow()
                logger.error("Task {} permanently failed after {} attempts", record.task_id, record.attempt)

        async with self._lock:
            self._records[record.task_id] = record
