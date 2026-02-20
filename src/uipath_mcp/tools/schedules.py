"""
Process schedule management tools — 6 tools (ALL new vs JS version).

  list_schedules  get_schedule  enable_schedule  disable_schedule
  set_schedule_enabled  get_next_executions
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError
from ..models import ProcessSchedule


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_schedules(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        enabled_only: Annotated[bool, Field(description="Return only enabled schedules")] = False,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> str:
        """List all process schedules with their cron expressions and next execution times."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).count()
            if enabled_only:
                params.filter("Enabled eq true")
            data = await st.client.get("ProcessSchedules", params=params.build(), folder_id=folder_id)
            schedules = [ProcessSchedule.model_validate(s).model_dump() for s in data.get("value", [])]
            return json.dumps(
                {"total_count": data.get("@odata.count", len(schedules)), "schedules": schedules},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_schedule(
        ctx: Context,
        schedule_id: Annotated[int, Field(description="Schedule ID")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Get full details of a single schedule by ID."""
        st = _state(ctx)
        try:
            data = await st.client.get_by_id("ProcessSchedules", schedule_id, folder_id=folder_id)
            return json.dumps(ProcessSchedule.model_validate(data).model_dump(), default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def enable_schedule(
        ctx: Context,
        schedule_id: Annotated[int, Field(description="Schedule ID to enable")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Enable a disabled process schedule."""
        st = _state(ctx)
        try:
            body = {"enabled": True, "scheduleIds": [schedule_id]}
            await st.client.post(
                "ProcessSchedules", body=body, action="SetEnabled", folder_id=folder_id
            )
            return json.dumps({"message": f"Schedule {schedule_id} enabled"})
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def disable_schedule(
        ctx: Context,
        schedule_id: Annotated[int, Field(description="Schedule ID to disable")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Disable an active process schedule."""
        st = _state(ctx)
        try:
            body = {"enabled": False, "scheduleIds": [schedule_id]}
            await st.client.post(
                "ProcessSchedules", body=body, action="SetEnabled", folder_id=folder_id
            )
            return json.dumps({"message": f"Schedule {schedule_id} disabled"})
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def set_schedule_enabled(
        ctx: Context,
        schedule_ids: Annotated[list[int], Field(description="List of schedule IDs")],
        enabled: Annotated[bool, Field(description="True to enable, False to disable")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Bulk enable or disable multiple schedules in one call."""
        st = _state(ctx)
        try:
            body = {"enabled": enabled, "scheduleIds": schedule_ids}
            await st.client.post(
                "ProcessSchedules", body=body, action="SetEnabled", folder_id=folder_id
            )
            action_verb = "enabled" if enabled else "disabled"
            return json.dumps(
                {"message": f"{len(schedule_ids)} schedule(s) {action_verb}",
                 "schedule_ids": schedule_ids}
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_next_executions(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        top: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> str:
        """
        List upcoming scheduled executions sorted by NextExecution time.
        Useful to see what will run next.
        """
        st = _state(ctx)
        try:
            params = (
                ODataParams()
                .filter("Enabled eq true")
                .top(top * 3)
            )
            data = await st.client.get("ProcessSchedules", params=params.build(), folder_id=folder_id)
            schedules = data.get("value", [])
            # Sort by NextExecution in Python (avoid OData orderby on computed field)
            schedules.sort(key=lambda s: s.get("NextExecution") or "")
            return json.dumps({"upcoming_executions": schedules[:top]}, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())
