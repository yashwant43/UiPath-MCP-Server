# Multi-Tenant Profile Support

Store multiple UiPath tenant credentials in the OS keyring and select one per server session.

## Problem

The current keyring integration stores a single set of credentials under the service name `uipath-mcp`. Users working with multiple tenants (e.g., prod, staging, different orgs) must manually re-run `auth setup` or juggle `.env` files.

## Design

### Keyring Storage Scheme

Each profile gets its own namespaced service name:

- `uipath-mcp/default` — the default profile
- `uipath-mcp/prod` — a user-named profile
- `uipath-mcp/myorg/mytenant` — an auto-derived profile

A profile index entry at `uipath-mcp/__profiles__` stores a comma-separated list of profile names (e.g., `"default,prod,myorg/mytenant"`). This powers `auth list` without scanning.

### Fields Per Profile

Same as today's `KEYRING_FIELDS` plus `read_only_mode`:

```
auth_mode, uipath_client_id, uipath_client_secret, uipath_org_name,
uipath_tenant_name, uipath_base_url, uipath_username, uipath_password,
uipath_pat, uipath_folder_id, uipath_folder_path, read_only_mode
```

### Profile Naming

- If `--profile` is given during setup, use it as-is.
- If omitted, auto-derive from credentials: `org/tenant` (cloud) or `tenant` (on_prem/pat).
- User is shown the derived name and prompted to accept or override.

### CLI Commands

All existing `auth` subcommands gain an optional `--profile` flag:

| Command | Behavior |
|---|---|
| `uipath-mcp auth setup [--profile NAME]` | Interactive setup. Prompts for auth mode, credentials, read-only mode, and profile name (if not given via flag). |
| `uipath-mcp auth test [--profile NAME]` | Verify a profile's credentials. Defaults to `"default"`. |
| `uipath-mcp auth clear [--profile NAME]` | Delete a profile from keyring and remove from index. Defaults to `"default"`. |
| `uipath-mcp auth list` | Table of all profiles: Name, Auth Mode, Org/Tenant, Read-Only. |

### Server Startup

Top-level `--profile` flag on the main command:

```bash
uipath-mcp --profile prod
```

Profile resolution order:
1. `--profile` CLI flag
2. `UIPATH_PROFILE` environment variable
3. `"default"`

This is session-scoped — no persistent "active profile" state is written.

### Config Integration

`get_settings()` signature becomes `get_settings(profile: str | None = None)`.

- `load_from_keyring(profile)` reads from `uipath-mcp/<profile>`.
- `read_only_mode` from keyring is included in the Settings init kwargs.
- `READ_ONLY_MODE` env var, if set, is excluded from keyring dict so pydantic-settings env var handling takes precedence. (Init kwargs have highest priority in pydantic-settings, so we must not pass keyring values for fields where the env var should win.)
- Settings singleton remains — one process, one profile, one singleton.

### Backward Compatibility & Migration

**Automatic migration:** When `load_from_keyring("default")` finds no credentials under `uipath-mcp/default` but old-style credentials exist under `uipath-mcp`, it:
1. Copies all fields to `uipath-mcp/default`
2. Adds `"default"` to the profile index
3. Deletes old entries
4. Logs at DEBUG level

**No-keyring fallback:** If keyring is unavailable, `--profile` is silently ignored (DEBUG log). Env vars / `.env` work as before.

**Existing Claude Desktop configs:** No `--profile` flag → `"default"` profile → migrated credentials. Zero config change needed.

### Files Changed

| File | Change |
|---|---|
| `keyring_store.py` | Namespace service names by profile, add profile index CRUD, add migration logic, add `read_only_mode` to `KEYRING_FIELDS` |
| `cli.py` | Add `--profile` option to `main` and all `auth` subcommands, add `auth list` command, add read-only prompt to `setup`, pass profile name through to `_start_server` |
| `config.py` | `get_settings(profile)`, `load_from_keyring(profile)`, handle `read_only_mode` env var override |
| `tests/conftest.py` | Update fixtures for profile-aware keyring functions |
| `tests/` | New tests for multi-profile storage, migration, CLI commands, profile resolution |

### Out of Scope

- Switching profiles mid-session (MCP tool)
- Profile export/import
- Profile aliases or shortcuts
