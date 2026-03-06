"""项目管理路由"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import asyncio
from agent_loop import run_agent_loop

from ai_decision import ai_decide_action, execute_db_query, recommend_better_project
from auth import decode_token
from deps import employee_store, project_chat_store, project_store, require_auth, role_store, system_config_store
from feedback_service import get_feedback_service
from models.requests import ProjectChatReq, ProjectCreateReq, ProjectMemberAddReq, ProjectUpdateReq
from project_chat_store import ProjectChatMessage
from project_store import ProjectConfig, ProjectMember, _now_iso
from role_permissions import has_permission
from stores import skill_store

router = APIRouter(prefix="/api/projects", dependencies=[Depends(require_auth)])


def _serialize_project(project: ProjectConfig) -> dict:
    data = asdict(project)
    data["member_count"] = len(project_store.list_members(project.id))
    return data


def _sync_feedback_project_flag(project_id: str, enabled: bool) -> None:
    try:
        get_feedback_service().update_project_config(project_id, enabled=enabled)
    except Exception:
        # 反馈升级能力在非 PG/禁用场景可能不可用；项目主流程不阻断。
        return


def _project_member_details(project_id: str) -> list[dict]:
    items: list[dict] = []
    for member in project_store.list_members(project_id):
        employee = employee_store.get(member.employee_id)
        if employee is None:
            continue
        skill_items = []
        for skill_id in employee.skills or []:
            skill = skill_store.get(skill_id)
            skill_items.append(
                {
                    "id": skill_id,
                    "name": getattr(skill, "name", "") or skill_id,
                    "description": getattr(skill, "description", "") if skill else "",
                }
            )
        items.append(
            {
                "member": member,
                "employee": employee,
                "skills": skill_items,
                "rule_domains": list(employee.rule_domains or []),
            }
        )
    return items


def _assert_project_manual_generation_enabled() -> None:
    cfg = system_config_store.get_global()
    if not bool(getattr(cfg, "enable_project_manual_generation", False)):
        raise HTTPException(403, "Project manual generation is disabled by system config")


def _ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", [])
    if not has_permission(permissions, permission_key):
        raise HTTPException(403, f"Permission denied: {permission_key}")


def _serialize_chat_employee_profile(member: ProjectMember, employee: Any, skills: list[dict]) -> dict[str, Any]:
    skill_ids = [
        str(item.get("id") or "").strip()
        for item in (skills or [])
        if str(item.get("id") or "").strip()
    ]
    skill_names = [
        str(item.get("name") or item.get("id") or "").strip()
        for item in (skills or [])
        if str(item.get("name") or item.get("id") or "").strip()
    ]
    if not skill_ids:
        skill_ids = [str(item).strip() for item in (getattr(employee, "skills", []) or []) if str(item).strip()]
    if not skill_names:
        skill_names = skill_ids
    return {
        "id": str(getattr(employee, "id", "")),
        "name": str(getattr(employee, "name", "")),
        "description": str(getattr(employee, "description", "")),
        "role": str(getattr(member, "role", "member") or "member"),
        "enabled": bool(getattr(member, "enabled", True)),
        "skills": skill_ids,
        "skill_names": skill_names,
        "rule_domains": [str(item).strip() for item in (getattr(employee, "rule_domains", []) or []) if str(item).strip()],
        "tone": str(getattr(employee, "tone", "") or ""),
        "verbosity": str(getattr(employee, "verbosity", "") or ""),
        "language": str(getattr(employee, "language", "") or ""),
        "mcp_enabled": bool(getattr(employee, "mcp_enabled", False)),
        "feedback_upgrade_enabled": bool(getattr(employee, "feedback_upgrade_enabled", False)),
    }


def _project_chat_employee_candidates(project_id: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in _project_member_details(project_id):
        member = item["member"]
        employee = item["employee"]
        if not bool(getattr(member, "enabled", True)):
            continue
        candidates.append(_serialize_chat_employee_profile(member, employee, item.get("skills") or []))
    return candidates


def _resolve_project_chat_employee(project_id: str, expected_employee_id: str = "") -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    candidates = _project_chat_employee_candidates(project_id)
    if not candidates:
        return None, []
    expected = str(expected_employee_id or "").strip()
    if expected:
        matched = next((item for item in candidates if item["id"] == expected), None)
        if matched is None:
            raise ValueError(f"employee_id is not an enabled member of project {project_id}: {expected}")
        return matched, candidates
    role_priority = {"owner": 0, "lead": 1, "primary": 2, "admin": 3, "member": 9}
    ordered = sorted(
        candidates,
        key=lambda item: (
            int(role_priority.get(str(item.get("role") or "").strip().lower(), 8)),
            str(item.get("id") or ""),
        ),
    )
    return ordered[0], candidates


def _pick_chat_provider(provider_id: str) -> tuple[dict, list[dict]]:
    from llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)
    if not providers:
        raise HTTPException(400, "未配置可用的 LLM 提供商")
    expected = str(provider_id or "").strip()
    if expected:
        selected = next((item for item in providers if str(item.get("id") or "") == expected), None)
        if selected is None:
            raise HTTPException(404, f"LLM provider not found: {expected}")
        return selected, providers
    default_provider = next((item for item in providers if bool(item.get("is_default"))), providers[0])
    return default_provider, providers


def _normalize_chat_history(history: list[dict] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized[-20:]


def _normalize_image_inputs(images: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for item in images or []:
        value = str(item or "").strip()
        if not value:
            continue
        lower = value.lower()
        if re.match(r"^data:image/[a-z0-9.+-]+;base64,", lower):
            normalized.append(value)
            continue
        if lower.startswith("http://") or lower.startswith("https://"):
            normalized.append(value)
    return normalized


def _build_project_chat_messages(
    project: ProjectConfig,
    user_message: str,
    history: list[dict] | None,
    images: list[str] | None = None,
    selected_employee: dict[str, Any] | None = None,
    tools: list[dict] | None = None,
) -> list[dict[str, Any]]:
    workspace_info = ""
    if project.workspace_path:
        workspace_info = f"\n\n当前项目工作区路径: {project.workspace_path}\n请在此目录下进行代码开发和文件操作。"

    tool_names = [t.get("tool_name", "") for t in (tools or [])] if tools else []
    tool_list_text = f"可用工具({len(tool_names)}个): {', '.join(tool_names)}" if tool_names else "当前无可用工具"

    system_prompt = (
        f"你是项目开发助手。请使用简洁中文回复，并结合项目上下文给出可执行建议。{workspace_info}\n\n"
        f"**{tool_list_text}**\n\n"
        "**工具调用规则（强制执行）**：\n"
        "1. 用户要求查询数据时，**立即调用对应工具**，无需询问或说明意图\n"
        "2. 例如：\"返回成员信息\" → 直接调用 query_project_members\n"
        "3. 调用工具后，基于返回数据给出清晰摘要\n"
        "4. 若无合适工具，明确告知\"当前无可用工具完成此操作\"\n"
        "5. 工具执行失败时，说明原因并给下一步建议"
    )
    if selected_employee:
        system_prompt += (
            f"\n当前执行员工：{selected_employee.get('name') or selected_employee.get('id')} "
            f"({selected_employee.get('id')})，"
            f"skills={', '.join(selected_employee.get('skill_names') or []) or '-'}，"
            f"rule_domains={', '.join(selected_employee.get('rule_domains') or []) or '-'}。"
        )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "system",
            "content": (
                f"当前项目: id={project.id}, name={project.name}, description={project.description or '-'}"
            ),
        },
        *_normalize_chat_history(history),
    ]
    normalized_images = _normalize_image_inputs(images)
    if normalized_images:
        content = [{"type": "text", "text": user_message or "请基于图片给建议。"}]
        for img in normalized_images:
            content.append({"type": "image_url", "image_url": {"url": img}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})
    return messages


def _resolve_chat_max_tokens(request_max_tokens: int | None) -> int:
    cfg = system_config_store.get_global()
    configured = int(getattr(cfg, "chat_max_tokens", 512) or 512)
    configured = max(128, min(configured, 8192))
    if request_max_tokens is None:
        return configured
    try:
        request_value = int(request_max_tokens)
    except (TypeError, ValueError):
        return configured
    if request_value <= 0:
        return configured
    return max(128, min(request_value, 8192))


def _current_username(auth_payload: dict) -> str:
    username = str(auth_payload.get("sub") or "").strip()
    return username or "unknown"


def _append_chat_record(
    *,
    project_id: str,
    username: str,
    role: str,
    content: str,
    attachments: list[str] | None = None,
    images: list[str] | None = None,
) -> None:
    text = str(content or "").strip()
    if not text:
        return
    try:
        project_chat_store.append_message(
            ProjectChatMessage(
                project_id=project_id,
                username=username,
                role=role,
                content=text,
                attachments=attachments or [],
                images=images or [],
            )
        )
    except Exception:
        pass


def _extract_ws_auth_payload(websocket: WebSocket) -> dict | None:
    token = str(websocket.query_params.get("token") or "").strip()
    if token:
        payload = decode_token(token)
        if payload is not None:
            return payload
    auth_header = str(websocket.headers.get("authorization") or "").strip()
    if auth_header.startswith("Bearer "):
        return decode_token(auth_header[7:])
    return None


def _chunk_text(content: str, chunk_size: int = 42) -> list[str]:
    text = str(content or "")
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _sse_payload(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("")
async def list_projects():
    projects = project_store.list_all()
    return {"projects": [_serialize_project(item) for item in projects]}


@router.post("")
async def create_project(req: ProjectCreateReq):
    project = ProjectConfig(
        id=project_store.new_id(),
        name=str(req.name or "").strip(),
        description=req.description,
        workspace_path=str(req.workspace_path or "").strip(),
        mcp_enabled=req.mcp_enabled,
        feedback_upgrade_enabled=req.feedback_upgrade_enabled,
    )
    if not project.name:
        raise HTTPException(400, "name is required")
    project_store.save(project)
    _sync_feedback_project_flag(project.id, project.feedback_upgrade_enabled)
    return {"status": "created", "project": _serialize_project(project)}


@router.get("/{project_id}")
async def get_project(project_id: str):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    return {"project": _serialize_project(project)}


@router.post("/{project_id}/smart-query")
async def smart_query_project(project_id: str, request: dict):
    """AI 智能查询端点：自动决策调用数据库或工具"""
    from dynamic_mcp import list_project_proxy_tools_runtime
    from llm_provider_service import get_llm_provider_service
    from starlette.concurrency import run_in_threadpool
    import json

    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    user_message = request.get("message", "")
    if not user_message:
        raise HTTPException(400, "message is required")

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)
    if not providers:
        raise HTTPException(400, "No LLM provider configured")

    provider = providers[0]
    provider_id = provider.get("id", "")
    model_name = provider.get("default_model", "")

    tools = list_project_proxy_tools_runtime(project_id, "")
    decision = await ai_decide_action(llm_service, provider_id, model_name, user_message, project_id, tools)

    if not decision or decision.get("action") == "chat":
        return {"status": "no_action", "message": "请使用普通对话"}

    action = decision.get("action")

    if action == "query_db":
        result = await run_in_threadpool(execute_db_query, decision.get("query", ""))
        return {"status": "ok", "action": "query_db", "result": result, "reason": decision.get("reason")}

    if action == "call_tool":
        from dynamic_mcp import invoke_project_skill_tool_runtime
        tool_result = await run_in_threadpool(
            invoke_project_skill_tool_runtime, project_id, decision.get("tool", ""), "", decision.get("args", {}), "{}", 60
        )
        return {"status": "ok", "action": "call_tool", "result": tool_result, "reason": decision.get("reason")}

    if action == "recommend_project":
        recommendation = recommend_better_project(user_message, project_id)
        return {"status": "ok", "action": "recommend_project", "result": recommendation}

    return {"status": "unknown_action"}


def _apply_project_update(project_id: str, req: ProjectUpdateReq) -> dict:
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "project": _serialize_project(project)}
    if "name" in updates:
        updates["name"] = str(updates["name"] or "").strip()
        if not updates["name"]:
            raise HTTPException(400, "name cannot be empty")
    updates["updated_at"] = _now_iso()
    updated = replace(project, **updates)
    project_store.save(updated)
    if "feedback_upgrade_enabled" in updates:
        _sync_feedback_project_flag(updated.id, bool(updated.feedback_upgrade_enabled))
    return {"status": "updated", "project": _serialize_project(updated)}


@router.put("/{project_id}")
async def update_project(project_id: str, req: ProjectUpdateReq):
    return _apply_project_update(project_id, req)


@router.patch("/{project_id}")
async def patch_project(project_id: str, req: ProjectUpdateReq):
    return _apply_project_update(project_id, req)


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    if not project_store.delete(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    try:
        project_chat_store.clear_project(project_id)
    except Exception:
        pass
    return {"status": "deleted", "project_id": project_id}


@router.get("/{project_id}/members")
async def list_project_members(project_id: str):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    members = []
    for member in project_store.list_members(project_id):
        employee = employee_store.get(member.employee_id)
        members.append(
            {
                **asdict(member),
                "employee_exists": employee is not None,
                "employee_name": getattr(employee, "name", ""),
                "employee_mcp_enabled": bool(getattr(employee, "mcp_enabled", False)) if employee else False,
            }
        )
    return {"members": members}


@router.post("/{project_id}/members")
async def add_project_member(project_id: str, req: ProjectMemberAddReq):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    employee_id = str(req.employee_id or "").strip()
    if not employee_id:
        raise HTTPException(400, "employee_id is required")
    employee = employee_store.get(employee_id)
    if employee is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    existing = project_store.get_member(project_id, employee_id)
    if existing is not None:
        return {
            "status": "exists",
            "message": f"Employee {employee_id} already exists in project {project_id}",
            "member": asdict(existing),
        }
    member = ProjectMember(
        project_id=project_id,
        employee_id=employee_id,
        role=str(req.role or "member").strip() or "member",
        enabled=bool(req.enabled),
        joined_at=_now_iso(),
    )
    project_store.upsert_member(member)
    return {"status": "created", "member": asdict(member)}


@router.delete("/{project_id}/members/{employee_id}")
async def remove_project_member(project_id: str, employee_id: str):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    if not project_store.remove_member(project_id, employee_id):
        raise HTTPException(404, f"Employee {employee_id} is not a member of project {project_id}")
    return {"status": "deleted", "project_id": project_id, "employee_id": employee_id}


@router.get("/{project_id}/chat/providers")
async def list_project_chat_providers(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    selected_provider, providers = _pick_chat_provider("")
    default_employee, candidates = _resolve_project_chat_employee(project_id, "")
    return {
        "project_id": project_id,
        "providers": providers,
        "default_provider_id": str(selected_provider.get("id") or ""),
        "default_model_name": str(selected_provider.get("default_model") or ""),
        "employees": candidates,
        "default_employee_id": str((default_employee or {}).get("id") or ""),
    }


@router.get("/{project_id}/chat/history")
async def list_project_chat_history(
    project_id: str,
    limit: int = 200,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    username = _current_username(auth_payload)
    records = project_chat_store.list_messages(project_id, username, limit=limit)
    return {"messages": [asdict(item) for item in records]}


@router.delete("/{project_id}/chat/history")
async def clear_project_chat_history(
    project_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    username = _current_username(auth_payload)
    removed = project_chat_store.clear_messages(project_id, username)
    return {"status": "cleared", "removed_count": int(removed)}


@router.websocket("/{project_id}/chat/ws")
async def ws_project_chat(project_id: str, websocket: WebSocket):
    from llm_provider_service import get_llm_provider_service

    auth_payload = _extract_ws_auth_payload(websocket)
    if auth_payload is None:
        await websocket.close(code=4401, reason="Missing or invalid token")
        return
    try:
        _ensure_permission(auth_payload, "menu.ai.chat")
    except HTTPException:
        await websocket.close(code=4403, reason="Permission denied")
        return

    project = project_store.get(project_id)
    if project is None:
        await websocket.close(code=4404, reason=f"Project {project_id} not found")
        return

    await websocket.accept()
    username = _current_username(auth_payload)
    await websocket.send_json(
        {
            "type": "ready",
            "project_id": project_id,
            "message": "connected",
        }
    )
    llm_service = get_llm_provider_service()

    active_tasks: dict[str, asyncio.Task] = {}
    cancel_events: dict[str, asyncio.Event] = {}

    async def handle_request(payload: dict):
        nonlocal active_tasks, cancel_events
        request_id = str(payload.get("request_id") or "").strip()
        if str(payload.get("type") or "").strip().lower() == "ping":
            await websocket.send_json({"type": "pong", "request_id": request_id})
            return

        if str(payload.get("type") or "").strip().lower() == "cancel":
            if request_id in cancel_events:
                cancel_events[request_id].set()
            return

        try:
            req = ProjectChatReq.model_validate(payload)
        except Exception as exc:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": f"Invalid payload: {str(exc)}"})
            return

        user_message = str(req.message or "").strip()
        normalized_images = _normalize_image_inputs(req.images)
        attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
        if not user_message and not normalized_images and not attachment_names:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": "message is required"})
            return

        effective_user_message = user_message
        if not effective_user_message and attachment_names:
            effective_user_message = f"我上传了附件：{', '.join(attachment_names)}。请先给我处理建议。"
        elif not effective_user_message and normalized_images:
            effective_user_message = "请基于我上传的图片给建议。"
        record_content = user_message or ("（发送了图片）" if normalized_images else "（发送了附件）")
        _append_chat_record(
            project_id=project_id, username=username, role="user", content=record_content,
            attachments=attachment_names, images=normalized_images,
        )

        cancel_event = asyncio.Event()
        cancel_events[request_id] = cancel_event

        try:
            selected_provider, _ = _pick_chat_provider(req.provider_id)
            provider_id = str(selected_provider.get("id") or "")
            model_name = str(req.model_name or "").strip() or str(selected_provider.get("default_model") or "")
            if not model_name:
                raise ValueError("model_name is required")
            selected_employee, _ = _resolve_project_chat_employee(project_id, req.employee_id)
            max_tokens = _resolve_chat_max_tokens(req.max_tokens)
            temperature = float(req.temperature if req.temperature is not None else 0.2)
            temperature = max(0.0, min(temperature, 2.0))

            # Fetch tools
            from dynamic_mcp import list_project_proxy_tools_runtime
            employee_id_val = str((selected_employee or {}).get("id") or "")
            tools = list_project_proxy_tools_runtime(project_id, employee_id_val)

            messages = _build_project_chat_messages(
                project, effective_user_message, req.history, normalized_images,
                selected_employee=selected_employee, tools=tools,
            )
            
        except Exception as exc:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
            return

        await websocket.send_json({
            "type": "start", "request_id": request_id, "project_id": project_id,
            "provider_id": provider_id, "model_name": model_name,
            "employee_id": employee_id_val,
            "employee_name": str((selected_employee or {}).get("name") or ""),
        })

        try:
            final_answer = ""
            stream_error = ""
            async for chunk_data in run_agent_loop(
                llm_service=llm_service, provider_id=provider_id, model_name=model_name,
                messages=messages, tools=tools, temperature=temperature, max_tokens=max_tokens,
                project_id=project_id, employee_id=employee_id_val, cancel_event=cancel_event
            ):
                chunk_data["request_id"] = request_id
                await websocket.send_json(chunk_data)
                if chunk_data.get("type") == "done":
                    # Use clean content for history, display_content for frontend
                    final_answer = chunk_data.get("content", "")
                if chunk_data.get("type") == "error":
                    stream_error = str(chunk_data.get("message") or "未知错误")

            if stream_error:
                _append_chat_record(
                    project_id=project_id, username=username, role="assistant", content=f"对话失败：{stream_error}",
                )
            else:
                _append_chat_record(
                    project_id=project_id, username=username, role="assistant", content=final_answer or "模型未返回有效内容。",
                )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            _append_chat_record(
                project_id=project_id, username=username, role="assistant", content=f"对话失败：{str(exc)}",
            )
            await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
        finally:
            cancel_events.pop(request_id, None)
            active_tasks.pop(request_id, None)

    while True:
        try:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                await websocket.send_json({"type": "error", "message": "Invalid payload type"})
                continue
                
            request_id = str(payload.get("request_id") or "").strip()
            if payload.get("type") == "cancel":
                if request_id in cancel_events:
                    cancel_events[request_id].set()
                continue
                
            task = asyncio.create_task(handle_request(payload))
            if request_id:
                active_tasks[request_id] = task
                
        except WebSocketDisconnect:
            for ev in cancel_events.values():
                ev.set()
            for t in active_tasks.values():
                t.cancel()
            break
        except Exception:
            await websocket.send_json({"type": "error", "message": "Invalid JSON payload"})
            continue

@router.post("/{project_id}/chat/stream")
async def stream_project_chat(
    project_id: str,
    req: ProjectChatReq,
    auth_payload: dict = Depends(require_auth),
):
    from llm_provider_service import get_llm_provider_service

    _ensure_permission(auth_payload, "menu.ai.chat")
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    username = _current_username(auth_payload)

    user_message = str(req.message or "").strip()
    normalized_images = _normalize_image_inputs(req.images)
    attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
    if not user_message and not normalized_images and not attachment_names:
        raise HTTPException(400, "message is required")

    effective_user_message = user_message
    if not effective_user_message and attachment_names:
        effective_user_message = f"我上传了附件：{', '.join(attachment_names)}。请先给我处理建议。"
    elif not effective_user_message and normalized_images:
        effective_user_message = "请基于我上传的图片给建议。"
    record_content = user_message or ("（发送了图片）" if normalized_images else "（发送了附件）")
    _append_chat_record(
        project_id=project_id,
        username=username,
        role="user",
        content=record_content,
        attachments=attachment_names,
        images=normalized_images,
    )

    selected_provider, _ = _pick_chat_provider(req.provider_id)
    provider_id = str(selected_provider.get("id") or "")
    model_name = str(req.model_name or "").strip() or str(selected_provider.get("default_model") or "")
    if not model_name:
        raise HTTPException(400, "model_name is required")
    try:
        selected_employee, _ = _resolve_project_chat_employee(project_id, req.employee_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    max_tokens = _resolve_chat_max_tokens(req.max_tokens)
    temperature = float(req.temperature if req.temperature is not None else 0.2)
    temperature = max(0.0, min(temperature, 2.0))

    from dynamic_mcp import list_project_proxy_tools_runtime
    employee_id_val = str((selected_employee or {}).get("id") or "")
    tools = list_project_proxy_tools_runtime(project_id, employee_id_val)

    llm_service = get_llm_provider_service()
    messages = _build_project_chat_messages(
        project,
        effective_user_message,
        req.history,
        normalized_images,
        selected_employee=selected_employee,
        tools=tools,
    )

    async def event_stream() -> AsyncIterator[str]:
        yield _sse_payload(
            "message",
            {
                "type": "start",
                "project_id": project_id,
                "provider_id": provider_id,
                "model_name": model_name,
                "employee_id": str((selected_employee or {}).get("id") or ""),
                "employee_name": str((selected_employee or {}).get("name") or ""),
            },
        )
        try:
            result = await llm_service.chat_completion(
                provider_id=provider_id,
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=120,
            )
            answer = str(result.get("content") or "").strip() or "模型未返回有效内容。"
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload(
                "message",
                {
                    "type": "done",
                    "content": answer,
                    "provider_id": provider_id,
                    "model_name": model_name,
                },
            )
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=answer,
            )
        except Exception as exc:
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=f"对话失败：{str(exc)}",
            )
            yield _sse_payload("message", {"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{project_id}/generate-manual")
async def generate_project_manual(project_id: str):
    """生成项目使用手册（面向接入方 AI 平台）"""
    from llm_provider_service import get_llm_provider_service

    _assert_project_manual_generation_enabled()

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)
    if not providers:
        raise HTTPException(400, "未配置 LLM 提供商")
    default_provider = next((p for p in providers if p.get("is_default")), providers[0])

    template_payload = await get_project_manual_template(project_id)
    template = str(template_payload.get("template") or "").strip()
    if not template:
        raise HTTPException(500, "项目手册模板为空，无法生成使用手册")

    project_name = str(template_payload.get("project_name") or "")
    system_prompt = (
        "你是技术文档撰写专家。请严格根据用户提供的手册模板要求生成最终使用手册，"
        "输出标准 Markdown，不要解释过程。"
    )

    try:
        result = await llm_service.chat_completion(
            provider_id=default_provider["id"],
            model_name=default_provider.get("default_model") or "gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": template},
            ],
            temperature=0.2,
            max_tokens=2800,
            timeout=60,
        )
        manual = str(result.get("content") or "").strip()
        return {
            "status": "success",
            "manual": manual,
            "template": template,
            "provider": default_provider["name"],
            "model": default_provider.get("default_model") or "gpt-4",
            "project_id": project_id,
            "project_name": project_name,
        }
    except Exception as exc:
        raise HTTPException(500, f"生成项目使用手册失败: {str(exc)}") from exc


@router.get("/{project_id}/manual-template")
async def get_project_manual_template(project_id: str):
    """获取项目手册提示词模板（供用户复制到其他 AI 使用）"""
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    member_items = _project_member_details(project_id)
    member_lines = []
    all_domains: set[str] = set()
    unique_skills: dict[str, dict] = {}
    for item in member_items:
        employee = item["employee"]
        member = item["member"]
        domains = item["rule_domains"]
        skills = item["skills"]
        for domain in domains:
            all_domains.add(str(domain))
        for skill in skills:
            unique_skills[str(skill["id"])] = skill
        member_lines.append(
            f"- {employee.name} ({employee.id}) role={member.role} "
            f"skills={len(skills)} domains={len(domains)}"
        )

    members_text = "\n".join(member_lines) if member_lines else "无"
    skills_text = (
        "\n".join(f"- {s['name']}:{s.get('description', '')}" for s in unique_skills.values())
        if unique_skills
        else "无"
    )
    domains_text = "\n".join(f"- {d}" for d in sorted(all_domains)) if all_domains else "无"
    employee_template_lines: list[str] = []
    for item in member_items:
        employee = item["employee"]
        member = item["member"]
        skills = item["skills"]
        domains = item["rule_domains"]
        style_hints = list(getattr(employee, "style_hints", []) or [])
        employee_skills_text = (
            "\n".join(f"  - {s['name']}:{s.get('description', '')}" for s in skills)
            if skills
            else "  - 无"
        )
        employee_domains_text = (
            "\n".join(f"  - {d}" for d in domains)
            if domains
            else "  - 无"
        )
        style_text = (
            "\n".join(f"  - {text}" for text in style_hints)
            if style_hints
            else "  - 无"
        )
        employee_template_lines.append(
            f"""### {employee.name}（{employee.id}）
- 角色:{member.role}
- 语调:{getattr(employee, "tone", "-")} / 风格:{getattr(employee, "verbosity", "-")} / 语言:{getattr(employee, "language", "-")}
- 记忆:scope={getattr(employee, "memory_scope", "-")}，保留{getattr(employee, "memory_retention_days", "-")}天

技能:
{employee_skills_text}

规则领域:
{employee_domains_text}

风格提示:
{style_text}
"""
        )
    employee_templates_text = "\n".join(employee_template_lines) if employee_template_lines else "无成员"

    template = f"""请根据以下信息，为"{project.name}"AI 项目模块生成一份完整的使用手册。

## 项目基本信息

- **项目 ID**：`{project.id}`
- **项目名称**：{project.name}
- **项目定位**：{project.description or "AI 开发团队"}
- **反馈升级**：{"已启用" if project.feedback_upgrade_enabled else "未启用"}

## 项目成员

{employee_templates_text}

---

## 手册生成要求

**重要：自动记忆规则**

在生成的使用手册中，必须在开头添加以下强制规则：

> **每次对话流程（强制执行）：**
> 1. 收到用户提问后，先检索相关记忆（`recall_project_memory`）
> 2. 解决问题过程中的关键信息会自动保存到记忆系统
> 3. 问题解决后，系统会自动记录本次对话的要点
> 
> **记忆自动保存的内容包括：**
> - 用户提出的问题
> - 使用的解决方案
> - 调用的工具和参数
> - 遇到的问题和解决方法
> - 重要的技术决策
> 
> **注意：**
> - 记忆系统会自动工作，无需手动调用保存
> - 如果遇到重要问题或发现 Bug，可手动提交反馈工单（`submit_project_feedback_bug`）用于规则进化

请按以下结构生成完整的使用手册：

### 第一部分：项目总览

#### 1. 项目简介
- **定位**：{project.name}是什么项目？解决什么问题？
- **适用场景**：什么时候应该使用这个项目？
- **能力边界**：项目能做什么，不能做什么？

#### 2. 核心工具说明

逐个说明以下工具的用途、参数、返回值和使用场景：

- **`list_project_members`**：列出项目所有成员
- **`get_project_profile`**：获取项目配置信息
- **`get_project_runtime_context`**：获取项目运行时上下文
- **`recall_project_memory`**：检索项目记忆
- **`query_project_rules`**：查询项目规则
- **`list_project_proxy_tools`**：列出项目可用技能工具
- **`invoke_project_skill_tool`**：调用项目技能
- **`submit_project_feedback_bug`**：提交反馈问题

---

### 第二部分：项目成员能力清单

为每个成员详细说明：
- 职责定位
- 核心技能
- 规则领域
- 风格特点（如有）

---

### 第三部分：推荐工作流

#### 标准开发流程

```
1. 获取项目上下文 → get_project_runtime_context
2. 记忆检索 → recall_project_memory
3. 规则检索 → query_project_rules
4. 技能调用 → invoke_project_skill_tool
5. 反馈闭环 → submit_project_feedback_bug
```

#### 典型场景示例

**场景 1：新增数据库表**
1. 获取上下文
2. 检索记忆（"数据库表设计"）
3. 检索规则（"数据库设计"）
4. 查看现有表结构（db-query）
5. 提交反馈

**场景 2：开发新的 Vue 组件**
1. 获取上下文
2. 检索记忆（"Element Plus 表格组件"）
3. 检索规则（"UI 设计"）
4. 查询数据结构（db-query）
5. 提交反馈

**场景 3：跨端协作（前后端联调）**
1. 获取项目成员
2. 检索后端记忆（"API 接口设计"）
3. 检索前端记忆（"API 调用"）
4. 查看数据库结构（db-query）
5. 提交联调反馈

---

### 第四部分：常见问题与故障排查

#### Q1：数据库查询失败
- 首次使用需提供数据库配置
- 检查连接信息是否正确
- 仅支持 SELECT 语句
- 单次查询最多返回 1000 行

#### Q2：记忆检索无结果
- 尝试更换关键词
- 检查 `project_name` 参数（必须是"{project.name}"）
- 确认记忆保留期（90 天）内是否有记录
- 尝试不指定 `employee_id` 进行全局检索

#### Q3：规则查询返回多条结果
- 优先使用最近更新的规则
- 根据 `domain` 字段筛选
- 可以同时参考多条规则

#### Q4：技能调用参数错误
- 查看错误信息中的参数提示
- 确认 `employee_id` 是否正确
- 确认技能名称是否正确
- 确认 `args` 参数格式正确（JSON 对象）

#### Q5：反馈提交失败
- 检查必填参数是否完整
- 确认项目反馈升级功能已启用
- 检查 `employee_id` 是否属于该项目成员

---

### 第五部分：最佳实践

#### 1. 参数规范
- 调用记忆时，必须传 `project_name="{project.name}"`
- 调用技能时，必须传 `employee_id`
- 提交反馈时，必须传 `employee_id`、`title`、`symptom`、`expected`

#### 2. 员工选择
- 根据任务类型选择合适的员工
- 跨端任务：分别调用相关员工的能力

#### 3. 记忆管理
- 定期检索记忆，避免重复踩坑
- 及时提交反馈，积累项目经验
- 使用精确的关键词提高检索准确率

#### 4. 规则遵循
- 开发前先检索相关规则
- 遵循规则中的最佳实践
- 发现规则不适用时及时反馈

#### 5. 技能使用
- 首次使用技能时注意配置要求
- 数据库查询注意安全限制
- 技能调用失败时查看详细错误信息

---

## 生成要求

1. **语言**：全部使用中文
2. **格式**：标准 Markdown
3. **完整性**：必须包含以上所有章节
4. **实用性**：提供具体的使用场景和示例
5. **清晰度**：每个工具的用途、参数、返回值都要说明清楚

请开始生成完整的使用手册。"""

    return {
        "status": "success",
        "template": template,
        "project_id": project.id,
        "project_name": project.name,
    }
