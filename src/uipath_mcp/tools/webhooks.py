"""
Webhook management tools — 4 tools (ALL new vs JS version).

  list_webhooks  create_webhook  update_webhook  delete_webhook
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError
from ..models import Webhook


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP, read_only: bool = False) -> None:

    @mcp.tool()
    async def list_webhooks(
        ctx: Context,
        top: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> str:
        """List all configured webhook subscriptions."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).count().build()
            data = await st.client.get("Webhooks", params=params)
            webhooks = [Webhook.model_validate(w).model_dump() for w in data.get("value", [])]
            return json.dumps(
                {"total_count": data.get("@odata.count", len(webhooks)), "webhooks": webhooks},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    if not read_only:

        @mcp.tool()
        async def create_webhook(
            ctx: Context,
            name: Annotated[str, Field(description="Webhook name")],
            url: Annotated[str, Field(description="Target URL that will receive events")],
            events: Annotated[
                list[str] | None,
                Field(
                    description=(
                        "Event types to subscribe to. "
                        "e.g. ['job.completed', 'queue.item.failed']. "
                        "Omit to subscribe to all events."
                    )
                ),
            ] = None,
            enabled: Annotated[bool, Field(description="Start enabled")] = True,
            secret: Annotated[
                str | None, Field(description="HMAC secret for payload signature verification")
            ] = None,
            allow_insecure_ssl: Annotated[bool, Field(description="Allow self-signed SSL certs")] = False,
        ) -> str:
            """Create a new webhook subscription."""
            st = _state(ctx)
            try:
                body: dict[str, Any] = {
                    "Name": name,
                    "Url": url,
                    "Enabled": enabled,
                    "AllowInsecureSsl": allow_insecure_ssl,
                    "SubscribeToAllEvents": events is None,
                }
                if secret:
                    body["Secret"] = secret
                if events:
                    body["Events"] = [{"EventType": e} for e in events]

                result = await st.client.post("Webhooks", body=body)
                return json.dumps(
                    {"message": f"Webhook '{name}' created", "webhook": result}, default=str
                )
            except UiPathError as e:
                return json.dumps(e.to_dict())

        @mcp.tool()
        async def update_webhook(
            ctx: Context,
            webhook_id: Annotated[int, Field(description="Webhook ID to update")],
            url: Annotated[str | None, Field(description="New target URL")] = None,
            enabled: Annotated[bool | None, Field(description="Enable or disable")] = None,
            name: Annotated[str | None, Field(description="New name")] = None,
        ) -> str:
            """Update a webhook's URL, name, or enabled state."""
            st = _state(ctx)
            try:
                body: dict[str, Any] = {}
                if url is not None:
                    body["Url"] = url
                if enabled is not None:
                    body["Enabled"] = enabled
                if name is not None:
                    body["Name"] = name
                if not body:
                    return json.dumps({"error": "No update fields provided"})
                await st.client.patch("Webhooks", webhook_id, body)
                return json.dumps({"message": f"Webhook {webhook_id} updated"})
            except UiPathError as e:
                return json.dumps(e.to_dict())

        @mcp.tool()
        async def delete_webhook(
            ctx: Context,
            webhook_id: Annotated[int, Field(description="Webhook ID to delete")],
        ) -> str:
            """Delete a webhook subscription."""
            st = _state(ctx)
            try:
                await st.client.delete("Webhooks", webhook_id)
                return json.dumps({"message": f"Webhook {webhook_id} deleted"})
            except UiPathError as e:
                return json.dumps(e.to_dict())
