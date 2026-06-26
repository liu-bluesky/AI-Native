"""内置工具测试：文件工具、命令工具、网络工具、路径安全、权限分类。

覆盖：
- 文件读写正常路径
- 路径逃逸（../）拒绝
- 命令风险分类（safe/medium/high/critical）
- 工具定义注册表完整性
- PermissionPolicy 风险计算
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from services.agent_runtime.builtin_tools.definitions import (
    BUILTIN_TOOL_DEFINITIONS,
    BUILTIN_TOOL_NAMES,
    LOCAL_BUILTIN_TOOL_NAMES,
    MCP_DELEGATED_BUILTIN_TOOL_NAMES,
    is_builtin_tool,
    is_local_builtin_tool,
    is_mcp_delegated_builtin_tool,
    iter_builtin_runtime_tools,
)
from services.agent_runtime.builtin_tools.command_tools import classify_command_risk
from services.agent_runtime.builtin_tools.registry import (
    execute_builtin_tool,
    get_builtin_tool_risk_override,
)
from services.agent_runtime.builtin_tools.workspace import (
    WorkspacePathError,
    resolve_workspace_path,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """创建临时 workspace 目录。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "src" / "test.py").write_text("# test file\nprint('test')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Test Project\nsecond\n", encoding="utf-8")
    return tmp_path


class TestWorkspacePathSecurity:
    """路径安全检查。"""

    def test_normal_relative_path_resolves(self, workspace: Path) -> None:
        result = resolve_workspace_path(str(workspace), "src/main.py", must_exist=True)
        assert result == workspace / "src" / "main.py"

    def test_dot_path_resolves_to_workspace(self, workspace: Path) -> None:
        result = resolve_workspace_path(str(workspace), ".", must_exist=True)
        assert result == workspace

    def test_path_traversal_rejected(self, workspace: Path) -> None:
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(str(workspace), "../../../etc/passwd")

    def test_workspace_absolute_path_resolves(self, workspace: Path) -> None:
        result = resolve_workspace_path(
            str(workspace),
            str(workspace / "src" / "main.py"),
            must_exist=True,
        )
        assert result == workspace / "src" / "main.py"

    def test_external_absolute_path_rejected(self, workspace: Path) -> None:
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(str(workspace), "/etc/passwd")

    def test_nonexistent_path_rejected_without_allow_create(self, workspace: Path) -> None:
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(str(workspace), "nonexistent.py", must_exist=True)

    def test_allow_create_for_write(self, workspace: Path) -> None:
        result = resolve_workspace_path(str(workspace), "new_file.py", allow_create=True)
        assert result == workspace / "new_file.py"


class TestToolDefinitions:
    """工具定义注册表完整性。"""

    def test_all_tools_have_required_fields(self) -> None:
        required_fields = {"name", "description", "input_schema", "action", "risk", "requires_approval", "scope"}
        for name, definition in BUILTIN_TOOL_DEFINITIONS.items():
            missing = required_fields - set(definition.keys())
            assert not missing, f"tool {name} missing fields: {missing}"

    def test_actions_are_canonical(self) -> None:
        expected_actions = {"file.read", "file.write", "command.check", "command.run", "network.read", "network.write", "mcp.list", "mcp.read", "mcp.call"}
        for name, definition in BUILTIN_TOOL_DEFINITIONS.items():
            assert definition["action"] in expected_actions, f"tool {name} has unexpected action: {definition['action']}"

    def test_risk_levels_valid(self) -> None:
        valid_levels = {"low", "medium", "high", "critical"}
        for name, definition in BUILTIN_TOOL_DEFINITIONS.items():
            assert definition["risk"] in valid_levels, f"tool {name} has invalid risk: {definition['risk']}"

    def test_is_builtin_tool(self) -> None:
        assert is_builtin_tool("list_files")
        assert is_builtin_tool("run_command")
        assert not is_builtin_tool("project_host_run_command")
        assert not is_builtin_tool("unknown_tool")

    def test_thirteen_tools_registered(self) -> None:
        assert len(BUILTIN_TOOL_NAMES) == 13

    def test_local_and_mcp_delegated_sets_are_disjoint(self) -> None:
        assert len(LOCAL_BUILTIN_TOOL_NAMES) == 10
        assert len(MCP_DELEGATED_BUILTIN_TOOL_NAMES) == 3
        assert LOCAL_BUILTIN_TOOL_NAMES.isdisjoint(MCP_DELEGATED_BUILTIN_TOOL_NAMES)
        assert LOCAL_BUILTIN_TOOL_NAMES | MCP_DELEGATED_BUILTIN_TOOL_NAMES == BUILTIN_TOOL_NAMES
        assert is_local_builtin_tool("read_file")
        assert is_mcp_delegated_builtin_tool("read_mcp_resource")

    def test_runtime_tool_entries_match_registry_shape(self) -> None:
        entries = iter_builtin_runtime_tools()
        assert len(entries) == 13
        by_name = {entry["tool_name"]: entry for entry in entries}
        read_file = by_name["read_file"]
        assert read_file["source"] == "builtin"
        assert read_file["builtin"] is True
        assert read_file["parameters_schema"]["required"] == ["path"]
        assert read_file["risk_level"] == "low"
        assert read_file["execution_backend"] == "builtin"
        assert by_name["call_mcp_tool"]["execution_backend"] == "mcp"
        assert by_name["call_mcp_tool"]["requires_approval"] is True


class TestFileTools:
    """文件工具测试。"""

    @pytest.mark.asyncio()
    async def test_list_files(self, workspace: Path) -> None:
        result = await execute_builtin_tool("list_files", {}, workspace_path=str(workspace))
        assert result["ok"] is True
        paths = [e["path"] for e in result["entries"]]
        assert "src" in paths
        assert "README.md" in paths

    @pytest.mark.asyncio()
    async def test_list_files_path_traversal(self, workspace: Path) -> None:
        result = await execute_builtin_tool("list_files", {"path": "../../"}, workspace_path=str(workspace))
        assert result["ok"] is False
        assert result["error_code"] == "workspace.out_of_scope"

    @pytest.mark.asyncio()
    async def test_read_file(self, workspace: Path) -> None:
        result = await execute_builtin_tool("read_file", {"path": "src/main.py"}, workspace_path=str(workspace))
        assert result["ok"] is True
        assert "hello" in result["content"]
        assert result["start_line"] == 1

    @pytest.mark.asyncio()
    async def test_read_file_accepts_workspace_absolute_path(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "read_file",
            {"path": str(workspace / "src" / "main.py")},
            workspace_path=str(workspace),
        )
        assert result["ok"] is True
        assert result["path"] == "src/main.py"
        assert "hello" in result["content"]

    @pytest.mark.asyncio()
    async def test_read_file_with_line_range(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "read_file",
            {"path": "src/test.py", "start_line": 1, "line_count": 1},
            workspace_path=str(workspace),
        )
        assert result["ok"] is True
        assert result["end_line"] == 1
        assert "# test file" in result["content"]

    @pytest.mark.asyncio()
    async def test_read_file_traversal(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "read_file", {"path": "../../../etc/passwd"}, workspace_path=str(workspace)
        )
        assert result["ok"] is False
        assert result["error_code"] == "workspace.out_of_scope"

    @pytest.mark.asyncio()
    async def test_search_text(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "search_text", {"query": "hello"}, workspace_path=str(workspace)
        )
        assert result["ok"] is True
        assert len(result["matches"]) >= 1
        assert any("main.py" in m["path"] for m in result["matches"])

    @pytest.mark.asyncio()
    async def test_write_file_new(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "write_file",
            {"path": "new.txt", "content": "new content"},
            workspace_path=str(workspace),
        )
        assert result["ok"] is True
        assert result["created"] is True
        assert (workspace / "new.txt").read_text() == "new content"

    @pytest.mark.asyncio()
    async def test_write_file_no_overwrite(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "write_file",
            {"path": "README.md", "content": "overwritten"},
            workspace_path=str(workspace),
        )
        assert result["ok"] is False
        assert result["error_code"] == "tool.schema_invalid"

    @pytest.mark.asyncio()
    async def test_write_file_with_overwrite(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "write_file",
            {"path": "README.md", "content": "overwritten", "overwrite": True},
            workspace_path=str(workspace),
        )
        assert result["ok"] is True
        assert result["overwritten"] is True
        assert (workspace / "README.md").read_text() == "overwritten"

    @pytest.mark.asyncio()
    async def test_write_file_traversal(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "write_file",
            {"path": "../../evil.txt", "content": "evil"},
            workspace_path=str(workspace),
        )
        assert result["ok"] is False
        assert result["error_code"] == "workspace.out_of_scope"

    @pytest.mark.asyncio()
    async def test_schema_validation_rejects_invalid_argument_type(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "read_file", {"path": 123}, workspace_path=str(workspace)
        )
        assert result["ok"] is False
        assert result["error_code"] == "tool.schema_invalid"
        assert "path" in result["error"]

    @pytest.mark.asyncio()
    async def test_schema_validation_rejects_missing_required_argument(self, workspace: Path) -> None:
        result = await execute_builtin_tool("read_file", {}, workspace_path=str(workspace))
        assert result["ok"] is False
        assert result["error_code"] == "tool.schema_invalid"
        assert "missing required argument: path" in result["error"]

    @pytest.mark.asyncio()
    async def test_apply_patch_reports_changed_files(self, workspace: Path) -> None:
        patch = (
            "diff --git a/README.md b/README.md\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1,2 +1,2 @@\n"
            "-# Test Project\n"
            "+# Changed Project\n"
            " second\n"
        )
        result = await execute_builtin_tool(
            "apply_patch",
            {"patch": patch, "summary": "rename heading"},
            workspace_path=str(workspace),
        )
        assert result["ok"] is True
        assert result["changed_files"] == ["README.md"]
        assert (workspace / "README.md").read_text(encoding="utf-8") == "# Changed Project\nsecond\n"

    @pytest.mark.asyncio()
    async def test_apply_patch_rejects_escaping_path(self, workspace: Path) -> None:
        patch = (
            "diff --git a/README.md b/../evil.txt\n"
            "--- a/README.md\n"
            "+++ b/../evil.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-# Test Project\n"
            "+evil\n"
        )
        result = await execute_builtin_tool(
            "apply_patch",
            {"patch": patch, "summary": "escape workspace"},
            workspace_path=str(workspace),
        )
        assert result["ok"] is False
        assert result["error_code"] == "workspace.out_of_scope"


class TestCommandRiskClassification:
    """命令风险分类测试。"""

    def test_safe_commands(self) -> None:
        for cmd in ["pwd", "ls -la", "cat file.txt", "rg pattern", "git status", "git log"]:
            risk, _ = classify_command_risk(cmd)
            assert risk == "low", f"expected low for: {cmd}, got {risk}"

    def test_medium_commands(self) -> None:
        for cmd in ["npm run build", "pytest", "ruff check .", "eslint src/"]:
            risk, _ = classify_command_risk(cmd)
            assert risk == "medium", f"expected medium for: {cmd}, got {risk}"

    def test_high_commands(self) -> None:
        for cmd in ["npm install", "pip install requests", "curl http://example.com", "docker build ."]:
            risk, _ = classify_command_risk(cmd)
            assert risk == "high", f"expected high for: {cmd}, got {risk}"

    def test_critical_commands(self) -> None:
        for cmd in ["rm -rf /", "sudo rm file", "git push --force", "chmod 777 .", "kill -9 1234"]:
            risk, _ = classify_command_risk(cmd)
            assert risk == "critical", f"expected critical for: {cmd}, got {risk}"

    def test_credential_terms_detected(self) -> None:
        risk, reasons = classify_command_risk("echo $password")
        assert risk == "critical"
        assert any("credential" in r for r in reasons)

    @pytest.mark.asyncio()
    async def test_check_command_risk_tool(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "check_command_risk", {"cmd": "rm -rf /"}, workspace_path=str(workspace)
        )
        assert result["ok"] is True
        assert result["risk"] == "critical"
        assert result["requires_approval"] is True

    @pytest.mark.asyncio()
    async def test_run_command_safe(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "run_command", {"cmd": "echo hello", "timeout_ms": 5000}, workspace_path=str(workspace)
        )
        assert result["ok"] is True
        assert "hello" in result["stdout"]
        assert result["exit_code"] == 0

    @pytest.mark.asyncio()
    async def test_run_command_timeout(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "run_command", {"cmd": "sleep 10", "timeout_ms": 1000}, workspace_path=str(workspace)
        )
        assert result["ok"] is False
        assert result["error_code"] == "command.timeout"


class TestPermissionRiskOverride:
    """权限策略风险覆盖测试。"""

    def test_write_file_overwrite_high_risk(self) -> None:
        risk = get_builtin_tool_risk_override("write_file", {"overwrite": True})
        assert risk == "high"

    def test_write_file_no_overwrite_medium_risk(self) -> None:
        risk = get_builtin_tool_risk_override("write_file", {"overwrite": False})
        assert risk == "medium"

    def test_run_command_safe(self) -> None:
        risk = get_builtin_tool_risk_override("run_command", {"cmd": "ls"})
        assert risk == "low"

    def test_run_command_critical(self) -> None:
        risk = get_builtin_tool_risk_override("run_command", {"cmd": "rm -rf /"})
        assert risk == "critical"

    def test_http_post_high(self) -> None:
        risk = get_builtin_tool_risk_override("http_post", {})
        assert risk == "high"

    def test_requires_approval_forces_permission_ask(self, tmp_path: Path) -> None:
        from services.agent_runtime.v2.permission_policy import PermissionPolicy
        from services.agent_runtime.v2.permission_store import PermissionStore

        decision = PermissionPolicy(PermissionStore(tmp_path)).evaluate(
            run_id="run-1",
            call_id="call-1",
            tool_name="apply_patch",
            args={"patch": "diff --git a/a.txt b/a.txt\n", "summary": "x"},
            tool_entry={
                "tool_name": "apply_patch",
                "risk_level": "medium",
                "requires_approval": True,
                "permission_scope": "workspace",
            },
        )

        assert decision.behavior == "ask"
        assert decision.risk_level == "medium"


class TestUnknownTool:
    """未知工具和错误处理。"""

    @pytest.mark.asyncio()
    async def test_unknown_tool(self, workspace: Path) -> None:
        result = await execute_builtin_tool("unknown_tool", {}, workspace_path=str(workspace))
        assert result["ok"] is False
        assert result["error_code"] == "tool.not_found"

    @pytest.mark.asyncio()
    async def test_missing_workspace(self) -> None:
        result = await execute_builtin_tool("list_files", {}, workspace_path="")
        assert result["ok"] is False
        assert result["error_code"] == "tool.schema_invalid"

    @pytest.mark.asyncio()
    async def test_mcp_delegated_tool_is_not_local_tool_not_found(self, workspace: Path) -> None:
        result = await execute_builtin_tool(
            "read_mcp_resource",
            {"server": "query-center", "uri": "query://usage-guide"},
            workspace_path=str(workspace),
        )
        assert result["ok"] is False
        assert result["error_code"] == "tool.mcp_delegated"


class TestToolExecutorIntegration:
    """ToolExecutor 与内置工具分发集成。"""

    @pytest.mark.asyncio()
    async def test_local_builtin_routes_to_builtin_executor(self, workspace: Path) -> None:
        from services.tool_executor import ToolExecutor

        executor = ToolExecutor(
            "proj-1",
            "emp-1",
            host_workspace_path=str(workspace),
        )

        result = await executor._execute_tool("read_file", {"path": "README.md"})

        assert result["ok"] is True
        assert "# Test Project" in result["content"]

    @pytest.mark.asyncio()
    async def test_mcp_delegated_builtin_falls_through_to_mcp_runtime(self, monkeypatch, workspace: Path) -> None:
        from services.tool_executor import ToolExecutor

        captured: dict[str, object] = {}

        def fake_invoke_project_tool_runtime(**kwargs):
            captured.update(kwargs)
            return {"ok": True, "source": "mcp-runtime"}

        monkeypatch.setattr(
            "services.mcp.dynamic_mcp_runtime.invoke_project_tool_runtime",
            fake_invoke_project_tool_runtime,
        )

        executor = ToolExecutor(
            "proj-1",
            "emp-1",
            host_workspace_path=str(workspace),
        )

        result = await executor._execute_tool(
            "read_mcp_resource",
            {"server": "query-center", "uri": "query://usage-guide"},
        )

        assert result == {"ok": True, "source": "mcp-runtime"}
        assert captured["tool_name"] == "read_mcp_resource"
