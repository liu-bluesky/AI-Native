"""初始化与认证路由"""

from __future__ import annotations

import re
import base64
import hashlib
import hmac
import json
import secrets
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from core.auth import SECRET_KEY, create_token
from core.config import get_api_data_dir
from core.data_scope import visible_department_ids_for
from core.deps import (
    department_store,
    ensure_permission,
    is_super_admin_payload,
    require_auth,
    resolve_role_ids_permissions,
    role_store,
    system_config_store,
    user_store,
)
from stores.json.user_store import User, hash_password, verify_password
from models.requests import InitSetupReq, LoginReq, RegisterInvitationCreateReq, RegisterReq

router = APIRouter(prefix="/api")


_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_INVITE_TOKEN_TYPE = "register_invite"
_INVITE_TOKEN_VERSION = 1
_MAX_INVITE_EXPIRES_IN_HOURS = 24 * 30
_INVITE_CODE_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,32}")
_SUPER_ADMIN_USERNAME = "admin"


def _sanitize_username(username: str) -> str:
    value = str(username or "").strip()
    if not value:
        raise HTTPException(400, "Username is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}", value):
        raise HTTPException(400, "Invalid username format")
    return value


def _sanitize_email(email: str) -> str:
    value = str(email or "").strip()
    if not value:
        raise HTTPException(400, "Email is required")
    if not _EMAIL_PATTERN.fullmatch(value):
        raise HTTPException(400, "Invalid email format")
    return value


def _sanitize_user_identity(value: str) -> str:
    identity = str(value or "").strip()
    if "@" in identity:
        return _sanitize_email(identity)
    return _sanitize_username(identity)


def _sanitize_display_name(value: str, *, default: str = "") -> str:
    display_name = str(value or "").strip() or str(default or "").strip()
    if not display_name:
        raise HTTPException(400, "Display name is required")
    if len(display_name) > 64:
        raise HTTPException(400, "Display name must be <= 64 chars")
    return display_name


def _normalize_role_ids(role_ids: list[str] | tuple[str, ...] | set[str] | None, *, fallback_role: str = "user") -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in role_ids or []:
        role_id = str(item or "").strip().lower()
        if not role_id or role_id in seen:
            continue
        seen.add(role_id)
        normalized.append(role_id)
    if normalized:
        return normalized
    fallback = str(fallback_role or "user").strip().lower() or "user"
    return [fallback]


def _load_permissions(role_ids: list[str] | tuple[str, ...] | set[str] | None, username: str = "") -> list[str]:
    normalized_role_ids = _normalize_role_ids(role_ids)
    primary_role_id = normalized_role_ids[0]
    if is_super_admin_payload({"sub": username, "role": primary_role_id, "roles": normalized_role_ids}):
        return ["*"]
    return resolve_role_ids_permissions(normalized_role_ids)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    normalized = str(value or "").strip()
    if not normalized or not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
        raise ValueError("Invalid base64url value")
    padding = "=" * (-len(normalized) % 4)
    raw = base64.urlsafe_b64decode((normalized + padding).encode("ascii"))
    if _b64url_encode(raw) != normalized:
        raise ValueError("Non-canonical base64url value")
    return raw


def _invite_secret() -> bytes:
    return hashlib.sha256(f"{SECRET_KEY}:register-invite:v1".encode("utf-8")).digest()


def _xor_invite_payload(data: bytes, nonce: bytes) -> bytes:
    secret = _invite_secret()
    stream = bytearray()
    counter = 0
    while len(stream) < len(data):
        stream.extend(
            hmac.new(
                secret,
                nonce + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
        )
        counter += 1
    return bytes(left ^ right for left, right in zip(data, stream))


def _encode_register_invite(payload: dict) -> str:
    nonce = secrets.token_bytes(12)
    plain = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cipher = nonce + _xor_invite_payload(zlib.compress(plain), nonce)
    signature = hmac.new(_invite_secret(), cipher, hashlib.sha256).digest()[:16]
    return f"{_b64url_encode(cipher)}.{_b64url_encode(signature)}"


def _invite_dir() -> Path:
    path = get_api_data_dir() / "auth-invitations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _invite_path(code: str) -> Path:
    normalized_code = str(code or "").strip()
    if not _INVITE_CODE_PATTERN.fullmatch(normalized_code):
        raise HTTPException(400, "Invalid invite code")
    return _invite_dir() / f"{normalized_code}.json"


def _new_invite_code() -> str:
    for _ in range(20):
        code = secrets.token_urlsafe(9).rstrip("_-")
        if len(code) < 8:
            continue
        if not _invite_path(code).exists():
            return code
    raise HTTPException(500, "Failed to create invite code")


def _save_register_invite(code: str, token: str, expires_at: int, created_by: str) -> None:
    payload = {
        "code": code,
        "token": token,
        "expires_at": int(expires_at),
        "created_by": str(created_by or "").strip(),
        "created_at": _iso_from_timestamp(int(time.time())),
    }
    _invite_path(code).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_register_invite_token(value: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    if "." in raw_value:
        return raw_value
    path = _invite_path(raw_value)
    if not path.exists():
        raise HTTPException(400, "Invalid invite code")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(400, "Invalid invite code") from exc
    if int(data.get("expires_at") or 0) < int(time.time()):
        raise HTTPException(400, "Invite token expired")
    token = str(data.get("token") or "").strip()
    if not token:
        raise HTTPException(400, "Invalid invite code")
    return token


def _decode_register_invite(token: str) -> dict:
    raw_token = str(token or "").strip()
    if not raw_token:
        return {}
    try:
        cipher_part, signature_part = raw_token.split(".", 1)
        cipher = _b64url_decode(cipher_part)
        signature = _b64url_decode(signature_part)
    except Exception as exc:
        raise HTTPException(400, "Invalid invite token") from exc
    expected_signature = hmac.new(_invite_secret(), cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(400, "Invalid invite token")
    if len(cipher) <= 12:
        raise HTTPException(400, "Invalid invite token")
    nonce = cipher[:12]
    encrypted_payload = cipher[12:]
    try:
        plain = zlib.decompress(_xor_invite_payload(encrypted_payload, nonce))
        payload = json.loads(plain.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(400, "Invalid invite token") from exc
    if payload.get("typ") != _INVITE_TOKEN_TYPE or int(payload.get("v") or 0) != _INVITE_TOKEN_VERSION:
        raise HTTPException(400, "Invalid invite token")
    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(400, "Invite token expired")
    return payload


def _normalize_department_invite_payload(
    department_ids: list[str],
    *,
    primary_department_id: str = "",
    visible_department_ids: set[str] | None = None,
) -> tuple[list[str], str]:
    known_departments = {item.id: item for item in department_store.list_departments()}
    normalized_department_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in department_ids or []:
        department_id = str(raw_id or "").strip()
        if not department_id or department_id in seen:
            continue
        department = known_departments.get(department_id)
        if department is None:
            raise HTTPException(400, f"Department not found: {department_id}")
        if visible_department_ids is not None and department_id not in visible_department_ids:
            raise HTTPException(403, f"Department not visible: {department_id}")
        if not bool(getattr(department, "enabled", True)):
            raise HTTPException(400, f"Department disabled: {department_id}")
        seen.add(department_id)
        normalized_department_ids.append(department_id)
    primary_id = str(primary_department_id or "").strip()
    if primary_id and primary_id not in normalized_department_ids:
        primary_id = ""
    if not primary_id and normalized_department_ids:
        primary_id = normalized_department_ids[0]
    return normalized_department_ids, primary_id


def _decode_invite_departments(token: str) -> tuple[list[str], str]:
    payload = _decode_register_invite(_load_register_invite_token(token))
    return _normalize_department_invite_payload(
        [
            str(item or "").strip()
            for item in payload.get("department_ids", [])
            if str(item or "").strip()
        ],
        primary_department_id=str(payload.get("primary_department_id") or "").strip(),
    )


def _iso_from_timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


@router.get("/init/status")
async def init_status():
    cfg = system_config_store.get_global()
    initialized = user_store.has_any()
    return {
        "initialized": initialized,
        "setup_required": not initialized,
        "enable_user_register": bool(getattr(cfg, "enable_user_register", True)),
    }


@router.post("/init/setup")
async def init_setup(req: InitSetupReq):
    if user_store.has_any():
        raise HTTPException(400, "Already initialized")
    requested_username = _sanitize_username(req.username or _SUPER_ADMIN_USERNAME)
    if requested_username.lower() != _SUPER_ADMIN_USERNAME:
        raise HTTPException(400, "Initial super admin username must be admin")
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be >= 6 chars")
    display_name = _sanitize_display_name(req.display_name, default="超级管理员")
    user = User(
        username=_SUPER_ADMIN_USERNAME,
        password_hash=hash_password(req.password),
        display_name=display_name,
        role="admin",
        role_ids=["admin"],
        created_by="system",
    )
    user_store.save(user)
    return {"status": "ok", "username": user.username, "display_name": user.display_name}


@router.post("/auth/login")
async def login(req: LoginReq):
    username = _sanitize_user_identity(req.username)
    user = user_store.get(username)
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    role_ids = _normalize_role_ids(user.role_ids or [user.role], fallback_role=user.role)
    token = create_token(user.username, user.role, role_ids)
    permissions = _load_permissions(role_ids, user.username)
    return {
        "token": token,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "role_ids": role_ids,
        "permissions": permissions,
    }


@router.get("/auth/me")
async def auth_me(auth_payload: dict = Depends(require_auth)):
    username = _sanitize_user_identity(str(auth_payload.get("sub") or ""))
    user = user_store.get(username)
    if user is None:
        raise HTTPException(404, "User not found")
    role_ids = _normalize_role_ids(user.role_ids or [user.role], fallback_role=user.role)
    permissions = _load_permissions(role_ids, user.username)
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "role_ids": role_ids,
        "default_ai_provider_id": str(user.default_ai_provider_id or "").strip(),
        "permissions": permissions,
    }


@router.post("/auth/invitations")
async def create_register_invitation(
    req: RegisterInvitationCreateReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "button.users.create")
    department_ids, primary_department_id = _normalize_department_invite_payload(
        req.department_ids,
        primary_department_id=req.primary_department_id,
        visible_department_ids=visible_department_ids_for(auth_payload),
    )
    if department_ids:
        ensure_permission(auth_payload, "button.departments.assign_users")

    expires_in_hours = int(req.expires_in_hours or 168)
    expires_in_hours = max(1, min(expires_in_hours, _MAX_INVITE_EXPIRES_IN_HOURS))
    issued_at = int(time.time())
    expires_at = issued_at + expires_in_hours * 3600
    payload = {
        "v": _INVITE_TOKEN_VERSION,
        "typ": _INVITE_TOKEN_TYPE,
        "department_ids": department_ids,
        "primary_department_id": primary_department_id,
        "iat": issued_at,
        "exp": expires_at,
        "nonce": secrets.token_urlsafe(12),
        "created_by": str(auth_payload.get("sub") or "").strip(),
    }
    token = _encode_register_invite(payload)
    code = _new_invite_code()
    _save_register_invite(
        code,
        token,
        expires_at,
        str(auth_payload.get("sub") or "").strip(),
    )
    return {
        "code": code,
        "token": code,
        "register_path": f"/register?invite={code}",
        "expires_at": _iso_from_timestamp(expires_at),
        "department_ids": department_ids,
        "primary_department_id": primary_department_id,
    }


@router.post("/auth/register")
async def register(req: RegisterReq):
    if not user_store.has_any():
        raise HTTPException(400, "System not initialized")
    cfg = system_config_store.get_global()
    if not bool(getattr(cfg, "enable_user_register", True)):
        raise HTTPException(403, "User registration is disabled")
    invite_department_ids: list[str] = []
    invite_primary_department_id = ""
    if str(req.invite_token or "").strip():
        invite_department_ids, invite_primary_department_id = _decode_invite_departments(req.invite_token)
    username = _sanitize_email(req.email or req.username)
    if len(req.password or "") < 6:
        raise HTTPException(400, "Password must be >= 6 chars")
    if user_store.get(username) is not None:
        raise HTTPException(409, "Email already exists")
    role_item = role_store.get("user")
    if role_item is None:
        raise HTTPException(500, "Role user not initialized")
    user = User(username=username, password_hash=hash_password(req.password), role=role_item.id)
    user_store.save(user)
    if invite_department_ids:
        try:
            department_store.set_user_memberships(
                username,
                invite_department_ids,
                primary_department_id=invite_primary_department_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    return {
        "status": "ok",
        "username": user.username,
        "role": user.role,
        "department_ids": invite_department_ids,
        "primary_department_id": invite_primary_department_id,
    }
