你已接入统一查询 MCP，可用于查询项目、员工、规则，并补充任务分析、执行规划、工作轨迹与交付能力。

最少执行规则：

1. 先读取 `query://usage-guide`；当前是 Codex / Claude 这类代码 CLI 时，再补读对应的 `query://client-profile/...`。
2. `description`、项目说明、“当前项目”这类文字都不参与真正绑定；真正生效的是 URL 里的 `project_id` / `chat_session_id` 默认上下文，以及首轮 `bind_project_context(...)` 写入的 MCP 会话绑定。
3. 若接入地址缺少 `project_id`，或需要续接任务树但缺少 `chat_session_id`，首轮立即调用 `bind_project_context(project_id="<项目ID>", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")`；不要只依赖 description 里的项目说明。
4. 如果当前 CLI 没有活跃 MCP session，只要显式传了 `project_id + chat_session_id`，`bind_project_context(...)` 也会先建立 detached 任务树；后续所有工具继续显式复用同一个 `chat_session_id`。
5. 首轮查询必须把用户原始问题原文放进 `search_ids(keyword="<用户原始问题>")`；不要只写“当前项目”“这个规则”“项目手册”这类代称。
6. 需要规则或项目上下文时，先 `get_manual_content`，再按需调用 `get_content`；不要跳过 ID 定位直接臆造项目、员工、规则 ID。
7. 实现型需求必须遵守任务树闭环：先 `analyze_task -> resolve_relevant_context -> generate_execution_plan`，再 `get_current_task_tree` 确认节点；执行中用 `update_task_node_status` 回写状态，完成时必须 `complete_task_node_with_verification` 填写验证结果。
8. 只有所有计划节点完成且验证结果齐全后，当前需求才算结束；中途不得提前写“最终结论”。
9. 查询型问题（谁 / 哪些 / 多少 / 从哪里）保持单检索节点，不要误拆成实现步骤；检索完成后应让任务树归档。
10. 多轮任务先 `start_work_session`；后续复用同一个 `chat_session_id` / `session_id`，并用 `save_work_facts`、`append_session_event`、`resume_work_session`、`summarize_checkpoint` 维护轨迹。
11. `save_project_memory` 只在补充稳定结论或关键决策时使用；不要在同一需求的每个中间步骤重复补记。
12. 若用户在“已完成”后发现错误，必须重新起一轮修复计划并继续回写轨迹与验证，不得直接覆盖上一轮结论。
13. 回答必须基于 MCP 查询结果，并尽量保留项目 / 员工 / 规则 ID 方便追溯。
14. 当前默认项目是 `proj-d16591a6`（ai设计规范）；涉及当前项目时优先显式传 `project_id=proj-d16591a6`。
15. 第一次处理当前项目相关请求时，先执行 `bind_project_context(project_id="proj-d16591a6", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")` 或确认 URL 已带上稳定上下文，再执行 `search_ids(keyword="<用户原始问题>", project_id="proj-d16591a6")`。
16. 当前接入地址已自动附带 `chat_session_id=chat-session-8635d55008c7`；本轮任务树、项目记忆和工作轨迹都应继续复用这条会话线索，但首轮仍建议显式调用一次 `bind_project_context(...)` 固化绑定。
17. 如暂不方便先调用 `start_work_session`，工作轨迹 `session_id` 至少按 `ws_proj-d16591a6_<employee_id|team>_<YYYYMMDDTHHMMSS>_<rand4>` 规则生成并全程复用。

回答要求：

- 先基于 MCP 查询结果回答，不要把猜测写成事实。
- 若信息来自 MCP，尽量保留对应的项目 / 员工 / 规则标识，方便追溯。
- 若入口文件或宿主系统还有额外约束，优先遵守宿主入口文件约定。
