"""
Tests for package management tools:
  list_packages, get_package, download_and_read_package
"""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import make_mock_ctx
from uipath_mcp.client import UiPathError


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_nupkg(files: dict[str, str]) -> bytes:
    """Create an in-memory .nupkg (zip) with the given filename→content mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _get_tool_fn(mcp, name):
    for tool in mcp._tool_manager._tools.values():
        if tool.name == name:
            return tool.fn
    raise AssertionError(f"Tool '{name}' not registered")


def _make_mcp():
    from mcp.server.fastmcp import FastMCP
    from uipath_mcp.tools.packages import register
    mcp = FastMCP("test")
    register(mcp)
    return mcp


SAMPLE_PKG = {
    "Id": "LifeSettlementDispatcher",
    "Title": "Life Settlement Dispatcher",
    "Version": "3.0.7",
    "Description": "Dispatches life settlement queue items",
    "Published": "2024-06-01T00:00:00Z",
    "IsLatestVersion": True,
    "ProjectType": "Process",
    "Authors": "RPA Team",
    "ReleaseNotes": "Bug fixes",
}


# ── list_packages ─────────────────────────────────────────────────────────────

class TestListPackages:

    async def test_returns_package_list(self, pat_settings):
        """list_packages returns structured JSON with all packages."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"value": [SAMPLE_PKG]})
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(await _get_tool_fn(_make_mcp(), "list_packages")(ctx=ctx))

        assert result["total_count"] == 1
        assert result["packages"][0]["id"] == "LifeSettlementDispatcher"
        assert result["packages"][0]["version"] == "3.0.7"
        assert result["packages"][0]["is_latest_version"] is True

    async def test_search_filter_is_applied(self, pat_settings):
        """list_packages with search= adds $filter to the request params."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"value": [SAMPLE_PKG]})
        ctx = make_mock_ctx(mock_client, pat_settings)

        await _get_tool_fn(_make_mcp(), "list_packages")(ctx=ctx, search="LifeSettlement")

        call_params = mock_client.get.call_args[1]["params"]
        assert "$filter" in call_params
        assert "LifeSettlement" in call_params["$filter"]

    async def test_returns_error_on_api_failure(self, pat_settings):
        """list_packages returns JSON error string on UiPathError."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=UiPathError("Forbidden", status_code=403))
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(await _get_tool_fn(_make_mcp(), "list_packages")(ctx=ctx))
        assert "error" in result


# ── get_package ───────────────────────────────────────────────────────────────

class TestGetPackage:

    async def test_returns_package_versions(self, pat_settings):
        """get_package returns all versions for the given package ID."""
        pkg_v1 = {**SAMPLE_PKG, "Version": "3.0.6", "IsLatestVersion": False}
        pkg_v2 = {**SAMPLE_PKG, "Version": "3.0.7", "IsLatestVersion": True}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"value": [pkg_v1, pkg_v2]})
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(
            await _get_tool_fn(_make_mcp(), "get_package")(
                ctx=ctx, package_id="LifeSettlementDispatcher"
            )
        )

        assert result["package_id"] == "LifeSettlementDispatcher"
        assert len(result["versions"]) == 2
        assert result["versions"][1]["version"] == "3.0.7"
        assert result["versions"][1]["is_latest_version"] is True

    async def test_returns_error_when_package_not_found(self, pat_settings):
        """get_package returns an error JSON when no packages match."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"value": []})
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(
            await _get_tool_fn(_make_mcp(), "get_package")(
                ctx=ctx, package_id="DoesNotExist"
            )
        )

        assert "error" in result
        assert "DoesNotExist" in result["error"]


# ── download_and_read_package ─────────────────────────────────────────────────

class TestDownloadAndReadPackage:

    def _mock_client_with_nupkg(self, pkg_data: dict, nupkg_bytes: bytes, pat_settings):
        """Return (mock_client, ctx) set up for a successful download."""
        mock_response = MagicMock()
        mock_response.content = nupkg_bytes

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"value": [pkg_data]})
        mock_client._request = AsyncMock(return_value=mock_response)
        mock_client._settings = MagicMock()
        mock_client._settings.orchestrator_base_url = "https://orchestrator.example.com"
        return mock_client

    async def test_downloads_and_extracts_all_xaml_files(self, pat_settings):
        """
        download_and_read_package should:
        1. GET Processes to resolve the version
        2. Call _request to download the .nupkg
        3. Extract and return all .xaml file contents
        """
        nupkg = _make_nupkg({
            "Main.xaml": "<Activity>Main workflow</Activity>",
            "Workflows/Helper.xaml": "<Activity>Helper</Activity>",
            "project.json": '{"name":"test"}',  # non-xaml, should be ignored
        })
        mock_client = self._mock_client_with_nupkg(SAMPLE_PKG, nupkg, pat_settings)
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(
            await _get_tool_fn(_make_mcp(), "download_and_read_package")(
                ctx=ctx, package_id="LifeSettlementDispatcher"
            )
        )

        assert result["package_id"] == "LifeSettlementDispatcher"
        assert result["version"] == "3.0.7"
        assert result["xaml_file_count"] == 2
        assert "Main.xaml" in result["xaml_files"]
        assert "Workflows/Helper.xaml" in result["xaml_files"]
        assert "project.json" not in result["xaml_files"]
        assert result["xaml_files"]["Main.xaml"] == "<Activity>Main workflow</Activity>"

        # Step 1: GET Processes, Step 2: _request for download
        assert mock_client.get.call_count == 1
        assert mock_client._request.call_count == 1

    async def test_download_url_uses_colon_separator(self, pat_settings):
        """The OData download key must use 'PackageId:Version' (colon, not dot)."""
        nupkg = _make_nupkg({"Main.xaml": "<Activity/>"})
        mock_client = self._mock_client_with_nupkg(SAMPLE_PKG, nupkg, pat_settings)
        ctx = make_mock_ctx(mock_client, pat_settings)

        await _get_tool_fn(_make_mcp(), "download_and_read_package")(
            ctx=ctx, package_id="LifeSettlementDispatcher"
        )

        called_url = mock_client._request.call_args[0][1]
        assert "LifeSettlementDispatcher:3.0.7" in called_url
        assert "LifeSettlementDispatcher.3.0.7" not in called_url

    async def test_xaml_filter_returns_only_matching_files(self, pat_settings):
        """xaml_filter should exclude .xaml files that don't contain the filter string."""
        nupkg = _make_nupkg({
            "Main.xaml": "<Activity>Main</Activity>",
            "Workflows/SaveAttachments.xaml": "<Activity>Save</Activity>",
            "Workflows/ParseEmail.xaml": "<Activity>Parse</Activity>",
        })
        mock_client = self._mock_client_with_nupkg(SAMPLE_PKG, nupkg, pat_settings)
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(
            await _get_tool_fn(_make_mcp(), "download_and_read_package")(
                ctx=ctx,
                package_id="LifeSettlementDispatcher",
                xaml_filter="SaveAttachments",
            )
        )

        assert result["xaml_file_count"] == 1
        assert "Workflows/SaveAttachments.xaml" in result["xaml_files"]
        assert "Main.xaml" not in result["xaml_files"]
        assert "Workflows/ParseEmail.xaml" not in result["xaml_files"]

    async def test_explicit_version_passed_to_filter(self, pat_settings):
        """When version= is given, the OData filter should include it."""
        nupkg = _make_nupkg({"Main.xaml": "<Activity/>"})
        pkg = {**SAMPLE_PKG, "Version": "2.1.0"}
        mock_client = self._mock_client_with_nupkg(pkg, nupkg, pat_settings)
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(
            await _get_tool_fn(_make_mcp(), "download_and_read_package")(
                ctx=ctx, package_id="LifeSettlementDispatcher", version="2.1.0"
            )
        )

        assert result["version"] == "2.1.0"
        # The OData $filter must include the version constraint
        get_params = mock_client.get.call_args[1]["params"]
        assert "2.1.0" in get_params["$filter"]

    async def test_returns_error_when_package_not_found(self, pat_settings):
        """Both the main and fallback queries returning empty → error JSON."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"value": []})
        mock_client._settings = MagicMock()
        mock_client._settings.orchestrator_base_url = "https://orchestrator.example.com"
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(
            await _get_tool_fn(_make_mcp(), "download_and_read_package")(
                ctx=ctx, package_id="Ghost"
            )
        )

        assert "error" in result
        assert "Ghost" in result["error"]

    async def test_returns_error_when_no_xaml_files_in_package(self, pat_settings):
        """A package with no .xaml files returns an error (not a crash)."""
        nupkg = _make_nupkg({"project.json": "{}", "lib/net45/UiPath.dll": ""})
        mock_client = self._mock_client_with_nupkg(SAMPLE_PKG, nupkg, pat_settings)
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(
            await _get_tool_fn(_make_mcp(), "download_and_read_package")(
                ctx=ctx, package_id="LifeSettlementDispatcher"
            )
        )

        assert "error" in result
        assert result["version"] == "3.0.7"

    async def test_returns_error_on_bad_zip(self, pat_settings):
        """Corrupted download (not a valid zip) returns a friendly error."""
        mock_response = MagicMock()
        mock_response.content = b"this is not a zip file"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"value": [SAMPLE_PKG]})
        mock_client._request = AsyncMock(return_value=mock_response)
        mock_client._settings = MagicMock()
        mock_client._settings.orchestrator_base_url = "https://orchestrator.example.com"
        ctx = make_mock_ctx(mock_client, pat_settings)

        result = json.loads(
            await _get_tool_fn(_make_mcp(), "download_and_read_package")(
                ctx=ctx, package_id="LifeSettlementDispatcher"
            )
        )

        assert "error" in result
        assert "zip" in result["error"].lower() or "nupkg" in result["error"].lower()
