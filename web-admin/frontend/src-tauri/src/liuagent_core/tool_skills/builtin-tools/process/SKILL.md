# process

## 作用

管理 `run_command(background=true)` 创建的后台进程。

## 选择时机

- 查看后台服务状态或日志。
- 向后台进程发送输入、等待、关闭或终止。

## 参数

`action` 可选 `list`、`poll`、`log`、`wait`、`kill`、`write`、`submit`、`close`；除 `list` 外通常需要 `session_id`。

## 边界

不要用 `process` 创建新进程；创建进程必须使用 `run_command`。

