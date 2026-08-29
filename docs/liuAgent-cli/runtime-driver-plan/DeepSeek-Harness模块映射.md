# DeepSeek-Harness 模块映射与代码检查清单

## 使用规则

本文件不是概念参考，而是每个阶段的源码检查入口。AI 修改当前项目之前必须：

1. 打开当前阶段列出的 DeepSeek 源码文件。
2. 同时打开对应测试、不变量和文档文件（如果存在）。
3. 记录参考实现解决的问题、状态边界、取消行为、错误码和资源释放方式。
4. 检查当前项目真实代码，不假设两边接口或运行时相同。
5. 形成“采用 / 改造 / 不采用”结论后，再确定实现方案。

参考仓库根目录：

`/Volumes/work_mac_1_5T/self/deepseek-harness/`

当前项目根目录：

`/Volumes/work_mac_1_5T/self/ai-employee/`

## P0：异步入口、实时事件和交互不卡顿

### DeepSeek-Harness 参考模块

- `packages/core/agent-loop/src/index.ts`
- `packages/core/agent-loop/src/agent.ts`
- `packages/core/agent-loop/src/runtime-context.ts`
- `packages/core/agent/src/dispatch.ts`
- `packages/core/agent/src/inbox.ts`
- `packages/api/gateway/src/stream-protocol.ts`
- `packages/api/gateway/src/stream-server.ts`
- `packages/api/session-controller/src/remote-events.ts`
- `packages/api/session-controller/src/control.ts`
- `docs/architecture.zh.md`
- `docs/agent-lifecycle.zh.md`

### 当前项目检查位置

- `web-admin/frontend/src-tauri/src/main.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/runtime.rs`
- `web-admin/frontend/src/utils/native-desktop-bridge.js`
- `web-admin/frontend/src/views/projects/ProjectChat.vue`

### 必须对比的问题

- 启动请求是否等待完整 Turn。
- 实时事件和持久事件是否分层。
- 事件断线后能否按游标补偿。
- 前端是否把请求 pending 当作 Runtime 状态。
- 流式增量是否造成过多 IPC、响应式更新和磁盘写入。

## P1：Job、取消、超时和资源回收

### DeepSeek-Harness 参考模块

- `packages/jobs/jobs/src/types.ts`
- `packages/jobs/jobs/src/index.ts`
- `packages/jobs/jobs-local/src/index.ts`
- `packages/guard/timeout-policy/src/index.ts`
- `packages/subprocess/subprocess/src/index.ts`
- `packages/subprocess/subprocess-local/src/index.ts`
- `packages/interaction/user-approval/src/index.ts`
- `packages/interaction/user-questions/src/index.ts`
- `docs/subsystems/core.zh.md`
- `docs/defensive-patterns.zh.md`

### 当前项目检查位置

- `web-admin/frontend/src-tauri/src/liuagent_core/runtime.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/state`
- `web-admin/frontend/src-tauri/src/main.rs`
- `web-admin/frontend/src/utils/local-ai-task-store.js`
- `web-admin/frontend/src/views/projects/ProjectChat.vue`

### 必须对比的问题

- cancel 是否同步、幂等并最终等待资源释放。
- Job 是否有 owner、并发限制和不可变快照。
- 模型、工具、审批和用户等待是否都有 timeout 与 abort。
- 取消后是否能确认子进程和后台任务已经退出。
- teardown 失败时是否诚实地标记为 failed/stopping，而不是伪造 cancelled。

## P2：Driver、Session 和 EventLog

### DeepSeek-Harness 参考模块

- `packages/core/agent-loop/src/agent.ts`
- `packages/core/agent-loop/src/tool-calls.ts`
- `packages/core/session/src/index.ts`
- `packages/core/session/src/types.ts`
- `packages/core/session/src/json.ts`
- `packages/core/session/src/chunk-rows.ts`
- `packages/core/session/src/seq-ranges.ts`
- `packages/session/session-persistence-jsonl/src/index.ts`
- `packages/session/session-persistence-jsonl/src/format.ts`
- `packages/session/session-persistence-jsonl/src/win32.ts`
- `packages/core/tools/src/index.ts`
- `packages/core/tools/src/types.ts`
- `packages/core/tools/src/presentation.ts`
- `docs/tool-execution-pipeline.zh.md`

### 当前项目检查位置

- `web-admin/frontend/src-tauri/src/liuagent_core/runtime.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/state`
- `web-admin/frontend/src-tauri/src/liuagent_core/types.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/definitions.rs`

### 必须对比的问题

- Session 事实、Runtime 实时状态和 UI 投影是否分离。
- event_seq 是否单调递增且支持增量读取。
- 流式 chunk 是否可压缩存储并保持恢复顺序。
- 工具调用是否先记录、再执行、再记录不可变结果。
- Driver 是否在每个步骤边界处理取消、失败和下一步输入。

## P3：Projection、Plan、Checkpoint 和 Inbox

### DeepSeek-Harness 参考模块

- `packages/plan/plan-mode/src/index.ts`
- `packages/plan/plan-mode/src/client.ts`
- `packages/plan/plan-mode/src/types.ts`
- `packages/core/agent/src/inbox.ts`
- `packages/core/agent/src/consumed-work.ts`
- `packages/session/session-checkpoint-policy/src/index.ts`
- `packages/compaction/compaction/src/checkpoint.ts`
- `packages/context/session-reference/src/projection.ts`
- `packages/api/session-controller/src/history.ts`
- `packages/api/session-controller/src/model-selection-projection.ts`

### 当前项目检查位置

- `web-admin/frontend/src-tauri/src/liuagent_core/planning.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/state`
- `web-admin/frontend/src-tauri/src/liuagent_core/types.rs`
- `web-admin/frontend/src/views/projects/ProjectChat.vue`
- `web-admin/frontend/src/utils/local-ai-task-store.js`

### 必须对比的问题

- Plan 是否是持久状态，而不仅是前端展示事件。
- 用户选择是否在下一次合法步骤前保持 pending。
- 恢复是否依据 step_id、attempt 和 checkpoint，而不是聊天文本猜测。
- Inbox 是否支持 claim、重复领取保护和 follow-up 模式。
- Projection 是否可以从事件重新折叠得到。

## P4：工具流水线、子智能体、Workflow 和跨平台进程

### DeepSeek-Harness 参考模块

- `packages/core/tools/src/index.ts`
- `packages/core/tools/src/schema.ts`
- `packages/core/tools/src/ts-types.ts`
- `packages/interaction/permission-presets/src/index.ts`
- `packages/interaction/commands/src/index.ts`
- `packages/subagent/subagent/src/index.ts`
- `packages/subagent/subagent-spawn-in-process/src/index.ts`
- `packages/subagent/subagent-in-process-driver/src/index.ts`
- `packages/workflow/workflow/src/index.ts`
- `packages/workflow/workflow-worker-thread/src/host.ts`
- `packages/workflow/workflow-worker-thread/src/protocol.ts`
- `packages/workflow/workflow-worker-thread/src/runtime.ts`
- `packages/workflow/workflow-worker-thread/src/worker.ts`
- `packages/shell/shell/src/index.ts`
- `packages/shell/bash-local/src/index.ts`
- `packages/shell/pwsh-local/src/index.ts`
- `packages/shell/tool-bash/src/index.ts`
- `packages/shell/tool-pwsh/src/index.ts`
- `packages/shell/tool-bash-persistent/src/index.ts`
- `packages/shell/tool-pwsh-persistent/src/index.ts`
- `packages/terminal/terminal/src/index.ts`
- `packages/fs/fs/src/index.ts`
- `packages/fs/tool-fs/src/read.ts`
- `packages/fs/tool-fs/src/write.ts`
- `packages/fs/tool-fs/src/sandbox.ts`
- `packages/mcp/mcp-client/src/connection.ts`
- `packages/mcp/mcp-client/src/transport.ts`
- `packages/context/agent-instructions/src/index.ts`
- `packages/compaction/compaction-basic/src/index.ts`
- `packages/runtime-diagnostics/invariants/src/index.ts`
- `docs/defensive-patterns.zh.md`

### 当前项目检查位置

- `web-admin/frontend/src-tauri/src/liuagent_core/tools`
- `web-admin/frontend/src-tauri/src/liuagent_core/permission.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/runtime.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/paths.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/state`
- `web-admin/frontend/src-tauri/src/main.rs`
- `web-admin/frontend/src-tauri/tauri.conf.json`

阶段 P4 的 `jobs.rs`、`driver.rs`、`projection.rs` 和 `process_supervisor.rs` 是本计划拟新增的当前项目文件，不是现有文件；修改前必须先检查当前 `runtime.rs`、`state/` 和进程工具实现，再决定拆分边界，禁止为了匹配参考路径而机械创建空模块。

### 必须对比的问题

- 工具是否经过统一的 pre/execute/post 流水线。
- 文件、Shell、MCP、网络和进程能力是否有清晰适配边界。
- 子智能体是否有 owner、取消和资源回收边界。
- Worker 崩溃或终止后是否能得到确定终态。
- 上下文是否有预算、压缩和历史裁剪策略。
- macOS 与 Windows 是否分别处理 shell、进程树、路径和权限。

## 结论记录模板

每个阶段的文档必须补充以下内容，不能只写“参考 DeepSeek-Harness”：

```text
参考模块：<实际读取的路径>
采用设计：<直接借鉴的机制>
适配设计：<因 Tauri/Rust/Vue 或平台差异而改造的机制>
不采用设计：<不适用的机制及原因>
当前代码证据：<当前项目实际入口和行为>
验证方式：<测试、构建或运行验证>
```

如果无法读取某个参考模块，必须在阶段文档记录阻塞原因，不得凭印象补全实现。
