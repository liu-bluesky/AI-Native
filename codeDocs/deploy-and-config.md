# 部署、配置与规则体系

---

## 一、Docker 部署体系 (`docker/`)

### 1.1 环境分层

项目支持三套独立的 Docker 环境，通过不同的 compose 文件和 env 文件区分：

| 环境 | Compose 文件 | Env 文件 | 特点 |
|---|---|---|---|
| **开发** | `docker-compose.yml` | `.env` | hot-reload、调试端口、本地卷挂载 |
| **测试** | `docker-compose.test.yml` | `.env.test` | CI/CD 集成、自动化测试 |
| **生产** | `compose.prod.yml` | `.env.prod` | 优化镜像、资源限制、健康检查 |

基础服务（PostgreSQL + Redis）通过 `docker-compose.yml` 中的 base 编排独立管理。

### 1.2 核心文件

| 文件 | 说明 |
|---|---|
| `Dockerfile.api` | **API 镜像构建**。基于 Python 3.10+，安装 uv、复制代码、安装依赖、启动 Uvicorn |
| `Dockerfile.frontend` | **前端镜像构建**。基于 Node 构建 + Nginx 运行，分两阶段：build 阶段用 Vite 打包，运行阶段用 Nginx 提供静态文件 |
| `nginx.conf` | **Nginx 配置**。处理 SPA 路由（`try_files`）、API 反向代理到后端、静态资源缓存策略 |
| `docker-compose.yml` | **开发编排**。启动 db (PostgreSQL)、redis、api (FastAPI)、frontend (Nginx+Vue) 四个服务 |
| `compose.prod.yml` | **生产编排**。增加资源限制、健康检查、日志驱动、重启策略 |
| `docker-compose.test.yml` | **测试编排**。挂载测试代码、设置测试环境变量 |

### 1.3 部署脚本

| 文件 | 说明 |
|---|---|
| `deploy.sh` | **Linux/Mac 部署脚本**。构建镜像 → 启动服务 → 健康检查 → 输出访问地址 |
| `deploy.ps1` | **Windows PowerShell 部署脚本**。功能同 `deploy.sh` |
| `build-publish-images.sh` | **构建并发布镜像**。构建 Docker 镜像并推送到镜像仓库 |

### 1.4 辅助目录

| 目录/文件 | 说明 |
|---|---|
| `init/` | 初始化脚本。包含 `001_usage_schema.sql` — 使用记录表结构 |
| `backup/` | 备份目录。包含数据库备份 `ai_employee.sql`、MCP 知识库快照 `local-sync-*.tar.gz` |
| `dist/` | 构建产物。`ai_employee-api_latest.tar`、`ai_employee-frontend_latest.tar` 等镜像归档 |
| `.ace-tool/index.json` | ACE 工具配置 |

### 1.5 README 文档

| 文件 | 说明 |
|---|---|
| `README.md` | Docker 部署总览 |
| `README.quick.md` | 快速开始指南 |
| `README.deploy-test.md` | 测试环境部署指导 |
| `README.publish.md` | 生产发布流程 |
| `README.migration.md` | 数据迁移指南 |
| `README.test-docker.md` | Docker 测试说明 |
| `README.learn.md` | 学习资源 |
| `README.zhihu.md` | 知乎相关 |
| `PUBLISH-CHECKLIST.md` | 发布检查清单 |
| `部署.md` | 中文部署说明 |

---

## 二、远程部署工具 (`remote-docker-deploy/`)

### 文件说明

| 文件 | 说明 |
|---|---|
| `deploy.sh` | 主部署脚本。SSH 连接远程主机 → 上传文件 → 启动 Docker Compose |
| `Dockerfile` | 应用镜像定义 |
| `docker-compose.yml` | 远程部署的编排配置 |
| `.env.example` | 远程环境变量模板 |
| `*.py` | Python 辅助脚本（健康检查、状态监控等） |

---

## 三、AI 规则体系 (`rules/`)

### 规则文件

| 文件 | 说明 |
|---|---|
| `coding-standards.md` | **编码规范**。变量命名、函数长度、注释风格、代码组织等约定 |
| `architecture-rules.md` | **架构约束**。模块依赖方向、分层规范、API 设计原则 |
| `api-design.md` | **API 设计规范**。RESTful 约定、错误码体系、分页规范 |
| `testing.md` | **测试规范**。单元测试覆盖率要求、集成测试策略、E2E 测试范围 |
| `git-workflow.md` | **Git 工作流规范**。分支策略、commit 格式、PR 流程 |

### 设计意图

`rules/` 目录是"AI 可消费的编码规则"。这些 Markdown 文件会被 MCP 规则服务读取并注入到 AI Agent 的上下文中，确保 AI 在生成代码时遵循项目约定。配合 `mcp-rules/` 中的 `evolve_rule` 和 `record_feedback` 能力，规则可以持续进化和优化。

---

## 四、智能体定义 (`agents/`)

| 文件 | 说明 |
|---|---|
| `developer.md` | **开发者智能体**。负责编码实现，使用 skills/rules/memory 等能力 |
| `reviewer.md` | **代码审查智能体**。检查代码质量、规范遵循、安全隐患 |
| `tester.md` | **测试智能体**。编写和执行测试用例 |
| `architect.md` | **架构师智能体**。系统设计、技术选型、模块划分 |

每个智能体文件定义了该角色的：
- 职责范围
- 可用技能组合
- 行为规则和约束
- 与其他智能体的协作方式

---

## 五、项目文档体系 (`docs/`)

### 文档目录结构

```
docs/
├── README.md                           # 文档总览
├── 开发经验.md                         # 开发经验总结
├── 总结文档.md                         # 项目总结
│
├── 00-项目总览/
│   └── PROJECT.md                      # 项目全景介绍
│
├── 10-平台架构设计/
│   └── AI-Native开发平台设计规范.md    # 核心架构设计文档
│
├── 20-产品应用设计/
│   ├── AI-员工工厂设计规范.md          # 产品设计规范
│   ├── 官网介绍页面方案.md             # 官网方案
│   └── *.png                           # 设计配图
│
├── 30-专项功能方案/                    # 各功能模块的详细设计
│   ├── AI对话中心类macOS交互升级方案.md
│   ├── AI对话中心重构方案.md
│   ├── AI对话框计划驱动执行工作流升级计划.md
│   ├── AI智能体开发工作流重构方案.md
│   ├── ClaudeCLI可借鉴能力与MCP升级映射.md
│   ├── MCP优先下的Agent运行时补强方案.md
│   ├── MCP工作流三层稳定化方案.md
│   ├── 任务闭环执行与恢复状态机设计.md
│   ├── 前后端对标Claude重构计划.md
│   ├── 前后端重构开发基线与回归清单.md
│   ├── 功能分割设计.md
│   ├── 外部Agent托管模式设计.md
│   ├── 文件资产系统开发计划.md
│   ├── 统一查询MCP升级规划.md
│   ├── 统一查询MCP开发实施骨架.md
│   ├── 统一查询MCP联调示例.md
│   ├── 项目模块MCP化设计.md
│   ├── 项目模块MCP联调示例.md
│   ├── 项目类型与素材库方案.md
│   ├── 飞书机器人自动回复需求与测试用例.md
│   ├── 仿新境AI/                     # 参照产品分析
│   │   ├── prd.md
│   │   ├── materials-route-noise-reduction.md
│   │   ├── 短片制作功能梳理.md
│   │   └── 短片制作开发拆解.md
│   └── 文件资产系统/
│       ├── README.md
│       ├── 正式导出任务模型设计.md
│       ├── 短片导出与正式渲染方案.md
│       └── 阶段推进计划.md
│
├── 40-数据存储升级/
│   └── PostgreSQL升级规划.md
│
├── 反馈驱动规则升级模块/
│   ├── README.md
│   ├── PRD-反馈驱动规则升级模块.md
│   ├── 前后端设计与菜单功能.md
│   └── 需求文档清单.md
│
└── update/
    └── 统一查询MCP升级前后对比.md
```

### 文档分类

| 前缀 | 类别 | 说明 |
|---|---|---|
| `00-` | 项目总览 | 项目定位、整体架构 |
| `10-` | 架构设计 | 平台架构规范 |
| `20-` | 产品设计 | 产品功能和应用设计 |
| `30-` | 功能方案 | 各专项功能的详细设计 |
| `40-` | 数据升级 | 数据存储相关升级 |
| `反馈驱动` | 业务模块 | 反馈驱动规则升级模块的全套文档 |
| `update/` | 升级对比 | 版本升级的前后对比 |

---

## 六、飞书技能包 (`skills/` 目录，项目根)

项目根目录下的 `skills/` 包含 **22 个飞书（Lark）API 技能包**，通过 `lark-cli` 调用：

| 技能 | 说明 |
|---|---|
| `lark-approval` | 飞书审批 API：审批实例、审批任务管理 |
| `lark-attendance` | 飞书考勤打卡：查询自己的考勤打卡记录 |
| `lark-base` | 飞书多维表格（Base）：建表、字段管理、记录读写、视图配置 |
| `lark-calendar` | 飞书日历：日程管理、会议室预定、忙闲查询 |
| `lark-contact` | 飞书通讯录：查询组织架构、人员信息、搜索员工 |
| `lark-doc` | 飞书云文档：创建/编辑/搜索飞书文档 |
| `lark-drive` | 飞书云空间：文件和文件夹管理、权限管理 |
| `lark-event` | 飞书事件订阅：WebSocket 实时监听飞书事件 |
| `lark-im` | 飞书即时通讯：收发消息、管理群聊 |
| `lark-mail` | 飞书邮箱：起草/发送/回复/搜索邮件 |
| `lark-minutes` | 飞书妙记：查询和下载会议纪要 |
| `lark-okr` | 飞书 OKR：管理目标和关键结果 |
| `lark-openapi-explorer` | 飞书原生 OpenAPI 探索 |
| `lark-shared` | 飞书 CLI 共享基础：认证、权限管理 |
| `lark-sheets` | 飞书电子表格：创建和操作电子表格 |
| `lark-skill-maker` | 飞书自定义技能创建工具 |
| `lark-slides` | 飞书幻灯片：读取和管理 PPT |
| `lark-task` | 飞书任务：管理待办和清单 |
| `lark-vc` | 飞书视频会议：查询会议记录和纪要 |
| `lark-whiteboard` | 飞书画板：查询和编辑画板 |
| `lark-wiki` | 飞书知识库：管理知识空间 |
| `lark-workflow-meeting-summary` | 会议纪要汇总工作流 |
| `lark-workflow-standup-report` | 日程待办摘要 |

技能版本锁定在 `skills-lock.json` 中，确保团队使用一致的版本。

---

## 七、环境变量配置要点

### API 服务 (`.env`)

```bash
# 数据库
DATABASE_URL=postgresql://user:password@localhost:5432/ai_employee
# Redis
REDIS_URL=redis://localhost:6379/0
# JWT
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256
# 飞书
LARK_APP_ID=xxx
LARK_APP_SECRET=xxx
# 调试
DEBUG=false
```

### Docker (`.env` / `.env.prod`)

```bash
# 镜像标签
API_IMAGE_TAG=latest
FRONTEND_IMAGE_TAG=latest
# 端口映射
API_PORT=8000
FRONTEND_PORT=80
# 数据库密码
POSTGRES_PASSWORD=xxx
```
