# check_command_risk

## 作用

检查命令风险，但不执行命令。

## 选择时机

- 需要在执行 Shell 命令前预判风险。
- 需要向用户解释命令影响。

## 参数

必须提供 `cmd`；可选 `cwd`，默认当前 workspace。

## 边界

检查结果不是执行结果；需要真正运行时必须改用 `run_command`。

