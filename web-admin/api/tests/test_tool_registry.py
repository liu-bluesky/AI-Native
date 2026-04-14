from services.runtime import tool_registry


def test_resolve_chat_workspace_path_prefers_connector_workspace():
    assert (
        tool_registry.resolve_chat_workspace_path(
            "/workspace/project",
            {"connector_workspace_path": "/workspace/connector"},
        )
        == "/workspace/connector"
    )
    assert (
        tool_registry.resolve_chat_workspace_path(
            "/workspace/project",
            {"connector_workspace_path": "   "},
        )
        == "/workspace/project"
    )


def test_resolve_local_connector_runtime_tools_builds_coding_tools():
    connector = object()

    tools, selected_connector, sandbox_mode = tool_registry.resolve_local_connector_runtime_tools(
        {
            "local_connector_id": "connector-1",
            "connector_workspace_path": "/workspace/connector",
            "connector_sandbox_mode": "read-only",
        },
        "/workspace/project",
        resolve_local_connector=lambda connector_id: connector if connector_id == "connector-1" else None,
        build_connector_tools=lambda: [
            {"tool_name": "local_connector_read_file", "description": "Read"},
            {"tool_name": "", "description": "ignored"},
        ],
    )

    assert selected_connector is connector
    assert sandbox_mode == "read-only"
    assert tools == [
        {
            "tool_name": "local_connector_read_file",
            "description": "Read",
            "workspace_path": "/workspace/connector",
            "sandbox_mode": "read-only",
        }
    ]


def test_collect_project_runtime_tools_filters_employee_and_name_and_priority():
    internal_tools = [
        {"tool_name": "emp_a__tool", "employee_id": "emp-a", "description": "A"},
        {"tool_name": "emp_b__tool", "employee_id": "emp-b", "description": "B"},
        {"tool_name": "query_project_rules", "employee_id": "", "builtin": True},
    ]
    external_tools = [
        {"tool_name": "external_search", "module_type": "external_mcp_tool"},
    ]

    result = tool_registry.collect_project_runtime_tools(
        "proj-1",
        selected_employee_ids=["emp-a"],
        enabled_tool_names=["query_project_rules", "emp_a__tool", "external_search"],
        tool_priority=["external_search", "emp_a__tool"],
        list_internal_tools=lambda project_id: list(internal_tools),
        list_external_tools=lambda project_id: list(external_tools),
    )

    assert [item["tool_name"] for item in result] == [
        "external_search",
        "emp_a__tool",
        "query_project_rules",
    ]


def test_summarize_effective_tools_infers_sources():
    summarized, total = tool_registry.summarize_effective_tools(
        [
            {"tool_name": "local_connector_read_file"},
            {"tool_name": "ext_tool", "module_type": "external_mcp_tool"},
            {"tool_name": "sys_tool", "module_type": "system_mcp_tool"},
            {"tool_name": "builtin_tool", "builtin": True},
            {"tool_name": "skill_tool", "employee_id": "emp-1"},
            {"tool_name": "project_tool"},
        ]
    )

    assert total == 6
    assert [item["source"] for item in summarized] == [
        "local_connector",
        "external_mcp",
        "system_mcp",
        "builtin",
        "project_skill",
        "project_tool",
    ]
