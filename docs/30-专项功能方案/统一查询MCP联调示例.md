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
  -H "Accept: application/json, text/event-stream" \
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
  -H "Accept: application/json, text/event-stream" \
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
  -H "Accept: application/json, text/event-stream" \
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

### 4.3 聚合当前任务最相关的上下文

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "resolve_relevant_context",
      "arguments": {
        "task": "请完成一个新的前端页面需求，先梳理规则，再由 AI 自主判断是否需要协作并输出实现方案",
        "project_id": "proj-d16591a6",
        "limit": 5
      }
    }
  }'
```

建议重点看：

- `project.summary`
- `matched_members`
- `matched_rules`
- `matched_tools`

### 4.4 生成执行步骤骨架

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "generate_execution_plan",
      "arguments": {
        "task": "请完成一个新的前端页面需求，先梳理规则，再由 AI 自主判断是否需要协作并输出实现方案",
        "project_id": "proj-d16591a6",
        "max_steps": 6
      }
    }
  }'
```

建议重点看：

- `planning_mode`
- `selected_employee_ids`
- `selected_members`
- `candidate_tools`
- `plan_steps`

如果你的宿主或 CLI 只暴露 SSE 配置，也可以把同样的 JSON-RPC body 直接 `POST` 到：

- `POST /mcp/query/sse?key=$API_KEY`

当前统一入口会自动桥接到 streamable-http transport，返回体仍是 `text/event-stream`。

### 4.5 从统一入口发起项目协作编排

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 6,
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

### 4.6 通过项目 ID 显式保存对话内容

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 7,
    "method": "tools/call",
    "params": {
      "name": "save_project_memory",
      "arguments": {
        "project_id": "proj-d16591a6",
        "content": "问题：统一查询 MCP 需要支持按项目写入对话内容\n结论：调用 save_project_memory(project_id, content, ...) 每次有效对话补记一次"
      }
    }
}'
```

### 4.7 保存工作事实

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 8,
    "method": "tools/call",
    "params": {
      "name": "save_work_facts",
      "arguments": {
        "project_id": "proj-d16591a6",
        "employee_id": "emp-9f0b6c4d",
        "session_id": "sess-demo-001",
        "phase": "Phase 3",
        "step": "Step 1",
        "status": "in_progress",
        "goal": "把 query MCP 记忆升级为结构化执行轨迹",
        "facts": [
          "已完成 query MCP 挂载级联调测试",
          "已确认 SSE bridge 可直接承载 JSON-RPC body"
        ],
        "changed_files": [
          "web-admin/api/services/dynamic_mcp_apps_query.py",
          "web-admin/api/tests/test_unit.py"
        ],
        "verification": [
          "python -m py_compile web-admin/api/services/dynamic_mcp_apps_query.py"
        ],
        "risks": [
          "仍需真实 API Key 联调"
        ],
        "next_steps": [
          "追加 verification 事件并生成 checkpoint"
        ]
      }
    }
  }'
```

### 4.8 追加会话事件

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 9,
    "method": "tools/call",
    "params": {
      "name": "append_session_event",
      "arguments": {
        "project_id": "proj-d16591a6",
        "employee_id": "emp-9f0b6c4d",
        "session_id": "sess-demo-001",
        "event_type": "verification",
        "content": "已完成标准链路和记忆链路联调",
        "phase": "Phase 3",
        "step": "Step 2",
        "status": "completed",
        "verification": [
          "uv run pytest web-admin/api/tests/test_unit.py -k query_mcp"
        ],
        "next_steps": [
          "更新 docs/总结文档.md 并保存项目记忆"
        ]
      }
    }
  }'
```

### 4.9 恢复工作轨迹与检查点

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 10,
    "method": "tools/call",
    "params": {
      "name": "resume_work_session",
      "arguments": {
        "project_id": "proj-d16591a6",
        "employee_id": "emp-9f0b6c4d",
        "session_id": "sess-demo-001"
      }
    }
}'
```

返回结果重点字段：

- `items[].trajectory`：每条记忆解析出的结构化轨迹
- `phases`：当前会话涉及的阶段列表
- `steps`：当前会话涉及的步骤列表
- `changed_files`：聚合出的相关文件
- `verification`：聚合出的验证动作
- `risks`：当前遗留风险
- `next_steps`：下一步建议
- `latest_status`：最近轨迹状态
- `timeline`：按时间排序的轻量执行时间线

补充说明：

- 当前轨迹会同时写入项目记忆和独立 `work_session_store`。
- 后台也可以直接查看：
  - `GET /api/work-sessions`
  - `GET /api/work-sessions/{session_id}`
  - 页面 `/work-sessions`

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 11,
    "method": "tools/call",
    "params": {
      "name": "summarize_checkpoint",
      "arguments": {
        "project_id": "proj-d16591a6",
        "employee_id": "emp-9f0b6c4d",
        "session_id": "sess-demo-001"
      }
    }
  }'
```

也可以先做“元数据探活”，确认真实入口已经把工具和资源暴露出来：

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 100,
    "method": "tools/list",
    "params": {}
  }'
```

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 101,
    "method": "resources/list",
    "params": {}
  }'
```

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 102,
    "method": "resources/read",
    "params": {
      "uri": "query://usage-guide"
    }
  }'
```

建议至少确认以下资源已经可读：

- `query://usage-guide`
- `query://client-profile/claude-code`
- `query://client-profile/codex`
- `query://client-profile/generic-cli`

补充说明：

- `POST /mcp/query/mcp` 和 `POST /mcp/query/sse` 做 JSON-RPC 调用时，客户端需要显式带上 `Accept: application/json, text/event-stream`。
- 若缺少该请求头，streamable-http transport 会返回 `406 Not Acceptable`，这不是业务错误，而是协议协商未满足。

说明：

- `project_id` 必填，用于定位项目与活跃成员。
- `content` 必填，建议保存“问题 / 结论 / 关键决策”这种结构化文本。
- 未传 `employee_id` 时，会按项目范围写入当前活跃成员，便于后续从项目记忆统一召回。

## 5. 需要手动编排时的回退链路

如果你不想让统一入口自动编排，或者要自己控制参数，建议改用：

1. `list_project_members(project_id)`
2. `get_project_runtime_context(project_id)`
3. `list_project_proxy_tools(project_id, employee_id)`
4. `invoke_project_skill_tool(project_id, tool_name, employee_id, args, args_json, timeout_sec)`

示例：

```bash
curl -sS -X POST "$BASE_URL/mcp/query/mcp?key=$API_KEY" \
  -H "Accept: application/json, text/event-stream" \
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
- 每次有效对话结束后，调用 `save_project_memory(project_id, content, ...)` 显式补记本轮对话内容。
- 如宿主只接统一入口，项目协作型任务优先调用 `execute_project_collaboration`。
- 不要把 `execute_project_collaboration` 理解成固定分工路由；它只是统一编排入口，具体协作方式由 AI 结合手册、规则和工具决定。
- 如果宿主同时支持统一 MCP 和项目 MCP，复杂执行场景仍优先直连项目 MCP。
- 统一查询 MCP 已暴露 `save_project_memory`，可通过 `project_id` 直接写入项目对话内容；`save_employee_memory` 仍不暴露。
