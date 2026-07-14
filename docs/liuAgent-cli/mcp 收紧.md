# liuAgent 桌面 MCP 架构收紧升级计划

## 1. 文档目的

当前桌面智能体同时存在本地内置工具、MCP Host 管理工具、统一查询 MCP、当前项目 MCP、员工/规则/技能 MCP、项目外部 MCP 和用户自定义 MCP 等概念。服务端模块化本身没有问题，但这些内部分类被直接暴露给模型和用户后，产生了以下问题：

- 模型需要理解过多入口、Server 名和 wrapper，容易猜测不存在的 `default`、`project` 等名称。
- 同一业务工具可能同时通过动态直连工具和 `call_mcp_tool` 暴露，形成重复入口。
- 当前 Host 会遍历多个 Server 的 `tools/list`，把大量完整 Tool Schema 一次性放入模型上下文。
- 项目查询、任务树、规则技能和第三方系统工具混在同一层，权限边界不清晰。
- `current-project`、`query-center`、员工 MCP、规则 MCP、技能 MCP 等是实现细节，却进入了对话设置和 AI 决策范围。
- 工具风险曾被统一包装为 `mcp.call / medium`，远程工具真实的只读、写入、破坏性属性在路由过程中丢失。

本计划的目标不是取消 MCP Server 名称，也不是将所有工具永久扁平化给模型，而是收敛为：

> 桌面端只连接一个系统管理的物理 MCP Runtime；保留稳定的 MCP 服务标识和服务描述，先选服务、再按需发现工具、最后只向模型注入少量相关 Tool Schema。

## 2. 核心决策

### 2.1 一个物理入口

桌面智能体只自动接入一个系统管理的 MCP 入口：

```text
/mcp/runtime
```

桌面 Registry 中只有一个系统内置连接：

```json
{
  "mcpServers": {
    "runtime": {
      "type": "http",
      "url": "/mcp/runtime",
      "desktopAuth": true,
      "builtin": true,
      "enabled": true
    }
  }
}
```

`runtime` 是桌面与服务端之间的唯一物理连接，不等于把所有工具一次性暴露给模型。

### 2.2 保留服务名称和服务描述

MCP 服务名称不能删除。模型需要通过稳定的服务标识和服务描述判断能力来源与适用范围。

Runtime 内部维护 `Server Catalog`，至少包含：

```json
[
  {
    "server_id": "system",
    "display_name": "系统能力",
    "description": "访问当前系统的项目、智能体、规则、技能、任务树、工作会话和协作能力。",
    "domain": "system",
    "source": "builtin"
  },
  {
    "server_id": "feishu-prod",
    "display_name": "飞书生产环境",
    "description": "访问项目已授权的飞书通讯录、群组、文档和消息能力。",
    "domain": "integrations",
    "source": "user-configured"
  }
]
```

模型先依据服务描述选择服务范围，再在该服务内搜索相关工具。不得要求模型猜测未发现的 Server 名。

### 2.3 两个内部能力域

`system` 和 `integrations` 是逻辑能力域，不是要求用户配置的两个物理 MCP Server。

| 能力域 | 定义 | 典型内容 |
| --- | --- | --- |
| `system` | 平台源码内置、平台维护、使用桌面登录身份鉴权的系统能力 | 项目、智能体、规则、技能、任务树、工作会话、记忆、项目协作 |
| `integrations` | 后续配置、第三方提供或访问系统外部数据的能力 | 飞书、GitHub、Jira、数据库、FTP、云服务、用户自定义 MCP |

固定归属规则：

- 平台源码内置能力归 `system`。
- 用户、项目或管理员后续添加的 MCP 一律归 `integrations`。
- 用户不能把自定义 MCP 标记成 `system`。
- 管理员审核通过的外部 MCP 仍归 `integrations`，通过 `trust_level=verified` 表示信任级别，不新增第三个能力域。

### 2.4 用户自定义 MCP 保留独立 Server 身份

用户自定义 MCP 不能全部折叠成一个没有来源信息的 `integrations` Server。每个自定义 MCP 必须保留独立、稳定的 `server_id`、服务描述、授权配置和健康状态。

示例：

```text
domain=integrations
server_id=mysql-prod
tool_name=query
canonical_tool_id=integrations.mysql-prod.query
```

另一个 Server 即使也暴露 `query`，仍是：

```text
integrations.analytics-db.query
```

这样可以保证：

- 工具重名不冲突。
- 权限和凭据按 Server 隔离。
- 可单独启用、停用、删除和审计。
- 运行日志能追溯到具体第三方来源。
- 一个外部 MCP 故障不会污染其他 Server。

## 3. 目标架构

```text
ProjectChat / Desktop UI
  -> Desktop Agent Runtime
  -> Local Native Tools
       - read_file
       - apply_patch
       - run_command
       - browser/local connector
  -> Desktop MCP Host
       -> 单一物理连接：runtime
            -> Server Catalog
                 - system
                 - feishu-prod
                 - mysql-prod
                 - github-company
            -> Tool Index
            -> Tool Search / Tool Selection
            -> Selected Tool Schemas
            -> Route Resolver
                 - SystemToolProvider
                 - IntegrationMcpProvider
```

服务端可以继续模块化：

```text
RuntimeToolCatalog
  -> ProjectToolProvider
  -> AgentToolProvider
  -> RuleToolProvider
  -> SkillToolProvider
  -> TaskTreeToolProvider
  -> WorkSessionToolProvider
  -> IntegrationMcpProvider
```

这些 Provider 是服务端内部实现，不再分别作为桌面可配置 MCP Server 暴露。

## 4. 工具发现与上下文控制

### 4.1 三级发现模型

#### 第一级：Server Catalog

始终可用，但只包含少量服务元数据，不包含完整工具 Schema。

```json
{
  "servers": [
    {
      "server_id": "system",
      "description": "项目、智能体、规则、技能和工作流"
    },
    {
      "server_id": "feishu-prod",
      "description": "飞书通讯录、群组、文档和消息"
    }
  ]
}
```

#### 第二级：Tool Index

Host 或服务端持有轻量索引，只包含工具名、摘要、关键词、能力域、只读属性和参数摘要，不包含完整 JSON Schema。

```json
{
  "server_id": "system",
  "tools": [
    {
      "tool_id": "system.get_project_detail",
      "name": "get_project_detail",
      "summary": "获取当前项目详情和绑定智能体信息",
      "keywords": ["项目", "智能体", "成员", "绑定"],
      "read_only": true
    }
  ]
}
```

#### 第三级：Selected Tool Schemas

每轮根据用户目标和 Server/Tool 搜索结果，最多选取固定数量的候选工具，将完整 Schema 注入模型请求。

初始建议：

- 简单查询：最多 5 个 Tool Schema。
- 实现型任务：最多 10 个 Tool Schema。
- 外部集成：每个候选 Server 最多 5 个 Tool Schema。
- 如模型确实需要更多工具，必须再次发起工具搜索，不一次性扩大整个目录。

### 4.2 模型调用形式

模型最终仍调用具体工具，不调用通用 wrapper：

```json
{
  "server_id": "system",
  "name": "get_project_manual",
  "arguments": {}
}
```

外部 MCP：

```json
{
  "server_id": "feishu-prod",
  "name": "send_message",
  "arguments": {
    "chat_id": "oc_xxx",
    "text": "发布完成"
  }
}
```

Host 内部根据 `server_id + tool_name` 路由。模型不接触远程 URL、鉴权头、transport 和 Registry 配置。

### 4.3 不再暴露给模型的管理工具

以下工具从模型普通工具目录移除：

- `list_mcp_tools`
- `call_mcp_tool`
- `read_mcp_resource`

它们改为 MCP Host 内部协议能力：

- Server 发现由 Host 自动完成。
- Tool Index 由 Host 缓存和刷新。
- 资源引导由 Runtime bootstrap 按需读取。
- 路由由 Host 根据已发现的真实 Server/Tool 元数据完成。

如果某类高级客户端确实需要手工管理 MCP，可在调试接口中保留，但不能注册到普通桌面对话模型。

## 5. 统一工具元数据

所有 `system` 工具和外部 MCP 工具必须转换为同一目录结构：

```json
{
  "server_id": "system",
  "domain": "system",
  "name": "get_project_manual",
  "canonical_tool_id": "system.get_project_manual",
  "description": "获取当前项目使用手册正文",
  "inputSchema": {
    "type": "object",
    "properties": {}
  },
  "annotations": {
    "readOnlyHint": true,
    "destructiveHint": false,
    "idempotentHint": true,
    "openWorldHint": false
  },
  "_meta": {
    "permission_action": "project.read",
    "scope": "project",
    "provider": "project",
    "trust_level": "builtin"
  }
}
```

约束：

- 权限判断不能依赖 `get_`、`list_` 等名称前缀。
- 权限判断不能依赖 Server 名是否为 `system`。
- MCP 标准 annotations 是行为语义的第一事实源。
- `_meta.permission_action`、`scope` 和 `trust_level` 用于本系统权限、审计和 UI 展示。
- 缺少 annotations 的外部工具按“未知写入能力”处理，不能静默当成只读。

## 6. 权限模型

### 6.1 基本判定

| 条件 | 默认行为 |
| --- | --- |
| `readOnlyHint=true` 且 `destructiveHint!=true` | 直接执行并记录摘要审计 |
| `readOnlyHint=false`、非破坏性 | 按当前完整权限/询问模式判定 |
| `destructiveHint=true` | 必须进入高风险授权，不被普通完整权限静默放行 |
| `openWorldHint=true` | 进入外部系统策略，检查凭据、目标域和外部写入风险 |
| annotations 缺失 | 按未知写入工具处理并要求授权 |

### 6.2 完整权限模式

完整权限只代表允许预先批准的工作区和系统内普通操作，不代表取消所有高风险确认。

完整权限下可直接执行：

- 系统只读查询。
- 项目内部普通写入。
- 工作区内可恢复文件写入。
- 已授权范围内的幂等操作。

仍需单独确认：

- 删除、清空、覆盖关键数据。
- 部署、发布、上线。
- 向外部系统发送消息或创建公开内容。
- 凭据读取、暴露或跨域传输。
- 外部数据库破坏性写入。
- annotations 标记为 destructive 的操作。

### 6.3 外部 MCP 信任级别

```text
builtin         平台源码内置
verified        管理员审核过的外部 MCP
project         项目管理员配置
user-configured 普通用户添加
```

信任级别影响默认授权策略和 UI 提示，但不能覆盖工具的 destructive/openWorld 属性。

## 7. 当前入口迁移映射

| 当前入口/概念 | 目标归属 | 处理方式 |
| --- | --- | --- |
| `/mcp/query` | `system` Provider | 保留给外部 CLI；桌面不再直接挂载 |
| `/mcp/projects/{project_id}` | `system` Provider | 保留独立客户端兼容；桌面通过 runtime 使用 |
| `/mcp/employees/{employee_id}` | `system` Provider | 转为内部员工能力 Provider |
| `/mcp/rules/{rule_id}` | `system` Provider | 转为内部规则能力 Provider |
| `/mcp/skills/{skill_id}` | `system` Provider | 转为内部技能能力 Provider |
| 项目外部 MCP | `integrations` | 保留真实 server_id，通过 Integration Provider 代理 |
| 用户自定义 MCP | `integrations` | 保留真实 server_id、描述、凭据和工具目录 |
| `current-project` | 删除桌面概念 | 当前 project_id 由 runtime context 自动绑定 |
| `query-center` | 删除桌面概念 | 作为 system 内部 Provider，不要求模型选入口 |
| `call_mcp_tool` | Host 内部能力 | 不再注册给普通模型 |
| `list_mcp_tools` | Host 内部能力 | 替换为自动 Server Catalog 和 Tool Search |
| `read_mcp_resource` | Bootstrap 内部能力 | 资源按入口规则自动读取 |

## 8. 升级阶段

### 阶段 0：冻结契约和建立基线

目标：在改路由前固定现状、指标和兼容范围。

工作项：

- 导出当前桌面会话真实 `mcpServers`、工具数量和完整 Schema Token 占用。
- 统计模型调用 `list_mcp_tools`、`call_mcp_tool`、动态直连工具的比例。
- 记录 Server 名猜测、工具重名、授权误判和 tools/list 失败样本。
- 建立 `McpServerDescriptor`、`McpToolIndexEntry`、`SelectedToolSchema` 的版本化协议。
- 明确旧入口只允许在迁移期读，不新增依赖。

验收：

- 有可重复的基线测试和 Token/工具数量统计。
- 新协议字段、版本和错误码完成评审。

### 阶段 1：建立 Runtime Server Catalog

目标：新增 `/mcp/runtime`，先完成统一发现，不切换执行流。

服务端工作：

- 新增 `RuntimeMcpProxyApp`。
- 新增 `RuntimeToolCatalog` 和 Provider 注册机制。
- 将项目、智能体、规则、技能、任务树、工作会话能力注册为 `system` Provider。
- 将项目外部 MCP 和用户自定义 MCP 注册为 `integrations` Server Descriptor。
- 对所有工具输出统一 annotations 和 `_meta`。

桌面工作：

- 增加 runtime 连接的只读发现能力。
- 缓存 Server Catalog 和 Tool Index。
- 增加目录版本、ETag/哈希和失效刷新机制。

验收：

- Runtime Catalog 能完整覆盖当前桌面实际可用能力。
- 同一工具不会因 Provider 聚合产生重复 canonical ID。
- Catalog 变化能触发缓存失效。

### 阶段 2：实现按需 Tool Search

目标：停止把所有 MCP Tool Schema 一次性注入模型。

工作项：

- 建立服务描述匹配和 Tool Index 搜索。
- 搜索输入至少包含用户原始目标、当前项目上下文、上一轮工具结果和模型主动请求。
- 搜索结果返回候选原因、相关度、server_id、canonical_tool_id 和 annotations 摘要。
- 每轮只组装 Selected Tool Schemas。
- 对多轮会话保留最近成功工具，但设定 TTL 和最大数量。
- 模型明确请求未加载工具时，执行二次搜索，不猜测工具或 Server。

验收：

- 工具数量增长时，模型请求中的 Tool Schema Token 不再线性增长。
- “当前项目绑定几个智能体”只加载 system 下少量项目查询工具。
- “发送飞书消息”只加载目标飞书 Server 的相关工具。

### 阶段 3：切换桌面执行路由

目标：桌面正式只连接 runtime。

工作项：

- `desktop_project_mcp_config` 替换为 `desktop_runtime_mcp_config`。
- 删除自动注入 `current-project` 的逻辑。
- Rust 动态路由改为 `server_id + canonical_tool_id`。
- 模型工具调用不再经过 `call_mcp_tool` wrapper。
- Host 在执行前校验 Tool Index 版本与实际 Server tools/list 是否一致。
- 保留本地原生工具为独立执行域，不通过远程 MCP 绕行。

验收：

- 桌面请求中只有一个系统内置物理 MCP 连接。
- 模型仍能看到明确 Server 来源。
- 项目查询、任务树和外部 MCP 调用均能正确路由。

### 阶段 4：统一权限、审计和 UI

目标：统一权限事实源，隐藏内部入口分类。

工作项：

- 权限门只使用 annotations、permission_action、scope、trust_level 和用户权限模式。
- 审计记录包含 physical_server=`runtime`、logical_server_id、domain、canonical_tool_id、remote_server_id。
- 桌面设置移除 `current-project`、`query-center` 等系统 Server 配置。
- 普通界面只展示“系统能力已连接”和“外部 MCP 列表”。
- 外部 MCP 配置页保留 Server 名、描述、来源、授权、健康状态和工具数量。

验收：

- 用户不再需要理解系统内部 MCP 分类。
- 管理员仍能追溯具体 Provider 和外部 Server。
- 只读、写入、高风险和外部开放世界权限行为符合统一矩阵。

### 阶段 5：删除旧桌面入口

目标：移除重复入口和长期兼容分支。

删除项：

- 桌面自动挂载 `current-project`。
- 桌面直接挂载 `query-center`。
- 普通模型工具中的 `list_mcp_tools`、`call_mcp_tool`、`read_mcp_resource`。
- Vue 层对系统内置 MCP 的注入和合并。
- 根据工具名、前缀或失败结果猜测 Server 的逻辑。
- 同一远程工具的 wrapper 调用和动态直连双入口。
- 为旧 Server 名增加的静默别名和兜底分片。

旧 `/mcp/query`、`/mcp/projects/...` 等服务端入口可继续服务外部 CLI 和独立客户端，但不得再作为桌面内部依赖。

验收：

- 代码搜索不到桌面运行链路对 `current-project` 和 `query-center` 的依赖。
- 普通模型工具目录中不存在三个 MCP 管理 wrapper。
- 删除旧配置后没有静默 fallback。

## 9. 代码改造清单

### 9.1 服务端

建议新增：

```text
web-admin/api/services/mcp/runtime_catalog.py
web-admin/api/services/mcp/runtime_tool_search.py
web-admin/api/services/mcp/runtime_mcp_proxy_app.py
web-admin/api/services/mcp/providers/system_provider.py
web-admin/api/services/mcp/providers/integration_provider.py
```

重点修改：

| 文件/模块 | 改造方向 |
| --- | --- |
| `core/server.py` | 挂载 `/mcp/runtime` |
| `dynamic_mcp_runtime.py` | 复用现有 ContextVar、认证和 transport 基础设施 |
| `dynamic_mcp_apps_query.py` | 将工具注册能力抽成 system Provider，不复制业务逻辑 |
| `dynamic_mcp_apps_project.py` | 将项目工具注册能力抽成 system Provider |
| `dynamic_mcp_external_tools.py` | 输出 Integration Server Descriptor 和 Tool Index |
| external MCP store | 补 server description、domain、trust_level、catalog_version |

### 9.2 桌面 Rust Host

| 文件/模块 | 改造方向 |
| --- | --- |
| `liuagent_core/runtime.rs` | 只注入 runtime；按需构建模型 Tool Schema |
| `liuagent_core/tools/mcp.rs` | 增加 Server Catalog、Tool Index、缓存和 canonical route |
| `liuagent_core/definitions.rs` | 移除普通模型的 MCP 管理 wrapper 定义 |
| `liuagent_core/permission.rs` | 接收统一远程工具权限元数据 |
| `liuagent_core/types.rs` | 增加目录、搜索结果和选中工具协议结构 |
| `liuagent_core/state.rs` | 持久化 catalog hash、TTL 和最近选中工具 |

### 9.3 前端

| 文件/模块 | 改造方向 |
| --- | --- |
| `ProjectChat.vue` | 删除系统 MCP 注入、wrapper 特殊展示和 Server 猜测提示 |
| 对话设置 | 只显示系统能力状态与外部 MCP 管理入口 |
| MCP 管理页 | 展示外部 server_id、描述、健康状态、权限和工具数 |
| Trace Viewer | 展示逻辑 Server 来源和具体工具，不显示物理 runtime wrapper |

## 10. 测试矩阵

### 10.1 Catalog 与发现

- 只有 system 时能返回稳定 Server Catalog。
- 添加两个用户 MCP 后分别保留独立 server_id。
- 不同 Server 暴露同名工具时 canonical_tool_id 不冲突。
- Server 描述、工具描述或 schema 变化后 catalog version 更新。
- 禁用或删除 MCP 后 Tool Index 立即失效。

### 10.2 上下文控制

- 100 个远程工具时，简单项目查询只注入不超过 5 个 Schema。
- 外部 MCP 数量增加时，模型上下文不按完整工具数线性增长。
- 二次工具搜索能够加载首轮未选择的工具。
- 最近使用工具缓存不会跨项目、跨用户或跨聊天会话污染。

### 10.3 路由

- `system.get_project_manual` 路由到项目 Provider。
- `system.get_current_task_tree` 路由到任务树 Provider。
- `integrations.feishu-prod.send_message` 路由到指定外部 MCP。
- Server 不存在时返回明确 `mcp.server_not_found`，不猜别名。
- Tool 不存在时返回明确 `mcp.tool_not_found`，不切换其他 Server。
- 目录版本漂移时先刷新目录，不盲目执行旧 Schema。

### 10.4 权限

- system 只读工具不弹授权。
- system 普通写入在完整权限下按策略执行。
- destructive 工具始终进入高风险授权。
- external open-world 工具执行前检查凭据和外部目标。
- annotations 缺失的用户 MCP 不得按只读执行。
- 显式调用路径和动态选中路径执行同一权限逻辑。

### 10.5 隔离和安全

- 项目 A 的自定义 MCP 不出现在项目 B Catalog。
- 用户 A 的私人 MCP 不对用户 B 可见。
- Desktop token 不进入模型上下文和审计正文。
- 外部 MCP 凭据只由 Host/服务端 transport 使用。
- MCP 返回内容继续经过截断、敏感信息过滤和审计策略。

### 10.6 前端体验

- 用户无需配置 `current-project` 或 `query-center`。
- “当前可用 MCP”展示实际 Server Catalog，不展示猜测名称。
- Trace 显示“系统能力 / get_project_manual”或“飞书生产 / send_message”。
- 外部 MCP 不可用时展示具体 Server 健康错误，不影响 system 工具。

## 11. 验收标准

### 架构验收

- 桌面端只有一个系统管理的物理 MCP 连接：`runtime`。
- 系统内部能力统一归 `system`，不再向桌面暴露 query/project/employee/rule/skill 多入口。
- 用户自定义 MCP 统一归 `integrations`，但保留独立 server_id 和服务描述。
- 模型通过服务描述和 Tool Index 选择工具，不猜 Server 名。

### 上下文验收

- 完整 MCP 工具总数增加时，简单请求的模型 Tool Schema Token 基本保持稳定。
- 每轮注入工具数符合配置上限。
- 无需把所有 Server 的完整 `tools/list` 结果放入模型上下文。

### 行为验收

- 项目查询、绑定智能体、规则技能、任务树和工作会话能力正常。
- 外部 MCP 能按独立 Server 正确发现和调用。
- 不再出现 `get_projectget_project`、猜 `default/project` 或 wrapper/动态直连重复调用。
- 工具失败后只报告真实路由和错误，不编造事实、不静默换入口。

### 权限验收

- `get_project_manual` 等只读工具直接执行。
- 写入、破坏性、开放世界工具按统一权限矩阵处理。
- 完整权限不会在动态工具路由中丢失，也不会绕过不可逆操作确认。

### 代码验收

- 普通模型目录不再注册三个 MCP 管理 wrapper。
- Vue 不再注入或合并系统内置 MCP Server。
- Rust Host 不再遍历所有 Server 并永久注入全部完整 Schema。
- 没有工具名前缀判断、Server 别名猜测或长期兼容兜底。

## 12. 观测指标

升级前后至少比较：

- 每轮模型请求 Tool Schema 数量和 Token 数量。
- MCP Server Catalog 数量、Tool Index 数量和 Selected Tool 数量。
- tools/list 调用次数和缓存命中率。
- Server 猜测失败次数。
- 工具重名冲突次数。
- permission.required 的只读误报率。
- 动态路由失败率和目录漂移刷新次数。
- 外部 MCP 故障对 system 工具成功率的影响。

建议目标：

- 简单查询平均注入 Tool Schema 不超过 5 个。
- 不存在的 Server 猜测调用降为 0。
- 只读工具错误授权率降为 0。
- 同一工具重复入口调用率降为 0。
- 外部 MCP 故障不影响 system Catalog 和 system 工具调用。

## 13. 回滚边界

本升级不采用静默 fallback，但需要可控版本回滚。

允许：

- 通过桌面版本整体回滚到上一版 Host。
- 通过服务端发布版本整体回滚 Runtime Catalog。
- 在切换前使用显式 feature flag 选择旧路由或 runtime 路由。

禁止：

- Runtime 路由失败后静默切换 `current-project`。
- Tool 不存在时自动尝试 `query-center` 或其他 Server。
- 同时长期维护 wrapper 调用和动态直连两套执行事实源。
- 为旧工具名增加永久别名、字符串拼接或分片兜底。

Feature flag 只用于迁移期整链路切换：

```text
desktop_mcp_runtime_v1=false -> 完整旧链路
desktop_mcp_runtime_v1=true  -> 完整 runtime 链路
```

不能在一次 Agent Run 内混用两条链路。

## 14. 实施原则

1. 服务端模块化，桌面入口单一化。
2. 保留 Server 名称和描述，隐藏物理路由细节。
3. 先选 Server，再搜索工具，再注入少量完整 Schema。
4. 用户自定义 MCP 属于 integrations，但必须保留独立身份。
5. 权限由标准 annotations 和统一权限元数据决定。
6. 不让模型调用 MCP 管理 wrapper，不让模型猜 Server。
7. 不使用工具名前缀、别名、重复注册和静默 fallback 掩盖架构问题。
8. 本地原生工具继续由桌面 Runtime 执行，不迁移到服务端 MCP。

最终目标可以概括为：

> 一个桌面物理 MCP Runtime，一份统一 Server Catalog，两个内部能力域，多个有独立身份的逻辑 Server，按需选择工具，并用同一套权限和审计规则执行。
