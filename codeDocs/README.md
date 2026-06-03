# AI 员工工厂 — 代码文档

> 生成日期：2026-06-03 | 基于当前代码仓库 `main` 分支

## 文档索引

| 文档 | 说明 |
|---|---|
| [directory-structure.md](./directory-structure.md) | **完整目录结构 + 每个文件的讲解**（核心文档） |
| [web-admin.md](./web-admin.md) | 管理台（FastAPI 后端 + Vue3 前端）详细拆解 |
| [mcp-services.md](./mcp-services.md) | 六大 MCP 服务详解（skills/rules/memory/persona/evolution/sync） |
| [deploy-and-config.md](./deploy-and-config.md) | Docker 部署、环境配置、飞书技能包、规则体系 |

## 项目简介

**AI 员工工厂** 是一个基于 MCP（Model Context Protocol）的 AI-Native 开发与管理平台。它把项目上下文、员工能力、技能、规则、记忆、人设、任务树和工作轨迹沉淀为可被外部 AI、IDE、CLI、后台系统稳定调用的 MCP 能力。

### 架构分层

```
┌─────────────────────────────────────────────┐
│              外部消费者                       │
│   Claude Code / Codex CLI / IDE / 飞书       │
└──────────────────┬──────────────────────────┘
                   │ MCP Protocol
┌──────────────────┴──────────────────────────┐
│           MCP 服务层 (6 个独立服务)            │
│  skills │ rules │ memory │ persona │         │
│  evolution │ sync │ + 统一查询入口            │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────┴──────────────────────────┐
│           Web-Admin 管理台                    │
│  FastAPI 后端 (28 个路由模块)                 │
│  Vue3 前端 (Element Plus)                    │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────┴──────────────────────────┐
│           数据 & 基础设施                      │
│  PostgreSQL 17 │ Redis 7 │ SQLite (备用)      │
│  Docker Compose │ Nginx                      │
└─────────────────────────────────────────────┘
```

### 核心技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Composition API + Element Plus + Vite 5 |
| 后端 API | Python FastAPI + Pydantic + Uvicorn |
| MCP 服务 | FastMCP (>=3.0) |
| 数据库 | PostgreSQL 17 (主) + Redis 7 + SQLite (usage 备用) |
| 认证 | JWT HS256 (PyJWT) |
| 包管理 | 前端 npm / 后端 uv |
| 部署 | Docker Compose (开发/测试/生产 三套编排) |
| 反向代理 | Nginx (前端容器内置) |
| AI 运行时 | Agent Runtime v2 (自定义多模型编排引擎) |
