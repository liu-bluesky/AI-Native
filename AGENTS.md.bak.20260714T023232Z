你已接入统一查询 MCP。

详细规则不要直接内联到宿主提示词；但开始执行前必须按需读取这些资源：
- `query://usage-guide`
- `query://client-profile/codex`（Codex CLI）

强制接入步骤：
1. 先读取 `query://usage-guide`；当前客户端是 Codex CLI，再读取对应画像 `query://client-profile/codex`。
1.1 `list_mcp_resources` 只用于发现资源目录，不等于读取资源；同一轮最多调用一次。资源 URI 已知时，必须直接用 `read_mcp_resource` 读取 `query://usage-guide` 和当前客户端对应的 `query://client-profile/...`，禁止反复调用 `list_mcp_resources`。
1.2 对“有几个员工 / 有哪些员工 / 有哪些工具 / 有哪些规则”这类简单查询，且 `project_id` 已明确时，直接调用对应业务工具（如 `list_project_members(project_id=...)`、`list_project_proxy_tools(...)`），不要为了满足 bootstrap 机械列资源目录。
2. 初始化不是只检查技能；先以当前 CLI 工作区为准，显式初始化本地 `.ai-employee/`，至少确保 `.ai-employee/skills/`、`.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/session-history/` 与 `.ai-employee/requirements/<project_id>/` 可用；canonical session 状态只使用 `active-sessions/<chat_session_id>.json` 与 `session-history/<project_id>__<chat_session_id>.json`。
3. 再检查 `.ai-employee/skills/query-mcp-workflow/` 是否已存在；缺失时先通过 MCP 从服务端技能库同步或创建到当前工作区，已存在则直接复用，禁止重复创建。
4. 通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；核心文件优先读取本地副本中的 `SKILL.md` 与 `manifest.json`。只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。
5. 若系统曾把 `.ai-employee` 或 `query-mcp-workflow` 隐式落到其他子目录，只能视为历史状态，不能替代当前 CLI 工作区初始化；当前入口仍要在当前工作区补齐。
6. 若当前任务是更新工作流规范或技能包，优先在本地技能副本、提示词模板和同步策略上修改；只有本地缺失或需要回源比对时，才从服务端技能库同步。
6.1 若用户明确要求“更新提示词”“同步提示词”“刷新 AGENTS.md”或类似操作，且 `project_id`、`chat_session_id` 与当前 CLI 工作区明确，直接调用 `sync_query_mcp_cli_prompt_to_local_file(project_id=<当前项目>, chat_session_id=<当前会话>, workspace_path=<当前 CLI 工作区>, target_file="AGENTS.md", backup=true, dry_run=false)`，用服务端渲染的 `runtime.cli_prompt` 覆盖当前项目根目录提示词文件；不要只预览或只口头说明。完成后保留工具返回的 `target_file`、`backup_file`、`content_hash` 作为验证记录；若 workspace_path 不明确或目标路径不在当前工作区，先说明阻塞。
7. 实现型需求优先调用 `start_project_workflow(...)` 作为固定入口；若宿主暂不适合走固定入口，至少按 `search_ids -> get_manual_content -> analyze_task -> resolve_relevant_context -> generate_execution_plan` 的顺序补齐前置步骤。
8. 仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或需要跨项目检索时，再调用 `search_ids(keyword="<用户原始问题>")`；已明确当前项目且在项目内执行时可直接读取上下文或进入本地实现，不要为满足流程机械检索。
9. 不要依赖 description、项目说明或“当前项目”文字做绑定；如需项目绑定或续接任务树，显式调用 `bind_project_context(...)`。
10. 当前任务先在项目本地推进：先在工作区完成分析、改动、验证和本地记录，再通过 MCP 回写任务树、工作事实、交付结论或记忆到服务端。
11. 每个需求必须维护 1 个本地 requirement 对象；项目工作区可解析时，写入 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。需求记录只保存需求内容和必要定位字段，不记录任务树、任务节点、执行历史、项目智能体上下文或其他过程结构。
12. 当前全局清晰度确认阈值为 3/5；先按 1-5 分估计用户需求清晰度。
13. 若只是查询、解释或客服型问题，且目标、对象、范围和预期结果足够清晰、清晰度分数 >= 3，可直接回答；凡涉及开发、实现、修改、写入或其他会改变项目状态的需求，先判断本轮用户是否已经给出明确执行指令；“修复”“开始”“继续”“按这个做”“修改”“执行”“开始改”等表达视为对当前清晰范围的确认，可直接进入执行，不要再次请求一般计划确认。
14. 若清晰度分数 < 3、需求表述模糊、对象或范围不明确，或存在两种及以上合理理解，先输出你的理解、计划摘要和可能误解点，再请求用户确认后再执行；同一轮已确认或用户已明确要求执行后不要重复确认；任何删除、移除、清空、覆盖、部署、发布、外部系统写入、凭据暴露或不可逆操作必须单独说明对象、影响范围和可恢复性，并取得用户明确确认后才能执行。
15. 一旦用户已确认计划或已明确要求执行，后续按已生成计划连续推进到完成；阶段之间只更新任务树、工作事实、验证结果和必要进度，不再停下来请求“是否继续”。只有遇到破坏性/不可逆操作、权限或环境阻塞、需求范围变化、验证无法推进，或必须由用户做业务决策时，才暂停并明确说明阻塞点。
16. 长任务先调用 `start_work_session` 获取 `session_id`，后续复用同一个 `chat_session_id/session_id`，并用 `save_work_facts`、`append_session_event` 维护轨迹。
17. 如宿主支持任务树，`bind_project_context(...)` 后立刻读取 `get_current_task_tree`，核对 `root_goal/title/current_node` 是否属于当前问题；若明显属于旧任务树，停止复用当前 `chat_session_id`，改为新建并持久化新的 `chat_session_id` 后重新绑定。
18. 真正进入执行前，再读取一次 `get_current_task_tree` 确认当前节点；开始节点用 `update_task_node_status`，完成节点必须用 `complete_task_node_with_verification` 补验证结果后再结束。
19. 如果当前宿主拿不到上述任务树工具，只能明确说明“任务树闭环未完成”，不要把自然语言进度当成已闭环。
20. 禁止以兜底、兼容、静默降级或重复写入多份状态来掩盖问题；遇到异常、缺失、路径不一致、状态不一致或接口不匹配时，优先定位并修正根因，收敛到唯一规范入口和 canonical 状态。





























当前接入上下文：
- 默认项目: `proj-cc47efb1`
- 建议把 URL 默认上下文里的 `project_id` 固定为 `proj-cc47efb1`。
- 涉及当前项目时，若项目和对象已明确，可直接 `get_manual_content(project_id="proj-cc47efb1")` 或进入 `start_project_workflow(...)`；仅在缺少 ID 或需要跨项目定位时，再调用 `search_ids(keyword="<用户原始问题>", project_id="proj-cc47efb1")`。
- 若要创建或续接当前项目任务树，优先显式调用 `bind_project_context(project_id="proj-cc47efb1", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")`。
- 当前页面已有 `chat_session_id=chat-session-b571d8f4-d79-clean-deploy`；仅在明确要续接当前任务树时复用，否则新开的并行 CLI 应重新生成自己的 `chat_session_id`。
- `chat_session_id` 生成后要立即持久化；优先写项目目录 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`，并同步维护 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。
- requirement 本地对象与 query-mcp canonical 状态要同时维护；不要只写 session 文件而缺失 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`，但 requirement 文件只记录需求内容。
- 如果自动 bootstrap 把状态写到了别的服务子目录，不能把它当成当前仓库根目录已初始化；入口提示词必须以当前 CLI 工作区为准重新核对。
- 若当前还没有 `session_id`，调用 `start_work_session` 后也要立刻持久化；中断恢复顺序固定为 `bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)`。
- 若项目工作区不可解析，再退回当前 CLI 自己的本地存储；不要在项目工作区写入分叉会话状态文件。

回答要求：
- 先基于 MCP 查询结果回答，不要把猜测写成事实。
- 若信息来自 MCP，尽量保留对应的项目 / 员工 / 规则 ID，方便追溯。
- 若入口文件或宿主系统还有额外约束，优先遵守宿主入口文件约定。