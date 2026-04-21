"""项目聊天任务树路由测试"""

from fastapi.testclient import TestClient


def _build_project_chat_task_tree_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in (
        "role_store",
        "system_config_store",
        "project_store",
        "project_chat_store",
        "project_chat_task_store",
        "work_session_store",
        "task_tree_evolution_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), store_factory


def test_project_chat_task_tree_routes_generate_update_and_clear(tmp_path, monkeypatch):
    from services.dynamic_mcp_collaboration import invoke_project_builtin_tool
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "在 AI 对话里展示当前执行任务，并且完成节点时必须填写验证",
        },
    )
    assert generate_response.status_code == 200
    payload = generate_response.json()["task_tree"]
    assert payload["chat_session_id"] == chat_session_id
    assert payload["progress_percent"] == 0
    assert len(payload["nodes"]) >= 2
    task_tree_session_id = payload["id"]
    leaf_node = next(item for item in payload["nodes"] if int(item["level"]) == 1)
    root_node = next(item for item in payload["nodes"] if int(item["level"]) == 0)
    assert root_node["node_kind"] == "goal"
    assert root_node["objective"]
    assert root_node["completion_criteria"]
    assert root_node["verification_method"]
    assert leaf_node["node_kind"] == "plan_step"
    assert leaf_node["objective"]
    assert leaf_node["completion_criteria"]
    assert leaf_node["verification_method"]

    start_response = client.patch(
        f"/api/projects/proj-1/chat/task-tree/nodes/{leaf_node['id']}",
        json={
            "chat_session_id": chat_session_id,
            "status": "in_progress",
            "is_current": True,
        },
    )
    assert start_response.status_code == 200
    start_payload = start_response.json()["task_tree"]
    assert start_payload["progress_percent"] > 0
    assert start_payload["progress_percent"] < 100

    work_events_after_start = client.get(
        "/api/projects/proj-1/work-session-events",
        params={"task_tree_session_id": task_tree_session_id},
    )
    assert work_events_after_start.status_code == 200
    start_items = work_events_after_start.json()["items"]
    assert len(start_items) >= 2
    event_types_after_start = {str(item.get("event_type") or "") for item in start_items}
    assert "task_tree_started" in event_types_after_start
    assert "task_node_progressed" in event_types_after_start or "task_node_updated" in event_types_after_start

    invalid_done_response = client.patch(
        f"/api/projects/proj-1/chat/task-tree/nodes/{leaf_node['id']}",
        json={
            "chat_session_id": chat_session_id,
            "status": "done",
        },
    )
    assert invalid_done_response.status_code == 400
    assert "verification_result" in invalid_done_response.json()["detail"]

    valid_done_response = client.patch(
        f"/api/projects/proj-1/chat/task-tree/nodes/{leaf_node['id']}",
        json={
            "chat_session_id": chat_session_id,
            "status": "done",
            "verification_result": "已完成人工验证，并确认页面状态正确",
            "summary_for_model": "该节点已完成，验证通过",
            "is_current": True,
        },
    )
    assert valid_done_response.status_code == 200
    updated_payload = valid_done_response.json()["task_tree"]
    assert updated_payload["current_node_id"]
    assert updated_payload["progress_percent"] > 0

    work_events_after_done = client.get(
        "/api/projects/proj-1/work-session-events",
        params={"task_tree_session_id": task_tree_session_id, "task_node_id": leaf_node["id"]},
    )
    assert work_events_after_done.status_code == 200
    done_items = work_events_after_done.json()["items"]
    assert any(str(item.get("event_type") or "") == "task_node_completed" for item in done_items)
    assert any(
        "已完成人工验证" in " ".join(item.get("verification") or [])
        for item in done_items
    )

    invalid_root_done_response = client.patch(
        f"/api/projects/proj-1/chat/task-tree/nodes/{root_node['id']}",
        json={
            "chat_session_id": chat_session_id,
            "status": "done",
            "verification_result": "根任务验证",
        },
    )
    assert invalid_root_done_response.status_code == 400
    assert "started before completion" in invalid_root_done_response.json()["detail"]

    get_response = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    )
    assert get_response.status_code == 200
    assert get_response.json()["task_tree"]["chat_session_id"] == chat_session_id

    builtin_tree = invoke_project_builtin_tool(
        "proj-1",
        "get_current_task_tree",
        username="tester",
        chat_session_id=chat_session_id,
        args={},
    )
    assert builtin_tree["tool_name"] == "get_current_task_tree"
    assert builtin_tree["chat_session_id"] == chat_session_id

    builtin_update = invoke_project_builtin_tool(
        "proj-1",
        "update_task_node_status",
        username="tester",
        chat_session_id=chat_session_id,
        args={
            "node_id": leaf_node["id"],
            "status": "verifying",
            "verification_result": "进入二次验证",
        },
    )
    assert builtin_update["tool_name"] == "update_task_node_status"
    assert builtin_update["node_id"] == leaf_node["id"]

    delete_tree_response = client.delete(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    )
    assert delete_tree_response.status_code == 200
    assert delete_tree_response.json()["removed_count"] == 1

    after_delete_tree_response = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    )
    assert after_delete_tree_response.status_code == 200
    assert after_delete_tree_response.json()["task_tree"] is None

    regenerate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "在 AI 对话里展示当前执行任务，并且完成节点时必须填写验证",
        },
    )
    assert regenerate_response.status_code == 200

    sessions_response = client.get("/api/projects/proj-1/chat/task-tree/sessions")
    assert sessions_response.status_code == 200
    sessions_payload = sessions_response.json()
    assert sessions_payload["storage_backend"] == "json"
    assert len(sessions_payload["items"]) == 1
    assert sessions_payload["items"][0]["chat_session_id"] == chat_session_id
    assert sessions_payload["items"][0]["username"] == "tester"

    manual_response = client.get("/api/projects/proj-1/manual-template")
    assert manual_response.status_code == 200
    manual_text = str(manual_response.json()["manual"] or "")
    assert "## 任务树工作流" in manual_text
    assert "不得把 `search_project_context`、`query_project_rules`" in manual_text

    clear_response = client.delete(
        "/api/projects/proj-1/chat/history",
        params={"chat_session_id": chat_session_id},
    )
    assert clear_response.status_code == 200

    after_clear_response = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    )
    assert after_clear_response.status_code == 200


def test_project_workflow_skill_routes_enable_and_set_default(tmp_path, monkeypatch):
    from stores import mcp_bridge
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    mcp_bridge.skill_store.save(
        mcp_bridge.Skill(
            id="query-mcp-workflow",
            version="1.0.0",
            name="Query MCP Workflow",
            description="统一查询 MCP 工作流稳定化技能",
            mcp_service="query-center-project",
            package_dir="mcp-skills/knowledge/skill-packages/query-mcp-workflow",
            mcp_enabled=True,
        )
    )

    enable_response = client.post(
        "/api/projects/proj-1/workflow-skills",
        json={"skill_id": "query-mcp-workflow"},
    )
    assert enable_response.status_code == 200
    assert enable_response.json()["status"] == "enabled"

    default_response = client.put(
        "/api/projects/proj-1/workflow-skills/default",
        json={"skill_id": "query-mcp-workflow"},
    )
    assert default_response.status_code == 200
    assert default_response.json()["default_workflow_skill"]["id"] == "query-mcp-workflow"

    detail_response = client.get("/api/projects/proj-1")
    assert detail_response.status_code == 200
    project_payload = detail_response.json()["project"]
    assert project_payload["workflow_skill_ids"] == ["query-mcp-workflow"]
    assert project_payload["default_workflow_skill_id"] == "query-mcp-workflow"
    assert project_payload["default_workflow_skill"]["id"] == "query-mcp-workflow"

    workflow_response = client.get("/api/projects/proj-1/workflow-skills")
    assert workflow_response.status_code == 200
    workflow_payload = workflow_response.json()
    assert workflow_payload["workflow_skill_bindings"][0]["id"] == "query-mcp-workflow"
    assert workflow_payload["workflow_skill_bindings"][0]["is_default"] is True


def test_project_chat_task_tree_routes_reconcile_stale_progress_from_work_events(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig
    from stores.json.work_session_store import WorkSessionEvent

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "优化项目详情页任务树展示，避免 CLI 结束后仍显示进行中",
        },
    )
    assert generate_response.status_code == 200
    task_tree = generate_response.json()["task_tree"]
    session = store_factory.project_chat_task_store.get("proj-1", "tester", chat_session_id)
    assert session is not None
    root_node = next(node for node in session.nodes if not node.parent_id)
    analysis_node = next(node for node in session.nodes if node.stage_key == "analysis")
    implementation_node = next(node for node in session.nodes if node.stage_key == "implementation")
    verification_node = next(node for node in session.nodes if node.stage_key == "verification")

    analysis_node.status = "in_progress"
    analysis_node.verification_result = ""
    implementation_node.status = "pending"
    implementation_node.verification_result = ""
    verification_node.status = "done"
    verification_node.verification_result = "Vite build passed without syntax errors."
    root_node.status = "in_progress"
    root_node.verification_result = ""
    session.current_node_id = analysis_node.id
    store_factory.project_chat_task_store.save(session)

    work_session_id = f"ws_{task_tree['id']}"
    for event in (
        WorkSessionEvent(
            id=store_factory.work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="tester",
            session_id=work_session_id,
            task_tree_session_id=task_tree["id"],
            task_tree_chat_session_id=chat_session_id,
            task_node_id=analysis_node.id,
            task_node_title=analysis_node.title,
            source_kind="work-facts",
            phase="analysis",
            step=analysis_node.title,
            status="completed",
            verification=["已完成页面现状和噪音来源梳理。"],
        ),
        WorkSessionEvent(
            id=store_factory.work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="tester",
            session_id=work_session_id,
            task_tree_session_id=task_tree["id"],
            task_tree_chat_session_id=chat_session_id,
            task_node_id=implementation_node.id,
            task_node_title=implementation_node.title,
            source_kind="work-facts",
            phase="implementation",
            step=implementation_node.title,
            status="in_progress",
            verification=["已完成树形结构降噪和主干样式强化。"],
        ),
        WorkSessionEvent(
            id=store_factory.work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="tester",
            session_id=work_session_id,
            task_tree_session_id=task_tree["id"],
            task_tree_chat_session_id=chat_session_id,
            task_node_id=verification_node.id,
            task_node_title=verification_node.title,
            source_kind="session-event",
            event_type="verification",
            phase="verification",
            step=verification_node.title,
            status="completed",
            verification=["Vite build passed without syntax errors."],
        ),
    ):
        store_factory.work_session_store.save(event)

    tree_response = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    )
    assert tree_response.status_code == 200
    reconciled_tree = tree_response.json()["task_tree"]
    assert reconciled_tree["status"] == "done"
    assert reconciled_tree["progress_percent"] == 100
    reconciled_nodes = {item["stage_key"]: item for item in reconciled_tree["nodes"]}
    assert reconciled_nodes["analysis"]["status"] == "done"
    assert "已完成页面现状和噪音来源梳理" in reconciled_nodes["analysis"]["verification_result"]
    assert reconciled_nodes["implementation"]["status"] == "done"
    assert "已完成树形结构降噪和主干样式强化" in reconciled_nodes["implementation"]["verification_result"]
    assert reconciled_nodes["verification"]["status"] == "done"
    assert reconciled_nodes["goal"]["status"] == "done"

    sessions_response = client.get("/api/projects/proj-1/chat/task-tree/sessions")
    assert sessions_response.status_code == 200
    session_summary = next(item for item in sessions_response.json()["items"] if item["id"] == task_tree["id"])
    assert session_summary["status"] == "done"
    assert session_summary["progress_percent"] == 100


def test_project_chat_ongoing_task_state_returns_active_resume_payload(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "修复中断后任务恢复提示",
        },
    )
    assert generate_response.status_code == 200
    task_tree = generate_response.json()["task_tree"]

    start_response = client.patch(
        f"/api/projects/proj-1/chat/task-tree/nodes/{task_tree['current_node_id']}",
        json={
            "chat_session_id": chat_session_id,
            "status": "in_progress",
            "is_current": True,
        },
    )
    assert start_response.status_code == 200

    ongoing_response = client.get("/api/projects/proj-1/chat/task-tree/ongoing")
    assert ongoing_response.status_code == 200
    payload = ongoing_response.json()
    assert payload["active_task_exists"] is True
    assert payload["needs_resume"] is True
    assert payload["can_continue"] is True
    assert payload["resume_reason"] == "needs_resume"
    assert payload["chat_session_id"] == chat_session_id
    assert payload["task_tree"]["chat_session_id"] == chat_session_id
    assert payload["current_node_title"]
    assert "未完成" in payload["user_message"]


def test_project_chat_ongoing_task_state_ignores_archived_done_task(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "当前项目做什么的",
        },
    )
    assert generate_response.status_code == 200

    from services.project_chat_task_tree import audit_task_tree_round

    audit_payload = audit_task_tree_round(
        project_id="proj-1",
        username="tester",
        chat_session_id=chat_session_id,
        assistant_content="当前项目定位是 AI 对话和 AI 图片视频生成。",
        successful_tool_names=["get_manual_content"],
        task_tree_tool_used=False,
    )
    assert audit_payload["history_task_tree"]["status"] == "done"
    assert audit_payload["history_task_tree"]["is_archived"] is True

    ongoing_response = client.get("/api/projects/proj-1/chat/task-tree/ongoing")
    assert ongoing_response.status_code == 200
    payload = ongoing_response.json()
    assert payload["active_task_exists"] is False
    assert payload["can_continue"] is False
    assert payload["task_tree"] is None


def test_project_chat_ongoing_task_state_marks_orphaned_query_state(tmp_path, monkeypatch):
    from services import query_mcp_project_state as state_service
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store_factory.project_store.save(
        ProjectConfig(id="proj-1", name="项目一", workspace_path=str(workspace))
    )

    state_service.save_query_mcp_project_state(
        project_id="proj-1",
        chat_session_id="chat-orphan",
        session_id="ws-orphan",
        root_goal="恢复之前的任务",
        latest_status="in_progress",
        step="等待恢复",
        source="test",
    )

    ongoing_response = client.get("/api/projects/proj-1/chat/task-tree/ongoing")
    assert ongoing_response.status_code == 200
    payload = ongoing_response.json()
    assert payload["active_task_exists"] is False
    assert payload["needs_resume"] is True
    assert payload["orphaned_state"] is True
    assert payload["can_continue"] is False
    assert payload["resume_reason"] == "orphaned_state"
    assert payload["chat_session_id"] == "chat-orphan"
    assert payload["query_mcp_state"]["chat_session_id"] == "chat-orphan"
    assert payload["resumable_query_mcp_state"]["session_id"] == "ws-orphan"


def test_project_chat_task_tree_routes_reconcile_prior_node_without_explicit_verification(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig
    from stores.json.work_session_store import WorkSessionEvent

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "/ai/chat/settings/projects/proj-d16591a6?tab=memory 展示内容太多，需要改成更清晰的纵向树结构",
        },
    )
    assert generate_response.status_code == 200
    task_tree = generate_response.json()["task_tree"]
    session = store_factory.project_chat_task_store.get("proj-1", "tester", chat_session_id)
    assert session is not None

    root_node = next(node for node in session.nodes if not node.parent_id)
    analysis_node = next(node for node in session.nodes if node.stage_key == "analysis")
    implementation_node = next(node for node in session.nodes if node.stage_key == "implementation")
    verification_node = next(node for node in session.nodes if node.stage_key == "verification")

    analysis_node.status = "verifying"
    analysis_node.verification_result = ""
    implementation_node.status = "done"
    implementation_node.verification_result = "已完成树形结构和视觉降噪改造。"
    verification_node.status = "done"
    verification_node.verification_result = "npm run build 成功。"
    root_node.status = "in_progress"
    root_node.verification_result = ""
    session.current_node_id = analysis_node.id
    store_factory.project_chat_task_store.save(session)

    work_session_id = f"ws_{task_tree['id']}"
    for event in (
        WorkSessionEvent(
            id=store_factory.work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="tester",
            session_id=work_session_id,
            task_tree_session_id=task_tree["id"],
            task_tree_chat_session_id=chat_session_id,
            task_node_id=analysis_node.id,
            task_node_title=analysis_node.title,
            source_kind="session-start",
            event_type="start",
            phase="analysis",
            step=analysis_node.title,
            status="in_progress",
            content="开始梳理当前页面结构与切换路径。",
        ),
        WorkSessionEvent(
            id=store_factory.work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="tester",
            session_id=work_session_id,
            task_tree_session_id=task_tree["id"],
            task_tree_chat_session_id=chat_session_id,
            task_node_id=implementation_node.id,
            task_node_title=implementation_node.title,
            source_kind="work-facts",
            phase="implementation",
            step=implementation_node.title,
            status="completed",
            verification=["已完成树形结构和视觉降噪改造。"],
        ),
        WorkSessionEvent(
            id=store_factory.work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="tester",
            session_id=work_session_id,
            task_tree_session_id=task_tree["id"],
            task_tree_chat_session_id=chat_session_id,
            task_node_id=verification_node.id,
            task_node_title=verification_node.title,
            source_kind="session-event",
            event_type="verification",
            phase="verification",
            step=verification_node.title,
            status="completed",
            verification=["npm run build 成功。"],
        ),
    ):
        store_factory.work_session_store.save(event)

    tree_response = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    )
    assert tree_response.status_code == 200
    reconciled_tree = tree_response.json()["task_tree"]
    reconciled_nodes = {item["stage_key"]: item for item in reconciled_tree["nodes"]}
    assert reconciled_tree["status"] == "done"
    assert reconciled_tree["progress_percent"] == 100
    assert reconciled_nodes["analysis"]["status"] == "done"
    assert "系统收口" in reconciled_nodes["analysis"]["verification_result"]
    assert reconciled_nodes["goal"]["status"] == "done"


def test_project_chat_task_tree_audit_keeps_unverified_completion_out_of_done(
    tmp_path,
    monkeypatch,
):
    from services.project_chat_task_tree import audit_task_tree_round
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "修复任务树自动推进的误判完成问题",
        },
    )
    assert generate_response.status_code == 200

    audit_payload = audit_task_tree_round(
        project_id="proj-1",
        username="tester",
        chat_session_id=chat_session_id,
        assistant_content="已完成修复，测试通过，请进入下一步",
        successful_tool_names=["search_project_context"],
        task_tree_tool_used=False,
    )

    assert audit_payload is not None
    assert audit_payload["code"] == "completion_unverified"
    assert audit_payload["severity"] == "high"
    assert audit_payload["category"] == "verification_guard"
    assert audit_payload["message"]
    assert audit_payload["recommended_action"]
    assert any("当前节点：" in item for item in audit_payload["evidence"])
    assert any("建议状态：" in item for item in audit_payload["evidence"])
    assert audit_payload["auto_updated"] is True
    assert audit_payload["suggested_status"] == "verifying"
    assert audit_payload["task_tree"]["current_node"]["status"] == "verifying"
    assert audit_payload["task_tree"]["status"] in {"pending", "in_progress"}


def test_project_chat_task_tree_audit_auto_completes_leaf_when_completion_and_verification_are_both_present(
    tmp_path,
    monkeypatch,
):
    from services.project_chat_task_tree import audit_task_tree_round
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "修复任务树进入 33% 后不往下推进的问题",
        },
    )
    assert generate_response.status_code == 200

    audit_payload = audit_task_tree_round(
        project_id="proj-1",
        username="tester",
        chat_session_id=chat_session_id,
        assistant_content="已完成当前问题定位并修复，已通过 git diff 和日志确认修改正确，继续下一步。",
        successful_tool_names=["local_connector_read_file", "local_connector_run_command"],
        task_tree_tool_used=False,
    )

    assert audit_payload is not None
    assert audit_payload["code"] == "step_auto_completed"
    assert audit_payload["severity"] == "low"
    assert audit_payload["category"] == "task_tree_auto_completion"
    assert audit_payload["auto_updated"] is True
    assert audit_payload["task_tree"]["progress_percent"] >= 33
    completed_leaf = next(
        item
        for item in audit_payload["task_tree"]["nodes"]
        if int(item["level"]) == 1 and item["stage_key"] == "analysis"
    )
    assert completed_leaf["status"] == "done"
    assert "系统自动验证" in completed_leaf["verification_result"]


def test_project_chat_task_tree_audit_auto_completes_context_bootstrap_step(
    tmp_path,
    monkeypatch,
):
    from core.deps import project_chat_task_store
    from services.project_chat_task_tree import audit_task_tree_round
    from stores.json.project_chat_task_store import ProjectChatTaskNode, ProjectChatTaskSession
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    chat_session_id = "chat-session-bootstrap-1"
    session_id = "tts-bootstrap-1"
    root_node = ProjectChatTaskNode(
        id="node-root-1",
        session_id=session_id,
        title="修复统一 MCP 接入后任务树上下文节点不推进的问题",
        description="根任务",
        level=0,
        sort_order=0,
        status="pending",
    )
    context_node = ProjectChatTaskNode(
        id="node-context-1",
        session_id=session_id,
        parent_id=root_node.id,
        title="先统一检索项目上下文、成员、规则和 MCP 能力。",
        description="建议工具：search_project_context\n阶段：context",
        level=1,
        sort_order=1,
        status="pending",
    )
    implementation_node = ProjectChatTaskNode(
        id="node-impl-1",
        session_id=session_id,
        parent_id=root_node.id,
        title="进入实现步骤",
        description="上下文预检完成后继续推进主任务。",
        level=1,
        sort_order=2,
        status="pending",
    )
    project_chat_task_store.save(
        ProjectChatTaskSession(
            id=session_id,
            project_id="proj-1",
            username="tester",
            chat_session_id=chat_session_id,
            title="修复统一 MCP 接入后任务树上下文节点不推进的问题",
            root_goal="修复统一 MCP 接入后任务树上下文节点不推进的问题",
            current_node_id=context_node.id,
            nodes=[root_node, context_node, implementation_node],
        )
    )
    payload_before = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    ).json()["task_tree"]
    current_node_before = payload_before["current_node"]
    assert current_node_before["status"] == "pending"

    audit_payload = audit_task_tree_round(
        project_id="proj-1",
        username="tester",
        chat_session_id=chat_session_id,
        assistant_content="本轮已拉取项目上下文，下面继续进入实现步骤。",
        successful_tool_names=["search_project_context"],
        task_tree_tool_used=False,
    )

    assert audit_payload is not None
    assert audit_payload["code"] == "bootstrap_step_auto_completed"
    assert audit_payload["severity"] == "low"
    assert audit_payload["category"] == "context_bootstrap"
    assert audit_payload["recommended_action"]
    assert any("自动完成上下文预检节点" in item for item in audit_payload["evidence"])
    assert audit_payload["auto_updated"] is True
    assert audit_payload["task_tree"]["progress_percent"] > 0
    assert audit_payload["task_tree"]["current_node"]["id"] != current_node_before["id"]
    completed_node = next(
        item for item in audit_payload["task_tree"]["nodes"] if item["id"] == current_node_before["id"]
    )
    assert completed_node["status"] == "done"
    assert "search_project_context" in completed_node["verification_result"]


def test_project_chat_task_tree_generates_single_step_for_lookup_query(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "当前项目员工都有谁",
        },
    )
    assert generate_response.status_code == 200
    payload = generate_response.json()["task_tree"]
    leaf_nodes = [item for item in payload["nodes"] if int(item["level"]) == 1]
    assert len(leaf_nodes) == 1
    assert "检索问题所需信息并直接回答用户" in leaf_nodes[0]["title"]


def test_project_chat_task_tree_generates_single_step_for_colloquial_lookup_query(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "当前项目做什么的",
        },
    )
    assert generate_response.status_code == 200
    payload = generate_response.json()["task_tree"]
    leaf_nodes = [item for item in payload["nodes"] if int(item["level"]) == 1]
    assert len(leaf_nodes) == 1
    assert "检索问题所需信息并直接回答用户" in leaf_nodes[0]["title"]


def test_project_chat_task_tree_generates_single_step_for_diagnostic_lookup_query(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "检查为什么新需求 '#/pages/attendance/addrule 这个页面的 补卡申请 按钮 激活颜色没变化 更换成 rgb(39, 181, 156) 这个颜色' 又卡在 33%",
        },
    )
    assert generate_response.status_code == 200
    payload = generate_response.json()["task_tree"]
    leaf_nodes = [item for item in payload["nodes"] if int(item["level"]) == 1]
    assert len(leaf_nodes) == 1
    assert payload["task_tree_health"]["detected_intent"] == "lookup_query"
    assert "检索问题所需信息并直接回答用户" in leaf_nodes[0]["title"]


def test_project_chat_task_tree_governance_goal_avoids_tabs_template(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "升级统一MCP任务树持久化方案，让前端页面直接看到反馈并支持中断恢复",
        },
    )
    assert generate_response.status_code == 200
    payload = generate_response.json()["task_tree"]
    leaf_nodes = [item for item in payload["nodes"] if int(item["level"]) == 1]
    assert leaf_nodes
    assert not any("Tabs" in item["title"] or "切换路径" in item["title"] for item in leaf_nodes)
    health = payload["task_tree_health"]
    assert health["detected_intent"] == "governance"
    assert health["rebuild_recommended"] is False
    assert health["safe_to_display"] is True


def test_project_chat_task_tree_health_flags_template_goal_mismatch(
    tmp_path,
    monkeypatch,
):
    from core.deps import project_chat_task_store
    from services.project_chat_task_tree import serialize_task_tree
    from stores.json.project_chat_task_store import ProjectChatTaskNode, ProjectChatTaskSession
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    chat_session_id = "chat-session-health-1"
    session_id = "tts-health-1"
    root_node = ProjectChatTaskNode(
        id="node-root-health-1",
        session_id=session_id,
        title="升级统一MCP任务树持久化方案，让前端页面直接看到反馈并支持中断恢复",
        description="根任务",
        level=0,
        sort_order=0,
        status="pending",
    )
    wrong_ui_node = ProjectChatTaskNode(
        id="node-ui-health-1",
        session_id=session_id,
        parent_id=root_node.id,
        title="改造成页内 Tabs 切换并保持状态同步",
        description="围绕错误模板推进页面切换改造。",
        level=1,
        sort_order=1,
        status="pending",
    )
    verification_node = ProjectChatTaskNode(
        id="node-verify-health-1",
        session_id=session_id,
        parent_id=root_node.id,
        title="验证结果并完成本轮收尾",
        description="验证当前治理任务结果。",
        level=1,
        sort_order=2,
        status="pending",
    )
    saved = project_chat_task_store.save(
        ProjectChatTaskSession(
            id=session_id,
            project_id="proj-1",
            username="tester",
            chat_session_id=chat_session_id,
            title=root_node.title,
            root_goal=root_node.title,
            current_node_id=wrong_ui_node.id,
            nodes=[root_node, wrong_ui_node, verification_node],
        )
    )

    payload = serialize_task_tree(saved)
    assert payload is not None
    health = payload["task_tree_health"]
    assert health["detected_intent"] == "governance"
    assert health["rebuild_recommended"] is True
    assert health["safe_to_display"] is False
    issue_codes = {item["code"] for item in health["issues"]}
    assert "template_goal_mismatch" in issue_codes


def test_project_chat_task_tree_generation_mismatch_records_evolution_sample(
    tmp_path,
    monkeypatch,
):
    from core.deps import project_chat_task_store
    from services.project_chat_task_tree import _record_task_tree_health_evolution_samples
    from stores.json.project_chat_task_store import ProjectChatTaskNode, ProjectChatTaskSession
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    chat_session_id = "chat-session-health-sample-1"
    session_id = "tts-health-sample-1"
    root_goal = "升级统一MCP任务树持久化方案，让前端页面直接看到反馈并支持中断恢复"
    root_node = ProjectChatTaskNode(
        id="node-root-health-sample-1",
        session_id=session_id,
        title=root_goal,
        description="根任务",
        level=0,
        sort_order=0,
        status="pending",
    )
    wrong_ui_node = ProjectChatTaskNode(
        id="node-ui-health-sample-1",
        session_id=session_id,
        parent_id=root_node.id,
        title="改造成页内 Tabs 切换并保持状态同步",
        description="围绕错误模板推进页面切换改造。",
        level=1,
        sort_order=1,
        status="pending",
    )
    verification_node = ProjectChatTaskNode(
        id="node-verify-health-sample-1",
        session_id=session_id,
        parent_id=root_node.id,
        title="验证结果并完成本轮收尾",
        description="验证当前治理任务结果。",
        level=1,
        sort_order=2,
        status="pending",
    )
    session = project_chat_task_store.save(
        ProjectChatTaskSession(
            id=session_id,
            project_id="proj-1",
            username="tester",
            chat_session_id=chat_session_id,
            title=root_goal,
            root_goal=root_goal,
            current_node_id=wrong_ui_node.id,
            nodes=[root_node, wrong_ui_node, verification_node],
        )
    )

    _record_task_tree_health_evolution_samples(session)

    samples = store_factory.task_tree_evolution_store.list_samples(
        project_id="proj-1",
        chat_session_id=chat_session_id,
        source_kind="generation",
    )
    assert samples
    assert samples[0].issue_code == "template_goal_mismatch"
    assert samples[0].wrong_template == "ui_flow"
    assert samples[0].corrected_template == "governance"


def test_project_chat_task_tree_evolution_summary_route_returns_high_frequency_issues(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig
    from stores.json.task_tree_evolution_store import TaskTreeEvolutionSample

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    store_factory.task_tree_evolution_store.save(
        TaskTreeEvolutionSample(
            id="ttes-1",
            project_id="proj-1",
            chat_session_id="chat-1",
            task_tree_session_id="tts-1",
            source_kind="generation",
            root_goal="升级统一 MCP 任务树持久化",
            detected_intent="governance",
            wrong_template="ui_flow",
            corrected_template="governance",
            issue_code="template_goal_mismatch",
            issue_message="当前节点与治理目标不一致。",
            user_visible=True,
            evidence=["命中了页面型启发式关键词：页面"],
        )
    )
    store_factory.task_tree_evolution_store.save(
        TaskTreeEvolutionSample(
            id="ttes-2",
            project_id="proj-1",
            chat_session_id="chat-1",
            task_tree_session_id="tts-1",
            source_kind="generation",
            root_goal="升级统一 MCP 任务树持久化",
            detected_intent="governance",
            wrong_template="ui_flow",
            corrected_template="governance",
            issue_code="template_goal_mismatch",
            issue_message="当前节点与治理目标不一致。",
            user_visible=True,
            evidence=["命中了页面型启发式关键词：页面"],
        )
    )
    store_factory.task_tree_evolution_store.save(
        TaskTreeEvolutionSample(
            id="ttes-3",
            project_id="proj-1",
            chat_session_id="chat-1",
            task_tree_session_id="tts-1",
            source_kind="audit",
            root_goal="升级统一 MCP 任务树持久化",
            detected_intent="governance",
            wrong_template="",
            corrected_template="",
            issue_code="progress_not_written_back",
            issue_message="当前节点未回写。",
            user_visible=True,
            manually_corrected=True,
            evidence=["建议状态：in_progress"],
        )
    )

    response = client.get(
        "/api/projects/proj-1/chat/task-tree/evolution-summary",
        params={
            "chat_session_id": "chat-1",
            "top": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "proj-1"
    assert payload["chat_session_id"] == "chat-1"
    assert payload["summary"]["total_samples"] == 3
    assert payload["summary"]["user_visible_count"] == 3
    assert payload["summary"]["manually_corrected_count"] == 1
    assert payload["summary"]["top_issue_codes"][0] == {
        "issue_code": "template_goal_mismatch",
        "count": 2,
    }
    assert payload["summary"]["top_wrong_templates"][0] == {
        "wrong_template": "ui_flow",
        "count": 2,
    }
    assert len(payload["summary"]["recent_samples"]) == 2


def test_project_chat_task_tree_audit_auto_completes_lookup_query(
    tmp_path,
    monkeypatch,
):
    from services.project_chat_task_tree import audit_task_tree_round
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "当前项目员工都有谁",
        },
    )
    assert generate_response.status_code == 200

    audit_payload = audit_task_tree_round(
        project_id="proj-1",
        username="tester",
        chat_session_id=chat_session_id,
        assistant_content="当前项目共有 1 名员工：前端架构与跨端攻坚专家。证据来自 search_project_context 返回的项目成员列表。",
        successful_tool_names=["search_project_context"],
        task_tree_tool_used=False,
    )

    assert audit_payload is not None
    assert audit_payload["code"] == "lookup_query_auto_completed"
    assert audit_payload["severity"] == "low"
    assert audit_payload["category"] == "lookup_query"
    assert audit_payload["message"]
    assert audit_payload["recommended_action"]
    assert any("归档目标：" in item for item in audit_payload["evidence"])
    assert audit_payload["task_tree"] is None
    assert audit_payload["history_task_tree"]["status"] == "done"
    assert audit_payload["history_task_tree"]["is_archived"] is True

    active_tree_response = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    )
    assert active_tree_response.status_code == 200
    assert active_tree_response.json()["task_tree"]["is_archived"] is True
    assert (
        active_tree_response.json()["task_tree"]["source_chat_session_id"]
        == chat_session_id
    )

    latest_tree_response = client.get("/api/projects/proj-1/chat/task-tree")
    assert latest_tree_response.status_code == 200
    assert latest_tree_response.json()["task_tree"]["is_archived"] is True
    assert (
        latest_tree_response.json()["task_tree"]["source_chat_session_id"]
        == chat_session_id
    )


def test_project_chat_task_tree_audit_auto_completes_colloquial_lookup_query(
    tmp_path,
    monkeypatch,
):
    from services.project_chat_task_tree import audit_task_tree_round
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "当前项目做什么的",
        },
    )
    assert generate_response.status_code == 200

    audit_payload = audit_task_tree_round(
        project_id="proj-1",
        username="tester",
        chat_session_id=chat_session_id,
        assistant_content="当前项目定位是 AI 对话和 AI 图片视频生成，目标是打造数字分身。",
        successful_tool_names=["get_manual_content"],
        task_tree_tool_used=False,
    )

    assert audit_payload is not None
    assert audit_payload["code"] == "lookup_query_auto_completed"
    assert audit_payload["severity"] == "low"
    assert audit_payload["category"] == "lookup_query"
    assert audit_payload["message"]
    assert audit_payload["history_task_tree"]["status"] == "done"
    assert audit_payload["history_task_tree"]["is_archived"] is True


def test_project_chat_task_tree_audit_recovers_embedded_task_completion_call(
    tmp_path,
    monkeypatch,
):
    from services.project_chat_task_tree import audit_task_tree_round
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "修复任务树没有回写的问题",
        },
    )
    assert generate_response.status_code == 200
    payload = generate_response.json()["task_tree"]
    leaf_node = next(item for item in payload["nodes"] if int(item["level"]) == 1)

    audit_payload = audit_task_tree_round(
        project_id="proj-1",
        username="tester",
        chat_session_id=chat_session_id,
        assistant_content=(
            f"<tool_call>complete_task_node_with_verification<arg_key>node_id</arg_key>"
            f"<arg_value>{leaf_node['id']}</arg_value><arg_key>verification_result</arg_key>"
            "<arg_value>已通过日志核对确认节点完成。</arg_value></tool_call>"
        ),
        successful_tool_names=[],
        task_tree_tool_used=False,
    )

    assert audit_payload is not None
    assert audit_payload["code"] == "embedded_task_call_recovered"
    assert audit_payload["severity"] == "low"
    assert audit_payload["category"] == "embedded_writeback_recovery"
    assert audit_payload["message"]
    assert audit_payload["recommended_action"]
    assert any("恢复的嵌入调用：" in item for item in audit_payload["evidence"])
    updated_leaf = next(
        item for item in audit_payload["task_tree"]["nodes"] if item["id"] == leaf_node["id"]
    )
    assert updated_leaf["status"] == "done"
    assert "日志核对" in updated_leaf["verification_result"]

    samples = store_factory.task_tree_evolution_store.list_samples(
        project_id="proj-1",
        chat_session_id=chat_session_id,
        source_kind="audit",
    )
    assert samples
    assert any(item.issue_code == "embedded_task_call_recovered" for item in samples)


def test_project_chat_task_tree_regenerates_for_new_goal_after_completion(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    first_generate = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "先完成第一个任务",
        },
    )
    assert first_generate.status_code == 200
    first_payload = first_generate.json()["task_tree"]
    root_node = next(item for item in first_payload["nodes"] if int(item["level"]) == 0)
    leaf_nodes = [item for item in first_payload["nodes"] if int(item["level"]) == 1]
    assert leaf_nodes
    for index, leaf_node in enumerate(leaf_nodes):
        start_leaf = client.patch(
            f"/api/projects/proj-1/chat/task-tree/nodes/{leaf_node['id']}",
            json={
                "chat_session_id": chat_session_id,
                "status": "in_progress",
                "is_current": index == 0,
            },
        )
        assert start_leaf.status_code == 200
        finish_leaf = client.patch(
            f"/api/projects/proj-1/chat/task-tree/nodes/{leaf_node['id']}",
            json={
                "chat_session_id": chat_session_id,
                "status": "done",
                "verification_result": f"叶子任务 {index + 1} 已验证完成",
            },
        )
        assert finish_leaf.status_code == 200

    start_root = client.patch(
        f"/api/projects/proj-1/chat/task-tree/nodes/{root_node['id']}",
        json={
            "chat_session_id": chat_session_id,
            "status": "in_progress",
            "is_current": True,
        },
    )
    assert start_root.status_code == 200
    start_root_payload = start_root.json()
    finish_root_payload = start_root_payload
    if start_root_payload.get("history_task_tree") is None:
        finish_root = client.patch(
            f"/api/projects/proj-1/chat/task-tree/nodes/{root_node['id']}",
            json={
                "chat_session_id": chat_session_id,
                "status": "done",
                "verification_result": "整体验证通过",
            },
        )
        assert finish_root.status_code == 200
        finish_root_payload = finish_root.json()

    assert finish_root_payload["task_tree"] is None
    assert finish_root_payload["history_task_tree"]["status"] == "done"
    assert finish_root_payload["history_task_tree"]["is_archived"] is True
    assert finish_root_payload["history_task_tree"]["source_chat_session_id"] == chat_session_id

    active_tree_after_done = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    )
    assert active_tree_after_done.status_code == 200
    assert active_tree_after_done.json()["task_tree"]["is_archived"] is True
    assert (
        active_tree_after_done.json()["task_tree"]["source_chat_session_id"]
        == chat_session_id
    )

    history_sessions = client.get("/api/projects/proj-1/chat/task-tree/sessions")
    assert history_sessions.status_code == 200
    history_items = history_sessions.json()["items"]
    assert len(history_items) == 1
    assert history_items[0]["is_archived"] is True
    assert history_items[0]["source_chat_session_id"] == chat_session_id

    second_generate = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "切换到第二个全新任务",
        },
    )
    assert second_generate.status_code == 200
    second_payload = second_generate.json()["task_tree"]
    assert second_payload["root_goal"] == "切换到第二个全新任务"
    assert second_payload["status"] == "pending"
    assert second_payload["progress_percent"] == 0

    sessions_after_regenerate = client.get("/api/projects/proj-1/chat/task-tree/sessions")
    assert sessions_after_regenerate.status_code == 200
    session_items = sessions_after_regenerate.json()["items"]
    assert len(session_items) == 2
    assert session_items[0]["chat_session_id"] == chat_session_id
    assert session_items[0]["is_archived"] is False
    assert session_items[1]["is_archived"] is True


def test_project_chat_task_tree_route_supports_exact_history_session_lookup(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    chat_session_id = "chat-session-1"
    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "修复记忆详情页里任务树和进度错位的问题",
        },
    )
    assert generate_response.status_code == 200
    payload = generate_response.json()["task_tree"]
    root_node = next(item for item in payload["nodes"] if int(item["level"]) == 0)

    working_payload = payload
    while True:
        current_node = working_payload["current_node"]
        if int(current_node["level"]) != 1:
            break
        start_leaf_response = client.patch(
            f"/api/projects/proj-1/chat/task-tree/nodes/{current_node['id']}",
            json={
                "chat_session_id": chat_session_id,
                "status": "in_progress",
                "is_current": True,
            },
        )
        assert start_leaf_response.status_code == 200
        complete_leaf_response = client.patch(
            f"/api/projects/proj-1/chat/task-tree/nodes/{current_node['id']}",
            json={
                "chat_session_id": chat_session_id,
                "status": "done",
                "verification_result": f"{current_node['title']} 已验证完成",
                "is_current": True,
            },
        )
        assert complete_leaf_response.status_code == 200
        working_payload = complete_leaf_response.json()["task_tree"]

    finish_root = client.patch(
        f"/api/projects/proj-1/chat/task-tree/nodes/{root_node['id']}",
        json={
            "chat_session_id": chat_session_id,
            "status": "done",
            "verification_result": "整棵任务树已验证完成",
            "is_current": True,
        },
    )
    assert finish_root.status_code == 200
    history_task_tree = finish_root.json()["history_task_tree"]
    assert history_task_tree["is_archived"] is True

    regenerate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "第二个新需求，保持聊天继续复用同一 chat_session_id",
        },
    )
    assert regenerate_response.status_code == 200
    current_task_tree = regenerate_response.json()["task_tree"]
    assert current_task_tree["is_archived"] is False

    history_lookup = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"session_id": history_task_tree["id"]},
    )
    assert history_lookup.status_code == 200
    assert history_lookup.json()["task_tree"]["id"] == history_task_tree["id"]
    assert history_lookup.json()["task_tree"]["is_archived"] is True
    assert history_lookup.json()["task_tree"]["source_chat_session_id"] == chat_session_id

    current_lookup = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": chat_session_id},
    )
    assert current_lookup.status_code == 200
    assert current_lookup.json()["task_tree"]["id"] == current_task_tree["id"]
    assert current_lookup.json()["task_tree"]["is_archived"] is False


def test_project_work_session_events_can_filter_by_task_tree_and_node(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig
    from stores.json.work_session_store import WorkSessionEvent

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.work_session_store.save(
        WorkSessionEvent(
            id=store_factory.work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="emp-1",
            session_id="ws-1",
            task_tree_session_id="tts-1",
            task_tree_chat_session_id="chat-1",
            task_node_id="node-1",
            task_node_title="定位问题",
            source_kind="work-facts",
            event_type="analysis",
            phase="分析",
            step="定位问题",
            status="in_progress",
            goal="修复记忆详情页绑定问题",
            content="已完成问题定位",
        )
    )
    store_factory.work_session_store.save(
        WorkSessionEvent(
            id=store_factory.work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="emp-1",
            session_id="ws-1",
            task_tree_session_id="tts-1",
            task_tree_chat_session_id="chat-1",
            task_node_id="node-2",
            task_node_title="完成修复",
            source_kind="session-event",
            event_type="verification",
            phase="验证",
            step="完成修复",
            status="completed",
            goal="修复记忆详情页绑定问题",
            content="已完成验证",
        )
    )

    list_response = client.get(
        "/api/projects/proj-1/work-session-events",
        params={"task_tree_session_id": "tts-1", "task_node_id": "node-1"},
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["task_tree_session_id"] == "tts-1"
    assert items[0]["task_node_id"] == "node-1"
    assert items[0]["task_node_title"] == "定位问题"

    summary_response = client.get(
        "/api/projects/proj-1/work-sessions",
        params={"task_tree_session_id": "tts-1"},
    )
    assert summary_response.status_code == 200
    summary_item = summary_response.json()["items"][0]
    assert summary_item["task_tree_session_id"] == "tts-1"
    assert set(summary_item["task_node_titles"]) == {"定位问题", "完成修复"}


def test_project_requirement_records_route_returns_aggregated_chain_summaries(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_chat_task_store import ProjectChatTaskSession
    from stores.json.project_store import ProjectConfig
    from stores.json.work_session_store import WorkSessionEvent

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_chat_task_store.save(
        ProjectChatTaskSession(
            id="tts-1",
            project_id="proj-1",
            username="tester",
            chat_session_id="chat-1",
            source_chat_session_id="chat-1",
            source_session_id="",
            title="修复需求记录加载性能",
            root_goal="修复需求记录加载性能",
            status="in_progress",
            lifecycle_status="active",
            round_index=1,
        )
    )
    store_factory.work_session_store.save(
        WorkSessionEvent(
            id=store_factory.work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="emp-1",
            session_id="ws-1",
            task_tree_session_id="tts-1",
            task_tree_chat_session_id="chat-1",
            task_node_id="node-1",
            task_node_title="梳理慢点",
            source_kind="work-facts",
            event_type="analysis",
            phase="分析",
            step="梳理慢点",
            status="in_progress",
            goal="修复需求记录加载性能",
            content="已完成首轮排查",
        )
    )

    response = client.get("/api/projects/proj-1/requirement-records")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "proj-1"
    assert payload["storage_backend"] == "json"
    assert len(payload["task_sessions"]) == 1
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"]
    assert item["rootGoal"] == "修复需求记录加载性能"
    assert item["roundDigest"] == "单轮处理"
    assert item["actorLabel"] == "emp-1"
    assert item["detailRound"]["sessionId"] == "tts-1"
    assert item["detailRound"]["primaryWorkSession"]["session_id"] == "ws-1"


def test_project_requirement_records_route_uses_short_ttl_cache(
    tmp_path,
    monkeypatch,
):
    from routers import projects as projects_router
    from stores.json.project_store import ProjectConfig

    call_count = 0
    original_builder = projects_router._build_project_requirement_records
    projects_router._project_requirement_records_local_cache.clear()

    def counted_builder(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_builder(*args, **kwargs)

    async def _get_fake_redis():
        raise RuntimeError("redis unavailable in test")

    monkeypatch.setattr(projects_router, "_build_project_requirement_records", counted_builder)
    monkeypatch.setattr(projects_router, "get_redis_client", _get_fake_redis)

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    first = client.get("/api/projects/proj-1/requirement-records")
    second = client.get("/api/projects/proj-1/requirement-records")

    assert first.status_code == 200
    assert second.status_code == 200
    assert call_count == 1


def test_project_requirement_records_route_hides_query_cli_shadow_chain_near_real_cli_chain(
    tmp_path,
    monkeypatch,
):
    from routers import projects as projects_router
    from stores.json.project_chat_task_store import ProjectChatTaskSession
    from stores.json.project_store import ProjectConfig

    projects_router._project_requirement_records_local_cache.clear()
    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-shadow-1", name="项目一"))

    root_goal = "当前 的 项目 规则有哪些"
    store_factory.project_chat_task_store.save(
        ProjectChatTaskSession(
            id="tts-query-cli-1",
            project_id="proj-shadow-1",
            username="tester",
            chat_session_id="query-cli.proj-1.tester.req-1",
            source_session_id="ws-query-cli-1",
            title=root_goal,
            root_goal=root_goal,
            status="done",
            lifecycle_status="active",
            created_at="2026-04-16T07:56:00+08:00",
            updated_at="2026-04-16T07:56:00+08:00",
        )
    )
    store_factory.project_chat_task_store.save(
        ProjectChatTaskSession(
            id="tts-cli-1",
            project_id="proj-shadow-1",
            username="tester",
            chat_session_id="cli.proj-1.20260416T075700.host01.1001.abc123",
            source_session_id="ws-cli-1",
            title=root_goal,
            root_goal=root_goal,
            status="done",
            lifecycle_status="active",
            created_at="2026-04-16T07:57:00+08:00",
            updated_at="2026-04-16T07:57:00+08:00",
        )
    )

    response = client.get("/api/projects/proj-shadow-1/requirement-records")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["detailRound"]["chatSessionId"] == "cli.proj-1.20260416T075700.host01.1001.abc123"
    assert len(payload["task_sessions"]) == 1
    assert payload["task_sessions"][0]["chat_session_id"] == "cli.proj-1.20260416T075700.host01.1001.abc123"


def test_project_requirement_records_route_keeps_same_goal_query_cli_history_when_time_gap_is_large(
    tmp_path,
    monkeypatch,
):
    from routers import projects as projects_router
    from stores.json.project_chat_task_store import ProjectChatTaskSession
    from stores.json.project_store import ProjectConfig

    projects_router._project_requirement_records_local_cache.clear()
    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-shadow-2", name="项目一"))

    root_goal = "当前 的 项目 规则有哪些"
    store_factory.project_chat_task_store.save(
        ProjectChatTaskSession(
            id="tts-query-cli-old",
            project_id="proj-shadow-2",
            username="tester",
            chat_session_id="query-cli.proj-1.tester.req-old",
            source_session_id="ws-query-cli-old",
            title=root_goal,
            root_goal=root_goal,
            status="done",
            lifecycle_status="active",
            created_at="2026-04-16T07:00:00+08:00",
            updated_at="2026-04-16T07:00:00+08:00",
        )
    )
    store_factory.project_chat_task_store.save(
        ProjectChatTaskSession(
            id="tts-cli-new",
            project_id="proj-shadow-2",
            username="tester",
            chat_session_id="cli.proj-1.20260416T075700.host01.1001.abc123",
            source_session_id="ws-cli-new",
            title=root_goal,
            root_goal=root_goal,
            status="done",
            lifecycle_status="active",
            created_at="2026-04-16T07:57:00+08:00",
            updated_at="2026-04-16T07:57:00+08:00",
        )
    )

    response = client.get("/api/projects/proj-shadow-2/requirement-records")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert {item["detailRound"]["chatSessionId"] for item in payload["items"]} == {
        "query-cli.proj-1.tester.req-old",
        "cli.proj-1.20260416T075700.host01.1001.abc123",
    }
    assert len(payload["task_sessions"]) == 2


def test_rebind_task_tree_chat_session_moves_query_cli_shadow_session(
    tmp_path,
    monkeypatch,
):
    from services.project_chat_task_tree import get_task_tree, rebind_task_tree_chat_session
    from stores.json.project_chat_task_store import ProjectChatTaskSession
    from stores.json.project_store import ProjectConfig

    _client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_chat_task_store.save(
        ProjectChatTaskSession(
            id="tts-shadow-1",
            project_id="proj-1",
            username="tester",
            chat_session_id="query-cli.proj-1.tester.req-1",
            title="当前 的 项目 规则有哪些",
            root_goal="当前 的 项目 规则有哪些",
            status="pending",
            lifecycle_status="active",
        )
    )

    migrated = rebind_task_tree_chat_session(
        project_id="proj-1",
        username="tester",
        from_chat_session_id="query-cli.proj-1.tester.req-1",
        to_chat_session_id="cli.proj-1.20260416T075700.host01.1001.abc123",
        root_goal="当前 的 项目 规则有哪些",
    )

    assert migrated is not None
    assert migrated.id == "tts-shadow-1"
    assert migrated.chat_session_id == "cli.proj-1.20260416T075700.host01.1001.abc123"
    assert (
        get_task_tree("proj-1", "tester", "query-cli.proj-1.tester.req-1")
        is None
    )
    rebound = get_task_tree(
        "proj-1",
        "tester",
        "cli.proj-1.20260416T075700.host01.1001.abc123",
    )
    assert rebound is not None
    assert rebound.id == "tts-shadow-1"


def test_project_chat_task_tree_requires_started_status_before_completion(
    tmp_path,
    monkeypatch,
):
    from services.dynamic_mcp_collaboration import invoke_project_builtin_tool
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "检查任务树节点不能在未开始时直接完成",
        },
    )
    assert generate_response.status_code == 200
    payload = generate_response.json()["task_tree"]
    leaf_node = next(item for item in payload["nodes"] if int(item["level"]) == 1)
    assert leaf_node["status"] == "pending"

    direct_complete_response = client.patch(
        f"/api/projects/proj-1/chat/task-tree/nodes/{leaf_node['id']}",
        json={
            "chat_session_id": chat_session_id,
            "status": "done",
            "verification_result": "已验证",
        },
    )
    assert direct_complete_response.status_code == 400
    assert "started before completion" in direct_complete_response.json()["detail"]

    builtin_complete = invoke_project_builtin_tool(
        "proj-1",
        "complete_task_node_with_verification",
        username="tester",
        chat_session_id=chat_session_id,
        args={
            "node_id": leaf_node["id"],
            "verification_result": "已验证",
        },
    )
    assert "started before completion" in str(builtin_complete.get("error") or "")

    start_response = client.patch(
        f"/api/projects/proj-1/chat/task-tree/nodes/{leaf_node['id']}",
        json={
            "chat_session_id": chat_session_id,
            "status": "in_progress",
            "is_current": True,
        },
    )
    assert start_response.status_code == 200

    builtin_complete_after_start = invoke_project_builtin_tool(
        "proj-1",
        "complete_task_node_with_verification",
        username="tester",
        chat_session_id=chat_session_id,
        args={
            "node_id": leaf_node["id"],
            "verification_result": "已验证",
        },
    )
    assert builtin_complete_after_start["status"] == "completed"
    assert builtin_complete_after_start["node_id"] == leaf_node["id"]


def test_project_chat_task_tree_refines_same_session_in_place_before_execution(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    session_response = client.post("/api/projects/proj-1/chat/sessions")
    assert session_response.status_code == 200
    chat_session_id = session_response.json()["session"]["id"]

    first_generate = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "优化记忆详情弹框",
        },
    )
    assert first_generate.status_code == 200
    first_payload = first_generate.json()["task_tree"]
    first_task_tree_id = first_payload["id"]

    second_generate = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": chat_session_id,
            "message": "根据项目 UI 规则优化记忆详情弹框内容",
            "max_steps": 8,
        },
    )
    assert second_generate.status_code == 200
    second_payload = second_generate.json()["task_tree"]

    assert second_payload["id"] == first_task_tree_id
    assert second_payload["chat_session_id"] == chat_session_id
    assert second_payload["root_goal"] == "根据项目 UI 规则优化记忆详情弹框内容"
    assert second_payload["is_archived"] is False

    sessions_response = client.get("/api/projects/proj-1/chat/task-tree/sessions")
    assert sessions_response.status_code == 200
    items = sessions_response.json()["items"]
    assert len(items) == 1
    assert items[0]["chat_session_id"] == chat_session_id
    assert items[0]["is_archived"] is False


def test_project_chat_task_tree_sessions_exclude_synthetic_query_cli_rows(
    tmp_path,
    monkeypatch,
):
    from core.deps import project_chat_task_store
    from stores.json.project_chat_task_store import ProjectChatTaskSession
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    project_chat_task_store.save(
        ProjectChatTaskSession(
            id="tts-cli-1",
            project_id="proj-1",
            username="tester",
            chat_session_id="query-cli.proj-1.tester.req-1",
            title="CLI synthetic task",
            root_goal="CLI synthetic task",
            status="pending",
            lifecycle_status="active",
        )
    )
    project_chat_task_store.save(
        ProjectChatTaskSession(
            id="tts-ui-1",
            project_id="proj-1",
            username="tester",
            chat_session_id="chat-session-real-1",
            title="Real UI task",
            root_goal="Real UI task",
            status="in_progress",
            lifecycle_status="active",
        )
    )

    sessions_response = client.get("/api/projects/proj-1/chat/task-tree/sessions")
    assert sessions_response.status_code == 200
    items = sessions_response.json()["items"]
    assert len(items) == 2
    assert items[0]["chat_session_id"] == "chat-session-real-1"
    assert items[1]["chat_session_id"] == "query-cli.proj-1.tester.req-1"


def test_build_task_tree_session_filters_internal_tool_plan_into_goal_steps(monkeypatch):
    from services import project_chat_task_tree as task_tree_svc

    monkeypatch.setattr(
        task_tree_svc,
        "_generate_execution_plan_payload",
        lambda *args, **kwargs: {
            "plan_steps": [
                {
                    "phase": "context",
                    "tool_name": "search_project_context",
                    "reason": "先统一检索项目上下文、成员、规则和 MCP 能力。",
                },
                {
                    "phase": "rule",
                    "tool_name": "query_project_rules",
                    "employee_id": "emp-7e52bc3d",
                    "reason": "先检索 产品设计与文档协作专员 相关规则，避免协作执行偏离约束。",
                },
                {
                    "phase": "execution",
                    "tool_name": "emp_7e52bc3d__db_query__db_query",
                    "reason": "Auto inferred proxy entry from scripts/db_query.py",
                },
            ]
        },
    )

    session = task_tree_svc.build_task_tree_session(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        root_goal="/ai/chat/settings/projects/proj-d16591a6 做成tabs 方便切换不用来回切换了",
    )

    leaf_titles = [node.title for node in session.nodes if int(node.level) == 1]
    leaf_descriptions = [node.description for node in session.nodes if int(node.level) == 1]

    assert leaf_titles == [
        "梳理 /ai/chat/settings/projects/proj-d16591a6 当前结构与切换路径",
        "改造成页内 Tabs 切换并保持状态同步",
        "验证 Tabs 切换、路由与边界状态",
    ]
    assert not any("Auto inferred proxy entry" in text for text in leaf_titles + leaf_descriptions)
    assert not any("search_project_context" in text for text in leaf_descriptions)
    assert not any("query_project_rules" in text for text in leaf_descriptions)


def test_build_task_tree_prompt_explicitly_forbids_internal_tools_as_nodes():
    from services.project_chat_task_tree import build_task_tree_prompt
    from stores.json.project_chat_task_store import ProjectChatTaskNode, ProjectChatTaskSession

    session = ProjectChatTaskSession(
        id="tts-prompt-1",
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-prompt-1",
        title="设置页改 Tabs",
        root_goal="/ai/chat/settings/projects/proj-d16591a6 做成tabs 方便切换不用来回切换了",
        current_node_id="node-1",
        nodes=[
            ProjectChatTaskNode(
                id="root-1",
                session_id="tts-prompt-1",
                title="设置页改 Tabs",
                level=0,
                sort_order=0,
            ),
            ProjectChatTaskNode(
                id="node-1",
                session_id="tts-prompt-1",
                parent_id="root-1",
                title="改造成页内 Tabs 切换并保持状态同步",
                level=1,
                sort_order=1,
            ),
        ],
    )

    prompt = build_task_tree_prompt(session)

    assert "任务树节点必须直接描述面向用户目标的工作步骤" in prompt
    assert "不要把 search_project_context、query_project_rules、search_ids、get_manual_content、resolve_relevant_context、generate_execution_plan 这类内部检索或规划工具直接写成任务节点。" in prompt
    assert "不要把候选代理工具、脚本路径或类似“Auto inferred proxy entry from scripts/... ”的描述当成任务节点。" in prompt
