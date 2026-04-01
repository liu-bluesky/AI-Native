# Claude CLI 可借鉴能力与 MCP 升级映射

> 日期：2026-04-01
> 来源参考：`/Users/liulantian/self/claude-code-cli/docs`
> 适用对象：当前项目的统一查询 MCP / 外部 Agent 接入路线

## 1. 结论先行

这次阅读 `claude-code-cli/docs` 后，结论很明确：

- 它最强的地方不是终端 UI。
- 它最强的地方是 Agent Runtime。
- 你当前系统最该借鉴的，不是做一个类似的 CLI 壳，而是把这些 runtime 能力沉淀为 MCP 服务能力。

换句话说：

> Claude Code 值得借鉴的是运行时内核，不是外壳形态。

因此对当前项目最合理的升级方向仍然成立：

- 不重做 CLI
- 不模仿 Ink 终端 UI
- 不复制命令行交互细节
- 重点把 `/mcp/query/sse` 升级成可被外部 CLI 复用的 Agent Capability Gateway

## 2. 这次主要看了什么

本次重点阅读了以下文档：

- `architecture-and-workflows.md`
- `modules/04-tool-system-and-permissions.md`
- `modules/05-query-engine-and-execution-loop.md`
- `modules/06-config-and-session-persistence.md`
- `modules/07-extensibility-mcp-plugins-skills.md`
- `project-architecture-quickstart.md`

这些文档共同说明了一件事：

- Claude CLI 不是“一个会调模型的命令行”
- 而是“一个围绕消息流、工具池、权限、会话恢复、扩展平面构建的开发型 Agent Runtime”

## 3. 真正值得借鉴的 5 个点

## 3.1 动态工具池，不是静态工具清单

Claude CLI 的工具系统不是“把所有工具都塞给模型”。

它强调的是：

- 工具是否存在
- 工具是否可见
- 工具当前是否允许调用

这三件事是分开的。

它的关键优点：

- 工具集合会根据模式、权限、平台、上下文动态变化。
- deny 规则会在工具暴露前先过滤，而不是等调用时再拒绝。
- MCP 工具和内置工具会统一进入同一个 runtime tool pool。

对当前系统的启发：

- 现在你的统一查询 MCP 更像“统一工具入口”。
- 后续应该升级成“动态能力暴露入口”。

建议映射到 `/mcp/query/sse`：

- 增加 `resolve_available_capabilities`
- 增加 `check_operation_policy`
- 增加 `classify_command_risk`
- 增加“先判断再暴露”的能力筛选逻辑

也就是说，未来客户端不该自己猜“哪些工具能用”，而应该从服务端拿到当下真实可用的能力视图。

## 3.2 QueryEngine 思路，比普通聊天接口更重要

Claude CLI 的核心不是单次 completion，而是：

- 会话级 QueryEngine
- 单轮 query loop
- 工具调用后重新进入消息流
- 异常恢复、compact、fallback、budget 控制

这说明它把 agent 执行看成一条长生命周期工作流，而不是简单问答。

对当前系统的启发：

- 你现在已有 `AgentOrchestrator`、`ToolExecutor`、`ConversationManager`
- 说明你已经有 runtime 基础
- 但这些能力还没有通过统一查询 MCP 以“高层能力”的方式对外暴露

建议映射到 `/mcp/query/sse`：

- 增加 `analyze_task`
- 增加 `generate_execution_plan`
- 增加 `summarize_checkpoint`
- 增加 `resume_work_session`

重点不是把当前后端直接包装成聊天接口，而是把“会话内核”拆成可被 CLI 调用的能力。

## 3.3 会话持久化本质上是事件日志，不只是聊天记录

Claude CLI 的 session persistence 很值得借鉴。

它保存的不是简单 user / assistant 文本，而是：

- transcript
- mode
- worktree state
- compact boundary
- attribution
- 恢复元信息

这意味着它保存的是“可恢复执行轨迹”。

对当前系统的启发：

- 你现在已经有 `save_project_memory`
- 也有 `ConversationManager`
- 但项目级记忆更偏知识沉淀，还不是完整工作轨迹

建议映射到 `/mcp/query/sse`：

- 增加 `save_work_facts`
- 增加 `append_session_event`
- 增加 `resume_work_session`
- 增加 `get_recent_decisions`

这会把当前系统从“记住结论”升级为“记住任务运行状态”。

这也是你未来要支持更强 CLI 协同的关键能力。

## 3.4 扩展不是附属物，而是运行时本体

Claude CLI 对 MCP、插件、技能的处理很成熟。

它的核心不是“支持很多扩展形式”，而是：

- 最终把这些东西统一汇入 command / tool / resource 三类对象
- 再统一进入同一个 runtime

这点很重要。

因为这意味着：

- 扩展来源可以不同
- 但运行时对象模型必须收敛

对当前系统的启发：

- 你现在已经有 Skills、Rules、Memory、Project MCP、Query MCP
- 但这些能力对外暴露时仍偏“按模块分开”
- `/mcp/query/sse` 还没有成为真正的统一 capability surface

建议映射到 `/mcp/query/sse`：

- 把上下文、规则、规划、策略、恢复、交付能力统一成稳定 tool/resource 集合
- 为不同客户端提供 profile 化使用说明
- 让 query MCP 不只是“找 ID 的地方”，而是“统一能力入口”

## 3.5 权限前置，而不是后置补救

Claude CLI 文档里最值得借鉴的一点，是权限深度嵌入 runtime。

它不是：

- 模型先决定
- 系统再兜底拒绝

而是：

- 工具发现前先过滤
- 调用前再判断
- 权限上下文本身就是 runtime 的一部分

对当前系统的启发：

- 你现在已有 local connector、sandbox mode、tool filtering
- 这说明底层执行控制已经有基础
- 但还缺统一的、面向外部 CLI 的策略判断接口

建议映射到 `/mcp/query/sse`：

- `check_operation_policy`
- `check_workspace_scope`
- `explain_block_reason`
- `resolve_execution_mode`

这样外部 CLI 在真正调用 shell 或写文件前，先通过你的服务做策略判断。

## 4. 哪些不值得抄

有些东西看起来很强，但并不适合当前项目优先投入。

当前不建议跟的内容：

- Ink 终端 UI
- REPL 交互壳
- slash command 细节
- local-jsx 命令形态
- 启动 fast-path 优化
- 终端级弹窗与面板系统

原因不是这些不重要，而是：

- 它们主要提升的是“自有 CLI 体验”
- 不是“作为 MCP 服务增强外部 CLI”的核心价值

你当前产品应该优先把投资放在：

- 统一能力暴露
- 上下文理解
- 执行策略
- 会话恢复
- 可审计轨迹

## 5. 和当前系统的映射关系

当前系统已经有一些很好的基础，不是从零开始。

### 5.1 已经有的基础

- 统一入口：`/mcp/query/sse`
- 统一使用说明：`query://usage-guide`
- 项目协作编排：`execute_project_collaboration`
- 会话内核雏形：`AgentOrchestrator`
- 工具执行器：`ToolExecutor`
- 对话上下文管理：`ConversationManager`
- 本地执行桥接：`local_connector_*`
- 前端统一接入弹窗：`UnifiedMcpAccessDialog.vue`

### 5.2 当前最主要的缺口

- 缺少 QueryEngine 风格的高层能力输出
- 缺少运行时能力视图，而不是静态工具清单
- 缺少事件化工作轨迹和恢复接口
- 缺少策略判断工具的标准化暴露
- 缺少针对不同 CLI 的接入画像

## 6. 对 `/mcp/query/sse` 的直接升级建议

如果把这次借鉴结果直接落到 `/mcp/query/sse`，建议分三层做。

### 6.1 第一层：先补高层智能体工具

优先加：

- `analyze_task`
- `extract_constraints`
- `generate_execution_plan`
- `resolve_relevant_context`

这是最接近 Claude CLI QueryEngine 价值的部分。

### 6.2 第二层：补策略判断工具

优先加：

- `check_operation_policy`
- `classify_command_risk`
- `check_workspace_scope`
- `resolve_execution_mode`

这是最接近 Claude CLI 权限模型价值的部分。

### 6.3 第三层：补恢复与轨迹工具

优先加：

- `save_work_facts`
- `append_session_event`
- `resume_work_session`
- `summarize_checkpoint`

这是最接近 Claude CLI session persistence 价值的部分。

## 7. 推荐的新文档关系

结合当前已有文档，建议后续阅读关系变成：

- `统一查询MCP联调示例.md`
  - 解决“怎么接”
- `统一查询MCP升级规划.md`
  - 解决“往哪升”
- 本文
  - 解决“为什么这么升，以及从 Claude CLI 借鉴什么”

## 8. 最终判断

这次对 `claude-code-cli/docs` 的阅读，最终没有推翻当前路线，反而进一步验证了你现在这个判断是对的：

- 不要和大厂比 CLI 外壳
- 要做能服务多个 CLI 的 MCP 能力层
- `/mcp/query/sse` 应该继续保留为稳定入口
- 真正要补的是 runtime intelligence，而不是 terminal UI

一句话总结：

> Claude CLI 值得借鉴的是“动态工具池 + QueryEngine + 权限前置 + 可恢复事件日志 + 统一扩展平面”，这些都更适合做成你的 MCP 服务能力，而不是再做一个新的 CLI。
