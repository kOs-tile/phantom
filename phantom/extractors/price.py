"""
PHANTOM Price Extractor
Extracts pricing information from e-commerce pages using regex patterns
and CSS selectors. Supports Amazon, eBay, Shopify, and generic sites.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from phantom.models import PriceData


# ── Price Regex Patterns ──────────────────────────────────────────────────────

# Matches: $19.99, $1,299.00, USD 19.99
_USD_PATTERN = re.compile(
    r"(?:USD\s*|US\$\s*|\$\s*)(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# Matches: €19,99  €1.299,99  EUR 19.99
_EUR_PATTERN = re.compile(
    r"(?:EUR\s*|€\s*)(\d{1,6}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)",
    re.IGNORECASE,
)

# Matches: £19.99  GBP 19.99
_GBP_PATTERN = re.compile(
    r"(?:GBP\s*|£\s*)(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# Matches: ¥1,299  JPY 1299
_JPY_PATTERN = re.compile(
    r"(?:JPY\s*|¥\s*)(\d{1,8}(?:,\d{3})*)",
    re.IGNORECASE,
)

# Generic: any price-looking string with currency symbol
_GENERIC_PRICE = re.compile(
    r"([\$€£¥₹])\s*(\d{1,6}(?:[,\.]\d{3})*(?:[,\.]\d{1,2})?)",
)

# Amazon ASIN pattern
_ASIN_PATTERN = re.compile(r"/dp/([A-Z0-9]{10})(?:/|$|\?)")

_CURRENCY_MAP: Dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
}

# ── CSS Selector Banks ────────────────────────────────────────────────────────

_AMAZON_SELECTORS: Dict[str, str] = {
    "current_price": "#priceblock_ourprice, #priceblock_dealprice, .a-price .a-offscreen, #apex_offerDisplay_desktop .a-price .a-offscreen",
    "original_price": ".a-text-price .a-offscreen, #priceblock_listprice",
    "product_title": "#productTitle",
    "in_stock": "#availability span",
}

_EBAY_SELECTORS: Dict[str, str] = {
    "current_price": ".x-price-primary .ux-textspans, #prcIsum, .vi-price",
    "original_price": ".x-price-approx__price .ux-textspans",
    "product_title": ".x-item-title__mainTitle, #itemTitle",
}

_GENERIC_SELECTORS: List[str] = [
    "[itemprop='price']",
    "[class*='price'][class*='current']",
    "[class*='price'][class*='sale']",
    "[class*='price']:not([class*='original']):not([class*='was']):not([class*='list'])",
    ".product-price",
    ".product__price",
    ".price-box .price",
    "span[data-price]",
    "meta[itemprop='price']",
]

_ORIGINAL_PRICE_SELECTORS: List[str] = [
    "[class*='original']:not([class*='price'])",
    "[class*='was-price']",
    "[class*='strikethrough']",
    "[class*='list-price']",
    "s[class*='price']",
    "del[class*='price']",
    ".original-price",
    ".price--compare",
]


def _parse_price_string(text: str) -> Optional[float]:
    """
    Parse a price string into a float value.
    Handles both US format ($1,299.99) and European format (€1.299,99).
    """
    if not text:
        return None

    # Remove whitespace and common noise chars
    cleaned = re.sub(r"[^\d.,]", "", text.strip())

    if not cleaned:
        return None

    comma_count = cleaned.count(",")
    dot_count = cleaned.count(".")

    if comma_count and dot_count:
        # The right-most separator is normally the decimal separator;
        # all earlier separators are grouping separators.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif comma_count:
        parts = cleaned.split(",")
        if comma_count == 1 and len(parts[1]) in (1, 2):
            cleaned = ".".join(parts)
        elif all(len(group) == 3 for group in parts[1:]):
            cleaned = "".join(parts)
        else:
            return None
    elif dot_count:
        parts = cleaned.split(".")
        if dot_count == 1 and len(parts[1]) in (1, 2):
            pass
        elif all(len(group) == 3 for group in parts[1:]):
            # Common European grouping without a decimal comma: 1.299 → 1299.
            cleaned = "".join(parts)
        else:
            return None

    try:
        value = float(cleaned)
        # Sanity check: prices should be reasonable
        if 0.01 <= value <= 999_999:
            return round(value, 2)
    except (ValueError, TypeError):
        pass

    return None


def _detect_currency(text: str) -> Tuple[str, str]:
    """Detect currency code and symbol from price text."""
    for symbol, code in _CURRENCY_MAP.items():
        if symbol in text:
            return code, symbol
    if "USD" in text.upper():
        return "USD", "$"
    if "EUR" in text.upper():
        return "EUR", "€"
    if "GBP" in text.upper():
        return "GBP", "£"
    return "USD", "$"


class PriceExtractor:
    """
    Extracts pricing data from e-commerce pages.

    Can operate on raw HTML strings or live Playwright page objects.
    Auto-detects Amazon, eBay, and falls back to generic extraction.
    """

    def from_html(self, html: str, url: str) -> PriceData:
        """
        Extract price data from raw HTML.

        Args:
            html: Full page HTML string
            url: Page URL (used for ASIN detection and site classification)

        Returns:
            PriceData with current_price, original_price, currency, etc.
        """
        result = PriceData(url=url)

        # Detect Amazon ASIN
        asin_match = _ASIN_PATTERN.search(url)
        if asin_match:
            result.asin = asin_match.group(1)

        # Try regex extraction from common patterns
        all_prices = self._extract_prices_from_html(html)

        if all_prices:
            # First match is usually current price
            result.current_price = all_prices[0]
            result.price_text = self._find_raw_price_text(html, all_prices[0])

            if len(all_prices) > 1:
                # Second price that's higher is usually original/was-price
                for p in all_prices[1:]:
                    if p > all_prices[0]:
                        result.original_price = p
                        break

        # Detect currency
        currency_text = html[:5000]  # Check early in document for currency symbols
        result.currency, result.currency_symbol = _detect_currency(currency_text)

        # Detect stock status
        stock_patterns = [
            (r"\bin\s+stock\b", True),
            (r"\badd\s+to\s+cart\b", True),
            (r"\bonly\s+\d+\s+left\b", True),
            (r"\bout\s+of\s+stock\b", False),
            (r"\bunavailable\b", False),
            (r"\bcurrently\s+unavailable\b", False),
        ]
        lower_html = html.lower()
        for pattern, in_stock in stock_patterns:
            if re.search(pattern, lower_html):
                result.in_stock = in_stock
                break

        logger.debug(
            "Price extraction: url={} price={} currency={}",
            url,
            result.current_price,
            result.currency,
        )
        return result

    def _extract_prices_from_html(self, html: str) -> List[float]:
        """Extract all price values found in HTML using regex patterns."""
        prices: List[float] = []
        seen: set = set()

        patterns = [_USD_PATTERN, _EUR_PATTERN, _GBP_PATTERN]
        for pattern in patterns:
            for match in pattern.finditer(html):
                price_str = match.group(1)
                value = _parse_price_string(price_str)
                if value and value not in seen:
                    prices.append(value)
                    seen.add(value)

        # Fallback: generic currency symbol detection
        if not prices:
            for match in _GENERIC_PRICE.finditer(html):
                price_str = match.group(2)
                value = _parse_price_string(price_str)
                if value and value not in seen:
                    prices.append(value)
                    seen.add(value)

        return sorted(prices)

    def _find_raw_price_text(self, html: str, price: float) -> Optional[str]:
        """Try to find the raw price string that matches a parsed value."""
        # Look for common price display patterns near the price value
        price_int = int(price)
        pattern = re.compile(
            rf"[\$€£¥]?\s*{price_int}[.,]\d{{1,2}}",
        )
        match = pattern.search(html)
        if match:
            return match.group(0).strip()
        return f"{price:.2f}"

    async def from_page(self, page: Any, url: str) -> PriceData:
        """
        Extract price from a live Playwright page.

        Tries site-specific selectors first, falls back to generic and regex.
        """
        result = PriceData(url=url)

        # Detect Amazon ASIN
        asin_match = _ASIN_PATTERN.search(url)
        if asin_match:
            result.asin = asin_match.group(1)

        # Choose selector bank based on URL
        if "amazon." in url:
            selectors = _AMAZON_SELECTORS
        elif "ebay." in url:
            selectors = _EBAY_SELECTORS
        else:
            selectors = {}

        # Try site-specific selectors
        if selectors:
            result = await self._extract_with_selectors(page, url, selectors, result)

        # If still no price, try generic selectors
        if result.current_price is None:
            result = await self._try_generic_selectors(page, url, result)

        # Last resort: regex on page HTML
        if result.current_price is None:
            try:
                html = await page.content()
                fallback = self.from_html(html, url)
                result.current_price = fallback.current_price
                result.original_price = fallback.original_price
                result.price_text = fallback.price_text
                result.currency = fallback.currency
                result.currency_symbol = fallback.currency_symbol
                result.in_stock = fallback.in_stock
            except Exception as exc:
                logger.warning("Fallback HTML price extraction failed: {}", exc)

        logger.info(
            "Page price extraction: url={} price={} original={}",
            url,
            result.current_price,
            result.original_price,
        )
        return result

    async def _extract_with_selectors(
        self,
        page: Any,
        url: str,
        selectors: Dict[str, str],
        result: PriceData,
    ) -> PriceData:
        for field, selector in selectors.items():
            try:
                element = await page.query_selector(selector)
                if not element:
                    continue
                text = await element.inner_text()
                if not text:
                    text = await element.get_attribute("content") or ""

                if field == "current_price":
                    result.current_price = _parse_price_string(text)
                    result.price_text = text.strip()
                    result.currency, result.currency_symbol = _detect_currency(text)
                elif field == "original_price":
                    result.original_price = _parse_price_string(text)
                elif field == "product_title":
                    result.product_title = text.strip()
                elif field == "in_stock":
                    lower = text.lower()
                    result.in_stock = "in stock" in lower or "add to cart" in lower
            except Exception:
                pass
        return result

    async def _try_generic_selectors(
        self,
        page: Any,
        url: str,
        result: PriceData,
    ) -> PriceData:
        for selector in _GENERIC_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element:
                    # Try content attribute first (meta tags), then inner text
                    text = await element.get_attribute("content")
                    if not text:
                        text = await element.inner_text()

                    price = _parse_price_string(text or "")
                    if price:
                        result.current_price = price
                        result.price_text = (text or "").strip()
                        result.currency, result.currency_symbol = _detect_currency(text or "")
                        break
            except Exception:
                pass

        for selector in _ORIGINAL_PRICE_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    price = _parse_price_string(text or "")
                    if price and (result.current_price is None or price > result.current_price):
                        result.original_price = price
                        break
            except Exception:
                pass

        return result
