"""Skill resource orchestration for external registries such as Vett."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from models.requests import SkillCreateReq
from services.skill_import_service import (
    PROJECT_ROOT,
    copy_skill_dir,
    import_skill_from_dir,
    pick_extracted_skill_dir,
)
from services.vett_registry_service import VettRegistryService
from stores.factory import system_config_store


class SkillResourceService:
    def __init__(self) -> None:
        self._vett = VettRegistryService()

    def _client(self, source: str) -> VettRegistryService:
        normalized = str(source or "").strip().lower()
        if normalized != "vett":
            raise HTTPException(400, f"Unsupported skill resource source: {source}")
        return self._vett

    @staticmethod
    def _risk_policy() -> dict[str, list[str]]:
        cfg = system_config_store.get_global()
        sources = getattr(cfg, "skill_registry_sources", {}) or {}
        vett = sources.get("vett") if isinstance(sources, dict) else {}
        policy = vett.get("risk_policy") if isinstance(vett, dict) else {}
        normalized: dict[str, list[str]] = {}
        for key in ("allow", "review", "deny"):
            values = policy.get(key) if isinstance(policy, dict) else []
            normalized[key] = [
                str(item or "").strip().lower()
                for item in (values if isinstance(values, list) else [])
                if str(item or "").strip()
            ]
        return normalized

    def _policy_action(self, risk: str, scan_status: str) -> str:
        if str(scan_status or "").strip().lower() != "completed":
            return "blocked"
        policy = self._risk_policy()
        normalized_risk = str(risk or "").strip().lower()
        if normalized_risk in set(policy.get("deny") or []):
            return "deny"
        if normalized_risk in set(policy.get("review") or []):
            return "review"
        return "allow"

    def _map_latest_version(self, payload: Any) -> dict[str, Any]:
        version = payload if isinstance(payload, dict) else {}
        risk = str(version.get("risk") or "").strip()
        scan_status = str(version.get("scanStatus") or version.get("scan_status") or "").strip()
        return {
            "version": str(version.get("version") or "").strip(),
            "risk": risk,
            "scan_status": scan_status,
            "policy_action": self._policy_action(risk, scan_status),
        }

    def _map_search_item(self, payload: Any) -> dict[str, Any]:
        item = payload if isinstance(payload, dict) else {}
        return {
            "id": str(item.get("id") or "").strip(),
            "slug": str(item.get("slug") or "").strip(),
            "owner": str(item.get("owner") or "").strip(),
            "repo": str(item.get("repo") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "install_count": int(item.get("installCount") or 0),
            "source_url": str(item.get("sourceUrl") or "").strip(),
            "created_at": str(item.get("createdAt") or "").strip(),
            "latest_version": self._map_latest_version(item.get("latestVersion") or {}),
        }

    def _map_version(self, payload: Any) -> dict[str, Any]:
        version = payload if isinstance(payload, dict) else {}
        risk = str(version.get("risk") or "").strip()
        scan_status = str(version.get("scanStatus") or version.get("scan_status") or "").strip()
        return {
            "version": str(version.get("version") or "").strip(),
            "hash": str(version.get("hash") or "").strip(),
            "artifact_url": str(version.get("artifactUrl") or "").strip(),
            "size": int(version.get("size") or 0),
            "risk": risk,
            "summary": str(version.get("summary") or "").strip(),
            "scan_status": scan_status,
            "git_ref": str(version.get("gitRef") or "").strip(),
            "commit_sha": str(version.get("commitSha") or "").strip(),
            "source_url": str(version.get("sourceUrl") or "").strip(),
            "rekor_log_index": str(version.get("rekorLogIndex") or "").strip(),
            "sigstore_bundle": version.get("sigstoreBundle") if isinstance(version.get("sigstoreBundle"), dict) else {},
            "created_at": str(version.get("createdAt") or "").strip(),
            "policy_action": self._policy_action(risk, scan_status),
        }

    def _map_detail(self, payload: Any) -> dict[str, Any]:
        item = payload if isinstance(payload, dict) else {}
        return {
            "source": "vett",
            "skill": {
                "id": str(item.get("id") or "").strip(),
                "slug": str(item.get("slug") or "").strip(),
                "owner": str(item.get("owner") or "").strip(),
                "repo": str(item.get("repo") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "source_url": str(item.get("sourceUrl") or "").strip(),
                "install_count": int(item.get("installCount") or 0),
                "created_at": str(item.get("createdAt") or "").strip(),
            },
            "versions": [
                self._map_version(version)
                for version in (item.get("versions") or [])
                if isinstance(version, dict)
            ],
        }

    @staticmethod
    def _bundle_digest_hex(sigstore_bundle: dict[str, Any]) -> str:
        if not isinstance(sigstore_bundle, dict):
            return ""
        digest_payload = (
            sigstore_bundle.get("messageSignature")
            if isinstance(sigstore_bundle.get("messageSignature"), dict)
            else {}
        )
        message_digest = (
            digest_payload.get("messageDigest")
            if isinstance(digest_payload.get("messageDigest"), dict)
            else {}
        )
        algorithm = str(message_digest.get("algorithm") or "").strip().upper()
        digest = str(message_digest.get("digest") or "").strip()
        if algorithm and algorithm != "SHA2_256":
            return ""
        if not digest:
            return ""
        try:
            return base64.b64decode(digest, validate=True).hex().lower()
        except Exception:
            return ""

    @classmethod
    def _verify_artifact(cls, content: bytes, version: dict[str, Any]) -> None:
        actual = hashlib.sha256(content).hexdigest().lower()
        bundle_digest = cls._bundle_digest_hex(version.get("sigstore_bundle") or {})
        expected_hash = str(version.get("hash") or "").strip().lower()
        if bundle_digest:
            if actual != bundle_digest:
                raise HTTPException(502, "Skill artifact verification failed")
            return
        if expected_hash and actual == expected_hash:
            return
        raise HTTPException(502, "Skill artifact verification failed")

    def _check_install_policy(self, version: dict[str, Any]) -> None:
        scan_status = str(version.get("scan_status") or "").strip().lower()
        risk = str(version.get("risk") or "").strip().lower()
        if scan_status != "completed":
            raise HTTPException(400, "Skill version has not completed registry scanning")
        if risk in set(self._risk_policy().get("deny") or []):
            raise HTTPException(400, "Skill version is blocked by policy")
        if not isinstance(version.get("sigstore_bundle"), dict) or not version.get("sigstore_bundle"):
            raise HTTPException(400, "Skill version is missing sigstore bundle metadata")

    @staticmethod
    def _local_export_dir_name(slug: str, source_dir: Path, imported_skill_id: str = "") -> str:
        candidate = str(imported_skill_id or "").strip()
        if candidate:
            return candidate
        slug_name = Path(str(slug or "").strip("/")).name
        if slug_name:
            return slug_name
        return source_dir.name

    @staticmethod
    def _resolve_install_dir(install_dir: str) -> Path | None:
        raw = str(install_dir or "").strip()
        if not raw:
            return None
        path = Path(raw).expanduser()
        path = (PROJECT_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise HTTPException(400, f"Skill install directory is not a folder: {path}")
        return path

    @staticmethod
    def _export_skill_dir(source_dir: Path, install_dir: Path, dir_name: str) -> Path:
        target_dir = install_dir / str(dir_name or source_dir.name).strip()
        return copy_skill_dir(source_dir, target_dir)

    @staticmethod
    def _extract_json_artifact(content: bytes, extract_dir: Path) -> Path | None:
        try:
            payload = json.loads(content.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
            return None

        extracted_any = False
        for item in payload.get("files") or []:
            if not isinstance(item, dict):
                continue
            rel = Path(str(item.get("path") or "").strip())
            if not rel.parts:
                continue
            if rel.is_absolute() or ".." in rel.parts:
                raise HTTPException(400, "Skill artifact contains unsafe path entries")
            target = extract_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if "contentBase64" in item and str(item.get("contentBase64") or "").strip():
                try:
                    data = base64.b64decode(str(item.get("contentBase64") or ""), validate=True)
                except Exception as exc:
                    raise HTTPException(400, "Skill artifact contains invalid base64 file content") from exc
            else:
                data = str(item.get("content") or "").encode("utf-8")
            target.write_bytes(data)
            extracted_any = True

        if not extracted_any:
            raise HTTPException(400, "Skill artifact JSON does not contain files")
        return pick_extracted_skill_dir(extract_dir)

    @classmethod
    def _extract_archive(cls, archive_path: Path, extract_dir: Path) -> Path:
        json_skill_dir = cls._extract_json_artifact(archive_path.read_bytes(), extract_dir)
        if json_skill_dir is not None:
            return json_skill_dir

        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as zf:
                for info in zf.infolist():
                    rel = Path(info.filename)
                    if rel.is_absolute() or ".." in rel.parts:
                        raise HTTPException(400, "Skill archive contains unsafe path entries")
                zf.extractall(extract_dir)
            return pick_extracted_skill_dir(extract_dir)

        if tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path) as tf:
                for member in tf.getmembers():
                    rel = Path(member.name)
                    if rel.is_absolute() or ".." in rel.parts:
                        raise HTTPException(400, "Skill archive contains unsafe path entries")
                tf.extractall(extract_dir)
            return pick_extracted_skill_dir(extract_dir)

        raise HTTPException(400, "Unsupported skill archive format")

    async def search(
        self,
        *,
        source: str,
        q: str = "",
        risk: str = "",
        sort_by: str = "installs",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._client(source)
        payload = await client.search_skills(
            q=q,
            risk=risk,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )
        return {
            "source": "vett",
            "items": [
                self._map_search_item(item)
                for item in (payload.get("skills") or [])
                if isinstance(item, dict)
            ],
            "pagination": payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {},
        }

    async def get_detail(self, *, source: str, slug: str) -> dict[str, Any]:
        payload = await self._client(source).get_skill_detail(slug)
        return self._map_detail(payload)

    async def resolve(self, *, source: str, input_value: str) -> dict[str, Any]:
        payload = await self._client(source).resolve_skill(input_value)
        status = str(payload.get("status") or "").strip()
        response: dict[str, Any] = {"source": "vett", "status": status}
        if status == "ready" and isinstance(payload.get("skill"), dict):
            skill = payload["skill"]
            response["skill"] = {
                "id": str(skill.get("id") or "").strip(),
                "slug": str(skill.get("slug") or "").strip(),
                "name": str(skill.get("name") or "").strip(),
            }
        if status == "processing":
            response["job_id"] = str(payload.get("jobId") or "").strip()
            response["slug"] = str(payload.get("slug") or "").strip()
        if status == "not_found":
            response["message"] = str(payload.get("message") or "").strip()
        return response

    async def get_job(self, *, source: str, job_id: str) -> dict[str, Any]:
        payload = await self._client(source).get_job_status(job_id)
        result = payload.get("result") if isinstance(payload.get("result"), dict) else None
        normalized: dict[str, Any] = {
            "id": str(payload.get("id") or "").strip(),
            "status": str(payload.get("status") or "").strip(),
            "error": payload.get("error"),
            "result": None,
            "created_at": str(payload.get("createdAt") or "").strip(),
            "started_at": str(payload.get("startedAt") or "").strip(),
            "completed_at": str(payload.get("completedAt") or "").strip(),
        }
        if result is not None:
            normalized["result"] = {
                "skill": self._map_search_item(result.get("skill") or {})
                if isinstance(result.get("skill"), dict)
                else None,
                "version": {
                    "version": str((result.get("version") or {}).get("version") or "").strip(),
                    "hash": str((result.get("version") or {}).get("hash") or "").strip(),
                    "risk": str((result.get("version") or {}).get("risk") or "").strip(),
                }
                if isinstance(result.get("version"), dict)
                else None,
            }
        return normalized

    async def install(
        self,
        *,
        source: str,
        slug: str,
        version: str,
        install_dir: str = "",
        import_to_library: bool = True,
        auth_payload: dict | None = None,
    ) -> dict[str, Any]:
        detail = await self.get_detail(source=source, slug=slug)
        skill = detail.get("skill") if isinstance(detail.get("skill"), dict) else {}
        versions = detail.get("versions") if isinstance(detail.get("versions"), list) else []
        target = next(
            (
                item
                for item in versions
                if isinstance(item, dict) and str(item.get("version") or "").strip() == str(version or "").strip()
            ),
            None,
        )
        if target is None:
            raise HTTPException(404, f"Version {version} not found for {slug}")

        self._check_install_policy(target)
        client = self._client(source)
        resolved_install_dir = self._resolve_install_dir(install_dir)
        if not import_to_library and resolved_install_dir is None:
            raise HTTPException(400, "请先选择本地技能目录")
        download_url = await client.get_download_url(str(skill.get("id") or ""), str(target.get("version") or ""))
        content = await client.download_artifact(download_url)
        self._verify_artifact(content, target)
        exported_dir: Path | None = None
        result = None

        with tempfile.TemporaryDirectory(prefix="vett-skill-") as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "artifact.bin"
            extract_dir = root / "extracted"
            archive_path.write_bytes(content)
            extract_dir.mkdir(parents=True, exist_ok=True)
            source_dir = self._extract_archive(archive_path, extract_dir)
            if import_to_library:
                result = import_skill_from_dir(
                    SkillCreateReq(
                        source_dir=str(source_dir),
                        version=str(target.get("version") or ""),
                    ),
                    auth_payload,
                    dedupe_if_same_version=True,
                )
            if resolved_install_dir is not None:
                exported_dir = self._export_skill_dir(
                    source_dir,
                    resolved_install_dir,
                    self._local_export_dir_name(
                        str(skill.get("slug") or slug),
                        source_dir,
                        result.skill.id if result is not None else "",
                    ),
                )

        return {
            "status": (
                "already_installed"
                if result is not None and result.already_exists
                else "installed"
                if result is not None
                else "downloaded"
            ),
            "source": "vett",
            "slug": str(skill.get("slug") or slug).strip(),
            "version": str(target.get("version") or "").strip(),
            "install_dir": str(exported_dir or resolved_install_dir or "").strip(),
            "local_skill": (
                {
                    "id": result.skill.id,
                    "name": result.skill.name,
                    "version": result.skill.version,
                }
                if result is not None
                else None
            ),
        }
