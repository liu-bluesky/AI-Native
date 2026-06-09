"""Plugin and tool registry primitives shared by agent runtimes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import get_project_root


def _string_value(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


@dataclass
class RuntimeToolEntry:
    tool_name: str
    source: str = "project"
    plugin_id: str = ""
    plugin_name: str = ""
    version: str = ""
    installed: bool = True
    load_status: str = "available"
    requires_trust: bool = False
    trusted: bool = True
    description: str = ""
    parameters_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    permission_scope: str = "workspace"
    execution_backend: str = "project"
    audit_policy: str = "standard"
    raw_tool: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.installed and (not self.requires_trust or self.trusted)

    def openai_tool(self) -> dict[str, Any]:
        payload = dict(self.raw_tool)
        payload.setdefault("tool_name", self.tool_name)
        payload.setdefault("source", self.source)
        if self.plugin_id:
            payload.setdefault("plugin_id", self.plugin_id)
        if self.version:
            payload.setdefault("version", self.version)
        payload.setdefault("installed", self.installed)
        payload.setdefault("load_status", self.load_status)
        payload.setdefault("requires_trust", self.requires_trust)
        payload.setdefault("trusted", self.trusted)
        if self.parameters_schema:
            payload.setdefault("parameters_schema", dict(self.parameters_schema))
        payload.setdefault("risk_level", self.risk_level)
        payload.setdefault("permission_scope", self.permission_scope)
        payload.setdefault("execution_backend", self.execution_backend)
        payload.setdefault("audit_policy", self.audit_policy)
        return payload

    def summary(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "source": self.source,
            "plugin_id": self.plugin_id,
            "plugin_name": self.plugin_name,
            "version": self.version,
            "installed": self.installed,
            "available": self.available,
            "load_status": self.load_status,
            "requires_trust": self.requires_trust,
            "trusted": self.trusted,
            "description": self.description,
            "parameters_schema": dict(self.parameters_schema),
            "risk_level": self.risk_level,
            "permission_scope": self.permission_scope,
            "execution_backend": self.execution_backend,
            "audit_policy": self.audit_policy,
        }


@dataclass
class PluginRegistryContext:
    workspace_path: str = ""
    workspace_trusted: bool = True
    include_browser_tools: bool = False
    browser_bridge_available: bool = False
    skill_roots: list[Path] = field(default_factory=list)
    cli_plugin_status: dict[str, dict[str, Any]] = field(default_factory=dict)


class PluginRegistry:
    """Normalizes runtime tools without depending on the legacy registry shape."""

    def __init__(
        self,
        tools: list[dict[str, Any]] | None = None,
        *,
        context: PluginRegistryContext | None = None,
    ):
        self._context = context or PluginRegistryContext()
        self._skill_manifests = self._load_skill_manifests(self._context.skill_roots)
        self._entries: dict[str, RuntimeToolEntry] = {}
        for item in tools or []:
            self.register_runtime_tool(item)

    @classmethod
    def from_runtime_tools(
        cls,
        tools: list[dict[str, Any]] | None,
        *,
        context: PluginRegistryContext | None = None,
    ) -> "PluginRegistry":
        return cls(tools, context=context)

    def register_runtime_tool(self, tool: dict[str, Any]) -> RuntimeToolEntry | None:
        if not isinstance(tool, dict):
            return None
        tool_name = _string_value(tool, "tool_name", "name")
        if not tool_name or tool_name in self._entries:
            return None
        source = self._infer_source(tool)
        plugin_id = _string_value(tool, "plugin_id", "skill_id", "mcp_server_name")
        skill_manifest = self._skill_manifests.get(plugin_id, {})
        plugin_status = self._plugin_status(plugin_id)
        installed = self._resolve_installed(tool, source=source, plugin_status=plugin_status)
        requires_trust = self._requires_trust(tool, source=source)
        trusted = bool(self._context.workspace_trusted) or not requires_trust
        load_status = self._load_status(
            installed=installed,
            trusted=trusted,
            requires_trust=requires_trust,
            plugin_status=plugin_status,
            explicit_status=_string_value(tool, "load_status", "status"),
        )
        parameters_schema = self._parameters_schema(tool)
        risk_level = self._risk_level(tool, source=source, tool_name=tool_name)
        permission_scope = self._permission_scope(tool, source=source)
        execution_backend = self._execution_backend(tool, source=source, tool_name=tool_name)
        audit_policy = self._audit_policy(tool, risk_level=risk_level)
        entry = RuntimeToolEntry(
            tool_name=tool_name,
            source=source,
            plugin_id=plugin_id,
            plugin_name=(
                _string_value(tool, "plugin_name", "skill_name", "mcp_server_name")
                or str(skill_manifest.get("name") or "").strip()
            ),
            version=self._resolve_version(tool, skill_manifest=skill_manifest, plugin_status=plugin_status),
            installed=installed,
            load_status=load_status,
            requires_trust=requires_trust,
            trusted=trusted,
            description=(
                _string_value(tool, "description", "label", "title")
                or str(skill_manifest.get("description") or "").strip()
            ),
            parameters_schema=parameters_schema,
            risk_level=risk_level,
            permission_scope=permission_scope,
            execution_backend=execution_backend,
            audit_policy=audit_policy,
            raw_tool={
                **tool,
                "tool_name": tool_name,
                "source": source,
                "plugin_id": plugin_id,
                "parameters_schema": parameters_schema,
                "risk_level": risk_level,
                "permission_scope": permission_scope,
                "execution_backend": execution_backend,
                "audit_policy": audit_policy,
            },
        )
        self._entries[tool_name] = entry
        return entry

    def entries(self) -> list[RuntimeToolEntry]:
        return list(self._entries.values())

    def names(self) -> list[str]:
        return [entry.tool_name for entry in self.entries() if entry.available]

    def available_entries(self) -> list[RuntimeToolEntry]:
        return [entry for entry in self.entries() if entry.available]

    def summary(self, *, max_items: int = 24) -> dict[str, Any]:
        entries = self.entries()
        return {
            "registered_tool_total": len(entries),
            "registered_tools": [entry.summary() for entry in entries[:max_items]],
            "tool_names": self.names(),
            "workspace_trusted": bool(self._context.workspace_trusted),
        }

    def _infer_source(self, tool: dict[str, Any]) -> str:
        explicit = _string_value(tool, "source", "tool_source", "origin")
        if explicit:
            return explicit
        tool_name = _string_value(tool, "tool_name", "name")
        if bool(tool.get("builtin")):
            return "builtin"
        if _string_value(tool, "mcp_server_name", "mcp_server_id"):
            return "mcp"
        if _string_value(tool, "skill_id", "skill_name"):
            return "skill"
        if _string_value(tool, "plugin_id", "plugin_name"):
            return "plugin"
        if _string_value(tool, "connector_id", "local_connector_id"):
            return "local_connector"
        if tool_name.startswith("project_host_"):
            return "project"
        if tool_name.startswith("browser_") or tool_name.startswith("chrome_"):
            return "browser"
        if tool_name.startswith("cli_") or "command" in tool_name:
            return "cli"
        return "project"

    def _requires_trust(self, tool: dict[str, Any], *, source: str) -> bool:
        if "requires_trust" in tool:
            return bool(tool.get("requires_trust"))
        if source in {"browser", "plugin", "cli", "local_connector"}:
            return True
        if source == "skill":
            plugin_id = _string_value(tool, "skill_id", "plugin_id")
            manifest = self._skill_manifests.get(plugin_id, {})
            return bool(manifest.get("project_local"))
        return False

    def _parameters_schema(self, tool: dict[str, Any]) -> dict[str, Any]:
        schema = tool.get("parameters_schema") or tool.get("parameters") or tool.get("schema")
        return dict(schema) if isinstance(schema, dict) else {}

    def _risk_level(self, tool: dict[str, Any], *, source: str, tool_name: str) -> str:
        explicit = _string_value(tool, "risk_level", "risk")
        if explicit:
            return explicit
        if tool_name == "project_host_run_command":
            return "medium"
        if tool_name.startswith("project_host_terminal_"):
            return "medium"
        if source in {"browser", "local_connector", "cli"}:
            return "medium"
        return "low"

    def _permission_scope(self, tool: dict[str, Any], *, source: str) -> str:
        explicit = _string_value(tool, "permission_scope", "scope")
        if explicit:
            return explicit
        if source in {"project", "skill", "mcp"}:
            return "project"
        if source in {"browser", "local_connector", "cli"}:
            return "workspace"
        return "global"

    def _execution_backend(self, tool: dict[str, Any], *, source: str, tool_name: str) -> str:
        explicit = _string_value(tool, "execution_backend", "backend")
        if explicit:
            return explicit
        if tool_name.startswith("project_host_terminal_") or tool_name == "project_host_run_command":
            return "project_host"
        return source

    def _audit_policy(self, tool: dict[str, Any], *, risk_level: str) -> str:
        explicit = _string_value(tool, "audit_policy")
        if explicit:
            return explicit
        if risk_level in {"high", "critical"}:
            return "full"
        if risk_level == "medium":
            return "standard"
        return "summary"

    def _resolve_installed(
        self,
        tool: dict[str, Any],
        *,
        source: str,
        plugin_status: dict[str, Any],
    ) -> bool:
        if "installed" in tool:
            return bool(tool.get("installed"))
        if source in {"builtin", "project", "mcp", "local_connector", "browser"}:
            return True
        if source == "skill":
            plugin_id = _string_value(tool, "skill_id", "plugin_id")
            return plugin_id in self._skill_manifests or not plugin_id
        if source in {"plugin", "cli"}:
            if plugin_status:
                return bool(plugin_status.get("installed"))
            return False
        return True

    def _resolve_version(
        self,
        tool: dict[str, Any],
        *,
        skill_manifest: dict[str, Any],
        plugin_status: dict[str, Any],
    ) -> str:
        return (
            _string_value(tool, "version", "installed_version")
            or str(plugin_status.get("installed_version") or "").strip()
            or str(skill_manifest.get("version") or "").strip()
        )

    def _plugin_status(self, plugin_id: str) -> dict[str, Any]:
        value = self._context.cli_plugin_status.get(str(plugin_id or "").strip())
        return dict(value) if isinstance(value, dict) else {}

    def _load_status(
        self,
        *,
        installed: bool,
        trusted: bool,
        requires_trust: bool,
        plugin_status: dict[str, Any],
        explicit_status: str,
    ) -> str:
        if requires_trust and not trusted:
            return "blocked_untrusted_workspace"
        if not installed:
            return explicit_status or "not_installed"
        if explicit_status:
            return explicit_status
        return str(plugin_status.get("status") or "available").strip() or "available"

    def _load_skill_manifests(self, roots: list[Path]) -> dict[str, dict[str, Any]]:
        manifests: dict[str, dict[str, Any]] = {}
        for root in roots:
            for skill_dir in self._iter_skill_dirs(root):
                manifest = self._read_skill_manifest(skill_dir)
                skill_id = str(
                    manifest.get("id")
                    or manifest.get("skill_id")
                    or manifest.get("name")
                    or skill_dir.name
                ).strip()
                if not skill_id or skill_id in manifests:
                    continue
                manifests[skill_id] = {
                    **manifest,
                    "id": skill_id,
                    "path": str(skill_dir),
                    "project_local": self._is_project_local_skill(skill_dir),
                }
        return manifests

    def _iter_skill_dirs(self, root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        candidates: list[Path] = []
        for path in [root, *root.glob("*"), *root.glob("*/*")]:
            if not path.is_dir():
                continue
            if (path / "SKILL.md").is_file() or (path / "manifest.json").is_file():
                candidates.append(path)
        return candidates

    def _read_skill_manifest(self, skill_dir: Path) -> dict[str, Any]:
        manifest_path = skill_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict):
                return payload
        return {"name": skill_dir.name}

    def _is_project_local_skill(self, skill_dir: Path) -> bool:
        workspace_path = str(self._context.workspace_path or "").strip()
        if not workspace_path:
            return False
        try:
            skill_dir.resolve().relative_to(Path(workspace_path).resolve())
        except (OSError, ValueError):
            return False
        return True


def default_plugin_registry_context(
    *,
    workspace_path: str = "",
    workspace_trusted: bool = True,
    include_browser_tools: bool = False,
    browser_bridge_available: bool = False,
    cli_plugin_status: dict[str, dict[str, Any]] | None = None,
) -> PluginRegistryContext:
    project_root = get_project_root()
    skill_roots = [
        project_root / ".ai-employee" / "skills",
        project_root / ".agents" / "skills",
    ]
    effective_cli_plugin_status = (
        dict(cli_plugin_status)
        if cli_plugin_status is not None
        else _load_cli_plugin_install_status(project_root)
    )
    return PluginRegistryContext(
        workspace_path=str(workspace_path or "").strip(),
        workspace_trusted=bool(workspace_trusted),
        include_browser_tools=bool(include_browser_tools),
        browser_bridge_available=bool(browser_bridge_available),
        skill_roots=skill_roots,
        cli_plugin_status=effective_cli_plugin_status,
    )


def _load_cli_plugin_install_status(project_root: Path) -> dict[str, dict[str, Any]]:
    path = project_root / ".ai-employee" / "cli-plugin-market" / "install-state.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    installs = payload.get("installs") if isinstance(payload, dict) else {}
    if not isinstance(installs, dict):
        return {}
    statuses: dict[str, dict[str, Any]] = {}
    for plugin_id, receipt in installs.items():
        normalized_id = str(plugin_id or "").strip()
        if not normalized_id or not isinstance(receipt, dict):
            continue
        installed = bool(receipt.get("installed"))
        installed_version = str(receipt.get("installed_version") or "").strip()
        latest_version = str(receipt.get("latest_version") or "").strip()
        statuses[normalized_id] = {
            "installed": installed,
            "installed_version": installed_version,
            "latest_version": latest_version,
            "status": "installed" if installed else "not_installed",
            "last_installed_at": str(receipt.get("last_installed_at") or "").strip(),
            "detection_source": str(receipt.get("detection_source") or "").strip(),
        }
    return statuses
