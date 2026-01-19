"""In-memory cache service with TTL support."""

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class CacheEntry:
    """A single cache entry with value and expiration time."""

    value: bytes
    expires_at: float


@dataclass
class PDFCache:
    """
    In-memory cache for generated PDFs with TTL support.

    Parameters
    ----------
    ttl_seconds : int
        Time-to-live for cache entries in seconds. Default is 1 hour.
    max_entries : int
        Maximum number of entries to store. Default is 100.
    """

    ttl_seconds: int = 3600  # 1 hour default
    max_entries: int = 100
    _cache: dict[str, CacheEntry] = field(default_factory=dict, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def get(self, token: str) -> bytes | None:
        """
        Get a cached PDF by token.

        Parameters
        ----------
        token : str
            The rendering token used as cache key.

        Returns
        -------
        bytes | None
            The cached PDF bytes if found and not expired, None otherwise.
        """
        with self._lock:
            entry = self._cache.get(token)
            if entry is None:
                return None

            # Check if expired
            if time.time() > entry.expires_at:
                del self._cache[token]
                return None

            return entry.value

    def set(self, token: str, pdf_bytes: bytes) -> None:
        """
        Store a PDF in the cache.

        Parameters
        ----------
        token : str
            The rendering token used as cache key.
        pdf_bytes : bytes
            The PDF content to cache.
        """
        with self._lock:
            # Clean up expired entries if we're at capacity
            if len(self._cache) >= self.max_entries:
                self._cleanup_expired()

            # If still at capacity, remove oldest entry
            if len(self._cache) >= self.max_entries:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].expires_at)
                del self._cache[oldest_key]

            self._cache[token] = CacheEntry(
                value=pdf_bytes,
                expires_at=time.time() + self.ttl_seconds,
            )

    def _cleanup_expired(self) -> None:
        """Remove all expired entries from the cache."""
        current_time = time.time()
        expired_keys = [key for key, entry in self._cache.items() if current_time > entry.expires_at]
        for key in expired_keys:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()

    def stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns
        -------
        dict
            Dictionary with cache stats (size, max_entries, ttl).
        """
        with self._lock:
            return {
                "size": len(self._cache),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
            }


# Global cache instance
pdf_cache = PDFCache()
