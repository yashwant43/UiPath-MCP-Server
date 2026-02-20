"""
Authentication manager for UiPath Orchestrator.

Three strategies:
  CloudAuthStrategy  — OAuth2 client_credentials via Automation Cloud identity server
  OnPremAuthStrategy — Username/password via /api/Account/Authenticate
  PATAuthStrategy    — Personal Access Token (no refresh)

Token caching:
  A module-level TokenCache + asyncio.Lock prevents thundering-herd token refreshes.
  Double-checked locking ensures only ONE coroutine ever refreshes at a time.
  Token is proactively refreshed 60 s before actual expiry.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from loguru import logger

from .config import AuthMode, Settings


# ── Errors ────────────────────────────────────────────────────────────────────

class UiPathAuthError(Exception):
    """Authentication failure with actionable context."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        detail: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


# ── Token Cache ───────────────────────────────────────────────────────────────

@dataclass
class TokenCache:
    """Thread/coroutine-safe token cache (one per auth strategy instance)."""

    access_token: str = ""
    expires_at: float = 0.0       # monotonic timestamp
    refresh_buffer: float = 60.0  # proactive refresh 60 s before expiry
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def is_valid(self) -> bool:
        return bool(self.access_token) and time.monotonic() < (
            self.expires_at - self.refresh_buffer
        )

    def set(self, token: str, expires_in: int) -> None:
        self.access_token = token
        self.expires_at = time.monotonic() + expires_in

    def clear(self) -> None:
        self.access_token = ""
        self.expires_at = 0.0


# Module-level cache — survives across all tool calls within one server process
_token_cache = TokenCache()


# ── Base strategy ─────────────────────────────────────────────────────────────

class AuthStrategy(ABC):
    """Abstract base for all auth strategies."""

    @abstractmethod
    async def get_token(self, client: httpx.AsyncClient) -> str:
        """Return a valid Bearer token, refreshing if needed."""

    @abstractmethod
    def get_base_headers(self) -> dict[str, str]:
        """Return non-secret headers always sent with every request."""


# ── Cloud OAuth2 ──────────────────────────────────────────────────────────────

class CloudAuthStrategy(AuthStrategy):
    """
    OAuth2 client_credentials flow for UiPath Automation Cloud.

    Token endpoint: https://cloud.uipath.com/{org}/identity_/connect/token
    Scope:          OR.Default  (covers all Orchestrator permissions)
    Lifetime:       3600 s
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache = _token_cache

    async def get_token(self, client: httpx.AsyncClient) -> str:
        # Fast path — no lock needed when token is valid
        if self._cache.is_valid:
            return self._cache.access_token

        # Slow path — acquire lock, re-check (another coroutine may have just refreshed)
        async with self._cache._lock:
            if self._cache.is_valid:
                return self._cache.access_token

            logger.debug("Cloud token expired/missing — acquiring via client_credentials")
            try:
                response = await client.post(
                    self._settings.cloud_token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._settings.uipath_client_id,
                        "client_secret": self._settings.uipath_client_secret.get_secret_value(),  # type: ignore[union-attr]
                        "scope": "OR.Default",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                data = response.json()
                token: str = data["access_token"]
                expires_in = int(data.get("expires_in", 3600))
                self._cache.set(token, expires_in)
                logger.info(f"Cloud OAuth2 token acquired (expires_in={expires_in}s)")
                return token

            except httpx.HTTPStatusError as exc:
                self._cache.clear()
                raise UiPathAuthError(
                    message="Failed to obtain cloud OAuth2 token — check UIPATH_CLIENT_ID/SECRET",
                    status_code=exc.response.status_code,
                    detail=exc.response.text[:500],
                ) from exc
            except httpx.RequestError as exc:
                self._cache.clear()
                raise UiPathAuthError(
                    message=f"Network error reaching token endpoint: {self._settings.cloud_token_url}",
                    detail=str(exc),
                ) from exc

    def get_base_headers(self) -> dict[str, str]:
        return {"X-UIPATH-TenantName": self._settings.uipath_tenant_name or ""}


# ── On-Premise ────────────────────────────────────────────────────────────────

class OnPremAuthStrategy(AuthStrategy):
    """
    Username/password authentication for on-premise Orchestrator.

    Endpoint:  {base_url}/api/Account/Authenticate
    Body:      {TenancyName, UsernameOrEmailAddress, Password}
    Token key: response["result"]  (NOT "access_token")
    Lifetime:  ~30 min (1800 s) — we cache for that long
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache = _token_cache

    async def get_token(self, client: httpx.AsyncClient) -> str:
        if self._cache.is_valid:
            return self._cache.access_token

        async with self._cache._lock:
            if self._cache.is_valid:
                return self._cache.access_token

            logger.debug("On-prem token expired/missing — authenticating")
            try:
                response = await client.post(
                    self._settings.onprem_auth_url,
                    json={
                        "TenancyName": self._settings.uipath_tenant_name,
                        "UsernameOrEmailAddress": self._settings.uipath_username,
                        "Password": self._settings.uipath_password.get_secret_value(),  # type: ignore[union-attr]
                    },
                )
                response.raise_for_status()
                data = response.json()

                if not data.get("success", False):
                    raise UiPathAuthError(
                        message="On-prem authentication failed",
                        detail=str(data.get("error", "Unknown error from Orchestrator")),
                    )

                token: str = data["result"]
                self._cache.set(token, expires_in=1800)
                logger.info("On-prem token acquired (expires_in=1800s)")
                return token

            except httpx.HTTPStatusError as exc:
                self._cache.clear()
                raise UiPathAuthError(
                    message="On-prem authentication HTTP error",
                    status_code=exc.response.status_code,
                    detail=exc.response.text[:500],
                ) from exc

    def get_base_headers(self) -> dict[str, str]:
        return {"X-UIPATH-TenantName": self._settings.uipath_tenant_name or ""}


# ── PAT ───────────────────────────────────────────────────────────────────────

class PATAuthStrategy(AuthStrategy):
    """
    Personal Access Token — no refresh needed; token IS the credential.
    The token is valid until the user revokes it in Automation Cloud settings.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_token(self, client: httpx.AsyncClient) -> str:  # noqa: ARG002
        return self._settings.uipath_pat.get_secret_value()  # type: ignore[union-attr]

    def get_base_headers(self) -> dict[str, str]:
        return {"X-UIPATH-TenantName": self._settings.uipath_tenant_name or ""}


# ── Factory ───────────────────────────────────────────────────────────────────

def create_auth_strategy(settings: Settings) -> AuthStrategy:
    """Return the correct AuthStrategy for the configured auth mode."""
    mapping: dict[AuthMode, type[AuthStrategy]] = {
        AuthMode.CLOUD: CloudAuthStrategy,
        AuthMode.ON_PREM: OnPremAuthStrategy,
        AuthMode.PAT: PATAuthStrategy,
    }
    return mapping[settings.auth_mode](settings)
