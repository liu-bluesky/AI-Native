action_markers
这个字段干嘛的

/Volumes/work_mac_1_5T/self/hermes-agent 这个项目也有 这种固定流程吗

└ □ 定位需求记录写入、读取、展示链路
接口总是报错超时修改细节
主要改动：

- 第 4 步 continuation 发给模型的工具结果现在会裁剪大字段：read_file 内容最多回灌 6000 字符，search_text 单条命中最多 500 字符，列表类结果最多 80 项。完整工具结果仍保留在本地运行详情里。
- 模型网关错误诊断增加了 body_bytes、每条 message 大小、最大消息列表、tool_call_id 完整性检查。后面再 500 时能判断是 payload 过大还是 tool 消息链不合法。
- OpenAI-compatible 工具调用现在优先保留模型上游返回的 tool_call.id，不再无条件改成本地 stable id，降低兼容网关拒绝 continuation 的概率。
- 补了对应单测，覆盖大文件 observation 裁剪、payload 诊断、原始 tool call id 保留。
