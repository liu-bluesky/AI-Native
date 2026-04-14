# AI 员工工厂 — 项目总览

> 面向 AI 智能体的上下文入口。阅读本文件即可理解项目全貌。

## 定位

基于 MCP（Model Context Protocol）的 AI-Native 开发平台。用户可自由组合 Skills + Rules + Memory + Persona 创建多个 AI 员工，通过进化引擎实现"越用越聪明"。

## 当前接入重点

当前项目已经补齐两类项目级入口：

- 项目 MCP：适合直接面向某个项目做上下文查询、规则读取、技能调用和项目协作编排。
- 统一查询 MCP：适合宿主只接一个聚合入口时，先定位项目/员工/规则，再读取正文或代理项目协作。

### 主次定位

当前项目默认按 `MCP-first` 运作，主次关系固定如下：

- 主入口：`项目 MCP`、`统一查询 MCP`，用于真正承载项目上下文读取、规则检索、技能调用、协作编排、任务树推进和工作轨迹沉淀。
- 次入口：`web-admin` 中的 AI 对话页面，用于运营配置、演示体验、人工验证、调试排查和结果可视化。
- 这意味着平台核心能力的完成标准，优先看是否能通过 MCP 稳定暴露和复用，而不是是否先在聊天框里“看起来能用”。
- 新增功能若涉及执行、协作、记忆、规则或上下文，默认先设计其 MCP 接口、追踪链路和项目级数据归属，再决定是否补聊天 UI。

### 新功能开发默认原则

- 不要把 AI 对话框当作产品主入口来反推平台架构；应优先从 MCP 调用面设计能力边界。
- 对话页面可以先行做验证，但最终应回收到 `tool`、`resource`、`prompt`、`task tree`、`work session` 等可追溯能力层。
- 若某项能力只能在页面聊天框中临时使用，且无法映射到项目 MCP 或统一查询 MCP，则默认视为能力尚未平台化。
- 前端页面的价值主要在于配置、观测、审核和人工介入，而不是替代 MCP 成为平台的第一入口。

当前项目协作口径：

- `execute_project_collaboration` 是统一协作编排入口。
- 是否单人主责、是否需要多人协作以及如何拆分，不由固定行业模板决定，而是由 AI 结合项目手册、员工手册、规则和工具自主判断。
- 若单个员工已能闭环，可保持单人主责；若需要多人协作，应先明确负责人、边界和交接。

推荐继续阅读：

- `docs/30-专项功能方案/项目模块MCP化设计.md`
- `docs/30-专项功能方案/项目模块MCP联调示例.md`
- `docs/30-专项功能方案/统一查询MCP联调示例.md`
- `docs/30-专项功能方案/MCP优先下的Agent运行时补强方案.md`

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Composition API + Element Plus + Vite |
| 后端 API | Python FastAPI + Pydantic |
| MCP 服务 | Python FastMCP 3.0+ |
| 数据存储 | JSON 文件（Skills/Rules/Persona/Evolution/Sync）、SQLite（Memory） |
| 认证 | JWT HS256（PyJWT） |
| 包管理 | 前端 npm / 后端 pyproject.toml |

## 目录结构

```
ai设计规范/
├── docs/
│   ├── 00-项目总览/
│   │   └── PROJECT.md                    ← 你在这里
│   ├── 10-平台架构设计/
│   │   └── AI-Native开发平台设计规范.md   ← 基础设施层设计文档
│   ├── 20-产品应用设计/
│   │   └── AI-员工工厂设计规范.md         ← 应用层设计文档
│   ├── 30-专项功能方案/
│   │   └── 功能分割设计.md
│   ├── 40-数据存储升级/
│   │   └── PostgreSQL升级规划.md
│   └── 反馈驱动规则升级模块/
│       ├── README.md
│       ├── 需求文档清单.md
│       └── PRD-反馈驱动规则升级模块.md
├── CLAUDE.md                     ← AI 工具强制规则（Rule Porter）
├── rules/                        ← AI 可消费的规则文件体系
│   ├── frontend.md               ← 前端编码规范
│   ├── backend.md                ← 后端编码规范
│   ├── ui-design.md              ← UI 设计规范（Design Token 体系）
│   ├── mcp-service.md            ← MCP 服务开发规范
│   └── architecture.md           ← 架构约束与数据流规则
├── agents/                       ← 项目专属智能体定义
│   ├── frontend-expert.md
│   ├── backend-expert.md
│   ├── mcp-architect.md
│   └── security-auditor.md
├── mcp-skills/                   ← 技能管理 MCP 服务
├── mcp-rules/                    ← 规则管理 MCP 服务
├── mcp-memory/                   ← 记忆管理 MCP 服务
├── mcp-persona/                  ← 人设管理 MCP 服务
├── mcp-evolution/                ← 进化引擎 MCP 服务
├── mcp-sync/                     ← 实时同步 MCP 服务
├── web-admin/                    ← 管理面板
│   ├── api/                      ← FastAPI 网关
│   │   ├── server.py             ← 入口（~20 行，仅注册路由）
│   │   ├── stores.py             ← importlib 桥接层（加载 6 个 MCP Store）
│   │   ├── deps.py               ← 公共依赖（require_auth、store 实例）
│   │   ├── models/requests.py    ← Pydantic 请求模型
│   │   └── routers/              ← 按域拆分的 APIRouter 模块
│   │       ├── init_auth.py      ← 初始化 & 认证
│   │       ├── employees.py      ← 员工 CRUD
│   │       ├── skills.py         ← 技能管理
│   │       ├── rules.py          ← 规则管理
│   │       ├── memory.py         ← 记忆代理
│   │       ├── personas.py       ← 人设代理
│   │       ├── evolution.py      ← 进化引擎
│   │       └── sync.py           ← 同步管理
│   └── frontend/                 ← Vue 3 SPA
│       └── src/views/            ← 按域分组的视图
│           ├── Layout.vue        ← 全局布局
│           ├── auth/             ← InitPage, LoginPage
│           ├── employees/        ← EmployeeList, EmployeeCreate, EmployeeEdit, EmployeeDetail
│           ├── skills/           ← SkillList, SkillCreate(目录导入), SkillEdit, SkillDetail
│           ├── rules/            ← RuleList, RuleCreate, RuleEdit, RuleDetail
│           ├── memory/           ← MemoryManager
│           ├── personas/         ← PersonaList, PersonaCreate, PersonaEdit, PersonaDetail
│           ├── evolution/        ← EvolutionReport, CandidateReview
│           └── sync/             ← SyncStatus
```

## MCP 服务矩阵

| 服务 | FastMCP 名称 | 存储 | 核心 Tools |
|------|-------------|------|-----------|
| mcp-skills | skills-service | JSON 文件 | get_skill, list_skills, install_skill, uninstall_skill |
| mcp-rules | rules-service | JSON 文件 | query_rule, get_rule, submit_rule, evolve_rule, record_feedback |
| mcp-memory | memory-service | SQLite | save_memory, recall, forget, compress_memories |
| mcp-persona | persona-service | JSON 文件 | get_persona, set_tone, train_persona_from_corpus, snapshot_persona |
| mcp-evolution | evolution-engine | JSON 文件 | analyze_usage_patterns, propose_rule, auto_evolve, review_candidate |
| mcp-sync | sync-service | JSON 文件 | push_update, sync_state, notify_agent |

## 六层架构

```
用户界面层 (Vue 3 SPA)
    ↕ HTTP/JWT
API 网关层 (FastAPI web-admin/api/)
    ↕ 直接 import Store
MCP 服务层 (6 个 FastMCP 微服务)
    ↕ JSON 文件 / SQLite
数据存储层
    ↕ 使用日志
进化引擎层 (mcp-evolution)
    ↕ push_update
同步层 (mcp-sync)
```

## 核心模式速查

- **数据模型**: `@dataclass(frozen=True)` — 全部不可变
- **存储层**: `XxxStore` 类，JSON 文件 CRUD（Memory 用 SQLite）
- **ID 生成**: `f"{prefix}-{uuid4().hex[:8]}"`
- **时间戳**: ISO 8601 字符串 `_now_iso()`
- **序列化**: `_serialize_xxx()` / `_deserialize_xxx()` 函数对
- **前端 API**: axios 实例 + JWT Bearer 拦截器，响应自动解包 `res.data`
- **后端路由**: APIRouter 按域拆分，`routers/*.py`，通过 `stores.py` importlib 桥接 MCP Store
- **技能创建**: 前端默认 `POST /api/skills/import-file` 上传 ZIP 技能包导入（也支持 `/api/skills` 目录导入）
- **前端路由**: hash 模式，懒加载 `() => import('../views/{domain}/Xxx.vue')`
- **项目协作**: 优先通过 `execute_project_collaboration` 进入统一编排；需要人工控参时回退到手动编排链路

## 快速启动

```bash
# 后端（开发模式，支持热更新）
cd web-admin/api && pip install -e . && python init_admin.py && python server.py

# 后端（生产模式）
cd web-admin/api && uvicorn server:app --host 0.0.0.0 --port 8000

# 后端（开放访问，可通过环境变量覆盖）
cd web-admin/api && API_HOST=0.0.0.0 API_PORT=8000 API_CORS_ALLOW_ORIGINS="*" python server.py

# 前端
cd web-admin/frontend && npm install && npm run dev

# MCP 服务（独立运行）
cd mcp-skills && pip install -e . && python server.py
```

## 规则文件索引

| 文件 | 职责 | 何时阅读 |
|------|------|---------|
| `rules/frontend.md` | Vue 3 + Element Plus 编码规范 | 修改前端代码前 |
| `rules/backend.md` | Python FastAPI + FastMCP 编码规范 | 修改后端代码前 |
| `rules/ui-design.md` | UI 设计规范（Design Token 体系） | 涉及样式/布局/新组件时 |
| `rules/mcp-service.md` | MCP 服务开发规范 | 新增/修改 MCP 服务时 |
| `rules/architecture.md` | 架构约束与安全边界 | 跨层/跨服务变更时 |
