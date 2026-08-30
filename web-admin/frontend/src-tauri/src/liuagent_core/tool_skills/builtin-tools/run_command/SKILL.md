# run_command

## 作用

执行 workspace 内的 Shell、Git、npm、cargo、测试、构建或脚本命令。

## 选择时机

- 需要运行测试、构建、格式化或项目脚本。
- 需要启动服务器、watcher 或其他后台服务。

## 参数与权限

必须提供 `cmd`；可选 `cwd`、`background`、`timeout_ms`、`max_output_chars`。这是中风险执行操作，通常需要授权。

## 边界

短命令使用 `background=false`；持续进程使用 `background=true`，返回的 `session_id` 交给 `process` 管理。

