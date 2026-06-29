"""
PHANTOM Browser Layer
Async Playwright session management, navigation, and DOM extraction.
"""

from phantom.browser.extractor import DOMExtractor
from phantom.browser.navigator import PageNavigator
from phantom.browser.session import BrowserSession

__all__ = ["BrowserSession", "PageNavigator", "DOMExtractor"]
