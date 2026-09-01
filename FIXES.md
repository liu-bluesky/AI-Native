# 项目聊天修复记录

## 修复时间
2026-09-01

## 修复的问题

### 1. 聊天记录丢失问题 ✅

**症状：**
- 删除消息后切换会话，聊天记录全部消失
- 发送消息后切换会话，消息也没了
- 对话失败

**根本原因：**
在 `ProjectChat.vue` 的 `deleteMessageAt` 函数中（第 26091 行附近），删除消息时调用 `persistCurrentChatRuntimeNow` 传入了错误的参数：
```javascript
// ❌ 错误：缺少 messages 字段
includeMessages: false,
```

这导致持久化的 payload 中没有 `messages` 字段，桌面端接收后会清空消息列表。

**修复方案：**
```javascript
// ✅ 正确：包含完整消息列表
includeMessages: true,
rows: messages.value,
```

**Commit:** `fe317fbd` - fix(project-chat): 修复删除消息时持久化导致聊天记录丢失的问题

---

### 2. 模型选择下拉框不生效问题 ✅

**症状：**
- 在聊天界面下拉框中选择模型后
- 实际发送消息时使用的仍是旧模型
- 模型切换没有生效

**根本原因：**
`setManualModelOptionValue` 函数只保存了选项值字符串，但没有解析它：
```javascript
// ❌ 错误：只保存字符串，不解析
function setManualModelOptionValue(value) {
  manualModelOptionValue.value = String(value || "").trim();
}
```

模型选择器使用 `providerId::modelName` 格式，需要解析后分别设置 `selectedProviderId` 和 `selectedModelName`。

**修复方案：**
```javascript
// ✅ 正确：解析并更新模型状态
function setManualModelOptionValue(value) {
  const normalized = String(value || "").trim();
  manualModelOptionValue.value = normalized;
  if (!normalized) {
    selectedProviderId.value = "";
    selectedModelName.value = "";
    return;
  }
  const separatorIndex = normalized.indexOf("::");
  if (separatorIndex > 0) {
    selectedProviderId.value = normalized.slice(0, separatorIndex);
    selectedModelName.value = normalized.slice(separatorIndex + 2);
  }
}
```

**Commit:** `7fa2b850` - fix(project-chat): 修复模型选择下拉框选择后不生效的问题

---

## 测试方案

### 测试问题 1：聊天记录持久化
1. 在项目聊天中发送几条消息
2. 删除其中一条消息
3. 切换到另一个会话
4. 切换回来
5. ✅ 期望：消息应该正常显示（除了被删除的那条）

### 测试问题 2：模型选择
1. 打开项目聊天界面
2. 点击模型选择下拉框
3. 选择一个不同的模型（例如从 GPT-4 切换到 Claude）
4. 发送一条消息
5. ✅ 期望：使用新选择的模型回复，可以在消息元数据或调试日志中确认

---

## 注意事项

1. **需要重启桌面应用** 才能应用这些修复
2. 如果之前的会话数据已经损坏，可能需要：
   - 删除有问题的会话重新开始
   - 或清除本地缓存：`~/.ai-employee/desktop-agent-runtime/project-chat/`
3. 这些修复已提交到 `feat/plugin-architecture` 分支

---

## 相关文件
- `web-admin/frontend/src/views/projects/ProjectChat.vue`
- `web-admin/frontend/src/modules/project-chat/services/projectChatRuntimeStorage.js`
- `web-admin/frontend/src/modules/project-chat/services/projectChatStorage.js`
