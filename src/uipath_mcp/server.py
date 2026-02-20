"""
UiPath MCP Server — main entry point.

Uses FastMCP with a lifespan context manager to:
  1. Validate configuration (with rich error panel on failure)
  2. Initialise the UiPath HTTP client (once; reused across all tool calls)
  3. Register all tools and resources
  4. Run with the configured transport (stdio / sse / streamable-http)

Logging always goes to stderr — stdout is reserved for the MCP JSON-RPC stream.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from loguru import logger
from mcp.server.fastmcp import FastMCP

from .auth import create_auth_strategy
from .client import UiPathClient
from .config import Settings, get_settings


# ── Logging setup ──────────────────────────────────────────────────────────────

def _setup_logging(settings: Settings) -> None:
    """Configure loguru to write to stderr in plain or JSON format."""
    logger.remove()
    if settings.log_json:
        logger.add(sys.stderr, level=settings.log_level.value, serialize=True)
    else:
        logger.add(
            sys.stderr,
            level=settings.log_level.value,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan> - {message}"
            ),
            colorize=True,
        )


# ── Application state ──────────────────────────────────────────────────────────

@dataclass
class AppState:
    """Shared state injected into every tool call via ctx.request_context.lifespan_context."""

    client: UiPathClient
    settings: Settings


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[AppState]:  # noqa: ARG001
    """Startup → yield AppState → shutdown."""
    try:
        settings = get_settings()
    except Exception as exc:
        # Show a rich, human-readable error instead of a raw stack trace
        from rich.console import Console
        from rich.panel import Panel

        Console(stderr=True).print(
            Panel(
                f"[bold red]Configuration Error[/bold red]\n\n{exc}\n\n"
                "[yellow]Copy [bold].env.example[/bold] to [bold].env[/bold] "
                "and fill in the required values.[/yellow]",
                title="UiPath MCP Server — Failed to Start",
                border_style="red",
            )
        )
        raise SystemExit(1) from exc

    _setup_logging(settings)
    logger.info(
        f"UiPath MCP Server starting "
        f"(auth={settings.auth_mode.value}, transport={settings.mcp_transport})"
    )

    auth = create_auth_strategy(settings)

    # Register tools here (inside lifespan) so read_only_mode is available.
    # Each module's register() skips write tools when read_only=True.
    from .tools import (  # noqa: PLC0415
        analytics, assets, audit, folders, jobs, packages, queues, robots, schedules, webhooks,
    )
    from . import resources as _resources  # noqa: PLC0415

    ro = settings.read_only_mode
    jobs.register(mcp, read_only=ro)
    queues.register(mcp, read_only=ro)
    robots.register(mcp)
    assets.register(mcp, read_only=ro)
    analytics.register(mcp)
    audit.register(mcp)
    schedules.register(mcp, read_only=ro)
    folders.register(mcp)
    webhooks.register(mcp, read_only=ro)
    packages.register(mcp)
    _resources.register(mcp)

    if ro:
        logger.info("READ_ONLY_MODE=true — write tools are not registered")

    async with UiPathClient(settings, auth) as client:
        logger.info(
            f"Connected to {settings.orchestrator_base_url} "
            f"(folder_id={settings.uipath_folder_id})"
        )
        yield AppState(client=client, settings=settings)

    logger.info("UiPath MCP Server shut down cleanly")


# ── FastMCP server ─────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="uipath-orchestrator",
    instructions=(
        "MCP server for UiPath Orchestrator. "
        "Provides tools for job management, queue operations, robot monitoring, "
        "asset management, process scheduling, analytics, audit logs, folder "
        "management, and webhook configuration. "
        "Most tools accept an optional folder_id parameter to scope the request "
        "to a specific Orchestrator folder/organization unit."
    ),
    lifespan=_lifespan,
)

# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for the `uipath-mcp` CLI command."""
    settings = get_settings()
    kwargs: dict = {}
    if settings.mcp_transport != "stdio":
        kwargs["host"] = settings.mcp_host
        kwargs["port"] = settings.mcp_port
    mcp.run(transport=settings.mcp_transport, **kwargs)


if __name__ == "__main__":
    main()
