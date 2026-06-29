"""
PHANTOM Data Models
Pydantic v2 models for all domain objects.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# ── Enumerations ─────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    """Lifecycle states for a browser task."""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    RETRYING = "retrying"


class TaskPriority(str, Enum):
    """Task priority levels for the queue."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WaitStrategy(str, Enum):
    """Page load wait strategies."""
    NETWORKIDLE = "networkidle"
    DOMCONTENTLOADED = "domcontentloaded"
    LOAD = "load"
    COMMIT = "commit"


class ExtractorType(str, Enum):
    """Available extractor types."""
    PRICE = "price"
    ARTICLE = "article"
    STRUCTURED = "structured"
    CUSTOM = "custom"


# ── Browser Profile ──────────────────────────────────────────────────────────

class ViewportSize(BaseModel):
    """Browser viewport dimensions."""
    width: int = Field(..., ge=320, le=3840)
    height: int = Field(..., ge=240, le=2160)


class BrowserProfile(BaseModel):
    """Complete browser fingerprint profile for a session."""
    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_agent: str
    viewport: ViewportSize
    locale: str = Field(default="en-US")
    timezone_id: str = Field(default="America/New_York")
    color_scheme: str = Field(default="light")
    device_scale_factor: float = Field(default=1.0, ge=1.0, le=3.0)
    has_touch: bool = Field(default=False)
    java_script_enabled: bool = Field(default=True)
    extra_http_headers: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ── Session State ────────────────────────────────────────────────────────────

class SessionState(BaseModel):
    """Runtime state of a browser session."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    profile: BrowserProfile
    active_tasks: int = Field(default=0, ge=0)
    total_requests: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: Optional[datetime] = None
    is_healthy: bool = Field(default=True)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ── Task Models ──────────────────────────────────────────────────────────────

class BrowseTask(BaseModel):
    """Request to navigate to a URL and capture page content."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str = Field(..., description="Target URL to browse")
    wait_strategy: WaitStrategy = Field(default=WaitStrategy.NETWORKIDLE)
    wait_for_selector: Optional[str] = Field(
        default=None, description="Wait for this CSS selector before extracting"
    )
    timeout_ms: Optional[int] = Field(default=None, ge=1000, le=120_000)
    javascript: Optional[str] = Field(
        default=None, description="JavaScript to inject and execute on the page"
    )
    capture_screenshot: bool = Field(default=False)
    extract_links: bool = Field(default=True)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class ScrapeJob(BaseModel):
    """Configuration for a structured scrape operation with CSS selectors."""
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str = Field(..., description="Target URL to scrape")
    selectors: Dict[str, str] = Field(
        ...,
        description="Mapping of field_name -> CSS selector",
        examples=[{"title": "h1.product-title", "price": "span.price"}],
    )
    multiple: Dict[str, bool] = Field(
        default_factory=dict,
        description="Whether to extract all matches (True) or first match (False) per selector",
    )
    wait_for_selector: Optional[str] = None
    timeout_ms: int = Field(default=30_000)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    schedule_cron: Optional[str] = Field(
        default=None, description="Cron expression for recurring scrapes"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ── Result Models ────────────────────────────────────────────────────────────

class PageResult(BaseModel):
    """Result of a page browse operation."""
    task_id: str
    url: str
    final_url: str = Field(..., description="URL after any redirects")
    status_code: int = Field(default=200)
    title: Optional[str] = None
    html: Optional[str] = Field(default=None, description="Full page HTML")
    text_content: Optional[str] = Field(default=None, description="Extracted plain text")
    links: List[str] = Field(default_factory=list)
    screenshot_path: Optional[str] = None
    javascript_result: Optional[Any] = None
    load_time_ms: int = Field(default=0, ge=0)
    success: bool = Field(default=True)
    error: Optional[str] = None
    completed_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class ExtractedData(BaseModel):
    """Result of a structured data extraction."""
    job_id: str
    url: str
    extractor_type: ExtractorType
    data: Dict[str, Any] = Field(default_factory=dict)
    raw_fields: Dict[str, Union[str, List[str]]] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    success: bool = Field(default=True)
    error: Optional[str] = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class PriceData(BaseModel):
    """Structured price extraction result."""
    url: str
    current_price: Optional[float] = None
    original_price: Optional[float] = None
    currency: str = Field(default="USD")
    currency_symbol: str = Field(default="$")
    discount_percent: Optional[float] = None
    in_stock: Optional[bool] = None
    asin: Optional[str] = Field(default=None, description="Amazon ASIN if detected")
    product_title: Optional[str] = None
    seller: Optional[str] = None
    price_text: Optional[str] = Field(default=None, description="Raw price string")
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def compute_discount(self) -> "PriceData":
        if (
            self.current_price is not None
            and self.original_price is not None
            and self.original_price > 0
            and self.discount_percent is None
        ):
            self.discount_percent = round(
                (1 - self.current_price / self.original_price) * 100, 1
            )
        return self

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class ArticleData(BaseModel):
    """Structured article extraction result."""
    url: str
    title: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[str] = None
    modified_date: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    word_count: int = Field(default=0, ge=0)
    images: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    site_name: Optional[str] = None
    language: Optional[str] = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class StructuredData(BaseModel):
    """Schema.org / JSON-LD / OpenGraph extraction result."""
    url: str
    json_ld: List[Dict[str, Any]] = Field(default_factory=list)
    opengraph: Dict[str, str] = Field(default_factory=dict)
    microdata: List[Dict[str, Any]] = Field(default_factory=list)
    meta_tags: Dict[str, str] = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ── Queue / Job Tracking ─────────────────────────────────────────────────────

class TaskRecord(BaseModel):
    """Full lifecycle record for a queued task."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = Field(..., description="browse | scrape | price | article | screenshot")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    url: str
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ── API Request/Response Schemas ─────────────────────────────────────────────

class BrowseRequest(BaseModel):
    url: str
    wait_strategy: WaitStrategy = WaitStrategy.NETWORKIDLE
    wait_for_selector: Optional[str] = None
    timeout_ms: Optional[int] = Field(default=None, ge=1000, le=120_000)
    javascript: Optional[str] = None
    capture_screenshot: bool = False
    extract_links: bool = True
    priority: TaskPriority = TaskPriority.MEDIUM


class ScrapeRequest(BaseModel):
    url: str
    selectors: Dict[str, str]
    multiple: Dict[str, bool] = Field(default_factory=dict)
    wait_for_selector: Optional[str] = None
    timeout_ms: int = Field(default=30_000)
    priority: TaskPriority = TaskPriority.MEDIUM


class PriceRequest(BaseModel):
    url: str
    timeout_ms: int = Field(default=30_000)


class ArticleRequest(BaseModel):
    url: str
    timeout_ms: int = Field(default=30_000)


class ScreenshotRequest(BaseModel):
    url: str
    full_page: bool = Field(default=True)
    wait_for_selector: Optional[str] = None
    timeout_ms: int = Field(default=30_000)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    active_tasks: int = 0
    queue_depth: int = 0
    browser_healthy: bool = True
    cache_connected: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
