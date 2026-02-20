"""
Tests for queue management tools.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_ctx
from uipath_mcp.client import UiPathError


class TestListQueues:

    async def test_returns_queue_list(self, pat_settings):
        queues_response = {
            "@odata.count": 2,
            "value": [
                {"Id": 1, "Name": "InvoiceQueue", "Description": "Invoice processing"},
                {"Id": 2, "Name": "OrderQueue", "Description": "Order processing"},
            ],
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=queues_response)
        ctx = make_mock_ctx(mock_client, pat_settings)

        from uipath_mcp.tools.queues import register
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        register(mcp)

        tool_fn = next(t.fn for t in mcp._tool_manager._tools.values() if t.name == "list_queues")
        result = json.loads(await tool_fn(ctx=ctx))

        assert result["total_count"] == 2
        assert result["queues"][0]["name"] == "InvoiceQueue"


class TestAddQueueItem:

    async def test_adds_item_with_correct_payload(self, pat_settings):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"Id": 501, "Status": "New"})
        ctx = make_mock_ctx(mock_client, pat_settings)

        from uipath_mcp.tools.queues import register
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        register(mcp)

        tool_fn = next(t.fn for t in mcp._tool_manager._tools.values() if t.name == "add_queue_item")
        result = json.loads(
            await tool_fn(
                ctx=ctx,
                queue_name="InvoiceQueue",
                specific_content={"InvoiceId": "INV-001", "Amount": 150.0},
                priority="High",
            )
        )

        assert "message" in result
        # Verify POST was called with the right body structure
        call_args = mock_client.post.call_args
        body = call_args.kwargs.get("body") or call_args.args[1]
        assert "itemData" in body
        assert body["itemData"]["Name"] == "InvoiceQueue"
        assert body["itemData"]["Priority"] == "High"

    async def test_bulk_add_returns_message(self, pat_settings):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"successful": 3, "failed": 0})
        ctx = make_mock_ctx(mock_client, pat_settings)

        from uipath_mcp.tools.queues import register
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        register(mcp)

        tool_fn = next(t.fn for t in mcp._tool_manager._tools.values() if t.name == "bulk_add_queue_items")
        items = [{"SpecificContent": {"Id": i}} for i in range(3)]
        result = json.loads(
            await tool_fn(ctx=ctx, queue_name="TestQueue", items=items)
        )

        assert "message" in result
        assert "3" in result["message"]
