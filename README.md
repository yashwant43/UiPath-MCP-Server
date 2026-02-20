# UiPath Orchestrator MCP Server (Python)

A production-quality **Model Context Protocol (MCP)** server that connects AI assistants (Claude, Cursor, etc.) to **UiPath Orchestrator**. Built in Python with full async support, structured retry logic, and 53 tools — significantly more capable than the original JavaScript version.

## Why Python? Why better?

| Dimension | JS Version | This Python Version |
|-----------|-----------|---------------------|
| HTTP client | node-fetch, no pooling | httpx HTTP/2 + connection pooling |
| Retry logic | None | tenacity exponential+jitter, Retry-After |
| Token caching | Per-instance (race-unsafe) | Module-level asyncio.Lock (thundering-herd safe) |
| Config validation | process.env checks | Pydantic Settings, SecretStr, @model_validator |
| Data models | TypeScript interfaces | Pydantic v2 with field aliases |
| Error types | String errors | Structured UiPathError(message, status_code, error_code) |
| Pagination | None | paginate() async generator + collect_all() |
| Logging | console.log (stdout!) | loguru → stderr, JSON mode for prod |
| Startup errors | Stack traces | rich Panel with actionable instructions |
| Tool count | 30 | **53** (23 new tools) |
| Tests | Unknown | pytest-asyncio + respx transport mocking |

---

## Quick Start

### Option A — Install from PyPI (recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# or: pip install uv

# Install the package
uv tool install uipath-orchestrator-mcp

# Create your .env file
curl -o .env https://raw.githubusercontent.com/your-org/uipath-orchestrator-mcp/main/.env.example
# Edit .env with your UiPath credentials, then:
uipath-mcp
```

### Option B — From source

```bash
git clone https://github.com/your-org/uipath-orchestrator-mcp.git
cd uipath-orchestrator-mcp
uv sync
cp .env.example .env
# Edit .env with your UiPath credentials
uv run uipath-mcp
```

### Inspect with MCP Inspector

```bash
uv run mcp dev src/uipath_mcp/server.py
```

---

## Authentication

Set `AUTH_MODE` in your `.env` to one of:

### Cloud OAuth2 (`AUTH_MODE=cloud`) — recommended for Automation Cloud

Create an **External Application** in Automation Cloud → Admin → External Apps.

```env
AUTH_MODE=cloud
UIPATH_CLIENT_ID=your_client_id
UIPATH_CLIENT_SECRET=your_client_secret
UIPATH_ORG_NAME=your_org_slug
UIPATH_TENANT_NAME=DefaultTenant
```

### On-Premise (`AUTH_MODE=on_prem`)

```env
AUTH_MODE=on_prem
UIPATH_BASE_URL=https://myserver.company.com/orchestrator
UIPATH_USERNAME=admin@company.com
UIPATH_PASSWORD=your_password
UIPATH_TENANT_NAME=Default
```

### Personal Access Token (`AUTH_MODE=pat`)

```env
AUTH_MODE=pat
UIPATH_BASE_URL=https://cloud.uipath.com/org/tenant/orchestrator_
UIPATH_PAT=your_personal_access_token
UIPATH_TENANT_NAME=DefaultTenant
```

---

## Claude Desktop / Cursor Configuration

### If installed via PyPI (`uv tool install uipath-orchestrator-mcp`)

```json
{
  "mcpServers": {
    "uipath": {
      "command": "uipath-mcp",
      "env": {
        "AUTH_MODE": "cloud",
        "UIPATH_CLIENT_ID": "your_client_id",
        "UIPATH_CLIENT_SECRET": "your_client_secret",
        "UIPATH_ORG_NAME": "your_org",
        "UIPATH_TENANT_NAME": "DefaultTenant",
        "UIPATH_FOLDER_ID": "1"
      }
    }
  }
}
```

### If running from source

```json
{
  "mcpServers": {
    "uipath": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/path/to/uipath-orchestrator-mcp",
        "uipath-mcp"
      ],
      "env": {
        "AUTH_MODE": "cloud",
        "UIPATH_CLIENT_ID": "your_client_id",
        "UIPATH_CLIENT_SECRET": "your_client_secret",
        "UIPATH_ORG_NAME": "your_org",
        "UIPATH_TENANT_NAME": "DefaultTenant",
        "UIPATH_FOLDER_ID": "1"
      }
    }
  }
}
```

---

## Available Tools (53 total)

### Job Management (12)
- `list_jobs` — Filter by state/process, paginate, order
- `list_running_jobs` — Shortcut: only Running jobs
- `list_failed_jobs` — Shortcut: Faulted jobs with date filter
- `list_jobs_by_process` — All jobs for a process name
- `get_job` — Full details of one job
- `get_job_output` — Parsed output arguments from completed job
- `get_job_statistics` — Success/failure rates for a process
- `get_job_logs` — Execution logs for a job
- `start_job` — Start a process (auto-looks up release key)
- `stop_job` — Stop with SoftStop or Kill
- `bulk_stop_jobs` ⭐ — Stop multiple jobs concurrently
- `wait_for_job` ⭐ — Poll until terminal state with progress reporting

### Queue Management (10)
- `list_queues`, `get_queue`
- `add_queue_item`, `bulk_add_queue_items` ⭐ (up to 1000 items at once)
- `list_queue_items`, `get_queue_item`
- `update_queue_item_status` ⭐, `delete_queue_item` ⭐
- `get_queue_stats`, `retry_failed_items` ⭐

### Robot & Machine Management (8)
- `list_robots`, `get_robot`, `list_available_robots` ⭐
- `list_robot_sessions` ⭐, `list_robot_logs`
- `list_machines`, `get_machine`, `get_robot_license_info` ⭐

### Asset Management (7)
- `list_assets`, `get_asset`
- `create_asset` ⭐, `update_asset` ⭐, `delete_asset` ⭐
- `get_robot_asset`, `set_credential_asset` ⭐

### Process Schedules (6) ⭐ All new
- `list_schedules`, `get_schedule`
- `enable_schedule`, `disable_schedule`, `set_schedule_enabled`
- `get_next_executions`

### Folder Management (5) ⭐ All new
- `list_folders`, `get_folder`, `list_sub_folders`
- `list_folder_robots`, `get_folder_stats`

### Analytics (6)
- `get_jobs_stats`, `get_queue_processing_stats`
- `get_license_usage`, `get_robot_utilization`
- `get_tenant_stats`, `get_error_patterns` ⭐

### Audit Logs (4)
- `list_audit_logs`, `get_audit_log_detail` ⭐
- `list_robot_logs`, `export_audit_logs` ⭐

### Webhooks (4) ⭐ All new
- `list_webhooks`, `create_webhook`, `update_webhook`, `delete_webhook`

⭐ = New in Python version (not in JS original)

---

## Resources

Read-only resources available to AI clients:
- `uipath://config/server` — Active server configuration (no secrets)
- `uipath://help/odata-filters` — OData filter syntax reference
- `uipath://help/tool-overview` — Quick reference of all tools

---

## Configuration Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `AUTH_MODE` | cloud \| on_prem \| pat | `cloud` |
| `UIPATH_CLIENT_ID` | Cloud app client ID | — |
| `UIPATH_CLIENT_SECRET` | Cloud app client secret | — |
| `UIPATH_ORG_NAME` | Organization slug | — |
| `UIPATH_TENANT_NAME` | Tenant name | — |
| `UIPATH_BASE_URL` | On-prem Orchestrator URL | — |
| `UIPATH_USERNAME` | On-prem username | — |
| `UIPATH_PASSWORD` | On-prem password | — |
| `UIPATH_PAT` | Personal Access Token | — |
| `UIPATH_FOLDER_ID` | Default folder ID | — |
| `MCP_TRANSPORT` | stdio \| sse \| streamable-http | `stdio` |
| `MCP_HOST` | Host for HTTP transport | `127.0.0.1` |
| `MCP_PORT` | Port for HTTP transport | `8000` |
| `HTTP_TIMEOUT` | Request timeout (seconds) | `30.0` |
| `RETRY_MAX_ATTEMPTS` | Max retry attempts | `3` |
| `LOG_LEVEL` | DEBUG \| INFO \| WARNING \| ERROR | `INFO` |
| `LOG_JSON` | Structured JSON logs | `false` |

---

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Run linter
uv run ruff check src/ tests/

# Type check
uv run mypy src/
```

---

## Architecture

```
src/uipath_mcp/
├── server.py     FastMCP + lifespan (initialises client once)
├── config.py     Pydantic Settings (all env vars, cross-field validation)
├── auth.py       3 auth strategies + module-level TokenCache with asyncio.Lock
├── client.py     httpx AsyncClient + tenacity retry + ODataParams builder + paginate()
├── models.py     Pydantic v2 models (Job, Queue, Robot, Asset, ...)
├── resources.py  MCP resources (config, help guides)
└── tools/
    ├── jobs.py      analytics.py
    ├── queues.py    audit.py
    ├── robots.py    schedules.py
    ├── assets.py    folders.py
    └── webhooks.py
```

Token refresh uses double-checked locking to prevent thundering-herd refreshes:
```python
if cache.is_valid: return cache.access_token   # fast path (99% of calls)
async with cache._lock:                         # slow path
    if cache.is_valid: return cache.access_token  # re-check after lock
    token = await _do_refresh()                 # only ONE coroutine reaches here
```

---

## License

MIT
