"""
PHANTOM Structured Data Extractor
Extracts JSON-LD, OpenGraph meta tags, Schema.org microdata,
and other structured semantic data from web pages.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from phantom.models import StructuredData


# ── OpenGraph Properties ──────────────────────────────────────────────────────

_OG_PROPERTIES = [
    "og:title", "og:type", "og:url", "og:image", "og:description",
    "og:site_name", "og:locale", "og:video", "og:audio",
    "article:author", "article:published_time", "article:modified_time",
    "article:section", "article:tag",
    "product:price:amount", "product:price:currency",
    "twitter:card", "twitter:title", "twitter:description", "twitter:image",
    "twitter:site", "twitter:creator",
]


def _extract_json_ld_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Extract all JSON-LD blocks from raw HTML.

    Handles multiple <script type="application/ld+json"> tags
    and both single objects and arrays.
    """
    results: List[Dict[str, Any]] = []
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                results.extend([d for d in data if isinstance(d, dict)])
            elif isinstance(data, dict):
                results.append(data)
        except json.JSONDecodeError as exc:
            logger.debug("JSON-LD parse error: {}", exc)
    return results


def _extract_opengraph_from_html(html: str) -> Dict[str, str]:
    """Extract OpenGraph and Twitter card meta properties from raw HTML."""
    og: Dict[str, str] = {}

    # Match <meta property="..." content="...">
    property_pattern = re.compile(
        r'<meta[^>]+property=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
        re.IGNORECASE,
    )
    for match in property_pattern.finditer(html):
        key = match.group(1).lower()
        value = match.group(2).strip()
        if key and value:
            og[key] = value

    # Also handle reversed attribute order
    property_pattern2 = re.compile(
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    for match in property_pattern2.finditer(html):
        value = match.group(1).strip()
        key = match.group(2).lower()
        if key and value and key not in og:
            og[key] = value

    # Match <meta name="..." content="..."> (for Twitter and general meta)
    name_pattern = re.compile(
        r'<meta[^>]+name=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
        re.IGNORECASE,
    )
    for match in name_pattern.finditer(html):
        key = match.group(1).lower()
        value = match.group(2).strip()
        if key and value and key not in og:
            og[key] = value

    return og


def _extract_meta_tags_from_html(html: str) -> Dict[str, str]:
    """Extract general <meta name="..." content="..."> pairs."""
    meta: Dict[str, str] = {}
    patterns = [
        re.compile(
            r'<meta[^>]+name=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
            re.IGNORECASE,
        ),
        re.compile(
            r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']([^"\']+)["\']',
            re.IGNORECASE,
        ),
    ]
    for i, pattern in enumerate(patterns):
        for match in pattern.finditer(html):
            if i == 0:
                key, value = match.group(1).lower(), match.group(2).strip()
            else:
                value, key = match.group(1).strip(), match.group(2).lower()
            if key and value and key not in meta:
                meta[key] = value
    return meta


class StructuredDataExtractor:
    """
    Extracts structured semantic data from web pages.

    Supports:
    - JSON-LD (Schema.org)
    - OpenGraph / Facebook
    - Twitter Cards
    - Standard <meta> tags
    - Schema.org microdata (via live page)
    """

    def from_html(self, html: str, url: str) -> StructuredData:
        """
        Extract all structured data from raw HTML.

        Args:
            html: Full page HTML
            url: Source URL

        Returns:
            StructuredData with json_ld, opengraph, and meta_tags populated.
        """
        result = StructuredData(url=url)

        result.json_ld = _extract_json_ld_from_html(html)
        result.opengraph = _extract_opengraph_from_html(html)
        result.meta_tags = _extract_meta_tags_from_html(html)

        logger.debug(
            "Structured extraction: url={} json_ld={} og_keys={} meta_keys={}",
            url,
            len(result.json_ld),
            len(result.opengraph),
            len(result.meta_tags),
        )
        return result

    async def from_page(self, page: Any, url: str) -> StructuredData:
        """
        Extract structured data from a live Playwright page.
        Uses browser-side DOM traversal for microdata extraction.
        """
        result = StructuredData(url=url)

        try:
            # JSON-LD via DOM
            raw_scripts: Any = await page.evaluate(
                """
                () => Array.from(
                    document.querySelectorAll('script[type="application/ld+json"]')
                ).map(s => s.textContent)
                """
            )
            for script_text in (raw_scripts or []):
                try:
                    data = json.loads(script_text)
                    if isinstance(data, list):
                        result.json_ld.extend([d for d in data if isinstance(d, dict)])
                    elif isinstance(data, dict):
                        result.json_ld.append(data)
                except json.JSONDecodeError:
                    pass

            # OpenGraph + Meta via DOM
            meta_data: Any = await page.evaluate(
                """
                () => {
                    const data = {};
                    document.querySelectorAll('meta[property], meta[name]').forEach(m => {
                        const key = (m.getAttribute('property') || m.getAttribute('name') || '').toLowerCase();
                        const val = m.getAttribute('content') || '';
                        if (key && val) data[key] = val;
                    });
                    return data;
                }
                """
            )
            if meta_data:
                for key, value in meta_data.items():
                    if key.startswith(("og:", "article:", "twitter:", "fb:")):
                        result.opengraph[key] = str(value)
                    else:
                        result.meta_tags[key] = str(value)

            # Microdata via DOM (Schema.org itemscope/itemtype)
            microdata: Any = await page.evaluate(
                """
                () => {
                    const items = [];
                    document.querySelectorAll('[itemscope]').forEach(scope => {
                        const item = {};
                        const itemtype = scope.getAttribute('itemtype');
                        if (itemtype) item['@type'] = itemtype.split('/').pop();
                        scope.querySelectorAll('[itemprop]').forEach(prop => {
                            const name = prop.getAttribute('itemprop');
                            const value = prop.getAttribute('content')
                                || prop.getAttribute('href')
                                || prop.getAttribute('src')
                                || prop.innerText;
                            if (name && value) item[name] = value.trim();
                        });
                        if (Object.keys(item).length > 1) items.push(item);
                    });
                    return items;
                }
                """
            )
            if microdata and isinstance(microdata, list):
                result.microdata = [dict(item) for item in microdata]

        except Exception as exc:
            logger.error("Page structured data extraction failed: {}", exc)
            # Fallback to HTML extraction
            try:
                html = await page.content()
                fallback = self.from_html(html, url)
                result.json_ld = fallback.json_ld
                result.opengraph = fallback.opengraph
                result.meta_tags = fallback.meta_tags
            except Exception:
                pass

        logger.info(
            "Structured data: url={} json_ld={} og_keys={} microdata={}",
            url,
            len(result.json_ld),
            len(result.opengraph),
            len(result.microdata),
        )
        return result

    @staticmethod
    def get_schema_type(json_ld_items: List[Dict[str, Any]], schema_type: str) -> Optional[Dict[str, Any]]:
        """
        Find the first JSON-LD item matching a Schema.org @type.

        Args:
            json_ld_items: List of JSON-LD objects
            schema_type: Schema.org type name (e.g. 'Product', 'Article', 'BreadcrumbList')

        Returns:
            First matching item, or None.
        """
        for item in json_ld_items:
            item_type = item.get("@type", "")
            if isinstance(item_type, list):
                if any(schema_type.lower() in t.lower() for t in item_type):
                    return item
            elif isinstance(item_type, str):
                if schema_type.lower() in item_type.lower():
                    return item
        return None

    @staticmethod
    def extract_product_schema(structured: StructuredData) -> Optional[Dict[str, Any]]:
        """
        Extract product details from JSON-LD Product schema.

        Returns dict with name, price, currency, availability, etc.
        """
        product = StructuredDataExtractor.get_schema_type(structured.json_ld, "Product")
        if not product:
            return None

        result: Dict[str, Any] = {
            "name": product.get("name"),
            "description": product.get("description"),
            "brand": None,
            "price": None,
            "currency": None,
            "availability": None,
            "rating": None,
            "review_count": None,
        }

        # Brand
        brand = product.get("brand")
        if isinstance(brand, dict):
            result["brand"] = brand.get("name")
        elif isinstance(brand, str):
            result["brand"] = brand

        # Offers / price
        offers = product.get("offers", product.get("offer"))
        if isinstance(offers, dict):
            result["price"] = offers.get("price") or offers.get("lowPrice")
            result["currency"] = offers.get("priceCurrency")
            availability = offers.get("availability", "")
            result["availability"] = availability.split("/")[-1] if "/" in str(availability) else availability
        elif isinstance(offers, list) and offers:
            first_offer = offers[0]
            result["price"] = first_offer.get("price")
            result["currency"] = first_offer.get("priceCurrency")

        # Ratings
        aggregate_rating = product.get("aggregateRating")
        if isinstance(aggregate_rating, dict):
            result["rating"] = aggregate_rating.get("ratingValue")
            result["review_count"] = aggregate_rating.get("reviewCount")

        return {k: v for k, v in result.items() if v is not None}
