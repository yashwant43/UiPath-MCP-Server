"""
Audit log tools — 4 tools.

  list_audit_logs  get_audit_log_detail  ⭐new
  list_robot_logs  export_audit_logs  ⭐new
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError
from ..models import AuditLog, RobotLog


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_audit_logs(
        ctx: Context,
        user_name: Annotated[str | None, Field(description="Filter by username")] = None,
        entity_type: Annotated[
            str | None,
            Field(description="Filter by entity type e.g. Robot | Asset | Queue | Job | Schedule"),
        ] = None,
        action: Annotated[
            str | None,
            Field(description="Filter by operation type e.g. Create | Update | Delete"),
        ] = None,
        since: Annotated[str | None, Field(description="ISO 8601 start datetime e.g. 2024-01-01T00:00:00Z")] = None,
        until: Annotated[str | None, Field(description="ISO 8601 end datetime")] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
        skip: Annotated[int, Field(ge=0)] = 0,
    ) -> str:
        """
        Query the Orchestrator audit log with optional filters.

        For UiPath Cloud this uses the modern Audit REST API
        (https://cloud.uipath.com/{org}/audit_/api/auditlogs) which requires
        PM.Audit.Read scope on your External Application.
        For on-premise deployments the legacy OData endpoint is used instead.
        """
        st = _state(ctx)
        audit_url = st.settings.audit_api_url
        try:
            if audit_url:
                # Cloud: modern Audit REST API (OData AuditLogs removed Dec 2023)
                params: dict[str, Any] = {
                    "language": "en",
                    "top": top,
                    "skip": skip,
                    "sortBy": "createdOn",
                    "sortOrder": "desc",
                }
                if user_name:
                    params["userName"] = user_name
                if entity_type:
                    params["entityType"] = entity_type
                if action:
                    params["operationType"] = action
                if since:
                    params["startTime"] = since
                if until:
                    params["endTime"] = until
                response = await st.client._request("GET", f"{audit_url}/auditlogs", params=params)
                data = response.json()
                results = data.get("results", data.get("items", data.get("value", [])))
                total = data.get("totalCount", data.get("total", len(results)))
                return json.dumps({"total_count": total, "skip": skip, "logs": results}, default=str)
            else:
                # On-prem: legacy OData endpoint
                parts: list[str] = []
                if user_name:
                    parts.append(f"UserName eq '{user_name}'")
                if entity_type:
                    parts.append(f"EntityType eq '{entity_type}'")
                if action:
                    parts.append(f"Action eq '{action}'")
                if since:
                    parts.append(f"CreationTime ge datetime'{since.rstrip('Z')}'")
                odata = ODataParams().top(top).skip(skip).count().orderby("CreationTime", "desc")
                if parts:
                    odata.filter(" and ".join(parts))
                odata_data = await st.client.get("AuditLogs", params=odata.build())
                logs = [AuditLog.model_validate(l).model_dump() for l in odata_data.get("value", [])]
                return json.dumps(
                    {"total_count": odata_data.get("@odata.count"), "skip": skip, "logs": logs},
                    default=str,
                )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_audit_log_detail(
        ctx: Context,
        audit_log_id: Annotated[str, Field(description="Audit log entry ID (integer for on-prem, UUID string for Cloud)")],
    ) -> str:
        """Get full details of a specific audit log entry including the change payload."""
        st = _state(ctx)
        audit_url = st.settings.audit_api_url
        try:
            if audit_url:
                response = await st.client._request("GET", f"{audit_url}/auditlogs/{audit_log_id}")
                return json.dumps(response.json(), default=str)
            else:
                data = await st.client.get_by_id("AuditLogs", audit_log_id)
                return json.dumps(AuditLog.model_validate(data).model_dump(), default=str)
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
        since: Annotated[str | None, Field(description="ISO 8601 start date")] = None,
        until: Annotated[str | None, Field(description="ISO 8601 end date")] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> str:
        """Query robot execution logs with rich filtering options."""
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
            if until:
                parts.append(f"TimeStamp le datetime'{until.rstrip('Z')}'")
            params = ODataParams().top(top).orderby("TimeStamp", "desc")
            if parts:
                params.filter(" and ".join(parts))
            data = await st.client.get("RobotLogs", params=params.build(), folder_id=folder_id)
            logs = [RobotLog.model_validate(l).model_dump() for l in data.get("value", [])]
            return json.dumps({"count": len(logs), "logs": logs}, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def export_audit_logs(
        ctx: Context,
        since: Annotated[str | None, Field(description="ISO 8601 start datetime")] = None,
        until: Annotated[str | None, Field(description="ISO 8601 end datetime")] = None,
        max_records: Annotated[int, Field(ge=1, le=10000)] = 1000,
    ) -> str:
        """
        Export audit logs as a JSON array suitable for further processing or saving.
        Collects up to max_records entries automatically across pages.
        """
        st = _state(ctx)
        audit_url = st.settings.audit_api_url
        try:
            if audit_url:
                # Cloud: paginate the new REST API manually
                all_logs: list[Any] = []
                page_size = min(100, max_records)
                skip = 0
                while len(all_logs) < max_records:
                    params: dict[str, Any] = {
                        "language": "en",
                        "top": page_size,
                        "skip": skip,
                        "sortBy": "createdOn",
                        "sortOrder": "desc",
                    }
                    if since:
                        params["startTime"] = since
                    if until:
                        params["endTime"] = until
                    response = await st.client._request("GET", f"{audit_url}/auditlogs", params=params)
                    data = response.json()
                    page = data.get("results", data.get("items", data.get("value", [])))
                    if not page:
                        break
                    all_logs.extend(page)
                    skip += page_size
                    if len(page) < page_size:
                        break  # last page
                return json.dumps(
                    {"exported_count": len(all_logs), "logs": all_logs[:max_records]},
                    default=str,
                )
            else:
                # On-prem: OData collect_all
                parts: list[str] = []
                if since:
                    parts.append(f"CreationTime ge datetime'{since.rstrip('Z')}'")
                if until:
                    parts.append(f"CreationTime le datetime'{until.rstrip('Z')}'")
                odata_params: dict = {"$orderby": "CreationTime desc"}
                if parts:
                    odata_params["$filter"] = " and ".join(parts)
                raw = await st.client.collect_all("AuditLogs", params=odata_params, max_items=max_records)
                structured = [AuditLog.model_validate(l).model_dump() for l in raw]
                return json.dumps({"exported_count": len(structured), "logs": structured}, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())
