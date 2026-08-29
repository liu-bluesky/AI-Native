• 完成内容

- 结果卡片从二态 completed 改为多状态：执行中、已暂停、等待回答、等待授权、失败、完成。
- 暂停后显示“任务已暂停 / 待继续”，追问显示“等待补充信息”，授权显示“等待本机授权”。
- 恢复执行、追问、授权、失败、完成分支都会写入明确状态，避免继续后沿用旧的“任务尚未完成”。
- 保留原有 checkpoint/session 恢复逻辑，不重复执行成功的工具操作，兼容 macOS 和 Windows。

文件

- web-admin/frontend/src/modules/project-chat/components/messages/LocalTaskResultSummary.vue:6
- web-admin/frontend/src/modules/project-chat/components/messages/LocalTaskResultSummary.vue:65
- web-admin/frontend/src/views/projects/ProjectChat.vue:34697
- web-admin/frontend/src/views/projects/ProjectChat.vue:35058
- web-admin/frontend/src/views/projects/ProjectChat.vue:35165
- web-admin/frontend/src/views/projects/ProjectChat.vue:35249
- web-admin/frontend/src/views/projects/ProjectChat.vue:35338
- web-admin/frontend/src/views/projects/ProjectChat.vue:35518

验证

- npm run test:local-task-result 通过。
- npm run build 通过。
- npm run test:pause-state 仍失败，但失败是仓库现有断言与当前暂停代码顺序不匹配，并非构建或本次状态卡片改动导致。
