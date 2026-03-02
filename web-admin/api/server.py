"""AI 员工工厂 — API 网关"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import init_auth, employees, skills, rules, memory, personas, evolution, sync
from dynamic_mcp import rule_mcp_proxy_app, skill_mcp_proxy_app

app = FastAPI(title="AI Employee Factory", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (init_auth, employees, skills, rules, memory, personas, evolution, sync):
    app.include_router(r.router)

app.mount("/mcp/rules/{rule_id}", rule_mcp_proxy_app)
app.mount("/mcp/skills/{skill_id}", skill_mcp_proxy_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
