# 本地插件

面向普通用户的配置步骤请先阅读 `docs/用户手册-插件与MCP.md`。

桌面端插件采用可组合的声明式运行时目录，不把项目管理、部署发布等业务代码塞进智能体核心。插件可以包含多个组件；当前桌面端执行器支持其中的 MCP 组件，其他组件元数据可先被发现并为后续运行时扩展保留。

## 目录

- 用户级：`~/.ai-employee/plugins/<plugin-id>/plugin.json`
- 项目级：`<workspace>/.ai-employee/plugins/<plugin-id>/plugin.json`

项目级插件会覆盖同 id 的用户级插件。插件目录只扫描一级子目录，目录或清单为符号链接时不会加载。

## 清单

```json
{
  "schemaVersion": 1,
  "id": "my-tools",
  "name": "我的工具",
  "version": "1.0.0",
  "description": "提供团队内部工具",
  "type": "runtime",
  "enabled": true,
  "author": { "name": "Example" },
  "content": {
    "skills": "./skills/",
    "docs": "./docs/",
    "scripts": "./scripts/"
  },
  "runtime": { "type": "node", "minimumVersion": "20" },
  "interface": {
    "displayName": "我的工具",
    "category": "Engineering",
    "capabilities": ["Read", "Write"]
  },
  "permissions": {
    "filesystem": { "allowedPaths": ["${workspace}"] },
    "network": { "allowedHosts": ["api.example.com"] }
  },
  "components": [
    {
      "id": "internal-search",
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
  ],
  "tools": ["search_internal_docs"]
}
```

`components` 是推荐格式，一个插件可以声明多个 `mcp`、`skill`、`provider` 或 `tool` 组件。当前桌面端会把启用的 `mcp` 组件注入会话；`skill`、`provider` 和 `tool` 组件先作为运行时元数据发现，不会被当作 MCP Server 直接启动。

MCP 组件的 `config` 使用现有 MCP 配置格式，也可以使用 `http` 或 `sse` 传输。stdio 插件默认以插件目录作为 `cwd`，因此清单中的相对脚本路径在 macOS 和 Windows 都可以工作。

## 使用方式

1. 将插件目录复制到用户级或项目级目录。
2. 打开项目聊天的“设置 → 插件与工具”。
3. 确认插件被发现并打开开关。
4. 新的本地会话会把已启用插件的 MCP server 注入工具列表。

未启用或清单无效的插件不会进入 AI 工具列表。插件服务进程仍然遵循 MCP 工具调用和现有权限确认流程；插件目录本身不会被自动下载或执行。
