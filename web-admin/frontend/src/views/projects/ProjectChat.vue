<template>
  <div class="chat-layout" v-loading="loading">
    <!-- Sidebar: Settings -->
    <!-- Main Chat Area -->
    <div class="chat-main">
      <div class="chat-header">
        <div class="chat-header-left">
          <h2>AI 对话中心</h2>
          <el-tag size="small" effect="plain">{{ chatModeLabel }}</el-tag>
          <el-tag :type="wsStatusType" size="small" effect="light">{{
            wsStatusText
          }}</el-tag>
          <el-tag
            v-if="isExternalAgentMode"
            :type="externalAgentInfo.ready ? 'success' : (externalAgentWarmupLoading ? 'warning' : 'info')"
            size="small"
            effect="light"
          >
            {{ externalAgentInfo.ready ? '会话已就绪' : (externalAgentWarmupLoading ? '会话预热中' : '会话未就绪') }}
          </el-tag>
          <el-tag
            v-if="isExternalAgentMode && externalAgentInfo.runtime_model_name"
            size="small"
            effect="plain"
          >
            运行标识 {{ externalAgentInfo.runtime_model_name }}
          </el-tag>
          <el-tag
            v-if="isExternalAgentMode && externalAgentInfo.thread_id"
            size="small"
            effect="plain"
          >
            Thread {{ shortThreadId }}
          </el-tag>
        </div>
        <div class="chat-header-right">
          <el-button
            @click="showSettingsDialog = true"
            :icon="Setting"
            circle
          />
          <el-button
            plain
            @click="clearMessages"
            :disabled="chatLoading || !messages.length"
            :icon="Delete"
            circle
            title="清空会话"
          />
        </div>
      </div>

      <div
        v-if="isExternalAgentMode"
        class="terminal-panel"
        :class="{ 'is-collapsed': !terminalPanelExpanded }"
      >
        <div class="terminal-panel-header">
          <div class="terminal-panel-title">
            <span>终端过程</span>
            <el-tag size="small" effect="plain">{{ terminalPanelStatusText }}</el-tag>
          </div>
          <div class="terminal-panel-actions">
            <el-button
              text
              size="small"
              @click="clearTerminalPanel"
              :disabled="!terminalPanelLines.length"
            >清空</el-button>
            <el-button text size="small" @click="terminalPanelExpanded = !terminalPanelExpanded">
              {{ terminalPanelExpanded ? '收起' : '展开' }}
            </el-button>
          </div>
        </div>
        <div v-show="terminalPanelExpanded" ref="terminalPanelRef" class="terminal-panel-body">
          <pre class="terminal-panel-pre">{{ terminalPanelText }}</pre>
        </div>
        <div v-show="terminalPanelExpanded" class="terminal-panel-footer">
          <el-input
            v-model="terminalPanelInput"
            size="small"
            placeholder="直接发送到真实 Codex 终端镜像，Enter 发送"
            @keyup.enter.prevent="sendTerminalMirrorInput"
          />
          <el-button size="small" @click="startTerminalMirror" :disabled="!externalAgentInfo.thread_id">
            连接镜像
          </el-button>
          <el-button size="small" type="primary" @click="sendTerminalMirrorInput" :disabled="!terminalPanelInput.trim()">
            发送
          </el-button>
        </div>
      </div>

      <div class="chat-messages" ref="messagesContainer">
        <el-empty
          v-if="!messages.length"
          description="选择项目并开始你的对话吧 ✨"
          :image-size="120"
        />
        <div v-else class="message-list-inner">
          <div
            v-for="(item, idx) in messages"
            :key="idx"
            :class="['message-row', item.role === 'user' ? 'is-user' : 'is-ai']"
          >
            <div class="message-avatar">
              <el-avatar
                :size="36"
                :class="item.role === 'user' ? 'avatar-user' : 'avatar-ai'"
              >
                {{ item.role === "user" ? "U" : "AI" }}
              </el-avatar>
            </div>
            <div class="message-content-wrapper">
              <div class="message-meta">
                <span class="role-name">{{
                  item.role === "user" ? "You" : "Assistant"
                }}</span>
                <span
                  v-if="item.time || item.created_at"
                  class="message-time"
                  >{{ item.time || item.created_at }}</span
                >
              </div>
              <div class="message-bubble">
                <pre
                  v-if="item.displayMode === 'terminal'"
                  class="message-text message-text-terminal"
                >{{ formatTerminalMessage(item, idx) }}</pre>
                <div
                  v-else
                  class="message-text"
                  v-html="
                    formatContent(item.content) ||
                    (chatLoading && idx === messages.length - 1
                      ? '思考中...'
                      : '')
                  "
                ></div>
                <!-- Images -->
                <div v-if="extractImages(item).length" class="message-images">
                  <el-image
                    v-for="(img, imageIndex) in extractImages(item)"
                    :key="imageIndex"
                    :src="img"
                    class="preview-image"
                    fit="cover"
                    :preview-src-list="extractImages(item)"
                    :initial-index="imageIndex"
                    preview-teleported
                  />
                </div>
                <div
                  v-if="extractAttachments(item).length"
                  class="message-attachments"
                >
                  <div
                    v-for="(attachment, attachmentIndex) in extractAttachments(
                      item,
                    )"
                    :key="`att-${idx}-${attachmentIndex}`"
                    class="attachment-item"
                  >
                    <el-tag
                      size="small"
                      :type="attachmentTagType(attachment.kind)"
                      effect="plain"
                    >
                      {{ attachmentTypeLabel(attachment) }}
                    </el-tag>
                    <span class="attachment-name">{{ attachment.name }}</span>
                  </div>
                </div>
                <div v-if="item.audit" class="message-audit">
                  <div class="message-audit-title">执行审计</div>
                  <div
                    v-if="item.audit.risk_signals?.length"
                    class="message-audit-section"
                  >
                    <div class="message-audit-label">高风险提示</div>
                    <div class="message-audit-tags">
                      <el-tag
                        v-for="risk in item.audit.risk_signals"
                        :key="`risk-${risk.id}-${risk.snippet}`"
                        size="small"
                        type="danger"
                        effect="plain"
                      >
                        {{ risk.label }}
                      </el-tag>
                    </div>
                  </div>
                  <div class="message-audit-section">
                    <div class="message-audit-label">工作区变更</div>
                    <template v-if="item.audit.after_diff_summary?.enabled">
                      <div class="message-audit-text">
                        改动文件数：{{ item.audit.after_diff_summary.changed_file_count }}
                      </div>
                      <pre
                        v-if="item.audit.after_diff_summary.diff_stat"
                        class="message-audit-pre"
                      >{{ item.audit.after_diff_summary.diff_stat }}</pre>
                      <pre
                        v-else-if="item.audit.after_diff_summary.status_lines?.length"
                        class="message-audit-pre"
                      >{{ item.audit.after_diff_summary.status_lines.join('\n') }}</pre>
                      <div v-else class="message-audit-text">暂无 Git 变更</div>
                    </template>
                    <div v-else class="message-audit-text">
                      {{ item.audit.after_diff_summary?.reason || '当前工作区不是 Git 仓库' }}
                    </div>
                  </div>
                  <div
                    v-if="item.audit.file_review_status && item.audit.file_review_status !== 'not_required'"
                    class="message-audit-section"
                  >
                    <div class="message-audit-label">变更审查</div>
                    <div class="message-audit-tags">
                      <el-tag
                        size="small"
                        :type="getFileReviewStatusMeta(item.audit.file_review_status).type"
                        effect="plain"
                      >
                        {{ getFileReviewStatusMeta(item.audit.file_review_status).label }}
                      </el-tag>
                    </div>
                    <div class="message-audit-text">
                      {{ getFileReviewStatusMeta(item.audit.file_review_status).text }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Composer Area -->
      <div class="chat-composer">
        <div
          class="chat-input-wrapper"
          :class="{ 'is-focused': inputFocused, 'is-dragover': isDragging }"
          @dragover.prevent="handleDragOver"
          @dragleave.prevent="handleDragLeave"
          @drop.prevent="handleDrop"
        >
          <div v-if="uploadFiles.length > 0" class="upload-preview-area">
            <div
              v-for="(file, idx) in uploadFiles"
              :key="idx"
              class="preview-item"
            >
              <img v-if="file.url" :src="file.url" class="preview-img" />
              <div v-else class="preview-doc">
                <el-icon :size="24"><Document /></el-icon>
                <span class="doc-name">{{ file.name }}</span>
                <span class="doc-type">{{ formatFileType(file.name) }}</span>
              </div>
              <div class="remove-mask" @click="removeFile(idx)">
                <el-icon><Delete /></el-icon>
              </div>
            </div>
          </div>

          <el-input
            v-model="draftText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 6 }"
            :placeholder="composerPlaceholder"
            resize="none"
            :disabled="chatLoading"
            @keydown.enter.exact.prevent="doSend"
            @focus="inputFocused = true"
            @blur="inputFocused = false"
            @paste="handlePaste"
            class="chat-textarea"
          />

          <div class="input-footer">
            <div class="footer-left">
              <el-upload
                action="#"
                :auto-upload="false"
                :show-file-list="false"
                accept="image/*"
                :multiple="true"
                :on-change="handleFileChange"
                :disabled="chatLoading || isExternalAgentMode"
              >
                <el-tooltip content="添加图片" placement="top">
                  <el-button text circle
                    ><el-icon><Picture /></el-icon
                  ></el-button>
                </el-tooltip>
              </el-upload>
              <el-upload
                action="#"
                :auto-upload="false"
                :show-file-list="false"
                accept=".wps,.doc,.docx,.pdf,.txt,.csv,.xlsx,.xls"
                :multiple="true"
                :on-change="handleFileChange"
                :disabled="chatLoading || isExternalAgentMode"
              >
                <el-tooltip content="添加文档" placement="top">
                  <el-button text circle
                    ><el-icon><Document /></el-icon
                  ></el-button>
                </el-tooltip>
              </el-upload>
            </div>
            <div class="footer-right">
              <span class="hint-text">{{ composerHintText }}</span>
              <el-tooltip
                v-if="chatLoading"
                content="暂停当前回答"
                placement="top"
              >
                <el-button
                  class="pause-generation-button"
                  type="danger"
                  plain
                  @click="stopGeneration"
                >
                  <el-icon><VideoPause /></el-icon>
                  <span>暂停</span>
                </el-button>
              </el-tooltip>
              <el-button
                v-else
                type="primary"
                :disabled="!canSend"
                @click="doSend"
                circle
              >
                <el-icon><Promotion /></el-icon>
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Settings Dialog -->
  <el-dialog
    v-model="showSettingsDialog"
    title="对话设置"
    width="850px"
    destroy-on-close
    class="custom-settings-dialog"
  >
    <div class="settings-dialog-body">
      <el-tabs tab-position="left" class="settings-tabs">
        <el-tab-pane label="基础设置">
          <el-form
            label-position="left"
            label-width="160px"
            class="settings-form"
            size="default"
          >
            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  选择项目
                  <el-tooltip
                    content="当前对话所在的关联项目，不同的项目可能绑定不同的知识库和工具。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select
                v-model="selectedProjectId"
                filterable
                placeholder="请选择项目"
                class="full-width"
              >
                <el-option
                  v-for="item in projects"
                  :key="item.id"
                  :label="`${item.name}`"
                  :value="item.id"
                >
                  <span style="float: left">{{ item.name }}</span>
                  <span
                    style="
                      float: right;
                      color: var(--el-text-color-secondary);
                      font-size: 12px;
                    "
                    >{{ item.id }}</span
                  >
                </el-option>
              </el-select>
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  执行员工
                  <el-tooltip
                    content="决定本次对话所使用的技能(Skills)及规则约束(Rules)。留空时由 AI 在项目可用员工能力内自行选择。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select
                v-model="selectedEmployeeIds"
                multiple
                collapse-tags
                collapse-tags-tooltip
                filterable
                clearable
                placeholder="默认全选（项目内全部员工）"
                class="full-width"
              >
                <el-option
                  v-for="item in projectEmployees"
                  :key="item.id"
                  :label="`${item.name || item.id}`"
                  :value="item.id"
                >
                  <div
                    style="
                      display: flex;
                      flex-direction: column;
                      gap: 4px;
                      padding: 4px 0;
                    "
                  >
                    <div
                      style="
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                      "
                    >
                      <span style="font-weight: 500">{{
                        item.name || item.id
                      }}</span>
                      <el-tag
                        size="small"
                        :type="item.role === 'admin' ? 'danger' : 'info'"
                        >{{ item.role || "member" }}</el-tag
                      >
                    </div>
                    <div
                      v-if="item.skill_names && item.skill_names.length"
                      style="
                        font-size: 12px;
                        color: var(--el-text-color-secondary);
                      "
                    >
                      技能: {{ item.skill_names.join(", ") }}
                    </div>
                    <div
                      v-if="item.rule_bindings && item.rule_bindings.length"
                      style="
                        font-size: 12px;
                        color: var(--el-text-color-secondary);
                      "
                    >
                      规则:
                      {{
                        item.rule_bindings
                          .map((rule) => rule.title || rule.id)
                          .join(" / ")
                      }}
                    </div>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  运行模式
                  <el-tooltip
                    content="系统对话走内置 Provider；外部 Agent 直接托管 Codex CLI PTY 会话。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-radio-group v-model="selectedChatMode" class="full-width">
                <el-radio-button
                  v-for="item in chatModes"
                  :key="item.id"
                  :label="item.id"
                >
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item v-if="isExternalAgentMode">
              <template #label>
                <span class="label-with-tooltip">
                  外部 Agent
                  <el-tooltip
                    content="第一阶段固定接入 Codex CLI。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <div class="full-width external-agent-meta">
                <div class="external-agent-row">
                  <span>类型：{{ externalAgentInfo.label || 'Codex CLI' }}</span>
                  <el-tag
                    :type="externalAgentInfo.available ? 'success' : 'warning'"
                    size="small"
                    effect="plain"
                  >
                    {{ externalAgentInfo.available ? '可用' : '未发现' }}
                  </el-tag>
                </div>
                <div class="external-agent-row external-agent-command">
                  命令：{{ externalAgentInfo.resolved_command || externalAgentInfo.command || 'codex' }}
                </div>
                <div class="external-agent-row external-agent-command">
                  来源：{{ externalAgentInfo.command_source === 'system' ? '系统 PATH' : externalAgentInfo.command_source === 'override' ? '手动覆盖' : '未找到' }}
                </div>
                <div class="external-agent-row external-agent-command">
                  运行标识：{{ externalAgentInfo.runtime_model_name || 'codex-cli' }}
                </div>
                <div class="external-agent-row external-agent-command">
                  精确模型：{{ externalAgentInfo.exact_model_name || '当前未暴露' }}
                </div>
                <div
                  v-if="externalAgentInfo.thread_id"
                  class="external-agent-row external-agent-command"
                >
                  Thread：{{ externalAgentInfo.thread_id }}
                </div>
                <div
                  v-if="externalAgentInfo.session_id"
                  class="external-agent-row external-agent-command"
                >
                  Session：{{ externalAgentInfo.session_id }}
                </div>
                <div class="external-agent-row external-agent-command">
                  沙箱：{{ externalAgentInfo.sandbox_mode || 'workspace-write' }}
                </div>
                <div
                  v-if="externalAgentInfo.support_dir"
                  class="external-agent-row external-agent-command"
                >
                  上下文目录：{{ externalAgentInfo.support_dir }}
                </div>
                <div class="external-agent-row">
                  <span>
                    项目 MCP：
                    {{
                      externalAgentInfo.mcp_bridge_enabled
                        ? `已注入 (${externalAgentInfo.mcp_server_name || 'project_mcp'})`
                        : '未注入'
                    }}
                  </span>
                  <el-tag
                    :type="externalAgentInfo.mcp_bridge_enabled ? 'success' : 'warning'"
                    size="small"
                    effect="plain"
                  >
                    {{ externalAgentInfo.mcp_bridge_enabled ? '可调用项目工具' : '暂不可用' }}
                  </el-tag>
                </div>
                <div
                  v-if="externalAgentInfo.mcp_bridge_reason && !externalAgentInfo.mcp_bridge_enabled"
                  class="external-agent-row external-agent-command"
                >
                  原因：{{ externalAgentInfo.mcp_bridge_reason }}
                </div>
                <div
                  v-if="externalAgentInfo.support_files?.length"
                  class="external-agent-support-list"
                >
                  <div
                    v-for="item in externalAgentInfo.support_files"
                    :key="`${item.kind}-${item.path}`"
                    class="external-agent-support-item"
                  >
                    <span>{{ item.label }}</span>
                    <code>{{ item.path }}</code>
                  </div>
                </div>
              </div>
            </el-form-item>

            <el-form-item v-if="isExternalAgentMode">
              <template #label>
                <span class="label-with-tooltip">
                  沙箱模式
                  <el-tooltip
                    content="先支持只读或工作区受限写入，不接复杂审批流。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select
                v-model="projectChatSettings.external_agent_sandbox_mode"
                class="full-width"
              >
                <el-option label="只读 (read-only)" value="read-only" />
                <el-option
                  label="工作区写入 (workspace-write)"
                  value="workspace-write"
                />
              </el-select>
            </el-form-item>

            <el-form-item v-if="isExternalAgentMode">
              <template #label>
                <span class="label-with-tooltip">
                  工作区路径
                  <el-tooltip
                    content="外部 Agent 启动时会将此路径作为 Codex CLI 的工作目录。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input
                :model-value="externalAgentInfo.workspace_path || '未配置'"
                readonly
                class="full-width"
              />
            </el-form-item>

            <el-alert
              v-if="isExternalAgentMode && !externalAgentInfo.available"
              title="未检测到 Codex CLI，保存设置后仍无法正常启动外部 Agent。"
              type="warning"
              :closable="false"
              show-icon
            />

            <el-form-item v-if="!isExternalAgentMode">
              <template #label>
                <span class="label-with-tooltip">
                  模型供应商
                  <el-tooltip
                    content="选择用于对话的基础大模型服务提供商，如 OpenAI、阿里云等。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select
                v-model="selectedProviderId"
                filterable
                placeholder="默认"
                class="full-width"
                @change="handleProviderChange"
              >
                <el-option
                  v-for="item in providers"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item v-if="!isExternalAgentMode">
              <template #label>
                <span class="label-with-tooltip">
                  模型版本
                  <el-tooltip
                    content="具体使用的大模型版本，如 gpt-4o 或 qwen-max。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select
                v-model="selectedModelName"
                filterable
                allow-create
                default-first-option
                placeholder="默认"
                class="full-width"
              >
                <el-option
                  v-for="item in availableModels"
                  :key="item"
                  :label="item"
                  :value="item"
                />
              </el-select>
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  系统提示词
                  <el-tooltip
                    :content="isExternalAgentMode ? '外部 Agent 首轮会把这里作为启动上下文的一部分注入。' : '(System Prompt) 设定 AI 的角色背景和最高优先级的行为准则。'"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input
                type="textarea"
                v-model="systemPrompt"
                :rows="3"
                :placeholder="isExternalAgentMode ? '补充给 Codex CLI 的启动上下文...' : '你是项目开发助手...'"
                class="full-width"
              />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  历史消息条数
                  <el-tooltip
                    content="每次向模型发送请求时，携带最近几次的对话历史。较小的值可节省 Token，较大的值有助于维持长上下文记忆。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input-number
                v-model="projectChatSettings.history_limit"
                :min="1"
                :max="50"
                class="full-width"
              />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="生成控制">
          <el-form
            label-position="left"
            label-width="160px"
            class="settings-form"
            size="default"
          >
            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  温度 (Temperature)
                  <el-tooltip
                    content="控制 AI 生成文本的随机性。值越小（如 0.1）回答越严谨保守，适合代码生成；值越大（如 0.8）回答越发散具有创造力。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-slider
                v-model="temperature"
                :min="0"
                :max="2"
                :step="0.1"
                show-input
                :show-input-controls="false"
              />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  最大输出 Token
                  <el-tooltip
                    content="限制 AI 单次回答的最大长度，1 个 Token 大约对应 0.5 个汉字或 1 个英文单词。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input-number
                v-model="chatMaxTokens"
                :min="128"
                :max="8192"
                :step="64"
                class="full-width"
              />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  回答风格
                  <el-tooltip
                    content="偏好 AI 返回内容的详细程度。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select
                v-model="projectChatSettings.answer_style"
                class="full-width"
              >
                <el-option label="简洁 (Concise)" value="concise" />
                <el-option label="平衡 (Balanced)" value="balanced" />
                <el-option label="详细 (Detailed)" value="detailed" />
              </el-select>
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  先结论后步骤
                  <el-tooltip
                    content="让 AI 在长篇大论前，先给出简明扼要的核心结论。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-switch
                v-model="projectChatSettings.prefer_conclusion_first"
              />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="工具策略 (MCP)">
          <el-form
            label-position="left"
            label-width="160px"
            class="settings-form"
            size="default"
          >
            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  自动使用工具
                  <el-tooltip
                    content="是否允许 AI 在必要时自主调用系统内置工具（如查数据库、读写文件）。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-switch v-model="projectChatSettings.auto_use_tools" />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  单轮仅回答
                  <el-tooltip
                    content="仅对下一次对话生效：强制 AI 直接用自然语言回答，禁止在此轮对话中调用任何工具。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-switch v-model="singleRoundAnswerOnly" />
            </el-form-item>

            <el-form-item label="MCP 模块">
              <el-tabs
                v-model="activeMcpSource"
                class="mcp-source-tabs"
                style="width: 100%"
              >
                <el-tab-pane
                  :label="`系统提供 (${systemMcpTotal})`"
                  name="system"
                >
                  <el-select
                    v-model="activeSystemScope"
                    size="small"
                    class="full-width mcp-scope-select"
                  >
                    <el-option
                      :label="`项目关联的所有 (${systemProjectRelatedModules.length})`"
                      value="project_related"
                    />
                    <el-option
                      :label="`系统本身提供的所有 (${systemGlobalModules.length})`"
                      value="system_global"
                    />
                  </el-select>
                  <div class="mcp-section-tip">
                    系统提供的 MCP
                    仅展示；此处勾选只控制当前项目对话可用工具，不修改模块定义。
                  </div>
                  <div
                    v-if="
                      activeSystemScope === 'project_related' &&
                      projectToolModules.length
                    "
                    class="mcp-tool-actions"
                  >
                    <span class="mcp-tool-count"
                      >本轮启用 {{ selectedProjectToolNames.length }}/{{
                        projectToolModules.length
                      }}</span
                    >
                    <div class="mcp-tool-buttons">
                      <el-button
                        text
                        size="small"
                        @click="selectAllProjectTools"
                        >全选</el-button
                      >
                      <el-button text size="small" @click="clearProjectTools"
                        >清空</el-button
                      >
                    </div>
                  </div>
                  <div class="mcp-module-list">
                    <el-empty
                      v-if="!activeSystemModules.length"
                      description="暂无系统模块"
                      :image-size="48"
                    />
                    <template v-else>
                      <div
                        v-for="item in activeSystemModules.slice(0, 12)"
                        :key="item.id || item.tool_name"
                        class="mcp-module-item"
                      >
                        <div class="mcp-module-row">
                          <div class="mcp-module-head">
                            <el-checkbox
                              v-if="
                                item.scope === 'project_related' &&
                                item.tool_name
                              "
                              :model-value="
                                isProjectToolSelected(item.tool_name)
                              "
                              @change="
                                (val) => toggleProjectTool(item.tool_name, val)
                              "
                            />
                            <span class="mcp-module-name">{{
                              item.name || item.id || "-"
                            }}</span>
                          </div>
                          <el-tag
                            size="small"
                            :type="moduleTagType(item.module_type)"
                            >{{ moduleTypeLabel(item.module_type) }}</el-tag
                          >
                        </div>
                        <div v-if="item.description" class="mcp-module-desc">
                          {{ item.description }}
                        </div>
                        <div
                          v-if="moduleMetaText(item)"
                          class="mcp-module-meta"
                        >
                          {{ moduleMetaText(item) }}
                        </div>
                      </div>
                      <div
                        v-if="activeSystemModules.length > 12"
                        class="mcp-module-more"
                      >
                        其余 {{ activeSystemModules.length - 12 }} 个模块未展示
                      </div>
                    </template>
                  </div>
                </el-tab-pane>
                <el-tab-pane
                  :label="`外部 (${externalMcpTotal})`"
                  name="external"
                >
                  <ExternalMcpManager
                    :project-id="selectedProjectId"
                    @changed="handleExternalModulesChanged"
                    @count-change="handleExternalModuleCountChange"
                  />
                </el-tab-pane>
              </el-tabs>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="执行安全">
          <el-form
            label-position="left"
            label-width="160px"
            class="settings-form"
            size="default"
          >
            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  允许 Shell 类工具
                  <el-tooltip
                    content="开启后，AI 可以通过终端执行命令行指令（存在一定安全风险）。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-switch v-model="projectChatSettings.allow_shell_tools" />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  允许写文件类工具
                  <el-tooltip
                    content="开启后，AI 可以直接修改或创建您的项目文件。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-switch v-model="projectChatSettings.allow_file_write_tools" />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  高风险二次确认
                  <el-tooltip
                    content="AI 在执行可能破坏系统的工具前，是否需要人工二次授权。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-switch v-model="projectChatSettings.high_risk_tool_confirm" />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  工具执行超时
                  <el-tooltip
                    content="单个工具允许执行的最长时间（秒），避免某个耗时任务卡死整个对话。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input-number
                v-model="projectChatSettings.tool_timeout_sec"
                :min="1"
                :max="600"
                class="full-width"
              />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  失败重试次数
                  <el-tooltip
                    content="工具执行失败时的自动重试次数。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input-number
                v-model="projectChatSettings.tool_retry_count"
                :min="0"
                :max="5"
                class="full-width"
              />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="高级策略">
          <el-form
            label-position="left"
            label-width="160px"
            class="settings-form"
            size="default"
          >
            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  最大循环轮次
                  <el-tooltip
                    content="AI 与工具之间交互迭代的最大次数，防止陷入无限死循环。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input-number
                v-model="projectChatSettings.max_loop_rounds"
                :min="1"
                :max="60"
                class="full-width"
              />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  最大工具轮次
                  <el-tooltip
                    content="一轮对话中，允许连续调用工具的最高批次数。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input-number
                v-model="projectChatSettings.max_tool_rounds"
                :min="1"
                :max="30"
                class="full-width"
              />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  单批工具调用数
                  <el-tooltip
                    content="每次向模型请求时，AI 并行发起工具调用的最大数量。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input-number
                v-model="projectChatSettings.max_tool_calls_per_round"
                :min="1"
                :max="30"
                class="full-width"
              />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span class="label-with-tooltip">
                  熔断后策略
                  <el-tooltip
                    content="当超过上述最大轮次限制（熔断）后，系统采取的动作：直接中断(Stop)或要求强制总结(Finalize)。"
                    placement="top"
                  >
                    <el-icon class="label-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select
                v-model="projectChatSettings.tool_budget_strategy"
                class="full-width"
              >
                <el-option label="强制收敛回答 (Finalize)" value="finalize" />
                <el-option label="直接停止 (Stop)" value="stop" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="settings-actions">
        <el-button @click="showSettingsDialog = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="settingsSaving"
          @click="saveProjectChatSettings(false)"
          >保存设置</el-button
        >
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import ExternalMcpManager from "@/components/ExternalMcpManager.vue";
import api from "@/utils/api.js";
import { createProjectChatWsClient } from "@/utils/ws-chat.js";
import {
  Delete,
  Picture,
  Promotion,
  Document,
  VideoPause,
  Setting,
  InfoFilled,
} from "@element-plus/icons-vue";
import { marked } from "marked";
import { extractTextFromFile } from "@/utils/file-extractor.js";

// 配置 marked 以支持代码高亮和换行
marked.setOptions({
  breaks: true,
  gfm: true,
});

const route = useRoute();

const HIGH_RISK_RULES = [
  {
    id: "delete_force",
    label: "删除类命令",
    severity: "high",
    pattern: /\brm\s+-rf\b|\bdel\s+\/[qsf]\b/i,
  },
  {
    id: "git_hard_reset",
    label: "Git 强制回滚",
    severity: "high",
    pattern: /\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-fd/i,
  },
  {
    id: "shell_pipe_remote",
    label: "远程脚本直执行",
    severity: "high",
    pattern: /(?:curl|wget)[^\n|]*\|\s*(?:sh|bash|zsh)/i,
  },
  {
    id: "network_transfer",
    label: "网络传输/外发",
    severity: "medium",
    pattern: /\b(?:scp|rsync|curl|wget)\b/i,
  },
];

const CHAT_SETTINGS_DEFAULTS = {
  chat_mode: "system",
  external_agent_type: "codex_cli",
  external_agent_sandbox_mode: "workspace-write",
  external_agent_sandbox_mode_explicit: false,
  selected_employee_id: "",
  selected_employee_ids: [],
  provider_id: "",
  model_name: "",
  temperature: 0.1,
  max_tokens: 512,
  system_prompt: "",
  auto_use_tools: true,
  enabled_project_tool_names: [],
  tool_priority: [],
  max_tool_calls_per_round: 6,
  max_loop_rounds: 20,
  max_tool_rounds: 6,
  repeated_tool_call_threshold: 2,
  tool_only_threshold: 3,
  tool_budget_strategy: "finalize",
  history_limit: 20,
  upload_file_limit: 6,
  max_file_size_mb: 15,
  doc_max_chars_per_file: 1200,
  doc_max_chars_total: 3000,
  allowed_file_types: [
    "image/*",
    ".wps",
    ".doc",
    ".docx",
    ".pdf",
    ".txt",
    ".csv",
    ".xlsx",
    ".xls",
  ],
  high_risk_tool_confirm: true,
  tool_timeout_sec: 60,
  tool_retry_count: 0,
  allow_shell_tools: true,
  allow_file_write_tools: true,
  answer_style: "concise",
  prefer_conclusion_first: true,
};

const loading = ref(false);
const chatLoading = ref(false);
const settingsSaving = ref(false);

const projects = ref([]);
const chatModes = ref([
  { id: "system", label: "系统对话" },
  { id: "external_agent", label: "外部 Agent" },
]);
const providers = ref([]);
const projectEmployees = ref([]);
const externalAgentInfo = ref({
  agent_type: "codex_cli",
  label: "Codex CLI",
  command: "codex",
  resolved_command: "",
  command_source: "missing",
  runtime_model_name: "codex-cli",
  exact_model_name: "",
  available: false,
  ready: false,
  session_id: "",
  thread_id: "",
  sandbox_mode: "workspace-write",
  workspace_path: "",
  sandbox_modes: ["read-only", "workspace-write"],
});
const mcpModules = ref({
  system: { project_related: [], system_global: [] },
  external: { modules: [] },
  summary: {
    system_project_related_total: 0,
    system_global_total: 0,
    external_total: 0,
  },
});
const messages = ref([]);

const selectedProjectId = ref("");
const selectedEmployeeIds = ref([]);
const selectedProviderId = ref("");
const selectedModelName = ref("");
const defaultProviderId = ref("");
const defaultModelName = ref("");
const temperature = ref(0.1);
const systemPrompt = ref("");
const activeMcpSource = ref("system");
const showSettingsDialog = ref(false);
const activeSystemScope = ref("project_related");
const selectedProjectToolNames = ref([]);
const projectChatSettings = ref({ ...CHAT_SETTINGS_DEFAULTS });
const singleRoundAnswerOnly = ref(false);
const externalMcpTotal = ref(0);

const wsConnected = ref(false);
const wsClient = ref(null);
const wsProjectId = ref("");
const pendingRequests = new Map();
const pendingAgentPrepares = new Map();
const activeApprovalIds = new Set();
const activeReviewIds = new Set();
const externalAgentWarmupLoading = ref(false);
const externalAgentWarmupKey = ref("");
const terminalPanelExpanded = ref(true);
const terminalPanelLines = ref([]);
const terminalPanelRef = ref(null);
const terminalPanelStatus = ref("idle");
const terminalPanelInput = ref("");
const terminalMirrorConnected = ref(false);

const maxUploadLimit = ref(6);
const chatMaxTokens = ref(512);

const selectedChatMode = computed({
  get() {
    return String(projectChatSettings.value.chat_mode || "system").trim();
  },
  set(value) {
    projectChatSettings.value = normalizeProjectChatSettings({
      ...projectChatSettings.value,
      chat_mode: String(value || "system").trim(),
    });
  },
});
const isExternalAgentMode = computed(
  () => selectedChatMode.value === "external_agent",
);
const chatModeLabel = computed(() =>
  isExternalAgentMode.value ? "外部 Agent" : "系统对话",
);
const wsStatusText = computed(() => (wsConnected.value ? "已连接" : "未连接"));
const wsStatusType = computed(() => (wsConnected.value ? "success" : "info"));
const composerPlaceholder = computed(() =>
  isExternalAgentMode.value
    ? "向 Codex CLI 发送输入，按 Enter 发送，Shift + Enter 换行。"
    : "输入你的问题，按 Enter 发送，Shift + Enter 换行。支持粘贴图片。",
);
const composerHintText = computed(() => {
  if (!isExternalAgentMode.value) return "按 Enter 发送";
  if (externalAgentWarmupLoading.value) return "Codex CLI 预热中...";
  if (externalAgentInfo.value.ready) return "Codex CLI 已就绪，Enter 直接发送";
  return "Enter 发送到 Codex CLI";
});
const shortThreadId = computed(() => {
  const value = String(externalAgentInfo.value.thread_id || '').trim();
  return value ? value.slice(0, 8) : '';
});
const terminalPanelStatusText = computed(() => {
  if (!isExternalAgentMode.value) return "未启用";
  if (terminalPanelStatus.value === "error") return "异常";
  if (chatLoading.value || terminalPanelStatus.value === "running") {
    return "运行中";
  }
  if (externalAgentWarmupLoading.value) return "预热中";
  if (
    terminalPanelStatus.value === "ready" ||
    externalAgentInfo.value.ready
  ) {
    return "待命";
  }
  return "未就绪";
});
const terminalPanelText = computed(() => {
  const lines = Array.isArray(terminalPanelLines.value)
    ? terminalPanelLines.value
        .map((line) => String(line || "").trim())
        .filter(Boolean)
    : [];
  if (lines.length) {
    return lines.join("\n");
  }
  const command = String(
    externalAgentInfo.value.resolved_command ||
      externalAgentInfo.value.command ||
      "codex",
  ).trim();
  const cwd = String(externalAgentInfo.value.workspace_path || "").trim();
  return [
    `# ${command}`,
    cwd ? `# cwd ${cwd}` : "",
    "# 等待外部 Agent 新请求…",
  ]
    .filter(Boolean)
    .join("\n");
});

const availableModels = computed(() => {
  const selected = (providers.value || []).find(
    (item) => item.id === selectedProviderId.value,
  );
  return Array.isArray(selected?.models) ? selected.models : [];
});

const systemProjectRelatedModules = computed(() => {
  const values = mcpModules.value?.system?.project_related;
  return Array.isArray(values) ? values : [];
});

const systemGlobalModules = computed(() => {
  const values = mcpModules.value?.system?.system_global;
  return Array.isArray(values) ? values : [];
});

const activeSystemModules = computed(() => {
  if (activeSystemScope.value === "system_global") {
    return systemGlobalModules.value;
  }
  return systemProjectRelatedModules.value;
});

const systemMcpTotal = computed(
  () =>
    systemProjectRelatedModules.value.length + systemGlobalModules.value.length,
);

const projectToolModules = computed(() =>
  systemProjectRelatedModules.value.filter((item) =>
    String(item?.tool_name || "").trim(),
  ),
);
const projectToolNameOptions = computed(() =>
  projectToolModules.value
    .map((item) => String(item?.tool_name || "").trim())
    .filter(Boolean),
);
const fileTypeOptions = computed(() =>
  normalizeStringList(
    [
      ...(CHAT_SETTINGS_DEFAULTS.allowed_file_types || []),
      ...(projectChatSettings.value.allowed_file_types || []),
    ],
    40,
  ),
);

const messagesContainer = ref(null);
const draftText = ref("");
const uploadFiles = ref([]);
const inputFocused = ref(false);
const isDragging = ref(false);
const IMAGE_EXTENSIONS = new Set([
  "png",
  "jpg",
  "jpeg",
  "gif",
  "bmp",
  "webp",
  "svg",
  "heic",
  "heif",
]);

function normalizeStringList(values, max = 200) {
  if (!Array.isArray(values)) return [];
  const set = new Set();
  const items = [];
  for (const item of values) {
    const text = String(item || "").trim();
    if (!text) continue;
    const key = text.toLowerCase();
    if (set.has(key)) continue;
    set.add(key);
    items.push(text);
    if (items.length >= max) break;
  }
  return items;
}

function detectHighRiskSignals(text) {
  const content = String(text || "");
  if (!content.trim()) return [];
  const findings = [];
  for (const rule of HIGH_RISK_RULES) {
    const matched = content.match(rule.pattern);
    if (!matched) continue;
    findings.push({
      id: rule.id,
      label: rule.label,
      severity: rule.severity,
      snippet: String(matched[0] || "")
        .trim()
        .replace(/\n/g, " ")
        .slice(0, 120),
    });
  }
  return findings;
}

function normalizeAuditPayload(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  const normalizeRiskItems = (values) =>
    Array.isArray(values)
      ? values.map((item) => ({
          id: String(item?.id || "").trim(),
          label: String(item?.label || "风险项").trim(),
          severity: String(item?.severity || "medium").trim(),
          snippet: String(item?.snippet || "").trim(),
        }))
      : [];
  const normalizeDiff = (value) => {
    const item = value && typeof value === "object" ? value : {};
    return {
      enabled: Boolean(item.enabled),
      reason: String(item.reason || "").trim(),
      repo_root: String(item.repo_root || "").trim(),
      changed_file_count: Number(item.changed_file_count || 0),
      status_lines: Array.isArray(item.status_lines)
        ? item.status_lines.map((line) => String(line || "").trim()).filter(Boolean)
        : [],
      diff_stat: String(item.diff_stat || "").trim(),
      staged_diff_stat: String(item.staged_diff_stat || "").trim(),
    };
  };
  return {
    approval_required: Boolean(source.approval_required),
    approval_mode: String(source.approval_mode || "").trim(),
    risk_signals: normalizeRiskItems(source.risk_signals),
    output_risk_signals: normalizeRiskItems(source.output_risk_signals),
    before_diff_summary: normalizeDiff(source.before_diff_summary),
    after_diff_summary: normalizeDiff(source.after_diff_summary),
    file_review_status: String(source.file_review_status || "not_required").trim() || "not_required",
  };
}

function getFileReviewStatusMeta(status) {
  const normalized = String(status || "not_required").trim();
  if (normalized === "pending") {
    return { label: "待审查", type: "warning", text: "检测到工作区文件改动，等待人工确认。" };
  }
  if (normalized === "approved") {
    return { label: "已通过", type: "success", text: "文件改动已人工确认，允许继续保留。" };
  }
  if (normalized === "rejected") {
    return { label: "已拒绝", type: "danger", text: "文件改动未通过人工确认，请回看 diff 后再处理。" };
  }
  return { label: "无需审查", type: "info", text: "当前未触发文件变更审查。" };
}

async function sendApprovalDecision(requestId, approvalId, approved) {
  if (!wsClient.value || !wsClient.value.isOpen()) {
    throw new Error("WebSocket 未连接");
  }
  wsClient.value.send({
    type: "approval_response",
    request_id: requestId,
    approval_id: approvalId,
    approved: Boolean(approved),
  });
}

async function sendFileReviewDecision(requestId, reviewId, approved) {
  if (!wsClient.value || !wsClient.value.isOpen()) {
    throw new Error("WebSocket 未连接");
  }
  wsClient.value.send({
    type: "file_review_response",
    request_id: requestId,
    review_id: reviewId,
    approved: Boolean(approved),
  });
}

function formatApprovalMessage(eventData) {
  const risks = Array.isArray(eventData?.risk_signals)
    ? eventData.risk_signals
    : [];
  const lines = [String(eventData?.message || "检测到高风险操作，需要确认后继续。")];
  if (risks.length) {
    lines.push("");
    lines.push("风险项：");
    for (const item of risks) {
      const label = String(item?.label || item?.id || "风险项").trim();
      const snippet = String(item?.snippet || "").trim();
      lines.push(`- ${label}${snippet ? `：${snippet}` : ""}`);
    }
  }
  return lines.join("\n");
}

async function handleApprovalRequired(eventData, row) {
  const requestId = String(eventData?.request_id || "").trim();
  const approvalId = String(eventData?.approval_id || "").trim();
  if (!requestId || !approvalId || activeApprovalIds.has(approvalId)) {
    return;
  }
  activeApprovalIds.add(approvalId);
  row.content = `${row.content || ""}\n\n> ⛔ 检测到高风险操作，等待审批...`.trim();
  scrollToBottom();
  try {
    await ElMessageBox.confirm(
      formatApprovalMessage(eventData),
      String(eventData?.title || "审批确认"),
      {
        confirmButtonText: "批准",
        cancelButtonText: "拒绝",
        type: "warning",
        distinguishCancelAndClose: true,
      },
    );
    await sendApprovalDecision(requestId, approvalId, true);
  } catch {
    try {
      await sendApprovalDecision(requestId, approvalId, false);
    } catch {
      // ignore
    }
  } finally {
    activeApprovalIds.delete(approvalId);
  }
}

function formatFileReviewMessage(eventData) {
  const diffSummary = eventData?.diff_summary && typeof eventData.diff_summary === "object"
    ? eventData.diff_summary
    : {};
  const lines = [String(eventData?.message || "检测到文件改动，请先确认是否允许保留本次变更。")];
  const changedFileCount = Number(diffSummary?.changed_file_count || 0);
  if (changedFileCount > 0) {
    lines.push(`改动文件数：${changedFileCount}`);
  }
  const diffStat = String(diffSummary?.diff_stat || "").trim();
  const statusLines = Array.isArray(diffSummary?.status_lines)
    ? diffSummary.status_lines.map((line) => String(line || "").trim()).filter(Boolean)
    : [];
  const preview = diffStat || statusLines.join("\n");
  if (preview) {
    lines.push("");
    lines.push("Diff 摘要：");
    lines.push(preview.slice(0, 2000));
  }
  return lines.join("\n");
}

async function handleFileReviewRequired(eventData, row) {
  const requestId = String(eventData?.request_id || "").trim();
  const reviewId = String(eventData?.review_id || "").trim();
  if (!requestId || !reviewId || activeReviewIds.has(reviewId)) {
    return;
  }
  activeReviewIds.add(reviewId);
  row.audit = normalizeAuditPayload({
    ...(row.audit && typeof row.audit === "object" ? row.audit : {}),
    after_diff_summary: eventData?.diff_summary || row.audit?.after_diff_summary || {},
    file_review_status: "pending",
  });
  row.content = `${row.content || ""}\n> 📝 检测到文件改动，等待审查确认`.trim();
  scrollToBottom();
  try {
    await ElMessageBox.confirm(
      formatFileReviewMessage(eventData),
      String(eventData?.title || "文件变更审查"),
      {
        confirmButtonText: "允许保留",
        cancelButtonText: "拒绝变更",
        type: "warning",
        distinguishCancelAndClose: true,
      },
    );
    await sendFileReviewDecision(requestId, reviewId, true);
  } catch {
    try {
      await sendFileReviewDecision(requestId, reviewId, false);
    } catch {
      // ignore
    }
  } finally {
    activeReviewIds.delete(reviewId);
  }
}

function normalizeExternalAgentInfo(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  return {
    agent_type: String(source.agent_type || "codex_cli").trim(),
    label: String(source.label || "Codex CLI").trim() || "Codex CLI",
    command: String(source.command || "codex").trim() || "codex",
    resolved_command: String(source.resolved_command || "").trim(),
    command_source: String(source.command_source || "missing").trim() || "missing",
    runtime_model_name: String(source.runtime_model_name || source.model_name || "codex-cli").trim() || "codex-cli",
    exact_model_name: String(source.exact_model_name || "").trim(),
    available: Boolean(source.available),
    ready: Boolean(source.ready),
    session_id: String(
      source.session_id || source.agent_session_id || "",
    ).trim(),
    thread_id: String(source.thread_id || "").trim(),
    sandbox_mode: String(source.sandbox_mode || "workspace-write").trim() || "workspace-write",
    workspace_path: String(source.workspace_path || "").trim(),
    context_root: String(source.context_root || "").trim(),
    support_dir: String(source.support_dir || "").trim(),
    mcp_bridge_enabled: Boolean(source.mcp_bridge_enabled),
    mcp_bridge_reason: String(source.mcp_bridge_reason || "").trim(),
    mcp_server_name: String(source.mcp_server_name || "").trim(),
    support_files: Array.isArray(source.support_files)
      ? source.support_files.map((item) => ({
          kind: String(item?.kind || "file").trim(),
          label: String(item?.label || item?.path || "文件").trim(),
          path: String(item?.path || "").trim(),
          written: Boolean(item?.written),
        }))
      : [],
    sandbox_modes: normalizeStringList(
      source.sandbox_modes || ["read-only", "workspace-write"],
      10,
    ),
  };
}

function normalizeProjectChatSettings(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  const legacySelected = String(source.selected_employee_id || "").trim();
  const selectedEmployeeIds = normalizeStringList(
    source.selected_employee_ids || [],
    200,
  );
  if (!selectedEmployeeIds.length && legacySelected) {
    selectedEmployeeIds.push(legacySelected);
  }
  const chatMode = String(source.chat_mode || CHAT_SETTINGS_DEFAULTS.chat_mode)
    .trim()
    .toLowerCase();
  const sandboxModeExplicit = Boolean(source.external_agent_sandbox_mode_explicit);
  const sandboxMode = String(
    source.external_agent_sandbox_mode ||
      CHAT_SETTINGS_DEFAULTS.external_agent_sandbox_mode,
  )
    .trim()
    .toLowerCase();
  const normalizedSandboxMode =
    sandboxMode === "read-only" || sandboxMode === "workspace-write"
      ? sandboxMode
      : CHAT_SETTINGS_DEFAULTS.external_agent_sandbox_mode;
  const effectiveSandboxMode =
    normalizedSandboxMode === "read-only" && !sandboxModeExplicit
      ? CHAT_SETTINGS_DEFAULTS.external_agent_sandbox_mode
      : normalizedSandboxMode;
  return {
    ...CHAT_SETTINGS_DEFAULTS,
    ...source,
    chat_mode:
      chatMode === "external_agent"
        ? "external_agent"
        : CHAT_SETTINGS_DEFAULTS.chat_mode,
    external_agent_type: "codex_cli",
    external_agent_sandbox_mode: effectiveSandboxMode,
    external_agent_sandbox_mode_explicit: sandboxModeExplicit,
    selected_employee_ids: selectedEmployeeIds,
    enabled_project_tool_names: normalizeStringList(
      source.enabled_project_tool_names ||
        CHAT_SETTINGS_DEFAULTS.enabled_project_tool_names,
    ),
    tool_priority: normalizeStringList(
      source.tool_priority || CHAT_SETTINGS_DEFAULTS.tool_priority,
    ),
    allowed_file_types: normalizeStringList(
      source.allowed_file_types || CHAT_SETTINGS_DEFAULTS.allowed_file_types,
      40,
    ),
  };
}

const effectiveUploadLimit = computed(() => {
  const projectLimit = Number(
    projectChatSettings.value.upload_file_limit ||
      CHAT_SETTINGS_DEFAULTS.upload_file_limit,
  );
  const systemLimit = Number(
    maxUploadLimit.value || CHAT_SETTINGS_DEFAULTS.upload_file_limit,
  );
  return Math.max(1, Math.min(projectLimit, systemLimit));
});

const maxFileSizeMb = computed(() =>
  Number(
    projectChatSettings.value.max_file_size_mb ||
      CHAT_SETTINGS_DEFAULTS.max_file_size_mb,
  ),
);

const historyLimit = computed(() =>
  Number(
    projectChatSettings.value.history_limit ||
      CHAT_SETTINGS_DEFAULTS.history_limit,
  ),
);

const docMaxCharsPerFile = computed(() =>
  Number(
    projectChatSettings.value.doc_max_chars_per_file ||
      CHAT_SETTINGS_DEFAULTS.doc_max_chars_per_file,
  ),
);

const docMaxCharsTotal = computed(() =>
  Number(
    projectChatSettings.value.doc_max_chars_total ||
      CHAT_SETTINGS_DEFAULTS.doc_max_chars_total,
  ),
);

const allowedFileTypes = computed(() =>
  normalizeStringList(
    projectChatSettings.value.allowed_file_types ||
      CHAT_SETTINGS_DEFAULTS.allowed_file_types,
    40,
  ).map((item) => item.toLowerCase()),
);

const canSend = computed(() => {
  if (chatLoading.value) return false;
  if (String(draftText.value || "").trim()) return true;
  if (isExternalAgentMode.value) return false;
  return uploadFiles.value.length > 0;
});

function formatContent(text) {
  if (!text) return "";
  try {
    return marked.parse(text);
  } catch (e) {
    return text;
  }
}

function scrollTerminalPanelBottom() {
  nextTick(() => {
    if (terminalPanelRef.value) {
      terminalPanelRef.value.scrollTop = terminalPanelRef.value.scrollHeight;
    }
  });
}

function appendTerminalPanelLine(text) {
  const line = String(text || '').trim();
  if (!line) return;
  const lines = Array.isArray(terminalPanelLines.value)
    ? terminalPanelLines.value.slice()
    : [];
  if (lines.length && lines[lines.length - 1] === line) return;
  lines.push(line);
  if (lines.length > 400) {
    lines.splice(0, lines.length - 400);
  }
  terminalPanelLines.value = lines;
  scrollTerminalPanelBottom();
}

function clearTerminalPanel() {
  terminalPanelLines.value = [];
  scrollTerminalPanelBottom();
}

function resetTerminalPanel() {
  terminalPanelLines.value = [];
  terminalPanelStatus.value = 'idle';
  terminalPanelInput.value = "";
  terminalMirrorConnected.value = false;
  scrollTerminalPanelBottom();
}

async function startTerminalMirror() {
  if (!isExternalAgentMode.value) return;
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return;
  if (!externalAgentInfo.value.thread_id) {
    await prepareExternalAgentSession({ silent: true });
  }
  const client = await ensureWsClient(projectId);
  client.send({
    type: "terminal_mirror_start",
    request_id: `mirror-start-${Date.now()}`,
    chat_mode: "external_agent",
    external_agent_type: "codex_cli",
    external_agent_sandbox_mode:
      projectChatSettings.value.external_agent_sandbox_mode || "workspace-write",
    external_agent_sandbox_mode_explicit: true,
  });
}

async function stopTerminalMirror() {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId || !wsClient.value) return;
  wsClient.value.send({
    type: "terminal_mirror_stop",
    request_id: `mirror-stop-${Date.now()}`,
  });
  terminalMirrorConnected.value = false;
}

async function sendTerminalMirrorInput() {
  const content = String(terminalPanelInput.value || "").trim();
  if (!content) return;
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return;
  const client = await ensureWsClient(projectId);
  if (!terminalMirrorConnected.value) {
    await startTerminalMirror();
  }
  appendTerminalPanelLine(`› ${content}`);
  client.send({
    type: "terminal_mirror_input",
    request_id: `mirror-input-${Date.now()}`,
    chat_mode: "external_agent",
    external_agent_type: "codex_cli",
    external_agent_sandbox_mode:
      projectChatSettings.value.external_agent_sandbox_mode || "workspace-write",
    external_agent_sandbox_mode_explicit: true,
    content,
  });
  terminalPanelInput.value = "";
}

function appendTerminalLog(row, text) {
  if (!row || row.displayMode !== "terminal") return;
  const line = String(text || "").trim();
  if (!line) return;
  const logs = Array.isArray(row.terminalLog) ? row.terminalLog.slice() : [];
  if (logs.length && logs[logs.length - 1] === line) return;
  logs.push(line);
  if (logs.length > 160) {
    logs.splice(0, logs.length - 160);
  }
  row.terminalLog = logs;
  appendTerminalPanelLine(line);
}

function formatTerminalMessage(item, idx) {
  const logs = Array.isArray(item?.terminalLog)
    ? item.terminalLog.map((line) => String(line || "").trim()).filter(Boolean)
    : [];
  const answer = String(item?.content || "").trim();
  if (logs.length && answer) {
    return `${logs.join("\n")}\n\n${answer}`;
  }
  if (logs.length) {
    return logs.join("\n");
  }
  if (answer) {
    return answer;
  }
  return chatLoading.value && idx === messages.value.length - 1
    ? "等待外部 Agent 输出..."
    : "";
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    }
  });
}

function extractImages(message) {
  if (!message || !Array.isArray(message.images)) return [];
  return message.images
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function fileExtension(name) {
  const text = String(name || "").trim();
  const idx = text.lastIndexOf(".");
  if (idx < 0 || idx === text.length - 1) return "";
  return text.slice(idx + 1).toLowerCase();
}

function isImageFile(file) {
  const mime = String(file?.type || "").toLowerCase();
  if (mime.startsWith("image/")) return true;
  return IMAGE_EXTENSIONS.has(fileExtension(file?.name || ""));
}

function isAllowedFileType(file) {
  const rules = allowedFileTypes.value;
  if (!rules.length) return true;
  const mime = String(file?.type || "").toLowerCase();
  const ext = `.${fileExtension(file?.name || "")}`;
  for (const rule of rules) {
    if (!rule) continue;
    if (rule === "image/*" && isImageFile(file)) return true;
    if (rule.endsWith("/*") && mime.startsWith(rule.slice(0, -1))) return true;
    if (rule.startsWith(".") && rule === ext) return true;
    if (rule === mime) return true;
  }
  return false;
}

function formatFileType(name) {
  const ext = fileExtension(name);
  return ext ? ext.toUpperCase() : "FILE";
}

function clipText(text, maxChars) {
  const value = String(text || "").trim();
  if (!value) return "";
  if (value.length <= maxChars) return value;
  return `${value.slice(0, maxChars)}\n（内容已截断）`;
}

function normalizeAttachment(name) {
  const normalizedName = String(name || "").trim();
  if (!normalizedName) return null;
  const ext = fileExtension(normalizedName);
  const kind = IMAGE_EXTENSIONS.has(ext) ? "image" : "document";
  return {
    name: normalizedName,
    kind,
    ext,
  };
}

function extractAttachments(message) {
  const values = Array.isArray(message?.attachments) ? message.attachments : [];
  return values.map(normalizeAttachment).filter(Boolean);
}

function attachmentTagType(kind) {
  return kind === "image" ? "success" : "info";
}

function attachmentTypeLabel(attachment) {
  const ext = String(attachment?.ext || "")
    .trim()
    .toUpperCase();
  if (ext) return ext;
  return attachment?.kind === "image" ? "图片" : "文档";
}

function handleFileChange(file) {
  const raw = file.raw;
  if (!raw) return;
  const isImage = isImageFile(raw);
  if (!isAllowedFileType(raw)) {
    ElMessage.error("文件类型不在当前项目对话设置允许范围内");
    return;
  }
  const sizeMB = raw.size / (1024 * 1024);
  if (sizeMB > maxFileSizeMb.value) {
    ElMessage.error(`文件超过 ${maxFileSizeMb.value}MB`);
    return;
  }
  if (uploadFiles.value.length >= effectiveUploadLimit.value) {
    ElMessage.warning(`最多只能上传 ${effectiveUploadLimit.value} 个文件`);
    return;
  }

  if (isImage) {
    file.url = URL.createObjectURL(raw);
    file.kind = "image";
  } else {
    file.url = "";
    file.kind = "document";
  }
  uploadFiles.value.push(file);
}

function handleDragOver() {
  isDragging.value = true;
}

function handleDragLeave() {
  isDragging.value = false;
}

function handleDrop(e) {
  isDragging.value = false;
  const files = e.dataTransfer?.files;
  if (!files || files.length === 0) return;
  for (let i = 0; i < files.length; i++) {
    handleFileChange({ raw: files[i], name: files[i].name });
  }
}

function handlePaste(event) {
  if (!event.clipboardData || !event.clipboardData.items) return;

  const items = event.clipboardData.items;
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (
      item.type.indexOf("image") !== -1 ||
      item.type.indexOf("text/plain") === -1
    ) {
      const file = item.getAsFile();
      if (file) {
        event.preventDefault();
        handleFileChange({ raw: file, name: file.name || "clipboard_file" });
      }
    }
  }
}

function removeFile(index) {
  uploadFiles.value.splice(index, 1);
}

function resetDraft() {
  draftText.value = "";
  uploadFiles.value = [];
}

function nowText() {
  return new Date().toLocaleString();
}

function toHistoryRows(sourceMessages, limit = 20) {
  const safeLimit = Math.max(1, Math.min(Number(limit || 20), 50));
  return (sourceMessages || [])
    .map((item) => ({
      role: String(item.role || "")
        .trim()
        .toLowerCase(),
      content: String(item.content || "").trim(),
    }))
    .filter(
      (item) =>
        (item.role === "user" || item.role === "assistant") && item.content,
    )
    .slice(-safeLimit);
}

function normalizeMcpModules(payload) {
  const systemProjectRelated = Array.isArray(payload?.system?.project_related)
    ? payload.system.project_related
    : [];
  const systemGlobal = Array.isArray(payload?.system?.system_global)
    ? payload.system.system_global
    : [];
  const external = Array.isArray(payload?.external?.modules)
    ? payload.external.modules
    : [];
  return {
    system: {
      project_related: systemProjectRelated,
      system_global: systemGlobal,
    },
    external: {
      modules: external,
    },
    summary: {
      system_project_related_total: Number(
        payload?.summary?.system_project_related_total ||
          systemProjectRelated.length,
      ),
      system_global_total: Number(
        payload?.summary?.system_global_total || systemGlobal.length,
      ),
      external_total: Number(
        payload?.summary?.external_total || external.length,
      ),
    },
  };
}

function syncSelectedProjectTools(modules) {
  const names = (modules || [])
    .map((item) => String(item?.tool_name || "").trim())
    .filter(Boolean);
  const previous = new Set(selectedProjectToolNames.value);
  const kept = names.filter((name) => previous.has(name));
  selectedProjectToolNames.value = kept.length ? kept : names;
}

function isProjectToolSelected(toolName) {
  const normalized = String(toolName || "").trim();
  if (!normalized) return false;
  return selectedProjectToolNames.value.includes(normalized);
}

function toggleProjectTool(toolName, checked) {
  const normalized = String(toolName || "").trim();
  if (!normalized) return;
  if (checked) {
    if (!selectedProjectToolNames.value.includes(normalized)) {
      selectedProjectToolNames.value.push(normalized);
    }
    return;
  }
  selectedProjectToolNames.value = selectedProjectToolNames.value.filter(
    (item) => item !== normalized,
  );
}

function selectAllProjectTools() {
  selectedProjectToolNames.value = projectToolModules.value
    .map((item) => String(item?.tool_name || "").trim())
    .filter(Boolean);
}

function clearProjectTools() {
  selectedProjectToolNames.value = [];
}

function moduleTypeLabel(moduleType) {
  const normalized = String(moduleType || "")
    .trim()
    .toLowerCase();
  const map = {
    builtin_tool: "系统工具",
    project_skill_tool: "项目技能",
    project_mcp_service: "项目服务",
    employee_mcp_service: "员工服务",
    skill_mcp_service: "技能服务",
    rule_mcp_service: "规则服务",
    external_mcp_service: "外部服务",
  };
  return map[normalized] || "MCP 模块";
}

function moduleTagType(moduleType) {
  const normalized = String(moduleType || "")
    .trim()
    .toLowerCase();
  if (normalized === "builtin_tool" || normalized === "project_mcp_service")
    return "success";
  if (normalized === "project_skill_tool" || normalized === "skill_mcp_service")
    return "warning";
  if (normalized === "employee_mcp_service") return "info";
  if (normalized === "rule_mcp_service") return "danger";
  return "info";
}

function moduleMetaText(item) {
  const parts = [];
  const toolName = String(item?.tool_name || "").trim();
  const employeeName = String(item?.employee_name || "").trim();
  const endpoint = String(
    item?.endpoint_http || item?.endpoint_sse || "",
  ).trim();
  const projectScope = String(item?.project_id || "").trim();
  if (employeeName) parts.push(`员工: ${employeeName}`);
  if (toolName) parts.push(`工具: ${toolName}`);
  if (endpoint) parts.push(`入口: ${endpoint}`);
  if (projectScope) parts.push(`范围: 项目(${projectScope})`);
  if (!projectScope && String(item?.scope || "").trim() === "external")
    parts.push("范围: 全局");
  return parts.join(" | ");
}

function handleExternalModuleCountChange(count) {
  externalMcpTotal.value = Number(count || 0);
}

function handleExternalModulesChanged(modules) {
  externalMcpTotal.value = Array.isArray(modules) ? modules.length : 0;
}

async function fetchSystemConfig() {
  try {
    const data = await api.get("/system-config");
    if (data?.config?.chat_upload_max_limit) {
      maxUploadLimit.value = Number(data.config.chat_upload_max_limit);
    }
    if (data?.config?.chat_max_tokens) {
      chatMaxTokens.value = Number(data.config.chat_max_tokens);
    }
  } catch (err) {
    console.error("加载系统配置失败", err);
  }
}

async function fetchProjects() {
  const data = await api.get("/projects");
  projects.value = data.projects || [];
}

function syncProjectFromRoute() {
  const routeProjectId = String(route.query.project_id || "").trim();
  const exists = (projects.value || []).some(
    (item) => item.id === routeProjectId,
  );
  const initialProjectId = exists ? routeProjectId : "";
  selectedProjectId.value = exists
    ? initialProjectId
    : String(projects.value[0]?.id || "");
}

async function fetchProvidersByProject(projectId) {
  if (!projectId) {
    chatModes.value = [
      { id: "system", label: "系统对话" },
      { id: "external_agent", label: "外部 Agent" },
    ];
    providers.value = [];
    projectEmployees.value = [];
    externalAgentInfo.value = normalizeExternalAgentInfo({});
    mcpModules.value = normalizeMcpModules({});
    externalMcpTotal.value = 0;
    projectChatSettings.value = { ...CHAT_SETTINGS_DEFAULTS };
    selectedProjectToolNames.value = [];
    selectedEmployeeIds.value = [];
    selectedProviderId.value = "";
    selectedModelName.value = "";
    systemPrompt.value = "";
    temperature.value = CHAT_SETTINGS_DEFAULTS.temperature;
    chatMaxTokens.value = CHAT_SETTINGS_DEFAULTS.max_tokens;
    void stopTerminalMirror().catch(() => {});
    resetTerminalPanel();
    return;
  }
  const data = await api.get(
    `/projects/${encodeURIComponent(projectId)}/chat/providers`,
  );
  const rawSettings =
    data?.chat_settings && typeof data.chat_settings === "object"
      ? data.chat_settings
      : {};
  const settings = normalizeProjectChatSettings(rawSettings);
  projectChatSettings.value = settings;
  chatModes.value = Array.isArray(data?.chat_modes) && data.chat_modes.length
    ? data.chat_modes
    : chatModes.value;
  providers.value = data.providers || [];
  projectEmployees.value = data.employees || [];
  externalAgentInfo.value = normalizeExternalAgentInfo(data?.external_agent || {});
  mcpModules.value = normalizeMcpModules(data.mcp_modules || {});
  externalMcpTotal.value = Number(
    data?.mcp_modules?.summary?.external_total ||
      mcpModules.value?.external?.modules?.length ||
      0,
  );
  syncSelectedProjectTools(mcpModules.value?.system?.project_related || []);

  const availableToolNames = new Set(
    projectToolModules.value
      .map((item) => String(item?.tool_name || "").trim())
      .filter(Boolean),
  );
  const savedToolNames = normalizeStringList(
    settings.enabled_project_tool_names || [],
  ).filter((name) => availableToolNames.has(name));
  const hasSavedToolSelection = Array.isArray(
    rawSettings?.enabled_project_tool_names,
  );
  if (hasSavedToolSelection) {
    selectedProjectToolNames.value = savedToolNames;
  }

  const allEmployeeIds = projectEmployees.value
    .map((item) => String(item?.id || "").trim())
    .filter(Boolean);
  const savedEmployeeIds = normalizeStringList(
    settings.selected_employee_ids || [],
  );
  const validSavedEmployeeIds = savedEmployeeIds.filter((id) =>
    allEmployeeIds.includes(id),
  );
  selectedEmployeeIds.value =
    validSavedEmployeeIds.length > 0 ? validSavedEmployeeIds : allEmployeeIds;

  defaultProviderId.value = String(data.default_provider_id || "");
  defaultModelName.value = String(data.default_model_name || "");

  const preferredProviderId = String(settings.provider_id || "").trim();
  const hasPreferredProvider = providers.value.some(
    (item) => item.id === preferredProviderId,
  );
  selectedProviderId.value = hasPreferredProvider
    ? preferredProviderId
    : defaultProviderId.value;

  const providerModels = (
    providers.value.find((item) => item.id === selectedProviderId.value)
      ?.models || []
  )
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const preferredModelName = String(settings.model_name || "").trim();
  if (preferredModelName && providerModels.includes(preferredModelName)) {
    selectedModelName.value = preferredModelName;
  } else {
    selectedModelName.value = String(
      defaultModelName.value || providerModels[0] || "",
    );
  }

  systemPrompt.value = String(settings.system_prompt || "");
  temperature.value = Number(
    settings.temperature ?? CHAT_SETTINGS_DEFAULTS.temperature,
  );
  chatMaxTokens.value = Number(
    settings.max_tokens ?? CHAT_SETTINGS_DEFAULTS.max_tokens,
  );
}

function buildProjectChatSettingsPayload() {
  const employeeIds = normalizeStringList(selectedEmployeeIds.value || []);
  return normalizeProjectChatSettings({
    ...projectChatSettings.value,
    chat_mode: String(selectedChatMode.value || "system").trim(),
    external_agent_type: "codex_cli",
    external_agent_sandbox_mode: String(
      projectChatSettings.value.external_agent_sandbox_mode || "workspace-write",
    ).trim(),
    external_agent_sandbox_mode_explicit: true,
    selected_employee_id: employeeIds.length === 1 ? employeeIds[0] : "",
    selected_employee_ids: employeeIds,
    provider_id: String(selectedProviderId.value || "").trim(),
    model_name: String(selectedModelName.value || "").trim(),
    temperature: Number(
      temperature.value ?? CHAT_SETTINGS_DEFAULTS.temperature,
    ),
    max_tokens: Number(
      chatMaxTokens.value || CHAT_SETTINGS_DEFAULTS.max_tokens,
    ),
    system_prompt: String(systemPrompt.value || ""),
    enabled_project_tool_names: [...selectedProjectToolNames.value],
  });
}

async function saveProjectChatSettings(silent = false) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    if (!silent) {
      ElMessage.warning("请先选择项目");
    }
    return;
  }
  settingsSaving.value = true;
  try {
    const payload = buildProjectChatSettingsPayload();
    const data = await api.put(
      `/projects/${encodeURIComponent(projectId)}/chat/settings`,
      { settings: payload },
    );
    projectChatSettings.value = normalizeProjectChatSettings(
      data?.settings || payload,
    );
    // 以服务端回读结果为准，避免“保存成功但界面仍旧值”的状态分叉。
    await fetchProvidersByProject(projectId);
    if (selectedChatMode.value === "external_agent") {
      await prepareExternalAgentSession({ force: true, silent: true });
    }
    if (!silent) {
      showSettingsDialog.value = false;
    }
    if (!silent) {
      ElMessage.success("项目对话设置已保存");
    }
  } catch (err) {
    if (!silent) {
      ElMessage.error(err?.detail || err?.message || "保存对话设置失败");
    }
  } finally {
    settingsSaving.value = false;
  }
}

function mapHistoryMessage(item) {
  const attachments = Array.isArray(item?.attachments) ? item.attachments : [];
  const images = Array.isArray(item?.images) ? item.images : [];
  return {
    id: String(item?.id || ""),
    role: String(item?.role || "assistant"),
    content: String(item?.content || ""),
    displayMode: String(item?.display_mode || "").trim(),
    terminalLog: [],
    audit: null,
    images: images,
    attachments,
    time: String(item?.created_at || ""),
  };
}

async function fetchChatHistory(projectId) {
  if (!projectId) {
    messages.value = [];
    return;
  }
  try {
    const data = await api.get(
      `/projects/${encodeURIComponent(projectId)}/chat/history`,
      {
        params: { limit: 200 },
      },
    );
    messages.value = (data.messages || []).map(mapHistoryMessage);
    scrollToBottom();
  } catch (err) {
    messages.value = [];
    ElMessage.error(err?.detail || err?.message || "加载聊天记录失败");
  }
}

function handleProviderChange() {
  const selected = (providers.value || []).find(
    (item) => item.id === selectedProviderId.value,
  );
  const modelList = Array.isArray(selected?.models) ? selected.models : [];
  if (
    !selectedModelName.value ||
    !modelList.includes(selectedModelName.value)
  ) {
    selectedModelName.value = String(
      selected?.default_model || modelList[0] || "",
    );
  }
}

async function clearMessages() {
  if (!selectedProjectId.value) {
    messages.value = [];
    return;
  }
  try {
    await api.delete(
      `/projects/${encodeURIComponent(selectedProjectId.value)}/chat/history`,
    );
    messages.value = [];
    ElMessage.success("聊天记录已清空");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "清空聊天记录失败");
  }
}

function isIntentOnlyReply(text) {
  const value = String(text || "").trim();
  if (!value || value.length > 180) return false;
  return (
    /^(我先|我会先|我去|我来|让我先|先帮你|正在|稍等)/.test(value) ||
    /(查一下|查询一下|先查|先检索|马上返回|稍后返回)/.test(value)
  );
}

function handleSocketMessage(eventData) {
  const eventType = String(eventData?.type || "")
    .trim()
    .toLowerCase();
  const requestId = String(eventData?.request_id || "").trim();
  if (eventType === "ready" || eventType === "pong") {
    return;
  }
  if (eventType === "agent_ready") {
    externalAgentWarmupLoading.value = false;
    terminalPanelStatus.value = "ready";
    appendTerminalPanelLine(`# 会话已预热 · thread=${String(eventData?.thread_id || "-").trim() || "-"}`);
    externalAgentInfo.value = normalizeExternalAgentInfo({
      ...externalAgentInfo.value,
      ...eventData,
      available: true,
      ready: true,
      session_id: String(
        eventData?.agent_session_id || eventData?.session_id || "",
      ).trim(),
    });
    const pendingPrepare = pendingAgentPrepares.get(requestId);
    if (pendingPrepare) {
      pendingAgentPrepares.delete(requestId);
      pendingPrepare.resolve(eventData);
    }
    void startTerminalMirror().catch(() => {});
    return;
  }
  if (eventType === "terminal_mirror_started") {
    terminalMirrorConnected.value = true;
    appendTerminalPanelLine(`# 真实终端镜像已连接 · thread=${String(eventData?.thread_id || "-").trim() || "-"}`);
    return;
  }
  if (eventType === "terminal_mirror_stopped") {
    terminalMirrorConnected.value = false;
    appendTerminalPanelLine(`# 真实终端镜像已停止`);
    return;
  }
  if (eventType === "terminal_mirror_chunk") {
    terminalMirrorConnected.value = true;
    appendTerminalPanelLine(String(eventData?.content || ""));
    return;
  }
  if (!requestId) {
    if (eventType === "error") {
    terminalPanelStatus.value = "error";
      ElMessage.error(String(eventData?.message || "对话异常"));
    }
    return;
  }
  if (eventType === "error" && pendingAgentPrepares.has(requestId)) {
    terminalPanelStatus.value = "error";
    const pendingPrepare = pendingAgentPrepares.get(requestId);
    pendingAgentPrepares.delete(requestId);
    externalAgentWarmupLoading.value = false;
    externalAgentInfo.value = {
      ...externalAgentInfo.value,
      ready: false,
    };
    pendingPrepare?.reject(new Error(String(eventData?.message || "外部 Agent 预热失败")));
    return;
  }
  const pending = pendingRequests.get(requestId);
  if (!pending) return;
  const row = messages.value[pending.assistantIndex];
  if (!row) {
    pendingRequests.delete(requestId);
    pending.reject(new Error("消息上下文已失效"));
    return;
  }
  if (eventType === "start") {
    terminalPanelStatus.value = "running";
    row.displayMode =
      String(eventData?.chat_mode || "").trim() === "external_agent"
        ? "terminal"
        : "";
    if (String(eventData?.chat_mode || "").trim() === "external_agent") {
      externalAgentInfo.value = normalizeExternalAgentInfo({
        ...externalAgentInfo.value,
        ...eventData,
        ready: true,
        session_id: String(
          eventData?.agent_session_id || externalAgentInfo.value.session_id || "",
        ).trim(),
        support_dir: String(eventData?.support_dir || externalAgentInfo.value.support_dir || "").trim(),
        mcp_bridge_enabled: Boolean(
          eventData?.mcp_bridge_enabled ?? externalAgentInfo.value.mcp_bridge_enabled,
        ),
        mcp_bridge_reason: String(
          eventData?.mcp_bridge_reason || externalAgentInfo.value.mcp_bridge_reason || "",
        ).trim(),
        mcp_server_name: String(
          eventData?.mcp_server_name || externalAgentInfo.value.mcp_server_name || "",
        ).trim(),
        support_files: Array.isArray(eventData?.support_files)
          ? eventData.support_files.map((item) => ({
              kind: String(item?.kind || "file").trim(),
              label: String(item?.label || item?.path || "文件").trim(),
              path: String(item?.path || "").trim(),
              written: Boolean(item?.written),
            }))
          : externalAgentInfo.value.support_files,
      });
      appendTerminalLog(
        row,
        `# Codex CLI 已连接 · sandbox=${String(eventData?.sandbox_mode || "workspace-write").trim()} · thread=${String(eventData?.thread_id || "-").trim() || "-"}`,
      );
    }
    return;
  }
  if (eventType === "approval_required") {
    void handleApprovalRequired(eventData, row);
    return;
  }
  if (eventType === "approval_resolved") {
    const approved = Boolean(eventData?.approved);
    row.content = approved
      ? `${row.content || ""}\n> ✅ 已批准，继续执行`.trim()
      : `${row.content || ""}\n> ❌ 已拒绝，本次执行取消`.trim();
    scrollToBottom();
    return;
  }
  if (eventType === "file_review_required") {
    row.audit = normalizeAuditPayload({
      ...(row.audit && typeof row.audit === "object" ? row.audit : {}),
      after_diff_summary: eventData?.diff_summary || row.audit?.after_diff_summary || {},
      file_review_status: "pending",
    });
    void handleFileReviewRequired(eventData, row);
    return;
  }
  if (eventType === "file_review_resolved") {
    const approved = Boolean(eventData?.approved);
    row.audit = normalizeAuditPayload({
      ...(row.audit && typeof row.audit === "object" ? row.audit : {}),
      file_review_status: approved ? "approved" : "rejected",
    });
    row.content = approved
      ? `${row.content || ""}\n> ✅ 文件变更已审查通过`.trim()
      : `${row.content || ""}\n> ❌ 文件变更未通过审查`.trim();
    scrollToBottom();
    return;
  }
  if (eventType === "status") {
    appendTerminalLog(row, `› ${String(eventData?.message || "处理中...").trim()}`);
    scrollToBottom();
    return;
  }
  if (eventType === "stderr") {
    appendTerminalLog(row, `! ${String(eventData?.message || "").trim()}`);
    scrollToBottom();
    return;
  }
  if (eventType === "command_start") {
    appendTerminalLog(row, `$ ${String(eventData?.command || "").trim() || "(command)"}`);
    scrollToBottom();
    return;
  }
  if (eventType === "command_result") {
    const exitCode = eventData?.exit_code;
    const statusText = String(eventData?.status || "completed").trim() || "completed";
    const exitLabel =
      exitCode === null || exitCode === undefined ? statusText : `exit=${exitCode}`;
    appendTerminalLog(row, `# 命令完成 · ${exitLabel}`);
    const outputPreview = String(eventData?.output_preview || "").trim();
    if (outputPreview) {
      appendTerminalLog(row, outputPreview);
    }
    scrollToBottom();
    return;
  }
  if (eventType === "usage") {
    const usage = eventData?.usage && typeof eventData.usage === "object"
      ? eventData.usage
      : {};
    appendTerminalLog(
      row,
      `# tokens in=${Number(usage.input_tokens || 0)} cache=${Number(usage.cached_input_tokens || 0)} out=${Number(usage.output_tokens || 0)}`,
    );
    scrollToBottom();
    return;
  }
  if (eventType === "delta") {
    row.content = `${row.content || ""}${String(eventData?.content || "")}`;
    scrollToBottom();
    return;
  }
  if (eventType === "audit") {
    row.audit = normalizeAuditPayload(eventData?.audit || {});
    scrollToBottom();
    return;
  }
  if (eventType === "tool_start") {
    const toolName = String(eventData?.tool_name || "工具");
    row.content = `${row.content || ""}\n\n> ⏳ 正在调用工具：\`${toolName}\``;
    scrollToBottom();
    return;
  }
  if (eventType === "tool_result") {
    const toolName = String(eventData?.tool_name || "工具");
    row.content = `${row.content || ""}\n\n> ✅ 工具调用完成：\`${toolName}\``;
    scrollToBottom();
    return;
  }
  if (eventType === "done") {
    terminalPanelStatus.value = "idle";
    const doneContent = String(eventData?.content || "").trim();
    const currentContent = String(row.content || "").trim();
    if (!currentContent) {
      row.content = doneContent;
    } else if (doneContent && currentContent !== doneContent) {
      if (
        isIntentOnlyReply(currentContent) ||
        /达到最大处理轮次|已停止生成/.test(doneContent)
      ) {
        row.content = doneContent;
      }
    }
    pendingRequests.delete(requestId);
    pending.resolve(row.content || "");
    scrollToBottom();
    return;
  }
  if (eventType === "error") {
    terminalPanelStatus.value = "error";
    const message = String(eventData?.message || "未知错误");
    appendTerminalPanelLine(`! ${message}`);
    row.content = `对话失败：${message}`;
    pendingRequests.delete(requestId);
    pending.reject(new Error(message));
    scrollToBottom();
  }
}

function rejectPendingRequests(reason) {
  const message = String(reason || "连接已断开").trim();
  const items = Array.from(pendingRequests.entries());
  for (const [requestId, pending] of items) {
    const row = messages.value[pending.assistantIndex];
    if (row && !String(row.content || "").trim()) {
      row.content = `请求失败：${message}`;
    }
    pending.reject(new Error(message));
    pendingRequests.delete(requestId);
  }
}

function rejectPendingAgentPrepares(reason) {
  const message = String(reason || "连接已断开").trim();
  const items = Array.from(pendingAgentPrepares.entries());
  for (const [requestId, pending] of items) {
    pending.reject(new Error(message));
    pendingAgentPrepares.delete(requestId);
  }
  externalAgentWarmupLoading.value = false;
  externalAgentInfo.value = {
    ...externalAgentInfo.value,
    ready: false,
    session_id: "",
  };
  externalAgentWarmupKey.value = "";
}

function buildExternalAgentWarmupKey(projectId) {
  return JSON.stringify({
    projectId: String(projectId || "").trim(),
    sandboxMode: String(
      projectChatSettings.value.external_agent_sandbox_mode || "workspace-write",
    ).trim(),
    systemPrompt: String(systemPrompt.value || "").trim(),
    employeeIds: normalizeStringList(selectedEmployeeIds.value || []),
  });
}

async function prepareExternalAgentSession({ force = false, silent = true } = {}) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId || !isExternalAgentMode.value) return;
  if (!externalAgentInfo.value.available) return;
  if (!String(externalAgentInfo.value.workspace_path || "").trim()) return;

  const warmupKey = buildExternalAgentWarmupKey(projectId);
  if (
    !force &&
    externalAgentInfo.value.ready &&
    externalAgentWarmupKey.value === warmupKey &&
    String(externalAgentInfo.value.session_id || "").trim()
  ) {
    return;
  }
  if (externalAgentWarmupLoading.value) {
    return;
  }

  const employeeIds = normalizeStringList(selectedEmployeeIds.value || []);
  const requestId = `agent-prepare-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  externalAgentWarmupLoading.value = true;
  try {
    const client = await ensureWsClient(projectId);
    const donePromise = new Promise((resolve, reject) => {
      pendingAgentPrepares.set(requestId, { resolve, reject });
    });
    client.send({
      type: "agent_prepare",
      request_id: requestId,
      chat_mode: "external_agent",
      external_agent_type: "codex_cli",
      external_agent_sandbox_mode:
        projectChatSettings.value.external_agent_sandbox_mode || "workspace-write",
      external_agent_sandbox_mode_explicit: true,
      employee_ids: employeeIds,
      employee_id: employeeIds.length === 1 ? employeeIds[0] : undefined,
      system_prompt: systemPrompt.value || undefined,
    });
    await donePromise;
    externalAgentWarmupKey.value = warmupKey;
  } catch (err) {
    externalAgentWarmupKey.value = "";
    if (!silent) {
      ElMessage.error(err?.message || "外部 Agent 预热失败");
    }
    throw err;
  } finally {
    pendingAgentPrepares.delete(requestId);
    externalAgentWarmupLoading.value = false;
  }
}

function disconnectWs(reason = "") {
  if (wsClient.value) {
    wsClient.value.close(1000, reason || "client close");
  }
  terminalMirrorConnected.value = false;
  wsClient.value = null;
  wsConnected.value = false;
  wsProjectId.value = "";
  rejectPendingAgentPrepares(reason || "连接已断开");
}

async function ensureWsClient(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) {
    throw new Error("缺少项目 ID");
  }
  if (
    wsClient.value &&
    wsProjectId.value === normalizedProjectId &&
    wsClient.value.isOpen()
  ) {
    return wsClient.value;
  }
  disconnectWs("switch project");

  const token = String(localStorage.getItem("token") || "").trim();
  if (!token) {
    throw new Error("登录状态失效，请重新登录");
  }
  wsProjectId.value = normalizedProjectId;
  const client = createProjectChatWsClient({
    projectId: normalizedProjectId,
    token,
    onOpen: () => {
      wsConnected.value = true;
    },
    onMessage: handleSocketMessage,
    onError: () => {
      wsConnected.value = false;
    },
    onClose: (event) => {
      wsConnected.value = false;
      wsClient.value = null;
      const code = Number(event?.code || 1000);
      if (code === 1000) return;
      const reason = String(event?.reason || "").trim() || `连接关闭(${code})`;
      rejectPendingRequests(reason);
      ElMessage.warning(`WebSocket 断开：${reason}`);
    },
  });
  wsClient.value = client;
  await client.ready;
  wsConnected.value = true;
  return client;
}

function getActiveRequestId() {
  const entries = Array.from(pendingRequests.entries());
  if (entries.length > 0) {
    return entries[entries.length - 1][0];
  }
  return null;
}

function stopGeneration() {
  const currentRequestId = getActiveRequestId();
  if (currentRequestId && wsClient.value && wsClient.value.isOpen()) {
    wsClient.value.send({ type: "cancel", request_id: currentRequestId });
    ElMessage.info(
      isExternalAgentMode.value ? "已发送 Ctrl+C 到外部 Agent" : "已发送停止指令",
    );
    return;
  }
  ElMessage.warning("当前没有可暂停的生成任务");
}

async function doSend() {
  if (!canSend.value) return;

  if (!selectedProjectId.value) {
    ElMessage.warning("请先选择项目");
    return;
  }

  if (isExternalAgentMode.value) {
    if (!externalAgentInfo.value.available) {
      ElMessage.error("未检测到 Codex CLI，无法启动外部 Agent 模式");
      return;
    }
    if (!String(externalAgentInfo.value.workspace_path || "").trim()) {
      ElMessage.warning("当前项目未配置 workspace_path");
      return;
    }
    if (uploadFiles.value.length > 0) {
      ElMessage.warning("外部 Agent 模式暂不支持附件，本次只发送文本内容");
    }
  }

  const text = String(draftText.value || "").trim();
  const files = isExternalAgentMode.value
    ? []
    : uploadFiles.value.map((item) => item.raw).filter(Boolean);
  const imageFiles = files.filter((file) => isImageFile(file));

  const historyRows = toHistoryRows(messages.value, historyLimit.value);
  const imageUrls = uploadFiles.value
    .filter((item) => item.kind === "image")
    .map((item) => item.url)
    .filter(Boolean);
  const attachmentNames = files
    .map((file) => String(file?.name || "").trim())
    .filter(Boolean);

  const readAsBase64 = (f) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(f);
    });
  const base64Images = await Promise.all(imageFiles.map(readAsBase64));

  let docsText = "";
  const docFiles = files.filter((file) => !isImageFile(file));
  if (docFiles.length > 0) {
    for (const file of docFiles) {
      const content = await extractTextFromFile(file);
      if (content) {
        const clipped = clipText(content, docMaxCharsPerFile.value);
        docsText += `\n\n【文档附件：${file.name}】\n${clipped}`;
      }
      if (docsText.length >= docMaxCharsTotal.value) {
        docsText = clipText(docsText, docMaxCharsTotal.value);
        break;
      }
    }
  }

  let userPrompt =
    text ||
    (attachmentNames.length
      ? `我上传了附件：${attachmentNames.join("、")}。请先给我处理建议。`
      : "");
  if (docsText) {
    userPrompt += `${docsText}\n\n请先给简要结论：最多 5 条，每条不超过 40 字。`;
  }

  messages.value.push({
    role: "user",
    content: text || "（发送了附件）",
    images: imageUrls,
    attachments: attachmentNames,
    time: nowText(),
  });
  messages.value.push({
    role: "assistant",
    content: "",
    displayMode: isExternalAgentMode.value ? "terminal" : "",
    terminalLog: [],
    audit: null,
    time: nowText(),
  });

  if (isExternalAgentMode.value) {
    terminalPanelExpanded.value = true;
    appendTerminalPanelLine(`
# ${nowText()} · 新请求`);
    appendTerminalPanelLine(`> ${String(text || userPrompt || '').trim() || '（空输入）'}`);
  }

  const assistantIndex = messages.value.length - 1;
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  chatLoading.value = true;
  resetDraft();
  scrollToBottom();

  try {
    if (isExternalAgentMode.value) {
      await prepareExternalAgentSession({ silent: true });
    }
    const client = await ensureWsClient(selectedProjectId.value);
    const donePromise = new Promise((resolve, reject) => {
      pendingRequests.set(requestId, { resolve, reject, assistantIndex });
    });
    const employeeIds = normalizeStringList(selectedEmployeeIds.value || []);
    const requestPayload = {
      request_id: requestId,
      chat_mode: selectedChatMode.value || "system",
      external_agent_type: "codex_cli",
      external_agent_sandbox_mode:
        projectChatSettings.value.external_agent_sandbox_mode || "workspace-write",
      external_agent_sandbox_mode_explicit: true,
      message: userPrompt,
      employee_ids: employeeIds,
      employee_id: employeeIds.length === 1 ? employeeIds[0] : undefined,
      history: historyRows,
      provider_id: isExternalAgentMode.value
        ? undefined
        : selectedProviderId.value || undefined,
      model_name: isExternalAgentMode.value
        ? undefined
        : selectedModelName.value || undefined,
      temperature: Number(temperature.value),
      max_tokens: Number(chatMaxTokens.value || 512),
      system_prompt: systemPrompt.value || undefined,
      attachment_names: attachmentNames,
      images: base64Images,
      auto_use_tools: singleRoundAnswerOnly.value
        ? false
        : Boolean(
            projectChatSettings.value.auto_use_tools ??
            CHAT_SETTINGS_DEFAULTS.auto_use_tools,
          ),
      tool_priority: normalizeStringList(
        projectChatSettings.value.tool_priority || [],
      ),
      max_tool_calls_per_round: Number(
        projectChatSettings.value.max_tool_calls_per_round ||
          CHAT_SETTINGS_DEFAULTS.max_tool_calls_per_round,
      ),
      max_loop_rounds: Number(
        projectChatSettings.value.max_loop_rounds ||
          CHAT_SETTINGS_DEFAULTS.max_loop_rounds,
      ),
      max_tool_rounds: Number(
        projectChatSettings.value.max_tool_rounds ||
          CHAT_SETTINGS_DEFAULTS.max_tool_rounds,
      ),
      repeated_tool_call_threshold: Number(
        projectChatSettings.value.repeated_tool_call_threshold ||
          CHAT_SETTINGS_DEFAULTS.repeated_tool_call_threshold,
      ),
      tool_only_threshold: Number(
        projectChatSettings.value.tool_only_threshold ||
          CHAT_SETTINGS_DEFAULTS.tool_only_threshold,
      ),
      tool_budget_strategy: String(
        projectChatSettings.value.tool_budget_strategy ||
          CHAT_SETTINGS_DEFAULTS.tool_budget_strategy,
      ),
      history_limit: Number(
        projectChatSettings.value.history_limit ||
          CHAT_SETTINGS_DEFAULTS.history_limit,
      ),
      tool_timeout_sec: Number(
        projectChatSettings.value.tool_timeout_sec ||
          CHAT_SETTINGS_DEFAULTS.tool_timeout_sec,
      ),
      tool_retry_count: Number(
        projectChatSettings.value.tool_retry_count ||
          CHAT_SETTINGS_DEFAULTS.tool_retry_count,
      ),
      allow_shell_tools: Boolean(
        projectChatSettings.value.allow_shell_tools ??
        CHAT_SETTINGS_DEFAULTS.allow_shell_tools,
      ),
      allow_file_write_tools: Boolean(
        projectChatSettings.value.allow_file_write_tools ??
        CHAT_SETTINGS_DEFAULTS.allow_file_write_tools,
      ),
      answer_style: String(
        projectChatSettings.value.answer_style ||
          CHAT_SETTINGS_DEFAULTS.answer_style,
      ),
      prefer_conclusion_first: Boolean(
        projectChatSettings.value.prefer_conclusion_first ??
        CHAT_SETTINGS_DEFAULTS.prefer_conclusion_first,
      ),
    };
    requestPayload.enabled_project_tool_names = [
      ...selectedProjectToolNames.value,
    ];
    client.send(requestPayload);
    await donePromise;
    if (!String(messages.value[assistantIndex]?.content || "").trim()) {
      messages.value[assistantIndex].content = "模型未返回内容。";
    }
  } catch (err) {
    messages.value[assistantIndex].content =
      `请求失败：${err?.message || "未知错误"}`;
    ElMessage.error(err?.message || "对话失败");
  } finally {
    pendingRequests.delete(requestId);
    chatLoading.value = false;
    singleRoundAnswerOnly.value = false;
    scrollToBottom();
  }
}

watch(selectedChatMode, async (value) => {
  if (String(value || "").trim() !== "external_agent") {
    externalAgentWarmupLoading.value = false;
    externalAgentWarmupKey.value = "";
    externalAgentInfo.value = {
      ...externalAgentInfo.value,
      ready: false,
      session_id: "",
    };
    resetTerminalPanel();
    return;
  }
  terminalPanelExpanded.value = true;
  if (selectedProjectId.value) {
    try {
      await prepareExternalAgentSession({ silent: true });
    } catch {
      // ignore; user can retry by sending message
    }
  }
});

watch(selectedProjectId, async (value) => {
  const projectId = String(value || "").trim();
  if (!projectId) {
    rejectPendingRequests("已切换项目，当前请求取消");
    disconnectWs("switch project");
    singleRoundAnswerOnly.value = false;
    chatModes.value = [
      { id: "system", label: "系统对话" },
      { id: "external_agent", label: "外部 Agent" },
    ];
    providers.value = [];
    projectEmployees.value = [];
    externalAgentInfo.value = normalizeExternalAgentInfo({});
    mcpModules.value = normalizeMcpModules({});
    selectedProjectToolNames.value = [];
    selectedEmployeeIds.value = [];
    selectedProviderId.value = "";
    selectedModelName.value = "";
    projectChatSettings.value = { ...CHAT_SETTINGS_DEFAULTS };
    systemPrompt.value = "";
    temperature.value = CHAT_SETTINGS_DEFAULTS.temperature;
    chatMaxTokens.value = CHAT_SETTINGS_DEFAULTS.max_tokens;
    resetTerminalPanel();
    return;
  }
  rejectPendingRequests("已切换项目，当前请求取消");
  disconnectWs("switch project");
  singleRoundAnswerOnly.value = false;
  void stopTerminalMirror().catch(() => {});
  resetTerminalPanel();
  try {
    await fetchProvidersByProject(projectId);
    await fetchChatHistory(projectId);
    if (selectedChatMode.value === "external_agent") {
      await prepareExternalAgentSession({ silent: true });
    }
  } catch (err) {
    chatModes.value = [
      { id: "system", label: "系统对话" },
      { id: "external_agent", label: "外部 Agent" },
    ];
    providers.value = [];
    projectEmployees.value = [];
    externalAgentInfo.value = normalizeExternalAgentInfo({});
    mcpModules.value = normalizeMcpModules({});
    selectedProjectToolNames.value = [];
    selectedEmployeeIds.value = [];
    selectedProviderId.value = "";
    selectedModelName.value = "";
    messages.value = [];
    ElMessage.error(err?.detail || err?.message || "加载模型供应商失败");
  }
});

onMounted(async () => {
  loading.value = true;
  try {
    await Promise.all([fetchSystemConfig(), fetchProjects()]);
    syncProjectFromRoute();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "初始化失败");
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  rejectPendingRequests("页面已关闭");
  disconnectWs("page closed");
});
</script>

<style scoped>
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  z-index: 10;
}

.chat-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.terminal-panel {
  flex-shrink: 0;
  margin: 16px 24px 0;
  border: 1px solid #1f2937;
  border-radius: 14px;
  background: #0b1220;
  color: #d1d5db;
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.18);
}

.terminal-panel.is-collapsed {
  margin-bottom: 0;
}

.terminal-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(15, 23, 42, 0.92);
}

.terminal-panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #e5e7eb;
}

.terminal-panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.terminal-panel-body {
  max-height: 220px;
  overflow: auto;
  padding: 14px;
}

.terminal-panel-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 12px;
  line-height: 1.55;
  color: #d1d5db;
}

.terminal-panel-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.8);
}

.chat-header-left h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.chat-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.settings-dialog-body {
  max-height: 70vh;
  overflow-y: auto;
  padding: 8px 16px;
}

.settings-form {
  flex: 1;
}

.settings-form .el-form-item {
  margin-bottom: 20px;
}

.settings-form :deep(.el-form-item__label) {
  padding-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
}

.label-with-tooltip {
  display: flex;
  align-items: center;
  gap: 4px;
}

.label-icon {
  color: var(--el-text-color-secondary);
  font-size: 14px;
  cursor: help;
  transition: color 0.2s;
}

.label-icon:hover {
  color: var(--el-color-primary);
}

.full-width {
  width: 100%;
}

.mcp-source-tabs :deep(.el-tabs__header) {
  margin: 0 0 8px 0;
}

.mcp-source-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
}

.mcp-scope-select {
  margin-bottom: 8px;
}

.mcp-tool-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.mcp-tool-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.mcp-tool-buttons {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mcp-external-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.mcp-section-tip {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 18px;
}

.mcp-section-tip.compact {
  margin-bottom: 0;
}

.mcp-module-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 4px;
}

.mcp-module-list {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 8px;
  max-height: 220px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mcp-module-item {
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 6px;
  padding: 8px;
  background: var(--el-fill-color-extra-light);
}

.mcp-module-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.mcp-module-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.mcp-module-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mcp-module-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 18px;
  word-break: break-word;
}

.mcp-module-meta {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  line-height: 16px;
  word-break: break-word;
}

.mcp-module-more {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 4px 0;
}

.sidebar-footer {
  margin-top: 16px;
}

.chat-layout {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: calc(100vh - 148px);
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 32px 24px;
  scroll-behavior: smooth;
}

.message-list-inner {
  display: flex;
  flex-direction: column;
  gap: 32px;
  max-width: 840px;
  margin: 0 auto;
}

.message-row {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.message-row.is-user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}

.avatar-user {
  background: var(--el-color-primary);
  font-weight: bold;
}

.avatar-ai {
  background: #10a37f;
  font-weight: bold;
}

.message-content-wrapper {
  max-width: 80%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-row.is-user .message-content-wrapper {
  align-items: flex-end;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.role-name {
  font-weight: 600;
}

.message-bubble {
  padding: 14px 18px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
  line-height: 1.6;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
}

.message-text {
  word-break: break-word;
}

.message-text-terminal {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 13px;
  line-height: 1.5;
}

.message-audit {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
}

.message-audit-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.message-audit-section {
  margin-top: 8px;
}

.message-audit-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}

.message-audit-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.message-audit-text {
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.message-audit-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
}

.message-text :deep(p) {
  margin-top: 0;
  margin-bottom: 0.8em;
}
.message-text :deep(p:last-child) {
  margin-bottom: 0;
}
.message-text :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 13px;
  line-height: 1.5;
}
.message-text :deep(code) {
  background: var(--el-fill-color-dark);
  padding: 3px 6px;
  border-radius: 6px;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 13px;
}
.message-text :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
}

.message-row.is-user .message-bubble {
  background: var(--el-color-primary);
  color: #ffffff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 12px rgba(var(--el-color-primary-rgb), 0.2);
}

.message-row.is-user .message-text :deep(code) {
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}

.message-row.is-ai .message-bubble {
  border-bottom-left-radius: 4px;
  background: #ffffff;
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
}

.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.message-attachments {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
}

.attachment-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.attachment-name {
  font-size: 12px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-image {
  width: 140px;
  height: 140px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
}

.chat-composer {
  flex-shrink: 0;
  padding: 24px;
  background: var(--el-bg-color);
  display: flex;
  justify-content: center;
  border-top: 1px solid var(--el-border-color-lighter);
}

.chat-input-wrapper {
  width: 100%;
  max-width: 840px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 16px;
  background: var(--el-fill-color-blank);
  transition:
    border-color 0.2s,
    box-shadow 0.2s,
    background-color 0.2s;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
}

.chat-input-wrapper.is-focused {
  border-color: var(--el-color-primary);
  box-shadow: 0 4px 16px rgba(var(--el-color-primary-rgb), 0.15);
}

.chat-input-wrapper.is-dragover {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
  border-style: dashed;
}

.upload-preview-area {
  display: flex;
  gap: 12px;
  padding: 12px 16px 0 16px;
  flex-wrap: wrap;
}

.preview-item {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}

.preview-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-doc {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  padding: 4px;
  box-sizing: border-box;
}

.doc-name {
  font-size: 10px;
  margin-top: 2px;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
}

.doc-type {
  font-size: 9px;
  line-height: 1;
  margin-top: 2px;
  padding: 2px 4px;
  border-radius: 8px;
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
}

.remove-mask {
  position: absolute;
  top: 0;
  right: 0;
  width: 20px;
  height: 20px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-bottom-left-radius: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}

.preview-item:hover .remove-mask {
  opacity: 1;
}

.chat-textarea :deep(.el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 12px 16px;
  font-size: 14px;
  resize: none;
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hint-text {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.external-agent-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--el-text-color-regular);
}

.external-agent-support-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.external-agent-support-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  font-size: 12px;
}

.external-agent-support-item code {
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  color: var(--el-text-color-secondary);
  word-break: break-all;
}

.external-agent-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.external-agent-command {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  word-break: break-all;
}

.pause-generation-button {
  border-radius: 999px;
  padding: 8px 14px;
  font-weight: 600;
}
</style>
