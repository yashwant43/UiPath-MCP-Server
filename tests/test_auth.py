"""
Tests for authentication strategies, token caching, and concurrent refresh safety.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from uipath_mcp.auth import (
    CloudAuthStrategy,
    PATAuthStrategy,
    UiPathAuthError,
    _token_cache,
)


class TestCloudAuth:

    @respx.mock
    async def test_obtains_token_on_first_call(
        self, cloud_settings, mock_token_response
    ):
        """First call should POST to the token endpoint and cache the result."""
        respx.post(cloud_settings.cloud_token_url).mock(
            return_value=httpx.Response(200, json=mock_token_response)
        )
        auth = CloudAuthStrategy(cloud_settings)
        async with httpx.AsyncClient() as client:
            token = await auth.get_token(client)

        assert token == "eyJ.test.token"
        assert _token_cache.is_valid

    @respx.mock
    async def test_cached_token_avoids_second_request(
        self, cloud_settings, mock_token_response
    ):
        """Second call with a valid token should NOT hit the network."""
        route = respx.post(cloud_settings.cloud_token_url).mock(
            return_value=httpx.Response(200, json=mock_token_response)
        )
        auth = CloudAuthStrategy(cloud_settings)
        async with httpx.AsyncClient() as client:
            t1 = await auth.get_token(client)
            t2 = await auth.get_token(client)

        assert t1 == t2
        assert route.call_count == 1  # Only one HTTP call

    @respx.mock
    async def test_concurrent_calls_refresh_token_only_once(
        self, cloud_settings, mock_token_response
    ):
        """
        10 concurrent coroutines seeing an expired token should trigger
        exactly ONE token refresh, not 10.
        """
        call_count = 0

        def count_and_respond(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=mock_token_response)

        respx.post(cloud_settings.cloud_token_url).mock(side_effect=count_and_respond)

        auth = CloudAuthStrategy(cloud_settings)
        async with httpx.AsyncClient() as client:
            tokens = await asyncio.gather(*[auth.get_token(client) for _ in range(10)])

        assert all(t == "eyJ.test.token" for t in tokens)
        assert call_count == 1, f"Expected 1 token request, got {call_count}"

    @respx.mock
    async def test_raises_auth_error_on_401(self, cloud_settings):
        """Bad credentials should raise UiPathAuthError with actionable detail."""
        respx.post(cloud_settings.cloud_token_url).mock(
            return_value=httpx.Response(401, json={"error": "invalid_client"})
        )
        auth = CloudAuthStrategy(cloud_settings)
        async with httpx.AsyncClient() as client:
            with pytest.raises(UiPathAuthError) as exc_info:
                await auth.get_token(client)

        assert exc_info.value.status_code == 401
        assert _token_cache.is_valid is False  # Cache was cleared

    @respx.mock
    async def test_clears_cache_on_failure(self, cloud_settings):
        """A failed refresh should leave the cache empty."""
        respx.post(cloud_settings.cloud_token_url).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        auth = CloudAuthStrategy(cloud_settings)
        async with httpx.AsyncClient() as client:
            with pytest.raises(UiPathAuthError):
                await auth.get_token(client)

        assert _token_cache.is_valid is False


class TestPATAuth:

    async def test_returns_pat_directly(self, pat_settings):
        """PAT strategy returns the token with no HTTP calls."""
        auth = PATAuthStrategy(pat_settings)
        async with httpx.AsyncClient() as client:
            token = await auth.get_token(client)
        assert token == "test_pat_token"

    async def test_pat_base_headers(self, pat_settings):
        """PAT strategy should include tenant header."""
        auth = PATAuthStrategy(pat_settings)
        headers = auth.get_base_headers()
        assert headers["X-UIPATH-TenantName"] == "TestTenant"
