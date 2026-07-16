# MCP 服务详解

> 更新日期：2026-06-04

当前仓库有两类 MCP 能力：

- 根目录 6 个独立 MCP 服务：`mcp-skills`、`mcp-rules`、`mcp-memory`、`mcp-persona`、`mcp-evolution`、`mcp-sync`。
- Web-Admin API 内部动态 MCP：统一查询 MCP、项目 MCP、员工 MCP、技能 MCP、规则 MCP。

## 一、根目录独立 MCP 服务

这些服务以 `server.py` 为入口，使用 `mcp.server.fastmcp.FastMCP` 构建。它们适合作为轻量、可独立运行的能力服务，也作为系统技能/规则/记忆/人设等知识库的本地源。

### `mcp-skills/` - 技能管理

服务名：`skills-service`

```text
mcp-skills/
├── server.py
├── store.py
├── pyproject.toml
└── knowledge/
    └── skill-packages/
        ├── query-mcp-workflow/
        ├── db-query/
        ├── ui/
        ├── vue/
        ├── css/
        └── ...
```

Tools：

| 工具 | 说明 |
|---|---|
| `get_skill(skill_id, version="")` | 获取技能定义。 |
| `list_skills(tags="", domain="")` | 列出技能，可按标签/领域过滤。 |
| `install_skill(employee_id, skill_id)` | 给员工安装技能。 |
| `uninstall_skill(employee_id, skill_id)` | 从员工卸载技能。 |

Resources：

- `skill://catalog`
- `skill://{skill_id}`
- `skill://{skill_id}/tools`

当前技能包覆盖：统一查询工作流、数据库查询、重构、前端、CSS、Vue、Node.js 后端、认证、异步 Python、Java Spring Boot、PHP、SQL 优化、软件架构、系统 MCP prompts、AI 图表 JSON 等。

### `mcp-rules/` - 规则管理

服务名：`rules-service`

Tools：

| 工具 | 说明 |
|---|---|
| `query_rule(keyword, domain="")` | 按关键词/领域查询规则。 |
| `get_rule(rule_id)` | 获取单条规则。 |
| `submit_rule(domain, title, content, severity, risk_domain)` | 提交规则。 |
| `evolve_rule(rule_id, change_description, author, bump_level)` | 演化规则并递增版本。 |
| `get_rule_stats()` | 获取规则统计。 |
| `record_feedback(rule_id, adopted)` | 记录采纳/拒绝反馈。 |

Resources：

- `rules://catalog`
- `rules://domains`
- `rules://{rule_id}`

### `mcp-memory/` - 记忆管理

服务名：`memory-service`

Tools：

| 工具 | 说明 |
|---|---|
| `save_memory(employee_id, content, type, importance, project_name)` | 保存记忆。 |
| `recall(employee_id, query="", limit=10)` | 召回记忆。 |
| `forget(memory_id)` | 删除记忆。 |
| `compress_memories(employee_id, keep_top=50)` | 压缩记忆。 |
| `save_identity_signal(...)` | 保存身份信号。 |
| `list_identity_signals(employee_id, signal_type="")` | 查询身份信号。 |
| `set_memory_classification(...)` | 设置记忆分类和用途标签。 |

Resources：

- `memory://{employee_id}/all`
- `memory://{employee_id}/recent`
- `memory://{employee_id}/important`
- `memory://{employee_id}/identity-signals`
- `memory://{employee_id}/isolation-policy`

实现上保留 SQLite/本地知识库，并可通过 Web-Admin store bridge 与 PostgreSQL 体系衔接。

### `mcp-persona/` - 人设管理

服务名：`persona-service`

Tools：

| 工具 | 说明 |
|---|---|
| `get_persona(persona_id)` | 获取人设。 |
| `set_tone(persona_id, tone)` | 设置语气。 |
| `set_style(persona_id, verbosity="", behaviors="", style_hints="")` | 设置表达风格。 |
| `train_persona_from_corpus(...)` | 根据语料训练人设。 |
| `set_decision_policy(...)` | 设置决策策略。 |
| `set_delegation_scope(...)` | 设置委派范围。 |
| `get_persona_drift(persona_id)` | 查看漂移。 |
| `snapshot_persona(persona_id)` | 生成快照。 |
| `restore_persona(snapshot_id)` | 恢复快照。 |
| `evaluate_persona_alignment(persona_id)` | 评估一致性。 |

Resources：

- `persona://{persona_id}`
- `persona://templates`
- `persona://{persona_id}/drift-report`
- `persona://{persona_id}/snapshots`
- `persona://{persona_id}/alignment-score`

### `mcp-evolution/` - 进化引擎

服务名：`evolution-engine`

Tools：

| 工具 | 说明 |
|---|---|
| `analyze_usage_patterns(employee_id, limit=200)` | 分析使用模式。 |
| `propose_rule(...)` | 提出候选规则。 |
| `auto_evolve(...)` | 自动进化。 |
| `review_candidate(...)` | 审核候选。 |
| `get_evolution_report(employee_id)` | 获取进化报告。 |

Resources：

- `evolution://candidates/{employee_id}`
- `evolution://updates/{employee_id}`
- `evolution://report/{employee_id}`

### `mcp-sync/` - 同步服务

服务名：`sync-service`

Tools：

| 工具 | 说明 |
|---|---|
| `push_update(...)` | 推送更新。 |
| `sync_state(employee_id)` | 同步员工状态。 |
| `notify_agent(...)` | 通知 Agent。 |

Resources：

- `sync://status/{employee_id}`
- `sync://events/{employee_id}`

## 二、Web-Admin 动态 MCP

动态 MCP 挂载在 FastAPI 应用中，源码集中在 `web-admin/api/services/mcp/`。它们是当前项目实际工作流最重要的 MCP 入口。

### 挂载路径

| 路径 | 说明 |
|---|---|
| `/mcp/query` | 统一查询 MCP，聚合项目、员工、规则、任务树和工作轨迹。 |
| `/mcp/projects/{project_id}` | 项目 MCP，围绕单个项目暴露手册、成员、规则、技能、协作工具等。 |
| `/mcp/employees/{employee_id}` | 员工 MCP，围绕单个员工暴露手册、规则、技能和记忆工具。 |
| `/mcp/skills/{skill_id}` | 技能 MCP proxy。 |
| `/mcp/rules/{rule_id}` | 规则 MCP proxy。 |

### 关键模块

| 模块 | 说明 |
|---|---|
| `dynamic_mcp_runtime.py` | 创建并导出各类 MCP proxy app。 |
| `dynamic_mcp_apps_query.py` | 统一查询 MCP 的工具定义。 |
| `dynamic_mcp_apps_project.py` | 项目 MCP 工具。 |
| `dynamic_mcp_apps_employee.py` | 员工 MCP 工具。 |
| `dynamic_mcp_context.py` | 项目/员工上下文聚合。 |
| `dynamic_mcp_collaboration.py` | 项目协作编排。 |
| `dynamic_mcp_skill_executor.py` | 项目/员工技能代理执行。 |
| `dynamic_mcp_skill_proxies.py` | 技能代理工具生成。 |
| `dynamic_mcp_external_tools.py` | 外部工具接入。 |
| `dynamic_mcp_transports.py` | MCP transport 兼容。 |
| `query_mcp_project_state.py` | 统一查询 MCP 的本地状态、requirement 和任务树状态处理。 |
| `project_mcp_presence.py` | 项目 MCP 存在性检测。 |

## 三、统一查询 MCP 工作流

统一查询 MCP 的核心是让 Codex/Claude/IDE 等宿主只接入一个入口，也能完成：

1. 显式绑定 `project_id`、`chat_session_id`、`session_id`。
2. 读取项目手册、员工手册和相关规则。
3. 分析任务、聚合上下文、生成计划。
4. 创建并维护本地 requirement。
5. 推进任务树节点状态。
6. 保存工作事实、会话事件、检查点和交付报告。
7. 在中断后按同一会话线恢复。

当前本地工作流技能副本位于：

```text
.ai-employee/skills/query-mcp-workflow/
├── SKILL.md
└── manifest.json
```

当前 canonical 本地状态路径：

```text
.ai-employee/query-mcp/active-sessions/<chat_session_id>.json
.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json
.ai-employee/requirements/<project_id>/<chat_session_id>.json
```

`.ai-employee/query-mcp/active/<project_id>.json` 是历史遗留项目级指针，只允许只读恢复，禁止新写，也不能作为当前窗口状态。

## 四、和桌面智能体 Runtime 的关系

MCP 工作流负责上下文、规则、任务树和状态闭环；Tauri `liuagent_core` 负责真实执行型任务的模型循环、本机工具、权限与暂停恢复。

相关路径：

- `web-admin/api/services/runtime/`
- `web-admin/api/services/assistant/`
- `web-admin/api/services/chat/`
- `web-admin/frontend/src-tauri/src/liuagent_core/`

常见链路：

```text
用户需求
  -> assistant 工作流识别
  -> 能力路由
  -> /mcp/query 或项目/员工 MCP 聚合上下文
  -> requirement + 任务树绑定
  -> 桌面 liuagent Runtime / 本地连接器 / 项目工具执行
  -> 权限、信任、验证策略
  -> 工作事实、任务树完成、交付报告
```

## 五、独立 MCP 与动态 MCP 的分工

| 能力 | 独立 MCP 服务 | Web-Admin 动态 MCP |
|---|---|---|
| 技能目录 | `mcp-skills` 管理系统技能包 | 项目/员工技能 proxy、技能资源和执行 |
| 规则目录 | `mcp-rules` 管理基础规则能力 | 项目规则、员工规则、反馈升级和经验规则 |
| 记忆 | `mcp-memory` 提供轻量记忆工具 | 项目记忆、员工记忆、工作事实和工作会话 |
| 人设 | `mcp-persona` 管理人设工具 | 员工页面、人设路由和项目上下文聚合 |
| 进化 | `mcp-evolution` 提供候选和报告工具 | 反馈工单、候选评审、进化报告页面 |
| 同步 | `mcp-sync` 推送和状态同步 | Web-Admin 同步路由、MCP 监控和 project state |

实际产品主链路优先走 Web-Admin 动态 MCP；根目录独立 MCP 服务提供基础能力、系统技能包和轻量接入面。
