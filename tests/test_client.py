"""
Tests for UiPathClient: retry logic, OData params, pagination, error handling.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from uipath_mcp.auth import PATAuthStrategy
from uipath_mcp.client import ODataParams, UiPathClient, UiPathError


class TestODataParams:

    def test_basic_filter_and_pagination(self):
        params = ODataParams().top(50).skip(100).filter("State eq 'Running'").build()
        assert params == {"$top": 50, "$skip": 100, "$filter": "State eq 'Running'"}

    def test_select_joins_fields_with_comma(self):
        params = ODataParams().select("Id", "Name", "State").build()
        assert params["$select"] == "Id,Name,State"

    def test_orderby_desc(self):
        params = ODataParams().orderby("CreationTime", "desc").build()
        assert params["$orderby"] == "CreationTime desc"

    def test_fluent_chain_returns_same_instance(self):
        builder = ODataParams()
        result = builder.top(10).skip(0).count()
        assert result is builder

    def test_empty_build_returns_empty_dict(self):
        assert ODataParams().build() == {}


class TestUiPathClientRetry:

    @pytest.fixture
    def pat_auth(self, pat_settings) -> PATAuthStrategy:
        return PATAuthStrategy(pat_settings)

    @respx.mock
    async def test_retries_on_429_succeeds_second_attempt(
        self, pat_settings, pat_auth, sample_jobs_response
    ):
        """Should retry on 429 and succeed on the second attempt."""
        jobs_url = f"{pat_settings.orchestrator_base_url}/odata/Jobs"
        call_count = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, headers={"Retry-After": "0.1"})
            return httpx.Response(200, json=sample_jobs_response)

        respx.get(jobs_url).mock(side_effect=respond)

        async with UiPathClient(pat_settings, pat_auth) as client:
            result = await client.get("Jobs")

        assert call_count == 2
        assert len(result["value"]) == 2

    @respx.mock
    async def test_does_not_retry_on_404(self, pat_settings, pat_auth):
        """404 should raise UiPathError immediately without any retries."""
        call_count = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(404, json={"message": "Not found"})

        respx.get(f"{pat_settings.orchestrator_base_url}/odata/Jobs(9999)").mock(
            side_effect=respond
        )

        async with UiPathClient(pat_settings, pat_auth) as client:
            with pytest.raises(UiPathError) as exc_info:
                await client.get_by_id("Jobs", 9999)

        assert call_count == 1  # No retries on 404
        assert exc_info.value.status_code == 404

    @respx.mock
    async def test_pagination_yields_all_pages(self, pat_settings, pat_auth):
        """paginate() should yield both pages and stop when server returns partial page."""
        base_url = f"{pat_settings.orchestrator_base_url}/odata/QueueItems"
        page1 = {"value": [{"Id": i} for i in range(10)]}
        page2 = {"value": [{"Id": i} for i in range(10, 15)]}  # 5 items < page_size=10
        call_count = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=page1 if call_count == 1 else page2)

        respx.get(base_url).mock(side_effect=respond)

        all_items: list[dict] = []
        async with UiPathClient(pat_settings, pat_auth) as client:
            async for page in client.paginate("QueueItems", page_size=10):
                all_items.extend(page)

        assert len(all_items) == 15
        assert call_count == 2

    @respx.mock
    async def test_collect_all_accumulates_pages(self, pat_settings, pat_auth):
        """collect_all() should return a flat list from multiple pages."""
        base_url = f"{pat_settings.orchestrator_base_url}/odata/Jobs"
        page1 = {"value": [{"Id": i} for i in range(100)]}
        page2 = {"value": [{"Id": i} for i in range(100, 150)]}
        call_count = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=page1 if call_count == 1 else page2)

        respx.get(base_url).mock(side_effect=respond)

        async with UiPathClient(pat_settings, pat_auth) as client:
            results = await client.collect_all("Jobs", max_items=5000)

        assert len(results) == 150

    @respx.mock
    async def test_folder_header_injected_when_folder_id_given(
        self, pat_settings, pat_auth
    ):
        """Requests with folder_id should include X-UIPATH-OrganizationUnitId header."""
        captured_headers: dict = {}
        base_url = f"{pat_settings.orchestrator_base_url}/odata/Jobs"

        def capture(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"value": []})

        respx.get(base_url).mock(side_effect=capture)

        async with UiPathClient(pat_settings, pat_auth) as client:
            await client.get("Jobs", folder_id=42)

        assert captured_headers.get("x-uipath-organizationunitid") == "42"
