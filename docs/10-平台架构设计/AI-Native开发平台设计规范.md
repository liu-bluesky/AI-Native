# AI-Native 开发平台设计规范

> 核心理念：用户可自定义组合 MCP + 规则 + 记忆 + Skills，创建多个 AI 员工，通过进化引擎实现"越用越聪明"。
>
> 平台定位：**AI 员工工厂** 的基础设施层，提供 MCP 服务、知识存储、进化引擎等核心能力。

---

## 目录

1. [平台定位](#1-平台定位)
2. [架构设计](#2-架构设计)
3. [MCP 服务规范](#3-mcp-服务规范)
4. [进化引擎](#4-进化引擎)
5. [落地路径](#5-落地路径)
6. [团队协作](#6-团队协作)
7. [安全设计](#7-安全设计)

---

## 1. 平台定位

### 1.1 与 AI 员工工厂的关系

本文档描述的是 **AI 员工工厂** 的基础设施层，为上层应用提供：

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI 员工工厂 (应用层)                           │
│         用户界面：员工管理、技能市场、规则工作台、进化面板           │
└───────────────────────────┬─────────────────────────────────────┘
                            │ 调用
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                AI-Native 开发平台 (基础设施层)                    │
│                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │ MCP 服务集群  │ │ 进化引擎     │ │ 数据存储层   │            │
│  │ • Skills     │ │ • 模式分析   │ │ • 规则库     │            │
│  │ • Rules      │ │ • 自动提炼   │ │ • 记忆库     │            │
│  │ • Memory     │ │ • 实时推送   │ │ • 日志/向量  │            │
│  │ • Persona    │ │ • 热更新     │ │              │            │
│  │ • Evolution  │ │              │ │              │            │
│  │ • Sync       │ │              │ │              │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 核心能力

| 能力层 | 提供的能力 | 支撑的 AI 员工特性 |
|--------|-----------|-------------------|
| **MCP 服务层** | Skills、Rules、Memory、Persona、Evolution、Sync | 可组合能力 |
| **进化引擎层** | 使用分析、规则生成、增量同步、热更新 | 越用越聪明 |
| **数据存储层** | 规则库、记忆库、使用日志、向量索引 | 知识持久化 |
| **编排层** | 意图路由、权限控制、版本管理、监控 | 多员工管理 |

### 1.3 主入口策略

当前平台默认采用 `MCP-first, Chat-second` 的入口策略：

- `项目 MCP` 和 `统一查询 MCP` 是平台主入口，负责对外暴露核心能力。
- `web-admin` 中的 AI 对话框是次要入口，主要承担配置、验证、排查、演示和可视化职责。
- 判断一个新能力是否真正完成，优先标准是它能否以 MCP 工具、资源、提示词或项目级执行上下文的形式被稳定复用。
- 聊天 UI 可以作为体验层先验证交互，但不应主导平台能力建模，也不应替代 MCP 成为系统真实边界。

对后续架构和功能设计的约束如下：

- 新能力默认先定义 MCP 入口、权限边界、项目级归属和追踪链路，再补后台或聊天页面。
- 需要长期复用或跨宿主接入的能力，不应只沉淀在页面交互逻辑里。
- 页面层应优先承担配置、观测、审核、手动介入和调试，而不是成为唯一的能力承载面。

---

## 2. 架构设计

### 2.1 平台全景

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            用户界面层 (User Interface)                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │   AI 员工管理    │  │   技能市场       │  │   规则工作台     │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI 员工编排层 (Orchestrator)                          │
│                                                                              │
│   用户创建 AI 员工：选择 Skills + 规则集 + 记忆库 + 人设                      │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  AI 员工实例                                                          │   │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐           │   │
│  │  │ 前端专家   │ │ 后端专家   │ │ 测试工程师 │ │ 运维专家   │  ...      │   │
│  │  │           │ │           │ │           │ │           │           │   │
│  │  │ Skills:   │ │ Skills:   │ │ Skills:   │ │ Skills:   │           │   │
│  │  │ • React   │ │ • Python  │ │ • Jest    │ │ • K8s     │           │   │
│  │  │ • CSS     │ │ • Django  │ │ • Cypress │ │ • Docker  │           │   │
│  │  │           │ │           │ │           │ │           │           │   │
│  │  │ 规则:     │ │ 规则:     │ │ 规则:     │ │ 规则:     │           │   │
│  │  │ 团队前端规│ │ 后端规范  │ │ 测试策略  │ │ 部署规范  │           │   │
│  │  │           │ │           │ │           │ │           │           │   │
│  │  │ 记忆:     │ │ 记忆:     │ │ 记忆:     │ │ 记忆:     │           │   │
│  │  │ 项目上下文│ │ 业务领域  │ │ 缺陷历史  │ │ 环境配置  │           │   │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MCP 编排层 (MCP Orchestrator)                          │
│  ┌───────────┬───────────┬───────────┬───────────┬───────────┐            │
│  │  意图路由   │  权限控制   │  版本管理   │  负载均衡   │  可观测性  │            │
│  └───────────┴───────────┴───────────┴───────────┴───────────┘            │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ MCP Protocol
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MCP 服务层 (Capability Pool)                          │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │  Skills MCP     │  │  Rules MCP      │  │  Memory MCP     │            │
│  │  ───────────    │  │  ───────────    │  │  ───────────    │            │
│  │  tools:         │  │  tools:         │  │  tools:         │            │
│  │  • get_skill    │  │  • query_rule   │  │  • save_memory  │            │
│  │  • list_skills  │  │  • submit_rule  │  │  • recall       │            │
│  │                 │  │  • evolve_rule  │  │  • forget       │            │
│  │  resources:     │  │                 │  │                 │            │
│  │  • skill-catalog│  │  resources:     │  │  resources:     │            │
│  │                 │  │  • rule-set/*   │  │  • memories/*   │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │  Evolution MCP  │  │  Persona MCP    │  │  Sync MCP       │            │
│  │  ───────────    │  │  ───────────    │  │  ───────────    │            │
│  │  tools:         │  │  tools:         │  │  tools:         │            │
│  │  • analyze_use  │  │  • get_persona  │  │  • push_update  │            │
│  │  • propose_rule │  │  • set_tone     │  │  • sync_state   │            │
│  │  • auto_refine  │  │  • set_style    │  │  • notify_agent │            │
│  │                 │  │                 │  │                 │            │
│  │  自动进化引擎    │  │  人设/风格设定  │  │  增量同步推送    │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │  UI 语义 MCP    │  │  业务逻辑 MCP   │  │  API 规范 MCP   │  可扩展...  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     进化引擎 (Evolution Engine)                               │
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │                      进化闭环 (Evolution Loop)                      │    │
│   │                                                                    │    │
│   │   使用 ──→ 采集 ──→ 分析 ──→ 提炼 ──→ 验证 ──→ 推送 ──→ 生效        │    │
│   │    │                    │                              │          │    │
│   │    │    ┌───────────────┴───────────────┐              │          │    │
│   │    │    ▼                               ▼              │          │    │
│   │    │  规则进化 (Rule Evolution)      记忆进化 (Memory)   │          │    │
│   │    │  • 新规则生成                    • 上下文压缩      │          │    │
│   │    │  • 规则修正                      • 关键事件记录    │          │    │
│   │    │  • 规则合并/废弃                 • 偏好学习        │          │    │
│   │    │                                  • 项目知识沉淀    │          │    │
│   └───────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │                   实时推送系统 (Real-time Sync)                     │    │
│   │                                                                    │    │
│   │   进化完成 ──→ 版本快照 ──→ 增量推送 ──→ AI员工热更新              │    │
│   │                              │                                    │    │
│   │                              ▼                                    │    │
│   │                    ┌─────────────────┐                           │    │
│   │                    │ WebSocket / SSE │ ← 实时通知                 │    │
│   │                    │ MCP Resource    │ ← 资源变更通知             │    │
│   │                    │ CLI Hook        │ ← 命令行推送               │    │
│   │                    └─────────────────┘                           │    │
│   └───────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        数据存储层 (Knowledge Store)                           │
│                                                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│  │ 规则库      │ │ 记忆库      │ │ 使用日志    │ │ 向量索引    │             │
│  │ (YAML/JSON)│ │ (SQLite)   │ │ (时序DB)   │ │ (pgvector) │             │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘             │
└─────────────────────────────────────────────────────────────────────────────┘
```

说明：

- 上图中的“前端专家 / 后端专家 / 测试工程师 / 运维专家”仅用于说明可组合员工形态，不代表平台只支持这类固定行业角色。
- 在项目协作场景下，是否单人主责、是否需要多人协作以及如何拆分，应由 AI 结合项目手册、员工手册、规则和工具自主判断，而不是依赖固定分工模板。
- 若单个员工已能完成任务，应允许保持单人主责；多人协作只在确有必要时发生。

### 2.2 分层职责

| 层级 | 职责 | 关键能力 |
|------|------|----------|
| 用户界面层 | 用户与平台的交互入口 | 员工管理、技能市场、规则编辑、进化面板 |
| AI 员工编排层 | 员工创建、配置、路由 | 组合配置、运行时管理、负载均衡 |
| MCP 编排层 | MCP 请求路由、服务治理 | 意图识别 → MCP 路由、权限控制、版本管理 |
| MCP 服务层 | 领域能力的标准化封装 | Skills/Rules/Memory/Persona/Evolution/Sync |
| 进化引擎层 | 知识的自动学习与推送 | 使用分析、规则生成、增量同步、热更新 |
| 数据存储层 | 持久化存储与检索 | 多模态存储、向量检索、版本管理 |

补充说明：

- 这里的“编排”强调统一入口、上下文装配、权限与工具调度，不等于把协作关系写死成某种行业分工路由。
- 当平台暴露项目级协作入口时，编排层应优先支持“AI 自主判断单人或多人协作”的模式。

### 2.3 MCP 编排层设计

编排层是平台的中枢，负责将 AI 的工具调用请求路由到正确的 MCP 服务。

**核心组件：**

- **意图路由器 (Intent Router)**：解析 AI 的调用意图，匹配最相关的 MCP 服务。支持精确匹配（工具名）和模糊匹配（语义相似度）。
- **服务注册表 (Service Registry)**：所有 MCP 服务在此注册，声明自己的能力（tools/resources/prompts）。新服务上线即可被发现，无需重启编排层。
- **权限网关 (Auth Gateway)**：基于调用者身份（用户/团队/角色/AI员工）控制对 MCP 服务的访问粒度。
- **版本路由 (Version Router)**：同一 MCP 服务可存在多个版本，支持灰度发布和 A/B 测试。
- **可观测性 (Observability)**：记录每次调用的输入、输出、耗时、命中率，为进化引擎提供数据源。

### 2.4 数据流转

```
AI 员工接收用户请求
    │
    ▼
MCP 编排层解析意图 ──→ 意图路由
                         │
                    ┌────┴────┐
                    ▼         ▼
              精确匹配     语义匹配
             (工具名)    (向量相似度)
                    │         │
                    └────┬────┘
                         ▼
                  目标 MCP 服务
                         │
                    ┌────┴────┐
                    ▼         ▼
              知识检索     规则匹配
                    │         │
                    └────┬────┘
                         ▼
                  结构化结果返回 AI 员工
                         │
                         ▼
                  AI 员工整合上下文生成回答
                         │
                         ▼
                  用户确认/修正
                         │
                         ▼
                  进化引擎采集（隐式）
```

**关键数据流：**

- **查询流**：AI 员工 → 编排层 → MCP 服务 → 知识存储 → 结果返回
- **反馈流**：用户行为（采纳/拒绝/修改）→ 进化引擎 → 质量评估 → 知识更新
- **同步流**：知识变更 → 版本快照 → 增量推送 → AI 员工热更新

---

## 3. MCP 服务规范

### 3.1 服务设计规范

每个 MCP 服务是一个独立的能力单元，遵循统一的接口契约。

**服务结构：**

```
mcp-service-{name}/
├── manifest.json          # 服务声明：名称、版本、能力描述
├── tools/                 # 工具定义（AI 可调用的函数）
├── resources/             # 资源定义（AI 可读取的数据）
├── prompts/               # 提示词模板（预置的交互模式）
├── knowledge/             # 知识条目存储（可选）
└── feedback/              # 反馈收集配置（可选）
```

**manifest.json 示例：**

```json
{
  "name": "rules-engine",
  "version": "1.2.0",
  "description": "团队开发规则与经验知识库",
  "capabilities": {
    "tools": ["query_rule", "suggest_practice", "submit_rule", "evolve_rule"],
    "resources": ["rule-set/*", "rule-catalog"],
    "prompts": ["code-review-with-rules"]
  },
  "dependencies": [],
  "access": { "teams": ["*"], "roles": ["developer"] }
}
```

### 3.2 核心 MCP 服务

#### 3.2.1 Skills MCP (技能服务)

管理通过目录导入的技能代码包，支持 Python 和 Node.js 脚本执行。

**技能创建方式：**

```bash
# 方式一：导入本地目录
skill import ./skill-react-development/

# 方式二：上传 ZIP 包
skill upload skill-react-dev.zip

# 方式三：从 Git 导入
skill clone https://github.com/team/skill-react.git
```

**工具定义：**

```python
# 技能导入（非 MCP 方式，通过 CLI 或 API）
# POST /api/skills/import
import_skill(directory_path)        # 导入技能目录
upload_skill(skill_package)         # 上传技能包 (.zip)
clone_skill(git_url)                # 从 Git 克隆

# 技能管理（通过 MCP 或 API）
get_skill(skill_id, version)        # 获取技能详情
list_skills(tags, domain)           # 列出可用技能
delete_skill(skill_id)              # 删除技能

# 技能绑定
install_skill(employee_id, skill_id)    # 安装技能到员工
uninstall_skill(employee_id, skill_id)  # 卸载技能

# 技能执行（通过 MCP）
execute_tool(skill_id, tool_name, parameters)  # 执行技能工具
test_skill(skill_id)                          # 测试技能（沙箱环境）
```

**资源定义：**

```python
skill://catalog                       # 技能目录
skill://{skill_id}                    # 技能详情
skill://{skill_id}/tools              # 技能工具列表
skill://{skill_id}/resources          # 技能资源
skill://{skill_id}/versions           # 技能版本历史
```

**技能包结构：**

```
skill-{name}/
├── manifest.yaml           # 技能元数据
├── tools/                  # 工具脚本
│   ├── *.py               # Python 工具
│   └── *.js               # Node.js 工具
├── resources/              # 资源文件
├── prompts/                # 提示词模板
├── requirements.txt        # Python 依赖
├── package.json            # Node.js 依赖（可选）
└── README.md               # 技能文档
```

**技能执行环境：**

```yaml
# 沙箱配置
sandbox:
  enabled: true
  memory_limit: "256MB"
  cpu_limit: "0.5"
  timeout: 30s
  
  # 文件系统隔离
  filesystem:
    mode: "isolated"        # 隔离模式
    read_only_paths: []     # 只读路径
    write_paths: ["/tmp"]   # 可写路径
    
  # 网络隔离
  network:
    enabled: false          # 默认禁用网络
    allowed_hosts: []       # 允许的主机
    
  # 环境变量
  env_vars:
    allowed: []             # 允许的环境变量白名单
    injected:               # 注入的环境变量
      SKILL_ID: "{skill_id}"
      EMPLOYEE_ID: "{employee_id}"
```

**技能安全扫描：**

```yaml
security_scan:
  # 上传时扫描
  on_upload:
    - virus_scan: true
    - sensitive_code_detection: true
    - dependency_audit: true
    
  # 敏感代码检测规则
  sensitive_patterns:
    - "password\\s*="
    - "api_key\\s*="
    - "secret\\s*="
    - "eval\\("
    - "exec\\("
    - "subprocess\\.call"
    
  # 禁止的系统调用
  forbidden_syscalls:
    - "fork"
    - "execve"
    - "socket"
```

#### 3.2.2 Rules MCP (规则服务)

管理团队规则和最佳实践，支持自动进化。

```python
# Tools
query_rule(keyword, domain)           # 按关键词和领域检索规则
suggest_practice(context)             # 根据上下文推荐最佳实践
submit_rule(rule_data)                # 提交新规则候选
evolve_rule(rule_id, evolution_data)  # 进化规则

# Resources
rule://catalog                        # 规则目录
rule://{rule_id}                      # 规则详情
rule://domains                        # 规则领域列表
```

#### 3.2.3 Memory MCP (记忆服务)

管理 AI 员工的持久记忆。

```python
# Tools
save_memory(employee_id, content, type)  # 保存记忆
recall(employee_id, query, limit)        # 检索记忆
forget(memory_id)                        # 删除记忆
compress_memories(employee_id)           # 压缩记忆

# Resources
memory://{employee_id}/all               # 所有记忆
memory://{employee_id}/recent            # 最近记忆
memory://{employee_id}/important         # 重要记忆
```

#### 3.2.4 Persona MCP (人设服务)

管理 AI 员工的人设和风格。

```python
# Tools
get_persona(persona_id)              # 获取人设
set_tone(employee_id, tone)          # 设置语调
set_style(employee_id, hints)        # 设置风格

# Resources
persona://{persona_id}                # 人设详情
persona://templates                   # 人设模板库
```

##### 数字分身能力扩展

当前 Persona MCP 仅覆盖"表达风格"层面，不足以支撑"每个人设计自己的数字分身"这一核心理念。需补充以下能力：

**扩展工具接口：**

```python
# 身份建模
train_persona_from_corpus(user_id, corpus_refs, consent_token)  # 从用户历史语料学习个人模式（需授权）
set_decision_policy(persona_id, policy)                         # 设置决策策略（价值观/偏好权重/风险偏好）
set_delegation_scope(persona_id, allowed_actions, risk_level)   # 设置代理授权边界

# 身份连续性
get_persona_drift(persona_id, window_days)                      # 检测人格漂移（防止随使用偏离本人）
snapshot_persona(persona_id)                                    # 创建人设快照（版本化）
restore_persona(persona_id, snapshot_id)                        # 回滚到历史快照

# 对齐评测
evaluate_persona_alignment(persona_id, benchmark_id)            # 评估"与本人一致率"（语气/决策/纠错偏好）

# Resources
persona://{persona_id}/drift-report     # 漂移报告
persona://{persona_id}/snapshots        # 快照列表
persona://{persona_id}/alignment-score  # 对齐评分
```

**Memory-Persona 协同机制：**

Memory MCP 需增加"身份信号"类型记忆，与 Persona 联动：

| 记忆类型 | 用途 | 示例 |
|----------|------|------|
| `long-term-goal` | 长期目标 | "推动团队采用 TDD" |
| `taboo` | 禁忌/底线 | "绝不在未经 review 时直接合并" |
| `stable-preference` | 稳定偏好 | "偏好函数式风格，厌恶深层嵌套" |
| `decision-pattern` | 决策模式 | "面对性能 vs 可读性时优先可读性" |

**代理授权边界：**

数字分身代表用户执行任务时，需明确"可代决策"与"需升级审批"的边界：

```yaml
delegation:
  auto_approve:
    - "code_style_suggestion"
    - "test_case_generation"
  require_confirmation:
    - "merge_request_approval"
    - "architecture_decision"
  forbidden:
    - "production_deployment"
    - "access_permission_change"
  # 核心约束：代理权限不可超出委托人原权限
  principle: "delegation_cannot_escalate"
  enforce: true
```

##### 训练数据治理

```yaml
persona_training:
  # 同意与撤销
  consent:
    required: true
    revocable: true
    revoke_action: "purge_trained_data"

  # 语料来源校验
  corpus_validation:
    integrity_check: true
    malicious_content_scan: true
    allowed_sources: ["user_owned_repos", "approved_documents"]

  # 数据遗忘（Right to be Forgotten）
  unlearning:
    enabled: true
    method: "retrain_without_revoked_corpus"
    audit_trail: true
```

#### 3.2.5 Evolution MCP (进化服务)

管理知识的自动进化和推送。

```python
# Tools
analyze_usage_patterns(employee_id, days)  # 分析使用模式
propose_rule(pattern_id, employee_id)      # 提出新规则候选
auto_evolve(employee_id, threshold)        # 自动进化
review_candidate(candidate_id, action)     # 审核候选规则

# Resources
evolution://candidates/{employee_id}        # 候选规则队列
evolution://updates/{employee_id}           # 最近更新
evolution://report/{employee_id}            # 进化报告
```

#### 3.2.6 Sync MCP (同步服务)

管理实时推送和热更新。

```python
# Tools
push_update(update_type, target_id, employee_ids)  # 推送更新
sync_state(employee_id)                            # 同步完整状态
notify_agent(employee_id, message, level)          # 发送通知

# Resources
sync://status/{employee_id}                        # 同步状态
sync://events/{employee_id}                        # 最近事件
```

### 3.3 领域 MCP 服务 (可扩展)

| MCP 服务 | 领域 | 核心能力 | 数据来源 |
|----------|------|----------|----------|
| UI 语义 MCP | 设计系统 | 组件意图解释、布局决策溯源、设计规范校验 | 设计稿标注、组件文档、设计评审记录 |
| 业务逻辑 MCP | 业务领域 | 业务流程查询、领域模型解释、边界条件提示 | 产品文档、需求评审、业务规则库 |
| API 规范 MCP | 接口契约 | 接口规范校验、参数约束提示、版本兼容检查 | OpenAPI Spec、接口变更记录 |
| 测试策略 MCP | 质量保障 | 测试用例推荐、覆盖率分析、回归风险评估 | 历史测试数据、缺陷库、覆盖率报告 |

---

## 4. 进化引擎

### 4.1 核心机制

"越用越聪明"通过工程化的进化闭环实现：

```
使用 → 采集 → 分析 → 提炼 → 验证 → 推送 → 生效（循环）
```

每一环都有明确的输入、处理逻辑和输出。

### 4.2 采集层

采集分为隐式和显式两种方式，尽量减少对开发者的打扰。

**隐式采集（零干扰）：**

| 信号 | 含义 | 采集方式 |
|------|------|----------|
| AI 员工调用了某条规则 | 该规则与当前场景相关 | 编排层自动记录 |
| 用户采纳了 AI 建议 | 规则有效 | 检测代码变更是否与建议一致 |
| 用户忽略/拒绝建议 | 规则可能不适用或有误 | 记录未采纳事件 |
| 同一规则被多人频繁调用 | 高价值规则 | 聚合调用频次 |
| AI 回答后用户手动修改 | 规则可能需要修正 | Diff 对比 AI 建议 vs 最终代码 |

**显式采集（主动贡献）：**

- 用户通过 CLI 命令提交新规则：`mcp-rule add --domain "error-handling" --title "..."`
- Code Review 中标记的通用性问题，一键转为规则候选
- 线上事故复盘产出的经验，结构化录入

### 4.3 评估层

不是所有反馈都应该直接入库。评估层负责过滤噪声、量化知识质量。

**置信度模型：**

每条知识条目维护一个动态置信度分数（0.0 - 1.0），由以下因子加权计算：

```python
confidence = (
    0.35 * adoption_rate      # 采纳率（被采纳次数 / 被推荐次数）
  + 0.25 * cross_user_score   # 跨用户验证（多少不同用户采纳过）
  + 0.20 * recency_score      # 时效性（近期使用频率）
  + 0.20 * source_authority   # 来源权威度
)

# 来源权威度权重
SOURCE_AUTHORITY = {
    "incident-review": 1.0,    # 线上事故复盘
    "code-review": 0.8,        # Code Review 沉淀
    "team-consensus": 0.9,     # 团队共识
    "auto-evolved": 0.6,       # 自动进化生成
    "user-submit": 0.5,        # 用户提交
}
```

**生命周期管理：**

| 置信度区间 | 状态 | 行为 |
|-----------|------|------|
| 0.8 - 1.0 | **已验证 (Verified)** | 正常推荐，高优先级展示 |
| 0.5 - 0.8 | **活跃 (Active)** | 正常推荐，标注"团队经验" |
| 0.3 - 0.5 | **待验证 (Pending)** | 仅在高相关度时推荐，标注"待验证" |
| 0.0 - 0.3 | **衰退 (Decaying)** | 不主动推荐，进入归档候选队列 |

### 4.4 提炼层

提炼是进化引擎中最关键的一环——将原始反馈数据转化为可用的知识条目。

**自动提炼流程：**

```
原始反馈数据
    │
    ▼
聚合分析（同一场景下的多次反馈归并）
    │
    ▼
模式识别（AI 辅助发现重复出现的修正模式）
    │
    ▼
候选知识生成（自动草拟规则条目）
    │
    ▼
置信度评估（计算初始置信度）
    │
    ├─── confidence >= 0.8 ──→ 自动入库 → 推送到绑定员工
    │
    └─── confidence < 0.8 ──→ 进入候选队列 → 等待用户审核
```

**人工审核的必要性**：完全自动化入库风险过高。初期采用"AI 提炼 + 人工审核"模式，当系统成熟后可逐步提高自动入库的置信度阈值。

### 4.5 实时推送

进化完成后，通过多种渠道实时推送到 AI 员工：

```
进化完成
    │
    ▼
生成更新事件
    │
    ├─── WebSocket ──→ IDE 实时通知
    │
    ├─── MCP Resource ──→ 资源变更通知
    │
    └─── CLI Hook ──→ 命令行推送
    │
    ▼
AI 员工热更新
"已为你学习 1 条新规则，立即生效"
```

### 4.6 版本管理

知识需要像代码一样进行版本控制。

**版本策略：**

- 每条知识条目独立版本号（语义化版本：major.minor.patch）
- 修改规则内容 → minor 版本递增
- 修改规则适用范围/严重级别 → major 版本递增
- 修改示例/描述文字 → patch 版本递增

**变更审计：**

```yaml
rule_id: rule-001
changelog:
  - version: "1.2.0"
    date: "2025-03-15"
    author: "auto-evolved"
    change: "扩展适用范围至 GraphQL 错误响应"
    reason: "检测到 GraphQL 相关修正模式"
    confidence_delta: +0.05
  - version: "1.0.0"
    date: "2024-10-01"
    author: "user-001"
    change: "初始创建"
    reason: "Q3 线上事故复盘产出"
```

### 4.7 进化安全加固

> 本节定义威胁模型与防御原理；可执行参数配置见 7.4.4 节。

#### 4.7.1 已知攻击向量

当前 `auto_promote(threshold=0.8, max_per_day=5, require_cross_user=3)` 对普通噪声有效，但对主动对抗场景存在以下风险：

| 攻击向量 | 描述 | 利用方式 |
|----------|------|----------|
| Sybil/串谋投票 | 3 个"不同用户"不等于独立可信用户 | 小号/机器人协同刷高 `cross_user_score` |
| 采纳率操纵 | 低风险场景反复触发建议 | 制造虚高 `adoption_rate`，推进低质量规则入库 |
| 慢速投毒 | `cooldown_hours: 24` 仅抑制短周期重复 | 低频长期投毒（slow poisoning）绕过冷却期 |
| 语义泛化投毒 | 构造"看似正确但过度泛化"的规则 | 短期通过验证、长期造成系统性错误 |
| 来源权威漂白 | 先推动候选进入"自动进化来源" | 利用迭代提权获得更高可信外观 |

#### 4.7.2 回滚机制增强

当前回滚机制的不足：

- `confidence_below: 0.3 after_days: 7` 对灾难性错误响应过慢（7天窗口）
- `rejection_rate_above: 0.7, min_samples: 10` 在低流量场景下触发滞后
- 未定义全局紧急刹车（kill switch），无法分钟级冻结自动入库与扩散
- 未定义因果回滚范围（衍生规则、受污染记忆、已推送事件链）

**加固措施：**

```yaml
rollback_hardening:
  # 紧急冻结开关
  emergency_kill_switch:
    enabled: true
    action: "freeze_auto_promote_and_unbind_latest_batch"
    trigger: ["manual", "critical_incident", "anomaly_spike"]

  # 因果回滚（联动清理污染链路）
  causal_rollback:
    include_derived_rules: true
    include_memory_writes: true
    include_sync_events: true

  # 分级扩散控制
  blast_radius_guard:
    staged_rollout: [1, 5, 25, 100]
    auto_halt_on:
      - "critical_incident"
      - "p95_latency_spike"
      - "rejection_rate_spike"
```

#### 4.7.3 信任加权验证

替代纯计数的跨用户验证，引入信任加权模型：

```python
trust_score = weighted_sum(
    account_age_factor,        # 账号年龄
    historical_quality_factor, # 历史贡献质量
    team_diversity_factor,     # 团队分布多样性
    device_fingerprint_factor  # 设备指纹独立性
)

# 跨用户验证升级为：
require_cross_user:
  min_users: 3
  min_trust_score: 2.4        # 信任分加权总和
  distinct_teams: 2           # 至少来自 2 个不同团队
```

#### 4.7.4 风险域分级

安全/合规/财务相关规则默认禁止自动入库：

```yaml
threshold_by_risk:
  low: 0.85                   # 代码风格、命名规范等
  medium: 0.90                # 架构模式、性能优化等
  high: "manual_only"         # 安全、合规、财务相关
```

---

## 5. 落地路径

### 5.1 总体策略

采用"基础设施先行 → AI 员工平台 → 智能化增强"的渐进式路径。

### 5.2 阶段规划

#### Phase 0：基础设施（第 1-2 周）

**目标**：搭建最小可用的 MCP 运行环境。

- MCP Server 框架：**Python FastMCP**（已确定）
- 搭建单机版编排层（初期无需分布式，单进程路由即可）
- 部署基础存储（SQLite + 本地文件，后续可迁移）
- 配置 IDE 端 MCP Client 连接

**交付物**：一个能被 AI IDE 调用的空壳 MCP 服务。

#### Phase 1：核心 MCP 服务（第 3-5 周）

**目标**：实现 Skills、Rules、Memory 三大核心 MCP 服务。

**Skills MCP：**
- 技能定义和版本管理
- 技能加载和工具调用路由
- 基础技能库（前端、后端、测试等）

**Rules MCP：**
- 支持手动录入规则条目（结构化 JSON/YAML）
- 提供 `query_rule` 工具：AI 可按关键词/场景查询相关规则
- 提供 `suggest_practice` 工具：根据代码上下文推荐最佳实践
- 基础反馈采集：记录 AI 调用了哪条规则、用户是否采纳

**Memory MCP：**
- 记忆存储（SQLite）
- 基础检索功能
- 记忆过期管理

**交付物**：三大核心 MCP 服务可用，支持 AI 员工基础能力。

#### Phase 2：AI 员工平台（第 6-8 周）

**目标**：实现 AI 员工编排层和用户界面。

**AI 员工编排层：**
- AI 员工 CRUD API
- 员工配置存储（YAML/JSON）
- MCP 资源动态绑定
- 多员工并行运行

**用户界面：**
- AI 员工管理界面
- 技能市场
- 规则工作台

**Persona MCP：**
- 人设模板库
- 风格配置生效
- 决策策略与代理授权边界
- 身份连续性（快照、漂移检测）
- 授权式语料训练管道
- 对齐评测基线

**交付物**：完整的 AI 员工创建和使用平台，含数字分身核心能力。

#### Phase 3：进化引擎（第 9-12 周）

**目标**：实现知识自动学习和进化。

**Evolution MCP：**
- 使用数据采集
- 模式分析器
- 规则自动生成
- 进化决策系统

**Sync MCP：**
- 推送 API
- 同步状态管理
- WebSocket 通知
- 热更新机制

**交付物**：可自动学习新规则的进化引擎。

#### Phase 4：规模化扩展（第 13 周+）

**目标**：横向扩展 MCP 服务和平台能力。

- 按需扩展：UI 语义 MCP、业务逻辑 MCP、API 规范 MCP、测试策略 MCP
- 编排层分布式部署（多实例 + 服务发现）
- 知识存储迁移至生产级方案（PostgreSQL + pgvector / Qdrant）
- 跨员工知识共享
- 规则冲突检测
- 技能市场开放

### 5.3 优先级矩阵

| 能力 | 价值 | 复杂度 | 优先级 | 所属阶段 |
|------|------|--------|--------|----------|
| Skills MCP | 高 | 中 | P0 | Phase 1 |
| Rules MCP | 高 | 低 | P0 | Phase 1 |
| Memory MCP | 高 | 中 | P0 | Phase 1 |
| AI 员工编排 | 高 | 中 | P0 | Phase 2 |
| 用户界面 | 高 | 中 | P1 | Phase 2 |
| Persona MCP | 中 | 低 | P1 | Phase 2 |
| 进化引擎 | 高 | 高 | P1 | Phase 3 |
| 实时推送 | 高 | 中 | P1 | Phase 3 |
| 领域 MCP 扩展 | 中 | 中 | P2 | Phase 4 |
| 分布式部署 | 中 | 高 | P3 | Phase 4 |

### 5.4 MVP 验收标准

Phase 2 完成时，以下场景必须可用：

1. 用户可以通过界面创建 AI 员工，选择技能、规则集、记忆配置、人设
2. AI 员工能够根据配置加载对应的 MCP 服务能力
3. 用户可以管理多个 AI 员工，支持创建、编辑、删除、复制
4. AI 员工能够持久化记忆，跨会话保持上下文

Phase 3 完成时，以下场景必须可用：

1. AI 员工的使用行为被自动采集和分析
2. 系统能够自动生成规则候选并推送审核
3. 高置信度规则能够自动入库并推送到 AI 员工
4. 规则更新能够实时推送到 AI 员工并热更新生效

---

## 6. 团队协作

### 6.1 角色定义

| 角色 | 职责 | 人数建议 |
|------|------|----------|
| 平台负责人 | 整体架构决策、优先级排序、跨团队协调 | 1 |
| 知识管理员 | 审核知识条目、维护知识质量、处理冲突 | 1-2 / 每个 MCP |
| MCP 开发者 | 开发和维护 MCP 服务代码 | 2-3 |
| 知识贡献者 | 提交规则、反馈问题（全体用户兼任） | 不限 |

### 6.2 权限模型

采用三层权限体系：团队 → 角色 → 个人。

**权限矩阵：**

| 操作 | 知识贡献者 | 知识管理员 | MCP 开发者 | 平台负责人 |
|------|-----------|-----------|-----------|-----------|
| 查询知识 | ✅ | ✅ | ✅ | ✅ |
| 提交规则候选 | ✅ | ✅ | ✅ | ✅ |
| 审核/入库规则 | ❌ | ✅ | ❌ | ✅ |
| 修改规则内容 | ❌ | ✅ | ❌ | ✅ |
| 删除/归档规则 | ❌ | ❌ | ❌ | ✅ |
| 创建 AI 员工 | ✅ | ✅ | ✅ | ✅ |
| 管理 AI 员工 | ✅ (自己创建的) | ✅ | ✅ | ✅ |
| 部署 MCP 服务 | ❌ | ❌ | ✅ | ✅ |
| 修改编排层配置 | ❌ | ❌ | ❌ | ✅ |

**团队隔离**：不同团队的 MCP 知识库默认隔离，可通过"共享规则"机制将高价值规则发布到全局空间。

### 6.3 知识共享与冲突处理

**共享机制：**

```
团队私有规则 ──(知识管理员提名)──→ 共享候选队列
                                      │
                              平台负责人审核
                                      │
                                      ▼
                              全局共享规则库
                                      │
                              所有团队可见可用
```

**冲突处理：**

| 冲突类型 | 处理策略 |
|----------|----------|
| 同团队内规则矛盾 | 知识管理员裁决，合并或废弃其一 |
| 跨团队规则矛盾 | 平台负责人协调，可保留为"团队特定规则"共存 |
| 新规则与已验证规则矛盾 | 新规则进入待验证状态，附带矛盾标记，需额外证据支撑 |
| 全局规则与团队规则矛盾 | 团队规则优先级更高（就近原则），但需标注偏差原因 |

### 6.4 协作流程

**日常使用流程（知识贡献者）：**

1. 使用 AI 员工开发，MCP 在后台自动提供上下文
2. 发现 AI 给出的建议不准确 → 修正后继续开发（隐式反馈自动采集）
3. 发现值得沉淀的经验 → 通过 CLI 提交规则候选
4. 收到知识管理员的审核反馈 → 补充/修正后重新提交

**知识管理员周期性工作：**

1. 每日：审核新提交的规则候选（目标 24h 内响应）
2. 每周：查看进化报告，处理低置信度规则
3. 每月：清理衰退规则，提名高价值规则至全局共享

### 6.5 度量指标

平台健康度通过以下指标衡量：

**使用指标：**

| 指标 | 计算方式 | 健康阈值 |
|------|----------|----------|
| 日活跃用户数 (DAU) | 当日使用 AI 员工的独立用户数 | 团队人数的 60%+ |
| 规则命中率 | 有效命中次数 / 总查询次数 | > 40% |
| 建议采纳率 | 用户采纳次数 / AI 推荐次数 | > 50% |
| 平均响应时间 | MCP 查询到返回结果的耗时 | < 500ms |

**知识质量指标：**

| 指标 | 计算方式 | 健康阈值 |
|------|----------|----------|
| 已验证规则占比 | 置信度 ≥ 0.8 的规则数 / 总规则数 | > 30% |
| 知识增长率 | 本月新增有效规则数 | 持续正增长 |
| 衰退规则占比 | 置信度 < 0.3 的规则数 / 总规则数 | < 15% |
| 跨团队共享率 | 全局共享规则数 / 总规则数 | > 10% |

**进化指标：**

| 指标 | 计算方式 | 健康阈值 |
|------|----------|----------|
| 自动进化成功率 | 自动入库规则数 / 候选规则数 | > 60% |
| 进化规则采纳率 | 进化生成的规则被采纳率 | > 50% |
| 规则更新周期 | 规则从候选到入库的平均时间 | < 7 天 |

---

## 7. 安全设计

### 7.1 权限模型增强

#### 7.1.1 资源级别权限控制

在基础角色权限之上，增加资源级别的细粒度控制：

```yaml
# 权限配置示例
permissions:
  rules:
    read:
      - "*"                    # 所有人可读
    write:
      - "admin"
      - "knowledge-manager"
    delete:
      - "admin"
      
  employees:
    create:
      - "*"                    # 所有人可创建
    read:
      - "owner"                # 创建者
      - "admin"
      - "team-member"          # 团队成员（只读）
    update:
      - "owner"
      - "admin"
    delete:
      - "owner"
      - "admin"
      
  memories:
    read:
      - "owner"                # 只有创建者可读
      - "admin"
    write:
      - "owner"
    delete:
      - "owner"
      - "admin"
```

#### 7.1.2 敏感操作二次确认

```yaml
sensitive_operations:
  - operation: "delete_rule"
    require_confirmation: true
    notify_admin: true
    
  - operation: "merge_rules"
    require_confirmation: true
    require_reviewer: "knowledge-manager"
    
  - operation: "auto_evolve_promote"
    require_confirmation: false
    notify_stakeholders: true
    log_level: "critical"

  - operation: "set_delegation_scope"
    require_confirmation: true
    notify_admin: true

  - operation: "restore_persona"
    require_confirmation: true
    notify_admin: false

  - operation: "train_persona_from_corpus"
    require_confirmation: true
    require_reviewer: "owner"
    notify_admin: true
```

### 7.2 数据保护

#### 7.2.1 敏感数据检测与脱敏

```yaml
data_protection:
  # 敏感字段检测
  sensitive_fields:
    - "password"
    - "api_key"
    - "token"
    - "secret"
    - "credential"
    - "private_key"
    
  # 自动脱敏
  redaction:
    enabled: true
    patterns:
      - pattern: "password\\s*[=:]\\s*['\"][^'\"]+['\"]"
        replace: "password=***REDACTED***"
      - pattern: "api_key\\s*[=:]\\s*['\"][a-zA-Z0-9]+['\"]"
        replace: "api_key=***REDACTED***"
      - pattern: "token\\s*[=:]\\s*['\"][a-zA-Z0-9_-]+['\"]"
        replace: "token=***REDACTED***"
        
  # 敏感数据警告
  warning:
    on_detect: true
    message: "检测到可能的敏感信息，已自动脱敏"
```

#### 7.2.2 数据加密

```yaml
encryption:
  # 静态加密
  at_rest:
    enabled: true
    algorithm: "AES-256-GCM"
    key_rotation: "90d"
    
  # 传输加密
  in_transit:
    enabled: true
    tls_version: "1.3"
    certificate_validation: true
    
  # 字段级加密
  field_level:
    - field: "memory.content"
      encrypt: true
    - field: "persona.style_hints"
      encrypt: false
    - field: "persona.decision_policy"
      encrypt: true
    - field: "persona.delegation_scope"
      encrypt: true
    - field: "persona.drift_report"
      encrypt: true
    - field: "persona.training_corpus_refs"
      encrypt: true
```

### 7.3 输入验证

#### 7.3.1 规则输入验证

```yaml
validation:
  rule:
    # 字段长度限制
    title:
      min_length: 5
      max_length: 100
      
    content:
      min_length: 10
      max_length: 5000
      sanitize: true           # 清理 HTML/脚本
      
    examples:
      max_count: 5
      good:
        max_length: 500
      bad:
        max_length: 500
        
    # 结构验证
    severity:
      allowed_values: ["required", "recommended", "optional"]
      
    domain:
      pattern: "^[a-z0-9-]+$"
      max_length: 50
```

#### 7.3.2 记忆输入验证

```yaml
validation:
  memory:
    content:
      max_length: 10000
      sanitize: true
      
    type:
      allowed_values: ["project-context", "user-preference", "key-event", "learned-pattern"]
      
    # 单员工记忆数量限制
    max_entries_per_employee: 1000
    
    # 存储配额
    storage_quota:
      per_employee: "10MB"
      per_team: "1GB"
```

#### 7.3.3 注入防护

```yaml
injection_protection:
  # SQL 注入防护
  sql_injection:
    enabled: true
    use_parameterized_queries: true
    
  # XSS 防护
  xss:
    enabled: true
    sanitize_html: true
    allowed_tags: []           # 不允许任何 HTML 标签
    
  # JSON 注入防护
  json_injection:
    enabled: true
    max_depth: 5
    max_array_length: 100
```

### 7.4 进化引擎安全

#### 7.4.1 自动入库限制

```yaml
evolution_security:
  # 自动入库限制
  auto_promote:
    enabled: true
    threshold: 0.8             # 基础阈值；风险分级阈值见 7.4.4
    max_per_day: 5             # 每天最多自动入库 5 条
    require_cross_user: 3      # 基础配置；加固版见 7.4.4 信任加权验证
    cooldown_hours: 24         # 相似规则入库冷却期
    
  # 防刷票机制
  anti_gaming:
    # 同一用户不能重复投票
    prevent_duplicate_votes: true
    # 异常行为检测
    anomaly_detection:
      enabled: true
      threshold: "10 votes in 1 hour"
      action: "flag_for_review"
```

#### 7.4.2 回滚机制

```yaml
rollback:
  enabled: true
  
  # 自动回滚条件
  auto_rollback:
    enabled: true
    conditions:
      - confidence_below: 0.3
        after_days: 7
      - rejection_rate_above: 0.7
        min_samples: 10
        
  # 手动回滚
  manual_rollback:
    allowed_roles: ["admin", "knowledge-manager"]
    require_reason: true
    
  # 回滚通知
  notification:
    on_auto_rollback: true
    recipients: ["rule_author", "bound_employees"]
```

#### 7.4.3 风险控制

```yaml
risk_control:
  # 规则影响范围评估
  impact_assessment:
    enabled: true
    high_impact_threshold: 10  # 绑定 10+ 员工视为高风险
    action: "require_manual_review"
    
  # 规则冲突检测
  conflict_detection:
    enabled: true
    similarity_threshold: 0.9
    action: "flag_for_review"
    
  # 灰度发布
  canary_release:
    enabled: true
    initial_employees: 2
    observation_period: "24h"
    success_threshold: 0.8
```

#### 7.4.4 进化安全加固参数

基于 4.7 节识别的攻击向量，以下为安全加固配置：

```yaml
evolution_security_hardening:
  # 按风险域分级自动入库阈值
  auto_promote:
    threshold_by_risk:
      low: 0.85
      medium: 0.90
      high: "manual_only"
    max_per_day_by_domain:
      normal: 5
      security_critical: 0
```

```yaml
  # 信任加权跨用户验证（替代纯计数）
  require_cross_user:
    min_users: 3
    min_trust_score: 2.4
    distinct_teams: 2
    trust_signals:
      - "account_age"
      - "device_fingerprint"
      - "team_diversity"
      - "historical_quality"
```

```yaml
  # Sybil 抵抗
  anti_gaming:
    sybil_resistance:
      enabled: true
      signals: ["account_age", "device_fingerprint", "team_diversity", "historical_quality"]
    slow_poisoning_detection:
      enabled: true
      window_days: 30
      anomaly_threshold: 2.5  # 标准差倍数
```

```yaml
  # 紧急冻结与因果回滚
  rollback:
    emergency_kill_switch:
      enabled: true
      action: "freeze_auto_promote_and_unbind_latest_batch"
    causal_rollback:
      include_derived_rules: true
      include_memory_writes: true
      include_sync_events: true
    blast_radius_guard:
      staged_rollout: [1, 5, 25, 100]
      auto_halt_on:
        - "critical_incident"
        - "p95_latency_spike"
        - "rejection_rate_spike"
    # 回滚振荡冷却（防止 promote/rollback 反复抖动）
    oscillation_guard:
      max_cycles: 2
      cooldown_hours: 72
      action: "lock_rule_and_escalate_to_admin"
```

### 7.5 MCP 调用安全

#### 7.5.1 服务验证

```yaml
mcp_security:
  # 服务注册验证
  service_registration:
    require_signature: true
    allowed_publishers: ["trusted-team"]
    
  # 服务调用验证
  service_invocation:
    verify_signature: true
    timeout: 30s
    
  # 服务白名单
  allowed_services:
    mode: "whitelist"          # 白名单模式
    services:
      - "skills"
      - "rules"
      - "memory"
      - "persona"
      - "evolution"
      - "sync"
```

#### 7.5.2 调用频率限制

```yaml
rate_limiting:
  # 全局限制
  global:
    requests_per_minute: 1000
    burst: 100
    
  # 单员工限制
  per_employee:
    requests_per_minute: 100
    burst: 20
    
  # 单工具限制
  per_tool:
    requests_per_minute: 50
    burst: 10
    
  # 超限处理
  on_exceed:
    action: "throttle"
    retry_after: 60
    notify: true
```

#### 7.5.3 调用审计

```yaml
audit:
  enabled: true
  
  # 记录级别
  log_level: "info"            # debug / info / warning / error
  
  # 记录内容
  log_content:
    - caller_id
    - employee_id
    - tool_name
    - parameters               # 脱敏后
    - response_status
    - duration
    - timestamp
    
  # 敏感操作记录
  sensitive_operations:
    log_level: "warning"
    include_parameters: false  # 不记录敏感参数
    notify_admin: true
```

### 7.6 系统韧性

#### 7.6.1 故障降级

```yaml
resilience:
  # 编排层高可用
  orchestrator:
    replicas: 3
    health_check_interval: 30s
    failover_timeout: 10s
    
  # 进化引擎降级
  evolution_engine:
    fallback_mode: "manual_review"    # 引擎故障时回退人工审核
    health_check_interval: 60s
    
  # MCP 服务熔断
  circuit_breaker:
    failure_threshold: 5
    success_threshold: 2
    timeout: 60s
    half_open_requests: 3
```

#### 7.6.2 数据一致性

```yaml
consistency:
  # 规则更新一致性
  rule_update:
    strategy: "eventual"       # 最终一致性
    sync_timeout: 30s
    retry_attempts: 3
    retry_backoff: "exponential"
    
  # 记忆压缩安全
  memory_compression:
    keep_important: true       # 保留重要记忆
    archive_deleted: true      # 归档而非删除
    retention_period: "30d"    # 归档保留 30 天
```

#### 7.6.3 错误处理

```yaml
error_handling:
  # MCP 调用失败
  mcp_failure:
    retry: 3
    backoff: [1s, 2s, 4s]
    fallback: "cached_response"
    
  # 进化分析失败
  evolution_failure:
    notify_admin: true
    queue_for_manual_review: true
    log_level: "error"
    
  # 推送失败
  push_failure:
    retry: 5
    backoff: "exponential"
    dead_letter_queue: true
    alert_threshold: 10        # 连续失败 10 次告警
```

### 7.7 安全事件响应

#### 7.7.1 安全告警

```yaml
security_alerts:
  # 告警触发条件
  triggers:
    - type: "suspicious_activity"
      conditions:
        - "multiple_failed_auth_attempts > 5"
        - "unusual_access_pattern"
      severity: "high"
      
    - type: "data_exfiltration"
      conditions:
        - "large_data_export"
        - "unusual_memory_access"
      severity: "critical"
      
    - type: "injection_attempt"
      conditions:
        - "sql_injection_detected"
        - "xss_attempt_detected"
      severity: "high"
```

#### 7.7.2 响应流程

```yaml
incident_response:
  # 自动响应
  auto_response:
    - trigger: "injection_attempt"
      actions:
        - "block_request"
        - "log_incident"
        - "notify_security_team"
        
    - trigger: "excessive_requests"
      actions:
        - "throttle_user"
        - "notify_admin"
        
  # 手动响应
  manual_response:
    roles: ["admin", "security-team"]
    actions:
      - "lock_account"
      - "revoke_tokens"
      - "rollback_changes"
      - "export_audit_logs"
```

### 7.8 安全检查清单

#### 7.8.1 部署前检查

```yaml
pre_deployment_checklist:
  - "所有 API 端点已启用认证"
  - "敏感数据已加密存储"
  - "输入验证规则已配置"
  - "频率限制已启用"
  - "审计日志已开启"
  - "敏感操作需要二次确认"
  - "服务白名单已配置"
  - "故障降级策略已测试"
```

#### 7.8.2 定期安全审计

```yaml
security_audit:
  frequency: "monthly"
  
  checklist:
    - "审查权限矩阵是否合理"
    - "检查敏感数据访问日志"
    - "验证加密密钥轮换"
    - "测试故障恢复流程"
    - "审查进化引擎自动入库记录"
    - "检查异常行为告警"
    - "更新安全规则库"
```

### 7.9 AI 原生威胁模型

传统 Web 安全（SQL 注入/XSS/CSRF）已在 7.3 节覆盖。本节聚焦 AI-Native 平台特有的威胁面。

#### 7.9.1 规则注入（Prompt Injection via Rules）

**威胁描述**：恶意用户通过提交规则，在规则文本中嵌入越权指令，操纵 AI 员工行为。

**当前覆盖**：7.3 仅覆盖 SQL/XSS/JSON 注入，未覆盖"指令与数据隔离"。

```yaml
rule_injection_protection:
  # 规则内容 DSL 白名单（禁止自由文本指令）
  content_policy:
    mode: "structured_only"
    allowed_elements:
      - "code_pattern"
      - "description"
      - "example"
      - "severity"
    forbidden_patterns:
      - "ignore previous"
      - "system prompt"
      - "you are now"
      - "disregard"

  # LLM 防注入分类器（规则入库前扫描）
  injection_classifier:
    enabled: true
    model: "lightweight-classifier"
    threshold: 0.7
    action: "quarantine_and_flag"

  # 执行前策略裁决
  policy_as_code:
    enabled: true
    engine: "OPA"
    evaluate_before_apply: true
```

#### 7.9.2 MCP 供应链攻击

**威胁描述**：恶意 MCP 服务注册到平台，窃取数据或注入恶意行为。

**当前覆盖**：7.5 有签名与发布者白名单，但缺少完整性验证链。

```yaml
mcp_supply_chain:
  # 可验证构建来源
  provenance:
    require_slsa_level: 2
    require_sbom: true
    format: "SPDX"

  # 工件完整性
  integrity:
    require_digest_pin: true
    algorithm: "SHA-256"
    verify_on_load: true

  # 证书与版本管理
  certificate:
    revocation_check: true
    crl_refresh_interval: "1h"
  version_ban:
    enabled: true
    ban_list_source: "platform_security_team"
```

#### 7.9.3 进化数据投毒

**威胁描述**：协同用户通过操纵反馈数据，将恶意或低质量规则推入知识库。

**当前覆盖**：7.4 有阈值和防刷票，但缺少统计异常检测。

```yaml
data_poisoning_defense:
  # 鲁棒统计检测
  anomaly_detection:
    enabled: true
    method: "robust_z_score"
    window: "30d"
    threshold: 2.5

  # 异常簇隔离
  cluster_isolation:
    enabled: true
    action: "quarantine_cluster"
    notify: "security_team"

  # 低信任来源降权
  source_downgrade:
    trigger: "anomaly_detected"
    action: "reduce_authority_weight_by_50%"
    duration: "30d"
```

#### 7.9.4 记忆外流（Memory Exfiltration）

**威胁描述**：通过精心构造的查询，诱导 AI 员工泄露其他用户的记忆数据。

**当前覆盖**：7.2 有脱敏和告警，但缺少按密级的检索控制与出站 DLP。

```yaml
memory_exfiltration_defense:
  # 属性级访问控制（ABAC）
  access_control:
    model: "ABAC"
    attributes:
      - "classification_level"
      - "data_purpose"
      - "requester_identity"

  # 出站 DLP
  data_loss_prevention:
    enabled: true
    scan_responses: true
    block_on:
      - "cross_employee_memory_reference"
      - "bulk_memory_export"
      - "sensitive_field_in_response"

  # 响应级水印
  watermark:
    enabled: true
    method: "steganographic_token"
    trace_on_leak: true
```

#### 7.9.5 跨员工污染

**威胁描述**：进化引擎将坏模式从一个员工传播到其他员工。

**当前覆盖**：6.2/6.3 有团队隔离与共享规则，但缺少检索平面硬隔离。

```yaml
cross_employee_isolation:
  # 租户级索引隔离
  index_isolation:
    mode: "tenant_per_employee"
    shared_index: "global_verified_only"

  # 跨员工传播审批
  propagation_control:
    require_approval: true
    approver: "knowledge_manager"
    max_propagation_depth: 2

  # 污染批次追踪
  contamination_tracking:
    enabled: true
    trace_origin: true
    one_click_isolate: true
```

#### 7.9.6 工具链越权

**威胁描述**：通过多跳 MCP 调用链，绕过单工具权限检查实现权限提升。

```yaml
tool_chain_security:
  # 调用图级权限验证
  call_graph_validation:
    enabled: true
    max_chain_depth: 5
    verify_least_privilege: true

  # 会话级能力令牌
  capability_token:
    enabled: true
    scope: "session"
    attenuate_on_delegation: true

  # 敏感链路强制人工确认
  sensitive_chain_detection:
    patterns:
      - "memory_read -> sync_push"
      - "rule_evolve -> auto_promote -> push_update"
    action: "require_human_confirmation"
```

#### 7.9.7 优先级与实施建议

| 优先级 | 威胁面 | 建议时间线 |
|--------|--------|-----------|
| P0 | 规则注入防护 | Phase 1 同步实施 |
| P0 | MCP 供应链完整性 | Phase 0 基础设施阶段 |
| P0 | 紧急冻结 + 因果回滚 | Phase 3 进化引擎同步 |
| P1 | 数据投毒检测 | Phase 3 |
| P1 | 记忆出站 DLP | Phase 2 |
| P1 | 跨员工污染隔离 | Phase 2 |
| P2 | 工具链越权防护 | Phase 4 |
| P2 | 持续红队演练 | Phase 4+ 常态化 |

---

## 附录

### A. 技术栈建议

```
后端框架: Python FastAPI + FastMCP
数据库: PostgreSQL + pgvector (向量检索)
缓存: Redis (会话/配置缓存)
消息队列: Redis Streams (事件通知)
实时通信: WebSocket + SSE
存储: 
  - 规则: YAML/JSON 文件 + Git 版本控制
  - 记忆: SQLite / PostgreSQL
  - 日志: TimescaleDB (时序数据)
前端: React + TypeScript
部署: Docker + Kubernetes
```

### B. 相关文档

- [AI 员工工厂设计规范](../20-产品应用设计/AI-员工工厂设计规范.md) - 完整的 AI 员工平台设计
- [mcp-rules-engine](./mcp-rules-engine/) - 规则 MCP 服务实现
