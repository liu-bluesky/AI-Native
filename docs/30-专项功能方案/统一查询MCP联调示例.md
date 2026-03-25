# 统一查询 MCP 联调示例

## 1. 准备

- API 服务地址：`http://localhost:8000`
- 需要可用 API Key（用于 MCP 访问）
- 统一查询 MCP 地址：
  - SSE: `http://localhost:8000/mcp/query/sse?key=$API_KEY`
  - HTTP: `http://localhost:8000/mcp/query/mcp?key=$API_KEY`

示例环境变量：

```bash
export BASE_URL="http://localhost:8000"
export API_KEY="<YOUR_API_KEY>"
```

## 2. 推荐调用顺序

统一查询 MCP 的推荐链路：

1. 先读取 `query://usage-guide`
2. 再调用 `search_ids(keyword="<用户原始问题>")` 定位项目 ID
3. 锁定项目后调用 `get_manual_content(project_id="<project_id>")`
4. 若任务需要项目协作，调用 `execute_project_collaboration(project_id="<project_id>", task="<用户原始任务>")`

说明：

- 统一查询 MCP 仍以查询优先。
- 如宿主只接统一入口，项目协作型任务优先走 `execute_project_collaboration`。
- `execute_project_collaboration` 是统一编排入口，但是否单人主责、是否需要多人协作以及如何拆分，仍由 AI 结合项目手册、员工手册、规则和工具自主判断。
- 如果需要手动编排，再继续调用 `list_project_members` / `get_project_runtime_context` / `list_project_proxy_tools` / `invoke_project_skill_tool`。

## 3. 读取统一入口使用说明

如果宿主支持 MCP Resource，先读取：

- `query://usage-guide`

如需直接用 HTTP JSON-RPC 验证，可先调用任一基础工具确认入口可用，例如：

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_ids",
      "arguments": {
        "keyword": "请只回复当前可用的项目 ID",
        "limit": 3
      }
    }
  }'
```

## 4. 完整链路示例

下面示例展示一条完整链路：

- 保留用户原始问题
- 先定位项目 ID
- 再读取项目手册
- 最后从统一入口发起项目协作编排

### 4.1 先定位项目 ID

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "search_ids",
      "arguments": {
        "keyword": "请帮我在 ai设计规范 项目里完成一个新的前端页面需求，并判断是否需要多人协作",
        "limit": 10
      }
    }
  }'
```

从返回结果中拿到目标项目 `project_id`，例如：

- `proj-d16591a6`

### 4.2 读取项目手册

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "get_manual_content",
      "arguments": {
        "project_id": "proj-d16591a6"
      }
    }
  }'
```

建议：

- 把返回的 `manual` 当作当前会话规则使用。
- 未读取项目手册前，不要直接回答当前项目相关问题。

### 4.3 从统一入口发起项目协作编排

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "execute_project_collaboration",
      "arguments": {
        "project_id": "proj-d16591a6",
        "task": "请完成一个新的前端页面需求，先梳理规则，再由 AI 自主判断是否需要协作并输出实现方案",
        "max_employees": 3,
        "max_tool_calls": 6,
        "auto_execute": true,
        "include_external_tools": true
      }
    }
  }'
```

返回结果重点字段：

- `project_id`：当前项目 ID
- `selected_employee_ids`：本轮被纳入协作范围的员工
- `selected_members`：参与协作的员工摘要
- `candidate_tools`：按任务匹配出的候选工具
- `plan_steps`：系统生成的协作步骤
- `executed_calls`：已自动执行的安全调用
- `skipped_calls`：未自动执行的调用及原因

## 5. 需要手动编排时的回退链路

如果你不想让统一入口自动编排，或者要自己控制参数，建议改用：

1. `list_project_members(project_id)`
2. `get_project_runtime_context(project_id)`
3. `list_project_proxy_tools(project_id, employee_id)`
4. `invoke_project_skill_tool(project_id, tool_name, employee_id, args, args_json, timeout_sec)`

示例：

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "list_project_members",
      "arguments": {
        "project_id": "proj-d16591a6"
      }
    }
  }'
```

## 6. 使用建议

- 首轮查询一定保留用户原始问题，优先放进 `search_ids.keyword`。
- 如宿主只接统一入口，项目协作型任务优先调用 `execute_project_collaboration`。
- 不要把 `execute_project_collaboration` 理解成固定分工路由；它只是统一编排入口，具体协作方式由 AI 结合手册、规则和工具决定。
- 如果宿主同时支持统一 MCP 和项目 MCP，复杂执行场景仍优先直连项目 MCP。
- 统一查询 MCP 不暴露 `save_project_memory` / `save_employee_memory`；如需显式写记忆，改用项目 MCP 或员工 MCP。
