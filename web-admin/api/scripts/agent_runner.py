"""Host agent runner for executing Codex outside the API sandbox."""

from __future__ import annotations

import asyncio
import errno
import json
import os
import pty
import shutil
import termios
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


def _disable_tty_echo(fd: int) -> None:
    try:
        attrs = termios.tcgetattr(fd)
        attrs[3] = attrs[3] & ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except Exception:
        return


class ExecRequest(BaseModel):
    cmd: list[str]
    cwd: str
    env: dict[str, str] = Field(default_factory=dict)


class PtyOpenRequest(BaseModel):
    cmd: list[str]
    cwd: str
    env: dict[str, str] = Field(default_factory=dict)


class PtyInputRequest(BaseModel):
    content: str = ""


class ProbeRequest(BaseModel):
    workspace_path: str = ""
    sandbox_mode: str = "workspace-write"


class MaterializeFileRequest(BaseModel):
    path: str
    content: str = ""


class MaterializeCopyRequest(BaseModel):
    source_path: str
    target_path: str


class MaterializeWorkspaceRequest(BaseModel):
    workspace_path: str = ""
    sandbox_mode: str = "workspace-write"
    files: list[MaterializeFileRequest] = Field(default_factory=list)
    copies: list[MaterializeCopyRequest] = Field(default_factory=list)


class PtySession:
    def __init__(self, process: asyncio.subprocess.Process, master_fd: int) -> None:
        self.process = process
        self.master_fd = master_fd
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task | None = None


app = FastAPI(title="Agent Runner", version="0.1.0")
_exec_processes: dict[str, asyncio.subprocess.Process] = {}
_pty_sessions: dict[str, PtySession] = {}


def _probe_workspace_access(workspace_path: str, sandbox_mode: str = "workspace-write") -> dict[str, Any]:
    raw = str(workspace_path or "").strip()
    mode = str(sandbox_mode or "workspace-write").strip() or "workspace-write"
    if not raw:
        return {"configured": False, "exists": False, "is_dir": False, "read_ok": False, "write_ok": False, "sandbox_mode": mode, "reason": "未配置 workspace_path"}
    workspace = Path(raw).expanduser()
    if not workspace.exists():
        return {"configured": True, "exists": False, "is_dir": False, "read_ok": False, "write_ok": False, "sandbox_mode": mode, "reason": f"工作区不存在：{workspace}"}
    if not workspace.is_dir():
        return {"configured": True, "exists": True, "is_dir": False, "read_ok": False, "write_ok": False, "sandbox_mode": mode, "reason": f"工作区不是目录：{workspace}"}
    result = {"configured": True, "exists": True, "is_dir": True, "read_ok": True, "write_ok": False, "sandbox_mode": mode, "path": str(workspace), "reason": ""}
    if mode != "workspace-write":
        result["reason"] = "当前请求的是只读模式(read-only)"
        return result
    support_dir = workspace / ".ai-employee"
    probe_file = support_dir / f".write-probe-{uuid.uuid4().hex}.tmp"
    try:
        support_dir.mkdir(parents=True, exist_ok=True)
        probe_file.write_text("ok", encoding="utf-8")
        try:
            probe_file.unlink()
        except FileNotFoundError:
            pass
        result["write_ok"] = True
        return result
    except Exception as exc:
        result["reason"] = str(exc)
        return result


@app.get("/health")
async def health() -> dict[str, Any]:
    command = shutil.which("codex") or ""
    return {"ok": True, "codex_available": bool(command), "codex_path": command}


@app.post("/probe-workspace")
async def probe_workspace(req: ProbeRequest) -> dict[str, Any]:
    return _probe_workspace_access(req.workspace_path, req.sandbox_mode)


@app.post("/workspace/materialize")
async def materialize_workspace(req: MaterializeWorkspaceRequest) -> dict[str, Any]:
    access = _probe_workspace_access(req.workspace_path, req.sandbox_mode)
    access["source"] = "runner"
    workspace_root = Path(str(req.workspace_path or "").strip()).expanduser()
    result: dict[str, Any] = {
        "ok": False,
        "workspace_access": access,
        "files": [],
        "copies": [],
    }
    if not access.get("configured") or not access.get("exists") or not access.get("is_dir"):
        result["reason"] = str(access.get("reason") or "工作区不可用")
        return result
    if req.sandbox_mode == "workspace-write" and not access.get("write_ok"):
        result["reason"] = str(access.get("reason") or "工作区不可写")
        return result

    file_results: list[dict[str, Any]] = []
    for item in list(req.files or []):
        path = Path(str(item.path or "").strip())
        entry = {"path": str(path), "written": False}
        try:
            if not path.is_absolute():
                raise ValueError("path 必须是绝对路径")
            path.relative_to(workspace_root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(item.content or ""), encoding="utf-8")
            entry["written"] = True
        except Exception as exc:
            entry["error"] = str(exc)
        file_results.append(entry)

    copy_results: list[dict[str, Any]] = []
    for item in list(req.copies or []):
        source = Path(str(item.source_path or "").strip())
        target = Path(str(item.target_path or "").strip())
        entry = {
            "source_path": str(source),
            "target_path": str(target),
            "written": False,
        }
        try:
            if not source.is_file():
                raise FileNotFoundError(f"源文件不存在：{source}")
            if not target.is_absolute():
                raise ValueError("target_path 必须是绝对路径")
            target.relative_to(workspace_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            entry["written"] = True
        except Exception as exc:
            entry["error"] = str(exc)
        copy_results.append(entry)

    result["ok"] = all(bool(item.get("written")) for item in [*file_results, *copy_results])
    result["files"] = file_results
    result["copies"] = copy_results
    return result


@app.post("/exec/stream")
async def exec_stream(req: ExecRequest):
    if not req.cmd:
        raise HTTPException(400, "cmd is required")
    exec_id = f"exec-{uuid.uuid4().hex[:12]}"

    async def stream():
        process = await asyncio.create_subprocess_exec(
            *req.cmd,
            cwd=req.cwd,
            env={**os.environ, **req.env},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _exec_processes[exec_id] = process
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        await queue.put({"type": "started", "exec_id": exec_id})

        async def pump(name: str, stream):
            while True:
                line = await stream.readline()
                if not line:
                    break
                await queue.put({"type": name, "data": line.decode("utf-8", errors="ignore")})

        stdout_task = asyncio.create_task(pump("stdout", process.stdout))
        stderr_task = asyncio.create_task(pump("stderr", process.stderr))
        try:
            while True:
                if process.returncode is not None and queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield json.dumps(event, ensure_ascii=False) + "\n"
                except asyncio.TimeoutError:
                    continue
            await process.wait()
            await stdout_task
            await stderr_task
            yield json.dumps({"type": "exit", "exec_id": exec_id, "returncode": process.returncode}, ensure_ascii=False) + "\n"
        finally:
            _exec_processes.pop(exec_id, None)
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except Exception:
                    process.kill()

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/exec/cancel/{exec_id}")
async def cancel_exec(exec_id: str) -> dict[str, Any]:
    process = _exec_processes.get(exec_id)
    if process is None or process.returncode is not None:
        return {"ok": False, "reason": "not_running"}
    process.terminate()
    return {"ok": True}


async def _pump_pty_session(session_id: str, session: PtySession) -> None:
    loop = asyncio.get_running_loop()
    process = session.process
    master_fd = session.master_fd
    try:
        while True:
            try:
                chunk = await loop.run_in_executor(None, os.read, master_fd, 4096)
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise
            if not chunk:
                if process.returncode is not None:
                    break
                continue
            await session.queue.put({"type": "chunk", "data": chunk.decode("utf-8", errors="ignore")})
            if process.returncode is not None:
                break
        await process.wait()
    finally:
        await session.queue.put({"type": "exit", "returncode": process.returncode})


@app.post("/pty/open")
async def pty_open(req: PtyOpenRequest) -> dict[str, Any]:
    if not req.cmd:
        raise HTTPException(400, "cmd is required")
    session_id = f"pty-{uuid.uuid4().hex[:12]}"
    master_fd, slave_fd = pty.openpty()
    _disable_tty_echo(slave_fd)
    process = await asyncio.create_subprocess_exec(
        *req.cmd,
        cwd=req.cwd,
        env={**os.environ, **req.env},
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
    )
    os.close(slave_fd)
    session = PtySession(process, master_fd)
    _pty_sessions[session_id] = session
    session.task = asyncio.create_task(_pump_pty_session(session_id, session))
    return {"session_id": session_id}


@app.get("/pty/stream/{session_id}")
async def pty_stream(session_id: str):
    session = _pty_sessions.get(session_id)
    if session is None:
        raise HTTPException(404, "session not found")

    async def stream():
        try:
            while True:
                event = await session.queue.get()
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event.get("type") == "exit":
                    break
        finally:
            _pty_sessions.pop(session_id, None)
            try:
                os.close(session.master_fd)
            except OSError:
                pass

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/pty/input/{session_id}")
async def pty_input(session_id: str, req: PtyInputRequest) -> dict[str, Any]:
    session = _pty_sessions.get(session_id)
    if session is None or session.process.returncode is not None:
        raise HTTPException(404, "session not running")
    os.write(session.master_fd, str(req.content or "").encode("utf-8", errors="ignore"))
    return {"ok": True}


@app.post("/pty/close/{session_id}")
async def pty_close(session_id: str) -> dict[str, Any]:
    session = _pty_sessions.pop(session_id, None)
    if session is None:
        return {"ok": False, "reason": "not_found"}
    if session.process.returncode is None:
        session.process.terminate()
    if session.task is not None:
        session.task.cancel()
    try:
        os.close(session.master_fd)
    except OSError:
        pass
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("AGENT_RUNNER_HOST", "127.0.0.1")
    port = int(os.environ.get("AGENT_RUNNER_PORT", "3927"))
    uvicorn.run(app, host=host, port=port)
