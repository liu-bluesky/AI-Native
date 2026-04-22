"""Project MCP online presence tests."""

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]


class _FakePresenceRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        _ = ex
        self.values[key] = value

    async def sadd(self, key: str, *values: str):
        self.sets.setdefault(key, set()).update(str(item) for item in values if str(item).strip())

    async def smembers(self, key: str):
        return set(self.sets.get(key, set()))

    async def mget(self, keys: list[str]):
        return [self.values.get(key) for key in keys]

    async def srem(self, key: str, *values: str):
        bucket = self.sets.setdefault(key, set())
        for item in values:
            bucket.discard(str(item))


def _build_project_mcp_monitor_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from services import project_mcp_presence as project_mcp_presence_service

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("role_store", "system_config_store", "user_store"):
        getattr(store_factory, proxy_name)._instance = None

    fake_redis = _FakePresenceRedis()

    async def _get_fake_redis():
        return fake_redis

    monkeypatch.setattr(project_mcp_presence_service, "get_redis_client", _get_fake_redis)

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), fake_redis, project_mcp_presence_service


def test_project_mcp_activity_lists_recent_presence(tmp_path, monkeypatch):
    client, _, project_mcp_presence_service = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    import asyncio

    asyncio.run(
        project_mcp_presence_service.touch_project_mcp_presence(
            endpoint_type="project",
            entity_id="proj-1",
            entity_name="项目一",
            project_id="proj-1",
            project_name="项目一",
            developer_name="alice",
            key_owner_username="owner-alice",
            api_key="key-alice-12345678",
            client_ip="127.0.0.1",
            transport="sse",
            method="GET",
            path="/mcp/projects/proj-1/sse",
            session_id="sess-1",
        )
    )

    response = client.get("/api/system/mcp-monitor/project-activity")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ttl_seconds"] == 180
    assert payload["summary"] == {
        "active_projects": 1,
        "active_developers": 1,
        "active_sessions": 1,
    }
    assert payload["items"][0]["endpoint_type"] == "project"
    assert payload["items"][0]["entity_id"] == "proj-1"
    assert payload["items"][0]["project_id"] == "proj-1"
    assert payload["items"][0]["project_name"] == "项目一"
    assert payload["items"][0]["developer_name"] == "alice"
    assert payload["items"][0]["key_owner_username"] == "owner-alice"
    assert payload["items"][0]["transport"] == "sse"
    assert payload["items"][0]["session_id"] == "sess-1"


def test_project_mcp_activity_blocks_non_admin_and_prunes_stale(tmp_path, monkeypatch):
    admin_client, fake_redis, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )
    fake_redis.sets.setdefault("system-mcp:presence:members", set()).update(
        {
            "system-mcp:presence:item:alive",
            "system-mcp:presence:item:stale",
        }
    )
    fake_redis.values["system-mcp:presence:item:alive"] = (
        '{"endpoint_type":"project","entity_id":"proj-1","entity_name":"项目一","project_id":"proj-1","project_name":"项目一","developer_name":"alice","api_key":"key...5678",'
        '"key_owner_username":"owner-alice",'
        '"client_ip":"127.0.0.1","transport":"sse","method":"GET","path":"/mcp/projects/proj-1/sse",'
        '"session_id":"sess-1","first_seen_at":"2026-04-02T00:00:00+00:00","last_seen_at":"2026-04-02T00:01:00+00:00","request_count":3}'
    )

    list_response = admin_client.get("/api/system/mcp-monitor/project-activity")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["project_id"] == "proj-1"
    assert "system-mcp:presence:item:stale" not in fake_redis.sets["system-mcp:presence:members"]

    blocked_client, _, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "bob", "role": "user"},
    )
    blocked_response = blocked_client.get("/api/system/mcp-monitor/project-activity")
    assert blocked_response.status_code == 403


def test_query_mcp_runtime_returns_contextual_urls_and_cli_prompt(tmp_path, monkeypatch):
    client, _, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    response = client.get(
        "/api/projects/query-mcp/runtime",
        params={
            "project_id": "proj-1",
            "chat_session_id": "chat-session-1",
        },
    )

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert "project_id=proj-1" in runtime["sse_url"]
    assert "chat_session_id=chat-session-1" in runtime["sse_url"]
    assert "project_id=proj-1" in runtime["http_url"]
    assert "chat_session_id=chat-session-1" in runtime["http_url"]
    assert runtime["prompt_mode"] == "bootstrap"
    assert runtime["clarity_confirm_threshold"] == 3
    assert runtime["bootstrap_resources"] == [
        "query://usage-guide",
        "query://client-profile/codex",
    ]
    assert runtime["bootstrap_checklist"] == [
        "read query://usage-guide",
        "read query://client-profile/codex",
        "initialize local .ai-employee state in the current CLI workspace and ensure query-mcp-workflow is available there",
        "treat project-local .ai-employee/skills/query-mcp-workflow as the default skill location; use mcp-skills/knowledge only when maintaining the workflow source repo",
        "generate and persist chat_session_id",
        "bind_project_context with project_id/chat_session_id/root_goal",
        "get_current_task_tree and verify the bound tree matches the current request",
        "call search_ids only when IDs are missing, scope is ambiguous, or cross-project lookup is needed",
        "get_manual_content before rule-specific execution",
        "score request clarity from 1-5; ask for confirmation only when clarity is below 3 or the request is ambiguous",
        "analyze_task -> resolve_relevant_context -> generate_execution_plan",
        "finish analysis, edits, verification, and local requirement/session recording before syncing task-tree or work-facts back to the server",
        "update_task_node_status on node start and complete_task_node_with_verification on node finish",
        "start_work_session and persist session_id for long tasks",
    ]
    assert "query://usage-guide" in runtime["cli_prompt"]
    assert "query://client-profile/codex" in runtime["cli_prompt"]
    assert "默认项目: `proj-1`" in runtime["cli_prompt"]
    assert "chat_session_id=chat-session-1" in runtime["cli_prompt"]
    assert "start_work_session" in runtime["cli_prompt"]
    assert "当前全局清晰度确认阈值为 3/5" in runtime["cli_prompt"]
    assert "清晰度分数 >= 3" in runtime["cli_prompt"]
    assert "清晰度分数 < 3" in runtime["cli_prompt"]
    assert "停止复用当前 `chat_session_id`" in runtime["cli_prompt"]
    assert "complete_task_node_with_verification" in runtime["cli_prompt"]
    assert ".ai-employee/query-mcp/active-sessions/<chat_session_id>.json" in runtime["cli_prompt"]
    assert "显式初始化本地 `.ai-employee/`" in runtime["cli_prompt"]
    assert "通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`" in runtime["cli_prompt"]
    assert "只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时" in runtime["cli_prompt"]
    assert "不能替代当前 CLI 工作区初始化" in runtime["cli_prompt"]
    assert "仅在缺少明确的 `project_id` / `employee_id` / `rule_id`" in runtime["cli_prompt"]
    assert "# Unified Query MCP" not in runtime["cli_prompt"]


def test_query_mcp_runtime_uses_system_clarity_threshold(tmp_path, monkeypatch):
    client, _, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    patch_response = client.patch(
        "/api/system-config",
        json={"query_mcp_clarity_confirm_threshold": 5},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["config"]["query_mcp_clarity_confirm_threshold"] == 5

    response = client.get(
        "/api/projects/query-mcp/runtime",
        params={"project_id": "proj-1", "chat_session_id": "chat-session-1"},
    )

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["clarity_confirm_threshold"] == 5
    assert (
        "score request clarity from 1-5; ask for confirmation only when clarity is below 5 or the request is ambiguous"
        in runtime["bootstrap_checklist"]
    )
    assert "当前全局清晰度确认阈值为 5/5" in runtime["cli_prompt"]
    assert "清晰度分数 >= 5" in runtime["cli_prompt"]


def test_query_mcp_runtime_uses_configured_bootstrap_template(tmp_path, monkeypatch):
    client, _, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    patch_response = client.patch(
        "/api/system-config",
        json={
            "query_mcp_bootstrap_prompt_template": "BOOT {{clarity_threshold}} | {{project_context_block}} | {{chat_session_block}}",
        },
    )
    assert patch_response.status_code == 200

    response = client.get(
        "/api/projects/query-mcp/runtime",
        params={"project_id": "proj-1", "chat_session_id": "chat-session-1"},
    )
    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["cli_prompt"].startswith("BOOT 3 |")
    assert "默认项目: `proj-1`" in runtime["cli_prompt"]
    assert "chat_session_id=chat-session-1" in runtime["cli_prompt"]


def test_query_mcp_runtime_normalizes_legacy_bootstrap_template(tmp_path, monkeypatch):
    client, _, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    patch_response = client.patch(
        "/api/system-config",
        json={
            "query_mcp_bootstrap_prompt_template": (
                "你已接入统一查询 MCP。\n"
                "6. 首轮必须把用户原始问题原文传给 `search_ids(keyword=\"<用户原始问题>\")`，不要只写“当前项目”这类代称。"
            ),
        },
    )
    assert patch_response.status_code == 200

    response = client.get(
        "/api/projects/query-mcp/runtime",
        params={"project_id": "proj-1", "chat_session_id": "chat-session-1"},
    )
    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert "首轮必须把用户原始问题原文传给" not in runtime["cli_prompt"]
    assert "仅在缺少明确的 `project_id` / `employee_id` / `rule_id`" in runtime["cli_prompt"]


def test_query_mcp_runtime_normalizes_legacy_skill_source_line(tmp_path, monkeypatch):
    client, _, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    patch_response = client.patch(
        "/api/system-config",
        json={
            "query_mcp_bootstrap_prompt_template": (
                "HEAD\n"
                "当前统一查询 MCP 工作流技能的服务端权威元数据位于 `mcp-skills/knowledge/skills/query-mcp-workflow.json`，技能包位于 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/`；核心文件优先读取 `SKILL.md` 与 `manifest.json`。若宿主或项目已提供本地同名技能目录，优先读取本地副本。\n"
                "TAIL"
            ),
        },
    )
    assert patch_response.status_code == 200

    response = client.get(
        "/api/projects/query-mcp/runtime",
        params={"project_id": "proj-1", "chat_session_id": "chat-session-1"},
    )
    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert "当前统一查询 MCP 工作流技能的服务端权威元数据位于" not in runtime["cli_prompt"]
    assert "通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`" in runtime["cli_prompt"]
    assert "只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时" in runtime["cli_prompt"]


def test_query_mcp_runtime_upgrades_legacy_default_bootstrap_template(tmp_path, monkeypatch):
    client, _, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    legacy_template = """你已接入统一查询 MCP。

详细规则不要直接内联到宿主提示词；但开始执行前必须按需读取这些资源：

- `query://usage-guide`
- `query://client-profile/codex`

强制接入步骤：

1. 先读取 `query://usage-guide`；当前是 Codex CLI 时，再读取 `query://client-profile/codex`。
2. 仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或需要跨项目检索时，再调用 `search_ids(keyword="<用户原始问题>")`；已明确当前项目且在项目内执行时可直接读取上下文或进入本地实现，不要为满足流程机械检索。
3. 不要依赖 description、项目说明或“当前项目”文字做绑定；如需项目绑定或续接任务树，显式调用 `bind_project_context(...)`。
4. 需要项目或规则上下文时，先读取 `get_manual_content(project_id=...)`，再按需继续查询规则或成员。
5. 实现型需求必须先走 `analyze_task -> resolve_relevant_context -> generate_execution_plan`，再进入执行与验证。
6. 当前全局清晰度确认阈值为 3/5；先按 1-5 分估计用户需求清晰度。
7. 若目标、对象、范围和预期结果足够清晰，且清晰度分数 >= 3，直接处理，不主动要求确认计划。
8. 若清晰度分数 < 3、需求表述模糊、对象或范围不明确，或存在两种及以上合理理解，先输出你的理解、计划摘要和可能误解点，再请求用户确认后再执行；同一轮已确认后不要重复确认；查询型、客服型问题不要默认升级成计划审批流程。
9. 长任务先调用 `start_work_session` 获取 `session_id`，后续复用同一个 `chat_session_id/session_id`，并用 `save_work_facts`、`append_session_event` 维护轨迹。
10. 如宿主支持任务树，`bind_project_context(...)` 后立刻读取 `get_current_task_tree`，核对 `root_goal/title/current_node` 是否属于当前问题；若明显属于旧任务树，停止复用当前 `chat_session_id`，改为新建并持久化新的 `chat_session_id` 后重新绑定。
11. 真正进入执行前，再读取一次 `get_current_task_tree` 确认当前节点；开始节点用 `update_task_node_status`，完成节点必须用 `complete_task_node_with_verification` 补验证结果后再结束。
12. 如果当前宿主拿不到上述任务树工具，只能明确说明“任务树闭环未完成”，不要把自然语言进度当成已闭环。

当前接入上下文：

- 默认项目: `proj-d16591a6`
- 建议把 URL 默认上下文里的 `project_id` 固定为 `proj-d16591a6`。
- 涉及当前项目时，若项目和对象已明确，可直接 `get_manual_content(project_id="proj-d16591a6")` 或进入 `start_project_workflow(...)`；仅在缺少 ID 或需要跨项目定位时，再调用 `search_ids(keyword="<用户原始问题>", project_id="proj-d16591a6")`。
- 若要创建或续接当前项目任务树，优先显式调用 `bind_project_context(project_id="proj-d16591a6", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")`。
- 当前页面已有 `chat_session_id=chat-session-8635d55008c7`；仅在明确要续接当前任务树时复用，否则新开的并行 CLI 应重新生成自己的 `chat_session_id`。
- `chat_session_id` 生成后要立即持久化；优先写项目目录 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`，并同步维护 `.ai-employee/query-mcp/active/<project_id>.json` 与 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。
- 若当前还没有 `session_id`，调用 `start_work_session` 后也要立刻持久化；中断恢复顺序固定为 `bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)`。
- 若项目工作区不可解析，再退回当前 CLI 自己的本地存储；不要新写 `current-session.json`、`chat_session_id.txt`、`session_id.txt`、`session.env` 这类 legacy 文件。

回答要求：

- 先基于 MCP 查询结果回答，不要把猜测写成事实。
- 若信息来自 MCP，尽量保留对应的项目 / 员工 / 规则 ID，方便追溯。
- 若入口文件或宿主系统还有额外约束，优先遵守宿主入口文件约定。"""

    patch_response = client.patch(
        "/api/system-config",
        json={"query_mcp_bootstrap_prompt_template": legacy_template},
    )
    assert patch_response.status_code == 200

    response = client.get(
        "/api/projects/query-mcp/runtime",
        params={"project_id": "proj-1", "chat_session_id": "chat-session-1"},
    )
    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert "显式初始化本地 `.ai-employee/`" in runtime["cli_prompt"]
    assert "当前任务先在项目本地推进" in runtime["cli_prompt"]
    assert "不能替代当前 CLI 工作区初始化" in runtime["cli_prompt"]


def test_query_mcp_prompt_surfaces_use_project_local_skill_wording():
    expected_local_marker = ".ai-employee/skills/query-mcp-workflow/"
    expected_source_marker = "mcp-skills/knowledge/skills/query-mcp-workflow.json"
    expected_repo_marker = "只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时"

    prompt_surface_files = [
        "AGENTS.md",
        "web-admin/api/stores/json/system_config_store.py",
        "web-admin/api/routers/projects.py",
        "web-admin/api/services/dynamic_mcp_apps_query.py",
        "web-admin/frontend/src/views/system/SystemConfig.vue",
        "web-admin/frontend/src/components/UnifiedMcpAccessDialog.vue",
    ]
    for relative_path in prompt_surface_files:
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert expected_local_marker in content, relative_path
        assert expected_source_marker in content, relative_path
        assert expected_repo_marker in content, relative_path

    skill_package_content = (
        REPO_ROOT / "mcp-skills/knowledge/skill-packages/query-mcp-workflow/SKILL.md"
    ).read_text(encoding="utf-8")
    assert ".ai-employee/skills/query-mcp-workflow/" in skill_package_content
    assert "system source repo" in skill_package_content


def test_query_mcp_sync_rule_file_exists_in_rules_directory():
    agents_content = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    rule_content = (REPO_ROOT / "rules/query-mcp-prompt-sync.md").read_text(encoding="utf-8")
    assert "需求一开始就要在当前 CLI 工作区完成本地初始化、创建 requirement 与 canonical session 状态" in agents_content
    assert "必须同步更新相关提示词入口、技能说明与回归测试" in rule_content
    assert ".ai-employee/skills/query-mcp-workflow/" in rule_content
    assert "mcp-skills/knowledge/skills/query-mcp-workflow.json" in rule_content
    assert "每个需求都必须在开始时创建并持续更新本地 requirement" in rule_content
    assert "远程服务写入只算 sync-back" in rule_content
    assert "`sync_status`、`pending_outbox_count`" in rule_content
    assert "web-admin/api/services/query_mcp_project_state.py" in rule_content


def test_project_manual_template_avoids_frontend_route_specific_wording(tmp_path, monkeypatch):
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig

    client, _, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )
    store_factory.project_store.save(
        ProjectConfig(
            id="proj-1",
            name="项目一",
            description="测试项目",
            created_by="admin",
        )
    )

    response = client.get("/api/projects/proj-1/manual-template")

    assert response.status_code == 200
    manual = response.json()["manual"]
    assert "/ai/chat" not in manual
    assert "当前宿主前端只展示当前仍在进行中的任务树" in manual


def test_project_mcp_proxy_tracks_runtime_presence(monkeypatch):
    import asyncio

    from services import dynamic_mcp_proxy_apps as proxy_apps

    captured: list[dict] = []

    async def _fake_touch_project_mcp_presence(**kwargs):
        captured.append(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(proxy_apps, "_touch_project_mcp_presence", _fake_touch_project_mcp_presence)

    class _UsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "alice" if api_key == "test-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key != "test-key":
                return None
            return {"created_by": "owner-alice"}

        @staticmethod
        def record_event(*args, **kwargs):
            _ = args, kwargs

    class _ProjectStore:
        @staticmethod
        def get(project_id: str):
            if project_id != "proj-1":
                return None
            return SimpleNamespace(id="proj-1", name="项目一", mcp_enabled=True, updated_at="2026-04-02T00:00:00+00:00")

        @staticmethod
        def list_members(project_id: str):
            _ = project_id
            return []

    class _EmployeeStore:
        @staticmethod
        def get(employee_id: str):
            _ = employee_id
            return None

    class _DummyTransportApp:
        async def __call__(self, scope, receive, send):
            _ = scope, receive
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    app = proxy_apps.ProjectMcpProxyApp(
        project_store=_ProjectStore(),
        employee_store=_EmployeeStore(),
        usage_store=_UsageStore(),
        current_api_key_ctx=SimpleNamespace(set=lambda value: value),
        current_developer_name_ctx=SimpleNamespace(set=lambda value: value),
        session_keys={},
        session_contexts={},
        project_apps={},
        project_app_signatures={},
        create_project_mcp=lambda project_id: _DummyTransportApp(),
        list_visible_external_mcp_modules=lambda project_id: [],
        replace_path_suffix=lambda path, old, new: path.replace(old, new),
        dual_transport_app_type=_DummyTransportApp,
        project_mcp_app_rev="test-rev",
    )

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/mcp/projects/proj-1/sse",
        "query_string": b"key=test-key&session_id=sess-1",
        "headers": [],
        "client": ("127.0.0.1", 8080),
        "path_params": {"project_id": "proj-1"},
    }
    sent_messages = []

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _send(message):
        sent_messages.append(message)

    asyncio.run(app(scope, _receive, _send))

    assert captured
    assert captured[0]["project_id"] == "proj-1"
    assert captured[0]["endpoint_type"] == "project"
    assert captured[0]["project_name"] == "项目一"
    assert captured[0]["developer_name"] == "alice"
    assert captured[0]["key_owner_username"] == "owner-alice"
    assert captured[0]["transport"] == "sse"
    assert captured[0]["session_id"] == "sess-1"
    assert sent_messages[-1]["type"] == "http.response.body"


def test_system_mcp_activity_lists_multiple_endpoint_types(tmp_path, monkeypatch):
    client, _, project_mcp_presence_service = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    import asyncio

    asyncio.run(
        project_mcp_presence_service.touch_project_mcp_presence(
            endpoint_type="query",
            entity_id="query-center",
            entity_name="统一查询 MCP",
            project_id="proj-1",
            project_name="项目一",
            developer_name="alice",
            key_owner_username="owner-alice",
            api_key="key-alice-12345678",
            client_ip="127.0.0.1",
            transport="sse",
            method="GET",
            path="/mcp/query/sse",
            session_id="sess-q1",
        )
    )
    asyncio.run(
        project_mcp_presence_service.touch_project_mcp_presence(
            endpoint_type="employee",
            entity_id="emp-1",
            entity_name="员工一",
            project_id="proj-1",
            project_name="项目一",
            developer_name="alice",
            key_owner_username="owner-alice",
            api_key="key-alice-12345678",
            client_ip="127.0.0.1",
            transport="streamable-http",
            method="POST",
            path="/mcp/employees/emp-1/mcp",
            session_id="sess-e1",
        )
    )

    response = client.get("/api/system/mcp-monitor/activity")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["active_entries"] == 2
    assert payload["summary"]["active_endpoint_types"] == 2
    assert payload["summary"]["active_projects"] == 1
    assert payload["summary"]["active_developers"] == 2
    assert {item["endpoint_type"] for item in payload["items"]} == {"query", "employee"}


def test_query_mcp_proxy_backfills_project_from_request_context(monkeypatch):
    from fastapi import FastAPI, Request

    from services import dynamic_mcp_proxy_apps as proxy_apps
    from services.dynamic_mcp_transports import replace_path_suffix

    captured: list[dict] = []

    async def _fake_touch_project_mcp_presence(**kwargs):
        captured.append(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(proxy_apps, "_touch_project_mcp_presence", _fake_touch_project_mcp_presence)
    monkeypatch.setattr(proxy_apps, "get_client_ip", lambda scope: "127.0.0.1")

    class _UsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "alice" if api_key == "test-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key != "test-key":
                return None
            return {"created_by": "owner-alice"}

        @staticmethod
        def record_event(*args, **kwargs):
            _ = args, kwargs

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["GET", "POST"])
    async def _echo(request: Request, full_path: str):
        _ = full_path
        await request.body()
        return {"ok": True}

    proxy_app = proxy_apps.QueryMcpProxyApp(
        usage_store=_UsageStore(),
        current_api_key_ctx=SimpleNamespace(set=lambda value: value),
        current_developer_name_ctx=SimpleNamespace(set=lambda value: value),
        session_keys={},
        session_contexts={},
        query_app=downstream,
        save_auto_query_memory=lambda *args, **kwargs: None,
        replace_path_suffix=replace_path_suffix,
    )

    app = FastAPI()
    app.mount("/mcp/query", proxy_app)
    client = TestClient(app)

    response = client.post(
        "/mcp/query/mcp?key=test-key&session_id=sess-q1",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "get_manual_content",
                "arguments": {
                    "project_id": "proj-1",
                    "project_name": "项目一",
                },
            },
        },
    )

    assert response.status_code == 200
    assert captured
    assert captured[-1]["endpoint_type"] == "query"
    assert captured[-1]["project_id"] == "proj-1"
    assert captured[-1]["project_name"] == "项目一"
    assert captured[-1]["key_owner_username"] == "owner-alice"
    assert captured[-1]["session_id"] == "sess-q1"
