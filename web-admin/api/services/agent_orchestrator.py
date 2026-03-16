from __future__ import annotations
import asyncio
import json
import time
from typing import Any, AsyncGenerator
from services.conversation_manager import ConversationManager
from services.tool_executor import ToolExecutor
from core.observability import logger, metrics

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

            while loop_count < self._max_loops:
                if cancel_event.is_set():
                    yield {"type": "done", "content": "[已停止]"}
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
                        yield {"type": "done", "content": fallback}
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
                        yield {"type": "done", "content": fallback}
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
                        yield {"type": "done", "content": fallback}
                        await self._conv.append_message(session_id, {"role": "user", "content": user_message})
                        await self._conv.append_message(session_id, {"role": "assistant", "content": fallback})
                        duration = time.time() - start_time
                        metrics.observe_histogram("conversation_duration", duration * 1000)
                        metrics.inc_counter("conversation_completed", {"project_id": project_id})
                        logger.info("conversation_completed", project_id=project_id, duration_ms=int(duration * 1000), loops=loop_count, reason="tool_only_loops")
                        completed = True
                        break
                    continue

                yield {"type": "done", "content": response_content}
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
                yield {"type": "done", "content": fallback}
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
