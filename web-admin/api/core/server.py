"""AI 员工工厂 — API 网关"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from routers import (
    agent_templates,
    init_auth,
    system_config,
    projects,
    employees,
    skill_resources,
    skills,
    rules,
    llm_providers,
    memory,
    personas,
    evolution,
    sync,
    usage,
    feedback_upgrade,
    users,
    roles,
    mcp_modules,
)
from services.dynamic_mcp_runtime import (
    employee_mcp_proxy_app,
    project_mcp_proxy_app,
    rule_mcp_proxy_app,
    skill_mcp_proxy_app,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI Employee Factory", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_allow_origins,
        allow_methods=settings.api_cors_allow_methods,
        allow_headers=settings.api_cors_allow_headers,
        allow_credentials=settings.api_cors_allow_credentials,
    )

    for r in (
        init_auth,
        agent_templates,
        system_config,
        projects,
        employees,
        skill_resources,
        skills,
        rules,
        llm_providers,
        memory,
        personas,
        evolution,
        sync,
        usage,
        feedback_upgrade,
        users,
        roles,
        mcp_modules,
    ):
        app.include_router(r.router)

    app.mount("/mcp/rules/{rule_id}", rule_mcp_proxy_app)
    app.mount("/mcp/skills/{skill_id}", skill_mcp_proxy_app)
    app.mount("/mcp/projects/{project_id}", project_mcp_proxy_app)
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

    return app


app = create_app()


def run() -> None:
    import uvicorn
    settings = get_settings()

    uvicorn.run(
        "server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )


if __name__ == "__main__":
    run()
