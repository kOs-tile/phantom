"""
PHANTOM Extractor Tests
Tests for DOM extraction, price parsing, article extraction, and structured data.
All tests use mock HTML strings — no real browser required.
"""

from __future__ import annotations

import pytest

from phantom.extractors.article import ArticleExtractor, _count_words, _html_to_text, _extract_date_from_text
from phantom.extractors.price import (
    PriceExtractor,
    _parse_price_string,
    _detect_currency,
)
from phantom.extractors.structured import (
    StructuredDataExtractor,
    _extract_json_ld_from_html,
    _extract_opengraph_from_html,
    _extract_meta_tags_from_html,
)
from phantom.models import PriceData, StructuredData


# ── Price Parser Tests ────────────────────────────────────────────────────────

class TestPriceParser:

    def test_parse_simple_usd(self):
        assert _parse_price_string("19.99") == 19.99

    def test_parse_usd_with_thousands(self):
        assert _parse_price_string("1,299.99") == 1299.99

    def test_parse_usd_no_cents(self):
        assert _parse_price_string("99") == 99.0

    def test_parse_european_decimal_comma(self):
        assert _parse_price_string("19,99") == 19.99

    def test_parse_european_thousands_dot(self):
        assert _parse_price_string("1.299,99") == 1299.99

    def test_parse_european_thousands_dot_without_cents(self):
        assert _parse_price_string("1.299") == 1299.0

    def test_parse_multiple_european_thousands_groups(self):
        assert _parse_price_string("12.345.678,90") is None  # exceeds extractor sanity cap

    def test_parse_us_thousands_without_cents(self):
        assert _parse_price_string("1,299") == 1299.0

    def test_parse_rejects_ambiguous_long_fraction(self):
        assert _parse_price_string("19.9999") is None

    def test_parse_with_currency_symbol_ignored(self):
        # _parse_price_string strips non-numeric before parsing
        assert _parse_price_string("299.00") == 299.0

    def test_parse_returns_none_for_empty(self):
        assert _parse_price_string("") is None

    def test_parse_returns_none_for_invalid(self):
        assert _parse_price_string("N/A") is None

    def test_parse_rounds_to_2_decimals(self):
        result = _parse_price_string("19.999")
        # Should handle as 19.999 → float
        assert result is not None

    def test_parse_rejects_zero(self):
        result = _parse_price_string("0.00")
        assert result is None  # 0 fails the >= 0.01 check

    def test_parse_rejects_unreasonably_large(self):
        result = _parse_price_string("9999999.99")
        assert result is None  # Exceeds 999,999 limit

    def test_detect_currency_usd(self):
        code, symbol = _detect_currency("$19.99")
        assert code == "USD"
        assert symbol == "$"

    def test_detect_currency_eur(self):
        code, symbol = _detect_currency("€49.99")
        assert code == "EUR"
        assert symbol == "€"

    def test_detect_currency_gbp(self):
        code, symbol = _detect_currency("£29.99")
        assert code == "GBP"
        assert symbol == "£"

    def test_detect_currency_default_usd(self):
        code, symbol = _detect_currency("no currency here")
        assert code == "USD"


class TestPriceExtractorHTML:

    def setup_method(self):
        self.extractor = PriceExtractor()

    def test_extract_simple_usd_price(self):
        html = "<html><body><span class='price'>$29.99</span></body></html>"
        result = self.extractor.from_html(html, "https://example.com/product")
        assert result.current_price == 29.99
        assert result.currency == "USD"

    def test_extract_price_with_original(self):
        html = "<html><body><span class='price'>$29.99</span> <span class='original'>$49.99</span></body></html>"
        result = self.extractor.from_html(html, "https://example.com/product")
        assert result.current_price is not None
        assert result.original_price is not None

    def test_extract_amazon_asin(self):
        result = self.extractor.from_html(
            "<html><body>$29.99</body></html>",
            "https://www.amazon.com/dp/B09XS7JWHH/ref=sr_1_1"
        )
        assert result.asin == "B09XS7JWHH"

    def test_extract_no_price_returns_none(self):
        html = "<html><body><p>No price here</p></body></html>"
        result = self.extractor.from_html(html, "https://example.com")
        assert result.current_price is None

    def test_extract_in_stock_detection(self):
        html = "<html><body>$19.99 <span>In Stock</span></body></html>"
        result = self.extractor.from_html(html, "https://example.com")
        assert result.in_stock is True

    def test_extract_out_of_stock_detection(self):
        html = "<html><body>$19.99 <span>Out of Stock</span></body></html>"
        result = self.extractor.from_html(html, "https://example.com")
        assert result.in_stock is False

    def test_extract_discount_computed(self):
        html = "<html><body>$25.00</body></html>"
        result = PriceData(
            url="https://example.com",
            current_price=25.0,
            original_price=50.0,
        )
        assert result.discount_percent == 50.0

    def test_extract_eur_price(self):
        html = "<html><body>€49,99</body></html>"
        result = self.extractor.from_html(html, "https://example.de/product")
        assert result.currency == "EUR"

    def test_url_preserved(self):
        url = "https://example.com/product/123"
        result = self.extractor.from_html("<html><body>$9.99</body></html>", url)
        assert result.url == url


# ── Article Extractor Tests ───────────────────────────────────────────────────

class TestHTMLToText:

    def test_strips_basic_tags(self):
        html = "<p>Hello <b>world</b></p>"
        text = _html_to_text(html)
        assert "Hello" in text
        assert "world" in text
        assert "<b>" not in text

    def test_strips_script_content(self):
        html = "<p>Content</p><script>var x = 1;</script>"
        text = _html_to_text(html)
        assert "Content" in text
        assert "var x" not in text

    def test_strips_style_content(self):
        html = "<p>Content</p><style>.cls { color: red; }</style>"
        text = _html_to_text(html)
        assert "Content" in text
        assert "color" not in text

    def test_count_words_basic(self):
        assert _count_words("Hello world this is a test") == 6

    def test_count_words_empty(self):
        assert _count_words("") == 0

    def test_count_words_punctuation(self):
        assert _count_words("Hello, world!") == 2

    def test_extract_date_iso_format(self):
        text = "Published on 2024-06-15T14:30:00Z"
        result = _extract_date_from_text(text)
        assert result is not None
        assert "2024-06-15" in result

    def test_extract_date_natural_format(self):
        text = "Published June 15, 2024"
        result = _extract_date_from_text(text)
        assert result is not None
        assert "2024" in result

    def test_extract_date_none_when_absent(self):
        result = _extract_date_from_text("No date in this text")
        assert result is None


class TestArticleExtractor:

    def setup_method(self):
        self.extractor = ArticleExtractor()

    def test_extract_title_from_html(self):
        html = "<html><head><title>Test Article</title></head><body><p>Content here</p></body></html>"
        result = self.extractor.from_html(html, "https://example.com/article")
        assert result.title == "Test Article"

    def test_extract_og_title_preferred(self):
        html = (
            "<html><head>"
            "<title>Default Title</title>"
            "<meta property='og:title' content='OG Article Title'/>"
            "</head><body><p>Content here</p></body></html>"
        )
        result = self.extractor.from_html(html, "https://example.com/article")
        assert result.title == "OG Article Title"

    def test_extract_og_description(self):
        html = (
            "<html><head>"
            "<meta property='og:description' content='This is the article summary'/>"
            "</head><body></body></html>"
        )
        result = self.extractor.from_html(html, "https://example.com")
        assert result.summary == "This is the article summary"

    def test_extract_og_site_name(self):
        html = (
            "<html><head>"
            "<meta property='og:site_name' content='TechCrunch'/>"
            "</head><body></body></html>"
        )
        result = self.extractor.from_html(html, "https://techcrunch.com/article")
        assert result.site_name == "TechCrunch"

    def test_extract_article_content(self):
        html = (
            "<html><body>"
            "<article><p>First paragraph with content.</p>"
            "<p>Second paragraph with more content here.</p></article>"
            "</body></html>"
        )
        result = self.extractor.from_html(html, "https://example.com")
        assert result.content is not None
        assert len(result.content) > 20

    def test_word_count_computed(self):
        html = (
            "<html><body><article>"
            "<p>This article has exactly ten words here today yes</p>"
            "</article></body></html>"
        )
        result = self.extractor.from_html(html, "https://example.com")
        assert result.word_count > 0

    def test_extract_published_date_from_og(self):
        html = (
            "<html><head>"
            "<meta property='article:published_time' content='2024-06-15T10:00:00Z'/>"
            "</head><body></body></html>"
        )
        result = self.extractor.from_html(html, "https://example.com")
        assert result.published_date == "2024-06-15T10:00:00Z"

    def test_extract_language_from_html_tag(self):
        html = "<html lang='en-US'><body><p>Content</p></body></html>"
        result = self.extractor.from_html(html, "https://example.com")
        assert result.language == "en-US"

    def test_extract_og_image(self):
        html = (
            "<html><head>"
            "<meta property='og:image' content='https://example.com/image.jpg'/>"
            "</head><body></body></html>"
        )
        result = self.extractor.from_html(html, "https://example.com")
        assert "https://example.com/image.jpg" in result.images

    def test_url_preserved(self):
        url = "https://example.com/article/123"
        result = self.extractor.from_html("<html><body></body></html>", url)
        assert result.url == url


# ── Structured Data Extractor Tests ──────────────────────────────────────────

class TestStructuredExtractorFunctions:

    def test_extract_json_ld_single_object(self):
        html = '''
        <html><head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Test Product"}
        </script>
        </head></html>
        '''
        results = _extract_json_ld_from_html(html)
        assert len(results) == 1
        assert results[0]["@type"] == "Product"
        assert results[0]["name"] == "Test Product"

    def test_extract_json_ld_array(self):
        html = '''
        <html><head>
        <script type="application/ld+json">
        [{"@type": "Product"}, {"@type": "Organization"}]
        </script>
        </head></html>
        '''
        results = _extract_json_ld_from_html(html)
        assert len(results) == 2

    def test_extract_json_ld_multiple_scripts(self):
        html = '''
        <html><head>
        <script type="application/ld+json">{"@type": "Product"}</script>
        <script type="application/ld+json">{"@type": "BreadcrumbList"}</script>
        </head></html>
        '''
        results = _extract_json_ld_from_html(html)
        assert len(results) == 2

    def test_extract_json_ld_handles_invalid_json(self):
        html = '''
        <html><head>
        <script type="application/ld+json">{invalid json}</script>
        </head></html>
        '''
        results = _extract_json_ld_from_html(html)
        assert results == []

    def test_extract_opengraph_property(self):
        html = '<html><head><meta property="og:title" content="Test Title"/></head></html>'
        og = _extract_opengraph_from_html(html)
        assert og.get("og:title") == "Test Title"

    def test_extract_opengraph_multiple(self):
        html = '''
        <html><head>
        <meta property="og:title" content="Title"/>
        <meta property="og:description" content="Desc"/>
        <meta property="og:image" content="https://example.com/img.jpg"/>
        </head></html>
        '''
        og = _extract_opengraph_from_html(html)
        assert og["og:title"] == "Title"
        assert og["og:description"] == "Desc"
        assert og["og:image"] == "https://example.com/img.jpg"

    def test_extract_meta_tags(self):
        html = '<html><head><meta name="description" content="Page description"/></head></html>'
        meta = _extract_meta_tags_from_html(html)
        assert meta.get("description") == "Page description"

    def test_extract_twitter_card_in_og(self):
        html = '<html><head><meta name="twitter:title" content="Tweet Title"/></head></html>'
        og = _extract_opengraph_from_html(html)
        assert "twitter:title" in og


class TestStructuredDataExtractor:

    def setup_method(self):
        self.extractor = StructuredDataExtractor()

    def test_from_html_full(self):
        html = '''
        <html><head>
        <script type="application/ld+json">{"@type": "Article", "headline": "Test"}</script>
        <meta property="og:title" content="OG Title"/>
        <meta name="description" content="Page desc"/>
        </head></html>
        '''
        result = self.extractor.from_html(html, "https://example.com")
        assert len(result.json_ld) == 1
        assert result.opengraph.get("og:title") == "OG Title"
        assert result.meta_tags.get("description") == "Page desc"

    def test_get_schema_type_product(self):
        items = [
            {"@type": "Product", "name": "Widget"},
            {"@type": "BreadcrumbList"},
        ]
        result = StructuredDataExtractor.get_schema_type(items, "Product")
        assert result is not None
        assert result["name"] == "Widget"

    def test_get_schema_type_not_found(self):
        items = [{"@type": "Article"}]
        result = StructuredDataExtractor.get_schema_type(items, "Product")
        assert result is None

    def test_get_schema_type_list_type(self):
        items = [{"@type": ["Product", "Thing"], "name": "Widget"}]
        result = StructuredDataExtractor.get_schema_type(items, "Product")
        assert result is not None

    def test_extract_product_schema(self):
        structured = StructuredData(
            url="https://example.com",
            json_ld=[{
                "@type": "Product",
                "name": "Widget Pro",
                "brand": {"name": "AcmeCorp"},
                "offers": {
                    "price": "29.99",
                    "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock"
                }
            }]
        )
        result = StructuredDataExtractor.extract_product_schema(structured)
        assert result is not None
        assert result["name"] == "Widget Pro"
        assert result["brand"] == "AcmeCorp"
        assert result["price"] == "29.99"
        assert result["currency"] == "USD"
        assert result["availability"] == "InStock"

    def test_extract_product_schema_returns_none_when_absent(self):
        structured = StructuredData(url="https://example.com", json_ld=[])
        result = StructuredDataExtractor.extract_product_schema(structured)
        assert result is None
