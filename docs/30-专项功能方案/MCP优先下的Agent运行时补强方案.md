# MCP 优先下的 Agent 运行时补强方案

> 日期：2026-04-13
> 适用范围：当前项目 `ai-employee`
> 目标：在保持 `MCP-first, Chat-second` 定位不变的前提下，把当前项目中的 Agent 能力从“有用”升级为“强内核、可复用、可扩展、前端可感知”

## 1. 结论先行

当前项目最强的不是 AI 对话框，而是：

- 项目级 MCP 入口
- 统一查询 MCP 入口
- 项目/员工/规则/记忆/任务树/工作轨迹的治理闭环

当前项目最弱的不是“没有 Agent”，而是 Agent 运行时仍然偏分散，而且任务树稳定性还不够强。

具体来说：

- 平台层已经很强
- 运行时内核还不够统一
- 任务树已经能跑，但还没有形成“生成更稳、反馈更显、异常可回溯、自进化可沉淀”的工程结构
- 前端已经能看到任务树，但还不能稳定看到“为什么错、为什么卡住、下一步该怎么修”

因此后续升级方向不应是“重做聊天 UI”，也不应是“模仿一个新的 CLI 壳”，而应是：

> 在 MCP 主入口不变的前提下，先补任务树稳定层、前端反馈面、自进化闭环，再补统一运行时、Prompt 装配、Provider 解析、Tool Registry 四层。

## 2. 当前定位与约束

当前项目已经明确采用：

- `MCP-first`
- `Chat-second`

含义如下：

- 主入口是 `项目 MCP` 与 `统一查询 MCP`
- `web-admin` 的 AI 对话框是辅助入口
- 新功能默认先判断是否能沉淀为 MCP 工具、资源、提示词、任务树上下文或工作轨迹能力
- 页面交互可以先做验证，但不应反向定义平台主能力边界

这意味着后续 Agent 运行时升级也必须服从这个定位：

- 不做另一个独立 Agent 产品壳
- 不优先做聊天页体验升级
- 优先做 MCP 调用面背后的运行时收口
- 任务树不是聊天页附属装饰，而是主执行链的一部分
- 前端反馈不是锦上添花，而是任务树治理闭环的一部分

## 3. 当前代码里的运行时现状

当前项目已经具备 Agent 运行时雏形，但职责散在多处。

### 3.1 已有基础

- [`web-admin/api/routers/projects.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/routers/projects.py)
  - 项目聊天入口
  - 项目消息装配
  - 项目 chat settings 读取
  - 任务树读写路由
- [`web-admin/api/services/agent_orchestrator.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/agent_orchestrator.py)
  - 模型循环执行
  - tool call 结果回流
  - 结果封装与任务树审计
- [`web-admin/api/services/conversation_manager.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/conversation_manager.py)
  - Redis 会话
  - 消息缓存
  - 简单历史压缩
- [`web-admin/api/services/tool_executor.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/tool_executor.py)
  - 工具调用执行
  - 本地连接器工具转发
  - 项目工具运行时调用
- [`web-admin/api/services/dynamic_mcp_runtime.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/dynamic_mcp_runtime.py)
  - 项目工具 / 员工工具 / 外部 MCP 工具运行时代理
  - 项目协作编排
  - 任务树上下文绑定
- [`web-admin/api/services/project_chat_task_tree.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/project_chat_task_tree.py)
  - 任务树创建、推进、归档、校验、事件回填
- [`web-admin/frontend/src/views/projects/ProjectChat.vue`](/Volumes/苹果1_5T/self/ai-employee/web-admin/frontend/src/views/projects/ProjectChat.vue)
  - 聊天页内联 `taskTreeAudit`
  - 任务树抽屉
  - 节点状态手动编辑
- [`web-admin/frontend/src/views/projects/ProjectDetail.vue`](/Volumes/苹果1_5T/self/ai-employee/web-admin/frontend/src/views/projects/ProjectDetail.vue)
  - round 级任务树回看
  - 轨迹与记忆关联展示

### 3.2 当前主要问题

#### 问题 1：统一运行时上下文没有真正收口

当前一次执行需要的上下文分散在：

- 路由层参数
- 项目 chat settings
- task tree prompt
- employee coordination mode
- workspace_path
- tool list
- local connector 配置
- 历史消息

这些信息虽然都能取到，但没有统一 `RuntimeContext`。

结果：

- 项目聊天、统一查询、协作执行、外部工具代理会各自拼一部分上下文
- 后续要增强执行链时，很容易多处同时改

#### 问题 2：Prompt 装配还没有成为独立层

当前项目消息构造主要集中在 `projects.py` 中的消息组装函数。

结果：

- 项目上下文、员工上下文、规则、任务树、工具摘要、历史消息混在一起
- 难以单独调试“哪一层 prompt 导致模型行为变化”
- 难以针对不同入口复用

#### 问题 3：Provider 决策能力还偏配置读取

当前项目已有：

- `provider_id`
- `model_name`
- connector 相关配置
- 平台模型服务能力

但还缺少统一的 Provider 解析层来回答：

- 最终选谁执行
- 选本地 connector 还是平台 provider
- fallback 怎么处理
- model/provider 选择优先级是什么

#### 问题 4：Tool 暴露与执行还不是统一注册表

当前工具来源很多：

- 项目内置工具
- 项目成员代理工具
- 外部 MCP 工具
- 全局助手内置工具
- 本地连接器工具

这些能力当前业务上能跑，但没有统一的 registry 抽象。

结果：

- 暴露逻辑、执行逻辑、权限判断逻辑不完全在同一处
- 前端展示、风险控制、模型暴露工具列表难以完全统一

#### 问题 5：任务树生成仍然带有“关键词误判”

当前任务树虽然已经具备：

- 计划步骤过滤
- 查询型问题自动收口
- 过程事件回填
- 未回写任务树时的审计提醒

但生成阶段仍存在明显的启发式误判风险。

已确认的真实例子：

- [`project_chat_task_tree.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/project_chat_task_tree.py) 的 `_build_goal_oriented_plan_steps()` 里，只要命中“页面 / 切换 / tabs / 设置页”等词，就会优先生成页面切换类节点
- 这会把“让前端页面直接看到反馈”“补方案文档”这类治理型需求，误判成“Tabs 改造”任务

结果：

- 任务树节点会偏离真实目标
- 后续 `audit_task_tree_round()` 再努力回写，也是在错误节点上推进
- 前端展示出来的执行路径会把错误直接暴露给用户

#### 问题 6：任务树审计已经存在，但还不是“前端可消费的反馈协议”

当前聊天页已经能展示：

- `taskTreeAudit.message`
- `suggested_status`
- `auto_updated`
- `executed_tool_names`

但仍然偏“文本提醒”，还不是稳定协议。

当前缺口：

- 缺少严重级别 `severity`
- 缺少问题归类 `category`
- 缺少前端动作建议 `recommended_action`
- 缺少修复提示 `repair_hint`
- 缺少结构化证据 `evidence`
- 缺少“本轮为什么被误判 / 为什么没有完成 / 为什么被自动推进”的可视化字段

结果：

- 前端只能显示一段提醒文字
- 用户能看到“有问题”，但很难一眼判断问题属于生成误判、回写缺失、验证不足还是归档异常

#### 问题 7：任务树有回写能力，但还缺少“自进化”闭环

当前系统已经有：

- `audit_task_tree_round()`
- work session 事件回填
- task tree reconciliation

但还没有把这些异常和人工修正，反向沉淀为“下一轮更稳”的运行时资产。

当前还缺：

- 任务树误判样本沉淀
- 节点质量评分
- 高频误判关键词黑名单 / 降权表
- 人工改写节点后的原因记录
- 任务树模板命中率统计

结果：

- 同一类问题会重复犯错
- 任务树虽然能补救，但很难自己变稳

## 4. 目标形态

后续推荐的稳定主链应为：

```text
Router / MCP Entry
  -> RuntimeContextResolver
  -> TaskTreeStabilityGuard
  -> PromptAssembler
  -> ProviderResolver
  -> ToolRegistry
  -> AgentOrchestrator Loop
  -> FeedbackSignalBuilder
  -> TaskTree / WorkSession / Memory 回写
  -> EvolutionRecorder
```

关键原则：

- 项目 MCP 与统一查询 MCP 继续作为主入口
- 聊天 UI 只是这些能力的一个消费面
- 运行时升级必须能同时服务：
  - 项目聊天
  - 统一查询 MCP
  - 项目协作执行
  - 外部 MCP 工具调用
- 任务树不是“附属显示”，而是主执行链的一部分
- 前端反馈面要直接消费运行时信号，而不是靠页面自己猜状态

## 5. 核心补强分别是什么

## 5.1 统一运行时

### 它要解决的问题

把“一次执行到底怎么跑”收口成同一套上下文对象。

### 推荐新增目录

```text
web-admin/api/services/runtime/
├── runtime_context.py
├── runtime_resolver.py
└── runtime_types.py
```

### 推荐核心对象

`RuntimeContext`

建议至少包含：

- `project_id`
- `username`
- `chat_session_id`
- `employee_id`
- `selected_employee_ids`
- `workspace_path`
- `skill_resource_directory`
- `chat_surface`
- `history`
- `images`
- `task_tree_payload`
- `task_tree_health`
- `feedback_signals`
- `chat_settings`
- `resolved_provider`
- `resolved_tools`

### 当前代码映射

- 从 [`projects.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/routers/projects.py) 抽出聊天执行需要的运行时上下文收集逻辑
- 从 [`dynamic_mcp_runtime.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/dynamic_mcp_runtime.py) 抽出 MCP 执行所需上下文解析逻辑
- 让 [`agent_orchestrator.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/agent_orchestrator.py) 接收统一上下文，而不是散装参数

### 第一阶段不做

- 不重写任务树系统
- 不替换现有 router
- 不引入全新 agent 类

## 5.2 Prompt 装配

### 它要解决的问题

把“模型到底看到什么”拆成稳定、可解释的 section。

### 推荐新增目录

```text
web-admin/api/services/prompting/
├── prompt_assembler.py
├── prompt_sections.py
└── prompt_cache.py
```

### 推荐 section

- `platform_section`
- `project_section`
- `employee_section`
- `rules_section`
- `memory_section`
- `task_tree_section`
- `tooling_section`
- `conversation_section`
- `feedback_section`

### 当前代码映射

重点拆分当前 [`projects.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/routers/projects.py) 中：

- `_build_project_chat_messages`
- `_build_global_chat_messages`

### 第一阶段目标

- 先把 section 拆出来
- 先保证输出和现有行为尽量等价
- 不先追求“更聪明”，先追求“可维护、可解释、可复用”

## 5.3 Provider 解析

### 它要解决的问题

把 provider/model/connector 的选择逻辑从“配置读取”升级为“统一决策”。

### 推荐新增目录

```text
web-admin/api/services/runtime/
└── provider_resolver.py
```

### 推荐核心对象

`ResolvedProviderRuntime`

建议包含：

- `provider_id`
- `model_name`
- `base_url`
- `api_mode`
- `source`
- `temperature`
- `max_tokens`
- `connector_mode`
- `connector_workspace_path`
- `sandbox_mode`
- `fallback_provider_id`
- `fallback_model_name`

### 当前代码映射

重点整合：

- [`projects.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/routers/projects.py) 中的项目聊天设置
- [`local_connector_service.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/local_connector_service.py) 的本地执行路径
- [`llm_provider_service.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/llm_provider_service.py) 的 provider/model 校验与调用能力

### 第一阶段目标

- 明确选择优先级
- 明确 connector 与平台 provider 的切换规则
- 明确 fallback 策略

## 5.4 Tool Registry

### 它要解决的问题

把“工具从哪里来、谁能看、谁能调、怎么调、是否高风险”统一成一套对象模型。

### 推荐新增目录

```text
web-admin/api/services/tools/
├── tool_entry.py
├── tool_registry.py
├── tool_visibility.py
└── tool_policy.py
```

### 推荐核心字段

`ToolEntry`

- `tool_name`
- `scope`
- `source`
- `schema`
- `project_id`
- `employee_id`
- `risk_level`
- `auto_callable`
- `timeout_sec`
- `visible_in_chat`
- `binds_task_tree`
- `executor`

### 当前代码映射

重点收口这些来源：

- [`dynamic_mcp_apps_project.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/dynamic_mcp_apps_project.py)
- [`dynamic_mcp_apps_employee.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/dynamic_mcp_apps_employee.py)
- [`dynamic_mcp_runtime.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/dynamic_mcp_runtime.py)
- [`tool_executor.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/tool_executor.py)

### 第一阶段目标

- 先统一工具元数据
- 再逐步统一执行与可见性判断
- 不要求第一版就替换所有调用路径

## 5.5 Task Tree Stability Guard

### 它要解决的问题

把“任务树生成错误、推进偏离、验证缺失、归档不稳”从零散补救，升级为一层显式守卫。

### 推荐新增目录

```text
web-admin/api/services/task_tree_guard/
├── task_tree_guard.py
├── task_tree_feedback.py
├── task_tree_health.py
└── task_tree_evolution.py
```

### 推荐核心职责

#### 1）生成前判型

在真正生成任务树前，先做一次轻量判型：

- 查询型
- 实现型
- 文档/方案型
- 页面交互型
- 配置/治理型

最重要的是避免把“提到页面”误判成“页面改造型任务”。

最小规则建议：

- “前端页面能看到反馈”不能单独触发 UI 改造模板
- 当需求同时命中文档 / 方案 / 稳定性 / 任务树时，应优先进入“治理型/方案型任务树模板”
- 只有明确出现“新增页面 / 改页面 / 改路由 / 改 Tabs / 交互重构”时，才进入页面改造模板

#### 2）节点质量校验

在任务树生成后立即做 lint：

- 节点标题是否直接对应用户目标
- 是否混入内部工具名
- 是否混入 `Auto inferred proxy entry from ...`
- 是否出现与原始目标无关的 UI/路由/Tabs 节点
- 是否缺少验证型尾节点

建议输出：

`TaskTreeHealthReport`

- `health_score`
- `issues`
- `rebuild_recommended`
- `rebuild_reason`
- `safe_to_display`

#### 3）推进期守卫

在 `audit_task_tree_round()` 之外再补一层：

- 当前节点和本轮回答语义不一致时，不自动推进
- 若回答明显属于“文档/方案输出”，但当前节点是“页面改造”，则标记 `node_goal_mismatch`
- 若任务树仍停在错误节点，但工作轨迹已显示完成其他类型工作，则建议重建而不是硬推进

#### 4）归档前收口

在归档前统一检查：

- 所有叶子节点是否有验证结果
- 根节点是否有整体验证
- 当前任务树是否存在高严重度 issue
- `task_tree / work_session / memory` 是否绑定同一 `chat_session_id`

### 当前代码映射

- [`project_chat_task_tree.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/services/project_chat_task_tree.py)
  - `_build_goal_oriented_plan_steps()`
  - `_build_task_tree_plan_steps()`
  - `audit_task_tree_round()`
  - `_reconcile_task_tree_from_work_session_events()`
- [`projects.py`](/Volumes/苹果1_5T/self/ai-employee/web-admin/api/routers/projects.py)
  - 首轮任务树创建与返回

### 第一阶段目标

- 先把“生成误判”挡住
- 再把“推进偏离”显式化
- 最后再决定是否自动重建任务树

## 5.6 Frontend Feedback Surface

### 它要解决的问题

让用户在前端页面第一眼就能看到：

- 当前任务树是否健康
- 这轮有没有自动推进
- 为什么没有标记完成
- 是否建议重建 / 修正 / 补验证

### 推荐新增目录

```text
web-admin/frontend/src/modules/task-tree-feedback/
├── taskTreeFeedback.ts
├── TaskTreeFeedbackBanner.vue
├── TaskTreeIssueList.vue
└── useTaskTreeHealth.ts
```

### 推荐前端承载位置

#### 聊天页 [`ProjectChat.vue`](/Volumes/苹果1_5T/self/ai-employee/web-admin/frontend/src/views/projects/ProjectChat.vue)

当前已有：

- 消息内 `taskTreeAudit`
- 任务树抽屉

建议新增：

- 聊天区顶部常驻 `TaskTreeFeedbackBanner`
- 抽屉顶部的“健康状态卡”
- 节点详情中的“为什么当前节点不安全 / 为什么建议验证中 / 为什么建议重建”

#### 项目详情页 [`ProjectDetail.vue`](/Volumes/苹果1_5T/self/ai-employee/web-admin/frontend/src/views/projects/ProjectDetail.vue)

当前已有：

- 历史 round 汇总
- 节点轨迹
- 验证结果展示

建议新增：

- 每个 round 的 `health_score`
- `issue_count`
- `rebuild_count`
- “本轮误判类型”标签

### 推荐前端反馈协议

后端不要只返回：

- `message`

应扩成：

```json
{
  "status": "attention",
  "code": "node_goal_mismatch",
  "severity": "high",
  "category": "task_tree_generation",
  "message": "当前节点与本轮回答目标不一致，建议重建任务树。",
  "recommended_action": "rebuild_task_tree",
  "repair_hint": "检测到本轮输出属于方案/文档类，而当前节点是页面改造类。",
  "evidence": ["命中了页面型启发式关键词：页面", "本轮无路由/组件变更"],
  "auto_updated": false
}
```

### 视觉要求

前端样式必须继续遵守项目 UI 规则 `rule-134beefd`：

- 保持浅色、轻玻璃、低噪音
- 只允许一个主焦点
- 反馈卡优先做“状态判断 + 一句解释 + 一个动作”
- 不把聊天页堆成后台审计台

### 第一阶段目标

- 先把“问题看得见”做出来
- 不先做复杂运营面板
- 不重做整个聊天页结构

## 5.7 Evolution Loop

### 它要解决的问题

让任务树从“每次重新猜”升级为“基于已知失败模式持续收敛”。

### 推荐沉淀内容

- 高频误判关键词
- 高频错误模板
- 人工修正后的正确节点标题
- 哪些 `audit code` 最常出现
- 哪些任务树最终需要重建
- 哪些重建后结果更稳定

### 推荐新增对象

`TaskTreeEvolutionSample`

- `root_goal`
- `detected_intent`
- `wrong_template`
- `corrected_template`
- `issue_code`
- `user_visible`
- `manually_corrected`
- `rebuild_successful`

### 建议的自进化方式

第一阶段不做“模型自动改规则”，只做可控闭环：

1. 记录误判样本
2. 汇总高频问题
3. 人工确认后更新启发式/模板
4. 再把稳定规则固化到运行时

### 第一阶段目标

- 先让系统知道自己哪里常错
- 再让系统减少重复犯错
- 暂不引入不可解释的自动策略漂移

## 6. 第一阶段建议落地顺序

## 6.1 Step 0：先做 Task Tree Stability Guard

原因：

- 这是当前最直接暴露给用户的问题
- 错误任务树会污染前端展示、工作轨迹和记忆摘要
- 不先补这层，后面的运行时收口会继续建立在错误执行路径上

交付物：

- `task_tree_guard.py`
- `TaskTreeHealthReport`
- 任务树生成判型规则
- 误判关键词降权表

## 6.2 Step 1：补 Frontend Feedback Surface

原因：

- 用户已经能在页面看到任务树
- 现在需要把“看见任务树”升级成“看见问题和建议动作”

交付物：

- `TaskTreeFeedbackBanner.vue`
- 聊天页任务树健康卡
- 项目详情页 round 健康标签
- 后端反馈协议扩展

## 6.3 Step 2：再做 Provider Resolver

原因：

- 改动面最小
- 最容易立刻降低执行分叉
- 为后续 RuntimeContext 提供稳定底座

交付物：

- `provider_resolver.py`
- provider 选择优先级文档

## 6.4 Step 3：拆 Prompt Assembler

原因：

- 当前消息装配已经够复杂
- 这是最影响可维护性的部分

交付物：

- `prompt_assembler.py`
- section 化 prompt 结构

## 6.5 Step 4：补 RuntimeContextResolver

原因：

- 有了 provider 和 prompt 两层后，再把上下文收口成本更低

交付物：

- `RuntimeContext`
- `runtime_resolver.py`

## 6.6 Step 5：建立 Tool Registry

原因：

- 收益最大
- 波及面也最大

交付物：

- `tool_registry.py`
- 当前工具来源统一映射表

## 6.7 Step 6：最后补 Evolution Loop

原因：

- 先把守卫和反馈面做出来，才能拿到足够可信的误判样本
- 自进化应建立在结构化反馈之上，而不是直接依赖模糊聊天记录

交付物：

- `task_tree_evolution.py`
- 误判样本存储结构
- 高频问题汇总脚本或接口

## 7. 第一阶段明确不做什么

- 不重做 `web-admin` AI 对话页
- 不新造一套 CLI
- 不重写任务树服务
- 不做“模型自己改自己规则”的黑箱自进化
- 不把当前项目平台化优势改成单体 Agent 架构
- 不把所有 MCP 模块硬收成一个巨型运行时文件

## 8. 对现有项目最重要的保护原则

后续重构时，必须保护当前项目最值钱的能力：

- `project_id + chat_session_id` 绑定
- 项目级 task tree 闭环
- 任务树节点必须持续对齐真实目标，不能为了自动推进而容忍错误拆解
- work session / project memory / task tree 的可追溯关系
- 项目协作入口 `execute_project_collaboration`
- 项目级 MCP 与统一查询 MCP 的双入口结构
- 前端页面要能直接看到当前任务树是否健康、为什么被拦住、下一步该做什么

也就是说：

> 该学习 Hermes 的，是运行时收口能力；不该丢掉的，是当前项目的平台治理能力，以及任务树可追溯、可审计、可视化的主链能力。

## 9. 第一阶段验收标准

第一阶段完成后，至少应满足：

- 方案/文档类需求不再被“页面/Tabs”启发式误判成页面改造任务
- 任务树生成后会立刻产出 `health_score` 与 `issues`
- 聊天页可直接看到任务树健康状态与修复建议
- 项目详情页可回看 round 级别的健康状态与误判类型
- `audit_task_tree_round()` 的输出不再只有自然语言，而是结构化反馈协议
- 误判样本可沉淀，且后续可用于调规则
- 不破坏现有 `project_id + chat_session_id + task_tree + work_session + memory` 绑定闭环

## 10. 一句话原则

当前项目后续不是“把聊天做强”，而是：

> 在 MCP 主入口不变的前提下，先把任务树做稳、把反馈做显，再把运行时做成真正可复用的厚能力层。
