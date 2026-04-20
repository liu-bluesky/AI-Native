"""AI 员工工厂 — API 网关"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.db_migrations import run_postgres_migrations
from core.deps import (
    project_experience_summary_store,
    project_material_store,
    project_store,
    project_studio_export_store,
)
from routers import (
    agent_templates,
    changelog_entries,
    init_auth,
    market,
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
    mcp_monitor,
    dictionaries,
    online_users,
    work_sessions,
)
from services.dynamic_mcp_runtime import (
    employee_mcp_proxy_app,
    project_mcp_proxy_app,
    query_mcp_proxy_app,
    rule_mcp_proxy_app,
    skill_mcp_proxy_app,
)
from services.project_experience_summary_service import (
    ProjectExperienceSummaryBackgroundService,
)
from services.studio_export_service import StudioExportBackgroundService


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.auto_run_db_migrations and (
            settings.core_store_backend == "postgres" or settings.usage_store_backend == "postgres"
        ):
            run_postgres_migrations(settings.database_url)
        worker = StudioExportBackgroundService(
            project_store=project_store,
            project_studio_export_store=project_studio_export_store,
            project_material_store=project_material_store,
            api_data_dir=settings.api_data_dir,
            poll_interval_seconds=settings.studio_export_worker_poll_seconds,
        )
        experience_summary_worker = ProjectExperienceSummaryBackgroundService(
            project_store=project_store,
            project_experience_summary_store=project_experience_summary_store,
            poll_interval_seconds=settings.studio_export_worker_poll_seconds,
        )
        app.state.studio_export_worker = worker
        app.state.project_experience_summary_worker = experience_summary_worker
        if settings.studio_export_worker_enabled:
            worker.start()
            experience_summary_worker.start()
        try:
            yield
        finally:
            await experience_summary_worker.stop()
            await worker.stop()

    app = FastAPI(title="AI Employee Factory", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_allow_origins,
        allow_methods=settings.api_cors_allow_methods,
        allow_headers=settings.api_cors_allow_headers,
        allow_credentials=settings.api_cors_allow_credentials,
    )

    for r in (
        init_auth,
        market,
        agent_templates,
        changelog_entries,
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
        mcp_monitor,
        dictionaries,
        online_users,
        work_sessions,
    ):
        app.include_router(r.router)
        public_router = getattr(r, "public_router", None)
        if public_router is not None:
            app.include_router(public_router)

    app.mount("/mcp/rules/{rule_id}", rule_mcp_proxy_app)
    app.mount("/mcp/skills/{skill_id}", skill_mcp_proxy_app)
    app.mount("/mcp/query", query_mcp_proxy_app)
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
