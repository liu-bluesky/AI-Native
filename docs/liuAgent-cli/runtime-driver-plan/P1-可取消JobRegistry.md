# P1：可取消 JobRegistry

- 状态：`pending`
- 前置阶段：P0 的独立提交
- 当前阶段：P1
- 下一计划文档：`docs/liuAgent-cli/runtime-driver-plan/P2-RuntimeDriver与事件日志.md`
- Git 提交：`feat(runtime): complete phase P1 cancellable job registry`

## 目标

用统一 JobRegistry 管理 Runtime 的状态、并发、暂停、恢复、取消、超时和资源回收。

## 改造前参考代码

先读取 `docs/liuAgent-cli/runtime-driver-plan/DeepSeek-Harness模块映射.md` 的 P1 节点，再检查其中列出的 DeepSeek 源码和当前项目入口。完成对比后，先更新本阶段方案，再修改代码。

## 实施范围

- 新增 `liuagent_core/jobs.rs`。
- 用 `run_id` 替代分散的进程内运行标记。
- 实现 `queued/running/waiting/stopping/paused/completed/failed/cancelled` 状态。
- pause/resume/cancel 全部幂等。
- 引入 CancellationToken 或等价取消控制器。
- 为模型、MCP、命令和用户等待增加超时。
- 任务销毁时回收 Driver、请求、工具和子进程。

## 验收

- 重复暂停和取消不会产生重复终态。
- 取消后不会遗留已知子进程。
- 超时有稳定错误码和终态事件。
- Job 快照不暴露内部可变状态。
- 应用关闭后任务能进入可恢复或明确失败状态。

## 完成动作

验证通过后按以下顺序执行，不要停留在本文件：

1. 将本文件的 `状态` 改为 `completed`，补充完成日期、实际改动、验证命令和验证结果。
2. 执行：`git diff --check`，确认没有当前阶段之外的修改。
3. 创建提交：`feat(runtime): complete phase P1 cancellable job registry`。
4. 提交成功后，立即读取并进入：

   `docs/liuAgent-cli/runtime-driver-plan/P2-RuntimeDriver与事件日志.md`

5. 读取 P2 文件全文后，只将 P2 标记为 `ready`，总结 P2 的目标、依赖和验收标准。
6. 停止当前执行轮次，不修改 P2 代码；等待新的“开始执行下一阶段”指令。
