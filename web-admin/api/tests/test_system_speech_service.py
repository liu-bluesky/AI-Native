"""System speech playback service tests."""

from types import SimpleNamespace


def test_darwin_system_speech_temporarily_unmutes_and_restores(monkeypatch):
    from services import system_speech_service as service

    calls = []

    def fake_which(binary):
        return f"/usr/bin/{binary}" if binary in {"say", "osascript"} else None

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:2] == ["osascript", "-e"] and "get volume settings" in command[2]:
            return SimpleNamespace(stdout="true,12\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(service.sys, "platform", "darwin")
    monkeypatch.setattr(service.shutil, "which", fake_which)
    monkeypatch.setattr(service.subprocess, "run", fake_run)

    service._run_native_system_speech_sync("hello")

    assert [call[0] for call in calls] == [
        [
            "osascript",
            "-e",
            'set currentSettings to get volume settings\nreturn (output muted of currentSettings as text) & "," & (output volume of currentSettings as text)',
        ],
        ["osascript", "-e", "set volume output volume 40"],
        ["osascript", "-e", "set volume output muted false"],
        ["/usr/bin/say", "hello"],
        ["osascript", "-e", "set volume output volume 12"],
        ["osascript", "-e", "set volume output muted true"],
    ]


def test_darwin_system_speech_uses_configured_reminder_volume(monkeypatch):
    from services import system_speech_service as service

    calls = []

    def fake_which(binary):
        return f"/usr/bin/{binary}" if binary in {"say", "osascript"} else None

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:2] == ["osascript", "-e"] and "get volume settings" in command[2]:
            return SimpleNamespace(stdout="false,22\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(service.sys, "platform", "darwin")
    monkeypatch.setattr(service.shutil, "which", fake_which)
    monkeypatch.setattr(service.subprocess, "run", fake_run)
    monkeypatch.setattr(
        service.system_config_store,
        "get_global",
        lambda: SimpleNamespace(voice_output_reminder_volume=35),
    )

    service._run_native_system_speech_sync("hello")

    assert ["osascript", "-e", "set volume output volume 35"] in [call[0] for call in calls]


def test_darwin_system_speech_still_speaks_when_volume_state_unavailable(monkeypatch):
    from services import system_speech_service as service

    calls = []

    def fake_which(binary):
        return f"/usr/bin/{binary}" if binary in {"say", "osascript"} else None

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:2] == ["osascript", "-e"] and "get volume settings" in command[2]:
            raise RuntimeError("osascript failed")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(service.sys, "platform", "darwin")
    monkeypatch.setattr(service.shutil, "which", fake_which)
    monkeypatch.setattr(service.subprocess, "run", fake_run)

    service._run_native_system_speech_sync("hello")

    assert [call[0] for call in calls] == [
        [
            "osascript",
            "-e",
            'set currentSettings to get volume settings\nreturn (output muted of currentSettings as text) & "," & (output volume of currentSettings as text)',
        ],
        ["/usr/bin/say", "hello"],
    ]
