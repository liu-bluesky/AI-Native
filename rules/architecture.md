# 架构约束与数据流规则

> 跨层/跨服务变更时的强制参考。

## 六层架构

```
┌─────────────────────────────────┐
│  用户界面层  (Vue 3 SPA)         │  ← 只与 API 网关通信
├─────────────────────────────────┤
│  API 网关层  (FastAPI)           │  ← 聚合全部 Store，JWT 鉴权
├─────────────────────────────────┤
│  MCP 服务层  (6 × FastMCP)      │  ← 独立进程，各自 Store
├─────────────────────────────────┤
│  数据存储层  (JSON / SQLite)     │  ← 每服务独占数据目录
├─────────────────────────────────┤
│  进化引擎层  (mcp-evolution)     │  ← 消费使用日志，产出候选规则
├─────────────────────────────────┤
│  同步层      (mcp-sync)         │  ← 推送变更到 AI 员工
└─────────────────────────────────┘
```

## 层间通信规则

| 调用方 → 被调用方 | 协议 | 约束 |
|-------------------|------|------|
| 前端 → API 网关 | HTTP + JWT Bearer | 所有请求经 axios 拦截器附加 token |
| API 网关 → Store | 直接 Python import | 网关是唯一允许跨服务 import 的层 |
| MCP 服务 → Store | 同进程调用 | 每个服务只访问自己的 Store |
| 进化引擎 → 使用日志 | UsageLogStore | 只读消费，不修改原始日志 |
| 同步层 → AI 员工 | SyncEvent 推送 | 异步通知，不阻塞调用方 |

## 数据流

### 查询流

```
用户操作 → 前端 axios → /api/{domain}/* → Store.get/list → JSON/SQLite → 响应
```

### 反馈流

```
用户行为(采纳/拒绝) → record_feedback → UsageLog → 进化引擎分析 → 候选规则
```

### 同步流

```
规则/记忆变更 → push_update → SyncEvent → AI 员工热更新
```

## 安全边界

### 认证

- JWT HS256，8 小时过期
- Secret 从 `JWT_SECRET` 环境变量读取，禁止硬编码
- 公开路由仅限：`/api/init/status`、`/api/init/setup`、`/api/auth/login`
- 其余路由必须 `Depends(require_auth)`

### 数据隔离

- 每个 MCP 服务独占 `knowledge/` 目录，禁止跨服务读写
- Memory 服务支持 4 级分类：public / internal / confidential / restricted
- 记忆作用域隔离：employee-private / team-shared / global-verified

### 进化引擎安全

- 高风险规则（`risk_domain: high`）禁止自动晋升
- 每日自动晋升上限 5 条
- 所有自动进化支持 `dry_run` 预览模式
- 人设训练（`train_persona_from_corpus`）需要 `consent_token` 授权

### CORS

当前开发阶段 `allow_origins=["*"]`，生产环境必须收窄为具体域名。

## 扩展约束

### 新增 MCP 服务

1. 在 `mcp-{name}/` 下创建标准目录结构
2. 在 `web-admin/api/stores.py` 添加 `_load_store` 调用和 store 实例导出
3. 在 `web-admin/api/routers/` 下新建对应路由文件
4. 在 `server.py` 注册新 router
5. 在 `PROJECT.md` MCP 服务矩阵注册
6. 在 `rules/mcp-service.md` 服务名表注册

### 新增前端页面

1. 在 `views/{domain}/` 下创建 `XxxYyy.vue`（PascalCase）
2. 在 `router/index.js` 的 Layout children 中注册路由
3. 如需侧边栏入口，在 `Layout.vue` 的 `el-menu` 中添加菜单项
4. 遵循 `rules/frontend.md` 和 `rules/ui-design.md`

### 新增 API 端点

1. 在 `web-admin/api/routers/` 对应域文件中添加路由
2. 受保护路由通过 Router 级 `dependencies=[Depends(require_auth)]` 自动鉴权
3. 请求体用 `models/requests.py` 中的 Pydantic BaseModel
4. 列表响应包裹在具名字段中
