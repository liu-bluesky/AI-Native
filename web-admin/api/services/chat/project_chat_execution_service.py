"""Shared non-stream project chat execution helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.requests import ProjectChatReq
from services.assistant.assistant_workflow_state_service import (
    build_assistant_workflow_state,
    evolve_assistant_workflow_state,
    with_assistant_workflow_state,
)
from services.assistant.assistant_workflow_policy_service import (
    latest_assistant_workflow_state_from_messages,
    prepare_assistant_workflow_state,
)
from services.assistant.assistant_capability_router_service import (
    apply_capability_routing,
    build_capability_routing_decision,
)
from services.chat.archive_workflow_state_service import (
    build_pending_archive_workflow_state,
    reply_contains_structured_pending_archive,
    with_archive_workflow_state,
)


@dataclass
class ProjectChatExecutionResult:
    content: str
    provider_id: str = ""
    model_name: str = ""
    error_message: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    selected_employee_ids: list[str] = field(default_factory=list)

    @property
    def is_error(self) -> bool:
        return bool(self.error_message)


def _assistant_source_context_with_archive_workflow(
    source_context: dict[str, Any] | None,
    content: str,
    assistant_workflow_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = str(content or "").strip()
    context = with_assistant_workflow_state(source_context, assistant_workflow_state)
    if not text:
        return context
    if reply_contains_structured_pending_archive(text):
        return with_archive_workflow_state(
            context,
            build_pending_archive_workflow_state(reply_content=text),
        )
    return context


def _extract_stream_error_message(payload: dict[str, Any]) -> str:
    for key in ("message", "error_message", "detail", "guard_message", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = _extract_stream_error_message(value)
            if nested:
                return nested
    return "未知错误"


async def run_project_chat_once(
    *,
    project_id: str,
    username: str,
    req: ProjectChatReq,
    auth_payload: dict[str, Any],
    save_memory_snapshot: bool = False,
    memory_source: str = "project-chat",
    publish_realtime: bool = False,
) -> ProjectChatExecutionResult:
    from routers import projects as projects_router
    from services.providers.llm_provider_service import get_llm_provider_service

    project = projects_router.project_store.get(project_id)
    if project is None:
        raise RuntimeError(f"Project {project_id} not found")

    user_message = str(req.message or "").strip()
    assistant_message_id = str(req.assistant_message_id or "").strip()
    normalized_images = projects_router._normalize_image_inputs(req.images)
    attachment_names = [
        str(name or "").strip()
        for name in (req.attachment_names or [])
        if str(name or "").strip()
    ]
    history = list(req.history or [])
    if not user_message and not normalized_images and not attachment_names:
        raise RuntimeError("message is required")

    effective_user_message = user_message
    chat_session_id = projects_router._require_project_chat_session_id(req.chat_session_id)
    source_context = projects_router._resolve_project_chat_request_source_context(
        project_id,
        username,
        chat_session_id,
        req.source_context,
    )
    request_kind = projects_router._resolve_project_chat_request_kind(
        req.request_kind,
        source_context=source_context,
    )
    is_interaction_continuation = projects_router._is_project_chat_interaction_continuation(
        request_kind,
        source_context=source_context,
    )
    is_followup_replan = projects_router._is_project_chat_followup_replan(request_kind)
    previous_messages = projects_router.project_chat_store.list_messages(
        project_id,
        username,
        limit=20,
        chat_session_id=chat_session_id,
    )
    previous_assistant_workflow_state = latest_assistant_workflow_state_from_messages(previous_messages)
    if not effective_user_message and attachment_names:
        effective_user_message = f"我上传了附件：{', '.join(attachment_names)}。请先给我处理建议。"
    elif not effective_user_message and normalized_images:
        effective_user_message = "请基于我上传的图片给建议。"

    record_content = user_message or ("（发送了图片）" if normalized_images else "（发送了附件）")
    user_record = None
    if not is_followup_replan:
        user_record = projects_router._append_chat_record(
            project_id=project_id,
            username=username,
            role="user",
            content=record_content,
            message_id=str(req.message_id or "").strip(),
            chat_session_id=chat_session_id,
            attachments=attachment_names,
            images=normalized_images,
            source_context=source_context,
        )
    if publish_realtime and user_record is not None:
        await projects_router.publish_project_chat_record_realtime(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            message=user_record,
        )

    runtime_settings = projects_router._resolve_chat_runtime_settings(req, project)
    if str(runtime_settings.get("chat_mode") or "").strip().lower() == "external_agent":
        runtime_settings["chat_mode"] = "system"
    selected_employees, _ = projects_router._resolve_project_chat_employees(
        project_id,
        list(runtime_settings.get("selected_employee_ids") or []),
        str(runtime_settings.get("selected_employee_id") or ""),
    )
    selected_employee = selected_employees[0] if len(selected_employees) == 1 else None
    selected_employee_ids = [
        str(item.get("id") or "")
        for item in selected_employees
        if str(item.get("id") or "")
    ]
    employee_id_val = selected_employee_ids[0] if len(selected_employee_ids) == 1 else ""
    direct_lark_cli = None if is_interaction_continuation else await projects_router._execute_direct_lark_cli_project_host_command(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        employee_id=employee_id_val,
        project=project,
        user_message=effective_user_message,
        timeout_sec=20,
    )
    if direct_lark_cli is not None:
        try:
            direct_resolved_runtime = await projects_router._resolve_project_chat_runtime(runtime_settings, auth_payload)
            direct_provider_id = direct_resolved_runtime.provider_id
            direct_model_name = direct_resolved_runtime.model_name
            direct_llm_service = get_llm_provider_service()
        except Exception:
            direct_provider_id = ""
            direct_model_name = ""
            direct_llm_service = None
        model_reply = await projects_router._build_direct_lark_cli_model_reply(
            llm_service=direct_llm_service,
            provider_id=direct_provider_id,
            model_name=direct_model_name,
            user_message=effective_user_message,
            result=direct_lark_cli.get("result") if isinstance(direct_lark_cli.get("result"), dict) else {},
            fallback_reply=str(direct_lark_cli.get("content") or "").strip(),
        )
        content = str(model_reply.get("content") or direct_lark_cli.get("content") or "").strip()
        assistant_source_context = _assistant_source_context_with_archive_workflow(
            source_context,
            content,
        )
        assistant_source_context = projects_router._with_project_chat_pending_interaction(
            assistant_source_context,
            direct_lark_cli.get("pending_interaction")
            if isinstance(direct_lark_cli.get("pending_interaction"), dict)
            else None,
        )
        assistant_record = projects_router._append_chat_record(
            project_id=project_id,
            username=username,
            role="assistant",
            content=content,
            message_id=assistant_message_id,
            chat_session_id=chat_session_id,
            source_context=assistant_source_context,
        )
        if publish_realtime and assistant_record is not None:
            await projects_router.publish_project_chat_record_realtime(
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                message=assistant_record,
            )
        if save_memory_snapshot:
            projects_router._save_project_chat_memory_snapshot(
                project_id=project_id,
                user_message=effective_user_message,
                answer=content,
                chat_session_id=chat_session_id,
                selected_employee_ids=selected_employee_ids,
                source=memory_source,
                allow_requirement_record=False,
            )
        return ProjectChatExecutionResult(
            content=content,
            provider_id=(
                str(model_reply.get("provider_id") or direct_provider_id).strip()
                if model_reply.get("model_processed")
                else ""
            ),
            model_name=(
                str(model_reply.get("model_name") or direct_model_name).strip()
                if model_reply.get("model_processed")
                else "direct-lark-cli"
            ),
            selected_employee_ids=selected_employee_ids,
        )

    clarify_pending_interaction = projects_router._build_project_chat_clarify_pending_interaction(
        user_message=effective_user_message,
        chat_session_id=chat_session_id,
    )
    if clarify_pending_interaction is not None:
        content = "需要你先确认更新目标，我再继续处理。"
        assistant_source_context = projects_router._with_project_chat_pending_interaction(
            source_context,
            clarify_pending_interaction,
        )
        assistant_record = projects_router._append_chat_record(
            project_id=project_id,
            username=username,
            role="assistant",
            content=content,
            message_id=assistant_message_id,
            chat_session_id=chat_session_id,
            source_context=assistant_source_context,
        )
        if publish_realtime and assistant_record is not None:
            await projects_router.publish_project_chat_record_realtime(
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                message=assistant_record,
            )
        return ProjectChatExecutionResult(
            content=content,
            provider_id="",
            model_name="direct-clarify",
            selected_employee_ids=selected_employee_ids,
        )

    enabled_tool_names = list(runtime_settings.get("enabled_project_tool_names") or [])
    explicit_tool_filter = bool(runtime_settings.get("enabled_project_tool_names_explicit"))
    explicit_tool_request = (
        bool(runtime_settings.get("auto_use_tools"))
        and explicit_tool_filter
        and bool(enabled_tool_names)
    )

    resolved_runtime = await projects_router._resolve_project_chat_runtime(runtime_settings, auth_payload)
    provider_mode = resolved_runtime.provider_mode
    selected_provider = resolved_runtime.provider
    provider_id = resolved_runtime.provider_id
    model_name = resolved_runtime.model_name

    llm_service = get_llm_provider_service()
    model_parameter_mode = projects_router._resolve_provider_model_parameter_mode(
        llm_service,
        provider_mode=provider_mode,
        selected_provider=selected_provider,
        model_name=model_name,
    )

    if model_parameter_mode in {"image", "video"}:
        artifacts = projects_router._normalize_chat_media_artifacts(
            await llm_service.generate_media_artifacts(
                provider_id,
                model_name,
                effective_user_message,
                owner_username=username,
                include_all=projects_router.is_admin_like(auth_payload),
                image_size=projects_router._resolve_project_chat_image_size(
                    runtime_settings.get("image_resolution"),
                    runtime_settings.get("image_aspect_ratio"),
                ),
                video_aspect_ratio=str(runtime_settings.get("video_aspect_ratio") or "").strip(),
                video_duration_seconds=int(runtime_settings.get("video_duration_seconds") or 0) or None,
            )
        )
        if not artifacts:
            raise RuntimeError("模型未返回有效媒体结果")
        images = projects_router._collect_chat_artifact_urls(artifacts, asset_type="image")
        videos = projects_router._collect_chat_artifact_urls(artifacts, asset_type="video")
        content = projects_router._build_generated_media_answer(artifacts)
        assistant_record = projects_router._append_chat_record(
            project_id=project_id,
            username=username,
            role="assistant",
            content=content,
            message_id=assistant_message_id,
            chat_session_id=chat_session_id,
            images=images,
            videos=videos,
            source_context=_assistant_source_context_with_archive_workflow(source_context, content),
        )
        if publish_realtime:
            await projects_router.publish_project_chat_record_realtime(
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                message=assistant_record,
            )
        return ProjectChatExecutionResult(
            content=content,
            provider_id=provider_id,
            model_name=model_name,
            artifacts=artifacts,
            images=images,
            videos=videos,
            selected_employee_ids=selected_employee_ids,
        )

    temperature = float(runtime_settings.get("temperature") if runtime_settings.get("temperature") is not None else 0.1)
    temperature = max(0.0, min(temperature, 2.0))
    assistant_workflow_state = prepare_assistant_workflow_state(
        user_message=effective_user_message,
        source_context=source_context,
        previous_state=previous_assistant_workflow_state,
        chat_surface=str(req.chat_surface or "main-chat").strip() or "main-chat",
        auto_use_tools=bool(runtime_settings.get("auto_use_tools")) and (
            explicit_tool_request
            or (
                not explicit_tool_filter
                and projects_router._should_enable_chat_tools(
                    effective_user_message,
                    attachment_names,
                    normalized_images,
                    None,
                )
            )
        ),
    )
    tools: list[dict[str, Any]] = []
    tools_enabled = bool(runtime_settings.get("auto_use_tools")) and (
        explicit_tool_request
        or (
            not explicit_tool_filter
            and projects_router._should_enable_chat_tools(
                effective_user_message,
                attachment_names,
                normalized_images,
                assistant_workflow_state,
            )
        )
    )
    if tools_enabled:
        tools = projects_router._collect_runtime_tools(
            project_id,
            selected_employee_ids=selected_employee_ids,
            enabled_tool_names=enabled_tool_names,
            explicit_tool_filter=explicit_tool_filter,
            tool_priority=list(runtime_settings.get("tool_priority") or []),
            project_workspace_path=str(project.workspace_path or "").strip(),
        )
        effective_user_message = await projects_router._maybe_enrich_project_chat_message_with_url_content(
            effective_user_message,
            tools,
            host_workspace_path=str(project.workspace_path or "").strip(),
        )

    effective_workspace_path = projects_router._resolve_project_workspace_for_chat(project, runtime_settings)
    tools = apply_capability_routing(
        tools,
        assistant_workflow=assistant_workflow_state,
        chat_surface=str(req.chat_surface or "main-chat").strip() or "main-chat",
    )
    capability_routing = build_capability_routing_decision(
        tools,
        assistant_workflow=assistant_workflow_state,
        chat_surface=str(req.chat_surface or "main-chat").strip() or "main-chat",
    )
    messages = projects_router._build_project_chat_messages(
        project,
        effective_user_message,
        req.history,
        normalized_images,
        selected_employee=selected_employee,
        selected_employees=selected_employees,
        tools=tools,
        custom_system_prompt=projects_router._resolve_default_chat_system_prompt(runtime_settings.get("system_prompt")),
        history_limit=int(runtime_settings.get("history_limit") or 20),
        answer_style=str(runtime_settings.get("answer_style") or "concise"),
        prefer_conclusion_first=bool(runtime_settings.get("prefer_conclusion_first", True)),
        workspace_path=effective_workspace_path,
        skill_resource_directory=req.skill_resource_directory,
        employee_coordination_mode=str(runtime_settings.get("employee_coordination_mode") or "auto"),
        source_context=source_context,
        task_tree_prompt="",
    )
    runtime_context = projects_router.build_chat_runtime_context(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        employee_id=employee_id_val,
        selected_employee_ids=selected_employee_ids,
        workspace_path=effective_workspace_path,
        host_workspace_path=str(project.workspace_path or "").strip(),
        skill_resource_directory=req.skill_resource_directory,
        chat_surface=str(req.chat_surface or "main-chat").strip() or "main-chat",
        history=req.history,
        images=normalized_images,
        task_tree_payload=None,
        task_tree_prompt="",
        chat_settings=runtime_settings,
        resolved_provider=resolved_runtime,
        tools=tools,
        messages=messages,
        local_connector=None,
        local_connector_sandbox_mode="workspace-write",
        capability_routing=capability_routing,
        metadata={
            "assistant_workflow": assistant_workflow_state,
            "request_kind": request_kind,
            "interaction_continuation": is_interaction_continuation,
            "continuation_token": str(getattr(req, "continuation_token", "") or "").strip(),
        },
    )

    llm_service_runtime = projects_router._resolve_chat_llm_service_runtime(
        llm_service,
        resolved_runtime,
        auth_payload,
    )
    redis_client = await projects_router.get_redis_client()
    conv_manager = projects_router.ConversationManager(redis_client)
    session_id = await conv_manager.create_session(project_id, employee_id_val)
    orchestrator = projects_router.build_agent_orchestrator(
        llm_service_runtime,
        conv_manager,
        runtime_settings,
    )

    final_answer = ""
    stream_error = ""
    assistant_artifacts: list[dict[str, Any]] = []
    last_done_payload: dict[str, Any] | None = None
    cancel_event = projects_router.asyncio.Event()

    try:
        async for chunk_data in orchestrator.run(
            **projects_router.build_orchestrator_run_kwargs(
                session_id=session_id,
                user_message=effective_user_message,
                runtime_context=runtime_context,
                temperature=temperature,
                cancel_event=cancel_event,
            )
        ):
            outgoing = dict(chunk_data)
            event_type = str(outgoing.get("type") or "").strip().lower()
            if event_type == "artifact":
                artifact_batch = projects_router._normalize_chat_media_artifacts(outgoing.get("artifacts"))
                if artifact_batch:
                    assistant_artifacts = projects_router._merge_chat_media_artifacts(
                        assistant_artifacts,
                        artifact_batch,
                    )
            if event_type == "done":
                assistant_artifacts = projects_router._merge_chat_media_artifacts(
                    assistant_artifacts,
                    projects_router._normalize_chat_media_artifacts(outgoing.get("artifacts")),
                )
                final_answer = str(outgoing.get("content") or "")
                last_done_payload = dict(outgoing)
            if event_type == "error":
                stream_error = _extract_stream_error_message(outgoing)

        if stream_error:
            content = f"对话失败：{stream_error}"
            assistant_workflow_state = evolve_assistant_workflow_state(
                assistant_workflow_state,
                reply_content=content,
                is_error=True,
            )
            assistant_source_context = _assistant_source_context_with_archive_workflow(
                source_context,
                content,
                assistant_workflow_state,
            )
            if is_followup_replan and assistant_message_id:
                assistant_record = projects_router.project_chat_store.update_message(
                    project_id,
                    username,
                    assistant_message_id,
                    content=content,
                    source_context=assistant_source_context,
                )
            else:
                assistant_record = projects_router._append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=content,
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                    source_context=assistant_source_context,
                )
            if publish_realtime and assistant_record is not None:
                await projects_router.publish_project_chat_record_realtime(
                    project_id=project_id,
                    username=username,
                    chat_session_id=chat_session_id,
                    message=assistant_record,
                )
            return ProjectChatExecutionResult(
                content=content,
                provider_id=provider_id,
                model_name=model_name,
                error_message=stream_error,
                selected_employee_ids=selected_employee_ids,
            )

        images = projects_router._collect_chat_artifact_urls(assistant_artifacts, asset_type="image")
        videos = projects_router._collect_chat_artifact_urls(assistant_artifacts, asset_type="video")
        persisted_answer = (
            final_answer
            or (
                "已生成图片和视频，请查看下方结果。"
                if images and videos
                else "已生成图片，请查看下方结果。"
                if images
                else "已生成视频，请查看下方结果。"
                if videos
                else "模型未返回有效内容。"
            )
        )
        archive_workflow_state = (
            build_pending_archive_workflow_state(reply_content=persisted_answer)
            if reply_contains_structured_pending_archive(persisted_answer)
            else None
        )
        assistant_workflow_state = evolve_assistant_workflow_state(
            assistant_workflow_state,
            reply_content=persisted_answer,
            archive_workflow_state=archive_workflow_state,
        )
        assistant_source_context = _assistant_source_context_with_archive_workflow(
            source_context,
            persisted_answer,
            assistant_workflow_state,
        )
        assistant_source_context = projects_router._with_project_chat_pending_interaction(
            assistant_source_context,
            projects_router._build_project_chat_pending_interaction(last_done_payload or {}),
        )
        if is_followup_replan and assistant_message_id:
            assistant_record = projects_router.project_chat_store.update_message(
                project_id,
                username,
                assistant_message_id,
                content=persisted_answer,
                source_context=assistant_source_context,
            )
        else:
            assistant_record = projects_router._append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=persisted_answer,
                message_id=assistant_message_id,
                chat_session_id=chat_session_id,
                images=images,
                videos=videos,
                source_context=assistant_source_context,
            )
        if publish_realtime and assistant_record is not None:
            await projects_router.publish_project_chat_record_realtime(
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                message=assistant_record,
            )
        if save_memory_snapshot:
            projects_router._save_project_chat_memory_snapshot(
                project_id=project_id,
                user_message=effective_user_message,
                answer=final_answer or persisted_answer,
                chat_session_id=chat_session_id,
                task_tree_payload=(last_done_payload or {}).get("history_task_tree")
                or (last_done_payload or {}).get("task_tree"),
                selected_employee_ids=selected_employee_ids,
                source=memory_source,
                allow_requirement_record=False,
            )
        return ProjectChatExecutionResult(
            content=final_answer or persisted_answer,
            provider_id=provider_id,
            model_name=model_name,
            artifacts=assistant_artifacts,
            images=images,
            videos=videos,
            selected_employee_ids=selected_employee_ids,
        )
    except Exception as exc:
        content = f"对话失败：{str(exc)}"
        assistant_workflow_state = evolve_assistant_workflow_state(
            assistant_workflow_state,
            reply_content=content,
            is_error=True,
        )
        assistant_source_context = _assistant_source_context_with_archive_workflow(
            source_context,
            content,
            assistant_workflow_state,
        )
        if is_followup_replan and assistant_message_id:
            assistant_record = projects_router.project_chat_store.update_message(
                project_id,
                username,
                assistant_message_id,
                content=content,
                source_context=assistant_source_context,
            )
        else:
            assistant_record = projects_router._append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=content,
                message_id=assistant_message_id,
                chat_session_id=chat_session_id,
                source_context=assistant_source_context,
            )
        if publish_realtime and assistant_record is not None:
            await projects_router.publish_project_chat_record_realtime(
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                message=assistant_record,
            )
        return ProjectChatExecutionResult(
            content=content,
            provider_id=provider_id,
            model_name=model_name,
            error_message=str(exc),
            selected_employee_ids=selected_employee_ids,
        )
