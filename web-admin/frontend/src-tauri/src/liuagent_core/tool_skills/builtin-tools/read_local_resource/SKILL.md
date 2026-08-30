# read_local_resource

## 作用

读取已配置目录中的 `AGENT.md`、`SKILL.md` 或规则 Markdown 文件。

## 选择时机

- 已通过 `list_local_resources` 找到目标资源。
- 执行前需要遵守项目技能或规则。

## 参数

必须提供 `kind` 和相对于对应资源目录的 `path`。

## 边界

只能读取配置目录内的文件；不得凭空拼接工作区外路径。

