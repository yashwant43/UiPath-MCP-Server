"""
Robot and machine management tools — 8 tools.

  list_robots  get_robot  list_available_robots  ⭐new
  list_robot_sessions  ⭐new  list_robot_logs
  list_machines  get_machine  get_robot_license_info  ⭐new
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError
from ..models import Machine, Robot, RobotLog, RobotSession


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_robots(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        name_filter: Annotated[str | None, Field(description="Filter by robot name (partial)")] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> str:
        """List all robots, optionally filtered by name."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).count()
            if name_filter:
                params.filter(f"contains(Name,'{name_filter}')")
            data = await st.client.get("Robots", params=params.build(), folder_id=folder_id)
            robots = [Robot.model_validate(r).model_dump() for r in data.get("value", [])]
            return json.dumps(
                {"total_count": data.get("@odata.count", len(robots)), "robots": robots},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_robot(
        ctx: Context,
        robot_id: Annotated[int, Field(description="Robot ID")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Get details of a single robot by ID."""
        st = _state(ctx)
        try:
            data = await st.client.get_by_id("Robots", robot_id, folder_id=folder_id)
            return json.dumps(Robot.model_validate(data).model_dump(), default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def list_available_robots(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Shortcut: list only robots currently in Available state."""
        st = _state(ctx)
        try:
            params = ODataParams().top(200).build()
            data = await st.client.get("Sessions", params=params, folder_id=folder_id)
            sessions = data.get("value", [])
            available = [
                s for s in sessions
                if s.get("IsConnected") and s.get("State") in ("Available", 2)
            ]
            return json.dumps(
                {"available_count": len(available), "sessions": available}, default=str
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def list_robot_sessions(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        connected_only: Annotated[bool, Field(description="Return only connected sessions")] = True,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> str:
        """List active robot sessions (shows which robots are currently connected)."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).build()
            data = await st.client.get("Sessions", params=params, folder_id=folder_id)
            sessions_raw = data.get("value", [])
            if connected_only:
                sessions_raw = [s for s in sessions_raw if s.get("IsConnected")]
            sessions = [RobotSession.model_validate(s).model_dump() for s in sessions_raw]
            return json.dumps(
                {"total_count": len(sessions), "sessions": sessions},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def list_robot_logs(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        process_name: Annotated[str | None, Field(description="Filter by process name")] = None,
        robot_name: Annotated[str | None, Field(description="Filter by robot name")] = None,
        level: Annotated[
            str | None,
            Field(description="Log level: Trace | Info | Warn | Error | Fatal"),
        ] = None,
        since: Annotated[str | None, Field(description="ISO 8601 start time")] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> str:
        """Query robot execution logs with filters."""
        st = _state(ctx)
        try:
            parts: list[str] = []
            if process_name:
                parts.append(f"ProcessName eq '{process_name}'")
            if robot_name:
                parts.append(f"RobotName eq '{robot_name}'")
            if level:
                parts.append(f"Level eq '{level}'")
            if since:
                parts.append(f"TimeStamp ge datetime'{since.rstrip('Z')}'")
            params = ODataParams().top(top).orderby("TimeStamp", "desc")
            if parts:
                params.filter(" and ".join(parts))
            data = await st.client.get("RobotLogs", params=params.build(), folder_id=folder_id)
            logs = [RobotLog.model_validate(l).model_dump() for l in data.get("value", [])]
            return json.dumps({"count": len(logs), "logs": logs}, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def list_machines(
        ctx: Context,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> str:
        """List all machine templates."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).count().build()
            data = await st.client.get("Machines", params=params)
            machines = [Machine.model_validate(m).model_dump() for m in data.get("value", [])]
            return json.dumps(
                {"total_count": data.get("@odata.count", len(machines)), "machines": machines},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_machine(
        ctx: Context,
        machine_id: Annotated[int, Field(description="Machine ID")],
    ) -> str:
        """Get details of a single machine by ID."""
        st = _state(ctx)
        try:
            data = await st.client.get_by_id("Machines", machine_id)
            return json.dumps(Machine.model_validate(data).model_dump(), default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_robot_license_info(
        ctx: Context,
    ) -> str:
        """
        Get runtime license utilization — how many slots are in use vs available.
        Shows named user and runtime license pool stats.
        """
        st = _state(ctx)
        try:
            result: dict[str, Any] = {}
            for key, endpoint in [
                ("runtime_licenses", "api/Stats/GetRuntimeLicenseStats"),
                ("named_user_licenses", "api/Stats/GetNamedUserLicenseStats"),
            ]:
                try:
                    result[key] = await st.client.api_get(endpoint)
                except UiPathError as inner_e:
                    result[key] = {"error": inner_e.message, "status_code": inner_e.status_code}
            return json.dumps(result, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())
