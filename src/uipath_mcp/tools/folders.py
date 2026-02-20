"""
Folder management tools — 5 tools (ALL new vs JS version).

  list_folders  get_folder  list_folder_robots  get_folder_stats  list_sub_folders
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError
from ..models import Folder


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_folders(
        ctx: Context,
        top: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> str:
        """List all accessible Orchestrator folders/organization units."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).count().build()
            data = await st.client.get("Folders", params=params)
            folders = [Folder.model_validate(f).model_dump() for f in data.get("value", [])]
            return json.dumps(
                {"total_count": data.get("@odata.count", len(folders)), "folders": folders},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_folder(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        folder_name: Annotated[str | None, Field(description="Folder display name (exact)")] = None,
    ) -> str:
        """Get a folder by ID or display name."""
        st = _state(ctx)
        try:
            if folder_id:
                data = await st.client.get_by_id("Folders", folder_id)
                return json.dumps(Folder.model_validate(data).model_dump(), default=str)
            if folder_name:
                params = ODataParams().filter(f"DisplayName eq '{folder_name}'").top(1).build()
                data = await st.client.get("Folders", params=params)
                items = data.get("value", [])
                if not items:
                    return json.dumps({"error": f"Folder '{folder_name}' not found"})
                return json.dumps(Folder.model_validate(items[0]).model_dump(), default=str)
            return json.dumps({"error": "Provide folder_id or folder_name"})
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def list_sub_folders(
        ctx: Context,
        parent_folder_id: Annotated[int, Field(description="Parent folder ID")],
    ) -> str:
        """List all child folders of a given parent folder."""
        st = _state(ctx)
        try:
            params = (
                ODataParams()
                .filter(f"ParentId eq {parent_folder_id}")
                .top(200)
                .build()
            )
            data = await st.client.get("Folders", params=params)
            folders = [Folder.model_validate(f).model_dump() for f in data.get("value", [])]
            return json.dumps(
                {"parent_id": parent_folder_id, "sub_folder_count": len(folders), "folders": folders},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def list_folder_robots(
        ctx: Context,
        folder_id: Annotated[int, Field(description="Folder ID")],
        top: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> str:
        """List all robots assigned to a specific folder."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).count().build()
            data = await st.client.get("Robots", params=params, folder_id=folder_id)
            robots = data.get("value", [])
            return json.dumps(
                {"folder_id": folder_id, "robot_count": len(robots), "robots": robots},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_folder_stats(
        ctx: Context,
        folder_id: Annotated[int, Field(description="Folder ID")],
    ) -> str:
        """
        Get a summary of jobs and queue items for a folder.
        Returns counts of successful, running, and failed jobs,
        plus queue item totals.
        """
        st = _state(ctx)
        try:
            # Get job counts
            job_params = ODataParams().count().top(0).build()
            all_jobs = await st.client.get("Jobs", params=job_params, folder_id=folder_id)

            running_params = (
                ODataParams()
                .count()
                .top(0)
                .filter("State eq UiPath.Server.Configuration.OData.JobState'Running'")
                .build()
            )
            running_jobs = await st.client.get("Jobs", params=running_params, folder_id=folder_id)

            faulted_params = (
                ODataParams()
                .count()
                .top(0)
                .filter("State eq UiPath.Server.Configuration.OData.JobState'Faulted'")
                .build()
            )
            faulted_jobs = await st.client.get("Jobs", params=faulted_params, folder_id=folder_id)

            # Get queue item counts
            queue_params = ODataParams().count().top(0).build()
            queue_items = await st.client.get("QueueItems", params=queue_params, folder_id=folder_id)

            return json.dumps(
                {
                    "folder_id": folder_id,
                    "jobs": {
                        "total": all_jobs.get("@odata.count", 0),
                        "running": running_jobs.get("@odata.count", 0),
                        "faulted": faulted_jobs.get("@odata.count", 0),
                    },
                    "queue_items": {
                        "total": queue_items.get("@odata.count", 0),
                    },
                },
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())
