# AI 员工工厂

基于 MCP（Model Context Protocol）的 AI-Native 开发平台。用户可自由组合 Skills + Rules + Memory + Persona 创建多个 AI 员工，通过进化引擎实现"越用越聪明"。

## 技术栈

- **前端**: Vue 3 + Element Plus + Vite
- **后端**: Python FastAPI + FastMCP 3.0+
- **存储**: JSON 文件 + SQLite（Memory）
- **认证**: JWT HS256

## 快速启动

### 后端

```bash
cd web-admin/api
pip install -e .
python init_admin.py  # 初始化管理员账户
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
