"""更新日志管理路由"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from core.deps import changelog_entry_store, ensure_permission, require_auth
from models.requests import ChangelogEntryCreateReq, ChangelogEntryUpdateReq
from stores.json.changelog_entry_store import ChangelogEntry


def _require_changelog_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.system.changelog")


router = APIRouter(prefix="/api/changelog-entries")
public_router = None


def _normalize_text(value: object, limit: int = 24000) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def _normalize_release_payload(data: dict[str, object], *, require_title: bool = False) -> dict[str, object]:
    payload = dict(data)
    payload["version"] = _normalize_text(payload.get("version"), 80)
    payload["title"] = _normalize_text(payload.get("title"), 160)
    payload["summary"] = _normalize_text(payload.get("summary"), 600)
    payload["content"] = _normalize_text(payload.get("content"), 24000)
    payload["release_date"] = _normalize_text(payload.get("release_date"), 32)
    payload["published"] = bool(payload.get("published", False))
    try:
        payload["sort_order"] = int(payload.get("sort_order", 100))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "sort_order must be an integer") from exc
    payload["sort_order"] = max(0, min(9999, int(payload["sort_order"])))
    if require_title and not payload["title"]:
        raise HTTPException(400, "title is required")
    return payload


@router.get("")
async def list_changelog_entries(_: None = Depends(_require_changelog_permission)):
    items = changelog_entry_store.list_all()
    return {"items": [asdict(item) for item in items]}


@router.get("/public")
async def list_public_changelog_entries():
    items = changelog_entry_store.list_public()
    return {"items": [asdict(item) for item in items]}


@router.get("/{entry_id}")
async def get_changelog_entry(entry_id: str, _: None = Depends(_require_changelog_permission)):
    item = changelog_entry_store.get(entry_id)
    if item is None:
        raise HTTPException(404, "Changelog entry not found")
    return {"item": asdict(item)}


@router.post("")
async def create_changelog_entry(
    req: ChangelogEntryCreateReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "button.changelog.create")
    payload = _normalize_release_payload(req.model_dump(), require_title=True)
    item = ChangelogEntry(
        id=changelog_entry_store.new_id(),
        version=str(payload["version"]),
        title=str(payload["title"]),
        summary=str(payload["summary"]),
        content=str(payload["content"]),
        release_date=str(payload["release_date"]),
        published=bool(payload["published"]),
        sort_order=int(payload["sort_order"]),
        created_by=str(auth_payload.get("sub") or "").strip(),
    )
    changelog_entry_store.save(item)
    return {"status": "created", "item": asdict(changelog_entry_store.get(item.id))}


@router.put("/{entry_id}")
async def update_changelog_entry(
    entry_id: str,
    req: ChangelogEntryUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "button.changelog.update")
    existing = changelog_entry_store.get(entry_id)
    if existing is None:
        raise HTTPException(404, "Changelog entry not found")
    updates = req.model_dump(exclude_none=True)
    payload = asdict(existing)
    payload.update(_normalize_release_payload(updates))
    if not str(payload.get("title") or "").strip():
        raise HTTPException(400, "title is required")
    changelog_entry_store.save(ChangelogEntry(**payload))
    return {"status": "updated", "item": asdict(changelog_entry_store.get(entry_id))}


@router.delete("/{entry_id}")
async def delete_changelog_entry(entry_id: str, auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "button.changelog.delete")
    if changelog_entry_store.get(entry_id) is None:
        raise HTTPException(404, "Changelog entry not found")
    if not changelog_entry_store.delete(entry_id):
        raise HTTPException(404, "Changelog entry not found")
    return {"status": "deleted", "entry_id": entry_id}
