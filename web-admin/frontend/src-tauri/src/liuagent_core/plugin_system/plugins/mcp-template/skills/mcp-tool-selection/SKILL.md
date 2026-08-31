# MCP 工具选择

## 作用

指导 AI 在 MCP Server 动态发现的工具中选择合适能力。

## 选择时机

- 用户请求明确属于该 MCP Server 的业务范围。
- MCP Server 已启用并且工具发现成功。
- 当前工具的输入 Schema 能满足请求参数。

## 执行方式

- 先读取 MCP 工具描述和输入 Schema。
- 优先选择只读工具；有副作用的工具必须经过 Runtime 权限检查。
- 通过 MCP Host 调用 `tools/call`，不要自行执行 MCP Server 命令。
- 只根据真实 MCP 返回结果回复用户。

## 边界

- 不要把 MCP Host 管理接口当成业务工具。
- 不要绕过 Runtime 的权限、超时和审计机制。
- MCP Server 不可用或工具 Schema 不完整时，应如实说明并停止调用。
