# P2：RuntimeDriver 与事件日志

- 状态：`pending`
- 前置阶段：P1 的独立提交
- 当前阶段：P2
- 下一计划文档：`docs/liuAgent-cli/runtime-driver-plan/P3-状态投影计划恢复与Inbox.md`
- Git 提交：`feat(runtime): complete phase P2 runtime driver and event log`

## 目标

把长流程拆成明确 Driver，并将 Runtime 事件升级为带顺序、版本和游标的持久 EventLog。

## 改造前参考代码

先读取 `docs/liuAgent-cli/runtime-driver-plan/DeepSeek-Harness模块映射.md` 的 P2 节点，再检查其中列出的 DeepSeek 源码和当前项目入口。完成对比后，先更新本阶段方案，再修改代码。

## 实施范围

- 新增 `liuagent_core/driver.rs`。
- Driver 负责 Inbox、Plan、模型、工具、审批和终态推进。
- 每个步骤边界检查取消、暂停和 deadline。
- 事件统一包含 `event_id/event_seq/run_id/schema_version`。
- 状态、计划、工具和终态事件立即落盘。
- 流式增量和命令输出按批次落盘。
- 前端按 `run_id + event_seq` 去重和补偿。

## 验收

- Driver 不依赖 Vue 页面存在。
- 模型或工具失败后不会卡死主循环。
- 事件序列在单个 Run 内单调递增。
- 断线后按游标可以补齐事件。
- 终态事件只产生一次。

## 完成动作

验证通过后按以下顺序执行，不要停留在本文件：

1. 将本文件的 `状态` 改为 `completed`，补充完成日期、实际改动、验证命令和验证结果。
2. 执行：`git diff --check`，确认没有当前阶段之外的修改。
3. 创建提交：`feat(runtime): complete phase P2 runtime driver and event log`。
4. 提交成功后，立即读取并进入：

   `docs/liuAgent-cli/runtime-driver-plan/P3-状态投影计划恢复与Inbox.md`

5. 读取 P3 文件全文后，只将 P3 标记为 `ready`，总结 P3 的目标、依赖和验收标准。
6. 停止当前执行轮次，不修改 P3 代码；等待新的“开始执行下一阶段”指令。
