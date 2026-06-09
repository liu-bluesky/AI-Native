# 统一查询 MCP 入口工作流与任务树体验调整计划

> 生成时间：2026-06-06 09:23:19 CST
> 最近补全：2026-06-06 09:30 CST
> 项目：ai员工工厂项目 / proj-d16591a6
> 工作区：/Volumes/work_mac_1_5T/self/ai-employee

## 背景

当前用户反馈集中在四个问题：

1. 任务树生成内容几乎都一样，明明是不同任务需求，却常被拆成类似“分析、实现、验证”的模板。
2. 任务停止、重启或上下文压缩后，恢复继续开发的可靠性差，下一轮很难知道真实做到哪里。
3. 工作总结不够友好，更像工具流水账，不像面向项目管理和交付的总结。
4. MCP 入口工作流本身需要进入计划范围，不能只改任务树生成或总结文案。

这份计划的目标不是再做一个 Codex、Hermes 或普通聊天工具，而是把 ai员工工厂收敛为“AI 项目执行系统 / Agent 工作流控制台”：负责接住需求、生成可执行任务树、调度工具和员工、记录真实状态、支持中断恢复，并产出人能读懂的交付总结。

## 这次必须说清楚的结论

仅写文档不会改变任务树生成结果。当前代码仍然会生成三段式任务树。

已核对真实代码入口：

- `web-admin/api/services/chat/project_chat_task_tree.py`
- `_build_goal_oriented_plan_steps(task_text, max_steps=6)`
- `ensure_task_tree(...)`
- `build_task_tree_session(...)`
- `web-admin/api/tests/test_project_chat_task_tree_routes.py`

当前根因很明确：`_build_goal_oriented_plan_steps` 虽然按 `detected_intent` 区分了 `governance`、`documentation`、`ui_flow`、修复、优化和默认分支，但每个分支基本都返回 3 个节点：分析、实现、验证。节点标题里有少量词替换，但结构没有真正按任务类型展开。

本轮新建“补全 MCP 入口工作流与任务树体验调整计划”的任务树时，系统再次生成：

1. 梳理 当前需求 当前任务链、反馈面和状态绑定
2. 完成 当前需求 的稳定性补强与反馈透出
3. 验证任务连续性、健康反馈和收尾结果

这就是用户说“几乎都一样”的直接证据。后续代码改造必须以“这个例子不再生成三步固定模板”为验收条件。

### 为什么不同需求仍会生成固定三步

根因不是模型没有识别出需求差异，而是识别结果没有真正进入差异化生成链路。

当前流程大致是：

1. `_classify_task_tree_intent(...)` 识别需求类型。
2. `_build_goal_oriented_plan_steps(...)` 按类型进入不同分支。
3. 每个分支仍手写返回 3 个叶子节点，阶段基本都是 `analysis`、`implementation`、`verification`。
4. 如果 `_build_task_tree_plan_steps(...)` 从执行计划里拿不到足够有效的步骤，会 fallback 到 `_build_goal_oriented_plan_steps(...)`。
5. 如果任务文本里没有可识别的路由或对象词，`target` 会落成“当前需求”。
6. `_build_task_tree_health_report(...)` 没有检查固定三步模板和“当前需求”泛化主语，因此这种结果会被判为健康。

所以现在的问题可以更准确地表述为：系统“识别了类型”，但“没有按类型生成不同结构”；系统“有健康检查”，但“没有把模板化计划判为不健康”。

必须避免的误解：

- 只更新这份文档或提示词，不会让后端生成器自动变好。
- 只要求 AI 在回答里“不要三步模板”，也不能保证任务树接口不再生成三步。
- 只在前端隐藏泛化节点，也不能解决 requirement 记录、恢复续跑和工作总结继续使用错误任务树的问题。
- 真正的修复必须落在后端生成器、健康检查、自动重建和回归测试上。

## 目标

让统一查询 MCP 入口成为项目执行的唯一规范主链：

- 不同需求生成不同结构的任务树。
- 每个需求从一开始就有本地 requirement 对象和 canonical session 状态。
- 停止、重启、压缩上下文后，可以从同一个 chat_session_id / session_id 恢复。
- 总结工作内容时，优先呈现“完成了什么、改了什么、怎么验证、风险是什么、下一步是什么”，而不是工具日志。
- 远程 MCP 记录、本地 requirement、任务树节点和用户可见输出保持一致。
- 修改完成后，任务树不再固定 3 个叶子节点；除非任务本身确实很小，否则应按任务类型生成 4 到 7 个有对象、有动作、有验收口径的节点。

### 计划执行完后用户能得到什么

从需求记录功能角度看，执行完后用户得到的不是“更长的聊天总结”，而是一套可恢复、可审计、可继续执行的需求记录主链。

每次用户提出需求后，应形成一条稳定需求记录，至少包含：

- 需求标题和 root_goal。
- `chat_session_id`、`session_id`、任务树 session id。
- 当前任务节点和全部任务分支。
- 每个节点的状态、验证结果和完成摘要。
- 本轮改动文件、验证命令、风险和下一步。
- 本地 requirement 文件路径和 query-mcp canonical 状态。
- 远程同步状态、pending_outbox 和失败原因。

用户在需求记录列表或详情里应该能直接判断：

- 这个需求现在是排队、等待用户、执行中、验证中、已完成、失败，还是可恢复。
- 当前卡在哪个具体节点，而不是只看到“分析/实现/验证”。
- 本轮到底做了什么、改了什么、怎么验证、还有什么风险。
- 如果中断或换新会话，应该从哪个 `chat_session_id`、`session_id` 和 `current_task_node` 继续。
- 如果同一需求后来被修复，应能看到原始需求和修复轮次，而不是散落成多条无关聊天。

修改完成后的直观差异：

- 现在：不同实现型需求经常都显示 3 个泛化节点，需求记录只能粗略说明“做过一轮任务”。
- 修改后：不同需求会生成不同计划结构，需求记录能成为项目执行台账。

## 当前现状

本地统一查询 MCP 工作流技能已经存在：

- /Volumes/work_mac_1_5T/self/ai-employee/.ai-employee/skills/query-mcp-workflow/SKILL.md
- /Volumes/work_mac_1_5T/self/ai-employee/.ai-employee/skills/query-mcp-workflow/manifest.json

该技能已经约束了几个关键原则：

- 执行前读取 query://usage-guide 和 query://client-profile/codex。
- 当前工作区必须初始化 .ai-employee/query-mcp/ 与 .ai-employee/requirements/<project_id>/。
- requirement 本地对象必须在需求开始时创建，不能等结束后补写。
- 多轮任务必须固定复用同一个 chat_session_id 与 session_id。
- 中断恢复顺序为 bind_project_context -> resume_work_session -> summarize_checkpoint。
- 如果宿主暴露任务树工具，必须用工具推进状态和验证结果，不能只用自然语言说完成。

问题在于：这些规则更多是“执行规范”，还不足以保证任务树生成质量、恢复摘要质量和用户总结体验。入口需要进一步成为“生成、恢复、总结”的产品契约。

## 改造范围

### 1. MCP 入口工作流

目标：把统一查询 MCP 入口从“工具调用顺序说明”升级为“项目执行状态机”。

需要明确每次需求进入时的主链：

1. 读取使用说明和客户端画像。
2. 以当前 CLI 工作区为准初始化本地状态目录。
3. 检查并复用本地 query-mcp-workflow 技能。
4. 根据 project_id / chat_session_id 绑定项目上下文。
5. 创建或恢复本地 requirement 对象。
6. 启动或恢复 work_session。
7. 生成任务树前先识别需求类型、对象、交付形态和风险。
8. 生成任务树后立即做健康检查。
9. 执行中同步维护本地 requirement、MCP 工作事实、任务树节点状态。
10. 收尾时生成面向人的交付报告。

入口不能只依赖提示词约束。后端应提供硬校验：缺少 project_id、chat_session_id、requirement 记录、current_task_node 或 verification_result 时，不允许把任务标记为完成。

### 2. 任务树差异化生成

目标：不同任务应该生成不同节点，而不是统一套模板。

建议按任务类型生成不同计划骨架：

- 查询型：明确查询对象、数据来源、核对方式、输出格式。
- 修复型：复现问题、定位根因、最小修复、回归验证、风险说明。
- 功能型：需求边界、接口/数据模型、实现路径、测试覆盖、交付说明。
- 文档型：信息来源、结构设计、文档写入、读回验证、后续执行建议。
- 部署型：环境检查、构建、发布、健康检查、回滚方案。
- 集成型：鉴权/配置、协议适配、错误处理、联调验证、运维说明。
- 恢复续跑型：读取本地状态、绑定项目上下文、恢复工作事实、定位当前节点、继续执行。

任务树节点标题必须直接描述用户目标，避免出现内部工具名或泛化阶段名。

不理想：

- 分析当前需求
- 完成当前需求
- 验证当前需求

更理想：

- 梳理 MCP 入口状态、requirement 记录和任务树绑定关系
- 补齐任务树差异化生成规则与健康检查
- 验证停止重启后能从 checkpoint 恢复到具体节点

任务树生成后增加健康评分：

- 节点标题是否包含真实对象。
- 是否能看出任务类型。
- 是否包含恢复锚点。
- 是否包含验证方式。
- 是否混入 search_ids、get_manual_content、resolve_relevant_context 等内部工具名。
- 是否每个任务都生成了几乎相同的标题。
- 叶子节点是否永远等于 3。
- 是否出现“当前需求”作为主要对象但没有真实业务词。

健康评分不合格时，必须自动重建或要求模型重新生成，而不是直接展示给用户。

健康检查必须把以下情况判为高风险：

- 叶子节点刚好 3 个，且阶段只有 `analysis`、`implementation`、`verification`。
- 两个及以上节点标题使用“当前需求”作为主要对象。
- 治理、修复、功能、部署、恢复续跑类任务少于 4 个叶子节点。
- 任务树节点没有包含 root_goal 中可识别的对象词。
- 生成结果与本轮需求类型不匹配，但仍被标记为 `safe_to_display=true`。

只要命中这些条件，`task_tree_health` 不能再给 100 分，必须返回 `rebuild_recommended=true` 或 `safe_to_display=false`。

## 完整代码实施计划

### 阶段 A：先补测试，固定失败证据

修改文件：

- `web-admin/api/tests/test_project_chat_task_tree_routes.py`

新增测试 1：治理/工作流类需求不应固定三步。

输入：

```text
补全 MCP 入口工作流与任务树体验调整计划，使其包含可直接实施的任务树生成代码改造方案
```

期望：

- 叶子节点数量至少 5 个。
- 不允许同时只出现 analysis、implementation、verification 三个阶段。
- 节点标题不能包含“当前需求”作为主要对象。
- 节点标题必须至少包含这些对象中的 3 类：MCP 入口、任务树生成、健康检查、恢复续跑、总结体验、测试。

新增测试 2：修复型需求生成修复链路。

输入：

```text
修复 /lark-cli 登录时 queued 被显示成已完成的问题
```

期望节点包含：

- 复现 queued 与已完成冲突
- 定位状态映射或前端展示入口
- 修复 waiting_user_action / queued 展示逻辑
- 增加回归测试
- 验证真实登录链路或模拟状态

新增测试 3：文档型需求生成文档链路。

输入：

```text
把 MCP 入口工作流调整计划写入 docs 目录
```

期望节点包含：

- 确认目标目录和已有文档
- 整理 MCP 入口工作流要点
- 写入 docs 文档
- 读回校对
- 记录后续实施项

新增测试 4：查询型需求保持单节点或短链路，不误拆实现型。

输入：

```text
这个项目有哪些 MCP 工具
```

期望：

- 叶子节点 1 到 2 个。
- 不出现“实现、修复、改造、测试覆盖”。
- 完成后可以归档。

新增测试 5：模板化健康检查。

构造或生成节点：

```text
梳理 当前需求 当前任务链、反馈面和状态绑定
完成 当前需求 的稳定性补强与反馈透出
验证任务连续性、健康反馈和收尾结果
```

期望：

- `task_tree_health.issue_count > 0`
- `rebuild_recommended == true`
- issue code 包含 `generic_three_step_template` 或 `generic_current_requirement_subject`

### 阶段 B：改生成器，不再返回固定三步

修改文件：

- `web-admin/api/services/chat/project_chat_task_tree.py`

重点修改函数：

- `_build_goal_oriented_plan_steps(task_text, max_steps=6)`
- `_build_task_tree_plan_steps(task_text, project_id, max_steps=6)`
- `_build_task_tree_health_report(session)`
- `ensure_task_tree(...)`

建议新增函数：

```python
def _extract_task_subjects(task_text: str) -> list[str]:
    """提取任务树节点应使用的真实对象词，避免只写当前需求。"""
```

```python
def _build_intent_specific_plan_steps(
    task_text: str,
    *,
    detected_intent: str,
    max_steps: int,
) -> list[dict[str, str]]:
    """按任务类型生成 1 到 7 个差异化节点。"""
```

```python
def _is_generic_three_step_plan(steps: list[dict[str, str]]) -> bool:
    """识别分析/实现/验证三段式模板。"""
```

```python
def _repair_generic_plan_steps(
    task_text: str,
    steps: list[dict[str, str]],
    *,
    detected_intent: str,
    max_steps: int,
) -> list[dict[str, str]]:
    """当生成结果仍模板化时，用任务类型和对象词重建。"""
```

具体生成策略：

1. 查询型：1 到 2 个节点。
2. 文档型：4 到 5 个节点。
3. 修复型：5 到 6 个节点。
4. 功能型：5 到 7 个节点。
5. 部署型：5 到 7 个节点。
6. 恢复续跑型：5 到 6 个节点。
7. 治理/工作流型：6 到 7 个节点。

改造要求：

- `_build_goal_oriented_plan_steps(...)` 不能再用“每个类型返回三步”的写法。
- `_build_task_tree_plan_steps(...)` fallback 到本地生成器时，也必须得到差异化步骤。
- `target = route_path or "当前需求"` 只能作为极端兜底，不允许成为多数任务节点的主要对象。
- 如果对象词提取失败，应从 root_goal 中提取关键词，或触发健康检查要求重建。
- 阶段字段可以仍使用 analysis、implementation、testing、verification、handoff 等，但节点数量和标题必须按任务类型变化。

治理/工作流型示例输出：

```python
[
    {"step": "定位任务树三段式模板的生成入口", "phase": "analysis"},
    {"step": "提取 MCP 入口、任务树生成、恢复续跑和总结体验的对象词", "phase": "analysis"},
    {"step": "改造 _build_goal_oriented_plan_steps 为任务类型差异化生成", "phase": "implementation"},
    {"step": "增加 generic_three_step_template 健康检查", "phase": "implementation"},
    {"step": "补充不同需求类型的任务树生成回归测试", "phase": "testing"},
    {"step": "验证新任务不会再生成固定三步模板", "phase": "verification"},
]
```

修复型示例输出：

```python
[
    {"step": "复现 /lark-cli 登录 queued 与已完成状态冲突", "phase": "analysis"},
    {"step": "定位任务状态映射和 Execution Trace 展示入口", "phase": "analysis"},
    {"step": "修复 queued / waiting_user_action 的完成态判断", "phase": "implementation"},
    {"step": "隐藏 queued 阶段无意义 stdout/stderr 噪音", "phase": "implementation"},
    {"step": "补充登录等待状态的路由或组件回归测试", "phase": "testing"},
    {"step": "验证授权链接出现、等待中、完成后三种状态", "phase": "verification"},
]
```

文档型示例输出：

```python
[
    {"step": "确认 docs 目标目录和已有相关文档", "phase": "analysis"},
    {"step": "整理 MCP 入口工作流、任务树和恢复续跑要点", "phase": "analysis"},
    {"step": "写入统一查询 MCP 入口工作流调整计划文档", "phase": "implementation"},
    {"step": "读回文档并校对计划完整性", "phase": "verification"},
    {"step": "记录后续代码实施文件和验收标准", "phase": "handoff"},
]
```

### 阶段 C：健康检查拦截模板化结果

修改 `_build_task_tree_health_report(session)`。

新增 issue：

- `generic_three_step_template`
- `generic_current_requirement_subject`
- `insufficient_intent_specific_nodes`
- `missing_task_subject`

判定规则：

- 叶子节点刚好 3 个，且 phase 分别是 analysis / implementation / verification，判为可疑。
- 两个以上节点标题包含“当前需求”，判为可疑。
- 节点标题没有包含 root_goal 中的有效对象词，判为可疑。
- 治理/工作流/修复/功能/部署类任务叶子节点少于 4 个，判为可疑。
- 查询型任务超过 2 个且包含实现类词，判为误拆。
- 如果一棵任务树同时命中固定三步和“当前需求”泛化主语，必须直接判为高风险。

health report 行为：

- 高风险模板化：`safe_to_display = False`，`rebuild_recommended = True`。
- 中风险模板化：允许展示，但记录 evolution sample。

### 阶段 D：ensure_task_tree 自动修复

修改 `ensure_task_tree(...)` 或其调用的生成流程。

流程：

1. `build_task_tree_session(...)` 生成初版。
2. 立即调用 `_build_task_tree_health_report(session)`。
3. 如果 `rebuild_recommended == True` 且原因是模板化：
   - 调用 `_repair_generic_plan_steps(...)` 重建 steps。
   - 重新构造 session.nodes。
   - 保存 evolution sample，`rebuild_successful=True`。
4. 再次 health check。
5. 如果仍不合格，保留但 `safe_to_display=False`，前端应提示“任务树需要重新生成”。

### 阶段 E：同步更新 query-mcp-workflow 技能

修改文件：

- `.ai-employee/skills/query-mcp-workflow/SKILL.md`

补充规则：

- 任务树节点不得固定为三段式。
- 生成任务树前必须识别任务类型和对象词。
- 生成后如果节点标题里仍以“当前需求”为主语，必须重建。
- 查询型任务保持短链路；实现型任务必须包含真实实现对象和验证对象。
- 恢复型任务必须包含恢复锚点：chat_session_id、session_id、current_task_node、requirement 路径。

### 阶段 F：运行验证

至少运行：

```bash
python -m pytest web-admin/api/tests/test_project_chat_task_tree_routes.py -q
python -m pytest web-admin/api/tests/test_project_mcp_presence.py -q
python -m pytest web-admin/api/tests/test_unit.py -q -k 'task_tree or query_mcp or work_session'
```

如果改动涉及前端状态展示，再运行对应前端测试或构建命令。

## 预期修改后的效果

用户问：

```text
补全 MCP 入口工作流与任务树体验调整计划，使其包含可直接实施的任务树生成代码改造方案
```

修改前可能生成：

```text
1. 梳理 当前需求 当前任务链、反馈面和状态绑定
2. 完成 当前需求 的稳定性补强与反馈透出
3. 验证任务连续性、健康反馈和收尾结果
```

修改后应生成：

```text
1. 定位任务树三段式模板的生成入口
2. 提取 MCP 入口、任务树生成、恢复续跑和总结体验的对象词
3. 改造任务类型差异化生成策略
4. 增加三段式模板健康检查与自动重建
5. 补充不同需求类型的任务树生成回归测试
6. 验证新任务树不再固定为三步模板
```

这才算真的解决问题。

## 本地 requirement 与 canonical 状态

目标：每个需求从开始就有一个可恢复的本地对象。

规范路径：

- .ai-employee/query-mcp/active-sessions/<chat_session_id>.json
- .ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json
- .ai-employee/requirements/<project_id>/<chat_session_id>.json

requirement 对象至少保留：

- workflow_skill
- record_path
- storage_scope
- task_tree
- current_task_node
- task_branches
- history
- session_id
- chat_session_id
- project_id
- root_goal
- latest_status
- phase
- step
- changed_files
- verification
- risks
- next_steps
- sync_status
- pending_outbox

关键原则：

- 本地 requirement 和 active-sessions 是当前 CLI 工作区恢复的锚点。
- 远程 MCP 写入成功不能替代本地 requirement。
- .ai-employee/query-mcp/active/<project_id>.json 只允许作为历史遗留指针只读恢复，禁止新写，不能作为当前窗口状态。
- 不能新写 current-session.json、chat_session_id.txt、session_id.txt、session.env 等 legacy 状态文件。
- 如果远程回写失败，要写 pending_outbox 和 sync_status，而不是静默跳过。

## 停止重启与恢复续跑

目标：任务中断后，不是“重新猜”，而是按状态恢复。

恢复流程固定为：

1. 从当前入口传入的 chat_session_id 或 .ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json 定位目标会话；只有历史恢复时才只读参考 .ai-employee/query-mcp/active/<project_id>.json。
2. 从 active-sessions/<chat_session_id>.json 读取 session_id、root_goal、current_node。
3. 从 requirements/<project_id>/<chat_session_id>.json 读取 task_tree、history、changed_files、verification、risks、next_steps。
4. 调用 bind_project_context 重新绑定项目和聊天会话。
5. 调用 resume_work_session 拉取服务端工作轨迹。
6. 调用 summarize_checkpoint 生成恢复摘要。
7. 调用 get_current_task_tree 核对当前节点是否属于当前问题。
8. 如果任务树明显挂错，创建新的 chat_session_id 并重新绑定。
9. 如果任务树正确，继续当前节点，而不是重头执行。

恢复摘要面向执行者要包含：

- 当前目标是什么。
- 当前阶段是什么。
- 当前节点是什么。
- 已完成哪些节点。
- 最近改过哪些文件。
- 已验证什么。
- 还缺什么验证。
- 风险和阻塞是什么。
- 下一步应该直接做什么。

## 工作总结与交付报告

目标：总结要像项目经理交付，不像日志转写。

推荐输出结构：

- 结论：本轮是否完成，完成到什么程度。
- 完成项：按用户目标列出，不按工具调用列出。
- 改动文件：只列真实变更文件，区分本轮改动和历史脏改动。
- 验证结果：列命令、结果、覆盖范围。
- 风险：说明未验证、依赖、兼容性、前端/后端剩余问题。
- 下一步：可继续执行的具体动作。
- 恢复信息：chat_session_id、session_id、current_task_node、requirement 文件路径。

避免输出：

- 只说“已完成 1 项”。
- 只贴工具名称和状态。
- 把 queued、pending、in_progress 直接展示给用户但不解释含义。
- 在验证没完成时提前说“最终完成”。
- 把历史残留进程或旧会话测试说成当前会话结果。

## 前端展示和用户反馈

目标：用户在界面上看到的状态必须和真实任务状态一致。

需要区分：

- Agent 已创建任务。
- 后台任务排队中。
- 等待用户操作。
- 正在执行。
- 等待外部系统返回。
- 已完成并验证。
- 失败并可重试。
- 已中断但可恢复。

例如 /lark-cli 登录这类任务，不能顶部显示“本轮执行已结束 / 已完成”，正文又说 queued。更合理的是：

- 标题：等待授权流程启动。
- 状态：任务已创建，尚未完成。
- 下一步：系统会继续监听；出现授权链接后展示给用户。
- Debug 信息：退出码、stdout、stderr 只放到可展开详情里。

## 后端校验与状态机

目标：把规范落到代码里，不能全靠提示词。

建议增加或强化这些校验：

- ensure_task_tree 生成后必须进行 health check。
- complete_task_node_with_verification 必须校验 verification_result 非空。
- 父节点完成前必须确认所有子节点完成。
- start_work_session 必须写入 canonical 本地状态和 requirement。
- save_work_facts / append_session_event 必须带同一条 chat_session_id / session_id。
- 恢复时如果 local requirement、MCP task tree、work_session 三者目标不一致，必须暴露冲突，不允许静默选择一个。
- 查询型任务不能被误拆成实现型任务树。
- 实现型任务不能只有“分析、实现、验证”三个泛化节点。

## 验收标准

这轮改造完成后，应能满足：

- 用户提出不同需求时，任务树节点能看出真实差异。
- 任意任务执行到一半停止后，新会话能恢复到具体节点。
- requirement 文件和 query-mcp canonical 状态始终存在且一致。
- 总结能清楚说明完成项、文件、验证、风险、下一步。
- 前端不再把 queued / waiting_user_action 显示成已完成。
- 内部工具调用不会被误展示成任务树节点。
- MCP 回写失败时不会静默成功，而是记录 sync_status 和 pending_outbox。
- 对治理、修复、功能、部署、恢复续跑类需求，不再生成固定 3 个叶子节点。
- 对文档型需求，任务树必须包含“确认目录/资料、整理内容、写入文档、读回校对、记录后续项”这类文档动作。
- 对查询型需求，任务树不能膨胀成实现任务。
- 新建一条“修改 docs/统一查询MCP入口工作流与任务树体验调整计划.md”这类文档需求时，不能再生成“梳理 当前需求 / 完成 当前需求 / 验证...”。
- 如果仍生成固定三步模板，`task_tree_health.issue_count` 必须大于 0，且 `rebuild_recommended` 必须为 true。
- 需求记录详情必须能展示当前节点、节点验证结果、改动文件、风险、下一步和恢复锚点。
- 中断后从需求记录恢复时，必须能定位到同一个 requirement、同一个 task tree 和同一个 work_session，而不是重建一条无关记录。

## 需要优先修改的文件方向

实际文件需在实施前再次核对，但优先关注：

- .ai-employee/skills/query-mcp-workflow/SKILL.md
- web-admin/api/services/chat/project_chat_task_tree.py
- web-admin/api/services/chat/project_chat_execution_service.py
- web-admin/api/services/work_session_store.py 或同类工作轨迹存储模块
- web-admin/api/routers/projects.py
- web-admin/api/tests/test_project_chat_task_tree_routes.py
- web-admin/api/tests/test_project_mcp_presence.py
- web-admin/api/tests/test_unit.py
- 前端负责 Execution Trace / 任务树 / 交付总结展示的组件

## 备注

这份文档记录完整实施计划，不代表代码已经完成。下一步如果开始实施，应先读取上述文件的当前 diff 和测试现状，避免覆盖工作区已有未提交改动。

最优先的代码动作是：先补 `test_project_chat_task_tree_routes.py` 中关于固定三步模板的失败测试，再改 `project_chat_task_tree.py` 的 `_build_goal_oriented_plan_steps` 和健康检查，让当前这类 MCP 工作流任务不再生成固定三步。
