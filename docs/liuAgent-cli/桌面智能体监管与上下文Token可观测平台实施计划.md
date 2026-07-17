# 桌面智能体监管与上下文 Token 可观测平台实施计划

## 1. 文档信息

- 状态：实施规划
- 编写日期：2026-07-17
- 目标端：AI 员工工厂桌面端
- 数据边界：仅存储在桌面智能体本机，不同步服务端
- 核心入口：复制助手回答 ID，在监管页面检索并复盘该回答的完整执行链路
- 关联文档：
  - `docs/liuAgent-cli/桌面本地智能体Trace与进度播报改造计划.md`
  - `docs/liuAgent-cli/design/06-state-storage.md`
  - `docs/liuAgent-cli/design/13-agent-orchestration.md`
  - `docs/liuAgent-cli/design/14-consistency-audit.md`

## 2. 背景与问题

桌面智能体已经能够完成模型调用、本地工具执行、权限确认、暂停恢复和项目聊天，但后续优化仍缺少统一监管入口。目前主要问题包括：

1. 用户能看到最终回答，但很难根据一个回答快速定位它经历了哪些模型轮次、工具调用和重试。
2. 执行记录存在于运行快照和事件数据中，但没有形成面向复盘的流程图。
3. 可以获得模型整体输入、输出 Token，但无法解释输入 Token 分别来自系统提示词、历史对话、项目规则、工具结果还是运行状态。
4. 上下文发生压缩、裁剪或替换后，缺少压缩前后对比和被移除内容的原因记录。
5. 缺少跨回答对比，无法判断某次智能体优化是否真的减少 Token、缩短耗时或降低失败率。
6. 现有统计页面更偏全局使用统计，不适合复盘单个回答的执行细节。

本计划建设一个桌面本地监管与复盘平台，将“回答 ID”作为主入口，把回答、运行、执行步骤、上下文、Token、错误和优化建议串成同一条可追溯链路。

## 3. 建设目标

### 3.1 核心目标

1. 支持复制 `assistant_message_id`，在监管页面精确搜索对应回答。
2. 展示从用户提问到最终回答的完整执行流程图。
3. 展示每轮模型调用的上下文组成、压缩动作和 Token 消耗。
4. 展示工具调用、权限决策、错误、重试、暂停和恢复过程。
5. 自动识别高 Token、重复工具调用、无效重试和上下文重复注入问题。
6. 支持选择两个回答进行执行链路和 Token 对比。
7. 所有监管数据只写入桌面端 SQLite，不写入服务端聊天历史或服务端监管库。

### 3.2 非目标

1. 不展示模型隐藏思维链或原始 Chain-of-Thought。
2. 不在前端根据日志猜测真实执行状态。
3. 不把桌面本地监管数据自动上传到服务端。
4. 不把监管平台做成可编辑工作流编排器；第一阶段只做只读复盘和分析。
5. 不用兼容兜底掩盖采集缺失。某项数据无法获得时必须显示“未采集”或“不支持”，不能伪造估算值。
6. 不读取或迁移旧 `localStorage` 聊天历史作为监管数据来源。

## 4. 总体架构决策

### 4.1 架构结论

采用“运行时结构化采集 + 本地 SQLite 持久化 + Tauri Command 查询 + Vue 监管页面”的架构：

```text
桌面智能体运行时
  ├─ 用户请求与回答 ID
  ├─ 上下文组装器
  ├─ 模型调用器
  ├─ 工具执行器
  ├─ 权限与状态机
  └─ Trace Event
          │
          ▼
本地监管采集器（Rust）
  ├─ 字段脱敏
  ├─ Token 计量
  ├─ Step/Edge 生成
  └─ SQLite 事务写入
          │
          ▼
project-chat.sqlite3
          │
          ▼
Tauri Commands
          │
          ▼
Vue 3 监管页面
  ├─ 回答 ID 搜索
  ├─ 执行链路流程图
  ├─ 上下文与压缩分析
  ├─ Token 与耗时分析
  └─ 优化建议与回答对比
```

### 4.2 数据权威来源

| 数据 | 权威来源 | 说明 |
|---|---|---|
| 回答 ID | `assistant_message_id` | 监管检索主键 |
| 用户消息 ID | `message_id` | 回答与用户问题关联 |
| 会话 | `chat_session_id` | 回答所属聊天会话 |
| 一次运行 | `run_id` | 一次回答可包含一次或多次恢复运行 |
| 一次请求 | `request_id` | 幂等、重试和传输关联 |
| 工具调用 | `call_id` / `tool_call_id` | 工具步骤主键 |
| 真实 Token 总量 | Provider 返回的 usage | 输入、输出、缓存输入和总量 |
| 上下文分段 Token | 上下文组装器采集 | 在发送模型前按分段计量 |
| 执行状态 | Runner / Runtime 事件 | 前端不得推断终态 |
| 执行关系 | Trace 的 parent、batch、round 信息 | 生成流程图边 |

## 5. 技术栈选型

### 5.1 桌面运行与本地服务层

| 领域 | 选型 | 选择原因 |
|---|---|---|
| 桌面容器 | Tauri 2 | 项目已使用，能够直接访问应用数据目录和本地能力 |
| 本地实现语言 | Rust | 与 Tauri 主进程一致，适合事务写入、脱敏和高频事件采集 |
| 本地数据库 | SQLite + `rusqlite` bundled | 当前项目聊天已使用，部署时不依赖系统 SQLite |
| 数据库模式 | WAL + `busy_timeout` + 短事务 | 支持运行事件持续写入，同时允许监管页面读取 |
| 序列化 | `serde` + `serde_json` | 用于事件元数据和只读快照 |
| 时间 | UTC Epoch Milliseconds | 便于流程排序、耗时统计和跨时区展示 |

### 5.2 前端展示层

| 领域 | 选型 | 选择原因 |
|---|---|---|
| 前端框架 | Vue 3 Composition API | 与当前前端一致 |
| UI 组件 | Element Plus | 复用表格、抽屉、分页、Tabs、Tag 和空状态 |
| 路由 | Vue Router | 增加独立桌面监管入口 |
| 流程图 | ECharts Graph | 项目已经安装 ECharts，适合只读 DAG、缩放、拖动和点击节点 |
| Token 趋势 | ECharts Line / Bar | 展示模型轮次、上下文组成和耗时趋势 |
| 上下文流向 | ECharts Sankey | 展示原始上下文如何经过选择、压缩后进入最终提示词 |
| 状态管理 | 页面级 Composition Service | 第一阶段不额外引入全局状态库 |
| Markdown | 现有 `marked` | 展示回答、提示词摘要和优化建议 |

### 5.3 流程图库决策

第一阶段选择 ECharts，而不是立即引入 Vue Flow：

1. 当前需求是只读监管，不需要用户编辑节点和连线。
2. ECharts 已经存在，减少桌面安装包依赖和维护成本。
3. Graph 适合执行 DAG，Line/Bar/Sankey 可共享主题和 Tooltip。
4. 可以通过 `roam`、节点点击、邻接高亮、分类图例和缩略视图满足复盘需求。

只有后续出现以下需求时才评估 Vue Flow：

- 需要人工拖拽修改执行计划。
- 需要把执行链路转成可复用工作流模板。
- 需要节点端口、连线编辑、嵌套子流程和人工回放控制。

### 5.4 Token 计量技术决策

Token 数据分成两类，不能混为一谈：

1. **Provider 权威用量**
   - 使用模型响应中的 `input_tokens`、`output_tokens`、`cached_input_tokens`、`total_tokens`。
   - 用于账单、总量和最终验收。

2. **上下文分段计量**
   - 在上下文组装器中给每个 segment 分配稳定 ID。
   - 组装完成、压缩前、压缩后分别执行 TokenMeter。
   - TokenMeter 按 Provider/模型选择明确的 tokenizer adapter。
   - tokenizer 不支持时写入 `measurement_status=unsupported`，不得使用字符数伪装为 Token。
   - 可以同时记录 `char_count` 和 `byte_count`，用于不支持 tokenizer 时排查体积，但界面必须明确它们不是 Token。

Provider 总输入 Token 与分段 Token 之和可能因消息包装、工具 schema 和 Provider 特殊 token 存在差异。系统必须记录 `unattributed_tokens`：

```text
unattributed_tokens = provider_input_tokens - sum(context_segment_tokens)
```

差异不能被静默抹平。当差异超过配置阈值时，监管页面显示“Token 归因不完整”。

## 6. 回答 ID 检索设计

### 6.1 主键规则

以 `assistant_message_id` 作为回答的 canonical ID：

```text
assistant_message_id
  → answer record
  → chat_session_id
  → one or more run_id
  → model rounds
  → execution steps and edges
  → context snapshots
  → token usage
```

禁止根据回答文本、时间或数组下标反向猜测回答 ID。

### 6.2 搜索能力

监管页搜索框支持：

1. 完整回答 ID 精确搜索。
2. 回答 ID 前缀搜索。
3. `request_id` 搜索。
4. `run_id` 搜索。
5. `chat_session_id` 搜索并列出该会话回答。
6. 按项目、模型、状态、时间范围组合筛选。

默认行为：

- 粘贴完整回答 ID 后按 Enter，直接打开回答详情。
- 搜索无结果时明确显示“本机监管库中没有该回答”，不请求服务端历史接口。
- 回答仍在执行时，详情页面显示实时状态并按本地事件增量刷新。

### 6.3 聊天页联动

每条助手回答菜单增加：

- 复制回答 ID。
- 查看执行监管。
- 与另一回答对比。

“查看执行监管”跳转参数：

```text
/ai/supervision?answer_id=<assistant_message_id>
```

桌面新窗口打开时仍读取同一个本地 SQLite。

## 7. 本地 SQLite 数据设计

### 7.1 存储位置

继续使用 Tauri 应用数据目录中的：

```text
project-chat.sqlite3
```

监管表与聊天表位于同一数据库，原因如下：

1. 回答 ID 与聊天消息天然需要事务关联。
2. 避免两个 SQLite 文件的生命周期和删除策略分叉。
3. 删除聊天会话时可以在同一事务中删除对应监管数据。
4. 保持桌面项目聊天本地唯一存储原则。

监管查询必须走单独的 Rust Repository/Command 模块，不允许前端直接访问数据库文件。

### 7.2 表设计

#### `agent_supervision_answers`

一条助手回答的入口记录。

| 字段 | 类型 | 说明 |
|---|---|---|
| `assistant_message_id` | TEXT PRIMARY KEY | 回答 ID |
| `username` | TEXT NOT NULL | 本地用户隔离 |
| `project_id` | TEXT NOT NULL | 项目隔离 |
| `chat_session_id` | TEXT NOT NULL | 会话 ID |
| `user_message_id` | TEXT NOT NULL | 对应用户消息 |
| `question_preview` | TEXT NOT NULL | 脱敏后的问题摘要 |
| `answer_preview` | TEXT NOT NULL | 回答摘要 |
| `status` | TEXT NOT NULL | queued/running/completed/failed/blocked/cancelled |
| `model_name` | TEXT NOT NULL | 最终回答模型 |
| `provider_id` | TEXT NOT NULL | Provider |
| `started_at_epoch_ms` | INTEGER NOT NULL | 开始时间 |
| `finished_at_epoch_ms` | INTEGER NOT NULL | 结束时间 |
| `duration_ms` | INTEGER NOT NULL | 总耗时 |
| `created_at_epoch_ms` | INTEGER NOT NULL | 创建时间 |
| `updated_at_epoch_ms` | INTEGER NOT NULL | 更新时间 |

索引：

- `(username, project_id, assistant_message_id)`
- `(username, project_id, chat_session_id, created_at_epoch_ms DESC)`
- `(username, project_id, status, created_at_epoch_ms DESC)`

#### `agent_supervision_runs`

一条回答对应的运行记录。暂停恢复可以产生多个 run attempt，但都关联同一回答。

关键字段：

- `run_id` 主键。
- `assistant_message_id` 外键。
- `request_id`。
- `attempt_index`。
- `resume_from_run_id`。
- `status`、`stop_reason`、`error_code`、`error_message`。
- `model_round_count`、`tool_round_count`、`tool_call_count`、`retry_count`。
- `started_at_epoch_ms`、`finished_at_epoch_ms`、`duration_ms`。

#### `agent_supervision_steps`

流程图节点表。

关键字段：

- `step_id` 主键。
- `run_id`。
- `parent_step_id`。
- `round_index`。
- `batch_index`。
- `step_index`。
- `step_type`。
- `status`。
- `title`、`summary`、`detail_preview`。
- `tool_name`、`call_id`。
- `input_preview`、`output_preview`。
- `started_at_epoch_ms`、`finished_at_epoch_ms`、`duration_ms`。
- `metadata_json`。

`step_type` 至少覆盖：

- `request`
- `context_build`
- `context_compaction`
- `model_call`
- `plan`
- `tool_call`
- `permission`
- `observation`
- `retry`
- `pause`
- `resume`
- `final_answer`
- `error`

#### `agent_supervision_edges`

流程图边表。

| 字段 | 说明 |
|---|---|
| `edge_id` | 主键 |
| `run_id` | 所属运行 |
| `source_step_id` | 起点 |
| `target_step_id` | 终点 |
| `edge_type` | sequence/dependency/result/retry/resume/branch |
| `label` | 边标签 |
| `sort_order` | 稳定排序 |

流程图只能从结构化关系生成，不能根据时间戳自动猜测所有边。

#### `agent_context_snapshots`

每轮模型调用的上下文快照摘要。

关键字段：

- `snapshot_id`。
- `run_id`、`model_step_id`、`round_index`。
- `snapshot_stage`：`before_selection`、`before_compaction`、`after_compaction`、`sent_to_model`。
- `context_limit_tokens`。
- `reserved_output_tokens`。
- `measured_input_tokens`。
- `provider_input_tokens`。
- `unattributed_tokens`。
- `compression_strategy`。
- `compression_reason`。
- `measurement_status`。

不保存未脱敏的完整密钥、Authorization、环境变量或凭据。

#### `agent_context_segments`

上下文组成明细。

建议 `segment_type`：

- `system_prompt`
- `project_manual`
- `project_rule`
- `employee_manual`
- `skill_instruction`
- `tool_schema`
- `conversation_history`
- `task_tree`
- `runtime_state`
- `observation`
- `tool_result`
- `attachment`
- `current_user_message`

关键字段：

- `segment_id`、`snapshot_id`。
- `source_id`、`source_type`、`source_title`。
- `selection_status`：selected/dropped/compacted/replaced。
- `selection_reason`。
- `original_char_count`、`final_char_count`。
- `original_token_count`、`final_token_count`。
- `tokenizer_name`、`measurement_status`。
- `content_hash`，用于识别重复注入。
- `preview_text`，仅保存脱敏摘要。

#### `agent_token_usage`

每轮模型调用的权威 Token 记录。

关键字段：

- `usage_id`、`run_id`、`model_step_id`、`round_index`。
- `provider_id`、`model_name`。
- `input_tokens`、`output_tokens`、`cached_input_tokens`、`total_tokens`。
- `estimated_cost`、`currency`。
- `usage_source`：provider/desktop-meter。
- `is_authoritative`。
- `created_at_epoch_ms`。

#### `agent_optimization_findings`

自动和人工优化结论。

关键字段：

- `finding_id`、`assistant_message_id`、`run_id`。
- `rule_code`。
- `severity`：info/warning/critical。
- `title`、`summary`、`evidence_json`。
- `recommendation`。
- `status`：open/accepted/dismissed/resolved。
- `created_at_epoch_ms`、`resolved_at_epoch_ms`。

### 7.3 数据写入原则

1. 回答、运行和首个 request step 在运行启动事务中创建。
2. 执行事件按 step 增量写入，不等待最终回答后一次性落库。
3. 模型调用结束时将 Provider usage 与对应 model step 同事务写入。
4. 最终回答结束时更新 answer 和 run 终态。
5. 相同 `event_id`、`step_id`、`usage_id` 使用唯一约束实现幂等。
6. SQLite 写入失败必须让运行状态记录明确错误，不允许静默改写到 JSON 或 `localStorage`。
7. 高频 token chunk 不逐 token 写库，只记录聚合后的模型步骤和必要的流式统计。

### 7.4 数据保留和删除

建议默认：

- 已完成回答监管数据保留 90 天，可在设置中调整。
- 失败、阻塞和人工标记回答优先保留。
- 删除聊天会话时，在同一 SQLite 事务删除 answer、run、step、edge、context、usage 和 finding。
- 提供“仅删除监管详情、保留聊天回答”的显式操作，但必须二次确认。
- 不自动上传或同步监管记录。

## 8. 运行时采集设计

### 8.1 采集点

| 阶段 | 必须采集 |
|---|---|
| 请求进入 | 回答 ID、用户消息 ID、请求 ID、会话、项目 |
| 上下文选择 | 候选 segment、选择状态、选择原因 |
| 上下文压缩 | 压缩策略、压缩前后大小、被删除 segment |
| 模型开始 | 模型、Provider、轮次、上下文限制 |
| 模型结束 | usage、耗时、finish reason、错误 |
| 工具开始 | 工具名、call ID、输入摘要、权限风险 |
| 权限决策 | 决策、来源、等待时长、幂等键 |
| 工具结束 | 输出摘要、退出码、错误、耗时 |
| 重试 | 原因、回退节点、重试次数、预算 |
| 暂停恢复 | pause reason、checkpoint、resume source |
| 最终回答 | 回答摘要、状态、总耗时、累计 Token |

### 8.2 Trace 与监管数据关系

Trace 是事实事件，监管表是查询投影：

```text
Trace Event → Supervision Projector → Steps / Edges / Usage / Context
```

不建议让每个业务模块直接拼监管页面数据。所有事件先进入统一 projector，再转换成监管表，避免模型、工具和权限模块分别定义不同结构。

### 8.3 不记录隐藏思维链

允许记录：

- 用户可见计划。
- 阶段性进度播报。
- 工具输入输出摘要。
- 结构化决策原因，例如权限策略命中、上下文超限、重试原因。
- 最终回答和自测结论。

禁止记录：

- 模型未显式输出的隐藏推理过程。
- 原始内部 Chain-of-Thought。
- 未脱敏的凭据和环境变量。

## 9. 监管页面信息架构

### 9.1 路由与入口

建议新增桌面路由：

```text
/ai/supervision
/ai/supervision/:assistantMessageId
```

页面建议：

```text
web-admin/frontend/src/views/desktop/AgentSupervision.vue
```

服务层建议：

```text
web-admin/frontend/src/modules/agent-supervision/services/agentSupervisionStorage.js
web-admin/frontend/src/modules/agent-supervision/mappers/agentSupervisionGraphMapper.js
web-admin/frontend/src/modules/agent-supervision/utils/agentTokenAnalysis.js
```

Tauri 模块建议：

```text
web-admin/frontend/src-tauri/src/agent_supervision_store.rs
```

### 9.2 页面布局

桌面宽屏采用三层结构：

1. 顶部搜索与全局摘要。
2. 中部主视图区，左侧流程图，右侧节点详情。
3. 底部上下文、Token、事件和优化建议 Tabs。

```text
┌────────────────────────────────────────────────────────────┐
│ 回答 ID 搜索      项目筛选  时间范围  状态  [搜索]          │
├────────────────────────────────────────────────────────────┤
│ 回答状态 │ 模型 │ 总耗时 │ 模型轮次 │ 工具次数 │ 总 Token │
├───────────────────────────────────┬────────────────────────┤
│                                   │ 节点详情               │
│          执行链路流程图           │ 输入/输出/耗时/Token    │
│                                   │ 错误/权限/重试信息      │
├───────────────────────────────────┴────────────────────────┤
│ 上下文组成 │ Token 趋势 │ 事件时间线 │ 优化建议 │ 回答对比 │
└────────────────────────────────────────────────────────────┘
```

### 9.3 流程图视觉规范

节点类型颜色：

| 类型 | 颜色语义 |
|---|---|
| 用户请求 | 中性蓝灰 |
| 上下文构建 | 紫色 |
| 模型调用 | 主蓝色 |
| 工具调用 | 青色 |
| 权限等待 | 黄色 |
| 压缩动作 | 橙色 |
| 成功终态 | 绿色 |
| 失败/阻塞 | 红色 |
| 暂停/恢复 | 灰蓝色 |

不能只依靠颜色表达状态，节点同时显示图标、标题和状态文字。

交互：

- 单击节点：右侧显示详情。
- 双击节点：聚焦并展开上下游。
- Hover：显示耗时、Token、状态摘要。
- 图例：按节点类型隐藏或显示。
- “只看异常”：过滤成功路径，保留错误、重试、权限和压缩节点。
- “关键路径”：高亮最终回答依赖的执行路径。

### 9.4 上下文分析视图

至少提供四种视图：

1. **组成堆叠图**：每轮模型调用各 segment Token 占比。
2. **压缩 Sankey 图**：候选上下文 → 选择/删除/压缩 → 最终 Prompt。
3. **重复注入列表**：按 `content_hash` 找出重复规则、手册和工具结果。
4. **上下文差异**：比较相邻两轮增加、删除和替换的 segment。

### 9.5 Token 视图

核心指标：

- 累计输入 Token。
- 累计输出 Token。
- 缓存输入 Token。
- 总 Token。
- 单轮峰值输入 Token。
- 工具 schema Token。
- 工具结果 Token。
- 历史对话 Token。
- 压缩节省 Token。
- 未归因 Token。
- 每千 Token 耗时。
- 如 Provider 可提供价格配置，则展示估算费用。

### 9.6 回答对比

支持选择两个回答 ID：

| 对比维度 | 示例 |
|---|---|
| 最终状态 | completed vs failed |
| 总耗时 | 32s vs 19s |
| 模型轮次 | 5 vs 3 |
| 工具调用 | 12 vs 7 |
| 输入 Token | 48k vs 27k |
| 压缩次数 | 2 vs 1 |
| 重试次数 | 3 vs 0 |
| 重复上下文 | 8k vs 1k |

对比结论必须基于结构化指标，不让模型凭回答文本主观判断性能是否改善。

## 10. 自动优化规则

第一阶段采用确定性规则，不立即引入另一个模型分析监管数据。

建议规则：

| 规则编码 | 触发条件 | 建议 |
|---|---|---|
| `CTX_DUPLICATE_CONTENT` | 同一轮相同 hash 重复注入 | 合并重复规则或历史片段 |
| `CTX_TOOL_RESULT_OVERSIZED` | 工具结果超过输入 Token 的设定比例 | 保存结构化摘要和可按需读取引用 |
| `CTX_HISTORY_DOMINANT` | 历史对话占比过高 | 使用阶段摘要替换远端历史 |
| `CTX_COMPACTION_LATE` | 接近窗口上限后才压缩 | 提前执行预算分配 |
| `TOKEN_UNATTRIBUTED_HIGH` | 未归因 Token 超阈值 | 检查工具 schema 和 Provider 包装 |
| `TOOL_DUPLICATE_CALL` | 相同工具参数重复调用 | 在运行时增加结果复用或幂等判断 |
| `TOOL_FAILURE_LOOP` | 同类错误连续出现 | 回到计划或请求用户输入，禁止盲目重试 |
| `MODEL_ROUND_EXCESSIVE` | 模型轮次超过预算 | 检查计划粒度和工具返回结构 |
| `PERMISSION_WAIT_LONG` | 权限等待占总耗时过高 | 改进权限提示和批量审批策略 |
| `OUTPUT_TOO_LONG` | 输出 Token 高但信息密度低 | 优化回答模板和风格约束 |

后续可以增加“AI 优化建议”，但必须：

1. 输入使用脱敏后的结构化监管摘要。
2. 与确定性规则结果分开展示。
3. 标记模型、Prompt 版本和生成时间。
4. 不把 AI 建议自动应用到系统提示词或规则。

## 11. Tauri Command 设计

建议命令：

```text
agent_supervision_search_answers
agent_supervision_get_answer
agent_supervision_get_run_graph
agent_supervision_get_context_analysis
agent_supervision_get_token_usage
agent_supervision_get_findings
agent_supervision_compare_answers
agent_supervision_update_finding_status
agent_supervision_delete_answer_details
```

所有查询必须包含 `username`，项目级查询还必须包含 `project_id`。

回答详情建议一次返回顶部摘要，流程图、上下文和事件明细按 Tab 懒加载，避免单次读取巨大 JSON。

## 12. 性能与可靠性

### 12.1 写入性能

- 事件先在 Rust 侧小批量聚合，按 50～200ms 或终态触发事务写入。
- 工具 stdout/stderr 只保存限制长度的脱敏 preview；完整大输出保存现有本地产物引用或按需分块，不直接塞入监管表。
- token chunk 不逐条写 SQLite。
- 所有索引围绕回答 ID、run ID、会话、项目和时间建立。

### 12.2 查询性能目标

- 完整回答 ID 查询：本机常规数据量下 100ms 内返回摘要。
- 流程图首屏：500 节点以内 1 秒内完成数据库读取和前端渲染。
- 超过 500 节点默认折叠 token chunk、重复 observation 和流式输出节点。
- 时间线分页读取，默认每页 100 条。

### 12.3 可靠性

- 启用外键并在连接初始化执行 `PRAGMA foreign_keys = ON`。
- 保持 WAL、busy timeout 和短事务。
- 写入使用稳定 ID 幂等，恢复运行不得重复生成同一 step。
- 投影失败必须记录 projector error，并允许从本地 Trace 重新构建监管投影。
- “可重建”不是写入失败时的静默兜底；运行页面必须显示采集异常。

## 13. 安全与隐私

### 13.1 本地边界

- 监管数据仅存在桌面端 `project-chat.sqlite3`。
- 不新增服务端监管写入接口。
- 不调用服务端聊天历史接口查找回答。
- 若未来支持导出，必须由用户显式操作并展示导出范围。

### 13.2 脱敏规则

写入前处理：

- Authorization、Cookie、API Key、Token、密码。
- 环境变量中的敏感值。
- 工具参数里的凭据字段。
- URL 查询参数中的敏感字段。
- 文件内容中命中的凭据模式。

脱敏必须在 Rust 采集层完成，不能只依赖前端隐藏。

### 13.3 页面权限

- 桌面端仅允许当前登录用户查看自己的本地监管记录。
- 查询必须按 `username + project_id` 隔离。
- “查看原始输入/输出”默认折叠，并对敏感类型永久脱敏。
- 删除操作必须明确说明影响范围并二次确认。

## 14. 分阶段实施计划

### 阶段 0：协议与基线冻结

目标：先定义 ID、事件、状态和 Token 口径，防止页面先行导致数据结构反复变化。

任务：

1. 确认 `assistant_message_id` 为回答检索主键。
2. 补齐 run、step、edge、context、usage 的 Rust struct。
3. 将现有 Trace 事件映射到监管 step 类型。
4. 定义 Provider usage 与 segment token 的口径。
5. 定义脱敏规则和禁止记录字段。
6. 产出固定测试夹具。

验收：

- 同一回答在暂停恢复后仍只有一个回答主记录。
- 所有流程节点都有稳定 ID、状态和父子/依赖关系。
- 文档和代码枚举一致。

### 阶段 1：回答 ID 检索与基础执行链路 MVP

目标：复制回答 ID 后能查看执行链路。

任务：

1. 增加 SQLite answer、run、step、edge 表。
2. 增加运行时 projector 和增量写入。
3. 增加 Tauri 查询 Commands。
4. 新增 `/ai/supervision` 页面。
5. 使用 ECharts Graph 展示流程图。
6. 聊天回答菜单增加“复制回答 ID”和“查看执行监管”。
7. 展示错误、重试、权限、暂停和恢复节点。

验收：

- 输入完整回答 ID 可精确打开对应回答。
- 流程图节点与 Trace 事件数量和状态一致。
- 点击工具节点可查看脱敏后的输入、输出和耗时。
- 服务端停机时仍能查看已记录的本地监管数据。

### 阶段 2：上下文组成与 Token 监管

目标：解释每轮输入 Token 从哪里来。

任务：

1. 上下文组装器输出稳定 segment 列表。
2. 增加 context snapshot 和 segment 表。
3. 接入 Provider usage 权威数据。
4. 增加 TokenMeter adapter 接口。
5. 记录压缩前后 Token、选择状态和原因。
6. 增加堆叠图、趋势图、Sankey 图和未归因 Token 告警。

验收：

- 每轮模型调用都有 Provider usage。
- 支持的模型可以看到上下文分段 Token。
- 不支持 tokenizer 的模型明确显示 unsupported。
- 压缩前后差异可追溯到具体 segment。

### 阶段 3：自动优化建议与异常检测

目标：从监管数据中产生可执行优化方向。

任务：

1. 实现确定性优化规则引擎。
2. 建立重复上下文、工具失败循环、无效重试和高 Token 规则。
3. 增加 findings 列表和处理状态。
4. 支持从 finding 跳转到证据节点。
5. 支持人工备注和“已解决/忽略”。

验收：

- 每条建议包含规则编码、证据、影响和建议动作。
- 建议可定位到具体 model round、segment 或 tool step。
- 规则不自动修改 Prompt、项目规则或执行策略。

### 阶段 4：回答对比与优化闭环

目标：验证优化前后的实际收益。

任务：

1. 增加双回答对比。
2. 对比耗时、轮次、工具次数、失败率、Token 和压缩收益。
3. 支持对比标记，例如 baseline/candidate。
4. 输出本地优化结论报告。
5. 增加回归基线和阈值告警。

验收：

- 可以证明一次优化减少了哪些 Token 或执行步骤。
- 指标变差时明确显示，不只展示正向结果。
- 对比报告可在本地导出，但不会自动上传。

### 阶段 5：长期容量与治理

目标：控制监管库体积并保持数据质量。

任务：

1. 增加本地保留策略和容量统计。
2. 增加 orphan 数据、一致性和外键检查。
3. 增加 SQLite vacuum/cleanup 的显式维护入口。
4. 增加 schema version 和迁移测试。
5. 增加监管采集健康状态。

验收：

- 清理策略不会删除人工标记或仍在运行的数据。
- 数据库异常可以明确诊断。
- schema 升级失败不会静默继续运行。

## 15. 建议代码改动范围

### 15.1 Rust/Tauri

新增或调整：

```text
web-admin/frontend/src-tauri/src/agent_supervision_store.rs
web-admin/frontend/src-tauri/src/agent_supervision_projector.rs
web-admin/frontend/src-tauri/src/agent_supervision_token_meter.rs
web-admin/frontend/src-tauri/src/main.rs
web-admin/frontend/src-tauri/Cargo.toml
```

与现有 `project_chat_store.rs` 共享数据库连接初始化和 schema version 策略，避免每个模块分别设置 WAL、busy timeout 和 migrations。

### 15.2 前端

新增或调整：

```text
web-admin/frontend/src/views/desktop/AgentSupervision.vue
web-admin/frontend/src/modules/agent-supervision/components/AnswerSearchBar.vue
web-admin/frontend/src/modules/agent-supervision/components/ExecutionGraph.vue
web-admin/frontend/src/modules/agent-supervision/components/ExecutionNodeDrawer.vue
web-admin/frontend/src/modules/agent-supervision/components/ContextCompositionPanel.vue
web-admin/frontend/src/modules/agent-supervision/components/TokenUsagePanel.vue
web-admin/frontend/src/modules/agent-supervision/components/OptimizationFindings.vue
web-admin/frontend/src/modules/agent-supervision/services/agentSupervisionStorage.js
web-admin/frontend/src/modules/agent-supervision/mappers/agentSupervisionGraphMapper.js
web-admin/frontend/src/router/index.js
web-admin/frontend/src/views/projects/ProjectChat.vue
```

### 15.3 测试

建议新增：

```text
web-admin/frontend/scripts/check-agent-supervision-local-storage.mjs
web-admin/frontend/scripts/check-agent-supervision-answer-search.mjs
web-admin/frontend/scripts/check-agent-supervision-graph.mjs
web-admin/frontend/scripts/check-agent-supervision-token-usage.mjs
```

Rust 单测覆盖：

- 回答 ID 查询。
- 回答、run、step、edge 事务写入。
- 幂等事件重复写入。
- 暂停恢复关联。
- 会话删除级联。
- 上下文 segment 压缩前后记录。
- usage 与 model step 关联。
- 脱敏。
- 并发读写。

## 16. 测试策略

### 16.1 固定夹具

至少准备以下运行夹具：

1. 单轮回答，无工具。
2. 多轮模型调用和两个工具。
3. 权限等待后继续。
4. 工具失败后重试成功。
5. 连续失败后阻塞。
6. 上下文超过预算后压缩。
7. 暂停后从 checkpoint 恢复。
8. 服务端离线时查看本地监管记录。
9. 相同事件重复到达。
10. 超大工具输出和敏感字段脱敏。

### 16.2 一致性断言

- `answer.status` 必须与最后一个 run 终态一致。
- `model_round_count` 必须与 model_call step 数量一致。
- `tool_call_count` 必须与唯一 call ID 数量一致。
- 每条 edge 的 source 和 target 必须存在。
- Provider usage 必须关联一个 model step。
- `sum(segment token) + unattributed_tokens` 应与 Provider input token 对齐到允许误差。
- 已完成运行不能保留未完成工具调用，除非明确标记 detached。
- 敏感值不得出现在 SQLite preview 和前端 DOM。

## 17. 验收标准

### 17.1 功能验收

- 可以复制任意新产生的回答 ID 并在监管页面检索。
- 可以查看回答、用户问题、运行状态和关联 ID。
- 可以通过流程图理解完整执行链路。
- 可以查看每轮模型调用和每次工具调用。
- 可以查看上下文组成、压缩动作和 Token。
- 可以查看确定性优化建议和证据。
- 可以对比两个回答的关键指标。

### 17.2 数据边界验收

- 监管数据只写入桌面本地 SQLite。
- 网络断开后仍可以检索和查看历史监管记录。
- 服务端没有新增监管历史写入。
- 不读取旧 `localStorage` 作为监管数据来源。
- SQLite 写入失败时明确报错，不切换到其他存储。

### 17.3 可理解性验收

- 新用户可以在 30 秒内根据回答 ID 找到流程图。
- 流程图不依赖颜色也能辨认节点状态。
- 默认视图突出关键路径，不被流式 token 和重复日志淹没。
- 点击异常节点能看到原因、证据和下一步建议。

### 17.4 性能验收

- 回答 ID 精确查询目标 100ms 内返回摘要。
- 500 节点以内流程图目标 1 秒内可交互。
- 监管写入不明显阻塞模型流式输出和工具执行。
- 长期使用后可以查看本地容量并执行显式清理。

## 18. 风险与对策

| 风险 | 对策 |
|---|---|
| Trace 事件字段不完整 | 先冻结协议，缺失字段显示未采集 |
| Provider 不返回 usage | 标记 provider_usage_missing，不伪造权威 Token |
| tokenizer 不支持某模型 | 显示 unsupported，保留字符与字节体积 |
| 流程图节点过多 | 默认聚合流式事件、折叠重复 observation |
| SQLite 高频写入影响执行 | Rust 批量短事务，不逐 token 写库 |
| 工具输出包含敏感信息 | Rust 写入前统一脱敏 |
| 数据库持续增长 | 保留策略、容量面板、显式清理 |
| 暂停恢复导致重复节点 | 稳定 event ID 和唯一约束幂等 |
| 自动优化建议误导 | 先使用确定性规则，展示证据，不自动应用 |
| 监管页面反向依赖服务端 | 所有详情查询走 Tauri 本地 Commands |

## 19. 推荐实施顺序

推荐按以下顺序实施，不能先做漂亮页面再补采集：

1. 冻结回答、运行、步骤、上下文和 Token 协议。
2. 建立 SQLite 表和 migrations。
3. 接入 Trace projector 和幂等写入。
4. 完成回答 ID 精确查询。
5. 完成基础流程图。
6. 接入上下文 segment 和 Provider usage。
7. 完成上下文与 Token 图表。
8. 增加确定性优化规则。
9. 增加回答对比。
10. 最后补容量治理和长期回归。

## 20. 第一版交付范围建议

为了尽快形成可用闭环，第一版只交付：

1. 回答 ID 搜索。
2. 回答与运行摘要。
3. 模型、工具、权限、错误、暂停恢复流程图。
4. Provider 输入、输出、缓存和总 Token。
5. 每轮耗时、Token 和工具次数。
6. 本地 SQLite 存储与会话删除级联。
7. 聊天回答的“复制回答 ID”和“查看执行监管”。

第二版再交付上下文 segment、压缩 Sankey、自动建议和回答对比。这样可以先验证回答 ID 到执行链路的主路径，再扩展上下文优化能力。

## 21. 最终技术结论

本功能应作为桌面智能体的本地可观测投影，而不是新的服务端日志系统：

- `assistant_message_id` 是用户入口。
- Trace Event 是执行事实。
- SQLite 是本地唯一监管存储。
- Tauri/Rust 负责采集、脱敏、计量和查询。
- Vue 3 + Element Plus 负责交互。
- ECharts Graph 负责执行链路，Line/Bar/Sankey 负责 Token 和上下文分析。
- Provider usage 是总 Token 权威数据。
- 上下文组装器负责分段 Token 和压缩归因。
- 任何未采集、不支持或归因不完整的数据都必须明确展示，不能静默兜底。

