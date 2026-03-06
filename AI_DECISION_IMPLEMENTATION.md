# AI 自主决策对话模块 - 实施完成

## 已完成的改造

### 1. 核心模块 (`ai_decision.py`)

- `execute_db_query()`: 直接查询数据库（自动使用系统配置的连接）
- `ai_decide_action()`: AI 自主决策调用什么工具
- `recommend_better_project()`: 跨项目推荐

### 2. API 端点 (`/api/projects/{project_id}/smart-query`)

**请求：**

```json
{
  "message": "查询所有员工"
}
```

**响应示例：**

```json
{
  "status": "ok",
  "action": "query_db",
  "result": {
    "status": "ok",
    "rows": [...],
    "count": 10
  },
  "reason": "直接查询数据库获取员工列表"
}
```

### 3. 前端调用 (`smart-query.js`)

```javascript
import { smartQuery } from "@/api/smart-query";

const result = await smartQuery(projectId, "查询所有员工");
console.log(result.action); // 'query_db' | 'call_tool' | 'recommend_project'
```

## 核心优势

| 对比项     | 旧方案            | 新方案           |
| ---------- | ----------------- | ---------------- |
| 工具选择   | 固定规则链        | AI 理解意图决策  |
| 数据库访问 | 需要配置 MCP 工具 | 直接复用系统连接 |
| 项目切换   | 手动              | AI 主动推荐      |
| 扩展性     | 新增工具需改规则  | 自动识别新工具   |

## 测试方法

```bash
# 启动服务
cd web-admin/api
python server.py

# 测试查询
curl -X POST http://localhost:8000/api/projects/{project_id}/smart-query \
  -H "Content-Type: application/json" \
  -d '{"message": "查询所有员工"}'
```

## 下一步建议

1. 在前端项目详情页添加智能查询输入框
2. 集成到现有聊天界面（如果有）
3. 添加查询历史记录
4. 优化 AI 决策的 prompt
   ✦ 为了实现“通过对话就能直接开发项目，并真实调用当前员工（AI Agent）绑定的能力”，我们需要将现有的 ProjectChat
   模块从一个“纯对话（Chat）”系统，升级为一个“带有工具调用能力的 Agentic 工作流（Agent Loop）”系统。

结合你目前的系统架构（基于 MCP 协议的动态技能分配），我为你提供以下全链路优化方案：

核心优化思路
目前你们的 Chat 只是把员工的 技能列表 拼成文本塞到了 System Prompt 里（见 \_build_project_chat_messages）。我们需要将其改为大模型原生的 Function
Calling（工具调用）机制，让模型不仅能“说话”，还能直接“执行动作”（比如读写文件、查数据库、运行终端命令）。

---

一、 后端改造方案 (Backend)

1. 升级 llm_provider_service.py 支持工具调用 (Tool Calling)
   当前的 chat_completion_stream 仅支持纯文本输出，需做如下升级：

- 增加参数：允许传入 tools 列表参数。
- 解析 Stream Chunk：兼容 OpenAI 标准的 tool_calls stream chunk 解析。当模型选择调用工具时，不再返回 content，而是返回 tool_calls 的函数名和参数片段。

2. 修改 WebSocket 路由 (Agent 循环引擎)
   重构 routers/projects.py 中的 ws_project_chat，引入ReAct 循环（思考 -> 行动 -> 观察）：

- 注入工具：从选中的 Employee ID 获取其绑定的所有 MCP Skills，转化为 OpenAI 格式的 tools 数组。
- 执行死循环 (Agent Loop)：
  1.  将 messages 和 tools 发给大模型（流式）。
  2.  如果大模型返回纯文本，则 WebSocket 返回 delta 事件给前端。
  3.  如果大模型返回 tool_calls，后端拦截并暂停生成，通过你现有的 dynamic_mcp.invoke_project_skill_tool_runtime 真实执行该工具（例如向工作区写代码）。
  4.  拿到工具执行结果后，将结果包装成 role: "tool" 追加到 messages 里。
  5.  重新触发大模型，让它基于执行结果继续回答或调用下一个工具，直到它认为任务完成并返回纯文本。

3. 上下文深度注入 (Context Injection)
   开发项目需要代码库上下文。在 \_build_project_chat_messages 中优化：

- 不再仅仅注入 workspace_path，可以默认附带当前工作区根目录的目录结构（树状图，限制层级）。
- 注入该员工设定的人设（Persona）和相关规则（Rules），确保代码风格符合你们的 ai设计规范。

---

二、 前端改造方案 (Frontend)

对于用户来说，“AI 正在改代码”的过程必须是透明且可控的。

1. WebSocket 协议增加 Tool 事件
   现有的 WS 只处理 delta 和 done，需要增加对工具调用的解析：

- tool_start：展示“正在调用技能：[工具名]...”的加载状态。
- tool_result：展示工具调用的返回结果摘要（比如“✅ 成功修改文件 main.py”）。

2. UI 交互渲染 (ProjectChat.vue)

- 动作卡片 (Action Card)：当收到 tool_start 时，在对话气泡中渲染一个卡片（类似 Cursor 或 Claude 的行为卡片）。
- 多步骤合并：由于 AI 可能会连续调用多个工具（如：先查目录 -> 再读文件 -> 最后写文件），前端需要把这一系列动作收拢到同一个对话气泡中，避免刷屏。

---

三、 MCP 技能扩充建议 (Skills)

为了让员工真正能“开发项目”，该项目绑定的员工需要具备以下基础的 MCP 技能（如果没有，需要补充）：

1.  read_file：读取指定路径的文件内容。
2.  write_file / replace_in_file：覆盖或修改代码内容。
3.  list_directory / glob：查看项目目录和搜索文件。
4.  run_shell_command：（可选并需带安全确认）执行构建、测试、Git 操作等终端命令。

总结
现在的流程：User -> (文本) -> AI -> (文本) -> User，AI 只是给了你代码，你要自己去复制粘贴。
优化后的流程：User -> AI -> AI 触发绑定员工的 MCP File Tool 修改本地代码 -> AI 告诉 User “我已经帮你改好了”。

如果你觉得这个方向契合你的需求，我可以立刻开始为你编写并修改后端的 projects.py 和 llm_provider_service.py 核心代码，把 Agentic Agent
Loop（工具执行引擎循环）的机制）落实到你的 WebSocket 中！
