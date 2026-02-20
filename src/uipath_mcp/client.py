"""
UiPath Orchestrator HTTP client.

Features:
  - httpx.AsyncClient with HTTP/2 and connection pooling (reused across tool calls)
  - tenacity retry with exponential back-off + jitter (no synchronized retry storms)
  - Automatic 429 Retry-After header handling
  - ODataParams fluent builder ($top, $skip, $filter, $select, $orderby, $expand, $count)
  - Folder header injection (X-UIPATH-OrganizationUnitId / X-UIPATH-FolderPath-Encoded)
  - Async pagination generator + collect-all helper
  - Structured UiPathError with status_code, error_code, detail, endpoint
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import httpx
from loguru import logger
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .auth import AuthStrategy, UiPathAuthError, _token_cache
from .config import Settings


# ── Errors ────────────────────────────────────────────────────────────────────

class UiPathError(Exception):
    """Structured error for UiPath Orchestrator API failures."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
        detail: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        self.endpoint = endpoint
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.message,
            "status_code": self.status_code,
            "error_code": self.error_code,
            "detail": self.detail,
            "endpoint": self.endpoint,
        }


# ── OData query builder ───────────────────────────────────────────────────────

class ODataParams:
    """
    Fluent builder for OData v4 query parameters.

    Example:
        params = ODataParams().top(100).skip(0).filter("State eq 'Running'").build()
        # {"$top": 100, "$skip": 0, "$filter": "State eq 'Running'"}
    """

    def __init__(self) -> None:
        self._params: dict[str, Any] = {}

    def top(self, n: int) -> "ODataParams":
        self._params["$top"] = n
        return self

    def skip(self, n: int) -> "ODataParams":
        self._params["$skip"] = n
        return self

    def filter(self, expr: str) -> "ODataParams":
        self._params["$filter"] = expr
        return self

    def select(self, *fields: str) -> "ODataParams":
        self._params["$select"] = ",".join(fields)
        return self

    def orderby(self, field_name: str, direction: str = "asc") -> "ODataParams":
        self._params["$orderby"] = f"{field_name} {direction}"
        return self

    def expand(self, *relations: str) -> "ODataParams":
        self._params["$expand"] = ",".join(relations)
        return self

    def count(self) -> "ODataParams":
        self._params["$count"] = "true"
        return self

    def build(self) -> dict[str, Any]:
        return dict(self._params)


# ── Retry helpers ─────────────────────────────────────────────────────────────

def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors that are safe to retry."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 502, 503, 504}
    return False


# ── HTTP client ───────────────────────────────────────────────────────────────

class UiPathClient:
    """
    Async HTTP client for UiPath Orchestrator.

    Use as an async context manager (typically inside FastMCP's lifespan):

        async with UiPathClient(settings, auth) as client:
            data = await client.get("Jobs")
    """

    def __init__(self, settings: Settings, auth: AuthStrategy) -> None:
        self._settings = settings
        self._auth = auth
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "UiPathClient":
        limits = httpx.Limits(
            max_connections=self._settings.http_max_connections,
            max_keepalive_connections=self._settings.http_max_keepalive,
        )
        self._client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(self._settings.http_timeout),
            limits=limits,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "uipath-mcp-server/1.0.0 (Python; httpx)",
            },
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _auth_headers(self) -> dict[str, str]:
        assert self._client is not None
        token = await self._auth.get_token(self._client)
        return {"Authorization": f"Bearer {token}", **self._auth.get_base_headers()}

    def _folder_headers(
        self,
        folder_id: int | None = None,
        folder_path: str | None = None,
    ) -> dict[str, str]:
        """Build folder-scoping headers, falling back to configured defaults."""
        eff_id = folder_id if folder_id is not None else self._settings.uipath_folder_id
        eff_path = folder_path or self._settings.uipath_folder_path
        if eff_id is not None:
            return {"X-UIPATH-OrganizationUnitId": str(eff_id)}
        if eff_path:
            return {"X-UIPATH-FolderPath-Encoded": quote(eff_path, safe="")}
        return {}

    def _odata_url(self, entity: str, action: str | None = None) -> str:
        base = f"{self._settings.orchestrator_base_url}/odata/{entity}"
        if action:
            base = f"{base}/UiPath.Server.Configuration.OData.{action}"
        return base

    def _api_url(self, path: str) -> str:
        """URL for non-OData /api/* endpoints."""
        return f"{self._settings.orchestrator_base_url}/{path.lstrip('/')}"

    def _raise_api_error(self, exc: httpx.HTTPStatusError, url: str) -> None:
        try:
            body = exc.response.json()
            message = body.get("message", body.get("Message", str(exc)))
            error_code = str(body.get("errorCode", body.get("ErrorCode", "")))
        except Exception:
            message = str(exc)
            error_code = None
        raise UiPathError(
            message=message,
            status_code=exc.response.status_code,
            error_code=error_code,
            detail=exc.response.text[:1000],
            endpoint=url,
        ) from exc

    async def _request(
        self,
        method: str,
        url: str,
        folder_id: int | None = None,
        folder_path: str | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request with retry logic."""
        assert self._client is not None

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._settings.retry_max_attempts),
                wait=wait_exponential_jitter(
                    initial=self._settings.retry_min_wait,
                    max=self._settings.retry_max_wait,
                    jitter=2.0,
                ),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            ):
                with attempt:
                    headers = {
                        **await self._auth_headers(),
                        **self._folder_headers(folder_id, folder_path),
                        **(extra_headers or {}),
                    }
                    attempt_num = attempt.retry_state.attempt_number
                    if attempt_num > 1:
                        logger.debug(f"Retry {attempt_num}/{self._settings.retry_max_attempts}: {method} {url}")
                    else:
                        logger.debug(f"{method} {url}")

                    response = await self._client.request(
                        method, url, headers=headers, **kwargs
                    )

                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After", "")
                        wait_sec = float(retry_after) if retry_after else self._settings.retry_min_wait
                        logger.warning(f"Rate limited (429) — waiting {wait_sec:.1f}s")
                        await asyncio.sleep(wait_sec)
                        response.raise_for_status()

                    if response.status_code == 401:
                        # Token may have been revoked — clear cache so next attempt re-authenticates
                        _token_cache.clear()
                        logger.warning("401 Unauthorized — cleared token cache, will re-authenticate")
                        response.raise_for_status()

                    if response.status_code == 404:
                        raise UiPathError(
                            message=f"Resource not found: {url}",
                            status_code=404,
                            error_code="NOT_FOUND",
                            endpoint=url,
                        )

                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        if not _is_retryable(exc):
                            self._raise_api_error(exc, url)
                        raise

                    return response

        except UiPathAuthError:
            raise
        except UiPathError:
            raise
        except RetryError as exc:
            raise UiPathError(
                message=f"All {self._settings.retry_max_attempts} retry attempts failed",
                endpoint=url,
            ) from exc

        # Should never reach here; for type-checker
        raise UiPathError(message="Unexpected retry loop exit", endpoint=url)

    # ── Public API methods ────────────────────────────────────────────────────

    async def get(
        self,
        entity: str,
        params: dict[str, Any] | None = None,
        folder_id: int | None = None,
        folder_path: str | None = None,
    ) -> dict[str, Any]:
        url = self._odata_url(entity)
        response = await self._request("GET", url, folder_id, folder_path, params=params)
        return response.json()

    async def get_by_id(
        self,
        entity: str,
        entity_id: int | str,
        params: dict[str, Any] | None = None,
        folder_id: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self._odata_url(entity)}({entity_id})"
        response = await self._request("GET", url, folder_id, params=params)
        return response.json()

    async def get_action(
        self,
        entity: str,
        action: str,
        params: dict[str, Any] | None = None,
        folder_id: int | None = None,
    ) -> dict[str, Any]:
        url = self._odata_url(entity, action)
        response = await self._request("GET", url, folder_id, params=params)
        return response.json()

    async def post(
        self,
        entity: str,
        body: dict[str, Any],
        action: str | None = None,
        folder_id: int | None = None,
    ) -> dict[str, Any]:
        url = self._odata_url(entity, action)
        response = await self._request("POST", url, folder_id, json=body)
        if response.status_code == 204:
            return {}
        return response.json()

    async def post_action(
        self,
        entity: str,
        entity_id: int | str,
        action: str,
        body: dict[str, Any] | None = None,
        folder_id: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self._odata_url(entity)}({entity_id})/UiPath.Server.Configuration.OData.{action}"
        response = await self._request("POST", url, folder_id, json=body or {})
        if response.status_code == 204:
            return {}
        return response.json()

    async def patch(
        self,
        entity: str,
        entity_id: int | str,
        body: dict[str, Any],
        folder_id: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self._odata_url(entity)}({entity_id})"
        response = await self._request("PATCH", url, folder_id, json=body)
        if response.status_code == 204:
            return {}
        return response.json()

    async def put(
        self,
        entity: str,
        entity_id: int | str,
        body: dict[str, Any],
        folder_id: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self._odata_url(entity)}({entity_id})"
        response = await self._request("PUT", url, folder_id, json=body)
        if response.status_code == 204:
            return {}
        return response.json()

    async def delete(
        self,
        entity: str,
        entity_id: int | str,
        folder_id: int | None = None,
    ) -> None:
        url = f"{self._odata_url(entity)}({entity_id})"
        await self._request("DELETE", url, folder_id)

    async def api_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a non-OData /api/* endpoint."""
        url = self._api_url(path)
        response = await self._request("GET", url, params=params)
        return response.json()

    # ── Pagination ────────────────────────────────────────────────────────────

    async def paginate(
        self,
        entity: str,
        params: dict[str, Any] | None = None,
        folder_id: int | None = None,
        folder_path: str | None = None,
        max_items: int | None = None,
        page_size: int = 100,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Async generator that yields pages of OData results.

        Stops when:
          - Server returns fewer items than page_size (last page)
          - max_items limit is reached
          - @odata.nextLink is absent

        Usage:
            async for page in client.paginate("Jobs", page_size=100):
                for job in page:
                    process(job)
        """
        base_params = dict(params or {})
        skip = 0
        collected = 0

        while True:
            page_params = {**base_params, "$top": page_size, "$skip": skip}
            data = await self.get(entity, params=page_params, folder_id=folder_id, folder_path=folder_path)
            items: list[dict[str, Any]] = data.get("value", [])

            if not items:
                break

            if max_items is not None:
                remaining = max_items - collected
                items = items[:remaining]

            yield items
            collected += len(items)
            skip += page_size

            if max_items is not None and collected >= max_items:
                break
            if len(items) < page_size:
                break
            if "@odata.nextLink" not in data and "$skip" not in str(data.get("@odata.context", "")):
                # If there's no nextLink and we got a full page, we'll try the next skip offset
                # (some UiPath endpoints don't return nextLink but do support skip-based paging)
                pass

    async def collect_all(
        self,
        entity: str,
        params: dict[str, Any] | None = None,
        folder_id: int | None = None,
        max_items: int = 10_000,
    ) -> list[dict[str, Any]]:
        """Collect all pages into a single list (capped at max_items)."""
        results: list[dict[str, Any]] = []
        async for page in self.paginate(entity, params, folder_id, max_items=max_items):
            results.extend(page)
        return results
