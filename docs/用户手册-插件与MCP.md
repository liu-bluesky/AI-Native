# 插件与 MCP 配置手册

这份文档面向使用桌面端的普通用户。你不需要修改 Rust 或 Vue 代码，只需要准备 MCP Server、放置插件清单，然后在项目聊天设置中启用插件。

## 1. 先理解两个概念

| 名称 | 作用 |
| --- | --- |
| 插件 | 一组可安装、可启用、可停用的业务能力，例如部署、内部知识库、项目管理 |
| MCP | 插件与 AI 之间的工具通信协议，MCP Server 才是真正提供工具的程序 |

简单理解：**插件是包装盒，MCP Server 是盒子里的工具。**

## 2. 使用内置插件

打开项目聊天页面，进入：

```text
设置 → 插件与工具
```

当前内置插件包括：

- 项目管理：项目列表、项目详情、切换工作区。
- 部署发布：读取部署目标、发布工作区文件。
- 媒体生成：按需求生成或编辑图片、视频、音频，以及音频转写。

打开开关后，插件工具才会进入 AI 工具列表。关闭开关后，AI 不会看到这些工具，也不会调用它们。

不需要点击“部署”“生成图片”等固定按钮。直接告诉 AI 你的需求即可，例如：

```text
把当前项目发布到测试环境。
```

AI 会根据当前启用的插件和用户需求决定是否调用工具。

## 3. 安装外部 MCP 插件

插件目录结构如下：

```text
<项目工作区>/
└── .ai-employee/
    └── plugins/
        └── company-search/
            ├── plugin.json
            └── server.mjs
```

也可以安装为用户级插件，让多个项目使用：

```text
macOS：~/.ai-employee/plugins/company-search/plugin.json
Windows：%USERPROFILE%\.ai-employee\plugins\company-search\plugin.json
```

插件目录只扫描一级子目录。将插件复制完成后，重新打开“插件与工具”设置即可发现。

## 4. 配置 stdio MCP

stdio 适合 MCP Server 运行在用户本机上的情况。下面示例使用 Node.js：

```json
{
  "id": "company-search",
  "name": "公司知识库搜索",
  "version": "1.0.0",
  "description": "搜索公司内部知识库",
  "type": "mcp",
  "enabled": true,
  "server": {
    "type": "stdio",
    "command": "node",
    "args": ["server.mjs"],
    "env": {
      "COMPANY_API_TOKEN": "请替换为自己的 Token"
    }
  },
  "tools": ["search_company_docs"]
}
```

使用 Python 时：

```json
{
  "server": {
    "type": "stdio",
    "command": "python",
    "args": ["server.py"]
  }
}
```

stdio 插件默认以插件目录作为工作目录，所以 `server.mjs`、`server.py` 等相对路径在 macOS 和 Windows 都可以使用。

Windows 如果使用 npm 命令，通常填写：

```json
{
  "server": {
    "type": "stdio",
    "command": "npx.cmd",
    "args": ["-y", "@example/company-search-mcp"]
  }
}
```

## 5. 配置 HTTP 或 SSE MCP

如果 MCP Server 已经运行在本机或服务器上，可以使用 HTTP：

```json
{
  "id": "company-api",
  "name": "公司 API",
  "version": "1.0.0",
  "type": "mcp",
  "enabled": true,
  "server": {
    "type": "http",
    "url": "http://127.0.0.1:8787/mcp"
  }
}
```

SSE 示例：

```json
{
  "server": {
    "type": "sse",
    "url": "https://example.com/mcp/sse"
  }
}
```

HTTP/SSE Server 必须能够从当前电脑访问，并且必须真正实现 MCP 协议，普通 REST API 地址不能直接使用。

## 6. 启用和停用

1. 打开项目聊天。
2. 进入“设置 → 插件与工具”。
3. 找到外部插件。
4. 打开或关闭右侧开关。
5. 新发起的本地会话会使用最新插件列表。

项目级插件只影响当前项目。用户级插件可以被多个项目发现，但每个项目仍然可以单独控制是否启用。

## 7. 常见问题

### 找不到插件

检查以下内容：

- 路径是否为 `.ai-employee/plugins/<plugin-id>/plugin.json`。
- `plugin.json` 是否是合法 JSON。
- 是否填写了非空的 `id`。
- `type` 是否为 `mcp`。
- 当前项目工作区是否配置正确。
- 是否重新打开了设置页面。

### 插件显示但无法启用

通常是 `server` 缺失、不是 JSON 对象，或者 MCP Server 配置不完整。先确认 `command + args` 或 `url` 正确。

### MCP 工具没有出现

- 确认插件开关已打开。
- 确认 MCP Server 程序可以独立启动。
- 确认 Node.js/Python 已加入系统 PATH。
- Windows 优先尝试使用 `npx.cmd`、`npm.cmd` 等命令。
- HTTP/SSE 地址需要在浏览器或其他工具中确认可以访问。

### MCP Server 会不会自动执行？

插件清单不会被自动下载。只有用户将插件放入插件目录并在设置中启用后，新的本地会话才会连接对应 MCP Server。涉及本地文件、命令或敏感操作时，仍然遵循现有授权确认流程。

