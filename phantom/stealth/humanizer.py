"""
PHANTOM Human Behavior Simulator
Simulates human mouse movement, random delays, scroll patterns, and form fill
behavior to evade bot detection based on behavioral analysis.
"""

from __future__ import annotations

import asyncio
import math
import random
from typing import List, Optional, Tuple

from loguru import logger


Point = Tuple[float, float]


def _bezier_curve(
    p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 20
) -> List[Point]:
    """
    Compute points along a cubic Bezier curve.
    Used for realistic mouse path generation.

    Args:
        p0: Start point
        p1: Control point 1
        p2: Control point 2
        p3: End point
        steps: Number of interpolation steps

    Returns:
        List of (x, y) points along the curve.
    """
    points: List[Point] = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = (
            mt ** 3 * p0[0]
            + 3 * mt ** 2 * t * p1[0]
            + 3 * mt * t ** 2 * p2[0]
            + t ** 3 * p3[0]
        )
        y = (
            mt ** 3 * p0[1]
            + 3 * mt ** 2 * t * p1[1]
            + 3 * mt * t ** 2 * p2[1]
            + t ** 3 * p3[1]
        )
        points.append((round(x, 2), round(y, 2)))
    return points


class HumanBehaviorSimulator:
    """
    Simulates realistic human interaction patterns in a browser.

    All methods are async to integrate cleanly with Playwright's async API.
    Actual mouse/scroll actions are injected via a Playwright Page object
    when provided; otherwise they run as pure simulation (useful for testing).
    """

    def __init__(
        self,
        min_delay_ms: int = 50,
        max_delay_ms: int = 300,
        typo_probability: float = 0.05,
        seed: Optional[int] = None,
    ) -> None:
        self._rng = random.Random(seed)
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.typo_probability = typo_probability

    # ── Delays ────────────────────────────────────────────────────────────────

    async def micro_delay(self) -> float:
        """Sleep for a random micro-delay. Returns actual ms slept."""
        ms = self._rng.uniform(self.min_delay_ms, self.max_delay_ms)
        await asyncio.sleep(ms / 1000)
        return ms

    async def thinking_pause(self) -> float:
        """Longer 'reading/thinking' pause (500ms–2s)."""
        ms = self._rng.uniform(500, 2000)
        await asyncio.sleep(ms / 1000)
        return ms

    async def page_load_wait(self) -> float:
        """Wait as if a human is waiting for a page to load (1–3s)."""
        ms = self._rng.uniform(1000, 3000)
        await asyncio.sleep(ms / 1000)
        return ms

    def random_delay_ms(self) -> float:
        """Return a random delay value in ms without sleeping."""
        return self._rng.uniform(self.min_delay_ms, self.max_delay_ms)

    # ── Mouse Movement ────────────────────────────────────────────────────────

    def generate_mouse_path(
        self,
        start: Point,
        end: Point,
        steps: int = 25,
        jitter: float = 0.15,
    ) -> List[Point]:
        """
        Generate a realistic Bezier-curve mouse path from start to end.

        Args:
            start: (x, y) starting position
            end: (x, y) target position
            steps: Number of intermediate points
            jitter: Magnitude of random control point deviation (0–1)

        Returns:
            Ordered list of (x, y) waypoints.
        """
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dist = math.sqrt(dx ** 2 + dy ** 2)

        # Control points with randomized jitter
        jitter_scale = dist * jitter
        cp1: Point = (
            start[0] + dx * 0.3 + self._rng.uniform(-jitter_scale, jitter_scale),
            start[1] + dy * 0.3 + self._rng.uniform(-jitter_scale, jitter_scale),
        )
        cp2: Point = (
            start[0] + dx * 0.7 + self._rng.uniform(-jitter_scale, jitter_scale),
            start[1] + dy * 0.7 + self._rng.uniform(-jitter_scale, jitter_scale),
        )

        return _bezier_curve(start, cp1, cp2, end, steps=steps)

    async def move_mouse_to(self, page: object, target: Point) -> None:
        """
        Move mouse to target using a Bezier path.
        `page` should be a Playwright Page instance.
        """
        try:
            # Get current position — default to top-left corner
            current: Point = (
                self._rng.uniform(0, 100),
                self._rng.uniform(0, 100),
            )
            path = self.generate_mouse_path(current, target, steps=self._rng.randint(15, 30))

            for point in path:
                await page.mouse.move(point[0], point[1])  # type: ignore[attr-defined]
                if self._rng.random() < 0.1:  # occasional micro-pause during movement
                    await asyncio.sleep(self._rng.uniform(0.01, 0.05))
        except Exception as exc:
            logger.warning("Mouse movement failed: {}", exc)

    async def human_click(self, page: object, selector: str) -> None:
        """
        Click an element with realistic human-like behavior:
        move to element, brief pause, then click.
        """
        try:
            element = await page.query_selector(selector)  # type: ignore[attr-defined]
            if element:
                box = await element.bounding_box()
                if box:
                    # Click slightly off-center for realism
                    x = box["x"] + box["width"] * self._rng.uniform(0.3, 0.7)
                    y = box["y"] + box["height"] * self._rng.uniform(0.3, 0.7)
                    await self.move_mouse_to(page, (x, y))
                    await asyncio.sleep(self._rng.uniform(0.05, 0.15))
                    await page.mouse.click(x, y)  # type: ignore[attr-defined]
                    await self.micro_delay()
        except Exception as exc:
            logger.warning("Human click failed: {}", exc)

    # ── Scrolling ─────────────────────────────────────────────────────────────

    async def scroll_page(
        self,
        page: object,
        direction: str = "down",
        distance: Optional[int] = None,
        steps: int = 5,
    ) -> None:
        """
        Scroll page with ease-in-out timing pattern.

        Args:
            page: Playwright Page instance
            direction: 'down' or 'up'
            distance: Total scroll distance in pixels (default: random 200-800)
            steps: Number of scroll increments
        """
        if distance is None:
            distance = self._rng.randint(200, 800)

        sign = 1 if direction == "down" else -1
        chunk = (distance * sign) // steps

        try:
            for i in range(steps):
                # Ease-in-out timing: slow at start and end, faster in middle
                progress = i / max(steps - 1, 1)
                ease = math.sin(progress * math.pi)
                delay = 0.05 + (1 - ease) * 0.1

                await page.mouse.wheel(0, chunk)  # type: ignore[attr-defined]
                await asyncio.sleep(delay)
        except Exception as exc:
            logger.warning("Scroll failed: {}", exc)

    async def read_and_scroll(self, page: object, sections: int = 3) -> None:
        """
        Simulate reading a page: scroll down in sections with pauses.
        """
        for _ in range(sections):
            await self.scroll_page(page, "down", distance=self._rng.randint(300, 600))
            await asyncio.sleep(self._rng.uniform(1.5, 4.0))  # reading pause

    # ── Form Interaction ──────────────────────────────────────────────────────

    async def type_text(
        self,
        page: object,
        selector: str,
        text: str,
        clear_first: bool = True,
    ) -> None:
        """
        Type text character by character with variable speed and optional typos.

        Args:
            page: Playwright Page instance
            selector: CSS selector for input element
            text: Text to type
            clear_first: Whether to clear the field before typing
        """
        try:
            element = await page.query_selector(selector)  # type: ignore[attr-defined]
            if not element:
                logger.warning("Selector not found for typing: {}", selector)
                return

            await element.click()
            await asyncio.sleep(self._rng.uniform(0.1, 0.3))

            if clear_first:
                await page.keyboard.press("Control+a")  # type: ignore[attr-defined]
                await asyncio.sleep(0.05)

            for char in text:
                # Occasionally introduce a typo and correct it
                if self._rng.random() < self.typo_probability:
                    typo = self._get_adjacent_key(char)
                    if typo:
                        await page.keyboard.type(typo)  # type: ignore[attr-defined]
                        await asyncio.sleep(self._rng.uniform(0.1, 0.3))
                        await page.keyboard.press("Backspace")  # type: ignore[attr-defined]
                        await asyncio.sleep(self._rng.uniform(0.05, 0.15))

                await page.keyboard.type(char)  # type: ignore[attr-defined]
                # Variable typing speed: 50–200ms per character
                await asyncio.sleep(self._rng.uniform(0.05, 0.20))

        except Exception as exc:
            logger.warning("Type text failed: {}", exc)

    def _get_adjacent_key(self, char: str) -> Optional[str]:
        """Return a keyboard-adjacent character for realistic typo simulation."""
        adjacency: dict[str, str] = {
            "a": "sq", "b": "vn", "c": "xv", "d": "sf", "e": "wr",
            "f": "dg", "g": "fh", "h": "gj", "i": "uo", "j": "hk",
            "k": "jl", "l": "k;", "m": "n,", "n": "mb", "o": "ip",
            "p": "o[", "q": "wa", "r": "et", "s": "ad", "t": "ry",
            "u": "yi", "v": "cb", "w": "qe", "x": "zc", "y": "tu",
            "z": "xa", " ": "  ",
        }
        lower = char.lower()
        if lower in adjacency and adjacency[lower]:
            return self._rng.choice(adjacency[lower])
        return None

    # ── Timing Profiles ───────────────────────────────────────────────────────

    def get_request_delay(self, base_ms: int = 1500) -> float:
        """
        Calculate delay before next request.
        Adds Gaussian noise around the base delay.
        """
        noise = self._rng.gauss(0, base_ms * 0.2)
        return max(base_ms + noise, 500) / 1000  # return seconds

    async def random_viewport_scroll(self, page: object) -> None:
        """Perform a small random scroll to simulate viewport adjustment."""
        try:
            amount = self._rng.randint(50, 150)
            direction = self._rng.choice(["down", "down", "down", "up"])
            await self.scroll_page(page, direction, distance=amount, steps=2)
        except Exception as exc:
            logger.debug("Viewport scroll: {}", exc)
