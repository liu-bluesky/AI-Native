# 模块代码规范与 ProjectChat 拆分计划

## 背景

`web-admin/frontend/src/views/projects/ProjectChat.vue` 当前约 36,107 行：

- `<template>` 起始于第 1 行，`<script setup>` 起始于第 4,719 行。
- `<style scoped>` 起始于第 26,531 行，样式约 9,577 行。
- `script setup` 内集中承载了项目选择、会话列表、消息渲染、WebSocket、任务树、外部 Agent、终端交互、工作区文件、素材保存、员工草稿、技能资源、设置中心、代码预览等职责。
- 文件内存在大量顶层状态、计算属性、监听器和函数，已经不适合作为单页继续扩展。

本计划的目标不是一次性重写页面，而是建立模块边界和准入规则，让后续功能无法再自然堆回一个几万行 SFC。

## 总原则

1. 页面文件只负责路由级编排，不承载业务细节。
2. 单个模块只对一个业务对象负责，例如会话、消息、设置、任务树、外部 Agent 或工作区文件。
3. UI、状态、接口、数据转换、浏览器存储、协议解析分层放置。
4. 每次新增功能必须先选择归属模块；没有归属模块时先建模块，再写功能。
5. 大文件治理按增量迁移推进，迁移期间保证行为不变，避免混合重构和新需求开发。

## 文件规模硬限制

| 文件类型 | 建议上限 | 强制上限 | 处理方式 |
| --- | ---: | ---: | --- |
| 路由级 `views/*.vue` | 400 行 | 800 行 | 超过后必须拆子组件或 composable |
| 功能组件 `components/*.vue` | 250 行 | 500 行 | 超过后拆成展示组件和容器组件 |
| composable `use*.js` | 250 行 | 450 行 | 超过后按状态、动作、订阅拆分 |
| service/api 文件 | 200 行 | 400 行 | 超过后按资源或协议拆分 |
| mapper/normalizer 文件 | 250 行 | 500 行 | 超过后按输入来源拆分 |
| CSS 文件 | 300 行 | 600 行 | 超过后按组件或区域拆分 |
| 常量配置文件 | 250 行 | 500 行 | 超过后按功能域拆分 |

强制规则：

- 新增文件超过强制上限，不允许合入。
- 修改既有超限文件时，除紧急修复外，必须同时迁出一部分职责，不能继续扩大文件。
- 路由页新增逻辑超过 80 行时，必须说明为什么不能放进已有模块。
- 单个 PR 修改 `ProjectChat.vue` 超过 300 行时，必须附带拆分说明和验证范围。

## 推荐目录结构

以 `ProjectChat` 为例，统一收敛到 `web-admin/frontend/src/modules/project-chat/`：

```text
src/modules/project-chat/
  components/
    ProjectChatShell.vue
    ProjectConversationSidebar.vue
    ProjectChatHeader.vue
    ChatMessageList.vue
    ChatMessageItem.vue
    ChatComposer.vue
    ChatSettingsCenter.vue
    ChatTaskTreePanel.vue
    ChatTerminalDock.vue
    NativeAgentPanel.vue
    WorkspaceFilePanel.vue
    SkillResourceDialog.vue
  composables/
    useProjectChatRoute.js
    useProjectChatSessions.js
    useProjectChatMessages.js
    useProjectChatComposer.js
    useProjectChatTransport.js
    useProjectChatTaskTree.js
    useProjectChatSettings.js
    useProjectChatNativeAgent.js
    useProjectChatTerminal.js
    useProjectChatWorkspaceFiles.js
    useProjectChatEmployeeDrafts.js
    useProjectChatSkillResources.js
    useProjectChatCodePreview.js
  services/
    projectChatApi.js
    projectChatWsProtocol.js
    projectChatStorage.js
    projectChatNativeBridge.js
  mappers/
    messageMappers.js
    taskTreeMappers.js
    settingsMappers.js
    nativeAgentMappers.js
  constants/
    commandConstants.js
    settingsConstants.js
    storageKeys.js
  styles/
    project-chat-layout.css
    project-chat-message.css
    project-chat-settings.css
    project-chat-terminal.css
```

`src/views/projects/ProjectChat.vue` 最终只保留：

- 路由参数读取。
- 模块级 composable 初始化。
- 顶层页面布局组件。
- 少量跨模块事件编排。

目标规模控制在 300 到 500 行。

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

### 阶段 0：冻结增量入口

目标：先止血，避免继续变大。

- 新需求默认不得直接向 `ProjectChat.vue` 增加业务逻辑。
- 只允许在原文件做 bug 修复、事件接线和迁移过渡。
- 新增业务必须进入 `src/modules/project-chat/` 对应目录。
- 为 `ProjectChat.vue` 建立行数基线：36,107 行。

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

当前已有 `useProjectChatTaskTreeState.js`，继续补齐边界：

- 任务树拉取、恢复、保存节点、打开面板。
- ongoing task notice。
- 本地 requirement record upsert。
- 任务树状态展示组件。

目标组件：

- `ChatTaskTreePanel.vue`
- `OngoingTaskRestoreNotice.vue`

目标文件：

- `useProjectChatTaskTree.js`
- `mappers/taskTreeMappers.js`

验收：

- 任务树相关 API 和状态不再散落在主页面。
- 任务树恢复、节点保存、面板打开行为保持一致。

### 阶段 5：外部 Agent、终端和工作区文件拆分

这部分状态机复杂，必须按能力拆：

- native external agent 会话、日志、记录、详情面板。
- terminal mirror、stdin、结构化表单交互。
- runner permission records 和审批动作。
- workspace file tree、文件读取、写入、diff preview。
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

验收：

- native bridge 调用集中在 service。
- Agent、终端、工作区文件互不直接 import。
- 复杂交互可以分别测试和手动验证。

### 阶段 6：设置中心、员工草稿、技能资源拆分

把配置类和辅助工作流迁出：

- 设置中心 panel、参数、自动保存。
- 员工草稿生成、匹配技能/规则、创建员工。
- 技能资源搜索、安装、目录选择。
- 素材保存弹窗。
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
- 任一 CSS 文件不超过 600 行。
- 页面视觉和响应式行为无明显回退。

## 最终目标

完成全部阶段后，规模目标如下：

| 模块 | 目标规模 |
| --- | ---: |
| `views/projects/ProjectChat.vue` | 300 到 500 行 |
| 单个 UI 组件 | 100 到 350 行 |
| 单个 composable | 120 到 350 行 |
| 单个 service/mapper | 80 到 300 行 |
| 单个 CSS 文件 | 100 到 500 行 |

## Review 检查清单

每次涉及 `ProjectChat` 或同类大型页面的 PR，必须检查：

- 是否新增了业务逻辑到路由页。
- 是否让一个文件超过强制行数上限。
- 是否把 API、mapper、storage、UI 状态混在一起。
- 是否新增了跨模块循环依赖。
- 是否有明确的模块归属和命名。
- 是否有最小验证：单元测试、构建、手动流程、截图或日志。
- 是否更新了相关文档或 checklist。

## 自动化建议

新增一个行数检查脚本，例如 `web-admin/frontend/scripts/check-file-size.mjs`：

```js
const limits = [
  ["src/views/**/*.vue", 800],
  ["src/modules/**/*.vue", 500],
  ["src/modules/**/composables/*.js", 450],
  ["src/modules/**/services/*.js", 400],
  ["src/modules/**/mappers/*.js", 500],
  ["src/modules/**/*.css", 600],
];
```

接入方式：

- 本地：`npm run check:file-size`
- CI：在 lint 后、build 前执行
- 超限输出文件路径、当前行数、上限和建议拆分目录

过渡期可以给 `ProjectChat.vue` 配置临时基线，但只允许下降：

```text
ProjectChat.vue baseline: 36107
规则：允许修改后行数 <= baseline；不允许继续增加。
退出条件：文件低于 800 行后移除 baseline。
```

## 执行顺序建议

1. 先合入本规范，作为后续 review 依据。
2. 建立文件行数检查脚本和临时基线。
3. 迁移纯函数、常量、storage 和 mapper。
4. 迁移消息、会话、输入区主路径。
5. 迁移 WebSocket 和实时协议。
6. 迁移任务树、外部 Agent、终端和工作区文件。
7. 迁移设置中心、员工草稿、技能资源和样式。
8. 删除过渡 glue code，收敛 `ProjectChat.vue` 到路由编排页。

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
