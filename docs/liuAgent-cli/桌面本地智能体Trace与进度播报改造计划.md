# 桌面本地智能体 Trace 与进度播报改造计划

## 背景

当前桌面本地智能体已经具备模型调用、本地工具调用、权限确认和运行状态恢复能力，但用户侧看到的过程信息仍偏粗粒度，常见表现是：

- 只显示“启动桌面本地 Agent Runtime，等待模型计算”。
- 工具调用结果能看到，但缺少类似 Codex / Claude 的执行转录。
- AI 阶段性发现、下一步动作、工具意图没有稳定展示。
- 失败恢复时日志容易重复，用户难以判断真实执行链路。

目标不是展示隐藏思维链，而是展示可审计的可见执行轨迹：

- AI 当前发现了什么。
- AI 下一步准备做什么。
- 模型什么时候开始/结束计算。
- 调用了什么工具、参数是什么、结果是什么。
- 改了哪些文件、diff 摘要是什么。
- 跑了什么命令、输出和退出状态是什么。
- 失败后系统如何自动修复或暂停。

## 核心原则

1. **不展示隐藏思维链**
   - 不依赖模型 raw chain-of-thought。
   - 只展示模型明确输出的可见进度播报、计划、工具调用和执行结果。

2. **事件类型固定，事件内容动态**
   - `type` / `status` / `event_id` 等协议字段固定。
   - `summary` / `next_action` / `detail` 等内容由 AI 或 Runner 动态生成。

3. **Runner 发真实事件**
   - 前端不伪造执行细节。
   - 模型调用、工具调用、命令输出、文件 diff 都由 Tauri Runner 或工具执行层发事件。

4. **前端只负责渲染和折叠**
   - 前端把事件展示为时间线、卡片、折叠输出。
   - 不在前端推断核心执行状态。

5. **可恢复、可追溯**
   - 运行事件写入本地 JSONL。
   - 刷新页面或恢复失败任务时可以重建同一条执行轨迹。

## 术语定义

| 术语 | 含义 |
|---|---|
| Agent Trace | 一次智能体运行的完整事件轨迹。 |
| Trace Event | 运行轨迹中的单个事件，如工具开始、命令输出、文件修改。 |
| Trace Span | 可展开的执行片段，如一次 `Bash(...)` 或 `Read(...)`。 |
| Progress Update | AI 面向用户生成的阶段性进度播报，不是隐藏思维链。 |
| Tool Transcript | 工具调用和工具结果的可见转录。 |
| Runtime Event Stream | Runner 实时推送给前端的事件流。 |

## 事件协议设计

### AgentTraceEvent 基础结构

```json
{
  "event_id": "evt_xxx",
  "run_id": "runtime_xxx",
  "chat_session_id": "chat_xxx",
  "parent_event_id": "",
  "type": "tool_call_started",
  "status": "running",
  "title": "Read(login.html)",
  "summary": "读取 login.html",
  "detail": "",
  "cwd": "/Volumes/work_mac_1_5T/work/test",
  "tool_name": "read_file",
  "input_preview": "",
  "output_preview": "",
  "metadata": {},
  "created_at_epoch_ms": 0,
  "finished_at_epoch_ms": 0,
  "duration_ms": 0
}
```

### 字段说明

| 字段 | 说明 |
|---|---|
| `event_id` | 事件唯一 ID，用于去重。 |
| `run_id` | 本轮本地智能体运行 ID。 |
| `chat_session_id` | 聊天会话 ID。 |
| `parent_event_id` | 父事件 ID，用于 span 分组。 |
| `type` | 固定事件类型。 |
| `status` | `pending` / `running` / `completed` / `failed` / `blocked` / `waiting_user`。 |
| `title` | 前端展示标题。 |
| `summary` | 简短摘要。 |
| `detail` | 可展开详情。 |
| `cwd` | 本机工作目录。 |
| `tool_name` | 工具名。 |
| `input_preview` | 输入参数摘要，需脱敏。 |
| `output_preview` | 输出摘要，长内容折叠。 |
| `metadata` | 类型相关扩展字段。 |
| `created_at_epoch_ms` | 创建时间。 |
| `finished_at_epoch_ms` | 完成时间。 |
| `duration_ms` | 耗时。 |

## 事件类型全集

建议完整协议包含 67 个事件类型。

| 类别 | 数量 | 事件类型 |
|---|---:|---|
| 运行生命周期 | 8 | `run_queued`、`run_started`、`run_resumed`、`run_paused`、`run_cancelled`、`run_finished`、`run_failed`、`run_state_changed` |
| 模型调用 | 5 | `model_call_started`、`model_token_chunk`、`model_call_finished`、`model_call_failed`、`model_output_normalized` |
| 计划与步骤 | 7 | `plan_created`、`plan_updated`、`plan_replaced`、`plan_step_started`、`plan_step_finished`、`plan_step_failed`、`plan_step_blocked` |
| 通用工具调用 | 5 | `tool_call_planned`、`tool_call_started`、`tool_call_progress`、`tool_call_finished`、`tool_call_failed` |
| 文件探索与修改 | 10 | `workspace_scanned`、`file_listed`、`file_searched`、`file_read_started`、`file_read_finished`、`file_edit_started`、`file_diff_generated`、`file_written`、`file_deleted`、`file_edit_finished` |
| 命令执行 | 6 | `command_planned`、`command_started`、`command_output_chunk`、`command_finished`、`command_failed`、`command_timeout` |
| MCP 调用 | 4 | `mcp_tool_started`、`mcp_tool_finished`、`mcp_resource_read`、`mcp_failed` |
| 网络/下载 | 5 | `network_request_started`、`network_response_received`、`download_started`、`download_finished`、`network_failed` |
| 权限确认 | 4 | `permission_required`、`permission_granted`、`permission_denied`、`permission_expired` |
| 验证与恢复 | 8 | `verification_started`、`verification_finished`、`test_started`、`test_finished`、`repair_attempted`、`schema_repaired`、`retry_scheduled`、`loop_paused` |
| UI/安全展示 | 5 | `output_collapsed`、`output_expanded`、`secret_redacted`、`artifact_created`、`user_input_required` |

## 第一阶段最小闭环

第一阶段不一次性实现 67 个事件，先打通可见执行体验。

### 已修复的进度播报 Bug

当前改造先修正以下问题，后续实现完整 Trace Viewer 时必须保持这些边界：

- `progress_update` 是一等 Runtime 事件，不再只靠前端固定文案模拟。
- 前端启动日志只表示 Runtime 状态，不再写死 `Computing...`，避免和真实 `model_call_started` 重复。
- `model_step.content_preview` 不再作为过程日志展示，避免把最终回答或“初步解决路径清单”重复塞进执行过程。
- 只有“模型可见文本 + 同时请求工具调用”的场景才发 `progress_update`；纯最终回答不发进度播报。
- `Progress update` 的文案来自模型可见输出，不是隐藏思维链。

### 已修复第一版：授权续跑缺少执行细节

已发现一个新的 Trace 断层问题：

```text
用户输入：检测注册页面有几个表单
模型返回：1 个 run_command 工具调用
状态：等待授权
授权提示：请在当前回答气泡中选择允许或拒绝；允许后会用同一个工具调用继续执行
问题：授权前没有展示足够的工具调用细节；用户授权后，续跑过程没有继续展示 run_command 的执行细节、命令输出和工具结果。
```

这个问题说明当前 Runtime / 前端对 `permission_required -> permission_granted -> tool_call_resumed -> command_started -> command_output_chunk -> command_finished -> tool_result` 这条链路没有完整 Trace。

必须补齐：

- 授权前展示待执行工具的真实参数摘要，例如 `run_command(<command>)`，而不是只显示“标准模型工具调用”。第一版已补充工具名和命令预览。
- 用户点击允许后，Runtime 从上次 `waiting_approval` 状态中恢复 pending tool，并继续使用同一个 `tool_call_id` 执行。第一版已实现 pending tool replay，并把工具结果接回后续模型循环。
- 授权续跑必须展示：
  - `permission_granted`
  - `tool_call_resumed`
  - `command_started`
  - `command_output_chunk`
  - `command_finished`
  - `tool_result`
- 前端用同一个 span 把授权前后的事件串起来，避免用户看不到“授权后到底执行了什么”。
- 如果命令没有输出，也要显示退出码、耗时和空输出说明。

第一版当前已具备：

- `permission.required` 不再被展示成普通 `Result: run_command`。
- `approval_required` 事件携带 `tool_call_id` / `tool_name`。
- 授权后 Runtime 直接 replay pending tool，而不是只靠模型重新生成同一个工具调用。
- replay 会发出 `tool_call_started` 和 `tool_result`，并把结果作为 tool observation 交给后续模型步骤。
- `search_text` 传入文件路径时会自动修正为目录 + `glob`，避免 `path is not a directory` 循环。
- 前端实时 Tauri 事件订阅已改为使用同一套 transcript 渲染，不再只显示 `operation.summary`；运行中应能看到 `Computing`、`Progress update`、`Bash(cmd)`、命令输出和退出码。
- 实时事件与最终 `runtime_events` 回放共用事件去重，避免运行中显示一次、结果返回后再重复显示一次。
- Tauri 事件订阅保留 `@tauri-apps/api/event.listen` 主路径，并补充 `window.__TAURI__.event.listen` fallback，避免桌面环境里 invoke 可用但 event listen 静默失败。
- `liuagent_start_local_chat` 会收集 event sink 发出的实时事件，并合并进最终 `LocalChatResult.runtime_events`；即使实时订阅失败，任务结束后也能回放模型调用、工具调用和命令 Trace 细节。
- `liuagent_core::start_local_chat_inner` 现在在 Core 层收集所有 event sink 事件，并合并进 `LocalChatResult.runtime_events`。这修复了只显示“启动 Runtime / 等待模型调用事件”然后直接给答案的问题：即使 Tauri 事件通道没有实时送达，最终结果也必须包含 `model_call_started`、`model_step`、工具调用和命令 Trace。

后续仍需细化：

- 新增正式 `tool_call_resumed` 事件，区分首次调用和授权后续跑。
- 为 `run_command` 增加 `command_started` / `command_output_chunk` / `command_finished` 细粒度事件。第一版已在 Runtime 层实现非流式命令 Trace：执行前发 `command_started`，执行后从工具结果拆出 stdout / stderr / exit code / duration 并发 `command_output_chunk` 与 `command_finished`。
- 前端把授权前后的同一个 `tool_call_id` 合并成一个 span。
- 后续如需接近终端实时体验，再把 `command_output_chunk` 下沉到 `run_command` 工具内部，改为执行中实时推送，而不是执行完成后拆分。

必须实现：

```text
run_started
progress_update
model_call_started
model_call_finished
tool_call_started
tool_call_finished
file_read_finished
file_diff_generated
file_written
command_started
command_output_chunk
command_finished
permission_required
schema_repaired
run_finished
```

第一阶段目标效果：

```text
Local Agent Runtime started
  - 正在创建本机会话

Progress update
  - 我已经定位到目标文件是 register.html，参考风格来自 login.html。
  - 下一步读取 login.html 并创建注册页。

Computing... (模型步骤 1)

Read(login.html)
Running...

Result: read_file
  - 读取 login.html 行 1-200/453

Edit(register.html)
Running...

Diff
  + 创建 register.html
  + 写入注册表单、渐变背景、商务风按钮

Verification
  - 回读 register.html
  - 文件已创建
```

## AI 进度播报设计

### 事件名

```text
progress_update
```

### 作用

让 AI 在长任务过程中主动告诉用户：

- 当前阶段性发现。
- 下一步动作。
- 为什么切换方案。
- 是否遇到阻塞。

### 注意

这不是隐藏思维链。它是 AI 主动生成的可见工作说明。

### 示例

```json
{
  "type": "progress_update",
  "status": "running",
  "title": "已有阶段性结论",
  "summary": "我已经确认用户选择的是 login.html 的浅色渐变商务风，目标文件是 register.html。",
  "next_action": "接下来读取 login.html 的结构和样式，再生成 register.html。",
  "metadata": {
    "selected_style_source": "login.html",
    "target_file": "register.html"
  }
}
```

## Runner 改造点

### 1. 统一事件构造器

位置建议：

```text
web-admin/frontend/src-tauri/src/liuagent_core/adapters/protocol.rs
```

新增：

```rust
pub fn agent_trace_event(...)
pub fn progress_update_event(...)
pub fn command_output_chunk_event(...)
pub fn file_diff_generated_event(...)
pub fn schema_repaired_event(...)
```

### 2. 模型循环发事件

位置：

```text
web-admin/frontend/src-tauri/src/liuagent_core/runtime.rs
```

模型调用前：

```text
model_call_started
```

模型返回后：

```text
model_call_finished
```

如果模型输出可见进度播报：

```text
progress_update
```

### 3. 工具执行发事件

位置：

```text
web-admin/frontend/src-tauri/src/liuagent_core/mod.rs
web-admin/frontend/src-tauri/src/liuagent_core/tools/*
```

工具调用前：

```text
tool_call_started
```

工具调用后：

```text
tool_call_finished
```

文件类工具额外发：

```text
file_read_finished
file_diff_generated
file_written
file_deleted
```

命令类工具额外发：

```text
command_started
command_output_chunk
command_finished
command_failed
command_timeout
```

### 4. 自动修复发事件

当前已开始修复：

- `write_file` 缺 `path` 时从最近用户消息推断目标文件名。
- `tool.schema_invalid` 返回明确恢复指令。

后续需要在修复发生时发：

```text
schema_repaired
repair_attempted
retry_scheduled
```

示例：

```json
{
  "type": "schema_repaired",
  "summary": "已从用户消息推断 write_file.path=register.html",
  "metadata": {
    "tool_name": "write_file",
    "field": "path",
    "value": "register.html"
  }
}
```

## 前端改造点

### 1. Trace Viewer

位置建议：

```text
web-admin/frontend/src/views/projects/ProjectChat.vue
```

或拆为组件：

```text
web-admin/frontend/src/modules/project-chat/components/agent-trace/AgentTracePanel.vue
web-admin/frontend/src/modules/project-chat/components/agent-trace/AgentTraceItem.vue
```

### 2. 展示规则

| 事件类型 | 展示形式 |
|---|---|
| `progress_update` | 普通文本进度播报 |
| `model_call_started` | `Computing...` |
| `tool_call_started` | `Explore(...)` / `Read(...)` / `Edit(...)` / `Bash(...)` |
| `command_output_chunk` | 终端输出块 |
| `file_diff_generated` | diff 折叠块 |
| `permission_required` | 授权确认卡片 |
| `schema_repaired` | 自动修复说明 |
| `run_finished` | 完成摘要 |

### 3. 去重

必须按 `event_id` 去重。

恢复历史时：

- 已展示事件不重复 append。
- 只补缺失事件。
- 最终状态事件覆盖运行中状态。

### 4. 折叠策略

长输出默认折叠：

```text
+65 lines，展开查看完整输出
```

需要折叠的内容：

- 命令 stdout/stderr。
- 文件 diff。
- 大 JSON。
- 长模型可见输出。

## 持久化设计

每次运行写入：

```text
.ai-employee/agent-runtime-v2/task-runs/<run_id>/trace.jsonl
```

每行一个事件：

```json
{"event_id":"evt_1","type":"run_started",...}
{"event_id":"evt_2","type":"model_call_started",...}
{"event_id":"evt_3","type":"tool_call_started",...}
```

恢复时：

1. 读取当前 run state。
2. 读取 `trace.jsonl`。
3. 按 `event_id` 去重。
4. 按时间排序。
5. 渲染 Trace Viewer。

## 工具能力补强

当前本地工具偏底层，后续建议补三个高阶文件工具：

| 工具 | 作用 |
|---|---|
| `copy_file` | 从已有文件复制到新文件，例如 `login.html` -> `register.html`。 |
| `replace_in_file` | 按规则替换文件片段，适合局部改造。 |
| `create_file_from_template` | 基于模板文件生成新文件，降低模型一次性整文件生成压力。 |

这些工具可以减少模型直接大段 `write_file` 的失败率。

## 分阶段实施

### 阶段 1：事件协议和可见轨迹

- 新增 `AgentTraceEvent`。
- 补 `progress_update`。
- 补模型、工具、文件、命令的核心事件。
- 前端展示 `Computing / Explore / Read / Edit / Bash / Result`。
- 按 `event_id` 去重。

### 阶段 2：文件和命令细节

- 文件读写展示路径、行号、字节数。
- 文件修改展示 diff 摘要。
- 命令执行流式展示 stdout/stderr。
- 长输出折叠。

### 阶段 3：恢复和错误修复

- 完整持久化 `trace.jsonl`。
- 恢复失败任务时重建 Trace。
- `schema_repaired`、`retry_scheduled`、`loop_paused` 展示清楚。

### 阶段 4：高阶工具

- 新增 `copy_file`。
- 新增 `replace_in_file`。
- 新增 `create_file_from_template`。
- 让模型优先使用高阶工具，而不是所有任务都直接 `write_file`。

## 验收标准

1. 用户能看到 AI 的可见进度播报。
2. 用户能看到每次模型调用开始和结束。
3. 用户能看到每次工具调用的参数摘要和结果摘要。
4. 文件修改能看到 diff 或至少看到加减行摘要。
5. 命令执行能看到 stdout/stderr，长输出可折叠。
6. 权限确认能明确展示工具、风险、影响范围。
7. 刷新页面后能恢复同一条运行轨迹，不重复显示历史事件。
8. `write_file` 缺 `path` 这类 schema 错误能自动修复或给模型明确修复建议。
9. 整体体验接近 Codex / Claude 的执行过程展示，但不展示隐藏思维链。

## 当前已完成的相关修复

- 桌面本地智能体追加“计划先行 · 选项驱动”提示词。
- Runner 模型步骤事件补充 `content_preview`。
- 前端本地事件展示改为更接近 `Computing / Explore / Result` 的形式。
- `write_file` 缺 `path` 时可从最近用户消息推断目标文件名。
- `tool.schema_invalid` 增加明确恢复提示。
- `write_file` 工具定义增加参数示例和字段说明。

## 后续优先级

优先级最高：

1. `AgentTraceEvent` 正式协议化。
2. `progress_update` 由 AI 动态生成。
3. 前端 Trace Viewer 去重和折叠。
4. 命令输出 chunk 流式展示。
5. 文件 diff 展示。

完成这些后，桌面本地智能体的执行过程会从“状态摘要”升级为“可审计执行轨迹”。
