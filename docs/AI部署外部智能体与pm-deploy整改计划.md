# AI 部署外部智能体与 pm-deploy 整改计划

生成时间：2026-06-16

## 背景

当前“部署产物 / AI 部署”链路已经暴露出两个核心问题：

1. 旧实现把 AI 部署做成了后端固定流程：项目 AI 回复一段策略后，后端继续调用固定部署函数执行 FTP 上传、备份、解压和状态回写。
2. `pm-deploy` 插件并不是真正的部署插件，只是根据少量上下文输出 `archive_policy`、`upload_mode` 等结构化计划，和系统真实部署配置不匹配。

用户期望的 AI 部署不是“后端代码按固定规则部署”，而是：

```text
用户部署要求
+ 当前服务端 artifact
+ 项目部署配置
+ 受控工具能力
-> 项目配置的外部智能体理解要求
-> 外部智能体调用部署工具或 CLI 插件
-> 工具执行并回写部署状态
```

这份计划用于收敛整改范围，避免继续把 `pm-deploy` 当成 AI 部署核心。

## 你要求的目标链路

用户确认的方向不是“后端固定部署”，而是下面这条链路：

```text
服务端提供部署所需信息
-> 项目配置的外部智能体理解部署要求
-> 外部智能体调用 pm / 部署 CLI
-> CLI 根据项目部署配置执行真实部署
-> 结果回写部署 run
```

这里的 `pm` 仅能作为外部智能体调用的执行工具或 CLI 入口，不能再承担“后端替 AI 做部署决策”的角色。

## 当前结论

`pm-deploy` 当前与系统部署配置不匹配。

它现在只做“计划生成”：

- 输入：部署上下文 JSON。
- 输出：`archive_policy`、`upload_mode`、`backup_policy`、`remote_command_policy`、`unsupported_requirements`。
- 不读取完整 `deploy_settings`。
- 不读取或下载 artifact。
- 不解压、不上传、不执行远端命令。
- 不回写部署运行记录。
- 不处理项目聊天外部智能体运行时。

系统真实部署配置包含：

- `deploy_settings.profiles`
- `components`
- `targets`
- `ftp_credential_id`
- `remote_path`
- `remote_command_mode`
- `deploy_command`
- artifact 存储路径、文件树、checksum、版本、状态
- 部署 run、备份路径、上传结果、失败日志、通知结果

因此当前 `pm-deploy` 不能作为“AI 部署插件”。继续保留它会造成误解：看起来像 AI 部署能力，实际只是一个简化规则判断器。

补一句当前事实：本轮已经把“AI 部署入口直接执行后端 FTP 流程”的旧链路拆掉了，但“`invalid artifact archive path` 的具体来源定位”“真正由外部智能体调用 `pm`/部署 CLI 执行”这两件事还没有在代码里完全闭环，不能把它说成已经彻底修好了。

## 已完成的临时止血

已经完成的方向性修正：

1. `deploy/ai-execute` 不再直接调用后端固定部署函数。
2. AI 部署入口要求项目聊天配置为 `chat_mode=external_agent`。
3. 后端返回 external agent handoff：包含部署上下文、工具列表、workspace 和 prompt。
4. 前端桌面端通过 Runner 启动外部智能体。
5. 非外部智能体模式、无桌面 Runner 或无 workspace 时明确阻塞。
6. 前端本地流程预览不再默认把 zip 判定为“解压后上传”，未明确要求时交给外部智能体判断。

这只是控制权止血，不代表最终架构完成。

## 目标架构

### 一句话目标

AI 部署入口只负责任务发起、上下文整理和能力注入；部署决策和工具调用由项目配置的外部智能体完成；服务端只提供受控能力，不再替智能体做固定策略判断。

### 正确链路

```text
1. 用户在部署产物里点击 AI 部署
2. 前端收集部署要求和流程参考
3. 后端校验项目聊天已选择外部智能体
4. 后端生成部署 handoff：
   - project_id
   - artifact_id
   - artifact metadata
   - deploy_settings 摘要
   - 可用工具
   - 安全边界
5. 桌面端 Runner 启动项目配置的外部智能体
6. 外部智能体理解用户要求
7. 外部智能体调用部署工具或 CLI 插件
8. 工具执行部署并回写部署 run
9. 前端展示部署产物和部署运行状态
```

### 安全边界

- 不把 FTP/SSH 密码原文交给大模型。
- 外部智能体只能拿到受控工具或短期能力句柄。
- 真实凭据解析由服务端或本机受控工具内部完成。
- 所有真实部署必须生成部署 run。
- 所有失败必须写入 run 的 `status/stage/log_excerpt/artifact_summary`。
- 用户说“只上传”时不能自动部署。
- 用户说“解压后部署”时不能原样上传压缩包。
- 用户说“不解压 / 原样上传”时不能解压。
- 用户要求不清楚时必须 blocked，不能猜成功。

## 整改范围

### 1. 下架或重命名当前 pm-deploy

当前 `pm-deploy` 不能继续以“部署插件”身份存在。

可选方案：

#### 方案 A：下架

移除：

- CLI 插件市场注册中的 `pm-deploy`
- `install_cli_plugin.sh` 对 `pm-deploy` 的安装分支
- `PROJECT_DEPLOY_AI_PLUGIN_ID = "pm-deploy"` 的 AI 部署依赖
- 相关测试里对 `pm-deploy` 的预期

适合短期避免误导。

#### 方案 B：重命名为 plan helper

保留但改名，例如：

```text
pm-deploy-plan
```

并明确说明：

- 只用于生成参考计划。
- 不执行部署。
- 不作为 AI 部署主链。
- 不允许自动决定 zip 默认解压。

适合后续保留辅助能力。

建议：先走方案 A 或 B，但必须从 AI 部署主链移除。

### 2. 设计真正的部署 CLI 插件

新增真正执行型插件，例如：

```text
project-deploy-cli
```

它必须匹配系统部署配置，而不是自己发明一套字段。

建议命令：

```bash
project-deploy-cli inspect --context -
project-deploy-cli deploy --context -
project-deploy-cli status --deployment-id <id>
```

输入上下文必须包含：

```json
{
  "project": {
    "id": "proj-xxx",
    "name": "项目名"
  },
  "artifact": {
    "id": "artifact-xxx",
    "name": "source-bundle.zip",
    "kind": "source-bundle",
    "checksum": "sha256:...",
    "storage_kind": "file|directory",
    "is_archive": true
  },
  "deploy_settings": {
    "profile": "test",
    "component": "testpc",
    "targets": [
      {
        "id": "server-1",
        "name": "服务器",
        "transport_mode": "ftp",
        "remote_path": "/xxx",
        "remote_command_mode": "none|ssh|project_host_command|local_connector",
        "has_deploy_command": false
      }
    ]
  },
  "user_requirement": "解压后部署",
  "ui_plan_reference": "流程参考文本",
  "chat_session_id": "chat-session-xxx"
}
```

插件输出必须包含：

```json
{
  "status": "success|failed|blocked",
  "deployment_id": "deploy-xxx",
  "stage": "ftp_upload_completed",
  "strategy": {
    "archive_policy": "extract_before_upload|upload_archive|auto",
    "upload_mode": "directory|file",
    "backup_policy": "backup_before_upload"
  },
  "summary": "部署摘要",
  "error": "",
  "evidence": {
    "backup_paths": [],
    "uploaded_files": 0,
    "remote_paths": []
  }
}
```

这个插件才是你说的“外部智能体拿到服务端提供的信息后，自己调用 `pm` 去部署”的承载点。不是 `pm-deploy` 这种只出计划、不做执行的轻量插件。

### 3. 提供受控部署能力，不暴露密码

外部智能体需要能部署，但不能直接拿明文密码。

建议拆成两类工具：

#### artifact 能力

- `get_deploy_artifact_metadata`
- `download_deploy_artifact`
- `materialize_deploy_artifact`
- `inspect_deploy_artifact_archive`

能力要求：

- 能拿到 artifact 内容或临时本地路径。
- 能列出 zip/tar 内部 entry。
- 能在失败时指出具体非法 entry，例如 `../index.html`。

#### transport 能力

- `prepare_deploy_target`
- `backup_remote_target`
- `upload_deploy_files`
- `run_remote_deploy_command`
- `complete_deploy_run`
- `fail_deploy_run`

能力要求：

- 工具内部使用系统保存的 `ftp_credential_id`。
- 不把密码传给模型。
- 每个工具调用都写入部署 run 事件。
- 任一失败都必须回写可见错误。

### 4. 修复 artifact 解包诊断

当前 `invalid artifact archive path` 信息太粗，用户无法定位哪个路径非法。

整改：

- 解包校验失败时记录具体 entry 名称。
- 错误信息改为：

```text
invalid artifact archive path: ../index.html
```

或：

```text
invalid artifact archive path: /Users/name/project/index.html
```

前端部署日志展示：

- artifact 名称
- deployment id
- stage
- 非法 entry
- 建议重新打包方式

验收：

- 构造含 `../index.html` 的 zip，部署 run 显示具体非法路径。
- 构造正常 zip，解压后上传成功。

### 5. AI 部署入口只做 handoff

后端 `deploy/ai-execute` 的职责应固定为：

- 校验权限。
- 校验 artifact 存在。
- 校验项目聊天是外部智能体。
- 创建或复用 chat_session。
- 生成 external agent prompt。
- 注入工具列表。
- 返回 handoff。

禁止：

- 自动调用 `_deploy_project_deploy_artifact_payload`。
- 自动调用 `pm-deploy` 得出最终策略。
- 静默复用历史 artifact。
- 在没有 Runner 的情况下 fallback 到服务端模型部署。

验收：

- 单测断言 `ai-execute` 不调用后端部署函数。
- 非 `external_agent` 返回明确错误。
- 返回内容包含 artifact_id、project_id、用户部署要求、工具名。

### 6. 前端展示状态收敛

前端需要明确区分两种状态：

1. 外部智能体执行状态
2. 真实部署运行状态

部署产物页展示：

- 点击 AI 部署后：显示“已交给外部智能体 Runner”，并显示 runner session id。
- 外部智能体调用部署工具后：展示部署 run 状态。
- 外部智能体未调用工具：不能显示“部署成功”。

部署运行 tab 展示：

- run status
- stage
- backup path
- upload result
- error detail
- artifact checksum
- strategy

验收：

- 外部智能体启动成功但未部署时，部署 run 不应显示 success。
- 工具部署成功后，run 显示 success。
- 工具失败后，run 显示 failed 或 blocked，并有错误详情。

## 分阶段计划

### P0：止血

目标：阻止“假 AI 部署”继续发生。

任务：

1. `ai-execute` 只返回 external agent handoff。
2. 前端要求外部智能体模式和桌面 Runner。
3. 本地流程预览改名为“流程参考”，不作为最终策略。
4. 移除 AI 部署主链对 `pm-deploy` 的依赖。

验收：

- 非 external agent 模式不能执行 AI 部署。
- 无 Runner 不能执行 AI 部署。
- `ai-execute` 不创建部署 run。
- `ai-execute` 不执行 FTP。

状态：已完成主体改造，仍需桌面端实测。

### P1：诊断修复

目标：让当前部署失败原因可定位。

任务：

1. 解包校验失败输出具体 zip/tar entry。
2. run 日志记录 `invalid_archive_entry`。
3. 前端失败日志弹窗展示非法 entry。
4. 增加 zip 路径安全测试。

验收：

- 非法 zip 明确显示哪个路径非法。
- 用户能根据日志重新打包。

### P2：真正部署 CLI 插件

目标：让外部智能体调用插件完成部署，而不是调用后端固定流程。

任务：

1. 新建 `project-deploy-cli` 插件。
2. 插件读取完整 deploy context。
3. 插件通过受控工具下载或 materialize artifact。
4. 插件根据用户要求决定解压/原样上传。
5. 插件调用受控 transport 工具上传。
6. 插件回写部署 run。

验收：

- 用户说“解压后部署”，插件解压后上传目录内容。
- 用户说“原样上传压缩包”，插件上传压缩包本身。
- 用户没说清楚时，插件可根据项目配置判断；无法判断时 blocked。
- run 记录能还原完整部署策略。

### P3：凭据与权限能力化

目标：外部智能体能部署但拿不到明文密码。

任务：

1. 为 deploy target 生成短期 capability token 或服务端内部调用句柄。
2. transport 工具内部解析 `ftp_credential_id`。
3. 所有敏感字段统一脱敏。
4. 工具调用审计记录 username、chat_session_id、artifact_id、target_id。

验收：

- prompt、日志、工具返回里不出现 FTP 密码。
- 工具能完成上传。
- 审计能查到谁通过哪个会话触发部署。

### P4：删除或重命名 pm-deploy

目标：消除概念误导。

任务：

1. 若采用下架：删除市场注册和安装脚本分支。
2. 若采用重命名：改为 `pm-deploy-plan`，描述明确为参考计划工具。
3. 更新测试、文档、提示词。

验收：

- UI 和日志中不再把 `pm-deploy` 称为部署插件。
- AI 部署主链不依赖 `pm-deploy`。

## 回归测试清单

### 后端

- `ai-execute` 非 external agent 返回 400。
- `ai-execute` external agent 返回 handoff。
- `ai-execute` 不调用 `_deploy_project_deploy_artifact_payload`。
- `deploy_project_deploy_artifact` 仍可作为受控工具部署已有 artifact。
- zip 安全解包正常路径成功。
- zip 路径穿越失败并输出具体 entry。
- 原样上传压缩包时不解压。
- 解压后部署时不上传 zip 本体。

### 前端

- 项目未配置外部智能体时，AI 部署按钮执行后提示阻塞。
- 非桌面端 Runner 时提示阻塞。
- 桌面端 Runner 可启动外部智能体会话。
- 启动 Runner 后不直接显示部署成功。
- 部署 run 成功后展示 success。
- 部署 run 失败后展示错误详情。

### 端到端

- 上传新 zip -> AI 部署 -> 外部智能体调用工具 -> run success。
- 历史 artifact -> AI 部署 -> 外部智能体调用工具 -> run success 或可解释失败。
- 非法 zip -> AI 部署 -> run failed，日志包含非法 entry。
- 用户说“只上传不部署” -> 只生成 artifact，不创建 deploy run。

## 关键验收口径

这次整改完成后，必须满足以下事实：

1. AI 部署入口不再固定决定部署流程。
2. 用户的“部署要求”和“执行流程”会进入外部智能体 prompt。
3. 外部智能体必须通过工具完成真实部署。
4. 没有工具调用时不能显示部署成功。
5. `pm-deploy` 不再作为 AI 部署核心。
6. 服务端可以提供受控部署能力，但不能替外部智能体做静默策略判断。
7. 解压失败必须能定位到具体 artifact 内部路径。

## 待决策问题

1. `pm-deploy` 是直接下架，还是重命名为 `pm-deploy-plan`？
2. 真正部署插件命名是否采用 `project-deploy-cli`？
3. 外部智能体调用部署能力时，优先走本机 CLI 插件，还是项目 MCP 工具？
4. artifact materialize 在服务端完成，还是 Runner 本机下载完成？
5. 远端命令执行是否纳入第一版，还是第一版只支持备份和上传？

建议决策：

- 短期：下架或重命名 `pm-deploy`，避免误导。
- 中期：实现 `project-deploy-cli deploy --context -`。
- 长期：把 artifact、transport、run 回写全部能力化，让外部智能体按用户要求编排。
