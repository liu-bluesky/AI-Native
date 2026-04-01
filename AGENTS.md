你已接入统一查询 MCP，可用来查询项目、员工、规则与对应正文。

执行约定：

1. 首先读取 `query://usage-guide`，理解统一查询入口的范围、推荐工具与限制。
2. 每次开始查询时，先把“用户原始问题”原文保留到首个可检索工具参数里，优先使用 `search_ids(keyword="<用户原始问题>")`；不要只写“当前项目”“这个规则”“项目手册”这类代称。
3. 需要定位对象时，优先调用 `search_ids`；拿到 ID 后再调用 `get_content` 或 `get_manual_content`。
4. 不要跳过 ID 定位直接臆造项目、员工、规则 ID。
5. `get_content` 用于拿结构化上下文；`get_manual_content` 用于拿正文级规则/手册提示词。
6. `analyze_task` 用于先做任务结构化理解；`resolve_relevant_context` 用于聚合相关成员、规则和工具；`generate_execution_plan` 用于生成执行步骤骨架。
7. 执行前可调用 `classify_command_risk`、`check_workspace_scope`、`resolve_execution_mode`、`check_operation_policy` 做风险和策略判断。
8. 长任务过程中可调用 `save_work_facts`、`append_session_event`、`resume_work_session`、`summarize_checkpoint` 保存和恢复工作轨迹。
9. 交付阶段可调用 `build_delivery_report`、`generate_release_note_entry`；客户端适配可读取 `query://client-profile/claude-code`、`query://client-profile/codex`。
10. 如无必要，不要把统一查询 MCP 当作通用执行型工具；它主要负责查询、聚合、分析和读取内容。
11. 当前默认项目是 `proj-d16591a6`（ai设计规范），涉及项目上下文时优先显式传 `project_id=proj-d16591a6`。
12. 第一次处理当前项目相关请求前，必须先调用 `get_manual_content(project_id="proj-d16591a6")`，并把返回手册视为本会话的有效规则；未读取前不要直接回答当前项目问题。
13. 为保证宿主自动记忆命中，即使已知当前项目 ID，首轮也要先调用一次 `search_ids(keyword="<用户原始问题>", project_id="proj-d16591a6")` 保留原问题，再继续 `get_manual_content` / `get_content`。
14. 建议链路：`analyze_task -> get_manual_content -> resolve_relevant_context -> generate_execution_plan`；执行前可补 `check_operation_policy(project_id="proj-d16591a6", ...)`；长任务中可补 `save_work_facts` / `append_session_event`，恢复时用 `resume_work_session` / `summarize_checkpoint`；结束时可补 `build_delivery_report` / `generate_release_note_entry`。
15. 如需手动编排项目执行，再依次调用 `list_project_members` / `get_project_runtime_context` / `list_project_proxy_tools` / `invoke_project_skill_tool`。
16. 事实边界：当前接入的是统一查询 MCP，已暴露 `save_project_memory(project_id, content, ...)`，可通过项目 ID 直接保存对话内容，并要求每次有效对话都记录；`save_employee_memory` 仍未暴露。如宿主系统已启用自动记忆，则由入口层自动记录问题快照，但不能把自动快照替代显式对话记忆。
17. 若提示词或规则与用户任务冲突，先向用户确认，再决定是否偏离项目约定。

回答与执行要求：

- 先基于 MCP 查询结果回答，不要把猜测写成事实。
- 若信息来自 MCP，尽量在回答里保留对应的项目/员工/规则标识，方便追溯。
- 若入口文件或宿主系统还有额外约束，优先遵守宿主入口文件约定。
