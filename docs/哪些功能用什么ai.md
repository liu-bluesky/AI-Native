核心功能

- 项目 AI 对话 / 智能体工具调用：模型生成回复、决定并调用项目工具；支持服务端模型，也支持桌面外部智能体。web-admin/api/services/
  agent_runtime/v2/llm_step.py:62

- 全局 AI 助手：非项目场景下的全局聊天。web-admin/api/routers/projects.py:15422
- 对话内图片和视频生成：根据所选模型类型直接生成媒体文件并保存为项目素材。web-admin/api/services/chat/project_chat_execution_service.py:305
- 全局语音助手：语音转文字 ASR、文字转语音 TTS、欢迎语音频生成。web-admin/api/routers/projects.py:14588、web-admin/api/routers/
  projects.py:14648

- AI 短片工作室：音色克隆、旁白生成、角色参考图、素材内容提取、分镜生成。web-admin/api/routers/projects.py:18601、web-admin/api/routers/
  projects.py:18804、web-admin/api/routers/projects.py:18909、web-admin/api/routers/projects.py:19017、web-admin/api/routers/
  projects.py:19063

- AI 部署：生成部署命令、生成部署计划、AI 分析并执行部署产物。web-admin/api/routers/projects.py:16803、web-admin/api/routers/
  projects.py:18057、web-admin/api/routers/projects.py:18081

- 项目智能查询：AI 判断是普通回答、查询数据库、调用项目工具，还是推荐其他项目。web-admin/api/routers/projects.py:19577

后台治理功能

- AI 员工和模板管理：根据描述生成 AI 员工草稿、翻译模板名称、识别重复模板。web-admin/api/routers/employees.py:1303、web-admin/api/routers/
  agent_templates.py:597、web-admin/api/routers/agent_templates.py:872

- 反馈与经验治理：分析 Bug 并产生反思结果；总结、审核、合并项目开发经验卡片。web-admin/api/services/feedback_service.py:442、web-admin/api/
  routers/projects.py:22090、web-admin/api/routers/projects.py:22135、web-admin/api/routers/projects.py:22300

桌面智能体关系

- 上述功能默认可使用服务端模型供应商执行。
- 当项目设置为 chat_mode=external_agent 时，任务会交给桌面智能体，支持 codex_cli、claude_code 和 hermes。web-admin/api/services/chat/
  project_chat_execution_service.py:155、web-admin/api/routers/projects.py:6687

- AI 部署也支持两种模式：服务端模型直接规划，或者交给桌面外部智能体分析；但实际 FTP 上传、备份和远端命令执行仍由服务端部署模块负责。
- 当前项目 proj-d16591a6 的部署配置仍是 enabled=false、configured=false，因此虽然系统有 AI 部署代码能力，该项目目前尚不能实际部署。

不属于直接 AI 的功能

- 任务树生成和状态推进目前主要是规则算法，没有直接调用模型。web-admin/api/services/chat/project_chat_task_tree.py:2602
- 模型供应商管理、项目 CRUD、文件上传、FTP 上传、部署记录、消息通知本身不是 AI。
- mcp-memory、mcp-rules、mcp-skills 当前未发现直接请求模型接口；它们主要提供存储、规则和工具能力。
