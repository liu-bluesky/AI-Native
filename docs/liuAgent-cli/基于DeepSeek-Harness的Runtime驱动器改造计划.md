# 基于 DeepSeek-Harness 的 Runtime 驱动器改造总计划

> 本文件是总入口和阶段索引，不承载具体编码任务。
> P0–P4 的实施细节、文件范围、验收条件和完成动作统一放在 `docs/liuAgent-cli/runtime-driver-plan/`。

## 1. 改造目标

把当前桌面本地智能体从“同步调用后等待结果”的 Runtime，改造成类似 DeepSeek-Harness 的可驱动、可恢复、可取消执行系统：

```text
RuntimeDriver 驱动器
  + EventLog 持久事件日志
  + CancellableJob 可取消任务
  + StateProjection 状态投影
  + PlanState 可恢复计划
  + RuntimeInbox 会话输入队列
```

最终解决：

- 页面等待长任务导致交互卡顿。
- 事件广播、轮询和持久化重复执行。
- 暂停/取消不能及时中断模型、MCP 和子进程。
- 应用重启后无法从准确步骤恢复。
- 同一会话的新输入被 `runtime.already_running` 丢弃。
- macOS / Windows 子进程和 Shell 行为不一致。

## 2. 参考设计

参考目录：

`/Volumes/work_mac_1_5T/self/deepseek-harness/`

重点借鉴：

| DeepSeek-Harness 设计 | 当前项目对应目标 |
|---|---|
| `packages/jobs/jobs/src/types.ts` | Job 取消、完成、快照和资源释放 |
| `packages/jobs/jobs-local/src/index.ts` | JobRegistry、Owner、并发限制和销毁回收 |
| `packages/plan/plan-mode/src/index.ts` | 计划状态持久化和用户审批 |
| `packages/interaction/user-questions/src/index.ts` | 用户等待支持 AbortSignal |
| `docs/architecture.zh.md` | 持久事件、实时事件和能力事件分层 |
| `docs/tool-execution-pipeline.zh.md` | 权限、超时、重试和工具终态 |

完整功能节点与参考模块路径见：

`docs/liuAgent-cli/runtime-driver-plan/DeepSeek-Harness模块映射.md`

执行任何阶段前，AI 必须先读取该映射文档中对应的 DeepSeek 源码路径，再检查当前项目实现，最后根据两边的实际代码调整解决方案。禁止只根据模块名称或文档描述直接照搬设计。

## 3. 目标架构

```text
ProjectChat.vue
    |
    +-- startRuntimeJob()       立即返回 run_id
    +-- subscribeRuntimeEvents()
    +-- listRuntimeEvents(cursor)
    +-- pauseRuntimeJob(run_id)
    +-- resumeRuntimeJob(run_id)
    +-- cancelRuntimeJob(run_id)
    |
    v
Tauri Runtime Gateway
    |
    +-- JobRegistry
    +-- RuntimeDriver
    +-- CancellationToken
    +-- EventLog
    +-- StateProjection
    +-- RuntimePlan
    +-- RuntimeInbox
    +-- ProcessSupervisor
```

职责边界：

- **Driver**：领取输入、推进计划、调用模型、执行工具和生成终态。
- **Job**：管理一次 Runtime 的状态、取消、暂停、完成和资源回收。
- **EventLog**：记录已发生事实，使用 `event_id + event_seq` 去重和补偿。
- **StateProjection**：由事件折叠得到当前状态，用于查询和恢复。
- **PlanState**：记录步骤、依赖、重试次数和恢复位置。
- **Inbox**：保存运行期间的新输入，避免消息丢失。
- **Vue**：只展示事件和投影，不根据原始请求是否 pending 推测任务状态。

## 4. 阶段执行顺序

必须严格按以下路径推进：

### P0：异步 Job 与交互不卡顿

文档：`docs/liuAgent-cli/runtime-driver-plan/P0-异步Job与交互不卡顿.md`

核心结果：启动接口立即返回 `run_id`，统一事件通道，停止正常运行期间的高频轮询，对流式事件节流。

Git 提交：

`feat(runtime): complete phase P0 async job entry`

完成后自动进入：

`docs/liuAgent-cli/runtime-driver-plan/P1-可取消JobRegistry.md`

### P1：可取消 JobRegistry

文档：`docs/liuAgent-cli/runtime-driver-plan/P1-可取消JobRegistry.md`

核心结果：建立统一 Job 状态、取消、暂停、恢复、超时和资源回收机制。

Git 提交：

`feat(runtime): complete phase P1 cancellable job registry`

完成后自动进入：

`docs/liuAgent-cli/runtime-driver-plan/P2-RuntimeDriver与事件日志.md`

### P2：RuntimeDriver 与事件日志

文档：`docs/liuAgent-cli/runtime-driver-plan/P2-RuntimeDriver与事件日志.md`

核心结果：拆出 Driver 主循环，正式实现带顺序、版本和游标的 EventLog。

Git 提交：

`feat(runtime): complete phase P2 runtime driver and event log`

完成后自动进入：

`docs/liuAgent-cli/runtime-driver-plan/P3-状态投影计划恢复与Inbox.md`

### P3：状态投影、计划恢复与 Inbox

文档：`docs/liuAgent-cli/runtime-driver-plan/P3-状态投影计划恢复与Inbox.md`

核心结果：实现 Projection、checkpoint、计划步骤恢复和会话输入队列。

Git 提交：

`feat(runtime): complete phase P3 projection plan recovery and inbox`

完成后自动进入：

`docs/liuAgent-cli/runtime-driver-plan/P4-跨平台进程治理与收尾.md`

### P4：跨平台进程治理与收尾

文档：`docs/liuAgent-cli/runtime-driver-plan/P4-跨平台进程治理与收尾.md`

核心结果：完成 macOS / Windows 进程树治理、双平台验证和最终交付。

Git 提交：

`feat(runtime): complete phase P4 cross-platform runtime hardening`

P4 完成后不再进入新计划文档，直接执行全量验证和交付总结。

## 5. 统一阶段规则

### 5.1 单阶段执行闸门

本计划默认采用“单阶段、单提交、单轮执行”模式。自动读取下一阶段文档，不等于自动执行下一阶段。

阶段状态必须按以下顺序推进：

```text
ready -> executing -> validating -> completed -> committed
```

允许的行为边界：

- 总入口打开后，只能读取并执行 P0。
- 当前阶段完成并提交后，可以自动读取下一阶段文档。
- 读取下一阶段后，只能将下一阶段标记为 `ready`，总结目标、依赖和验收标准。
- 当前执行轮次必须停止，不得修改下一阶段代码。
- 下一阶段必须等待新的明确执行指令后，才能进入 `executing`。
- 任何一次执行都不得跨越两个或以上阶段。

禁止以下行为：

- 读取 P1 后自动开始 P1 实现。
- 在同一轮连续执行 P0、P1、P2、P3 或 P4。
- 未完成当前阶段 Git 提交就进入下一阶段。
- 以“自动访问下一文档”为理由跳过阶段启动指令。

每个阶段只允许一个独立 Git 版本，严格执行：

1. 进入阶段后先读取对应阶段文档全文，并将阶段标记为 `ready`。
2. 收到明确的阶段启动指令后，才将阶段标记为 `executing`。
3. 读取 `docs/liuAgent-cli/runtime-driver-plan/DeepSeek-Harness模块映射.md` 中该阶段的参考模块路径。
4. 打开并检查列出的 DeepSeek 源码、测试和不变量文件，提取可借鉴的生命周期、错误处理和边界行为。
5. 检查当前项目实现，确认真实入口、数据流、平台差异和已有兼容逻辑。
6. 基于两边代码重新调整本阶段解决方案，记录采用、改造和不采用的设计。
7. 检查前置阶段提交、工作区状态和当前验收条件。
8. 只修改当前阶段范围内的代码、测试和文档。
9. 将阶段标记为 `validating`，运行当前阶段规定的验证命令。
10. 更新阶段文档的 `状态`、完成日期、实际改动和验证结果。
11. 执行 `git diff --check`。
12. 确认没有无关改动后，创建当前阶段指定 Git 提交，并将阶段标记为 `committed`。
13. Git 提交成功后，按照当前阶段文档中写明的明确路径，自动读取下一阶段文档。
14. 读取下一阶段后，只将下一阶段标记为 `ready`，总结其目标、依赖和验收标准，然后停止当前执行轮次。

阶段未完成、验证失败或依赖未满足时：

- 将阶段标记为 `blocked`。
- 记录失败命令、错误摘要和恢复条件。
- 不创建“完成”提交。
- 不进入下一阶段。

## 6. 完成后的固定语言提示

阶段提交成功后，下一轮执行上下文必须使用实际路径，不得使用“下一个文档”这类模糊表述：

```text
当前阶段已完成并已提交 Git 版本。
请立即读取并进入下一个计划文档：<当前阶段文档中写明的实际路径>
读取后只总结下一阶段的目标、依赖、改动范围和验收标准，并将其标记为 ready。
停止当前执行轮次，不要修改下一阶段代码。
等待新的明确指令“开始执行下一阶段”后，才能进入 executing。
禁止在同一轮跨越多个阶段。
先检查前置阶段提交、工作区状态和本阶段验收条件；如发现阻塞，标记 blocked 并记录原因，不得跳过验证。
```

实际路径链已经固定为：

```text
docs/liuAgent-cli/runtime-driver-plan/P0-异步Job与交互不卡顿.md
  -> docs/liuAgent-cli/runtime-driver-plan/P1-可取消JobRegistry.md
  -> docs/liuAgent-cli/runtime-driver-plan/P2-RuntimeDriver与事件日志.md
  -> docs/liuAgent-cli/runtime-driver-plan/P3-状态投影计划恢复与Inbox.md
  -> docs/liuAgent-cli/runtime-driver-plan/P4-跨平台进程治理与收尾.md
  -> 全量验证与交付总结
```

## 7. 最终验收标准

全部阶段完成后，必须确认：

- Runtime 启动接口不等待整轮任务结束。
- 每个任务拥有稳定的 `run_id`。
- 每个事件拥有稳定的 `event_id + event_seq`。
- 正常运行不依赖 600ms 高频轮询。
- 暂停、恢复、取消全部幂等。
- 模型、工具、审批和用户问题都有超时与取消。
- 已完成步骤不会在恢复时重复执行。
- 同一会话的新输入不会被静默丢弃。
- 页面关闭或切换不会导致 Runtime 丢失。
- macOS 和 Windows 都能回收完整子进程树。
- Runtime 重启后能够从 checkpoint 继续。
- 失败、暂停、取消、等待用户和完成均有明确终态。

## 8. 变更范围总览

预计涉及：

- `web-admin/frontend/src-tauri/src/main.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/runtime.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/types.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/state`
- `web-admin/frontend/src-tauri/src/liuagent_core/jobs.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/driver.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/projection.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/process_supervisor.rs`
- `web-admin/frontend/src/utils/native-desktop-bridge.js`
- `web-admin/frontend/src/views/projects/ProjectChat.vue`

具体文件必须以当前阶段文档为准，不得一次性修改全部范围。

## 9. 风险与回滚

- 每个阶段提交都是独立回滚边界。
- 保留旧入口作为临时兼容路径，验证通过后再切换默认入口。
- 新事件格式增加 `schema_version`，不直接破坏旧状态文件。
- 取消失败时只能标记 `stopping` 或 `failed`，不能伪造为 `cancelled`。
- macOS 和 Windows 的进程治理必须分别实现和验证。
- 现有未提交改动不得混入阶段提交。
