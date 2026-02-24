"""
Keyring integration for UiPath MCP Server.

Stores and retrieves UiPath credentials from the OS credential store
(Windows Credential Manager, macOS Keychain, or Linux Secret Service).

Service name: "uipath-mcp"
Username (key): the field name in lowercase (e.g., "uipath_client_id")
"""

from __future__ import annotations

from typing import Any

from loguru import logger

SERVICE_NAME = "uipath-mcp"

# All fields that can be stored/loaded via keyring.
KEYRING_FIELDS: tuple[str, ...] = (
    "auth_mode",
    "uipath_client_id",
    "uipath_client_secret",
    "uipath_org_name",
    "uipath_tenant_name",
    "uipath_base_url",
    "uipath_username",
    "uipath_password",
    "uipath_pat",
    "uipath_folder_id",
    "uipath_folder_path",
)


def _get_keyring():
    """Return the ``keyring`` module if a usable backend exists, else ``None``."""
    try:
        import keyring as kr

        backend = kr.get_keyring()
        backend_name = type(backend).__name__.lower()
        if "fail" in backend_name or "null" in backend_name:
            logger.debug(f"Keyring backend '{type(backend).__name__}' is not usable, skipping")
            return None
        return kr
    except Exception as exc:
        logger.debug(f"Keyring unavailable: {exc}")
        return None


def load_from_keyring() -> dict[str, Any]:
    """Load all stored credentials from the OS keyring.

    Returns a dict of ``{field_name: value}`` for fields that exist.
    Returns an empty dict if the keyring is unavailable or any read fails.
    """
    kr = _get_keyring()
    if kr is None:
        return {}

    values: dict[str, Any] = {}
    try:
        for field in KEYRING_FIELDS:
            value = kr.get_password(SERVICE_NAME, field)
            if value is not None:
                values[field] = value
    except Exception as exc:
        logger.warning(f"Failed to read from keyring: {exc}. Falling back to env vars.")
        return {}

    if values:
        logger.debug(f"Loaded {len(values)} credential(s) from keyring")
    return values


def store_credential(field: str, value: str) -> None:
    """Store a single credential in the OS keyring."""
    import keyring

    keyring.set_password(SERVICE_NAME, field, value)


def delete_credential(field: str) -> None:
    """Delete a single credential from the OS keyring (no-op if absent)."""
    import keyring
    import keyring.errors

    try:
        keyring.delete_password(SERVICE_NAME, field)
    except keyring.errors.PasswordDeleteError:
        pass


def clear_all() -> int:
    """Delete all UiPath credentials from the OS keyring. Returns count deleted."""
    import keyring
    import keyring.errors

    count = 0
    for field in KEYRING_FIELDS:
        try:
            keyring.delete_password(SERVICE_NAME, field)
            count += 1
        except keyring.errors.PasswordDeleteError:
            pass
    return count


def read_all() -> dict[str, str]:
    """Read all stored credentials (for display in ``auth test``)."""
    import keyring

    result: dict[str, str] = {}
    for field in KEYRING_FIELDS:
        value = keyring.get_password(SERVICE_NAME, field)
        if value is not None:
            result[field] = value
    return result
