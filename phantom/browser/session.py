"""
PHANTOM Browser Session Manager
Manages the async Playwright browser instance with one context per task.
Applies stealth fingerprints, evasion scripts, and proxy configuration.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from loguru import logger

from phantom.config import settings
from phantom.models import BrowserProfile, SessionState
from phantom.stealth.evasion import EvasionScripts
from phantom.stealth.fingerprint import BrowserFingerprint, FingerprintGenerator


class BrowserSession:
    """
    Manages a single Playwright browser instance with isolated per-task contexts.

    Usage::

        async with BrowserSession() as session:
            async with session.new_context() as context:
                page = await context.new_page()
                ...
    """

    def __init__(self) -> None:
        self._playwright: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._fingerprint_gen = FingerprintGenerator()
        self._active_contexts: int = 0
        self._total_requests: int = 0
        self._errors: int = 0
        self._started_at: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._current_profile: Optional[BrowserProfile] = None

    async def start(self) -> None:
        """Launch the browser. Called once at application startup."""
        from playwright.async_api import async_playwright

        logger.info("Starting PHANTOM browser session (headless={})", settings.browser_headless)

        self._playwright = await async_playwright().start()

        fp: BrowserFingerprint = self._fingerprint_gen.generate()
        self._current_profile = fp.to_browser_profile()

        launch_kwargs: dict[str, Any] = {
            "headless": settings.browser_headless,
            "args": EvasionScripts.get_cdp_args(),
            "ignore_default_args": EvasionScripts.get_ignore_default_args(),
        }

        if settings.proxy_url:
            launch_kwargs["proxy"] = {"server": settings.proxy_url}

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        self._started_at = datetime.utcnow()
        logger.info("Browser launched with fingerprint: UA={}", fp.user_agent[:60])

    async def stop(self) -> None:
        """Gracefully close the browser and Playwright instance."""
        logger.info("Stopping PHANTOM browser session")
        if self._browser:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.warning("Error closing browser: {}", exc)
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning("Error stopping playwright: {}", exc)
        self._browser = None
        self._playwright = None

    @asynccontextmanager
    async def new_context(
        self,
        fingerprint: Optional[BrowserFingerprint] = None,
    ) -> AsyncGenerator[Any, None]:
        """
        Create an isolated browser context for a single task.

        Each context gets its own cookies, storage, and viewport.
        The context is automatically closed when the block exits.

        Args:
            fingerprint: Optional fingerprint to apply. Generates a new one if not provided.

        Yields:
            A Playwright BrowserContext instance with evasion scripts injected.
        """
        if not self._browser:
            raise RuntimeError("BrowserSession not started. Call start() first.")

        fp = fingerprint or self._fingerprint_gen.generate()

        context_kwargs: dict[str, Any] = {
            "user_agent": fp.user_agent,
            "viewport": {"width": fp.viewport[0], "height": fp.viewport[1]},
            "locale": fp.locale,
            "timezone_id": fp.timezone_id,
            "color_scheme": fp.color_scheme,
            "device_scale_factor": fp.device_scale_factor,
            "has_touch": False,
            "java_script_enabled": True,
            "extra_http_headers": {
                "Accept-Language": fp.accept_language,
                **fp.extra_headers,
            },
        }

        if settings.proxy_url:
            context_kwargs["proxy"] = {"server": settings.proxy_url}

        context = await self._browser.new_context(**context_kwargs)

        # Inject full evasion script before any page scripts run
        evasion_script = EvasionScripts.get_full_evasion_script(
            languages=[fp.locale, fp.locale.split("-")[0]],
        )
        await context.add_init_script(evasion_script)

        async with self._lock:
            self._active_contexts += 1

        logger.debug(
            "New browser context created (active: {}) locale={} viewport={}x{}",
            self._active_contexts,
            fp.locale,
            fp.viewport[0],
            fp.viewport[1],
        )

        try:
            yield context
        finally:
            try:
                await context.close()
            except Exception as exc:
                logger.warning("Error closing context: {}", exc)
            async with self._lock:
                self._active_contexts = max(0, self._active_contexts - 1)
            logger.debug("Browser context closed (active: {})", self._active_contexts)

    def get_state(self) -> SessionState:
        """Return current session health and statistics."""
        profile = self._current_profile or BrowserProfile(
            user_agent="unknown",
            viewport={"width": 1920, "height": 1080},  # type: ignore
        )
        return SessionState(
            profile=profile,
            active_tasks=self._active_contexts,
            total_requests=self._total_requests,
            errors=self._errors,
            started_at=self._started_at or datetime.utcnow(),
            last_activity=datetime.utcnow(),
            is_healthy=self._browser is not None,
        )

    @property
    def is_running(self) -> bool:
        """Whether the browser is currently active."""
        return self._browser is not None

    def record_request(self, error: bool = False) -> None:
        """Increment request counters."""
        self._total_requests += 1
        if error:
            self._errors += 1

    async def __aenter__(self) -> "BrowserSession":
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()
