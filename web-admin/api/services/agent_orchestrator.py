from __future__ import annotations
import asyncio
import json
import re
import time
from typing import Any, AsyncGenerator
from services.conversation_manager import ConversationManager
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
        messages: list[dict] | None = None,
        local_connector: Any | None = None,
        local_connector_workspace_path: str = "",
        local_connector_sandbox_mode: str = "workspace-write",
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
                timeout_sec=self._tool_timeout_sec,
                max_retries=self._tool_retry_count,
                local_connector=local_connector,
                local_connector_workspace_path=local_connector_workspace_path,
                local_connector_sandbox_mode=local_connector_sandbox_mode,
            )
            loop_count = 0
            completed = False
            tool_only_loops = 0
            tool_rounds = 0
            last_tool_signature = ""
            repeated_tool_signature_rounds = 0
            collected_artifacts: list[dict[str, Any]] = []

            while loop_count < self._max_loops:
                if cancel_event.is_set():
                    yield {
                        "type": "done",
                        "content": "[已停止]",
                        "artifacts": collected_artifacts,
                        "images": _collect_artifact_urls(collected_artifacts, asset_type="image"),
                        "videos": _collect_artifact_urls(collected_artifacts, asset_type="video"),
                    }
                    completed = True
                    break

                loop_count += 1
                response_content = ""
                tool_calls_buffer = {}

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

                logger.info("agent_loop_response", has_tool_calls=bool(tool_calls_buffer), response_length=len(response_content))

                if tool_calls_buffer:
                    tool_rounds += 1
                    ordered_tool_calls = list(tool_calls_buffer.values())
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
                        fallback = await self._resolve_guard_fallback(
                            provider_id=provider_id,
                            model_name=model_name,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            default_message="工具调用已达到预算上限，已停止生成。请补充更明确的参数后重试。",
                        )
                        yield {
                            "type": "done",
                            "content": fallback,
                            "artifacts": collected_artifacts,
                            "images": _collect_artifact_urls(collected_artifacts, asset_type="image"),
                            "videos": _collect_artifact_urls(collected_artifacts, asset_type="video"),
                        }
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
                        fallback = await self._resolve_guard_fallback(
                            provider_id=provider_id,
                            model_name=model_name,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            default_message="检测到重复工具调用且未产出正文，已停止生成。请调整问题或补充参数后重试。",
                        )
                        yield {
                            "type": "done",
                            "content": fallback,
                            "artifacts": collected_artifacts,
                            "images": _collect_artifact_urls(collected_artifacts, asset_type="image"),
                            "videos": _collect_artifact_urls(collected_artifacts, asset_type="video"),
                        }
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

                    if not str(response_content or "").strip():
                        tool_only_loops += 1
                    else:
                        tool_only_loops = 0
                    messages.append({"role": "assistant", "content": response_content or None, "tool_calls": ordered_tool_calls})

                    for tc in ordered_tool_calls:
                        yield {
                            "type": "tool_start",
                            "tool_name": str((tc.get("function") or {}).get("name") or "tool"),
                        }
                    tool_start = time.time()
                    tool_results = await tool_executor.execute_parallel(ordered_tool_calls)
                    tool_duration = time.time() - tool_start

                    metrics.observe_histogram("tool_execution_duration", tool_duration * 1000)
                    metrics.inc_counter("tool_calls_total", {"count": len(ordered_tool_calls)})

                    for tc, result in zip(ordered_tool_calls, tool_results):
                        if isinstance(result, Exception):
                            result = {"error": str(result)}
                        tool_name = tc["function"]["name"]
                        success = "error" not in result
                        metrics.inc_counter("tool_call", {"tool": tool_name, "status": "success" if success else "error"})
                        yield {
                            "type": "tool_result",
                            "tool_name": tool_name,
                            "status": "success" if success else "error",
                            "output_preview": _preview_tool_result(result),
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
                    if tool_only_loops >= self._tool_only_threshold:
                        fallback = await self._resolve_guard_fallback(
                            provider_id=provider_id,
                            model_name=model_name,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            default_message="工具调用连续多轮未产出正文，已停止生成。请补充更明确的参数后重试。",
                        )
                        yield {
                            "type": "done",
                            "content": fallback,
                            "artifacts": collected_artifacts,
                            "images": _collect_artifact_urls(collected_artifacts, asset_type="image"),
                            "videos": _collect_artifact_urls(collected_artifacts, asset_type="video"),
                        }
                        await self._conv.append_message(session_id, {"role": "user", "content": user_message})
                        await self._conv.append_message(session_id, {"role": "assistant", "content": fallback})
                        duration = time.time() - start_time
                        metrics.observe_histogram("conversation_duration", duration * 1000)
                        metrics.inc_counter("conversation_completed", {"project_id": project_id})
                        logger.info("conversation_completed", project_id=project_id, duration_ms=int(duration * 1000), loops=loop_count, reason="tool_only_loops")
                        completed = True
                        break
                    continue

                yield {
                    "type": "done",
                    "content": response_content,
                    "artifacts": collected_artifacts,
                    "images": _collect_artifact_urls(collected_artifacts, asset_type="image"),
                    "videos": _collect_artifact_urls(collected_artifacts, asset_type="video"),
                }
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
                yield {
                    "type": "done",
                    "content": fallback,
                    "artifacts": collected_artifacts,
                    "images": _collect_artifact_urls(collected_artifacts, asset_type="image"),
                    "videos": _collect_artifact_urls(collected_artifacts, asset_type="video"),
                }
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
    ) -> str:
        """在工具循环触发保护条件时，尝试基于已有上下文直接产出最终答案。"""
        try:
            finalize_messages = list(messages)
            finalize_messages.append(
                {
                    "role": "system",
                    "content": (
                        "请基于当前已有上下文与工具结果，直接输出最终答案。"
                        "不要再发起任何工具调用；若信息不足，明确指出缺失项并给出最小下一步。"
                    ),
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
    ) -> str:
        if self._tool_budget_strategy == "finalize":
            final_answer = await self._try_finalize_without_tools(
                provider_id=provider_id,
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if final_answer:
                return final_answer
        return default_message
