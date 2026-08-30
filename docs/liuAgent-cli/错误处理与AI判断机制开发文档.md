# 桌面本地 Agent 错误处理与 AI 判断机制开发文档

## 1. 文档目的

本文档定义桌面本地 Agent Runtime 的错误处理规则，解决以下问题：

- 工具失败不能直接中断用户对话。
- 普通 Runtime 错误不能直接弹框。
- 错误必须先被本地记录，再交给 AI 判断。
- AI 需要决定重试、换方案、继续执行、等待用户，还是确认需求无法完成。
- 只有真正影响用户原始需求完成的错误，才允许作为最终结果返回用户。
- 模型接口本身无法通信时，允许对话以连接错误结束。

本文档适用于 macOS 和 Windows。路径、进程、日志和文件操作必须由本地 Runtime 使用平台无关 API 处理，前端不能自行拼接平台绝对路径。

## 2. 核心原则

### 2.1 内部错误不等于用户错误

以下内容属于 Runtime 内部执行信息，不能直接作为对话最终结果：

- `tool.execution_failed`
- `tool.schema_invalid`
- `resource.read_failed`
- `runtime.paused`
- `runtime.interrupted`
- 命令退出码非零
- stdout/stderr 原始内容
- 工具调用 JSON
- `failure_signature`
- `repeated_failure`
- `tool_recovery_limit_reached`

这些内容必须先进入错误记录和 AI 错误分析流程。

### 2.2 对话默认必须继续

只要模型接口仍然可用，普通工具错误不应让对话停在“失败”状态。Runtime 应继续尝试：

1. 重试原操作；
2. 修改参数后重试；
3. 使用替代工具；
4. 改变执行策略；
5. 读取日志和产物后让 AI 重新判断。

### 2.3 用户可见错误必须证明需求被阻断

只有同时满足以下条件，才可以向用户返回最终错误：

- AI 已读取或获得完整错误上下文；
- Runtime 已执行允许范围内的重试或替代方案；
- 没有可行的继续路径；
- 错误直接导致用户原始需求无法完成；
- 错误不是单纯的中间工具失败或内部状态失败。

判断标准不是“某个工具失败”，而是：

```text
requirement_blocked = true
```

## 3. 错误分类

### 3.1 可重试错误

适用于短暂性错误，不需要用户参与。

典型情况：

- 模型或工具服务临时超时，但连接仍可用；
- HTTP 5xx；
- 网络瞬时断开；
- 本地进程启动竞争或临时占用；
- 临时文件尚未生成；
- 资源暂时不可读；
- 媒体文件下载或落盘失败；
- 工具返回空结果但没有明确证明目标失败。

处理规则：

- Runtime 自动重试；
- 使用指数退避或明确的重试间隔；
- 限制最大次数；
- 每次尝试都写入错误记录；
- 不弹框；
- 不把原始错误直接展示给用户；
- 重试成功后，用户只看到正常的 AI 最终结果。

建议状态：

```text
retrying
reconnecting
running
```

### 3.2 需要暂停分析的错误

适用于 Runtime 无法直接判断错误是否影响需求，但 AI 仍可能恢复的情况。

典型情况：

- 同一工具连续失败；
- 文件修改失败，但可能存在替代路径；
- 后台命令退出，但需要检查 stdout/stderr 和产物；
- 任务没有收到完成信号；
- 验证失败，但可能只是验证方式不适配；
- 工具返回结构异常，需要 AI 判断下一步。

处理规则：

- 暂停当前执行节点，不销毁 Runtime 上下文；
- 写入完整错误记录文件；
- 将错误记录摘要、文件路径和原始需求交给 AI；
- AI 决定重试、换方案、继续或最终阻断；
- 这个暂停是内部分析状态，不是向用户报告“任务失败”。

建议状态：

```text
diagnosing
waiting_ai_judgement
```

### 3.3 需要用户交互的等待

这类不是普通错误，允许等待用户操作。

典型情况：

- `permission.required`；
- `interaction.user_input_required`；
- 高风险操作需要用户确认；
- 目标信息确实缺失，AI 无法安全推断。

处理规则：

- 展示明确的授权或问题交互；
- 保存 checkpoint；
- 继续使用同一个任务、会话和工具调用上下文；
- 不把原始 Runtime 错误当成最终错误。

建议状态：

```text
waiting_approval
waiting_user
```

### 3.4 用户需求根本被阻断

只有 AI 判断原始需求无法完成时，才进入此类。

典型情况：

- 用户要求读取的文件确认不存在，且没有替代文件；
- 用户要求修改的目标不可访问，且授权后仍失败；
- 必需的外部服务不可用，且没有备用方案；
- 模型无法根据任何可用上下文完成任务；
- 关键输入损坏且无法恢复；
- 所有安全允许的方案都已尝试并失败。

处理规则：

- 由 AI 生成正常的最终回答；
- 返回根本原因，而不是只返回错误码；
- 返回已尝试的方案；
- 返回原始错误摘要；
- 返回错误记录文件路径；
- 明确说明用户可以采取的下一步；
- 不使用普通错误弹框代替 AI 回复。

建议状态：

```text
blocked
```

### 3.5 模型接口连接错误

这是唯一允许直接结束本轮对话的基础设施类错误，但也应先重试。

典型情况：

- 模型接口连接超时；
- DNS、TLS 或连接建立失败；
- API 请求在重试后仍无响应；
- Provider 不可达；
- 模型接口返回无法继续处理的连接级错误。

处理规则：

- 先执行有限次数重试；
- 保存当前会话和 Runtime checkpoint；
- 如果仍无法连接，允许返回“模型连接失败”；
- 返回连接错误记录路径；
- 不应伪装成工具执行失败；
- 不应丢失此前已经完成的工具结果和文件变更。

建议状态：

```text
model_connection_failed
```

## 4. 标准处理流程

```text
工具或 Runtime 产生错误
        |
        v
生成唯一 error_id
        |
        v
写入本地错误记录文件
        |
        v
判断是否为模型连接错误
        |
        +-- 是 --> 重试模型连接
        |             |
        |             +-- 成功 --> 继续当前 Agent Loop
        |             |
        |             +-- 失败 --> 返回模型连接错误
        |
        +-- 否 --> 判断是否可自动重试
                      |
                      +-- 是 --> 重试原工具或替代参数
                      |
                      +-- 否 --> 暂停当前节点并交给 AI 分析
                                      |
                                      +-- retry --> 继续重试
                                      +-- alternative --> 换方案
                                      +-- continue --> 继续任务
                                      +-- waiting_user --> 等待用户
                                      +-- blocked --> 返回 AI 解析后的最终错误
```

## 5. AI 错误处理提示词

错误处理提示词只在发生错误时注入，不作为每轮普通对话的固定提示词。

Runtime 应向 AI 提供结构化错误上下文，至少包括：

```json
{
  "error_id": "err_xxx",
  "project_id": "project_xxx",
  "chat_session_id": "session_xxx",
  "requirement": "用户原始需求",
  "stage": "tool_execution",
  "tool_name": "read_file",
  "tool_call_id": "call_xxx",
  "error_code": "resource.read_failed",
  "error_message": "读取资源失败",
  "error_record_path": "/platform/path/error.json",
  "stdout_log_path": "",
  "stderr_log_path": "/platform/path/stderr.log",
  "attempt": 2,
  "max_attempts": 3,
  "previous_strategies": [
    "read_file:missing.md"
  ],
  "workspace_path": "/platform/path/workspace",
  "affected_targets": [
    "missing.md"
  ]
}
```

AI 需要输出结构化判断：

```json
{
  "decision": "retry|alternative|continue|waiting_user|blocked",
  "requirement_blocked": false,
  "reason": "判断原因",
  "next_action": "下一步动作",
  "user_visible": false,
  "user_summary": "",
  "error_record_path": ""
}
```

约束：

- `user_visible=false` 时，不能将原始错误直接写入最终 assistant 内容；
- `decision=blocked` 时，必须设置 `requirement_blocked=true`；
- `decision=blocked` 时必须返回 `error_record_path`；
- AI 不得声称已完成未验证的文件修改；
- AI 不得因为一次工具失败直接判断需求失败；
- AI 应优先读取错误记录和 stdout/stderr，再做判断；
- 原始日志中的 API Key、Token、Cookie 和密码必须脱敏。

## 6. 本地错误记录文件

### 6.0 不新增错误日志工具

错误记录不需要新增一个面向 AI 的开发工具或业务工具。

记录动作由现有桌面 Runtime 内部完成，优先复用已有能力：

- 现有 Runtime 文件写入能力；
- 现有工作区目录创建能力；
- 现有 stdout/stderr 日志能力；
- 现有 Runtime Event 和 checkpoint 持久化能力；
- 现有会话需求记录能力。

AI 的职责仅包括：

- 读取 Runtime 提供的错误摘要和日志路径；
- 根据错误上下文判断下一步；
- 选择重试、替代方案、继续、等待用户或阻断；
- 生成用户可见的自然语言结果。

AI 不负责：

- 自己拼接平台绝对路径；
- 自己创建错误日志目录；
- 自己决定日志文件名；
- 直接覆盖或删除 Runtime 错误记录；
- 用新增工具绕过 Runtime 的权限和审计。

错误记录写入仍然必须由 Rust Runtime 统一处理，以保证 macOS 和 Windows 的路径、权限、原子写入和失败兜底行为一致。

### 6.1 当前已有记录

当前 Runtime 已具备以下记录能力：

- 会话需求记录：

```text
<workspace>/.ai-employee/requirements/<project_id>/<chat_session_id>.json
```

- Runtime 诊断字段：
  - `failed_model_step_count`
  - `failed_tool_call_count`
  - `stopped_reason`
  - `prompt_stack`
  - 总耗时和阶段耗时

- 后台命令日志：
  - `stdout_log_path`
  - `stderr_log_path`
  - `state_path`
  - `job_id`

这些能力可以支撑错误分析的基础，但当前记录仍然分散，且需求记录文件更偏向“会话最终状态”，不是完整的逐错误记录。

### 6.2 错误记录实现

每个需要追踪的错误事件生成独立记录：

```text
<workspace>/.ai-employee/runtime-errors/<project_id>/<chat_session_id>/<error_id>.json
```

文件内容包括：

```json
{
  "version": "runtime-error/v1",
  "error_id": "err_xxx",
  "created_at": "2026-08-30T00:00:00Z",
  "project_id": "project_xxx",
  "chat_session_id": "session_xxx",
  "runtime_session_id": "runtime_xxx",
  "requirement": "用户原始需求",
  "stage": "tool_execution|model_request|runtime_entry",
  "tool": {
    "name": "read_file",
    "tool_call_id": "call_xxx",
    "arguments_preview": {
      "path": "missing.md"
    }
  },
  "error": {
    "code": "resource.read_failed",
    "message": "读取资源失败",
    "status": "failed",
    "retryable": true,
    "requirement_blocked": false
  },
  "attempt": {
    "number": 1,
    "max": 3,
    "strategy": "read_file"
  },
  "logs": {
    "stdout_path": "",
    "stderr_path": "",
    "runtime_event_ids": [
      "event_xxx"
    ]
  },
  "ai_judgement": {
    "status": "pending|completed|not_requested",
    "decision": "",
    "reason": ""
  },
  "resolution": null
}
```

要求：

- 文件使用 UTF-8 JSON；
- 写入采用临时文件后原子替换；
- 目录创建和路径清理由 Rust Runtime 完成；
- macOS 和 Windows 均不得硬编码 `/`、`\` 或用户目录；
- 前端只消费 Runtime 返回的路径；
- 记录文件写入失败不能覆盖原始工具错误；
- 错误记录失败时，至少保留 Runtime 内存事件和会话需求记录。

当前已覆盖：

- 工具执行错误：记录工具参数摘要、失败签名、重试信息、stdout/stderr 和关联日志路径；
- 模型请求错误：记录安全的 endpoint、供应商、模型和错误码，不记录 API Key 或 URL 查询凭据；
- Runtime 入口错误：工作区、网关或初始化阶段失败时也会落盘；
- 错误记录路径会回写到 `LocalChatResult`，最终不可恢复时由对话反馈给用户。

## 7. 前端展示规则

### 7.1 禁止普通错误弹框

普通工具和 Runtime 错误不得调用：

```js
showManualCloseErrorDialog(...)
ElMessageBox.alert(...)
```

除非错误已经被判断为模型连接彻底失败，或属于明确的用户确认交互。

### 7.2 正常情况下用户看到的内容

用户只看到 AI 的自然语言结果，例如：

> 原文件读取失败，我已检查目录并改用备用文件完成处理。

如果需求最终确实无法完成：

> 当前需求无法完成。目标文件不存在，已尝试读取、搜索同名文件和检查工作区目录，但没有找到可替代文件。详细错误记录：`<error_record_path>`。

### 7.3 执行轨迹与最终回答分离

运行详情可以保留：

- 原始错误码；
- 工具参数摘要；
- stdout/stderr；
- 重试次数；
- Runtime 事件；
- AI 判断；
- 错误文件路径。

但这些内容不应自动拼接到普通 assistant 最终回答中，除非 AI 判断需求已经被根本阻断。

## 8. 当前实现差距

截至 2026 年 8 月 30 日，以下主链路已经落地：

1. 普通工具失败会先生成独立 `runtime-error/v1` JSON 记录。
2. 错误记录路径会进入 tool observation，只在错误场景注入 `runtime_error_diagnosis_required` 提示。
3. 同一失败策略重复出现，或失败达到配置上限时，只追加一次 AI 诊断轮次，不再直接以 `tool_recovery_limit_reached` 结束。
4. AI 仍可通过标准工具改变参数、切换工具或继续任务；只有最终确认无法完成时才进入 `requirement_blocked`。
5. `requirement_blocked` 会使用 AI 最终内容，并附带错误记录文件路径。
6. `ProjectChat.vue` 普通 Runtime 结果不再调用错误弹框，也不再拼接 `执行失败：原始错误`。
7. 网络中断、超时、授权和用户补充信息仍保留各自的恢复或交互路径。
8. 模型请求失败和 Runtime 入口失败也会写入 `runtime-errors`，并将记录路径返回给前端。
9. 会话切换会等待活动任务的最新消息和媒体资产快照写入完成后再读取。

仍需后续增强的部分：

1. 前端其他独立上传流程仍有专用错误提示，它们不属于本地 Agent 对话 Runtime 主链路。
2. 图片生成成功后的真实供应商回归仍需在桌面端执行；代码层面已覆盖会话切换时的持久化等待和媒体合并恢复。

## 9. 非回归要求

实现本机制时必须保证：

- 工具失败后 AI 仍能继续收到完整 tool observation；
- 重试不会重复执行不可重入的写操作；
- 写文件、应用补丁等操作必须使用幂等或目标快照校验；
- 错误记录失败不能导致正常任务额外失败；
- 会话切换后错误事件仍写入原任务所属会话；
- 页面刷新后可以恢复错误记录路径和 AI 判断状态；
- macOS 和 Windows 的路径、进程、日志读取行为一致；
- 用户主动暂停、授权等待和补充信息流程不被普通错误机制覆盖；
- 模型连接失败时不能丢失此前已经完成的工具结果；
- 最终回答不能声称未验证的任务已经完成。

## 10. 最低回归场景

至少验证以下场景：

1. 工具第一次失败，第二次重试成功。
2. 工具失败后改用替代工具成功。
3. 同一错误重复出现，只进入一次 AI 错误诊断轮次。
4. AI 判断可以继续，用户不看到原始错误。
5. AI 判断需求被根本阻断，返回自然语言说明和错误文件路径。
6. `permission.required` 仍然等待用户授权。
7. `interaction.user_input_required` 仍然等待用户回答。
8. 模型连接超时，重试后仍失败，返回连接错误。
9. 运行过程中切换会话，错误记录和最终回答仍回到原会话。
10. 错误日志写入失败时，原始错误仍保留在 Runtime 和会话记录中。
11. 图片生成或其他媒体工具完成后切换到新会话，再切回原会话，媒体 URL 和 `mediaAssets` 仍可恢复。

## 11. 本次实现的状态约定

Runtime 内部状态与用户对话状态必须分开：

| Runtime 状态 | 用户对话行为 |
| --- | --- |
| `retrying` / 自动重试 | 继续运行，不弹框 |
| `diagnosing` / `waiting_ai_judgement` | 追加一次错误分析提示，继续同一 Agent Loop |
| `waiting_approval` | 请求用户授权，保存 checkpoint |
| `waiting_user` | 请求用户补充必要信息，保存 checkpoint |
| `runtime_interrupted` | 按现有策略自动从 checkpoint 恢复 |
| `requirement_blocked` | 展示 AI 解析后的自然语言结论和错误记录路径 |
| 模型连接超时重试耗尽 | 返回连接不可用说明、错误记录路径和已保留的本地上下文 |

普通工具错误不应直接映射成用户消息中的 `failed`、`blocked` 或 Runtime 原始错误。运行详情可以保留这些字段，但最终 assistant 内容必须来自 AI 正常回答，或来自 `requirement_blocked` 场景下的 AI 解析结果。
