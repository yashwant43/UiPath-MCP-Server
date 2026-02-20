"""
Asset management tools — 7 tools.

  list_assets  get_asset  create_asset  ⭐new  update_asset  ⭐new
  delete_asset  ⭐new  get_robot_asset  set_credential_asset  ⭐new
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError
from ..models import Asset, AssetValueType


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_assets(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        value_type: Annotated[
            str | None,
            Field(description="Filter by type: Text | Integer | Bool | Credential"),
        ] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> str:
        """List assets in a folder, optionally filtered by type."""
        st = _state(ctx)
        try:
            params = ODataParams().top(top).count()
            if value_type:
                params.filter(
                    f"ValueType eq UiPath.Server.Configuration.OData.AssetValueType'{value_type}'"
                )
            data = await st.client.get("Assets", params=params.build(), folder_id=folder_id)
            assets = [Asset.model_validate(a).model_dump() for a in data.get("value", [])]
            return json.dumps(
                {"total_count": data.get("@odata.count", len(assets)), "assets": assets},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_asset(
        ctx: Context,
        asset_id: Annotated[int | None, Field(description="Asset ID")] = None,
        asset_name: Annotated[str | None, Field(description="Asset name (exact)")] = None,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Get an asset by ID or exact name."""
        st = _state(ctx)
        try:
            if asset_id:
                data = await st.client.get_by_id("Assets", asset_id, folder_id=folder_id)
                return json.dumps(Asset.model_validate(data).model_dump(), default=str)
            if asset_name:
                params = ODataParams().filter(f"Name eq '{asset_name}'").top(1).build()
                data = await st.client.get("Assets", params=params, folder_id=folder_id)
                items = data.get("value", [])
                if not items:
                    return json.dumps({"error": f"Asset '{asset_name}' not found"})
                return json.dumps(Asset.model_validate(items[0]).model_dump(), default=str)
            return json.dumps({"error": "Provide asset_id or asset_name"})
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def create_asset(
        ctx: Context,
        name: Annotated[str, Field(description="Asset name")],
        value_type: Annotated[str, Field(description="Text | Integer | Bool | Credential")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        string_value: Annotated[str | None, Field(description="Value for Text type")] = None,
        integer_value: Annotated[int | None, Field(description="Value for Integer type")] = None,
        bool_value: Annotated[bool | None, Field(description="Value for Bool type")] = None,
        credential_username: Annotated[str | None, Field(description="Username for Credential type")] = None,
        credential_password: Annotated[str | None, Field(description="Password for Credential type")] = None,
        description: Annotated[str | None, Field(description="Asset description")] = None,
    ) -> str:
        """Create a new asset (Text, Integer, Bool, or Credential)."""
        st = _state(ctx)
        try:
            body: dict[str, Any] = {"Name": name, "ValueType": value_type}
            if description:
                body["Description"] = description
            if value_type == "Text" and string_value is not None:
                body["StringValue"] = string_value
            elif value_type == "Integer" and integer_value is not None:
                body["IntValue"] = integer_value
            elif value_type == "Bool" and bool_value is not None:
                body["BoolValue"] = bool_value
            elif value_type == "Credential":
                if credential_username:
                    body["CredentialUsername"] = credential_username
                if credential_password:
                    body["CredentialPassword"] = credential_password

            result = await st.client.post("Assets", body=body, folder_id=folder_id)
            return json.dumps(
                {"message": f"Asset '{name}' created", "asset": result}, default=str
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def update_asset(
        ctx: Context,
        asset_id: Annotated[int, Field(description="Asset ID to update")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        string_value: Annotated[str | None, Field(description="New value for Text asset")] = None,
        integer_value: Annotated[int | None, Field(description="New value for Integer asset")] = None,
        bool_value: Annotated[bool | None, Field(description="New value for Bool asset")] = None,
        description: Annotated[str | None, Field(description="New description")] = None,
    ) -> str:
        """Update an existing asset's value or description."""
        st = _state(ctx)
        try:
            body: dict[str, Any] = {}
            if string_value is not None:
                body["StringValue"] = string_value
            if integer_value is not None:
                body["IntValue"] = integer_value
            if bool_value is not None:
                body["BoolValue"] = bool_value
            if description is not None:
                body["Description"] = description
            if not body:
                return json.dumps({"error": "No update fields provided"})
            await st.client.patch("Assets", asset_id, body, folder_id=folder_id)
            return json.dumps({"message": f"Asset {asset_id} updated"})
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def delete_asset(
        ctx: Context,
        asset_id: Annotated[int, Field(description="Asset ID to delete")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Delete an asset by ID."""
        st = _state(ctx)
        try:
            await st.client.delete("Assets", asset_id, folder_id=folder_id)
            return json.dumps({"message": f"Asset {asset_id} deleted"})
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def get_robot_asset(
        ctx: Context,
        robot_name: Annotated[str, Field(description="Robot name")],
        asset_name: Annotated[str, Field(description="Asset name")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """
        Retrieve the value of an asset as seen by a specific robot.
        Useful for per-robot assets (ValueScope=PerRobot).
        """
        st = _state(ctx)
        try:
            params = ODataParams().filter(
                f"RobotName eq '{robot_name}' and Name eq '{asset_name}'"
            ).top(1).build()
            data = await st.client.get(
                "Assets/GetRobotAsset",
                params=params,
                folder_id=folder_id,
            )
            return json.dumps(data, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    @mcp.tool()
    async def set_credential_asset(
        ctx: Context,
        asset_id: Annotated[int, Field(description="Credential asset ID")],
        username: Annotated[str, Field(description="New username")],
        password: Annotated[str, Field(description="New password")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Update the username and password of a Credential-type asset."""
        st = _state(ctx)
        try:
            body = {"CredentialUsername": username, "CredentialPassword": password}
            await st.client.patch("Assets", asset_id, body, folder_id=folder_id)
            return json.dumps({"message": f"Credential asset {asset_id} updated"})
        except UiPathError as e:
            return json.dumps(e.to_dict())
