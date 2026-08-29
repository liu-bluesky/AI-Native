---
name: plugin-configurator
description: 配置已安装的 AI 插件和 MCP Server，包括 transport、命令参数、工作目录、环境变量、项目级与用户级范围。用户要求配置插件、修改 MCP、测试连接或排查工具不可用时使用。
---

# 插件配置

## 配置顺序

1. 先列出当前已安装插件和来源，再确认用户要修改的插件。
2. 优先编辑插件自己的 `plugin.json`；不要把插件配置散落到智能体核心代码。
3. MCP 组件使用 `components[].config` 配置 `command`、`args`、可选 `cwd` 或 `url`；组件入口使用 `components[].entry`。
4. 相对脚本路径以插件目录为基准；Windows 命令优先检查 `.cmd` 入口。
5. 修改后验证 JSON，再测试 MCP Server 的工具发现。
6. 测试失败时保留原配置，报告具体错误和下一步修复建议。

## 常用配置

```json
{
  "schemaVersion": 1,
  "id": "company-search",
  "type": "mcp",
  "enabled": true,
  "components": [
    {
      "id": "company-search-mcp",
      "kind": "mcp",
      "entry": "./server.mjs",
      "config": {
        "type": "stdio",
        "command": "node",
        "args": ["server.mjs"],
        "env": {}
      },
      "enabled": true
    }
  ]
}
```

## 约束

- 每次只修改用户指定的插件和字段。
- 不将普通 REST 地址当作 MCP HTTP Server。
- 不在没有用户确认时更换插件来源、安装依赖或启用插件。
- 不把插件工具复制或硬编码到内置工具注册表。
- 项目级配置优先于用户级同 ID 插件，但要向用户说明覆盖关系。
- MCP 配置必须放在 `components[].config`，不得放在插件根级别。
