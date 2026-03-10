# AI 员工工厂

uvicorn server:app --host 192.168.1.126 --port 8000
EXTERNAL_AGENT_RUNNER_URL=http://127.0.0.1:3931 uvicorn server:app --host 0.0.0.0 --port 8000
基于 MCP（Model Context Protocol）的 AI-Native 开发平台。用户可自由组合 Skills + Rules + Memory + Persona 创建多个 AI 员工，通过进化引擎实现"越用越聪明"。

## 技术栈

- **前端**: Vue 3 + Element Plus + Vite
- **后端**: Python FastAPI + FastMCP 3.0+
- **存储**: JSON 文件 + SQLite（Memory）
- **认证**: JWT HS256

## 快速启动

### 数据库初始化

**开发环境**（默认使用 JSON 文件存储）：

```bash
cd web-admin/api
pip install -e .
python init_admin.py  # 自动创建 data/ 目录和管理员账户（admin/123456）
```

**生产环境**（使用 PostgreSQL）：

```bash
# 1. 创建数据库
createdb ai_employee

# 2. 配置环境变量
export DATABASE_URL="postgresql://用户名:密码@localhost:5432/ai_employee"

# 3. 初始化（自动建表）
cd web-admin/api
pip install -e .
python init_admin.py  # 首次运行自动创建所有表
```

### 后端

```bash
cd web-admin/api
python server.py      # 开发模式（支持热更新）
```

生产模式：

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd web-admin/frontend
npm install
npm run dev
```

访问 `http://localhost:5173`

## 核心功能

- **员工管理**: 创建/配置多个 AI 员工，绑定技能、规则、人设
- **技能管理**: 上传 ZIP 技能包或从目录导入
- **规则管理**: 查询/提交/进化规则，支持反馈驱动升级
- **记忆管理**: 向量化存储，支持语义检索
- **人设管理**: 自定义 AI 员工画像与行为风格
- **进化引擎**: 分析使用模式，自动提出规则优化建议

## 项目结构

```
ai设计规范/
├── docs/                    # 设计文档
├── rules/                   # AI 可消费的规则文件
├── agents/                  # 项目专属智能体定义
├── mcp-skills/              # 技能管理 MCP 服务
├── mcp-rules/               # 规则管理 MCP 服务
├── mcp-memory/              # 记忆管理 MCP 服务
├── mcp-persona/             # 人设管理 MCP 服务
├── mcp-evolution/           # 进化引擎 MCP 服务
├── mcp-sync/                # 实时同步 MCP 服务
└── web-admin/               # 管理面板
    ├── api/                 # FastAPI 网关
    └── frontend/            # Vue 3 SPA
```

## 文档

- [项目总览](docs/00-项目总览/PROJECT.md) - 完整架构与技术细节
- [反馈驱动规则升级模块](docs/反馈驱动规则升级模块/README.md) - 进化引擎设计
- [编码规范](rules/) - 前端/后端/UI/MCP 服务开发规范

## License

MIT
⏺ 我已经详细分析了 /ai/chat  
 模块的代码，发现了严重的架构问题。你的直觉是对的，这个模块确实存在重大缺陷：

🔴 核心问题诊断

1. 假流式（Fake Streaming）问题

问题位置：llm_provider_service.py:486-489

if self.\_is_responses_provider(provider):
result = await self.chat_completion(provider_id, model_name, messages, temperature,
max_tokens, timeout)
yield {"content": result.get("content", "")} # ❌ 一次性返回全部内容
return

问题：对于 responses 类型的 provider，代码调用了非流式的 chat_completion，等待完整响应后一次性
yield，这根本不是真正的流式输出。

---

2. 流式解析逻辑缺陷

问题位置：llm_provider_service.py:518-528

async for line in resp.aiter_lines():
line = line.strip()
if not line or line == "data: [DONE]":
continue
if line.startswith("data: "):
try:
data = json.loads(line[6:])
delta = data.get("choices", [{}])[0].get("delta", {})
yield delta # ❌ 只返回 delta，没有处理 tool_calls
except (json.JSONDecodeError, IndexError, KeyError):
continue # ❌ 静默吞掉错误

问题：

- 只提取了 delta，没有处理 tool_calls 的流式片段
- 异常被静默吞掉，导致调试困难
- 没有处理 finish_reason，无法判断流是否正常结束

---

3. Agent Loop 的致命缺陷

问题位置：agent_loop.py:243

yield {"type": "done", "content": final_full_content}

问题：final_full_content 在整个 loop 过程中累积，但在 type: "done" 时一次性返回全部内容，这导致：

- 前端收到的 delta 事件是真实流式的
- 但最后的 done 事件又把完整内容重复发送一次
- 逻辑混乱：既想流式又想批量

---

4. 工具调用结果污染对话历史

问题位置：agent_loop.py:208-209

final_full_content += f"\n\n> ⚡️ 正在调用技能: `{tool_name}`...\n\n> ✅ 技能 `{tool_name}`
调用完成\n\n"

问题：工具调用的 UI 提示被混入
final_full_content，最终会被保存到对话历史中（projects.py:662），导致：

- 对话历史被污染
- 下次对话时，LLM 会看到这些 UI 标记
- 破坏了 messages 的纯净性

---

5. WebSocket 并发处理不当

问题位置：projects.py:688-690

task = asyncio.create_task(handle_request(payload))
if request_id:
active_tasks[request_id] = task

问题：

- handle_request 是 async def，但内部的 run_agent_loop 是流式生成器
- 如果用户快速发送多条消息，多个 task 会并发执行
- 没有队列机制，可能导致消息乱序或资源竞争

---

📊 问题总结

┌───────────────────┬──────────┬───────────────────────────────────────────┐
│ 问题类型 │ 严重程度 │ 影响 │
├───────────────────┼──────────┼───────────────────────────────────────────┤
│ 假流式输出 │ 🔴 严重 │ 用户体验差，responses provider 完全不流式 │
├───────────────────┼──────────┼───────────────────────────────────────────┤
│ 流式解析不完整 │ 🔴 严重 │ tool_calls 无法正确处理，异常被吞 │
├───────────────────┼──────────┼───────────────────────────────────────────┤
│ done 事件重复内容 │ 🟡 中等 │ 逻辑混乱，前端可能重复显示 │
├───────────────────┼──────────┼───────────────────────────────────────────┤
│ 对话历史污染 │ 🔴 严重 │ 破坏 LLM 上下文，影响后续对话质量 │
├───────────────────┼──────────┼───────────────────────────────────────────┤
│ 并发控制缺失 │ 🟡 中等 │ 高并发场景下可能出现竞态条件 │
└───────────────────┴──────────┴───────────────────────────────────────────┘

---

✅ 建议修复方案（概要）

1. 移除假流式：responses provider 应该明确标记为非流式，或实现真正的流式代理
2. 完善流式解析：正确处理 tool_calls 的增量片段，记录 finish_reason
3. 分离 UI 和数据：工具调用提示不应混入 final_full_content，应该单独通过 WebSocket 事件发送
4. 修正 done 事件：不应该重复发送完整内容，前端应该自行拼接 delta
5. 增加并发控制：对同一 project_id + username 的请求进行排队处理

---

你是否需要我提供详细的修复代码？ 我可以逐个问题给出最小化的修复方案。
