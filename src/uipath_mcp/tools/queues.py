"""
Queue management tools — 10 tools.

  list_queues    get_queue        add_queue_item      bulk_add_queue_items  ⭐new
  list_queue_items  get_queue_item  update_queue_item_status  ⭐new
  delete_queue_item  ⭐new  get_queue_stats  retry_failed_items  ⭐new
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError
from ..models import Queue, QueueItem


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_queues(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> str:
        """List all queue definitions in a folder."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).count().build()
            data = await st.client.get("QueueDefinitions", params=params, folder_id=folder_id)
            queues = [Queue.model_validate(q).model_dump() for q in data.get("value", [])]
            return json.dumps(
                {"total_count": data.get("@odata.count", len(queues)), "queues": queues},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_queue(
        ctx: Context,
        queue_id: Annotated[int | None, Field(description="Queue definition ID")] = None,
        queue_name: Annotated[str | None, Field(description="Queue name (exact)")] = None,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Get a queue by ID or exact name."""
        st = _state(ctx)
        try:
            if queue_id:
                data = await st.client.get_by_id("QueueDefinitions", queue_id, folder_id=folder_id)
                return json.dumps(Queue.model_validate(data).model_dump(), default=str)
            if queue_name:
                params = ODataParams().filter(f"Name eq '{queue_name}'").top(1).build()
                data = await st.client.get("QueueDefinitions", params=params, folder_id=folder_id)
                items = data.get("value", [])
                if not items:
                    return json.dumps({"error": f"Queue '{queue_name}' not found"})
                return json.dumps(Queue.model_validate(items[0]).model_dump(), default=str)
            return json.dumps({"error": "Provide queue_id or queue_name"})
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def add_queue_item(
        ctx: Context,
        queue_name: Annotated[str, Field(description="Target queue name")],
        specific_content: Annotated[
            dict[str, Any], Field(description="Item payload as JSON object")
        ],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        priority: Annotated[str, Field(description="Low | Normal | High")] = "Normal",
        reference: Annotated[str | None, Field(description="Unique reference string")] = None,
        defer_date: Annotated[str | None, Field(description="ISO 8601 defer date")] = None,
        due_date: Annotated[str | None, Field(description="ISO 8601 due date")] = None,
    ) -> str:
        """Add a single item to a queue."""
        st = _state(ctx)
        try:
            item_data: dict[str, Any] = {
                "Name": queue_name,
                "Priority": priority,
                "SpecificContent": specific_content,
            }
            if reference:
                item_data["Reference"] = reference
            if defer_date:
                item_data["DeferDate"] = defer_date
            if due_date:
                item_data["DueDate"] = due_date

            result = await st.client.post(
                "Queues",
                body={"itemData": item_data},
                action="AddQueueItem",
                folder_id=folder_id,
            )
            return json.dumps(
                {"message": "Queue item added successfully", "item": result}, default=str
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def bulk_add_queue_items(
        ctx: Context,
        queue_name: Annotated[str, Field(description="Target queue name")],
        items: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    "List of item objects. Each must have 'SpecificContent' (dict). "
                    "Optional per item: Priority, Reference, DeferDate, DueDate."
                )
            ),
        ],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        commit_type: Annotated[
            str,
            Field(description="AllOrNothing (rollback on any fail) | ProcessAllIndependently"),
        ] = "AllOrNothing",
    ) -> str:
        """
        Add multiple queue items in a single API call (up to 1000 items).
        Much more efficient than calling add_queue_item repeatedly.
        """
        st = _state(ctx)
        if not items:
            return json.dumps({"error": "items list is empty"})
        try:
            body = {
                "queueName": queue_name,
                "commitType": commit_type,
                "queueItems": items,
            }
            result = await st.client.post(
                "Queues",
                body=body,
                action="BulkAddQueueItems",
                folder_id=folder_id,
            )
            return json.dumps(
                {
                    "message": f"Bulk added {len(items)} items to '{queue_name}'",
                    "result": result,
                },
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def list_queue_items(
        ctx: Context,
        queue_name: Annotated[str | None, Field(description="Filter by queue name")] = None,
        status: Annotated[
            str | None,
            Field(description="Filter by status: New | InProgress | Failed | Successful | Abandoned"),
        ] = None,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
        skip: Annotated[int, Field(ge=0)] = 0,
    ) -> str:
        """List queue items with optional filters."""
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
            if status:
                parts.append(f"Status eq '{status}'")
            params = ODataParams().top(top).skip(skip).count().orderby("CreationTime", "desc")
            if parts:
                params.filter(" and ".join(parts))
            data = await st.client.get("QueueItems", params=params.build(), folder_id=folder_id)
            items = [QueueItem.model_validate(i).model_dump() for i in data.get("value", [])]
            return json.dumps(
                {"total_count": data.get("@odata.count"), "skip": skip, "items": items},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_queue_item(
        ctx: Context,
        item_id: Annotated[int, Field(description="Queue item ID")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Get details of a single queue item by ID."""
        st = _state(ctx)
        try:
            data = await st.client.get_by_id("QueueItems", item_id, folder_id=folder_id)
            return json.dumps(QueueItem.model_validate(data).model_dump(), default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def update_queue_item_status(
        ctx: Context,
        item_id: Annotated[int, Field(description="Queue item ID")],
        review_status: Annotated[
            str,
            Field(description="New review status: None | Approved | Rejected | InReview | OnHold"),
        ],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        review_comments: Annotated[str | None, Field(description="Optional review comment")] = None,
    ) -> str:
        """Update the review status of a queue item (for manual review workflows)."""
        st = _state(ctx)
        try:
            body: dict[str, Any] = {"ReviewStatus": review_status}
            if review_comments:
                body["ReviewerComments"] = review_comments
            await st.client.patch("QueueItems", item_id, body, folder_id=folder_id)
            return json.dumps({"message": f"Item {item_id} review status → {review_status}"})
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def delete_queue_item(
        ctx: Context,
        item_id: Annotated[int, Field(description="Queue item ID to delete")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Delete a specific queue item. Only New/Failed/Abandoned items can be deleted."""
        st = _state(ctx)
        try:
            await st.client.delete("QueueItems", item_id, folder_id=folder_id)
            return json.dumps({"message": f"Queue item {item_id} deleted"})
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_queue_stats(
        ctx: Context,
        queue_name: Annotated[str, Field(description="Queue name")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """
        Get processing statistics for a queue:
        counts by status, success rate, retry rate.
        """
        st = _state(ctx)
        try:
            q_data = await st.client.get(
                "QueueDefinitions",
                params=ODataParams().filter(f"Name eq '{queue_name}'").top(1).build(),
                folder_id=folder_id,
            )
            q_items = q_data.get("value", [])
            if not q_items:
                return json.dumps({"error": f"Queue '{queue_name}' not found"})
            queue_id = q_items[0]["Id"]
            params = (
                ODataParams()
                .filter(f"QueueDefinitionId eq {queue_id}")
                .top(5000)
                .select("Status", "RetryNumber", "StartTime", "EndTime")
            )
            data = await st.client.get("QueueItems", params=params.build(), folder_id=folder_id)
            items_raw = data.get("value", [])

            counts: dict[str, int] = {}
            for item in items_raw:
                s = item.get("Status", "Unknown")
                counts[s] = counts.get(s, 0) + 1

            total = len(items_raw)
            successful = counts.get("Successful", 0)
            failed = counts.get("Failed", 0)
            return json.dumps(
                {
                    "queue_name": queue_name,
                    "total_items": total,
                    "counts_by_status": counts,
                    "success_rate_pct": round(successful / total * 100, 1) if total else 0.0,
                    "failure_rate_pct": round(failed / total * 100, 1) if total else 0.0,
                },
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def retry_failed_items(
        ctx: Context,
        queue_name: Annotated[str, Field(description="Queue name")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        max_items: Annotated[
            int, Field(description="Maximum items to retry", ge=1, le=1000)
        ] = 100,
    ) -> str:
        """
        Bulk-retry all Failed items in a queue.
        Sets their status back to New so they can be processed again.
        """
        st = _state(ctx)
        try:
            # Look up queue definition ID
            q_data = await st.client.get(
                "QueueDefinitions",
                params=ODataParams().filter(f"Name eq '{queue_name}'").top(1).build(),
                folder_id=folder_id,
            )
            q_items = q_data.get("value", [])
            if not q_items:
                return json.dumps({"error": f"Queue '{queue_name}' not found"})
            queue_id = q_items[0]["Id"]
            # Fetch failed item IDs
            params = (
                ODataParams()
                .filter(f"QueueDefinitionId eq {queue_id} and Status eq 'Failed'")
                .top(max_items)
                .select("Id")
            )
            data = await st.client.get("QueueItems", params=params.build(), folder_id=folder_id)
            item_ids = [i["Id"] for i in data.get("value", [])]

            if not item_ids:
                return json.dumps({"message": "No failed items found", "retried": 0})

            body = {"queueItemIds": item_ids}
            await st.client.post(
                "QueueItems", body=body, action="SetItemReviewStatus", folder_id=folder_id
            )
            return json.dumps(
                {"message": f"Retried {len(item_ids)} failed items in '{queue_name}'",
                 "retried": len(item_ids)},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())
