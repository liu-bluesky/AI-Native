<template>
  <div v-if="!isSettingsCenterRoute" class="chat-layout" v-loading="loading">
    <div
      class="chat-layout__ambient chat-layout__ambient--left"
      aria-hidden="true"
    />
    <div
      class="chat-layout__ambient chat-layout__ambient--right"
      aria-hidden="true"
    />
    <div class="chat-layout__mesh" aria-hidden="true" />

    <div class="chat-main">
      <div class="chat-shell">
        <aside class="chat-conversation-sidebar">
          <div class="chat-sidebar-brand-panel">
            <div class="chat-sidebar-brand">
              <div class="chat-sidebar-brand__mark">AI</div>
              <div>
                <div class="chat-sidebar-brand__name">AI 对话</div>
                <div class="chat-sidebar-brand__meta">项目会话</div>
              </div>
            </div>
            <el-button
              class="chat-page-settings-button"
              @click="openSettingsCenter('chat')"
              :icon="Setting"
              circle
              ref="chatSettingsButtonRef"
            />
          </div>

          <div class="chat-sidebar-project-card">
            <div class="chat-sidebar-card__label">项目</div>
            <el-dropdown
              class="chat-project-dropdown"
              trigger="click"
              placement="bottom-start"
              @command="handleProjectCommand"
            >
              <button
                type="button"
                class="chat-project-switcher"
                :class="{ 'is-empty': !selectedProjectId }"
                ref="projectSwitcherRef"
              >
                <span class="chat-project-switcher__name">
                  {{ currentProjectLabel }}
                </span>
              </button>
              <template #dropdown>
                <el-dropdown-menu
                  class="chat-project-switcher-menu"
                  :style="projectSwitcherMenuStyle"
                >
                  <el-dropdown-item v-if="!projects.length" disabled>
                    <div class="chat-project-option chat-project-option--empty">
                      <span class="chat-project-option__name">暂无项目</span>
                    </div>
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-for="item in projects"
                    :key="item.id"
                    :command="item.id"
                  >
                    <div class="chat-project-option">
                      <span class="chat-project-option__name">{{
                        item.name
                      }}</span>
                    </div>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <div class="chat-conversation-sidebar__actions">
            <el-button
              class="chat-new-conversation-button"
              @click="handleCreateNewConversation"
              :loading="creatingChatSession"
              :icon="DocumentCopy"
            >
              新对话
            </el-button>
            <el-button
              text
              class="chat-clear-current-button"
              @click="clearMessages"
              :disabled="chatLoading || !currentChatSessionId"
            >
              清空对话
            </el-button>
          </div>

          <div class="chat-session-panel">
            <div class="chat-session-panel__head">
              <div class="chat-session-panel__title">最近对话</div>
            </div>

            <div class="chat-session-strip">
              <div
                v-if="groupedChatSessions.length"
                class="chat-session-groups"
              >
                <div
                  v-for="group in groupedChatSessions"
                  :key="group.label"
                  class="chat-session-group"
                >
                  <div class="chat-session-group__title">{{ group.label }}</div>
                  <div class="chat-session-list">
                    <button
                      v-for="session in group.items"
                      :key="session.id"
                      type="button"
                      class="chat-session-chip"
                      :class="{
                        'is-active': currentChatSessionId === session.id,
                      }"
                      @click="selectChatSession(session.id)"
                    >
                      <div class="chat-session-chip__row">
                        <span class="chat-session-chip__title">
                          {{ session.title }}
                        </span>
                        <el-button
                          text
                          size="small"
                          class="chat-session-chip__delete"
                          :icon="Delete"
                          :loading="deletingChatSessionId === session.id"
                          @click.stop="deleteChatSession(session)"
                        />
                      </div>
                      <span class="chat-session-chip__meta">
                        {{ formatChatSessionMeta(session) }}
                      </span>
                    </button>
                  </div>
                </div>
              </div>
              <div v-else class="chat-session-empty">暂无历史会话</div>
            </div>
          </div>

          <div class="chat-sidebar-footer">
            <div class="chat-sidebar-user">
              <div class="chat-sidebar-user__avatar">
                {{ currentUsernameInitial }}
              </div>
              <div class="chat-sidebar-user__meta">
                <div class="chat-sidebar-user__name">{{ currentUsername }}</div>
                <div class="chat-sidebar-user__role">当前账号</div>
              </div>
              <el-button
                text
                class="chat-sidebar-user__logout"
                @click="logoutFromChat"
                >退出</el-button
              >
            </div>
          </div>
        </aside>

        <div class="chat-stage">
          <div class="chat-context-bar">
            <div class="chat-context-bar__surface" ref="chatContextBarRef">
              <div class="chat-context-bar__copy">
                <div class="chat-context-bar__eyebrow">AI Operating System</div>
                <div class="chat-context-bar__title">
                  {{ hasSelectedProject ? currentProjectLabel : "AI 对话" }}
                </div>
                <p class="chat-context-bar__summary">
                  {{
                    hasSelectedProject
                      ? "在同一项目里继续推进前端、后端、数据库更新，以及对话、规则与资产。"
                      : "先建立判断，再展开步骤与执行。"
                  }}
                </p>
                <div class="chat-context-bar__meta">
                  <span>{{
                    hasSelectedProject ? currentProjectLabel : "通用对话"
                  }}</span>
                  <span>{{ chatModeLabel }}</span>
                  <span>{{ currentModelSummary }}</span>
                  <span>{{ chatHeaderStatusText }}</span>
                </div>
              </div>
              <div class="chat-context-bar__actions">
                <el-button
                  size="small"
                  class="chat-context-bar__action-button chat-context-bar__action-button--guide"
                  @click="startChatTour(true)"
                  ref="chatGuideButtonRef"
                >
                  使用引导
                </el-button>
                <el-button
                  v-if="hasSelectedProject"
                  size="small"
                  plain
                  class="chat-context-bar__action-button"
                  @click="openCurrentMaterialLibrary"
                >
                  素材库
                </el-button>
                <el-button
                  size="small"
                  plain
                  class="chat-context-bar__action-button"
                  @click="openUnifiedMcpDialog"
                >
                  MCP 接入
                </el-button>
                <el-button
                  size="small"
                  plain
                  class="chat-context-bar__action-button"
                  @click="openSkillResourceCenter"
                >
                  技能资源
                </el-button>
              </div>
            </div>
          </div>
          <div class="chat-messages-shell">
            <div
              class="chat-messages"
              ref="messagesContainer"
              @click="handleMessageAreaClick"
            >
              <div class="message-list-inner">
                <div v-if="!messages.length" class="chat-empty-state">
                  <div class="chat-empty-state__hero">
                    <div class="chat-empty-badge">
                      {{
                        hasSelectedProject
                          ? "Project Context Ready"
                          : hasAccessibleProjects
                            ? "General Chat"
                            : "Access Pending"
                      }}
                    </div>
                    <div class="chat-empty-title">{{ emptyStateTitle }}</div>
                    <div class="chat-empty-text">{{ emptyStateText }}</div>
                  </div>
                  <div v-if="starterPrompts.length" class="chat-empty-actions">
                    <button
                      v-for="prompt in starterPrompts"
                      :key="prompt"
                      type="button"
                      class="chat-empty-action"
                      @click="applyStarterPrompt(prompt)"
                    >
                      {{ prompt }}
                    </button>
                  </div>
                </div>
                <template v-else>
                  <div
                    v-if="chatHistoryHasMore || chatHistoryLoadingMore"
                    class="chat-history-loader"
                  >
                    <el-button
                      text
                      class="chat-history-loader__button"
                      :loading="chatHistoryLoadingMore"
                      @click="loadOlderMessages"
                    >
                      {{
                        chatHistoryLoadingMore
                          ? "正在加载更早消息..."
                          : "加载更早消息"
                      }}
                    </el-button>
                  </div>
                  <div
                    v-for="(item, idx) in messages"
                    :key="idx"
                    :class="[
                      'message-row',
                      String(item?.id || '').trim() === highlightedMessageId
                        ? 'is-highlighted'
                        : '',
                      item.role === 'user' ? 'is-user' : 'is-ai',
                    ]"
                    :data-message-id="
                      String(item?.id || '').trim() || undefined
                    "
                  >
                    <div class="message-avatar">
                      <el-avatar
                        :size="36"
                        :class="
                          item.role === 'user' ? 'avatar-user' : 'avatar-ai'
                        "
                      >
                        {{ avatarLabel(item) }}
                      </el-avatar>
                    </div>
                    <div class="message-content-wrapper">
                      <div class="message-meta">
                        <span class="role-name">{{
                          messageRoleName(item)
                        }}</span>
                        <span
                          v-if="item.time || item.created_at"
                          class="message-time"
                          >{{
                            formatRelativeDateTime(item.time || item.created_at)
                          }}</span
                        >
                      </div>
                      <div
                        :class="[
                          'message-bubble',
                          isInlineEditingMessage(idx)
                            ? 'message-bubble--editing'
                            : '',
                        ]"
                      >
                        <template v-if="isInlineEditingMessage(idx)">
                          <div
                            class="message-inline-editor"
                            :data-inline-editor-id="inlineEditingMessageId"
                          >
                            <el-input
                              v-model="inlineEditingDraft"
                              class="message-inline-editor__input"
                              type="textarea"
                              resize="none"
                              :autosize="{ minRows: 4, maxRows: 10 }"
                              placeholder="继续润色这条消息…"
                              @keydown.stop="
                                handleInlineMessageEditKeydown($event)
                              "
                            />
                            <div class="message-inline-editor__footer">
                              <div class="message-inline-editor__hint">
                                <span class="message-inline-editor__hint-label">
                                  快捷键
                                </span>
                                <span class="message-inline-editor__shortcut">
                                  <kbd>Cmd/Ctrl</kbd>
                                  <kbd>Enter</kbd>
                                  <span>重新生成</span>
                                </span>
                                <span class="message-inline-editor__shortcut">
                                  <kbd>Esc</kbd>
                                  <span>取消</span>
                                </span>
                              </div>
                              <div class="message-inline-editor__actions">
                                <el-button
                                  text
                                  class="message-inline-editor__button message-inline-editor__button--ghost"
                                  :disabled="inlineEditingBusy"
                                  @click="cancelInlineMessageEdit"
                                >
                                  取消
                                </el-button>
                                <el-button
                                  plain
                                  class="message-inline-editor__button message-inline-editor__button--soft"
                                  :disabled="inlineEditingBusy"
                                  @click="applyInlineMessageEditToComposer"
                                >
                                  应用到输入框
                                </el-button>
                                <el-button
                                  type="primary"
                                  class="message-inline-editor__button message-inline-editor__button--primary"
                                  :loading="inlineEditingBusy"
                                  @click="submitInlineMessageEditAndReplay"
                                >
                                  保存并重新生成
                                </el-button>
                              </div>
                            </div>
                          </div>
                        </template>
                        <template v-else-if="item.displayMode === 'terminal'">
                          <div
                            v-if="terminalLogLines(item).length"
                            class="message-process"
                          >
                            <button
                              type="button"
                              class="message-process-toggle"
                              @click="
                                item.processExpanded = !item.processExpanded
                              "
                            >
                              <span>
                                思考过程
                                <span class="message-process-count">
                                  {{ terminalLogLines(item).length }} 条
                                </span>
                              </span>
                              <span class="message-process-meta">
                                {{ item.processExpanded ? "收起" : "展开" }}
                              </span>
                            </button>
                            <pre
                              v-show="item.processExpanded"
                              class="message-text message-text-terminal message-process-pre"
                              >{{ formatTerminalLogs(item) }}</pre
                            >
                          </div>
                          <div
                            class="message-text"
                            v-html="
                              formatContent(item.content) ||
                              (chatLoading && idx === messages.length - 1
                                ? '思考中...'
                                : '')
                            "
                          ></div>
                        </template>
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
                        <div
                          v-if="extractImages(item).length"
                          class="message-images"
                        >
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
                          v-if="extractVideos(item).length"
                          class="message-videos"
                        >
                          <video
                            v-for="(video, videoIndex) in extractVideos(item)"
                            :key="`video-${idx}-${videoIndex}`"
                            :src="video"
                            class="preview-video"
                            controls
                            preload="metadata"
                            playsinline
                          />
                        </div>
                        <div
                          v-if="extractAttachments(item).length"
                          class="message-attachments"
                        >
                          <div
                            v-for="(
                              attachment, attachmentIndex
                            ) in extractAttachments(item)"
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
                            <span class="attachment-name">{{
                              attachment.name
                            }}</span>
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
                            <template
                              v-if="item.audit.after_diff_summary?.enabled"
                            >
                              <div class="message-audit-text">
                                改动文件数：{{
                                  item.audit.after_diff_summary
                                    .changed_file_count
                                }}
                              </div>
                              <pre
                                v-if="item.audit.after_diff_summary.diff_stat"
                                class="message-audit-pre"
                                >{{
                                  item.audit.after_diff_summary.diff_stat
                                }}</pre
                              >
                              <pre
                                v-else-if="
                                  item.audit.after_diff_summary.status_lines
                                    ?.length
                                "
                                class="message-audit-pre"
                                >{{
                                  item.audit.after_diff_summary.status_lines.join(
                                    "\n",
                                  )
                                }}</pre
                              >
                              <div v-else class="message-audit-text">
                                暂无 Git 变更
                              </div>
                            </template>
                            <div v-else class="message-audit-text">
                              {{
                                item.audit.after_diff_summary?.reason ||
                                "当前工作区不是 Git 仓库"
                              }}
                            </div>
                          </div>
                          <div
                            v-if="
                              item.audit.file_review_status &&
                              item.audit.file_review_status !== 'not_required'
                            "
                            class="message-audit-section"
                          >
                            <div class="message-audit-label">变更审查</div>
                            <div class="message-audit-tags">
                              <el-tag
                                size="small"
                                :type="
                                  getFileReviewStatusMeta(
                                    item.audit.file_review_status,
                                  ).type
                                "
                                effect="plain"
                              >
                                {{
                                  getFileReviewStatusMeta(
                                    item.audit.file_review_status,
                                  ).label
                                }}
                              </el-tag>
                            </div>
                            <div class="message-audit-text">
                              {{
                                getFileReviewStatusMeta(
                                  item.audit.file_review_status,
                                ).text
                              }}
                            </div>
                          </div>
                        </div>
                        <div
                          v-if="
                            item.role !== 'user' && getEmployeeDraftCard(item)
                          "
                          class="message-employee-draft"
                        >
                          <div class="message-employee-draft__head">
                            <div>
                              <div class="message-employee-draft__eyebrow">
                                AI 员工草稿
                              </div>
                              <div class="message-employee-draft__title">
                                {{
                                  getEmployeeDraftCard(item).name ||
                                  "未命名员工"
                                }}
                              </div>
                            </div>
                            <div class="message-employee-draft__pills">
                              <span class="employee-draft-pill">
                                技能
                                {{
                                  getEmployeeDraftCard(item).matched_skill_count
                                }}
                              </span>
                              <span class="employee-draft-pill">
                                规则
                                {{
                                  getEmployeeDraftCard(item).matched_rule_count
                                }}
                              </span>
                            </div>
                          </div>
                          <div
                            v-if="getEmployeeDraftCard(item).description"
                            class="message-employee-draft__desc"
                          >
                            {{ getEmployeeDraftCard(item).description }}
                          </div>
                          <div class="message-employee-draft__meta">
                            <div class="message-employee-draft__meta-item">
                              <span class="meta-label">核心目标</span>
                              <span class="meta-value">
                                {{ getEmployeeDraftCard(item).goal || "-" }}
                              </span>
                            </div>
                            <div class="message-employee-draft__meta-item">
                              <span class="meta-label">语调 / 风格</span>
                              <span class="meta-value">
                                {{ getEmployeeDraftCard(item).tone || "-" }} /
                                {{
                                  getEmployeeDraftCard(item).verbosity || "-"
                                }}
                              </span>
                            </div>
                          </div>
                          <div
                            v-if="
                              getEmployeeDraftCard(item).style_hints?.length
                            "
                            class="message-employee-draft__tags"
                          >
                            <el-tag
                              v-for="hint in getEmployeeDraftCard(item)
                                .style_hints"
                              :key="`style-${hint}`"
                              size="small"
                              effect="plain"
                            >
                              {{ hint }}
                            </el-tag>
                          </div>
                          <div
                            v-if="
                              getEmployeeDraftCard(item).default_workflow
                                ?.length
                            "
                            class="message-employee-draft__workflow"
                          >
                            <div class="meta-label">默认工作流</div>
                            <ol class="employee-draft-workflow-list">
                              <li
                                v-for="step in getEmployeeDraftCard(item)
                                  .default_workflow"
                                :key="`workflow-${step}`"
                              >
                                {{ step }}
                              </li>
                            </ol>
                          </div>
                          <div class="message-employee-draft__actions">
                            <el-button
                              type="primary"
                              :loading="
                                employeeDraftCreatingKey ===
                                getEmployeeDraftKey(item)
                              "
                              :disabled="Boolean(item.employeeDraftCreatedName)"
                              @click="createEmployeeFromDraft(item)"
                            >
                              手动创建员工
                            </el-button>
                            <span
                              v-if="item.employeeDraftCreatedName"
                              class="message-employee-draft__success"
                            >
                              已创建：{{ item.employeeDraftCreatedName }}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div
                        v-if="
                          !isInlineEditingMessage(idx) &&
                          getMessageActions(item, idx).length
                        "
                        class="message-actions"
                      >
                        <el-tooltip
                          v-for="action in getMessageActions(item, idx)"
                          :key="`${idx}-${action.key}`"
                          :content="action.tooltip"
                          placement="top"
                        >
                          <el-button
                            text
                            size="small"
                            class="message-action-button"
                            :icon="action.icon"
                            circle
                            @click="handleMessageAction(item, idx, action.key)"
                          />
                        </el-tooltip>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <el-dialog
            v-model="terminalApprovalDialogVisible"
            title="等待操作确认"
            width="min(560px, calc(100vw - 32px))"
            :close-on-click-modal="false"
            :close-on-press-escape="false"
            :show-close="false"
            class="terminal-approval-dialog"
          >
            <div v-if="terminalApprovalPrompt" class="terminal-approval-card">
              <div class="terminal-approval-card__title">
                {{ terminalApprovalPrompt.title }}
              </div>
              <div
                v-if="terminalApprovalPrompt.description"
                class="terminal-approval-card__desc"
              >
                {{ terminalApprovalPrompt.description }}
              </div>
              <pre
                v-if="terminalApprovalPrompt.message"
                class="terminal-approval-card__message"
                >{{ terminalApprovalPrompt.message }}</pre
              >
            </div>
            <template #footer>
              <div class="terminal-approval-dialog__footer">
                <el-button
                  type="danger"
                  plain
                  @click="sendTerminalApprovalChoice('3')"
                >
                  取消
                </el-button>
                <el-button @click="sendTerminalApprovalChoice('2')">
                  本会话批准
                </el-button>
                <el-button
                  type="primary"
                  @click="sendTerminalApprovalChoice('1')"
                >
                  批准一次
                </el-button>
              </div>
            </template>
          </el-dialog>

          <!-- Composer Area -->
          <div class="chat-composer">
            <div class="chat-composer-panel">
              <div
                class="chat-input-wrapper"
                :class="{
                  'is-focused': inputFocused,
                  'is-dragover': isDragging,
                }"
                ref="chatComposerRef"
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
                      <span class="doc-type">{{
                        formatFileType(file.name)
                      }}</span>
                    </div>
                    <div class="remove-mask" @click="removeFile(idx)">
                      <el-icon><Delete /></el-icon>
                    </div>
                  </div>
                </div>

                <el-input
                  v-model="draftText"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 8 }"
                  :placeholder="composerPlaceholder"
                  resize="none"
                  :disabled="isComposerDisabled"
                  @focus="inputFocused = true"
                  @blur="handleEditorBlur"
                  @keydown="handleEditorKeydown"
                  @paste="handleEditorPaste"
                  @compositionstart="handleEditorCompositionStart"
                  @compositionend="handleEditorCompositionEnd"
                  class="chat-textarea"
                />

                <ComposerAssistBar
                  :actions="composerAssistActions"
                  :active-action-id="activeComposerAssist"
                  @toggle="toggleComposerAssist"
                />

                <div class="input-footer">
                  <div class="footer-left">
                    <el-select
                      v-if="!isExternalAgentMode"
                      v-model="selectedModelOptionValue"
                      class="chat-model-select"
                      popper-class="chat-model-select-dropdown"
                      size="small"
                      filterable
                      placeholder="选择模型"
                      :disabled="chatLoading || !providerModelGroups.length"
                    >
                      <el-option-group
                        v-for="group in providerModelGroups"
                        :key="group.providerId"
                        :label="group.label"
                      >
                        <el-option
                          v-for="option in group.options"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        >
                          <div class="chat-model-option">
                            <div class="chat-model-option__main">
                              <span class="chat-model-option__name">{{
                                option.modelName
                              }}</span>
                              <span class="chat-model-option__provider">
                                {{ option.providerLabel }}
                              </span>
                            </div>
                            <span class="chat-model-option__type">
                              {{ option.modelTypeLabel }}
                            </span>
                          </div>
                        </el-option>
                      </el-option-group>
                    </el-select>
                    <div v-else class="chat-model-pill">
                      {{ externalAgentDisplayLabel }}
                    </div>
                    <el-upload
                      action="#"
                      :auto-upload="false"
                      :show-file-list="false"
                      accept="image/*"
                      :multiple="true"
                      :on-change="handleFileChange"
                      :disabled="
                        chatLoading || isExternalAgentMode || !selectedProjectId
                      "
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
                      :disabled="
                        chatLoading || isExternalAgentMode || !selectedProjectId
                      "
                    >
                      <el-tooltip content="添加文档" placement="top">
                        <el-button text circle
                          ><el-icon><Document /></el-icon
                        ></el-button>
                      </el-tooltip>
                    </el-upload>
                    <el-popover
                      v-if="shouldShowMediaParameterTrigger"
                      v-model:visible="mediaParameterPopoverVisible"
                      trigger="click"
                      placement="top-start"
                      :width="currentModelParameterMode === 'image' ? 460 : 420"
                      :teleported="false"
                    >
                      <template #reference>
                        <el-button
                          class="chat-media-parameter-trigger"
                          text
                          :disabled="chatLoading"
                        >
                          <el-icon class="chat-media-parameter-trigger__icon">
                            <component :is="currentMediaParameterTriggerIcon" />
                          </el-icon>
                          <span class="chat-media-parameter-trigger__label">
                            {{ currentMediaParameterTriggerLabel }}
                          </span>
                        </el-button>
                      </template>

                      <div class="chat-media-parameter-panel">
                        <div class="chat-media-parameter-panel__head">
                          <div class="chat-media-parameter-panel__eyebrow">
                            {{ currentMediaParameterTriggerLabel }}
                          </div>
                          <div class="chat-media-parameter-panel__title">
                            {{ currentMediaParameterPanelTitle }}
                          </div>
                          <div class="chat-media-parameter-panel__summary">
                            {{ currentModelSummary }}
                          </div>
                        </div>

                        <div class="chat-media-parameter-panel__sections">
                          <section
                            v-for="section in currentModelParameterSections"
                            :key="`popover-${section.key}`"
                            class="chat-media-parameter-section"
                          >
                            <div class="chat-media-parameter-section__label">
                              {{ section.label }}
                            </div>
                            <div
                              v-if="section.helper"
                              class="chat-media-parameter-section__helper"
                            >
                              {{ section.helper }}
                            </div>
                            <div
                              class="chat-media-parameter-section__options"
                              :class="{
                                'is-aspect': section.key === 'image_aspect_ratio' || section.key === 'video_aspect_ratio',
                                'is-resolution': section.key === 'image_resolution',
                              }"
                            >
                              <button
                                v-for="option in section.options"
                                :key="`${section.key}-${option.id}`"
                                type="button"
                                class="chat-media-parameter-option"
                                :class="{
                                  'is-active': option.value === section.modelValue,
                                  'is-resolution': section.key === 'image_resolution',
                                }"
                                @click="setCurrentModelParameterValue(section.key, option.value)"
                              >
                                <span class="chat-media-parameter-option__label">
                                  {{ option.label }}
                                </span>
                              </button>
                            </div>
                          </section>
                        </div>

                        <section
                          v-if="shouldShowImageFourViewsOption"
                          class="chat-media-parameter-section chat-media-parameter-section--toggle"
                        >
                          <div class="chat-media-parameter-section__label">
                            四视图
                          </div>
                          <div class="chat-media-parameter-section__helper">
                            勾选后会自动要求输出同一角色的正面、背面、左侧、右侧四视图。
                          </div>
                          <button
                            type="button"
                            class="chat-media-toggle-card"
                            :class="{
                              'is-active': imageGenerateFourViewsEnabled,
                            }"
                            @click="toggleImageGenerateFourViews"
                          >
                            <div class="chat-media-toggle-card__content">
                              <span class="chat-media-toggle-card__title">
                                自动生成四视图
                              </span>
                              <span class="chat-media-toggle-card__description">
                                适合角色设定图和素材前置统一。
                              </span>
                            </div>
                            <span
                              class="chat-media-toggle-card__indicator"
                              :class="{
                                'is-active': imageGenerateFourViewsEnabled,
                              }"
                            >
                              {{ imageGenerateFourViewsEnabled ? "已开启" : "未开启" }}
                            </span>
                          </button>
                        </section>
                      </div>
                    </el-popover>
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
                      class="send-message-button"
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
      </div>
    </div>
  </div>

  <UnifiedMcpAccessDialog
    v-model="unifiedMcpDialogVisible"
    title="统一 MCP 接入"
    :project-id="selectedProjectId"
    :project-label="currentProjectLabel"
  />

  <el-dialog
    v-model="codePreviewVisible"
    :title="codePreviewTitle"
    width="min(1200px, calc(100vw - 32px))"
    destroy-on-close
    class="code-preview-dialog"
  >
    <div class="code-preview-shell">
      <div v-if="codePreviewError" class="code-preview-error">
        {{ codePreviewError }}
      </div>
      <iframe
        v-else
        class="code-preview-frame"
        :srcdoc="codePreviewSrcdoc"
        sandbox="allow-scripts allow-forms allow-modals"
        referrerpolicy="no-referrer"
      />
    </div>
  </el-dialog>

  <ProjectEmployeeDraftCreateDialog
    v-model="employeeDraftDialogVisible"
    :loading="employeeDraftDialogLoading"
    :submitting="employeeCreateSubmitting"
    :payload="employeeDraftDialogPayload"
    :matched-skill-labels="employeeDraftDialogMatchedSkillLabels"
    :matched-rule-labels="employeeDraftDialogMatchedRuleLabels"
    :rule-draft-labels="employeeDraftDialogRuleDraftLabels"
    :auto-rule-generation-enabled="employeeDraftAutoRuleGenerationEnabled"
    :auto-rule-generation-max-count="employeeDraftAutoRuleGenerationMaxCount"
    :auto-rule-source-labels="employeeDraftAutoRuleSourceLabels"
    :can-add-to-project="Boolean(String(selectedProjectId || '').trim())"
    @confirm="confirmEmployeeDraftCreation"
    @close="resetEmployeeDraftDialogState"
  />

  <ProjectMaterialSaveDialog
    v-model="materialDialogVisible"
    :loading="materialDialogSaving"
    :project-label="currentProjectLabel"
    :message-role-label="
      materialDialogPayload
        ? messageRoleName(materialDialogPayload.message)
        : ''
    "
    :image-count="
      materialDialogPayload
        ? extractImages(materialDialogPayload.message).length
        : 0
    "
    :source-chat-session-id="
      materialDialogPayload?.source_chat_session_id || ''
    "
    :initial-form="materialDialogPayload?.form || {}"
    :asset-type-options="MATERIAL_ASSET_TYPE_OPTIONS"
    :mime-type-options="MATERIAL_MIME_TYPE_OPTIONS"
    @submit="submitMaterialDialog"
    @close="resetMaterialDialogState"
  />

  <el-dialog
    v-model="skillResourceDialogVisible"
    title="技能资源"
    width="min(880px, calc(100vw - 32px))"
    destroy-on-close
    class="skill-resource-dialog"
  >
    <div class="skill-resource-dialog__body">
      <div class="skill-resource-dialog__hint">
        对话里发现当前项目缺技能时，可以先选好本地下载目录，再打开下面的网站自己下载技能包或模板。保存后，当前对话会把这个目录当作优先参考的本地技能来源，但不会自动绑定到系统。
      </div>

      <div class="skill-resource-dialog__directory">
        <div class="skill-resource-dialog__directory-head">
          <div class="skill-resource-dialog__section-title">本地技能目录</div>
          <div class="skill-resource-dialog__directory-actions">
            <el-button
              size="small"
              @click="useWorkspaceAsSkillDirectory"
              :disabled="!workspacePathResolved"
            >
              使用当前工作区
            </el-button>
            <el-button
              size="small"
              @click="pickSkillResourceDirectory"
              :loading="skillResourceDirectoryPicking"
            >
              选择目录
            </el-button>
            <el-button
              size="small"
              text
              @click="copySkillResourceDirectory"
              :disabled="!skillResourceDirectoryResolved"
            >
              复制路径
            </el-button>
          </div>
        </div>
        <div
          class="skill-resource-dialog__directory-value"
          :class="{ 'is-empty': !skillResourceDirectoryResolved }"
        >
          {{
            skillResourceDirectoryResolved ||
            "还没有选择目录。建议先选择本地技能下载目录。"
          }}
        </div>
        <div class="skill-resource-dialog__directory-meta">
          优先使用当前项目工作区，也可以单独指定一个技能下载目录。
        </div>
      </div>

      <div class="skill-resource-dialog__section-title">推荐网站</div>
      <div class="skill-resource-search">
        <el-input
          v-model="skillResourceSearchQuery"
          placeholder="搜索技能资源，例如 Java 开发、界面设计、浏览器调试"
          clearable
          @keyup.enter="searchSkillResources"
        >
          <template #append>
            <el-button
              :loading="skillResourceSearchLoading"
              @click="searchSkillResources"
            >
              搜索
            </el-button>
          </template>
        </el-input>
        <div class="skill-resource-search__meta">
          <span>支持中文搜索，结果会下载到下方选择的本地技能目录。</span>
          <el-button
            v-if="skillResourceSearchQuery || skillResourceSearchResults.length"
            text
            size="small"
            @click="resetSkillResourceSearch"
          >
            清空结果
          </el-button>
        </div>
        <div
          v-if="skillResourceSearchResolvedQueries.length > 1"
          class="skill-resource-search__expanded"
        >
          已自动扩展英文关键词：
          {{ skillResourceSearchResolvedQueries.join(" / ") }}
        </div>
      </div>

      <div
        v-if="skillResourceSearchResults.length"
        class="skill-resource-site-list skill-resource-site-list--search"
      >
        <article
          v-for="site in skillResourceSearchResults"
          :key="site.id || site.slug"
          class="skill-resource-site-card"
        >
          <div class="skill-resource-site-card__head">
            <div class="skill-resource-site-card__title-wrap">
              <div class="skill-resource-site-card__title">
                {{ site.title }}
              </div>
            </div>
            <el-tag
              v-if="site.latestVersionLabel"
              size="small"
              effect="plain"
              type="success"
            >
              {{ site.latestVersionLabel }}
            </el-tag>
          </div>
          <div v-if="site.description" class="skill-resource-site-card__desc">
            {{ site.description }}
          </div>
          <div
            v-if="site.localizedDescription"
            class="skill-resource-site-card__desc skill-resource-site-card__desc--localized"
          >
            {{ site.localizedDescription }}
          </div>
          <div class="skill-resource-site-card__url">
            {{ site.url }}
          </div>
          <div class="skill-resource-site-card__actions">
            <el-link :href="site.url" target="_blank" rel="noopener noreferrer">
              打开网站
            </el-link>
            <el-button
              text
              size="small"
              type="success"
              :loading="skillResourceInstallingSlug === site.slug"
              :disabled="!site.canInstall"
              @click="installSkillResource(site)"
            >
              下载到本地技能目录
            </el-button>
          </div>
        </article>
      </div>
      <el-empty
        v-else-if="skillResourceSearchQuery && !skillResourceSearchLoading"
        description="没有找到匹配的技能资源"
        :image-size="56"
      />
      <div
        v-if="
          skillResourceSearchQuery &&
          !skillResourceSearchLoading &&
          !skillResourceSearchResults.length &&
          skillResourceSearchResolvedQueries.length > 1
        "
        class="skill-resource-search__expanded skill-resource-search__expanded--empty"
      >
        已尝试关键词：{{ skillResourceSearchResolvedQueries.join(" / ") }}
      </div>

      <div v-if="skillResourceSites.length" class="skill-resource-site-list">
        <article
          v-for="site in skillResourceSites"
          :key="site.id"
          class="skill-resource-site-card"
        >
          <div class="skill-resource-site-card__head">
            <div class="skill-resource-site-card__title">{{ site.title }}</div>
            <div class="skill-resource-site-card__badge">推荐</div>
          </div>
          <div v-if="site.description" class="skill-resource-site-card__desc">
            {{ site.description }}
          </div>
          <div class="skill-resource-site-card__url">{{ site.url }}</div>
          <div class="skill-resource-site-card__actions">
            <el-link :href="site.url" target="_blank" rel="noopener noreferrer">
              打开网站
            </el-link>
            <el-button text size="small" @click="copySkillResourceSite(site)">
              复制地址
            </el-button>
          </div>
        </article>
      </div>
      <el-empty v-else description="当前还没有配置技能网站" :image-size="56" />
    </div>
  </el-dialog>

  <div
    v-if="isSettingsCenterRoute"
    class="settings-center-page"
    v-loading="loading"
  >
    <div class="settings-center-shell">
      <aside class="settings-center-sidebar" ref="settingsSidebarRef">
        <div class="settings-center-sidebar-card">
          <div class="settings-center-brand-panel">
            <div class="settings-center-brand">
              <div class="settings-center-brand__mark">AI</div>
              <div>
                <div class="settings-center-brand__name">设置中心</div>
                <div class="settings-center-brand__meta">对话与平台入口</div>
              </div>
            </div>
            <el-button
              text
              class="settings-center-close-button"
              @click="closeSettingsCenter"
              >关闭</el-button
            >
          </div>

          <div class="settings-center-nav-group">
            <div class="settings-center-nav-group__title">当前对话</div>
            <div class="settings-center-sidebar__nav">
              <button
                v-for="item in settingsInternalItems"
                :key="item.id"
                type="button"
                class="settings-center-nav-item"
                :class="{ 'is-active': activeSettingsPanel === item.id }"
                @click="openSettingsCenter(item.id)"
              >
                <span class="settings-center-nav-item__row">
                  <span class="settings-center-nav-item__label">{{
                    item.label
                  }}</span>
                </span>
                <span v-if="item.desc" class="settings-center-nav-item__desc">
                  {{ item.desc }}
                </span>
              </button>
            </div>
          </div>

          <div class="settings-center-nav-group">
            <div class="settings-center-nav-group__title">平台入口</div>
            <div class="settings-center-sidebar__nav">
              <button
                v-for="item in settingsRouteItems"
                :key="item.id"
                type="button"
                class="settings-center-nav-item"
                :class="{ 'is-active': activeSettingsPanel === item.id }"
                @click="openSettingsCenter(item.id)"
              >
                <span class="settings-center-nav-item__row">
                  <span class="settings-center-nav-item__label">{{
                    item.label
                  }}</span>
                </span>
                <span v-if="item.desc" class="settings-center-nav-item__desc">
                  {{ item.desc }}
                </span>
              </button>
            </div>
          </div>

          <div class="settings-center-account">
            <div class="settings-center-account__avatar">
              {{ currentUsernameInitial }}
            </div>
            <div class="settings-center-account__meta">
              <div class="settings-center-account__name">
                {{ currentUsername }}
              </div>
              <div class="settings-center-account__role">当前账号</div>
            </div>
            <el-button
              text
              class="settings-center-account__logout"
              @click="logoutFromChat"
              >退出</el-button
            >
          </div>
        </div>
      </aside>

      <section class="settings-center-stage">
        <div class="settings-center-context-bar" ref="settingsContextBarRef">
          <div class="settings-center-context-bar__copy">
            <div class="settings-center-context-bar__title">
              {{ activeSettingsPanelItem?.label || "设置" }}
            </div>
            <div
              v-if="activeSettingsPanelItem?.desc"
              class="settings-center-context-bar__desc"
            >
              {{ activeSettingsPanelItem.desc }}
            </div>
            <div class="settings-center-context-bar__meta">
              <span>项目：{{ currentProjectLabel }}</span>
              <span>模式：系统对话</span>
              <span>
                面板：{{
                  activeSettingsPanelItem?.kind === "route"
                    ? "平台页面"
                    : "对话配置"
                }}
              </span>
            </div>
          </div>
          <div class="settings-center-context-bar__actions">
            <el-button
              type="primary"
              plain
              @click="startSettingsTour(true)"
              ref="settingsGuideButtonRef"
            >
              菜单导览
            </el-button>
          </div>
        </div>

        <div
          v-if="activeSettingsPanel === 'chat'"
          class="settings-center-stage__body settings-center-stage__body--chat"
        >
          <div class="settings-chat-layout">
            <aside class="settings-chat-sidebar">
              <div
                class="settings-chat-sidebar-card settings-chat-sidebar-card--hero"
              >
                <div class="settings-chat-sidebar-card__eyebrow">
                  Conversation Control
                </div>
                <div class="settings-chat-sidebar-card__title">
                  把当前回答路径收束在同一套上下文里。
                </div>
                <p class="settings-chat-sidebar-card__text">
                  这里统一管理执行员工、系统提示词、模型输出风格，以及 MCP
                  与工具预算。改动会直接影响当前对话的调度判断。
                </p>
                <div class="settings-chat-sidebar-card__meta">
                  <span>{{
                    hasSelectedProject ? currentProjectLabel : "未选择项目"
                  }}</span>
                  <span>{{ chatModeLabel }}</span>
                  <span>{{ activeChatSessionTitle }}</span>
                </div>
                <div class="settings-chat-sidebar-card__actions">
                  <div class="settings-chat-sidebar-card__status">
                    {{ autoSaveStatusText }}
                  </div>
                  <el-button
                    plain
                    size="small"
                    class="settings-summary-sync-button settings-summary-sync-button--hero"
                    :loading="settingsSaving"
                    @click="saveProjectChatSettings(false)"
                  >
                    立即同步
                  </el-button>
                </div>
              </div>

              <div class="settings-chat-sidebar-card">
                <div class="settings-chat-section-label">当前上下文</div>
                <div class="settings-chat-fact-list">
                  <div class="settings-chat-fact">
                    <span class="settings-chat-fact__label">执行员工</span>
                    <span class="settings-chat-fact__value">{{
                      selectedEmployeeSummary
                    }}</span>
                  </div>
                  <div class="settings-chat-fact">
                    <span class="settings-chat-fact__label">默认模型</span>
                    <span class="settings-chat-fact__value">{{
                      currentModelSummary
                    }}</span>
                  </div>
                  <div class="settings-chat-fact">
                    <span class="settings-chat-fact__label">模型类型</span>
                    <span class="settings-chat-fact__value">{{
                      currentModelTypeLabel
                    }}</span>
                  </div>
                  <div class="settings-chat-fact">
                    <span class="settings-chat-fact__label">本地连接器</span>
                    <span class="settings-chat-fact__value">{{
                      localConnectorSummary
                    }}</span>
                  </div>
                  <div class="settings-chat-fact">
                    <span class="settings-chat-fact__label">当前面板</span>
                    <span class="settings-chat-fact__value">对话配置</span>
                  </div>
                </div>
              </div>

              <div
                class="settings-chat-sidebar-card settings-chat-sidebar-card--note"
              >
                <div class="settings-chat-section-label">生效边界</div>
                <p class="settings-chat-sidebar-card__note">
                  <template v-if="hasSelectedProject">
                    当前配置会跟随项目上下文一起参与系统对话调度，不会改动平台其他页面的默认值。
                  </template>
                  <template v-else>
                    还没有选中项目，所以这里只能维护通用对话行为；项目员工和项目级
                    MCP 会在选择项目后开放。
                  </template>
                </p>
              </div>
            </aside>

            <div class="settings-chat-main">
              <div class="settings-chat-main-card" ref="settingsMainCardRef">
                <div class="settings-summary-card">
                  <div class="settings-summary-title">影响当前回答</div>
                  <div class="settings-summary-text">
                    这些设置会决定系统对话如何拼装上下文、选择模型与员工，并约束工具调用的上限与回退策略。
                  </div>
                  <div class="settings-summary-pills">
                    <span class="settings-summary-pill">
                      项目上下文 ·
                      {{ hasSelectedProject ? currentProjectLabel : "未选择" }}
                    </span>
                    <span class="settings-summary-pill">
                      执行员工 · {{ selectedEmployeeSummary }}
                    </span>
                    <span class="settings-summary-pill">
                      默认模型 · {{ currentModelSummary }}
                    </span>
                    <span class="settings-summary-pill">
                      模型类型 · {{ currentModelTypeLabel }}
                    </span>
                  </div>
                </div>

                <el-tabs class="settings-tabs">
                  <el-tab-pane label="基础设置">
                    <el-form
                      label-position="left"
                      label-width="160px"
                      class="settings-form"
                      size="default"
                    >
                      <el-form-item>
                        <template #label>
                          <span class="label-with-tooltip">执行员工</span>
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
                          :disabled="!selectedProjectId"
                        >
                          <el-option
                            v-for="item in projectEmployees"
                            :key="item.id"
                            :label="`${item.name || item.id}`"
                            :value="item.id"
                          >
                            <div class="settings-employee-option">
                              <div class="settings-employee-option__head">
                                <span class="settings-employee-option__name">
                                  {{ item.name || item.id }}
                                </span>
                                <el-tag
                                  size="small"
                                  :type="
                                    item.role === 'admin' ? 'danger' : 'info'
                                  "
                                >
                                  {{ item.role || "member" }}
                                </el-tag>
                              </div>
                              <div
                                v-if="
                                  item.skill_names && item.skill_names.length
                                "
                                class="settings-employee-option__meta"
                              >
                                技能: {{ item.skill_names.join(", ") }}
                              </div>
                              <div
                                v-if="
                                  item.rule_bindings &&
                                  item.rule_bindings.length
                                "
                                class="settings-employee-option__meta"
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
                            协作模式
                            <el-tooltip
                              content="多选员工时，自动协作会把任务拆解、协作边界和工具约束写入系统提示词；是否需要多人协作以及如何分工，仍由 AI 结合手册和规则自主判断。手动模式只保留当前工具池，不额外注入协作约束。"
                              placement="top"
                            >
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
                            </el-tooltip>
                          </span>
                        </template>
                        <el-select
                          v-model="projectChatSettings.employee_coordination_mode"
                          class="full-width"
                          :disabled="!selectedProjectId"
                        >
                          <el-option label="自动协作" value="auto" />
                          <el-option label="手动模式" value="manual" />
                        </el-select>
                      </el-form-item>

                      <el-form-item v-if="hasSelectedProject">
                        <template #label>
                          <span class="label-with-tooltip">
                            AI 入口文件
                            <el-tooltip
                              content="项目级规则入口。系统对话会优先读取它来理解规则、目录约定和实现约束。"
                              placement="top"
                            >
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
                            </el-tooltip>
                          </span>
                        </template>
                        <div class="workspace-path-editor">
                          <el-input
                            v-model="aiEntryFileDraft"
                            class="full-width"
                            placeholder="如 .ai/ENTRY.md 或 /abs/path/to/ENTRY.md"
                          />
                          <div class="workspace-path-actions">
                            <el-button
                              @click="promptProjectAiEntryFile"
                              :loading="aiEntryFilePicking"
                            >
                              选择文件
                            </el-button>
                            <el-button
                              type="primary"
                              :loading="aiEntryFileSaving"
                              @click="saveProjectAiEntryFile()"
                            >
                              保存入口
                            </el-button>
                          </div>
                          <div class="workspace-path-hint">
                            <template v-if="projectWorkspacePath">
                              当前项目工作区：{{
                                projectWorkspacePath
                              }}。若选择的文件位于该目录内，保存时会自动转成相对路径，便于系统对话统一复用。
                            </template>
                            <template v-else>
                              当前项目还没有平台工作区路径时，建议直接填写相对路径或绝对路径。
                            </template>
                            <template v-if="aiEntryFileResolved">
                              当前已保存：{{ aiEntryFileResolved }}
                            </template>
                            <template v-if="aiEntryFileDirty">
                              当前输入尚未保存。
                            </template>
                          </div>
                        </div>
                      </el-form-item>

                      <el-form-item>
                        <template #label>
                          <span class="label-with-tooltip">
                            系统提示词
                            <el-tooltip
                              content="(System Prompt) 设定 AI 的角色背景和最高优先级的行为准则。"
                              placement="top"
                            >
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
                            </el-tooltip>
                          </span>
                        </template>
                        <el-input
                          type="textarea"
                          v-model="systemPrompt"
                          :rows="3"
                          :placeholder="
                            isExternalAgentMode
                              ? `补充给 ${externalAgentDisplayLabel} 的启动上下文...`
                              : '你是项目开发助手...'
                          "
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
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
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

                  <el-tab-pane label="生成回答">
                    <el-form
                      label-position="left"
                      label-width="160px"
                      class="settings-form"
                      size="default"
                    >
                      <div class="model-parameter-note">
                        <div class="model-parameter-note__title">
                          当前模型类型：{{ currentModelTypeLabel }}
                        </div>
                        <div class="model-parameter-note__text">
                          {{
                            currentModelTypeDescription ||
                            "参数面板会跟随当前模型类型切换。"
                          }}
                        </div>
                      </div>

                      <template v-if="currentModelParameterMode === 'text'">
                        <el-form-item>
                          <template #label>
                            <span class="label-with-tooltip">
                              温度 (Temperature)
                              <el-tooltip
                                content="控制 AI 生成文本的随机性。值越小（如 0.1）回答越严谨保守，适合代码生成；值越大（如 0.8）回答越发散具有创造力。"
                                placement="top"
                              >
                                <el-icon class="label-icon"
                                  ><InfoFilled
                                /></el-icon>
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
                                <el-icon class="label-icon"
                                  ><InfoFilled
                                /></el-icon>
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
                                <el-icon class="label-icon"
                                  ><InfoFilled
                                /></el-icon>
                              </el-tooltip>
                            </span>
                          </template>
                          <el-select
                            v-model="projectChatSettings.answer_style"
                            class="full-width"
                          >
                            <el-option label="简洁 (Concise)" value="concise" />
                            <el-option
                              label="平衡 (Balanced)"
                              value="balanced"
                            />
                            <el-option
                              label="详细 (Detailed)"
                              value="detailed"
                            />
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
                                <el-icon class="label-icon"
                                  ><InfoFilled
                                /></el-icon>
                              </el-tooltip>
                            </span>
                          </template>
                          <el-switch
                            v-model="
                              projectChatSettings.prefer_conclusion_first
                            "
                          />
                        </el-form-item>
                      </template>

                      <template
                        v-else-if="
                          currentModelParameterMode === 'image' ||
                          currentModelParameterMode === 'video'
                        "
                      >
                        <el-form-item
                          v-for="section in currentModelParameterSections"
                          :key="`settings-${section.key}`"
                        >
                          <template #label>
                            <span class="label-with-tooltip">
                              {{ section.label }}
                              <el-tooltip
                                v-if="section.helper"
                                :content="section.helper"
                                placement="top"
                              >
                                <el-icon class="label-icon"
                                  ><InfoFilled
                                /></el-icon>
                              </el-tooltip>
                            </span>
                          </template>
                          <el-segmented
                            v-if="section.useSegmented"
                            :model-value="section.modelValue"
                            :options="
                              section.options.map((item) => ({
                                label: item.label,
                                value: item.value,
                              }))
                            "
                            class="full-width"
                            @change="
                              (value) =>
                                setCurrentModelParameterValue(
                                  section.key,
                                  value,
                                )
                            "
                          />
                          <el-select
                            v-else
                            :model-value="section.modelValue"
                            class="full-width"
                            @change="
                              (value) =>
                                setCurrentModelParameterValue(
                                  section.key,
                                  value,
                                )
                            "
                          >
                            <el-option
                              v-for="option in section.options"
                              :key="`${section.key}-${option.id}`"
                              :label="option.label"
                              :value="option.value"
                            />
                          </el-select>
                        </el-form-item>
                      </template>
                    </el-form>
                  </el-tab-pane>

                  <el-tab-pane label="工具与约束">
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
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
                            </el-tooltip>
                          </span>
                        </template>
                        <el-switch
                          v-model="projectChatSettings.auto_use_tools"
                        />
                      </el-form-item>

                      <el-form-item>
                        <template #label>
                          <span class="label-with-tooltip">
                            单轮仅回答
                            <el-tooltip
                              content="仅对下一次对话生效：强制 AI 直接用自然语言回答，禁止在此轮对话中调用任何工具。"
                              placement="top"
                            >
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
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
                                >本轮启用
                                {{ selectedProjectToolNames.length }}/{{
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
                                <el-button
                                  text
                                  size="small"
                                  @click="clearProjectTools"
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
                                  v-for="item in activeSystemModules.slice(
                                    0,
                                    12,
                                  )"
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
                                          (val) =>
                                            toggleProjectTool(
                                              item.tool_name,
                                              val,
                                            )
                                        "
                                      />
                                      <span class="mcp-module-name">{{
                                        item.name || item.id || "-"
                                      }}</span>
                                    </div>
                                    <el-tag
                                      size="small"
                                      :type="moduleTagType(item.module_type)"
                                      >{{
                                        moduleTypeLabel(item.module_type)
                                      }}</el-tag
                                    >
                                  </div>
                                  <div
                                    v-if="item.description"
                                    class="mcp-module-desc"
                                  >
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
                                  其余
                                  {{ activeSystemModules.length - 12 }}
                                  个模块未展示
                                </div>
                              </template>
                            </div>
                          </el-tab-pane>
                          <el-tab-pane
                            v-if="hasSelectedProject"
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

                      <div class="settings-section-title">执行限制</div>

                      <el-form-item>
                        <template #label>
                          <span class="label-with-tooltip">
                            工具执行超时
                            <el-tooltip
                              content="单个工具允许执行的最长时间（秒），避免某个耗时任务卡死整个对话。"
                              placement="top"
                            >
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
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
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
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

                      <div class="settings-section-title">调度上限</div>

                      <el-form-item>
                        <template #label>
                          <span class="label-with-tooltip">
                            最大循环轮次
                            <el-tooltip
                              content="AI 与工具之间交互迭代的最大次数，防止陷入无限死循环。"
                              placement="top"
                            >
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
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
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
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
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
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
                              <el-icon class="label-icon"
                                ><InfoFilled
                              /></el-icon>
                            </el-tooltip>
                          </span>
                        </template>
                        <el-select
                          v-model="projectChatSettings.tool_budget_strategy"
                          class="full-width"
                        >
                          <el-option
                            label="强制收敛回答 (Finalize)"
                            value="finalize"
                          />
                          <el-option label="直接停止 (Stop)" value="stop" />
                        </el-select>
                      </el-form-item>
                    </el-form>
                  </el-tab-pane>
                </el-tabs>
              </div>
            </div>
          </div>
        </div>

        <div
          v-else
          class="settings-center-stage__body settings-center-stage__body--inline"
        >
          <router-view class="settings-center-inline-page" />
        </div>
      </section>
    </div>
  </div>

  <el-tour
    v-model="chatTourVisible"
    v-model:current="chatTourCurrent"
    :show-arrow="false"
    :mask="true"
    :scroll-into-view-options="{ block: 'center', behavior: 'smooth' }"
    @close="handleChatTourClose"
    @finish="handleChatTourFinish"
  >
    <el-tour-step
      v-for="(item, index) in chatTourSteps"
      :key="`chat-tour-${index}`"
      :target="item.target"
      :title="item.title"
      :description="item.description"
      :placement="item.placement || 'bottom'"
    />
  </el-tour>

  <el-tour
    v-model="settingsTourVisible"
    v-model:current="settingsTourCurrent"
    :show-arrow="false"
    :mask="true"
    :scroll-into-view-options="{ block: 'center', behavior: 'smooth' }"
    @close="handleSettingsTourClose"
    @finish="handleSettingsTourFinish"
  >
    <el-tour-step
      v-for="(item, index) in settingsTourStepsResolved"
      :key="`settings-tour-${index}`"
      :target="item.target"
      :title="item.title"
      :description="item.description"
      :placement="item.placement || 'bottom'"
    />
  </el-tour>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import ExternalMcpManager from "@/components/ExternalMcpManager.vue";
import ProjectEmployeeDraftCreateDialog from "@/components/ProjectEmployeeDraftCreateDialog.vue";
import ProjectMaterialSaveDialog from "@/components/ProjectMaterialSaveDialog.vue";
import UnifiedMcpAccessDialog from "@/components/UnifiedMcpAccessDialog.vue";
import api from "@/utils/api.js";
import { createProjectChatWsClient } from "@/utils/ws-chat.js";
import { clearPermissionArray, hasPermission } from "@/utils/permissions.js";
import { fetchDictionary } from "@/utils/dictionaries.js";
import {
  Delete,
  Picture,
  Promotion,
  Document,
  DocumentCopy,
  CollectionTag,
  EditPen,
  Files,
  RefreshRight,
  VideoPause,
  Setting,
  InfoFilled,
} from "@element-plus/icons-vue";
import { marked } from "marked";
import { extractTextFromFile } from "@/utils/file-extractor.js";
import ComposerAssistBar from "@/components/ComposerAssistBar.vue";
import { buildRuntimeUrl } from "@/utils/runtime-url.js";
import { formatDateGroupLabel, formatRelativeDateTime } from "@/utils/date.js";
import {
  buildModelTypeMetaMap,
  DEFAULT_MODEL_TYPE,
  FALLBACK_MODEL_TYPE_OPTIONS,
  formatChatParameterValueLabel,
  findProviderModelConfig,
  getChatParameterDictionaryKey,
  getChatParameterDefaultValue,
  listChatParameterKeys,
  normalizeChatParameterValue,
  normalizeProviderModelConfigs,
  normalizeProviderModelNames,
  resolveChatParameterOptions,
} from "@/utils/llm-models.js";
import {
  buildMaterialDialogPayload,
  canSaveMessageAsMaterial as canSaveMessageAsMaterialEntry,
  MATERIAL_ASSET_TYPE_OPTIONS,
  MATERIAL_MIME_TYPE_OPTIONS,
} from "@/utils/project-materials.js";
import {
  pickWorkspaceDirectory,
  pickWorkspaceFile,
  toWorkspaceRelativePath,
} from "@/utils/workspace-picker.js";
import {
  buildChatSettingsRoute,
  inferSettingsPanelFromPath,
  isChatSettingsRoutePath,
} from "@/utils/chat-settings-route.js";

// 配置 marked 以支持代码高亮和换行
marked.setOptions({
  breaks: true,
  gfm: true,
});

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeCodeLanguage(value) {
  return String(value || "")
    .trim()
    .split(/\s+/)[0]
    .toLowerCase();
}

const markdownRenderer = new marked.Renderer();
const CODE_COPY_ICON_HTML =
  '<span class="el-icon chat-code-block__icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><path fill="currentColor" d="M128 320v576h576V320zm-32-64h640a32 32 0 0 1 32 32v640a32 32 0 0 1-32 32H96a32 32 0 0 1-32-32V288a32 32 0 0 1 32-32M960 96v704a32 32 0 0 1-32 32h-96v-64h64V128H384v64h-64V96a32 32 0 0 1 32-32h576a32 32 0 0 1 32 32M256 672h320v64H256zm0-192h320v64H256z" /></svg></span>';
const CODE_COPIED_ICON_HTML =
  '<span class="el-icon chat-code-block__icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><path fill="currentColor" d="M406.656 706.944 195.84 496.256a32 32 0 1 0-45.248 45.248l256 256 512-512a32 32 0 0 0-45.248-45.248L406.592 706.944z" /></svg></span>';
const CODE_PREVIEW_ICON_HTML =
  '<span class="el-icon chat-code-block__icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><path fill="currentColor" d="M942.2 486.2C847.4 334.6 691 224 512 224S176.6 334.6 81.8 486.2a48.9 48.9 0 0 0 0 51.6C176.6 689.4 333 800 512 800s335.4-110.6 430.2-262.2a48.9 48.9 0 0 0 0-51.6M512 736c-147.8 0-279-88.5-363.1-224C233 376.5 364.2 288 512 288s279 88.5 363.1 224C791 647.5 659.8 736 512 736m0-352a128 128 0 1 0 0 256 128 128 0 0 0 0-256m0 192a64 64 0 1 1 0-128 64 64 0 0 1 0 128" /></svg></span>';
const EMPLOYEE_DRAFT_BLOCK_RE = /```employee-draft\s*([\s\S]*?)```/i;
const PREVIEWABLE_CODE_LANGUAGES = new Set(["vue", "html", "htm"]);

function isPreviewableCodeBlock(content, language) {
  const normalizedLanguage = normalizeCodeLanguage(language);
  const text = String(content || "").trim();
  if (!text) return false;
  if (PREVIEWABLE_CODE_LANGUAGES.has(normalizedLanguage)) return true;
  if (/<template[\s>]/i.test(text) || /<script[\s>]/i.test(text)) return true;
  if (/<!doctype html/i.test(text) || /<html[\s>]/i.test(text)) return true;
  return false;
}

markdownRenderer.code = ({ text, lang, escaped }) => {
  const language = normalizeCodeLanguage(lang);
  const languageLabel = escapeHtml(language || "code");
  const codeHtml = escaped ? text : escapeHtml(text);
  const actions = [];
  if (isPreviewableCodeBlock(text, language)) {
    actions.push(
      `<button type="button" class="chat-code-block__preview" aria-label="预览代码" title="预览代码" data-code-lang="${escapeHtml(language || "")}">${CODE_PREVIEW_ICON_HTML}</button>`,
    );
  }
  actions.push(
    `<button type="button" class="chat-code-block__copy" aria-label="复制代码" title="复制代码" data-copy-label="复制代码" data-copied-label="已复制" data-copy-icon="${escapeHtml(CODE_COPY_ICON_HTML)}" data-copied-icon="${escapeHtml(CODE_COPIED_ICON_HTML)}">${CODE_COPY_ICON_HTML}</button>`,
  );
  return [
    '<div class="chat-code-block">',
    '<div class="chat-code-block__toolbar">',
    `<span class="chat-code-block__lang">${languageLabel}</span>`,
    `<div class="chat-code-block__actions">${actions.join("")}</div>`,
    "</div>",
    `<pre><code${language ? ` class="language-${escapeHtml(language)}"` : ""}>${codeHtml}</code></pre>`,
    "</div>",
  ].join("");
};

const route = useRoute();
const router = useRouter();
const CHAT_BASE_ROUTE_PATH = "/ai/chat";

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
  local_connector_id: "",
  connector_workspace_path: "",
  connector_sandbox_mode: "workspace-write",
  connector_sandbox_mode_explicit: false,
  selected_employee_id: "",
  selected_employee_ids: [],
  employee_coordination_mode: "auto",
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
  answer_style: "concise",
  prefer_conclusion_first: true,
  image_resolution: "1080x1080",
  image_aspect_ratio: "1:1",
  image_generate_four_views: false,
  image_style: "auto",
  image_quality: "high",
  video_aspect_ratio: "16:9",
  video_style: "cinematic",
  video_duration_seconds: 5,
  video_motion_strength: "medium",
};

const EMPLOYEE_DRAFT_AUTO_RULE_SOURCE_LABELS = {
  prompts_chat_curated: "系统规则源",
};

// 开放未选择项目时的通用对话模式，复用现有 sendGlobalChatWithoutProject 逻辑。
const ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT = true;
const LOCAL_CONNECTOR_STORAGE_PREFIX = "project_chat.local_connector";
const PROJECT_CREATED_EVENT = "project-created";
const GUIDE_TOUR_STORAGE_PREFIX = "project_chat.guide_tour";
const CHAT_PARAMETER_SECTION_CONFIG = {
  image: [
    {
      key: "image_aspect_ratio",
      label: "图片比例",
      helper: "先确定画面构图比例，再选择对应输出尺寸。",
      control: "segmented",
      maxSegmentedOptions: 5,
    },
    {
      key: "image_resolution",
      label: "图片分辨率",
      helper: "在比例确定后，再选择固定尺寸档位，后端会自动换算最终输出尺寸。",
      control: "select",
    },
    {
      key: "image_style",
      label: "图片风格",
      helper: "控制图片整体视觉风格。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
    {
      key: "image_quality",
      label: "图片质量",
      helper: "平衡生成速度和细节质量。",
      control: "segmented",
      maxSegmentedOptions: 3,
    },
  ],
  video: [
    {
      key: "video_aspect_ratio",
      label: "视频比例",
      helper: "控制视频画幅比例。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
    {
      key: "video_style",
      label: "视频风格",
      helper: "控制镜头和整体表现风格。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
    {
      key: "video_duration_seconds",
      label: "视频时长",
      helper: "控制单次生成片段长度。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
    {
      key: "video_motion_strength",
      label: "动作强度",
      helper: "控制镜头和主体的动态程度。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
  ],
};
const SETTINGS_CENTER_ITEM_DEFS = [
  {
    id: "chat",
    label: "对话设置",
    desc: "当前项目的 AI 对话运行参数",
    kind: "internal",
  },
  {
    id: "user-settings",
    label: "用户设置",
    desc: "当前账号默认 AI 与个人偏好",
    kind: "route",
    path: "/user/settings",
  },
  {
    id: "system-config",
    label: "系统配置",
    desc: "全局系统开关与默认项",
    kind: "route",
    path: "/system/config",
    permission: "menu.system.config",
  },
  {
    id: "dictionaries",
    label: "字典管理",
    desc: "维护模型类型等全局字典",
    kind: "route",
    path: "/dictionaries",
    permission: ["menu.system.dictionaries", "menu.system.config"],
  },
  {
    id: "providers",
    label: "模型供应商",
    desc: "管理平台模型源",
    kind: "route",
    path: "/llm/providers",
    permission: "menu.llm.providers",
  },
  {
    id: "projects",
    label: "项目管理",
    desc: "查看和维护项目列表",
    kind: "route",
    path: "/projects",
    permission: "menu.projects",
  },
  {
    id: "agent-templates",
    label: "智能体模板",
    desc: "沉淀行业模板，再创建员工",
    kind: "route",
    path: "/agent-templates",
    permission: "menu.employees",
  },
  {
    id: "employees",
    label: "员工管理",
    desc: "管理员工与能力绑定",
    kind: "route",
    path: "/employees",
    permission: "menu.employees",
  },
  {
    id: "skills",
    label: "技能目录",
    desc: "维护可复用技能",
    kind: "route",
    path: "/skills",
    permission: "menu.skills",
  },
  {
    id: "rules",
    label: "规则管理",
    desc: "管理系统规则",
    kind: "route",
    path: "/rules",
    permission: "menu.rules",
  },
  {
    id: "users",
    label: "用户管理",
    desc: "账号与权限视图",
    kind: "route",
    path: "/users",
    permission: "menu.users",
  },
  {
    id: "roles",
    label: "角色管理",
    desc: "角色和权限配置",
    kind: "route",
    path: "/roles",
    permission: "menu.roles",
  },
  {
    id: "api-keys",
    label: "API Key",
    desc: "使用控制和密钥管理",
    kind: "route",
    path: "/usage/keys",
    permission: "menu.usage.keys",
  },
];
const ROLE_LABEL_MAP = {
  admin: "管理员",
  user: "普通用户",
};
const SETTINGS_GUIDE_REASON_MAP = {
  chat: "先把项目、执行员工、模型和工具预算收束到同一轮上下文里。",
  "user-settings": "这里决定你的默认 AI 来源和个人偏好，会影响日常进入对话时的默认落点。",
  "system-config": "适合维护平台级默认值、功能开关和全局行为边界。",
  dictionaries: "当模型类型、字典项需要统一维护时，从这里集中处理。",
  providers: "维护供应商与模型池，决定平台能用哪些 AI 入口。",
  projects: "切回项目列表，确认当前上下文、成员边界和工作区归属。",
  "agent-templates": "先沉淀标准模板，再批量复用到不同员工。",
  employees: "管理员工角色、技能绑定和提示词结构，是把对话结论落成资产的主入口。",
  skills:
    "维护和补充更新技能。需要推进项目前端、后端或数据库数据时，可以先在这里补齐复用能力，再回到对话执行。",
  rules: "把稳定做法沉淀成规则，减少后续回答漂移。",
  users: "用于查看账号、权限和成员可见范围。",
  roles: "集中定义角色与权限，控制谁能看到哪些入口。",
  "api-keys": "当需要做调用控制、额度分配或密钥轮换时优先来这里。",
};

function formatRoleLabel(roleId) {
  const normalized = String(roleId || "").trim().toLowerCase();
  if (!normalized) return "当前用户";
  if (ROLE_LABEL_MAP[normalized]) return ROLE_LABEL_MAP[normalized];
  return normalized.replace(/[_-]+/g, " ");
}

function guideTourStorageKey(surface, username, roleId) {
  return [
    GUIDE_TOUR_STORAGE_PREFIX,
    String(surface || "").trim() || "chat",
    String(username || "").trim() || "anonymous",
    String(roleId || "").trim() || "user",
  ].join(".");
}

function resolveCurrentUsername() {
  return (
    String(localStorage.getItem("username") || "anonymous").trim() ||
    "anonymous"
  );
}

function resolveTourTarget(targetRef) {
  const raw = targetRef?.value;
  if (!raw) return document.body;
  return raw.$el || raw;
}

function hasSeenGuideTour(surface, username, roleId) {
  if (typeof window === "undefined") return true;
  return (
    localStorage.getItem(guideTourStorageKey(surface, username, roleId)) ===
    "1"
  );
}

function markGuideTourSeen(surface, username, roleId) {
  if (typeof window === "undefined") return;
  localStorage.setItem(guideTourStorageKey(surface, username, roleId), "1");
}

function localConnectorPreferenceStorageKey() {
  return `${LOCAL_CONNECTOR_STORAGE_PREFIX}.selected.${resolveCurrentUsername()}`;
}

function localConnectorWorkspaceStorageKey(projectId, connectorId) {
  return [
    LOCAL_CONNECTOR_STORAGE_PREFIX,
    "workspace",
    resolveCurrentUsername(),
    String(projectId || "").trim() || "default",
    String(connectorId || "").trim() || "default",
  ].join(".");
}

function readPreferredLocalConnectorId() {
  return String(
    localStorage.getItem(localConnectorPreferenceStorageKey()) || "",
  ).trim();
}

function writePreferredLocalConnectorId(connectorId) {
  const normalized = String(connectorId || "").trim();
  const key = localConnectorPreferenceStorageKey();
  if (normalized) {
    localStorage.setItem(key, normalized);
    return;
  }
  localStorage.removeItem(key);
}

function readPreferredLocalWorkspacePath(projectId, connectorId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedConnectorId = String(connectorId || "").trim();
  if (!normalizedProjectId || !normalizedConnectorId) return "";
  return String(
    localStorage.getItem(
      localConnectorWorkspaceStorageKey(
        normalizedProjectId,
        normalizedConnectorId,
      ),
    ) || "",
  ).trim();
}

function writePreferredLocalWorkspacePath(
  projectId,
  connectorId,
  workspacePath,
) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedConnectorId = String(connectorId || "").trim();
  if (!normalizedProjectId || !normalizedConnectorId) return;
  const normalizedWorkspacePath = String(workspacePath || "").trim();
  const key = localConnectorWorkspaceStorageKey(
    normalizedProjectId,
    normalizedConnectorId,
  );
  if (normalizedWorkspacePath) {
    localStorage.setItem(key, normalizedWorkspacePath);
    return;
  }
  localStorage.removeItem(key);
}

function skillResourceDirectoryStorageKey(projectId) {
  return [
    LOCAL_CONNECTOR_STORAGE_PREFIX,
    "skill_dir",
    resolveCurrentUsername(),
    String(projectId || "").trim() || "default",
  ].join(".");
}

function readPreferredSkillResourceDirectory(projectId) {
  return String(
    localStorage.getItem(skillResourceDirectoryStorageKey(projectId)) || "",
  ).trim();
}

function writePreferredSkillResourceDirectory(projectId, directoryPath) {
  const normalized = String(directoryPath || "").trim();
  const key = skillResourceDirectoryStorageKey(projectId);
  if (normalized) {
    localStorage.setItem(key, normalized);
    return;
  }
  localStorage.removeItem(key);
}

function buildProjectProvidersRequestUrl(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  return `/projects/${encodeURIComponent(normalizedProjectId)}/chat/providers`;
}

function applyLocalConnectorRuntimeSettings(baseSettings) {
  return normalizeDictionaryBackedChatSettings(
    normalizeProjectChatSettings(
      baseSettings && typeof baseSettings === "object" ? baseSettings : {},
    ),
  );
}

const loading = ref(false);
const chatLoading = ref(false);
const settingsSaving = ref(false);
const workspacePathSaving = ref(false);
const workspacePathTesting = ref(false);
const autoSaveState = ref("idle");
const autoSaveUpdatedAt = ref("");
const projectSettingsHydrating = ref(false);

const projects = ref([]);
const providers = ref([]);
const localConnectors = ref([]);
const desktopConnectorArtifacts = ref([]);
const projectEmployees = ref([]);
const externalAgentInfo = ref({
  agent_type: "codex_cli",
  label: "Codex CLI",
  command: "codex",
  resolved_command: "",
  command_source: "missing",
  runtime_model_name: "codex-cli",
  exact_model_name: "",
  execution_mode: "local_connector",
  runner_url: "",
  materialized_by: "",
  available: false,
  installed: false,
  implemented: true,
  reason: "",
  supports_terminal_mirror: true,
  supports_workspace_write: true,
  ready: false,
  session_id: "",
  thread_id: "",
  sandbox_mode: "workspace-write",
  workspace_path: "",
  local_connector_id: "",
  local_connector_name: "",
  local_connector_online: false,
  sandbox_modes: ["read-only", "workspace-write"],
  agent_types: [],
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
const runtimeExternalTools = ref([]);
const messages = ref([]);
const chatSessions = ref([]);
const employeeDraftCatalog = ref({
  skills: [],
  rules: [],
  loaded_at: 0,
});
const employeeDraftCreatingKey = ref("");
const employeeDraftDialogVisible = ref(false);
const employeeDraftDialogLoading = ref(false);
const employeeDraftDialogPayload = ref(null);
const employeeDraftDialogItem = ref(null);
const materialDialogVisible = ref(false);
const materialDialogSaving = ref(false);
const materialDialogPayload = ref(null);
const employeeDraftExternalSkillSites = ref([]);
const employeeDraftAutoCreateSkills = ref(true);
const employeeDraftAutoCreateRules = ref(true);
const employeeDraftAddToProject = ref(false);
const employeeDraftAutoRuleGenerationEnabled = ref(true);
const employeeDraftAutoRuleGenerationSourceFilters = ref([
  "prompts_chat_curated",
]);
const employeeDraftAutoRuleGenerationMaxCount = ref(3);
const unifiedMcpDialogVisible = ref(false);
const skillResourceDialogVisible = ref(false);
const skillResourceDirectoryDraft = ref("");
const skillResourceDirectoryPicking = ref(false);
const skillResourceSearchQuery = ref("");
const skillResourceSearchResults = ref([]);
const skillResourceSearchResolvedQueries = ref([]);
const skillResourceSearchLoading = ref(false);
const skillResourceInstallingSlug = ref("");
const codePreviewVisible = ref(false);
const codePreviewTitle = ref("代码预览");
const codePreviewSrcdoc = ref("");
const codePreviewError = ref("");

const selectedProjectId = ref("");
const selectedEmployeeIds = ref([]);
const selectedProviderId = ref("");
const selectedModelName = ref("");
const defaultProviderId = ref("");
const defaultModelName = ref("");
const globalDefaultProviderId = ref("");
const globalDefaultModelName = ref("");
const modelTypeOptions = ref(FALLBACK_MODEL_TYPE_OPTIONS);
const chatParameterOptions = ref({});
const temperature = ref(0.1);
const systemPrompt = ref("");
const activeMcpSource = ref("system");
const activeSettingsPanel = ref("chat");
const activeSystemScope = ref("project_related");
const selectedProjectToolNames = ref([]);
const projectChatSettings = ref({ ...CHAT_SETTINGS_DEFAULTS });
const projectWorkspacePath = ref("");
const workspacePathDraft = ref("");
const projectAiEntryFile = ref("");
const aiEntryFileDraft = ref("");
const singleRoundAnswerOnly = ref(false);
const employeeCreateSubmitting = ref(false);
const activeComposerAssist = ref("");
const externalMcpTotal = ref(0);
const agentStatusExpanded = ref(false);
const currentChatSessionId = ref("");
const creatingChatSession = ref(false);
const deletingChatSessionId = ref("");
const downloadingDesktopArtifactKey = ref("");
const localConnectorRefreshing = ref(false);
const localConnectorPairing = ref(false);
const workspacePathPicking = ref(false);
const aiEntryFilePicking = ref(false);
const aiEntryFileSaving = ref(false);
let connectorPollTimer = null;
let terminalApprovalFallbackTimer = null;

const wsConnected = ref(false);
const wsClient = ref(null);
const wsProjectId = ref("");
const pendingRequests = new Map();
const pendingAgentPrepares = new Map();
const activeApprovalIds = new Set();
const activeReviewIds = new Set();
const externalAgentWarmupLoading = ref(false);
const externalAgentWarmupKey = ref("");
const terminalPanelExpanded = ref(false);
const terminalPanelLines = ref([]);
const terminalPanelRef = ref(null);
const terminalPanelStatus = ref("idle");
const terminalPanelInput = ref("");
const terminalMirrorConnected = ref(false);
const activeTerminalMirrorAssistantIndex = ref(-1);
const terminalApprovalDialogVisible = ref(false);
const terminalApprovalHandledKey = ref("");
const terminalApprovalFallbackPrompt = ref(null);
const inlineEditingMessageIndex = ref(-1);
const inlineEditingMessageId = ref("");
const inlineEditingDraft = ref("");
const inlineEditingBusy = ref(false);
const highlightedMessageId = ref("");
const chatTourVisible = ref(false);
const chatTourCurrent = ref(0);
const settingsTourVisible = ref(false);
const settingsTourCurrent = ref(0);

const maxUploadLimit = ref(6);
const chatMaxTokens = ref(512);
const chatSettingsButtonRef = ref(null);
const chatGuideButtonRef = ref(null);
const chatContextBarRef = ref(null);
const chatComposerRef = ref(null);
const settingsSidebarRef = ref(null);
const settingsGuideButtonRef = ref(null);
const settingsContextBarRef = ref(null);
const settingsMainCardRef = ref(null);

const hasSelectedProject = computed(() =>
  Boolean(String(selectedProjectId.value || "").trim()),
);
const canUseExternalAgent = computed(() => false);
const isExternalAgentMode = computed(() => false);
const chatModeLabel = computed(() => "系统对话");
const wsStatusText = computed(() => (wsConnected.value ? "已连接" : "未连接"));
const wsStatusType = computed(() => (wsConnected.value ? "success" : "info"));
const workspacePathResolved = computed(() =>
  String(externalAgentInfo.value.workspace_path || "").trim(),
);
const workspacePathDraftNormalized = computed(() =>
  String(workspacePathDraft.value || "").trim(),
);
const aiEntryFileResolved = computed(() =>
  String(projectAiEntryFile.value || "").trim(),
);
const aiEntryFileDraftNormalized = computed(() =>
  String(aiEntryFileDraft.value || "").trim(),
);
const workspacePathConfigured = computed(() => !!workspacePathResolved.value);
const externalAgentConnectorRequired = computed(
  () => isExternalAgentMode.value && !usingLocalConnector.value,
);
const workspacePathDirty = computed(() => {
  if (!isExternalAgentMode.value) return false;
  return workspacePathDraftNormalized.value !== workspacePathResolved.value;
});
const aiEntryFileDirty = computed(
  () => aiEntryFileDraftNormalized.value !== aiEntryFileResolved.value,
);
const activeLocalConnector = computed(() => {
  const connectorId = String(
    projectChatSettings.value.local_connector_id || "",
  ).trim();
  if (!connectorId) return null;
  return (
    (localConnectors.value || []).find(
      (item) => String(item?.id || "").trim() === connectorId,
    ) || null
  );
});
const usingLocalConnector = computed(() => Boolean(activeLocalConnector.value));
const activeLocalConnectorProviderId = computed(() => {
  const connectorId = String(
    projectChatSettings.value.local_connector_id || "",
  ).trim();
  if (!connectorId) return "";
  return String(
    (providers.value || []).find(
      (item) =>
        item?.provider_type === "local-connector" &&
        String(item?.connector_id || "").trim() === connectorId,
    )?.id || "",
  ).trim();
});
const modelTypeMetaMap = computed(() =>
  buildModelTypeMetaMap(modelTypeOptions.value),
);
const providerDisplayNameMap = computed(() => {
  const map = new Map();
  for (const item of providers.value || []) {
    const providerId = String(item?.id || "").trim();
    if (!providerId) continue;
    map.set(providerId, String(item?.name || providerId).trim());
  }
  return map;
});
const externalAgentDisplayLabel = computed(
  () =>
    String(externalAgentInfo.value.label || "外部 Agent").trim() ||
    "外部 Agent",
);
const externalAgentAvailabilityLabel = computed(() => {
  if (externalAgentInfo.value.command_source === "local_connector_required") {
    return "需连接器";
  }
  if (externalAgentInfo.value.available) return "可用";
  if (externalAgentInfo.value.installed) return "已安装待接入";
  return "未发现";
});
const externalAgentRuntimeLabel = computed(
  () =>
    String(
      externalAgentInfo.value.runtime_model_name ||
        externalAgentInfo.value.agent_type ||
        "external-agent",
    ).trim() || "external-agent",
);
const externalAgentStatusSummary = computed(() => {
  const parts = [
    externalAgentDisplayLabel.value,
    externalAgentRuntimeLabel.value,
    "本地连接器",
    String(externalAgentInfo.value.sandbox_mode || "workspace-write").trim() ||
      "workspace-write",
  ];
  if (externalAgentInfo.value.local_connector_name) {
    parts.push(externalAgentInfo.value.local_connector_name);
  }
  if (externalAgentInfo.value.thread_id) {
    parts.push(`Thread ${shortThreadId.value}`);
  }
  return parts.filter(Boolean).join(" · ");
});
const chatHeaderStatusText = computed(() => {
  if (!isExternalAgentMode.value) return wsStatusText.value;
  if (externalAgentConnectorRequired.value) return "未选择连接器";
  if (!workspacePathConfigured.value) return "未配置工作区";
  if (workspacePathDirty.value) return "工作区未保存";
  if (externalAgentWarmupLoading.value) return "预热中";
  if (externalAgentInfo.value.ready) return "已就绪";
  return "未就绪";
});
const chatHeaderStatusType = computed(() => {
  if (!isExternalAgentMode.value) return wsStatusType.value;
  if (externalAgentConnectorRequired.value) return "warning";
  if (!workspacePathConfigured.value || workspacePathDirty.value)
    return "warning";
  if (externalAgentWarmupLoading.value) return "warning";
  if (externalAgentInfo.value.ready) return "success";
  return "info";
});
const chatHeaderSubtext = computed(() => {
  if (!hasAccessibleProjects.value) {
    return "当前账号未分配任何项目";
  }
  if (!hasSelectedProject.value) {
    return ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
      ? "当前是通用对话；选择项目后可切换到项目上下文"
      : "请先在顶部选择项目后开始对话";
  }
  if (!isExternalAgentMode.value) {
    const provider = String(
      selectedProviderId.value || defaultProviderId.value || "",
    ).trim();
    const model = String(
      selectedModelName.value || defaultModelName.value || "",
    ).trim();
    if (provider && model) return `${provider} · ${model}`;
    if (model) return `当前模型 ${model}`;
    return "系统对话";
  }
  const parts = [
    `${externalAgentDisplayLabel.value} 对话`,
    externalAgentRuntimeLabel.value,
    "本地连接器",
  ];
  if (externalAgentConnectorRequired.value) {
    parts.push("待选择连接器");
  }
  if (externalAgentInfo.value.local_connector_name) {
    parts.push(externalAgentInfo.value.local_connector_name);
  }
  if (shortThreadId.value) {
    parts.push(`Thread ${shortThreadId.value}`);
  }
  return parts.filter(Boolean).join(" · ");
});
const currentUsername = computed(() => resolveCurrentUsername());
const currentUsernameInitial = computed(
  () =>
    String(currentUsername.value || "?")
      .trim()
      .slice(0, 1)
      .toUpperCase() || "?",
);
const currentRoleId = computed(
  () =>
    String(localStorage.getItem("role") || "user")
      .trim()
      .toLowerCase() || "user",
);
const currentRoleLabel = computed(() => formatRoleLabel(currentRoleId.value));

async function logoutFromChat() {
  try {
    await ElMessageBox.confirm("确认退出当前登录账号？", "退出登录", {
      confirmButtonText: "退出",
      cancelButtonText: "取消",
      type: "warning",
    });
  } catch {
    return;
  }
  localStorage.removeItem("token");
  localStorage.removeItem("username");
  localStorage.removeItem("role");
  clearPermissionArray();
  router.replace("/login");
}

const localConnectorSummary = computed(() => {
  if (!isExternalAgentMode.value) {
    return usingLocalConnector.value ? "已绑定连接器" : "未使用";
  }
  if (externalAgentConnectorRequired.value) {
    return "待选择连接器";
  }
  if (!activeLocalConnector.value) {
    return "未连接";
  }
  const connectorName = String(
    activeLocalConnector.value.connector_name ||
      activeLocalConnector.value.id ||
      "",
  ).trim();
  const onlineText = activeLocalConnector.value.online ? "在线" : "离线";
  return [connectorName || "本地连接器", onlineText]
    .filter(Boolean)
    .join(" · ");
});
const currentProjectLabel = computed(() => {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return "未选择";
  const matched = (projects.value || []).find((item) => item.id === projectId);
  return String(matched?.name || projectId);
});
const skillResourceSites = computed(() =>
  (employeeDraftExternalSkillSites.value || [])
    .map(normalizeEmployeeDraftExternalSkillSite)
    .filter((item) => item.title && item.url),
);
const skillResourceDirectoryStored = computed(() =>
  readPreferredSkillResourceDirectory(selectedProjectId.value),
);
const skillResourceDirectoryResolved = computed(() =>
  String(
    skillResourceDirectoryDraft.value || skillResourceDirectoryStored.value,
  ).trim(),
);
const settingsCenterItems = computed(() =>
  SETTINGS_CENTER_ITEM_DEFS.filter(
    (item) => !item.permission || hasPermission(item.permission),
  ),
);
const settingsInternalItems = computed(() =>
  settingsCenterItems.value.filter((item) => item.kind === "internal"),
);
const settingsRouteItems = computed(() =>
  settingsCenterItems.value.filter((item) => item.kind === "route"),
);
const activeSettingsPanelItem = computed(
  () =>
    settingsCenterItems.value.find(
      (item) => item.id === String(activeSettingsPanel.value || "").trim(),
    ) ||
    settingsCenterItems.value[0] ||
    null,
);
const isSettingsCenterRoute = computed(() =>
  isChatSettingsRoutePath(route.path),
);
const roleAccessNarrative = computed(() => {
  if (currentRoleId.value === "admin") {
    return "你当前处于平台治理视角，可以同时调整对话策略、全局配置、模型供应商和角色权限。";
  }
  if (hasPermission("menu.projects") && hasPermission("menu.employees")) {
    return "你当前偏向项目与员工协同视角，适合先在对话里验证方案，再去项目或员工入口做结构化落地。";
  }
  if (hasPermission("menu.projects")) {
    return "你当前以项目协作为主，优先关注项目上下文、对话配置和个人默认 AI。";
  }
  return "你当前以个人使用视角为主，设置中心只展示你实际可访问的入口，避免把平台配置暴露给无关角色。";
});
const settingsMenuGuideEntries = computed(() =>
  settingsCenterItems.value.map((item) => ({
    ...item,
    intro:
      SETTINGS_GUIDE_REASON_MAP[item.id] ||
      item.desc ||
      roleAccessNarrative.value,
  })),
);
const chatTourSteps = computed(() => [
  {
    title: `${currentRoleLabel.value} 的使用引导`,
    description:
      "这是分步蒙层导览。看过一次或主动跳过后，本账号在当前角色下不会再自动弹出。",
    target: () => resolveTourTarget(chatGuideButtonRef),
    placement: "bottom-start",
  },
  {
    title: hasSelectedProject.value
      ? `${currentProjectLabel.value} 的主要能力入口`
      : "先看当前对话工作台",
    description: hasSelectedProject.value
      ? "这里把当前项目的主入口集中在一起：继续 AI 对话、打开素材库、接入 MCP、补更新技能。要更新项目的前端、后端或数据库数据，通常就从这里进入并继续推进。"
      : "这里是当前会话的主工作台。即使还没选项目，也可以先直接对话，再根据需要补项目、MCP 或技能资源。",
    target: () => resolveTourTarget(chatContextBarRef),
    placement: "bottom-start",
  },
  {
    title: hasSelectedProject.value
      ? `确认项目上下文：${currentProjectLabel.value}`
      : hasAccessibleProjects.value
        ? "先判断是否切到项目上下文"
        : "当前先用通用对话",
    description: hasSelectedProject.value
      ? "当前项目已选中，后续提问、附件、员工和工具都会优先围绕这个项目组织。"
      : hasAccessibleProjects.value
        ? "如果问题依赖项目规则、成员或素材，先切到对应项目；纯泛化问题可以先直接开始。"
        : "当前账号没有可访问项目时，也能先做通用对话，不会卡在项目选择上。",
    target: () => resolveTourTarget(projectSwitcherRef),
    placement: "right-start",
  },
  {
    title: "直接下达任务，不要只给主题",
    description:
      "在输入框里优先写“目标 + 约束 + 预期结果”。如果你要更新项目前端、后端或数据库数据，直接把改动范围、接口/表、预期结果写清楚，AI 更容易一次给到可执行输出。",
    target: () => resolveTourTarget(chatComposerRef),
    placement: "top",
  },
  {
    title: "需要收束结果时进入设置中心",
    description:
      "当你要调整执行员工、系统提示词、模型参数或工具预算时，从这里进入设置中心。那里会按你当前角色只展示真正可用的菜单。",
    target: () => resolveTourTarget(chatSettingsButtonRef),
    placement: "left",
  },
]);
const settingsTourStepsResolved = computed(() => [
  {
    title: `${currentRoleLabel.value} 的菜单导览`,
    description:
      "这是按当前角色权限生成的分步导览。跳过或完成后，本账号在当前角色下不会再自动弹出。",
    target: () => resolveTourTarget(settingsGuideButtonRef),
    placement: "bottom-start",
  },
  {
    title: "左侧只显示你真正能访问的菜单",
    description: roleAccessNarrative.value,
    target: () => resolveTourTarget(settingsSidebarRef),
    placement: "right-start",
  },
  ...settingsMenuGuideEntries.value.map((item) => ({
    title:
      item.kind === "internal"
        ? `${item.label}：当前项目会话配置`
        : `${item.label}：菜单用途`,
    description: item.intro,
    target: () => resolveTourTarget(settingsSidebarRef),
    placement: "right-start",
  })),
  {
    title: "先在这里改当前对话，再去平台页面",
    description:
      "建议先完成当前项目对话设置，再进入其他平台菜单。改完后回到 AI 对话立即验证，最容易看出配置是否真的生效。",
    target: () => resolveTourTarget(settingsMainCardRef),
    placement: "left-start",
  },
  {
    title: "需要重新看导览时，从这里再次打开",
    description:
      "导览不会反复自动打扰你；只有手动点击“菜单导览”时，才会重新播放。",
    target: () => resolveTourTarget(settingsContextBarRef),
    placement: "bottom",
  },
]);
const selectedEmployeeSummary = computed(() => {
  const selectedCount = Array.isArray(selectedEmployeeIds.value)
    ? selectedEmployeeIds.value.length
    : 0;
  const total = Array.isArray(projectEmployees.value)
    ? projectEmployees.value.length
    : 0;
  if (!total) return "暂无员工";
  if (!selectedCount) return `全部员工 (${total})`;
  if (selectedCount === 1) {
    const selectedId = String(selectedEmployeeIds.value[0] || "").trim();
    const matched = (projectEmployees.value || []).find(
      (item) => String(item.id || "").trim() === selectedId,
    );
    return String(matched?.name || selectedId || "1 名员工");
  }
  return `${selectedCount} 名员工`;
});
const currentModelSummary = computed(() => {
  const provider = String(
    selectedProviderId.value || defaultProviderId.value || "",
  ).trim();
  const providerLabel = providerDisplayNameMap.value.get(provider) || provider;
  const model = String(
    selectedModelName.value || defaultModelName.value || "",
  ).trim();
  if (providerLabel && model) return `${providerLabel} / ${model}`;
  if (model) return model;
  if (providerLabel) return providerLabel;
  return "系统默认";
});
const currentSelectedProvider = computed(
  () =>
    (providers.value || []).find(
      (item) =>
        String(item?.id || "").trim() ===
        String(
          selectedProviderId.value || defaultProviderId.value || "",
        ).trim(),
    ) || null,
);
const currentSelectedModelConfig = computed(() =>
  findProviderModelConfig(
    currentSelectedProvider.value,
    String(selectedModelName.value || defaultModelName.value || "").trim(),
    modelTypeOptions.value,
  ),
);
const currentModelType = computed(
  () =>
    String(
      currentSelectedModelConfig.value?.model_type || DEFAULT_MODEL_TYPE,
    ).trim() || DEFAULT_MODEL_TYPE,
);
const currentModelTypeMeta = computed(
  () =>
    modelTypeMetaMap.value.get(currentModelType.value) ||
    modelTypeMetaMap.value.get(DEFAULT_MODEL_TYPE),
);
const currentModelTypeLabel = computed(
  () =>
    String(currentModelTypeMeta.value?.label || "文本生成").trim() ||
    "文本生成",
);
const currentModelTypeDescription = computed(() =>
  String(currentModelTypeMeta.value?.description || "").trim(),
);
const currentModelParameterMode = computed(
  () =>
    String(currentModelTypeMeta.value?.chat_parameter_mode || "text").trim() ||
    "text",
);
const mediaParameterPopoverVisible = ref(false);
const shouldShowMediaParameterTrigger = computed(
  () =>
    (currentModelParameterMode.value === "image" ||
      currentModelParameterMode.value === "video") &&
    currentModelParameterSections.value.length > 0,
);
const currentMediaParameterTriggerLabel = computed(() =>
  currentModelParameterMode.value === "video" ? "视频生成" : "图片生成",
);
const currentMediaParameterPanelTitle = computed(() =>
  currentModelParameterMode.value === "video"
    ? "选择视频生成参数"
    : "选择图片生成参数",
);
const currentMediaParameterTriggerIcon = computed(() =>
  currentModelParameterMode.value === "video" ? CollectionTag : Picture,
);
const shouldShowImageFourViewsOption = computed(
  () => currentModelParameterMode.value === "image",
);

function coerceBooleanSetting(value, fallback = false) {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  if (typeof value === "boolean") return value;
  const normalizedValue = String(value).trim().toLowerCase();
  if (["true", "1", "yes", "on"].includes(normalizedValue)) return true;
  if (["false", "0", "no", "off"].includes(normalizedValue)) return false;
  return Boolean(value);
}

const imageGenerateFourViewsEnabled = computed(() =>
  coerceBooleanSetting(
    projectChatSettings.value?.image_generate_four_views,
    false,
  ),
);

function getChatParameterDictionaryEntry(parameterKey) {
  return chatParameterOptions.value?.[parameterKey] || {};
}

function getRuntimeChatParameterDefaultValue(parameterKey) {
  return normalizeChatParameterValue(
    parameterKey,
    getChatParameterDictionaryEntry(parameterKey).defaultValue ??
      getChatParameterDefaultValue(parameterKey),
    getChatParameterDictionaryEntry(parameterKey).options || [],
  );
}

const resolvedChatParameterOptions = computed(() => {
  const next = {};
  for (const parameterKey of listChatParameterKeys()) {
    next[parameterKey] = resolveChatParameterOptions(
      parameterKey,
      getChatParameterDictionaryEntry(parameterKey).options || [],
    );
  }
  return next;
});
const currentModelParameterSections = computed(() =>
  (CHAT_PARAMETER_SECTION_CONFIG[currentModelParameterMode.value] || [])
    .map((section) => {
      const options = resolvedChatParameterOptions.value[section.key] || [];
      if (!options.length) return null;
      const normalizedValue = normalizeChatParameterValue(
        section.key,
        projectChatSettings.value?.[section.key],
        getChatParameterDictionaryEntry(section.key).options || [],
      );
      return {
        ...section,
        options,
        modelValue: normalizedValue,
        useSegmented:
          section.control === "segmented" &&
          options.length <= Number(section.maxSegmentedOptions || 4),
      };
    })
    .filter(Boolean),
);

function setCurrentModelParameterValue(parameterKey, value) {
  projectChatSettings.value = {
    ...projectChatSettings.value,
    [parameterKey]: normalizeChatParameterValue(
      parameterKey,
      value,
      getChatParameterDictionaryEntry(parameterKey).options || [],
    ),
  };
}

function toggleImageGenerateFourViews() {
  projectChatSettings.value = {
    ...projectChatSettings.value,
    image_generate_four_views: !imageGenerateFourViewsEnabled.value,
  };
}

function describeChatParameterValue(parameterKey, value) {
  return formatChatParameterValueLabel(
    parameterKey,
    value,
    getChatParameterDictionaryEntry(parameterKey).options || [],
  );
}

function buildModelGenerationInstruction() {
  if (currentModelParameterMode.value === "image") {
    const instructionLines = [
      "当前模型类型：图片生成。",
      "请按以下预设执行本轮生成：",
      `- 图片比例：${describeChatParameterValue("image_aspect_ratio", projectChatSettings.value.image_aspect_ratio)}`,
      `- 图片分辨率：${describeChatParameterValue("image_resolution", projectChatSettings.value.image_resolution)}`,
      `- 图片风格：${describeChatParameterValue("image_style", projectChatSettings.value.image_style)}`,
      `- 图片质量：${describeChatParameterValue("image_quality", projectChatSettings.value.image_quality)}`,
      "- 如果模型支持直接生成图片，请直接返回图片结果；如果当前模型只支持文本，请输出可直接用于图片生成的高质量提示词。",
    ];
    if (imageGenerateFourViewsEnabled.value) {
      instructionLines.push(
        "- 四视图：开启，自动生成同一角色的正面、背面、左侧、右侧四视图。",
      );
      instructionLines.push(
        "- 输出要求：四张独立视图，保持角色服装、发型、年龄感、五官和整体设定一致，不要多人，不要多头，不要四宫格拼接，不要杂乱排版。",
      );
      instructionLines.push("- 不要文字、水印、边框、logo。");
    }
    return instructionLines.join("\n");
  }
  if (currentModelParameterMode.value === "video") {
    return [
      "当前模型类型：视频生成。",
      "请按以下预设执行本轮生成：",
      `- 视频比例：${describeChatParameterValue("video_aspect_ratio", projectChatSettings.value.video_aspect_ratio)}`,
      `- 视频风格：${describeChatParameterValue("video_style", projectChatSettings.value.video_style)}`,
      `- 视频时长：${describeChatParameterValue("video_duration_seconds", projectChatSettings.value.video_duration_seconds)}`,
      `- 动作强度：${describeChatParameterValue("video_motion_strength", projectChatSettings.value.video_motion_strength)}`,
      "- 如果模型支持直接生成视频，请直接返回视频结果；如果当前模型只支持文本，请输出可直接用于视频生成的分镜式提示词。",
    ].join("\n");
  }
  return "";
}

function appendModelGenerationInstruction(prompt) {
  const instruction = buildModelGenerationInstruction();
  if (!instruction) return prompt;
  return [String(prompt || "").trim(), "", instruction]
    .filter(Boolean)
    .join("\n");
}

watch(currentModelParameterMode, (nextMode) => {
  if (nextMode !== "image" && nextMode !== "video") {
    mediaParameterPopoverVisible.value = false;
  }
});

const activeChatSessionTitle = computed(() => {
  const sessionId = String(currentChatSessionId.value || "").trim();
  if (!sessionId) return "新对话";
  const matched = (chatSessions.value || []).find(
    (item) => item.id === sessionId,
  );
  return String(matched?.title || "新对话").trim() || "新对话";
});
const currentChatSession = computed(
  () =>
    (chatSessions.value || []).find(
      (item) => item.id === String(currentChatSessionId.value || "").trim(),
    ) || null,
);
const autoSaveStatusText = computed(() => {
  if (!selectedProjectId.value) return "未选择项目";
  if (projectSettingsHydrating.value) return "正在同步项目配置...";
  if (settingsSaving.value || autoSaveState.value === "saving") {
    return "配置保存中...";
  }
  if (autoSaveState.value === "error") return "自动保存失败";
  if (autoSaveUpdatedAt.value) return `已自动保存 ${autoSaveUpdatedAt.value}`;
  return "修改后自动保存";
});
const externalAgentOptions = computed(() =>
  Array.isArray(externalAgentInfo.value.agent_types)
    ? externalAgentInfo.value.agent_types
    : [],
);
const hasAccessibleProjects = computed(
  () => Array.isArray(projects.value) && projects.value.length > 0,
);
const groupedChatSessions = computed(() => {
  const groups = new Map();
  for (const session of chatSessions.value || []) {
    const label = resolveChatSessionGroupLabel(session);
    if (!groups.has(label)) {
      groups.set(label, []);
    }
    groups.get(label).push(session);
  }
  return Array.from(groups.entries()).map(([label, items]) => ({
    label,
    items,
  }));
});
const starterPrompts = computed(() => {
  if (!hasSelectedProject.value && ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT) {
    return [
      "帮我梳理这个问题的思路",
      "先给结论，再展开步骤",
      "把我的想法优化成可执行方案",
    ];
  }
  if (!hasAccessibleProjects.value || !hasSelectedProject.value) return [];
  return [
    "帮我分析这个项目的当前问题",
    "先给一个实现方案",
    "把需求拆成可执行步骤",
  ];
});
const emptyStateTitle = computed(() => {
  if (!hasAccessibleProjects.value) return "暂无可访问项目";
  if (!hasSelectedProject.value) {
    return ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
      ? "开始一轮通用对话"
      : "先选择一个项目";
  }
  return "开始一轮新的对话";
});
const emptyStateText = computed(() => {
  if (!hasAccessibleProjects.value) {
    if (activeComposerAssistMeta.value?.id === "employee_create") {
      return "当前没有可访问项目，但你仍然可以直接描述岗位职责，AI 会先帮你生成员工草稿，确认后即可创建到员工管理。";
    }
    return ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
      ? "当前账号还没有被分配任何项目，但你仍然可以直接进行通用对话；如果需要创建 AI 员工，也可以点击“创建员工”。"
      : "当前账号还没有被分配任何项目。你仍然可以点击“创建员工”，先在这里生成并创建 AI 员工。";
  }
  if (!hasSelectedProject.value) {
    return activeComposerAssistMeta.value?.id === "employee_create"
      ? "当前将直接生成员工草稿，无需选择项目；确认后会直接创建到员工管理。"
      : ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
        ? "当前是通用对话模式。你可以直接聊天；如果需要项目上下文或项目员工，再从顶部选择项目。"
        : "请先从顶部选择一个项目，再进行普通对话或上传附件。";
  }
  return "选择项目后，你可以直接提问、上传附件，或让系统基于项目上下文给方案与实现建议。";
});

const composerPlaceholder = computed(() =>
  !hasAccessibleProjects.value
    ? activeComposerAssistMeta.value?.id === "employee_create"
      ? "描述你要创建的员工角色，例如：帮我创建一个擅长 PRD 拆解和原型输出的产品经理员工。"
      : ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
        ? "当前没有可访问项目，也可以直接开始通用对话；如需创建员工，可点击上方“创建员工”。"
        : "当前没有可访问项目；如需创建员工，可先点击上方“创建员工”。"
    : !hasSelectedProject.value
      ? activeComposerAssistMeta.value?.id === "employee_create"
        ? "描述你要创建的员工角色，例如：帮我创建一个擅长 PRD 拆解和原型输出的产品经理员工。"
        : ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
          ? "直接输入问题开始通用对话；如需项目上下文，再从顶部选择项目。"
          : "请先从顶部选择项目；如需快速创建员工，也可直接点击“创建员工”。"
      : "输入你的问题，按 Enter 发送，Shift + Enter 换行。支持粘贴图片。",
);
const composerHintText = computed(() => {
  if (!hasAccessibleProjects.value) {
    return activeComposerAssistMeta.value?.id === "employee_create"
      ? "当前将直接生成员工草稿，无需选择项目"
      : ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
        ? "当前是通用对话"
        : "暂无可访问项目";
  }
  if (!hasSelectedProject.value) {
    return activeComposerAssistMeta.value?.id === "employee_create"
      ? "当前将直接生成员工草稿，无需选择项目"
      : ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
        ? "当前是通用对话，Enter 发送"
        : "请先选择项目";
  }
  if (activeComposerAssistMeta.value) {
    return `${activeComposerAssistMeta.value.label} 已激活，Enter 发送`;
  }
  return "Enter 发送，Shift + Enter 换行";
});
const shortThreadId = computed(() => {
  const value = String(externalAgentInfo.value.thread_id || "").trim();
  return value ? value.slice(0, 8) : "";
});
const terminalPanelStatusText = computed(() => {
  if (!isExternalAgentMode.value) return "未启用";
  if (terminalPanelStatus.value === "error") return "异常";
  if (chatLoading.value || terminalPanelStatus.value === "running") {
    return "运行中";
  }
  if (externalAgentWarmupLoading.value) return "预热中";
  if (terminalPanelStatus.value === "ready" || externalAgentInfo.value.ready) {
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
  return [`# ${command}`, cwd ? `# cwd ${cwd}` : "", "# 等待外部 Agent 新请求…"]
    .filter(Boolean)
    .join("\n");
});
function extractTerminalApprovalPrompt(rawText) {
  const raw = String(rawText || "");
  const lowered = raw.toLowerCase();
  const hasOnceChoice =
    lowered.includes("approve once") ||
    lowered.includes("allow once") ||
    lowered.includes("approve for this request") ||
    lowered.includes("allow for this request");
  const hasSessionChoice =
    lowered.includes("approve this session") ||
    lowered.includes("allow this session") ||
    lowered.includes("approve for this session") ||
    lowered.includes("allow for this session");
  const hasRejectChoice =
    lowered.includes("cancel") ||
    lowered.includes("reject") ||
    lowered.includes("deny");
  const hasApprovalContext =
    lowered.includes("run the tool") ||
    lowered.includes("mcp server") ||
    lowered.includes("allow this action") ||
    lowered.includes("approval");
  if (
    !(
      hasApprovalContext &&
      hasOnceChoice &&
      hasSessionChoice &&
      hasRejectChoice
    )
  ) {
    return null;
  }
  const toolMatch = raw.match(/run the tool "([^"]+)"/i);
  const serverMatch = raw.match(/the ([a-z0-9_-]+) mcp server/i);
  const toolName = String(toolMatch?.[1] || "").trim();
  const serverName = String(serverMatch?.[1] || "").trim();
  const titleParts = [];
  if (serverName) titleParts.push(serverName);
  if (toolName) titleParts.push(toolName);
  return {
    key: raw,
    title:
      titleParts.length > 0
        ? `检测到审批请求：${titleParts.join(" / ")}`
        : "检测到审批请求",
    description: "该工具调用需要确认后才会继续执行。",
    message: clipText(raw, 1200),
  };
}
const terminalApprovalPromptFromOutput = computed(() =>
  extractTerminalApprovalPrompt(terminalPanelText.value),
);
const terminalApprovalPrompt = computed(
  () =>
    terminalApprovalPromptFromOutput.value ||
    terminalApprovalFallbackPrompt.value,
);

function clearTerminalApprovalFallback() {
  if (terminalApprovalFallbackTimer !== null) {
    window.clearTimeout(terminalApprovalFallbackTimer);
    terminalApprovalFallbackTimer = null;
  }
  terminalApprovalFallbackPrompt.value = null;
}

function setTerminalApprovalPrompt(payload) {
  const key = String(payload?.key || "").trim();
  if (!key) return;
  terminalApprovalFallbackPrompt.value = {
    key,
    title: String(payload?.title || "检测到审批请求").trim(),
    description: String(
      payload?.description || "终端请求确认后才会继续执行。",
    ).trim(),
    message: String(payload?.message || "").trim(),
  };
  terminalApprovalDialogVisible.value = true;
}

function scheduleTerminalApprovalFallback(requestMeta) {
  clearTerminalApprovalFallback();
  const requestId =
    String(requestMeta?.requestId || "").trim() || `${Date.now()}`;
  const toolName = String(requestMeta?.lastToolName || "").trim();
  terminalApprovalFallbackTimer = window.setTimeout(() => {
    if (terminalApprovalPromptFromOutput.value) return;
    setTerminalApprovalPrompt({
      key: `fallback:${requestId}:${toolName || "approval"}`,
      title: toolName ? `检测到审批请求：${toolName}` : "检测到审批请求",
      description:
        "真实终端已进入审批等待状态；如果原始提示未同步到页面，可直接在这里继续。",
    });
  }, 1200);
}

const availableModels = computed(() => {
  const selected = (providers.value || []).find(
    (item) => item.id === selectedProviderId.value,
  );
  return normalizeProviderModelNames(selected, modelTypeOptions.value);
});
const providerModelGroups = computed(() =>
  (providers.value || [])
    .map((provider) => {
      const providerId = String(provider?.id || "").trim();
      const providerLabel = String(
        provider?.name || providerId || "未命名供应商",
      ).trim();
      const models = normalizeProviderModelConfigs(
        provider,
        modelTypeOptions.value,
      );
      return {
        providerId,
        label: providerLabel,
        options: models.map((item) => ({
          value: `${providerId}::${item.name}`,
          modelName: item.name,
          modelType: item.model_type,
          modelTypeLabel:
            modelTypeMetaMap.value.get(item.model_type)?.label || "文本生成",
          providerId,
          providerLabel,
          label: `${item.name} · ${providerLabel}`,
        })),
      };
    })
    .filter((group) => group.providerId && group.options.length),
);
const selectedModelOptionValue = computed({
  get() {
    const providerId = String(selectedProviderId.value || "").trim();
    const modelName = String(selectedModelName.value || "").trim();
    if (!providerId || !modelName) return "";
    return `${providerId}::${modelName}`;
  },
  set(value) {
    const normalized = String(value || "").trim();
    if (!normalized) {
      selectedProviderId.value = "";
      selectedModelName.value = "";
      return;
    }
    const separatorIndex = normalized.indexOf("::");
    if (separatorIndex < 0) return;
    selectedProviderId.value = normalized.slice(0, separatorIndex);
    selectedModelName.value = normalized.slice(separatorIndex + 2);
  },
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
const promptsChatToolMap = computed(() => {
  const toolMap = {};
  for (const item of runtimeExternalTools.value) {
    const source = String(item?.module_source || "")
      .trim()
      .toLowerCase();
    const moduleName = String(item?.module_name || "")
      .trim()
      .toLowerCase();
    const remoteToolName = String(item?.remote_tool_name || "").trim();
    const toolName = String(item?.tool_name || "").trim();
    if (!toolName || !remoteToolName) continue;
    if (source !== "system_config") continue;
    if (!["prompts.chat", "prompts-chat"].includes(moduleName)) continue;
    toolMap[remoteToolName] = toolName;
  }
  return toolMap;
});
const composerAssistActions = computed(() => {
  const toolMap = promptsChatToolMap.value;
  const actions = [];
  actions.push({
    id: "employee_create",
    icon: "employee",
    label: "创建员工",
    shortDesc: "描述职责，自动创建员工",
    activeText:
      "本轮会优先调用系统能力检索与已接入 MCP 能力，完善技能和规则建议，并在返回草稿后自动创建员工。",
    seedText:
      "我要创建一个新员工，主要负责【在这里补充角色职责】。请优先结合系统能力库和已接入的 MCP 能力，整理出合适的技能、规则和工作方式建议，并输出成可直接创建的员工草稿，系统会在你输出后自动创建员工并绑定相关能力。",
    toolNames: [
      toolMap.search_skills,
      toolMap.get_skill,
      toolMap.search_prompts,
      toolMap.get_prompt,
      toolMap.improve_prompt,
    ].filter(Boolean),
    promptOnly: true,
    instruction:
      "请先调用当前可用的系统能力检索工具和 MCP 能力，补全最合适的技能、规则建议与工作流，再把用户需求整理成一个可直接创建的 AI 员工草稿；输出先给简短说明，最后必须附带一个严格 JSON 的 ```employee-draft``` 代码块。若从 prompts.chat 或其他外部能力中提炼出可直接落地的规则，请写入 rule_drafts 数组（title、domain、content，可选 source_label、source_url）；系统会据此创建本地规则并绑定到员工身上。",
  });
  if (toolMap.search_prompts || toolMap.get_prompt) {
    actions.push({
      id: "prompt_search",
      icon: "search",
      label: "搜提示词",
      shortDesc: "先搜参考再创作",
      activeText: "本轮会优先搜索已接入的提示词库作为创作参考。",
      seedText:
        "我想做一个关于【在这里补充任务/场景】的提示词，请先搜索相关参考，再帮我整理成适合当前场景的最终版本。",
      toolNames: [toolMap.search_prompts, toolMap.get_prompt].filter(Boolean),
      instruction:
        "请优先调用当前可用的提示词检索工具搜索相关提示词；如有合适候选，再调用详情工具读取细节，然后基于检索结果完成创作。",
    });
  }
  if (toolMap.improve_prompt) {
    actions.push({
      id: "prompt_improve",
      icon: "improve",
      label: "优化提示词",
      shortDesc: "把草稿升级成成品",
      activeText: "本轮会优先调用已接入的提示词增强能力来优化你的草稿。",
      seedText:
        "请把下面这段基础提示词优化成结构清晰、可直接使用的高质量版本：\n\n【把你的草稿写在这里】",
      toolNames: [toolMap.improve_prompt],
      instruction:
        "请优先调用当前可用的提示词增强能力强化用户输入，并输出最终可直接复制使用的成品提示词。",
    });
  }
  if (toolMap.search_skills || toolMap.get_skill) {
    actions.push({
      id: "skill_search",
      icon: "skill",
      label: "找技能模板",
      shortDesc: "先找技能再生成",
      activeText: "本轮会优先搜索已接入的技能模板库作为创作依据。",
      seedText:
        "我想完成【在这里补充任务/场景】，请先搜索合适的 Agent Skill / 技能模板，再帮我整理成可执行方案或提示词。",
      toolNames: [toolMap.search_skills, toolMap.get_skill].filter(Boolean),
      instruction:
        "请优先调用当前可用的技能检索工具搜索相关技能；如有高匹配项，再调用详情工具获取细节，并基于结果完成输出。",
    });
  }
  return actions;
});
const activeComposerAssistMeta = computed(
  () =>
    composerAssistActions.value.find(
      (item) => item.id === String(activeComposerAssist.value || "").trim(),
    ) || null,
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
const projectSwitcherRef = ref(null);
const draftText = ref("");
const editorComposing = ref(false);
const uploadFiles = ref([]);
const inputFocused = ref(false);
const isDragging = ref(false);
let autoSaveTimer = null;
let lastAutoSavedFingerprint = "";
let highlightedMessageTimer = null;
const projectSwitcherMenuWidth = ref(0);
const CHAT_HISTORY_PAGE_SIZE = 120;
const chatHistoryLoadedCount = ref(0);
const chatHistoryLoadingMore = ref(false);
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

function syncProjectSwitcherMenuWidth() {
  nextTick(() => {
    const element = projectSwitcherRef.value;
    const width = Number(element?.offsetWidth || 0);
    if (width > 0) {
      projectSwitcherMenuWidth.value = width;
    }
  });
}

const projectSwitcherMenuStyle = computed(() => {
  const width = Number(projectSwitcherMenuWidth.value || 0);
  if (!width) return {};
  return {
    width: `${width}px`,
    minWidth: `${width}px`,
    maxWidth: "calc(100vw - 24px)",
  };
});

function chatSessionStorageKey(projectId) {
  const normalized = String(projectId || "").trim();
  return normalized ? `project_chat_session_${normalized}` : "";
}

function rememberChatSession(projectId, sessionId) {
  const key = chatSessionStorageKey(projectId);
  if (!key) return;
  const normalized = String(sessionId || "").trim();
  if (normalized) {
    localStorage.setItem(key, normalized);
  } else {
    localStorage.removeItem(key);
  }
}

function restoreChatSession(projectId) {
  const key = chatSessionStorageKey(projectId);
  if (!key) return "";
  return String(localStorage.getItem(key) || "").trim();
}

function clearChatSessionMemory(projectId) {
  const key = chatSessionStorageKey(projectId);
  if (key) {
    localStorage.removeItem(key);
  }
}

function normalizeChatSession(item) {
  return {
    id: String(item?.id || "").trim(),
    title: String(item?.title || "新对话").trim() || "新对话",
    preview: String(item?.preview || "").trim(),
    message_count: Number(item?.message_count || 0),
    created_at: String(item?.created_at || "").trim(),
    updated_at: String(item?.updated_at || "").trim(),
    last_message_at: String(item?.last_message_at || "").trim(),
  };
}

const chatHistoryHasMore = computed(() => {
  const total = Number(currentChatSession.value?.message_count || 0);
  if (total > 0) {
    return chatHistoryLoadedCount.value < total;
  }
  return chatHistoryLoadedCount.value >= CHAT_HISTORY_PAGE_SIZE;
});

function formatChatSessionMeta(session) {
  const count = Number(session?.message_count || 0);
  const time = formatChatSessionTime(
    session?.last_message_at ||
      session?.updated_at ||
      session?.created_at ||
      "",
  );
  return `${count} 条 · ${time}`;
}

function formatChatSessionTime(value) {
  return formatRelativeDateTime(value, { fallback: "刚刚" });
}

function resolveChatSessionGroupLabel(session) {
  const source = String(
    session?.last_message_at ||
      session?.updated_at ||
      session?.created_at ||
      "",
  ).trim();
  return formatDateGroupLabel(source, { fallback: "更早" });
}

function extractEmployeeDraftPayload(text) {
  const content = String(text || "");
  const match = content.match(EMPLOYEE_DRAFT_BLOCK_RE);
  if (!match) return null;
  try {
    const parsed = JSON.parse(String(match[1] || "").trim());
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function stripEmployeeDraftBlock(text) {
  const content = String(text || "");
  if (!content) return "";
  return content.replace(EMPLOYEE_DRAFT_BLOCK_RE, "").trim();
}

function normalizeEmployeeDraftPayload(raw) {
  const item = raw && typeof raw === "object" ? raw : {};
  return {
    name: String(item.name || "").trim(),
    description: String(item.description || "").trim(),
    goal: String(item.goal || "").trim(),
    industry: String(item.industry || "").trim(),
    source_filters: normalizeStringList(item.source_filters || [], 8),
    tone: String(item.tone || "professional").trim() || "professional",
    verbosity: String(item.verbosity || "concise").trim() || "concise",
    language: String(item.language || "zh-CN").trim() || "zh-CN",
    skills: normalizeStringList(
      [
        ...(Array.isArray(item.skills) ? item.skills : []),
        ...(Array.isArray(item.skill_ids) ? item.skill_ids : []),
        ...(Array.isArray(item.skill_names) ? item.skill_names : []),
        ...(Array.isArray(item.skill_keywords) ? item.skill_keywords : []),
      ],
      20,
    ),
    rule_ids: normalizeStringList(item.rule_ids || [], 30),
    rule_titles: normalizeStringList(item.rule_titles || [], 30),
    rule_domains: normalizeStringList(
      [
        ...(Array.isArray(item.rule_domains) ? item.rule_domains : []),
        ...(Array.isArray(item.rule_categories) ? item.rule_categories : []),
      ],
      20,
    ),
    rule_drafts: (Array.isArray(item.rule_drafts) ? item.rule_drafts : [])
      .map((draft) => ({
        title: String(draft?.title || "").trim(),
        domain: String(draft?.domain || "").trim(),
        content: String(draft?.content || "").trim(),
        source_label: String(draft?.source_label || "").trim(),
        source_url: String(draft?.source_url || "").trim(),
      }))
      .filter((draft) => draft.title || draft.domain || draft.content),
    style_hints: normalizeStringList(item.style_hints || [], 12),
    default_workflow: normalizeStringList(item.default_workflow || [], 12),
    tool_usage_policy: String(item.tool_usage_policy || "").trim(),
    memory_scope: String(item.memory_scope || "project").trim() || "project",
    memory_retention_days: Number(item.memory_retention_days || 90),
  };
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
        ? item.status_lines
            .map((line) => String(line || "").trim())
            .filter(Boolean)
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
    file_review_status:
      String(source.file_review_status || "not_required").trim() ||
      "not_required",
  };
}

function getFileReviewStatusMeta(status) {
  const normalized = String(status || "not_required").trim();
  if (normalized === "pending") {
    return {
      label: "待审查",
      type: "warning",
      text: "检测到工作区文件改动，等待人工确认。",
    };
  }
  if (normalized === "approved") {
    return {
      label: "已通过",
      type: "success",
      text: "文件改动已人工确认，允许继续保留。",
    };
  }
  if (normalized === "rejected") {
    return {
      label: "已拒绝",
      type: "danger",
      text: "文件改动未通过人工确认，请回看 diff 后再处理。",
    };
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
  const lines = [
    String(eventData?.message || "检测到高风险操作，需要确认后继续。"),
  ];
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
  row.content =
    `${row.content || ""}\n\n> ⛔ 检测到高风险操作，等待审批...`.trim();
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
  const diffSummary =
    eventData?.diff_summary && typeof eventData.diff_summary === "object"
      ? eventData.diff_summary
      : {};
  const lines = [
    String(
      eventData?.message || "检测到文件改动，请先确认是否允许保留本次变更。",
    ),
  ];
  const changedFileCount = Number(diffSummary?.changed_file_count || 0);
  if (changedFileCount > 0) {
    lines.push(`改动文件数：${changedFileCount}`);
  }
  const diffStat = String(diffSummary?.diff_stat || "").trim();
  const statusLines = Array.isArray(diffSummary?.status_lines)
    ? diffSummary.status_lines
        .map((line) => String(line || "").trim())
        .filter(Boolean)
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
    after_diff_summary:
      eventData?.diff_summary || row.audit?.after_diff_summary || {},
    file_review_status: "pending",
  });
  row.content =
    `${row.content || ""}\n> 📝 检测到文件改动，等待审查确认`.trim();
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
    command_source:
      String(source.command_source || "missing").trim() || "missing",
    runtime_model_name:
      String(
        source.runtime_model_name || source.model_name || "codex-cli",
      ).trim() || "codex-cli",
    exact_model_name: String(source.exact_model_name || "").trim(),
    execution_mode:
      String(source.execution_mode || "local_connector").trim() ||
      "local_connector",
    runner_url: String(source.runner_url || "").trim(),
    materialized_by: String(source.materialized_by || "").trim(),
    available: Boolean(source.available),
    installed: Boolean(source.installed ?? source.available),
    implemented: Boolean(source.implemented ?? true),
    reason: String(source.reason || "").trim(),
    supports_terminal_mirror: Boolean(source.supports_terminal_mirror ?? true),
    supports_workspace_write: Boolean(source.supports_workspace_write ?? true),
    ready: Boolean(source.ready),
    session_id: String(
      source.session_id || source.agent_session_id || "",
    ).trim(),
    thread_id: String(source.thread_id || "").trim(),
    sandbox_mode:
      String(source.sandbox_mode || "workspace-write").trim() ||
      "workspace-write",
    workspace_path: String(source.workspace_path || "").trim(),
    local_connector_id: String(source.local_connector_id || "").trim(),
    local_connector_name: String(source.local_connector_name || "").trim(),
    local_connector_online: Boolean(source.local_connector_online),
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
    workspace_access:
      source.workspace_access && typeof source.workspace_access === "object"
        ? {
            configured: Boolean(source.workspace_access.configured),
            exists: Boolean(source.workspace_access.exists),
            is_dir: Boolean(source.workspace_access.is_dir),
            read_ok: Boolean(source.workspace_access.read_ok),
            write_ok: Boolean(source.workspace_access.write_ok),
            source: String(source.workspace_access.source || "").trim(),
            sandbox_mode:
              String(
                source.workspace_access.sandbox_mode ||
                  source.sandbox_mode ||
                  "workspace-write",
              ).trim() || "workspace-write",
            reason: String(source.workspace_access.reason || "").trim(),
          }
        : {
            configured: false,
            exists: false,
            is_dir: false,
            read_ok: false,
            write_ok: false,
            source: "",
            sandbox_mode:
              String(source.sandbox_mode || "workspace-write").trim() ||
              "workspace-write",
            reason: "",
          },
    sandbox_modes: normalizeStringList(
      source.sandbox_modes || ["read-only", "workspace-write"],
      10,
    ),
    agent_types: Array.isArray(source.agent_types)
      ? source.agent_types.map((item) => ({
          agent_type: String(item?.agent_type || "codex_cli").trim(),
          label: String(item?.label || item?.agent_type || "外部 Agent").trim(),
          available: Boolean(item?.available),
          installed: Boolean(item?.installed ?? item?.available),
          implemented: Boolean(item?.implemented ?? true),
          reason: String(item?.reason || "").trim(),
        }))
      : [],
  };
}

function normalizeEffectiveTools(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => ({
      tool_name: String(item?.tool_name || "").trim(),
      source: String(item?.source || "project_tool").trim() || "project_tool",
      description: String(item?.description || "").trim(),
    }))
    .filter((item) => item.tool_name)
    .slice(0, 24);
}

function effectiveToolSourceLabel(source) {
  return (
    {
      external_mcp: "外部 MCP",
      system_mcp: "系统 MCP",
      project_skill: "项目技能",
      builtin: "内置",
      local_connector: "本地连接器",
      project_tool: "项目工具",
    }[String(source || "").trim()] || "工具"
  );
}

function effectiveToolSourceTagType(source) {
  return (
    {
      external_mcp: "success",
      system_mcp: "warning",
      project_skill: "",
      builtin: "info",
      local_connector: "danger",
      project_tool: "",
    }[String(source || "").trim()] || ""
  );
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
  const sandboxModeExplicit = Boolean(
    source.connector_sandbox_mode_explicit ??
    source.external_agent_sandbox_mode_explicit,
  );
  const sandboxMode = String(
    source.connector_sandbox_mode ||
      source.external_agent_sandbox_mode ||
      CHAT_SETTINGS_DEFAULTS.connector_sandbox_mode,
  )
    .trim()
    .toLowerCase();
  const normalizedSandboxMode =
    sandboxMode === "read-only" || sandboxMode === "workspace-write"
      ? sandboxMode
      : CHAT_SETTINGS_DEFAULTS.connector_sandbox_mode;
  const effectiveSandboxMode =
    normalizedSandboxMode === "read-only" && !sandboxModeExplicit
      ? CHAT_SETTINGS_DEFAULTS.connector_sandbox_mode
      : normalizedSandboxMode;
  const coordinationMode = String(
    source.employee_coordination_mode ||
      CHAT_SETTINGS_DEFAULTS.employee_coordination_mode,
  )
    .trim()
    .toLowerCase();
  return {
    ...CHAT_SETTINGS_DEFAULTS,
    ...source,
    chat_mode:
      chatMode === "system" ? "system" : CHAT_SETTINGS_DEFAULTS.chat_mode,
    connector_sandbox_mode: effectiveSandboxMode,
    connector_sandbox_mode_explicit: sandboxModeExplicit,
    local_connector_id: String(
      source.local_connector_id || CHAT_SETTINGS_DEFAULTS.local_connector_id,
    ).trim(),
    connector_workspace_path: String(
      source.connector_workspace_path ||
        CHAT_SETTINGS_DEFAULTS.connector_workspace_path,
    ).trim(),
    selected_employee_ids: selectedEmployeeIds,
    employee_coordination_mode:
      coordinationMode === "manual" ? "manual" : "auto",
    image_generate_four_views: coerceBooleanSetting(
      source.image_generate_four_views,
      CHAT_SETTINGS_DEFAULTS.image_generate_four_views,
    ),
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

function normalizeDictionaryBackedChatSettings(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  const next = { ...source };
  for (const parameterKey of listChatParameterKeys()) {
    next[parameterKey] = normalizeChatParameterValue(
      parameterKey,
      next[parameterKey] ?? getRuntimeChatParameterDefaultValue(parameterKey),
      getChatParameterDictionaryEntry(parameterKey).options || [],
    );
  }
  return next;
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
  if (
    !String(selectedProjectId.value || "").trim() &&
    activeComposerAssistMeta.value?.id !== "employee_create" &&
    !ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
  ) {
    return false;
  }
  if (String(draftText.value || "").trim()) return true;
  if (isExternalAgentMode.value) return false;
  if (!String(selectedProjectId.value || "").trim()) {
    return (
      activeComposerAssistMeta.value?.id === "employee_create" ||
      ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
    );
  }
  return uploadFiles.value.length > 0;
});

const isProjectOptionalEmployeeCreate = computed(
  () =>
    !String(selectedProjectId.value || "").trim() &&
    activeComposerAssistMeta.value?.id === "employee_create",
);

const isComposerDisabled = computed(() => {
  if (chatLoading.value) return true;
  if (isProjectOptionalEmployeeCreate.value) return false;
  if (!ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT) {
    return !selectedProjectId.value;
  }
  return false;
});

function formatContent(text) {
  const displayText = stripEmployeeDraftBlock(text);
  if (!displayText) return "";
  try {
    return marked.parse(displayText, { renderer: markdownRenderer });
  } catch (e) {
    return displayText;
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
  const line = String(text || "").trim();
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
  terminalPanelStatus.value = "idle";
  terminalPanelInput.value = "";
  terminalMirrorConnected.value = false;
  activeTerminalMirrorAssistantIndex.value = -1;
  terminalApprovalDialogVisible.value = false;
  terminalApprovalHandledKey.value = "";
  clearTerminalApprovalFallback();
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
    external_agent_type: String(
      projectChatSettings.value.external_agent_type || "codex_cli",
    ).trim(),
    external_agent_sandbox_mode:
      projectChatSettings.value.external_agent_sandbox_mode ||
      "workspace-write",
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
  await sendTerminalMirrorContent(content);
  terminalPanelInput.value = "";
}

async function sendTerminalMirrorContent(content, options = {}) {
  const normalizedContent = String(content || "").trim();
  if (!normalizedContent) return;
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return;
  const client = await ensureWsClient(projectId);
  if (!terminalMirrorConnected.value) {
    await startTerminalMirror();
  }
  if (options?.echo !== false) {
    appendTerminalPanelLine(`› ${normalizedContent}`);
  }
  client.send({
    type: "terminal_mirror_input",
    request_id: `mirror-input-${Date.now()}`,
    chat_mode: "external_agent",
    external_agent_type: String(
      projectChatSettings.value.external_agent_type || "codex_cli",
    ).trim(),
    external_agent_sandbox_mode:
      projectChatSettings.value.external_agent_sandbox_mode ||
      "workspace-write",
    external_agent_sandbox_mode_explicit: true,
    content:
      options?.appendNewline === false
        ? normalizedContent
        : `${normalizedContent}\r`,
  });
}

async function sendTerminalApprovalChoice(choice) {
  const activePromptKey = String(
    terminalApprovalPrompt.value?.key || "",
  ).trim();
  if (activePromptKey) {
    terminalApprovalHandledKey.value = activePromptKey;
  }
  clearTerminalApprovalFallback();
  terminalApprovalDialogVisible.value = false;
  await sendTerminalMirrorContent(String(choice || "").trim());
  const activeRequestId = getActiveRequestId();
  if (activeRequestId) {
    const pending = pendingRequests.get(activeRequestId);
    if (pending?.awaitingTerminalApproval) {
      pending.awaitingTerminalApproval = false;
      pending.resolve(
        String(messages.value[pending.assistantIndex]?.content || "").trim(),
      );
    }
  }
}

function appendAssistantStatusNote(row, text) {
  if (!row) return;
  const note = String(text || "").trim();
  if (!note) return;
  const current = String(row.content || "").trim();
  if (!current) {
    row.content = note;
    return;
  }
  if (current.endsWith(note)) {
    return;
  }
  row.content = `${current}\n\n${note}`;
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

function isMcpApprovalCancelledMessage(value) {
  return String(value || "")
    .toLowerCase()
    .includes("user cancelled mcp tool call");
}

async function handoffExternalAgentRequestToTerminal(row, requestMeta) {
  if (!isExternalAgentMode.value || !row || !requestMeta) return false;
  const userPrompt = String(requestMeta.userPrompt || "").trim();
  if (!userPrompt || requestMeta.handoffTriggered) return false;
  requestMeta.handoffTriggered = true;
  terminalPanelStatus.value = "running";
  activeTerminalMirrorAssistantIndex.value = Number(
    requestMeta.assistantIndex ?? -1,
  );
  appendTerminalLog(
    row,
    "# 检测到 MCP 写操作需要交互审批，已切换到真实终端继续执行",
  );
  try {
    await sendTerminalMirrorContent(userPrompt);
    scheduleTerminalApprovalFallback(requestMeta);
    appendAssistantStatusNote(
      row,
      "> ⏳ 已切换到交互审批模式，请在弹出的确认框里继续。",
    );
    scrollToBottom();
    return true;
  } catch (err) {
    appendTerminalLog(
      row,
      `! 自动切换真实终端失败：${String(err?.message || err || "未知错误").trim()}`,
    );
    clearTerminalApprovalFallback();
    return false;
  }
}

function terminalLogLines(item) {
  return Array.isArray(item?.terminalLog)
    ? item.terminalLog.map((line) => String(line || "").trim()).filter(Boolean)
    : [];
}

function formatTerminalLogs(item) {
  return terminalLogLines(item).join("\n");
}

function messageRoleName(item) {
  if (String(item?.role || "").trim() === "user") return "You";
  if (String(item?.displayMode || "").trim() === "terminal") {
    return externalAgentDisplayLabel.value;
  }
  return "Assistant";
}

function avatarLabel(item) {
  if (String(item?.role || "").trim() === "user") return "U";
  const source = String(
    String(item?.displayMode || "").trim() === "terminal"
      ? externalAgentDisplayLabel.value
      : "AI",
  ).trim();
  return source.slice(0, 1).toUpperCase() || "A";
}

function buildMessageMarkdown(item, options = {}) {
  const includeProcess = Boolean(options?.includeProcess);
  const parts = [];
  const content = String(item?.content || "").trim();
  const logs = formatTerminalLogs(item).trim();

  if (includeProcess && logs) {
    parts.push(["## 思考过程", "```text", logs, "```"].join("\n"));
  }
  if (content) {
    parts.push(content);
  } else if (!parts.length && logs) {
    parts.push(["```text", logs, "```"].join("\n"));
  }
  return parts.join("\n\n").trim();
}

async function writeClipboardText(text) {
  const value = String(text || "");
  if (!value.trim()) {
    throw new Error("empty");
  }
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!ok) {
    throw new Error("copy_failed");
  }
}

function hasMessageCopyableContent(item, options = {}) {
  const includeProcess = Boolean(options?.includeProcess);
  const content = String(item?.content || "").trim();
  if (content) return true;
  if (includeProcess) {
    return terminalLogLines(item).length > 0;
  }
  return false;
}

async function copyMessageMarkdown(item, options = {}) {
  const content = buildMessageMarkdown(item, options);
  if (!content) {
    ElMessage.warning("当前消息暂无可复制内容");
    return;
  }
  try {
    await writeClipboardText(content);
    ElMessage.success(
      options?.includeProcess
        ? "已复制 Markdown（含思考过程）"
        : "已复制 Markdown",
    );
  } catch {
    ElMessage.error("复制失败");
  }
}

function createLocalMessageId() {
  return `chat-local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function resolveMessageSource(messageIndex) {
  const normalizedIndex = Number(messageIndex);
  if (!Number.isInteger(normalizedIndex) || normalizedIndex < 0) return null;
  const current = messages.value[normalizedIndex];
  if (!current) return null;
  if (String(current?.role || "").trim() === "user") {
    return { index: normalizedIndex, item: current };
  }
  for (let cursor = normalizedIndex - 1; cursor >= 0; cursor -= 1) {
    const candidate = messages.value[cursor];
    if (String(candidate?.role || "").trim() === "user") {
      return { index: cursor, item: candidate };
    }
  }
  return null;
}

function messageHasReplayUnsupportedAssets(item) {
  return (
    (Array.isArray(item?.attachments) && item.attachments.length > 0) ||
    (Array.isArray(item?.images) && item.images.length > 0)
  );
}

function canReplayMessageSource(messageIndex) {
  const source = resolveMessageSource(messageIndex);
  if (!source) return false;
  if (!String(source.item?.content || "").trim()) return false;
  if (messageHasReplayUnsupportedAssets(source.item)) return false;
  return true;
}

function canDeleteMessage(item, messageIndex) {
  const normalizedIndex = Number(messageIndex);
  if (!Number.isInteger(normalizedIndex) || normalizedIndex < 0) return false;
  if (!item) return false;
  if (!String(currentChatSessionId.value || "").trim()) return false;
  if (String(item?.role || "").trim() === "user") {
    return Boolean(String(item?.id || "").trim());
  }
  return Boolean(resolveMessageSource(normalizedIndex));
}

function resolveDeleteTarget(messageIndex) {
  const normalizedIndex = Number(messageIndex);
  if (!Number.isInteger(normalizedIndex) || normalizedIndex < 0) return null;
  const item = messages.value[normalizedIndex];
  if (!item) return null;
  const role = String(item?.role || "").trim();
  if (role === "user") {
    const messageId = String(item?.id || "").trim();
    if (!messageId) return null;
    return {
      mode: "truncate",
      item,
      index: normalizedIndex,
      messageId,
    };
  }
  const source = resolveMessageSource(normalizedIndex);
  const sourceMessageId = String(source?.item?.id || "").trim();
  if (!source || !sourceMessageId) return null;
  return {
    mode: "truncate",
    item,
    index: normalizedIndex,
    messageId: sourceMessageId,
    sourceIndex: source.index,
  };
}

function getDeleteActionTooltip(item) {
  const role = String(item?.role || "").trim();
  return role === "user" ? "删除此条及后续" : "删除这轮对话";
}

function buildDeleteMessageConfirmText(item) {
  const role = String(item?.role || "").trim();
  if (role === "user") {
    return "确认删除这条消息及其后续内容吗？删除后不可恢复。";
  }
  return "确认删除这条 AI 回复所在整轮对话吗？会同时删除对应提问与后续内容。";
}

function applyDeleteTargetLocally(target) {
  if (!target) return;
  const role = String(target?.item?.role || "").trim();
  const sliceIndex =
    role === "user"
      ? Number(target?.index)
      : Number(target?.sourceIndex ?? target?.index);
  if (!Number.isInteger(sliceIndex) || sliceIndex < 0) return;
  messages.value = messages.value.slice(0, sliceIndex);
  chatHistoryLoadedCount.value = messages.value.length;
}

function buildDeleteSuccessText(item) {
  const role = String(item?.role || "").trim();
  return role === "user" ? "消息已删除" : "该轮对话已删除";
}

function buildDeleteErrorText(item) {
  const role = String(item?.role || "").trim();
  return role === "user" ? "删除消息失败" : "删除该轮对话失败";
}

function resetInlineMessageEdit() {
  inlineEditingMessageIndex.value = -1;
  inlineEditingMessageId.value = "";
  inlineEditingDraft.value = "";
  inlineEditingBusy.value = false;
}

function isInlineEditingMessage(messageIndex) {
  const normalizedIndex = Number(messageIndex);
  if (!Number.isInteger(normalizedIndex) || normalizedIndex < 0) return false;
  if (normalizedIndex !== inlineEditingMessageIndex.value) return false;
  const current = messages.value[normalizedIndex];
  if (!current) return false;
  return (
    String(current?.id || "").trim() ===
    String(inlineEditingMessageId.value || "").trim()
  );
}

function focusInlineMessageEditor() {
  nextTick(() => {
    const editorRoot = messagesContainer.value?.querySelector?.(
      `[data-inline-editor-id="${inlineEditingMessageId.value}"]`,
    );
    if (editorRoot?.scrollIntoView) {
      editorRoot.scrollIntoView({
        block: "center",
        behavior: "smooth",
      });
    }
    const textarea = editorRoot?.querySelector?.("textarea");
    if (!textarea) return;
    textarea.focus();
    const textLength = String(textarea.value || "").length;
    if (typeof textarea.setSelectionRange === "function") {
      textarea.setSelectionRange(textLength, textLength);
    }
  });
}

function getInlineEditingSource() {
  if (inlineEditingMessageIndex.value < 0) return null;
  const current = messages.value[inlineEditingMessageIndex.value];
  if (!current) return null;
  if (
    String(current?.id || "").trim() !==
    String(inlineEditingMessageId.value || "").trim()
  ) {
    return null;
  }
  return {
    index: inlineEditingMessageIndex.value,
    item: current,
  };
}

function normalizeInlineEditingDraft() {
  return String(inlineEditingDraft.value || "").trim();
}

async function truncateConversationFromSource(source) {
  if (!source) return;
  const projectId = String(selectedProjectId.value || "").trim();
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  if (projectId && chatSessionId) {
    const messageId = String(source.item?.id || "").trim();
    if (!messageId) {
      throw new Error("当前消息尚未保存完成，请稍后再试");
    }
    await api.post(
      `/projects/${encodeURIComponent(projectId)}/chat/history/truncate`,
      {
        chat_session_id: chatSessionId,
        message_id: messageId,
      },
    );
  }
  messages.value = messages.value.slice(0, source.index);
  chatHistoryLoadedCount.value = messages.value.length;
}

async function deleteMessageAt(messageIndex) {
  if (chatLoading.value) {
    ElMessage.warning("当前回答进行中，暂时不能删除消息");
    return;
  }
  const normalizedIndex = Number(messageIndex);
  if (!Number.isInteger(normalizedIndex) || normalizedIndex < 0) return;
  const item = messages.value[normalizedIndex];
  const target = resolveDeleteTarget(normalizedIndex);
  if (!item || !target || !canDeleteMessage(item, normalizedIndex)) {
    ElMessage.warning("当前消息尚未保存完成，请稍后再试");
    return;
  }
  try {
    await ElMessageBox.confirm(
      buildDeleteMessageConfirmText(item),
      "删除消息",
      {
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  const projectId = String(selectedProjectId.value || "").trim();
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  try {
    await api.post(
      `/projects/${encodeURIComponent(projectId)}/chat/history/truncate`,
      {
        chat_session_id: chatSessionId,
        message_id: target.messageId,
      },
    );
    applyDeleteTargetLocally(target);
    ElMessage.success(buildDeleteSuccessText(item));
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || buildDeleteErrorText(item));
  }
}

async function openInlineMessageEditor(messageIndex) {
  if (chatLoading.value) {
    ElMessage.warning("当前回答进行中，暂时不能编辑历史消息");
    return;
  }
  const source = resolveMessageSource(messageIndex);
  if (!source) {
    ElMessage.warning("未找到可编辑的原始用户消息");
    return;
  }
  if (messageHasReplayUnsupportedAssets(source.item)) {
    ElMessage.warning("带附件或图片的消息暂不支持编辑");
    return;
  }
  inlineEditingMessageIndex.value = source.index;
  inlineEditingMessageId.value = String(source.item?.id || "").trim();
  inlineEditingDraft.value = String(source.item?.content || "").trim();
  focusInlineMessageEditor();
}

async function replayMessageFromSource(messageIndex, options = {}) {
  if (chatLoading.value) {
    ElMessage.warning("当前回答进行中，暂时不能重新生成");
    return;
  }
  const source = resolveMessageSource(messageIndex);
  if (!source || !canReplayMessageSource(messageIndex)) {
    ElMessage.warning("当前消息暂不支持重新生成");
    return;
  }
  const nextPrompt = String(
    options?.message ?? source.item?.content ?? "",
  ).trim();
  if (!nextPrompt) {
    ElMessage.warning("消息不能为空");
    return;
  }
  try {
    await truncateConversationFromSource(source);
    draftText.value = nextPrompt;
    await doSend();
  } catch (err) {
    if (options?.throwOnError) {
      throw err;
    }
    ElMessage.error(err?.detail || err?.message || "重新生成失败");
  }
}

function cancelInlineMessageEdit() {
  resetInlineMessageEdit();
}

function applyInlineMessageEditToComposer() {
  const edited = normalizeInlineEditingDraft();
  if (!edited) {
    ElMessage.warning("消息不能为空");
    return;
  }
  draftText.value = edited;
  resetInlineMessageEdit();
  scrollToBottom();
  ElMessage.success("已填入输入框，可以继续修改后发送");
}

async function submitInlineMessageEditAndReplay() {
  if (inlineEditingBusy.value) return;
  const source = getInlineEditingSource();
  if (!source) {
    resetInlineMessageEdit();
    ElMessage.warning("当前消息不可编辑，请重新操作");
    return;
  }
  const edited = normalizeInlineEditingDraft();
  if (!edited) {
    ElMessage.warning("消息不能为空");
    return;
  }
  inlineEditingBusy.value = true;
  try {
    await replayMessageFromSource(source.index, {
      message: edited,
      throwOnError: true,
    });
    resetInlineMessageEdit();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "重新生成失败");
  } finally {
    inlineEditingBusy.value = false;
  }
}

function handleInlineMessageEditKeydown(event) {
  if (!event) return;
  if (event.key === "Escape") {
    event.preventDefault();
    cancelInlineMessageEdit();
    return;
  }
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    void submitInlineMessageEditAndReplay();
  }
}

function getMessageActions(item, messageIndex) {
  const actions = [];
  const role = String(item?.role || "").trim();
  if (role === "user" && canReplayMessageSource(messageIndex)) {
    actions.push({
      key: "edit_message",
      tooltip: "编辑",
      icon: EditPen,
    });
    actions.push({
      key: "edit_and_regenerate",
      tooltip: "编辑后重新生成",
      icon: RefreshRight,
    });
  }
  if (role !== "user" && canReplayMessageSource(messageIndex)) {
    actions.push({
      key: "regenerate",
      tooltip: "重新生成",
      icon: RefreshRight,
    });
    actions.push({
      key: "edit_and_regenerate",
      tooltip: "编辑后重新生成",
      icon: EditPen,
    });
  }
  if (hasMessageCopyableContent(item)) {
    actions.push({
      key: "copy_markdown",
      tooltip: role === "user" ? "复制消息" : "复制 Markdown",
      icon: DocumentCopy,
    });
  }
  if (
    role !== "user" &&
    hasMessageCopyableContent(item, { includeProcess: true }) &&
    terminalLogLines(item).length
  ) {
    actions.push({
      key: "copy_with_process",
      tooltip: "复制含过程",
      icon: Files,
    });
  }
  if (canSaveMessageAsMaterial(item)) {
    actions.push({
      key: "save_to_material_library",
      tooltip: "加入素材库",
      icon: CollectionTag,
    });
  }
  if (canDeleteMessage(item, messageIndex)) {
    actions.push({
      key: "delete_message",
      tooltip: getDeleteActionTooltip(item),
      icon: Delete,
    });
  }
  return actions;
}

function handleMessageAction(item, messageIndex, actionKey) {
  switch (String(actionKey || "").trim()) {
    case "edit_message":
      void openInlineMessageEditor(messageIndex);
      return;
    case "regenerate":
      void replayMessageFromSource(messageIndex);
      return;
    case "edit_and_regenerate":
      void openInlineMessageEditor(messageIndex);
      return;
    case "copy_markdown":
      copyMessageMarkdown(item);
      return;
    case "copy_with_process":
      copyMessageMarkdown(item, { includeProcess: true });
      return;
    case "save_to_material_library":
      void openMaterialDialog(item, messageIndex);
      return;
    case "delete_message":
      void deleteMessageAt(messageIndex);
      return;
    default:
      return;
  }
}

function buildCodePreviewTitle(language, content) {
  const normalizedLanguage = normalizeCodeLanguage(language);
  if (normalizedLanguage === "vue" || /<template[\s>]/i.test(content)) {
    return "Vue 组件预览";
  }
  if (normalizedLanguage === "html" || normalizedLanguage === "htm") {
    return "HTML 预览";
  }
  return "代码预览";
}

function extractSfcTemplate(content) {
  const match = String(content || "").match(
    /<template[^>]*>([\s\S]*?)<\/template>/i,
  );
  return String(match?.[1] || "").trim();
}

function extractSfcStyles(content) {
  const styles = [];
  const regex = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  for (const match of String(content || "").matchAll(regex)) {
    const text = String(match?.[1] || "").trim();
    if (text) styles.push(text);
  }
  return styles;
}

function extractSfcScript(content) {
  const setupMatch = String(content || "").match(
    /<script\b[^>]*setup[^>]*>([\s\S]*?)<\/script>/i,
  );
  if (setupMatch) return String(setupMatch[1] || "");
  const normalMatch = String(content || "").match(
    /<script\b[^>]*>([\s\S]*?)<\/script>/i,
  );
  return String(normalMatch?.[1] || "");
}

function collectScriptRefInitializers(scriptContent) {
  const refs = [];
  const regex =
    /const\s+([A-Za-z_$][\w$]*)\s*=\s*ref(?:<[^>]+>)?\s*\(([\s\S]*?)\)\s*(?:;|\n)/g;
  for (const match of String(scriptContent || "").matchAll(regex)) {
    const name = String(match?.[1] || "").trim();
    const expression = String(match?.[2] || "").trim();
    if (!name) continue;
    refs.push({ name, expression });
  }
  return refs;
}

function collectScriptReactiveInitializers(scriptContent) {
  const reactives = [];
  const regex =
    /const\s+([A-Za-z_$][\w$]*)\s*=\s*reactive\s*\((\{[\s\S]*?\})\s*\)\s*(?:;|\n)/g;
  for (const match of String(scriptContent || "").matchAll(regex)) {
    const name = String(match?.[1] || "").trim();
    const expression = String(match?.[2] || "").trim();
    if (!name) continue;
    reactives.push({ name, expression });
  }
  return reactives;
}

function collectScriptFunctionNames(scriptContent) {
  const names = new Set();
  const regex = /(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(/g;
  for (const match of String(scriptContent || "").matchAll(regex)) {
    const name = String(match?.[1] || "").trim();
    if (!name) continue;
    names.add(name);
  }
  return Array.from(names);
}

function collectTemplateModelPaths(template) {
  const paths = new Set();
  const regex = /v-model(?:\.[^=]+)?="([^"]+)"/g;
  for (const match of String(template || "").matchAll(regex)) {
    const path = String(match?.[1] || "").trim();
    if (!path) continue;
    paths.add(path);
  }
  return Array.from(paths);
}

function transformVueTemplateToStaticHtml(template) {
  let html = String(template || "").trim();
  if (!html) return "";

  html = html.replace(/<template[^>]*>|<\/template>/gi, "");
  html = html.replace(/<script[\s\S]*?<\/script>/gi, "");

  html = html.replace(/{{[\s\S]*?}}/g, "示例内容");
  html = html.replace(/\s(?:v-|:|@)[^=\s>]+(?:=(["'])[\s\S]*?\1)?/g, "");

  html = html.replace(
    /<el-form-item\b([^>]*)>/gi,
    '<div class="preview-form-item"$1>',
  );
  html = html.replace(/<\/el-form-item>/gi, "</div>");
  html = html.replace(/<el-form\b([^>]*)>/gi, '<form class="preview-form"$1>');
  html = html.replace(/<\/el-form>/gi, "</form>");
  html = html.replace(/<el-alert\b([^>]*)>/gi, '<div class="preview-alert"$1>');
  html = html.replace(/<\/el-alert>/gi, "</div>");
  html = html.replace(
    /<el-checkbox\b([^>]*)>/gi,
    '<label class="preview-checkbox"$1><input type="checkbox" />',
  );
  html = html.replace(/<\/el-checkbox>/gi, "</label>");
  html = html.replace(
    /<el-button\b([^>]*)>/gi,
    '<button type="button" class="preview-button"$1>',
  );
  html = html.replace(/<\/el-button>/gi, "</button>");
  html = html.replace(
    /<el-input-number\b([^>]*)\/>/gi,
    '<input type="number" class="preview-input" $1 />',
  );
  html = html.replace(/<el-input\b([^>]*)\/>/gi, (_match, attrs) => {
    const typeMatch = String(attrs || "").match(/\btype=(['"])(.*?)\1/i);
    const type = String(typeMatch?.[2] || "text").trim() || "text";
    return `<input class="preview-input" type="${escapeHtml(type)}" ${attrs || ""} />`;
  });
  html = html.replace(
    /<el-input\b([^>]*)>([\s\S]*?)<\/el-input>/gi,
    (_match, attrs) => {
      const typeMatch = String(attrs || "").match(/\btype=(['"])(.*?)\1/i);
      const type = String(typeMatch?.[2] || "text").trim() || "text";
      if (type === "textarea") {
        return `<textarea class="preview-textarea" ${attrs || ""}></textarea>`;
      }
      return `<input class="preview-input" type="${escapeHtml(type)}" ${attrs || ""} />`;
    },
  );
  html = html.replace(
    /<el-select\b([^>]*)>([\s\S]*?)<\/el-select>/gi,
    '<select class="preview-select"$1>$2</select>',
  );
  html = html.replace(
    /<el-option\b([^>]*)>([\s\S]*?)<\/el-option>/gi,
    (_match, attrs, inner) => {
      const labelMatch = String(attrs || "").match(/\blabel=(['"])(.*?)\1/i);
      const label = String(labelMatch?.[2] || inner || "选项").trim() || "选项";
      return `<option>${escapeHtml(label)}</option>`;
    },
  );
  html = html.replace(
    /<el-radio-group\b([^>]*)>/gi,
    '<div class="preview-radio-group"$1>',
  );
  html = html.replace(/<\/el-radio-group>/gi, "</div>");
  html = html.replace(
    /<el-radio\b([^>]*)>([\s\S]*?)<\/el-radio>/gi,
    '<label class="preview-radio"$1><input type="radio" />$2</label>',
  );
  html = html.replace(
    /<el-switch\b([^>]*)\/?>/gi,
    '<label class="preview-switch"$1><span class="preview-switch__track"></span></label>',
  );
  html = html.replace(/<el-icon\b[^>]*>[\s\S]*?<\/el-icon>/gi, "");

  html = html.replace(
    /<el-[a-z0-9-]+\b([^>]*)>/gi,
    '<div class="preview-block"$1>',
  );
  html = html.replace(/<\/el-[a-z0-9-]+>/gi, "</div>");

  html = html.replace(
    /\s(?:clearable|show-password|filterable|multiple|text|circle|plain|border|show-icon|destroy-on-close|closable)(?=[\s>])/gi,
    "",
  );
  return html;
}

function buildStaticVuePreviewHtml(template) {
  const html = transformVueTemplateToStaticHtml(template);
  if (!html) return "";
  return ['<div class="preview-static-shell">', html, "</div>"].join("");
}

function buildHtmlPreviewSrcdoc(content) {
  const html = String(content || "").trim();
  if (!html) return "";
  if (/<!doctype html/i.test(html) || /<html[\s>]/i.test(html)) {
    return html;
  }
  return [
    "<!doctype html>",
    '<html lang="zh-CN">',
    "<head>",
    '<meta charset="UTF-8" />',
    '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
    "<style>html,body{margin:0;padding:0;min-height:100%;background:#f7f7f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','PingFang SC','Microsoft YaHei',sans-serif;}body{padding:24px;}</style>",
    "</head>",
    "<body>",
    html,
    "</body>",
    "</html>",
  ].join("");
}

function buildVuePreviewSrcdoc(content) {
  const template = extractSfcTemplate(content) || String(content || "").trim();
  if (!template) return "";
  const styles = extractSfcStyles(content).join("\n\n");
  const scriptContent = extractSfcScript(content);
  const refInitializers = collectScriptRefInitializers(scriptContent);
  const reactiveInitializers = collectScriptReactiveInitializers(scriptContent);
  const functionNames = collectScriptFunctionNames(scriptContent);
  const modelPaths = collectTemplateModelPaths(template);
  const staticPreviewHtml = buildStaticVuePreviewHtml(template);

  return [
    "<!doctype html>",
    '<html lang="zh-CN">',
    "<head>",
    '<meta charset="UTF-8" />',
    '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
    '<link rel="stylesheet" href="https://unpkg.com/element-plus/dist/index.css" />',
    "<style>",
    "html,body{margin:0;padding:0;min-height:100%;background:#f7f7f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','PingFang SC','Microsoft YaHei',sans-serif;}",
    "body{padding:24px;box-sizing:border-box;}",
    "#app{min-height:calc(100vh - 48px);}",
    ".preview-static-shell{min-height:calc(100vh - 48px);}",
    ".preview-form{display:block;}",
    ".preview-form-item{display:flex;flex-direction:column;gap:8px;margin-bottom:18px;}",
    ".preview-input,.preview-textarea,.preview-select{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #dcdfe6;border-radius:8px;background:#fff;color:#1f2937;font-size:14px;line-height:1.5;}",
    ".preview-textarea{min-height:96px;resize:vertical;}",
    ".preview-button{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:0 18px;border-radius:10px;border:1px solid #0f172a;background:#0f172a;color:#fff;font-size:14px;font-weight:600;cursor:default;}",
    ".preview-checkbox,.preview-radio{display:inline-flex;align-items:center;gap:8px;color:#4b5563;font-size:14px;}",
    ".preview-switch{display:inline-flex;align-items:center;width:42px;height:24px;padding:2px;border-radius:999px;background:rgba(226,232,240,.92);box-sizing:border-box;}",
    ".preview-switch__track{display:block;width:20px;height:20px;border-radius:50%;background:#0f172a;margin-left:auto;}",
    ".preview-alert{margin-bottom:16px;padding:10px 12px;border-radius:10px;border:1px solid rgba(56,189,248,.18);background:rgba(239,249,255,.88);color:#0f172a;font-size:13px;line-height:1.6;}",
    ".preview-block{display:block;}",
    ".preview-error{padding:16px;border-radius:16px;background:#fff1f2;border:1px solid rgba(244,63,94,.18);color:#9f1239;font-size:14px;line-height:1.7;white-space:pre-wrap;}",
    styles,
    "</style>",
    "</head>",
    "<body>",
    `<div id="app">${staticPreviewHtml}</div>`,
    '<script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"><\\/script>',
    '<script src="https://unpkg.com/element-plus/dist/index.full.min.js"><\\/script>',
    "<script>",
    `const previewTemplate = ${JSON.stringify(template)};`,
    `const previewRefs = ${JSON.stringify(refInitializers)};`,
    `const previewReactives = ${JSON.stringify(reactiveInitializers)};`,
    `const previewFunctions = ${JSON.stringify(functionNames)};`,
    `const previewModelPaths = ${JSON.stringify(modelPaths)};`,
    `function evaluateLiteral(source, fallback){ if(!source){ return fallback; } try { return (new Function("return (" + source + ")"))(); } catch { return fallback; } }`,
    `function inferLeafDefault(path){ const leaf = String(path.split('.').pop() || '').toLowerCase(); if(/^(is|has|can|show|enable|loading|locked|disabled|visible|checked|remember|submitting)/.test(leaf)){ return false; } if(/count|size|total|days|length|index|step/.test(leaf)){ return 0; } return ''; }`,
    `function ensurePath(root, path){ const parts = String(path || '').split('.').map((item) => item.trim()).filter(Boolean); if(!parts.length){ return; } let current = root; for(let i = 0; i < parts.length; i += 1){ const key = parts[i]; const isLast = i === parts.length - 1; if(isLast){ if(current[key] === undefined){ current[key] = inferLeafDefault(path); } break; } if(!current[key] || typeof current[key] !== 'object' || Array.isArray(current[key])){ current[key] = {}; } current = current[key]; } }`,
    `function noop(){ return undefined; }`,
    `const component = { setup(){ const ctx = {}; for(const item of previewReactives){ ctx[item.name] = Vue.reactive(evaluateLiteral(item.expression, {})); } for(const item of previewRefs){ ctx[item.name] = Vue.ref(evaluateLiteral(item.expression, inferLeafDefault(item.name))); } if(!ctx.form){ ctx.form = Vue.reactive({}); } if(!ctx.rules){ ctx.rules = Vue.reactive({}); } for(const path of previewModelPaths){ const rootName = String(path.split('.')[0] || '').trim(); if(!rootName){ continue; } const rootValue = ctx[rootName]; if(rootValue && typeof rootValue === 'object' && !('value' in rootValue)){ ensurePath(rootValue, path.split('.').slice(1).join('.')); continue; } if(rootValue && typeof rootValue === 'object' && 'value' in rootValue){ if(rootValue.value === undefined || rootValue.value === null || typeof rootValue.value !== 'object'){ rootValue.value = {}; } ensurePath(rootValue.value, path.split('.').slice(1).join('.')); continue; } if(path.includes('.')){ ctx[rootName] = Vue.reactive({}); ensurePath(ctx[rootName], path.split('.').slice(1).join('.')); } else if(ctx[rootName] === undefined){ ctx[rootName] = Vue.ref(inferLeafDefault(path)); } } for(const name of previewFunctions){ if(!ctx[name]){ ctx[name] = noop; } } return ctx; }, template: previewTemplate };`,
    `function showError(error){ const el = document.getElementById('app'); if(el){ el.innerHTML = '<div class="preview-error">' + String(error && error.message ? error.message : error) + '</div>'; } }`,
    `window.setTimeout(() => { if(!window.Vue || !window.ElementPlus){ return; } try { const app = Vue.createApp(component); app.use(ElementPlus); app.config.errorHandler = (error) => { showError(error); }; app.mount('#app'); } catch (error) { showError(error); } }, 80);`,
    "<\\/script>",
    "</body>",
    "</html>",
  ].join("");
}

function openCodePreview(content, language) {
  const text = String(content || "").trim();
  if (!text) {
    ElMessage.warning("当前代码块暂无可预览内容");
    return;
  }
  codePreviewError.value = "";
  codePreviewTitle.value = buildCodePreviewTitle(language, text);
  try {
    if (
      /<!doctype html/i.test(text) ||
      /<html[\s>]/i.test(text) ||
      ["html", "htm"].includes(normalizeCodeLanguage(language))
    ) {
      codePreviewSrcdoc.value = buildHtmlPreviewSrcdoc(text);
    } else if (isPreviewableCodeBlock(text, language)) {
      codePreviewSrcdoc.value = buildVuePreviewSrcdoc(text);
    } else {
      codePreviewError.value =
        "当前代码块暂不支持预览，仅支持 HTML 和 Vue 单文件组件。";
    }
  } catch (error) {
    codePreviewError.value = String(error?.message || error || "预览生成失败");
  }
  codePreviewVisible.value = true;
}

const codeCopyResetTimers = new WeakMap();

function setCodeCopyButtonState(button, copied) {
  if (!button) return;
  const idleLabel = String(button.dataset.copyLabel || "复制").trim() || "复制";
  const copiedLabel =
    String(button.dataset.copiedLabel || "已复制").trim() || "已复制";
  const idleIcon = String(button.dataset.copyIcon || "").trim();
  const copiedIcon = String(button.dataset.copiedIcon || "").trim();
  button.innerHTML = copied ? copiedIcon || copiedLabel : idleIcon || idleLabel;
  button.setAttribute("aria-label", copied ? copiedLabel : idleLabel);
  button.setAttribute("title", copied ? copiedLabel : idleLabel);
  button.dataset.copied = copied ? "true" : "false";
}

async function handleMessageAreaClick(event) {
  const previewButton = event?.target?.closest?.(".chat-code-block__preview");
  const copyButton = event?.target?.closest?.(".chat-code-block__copy");
  const button = previewButton || copyButton;
  if (!button) return;
  const wrapper = button.closest(".chat-code-block");
  const codeElement = wrapper?.querySelector("pre code");
  const content = String(codeElement?.textContent || "");
  if (!content && !previewButton) {
    ElMessage.warning("当前代码块暂无可复制内容");
    return;
  }
  if (previewButton) {
    const language = String(previewButton.dataset.codeLang || "").trim();
    openCodePreview(content, language);
    return;
  }
  try {
    await writeClipboardText(content);
    setCodeCopyButtonState(copyButton, true);
    const previousTimer = codeCopyResetTimers.get(copyButton);
    if (previousTimer) {
      window.clearTimeout(previousTimer);
    }
    const timerId = window.setTimeout(() => {
      setCodeCopyButtonState(copyButton, false);
      codeCopyResetTimers.delete(copyButton);
    }, 2000);
    codeCopyResetTimers.set(copyButton, timerId);
  } catch {
    ElMessage.error("复制失败");
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    }
  });
}

function clearHighlightedMessage() {
  if (highlightedMessageTimer !== null) {
    window.clearTimeout(highlightedMessageTimer);
    highlightedMessageTimer = null;
  }
  highlightedMessageId.value = "";
}

function routeChatTarget() {
  return {
    projectId: String(route.query.project_id || "").trim(),
    chatSessionId: String(route.query.chat_session_id || "").trim(),
    messageId: String(route.query.message_id || "").trim(),
  };
}

async function focusMessageById(messageId, options = {}) {
  const normalizedMessageId = String(messageId || "").trim();
  if (!normalizedMessageId) return false;
  await nextTick();
  const container = messagesContainer.value;
  const candidates = Array.from(
    container?.querySelectorAll?.(".message-row[data-message-id]") || [],
  );
  const target = candidates.find(
    (node) =>
      String(node?.dataset?.messageId || "").trim() === normalizedMessageId,
  );
  if (!target) {
    return false;
  }
  target.scrollIntoView({
    behavior: options.smooth === false ? "auto" : "smooth",
    block: "center",
  });
  if (target instanceof HTMLElement) {
    target.focus?.({ preventScroll: true });
  }
  highlightedMessageId.value = normalizedMessageId;
  if (highlightedMessageTimer !== null) {
    window.clearTimeout(highlightedMessageTimer);
  }
  highlightedMessageTimer = window.setTimeout(() => {
    highlightedMessageId.value = "";
    highlightedMessageTimer = null;
  }, 2600);
  return true;
}

async function applyRouteMessageFocus() {
  const { messageId, chatSessionId } = routeChatTarget();
  if (!messageId) {
    clearHighlightedMessage();
    return;
  }
  if (
    chatSessionId &&
    chatSessionId !== String(currentChatSessionId.value || "").trim()
  ) {
    return;
  }
  await focusMessageById(messageId, { smooth: false });
}

watch(
  messages,
  (value) => {
    if (inlineEditingMessageIndex.value < 0) return;
    const current = value[inlineEditingMessageIndex.value];
    if (
      !current ||
      String(current?.id || "").trim() !==
        String(inlineEditingMessageId.value || "").trim()
    ) {
      resetInlineMessageEdit();
    }
  },
  { deep: false },
);

function extractImages(message) {
  if (!message || !Array.isArray(message.images)) return [];
  return message.images
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function extractVideos(message) {
  if (!message || !Array.isArray(message.videos)) return [];
  return message.videos
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function mergeMediaUrls(...groups) {
  const urls = [];
  const seen = new Set();
  for (const group of groups) {
    for (const item of Array.isArray(group) ? group : []) {
      const url = String(item || "").trim();
      if (!url || seen.has(url)) continue;
      seen.add(url);
      urls.push(url);
    }
  }
  return urls;
}

function mergeImageUrls(...groups) {
  return mergeMediaUrls(...groups);
}

function mergeVideoUrls(...groups) {
  return mergeMediaUrls(...groups);
}

function inferArtifactAssetType(item) {
  const explicit = String(item?.asset_type || item?.assetType || "")
    .trim()
    .toLowerCase();
  if (["image", "video"].includes(explicit)) return explicit;
  const mimeType = String(
    item?.mime_type || item?.mimeType || item?.content_type || "",
  )
    .trim()
    .toLowerCase();
  if (mimeType.startsWith("video/")) return "video";
  const contentUrl = String(
    item?.content_url ||
      item?.contentUrl ||
      item?.video_url ||
      item?.videoUrl ||
      item?.url ||
      "",
  ).trim();
  if (/\.(mp4|mov|m4v|webm|avi|mkv)(?:[?#].*)?$/i.test(contentUrl)) {
    return "video";
  }
  return "image";
}

function collectArtifactImageUrls(payload) {
  const directImages = Array.isArray(payload?.images) ? payload.images : [];
  const artifacts = Array.isArray(payload?.artifacts) ? payload.artifacts : [];
  return mergeImageUrls(
    directImages,
    artifacts.flatMap((item) =>
      inferArtifactAssetType(item) === "video"
        ? []
        : [
            item?.preview_url,
            item?.content_url,
            item?.previewUrl,
            item?.contentUrl,
            item?.url,
          ],
    ),
  );
}

function collectArtifactVideoUrls(payload) {
  const directVideos = Array.isArray(payload?.videos) ? payload.videos : [];
  const artifacts = Array.isArray(payload?.artifacts) ? payload.artifacts : [];
  return mergeVideoUrls(
    directVideos,
    artifacts.flatMap((item) =>
      inferArtifactAssetType(item) === "video"
        ? [
            item?.content_url,
            item?.contentUrl,
            item?.video_url,
            item?.videoUrl,
            item?.url,
          ]
        : [],
    ),
  );
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

function canSaveMessageAsMaterial(message) {
  return canSaveMessageAsMaterialEntry(
    message,
    String(selectedProjectId.value || "").trim(),
  );
}

function resetMaterialDialogState() {
  materialDialogSaving.value = false;
  materialDialogPayload.value = null;
}

async function openMaterialDialog(message, messageIndex) {
  if (!canSaveMessageAsMaterial(message)) {
    ElMessage.warning("当前消息暂无可入库的内容");
    return;
  }
  materialDialogPayload.value = buildMaterialDialogPayload({
    message,
    messageIndex,
    currentChatSessionId: String(currentChatSessionId.value || "").trim(),
    currentUsername: String(currentUsername.value || "").trim(),
  });
  materialDialogVisible.value = true;
}

async function submitMaterialDialog(formPayload) {
  const projectId = String(selectedProjectId.value || "").trim();
  const payloadState = materialDialogPayload.value;
  if (!projectId || !payloadState || !formPayload) {
    materialDialogVisible.value = false;
    return;
  }
  materialDialogSaving.value = true;
  try {
    await api.post(`/projects/${projectId}/materials`, {
      asset_type: formPayload.asset_type,
      title: formPayload.title,
      summary: formPayload.summary,
      preview_url: formPayload.preview_url,
      content_url: formPayload.content_url,
      mime_type: formPayload.mime_type,
      status: "ready",
      source_message_id: payloadState.source_message_id,
      source_chat_session_id: payloadState.source_chat_session_id,
      source_username: payloadState.source_username,
      structured_content: formPayload.structured_content,
      metadata: formPayload.metadata,
    });
    ElMessage.success("已加入当前项目素材库");
    materialDialogVisible.value = false;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存素材失败");
  } finally {
    materialDialogSaving.value = false;
  }
}

async function ensureEmployeeDraftCatalog(force = false) {
  const now = Date.now();
  const loadedAt = Number(employeeDraftCatalog.value.loaded_at || 0);
  if (
    !force &&
    employeeDraftCatalog.value.skills.length &&
    employeeDraftCatalog.value.rules.length &&
    now - loadedAt < 60_000
  ) {
    return employeeDraftCatalog.value;
  }
  const [skillsRes, rulesRes] = await Promise.all([
    api.get("/skills"),
    api.get("/rules"),
  ]);
  employeeDraftCatalog.value = {
    skills: (skillsRes.skills || [])
      .filter(isReusableEmployeeDraftSkill)
      .map((skill) => ({
        id: String(skill.id || "").trim(),
        name: String(skill.name || skill.id || "").trim(),
        description: String(skill.description || "").trim(),
        tags: Array.isArray(skill.tags) ? skill.tags : [],
      })),
    rules: (rulesRes.rules || []).map((rule) => ({
      id: String(rule.id || "").trim(),
      title: String(rule.title || rule.id || "").trim(),
      domain: String(rule.domain || "").trim(),
    })),
    loaded_at: now,
  };
  return employeeDraftCatalog.value;
}

function buildEmployeeDraftAssistContext() {
  const skillLines = employeeDraftCatalog.value.skills
    .slice(0, 40)
    .map(
      (skill) =>
        `- ${skill.id} | ${skill.name}${skill.description ? ` | ${clipText(skill.description, 80).replace(/\n/g, " ")}` : ""}`,
    );
  const ruleLines = employeeDraftCatalog.value.rules
    .slice(0, 60)
    .map((rule) => `- ${rule.id} | ${rule.domain || "未分类"} | ${rule.title}`);
  return [
    "系统可用技能目录（优先从这里匹配，不要臆造不存在的技能 ID）：",
    skillLines.length ? skillLines.join("\n") : "- 暂无本地技能",
    "",
    "系统可用规则目录（优先输出 rule_domains / rule_titles，便于系统自动绑定）：",
    ruleLines.length ? ruleLines.join("\n") : "- 暂无本地规则",
    "",
    "输出要求：",
    "- 先用 3 到 6 行说明你推荐这个员工的定位。",
    "- 最后必须追加一个 ```employee-draft``` 代码块，内容是严格 JSON，不要写注释。",
    "- JSON 至少包含：name、description、goal、skills、rule_domains、style_hints、default_workflow、tool_usage_policy、memory_scope、memory_retention_days。",
    "- skills 字段里优先放技能 ID；如果拿不准，可放技能名称或关键词。",
    "- rule_domains 优先输出领域名；rule_titles 可补充你认为最关键的规则标题。",
    "- 如果从外部提示词或技能模板中提炼出了可直接落地的员工规则，请额外输出 rule_drafts 数组；每项包含 title、domain、content，可选 source_label、source_url。",
  ]
    .filter(Boolean)
    .join("\n");
}

function normalizeMatchKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function isReusableEmployeeDraftSkill(skill) {
  const tags = Array.isArray(skill?.tags)
    ? skill.tags.map((item) => normalizeMatchKey(item))
    : [];
  return !tags.some((tag) =>
    ["employee-draft", "system-mcp", "system-mcp-import"].includes(tag),
  );
}

function matchSkillsFromDraft(skillHints, skillCatalog) {
  const hints = normalizeStringList(skillHints || [], 20);
  if (!hints.length) return [];
  const matchedIds = [];
  const seen = new Set();
  for (const hint of hints) {
    const target = normalizeMatchKey(hint);
    if (!target) continue;
    const exact = skillCatalog.find(
      (skill) =>
        normalizeMatchKey(skill.id) === target ||
        normalizeMatchKey(skill.name) === target,
    );
    const partial =
      exact ||
      skillCatalog.find((skill) =>
        [skill.id, skill.name]
          .map(normalizeMatchKey)
          .some((text) => text && text.includes(target)),
      );
    if (!partial) continue;
    if (seen.has(partial.id)) continue;
    seen.add(partial.id);
    matchedIds.push(partial.id);
  }
  return matchedIds;
}

function matchRulesFromDraft(draft, ruleCatalog) {
  const bindings = [];
  const seen = new Set();
  const addRule = (rule) => {
    if (!rule?.id || seen.has(rule.id)) return;
    seen.add(rule.id);
    bindings.push({
      id: rule.id,
      title: rule.title,
      domain: rule.domain,
    });
  };

  for (const ruleId of normalizeStringList(draft.rule_ids || [], 30)) {
    addRule(
      ruleCatalog.find(
        (rule) => normalizeMatchKey(rule.id) === normalizeMatchKey(ruleId),
      ),
    );
  }
  for (const title of normalizeStringList(draft.rule_titles || [], 30)) {
    const normalized = normalizeMatchKey(title);
    addRule(
      ruleCatalog.find(
        (rule) =>
          normalizeMatchKey(rule.title) === normalized ||
          normalizeMatchKey(rule.title).includes(normalized),
      ),
    );
  }
  for (const domain of normalizeStringList(draft.rule_domains || [], 20)) {
    const normalized = normalizeMatchKey(domain);
    for (const rule of ruleCatalog) {
      if (normalizeMatchKey(rule.domain) !== normalized) continue;
      addRule(rule);
    }
  }
  return bindings;
}

function buildEmployeeDraftCard(rawDraft) {
  const draft = normalizeEmployeeDraftPayload(rawDraft);
  const skillCatalog = Array.isArray(employeeDraftCatalog.value.skills)
    ? employeeDraftCatalog.value.skills
    : [];
  const ruleCatalog = Array.isArray(employeeDraftCatalog.value.rules)
    ? employeeDraftCatalog.value.rules
    : [];
  const matchedSkillIds = matchSkillsFromDraft(draft.skills, skillCatalog);
  const matchedRuleBindings = matchRulesFromDraft(draft, ruleCatalog);
  return {
    ...draft,
    matched_skill_count: matchedSkillIds.length,
    matched_rule_count: matchedRuleBindings.length,
  };
}

function buildEmployeeAutoCreatePayload(rawDraft) {
  const draft = normalizeEmployeeDraftPayload(rawDraft);
  return {
    ...draft,
    add_to_current_project: Boolean(
      String(selectedProjectId.value || "").trim(),
    ),
    memory_retention_days: Math.min(
      365,
      Math.max(7, Number(draft.memory_retention_days || 90)),
    ),
    auto_create_missing_skills: true,
    auto_create_missing_rules: true,
  };
}

function normalizeEmployeeDraftExternalSkillSite(raw) {
  return {
    id: String(raw?.id || "").trim(),
    title: String(raw?.title || "").trim(),
    description: String(raw?.description || "").trim(),
    url: String(raw?.url || "").trim(),
  };
}

function buildVettSkillPageUrl(slug) {
  const normalized = String(slug || "")
    .trim()
    .replace(/^\/+|\/+$/g, "");
  return normalized ? `https://vett.sh/skills/${normalized}` : "";
}

const skillResourceIntentAliasGroups = [
  {
    match: [
      "java开发",
      "java后端",
      "java",
      "后端",
      "backend",
      "spring",
      "springboot",
      "spring boot",
      "jvm",
    ],
    queries: ["java", "spring", "spring boot", "backend", "jvm"],
  },
  {
    match: [
      "界面设计",
      "ui设计",
      "界面",
      "ui",
      "视觉",
      "交互",
      "排版",
      "设计系统",
      "frontend",
      "interface",
      "design system",
      "design-system",
    ],
    queries: ["ui", "frontend", "design", "interface", "design system"],
  },
  {
    match: [
      "css",
      "样式",
      "布局",
      "响应式",
      "动画",
      "style",
      "responsive",
      "animation",
    ],
    queries: ["css", "style", "responsive", "animation"],
  },
  {
    match: ["vue", "vue3", "composition api", "composition-api"],
    queries: ["vue", "vue3", "composition api"],
  },
  {
    match: [
      "浏览器",
      "调试",
      "性能",
      "chrome",
      "devtools",
      "browser",
      "performance",
    ],
    queries: ["chrome", "devtools", "browser", "performance"],
  },
  {
    match: [
      "架构",
      "架构设计",
      "技术选型",
      "系统设计",
      "architect",
      "architecture",
      "system design",
      "software architect",
    ],
    queries: [
      "software architect",
      "architecture",
      "architect",
      "system design",
    ],
  },
  {
    match: [
      "node",
      "nodejs",
      "node.js",
      "javascript",
      "js",
      "工程实践",
      "工具链",
    ],
    queries: ["nodejs", "node", "javascript", "js"],
  },
];

function normalizeSearchAliasKey(value) {
  return normalizeMatchKey(value).replace(/[\s._/+-]+/g, "");
}

function pushSkillResourceSearchQuery(buffer, seen, value) {
  const text = String(value || "").trim();
  const key = normalizeMatchKey(text);
  if (!text || !key || seen.has(key)) {
    return;
  }
  seen.add(key);
  buffer.push(text);
}

function buildSkillResourceSearchQueries(query) {
  const rawQuery = String(query || "").trim();
  const normalized = normalizeMatchKey(rawQuery);
  const compact = normalizeSearchAliasKey(rawQuery);
  const queries = [];
  const seen = new Set();
  pushSkillResourceSearchQuery(queries, seen, rawQuery);
  const asciiTokens = rawQuery.match(/[A-Za-z][A-Za-z0-9.+#-]*/g) || [];
  asciiTokens.forEach((token) =>
    pushSkillResourceSearchQuery(queries, seen, token),
  );
  skillResourceIntentAliasGroups.forEach((group) => {
    const matched = group.match.some((token) => {
      const compactToken = normalizeSearchAliasKey(token);
      return (
        (normalized && normalized.includes(normalizeMatchKey(token))) ||
        (compact && compactToken && compact.includes(compactToken))
      );
    });
    if (!matched) {
      return;
    }
    group.queries.forEach((token) =>
      pushSkillResourceSearchQuery(queries, seen, token),
    );
  });
  return queries.slice(0, 6);
}

function inferChineseSkillSummary(raw) {
  const name = String(raw?.name || raw?.slug || "").trim();
  const slug = String(raw?.slug || "")
    .trim()
    .toLowerCase();
  const description = String(raw?.description || "").trim();
  const joined = `${name} ${slug} ${description}`.toLowerCase();
  if (joined.includes("ui") || joined.includes("interface")) {
    return "适合界面审美、排版层级、交互一致性和设计系统类员工。";
  }
  if (
    joined.includes("css") ||
    joined.includes("style") ||
    joined.includes("responsive")
  ) {
    return "适合布局系统、响应式、动画和样式治理相关任务。";
  }
  if (joined.includes("vue")) {
    return "适合 Vue 组件设计、Composition API 和工程实践相关任务。";
  }
  if (
    joined.includes("chrome") ||
    joined.includes("devtools") ||
    joined.includes("browser")
  ) {
    return "适合浏览器调试、渲染链路分析和性能定位相关任务。";
  }
  if (joined.includes("architect") || joined.includes("architecture")) {
    return "适合系统拆分、技术选型、边界设计和架构治理相关任务。";
  }
  if (
    joined.includes("node") ||
    joined.includes("javascript") ||
    joined.includes("js")
  ) {
    return "适合 JS 工具链、构建脚本、运行时治理和工程交付相关任务。";
  }
  if (joined.includes("frontend") || joined.includes("design")) {
    return "适合前端界面、组件设计和交付规范相关任务。";
  }
  return "适合相关技能补强场景，建议结合原始说明和来源页面进一步判断是否匹配当前任务。";
}

function resolveLocalizedSkillSummary(raw, url) {
  const normalizedUrl = String(url || "").trim();
  const matched = (employeeDraftExternalSkillSites.value || []).find(
    (item) => String(item?.url || "").trim() === normalizedUrl,
  );
  if (matched?.description) {
    return String(matched.description || "").trim();
  }
  return inferChineseSkillSummary(raw);
}

function normalizeSkillResourceSearchItem(raw) {
  const latestVersion =
    raw?.latest_version && typeof raw.latest_version === "object"
      ? raw.latest_version
      : {};
  const risk = String(latestVersion.risk || "")
    .trim()
    .toLowerCase();
  const scanStatus = String(latestVersion.scan_status || "")
    .trim()
    .toLowerCase();
  const policyAction = String(latestVersion.policy_action || "")
    .trim()
    .toLowerCase();
  const latestVersionNumber = String(latestVersion.version || "").trim();
  const installCount =
    Number(raw?.install_count ?? raw?.installCount ?? 0) || 0;
  const pageUrl =
    buildVettSkillPageUrl(raw?.slug) || String(raw?.source_url || "").trim();
  return {
    id: String(raw?.id || "").trim(),
    slug: String(raw?.slug || "").trim(),
    title: String(raw?.name || raw?.slug || "").trim(),
    description: String(raw?.description || "").trim(),
    url: pageUrl,
    localizedDescription: resolveLocalizedSkillSummary(raw, pageUrl),
    latestVersionLabel: latestVersionNumber ? `v${latestVersionNumber}` : "",
    canInstall:
      !!latestVersionNumber &&
      scanStatus === "completed" &&
      policyAction !== "deny" &&
      policyAction !== "blocked",
    requiresReview: policyAction === "review",
    risk,
    scanStatus,
    version: latestVersionNumber,
    installCount,
  };
}

function scoreSkillResourceSearchItem(
  item,
  rawQuery,
  matchedQuery,
  queryIndex,
) {
  const joined = normalizeMatchKey(
    `${item?.title || ""} ${item?.slug || ""} ${item?.description || ""}`,
  );
  const raw = normalizeMatchKey(rawQuery);
  const matched = normalizeMatchKey(matchedQuery);
  let score = 120 - queryIndex * 12;
  if (matched && joined.includes(matched)) {
    score += 36;
  }
  if (raw && joined.includes(raw)) {
    score += 48;
  }
  if (matched && normalizeMatchKey(item?.title || "") === matched) {
    score += 18;
  }
  if (item?.canInstall) {
    score += 6;
  }
  if ((skillResourceSites.value || []).some((site) => site.url === item?.url)) {
    score += 14;
  }
  score += Math.min(18, Math.log10((Number(item?.installCount) || 0) + 1) * 8);
  return score;
}

function mergeSkillResourceSearchResults(groups, rawQuery) {
  const merged = new Map();
  groups.forEach(({ query, items, index }) => {
    items.forEach((rawItem) => {
      const item = normalizeSkillResourceSearchItem(rawItem);
      if (!item.slug || !item.url) {
        return;
      }
      const score = scoreSkillResourceSearchItem(item, rawQuery, query, index);
      const existing = merged.get(item.slug);
      if (!existing || score > existing.searchScore) {
        merged.set(item.slug, {
          ...item,
          searchScore: score,
          matchedQuery: query,
        });
      }
    });
  });
  return Array.from(merged.values())
    .sort((left, right) => {
      if (right.searchScore !== left.searchScore) {
        return right.searchScore - left.searchScore;
      }
      if (right.installCount !== left.installCount) {
        return right.installCount - left.installCount;
      }
      return left.title.localeCompare(right.title);
    })
    .slice(0, 18);
}

async function fetchSkillResourceSearchItems(query) {
  const data = await api.get("/skill-resources", {
    params: {
      source: "vett",
      q: query,
      limit: 8,
      offset: 0,
    },
  });
  return Array.isArray(data?.items) ? data.items : [];
}

const employeeDraftDialogMatchedSkillIds = computed(() => {
  const payload = employeeDraftDialogPayload.value;
  if (!payload) return [];
  return matchSkillsFromDraft(
    payload.skills,
    Array.isArray(employeeDraftCatalog.value.skills)
      ? employeeDraftCatalog.value.skills
      : [],
  );
});

const employeeDraftDialogMatchedSkillLabels = computed(() => {
  const skillMap = new Map(
    (employeeDraftCatalog.value.skills || []).map((skill) => [
      skill.id,
      skill.name || skill.id,
    ]),
  );
  return employeeDraftDialogMatchedSkillIds.value.map((id) => {
    const name = String(skillMap.get(id) || id).trim();
    return `${name} (${id})`;
  });
});

const employeeDraftDialogMatchedRuleBindings = computed(() => {
  const payload = employeeDraftDialogPayload.value;
  if (!payload) return [];
  return matchRulesFromDraft(
    payload,
    Array.isArray(employeeDraftCatalog.value.rules)
      ? employeeDraftCatalog.value.rules
      : [],
  );
});

const employeeDraftDialogMatchedRuleLabels = computed(() =>
  employeeDraftDialogMatchedRuleBindings.value.map((rule) =>
    rule.domain ? `${rule.title} (${rule.domain})` : rule.title,
  ),
);

function syncSkillResourceDirectoryDraft() {
  skillResourceDirectoryDraft.value = readPreferredSkillResourceDirectory(
    selectedProjectId.value,
  );
}

function setSkillResourceDirectory(directoryPath, options = {}) {
  const normalized = String(directoryPath || "").trim();
  const previous = String(skillResourceDirectoryResolved.value || "").trim();
  skillResourceDirectoryDraft.value = normalized;
  writePreferredSkillResourceDirectory(selectedProjectId.value, normalized);
  if (previous !== normalized) {
    externalAgentWarmupKey.value = "";
  }
  if (!options?.silent) {
    ElMessage.success(normalized ? "技能目录已保存" : "技能目录已清空");
  }
}

function openSkillResourceCenter() {
  syncSkillResourceDirectoryDraft();
  skillResourceDialogVisible.value = true;
}

function openCurrentMaterialLibrary() {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    ElMessage.warning("请先选择项目");
    return;
  }
  void router.push({ path: "/materials", query: { project_id: projectId } });
}

function openUnifiedMcpDialog() {
  unifiedMcpDialogVisible.value = true;
}

function useWorkspaceAsSkillDirectory() {
  const nextDirectory = String(projectWorkspacePath.value || "").trim();
  if (!nextDirectory) {
    ElMessage.warning("当前还没有可复用的工作区路径");
    return;
  }
  setSkillResourceDirectory(nextDirectory);
}

async function pickSkillResourceDirectory() {
  const title = `选择技能下载目录 · ${String(currentProjectLabel.value || "").trim() || "AI 对话"}`;
  const initialPath = String(
    skillResourceDirectoryResolved.value || projectWorkspacePath.value || "",
  ).trim();
  skillResourceDirectoryPicking.value = true;
  try {
    const picked = await pickWorkspaceDirectory(initialPath, {
      title,
      placeholder: "/Users/yourname/.codex/skills",
    });
    const pickedPath = String(picked || "").trim();
    if (!pickedPath) {
      return;
    }
    setSkillResourceDirectory(pickedPath);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "选择技能目录失败");
  } finally {
    skillResourceDirectoryPicking.value = false;
  }
}

async function copySkillResourceDirectory() {
  const directoryPath = String(
    skillResourceDirectoryResolved.value || "",
  ).trim();
  if (!directoryPath) {
    ElMessage.warning("请先选择技能目录");
    return;
  }
  try {
    await writeClipboardText(directoryPath);
    ElMessage.success("技能目录路径已复制");
  } catch {
    ElMessage.error("复制路径失败");
  }
}

async function copySkillResourceSite(site) {
  const url = String(site?.url || "").trim();
  if (!url) {
    ElMessage.warning("当前站点没有可复制地址");
    return;
  }
  try {
    await writeClipboardText(url);
    ElMessage.success("站点地址已复制");
  } catch {
    ElMessage.error("复制地址失败");
  }
}

async function searchSkillResources() {
  const query = String(skillResourceSearchQuery.value || "").trim();
  if (!query) {
    skillResourceSearchResults.value = [];
    skillResourceSearchResolvedQueries.value = [];
    return;
  }
  const expandedQueries = buildSkillResourceSearchQueries(query);
  skillResourceSearchResolvedQueries.value = expandedQueries;
  skillResourceSearchLoading.value = true;
  try {
    const settled = await Promise.allSettled(
      expandedQueries.map((searchQuery) =>
        fetchSkillResourceSearchItems(searchQuery),
      ),
    );
    const groups = settled
      .map((entry, index) => {
        if (entry.status !== "fulfilled") {
          return null;
        }
        return {
          query: expandedQueries[index],
          index,
          items: Array.isArray(entry.value) ? entry.value : [],
        };
      })
      .filter(Boolean);
    if (!groups.length) {
      const failed = settled.find((entry) => entry.status === "rejected");
      throw failed?.reason || new Error("搜索技能资源失败");
    }
    skillResourceSearchResults.value = mergeSkillResourceSearchResults(
      groups,
      query,
    );
  } catch (err) {
    skillResourceSearchResults.value = [];
    ElMessage.error(err?.detail || err?.message || "搜索技能资源失败");
  } finally {
    skillResourceSearchLoading.value = false;
  }
}

function resetSkillResourceSearch() {
  skillResourceSearchQuery.value = "";
  skillResourceSearchResults.value = [];
  skillResourceSearchResolvedQueries.value = [];
}

async function installSkillResource(site) {
  const slug = String(site?.slug || "").trim();
  const version = String(site?.version || "").trim();
  const installDir = String(skillResourceDirectoryResolved.value || "").trim();
  if (!slug || !version) {
    ElMessage.warning("当前技能资源缺少可安装版本");
    return;
  }
  if (!installDir) {
    ElMessage.warning("请先选择本地技能目录");
    return;
  }
  if (site?.requiresReview) {
    await ElMessageBox.confirm(
      `技能「${site.title || slug}」被标记为需要人工确认，确定继续安装？`,
      "高风险确认",
      { type: "warning" },
    );
  }
  skillResourceInstallingSlug.value = slug;
  try {
    const result = await api.post(`/skill-resources/vett/${slug}/install`, {
      version,
      install_dir: installDir,
      import_to_library: false,
    });
    const resolvedInstallDir = String(result?.install_dir || installDir).trim();
    ElMessage.success(
      resolvedInstallDir
        ? `技能已下载到本地技能目录：${resolvedInstallDir}`
        : "技能已下载到本地技能目录",
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "下载技能资源失败");
  } finally {
    skillResourceInstallingSlug.value = "";
  }
}

const employeeDraftDialogRuleDraftLabels = computed(() => {
  const payload = employeeDraftDialogPayload.value;
  if (!payload || !Array.isArray(payload.rule_drafts)) return [];
  return payload.rule_drafts
    .map((draft) => {
      const title = String(draft?.title || "").trim();
      const domain = String(draft?.domain || "").trim();
      if (!title && !domain) return "";
      return domain ? `${title || "未命名规则"} (${domain})` : title;
    })
    .filter(Boolean);
});

const employeeDraftAutoRuleSourceLabels = computed(() =>
  normalizeStringList(
    (employeeDraftAutoRuleGenerationSourceFilters.value || []).map(
      (item) =>
        EMPLOYEE_DRAFT_AUTO_RULE_SOURCE_LABELS[String(item || "").trim()] ||
        "系统规则源",
    ),
    6,
  ),
);

function getEmployeeDraftCard(item) {
  const rawDraft = extractEmployeeDraftPayload(item?.content || "");
  if (!rawDraft) return null;
  return buildEmployeeDraftCard(rawDraft);
}

function getEmployeeDraftKey(item) {
  const messageId = String(item?.id || "").trim();
  if (messageId) return `msg:${messageId}`;
  const content = String(item?.content || "").trim();
  return `content:${content.slice(0, 120)}`;
}

function resetEmployeeDraftDialogState() {
  employeeDraftDialogLoading.value = false;
  employeeDraftDialogPayload.value = null;
  employeeDraftDialogItem.value = null;
  employeeDraftAutoCreateSkills.value = true;
  employeeDraftAutoCreateRules.value = true;
  employeeDraftAddToProject.value = false;
}

function handleStartEmployeeCreation() {
  toggleComposerAssist("employee_create");
}

async function autoCreateEmployeeFromDraftMessage(
  item,
  { resetAssist = false } = {},
) {
  if (!item || item.employeeDraftCreatedName) {
    return false;
  }
  const rawDraft = extractEmployeeDraftPayload(item?.content || "");
  if (!rawDraft) {
    return false;
  }
  const payload = buildEmployeeAutoCreatePayload(rawDraft);
  await openEmployeeDraftCreateDialog(item, payload);
  if (resetAssist && activeComposerAssist.value === "employee_create") {
    activeComposerAssist.value = "";
  }
  return true;
}

async function openEmployeeDraftCreateDialog(item, payload) {
  employeeDraftDialogPayload.value = payload;
  employeeDraftDialogItem.value = item;
  employeeDraftAutoCreateSkills.value = true;
  employeeDraftAutoCreateRules.value = true;
  employeeDraftAddToProject.value = Boolean(
    String(selectedProjectId.value || "").trim(),
  );
  employeeDraftDialogVisible.value = true;
}

async function createEmployeeFromDraft(item) {
  const rawDraft = extractEmployeeDraftPayload(item?.content || "");
  if (!rawDraft) {
    ElMessage.warning("当前消息里没有可创建的员工草稿");
    return;
  }
  try {
    const draft = normalizeEmployeeDraftPayload(rawDraft);
    const payload = {
      ...draft,
      add_to_current_project: Boolean(
        String(selectedProjectId.value || "").trim(),
      ),
      memory_retention_days: Math.min(
        365,
        Math.max(7, Number(draft.memory_retention_days || 90)),
      ),
    };
    await openEmployeeDraftCreateDialog(item, payload);
  } catch {}
}

async function confirmEmployeeDraftCreation(options = {}) {
  const payload = employeeDraftDialogPayload.value;
  const item = employeeDraftDialogItem.value;
  if (!payload || !item) {
    employeeDraftDialogVisible.value = false;
    return;
  }
  employeeDraftCreatingKey.value = getEmployeeDraftKey(item);
  try {
    const employee = await handleQuickCreateEmployee({
      ...payload,
      skills: Array.isArray(payload.skills) ? payload.skills : [],
      rule_drafts: Array.isArray(payload.rule_drafts)
        ? payload.rule_drafts
        : [],
      add_to_current_project:
        options?.add_to_current_project ?? employeeDraftAddToProject.value,
      auto_create_missing_skills:
        options?.auto_create_missing_skills ??
        employeeDraftAutoCreateSkills.value,
      auto_create_missing_rules:
        options?.auto_create_missing_rules ??
        employeeDraftAutoCreateRules.value,
    });
    item.employeeDraftCreatedName = String(
      employee?.name || payload.name || "",
    ).trim();
    employeeDraftDialogVisible.value = false;
  } finally {
    employeeDraftCreatingKey.value = "";
  }
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

function applyStarterPrompt(prompt) {
  draftText.value = String(prompt || "").trim();
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

function handleEditorCompositionStart() {
  editorComposing.value = true;
}

function handleEditorCompositionEnd() {
  editorComposing.value = false;
}

function handleEditorBlur() {
  inputFocused.value = false;
}

function handleEditorKeydown(event) {
  const nativeEvent = event;
  const isImeComposing =
    editorComposing.value ||
    Boolean(nativeEvent?.isComposing) ||
    Number(nativeEvent?.keyCode || 0) === 229;
  if (event.key === "Enter" && !event.shiftKey && !isImeComposing) {
    event.preventDefault();
    void doSend();
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

function handleEditorPaste(event) {
  handlePaste(event);
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

function normalizeRuntimeExternalTools(payload) {
  if (!Array.isArray(payload)) return [];
  return payload
    .map((item) => ({
      tool_name: String(item?.tool_name || "").trim(),
      remote_tool_name: String(item?.remote_tool_name || "").trim(),
      module_name: String(item?.module_name || "").trim(),
      module_source: String(item?.module_source || "").trim(),
      description: String(item?.description || "").trim(),
      disabled: Boolean(item?.disabled),
    }))
    .filter((item) => item.tool_name && !item.disabled);
}

function mergeToolPriority(baseNames, promotedNames) {
  return normalizeStringList([...(promotedNames || []), ...(baseNames || [])]);
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

function toggleComposerAssist(actionId) {
  const normalized = String(actionId || "").trim();
  if (!normalized) return;
  if (activeComposerAssist.value === normalized) {
    activeComposerAssist.value = "";
    return;
  }
  const action = composerAssistActions.value.find(
    (item) => item.id === normalized,
  );
  if (!action) return;
  activeComposerAssist.value = normalized;
  if (normalized === "employee_create") {
    void ensureEmployeeDraftCatalog().catch(() => {});
  }
  draftText.value = String(action.seedText || "").trim();
}

function syncSettingsRouteState() {
  if (!isChatSettingsRoutePath(route.path)) {
    activeSettingsPanel.value = "chat";
    return;
  }
  const requestedPanel = inferSettingsPanelFromPath(route.path);
  const matched =
    settingsCenterItems.value.find((item) => item.id === requestedPanel) ||
    settingsInternalItems.value[0] ||
    settingsCenterItems.value[0] ||
    null;
  if (!matched) return;
  activeSettingsPanel.value = matched.id;
  if (matched.id !== requestedPanel) {
    const targetPath = buildChatSettingsRoute(matched.path || "/chat");
    if (route.path !== targetPath) {
      void router.replace(targetPath);
    }
  }
}

function openSettingsCenter(panelId = "chat") {
  const normalized = String(panelId || "chat").trim() || "chat";
  const matched = settingsCenterItems.value.find(
    (item) => item.id === normalized,
  );
  void router.push(buildChatSettingsRoute(matched?.path || "/chat"));
}

function closeSettingsCenter() {
  void router.push(CHAT_BASE_ROUTE_PATH);
}

async function startChatTour(force = false) {
  const username = currentUsername.value;
  const roleId = currentRoleId.value;
  if (!force && hasSeenGuideTour("chat", username, roleId)) return;
  settingsTourVisible.value = false;
  chatTourCurrent.value = 0;
  await nextTick();
  chatTourVisible.value = true;
}

async function startSettingsTour(force = false) {
  const username = currentUsername.value;
  const roleId = currentRoleId.value;
  if (!force && hasSeenGuideTour("settings", username, roleId)) return;
  chatTourVisible.value = false;
  if (!isSettingsCenterRoute.value || activeSettingsPanel.value !== "chat") {
    await router.push(buildChatSettingsRoute("/chat"));
  }
  settingsTourCurrent.value = 0;
  await nextTick();
  settingsTourVisible.value = true;
}

function handleChatTourClose() {
  chatTourVisible.value = false;
  markGuideTourSeen("chat", currentUsername.value, currentRoleId.value);
}

function handleChatTourFinish() {
  chatTourVisible.value = false;
  markGuideTourSeen("chat", currentUsername.value, currentRoleId.value);
}

function handleSettingsTourClose() {
  settingsTourVisible.value = false;
  markGuideTourSeen("settings", currentUsername.value, currentRoleId.value);
}

function handleSettingsTourFinish() {
  settingsTourVisible.value = false;
  markGuideTourSeen("settings", currentUsername.value, currentRoleId.value);
}

function handleProjectCommand(projectId) {
  selectedProjectId.value = String(projectId || "").trim();
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
    employeeDraftAutoRuleGenerationEnabled.value =
      !Object.prototype.hasOwnProperty.call(
        data?.config || {},
        "employee_auto_rule_generation_enabled",
      ) || !!data?.config?.employee_auto_rule_generation_enabled;
    employeeDraftAutoRuleGenerationSourceFilters.value = normalizeStringList(
      data?.config?.employee_auto_rule_generation_source_filters || [
        "prompts_chat_curated",
      ],
      8,
    );
    employeeDraftExternalSkillSites.value = (
      Array.isArray(data?.config?.employee_external_skill_sites)
        ? data.config.employee_external_skill_sites
        : []
    )
      .map(normalizeEmployeeDraftExternalSkillSite)
      .filter((item) => item.url && item.title);
    employeeDraftAutoRuleGenerationMaxCount.value = Math.min(
      6,
      Math.max(
        1,
        Number(data?.config?.employee_auto_rule_generation_max_count || 3),
      ),
    );
  } catch (err) {
    console.error("加载系统配置失败", err);
    employeeDraftAutoRuleGenerationEnabled.value = true;
    employeeDraftAutoRuleGenerationSourceFilters.value = [
      "prompts_chat_curated",
    ];
    employeeDraftExternalSkillSites.value = [];
    employeeDraftAutoRuleGenerationMaxCount.value = 3;
  }
}

async function fetchModelTypeOptions() {
  try {
    const data = await fetchDictionary("llm_model_types");
    const options = Array.isArray(data?.options) ? data.options : [];
    if (options.length) {
      modelTypeOptions.value = options;
    }
  } catch (err) {
    modelTypeOptions.value = FALLBACK_MODEL_TYPE_OPTIONS;
    console.warn("加载模型类型失败", err);
  }
}

async function fetchChatParameterOptions() {
  const next = {};
  await Promise.all(
    listChatParameterKeys().map(async (parameterKey) => {
      const dictionaryKey = getChatParameterDictionaryKey(parameterKey);
      try {
        const data = await fetchDictionary(dictionaryKey);
        next[parameterKey] = {
          options: Array.isArray(data?.options) ? data.options : [],
          defaultValue: data?.default_value,
        };
      } catch (err) {
        next[parameterKey] = {
          options: [],
          defaultValue: undefined,
        };
        console.warn(`加载参数字典失败: ${dictionaryKey}`, err);
      }
    }),
  );
  chatParameterOptions.value = next;
  projectChatSettings.value = applyLocalConnectorRuntimeSettings(
    projectChatSettings.value,
  );
}

async function fetchProjects() {
  const data = await api.get("/projects");
  projects.value = data.projects || [];
  if (!projects.value.length) {
    localStorage.removeItem("project_id");
    return;
  }
  const savedProjectId = String(
    localStorage.getItem("project_id") || "",
  ).trim();
  if (
    savedProjectId &&
    !(projects.value || []).some((item) => item.id === savedProjectId)
  ) {
    localStorage.removeItem("project_id");
  }
}

async function fetchGlobalProviders() {
  const providerData = await api.get("/llm/providers", {
    params: { enabled_only: true },
  });
  const list = Array.isArray(providerData?.providers)
    ? providerData.providers
    : [];
  providers.value = list;
  localConnectors.value = [];
  desktopConnectorArtifacts.value = [];
  globalDefaultProviderId.value = String(
    list.find((item) => Boolean(item?.is_default))?.id || list[0]?.id || "",
  ).trim();
  const provider =
    list.find((item) => item.id === globalDefaultProviderId.value) ||
    list[0] ||
    {};
  const models = normalizeProviderModelNames(provider, modelTypeOptions.value);
  globalDefaultModelName.value = String(
    provider?.default_model || models[0] || "",
  ).trim();
  defaultProviderId.value = globalDefaultProviderId.value;
  defaultModelName.value = globalDefaultModelName.value;

  const currentProviderValid = list.some(
    (item) =>
      String(item?.id || "").trim() ===
      String(selectedProviderId.value || "").trim(),
  );
  if (!currentProviderValid) {
    selectedProviderId.value = globalDefaultProviderId.value;
  }
  const selectedProvider =
    list.find((item) => item.id === selectedProviderId.value) || provider;
  const selectedModels = normalizeProviderModelNames(
    selectedProvider,
    modelTypeOptions.value,
  );
  if (
    !selectedModelName.value ||
    !selectedModels.includes(String(selectedModelName.value || "").trim())
  ) {
    selectedModelName.value = String(
      selectedProvider?.default_model ||
        selectedModels[0] ||
        globalDefaultModelName.value ||
        "",
    ).trim();
  }
  projectChatSettings.value = applyLocalConnectorRuntimeSettings(
    projectChatSettings.value,
    String(selectedProjectId.value || "").trim(),
    localConnectors.value,
  );
}

async function refreshLocalConnectorCatalog(silent = true) {
  if (localConnectorRefreshing.value) {
    return;
  }
  localConnectorRefreshing.value = true;
  try {
    const projectId = String(selectedProjectId.value || "").trim();
    if (projectId) {
      await fetchProvidersByProject(projectId);
    } else {
      await fetchGlobalProviders();
    }
    if (!silent) {
      ElMessage.success("连接器列表已刷新");
    }
  } catch (err) {
    if (!silent) {
      ElMessage.error(err?.detail || err?.message || "刷新连接器失败");
    }
  } finally {
    localConnectorRefreshing.value = false;
  }
}

function syncProjectFromRoute() {
  const { projectId: routeProjectId } = routeChatTarget();
  const savedProjectId = String(
    localStorage.getItem("project_id") || "",
  ).trim();
  const initialProjectId = resolveAvailableProjectId(
    routeProjectId || savedProjectId,
  );
  if (initialProjectId) {
    selectedProjectId.value = initialProjectId;
    localStorage.setItem("project_id", initialProjectId);
    return;
  }
  clearSelectedProjectState();
}

async function handleProjectCreated(event) {
  const createdProjectId = String(event?.detail?.projectId || "").trim();
  await fetchProjects();
  const nextProjectId = resolveAvailableProjectId(
    createdProjectId || localStorage.getItem("project_id") || "",
  );
  if (!nextProjectId) return;
  if (nextProjectId === String(selectedProjectId.value || "").trim()) {
    localStorage.setItem("project_id", nextProjectId);
    return;
  }
  selectedProjectId.value = nextProjectId;
}

async function fetchProvidersByProject(projectId) {
  projectSettingsHydrating.value = true;
  if (!projectId) {
    projectEmployees.value = [];
    externalAgentInfo.value = normalizeExternalAgentInfo({});
    mcpModules.value = normalizeMcpModules({});
    runtimeExternalTools.value = [];
    externalMcpTotal.value = 0;
    activeMcpSource.value = "system";
    selectedProjectToolNames.value = [];
    selectedEmployeeIds.value = [];
    systemPrompt.value = "";
    temperature.value = CHAT_SETTINGS_DEFAULTS.temperature;
    chatMaxTokens.value = CHAT_SETTINGS_DEFAULTS.max_tokens;
    activeComposerAssist.value = "";
    void stopTerminalMirror().catch(() => {});
    resetTerminalPanel();
    projectWorkspacePath.value = "";
    workspacePathDraft.value = "";
    projectAiEntryFile.value = "";
    aiEntryFileDraft.value = "";
    chatSessions.value = [];
    currentChatSessionId.value = "";
    autoSaveState.value = "idle";
    autoSaveUpdatedAt.value = "";
    lastAutoSavedFingerprint = "";
    await fetchGlobalProviders();
    projectChatSettings.value = applyLocalConnectorRuntimeSettings({
      ...CHAT_SETTINGS_DEFAULTS,
    });
    projectSettingsHydrating.value = false;
    return;
  }
  let hydrated = false;
  try {
    const data = await api.get(buildProjectProvidersRequestUrl(projectId));
    const rawSettings =
      data?.chat_settings && typeof data.chat_settings === "object"
        ? data.chat_settings
        : {};
    providers.value = data.providers || [];
    localConnectors.value = [];
    const settings = applyLocalConnectorRuntimeSettings(rawSettings);
    projectChatSettings.value = settings;
    projectEmployees.value = data.employees || [];
    externalAgentInfo.value = normalizeExternalAgentInfo({
      ...(data?.external_agent && typeof data.external_agent === "object"
        ? data.external_agent
        : {}),
      workspace_access:
        data?.workspace_access ||
        data?.external_agent?.workspace_access ||
        undefined,
    });
    projectWorkspacePath.value = String(
      data?.project_workspace_path || "",
    ).trim();
    projectAiEntryFile.value = String(data?.project_ai_entry_file || "").trim();
    aiEntryFileDraft.value = projectAiEntryFile.value;
    workspacePathDraft.value = String(
      projectWorkspacePath.value ||
        data?.workspace_path ||
        data?.external_agent?.workspace_path ||
        "",
    ).trim();
    mcpModules.value = normalizeMcpModules(data.mcp_modules || {});
    runtimeExternalTools.value = normalizeRuntimeExternalTools(
      data?.runtime_external_tools || [],
    );
    externalMcpTotal.value = Number(
      data?.mcp_modules?.summary?.external_total ||
        mcpModules.value?.external?.modules?.length ||
        0,
    );
    if (
      activeComposerAssist.value &&
      !composerAssistActions.value.some(
        (item) => item.id === activeComposerAssist.value,
      )
    ) {
      activeComposerAssist.value = "";
    }
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

    const providerModels = normalizeProviderModelNames(
      providers.value.find((item) => item.id === selectedProviderId.value),
      modelTypeOptions.value,
    );
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
    hydrated = true;
  } finally {
    projectSettingsHydrating.value = false;
    if (hydrated) {
      await nextTick();
      markAutoSaveSynced();
      autoSaveState.value = "saved";
    }
  }
}

async function handleQuickCreateEmployee(payload) {
  employeeCreateSubmitting.value = true;
  try {
    const employeeRes = await api.post("/employees/create-from-draft", {
      name: payload.name,
      description: payload.description || "",
      goal: payload.goal || "",
      tone: payload.tone || "professional",
      verbosity: payload.verbosity || "concise",
      language: payload.language || "zh-CN",
      skills: Array.isArray(payload.skills) ? payload.skills : [],
      rule_ids: Array.isArray(payload.rule_ids) ? payload.rule_ids : [],
      rule_titles: Array.isArray(payload.rule_titles)
        ? payload.rule_titles
        : [],
      rule_domains: Array.isArray(payload.rule_domains)
        ? payload.rule_domains
        : [],
      rule_drafts: Array.isArray(payload.rule_drafts)
        ? payload.rule_drafts
        : [],
      style_hints: Array.isArray(payload.style_hints)
        ? payload.style_hints
        : [],
      default_workflow: Array.isArray(payload.default_workflow)
        ? payload.default_workflow
        : [],
      tool_usage_policy: payload.tool_usage_policy || "",
      auto_evolve: true,
      evolve_threshold: 0.8,
      feedback_upgrade_enabled: false,
      mcp_enabled: true,
      memory_scope: payload.memory_scope || "project",
      memory_retention_days: Number(payload.memory_retention_days || 90),
      auto_create_missing_skills: payload.auto_create_missing_skills !== false,
      auto_create_missing_rules: payload.auto_create_missing_rules !== false,
    });
    const employee = employeeRes?.employee || {};
    const createdSkills = Array.isArray(employeeRes?.created_skills)
      ? employeeRes.created_skills
      : [];
    const importedSystemMcpSkills = Array.isArray(
      employeeRes?.imported_system_mcp_skills,
    )
      ? employeeRes.imported_system_mcp_skills
      : [];
    const createdRules = Array.isArray(employeeRes?.created_rules)
      ? employeeRes.created_rules
      : [];
    const employeeId = String(employee.id || "").trim();
    const projectId = String(selectedProjectId.value || "").trim();
    if (payload.add_to_current_project && projectId && employeeId) {
      await api.post(`/projects/${encodeURIComponent(projectId)}/members`, {
        employee_id: employeeId,
        role: "member",
        enabled: true,
      });
    }
    if (projectId) {
      await fetchProvidersByProject(projectId);
      if (payload.add_to_current_project && employeeId) {
        selectedEmployeeIds.value = [employeeId];
      }
    }
    if (
      createdSkills.length ||
      createdRules.length ||
      importedSystemMcpSkills.length
    ) {
      await ensureEmployeeDraftCatalog(true);
    }
    const createdParts = [];
    if (createdSkills.length) {
      createdParts.push(`技能 ${createdSkills.length} 个`);
    }
    if (importedSystemMcpSkills.length) {
      createdParts.push(`系统MCP技能 ${importedSystemMcpSkills.length} 个`);
    }
    if (createdRules.length) {
      createdParts.push(`规则 ${createdRules.length} 条`);
    }
    ElMessage.success(
      payload.add_to_current_project && projectId
        ? `员工「${employee.name || employeeId}」已创建并加入当前项目${createdParts.length ? `，自动补齐${createdParts.join("、")}` : ""}`
        : `员工「${employee.name || employeeId}」创建成功${createdParts.length ? `，自动补齐${createdParts.join("、")}` : ""}`,
    );
    return employee;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "创建员工失败");
    throw err;
  } finally {
    employeeCreateSubmitting.value = false;
  }
}

function buildProjectChatSettingsPayload() {
  const employeeIds = normalizeStringList(selectedEmployeeIds.value || []);
  return applyLocalConnectorRuntimeSettings({
    ...projectChatSettings.value,
    chat_mode: "system",
    selected_employee_id: employeeIds.length === 1 ? employeeIds[0] : "",
    selected_employee_ids: employeeIds,
    employee_coordination_mode: String(
      projectChatSettings.value.employee_coordination_mode ||
        CHAT_SETTINGS_DEFAULTS.employee_coordination_mode,
    )
      .trim()
      .toLowerCase(),
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

const autoSaveFingerprint = computed(() => {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId || projectSettingsHydrating.value) return "";
  return JSON.stringify(buildProjectChatSettingsPayload());
});

function clearAutoSaveTimer() {
  if (autoSaveTimer) {
    window.clearTimeout(autoSaveTimer);
    autoSaveTimer = null;
  }
}

function markAutoSaveSynced() {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return;
  clearAutoSaveTimer();
  lastAutoSavedFingerprint = JSON.stringify(buildProjectChatSettingsPayload());
}

function scheduleAutoSave() {
  if (!selectedProjectId.value || projectSettingsHydrating.value) return;
  const fingerprint = autoSaveFingerprint.value;
  if (!fingerprint || fingerprint === lastAutoSavedFingerprint) return;
  clearAutoSaveTimer();
  autoSaveState.value = "pending";
  autoSaveTimer = window.setTimeout(async () => {
    autoSaveTimer = null;
    await saveProjectChatSettings(true);
  }, 700);
}

async function saveProjectChatSettings(silent = false) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    if (!silent) {
      ElMessage.warning("请先选择项目");
    }
    return;
  }
  clearAutoSaveTimer();
  autoSaveState.value = "saving";
  settingsSaving.value = true;
  try {
    const payload = buildProjectChatSettingsPayload();
    const data = await api.put(
      `/projects/${encodeURIComponent(projectId)}/chat/settings`,
      { settings: payload },
    );
    projectChatSettings.value = applyLocalConnectorRuntimeSettings(
      data?.settings || payload,
    );
    // 以服务端回读结果为准，避免“保存成功但界面仍旧值”的状态分叉。
    await fetchProvidersByProject(projectId);
    markAutoSaveSynced();
    autoSaveState.value = "saved";
    autoSaveUpdatedAt.value = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    if (!silent) {
      ElMessage.success("项目对话设置已保存");
    }
  } catch (err) {
    autoSaveState.value = "error";
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
  const videos = Array.isArray(item?.videos) ? item.videos : [];
  return {
    id: String(item?.id || ""),
    role: String(item?.role || "assistant"),
    content: String(item?.content || ""),
    displayMode: String(item?.display_mode || "").trim(),
    terminalLog: [],
    processExpanded: false,
    audit: null,
    images: images,
    videos: videos,
    attachments,
    time: String(item?.created_at || ""),
  };
}

async function fetchChatSessions(projectId, preferredSessionId = "") {
  if (!projectId) {
    chatSessions.value = [];
    currentChatSessionId.value = "";
    messages.value = [];
    chatHistoryLoadedCount.value = 0;
    return "";
  }
  try {
    const data = await api.get(
      `/projects/${encodeURIComponent(projectId)}/chat/sessions`,
      {
        params: { limit: 50 },
      },
    );
    chatSessions.value = (data.sessions || []).map(normalizeChatSession);
    const remembered = restoreChatSession(projectId);
    const preferred = String(preferredSessionId || "").trim() || remembered;
    const fallback = String(chatSessions.value[0]?.id || "").trim();
    const resolved =
      [preferred, fallback].find(
        (candidate) =>
          candidate && chatSessions.value.some((item) => item.id === candidate),
      ) || "";
    currentChatSessionId.value = resolved;
    rememberChatSession(projectId, resolved);
    return resolved;
  } catch (err) {
    chatSessions.value = [];
    currentChatSessionId.value = "";
    chatHistoryLoadedCount.value = 0;
    ElMessage.error(err?.detail || err?.message || "加载会话列表失败");
    return "";
  }
}

async function fetchChatHistory(
  projectId,
  chatSessionId = currentChatSessionId.value,
  options = {},
) {
  if (!projectId) {
    messages.value = [];
    chatHistoryLoadedCount.value = 0;
    return;
  }
  const normalizedSessionId = String(chatSessionId || "").trim();
  currentChatSessionId.value = normalizedSessionId;
  if (!normalizedSessionId) {
    messages.value = [];
    chatHistoryLoadedCount.value = 0;
    return;
  }
  const append = options.append === true;
  const offset = Math.max(0, Number(options.offset ?? 0) || 0);
  const limit = Math.max(
    1,
    Number(options.limit || CHAT_HISTORY_PAGE_SIZE) || CHAT_HISTORY_PAGE_SIZE,
  );
  const container = messagesContainer.value;
  const previousScrollHeight = Number(container?.scrollHeight || 0);
  const previousScrollTop = Number(container?.scrollTop || 0);
  try {
    const data = await api.get(
      `/projects/${encodeURIComponent(projectId)}/chat/history`,
      {
        params: {
          limit,
          offset,
          chat_session_id: normalizedSessionId,
        },
      },
    );
    const historyRows = (data.messages || []).map(mapHistoryMessage);
    messages.value = append ? [...historyRows, ...messages.value] : historyRows;
    chatHistoryLoadedCount.value = messages.value.length;
    rememberChatSession(projectId, normalizedSessionId);
    if (append) {
      nextTick(() => {
        if (!messagesContainer.value) return;
        const nextScrollHeight = Number(
          messagesContainer.value.scrollHeight || 0,
        );
        messagesContainer.value.scrollTop =
          nextScrollHeight - previousScrollHeight + previousScrollTop;
      });
    } else {
      scrollToBottom();
    }
  } catch (err) {
    if (!append) {
      messages.value = [];
      chatHistoryLoadedCount.value = 0;
    }
    ElMessage.error(
      err?.detail ||
        err?.message ||
        (append ? "加载更早消息失败" : "加载聊天记录失败"),
    );
  }
}

async function loadOlderMessages() {
  const projectId = String(selectedProjectId.value || "").trim();
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  if (!projectId || !chatSessionId || chatHistoryLoadingMore.value) return;
  if (!chatHistoryHasMore.value) return;
  chatHistoryLoadingMore.value = true;
  try {
    await fetchChatHistory(projectId, chatSessionId, {
      append: true,
      offset: chatHistoryLoadedCount.value,
      limit: CHAT_HISTORY_PAGE_SIZE,
    });
  } finally {
    chatHistoryLoadingMore.value = false;
  }
}

function handleProviderChange() {
  const selected = (providers.value || []).find(
    (item) => item.id === selectedProviderId.value,
  );
  const modelList = normalizeProviderModelNames(
    selected,
    modelTypeOptions.value,
  );
  if (
    !selectedModelName.value ||
    !modelList.includes(selectedModelName.value)
  ) {
    selectedModelName.value = String(
      selected?.default_model || modelList[0] || "",
    );
  }
}

function resetExternalAgentRuntimeState() {
  externalAgentWarmupKey.value = "";
  externalAgentWarmupLoading.value = false;
  externalAgentInfo.value = normalizeExternalAgentInfo({
    ...externalAgentInfo.value,
    ready: false,
    session_id: "",
    thread_id: "",
    workspace_path: usingLocalConnector.value
      ? String(
          projectChatSettings.value.connector_workspace_path ||
            workspacePathDraftNormalized.value ||
            "",
        ).trim()
      : String(
          projectWorkspacePath.value ||
            externalAgentInfo.value.workspace_path ||
            "",
        ).trim(),
  });
  resetTerminalPanel();
}

async function createChatSession(options = {}) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    return null;
  }
  creatingChatSession.value = true;
  try {
    const data = await api.post(
      `/projects/${encodeURIComponent(projectId)}/chat/sessions`,
      {},
    );
    const session = normalizeChatSession(data.session || {});
    if (!session.id) {
      throw new Error("创建会话失败");
    }
    chatSessions.value = [
      session,
      ...chatSessions.value.filter((item) => item.id !== session.id),
    ];
    if (options.switchTo !== false) {
      currentChatSessionId.value = session.id;
      rememberChatSession(projectId, session.id);
      messages.value = [];
      chatHistoryLoadedCount.value = 0;
      scrollToBottom();
    }
    return session;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "创建新对话失败");
    return null;
  } finally {
    creatingChatSession.value = false;
  }
}

const LOCAL_CONNECTOR_RUNTIME_PORTS = Array.from(
  { length: 21 },
  (_item, index) => 3931 + index,
);

async function readLocalConnectorError(response, fallbackMessage) {
  try {
    const payload = await response.json();
    return (
      String(
        payload?.detail || payload?.message || fallbackMessage || "",
      ).trim() || fallbackMessage
    );
  } catch (_error) {
    return fallbackMessage;
  }
}

async function resolveBrowserConnectorRuntimeUrl() {
  for (const port of LOCAL_CONNECTOR_RUNTIME_PORTS) {
    const baseUrl = `http://127.0.0.1:${port}`;
    try {
      const response = await fetch(`${baseUrl}/health`, {
        method: "GET",
        cache: "no-store",
      });
      if (response.ok) {
        return baseUrl;
      }
    } catch (_error) {
      // try next port
    }
  }
  throw new Error("未检测到本机 Local Connector，请先启动桌面连接器");
}

async function pairBrowserLocalConnector() {
  if (localConnectorPairing.value) {
    return;
  }
  localConnectorPairing.value = true;
  try {
    const data = await api.post("/local-connectors/pair/browser-session");
    const pairing = data?.pairing || {};
    const pairCode = String(pairing.pair_code || "").trim();
    const platformUrl = String(pairing.platform_url || "").trim();
    if (!pairCode || !platformUrl) {
      throw new Error("服务端没有返回可用的配对信息");
    }
    const runtimeUrl = await resolveBrowserConnectorRuntimeUrl();
    const response = await fetch(`${runtimeUrl}/pairing/connect`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        pair_code: pairCode,
        platform_url: platformUrl,
      }),
    });
    if (!response.ok) {
      throw new Error(
        await readLocalConnectorError(response, "本机连接器认证失败"),
      );
    }
    const payload = await response.json().catch(() => ({}));
    const connectorId = String(payload?.pairing?.connector_id || "").trim();
    await refreshLocalConnectorCatalog(true);
    if (connectorId) {
      projectChatSettings.value.local_connector_id = connectorId;
    }
    ElMessage.success("本机连接器已认证成功，请保存当前设置");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "匹配本地连接器失败");
  } finally {
    localConnectorPairing.value = false;
  }
}

async function requestWorkspacePickSession(connectorId) {
  return api.post(
    `/local-connectors/${encodeURIComponent(connectorId)}/workspace-pick/session`,
  );
}

async function pickWorkspaceViaLocalConnector(connectorId, options = {}) {
  const normalizedConnectorId = String(connectorId || "").trim();
  if (!normalizedConnectorId) {
    throw new Error("缺少本地连接器 ID");
  }
  const data = await requestWorkspacePickSession(normalizedConnectorId);
  const session = data?.workspace_pick || {};
  const sessionId = String(session.session_id || "").trim();
  const sessionToken = String(session.session_token || "").trim();
  const platformUrl = String(session.platform_url || "").trim();
  if (!sessionId || !sessionToken || !platformUrl) {
    throw new Error("服务端没有返回可用的目录选择会话");
  }
  const runtimeUrl = await resolveBrowserConnectorRuntimeUrl();
  const response = await fetch(`${runtimeUrl}/workspace/pick`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      platform_url: platformUrl,
      session_id: sessionId,
      session_token: sessionToken,
      title:
        String(options?.title || "").trim() ||
        `选择项目工作区目录 · ${String(currentProjectLabel.value || "").trim() || "AI 对话中心"}`,
      initial_path: String(
        options?.initialPath ||
          workspacePathDraftNormalized.value ||
          workspacePathResolved.value ||
          "",
      ).trim(),
    }),
  });
  if (!response.ok) {
    throw new Error(
      await readLocalConnectorError(response, "本机目录选择失败"),
    );
  }
  return response.json();
}

async function downloadDesktopConnectorArtifact(item) {
  const filename = String(item?.filename || "").trim();
  if (!filename) {
    ElMessage.warning("缺少桌面安装包文件名");
    return;
  }
  downloadingDesktopArtifactKey.value = filename;
  try {
    const response = await api.get(
      "/local-connectors/desktop-artifacts/download",
      {
        params: { name: filename },
        responseType: "blob",
      },
    );
    const url = URL.createObjectURL(response);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success("桌面安装包已下载");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "下载桌面安装包失败");
  } finally {
    downloadingDesktopArtifactKey.value = "";
  }
}

async function handleCreateNewConversation() {
  if (
    !String(selectedProjectId.value || "").trim() &&
    ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
  ) {
    currentChatSessionId.value = "";
    messages.value = [];
    chatHistoryLoadedCount.value = 0;
    activeComposerAssist.value = "";
    resetDraft();
    scrollToBottom();
    return;
  }
  const session = await createChatSession({ switchTo: true });
  if (!session) return;
  resetDraft();
}

async function selectChatSession(sessionId) {
  const projectId = String(selectedProjectId.value || "").trim();
  const normalizedSessionId = String(sessionId || "").trim();
  if (!projectId || !normalizedSessionId) return;
  if (chatLoading.value) {
    ElMessage.warning("当前回答进行中，暂时不能切换会话");
    return;
  }
  await fetchChatHistory(projectId, normalizedSessionId);
}

async function deleteChatSession(session) {
  const projectId = String(selectedProjectId.value || "").trim();
  const chatSessionId = String(session?.id || "").trim();
  if (!projectId || !chatSessionId) return;
  if (chatLoading.value && currentChatSessionId.value === chatSessionId) {
    ElMessage.warning("当前回答进行中，暂时不能删除这个会话");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确认删除会话「${String(session?.title || "新对话")}」吗？删除后不可恢复。`,
      "删除历史对话",
      {
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  deletingChatSessionId.value = chatSessionId;
  try {
    await api.delete(
      `/projects/${encodeURIComponent(projectId)}/chat/history`,
      {
        params: { chat_session_id: chatSessionId },
      },
    );
    chatSessions.value = chatSessions.value.filter(
      (item) => item.id !== chatSessionId,
    );
    const isCurrentSession = currentChatSessionId.value === chatSessionId;
    if (isCurrentSession) {
      clearChatSessionMemory(projectId);
      const nextSessionId = String(chatSessions.value[0]?.id || "").trim();
      if (nextSessionId) {
        await fetchChatHistory(projectId, nextSessionId);
      } else {
        currentChatSessionId.value = "";
        messages.value = [];
        await createChatSession({ switchTo: true });
      }
    }
    ElMessage.success("历史对话已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除历史对话失败");
  } finally {
    deletingChatSessionId.value = "";
  }
}

async function clearMessages() {
  const projectId = String(selectedProjectId.value || "").trim();
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  if (!projectId || !chatSessionId) {
    messages.value = [];
    return;
  }
  try {
    await api.delete(
      `/projects/${encodeURIComponent(projectId)}/chat/history`,
      {
        params: { chat_session_id: chatSessionId },
      },
    );
    messages.value = [];
    chatHistoryLoadedCount.value = 0;
    chatSessions.value = chatSessions.value.filter(
      (item) => item.id !== chatSessionId,
    );
    clearChatSessionMemory(projectId);
    const nextSessionId = String(chatSessions.value[0]?.id || "").trim();
    if (nextSessionId) {
      await fetchChatHistory(projectId, nextSessionId);
    } else {
      currentChatSessionId.value = "";
      await createChatSession({ switchTo: true });
    }
    ElMessage.success("当前会话已清空");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "清空当前会话失败");
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

async function handleSocketMessage(eventData) {
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
    appendTerminalPanelLine(
      `# 会话已预热 · thread=${String(eventData?.thread_id || "-").trim() || "-"}`,
    );
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
    appendTerminalPanelLine(
      `# 真实终端镜像已连接 · thread=${String(eventData?.thread_id || "-").trim() || "-"}`,
    );
    const mirrorRow = messages.value[activeTerminalMirrorAssistantIndex.value];
    if (mirrorRow) {
      appendTerminalLog(
        mirrorRow,
        `# 真实终端镜像已连接 · thread=${String(eventData?.thread_id || "-").trim() || "-"}`,
      );
    }
    return;
  }
  if (eventType === "terminal_mirror_stopped") {
    terminalMirrorConnected.value = false;
    appendTerminalPanelLine(`# 真实终端镜像已停止`);
    const mirrorRow = messages.value[activeTerminalMirrorAssistantIndex.value];
    if (mirrorRow) {
      appendTerminalLog(mirrorRow, "# 真实终端镜像已停止");
    }
    activeTerminalMirrorAssistantIndex.value = -1;
    return;
  }
  if (eventType === "terminal_mirror_chunk") {
    terminalMirrorConnected.value = true;
    const chunk = String(eventData?.content || "");
    appendTerminalPanelLine(chunk);
    const mirrorRow = messages.value[activeTerminalMirrorAssistantIndex.value];
    if (mirrorRow) {
      appendTerminalLog(mirrorRow, chunk);
    }
    return;
  }
  if (eventType === "terminal_approval_required") {
    const mirrorRow = messages.value[activeTerminalMirrorAssistantIndex.value];
    if (mirrorRow) {
      appendAssistantStatusNote(
        mirrorRow,
        "> ⏳ 终端请求审批，请在弹框中继续。",
      );
    }
    setTerminalApprovalPrompt({
      key: String(eventData?.key || "").trim(),
      title: String(eventData?.title || "检测到终端审批").trim(),
      description: String(
        eventData?.description || "当前操作需要用户确认后才会继续执行。",
      ).trim(),
      message: String(eventData?.message || "").trim(),
    });
    scrollToBottom();
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
    pendingPrepare?.reject(
      new Error(String(eventData?.message || "外部 Agent 预热失败")),
    );
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
    row.effectiveTools = normalizeEffectiveTools(eventData?.effective_tools);
    row.effectiveToolTotal = Number(
      eventData?.effective_tool_total || row.effectiveTools.length || 0,
    );
    if (String(eventData?.chat_mode || "").trim() === "external_agent") {
      externalAgentInfo.value = normalizeExternalAgentInfo({
        ...externalAgentInfo.value,
        ...eventData,
        ready: true,
        session_id: String(
          eventData?.agent_session_id ||
            externalAgentInfo.value.session_id ||
            "",
        ).trim(),
        support_dir: String(
          eventData?.support_dir || externalAgentInfo.value.support_dir || "",
        ).trim(),
        mcp_bridge_enabled: Boolean(
          eventData?.mcp_bridge_enabled ??
          externalAgentInfo.value.mcp_bridge_enabled,
        ),
        mcp_bridge_reason: String(
          eventData?.mcp_bridge_reason ||
            externalAgentInfo.value.mcp_bridge_reason ||
            "",
        ).trim(),
        mcp_server_name: String(
          eventData?.mcp_server_name ||
            externalAgentInfo.value.mcp_server_name ||
            "",
        ).trim(),
        support_files: Array.isArray(eventData?.support_files)
          ? eventData.support_files.map((item) => ({
              kind: String(item?.kind || "file").trim(),
              label: String(item?.label || item?.path || "文件").trim(),
              path: String(item?.path || "").trim(),
              written: Boolean(item?.written),
            }))
          : externalAgentInfo.value.support_files,
        execution_mode: String(
          eventData?.execution_mode ||
            externalAgentInfo.value.execution_mode ||
            "local",
        ).trim(),
        runner_url: String(
          eventData?.runner_url || externalAgentInfo.value.runner_url || "",
        ).trim(),
        materialized_by: String(
          eventData?.materialized_by ||
            externalAgentInfo.value.materialized_by ||
            "",
        ).trim(),
        workspace_access:
          eventData?.workspace_access &&
          typeof eventData.workspace_access === "object"
            ? {
                configured: Boolean(eventData.workspace_access.configured),
                exists: Boolean(eventData.workspace_access.exists),
                is_dir: Boolean(eventData.workspace_access.is_dir),
                read_ok: Boolean(eventData.workspace_access.read_ok),
                write_ok: Boolean(eventData.workspace_access.write_ok),
                source: String(eventData.workspace_access.source || "").trim(),
                sandbox_mode:
                  String(
                    eventData.workspace_access.sandbox_mode ||
                      eventData?.sandbox_mode ||
                      "workspace-write",
                  ).trim() || "workspace-write",
                reason: String(eventData.workspace_access.reason || "").trim(),
              }
            : externalAgentInfo.value.workspace_access,
      });
      appendTerminalLog(
        row,
        `# ${externalAgentDisplayLabel.value} 已连接 · sandbox=${String(eventData?.sandbox_mode || "workspace-write").trim()} · thread=${String(eventData?.thread_id || "-").trim() || "-"}`,
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
    terminalApprovalDialogVisible.value = false;
    appendAssistantStatusNote(
      row,
      approved ? "> ✅ 已批准，继续执行" : "> ❌ 已拒绝，本次执行取消",
    );
    scrollToBottom();
    return;
  }
  if (eventType === "file_review_required") {
    row.audit = normalizeAuditPayload({
      ...(row.audit && typeof row.audit === "object" ? row.audit : {}),
      after_diff_summary:
        eventData?.diff_summary || row.audit?.after_diff_summary || {},
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
    appendTerminalLog(
      row,
      `› ${String(eventData?.message || "处理中...").trim()}`,
    );
    scrollToBottom();
    return;
  }
  if (eventType === "stderr") {
    appendTerminalLog(row, `! ${String(eventData?.message || "").trim()}`);
    scrollToBottom();
    return;
  }
  if (eventType === "command_start") {
    appendTerminalLog(
      row,
      `$ ${String(eventData?.command || "").trim() || "(command)"}`,
    );
    scrollToBottom();
    return;
  }
  if (eventType === "command_result") {
    const exitCode = eventData?.exit_code;
    const statusText =
      String(eventData?.status || "completed").trim() || "completed";
    const exitLabel =
      exitCode === null || exitCode === undefined
        ? statusText
        : `exit=${exitCode}`;
    appendTerminalLog(row, `# 命令完成 · ${exitLabel}`);
    const outputPreview = String(eventData?.output_preview || "").trim();
    if (outputPreview) {
      appendTerminalLog(row, outputPreview);
      if (isMcpApprovalCancelledMessage(outputPreview) && pending) {
        pending.mcpApprovalCancelled = true;
      }
    }
    scrollToBottom();
    return;
  }
  if (eventType === "usage") {
    const usage =
      eventData?.usage && typeof eventData.usage === "object"
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
  if (eventType === "artifact") {
    row.images = mergeImageUrls(
      extractImages(row),
      collectArtifactImageUrls(eventData),
    );
    row.videos = mergeVideoUrls(
      extractVideos(row),
      collectArtifactVideoUrls(eventData),
    );
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
    if (pending) {
      pending.lastToolName = toolName;
    }
    appendAssistantStatusNote(row, `> ⏳ 正在调用工具：\`${toolName}\``);
    scrollToBottom();
    return;
  }
  if (eventType === "tool_result") {
    const toolName = String(eventData?.tool_name || "工具");
    const statusText = String(eventData?.status || "")
      .trim()
      .toLowerCase();
    const outputPreview = String(eventData?.output_preview || "").trim();
    const success =
      !statusText || ["success", "completed", "ok"].includes(statusText);
    const approvalPending = isMcpApprovalCancelledMessage(outputPreview);
    if (approvalPending && pending) {
      pending.mcpApprovalCancelled = true;
      pending.lastToolName = toolName;
    }
    if (approvalPending) {
      appendAssistantStatusNote(row, `> ⏳ 工具调用等待审批：\`${toolName}\``);
    } else if (success) {
      appendAssistantStatusNote(row, `> ✅ 工具调用完成：\`${toolName}\``);
    } else {
      appendAssistantStatusNote(row, `> ❌ 工具调用失败：\`${toolName}\``);
    }
    scrollToBottom();
    return;
  }
  if (eventType === "done") {
    terminalPanelStatus.value = "idle";
    row.images = mergeImageUrls(
      extractImages(row),
      collectArtifactImageUrls(eventData),
    );
    row.videos = mergeVideoUrls(
      extractVideos(row),
      collectArtifactVideoUrls(eventData),
    );
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
    if (pending?.mcpApprovalCancelled) {
      const handedOff = await handoffExternalAgentRequestToTerminal(
        row,
        pending,
      );
      if (handedOff) {
        pending.awaitingTerminalApproval = true;
        scrollToBottom();
        return;
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
    agentType: String(
      projectChatSettings.value.external_agent_type || "codex_cli",
    ).trim(),
    localConnectorId: String(
      projectChatSettings.value.local_connector_id || "",
    ).trim(),
    workspacePath: String(
      workspacePathDraftNormalized.value || workspacePathResolved.value || "",
    ).trim(),
    sandboxMode: String(
      projectChatSettings.value.external_agent_sandbox_mode ||
        "workspace-write",
    ).trim(),
    skillResourceDirectory: String(
      skillResourceDirectoryResolved.value || "",
    ).trim(),
    systemPrompt: String(systemPrompt.value || "").trim(),
    employeeIds: normalizeStringList(selectedEmployeeIds.value || []),
  });
}

async function promptProjectWorkspacePath() {
  if (!usingLocalConnector.value) {
    ElMessage.warning(
      "请先选择本地连接器，再填写连接器所在电脑上的工作区绝对路径",
    );
    return;
  }
  const connectorId = String(
    projectChatSettings.value.local_connector_id || "",
  ).trim();
  if (!connectorId) {
    ElMessage.warning("请先选择本地连接器");
    return;
  }
  workspacePathPicking.value = true;
  try {
    const payload = await pickWorkspaceViaLocalConnector(connectorId);
    const pickedPath = String(payload?.path || "").trim();
    if (payload?.cancelled || !pickedPath) {
      return;
    }
    workspacePathDraft.value = pickedPath;
    await saveProjectWorkspacePath(pickedPath);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "打开本机目录选择器失败");
  } finally {
    workspacePathPicking.value = false;
  }
}

function normalizeAiEntryFileForSave(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) return "";
  const normalizedRelative = toWorkspaceRelativePath(
    rawValue,
    projectWorkspacePath.value,
  );
  return String(normalizedRelative || rawValue).trim();
}

async function promptProjectAiEntryFile() {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    ElMessage.warning("请先选择项目");
    return;
  }
  aiEntryFilePicking.value = true;
  try {
    const pickedPath = await pickWorkspaceFile(
      aiEntryFileDraftNormalized.value || aiEntryFileResolved.value || "",
      {
        title: "选择 AI 入口文件",
        placeholder: ".ai/ENTRY.md",
        basePath: projectWorkspacePath.value,
      },
    );
    if (!pickedPath) {
      return;
    }
    aiEntryFileDraft.value = normalizeAiEntryFileForSave(pickedPath);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "打开文件选择器失败");
  } finally {
    aiEntryFilePicking.value = false;
  }
}

async function saveProjectAiEntryFile(aiEntryFileOverride = null) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    ElMessage.warning("请先选择项目");
    return;
  }
  aiEntryFileSaving.value = true;
  try {
    const normalizedOverride =
      typeof Event !== "undefined" && aiEntryFileOverride instanceof Event
        ? null
        : aiEntryFileOverride;
    const aiEntryFile = normalizeAiEntryFileForSave(
      normalizedOverride ?? aiEntryFileDraft.value ?? "",
    );
    const data = await api.patch(
      `/projects/${encodeURIComponent(projectId)}/chat/ai-entry-file`,
      {
        ai_entry_file: aiEntryFile,
      },
    );
    const persisted = String(data?.ai_entry_file || aiEntryFile).trim();
    projectAiEntryFile.value = persisted;
    aiEntryFileDraft.value = persisted;
    projects.value = (projects.value || []).map((item) =>
      String(item?.id || "").trim() === projectId
        ? { ...item, ai_entry_file: persisted }
        : item,
    );
    ElMessage.success(persisted ? "AI 入口文件已保存" : "已清空 AI 入口文件");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存 AI 入口文件失败");
  } finally {
    aiEntryFileSaving.value = false;
  }
}

async function saveProjectWorkspacePath(workspacePathOverride = null) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    ElMessage.warning("请先选择项目");
    return;
  }
  const normalizedOverride =
    typeof Event !== "undefined" && workspacePathOverride instanceof Event
      ? null
      : workspacePathOverride;
  const workspacePath = String(
    normalizedOverride ?? workspacePathDraft.value ?? "",
  ).trim();
  workspacePathSaving.value = true;
  try {
    if (!usingLocalConnector.value) {
      ElMessage.warning("请先选择本地连接器");
      return;
    }
    const connectorId = String(
      projectChatSettings.value.local_connector_id || "",
    ).trim();
    workspacePathDraft.value = workspacePath;
    writePreferredLocalWorkspacePath(projectId, connectorId, workspacePath);
    projectChatSettings.value = normalizeProjectChatSettings({
      ...projectChatSettings.value,
      connector_workspace_path: workspacePath,
    });
    await fetchProvidersByProject(projectId);
    externalAgentWarmupKey.value = "";
    externalAgentInfo.value = normalizeExternalAgentInfo({
      ...externalAgentInfo.value,
      ready: false,
      session_id: "",
      thread_id: "",
      workspace_path: workspacePath,
    });
    ElMessage.success(
      workspacePath ? "连接器工作区路径已保存" : "已清空连接器工作区路径",
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存工作区路径失败");
  } finally {
    workspacePathSaving.value = false;
  }
}

async function testProjectWorkspacePath() {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    ElMessage.warning("请先选择项目");
    return;
  }
  if (!usingLocalConnector.value) {
    ElMessage.warning("请先选择本地连接器");
    return;
  }
  if (!workspacePathDraftNormalized.value && !workspacePathResolved.value) {
    ElMessage.warning("请先填写工作区绝对路径");
    return;
  }
  workspacePathTesting.value = true;
  try {
    if (workspacePathDirty.value || !workspacePathConfigured.value) {
      await saveProjectWorkspacePath();
    }
    await fetchProvidersByProject(projectId);
    if (!externalAgentInfo.value.workspace_access?.read_ok) {
      throw new Error(
        String(
          externalAgentInfo.value.workspace_access?.reason || "工作区不可访问",
        ),
      );
    }
    ElMessage.success("工作区可用，本地连接器工具已可在该目录执行");
  } catch (err) {
    ElMessage.error(err?.message || "工作区测试失败");
  } finally {
    workspacePathTesting.value = false;
  }
}

async function prepareExternalAgentSession({
  force = false,
  silent = true,
} = {}) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId || !isExternalAgentMode.value) return;
  if (!usingLocalConnector.value) return;
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
      external_agent_type: String(
        projectChatSettings.value.external_agent_type || "codex_cli",
      ).trim(),
      external_agent_sandbox_mode:
        projectChatSettings.value.external_agent_sandbox_mode ||
        "workspace-write",
      connector_sandbox_mode: String(
        projectChatSettings.value.connector_sandbox_mode || "workspace-write",
      ).trim(),
      connector_sandbox_mode_explicit: true,
      local_connector_id: String(
        projectChatSettings.value.local_connector_id || "",
      ).trim(),
      connector_workspace_path: String(
        workspacePathDraftNormalized.value || workspacePathResolved.value || "",
      ).trim(),
      skill_resource_directory: String(
        skillResourceDirectoryResolved.value || "",
      ).trim(),
      employee_ids: employeeIds,
      employee_id: employeeIds.length === 1 ? employeeIds[0] : undefined,
      employee_coordination_mode: String(
        projectChatSettings.value.employee_coordination_mode ||
          CHAT_SETTINGS_DEFAULTS.employee_coordination_mode,
      )
        .trim()
        .toLowerCase(),
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
      isExternalAgentMode.value
        ? "已发送 Ctrl+C 到外部 Agent"
        : "已发送停止指令",
    );
    return;
  }
  ElMessage.warning("当前没有可暂停的生成任务");
}

async function generateEmployeeDraftWithoutProject() {
  const text = String(draftText.value || "").trim();
  if (!text) {
    ElMessage.warning("请先描述你要创建的员工");
    return;
  }
  const userMessage = {
    id: createLocalMessageId(),
    role: "user",
    content: text,
    images: [],
    videos: [],
    attachments: [],
    time: nowText(),
  };
  const assistantMessage = {
    id: createLocalMessageId(),
    role: "assistant",
    content: "",
    images: [],
    videos: [],
    attachments: [],
    displayMode: "",
    terminalLog: [],
    processExpanded: false,
    audit: null,
    time: nowText(),
  };

  const history = messages.value
    .slice(-6)
    .map((item) => ({
      role: String(item?.role || "assistant"),
      content: String(item?.content || ""),
    }))
    .filter(
      (item) =>
        ["user", "assistant"].includes(item.role) && item.content.trim(),
    );

  messages.value.push(userMessage);
  messages.value.push(assistantMessage);

  const assistantIndex = messages.value.length - 1;
  chatLoading.value = true;
  resetDraft();
  scrollToBottom();

  try {
    await ensureEmployeeDraftCatalog();
    const response = await api.post("/employees/generate-draft", {
      message: String(
        [text, "", buildEmployeeDraftAssistContext()]
          .filter(Boolean)
          .join("\n"),
      ),
      history,
      provider_id: String(
        selectedProviderId.value || defaultProviderId.value || "",
      ).trim(),
      model_name: String(
        selectedModelName.value || defaultModelName.value || "",
      ).trim(),
      temperature: Number(
        temperature.value ?? CHAT_SETTINGS_DEFAULTS.temperature,
      ),
      system_prompt:
        "你是 AI 员工架构师。请根据用户需求和现有技能、规则目录生成员工草稿。先给一句简短说明，最后必须附带严格 JSON 的 ```employee-draft``` 代码块；如果能明确整理出可直接落地的员工规则，请输出 rule_drafts 数组，每项包含 title、domain、content。",
    });
    messages.value[assistantIndex].content = String(
      response?.content || "未生成员工草稿。",
    ).trim();
    await autoCreateEmployeeFromDraftMessage(messages.value[assistantIndex], {
      resetAssist: true,
    });
  } catch (err) {
    messages.value[assistantIndex].content =
      `请求失败：${err?.message || "未知错误"}`;
    ElMessage.error(err?.detail || err?.message || "生成员工草稿失败");
  } finally {
    chatLoading.value = false;
    scrollToBottom();
  }
}

async function sendGlobalChatWithoutProject() {
  const text = String(draftText.value || "").trim();
  if (!text) {
    ElMessage.warning("请输入消息内容");
    return;
  }
  const userMessage = {
    id: createLocalMessageId(),
    role: "user",
    content: text,
    images: [],
    videos: [],
    attachments: [],
    time: nowText(),
  };
  const assistantMessage = {
    id: createLocalMessageId(),
    role: "assistant",
    content: "",
    images: [],
    videos: [],
    attachments: [],
    displayMode: "",
    terminalLog: [],
    processExpanded: false,
    audit: null,
    time: nowText(),
  };

  const history = messages.value
    .slice(-10)
    .map((item) => ({
      role: String(item?.role || "assistant"),
      content: String(item?.content || ""),
    }))
    .filter(
      (item) =>
        ["user", "assistant"].includes(item.role) && item.content.trim(),
    );

  messages.value.push(userMessage);
  messages.value.push(assistantMessage);

  const assistantIndex = messages.value.length - 1;
  chatLoading.value = true;
  resetDraft();
  scrollToBottom();

  try {
    const response = await api.post("/projects/chat/global", {
      message: appendModelGenerationInstruction(text),
      history,
      provider_id: String(
        selectedProviderId.value || defaultProviderId.value || "",
      ).trim(),
      model_name: String(
        selectedModelName.value || defaultModelName.value || "",
      ).trim(),
      temperature: Number(
        temperature.value ?? CHAT_SETTINGS_DEFAULTS.temperature,
      ),
      max_tokens: Number(
        chatMaxTokens.value || CHAT_SETTINGS_DEFAULTS.max_tokens,
      ),
      system_prompt: String(systemPrompt.value || "").trim(),
      skill_resource_directory: String(
        skillResourceDirectoryResolved.value || "",
      ).trim(),
      answer_style: String(
        projectChatSettings.value.answer_style ||
          CHAT_SETTINGS_DEFAULTS.answer_style,
      ).trim(),
      prefer_conclusion_first: Boolean(
        projectChatSettings.value.prefer_conclusion_first ??
        CHAT_SETTINGS_DEFAULTS.prefer_conclusion_first,
      ),
    });
    messages.value[assistantIndex].content = String(
      response?.content || "未返回有效内容。",
    ).trim();
  } catch (err) {
    messages.value[assistantIndex].content =
      `请求失败：${err?.message || "未知错误"}`;
    ElMessage.error(err?.detail || err?.message || "通用对话失败");
  } finally {
    chatLoading.value = false;
    scrollToBottom();
  }
}

async function doSend() {
  if (!canSend.value) return;

  if (
    !selectedProjectId.value &&
    activeComposerAssistMeta.value?.id === "employee_create"
  ) {
    await generateEmployeeDraftWithoutProject();
    return;
  }

  if (!selectedProjectId.value) {
    if (ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT) {
      await sendGlobalChatWithoutProject();
      return;
    }
    ElMessage.warning("请先选择项目");
    return;
  }

  const text = String(draftText.value || "").trim();
  let activeChatSessionId = String(currentChatSessionId.value || "").trim();
  if (!activeChatSessionId) {
    const created = await createChatSession({ switchTo: true });
    activeChatSessionId = String(created?.id || "").trim();
    if (!activeChatSessionId) {
      return;
    }
  }
  const files = uploadFiles.value.map((item) => item.raw).filter(Boolean);
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
  const assistAction = activeComposerAssistMeta.value;
  const assistToolNames = normalizeStringList(
    assistAction?.toolNames || [],
    20,
  );
  const shouldInjectAssistPrompt = Boolean(
    assistAction && (assistToolNames.length || assistAction.promptOnly),
  );
  let assistContextText = "";
  if (assistAction?.id === "employee_create") {
    try {
      await ensureEmployeeDraftCatalog();
      assistContextText = buildEmployeeDraftAssistContext();
    } catch (err) {
      console.warn("employee draft catalog load failed", err);
    }
    if (!assistToolNames.length && selectedProjectId.value) {
      ElMessage.warning(
        "当前项目没有可用的远程能力检索工具，本次会回退为基于本地目录的自动创建",
      );
    }
  }
  const effectiveUserPrompt = shouldInjectAssistPrompt
    ? [
        userPrompt,
        "",
        "创作辅助要求：",
        `- 当前已激活：${assistAction.label}`,
        `- ${assistAction.instruction}`,
        assistContextText,
        "- 最终输出请直接给我可使用的结果，不要只停留在工具原始返回。",
      ]
        .filter(Boolean)
        .join("\n")
    : userPrompt;
  const finalUserPrompt = appendModelGenerationInstruction(effectiveUserPrompt);
  const effectiveToolPriority = mergeToolPriority(
    projectChatSettings.value.tool_priority || [],
    assistToolNames,
  );
  const effectiveAutoUseTools =
    assistAction && assistToolNames.length
      ? true
      : singleRoundAnswerOnly.value
        ? false
        : Boolean(
            projectChatSettings.value.auto_use_tools ??
            CHAT_SETTINGS_DEFAULTS.auto_use_tools,
          );
  const userMessage = {
    id: createLocalMessageId(),
    role: "user",
    content: text || "（发送了附件）",
    images: imageUrls,
    videos: [],
    attachments: attachmentNames,
    time: nowText(),
  };
  const assistantMessage = {
    id: createLocalMessageId(),
    role: "assistant",
    content: "",
    images: [],
    videos: [],
    attachments: [],
    displayMode: "",
    effectiveTools: [],
    effectiveToolTotal: 0,
    terminalLog: [],
    processExpanded: false,
    audit: null,
    time: nowText(),
  };

  messages.value.push(userMessage);
  messages.value.push(assistantMessage);

  const assistantIndex = messages.value.length - 1;
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  chatLoading.value = true;
  resetDraft();
  scrollToBottom();

  try {
    const client = await ensureWsClient(selectedProjectId.value);
    const donePromise = new Promise((resolve, reject) => {
      pendingRequests.set(requestId, {
        resolve,
        reject,
        requestId,
        assistantIndex,
        userPrompt: finalUserPrompt,
        mcpApprovalCancelled: false,
        awaitingTerminalApproval: false,
        handoffTriggered: false,
        lastToolName: "",
      });
    });
    const employeeIds = normalizeStringList(selectedEmployeeIds.value || []);
    const requestPayload = {
      request_id: requestId,
      message_id: userMessage.id,
      assistant_message_id: assistantMessage.id,
      chat_session_id: activeChatSessionId,
      chat_mode: "system",
      skill_resource_directory: String(
        skillResourceDirectoryResolved.value || "",
      ).trim(),
      message: finalUserPrompt,
      employee_ids: employeeIds,
      employee_id: employeeIds.length === 1 ? employeeIds[0] : undefined,
      employee_coordination_mode: String(
        projectChatSettings.value.employee_coordination_mode ||
          CHAT_SETTINGS_DEFAULTS.employee_coordination_mode,
      )
        .trim()
        .toLowerCase(),
      history: historyRows,
      provider_id: selectedProviderId.value || undefined,
      model_name: selectedModelName.value || undefined,
      temperature: Number(temperature.value),
      max_tokens: Number(chatMaxTokens.value || 512),
      system_prompt: systemPrompt.value || undefined,
      attachment_names: attachmentNames,
      images: base64Images,
      auto_use_tools: effectiveAutoUseTools,
      tool_priority: effectiveToolPriority,
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
      answer_style: String(
        projectChatSettings.value.answer_style ||
          CHAT_SETTINGS_DEFAULTS.answer_style,
      ),
      prefer_conclusion_first: Boolean(
        projectChatSettings.value.prefer_conclusion_first ??
        CHAT_SETTINGS_DEFAULTS.prefer_conclusion_first,
      ),
    };
    requestPayload.enabled_project_tool_names = normalizeStringList(
      [
        ...selectedProjectToolNames.value,
        ...(assistAction?.id === "employee_create" ? assistToolNames : []),
      ],
      200,
    );
    client.send(requestPayload);
    await donePromise;
    if (!String(messages.value[assistantIndex]?.content || "").trim()) {
      messages.value[assistantIndex].content = "模型未返回内容。";
    }
    if (assistAction?.id === "employee_create") {
      await autoCreateEmployeeFromDraftMessage(messages.value[assistantIndex], {
        resetAssist: true,
      });
    }
  } catch (err) {
    messages.value[assistantIndex].content =
      `请求失败：${err?.message || "未知错误"}`;
    ElMessage.error(err?.message || "对话失败");
  } finally {
    pendingRequests.delete(requestId);
    chatLoading.value = false;
    singleRoundAnswerOnly.value = false;
    if (selectedProjectId.value) {
      await fetchChatSessions(selectedProjectId.value, activeChatSessionId);
    }
    scrollToBottom();
  }
}

watch(
  () =>
    String(projectChatSettings.value.external_agent_type || "codex_cli").trim(),
  () => {
    const nextType = String(
      projectChatSettings.value.external_agent_type || "codex_cli",
    ).trim();
    const option =
      (externalAgentOptions.value || []).find(
        (item) => item.agent_type === nextType,
      ) || {};
    externalAgentWarmupKey.value = "";
    externalAgentWarmupLoading.value = false;
    externalAgentInfo.value = normalizeExternalAgentInfo({
      ...externalAgentInfo.value,
      ...option,
      agent_type: nextType,
      label: String(option.label || nextType).trim(),
      ready: false,
      session_id: "",
      thread_id: "",
    });
    resetTerminalPanel();
  },
);

watch(selectedProviderId, () => {
  handleProviderChange();
});

watch(
  () => terminalApprovalPrompt.value?.key || "",
  (nextKey) => {
    const normalizedKey = String(nextKey || "").trim();
    if (!normalizedKey) {
      terminalApprovalDialogVisible.value = false;
      return;
    }
    if (
      normalizedKey === String(terminalApprovalHandledKey.value || "").trim()
    ) {
      return;
    }
    terminalApprovalDialogVisible.value = true;
  },
);

watch(
  () => [
    route.path,
    settingsCenterItems.value.map((item) => item.id).join("|"),
  ],
  () => {
    syncSettingsRouteState();
  },
  { immediate: true },
);

watch(
  () => isSettingsCenterRoute.value,
  async (visible) => {
    if (!visible) {
      settingsTourVisible.value = false;
      return;
    }
    await nextTick();
    void startSettingsTour(false);
  },
  { immediate: true },
);

watch(
  () => String(selectedProjectId.value || "").trim(),
  () => {
    syncSkillResourceDirectoryDraft();
  },
  { immediate: true },
);

watch(autoSaveFingerprint, (nextFingerprint, prevFingerprint) => {
  if (!nextFingerprint || nextFingerprint === prevFingerprint) return;
  scheduleAutoSave();
});

function clearSelectedProjectState() {
  clearChatSessionMemory(selectedProjectId.value);
  selectedProjectId.value = "";
  localStorage.removeItem("project_id");
  currentChatSessionId.value = "";
  chatSessions.value = [];
}

function resolveAvailableProjectId(preferredId = "") {
  const normalizedPreferred = String(preferredId || "").trim();
  if (
    normalizedPreferred &&
    (projects.value || []).some((item) => item.id === normalizedPreferred)
  ) {
    return normalizedPreferred;
  }
  return String(projects.value[0]?.id || "").trim();
}

watch(selectedProjectId, async (value) => {
  const projectId = String(value || "").trim();
  if (projectId) {
    localStorage.setItem("project_id", projectId);
  } else {
    localStorage.removeItem("project_id");
  }
  if (!projectId) {
    rejectPendingRequests("已切换项目，当前请求取消");
    disconnectWs("switch project");
    singleRoundAnswerOnly.value = false;
    await fetchProvidersByProject("");
    return;
  }
  rejectPendingRequests("已切换项目，当前请求取消");
  disconnectWs("switch project");
  singleRoundAnswerOnly.value = false;
  resetTerminalPanel();
  try {
    agentStatusExpanded.value = false;
    await fetchProvidersByProject(projectId);
    const { chatSessionId: routeChatSessionId } = routeChatTarget();
    let chatSessionId = await fetchChatSessions(projectId, routeChatSessionId);
    if (!chatSessionId) {
      const created = await createChatSession({ switchTo: true });
      chatSessionId = String(created?.id || "").trim();
    }
    await fetchChatHistory(projectId, chatSessionId);
    await applyRouteMessageFocus();
  } catch (err) {
    if (
      err?.status === 403 ||
      err?.status === 404 ||
      String(err?.detail || "").includes("Project access denied")
    ) {
      await fetchProjects();
      const fallbackProjectId = resolveAvailableProjectId();
      if (fallbackProjectId && fallbackProjectId !== projectId) {
        selectedProjectId.value = fallbackProjectId;
        localStorage.setItem("project_id", fallbackProjectId);
      } else if (!fallbackProjectId) {
        clearSelectedProjectState();
      }
    }
    await fetchProvidersByProject("");
    messages.value = [];
    ElMessage.error(err?.detail || err?.message || "加载模型供应商失败");
  }
});

watch(
  () => [
    String(route.query.project_id || "").trim(),
    String(route.query.chat_session_id || "").trim(),
    String(route.query.message_id || "").trim(),
  ],
  async ([routeProjectId, routeChatSessionId, routeMessageId], previous) => {
    const previousKey = Array.isArray(previous) ? previous.join("|") : "";
    const currentKey = [
      routeProjectId,
      routeChatSessionId,
      routeMessageId,
    ].join("|");
    if (currentKey === previousKey) return;
    const activeProjectId = String(selectedProjectId.value || "").trim();
    if (routeProjectId && routeProjectId !== activeProjectId) {
      selectedProjectId.value = resolveAvailableProjectId(routeProjectId);
      return;
    }
    if (!activeProjectId) return;
    if (
      routeChatSessionId &&
      routeChatSessionId !== String(currentChatSessionId.value || "").trim()
    ) {
      await fetchChatHistory(activeProjectId, routeChatSessionId);
    }
    await applyRouteMessageFocus();
  },
);

onMounted(async () => {
  loading.value = true;
  window.addEventListener(PROJECT_CREATED_EVENT, handleProjectCreated);
  try {
    await Promise.all([
      fetchSystemConfig(),
      fetchProjects(),
      fetchModelTypeOptions(),
      fetchChatParameterOptions(),
      fetchGlobalProviders(),
    ]);
    syncProjectFromRoute();
    if (!String(selectedProjectId.value || "").trim()) {
      await fetchProvidersByProject("");
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "初始化失败");
  } finally {
    loading.value = false;
  }
  await nextTick();
  if (!isSettingsCenterRoute.value) {
    void startChatTour(false);
  }
  syncProjectSwitcherMenuWidth();
  window.addEventListener("resize", syncProjectSwitcherMenuWidth);
});

onUnmounted(() => {
  window.removeEventListener(PROJECT_CREATED_EVENT, handleProjectCreated);
  window.removeEventListener("resize", syncProjectSwitcherMenuWidth);
  if (connectorPollTimer !== null) {
    clearInterval(connectorPollTimer);
    connectorPollTimer = null;
  }
  clearHighlightedMessage();
  clearAutoSaveTimer();
  rejectPendingRequests("页面已关闭");
  disconnectWs("page closed");
});
</script>

<style scoped>
.chat-parameter-ribbon {
  display: grid;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background:
    linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.92),
      rgba(248, 250, 252, 0.9)
    ),
    rgba(255, 255, 255, 0.88);
}

.chat-parameter-ribbon__title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #526071;
}

.chat-parameter-ribbon__items {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 6px;
}

.chat-parameter-ribbon__item {
  display: grid;
  gap: 4px;
  padding: 7px 8px;
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.12);
}

.chat-parameter-ribbon__label {
  font-size: 11px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
}

.chat-parameter-ribbon__helper {
  min-height: 0;
  font-size: 10px;
  line-height: 1.35;
  color: #64748b;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.chat-parameter-ribbon__control {
  width: 100%;
}

.chat-parameter-ribbon__control :deep(.el-select__wrapper) {
  min-height: 30px;
  padding-top: 0;
  padding-bottom: 0;
  border-radius: 10px;
}

.chat-parameter-ribbon__control :deep(.el-segmented) {
  min-height: 30px;
}

.chat-parameter-ribbon__control :deep(.el-segmented__item) {
  min-height: 26px;
  font-size: 11px;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  padding: 18px max(20px, calc((100% - 1240px) / 2)) 12px;
  background: transparent;
  border-bottom: none;
  z-index: 10;
  position: relative;
}

.chat-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  min-width: 0;
}

.chat-title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.chat-title-subtext {
  font-size: 12px;
  line-height: 1.4;
  color: #6b7280;
  font-weight: 500;
}

.chat-status-pills {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-left: auto;
}

.chat-shell {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  gap: 18px;
  padding: 18px max(20px, calc((100% - 1240px) / 2)) 18px;
  align-items: stretch;
  overflow: hidden;
}

.chat-workbench {
  min-width: 0;
  min-height: 0;
  display: flex;
}

.chat-stage {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  border: 1px solid rgba(255, 255, 255, 0.92);
  border-radius: 32px;
  background: radial-gradient(
    circle at top,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.94) 56%,
    rgba(244, 247, 251, 0.96)
  );
  box-shadow:
    0 24px 64px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

.chat-conversation-sidebar {
  width: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 28px;
  padding: 16px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.96),
    rgba(248, 250, 252, 0.92)
  );
  backdrop-filter: blur(14px);
  box-shadow:
    0 16px 36px rgba(15, 23, 42, 0.05),
    0 2px 8px rgba(15, 23, 42, 0.03);
}

.chat-project-panel {
  margin-bottom: 16px;
  padding: 14px;
  border: 1px solid rgba(191, 219, 254, 0.72);
  border-radius: 22px;
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.12),
      transparent 32%
    ),
    linear-gradient(
      180deg,
      rgba(248, 250, 252, 0.98),
      rgba(255, 255, 255, 0.94)
    );
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.chat-project-panel__eyebrow {
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.chat-project-panel__title {
  margin-top: 10px;
  font-size: 16px;
  line-height: 1.35;
  font-weight: 700;
  color: #0f172a;
}

.chat-project-panel__desc {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

.chat-project-panel__select {
  margin-top: 12px;
}

.chat-project-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.chat-project-option__name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-project-option__id {
  flex-shrink: 0;
  font-size: 12px;
  color: #94a3b8;
}

.chat-conversation-sidebar__head {
  margin-bottom: 14px;
}

.chat-conversation-sidebar__title {
  margin-top: 6px;
  font-size: 20px;
  line-height: 1.2;
  font-weight: 700;
  color: #0f172a;
}

.chat-conversation-sidebar__desc {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

.chat-conversation-sidebar__actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.chat-quick-bar__eyebrow {
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #94a3b8;
}

.chat-quick-bar__title {
  margin-top: 6px;
  font-size: 20px;
  line-height: 1.2;
  font-weight: 700;
  color: #0f172a;
}

.chat-quick-bar__desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
}

.chat-new-conversation-button {
  justify-content: center;
  height: 38px !important;
  border-radius: 999px !important;
  border-color: rgba(15, 23, 42, 0.08) !important;
  background: linear-gradient(180deg, #111827, #1f2937) !important;
  color: #f8fafc !important;
  font-weight: 600;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.16) !important;
}

.chat-stage-toolbar {
  flex-shrink: 0;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.84);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.84),
    rgba(248, 250, 252, 0.72)
  );
}

.chat-top-summary {
  margin-bottom: 12px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.chat-top-summary .chat-side-summary__row {
  min-width: 0;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.78);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.92);
}

.chat-side-summary__row {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.chat-side-summary__label {
  font-size: 11px;
  line-height: 1;
  color: #94a3b8;
  letter-spacing: 0.04em;
}

.chat-side-summary__value {
  font-size: 13px;
  line-height: 1.45;
  font-weight: 600;
  color: #0f172a;
  word-break: break-word;
}

.chat-quick-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  align-items: stretch;
}

.chat-quick-field,
.chat-quick-mode-note {
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.7);
  padding: 12px 14px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.92);
}

.chat-quick-label {
  margin-bottom: 8px;
  font-size: 12px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #64748b;
}

.chat-quick-mode-text {
  min-height: 40px;
  display: flex;
  align-items: center;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
}

.chat-quick-mode-group {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.chat-quick-mode-group :deep(.el-radio-button__inner) {
  width: 100%;
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
}

.chat-session-strip {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.chat-session-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
}

.chat-session-chip {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  cursor: pointer;
  color: #0f172a;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background-color 0.18s ease;
}

.chat-session-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(148, 163, 184, 0.92);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
}

.chat-session-chip.is-active {
  border-color: rgba(37, 99, 235, 0.26);
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.12),
      transparent 38%
    ),
    #ffffff;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.08);
}

.chat-session-chip__title {
  display: block;
  flex: 1;
  min-width: 0;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.3;
}

.chat-session-chip__meta {
  font-size: 12px;
  line-height: 1.4;
  color: #64748b;
}

.chat-session-empty {
  display: flex;
  align-items: center;
  min-height: 56px;
  padding: 0 4px;
  font-size: 13px;
  color: #94a3b8;
}

.terminal-panel {
  width: 100%;
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

.terminal-panel-hint {
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.12);
  color: #bfdbfe;
  font-size: 12px;
  line-height: 1.55;
}

.terminal-approval-card {
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(251, 191, 36, 0.3);
  background: rgba(120, 53, 15, 0.35);
}

.terminal-approval-card__title {
  font-size: 13px;
  font-weight: 700;
  color: #fde68a;
}

.terminal-approval-card__desc {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.55;
  color: #fef3c7;
}

.terminal-approval-card__message {
  margin: 10px 0 0;
  padding: 10px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.28);
  color: #f8fafc;
  white-space: pre-wrap;
  word-break: break-word;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 12px;
  line-height: 1.55;
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

.terminal-approval-dialog__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.chat-header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #0f172a;
}

.chat-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.chat-settings-button {
  width: 34px;
  height: 34px;
}

.chat-create-employee-button {
  width: auto !important;
  min-width: 104px;
  height: 34px !important;
  padding: 0 14px !important;
  border-radius: 999px !important;
  border-color: rgba(59, 130, 246, 0.16) !important;
  background: linear-gradient(180deg, #ffffff 0%, #f5f9ff 100%) !important;
  color: #2563eb !important;
  font-weight: 600;
  box-shadow: 0 6px 18px rgba(37, 99, 235, 0.08) !important;
}

.chat-create-employee-button:hover {
  border-color: rgba(37, 99, 235, 0.26) !important;
  background: linear-gradient(180deg, #ffffff 0%, #edf5ff 100%) !important;
}

.chat-status-pills :deep(.el-tag) {
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  border-color: rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.94);
  color: #4b5563;
}

.settings-dialog-body {
  max-height: 70vh;
  overflow-y: auto;
  padding: 8px 16px;
}

.settings-summary-card {
  display: grid;
  gap: 12px;
  width: 100%;
  margin: 0 0 18px;
  padding: 22px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 28px;
  background:
    radial-gradient(
      circle at top right,
      rgba(103, 232, 249, 0.12),
      transparent 36%
    ),
    radial-gradient(
      circle at top left,
      rgba(125, 211, 252, 0.12),
      transparent 28%
    ),
    rgba(255, 255, 255, 0.66);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.settings-summary-title {
  color: #0f172a;
  font-size: 13px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.settings-summary-text {
  max-width: 780px;
  margin-top: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #475569;
}

.settings-summary-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.settings-summary-pill {
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  background: rgba(255, 255, 255, 0.76);
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
  font-weight: 600;
}

.model-parameter-note {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  margin-bottom: 16px;
  border-radius: 18px;
  border: 1px solid rgba(203, 213, 225, 0.72);
  background: rgba(248, 250, 252, 0.9);
}

.model-parameter-note__title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.5;
}

.model-parameter-note__text {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.settings-form {
  flex: 1;
  width: 100%;
  max-width: none;
  padding-bottom: 6px;
}

.settings-form .el-form-item {
  margin-bottom: 16px;
  padding: 18px 18px 20px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.82),
    0 14px 30px rgba(15, 23, 42, 0.04);
}

.settings-form .el-form-item:first-child {
  padding-top: 18px;
}

.settings-mode-group {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.settings-mode-group :deep(.el-radio-button__inner) {
  width: 100%;
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
}

.settings-employee-option {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 0;
}

.settings-employee-option__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.settings-employee-option__name {
  font-weight: 600;
  color: #0f172a;
}

.settings-employee-option__meta {
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
}

.external-agent-download-card {
  margin-top: 10px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px dashed rgba(148, 163, 184, 0.32);
  background: rgba(248, 250, 252, 0.9);
}

.external-agent-download-card__text {
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

.external-agent-download-card__subtitle {
  margin-top: 10px;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.external-agent-download-card__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.settings-section-title {
  margin: 6px 0 14px;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.settings-subtle-card {
  margin-top: 8px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px dashed rgba(148, 163, 184, 0.32);
  background: rgba(248, 250, 252, 0.9);
}

.settings-subtle-title {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
}

.settings-subtle-text {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

.settings-form :deep(.el-form-item__label) {
  padding-bottom: 12px;
  font-weight: 600;
  font-size: 13px;
  color: #0f172a;
  display: flex;
  align-items: center;
}

.settings-form :deep(.el-input__wrapper),
.settings-form :deep(.el-select__wrapper),
.settings-form :deep(.el-input-number .el-input__wrapper),
.settings-form :deep(.el-cascader .el-input__wrapper),
.settings-form :deep(.el-mentions),
.settings-form :deep(.el-textarea__inner) {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.86);
}

.settings-form :deep(.el-input__wrapper),
.settings-form :deep(.el-select__wrapper),
.settings-form :deep(.el-input-number .el-input__wrapper),
.settings-form :deep(.el-cascader .el-input__wrapper),
.settings-form :deep(.el-mentions) {
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.06);
}

.settings-form :deep(.el-textarea__inner) {
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.06);
  min-height: 104px;
}

.settings-form :deep(.el-input__wrapper.is-focus),
.settings-form :deep(.el-select__wrapper.is-focused),
.settings-form :deep(.el-input-number .el-input__wrapper.is-focus),
.settings-form :deep(.el-cascader .el-input__wrapper.is-focus),
.settings-form :deep(.el-mentions.is-focus),
.settings-form :deep(.el-textarea__inner:focus) {
  box-shadow:
    inset 0 0 0 1px rgba(56, 189, 248, 0.24),
    0 0 0 4px rgba(103, 232, 249, 0.12);
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

.settings-summary-actions {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: 8px 10px;
}

.settings-summary-status {
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
}

.settings-summary-sync-button {
  min-height: 36px !important;
  padding: 0 14px !important;
  border-radius: 999px !important;
  border-color: rgba(15, 23, 42, 0.08) !important;
  background: rgba(255, 255, 255, 0.72) !important;
  color: #374151 !important;
  font-weight: 600;
  box-shadow: none !important;
  transition:
    transform 0.22s ease,
    box-shadow 0.22s ease,
    border-color 0.22s ease,
    background-position 0.32s ease,
    color 0.22s ease;
}

.settings-summary-sync-button:hover {
  border-color: rgba(56, 189, 248, 0.24) !important;
  background: rgba(255, 255, 255, 0.92) !important;
  color: #0f172a !important;
}

.settings-summary-sync-button--hero {
  border-color: transparent !important;
  background:
    linear-gradient(
      135deg,
      #020617 0%,
      #0f172a 34%,
      #1e293b 68%,
      #0f766e 100%
    ) !important;
  background-size: 180% 180% !important;
  background-position: 0% 50% !important;
  color: #fff !important;
  box-shadow: 0 18px 28px rgba(15, 23, 42, 0.14) !important;
}

.settings-summary-sync-button--hero:hover {
  border-color: transparent !important;
  background-position: 100% 50% !important;
  color: #fff !important;
  transform: translateY(-1px);
  box-shadow:
    0 24px 36px rgba(15, 23, 42, 0.18),
    0 0 0 1px rgba(125, 211, 252, 0.18) !important;
}

.settings-chat-layout,
.settings-center-context-bar,
.settings-center-inline-page {
  width: min(100%, var(--settings-center-max-width));
  margin: 0 auto;
}

.settings-chat-layout {
  display: grid;
  grid-template-columns: var(--settings-chat-sidebar-width) minmax(0, 1fr);
  gap: var(--settings-center-shell-gap);
}

.settings-chat-sidebar,
.settings-chat-main {
  min-width: 0;
}

.settings-chat-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.settings-chat-sidebar-card,
.settings-chat-main-card {
  border: 1px solid var(--settings-surface-border);
  box-shadow: var(--settings-surface-shadow);
  backdrop-filter: blur(20px);
}

.settings-chat-sidebar-card {
  padding: 22px 20px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.62);
}

.settings-chat-sidebar-card--hero {
  background:
    radial-gradient(
      circle at top right,
      rgba(103, 232, 249, 0.14),
      transparent 34%
    ),
    radial-gradient(
      circle at top left,
      rgba(125, 211, 252, 0.14),
      transparent 26%
    ),
    rgba(255, 255, 255, 0.58);
}

.settings-chat-sidebar-card--note {
  background:
    radial-gradient(
      circle at top right,
      rgba(148, 163, 184, 0.12),
      transparent 34%
    ),
    rgba(255, 255, 255, 0.64);
}

.settings-chat-sidebar-card__eyebrow,
.settings-chat-section-label {
  color: #7c8aa0;
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.settings-chat-sidebar-card__title {
  margin-top: 10px;
  color: #0f172a;
  font-size: clamp(26px, 3vw, 34px);
  line-height: 1.06;
  font-weight: 600;
  letter-spacing: -0.03em;
  font-family:
    "Avenir Next", "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.settings-chat-sidebar-card__text,
.settings-chat-sidebar-card__note {
  margin: 10px 0 0;
  color: #475569;
  font-size: 14px;
  line-height: 1.7;
}

.settings-chat-sidebar-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.settings-chat-sidebar-card__meta span {
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.72);
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
  font-weight: 600;
}

.settings-chat-sidebar-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  margin-top: 18px;
}

.settings-chat-sidebar-card__status {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.settings-chat-fact-list {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.settings-chat-fact {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.68);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.settings-chat-fact__label {
  color: #7c8aa0;
  font-size: 11px;
  line-height: 1.4;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.settings-chat-fact__value {
  color: #0f172a;
  font-size: 14px;
  line-height: 1.6;
  font-weight: 600;
  word-break: break-word;
}

.settings-chat-main-card {
  padding: 22px;
  border-radius: var(--settings-surface-radius);
  background: rgba(255, 255, 255, 0.6);
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
  height: 100%;
  overflow: hidden;
  background:
    radial-gradient(
      circle at top left,
      rgba(255, 255, 255, 0.98),
      transparent 28%
    ),
    linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  min-height: 220px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 34px max(28px, calc((100% - 820px) / 2)) 28px;
  scroll-behavior: smooth;
}

.chat-empty-state {
  width: 100%;
  max-width: 720px;
  margin: auto;
  padding: 48px 0 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.chat-empty-badge {
  padding: 6px 11px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(226, 232, 240, 0.92);
  color: #374151;
  font-size: 12px;
  font-weight: 600;
}

.chat-empty-title {
  margin-top: 20px;
  font-size: 38px;
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: #111827;
}

.chat-empty-text {
  margin-top: 14px;
  max-width: 600px;
  font-size: 14px;
  line-height: 1.75;
  color: #6b7280;
}

.chat-empty-actions {
  margin-top: 24px;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.chat-empty-action {
  padding: 12px 14px;
  border-radius: 999px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.96);
  color: #111827;
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background-color 0.18s ease;
}

.chat-empty-action:hover {
  transform: translateY(-1px);
  border-color: rgba(156, 163, 175, 0.92);
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(17, 24, 39, 0.06);
}

.chat-history-loader {
  display: flex;
  justify-content: center;
  margin-bottom: 6px;
}

.chat-history-loader__button {
  min-height: 32px;
  padding: 0 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.9);
  color: #4b5563;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
}

.message-list-inner {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.message-row {
  display: block;
}

.message-row.is-highlighted .message-bubble {
  border-color: rgba(37, 99, 235, 0.38) !important;
  box-shadow:
    0 0 0 3px rgba(59, 130, 246, 0.14),
    0 18px 36px rgba(37, 99, 235, 0.08);
}

.message-row-process {
  align-items: stretch;
}

.message-row.is-user {
  flex-direction: initial;
}

.message-avatar {
  display: none;
}

.message-avatar :deep(.el-avatar) {
  width: 32px !important;
  height: 32px !important;
  font-size: 12px;
}

.avatar-user {
  background: #e5e7eb;
  color: #374151;
  font-weight: 700;
  box-shadow: none;
}

.avatar-ai {
  background: linear-gradient(135deg, #111827 0%, #374151 100%);
  color: #f9fafb;
  font-weight: 700;
  box-shadow: none;
}

.message-content-wrapper {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message-content-wrapper-process {
  max-width: 100%;
  width: 100%;
}

.message-row.is-ai .message-content-wrapper {
  max-width: 100%;
}

.message-row.is-ai .message-bubble > .message-text,
.message-row.is-ai .message-bubble > .message-process,
.message-row.is-ai .message-bubble > .message-audit,
.message-row.is-ai .message-bubble > .message-employee-draft,
.message-row.is-ai .message-bubble > .message-images,
.message-row.is-ai .message-bubble > .message-videos,
.message-row.is-ai .message-bubble > .message-attachments {
  max-width: 680px;
}

.message-row.is-user .message-content-wrapper {
  align-items: stretch;
  max-width: 100%;
}

.message-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: #6b7280;
}

.role-name {
  font-weight: 600;
  color: #111827;
}

.message-time {
  opacity: 1;
  color: #9ca3af;
}

.message-bubble {
  padding: 20px 22px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.98);
  color: #111827;
  line-height: 1.7;
  font-size: 15px;
  border: 1px solid rgba(226, 232, 240, 0.95);
  box-shadow:
    0 12px 28px rgba(15, 23, 42, 0.04),
    0 2px 6px rgba(15, 23, 42, 0.02);
  min-width: 0;
  overflow-wrap: anywhere;
}

.message-row.message-row-process .message-bubble.message-bubble-process {
  padding: 0;
  background: transparent;
  border: 0;
  box-shadow: none;
  border-radius: 0;
}

.message-text {
  word-break: break-word;
}

.message-inline-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: min(100%, 680px);
}

.message-inline-editor__input {
  width: 100%;
}

.message-inline-editor :deep(.el-textarea__wrapper) {
  padding: 0;
  border-radius: 20px;
  background: transparent;
  box-shadow: none;
}

.message-inline-editor :deep(.el-textarea__inner) {
  min-height: 132px !important;
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.26);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.94),
    rgba(250, 250, 252, 0.9)
  );
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.7),
    0 1px 2px rgba(15, 23, 42, 0.02);
  padding: 15px 16px;
  color: #1f2937;
  line-height: 1.8;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.message-inline-editor :deep(.el-textarea__inner::placeholder) {
  color: #9ca3af;
}

.message-inline-editor :deep(.el-textarea__inner:focus) {
  border-color: rgba(59, 130, 246, 0.28);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(252, 252, 253, 0.94)
  );
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.82),
    0 0 0 4px rgba(255, 255, 255, 0.42);
}

.message-inline-editor__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.message-inline-editor__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: auto;
}

.message-inline-editor__hint {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: #6b7280;
}

.message-inline-editor__hint-label {
  color: #9ca3af;
}

.message-inline-editor__shortcut {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.5);
  color: #6b7280;
}

.message-inline-editor__shortcut kbd {
  min-width: 24px;
  height: 22px;
  padding: 0 7px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: rgba(255, 255, 255, 0.96);
  color: #374151;
  font-size: 11px;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  line-height: 20px;
  text-align: center;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.message-inline-editor__button {
  min-height: 34px !important;
  padding: 0 14px !important;
  border-radius: 999px !important;
  box-shadow: none !important;
  font-weight: 500;
}

.message-inline-editor__button--ghost {
  color: #6b7280 !important;
}

.message-inline-editor__button--ghost:hover {
  color: #111827 !important;
  background: rgba(15, 23, 42, 0.04) !important;
}

.message-inline-editor__button--soft {
  border-color: rgba(148, 163, 184, 0.22) !important;
  background: rgba(255, 255, 255, 0.68) !important;
  color: #374151 !important;
}

.message-inline-editor__button--soft:hover {
  border-color: rgba(59, 130, 246, 0.18) !important;
  background: rgba(255, 255, 255, 0.9) !important;
  color: #1f2937 !important;
}

.message-inline-editor__button--primary {
  border-color: transparent !important;
  background: #111827 !important;
  color: #f9fafb !important;
}

.message-inline-editor__button--primary:hover {
  background: #1f2937 !important;
  color: #ffffff !important;
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

.message-process {
  margin-bottom: 14px;
  border: 1px solid rgba(229, 231, 235, 0.95);
  border-radius: 16px;
  background: #f8fafc;
  overflow: hidden;
}

.message-process-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 14px;
  border: 0;
  background: transparent;
  color: #111827;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.message-process-count {
  margin-left: 6px;
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
}

.message-process-meta {
  color: #4b5563;
  font-size: 12px;
  font-weight: 500;
}

.message-process-pre {
  padding: 0 14px 14px;
  color: #374151;
  font-size: 12px;
  line-height: 1.6;
  max-height: 280px;
  overflow: auto;
}

.message-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  opacity: 1;
  padding-left: 4px;
}

.message-action-button {
  color: #9ca3af;
  border-radius: 999px;
  width: 30px;
  height: 30px;
  padding: 0;
}

.message-action-button:hover {
  color: #111827;
  background: rgba(17, 24, 39, 0.05);
}

.message-audit {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  background: #f9fafb;
  border: 1px solid rgba(229, 231, 235, 0.95);
}

.message-tool-summary {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  background: #fffdf5;
  border: 1px solid rgba(245, 223, 77, 0.35);
}

.message-tool-summary__title {
  font-size: 12px;
  font-weight: 600;
  color: #111827;
}

.message-tool-summary__count {
  margin-left: 6px;
  color: #6b7280;
  font-weight: 500;
}

.message-tool-summary__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.message-audit-title {
  font-size: 12px;
  font-weight: 600;
  color: #111827;
}

.message-audit-section {
  margin-top: 8px;
}

.message-audit-label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 6px;
}

.message-audit-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.message-audit-text {
  font-size: 12px;
  color: #374151;
}

.message-audit-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  color: #374151;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
}

.message-employee-draft {
  margin-top: 12px;
  padding: 14px 14px 12px;
  border-radius: 18px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.1),
      transparent 38%
    ),
    linear-gradient(180deg, rgba(248, 250, 252, 0.98), #ffffff);
}

.message-employee-draft__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.message-employee-draft__eyebrow {
  color: #2563eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.message-employee-draft__title {
  margin-top: 4px;
  color: #111827;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.35;
}

.message-employee-draft__pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.employee-draft-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.86);
  color: #334155;
  font-size: 12px;
  font-weight: 500;
}

.message-employee-draft__desc {
  margin-top: 10px;
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.message-employee-draft__meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.message-employee-draft__meta-item {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(226, 232, 240, 0.9);
}

.meta-label {
  display: block;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
}

.meta-value {
  color: #1f2937;
  font-size: 13px;
  line-height: 1.6;
}

.message-employee-draft__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.message-employee-draft__workflow {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(226, 232, 240, 0.9);
}

.employee-draft-workflow-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #334155;
  font-size: 13px;
  line-height: 1.7;
}

.message-employee-draft__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}

.message-employee-draft__success {
  color: #15803d;
  font-size: 12px;
  line-height: 1.6;
}

.employee-draft-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.employee-draft-dialog__summary {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(37, 99, 235, 0.12);
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.08),
      transparent 42%
    ),
    linear-gradient(180deg, rgba(248, 250, 252, 0.96), #ffffff);
}

.employee-draft-dialog__title {
  color: #0f172a;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.4;
}

.employee-draft-dialog__desc {
  margin-top: 8px;
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.employee-draft-dialog__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 12px;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.employee-draft-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.employee-draft-dialog__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.employee-draft-dialog__section-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

.employee-draft-dialog__section-hint {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.employee-draft-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.employee-draft-dialog__panel {
  min-height: 112px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #f8fafc;
}

.employee-draft-dialog__panel-title {
  margin-bottom: 10px;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.employee-draft-dialog__subsection {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed rgba(203, 213, 225, 0.92);
}

.employee-draft-dialog__subsection-title {
  margin-bottom: 10px;
  color: #92400e;
  font-size: 12px;
  font-weight: 600;
}

.employee-draft-dialog__tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.employee-draft-dialog__empty {
  color: #64748b;
  font-size: 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.employee-draft-dialog__switches {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  width: 100%;
  min-width: 0;
}

.skill-resource-dialog__body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.skill-resource-dialog__hint {
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(59, 130, 246, 0.14);
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.08),
      transparent 42%
    ),
    linear-gradient(180deg, rgba(248, 250, 252, 0.96), #ffffff);
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.skill-resource-dialog__section-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

.skill-resource-dialog__directory {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #f8fafc;
}

.skill-resource-dialog__directory-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.skill-resource-dialog__directory-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.skill-resource-dialog__directory-value {
  min-height: 52px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.96);
  color: #111827;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
}

.skill-resource-dialog__directory-value.is-empty {
  color: #94a3b8;
  font-family: inherit;
}

.skill-resource-dialog__directory-meta {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.skill-resource-search {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-resource-search__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.skill-resource-search__expanded {
  color: #475569;
  font-size: 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.skill-resource-search__expanded--empty {
  margin-top: -4px;
  margin-bottom: 8px;
}

.skill-resource-site-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
  max-height: min(52vh, 520px);
  overflow-y: auto;
  padding-right: 4px;
}

.skill-resource-site-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.94)
  );
}

.skill-resource-site-list--search {
  max-height: min(46vh, 420px);
}

.skill-resource-site-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.skill-resource-site-card__title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.skill-resource-site-card__title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.skill-resource-site-card__badge {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.12);
  color: #2563eb;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.6;
}

.skill-resource-site-card__desc {
  color: #475569;
  font-size: 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.skill-resource-site-card__desc--localized {
  color: #0f172a;
  font-weight: 500;
}

.skill-resource-site-card__url {
  color: #64748b;
  font-size: 11px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.skill-resource-site-card__actions {
  margin-top: auto;
  padding-top: 2px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.employee-draft-external-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.employee-draft-external-preview__hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.employee-draft-external-preview__frame {
  width: 100%;
  min-height: 72vh;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 18px;
  background: #ffffff;
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
  background: rgba(15, 23, 42, 0.08);
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

.message-text :deep(.chat-code-block) {
  margin: 12px 0;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: #0f172a;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.16);
}

.message-text :deep(.chat-code-block__toolbar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  background: rgba(15, 23, 42, 0.96);
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.message-text :deep(.chat-code-block__lang) {
  font-size: 12px;
  line-height: 1;
  color: rgba(226, 232, 240, 0.72);
  text-transform: lowercase;
  font-family:
    ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
}

.message-text :deep(.chat-code-block__actions) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.message-text :deep(.chat-code-block__copy),
.message-text :deep(.chat-code-block__preview) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: rgba(15, 23, 42, 0.2);
  color: #e2e8f0;
  border-radius: 999px;
  padding: 0;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease;
}

.message-text :deep(.chat-code-block__icon) {
  display: inline-flex;
  width: 15px;
  height: 15px;
}

.message-text :deep(.chat-code-block__icon svg) {
  width: 100%;
  height: 100%;
}

.message-text :deep(.chat-code-block__copy:hover),
.message-text :deep(.chat-code-block__preview:hover) {
  background: rgba(148, 163, 184, 0.16);
  border-color: rgba(148, 163, 184, 0.42);
}

.message-text :deep(.chat-code-block__copy[data-copied="true"]) {
  color: #bbf7d0;
  border-color: rgba(34, 197, 94, 0.34);
  background: rgba(34, 197, 94, 0.14);
}

.message-text :deep(.chat-code-block pre) {
  margin: 0;
  padding: 14px 16px 16px;
  border-radius: 0;
  border: 0;
  box-shadow: none;
  background: #0b1120;
}

.code-preview-shell {
  min-height: 72vh;
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92), #ffffff);
}

.code-preview-frame {
  width: 100%;
  min-height: 72vh;
  border: 0;
  background: #ffffff;
}

.code-preview-error {
  padding: 18px 20px;
  color: #9f1239;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.message-row.is-user .message-bubble {
  background: linear-gradient(
    180deg,
    rgba(245, 247, 250, 0.96),
    rgba(255, 255, 255, 0.98)
  );
  color: #111827;
  border-color: rgba(226, 232, 240, 0.95);
}

.message-row.is-user .message-text :deep(code) {
  background: rgba(17, 24, 39, 0.08);
  color: inherit;
}

.message-row.is-ai .message-bubble {
  background: rgba(255, 255, 255, 0.98);
}

.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.message-videos {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
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

.preview-video {
  width: min(100%, 320px);
  max-height: 240px;
  border-radius: 12px;
  border: 1px solid var(--el-border-color-lighter);
  background: #020617;
}

.chat-composer {
  flex-shrink: 0;
  padding: 10px max(24px, calc((100% - 820px) / 2)) 24px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0),
    rgba(248, 250, 252, 0.92) 18%,
    rgba(255, 255, 255, 0.98) 100%
  );
  display: flex;
  justify-content: center;
  border-top: 1px solid rgba(226, 232, 240, 0.92);
  position: sticky;
  bottom: 0;
  z-index: 1;
}

@media (max-height: 820px) {
  .chat-shell {
    padding-top: 12px;
    padding-bottom: 12px;
  }

  .chat-messages {
    min-height: 160px;
    padding-top: 22px;
    padding-bottom: 18px;
  }

  .chat-composer {
    padding-top: 8px;
    padding-bottom: 14px;
  }
}

.chat-input-wrapper {
  width: 100%;
  max-width: 840px;
  border: 1px solid rgba(203, 213, 225, 0.95);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.98);
  transition:
    border-color 0.2s,
    box-shadow 0.2s,
    background-color 0.2s;
  box-shadow:
    0 18px 36px rgba(15, 23, 42, 0.06),
    0 3px 8px rgba(15, 23, 42, 0.03);
  display: flex;
  flex-direction: column;
}

.chat-input-wrapper.is-focused {
  border-color: rgba(17, 24, 39, 0.18);
  box-shadow: 0 16px 40px rgba(17, 24, 39, 0.1);
}

.chat-input-wrapper.is-dragover {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
  border-style: dashed;
}

.upload-preview-area {
  display: flex;
  gap: 12px;
  padding: 12px 16px 0;
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
  padding: 18px 18px 10px;
  font-size: 15px;
  line-height: 1.7;
  resize: none;
  color: #111827;
}

.chat-textarea :deep(.el-textarea__inner)::placeholder {
  color: #9ca3af;
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 14px 14px;
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 2px;
  min-width: 0;
}

.footer-left :deep(.el-button) {
  width: 34px;
  height: 34px;
  color: #6b7280;
}

.chat-model-select {
  width: 236px;
  max-width: min(46vw, 320px);
  min-width: 0;
}

.chat-model-select :deep(.el-select__wrapper) {
  min-height: 34px;
  border-radius: 999px;
  box-shadow: none;
  background: rgba(248, 250, 252, 0.92);
}

:deep(.chat-model-select-dropdown .el-select-dropdown__item) {
  height: auto;
  min-height: 46px;
  line-height: 1.4;
  padding-top: 8px;
  padding-bottom: 8px;
}

:deep(.chat-model-select-dropdown .el-select-dropdown__item.is-hovering) {
  background: rgba(59, 130, 246, 0.08);
}

:deep(.chat-model-select-dropdown .el-select-group__wrap:not(:last-of-type)) {
  margin-bottom: 4px;
}

.chat-model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.chat-model-option__main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  gap: 2px;
}

.chat-model-option__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  color: #0f172a;
}

.chat-model-option__provider {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: #64748b;
}

.chat-model-option__type {
  flex-shrink: 0;
  white-space: nowrap;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(226, 232, 240, 0.88);
  color: #475569;
  font-size: 11px;
  line-height: 1.2;
  font-weight: 700;
}

.chat-model-pill {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(241, 245, 249, 0.92);
  color: #334155;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

.hint-text {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}

.send-message-button {
  width: 38px;
  height: 38px;
  border: 0;
  background: #111827;
  box-shadow: none;
}

.send-message-button:disabled {
  box-shadow: none;
  background: #d1d5db;
  color: #f9fafb;
}

.external-agent-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--el-text-color-regular);
}

.external-agent-status-card {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.92);
  overflow: hidden;
}

.external-agent-status-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.external-agent-status-head {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.external-agent-status-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.5;
  word-break: break-word;
}

.external-agent-status-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.external-agent-status-meta {
  flex-shrink: 0;
  font-size: 12px;
  color: #64748b;
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

.workspace-guide-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  margin: 14px max(20px, calc((100% - 920px) / 2)) 0;
}

.workspace-guide-banner--warning {
  border: 1px solid var(--el-color-warning-light-5);
  background: var(--el-color-warning-light-9);
}

.workspace-guide-banner--info {
  border: 1px solid var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.workspace-guide-content {
  min-width: 0;
}

.workspace-guide-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.workspace-guide-text {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.workspace-guide-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.workspace-path-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.workspace-path-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.workspace-path-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
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

.chat-layout {
  position: relative;
  background:
    radial-gradient(
      circle at top left,
      rgba(255, 255, 255, 0.98),
      transparent 24%
    ),
    linear-gradient(180deg, #f6f7fb 0%, #eef2f7 100%);
}

.chat-page-actions {
  position: absolute;
  top: 18px;
  right: max(20px, calc((100% - 1240px) / 2));
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.chat-page-settings-button {
  width: 44px;
  height: 44px;
  border: 1px solid rgba(148, 163, 184, 0.26) !important;
  background: rgba(255, 255, 255, 0.84) !important;
  color: #111827 !important;
  box-shadow: 0 14px 30px rgba(15, 23, 42, 0.08) !important;
  backdrop-filter: blur(16px);
}

.chat-page-settings-button:hover {
  border-color: rgba(59, 130, 246, 0.22) !important;
  background: rgba(255, 255, 255, 0.94) !important;
  color: #2563eb !important;
}

.chat-shell {
  gap: 16px;
  padding: 76px max(20px, calc((100% - 1240px) / 2)) 18px;
}

.chat-conversation-sidebar {
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 28px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.96),
    rgba(245, 247, 250, 0.92)
  );
  box-shadow:
    0 20px 40px rgba(15, 23, 42, 0.06),
    0 2px 10px rgba(15, 23, 42, 0.03);
  padding: 14px;
}

.chat-sidebar-top {
  margin-bottom: 10px;
}

.chat-project-switcher {
  position: relative;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 14px 48px 14px 14px;
  border: 1px solid rgba(191, 219, 254, 0.72);
  border-radius: 22px;
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.14),
      transparent 36%
    ),
    linear-gradient(
      180deg,
      rgba(248, 250, 252, 0.98),
      rgba(255, 255, 255, 0.94)
    );
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.chat-project-switcher::after {
  content: "";
  position: absolute;
  top: 50%;
  right: 18px;
  width: 9px;
  height: 9px;
  border-right: 2px solid #64748b;
  border-bottom: 2px solid #64748b;
  transform: translateY(-62%) rotate(45deg);
}

.chat-project-switcher:hover {
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.3);
  box-shadow: 0 12px 28px rgba(59, 130, 246, 0.1);
}

.chat-project-switcher.is-empty {
  border-color: rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.96);
}

.chat-project-switcher__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  line-height: 1.35;
  font-weight: 700;
  color: #0f172a;
}

.chat-project-switcher__meta {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
}

:deep(.chat-project-switcher-menu) {
  padding: 6px;
  border-radius: 18px;
  border: 1px solid rgba(226, 232, 240, 0.96);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.1);
}

:deep(.chat-project-switcher-menu .el-dropdown-menu__item) {
  padding: 0;
  border-radius: 14px;
}

:deep(
  .chat-project-switcher-menu .el-dropdown-menu__item:not(.is-disabled):hover
) {
  background: rgba(59, 130, 246, 0.08);
}

.chat-project-option {
  min-width: 250px;
  padding: 12px 14px;
}

.chat-conversation-sidebar__actions {
  margin-bottom: 10px;
  gap: 8px;
}

.chat-new-conversation-button {
  height: 42px !important;
  border-radius: 18px !important;
  border: 1px solid rgba(17, 24, 39, 0.06) !important;
  background: linear-gradient(180deg, #111827, #1f2937) !important;
  color: #f8fafc !important;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.16) !important;
}

.chat-clear-current-button {
  justify-content: flex-start !important;
  padding-left: 6px !important;
  color: #667085 !important;
}

.chat-session-strip {
  padding: 0 2px 2px;
}

.chat-session-groups {
  gap: 12px;
}

.chat-session-group {
  gap: 6px;
}

.chat-session-group__title {
  padding: 0 6px;
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.04em;
}

.chat-session-list {
  gap: 6px;
  padding-right: 0;
}

.chat-session-chip {
  border: 0;
  border-radius: 16px;
  background: transparent;
  box-shadow: none;
  padding: 11px 12px;
}

.chat-session-chip:hover {
  transform: none;
  border-color: transparent;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: none;
}

.chat-session-chip.is-active {
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.12),
      transparent 40%
    ),
    rgba(219, 234, 254, 0.88);
}

.chat-session-chip__row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.chat-session-chip__title {
  display: block;
  flex: 1;
  min-width: 0;
  width: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}

.chat-session-chip__delete {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  color: #98a2b3;
  opacity: 0;
  transition:
    opacity 0.18s ease,
    color 0.18s ease;
}

.chat-session-chip:hover .chat-session-chip__delete,
.chat-session-chip.is-active .chat-session-chip__delete {
  opacity: 1;
}

.chat-session-chip__delete:hover {
  color: #ef4444;
}

.chat-session-chip__meta {
  font-size: 11px;
  color: #8a94a6;
}

.chat-stage {
  border: 1px solid rgba(255, 255, 255, 0.96);
  border-radius: 34px;
  background: radial-gradient(
    circle at top,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.96) 58%,
    rgba(244, 247, 251, 0.98)
  );
  box-shadow:
    0 26px 64px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

.workspace-guide-banner {
  margin-top: 16px;
  margin-left: max(24px, calc((100% - 860px) / 2));
  margin-right: max(24px, calc((100% - 860px) / 2));
}

.chat-messages {
  padding: 28px max(28px, calc((100% - 860px) / 2)) 18px;
  background: transparent;
}

.message-list-inner {
  max-width: 860px;
  gap: 26px;
}

.chat-empty-state {
  max-width: 760px;
  min-height: calc(100vh - 368px);
  justify-content: center;
  padding: 4px 0 8px;
}

.chat-empty-badge {
  border-radius: 999px;
  border: 1px solid rgba(226, 232, 240, 0.96);
  background: rgba(255, 255, 255, 0.86);
  color: #6b7280;
  font-size: 12px;
  font-weight: 600;
}

.chat-empty-title {
  margin-top: 16px;
  font-size: 40px;
  font-weight: 700;
  line-height: 1.18;
  letter-spacing: -0.03em;
  color: #111827;
}

.chat-empty-text {
  margin-top: 12px;
  max-width: 560px;
  color: #6b7280;
  font-size: 14px;
  line-height: 1.8;
}

.message-row {
  width: 100%;
}

.message-row.is-user {
  justify-content: flex-end;
}

.message-row.is-user .message-content-wrapper {
  max-width: min(560px, 72%);
}

.message-row.is-user .message-meta {
  justify-content: flex-end;
  padding-right: 4px;
}

.message-row.is-user .role-name {
  display: none;
}

.message-row.is-user .message-bubble {
  padding: 14px 18px;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 22px;
  background: linear-gradient(
    180deg,
    rgba(245, 247, 250, 0.98),
    rgba(255, 255, 255, 0.96)
  );
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.message-row.is-ai {
  justify-content: flex-start;
}

.message-row.is-ai .message-content-wrapper {
  max-width: 100%;
}

.message-row.is-ai .message-meta {
  justify-content: flex-start;
  gap: 8px;
  padding-left: 2px;
}

.message-row.is-ai .message-bubble {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.message-row.is-ai .message-text {
  color: #2b3340;
  font-size: 15px;
  line-height: 1.9;
}

.message-actions {
  padding-left: 0;
}

.chat-composer {
  padding: 14px max(28px, calc((100% - 860px) / 2)) 22px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0),
    rgba(248, 250, 252, 0.92) 16%,
    rgba(255, 255, 255, 0.98) 100%
  );
  border-top: 0;
}

.chat-input-wrapper {
  max-width: 860px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow:
    0 20px 40px rgba(15, 23, 42, 0.06),
    0 4px 12px rgba(15, 23, 42, 0.03);
}

.chat-textarea :deep(.el-textarea__inner) {
  padding-top: 16px;
  padding-bottom: 8px;
}

.input-footer {
  padding-top: 4px;
}

.settings-center-page {
  --settings-center-max-width: 1440px;
  --settings-center-shell-gap: 24px;
  --settings-center-shell-padding-inline: 24px;
  --settings-center-sidebar-width: 332px;
  --settings-chat-sidebar-width: 360px;
  --settings-surface-radius: 30px;
  --settings-surface-shadow:
    0 24px 64px rgba(15, 23, 42, 0.08), 0 14px 34px rgba(15, 23, 42, 0.06);
  --settings-surface-border: rgba(255, 255, 255, 0.82);
  min-height: 100vh;
  height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(
      circle at 18% 0%,
      rgba(125, 211, 252, 0.16),
      transparent 26%
    ),
    radial-gradient(
      circle at 82% 14%,
      rgba(103, 232, 249, 0.12),
      transparent 22%
    ),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%);
}

.settings-center-shell {
  display: grid;
  grid-template-columns: var(--settings-center-sidebar-width) minmax(0, 1fr);
  gap: var(--settings-center-shell-gap);
  height: 100%;
  padding: 18px var(--settings-center-shell-padding-inline) 22px;
  background: transparent;
}

.settings-center-sidebar {
  min-width: 0;
  min-height: 0;
  display: flex;
}

.settings-center-sidebar-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  margin-bottom: 40px;
  padding: 18px 16px 16px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: var(--settings-surface-radius);
  background: rgba(255, 255, 255, 0.58);
  box-shadow: var(--settings-surface-shadow);
  backdrop-filter: blur(20px);
  overflow-y: auto;
}

.settings-center-brand-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 2px 4px 16px;
}

.settings-center-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.settings-center-brand__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 14px;
  background: linear-gradient(180deg, #0f172a, #1e293b);
  color: #fff;
  box-shadow: 0 16px 28px rgba(15, 23, 42, 0.16);
  font-size: 12px;
  font-weight: 700;
}

.settings-center-brand__name {
  color: #0f172a;
  font-size: 17px;
  line-height: 1.2;
  font-weight: 600;
  letter-spacing: -0.02em;
  font-family:
    "Avenir Next", "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.settings-center-brand__meta {
  margin-top: 4px;
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.3;
}

.settings-center-nav-group + .settings-center-nav-group {
  margin-top: 18px;
}

.settings-center-nav-group__title {
  padding: 0 8px 10px;
  color: #7c8aa0;
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.settings-center-sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.settings-center-nav-item {
  width: 100%;
  padding: 13px 14px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.34);
  text-align: left;
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.76);
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    color 0.18s ease;
}

.settings-center-nav-item:hover {
  transform: translateY(-1px);
  border-color: rgba(56, 189, 248, 0.16);
  background: rgba(255, 255, 255, 0.7);
  box-shadow: 0 18px 28px rgba(15, 23, 42, 0.06);
}

.settings-center-nav-item.is-active {
  border-color: rgba(255, 255, 255, 0.84);
  background:
    radial-gradient(
      circle at top right,
      rgba(103, 232, 249, 0.12),
      transparent 46%
    ),
    rgba(255, 255, 255, 0.84);
  box-shadow: 0 18px 28px rgba(15, 23, 42, 0.08);
}

.settings-center-nav-item__row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  width: 100%;
}

.settings-center-nav-item__label {
  display: block;
  flex: 1;
  min-width: 0;
  font-size: 14px;
  line-height: 1.35;
  font-weight: 600;
  color: #0f172a;
}

.settings-center-nav-item__desc {
  display: block;
  margin-top: 6px;
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.6;
}

.settings-center-account {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: auto;
  padding: 18px 8px 2px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
}

.settings-center-account__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 16px;
  background: linear-gradient(180deg, #0f172a, #1e293b);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 16px 28px rgba(15, 23, 42, 0.16);
}

.settings-center-account__meta {
  min-width: 0;
  flex: 1;
}

.settings-center-account__name {
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

.settings-center-account__role {
  margin-top: 4px;
  color: #7c8aa0;
  font-size: 12px;
}

.settings-center-account__logout {
  flex-shrink: 0;
  color: #7c8aa0 !important;
}

.settings-center-stage {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 4px 0 8px;
  border-radius: 34px;
  background: transparent;
  box-shadow: none;
}

.settings-center-context-bar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 2px 0;
  text-align: left;
}

.settings-center-close-button {
  flex-shrink: 0;
  min-height: 34px;
  padding: 0 12px !important;
  border-radius: 999px !important;
  color: #64748b !important;
  border: 1px solid rgba(255, 255, 255, 0.76) !important;
  background: rgba(255, 255, 255, 0.68) !important;
}

.settings-center-close-button:hover {
  background: rgba(255, 255, 255, 0.9) !important;
  color: #0f172a !important;
}

.settings-center-context-bar__title {
  color: #0f172a;
  font-size: 19px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.02em;
}

.settings-center-context-bar__desc {
  max-width: 720px;
  color: #475569;
  font-size: 14px;
  line-height: 1.6;
}

.settings-center-context-bar__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 8px;
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.settings-center-context-bar__meta span {
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.68);
}

.settings-center-context-bar__meta span:not(:last-child)::after {
  display: none;
}

.settings-center-stage__body {
  flex: 1;
  min-height: 0;
  padding-top: 14px;
  overflow: visible;
}

.settings-center-stage__body--chat {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  overflow-y: auto;
  padding: 18px 0 28px;
}

.settings-center-stage__body--inline {
  min-width: 0;
  overflow: auto;
  padding: 14px 0 28px;
}

.settings-center-inline-page {
  min-width: 0;
}

.settings-tabs {
  flex: 1;
  min-height: 0;
  width: 100%;
}

.settings-tabs :deep(.el-tabs__header) {
  margin: 0 0 20px;
  padding-bottom: 0;
  background: transparent;
}

.settings-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.settings-tabs :deep(.el-tabs__nav-wrap),
.settings-tabs :deep(.el-tabs__nav-scroll) {
  display: flex;
  align-items: center;
}

.settings-tabs :deep(.el-tabs__nav) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.84);
}

.settings-tabs :deep(.el-tabs__item) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 38px;
  line-height: 1.2;
  padding: 0 16px;
  border: 0;
  border-bottom: 0;
  border-radius: 999px;
  color: #64748b;
  font-size: 13px;
  font-weight: 600;
  text-align: center;
  background: transparent;
}

.settings-tabs
  :deep(.el-tabs--top > .el-tabs__header .el-tabs__item:nth-child(2)),
.settings-tabs
  :deep(.el-tabs--top > .el-tabs__header .el-tabs__item:last-child),
.settings-tabs
  :deep(.el-tabs--bottom > .el-tabs__header .el-tabs__item:nth-child(2)),
.settings-tabs
  :deep(.el-tabs--bottom > .el-tabs__header .el-tabs__item:last-child) {
  padding-left: 16px;
  padding-right: 16px;
}

.settings-tabs :deep(.el-tabs__item.is-active) {
  color: #fff;
  border-bottom-color: transparent;
  background: linear-gradient(180deg, #0f172a, #1e293b);
  box-shadow: 0 18px 28px rgba(15, 23, 42, 0.14);
}

.settings-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

.settings-tabs :deep(.el-tabs__content) {
  height: 100%;
  overflow: visible;
}

.settings-tabs :deep(.el-tab-pane) {
  width: min(100%, 940px);
}

.chat-model-select {
  width: 188px;
}

.chat-model-select :deep(.el-select__wrapper) {
  background: #f3f5f8;
}

.chat-stage {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100%;
  padding: 10px 0 0 20px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
  overflow: hidden;
}

.chat-context-bar {
  padding: 0 0 8px;
}

.chat-context-bar__surface {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 20px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 26px;
  background:
    radial-gradient(
      circle at top right,
      rgba(103, 232, 249, 0.12),
      transparent 34%
    ),
    radial-gradient(
      circle at top left,
      rgba(125, 211, 252, 0.12),
      transparent 26%
    ),
    rgba(255, 255, 255, 0.54);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.86);
}

.chat-context-bar__copy {
  min-width: 0;
  flex: 1;
}

.chat-context-bar__eyebrow {
  color: var(--page-text-soft, #7c8aa0);
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.chat-context-bar__title {
  margin-top: 10px;
  color: #0f172a;
  font-size: clamp(26px, 3vw, 36px);
  font-weight: 600;
  line-height: 1.04;
  letter-spacing: -0.03em;
  font-family:
    "Avenir Next", "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.chat-context-bar__summary {
  max-width: 520px;
  margin: 8px 0 0;
  color: #475569;
  font-size: 14px;
  line-height: 1.6;
}

.chat-context-bar__meta {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 6px 8px;
  margin-top: 10px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 12px;
  line-height: 1.5;
}

.chat-context-bar__meta span:not(:last-child)::after {
  content: "·";
  margin-left: 10px;
  color: #c0c4cc;
}

.chat-context-bar__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  width: auto;
  flex-shrink: 0;
  align-self: center;
}

.chat-context-bar__action-button {
  border-radius: 999px !important;
  border-color: rgba(15, 23, 42, 0.08) !important;
  background: rgba(255, 255, 255, 0.86) !important;
  color: #334155 !important;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05);
}

.chat-context-bar__action-button:hover {
  border-color: rgba(56, 189, 248, 0.24) !important;
  color: #0f172a !important;
  background: #ffffff !important;
}

.workspace-guide-banner {
  margin: 8px auto 12px;
  width: min(100%, 780px);
  border-radius: 14px;
}

.chat-messages-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-messages {
  flex: 1 1 auto;
  min-height: 0;
  padding: 14px 20px 22px;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-padding-bottom: 28px;
  scroll-behavior: smooth;
  background: transparent;
}

.message-list-inner {
  max-width: none;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  min-height: min-content;
}

.chat-empty-state {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 32px 0 18px;
  text-align: center;
  background: transparent;
  border: 0;
}

.chat-empty-state__hero {
  width: min(720px, 100%);
  max-width: 100%;
  padding: 40px 42px 36px;
  border: 1px solid rgba(255, 255, 255, 0.76);
  border-radius: 34px;
  background:
    radial-gradient(
      circle at top right,
      rgba(103, 232, 249, 0.12),
      transparent 34%
    ),
    rgba(255, 255, 255, 0.58);
  box-shadow:
    0 24px 64px rgba(15, 23, 42, 0.08),
    0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.chat-empty-badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.72);
  color: var(--page-text-soft, #7c8aa0);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.chat-empty-title {
  margin-top: 18px;
  color: #0f172a;
  font-size: clamp(34px, 5vw, 48px);
  font-weight: 600;
  line-height: 1.06;
  letter-spacing: -0.03em;
  font-family:
    "Avenir Next", "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.chat-empty-text {
  display: block;
  max-width: 560px;
  margin-top: 12px;
  color: #475569;
  font-size: 14px;
  line-height: 1.8;
}

.chat-empty-actions {
  display: grid;
  width: min(720px, 100%);
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.chat-empty-action {
  min-width: 0;
  padding: 16px 18px;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.82);
  color: #0f172a;
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.06);
  font-weight: 600;
  line-height: 1.5;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    background-color 0.2s ease;
}

.chat-empty-action:hover {
  transform: translateY(-2px);
  border-color: rgba(56, 189, 248, 0.22);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 22px 34px rgba(15, 23, 42, 0.08);
}

.message-row.is-user .message-meta,
.message-row.is-ai .message-meta {
  display: none;
}

.message-process {
  border-radius: 12px;
  background: #f3f4f6;
}

.message-audit,
.message-employee-draft {
  border-radius: 14px;
  box-shadow: none;
}

.chat-composer {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  padding: 0 20px 20px;
  position: static;
  bottom: auto;
  z-index: auto;
  background: transparent;
  border-top: 0;
}

.chat-composer-panel {
  width: 100%;
  max-width: none;
  min-width: 0;
  margin: 0;
  border-radius: 30px;
  background: transparent;
}

.chat-input-wrapper {
  width: 100%;
  max-width: none;
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: none;
  backdrop-filter: blur(20px);
}

.chat-input-wrapper.is-focused {
  border-color: rgba(56, 189, 248, 0.26);
  box-shadow: 0 0 0 1px rgba(103, 232, 249, 0.16);
}

.chat-textarea :deep(.el-textarea__inner) {
  min-height: 92px !important;
  padding: 20px 22px 10px;
  color: #0f172a;
  border: 0 !important;
  box-shadow: none !important;
  background: transparent !important;
}

.chat-textarea :deep(.el-textarea__inner)::placeholder {
  color: #a3a3a3;
}

.chat-input-wrapper :deep(.composer-assist) {
  padding: 0 14px 6px;
}

.chat-input-wrapper :deep(.composer-assist-strip) {
  gap: 8px;
}

.chat-input-wrapper :deep(.composer-assist-chip) {
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(255, 255, 255, 0.66);
  color: #475569;
  min-height: 32px;
}

.chat-input-wrapper :deep(.composer-assist-chip.is-active) {
  border-color: rgba(56, 189, 248, 0.2);
  background: rgba(240, 249, 255, 0.92);
  color: #0f172a;
}

.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 12px 12px;
}

.footer-left,
.footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.footer-left :deep(.el-button) {
  color: #71717a;
  width: 34px;
  height: 34px;
}

.chat-media-parameter-trigger {
  width: auto !important;
  min-width: 0;
  padding: 0 12px !important;
  border-radius: 999px !important;
  border: 1px solid rgba(15, 23, 42, 0.06) !important;
  background: rgba(255, 255, 255, 0.78) !important;
  color: #374151 !important;
  gap: 6px;
}

.chat-media-parameter-trigger:hover {
  border-color: rgba(56, 189, 248, 0.22) !important;
  background: rgba(240, 249, 255, 0.96) !important;
  color: #0f172a !important;
}

.chat-media-parameter-trigger__icon {
  font-size: 14px;
}

.chat-media-parameter-trigger__label {
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
}

.chat-media-parameter-panel {
  display: grid;
  gap: 16px;
}

.chat-media-parameter-panel__head {
  display: grid;
  gap: 4px;
}

.chat-media-parameter-panel__eyebrow {
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.chat-media-parameter-panel__title {
  color: #0f172a;
  font-size: 18px;
  line-height: 1.2;
  font-weight: 600;
}

.chat-media-parameter-panel__summary {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.chat-media-parameter-panel__sections {
  display: grid;
  gap: 14px;
}

.chat-media-parameter-section {
  display: grid;
  gap: 8px;
}

.chat-media-parameter-section--toggle {
  margin-top: 2px;
  padding-top: 2px;
}

.chat-media-parameter-section__label {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
}

.chat-media-parameter-section__helper {
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.5;
}

.chat-media-parameter-section__options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chat-media-parameter-section__options.is-aspect {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.chat-media-parameter-section__options.is-resolution {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.chat-media-parameter-option {
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.9);
  color: #475569;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.3;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.chat-media-parameter-option:hover {
  border-color: rgba(56, 189, 248, 0.22);
  background: rgba(255, 255, 255, 0.96);
  color: #0f172a;
  transform: translateY(-1px);
}

.chat-media-parameter-option.is-active {
  border-color: rgba(56, 189, 248, 0.24);
  background: rgba(240, 249, 255, 0.96);
  color: #0f172a;
  box-shadow: 0 10px 24px rgba(56, 189, 248, 0.12);
}

.chat-media-parameter-option.is-resolution {
  min-height: 44px;
  justify-content: center;
}

.chat-media-parameter-option__label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  text-align: center;
}

.chat-media-toggle-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.9);
  color: #0f172a;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.chat-media-toggle-card:hover {
  border-color: rgba(56, 189, 248, 0.22);
  background: rgba(255, 255, 255, 0.96);
  transform: translateY(-1px);
}

.chat-media-toggle-card.is-active {
  border-color: rgba(56, 189, 248, 0.24);
  background: rgba(240, 249, 255, 0.96);
  box-shadow: 0 10px 24px rgba(56, 189, 248, 0.12);
}

.chat-media-toggle-card__content {
  display: grid;
  gap: 4px;
}

.chat-media-toggle-card__title {
  font-size: 13px;
  line-height: 1.3;
  font-weight: 600;
}

.chat-media-toggle-card__description {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.chat-media-toggle-card__indicator {
  flex-shrink: 0;
  min-width: 64px;
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  text-align: center;
}

.chat-media-toggle-card__indicator.is-active {
  background: linear-gradient(180deg, #0f172a, #1e293b);
  color: #ffffff;
}

.chat-model-select {
  width: clamp(196px, 24vw, 248px);
  flex: 0 1 248px;
  min-width: 0;
}

.chat-model-select :deep(.el-select__wrapper),
.chat-model-pill {
  min-height: 32px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.66);
  box-shadow: none;
}

.chat-model-pill {
  display: inline-flex;
  align-items: center;
  padding: 0 12px;
  border-radius: 999px;
  color: #52525b;
  font-size: 12px;
}

.hint-text {
  display: none;
}

.send-message-button {
  width: 36px;
  height: 36px;
  background: linear-gradient(180deg, #0f172a, #1e293b) !important;
  border: 0 !important;
  box-shadow: 0 14px 24px rgba(15, 23, 42, 0.18) !important;
}

.send-message-button:disabled {
  background: #d4d4d8 !important;
}

.message-row {
  position: relative;
  display: flex;
  width: 100%;
}

.message-row.is-ai .message-content-wrapper {
  width: 100%;
  max-width: min(920px, 100%);
  align-items: flex-start;
}

.message-row.is-ai .message-bubble > .message-text,
.message-row.is-ai .message-bubble > .message-process,
.message-row.is-ai .message-bubble > .message-audit,
.message-row.is-ai .message-bubble > .message-employee-draft,
.message-row.is-ai .message-bubble > .message-images,
.message-row.is-ai .message-bubble > .message-videos,
.message-row.is-ai .message-bubble > .message-attachments {
  max-width: min(920px, 100%);
}

.message-row.is-user {
  justify-content: flex-end;
}

.message-row.is-user .message-content-wrapper {
  width: auto;
  max-width: min(880px, 84%);
  align-items: flex-end;
}

.message-row.is-user .message-bubble {
  padding: 14px 18px;
  border: 1px solid rgba(255, 255, 255, 0.88);
  border-radius: 24px;
  background:
    radial-gradient(
      circle at top left,
      rgba(125, 211, 252, 0.14),
      transparent 54%
    ),
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(248, 250, 252, 0.8));
  box-shadow: none;
  width: fit-content;
  min-width: 0;
  max-width: 100%;
  backdrop-filter: blur(16px);
}

.message-row.is-user .message-bubble.message-bubble--editing {
  width: min(100%, 680px);
  min-width: min(320px, 100%);
  padding: 14px;
  border-color: rgba(255, 255, 255, 0.9);
  background:
    radial-gradient(
      circle at top left,
      rgba(125, 211, 252, 0.12),
      transparent 56%
    ),
    rgba(255, 255, 255, 0.78);
}

.message-row.is-user .message-inline-editor {
  width: 100%;
}

.message-row.is-user .message-text {
  color: #0f172a;
  font-size: 15px;
  line-height: 1.8;
}

.message-row.is-ai .message-bubble {
  padding: 16px 18px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 26px;
  background:
    radial-gradient(
      circle at top right,
      rgba(103, 232, 249, 0.08),
      transparent 42%
    ),
    rgba(255, 255, 255, 0.56);
  box-shadow: none;
  display: flex;
  flex-direction: column;
  width: min(100%, 920px);
  max-width: 100%;
  backdrop-filter: blur(18px);
}

.message-row.is-ai .message-text {
  color: #24303d;
  font-size: 15px;
  line-height: 1.85;
}

.message-text :deep(p) {
  margin-bottom: 0.9em;
}

.message-text :deep(ul),
.message-text :deep(ol) {
  margin: 0.5em 0 0.9em;
  padding-left: 1.3em;
}

.message-process {
  margin-bottom: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: rgba(245, 246, 248, 0.86);
}

.message-process-toggle {
  padding: 10px 12px;
  color: #374151;
  font-size: 12px;
}

.message-process-pre {
  padding: 0 12px 12px;
  font-size: 12px;
  line-height: 1.6;
}

.message-audit {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid #eceef2;
  border-radius: 16px;
  background: rgba(250, 250, 250, 0.86);
}

.message-audit-title {
  color: #374151;
  font-size: 12px;
  font-weight: 600;
}

.message-audit-label,
.message-audit-text,
.message-audit-pre {
  color: #6b7280;
}

.message-employee-draft {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid #e7eaf0;
  border-radius: 18px;
  background: rgba(250, 251, 252, 0.88);
}

.message-employee-draft__title {
  font-size: 15px;
}

.message-employee-draft__desc,
.meta-value,
.employee-draft-workflow-list {
  color: #4b5563;
}

.message-employee-draft__meta-item,
.message-employee-draft__workflow {
  background: #ffffff;
  border-color: #eceef2;
}

.message-images {
  margin-top: 10px;
  gap: 10px;
}

.message-videos {
  margin-top: 10px;
  gap: 12px;
}

.preview-image {
  border-radius: 14px;
  border: 1px solid #eceef2;
}

.preview-video {
  border-radius: 16px;
  border: 1px solid #eceef2;
  background: #020617;
}

.message-attachments {
  gap: 8px;
  margin-top: 10px;
}

.attachment-item {
  padding: 8px 10px;
  border: 1px solid #eceef2;
  border-radius: 12px;
  background: #fafafa;
}

.message-actions {
  margin-top: 8px;
  padding-left: 0;
  gap: 6px;
}

.message-row.is-user .message-actions {
  justify-content: flex-end;
}

.message-action-button {
  width: 28px;
  height: 28px;
  color: #a1a1aa;
}

.message-action-button:hover {
  color: #52525b;
  background: rgba(15, 23, 42, 0.05);
}

.chat-layout {
  position: relative;
  min-height: 100%;
  overflow: hidden;
  color: var(--page-text, #0f172a);
  background: var(
    --page-bg,
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%)
  );
}

.chat-layout__ambient,
.chat-layout__mesh {
  position: absolute;
  pointer-events: none;
}

.chat-layout__ambient {
  width: 32rem;
  height: 32rem;
  border-radius: 50%;
  filter: blur(72px);
  opacity: 0.72;
  animation: glowPulse 18s ease-in-out infinite;
}

.chat-layout__ambient--left {
  top: -11rem;
  left: -14rem;
  background: rgba(125, 211, 252, 0.34);
}

.chat-layout__ambient--right {
  top: 2rem;
  right: -11rem;
  background: rgba(103, 232, 249, 0.22);
  animation-delay: -5s;
}

.chat-layout__mesh {
  inset: 0;
  opacity: 0.28;
  background:
    linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
  background-size: 88px 88px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.68), transparent 78%);
}

.chat-main {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  min-height: 100%;
  padding: 0 20px 20px;
  box-sizing: border-box;
  overflow-x: hidden;
  overflow-y: auto;
}

.chat-shell {
  display: grid;
  width: 100%;
  max-width: none;
  margin: 0 auto;
  grid-template-columns: 332px minmax(0, 1fr);
  gap: 24px;
  height: 100%;
  min-height: 0;
  padding: 18px 0 22px;
  box-sizing: border-box;
  align-items: stretch;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}

.chat-conversation-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}

.chat-sidebar-brand-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 2px 16px;
}

.chat-sidebar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.chat-sidebar-brand__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  background: #0f172a;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.chat-sidebar-brand__name {
  color: #0f172a;
  font-size: 16px;
  line-height: 1.2;
  font-weight: 600;
  font-family:
    "Avenir Next", "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.chat-sidebar-brand__meta {
  margin-top: 2px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 11px;
  line-height: 1.3;
}

.chat-page-settings-button {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(255, 255, 255, 0.72) !important;
  background: rgba(255, 255, 255, 0.66) !important;
  color: #475569 !important;
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.05) !important;
}

.chat-page-settings-button:hover {
  border-color: rgba(56, 189, 248, 0.28) !important;
  background: rgba(255, 255, 255, 0.86) !important;
  color: #0f172a !important;
}

.chat-sidebar-project-card {
  margin-top: 2px;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 24px;
  background:
    radial-gradient(
      circle at top right,
      rgba(103, 232, 249, 0.14),
      transparent 38%
    ),
    rgba(255, 255, 255, 0.68);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.84),
    0 14px 28px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(18px);
}

.chat-sidebar-project-card :deep(.chat-project-dropdown) {
  display: block;
  width: 100%;
}

.chat-sidebar-card__label {
  margin: 0 0 10px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.chat-project-switcher {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  position: relative;
  min-width: 0;
  height: 48px;
  padding: 0 40px 0 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.76);
  box-shadow: 0 14px 24px rgba(15, 23, 42, 0.04);
}

.chat-project-switcher::after {
  transform: translateY(-50%) rotate(45deg);
}

.chat-project-switcher:hover {
  border-color: rgba(56, 189, 248, 0.22);
  background: rgba(255, 255, 255, 0.9);
}

.chat-project-switcher__name {
  display: block;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

:deep(.chat-project-switcher-menu) {
  max-width: calc(100vw - 24px);
  padding: 6px;
  box-sizing: border-box;
}

:deep(.chat-project-switcher-menu .el-dropdown-menu__item) {
  max-width: 100%;
}

.chat-project-option {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  padding: 11px 14px;
  box-sizing: border-box;
}

.chat-project-option--empty {
  justify-content: center;
}

.chat-project-option--empty .chat-project-option__name {
  color: #9ca3af;
}

.chat-project-option__name {
  min-width: 0;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-conversation-sidebar__actions {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  margin-top: 14px;
  padding: 0;
}

.chat-new-conversation-button {
  width: 100%;
  height: 42px !important;
  border-radius: 999px !important;
  border: 0 !important;
  background: linear-gradient(180deg, #0f172a, #1e293b) !important;
  color: #fff !important;
  font-weight: 600;
  box-shadow: 0 18px 28px rgba(15, 23, 42, 0.14) !important;
}

.chat-clear-current-button {
  justify-content: flex-start;
  min-height: 32px !important;
  padding: 0 6px !important;
  color: var(--page-text-soft, #7c8aa0) !important;
}

.chat-session-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  margin-top: 14px;
  padding: 14px 12px 10px;
  flex: 1;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.66);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.82),
    0 18px 32px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(18px);
}

.chat-session-panel__head {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  padding: 0 6px 10px;
}

.chat-session-panel__title {
  color: #475569;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.chat-session-strip {
  flex: 1;
  min-height: 0;
}

.chat-session-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow: auto;
  padding-right: 4px;
}

.chat-session-group__title {
  padding: 0 6px 4px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.chat-session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-session-chip {
  padding: 12px 14px;
  border: 1px solid rgba(15, 23, 42, 0.04);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.68);
  text-align: left;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.chat-session-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(56, 189, 248, 0.18);
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
}

.chat-session-chip.is-active {
  border-color: rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.08);
}

.chat-session-chip__title {
  display: block;
  flex: 1;
  min-width: 0;
  width: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #111827;
  font-size: 13px;
  font-weight: 500;
}

.chat-session-chip__row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.chat-session-chip__delete {
  opacity: 0;
  color: #a1a1aa;
}

.chat-session-chip:hover .chat-session-chip__delete,
.chat-session-chip.is-active .chat-session-chip__delete {
  opacity: 1;
}

.chat-session-chip__meta {
  color: #9ca3af;
  font-size: 11px;
}

.chat-session-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 12px;
}

.chat-sidebar-footer {
  margin-top: 14px;
  padding: 0;
}

.chat-sidebar-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.66);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(18px);
}

.chat-sidebar-user__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: #e4e4e7;
  color: #52525b;
  font-size: 12px;
  font-weight: 700;
}

.chat-sidebar-user__name {
  color: #27272a;
  font-size: 13px;
  font-weight: 500;
}

.chat-sidebar-user__role {
  margin-top: 2px;
  color: #9ca3af;
  font-size: 11px;
}

.chat-sidebar-user__meta {
  min-width: 0;
  flex: 1;
}

.chat-sidebar-user__logout {
  flex-shrink: 0;
  color: #8b8d93 !important;
}

@keyframes glowPulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.64;
  }
  50% {
    transform: scale(1.08);
    opacity: 0.88;
  }
}

@media (max-width: 1120px) {
  .settings-center-page {
    --settings-center-max-width: 100%;
    --settings-chat-sidebar-width: minmax(0, 1fr);
  }

  .chat-shell {
    width: 100%;
    grid-template-columns: 1fr;
    min-height: auto;
    height: auto;
    gap: 20px;
    padding: 14px 0 0;
  }

  .chat-conversation-sidebar {
    order: 2;
    padding: 0;
    border: 0;
  }

  .chat-stage {
    order: 1;
    min-height: auto;
    padding: 0;
  }

  .chat-main {
    padding: 0 14px 18px;
  }

  .chat-messages {
    padding: 10px 14px 18px;
    scroll-padding-bottom: 22px;
  }

  .chat-context-bar__surface {
    flex-direction: column;
    align-items: flex-start;
    padding: 16px 16px;
  }

  .chat-context-bar__actions {
    width: 100%;
    justify-content: flex-start;
  }

  .chat-empty-title {
    font-size: 36px;
  }

  .chat-empty-state {
    min-height: 360px;
  }

  .chat-empty-actions {
    grid-template-columns: 1fr;
  }

  .workspace-guide-banner {
    width: calc(100% - 36px);
  }

  .settings-center-shell {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
    gap: 14px;
    padding: 14px;
  }

  .settings-center-sidebar {
    min-height: auto;
  }

  .settings-center-sidebar-card {
    padding: 16px;
    border-radius: 26px;
  }

  .settings-center-sidebar__nav {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
    gap: 8px;
  }

  .settings-center-stage {
    height: auto;
    min-height: 0;
    padding-top: 4px;
    border-radius: 28px;
  }

  .settings-center-context-bar__title {
    font-size: 18px;
  }

  .settings-chat-main-card {
    padding: 18px;
  }

  .message-employee-draft__meta {
    grid-template-columns: 1fr;
  }

  .employee-draft-dialog__grid {
    grid-template-columns: 1fr;
  }

  .input-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .skill-resource-dialog__directory-head {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (max-width: 640px) {
  .chat-main {
    padding: 0 10px 14px;
  }

  .chat-messages {
    padding: 8px 10px 16px;
    scroll-padding-bottom: 20px;
  }

  .chat-composer {
    padding: 0 14px 16px;
  }

  .chat-shell {
    width: 100%;
    gap: 16px;
    padding: 8px 0 0;
  }

  .chat-composer-panel {
    width: 100%;
    min-width: 0;
  }

  .chat-project-switcher {
    padding: 13px 40px 13px 13px;
    border-radius: 16px;
  }

  :deep(.chat-project-switcher-menu) {
    min-width: min(320px, calc(100vw - 24px));
  }

  .message-row {
    gap: 0;
  }

  .message-avatar {
    display: none;
  }

  .message-bubble {
    padding: 16px;
    border-radius: 20px;
  }

  .message-row.is-user .message-bubble.message-bubble--editing {
    width: 100%;
    min-width: 0;
  }

  .message-inline-editor__footer {
    align-items: flex-start;
  }

  .message-inline-editor__actions {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
  }

  .message-row.is-ai .message-content-wrapper,
  .message-row.is-user .message-content-wrapper {
    width: 100%;
    max-width: 100%;
  }

  .message-row.is-user .message-bubble {
    width: 100%;
    min-width: 0;
  }

  .message-actions {
    opacity: 1;
    flex-wrap: wrap;
  }

  .chat-conversation-sidebar__actions {
    justify-content: flex-start;
  }

  .message-employee-draft__head,
  .message-employee-draft__actions {
    flex-direction: column;
    align-items: flex-start;
  }

  .employee-draft-dialog__section-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .chat-context-bar__meta {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .chat-context-bar__meta span:not(:last-child)::after {
    display: none;
  }

  .chat-empty-title {
    font-size: 32px;
  }

  .chat-empty-state__hero {
    padding: 30px 22px 28px;
  }

  .chat-context-bar__surface {
    padding: 14px;
    border-radius: 22px;
  }

  .chat-context-bar__title {
    font-size: 30px;
  }

  .chat-empty-actions {
    width: 100%;
  }

  .input-footer {
    align-items: stretch;
    gap: 10px;
    flex-wrap: wrap;
  }

  .chat-model-select {
    width: 100%;
    max-width: none;
  }

  .footer-left {
    width: 100%;
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .footer-right {
    width: 100%;
    justify-content: flex-end;
  }

  .skill-resource-dialog__directory-actions {
    width: 100%;
  }

  .skill-resource-site-list {
    grid-template-columns: 1fr;
  }

  .settings-center-brand__name {
    font-size: 14px;
  }

  .settings-center-nav-item {
    padding: 12px;
    border-radius: 18px;
  }

  .settings-chat-sidebar-card,
  .settings-chat-main-card {
    padding: 16px;
    border-radius: 24px;
  }

  .settings-chat-sidebar-card__title {
    font-size: 28px;
  }

  .settings-chat-sidebar-card__actions,
  .settings-summary-pills {
    width: 100%;
  }

  .settings-chat-sidebar-card__actions > * {
    width: 100%;
  }

  .settings-summary-sync-button,
  .settings-summary-sync-button--hero {
    width: 100%;
  }

  .settings-center-context-bar__meta {
    gap: 6px;
  }

  .settings-summary-card {
    padding: 18px;
  }

  .settings-form .el-form-item {
    padding: 16px;
    border-radius: 20px;
  }

  .settings-tabs :deep(.el-tabs__header) {
    margin-bottom: 16px;
  }

  .settings-tabs :deep(.el-tabs__nav) {
    width: 100%;
    gap: 6px;
    flex-wrap: wrap;
    border-radius: 22px;
  }

  .settings-tabs :deep(.el-tabs__item) {
    flex: 1 1 auto;
    min-width: max-content;
  }

  .settings-chat-sidebar-card__actions {
    justify-content: flex-start;
  }
}
</style>
