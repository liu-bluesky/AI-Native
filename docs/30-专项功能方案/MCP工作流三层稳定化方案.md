# MCP 工作流三层稳定化方案

## 1. 背景

当前统一查询 MCP 已经具备项目绑定、上下文查询、任务分析、执行规划、工作轨迹和任务树闭环能力，但实际使用时仍有一个稳定性问题：很多关键步骤依赖宿主提示词提醒 AI 自觉执行。

当 AI 漏掉某一步时，系统可能出现以下问题：

- 没有先读取 `query://usage-guide` 和客户端画像，导致接入规则缺失。
- 没有用用户原始问题调用 `search_ids`，导致项目、规则和记忆检索不可追溯。
- 没有显式绑定 `project_id + chat_session_id`，导致任务树和记忆挂错会话。
- 没有先走 `analyze_task -> resolve_relevant_context -> generate_execution_plan`，导致任务规划不稳定。
- 没有回写任务树节点状态和验证结果，导致自然语言声称完成但系统状态未闭环。

因此稳定化不能只靠“更长的提示词”，也不应回到 `cli-runner` 这类本地命令封装。正确方向是把工作流拆成三层：

- 第一层：技能告诉 AI 怎么做。
- 第二层：工具或脚本封装固定步骤。
- 第三层：后端校验强制闭环。

## 2. 目标

本方案目标是让统一查询 MCP 的关键执行链路从“提示词驱动”升级为“技能引导 + 工具固定流程 + 后端校验”的稳定机制。

核心目标：

- 降低 AI 漏调用、错调用、跳步骤的概率。
- 把固定步骤从宿主提示词迁移到可复用技能和 MCP 工具中。
- 后端返回明确的 `missing_steps`、`blocked_reason` 和 `next_required_actions`，让 AI 无法把未闭环任务包装成已完成。
- 保持当前 MCP 标准协议，不要求注册系统本地 CLI 命令。
- 保持项目、任务树、工作轨迹、记忆使用同一条 `chat_session_id/session_id`。

## 3. 非目标

本方案不做以下事情：

- 不继续使用 `cli-runner` 作为稳定化主方案。
- 不把 Codex、Claude Code、Gemini CLI 等宿主本身再封装成一个“跑 CLI 的技能”。
- 不要求用户每次手工绑定员工或手工选择技能。
- 不把详细规则全部塞进宿主系统提示词。
- 不绕过现有统一查询 MCP 的项目绑定、任务树和工作轨迹能力。

## 4. 设计原则

### 4.1 技能只负责“教 AI”

技能层只放简短、可触发、可复用的工作方法，不承载后端状态，不执行真实闭环。

技能应该告诉 AI：

- 什么时候必须进入统一查询 MCP 工作流。
- 首选调用哪个固定入口工具。
- 遇到工具返回 `blocked`、`needs_confirmation`、`missing_steps` 时如何继续。
- 不要把技能文本当成事实来源，事实仍以 MCP 查询结果为准。

### 4.1.1 技能分发原则

`query-mcp-workflow` 不应作为“每个项目本地各拷一份”的技能文件存在，而应作为系统内置技能或系统技能库资产统一维护。

推荐原则：

- 技能在系统技能库中维护一份权威版本。
- 项目和员工只保存“已启用/已绑定”的索引关系，不复制技能正文。
- AI 通过 MCP 查询项目或员工技能索引后直接感知该技能可用。
- 技能升级时，应以系统技能库版本为准，而不是逐项目手工替换本地文件。

### 4.2 工具负责“固定步骤”

固定步骤不应该依赖 AI 自己逐条记住。工具层应提供一个编排入口，例如：

```text
start_project_workflow(...)
```

该入口一次性完成或返回以下结构：

- 用户原始问题登记。
- 项目绑定状态。
- 项目手册与相关规则读取状态。
- 任务分析结果。
- 相关上下文聚合结果。
- 执行计划骨架。
- 工作会话创建或复用结果。
- 任务树当前节点状态。
- 后端校验结果。
- 下一步必须动作。

### 4.3 后端负责“强制闭环”

后端不应只给 AI 建议，而要给出可机器判断的状态。

关键原则：

- 未绑定项目或会话时，返回 `blocked`。
- 未完成必需前置步骤时，返回 `missing_steps`。
- 未完成任务树节点验证时，不允许返回 `completed`。
- 风险操作未经过 `check_operation_policy` 时，返回 `needs_policy_check`。
- 输出必须有稳定 schema，避免 AI 自由解释。

## 5. 三层架构

```text
用户需求
  ↓
第一层：query-mcp-workflow 技能
  ↓
第二层：start_project_workflow 固定入口
  ↓
第三层：后端 workflow guard / task-tree guard / policy guard
  ↓
允许执行 / 需要补步骤 / 阻断 / 需要确认
```

## 6. 第一层：技能告诉 AI 怎么做

建议新增技能包：

```text
mcp-skills/knowledge/skill-packages/query-mcp-workflow/
```

建议新增技能注册：

```text
mcp-skills/knowledge/skills/query-mcp-workflow.json
```

技能触发条件：

- 用户要求开发、排查、实现、重构、写方案或继续已有 MCP 工作流。
- 当前任务涉及 `project_id`、`chat_session_id`、任务树、项目规则、员工技能或工作轨迹。
- 用户明确要求提升 MCP 工作流稳定性。

技能核心说明：

- 优先调用 `start_project_workflow`，不要手动拼接十几个查询步骤。
- 如果工具返回 `status=ready`，再按 `next_required_actions` 执行。
- 如果工具返回 `status=blocked`，先补齐 `missing_steps`，不要继续实现。
- 如果当前宿主拿不到任务树推进工具，必须明确说明“任务树闭环未完成”。
- 技能不执行本地命令，不替代 MCP 工具，不保存状态。

### 6.1 获取与启用方式

本方案下，`query-mcp-workflow` 的主获取方式不是“下载到项目本地”，而是“在系统内启用”。

推荐交互：

- `启用到项目`
- `绑定到员工`
- `设为默认工作流技能`
- `下载技能包（可选，仅用于导出或离线场景）`

设计结论：

- 日常使用以系统内直接启用为主。
- 下载只作为导出、离线备份、外部宿主迁移的辅助能力。
- 不要求用户每次把技能下载到项目目录。
- 不要求每个项目复制一份技能文件。

### 6.2 页面与后端分工

前端页面负责：

- 展示该技能是“系统内置技能 / 系统技能库资产”。
- 提供 `启用到项目`、`绑定到员工`、`设为默认工作流技能` 按钮。
- 展示当前启用范围、绑定对象和默认状态。

后端负责：

- 将该技能写入系统技能库主记录。
- 维护项目到技能、员工到技能的绑定关系。
- 把该技能加入项目或员工的技能索引。
- 让 AI 后续可通过 MCP 查询到该技能，而不是依赖本地文件扫描。

### 6.3 为什么不以下载到本地为主

如果以“下载到项目本地”为主流程，会带来几个问题：

- 技能版本容易漂移，不同项目副本可能不一致。
- 技能升级后需要逐项目替换，维护成本高。
- 项目、员工、系统技能库三套状态容易脱节。
- AI 查询到的是本地副本还是系统权威版本，容易产生歧义。

因此本方案采用：

```text
系统技能库保存权威技能
项目/员工只保存启用与绑定关系
AI 通过 MCP 查询索引直接使用
```

## 7. 第二层：工具或脚本封装固定步骤

### 7.1 推荐新增 MCP 工具

工具名称：

```text
start_project_workflow
```

建议位置：

```text
web-admin/api/services/dynamic_mcp_apps_query.py
```

原因：

- 该文件已注册统一查询 MCP 的主要工具。
- 现有能力已经包括 `bind_project_context`、`analyze_task`、`resolve_relevant_context`、`generate_execution_plan`、`start_work_session` 等。
- 新工具可以复用现有内部 payload 方法，避免重复实现一套工作流。

### 7.2 输入参数

```json
{
  "raw_request": "用户原始问题",
  "project_id": "proj-d16591a6",
  "chat_session_id": "chat-session-xxx",
  "client_profile": "codex",
  "employee_id": "",
  "clarity_score": 4,
  "start_session": true,
  "max_steps": 6
}
```

字段说明：

- `raw_request`：必须是用户原始问题，不能只写“当前任务”。
- `project_id`：项目绑定依据，不能依赖 MCP description。
- `chat_session_id`：任务树、记忆、工作轨迹的会话锚点。
- `client_profile`：默认 `codex`，用于返回客户端约束。
- `clarity_score`：由 AI 初步估计，也可由后端返回修正建议。
- `start_session`：是否自动创建工作会话。
- `max_steps`：执行计划步骤上限。

### 7.3 输出结构

```json
{
  "status": "ready",
  "project_id": "proj-d16591a6",
  "chat_session_id": "chat-session-xxx",
  "session_id": "ws_xxx",
  "workflow_version": "query-mcp-workflow/v1",
  "analysis": {},
  "relevant_context": {},
  "execution_plan": {},
  "task_tree": {
    "available": true,
    "current_node_id": "ttn_xxx",
    "current_node_title": "实现固定 MCP 工作流入口"
  },
  "guard": {
    "status": "ready",
    "missing_steps": [],
    "blocked_reason": "",
    "required_before_execution": []
  },
  "next_required_actions": [
    "mark_current_task_node_in_progress",
    "perform_file_edits",
    "run_targeted_verification",
    "complete_task_node_with_verification"
  ],
  "backend_enforced_checks": [
    "raw_request_present",
    "project_bound",
    "manual_loaded",
    "analysis_generated",
    "context_resolved",
    "plan_generated",
    "work_session_started"
  ]
}
```

### 7.4 失败输出

```json
{
  "status": "blocked",
  "guard": {
    "status": "blocked",
    "missing_steps": [
      "project_id",
      "chat_session_id",
      "raw_request_search"
    ],
    "blocked_reason": "缺少项目绑定或用户原始问题登记，不能进入实现。",
    "required_before_execution": [
      "call_bind_project_context",
      "call_search_ids_with_raw_request"
    ]
  },
  "next_required_actions": [
    "补齐 project_id 和 chat_session_id 后重新调用 start_project_workflow"
  ]
}
```

## 8. 第三层：后端校验强制闭环

### 8.1 校验器职责

建议新增内部校验器：

```text
validate_query_workflow_guard(...)
```

校验器不需要暴露为用户工具，但应被 `start_project_workflow` 和后续节点完成工具复用。

校验项：

- `raw_request` 非空。
- `search_ids` 已使用原始问题。
- `project_id` 已显式传入。
- `chat_session_id` 已显式传入或已由后端创建并持久化。
- 项目手册已读取。
- 实现型任务已完成 `analyze_task -> resolve_relevant_context -> generate_execution_plan`。
- 工作会话已创建或已恢复。
- 当前任务树属于本轮用户问题。
- 当前节点开始前已标记 `in_progress`。
- 当前节点完成时带有验证结果。
- 风险命令或外部操作已通过 `check_operation_policy`。

### 8.2 状态枚举

```text
ready
blocked
needs_confirmation
needs_policy_check
in_progress
verifying
completed
```

状态语义：

- `ready`：前置条件满足，可以进入下一步。
- `blocked`：缺必填上下文或缺前置步骤，不能继续。
- `needs_confirmation`：清晰度不足或高风险动作需要用户确认。
- `needs_policy_check`：涉及命令、路径或工具执行，但未做策略检查。
- `in_progress`：当前节点正在执行。
- `verifying`：实现完成但验证未完成。
- `completed`：节点和整体验证均完成。

### 8.3 后端阻断规则

后端必须阻断以下情况：

- 没有 `raw_request` 就进入工作流。
- 没有 `project_id` 却尝试写项目记忆或任务树。
- 有任务树但 `chat_session_id` 不一致。
- 实现型任务没有生成结构化执行计划。
- 节点没有验证结果却被标记完成。
- 工具返回风险为高危但未确认。
- 输出 schema 不满足预期。

## 8.4 任务生命周期与暂停恢复

本方案要求：一次需求开始后创建的任务计划，不应只伴随某一次 AI 回复，而应伴随整条需求生命周期，直到完成并归档。

### 8.4.1 生命周期规则

标准生命周期：

```text
用户提出需求
  -> 创建或绑定 chat_session_id
  -> 创建任务树 / 执行计划 / work session
  -> 多轮对话持续复用同一任务
  -> 暂停后恢复
  -> 继续执行与验证
  -> 全部完成
  -> 归档
```

### 8.4.2 持续存在规则

只要需求未结束，任务计划就应该保持可检测：

- 在同一 `project_id + chat_session_id` 下，多次对话都应能读取到当前活动任务树。
- 即使 AI 暂停、用户暂时不继续开发，只要没有完成归档，任务仍应保持 `pending`、`in_progress` 或 `verifying`。
- 不允许因为一次对话中断、模型上下文清空或宿主重启，就把任务视为结束。
- 只有在全部节点完成并写入验证结果后，任务才允许归档并从“当前活动任务”中移除。

### 8.4.3 为什么任务会丢

任务丢失通常不是“需求结束了”，而是状态没有被后端正确持久化。

常见原因：

- 只把计划留在 AI 当前上下文里，没有写任务树和工作轨迹。
- 没有稳定复用 `chat_session_id`。
- 没有先 `start_work_session` 或没有持久化 `session_id`。
- 新开会话后没有按 `bind_project_context -> resume_work_session -> summarize_checkpoint` 恢复。
- 前端继续对话时没有把旧的 `chat_session_id` 带回来。

### 8.4.4 稳定化要求

为避免暂停后丢任务，本方案要求：

- 首轮就创建并持久化 `chat_session_id`。
- 长任务必须创建并复用 `session_id`。
- 任务树、工作轨迹、项目记忆必须绑定同一条会话线索。
- 当前活动任务必须能从后端状态恢复，而不是依赖 AI 自己回忆。
- 前端重新进入对话时，应自动读取当前活动任务树或给出恢复入口。

### 8.4.5 恢复流程

中断恢复的推荐顺序：

```text
恢复 chat_session_id + session_id
  -> bind_project_context(...)
  -> resume_work_session(...)
  -> summarize_checkpoint(...)
  -> get_current_task_tree(...)
  -> 继续执行当前节点
```

### 8.4.6 后端判定规则

后端应明确区分以下状态：

- `active_task_exists=true`：当前需求仍在进行，应继续沿用旧计划。
- `needs_resume=true`：当前任务未完成，但宿主中断，需要恢复上下文。
- `archived=true`：当前需求已完成，可开始下一轮新任务。
- `orphaned_state=true`：存在工作轨迹但没有正确挂到当前任务树，需要修复绑定。

## 9. MVP 范围

第一阶段只做最小稳定化闭环。

MVP 包含：

- 新增本方案文档。
- 新增 `query-mcp-workflow` 技能包。
- 新增 `start_project_workflow` MCP 工具。
- `start_project_workflow` 返回结构化 guard 和 next actions。
- 技能以系统技能库资产形式接入，支持项目启用、员工绑定和默认技能设置。
- 使用现有 `analyze_task`、`resolve_relevant_context`、`generate_execution_plan`、`start_work_session` 能力。
- 使用现有 `.ai-employee/query-mcp/` canonical 状态文件规范。
- 增加最小单元测试，确认工具暴露、guard 输出和 usage guide 引导。

MVP 不包含：

- 不做本地 CLI 命令执行。
- 不做跨宿主 CLI 自动安装。
- 不做复杂 UI 改造。
- 不替换现有任务树服务。

## 10. 推荐实施步骤

### 10.1 文档

新增：

```text
docs/30-专项功能方案/MCP工作流三层稳定化方案.md
```

### 10.2 技能

新增：

```text
mcp-skills/knowledge/skill-packages/query-mcp-workflow/SKILL.md
mcp-skills/knowledge/skill-packages/query-mcp-workflow/manifest.json
mcp-skills/knowledge/skills/query-mcp-workflow.json
```

配套后端与页面能力：

- 在系统技能库中登记 `query-mcp-workflow` 为内置技能。
- 提供项目启用、员工绑定、默认技能设置接口。
- 在项目详情或技能管理页面提供对应按钮，而不是只提供下载。

### 10.3 后端工具

修改：

```text
web-admin/api/services/dynamic_mcp_apps_query.py
```

建议新增：

```text
_start_project_workflow_payload(...)
_build_query_workflow_guard(...)
```

建议补充：

```text
_attach_system_skill_to_project(...)
_attach_system_skill_to_employee(...)
_resolve_project_skill_index(...)
```

注册工具：

```python
@mcp.tool()
def start_project_workflow(...):
    ...
```

后端还应补齐：

- 系统技能库主记录。
- 项目技能索引与员工技能索引。
- 当前活动任务、归档任务和恢复状态的统一读取接口。

### 10.4 测试

修改：

```text
web-admin/api/tests/test_unit.py
```

测试项：

- `start_project_workflow` 出现在统一查询 MCP 工具列表中。
- 缺少 `raw_request` 时返回 `blocked`。
- 传入 `raw_request + project_id + chat_session_id` 时返回 `analysis`、`relevant_context`、`execution_plan`、`guard`。
- usage guide 或 Codex profile 提示优先使用固定工作流入口。
- 系统技能启用到项目或绑定到员工后，可在技能索引查询中被命中。
- 任务未完成时，多轮对话恢复仍能读到同一活动任务树。
- 任务完成后，活动任务树会归档，不再继续占用当前任务。

## 11. 与现有规则的关系

本方案参考并落地以下项目经验规则：

- `rule-bf71b9e1`：工作流设计、固定入口、经验沉淀要形成端到端闭环。
- `rule-0903e0a6`：关键链路必须有显式模型、prompt version 和 output schema。
- `rule-86cb12b0`：规则和经验应按任务检索注入，不全量硬塞。
- `rule-9fa42976`：链路写入、删除、恢复和幂等要保持一致。
- `rule-838fe0c9`：AI 生成可复用知识或规则时应保留人工审核门。

## 12. 验收标准

文档验收：

- 能清楚解释三层分别解决什么问题。
- 明确说明 `cli-runner` 不是本方案方向。
- 给出后端工具、技能包、测试文件的落地路径。
- 给出输入输出 schema 和阻断规则。
- 明确说明技能以系统内置资产存在，主流程不是下载到项目本地。
- 明确说明任务计划应贯穿整个需求生命周期，而不是一次回复生命周期。

功能验收：

- AI 不需要记住十几个 MCP 前置步骤，只需优先调用 `start_project_workflow`。
- 后端能返回缺失步骤，而不是让 AI 自由猜测下一步。
- 任务树未验证时，后端不会给出完成状态。
- 关键链路状态能通过 `chat_session_id/session_id` 追溯。
- 中断恢复后能继续沿用同一条工作轨迹。
- 启用到项目或绑定到员工后，AI 能直接通过 MCP 查询到该技能并使用。
- 项目不需要复制技能文件，也不依赖手工下载后再接入。

稳定性验收：

- 同一请求重复进入工作流不会重复生成无关任务树。
- 缺 `project_id`、缺 `chat_session_id`、缺验证结果时均可观测。
- 风险动作未检查时不会进入真实执行。
- 单元测试覆盖 ready 与 blocked 两类返回。
- AI 暂停、宿主重启或多轮对话切换后，只要需求未完成，活动任务仍可恢复。
- 只有归档后，计划才从当前活动任务中移除。

## 13. 风险与处理

风险一：固定入口过大，变成另一个黑盒。

处理方式：

- 输出必须保留每个子步骤的状态。
- `backend_enforced_checks` 必须列出已完成校验。
- `missing_steps` 必须明确可执行。

风险二：技能和后端规则重复。

处理方式：

- 技能只写“怎么调用”和“遇到状态怎么处理”。
- 后端负责事实校验和阻断。
- 详细规则仍由 MCP 资源和项目规则按需读取。

风险三：旧任务树被误复用。

处理方式：

- `start_project_workflow` 必须校验任务树 `root_goal/title/current_node`。
- 明显不属于当前问题时返回 `blocked`，要求新建 `chat_session_id`。

风险四：后端无法推进任务树。

处理方式：

- 返回 `task_tree.available=false` 或 `task_tree_closure_supported=false`。
- AI 最终答复必须说明“任务树闭环未完成”。

风险五：技能以本地文件副本分发，导致项目版本漂移。

处理方式：

- 技能权威版本只保留在系统技能库。
- 项目和员工只维护绑定关系，不复制技能正文。
- 页面下载能力仅作为导出用途，不作为主流程。

风险六：任务计划只存在 AI 上下文里，暂停后丢失。

处理方式：

- 任务树、工作轨迹、恢复状态全部后端持久化。
- 强制复用 `chat_session_id/session_id`。
- 前端恢复时优先拉活动任务而不是重新新建任务。

## 14. 结论

三层稳定化的核心不是“让 AI 多记一段提示词”，而是把不稳定的人工约定下沉为稳定接口和后端状态机。

最终形态应是：

```text
技能负责触发和指导
工具负责固定流程编排
后端负责校验、阻断和闭环
```

这样当前统一查询 MCP 才能从提示词运营，升级为可追踪、可恢复、可验证的工程化工作流。
