# 内置工具技能索引

## 作用

这是桌面本地 Runtime 内置工具的选择指南。工具本身由 Runtime 注册和执行；本技能只负责帮助 AI 判断什么时候使用哪个工具、如何组合工具以及如何遵守权限边界。

## 总体选择规则

1. 先判断任务是否需要真实读取、修改、执行或访问外部服务；只需要解释时不要调用工具。
2. 读取文件前优先使用 `list_files`、`read_file`、`search_text`，不要用 `run_command` 替代文件工具。
3. 修改文件优先使用 `apply_patch`；只有需要完整创建或替换文件时才使用 `write_file`。
4. 执行命令前需要真实运行时使用 `run_command`；只想判断风险使用 `check_command_risk`。
5. 需要持续运行服务时使用 `run_command(background=true)`，之后用 `process` 管理，不要重复启动同一服务。
6. 需要用户决定且缺失信息会改变结果时使用 `ask_user_question`，一次最多 3 个具体问题。
7. 复杂任务使用 `update_execution_plan`，简单问答不要创建计划。
8. 网络、媒体、部署和删除操作要按工具的风险等级和授权要求执行，不要假报成功。
9. MCP 工具是动态发现的外部工具，不要把 MCP Host 管理接口当作普通内置工具。

## 工具目录

每个工具的详细说明位于同名子目录：

- `ask_user_question/`
- `update_execution_plan/`
- `list_files/`
- `read_file/`
- `list_local_resources/`
- `read_local_resource/`
- `search_text/`
- `apply_patch/`
- `write_file/`
- `delete_file/`
- `check_command_risk/`
- `run_command/`
- `process/`
- `http_get/`
- `web_search/`
- `web_extract/`
- `http_post/`
- `download_file/`
- `generate_image/`
- `edit_image/`
- `generate_video/`
- `generate_audio/`
- `transcribe_audio/`
- `list_projects/`
- `get_project/`
- `list_bot_projects/`
- `switch_project_workspace/`
- `get_project_deploy_options/`
- `deploy_workspace_files_to_target/`

