"""Interactive PTY sessions for project chat host terminals."""

from __future__ import annotations

import asyncio
import errno
import os
import pty
import termios
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from services.cli_plugin_market_service import build_cli_plugin_runtime_environment
from services.project_host_command_service import _resolve_workspace_root

_MAX_HISTORY_CHUNKS = 400


def _disable_tty_echo(fd: int) -> None:
    try:
        attrs = termios.tcgetattr(fd)
        attrs[3] = attrs[3] & ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except Exception:
        return


def _resolve_shell_command() -> list[str]:
    shell_path = str(os.environ.get("SHELL") or "").strip() or "/bin/zsh"
    shell_name = Path(shell_path).name.lower()
    if shell_name in {"bash", "zsh"}:
        return [shell_path, "-l"]
    return [shell_path]


@dataclass
class ProjectHostTerminalSession:
    session_id: str
    owner_key: tuple[str, str, str]
    workspace_path: str
    process: asyncio.subprocess.Process
    master_fd: int
    command: list[str]
    history_chunks: list[str] = field(default_factory=list)
    listeners: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    pump_task: asyncio.Task[None] | None = None
    closed: bool = False
    exit_code: int | None = None


_terminal_sessions: dict[str, ProjectHostTerminalSession] = {}
_terminal_owner_index: dict[tuple[str, str, str], str] = {}


def _session_owner_key(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
) -> tuple[str, str, str]:
    return (
        str(project_id or "").strip(),
        str(username or "").strip(),
        str(chat_session_id or "").strip(),
    )


async def _broadcast_terminal_event(
    session: ProjectHostTerminalSession,
    event: dict[str, Any],
) -> None:
    if event.get("type") == "chunk":
        chunk_text = str(event.get("content") or "")
        if chunk_text:
            session.history_chunks.append(chunk_text)
            if len(session.history_chunks) > _MAX_HISTORY_CHUNKS:
                session.history_chunks = session.history_chunks[-_MAX_HISTORY_CHUNKS:]
    listeners = list(session.listeners)
    for queue in listeners:
        await queue.put(dict(event))


async def _pump_terminal_session(session_id: str) -> None:
    session = _terminal_sessions.get(session_id)
    if session is None:
        return
    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                chunk = await loop.run_in_executor(None, os.read, session.master_fd, 4096)
            except OSError as exc:
                if exc.errno in {errno.EIO, errno.EBADF}:
                    break
                raise
            if not chunk:
                if session.process.returncode is not None:
                    break
                await asyncio.sleep(0.05)
                continue
            await _broadcast_terminal_event(
                session,
                {"type": "chunk", "content": chunk.decode("utf-8", errors="ignore")},
            )
            if session.process.returncode is not None:
                break
        await session.process.wait()
    finally:
        session.closed = True
        session.exit_code = session.process.returncode
        _terminal_owner_index.pop(session.owner_key, None)
        await _broadcast_terminal_event(
            session,
            {
                "type": "exit",
                "exit_code": session.exit_code,
            },
        )
        if not session.listeners:
            _cleanup_terminal_session(session_id)


def _cleanup_terminal_session(session_id: str) -> None:
    session = _terminal_sessions.pop(session_id, None)
    if session is None:
        return
    _terminal_owner_index.pop(session.owner_key, None)
    try:
        os.close(session.master_fd)
    except OSError:
        pass


async def start_or_attach_project_host_terminal(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    workspace_path: str,
    initial_command: str = "",
) -> dict[str, Any]:
    owner_key = _session_owner_key(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
    )
    existing_session_id = _terminal_owner_index.get(owner_key)
    existing_session = _terminal_sessions.get(existing_session_id or "")
    normalized_initial_command = str(initial_command or "").strip()
    if existing_session is not None and not existing_session.closed:
        if normalized_initial_command:
            await write_project_host_terminal_input(
                existing_session.session_id,
                f"{normalized_initial_command}\r",
            )
        return {
            "session_id": existing_session.session_id,
            "workspace_path": existing_session.workspace_path,
            "attached_existing": True,
            "command": normalized_initial_command,
        }

    workspace_root, _ = _resolve_workspace_root(workspace_path)
    shell_command = _resolve_shell_command()
    session_id = f"host-term-{uuid.uuid4().hex[:12]}"
    master_fd, slave_fd = pty.openpty()
    _disable_tty_echo(slave_fd)
    exec_env, plugin_runtime_metadata = build_cli_plugin_runtime_environment()
    process = await asyncio.create_subprocess_exec(
        *shell_command,
        cwd=str(workspace_root),
        env=exec_env,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
    )
    os.close(slave_fd)
    session = ProjectHostTerminalSession(
        session_id=session_id,
        owner_key=owner_key,
        workspace_path=str(workspace_root),
        process=process,
        master_fd=master_fd,
        command=shell_command,
    )
    _terminal_sessions[session_id] = session
    _terminal_owner_index[owner_key] = session_id
    session.pump_task = asyncio.create_task(_pump_terminal_session(session_id))
    if normalized_initial_command:
        os.write(master_fd, f"{normalized_initial_command}\r".encode("utf-8", errors="ignore"))
    return {
        "session_id": session_id,
        "workspace_path": str(workspace_root),
        "attached_existing": False,
        "command": normalized_initial_command,
        "shell_command": shell_command,
        **plugin_runtime_metadata,
    }


def get_project_host_terminal_session(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
) -> ProjectHostTerminalSession | None:
    owner_key = _session_owner_key(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
    )
    session_id = _terminal_owner_index.get(owner_key)
    session = _terminal_sessions.get(session_id or "")
    if session is None or session.closed:
        return None
    return session


def attach_project_host_terminal_listener(
    session_id: str,
) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]]]:
    session = _terminal_sessions.get(str(session_id or "").strip())
    if session is None:
        raise LookupError("terminal session not found")
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    session.listeners.add(queue)
    history_events = [{"type": "chunk", "content": chunk} for chunk in session.history_chunks]
    if session.closed:
        history_events.append({"type": "exit", "exit_code": session.exit_code})
    return queue, history_events


def detach_project_host_terminal_listener(
    session_id: str,
    queue: asyncio.Queue[dict[str, Any]] | None,
) -> None:
    session = _terminal_sessions.get(str(session_id or "").strip())
    if session is None or queue is None:
        return
    session.listeners.discard(queue)
    if session.closed and not session.listeners:
        _cleanup_terminal_session(session_id)


async def write_project_host_terminal_input(session_id: str, content: str) -> dict[str, Any]:
    session = _terminal_sessions.get(str(session_id or "").strip())
    if session is None or session.closed or session.process.returncode is not None:
        raise LookupError("terminal session not running")
    payload = str(content or "")
    if not payload:
        return {"ok": True}
    os.write(session.master_fd, payload.encode("utf-8", errors="ignore"))
    return {"ok": True}


async def stop_project_host_terminal(session_id: str) -> dict[str, Any]:
    session = _terminal_sessions.get(str(session_id or "").strip())
    if session is None:
        return {"ok": False, "reason": "not_found"}
    if session.process.returncode is None:
        session.process.terminate()
    try:
        os.close(session.master_fd)
    except OSError:
        pass
    if session.pump_task is not None:
        try:
            await asyncio.wait_for(session.pump_task, timeout=2)
        except Exception:
            if session.process.returncode is None:
                session.process.kill()
    session.closed = True
    if not session.listeners:
        _cleanup_terminal_session(session_id)
    return {"ok": True}


def list_project_host_terminal_sessions() -> Iterable[ProjectHostTerminalSession]:
    return list(_terminal_sessions.values())
