"""
MCP Resources for the UiPath Orchestrator server.

Resources expose read-only data that AI clients can browse without tool invocations.
They are cheap to read and serve as ambient context.

URIs:
  uipath://config/server         - Current server configuration (no secrets)
  uipath://help/odata-filters    - OData filter syntax reference
  uipath://help/tool-overview    - Quick reference of all available tools
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import get_settings


def register(mcp: FastMCP) -> None:

    @mcp.resource("uipath://config/server")
    def get_server_config() -> str:
        """Current UiPath MCP server configuration (no secrets exposed)."""
        s = get_settings()
        lines = [
            "UiPath MCP Server — Active Configuration",
            "=" * 45,
            f"  Auth mode       : {s.auth_mode.value}",
            f"  Organization    : {s.uipath_org_name or 'N/A'}",
            f"  Tenant          : {s.uipath_tenant_name or 'N/A'}",
            f"  Orchestrator URL: {s.orchestrator_base_url}",
            f"  Default folder  : {s.uipath_folder_id or 'none (pass folder_id to each tool)'}",
            f"  Transport       : {s.mcp_transport}",
            f"  HTTP timeout    : {s.http_timeout}s",
            f"  Retry attempts  : {s.retry_max_attempts}",
            f"  Default page    : {s.default_page_size} items",
            f"  Log level       : {s.log_level.value}",
        ]
        return "\n".join(lines)

    @mcp.resource("uipath://help/odata-filters")
    def get_odata_filter_guide() -> str:
        """OData $filter syntax reference for UiPath Orchestrator tools."""
        return """\
OData Filter Expression Guide for UiPath Orchestrator Tools
===========================================================

Comparison operators
  eq  - equals:           State eq 'Running'
  ne  - not equals:       State ne 'Faulted'
  gt  - greater than:     Id gt 1000
  lt  - less than:        Id lt 5000
  ge  - greater or equal: CreationTime ge 2024-01-01T00:00:00Z
  le  - less or equal:    CreationTime le 2024-12-31T23:59:59Z

String functions
  contains(Field, 'text')       partial match
  startswith(Field, 'prefix')   starts with prefix
  endswith(Field, 'suffix')     ends with suffix

Logical operators
  and  /  or  /  not

Enum fields
  UiPath enums require the full type path in the filter:
    State eq UiPath.Server.Configuration.OData.JobState'Faulted'
    Status eq UiPath.Server.Configuration.OData.QueueItemStatus'New'
    Level eq UiPath.Server.Configuration.OData.RobotLogLevel'Error'

Common examples
  Faulted jobs today:
    State eq UiPath.Server.Configuration.OData.JobState'Faulted'
    and CreationTime ge 2024-06-01T00:00:00Z

  High-priority new queue items:
    Status eq UiPath.Server.Configuration.OData.QueueItemStatus'New'
    and Priority eq UiPath.Server.Configuration.OData.QueueItemPriority'High'

  Error logs for a specific robot:
    RobotName eq 'MyRobot'
    and Level eq UiPath.Server.Configuration.OData.RobotLogLevel'Error'
"""

    @mcp.resource("uipath://help/tool-overview")
    def get_tool_overview() -> str:
        """Quick reference of all tools grouped by category."""
        return """\
UiPath MCP Server — Tool Overview
===================================

Job Management (12 tools)
  list_jobs              List jobs with state/process filters and pagination
  list_running_jobs      Shortcut: only Running jobs
  list_failed_jobs       Shortcut: Faulted jobs with date filter
  list_jobs_by_process   All jobs for a specific process name
  get_job                Full details of one job by ID
  get_job_output         Parsed output arguments from a completed job
  get_job_statistics     Success/failure rates for a process
  get_job_logs           Execution logs for a job (by job Key GUID)
  start_job              Start a process job (auto-looks up release key)
  stop_job               Stop one job (SoftStop or Kill)
  bulk_stop_jobs ⭐       Stop multiple jobs concurrently
  wait_for_job ⭐         Poll until terminal state with progress reporting

Queue Management (10 tools)
  list_queues            All queues with stats
  get_queue              Single queue by ID or name
  add_queue_item         Add one item
  bulk_add_queue_items ⭐ Up to 1000 items in one API call
  list_queue_items       Items with status/queue filter + pagination
  get_queue_item         Single item by ID
  update_queue_item_status ⭐  Set review status
  delete_queue_item ⭐    Delete an item
  get_queue_stats        Throughput, success rate
  retry_failed_items ⭐   Bulk-retry all failed items

Robot & Machine Management (8 tools)
  list_robots            All robots with name filter
  get_robot              Single robot by ID
  list_available_robots ⭐ Only Available-state sessions
  list_robot_sessions ⭐  Active connected sessions
  list_robot_logs        Execution logs with level/date/robot filters
  list_machines          Machine templates
  get_machine            Single machine by ID
  get_robot_license_info ⭐ Runtime + named-user license utilisation

Asset Management (7 tools)
  list_assets            Filter by type
  get_asset              By ID or name
  create_asset ⭐         Text, Integer, Bool, or Credential
  update_asset ⭐         Change value or description
  delete_asset ⭐         Remove an asset
  get_robot_asset        Per-robot scoped asset value
  set_credential_asset ⭐ Update username+password on Credential assets

Process Schedules (6 tools — all new ⭐)
  list_schedules         With enabled filter
  get_schedule           Single schedule by ID
  enable_schedule        Enable one schedule
  disable_schedule       Disable one schedule
  set_schedule_enabled   Bulk enable/disable
  get_next_executions    Upcoming executions sorted by time

Folder Management (5 tools — all new ⭐)
  list_folders           All accessible folders
  get_folder             By ID or display name
  list_sub_folders       Child folders of a parent
  list_folder_robots     Robots assigned to a folder
  get_folder_stats       Job + queue item counts for a folder

Analytics (6 tools)
  get_jobs_stats         Job counts by state for a date range
  get_queue_processing_stats  Queue throughput + avg duration
  get_license_usage      Consumption + traditional license stats
  get_robot_utilization  Connected/busy/idle session breakdown
  get_tenant_stats       Entity counts across the tenant
  get_error_patterns ⭐   Top recurring error messages from robot logs

Audit Logs (4 tools)
  list_audit_logs        Filter by user/entity/action/date
  get_audit_log_detail ⭐ Full detail of one audit entry
  list_robot_logs        Execution log search
  export_audit_logs ⭐    Paginated export up to 10 000 records

Webhooks (4 tools — all new ⭐)
  list_webhooks          All webhook subscriptions
  create_webhook         Create with event filter + HMAC secret
  update_webhook         Change URL, name, or enabled state
  delete_webhook         Remove a subscription

⭐ = New in Python version (not in JS original)
"""
