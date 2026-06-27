• 现在的逻辑不是“附件不走大模型”，而是：

- 文档类附件：前端桌面先本地抽取文字，再把文字放进大模型 prompt。
- 图片类附件：如果模型模式支持 inline_image，会作为多模态图片发给大模型。
- provider_file 模式：才会通过桌面端上传到模型供应商，拿 provider_file_id。

你觉得奇怪是对的：如果你的产品预期是“附件由前端桌面直接上传给大模型供应商，不做本地解析主流程”，那我刚才的修复偏保守了，把本地解析当成了默认兜底。

更合理的规则应该是：

1. 模型支持文件上传：前端桌面直接上传给模型供应商，后端不参与。
2. 模型支持图片多模态：图片直接作为图片发给模型。
3. 模型不支持文件/图片时，才本地解析成文字作为兜底。
4. UI 明确展示“已上传给模型 / 已作为图片发送 / 已本地解析兜底”，避免误解。

我可以继续把附件路由改成这个优先级。

# ai部署 技术路线细节

• 不是完全走桌面智能体。

当前链路分两段：

1. 打包/读取本地 zip：需要本机能力时，按约束必须走项目聊天里已选择的外部智能体，并且运行在桌面端 Runner 上。
2. 项目详情里的“部署产物 / AI 部署”：现在走的是服务端部署产物模块。前端调用
   POST /projects/{project_id}/deploy-artifacts/{artifact_id}/deploy/ai-execute，后端在 routers/projects.py 里执行 \_execute_project_deploy_artifact_agent_payload，由服务端的部署 Agent 调用受控工具完成解压、上传 FTP、运行已配置远端命令等。

关键点：项目详情 AI 部署不会把 FTP/SSH 凭据交给桌面智能体，也不是让桌面端直接部署到服务器。桌面端/外部智能体主要负责本地打包并上传 artifact；artifact 到了服务端后，AI 部署由服务端部署产物能力执行。当前 MCP 任务树工具没有暴露，所以任务树闭环
未完成。

• 已按你纠正后的目标处理完：这次不是修“你是什么模型”这个单点问题，而是把它作为桌面本地智能体执行闭环缺失的症状来设计升级方案。

已更新：

- 方案记录.txt：已覆盖完善，加入“问题边界”、完整 Runtime 执行流程、自测计划、自测失败反馈、自动修正、重试边界、最终验证、状态持久化和每步中文注释。
- docs/liuAgent-cli/桌面本地智能体Trace与进度播报改造计划.md：已同步补齐播报方案，把 SelfTestPlan、SelfFeedback、SelfCorrectionPlan、LoopBudget、self*test*_、
  self*feedback_created、self_correction_planned、loop_budget*_ 等作为一等事件和前端展示对象。

我也补了本地 requirement 记录，但当前宿主没有暴露 query MCP server，所以服务端任务树闭环没法完成；本地记录已标明这个限制。

验证过：

- git diff --check 通过。
- 本轮没有改运行代码。
- system.md 和 ChatComposer.vue 仍是已有脏改，我没有动。

• 已按你纠正后的目标处理完：这次不是修“你是什么模型”这个单点问题，而是把它作为桌面本地智能体执行闭环缺失的症状来设计升级方案。

已更新：

- 方案记录.txt：已覆盖完善，加入“问题边界”、完整 Runtime 执行流程、自测计划、自测失败反馈、自动修正、重试边界、最终验证、状态持久化和每步中文注释。
- docs/liuAgent-cli/桌面本地智能体Trace与进度播报改造计划.md：已同步补齐播报方案，把 SelfTestPlan、SelfFeedback、SelfCorrectionPlan、LoopBudget、self*test*_、
  self*feedback_created、self_correction_planned、loop_budget*_ 等作为一等事件和前端展示对象。

我也补了本地 requirement 记录，但当前宿主没有暴露 query MCP server，所以服务端任务树闭环没法完成；本地记录已标明这个限制。

验证过：

- git diff --check 通过。
- 本轮没有改运行代码。
- system.md 和 ChatComposer.vue 仍是已有脏改，我没有动。
