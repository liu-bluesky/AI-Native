"""Adapter for the public Vett skill registry API."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

from stores.factory import system_config_store

DEFAULT_VETT_BASE_URL = "https://vett.sh/api/v1"
DEFAULT_VETT_TIMEOUT_MS = 10000


def _normalize_base_url(value: Any) -> str:
    return str(value or DEFAULT_VETT_BASE_URL).strip().rstrip("/") or DEFAULT_VETT_BASE_URL


def _normalize_timeout_ms(value: Any) -> int:
    try:
        timeout_ms = int(value or DEFAULT_VETT_TIMEOUT_MS)
    except (TypeError, ValueError):
        timeout_ms = DEFAULT_VETT_TIMEOUT_MS
    return max(1000, min(60000, timeout_ms))


class VettRegistryService:
    def _config(self) -> dict[str, Any]:
        cfg = system_config_store.get_global()
        sources = getattr(cfg, "skill_registry_sources", {}) or {}
        raw = sources.get("vett") if isinstance(sources, dict) else {}
        return raw if isinstance(raw, dict) else {}

    def is_enabled(self) -> bool:
        return bool(self._config().get("enabled", True))

    def _base_url(self) -> str:
        return _normalize_base_url(self._config().get("base_url"))

    def _timeout(self) -> float:
        return _normalize_timeout_ms(self._config().get("timeout_ms")) / 1000.0

    def _ensure_enabled(self) -> None:
        if not self.is_enabled():
            raise HTTPException(400, "Vett registry source is disabled")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        self._ensure_enabled()
        url = f"{self._base_url()}{path if path.startswith('/') else f'/{path}'}"
        timeout = self._timeout()
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects) as client:
            try:
                response = await client.request(
                    method.upper(),
                    url,
                    params=params,
                    json=json_body,
                    headers={"Accept": "application/json"},
                )
            except httpx.RequestError as exc:
                raise HTTPException(502, f"Failed to reach Vett registry: {exc}") from exc
        if response.status_code >= 400:
            detail = ""
            try:
                payload = response.json()
                detail = str(payload.get("error") or payload.get("message") or "").strip()
            except Exception:
                detail = response.text.strip()
            message = detail or f"Vett registry request failed with status {response.status_code}"
            raise HTTPException(response.status_code, message)
        return response

    async def search_skills(
        self,
        *,
        q: str = "",
        risk: str = "",
        sort_by: str = "installs",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"sortBy": sort_by, "limit": max(1, min(250, int(limit))), "offset": max(0, int(offset))}
        if str(q or "").strip():
            params["q"] = str(q).strip()
        if str(risk or "").strip():
            params["risk"] = str(risk).strip()
        response = await self._request("GET", "/skills", params=params)
        payload = response.json() if response.content else {}
        return payload if isinstance(payload, dict) else {}

    async def get_skill_detail(self, slug: str) -> dict[str, Any]:
        normalized = str(slug or "").strip().strip("/")
        if not normalized:
            raise HTTPException(400, "slug is required")
        response = await self._request("GET", f"/skills/{normalized}")
        payload = response.json() if response.content else {}
        return payload if isinstance(payload, dict) else {}

    async def resolve_skill(self, input_value: str) -> dict[str, Any]:
        normalized = str(input_value or "").strip()
        if not normalized:
            raise HTTPException(400, "input is required")
        response = await self._request("POST", "/resolve", json_body={"input": normalized})
        payload = response.json() if response.content else {}
        return payload if isinstance(payload, dict) else {}

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        normalized = str(job_id or "").strip()
        if not normalized:
            raise HTTPException(400, "job_id is required")
        response = await self._request("GET", f"/jobs/{normalized}")
        payload = response.json() if response.content else {}
        return payload if isinstance(payload, dict) else {}

    async def get_download_url(self, skill_id: str, version: str) -> str:
        normalized_skill_id = str(skill_id or "").strip()
        normalized_version = str(version or "").strip()
        if not normalized_skill_id or not normalized_version:
            raise HTTPException(400, "skill_id and version are required")
        response = await self._request(
            "GET",
            f"/download/{normalized_skill_id}@{normalized_version}",
            follow_redirects=False,
        )
        location = str(response.headers.get("location") or "").strip()
        if response.status_code in {301, 302, 303, 307, 308} and location:
            return location
        if location:
            return location
        if response.url:
            return str(response.url)
        raise HTTPException(502, "Vett download endpoint did not return a signed URL")

    async def download_artifact(self, url: str) -> bytes:
        normalized = str(url or "").strip()
        if not normalized:
            raise HTTPException(400, "download url is required")
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            try:
                async with client.stream("GET", normalized) as response:
                    if response.status_code >= 400:
                        raise HTTPException(502, "Failed to download skill artifact")
                    chunks: list[bytes] = []
                    async for chunk in response.aiter_bytes():
                        chunks.append(chunk)
            except httpx.RequestError as exc:
                raise HTTPException(502, f"Failed to download skill artifact: {exc}") from exc
        return b"".join(chunks)
