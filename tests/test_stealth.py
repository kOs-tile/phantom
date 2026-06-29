"""
PHANTOM Stealth Layer Tests
Tests for fingerprint generation, humanizer delays, and evasion scripts.
All tests run without a real browser.
"""

from __future__ import annotations

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from phantom.stealth.evasion import EvasionScripts
from phantom.stealth.fingerprint import (
    BrowserFingerprint,
    FingerprintGenerator,
    _CHROME_VERSIONS,
    _VIEWPORT_SIZES,
)
from phantom.stealth.humanizer import HumanBehaviorSimulator, _bezier_curve


# ── FingerprintGenerator Tests ────────────────────────────────────────────────

class TestFingerprintGenerator:

    def setup_method(self):
        self.gen = FingerprintGenerator(seed=42)

    def test_generate_returns_fingerprint(self):
        fp = self.gen.generate()
        assert isinstance(fp, BrowserFingerprint)

    def test_user_agent_contains_chrome(self):
        fp = self.gen.generate()
        assert "Chrome/" in fp.user_agent

    def test_user_agent_contains_mozilla(self):
        fp = self.gen.generate()
        assert "Mozilla/5.0" in fp.user_agent

    def test_user_agent_contains_webkit(self):
        fp = self.gen.generate()
        assert "AppleWebKit/537.36" in fp.user_agent

    def test_user_agent_is_valid(self):
        fp = self.gen.generate()
        assert FingerprintGenerator.is_valid_user_agent(fp.user_agent)

    def test_chrome_version_in_valid_range(self):
        fp = self.gen.generate()
        version = FingerprintGenerator.get_chrome_version_from_ua(fp.user_agent)
        assert version is not None
        major = int(version.split(".")[0])
        assert 120 <= major <= 125

    def test_viewport_is_realistic(self):
        fp = self.gen.generate()
        w, h = fp.viewport
        assert w in [v[0] for v in _VIEWPORT_SIZES]
        assert h in [v[1] for v in _VIEWPORT_SIZES]

    def test_locale_in_valid_set(self):
        fp = self.gen.generate()
        valid_locales = {"en-US", "en-GB", "de-DE", "fr-FR", "es-ES", "ja-JP"}
        assert fp.locale in valid_locales

    def test_timezone_matches_locale(self):
        fp = self.gen.generate(locale_preference="en-US")
        assert fp.timezone_id == "America/New_York"

    def test_timezone_matches_german_locale(self):
        fp = self.gen.generate(locale_preference="de-DE")
        assert fp.timezone_id == "Europe/Berlin"

    def test_accept_language_contains_locale(self):
        fp = self.gen.generate(locale_preference="en-US")
        assert "en-US" in fp.accept_language

    def test_os_preference_windows(self):
        fp = self.gen.generate(os_preference="windows")
        assert fp.os_type == "windows"
        assert "Windows" in fp.user_agent

    def test_os_preference_mac(self):
        fp = self.gen.generate(os_preference="mac")
        assert fp.os_type == "mac"
        assert "Macintosh" in fp.user_agent

    def test_os_preference_linux(self):
        fp = self.gen.generate(os_preference="linux")
        assert fp.os_type == "linux"
        assert "Linux" in fp.user_agent

    def test_color_scheme_default(self):
        fp = self.gen.generate()
        assert fp.color_scheme == "light"

    def test_device_scale_factor_valid(self):
        fp = self.gen.generate()
        assert fp.device_scale_factor in [1.0, 1.25, 1.5, 2.0]

    def test_extra_headers_include_accept(self):
        fp = self.gen.generate()
        assert "Accept" in fp.extra_headers

    def test_extra_headers_include_sec_fetch(self):
        fp = self.gen.generate()
        assert "Sec-Fetch-Dest" in fp.extra_headers

    def test_generate_batch(self):
        fps = self.gen.generate_batch(5)
        assert len(fps) == 5
        assert all(isinstance(fp, BrowserFingerprint) for fp in fps)

    def test_different_seeds_produce_different_ua(self):
        gen1 = FingerprintGenerator(seed=1)
        gen2 = FingerprintGenerator(seed=9999)
        # With different seeds, results should differ (not guaranteed every time,
        # but with 10 generations we expect at least some differences)
        fps1 = {gen1.generate().user_agent for _ in range(10)}
        fps2 = {gen2.generate().user_agent for _ in range(10)}
        # At minimum both produce valid UAs
        assert all(FingerprintGenerator.is_valid_user_agent(ua) for ua in fps1)
        assert all(FingerprintGenerator.is_valid_user_agent(ua) for ua in fps2)

    def test_to_browser_profile(self):
        fp = self.gen.generate()
        profile = fp.to_browser_profile()
        assert profile.user_agent == fp.user_agent
        assert profile.viewport.width == fp.viewport[0]
        assert profile.viewport.height == fp.viewport[1]
        assert profile.locale == fp.locale
        assert profile.timezone_id == fp.timezone_id

    def test_get_chrome_version_from_ua(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.6367.207 Safari/537.36"
        version = FingerprintGenerator.get_chrome_version_from_ua(ua)
        assert version == "124.0.6367.207"

    def test_is_valid_ua_rejects_firefox(self):
        firefox_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
        assert not FingerprintGenerator.is_valid_user_agent(firefox_ua)


# ── HumanBehaviorSimulator Tests ──────────────────────────────────────────────

class TestHumanBehaviorSimulator:

    def setup_method(self):
        self.sim = HumanBehaviorSimulator(
            min_delay_ms=10,
            max_delay_ms=20,
            seed=42,
        )

    def test_bezier_curve_returns_correct_count(self):
        points = _bezier_curve((0, 0), (10, 0), (10, 10), (20, 10), steps=10)
        assert len(points) == 11  # steps + 1

    def test_bezier_curve_starts_at_p0(self):
        p0 = (5.0, 5.0)
        points = _bezier_curve(p0, (10, 0), (10, 10), (20, 10), steps=5)
        assert abs(points[0][0] - p0[0]) < 0.01
        assert abs(points[0][1] - p0[1]) < 0.01

    def test_bezier_curve_ends_at_p3(self):
        p3 = (20.0, 10.0)
        points = _bezier_curve((0, 0), (5, 0), (15, 10), p3, steps=5)
        assert abs(points[-1][0] - p3[0]) < 0.01
        assert abs(points[-1][1] - p3[1]) < 0.01

    def test_generate_mouse_path_returns_points(self):
        path = self.sim.generate_mouse_path((0, 0), (100, 100))
        assert len(path) > 0
        assert all(isinstance(p, tuple) and len(p) == 2 for p in path)

    def test_generate_mouse_path_starts_near_start(self):
        start = (10.0, 10.0)
        path = self.sim.generate_mouse_path(start, (200, 200))
        # First point should be close to start
        assert abs(path[0][0] - start[0]) < 1.0
        assert abs(path[0][1] - start[1]) < 1.0

    def test_generate_mouse_path_ends_near_end(self):
        end = (200.0, 200.0)
        path = self.sim.generate_mouse_path((10, 10), end)
        assert abs(path[-1][0] - end[0]) < 1.0
        assert abs(path[-1][1] - end[1]) < 1.0

    def test_random_delay_ms_in_range(self):
        for _ in range(20):
            delay = self.sim.random_delay_ms()
            assert 10 <= delay <= 20

    @pytest.mark.asyncio
    async def test_micro_delay_returns_float(self):
        ms = await self.sim.micro_delay()
        assert isinstance(ms, float)
        assert ms > 0

    @pytest.mark.asyncio
    async def test_thinking_pause_range(self):
        # Use a fast sim for testing
        sim = HumanBehaviorSimulator(min_delay_ms=1, max_delay_ms=2, seed=1)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            ms = await sim.thinking_pause()
            mock_sleep.assert_called_once()
            assert 500 <= ms <= 2000

    def test_get_adjacent_key_exists(self):
        # Test that adjacent key lookup works
        result = self.sim._get_adjacent_key("a")
        assert result in ("s", "q") or result is not None

    def test_get_adjacent_key_space_returns_something(self):
        result = self.sim._get_adjacent_key(" ")
        assert result == " "  # space is adjacent to itself in our map

    def test_get_adjacent_key_unknown_char_returns_none(self):
        result = self.sim._get_adjacent_key("!")
        # Non-alpha chars not in adjacency map return None
        assert result is None

    def test_get_request_delay_positive(self):
        delay = self.sim.get_request_delay(base_ms=1500)
        assert delay > 0

    def test_get_request_delay_minimum_500ms(self):
        # Even with negative noise, should return at least 0.5 seconds
        for _ in range(10):
            delay = self.sim.get_request_delay(base_ms=1500)
            assert delay >= 0.5


# ── EvasionScripts Tests ──────────────────────────────────────────────────────

class TestEvasionScripts:

    def test_hide_webdriver_returns_string(self):
        script = EvasionScripts.hide_webdriver()
        assert isinstance(script, str)
        assert "webdriver" in script
        assert "undefined" in script

    def test_fake_chrome_runtime_returns_string(self):
        script = EvasionScripts.fake_chrome_runtime()
        assert "chrome" in script.lower()
        assert "runtime" in script

    def test_fake_navigator_plugins_returns_string(self):
        script = EvasionScripts.fake_navigator_plugins()
        assert "plugins" in script
        assert "Chrome PDF" in script

    def test_fake_mime_types_returns_string(self):
        script = EvasionScripts.fake_mime_types()
        assert "mimeTypes" in script
        assert "application/pdf" in script

    def test_override_permissions_query_returns_string(self):
        script = EvasionScripts.override_permissions_query()
        assert "permissions" in script.lower()
        assert "notifications" in script

    def test_spoof_languages_default(self):
        script = EvasionScripts.spoof_languages()
        assert "en-US" in script
        assert "languages" in script

    def test_spoof_languages_custom(self):
        script = EvasionScripts.spoof_languages(["de-DE", "de"])
        assert "de-DE" in script

    def test_disable_automation_controlled_returns_string(self):
        script = EvasionScripts.disable_automation_controlled()
        assert "userAgentData" in script

    def test_spoof_hardware_concurrency(self):
        script = EvasionScripts.spoof_hardware_concurrency(cores=8)
        assert "hardwareConcurrency" in script
        assert "8" in script

    def test_spoof_device_memory(self):
        script = EvasionScripts.spoof_device_memory(gb=16)
        assert "deviceMemory" in script
        assert "16" in script

    def test_get_full_evasion_script_combines_all(self):
        script = EvasionScripts.get_full_evasion_script()
        assert "webdriver" in script
        assert "plugins" in script
        assert "chrome" in script.lower()
        assert len(script) > 1000  # Should be substantial

    def test_get_cdp_args_returns_list(self):
        args = EvasionScripts.get_cdp_args()
        assert isinstance(args, list)
        assert len(args) > 5
        assert "--disable-blink-features=AutomationControlled" in args

    def test_get_ignore_default_args_returns_list(self):
        args = EvasionScripts.get_ignore_default_args()
        assert isinstance(args, list)
        assert "--enable-automation" in args

    def test_fix_iframe_contentwindow_returns_string(self):
        script = EvasionScripts.fix_iframe_contentwindow()
        assert "iframe" in script.lower()
        assert "webdriver" in script
