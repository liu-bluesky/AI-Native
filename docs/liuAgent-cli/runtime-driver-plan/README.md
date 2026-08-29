# Runtime 驱动器改造阶段计划

## 使用方式

本目录是《基于 DeepSeek-Harness 的 Runtime 驱动器改造计划》的可执行拆分。阶段按 `P0 → P1 → P2 → P3 → P4` 顺序推进。

每个阶段遵守以下规则：

- 一个阶段对应一个独立 Git 提交版本。
- 当前阶段未完成或被标记为 `blocked` 时，不得进入下一阶段。
- 完成当前阶段后，按照该阶段文档“完成动作”中的明确路径自动读取下一文件。
- 读取下一文件后只标记为 `ready`，不得在同一轮自动执行下一阶段。
- 下一阶段必须等待明确的“开始执行下一阶段”指令。
- 每次进入阶段先检查前置提交、工作区状态和验收条件。
- 不跨阶段混合无关代码重构。

阶段状态：

```text
ready -> executing -> validating -> completed -> committed
```

读取下一阶段后，下一阶段保持 `ready`；只有收到新的明确启动指令，才能进入 `executing`。

## 阶段索引

| 阶段 | 文档 | 目标 | Git 提交主题 |
|---|---|---|---|
| P0 | `P0-异步Job与交互不卡顿.md` | 异步启动、单事件通道、流式节流 | `feat(runtime): complete phase P0 async job entry` |
| P1 | `P1-可取消JobRegistry.md` | Job 状态、取消、暂停、超时和资源回收 | `feat(runtime): complete phase P1 cancellable job registry` |
| P2 | `P2-RuntimeDriver与事件日志.md` | Driver 主循环、EventLog、事件游标 | `feat(runtime): complete phase P2 runtime driver and event log` |
| P3 | `P3-状态投影计划恢复与Inbox.md` | Projection、checkpoint、计划恢复和输入队列 | `feat(runtime): complete phase P3 projection plan recovery and inbox` |
| P4 | `P4-跨平台进程治理与收尾.md` | macOS/Windows 进程治理、全量验收和收尾 | `feat(runtime): complete phase P4 cross-platform runtime hardening` |

## 固定执行提示

```text
当前阶段已完成并已提交 Git 版本。
请立即读取指定的下一阶段文件：<这里必须替换为当前阶段文档中写明的绝对工作区相对路径>
读取完成后只总结该阶段并标记为 ready，不要修改该阶段代码。
停止当前执行轮次，等待新的“开始执行下一阶段”指令。
禁止在同一轮跨越多个阶段。
```

P4 完成后，下一计划文档为 `none`，进入全量验证和交付总结。

## 改造前代码检查规则

每个阶段开始时，AI 必须按以下顺序工作：

1. 读取当前阶段文档。
2. 读取 `DeepSeek-Harness模块映射.md` 中当前阶段对应的模块路径。
3. 实际打开并检查参考模块的源码、测试和 `invariant.ts` 文件。
4. 检查当前项目对应入口和已有实现。
5. 对比两边的状态模型、错误处理、取消边界、持久化方式和平台差异。
6. 先更新解决方案，再开始修改代码。

如果参考代码和当前项目技术栈或运行边界不同，必须采用适配方案，不能直接复制 TypeScript、Node 或 Linux 专属实现。
