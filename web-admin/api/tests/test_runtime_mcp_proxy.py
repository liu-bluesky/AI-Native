from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from services.mcp.dynamic_mcp_proxy_apps import RuntimeMcpProxyApp


class _ProjectProxyProbe:
    async def __call__(self, scope, receive, send):
        response = JSONResponse(
            {
                "project_id": (scope.get("path_params") or {}).get("project_id", ""),
                "path": scope.get("path", ""),
            }
        )
        await response(scope, receive, send)


def _client() -> TestClient:
    app = FastAPI()
    app.mount("/mcp/runtime", RuntimeMcpProxyApp(_ProjectProxyProbe()))
    return TestClient(app)


def test_runtime_mcp_requires_explicit_project_context():
    response = _client().get("/mcp/runtime/mcp")

    assert response.status_code == 400
    assert response.json()["code"] == "mcp.project_context_missing"


def test_runtime_mcp_routes_to_project_provider_without_exposing_project_server_name():
    response = _client().get(
        "/mcp/runtime/mcp",
        params={"project_id": "proj-657fe77f"},
    )

    assert response.status_code == 200
    assert response.json()["project_id"] == "proj-657fe77f"
