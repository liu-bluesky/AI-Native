# switch_project_workspace

## 作用

按 `project_id` 切换飞书机器人当前会话使用的本机工作区。

## 选择时机

- 已通过 `list_bot_projects` 找到目标项目。
- 后续工具需要在新的项目工作区执行。

## 边界

只接受项目 ID，不接受任意工作区路径；不能跳过项目选择直接猜路径。

