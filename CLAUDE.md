你已接入统一查询 MCP，可用于查询项目、员工、规则，并补充任务分析、执行规划、工作轨迹与交付能力。

最少执行规则：

1. 先读取 `query://usage-guide`；当前是 Codex / Claude 这类代码 CLI 时，再补读对应的 `query://client-profile/...`。
2. `description`、项目说明、“当前项目”这类文字都不参与真正绑定；真正生效的是 URL 里的 `project_id` / `chat_session_id` 默认上下文，以及首轮 `bind_project_context(...)` 写入的 MCP 会话绑定。
3. 若接入地址缺少 `project_id`，或需要续接任务树但缺少 `chat_session_id`，首轮立即调用 `bind_project_context(project_id="<项目ID>", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")`；不要只依赖 description 里的项目说明。
4. 每个 CLI 进程首次接入时，都应自行生成唯一的 `chat_session_id`，推荐格式：`cli.proj-d16591a6.<YYYYMMDDTHHMMSS>.<host6>.<pid>.<rand6>`；同一进程整轮任务内固定复用，新开的并行 CLI 或新的独立任务都必须重新生成，不要共用。
   4.1 这个 `chat_session_id` 要立即持久化；如能解析项目工作区，优先写到项目目录 `.ai-employee/query-mcp/`，否则再退回当前 CLI 自己的本地存储。CLI 中断、重启或网络重连后，先恢复本地值，再继续挂回同一条任务树。
5. 如果当前 CLI 没有活跃 MCP session，只要显式传了 `project_id + chat_session_id`，`bind_project_context(...)` 也会先建立 detached 任务树；后续所有工具继续显式复用当前进程自己生成的同一个 `chat_session_id`。
6. 首轮查询必须把用户原始问题原文放进 `search_ids(keyword="<用户原始问题>")`；不要只写“当前项目”“这个规则”“项目手册”这类代称。
7. 需要规则或项目上下文时，先 `get_manual_content` 读取项目/员工手册，再按需调用 `get_content`；不要跳过 ID 定位直接臆造项目、员工、规则 ID。
8. 项目型问题优先使用项目绑定的员工、规则和技能；先判断项目内现成能力能否闭环，只有项目能力不足时才自行补足。
9. 每次新请求进入分析、实现或排查前，重新获取与当前任务直接相关的规则正文；不要只看规则标题，也不要把无关项目规则机械套用到所有请求。
10. 实现型需求必须遵守任务树闭环：先 `analyze_task -> resolve_relevant_context -> generate_execution_plan`，再 `get_current_task_tree` 确认节点；执行中用 `update_task_node_status` 回写状态，完成时必须 `complete_task_node_with_verification` 填写验证结果。
11. 只有所有计划节点完成且验证结果齐全后，当前需求才算结束；中途不得提前写“最终结论”。
12. 查询型问题（谁 / 哪些 / 多少 / 从哪里）保持单检索节点，不要误拆成实现步骤；检索完成后应让任务树归档。
13. 多轮任务先 `start_work_session`；后续复用同一个 `chat_session_id` / `session_id`，并用 `save_work_facts`、`append_session_event`、`resume_work_session`、`summarize_checkpoint` 维护轨迹。
    13.1 `start_work_session` 返回的服务端 `session_id` 也要立刻持久化；如能解析项目工作区，优先写到项目目录 `.ai-employee/query-mcp/`，否则再退回当前 CLI 自己的本地存储。后续恢复、补轨迹和检查点总结都用这一条值，不要每次新生成。
    13.2 CLI 中断后的标准恢复顺序是：恢复本地 `chat_session_id/session_id` -> `bind_project_context(...)` -> `resume_work_session(...)` -> `summarize_checkpoint(...)` -> 紧接着继续当前任务；如果项目工作区不可解析，则恢复来源应是当前 CLI 自己的本地存储，而不是共享仓库根目录。
14. `save_project_memory` 只在补充稳定结论或关键决策时使用；不要在同一需求的每个中间步骤重复补记。
15. 若用户在“已完成”后发现错误，必须重新起一轮修复计划并继续回写轨迹与验证，不得直接覆盖上一轮结论。
16. 回答必须基于 MCP 查询结果，并尽量保留项目 / 员工 / 规则 ID 方便追溯。
17. 当前默认项目是 `proj-d16591a6`（ai设计规范）；涉及当前项目时优先显式传 `project_id=proj-d16591a6`。
18. 第一次处理当前项目相关请求时，先执行 `bind_project_context(project_id="proj-d16591a6", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")` 或确认 URL 已带上稳定上下文，再执行 `search_ids(keyword="<用户原始问题>", project_id="proj-d16591a6")`。
19. 当前页面已有 `chat_session_id=chat-session-8635d55008c7`，这只适合明确要续接当前这轮任务时手动复用；如果是新开的或并行 CLI，请改为自己生成新的 `chat_session_id`，不要直接共用。
20. 如暂不方便先调用 `start_work_session`，工作轨迹 `session_id` 至少按 `ws_proj-d16591a6_<employee_id|team>_<YYYYMMDDTHHMMSS>_<rand4>` 规则生成并全程复用。
21. 当前项目如需在前端直接查看误判样本与高频问题，可读取 `/api/projects/proj-d16591a6/chat/task-tree/evolution-summary?chat_session_id=<聊天会话ID>`。

回答要求：

- 先基于 MCP 查询结果回答，不要把猜测写成事实。
- 若信息来自 MCP，尽量保留对应的项目 / 员工 / 规则标识，方便追溯。
- 若入口文件或宿主系统还有额外约束，优先遵守宿主入口文件约定。
