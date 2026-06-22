# 工具系统

工具系统负责把模型的工具调用意图变成可校验、可授权、可执行、可审计的动作。

## ToolDefinition

工具对模型和运行时暴露的定义。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | string | 是 | 工具名，必须唯一。 |
| `description` | string | 是 | 给模型看的能力说明。 |
| `input_schema` | object | 是 | JSON Schema 参数定义。 |
| `action` | string | 是 | 权限策略动作名，例如 `file.read`、`file.write`、`command.run`。 |
| `risk` | RiskLevel | 是 | 默认风险等级。 |
| `requires_approval` | boolean | 是 | 默认是否需要用户确认。 |
| `scope` | string[] | 是 | 工具允许访问的资源范围。 |

## ToolRegistryEntry

运行时登记的工具条目。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `definition` | ToolDefinition | 是 | 工具定义。 |
| `executor_ref` | string | 是 | 执行器引用。 |
| `enabled` | boolean | 是 | 当前是否启用。 |
| `source` | `builtin` \| `mcp` \| `plugin` | 是 | 工具来源。 |

## ToolCall

模型发起的工具调用请求。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tool_call_id` | ID | 是 | 调用 ID。 |
| `name` | string | 是 | 工具名。 |
| `arguments` | object | 是 | 已解析参数。 |
| `run_id` | ID | 是 | 所属执行。 |
| `action` | string | 是 | 权限策略动作名，来自 `ToolDefinition.action`。 |
| `origin_message_id` | ID | 是 | 来源模型消息。 |
| `status` | ToolCallStatus | 是 | `created`、`validating`、`waiting_permission`、`executing`、`succeeded`、`failed`、`rejected`、`denied`、`cancelled`。 |
| `tool_batch_id` | ID | 否 | 所属工具批次。 |
| `index` | number | 否 | 模型一次返回多个工具调用时的稳定顺序。 |
| `depends_on` | ID[] | 否 | 必须先成功的工具调用 ID。 |
| `permission_request_id` | ID | 否 | 等待或已使用的权限请求 ID。 |
| `created_at` | Timestamp | 是 | 创建时间。 |
| `started_at` | Timestamp | 否 | 真正开始执行时间。 |
| `ended_at` | Timestamp | 否 | 完成、失败、拒绝或取消时间。 |

## ToolCall 来源约束

工具调用必须来自模型明确产出的结构化 `ModelToolCall`，再由 Core 转换为 `ToolCall`。运行时、Adapter、前端或后端都不能根据用户自然语言中的关键词、正则匹配或意图猜测直接合成工具调用。

硬性规则：

- 禁止用正则、关键词、字符串包含关系或路径提取逻辑从 `user_message` 中推断 `delete_file`、`write_file`、`run_command`、`call_mcp_tool` 等工具调用。
- 允许解析的只有模型输出中的结构化工具调用协议；即使模型文字里说“我将删除文件”，只要没有合法 `ModelToolCall`，就不能进入工具执行链路。
- 用户输入“删除吧”“确认删除”“已授权”等自然语言，不能被当成新的工具调用；它只能在已有 `PermissionRequest` 的上下文中转换为引用该 `request_id` 的 `PermissionDecision`。
- Core 收到 `ModelToolCall` 后必须先做 schema 校验、工具注册表校验、workspace 范围校验和 Permission Gate 检查，不能先执行再补授权。
- 删除、覆盖、命令执行、网络写入、MCP 写入等高风险动作，必须在真正调用 executor 之前进入 `waiting_permission`，并生成可展示、可审计的 `PermissionRequest`。
- 授权 UI 只能展示已经由 Permission Gate 产生的具体权限请求，不能根据聊天文本提前弹出“删除/写入/执行”的假授权。
- 测试必须覆盖负例：用户自然语言包含“删除”“remove”“delete_file”等词时，如果模型没有结构化工具调用，不得产生删除工具调用，也不得删除文件。

## ToolBatch

当模型一次返回多个工具调用时，Core 必须创建工具批次，避免 CLI、Web、Desktop 各自猜测执行顺序。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tool_batch_id` | ID | 是 | 批次 ID。 |
| `run_id` | ID | 是 | 所属 Run。 |
| `origin_message_id` | ID | 是 | 来源模型消息。 |
| `mode` | `sequential` \| `parallel` | 是 | 调度模式。 |
| `failure_policy` | `fail_fast` \| `continue_on_error` \| `model_decides` | 是 | 失败处理策略。 |
| `tool_call_ids` | ID[] | 是 | 批次内工具调用 ID，顺序与 `index` 一致。 |
| `status` | `created` \| `running` \| `succeeded` \| `failed` \| `cancelled` | 是 | 批次状态。 |
| `created_at` | Timestamp | 是 | 创建时间。 |
| `ended_at` | Timestamp | 否 | 结束时间。 |

默认策略：

- 没有依赖关系且工具均为 `safe` 或只读时，可以使用 `parallel`。
- 写文件、运行命令、网络写入、打开外部链接默认使用 `sequential`。
- 同一批次内既有读操作又有写操作时，写操作必须在相关读操作之后。
- 任何高风险工具失败时，默认 `fail_fast`。

## ToolResult

工具执行后的统一返回。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tool_result_id` | ID | 是 | 工具结果 ID。 |
| `tool_call_id` | ID | 是 | 对应的工具调用。 |
| `ok` | boolean | 是 | 是否成功。 |
| `content` | string | 是 | 给模型看的摘要文本。 |
| `summary` | string | 是 | 给 UI、事件流和审计展示的短摘要；可由 `content` 截断生成。 |
| `data` | object | 否 | 结构化数据。 |
| `error` | ToolError | 否 | 错误对象。 |
| `audit_id` | ID | 否 | 关联审计记录。 |
| `created_at` | Timestamp | 是 | 结果生成时间。 |

## ToolError

工具错误必须结构化，避免只把 stderr 丢给模型。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `code` | string | 是 | 稳定错误码。 |
| `message` | string | 是 | 可读错误说明。 |
| `retryable` | boolean | 是 | 是否可重试。 |
| `details` | object | 否 | 原始错误细节。 |

## 执行链路

```text
ToolCall
  -> schema validate
  -> permission check
  -> executor
  -> ToolResult
  -> Observation
```

Tool Runtime 不应该绕过 Permission Gate。即使工具来自 MCP 或插件，也必须进入同一条执行链路。

`ToolResult.content` 面向模型 observation，允许包含必要上下文；`ToolResult.summary` 面向 UI，必须短且不包含敏感数据。`tool_result` 事件只使用 UI 摘要，不直接暴露完整 `content`。

## MCP stdio framing

本地 MCP adapter 从 workspace `.ai-employee/mcp-adapter/servers.json` 读取 server 配置。默认使用逐行 JSON-RPC，适配简单本地桥接器；标准 MCP server 必须显式配置 framing：

```json
{
  "servers": {
    "local": {
      "command": "/path/to/mcp-server",
      "args": ["--stdio"],
      "cwd": ".",
      "framing": "content-length"
    }
  }
}
```

`framing` 可取 `content-length`、`mcp`、`standard`；也可通过 `transport` 写入等价值。启用后，请求和响应都按 `Content-Length: <bytes>\r\n\r\n<body>` 解析。未配置时保持逐行 JSON-RPC，避免破坏已有轻量 adapter。

无论使用哪种 framing，`tools/call` 都必须先进入 Permission Gate；framing 只影响传输解析，不改变工具授权、审计和 workspace 范围规则。

## 多工具 observation 聚合

ToolBatch 完成后，Core 按 `index` 聚合 observation：

1. 每个 `ToolCall` 必须产生一个终态：`succeeded`、`failed`、`rejected`、`denied` 或 `cancelled`。
2. `continue_on_error` 下，失败工具也要生成 `ToolResult.ok=false`，不能丢失。
3. 交回模型的 observation 必须包含 `tool_call_id`，让模型能对应原始工具调用。
4. 给 UI 的 `tool_result` 事件可以逐个发送，但模型下一轮输入必须使用聚合后的完整结果。
