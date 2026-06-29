"""
PHANTOM — Hermes Agent Stealth Browser Engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A production-grade stealth browser automation engine designed for Hermes agents.
Enables browsing, scraping, and structured data extraction while mimicking
real human behavior to bypass anti-bot detection systems.

Usage::

    from phantom import PhantomSettings, BrowseTask, PageResult

Version: 0.1.0
"""

from phantom.config import settings
from phantom.models import (
    ArticleData,
    ArticleRequest,
    BrowseRequest,
    BrowseTask,
    BrowserProfile,
    ExtractedData,
    ExtractorType,
    HealthResponse,
    PageResult,
    PriceData,
    PriceRequest,
    ScrapeJob,
    ScrapeRequest,
    ScreenshotRequest,
    SessionState,
    StructuredData,
    TaskPriority,
    TaskRecord,
    TaskStatus,
    ViewportSize,
)

__version__ = "0.1.0"
__author__ = "Hermes Agent Team"
__all__ = [
    "settings",
    "BrowseTask",
    "BrowseRequest",
    "BrowserProfile",
    "ExtractedData",
    "ExtractorType",
    "HealthResponse",
    "PageResult",
    "PriceData",
    "PriceRequest",
    "ScrapeJob",
    "ScrapeRequest",
    "ScreenshotRequest",
    "SessionState",
    "StructuredData",
    "TaskPriority",
    "TaskRecord",
    "TaskStatus",
    "ViewportSize",
    "ArticleData",
    "ArticleRequest",
]
