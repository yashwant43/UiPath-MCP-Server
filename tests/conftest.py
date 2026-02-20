"""
Shared pytest fixtures.

All HTTP calls are mocked at the httpx transport level using respx.
No real network calls are made in any test.
pytest-asyncio is configured in auto mode (no @pytest.mark.asyncio needed).
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

# Set required env vars BEFORE importing anything from uipath_mcp
# so pydantic-settings validation passes at import time.
os.environ.setdefault("AUTH_MODE", "pat")
os.environ.setdefault("UIPATH_BASE_URL", "https://orchestrator.example.com")
os.environ.setdefault("UIPATH_PAT", "test_pat_token")
os.environ.setdefault("UIPATH_TENANT_NAME", "TestTenant")

from uipath_mcp.auth import TokenCache, _token_cache  # noqa: E402
from uipath_mcp.config import AuthMode, Settings  # noqa: E402


# ── Settings fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def cloud_settings() -> Settings:
    return Settings(
        auth_mode=AuthMode.CLOUD,
        uipath_client_id="test_client_id",
        uipath_client_secret="test_client_secret",  # type: ignore[arg-type]
        uipath_org_name="test_org",
        uipath_tenant_name="TestTenant",
    )


@pytest.fixture
def pat_settings() -> Settings:
    return Settings(
        auth_mode=AuthMode.PAT,
        uipath_base_url="https://orchestrator.example.com",
        uipath_pat="test_pat_token",  # type: ignore[arg-type]
        uipath_tenant_name="TestTenant",
    )


@pytest.fixture(autouse=True)
def reset_token_cache() -> None:
    """Clear the module-level token cache before each test."""
    _token_cache.clear()
    yield
    _token_cache.clear()


# ── Mock context helpers ───────────────────────────────────────────────────────

def make_mock_ctx(client_mock: AsyncMock, settings: Settings) -> MagicMock:
    """Build a minimal mock Context with an AppState-like lifespan_context."""
    state = MagicMock()
    state.client = client_mock
    state.settings = settings

    ctx = MagicMock()
    ctx.request_context.lifespan_context = state
    ctx.info = AsyncMock()
    ctx.report_progress = AsyncMock()
    return ctx


# ── Sample API response fixtures ──────────────────────────────────────────────

@pytest.fixture
def mock_token_response() -> dict:
    return {
        "access_token": "eyJ.test.token",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "OR.Default",
    }


@pytest.fixture
def sample_jobs_response() -> dict:
    return {
        "@odata.context": "$metadata#Jobs",
        "@odata.count": 2,
        "value": [
            {
                "Id": 101,
                "Key": "abc-123-def",
                "ReleaseName": "MyProcess",
                "State": "Successful",
                "Source": "Manual",
                "StartTime": "2024-01-15T10:00:00Z",
                "EndTime": "2024-01-15T10:05:00Z",
                "CreationTime": "2024-01-15T09:59:00Z",
            },
            {
                "Id": 102,
                "Key": "ghi-456-jkl",
                "ReleaseName": "MyProcess",
                "State": "Faulted",
                "Source": "Schedule",
                "CreationTime": "2024-01-15T09:00:00Z",
            },
        ],
    }


@pytest.fixture
def sample_queue_items_response() -> dict:
    return {
        "@odata.count": 1,
        "value": [
            {
                "Id": 201,
                "Status": "New",
                "Priority": "Normal",
                "QueueDefinitionName": "TestQueue",
                "SpecificContent": {"Email": "test@example.com"},
                "CreationTime": "2024-01-15T10:00:00Z",
            }
        ],
    }


@pytest.fixture
def sample_releases_response() -> dict:
    return {
        "value": [
            {
                "Id": 10,
                "Key": "release-key-uuid",
                "Name": "MyProcess",
                "ProcessKey": "MyProcess",
                "ProcessVersion": "1.0.0",
                "IsLatestVersion": True,
            }
        ]
    }
