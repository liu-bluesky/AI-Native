# AI 结构化交互协议

## 目标

AI 先生成渠道无关的结构化交互数据，再根据当前渠道和能力选择反馈方式。`element-easy-form`、飞书卡片、移动端卡片和自然语言追问都是渲染器，不是协议本身。

## 原则

- 结构化数据服务系统，不直接原样展示给用户。
- `user_message` 或 `summary` 必须解释用户将要确认、补充或执行的内容。
- `presentation_hint` 只是 AI 的推荐，宿主可根据渠道能力调整。
- 修改、删除和保存操作必须等待用户明确确认。
- 同一份协议应能被 Web、桌面、移动端和机器人适配。

## 最小数据结构

```json
{
  "version": "1",
  "id": "interaction-1",
  "kind": "clarification | confirmation | data_collection | operation",
  "operation": "update_agent",
  "status": "waiting_user",
  "user_message": "我准备更新一个售前客服智能体，请确认配置。",
  "summary": "需要确认智能体名称和能力",
  "data": {},
  "fields": [],
  "options": [],
  "confirmation_required": true,
  "presentation_hint": {
    "type": "form | card | table | list | wizard | summary | clarification",
    "reason": "字段较多"
  },
  "submit_label": "确认",
  "cancel_label": "取消"
}
```

## 渲染决策

AI 可以在 `presentation_hint` 中提出建议，前端或机器人运行时再根据渠道能力选择最终方式：

- Web / 桌面：表单、表格、向导或摘要。
- 手机：分步表单、卡片、列表或摘要。
- 机器人：卡片、按钮、文字追问或跳转完整表单。

普通聊天中的内部协议可以使用 `structured-interaction` 代码块传输，展示层必须过滤该代码块，不能把原始 JSON 直接反馈给用户。
