# 项目模块 MCP 联调示例

## 1. 准备

- API 服务地址：`http://localhost:8000`
- 需要管理员登录拿到 `Bearer Token`
- 需要可用 API Key（用于 MCP 访问）

示例环境变量：

```bash
export BASE_URL="http://localhost:8000"
export TOKEN="<YOUR_BEARER_TOKEN>"
export API_KEY="<YOUR_API_KEY>"
```

## 2. 创建项目

```bash
curl -sS -X POST "$BASE_URL/api/projects" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "web-admin",
    "description": "Web 管理台项目",
    "mcp_enabled": true,
    "feedback_upgrade_enabled": true
  }'
```

返回里取 `project.id`，记为 `PROJECT_ID`。

## 3. 添加项目成员

```bash
curl -sS -X POST "$BASE_URL/api/projects/$PROJECT_ID/members" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "employee_id": "emp-8cd60aec",
    "role": "member",
    "enabled": true
  }'
```

## 4. 查看成员

```bash
curl -sS "$BASE_URL/api/projects/$PROJECT_ID/members" \
  -H "Authorization: Bearer $TOKEN"
```

## 5. 项目 MCP 地址

- SSE: `http://localhost:8000/mcp/projects/$PROJECT_ID/sse?key=$API_KEY`
- HTTP: `http://localhost:8000/mcp/projects/$PROJECT_ID/mcp?key=$API_KEY`

## 6. MCP 工具调用示例（HTTP JSON-RPC）

### 6.1 列出项目成员

```bash
curl -sS -X POST "http://localhost:8000/mcp/projects/$PROJECT_ID/mcp?key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "list_project_members",
      "arguments": {}
    }
  }'
```

### 6.2 查询项目规则

```bash
curl -sS -X POST "http://localhost:8000/mcp/projects/$PROJECT_ID/mcp?key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "query_project_rules",
      "arguments": {
        "keyword": "数据库"
      }
    }
  }'
```

### 6.3 提交项目反馈工单

```bash
curl -sS -X POST "http://localhost:8000/mcp/projects/$PROJECT_ID/mcp?key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "submit_project_feedback_bug",
      "arguments": {
        "employee_id": "emp-8cd60aec",
        "title": "接口字段不一致",
        "symptom": "前端提交字段后端未识别",
        "expected": "接口字段定义与文档一致",
        "category": "api-contract",
        "severity": "high"
      }
    }
  }'
```

### 6.4 项目协作编排执行

适用场景：
- 接入方只连接项目 MCP，希望直接输入一个任务，由 AI 结合项目手册、员工手册、规则和工具，自主判断是否需要多人协作并尝试执行。
- 不想自己先做“选人 -> 查工具 -> 手动逐个调用”的编排。

```bash
curl -sS -X POST "http://localhost:8000/mcp/projects/$PROJECT_ID/mcp?key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "execute_project_collaboration",
      "arguments": {
        "task": "请完成一个新的前端页面需求，先梳理规则，再由 AI 判断是否需要协作并输出实现方案",
        "max_employees": 3,
        "max_tool_calls": 6,
        "auto_execute": true,
        "include_external_tools": true
      }
    }
  }'
```

返回结果说明：
- `selected_employee_ids`：本轮被纳入协作范围的项目成员。
- `candidate_tools`：按任务匹配出的候选工具。
- `plan_steps`：项目 MCP 生成的协作执行步骤。
- `executed_calls`：已自动执行的安全调用。
- `skipped_calls`：因参数不可安全映射等原因未自动执行的调用。

建议：
- 如果只是做项目内多员工协作，优先调用 `execute_project_collaboration`。
- `execute_project_collaboration` 是统一编排入口，不预设前端/后端/行业顾问等固定分工模板；若单个成员已能闭环，可保持单人主责。
- 如果需要人工精细控制参数或执行顺序，再回退到 `list_project_members` / `get_project_runtime_context` / `list_project_proxy_tools` / `invoke_project_skill_tool`。

## 7. 前端入口

- 项目列表：`#/projects`
- 项目详情：`#/projects/{project_id}`
