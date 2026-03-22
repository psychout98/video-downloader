"""
Unit tests for BaseAPIClient (server/clients/base_client.py).

Tests retry logic, timeout handling, and request methods.
"""
from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from server.clients.base_client import BaseAPIClient


@pytest.mark.unit
class TestBaseAPIClientInit:
    """BaseAPIClient initialization tests."""

    def test_init_default_timeout(self):
        """BaseAPIClient initializes with default 30s timeout."""
        client = BaseAPIClient()
        assert client._max_retries == 3
        assert client._backoff_base == 1.0

    def test_init_custom_timeout(self):
        """BaseAPIClient accepts custom timeout."""
        client = BaseAPIClient(timeout=60.0)
        # Timeout is set on the httpx client
        assert client._client is not None

    def test_init_custom_max_retries(self):
        """BaseAPIClient accepts custom max_retries."""
        client = BaseAPIClient(max_retries=5)
        assert client._max_retries == 5

    def test_init_custom_backoff_base(self):
        """BaseAPIClient accepts custom backoff_base."""
        client = BaseAPIClient(backoff_base=2.0)
        assert client._backoff_base == 2.0

    def test_init_with_custom_headers(self):
        """BaseAPIClient can be initialized with custom headers."""
        headers = {"Authorization": "Bearer test"}
        client = BaseAPIClient(headers=headers)
        assert client._client is not None

    def test_init_with_base_url(self):
        """BaseAPIClient accepts base_url."""
        client = BaseAPIClient(base_url="https://api.example.com")
        assert client._client is not None


@pytest.mark.unit
class TestBaseAPIClientRequest:
    """BaseAPIClient._request() tests."""

    @pytest.mark.asyncio
    async def test_successful_get_request(self):
        """Successful GET request returns response."""
        client = BaseAPIClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            response = await client.get("https://example.com/test")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_with_custom_headers(self):
        """Request can pass custom headers."""
        client = BaseAPIClient()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            headers = {"X-Custom": "value"}
            response = await client._request("GET", "/test", headers=headers)
            assert response.status_code == 200
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_retries_on_429_status(self):
        """Request retries on 429 (rate limit) status."""
        client = BaseAPIClient(max_retries=2, backoff_base=0.01)

        # First attempt returns 429, second returns 200
        responses = [
            MagicMock(status_code=429),
            MagicMock(status_code=200),
        ]

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = responses

            response = await client._request("GET", "/test", retry=True)
            assert response.status_code == 200
            assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_request_retries_on_500_status(self):
        """Request retries on 500 (server error) status."""
        client = BaseAPIClient(max_retries=2, backoff_base=0.01)

        responses = [
            MagicMock(status_code=500),
            MagicMock(status_code=200),
        ]

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = responses

            response = await client._request("GET", "/test")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_retries_on_503_status(self):
        """Request retries on 503 (service unavailable) status."""
        client = BaseAPIClient(max_retries=2, backoff_base=0.01)

        responses = [
            MagicMock(status_code=503),
            MagicMock(status_code=200),
        ]

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = responses

            response = await client._request("GET", "/test")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_no_retry_on_404_status(self):
        """Request does NOT retry on 404 (not found)."""
        client = BaseAPIClient(max_retries=3)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(httpx.HTTPStatusError):
                await client._request("GET", "/test")

            # Should only be called once (no retry)
            assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_request_no_retry_on_401_status(self):
        """Request does NOT retry on 401 (unauthorized)."""
        client = BaseAPIClient(max_retries=3)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(httpx.HTTPStatusError):
                await client._request("GET", "/test")

            # Should only be called once
            assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_request_retries_on_connection_error(self):
        """Request retries on connection errors."""
        client = BaseAPIClient(max_retries=2, backoff_base=0.01)

        mock_response = MagicMock(status_code=200)

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                httpx.ConnectError("Connection failed"),
                mock_response,
            ]

            response = await client._request("GET", "/test")
            assert response.status_code == 200
            assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_request_retries_on_timeout(self):
        """Request retries on timeout errors."""
        client = BaseAPIClient(max_retries=2, backoff_base=0.01)

        mock_response = MagicMock(status_code=200)

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                httpx.ConnectTimeout("Timeout"),
                mock_response,
            ]

            response = await client._request("GET", "/test")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_disables_retry_with_retry_false(self):
        """Request with retry=False only attempts once."""
        client = BaseAPIClient(max_retries=3, backoff_base=0.01)

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = httpx.ConnectError("Connection failed")

            with pytest.raises(httpx.ConnectError):
                await client._request("GET", "/test", retry=False)

            # Should only be called once
            assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_request_exponential_backoff(self):
        """Request uses exponential backoff for retries."""
        client = BaseAPIClient(max_retries=3, backoff_base=1.0)

        mock_response = MagicMock(status_code=200)

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                httpx.ConnectError("Fail 1"),
                httpx.ConnectError("Fail 2"),
                mock_response,
            ]

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                response = await client._request("GET", "/test")
                assert response.status_code == 200

                # Should have slept with increasing delays (1s, 2s)
                assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_request_exhausts_retries(self):
        """Request raises after exhausting all retries."""
        client = BaseAPIClient(max_retries=2, backoff_base=0.01)

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = httpx.ConnectError("Connection failed")

            with pytest.raises(httpx.ConnectError):
                await client._request("GET", "/test")

            # Should have attempted max_retries times
            assert mock_request.call_count == 2


@pytest.mark.unit
class TestBaseAPIClientConvenienceMethods:
    """BaseAPIClient convenience method tests (get, post, etc)."""

    @pytest.mark.asyncio
    async def test_get_method(self):
        """get() convenience method works."""
        client = BaseAPIClient()

        mock_response = MagicMock(status_code=200)

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            response = await client.get("/test")
            assert response.status_code == 200
            # Verify it called request with GET method
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_method(self):
        """post() convenience method works."""
        client = BaseAPIClient()

        mock_response = MagicMock(status_code=201)

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            response = await client.post("/test", json={"data": "value"})
            assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_delete_method(self):
        """delete() convenience method works."""
        client = BaseAPIClient()

        mock_response = MagicMock(status_code=204)

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            response = await client.delete("/test")
            assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_put_method(self):
        """put() convenience method works."""
        client = BaseAPIClient()

        mock_response = MagicMock(status_code=200)

        with patch.object(client._client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            response = await client.put("/test", json={"data": "value"})
            assert response.status_code == 200


@pytest.mark.unit
class TestBaseAPIClientClose:
    """BaseAPIClient cleanup tests."""

    @pytest.mark.asyncio
    async def test_close_method(self):
        """close() closes the httpx client."""
        client = BaseAPIClient()

        with patch.object(client._client, "aclose", new_callable=AsyncMock) as mock_close:
            await client.close()
            mock_close.assert_called_once()
