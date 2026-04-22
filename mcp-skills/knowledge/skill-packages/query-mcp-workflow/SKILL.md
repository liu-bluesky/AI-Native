# 统一查询 MCP 工作流

## 作用

当项目依赖统一查询 MCP 来处理需求、恢复执行、推进任务树并形成可验证交付时，使用这个技能。

这个技能是工作流说明，不是 CLI 包装器。它负责约束 AI 如何一致地使用现有 MCP 工具和系统 API；它不能替代后端校验。

## 初始化

1. 执行前先读取统一查询 MCP 使用说明。
2. 如果当前是 Codex 这类编码型客户端，再读取 Codex 客户端画像。
3. 执行前先检查当前项目根目录下是否已有本地 `query-mcp-workflow` 技能；如果缺失，再通过 MCP 从服务端技能库同步或创建到本地；如果已存在，则直接复用。
4. 通用场景下，工作流技能默认位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`。
5. 优先读取本地同步副本；包内首先检查 `SKILL.md` 和 `manifest.json`。
6. 只有当前仓库本身是这个工作流技能的 system source repo 时，才使用 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为源事实位置。
7. 执行前先以当前 CLI 工作区为准补齐 `.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/active/`、`.ai-employee/query-mcp/session-history/` 与 `.ai-employee/requirements/<project_id>/`；不要把其他子目录里的历史状态视为当前工作区已初始化。

## 技能类型

- `更新`：当任务是修改提示词、`SKILL.md`、`manifest.json`、模板、打包内容或同步规则时使用。
- `使用`：当任务是执行需求、恢复进度、推进任务树、排查问题、验证结果或交付时使用。

## 必需工作流

1. 仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或需要跨项目检索时，才调用 `search_ids(keyword="<用户原始问题>")`；不要把它当作每次必走前置步骤。
2. 项目内执行前先读取项目手册内容。
3. 实现型任务在改代码前，先执行任务分析、相关上下文聚合和执行计划生成。
4. 优先在项目本地推进任务：先完成分析、改动、验证和本地记录，再通过 MCP 把任务树状态、工作事实和交付结果同步回服务端。
5. requirement 本地对象必须在需求开始时创建，且在分析、实现、验证每一步推进时持续更新；禁止等到需求结束后再一次性补写。
6. 多轮任务必须固定复用同一个 `chat_session_id` 与同一个 `session_id`。
7. 中断后继续执行时，按 `bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)` 的顺序恢复。
8. 不要把自然语言进度当成任务闭环。只要宿主暴露了任务树工具，就必须写入工具可见的状态与验证结果。
9. 如果远程回写失败、延迟或只把状态写到子目录 fallback，本地 requirement 和 query-mcp canonical 状态仍然是当前 CLI 工作区的权威记录；应保留 `sync_status`/outbox，而不是跳过本地直接记远程。
10. 当修改 query-mcp 提示词、运行时契约、预览文案或技能包时，必须同步更新对应提示词入口和回归测试，而不是只改一个位置。

## 三层契约

技能层负责说明 AI 应该怎么做。

工具/脚本层负责把重复步骤封装起来，降低对提示词细节的依赖。

后端校验层必须负责约束任务归属、会话连续性、状态流转是否合法，以及验证结果是否齐全。

## 面向用户的反馈要求

如果存在可恢复任务，要明确告诉用户“可以继续”，并指出当前阶段或下一步动作。

如果只发现孤立的本地状态或 MCP 状态，要明确告诉用户“找到了历史状态，但在恢复项目/会话绑定之前，不能保证它一定属于当前活动任务”。

如果当前宿主拿不到任务树工具，应明确说明“任务树闭环未完成”，而不是直接宣称任务已完成。

## 边界

- 如果本地工作流技能已经存在且可用，不要重复创建。
- 不要创建或依赖临时的 legacy 会话文件；应使用 canonical 的 query-mcp 状态文件路径或后端状态服务。
- 不要把“远程已记录”当作“本地 requirement 已创建”；只要当前 CLI 工作区缺少 canonical 文件，就视为本地初始化未完成。
