action_markers
这个字段干嘛的

---

• 发现问题了，根因不在“进度描述文案”，而在桌面端本地智能体的 runtime.rs Agent Loop：

实现型任务里，read_file / search_text / list_files 成功后会一直被当成“正常推进”，没
有探索预算，也没有要求模型转入 write_file / apply_patch。所以“现在没有登录页在做一
个登录页”这种任务，模型可以连续读文件、搜文件很多轮，却不被 runtime 判定为跑偏。更
严重的是：只读完以后如果模型直接空工具调用说“已完成”，以前也可能按 no_tool_calls 结
束。

我已在 web-admin/frontend/src-tauri/src/liuagent_core/runtime.rs:62 修复：

- 实现型任务新增探索预算：连续 3 轮只读/搜索/列目录后，runtime 会插入控制消息，要求
  下一轮必须 write_file / apply_patch / run_command，否则说明阻塞。

- 如果模型继续只读，会停止为 exploration_budget_exceeded，不再无限循环。
- 如果只读后模型直接说完成，但没有任何写入/补丁/命令，也不会被判成功。
- 普通查询类任务不受影响，仍允许多轮读取后回答。
- 用户可见失败文案也会明确显示“实现型任务持续读取/搜索，没有进入写入或执行”。

验证已通过：

- cargo test liuagent_core::runtime::tests：58 个测试通过
- cargo fmt --check：通过
- git diff --check：通过

这次修的是桌面端本地智能体/Tauri runtime，不是后端智能体。

---

• 你说的区别是准确的：之前桌面智能体显示的是固定模板，不是 Codex 那种“我现在发现了什
么、所以接下来要做什么”。

我这次已改成两层：

1. 后端 runtime 事件新增动态字段：
   web-admin/frontend/src-tauri/src/liuagent_core/runtime.rs:3579

   现在 progress_update 会带：
   - current_focus：当前关注点，比如“收集实现所需的文件结构和现有页面风格”
   - next_action：下一步具体动作，比如“读取 register.html，复用注册页的视觉风格和
     表单交互”

   - summary：不再只是“标准模型工具调用：read_file”，会根据工具参数生成更像人话的
     目的说明

2. 前端不再固定显示“推进当前任务”：
   web-admin/frontend/src/views/projects/ProjectChat.vue:7760

   现在优先展示 runtime 下发的 current_focus，再展示 summary 和 next_action。

改后效果大概会从：

推进当前任务
准备执行本地工具：标准模型工具调用：read_file
下一步：执行模型请求的 1 个本地工具调用

变成更接近：

收集实现所需的文件结构和现有页面风格 - 准备读取 register.html 第 700-819 行，复用注册页的视觉风格和表单交互 - 下一步：读取 register.html 第 700-819 行，复用注册页的视觉风格和表单交互

已验证：

- cargo test liuagent_core::runtime::tests：58 个通过
- cargo fmt --check：通过
- git diff --check：通过
- npm run build：通过，只有已有的 mockjs eval 和 chunk size 警告

这次解决的是“展示内容固定化”，不是只修循环。
