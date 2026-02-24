"""
CLI entry point for the UiPath MCP Server.

Usage::

    uipath-mcp                  Start the MCP server (default)
    uipath-mcp auth setup       Store credentials in OS keyring
    uipath-mcp auth test        Verify stored credentials are accessible
    uipath-mcp auth clear       Remove all stored credentials from keyring
"""

from __future__ import annotations

import sys

import click


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """UiPath Orchestrator MCP Server."""
    if ctx.invoked_subcommand is None:
        _start_server()


@main.group()
def auth() -> None:
    """Manage credentials stored in the OS keyring."""


@auth.command()
@click.option(
    "--mode",
    type=click.Choice(["cloud", "on_prem", "pat"], case_sensitive=False),
    prompt="Authentication mode",
    help="Authentication mode: cloud, on_prem, or pat",
)
def setup(mode: str) -> None:
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
        store_credential("auth_mode", mode)

        for field_name, label, is_secret in fields_by_mode[mode]:
            value = click.prompt(f"  {label}", hide_input=is_secret)
            store_credential(field_name, value)

        for field_name, label in optional_fields:
            value = click.prompt(f"  {label} (press Enter to skip)", default="", show_default=False)
            if value:
                store_credential(field_name, value)

        console.print(
            Panel(
                f"[green]Credentials stored in OS keyring[/green] (service: uipath-mcp)\n"
                f"Auth mode: {mode}\n\n"
                "[dim]Run [bold]uipath-mcp auth test[/bold] to verify.[/dim]",
                title="Setup Complete",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[red]Failed to store credentials:[/red] {exc}", err=True)
        sys.exit(1)


@auth.command("test")
def test_cmd() -> None:
    """Verify that stored credentials are accessible and valid."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from .keyring_store import KEYRING_FIELDS, read_all

    console = Console()

    try:
        stored = read_all()
    except Exception as exc:
        console.print(f"[red]Keyring unavailable:[/red] {exc}", err=True)
        sys.exit(1)

    if not stored:
        console.print("[yellow]No credentials found in keyring.[/yellow]")
        console.print("Run [bold]uipath-mcp auth setup[/bold] first.")
        sys.exit(1)

    # Display stored fields (mask secrets)
    secret_fields = {"uipath_client_secret", "uipath_password", "uipath_pat"}
    table = Table(title="Stored Credentials")
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


@auth.command()
@click.confirmation_option(prompt="Remove all UiPath credentials from keyring?")
def clear() -> None:
    """Remove all stored UiPath credentials from the OS keyring."""
    from rich.console import Console

    from .keyring_store import clear_all

    console = Console()
    try:
        count = clear_all()
        console.print(f"[green]Cleared {count} credential(s) from keyring.[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to clear credentials:[/red] {exc}", err=True)
        sys.exit(1)


def _start_server() -> None:
    """Start the MCP server (delegates to server module)."""
    from .config import get_settings
    from .server import mcp

    settings = get_settings()
    kwargs: dict = {}
    if settings.mcp_transport != "stdio":
        kwargs["host"] = settings.mcp_host
        kwargs["port"] = settings.mcp_port
    mcp.run(transport=settings.mcp_transport, **kwargs)
