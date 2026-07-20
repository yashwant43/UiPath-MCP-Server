"""
Process schedule management tools — 6 tools (ALL new vs JS version).

  list_schedules  get_schedule  enable_schedule  disable_schedule
  set_schedule_enabled  get_next_executions
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError
from ..models import ProcessSchedule

_TRIGGER_ENDPOINTS = (
    ("ProcessSchedules", None),
    ("ApiTriggers", "event"),
    ("HttpTriggers", "api"),
)


def _trigger_type(item: dict[str, Any], default: str | None) -> str:
    if default is not None:
        return default
    if item.get("QueueDefinitionId") is not None or item.get("QueueDefinitionName"):
        return "queue"
    return "time"


def _machine_robot(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "machine_id": item.get("MachineId"),
        "machine_name": item.get("MachineName"),
        "robot_id": item.get("RobotId"),
        "robot_username": item.get("RobotUserName") or item.get("RobotUsername"),
        "host_machine_name": item.get("HostMachineName") or item.get("Hostname"),
    }


def _normalize_trigger(
    item: dict[str, Any], endpoint: str, default_type: str | None
) -> dict[str, Any]:
    process_name = item.get("ReleaseName") or item.get("ProcessName")
    return {
        "id": item.get("Id"),
        "name": item.get("Name"),
        "release_name": item.get("ReleaseName") or process_name,
        "release_id": item.get("ReleaseId") or item.get("ProcessId"),
        "process_name": process_name,
        "enabled": item.get("Enabled"),
        "trigger_type": _trigger_type(item, default_type),
        "source_endpoint": endpoint,
        "time_zone_id": item.get("TimeZoneId"),
        "cron_expression": item.get("StartProcessCron") or item.get("CronExpression"),
        "start_at": item.get("StartAt"),
        "next_execution": item.get("StartProcessNextOccurrence") or item.get("NextExecution"),
        "strategy": item.get("StartStrategy") or item.get("Strategy"),
        "stop_strategy": item.get("StopStrategy"),
        "runtime_type": item.get("RuntimeType"),
        "job_priority": item.get("JobPriority"),
        "queue_definition_id": item.get("QueueDefinitionId"),
        "queue_definition_name": item.get("QueueDefinitionName"),
        "machine_robots": [_machine_robot(target) for target in item.get("MachineRobots", [])],
    }


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP, read_only: bool = False) -> None:

    @mcp.tool()
    async def list_schedules(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        enabled_only: Annotated[bool, Field(description="Return only enabled schedules")] = False,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> str:
        """List all trigger types and their execution targets in a folder."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).count()
            if enabled_only:
                params.filter("Enabled eq true")
            query = params.build()
            responses = await asyncio.gather(
                *(
                    st.client.get(endpoint, params=query.copy(), folder_id=folder_id)
                    for endpoint, _ in _TRIGGER_ENDPOINTS
                )
            )
            schedules = [
                _normalize_trigger(item, endpoint, default_type)
                for (endpoint, default_type), data in zip(
                    _TRIGGER_ENDPOINTS, responses, strict=True
                )
                for item in data.get("value", [])
            ]
            return json.dumps(
                {"total_count": len(schedules), "schedules": schedules},
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

    if not read_only:

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
