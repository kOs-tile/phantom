"""
PHANTOM Cache Layer
Redis-backed result store with in-memory fallback and TTL management.
"""

from phantom.cache.result_store import ResultStore

__all__ = ["ResultStore"]
