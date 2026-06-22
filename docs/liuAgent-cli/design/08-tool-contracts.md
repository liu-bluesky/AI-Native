# 工具契约

本文档定义第一版内置工具的参数、结果、权限和错误契约。所有工具都必须进入 Tool Runtime，并经过 schema 校验、Permission Gate 和 Audit Log。

所有内置工具只能由模型结构化工具调用触发。运行时不得从用户自然语言、关键词或正则匹配中推断并合成工具调用；权限请求也只能在具体 `ToolCall` 通过 schema 和范围校验后、executor 执行前生成。

## 通用 ToolCall

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tool_call_id` | ID | 是 | 调用 ID。 |
| `name` | string | 是 | 工具名。 |
| `arguments` | object | 是 | 工具参数。 |
| `run_id` | ID | 是 | 所属 Run。 |
| `action` | string | 是 | 权限策略动作名；例如本工具名是 `run_command`，对应 action 是 `command.run`。 |
| `origin_message_id` | ID | 是 | 触发调用的模型消息。 |
| `status` | ToolCallStatus | 是 | 工具调用生命周期状态。 |
| `permission_request_id` | ID | 否 | 关联的权限请求 ID。 |
| `created_at` | Timestamp | 是 | 创建时间。 |
| `started_at` | Timestamp | 否 | 实际开始执行时间。 |
| `ended_at` | Timestamp | 否 | 完成、失败、拒绝或取消时间。 |

## 通用 ToolResult

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tool_result_id` | ID | 是 | 结果 ID。 |
| `tool_call_id` | ID | 是 | 对应调用。 |
| `ok` | boolean | 是 | 是否成功。 |
| `content` | string | 是 | 回传给模型的 observation 摘要。 |
| `summary` | string | 是 | 给 UI、事件流和审计展示的短摘要；可由 `content` 截断生成。 |
| `data` | object | 否 | 结构化结果。 |
| `error` | ToolError | 否 | 失败原因。 |
| `audit_id` | ID | 否 | 关联审计记录。 |
| `created_at` | Timestamp | 是 | 完成时间。 |

## 文件工具

### list_files

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `path` | RelativePath | 否 | `"."` | 必须在 workspace 内。 |
| `max_depth` | number | 否 | `2` | 最大建议 5。 |
| `include_hidden` | boolean | 否 | `false` | 读取隐藏目录可配置确认。 |

结果：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `entries` | FileEntry[] | 文件和目录列表。 |
| `truncated` | boolean | 是否截断。 |

### read_file

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `path` | RelativePath | 是 | 无 | 必须在 workspace 内。 |
| `start_line` | number | 否 | `1` | 从 1 开始。 |
| `line_count` | number | 否 | `200` | 默认截断。 |

结果：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `path` | RelativePath | 文件路径。 |
| `content` | string | 文本内容。 |
| `start_line` | number | 起始行。 |
| `end_line` | number | 结束行。 |
| `truncated` | boolean | 是否截断。 |

### search_text

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | 无 | 普通只读。 |
| `path` | RelativePath | 否 | `"."` | 必须在 workspace 内。 |
| `glob` | string | 否 | 无 | 文件过滤。 |
| `max_results` | number | 否 | `50` | 防止大输出。 |

结果：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `matches` | TextMatch[] | 命中列表。 |
| `truncated` | boolean | 是否截断。 |

### apply_patch

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `patch` | string | 是 | 无 | 写 workspace 文件，至少 `medium`。 |
| `summary` | string | 是 | 无 | 修改目的。 |

结果：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `changed_files` | RelativePath[] | 变更文件。 |
| `applied` | boolean | 是否成功应用。 |

### write_file

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `path` | RelativePath | 是 | 无 | 写 workspace 文件，至少 `medium`。 |
| `content` | string | 是 | 无 | 新文件内容。 |
| `overwrite` | boolean | 否 | `false` | 覆盖已有文件时风险升为 `high`。 |

结果：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `path` | RelativePath | 写入路径。 |
| `created` | boolean | 是否新建。 |
| `overwritten` | boolean | 是否覆盖已有文件。 |

## 命令工具

### check_command_risk

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `cmd` | string | 是 | 无 | 只做分类，不执行命令。 |
| `cwd` | RelativePath | 否 | `"."` | 必须在 workspace 内。 |

结果：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `risk` | RiskLevel | 风险等级。 |
| `reasons` | string[] | 命中原因。 |
| `requires_approval` | boolean | 是否需要确认。 |
| `suggested_preview` | object | 给权限请求使用的预览信息。 |

### run_command

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `cmd` | string | 是 | 无 | 必须先做风险分类。 |
| `cwd` | RelativePath | 否 | `"."` | 必须在 workspace 内。 |
| `timeout_ms` | number | 否 | `30000` | 超时终止。 |
| `max_output_chars` | number | 否 | `20000` | 输出截断。 |

结果：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `exit_code` | number | 退出码。 |
| `stdout` | string | 标准输出，可能截断。 |
| `stderr` | string | 标准错误，可能截断。 |
| `duration_ms` | number | 执行耗时。 |
| `truncated` | boolean | 是否截断。 |

权限策略：

- `safe`: `pwd`、`ls`、`rg`、只读 git 查询。
- `medium`: 写 workspace 文件的格式化、测试生成缓存。
- `high`: 安装依赖、启动长服务、网络写入。
- `critical`: 部署、删除、系统目录写入、凭据操作。

## 网络工具

### http_get

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `url` | string | 是 | 无 | 公开读取。 |
| `headers` | object | 否 | `{}` | 禁止自动带本地凭据。 |
| `timeout_ms` | number | 否 | `30000` | 超时终止。 |

### download_file

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `url` | string | 是 | 无 | 网络读取。 |
| `dest_path` | RelativePath | 是 | 无 | 写 workspace 文件，至少 `medium`。 |
| `overwrite` | boolean | 否 | `false` | 覆盖已有文件时风险升为 `high`。 |
| `timeout_ms` | number | 否 | `30000` | 超时终止。 |

结果：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dest_path` | RelativePath | 下载保存路径。 |
| `bytes` | number | 写入字节数。 |
| `content_type` | string | 响应类型。 |

### http_post

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `url` | string | 是 | 无 | 默认 `high`。 |
| `headers` | object | 否 | `{}` | 禁止自动带本地凭据。 |
| `body` | JsonValue | 是 | 无 | 提交内容必须进入审计。 |

## MCP 工具

### list_mcp_tools

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `server` | string | 否 | 无 | 指定 MCP server。 |

### read_mcp_resource

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `server` | string | 是 | 无 | MCP server 名。 |
| `uri` | string | 是 | 无 | 资源 URI。 |

结果：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `uri` | string | 资源 URI。 |
| `mime_type` | string | 内容类型。 |
| `content` | string | 文本内容或序列化摘要。 |
| `truncated` | boolean | 是否截断。 |

### call_mcp_tool

参数：

| 字段 | 类型 | 必填 | 默认值 | 权限 |
| --- | --- | --- | --- | --- |
| `server` | string | 是 | 无 | MCP server 名。 |
| `tool` | string | 是 | 无 | MCP tool 名。 |
| `arguments` | object | 是 | `{}` | 进入统一权限判断。 |

MCP 工具的风险不能只看工具名，必须结合 `arguments` 判断。例如同一个 `drive` 工具可能只是读文件，也可能删除文件。

## 稳定错误码

| 错误码 | 含义 | 可重试 |
| --- | --- | --- |
| `tool.not_found` | 工具不存在或未启用 | 否 |
| `tool.schema_invalid` | 参数不符合 schema | 可修改后重试 |
| `permission.denied` | 用户或策略拒绝 | 否 |
| `permission.required` | 需要用户确认 | 是 |
| `workspace.out_of_scope` | 路径逃逸 workspace | 否 |
| `command.timeout` | 命令超时 | 是 |
| `command.failed` | 命令非零退出 | 视情况 |
| `network.failed` | 网络请求失败 | 是 |
| `mcp.failed` | MCP 调用失败 | 视情况 |
