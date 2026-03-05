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

## 7. 前端入口

- 项目列表：`#/projects`
- 项目详情：`#/projects/{project_id}`
