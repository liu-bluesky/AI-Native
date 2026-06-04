"""Skill registry primitives shared by agent runtimes.

The runtime uses this module as the boundary for Hermes-style skills and slash
commands. It intentionally models discovery and resolution only; loading skill
documents and executing commands stays with higher-level integrations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _string_value(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalize_command_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.startswith("/") else f"/{text}"


@dataclass(frozen=True)
class SlashCommand:
    name: str
    skill_id: str = ""
    description: str = ""
    arguments_schema: dict[str, Any] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    raw_command: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_command_name(self.name))
        object.__setattr__(
            self,
            "aliases",
            tuple(
                normalized
                for normalized in (_normalize_command_name(alias) for alias in self.aliases)
                if normalized
            ),
        )

    def matches(self, value: str) -> bool:
        command = _normalize_command_name(value)
        return command == self.name or command in self.aliases

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "skill_id": self.skill_id,
            "description": self.description,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True)
class RuntimeSkill:
    skill_id: str
    name: str = ""
    description: str = ""
    version: str = ""
    path: str = ""
    enabled: bool = True
    load_status: str = "available"
    slash_commands: tuple[SlashCommand, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.enabled and self.load_status == "available"

    def summary(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "path": self.path,
            "enabled": self.enabled,
            "available": self.available,
            "load_status": self.load_status,
            "slash_commands": [command.summary() for command in self.slash_commands],
        }


class SkillRegistry:
    """Collects runtime skills and resolves slash commands."""

    def __init__(self, skills: list[RuntimeSkill] | None = None):
        self._skills: dict[str, RuntimeSkill] = {}
        self._commands: dict[str, SlashCommand] = {}
        for skill in skills or []:
            self.register(skill)

    @classmethod
    def from_manifests(
        cls,
        manifests: list[dict[str, Any]],
        *,
        base_path: str | Path = "",
    ) -> "SkillRegistry":
        registry = cls()
        for manifest in manifests:
            skill = runtime_skill_from_manifest(manifest, base_path=base_path)
            if skill is not None:
                registry.register(skill)
        return registry

    def register(self, skill: RuntimeSkill) -> RuntimeSkill:
        self._skills[skill.skill_id] = skill
        for command in skill.slash_commands:
            if not command.name:
                continue
            self._commands[command.name] = command
            for alias in command.aliases:
                self._commands[alias] = command
        return skill

    def get(self, skill_id: str) -> RuntimeSkill | None:
        return self._skills.get(str(skill_id or "").strip())

    def skills(self, *, available_only: bool = False) -> list[RuntimeSkill]:
        values = list(self._skills.values())
        if available_only:
            return [skill for skill in values if skill.available]
        return values

    def commands(self, *, available_only: bool = False) -> list[SlashCommand]:
        command_names = {
            command.name
            for skill in self.skills(available_only=available_only)
            for command in skill.slash_commands
        }
        return [self._commands[name] for name in sorted(command_names) if name in self._commands]

    def resolve_command(self, message: str) -> SlashCommand | None:
        token = _first_token(message)
        if not token:
            return None
        return self._commands.get(_normalize_command_name(token))

    def summary(self) -> dict[str, Any]:
        skills = self.skills()
        return {
            "skill_total": len(skills),
            "available_skill_total": len([skill for skill in skills if skill.available]),
            "skills": [skill.summary() for skill in skills],
            "slash_commands": [command.summary() for command in self.commands()],
        }


def runtime_skill_from_manifest(
    manifest: dict[str, Any],
    *,
    base_path: str | Path = "",
) -> RuntimeSkill | None:
    if not isinstance(manifest, dict):
        return None
    skill_id = _string_value(manifest, "id", "skill_id", "name")
    if not skill_id:
        return None
    commands = tuple(
        command
        for command in (
            _slash_command_from_manifest(item, skill_id=skill_id)
            for item in _manifest_commands(manifest)
        )
        if command is not None
    )
    raw_path = _string_value(manifest, "path", "directory")
    if not raw_path and base_path:
        raw_path = str(Path(base_path) / skill_id)
    return RuntimeSkill(
        skill_id=skill_id,
        name=_string_value(manifest, "name", "title") or skill_id,
        description=_string_value(manifest, "description"),
        version=_string_value(manifest, "version"),
        path=raw_path,
        enabled=bool(manifest.get("enabled", True)),
        load_status=_string_value(manifest, "load_status", "status") or "available",
        slash_commands=commands,
        metadata=dict(manifest.get("metadata") or {}),
        raw_manifest=dict(manifest),
    )


def _manifest_commands(manifest: dict[str, Any]) -> list[dict[str, Any] | str]:
    commands = manifest.get("slash_commands", manifest.get("commands", []))
    if isinstance(commands, dict):
        return list(commands.values())
    if isinstance(commands, list):
        return commands
    return []


def _slash_command_from_manifest(
    value: dict[str, Any] | str,
    *,
    skill_id: str,
) -> SlashCommand | None:
    if isinstance(value, str):
        name = value
        payload: dict[str, Any] = {}
    elif isinstance(value, dict):
        name = _string_value(value, "name", "command")
        payload = value
    else:
        return None
    normalized_name = _normalize_command_name(name)
    if not normalized_name:
        return None
    aliases = payload.get("aliases") or ()
    if isinstance(aliases, str):
        aliases = [aliases]
    return SlashCommand(
        name=normalized_name,
        skill_id=skill_id,
        description=_string_value(payload, "description", "summary"),
        arguments_schema=dict(payload.get("arguments_schema") or payload.get("schema") or {}),
        aliases=tuple(str(alias) for alias in aliases),
        raw_command=dict(payload),
    )


def _first_token(message: str) -> str:
    text = str(message or "").strip()
    if not text:
        return ""
    return text.split(maxsplit=1)[0]


__all__ = [
    "RuntimeSkill",
    "SkillRegistry",
    "SlashCommand",
    "runtime_skill_from_manifest",
]
