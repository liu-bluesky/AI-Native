# P3：状态投影、计划恢复与 Inbox

- 状态：`pending`
- 前置阶段：P2 的独立提交
- 当前阶段：P3
- 下一计划文档：`docs/liuAgent-cli/runtime-driver-plan/P4-跨平台进程治理与收尾.md`
- Git 提交：`feat(runtime): complete phase P3 projection plan recovery and inbox`

## 目标

让 Runtime、计划和用户输入都能持久化、恢复和增量推进，避免重复执行或丢失追问。

## 改造前参考代码

先读取 `docs/liuAgent-cli/runtime-driver-plan/DeepSeek-Harness模块映射.md` 的 P3 节点，再检查其中列出的 DeepSeek 源码和当前项目入口。完成对比后，先更新本阶段方案，再修改代码。

## 实施范围

- 新增 `liuagent_core/projection.rs`。
- EventLog 折叠生成 RuntimeStateProjection。
- 保存 `last_event_seq`、`current_step_id` 和 `recoverable`。
- PlanStep 增加依赖、attempt、重试上限和恢复标志。
- 增加 checkpoint 和应用重启恢复。
- 新增会话级 Runtime Inbox。
- 支持 `queue_followup/interrupt_and_append/new_turn`。

## 验收

- 页面重开后能从增量事件恢复当前状态。
- 已完成工具不会重复执行。
- 暂停任务能从正确的 `step_id` 继续。
- 运行期间的新消息不会被静默丢弃。
- 重复领取 Inbox 消息不会重复处理。

## 完成动作

验证通过后按以下顺序执行，不要停留在本文件：

1. 将本文件的 `状态` 改为 `completed`，补充完成日期、实际改动、验证命令和验证结果。
2. 执行：`git diff --check`，确认没有当前阶段之外的修改。
3. 创建提交：`feat(runtime): complete phase P3 projection plan recovery and inbox`。
4. 提交成功后，立即读取并进入：

   `docs/liuAgent-cli/runtime-driver-plan/P4-跨平台进程治理与收尾.md`

5. 读取 P4 文件全文后，只将 P4 标记为 `ready`，总结 P4 的目标、依赖和验收标准。
6. 停止当前执行轮次，不修改 P4 代码；等待新的“开始执行下一阶段”指令。
