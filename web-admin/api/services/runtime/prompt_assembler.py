"""Minimal shared prompt assembly helpers."""

from __future__ import annotations

from typing import Any, Callable

from core.deps import system_config_store


def resolve_chat_style_hints(
    answer_style: str = "concise",
    *,
    prefer_conclusion_first: bool = True,
) -> tuple[str, str]:
    normalized_style = str(answer_style or "concise").strip().lower() or "concise"
    config = system_config_store.get_global()
    style_hints = getattr(config, "chat_style_hints", {}) or {}
    selected = style_hints.get(normalized_style) if isinstance(style_hints, dict) else None
    if not isinstance(selected, dict):
        selected = (
            style_hints.get("concise")
            if isinstance(style_hints, dict) and isinstance(style_hints.get("concise"), dict)
            else {}
        )
    style_hint = str(selected.get("style_hint") or "输出风格：简洁，避免冗长。").strip()
    default_order_hint = str(selected.get("order_hint") or "回答顺序：先给结论再给步骤。").strip()
    order_hint = default_order_hint if prefer_conclusion_first else "回答顺序：按自然推理顺序给出。"
    return style_hint, order_hint


def join_prompt_sections(*sections: str) -> str:
    normalized = [str(section or "").strip() for section in sections if str(section or "").strip()]
    return "\n\n".join(normalized)


def assemble_chat_messages(
    *,
    system_messages: list[str],
    history: list[dict] | None,
    user_message: str,
    images: list[str] | None,
    history_limit: int,
    normalize_history: Callable[..., list[dict[str, Any]]],
    normalize_images: Callable[[list[str] | None], list[str]],
    image_fallback_text: str = "请基于图片给建议。",
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": content}
        for content in system_messages
        if str(content or "").strip()
    ]
    messages.extend(normalize_history(history, limit=history_limit))
    normalized_images = normalize_images(images)
    if normalized_images:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": user_message or image_fallback_text}
        ]
        for image_url in normalized_images:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
        messages.append({"role": "user", "content": content})
        return messages
    messages.append({"role": "user", "content": user_message})
    return messages
