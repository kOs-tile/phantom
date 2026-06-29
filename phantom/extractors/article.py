"""
PHANTOM Article Extractor
Readability-style article content extraction from news/blog pages.
Extracts title, author, date, content, word count, and metadata.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional
from html.parser import HTMLParser

from loguru import logger

from phantom.models import ArticleData


# ── Content Heuristics ────────────────────────────────────────────────────────

# Common article content container classes/IDs
_CONTENT_SELECTORS = [
    "article",
    "[itemprop='articleBody']",
    ".article-body",
    ".article-content",
    ".entry-content",
    ".post-content",
    ".story-body",
    ".article__body",
    ".content-body",
    ".article-text",
    "main article",
    "#article-body",
    "#story-body",
    ".prose",
]

_TITLE_SELECTORS = [
    "h1[itemprop='headline']",
    ".article-title h1",
    ".entry-title",
    ".post-title",
    "article h1",
    "main h1",
    "h1",
]

_AUTHOR_SELECTORS = [
    "[itemprop='author'] [itemprop='name']",
    "[itemprop='author']",
    "[rel='author']",
    ".author-name",
    ".byline-name",
    ".article-author",
    "[class*='author']",
    ".byline",
]

_DATE_SELECTORS = [
    "time[itemprop='datePublished']",
    "time[datetime]",
    "[itemprop='datePublished']",
    "[itemprop='dateModified']",
    ".publish-date",
    ".article-date",
    ".byline-date",
    "[class*='date']:not([class*='update'])",
    "time",
]


class _TextStripper(HTMLParser):
    """Minimal HTML to plain text stripper."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "noscript", "nav", "header", "footer"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "nav", "header", "footer"):
            self._skip = False
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self.parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self.parts)


def _html_to_text(html: str) -> str:
    """Convert HTML fragment to clean plain text."""
    stripper = _TextStripper()
    try:
        stripper.feed(html)
        text = stripper.get_text()
        # Normalize whitespace
        text = re.sub(r" {2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        # Fallback: strip all tags
        return re.sub(r"<[^>]+>", " ", html).strip()


def _count_words(text: str) -> int:
    """Count words in a text string."""
    return len(re.findall(r"\b\w+\b", text))


def _extract_date_from_text(text: str) -> Optional[str]:
    """Try to extract a date string from arbitrary text."""
    patterns = [
        r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?)?\b",  # ISO 8601
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b",  # "June 15, 2024"
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",  # MM/DD/YYYY
        r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


class ArticleExtractor:
    """
    Extracts structured article data from news and blog pages.

    Supports both live Playwright pages and raw HTML extraction.
    """

    def from_html(self, html: str, url: str) -> ArticleData:
        """
        Extract article data from raw HTML.

        Args:
            html: Full page HTML
            url: Source URL

        Returns:
            ArticleData with title, author, content, word count, etc.
        """
        result = ArticleData(url=url)

        # Extract Open Graph / meta fallbacks
        og_title = self._extract_meta_value(html, ["og:title", "twitter:title"])
        og_author = self._extract_meta_value(html, ["author", "article:author"])
        og_date = self._extract_meta_value(html, ["article:published_time", "datePublished"])
        og_site = self._extract_meta_value(html, ["og:site_name"])
        og_description = self._extract_meta_value(html, ["og:description", "description"])

        # Extract title from <title> tag
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            result.title = title_match.group(1).strip()

        # Prefer OG title
        if og_title:
            result.title = og_title

        result.author = og_author
        result.published_date = og_date
        result.site_name = og_site
        result.summary = og_description

        # Extract main content — look for <article> or common content divs
        content_html = self._find_main_content(html)
        if content_html:
            result.content = _html_to_text(content_html)
            result.word_count = _count_words(result.content or "")

        # Date fallback: scan visible text
        if not result.published_date and result.content:
            result.published_date = _extract_date_from_text(result.content[:500])

        # Extract images
        result.images = self._extract_image_urls(html)

        # Language detection (basic)
        lang_match = re.search(r'<html[^>]*lang=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if lang_match:
            result.language = lang_match.group(1)

        logger.debug(
            "Article extraction: url={} words={} title={}",
            url,
            result.word_count,
            (result.title or "")[:50],
        )
        return result

    def _find_main_content(self, html: str) -> Optional[str]:
        """Find the main article content block in raw HTML."""
        # Try <article> tag first
        article_match = re.search(
            r"<article[^>]*>(.*?)</article>",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if article_match:
            return article_match.group(1)

        # Common content div patterns
        content_patterns = [
            r'<div[^>]+(?:class|id)[^>]*(?:article-body|entry-content|post-content|story-body|article__body|content-body)[^>]*>(.*?)</div\s*>',
            r'<main[^>]*>(.*?)</main>',
        ]

        for pattern in content_patterns:
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1)
                # Only return if it has substantial content
                text = _html_to_text(content)
                if len(text) > 200:
                    return content

        # Last resort: extract all paragraph text
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL)
        if paragraphs:
            return " ".join(paragraphs)

        return None

    def _extract_meta_value(self, html: str, names: List[str]) -> Optional[str]:
        """Extract content from meta tags by name or property."""
        for name in names:
            pattern = re.compile(
                rf'<meta[^>]+(?:name|property)=["\'](?:{re.escape(name)})["\'][^>]+content=["\']([^"\']+)["\']',
                re.IGNORECASE,
            )
            match = pattern.search(html)
            if not match:
                # Try reversed attribute order
                pattern2 = re.compile(
                    rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:{re.escape(name)})["\']',
                    re.IGNORECASE,
                )
                match = pattern2.search(html)
            if match:
                return match.group(1).strip()
        return None

    def _extract_image_urls(self, html: str) -> List[str]:
        """Extract image URLs from the page."""
        # Prefer OG image
        og_image = self._extract_meta_value(html, ["og:image", "twitter:image"])
        images = []
        if og_image:
            images.append(og_image)

        # Extract article images
        img_pattern = re.compile(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
            re.IGNORECASE,
        )
        for match in img_pattern.finditer(html):
            src = match.group(1)
            if src.startswith("http") and src not in images:
                # Skip tracking pixels and icons (small files)
                if not re.search(r"\.(gif|ico)$|1x1|pixel|tracking", src, re.IGNORECASE):
                    images.append(src)
                    if len(images) >= 10:
                        break

        return images

    async def from_page(self, page: Any, url: str) -> ArticleData:
        """
        Extract article data from a live Playwright page.
        Uses DOM traversal for more accurate extraction than HTML parsing.
        """
        result = ArticleData(url=url)

        try:
            # Title
            for selector in _TITLE_SELECTORS:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        result.title = (await el.inner_text()).strip()
                        break
                except Exception:
                    pass

            # Author
            for selector in _AUTHOR_SELECTORS:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        result.author = (await el.inner_text()).strip()
                        break
                except Exception:
                    pass

            # Date
            for selector in _DATE_SELECTORS:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        date_text = await el.get_attribute("datetime")
                        if not date_text:
                            date_text = (await el.inner_text()).strip()
                        result.published_date = date_text
                        break
                except Exception:
                    pass

            # Content
            for selector in _CONTENT_SELECTORS:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        html_content = await el.inner_html()
                        text = _html_to_text(html_content)
                        if len(text) > 200:
                            result.content = text
                            result.word_count = _count_words(text)
                            break
                except Exception:
                    pass

            # Meta tags
            meta_data = await page.evaluate(
                """
                () => {
                    const metas = {};
                    document.querySelectorAll('meta[name], meta[property]').forEach(m => {
                        const key = m.getAttribute('name') || m.getAttribute('property');
                        const val = m.getAttribute('content');
                        if (key && val) metas[key] = val;
                    });
                    return metas;
                }
                """
            )
            if meta_data:
                result.site_name = meta_data.get("og:site_name")
                result.summary = meta_data.get("og:description") or meta_data.get("description")
                if not result.published_date:
                    result.published_date = (
                        meta_data.get("article:published_time")
                        or meta_data.get("datePublished")
                    )

            # Language
            try:
                result.language = await page.evaluate(
                    "() => document.documentElement.lang || navigator.language"
                )
            except Exception:
                pass

        except Exception as exc:
            logger.error("Page article extraction failed: {}", exc)

        logger.info(
            "Article extracted: url={} words={}", url, result.word_count
        )
        return result
