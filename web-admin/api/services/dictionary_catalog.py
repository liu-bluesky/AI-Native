"""Central static dictionary registry for backend and frontend option lists."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from stores.factory import system_config_store

_DICTIONARY_REGISTRY: dict[str, dict[str, Any]] = {
    "llm_model_types": {
        "key": "llm_model_types",
        "label": "模型类型",
        "description": "用于区分模型能力，并驱动不同的参数面板与交互逻辑。",
        "default_value": "text_generation",
        "options": [
            {
                "id": "text_generation",
                "label": "文本生成",
                "description": "适合问答、写作、代码与通用对话。",
                "chat_parameter_mode": "text",
            },
            {
                "id": "multimodal_chat",
                "label": "多模态对话",
                "description": "支持图文理解和通用对话，参数面板沿用文本模式。",
                "chat_parameter_mode": "text",
            },
            {
                "id": "image_generation",
                "label": "图片生成",
                "description": "适合根据提示词或参考图生成图片。",
                "chat_parameter_mode": "image",
            },
            {
                "id": "video_generation",
                "label": "视频生成",
                "description": "适合生成短视频或动画片段。",
                "chat_parameter_mode": "video",
            },
            {
                "id": "audio_generation",
                "label": "音频生成",
                "description": "适合语音、配音或音频内容生成。",
                "chat_parameter_mode": "text",
            },
            {
                "id": "audio_transcription",
                "label": "音频转写",
                "description": "适合语音识别、语音转文本与实时转写场景。",
                "chat_parameter_mode": "text",
            },
        ],
    },
    "llm_image_resolutions": {
        "key": "llm_image_resolutions",
        "label": "图片分辨率",
        "description": "图片生成模型可选的默认分辨率预设。",
        "default_value": "1080x1080",
        "options": [
            {
                "id": "720x720",
                "label": "720x720",
                "description": "固定尺寸基准值，后端会结合当前图片比例自动换算最终尺寸。",
            },
            {
                "id": "1080x1080",
                "label": "1080x1080",
                "description": "固定尺寸基准值，后端会结合当前图片比例自动换算最终尺寸。",
            },
            {
                "id": "2160x2160",
                "label": "2160x2160",
                "description": "固定尺寸基准值，后端会结合当前图片比例自动换算最终尺寸。",
            },
        ],
    },
    "llm_image_aspect_ratios": {
        "key": "llm_image_aspect_ratios",
        "label": "图片比例",
        "description": "图片生成模型的画幅比例预设。",
        "default_value": "1:1",
        "options": [
            {"id": "1:1", "label": "1:1 方图", "description": "适合头像、电商主图和通用素材。"},
            {"id": "3:4", "label": "3:4 竖构图", "description": "适合人物写真、海报卡片。"},
            {"id": "4:3", "label": "4:3 横构图", "description": "适合展示图和通用横版画面。"},
            {"id": "9:16", "label": "9:16 竖屏", "description": "适合手机竖屏封面、短视频封面。"},
            {"id": "16:9", "label": "16:9 横屏", "description": "适合横版宣传图、宽屏头图。"},
        ],
    },
    "llm_image_styles": {
        "key": "llm_image_styles",
        "label": "图片风格",
        "description": "图片生成模型的风格倾向预设。",
        "default_value": "auto",
        "options": [
            {"id": "auto", "label": "自动", "description": "由模型根据提示词自行判断最适合的风格。"},
            {"id": "realistic", "label": "写实", "description": "逼近真实摄影和写实光影效果。"},
            {"id": "illustration", "label": "插画", "description": "适合插画、概念图和视觉创意场景。"},
        ],
    },
    "llm_image_qualities": {
        "key": "llm_image_qualities",
        "label": "图片质量",
        "description": "图片生成模型的质量档位预设。",
        "default_value": "high",
        "options": [
            {"id": "standard", "label": "标准", "description": "生成更快，适合草稿和快速尝试。"},
            {"id": "high", "label": "高质量", "description": "细节更多，适合正式出图。"},
        ],
    },
    "llm_video_aspect_ratios": {
        "key": "llm_video_aspect_ratios",
        "label": "视频比例",
        "description": "视频生成模型的画幅比例预设。",
        "default_value": "16:9",
        "options": [
            {"id": "1:1", "label": "1:1 方图", "description": "适合方形信息流和封面视频。"},
            {"id": "9:16", "label": "9:16 竖屏", "description": "适合短视频、手机竖屏播放。"},
            {"id": "16:9", "label": "16:9 横屏", "description": "适合横版宣传片和宽屏内容。"},
        ],
    },
    "llm_video_styles": {
        "key": "llm_video_styles",
        "label": "视频风格",
        "description": "视频生成模型的风格倾向预设。",
        "default_value": "cinematic",
        "options": [
            {"id": "cinematic", "label": "电影感", "description": "强调镜头语言和氛围质感。"},
            {"id": "realistic", "label": "写实", "description": "更接近真实拍摄和生活场景。"},
            {"id": "animation", "label": "动画", "description": "适合动画感和风格化视频。"},
        ],
    },
    "llm_video_duration_seconds": {
        "key": "llm_video_duration_seconds",
        "label": "视频时长",
        "description": "视频生成模型的默认时长预设，单位为秒。",
        "default_value": "5",
        "options": [
            {"id": "5", "label": "5 秒", "description": "快速试片和短节奏镜头。"},
            {"id": "10", "label": "10 秒", "description": "兼顾信息量和生成速度。"},
            {"id": "15", "label": "15 秒", "description": "适合剧情更完整的短片段。"},
        ],
    },
    "llm_video_motion_strengths": {
        "key": "llm_video_motion_strengths",
        "label": "动作强度",
        "description": "视频生成模型的镜头和动作动态程度预设。",
        "default_value": "medium",
        "options": [
            {"id": "low", "label": "低", "description": "镜头更稳，适合静态场景。"},
            {"id": "medium", "label": "中", "description": "兼顾稳定性和动态表现。"},
            {"id": "high", "label": "高", "description": "动作更强，适合运动和冲击感画面。"},
        ],
    },
}

_DICTIONARY_USAGE_REGISTRY: dict[str, list[dict[str, str]]] = {
    "llm_model_types": [
        {
            "id": "llm.providers",
            "label": "模型供应商管理",
            "route": "/llm/providers",
            "description": "决定供应商模型属于文本、图片还是视频能力类型。",
        },
        {
            "id": "projects.chat",
            "label": "AI 对话参数面板",
            "route": "/projects/chat",
            "description": "根据模型类型切换文本、图片和视频参数面板。",
        },
    ],
    "llm_image_resolutions": [
        {
            "id": "projects.chat.image_resolution",
            "label": "AI 对话 · 图片参数",
            "route": "/projects/chat",
            "description": "控制图片生成的分辨率选项和默认值。",
        }
    ],
    "llm_image_aspect_ratios": [
        {
            "id": "projects.chat.image_aspect_ratio",
            "label": "AI 对话 · 图片参数",
            "route": "/projects/chat",
            "description": "控制图片生成的画幅比例选项和默认值。",
        }
    ],
    "llm_image_styles": [
        {
            "id": "projects.chat.image_style",
            "label": "AI 对话 · 图片参数",
            "route": "/projects/chat",
            "description": "控制图片生成的风格预设和默认值。",
        }
    ],
    "llm_image_qualities": [
        {
            "id": "projects.chat.image_quality",
            "label": "AI 对话 · 图片参数",
            "route": "/projects/chat",
            "description": "控制图片生成的质量档位和默认值。",
        }
    ],
    "llm_video_aspect_ratios": [
        {
            "id": "projects.chat.video_aspect_ratio",
            "label": "AI 对话 · 视频参数",
            "route": "/projects/chat",
            "description": "控制视频生成的画幅比例选项和默认值。",
        }
    ],
    "llm_video_styles": [
        {
            "id": "projects.chat.video_style",
            "label": "AI 对话 · 视频参数",
            "route": "/projects/chat",
            "description": "控制视频生成的风格预设和默认值。",
        }
    ],
    "llm_video_duration_seconds": [
        {
            "id": "projects.chat.video_duration_seconds",
            "label": "AI 对话 · 视频参数",
            "route": "/projects/chat",
            "description": "控制视频生成的时长选项和默认值。",
        }
    ],
    "llm_video_motion_strengths": [
        {
            "id": "projects.chat.video_motion_strength",
            "label": "AI 对话 · 视频参数",
            "route": "/projects/chat",
            "description": "控制视频生成的动作强度选项和默认值。",
        }
    ],
}


def has_builtin_dictionary(dictionary_key: str) -> bool:
    key = str(dictionary_key or "").strip()
    return bool(key) and key in _DICTIONARY_REGISTRY


def _dictionary_usage_refs(dictionary_key: str) -> list[dict[str, str]]:
    key = str(dictionary_key or "").strip()
    refs = _DICTIONARY_USAGE_REGISTRY.get(key)
    if not isinstance(refs, list):
        return []
    return [dict(item) for item in refs if isinstance(item, dict)]


def _normalize_dictionary_definition(
    raw: dict[str, Any],
    *,
    fallback_key: str,
    builtin: bool,
) -> dict[str, Any]:
    key = str(raw.get("key") or fallback_key).strip() or fallback_key
    options = raw.get("options") if isinstance(raw.get("options"), list) else []
    return {
        "key": key,
        "label": str(raw.get("label") or "").strip(),
        "description": str(raw.get("description") or "").strip(),
        "default_value": raw.get("default_value"),
        "options": [dict(item) for item in options if isinstance(item, dict)],
        "usage_refs": _dictionary_usage_refs(key),
        "builtin": builtin,
    }


def get_builtin_dictionary_definition(dictionary_key: str) -> dict[str, Any] | None:
    key = str(dictionary_key or "").strip()
    raw = _DICTIONARY_REGISTRY.get(key)
    if not isinstance(raw, dict):
        return None
    return _normalize_dictionary_definition(raw, fallback_key=key, builtin=True)


def _dictionary_overrides() -> dict[str, Any]:
    try:
        config = system_config_store.get_global()
    except Exception:
        return {}
    raw = getattr(config, "dictionaries", None)
    return raw if isinstance(raw, dict) else {}


def _merge_dictionary_definition(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(override, dict):
        return deepcopy(base)

    merged = deepcopy(base)
    label = str(override.get("label") or "").strip()
    description = str(override.get("description") or "").strip()
    default_value = str(override.get("default_value") or "").strip()
    options = override.get("options") if isinstance(override.get("options"), list) else None
    if label:
        merged["label"] = label
    if description:
        merged["description"] = description
    if default_value:
        merged["default_value"] = default_value
    if options is not None:
        merged["options"] = [dict(item) for item in options if isinstance(item, dict)]
    return merged


def has_dictionary(dictionary_key: str) -> bool:
    return get_dictionary_definition(dictionary_key) is not None


def get_custom_dictionary_definition(dictionary_key: str) -> dict[str, Any] | None:
    key = str(dictionary_key or "").strip()
    if not key or has_builtin_dictionary(key):
        return None
    override = _dictionary_overrides().get(key)
    if not isinstance(override, dict):
        return None
    return _normalize_dictionary_definition(override, fallback_key=key, builtin=False)


def list_dictionaries() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    overrides = _dictionary_overrides()
    seen_keys: set[str] = set()
    for item in _DICTIONARY_REGISTRY.values():
        key = str(item.get("key") or "").strip()
        definition = _merge_dictionary_definition(get_builtin_dictionary_definition(key) or item, overrides.get(key))
        options = definition.get("options") if isinstance(definition.get("options"), list) else []
        seen_keys.add(str(definition.get("key") or "").strip())
        items.append(
            {
                "key": str(definition.get("key") or "").strip(),
                "label": str(definition.get("label") or "").strip(),
                "description": str(definition.get("description") or "").strip(),
                "default_value": definition.get("default_value"),
                "option_count": len(options),
                "usage_refs": _dictionary_usage_refs(str(definition.get("key") or "").strip()),
                "builtin": True,
            }
        )
    for raw_key, raw in overrides.items():
        key = str(raw_key or "").strip()
        if not key or key in seen_keys or not isinstance(raw, dict):
            continue
        definition = _normalize_dictionary_definition(raw, fallback_key=key, builtin=False)
        options = definition.get("options") if isinstance(definition.get("options"), list) else []
        items.append(
            {
                "key": str(definition.get("key") or "").strip(),
                "label": str(definition.get("label") or "").strip(),
                "description": str(definition.get("description") or "").strip(),
                "default_value": definition.get("default_value"),
                "option_count": len(options),
                "usage_refs": [],
                "builtin": False,
            }
        )
    return items


def get_dictionary_definition(dictionary_key: str) -> dict[str, Any] | None:
    key = str(dictionary_key or "").strip()
    if not key:
        return None
    base = get_builtin_dictionary_definition(key)
    if base is not None:
        override = _dictionary_overrides().get(key)
        return _merge_dictionary_definition(base, override)
    return get_custom_dictionary_definition(key)


def list_dictionary_options(dictionary_key: str) -> list[dict[str, Any]]:
    definition = get_dictionary_definition(dictionary_key) or {}
    options = definition.get("options") if isinstance(definition.get("options"), list) else []
    return [dict(item) for item in options if isinstance(item, dict)]


def get_dictionary_default_value(dictionary_key: str, fallback: Any = "") -> Any:
    definition = get_dictionary_definition(dictionary_key) or {}
    value = definition.get("default_value")
    return fallback if value in (None, "") else value
