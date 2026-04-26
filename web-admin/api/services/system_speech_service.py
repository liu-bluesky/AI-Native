"""System-native speech playback helpers.

This module intentionally plays speech from the API process instead of relying
on browser audio APIs, so bot-triggered events can be announced even when no
browser tab is focused.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from typing import Any

from core.deps import system_config_store
from stores.json.system_config_store import (
    normalize_voice_allowed_role_ids,
    normalize_voice_allowed_usernames,
)

logger = logging.getLogger(__name__)

_SYSTEM_SPEECH_MAX_TEXT_LENGTH = 1200
_DARWIN_SPEECH_VOLUME = 80
_system_speech_queue: asyncio.Queue[dict[str, Any]] | None = None
_system_speech_worker_task: asyncio.Task | None = None


def _normalize_speech_text(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if len(normalized) > _SYSTEM_SPEECH_MAX_TEXT_LENGTH:
        normalized = normalized[: _SYSTEM_SPEECH_MAX_TEXT_LENGTH - 1].rstrip() + "…"
    return normalized


def _role_ids_from_values(values: list[str] | tuple[str, ...] | set[str] | None) -> set[str]:
    return {str(item or "").strip() for item in (values or []) if str(item or "").strip()}


def is_system_speech_allowed(*, owner_username: str = "", role_ids: list[str] | tuple[str, ...] | set[str] | None = None) -> tuple[bool, str]:
    config = system_config_store.get_global()
    if not bool(getattr(config, "voice_output_enabled", False)):
        return False, "系统未开启语音播报"

    allowed_usernames = normalize_voice_allowed_usernames(
        getattr(config, "voice_input_allowed_usernames", [])
    )
    allowed_roles = set(
        normalize_voice_allowed_role_ids(getattr(config, "voice_input_allowed_role_ids", []))
    )
    if not allowed_usernames and not allowed_roles:
        return True, ""

    username = str(owner_username or "").strip().lower()
    normalized_allowed_usernames = {str(item or "").strip().lower() for item in allowed_usernames}
    if username and username in normalized_allowed_usernames:
        return True, ""

    current_roles = _role_ids_from_values(role_ids)
    if current_roles.intersection(allowed_roles):
        return True, ""

    return False, "当前账号未开通全局助手语音"


def _run_osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return str(result.stdout or "").strip()


def _read_darwin_output_state() -> dict[str, Any] | None:
    if not shutil.which("osascript"):
        return None
    try:
        output = _run_osascript(
            'set currentSettings to get volume settings\n'
            'return (output muted of currentSettings as text) & "," & (output volume of currentSettings as text)'
        )
    except Exception:
        logger.exception("failed to read macOS output volume state")
        return None
    muted_raw, _, volume_raw = output.partition(",")
    try:
        volume = int(str(volume_raw or "").strip())
    except ValueError:
        return None
    muted = str(muted_raw or "").strip().lower() == "true"
    return {"muted": muted, "volume": max(0, min(100, volume))}


def _set_darwin_output_state(*, muted: bool | None = None, volume: int | None = None) -> None:
    if not shutil.which("osascript"):
        return
    scripts: list[str] = []
    if volume is not None:
        scripts.append(f"set volume output volume {max(0, min(100, int(volume)))}")
    if muted is not None:
        scripts.append(f"set volume with output muted {str(bool(muted)).lower()}")
    for script in scripts:
        _run_osascript(script)


def _prepare_darwin_output_for_speech(target_volume: int = _DARWIN_SPEECH_VOLUME) -> dict[str, Any] | None:
    state = _read_darwin_output_state()
    if state is None:
        return None
    try:
        _set_darwin_output_state(muted=False, volume=target_volume)
    except Exception:
        logger.exception("failed to prepare macOS output volume for speech")
        return None
    return state


def _restore_darwin_output_state(state: dict[str, Any] | None) -> None:
    if not isinstance(state, dict):
        return
    try:
        _set_darwin_output_state(
            muted=bool(state.get("muted", False)),
            volume=int(state.get("volume", _DARWIN_SPEECH_VOLUME)),
        )
    except Exception:
        logger.exception("failed to restore macOS output volume state")


def _run_native_system_speech_sync(text: str) -> None:
    normalized = _normalize_speech_text(text)
    if not normalized:
        return

    if sys.platform == "darwin":
        binary = shutil.which("say")
        if not binary:
            raise RuntimeError("macOS say 命令不可用")
        previous_output_state = _prepare_darwin_output_for_speech()
        try:
            subprocess.run([binary, normalized], check=True)
        finally:
            _restore_darwin_output_state(previous_output_state)
        return

    if sys.platform.startswith("win"):
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$speaker.Speak([Environment]::GetEnvironmentVariable('AI_EMPLOYEE_SPEECH_TEXT'))"
        )
        env = {**os.environ, "AI_EMPLOYEE_SPEECH_TEXT": normalized}
        subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True, env=env)
        return

    spd_say = shutil.which("spd-say")
    if spd_say:
        subprocess.run([spd_say, normalized], check=True)
        return
    espeak = shutil.which("espeak")
    if espeak:
        subprocess.run([espeak, normalized], check=True)
        return
    raise RuntimeError("当前系统没有可用的后台播报命令（需要 say、spd-say 或 espeak）")


async def _system_speech_worker() -> None:
    global _system_speech_queue
    queue = _system_speech_queue
    if queue is None:
        return
    while True:
        item = await queue.get()
        try:
            text = _normalize_speech_text(str(item.get("text") or ""))
            if text:
                await asyncio.to_thread(_run_native_system_speech_sync, text)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "system speech playback failed",
                extra={"source": str(item.get("source") or "").strip()},
            )
        finally:
            queue.task_done()


def _ensure_system_speech_queue() -> asyncio.Queue[dict[str, Any]]:
    global _system_speech_queue, _system_speech_worker_task
    if _system_speech_queue is None:
        _system_speech_queue = asyncio.Queue(maxsize=50)
    if _system_speech_worker_task is None or _system_speech_worker_task.done():
        _system_speech_worker_task = asyncio.create_task(_system_speech_worker())
    return _system_speech_queue


async def enqueue_system_speech(
    text: str,
    *,
    owner_username: str = "",
    role_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    source: str = "system",
    require_enabled: bool = True,
) -> dict[str, Any]:
    normalized = _normalize_speech_text(text)
    if not normalized:
        return {"queued": False, "reason": "语音内容为空"}

    if require_enabled:
        allowed, reason = is_system_speech_allowed(
            owner_username=owner_username,
            role_ids=role_ids,
        )
        if not allowed:
            return {"queued": False, "reason": reason}

    queue = _ensure_system_speech_queue()
    if queue.full():
        return {"queued": False, "reason": "系统播报队列已满，请稍后重试"}
    await queue.put(
        {
            "text": normalized,
            "owner_username": str(owner_username or "").strip(),
            "source": str(source or "system").strip() or "system",
        }
    )
    return {"queued": True, "reason": "", "text_length": len(normalized), "queue_size": queue.qsize()}
