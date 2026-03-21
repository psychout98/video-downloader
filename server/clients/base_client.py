"""
Shared HTTP base client with automatic retry, exponential backoff, and timeouts.

All API clients (TMDB, Torrentio, Real-Debrid) inherit from this to get
consistent, reliable request handling instead of each rolling their own.

Retry behaviour
---------------
- Retries on: ConnectError, ConnectTimeout, ReadTimeout, 429, 500-504, 520-524
- Does NOT retry: 400, 401, 403, 404 (raises immediately)
- Exponential backoff: 1s, 2s, 4s (configurable base)
- Structured logging on every retry attempt
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# HTTP status codes that warrant a retry (server-side transient errors)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504, 520, 521, 522, 524}


class BaseAPIClient:
    """Async HTTP client with built-in retry and exponential backoff."""

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
    ):
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._client_name = type(self).__name__

        client_kwargs: dict[str, Any] = {"timeout": timeout}
        if base_url:
            client_kwargs["base_url"] = base_url
        if headers:
            client_kwargs["headers"] = headers
        if params:
            client_kwargs["params"] = params

        self._client = httpx.AsyncClient(**client_kwargs)

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Core request with retry
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        retry: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with automatic retry on transient failures.

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, DELETE, etc.)
        url : str
            URL or path (resolved against base_url if set).
        retry : bool
            Set to False to disable retry for this specific call.
        **kwargs
            Passed through to httpx (params, data, json, headers, etc.)
        """
        max_attempts = self._max_retries if retry else 1
        last_exc: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                response = await self._client.request(method, url, **kwargs)

                # Check for retryable HTTP status codes
                if response.status_code in _RETRYABLE_STATUS and attempt < max_attempts - 1:
                    delay = self._backoff_base * (2 ** attempt)
                    logger.info(
                        "%s %s %s returned %d — retrying in %.1fs (attempt %d/%d)",
                        self._client_name, method, url,
                        response.status_code, delay, attempt + 1, max_attempts,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable errors: raise immediately
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError:
                # Already raised by raise_for_status — let it propagate
                raise

            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.PoolTimeout,
            ) as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    delay = self._backoff_base * (2 ** attempt)
                    logger.info(
                        "%s %s %s failed (%s) — retrying in %.1fs (attempt %d/%d)",
                        self._client_name, method, url,
                        type(exc).__name__, delay, attempt + 1, max_attempts,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        "%s %s %s failed after %d attempts: %s",
                        self._client_name, method, url, max_attempts, exc,
                    )

        # All retries exhausted
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("DELETE", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("PUT", url, **kwargs)
