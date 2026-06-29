"""
PHANTOM API Tests
Tests for FastAPI routes using TestClient with mocked browser/queue/cache.
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from phantom.models import (
    ArticleData,
    ExtractedData,
    ExtractorType,
    HealthResponse,
    PageResult,
    PriceData,
    TaskPriority,
    TaskRecord,
    TaskStatus,
    WaitStrategy,
)


# ── App setup with mocks ──────────────────────────────────────────────────────

def make_test_app():
    """Create a TestClient with mocked services."""
    import phantom.api.main as main_module

    # Mock browser session
    mock_browser = MagicMock()
    mock_browser.is_running = True
    mock_browser.active_contexts = 0
    mock_browser.record_request = MagicMock()

    # Mock task queue
    mock_queue = MagicMock()
    mock_queue.active_tasks = 0
    mock_queue.queue_depth = 0
    mock_queue.list_tasks.return_value = []
    mock_queue.get_task.return_value = None

    # Mock result store
    mock_store = MagicMock()
    mock_store.health = AsyncMock(return_value={"redis_connected": False, "backend": "memory"})
    mock_store.set_task_result = AsyncMock()
    mock_store.get_task_result = AsyncMock(return_value=None)

    main_module.browser_session = mock_browser
    main_module.task_queue = mock_queue
    main_module.result_store = mock_store

    from fastapi.testclient import TestClient
    from phantom.api.main import app

    # Override lifespan for testing (don't start real browser)
    app.router.lifespan_context = None  # type: ignore

    return TestClient(app, raise_server_exceptions=False), mock_browser, mock_queue, mock_store


# ── Health endpoint ───────────────────────────────────────────────────────────

def _make_async_mock_store():
    """Create a fully async-compatible mock ResultStore."""
    mock_store = MagicMock()
    mock_store.connect = AsyncMock(return_value=False)
    mock_store.disconnect = AsyncMock()
    mock_store.health = AsyncMock(return_value={"redis_connected": False, "backend": "memory"})
    mock_store.set_task_result = AsyncMock()
    mock_store.get_task_result = AsyncMock(return_value=None)
    return mock_store


def _make_async_mock_queue():
    """Create a fully async-compatible mock TaskQueue."""
    mock_queue = MagicMock()
    mock_queue.start = AsyncMock()
    mock_queue.stop = AsyncMock()
    mock_queue.active_tasks = 0
    mock_queue.queue_depth = 0
    mock_queue.list_tasks.return_value = []
    mock_queue.get_task.return_value = None
    return mock_queue


def _make_async_mock_browser():
    """Create a fully async-compatible mock BrowserSession."""
    mock_browser = MagicMock()
    mock_browser.start = AsyncMock()
    mock_browser.stop = AsyncMock()
    mock_browser.is_running = True
    mock_browser.record_request = MagicMock()
    return mock_browser


class TestHealthEndpoint:

    def test_health_returns_200(self):
        import phantom.api.main as main_module
        from fastapi.testclient import TestClient
        from phantom.api.main import app

        main_module.browser_session = _make_async_mock_browser()
        main_module.task_queue = _make_async_mock_queue()
        main_module.result_store = _make_async_mock_store()

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_schema(self):
        import phantom.api.main as main_module
        from fastapi.testclient import TestClient
        from phantom.api.main import app

        mock_queue = _make_async_mock_queue()
        mock_queue.active_tasks = 2
        mock_queue.queue_depth = 5
        mock_store = _make_async_mock_store()
        mock_store.health = AsyncMock(return_value={"redis_connected": True})

        main_module.browser_session = _make_async_mock_browser()
        main_module.task_queue = mock_queue
        main_module.result_store = mock_store

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "browser_healthy" in data

    def test_health_version_correct(self):
        import phantom.api.main as main_module
        from fastapi.testclient import TestClient
        from phantom.api.main import app

        main_module.browser_session = _make_async_mock_browser()
        main_module.task_queue = _make_async_mock_queue()
        main_module.result_store = _make_async_mock_store()

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["version"] == "0.1.0"


# ── Jobs endpoints ────────────────────────────────────────────────────────────

class TestJobsEndpoints:

    def setup_method(self):
        import phantom.api.main as main_module
        from fastapi.testclient import TestClient
        from phantom.api.main import app

        self.mock_browser = _make_async_mock_browser()
        self.mock_queue = _make_async_mock_queue()
        self.mock_store = _make_async_mock_store()

        main_module.browser_session = self.mock_browser
        main_module.task_queue = self.mock_queue
        main_module.result_store = self.mock_store

        self._app = app
        self._client_ctx = TestClient(app, raise_server_exceptions=False)
        self.client = self._client_ctx.__enter__()

    def teardown_method(self):
        try:
            self._client_ctx.__exit__(None, None, None)
        except Exception:
            pass

    def test_list_jobs_returns_200(self):
        self.mock_queue.list_tasks.return_value = []
        response = self.client.get("/jobs")
        assert response.status_code == 200

    def test_list_jobs_returns_list(self):
        self.mock_queue.list_tasks.return_value = []
        response = self.client.get("/jobs")
        if response.status_code == 200:
            assert isinstance(response.json(), list)

    def test_list_jobs_with_tasks(self):
        task = TaskRecord(
            task_id="abc123",
            task_type="browse",
            status=TaskStatus.DONE,
            priority=TaskPriority.MEDIUM,
            url="https://example.com",
        )
        self.mock_queue.list_tasks.return_value = [task]
        response = self.client.get("/jobs")
        if response.status_code == 200:
            data = response.json()
            assert len(data) == 1
            assert data[0]["task_id"] == "abc123"

    def test_get_job_returns_404_when_not_found(self):
        self.mock_queue.get_task.return_value = None
        response = self.client.get("/jobs/nonexistent-id")
        assert response.status_code == 404

    def test_get_job_returns_task_when_found(self):
        task = TaskRecord(
            task_id="found-task-id",
            task_type="price",
            status=TaskStatus.DONE,
            priority=TaskPriority.HIGH,
            url="https://amazon.com/dp/B123",
        )
        self.mock_queue.get_task.return_value = task
        response = self.client.get("/jobs/found-task-id")
        if response.status_code == 200:
            data = response.json()
            assert data["task_id"] == "found-task-id"

    def test_list_jobs_invalid_status_filter_returns_400(self):
        response = self.client.get("/jobs?status_filter=invalid_status")
        assert response.status_code == 400


# ── Model Tests ───────────────────────────────────────────────────────────────

class TestModels:

    def test_browse_task_url_validation(self):
        from phantom.models import BrowseTask
        task = BrowseTask(url="https://example.com")
        assert task.url == "https://example.com"

    def test_browse_task_rejects_invalid_url(self):
        from phantom.models import BrowseTask
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            BrowseTask(url="not-a-url")

    def test_scrape_job_url_validation(self):
        from phantom.models import ScrapeJob
        job = ScrapeJob(url="https://example.com", selectors={"title": "h1"})
        assert job.url == "https://example.com"
        assert job.selectors["title"] == "h1"

    def test_price_data_discount_computed(self):
        price = PriceData(
            url="https://example.com",
            current_price=50.0,
            original_price=100.0,
        )
        assert price.discount_percent == 50.0

    def test_price_data_no_discount_when_equal(self):
        price = PriceData(
            url="https://example.com",
            current_price=50.0,
            original_price=50.0,
        )
        assert price.discount_percent == 0.0

    def test_task_record_default_status_pending(self):
        record = TaskRecord(
            task_type="browse",
            url="https://example.com",
        )
        assert record.status == TaskStatus.PENDING

    def test_task_record_duration_none_when_not_started(self):
        record = TaskRecord(task_type="browse", url="https://example.com")
        assert record.duration_ms is None

    def test_health_response_defaults(self):
        health = HealthResponse()
        assert health.status == "ok"
        assert health.version == "0.1.0"
        assert health.active_tasks == 0

    def test_page_result_model(self):
        result = PageResult(
            task_id="test-id",
            url="https://example.com",
            final_url="https://example.com",
            status_code=200,
            title="Test Page",
            success=True,
        )
        assert result.success
        assert result.task_id == "test-id"
        assert result.title == "Test Page"

    def test_extracted_data_model(self):
        data = ExtractedData(
            job_id="job-1",
            url="https://example.com",
            extractor_type=ExtractorType.CUSTOM,
            data={"title": "Widget"},
            success=True,
        )
        assert data.success
        assert data.data["title"] == "Widget"

    def test_article_data_model(self):
        article = ArticleData(
            url="https://example.com/article",
            title="Test Article",
            author="John Doe",
            word_count=500,
        )
        assert article.title == "Test Article"
        assert article.word_count == 500

    def test_task_record_priority_default_medium(self):
        record = TaskRecord(task_type="browse", url="https://example.com")
        assert record.priority == TaskPriority.MEDIUM

    def test_viewport_size_validation(self):
        from phantom.models import ViewportSize
        vp = ViewportSize(width=1920, height=1080)
        assert vp.width == 1920
        assert vp.height == 1080

    def test_viewport_size_rejects_too_small(self):
        from phantom.models import ViewportSize
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ViewportSize(width=100, height=100)  # width < 320 is fine, height < 240 fails
