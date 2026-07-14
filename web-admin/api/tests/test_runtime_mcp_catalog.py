import pytest

from services.mcp import dynamic_mcp_runtime as runtime


class _FakeTool:
    def __init__(self, payload: dict):
        self.payload = payload

    def model_dump(self, **_kwargs):
        return dict(self.payload)


class _FakeMcp:
    async def list_tools(self):
        return [
            _FakeTool(
                {
                    "name": "list_project_members",
                    "description": "列出项目智能体",
                    "inputSchema": {"type": "object"},
                    "meta": {
                        "domain": "system",
                        "server_id": "system",
                        "canonical_tool_id": "system.system.list_project_members",
                    },
                }
            ),
            _FakeTool(
                {
                    "name": "external__feishu__list_chats",
                    "description": "列出飞书群聊",
                    "inputSchema": {"type": "object"},
                    "meta": {
                        "domain": "integrations",
                        "server_id": "feishu-prod",
                        "canonical_tool_id": "integrations.feishu-prod.list_chats",
                    },
                }
            ),
        ]


@pytest.fixture(autouse=True)
def _runtime_catalog_stubs(monkeypatch):
    monkeypatch.setattr(runtime, "_build_project_mcp_server_impl", lambda *_args, **_kwargs: _FakeMcp())
    monkeypatch.setattr(
        runtime,
        "list_project_external_server_catalog_runtime",
        lambda _project_id: [
            {
                "server_id": "feishu-prod",
                "display_name": "飞书生产环境",
                "description": "飞书集成",
                "domain": "integrations",
                "source": "user-configured",
                "enabled": True,
                "health": "unavailable",
                "tool_count": 0,
            }
        ],
    )


@pytest.mark.asyncio
async def test_runtime_catalog_uses_registered_tools_and_preserves_server_identity():
    result = await runtime.get_project_runtime_mcp_catalog_runtime("proj-1")

    assert result["ok"] is True
    assert result["physical_server"] == "runtime"
    assert result["server_count"] == 2
    assert result["tool_count"] == 2
    assert result["tools"] == []
    servers = {item["server_id"]: item for item in result["servers"]}
    assert servers["system"]["tool_count"] == 1
    assert servers["feishu-prod"]["tool_count"] == 1
    assert servers["feishu-prod"]["health"] == "available"


@pytest.mark.asyncio
async def test_runtime_catalog_filters_tool_index_by_server_id():
    result = await runtime.get_project_runtime_mcp_catalog_runtime("proj-1", "feishu-prod")

    assert result["ok"] is True
    assert result["selected_server_id"] == "feishu-prod"
    assert [item["canonical_tool_id"] for item in result["tools"]] == [
        "integrations.feishu-prod.list_chats"
    ]


@pytest.mark.asyncio
async def test_runtime_catalog_rejects_unknown_server_id():
    result = await runtime.get_project_runtime_mcp_catalog_runtime("proj-1", "default")

    assert result["ok"] is False
    assert result["code"] == "mcp.server_not_found"
    assert result["tools"] == []
