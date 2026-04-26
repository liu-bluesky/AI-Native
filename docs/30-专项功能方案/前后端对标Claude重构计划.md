# 前后端对标 Claude Code 的重构计划

> 日期：2026-04-25  
> 当前项目：`/Volumes/苹果1_5T/self/ai-employee`  
> 参考仓库：`/Volumes/苹果1_5T/self/claude-code-cli/`  
> 结论：借鉴 Claude Code 的运行时分层、工具治理、权限前置、会话恢复和扩展面，不复制 CLI/Ink 终端 UI。

## 1. 当前检查结论

### 1.1 当前项目形态

- 前端：`web-admin/frontend`，Vue 3 + Element Plus + Vite。
- 后端：`web-admin/api`，FastAPI + FastMCP，已有 JSON/PostgreSQL 双存储形态。
- MCP-first 定位已经写入 `README.md`，平台主能力应沉淀为 MCP tools/resources/prompts，而不是由 Web 聊天页反向定义。
- 已有专项文档：
  - `docs/30-专项功能方案/ClaudeCLI可借鉴能力与MCP升级映射.md`
  - `docs/30-专项功能方案/MCP优先下的Agent运行时补强方案.md`
  - `docs/30-专项功能方案/AI对话中心重构方案.md`
  - `docs/30-专项功能方案/任务闭环执行与恢复状态机设计.md`

### 1.2 当前主要复杂度

- `web-admin/frontend/src/views/projects/ProjectChat.vue` 约 2 万行，是前端最大风险点，混合了聊天、MCP 配置、任务树、终端镜像、审批、tour、设置面板、WebSocket 和运行时状态。
- `web-admin/frontend/src/views/projects/ProjectShortFilmStudio.vue`、`ProjectDetail.vue`、`GlobalAiAssistant.vue` 也明显偏大，适合按业务域拆分。
- `web-admin/api/routers/projects.py` 约 1.45 万行，是后端最大风险点，混合了项目 CRUD、聊天、素材、短片工作室、导出任务、任务树、模型选择和大量 normalize/serialize 函数。
- 后端已有 `web-admin/api/services/runtime/`、`task_tree_guard/`、`project_chat_task_tree.py`、`agent_orchestrator.py`、`tool_executor.py`，说明运行时拆分已经启动，但还没有彻底收口。
- 前端已有 `web-admin/frontend/src/modules/task-tree-feedback/`，说明任务树反馈协议开始结构化，但还未扩展成完整 Runtime Feedback Surface。

## 2. Claude Code 可借鉴点

### 2.1 运行时内核优先

Claude Code 的重点不是 UI，而是围绕 QueryEngine、Tool、Permission、Session、Command、MCP、Skill 形成统一运行时。当前项目应对标这一点，把平台能力沉淀到统一 MCP/Runtime 层。

### 2.2 模块边界清晰

参考仓库按以下维度组织：

- `commands/`：命令入口与交互动作。
- `tools/`：工具定义、输入校验、权限、UI 展示、执行结果。
- `services/tools/`：工具编排、执行、hooks、流式调度。
- `services/mcp/`：MCP 客户端、连接、配置、认证、规范化。
- `state/`、`context/`：运行时状态与 UI 上下文。
- `components/design-system/`：设计系统组件，而不是在业务页内堆样式。

### 2.3 权限与工具前置治理

Claude Code 把工具可见性、工具可用性、权限判断和执行分开处理。当前项目应把 `check_operation_policy`、`check_workspace_scope`、`classify_command_risk`、工具过滤、执行模式解析纳入统一 Tool Registry，而不是散落在路由和前端条件分支里。

### 2.4 会话恢复是事件日志

Claude Code 的会话恢复不是简单聊天记录，而是可恢复执行轨迹。当前项目已有任务树、work session、memory、requirement 本地对象，应继续统一成事件日志：每次任务分析、节点推进、工具调用、验证、异常和恢复都可追溯。

## 3. 目标架构

### 3.1 后端目标分层

```text
web-admin/api/
├── routers/                    # 只做 HTTP 入参、鉴权和响应装配
│   ├── projects.py             # 保留项目基础路由，逐步瘦身
│   ├── project_chat.py         # 新增：项目聊天/会话路由
│   ├── project_materials.py    # 新增：素材库路由
│   ├── project_studio.py       # 新增：短片工作室路由
│   └── project_task_tree.py    # 新增：任务树路由
├── services/runtime/           # Agent Runtime 内核
│   ├── runtime_types.py
│   ├── runtime_resolver.py
│   ├── provider_resolver.py
│   ├── prompt_assembler.py
│   ├── tool_registry.py
│   ├── run_request_factory.py
│   └── orchestrator_factory.py
├── services/tools/             # 建议新增：工具执行治理层
│   ├── registry.py
│   ├── permissions.py
│   ├── execution.py
│   └── audit.py
├── services/project_chat/      # 建议新增：项目聊天领域服务
├── services/project_studio/    # 建议新增：短片工作室领域服务
└── stores/                     # 保持 JSON/Postgres 双实现，但统一接口
```

核心原则：router 变薄，runtime 变厚；业务域服务负责领域规则，runtime 服务负责执行链路。

### 3.2 前端目标分层

```text
web-admin/frontend/src/
├── api/                        # 按领域封装请求客户端
│   ├── projectChat.ts
│   ├── projectMaterials.ts
│   ├── projectStudio.ts
│   └── taskTree.ts
├── modules/
│   ├── project-chat/           # 聊天主域
│   ├── runtime-feedback/       # 运行时/任务树反馈面
│   ├── project-settings/       # 项目 AI 设置、MCP、模型配置
│   ├── host-terminal/          # 终端镜像与审批
│   └── studio/                 # 短片工作室
├── components/design-system/   # 项目内设计系统与通用交互组件
├── composables/                # 组合式状态与副作用
└── views/projects/             # 页面编排层，只组合模块
```

核心原则：页面只编排，逻辑进 composables，协议进 api，展示进模块组件。

## 4. 分阶段重构计划

### Phase 0：冻结基线与建立护栏（1-2 天）

目标：先让后续重构可控。

- 建立当前关键行为清单：项目聊天、任务树、MCP 工具、模型选择、素材上传、短片工作室、终端镜像。
- 补充 smoke tests 或最小回归脚本，至少覆盖项目聊天、任务树读取/推进、provider resolver、tool registry。
- 为 `ProjectChat.vue`、`projects.py` 标记“仅迁移不新增大功能”的临时约束。
- 输出迁移矩阵：旧函数/状态/接口 → 新模块位置。

验收：能说明每个高风险入口的回归方式，且无新增大规模逻辑继续进入巨型文件。

### Phase 1：前端 ProjectChat 瘦身（3-5 天）

目标：先拆最痛的页面，但不改变用户行为。

- 抽 `modules/project-chat/`：消息列表、输入框、附件、会话恢复、WebSocket 状态。
- 抽 `modules/runtime-feedback/`：任务树健康、审计 banner、节点验证状态、恢复提示。
- 抽 `modules/project-settings/`：模型、provider、MCP source、工具选择、workspace/entry file 配置。
- 抽 `modules/host-terminal/`：终端镜像、审批 fallback、terminal panel。
- 把副作用迁入 composables：`useProjectChatSession`、`useProjectRuntimeSettings`、`useTaskTreeState`、`useHostTerminalMirror`。

验收：`ProjectChat.vue` 降到 3000 行以内；每个模块有清晰 props/emits 或 composable API；页面只负责布局和模块组合。

### Phase 2：后端 projects.py 按领域拆路由（4-6 天）

目标：消除单文件路由中心化风险。

- 抽 `routers/project_chat.py`：聊天发送、会话、任务树上下文绑定、运行时调用。
- 抽 `routers/project_materials.py`：素材上传、预览、删除、元数据。
- 抽 `routers/project_studio.py`：短片工作室、脚本抽取、分镜、导出任务。
- 抽 `routers/project_task_tree.py`：任务树 CRUD、节点推进、审计、恢复。
- 将 normalize/serialize 工具迁入领域 serializer：`services/project_materials/serializers.py`、`services/project_studio/serializers.py`。

验收：`projects.py` 保留项目基础 CRUD 和公共 serializer，目标降到 3000 行以内；原 API 路径保持兼容；已有测试可通过或只需改 import。

### Phase 3：对标 Claude 的 Runtime Core 收口（5-8 天）

目标：把 Agent 执行链路从业务路由中抽出来。

- 完善 `services/runtime/runtime_types.py`：显式定义 `ChatRuntimeContext`、`ResolvedProviderRuntime`、`EffectiveToolDescriptor`、`PromptAssemblyResult`。
- 强化 `runtime_resolver.py`：统一解析 project、employee、chat settings、workspace、session、task tree、memory。
- 强化 `prompt_assembler.py`：按 section 装配 system/project/employee/rules/tools/task_tree/history，支持调试输出。
- 强化 `provider_resolver.py`：统一 provider/model 优先级、fallback、connector 与平台 provider 的选择结果。
- 强化 `tool_registry.py`：统一项目工具、员工代理工具、外部 MCP、本地连接器工具的可见性、排序、权限预判。

验收：项目聊天、统一查询 MCP、项目协作执行能复用同一套 runtime resolver/assembler/registry；新增能力不再直接拼 prompt 或手写工具列表。

### Phase 4：权限、工具和任务树治理闭环（4-6 天）

目标：把 Claude Code 的“工具前置治理”落到当前 MCP-first 架构。

- 新增或强化 `services/tools/permissions.py`：统一封装 workspace scope、sandbox mode、风险等级、用户确认策略。
- 新增或强化 `services/tools/execution.py`：统一执行前检查、执行中事件、执行后审计。
- 强化 `task_tree_guard`：生成前判型、节点质量检查、推进期守卫、归档前验证。
- 前端 `runtime-feedback` 消费结构化协议：`severity`、`category`、`recommended_action`、`repair_hint`、`evidence`。
- 将人工修正、误判样本和自动审计写入可统计的 evolution samples。

验收：工具暴露前可解释“为什么可用/不可用”；任务树错误能给出结构化问题和推荐动作；用户能在前端看懂风险来源。

### Phase 5：设计系统与业务模块统一（3-5 天）

目标：把 Claude 的 design-system 思路映射到 Web 管理端。

- 新增 `components/design-system/`：Pane、StatusTag、EmptyState、MetricStrip、ActionToolbar、ConfirmPanel、FeedbackBanner。
- 统一项目工作区、任务树、MCP 配置、素材库的视觉语言。
- 将 `ui-design.css` 中可复用 token 提炼为 CSS variables 和组件级样式约定。
- 逐步替换巨型页面内的重复卡片、状态、按钮组和提示条。

验收：新模块优先使用设计系统组件；重复样式减少；页面视觉一致性提升。

### Phase 6：事件日志、恢复和观测（4-7 天）

目标：让“可恢复执行轨迹”成为平台默认能力。

- 统一 work session、task tree、memory、requirement 的关联键：`project_id + chat_session_id + session_id`。
- 将关键事件写成统一 event：任务分析、计划生成、工具暴露、工具调用、权限判断、节点验证、失败恢复。
- 为前端提供 session timeline：按轮次展示“计划 → 执行 → 验证 → 恢复”。
- 增加运行时调试面板：prompt sections、provider 选择、tool registry 快照、policy result。

验收：中断后能恢复到明确节点；排查一次模型或工具异常时，可以看到完整运行时上下文，而不是只看聊天文本。

## 5. 不建议做的事

- 不要重做 Claude Code 的 CLI/Ink UI；当前项目主入口是 MCP-first 平台能力。
- 不要一次性改写全部前后端；先围绕 `ProjectChat.vue` 和 `projects.py` 做可回归迁移。
- 不要把新功能继续塞进巨型页面或巨型 router。
- 不要让前端直接理解复杂后端策略；后端应返回结构化 runtime feedback。
- 不要只做 UI 拆分而不收口 runtime，否则只是把复杂度换位置。

## 6. 第一轮推荐落地顺序

1. 建迁移矩阵和回归清单。
2. 拆 `ProjectChat.vue` 的 task tree/runtime feedback 模块。
3. 拆 `ProjectChat.vue` 的 settings 和 terminal 模块。
4. 拆 `projects.py` 的 task tree 和 project chat 路由。
5. 补强 `services/runtime/` 的 resolver、assembler、registry。
6. 建 `services/tools/` 的权限与执行治理层。
7. 再拆素材库和短片工作室。

## 7. 成功指标

- `ProjectChat.vue`：从约 2 万行降到 3000 行以内。
- `projects.py`：从约 1.45 万行降到 3000 行以内。
- Runtime 复用：项目聊天、统一查询 MCP、项目协作执行共用同一套上下文解析和工具注册。
- 权限前置：工具暴露前已有 policy 结果，执行前不再临时散判。
- 任务树闭环：每个执行节点都能看到状态、验证、异常原因和恢复建议。
- 可观测性：任一会话能回放 provider、prompt sections、tool registry、policy、task tree 变化。

