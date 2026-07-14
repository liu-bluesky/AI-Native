import asyncio
from contextvars import ContextVar
from pathlib import Path

from services.mcp import dynamic_mcp_apps_project as project_mcp


def test_project_mcp_binds_single_query_project_rules_function(monkeypatch, tmp_path: Path):
    captured = {}

    class _FakeProject:
        id = "proj-1"
        name = "项目一"
        description = ""
        mcp_enabled = True
        feedback_upgrade_enabled = False

    monkeypatch.setattr(
        project_mcp,
        "project_store",
        type("Store", (), {"get": staticmethod(lambda project_id: _FakeProject() if project_id == "proj-1" else None)})(),
    )
    monkeypatch.setattr(project_mcp, "_build_project_proxy_specs", lambda _project_id: ({}, {}))
    monkeypatch.setattr(project_mcp, "list_project_external_tools_runtime", lambda _project_id: [])
    monkeypatch.setattr(project_mcp, "_active_project_member_employees", lambda _project_id: [])

    def fake_query_project_rules(project_id: str, keyword: str = "", employee_id: str = ""):
        captured.update(
            project_id=project_id,
            keyword=keyword,
            employee_id=employee_id,
        )
        return []

    monkeypatch.setattr(project_mcp, "query_project_rules", fake_query_project_rules)
    server = project_mcp.build_project_mcp_server(
        "proj-1",
        current_api_key_ctx=ContextVar("key", default=""),
        current_developer_name_ctx=ContextVar("developer", default=""),
        project_root=tmp_path,
        recall_limit=20,
        list_project_tools_fn=lambda _project_id, _employee_id="": [],
        invoke_project_tool_fn=lambda **_kwargs: {},
    )

    tools = asyncio.run(server.list_tools())
    rule_tool = next(item for item in tools if item.name == "query_project_rules")
    assert set(rule_tool.inputSchema["properties"]) == {"keyword", "employee_id"}

    asyncio.run(
        server.call_tool(
            "query_project_rules",
            {"keyword": "css", "employee_id": "emp-1"},
        )
    )
    assert captured == {
        "project_id": "proj-1",
        "keyword": "css",
        "employee_id": "emp-1",
    }
