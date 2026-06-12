# MCP 提示词更新与打包部署通知工具可行性计划

生成时间：2026-06-12

## 背景

本次调研对象是当前系统里 AI 对话接入 MCP 后，是否可以继续新增两个面向客户端项目/统一 MCP 接入的工具：

1. 在客户端项目根目录告诉 AI“更新提示词”后，AI 通过 MCP 获取服务器上对应项目的 CLI 引导提示词，内容与“统一 MCP 接入”弹窗里的“展开引导提示词预览”一致，并覆盖当前项目的本地提示词文件。
2. 客户端项目完成打包后，通过 MCP 把产物文件推送到服务端；服务端检测到完整新产物后自动发起部署，部署结束后通过飞书、微信、QQ 机器人通知对应群。

结论：两个需求都可行。第一个需求围绕 `/api/projects/query-mcp/runtime` 返回的 `runtime.cli_prompt` 做服务器读取和本地文件覆盖。第二个需求围绕“产物推送 + 服务端自动部署”设计：MCP 负责把产物和清单推送到服务端，服务端以产物完整性校验通过作为触发点自动部署；FTP/SFTP/SCP 只是服务端部署阶段可选的远端传输协议。

## 本次修正口径

用户确认的“要获取/更新的提示词”是前端统一 MCP 接入弹窗里点击“展开引导提示词预览”后看到的那段引导提示词。客户端项目根目录里的“更新提示词”动作，应把这段服务器渲染结果拉回本地，并覆盖本地提示词文件。

准确对象：

- 前端组件：`web-admin/frontend/src/components/UnifiedMcpAccessDialog.vue`
- 前端文案：`展开引导提示词预览`
- 运行时接口：`GET /api/projects/query-mcp/runtime`
- 展示字段：`runtime.cli_prompt`
- 后端渲染函数：`_build_query_mcp_cli_prompt(...)`
- 模板来源：系统配置 `query_mcp_bootstrap_prompt_template`

## 现状依据

### MCP 入口与工具注册

当前 Web-Admin 后端已经支持动态 MCP：

- `/mcp/query`：统一查询 MCP，实现在 `web-admin/api/services/mcp/dynamic_mcp_apps_query.py`。
- `/mcp/projects/{project_id}`：项目 MCP，实现在 `web-admin/api/services/mcp/dynamic_mcp_apps_project.py`。
- `/mcp/employees/{employee_id}`、`/mcp/skills/{skill_id}`、`/mcp/rules/{rule_id}`：员工、技能、规则 MCP。
- 外部 MCP 工具可通过系统配置暴露给项目，相关实现在 `dynamic_mcp_external_tools.py`。

项目 MCP 已有内置工具：

- `get_project_profile`
- `get_project_manual`
- `get_project_runtime_context`
- `list_project_proxy_tools`
- `list_external_mcp_tools`
- `invoke_external_mcp_tool`
- `invoke_project_skill_tool`
- `execute_project_collaboration`

因此新增项目级 MCP 工具不需要新建一套 MCP 服务，优先扩展 `create_project_mcp(...)`。

### 统一 MCP 引导提示词相关入口

“展开引导提示词预览”位于前端统一 MCP 接入弹窗：

- 前端位置：`web-admin/frontend/src/components/UnifiedMcpAccessDialog.vue`
- UI 文案：`展开引导提示词预览`
- 前端请求：`GET /api/projects/query-mcp/runtime`
- 前端展示字段：`runtime.cli_prompt`

后端生成链路：

- 路由：`web-admin/api/routers/projects.py` 的 `get_query_mcp_runtime`
- 生成函数：`_build_query_mcp_cli_prompt(...)`
- 模板来源：系统配置 `query_mcp_bootstrap_prompt_template`
- 模板配置页：`web-admin/frontend/src/views/system/SystemConfig.vue` 的 `CLI Bootstrap 提示词模板`
- 模板变量：`{{clarity_threshold}}`、`{{project_context_block}}`、`{{chat_session_block}}`

因此这个提示词不是每个项目独立存一份完整文本。它是：

```text
query_mcp_bootstrap_prompt_template 全局模板
+ 当前 project_id 渲染出的 project_context_block
+ 当前 chat_session_id 渲染出的 chat_session_block
+ clarity_threshold
= runtime.cli_prompt
```

所以第一需求应设计为“根据 `project_id/chat_session_id` 获取服务器渲染出的 `runtime.cli_prompt`，再由本地 AI/连接器覆盖当前项目根目录下的提示词文件”。

### 打包部署与机器人通知相关入口

当前已有能力：

- `project_host_run_command`：在项目工作区执行 shell 命令，适合构建、测试、打包、调用脚本。
- `project_host_terminal_*`：交互式 PTY 终端，适合处理登录、授权、持续输出。
- `remote-docker-deploy/remote_docker_deploy.py`：远程 Docker 发布编排器。
- `remote-docker-deploy/package_deploy_artifacts.sh`：本地构建并打包镜像或源码包。
- `remote-docker-deploy/upload_deploy_artifacts.sh`：通过 SCP/SSH 上传产物。
- `remote-docker-deploy/update_remote_stack.sh`：远端预检查、备份、加载镜像或构建、执行 `deploy.sh up`。
- 飞书机器人已经有事件接收、OpenAPI 回复、`lark-cli` 发送能力。
- 微信、QQ 当前更接近连接器配置骨架，未看到与飞书同等完整的实际发送实现。

因此第二个需求的最短路径是：

1. 客户端项目本地完成打包，生成产物和清单。
2. AI 通过 MCP 将产物文件和 manifest 推送到服务端。
3. 服务端校验文件完整性、版本号、checksum 和部署配置。
4. 服务端检测到完整新产物后自动创建部署运行记录并发起部署。
5. 部署成功或失败后调用通知适配器。
6. 飞书先完整支持；微信、QQ 先定义接口与配置，后续补齐平台发送实现。

## 需求一：MCP 拉取统一 MCP CLI 引导提示词并覆盖本地文件

### 建议工具

建议新增统一查询 MCP 只读工具，并定义本地覆盖流程：

```text
get_query_mcp_cli_prompt_preview
sync_query_mcp_cli_prompt_to_local_file
```

获取预览参数建议：

```json
{
  "project_id": "proj-xxx",
  "chat_session_id": "chat-session-xxx",
  "clarity_threshold": 3
}
```

本地同步参数建议：

```json
{
  "project_id": "proj-xxx",
  "chat_session_id": "chat-session-xxx",
  "workspace_path": "/path/to/client-project",
  "target_file": "AGENTS.md",
  "backup": true,
  "dry_run": false
}
```

返回建议：

```json
{
  "status": "preview | synced | dry_run | no_change | blocked",
  "project_id": "...",
  "chat_session_id": "...",
  "template_source": "system_config.query_mcp_bootstrap_prompt_template",
  "rendered_field": "runtime.cli_prompt",
  "rendered_cli_prompt": "...",
  "target_file": "AGENTS.md",
  "backup_file": "AGENTS.md.bak.20260612T000000",
  "content_hash": "...",
  "changed": true,
  "audit_id": "..."
}
```

### 落地方式

优先在统一查询 MCP 中增加只读预览工具，内部复用：

- `projects.py` 的 `_build_query_mcp_cli_prompt(...)`
- `system_config_store.get_global()`

本地覆盖由 AI 所在项目根目录执行：

1. 用户在项目根目录告诉 AI：“更新提示词”。
2. AI 识别当前项目的 `project_id` 和 `chat_session_id`。
3. AI 调用 MCP `get_query_mcp_cli_prompt_preview`。
4. MCP 返回与前端弹窗一致的 `runtime.cli_prompt`。
5. AI 在本地写入 `target_file`，默认先创建备份。
6. 写入后计算 hash，并提示本地文件已与服务器提示词一致。

需要注意：

- MCP 工具只负责返回服务器渲染结果，不直接写客户端磁盘。
- 本地覆盖必须限制在当前项目根目录内，禁止写到项目外路径。
- 覆盖前建议生成备份；如果目标文件不存在，允许创建。
- 本地文件内容必须完整等于 `runtime.cli_prompt`，不要再拼接额外说明。
- 如果无法识别 `project_id`，应先让用户选择或从本地 `.ai-employee` 状态读取。

### 可行性

可行，复杂度中低。

核心原因：

- 预览接口 `/api/projects/query-mcp/runtime` 已经返回 `runtime.cli_prompt`。
- 后端已有 `_build_query_mcp_cli_prompt(...)` 负责按 `project_id/chat_session_id` 渲染。
- 本地 AI/连接器已经具备在项目根目录写文件的能力。
- 只需要补 MCP 预览工具、项目 ID 识别、本地路径安全校验、备份和 hash 校验。

## 需求二：MCP 打包部署并通知群

### 建议工具

新增项目 MCP 工具：

```text
push_project_deploy_artifact
get_project_deploy_upload_status
```

参数建议：

```json
{
  "profile": "prod",
  "artifact_name": "release-20260612.tar.gz",
  "artifact_kind": "docker-images | source-bundle | frontend-dist",
  "manifest": {
    "version": "2026.06.12.1",
    "checksum": "sha256:...",
    "size": 123456,
    "commit": "git-sha",
    "build_summary": "发布说明或变更摘要"
  },
  "auto_deploy": true
}
```

说明：

- `profile` 必须来自当前项目保存的部署配置。
- MCP 参数只传产物元数据、部署档位和是否允许自动部署，不直接携带服务器地址、凭据、通知群等敏感配置。
- 服务器地址、传输协议、远端目录、执行命令、通知群、消息模板等都从项目详情页维护，并落到项目配置里。
- 文件可以小文件一次上传，也可以大文件分片上传；只有 manifest 校验通过后，服务端才把产物标记为 `ready`。

返回建议：

```json
{
  "status": "uploading | ready | deploy_queued | blocked | failed",
  "upload_id": "...",
  "deployment_id": "...",
  "project_id": "...",
  "profile": "prod",
  "artifact_ref": "...",
  "checksum_verified": true,
  "auto_deploy": true
}
```

### 推荐架构

新增后端服务：

```text
services/deploy/project_artifact_service.py
services/deploy/project_deploy_service.py
services/deploy/deploy_transport_service.py
services/notifications/bot_notification_service.py
```

### 项目表配置设计

部署配置建议作为项目配置的一部分保存。当前项目模型已经把项目基础信息集中在 `ProjectConfig`，后续可新增 `deploy_settings` 字段；如果底层是 JSON store，就随项目 JSON 保存；如果底层是数据库，就作为项目表的 JSON 字段保存。

建议结构：

```text
ProjectConfig
- deploy_settings
  - version
  - enabled
  - default_profile
  - profiles[]
    - id
    - name
    - environment
    - artifact_kind
    - package
      - workspace_path
      - build_command
      - artifact_paths[]
      - output_dir
    - transport
      - mode
      - host
      - port
      - username
      - remote_dir
      - credential_ref
    - remote_executor
      - mode
      - working_dir
      - pre_check_command
      - deploy_command
      - health_check_command
      - rollback_command
    - notify
      - enabled
      - targets[]
        - platform
        - connector_id
        - chat_id
        - message_template
    - safety
      - require_confirm
      - dry_run_default
      - auto_deploy_on_artifact_update
      - lock_key
      - log_redaction_enabled
    - enabled
```

设计原则：

- 项目配置保存“怎么部署”，部署运行记录保存“这次部署做了什么”。
- 项目表只保存 `credential_ref`，不保存明文密码、token、SSH 私钥内容。
- `profiles[]` 对应 `prod`、`staging`、`test` 等环境；MCP 工具按 `profile` 读取配置。
- `auto_deploy_on_artifact_update` 控制服务端检测到完整新产物后是否自动发起部署。
- `transport` 只负责上传产物，`remote_executor` 负责远端执行，二者分离。
- 通知群配置属于项目部署配置的一部分，执行时只引用配置，不由 MCP 参数临时拼接。
- 配置需要带 `version`，方便以后兼容从 `/Users/liulantian/Downloads/pm-config` 这类配置目录导入或迁移。

产物记录和部署运行记录单独保存：

```text
ProjectDeployArtifact
- id
- project_id
- profile
- artifact_name
- artifact_kind
- version
- checksum
- size
- storage_path
- status
- uploaded_by
- uploaded_at
- ready_at
- deployment_id
```

```text
ProjectDeployRun
- id
- project_id
- profile
- status
- requested_by
- chat_session_id
- task_tree_node_id
- stage
- dry_run
- config_version
- config_snapshot
- artifact_summary
- log_excerpt
- notify_result
- rollback_ref
- created_at
- updated_at
```

`ProjectDeployArtifact` 记录服务端收到的产物状态；`ProjectDeployRun` 记录自动部署状态。`config_snapshot` 只能保存脱敏后的关键配置摘要，用于审计和回放；凭据仍然只保留引用。

### 项目详情前端配置

在 `web-admin/frontend/src/views/projects/ProjectDetail.vue` 的项目详情页增加“部署配置”区块，建议放在项目工作区页签中，或作为独立 tab：

```text
项目详情
- 项目概览
- UI 规则绑定
- 经验规则
- 代码仓库
- 部署配置
```

前端配置能力：

- 选择默认部署档位：`prod`、`staging`、`test`。
- 新增、编辑、复制、禁用部署档位。
- 配置打包命令、产物类型、产物路径和输出目录。
- 配置上传方式：`scp/sftp/ftp/ftps/registry`。
- 配置服务器地址、端口、远端目录、工作目录和凭据引用。
- 配置远端执行命令：预检查、部署、健康检查、回滚。
- 配置通知目标：飞书、微信、QQ 的连接器、群 ID 和消息模板。
- 配置产物更新策略：上传完成后自动部署 / 只入库不部署 / 需要人工确认。
- 提供“校验配置”“保存配置”两个基础动作。
- 支持从 `pm-config` 风格配置文件导入，并在保存前转换为标准 `deploy_settings`。

后端接口建议：

```text
GET /api/projects/{project_id}
PUT /api/projects/{project_id}
POST /api/projects/{project_id}/deploy-settings/validate
POST /api/projects/{project_id}/deploy-settings/import
POST /api/projects/{project_id}/deploy-artifacts
POST /api/projects/{project_id}/deploy-artifacts/{artifact_id}/complete
GET /api/projects/{project_id}/deploy-artifacts/{artifact_id}
```

其中 `PUT /api/projects/{project_id}` 可先承载 `deploy_settings` 保存；后续如果表单复杂度增加，再拆成独立 deploy-settings 接口。

### 执行链路

第一阶段建议按“产物推送后自动部署”闭环：

1. 客户端项目本地执行打包，生成产物文件和 manifest。
2. AI 调用 MCP `push_project_deploy_artifact`，把产物推送到服务端 artifact inbox。
3. 服务端写入 `ProjectDeployArtifact`，状态为 `uploading`。
4. 文件上传完成后，服务端校验 checksum、size、version、profile。
5. 校验通过后，服务端把产物标记为 `ready`。
6. 服务端检测到 `ready` 新产物，读取项目 `deploy_settings`。
7. 如果配置允许自动部署，服务端创建 `ProjectDeployRun` 并进入 `queued`。
8. 服务端使用配置里的 `transport` 和 `remote_executor` 上传到目标服务器并执行部署。
9. 部署结果写回 `ProjectDeployRun`，并调用通知适配器。
10. AI 可调用 `get_project_deploy_upload_status` 查询上传与自动部署状态。

第二阶段再抽象远端传输协议：

- `scp`/`ssh`：继续走现有 `remote-docker-deploy`。
- `sftp`：可以作为安全文件传输方式。
- `ftp`/`ftps`：只负责上传产物，不能替代远端执行；仍需要 SSH、Webhook、远端 Agent 或服务器侧部署 API 执行部署。

### 通知适配器

第一版：

- 飞书：复用现有 OpenAPI / `lark-cli im +messages-send` 能力。
- 微信、QQ：先落连接器配置、参数校验和统一接口，若没有实际发送 API，返回 `unsupported`，不伪装成功。

建议接口：

```text
send_deploy_notification(platform, connector_id, target, message, metadata)
```

通知内容至少包含：

- 项目名与部署目标。
- 提交或构建摘要。
- 部署状态。
- 产物类型。
- 远端目录。
- 耗时。
- 回滚引用。
- 日志摘要和查看链接。

### 安全与权限

部署工具必须按高风险操作处理：

- 是否自动部署由项目配置控制；开启自动部署前必须在项目详情页显式配置并保存。
- 不允许 MCP 参数直接传明文服务器密码。
- 远端凭据只能用 `credential_ref` 或系统密钥服务读取。
- 日志输出必须脱敏：密码、token、cookie、Authorization、SSH 私钥路径等不能回传给模型或群。
- 部署过程必须有锁，避免同一目标并发发布。
- 上传后远端执行失败要返回明确失败阶段，不允许只报“部署失败”。
- 必须保留回滚信息。
- 群通知属于外部写入，必须单独纳入权限策略。

## 具体实施计划

### 阶段 1：统一 MCP CLI 引导提示词本地同步

目标：先让 AI 能在客户端项目根目录按 `project_id/chat_session_id` 获取“展开引导提示词预览”的真实 `runtime.cli_prompt`，并覆盖当前项目本地提示词文件。

改动：

- 在统一查询 MCP 增加 `get_query_mcp_cli_prompt_preview`。
- 复用 `_build_query_mcp_cli_prompt(...)` 渲染预览。
- 增加本地同步流程 `sync_query_mcp_cli_prompt_to_local_file`。
- 本地覆盖前做项目根目录校验、备份、hash 比对。
- 返回 `rendered_cli_prompt`、`target_file`、`backup_file`、`content_hash`。
- 补测试覆盖：
  - 根据 `project_id` 生成包含默认项目上下文的 `runtime.cli_prompt`。
  - 根据 `chat_session_id` 生成会话上下文。
  - 本地目标路径必须位于项目根目录内。
  - `dry_run` 不写文件。
  - 覆盖前生成备份。

验收：

- MCP `tools/list` 可看到预览工具。
- 调用预览工具返回值与前端“展开引导提示词预览”一致。
- 用户在项目根目录说“更新提示词”后，本地目标文件被服务器返回的 `runtime.cli_prompt` 覆盖。
- 覆盖后 hash 与 MCP 返回内容一致。

### 阶段 2：项目部署配置、产物记录与运行记录

目标：把部署配置写入项目配置，并把 MCP 推送的产物状态和自动部署运行状态纳入服务端管理。

改动：

- `ProjectConfig` 增加 `deploy_settings`。
- `ProjectCreateReq` / `ProjectUpdateReq` 增加 `deploy_settings`。
- 项目读取、保存、手册和运行时上下文输出部署配置摘要，敏感字段脱敏。
- 新增部署产物记录 store，用于保存 MCP 推送后的产物状态。
- 新增部署运行记录 store，只保存执行记录，不重复保存可编辑配置。
- 新增 HTTP 校验接口，用于校验项目部署配置。
- 增加运行状态机：`queued/running/success/failed/blocked/cancelled`。
- 增加产物状态机：`uploading/ready/deploy_queued/deployed/failed/blocked`。
- 增加部署日志脱敏工具。

验收：

- 项目详情保存 `deploy_settings` 后，刷新页面仍能回显。
- 可以创建 `prod` 部署档位。
- MCP 推送产物后可以创建 `ProjectDeployArtifact`。
- 产物校验通过后可以自动创建 `ProjectDeployRun`。
- 状态流转和日志脱敏通过单测。

### 阶段 2.5：项目详情部署配置页面

目标：让用户在项目详情前端页面维护部署配置。

改动：

- 在 `ProjectDetail.vue` 增加“部署配置”区块或 tab。
- 增加部署档位列表，支持新增、编辑、复制、禁用。
- 表单覆盖打包、传输、远端执行、通知、安全确认。
- 增加配置校验按钮。
- 增加产物更新策略开关：上传完成后自动部署 / 只保存产物 / 需要人工确认。
- 支持导入 `pm-config` 风格配置文件，并转换为 `deploy_settings`。

验收：

- 用户能在项目详情创建并保存至少一个 `prod` 配置。
- 保存后 `GET /api/projects/{project_id}` 返回脱敏后的部署配置。
- 配置页能显示产物上传后是否自动部署。
- 未配置凭据引用、远端目录或通知目标时，前端能给出字段级错误。

### 阶段 3：MCP 产物推送与自动部署触发

目标：通过 MCP 推送产物，并由服务端检测完整新产物后自动部署。

改动：

- 在项目 MCP 增加 `push_project_deploy_artifact`。
- 在项目 MCP 增加 `get_project_deploy_upload_status`。
- MCP 推送产物文件、manifest 和 checksum。
- 服务端按 `project_id + profile` 读取项目配置里的 `deploy_settings`。
- 服务端检测到 `ready` 新产物后自动创建部署任务。
- 输出结构化阶段结果。

验收：

- 上传中文件状态为 `uploading`。
- checksum 校验通过后状态变为 `ready`。
- 配置允许自动部署时，服务端自动创建 `ProjectDeployRun`。
- 缺少凭据、部署配置或远端执行配置时返回 `blocked`，不静默失败。

### 阶段 4：机器人通知服务

目标：部署结果能通知指定群。

改动：

- 新增统一通知服务。
- 飞书先接入真实发送。
- 微信、QQ 若仅有配置未有发送实现，明确返回 `unsupported`。
- 通知结果写回部署运行记录。

验收：

- 飞书消息预览可生成。
- 飞书真实发送成功后返回消息 ID 或成功状态。
- 微信/QQ 未实现时返回明确 unsupported，不影响部署主结果。

### 阶段 5：远端传输协议抽象

目标：满足不同服务器接收产物的传输环境。

改动：

- 新增 transport 抽象：`scp/sftp/ftp/ftps`。
- 对 FTP/FTPS 只实现上传，不负责远端命令执行。
- 如果目标需要部署执行，必须配置 SSH、远端 Webhook 或远端 Agent。

验收：

- SFTP 上传可替代 SCP 上传阶段。
- FTP/FTPS 传输后若无执行通道，工具返回 `blocked: missing remote executor`。
- 所有传输配置均不暴露明文凭据。

## 推荐优先级

1. 先做 `get_query_mcp_cli_prompt_preview`，它是只读工具，收益高、风险低。
2. 再做本地同步覆盖流程 `sync_query_mcp_cli_prompt_to_local_file`。
3. 再做项目表 `deploy_settings` 和项目详情“部署配置”页面，先不碰真实发布。
4. 做部署产物记录、上传完成校验和状态查询。
5. 做服务端检测 `ready` 产物后自动创建部署运行记录。
6. 打通飞书通知。
7. 最后补 SFTP/FTP/FTPS 和微信/QQ 真实发送。

## 主要风险

- 当前任务树生成对本类 MCP 治理需求仍会产生不匹配节点，需要单独修复，否则 MCP 工具执行记录和用户目标可能显示不一致。
- 工具命名必须直接指向 `cli_prompt` / `local_file_sync`，避免泛称导致接入方选错流程。
- 真实部署、群通知、凭据读取都属于高风险能力，开启对应配置时必须显式确认并留审计；产物变为 `ready` 后，服务端按已保存配置自动发起部署，不再要求 AI 或用户手动触发。
- 部署配置进入项目表后，接口返回必须脱敏，否则项目详情页可能暴露凭据信息。
- 配置导入必须做字段映射和 schema 校验，不能把外部配置文件原样作为不可解释的大块文本保存。
- 自动部署必须以 manifest 完整、checksum 通过和配置允许为前提，不能在文件上传未完成时触发。
- 同一项目同一部署档位必须有部署锁，避免连续上传产物触发并发部署。
- 纯 FTP 只能上传文件，不能完成远端部署；必须配合 SSH、远端 Agent 或服务端部署 API。
- 微信/QQ 目前未看到与飞书同等完整的发送实现，不能在第一版承诺真实通知成功。
- 现有远程发布脚本存在本地凭据读取能力，后续接入 MCP 时必须收敛到 `credential_ref`，避免把明文凭据暴露给模型、日志或群消息。

## 最小可交付范围

第一期建议交付：

- `get_query_mcp_cli_prompt_preview`
- `sync_query_mcp_cli_prompt_to_local_file`
- `push_project_deploy_artifact`
- `get_project_deploy_upload_status`
- `ProjectConfig.deploy_settings`
- `ProjectDeployArtifact` 记录
- 项目详情“部署配置”区块
- `ProjectDeployRun` 记录
- 飞书消息预览
- 单元测试和一份操作说明

第一期不做：

- 真实 FTP 部署。
- 微信/QQ 真实消息发送。
- 未在项目详情页显式开启配置的生产自动部署。
- 在群里展示完整构建日志或敏感配置。
