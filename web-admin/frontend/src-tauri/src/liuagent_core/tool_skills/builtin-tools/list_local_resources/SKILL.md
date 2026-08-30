# list_local_resources

## 作用

列出已配置的本地 Agent、Skill 或 Rule 资源。

## 选择时机

- 需要查找某个本地技能、项目规则或智能体定义。
- 不确定资源目录中有哪些可复用说明。

## 参数

必须提供 `kind`，取值为 `agent`、`skill` 或 `rule`。

## 边界

只访问 Runtime 提供的配置目录，不要猜测目录路径或读取未配置目录。

