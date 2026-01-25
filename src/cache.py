"""
Redis caching layer for external API responses.
Reduces API calls and improves response times.

Usage:
    from cache import cache, cached

    # Initialize on startup
    await cache.connect()

    # Manual caching
    await cache.set("key", {"data": "value"}, category="track")
    data = await cache.get("key")

    # Decorator-based caching
    @cached(category="search")
    async def search_tracks(query: str):
        ...
"""

import json
import hashlib
import os
from typing import Optional, Any, Callable
from functools import wraps
from datetime import datetime

# Try to import redis, gracefully handle if not installed
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    aioredis = None


class CacheStats:
    """Track cache hit/miss statistics."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.start_time = datetime.utcnow()

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "errors": self.errors,
            "hit_rate": f"{self.hit_rate:.1%}",
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds()
        }


class CacheManager:
    """
    Redis-based cache for API responses.

    Falls back gracefully to no-op caching if Redis is unavailable,
    allowing the application to run without Redis dependency.
    """

    # TTL in seconds by category
    DEFAULT_TTL = {
        "track": 86400,           # 24 hours - track metadata rarely changes
        "audio_features": 86400,  # 24 hours - audio features are static
        "search": 3600,           # 1 hour - search results may update
        "artist": 86400,          # 24 hours
        "musicbrainz": 604800,    # 1 week - MB data is stable
        "wikidata": 604800,       # 1 week - Wikidata is stable
        "genius": 86400,          # 24 hours
        "recommendation": 300,    # 5 minutes - recommendations should be fresh
    }

    # Cache key prefix for namespacing
    PREFIX = "nexttrack:"

    def __init__(self):
        self._redis: Optional[Any] = None
        self._enabled = False
        self._fallback_cache: dict = {}  # In-memory fallback
        self._max_fallback_size = 1000
        self.stats = CacheStats()

    @property
    def is_enabled(self) -> bool:
        """Check if Redis caching is active."""
        return self._enabled

    async def connect(self, redis_url: Optional[str] = None) -> bool:
        """
        Connect to Redis server.

        Args:
            redis_url: Redis connection URL (default: from REDIS_URL env var)

        Returns:
            True if connected, False if unavailable
        """
        if not REDIS_AVAILABLE:
            print("⚠️  Redis package not installed - using in-memory fallback cache")
            print("   Install with: pip install redis")
            return False

        url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")

        try:
            self._redis = aioredis.from_url(
                url,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await self._redis.ping()
            self._enabled = True
            print(f"✅ Redis cache connected: {self._mask_url(url)}")
            return True

        except Exception as e:
            print(f"⚠️  Redis unavailable ({e}) - using in-memory fallback cache")
            self._enabled = False
            return False

    def _mask_url(self, url: str) -> str:
        """Mask password in Redis URL for logging."""
        if "@" in url:
            # URL has credentials
            parts = url.split("@")
            return f"redis://***@{parts[-1]}"
        return url

    def _make_key(self, key: str) -> str:
        """Create namespaced cache key."""
        return f"{self.PREFIX}{key}"

    def _hash_key(self, *args, **kwargs) -> str:
        """Create hash key from function arguments."""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
        return hashlib.md5(key_data.encode()).hexdigest()

    async def get(self, key: str) -> Optional[Any]:
        """
        Get cached value.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        full_key = self._make_key(key)

        try:
            if self._enabled and self._redis:
                data = await self._redis.get(full_key)
                if data:
                    self.stats.hits += 1
                    return json.loads(data)
                self.stats.misses += 1
                return None
            else:
                # Fallback to in-memory cache
                if full_key in self._fallback_cache:
                    entry = self._fallback_cache[full_key]
                    # Check if expired
                    if entry["expires"] > datetime.utcnow().timestamp():
                        self.stats.hits += 1
                        return entry["data"]
                    else:
                        del self._fallback_cache[full_key]
                self.stats.misses += 1
                return None

        except Exception as e:
            self.stats.errors += 1
            print(f"Cache get error: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        category: str = "track",
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set cached value.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            category: Category for TTL lookup
            ttl: Override TTL in seconds

        Returns:
            True if cached successfully
        """
        full_key = self._make_key(key)
        expire_seconds = ttl or self.DEFAULT_TTL.get(category, 3600)

        try:
            serialized = json.dumps(value)

            if self._enabled and self._redis:
                await self._redis.setex(full_key, expire_seconds, serialized)
                return True
            else:
                # Fallback to in-memory cache
                if len(self._fallback_cache) >= self._max_fallback_size:
                    # Evict oldest entries
                    self._evict_expired()

                self._fallback_cache[full_key] = {
                    "data": value,
                    "expires": datetime.utcnow().timestamp() + expire_seconds
                }
                return True

        except Exception as e:
            self.stats.errors += 1
            print(f"Cache set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a cached value."""
        full_key = self._make_key(key)

        try:
            if self._enabled and self._redis:
                await self._redis.delete(full_key)
            elif full_key in self._fallback_cache:
                del self._fallback_cache[full_key]
            return True
        except Exception as e:
            print(f"Cache delete error: {e}")
            return False

    async def clear(self, pattern: Optional[str] = None) -> int:
        """
        Clear cached values.

        Args:
            pattern: Optional pattern to match (e.g., "search:*")

        Returns:
            Number of keys deleted
        """
        try:
            if self._enabled and self._redis:
                if pattern:
                    full_pattern = self._make_key(pattern)
                    keys = await self._redis.keys(full_pattern)
                else:
                    keys = await self._redis.keys(f"{self.PREFIX}*")

                if keys:
                    return await self._redis.delete(*keys)
                return 0
            else:
                # Clear fallback cache
                if pattern:
                    full_pattern = self._make_key(pattern.replace("*", ""))
                    to_delete = [k for k in self._fallback_cache if k.startswith(full_pattern)]
                    for k in to_delete:
                        del self._fallback_cache[k]
                    return len(to_delete)
                else:
                    count = len(self._fallback_cache)
                    self._fallback_cache.clear()
                    return count

        except Exception as e:
            print(f"Cache clear error: {e}")
            return 0

    def _evict_expired(self):
        """Remove expired entries from fallback cache."""
        now = datetime.utcnow().timestamp()
        expired = [k for k, v in self._fallback_cache.items() if v["expires"] <= now]
        for k in expired:
            del self._fallback_cache[k]

        # If still too large, remove oldest
        if len(self._fallback_cache) >= self._max_fallback_size:
            sorted_keys = sorted(
                self._fallback_cache.keys(),
                key=lambda k: self._fallback_cache[k]["expires"]
            )
            for k in sorted_keys[:100]:  # Remove 100 oldest
                del self._fallback_cache[k]

    async def get_stats(self) -> dict:
        """Get cache statistics."""
        stats = self.stats.to_dict()
        stats["enabled"] = self._enabled
        stats["backend"] = "redis" if self._enabled else "in-memory"

        if not self._enabled:
            stats["fallback_size"] = len(self._fallback_cache)

        return stats

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._enabled = False


# Global cache instance
cache = CacheManager()


def cached(
    category: str = "track",
    key_prefix: Optional[str] = None,
    ttl: Optional[int] = None
):
    """
    Decorator for caching async function results.

    Usage:
        @cached(category="search")
        async def search_tracks(query: str) -> List[Track]:
            ...

        @cached(category="track", ttl=7200)  # 2 hour override
        async def get_track(track_id: str) -> Track:
            ...

    Args:
        category: Cache category for TTL
        key_prefix: Custom key prefix (default: function name)
        ttl: Override TTL in seconds
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            prefix = key_prefix or func.__name__
            key_hash = cache._hash_key(*args, **kwargs)
            cache_key = f"{prefix}:{key_hash}"

            # Try cache first
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Call function
            result = await func(*args, **kwargs)

            # Cache result if not None
            if result is not None:
                await cache.set(cache_key, result, category=category, ttl=ttl)

            return result

        # Add cache bypass method
        wrapper.nocache = func
        return wrapper

    return decorator


def cache_key(*parts) -> str:
    """
    Helper to create consistent cache keys.

    Usage:
        key = cache_key("track", track_id)
        key = cache_key("search", query, limit)
    """
    return ":".join(str(p) for p in parts)
