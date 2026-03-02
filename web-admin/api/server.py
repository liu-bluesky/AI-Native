"""AI 员工工厂 — API 网关"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware

from routers import init_auth, employees, skills, rules, memory, personas, evolution, sync, usage
from dynamic_mcp import employee_mcp_proxy_app, rule_mcp_proxy_app, skill_mcp_proxy_app


def _split_env_list(env_name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or default


def _env_bool(env_name: str, default: bool) -> bool:
    raw = os.environ.get(env_name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


app = FastAPI(title="AI Employee Factory", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_split_env_list("API_CORS_ALLOW_ORIGINS", ["*"]),
    allow_methods=_split_env_list("API_CORS_ALLOW_METHODS", ["*"]),
    allow_headers=_split_env_list("API_CORS_ALLOW_HEADERS", ["*"]),
    allow_credentials=_env_bool("API_CORS_ALLOW_CREDENTIALS", False),
)

for r in (init_auth, employees, skills, rules, memory, personas, evolution, sync, usage):
    app.include_router(r.router)

app.mount("/mcp/rules/{rule_id}", rule_mcp_proxy_app)
app.mount("/mcp/skills/{skill_id}", skill_mcp_proxy_app)
app.mount("/mcp/employees/{employee_id}", employee_mcp_proxy_app)


# Compatibility: some MCP clients probe OAuth/OIDC well-known endpoints even when using API key auth.
# Return 204 to indicate "no metadata here" and avoid noisy 404 logs.
@app.get("/.well-known/oauth-authorization-server")
@app.get("/.well-known/oauth-authorization-server/{resource_path:path}")
@app.get("/.well-known/openid-configuration")
@app.get("/.well-known/openid-configuration/{resource_path:path}")
@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/{resource_path:path}")
async def mcp_well_known_probe(resource_path: str = ""):
    return Response(status_code=204)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "server:app",
        host=os.environ.get("API_HOST", "0.0.0.0"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=_env_bool("API_RELOAD", True),
    )


if __name__ == "__main__":
    run()
