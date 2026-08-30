# MCP Plugin Template

一个 MCP Server 对应一个 MCP Plugin。

- `plugin.json`：插件身份、权限和动态能力说明。
- `mcp.json`：Server 连接配置模板。
- `skills/`：MCP 工具选择规则。

连接由 Core 的 MCP Host 负责；连接成功后通过 `tools/list` 发现的工具由 `mcp_plugin_manifest` 转换为 Plugin Registry 能力。
