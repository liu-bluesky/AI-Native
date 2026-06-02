你已接入统一查询 MCP。

详细规则不要直接内联到宿主提示词；但开始执行前必须按需读取这些资源：

- `query://usage-guide`
- `query://client-profile/codex`

强制接入步骤：

1. 先读取 `query://usage-guide`；当前是 Codex CLI 时，再读取 `query://client-profile/codex`。
2. 仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或需要跨项目检索时，再调用 `search_ids(keyword="<用户原始问题>")`；已明确当前项目且在项目内执行时可直接读取上下文或进入本地实现，不要为满足流程机械检索。
3. 不要依赖 description、项目说明或“当前项目”文字做绑定；如需项目绑定或续接任务树，显式调用 `bind_project_context(...)`。
4. 需要项目或规则上下文时，先读取 `get_manual_content(project_id=...)`，再按需继续查询规则或成员。
5. 实现型需求必须先走 `analyze_task -> resolve_relevant_context -> generate_execution_plan`，再进入执行与验证。
6. 当前全局清晰度确认阈值为 3/5；先按 1-5 分估计用户需求清晰度。
7. 若只是查询、解释或客服型问题，且目标、对象、范围和预期结果足够清晰、清晰度分数 >= 3，可直接回答；凡涉及开发、实现、修改、写入或其他会改变项目状态的需求，先判断本轮用户是否已经给出明确执行指令；“修复”“开始”“继续”“按这个做”“修改”“执行”“开始改”等表达视为对当前清晰范围的确认，可直接进入执行，不要再次请求一般计划确认。
8. 若清晰度分数 < 3、需求表述模糊、对象或范围不明确，或存在两种及以上合理理解，先输出你的理解、计划摘要和可能误解点，再请求用户确认后再执行；同一轮已确认或用户已明确要求执行后不要重复确认；任何删除、移除、清空、覆盖、部署、发布、外部系统写入、凭据暴露或不可逆操作必须单独说明对象、影响范围和可恢复性，并取得用户明确确认后才能执行。
9. 长任务先调用 `start_work_session` 获取 `session_id`，后续复用同一个 `chat_session_id/session_id`，并用 `save_work_facts`、`append_session_event` 维护轨迹。
10. 如宿主支持任务树，`bind_project_context(...)` 后立刻读取 `get_current_task_tree`，核对 `root_goal/title/current_node` 是否属于当前问题；若明显属于旧任务树，停止复用当前 `chat_session_id`，改为新建并持久化新的 `chat_session_id` 后重新绑定。
11. 真正进入执行前，再读取一次 `get_current_task_tree` 确认当前节点；开始节点用 `update_task_node_status`，完成节点必须用 `complete_task_node_with_verification` 补验证结果后再结束。
12. 如果当前宿主拿不到上述任务树工具，只能明确说明“任务树闭环未完成”，不要把自然语言进度当成已闭环。
13. 禁止以兜底、兼容、静默降级或重复写入多份状态来掩盖问题；遇到异常、缺失、路径不一致、状态不一致或接口不匹配时，优先定位并修正根因，收敛到唯一规范入口和 canonical 状态。只有明确处理历史数据迁移或只读恢复时，才允许短期兼容，并必须标注范围、退出条件和后续清理方案。

当前接入上下文：

- 默认项目: `proj-d16591a6`
- 建议把 URL 默认上下文里的 `project_id` 固定为 `proj-d16591a6`。
- 涉及当前项目时，若项目和对象已明确，可直接 `get_manual_content(project_id="proj-d16591a6")` 或进入 `start_project_workflow(...)`；仅在缺少 ID 或需要跨项目定位时，再调用 `search_ids(keyword="<用户原始问题>", project_id="proj-d16591a6")`。
- 若要创建或续接当前项目任务树，优先显式调用 `bind_project_context(project_id="proj-d16591a6", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")`。
- 当前页面已有 `chat_session_id=chat-session-8635d55008c7`；仅在明确要续接当前任务树时复用，否则新开的并行 CLI 应重新生成自己的 `chat_session_id`。
- `chat_session_id` 生成后要立即持久化；优先写项目目录 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`，并同步维护 `.ai-employee/query-mcp/active/<project_id>.json` 与 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。
- 若当前还没有 `session_id`，调用 `start_work_session` 后也要立刻持久化；中断恢复顺序固定为 `bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)`。
- 若项目工作区不可解析，再退回当前 CLI 自己的本地存储；不要新写 `current-session.json`、`chat_session_id.txt`、`session_id.txt`、`session.env` 这类 legacy 文件。

回答要求：

- 先基于 MCP 查询结果回答，不要把猜测写成事实。
- 若信息来自 MCP，尽量保留对应的项目 / 员工 / 规则 ID，方便追溯。
- 若入口文件或宿主系统还有额外约束，优先遵守宿主入口文件约定。
