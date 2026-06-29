"""
PHANTOM Extractors
Domain-specific data extractors: price, article, structured (Schema.org/OG/JSON-LD).
"""

from phantom.extractors.article import ArticleExtractor
from phantom.extractors.price import PriceExtractor
from phantom.extractors.structured import StructuredDataExtractor

__all__ = ["PriceExtractor", "ArticleExtractor", "StructuredDataExtractor"]
