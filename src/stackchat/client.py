"""HTTP client for the Princeton University Library Blacklight catalog.

Single shared AsyncClient with:
- HTTP/2
- Polite User-Agent header
- tenacity retry on 429 / 5xx / transport errors
- TTL LRU cache (5 min) to avoid duplicate calls when a model iterates filters
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

import httpx
from cachetools import TTLCache
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from stackchat.settings import settings

logger = logging.getLogger(__name__)

# Cache is module-level but sized from settings at import time.
_cache: TTLCache[str, Any] = TTLCache(
    maxsize=settings.cache_max_size, ttl=settings.cache_ttl
)
_cache_lock = asyncio.Lock()

# Module-level client singleton; created on first use, reused afterward.
_client: httpx.AsyncClient | None = None


def _build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.catalog_url,
        http2=True,
        timeout=settings.http_timeout,
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    )


def _get_client() -> httpx.AsyncClient:
    """Return the module-level AsyncClient, creating it if necessary."""
    global _client
    if _client is None or _client.is_closed:
        _client = _build_client()
    return _client


async def close_client() -> None:
    """Close the shared client (call during server shutdown)."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


# ── Retry predicate ───────────────────────────────────────────────────────────


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return False


def _retrying(fn):  # type: ignore[no-untyped-def]
    """Apply tenacity retry decorator for catalog HTTP calls."""
    return retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(settings.retry_attempts),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        reraise=True,
    )(fn)


# ── Cache helpers ─────────────────────────────────────────────────────────────


def _cache_key(path: str, params: list[tuple[str, str]]) -> str:
    raw = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params))
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Core request functions ────────────────────────────────────────────────────


@_retrying
async def _get_json(path: str, params: list[tuple[str, str]]) -> Any:
    """Issue a GET request and return parsed JSON, bypassing the cache."""
    client = _get_client()
    response = await client.get(path, params=params)
    response.raise_for_status()
    return response.json()


async def get_json_cached(path: str, params: list[tuple[str, str]]) -> Any:
    """Return parsed JSON for *path*+*params*, using the in-process cache."""
    key = _cache_key(path, params)
    async with _cache_lock:
        if key in _cache:
            logger.debug("cache hit: %s", path)
            return _cache[key]

    result = await _get_json(path, params)

    async with _cache_lock:
        _cache[key] = result

    return result


async def catalog_search(params: list[tuple[str, str]]) -> Any:
    """GET /catalog.json with *params*."""
    return await get_json_cached("/catalog.json", params)


async def catalog_record(record_id: str) -> Any:
    """GET /catalog/{id}.json for a single record."""
    return await get_json_cached(f"/catalog/{record_id}.json", [])


async def catalog_facet(facet_field: str, params: list[tuple[str, str]]) -> Any:
    """GET /catalog/facet/{field}.json for facet enumeration."""
    return await get_json_cached(f"/catalog/facet/{facet_field}.json", params)


async def catalog_browse(index_path: str, params: list[tuple[str, str]]) -> Any:
    """GET a /browse/{index}.json endpoint."""
    return await get_json_cached(index_path, params)
