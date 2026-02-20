"""
UiPath MCP Server Configuration.

Priority order (highest → lowest):
  1. Environment variables
  2. .env file
  3. Defaults defined here

Authentication modes are mutually exclusive — set AUTH_MODE and provide
the corresponding credentials:

  cloud    → UIPATH_CLIENT_ID + UIPATH_CLIENT_SECRET + UIPATH_ORG_NAME + UIPATH_TENANT_NAME
  on_prem  → UIPATH_BASE_URL + UIPATH_USERNAME + UIPATH_PASSWORD + UIPATH_TENANT_NAME
  pat      → UIPATH_BASE_URL + UIPATH_PAT + UIPATH_TENANT_NAME
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthMode(str, Enum):
    CLOUD = "cloud"
    ON_PREM = "on_prem"
    PAT = "pat"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    # ── Auth mode ────────────────────────────────────────────────────────────
    auth_mode: AuthMode = Field(
        default=AuthMode.CLOUD,
        description="Authentication strategy: cloud | on_prem | pat",
    )

    # ── Cloud OAuth2 ─────────────────────────────────────────────────────────
    uipath_client_id: str | None = Field(default=None)
    uipath_client_secret: SecretStr | None = Field(default=None)
    uipath_org_name: str | None = Field(default=None)
    uipath_tenant_name: str | None = Field(default=None)

    # ── On-Premise ───────────────────────────────────────────────────────────
    uipath_base_url: str | None = Field(default=None)
    uipath_username: str | None = Field(default=None)
    uipath_password: SecretStr | None = Field(default=None)

    # ── PAT ──────────────────────────────────────────────────────────────────
    uipath_pat: SecretStr | None = Field(default=None)

    # ── Folder context ───────────────────────────────────────────────────────
    uipath_folder_id: int | None = Field(default=None)
    uipath_folder_path: str | None = Field(default=None)

    # ── HTTP client ──────────────────────────────────────────────────────────
    http_timeout: float = Field(default=30.0, ge=1.0, le=300.0)
    http_max_connections: int = Field(default=20, ge=1, le=100)
    http_max_keepalive: int = Field(default=10, ge=1, le=50)

    # ── Retry ────────────────────────────────────────────────────────────────
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_min_wait: float = Field(default=1.0, ge=0.0)
    retry_max_wait: float = Field(default=30.0, ge=1.0)

    # ── Pagination ───────────────────────────────────────────────────────────
    default_page_size: int = Field(default=100, ge=1, le=1000)
    max_page_size: int = Field(default=1000, ge=1, le=10000)

    # ── MCP transport ────────────────────────────────────────────────────────
    mcp_transport: str = Field(default="stdio")
    mcp_host: str = Field(default="127.0.0.1")
    mcp_port: int = Field(default=8000, ge=1024, le=65535)

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: LogLevel = Field(default=LogLevel.INFO)
    log_json: bool = Field(default=False)

    # ── Computed properties ──────────────────────────────────────────────────

    @property
    def orchestrator_base_url(self) -> str:
        """Full base URL for the Orchestrator OData API."""
        if self.auth_mode == AuthMode.CLOUD:
            return (
                f"https://cloud.uipath.com/{self.uipath_org_name}"
                f"/{self.uipath_tenant_name}/orchestrator_"
            )
        base = (self.uipath_base_url or "").rstrip("/")
        return base

    @property
    def audit_api_url(self) -> str | None:
        """
        Base URL for the modern Audit REST API.

        Cloud: https://cloud.uipath.com/{org}/audit_/api  (deprecated OData AuditLogs
               endpoint was removed in Dec 2023; requires PM.Audit.Read scope)
        On-prem / PAT: None — caller should fall back to OData AuditLogs.
        """
        if self.auth_mode == AuthMode.CLOUD and self.uipath_org_name:
            return f"https://cloud.uipath.com/{self.uipath_org_name}/audit_/api"
        return None

    @property
    def cloud_token_url(self) -> str:
        return f"https://cloud.uipath.com/{self.uipath_org_name}/identity_/connect/token"

    @property
    def onprem_auth_url(self) -> str:
        return f"{self.orchestrator_base_url}/api/Account/Authenticate"

    # ── Validators ───────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_auth_requirements(self) -> "Settings":
        required: dict[AuthMode, list[str]] = {
            AuthMode.CLOUD: [
                "uipath_client_id",
                "uipath_client_secret",
                "uipath_org_name",
                "uipath_tenant_name",
            ],
            AuthMode.ON_PREM: [
                "uipath_base_url",
                "uipath_username",
                "uipath_password",
                "uipath_tenant_name",
            ],
            AuthMode.PAT: [
                "uipath_base_url",
                "uipath_pat",
                "uipath_tenant_name",
            ],
        }
        missing = [f for f in required[self.auth_mode] if getattr(self, f) is None]
        if missing:
            env_names = ", ".join(f.upper() for f in missing)
            raise ValueError(
                f"Auth mode '{self.auth_mode.value}' requires these env vars: {env_names}\n"
                f"Copy .env.example to .env and fill in the missing values."
            )
        return self


# Module-level singleton ──────────────────────────────────────────────────────

_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the validated Settings singleton (created on first call)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
