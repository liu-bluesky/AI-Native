# P0：异步 Job 与交互不卡顿

- 状态：`pending`
- 前置阶段：无
- 当前阶段：P0
- 下一计划文档：`docs/liuAgent-cli/runtime-driver-plan/P1-可取消JobRegistry.md`
- Git 提交：`feat(runtime): complete phase P0 async job entry`

## 目标

让启动接口快速返回 `run_id`，前端通过事件和 Job 状态展示运行过程，不再等待整轮模型和工具执行结束。

## 改造前参考代码

先读取 `docs/liuAgent-cli/runtime-driver-plan/DeepSeek-Harness模块映射.md` 的 P0 节点，再检查其中列出的 DeepSeek 源码和当前项目入口。完成对比后，先更新本阶段方案，再修改代码。

## 实施范围

- 新增异步 Runtime Job 启动入口。
- 保留旧入口作为临时兼容路径，但默认切换到异步入口。
- 正式 Runtime 事件通道只保留一个。
- 正常运行停止 600ms 高频轮询。
- 前端流式文本按 50–100ms 节流刷新。
- loading、暂停和完成状态绑定 Runtime Projection/快照。

## 重点文件

- `web-admin/frontend/src-tauri/src/main.rs`
- `web-admin/frontend/src-tauri/src/liuagent_core/types.rs`
- `web-admin/frontend/src/utils/native-desktop-bridge.js`
- `web-admin/frontend/src/views/projects/ProjectChat.vue`

## 验收

- 启动调用立即返回 `run_id`。
- 页面在任务完成前保持可输入、可切换和可关闭。
- 事件持续到达，终态事件能正确关闭运行状态。
- 旧事件通道不会与正式通道同时发送。
- 断线时不会丢失已落盘事件。

## 完成动作

验证通过后按以下顺序执行，不要停留在本文件：

1. 将本文件的 `状态` 改为 `completed`，补充完成日期、实际改动、验证命令和验证结果。
2. 执行：`git diff --check`，确认没有当前阶段之外的修改。
3. 创建提交：`feat(runtime): complete phase P0 async job entry`。
4. 提交成功后，立即读取并进入：

   `docs/liuAgent-cli/runtime-driver-plan/P1-可取消JobRegistry.md`

5. 读取 P1 文件全文后，只将 P1 标记为 `ready`，总结 P1 的目标、依赖和验收标准。
6. 停止当前执行轮次，不修改 P1 代码；等待新的“开始执行下一阶段”指令。
