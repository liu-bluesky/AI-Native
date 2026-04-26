from __future__ import annotations
import asyncio
import json
import re
import shlex
import time
from typing import Any, AsyncGenerator
from services.conversation_manager import ConversationManager
from services.project_chat_task_tree import audit_task_tree_round
from services.tool_executor import ToolExecutor
from core.observability import logger, metrics


_IMAGE_URL_PATTERN = re.compile(
    r"^https?://.+\.(?:png|jpe?g|gif|webp|bmp|svg)(?:[?#].*)?$",
    re.IGNORECASE,
)
_VIDEO_URL_PATTERN = re.compile(
    r"^https?://.+\.(?:mp4|mov|m4v|webm|avi|mkv)(?:[?#].*)?$",
    re.IGNORECASE,
)
_TASK_TREE_TOOL_NAMES = {
    "get_current_task_tree",
    "update_task_node_status",
    "complete_task_node_with_verification",
}
_HOST_EXECUTION_TOOL_NAMES = {
    "project_host_run_command",
}
_EXECUTION_REQUEST_PATTERNS = (
    r"\b(?:install|run|execute|send|list|query|check|open|configure|login|deploy|debug)\b",
)
_EXECUTION_REQUEST_HINT_PATTERNS = (
    r"帮我",
    r"请你",
    r"直接",
    r"继续",
)
_EXECUTION_ACTION_PATTERNS = (
    r"安装",
    r"执行",
    r"运行",
    r"发送",
    r"发",
    r"查询",
    r"查看",
    r"列出",
    r"配置",
    r"登录",
    r"授权",
    r"打开",
    r"启动",
    r"停止",
    r"重启",
    r"部署",
    r"排查",
)
_EXECUTION_DEFERRAL_PATTERNS = (
    r"你(?:现在)?(?:直接)?执行(?:下面|这条)?命令",
    r"把(?:终端)?输出发我",
    r"也可以自己先执行",
    r"你也可以自己",
    r"如果你要自己(?:先)?执行",
    r"只差最后一步执行",
    r"我就能继续",
    r"回复我[“\"]?(?:继续|已完成|已授权)",
    r"you can run",
    r"run (?:the|this) command",
    r"paste (?:the )?output",
    r"send me the output",
)
_REAL_BLOCKER_PATTERNS = (
    r"浏览器(?:里)?(?:完成|打开|授权|登录|确认)",
    r"需要你(?:本人|亲自)?(?:完成|确认|授权|登录)",
    r"验证码",
    r"人工确认",
    r"手动确认",
    r"权限限制",
    r"系统弹窗",
    r"browser (?:auth|authorization|login|confirmation)",
    r"manual (?:authorization|confirmation|approval)",
    r"captcha",
)
_AUTO_FOLLOWUP_COMMAND_PATTERNS = (
    r"run `([^`]+)` in the background",
    r"run `([^`]+)`",
    r"执行 `([^`]+)`",
    r"运行 `([^`]+)`",
)
_LARK_OPEN_ID_PATTERN = re.compile(r"\bou_[A-Za-z0-9]+\b")
_LARK_SEND_MESSAGE_INTENT_PATTERNS = (
    re.compile(
        r"(?:帮我|请|麻烦|直接|继续|现在)?\s*(?:给|向)\s*(?P<recipient>[^\s，。,：:；;“\"'‘’]+?)\s*(?:发送|发)\s*(?P<content>.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:send|message)\s+(?P<recipient>[A-Za-z0-9._-]+)\s+(?P<content>.+)",
        re.IGNORECASE,
    ),
)
_LARK_AUTH_BLOCKER_PATTERNS = (
    r"等待(?:配置应用|用户授权|授权)",
    r"verification url",
    r"open it in a browser",
    r"browser",
)


def _normalize_usage_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_usage_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _record_model_usage_event(
    *,
    project_id: str,
    employee_id: str,
    username: str,
    chat_session_id: str,
    provider_id: str,
    model_name: str,
    prompt_version: str,
    duration_ms: float,
    usage: dict[str, Any] | None,
    request_id: str,
) -> None:
    try:
        from core.deps import usage_store
    except Exception:
        return
    normalized_provider_id = str(provider_id or "").strip()
    normalized_model_name = str(model_name or "").strip()
    usage_payload = usage if isinstance(usage, dict) else {}
    if not (normalized_provider_id or normalized_model_name or usage_payload):
        return
    try:
        usage_store.record_event(
            employee_id,
            "",
            username or "anonymous",
            "model_call",
            client_ip="",
            scope_id="llm:chat",
            project_id=project_id,
            chat_session_id=chat_session_id,
            request_id=request_id,
            status="success",
            duration_ms=duration_ms,
            provider_id=normalized_provider_id,
            model_name=normalized_model_name,
            prompt_version=str(prompt_version or "").strip(),
            input_tokens=_normalize_usage_int(usage_payload.get("input_tokens")),
            output_tokens=_normalize_usage_int(usage_payload.get("output_tokens")),
            cached_input_tokens=_normalize_usage_int(usage_payload.get("cached_input_tokens")),
            total_tokens=_normalize_usage_int(usage_payload.get("total_tokens")),
            cost_usd=_normalize_usage_float(usage_payload.get("cost_usd")),
        )
    except Exception:
        logger.warning(
            "record_model_usage_event_failed",
            project_id=project_id,
            provider_id=normalized_provider_id,
            model_name=normalized_model_name,
        )


def _is_image_url(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lower = text.lower()
    if lower.startswith("data:image/"):
        return True
    return bool(_IMAGE_URL_PATTERN.match(text))


def _normalize_image_url(value: Any) -> str:
    text = str(value or "").strip()
    return text if _is_image_url(text) else ""


def _is_video_url(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lower = text.lower()
    if lower.startswith("data:video/"):
        return True
    return bool(_VIDEO_URL_PATTERN.match(text))


def _normalize_video_url(value: Any) -> str:
    text = str(value or "").strip()
    return text if _is_video_url(text) else ""


def _normalize_media_url(value: Any) -> str:
    return _normalize_image_url(value) or _normalize_video_url(value)


def _guess_mime_type(url: str, fallback: str = "") -> str:
    preferred = str(fallback or "").strip().lower()
    if preferred.startswith(("image/", "video/")):
        return preferred
    lower = str(url or "").lower()
    if lower.startswith("data:image/"):
        prefix = lower.split(";", 1)[0]
        return prefix.replace("data:", "", 1)
    if lower.startswith("data:video/"):
        prefix = lower.split(";", 1)[0]
        return prefix.replace("data:", "", 1)
    if ".png" in lower:
        return "image/png"
    if ".jpg" in lower or ".jpeg" in lower:
        return "image/jpeg"
    if ".gif" in lower:
        return "image/gif"
    if ".webp" in lower:
        return "image/webp"
    if ".bmp" in lower:
        return "image/bmp"
    if ".svg" in lower:
        return "image/svg+xml"
    if ".mp4" in lower:
        return "video/mp4"
    if ".mov" in lower:
        return "video/quicktime"
    if ".m4v" in lower:
        return "video/x-m4v"
    if ".webm" in lower:
        return "video/webm"
    if ".avi" in lower:
        return "video/x-msvideo"
    if ".mkv" in lower:
        return "video/x-matroska"
    return "image/png"


def _image_data_url_from_base64(value: Any, mime_type: str = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("data:image/"):
        return raw
    normalized = re.sub(r"\s+", "", raw)
    if not normalized:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", normalized):
        return ""
    return f"data:{_guess_mime_type('', mime_type)};base64,{normalized}"


def _preview_tool_result(result: Any, *, limit: int = 600) -> str:
    if isinstance(result, str):
        text = result
    else:
        try:
            text = json.dumps(result, ensure_ascii=False)
        except Exception:
            text = str(result)
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _truncate_text(value: Any, *, limit: int = 1200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _sanitize_tool_value(value: Any, *, _depth: int = 0) -> Any:
    if _depth >= 4:
        return _truncate_text(value, limit=400)
    if isinstance(value, dict):
        items = list(value.items())
        payload: dict[str, Any] = {}
        for index, (key, item) in enumerate(items):
            if index >= 20:
                payload["__truncated__"] = f"... {len(items) - 20} more keys"
                break
            payload[str(key)] = _sanitize_tool_value(item, _depth=_depth + 1)
        return payload
    if isinstance(value, (list, tuple)):
        items = list(value)
        payload = [
            _sanitize_tool_value(item, _depth=_depth + 1)
            for item in items[:12]
        ]
        if len(items) > 12:
            payload.append(f"... {len(items) - 12} more items")
        return payload
    if isinstance(value, str):
        return _truncate_text(value, limit=600)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _truncate_text(value, limit=400)


def _has_host_execution_tools(tools: list[dict[str, Any]] | None) -> bool:
    for item in tools or []:
        tool_name = str((item or {}).get("tool_name") or "").strip()
        if tool_name in _HOST_EXECUTION_TOOL_NAMES:
            return True
    return False


def _looks_like_execution_request(user_message: str) -> bool:
    text = str(user_message or "").strip()
    if not text:
        return False
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in _EXECUTION_REQUEST_PATTERNS):
        return True
    has_hint = any(re.search(pattern, text, re.IGNORECASE) for pattern in _EXECUTION_REQUEST_HINT_PATTERNS)
    has_action = any(re.search(pattern, text, re.IGNORECASE) for pattern in _EXECUTION_ACTION_PATTERNS)
    return has_hint and has_action


def _looks_like_execution_deferral(response_content: str) -> bool:
    text = str(response_content or "").strip()
    if not text:
        return False
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _EXECUTION_DEFERRAL_PATTERNS)


def _looks_like_real_blocker(response_content: str) -> bool:
    text = str(response_content or "").strip()
    if not text:
        return False
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _REAL_BLOCKER_PATTERNS)


def _should_retry_premature_execution_deferral(
    *,
    user_message: str,
    response_content: str,
    tools: list[dict[str, Any]] | None,
    successful_tool_names: list[str] | None,
) -> bool:
    normalized_response = str(response_content or "").strip()
    if not normalized_response:
        return False
    if not _has_host_execution_tools(tools):
        return False
    if "project_host_run_command" not in {str(item or "").strip() for item in (successful_tool_names or [])}:
        return False
    if not _looks_like_execution_request(user_message):
        return False
    if _looks_like_real_blocker(normalized_response):
        return False
    return _looks_like_execution_deferral(normalized_response)


def _collect_result_text_candidates(result: Any) -> list[str]:
    if isinstance(result, str):
        return [result]
    if not isinstance(result, dict):
        return []
    candidates: list[str] = []
    for key in ("stdout", "stderr", "output_preview", "error", "hint", "message"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)
    nested_error = result.get("error")
    if isinstance(nested_error, dict):
        for key in ("message", "hint", "detail"):
            value = nested_error.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value)
    return candidates


def _extract_json_string_payloads(text: str) -> list[str]:
    normalized = str(text or "").strip()
    if not normalized:
        return []
    payloads = [normalized]
    try:
        parsed = json.loads(normalized)
    except Exception:
        return payloads
    if isinstance(parsed, dict):
        for key in ("message", "hint", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                payloads.append(value)
            elif isinstance(value, dict):
                for nested_key in ("message", "hint", "detail"):
                    nested_value = value.get(nested_key)
                    if isinstance(nested_value, str) and nested_value.strip():
                        payloads.append(nested_value)
    return payloads


def _is_safe_auto_followup_host_command(
    command: str,
    *,
    executed_command: str = "",
) -> bool:
    normalized = str(command or "").strip()
    if not normalized:
        return False
    args = _parse_shell_like_command(normalized)
    if not args:
        return False
    if any(token in {"|", "||", "&&", ";"} for token in args):
        return False
    if any(marker in normalized for marker in ("\n", "\r", "$(", "`")):
        return False
    executed_args = _parse_shell_like_command(executed_command)
    if not executed_args:
        return False
    return args[0] == executed_args[0]


def _parse_shell_like_command(command: str) -> list[str]:
    normalized = str(command or "").strip()
    if not normalized:
        return []
    try:
        return shlex.split(normalized)
    except ValueError:
        return []


def _extract_lark_auth_login_domains_from_scope_command(command: str) -> list[str]:
    args = _parse_shell_like_command(command)
    if len(args) < 4 or args[:3] != ["lark-cli", "auth", "login"]:
        return []

    scope_values: list[str] = []
    index = 3
    while index < len(args):
        current = str(args[index] or "").strip()
        if current == "--scope" and index + 1 < len(args):
            scope_values.append(str(args[index + 1] or "").strip())
            index += 2
            continue
        if current.startswith("--scope="):
            scope_values.append(current.split("=", 1)[1].strip())
        index += 1

    domains: list[str] = []
    seen: set[str] = set()
    for raw_scope_value in scope_values:
        for token in re.split(r"[\s,]+", raw_scope_value):
            normalized = str(token or "").strip()
            if not normalized:
                continue
            domain = normalized.split(":", 1)[0].strip().lower()
            if not domain or not re.fullmatch(r"[a-z][a-z0-9_-]*", domain):
                continue
            if domain in seen:
                continue
            seen.add(domain)
            domains.append(domain)
    return domains


def _build_lark_auth_login_recovery_command(command: str) -> str:
    args = _parse_shell_like_command(command)
    if len(args) < 4 or args[:3] != ["lark-cli", "auth", "login"]:
        return ""

    domains = _extract_lark_auth_login_domains_from_scope_command(command)
    preserved_flags: list[str] = []
    index = 3
    while index < len(args):
        current = str(args[index] or "").strip()
        if current == "--scope":
            index += 2
            continue
        if current.startswith("--scope="):
            index += 1
            continue
        if current in {"--json", "--no-wait"}:
            preserved_flags.append(current)
        index += 1

    rebuilt = ["lark-cli", "auth", "login", *preserved_flags]
    if domains:
        rebuilt.extend(["--domain", ",".join(domains)])
    else:
        rebuilt.append("--recommend")
    return " ".join(shlex.quote(part) for part in rebuilt)


def _extract_lark_auth_recovery_host_command(
    result: Any,
    *,
    executed_command: str,
    seen_commands: set[str] | None = None,
) -> str:
    normalized_command = str(executed_command or "").strip()
    normalized_seen = {
        str(item or "").strip()
        for item in (seen_commands or set())
        if str(item or "").strip()
    }
    if not normalized_command:
        return ""
    lower_command = normalized_command.lower()
    if not lower_command.startswith("lark-cli auth login"):
        return ""

    all_text = "\n".join(_collect_result_text_candidates(result)).lower()
    if "invalid or malformed scopes" not in all_text:
        return ""

    recovery_command = _build_lark_auth_login_recovery_command(normalized_command)
    if not recovery_command or recovery_command in normalized_seen:
        return ""
    if not _is_safe_auto_followup_host_command(
        recovery_command,
        executed_command=normalized_command,
    ):
        return ""
    return recovery_command


def _extract_auto_followup_project_host_command(
    result: Any,
    *,
    executed_command: str = "",
    seen_commands: set[str] | None = None,
) -> str:
    normalized_seen = {str(item or "").strip() for item in (seen_commands or set()) if str(item or "").strip()}
    for candidate_text in _collect_result_text_candidates(result):
        for text in _extract_json_string_payloads(candidate_text):
            for pattern in _AUTO_FOLLOWUP_COMMAND_PATTERNS:
                match = re.search(pattern, text, re.IGNORECASE)
                if not match:
                    continue
                command = str(match.group(1) or "").strip()
                if not command or command in normalized_seen:
                    continue
                if not _is_safe_auto_followup_host_command(
                    command,
                    executed_command=executed_command,
                ):
                    continue
                return command
    return _extract_lark_auth_recovery_host_command(
        result,
        executed_command=executed_command,
        seen_commands=seen_commands,
    )


def _is_lark_contact_search_command(command: str) -> bool:
    args = _parse_shell_like_command(command)
    return len(args) >= 3 and args[:3] == ["lark-cli", "contact", "+search-user"]


def _is_lark_message_send_command(command: str) -> bool:
    args = _parse_shell_like_command(command)
    return len(args) >= 3 and args[:3] == ["lark-cli", "im", "+messages-send"]


def _is_lark_auth_login_command(command: str) -> bool:
    args = _parse_shell_like_command(command)
    return len(args) >= 3 and args[:3] == ["lark-cli", "auth", "login"]


def _normalize_lark_message_content(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^(?:消息|内容)\s*[:：]\s*", "", text)
    text = text.strip(" \t\r\n\"'“”‘’")
    return text.rstrip("。！？!?,，")


def _parse_lark_send_message_intent(user_message: str) -> dict[str, str]:
    text = str(user_message or "").strip()
    if not text:
        return {}
    for pattern in _LARK_SEND_MESSAGE_INTENT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        recipient = str(match.group("recipient") or "").strip(" \t\r\n\"'“”‘’")
        content = _normalize_lark_message_content(match.group("content"))
        if recipient and content:
            return {"recipient": recipient, "content": content}
    return {}


def _collect_lark_open_ids(payload: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) == "open_id" and isinstance(value, str):
                normalized = str(value).strip()
                if _LARK_OPEN_ID_PATTERN.fullmatch(normalized):
                    result.add(normalized)
            else:
                result.update(_collect_lark_open_ids(value))
        return result
    if isinstance(payload, list):
        for item in payload:
            result.update(_collect_lark_open_ids(item))
        return result
    if isinstance(payload, str):
        return set(_LARK_OPEN_ID_PATTERN.findall(payload))
    return result


def _extract_unique_lark_open_id_from_result(result: Any) -> str:
    open_ids: set[str] = set()
    if isinstance(result, dict):
        open_ids.update(_collect_lark_open_ids(result))
    for candidate in _collect_result_text_candidates(result):
        normalized = str(candidate or "").strip()
        if not normalized:
            continue
        try:
            parsed = json.loads(normalized)
        except Exception:
            open_ids.update(_collect_lark_open_ids(normalized))
        else:
            open_ids.update(_collect_lark_open_ids(parsed))
    return next(iter(open_ids)) if len(open_ids) == 1 else ""


def _build_lark_message_send_command(*, open_id: str, content: str) -> str:
    normalized_open_id = str(open_id or "").strip()
    normalized_content = _normalize_lark_message_content(content)
    if not normalized_open_id or not normalized_content:
        return ""
    parts = [
        "lark-cli",
        "im",
        "+messages-send",
        "--as",
        "user",
        "--user-id",
        normalized_open_id,
        "--text",
        normalized_content,
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _result_requires_lark_send_auth(result: Any) -> bool:
    text = "\n".join(_collect_result_text_candidates(result)).lower()
    if not text:
        return False
    return "missing required scope" in text or "missing_scope" in text


def _is_successful_project_host_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("timed_out"):
        return False
    if "error" in result:
        return False
    if result.get("ok") is True:
        return True
    try:
        return int(result.get("exit_code", 1)) == 0
    except (TypeError, ValueError):
        return False


def _is_lark_auth_blocker_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("timed_out"):
        return True
    text = "\n".join(_collect_result_text_candidates(result))
    if not text:
        return False
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _LARK_AUTH_BLOCKER_PATTERNS)


def _update_lark_workflow_state_from_result(
    workflow_state: dict[str, Any],
    *,
    executed_command: str,
    result: Any,
) -> None:
    normalized_command = str(executed_command or "").strip()
    if not normalized_command:
        return
    if _is_lark_message_send_command(normalized_command):
        if _result_requires_lark_send_auth(result):
            workflow_state["pending_send_command"] = normalized_command
            return
        if (
            workflow_state.get("pending_send_command") == normalized_command
            and _is_successful_project_host_result(result)
        ):
            workflow_state["pending_send_command"] = ""


def _extract_lark_workflow_followup_command(
    result: Any,
    *,
    executed_command: str,
    user_message: str,
    workflow_state: dict[str, Any] | None = None,
    seen_commands: set[str] | None = None,
) -> dict[str, str]:
    normalized_command = str(executed_command or "").strip()
    normalized_seen = {
        str(item or "").strip()
        for item in (seen_commands or set())
        if str(item or "").strip()
    }
    state = workflow_state or {}

    if _is_lark_contact_search_command(normalized_command):
        intent = _parse_lark_send_message_intent(user_message)
        open_id = _extract_unique_lark_open_id_from_result(result)
        followup_command = _build_lark_message_send_command(
            open_id=open_id,
            content=intent.get("content") or "",
        )
        if intent and followup_command and followup_command not in normalized_seen:
            state["pending_send_command"] = followup_command
            state["last_contact_open_id"] = open_id
            return {
                "command": followup_command,
                "reason": "lark_cli_send_message_workflow",
                "message": "已从联系人查询结果中拿到唯一 open_id，系统继续直接发送消息。",
            }

    if _is_lark_auth_login_command(normalized_command):
        pending_send_command = str(state.get("pending_send_command") or "").strip()
        if (
            pending_send_command
            and pending_send_command not in normalized_seen
            and _is_successful_project_host_result(result)
            and not _is_lark_auth_blocker_result(result)
        ):
            return {
                "command": pending_send_command,
                "reason": "lark_cli_resume_after_auth",
                "message": "授权命令已完成，系统正在自动重试之前待发送的消息。",
            }

    return {}


def _extract_tool_call_arguments(tool_call: dict[str, Any]) -> tuple[Any | None, str]:
    raw_arguments = str((tool_call.get("function") or {}).get("arguments") or "").strip()
    if not raw_arguments:
        return None, ""
    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return None, _truncate_text(raw_arguments, limit=400)
    return _sanitize_tool_value(parsed), _preview_tool_result(parsed, limit=400)


def _build_tool_call_event_payload(
    tool_call: dict[str, Any],
    *,
    tool_index: int,
    tool_count: int,
    requested_tool_count: int,
) -> dict[str, Any]:
    tool_name = str((tool_call.get("function") or {}).get("name") or "tool").strip() or "tool"
    arguments, arguments_preview = _extract_tool_call_arguments(tool_call)
    payload: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_index": tool_index,
        "tool_count": tool_count,
        "requested_tool_count": requested_tool_count,
        "arguments_preview": arguments_preview,
    }
    if arguments is not None:
        payload["arguments"] = arguments
        if isinstance(arguments, dict):
            command = str(arguments.get("command") or "").strip()
            cwd = str(arguments.get("cwd") or "").strip()
            if command:
                payload["command"] = _truncate_text(command, limit=500)
            if cwd:
                payload["cwd"] = _truncate_text(cwd, limit=300)
    return payload


def _build_tool_result_event_payload(
    tool_call: dict[str, Any],
    result: Any,
    *,
    tool_index: int,
    tool_count: int,
    requested_tool_count: int,
    duration_ms: float,
) -> dict[str, Any]:
    payload = _build_tool_call_event_payload(
        tool_call,
        tool_index=tool_index,
        tool_count=tool_count,
        requested_tool_count=requested_tool_count,
    )
    payload["output_preview"] = _preview_tool_result(result)
    payload["duration_ms"] = round(duration_ms, 1)
    if isinstance(result, dict):
        for key in (
            "ok",
            "timed_out",
            "blocked",
            "exit_code",
            "workspace_path",
            "requested_workspace_path",
            "workspace_source",
            "environment_label",
            "environment_summary",
            "service_start_script_hint",
            "source",
        ):
            if key in result:
                payload[key] = result.get(key)
        error_text = _truncate_text(result.get("error"), limit=1000)
        stdout_preview = _truncate_text(result.get("stdout"), limit=2000)
        stderr_preview = _truncate_text(result.get("stderr"), limit=2000)
        command = _truncate_text(result.get("command"), limit=500)
        cwd = _truncate_text(result.get("cwd"), limit=300)
        if command:
            payload["command"] = command
        if cwd:
            payload["cwd"] = cwd
        if error_text:
            payload["error"] = error_text
        if stdout_preview:
            payload["stdout_preview"] = stdout_preview
        if stderr_preview:
            payload["stderr_preview"] = stderr_preview
    return payload


def _build_guard_event_payload(
    *,
    reason: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "guard_reason": str(reason or "").strip(),
        "guard_message": str(message or "").strip(),
    }
    if isinstance(details, dict) and details:
        payload["guard_details"] = details
    return payload


def _extract_task_tree_payload(tool_name: str, result: Any) -> dict[str, Any] | None:
    normalized_tool_name = str(tool_name or "").strip()
    if normalized_tool_name not in _TASK_TREE_TOOL_NAMES:
        return None
    if not isinstance(result, dict):
        return None
    if isinstance(result.get("tree"), list) and str(result.get("chat_session_id") or "").strip():
        return result
    if isinstance(result.get("task_tree"), dict):
        payload = result.get("task_tree")
        if isinstance(payload, dict) and str(payload.get("chat_session_id") or "").strip():
            return payload
    if isinstance(result.get("history_task_tree"), dict):
        payload = result.get("history_task_tree")
        if isinstance(payload, dict) and str(payload.get("chat_session_id") or "").strip():
            return payload
    return None


def _build_done_payload(
    *,
    content: str,
    artifacts: list[dict[str, Any]],
    project_id: str,
    username: str,
    chat_session_id: str,
    successful_tool_names: list[str],
    task_tree_tool_used: bool,
    completed_reason: str = "",
    guard_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "type": "done",
        "content": content,
        "artifacts": artifacts,
        "images": _collect_artifact_urls(artifacts, asset_type="image"),
        "videos": _collect_artifact_urls(artifacts, asset_type="video"),
    }
    if str(completed_reason or "").strip():
        payload["completed_reason"] = str(completed_reason).strip()
    if isinstance(guard_payload, dict) and guard_payload:
        payload.update(guard_payload)
    task_tree_audit = audit_task_tree_round(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        assistant_content=content,
        successful_tool_names=successful_tool_names,
        task_tree_tool_used=task_tree_tool_used,
    )
    if isinstance(task_tree_audit, dict):
        payload["task_tree_audit"] = task_tree_audit
        if "task_tree" in task_tree_audit:
            payload["task_tree"] = task_tree_audit.get("task_tree")
        history_task_tree_payload = task_tree_audit.get("history_task_tree")
        if isinstance(history_task_tree_payload, dict):
            payload["history_task_tree"] = history_task_tree_payload
    return payload


def _artifact_asset_type(item: dict[str, Any]) -> str:
    explicit = str(item.get("asset_type") or "").strip().lower()
    if explicit in {"image", "video"}:
        return explicit
    mime_type = str(item.get("mime_type") or "").strip().lower()
    if mime_type.startswith("video/"):
        return "video"
    content_url = str(item.get("content_url") or "").strip()
    preview_url = str(item.get("preview_url") or "").strip()
    if _is_video_url(content_url) or _is_video_url(preview_url):
        return "video"
    return "image"


def _collect_artifact_urls(
    items: list[dict[str, Any]],
    *,
    asset_type: str,
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for item in items:
        if _artifact_asset_type(item) != asset_type:
            continue
        candidates = (
            [str(item.get("content_url") or "").strip()]
            if asset_type == "video"
            else [
                str(item.get("preview_url") or "").strip(),
                str(item.get("content_url") or "").strip(),
            ]
        )
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            urls.append(candidate)
    return urls


def _dedupe_media_artifacts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        asset_type = _artifact_asset_type(item)
        preview_url = str(item.get("preview_url") or "").strip()
        content_url = str(item.get("content_url") or "").strip()
        key = f"{asset_type}||{preview_url}||{content_url}"
        if not preview_url and not content_url:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _normalize_single_media_artifact(
    item: Any,
    *,
    default_title: str,
    index: int,
) -> dict[str, Any] | None:
    if isinstance(item, str):
        media_url = _normalize_media_url(item)
        if not media_url:
            return None
        asset_type = "video" if _is_video_url(media_url) else "image"
        return {
            "asset_type": asset_type,
            "title": f"{default_title} #{index}",
            "summary": "",
            "preview_url": media_url,
            "content_url": media_url,
            "mime_type": _guess_mime_type(media_url),
            "metadata": {},
        }
    if not isinstance(item, dict):
        return None

    hinted_asset_type = str(
        item.get("asset_type")
        or item.get("assetType")
        or item.get("type")
        or item.get("kind")
        or ""
    ).strip().lower()
    mime_type = str(
        item.get("mime_type")
        or item.get("mimeType")
        or item.get("content_type")
        or item.get("contentType")
        or item.get("media_type")
        or item.get("mediaType")
        or ""
    ).strip()

    preview_url = ""
    for key in (
        "preview_url",
        "previewUrl",
        "thumbnail_url",
        "thumbnailUrl",
        "poster_url",
        "posterUrl",
        "cover_url",
        "coverUrl",
    ):
        preview_url = _normalize_media_url(item.get(key))
        if preview_url:
            break

    content_url = ""
    for key in (
        "content_url",
        "contentUrl",
        "image_url",
        "imageUrl",
        "video_url",
        "videoUrl",
        "url",
        "source_url",
        "sourceUrl",
        "download_url",
        "downloadUrl",
        "href",
        "uri",
    ):
        content_url = _normalize_media_url(item.get(key))
        if content_url:
            break

    asset_type = hinted_asset_type if hinted_asset_type in {"image", "video"} else ""
    if not asset_type:
        if mime_type.lower().startswith("video/"):
            asset_type = "video"
        elif mime_type.lower().startswith("image/"):
            asset_type = "image"
        elif _is_video_url(content_url) or _is_video_url(preview_url):
            asset_type = "video"
        else:
            asset_type = "image"

    if asset_type == "video":
        if not content_url and _is_video_url(preview_url):
            content_url = preview_url
        if not preview_url:
            preview_url = content_url
    else:
        if not preview_url:
            preview_url = content_url
        if not content_url:
            content_url = preview_url

    if asset_type == "image" and not preview_url and not content_url:
        for key in ("b64_json", "base64", "image_base64", "imageBase64", "contentBase64"):
            data_url = _image_data_url_from_base64(item.get(key), mime_type)
            if data_url:
                preview_url = data_url
                content_url = data_url
                break

    if not preview_url and not content_url:
        return None

    title = str(
        item.get("title")
        or item.get("name")
        or item.get("filename")
        or item.get("file_name")
        or item.get("label")
        or f"{default_title} #{index}"
    ).strip()
    summary = str(
        item.get("summary")
        or item.get("description")
        or item.get("caption")
        or item.get("prompt")
        or ""
    ).strip()
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "asset_type": asset_type,
        "title": title[:120] or f"{default_title} #{index}",
        "summary": summary[:1000],
        "preview_url": preview_url,
        "content_url": content_url,
        "mime_type": _guess_mime_type(content_url or preview_url, mime_type),
        "metadata": metadata,
    }


def _extract_media_artifacts(
    payload: Any,
    *,
    default_title: str,
    _depth: int = 0,
) -> list[dict[str, Any]]:
    if _depth > 4 or payload is None:
        return []

    if isinstance(payload, str):
        normalized = _normalize_single_media_artifact(
            payload,
            default_title=default_title,
            index=1,
        )
        return [normalized] if normalized else []

    if isinstance(payload, list):
        result: list[dict[str, Any]] = []
        for idx, item in enumerate(payload, start=1):
            result.extend(
                _extract_media_artifacts(
                    item,
                    default_title=default_title,
                    _depth=_depth + 1,
                )
            )
            if isinstance(item, (str, dict)):
                normalized = _normalize_single_media_artifact(
                    item,
                    default_title=default_title,
                    index=idx,
                )
                if normalized:
                    result.append(normalized)
        return _dedupe_media_artifacts(result)

    if not isinstance(payload, dict):
        return []

    result: list[dict[str, Any]] = []
    normalized_self = _normalize_single_media_artifact(
        payload,
        default_title=default_title,
        index=1,
    )
    if normalized_self:
        result.append(normalized_self)

    for key in (
        "artifacts",
        "images",
        "videos",
        "image_urls",
        "imageUrls",
        "video_urls",
        "videoUrls",
        "generated_images",
        "generatedImages",
        "generated_videos",
        "generatedVideos",
        "results",
        "items",
        "data",
        "output",
        "result",
        "assets",
    ):
        if key not in payload:
            continue
        result.extend(
            _extract_media_artifacts(
                payload.get(key),
                default_title=default_title,
                _depth=_depth + 1,
            )
        )
    return _dedupe_media_artifacts(result)

class AgentOrchestrator:
    def __init__(
        self,
        llm_service,
        conversation_manager: ConversationManager,
        max_loops: int = 20,
        max_tool_rounds: int = 6,
        repeated_tool_call_threshold: int = 2,
        tool_only_threshold: int = 3,
        tool_budget_strategy: str = "finalize",
        max_tool_calls_per_round: int = 6,
        tool_timeout_sec: int = 60,
        tool_retry_count: int = 0,
    ):
        self._llm = llm_service
        self._conv = conversation_manager
        self._max_loops = max(1, min(int(max_loops), 60))
        self._max_tool_rounds = max(1, min(int(max_tool_rounds), 30))
        self._repeated_tool_call_threshold = max(1, min(int(repeated_tool_call_threshold), 10))
        self._tool_only_threshold = max(1, min(int(tool_only_threshold), 10))
        strategy = str(tool_budget_strategy or "finalize").strip().lower()
        self._tool_budget_strategy = strategy if strategy in {"stop", "finalize"} else "finalize"
        self._max_tool_calls_per_round = max(1, min(int(max_tool_calls_per_round), 30))
        self._tool_timeout_sec = max(1, min(int(tool_timeout_sec), 600))
        self._tool_retry_count = max(0, min(int(tool_retry_count), 5))

    async def run(
        self,
        session_id: str,
        user_message: str,
        tools: list[dict],
        provider_id: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        project_id: str,
        employee_id: str,
        cancel_event: asyncio.Event,
        username: str = "",
        chat_session_id: str = "",
        role_ids: list[str] | None = None,
        messages: list[dict] | None = None,
        local_connector: Any | None = None,
        local_connector_workspace_path: str = "",
        host_workspace_path: str = "",
        local_connector_sandbox_mode: str = "workspace-write",
        global_assistant_bridge_handler: Any | None = None,
        prompt_version: str = "",
    ) -> AsyncGenerator[dict, None]:
        start_time = time.time()
        metrics.inc_counter("conversation_started", {"project_id": project_id})

        if not user_message.strip():
            yield {"type": "error", "message": "消息不能为空"}
            metrics.inc_counter("conversation_error", {"reason": "empty_message"})
            return

        try:
            if messages is None:
                messages = await self._conv.get_context(session_id, max_tokens * 3)
                messages.append({"role": "user", "content": user_message})

            tool_executor = ToolExecutor(
                project_id,
                employee_id,
                username=username,
                chat_session_id=chat_session_id,
                role_ids=role_ids,
                timeout_sec=self._tool_timeout_sec,
                max_retries=self._tool_retry_count,
                local_connector=local_connector,
                local_connector_workspace_path=local_connector_workspace_path,
                host_workspace_path=host_workspace_path,
                local_connector_sandbox_mode=local_connector_sandbox_mode,
                global_assistant_bridge_handler=global_assistant_bridge_handler,
            )
            loop_count = 0
            completed = False
            tool_only_loops = 0
            tool_rounds = 0
            last_tool_signature = ""
            repeated_tool_signature_rounds = 0
            collected_artifacts: list[dict[str, Any]] = []
            successful_tool_names: list[str] = []
            task_tree_tool_used = False
            premature_deferral_retries = 0
            auto_followup_retries = 0
            seen_auto_followup_commands: set[str] = set()
            lark_workflow_state: dict[str, Any] = {}

            while loop_count < self._max_loops:
                if cancel_event.is_set():
                    yield _build_done_payload(
                        content="[已停止]",
                        artifacts=collected_artifacts,
                        project_id=project_id,
                        username=username,
                        chat_session_id=chat_session_id,
                        successful_tool_names=successful_tool_names,
                        task_tree_tool_used=task_tree_tool_used,
                        completed_reason="cancelled",
                    )
                    completed = True
                    break

                loop_count += 1
                response_content = ""
                tool_calls_buffer = {}
                llm_call_started = time.monotonic()
                llm_usage: dict[str, Any] = {}
                llm_provider_id = str(provider_id or "").strip()
                llm_model_name = str(model_name or "").strip()

                logger.info("agent_loop_start", loop=loop_count, tools_count=len(tools), has_system_prompt=any(m.get("role") == "system" for m in messages))

                chunk_count = 0
                async for chunk in self._llm.chat_completion_stream(
                    provider_id=provider_id,
                    model_name=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=120,
                    tools=self._format_tools(tools) if tools else None
                ):
                    chunk_count += 1
                    if chunk_count <= 3:
                        logger.info("llm_chunk_sample", chunk_index=chunk_count, chunk_type=type(chunk).__name__, chunk_keys=list(chunk.keys()) if isinstance(chunk, dict) else None)

                    if cancel_event.is_set():
                        break

                    if isinstance(chunk, dict):
                        if isinstance(chunk.get("usage"), dict):
                            llm_usage = dict(chunk["usage"])
                            llm_provider_id = str(chunk.get("provider_id") or llm_provider_id).strip()
                            llm_model_name = str(chunk.get("model_name") or llm_model_name).strip()
                        if "tool_calls" in chunk:
                            logger.info("tool_calls_chunk", tool_calls=chunk["tool_calls"])
                            for tc in chunk["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_buffer:
                                    tool_calls_buffer[idx] = {"id": tc.get("id", ""), "type": "function", "function": {"name": "", "arguments": ""}}
                                if "name" in tc:
                                    tool_calls_buffer[idx]["function"]["name"] += tc["name"]
                                if "arguments" in tc:
                                    tool_calls_buffer[idx]["function"]["arguments"] += tc["arguments"]
                                if "function" in tc:
                                    if "name" in tc["function"]:
                                        tool_calls_buffer[idx]["function"]["name"] += tc["function"]["name"]
                                    if "arguments" in tc["function"]:
                                        tool_calls_buffer[idx]["function"]["arguments"] += tc["function"]["arguments"]
                        if "content" in chunk:
                            delta = chunk["content"]
                            response_content += delta
                            yield {"type": "delta", "content": delta}

                _record_model_usage_event(
                    project_id=project_id,
                    employee_id=employee_id,
                    username=username,
                    chat_session_id=chat_session_id,
                    provider_id=llm_provider_id,
                    model_name=llm_model_name,
                    prompt_version=prompt_version,
                    duration_ms=round((time.monotonic() - llm_call_started) * 1000, 1),
                    usage=llm_usage,
                    request_id=f"{session_id}:loop:{loop_count}",
                )

                logger.info("agent_loop_response", has_tool_calls=bool(tool_calls_buffer), response_length=len(response_content))

                if tool_calls_buffer:
                    tool_rounds += 1
                    ordered_tool_calls = list(tool_calls_buffer.values())
                    requested_tool_count = len(ordered_tool_calls)
                    if len(ordered_tool_calls) > self._max_tool_calls_per_round:
                        ordered_tool_calls = ordered_tool_calls[: self._max_tool_calls_per_round]

                    signature_items: list[str] = []
                    for tc in ordered_tool_calls:
                        fn = str((tc.get("function") or {}).get("name") or "")
                        args = str((tc.get("function") or {}).get("arguments") or "")
                        signature_items.append(f"{fn}::{args}")
                    current_tool_signature = "||".join(sorted(signature_items))
                    if current_tool_signature and current_tool_signature == last_tool_signature:
                        repeated_tool_signature_rounds += 1
                    else:
                        repeated_tool_signature_rounds = 0
                    last_tool_signature = current_tool_signature

                    if tool_rounds > self._max_tool_rounds:
                        guard_message = (
                            f"工具调用已达到预算上限（已请求第 {tool_rounds} 轮，当前上限 {self._max_tool_rounds} 轮）。"
                        )
                        guard_payload = _build_guard_event_payload(
                            reason="tool_budget_exceeded",
                            message=guard_message,
                            details={
                                "tool_rounds": tool_rounds,
                                "max_tool_rounds": self._max_tool_rounds,
                                "requested_tool_count": requested_tool_count,
                                "max_tool_calls_per_round": self._max_tool_calls_per_round,
                            },
                        )
                        fallback = await self._resolve_guard_fallback(
                            provider_id=provider_id,
                            model_name=model_name,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            default_message="工具调用已达到预算上限，已停止生成。请补充更明确的参数后重试。",
                            guard_message=guard_message,
                        )
                        yield _build_done_payload(
                            content=fallback,
                            artifacts=collected_artifacts,
                            project_id=project_id,
                            username=username,
                            chat_session_id=chat_session_id,
                            successful_tool_names=successful_tool_names,
                            task_tree_tool_used=task_tree_tool_used,
                            completed_reason="tool_budget_exceeded",
                            guard_payload=guard_payload,
                        )
                        await self._conv.append_message(session_id, {"role": "user", "content": user_message})
                        await self._conv.append_message(session_id, {"role": "assistant", "content": fallback})
                        duration = time.time() - start_time
                        metrics.observe_histogram("conversation_duration", duration * 1000)
                        metrics.inc_counter("conversation_completed", {"project_id": project_id})
                        logger.info(
                            "conversation_completed",
                            project_id=project_id,
                            duration_ms=int(duration * 1000),
                            loops=loop_count,
                            reason="tool_budget_exceeded",
                        )
                        completed = True
                        break
                    if (
                        repeated_tool_signature_rounds >= self._repeated_tool_call_threshold
                        and not str(response_content or "").strip()
                    ):
                        guard_message = (
                            "检测到重复工具调用且没有正文输出"
                            f"（连续命中 {repeated_tool_signature_rounds} 次，阈值 {self._repeated_tool_call_threshold} 次）。"
                        )
                        guard_payload = _build_guard_event_payload(
                            reason="repeated_tool_signature",
                            message=guard_message,
                            details={
                                "repeated_tool_signature_rounds": repeated_tool_signature_rounds,
                                "repeated_tool_call_threshold": self._repeated_tool_call_threshold,
                                "tool_rounds": tool_rounds,
                                "requested_tool_count": requested_tool_count,
                            },
                        )
                        fallback = await self._resolve_guard_fallback(
                            provider_id=provider_id,
                            model_name=model_name,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            default_message="检测到重复工具调用且未产出正文，已停止生成。请调整问题或补充参数后重试。",
                            guard_message=guard_message,
                        )
                        yield _build_done_payload(
                            content=fallback,
                            artifacts=collected_artifacts,
                            project_id=project_id,
                            username=username,
                            chat_session_id=chat_session_id,
                            successful_tool_names=successful_tool_names,
                            task_tree_tool_used=task_tree_tool_used,
                            completed_reason="repeated_tool_signature",
                            guard_payload=guard_payload,
                        )
                        await self._conv.append_message(session_id, {"role": "user", "content": user_message})
                        await self._conv.append_message(session_id, {"role": "assistant", "content": fallback})
                        duration = time.time() - start_time
                        metrics.observe_histogram("conversation_duration", duration * 1000)
                        metrics.inc_counter("conversation_completed", {"project_id": project_id})
                        logger.info(
                            "conversation_completed",
                            project_id=project_id,
                            duration_ms=int(duration * 1000),
                            loops=loop_count,
                            reason="repeated_tool_signature",
                        )
                        completed = True
                        break

                    response_has_text = bool(str(response_content or "").strip())
                    round_made_tool_progress = False
                    messages.append({"role": "assistant", "content": response_content or None, "tool_calls": ordered_tool_calls})

                    for index, tc in enumerate(ordered_tool_calls, start=1):
                        yield {
                            "type": "tool_start",
                            **_build_tool_call_event_payload(
                                tc,
                                tool_index=index,
                                tool_count=len(ordered_tool_calls),
                                requested_tool_count=requested_tool_count,
                            ),
                        }
                    tool_start = time.time()
                    tool_results = await tool_executor.execute_parallel(ordered_tool_calls)
                    tool_duration = time.time() - tool_start

                    metrics.observe_histogram("tool_execution_duration", tool_duration * 1000)
                    metrics.inc_counter("tool_calls_total", {"count": len(ordered_tool_calls)})

                    for index, (tc, result) in enumerate(zip(ordered_tool_calls, tool_results), start=1):
                        if isinstance(result, Exception):
                            result = {"error": str(result)}
                        tool_name = tc["function"]["name"]
                        success = "error" not in result
                        if success:
                            round_made_tool_progress = True
                            successful_tool_names.append(str(tool_name or "").strip())
                            if str(tool_name or "").strip() in _TASK_TREE_TOOL_NAMES:
                                task_tree_tool_used = True
                        metrics.inc_counter("tool_call", {"tool": tool_name, "status": "success" if success else "error"})
                        yield {
                            "type": "tool_result",
                            "status": "success" if success else "error",
                            **_build_tool_result_event_payload(
                                tc,
                                result,
                                tool_index=index,
                                tool_count=len(ordered_tool_calls),
                                requested_tool_count=requested_tool_count,
                                duration_ms=tool_duration * 1000,
                            ),
                            "task_tree": _extract_task_tree_payload(tool_name, result),
                        }
                        artifacts = _extract_media_artifacts(
                            result,
                            default_title=str(tool_name or "AI 生成图片"),
                        )
                        if artifacts:
                            collected_artifacts = _dedupe_media_artifacts(
                                [*collected_artifacts, *artifacts]
                            )
                            yield {
                                "type": "artifact",
                                "tool_name": tool_name,
                                "artifacts": artifacts,
                                "images": _collect_artifact_urls(artifacts, asset_type="image"),
                                "videos": _collect_artifact_urls(artifacts, asset_type="video"),
                            }
                        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, ensure_ascii=False)})
                        if str(tool_name or "").strip() == "project_host_run_command":
                            current_result = result
                            current_command = str(result.get("command") or "")
                            _update_lark_workflow_state_from_result(
                                lark_workflow_state,
                                executed_command=current_command,
                                result=current_result,
                            )
                            while auto_followup_retries < 4:
                                followup = _extract_lark_workflow_followup_command(
                                    current_result,
                                    executed_command=current_command,
                                    user_message=user_message,
                                    workflow_state=lark_workflow_state,
                                    seen_commands=seen_auto_followup_commands,
                                )
                                if not followup:
                                    followup_command = _extract_auto_followup_project_host_command(
                                        current_result,
                                        executed_command=current_command,
                                        seen_commands=seen_auto_followup_commands,
                                    )
                                    if followup_command:
                                        followup = {
                                            "command": followup_command,
                                            "reason": "auto_followup_command",
                                            "message": (
                                                "检测到工具结果里已经给出了可继续执行的下一条命令，"
                                                "系统已自动继续执行。"
                                            ),
                                        }
                                followup_command = str(followup.get("command") or "").strip()
                                if not followup_command:
                                    break
                                auto_followup_retries += 1
                                round_made_tool_progress = True
                                seen_auto_followup_commands.add(followup_command)
                                synthetic_tool_call = {
                                    "id": f"auto-followup-{auto_followup_retries}",
                                    "type": "function",
                                    "function": {
                                        "name": "project_host_run_command",
                                        "arguments": json.dumps(
                                            {
                                                "command": followup_command,
                                                "timeout_sec": 30,
                                            },
                                            ensure_ascii=False,
                                        ),
                                    },
                                }
                                yield {
                                    "type": "auto_continue",
                                    "reason": str(followup.get("reason") or "auto_followup_command"),
                                    "message": str(
                                        followup.get("message")
                                        or "系统已自动继续执行。"
                                    ),
                                    "previous_response_preview": _truncate_text(
                                        followup_command,
                                        limit=300,
                                    ),
                                    "retry_count": auto_followup_retries,
                                }
                                yield {
                                    "type": "tool_start",
                                    **_build_tool_call_event_payload(
                                        synthetic_tool_call,
                                        tool_index=1,
                                        tool_count=1,
                                        requested_tool_count=1,
                                    ),
                                }
                                messages.append(
                                    {
                                        "role": "assistant",
                                        "content": None,
                                        "tool_calls": [synthetic_tool_call],
                                    }
                                )
                                synthetic_tool_result = await tool_executor.execute_parallel(
                                    [synthetic_tool_call],
                                )
                                synthetic_result = synthetic_tool_result[0]
                                if isinstance(synthetic_result, Exception):
                                    synthetic_result = {"error": str(synthetic_result)}
                                synthetic_success = "error" not in synthetic_result
                                if synthetic_success:
                                    round_made_tool_progress = True
                                    successful_tool_names.append("project_host_run_command")
                                yield {
                                    "type": "tool_result",
                                    "status": "success" if synthetic_success else "error",
                                    **_build_tool_result_event_payload(
                                        synthetic_tool_call,
                                        synthetic_result,
                                        tool_index=1,
                                        tool_count=1,
                                        requested_tool_count=1,
                                        duration_ms=0,
                                    ),
                                }
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": synthetic_tool_call["id"],
                                        "content": json.dumps(
                                            synthetic_result,
                                            ensure_ascii=False,
                                        ),
                                    }
                                )
                                current_result = synthetic_result
                                current_command = str(
                                    synthetic_result.get("command") or followup_command
                                )
                                _update_lark_workflow_state_from_result(
                                    lark_workflow_state,
                                    executed_command=current_command,
                                    result=current_result,
                                )
                    if response_has_text or round_made_tool_progress:
                        tool_only_loops = 0
                    else:
                        tool_only_loops += 1
                    if tool_only_loops >= self._tool_only_threshold:
                        guard_message = (
                            f"工具调用连续多轮未产出正文（连续 {tool_only_loops} 轮，阈值 {self._tool_only_threshold} 轮）。"
                        )
                        guard_payload = _build_guard_event_payload(
                            reason="tool_only_loops",
                            message=guard_message,
                            details={
                                "tool_only_loops": tool_only_loops,
                                "tool_only_threshold": self._tool_only_threshold,
                                "tool_rounds": tool_rounds,
                                "requested_tool_count": requested_tool_count,
                            },
                        )
                        fallback = await self._resolve_guard_fallback(
                            provider_id=provider_id,
                            model_name=model_name,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            default_message="工具调用连续多轮未产出正文，已停止生成。请补充更明确的参数后重试。",
                            guard_message=guard_message,
                        )
                        yield _build_done_payload(
                            content=fallback,
                            artifacts=collected_artifacts,
                            project_id=project_id,
                            username=username,
                            chat_session_id=chat_session_id,
                            successful_tool_names=successful_tool_names,
                            task_tree_tool_used=task_tree_tool_used,
                            completed_reason="tool_only_loops",
                            guard_payload=guard_payload,
                        )
                        await self._conv.append_message(session_id, {"role": "user", "content": user_message})
                        await self._conv.append_message(session_id, {"role": "assistant", "content": fallback})
                        duration = time.time() - start_time
                        metrics.observe_histogram("conversation_duration", duration * 1000)
                        metrics.inc_counter("conversation_completed", {"project_id": project_id})
                        logger.info("conversation_completed", project_id=project_id, duration_ms=int(duration * 1000), loops=loop_count, reason="tool_only_loops")
                        completed = True
                        break
                    continue

                if (
                    premature_deferral_retries < 2
                    and _should_retry_premature_execution_deferral(
                        user_message=user_message,
                        response_content=response_content,
                        tools=tools,
                        successful_tool_names=successful_tool_names,
                    )
                ):
                    premature_deferral_retries += 1
                    yield {
                        "type": "auto_continue",
                        "reason": "premature_execution_deferral",
                        "message": (
                            "检测到上一条回复把可继续执行的步骤提前下放给了用户，"
                            "系统已自动继续补跑后续命令。"
                        ),
                        "previous_response_preview": _truncate_text(
                            response_content,
                            limit=300,
                        ),
                        "retry_count": premature_deferral_retries,
                    }
                    messages.append({"role": "assistant", "content": response_content})
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "上一条回复把仍可继续执行的步骤提前下放给了用户。"
                                "当前用户明确要求你在这台电脑上直接执行，且宿主命令工具仍可用。"
                                "除非存在真实人工阻塞（例如浏览器授权、验证码、权限确认或系统弹窗），"
                                "否则继续调用必要工具直到完成用户原始目标。"
                                "不要再让用户自己执行命令、复制命令、粘贴输出或回复“继续”来替你完成本应可自动执行的步骤。"
                            ),
                        }
                    )
                    logger.info(
                        "agent_loop_retry_after_premature_deferral",
                        project_id=project_id,
                        retry_count=premature_deferral_retries,
                    )
                    continue

                yield _build_done_payload(
                    content=response_content,
                    artifacts=collected_artifacts,
                    project_id=project_id,
                    username=username,
                    chat_session_id=chat_session_id,
                    successful_tool_names=successful_tool_names,
                    task_tree_tool_used=task_tree_tool_used,
                    completed_reason="completed",
                )
                await self._conv.append_message(session_id, {"role": "user", "content": user_message})
                await self._conv.append_message(session_id, {"role": "assistant", "content": response_content})

                duration = time.time() - start_time
                metrics.observe_histogram("conversation_duration", duration * 1000)
                metrics.inc_counter("conversation_completed", {"project_id": project_id})
                logger.info("conversation_completed", project_id=project_id, duration_ms=int(duration * 1000), loops=loop_count)
                completed = True
                break
            if not completed:
                fallback = "达到最大处理轮次，已停止生成。"
                guard_payload = _build_guard_event_payload(
                    reason="max_loops",
                    message=f"达到最大处理轮次（已执行 {loop_count} 轮，当前上限 {self._max_loops} 轮）。",
                    details={
                        "loop_count": loop_count,
                        "max_loops": self._max_loops,
                        "tool_rounds": tool_rounds,
                    },
                )
                yield _build_done_payload(
                    content=fallback,
                    artifacts=collected_artifacts,
                    project_id=project_id,
                    username=username,
                    chat_session_id=chat_session_id,
                    successful_tool_names=successful_tool_names,
                    task_tree_tool_used=task_tree_tool_used,
                    completed_reason="max_loops",
                    guard_payload=guard_payload,
                )
                await self._conv.append_message(session_id, {"role": "user", "content": user_message})
                await self._conv.append_message(session_id, {"role": "assistant", "content": fallback})
                duration = time.time() - start_time
                metrics.observe_histogram("conversation_duration", duration * 1000)
                metrics.inc_counter("conversation_completed", {"project_id": project_id})
                logger.info("conversation_completed", project_id=project_id, duration_ms=int(duration * 1000), loops=loop_count, reason="max_loops")
        except Exception as e:
            metrics.inc_counter("conversation_error", {"reason": "exception"})
            logger.error("conversation_failed", error=str(e))
            raise

    def _format_tools(self, tools: list[dict]) -> list[dict]:
        return [{"type": "function", "function": {"name": t["tool_name"], "description": t.get("description", ""), "parameters": t.get("parameters_schema", {"type": "object", "properties": {}})}} for t in tools]

    async def _try_finalize_without_tools(
        self,
        *,
        provider_id: str,
        model_name: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        guard_message: str = "",
    ) -> str:
        """在工具循环触发保护条件时，尝试基于已有上下文直接产出最终答案。"""
        try:
            normalized_guard_message = str(guard_message or "").strip()
            finalize_instruction = (
                "请基于当前已有上下文与工具结果，直接输出最终答案。"
                "不要再发起任何工具调用；若信息不足，明确指出缺失项并给出最小下一步。"
            )
            if normalized_guard_message:
                finalize_instruction += (
                    f" 当前系统停止继续调用工具的原因：{normalized_guard_message}。"
                    "不要写“我不能再发起工具调用”或“当前轮被限制”这类内部视角表述，"
                    "只输出面向用户的结论，并在末尾用一句话简要说明本轮停止原因。"
                )
            finalize_messages = list(messages)
            finalize_messages.append(
                {
                    "role": "system",
                    "content": finalize_instruction,
                }
            )
            result = await self._llm.chat_completion(
                provider_id=provider_id,
                model_name=model_name,
                messages=finalize_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=60,
            )
            return str(result.get("content") or "").strip()
        except Exception:
            return ""

    async def _resolve_guard_fallback(
        self,
        *,
        provider_id: str,
        model_name: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        default_message: str,
        guard_message: str = "",
    ) -> str:
        if self._tool_budget_strategy == "finalize":
            final_answer = await self._try_finalize_without_tools(
                provider_id=provider_id,
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                guard_message=guard_message,
            )
            if final_answer:
                return final_answer
        return default_message
