# AI 员工工厂

基于 MCP（Model Context Protocol）的 AI-Native 开发平台。用户可自由组合 Skills、Rules、Memory、Persona 创建多个 AI 员工，并通过进化引擎持续优化能力。

## 技术栈

- 前端：Vue 3 + Element Plus + Vite
- 后端：FastAPI + FastMCP
- 存储：PostgreSQL / JSON / SQLite（按模块切换）
- 认证：JWT HS256

## 后端数据库配置

后端数据库配置现在分成两个清晰入口：

- 本地直跑后端：`web-admin/api/.env`
- Docker 编排：`docker/.env`

推荐规则：

- 应用内部优先使用 `DATABASE_URL`
- `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME` 只作为兼容回退
- 真实环境变量优先级高于 `.env` 文件
- 本地 API 会自动读取 `web-admin/api/.env` 和 `web-admin/api/.env.local`

### 1. 本地直跑后端

先准备配置文件：

```bash
cp web-admin/api/.env.example web-admin/api/.env
```

默认示例使用本机 PostgreSQL：

```env
DATABASE_URL=postgresql://admin:changeme@127.0.0.1:5432/ai_employee
CORE_STORE_BACKEND=postgres
USAGE_STORE_BACKEND=postgres
```

初始化并启动：

```bash
cd web-admin/api
pip install -e .
python init_admin.py
python server.py
```

如需走外部 Agent Runner，可在 `web-admin/api/.env` 里追加：

```env
EXTERNAL_AGENT_RUNNER_URL=http://127.0.0.1:3931
```

说明：

- 这不是外部 Agent 的必填配置。大多数本机开发场景下，如果 `codex` / `claude` / `gemini` 这类 CLI 已经安装好且命令能直接在当前机器执行，就不需要配置它。
- 不配置时，`web-admin/api` 会直接在当前运行环境里拉起外部 Agent CLI，这属于“本地执行”模式。
- 配置后，`web-admin/api` 不再自己直接执行 CLI，而是把执行请求转发给一个单独的 Runner 服务，这属于“Runner 托管”模式。

什么情况下才需要配：

- `web-admin/api` 跑在 Docker 容器里，但外部 Agent CLI 装在宿主机（你的真实电脑系统）上，没有装进容器里。
- 你希望把外部 Agent 的执行能力单独托管出去，便于多人共用同一台执行机器。
- 你需要更稳定的宿主机级能力，例如工作区探测、流式执行、PTY 终端镜像等。

“宿主机 / 容器分离”是什么意思：

- 宿主机：你的真实电脑系统，例如 macOS。
- 容器：Docker 里的隔离运行环境。
- 如果 API 在容器里，而 `codex` 命令只装在宿主机里，那么容器里的 API 通常看不到这个命令；这时就需要通过 `EXTERNAL_AGENT_RUNNER_URL` 把执行请求转发到宿主机上的 Runner。

可以这样理解：

- 不配 `EXTERNAL_AGENT_RUNNER_URL`：API 自己执行外部 Agent CLI。
- 配了 `EXTERNAL_AGENT_RUNNER_URL`：API 把执行请求交给 Runner 服务。

建议：

- 个人本机直接开发：通常不需要配置。
- Docker 跑 API、CLI 不在同一环境、或准备做多人共享：再配置。

### 2. Docker 启动整套服务

先准备 Docker 配置：

```bash
cp docker/.env.example docker/.env
```

`docker/.env` 只负责 Compose 级别的数据库参数和存储后端，例如：

```env
DB_USER=admin
DB_PASSWORD=changeme
DB_NAME=ai_employee
DB_PORT=5432
CORE_STORE_BACKEND=postgres
USAGE_STORE_BACKEND=postgres
```

启动：

```bash
cd docker
docker compose up -d --build
```

访问地址：

- 前端：`http://localhost:3000`
- API：`http://localhost:8000`

## 常用启动方式

### 本地开发

```bash
cd web-admin/frontend
npm install
npm run dev
```

前端开发服务器默认走代理，接口指向后端 `8000`。

### 生产方式启动 API

```bash
cd web-admin/api
uvicorn server:app --host 0.0.0.0 --port 8000
```

## 项目结构

```text
ai设计规范/
├── docs/
├── rules/
├── agents/
├── mcp-skills/
├── mcp-rules/
├── mcp-memory/
├── mcp-persona/
├── mcp-evolution/
├── mcp-sync/
├── docker/
└── web-admin/
    ├── api/
    └── frontend/
```

## 文档

- [项目总览](docs/00-项目总览/PROJECT.md)
- [Docker 使用说明](docker/README.md)
- [编码规范](rules/)

## License

MIT
