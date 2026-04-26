import asyncio

import pytest


class _FakeProcess:
    def __init__(self):
        self.returncode = None
        self.terminated = False
        self.killed = False

    async def wait(self):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9


@pytest.mark.asyncio
async def test_project_host_terminal_session_reuses_owner_and_writes_initial_command(
    monkeypatch,
):
    from services import project_host_terminal_service as service

    fake_process = _FakeProcess()
    writes: list[tuple[int, bytes]] = []
    closed_fds: list[int] = []

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return fake_process

    async def _fake_pump_terminal_session(session_id: str) -> None:
        session = service._terminal_sessions.get(session_id)
        if session is not None:
            session.closed = False

    monkeypatch.setattr(service, "_resolve_shell_command", lambda: ["/bin/sh"])
    monkeypatch.setattr(service.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    monkeypatch.setattr(service, "_pump_terminal_session", _fake_pump_terminal_session)
    monkeypatch.setattr(service.pty, "openpty", lambda: (101, 202))
    monkeypatch.setattr(service.os, "write", lambda fd, data: writes.append((fd, data)))
    monkeypatch.setattr(service.os, "close", lambda fd: closed_fds.append(fd))

    started = await service.start_or_attach_project_host_terminal(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_path="/tmp",
        initial_command="lark-cli config init --new",
    )
    session_id = str(started["session_id"])

    queue, history = service.attach_project_host_terminal_listener(session_id)
    assert history == []

    attached = await service.start_or_attach_project_host_terminal(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_path="/tmp",
        initial_command="lark-cli auth login --recommend",
    )

    assert attached["attached_existing"] is True
    assert attached["session_id"] == session_id
    assert writes[0][1].decode("utf-8") == "lark-cli config init --new\r"
    assert writes[1][1].decode("utf-8") == "lark-cli auth login --recommend\r"

    service.detach_project_host_terminal_listener(session_id, queue)
    stopped = await service.stop_project_host_terminal(session_id)
    assert stopped["ok"] is True
    assert fake_process.terminated is True
    assert 101 in closed_fds
