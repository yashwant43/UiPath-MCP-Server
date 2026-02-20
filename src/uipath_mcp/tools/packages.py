"""
Package management tools — 3 tools.

  list_packages        list all published packages (processes) with versions
  get_package          get details of a specific package by name
  download_and_read_package  download a .nupkg, extract it, and return all .xaml file contents
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP) -> None:

    # ── list_packages ──────────────────────────────────────────────────────────

    @mcp.tool()
    async def list_packages(
        ctx: Context,
        search: Annotated[str | None, Field(description="Filter by package name (partial match)")] = None,
        top: Annotated[int, Field(description="Max results to return", ge=1, le=250)] = 50,
    ) -> str:
        """List all published packages (processes) available in Orchestrator."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).orderby("Id").build()
            if search:
                params["$filter"] = f"contains(Id,'{search}')"

            data = await st.client.get("Processes", params=params)
            packages = data.get("value", [])

            result = []
            for p in packages:
                result.append({
                    "id": p.get("Id"),
                    "title": p.get("Title"),
                    "version": p.get("Version"),
                    "description": p.get("Description"),
                    "published": p.get("Published"),
                    "is_latest_version": p.get("IsLatestVersion"),
                    "project_type": p.get("ProjectType"),
                })

            return json.dumps({"total_count": len(result), "packages": result}, indent=2)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── get_package ────────────────────────────────────────────────────────────

    @mcp.tool()
    async def get_package(
        ctx: Context,
        package_id: Annotated[str, Field(description="Package ID (process name), e.g. 'LifeSettlementDispatcher'")],
    ) -> str:
        """Get details and all available versions of a specific package."""
        st = _state(ctx)
        try:
            params = ODataParams().filter(f"Id eq '{package_id}'").build()
            data = await st.client.get("Processes", params=params)
            packages = data.get("value", [])

            if not packages:
                return json.dumps({"error": f"Package '{package_id}' not found."})

            result = []
            for p in packages:
                result.append({
                    "id": p.get("Id"),
                    "title": p.get("Title"),
                    "version": p.get("Version"),
                    "description": p.get("Description"),
                    "published": p.get("Published"),
                    "is_latest_version": p.get("IsLatestVersion"),
                    "authors": p.get("Authors"),
                    "project_type": p.get("ProjectType"),
                    "release_notes": p.get("ReleaseNotes"),
                })

            return json.dumps({"package_id": package_id, "versions": result}, indent=2)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── download_and_read_package ──────────────────────────────────────────────

    @mcp.tool()
    async def download_and_read_package(
        ctx: Context,
        package_id: Annotated[str, Field(description="Package ID (process name), e.g. 'LifeSettlementDispatcher'")],
        version: Annotated[str | None, Field(description="Specific version to download, e.g. '3.0.7'. Defaults to latest.")] = None,
        xaml_filter: Annotated[str | None, Field(description="Only return .xaml files whose path contains this string, e.g. 'SaveAttachments'")] = None,
    ) -> str:
        """
        Download a UiPath package (.nupkg) from Orchestrator, extract it,
        and return the contents of all .xaml workflow files.
        Useful for reading and analyzing process source code.
        """
        st = _state(ctx)
        try:
            # Step 1: Find the package and resolve version
            filters = [f"Id eq '{package_id}'"]
            if version:
                filters.append(f"Version eq '{version}'")
            else:
                filters.append("IsLatestVersion eq true")

            params = ODataParams().filter(" and ".join(filters)).build()
            data = await st.client.get("Processes", params=params)
            packages = data.get("value", [])

            if not packages:
                # Fallback: try without IsLatestVersion filter (some Orchestrators behave differently)
                fallback_params = ODataParams().filter(f"Id eq '{package_id}'").orderby("Version", "desc").top(1).build()
                data = await st.client.get("Processes", params=fallback_params)
                packages = data.get("value", [])

            if not packages:
                return json.dumps({"error": f"Package '{package_id}' not found. Check the package ID and try again."})

            pkg = packages[0]
            resolved_version = pkg.get("Version")
            pkg_key = f"{package_id}.{resolved_version}"

            # Step 2: Download the .nupkg file
            download_url = (
                f"{st.client._settings.orchestrator_base_url}/odata/Processes/UiPath.Server.Configuration.OData.DownloadPackage(key='{pkg_key}')"
            )

            response = await st.client._request("GET", download_url)
            nupkg_bytes = response.content

            # Step 3: Extract and read .xaml files from the zip
            xaml_files: dict[str, str] = {}
            with zipfile.ZipFile(io.BytesIO(nupkg_bytes)) as zf:
                for name in zf.namelist():
                    if name.endswith(".xaml"):
                        if xaml_filter and xaml_filter.lower() not in name.lower():
                            continue
                        with zf.open(name) as f:
                            try:
                                xaml_files[name] = f.read().decode("utf-8")
                            except UnicodeDecodeError:
                                xaml_files[name] = f.read().decode("latin-1")

            if not xaml_files:
                return json.dumps({
                    "package_id": package_id,
                    "version": resolved_version,
                    "error": "No .xaml files found matching the filter." if xaml_filter else "No .xaml files found in package.",
                })

            return json.dumps({
                "package_id": package_id,
                "version": resolved_version,
                "xaml_file_count": len(xaml_files),
                "xaml_files": xaml_files,
            }, indent=2)

        except UiPathError as e:
            return json.dumps(e.to_dict())
        except zipfile.BadZipFile:
            return json.dumps({"error": "Downloaded file is not a valid zip/nupkg. The package may be corrupted."})
        except Exception as e:
            return json.dumps({"error": f"Unexpected error: {str(e)}"})
