# AI员工工厂桌面端与本地执行器改造计划

> 生成时间：2026-06-06
> 项目：ai员工工厂 / proj-d16591a6
> 关联文档：
>
> - `docs/00-项目总览/AI项目执行系统目标定义.md`
> - `docs/00-项目总览/AI员工工厂外部执行员工接入计划.md`

## 核心结论

ai员工工厂可以继续保持 Docker 服务端部署，但要让用户稳定地使用本机 Codex、Hermes、Claude Code 和本地项目工作区，需要提供桌面端。

桌面端不是把网页简单套进 WebView，而是把当前 Local Connector 能力内置到客户端：

```text
桌面端
  -> 登录与服务端选择
  -> 本机工作区选择
  -> 本机 Codex / Hermes / Claude Code 探测
  -> 文件读写与命令执行权限控制
  -> 执行日志和状态回传

Docker 服务端
  -> 账号、项目、任务树、记忆、权限、协作、交付记录
  -> 调度桌面端或其他执行器
```

也就是说，用户未来仍然在 ai员工工厂下达项目目标；桌面端负责把这些目标转化为本机执行能力。

## 当前问题

### 1. Docker 服务端不能直接获取用户本机能力

当前前端会显示“本地连接器”“连接器工作区”和“外部 Agent”，但用户很容易理解成 Docker 服务端可以直接发现本机 Codex 或本机目录。

实际边界是：

- Docker 服务端只能访问容器或服务器上的资源。
- 用户 Mac / Windows 上的项目目录、Codex、Hermes，只能由运行在那台机器上的进程访问。
- 当前 Local Connector 就是这个本机进程。

因此，远程 Docker 部署没有问题，但执行器必须靠近工作区。

### 2. 登录页缺少服务端地址配置

当前前端 API 固定使用 `/api`：

```js
const api = axios.create({ baseURL: "/api" });
```

这适合浏览器访问固定域名或同源部署，但不适合桌面端。桌面端用户可能今天连接本机服务，明天连接远程 Docker 服务，后天连接测试环境。

登录前必须允许用户填写和切换服务端地址。

### 3. 外部 Agent 设置交互不够清晰

当前项目聊天设置中，“执行方式”“外部 Agent”“本地连接器”“连接器工作区”“协作模式”集中在一组表单里。

主要问题：

- 用户不知道“本地连接器离线”是服务端问题、浏览器问题，还是本机 Connector 没启动。
- “连接本机”“刷新”“选择目录”“保存”“测试”是多个离散动作，缺少明确步骤。
- 工作区路径是连接器所在电脑上的绝对路径，但界面没有足够强调这一点。
- 外部 Agent 可用性依赖连接器在线、Codex 可用、工作区可读、权限模式正确，但当前反馈分散。
- 协作模式和执行器设置混在一起，容易误解成选择“自动协作”就能自动解决本地执行环境问题。

### 4. 网页模式和桌面模式边界不清

浏览器网页只能通过 `127.0.0.1` 探测本地 Connector；桌面端可以直接内置 Connector。

如果不区分这两种模式，用户会困惑：

- 为什么网页需要安装连接器？
- 为什么 Docker 服务端不能读取本地路径？
- 为什么桌面端可以选择本机目录？
- 为什么同一个项目在不同电脑上的工作区路径不同？

## 改造目标

### 产品目标

把 ai员工工厂改造成：

```text
服务端项目执行中枢 + 桌面端本机执行入口
```

服务端负责项目级状态，桌面端负责本机能力。

### 用户体验目标

用户在桌面端打开应用后，流程应该是：

```text
选择或输入服务端地址
-> 检查服务端健康状态
-> 登录账号
-> 选择项目
-> 绑定本机工作区
-> 检测 Codex / Hermes / Claude Code
-> 下达项目目标
-> 查看任务树、执行日志、验证结果和交付报告
```

用户不应该再单独理解“先安装 Local Connector，再打开网页，再配对，再填路径”这一串隐性前置条件。

## 桌面端架构

### 推荐技术路线

当前项目桌面端默认只使用 Tauri。

这是后续开发的硬约束，不再把 Electron 作为并列默认方案。除非用户在后续对话里再次明确要求“用 Electron 做实验版本”，否则任何实现、脚手架、依赖、打包脚本、文档和验收都必须围绕 Tauri 展开。

Tauri 优势：

- 包体较小。
- 原生文件选择和命令执行能力清晰。
- 权限边界更容易收敛。
- 适合把现有 Vue 前端迁入桌面壳。
- 更符合本项目“网页仍可 Docker 部署，桌面端负责本机能力”的长期架构。

Electron 仅作为显式实验选项：

- 不允许在未确认的情况下新增 Electron 依赖、`electron/` 目录、Electron preload 或 Electron main 进程。
- 不允许把“快速验证”作为偏离 Tauri 的理由。
- 如果确实需要 Electron 对比实验，必须单独建立实验分支或独立目录，并在文档中标注“非主线实现”。

后续开发者判断标准：

```text
默认路线：Vue 前端 + src-tauri 原生壳 + Tauri command bridge。
网页构建：继续使用 Vite，保持 Docker / 浏览器部署可用。
桌面构建：使用 Tauri CLI，复用同一套 Vue 前端。
本机能力：通过 Tauri command 暴露给前端，不直接依赖浏览器能力。
```

### 桌面端模块

```text
desktop-shell/
  server-profile      服务端地址管理
  auth-session        登录态与 token 管理
  workspace-manager   工作区选择、保存、校验
  executor-detector   Codex / Hermes / Claude Code 探测
  local-runner        命令执行、PTY、日志流
  file-bridge         文件读写、搜索、目录树
  permission-guard    权限确认、沙箱模式、危险动作拦截
  sync-client         状态、任务树、日志、验证结果回传服务端
```

### 服务端职责保持不变

服务端继续负责：

- 用户账号和权限。
- 项目配置。
- 员工、技能、规则。
- 任务树。
- requirement 对象。
- 工作会话。
- 项目记忆。
- 交付报告。
- 多人协作和审计。

服务端不直接假设自己能访问用户本机工作区。

## 登录页服务端地址改造

### 新增登录前服务端选择

登录页增加“服务端地址”区域，默认收起或以紧凑方式展示。

字段：

```text
服务端地址
最近使用
连接状态
环境标签
```

示例：

```text
服务端地址：
https://ai.example.com

最近使用：
- 本机开发 http://127.0.0.1:5173 或 http://127.0.0.1:8000
- 远程 Docker https://xxx.example.com
- 测试环境 https://test.xxx.example.com
```

### 地址校验规则

输入后先校验：

- 必须是 `http://` 或 `https://`。
- 去掉末尾 `/`。
- 不允许把路径误填成 API 路径，例如 `/api/auth/login`。
- 点击登录前先请求健康检查接口。

推荐新增接口：

```text
GET /api/health
GET /api/init/status
```

桌面端保存的是服务端 origin，例如：

```text
https://ai.example.com
```

API 层拼接：

```text
{server_origin}/api
```

### 本地存储

桌面端持久化：

```json
{
  "active_server_origin": "https://ai.example.com",
  "server_profiles": [
    {
      "id": "prod",
      "name": "远程生产",
      "origin": "https://ai.example.com",
      "last_used_at": "2026-06-06T14:30:00+08:00"
    }
  ]
}
```

浏览器模式也可以使用 localStorage 保存最近地址，但只在独立部署或调试环境启用；生产网页默认同源 `/api`，避免普通用户误改。

### 登录态隔离

不同服务端地址必须隔离 token。

不要只用一个全局 `token` key，否则从 A 服务端切到 B 服务端时会出现登录态串线。

建议 key：

```text
auth:<normalized_server_origin>:token
auth:<normalized_server_origin>:profile
auth:<normalized_server_origin>:remember_login_info
```

### API 客户端改造

当前：

```js
axios.create({ baseURL: "/api" });
```

目标：

```text
baseURL = resolveActiveServerOrigin() + '/api'
```

要求：

- 登录前也能设置 active server。
- 切换 server 后清空当前运行中的请求状态。
- 401 只清理当前 server 的 token。
- WebSocket、SSE、文件下载、MCP 地址复制都必须共用同一个 server origin。

## 当前前端 UI 交互改造

### 1. 登录页

现状：登录页只输入账号和密码。

目标：登录页变成“连接服务端 + 登录账号”两段式。

推荐布局：

```text
顶部：产品名和当前连接状态

服务端区域：
  服务端地址输入
  最近使用下拉
  测试连接按钮
  状态提示：可连接 / 初始化未完成 / 无法连接 / 版本不兼容

账号区域：
  账号
  密码
  记住密码
  登录按钮
```

交互规则：

- 服务端未校验通过时，登录按钮禁用。
- 如果服务端返回 `setup_required=true`，主按钮变成“初始化此服务端”。
- 切换服务端时，账号密码保留但 token 不复用。
- 错误提示放在服务端输入框下方，不只弹全局 toast。

### 2. 初始化页

初始化页也要支持服务端地址。

用户可能第一次打开桌面端，但要初始化的是远程 Docker 服务。此时初始化页必须清楚显示当前服务端地址，避免把本机和远程环境混淆。

### 3. 项目聊天设置

当前表单应拆成两个层级：

```text
执行入口
  系统对话
  外部 Agent

本机执行环境
  运行位置：本机桌面端 / 本地连接器 / 服务器执行器
  执行器：Codex / Hermes / Claude Code
  工作区
  权限模式
  环境检查

协作策略
  自动协作
  手动选择员工
```

这样用户能理解“协作模式”不负责解决本机执行环境。

### 4. 本机执行环境状态卡

外部 Agent 模式下，优先显示一张状态卡，而不是零散表单。

状态卡包含：

```text
运行位置：当前电脑
连接状态：在线
工作区：/Volumes/work_mac_1_5T/self/ai-employee
Codex：已安装 / 未检测到
Hermes：已安装 / 未检测到
权限：workspace-write
```

主按钮：

```text
选择工作区
检查环境
开始执行
```

只有环境检查通过后，“开始执行”才可用。

### 5. 网页模式提示

如果用户在浏览器网页中启用外部 Agent，界面必须明确提示：

```text
当前是网页模式。网页不能直接读取本机项目，需要启动本地连接器。
如果使用桌面端，则连接器能力已内置。
```

按钮：

```text
连接本机
下载桌面端
查看说明
```

### 6. 工作区路径输入

工作区路径必须标注归属：

```text
这是运行执行器的那台电脑上的绝对路径。
```

不要只写 `/path/to/project`。建议 placeholder 使用与系统相关的示例：

```text
macOS: /Volumes/work_mac_1_5T/self/ai-employee
Windows: D:\projects\ai-employee
Linux: /home/user/projects/ai-employee
```

桌面端优先用系统目录选择器，减少手填路径。

### 7. 错误状态

错误必须可行动。

示例：

```text
本地连接器离线
原因：没有检测到本机 Connector 心跳。
下一步：启动桌面端，或点击“连接本机”进行配对。
```

```text
连接器未检测到 Codex CLI
原因：当前电脑 PATH 中没有 codex 命令。
下一步：安装 Codex CLI，或在桌面端设置 Codex 可执行文件路径。
```

```text
工作区不可访问
原因：连接器所在电脑上不存在该路径。
下一步：选择这台电脑上的项目目录。
```

### 8. 不要把执行器设置藏得太深

项目聊天是主要执行入口，外部 Agent 可用性应该在发送消息前就能看到。

建议在输入框附近显示简短状态：

```text
外部 Agent：Codex · 本机 · 工作区已就绪
```

未就绪时：

```text
外部 Agent 未就绪：请选择工作区
```

点击状态进入设置面板。

## AI 对话交互重构

### 当前代码观察

当前 AI 对话主界面集中在 `web-admin/frontend/src/views/projects/ProjectChat.vue`，它已经包含很多能力：

- 左侧项目和最近对话。
- 中间消息列表。
- 空状态推荐问题。
- 用户消息与 AI 消息气泡。
- 消息内联编辑和重新生成。
- 操作过程卡片。
- 任务树抽屉。
- 终端镜像和终端审批。
- 附件上传。
- 斜杠菜单。
- 模型选择。
- 外部 Agent 状态条。
- 工作状态条。
- 多媒体参数面板。

问题不在于功能少，而在于这些能力没有形成主流 AI 对话产品那种清晰的信息架构。

当前交互的主要问题：

- `ProjectChat.vue` 过大，消息渲染、任务树、终端、审批、输入框、设置入口和运行状态混在一个文件里，导致后续交互优化成本很高。
- 消息区域里同时承载回答正文、过程轨迹、操作卡、终端表单、审批表单和任务树审计，普通用户很难判断“AI 正在回答”还是“系统正在执行任务”。
- 任务树放在抽屉里，执行状态又在消息卡和输入框上方各出现一份，状态入口分散。
- 输入框底部同时放模型、附件、多媒体参数、快捷提示、暂停和发送按钮，主操作不够突出。
- 外部 Agent 模式只显示一个 pill，缺少像主流产品那样的“当前执行环境是否就绪”的明显提示。
- 终端输出、命令证据和任务进度都在消息流内部展开，会打断对话阅读。
- 空状态文案偏系统说明，缺少“我可以帮你做什么”的直接任务入口。
- 当前界面视觉上有较多装饰、面板和状态条，作为项目执行系统可以保留专业感，但对话主路径需要更克制。

### 重构目标

AI 对话应该从“把所有能力塞进聊天流”改成“三层工作台”：

```text
左侧：会话与项目
中间：主对话
右侧：执行详情
```

中间主对话只负责：

- 用户目标。
- AI 的简洁回复。
- 关键确认。
- 任务完成摘要。

右侧执行详情负责：

- 任务树。
- 当前步骤。
- Codex / Hermes 工作细节。
- 命令日志。
- 文件变更。
- 权限确认。
- 验证结果。

这样既保留项目执行系统的专业能力，又让主对话接近主流 AI 产品的使用习惯。

### 推荐布局

桌面宽屏：

```text
┌────────────────┬──────────────────────────────┬──────────────────────┐
│ 会话 / 项目     │ 对话                          │ 执行详情              │
│                │                              │                      │
│ 最近对话        │ 用户消息                      │ 当前任务              │
│ 项目切换        │ AI 回复                        │ 任务树                │
│ 新对话          │ 关键确认卡                    │ Codex 日志            │
│                │                              │ 文件变更              │
│                │ 输入框                        │ 验证结果              │
└────────────────┴──────────────────────────────┴──────────────────────┘
```

窄屏或网页：

```text
对话为主
执行详情通过底部 sheet 或右侧抽屉打开
输入框固定在底部
```

### 中间对话区

主流 AI 对话体验应具备：

- 消息最大宽度稳定，避免左右大幅漂移。
- 用户消息靠右或轻量右对齐，AI 消息靠左。
- AI 正在生成时显示短状态，例如“正在分析项目上下文”。
- 执行型任务不在正文里堆大量日志，只显示摘要和“查看执行详情”。
- AI 回复底部提供复制、重新生成、编辑后重试、转为任务等轻量操作。
- 长回答自动分段，代码块可复制。
- 错误状态直接说明原因和下一步。

执行型消息示例：

```text
我会把登录页改成可选择服务端地址，并同步处理 API baseURL 与 token 隔离。

已创建任务：
1. 梳理当前 API 调用入口
2. 增加服务端地址配置
3. 改造登录页
4. 验证登录和切换服务端

[查看执行详情]
```

### 右侧执行详情区

执行详情区是 ai员工工厂区别于普通聊天产品的核心，但默认不要挤压主对话。

建议使用 tabs：

```text
进度
日志
文件
验证
权限
```

`进度`：

- 当前任务树。
- 当前节点。
- 完成 / 进行中 / 等待用户 / 失败。
- 每个节点的验证状态。

`日志`：

- Codex / Hermes / Claude Code 的结构化事件。
- 只展示摘要行，原始终端可展开。

`文件`：

- 新增、修改、删除文件列表。
- 每个文件的 diff 入口。

`验证`：

- 测试命令。
- 构建结果。
- API 检查。
- 截图或运行状态。

`权限`：

- 本次请求的沙箱模式。
- 高风险动作确认记录。
- 执行来源：桌面端 / 本地连接器 / 服务器执行器。

### 输入框重构

当前输入框能力多，但主操作不够集中。目标是让输入框像主流 AI 产品一样直接：

```text
输入目标...
[附件] [工具/模式] [执行环境状态]                         [发送]
```

建议：

- 发送按钮保持唯一主按钮。
- 模型选择、执行方式、媒体参数放入一个“模式/工具”菜单，不长期占用底部空间。
- 外部 Agent 状态作为一个短状态 chip 显示，例如 `Codex · 本机就绪`。
- 未就绪时 chip 显示 `外部 Agent 未就绪`，点击直接打开环境检查。
- 支持 `Enter` 发送、`Shift+Enter` 换行、`Cmd/Ctrl+Enter` 强制发送。
- 上传附件后在输入框上方显示紧凑附件条。
- 正在执行时发送按钮切换为停止按钮，旁边显示“查看进度”。

### 空状态重构

空状态不要先讲系统概念，应该给用户可以直接点击的任务入口。

示例：

```text
今天要推进什么？

[修复一个 bug]
[分析当前项目]
[生成改造计划]
[检查部署状态]
[让 Codex 修改代码]
```

如果项目未配置执行环境：

```text
当前项目还没有绑定本机执行环境。

[选择工作区]
[连接桌面端]
[先用普通对话]
```

### 执行状态展示规则

不要把所有状态都做成消息。

推荐规则：

- 用户目标和 AI 关键结论进入消息流。
- 任务树、命令、文件、验证进入右侧执行详情。
- 等待用户确认时，在消息流出现一张确认卡，同时右侧权限 tab 记录详情。
- 失败时，消息流显示可读原因和下一步；右侧保留错误堆栈和原始日志。
- 完成时，消息流显示交付摘要；右侧保留证据。

### Codex 工作细节展示

Codex 的工作细节应分层：

默认展示：

```text
Codex 正在执行：改造登录页服务端地址配置
当前步骤：修改 API baseURL
```

展开进度：

```text
读取文件：web-admin/frontend/src/utils/api.js
修改文件：web-admin/frontend/src/views/auth/LoginPage.vue
运行命令：npm test
```

高级日志：

```text
原始终端输出
工具调用事件
命令 stdout / stderr
文件 diff
```

默认不展示大段原始日志，避免对话流变成终端。

### 组件拆分建议

从 `ProjectChat.vue` 拆出以下组件：

```text
ProjectChatShell.vue
ChatConversationSidebar.vue
ChatMessageList.vue
ChatMessageRow.vue
ChatComposer.vue
ChatEmptyState.vue
ExecutionStatusChip.vue
ExecutionDetailPanel.vue
ExecutionTaskTreeTab.vue
ExecutionLogTab.vue
ExecutionFilesTab.vue
ExecutionVerificationTab.vue
ExecutionPermissionTab.vue
TerminalMirrorPanel.vue
OperationApprovalCard.vue
```

拆分原则：

- 消息列表只关心消息。
- 输入框只关心输入和发送。
- 执行详情只关心任务、日志、文件、验证和权限。
- 终端只作为执行详情的一种视图，不直接污染普通对话流。

### 阶段落地

第一步：不改业务逻辑，只调整信息架构。

- 保留现有消息、任务树、终端和操作卡数据结构。
- 新增右侧 `ExecutionDetailPanel`。
- 把任务树抽屉能力迁入右侧面板。
- 消息流里的过程卡默认折叠成“查看执行详情”。

第二步：重构输入框。

- 收敛底部按钮。
- 增加执行环境 chip。
- 把模型、媒体参数、外部 Agent 配置放入工具菜单。

第三步：拆分 `ProjectChat.vue`。

- 先拆纯展示组件。
- 再拆状态计算和事件处理。
- 最后拆终端与审批逻辑。

第四步：接入桌面端执行细节。

- Codex / Hermes 日志进入执行详情面板。
- 文件变更进入文件 tab。
- 权限确认进入权限 tab。
- 交付验证进入验证 tab。

### 验收标准

- 普通用户可以只看中间对话完成一次任务，不需要理解任务树细节。
- 开发者可以打开右侧执行详情查看 Codex 做了什么。
- 等待用户确认时，确认卡明显、可操作，并能恢复原任务。
- 输入框主按钮清晰，状态 chip 能说明当前使用的是普通对话、Codex、本机执行还是服务器执行。
- 移动端或窄屏下，对话仍然优先，执行详情可临时打开。
- `ProjectChat.vue` 不再继续承载所有交互，核心组件职责清晰。

## 本地执行器能力

### Codex 探测

桌面端启动后执行：

```text
codex --version
which codex
```

记录：

- 是否可用。
- 可执行文件路径。
- 版本。
- 默认工作目录权限。

### Hermes 探测

根据 Hermes 实际部署方式支持多种探测：

```text
hermes --version
hermes daemon status
HTTP health endpoint
配置文件路径
```

如果 Hermes 是独立服务，桌面端只保存 endpoint 和认证信息，不强行假设它是命令行。

### Claude Code 探测

类似 Codex：

```text
claude --version
which claude
```

具体命令以实际 CLI 为准，不能硬编码到不可配置。

### 工作区权限

每个工作区保存：

```json
{
  "project_id": "proj-d16591a6",
  "workspace_path": "/Volumes/work_mac_1_5T/self/ai-employee",
  "sandbox_mode": "workspace-write",
  "allowed_executors": ["codex_cli", "hermes"],
  "last_verified_at": "2026-06-06T14:30:00+08:00"
}
```

危险动作仍需确认：

- 删除大量文件。
- 覆盖配置。
- 部署。
- 发布。
- 暴露凭据。
- `git reset --hard` 等不可逆操作。

## 服务端与桌面端协议

### 桌面端注册

桌面端登录后向服务端注册当前执行端：

```json
{
  "client_type": "desktop",
  "device_name": "liudeMac-mini.local",
  "platform": "darwin",
  "capabilities": {
    "workspace_pick": true,
    "file_read": true,
    "file_write": true,
    "terminal": true,
    "codex_cli": true,
    "hermes": true
  }
}
```

### 心跳

桌面端持续上报：

```json
{
  "online": true,
  "active_workspace": "/Volumes/work_mac_1_5T/self/ai-employee",
  "executors": {
    "codex_cli": {
      "available": true,
      "version": "..."
    },
    "hermes": {
      "available": false,
      "reason": "未配置 Hermes endpoint"
    }
  }
}
```

### 执行任务

服务端下发：

```json
{
  "task_id": "...",
  "project_id": "proj-d16591a6",
  "chat_session_id": "...",
  "executor_type": "codex_cli",
  "workspace_path": "/Volumes/work_mac_1_5T/self/ai-employee",
  "sandbox_mode": "workspace-write",
  "user_goal": "用户原始目标",
  "task_node": {
    "id": "...",
    "title": "..."
  }
}
```

桌面端回传：

```json
{
  "task_id": "...",
  "event_type": "tool_result",
  "summary": "执行了测试",
  "evidence": {
    "command": "npm test",
    "exit_code": 0
  }
}
```

## 改造阶段

### 阶段 1：前端服务端地址抽象

目标：

- 登录页增加服务端地址。
- API、WebSocket、SSE、下载地址统一走 active server origin。
- token 按服务端隔离。
- 初始化页支持当前服务端展示和初始化。

验收：

- 可以在登录页切换本机开发服务和远程 Docker 服务。
- 切换服务端后不会串用旧 token。
- 服务端不可达时给出明确错误。

### 阶段 2：外部 Agent 设置 UI 梳理

目标：

- 将“执行方式”“本机执行环境”“协作策略”拆分。
- 增加环境状态卡。
- 明确网页模式和桌面模式差异。
- 错误状态给出下一步动作。

验收：

- 用户能一眼看出为什么外部 Agent 不可用。
- 用户知道工作区路径属于哪台机器。
- “协作模式”不再被误解为连接器配置。

### 阶段 3：桌面端最小可用版本

目标：

- 桌面端可配置服务端地址并登录。
- 可选择本机工作区。
- 可检测 Codex CLI。
- 可把桌面端注册为本机执行器。
- 可从项目聊天触发 Codex 在本机工作区执行。

验收：

- 不单独安装 Local Connector，也能完成本机执行。
- 服务端任务树能看到执行状态。
- 前端能看到日志流和最终验证结果。

### 阶段 4：Hermes 与多执行器

目标：

- 支持 Hermes endpoint 或本机 Hermes runner。
- 支持 Claude Code。
- 支持每个项目选择默认执行器。
- 支持按任务类型自动选择执行器。

验收：

- 代码任务可走 Codex。
- 多工具编排任务可走 Hermes。
- 执行器不可用时系统能解释原因并建议替代方案。

### 阶段 5：权限、审计和分发

目标：

- 桌面端签名和自动更新。
- 权限确认弹窗。
- 危险动作拦截。
- 执行日志审计。
- 多服务端 profile 管理。

验收：

- 用户能查看某次执行改了哪些文件、跑了哪些命令、是否经过确认。
- 管理员能看到执行来源是哪个桌面端和哪台机器。

## 技术改造清单

### 前端

- 新增 `server-profile` 工具模块。
- 改造 `utils/api.js`，支持动态 baseURL。
- 改造 `utils/ws-chat.js`，WebSocket 地址从 active server origin 生成。
- 改造登录页 `LoginPage.vue`。
- 改造初始化页 `InitPage.vue`。
- 改造项目聊天设置中的外部 Agent 配置区。
- 增加本机执行环境状态组件。
- 增加服务端连接状态组件。

### 桌面端

- 使用 Tauri 作为唯一默认桌面壳。
- 复用现有 Vue 前端。
- 增加 Tauri command bridge，先覆盖原生目录选择和执行器探测。
- 内置 Local Connector 能力。
- 实现执行器探测。
- 实现任务日志流回传。
- 禁止默认新增 Electron 实现；Electron 只能在用户明确要求时作为实验项。

### 后端

- 增加桌面端注册和心跳接口。
- 统一 local connector 与 desktop executor 的数据模型。
- 增加执行器能力查询接口。
- 增加任务下发和事件回传接口。
- 保持任务树、工作会话、requirement、交付报告为主状态。

## UI 设计原则

- 一个屏幕只突出一个主动作；登录页先连接服务端，再登录。
- 状态必须靠近操作；外部 Agent 不可用时，在发送入口和设置区都要显示原因。
- 错误必须有下一步；不要只显示“离线”。
- 路径必须标注机器归属；避免用户把 Docker 容器路径、本机路径和服务器路径混淆。
- 连接器、执行器、协作模式是三类概念，界面上必须分组。
- 桌面端优先使用系统原生选择器，减少手填路径。
- 所有按钮要有明确状态：默认、加载、禁用、失败后重试。

## 风险

### 服务端地址导致登录态混乱

风险：用户切换服务端后仍使用旧 token。

处理：token 和 profile 必须按 server origin 隔离。

### 桌面端权限过大

风险：桌面端能读写本机文件和执行命令。

处理：工作区级授权、沙箱模式、危险动作确认、审计日志。

### 网页和桌面端能力不一致

风险：用户在网页看到的功能，在桌面端行为不同。

处理：显式展示当前运行模式：网页模式 / 桌面模式 / 服务器执行模式。

### Hermes 部署形态不统一

风险：Hermes 可能是 CLI、daemon、HTTP 服务或容器。

处理：不要硬编码单一路径，抽象为 executor provider。

## 最小落地建议

优先做三件事：

1. 登录页支持服务端地址，并完成 API / WebSocket / token 隔离。
2. 把外部 Agent 设置 UI 改成“环境状态卡 + 分步检查”。
3. 做桌面端最小壳，内置工作区选择和 Codex 探测。

这三件事完成后，用户就能明确理解：

```text
服务端负责项目管理。
桌面端负责本机执行。
ai员工工厂负责下达目标和收集交付结果。
```

## 2026-06-06 开发进度

### 已落地

1. 登录前服务端地址能力已进入前端：
   - 新增 `web-admin/frontend/src/utils/server-profile.js`。
   - API、WebSocket、素材下载、运行时 URL 已改为跟随 active server origin。
   - token、角色、记住登录信息按 server origin 隔离。
   - 登录页可输入服务端地址、测试连接、展示最近服务端。
   - 初始化页显示当前服务端，并支持返回登录页切换服务端。

2. 项目聊天 AI 交互已开始按“三层工作台”改造：
   - 中间对话区右侧新增常驻“执行详情”栏。
   - 执行详情包含 `进度 / 日志 / 文件 / 验证 / 权限` tabs。
   - 任务树节点、当前执行状态、终端输出、工作区、权限模式都能在右侧聚合查看。
   - 输入框左下新增执行环境状态 chip，未就绪时可直接进入设置。
   - 宽屏显示右侧执行详情，窄屏自动退回主对话视图。

3. 外部 Agent 设置区已按概念分组：
   - `执行入口`：系统对话 / 外部 Agent。
   - `本机执行环境`：连接器、工作区、权限、Codex/Hermes/Claude Code 检查入口。
   - `协作策略`：自动协作 / 手动模式。
   - 工作区输入已明确标注“执行器所在电脑上的绝对路径”。
   - 网页模式提示用户需要本地连接器；桌面端会内置本机能力。

4. 桌面端原生桥前端挂载点已补齐：
   - 新增 `web-admin/frontend/src/utils/native-desktop-bridge.js`。
   - 支持未来 Tauri command bridge，也保留 `__AI_EMPLOYEE_DESKTOP__` / `aiEmployeeDesktop` 作为兼容注入名。
   - 工作区选择优先调用原生目录选择器，失败后回退原有服务端/手填路径。
   - 设置区预留 Codex、Hermes、Claude Code 探测展示与“检查环境”按钮。

5. 桌面端技术路线已收敛：
   - 主线实现固定为 Tauri。
   - Electron 不再作为默认备选方案。
   - 后续任何桌面端开发都必须优先检查 `web-admin/frontend/src-tauri/`。
   - Tauri 与网页共用 Vue 前端；网页仍通过 `npm run build` 打包，桌面端通过 Tauri CLI 打包。

6. Tauri 最小壳已开始落地：
   - 新增 `web-admin/frontend/src-tauri/tauri.conf.json`。
   - 新增 `web-admin/frontend/src-tauri/Cargo.toml`、`build.rs`、`src/main.rs`。
   - 已在 Rust command 中预置 `pick_workspace_directory`、`detect_executors`、`get_runtime_info`。
   - 前端 `native-desktop-bridge.js` 已适配 Tauri `window.__TAURI__.core.invoke`，并保留兼容注入名。
   - 新增 `npm run tauri:check` 做 Tauri 契约自检。
   - `npm run tauri:dev` / `npm run tauri:build` 只在本机已安装 Tauri CLI 时使用，不影响 Docker / 网页构建。

### 当前边界

- 当前仓库的桌面原生入口必须落在 `web-admin/frontend/src-tauri/`。
- 当前 npm 默认依赖不强制安装 Tauri CLI，因此网页构建仍然可用；桌面开发机需要自行安装 Tauri CLI 和 Rust 工具链。
- Codex / Hermes 的交互式真实执行、PTY 日志流、危险动作系统弹窗，还需要后续原生壳或本地执行器进程实现。
- 桌面桥必须通过 Tauri command 实现；前端 `native-desktop-bridge.js` 负责适配 Tauri invoke 与兼容注入名。
- 现阶段只允许实现低风险能力：目录选择、执行器探测、运行时信息读取、受限 Runner 自检命令。任意命令执行、PTY 和写入类动作必须在权限策略、审计日志和危险动作确认设计完成后再接入。

### 防跑偏规则

后续继续开发时必须先检查这一节：

1. 桌面端默认技术栈是 Tauri，不是 Electron。
2. 不要新增 `electron/` 目录、Electron preload、Electron main 进程或 Electron 依赖。
3. 不要把本地命令执行直接塞进前端或普通 Web API。
4. 所有本机能力都应通过 Tauri command 暴露，并在前端 `native-desktop-bridge.js` 里统一适配。
5. 每次新增本机能力，都要同时说明权限边界、用户确认方式、审计记录和网页模式下的降级提示。
6. 网页构建必须继续通过；桌面能力不能让 Docker / 浏览器部署变成必须安装 Tauri。
7. Runner 命令不得走 shell 字符串，必须使用结构化 `command + args + workspacePath`，并由 Tauri command 内部白名单分类后再执行。

### 下一阶段 Tauri 落地顺序

1. 建立 `web-admin/frontend/src-tauri/`：
   - `tauri.conf.json`
   - `Cargo.toml`
   - `build.rs`
   - `src/main.rs`
2. 在 Tauri command 中实现：
   - `pick_workspace_directory`
   - `detect_executors`
   - `get_runtime_info`
3. 前端 `native-desktop-bridge.js` 适配：
   - 优先识别 Tauri `window.__TAURI__.core.invoke`
   - 保留 `__AI_EMPLOYEE_DESKTOP__` / `aiEmployeeDesktop` 兼容入口
4. 验证：
   - `npm run build`
   - Tauri 契约自检脚本
   - 安装 Tauri CLI 后再执行 `npm run tauri:dev`

### 验证

已执行：

```bash
cd web-admin/frontend
npm run build
```

结果：构建通过。仍存在项目原有的 `mockjs eval` 和大 chunk 体积警告。

## 2026-06-06 继续开发记录

### 本轮已完成

1. Tauri 骨架修正：
   - `src-tauri/Cargo.toml` 保持二进制桌面应用形态，不再声明不存在的 Rust library target。
   - `src-tauri/check-tauri-shell.mjs` 增加 `get_runtime_info`、Tauri v2 依赖和前端桥接契约检查。
   - 继续保持 `tauri:dev` / `tauri:build` 脚本只依赖本机 Tauri CLI，不把 Tauri CLI 放进默认 npm 依赖，避免影响 Docker/Web 安装。

2. 桌面桥能力补齐：
   - `native-desktop-bridge.js` 增加 `getNativeRuntimeInfo()`。
   - `detectNativeExecutors()` 返回值增加 workspace 检测结果归一化。
   - Tauri command 映射继续统一走 `pick_workspace_directory`、`detect_executors`、`get_runtime_info`。

3. 项目聊天页桌面态增强：
   - 外部 Agent 设置卡展示原生桥平台、架构和版本。
   - “检查环境”会同时读取 Tauri runtime info、Codex/Hermes/Claude Code 状态和本机工作区可访问性。
   - 桌面端选择工作区时优先走 Tauri 原生目录选择器。
   - 设置区明确提示：当前桌面桥已覆盖目录选择和执行器检测；完整外部 Agent 执行仍沿用现有后端连接器链路，直到本地 Runner / PTY / 权限审批接入完成。

### 当前仍未完成

- 还没有把 Codex/Hermes 的交互式真实执行、PTY 日志流、权限确认弹窗和审计记录迁入 Tauri。
- 因此当前桌面端不是“完整桌面版 Codex”，只是已经具备本机能力探测、工作区选择和受限 Runner 自检的 Tauri 壳基础。
- 要达到“桌面 Codex 等价能力”，下一阶段必须实现 Tauri 本地 Runner：
  - command execution / PTY session
  - permission guard
  - approval dialog
  - streamed logs
  - task-tree / work-session 回传
  - workspace scoped file bridge

### 本轮验证

已执行：

```bash
cd web-admin/frontend
npm run tauri:check
npm run build
```

结果：

- `npm run tauri:check` 通过。
- `npm run build` 通过。
- 构建仍存在项目原有的 `mockjs eval` 和大 chunk 体积警告。

未完成验证：

```bash
cargo --version
tauri --version
```

当前机器返回 `command not found`，说明本机还没有 Rust / Tauri CLI，暂时无法执行 `cargo check`、`npm run tauri:dev` 或 `npm run tauri:build` 的原生编译验证。

## 2026-06-06 Tauri Runner 基础能力继续开发记录

### 本轮目标

在不引入 Electron、不影响 Docker/Web 构建的前提下，先把桌面端本地 Runner 的安全契约打通：

- Tauri command 提供命令风险分类。
- Tauri command 提供低风险自检命令执行。
- 前端原生桥统一适配 Runner command。
- 项目聊天页展示 Runner 自检入口和结果。
- 合约检查脚本覆盖新增能力。

### 已实现范围

1. Tauri 原生命令契约：
   - 新增 `classify_runner_command`。
   - 新增 `run_runner_command`。
   - 请求结构固定为 `command`、`args`、`workspacePath`、`timeoutMs`、`dryRun`。
   - 返回结构包含 `allowed`、`riskLevel`、`requiresApproval`、`blockedReason`、`stdout`、`stderr`、`exitCode`、`durationMs`、`timedOut`。

2. 当前白名单：
   - `node --version`
   - `npm --version`
   - `git --version`
   - `git status --short`
   - `codex --version`
   - `hermes --version`
   - `claude --version`
   - `cargo --version`
   - `tauri --version`

3. 权限边界：
   - 不通过 shell 执行。
   - 不接受任意字符串拼接命令。
   - `git status --short` 必须有可访问的本机工作区目录。
   - 当前分类结果只会返回 `low` 或 `blocked`。
   - 当前不实现写入类、安装类、删除类、提交类、部署类命令。

4. 前端桥接：
   - `native-desktop-bridge.js` 新增 `classifyNativeRunnerCommand()`。
   - `native-desktop-bridge.js` 新增 `runNativeRunnerCommand()`。
   - Web 模式下仍然不会假装有本机 Runner。

5. ProjectChat UI：
   - 外部 Agent 的“本机执行环境”状态卡新增 `Runner 自检`。
   - 本地运行侧栏新增“本机 Runner 自检”卡片。
   - 自检会检查原生桥、执行器状态、工作区和少量只读命令。
   - 输出只展示摘要、退出码和拦截原因，不把它包装成完整终端。

6. 验证入口：
   - `src-tauri/check-tauri-shell.mjs` 已覆盖新增 Tauri command 和前端桥接方法。

### 仍未实现范围

- 未实现 Codex/Hermes/Claude Code 的交互式会话。
- 未实现 PTY 流式日志。
- 未实现危险动作授权弹窗。
- 未实现授权决策持久化和审计回传。
- 未实现任务树 / work-session 与桌面 Runner 的完整回传闭环。
- 未实现 Tauri 原生编译验证；当前机器缺少 Rust / Tauri CLI。

### 后续开发顺序

1. 在当前白名单 Runner 基础上接入权限决策记录。
2. 再接入只读文件检索、目录列表和差异预览。
3. 再接入需要确认的写入类操作。
4. 最后接入 PTY 与 Codex/Hermes 交互式执行。

任何阶段都必须保持：

- Tauri 主线。
- Web/Docker 构建可用。
- 本机命令不走 shell。
- 高风险动作必须显式授权。

## 2026-06-08 Tauri Runner 权限决策记录继续开发

### 本轮目标

在不放开 Runner 命令白名单、不引入 Electron 的前提下，先把“用户对命令审批的决定可被桌面端记录”接入原生桥：

- Tauri 原生命令提供权限决策记录写入。
- Tauri 原生命令提供最近权限决策读取。
- 前端 bridge 统一适配权限决策记录 API。
- 本地运行面板的命令审批卡展示最近记录。
- 终端审批按钮触发时尝试写入原生账本。

### 已实现范围

1. Tauri 原生命令契约：
   - 新增 `record_runner_permission_decision`。
   - 新增 `list_runner_permission_decisions`。
   - 单条记录包含 `decisionId`、`command`、`args`、`workspacePath`、`decision`、`reason`、`scope`、`source`、`riskLevel`、`createdAtEpochMs`。
   - 允许的决定枚举为 `approve_once`、`approve_session`、`reject`。

2. 本机存储边界：
   - 使用 Tauri app data 目录下的 `runner-permission-decisions.json`。
   - 只保留最近 100 条。
   - 不写 legacy session 文件，不新增多个 fallback 状态位置。
   - 当前是桌面端本机审计账本，还没有回传服务端任务树或 work-session。

3. 前端桥接：
   - `native-desktop-bridge.js` 新增 `recordNativeRunnerPermissionDecision()`。
   - `native-desktop-bridge.js` 新增 `listNativeRunnerPermissionDecisions()`。
   - Web 模式下读取最近记录为空，不假装存在本机账本。

4. ProjectChat UI：
   - 本地运行侧栏“命令审批”卡新增最近审批记录列表。
   - 支持刷新原生审批记录。
   - 用户点击“批准一次 / 本会话批准 / 取消”时，会在发送终端输入前尝试写入原生账本。
   - 记录失败不会阻塞现有终端审批流程，但会给出提示。

5. 合约检查：
   - `src-tauri/check-tauri-shell.mjs` 已覆盖新增 Tauri command 和前端 bridge 方法。

### 当前仍未实现范围

- 未实现危险动作系统级弹窗。
- 未实现审批记录回传服务端任务树 / work-session / 审计事件。
- 未实现只读文件检索、目录列表和差异预览。
- 未实现写入类操作授权。
- 未实现 PTY 与 Codex/Hermes/Claude Code 的交互式会话。
- 未实现 Tauri 原生编译验证；当前机器仍缺少 Rust / Tauri CLI 时无法执行。

### 后续开发顺序

1. 在权限决策记录基础上接入只读文件检索、目录列表和差异预览。
2. 把权限记录回传到服务端任务树 / work-session / 审计事件。
3. 接入需要确认的写入类操作，所有写入必须先形成权限记录。
4. 最后接入 PTY 与 Codex/Hermes 交互式执行。

## 2026-06-08 Tauri 只读文件桥继续开发

### 本轮目标

在不接入写入、不扩大 Runner 命令权限的前提下，把桌面端工作区文件浏览从后端接口扩展到 Tauri 原生只读文件桥：

- Tauri 原生命令提供工作区目录列表。
- Tauri 原生命令提供 1MB 内文本文件读取。
- 前端 bridge 统一适配只读文件 API。
- ProjectChat 本地运行面板在桌面端优先使用原生只读文件桥。
- 桌面端文件编辑区明确进入只读预览状态，不显示可写假象。

### 已实现范围

1. Tauri 原生命令契约：
   - 新增 `list_workspace_files`。
   - 新增 `read_workspace_file`。
   - 请求必须携带 `workspacePath`，可选相对 `path`。
   - 路径解析后必须位于 workspace root 内，禁止越界读取。
   - 目录最多返回 500 条。
   - 文件超过 1MB 时不在侧栏直接读取。
   - 返回给前端的相对路径统一使用 `/`。

2. 前端桥接：
   - `native-desktop-bridge.js` 新增 `listNativeWorkspaceFiles()`。
   - `native-desktop-bridge.js` 新增 `readNativeWorkspaceFile()`。
   - Web 模式下不伪造原生文件能力。

3. ProjectChat UI：
   - 本地运行侧栏文件树在桌面端优先调用 Tauri 原生只读文件桥。
   - 非桌面端继续沿用现有服务端 `/workspace/files` 和 `/workspace/file` 接口。
   - 桌面端文件区展示“原生只读文件桥”提示。
   - 桌面端保存按钮显示为“只读”并禁用；文本区只读预览。

4. 合约检查：
   - `src-tauri/check-tauri-shell.mjs` 已覆盖新增只读文件 command 和前端 bridge 方法。

### 当前仍未实现范围

- 未实现 diff / 差异预览。
- 未实现文件写入授权流程。
- 未实现文件变更审计回传。
- 未实现服务端任务树 / work-session 联动。
- 未实现 PTY 与 Codex/Hermes/Claude Code 的交互式会话。
- 未实现 Tauri 原生编译验证；当前机器仍缺少 Rust / Tauri CLI 时无法执行。

### 后续开发顺序

1. 接入只读 diff / 差异预览。
2. 把权限记录和文件审计回传到服务端任务树 / work-session / 审计事件。
3. 接入需要确认的写入类操作，所有写入必须先形成权限记录。
4. 最后接入 PTY 与 Codex/Hermes 交互式执行。

## 2026-06-08 Tauri 只读差异预览继续开发

### 本轮目标

在只读文件桥基础上继续补齐工作区差异预览，但仍不接入写入、删除、提交或任意命令执行：

- Tauri 原生命令提供工作区或选中文件的 git diff 预览。
- 前端 bridge 统一适配 diff 预览 API。
- ProjectChat 本地运行面板展示 diff 状态、摘要和截断后的详细差异。
- 保持路径必须位于 workspace root 内。
- 保持命令不走 shell。

### 已实现范围

1. Tauri 原生命令契约：
   - 新增 `preview_workspace_diff`。
   - 内部只读取 `git status --short`、`git diff --stat`、`git diff`。
   - 使用结构化 git 参数和 `current_dir(workspace)`，不拼接 shell 字符串。
   - 可预览整个工作区；选中文件时预览该文件。
   - 输出包含 `available`、`summary`、`diff`、`status`、`exitCode`、`truncated`、`reason`。
   - `summary/status` 最多 8,000 字符，`diff` 最多 30,000 字符。

2. 前端桥接：
   - `native-desktop-bridge.js` 新增 `previewNativeWorkspaceDiff()`。
   - Web 模式下不伪造原生 diff 能力。

3. ProjectChat UI：
   - 本地运行侧栏文件区新增“差异预览”。
   - 未选中文件时预览整个工作区。
   - 选中文件后预览当前文件差异。
   - 显示 `未预览 / 读取中 / 无差异 / 已生成 / 已截断 / 不可用` 状态。
   - git 不可用、非 git 仓库或其他错误时显示原因。

4. 合约检查：
   - `src-tauri/check-tauri-shell.mjs` 已覆盖新增 diff command 和前端 bridge 方法。

### 当前仍未实现范围

- 未实现文件写入授权流程。
- 未实现文件变更审计回传。
- 未实现服务端任务树 / work-session 联动。
- 未实现危险动作系统级弹窗。
- 未实现 PTY 与 Codex/Hermes/Claude Code 的交互式会话。
- 未实现 Tauri 原生编译验证；当前机器仍缺少 Rust / Tauri CLI 时无法执行。

### 后续开发顺序

1. 把权限记录和文件审计回传到服务端任务树 / work-session / 审计事件。
2. 接入需要确认的写入类操作，所有写入必须先形成权限记录。
3. 接入危险动作系统级弹窗。
4. 最后接入 PTY 与 Codex/Hermes 交互式执行。

## 2026-06-08 桌面端审计事件回写继续开发

### 本轮目标

在不新增 Electron、不放开写入、不接入 PTY 的前提下，先把桌面端本机动作形成服务端可追踪记录：

- Runner 权限决定回写到项目 work-session。
- 工作区文件只读预览回写到项目 work-session。
- 工作区 diff 只读预览回写到项目 work-session。
- 回写内容只包含动作摘要、路径、状态和验证标记。
- 不上传文件正文，不上传完整 diff。

### 已实现范围

1. 服务端审计入口：
   - 新增 `POST /api/projects/{project_id}/chat/desktop-audit-events`。
   - 请求体使用 `ProjectDesktopAuditEventReq`。
   - 服务端复用既有 `work_session_store` 和 `WorkSessionEvent`。
   - `source_kind` 固定为 `desktop_audit`。
   - 如果前端没有现成 `session_id`，按 `project_id + chat_session_id` 生成稳定的 `desktop-audit-*` 会话 ID。
   - 不新增独立桌面审计存储，不写多份 fallback 状态。

2. 服务端记录边界：
   - `event_type`、`phase`、`step`、`status`、`content` 均做长度限制。
   - `facts`、`changed_files`、`verification`、`risks`、`next_steps` 做数量和单项长度限制。
   - 审计入口返回既有 work-session summary，便于前端刷新当前工作会话。

3. ProjectChat 前端回写：
   - 新增 `recordDesktopAuditEvent()`，统一补齐 `project_id`、`chat_session_id`、`task_tree_session_id`、`task_node_id` 和 `session_id`。
   - Runner 审批按钮写入本机权限账本后，静默回写 `desktop_runner_permission_decision`。
   - 桌面端只读文件预览成功后，静默回写 `desktop_workspace_file_read`。
   - 桌面端 diff 预览成功或失败后，静默回写 `desktop_workspace_diff_preview`。
   - 回写失败只在控制台记录，不阻塞用户当前桌面动作。

4. 数据最小化：
   - 文件预览只回传文件相对路径、字节数和截断状态。
   - diff 预览只回传目标路径、可用状态、截断状态、退出码和首条摘要。
   - Runner 审批只回传决定类型、工作区路径和审批提示标题。
   - 不把 `workspaceFileDraft`、文件内容、`diff` 正文或完整终端输出上传到审计接口。

### 当前仍未实现范围

- 未实现文件写入授权流程。
- 未实现危险动作系统级弹窗。
- 未实现真实任务树工具闭环；当前宿主未暴露 MCP 任务树工具，本轮只完成服务端 work-session 回写入口和本地记录。
- 未实现 PTY 与 Codex/Hermes/Claude Code 的交互式会话。
- 未实现 Tauri 原生编译验证；当前机器仍缺少 Rust / Tauri CLI 时无法执行。

### 后续开发顺序

1. 在现有审计回写基础上，接入写入前的危险动作确认模型，但先不执行写入。
2. 再实现受限文件写入命令，所有写入必须包含 diff 预览、用户确认和 work-session 审计事件。
3. 再接入系统级危险动作弹窗。
4. 最后接入 PTY 与 Codex/Hermes 交互式执行。

## 2026-06-08 Tauri 写入前确认模型继续开发

### 本轮目标

在不执行真实文件写入的前提下，先把桌面端写入前的风险确认链路打通：

- Tauri 原生命令只生成写入准备摘要。
- 前端 bridge 统一适配写入准备 API。
- ProjectChat 桌面端文件草稿可编辑，但点击按钮只进入“准备写入”流程。
- 用户确认或取消都记录到本机权限账本和服务端 work-session 审计。
- 当前阶段不调用 `fs::write`，不提交、不删除、不覆盖文件。

### 已实现范围

1. Tauri 原生命令契约：
   - 新增 `prepare_workspace_file_write`。
   - 输入为 `workspacePath`、相对 `path` 和草稿 `content`。
   - 路径父目录必须位于 workspace root 内。
   - 读取当前文件内容后计算 `currentSize`、`nextSize`、`currentLineCount`、`nextLineCount`、`changed`。
   - 返回 `riskLevel`、`requiresApproval`、`summary` 和 `reason`。
   - 只做准备和分类，不执行写入。

2. 前端桥接：
   - `native-desktop-bridge.js` 新增 `prepareNativeWorkspaceFileWrite()`。
   - 归一化写入准备结果，兼容 snake_case / camelCase 字段。
   - `src-tauri/check-tauri-shell.mjs` 已覆盖新增 command 和前端 bridge 方法。

3. ProjectChat UI 与流程：
   - 桌面端文件区允许编辑本地草稿。
   - 桌面端按钮由“只读”调整为“准备写入”。
   - 点击后弹出写入前确认，展示路径、大小变化、行数变化和风险级别。
   - 用户确认时写入本机权限账本：`workspace_file_write` / `approve_once`。
   - 用户取消时写入本机权限账本：`workspace_file_write` / `reject`。
   - 确认、取消或失败都会通过 `desktop_workspace_file_write_prepare` 回写服务端 work-session 审计事件。

### 当前仍未实现范围

- 未实现真实文件写入。
- 未实现写入后的自动 diff 验证和文件刷新。
- 未实现系统级危险动作弹窗。
- 未实现任务树工具闭环；当前宿主未暴露 MCP 任务树工具，本轮仍只维护本地 canonical 状态和服务端 work-session 审计入口。
- 未实现 PTY 与 Codex/Hermes/Claude Code 的交互式会话。
- 未实现 Tauri 原生编译验证；当前机器仍缺少 Rust / Tauri CLI 时无法执行。

### 后续开发顺序

1. 在 `prepare_workspace_file_write` 之后接入受限真实写入命令。
2. 真实写入必须要求：已有 diff 预览、用户确认、权限账本记录和 work-session 审计事件。
3. 写入后必须重新读取文件、刷新 diff，并把验证结果回写 work-session。
4. 再接入系统级危险动作弹窗。
5. 最后接入 PTY 与 Codex/Hermes 交互式执行。

## 2026-06-08 Tauri 启动与网页模式误判修复

### 本轮目标

定位用户执行 `npm run tauri:dev` 后仍提示“当前是网页模式”的原因，并补齐桌面端原生桥运行态判断。

### 定位结论

1. Rust / Cargo 已安装完成：
   - `cargo --version` 可用。
   - `rustc --version` 可用。
   - `cargo check` 已能在 `web-admin/frontend/src-tauri` 下通过。

2. `npm run tauri:dev` 已能启动桌面进程：
   - Vite dev server 监听 `http://127.0.0.1:3000`。
   - Tauri debug 二进制 `target/debug/ai-employee-factory-desktop` 已运行。

3. 仍显示网页模式的主要原因有两个：
   - 如果用户打开的是浏览器里的 `http://127.0.0.1:3000`，该页面本身就是网页模式；只有 Tauri 独立窗口才有原生桥。
   - 前端原生桥判断之前主要依赖 `@tauri-apps/api/core.isTauri()` 和 invoke 函数探测；当 Tauri 全局对象注入顺序稍晚，或只注入 `__TAURI__` / `__TAURI_INTERNALS__` 时，页面初始状态可能误判并停留在网页模式。

### 已实现修复

1. `native-desktop-bridge.js`：
   - 新增 `resolveNativeGlobal()`。
   - 原生桥判断同时识别 `globalThis.isTauri`、`globalThis.__TAURI__` 和 `globalThis.__TAURI_INTERNALS__`。
   - `resolveTauriInvoke()` 改为从 `globalThis` 解析 Tauri invoke，减少浏览器 / WebView 注入差异造成的误判。

2. `ProjectChat.vue`：
   - 页面挂载时立即刷新一次桌面运行时信息。
   - 页面挂载后 300ms 再刷新一次桌面运行时信息，避免 Tauri 注入稍晚导致状态卡停留在“网页模式”。

3. `src-tauri/check-tauri-shell.mjs`：
   - 合约检查新增 `__TAURI_INTERNALS__` 和 `resolveNativeGlobal`，防止后续回退到单一判断方式。

### 本轮验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `cd web-admin/frontend/src-tauri && cargo check` 通过。
- `git diff --check` 通过。

## 2026-06-08 AI 对话需求记录沉淀

### 本轮目标

外部 Agent 的目标是替代用户手动操作命令行，因此 AI 对话里的需求不能只停留在聊天历史。本轮把普通 AI 对话和 Tauri 外部 Agent 对话都写入项目需求记录，让项目详情页的“需求记录”能看到从对话发起、执行中、完成或阻塞的状态。

### 已实现范围

1. 后端 API：
   - 新增 `POST /projects/{project_id}/chat/requirement-record`。
   - 接收 `chat_session_id`、用户消息 ID、assistant 消息 ID、root goal、状态、最终摘要、Runner session id 和执行器类型。
   - 每轮用户消息生成独立需求记录键，同时保留原始 `source_chat_session_id`，避免同一聊天会话内多次需求互相覆盖。
   - 复用 `project_chat_task_store` 写入 `ProjectChatTaskSession`，并刷新项目需求记录缓存。

2. ProjectChat：
   - 普通项目 AI 对话发送后立即写入 `in_progress` 需求记录。
   - AI 对话完成后更新为 `done`，失败后更新为 `blocked`。
   - Tauri 外部 Agent Runner 启动后写入 `in_progress`，完成/取消/失败后更新为 `done / blocked`。
   - 需求记录写入失败只打印 warning，不阻塞用户发消息或 Runner UI。

3. 对话展示：
   - 外部 Agent 最终回答不再在正文里展示“运行诊断”折叠块。
   - 诊断信息保存在需求记录 `source_context` 和消息元数据里，供后续排查，不污染聊天正文。

### 当前边界

- 需求记录目前是按每轮用户消息沉淀为轻量 task session，还不是完整 MCP 任务树闭环。
- MCP resources 在当前执行环境未暴露，服务端任务树闭环未完成；本轮已维护本地 canonical 状态。
- Runner 仍是非 PTY 会话，交互式权限确认和流式输入仍需继续开发。

### 验证

- `web-admin/api/.venv/bin/python -m py_compile web-admin/api/routers/projects.py web-admin/api/models/requests.py` 通过。
- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。

### 当前操作提示

- 正确启动命令仍是：`cd web-admin/frontend && npm run tauri:dev`。
- 如果终端仍报 `cargo metadata ... No such file or directory`，说明那个终端没有加载 Rust PATH；重新开一个终端，或执行 `source ~/.cargo/env` 后再运行。
- 检测 Codex / Hermes 必须在 Tauri 打开的独立桌面窗口里点“检查环境”；浏览器标签页 `http://127.0.0.1:3000` 会继续显示网页模式，这是符合预期的边界。

## 2026-06-08 桌面端移除本地连接器同级选项

### 本轮目标

桌面主线已经切到 Tauri 原生桥后，项目聊天设置里的“本机执行环境”不应再要求用户选择“本地连接器”。本地连接器只保留为浏览器兼容模式入口。

### 已实现范围

1. 桌面端运行态：
   - `ProjectChat.vue` 中 `externalAgentConnectorRequired` 改为只在非 Tauri 桌面模式下要求 `local_connector_id`。
   - 运行位置显示为“桌面端原生桥”，不再在桌面端显示“本地连接器”。
   - 桌面端显示“本机运行方式”说明，明确不需要选择本地连接器。

2. 浏览器兼容态：
   - 非 Tauri 模式仍保留“本地连接器”选择、连接本机和刷新入口。
   - 相关提示统一改为“浏览器模式请先选择本地连接器”。

3. 工作区文案：
   - Tauri 桌面端字段显示“本机工作区”。
   - 浏览器兼容模式字段继续显示“连接器工作区”。

### 验证

- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Hermes one-shot 空终端修复

### 问题

Hermes 改用 `hermes -z <prompt>` 后，界面仍按 PTY 会话展示，运行终端长期为空，只显示“思考中 / Runner 运行中”。这会让用户误以为没有任何响应。

### 原因

`hermes -z/--oneshot` 是脚本模式，准确出口是结束时的 stdout 最终响应；它不是交互式 TUI，也不承诺运行中持续输出。继续把它挂在 PTY 上，会造成终端空白和输入控制键无效。

### 已修复

1. Tauri：
   - stdout final-output 执行器改走普通 pipe 子进程，不再挂 PTY。
   - 新增 `start_external_agent_pipe_session()`，捕获 stdout/stderr。
   - 新增 `spawn_external_agent_process_waiter()`，进程结束后在退出码为 0 时把 stdout 写入 `finalOutput`。
   - Runner cancel 同时支持 PTY child 和普通 process child。

2. ProjectChat：
   - 对不支持 stdin 的 one-shot Runner，运行状态文案改为“等待执行器返回最终响应”。
   - 终端空态文案改为“执行器输出”，不再误导为实时 PTY 输出。

### 验证

- `cd web-admin/frontend/src-tauri && cargo fmt --check` 通过。
- `cd web-admin/frontend/src-tauri && cargo check` 通过。
- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Hermes 最终回答准确出口修复

### 问题

用户在桌面端选择 Hermes 外部 Agent 后，AI 对话没有回答用户问题，只显示：

- `Runner 会话没有可恢复的本机进程句柄`
- `外部 Agent 没有返回可展示的最终回答`

这不是用户问题本身无法回答，而是最终回答提取链路有缺口。

### 根因

1. Codex CLI 支持 `--output-last-message`，Runner 可从临时文件读取最终回答。
2. Hermes 源码和本机 `hermes --help` 显示 `-z/--oneshot` 是脚本出口：只向 stdout 输出最终响应文本。
3. 原先前端只认 `finalOutput` / `final`，但 Hermes 的准确出口还没有被后端写入 `finalOutput`，导致聊天层拿不到答案。
4. Tauri dev 热更新、窗口重载或读取历史快照时，Rust 内存中的 child 句柄无法恢复，旧逻辑会把仍标记 running 的快照改成 failed，并在聊天正文显示“没有可恢复的本机进程句柄”。

### 已修复

1. Tauri：
   - Hermes 启动命令固定使用 `hermes -z <prompt>`，沿用 Hermes 官方 one-shot 输出契约。
   - Runner waiter 只在执行器声明 stdout 是最终回答、且退出码为 0 时，把 stdout/PTY 的完整输出写入 `final_output`。
   - Codex 仍使用 `--output-last-message` 文件，不受影响。

2. ProjectChat：
   - 最终回答只认后端 `finalOutput` 或 `final` 日志。
   - 前端不再通过终端日志正则或混杂输出推断 Hermes 答案。

### 验证

- `cd web-admin/frontend/src-tauri && cargo fmt --check` 通过。
- `cd web-admin/frontend/src-tauri && cargo check` 通过。
- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Runner PTY 运行终端详情

### 本轮目标

用户要求“直接做 PTY，不要过度”，并希望交互更友好。本轮不引入新的复杂终端依赖，在已有 `portable-pty` 会话基础上先补齐可用的运行终端详情：让用户能看到真实 PTY 输出、直接取消 Runner、发送常用控制键，并继续用 ElementEasyForm 承接结构化提示。

### 已实现范围

1. ProjectChat：
   - Runner 详情抽屉新增“运行终端”区域，合并展示 PTY / stdout / stdin / system / stderr 日志。
   - 终端输出自动过滤 Codex 内部 rollout / tokens 噪声，主回答仍只使用最终结果。
   - 详情内新增 `取消 Runner`，不需要回到设置页。
   - 终端区新增 Ctrl+C、回车、空格、上/下方向键，直接写入 PTY stdin。
   - 新输出到达时自动滚动到底部。

2. ElementEasyForm：
   - 保留上一轮确认、单选、多选、文本输入表单。
   - 表单无法识别时，仍可使用手动输入和控制键兜底。

3. 合约检查：
   - `check-tauri-shell.mjs` 增加运行终端文本、控制键发送和终端输出样式检查。

### 当前边界

- 当前是轻量终端日志视图，不是完整 xterm 渲染器；全屏 TUI、光标定位和复杂 ANSI 交互仍可能显示不完整。
- 权限确认仍是本机会话交互，尚未升级为系统级审批弹窗或服务端审计闭环。
- MCP 任务树工具本轮未暴露，任务树闭环未完成；继续维护本地 canonical 状态。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Runner ElementEasyForm 交互扩展

### 本轮目标

在 PTY 底座之上继续提升交互友好度：不只识别确认类提示，还要把常见单选、多选和文本输入提示转成 ElementEasyForm 表单，减少用户直接输入方向键、空格或 y/n 的机会。

### 已实现范围

1. ProjectChat：
   - Runner PTY 输出复用现有 `detectTerminalChoiceInteraction()` 解析逻辑。
   - 支持把常见终端选择题渲染为 ElementEasyForm 单选 / 多选表单。
   - 支持识别 `请输入`、`enter`、`input` 等文本输入提示，并渲染为 `ElInput`。
   - 提交单选时自动发送方向键与回车到 PTY。
   - 提交多选时自动按选中差异发送空格、方向键与回车到 PTY。
   - 确认类提示继续用 `继续 / 取消` 单选表单。

2. 交互发送：
   - 新增 `sendNativeExternalAgentInputContent()`，支持发送控制字符且可关闭自动换行。
   - 手动输入入口仍保留，表单识别失败时用户可兜底。

3. 合约检查：
   - `check-tauri-shell.mjs` 增加 Runner 表单交互、选择解析和 `ElInput` / `ElCheckboxGroup` 检查。

### 当前边界

- 选择题识别基于文本日志启发式规则，不等于完整终端 UI 解析。
- 全屏 TUI 仍建议后续接入 xterm 类终端组件。
- 权限确认还未升级为系统级弹窗或服务端审计审批流。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 对话消息跳转 Runner 详情

### 本轮目标

Runner 详情抽屉已经可用，但用户仍需要先进入本地运行页查找记录。本轮把 AI 对话中的外部 Agent 消息和本机 Runner session 关联起来，支持从消息操作直接打开运行详情。

### 已实现范围

1. ProjectChat：
   - 消息操作区新增“查看运行详情”动作。
   - 仅当消息能解析到 Tauri Runner session id 时展示该动作。
   - session id 支持从 `source_context`、operation id 和 operation meta 中解析。
   - 点击后调用现有 `getNativeExternalAgentSession()`，并打开 Runner 运行详情抽屉。

### 当前边界

- 该入口只对 Tauri 外部 Agent Runner 消息生效。
- 如果本机 app data 已被清理或不是同一台桌面端，详情读取会失败并提示。
- 仍未接入 PTY 输入和交互式权限确认。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Runner 运行详情抽屉

### 本轮目标

运行记录列表只能定位会话，还不能高效排查和复用结果。本轮新增 Runner 运行详情抽屉，把最终回答、stdout、stderr/system 诊断分区展示，并提供复制能力。

### 已实现范围

1. ProjectChat：
   - 点击“Runner 运行记录”后打开独立运行详情抽屉。
   - 抽屉展示 session id、执行器、状态、退出码、工作区和启动命令。
   - 日志分为最终回答、stdout、stderr/system 三块展示。
   - 支持复制最终回答。
   - 支持复制完整 Runner 日志。

2. 交互边界：
   - 详情抽屉只读取现有 Runner session snapshot，不改变进程执行状态。
   - 正在运行的 session 被打开后仍沿用现有轮询刷新。

### 当前边界

- 详情抽屉还没有从 AI 对话消息内直接跳转。
- 还没有 PTY 输入、交互式权限确认或运行中命令输入。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Runner 运行记录 UI

### 本轮目标

Runner 会话快照已经能落盘，下一步需要让用户在桌面端直接看到这些运行记录。本轮在“本地运行”侧栏增加 Runner 运行记录卡片，先提供列表、刷新和详情加载能力。

### 已实现范围

1. ProjectChat 本地运行侧栏：
   - 新增“Runner 运行记录”卡片。
   - 调用 `listNativeExternalAgentSessions()` 拉取最近 Runner 会话。
   - 展示会话摘要、执行器、状态、退出码、工作区尾部路径和更新时间。
   - 点击记录后调用 `getNativeExternalAgentSession()` 读取完整快照，并把日志加载到现有终端输出区。

2. 状态联动：
   - 进入本地运行面时自动刷新运行记录。
   - Runner 启动、完成、取消后静默刷新运行记录。
   - 正在运行的历史记录被选中后会继续轮询当前 session。

### 当前边界

- 运行详情仍复用现有终端输出区，还不是独立详情抽屉。
- 记录来自本机 Tauri app data，只代表当前桌面端本机运行历史。
- 当前仍未接入 PTY 输入和交互式权限确认。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Runner 会话快照持久化

### 本轮目标

Runner 会话不能只保存在 Tauri 进程内存里。第一阶段先把外部 Agent Runner 的会话快照和日志写入桌面端 app data 目录，使桌面端重启后仍可读取最近会话结果，为后续独立运行详情页和事件流打基础。

### 已实现范围

1. Tauri Runner：
   - `ExternalAgentSessionSnapshot` 支持序列化和反序列化。
   - Runner 会话启动、日志追加、取消、结束时写入 `external-agent-sessions/<session_id>.json`。
   - `get_external_agent_session` 在内存 miss 时会回读持久化快照。
   - 新增 `list_external_agent_sessions`，返回最近 Runner 会话快照，并用内存态覆盖同 ID 的落盘态。

2. 前端 bridge：
   - `native-desktop-bridge.js` 新增 `listNativeExternalAgentSessions()`。
   - Tauri 合约检查覆盖 `list_external_agent_sessions / listNativeExternalAgentSessions`。

### 当前边界

- 持久化的是会话快照和日志文本，不包含可恢复进程句柄；桌面端重启后只能查看历史状态，不能继续控制旧进程。
- 当前仍是非 PTY Runner，交互式权限提示和输入仍未接入。
- 暂未新增运行详情页 UI；本轮先收敛数据契约和本机持久化来源。

### 验证

- `cd web-admin/frontend/src-tauri && cargo fmt --check` 通过。
- `cd web-admin/frontend/src-tauri && cargo check` 通过。
- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Runner 对话展示收敛

### 本轮目标

修复外部 Agent 返回后主对话出现 `EXECUTION TRACE`、`进行中 / 已完成 1 项`、`展开`、`外部 Agent Runner 已完成` 等工程化文案的问题。AI 对话页应优先展示外部 Agent 的回答，运行细节只在需要排查时查看。

### 已实现范围

1. ProjectChat：
   - 外部 Agent Runner 运行中的 assistant 文案改为 `正在处理你的请求...`。
   - Runner 最终消息不再强制加“外部 Agent Runner 已完成 / 最终回答”包装，优先直接展示最终回答正文。
   - Runner operation 增加 `hide_in_message_process` 和 `source=tauri_external_agent_runner`。
   - 新旧 `native-external-agent:*` operation 默认不进入消息里的执行过程卡。
   - 历史持久化时也写入隐藏标记，避免刷新后重新展示执行轨迹。
   - 通用执行过程 eyebrow 从 `Execution Trace` 改为中文 `执行过程`。

### 当前边界

- Runner 运行诊断仍保留在最终消息的折叠区。
- 当前仍是非 PTY Runner，完整交互式执行详情应进入独立运行视图，而不是重新塞回 AI 对话页。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

### 当前边界

- 桌面端已经不需要本地连接器选项来做目录选择和 Codex / Hermes 检测。
- 交互式 Codex / Hermes 执行仍未完成；点击真正外部 Agent 执行时，桌面端会提示本地 Runner / PTY 尚未接入，而不是要求选择本地连接器。

## 2026-06-08 外部 Agent 选项对齐本机执行器检测

### 本轮目标

环境检测已能识别 Codex、Hermes 和 Claude Code，但“外部 Agent”下拉此前只稳定显示 Codex。本轮把外部 Agent 选项与本机执行器检测结果对齐。

### 已实现范围

1. 前端选项目录：
   - `ProjectChat.vue` 新增桌面外部 Agent 目录：`codex_cli`、`hermes`、`claude_code`。
   - 外部 Agent 下拉固定按 `Codex CLI / Hermes / Claude Code` 顺序展示。
   - 如果 Tauri 检测已返回版本，选项 label 会显示版本，例如 `Codex CLI · codex-cli 0.125.0`、`Hermes · Hermes Agent v0.15.1`、`Claude Code · 2.1.120 (Claude Code)`。
   - 选中 Hermes / Claude Code 后，状态卡标题和运行模型跟随当前选项，不再沿用 Codex 文案。

2. 后端返回目录：
   - `projects.py` 新增 `_EXTERNAL_AGENT_TYPE_CATALOG`。
   - 项目外部 Agent 信息返回 `codex_cli`、`hermes`、`claude_code` 三种 `agent_types`。
   - 继续保留 `external_agent_type` 白名单，允许三种类型进入项目设置。

3. 执行边界：
   - 桌面端当前仍不把 Hermes / Claude Code 静默映射成 Codex 执行。
   - 在本地 Runner / PTY 接入前，桌面端真正发起外部 Agent 执行会提示交互式 Runner 尚未完成。

### 验证

- `web-admin/api/.venv/bin/python -m py_compile web-admin/api/routers/projects.py` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `cd web-admin/frontend && npm run tauri:check` 通过。
- `git diff --check` 通过。

### 后续开发顺序

1. 接入 Tauri 本地 Runner / PTY 的会话模型。
2. 为 Codex、Hermes、Claude Code 分别定义启动命令、参数契约、日志解析和取消流程。
3. 将外部 Agent 的真实执行从旧本地连接器链路切换到桌面端 Runner。

## 2026-06-08 AI 对话页移除执行详情侧栏

### 本轮目标

AI 对话页保持专注，不再在主聊天区域常驻展示“执行详情”侧栏。执行进度、日志、文件、验证和权限信息后续应进入独立运行面板或设置区，而不是占用对话页面宽度。

### 已实现范围

1. `ProjectChat.vue`：
   - 移除 AI 对话页中的 `execution-detail-panel` 模板。
   - 移除执行详情 tabs：进度、日志、文件、验证、权限。
   - 移除执行详情专用样式和未使用的 `executionDetailActiveTab` / `executionDetailStatus*` 状态。
   - 普通对话页 `chat-workbench` 改为单列布局，让聊天区占满主区域。
   - 本地运行面板 `local-runner-panel` 保持不变，仍用于 Runner 自检、只读文件桥、diff 预览和写入准备。

### 验证

- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `cd web-admin/frontend && npm run tauri:check` 通过。
- `git diff --check` 通过。

### 当前边界

- 主 AI 对话页不再展示执行详情侧栏。
- 执行状态 chip、设置页本机执行环境卡和本地运行面板仍保留。
- 后续若需要完整执行详情，应迁移到独立运行视图，而不是恢复到 AI 对话页常驻侧栏。

## 2026-06-08 外部 Agent 启动计划能力

### 本轮目标

在接入真实交互式 PTY 之前，先让 Tauri 桌面端能够为 Codex / Hermes / Claude Code 生成启动前计划，明确命令、工作区、安装状态、风险级别和是否需要审批，但不创建进程。

### 已实现范围

1. Tauri 原生命令：
   - 新增 `prepare_external_agent_launch`。
   - 输入 `agentType`、`workspacePath` 和可选 `prompt`。
   - 支持 `codex_cli`、`hermes`、`claude_code` 三种类型。
   - 校验工作区必须存在且为目录。
   - 通过 `--version` 检测对应可执行文件。
   - 返回命令、参数、工作区、版本、阻塞原因、风险级别、是否需要审批和摘要。
   - 当前只生成计划，不启动进程。

2. 前端 bridge：
   - `native-desktop-bridge.js` 新增 `prepareNativeExternalAgentLaunch()`。
   - 统一归一化 snake_case / camelCase 返回字段。

3. ProjectChat 设置页：
   - 启动计划只作为内部预检能力保留。
   - 用户主操作不再展示独立“启动计划”按钮，避免误解为真实可执行验证。
   - 真实可用性以后续“试运行”或完整 Runner 会话为准。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend/src-tauri && cargo check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Runner 任务包接入附件与 slash command

### 本轮目标

上一轮已经为桌面端外部 Agent 增加任务包，但 Runner 分支在发送流程中过早返回，仍会绕过附件文本提取、slash command 解析、创作辅助 prompt 和模型模式指令。本轮把 Tauri Runner 启动点移动到完整 `finalUserPrompt` 构造之后。

### 已实现范围

1. ProjectChat：
   - `startNativeExternalAgentSession()` 支持 `displayPrompt` 与 `executionPrompt` 分离。
   - AI 对话中展示 `displayPrompt`，Runner 实际执行 `executionPrompt`。
   - Tauri 桌面端外部 Agent 分支移动到附件、slash command、辅助 prompt、工具策略和模型生成指令构造之后。
   - Runner 任务包新增附件名和 slash command 类型。
   - requirement `source_context` 记录 `attachment_names` 与 `slash_command`，便于回查。

2. 行为收敛：
   - 纯文本、附件文本、`/stats`、`/form-json`、创作辅助等会统一进入 Runner 任务包。
   - 页面用户消息仍保留用户实际输入或 slash command 原文，不展示内部执行 prompt。
   - 浏览器模式仍沿用原本 local connector / WebSocket 外部 Agent 链路。

3. 合约检查：
   - `check-tauri-shell.mjs` 新增 `displayPrompt`、`executionPrompt`、`slashCommandKind`、`attachmentNames` 检查。

### 当前边界

- 图片附件仍只在普通 WebSocket 对话里以 base64 进入模型；Tauri Runner 当前只收到附件名和已提取的文本附件内容。
- `/run`、`/lark-cli` 这类依赖工具链的 slash command 会进入外部 Agent prompt，但桌面端 Runner 仍不会自动接管完整工具调用协议。
- 当前仍未接入 PTY 交互输入和权限确认。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 Runner 非 PTY stdin 输入

### 本轮目标

完整 PTY 还未接入，但部分外部 Agent CLI 会在运行中等待简单输入或确认。本轮先实现非 PTY stdin 过渡能力：保留子进程 stdin 句柄，允许桌面端向运行中的 Runner 会话发送一行输入。

### 已实现范围

1. Tauri Runner：
   - `ExternalAgentSessionState` 保留 `ChildStdin`。
   - `ExternalAgentSessionSnapshot` 新增 `stdinOpen`。
   - `start_external_agent_session` 改为 `stdin(Stdio::piped())`。
   - 新增 `write_external_agent_session_input` 命令。
   - 写入 stdin 后追加 `stdin` 日志并落盘 session snapshot。
   - 会话结束或取消时关闭 stdin 句柄。

2. 前端 bridge：
   - `native-desktop-bridge.js` 新增 `writeNativeExternalAgentSessionInput()`。
   - session snapshot 归一化新增 `stdinOpen`。

3. ProjectChat：
   - Runner 运行详情抽屉在 `stdinOpen` 且会话运行中时显示输入框。
   - 设置页 Runner 状态卡同样提供发送输入入口。
   - 发送内容后刷新 session snapshot，并把 `stdin` 日志显示在诊断区。

### 当前边界

- 这仍不是 PTY：无法处理光标控制、全屏 TUI、复杂多选菜单或交互式权限 UI。
- 当前只支持发送文本并自动追加换行。
- 权限确认仍未接入系统弹窗或结构化审批流。

## 2026-06-08 Runner PTY 底座接入

### 本轮目标

用户明确要求“直接做 PTY，不要过度”。本轮把外部 Agent Runner 从普通 pipe 子进程切到 `portable-pty`，让 Codex / Hermes / Claude Code 在真实伪终端里运行，为后续 ElementEasyForm 结构化交互打底。

### 已实现范围

1. Tauri Runner：
   - 新增 `portable-pty` 依赖。
   - `start_external_agent_session` 使用 `native_pty_system().openpty()` 创建 PTY。
   - 外部 Agent 命令通过 PTY slave 启动。
   - PTY master reader 统一采集输出，日志 stream 标记为 `pty`。
   - PTY master writer 作为 session stdin，继续复用 `write_external_agent_session_input` 写入。
   - waiter 线程等待 PTY child 退出并回收 session 状态。

2. ProjectChat：
   - PTY 输出纳入最终 stdout fallback 展示。
   - 现有 Runner 输入框直接写入 PTY，而不是普通 stdin pipe。
   - 增加 Runner 确认类提示识别，发现 `(y/n)`、`yes/no`、`是否继续`、`proceed` 等提示时，在运行详情中显示 ElementEasyForm 单选表单。
   - 表单提交后写入 `y` / `n` 到 PTY；也允许切回手动输入。

3. ElementEasyForm 方向：
   - 当前项目已经接入 `element-easy-form`，并且 ProjectChat 已有终端结构化交互模型。
   - 本轮先接确认类提示；后续继续扩展选择、多选和自由文本输入类 schema。

### 当前边界

- 当前只识别确认类提示，复杂选择、多选和自由文本输入还未结构化。
- 复杂全屏 TUI 可以运行在 PTY 内，但当前前端还不是完整终端模拟器，只展示文本日志、确认表单和单行输入。
- 权限确认仍未接入系统弹窗或结构化审批流。

### 验证

- `cd web-admin/frontend/src-tauri && cargo fmt --check` 通过。
- `cd web-admin/frontend/src-tauri && cargo check` 通过。
- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend/src-tauri && cargo fmt --check` 通过。
- `cd web-admin/frontend/src-tauri && cargo check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

### 当前边界

- 启动计划不等于真实执行，不创建 Codex / Hermes / Claude Code 进程。
- Codex 当前计划命令为 `codex exec --sandbox workspace-write`；Hermes / Claude Code 暂只生成基础命令，后续要补各自参数契约。
- 下一步应接入 PTY 会话、日志流、取消流程和权限确认。

## 2026-06-08 外部 Agent 任务包契约

### 本轮目标

修复桌面端外部 Agent Runner 只拿到用户短句，导致 Codex / Hermes / Claude Code 输出“我在，请继续说明”这类待命话术的问题。Runner 启动时应收到清晰的任务包，AI 对话里仍只展示用户原始消息。

### 已实现范围

1. ProjectChat：
   - 新增 `buildNativeExternalAgentTaskPrompt()`。
   - Runner 启动前把用户原始输入包装为外部 Agent 任务包。
   - 任务包包含项目、`project_id`、`chat_session_id`、本机工作区、外部 Agent 类型、选中员工和最近对话摘要。
   - 任务包明确要求外部 Agent 直接处理“用户本次任务”，不要只回复待命话术。
   - 任务包明确最终回答只输出用户可读结论、关键改动、验证结果和剩余风险，不输出 tokens、rollout、内部诊断或原始日志。

2. 对话与记录：
   - AI 对话中的 user message 继续保留用户原始输入，不展示包装后的长 prompt。
   - requirement 记录的 `source_context` 增加 `task_prompt_preview`，便于排查 Runner 实际收到的任务包。
   - Runner 原生命令仍只接收一个 prompt 参数，不走 shell，不开放任意命令字符串。

3. 合约检查：
   - `check-tauri-shell.mjs` 新增 ProjectChat 任务包契约检查，覆盖任务包函数、用户任务段落和启动时传入 `taskPrompt`。

### 当前边界

- 当前仍是非 PTY Runner，不能处理 CLI 运行中的交互式输入和权限确认。
- 附件和 slash command 仍未统一进入 Tauri Runner 任务包；本轮先覆盖纯文本 AI 对话任务。
- Hermes / Claude Code 的最终回答捕获仍主要依赖 stdout fallback。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-08 外部 Agent 一次性试运行

### 本轮目标

在完整 PTY 会话之前，先把桌面端外部 Agent 的用户入口收敛为“本地诊断”：验证 Codex / Hermes / Claude Code 的命令、版本和工作区 cwd，不触发模型调用，避免把网络、登录态或模型响应慢误判为桌面端不可用。

### 已实现范围

1. Tauri 原生命令：
   - 新增 `run_external_agent_once`。
   - 不接受任意 shell 字符串，不走 shell。
   - 根据 `agentType` 固定生成命令：
     - Codex CLI：`codex exec --sandbox workspace-write <prompt>`。
     - Hermes：`hermes -z <prompt>`。
     - Claude Code：`claude --print <prompt>`。
   - 工作目录固定为用户选择的本机工作区。
   - 默认 60 秒超时，可在 5 秒到 180 秒内限制。
   - stdout / stderr 分别截断，避免一次性输出撑爆前端。
   - 子进程输出用后台线程读取，避免管道阻塞。

2. 前端 bridge：
   - `native-desktop-bridge.js` 新增 `runNativeExternalAgentOnce()`。
   - 合约检查补充 `run_external_agent_once` / `runNativeExternalAgentOnce`。

3. ProjectChat 设置页：
   - 本机执行环境卡保留“本地诊断”按钮，不再把“启动计划”作为显眼用户操作。
   - 本地诊断内部先做启动预检，再执行 `<agent> --version` 和 `git status --short`。
   - 本地诊断不调用 `codex exec` / `hermes -z` / `claude --print`，不会触发模型请求。
   - 诊断结果展示 exit code、耗时、stdout、stderr、阻塞原因。
   - 诊断结果写入本机 Runner 权限记录，并通过桌面审计事件回写摘要。

### 当前边界

- 这仍然不是主 AI 对话流里的外部 Agent 执行。
- 当前没有 PTY、流式日志、取消按钮、交互式权限提示接管。
- `run_external_agent_once` 底层能力仍存在，但当前 UI 不直接触发模型型试运行；真实执行前仍需要更完整的权限模型和可取消会话。
- 主对话页继续不展示“执行详情”侧栏；后续完整执行详情应进入独立运行视图或本地运行面板。

### 后续开发顺序

1. 为 `run_external_agent_once` 增加更严格的审批令牌或本机权限记录校验。
2. 接入可取消的进程句柄和运行中状态。
3. 接入 PTY / 流式日志，把 Codex / Hermes / Claude Code 的真实执行从服务端旧链路迁移到桌面端 Runner。

## 2026-06-08 外部 Agent Runner 会话第一版

### 本轮目标

去掉没有真实执行价值的“本地诊断”入口，开始接真实外部 Agent 执行链路。第一版先做后台 Runner 会话、stdout/stderr 日志轮询、取消按钮和最终状态回收；暂不宣称完整 PTY。

### 已实现范围

1. Tauri 原生命令：
   - 新增 `start_external_agent_session`。
   - 新增 `get_external_agent_session`。
   - 新增 `cancel_external_agent_session`。
   - 使用进程句柄保存在内存 session store 中。
   - stdout / stderr 后台线程持续采集到 session logs。
   - waiter 线程等待进程退出并更新 `completed / failed / cancelled` 状态。
   - 取消会 kill 当前本机进程。

2. 前端 bridge：
   - 新增 `startNativeExternalAgentSession()`。
   - 新增 `getNativeExternalAgentSession()`。
   - 新增 `cancelNativeExternalAgentSession()`。
   - 统一归一化 session snapshot 和增量 logs。

3. ProjectChat 设置页：
   - 移除“本地诊断”按钮。
   - 新增“启动 Runner”按钮。
   - Runner 会使用当前输入框内容作为外部 Agent prompt。
   - 会话运行时展示 stdout / stderr 日志。
   - 会话运行中显示“取消”按钮。
   - 启动事件写入本机权限记录和桌面审计摘要。

### 当前边界

- 当前是非交互进程会话，不是完整 PTY。
- 还没有把最终结果自动写回主对话消息。
- 还没有处理 CLI 内部交互式权限提示，只能通过 stdout/stderr 展示出来。
- session store 当前在 Tauri 进程内存中，重启桌面端后会话状态会丢失。

### 后续开发顺序

1. 把 Runner 最终 stdout/stderr 摘要回写到运行面板或对话消息。
2. 接入 PTY，支持交互式权限提示和输入。
3. 增加更明确的权限审批令牌，避免未确认 prompt 直接启动 Agent。
4. 增加会话持久化和重启恢复。

## 2026-06-08 Runner 会话结果回写主对话

### 本轮目标

Runner 会话不能只停留在设置卡里看日志。本轮把外部 Agent Runner 的启动、运行状态和最终 stdout/stderr 摘要回写到主对话消息里，让用户能在对话流中看到这次执行的结果。

### 已实现范围

1. ProjectChat：
   - 启动 Runner 成功后，自动在主对话追加用户任务消息和 assistant 运行消息。
   - 保存当前 Runner 对应的 assistant message id。
   - 轮询到增量 logs 时，同步更新该 assistant 消息的 operation。
   - Runner 结束、失败或取消后，更新同一条 assistant 消息为最终结果。
   - 最终结果包含执行器、状态、退出码和 stdout/stderr 摘要。

2. 取消体验：
   - 点击取消后先乐观更新为 `cancelling`。
   - 继续轮询直到 Tauri waiter 回收为 `cancelled / failed / completed`。
   - 最终状态也会写回主对话消息。

### 当前边界

- 主对话回写目前是前端本地消息，尚未持久化到后端聊天历史。
- stdout/stderr 摘要会截断，完整日志仍以 Runner 会话内存 logs 为准。
- 仍未接入完整 PTY 和交互式权限提示输入。

### 后续开发顺序

1. 将 Runner 最终消息持久化到后端聊天历史。
2. 把 Runner session id 与 work-session / task tree 节点建立正式关联。
3. 接入 PTY 输入，处理 Codex / Hermes / Claude 的权限提示。

## 2026-06-08 Runner 最终消息持久化

### 本轮目标

Runner 最终结果不能只存在前端内存里。本轮新增后端历史追加接口，并在 Runner 结束后把用户任务和 assistant 最终结果写入当前项目 chat session。

### 已实现范围

1. 后端 API：
   - 新增 `POST /projects/{project_id}/chat/history/messages`。
   - 只允许当前项目当前用户追加 `user / assistant / system` 消息。
   - 要求 `chat_session_id` 和非空 `content`。
   - 复用 `project_chat_store.append_message` 写入 JSON / PostgreSQL 存储。
   - `source_context` 保留 Runner session id、执行器类型、状态、退出码和 operations。

2. 前端：
   - Runner 完成、失败或取消后，持久化对应用户任务消息。
   - 持久化 assistant 最终结果消息。
   - 按 Runner session id 去重，避免重复轮询导致重复写入。
   - 持久化失败只记录 warning，不阻塞当前 UI 展示。

### 当前边界

- 运行中日志仍是前端轮询内存态，只有最终摘要持久化。
- 后端当前是 append-only，不做已有本地消息的 update；因此只在最终态写入。
- 还未把 Runner session id 绑定到 task tree 节点。

### 后续开发顺序

1. 将 Runner session id 与 work-session / task tree 节点绑定。
2. 为运行中日志增加可持久化事件流或运行记录详情页。
3. 接入 PTY 交互输入。

## 2026-06-08 Runner 输出归一化与 Codex 最终回答捕获

### 本轮目标

修复外部 Agent Runner 返回内容里混入 Codex CLI stderr、tokens used、rollout 记录错误和重复入口话术的问题。用户在 AI 对话流里应优先看到外部 Agent 的最终回答，而不是原始进程诊断。

### 已实现范围

1. Tauri Runner：
   - Codex CLI 启动参数新增 `--color never`，减少终端控制字符干扰。
   - Codex CLI 启动参数新增 `--ephemeral`，减少对本机 Codex 会话持久化的依赖。
   - Codex CLI 启动参数新增 `--output-last-message <tmp-file>`，由 Tauri waiter 在进程结束后读取最终回答。
   - `ExternalAgentSessionSnapshot` 新增 `finalOutput` 字段。
   - Tauri waiter 读取最终回答后删除临时文件，并把最终回答作为 `final` 日志写入 session logs。

2. 前端 bridge：
   - `native-desktop-bridge.js` 归一化 `finalOutput / final_output`。
   - Tauri 合约检查覆盖 `--output-last-message`、`--ephemeral` 和 `finalOutput`。

3. ProjectChat：
   - Runner 最终消息优先展示 `finalOutput`。
   - stdout 只作为 fallback。
   - stderr 中的 Codex 内部诊断、`tokens used`、`failed to record rollout items` 和 `codex_core::session` 错误不再作为主输出展示。
   - 原始运行信息保留在折叠的“运行诊断”里，便于排查但不干扰对话结果。

### 当前边界

- 当前仍是非 PTY Runner，会话不能处理 CLI 运行中的交互式输入。
- `--output-last-message` 当前只对 Codex CLI 生效；Hermes / Claude Code 仍依赖 stdout fallback。
- 如果外部 Agent 自身只输出入口待命话术，前端只能如实展示最终回答，后续需要继续完善 prompt 包装和会话契约。

### 验证

- `cd web-admin/frontend && npm run tauri:check` 通过。
- `cd web-admin/frontend/src-tauri && cargo fmt --check` 通过。
- `cd web-admin/frontend/src-tauri && cargo check` 通过。
- `cd web-admin/frontend && npm run build` 通过；仍保留既有 `mockjs eval` 与大 chunk 警告。
- `git diff --check` 通过。

## 2026-06-09 Runner 执行终端与过程详情设计修复

### 本轮目标

修复计划文档中的一个交互设计缺口：

早期方案要求在 AI 对话页右侧常驻“执行详情”侧栏，后续又明确移除了该侧栏，让主对话保持专注。但移除后没有补齐新的承载位置，导致 Runner / Codex / Hermes / Claude Code 的执行过程细节到底展示在哪里不够明确。

本轮设计修复的目标是：

- 主 AI 对话页继续保持单列、轻量、面向用户结论。
- 执行过程细节进入独立运行视图、Runner 详情抽屉或本地运行面板。
- 前端可以像命令终端一样展示实时执行过程，但不把原始终端噪音塞回普通聊天流。
- 开发者和高级用户可以追溯命令、日志、文件、权限和验证证据。
- 普通用户仍然只需要看主对话里的最终回答和必要确认。

### 设计结论

执行过程详情采用“三层展示”：

```text
主 AI 对话
  只展示用户目标、运行中摘要、关键确认、最终回答和“查看运行详情”入口

Runner 运行详情
  展示一次 Runner 会话的命令、状态、终端输出、输入、最终回答和诊断日志

本地运行面板 / 独立运行视图
  汇总 Runner 会话列表、权限记录、文件预览、diff、验证和审计事件
```

不再恢复 AI 对话页右侧常驻执行详情侧栏。

如果后续需要长期展示执行细节，应优先做独立运行视图，例如：

```text
/projects/:projectId/runs
/projects/:projectId/runs/:runnerSessionId
```

桌面端也可以把该视图作为一个独立窗口或工作台面板打开。

### 主 AI 对话页规则

主 AI 对话页只承担“目标与结论”：

- 用户发送的原始目标进入消息流。
- Runner 启动后显示短状态，例如 `正在由 Codex CLI 执行...`。
- Runner 运行中不展开 stdout / stderr / PTY 原始日志。
- Runner 结束后优先展示 `finalOutput` 或归一化后的最终回答。
- 失败时展示可读原因和下一步，而不是完整堆栈。
- 消息操作区提供 `查看运行详情`。
- 消息元数据必须保留 `runner_session_id`、`runner_agent_type`、`workspace_path`、`chat_session_id`、`task_node_id`。

主对话中禁止长期展示：

- 大段 PTY 原始输出。
- Codex tokens、rollout、内部诊断。
- 重复的执行过程卡。
- 文件 diff 正文。
- 权限账本列表。

这些内容必须进入 Runner 运行详情或本地运行面板。

### Runner 运行详情

Runner 运行详情是一次执行的核心展示面，形态可以是抽屉、独立页或桌面端窗口。

推荐结构：

```text
顶部摘要
  执行器：Codex CLI / Hermes / Claude Code
  状态：pending / running / waiting_input / completed / failed / cancelled
  工作区：当前本机路径
  命令：结构化 command + args
  开始时间 / 结束时间 / 耗时
  操作：取消 / 复制最终回答 / 复制完整日志 / 打开工作区

主体 tabs
  终端
  最终回答
  文件
  验证
  权限
  诊断
```

`终端`：

- 展示 PTY / stdout / stderr / stdin / system 日志。
- 默认自动滚动到底部。
- 支持暂停自动滚动。
- 支持复制选中内容和复制全部日志。
- 运行中支持输入框和快捷控制键：Ctrl+C、Enter、Space、方向键。
- 终端输出应保留 ANSI 文本；轻量模式可先做文本化展示，完整模式再接 xterm。

`最终回答`：

- 优先读取 Runner session 的 `finalOutput`。
- Codex 优先使用 `--output-last-message` 结果。
- Hermes one-shot 使用 stdout 作为最终回答。
- Claude Code 使用 stdout 或其后续明确的最终回答出口。
- 若没有最终回答，显示失败原因和诊断入口。

`文件`：

- 展示本次运行关联的文件读取、diff 预览、写入准备和后续真实写入记录。
- 文件正文和 diff 默认不上传服务端，只在本机视图展示。
- 服务端审计只记录路径、大小、状态、截断标记和摘要。

`验证`：

- 展示本次 Runner 触发或建议的验证命令。
- 展示命令退出码、摘要和是否通过。
- 验证结果需要能回写到 work-session / requirement / task tree。

`权限`：

- 展示本次会话中的权限请求。
- 展示用户决策：批准一次、本会话批准、拒绝。
- 展示风险级别、命令、路径、来源和时间。
- 高风险动作必须在执行前确认，不能只事后记录。

`诊断`：

- 展示原始 stderr、系统事件、进程状态、截断说明、恢复失败原因。
- 默认折叠，避免普通用户误读。

### 轻量终端与完整终端

实现分两级。

第一阶段使用轻量终端：

```text
PTY / stdout / stderr logs
  -> 前端增量轮询或事件推送
  -> 虚拟列表 / pre 文本展示
  -> 输入框 + 控制键按钮
```

适用范围：

- 展示 Codex / Hermes / Claude Code 运行过程。
- 展示确认提示和简单选择题。
- 展示 stdout / stderr / finalOutput。
- 支持取消、输入、复制日志。

第二阶段再接完整终端：

```text
Tauri portable-pty
  -> 二进制/字节流事件
  -> @xterm/xterm
  -> fit addon / search addon / clipboard
```

适用范围：

- 全屏 TUI。
- 复杂 ANSI、光标定位、进度条、选择菜单。
- 更接近真实命令终端的交互体验。

选择标准：

- 如果目标是让用户看清 AI 做了什么，轻量终端优先。
- 如果目标是完整复刻命令行交互，接入 xterm。
- 接入 xterm 前必须保证 Web / Docker 构建仍然可用，桌面能力不能反向污染普通网页模式。

### 数据流设计

Runner 会话数据以 `runner_session_id` 为主键。

```text
Tauri Runner
  -> session snapshot
  -> incremental logs
  -> finalOutput
  -> permission records
  -> workspace file / diff metadata

前端 ProjectChat
  -> 主对话消息只保存摘要和 runner_session_id
  -> Runner 详情按 runner_session_id 拉取本机 snapshot
  -> 运行结束后追加最终消息到聊天历史

服务端
  -> chat history 保存用户可读消息
  -> requirement record 保存需求状态
  -> work-session 保存审计摘要
  -> task tree 保存节点进度和验证结果
```

刷新恢复规则：

- 如果 Runner 仍在运行，前端恢复轮询并保持运行状态。
- 如果 Runner 已完成，前端展示最终回答和历史日志。
- 如果 Tauri 进程重启导致进程句柄丢失，只允许查看快照，不假装还能继续控制旧进程。
- `cancelled`、`failed`、`completed` 都不是运行态，刷新后不能显示“思考中”或禁用发送按钮。

### 审计与隐私边界

默认不上传：

- 文件正文。
- 完整 diff。
- 完整 PTY 原始日志。
- 用户本机绝对路径下的敏感片段。

默认上传或记录：

- Runner session id。
- 执行器类型。
- 状态、退出码和耗时。
- 操作摘要。
- 文件相对路径、大小、截断状态。
- 权限决策摘要。
- 验证命令和结果摘要。

如果后续要上传完整日志或 diff，必须增加单独开关和明确提示。

### 权限交互规则

Runner 终端展示不能绕过权限模型。

- 只读命令可以直接展示结果。
- 写入、删除、安装、提交、部署、发布必须先进入权限确认。
- 权限确认同时写入本机权限账本和服务端 work-session 审计摘要。
- 终端中出现 CLI 自带确认提示时，前端可以用结构化表单辅助输入，但不能替代系统级高风险审批。
- 用户拒绝后，Runner 详情要记录拒绝原因，并把主对话状态更新为 blocked 或 cancelled。

### 实施顺序

1. 收敛 Runner 详情抽屉信息架构：
   - 顶部摘要。
   - 终端 / 最终回答 / 文件 / 验证 / 权限 / 诊断 tabs。
   - `查看运行详情` 从消息操作区进入。

2. 完善轻量终端：
   - 增量日志列表。
   - 自动滚动和暂停滚动。
   - 输入框与控制键。
   - 复制最终回答和完整日志。

3. 绑定执行证据：
   - 文件读取、diff、写入准备进入 `文件` tab。
   - Runner 自检和验证命令进入 `验证` tab。
   - 权限记录进入 `权限` tab。

4. 打通服务端追踪：
   - Runner session id 关联 requirement record。
   - Runner 结束后写入 chat history。
   - 权限和验证摘要回写 work-session。
   - task tree 节点写入当前状态和验证结果。

5. 再评估 xterm：
   - 只有轻量终端无法满足复杂 TUI 时再接入。
   - xterm 作为增强渲染层，不改变 Runner session、权限和审计数据模型。

### 验收标准

- 普通用户在主 AI 对话页只看到清晰的运行状态和最终回答。
- 点击 `查看运行详情` 后，可以看到完整执行过程。
- Runner 详情能实时展示 PTY / stdout / stderr / stdin / system 日志。
- 运行中可以取消 Runner，并能看到取消后的最终状态。
- 需要输入时，可以在详情页发送文本或控制键。
- Codex 最终回答优先展示 `finalOutput`，不会把 tokens、rollout 或内部诊断当成主回答。
- Hermes one-shot 的 stdout 能作为最终回答展示。
- 刷新后运行态、完成态、取消态恢复正确。
- 文件、验证、权限和诊断信息有明确归属，不再散落在聊天正文里。
- Web / Docker 构建不依赖 Tauri 原生能力；网页模式只能查看服务端已有摘要，不假装拥有本机 Runner。

### 当前文档修复结论

本节修正了“执行详情侧栏移除后缺少最终承载位置”的设计 bug。

最终方向是：

```text
AI 对话页负责目标和结论。
Runner 运行详情负责终端过程。
本地运行面板或独立运行视图负责会话历史、文件、验证、权限和诊断。
```

后续实现不应恢复 AI 对话页常驻执行详情侧栏，而应沿这个结构推进。
