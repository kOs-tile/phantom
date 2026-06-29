"""
PHANTOM Page Navigator
Handles page navigation, wait strategies, screenshot capture,
and JavaScript injection within a browser context.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from phantom.config import settings
from phantom.models import BrowseTask, PageResult, WaitStrategy
from phantom.stealth.humanizer import HumanBehaviorSimulator


# Map WaitStrategy enum to Playwright load state strings
_WAIT_STATE_MAP: Dict[WaitStrategy, str] = {
    WaitStrategy.NETWORKIDLE: "networkidle",
    WaitStrategy.DOMCONTENTLOADED: "domcontentloaded",
    WaitStrategy.LOAD: "load",
    WaitStrategy.COMMIT: "commit",
}


class PageNavigator:
    """
    High-level page navigation and interaction layer.

    Wraps a Playwright Page to provide smart wait strategies,
    screenshot capture, JavaScript evaluation, and link extraction.
    """

    def __init__(
        self,
        page: Any,
        humanizer: Optional[HumanBehaviorSimulator] = None,
    ) -> None:
        self._page = page
        self._humanizer = humanizer or HumanBehaviorSimulator()

    async def navigate(
        self,
        task: BrowseTask,
    ) -> PageResult:
        """
        Navigate to a URL and extract page content per task specification.

        Args:
            task: BrowseTask configuration

        Returns:
            PageResult with content, links, and optional screenshot.
        """
        timeout = task.timeout_ms or settings.default_timeout_ms
        wait_state = _WAIT_STATE_MAP.get(task.wait_strategy, "networkidle")

        start_ts = time.monotonic()
        screenshot_path: Optional[str] = None
        error_msg: Optional[str] = None
        success = True

        try:
            response = await self._page.goto(
                task.url,
                timeout=timeout,
                wait_until=wait_state,
            )

            # Wait for specific selector if requested
            if task.wait_for_selector:
                try:
                    await self._page.wait_for_selector(
                        task.wait_for_selector,
                        timeout=min(timeout, 15_000),
                    )
                except Exception as sel_exc:
                    logger.warning(
                        "Selector '{}' not found within timeout: {}",
                        task.wait_for_selector,
                        sel_exc,
                    )

            # Inject and run JavaScript if provided
            js_result: Optional[Any] = None
            if task.javascript:
                try:
                    js_result = await self._page.evaluate(task.javascript)
                except Exception as js_exc:
                    logger.warning("JavaScript injection failed: {}", js_exc)

            # Human-like viewport scroll
            await self._humanizer.micro_delay()

            # Capture screenshot
            if task.capture_screenshot:
                screenshot_path = await self._take_screenshot(task.task_id)

            # Extract page data
            title = await self._get_title()
            final_url = self._page.url
            html = await self._page.content()
            text_content = await self._extract_text()
            links: List[str] = []
            if task.extract_links:
                links = await self._extract_links()

            status_code = response.status if response else 200
            load_time_ms = int((time.monotonic() - start_ts) * 1000)

            logger.info(
                "Navigated to {} (status={} load={}ms)",
                task.url,
                status_code,
                load_time_ms,
            )

            return PageResult(
                task_id=task.task_id,
                url=task.url,
                final_url=final_url,
                status_code=status_code,
                title=title,
                html=html,
                text_content=text_content,
                links=links,
                screenshot_path=screenshot_path,
                javascript_result=js_result,
                load_time_ms=load_time_ms,
                success=True,
            )

        except Exception as exc:
            error_msg = str(exc)
            load_time_ms = int((time.monotonic() - start_ts) * 1000)
            logger.error("Navigation failed for {}: {}", task.url, exc)

            # Try to capture error screenshot
            try:
                screenshot_path = await self._take_screenshot(f"{task.task_id}_error")
            except Exception:
                pass

            return PageResult(
                task_id=task.task_id,
                url=task.url,
                final_url=task.url,
                status_code=0,
                title=None,
                html=None,
                text_content=None,
                links=[],
                screenshot_path=screenshot_path,
                load_time_ms=load_time_ms,
                success=False,
                error=error_msg,
            )

    async def screenshot(
        self,
        task_id: str,
        full_page: bool = True,
        selector: Optional[str] = None,
    ) -> Optional[str]:
        """
        Capture a screenshot of the current page.

        Args:
            task_id: Unique task ID for filename.
            full_page: If True, capture the full scrollable page.
            selector: Optional CSS selector to capture a specific element.

        Returns:
            Path to saved screenshot file, or None on failure.
        """
        return await self._take_screenshot(task_id, full_page=full_page, selector=selector)

    async def evaluate_js(self, javascript: str) -> Any:
        """Execute JavaScript and return the result."""
        return await self._page.evaluate(javascript)

    async def wait_for_element(self, selector: str, timeout_ms: int = 10_000) -> bool:
        """
        Wait for a CSS selector to appear on the page.

        Returns:
            True if element appeared within timeout, False otherwise.
        """
        try:
            await self._page.wait_for_selector(selector, timeout=timeout_ms)
            return True
        except Exception:
            return False

    async def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the page."""
        await self._humanizer.scroll_page(self._page, "down", distance=10_000, steps=10)

    async def _take_screenshot(
        self,
        name: str,
        full_page: bool = True,
        selector: Optional[str] = None,
    ) -> Optional[str]:
        """Internal screenshot helper."""
        try:
            screenshot_dir = settings.screenshot_dir
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = screenshot_dir / f"{name}.png"

            if selector:
                element = await self._page.query_selector(selector)
                if element:
                    await element.screenshot(path=str(path))
                else:
                    await self._page.screenshot(path=str(path), full_page=full_page)
            else:
                await self._page.screenshot(path=str(path), full_page=full_page)

            logger.debug("Screenshot saved: {}", path)
            return str(path)
        except Exception as exc:
            logger.warning("Screenshot failed: {}", exc)
            return None

    async def _get_title(self) -> Optional[str]:
        """Extract page title."""
        try:
            return await self._page.title()
        except Exception:
            return None

    async def _extract_text(self) -> Optional[str]:
        """Extract visible text content from the page."""
        try:
            return await self._page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
        except Exception:
            return None

    async def _extract_links(self) -> List[str]:
        """Extract all href links from the page."""
        try:
            links = await self._page.evaluate(
                """
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(href => href.startsWith('http'))
                    .slice(0, 200)
                """
            )
            return [str(lnk) for lnk in links]
        except Exception:
            return []
