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
    "read_only_mode",
)

PROFILES_INDEX_SERVICE = f"{SERVICE_NAME}/__profiles__"
PROFILES_INDEX_KEY = "profiles"


def service_name_for_profile(profile: str) -> str:
    """Return the keyring service name for the given profile."""
    return f"{SERVICE_NAME}/{profile}"


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


def load_from_keyring(profile: str = "default") -> dict[str, Any]:
    """Load all stored credentials from the OS keyring.

    Returns a dict of ``{field_name: value}`` for fields that exist.
    Returns an empty dict if the keyring is unavailable or any read fails.
    """
    kr = _get_keyring()
    if kr is None:
        return {}

    svc = service_name_for_profile(profile)
    values: dict[str, Any] = {}
    try:
        for field in KEYRING_FIELDS:
            value = kr.get_password(svc, field)
            if value is not None:
                values[field] = value
    except Exception as exc:
        logger.warning(f"Failed to read from keyring: {exc}. Falling back to env vars.")
        return {}

    if values:
        logger.debug(f"Loaded {len(values)} credential(s) from keyring (profile={profile})")
    return values


def store_credential(field: str, value: str, profile: str = "default") -> None:
    """Store a single credential in the OS keyring."""
    import keyring

    keyring.set_password(service_name_for_profile(profile), field, value)


def delete_credential(field: str, profile: str = "default") -> None:
    """Delete a single credential from the OS keyring (no-op if absent)."""
    import keyring
    import keyring.errors

    try:
        keyring.delete_password(service_name_for_profile(profile), field)
    except keyring.errors.PasswordDeleteError:
        pass


def clear_all(profile: str = "default") -> int:
    """Delete all UiPath credentials from the OS keyring. Returns count deleted."""
    import keyring
    import keyring.errors

    svc = service_name_for_profile(profile)
    count = 0
    for field in KEYRING_FIELDS:
        try:
            keyring.delete_password(svc, field)
            count += 1
        except keyring.errors.PasswordDeleteError:
            pass
    return count


def read_all(profile: str = "default") -> dict[str, str]:
    """Read all stored credentials (for display in ``auth test``)."""
    import keyring

    svc = service_name_for_profile(profile)
    result: dict[str, str] = {}
    for field in KEYRING_FIELDS:
        value = keyring.get_password(svc, field)
        if value is not None:
            result[field] = value
    return result
