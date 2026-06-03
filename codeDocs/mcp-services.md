# MCP 服务详解

## 概述

项目包含 **6 个独立的 MCP 服务**，每个服务负责一种特定的能力领域。所有 MCP 服务基于 **FastMCP（>=3.0）** 框架构建，通过 MCP 协议向外暴露工具（Tools）和资源（Resources）。

---

## 一、技能管理 MCP (`mcp-skills/`)

**服务名：** `skills-service`

### 目录结构

```
mcp-skills/
├── server.py                 # MCP 服务入口
├── pyproject.toml            # Python 项目配置
├── .env.example              # 环境变量模板
├── __init__.py               # 包初始化
├── skills.db                 # 技能数据库 (SQLite)
└── knowledge/
    ├── skills/               # 技能定义 (JSON)
    │   ├── query-mcp-workflow.json      # 统一查询工作流
    │   ├── animation-designer.json
    │   ├── async-python-patterns.json
    │   ├── auth-implementation-patterns.json
    │   ├── css.json
    │   ├── db-query.json
    │   ├── java-spring-boot.json
    │   ├── nodejs-backend-patterns.json
    │   ├── php.json
    │   ├── refactor.json
    │   ├── software-architect.json
    │   ├── sql-optimization-patterns.json
    │   ├── system-mcp-prompts-chat.json
    │   ├── ui.json
    │   └── vue.json
    └── skill-packages/       # 技能包目录（每个技能一个子目录）
        └── query-mcp-workflow/
            ├── SKILL.md      # 技能主文档（Markdown 格式）
            ├── manifest.json # 技能清单（版本、依赖、能力声明）
            ├── prompts/      # 提示词模板
            └── references/   # 参考文档
```

### 暴露的工具 (Tools)

| 工具名 | 参数 | 说明 |
|---|---|---|
| `get_skill` | `skill_id`, `version` | 获取指定技能的完整定义和文档 |
| `list_skills` | `tags`, `domain` | 列出所有可用技能，支持按标签和领域过滤 |
| `install_skill` | `employee_id`, `skill_id` | 将技能安装到指定 AI 员工 |
| `uninstall_skill` | `employee_id`, `skill_id` | 从 AI 员工卸载指定技能 |

### 暴露的资源 (Resources)

| 资源 URI | 说明 |
|---|---|
| `skill://catalog` | 所有技能的摘要目录 |
| `skill://{skill_id}` | 指定技能的完整详情 |
| `skill://{skill_id}/tools` | 指定技能包含的工具列表 |

### 设计意图

技能 MCP 是能力市场的中枢。它管理着从"前端开发（vue/css/ui）"到"后端架构（java-spring-boot/nodejs）"、从"数据库查询"到"代码重构"的全栈技能库。外部 Agent 通过此服务发现和安装需要的技能包。

---

## 二、规则管理 MCP (`mcp-rules/`)

**服务名：** `rules-service`

### 目录结构

```
mcp-rules/
├── server.py                 # MCP 服务入口
├── pyproject.toml            # Python 项目配置
├── __init__.py               # 包初始化
├── .env.example              # 环境变量模板
├── rules.db                  # 规则数据库 (SQLite)
└── knowledge/
    └── rules/                # 规则定义 (JSON)
        ├── coding-standards.json
        ├── architecture.json
        ├── api-design.json
        ├── testing.json
        ├── git-workflow.json
        └── security.json
```

### 暴露的工具 (Tools)

| 工具名 | 参数 | 说明 |
|---|---|---|
| `query_rule` | `keyword`, `domain` | 按关键词和领域模糊检索规则 |
| `get_rule` | `rule_id` | 获取单条规则的完整内容 |
| `submit_rule` | `domain`, `title`, `content`, `severity`, `risk_domain` | 提交新规则（含严重级别和风险域） |
| `evolve_rule` | `rule_id`, `change_description`, `author`, `bump_level` | **规则进化**。根据变更描述自动递增版本号（major/minor/patch） |
| `get_rule_stats` | (无) | 获取规则库统计：总数、领域分布、平均置信度、已验证数、衰减数 |
| `record_feedback` | `rule_id`, `adopted` | **反馈记录**。记录规则被采纳/拒绝，自动调整置信度 |

### 暴露的资源 (Resources)

| 资源 URI | 说明 |
|---|---|
| `rules://catalog` | 所有规则摘要 |
| `rules://domains` | 可用规则领域列表 |
| `rules://{rule_id}` | 单条规则详情 |

### 设计意图

规则 MCP 实现了"规则即代码"的理念。它不仅管理静态规则，还支持规则的**进化（evolve）**——根据使用反馈自动调整置信度和版本。这构成了 AI 员工的"约束层"，确保其行为遵循项目规范。

---

## 三、记忆管理 MCP (`mcp-memory/`)

**服务名：** `memory-service`

### 目录结构

```
mcp-memory/
├── server.py                 # MCP 服务入口
├── pyproject.toml            # Python 项目配置
├── __init__.py               # 包初始化
├── knowledge.db              # 知识库 (SQLite)
└── memory_store.db           # 记忆存储 (SQLite)
```

### 暴露的工具 (Tools)

| 工具名 | 参数 | 说明 |
|---|---|---|
| `save_memory` | `employee_id`, `content`, `type`, `importance`, `project_name` | 保存一条记忆，可指定重要性（0-1）和所属项目 |
| `recall` | `employee_id`, `query`, `limit` | 按关键词检索记忆，返回最匹配的 N 条 |
| `forget` | `memory_id` | 删除一条指定记忆 |
| `compress_memories` | `employee_id`, `keep_top` | **记忆压缩**。保留高重要性记忆，清除低价值记忆 |
| `save_identity_signal` | `employee_id`, `signal_type`, `content`, `importance`, `project_name` | **保存身份信号**。这是"数字分身"的核心——记录 AI 员工的偏好、决策模式、沟通风格 |
| `list_identity_signals` | `employee_id`, `signal_type` | 查询指定类型的身份信号 |
| `set_memory_classification` | `memory_id`, `level`, `purpose_tags` | 给记忆设置分级标签（公开/内部/机密）和用途标签 |

### 暴露的资源 (Resources)

| 资源 URI | 说明 |
|---|---|
| `memory://{employee_id}/all` | 员工所有记忆 |
| `memory://{employee_id}/recent` | 最近记忆 |
| `memory://{employee_id}/important` | 重要记忆（重要性阈值筛选） |
| `memory://{employee_id}/identity-signals` | 数字分身的身份信号集合 |
| `memory://{employee_id}/isolation-policy` | 隔离策略（控制记忆的访问范围） |

### 设计意图

记忆 MCP 是 AI 员工的"长期记忆系统"。核心特性：
- **身份信号 (Identity Signals)**：区别于普通记忆，这是构建"数字分身"的关键——记录 AI 员工的个性、偏好和决策模式
- **记忆压缩 (Compress)**：自动清理低价值记忆，保持记忆库的效率和相关性
- **双后端支持**：开发环境用 SQLite，生产环境通过 bridge 连接 PostgreSQL

---

## 四、人设管理 MCP (`mcp-persona/`)

**服务名：** `persona-service`

### 目录结构

```
mcp-persona/
├── server.py                 # MCP 服务入口
└── pyproject.toml            # Python 项目配置
```

### 设计意图

人设 MCP 管理 AI 员工的"人格层"。每个 AI 员工可以有不同的：
- **角色定义**：前端工程师、后端架构师、产品经理等
- **性格特征**：严谨/创意、主动/被动、详细/简洁
- **沟通风格**：正式/轻松、中文/英文、技术向/业务向

这层配置决定了 AI 员工在交互中的"语气"和"思维方式"。

---

## 五、进化引擎 MCP (`mcp-evolution/`)

**服务名：** `evolution-service`

### 目录结构

```
mcp-evolution/
├── server.py                 # MCP 服务入口
├── pyproject.toml            # Python 项目配置
└── __init__.py               # 包初始化
```

### 设计意图

进化引擎是 AI 员工的"自我改进"系统。它：
1. 收集 AI 员工的使用反馈和任务表现数据
2. 分析弱点和改进机会
3. 自动调整技能组合、规则优先级和记忆策略
4. 生成进化报告，记录改进轨迹

---

## 六、同步 MCP (`mcp-sync/`)

**服务名：** `sync-service`

### 目录结构

```
mcp-sync/
├── server.py                 # MCP 服务入口
└── pyproject.toml            # Python 项目配置
```

### 设计意图

同步服务确保所有 MCP 服务之间的数据一致性。当技能、规则、记忆等模块发生变更时，同步服务负责：
- 跨服务状态同步
- 缓存失效通知
- 数据迁移协调

---

## MCP 服务间关系

```
                    ┌─────────────┐
                    │ sync (同步)  │ ← 协调所有服务的数据一致性
                    └──────┬──────┘
                           │
    ┌──────────────────────┼──────────────────────┐
    │                      │                      │
┌───▼────┐          ┌──────▼──────┐        ┌──────▼──────┐
│ skills  │          │    rules     │        │   memory    │
│ (技能)  │          │   (规则)     │        │   (记忆)    │
└───┬─────┘          └──────┬──────┘        └──────┬──────┘
    │                       │                      │
    │     ┌─────────────────┼──────────────────────┤
    │     │                 │                      │
    └─────┼─────────────────┼──────────────────────┘
          │                 │
    ┌─────▼─────┐    ┌──────▼──────┐
    │  persona   │    │  evolution  │
    │  (人设)    │    │  (进化)     │
    └───────────┘    └─────────────┘
```

- **skills** + **rules** = 员工的能力和约束
- **memory** + **persona** = 员工的知识和人格
- **evolution** = 根据反馈持续优化上述四者
- **sync** = 保证跨服务状态一致
