# 取消服务端产物自动部署与后端 FTP 上传实施计划

## 1. 目标

将项目部署能力收敛为唯一主链路：**桌面端 Tauri 读取项目部署配置后，直接从用户机器上传到 FTP，并由后端记录部署结果及按配置触发远端命令、通知。**

本次计划删除以下能力：

1. 服务端保存部署产物后，由服务端自动上传 FTP 并执行部署。
2. MCP 将本地产物推送到服务端 artifact 模块后自动部署。
3. 对已有服务端 artifact 再次发起部署。
4. 后端进程直接连接 FTP、创建目录、备份和上传文件的执行逻辑。

## 2. 保留边界

以下能力继续保留：

- 桌面端部署工具读取 `deploy-options` 获取脱敏后的目标配置。
- `POST /api/projects/{project_id}/deploy/direct-prepare`：向桌面端返回本次允许使用的 FTP 目标参数。
- Tauri `deploy.rs` 中 `upload_source_to_ftp` 及相关 `curl` FTP 上传、目录上传、远端备份逻辑。
- `POST /api/projects/{project_id}/deploy/direct-complete`：接收桌面端上传结果、生成部署运行记录、按配置触发远端命令和通知。
- 全局 FTP 连接管理，以及项目部署设置中选择 FTP 连接、远端目录和部署命令的能力。
- 部署运行记录、通知记录和必要的审计信息。

## 3. 删除后的产品行为

### 3.1 桌面端部署

用户在桌面端请求部署时：

1. AI 读取部署档位和目标。
2. 用户确认目标及高风险操作。
3. Tauri 从本地工作区读取文件或目录。
4. Tauri 直接上传 FTP。
5. Tauri 调用 `direct-complete` 上报结果。
6. 后端仅记录运行状态、执行已配置的远端命令并发送通知。

### 3.2 MCP 和远程客户端

- 不再提供 `push_project_deploy_artifact`。
- 不再提供 `deploy_project_deploy_artifact`。
- 远程 MCP、浏览器端或没有桌面 Runner 的客户端不能上传部署产物，也不能部署已有服务端产物。
- 相关请求统一返回明确的 `desktop_runner_required` / `unsupported`，提示用户在桌面端执行直接部署。
- 不允许静默回退到服务端 FTP，不允许继续接收 base64 产物后假装部署成功。

### 3.3 历史 artifact

- 历史部署 artifact 和部署运行记录默认只读保留，避免升级时直接造成数据丢失。
- 页面不再提供“部署”“AI 部署”“重新部署”入口。
- 若产品确认不再需要历史 artifact 下载和审计，可在后续独立数据清理任务中删除；本次代码改造不自动删除历史文件或数据库记录。

## 4. 影响范围

### 4.1 后端部署路由

重点文件：`web-admin/api/routers/projects.py`

删除或下线：

- `ftplib` 导入和 `project_deploy_ftp_client_factory`。
- 服务端 FTP 连接、目录创建、备份、单文件上传、目录递归上传相关帮助函数。
- `_upload_project_deploy_artifact_to_ftp` 及其调用链。
- `_execute_project_deploy_run_for_artifact` 中服务端 FTP 执行分支。
- artifact AI 执行计划中与解压、文件操作、FTP 上传有关的动作和模型提示。
- `POST /{project_id}/deploy-artifacts/{artifact_id}/deploy`。
- 若仍存在 artifact AI execute 内部入口，一并删除或改为不可用，不保留隐蔽部署入口。
- artifact 上传接口中的 `auto_deploy` 行为，以及保存后创建部署任务的逻辑。

保留并回归：

- `deploy-options`。
- `deploy/direct-prepare`。
- `deploy/direct-complete`。
- 远端命令执行、部署通知和 deploy run 记录。

### 4.2 请求模型与部署存储

重点文件：

- `web-admin/api/models/requests.py`
- `web-admin/api/stores/json/project_deploy_store.py`
- 对应 PostgreSQL store 和迁移文件（如有）

处理项：

- 删除仅供 artifact 部署使用的请求模型，例如 artifact deploy 请求和 AI execute 请求。
- 从 artifact push/upload 请求中删除 `auto_deploy`。
- 保留历史 artifact 数据结构的只读兼容，避免旧数据反序列化失败。
- 新代码不再创建 `deploy_queued` 等仅用于服务端自动部署的状态。
- 评估 artifact 上传、查询、删除是否还有独立价值；若无价值，整个 artifact CRUD 模块一并下线。

## 5. MCP 能力清理

重点文件：

- `web-admin/api/services/mcp/dynamic_mcp_apps_query.py`
- `web-admin/api/services/mcp/dynamic_mcp_collaboration.py`
- MCP 工具定义、项目代理工具映射和相关测试

删除：

- `push_project_deploy_artifact` 工具定义、参数 schema、处理函数和路由代理。
- `deploy_project_deploy_artifact` 工具定义、参数 schema、处理函数和路由代理。
- `auto_deploy=true` 默认行为及相关说明。
- “本地 zip 先推送服务端 artifact，再由服务端自动部署”的所有工作流文案。

调整：

- 部署类任务只暴露 `get_project_deploy_options` 和桌面端直接部署工具。
- 非桌面 MCP 调用部署时明确返回能力缺失，而不是建议上传 artifact。
- 更新动态提示词，明确部署必须在可访问本地文件的桌面 Runner 中完成。

## 6. 桌面端与 Web 前端清理

### 6.1 Tauri 工具

重点文件：

- `web-admin/frontend/src-tauri/src/liuagent_core/tools/deploy.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/definitions.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/runtime.rs`

删除：

- 上传到 `/deploy-artifacts/upload` 的旧工具实现。
- `auto_deploy` 参数、artifact 上传 URL 和上传后部署请求。
- 仅用于服务端 artifact 上传的 multipart、结果摘要和测试。

保留：

- 桌面直接部署工具。
- `direct-prepare`、本地 FTP 上传、`direct-complete` 完整链路。
- 高风险操作授权、文件数量和大小限制。

### 6.2 项目部署设置页

重点文件：`web-admin/frontend/src/components/project-workspace/ProjectDeploySettingsPanel.vue`

删除：

- `auto_deploy_on_artifact_update` 开关。
- 与“上传 artifact 后自动部署”相关的说明、校验和默认值。

保留：

- 环境档位、组件、目标、FTP 连接、远端路径、部署命令和通知配置。

### 6.3 部署产物页面

- 移除 artifact 的“部署”“AI 部署”“重新部署”按钮和 API 调用。
- 若 artifact 模块整体下线，则同步移除项目详情入口、路由和权限点。
- 若暂时保留历史记录，则页面改为只读，并明确标记“历史服务端产物，不可部署”。

## 7. 技能包、提示词与文档同步

重点范围：

- `.ai-employee/skills/project-deploy-artifact/`
- `mcp-skills/knowledge/skill-packages/project-deploy-artifact/`
- `mcp-skills/knowledge/skills/` 中对应技能元数据
- `.ai-employee/skills/query-mcp-workflow/SKILL.md`
- Query MCP usage guide、Codex/Claude/Hermes 客户端画像生成模板
- 根目录 `AGENTS.md`、`CLAUDE.md`、`HERMES.md` 的服务端生成源
- `system.md`、`docs/哪些功能用什么ai.md` 等架构说明

处理方式：

1. 删除 `project-deploy-artifact` 技能，或将其重构为仅负责调用桌面直接部署工具；不能继续描述服务端 artifact 自动部署。
2. 删除 `push_local_artifact.py` 及 `--no-auto-deploy` 等参数。
3. 全局替换“客户端上传 artifact，服务端自动部署”为“桌面客户端直接上传 FTP，后端仅完成记录、命令与通知”。
4. 更新客户端能力边界：无桌面 Runner 时部署为 `blocked`，不再提供 MCP 远程上传替代方案。
5. 更新提示词回归测试，避免旧规则被重新渲染回 `AGENTS.md`。

## 8. 推荐实施顺序

### 阶段一：先建立新能力边界

1. 为桌面直接部署补充端到端测试。
2. 明确没有桌面 Runner 时的错误码和用户提示。
3. 确认远端命令和通知仍由 `direct-complete` 正常触发。

### 阶段二：关闭自动部署入口

1. 删除 Web 前端自动部署开关和部署按钮。
2. 删除 MCP 的两个 artifact 部署工具。
3. 删除 artifact push/upload 的 `auto_deploy` 参数和触发逻辑。
4. 删除已有 artifact 的部署 API。

### 阶段三：删除后端 FTP 执行实现

1. 删除 artifact 部署执行器及 AI 执行计划。
2. 删除后端 `ftplib` 上传、目录和备份函数。
3. 删除不再可达的模型、常量、状态和日志格式。
4. 用静态扫描确认后端不再存在 FTP 网络连接调用。

### 阶段四：清理 artifact 模块

1. 判断 artifact 是否保留为历史只读模块。
2. 若保留，收紧为上传记录/下载/删除，不允许部署。
3. 若不保留，删除 artifact CRUD、页面、存储和权限配置。
4. 数据库表删除必须另建迁移，并在确认历史数据无需保留后执行。

### 阶段五：同步工作流与文档

1. 修改 Query MCP 工具注册与提示词模板。
2. 修改本地及系统技能包。
3. 重新生成并同步各 CLI 入口提示词。
4. 更新架构文档和功能归属说明。

## 9. 测试计划

### 9.1 必须通过的正向测试

- 桌面端可读取部署档位和目标。
- 桌面端可上传单文件、压缩包和目录到 FTP。
- 桌面端上传失败时不会调用成功通知。
- `direct-complete` 可正确记录成功、失败和 blocked 状态。
- 配置远端命令时仍可在上传成功后执行。
- 通知开关为真时发送通知，为假时不发送。
- FTP 凭据不会出现在模型提示词、普通 API 响应或部署日志中。

### 9.2 必须通过的删除验证

- API 路由中不存在 artifact deploy 和 artifact AI execute 入口。
- MCP 工具列表中不存在 `push_project_deploy_artifact` 和 `deploy_project_deploy_artifact`。
- 后端代码中不存在 `ftplib.FTP`、`storbinary` 或等价 FTP 上传调用。
- 项目部署设置中不存在自动部署开关。
- Tauri 中不存在上传服务端 artifact 后再部署的旧链路。
- 提示词和技能中不存在“推送服务端 artifact 后自动部署”的有效指令。

### 9.3 回归测试

- 全局 FTP 连接 CRUD 和权限校验正常。
- 项目部署配置校验正常。
- 部署运行记录查询和通知重发正常。
- 非桌面客户端请求部署时返回明确、稳定且可测试的错误。
- 历史 artifact 数据存在时服务启动和页面读取不报错。

## 10. 风险与回滚

### 风险

- 删除 MCP artifact 工具后，远程 Codex/Claude 或纯浏览器会失去部署能力。
- 桌面端离线或 Runner 不可用时，没有服务端替代部署路径。
- 历史自动化脚本仍调用 artifact API 时会失败。
- 如果先删后端 FTP、但 MCP 与页面入口未同步删除，会形成运行时 404/500。
- 如果只改本地提示词而不改生成源，后续同步会恢复旧规则。

### 回滚策略

- 代码回滚以版本控制恢复，不保留双实现或隐藏开关。
- 第一阶段先关闭入口、保留历史数据；确认稳定后再删除存储结构。
- 数据库迁移采用后置策略，代码稳定一个发布周期后再决定是否删除 artifact 表。
- 不删除历史 FTP 连接和项目 target 配置，因为桌面直传仍依赖这些配置。

## 11. 完成定义

满足以下条件才算完成：

1. 生产代码中只有桌面端执行 FTP 数据传输。
2. 后端不再建立 FTP 连接，也不再保存新产物用于自动部署。
3. MCP 不再提供产物上传部署或已有产物部署工具。
4. Web 页面不再提供自动部署配置和服务端产物部署入口。
5. 桌面直接部署、远端命令、通知和运行记录通过回归测试。
6. 技能包、动态提示词、CLI 入口提示词和架构文档全部采用新边界。
7. 历史 artifact 的保留或清理策略已明确，且升级不会造成不可预期的数据丢失。

