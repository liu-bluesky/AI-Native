# 模块代码规范与 ProjectChat 拆分计划

## 背景

`web-admin/frontend/src/views/projects/ProjectChat.vue` 初始约 36,107 行，当前约 23,096 行：

- `<template>` 起始于第 1 行，`<script setup>` 起始于第 4,719 行。
- `<style scoped>` 已迁为多个外部 scoped style 引用，当前页面底部引用 `project-chat-style-01.css` 到 `project-chat-style-15.css`。
- `script setup` 内集中承载了项目选择、会话列表、消息渲染、WebSocket、任务树、外部 Agent、终端交互、工作区文件、素材保存、员工草稿、技能资源、设置中心、代码预览等职责。
- 文件内存在大量顶层状态、计算属性、监听器和函数，已经不适合作为单页继续扩展。

本计划的目标不是一次性重写页面，而是建立模块边界和准入规则，让后续功能无法再自然堆回一个几万行 SFC。

## 当前执行快照

更新时间：2026-06-10。

- `ProjectChat.vue` 当前约 23,096 行，仍是路由页和大量业务逻辑混合状态。
- `src/modules/project-chat/` 下已有 62 个拆分文件，包含组件、composable、service、mapper、constants 和 styles。
- 已完成文件规模规则调整：固定行数不再作为拆分硬门槛，`check:file-size` 只做已登记大文件的回涨检查。
- 已迁出部分消息、会话、输入区、任务树面板、任务树恢复提示与节点草稿 mapper、技能资源弹窗、代码预览、终端审批弹窗、mapper、storage、markdown 和样式文件。
- `services/projectChatWsProtocol.js` 已承接部分 WebSocket 事件归一化、后台操作事件分类、done/guard 状态归一化和 operation payload 构造；`composables/useProjectChatPendingRequests.js` 已承接 pending request Map、当前活动请求 ID 与按会话查询逻辑；pending request 的消息行副作用、设置中心、native agent、terminal、workspace file 等核心逻辑仍大量留在 `ProjectChat.vue`。
- `composables/useProjectChatTaskTreeActions.js` 已承接任务树加载、恢复、删除、节点保存和工作轨迹同步编排；`services/projectChatWorkspaceApi.js` 已承接工作区文件 Web API 边界；`services/projectChatSettingsApi.js` 已承接设置中心 providers/settings API 边界；`services/projectChatEmployeeDraftApi.js` 和 `services/projectChatMaterialsApi.js` 已承接员工草稿与素材保存 API 边界。
- 后续重构必须优先保持 UI/CSS 不漂移；组件或样式迁移前先确认类名、DOM 结构和 scoped 行为。

## 总原则

1. 页面文件只负责路由级编排，不承载业务细节。
2. 单个模块只对一个业务对象负责，例如会话、消息、设置、任务树、外部 Agent 或工作区文件。
3. UI、状态、接口、数据转换、浏览器存储、协议解析分层放置。
4. 每次新增功能必须先选择归属模块；没有归属模块时先建模块，再写功能。
5. 大文件治理按增量迁移推进，迁移期间保证行为不变，避免混合重构和新需求开发。

## 文件规模治理信号

文件行数只作为可读性和职责边界的观察信号，不作为固定硬上限。是否继续拆分必须先看职责是否混杂、数据流是否过深、是否难以验证、是否出现跨模块循环依赖，以及是否会导致 UI/CSS 行为漂移。

| 文件类型 | 建议观察点 | 处理方式 |
| --- | --- | --- |
| 路由级 `views/*.vue` | 是否继续承载业务细节、协议解析、API 拼装或大段状态机 | 优先迁出到明确的组件、composable、service 或 mapper |
| 功能组件 `components/*.vue` | 是否同时负责容器编排、展示细节和跨模块状态 | 只在职责边界清晰时拆成容器组件和展示组件 |
| composable `use*.js` | 是否混合多个业务能力、生命周期清理和副作用难以确认 | 按状态、动作、订阅或协议边界拆分 |
| service/api 文件 | 是否混合多个资源、协议和浏览器副作用 | 按资源、协议或副作用边界拆分 |
| mapper/normalizer 文件 | 是否同时处理多个输入来源或多种输出结构 | 按输入来源、输出对象或纯函数职责拆分 |
| CSS 文件 | 是否混合组件私有样式、跨组件布局和响应式状态 | 随组件迁移或按业务区域收敛到样式模块 |
| 常量配置文件 | 是否混合无关业务域，导致命名和依赖失焦 | 按功能域或稳定配置对象拆分 |

准入规则：

- 新增文件不因单纯行数被拒绝；若职责单一、数据流清楚、验证充分，可以保留在同一文件。
- 修改既有大文件时，禁止无理由继续扩大职责范围；新增能力必须先确认归属模块。
- 路由页新增业务逻辑时，必须说明为什么不能放进已有模块。
- 单个 PR 大幅修改 `ProjectChat.vue` 时，必须附带拆分说明和验证范围。

## 推荐目录结构

以 `ProjectChat` 为例，统一收敛到 `web-admin/frontend/src/modules/project-chat/`：

```text
src/modules/project-chat/
  components/
    code-preview/
      CodePreviewDialog.vue
    composer/
      ChatComposer.vue
      ChatComposer.css
      ChatMediaParameterPopover.vue
    execution-status/
      ChatExecutionStatusChip.vue
      ChatExecutionStatusPopover.vue
      ChatExecutionStatusPopoverPanel.vue
    layout/
      ChatContextBar.vue
    messages/
      ChatMessageList.vue
      ChatMessageList.css
    sessions/
      ChatSessionList.vue
      GroupChatDialog.vue
      ProjectConversationSidebar.vue
    skill-resource/
      SkillResourceDialog.vue
      SkillResourceDialog.css
    task-tree/
      ChatTaskTreePanel.vue
      ChatTaskTreePanel.css
    terminal/
      TerminalApprovalDialog.vue
  composables/
    useProjectChatComposer.js
    useProjectChatPendingRequests.js
    useProjectChatTaskTreeState.js
    useProjectChatTransport.js
  services/
    projectChatCodePreview.js
    projectChatEmployeeDraftApi.js
    projectChatMaterialsApi.js
    projectChatMarkdown.js
    projectChatRequirementRecord.js
    projectChatRuntimeStorage.js
    projectChatSettingsApi.js
    projectChatSkillResources.js
    projectChatStorage.js
    projectChatTaskTreeApi.js
    projectChatWorkspaceApi.js
  mappers/
    chatSourceMappers.js
    mediaMappers.js
    messageMappers.js
    nativeAgentMappers.js
    native-agent/
      nativeAgentDetailMappers.js
    taskTreeMappers.js
    terminalMappers.js
    workspaceMappers.js
  constants/
    chatSettingsDefaults.js
    highRiskRules.js
    projectChatConstants.js
    settingsCenterConfig.js
  styles/
    project-chat-style-01.css
    ...
    project-chat-style-15.css
```

后续新增组件必须继续放入业务子目录，不要退回 `components/` 扁平目录。现有 `project-chat-style-01.css` 到 `project-chat-style-15.css` 是过渡状态，后续应在视觉对照充分时再按业务域重命名和收敛 owner。

`src/views/projects/ProjectChat.vue` 最终只保留：

- 路由参数读取。
- 模块级 composable 初始化。
- 顶层页面布局组件。
- 少量跨模块事件编排。

目标是持续收敛为路由编排页；具体行数不是验收硬门槛。

## 分层职责

### View 层

只做页面入口和跨模块编排：

- 读取 `route`、`router`。
- 初始化项目 ID、会话 ID、当前面板。
- 组合 `ProjectChatShell`、弹窗、全局反馈组件。
- 把跨模块事件转发给对应 composable。

禁止在 View 层新增：

- API 请求细节。
- WebSocket 消息解析。
- 大段数据 normalize。
- localStorage key 拼接。
- 复杂终端或 Agent 状态机。
- 超过 20 行的事件处理函数。

### Component 层

组件只负责展示和局部交互：

- `props` 接收状态。
- `emits` 抛出用户动作。
- 不直接调用业务 API，除非是高度封闭的上传/下载控件。
- 不读取全局路由和 localStorage。

组件拆分优先级：

1. 页面区域：头部、侧栏、消息区、输入区、设置中心、终端区。
2. 重复卡片：消息项、会话项、任务节点、文件项、权限记录。
3. 弹窗：员工草稿、素材保存、技能资源、统一 MCP、任务树详情。

### Composable 层

每个 composable 只暴露一个业务能力：

- `state`：响应式状态。
- `computed`：派生状态。
- `actions`：用户动作和业务动作。
- `lifecycle`：订阅、清理、恢复。

命名示例：

```js
export function useProjectChatMessages(options) {
  const messages = ref([]);
  const loading = ref(false);

  async function fetchHistory(sessionId) {}
  function appendRealtimeMessage(payload) {}
  function resetMessages() {}

  return {
    messages,
    loading,
    fetchHistory,
    appendRealtimeMessage,
    resetMessages,
  };
}
```

禁止 composable 之间形成互相 import。跨模块协作通过 View 层或一个明确的 orchestrator 组合。

### Service 层

service 负责副作用边界：

- API 请求。
- WebSocket 协议封装。
- native bridge 调用。
- localStorage/sessionStorage 读写。
- Markdown 渲染、HTML 预览等纯工具能力。

service 不持有 Vue 响应式状态，不直接弹 `ElMessage`。

### Mapper 层

mapper 负责输入输出结构转换：

- 服务端消息转 UI 消息。
- WebSocket event 转业务事件。
- 任务树 payload normalize。
- 设置表单和接口 payload 互转。

mapper 必须是纯函数，便于单元测试。

## ProjectChat 拆分阶段

### 当前阶段状态

| 阶段 | 当前状态 | 说明 |
| --- | --- | --- |
| 阶段 0：冻结增量入口 | 部分完成 | 文档规则和回涨检查已建立；PR 模板或 review 自动引用未确认。 |
| 阶段 1：低风险纯函数和常量迁移 | 部分完成 | storage、markdown、constants、message/task/native/terminal/workspace mapper 已迁出一批；仍需继续清理页面内纯函数。 |
| 阶段 2：消息与会话模块拆分 | 部分完成 | 会话侧栏、消息列表、输入区等已拆到模块目录；消息渲染 DOM 仍有大量内容留在页面，后续需谨慎避免 UI 回归。 |
| 阶段 3：传输与实时协议拆分 | 部分完成 | `useProjectChatTransport.js`、`useProjectChatPendingRequests.js` 和 `projectChatWsProtocol.js` 已存在，部分协议归一化、后台操作映射、done/guard 状态归一化、pending request Map 与活动请求 ID 选择已迁出；`handleSocketMessage`、pending request resolve/reject 副作用和大量实时事件处理仍主要在页面内。 |
| 阶段 4：任务树、工作流和需求记录拆分 | 部分完成 | 任务树面板、状态 composable、actions composable、API service、恢复提示 mapper、节点草稿 mapper 和保存节点 payload/校验 mapper 已存在；任务树主流程已基本迁出，需求记录和部分面板联动仍在页面。 |
| 阶段 5：外部 Agent、终端和工作区文件拆分 | 部分完成 | native/terminal/workspace mapper、工作区文件 Web API service 和终端审批弹窗已拆出；native agent、terminal mirror、runner 权限、workspace file 主状态机仍在页面。 |
| 阶段 6：设置中心、员工草稿、技能资源拆分 | 部分完成 | 技能资源弹窗、设置中心 API service、员工草稿 API service 和素材保存 API service 已拆出；设置中心表单状态、员工草稿匹配/弹窗状态、素材弹窗状态、统一 MCP 弹窗仍主要在页面。 |
| 阶段 7：样式拆分 | 部分完成 | 大段 scoped CSS 已迁到 15 个外部 scoped style 文件；还未按业务域命名和 owner 收敛。 |

后续优先级：

1. 继续阶段 3，把 pending request 分发、done/error 结算和更多实时事件映射从页面迁出。
2. 继续阶段 4，把需求记录和剩余面板联动收敛到明确边界。
3. 继续阶段 5，按 native agent、terminal、workspace file 三条状态机分片推进，优先迁出 API/协议边界。
4. 阶段 6 和阶段 7 只在有视觉对照或明确 owner 时推进，避免再次出现 UI/CSS 回归。

### 阶段 0：冻结增量入口

目标：先止血，避免继续变大。

- 新需求默认不得直接向 `ProjectChat.vue` 增加业务逻辑。
- 只允许在原文件做 bug 修复、事件接线和迁移过渡。
- 新增业务必须进入 `src/modules/project-chat/` 对应目录。
- 为 `ProjectChat.vue` 建立当前回涨检查基线：23,809 行。

验收：

- 文档规则合入。
- 后续 PR 模板或 review checklist 引用本规范。

### 阶段 1：低风险纯函数和常量迁移

优先迁移无响应式依赖、无 DOM 依赖、无 API 依赖的内容：

- HTML escape、代码语言 normalize、代码预览判断。
- storage key 构造和读取写入。
- 时间、状态、标签、权限展示文案。
- command alias、风险规则、设置项配置。
- 消息、附件、素材、任务树、Agent record 的 normalize 函数。

目标文件：

- `services/projectChatStorage.js`
- `services/projectChatMarkdown.js`
- `mappers/messageMappers.js`
- `mappers/taskTreeMappers.js`
- `constants/storageKeys.js`
- `constants/commandConstants.js`

验收：

- `ProjectChat.vue` 减少 2,000 到 4,000 行。
- 迁出的纯函数有直接单元测试或最小脚本验证。

### 阶段 2：消息与会话模块拆分

先拆主路径，因为这是页面核心：

- 会话列表、创建、删除、切换、历史加载。
- 消息列表、旧消息加载、滚动吸底、消息定位。
- 消息操作：复制、删除、编辑重放、保存素材入口。
- 输入区：附件、粘贴、拖拽、队列 follow-up、发送请求。

目标组件：

- `ProjectConversationSidebar.vue`
- `ChatMessageList.vue`
- `ChatMessageItem.vue`
- `ChatComposer.vue`

目标 composable：

- `useProjectChatSessions.js`
- `useProjectChatMessages.js`
- `useProjectChatComposer.js`

验收：

- `ProjectChat.vue` 不再直接维护消息列表 DOM 细节。
- 消息滚动、发送、停止、删除、编辑重放行为保持一致。

### 阶段 3：传输与实时协议拆分

把 WebSocket、pending request、实时事件处理独立出来：

- WebSocket 连接、重连、断开。
- pending request map。
- 实时消息 append。
- 任务状态、工具调用、权限审批、结构化交互事件分发。
- 取消生成和快速取消。

目标文件：

- `useProjectChatTransport.js`
- `services/projectChatWsProtocol.js`
- `mappers/realtimeEventMappers.js`

验收：

- View 层只订阅 `transport.on(eventName, handler)` 或接收 composable 暴露的状态。
- WebSocket event 解析不出现在 `ProjectChat.vue`。

### 阶段 4：任务树、工作流和需求记录拆分

当前已有 `useProjectChatTaskTreeState.js` 和 `useProjectChatTaskTreeActions.js`，继续补齐边界：

- 任务树拉取、恢复、删除、保存节点、打开面板已迁出。
- ongoing task notice 已迁出到 task tree actions/mapper。
- 本地 requirement record upsert。
- 任务树状态展示组件与剩余面板联动。

目标组件：

- `ChatTaskTreePanel.vue`
- `OngoingTaskRestoreNotice.vue`

目标文件：

- `useProjectChatTaskTreeState.js`
- `useProjectChatTaskTreeActions.js`
- `mappers/taskTreeMappers.js`
- `services/projectChatTaskTreeApi.js`

验收：

- 任务树相关 API 和状态不再散落在主页面。
- 任务树恢复、节点保存、面板打开行为保持一致。
- requirement record 与任务树闭环联动仍需继续迁移。

### 阶段 5：外部 Agent、终端和工作区文件拆分

这部分状态机复杂，必须按能力拆：

- native external agent 会话、日志、记录、详情面板。
- terminal mirror、stdin、结构化表单交互。
- runner permission records 和审批动作。
- workspace file tree、文件读取、写入、diff preview；其中 Web API 已迁入 `projectChatWorkspaceApi.js`，native bridge 分支和主状态机仍在页面。
- project workspace path 和 AI entry file 配置。

目标组件：

- `NativeAgentPanel.vue`
- `ChatTerminalDock.vue`
- `WorkspaceFilePanel.vue`
- `RunnerPermissionDialog.vue`

目标 composable：

- `useProjectChatNativeAgent.js`
- `useProjectChatTerminal.js`
- `useProjectChatWorkspaceFiles.js`
- `services/projectChatWorkspaceApi.js`

验收：

- native bridge 调用集中在 service。
- Agent、终端、工作区文件互不直接 import。
- 复杂交互可以分别测试和手动验证。

### 阶段 6：设置中心、员工草稿、技能资源拆分

把配置类和辅助工作流迁出：

- 设置中心 panel、参数、自动保存。
- 设置中心 providers/settings API 已迁入 `projectChatSettingsApi.js`，表单状态和自动保存编排仍在页面。
- 员工草稿目录加载、生成草稿、创建员工 API 已迁入 `projectChatEmployeeDraftApi.js`，匹配技能/规则和弹窗状态仍在页面。
- 技能资源搜索、安装、目录选择。
- 素材保存 API 已迁入 `projectChatMaterialsApi.js`，素材保存弹窗状态仍在页面。
- 统一 MCP 弹窗。

目标组件：

- `ChatSettingsCenter.vue`
- `EmployeeDraftDialogHost.vue`
- `SkillResourceDialog.vue`
- `MaterialSaveDialogHost.vue`

目标 composable：

- `useProjectChatSettings.js`
- `useProjectChatEmployeeDrafts.js`
- `useProjectChatSkillResources.js`

验收：

- 设置和辅助弹窗从主页面剥离。
- 自动保存、草稿创建、技能安装均有回归验证。

### 阶段 7：样式拆分

样式随组件迁移：

- 组件私有样式放入对应 `.vue`。
- 跨组件布局样式放入 `styles/project-chat-layout.css`。
- 消息渲染样式放入 `styles/project-chat-message.css`。
- 设置中心样式放入 `styles/project-chat-settings.css`。
- 终端和 Agent 样式放入 `styles/project-chat-terminal.css`。

验收：

- `ProjectChat.vue` 内不再保留大段 scoped CSS。
- 任一 CSS 文件职责清晰，不把组件私有样式、跨组件布局和无关业务域混在一起。
- 页面视觉和响应式行为无明显回退。

## 最终目标

完成全部阶段后，规模目标如下：

| 模块 | 目标状态 |
| --- | --- |
| `views/projects/ProjectChat.vue` | 只保留路由参数、模块初始化和跨模块事件编排 |
| 单个 UI 组件 | 只负责展示、局部交互、props 和 emits |
| 单个 composable | 只负责一个业务能力的状态、动作、生命周期和清理 |
| 单个 service/mapper | service 负责协议/API/副作用，mapper 保持纯输入输出转换 |
| 单个 CSS 文件 | 按组件私有样式或业务区域归属，避免样式所有权漂移 |

## Review 检查清单

每次涉及 `ProjectChat` 或同类大型页面的 PR，必须检查：

- 是否新增了业务逻辑到路由页。
- 是否出现职责混杂、文件异常膨胀或后续难以验证的趋势。
- 是否把 API、mapper、storage、UI 状态混在一起。
- 是否新增了跨模块循环依赖。
- 是否有明确的模块归属和命名。
- 是否有最小验证：单元测试、构建、手动流程、截图或日志。
- 是否更新了相关文档或 checklist。

## 自动化建议

保留一个回涨检查脚本，例如 `web-admin/frontend/scripts/check-file-size.mjs`。脚本只用于阻止已登记的大文件继续变大，不再用固定行数阈值驱动拆分：

```js
const regressionBaselines = {
  "src/views/projects/ProjectChat.vue": 23809,
};
```

接入方式：

- 本地：`npm run check:file-size`
- CI：在 lint 后、build 前执行
- 回涨时输出文件路径、当前行数和登记基线

过渡期可以给 `ProjectChat.vue` 配置临时基线，但只允许相对基线下降或持平：

```text
ProjectChat.vue baseline: 23809
规则：允许修改后行数 <= baseline；不允许继续增加。
退出条件：该页面已经收敛为清晰的路由编排页，并且后续维护不再依赖行数脚本兜底。
```

## 执行顺序建议

1. 已完成：合入本规范，作为后续 review 依据。
2. 已完成：建立回涨检查脚本和当前基线。
3. 已部分完成：迁移纯函数、常量、storage 和 mapper。
4. 已部分完成：迁移消息、会话、输入区主路径。
5. 正在推进：迁移 WebSocket、实时协议和 pending request 分发。
6. 后续继续：迁移任务树、外部 Agent、终端和工作区文件。
7. 后续谨慎推进：迁移设置中心、员工草稿、技能资源和样式 owner。
8. 最后收尾：删除过渡 glue code，收敛 `ProjectChat.vue` 到路由编排页。

## 风险与控制

- 风险：一次性拆太多导致聊天主流程回归困难。
  控制：每个阶段只迁一个业务域，合并前跑主流程验证。
- 风险：迁出 composable 后状态依赖不清。
  控制：统一由 View 层组合，禁止 composable 循环引用。
- 风险：样式拆分后视觉漂移。
  控制：组件迁移时保留类名，最后再整理命名。
- 风险：旧文件长期保留临时桥接。
  控制：每个阶段记录待删除 glue code，下一阶段开始前先清理。

## 本次不做的事

- 不直接重构 `ProjectChat.vue` 代码。
- 不调整现有接口协议。
- 不改变页面视觉和交互。
- 不引入新的状态管理库，除非后续单独评审确认收益大于迁移成本。
