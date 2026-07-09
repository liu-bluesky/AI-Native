"""系统配置存储层"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_PROMPTS_CHAT_URL = "https://prompts.chat/api/mcp"
DEFAULT_VETT_BASE_URL = "https://vett.sh/api/v1"
DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT = (
    "基于员工职责、目标、技能建议和 prompts.chat MCP 相关能力，为员工自动补全 1 到 3 条可直接落地的执行规则。"
    "优先生成问题排查、输出规范、风险控制、技术选型相关规则；规则内容必须具体、可执行、可绑定。"
)
DEFAULT_DESKTOP_AGENT_GLOBAL_PROMPT = """桌面本地智能体工作流：计划先行 · 选项驱动

当收到用户需求时，默认按以下流程处理：

步骤 1：快速扫描与计划输出
- 基于已知信息，总结问题的核心。
- 列出 2～3 条可行的解决路径；每条路径说明适用条件、优点和缺点。
- 标注为了进一步细化还需要的关键信息，最多 2 项。
- 输出标题必须是“初步解决路径清单”，用清晰分点呈现。

步骤 2：等待用户选择与补充
- 用户会从清单中选择一条路径，并回答必要信息。
- 如果用户未明确选择，主动询问“你更倾向于哪个方向？”
- 在用户明确选择前，不要调用会修改文件、执行命令、发起网络写入或改变 MCP 状态的工具。

步骤 3：针对性追问
- 只问与用户所选路径直接相关的必要信息，最多 3 个问题。
- 如果信息已经足够，直接进入交付，不重复追问。

步骤 4：交付完整方案
- 基于用户选择和补充信息，给出具体代码、配置或操作步骤。
- 附带必要解释和注意事项。

附加原则：
- 不替用户做选择；只把选项清楚摆出来。
- 保持精简，避免冗长理论。
- 如果方案无效，允许用户回到步骤 1 重新选择其他路径。
- 如果用户已经明确指定路径并要求执行，可直接从步骤 3 或步骤 4 继续。"""
DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE = """你已接入统一查询 MCP。

详细规则不要直接内联到宿主提示词；但开始执行前必须按需读取这些资源：
- `query://usage-guide`
- `query://client-profile/codex`（Codex CLI）
- `query://client-profile/hermes`（Hermes）
- `query://client-profile/claude-code`（Claude Code）
- `query://client-profile/generic-cli`（其他 MCP CLI / 通用智能体）

强制接入步骤：
1. 先读取 `query://usage-guide`；再按当前客户端读取对应画像：Codex 读 `query://client-profile/codex`，Hermes 读 `query://client-profile/hermes`，Claude Code 读 `query://client-profile/claude-code`，其他 CLI 或不确定时读 `query://client-profile/generic-cli`。
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
10. 当前任务先在项目本地推进：先在工作区完成分析、改动、验证和本地记录，再通过 MCP 回写任务树、交付结论或记忆到服务端；详细执行轨迹留在本地 runtime。
11. 每个需求必须维护 1 个本地 requirement 对象；项目工作区可解析时，写入 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。需求记录只保存需求内容和必要定位字段，不记录任务树、任务节点、执行历史、项目智能体上下文或其他过程结构。
12. 当前全局清晰度确认阈值为 {{clarity_threshold}}/5；先按 1-5 分估计用户需求清晰度。
13. 若只是查询、解释或客服型问题，且目标、对象、范围和预期结果足够清晰、清晰度分数 >= {{clarity_threshold}}，可直接回答；凡涉及开发、实现、修改、写入或其他会改变项目状态的需求，先判断本轮用户是否已经给出明确执行指令；“修复”“开始”“继续”“按这个做”“修改”“执行”“开始改”等表达视为对当前清晰范围的确认，可直接进入执行，不要再次请求一般计划确认。
14. 若清晰度分数 < {{clarity_threshold}}、需求表述模糊、对象或范围不明确，或存在两种及以上合理理解，先输出你的理解、计划摘要和可能误解点，再请求用户确认后再执行；同一轮已确认或用户已明确要求执行后不要重复确认；任何删除、移除、清空、覆盖、部署、发布、外部系统写入、凭据暴露或不可逆操作必须单独说明对象、影响范围和可恢复性，并取得用户明确确认后才能执行。
15. 一旦用户已确认计划或已明确要求执行，后续按已生成计划连续推进到完成；阶段之间只更新任务树、验证结果和必要进度，本地执行轨迹由本地 runtime 保存，不再停下来请求“是否继续”。只有遇到破坏性/不可逆操作、权限或环境阻塞、需求范围变化、验证无法推进，或必须由用户做业务决策时，才暂停并明确说明阻塞点。
16. 长任务先调用 `record_requirement` 记录服务端需求本体；后续复用同一个 `chat_session_id/session_id`，详细执行轨迹由本地 runtime 保存。
17. 如宿主支持任务树，`bind_project_context(...)` 后立刻读取 `get_current_task_tree`，核对 `root_goal/title/current_node` 是否属于当前问题；若明显属于旧任务树，停止复用当前 `chat_session_id`，改为新建并持久化新的 `chat_session_id` 后重新绑定。
18. 真正进入执行前，再读取一次 `get_current_task_tree` 确认当前节点；开始节点用 `update_task_node_status`，完成节点必须用 `complete_task_node_with_verification` 补验证结果后再结束。
19. 如果当前宿主拿不到上述任务树工具，只能明确说明“任务树闭环未完成”，不要把自然语言进度当成已闭环。
20. 禁止以兜底、兼容、静默降级或重复写入多份状态来掩盖问题；遇到异常、缺失、路径不一致、状态不一致或接口不匹配时，优先定位并修正根因，收敛到唯一规范入口和 canonical 状态。

项目聊天部署约束：
1. 用户提“部署 / 发布到服务器 / 上线 / 发版”这类需求时，第一步先调用 `get_project_deploy_options(project_id)` 读取项目部署配置（脱敏），把可选的环境档位 profile（prod/test 等）和服务器目标 target（含 remote_path、是否带 deploy_command）摆给用户，让用户选择档位和目标后再执行；不要默认直接打包推送。
2. 部署不一定是压缩包：根据配置里每个 component 的 `artifact_kind` 和 target 的部署方式判断——可能是上传 source-bundle 产物、触发已配置的远端 `deploy_command`，或二者结合。只有确实需要打包时才走打包链路。
3. 通知由项目部署配置决定，不询问用户：配置里 `notify_enabled` 为真就按配置通知，为假就不通知。
4. `get_project_deploy_options` 返回 `configured=false`（未启用或无 profiles）时，直接报告 `blocked` / `missing`，提示用户去项目详情的部署配置里补齐档位、服务器目标和凭据；禁止凭空打包或臆造服务器、路径、凭据信息。
5. 需要在用户机器上运行打包命令时，只能通过项目聊天的命令执行能力处理，且必须在桌面端 Runner 中运行；未运行桌面端或当前电脑不可达时，停止并提示无法执行本地命令。执行本地打包命令前必须明确命令内容、工作目录、影响范围、产物路径和可恢复性，并取得用户明确授权。
6. 选定档位/目标、确认部署方式后执行：客户端打包完成或读取用户指定压缩包后，把产物推送到服务端项目详情的部署产物模块；若本地 `project-deploy-artifact` 技能提供 `scripts/push_local_artifact.py`，优先用脚本从当前客户端/桌面端 Runner 读取本地文件并上传；否则调用 `push_project_deploy_artifact` 时必须传 `artifact_content_base64`，不要把 Windows/macOS 本地路径当作服务端可读路径。自动部署由部署产物 AI/服务端部署能力基于服务端 artifact 和项目部署配置执行。
6.1 用户说“推送到服务端部署”“上传部署”“部署这个 zip”“新代码部署”且未限定“只上传”时，`push_project_deploy_artifact.auto_deploy=true`；只有明确“只上传”才传 false。只有用户明确给出 `artifact_id` 或明确说部署已有服务端产物时，才调用 `deploy_project_deploy_artifact`；本地 zip、新代码、重新打包、上传部署或推送部署产物必须先上传本轮文件生成新 artifact，禁止复用历史 artifact。
6.2 如果入口当前接入上下文已提供默认 `project_id`，部署、上传或推送部署产物时直接使用该项目；不要在用户已确认部署后再因为“缺少 project_id”暂停。
7. 部署到生产档位、触发远端 deploy_command 或任何不可逆操作前，必须单独说明对象、影响范围和可恢复性，并取得用户明确确认后才执行。
8. 禁止扫描、读取或复用历史发布配置、CI 配置、本地凭据、远端脚本或环境变量作为执行依据；禁止把 FTP/SSH 账号密码交给模型或本地命令；凭据只通过项目部署配置由服务端使用，AI 侧只读到脱敏摘要。缺少桌面端 Runner、打包命令、部署产物上传能力、服务端 artifact、项目部署配置或部署产物自动部署能力时，直接报告 `blocked` / `missing`。
9. 当前删除打包文件只删除服务端保存的部署 artifact 文件及 artifact 记录；不删除外部平台消息，也不删除远端服务器已部署目录。
10. 机器人通知群优先使用机器人连接器扫描结果；飞书支持扫描机器人所在群，微信/QQ 若返回 `unsupported`，客户端必须提示平台缺少群列表 API/适配能力。

当前接入上下文：
{{project_context_block}}
{{chat_session_block}}
- `chat_session_id` 生成后要立即持久化；优先写项目目录 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`，并同步维护 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。
- requirement 本地对象与 query-mcp canonical 状态要同时维护；不要只写 session 文件而缺失 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`，但 requirement 文件只记录需求内容。
- 如果自动 bootstrap 把状态写到了别的服务子目录，不能把它当成当前仓库根目录已初始化；入口提示词必须以当前 CLI 工作区为准重新核对。
- 若当前还没有 `session_id`，调用 `record_requirement` 后也要立刻持久化；中断恢复先读取本地 runtime 状态，再调用 `bind_project_context(...)` 并读取当前任务树。
- 若项目工作区不可解析，再退回当前 CLI 自己的本地存储；不要在项目工作区写入分叉会话状态文件。

回答要求：
- 先基于 MCP 查询结果回答，不要把猜测写成事实。
- 若信息来自 MCP，尽量保留对应的项目 / 员工 / 规则 ID，方便追溯。
- 若入口文件或宿主系统还有额外约束，优先遵守宿主入口文件约定。"""
DEFAULT_QUERY_MCP_USAGE_GUIDE_TEMPLATE = """# Unified Query MCP

- 统一入口路径: /mcp/query
- 目标: 提供项目/员工/规则查询、任务分析、上下文聚合、执行规划、任务树推进、本地运行轨迹、需求记录查询和交付报告能力。
- 推荐工具: start_project_workflow / bind_project_context / record_requirement / search_ids / get_content / get_manual_content / analyze_task / resolve_relevant_context / generate_execution_plan / get_current_task_tree / update_task_node_status / complete_task_node_with_verification / classify_command_risk / check_workspace_scope / resolve_execution_mode / check_operation_policy / build_delivery_report / generate_release_note_entry / save_project_memory

## 最少执行规则
1. 先读取 query://usage-guide；再按当前客户端读取对应 client profile：Codex 读 query://client-profile/codex，Hermes 读 query://client-profile/hermes，Claude Code 读 query://client-profile/claude-code，其他 CLI 或不确定时读 query://client-profile/generic-cli。
1.0.1 `list_mcp_resources` 只用于发现资源目录，不等于读取资源；同一轮最多调用一次。资源 URI 已知时，直接用 read_mcp_resource 读取 query://usage-guide 和对应 client profile，禁止反复调用 list_mcp_resources。
1.0.2 简单查询直达业务工具：用户询问项目有几个/哪些员工、工具或规则，且 project_id 已明确时，直接调用 list_project_members / list_project_proxy_tools / get_current_task_tree 等对应工具，不要为了 bootstrap 机械列资源目录。
1.1 实现型需求优先调用 start_project_workflow(...) 作为固定入口，不要手动拼接十几个前置查询步骤。
1.2 统一查询工作流默认先检查项目本地 `.ai-employee/skills/query-mcp-workflow/`；若不存在，再从系统技能库同步或创建到本地；已存在则直接复用，禁止重复创建。
1.3 通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；优先读取本地副本中的 `SKILL.md` 与 `manifest.json`。只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。
1.4 打包命令只能通过项目聊天命令执行能力处理，并且必须在桌面端 Runner 中运行；客户端打包或读取指定压缩包后，必须推送到服务端项目详情的部署产物模块；若本地 `project-deploy-artifact` 技能提供 `scripts/push_local_artifact.py`，优先用脚本从当前客户端/Runner 读取本地文件并上传，否则调用 `push_project_deploy_artifact` 时必须传 `artifact_content_base64`；再由部署产物 AI/服务端自动部署能力执行部署。
1.4.1 执行本地打包命令前必须明确命令内容、工作目录、影响范围、生成产物路径和可恢复性；执行本地打包命令前必须取得用户明确授权。
1.4.2 未运行桌面端 Runner 或当前电脑不可达时，必须停止并提示无法执行本地打包命令；只有用户明确给出 `artifact_id` 或明确说部署已有服务端产物时，才调用 `deploy_project_deploy_artifact`。
1.4.3 禁止扫描、读取或复用历史发布配置、CI 配置、本地凭据、远端脚本或环境变量作为执行依据；禁止把 FTP/SSH 账号密码交给模型或本地命令；缺少桌面端 Runner、打包命令、部署产物上传能力、服务端 artifact、项目部署配置或部署产物自动部署能力时，直接报告 blocked / missing。
1.4.4 只有用户明确给出 artifact_id 或明确说部署已有服务端产物时，才调用 `deploy_project_deploy_artifact`；用户说本地 zip、新代码、重新打包、上传部署或推送部署产物时，必须先调用 `push_project_deploy_artifact` 上传本轮文件内容生成新 artifact；用户说“推送到服务端部署”时 `auto_deploy=true`，只有明确“只上传”才设为 false。
1.4.5 如果入口当前接入上下文、URL 默认上下文或渲染出的 CLI 提示词已提供 `project_id`，部署、上传或推送部署产物时把它视为明确项目 ID；不要因为用户回复“确认部署”时未重复 project_id 就暂停。
1.5 部署任务禁止扫描、读取或复用历史发布配置、CI 配置、本地凭据、远端脚本或环境变量作为执行依据；缺少登录态、部署产物上传能力、服务端 artifact、项目部署配置、远端路径或部署产物自动部署能力时，直接报告 `blocked` / `missing`。
2. MCP 配置里的 description、项目说明和“当前项目”这类文字都不参与真正绑定；真正生效的是 URL 里的 project_id / chat_session_id 默认上下文、MCP 会话绑定、渲染出的 CLI 提示词和本地 canonical 状态。
3. 先从 URL 默认上下文、MCP 绑定上下文、渲染出的 CLI 提示词和本地 canonical 状态恢复 `project_id`；只有这些位置都缺失时，才调用 bind_project_context(project_id, chat_session_id?, root_goal?) 或要求用户提供项目 ID。
4. 如果当前 CLI 没有活跃 MCP session，只要显式传了 project_id + chat_session_id，bind_project_context(...) 也会走 detached 绑定并先建任务树；后续所有工具继续显式复用同一个 chat_session_id。
4.0 如果 direct CLI fallback 已先生成临时 `query-cli.*` 会话，后续再用显式 `cli.*` 会话调用 bind_project_context(...) 时，系统会自动把影子任务树迁到正式会话；但最佳实践仍然是首轮就传稳定 chat_session_id。
4.1 每个 CLI 会话都应持久化自己生成的 chat_session_id；如能解析项目工作区，优先写到项目目录 `.ai-employee/query-mcp/`，否则再退回 CLI 自己的本地存储。同一轮任务固定复用，只有新开的并行 CLI 或全新任务才重新生成。
4.2 query-mcp 本地持久化必须使用唯一文件规范：每进程/窗口会话文件为 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每个 CLI 进程或窗口写自己的独立文件，避免多进程和多窗口冲突）；历史索引文件为 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`；需求记录文件为 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。不要写入其他分叉会话状态文件。
4.3 每个需求还必须单独维护 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`；一条需求一个对象，不要把多个需求混写到同一聚合文件。
4.4 requirement 对象只记录需求内容和必要定位字段；不要把 `workflow_skill`、`task_tree`、`current_task_node`、`task_branches`、`history`、项目智能体上下文等过程结构写入需求记录。
5. type=sse 的客户端可能直接使用 POST /mcp/query/sse 作为 JSON-RPC bridge，而不是先 GET /sse 再 /messages；这类接法若 URL 已带 project_id 或本地 canonical 状态可恢复 project_id，不要再要求用户重复提供；确实没有项目 ID 时才提示补充。
6. 仅在缺少明确的 project_id / employee_id / rule_id，或需要跨项目检索时，再调用 search_ids(keyword="<用户原始问题>")；已明确当前项目且在项目内执行时，可直接 get_manual_content、start_project_workflow 或进入本地实现。
7. 需要规则或项目上下文时，先 get_manual_content，再按需调用 get_content；不要跳过 ID 定位直接臆造项目、员工、规则 ID。
7.0 项目型问题优先使用项目绑定员工、规则和技能；先判断项目内现成能力能否闭环，只有项目能力不足时才自行补足。
7.0.1 每次新请求进入分析、实现或排查前，重新获取与当前任务直接相关的规则正文；不要只看规则标题，也不要把无关规则机械带入当前问题。
7.0.2 实现型任务先在项目本地推进：先完成本地分析、改动、验证和 requirement 记录，再通过 MCP 回写任务树、交付结论与记忆；详细执行轨迹留在本地 runtime。
7.0.3 {{clarity_threshold_line}}
7.0.4 {{clarity_direct_line}}
7.0.5 {{clarity_confirm_line}}
7.0.6 {{clarity_repeat_line}}
7.0.7 {{continuous_execution_line}}
7.1 记忆检索不是每轮固定步骤；仅在新需求开始、续跑恢复、修复旧问题或当前问题明显依赖历史经验时，再调用 recall_project_memory 或 recall_employee_memory。
7.2 同一任务轮若已生成任务树并进入执行，后续默认依赖当前会话、任务树和本地运行轨迹，不要重复检索同一批项目记忆。
8. 实现型需求必须遵守任务树闭环：先 analyze_task -> resolve_relevant_context -> generate_execution_plan，再 get_current_task_tree 确认节点；执行中用 update_task_node_status 回写状态，完成时必须 complete_task_node_with_verification 填写验证结果。
9. 只有所有计划节点完成且验证结果齐全后，当前需求才算结束；执行中不得提前写“最终结论”。
10. 查询型问题（谁 / 哪些 / 多少 / 从哪里）保持单检索节点，不要误拆成实现步骤；检索完成后应让任务树归档。
11. 如用户在“已完成”后发现问题，必须重新起一轮修复计划，并继续回写轨迹与验证；不得直接覆盖上一轮结论。
12. 禁止以兜底、兼容、静默降级或重复写入多份状态来掩盖问题；遇到异常、缺失、路径不一致、状态不一致或接口不匹配时，优先定位并修正根因，收敛到唯一规范入口和 canonical 状态。

## 任务树与绑定约束
- 任务树与记忆必须使用同一条聊天会话线索；记录项目记忆、本地执行轨迹或本地运行事件时，应复用当前 chat_session_id / session_id，不得把任务树和记忆拆成两条无关轨迹。
- 同一条用户提问在统一查询 MCP 下只允许沉淀 1 条项目级问题记忆，并绑定 1 棵任务树；record_requirement 等续跑工具不得再生成新的“用户问题”记忆或新的任务树。
- 需要沉淀对话结论时，除最终答案外，还应保证后续可从记忆详情回看该轮规划、执行节点和验证结果。
- 任务树节点必须直接描述面向用户目标的工作步骤；不要把 search_project_context、query_project_rules、search_ids、get_manual_content、resolve_relevant_context、generate_execution_plan 等内部检索/规划工具直接当成节点标题。
- 候选代理工具、脚本路径和类似“Auto inferred proxy entry from scripts/... ”的描述，只能作为内部工具信息，不得直接展示为任务树节点。
- `bind_project_context(...)` 后如已返回任务树，或宿主支持 `get_current_task_tree`，必须立刻校验 `root_goal/title/current_node` 是否属于当前用户原始问题；若明显属于旧问题，说明当前 `chat_session_id` 挂错了任务树，应立即改用新的 `chat_session_id` 重新绑定。
- 不允许跳过节点状态回写直接口头宣布完成；开始节点用 `update_task_node_status`，完成节点用 `complete_task_node_with_verification`，父节点完成前必须补齐自己的整体验证结果。
- 若当前宿主未暴露任务树读取/推进工具，只能说明“无法完成任务树执行闭环”，不得把缺失能力包装成已闭环。

## 高层能力
- analyze_task: 对用户原始任务做结构化理解。
- resolve_relevant_context: 聚合相关项目成员、规则、工具和上下文。
- generate_execution_plan: 输出执行步骤骨架，用于生成真正的任务计划。
- get_current_task_tree / update_task_node_status / complete_task_node_with_verification: 用于读取、推进和验证任务树节点。

## 策略与执行能力
- classify_command_risk: 判断命令风险等级。
- check_workspace_scope: 校验路径是否位于工作区内。
- resolve_execution_mode: 判断该走 local connector、项目工具还是仅保留查询。
- check_operation_policy: 输出允许 / 拦截 / 需确认结论。
- resolve_project_experience_rules: 按任务文本从项目经验规则中按需加载相关经验卡片，避免无关经验占用上下文。
- execute_project_collaboration: 统一编排入口（项目协作），但是否单人主责、是否需要多人协作以及如何拆分，仍由 AI 结合项目手册、员工手册、规则和工具自主判断，不预设固定行业分工模板。
- 若需要手动编排项目执行，再继续调用 list_project_members / get_project_runtime_context / resolve_project_experience_rules / list_project_proxy_tools / invoke_project_skill_tool。

## 本地运行轨迹与恢复
- 多轮任务先调用 record_requirement；服务端只保存用户需求内容和必要定位字段。
- 后续复用同一个 chat_session_id / session_id；详细执行轨迹、阶段、步骤、文件、验证、风险和下一步由 CLI/桌面端本地 runtime 保存。
- 每个新聊天窗口的首轮有效对话，如用户未显式提供 session_id，应优先调用 record_requirement，并把 chat_session_id / session_id 写入本地 canonical 状态。
- 建议把客户端自生成的 chat_session_id 和 record_requirement 返回的 session_id 一起持久化；如能解析项目工作区，优先通过统一状态服务写入 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（窗口级/进程级权威状态）、`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`，并同步维护 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`，否则再退回 CLI 自己的本地存储。这样 CLI 中断后可以直接恢复同一条任务树和本地运行轨迹。
- 缺少活跃 MCP session 的 CLI / bridge 场景下，也必须显式传入并持续复用同一个 chat_session_id；否则容易出现“轨迹已写入，但当前主视图没有挂到任务树”的错觉。
- 推荐的中断恢复顺序是：先从本地恢复 chat_session_id 和 session_id，再调用 bind_project_context(...) 并读取当前任务树继续执行；如果项目工作区不可解析，则恢复来源应是 CLI 自己的本地存储，而不是共享仓库根目录。
- 如宿主需要展示任务树演化摘要，可按需读取 /api/projects/{project_id}/chat/task-tree/evolution-summary?chat_session_id=...。

## 记忆与交付
- recall_project_memory / recall_employee_memory 只在新需求开始、续跑恢复、修复旧问题或明显需要历史经验时使用；不要把记忆检索当成每个计划节点的固定前置动作。
- 同一任务轮若已生成任务树并进入执行，后续优先依赖当前会话、任务树和本地运行轨迹；除非用户明确要求沿用历史方案或当前上下文明显不足，否则不要重复 recall。
- save_project_memory 只在补充稳定结论或关键决策时使用；不要在同一需求的每个中间步骤重复补记。如宿主已启用自动记忆快照，仅在入口未覆盖自动记忆或需要补一条稳定结论时再额外保存。
- build_delivery_report 用于结构化汇总本轮交付；generate_release_note_entry 用于生成更新日志条目。
- 可读取 query://client-profile/codex、query://client-profile/hermes、query://client-profile/claude-code 或 query://client-profile/generic-cli 作为客户端接入画像。

## 说明
- 本入口仍以查询与聚合优先；如宿主支持多 MCP，复杂执行场景仍优先直连对应 project MCP。
- 本入口已暴露 save_project_memory，可通过 project_id 直接写入项目对话内容；save_employee_memory 仍不暴露。如宿主系统已启用自动记忆，入口层仍会自动记录问题快照。"""
DEFAULT_QUERY_MCP_CLIENT_PROFILE_TEMPLATE = """# {{client_title}} Client Profile

{{focus_lines}}"""
DEFAULT_QUERY_MCP_DESKTOP_AGENT_PROFILE_TEMPLATE = """# {{client_title}} Client Profile

{{focus_lines}}"""

_LEGACY_SEARCH_IDS_LINE = '首轮必须把用户原始问题原文传给 `search_ids(keyword="<用户原始问题>")`，不要只写“当前项目”这类代称。'
_UPDATED_SEARCH_IDS_LINE = '仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或需要跨项目检索时，再调用 `search_ids(keyword="<用户原始问题>")`；已明确当前项目且在项目内执行时可直接读取上下文或进入本地实现，不要为满足流程机械检索。'
_LEGACY_SEARCH_IDS_LINE_GUIDE = '首轮查询必须把用户原始问题原文放进 search_ids(keyword="<用户原始问题>")；不要只写“当前项目”“这个规则”“项目手册”这类代称。'
_UPDATED_SEARCH_IDS_LINE_GUIDE = '仅在缺少明确的 project_id / employee_id / rule_id，或需要跨项目检索时，再调用 search_ids(keyword="<用户原始问题>")；已明确当前项目且在项目内执行时，可直接 get_manual_content、start_project_workflow 或进入本地实现。'
_CLIENT_PROFILE_BOOTSTRAP_LINE = '1. 先读取 `query://usage-guide`；再按当前客户端读取对应画像：Codex 读 `query://client-profile/codex`，Hermes 读 `query://client-profile/hermes`，Claude Code 读 `query://client-profile/claude-code`，其他 CLI 或不确定时读 `query://client-profile/generic-cli`。'
_RESOURCE_DISCOVERY_GUARD_BOOTSTRAP_LINE = '1.1 `list_mcp_resources` 只用于发现资源目录，不等于读取资源；同一轮最多调用一次。资源 URI 已知时，必须直接用 `read_mcp_resource` 读取 `query://usage-guide` 和当前客户端对应的 `query://client-profile/...`，禁止反复调用 `list_mcp_resources`。'
_CLIENT_PROFILE_GUIDE_LINE = '1. 先读取 query://usage-guide；再按当前客户端读取对应 client profile：Codex 读 query://client-profile/codex，Hermes 读 query://client-profile/hermes，Claude Code 读 query://client-profile/claude-code，其他 CLI 或不确定时读 query://client-profile/generic-cli。'
_CLIENT_PROFILE_BOOTSTRAP_RESOURCE_LINES = [
    "- `query://client-profile/codex`（Codex CLI）",
    "- `query://client-profile/hermes`（Hermes）",
    "- `query://client-profile/claude-code`（Claude Code）",
    "- `query://client-profile/generic-cli`（其他 MCP CLI / 通用智能体）",
]
_SIMPLE_QUERY_DIRECT_BOOTSTRAP_LINE = '1.2 对“有几个员工 / 有哪些员工 / 有哪些工具 / 有哪些规则”这类简单查询，且 `project_id` 已明确时，直接调用对应业务工具（如 `list_project_members(project_id=...)`、`list_project_proxy_tools(...)`），不要为了满足 bootstrap 机械列资源目录。'
_RESOURCE_DISCOVERY_GUARD_GUIDE_LINE = '1.0.1 `list_mcp_resources` 只用于发现资源目录，不等于读取资源；同一轮最多调用一次。资源 URI 已知时，直接用 read_mcp_resource 读取 query://usage-guide 和对应 client profile，禁止反复调用 list_mcp_resources。'
_SIMPLE_QUERY_DIRECT_GUIDE_LINE = '1.0.2 简单查询直达业务工具：用户询问项目有几个/哪些员工、工具或规则，且 project_id 已明确时，直接调用 list_project_members / list_project_proxy_tools / get_current_task_tree 等对应工具，不要为了 bootstrap 机械列资源目录。'
_DEPLOY_ARTIFACT_SKILL_GUIDE_LINES = [
    '1.4 用户提“部署 / 发布到服务器 / 上线”需求时，先调用 `get_project_deploy_options(project_id)` 读取脱敏部署配置，把可选环境档位 profile 和服务器目标 target 摆给用户让其选择；返回 `configured=false` 时直接报 `blocked` / `missing` 并提示去项目详情补齐部署配置，不要凭空打包或臆造服务器信息。部署不一定是压缩包，按 component 的 `artifact_kind` 和 target 是否带 `deploy_command` 判断方式；通知由配置的 `notify_enabled` 决定，不询问用户。',
    '1.4.1 打包命令只能通过项目聊天命令执行能力处理，并且必须在桌面端 Runner 中运行；客户端打包或读取指定压缩包后，必须推送到服务端项目详情的部署产物模块；若本地 `project-deploy-artifact` 技能提供 `scripts/push_local_artifact.py`，优先用脚本从当前客户端/Runner 读取本地文件并上传，否则调用 `push_project_deploy_artifact` 时必须传 `artifact_content_base64`；再由部署产物 AI/服务端自动部署能力执行部署。',
    '1.4.2 执行本地打包命令前必须明确命令内容、工作目录、影响范围、生成产物路径和可恢复性；执行本地打包命令前必须取得用户明确授权。',
    '1.4.3 未运行桌面端 Runner 或当前电脑不可达时，必须停止并提示无法执行本地打包命令；只有用户明确给出 `artifact_id` 或明确说部署已有服务端产物时，才调用 `deploy_project_deploy_artifact`。',
    '1.4.4 禁止扫描、读取或复用历史发布配置、CI 配置、本地凭据、远端脚本或环境变量作为执行依据；禁止把 FTP/SSH 账号密码交给模型或本地命令；缺少桌面端 Runner、打包命令、部署产物上传能力、服务端 artifact、项目部署配置或部署产物自动部署能力时，直接报告 blocked / missing。',
    '1.4.5 只有用户明确给出 artifact_id 或明确说部署已有服务端产物时，才调用 `deploy_project_deploy_artifact`；用户说本地 zip、新代码、重新打包、上传部署或推送部署产物时，必须先调用 `push_project_deploy_artifact` 上传本轮文件内容生成新 artifact；用户说“推送到服务端部署”时 `auto_deploy=true`，只有明确“只上传”才设为 false。',
    '1.4.6 如果入口当前接入上下文、URL 默认上下文或渲染出的 CLI 提示词已提供 `project_id`，部署、上传或推送部署产物时把它视为明确项目 ID；不要因为用户回复“确认部署”时未重复 project_id 就暂停。',
    '1.5 部署到生产档位或触发远端 deploy_command 等不可逆操作前必须单独说明对象、影响范围和可恢复性并取得用户确认；禁止扫描、读取或复用历史发布配置、CI 配置、本地凭据、远端脚本或环境变量作为执行依据；缺少登录态、部署产物上传能力、服务端 artifact、项目部署配置、远端路径或部署产物自动部署能力时，直接报告 `blocked` / `missing`。',
]
_LEGACY_DEPLOY_GUIDE_LINE_PATTERNS = (
    "部署产物任务必须先加载",
    "客户端只打包、计算 artifact 元数据",
    "客户端通过 MCP/部署技能读取项目的 FTP",
    "客户端先通过 MCP/部署技能读取项目级部署参数",
    "MCP 提示词不提供打包产物上传",
    "项目聊天界面本身有“部署产物上传/部署”按钮",
    "部署产物上传/部署",
    "在客户端本地执行部署",
    "FTP-only 部署要求",
    "服务端按 `deploy_settings` 部署",
    "缺少推送工具",
)
_DEPLOY_CONTRACT_LINE_PREFIXES = ("1.4", "1.5")
_DEPLOY_CONTRACT_LINE_HINTS = (
    "打包",
    "部署",
    "发布",
    "产物",
    "artifact",
    "deploy",
    "FTP",
    "SSH",
    "Runner",
    "远端",
    "上传",
    "推送",
)
_LEGACY_QUERY_MCP_SKILL_SOURCE_LINE = '当前统一查询 MCP 工作流技能的服务端权威元数据位于 `mcp-skills/knowledge/skills/query-mcp-workflow.json`，技能包位于 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/`；核心文件优先读取 `SKILL.md` 与 `manifest.json`。若宿主或项目已提供本地同名技能目录，优先读取本地副本。'
_UPDATED_QUERY_MCP_SKILL_SOURCE_LINE = '通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；核心文件优先读取本地副本中的 `SKILL.md` 与 `manifest.json`。只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。'
_LEGACY_QUERY_MCP_SKILL_SOURCE_LINE_GUIDE = '服务端权威技能元数据位于 `mcp-skills/knowledge/skills/query-mcp-workflow.json`，技能包位于 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/`；若宿主或项目已注入本地同名技能目录，优先读取本地副本，核心文件先看 `SKILL.md` 与 `manifest.json`。'
_UPDATED_QUERY_MCP_SKILL_SOURCE_LINE_GUIDE = '通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；优先读取本地副本中的 `SKILL.md` 与 `manifest.json`。只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。'
_LEGACY_CLARITY_DIRECT_LINE = '若目标、对象、范围和预期结果足够清晰，且清晰度分数 >= {{clarity_threshold}}，直接处理，不主动要求确认计划。'
_UPDATED_CLARITY_DIRECT_LINE = '若只是查询、解释或客服型问题，且目标、对象、范围和预期结果足够清晰、清晰度分数 >= {{clarity_threshold}}，可直接回答；凡涉及开发、实现、修改、写入或其他会改变项目状态的需求，先判断本轮用户是否已经给出明确执行指令；“修复”“开始”“继续”“按这个做”“修改”“执行”“开始改”等表达视为对当前清晰范围的确认，可直接进入执行，不要再次请求一般计划确认。'
_LEGACY_CLARITY_CONFIRM_LINE = '若清晰度分数 < {{clarity_threshold}}、需求表述模糊、对象或范围不明确，或存在两种及以上合理理解，先输出你的理解、计划摘要和可能误解点，再请求用户确认后再执行；同一轮已确认后不要重复确认；查询型、客服型问题不要默认升级成计划审批流程。'
_UPDATED_CLARITY_CONFIRM_LINE = '若清晰度分数 < {{clarity_threshold}}、需求表述模糊、对象或范围不明确，或存在两种及以上合理理解，先输出你的理解、计划摘要和可能误解点，再请求用户确认后再执行；同一轮已确认或用户已明确要求执行后不要重复确认；任何删除、移除、清空、覆盖、部署、发布、外部系统写入、凭据暴露或不可逆操作必须单独说明对象、影响范围和可恢复性，并取得用户明确确认后才能执行。'
_CONTINUOUS_EXECUTION_TEXT = '一旦用户已确认计划或已明确要求执行，后续按已生成计划连续推进到完成；阶段之间只更新任务树、验证结果和必要进度，本地执行轨迹由本地 runtime 保存，不再停下来请求“是否继续”。只有遇到破坏性/不可逆操作、权限或环境阻塞、需求范围变化、验证无法推进，或必须由用户做业务决策时，才暂停并明确说明阻塞点。'
_CONTINUOUS_EXECUTION_BOOTSTRAP_LINE = f'15. {_CONTINUOUS_EXECUTION_TEXT}'
_CONTINUOUS_EXECUTION_GUIDE_LINE = f'7.0.7 {_CONTINUOUS_EXECUTION_TEXT}'
_PROMPT_SYNC_BOOTSTRAP_LINE = '6.1 若用户明确要求“更新提示词”“同步提示词”“刷新 AGENTS.md”或类似操作，且 `project_id`、`chat_session_id` 与当前 CLI 工作区明确，直接调用 `sync_query_mcp_cli_prompt_to_local_file(project_id=<当前项目>, chat_session_id=<当前会话>, workspace_path=<当前 CLI 工作区>, target_file="AGENTS.md", backup=true, dry_run=false)`，用服务端渲染的 `runtime.cli_prompt` 覆盖当前项目根目录提示词文件；不要只预览或只口头说明。完成后保留工具返回的 `target_file`、`backup_file`、`content_hash` 作为验证记录；若 workspace_path 不明确或目标路径不在当前工作区，先说明阻塞。'
_ROOT_CAUSE_RULE_BOOTSTRAP_LINE = '20. 禁止以兜底、兼容、静默降级或重复写入多份状态来掩盖问题；遇到异常、缺失、路径不一致、状态不一致或接口不匹配时，优先定位并修正根因，收敛到唯一规范入口和 canonical 状态。'
_ROOT_CAUSE_RULE_GUIDE_LINE = '12. 禁止以兜底、兼容、静默降级或重复写入多份状态来掩盖问题；遇到异常、缺失、路径不一致、状态不一致或接口不匹配时，优先定位并修正根因，收敛到唯一规范入口和 canonical 状态。'
_DEPLOY_ARTIFACT_CONTRACT_BOOTSTRAP_BLOCK = """项目聊天部署约束：
1. 用户提“部署 / 发布到服务器 / 上线 / 发版”这类需求时，第一步先调用 `get_project_deploy_options(project_id)` 读取项目部署配置（脱敏），把可选的环境档位 profile（prod/test 等）和服务器目标 target（含 remote_path、是否带 deploy_command）摆给用户，让用户选择档位和目标后再执行；不要默认直接打包推送。
2. 部署不一定是压缩包：根据配置里每个 component 的 `artifact_kind` 和 target 的部署方式判断——可能是上传 source-bundle 产物、触发已配置的远端 `deploy_command`，或二者结合。只有确实需要打包时才走打包链路，不要把所有部署都当成“打 zip”。
3. 通知由项目部署配置决定，不询问用户：配置里 `notify_enabled` 为真就按配置通知，为假就不通知；不要把“是否通知”作为问题抛给用户。
4. `get_project_deploy_options` 返回 `configured=false`（未启用或无 profiles）时，直接报告 `blocked` / `missing`，提示用户去项目详情的部署配置里补齐档位、服务器目标和凭据；禁止凭空打包或臆造服务器、路径、凭据信息。
5. 需要在用户机器上运行打包命令时，只能通过项目聊天的命令执行能力处理，且必须在桌面端 Runner 中运行；未运行桌面端或当前电脑不可达时，停止并提示无法执行本地命令。执行本地打包命令前必须明确命令内容、工作目录、影响范围、产物路径和可恢复性，并取得用户明确授权。
6. 选定档位/目标、确认部署方式后执行：客户端打包完成或读取用户指定压缩包后，把产物推送到服务端项目详情的部署产物模块；若本地 `project-deploy-artifact` 技能提供 `scripts/push_local_artifact.py`，优先用脚本从当前客户端/桌面端 Runner 读取本地文件并上传；否则调用 `push_project_deploy_artifact` 时必须传 `artifact_content_base64`，不要把 Windows/macOS 本地路径当作服务端可读路径。自动部署由部署产物 AI/服务端部署能力基于服务端 artifact 和项目部署配置执行。
6.1 用户说“推送到服务端部署”“上传部署”“部署这个 zip”“新代码部署”且未限定“只上传”时，`push_project_deploy_artifact.auto_deploy=true`；只有明确“只上传”才传 false。只有用户明确给出 `artifact_id` 或明确说部署已有服务端产物时，才调用 `deploy_project_deploy_artifact`；本地 zip、新代码、重新打包、上传部署或推送部署产物必须先上传本轮文件生成新 artifact，禁止复用历史 artifact。
6.2 如果入口当前接入上下文已提供默认 `project_id`，部署、上传或推送部署产物时直接使用该项目；不要在用户已确认部署后再因为“缺少 project_id”暂停。
7. 部署到生产档位、触发远端 deploy_command 或任何不可逆操作前，必须单独说明对象、影响范围和可恢复性，并取得用户明确确认后才执行。
8. 禁止扫描、读取或复用历史发布配置、CI 配置、本地凭据、远端脚本或环境变量作为执行依据；禁止把 FTP/SSH 账号密码交给模型或本地命令；凭据只通过项目部署配置由服务端使用，AI 侧只读到脱敏摘要。缺少桌面端 Runner、打包命令、部署产物上传能力、服务端 artifact、项目部署配置或部署产物自动部署能力时，直接报告 `blocked` / `missing`。
9. 当前删除打包文件只删除服务端保存的部署 artifact 文件及 artifact 记录；不删除外部平台消息，也不删除远端服务器已部署目录。
10. 机器人通知群优先使用机器人连接器扫描结果；飞书支持扫描机器人所在群，微信/QQ 若返回 `unsupported`，客户端必须提示平台缺少群列表 API/适配能力。"""
_UPDATED_QUERY_MCP_ACTIVE_STATE_GUIDE_LINE = '4.2 query-mcp 本地持久化必须使用唯一文件规范：每进程/窗口会话文件为 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每个 CLI 进程或窗口写自己的独立文件，避免多进程和多窗口冲突）；历史索引文件为 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`；需求记录文件为 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。不要写入其他分叉会话状态文件。'
_UPDATED_QUERY_MCP_ACTIVE_STATE_BOOTSTRAP_INIT_LINE = '2. 初始化不是只检查技能；先以当前 CLI 工作区为准，显式初始化本地 `.ai-employee/`，至少确保 `.ai-employee/skills/`、`.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/session-history/` 与 `.ai-employee/requirements/<project_id>/` 可用；canonical session 状态只使用 `active-sessions/<chat_session_id>.json` 与 `session-history/<project_id>__<chat_session_id>.json`。'
_UPDATED_QUERY_MCP_ACTIVE_STATE_BOOTSTRAP_CONTEXT_LINE = '- `chat_session_id` 生成后要立即持久化；优先写项目目录 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`，并同步维护 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。'
_UPDATED_QUERY_MCP_ACTIVE_STATE_RECOVERY_LINE = '- 建议把客户端自生成的 chat_session_id 和 record_requirement 返回的 session_id 一起持久化；如能解析项目工作区，优先通过统一状态服务写入 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（窗口级/进程级权威状态）、`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`，并同步维护 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`，否则再退回 CLI 自己的本地存储。这样 CLI 中断后可以直接恢复同一条任务树和本地运行轨迹。'


def _normalize_query_mcp_active_state_contract(text: str) -> str:
    upgraded = str(text or "")
    replacements = {
        '2. 初始化不是只检查技能；先以当前 CLI 工作区为准，显式初始化本地 `.ai-employee/`，至少确保 `.ai-employee/skills/`、`.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/active/`、`.ai-employee/query-mcp/session-history/` 与 `.ai-employee/requirements/<project_id>/` 可用。': _UPDATED_QUERY_MCP_ACTIVE_STATE_BOOTSTRAP_INIT_LINE,
        '2. 初始化不是只检查技能；先以当前 CLI 工作区为准，显式初始化本地 `.ai-employee/`，至少确保 `.ai-employee/skills/`、`.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/session-history/` 与 `.ai-employee/requirements/<project_id>/` 可用；`.ai-employee/query-mcp/active/<project_id>.json` 仅作为历史遗留指针只读恢复，禁止新写。': _UPDATED_QUERY_MCP_ACTIVE_STATE_BOOTSTRAP_INIT_LINE,
        '- `chat_session_id` 生成后要立即持久化；优先写项目目录 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`，并同步维护 `.ai-employee/query-mcp/active/<project_id>.json` 与 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。': _UPDATED_QUERY_MCP_ACTIVE_STATE_BOOTSTRAP_CONTEXT_LINE,
        '4.2 query-mcp 本地持久化必须使用唯一文件规范：每进程会话文件为 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每个 CLI 进程写自己的独立文件，避免多进程冲突）；项目级权威状态文件为 `.ai-employee/query-mcp/active/<project_id>.json` 与 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。除兼容历史数据时只读外，禁止新写 `current-session.json`、`chat_session_id.txt`、`session_id.txt`、`chat_session_id`、`session_id`、`session.env`、`current-query-session.json`、`current-work-session.json` 这类分叉文件。': _UPDATED_QUERY_MCP_ACTIVE_STATE_GUIDE_LINE,
        '- 建议把客户端自生成的 chat_session_id 和 record_requirement 返回的 session_id 一起持久化；如能解析项目工作区，优先通过统一状态服务写入 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`（每进程独立）、`.ai-employee/query-mcp/active/<project_id>.json`、`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`，否则再退回 CLI 自己的本地存储。这样 CLI 中断后可以直接恢复同一条任务树和本地运行轨迹。': _UPDATED_QUERY_MCP_ACTIVE_STATE_RECOVERY_LINE,
    }
    for legacy, current in replacements.items():
        upgraded = upgraded.replace(legacy, current)
    return upgraded


def _insert_prompt_lines(text: str, *, anchor: str, fallback_heading: str, lines: list[str]) -> str:
    insert_text = "\n".join(lines)
    if anchor in text:
        return text.replace(anchor, f"{anchor}\n{insert_text}", 1)
    if fallback_heading in text:
        return text.replace(fallback_heading, f"{fallback_heading}\n{insert_text}", 1)
    return text


def _normalize_bootstrap_client_profile_resource_lines(text: str) -> str:
    upgraded = str(text or "")
    if "强制接入步骤：" not in upgraded:
        return upgraded

    header, separator, tail = upgraded.partition("强制接入步骤：")
    if "详细规则不要直接内联到宿主提示词" not in header:
        resource_block = "\n".join(
            [
                "详细规则不要直接内联到宿主提示词；但开始执行前必须按需读取这些资源：",
                "- `query://usage-guide`",
                *_CLIENT_PROFILE_BOOTSTRAP_RESOURCE_LINES,
            ]
        )
        return header.rstrip() + "\n\n" + resource_block + "\n\n" + separator + "\n" + tail.lstrip("\n")

    lines = header.splitlines()
    normalized_lines: list[str] = []
    inserted = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- `query://client-profile/"):
            continue
        normalized_lines.append(line)
        if stripped == "- `query://usage-guide`":
            normalized_lines.extend(_CLIENT_PROFILE_BOOTSTRAP_RESOURCE_LINES)
            inserted = True

    if not inserted:
        normalized_lines.extend(_CLIENT_PROFILE_BOOTSTRAP_RESOURCE_LINES)
    return "\n".join(normalized_lines).rstrip() + "\n\n" + separator + "\n" + tail.lstrip("\n")


def _normalize_bootstrap_deploy_contract_block(text: str) -> str:
    upgraded = str(text or "")
    markers = [
        "项目聊天部署约束：",
        "项目聊天打包部署命令约束：",
        "部署产物技能入口：",
        "客户端 AI 打包部署契约：",
    ]
    positions = [upgraded.find(marker) for marker in markers if marker in upgraded]
    if not positions:
        return upgraded
    start = min(position for position in positions if position >= 0)
    end = upgraded.find("\n\n当前接入上下文：", start)
    if end == -1:
        end = upgraded.find("当前接入上下文：", start)
    suffix = upgraded[end:].lstrip() if end != -1 else ""
    return (
        upgraded[:start].rstrip()
        + "\n\n"
        + _DEPLOY_ARTIFACT_CONTRACT_BOOTSTRAP_BLOCK
        + ("\n\n" + suffix if suffix else "")
    )


def _normalize_usage_guide_deploy_contract_lines(text: str) -> str:
    upgraded = str(text or "")
    if "# Unified Query MCP" not in upgraded or "## 最少执行规则" not in upgraded:
        return upgraded

    filtered_lines: list[str] = []
    for line in upgraded.splitlines():
        stripped = line.strip()
        if stripped in _DEPLOY_ARTIFACT_SKILL_GUIDE_LINES:
            continue
        if any(pattern in stripped for pattern in _LEGACY_DEPLOY_GUIDE_LINE_PATTERNS):
            continue
        if stripped.startswith(_DEPLOY_CONTRACT_LINE_PREFIXES) and any(
            hint in stripped for hint in _DEPLOY_CONTRACT_LINE_HINTS
        ):
            continue
        filtered_lines.append(line)
    upgraded = "\n".join(filtered_lines)

    anchor = _UPDATED_QUERY_MCP_SKILL_SOURCE_LINE_GUIDE
    if anchor in upgraded:
        return upgraded.replace(
            anchor,
            f"{anchor}\n" + "\n".join(_DEPLOY_ARTIFACT_SKILL_GUIDE_LINES),
            1,
        )
    marker = "\n2. MCP 配置里的 description"
    if marker in upgraded:
        return upgraded.replace(
            marker,
            "\n" + "\n".join(_DEPLOY_ARTIFACT_SKILL_GUIDE_LINES) + marker,
            1,
        )
    return _insert_prompt_lines(
        upgraded,
        anchor="## 最少执行规则",
        fallback_heading="## 最少执行规则",
        lines=_DEPLOY_ARTIFACT_SKILL_GUIDE_LINES,
    )


_CLIENT_DEPLOY_ARTIFACT_PROFILE_LINES = [
    "- 部署约束: 用户提“部署 / 发布到服务器 / 上线”需求时，先调用 `get_project_deploy_options(project_id)` 读取脱敏部署配置，把可选环境档位 profile（prod/test 等）和服务器目标 target（含 remote_path、是否带 deploy_command）摆给用户让其选择，再决定打包/上传/触发远端命令；部署不一定是压缩包，按 component 的 `artifact_kind` 和 target 是否带 deploy_command 判断方式；通知由配置的 `notify_enabled` 决定，不询问用户；返回 `configured=false` 时报 `blocked` / `missing` 并提示去项目详情补齐部署配置，不要凭空打包或臆造服务器信息。",
    "- 部署约束: 打包命令只能通过项目聊天命令执行能力处理，并且必须在桌面端 Runner 中运行；客户端打包或读取指定压缩包后，必须推送到服务端项目详情的部署产物模块；若本地 `project-deploy-artifact` 技能提供 `scripts/push_local_artifact.py`，优先用脚本从当前客户端/Runner 读取本地文件并上传，否则调用 `push_project_deploy_artifact` 时必须传 `artifact_content_base64`；再由部署产物 AI/服务端自动部署能力执行部署。",
    "- 部署约束: 执行本地打包命令前必须明确命令内容、工作目录、影响范围、生成产物路径和可恢复性；执行本地打包命令前必须取得用户明确授权；部署到生产档位或触发远端 deploy_command 等不可逆操作前必须单独说明影响范围和可恢复性并取得用户确认。",
    "- 部署约束: 未运行桌面端 Runner 或当前电脑不可达时，必须停止并提示无法执行本地打包命令；只有用户明确给出 `artifact_id` 或明确说部署已有服务端产物时，才调用 `deploy_project_deploy_artifact`；本地 zip、新代码、重新打包、上传部署或推送部署产物必须先上传本轮文件生成新 artifact。",
    "- 部署约束: 如果 URL 默认上下文、MCP 绑定上下文、渲染出的 CLI 提示词或本地 canonical 状态已提供 `project_id`，部署、上传或推送部署产物时直接使用它；不要在用户已确认部署后再因为“缺少 project_id”暂停。",
    "- 部署约束: 禁止扫描、读取或复用历史发布配置、CI 配置、本地凭据、远端脚本或环境变量作为执行依据；禁止把 FTP/SSH 账号密码交给模型或本地命令；凭据只通过项目部署配置由服务端使用，AI 侧只读到脱敏摘要；缺少桌面端 Runner、打包命令、部署产物上传能力、服务端 artifact、项目部署配置或部署产物自动部署能力时直接报告 `blocked` / `missing`。",
]


def normalize_query_mcp_client_profile_template(template: str) -> str:
    normalized = str(template or "").strip()
    if not normalized:
        return DEFAULT_QUERY_MCP_CLIENT_PROFILE_TEMPLATE
    if "{{focus_lines}}" in normalized:
        return normalized

    filtered_lines: list[str] = []
    inserted = False
    for line in normalized.splitlines():
        stripped = line.strip()
        if stripped in _CLIENT_DEPLOY_ARTIFACT_PROFILE_LINES:
            continue
        if any(pattern in stripped for pattern in _LEGACY_DEPLOY_GUIDE_LINE_PATTERNS):
            continue
        if stripped.startswith("- 部署约束:"):
            if not inserted:
                filtered_lines.extend(_CLIENT_DEPLOY_ARTIFACT_PROFILE_LINES)
                inserted = True
            continue
        filtered_lines.append(line)

    upgraded = "\n".join(filtered_lines)
    if not inserted and "Client Profile" in upgraded and "- 部署约束:" in upgraded:
        lines = upgraded.splitlines()
        insert_at = next(
            (
                index
                for index, line in enumerate(lines)
                if line.strip().startswith("- 接入约束:")
            ),
            len(lines),
        )
        lines[insert_at:insert_at] = _CLIENT_DEPLOY_ARTIFACT_PROFILE_LINES
        upgraded = "\n".join(lines)
    return upgraded


def normalize_query_mcp_desktop_agent_profile_template(template: str) -> str:
    normalized = str(template or "").strip()
    if not normalized:
        return DEFAULT_QUERY_MCP_DESKTOP_AGENT_PROFILE_TEMPLATE
    if "{{focus_lines}}" in normalized:
        return normalized
    return normalized


def _looks_like_legacy_bootstrap_template(template: str) -> bool:
    normalized = str(template or "").strip()
    if not normalized:
        return False
    # Legacy built-in bootstrap prompts should be auto-upgraded to the latest local-first contract.
    return (
        "你已接入统一查询 MCP。" in normalized
        and "强制接入步骤：" in normalized
        and "当前接入上下文：" in normalized
        and "回答要求：" in normalized
        and "显式初始化本地 `.ai-employee/`" not in normalized
        and "当前任务先在项目本地推进" not in normalized
    )


def normalize_query_mcp_bootstrap_prompt_template(template: str) -> str:
    normalized = str(template or "").strip()
    if not normalized:
        return DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE
    if _looks_like_legacy_bootstrap_template(normalized):
        return DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE
    upgraded = _normalize_bootstrap_client_profile_resource_lines(_normalize_query_mcp_active_state_contract(
        normalized.replace(_LEGACY_SEARCH_IDS_LINE, _UPDATED_SEARCH_IDS_LINE)
        .replace(_LEGACY_QUERY_MCP_SKILL_SOURCE_LINE, _UPDATED_QUERY_MCP_SKILL_SOURCE_LINE)
        .replace(_LEGACY_CLARITY_DIRECT_LINE, _UPDATED_CLARITY_DIRECT_LINE)
        .replace(_LEGACY_CLARITY_CONFIRM_LINE, _UPDATED_CLARITY_CONFIRM_LINE)
        .replace(
            "1. 先读取 `query://usage-guide`；当前是 Codex CLI 时，再读取 `query://client-profile/codex`。",
            _CLIENT_PROFILE_BOOTSTRAP_LINE,
        )
        .replace(
            "1. 先读取 query://usage-guide；当前是 Codex / Claude 这类代码 CLI 时，再补读 query://client-profile/codex 或 query://client-profile/claude-code。",
            _CLIENT_PROFILE_GUIDE_LINE,
        )
        .replace(
            '1.1 `list_mcp_resources` 只用于发现资源目录，不等于读取资源；同一轮最多调用一次。资源 URI 已知时，必须直接用 `read_mcp_resource` 读取 `query://usage-guide` 和 `query://client-profile/codex`，禁止反复调用 `list_mcp_resources`。',
            _RESOURCE_DISCOVERY_GUARD_BOOTSTRAP_LINE,
        )
    ))
    if (
        "你已接入统一查询 MCP。" in upgraded
        and "强制接入步骤：" in upgraded
        and _CLIENT_PROFILE_BOOTSTRAP_LINE not in upgraded
    ):
        upgraded = _insert_prompt_lines(
            upgraded,
            anchor="强制接入步骤：",
            fallback_heading="强制接入步骤：",
            lines=[_CLIENT_PROFILE_BOOTSTRAP_LINE],
        )
    if (
        "你已接入统一查询 MCP。" in upgraded
        and "强制接入步骤：" in upgraded
        and (
            _RESOURCE_DISCOVERY_GUARD_BOOTSTRAP_LINE not in upgraded
            or _SIMPLE_QUERY_DIRECT_BOOTSTRAP_LINE not in upgraded
        )
    ):
        anchor = _CLIENT_PROFILE_BOOTSTRAP_LINE
        upgraded = upgraded.replace(f"\n{_RESOURCE_DISCOVERY_GUARD_BOOTSTRAP_LINE}", "")
        upgraded = upgraded.replace(f"\n{_SIMPLE_QUERY_DIRECT_BOOTSTRAP_LINE}", "")
        upgraded = _insert_prompt_lines(
            upgraded,
            anchor=anchor,
            fallback_heading="强制接入步骤：",
            lines=[
                _RESOURCE_DISCOVERY_GUARD_BOOTSTRAP_LINE,
                _SIMPLE_QUERY_DIRECT_BOOTSTRAP_LINE,
            ],
        )
    if (
        "你已接入统一查询 MCP。" in upgraded
        and "强制接入步骤：" in upgraded
        and "不再停下来请求“是否继续”" not in upgraded
    ):
        long_task_line = "15. 长任务先调用 `record_requirement` 记录服务端需求本体；后续复用同一个 `chat_session_id/session_id`，详细执行轨迹由本地 runtime 保存。"
        if long_task_line in upgraded:
            upgraded = upgraded.replace(
                long_task_line,
                f"{_CONTINUOUS_EXECUTION_BOOTSTRAP_LINE}\n"
                "16. 长任务先调用 `record_requirement` 记录服务端需求本体；后续复用同一个 `chat_session_id/session_id`，详细执行轨迹由本地 runtime 保存。",
            )
            upgraded = upgraded.replace("16. 如宿主支持任务树，", "17. 如宿主支持任务树，")
            upgraded = upgraded.replace("17. 真正进入执行前，", "18. 真正进入执行前，")
            upgraded = upgraded.replace("18. 如果当前宿主拿不到上述任务树工具，", "19. 如果当前宿主拿不到上述任务树工具，")
            upgraded = upgraded.replace("19. 禁止以兜底、兼容、静默降级", "20. 禁止以兜底、兼容、静默降级")
        else:
            upgraded = _insert_prompt_lines(
                upgraded,
                anchor=f"5. {_UPDATED_CLARITY_CONFIRM_LINE}",
                fallback_heading="强制接入步骤：",
                lines=[_CONTINUOUS_EXECUTION_BOOTSTRAP_LINE],
            )
    if (
        "你已接入统一查询 MCP。" in upgraded
        and "强制接入步骤：" in upgraded
        and "sync_query_mcp_cli_prompt_to_local_file" not in upgraded
    ):
        upgraded = _insert_prompt_lines(
            upgraded,
            anchor="6. 若当前任务是更新工作流规范或技能包，优先在本地技能副本、提示词模板和同步策略上修改；只有本地缺失或需要回源比对时，才从服务端技能库同步。",
            fallback_heading="强制接入步骤：",
            lines=[_PROMPT_SYNC_BOOTSTRAP_LINE],
        )
    if (
        "你已接入统一查询 MCP。" in upgraded
        and "强制接入步骤：" in upgraded
        and "当前接入上下文：" in upgraded
        and "禁止以兜底、兼容、静默降级" not in upgraded
    ):
        upgraded = upgraded.replace(
            "19. 如果当前宿主拿不到上述任务树工具，只能明确说明“任务树闭环未完成”，不要把自然语言进度当成已闭环。",
            "19. 如果当前宿主拿不到上述任务树工具，只能明确说明“任务树闭环未完成”，不要把自然语言进度当成已闭环。\n"
            f"{_ROOT_CAUSE_RULE_BOOTSTRAP_LINE}",
        )
    upgraded = _normalize_bootstrap_deploy_contract_block(upgraded)
    if (
        "你已接入统一查询 MCP。" in upgraded
        and "当前接入上下文：" in upgraded
        and "项目聊天部署约束：" not in upgraded
    ):
        upgraded = upgraded.replace(
            "当前接入上下文：",
            f"{_DEPLOY_ARTIFACT_CONTRACT_BOOTSTRAP_BLOCK}\n\n当前接入上下文：",
            1,
        )
    return upgraded


def normalize_query_mcp_usage_guide_template(template: str) -> str:
    normalized = str(template or "").strip()
    if not normalized:
        return DEFAULT_QUERY_MCP_USAGE_GUIDE_TEMPLATE
    upgraded = _normalize_query_mcp_active_state_contract(
        normalized.replace(_LEGACY_SEARCH_IDS_LINE_GUIDE, _UPDATED_SEARCH_IDS_LINE_GUIDE).replace(
            _LEGACY_QUERY_MCP_SKILL_SOURCE_LINE_GUIDE,
            _UPDATED_QUERY_MCP_SKILL_SOURCE_LINE_GUIDE,
        )
        .replace(
            "1. 先读取 query://usage-guide；当前是 Codex / Claude 这类代码 CLI 时，再补读 query://client-profile/codex 或 query://client-profile/claude-code。",
            _CLIENT_PROFILE_GUIDE_LINE,
        )
    )
    upgraded = _normalize_usage_guide_deploy_contract_lines(upgraded)
    if (
        "# Unified Query MCP" in upgraded
        and "## 最少执行规则" in upgraded
        and _CLIENT_PROFILE_GUIDE_LINE not in upgraded
    ):
        upgraded = _insert_prompt_lines(
            upgraded,
            anchor="## 最少执行规则",
            fallback_heading="## 最少执行规则",
            lines=[_CLIENT_PROFILE_GUIDE_LINE],
        )
    if (
        "# Unified Query MCP" in upgraded
        and "## 最少执行规则" in upgraded
        and (
            _RESOURCE_DISCOVERY_GUARD_GUIDE_LINE not in upgraded
            or _SIMPLE_QUERY_DIRECT_GUIDE_LINE not in upgraded
        )
    ):
        anchor = _CLIENT_PROFILE_GUIDE_LINE
        upgraded = upgraded.replace(f"\n{_RESOURCE_DISCOVERY_GUARD_GUIDE_LINE}", "")
        upgraded = upgraded.replace(f"\n{_SIMPLE_QUERY_DIRECT_GUIDE_LINE}", "")
        upgraded = _insert_prompt_lines(
            upgraded,
            anchor=anchor,
            fallback_heading="## 最少执行规则",
            lines=[
                _RESOURCE_DISCOVERY_GUARD_GUIDE_LINE,
                _SIMPLE_QUERY_DIRECT_GUIDE_LINE,
            ],
        )
    if (
        "# Unified Query MCP" in upgraded
        and "## 最少执行规则" in upgraded
        and "project-deploy-artifact" not in upgraded
    ):
        upgraded = _normalize_usage_guide_deploy_contract_lines(upgraded)
    if (
        "# Unified Query MCP" in upgraded
        and "## 最少执行规则" in upgraded
        and "不再停下来请求“是否继续”" not in upgraded
    ):
        upgraded = upgraded.replace(
            "7.0.6 {{clarity_repeat_line}}",
            "7.0.6 {{clarity_repeat_line}}\n7.0.7 {{continuous_execution_line}}",
        )
    if (
        "# Unified Query MCP" in upgraded
        and "## 最少执行规则" in upgraded
        and "禁止以兜底、兼容、静默降级" not in upgraded
    ):
        upgraded = upgraded.replace(
            "11. 如用户在“已完成”后发现问题，必须重新起一轮修复计划，并继续回写轨迹与验证；不得直接覆盖上一轮结论。",
            "11. 如用户在“已完成”后发现问题，必须重新起一轮修复计划，并继续回写轨迹与验证；不得直接覆盖上一轮结论。\n"
            f"{_ROOT_CAUSE_RULE_GUIDE_LINE}",
        )
    return upgraded
DEFAULT_CHAT_STYLE_HINTS = {
    "concise": {
        "style_hint": "输出风格：简洁，避免冗长。",
        "order_hint": "回答顺序：先给结论再给步骤。",
    },
    "balanced": {
        "style_hint": "输出风格：平衡，先结论后关键步骤。",
        "order_hint": "回答顺序：先给结论再给步骤。",
    },
    "detailed": {
        "style_hint": "输出风格：详细，覆盖关键前提、步骤与风险。",
        "order_hint": "回答顺序：先给结论再给步骤。",
    },
}


def default_employee_external_skill_sites() -> list[dict[str, object]]:
    return [
        {
            "id": "frontend-ui",
            "title": "UI 与界面一致性",
            "description": "适合界面审美、排版层级、交互一致性和设计系统类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/ui",
        },
        {
            "id": "frontend-css",
            "title": "CSS 与样式工程化",
            "description": "适合布局系统、响应式、动画和样式治理类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/css",
        },
        {
            "id": "frontend-vue",
            "title": "Vue 深度应用",
            "description": "适合 Vue 组件设计、Composition API 和工程实践类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/vue",
        },
        {
            "id": "frontend-browser",
            "title": "浏览器调试与性能排查",
            "description": "适合 Chrome DevTools、渲染链路和性能定位类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/chrome",
        },
        {
            "id": "frontend-architecture",
            "title": "架构设计与技术选型",
            "description": "适合系统拆分、边界设计、技术取舍和演进治理类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/software-architect",
        },
        {
            "id": "frontend-nodejs",
            "title": "JavaScript / Node.js 工程实践",
            "description": "适合 JS 工具链、构建脚本、运行时治理和工程交付类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/nodejs",
        },
    ]


def default_public_contact_channels() -> list[dict[str, object]]:
    return []


def default_bot_platform_connectors() -> list[dict[str, object]]:
    return []


def default_global_assistant_guide_modules() -> list[dict[str, object]]:
    return [
        {
            "id": "ai-chat",
            "name": "AI 对话中心",
            "summary": "统一的 AI 对话入口，可用于系统咨询、项目协作、状态排查和需求推进。",
            "paths": ["/ai/chat"],
            "permission": "menu.ai.chat",
            "enabled": True,
            "is_public": False,
            "sort_order": 10,
        },
        {
            "id": "projects",
            "name": "项目管理",
            "summary": "管理项目、项目成员、项目聊天设置与项目级工作入口。",
            "paths": ["/projects"],
            "permission": "menu.projects",
            "enabled": True,
            "is_public": False,
            "sort_order": 20,
        },
        {
            "id": "project-work-logs",
            "name": "项目工作日志",
            "summary": "在工作台里维护项目工作日志模板、生成记录、审核状态和后续追踪。",
            "paths": ["/work-logs"],
            "permission": "menu.projects",
            "enabled": True,
            "is_public": False,
            "sort_order": 25,
        },
        {
            "id": "employees",
            "name": "员工管理",
            "summary": "配置 AI 员工、职责、技能绑定、规则绑定和使用手册。",
            "paths": ["/employees"],
            "permission": "menu.employees",
            "enabled": True,
            "is_public": False,
            "sort_order": 30,
        },
        {
            "id": "skills",
            "name": "技能目录",
            "summary": "维护技能、技能资源与可复用能力资产。",
            "paths": ["/skills", "/skill-resources"],
            "permission": "menu.skills",
            "enabled": True,
            "is_public": False,
            "sort_order": 40,
        },
        {
            "id": "rules",
            "name": "规则管理",
            "summary": "维护通用规则、项目规则与员工规则，用于约束 AI 输出和执行方式。",
            "paths": ["/rules"],
            "permission": "menu.rules",
            "enabled": True,
            "is_public": False,
            "sort_order": 50,
        },
        {
            "id": "system-config",
            "name": "系统配置",
            "summary": "配置系统级开关、语音能力、默认提示词和运行参数。",
            "paths": ["/system/config"],
            "permission": "menu.system.config",
            "enabled": True,
            "is_public": False,
            "sort_order": 60,
        },
        {
            "id": "llm-providers",
            "name": "模型供应商",
            "summary": "接入文本、语音、图像等模型供应商，并配置默认模型。",
            "paths": ["/llm/providers"],
            "permission": "menu.llm.providers",
            "enabled": True,
            "is_public": False,
            "sort_order": 70,
        },
        {
            "id": "users-roles",
            "name": "用户与角色",
            "summary": "管理账号、角色、菜单权限和按钮权限。",
            "paths": ["/users", "/roles"],
            "permission": "menu.users",
            "enabled": True,
            "is_public": False,
            "sort_order": 80,
        },
        {
            "id": "materials",
            "name": "素材工作区",
            "summary": "查看素材库、声音资产和产出作品。",
            "paths": ["/materials", "/materials/voices", "/materials/works"],
            "permission": "",
            "enabled": True,
            "is_public": False,
            "sort_order": 90,
        },
        {
            "id": "studio",
            "name": "短片工作台",
            "summary": "围绕分镜、音轨、导出等流程完成短片制作。",
            "paths": ["/materials/studio"],
            "permission": "",
            "enabled": True,
            "is_public": False,
            "sort_order": 100,
        },
        {
            "id": "intro",
            "name": "官网介绍页",
            "summary": "对外展示产品定位、核心能力和整体工作流。",
            "paths": ["/intro"],
            "permission": "",
            "enabled": True,
            "is_public": True,
            "sort_order": 110,
        },
        {
            "id": "market",
            "name": "官网市场页",
            "summary": "对外展示产品能力、案例与市场化介绍内容。",
            "paths": ["/market"],
            "permission": "",
            "enabled": True,
            "is_public": True,
            "sort_order": 120,
        },
        {
            "id": "updates",
            "name": "官网更新页",
            "summary": "对外展示版本更新、功能变更和产品迭代记录。",
            "paths": ["/updates"],
            "permission": "",
            "enabled": True,
            "is_public": True,
            "sort_order": 130,
        },
    ]


def normalize_voice_allowed_usernames(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        username = str(raw_item or "").strip()[:120]
        if not username:
            continue
        dedupe_key = username.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(username)
        if len(normalized) >= 200:
            break
    return normalized


def normalize_voice_allowed_role_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        role_id = str(raw_item or "").strip().lower()[:64]
        if not role_id or role_id in seen:
            continue
        seen.add(role_id)
        normalized.append(role_id)
        if len(normalized) >= 50:
            break
    return normalized


def normalize_global_assistant_wake_phrase(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(part for part in text.split())
    return text.strip()[:80] or "你好助手"


def normalize_global_assistant_idle_timeout_sec(value: object) -> int:
    try:
        timeout_sec = int(value or 5)
    except (TypeError, ValueError):
        timeout_sec = 5
    return max(3, min(30, timeout_sec))


DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT = (
    "你好，我是系统状态助手。我会默认保持实时通话，随时帮你观察当前页面、系统状态和功能是否可用。"
)
DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT = (
    "你是系统状态助手。\n"
    "你的职责是基于当前页面、实时系统快照和本轮对话消息，直接回答系统状态、当前页面、当前项目、当前账号、功能可用性相关问题。\n"
    "你已经拿到本轮对话历史和实时快照；禁止回答“我无法访问之前的对话历史”或“我没有上下文”。\n"
    "如果答案就在本轮消息或快照里，直接给结论；如果快照里没有，就明确说明“当前快照里没有这项数据”，并指出缺少什么信息。\n"
    "不要把用户打回去重新描述，除非用户问题本身含糊到无法判断目标。\n"
    "当用户询问这个系统做什么、有哪些功能、怎么使用、去哪里配置、哪个页面负责什么时，先调用 global_assistant_system_guide 再回答。\n"
    "当用户询问当前页面接口状态、最近请求、响应数据、报错接口或页面是否真的拿到数据时，优先调用 global_assistant_browser_requests。\n"
    "当用户要求你检查页面元素、读取页面文字、点击、输入、选择、滚动、按键、切换页面、跳转路由或直接执行页面脚本时，优先调用 global_assistant_browser_actions。\n"
    "执行 click、fill、select 前，如果页面里是图标按钮或存在多个相邻按钮，先用 query_dom 查看候选元素，并优先使用 data-testid、id、aria-label、title 这些唯一标识来构造 selector；不要猜测或使用过宽的 .el-button、button:nth-child(...) 之类 selector。"
)
DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT = (
    "请严格逐字转写用户原话，只输出识别到的中文文本；不要补充、不要改写、不要总结、不要猜测、不要重复上一句；听不清就留空。"
)


def normalize_global_assistant_greeting_audio(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, object] = {}
    signature = str(value.get("signature") or "").strip()[:64]
    if signature:
        normalized["signature"] = signature
    storage_path = str(value.get("storage_path") or "").strip()[:500]
    if storage_path:
        normalized["storage_path"] = storage_path
    content_type = str(value.get("content_type") or "").strip()[:120]
    if content_type:
        normalized["content_type"] = content_type
    generated_at = str(value.get("generated_at") or "").strip()[:80]
    if generated_at:
        normalized["generated_at"] = generated_at
    try:
        file_size_bytes = int(value.get("file_size_bytes") or 0)
    except (TypeError, ValueError):
        file_size_bytes = 0
    if file_size_bytes > 0:
        normalized["file_size_bytes"] = file_size_bytes
    return normalized


def normalize_public_changelog(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()[:24000]


def normalize_query_mcp_public_base_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.query or parsed.fragment:
        return ""
    normalized_path = str(parsed.path or "").strip().rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", ""))


def normalize_query_mcp_clarity_confirm_threshold(value: object) -> int:
    try:
        threshold = int(value or 3)
    except (TypeError, ValueError):
        threshold = 3
    return max(1, min(5, threshold))


def normalize_chat_style_hints(value: object) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    source = value if isinstance(value, dict) else {}
    for key, defaults in DEFAULT_CHAT_STYLE_HINTS.items():
        raw_item = source.get(key) if isinstance(source, dict) else {}
        item = raw_item if isinstance(raw_item, dict) else {}
        normalized[key] = {
            "style_hint": str(item.get("style_hint") or defaults["style_hint"]).strip()[:500]
            or defaults["style_hint"],
            "order_hint": str(item.get("order_hint") or defaults["order_hint"]).strip()[:500]
            or defaults["order_hint"],
        }
    return normalized


def default_skill_registry_sources() -> dict[str, object]:
    return {
        "vett": {
            "enabled": True,
            "base_url": DEFAULT_VETT_BASE_URL,
            "timeout_ms": 10000,
            "risk_policy": {
                "allow": ["none", "low", "medium"],
                "review": ["high"],
                "deny": ["critical"],
            },
        }
    }


def normalize_employee_external_skill_sites(value: object) -> list[dict[str, object]]:
    defaults = default_employee_external_skill_sites()
    if not isinstance(value, list):
        return defaults

    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        item_id = str(raw_item.get("id") or "").strip()[:80]
        title = str(raw_item.get("title") or "").strip()[:120]
        description = str(raw_item.get("description") or "").strip()[:280]
        url = str(raw_item.get("url") or "").strip()[:500]
        dedupe_key = (item_id or title or url).lower()
        if not dedupe_key or dedupe_key in seen or not url:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "id": item_id or f"site-{len(normalized) + 1}",
                "title": title or "未命名站点",
                "description": description,
                "url": url,
            }
        )
        if len(normalized) >= 20:
            break
    return normalized


def normalize_public_contact_channels(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        channel_type = str(raw_item.get("type") or "qq_group").strip().lower()
        if channel_type != "qq_group":
            continue
        item_id = str(raw_item.get("id") or "").strip()[:80]
        title = str(raw_item.get("title") or "").strip()[:120]
        description = str(raw_item.get("description") or "").strip()[:280]
        qq_group_number = "".join(
            char for char in str(raw_item.get("qq_group_number") or "") if char.isdigit()
        )[:32]
        button_text = str(raw_item.get("button_text") or "").strip()[:40]
        guide_text = str(raw_item.get("guide_text") or "").strip()[:160]
        join_link = str(raw_item.get("join_link") or "").strip()[:500]
        qr_image_url = str(raw_item.get("qr_image_url") or "").strip()[:500]
        try:
            sort_order = int(raw_item.get("sort_order") or 0)
        except (TypeError, ValueError):
            sort_order = 0
        sort_order = max(0, min(999, sort_order))
        dedupe_key = (item_id or qq_group_number or title).lower()
        if not dedupe_key or dedupe_key in seen:
            continue
        if not qq_group_number and not join_link and not qr_image_url:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "id": item_id or f"contact-{len(normalized) + 1}",
                "enabled": bool(raw_item.get("enabled", True)),
                "type": "qq_group",
                "title": title or "加入用户交流群",
                "description": description,
                "qq_group_number": qq_group_number,
                "button_text": button_text or "复制群号",
                "guide_text": guide_text or "打开 QQ，搜索群号加入。",
                "join_link": join_link,
                "qr_image_url": qr_image_url,
                "sort_order": sort_order,
            }
        )
        if len(normalized) >= 10:
            break
    return normalized


def _normalize_bot_connector_id(raw_value: object, fallback: str) -> str:
    text = str(raw_value or "").strip().lower()[:80]
    for char in text:
        if (char.isascii() and char.isalnum()) or char in {"-", "_"}:
            continue
        text = text.replace(char, "-")
    while "--" in text:
        text = text.replace("--", "-")
    text = text.strip("-_")
    return text or fallback


def normalize_bot_platform_connectors(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    def normalize_scanned_chats(raw_value: object, *, connector_id: str, platform: str) -> list[dict[str, object]]:
        if not isinstance(raw_value, list):
            return []
        chats: list[dict[str, object]] = []
        seen_chat_ids: set[str] = set()
        for raw_chat in raw_value:
            if not isinstance(raw_chat, dict):
                continue
            chat_id = str(raw_chat.get("chat_id") or raw_chat.get("external_chat_id") or "").strip()[:200]
            if not chat_id or chat_id in seen_chat_ids:
                continue
            seen_chat_ids.add(chat_id)
            chat_platform = str(raw_chat.get("platform") or platform).strip().lower()
            if chat_platform != platform:
                chat_platform = platform
            chats.append(
                {
                    "platform": chat_platform,
                    "connector_id": connector_id,
                    "chat_id": chat_id,
                    "chat_name": str(raw_chat.get("chat_name") or raw_chat.get("name") or "").strip()[:200],
                    "chat_type": str(raw_chat.get("chat_type") or "").strip()[:80],
                    "chat_mode": str(raw_chat.get("chat_mode") or "").strip()[:80],
                    "description": str(raw_chat.get("description") or "").strip()[:300],
                    "source": str(raw_chat.get("source") or "bot_connector_scan").strip()[:160],
                    "scanned_at": str(raw_chat.get("scanned_at") or "").strip()[:80],
                }
            )
        return chats[:500]

    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    supported_platforms = {"qq", "feishu", "wechat"}
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        platform = str(raw_item.get("platform") or "").strip().lower()
        if platform not in supported_platforms:
            continue
        fallback_id = f"{platform}-connector-{len(normalized) + 1}"
        item_id = _normalize_bot_connector_id(raw_item.get("id"), fallback_id)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        try:
            sort_order = int(raw_item.get("sort_order") or 0)
        except (TypeError, ValueError):
            sort_order = 0
        sort_order = max(0, min(999, sort_order))
        default_receive_mode = "http_callback" if platform == "feishu" else "manual"
        event_receive_mode = str(raw_item.get("event_receive_mode") or default_receive_mode).strip().lower()
        allowed_receive_modes = {"http_callback", "long_connection", "manual", "polling"}
        if event_receive_mode not in allowed_receive_modes:
            event_receive_mode = default_receive_mode
        normalized.append(
            {
                "id": item_id,
                "enabled": bool(raw_item.get("enabled", True)),
                "platform": platform,
                "name": str(raw_item.get("name") or "").strip()[:120],
                "owner_username": str(raw_item.get("owner_username") or raw_item.get("created_by") or "").strip()[:120],
                "agent_name": "",
                "description": str(raw_item.get("description") or "").strip()[:280],
                "system_prompt": str(raw_item.get("system_prompt") or "").strip()[:4000],
                "chat_mode": "desktop_local_agent",
                "external_agent_type": (
                    str(raw_item.get("external_agent_type") or "").strip().lower()
                    if str(raw_item.get("external_agent_type") or "").strip().lower()
                    in {"codex_cli", "hermes", "claude_code"}
                    else "codex_cli"
                ),
                "sandbox_mode": (
                    str(raw_item.get("sandbox_mode") or raw_item.get("connector_sandbox_mode") or "workspace-write")
                    .strip()
                    .lower()
                    if str(raw_item.get("sandbox_mode") or raw_item.get("connector_sandbox_mode") or "workspace-write")
                    .strip()
                    .lower()
                    in {"workspace-write", "read-only", "full-access"}
                    else "workspace-write"
                ),
                "high_risk_tool_confirm": bool(raw_item.get("high_risk_tool_confirm", True)),
                "provider_id": str(raw_item.get("provider_id") or "").strip()[:120],
                "model_name": str(raw_item.get("model_name") or "").strip()[:160],
                "app_id": str(raw_item.get("app_id") or "").strip()[:160],
                "app_secret": str(raw_item.get("app_secret") or "").strip()[:200],
                "bot_open_id": str(raw_item.get("bot_open_id") or "").strip()[:160],
                "bot_user_id": str(raw_item.get("bot_user_id") or "").strip()[:160],
                "bot_union_id": str(raw_item.get("bot_union_id") or "").strip()[:160],
                "verification_token": str(raw_item.get("verification_token") or "").strip()[:200],
                "encrypt_key": str(raw_item.get("encrypt_key") or "").strip()[:200],
                "event_receive_mode": event_receive_mode,
                "auto_start_worker": bool(raw_item.get("auto_start_worker", False)),
                "reply_identity": (
                    str(raw_item.get("reply_identity") or "bot").strip().lower()
                    if str(raw_item.get("reply_identity") or "bot").strip().lower() in {"bot", "user"}
                    else "bot"
                ),
                "project_id": "",
                "scanned_chats": normalize_scanned_chats(
                    raw_item.get("scanned_chats"),
                    connector_id=item_id,
                    platform=platform,
                ),
                "guide_url": str(raw_item.get("guide_url") or "").strip()[:500],
                "sort_order": sort_order,
            }
        )
    return sorted(
        normalized,
        key=lambda item: (
            int(item["sort_order"]),
            str(item["platform"]),
            str(item.get("name") or ""),
            str(item["id"]),
        ),
    )


def _normalize_global_assistant_guide_module_id(raw_value: object, fallback: str) -> str:
    text = str(raw_value or "").strip().lower()[:80]
    for source, target in (
        (" ", "-"),
        ("/", "-"),
        ("\\", "-"),
        (".", "-"),
        (":", "-"),
    ):
        text = text.replace(source, target)
    while "--" in text:
        text = text.replace("--", "-")
    text = text.strip("-_")
    if text:
        return text
    return fallback


def normalize_global_assistant_guide_modules(value: object) -> list[dict[str, object]]:
    defaults = deepcopy(default_global_assistant_guide_modules())
    if not isinstance(value, list):
        return defaults

    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        raw_paths = raw_item.get("paths")
        path_values = raw_paths if isinstance(raw_paths, list) else [raw_paths]
        paths: list[str] = []
        seen_paths: set[str] = set()
        for raw_path in path_values:
            path = str(raw_path or "").strip()[:240]
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            paths.append(path)
            if len(paths) >= 12:
                break
        name = str(raw_item.get("name") or "").strip()[:120]
        summary = str(raw_item.get("summary") or "").strip()[:280]
        permission = str(raw_item.get("permission") or "").strip()[:120]
        fallback_id = f"module-{len(normalized) + 1}"
        module_id = _normalize_global_assistant_guide_module_id(
            raw_item.get("id") or name or (paths[0] if paths else ""),
            fallback_id,
        )
        dedupe_key = module_id.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        try:
            sort_order = int(raw_item.get("sort_order") or 0)
        except (TypeError, ValueError):
            sort_order = 0
        sort_order = max(0, min(999, sort_order))
        normalized.append(
            {
                "id": module_id,
                "name": name or module_id,
                "summary": summary,
                "paths": paths,
                "permission": permission,
                "enabled": bool(raw_item.get("enabled", True)),
                "is_public": bool(raw_item.get("is_public", False)),
                "sort_order": sort_order,
            }
        )
        if len(normalized) >= 40:
            break
    if not normalized:
        return defaults
    return sorted(
        normalized,
        key=lambda item: (
            int(item.get("sort_order") or 0),
            str(item.get("name") or "").strip(),
            str(item.get("id") or "").strip(),
        ),
    )


def normalize_skill_registry_sources(value: object) -> dict[str, object]:
    defaults = deepcopy(default_skill_registry_sources())
    if not isinstance(value, dict):
        return defaults

    normalized = deepcopy(defaults)
    raw_vett = value.get("vett")
    if not isinstance(raw_vett, dict):
        return normalized

    vett = dict(raw_vett)
    base_url = str(vett.get("base_url") or DEFAULT_VETT_BASE_URL).strip() or DEFAULT_VETT_BASE_URL
    try:
        timeout_ms = int(vett.get("timeout_ms") or 10000)
    except (TypeError, ValueError):
        timeout_ms = 10000
    timeout_ms = max(1000, min(60000, timeout_ms))

    raw_policy = vett.get("risk_policy")
    default_policy = defaults["vett"]["risk_policy"]
    normalized_policy: dict[str, list[str]] = {}
    for key in ("allow", "review", "deny"):
        source_values = raw_policy.get(key) if isinstance(raw_policy, dict) else default_policy.get(key)
        items: list[str] = []
        seen: set[str] = set()
        for item in source_values if isinstance(source_values, list) else []:
            text = str(item or "").strip().lower()
            if not text or text in seen:
                continue
            seen.add(text)
            items.append(text)
        normalized_policy[key] = items or list(default_policy.get(key) or [])

    normalized["vett"] = {
        "enabled": bool(vett.get("enabled", True)),
        "base_url": base_url.rstrip("/"),
        "timeout_ms": timeout_ms,
        "risk_policy": normalized_policy,
    }
    return normalized


def normalize_dictionaries(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}

    def normalize_image_resolution_token(raw: object) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        alias_map = {
            "720p": "720x720",
            "1080p": "1080x1080",
            "fhd": "1080x1080",
            "fullhd": "1080x1080",
            "4k": "2160x2160",
            "uhd": "2160x2160",
            "2160p": "2160x2160",
        }
        if lowered in alias_map:
            return alias_map[lowered]
        if lowered.endswith("p") and lowered[:-1].isdigit():
            base = lowered[:-1]
            return f"{base}x{base}"
        if "x" in lowered or "*" in lowered:
            raw_width, _, raw_height = lowered.replace("*", "x").partition("x")
            if raw_width.isdigit() and raw_height.isdigit():
                return f"{int(raw_width)}x{int(raw_height)}"
        return text

    normalized: dict[str, object] = {}
    for raw_key, raw_definition in value.items():
        dictionary_key = str(raw_key or "").strip()[:80]
        if not dictionary_key or not isinstance(raw_definition, dict):
            continue

        options: list[dict[str, str]] = []
        seen_option_ids: set[str] = set()
        for raw_option in raw_definition.get("options") if isinstance(raw_definition.get("options"), list) else []:
            if not isinstance(raw_option, dict):
                continue
            option_id = str(raw_option.get("id") or "").strip()[:80]
            if dictionary_key == "llm_image_resolutions":
                option_id = normalize_image_resolution_token(option_id)[:80]
            if not option_id or option_id in seen_option_ids:
                continue
            seen_option_ids.add(option_id)
            option_label = str(raw_option.get("label") or option_id).strip()[:120] or option_id
            if dictionary_key == "llm_image_resolutions":
                option_label = normalize_image_resolution_token(option_label)[:120] or option_id
            options.append(
                {
                    "id": option_id,
                    "label": option_label,
                    "description": str(raw_option.get("description") or "").strip()[:500],
                    "chat_parameter_mode": str(raw_option.get("chat_parameter_mode") or "").strip()[:40],
                }
            )
            if len(options) >= 100:
                break

        default_value = str(raw_definition.get("default_value") or "").strip()[:80]
        if dictionary_key == "llm_image_resolutions":
            default_value = normalize_image_resolution_token(default_value)[:80]

        definition: dict[str, Any] = {
            "key": dictionary_key,
            "label": str(raw_definition.get("label") or "").strip()[:120],
            "description": str(raw_definition.get("description") or "").strip()[:500],
            "default_value": default_value,
            "options": options,
        }
        normalized[dictionary_key] = definition

    return normalized


@dataclass
class SystemConfig:
    id: str = "global"
    enable_project_manual_generation: bool = False
    enable_employee_manual_generation: bool = False
    enable_user_register: bool = True
    chat_upload_max_limit: int = 6
    default_chat_system_prompt: str = ""
    desktop_agent_global_prompt: str = DEFAULT_DESKTOP_AGENT_GLOBAL_PROMPT
    employee_auto_rule_generation_enabled: bool = True
    employee_auto_rule_generation_source_filters: list[str] = field(
        default_factory=lambda: ["prompts_chat_curated"]
    )
    employee_auto_rule_generation_max_count: int = 3
    employee_auto_rule_generation_prompt: str = DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT
    employee_external_skill_sites: list[dict[str, object]] = field(
        default_factory=default_employee_external_skill_sites
    )
    global_assistant_guide_modules: list[dict[str, object]] = field(
        default_factory=default_global_assistant_guide_modules
    )
    voice_input_enabled: bool = False
    voice_input_provider_id: str = ""
    voice_input_model_name: str = ""
    voice_input_allowed_usernames: list[str] = field(default_factory=list)
    voice_input_allowed_role_ids: list[str] = field(default_factory=list)
    voice_output_enabled: bool = False
    voice_output_provider_id: str = ""
    voice_output_model_name: str = ""
    voice_output_voice: str = ""
    voice_output_reminder_volume: int = 40
    global_assistant_enabled: bool = True
    global_assistant_greeting_enabled: bool = True
    global_assistant_greeting_text: str = DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT
    global_assistant_chat_provider_id: str = ""
    global_assistant_chat_model_name: str = ""
    global_assistant_system_prompt: str = DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT
    global_assistant_transcription_prompt: str = DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT
    global_assistant_wake_phrase: str = "你好助手"
    global_assistant_idle_timeout_sec: int = 5
    global_assistant_greeting_audio: dict[str, object] = field(default_factory=dict)
    bot_platform_connectors: list[dict[str, object]] = field(
        default_factory=default_bot_platform_connectors
    )
    feishu_bot_long_connection_worker_enabled: bool = False
    public_contact_channels: list[dict[str, object]] = field(
        default_factory=default_public_contact_channels
    )
    public_changelog: str = ""
    query_mcp_public_base_url: str = ""
    query_mcp_clarity_confirm_threshold: int = 3
    query_mcp_bootstrap_prompt_template: str = DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE
    query_mcp_usage_guide_template: str = DEFAULT_QUERY_MCP_USAGE_GUIDE_TEMPLATE
    query_mcp_client_profile_template: str = DEFAULT_QUERY_MCP_CLIENT_PROFILE_TEMPLATE
    query_mcp_desktop_agent_profile_template: str = DEFAULT_QUERY_MCP_DESKTOP_AGENT_PROFILE_TEMPLATE
    chat_style_hints: dict[str, object] = field(default_factory=lambda: deepcopy(DEFAULT_CHAT_STYLE_HINTS))
    skill_registry_sources: dict[str, object] = field(
        default_factory=default_skill_registry_sources
    )
    dictionaries: dict[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.default_chat_system_prompt = str(self.default_chat_system_prompt or "").strip()[:8000]
        self.desktop_agent_global_prompt = str(self.desktop_agent_global_prompt or "").strip()[:12000]
        self.employee_auto_rule_generation_source_filters = [
            str(item or "").strip()
            for item in (self.employee_auto_rule_generation_source_filters or [])
            if str(item or "").strip()
        ][:12] or ["prompts_chat_curated"]
        try:
            self.employee_auto_rule_generation_max_count = int(
                self.employee_auto_rule_generation_max_count or 3
            )
        except (TypeError, ValueError):
            self.employee_auto_rule_generation_max_count = 3
        self.query_mcp_public_base_url = normalize_query_mcp_public_base_url(
            self.query_mcp_public_base_url
        )
        self.query_mcp_clarity_confirm_threshold = normalize_query_mcp_clarity_confirm_threshold(
            self.query_mcp_clarity_confirm_threshold
        )
        self.query_mcp_bootstrap_prompt_template = (
            normalize_query_mcp_bootstrap_prompt_template(
                self.query_mcp_bootstrap_prompt_template or DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE
            )[:24000]
            or DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE
        )
        self.query_mcp_usage_guide_template = (
            normalize_query_mcp_usage_guide_template(
                self.query_mcp_usage_guide_template or DEFAULT_QUERY_MCP_USAGE_GUIDE_TEMPLATE
            )[:32000]
            or DEFAULT_QUERY_MCP_USAGE_GUIDE_TEMPLATE
        )
        self.query_mcp_client_profile_template = (
            normalize_query_mcp_client_profile_template(
                self.query_mcp_client_profile_template or DEFAULT_QUERY_MCP_CLIENT_PROFILE_TEMPLATE
            )[:12000]
            or DEFAULT_QUERY_MCP_CLIENT_PROFILE_TEMPLATE
        )
        self.query_mcp_desktop_agent_profile_template = (
            normalize_query_mcp_desktop_agent_profile_template(
                self.query_mcp_desktop_agent_profile_template
                or DEFAULT_QUERY_MCP_DESKTOP_AGENT_PROFILE_TEMPLATE
            )[:12000]
            or DEFAULT_QUERY_MCP_DESKTOP_AGENT_PROFILE_TEMPLATE
        )
        self.chat_style_hints = normalize_chat_style_hints(self.chat_style_hints)
        self.employee_auto_rule_generation_max_count = max(
            1, min(6, self.employee_auto_rule_generation_max_count)
        )
        self.employee_auto_rule_generation_prompt = str(
            self.employee_auto_rule_generation_prompt or DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT
        ).strip()[:8000] or DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT
        self.employee_external_skill_sites = normalize_employee_external_skill_sites(
            self.employee_external_skill_sites
        )
        self.global_assistant_guide_modules = normalize_global_assistant_guide_modules(
            self.global_assistant_guide_modules
        )
        self.voice_input_provider_id = str(self.voice_input_provider_id or "").strip()[:120]
        self.voice_input_model_name = str(self.voice_input_model_name or "").strip()[:160]
        self.voice_input_allowed_usernames = normalize_voice_allowed_usernames(
            self.voice_input_allowed_usernames
        )
        self.voice_input_allowed_role_ids = normalize_voice_allowed_role_ids(
            self.voice_input_allowed_role_ids
        )
        self.voice_output_provider_id = str(self.voice_output_provider_id or "").strip()[:120]
        self.voice_output_model_name = str(self.voice_output_model_name or "").strip()[:160]
        self.voice_output_voice = str(self.voice_output_voice or "").strip()[:200]
        try:
            self.voice_output_reminder_volume = int(self.voice_output_reminder_volume)
        except (TypeError, ValueError):
            self.voice_output_reminder_volume = 40
        self.voice_output_reminder_volume = max(0, min(100, self.voice_output_reminder_volume))
        self.global_assistant_chat_provider_id = str(
            self.global_assistant_chat_provider_id or ""
        ).strip()[:120]
        self.global_assistant_chat_model_name = str(
            self.global_assistant_chat_model_name or ""
        ).strip()[:160]
        self.global_assistant_greeting_text = str(
            self.global_assistant_greeting_text
            or DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT
        ).strip()[:1000]
        self.global_assistant_system_prompt = str(
            self.global_assistant_system_prompt or DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT
        ).strip()[:8000]
        self.global_assistant_transcription_prompt = str(
            self.global_assistant_transcription_prompt or DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT
        ).strip()[:1000]
        self.global_assistant_wake_phrase = normalize_global_assistant_wake_phrase(
            self.global_assistant_wake_phrase
        )
        self.global_assistant_idle_timeout_sec = normalize_global_assistant_idle_timeout_sec(
            self.global_assistant_idle_timeout_sec
        )
        self.global_assistant_greeting_audio = normalize_global_assistant_greeting_audio(
            self.global_assistant_greeting_audio
        )
        self.bot_platform_connectors = normalize_bot_platform_connectors(
            self.bot_platform_connectors
        )
        self.public_contact_channels = normalize_public_contact_channels(
            self.public_contact_channels
        )
        self.public_changelog = normalize_public_changelog(self.public_changelog)
        self.skill_registry_sources = normalize_skill_registry_sources(
            self.skill_registry_sources
        )
        self.dictionaries = normalize_dictionaries(self.dictionaries)


def normalize_system_config_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    allowed_fields = {item.name for item in fields(SystemConfig)}
    return {
        str(key): value
        for key, value in payload.items()
        if isinstance(key, str) and key in allowed_fields
    }


class SystemConfigStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "system-config.json"

    def get_global(self) -> SystemConfig:
        if not self._path.exists():
            return SystemConfig()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        payload = normalize_system_config_payload(data)
        config = SystemConfig(**payload)
        if asdict(config) != data:
            self.save_global(config)
        return config

    def save_global(self, config: SystemConfig) -> None:
        self._path.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def patch_global(self, updates: dict) -> SystemConfig:
        current = self.get_global()
        payload = asdict(current)
        payload.update(updates)
        payload["updated_at"] = _now_iso()
        if not payload.get("created_at"):
            payload["created_at"] = _now_iso()
        updated = SystemConfig(**payload)
        self.save_global(updated)
        return updated
