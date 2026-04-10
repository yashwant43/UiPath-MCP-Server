"""
CLI entry point for the UiPath MCP Server.

Usage::

    uipath-mcp                  Start the MCP server (default)
    uipath-mcp --profile prod   Start the MCP server with a named profile
    uipath-mcp auth setup       Store credentials in OS keyring
    uipath-mcp auth test        Verify stored credentials are accessible
    uipath-mcp auth clear       Remove all stored credentials from keyring
    uipath-mcp auth list        List all stored profiles
"""

from __future__ import annotations

import sys

import click


# ── Helper wrappers (easy to mock in tests) ──────────────────────────────────


def _add_profile_to_index(profile: str) -> None:
    from .keyring_store import add_profile_to_index

    add_profile_to_index(profile)


def _remove_profile_from_index(profile: str) -> None:
    from .keyring_store import remove_profile_from_index

    remove_profile_from_index(profile)


# ── CLI Groups ───────────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option(
    "--profile",
    default=None,
    envvar="UIPATH_PROFILE",
    help="Profile name to use (default: from keyring or env).",
)
@click.pass_context
def main(ctx: click.Context, profile: str | None) -> None:
    """UiPath Orchestrator MCP Server."""
    ctx.ensure_object(dict)
    ctx.obj["profile"] = profile
    if ctx.invoked_subcommand is None:
        _start_server(profile=profile)


@main.group()
def auth() -> None:
    """Manage credentials stored in the OS keyring."""


# ── auth setup ───────────────────────────────────────────────────────────────


@auth.command()
@click.option(
    "--mode",
    type=click.Choice(["cloud", "on_prem", "pat"], case_sensitive=False),
    prompt="Authentication mode",
    help="Authentication mode: cloud, on_prem, or pat",
)
@click.option(
    "--profile",
    default=None,
    help="Profile name (auto-derived if not given).",
)
def setup(mode: str, profile: str | None) -> None:
    """Interactive setup: store UiPath credentials in the OS keyring."""
    from rich.console import Console
    from rich.panel import Panel

    from .keyring_store import store_credential

    console = Console()

    # Required fields per auth mode: (field_name, prompt_label, is_secret)
    fields_by_mode: dict[str, list[tuple[str, str, bool]]] = {
        "cloud": [
            ("uipath_client_id", "Client ID", False),
            ("uipath_client_secret", "Client Secret", True),
            ("uipath_org_name", "Organization slug", False),
            ("uipath_tenant_name", "Tenant name", False),
        ],
        "on_prem": [
            ("uipath_base_url", "Orchestrator base URL", False),
            ("uipath_username", "Username", False),
            ("uipath_password", "Password", True),
            ("uipath_tenant_name", "Tenant name", False),
        ],
        "pat": [
            ("uipath_base_url", "Orchestrator base URL", False),
            ("uipath_pat", "Personal Access Token", True),
            ("uipath_tenant_name", "Tenant name", False),
        ],
    }

    optional_fields: list[tuple[str, str]] = [
        ("uipath_folder_id", "Default folder ID"),
        ("uipath_folder_path", "Default folder path"),
    ]

    try:
        # Collect all values first before storing
        collected: dict[str, str] = {"auth_mode": mode}

        for field_name, label, is_secret in fields_by_mode[mode]:
            value = click.prompt(f"  {label}", hide_input=is_secret)
            collected[field_name] = value

        for field_name, label in optional_fields:
            value = click.prompt(f"  {label} (press Enter to skip)", default="", show_default=False)
            if value:
                collected[field_name] = value

        # Read-only mode prompt
        read_only = click.confirm("  Read-only mode?", default=False)
        if read_only:
            collected["read_only_mode"] = "true"

        # Auto-derive profile name if not given
        if profile is None:
            if mode == "cloud":
                org = collected.get("uipath_org_name", "")
                tenant = collected.get("uipath_tenant_name", "")
                derived = f"{org}/{tenant}" if org and tenant else "default"
            else:
                derived = collected.get("uipath_tenant_name", "default")
            profile = click.prompt("  Profile name", default=derived)

        # Now store everything
        for field_name, value in collected.items():
            store_credential(field_name, value, profile=profile)

        _add_profile_to_index(profile)

        console.print(
            Panel(
                f"[green]Credentials stored in OS keyring[/green] (profile: {profile})\n"
                f"Auth mode: {mode}\n\n"
                "[dim]Run [bold]uipath-mcp auth test[/bold] to verify.[/dim]",
                title="Setup Complete",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[red]Failed to store credentials:[/red] {exc}", err=True)
        sys.exit(1)


# ── auth test ────────────────────────────────────────────────────────────────


@auth.command("test")
@click.option("--profile", default="default", help="Profile name to test.")
def test_cmd(profile: str) -> None:
    """Verify that stored credentials are accessible and valid."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from .keyring_store import KEYRING_FIELDS, read_all

    console = Console()

    try:
        stored = read_all(profile=profile)
    except Exception as exc:
        console.print(f"[red]Keyring unavailable:[/red] {exc}", err=True)
        sys.exit(1)

    if not stored:
        console.print("[yellow]No credentials found in keyring.[/yellow]")
        console.print("Run [bold]uipath-mcp auth setup[/bold] first.")
        sys.exit(1)

    # Display stored fields (mask secrets)
    secret_fields = {"uipath_client_secret", "uipath_password", "uipath_pat"}
    table = Table(title=f"Stored Credentials (profile: {profile})")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    for field in KEYRING_FIELDS:
        if field in stored:
            display = "****" if field in secret_fields else stored[field]
            table.add_row(field, display)
    console.print(table)

    # Validate by constructing Settings
    try:
        from .config import Settings

        settings = Settings(**stored)
        console.print(
            Panel(
                f"[green]Configuration valid![/green]\n"
                f"Auth mode: {settings.auth_mode.value}\n"
                f"Base URL: {settings.orchestrator_base_url}",
                title="Auth Test Passed",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(
            Panel(
                f"[red]Configuration invalid:[/red]\n{exc}",
                title="Auth Test Failed",
                border_style="red",
            ),
            err=True,
        )
        sys.exit(1)


# ── auth clear ───────────────────────────────────────────────────────────────


@auth.command()
@click.option("--profile", default="default", help="Profile name to clear.")
@click.confirmation_option(prompt="Remove all UiPath credentials from keyring?")
def clear(profile: str) -> None:
    """Remove all stored UiPath credentials from the OS keyring."""
    from rich.console import Console

    from .keyring_store import clear_all

    console = Console()
    try:
        count = clear_all(profile=profile)
        _remove_profile_from_index(profile)
        console.print(f"[green]Cleared {count} credential(s) from keyring (profile: {profile}).[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to clear credentials:[/red] {exc}", err=True)
        sys.exit(1)


# ── auth list ────────────────────────────────────────────────────────────────


@auth.command("list")
def list_cmd() -> None:
    """List all stored profiles and their settings."""
    from rich.console import Console
    from rich.table import Table

    from .keyring_store import list_profiles, read_all

    console = Console()

    profiles = list_profiles()
    if not profiles:
        console.print("[yellow]No profiles found.[/yellow]")
        return

    table = Table(title="Stored Profiles")
    table.add_column("Profile", style="cyan")
    table.add_column("Auth Mode")
    table.add_column("Org/Tenant")
    table.add_column("Read-Only")

    for name in profiles:
        creds = read_all(profile=name)
        auth_mode = creds.get("auth_mode", "?")
        org = creds.get("uipath_org_name", "")
        tenant = creds.get("uipath_tenant_name", "")
        org_tenant = f"{org}/{tenant}" if org else tenant
        read_only = creds.get("read_only_mode", "false")
        table.add_row(name, auth_mode, org_tenant, read_only)

    console.print(table)


# ── Server start ─────────────────────────────────────────────────────────────


def _start_server(profile: str | None = None) -> None:
    """Start the MCP server (delegates to server module)."""
    from .config import get_settings
    from .server import mcp

    settings = get_settings(profile=profile)
    kwargs: dict = {}
    if settings.mcp_transport != "stdio":
        kwargs["host"] = settings.mcp_host
        kwargs["port"] = settings.mcp_port
    mcp.run(transport=settings.mcp_transport, **kwargs)
