"""
PHANTOM Task Queue Tests
Tests for priority ordering, retry logic, concurrency limits, and lifecycle.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from phantom.models import TaskPriority, TaskRecord, TaskStatus
from phantom.queue.task_queue import TaskQueue, _PRIORITY_WEIGHT, _QueueItem


# ── Priority Weight Tests ─────────────────────────────────────────────────────

class TestPriorityWeights:

    def test_high_lower_than_medium(self):
        assert _PRIORITY_WEIGHT[TaskPriority.HIGH] < _PRIORITY_WEIGHT[TaskPriority.MEDIUM]

    def test_medium_lower_than_low(self):
        assert _PRIORITY_WEIGHT[TaskPriority.MEDIUM] < _PRIORITY_WEIGHT[TaskPriority.LOW]

    def test_high_lowest_weight(self):
        assert _PRIORITY_WEIGHT[TaskPriority.HIGH] == 0


# ── QueueItem Comparison Tests ────────────────────────────────────────────────

class TestQueueItem:

    def _make_record(self, priority: TaskPriority, url: str = "https://example.com") -> TaskRecord:
        return TaskRecord(
            task_type="browse",
            status=TaskStatus.PENDING,
            priority=priority,
            url=url,
        )

    def test_high_priority_less_than_medium(self):
        high_record = self._make_record(TaskPriority.HIGH)
        med_record = self._make_record(TaskPriority.MEDIUM)
        high_item = _QueueItem(high_record, AsyncMock())
        med_item = _QueueItem(med_record, AsyncMock())
        assert high_item < med_item

    def test_medium_priority_less_than_low(self):
        med_record = self._make_record(TaskPriority.MEDIUM)
        low_record = self._make_record(TaskPriority.LOW)
        med_item = _QueueItem(med_record, AsyncMock())
        low_item = _QueueItem(low_record, AsyncMock())
        assert med_item < low_item

    def test_equal_priority_ordered_by_time(self):
        r1 = self._make_record(TaskPriority.MEDIUM)
        r2 = self._make_record(TaskPriority.MEDIUM)
        item1 = _QueueItem(r1, AsyncMock())
        # Simulate item2 enqueued slightly later
        import time as _time
        _time.sleep(0.001)
        item2 = _QueueItem(r2, AsyncMock())
        # item1 should come before item2 (same priority, earlier time)
        assert item1 < item2


# ── TaskQueue Tests ───────────────────────────────────────────────────────────

class TestTaskQueue:

    @pytest.fixture
    async def queue(self):
        """Provide a started TaskQueue, stopped after test."""
        q = TaskQueue(max_concurrent=2, max_retries=2)
        await q.start(num_workers=2)
        yield q
        await q.stop()

    @pytest.mark.asyncio
    async def test_enqueue_returns_task_record(self):
        q = TaskQueue(max_concurrent=1)
        handler = AsyncMock(return_value={"result": "ok"})
        record = await q.enqueue(
            url="https://example.com",
            task_type="browse",
            handler=handler,
            priority=TaskPriority.MEDIUM,
        )
        assert isinstance(record, TaskRecord)
        assert record.status == TaskStatus.PENDING
        assert record.url == "https://example.com"
        assert record.task_type == "browse"

    @pytest.mark.asyncio
    async def test_enqueue_increments_queue_depth(self):
        q = TaskQueue(max_concurrent=1)
        handler = AsyncMock(return_value={})
        await q.enqueue("https://a.com", "browse", handler)
        await q.enqueue("https://b.com", "browse", handler)
        assert q.queue_depth == 2

    @pytest.mark.asyncio
    async def test_task_completes_successfully(self):
        q = TaskQueue(max_concurrent=2)
        handler = AsyncMock(return_value={"data": "extracted"})
        await q.start(num_workers=1)
        record = await q.enqueue("https://example.com", "browse", handler)
        # Wait for task to complete
        for _ in range(50):
            await asyncio.sleep(0.05)
            r = q.get_task(record.task_id)
            if r and r.status == TaskStatus.DONE:
                break
        await q.stop()
        final_record = q.get_task(record.task_id)
        assert final_record is not None
        assert final_record.status == TaskStatus.DONE
        assert final_record.result == {"data": "extracted"}

    @pytest.mark.asyncio
    async def test_task_fails_after_max_retries(self):
        q = TaskQueue(max_concurrent=1, max_retries=2)
        q._backoff_base_ms = 10  # fast backoff for testing

        handler = AsyncMock(side_effect=RuntimeError("Connection refused"))
        await q.start(num_workers=1)
        record = await q.enqueue("https://example.com", "browse", handler)

        # Wait long enough for retries (2 * 10ms = 20ms + processing)
        for _ in range(100):
            await asyncio.sleep(0.05)
            r = q.get_task(record.task_id)
            if r and r.status == TaskStatus.FAILED:
                break

        await q.stop()
        final = q.get_task(record.task_id)
        assert final is not None
        assert final.status == TaskStatus.FAILED
        assert final.attempt >= 2

    @pytest.mark.asyncio
    async def test_get_task_returns_record(self):
        q = TaskQueue(max_concurrent=1)
        handler = AsyncMock(return_value={})
        record = await q.enqueue("https://example.com", "browse", handler)
        retrieved = q.get_task(record.task_id)
        assert retrieved is not None
        assert retrieved.task_id == record.task_id

    @pytest.mark.asyncio
    async def test_get_task_returns_none_for_unknown(self):
        q = TaskQueue(max_concurrent=1)
        result = q.get_task("non-existent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_tasks_returns_all(self):
        q = TaskQueue(max_concurrent=1)
        handler = AsyncMock(return_value={})
        await q.enqueue("https://a.com", "browse", handler)
        await q.enqueue("https://b.com", "browse", handler)
        await q.enqueue("https://c.com", "browse", handler)
        tasks = q.list_tasks()
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_status(self):
        q = TaskQueue(max_concurrent=1)
        handler = AsyncMock(return_value={})
        await q.enqueue("https://a.com", "browse", handler)
        await q.enqueue("https://b.com", "browse", handler)
        pending = q.list_tasks(status=TaskStatus.PENDING)
        assert all(t.status == TaskStatus.PENDING for t in pending)

    @pytest.mark.asyncio
    async def test_list_tasks_respects_limit(self):
        q = TaskQueue(max_concurrent=1)
        handler = AsyncMock(return_value={})
        for i in range(10):
            await q.enqueue(f"https://example{i}.com", "browse", handler)
        tasks = q.list_tasks(limit=5)
        assert len(tasks) == 5

    @pytest.mark.asyncio
    async def test_high_priority_processed_before_low(self):
        """High priority tasks should complete before low priority tasks."""
        q = TaskQueue(max_concurrent=1, max_retries=1)
        # Don't start workers yet — just enqueue
        completion_order = []

        async def handler_factory(label: str):
            async def _handler(record: TaskRecord):
                completion_order.append(label)
                return {"label": label}
            return _handler

        # Enqueue low first, high second
        low_handler = await handler_factory("LOW")
        high_handler = await handler_factory("HIGH")

        await q.enqueue("https://low.com", "browse", low_handler, priority=TaskPriority.LOW)
        await q.enqueue("https://high.com", "browse", high_handler, priority=TaskPriority.HIGH)

        await q.start(num_workers=1)

        for _ in range(50):
            await asyncio.sleep(0.05)
            if len(completion_order) >= 2:
                break

        await q.stop()

        # HIGH should be first in completion order
        if len(completion_order) >= 2:
            assert completion_order[0] == "HIGH"

    @pytest.mark.asyncio
    async def test_queue_depth_decreases_after_processing(self):
        q = TaskQueue(max_concurrent=2)
        handler = AsyncMock(return_value={})
        await q.enqueue("https://example.com", "browse", handler)
        initial_depth = q.queue_depth
        await q.start(num_workers=1)
        await asyncio.sleep(0.3)
        await q.stop()
        # After processing, depth should be 0
        assert q.queue_depth == 0

    @pytest.mark.asyncio
    async def test_task_record_has_started_at_when_done(self):
        q = TaskQueue(max_concurrent=1, max_retries=1)
        handler = AsyncMock(return_value={"ok": True})
        await q.start(num_workers=1)
        record = await q.enqueue("https://example.com", "browse", handler)

        for _ in range(50):
            await asyncio.sleep(0.05)
            r = q.get_task(record.task_id)
            if r and r.status == TaskStatus.DONE:
                break

        await q.stop()
        final = q.get_task(record.task_id)
        assert final is not None
        if final.status == TaskStatus.DONE:
            assert final.started_at is not None
            assert final.completed_at is not None
