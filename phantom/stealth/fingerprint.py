"""
PHANTOM Fingerprint Generator
Generates realistic, randomized browser fingerprints to evade bot detection.
Covers User-Agent, viewport, timezone, locale, and HTTP headers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from loguru import logger

from phantom.models import BrowserProfile, ViewportSize


# ── Chrome UA Templates ───────────────────────────────────────────────────────

_CHROME_VERSIONS = [
    "120.0.6099.130",
    "121.0.6167.184",
    "122.0.6261.128",
    "123.0.6312.122",
    "124.0.6367.207",
    "125.0.6422.141",
]

_OS_TEMPLATES: Dict[str, List[str]] = {
    "windows": [
        "Windows NT 10.0; Win64; x64",
        "Windows NT 11.0; Win64; x64",
        "Windows NT 10.0; WOW64",
    ],
    "mac": [
        "Macintosh; Intel Mac OS X 10_15_7",
        "Macintosh; Intel Mac OS X 13_5_1",
        "Macintosh; Intel Mac OS X 14_2_1",
    ],
    "linux": [
        "X11; Linux x86_64",
        "X11; Ubuntu; Linux x86_64",
        "X11; Linux aarch64",
    ],
}

_ACCEPT_LANGUAGE_POOLS: Dict[str, List[str]] = {
    "en-US": ["en-US,en;q=0.9", "en-US,en;q=0.9,es;q=0.8", "en-US,en;q=0.8"],
    "en-GB": ["en-GB,en;q=0.9", "en-GB,en-US;q=0.8,en;q=0.7"],
    "de-DE": ["de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"],
    "fr-FR": ["fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"],
    "es-ES": ["es-ES,es;q=0.9,en-US;q=0.8,en;q=0.6"],
    "ja-JP": ["ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7"],
}

_TIMEZONE_LOCALE_MAP: Dict[str, str] = {
    "en-US": "America/New_York",
    "en-GB": "Europe/London",
    "de-DE": "Europe/Berlin",
    "fr-FR": "Europe/Paris",
    "es-ES": "Europe/Madrid",
    "ja-JP": "Asia/Tokyo",
}

_VIEWPORT_SIZES: List[Tuple[int, int]] = [
    (1366, 768),
    (1440, 900),
    (1536, 864),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
    (1280, 800),
    (1280, 720),
]

_VIEWPORT_WEIGHTS = [25, 20, 15, 10, 20, 5, 3, 2]  # approximate real-world distribution


@dataclass
class BrowserFingerprint:
    """A complete, self-consistent browser fingerprint."""
    user_agent: str
    viewport: Tuple[int, int]
    locale: str
    timezone_id: str
    accept_language: str
    color_scheme: str
    device_scale_factor: float
    platform: str
    chrome_version: str
    os_type: str
    extra_headers: Dict[str, str] = field(default_factory=dict)

    def to_browser_profile(self) -> BrowserProfile:
        """Convert to a BrowserProfile Pydantic model."""
        return BrowserProfile(
            user_agent=self.user_agent,
            viewport=ViewportSize(width=self.viewport[0], height=self.viewport[1]),
            locale=self.locale,
            timezone_id=self.timezone_id,
            color_scheme=self.color_scheme,
            device_scale_factor=self.device_scale_factor,
            has_touch=False,
            extra_http_headers={
                "Accept-Language": self.accept_language,
                **self.extra_headers,
            },
        )


class FingerprintGenerator:
    """
    Generates realistic, randomized browser fingerprints.

    Each fingerprint is internally consistent — timezone matches locale,
    User-Agent OS matches platform, etc.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)

    def generate(
        self,
        os_preference: Optional[str] = None,
        locale_preference: Optional[str] = None,
    ) -> BrowserFingerprint:
        """
        Generate a new randomized browser fingerprint.

        Args:
            os_preference: Force a specific OS type ('windows', 'mac', 'linux').
            locale_preference: Force a specific locale (e.g. 'en-US').

        Returns:
            A BrowserFingerprint with all fields consistently populated.
        """
        # Select OS
        os_type = os_preference or self._rng.choice(["windows", "windows", "mac", "linux"])
        os_string = self._rng.choice(_OS_TEMPLATES[os_type])

        # Select Chrome version
        chrome_version = self._rng.choice(_CHROME_VERSIONS)
        major_version = chrome_version.split(".")[0]

        # Build User-Agent
        user_agent = (
            f"Mozilla/5.0 ({os_string}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_version} Safari/537.36"
        )

        # Select viewport (weighted)
        viewport = self._rng.choices(_VIEWPORT_SIZES, weights=_VIEWPORT_WEIGHTS, k=1)[0]

        # Select locale
        locale = locale_preference or self._rng.choice(list(_ACCEPT_LANGUAGE_POOLS.keys()))
        accept_language = self._rng.choice(_ACCEPT_LANGUAGE_POOLS[locale])
        timezone_id = _TIMEZONE_LOCALE_MAP.get(locale, "America/New_York")

        # Platform string (matches OS)
        platform_map = {
            "windows": "Win32",
            "mac": "MacIntel",
            "linux": "Linux x86_64",
        }
        platform = platform_map[os_type]

        # Device scale factor — Retina for Mac, usually 1.0 for Windows
        if os_type == "mac":
            scale = self._rng.choice([1.0, 2.0])
        else:
            scale = self._rng.choice([1.0, 1.0, 1.25, 1.5])

        # Extra headers that real browsers send
        extra_headers: Dict[str, str] = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            f"Sec-Ch-Ua": f'"Chromium";v="{major_version}", "Google Chrome";v="{major_version}", "Not=A?Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": f'"{platform_map[os_type].replace("Win32", "Windows").replace("MacIntel", "macOS").replace("Linux x86_64", "Linux")}"',
        }

        fp = BrowserFingerprint(
            user_agent=user_agent,
            viewport=viewport,
            locale=locale,
            timezone_id=timezone_id,
            accept_language=accept_language,
            color_scheme="light",
            device_scale_factor=scale,
            platform=platform,
            chrome_version=chrome_version,
            os_type=os_type,
            extra_headers=extra_headers,
        )

        logger.debug(
            "Generated fingerprint: chrome={} os={} locale={} viewport={}x{}",
            chrome_version,
            os_type,
            locale,
            viewport[0],
            viewport[1],
        )
        return fp

    def generate_batch(self, count: int) -> List[BrowserFingerprint]:
        """Generate multiple distinct fingerprints."""
        return [self.generate() for _ in range(count)]

    @staticmethod
    def get_chrome_version_from_ua(user_agent: str) -> Optional[str]:
        """Extract Chrome version string from a User-Agent string."""
        import re
        match = re.search(r"Chrome/(\d+\.\d+\.\d+\.\d+)", user_agent)
        return match.group(1) if match else None

    @staticmethod
    def is_valid_user_agent(user_agent: str) -> bool:
        """Validate that a User-Agent string looks like a real Chrome browser."""
        required = ["Mozilla/5.0", "AppleWebKit", "Chrome/", "Safari/537.36"]
        return all(token in user_agent for token in required)
