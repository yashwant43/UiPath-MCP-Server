"""
Analytics and monitoring tools — 6 tools.

  get_jobs_stats  get_queue_processing_stats  get_license_usage
  get_robot_utilization  get_tenant_stats  get_error_patterns  ⭐new
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def get_jobs_stats(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        since: Annotated[str | None, Field(description="ISO 8601 start date")] = None,
        until: Annotated[str | None, Field(description="ISO 8601 end date")] = None,
    ) -> str:
        """
        Get job counts grouped by state for a date range.
        Useful for dashboard-style health overviews.
        """
        st = _state(ctx)
        try:
            parts: list[str] = []
            if since:
                parts.append(f"CreationTime ge datetime'{since.rstrip('Z')}'")
            if until:
                parts.append(f"CreationTime le datetime'{until.rstrip('Z')}'")
            params = ODataParams().top(5000).select("State").count()
            if parts:
                params.filter(" and ".join(parts))
            data = await st.client.get("Jobs", params=params.build(), folder_id=folder_id)
            jobs = data.get("value", [])

            counts: dict[str, int] = {}
            for j in jobs:
                s = j.get("State", "Unknown")
                counts[s] = counts.get(s, 0) + 1

            total = len(jobs)
            return json.dumps(
                {
                    "total_jobs": total,
                    "date_range": {"since": since, "until": until},
                    "counts_by_state": counts,
                    "success_rate_pct": round(
                        counts.get("Successful", 0) / total * 100, 1
                    ) if total else 0.0,
                },
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_queue_processing_stats(
        ctx: Context,
        queue_name: Annotated[str | None, Field(description="Queue name (all queues if omitted)")] = None,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        since: Annotated[str | None, Field(description="ISO 8601 start date")] = None,
    ) -> str:
        """
        Get queue throughput statistics: total processed, success rate,
        average processing duration, and top failure reasons.
        """
        st = _state(ctx)
        try:
            parts: list[str] = []
            if queue_name:
                q_data = await st.client.get(
                    "QueueDefinitions",
                    params=ODataParams().filter(f"Name eq '{queue_name}'").top(1).build(),
                    folder_id=folder_id,
                )
                q_items = q_data.get("value", [])
                if not q_items:
                    return json.dumps({"error": f"Queue '{queue_name}' not found"})
                parts.append(f"QueueDefinitionId eq {q_items[0]['Id']}")
            if since:
                parts.append(f"CreationTime ge datetime'{since.rstrip('Z')}'")
            parts.append("Status ne 'New'")

            params = (
                ODataParams()
                .top(5000)
                .filter(" and ".join(parts))
            )
            data = await st.client.get("QueueItems", params=params.build(), folder_id=folder_id)
            items = data.get("value", [])

            counts: dict[str, int] = {}
            exception_types: dict[str, int] = {}
            durations: list[float] = []

            for item in items:
                status = item.get("Status", "Unknown")
                counts[status] = counts.get(status, 0) + 1

                exc_type = item.get("ProcessingExceptionType")
                if exc_type:
                    exception_types[exc_type] = exception_types.get(exc_type, 0) + 1

                start = item.get("StartTime")
                end = item.get("EndTime")
                if start and end:
                    from datetime import datetime
                    try:
                        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        e2 = datetime.fromisoformat(end.replace("Z", "+00:00"))
                        durations.append((e2 - s).total_seconds())
                    except Exception:
                        pass

            total = len(items)
            avg_duration = sum(durations) / len(durations) if durations else 0.0

            return json.dumps(
                {
                    "queue_name": queue_name or "all",
                    "total_processed": total,
                    "counts_by_status": counts,
                    "success_rate_pct": round(
                        counts.get("Successful", 0) / total * 100, 1
                    ) if total else 0.0,
                    "avg_processing_seconds": round(avg_duration, 1),
                    "top_exception_types": dict(
                        sorted(exception_types.items(), key=lambda x: -x[1])[:5]
                    ),
                },
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_license_usage(
        ctx: Context,
    ) -> str:
        """Get current license allocation and consumption across all types."""
        st = _state(ctx)
        try:
            result: dict[str, Any] = {}
            for key, endpoint in [
                ("traditional_licenses", "api/Stats/GetLicenseStats"),
                ("consumption_licenses", "api/Stats/GetConsumptionLicenseStats"),
            ]:
                try:
                    result[key] = await st.client.api_get(endpoint)
                except UiPathError as inner_e:
                    result[key] = {"error": inner_e.message, "status_code": inner_e.status_code}
            return json.dumps(result, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_robot_utilization(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """
        Get robot session statistics: how many are connected,
        available vs busy vs disconnected.
        """
        st = _state(ctx)
        try:
            params = ODataParams().top(500).build()
            data = await st.client.get("Sessions", params=params, folder_id=folder_id)
            sessions = data.get("value", [])

            state_counts: dict[str, int] = {}
            connected = 0
            for s in sessions:
                state = s.get("State", "Unknown")
                state_counts[state] = state_counts.get(state, 0) + 1
                if s.get("IsConnected"):
                    connected += 1

            total = len(sessions)
            return json.dumps(
                {
                    "total_sessions": total,
                    "connected": connected,
                    "disconnected": total - connected,
                    "state_breakdown": state_counts,
                    "utilization_pct": round(
                        state_counts.get("Busy", 0) / connected * 100, 1
                    ) if connected else 0.0,
                },
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_tenant_stats(
        ctx: Context,
    ) -> str:
        """
        Get entity count statistics across the entire tenant
        (total jobs, queues, robots, etc.).
        """
        st = _state(ctx)
        try:
            stats = await st.client.api_get("api/Stats/GetCountStats")
            return json.dumps(stats, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_error_patterns(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        since: Annotated[str | None, Field(description="ISO 8601 start date")] = None,
        top_n: Annotated[int, Field(description="Return top N error patterns", ge=1, le=50)] = 10,
    ) -> str:
        """
        Analyse robot logs to find the most frequent error messages.
        Useful for identifying recurring failures and prioritising fixes.
        """
        st = _state(ctx)
        try:
            parts = ["Level eq 'Error'"]
            if since:
                parts.append(f"TimeStamp ge datetime'{since.rstrip('Z')}'")
            params = (
                ODataParams()
                .top(2000)
                .filter(" and ".join(parts))
                .select("Message", "ProcessName", "RobotName")
            )
            data = await st.client.get("RobotLogs", params=params.build(), folder_id=folder_id)
            logs = data.get("value", [])

            # Group by message prefix (first 100 chars) to normalise
            pattern_counts: dict[str, int] = {}
            pattern_processes: dict[str, set[str]] = {}

            for log in logs:
                msg = (log.get("Message") or "")[:100].strip()
                process = log.get("ProcessName", "unknown")
                pattern_counts[msg] = pattern_counts.get(msg, 0) + 1
                if msg not in pattern_processes:
                    pattern_processes[msg] = set()
                pattern_processes[msg].add(process)

            top_patterns = sorted(pattern_counts.items(), key=lambda x: -x[1])[:top_n]
            result = [
                {
                    "error_pattern": pattern,
                    "occurrences": count,
                    "processes": list(pattern_processes.get(pattern, set())),
                }
                for pattern, count in top_patterns
            ]
            return json.dumps(
                {"total_errors_analyzed": len(logs), "top_error_patterns": result},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())
