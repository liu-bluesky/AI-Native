# liuAgent CLI 智能体的手规划

## 相关文档

- [项目设计](./PROJECT_DESIGN.md)

## 定位

liuAgent CLI 的“手”是一个受控工具执行层。模型只负责提出工具调用意图，CLI 负责校验、授权、执行和把结果回传给模型。

```text
模型 -> tool_call -> 权限检查 -> 工具执行 -> observation -> 模型继续推理
```

## 手的最小架构

### 1. Tool Registry

登记所有工具，让模型知道有哪些能力可以用。

每个工具保留：

- `name`: 工具名
- `description`: 用途说明
- `input_schema`: JSON Schema 参数定义
- `action`: 权限策略动作名，例如 `file.read`、`file.write`、`command.run`
- `risk`: 风险等级
- `requires_approval`: 默认是否需要用户确认
- `scope`: 工具允许访问的资源范围
- `execute`: 执行函数

### 2. Tool Router

接收模型的 `tool_call`，按工具名找到对应工具。

Router 只负责分发，不直接执行危险动作。

### 3. Permission Gate

所有工具执行前都要过权限闸门。

主要检查：

- 路径是否在 workspace 内
- 参数是否符合 `input_schema`
- 命令是否高风险
- 是否涉及删除、覆盖、部署、发消息、网络写入
- 是否可能读取或外传本地凭据

### 4. Tool Executor

真正执行工具，并统一返回结果。

```json
{
  "tool_result_id": "result_001",
  "tool_call_id": "call_001",
  "ok": true,
  "content": "读取 120 行，命中 3 处。",
  "summary": "读取文件成功",
  "data": {},
  "error": null,
  "audit_id": "audit_001",
  "created_at": "2026-06-20T07:00:00Z"
}
```

### 5. Observation Adapter

把工具结果整理成模型能继续使用的 observation。

要求：

- 长文件只回传相关片段
- 长命令输出要截断
- 错误也要回传给模型
- 结构化结果优先保留 JSON

## 第一批工具

### 文件工具

- `list_files`: 列目录
- `read_file`: 读文件
- `search_text`: 搜索文本
- `apply_patch`: 修改文件
- `write_file`: 新建文件，默认需要确认

### 命令工具

- `run_command`: 执行本地命令
- `check_command_risk`: 判断命令风险

默认限制在 workspace 内执行。删除、安装依赖、部署、写系统目录必须确认。

### 网络工具

- `http_get`: 读取公开 URL
- `http_post`: 调用外部 API，默认需要确认
- `download_file`: 下载文件到 workspace

网络工具不能自动携带本地凭据。

### MCP 工具

- `list_mcp_tools`: 发现 MCP 工具
- `call_mcp_tool`: 调用 MCP 工具
- `read_mcp_resource`: 读取 MCP 资源

MCP 工具也必须经过同一套权限闸门。

## 权限等级

| 等级 | 例子 | 策略 |
| --- | --- | --- |
| safe | 读文件、列目录、搜索 | 自动执行 |
| medium | 写 workspace 文件、运行只读命令 | 可配置确认 |
| high | 删除、安装依赖、网络写入 | 必须确认 |
| critical | 部署、发消息、外传密钥、系统目录写入 | 默认禁止或强确认 |

## 最小执行循环

```text
1. 用户输入
2. 调模型
3. 模型返回最终答案：结束
4. 模型返回工具调用：
   - 校验工具名
   - 校验参数
   - 经过权限闸门
   - 执行工具
   - 回传 observation
5. 回到第 2 步
```

## 第一版边界

第一版只把“手”做稳，不先做复杂多智能体。

优先保证：

- 工具可被模型发现
- 参数可校验
- 执行有权限控制
- 结果能回传模型
- 失败后模型还能继续处理

后续再扩展长期记忆、多人协作、远程执行和任务树。
