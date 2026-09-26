"""
PHANTOM API Routes
REST endpoints for browse, scrape, extract, screenshot, jobs, and health.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from phantom.browser.extractor import DOMExtractor
from phantom.browser.navigator import PageNavigator
from phantom.extractors.article import ArticleExtractor
from phantom.extractors.price import PriceExtractor
from phantom.extractors.structured import StructuredDataExtractor
from phantom.reliability.contracts import (
    ExtractionDriftReport,
    ExtractionDriftRequest,
    ExtractionQualityReport,
    ExtractionValidationRequest,
    compare_extractions,
    evaluate_extraction_contract,
)
from phantom.models import (
    ArticleData,
    ArticleRequest,
    BrowseRequest,
    BrowseTask,
    ExtractedData,
    ExtractorType,
    HealthResponse,
    PageResult,
    PriceData,
    PriceRequest,
    ScrapeRequest,
    ScreenshotRequest,
    TaskPriority,
    TaskRecord,
    TaskStatus,
)
from phantom.stealth.humanizer import HumanBehaviorSimulator

router = APIRouter()

# ── Dependency injection ──────────────────────────────────────────────────────

def get_browser_session():
    """Inject browser session from app state."""
    from phantom.api.main import browser_session
    return browser_session


def get_task_queue():
    """Inject task queue from app state."""
    from phantom.api.main import task_queue
    return task_queue


def get_result_store():
    """Inject result store from app state."""
    from phantom.api.main import result_store
    return result_store


# ── Helper ────────────────────────────────────────────────────────────────────

async def _navigate_url(
    browser_session: Any,
    task: BrowseTask,
) -> PageResult:
    """Run a navigation task in an isolated browser context."""
    async with browser_session.new_context() as context:
        page = await context.new_page()
        humanizer = HumanBehaviorSimulator()
        navigator = PageNavigator(page, humanizer)
        result = await navigator.navigate(task)
        browser_session.record_request(error=not result.success)
        return result


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check(
    browser_session=Depends(get_browser_session),
    task_queue=Depends(get_task_queue),
    result_store=Depends(get_result_store),
) -> HealthResponse:
    """Service health check. Returns status, queue depth, and cache status."""
    cache_health = await result_store.health()
    return HealthResponse(
        status="ok",
        version="0.1.0",
        active_tasks=task_queue.active_tasks,
        queue_depth=task_queue.queue_depth,
        browser_healthy=browser_session.is_running,
        cache_connected=cache_health.get("redis_connected", False),
        timestamp=datetime.utcnow(),
    )


# ── Reliability ───────────────────────────────────────────────────────────────

@router.post(
    "/validate/extraction",
    response_model=ExtractionQualityReport,
    tags=["Reliability"],
)
async def validate_extraction(
    request: ExtractionValidationRequest,
) -> ExtractionQualityReport:
    """Validate any structured extraction payload against a deterministic contract.

    This endpoint is browser/provider independent: callers may validate PHANTOM
    results or payloads produced by another browser agent/provider.
    """
    return evaluate_extraction_contract(request.data, request.contract)


@router.post(
    "/validate/extraction-drift",
    response_model=ExtractionDriftReport,
    tags=["Reliability"],
)
async def validate_extraction_drift(
    request: ExtractionDriftRequest,
) -> ExtractionDriftReport:
    """Compare a baseline/current extraction under one deterministic contract."""
    return compare_extractions(
        request.baseline,
        request.current,
        request.contract,
    )


# ── Browse ────────────────────────────────────────────────────────────────────

@router.post("/browse", response_model=PageResult, tags=["Browser"])
async def browse(
    request: BrowseRequest,
    browser_session=Depends(get_browser_session),
    result_store=Depends(get_result_store),
) -> PageResult:
    """
    Navigate to a URL and return full page content.

    Supports JavaScript injection, custom wait strategies,
    screenshot capture, and link extraction.
    """
    if not browser_session.is_running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser session is not available",
        )

    task = BrowseTask(
        url=request.url,
        wait_strategy=request.wait_strategy,
        wait_for_selector=request.wait_for_selector,
        timeout_ms=request.timeout_ms,
        javascript=request.javascript,
        capture_screenshot=request.capture_screenshot,
        extract_links=request.extract_links,
        priority=request.priority,
    )

    result = await _navigate_url(browser_session, task)

    # Cache result
    await result_store.set_task_result(task.task_id, result.model_dump())

    return result


# ── Scrape ────────────────────────────────────────────────────────────────────

@router.post("/scrape", response_model=ExtractedData, tags=["Browser"])
async def scrape(
    request: ScrapeRequest,
    browser_session=Depends(get_browser_session),
    result_store=Depends(get_result_store),
) -> ExtractedData:
    """
    Navigate to a URL and extract data using CSS selectors.

    Provide a `selectors` map of field_name -> CSS selector.
    Set `multiple[field_name] = true` to capture all matches.
    """
    if not browser_session.is_running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser session is not available",
        )

    job_id = str(uuid.uuid4())

    try:
        async with browser_session.new_context() as context:
            page = await context.new_page()

            # Navigate
            await page.goto(
                request.url,
                timeout=request.timeout_ms,
                wait_until="networkidle",
            )

            if request.wait_for_selector:
                try:
                    await page.wait_for_selector(
                        request.wait_for_selector,
                        timeout=min(request.timeout_ms, 15_000),
                    )
                except Exception:
                    pass

            # Extract
            extractor = DOMExtractor(page)
            raw_fields = await extractor.extract_by_selectors(
                request.selectors,
                request.multiple,
            )

            result = ExtractedData(
                job_id=job_id,
                url=request.url,
                extractor_type=ExtractorType.CUSTOM,
                data=dict(raw_fields),
                raw_fields={k: (v if v is not None else "") for k, v in raw_fields.items()},  # type: ignore
                success=True,
            )
            browser_session.record_request()

    except Exception as exc:
        logger.error("Scrape failed for {}: {}", request.url, exc)
        result = ExtractedData(
            job_id=job_id,
            url=request.url,
            extractor_type=ExtractorType.CUSTOM,
            success=False,
            error=str(exc),
        )
        browser_session.record_request(error=True)

    await result_store.set_task_result(job_id, result.model_dump())
    return result


# ── Extract Price ─────────────────────────────────────────────────────────────

@router.post("/extract/price", response_model=PriceData, tags=["Extractors"])
async def extract_price(
    request: PriceRequest,
    browser_session=Depends(get_browser_session),
    result_store=Depends(get_result_store),
) -> PriceData:
    """
    Extract price information from a product URL.

    Auto-detects Amazon, eBay, Shopify, and generic e-commerce sites.
    Returns current price, original price, currency, stock status, and ASIN.
    """
    if not browser_session.is_running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser session is not available",
        )

    extractor = PriceExtractor()

    try:
        async with browser_session.new_context() as context:
            page = await context.new_page()
            await page.goto(request.url, timeout=request.timeout_ms, wait_until="networkidle")
            result = await extractor.from_page(page, request.url)
            browser_session.record_request()
    except Exception as exc:
        logger.error("Price extraction failed for {}: {}", request.url, exc)
        result = PriceData(url=request.url)
        browser_session.record_request(error=True)

    return result


# ── Extract Article ───────────────────────────────────────────────────────────

@router.post("/extract/article", response_model=ArticleData, tags=["Extractors"])
async def extract_article(
    request: ArticleRequest,
    browser_session=Depends(get_browser_session),
) -> ArticleData:
    """
    Extract article content from a news or blog URL.

    Returns title, author, publish date, full content, word count, and images.
    """
    if not browser_session.is_running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser session is not available",
        )

    extractor = ArticleExtractor()

    try:
        async with browser_session.new_context() as context:
            page = await context.new_page()
            await page.goto(request.url, timeout=request.timeout_ms, wait_until="networkidle")
            result = await extractor.from_page(page, request.url)
            browser_session.record_request()
    except Exception as exc:
        logger.error("Article extraction failed for {}: {}", request.url, exc)
        result = ArticleData(url=request.url)
        browser_session.record_request(error=True)

    return result


# ── Screenshot ────────────────────────────────────────────────────────────────

@router.post("/screenshot", tags=["Browser"])
async def take_screenshot(
    request: ScreenshotRequest,
    browser_session=Depends(get_browser_session),
) -> Dict[str, Any]:
    """
    Navigate to a URL and capture a screenshot.

    Returns the path to the saved PNG file.
    """
    if not browser_session.is_running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser session is not available",
        )

    task_id = str(uuid.uuid4())

    try:
        async with browser_session.new_context() as context:
            page = await context.new_page()
            await page.goto(
                request.url,
                timeout=request.timeout_ms,
                wait_until="networkidle",
            )

            if request.wait_for_selector:
                try:
                    await page.wait_for_selector(
                        request.wait_for_selector,
                        timeout=10_000,
                    )
                except Exception:
                    pass

            humanizer = HumanBehaviorSimulator()
            navigator = PageNavigator(page, humanizer)
            path = await navigator.screenshot(task_id, full_page=request.full_page)
            browser_session.record_request()

            return {
                "task_id": task_id,
                "url": request.url,
                "screenshot_path": path,
                "success": path is not None,
            }

    except Exception as exc:
        logger.error("Screenshot failed for {}: {}", request.url, exc)
        browser_session.record_request(error=True)
        return {
            "task_id": task_id,
            "url": request.url,
            "screenshot_path": None,
            "success": False,
            "error": str(exc),
        }


# ── Jobs ──────────────────────────────────────────────────────────────────────

@router.get("/jobs", response_model=List[TaskRecord], tags=["Queue"])
async def list_jobs(
    status_filter: Optional[str] = None,
    limit: int = 50,
    task_queue=Depends(get_task_queue),
) -> List[TaskRecord]:
    """
    List all queued and completed task records.

    Optionally filter by status: pending, running, done, failed, retrying.
    """
    status_enum: Optional[TaskStatus] = None
    if status_filter:
        try:
            status_enum = TaskStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter. Must be one of: {[s.value for s in TaskStatus]}",
            )

    return task_queue.list_tasks(status=status_enum, limit=limit)


@router.get("/jobs/{task_id}", response_model=TaskRecord, tags=["Queue"])
async def get_job(
    task_id: str,
    task_queue=Depends(get_task_queue),
) -> TaskRecord:
    """Get a specific task record by ID, including result and error if available."""
    record = task_queue.get_task(task_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return record
