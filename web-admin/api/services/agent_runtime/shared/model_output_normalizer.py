"""Normalize model text output before it reaches users or completion gates."""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime.shared.tool_calls import CollectedToolCall


_DSML = r"\uff5c\uff5cDSML\uff5c\uff5c"
_DSML_TOOL_CALLS_RE = re.compile(
    rf"<{_DSML}tool_calls\b[^>]*>.*?</{_DSML}tool_calls>",
    re.DOTALL | re.IGNORECASE,
)
_DSML_INVOKE_RE = re.compile(
    rf"<{_DSML}invoke\b(?P<attrs>[^>]*)>(?P<body>.*?)</{_DSML}invoke>",
    re.DOTALL | re.IGNORECASE,
)
_DSML_PARAMETER_RE = re.compile(
    rf"<{_DSML}parameter\b(?P<attrs>[^>]*)>(?P<body>.*?)</{_DSML}parameter>",
    re.DOTALL | re.IGNORECASE,
)
_ATTR_RE = re.compile(r"([A-Za-z_][\w:-]*)\s*=\s*(['\"])(.*?)\2", re.DOTALL)
_TOOL_XML_RE = re.compile(
    r"<(?P<tag>tool_call|tool_calls|function_call|function_calls)\b[^>]*>"
    r"(?P<body>.*?)"
    r"</(?P=tag)>",
    re.DOTALL | re.IGNORECASE,
)
_FUNCTION_XML_RE = re.compile(
    r"(?:(?<=^)|(?<=[\n\r.!?:]))[ \t]*"
    r"<function\b(?P<attrs>[^>]*)>"
    r"(?P<body>.*?)"
    r"</function>",
    re.DOTALL | re.IGNORECASE,
)
_HARMONY_TOOL_LEAK_RE = re.compile(
    r"(?:^|[\s>|])to=functions\.[A-Za-z_][\w.]*",
    re.IGNORECASE,
)
_HARMONY_TOOL_CALL_RE = re.compile(
    r"(?:assistant\s+)?to=functions\.(?P<name>[A-Za-z_][\w.]*)\s*(?P<arguments>\{.*?\})\s*$",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class StrippedProtocolBlock:
    kind: str
    char_length: int
    parsed_tool_call_count: int = 0
    tool_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "char_length": self.char_length,
            "parsed_tool_call_count": self.parsed_tool_call_count,
            "tool_names": list(self.tool_names),
        }


@dataclass
class ModelOutputNormalizationResult:
    raw_content: str
    visible_content: str
    tool_calls: list[CollectedToolCall] = field(default_factory=list)
    parsed_tool_calls: list[CollectedToolCall] = field(default_factory=list)
    stripped_protocol_blocks: list[StrippedProtocolBlock] = field(default_factory=list)
    leak_detected: bool = False
    leak_kinds: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)

    @property
    def parsed_text_tool_call_count(self) -> int:
        return len(self.parsed_tool_calls)

    @property
    def stripped_protocol_block_count(self) -> int:
        return len(self.stripped_protocol_blocks)

    def has_changes(self) -> bool:
        return (
            self.visible_content != self.raw_content
            or bool(self.parsed_tool_calls)
            or bool(self.stripped_protocol_blocks)
            or bool(self.leak_detected)
            or bool(self.parse_errors)
        )

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "raw_content_length": len(self.raw_content),
            "visible_content_length": len(self.visible_content),
            "parsed_text_tool_call_count": self.parsed_text_tool_call_count,
            "stripped_protocol_block_count": self.stripped_protocol_block_count,
            "leak_detected": self.leak_detected,
            "leak_kinds": list(self.leak_kinds),
            "parse_errors": list(self.parse_errors),
            "stripped_protocol_blocks": [
                item.to_dict() for item in self.stripped_protocol_blocks
            ],
        }

    def to_transcript_payload(self) -> dict[str, Any]:
        return {
            **self.to_event_payload(),
            "raw_content": self.raw_content,
            "visible_content": self.visible_content,
            "parsed_tool_calls": [item.to_dict() for item in self.parsed_tool_calls],
        }


def normalize_model_output(
    *,
    content: str,
    structured_tool_calls: list[CollectedToolCall] | None = None,
    allowed_tool_names: set[str] | list[str] | tuple[str, ...] | None = None,
    max_tool_calls: int | None = None,
) -> ModelOutputNormalizationResult:
    raw_content = str(content or "")
    visible_content = raw_content
    structured_calls = list(structured_tool_calls or [])
    allowed = {
        str(item or "").strip()
        for item in (allowed_tool_names or [])
        if str(item or "").strip()
    }
    parsed_calls: list[CollectedToolCall] = []
    stripped_blocks: list[StrippedProtocolBlock] = []
    parse_errors: list[str] = []
    leak_kinds: list[str] = []

    visible_content, dsml_calls, dsml_blocks, dsml_errors = _consume_dsml_blocks(
        visible_content,
        allowed_tool_names=allowed,
    )
    parsed_calls.extend(dsml_calls)
    stripped_blocks.extend(dsml_blocks)
    parse_errors.extend(dsml_errors)
    if dsml_blocks:
        leak_kinds.append("dsml_tool_calls")

    visible_content, xml_calls, xml_blocks, xml_errors = _consume_xml_tool_blocks(
        visible_content,
        allowed_tool_names=allowed,
    )
    parsed_calls.extend(xml_calls)
    stripped_blocks.extend(xml_blocks)
    parse_errors.extend(xml_errors)
    if xml_blocks:
        leak_kinds.append("xml_tool_calls")

    visible_content, harmony_calls, harmony_blocks, harmony_errors = _consume_harmony_tool_calls(
        visible_content,
        allowed_tool_names=allowed,
    )
    parsed_calls.extend(harmony_calls)
    stripped_blocks.extend(harmony_blocks)
    parse_errors.extend(harmony_errors)
    if harmony_blocks:
        leak_kinds.append("harmony_tool_call")
    elif _HARMONY_TOOL_LEAK_RE.search(visible_content):
        leak_kinds.append("harmony_tool_call")
        visible_content = _strip_harmony_tool_leak_tail(visible_content)

    visible_content = _cleanup_visible_content(visible_content)
    combined_calls = _limit_tool_calls(
        [*structured_calls, *parsed_calls],
        max_tool_calls=max_tool_calls,
    )
    if max_tool_calls is not None:
        allowed_parsed_total = max(0, int(max_tool_calls) - len(structured_calls))
        parsed_calls = parsed_calls[:allowed_parsed_total]
    return ModelOutputNormalizationResult(
        raw_content=raw_content,
        visible_content=visible_content,
        tool_calls=combined_calls,
        parsed_tool_calls=parsed_calls,
        stripped_protocol_blocks=stripped_blocks,
        leak_detected=bool(leak_kinds or stripped_blocks or parse_errors),
        leak_kinds=_dedupe(leak_kinds),
        parse_errors=parse_errors,
    )


def _consume_dsml_blocks(
    content: str,
    *,
    allowed_tool_names: set[str],
) -> tuple[str, list[CollectedToolCall], list[StrippedProtocolBlock], list[str]]:
    calls: list[CollectedToolCall] = []
    blocks: list[StrippedProtocolBlock] = []
    errors: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        block = match.group(0)
        block_calls: list[CollectedToolCall] = []
        block_tool_names: list[str] = []
        for invoke in _DSML_INVOKE_RE.finditer(block):
            attrs = _parse_attrs(invoke.group("attrs"))
            tool_name = str(attrs.get("name") or "").strip()
            if not tool_name:
                errors.append("dsml_invoke_missing_name")
                continue
            if not _is_allowed_tool(tool_name, allowed_tool_names):
                errors.append(f"dsml_tool_not_allowed:{tool_name}")
                continue
            arguments: dict[str, Any] = {}
            for parameter in _DSML_PARAMETER_RE.finditer(invoke.group("body")):
                param_attrs = _parse_attrs(parameter.group("attrs"))
                param_name = str(param_attrs.get("name") or "").strip()
                if not param_name:
                    errors.append(f"dsml_parameter_missing_name:{tool_name}")
                    continue
                arguments[param_name] = _coerce_dsml_parameter(
                    parameter.group("body"),
                    param_attrs,
                )
            block_calls.append(_collected_text_tool_call(tool_name, arguments, "dsml"))
            block_tool_names.append(tool_name)
        calls.extend(block_calls)
        blocks.append(
            StrippedProtocolBlock(
                kind="dsml_tool_calls",
                char_length=len(block),
                parsed_tool_call_count=len(block_calls),
                tool_names=block_tool_names,
            )
        )
        return ""

    cleaned = _DSML_TOOL_CALLS_RE.sub(_replace, content)
    return cleaned, calls, blocks, errors


def _consume_xml_tool_blocks(
    content: str,
    *,
    allowed_tool_names: set[str],
) -> tuple[str, list[CollectedToolCall], list[StrippedProtocolBlock], list[str]]:
    calls: list[CollectedToolCall] = []
    blocks: list[StrippedProtocolBlock] = []
    errors: list[str] = []

    def _replace_tool(match: re.Match[str]) -> str:
        block = match.group(0)
        tag = str(match.group("tag") or "tool_call").lower()
        block_calls, block_errors = _parse_json_tool_call_body(
            match.group("body"),
            allowed_tool_names=allowed_tool_names,
            source=f"xml_{tag}",
        )
        calls.extend(block_calls)
        errors.extend(block_errors)
        blocks.append(
            StrippedProtocolBlock(
                kind=f"xml_{tag}",
                char_length=len(block),
                parsed_tool_call_count=len(block_calls),
                tool_names=[item.tool_name for item in block_calls],
            )
        )
        return ""

    cleaned = _TOOL_XML_RE.sub(_replace_tool, content)

    def _replace_function(match: re.Match[str]) -> str:
        attrs = _parse_attrs(match.group("attrs"))
        tool_name = str(attrs.get("name") or "").strip()
        if not tool_name:
            return match.group(0)
        block = match.group(0)
        block_calls: list[CollectedToolCall] = []
        if _is_allowed_tool(tool_name, allowed_tool_names):
            body = html.unescape(str(match.group("body") or "").strip())
            arguments = _parse_json_object(body) if body else {}
            if arguments is None:
                arguments = {"input": body}
            block_calls.append(_collected_text_tool_call(tool_name, arguments, "xml_function"))
        else:
            errors.append(f"xml_function_tool_not_allowed:{tool_name}")
        calls.extend(block_calls)
        blocks.append(
            StrippedProtocolBlock(
                kind="xml_function",
                char_length=len(block),
                parsed_tool_call_count=len(block_calls),
                tool_names=[item.tool_name for item in block_calls],
            )
        )
        return ""

    cleaned = _FUNCTION_XML_RE.sub(_replace_function, cleaned)
    return cleaned, calls, blocks, errors


def _parse_json_tool_call_body(
    body: str,
    *,
    allowed_tool_names: set[str],
    source: str,
) -> tuple[list[CollectedToolCall], list[str]]:
    text = html.unescape(str(body or "").strip())
    if not text:
        return [], [f"{source}_empty_body"]
    payload = _parse_json_value(text)
    if payload is None:
        return [], [f"{source}_invalid_json"]
    items = payload if isinstance(payload, list) else [payload]
    calls: list[CollectedToolCall] = []
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            errors.append(f"{source}_non_object_call")
            continue
        parsed = _tool_call_from_mapping(item, allowed_tool_names, source)
        if isinstance(parsed, CollectedToolCall):
            calls.append(parsed)
        else:
            errors.append(parsed)
    return calls, errors


def _tool_call_from_mapping(
    payload: dict[str, Any],
    allowed_tool_names: set[str],
    source: str,
) -> CollectedToolCall | str:
    function = payload.get("function") if isinstance(payload.get("function"), dict) else {}
    tool_name = str(
        payload.get("tool_name")
        or payload.get("name")
        or function.get("name")
        or ""
    ).strip()
    if not tool_name:
        return f"{source}_missing_tool_name"
    if not _is_allowed_tool(tool_name, allowed_tool_names):
        return f"{source}_tool_not_allowed:{tool_name}"
    raw_arguments = (
        payload.get("arguments")
        if "arguments" in payload
        else function.get("arguments")
    )
    if isinstance(raw_arguments, str):
        parsed_arguments = _parse_json_object(raw_arguments)
        arguments = parsed_arguments if parsed_arguments is not None else {"input": raw_arguments}
    elif isinstance(raw_arguments, dict):
        arguments = raw_arguments
    elif raw_arguments is None:
        arguments = {}
    else:
        arguments = {"input": raw_arguments}
    return _collected_text_tool_call(tool_name, arguments, source)


def _parse_attrs(raw_attrs: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(str(raw_attrs or "")):
        attrs[str(match.group(1)).strip()] = html.unescape(str(match.group(3) or ""))
    return attrs


def _coerce_dsml_parameter(raw_value: str, attrs: dict[str, str]) -> Any:
    text = html.unescape(str(raw_value or "").strip())
    if str(attrs.get("string") or "").strip().lower() == "true":
        return text
    parsed = _parse_json_value(text)
    if parsed is not None:
        return parsed
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        pass
    try:
        return float(text)
    except (TypeError, ValueError):
        return text


def _parse_json_object(value: str) -> dict[str, Any] | None:
    parsed = _parse_json_value(value)
    return parsed if isinstance(parsed, dict) else None


def _parse_json_value(value: str) -> Any:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _is_allowed_tool(tool_name: str, allowed_tool_names: set[str]) -> bool:
    return bool(allowed_tool_names) and tool_name in allowed_tool_names


def _collected_text_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    source: str,
) -> CollectedToolCall:
    arguments_text = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
    seed = f"{source}:{tool_name}:{arguments_text}"
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:12]
    call_id = f"call_text_{digest}"
    return CollectedToolCall(
        call_id=call_id,
        tool_name=tool_name,
        arguments=arguments_text,
        raw={
            "id": call_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": arguments_text,
            },
            "source": source,
        },
    )


def _strip_harmony_tool_leak_tail(content: str) -> str:
    match = _HARMONY_TOOL_LEAK_RE.search(content)
    if not match:
        return content
    prefix = content[: match.start()].rstrip()
    if prefix.strip().lower() in {"assistant", "commentary", "<|channel|>commentary"}:
        return ""
    return prefix


def _consume_harmony_tool_calls(
    content: str,
    *,
    allowed_tool_names: set[str],
) -> tuple[str, list[CollectedToolCall], list[StrippedProtocolBlock], list[str]]:
    match = _HARMONY_TOOL_CALL_RE.search(str(content or ""))
    if not match:
        return content, [], [], []
    block = match.group(0)
    tool_name = str(match.group("name") or "").strip()
    calls: list[CollectedToolCall] = []
    errors: list[str] = []
    if not _is_allowed_tool(tool_name, allowed_tool_names):
        errors.append(f"harmony_tool_not_allowed:{tool_name}")
    else:
        arguments = _parse_json_object(match.group("arguments"))
        if arguments is None:
            errors.append(f"harmony_tool_invalid_json:{tool_name}")
        else:
            calls.append(_collected_text_tool_call(tool_name, arguments, "harmony"))
    blocks = [
        StrippedProtocolBlock(
            kind="harmony_tool_call",
            char_length=len(block),
            parsed_tool_call_count=len(calls),
            tool_names=[tool_name] if tool_name else [],
        )
    ]
    prefix = content[: match.start()].rstrip()
    if prefix.strip().lower() in {"assistant", "commentary", "<|channel|>commentary"}:
        prefix = ""
    return prefix, calls, blocks, errors


def _cleanup_visible_content(content: str) -> str:
    lines = [line.rstrip() for line in str(content or "").splitlines()]
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _limit_tool_calls(
    calls: list[CollectedToolCall],
    *,
    max_tool_calls: int | None,
) -> list[CollectedToolCall]:
    if max_tool_calls is None:
        return calls
    if int(max_tool_calls) <= 0:
        return []
    return calls[: max(1, int(max_tool_calls))]


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output
