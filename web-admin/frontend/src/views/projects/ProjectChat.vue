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
      <div
        class="chat-shell"
        :class="{ 'chat-shell--local-runner': isLocalRunnerSurface }"
      >
        <ProjectConversationSidebar
          ref="conversationSidebarRef"
          v-model:selected-project-id="selectedProjectId"
          :projects="projects"
          :surface-mark="chatSurfaceMark"
          :surface-name="chatSurfaceName"
          :surface-meta="chatSurfaceMeta"
          :creating-session="creatingChatSession"
          :chat-loading="chatLoading"
          :has-selected-project="hasSelectedProject"
          :current-session-id="currentChatSessionId"
          :sessions-loading="chatSessionsLoading"
          :session-groups="groupedChatSessions"
          :deleting-session-id="deletingChatSessionId"
          :username-initial="currentUsernameInitial"
          :username="currentUsername"
          @open-settings="openSettingsCenter"
          @project-change="handleProjectCommand"
          @create-conversation="handleCreateNewConversation"
          @open-group-chat="openGroupChatDialog"
          @clear-current="clearMessages"
          @select-session="selectChatSession"
          @edit-session="openGroupChatDialog"
          @delete-session="deleteChatSession"
          @logout="logoutFromChat"
        />

        <div class="chat-stage">
          <ChatContextBar
            ref="chatContextBarHostRef"
            :has-selected-project="hasSelectedProject"
            :project-label="currentProjectLabel"
            :surface-name="chatSurfaceName"
            :chat-mode-label="chatModeLabel"
            :session-source-label="currentChatSessionSourceLabel"
            :model-summary="currentModelSummary"
            :status-text="chatHeaderStatusText"
            :can-trust-workspace="canTrustAgentRuntimeWorkspace"
            :workspace-trust-saving="workspaceTrustSaving"
            @start-guide="startChatTour"
            @open-project-detail="openCurrentProjectDetail"
            @open-material-library="openCurrentMaterialLibrary"
            @trust-workspace="trustAgentRuntimeWorkspace"
            @open-mcp="openUnifiedMcpDialog"
            @open-skill-resource="openSkillResourceCenter"
          />
          <div class="chat-workbench">
            <div class="chat-messages-shell">
              <div
                class="chat-messages"
                ref="messagesContainer"
                @scroll="handleMessagesScroll"
                @click="handleMessageAreaClick"
              >
                <ChatMessageList
                  :history-loading="chatHistoryLoading"
                  :messages="messages"
                  :has-selected-project="hasSelectedProject"
                  :has-accessible-projects="hasAccessibleProjects"
                  :empty-state-title="emptyStateTitle"
                  :empty-state-text="emptyStateText"
                  :starter-prompts="starterPrompts"
                  :history-has-more="chatHistoryHasMore"
                  :history-loading-more="chatHistoryLoadingMore"
                  @apply-starter-prompt="applyStarterPrompt"
                  @load-older="loadOlderMessages"
                >
                  <div
                    v-for="(item, idx) in messages"
                    :key="item.id || `message-${idx}`"
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
                        <template v-else>
                          <div
                            v-if="isExternalAgentWaitingMessage(item)"
                            class="message-external-waiting"
                          >
                            <div class="message-external-waiting__visual">
                              <span></span>
                              <span></span>
                              <span></span>
                            </div>
                            <div class="message-external-waiting__body">
                              <strong>{{
                                externalAgentWaitingMessageTitle(item)
                              }}</strong>
                              <span>{{
                                externalAgentWaitingMessageDescription(item)
                              }}</span>
                              <div class="message-external-waiting__bar">
                                <i></i>
                              </div>
                            </div>
                          </div>
                          <template v-else-if="item.displayMode === 'terminal'">
                            <div
                              v-if="
                                terminalInteractionFormForMessage(item, idx)
                              "
                              class="message-terminal-form"
                              :class="{
                                'is-submitted':
                                  terminalStructuredSubmissionHintForMessage(
                                    idx,
                                  ),
                              }"
                            >
                              <div class="message-terminal-form__head">
                                <div>
                                  <strong>{{
                                    terminalStructuredInteraction.title
                                  }}</strong>
                                  <p>
                                    {{
                                      terminalStructuredInteraction.description
                                    }}
                                  </p>
                                </div>
                                <el-tag size="small" effect="plain"
                                  >表单交互</el-tag
                                >
                              </div>
                              <ElementEasyForm
                                :form-json="terminalInteractionFormJson"
                                class="message-terminal-form__easy-form"
                              />
                              <div class="message-terminal-form__actions">
                                <el-button
                                  v-if="
                                    !terminalStructuredSubmissionHintForMessage(
                                      idx,
                                    )
                                  "
                                  text
                                  @click="dismissTerminalStructuredInteraction"
                                >
                                  使用终端兜底
                                </el-button>
                                <el-button
                                  type="primary"
                                  :disabled="
                                    !canSubmitTerminalStructuredInteraction ||
                                    Boolean(
                                      terminalStructuredSubmissionHintForMessage(
                                        idx,
                                      ),
                                    )
                                  "
                                  @click="submitTerminalStructuredInteraction"
                                >
                                  {{
                                    terminalStructuredSubmissionHintForMessage(
                                      idx,
                                    )
                                      ? "已提交，继续执行中"
                                      : "确认并继续"
                                  }}
                                </el-button>
                              </div>
                            </div>
                            <div
                              v-if="
                                terminalStructuredSubmissionHintForMessage(idx)
                              "
                              class="message-terminal-form__submitted"
                            >
                              {{
                                terminalStructuredSubmissionHintForMessage(idx)
                              }}
                            </div>
                          </template>
                          <div
                            v-if="shouldShowMessageProcess(item, idx)"
                            class="message-process-shell"
                          >
                            <button
                              type="button"
                              class="message-process-shell__toggle"
                              @click="
                                item.processExpanded = !item.processExpanded
                              "
                            >
                              <span class="message-process-shell__title-wrap">
                                <span class="message-process-shell__eyebrow">
                                  {{ messageProcessEyebrow(item, idx) }}
                                </span>
                                <span class="message-process-shell__title">
                                  {{ messageProcessTitle(item, idx) }}
                                </span>
                              </span>
                              <span class="message-process-shell__meta">
                                <el-button
                                  v-if="
                                    operationPrimaryActionLabel(
                                      primaryMessageProcessOperation(item),
                                    )
                                  "
                                  size="small"
                                  type="primary"
                                  plain
                                  class="message-process-shell__primary-action"
                                  @click.stop="
                                    handleOperationPrimaryAction(
                                      primaryMessageProcessOperation(item),
                                    )
                                  "
                                >
                                  {{
                                    operationPrimaryActionLabel(
                                      primaryMessageProcessOperation(item),
                                    )
                                  }}
                                </el-button>
                                <span
                                  v-if="messageProcessStateLabel(item, idx)"
                                  class="message-process-shell__state"
                                  :class="`is-${messageProcessStateTone(item, idx)}`"
                                >
                                  {{ messageProcessStateLabel(item, idx) }}
                                </span>
                                <span
                                  v-if="messageProcessStepCount(item, idx)"
                                  class="message-process-shell__count"
                                >
                                  {{ messageProcessStepCount(item, idx) }} 项
                                </span>
                                <span>{{
                                  item.processExpanded ? "收起" : "展开"
                                }}</span>
                              </span>
                            </button>
                            <div
                              v-show="item.processExpanded"
                              class="message-process-shell__body"
                            >
                              <div
                                v-if="
                                  messageLiveProgressItems(item, idx).length
                                "
                                class="message-live-progress"
                              >
                                <div class="message-live-progress__head">
                                  <div>
                                    <div class="message-live-progress__eyebrow">
                                      本轮运行轨迹
                                    </div>
                                    <div class="message-live-progress__title">
                                      {{ messageProcessTitle(item, idx) }}
                                    </div>
                                  </div>
                                  <span
                                    class="message-live-progress__badge"
                                    :class="`is-${messageProcessStateTone(item, idx)}`"
                                  >
                                    {{ messageProcessStateLabel(item, idx) }}
                                  </span>
                                </div>
                                <div class="message-live-progress__list">
                                  <div
                                    v-for="progressItem in messageLiveProgressItems(
                                      item,
                                      idx,
                                    )"
                                    :key="progressItem.id"
                                    class="message-live-progress__item"
                                    :class="`is-${progressItem.phase}`"
                                  >
                                    <span class="message-live-progress__marker">
                                      <CircleCheck
                                        v-if="
                                          progressItem.phase === 'completed'
                                        "
                                        :size="13"
                                      />
                                      <span v-else></span>
                                    </span>
                                    <span class="message-live-progress__main">
                                      <span
                                        class="message-live-progress__item-title"
                                      >
                                        {{ progressItem.title }}
                                      </span>
                                      <span
                                        v-if="progressItem.summary"
                                        class="message-live-progress__item-summary"
                                      >
                                        {{ progressItem.summary }}
                                      </span>
                                    </span>
                                    <span class="message-live-progress__phase">
                                      {{ progressItem.phaseLabel }}
                                    </span>
                                  </div>
                                </div>
                              </div>
                              <div
                                v-if="messageProcessOperations(item).length"
                                class="message-operations"
                              >
                                <article
                                  v-for="operation in messageProcessOperations(
                                    item,
                                  )"
                                  :key="operation.id"
                                  class="message-operation-card"
                                  :class="`is-${operation.phase}`"
                                >
                                  <div class="message-operation-card__head">
                                    <div
                                      class="message-operation-card__title-wrap"
                                    >
                                      <span
                                        class="message-operation-card__title"
                                      >
                                        {{ operation.title }}
                                      </span>
                                      <span
                                        v-if="operation.summary"
                                        class="message-operation-card__summary"
                                      >
                                        {{ operation.summary }}
                                      </span>
                                    </div>
                                    <span class="message-operation-card__badge">
                                      {{ operationPhaseLabel(operation) }}
                                    </span>
                                  </div>
                                  <div
                                    v-if="operationRiskLabel(operation)"
                                    class="message-operation-card__risk"
                                    :class="`is-${operationRiskTone(operation)}`"
                                  >
                                    {{ operationRiskLabel(operation) }}
                                  </div>
                                  <div
                                    v-if="
                                      operationRuntimeMetaTags(operation).length
                                    "
                                    class="message-operation-card__meta-tags"
                                  >
                                    <span
                                      v-for="tag in operationRuntimeMetaTags(
                                        operation,
                                      )"
                                      :key="tag"
                                      class="message-operation-card__meta-tag"
                                    >
                                      {{ tag }}
                                    </span>
                                  </div>
                                  <ol
                                    v-if="operationPlanSteps(operation).length"
                                    class="message-operation-card__plan"
                                  >
                                    <li
                                      v-for="(
                                        step, stepIndex
                                      ) in operationPlanSteps(operation)"
                                      :key="String(step.step_id || stepIndex)"
                                      class="message-operation-card__plan-step"
                                      :class="`is-${planStepPhase(step)}`"
                                    >
                                      <span
                                        class="message-operation-card__plan-check"
                                      >
                                        <CircleCheck
                                          v-if="
                                            planStepPhase(step) === 'completed'
                                          "
                                          :size="13"
                                        />
                                        <span v-else>{{ stepIndex + 1 }}</span>
                                      </span>
                                      <span
                                        class="message-operation-card__plan-main"
                                      >
                                        <span
                                          class="message-operation-card__plan-title"
                                        >
                                          {{
                                            step.title ||
                                            `步骤 ${stepIndex + 1}`
                                          }}
                                        </span>
                                        <span
                                          v-if="step.summary"
                                          class="message-operation-card__plan-summary"
                                        >
                                          {{ step.summary }}
                                        </span>
                                      </span>
                                      <span
                                        class="message-operation-card__plan-status"
                                      >
                                        {{ planStepStatusLabel(step) }}
                                      </span>
                                    </li>
                                  </ol>
                                  <p
                                    v-else-if="operation.detail"
                                    class="message-operation-card__detail"
                                  >
                                    {{ operation.detail }}
                                  </p>
                                  <div
                                    v-if="
                                      operationCommand(operation) ||
                                      operationCwd(operation) ||
                                      operationExitCode(operation)
                                    "
                                    class="message-operation-card__command"
                                  >
                                    <div
                                      v-if="operationCwd(operation)"
                                      class="message-operation-card__command-meta"
                                    >
                                      cwd={{ operationCwd(operation) }}
                                    </div>
                                    <pre
                                      v-if="operationCommand(operation)"
                                      class="message-operation-card__command-pre"
                                      >{{ operationCommand(operation) }}</pre
                                    >
                                    <div
                                      v-if="operationExitCode(operation)"
                                      class="message-operation-card__command-meta"
                                    >
                                      exit={{ operationExitCode(operation) }}
                                    </div>
                                  </div>
                                  <div
                                    v-if="operationOutput(operation)"
                                    class="message-operation-card__output"
                                  >
                                    <div
                                      class="message-operation-card__output-label"
                                    >
                                      输出摘要
                                    </div>
                                    <pre
                                      class="message-operation-card__output-pre"
                                      >{{ operationOutput(operation) }}</pre
                                    >
                                  </div>
                                  <p
                                    v-if="operationActionHint(operation)"
                                    class="message-operation-card__action"
                                  >
                                    {{ operationActionHint(operation) }}
                                  </p>
                                  <div
                                    v-if="
                                      messageOperationInteractionFormJson(
                                        operation,
                                      ) &&
                                      !isMessageFooterActionOperation(
                                        item,
                                        operation,
                                      )
                                    "
                                    class="message-operation-card__form"
                                    :class="{
                                      'is-submitted':
                                        operationInteractionSubmittedHint(
                                          operation,
                                        ),
                                    }"
                                  >
                                    <div
                                      class="message-operation-card__form-head"
                                    >
                                      <div>
                                        <strong>{{
                                          operationInteractionTitle(operation)
                                        }}</strong>
                                        <p>
                                          {{
                                            operationInteractionDescription(
                                              operation,
                                            )
                                          }}
                                        </p>
                                      </div>
                                      <el-tag size="small" effect="plain">
                                        结构化交互
                                      </el-tag>
                                    </div>
                                    <ElementEasyForm
                                      :form-json="
                                        messageOperationInteractionFormJson(
                                          operation,
                                        )
                                      "
                                      class="message-operation-card__easy-form"
                                    />
                                    <div
                                      class="message-operation-card__form-actions"
                                    >
                                      <el-button
                                        v-if="
                                          operationInteractionCanFallbackToTerminal(
                                            operation,
                                          ) &&
                                          !operationInteractionSubmittedHint(
                                            operation,
                                          )
                                        "
                                        text
                                        @click="
                                          dismissOperationInteractionForm(
                                            operation,
                                          )
                                        "
                                      >
                                        {{
                                          operationInteractionFallbackLabel(
                                            operation,
                                          )
                                        }}
                                      </el-button>
                                      <el-button
                                        type="primary"
                                        :disabled="
                                          !canSubmitOperationInteraction(
                                            operation,
                                          ) ||
                                          Boolean(
                                            operationInteractionSubmittedHint(
                                              operation,
                                            ),
                                          )
                                        "
                                        @click="
                                          submitOperationInteraction(operation)
                                        "
                                      >
                                        {{
                                          operationInteractionSubmittedHint(
                                            operation,
                                          )
                                            ? "已提交，继续执行中"
                                            : operationInteractionSubmitLabel(
                                                operation,
                                              )
                                        }}
                                      </el-button>
                                    </div>
                                  </div>
                                  <div
                                    v-if="
                                      operationInteractionSubmittedHint(
                                        operation,
                                      )
                                    "
                                    class="message-operation-card__submitted"
                                  >
                                    {{
                                      operationInteractionSubmittedHint(
                                        operation,
                                      )
                                    }}
                                  </div>
                                  <div
                                    v-if="
                                      operationActionButtons(operation)
                                        .length &&
                                      !isMessageFooterActionOperation(
                                        item,
                                        operation,
                                      )
                                    "
                                    class="message-operation-card__actions"
                                  >
                                    <el-button
                                      v-for="action in operationActionButtons(
                                        operation,
                                      )"
                                      :key="`${operation.id}-${action.key}`"
                                      size="small"
                                      :type="
                                        action.type === 'danger'
                                          ? 'danger'
                                          : 'primary'
                                      "
                                      :plain="action.type !== 'danger'"
                                      @click="
                                        handleOperationAction(
                                          operation,
                                          action.key,
                                        )
                                      "
                                    >
                                      {{ action.label }}
                                    </el-button>
                                  </div>
                                </article>
                              </div>
                              <div
                                v-if="messageProcessLogEntries(item).length"
                                class="message-process-stream"
                              >
                                <div
                                  v-for="entry in messageProcessLogEntries(
                                    item,
                                  )"
                                  :key="entry.id"
                                  class="message-process-stream__item"
                                  :class="`is-${entry.level}`"
                                >
                                  <span
                                    class="message-process-stream__dot"
                                  ></span>
                                  <span class="message-process-stream__text">
                                    {{ entry.text }}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div
                            v-if="messageBodyHtml(item, idx)"
                            class="message-text"
                            v-html="messageBodyHtml(item, idx)"
                          ></div>
                          <div
                            v-if="messageFooterInteractionOperation(item)"
                            class="message-footer-action message-footer-action--form"
                          >
                            <div class="message-footer-action__form-head">
                              <div class="message-footer-action__content">
                                <strong>{{
                                  operationInteractionTitle(
                                    messageFooterInteractionOperation(item),
                                  )
                                }}</strong>
                                <span>{{
                                  operationInteractionDescription(
                                    messageFooterInteractionOperation(item),
                                  )
                                }}</span>
                              </div>
                              <el-tag size="small" effect="plain">
                                需要你操作
                              </el-tag>
                            </div>
                            <ElementEasyForm
                              :form-json="
                                messageOperationInteractionFormJson(
                                  messageFooterInteractionOperation(item),
                                )
                              "
                              class="message-footer-action__easy-form"
                            />
                            <div class="message-footer-action__form-actions">
                              <el-button
                                v-if="
                                  operationInteractionCanFallbackToTerminal(
                                    messageFooterInteractionOperation(item),
                                  )
                                "
                                text
                                @click="
                                  dismissOperationInteractionForm(
                                    messageFooterInteractionOperation(item),
                                  )
                                "
                              >
                                使用终端兜底
                              </el-button>
                              <el-button
                                type="primary"
                                :disabled="
                                  !canSubmitOperationInteraction(
                                    messageFooterInteractionOperation(item),
                                  )
                                "
                                @click="
                                  submitOperationInteraction(
                                    messageFooterInteractionOperation(item),
                                  )
                                "
                              >
                                确认并继续
                              </el-button>
                            </div>
                          </div>
                          <div
                            v-else-if="messageFooterButtonActionOperation(item)"
                            class="message-footer-action"
                          >
                            <div class="message-footer-action__content">
                              <strong>{{
                                messageFooterButtonActionOperation(item)
                                  .title || "需要你确认"
                              }}</strong>
                              <span>{{
                                messageFooterButtonActionOperation(item)
                                  .summary ||
                                operationActionHint(
                                  messageFooterButtonActionOperation(item),
                                )
                              }}</span>
                            </div>
                            <div class="message-footer-action__buttons">
                              <el-button
                                v-for="action in operationActionButtons(
                                  messageFooterButtonActionOperation(item),
                                )"
                                :key="`footer-${messageFooterButtonActionOperation(item).id}-${action.key}`"
                                size="small"
                                :type="
                                  action.type === 'danger'
                                    ? 'danger'
                                    : 'primary'
                                "
                                :plain="action.type !== 'danger'"
                                @click="
                                  handleOperationAction(
                                    messageFooterButtonActionOperation(item),
                                    action.key,
                                  )
                                "
                              >
                                {{ action.label }}
                              </el-button>
                            </div>
                          </div>
                          <div
                            v-if="
                              item.displayMode !== 'terminal' &&
                              formJsonArtifactsForMessage(item).length
                            "
                            class="message-form-json-artifacts"
                          >
                            <article
                              v-for="(
                                artifact, artifactIndex
                              ) in formJsonArtifactsForMessage(item)"
                              :key="`form-json-${idx}-${artifactIndex}`"
                              class="message-form-json-card"
                            >
                              <div class="message-form-json-card__head">
                                <div>
                                  <strong>{{ artifact.title }}</strong>
                                  <p>
                                    {{ artifact.fieldCount }} 个字段，可复制
                                    formJson 或直接预览。
                                  </p>
                                </div>
                                <el-button
                                  size="small"
                                  type="primary"
                                  plain
                                  @click="copyFormJsonArtifact(artifact)"
                                >
                                  复制 JSON
                                </el-button>
                              </div>
                              <div class="message-form-json-card__preview">
                                <ElementEasyForm
                                  :form-json="artifact.formJson"
                                  class="message-form-json-card__easy-form"
                                />
                              </div>
                            </article>
                          </div>
                        </template>
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
                          v-if="item.taskTreeAudit"
                          class="message-task-tree-audit"
                          :class="[
                            `is-${item.taskTreeAudit.status || 'attention'}`,
                            `has-severity-${item.taskTreeAudit.severity || 'medium'}`,
                          ]"
                        >
                          <div class="message-task-tree-audit__head">
                            <div class="message-task-tree-audit__head-main">
                              <div class="message-task-tree-audit__title">
                                任务推进校验
                              </div>
                              <div class="message-task-tree-audit__signal-tags">
                                <el-tag
                                  size="small"
                                  effect="plain"
                                  :type="
                                    getTaskTreeAuditSeverityMeta(
                                      item.taskTreeAudit.severity,
                                    ).type
                                  "
                                >
                                  {{
                                    getTaskTreeAuditSeverityMeta(
                                      item.taskTreeAudit.severity,
                                    ).label
                                  }}
                                </el-tag>
                                <el-tag
                                  v-if="item.taskTreeAudit.category"
                                  size="small"
                                  effect="plain"
                                  type="info"
                                >
                                  {{
                                    getTaskTreeAuditCategoryLabel(
                                      item.taskTreeAudit.category,
                                    )
                                  }}
                                </el-tag>
                              </div>
                            </div>
                            <el-button
                              text
                              size="small"
                              @click="openTaskTreePanel"
                            >
                              查看任务树
                            </el-button>
                          </div>
                          <div class="message-task-tree-audit__text">
                            {{ item.taskTreeAudit.message }}
                          </div>
                          <div
                            v-if="item.taskTreeAudit.recommended_action"
                            class="message-task-tree-audit__action"
                          >
                            建议动作：{{
                              item.taskTreeAudit.recommended_action
                            }}
                          </div>
                          <div class="message-task-tree-audit__meta">
                            当前节点：
                            {{
                              item.taskTreeAudit.current_node?.title || "未识别"
                            }}
                            <template
                              v-if="item.taskTreeAudit.suggested_status"
                            >
                              · 建议状态
                              {{ item.taskTreeAudit.suggested_status }}
                            </template>
                            <template v-if="item.taskTreeAudit.auto_updated">
                              · 已自动保留
                            </template>
                          </div>
                          <div
                            v-if="item.taskTreeAudit.evidence?.length"
                            class="message-task-tree-audit__evidence"
                          >
                            <div
                              class="message-task-tree-audit__evidence-label"
                            >
                              证据
                            </div>
                            <ul class="message-task-tree-audit__evidence-list">
                              <li
                                v-for="(evidence, evidenceIndex) in item
                                  .taskTreeAudit.evidence"
                                :key="`task-audit-evidence-${evidenceIndex}`"
                              >
                                {{ evidence }}
                              </li>
                            </ul>
                          </div>
                          <div
                            v-if="
                              item.taskTreeAudit.executed_tool_names?.length
                            "
                            class="message-task-tree-audit__tags"
                          >
                            <el-tag
                              v-for="toolName in item.taskTreeAudit
                                .executed_tool_names"
                              :key="`task-audit-${toolName}`"
                              size="small"
                              effect="plain"
                            >
                              {{ toolName }}
                            </el-tag>
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
                </ChatMessageList>
              </div>
            </div>

            <aside v-if="isLocalRunnerSurface" class="local-runner-panel">
              <section class="local-runner-card local-runner-card--self-check">
                <div class="local-runner-card__head">
                  <div>
                    <div class="local-runner-card__eyebrow">Runner</div>
                    <div class="local-runner-card__title">本机 Runner 自检</div>
                  </div>
                  <el-button
                    size="small"
                    :loading="nativeRunnerSelfChecking"
                    :disabled="!nativeDesktopBridgeAvailable"
                    @click="runNativeRunnerSelfCheck"
                  >
                    运行自检
                  </el-button>
                </div>
                <div
                  v-if="!nativeDesktopBridgeAvailable"
                  class="local-runner-empty"
                >
                  当前是网页模式；Tauri 桌面端启动后才会提供本机 Runner。
                </div>
                <div
                  v-else-if="nativeRunnerSelfCheckResults.length"
                  class="local-runner-self-check"
                >
                  <div
                    v-for="item in nativeRunnerSelfCheckResults"
                    :key="item.id"
                    class="local-runner-self-check__item"
                    :class="`is-${item.tone}`"
                  >
                    <div>
                      <strong>{{ item.label }}</strong>
                      <span>{{ item.summary }}</span>
                    </div>
                    <el-tag
                      size="small"
                      :type="runnerSelfCheckTagType(item)"
                      effect="plain"
                    >
                      {{ runnerSelfCheckStatusLabel(item) }}
                    </el-tag>
                  </div>
                </div>
                <div v-else class="local-runner-empty">
                  运行自检会检查原生桥、工作区和少量只读命令白名单。
                </div>
              </section>

              <section class="local-runner-card local-runner-card--approval">
                <div class="local-runner-card__head">
                  <div>
                    <div class="local-runner-card__eyebrow">Approval Queue</div>
                    <div class="local-runner-card__title">命令审批</div>
                  </div>
                  <div class="local-runner-card__actions">
                    <el-button
                      size="small"
                      text
                      :loading="nativeRunnerPermissionRecordsLoading"
                      :disabled="!nativeDesktopBridgeAvailable"
                      @click="refreshNativeRunnerPermissionRecords"
                    >
                      刷新
                    </el-button>
                    <el-tag
                      size="small"
                      :type="terminalApprovalPrompt ? 'warning' : 'success'"
                      effect="plain"
                    >
                      {{ terminalApprovalPrompt ? "等待确认" : "空闲" }}
                    </el-tag>
                  </div>
                </div>
                <div v-if="terminalApprovalPrompt" class="local-approval-panel">
                  <div class="local-approval-panel__title">
                    {{ terminalApprovalPrompt.title }}
                  </div>
                  <p
                    v-if="terminalApprovalPrompt.description"
                    class="local-approval-panel__desc"
                  >
                    {{ terminalApprovalPrompt.description }}
                  </p>
                  <pre
                    v-if="terminalApprovalPrompt.message"
                    class="local-approval-panel__message"
                    >{{ terminalApprovalPrompt.message }}</pre
                  >
                  <div class="local-approval-panel__actions">
                    <el-button
                      size="small"
                      type="danger"
                      plain
                      @click="sendTerminalApprovalChoice('3')"
                    >
                      取消
                    </el-button>
                    <el-button
                      size="small"
                      @click="sendTerminalApprovalChoice('2')"
                    >
                      本会话批准
                    </el-button>
                    <el-button
                      size="small"
                      type="primary"
                      @click="sendTerminalApprovalChoice('1')"
                    >
                      批准一次
                    </el-button>
                  </div>
                </div>
                <div v-else class="local-runner-empty">
                  当前没有待确认命令；需要审批时会固定显示在这里。
                </div>
                <div
                  v-if="nativeRunnerPermissionRecords.length"
                  class="local-permission-records"
                >
                  <div class="local-permission-records__title">
                    最近审批记录
                  </div>
                  <div
                    v-for="record in nativeRunnerPermissionRecords"
                    :key="record.decisionId"
                    class="local-permission-record"
                  >
                    <div>
                      <strong>{{
                        runnerPermissionDecisionLabel(record)
                      }}</strong>
                      <span>{{ runnerPermissionRecordSummary(record) }}</span>
                    </div>
                    <span>{{ runnerPermissionRecordTime(record) }}</span>
                  </div>
                </div>
              </section>

              <section class="local-runner-card local-runner-card--process">
                <div class="local-runner-card__head">
                  <div>
                    <div class="local-runner-card__eyebrow">Process</div>
                    <div class="local-runner-card__title">执行过程</div>
                  </div>
                  <el-tag
                    size="small"
                    effect="plain"
                    :type="localRunnerProcessStatusTagType"
                  >
                    {{ terminalPanelStatusText }}
                  </el-tag>
                </div>
                <div class="local-process-summary">
                  <div>
                    <span>会话</span>
                    <strong>{{ hostTerminalSessionId || "未连接" }}</strong>
                  </div>
                  <div>
                    <span>命令</span>
                    <strong>{{ terminalActiveCommand || "等待任务" }}</strong>
                  </div>
                  <div>
                    <span>日志</span>
                    <strong>{{ terminalPanelLineCount }} 行</strong>
                  </div>
                </div>
                <div class="local-process-timeline">
                  <div
                    v-for="item in localRunnerProcessItems"
                    :key="item.id"
                    class="local-process-timeline__item"
                    :class="`is-${item.phase}`"
                  >
                    <span class="local-process-timeline__marker">
                      <CircleCheck
                        v-if="item.phase === 'completed'"
                        :size="13"
                      />
                      <span v-else></span>
                    </span>
                    <span class="local-process-timeline__main">
                      <span class="local-process-timeline__title">
                        {{ item.title }}
                      </span>
                      <span
                        v-if="item.summary"
                        class="local-process-timeline__summary"
                      >
                        {{ item.summary }}
                      </span>
                    </span>
                    <span class="local-process-timeline__phase">
                      {{ item.phaseLabel }}
                    </span>
                  </div>
                </div>
              </section>

              <section class="local-runner-card local-runner-card--sessions">
                <div class="local-runner-card__head">
                  <div>
                    <div class="local-runner-card__eyebrow">Run History</div>
                    <div class="local-runner-card__title">Runner 运行记录</div>
                  </div>
                  <el-button
                    size="small"
                    text
                    :loading="nativeExternalAgentSessionRecordsLoading"
                    :disabled="!nativeDesktopBridgeAvailable"
                    @click="refreshNativeExternalAgentSessionRecords"
                  >
                    刷新
                  </el-button>
                </div>
                <div
                  v-if="!nativeDesktopBridgeAvailable"
                  class="local-runner-empty"
                >
                  当前是网页模式；Tauri 桌面端启动后才会提供本机运行记录。
                </div>
                <div
                  v-else-if="nativeExternalAgentSessionRecords.length"
                  class="local-runner-session-records"
                >
                  <button
                    v-for="record in nativeExternalAgentSessionRecords"
                    :key="record.sessionId"
                    type="button"
                    class="local-runner-session-record"
                    :class="{
                      'is-active':
                        selectedNativeExternalAgentRecordId ===
                        record.sessionId,
                    }"
                    @click="selectNativeExternalAgentSessionRecord(record)"
                  >
                    <div class="local-runner-session-record__main">
                      <strong>{{ record.summary || "Runner 会话" }}</strong>
                      <span>{{
                        nativeExternalAgentRecordSummary(record)
                      }}</span>
                    </div>
                    <div class="local-runner-session-record__meta">
                      <el-tag
                        size="small"
                        effect="plain"
                        :type="nativeExternalAgentRecordTagType(record)"
                      >
                        {{ nativeExternalAgentRecordStatusLabel(record) }}
                      </el-tag>
                      <span>{{ nativeExternalAgentRecordTime(record) }}</span>
                    </div>
                  </button>
                </div>
                <div v-else class="local-runner-empty">
                  暂无 Runner 运行记录；从 AI 对话外部 Agent
                  模式发送任务后会出现在这里。
                </div>
              </section>

              <section class="local-runner-card local-runner-card--workspace">
                <div class="local-runner-card__head">
                  <div>
                    <div class="local-runner-card__eyebrow">Workspace</div>
                    <div class="local-runner-card__title">文件树 / 编辑器</div>
                  </div>
                  <el-button
                    size="small"
                    text
                    :loading="workspaceFileTreeLoading"
                    :disabled="!canUseWorkspaceFiles"
                    @click="refreshWorkspaceFileTree"
                  >
                    刷新
                  </el-button>
                </div>
                <div class="local-workspace-root">
                  {{ projectWorkspaceResolved || "未配置项目工作区" }}
                </div>
                <div v-if="canUseWorkspaceFiles" class="local-workspace-source">
                  {{ workspaceFileBridgeLabel }}
                </div>
                <div v-if="!canUseWorkspaceFiles" class="local-runner-empty">
                  先在设置中保存项目工作区后，才能直接浏览和编辑本机文件。
                </div>
                <template v-else>
                  <div class="local-file-browser">
                    <div class="local-file-browser__toolbar">
                      <el-button
                        size="small"
                        text
                        :disabled="!workspaceFileTreePath"
                        @click="openWorkspaceDirectory(workspaceParentPath)"
                      >
                        上一级
                      </el-button>
                      <span>{{ workspaceFileTreePath || "." }}</span>
                    </div>
                    <div class="local-file-list">
                      <button
                        v-for="item in workspaceFileItems"
                        :key="`${item.kind}:${item.path}`"
                        type="button"
                        class="local-file-item"
                        :class="{
                          'is-active': item.path === activeWorkspaceFilePath,
                        }"
                        @click="handleWorkspaceFileClick(item)"
                      >
                        <span class="local-file-item__icon">
                          {{ item.kind === "directory" ? "DIR" : "TXT" }}
                        </span>
                        <span class="local-file-item__name">{{
                          item.name
                        }}</span>
                      </button>
                      <div
                        v-if="!workspaceFileItems.length"
                        class="local-runner-empty"
                      >
                        当前目录没有可展示文件。
                      </div>
                    </div>
                  </div>
                  <div class="local-editor">
                    <div class="local-editor__head">
                      <span>{{ activeWorkspaceFilePath || "未选择文件" }}</span>
                      <el-button
                        size="small"
                        type="primary"
                        :loading="workspaceFileSaving"
                        :disabled="
                          !activeWorkspaceFilePath || !workspaceFileDirty
                        "
                        @click="saveActiveWorkspaceFile"
                      >
                        {{ workspaceFileReadOnly ? "准备写入" : "保存" }}
                      </el-button>
                    </div>
                    <el-input
                      v-model="workspaceFileDraft"
                      type="textarea"
                      resize="none"
                      :autosize="{ minRows: 8, maxRows: 14 }"
                      :disabled="
                        !activeWorkspaceFilePath || workspaceFileLoading
                      "
                      :readonly="false"
                      :placeholder="
                        workspaceFileReadOnly
                          ? '桌面端可编辑草稿；点击准备写入只生成确认摘要，不会直接保存。'
                          : '从上方文件树选择文本文件后可在这里编辑。'
                      "
                      class="local-editor__textarea"
                    />
                  </div>
                  <div class="local-diff-preview">
                    <div class="local-diff-preview__head">
                      <div>
                        <strong>差异预览</strong>
                        <span>{{ workspaceDiffTargetLabel }}</span>
                      </div>
                      <div class="local-runner-card__actions">
                        <el-tag size="small" effect="plain">
                          {{ workspaceDiffStatusLabel }}
                        </el-tag>
                        <el-button
                          size="small"
                          text
                          :loading="workspaceDiffLoading"
                          :disabled="!canPreviewWorkspaceDiff"
                          @click="refreshWorkspaceDiffPreview"
                        >
                          预览
                        </el-button>
                      </div>
                    </div>
                    <div
                      v-if="!canPreviewWorkspaceDiff"
                      class="local-runner-empty"
                    >
                      差异预览需要 Tauri 桌面端原生桥和项目工作区。
                    </div>
                    <div
                      v-else-if="
                        workspaceDiffPreview?.reason &&
                        !workspaceDiffPreview?.available
                      "
                      class="local-runner-empty"
                    >
                      {{ workspaceDiffPreview.reason }}
                    </div>
                    <pre
                      v-else-if="
                        workspaceDiffPreview?.diff ||
                        workspaceDiffPreview?.summary ||
                        workspaceDiffPreview?.status
                      "
                      class="local-diff-preview__output"
                      >{{
                        [
                          workspaceDiffPreview?.status,
                          workspaceDiffPreview?.summary,
                          workspaceDiffPreview?.diff,
                        ]
                          .filter(Boolean)
                          .join("\n\n")
                      }}</pre
                    >
                    <div v-else class="local-runner-empty">
                      尚未生成差异预览；没有选中文件时会预览整个工作区。
                    </div>
                  </div>
                </template>
              </section>

              <section class="local-runner-card local-runner-card--terminal">
                <div class="local-runner-card__head">
                  <div>
                    <div class="local-runner-card__eyebrow">Terminal</div>
                    <div class="local-runner-card__title">终端输出</div>
                  </div>
                  <el-tag size="small" effect="plain">
                    {{ terminalPanelStatusText }}
                  </el-tag>
                </div>
                <pre class="local-terminal-output">{{ terminalPanelText }}</pre>
              </section>
            </aside>

            <el-drawer
              v-model="nativeExternalAgentSessionDetailVisible"
              size="min(760px, calc(100vw - 24px))"
              title="Runner 运行详情"
              class="runner-session-drawer"
            >
              <div class="runner-session-detail">
                <div class="runner-session-detail__hero">
                  <div>
                    <div class="runner-session-detail__eyebrow">
                      {{
                        nativeExternalAgentSession?.label || "External Agent"
                      }}
                    </div>
                    <div class="runner-session-detail__title">
                      {{ nativeExternalAgentSession?.summary || "Runner 会话" }}
                    </div>
                    <div class="runner-session-detail__meta">
                      <span>{{ nativeExternalAgentSession?.sessionId }}</span>
                      <span>
                        状态
                        {{
                          nativeExternalAgentRecordStatusLabel(
                            nativeExternalAgentSession,
                          )
                        }}
                      </span>
                      <span>
                        exit={{ nativeExternalAgentSession?.exitCode ?? "-" }}
                      </span>
                    </div>
                  </div>
                  <el-tag
                    size="small"
                    effect="plain"
                    :type="
                      nativeExternalAgentRecordTagType(
                        nativeExternalAgentSession,
                      )
                    "
                  >
                    {{
                      nativeExternalAgentRecordStatusLabel(
                        nativeExternalAgentSession,
                      )
                    }}
                  </el-tag>
                </div>
                <div class="runner-session-detail__actions">
                  <el-button
                    size="small"
                    :disabled="!nativeExternalAgentFinalAnswerText"
                    @click="copyNativeExternalAgentFinalAnswer"
                  >
                    复制最终回答
                  </el-button>
                  <el-button
                    size="small"
                    :disabled="!nativeExternalAgentFullLogText"
                    @click="copyNativeExternalAgentFullLog"
                  >
                    复制完整日志
                  </el-button>
                </div>
                <div class="runner-session-detail__grid">
                  <div>
                    <span>执行器</span>
                    <strong>{{
                      nativeExternalAgentSession?.agentType || "-"
                    }}</strong>
                  </div>
                  <div>
                    <span>工作区</span>
                    <strong>{{
                      nativeExternalAgentSession?.workspacePath || "-"
                    }}</strong>
                  </div>
                  <div>
                    <span>命令</span>
                    <strong>{{ nativeExternalAgentCommandText || "-" }}</strong>
                  </div>
                </div>
                <el-tabs
                  v-model="nativeExternalAgentDetailActiveTab"
                  class="runner-session-detail__tabs"
                >
                  <el-tab-pane name="terminal">
                    <template #label>
                      <span>终端</span>
                      <em>{{ nativeExternalAgentLogStats.total }}</em>
                    </template>
                    <section
                      class="runner-session-detail__section runner-session-detail__terminal"
                    >
                      <div class="runner-session-detail__section-head">
                        <div>
                          <strong>运行终端</strong>
                          <span>{{
                            nativeExternalAgentTerminalStatusText
                          }}</span>
                        </div>
                        <div class="runner-session-detail__terminal-actions">
                          <el-button
                            v-for="item in nativeExternalAgentTerminalControls"
                            :key="item.key"
                            size="small"
                            text
                            :type="item.type || 'default'"
                            :disabled="!canWriteNativeExternalAgentStdin"
                            :loading="nativeExternalAgentStdinSending"
                            @click="
                              sendNativeExternalAgentControl(item.content)
                            "
                          >
                            {{ item.label }}
                          </el-button>
                        </div>
                      </div>
                      <pre
                        ref="nativeExternalAgentTerminalRef"
                        class="runner-session-detail__terminal-output"
                        :class="{
                          'is-running':
                            nativeExternalAgentSession?.status === 'running',
                        }"
                        >{{
                          nativeExternalAgentTerminalText ||
                          "Runner 启动后会在这里显示执行器输出"
                        }}</pre
                      >
                    </section>
                    <div
                      v-if="nativeExternalAgentInteractionPrompt"
                      class="runner-session-detail__interaction"
                    >
                      <div class="runner-session-detail__section-head">
                        <strong>{{
                          nativeExternalAgentInteractionPrompt.title
                        }}</strong>
                        <span>{{
                          nativeExternalAgentInteractionPrompt.description
                        }}</span>
                      </div>
                      <ElementEasyForm
                        :form-json="nativeExternalAgentInteractionFormJson"
                        class="runner-session-detail__easy-form"
                      />
                      <div class="runner-session-detail__actions">
                        <el-button
                          size="small"
                          text
                          @click="dismissNativeExternalAgentInteraction"
                        >
                          手动输入
                        </el-button>
                        <el-button
                          size="small"
                          type="primary"
                          :loading="nativeExternalAgentStdinSending"
                          @click="submitNativeExternalAgentInteraction"
                        >
                          确认
                        </el-button>
                      </div>
                    </div>
                    <div
                      v-if="canWriteNativeExternalAgentStdin"
                      class="runner-session-detail__stdin"
                    >
                      <el-input
                        v-model="nativeExternalAgentStdinDraft"
                        size="small"
                        placeholder="发送给 Runner 的输入"
                        clearable
                        @keyup.enter="sendNativeExternalAgentStdin"
                      />
                      <el-button
                        size="small"
                        type="primary"
                        :loading="nativeExternalAgentStdinSending"
                        @click="sendNativeExternalAgentStdin"
                      >
                        发送
                      </el-button>
                    </div>
                  </el-tab-pane>
                  <el-tab-pane name="final">
                    <template #label>
                      <span>最终回答</span>
                    </template>
                    <section class="runner-session-detail__section">
                      <div class="runner-session-detail__section-head">
                        <strong>最终回答</strong>
                        <span>优先展示 Runner finalOutput</span>
                      </div>
                      <pre class="runner-session-detail__output">{{
                        nativeExternalAgentFinalAnswerText || "暂无最终回答"
                      }}</pre>
                    </section>
                  </el-tab-pane>
                  <el-tab-pane name="files">
                    <template #label>
                      <span>文件</span>
                      <em>{{ nativeExternalAgentFileEvidenceItems.length }}</em>
                    </template>
                    <div
                      v-if="nativeExternalAgentFileEvidenceItems.length"
                      class="runner-session-detail__evidence-list"
                    >
                      <article
                        v-for="(
                          item, index
                        ) in nativeExternalAgentFileEvidenceItems"
                        :key="`runner-file-${index}`"
                        class="runner-session-detail__evidence"
                      >
                        <span>{{ item.kind }}</span>
                        <strong>{{ item.path || item.title }}</strong>
                        <p v-if="item.summary">{{ item.summary }}</p>
                        <small v-if="item.status">{{ item.status }}</small>
                      </article>
                    </div>
                    <div v-else class="runner-session-detail__empty">
                      当前 Runner 会话暂无文件、diff 或写入准备记录。
                    </div>
                  </el-tab-pane>
                  <el-tab-pane name="verification">
                    <template #label>
                      <span>验证</span>
                      <em>{{ nativeExternalAgentVerificationItems.length }}</em>
                    </template>
                    <div
                      v-if="nativeExternalAgentVerificationItems.length"
                      class="runner-session-detail__evidence-list"
                    >
                      <article
                        v-for="(
                          item, index
                        ) in nativeExternalAgentVerificationItems"
                        :key="`runner-verification-${index}`"
                        class="runner-session-detail__evidence"
                      >
                        <span>{{ item.kind }}</span>
                        <strong>{{ item.title }}</strong>
                        <p v-if="item.summary">{{ item.summary }}</p>
                        <small v-if="runnerEvidenceMetaText(item)">
                          {{ runnerEvidenceMetaText(item) }}
                        </small>
                      </article>
                    </div>
                    <div v-else class="runner-session-detail__empty">
                      当前 Runner 会话暂无验证命令或自检结果。
                    </div>
                  </el-tab-pane>
                  <el-tab-pane name="permissions">
                    <template #label>
                      <span>权限</span>
                      <em>{{
                        nativeExternalAgentSessionPermissionRecords.length
                      }}</em>
                    </template>
                    <div
                      v-if="nativeExternalAgentSessionPermissionRecords.length"
                      class="runner-session-detail__evidence-list"
                    >
                      <article
                        v-for="record in nativeExternalAgentSessionPermissionRecords"
                        :key="
                          record.id ||
                          `${record.command}-${record.createdAtEpochMs}`
                        "
                        class="runner-session-detail__evidence"
                      >
                        <span>{{ runnerPermissionDecisionLabel(record) }}</span>
                        <strong>{{
                          runnerPermissionRecordSummary(record)
                        }}</strong>
                        <small>{{ runnerPermissionRecordTime(record) }}</small>
                      </article>
                    </div>
                    <div v-else class="runner-session-detail__empty">
                      当前 Runner 会话暂无权限决策记录。
                    </div>
                  </el-tab-pane>
                  <el-tab-pane name="diagnostics">
                    <template #label>
                      <span>诊断</span>
                      <em>{{
                        nativeExternalAgentLogStats.stderr +
                        nativeExternalAgentLogStats.system
                      }}</em>
                    </template>
                    <div class="runner-session-detail__diagnostic-grid">
                      <div
                        v-for="item in nativeExternalAgentDiagnosticItems"
                        :key="item.label"
                      >
                        <span>{{ item.label }}</span>
                        <strong>{{ item.value }}</strong>
                      </div>
                      <div>
                        <span>logs</span>
                        <strong>
                          stdout={{
                            nativeExternalAgentLogStats.stdout
                          }}
                          stderr={{
                            nativeExternalAgentLogStats.stderr
                          }}
                          stdin={{
                            nativeExternalAgentLogStats.stdin
                          }}
                          system={{ nativeExternalAgentLogStats.system }}
                        </strong>
                      </div>
                    </div>
                    <section class="runner-session-detail__section">
                      <div class="runner-session-detail__section-head">
                        <strong>stderr / system / stdin</strong>
                        <span>默认归入诊断，不进入主回答</span>
                      </div>
                      <pre class="runner-session-detail__output">{{
                        nativeExternalAgentDiagnosticText || "无诊断日志"
                      }}</pre>
                    </section>
                  </el-tab-pane>
                </el-tabs>
              </div>
            </el-drawer>
          </div>

          <TerminalApprovalDialog
            v-if="!isLocalRunnerSurface"
            v-model="terminalApprovalDialogVisible"
            :prompt="terminalApprovalPrompt"
            @choose="sendTerminalApprovalChoice"
          />

          <ChatComposer
            ref="chatComposerRef"
            v-model:draft-text="draftText"
            v-model:input-focused="inputFocused"
            v-model:selected-model-option-value="selectedModelOptionValue"
            :show-agent-workflow-status-strip="showAgentWorkflowStatusStrip"
            :agent-workflow-state="agentWorkflowState"
            :agent-workflow-meta-items="agentWorkflowMetaItems"
            :show-working-status-bar="showWorkingStatusBar"
            :working-status-title="workingStatusTitle"
            :working-status-elapsed-label="workingStatusElapsedLabel"
            :working-status-meta-items="workingStatusMetaItems"
            :is-dragging="isDragging"
            :upload-files="uploadFiles"
            :format-file-type="formatFileType"
            :composer-placeholder="composerPlaceholder"
            :is-composer-disabled="isComposerDisabled"
            :is-chat-settings-display-ready="isChatSettingsDisplayReady"
            :is-slash-command-menu-visible="isSlashCommandMenuVisible"
            :filtered-slash-commands="filteredSlashCommands"
            :slash-command-highlight-index="slashCommandHighlightIndex"
            :is-external-agent-mode="isExternalAgentMode"
            :provider-model-groups="providerModelGroups"
            :chat-loading="chatLoading"
            :external-agent-display-label="externalAgentDisplayLabel"
            :has-selected-project="hasSelectedProject"
            :execution-runtime-tone-class="executionRuntimeToneClass"
            :composer-execution-chip-label="composerExecutionChipLabel"
            :execution-runtime-title="executionRuntimeTitle"
            :execution-runtime-description="executionRuntimeDescription"
            :composer-execution-status-tag-type="composerExecutionStatusTagType"
            :composer-execution-status-label="composerExecutionStatusLabel"
            :composer-execution-summary-items="composerExecutionSummaryItems"
            :composer-execution-detail-available="
              composerExecutionDetailAvailable
            "
            :native-executor-detecting="nativeExecutorDetecting"
            :native-runner-self-checking="nativeRunnerSelfChecking"
            :external-agent-warmup-loading="externalAgentWarmupLoading"
            :execution-runtime-action-label="executionRuntimeActionLabel"
            :selected-project-id="selectedProjectId"
            :composer-hint-text="composerHintText"
            :show-pause-generation-button="showPauseGenerationButton"
            :can-send="canSend"
            @focus-agent-workflow-operation="focusAgentWorkflowOperation"
            @drag-over="handleDragOver"
            @drag-leave="handleDragLeave"
            @drop-files="handleDrop"
            @remove-file="removeFile"
            @editor-blur="handleEditorBlur"
            @editor-keydown="handleEditorKeydown"
            @editor-paste="handleEditorPaste"
            @editor-composition-start="handleEditorCompositionStart"
            @editor-composition-end="handleEditorCompositionEnd"
            @apply-slash-command-selection="applySlashCommandSelection"
            @open-settings="openSettingsCenter"
            @open-execution-detail="openComposerExecutionDetail"
            @execute-primary="handleComposerExecutionPrimaryAction"
            @file-change="handleFileChange"
            @stop-generation="stopGeneration"
            @send="doSend"
          >
            <template #media-parameters>
              <ChatMediaParameterPopover
                v-model="mediaParameterPopoverVisible"
                :visible="shouldShowMediaParameterTrigger"
                :disabled="chatLoading"
                :mode="currentModelParameterMode"
                :trigger-label="currentMediaParameterTriggerLabel"
                :panel-title="currentMediaParameterPanelTitle"
                :model-summary="currentModelSummary"
                :sections="currentModelParameterSections"
                :show-four-views-option="shouldShowImageFourViewsOption"
                :four-views-enabled="imageGenerateFourViewsEnabled"
                @select-parameter="setCurrentModelParameterValue"
                @toggle-four-views="toggleImageGenerateFourViews"
              />
            </template>
          </ChatComposer>

          <ChatTaskTreePanel
            v-model="taskTreePanelVisible"
            v-model:status-draft="taskTreeStatusDraft"
            v-model:verification-draft="taskTreeVerificationDraft"
            v-model:summary-draft="taskTreeSummaryDraft"
            :loading="taskTreeLoading"
            :saving="taskTreeSaving"
            :task-tree="displayedChatTaskTree"
            :health="displayedChatTaskTreeHealth"
            :has-task-tree="hasChatTaskTree"
            :readonly="taskTreeIsReadonly"
            :progress-label="taskTreeProgressLabel"
            :tree-data="taskTreeTreeData"
            :selected-node-id="selectedTaskTreeNodeId"
            :selected-node="taskTreeSelectedNode"
            :selected-node-child-count="taskTreeSelectedNodeChildCount"
            :status-options="taskTreeStatusOptions"
            :verification-placeholder="taskTreeVerificationPlaceholder"
            :save-hint="taskTreeSaveHint"
            @delete-current="deleteCurrentTaskTree"
            @node-click="handleTaskTreeNodeClick"
            @save-node="saveTaskTreeNode"
          />
        </div>
      </div>
    </div>
  </div>

  <UnifiedMcpAccessDialog
    v-model="unifiedMcpDialogVisible"
    title="统一 MCP 接入"
    :project-id="mcpDialogProjectId"
    :project-label="mcpDialogProjectLabel"
    :chat-session-id="currentChatSessionId"
  />

  <GroupChatDialog
    v-model="groupChatDialogVisible"
    :title="groupChatDialogTitle"
    :status="groupChatDialogStatus"
    :draft="groupChatDraft"
    :platform-options="groupChatPlatformOptions"
    :connector-options="groupBotConnectorOptions"
    :connector-hint="groupBotConnectorHint"
    :resolve-identity-options="groupChatResolveIdentityOptions"
    :editing-session-id="groupChatEditingSessionId"
    :creating="groupChatCreating"
    :resolving="groupChatResolving"
    :editing-resolved="groupChatEditingResolved"
    :can-submit="canSubmitGroupChatDialog"
    @update:draft="groupChatDraft = $event"
    @closed="resetGroupChatDraft"
    @resolve="resolveGroupChatSourceId"
    @submit="submitGroupChatDialog"
  />

  <CodePreviewDialog
    v-model="codePreviewVisible"
    :title="codePreviewTitle"
    :srcdoc="codePreviewSrcdoc"
    :error="codePreviewError"
  />

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

  <SkillResourceDialog
    v-model="skillResourceDialogVisible"
    v-model:search-query="skillResourceSearchQuery"
    :workspace-path-resolved="workspacePathResolved"
    :directory-resolved="skillResourceDirectoryResolved"
    :directory-picking="skillResourceDirectoryPicking"
    :search-loading="skillResourceSearchLoading"
    :search-results="skillResourceSearchResults"
    :resolved-queries="skillResourceSearchResolvedQueries"
    :sites="skillResourceSites"
    :installing-slug="skillResourceInstallingSlug"
    @use-workspace="useWorkspaceAsSkillDirectory"
    @pick-directory="pickSkillResourceDirectory"
    @copy-directory="copySkillResourceDirectory"
    @search="searchSkillResources"
    @reset-search="resetSkillResourceSearch"
    @install-site="installSkillResource"
    @copy-site="copySkillResourceSite"
  />

  <div
    v-if="isSettingsCenterRoute"
    class="settings-center-page"
    v-loading="loading"
  >
    <div
      class="settings-center-shell"
      :class="{
        'settings-center-shell--single': settingsInternalItems.length <= 1,
      }"
    >
      <aside
        v-if="settingsInternalItems.length > 1"
        class="settings-center-sidebar"
        ref="settingsSidebarRef"
      >
        <div class="settings-center-sidebar-card">
          <div class="settings-center-brand-panel">
            <div class="settings-center-brand">
              <div class="settings-center-brand__mark">AI</div>
              <div>
                <div class="settings-center-brand__name">对话设置</div>
                <div class="settings-center-brand__meta">
                  仅作用于当前对话上下文
                </div>
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

      <section
        class="settings-center-stage"
        :class="{
          'settings-center-stage--single': settingsInternalItems.length <= 1,
        }"
      >
        <div class="settings-center-context-bar" ref="settingsContextBarRef">
          <div class="settings-center-context-bar__copy">
            <div class="settings-center-context-bar__title">
              {{ activeSettingsPanelMeta?.label || "设置" }}
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
            <el-button
              plain
              :loading="settingsSaving"
              @click="saveProjectChatSettings(false)"
            >
              立即同步
            </el-button>
            <el-button text @click="closeSettingsCenter">关闭</el-button>
          </div>
        </div>

        <div
          v-if="activeSettingsPanel === 'chat'"
          class="settings-center-stage__body settings-center-stage__body--chat"
        >
          <div class="settings-chat-layout settings-chat-layout--single">
            <div class="settings-chat-main settings-chat-main--wide">
              <div class="settings-chat-main-card" ref="settingsMainCardRef">
                <section class="settings-chat-quick-overview">
                  <article class="settings-chat-quick-overview__card">
                    <span class="settings-chat-quick-overview__label">
                      项目上下文
                    </span>
                    <strong class="settings-chat-quick-overview__value">{{
                      hasSelectedProject ? currentProjectLabel : "未选择项目"
                    }}</strong>
                    <span class="settings-chat-quick-overview__meta">
                      {{
                        hasSelectedProject
                          ? "当前改动只影响这个项目下的对话"
                          : "当前仅维护通用对话行为"
                      }}
                    </span>
                  </article>
                  <article class="settings-chat-quick-overview__card">
                    <span class="settings-chat-quick-overview__label">
                      执行对象
                    </span>
                    <strong class="settings-chat-quick-overview__value">{{
                      selectedEmployeeSummary
                    }}</strong>
                    <span class="settings-chat-quick-overview__meta">
                      {{
                        projectChatSettings.employee_coordination_mode ===
                        "manual"
                          ? "手动保留当前工具池"
                          : "允许系统自动协作"
                      }}
                    </span>
                  </article>
                  <article class="settings-chat-quick-overview__card">
                    <span class="settings-chat-quick-overview__label">
                      当前模型
                    </span>
                    <strong class="settings-chat-quick-overview__value">{{
                      currentModelTypeLabel
                    }}</strong>
                    <span class="settings-chat-quick-overview__meta">
                      {{ currentModelSummary }}
                    </span>
                  </article>
                  <article class="settings-chat-quick-overview__card">
                    <span class="settings-chat-quick-overview__label">
                      工具与 MCP
                    </span>
                    <strong class="settings-chat-quick-overview__value">{{
                      singleRoundAnswerOnly
                        ? "本轮仅回答"
                        : projectChatSettings.auto_use_tools
                          ? "允许工具调用"
                          : "关闭工具调用"
                    }}</strong>
                    <span class="settings-chat-quick-overview__meta">
                      {{
                        projectToolModules.length
                          ? `项目工具 ${selectedProjectToolNames.length}/${projectToolModules.length}`
                          : "当前没有项目级工具"
                      }}
                    </span>
                  </article>
                </section>

                <section
                  class="settings-parameter-section settings-parameter-section--compact"
                >
                  <div class="settings-parameter-section__header">
                    <div class="settings-parameter-section__title">
                      快速调整
                    </div>
                    <p class="settings-parameter-section__desc">
                      打开页面后优先处理这里。模型切换仍在主对话输入框左下角完成，这里只负责本轮的上下文、风格和工具边界。
                    </p>
                  </div>
                  <el-form
                    label-position="top"
                    class="settings-form settings-form--quick"
                    size="default"
                  >
                    <div class="settings-quick-form-grid">
                      <el-form-item label="执行员工">
                        <el-select
                          v-model="selectedEmployeeIds"
                          multiple
                          collapse-tags
                          collapse-tags-tooltip
                          filterable
                          clearable
                          placeholder="留空表示自动分配员工"
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
                            </div>
                          </el-option>
                        </el-select>
                      </el-form-item>

                      <div class="settings-execution-section">
                        <span>执行入口</span>
                        <strong
                          >选择这轮对话由服务端模型回答，还是交给外部 Agent
                          执行。</strong
                        >
                      </div>

                      <el-form-item label="执行方式">
                        <div
                          v-if="!isChatSettingsDisplayReady"
                          class="settings-loading-placeholder"
                        >
                          正在加载项目配置...
                        </div>
                        <el-select
                          v-else
                          v-model="projectChatSettings.chat_mode"
                          class="full-width"
                          :disabled="!selectedProjectId"
                        >
                          <el-option label="系统对话" value="system" />
                          <el-option
                            label="外部 Agent"
                            value="external_agent"
                            :disabled="!canUseExternalAgent"
                          />
                        </el-select>
                      </el-form-item>

                      <div
                        v-if="isExternalAgentMode"
                        class="settings-execution-section settings-execution-section--runtime"
                      >
                        <span>本机执行环境</span>
                        <strong
                          >工作区和权限都属于运行执行器的那台电脑；桌面端使用原生桥，浏览器兼容模式才需要本地连接器。</strong
                        >
                      </div>

                      <div
                        v-if="isExternalAgentMode"
                        class="settings-runtime-status-card"
                        :class="executionRuntimeToneClass"
                      >
                        <div class="settings-runtime-status-card__main">
                          <span
                            class="settings-runtime-status-card__dot"
                          ></span>
                          <div>
                            <strong>{{ executionRuntimeTitle }}</strong>
                            <span>{{ executionRuntimeDescription }}</span>
                          </div>
                        </div>
                        <div class="settings-runtime-status-card__grid">
                          <span>运行位置</span>
                          <strong>{{
                            nativeDesktopBridgeAvailable
                              ? "桌面端原生桥"
                              : usingLocalConnector
                                ? "本地连接器"
                                : "网页模式"
                          }}</strong>
                          <span>执行器</span>
                          <strong>{{ externalAgentDisplayLabel }}</strong>
                          <span>工作区</span>
                          <strong>{{ executionWorkspaceLabel }}</strong>
                          <span>权限</span>
                          <strong>{{
                            projectChatSettings.connector_sandbox_mode ||
                            "workspace-write"
                          }}</strong>
                          <span>Codex</span>
                          <strong>{{ nativeExecutorLabel("codex") }}</strong>
                          <span>Hermes</span>
                          <strong>{{ nativeExecutorLabel("hermes") }}</strong>
                          <span>Claude Code</span>
                          <strong>{{
                            nativeExecutorLabel("claudeCode")
                          }}</strong>
                          <span>原生桥</span>
                          <strong>{{ nativeDesktopRuntimeLabel }}</strong>
                        </div>
                        <div class="settings-runtime-status-card__actions">
                          <el-button
                            size="small"
                            :loading="nativeExecutorDetecting"
                            @click="refreshNativeExecutorStatus"
                          >
                            检查环境
                          </el-button>
                          <el-button
                            size="small"
                            plain
                            :loading="nativeRunnerSelfChecking"
                            :disabled="!nativeDesktopBridgeAvailable"
                            @click="runNativeRunnerSelfCheck"
                          >
                            Runner 自检
                          </el-button>
                          <el-button
                            size="small"
                            type="primary"
                            plain
                            :loading="nativeExternalAgentRunning"
                            :disabled="!nativeDesktopBridgeAvailable"
                            @click="startNativeExternalAgentSession"
                          >
                            启动 Runner
                          </el-button>
                        </div>
                        <div
                          v-if="nativeWorkspaceStatusLabel"
                          class="settings-runtime-status-card__hint"
                        >
                          {{ nativeWorkspaceStatusLabel }}
                        </div>
                        <div class="settings-runtime-status-card__hint">
                          Runner 会启动当前外部 Agent
                          的非交互进程并持续采集日志；聊天区暂停只会转入后台运行。
                        </div>
                        <div
                          v-if="nativeExternalAgentSession"
                          class="settings-runtime-status-card__run-result"
                        >
                          <div class="settings-runtime-status-card__run-head">
                            <strong>{{
                              nativeExternalAgentSession.summary ||
                              "Runner 会话"
                            }}</strong>
                            <span>
                              {{ nativeExternalAgentSession.status }}
                              · exit={{
                                nativeExternalAgentSession.exitCode ?? "-"
                              }}
                            </span>
                          </div>
                          <pre v-if="nativeExternalAgentSessionOutput">{{
                            nativeExternalAgentSessionOutput
                          }}</pre>
                          <pre
                            v-if="nativeExternalAgentSessionError"
                            class="is-stderr"
                            >{{ nativeExternalAgentSessionError }}</pre
                          >
                          <div
                            v-if="canWriteNativeExternalAgentStdin"
                            class="settings-runtime-status-card__stdin"
                          >
                            <el-input
                              v-model="nativeExternalAgentStdinDraft"
                              size="small"
                              placeholder="发送给 Runner 的输入"
                              clearable
                              @keyup.enter="sendNativeExternalAgentStdin"
                            />
                            <el-button
                              size="small"
                              :loading="nativeExternalAgentStdinSending"
                              @click="sendNativeExternalAgentStdin"
                            >
                              发送
                            </el-button>
                          </div>
                          <span
                            v-if="nativeExternalAgentSession.blockedReason"
                            class="settings-runtime-status-card__hint"
                          >
                            {{ nativeExternalAgentSession.blockedReason }}
                          </span>
                        </div>
                        <div
                          v-if="nativeRunnerSelfCheckResults.length"
                          class="settings-runtime-status-card__runner"
                        >
                          <div
                            v-for="item in nativeRunnerSelfCheckResults"
                            :key="item.id"
                            class="settings-runtime-status-card__runner-item"
                            :class="`is-${item.tone}`"
                          >
                            <span>{{ item.label }}</span>
                            <strong>{{
                              runnerSelfCheckStatusLabel(item)
                            }}</strong>
                          </div>
                        </div>
                      </div>

                      <el-form-item
                        v-if="isExternalAgentMode"
                        label="外部 Agent"
                      >
                        <el-select
                          v-model="projectChatSettings.external_agent_type"
                          class="full-width"
                          :disabled="!externalAgentOptions.length"
                        >
                          <el-option
                            v-for="item in externalAgentOptions"
                            :key="item.agent_type"
                            :label="item.label || item.agent_type"
                            :value="item.agent_type"
                            :disabled="!item.implemented"
                          />
                        </el-select>
                      </el-form-item>

                      <el-form-item
                        v-if="
                          isExternalAgentMode && nativeDesktopBridgeAvailable
                        "
                        label="本机运行方式"
                      >
                        <div class="workspace-path-editor">
                          <div class="workspace-path-hint">
                            桌面端已接入 Tauri 原生桥，可直接选择本机目录并检测
                            Codex /
                            Hermes；不需要再选择本地连接器。完整交互式执行仍需继续接入本地
                            Runner / PTY。
                          </div>
                        </div>
                      </el-form-item>

                      <el-form-item
                        v-if="
                          isExternalAgentMode && !nativeDesktopBridgeAvailable
                        "
                        label="本地连接器"
                      >
                        <div class="workspace-path-editor">
                          <el-select
                            v-model="projectChatSettings.local_connector_id"
                            class="full-width"
                            filterable
                            clearable
                            placeholder="选择本机连接器"
                          >
                            <el-option
                              v-for="item in localConnectors"
                              :key="item.id"
                              :label="item.connector_name || item.id"
                              :value="item.id"
                            >
                              <span>{{ item.connector_name || item.id }}</span>
                              <el-tag
                                size="small"
                                :type="item.online ? 'success' : 'info'"
                              >
                                {{ item.online ? "在线" : "离线" }}
                              </el-tag>
                            </el-option>
                          </el-select>
                          <div class="workspace-path-actions">
                            <el-button
                              @click="pairBrowserLocalConnector"
                              :loading="localConnectorPairing"
                            >
                              连接本机
                            </el-button>
                            <el-button
                              @click="refreshLocalConnectorCatalog(false)"
                              :loading="localConnectorRefreshing"
                            >
                              刷新
                            </el-button>
                          </div>
                          <div class="workspace-path-hint">
                            {{ localConnectorSummary }}
                            <template v-if="externalAgentInfo.reason">
                              · {{ externalAgentInfo.reason }}
                            </template>
                            <template v-else>
                              · 网页模式需要本地连接器；桌面端不需要此选项。
                            </template>
                          </div>
                        </div>
                      </el-form-item>

                      <el-form-item
                        v-if="isExternalAgentMode"
                        :label="
                          nativeDesktopBridgeAvailable
                            ? '本机工作区'
                            : '本地连接器工作区'
                        "
                      >
                        <div class="workspace-path-editor">
                          <el-input
                            v-model="workspacePathDraft"
                            class="full-width"
                            placeholder="macOS: /Volumes/work_mac_1_5T/self/ai-employee"
                          />
                          <div class="workspace-path-actions">
                            <el-button
                              @click="promptProjectWorkspacePath"
                              :loading="workspacePathPicking"
                            >
                              {{
                                nativeDesktopBridgeAvailable
                                  ? "选择本机目录"
                                  : "连接器选目录"
                              }}
                            </el-button>
                            <el-button
                              type="primary"
                              @click="saveProjectWorkspacePath()"
                              :loading="workspacePathSaving"
                            >
                              保存
                            </el-button>
                            <el-button
                              @click="testProjectWorkspacePath"
                              :loading="workspacePathTesting"
                            >
                              测试
                            </el-button>
                          </div>
                          <div class="workspace-path-hint">
                            <template v-if="workspacePathResolved">
                              当前已保存：{{ workspacePathResolved }}
                            </template>
                            <template v-else>
                              {{
                                nativeDesktopBridgeAvailable
                                  ? "当前还没有配置本机工作区。"
                                  : "当前还没有配置本地连接器工作区。"
                              }}
                            </template>
                            这是执行器所在电脑上的绝对路径。
                          </div>
                        </div>
                      </el-form-item>

                      <div class="settings-execution-section">
                        <span>协作策略</span>
                        <strong
                          >协作策略决定员工如何分工；本机执行环境仍需在上方单独检查。</strong
                        >
                      </div>

                      <el-form-item label="协作模式">
                        <el-select
                          v-model="
                            projectChatSettings.employee_coordination_mode
                          "
                          class="full-width"
                          :disabled="!selectedProjectId"
                        >
                          <el-option label="自动协作" value="auto" />
                          <el-option label="手动模式" value="manual" />
                        </el-select>
                      </el-form-item>

                      <el-form-item label="回答风格">
                        <el-select
                          v-model="projectChatSettings.answer_style"
                          class="full-width"
                        >
                          <el-option label="简洁 (Concise)" value="concise" />
                          <el-option label="平衡 (Balanced)" value="balanced" />
                          <el-option label="详细 (Detailed)" value="detailed" />
                        </el-select>
                      </el-form-item>

                      <el-form-item label="历史消息条数">
                        <el-input-number
                          v-model="projectChatSettings.history_limit"
                          :min="1"
                          :max="50"
                          class="full-width"
                        />
                      </el-form-item>

                      <el-form-item label="按需启用工具">
                        <el-switch
                          v-model="projectChatSettings.auto_use_tools"
                          @change="
                            projectChatSettings.auto_use_tools_explicit = true
                          "
                        />
                      </el-form-item>

                      <el-form-item label="单轮仅回答">
                        <el-switch v-model="singleRoundAnswerOnly" />
                      </el-form-item>

                      <el-form-item
                        v-if="currentModelParameterMode === 'text'"
                        label="先结论后步骤"
                      >
                        <el-switch
                          v-model="projectChatSettings.prefer_conclusion_first"
                        />
                      </el-form-item>

                      <el-form-item
                        v-if="currentModelParameterMode === 'text'"
                        label="温度"
                      >
                        <el-slider
                          v-model="temperature"
                          :min="0"
                          :max="2"
                          :step="0.1"
                          show-input
                          :show-input-controls="false"
                        />
                      </el-form-item>
                    </div>
                  </el-form>
                </section>

                <el-tabs class="settings-tabs">
                  <el-tab-pane label="上下文与提示">
                    <el-form
                      label-position="left"
                      label-width="160px"
                      class="settings-form"
                      size="default"
                    >
                      <section class="settings-parameter-section">
                        <div class="settings-parameter-section__header">
                          <div class="settings-parameter-section__title">
                            项目上下文
                          </div>
                          <p class="settings-parameter-section__desc">
                            <template v-if="showLocalRuntimeSettings">
                              让系统知道真实工作区、入口规则文件以及这一轮的最高优先级提示词。
                            </template>
                            <template v-else>
                              这里只保留当前对话真正需要的项目级上下文，不展示本机开发控制项。
                            </template>
                          </p>
                        </div>
                        <el-form-item
                          v-if="hasSelectedProject && showLocalRuntimeSettings"
                        >
                          <template #label>
                            <span class="label-with-tooltip">
                              项目工作区
                              <el-tooltip
                                content="当前项目在这台电脑上的真实目录。AI 直接执行本机命令、解析相对 AI 入口文件时都会以这里为基准。"
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
                              v-model="projectWorkspaceDraft"
                              class="full-width"
                              placeholder="/Volumes/苹果1_5T/self/ai-employee"
                            />
                            <div class="workspace-path-actions">
                              <el-button
                                @click="promptProjectWorkspaceDirectory"
                                :loading="projectWorkspacePicking"
                              >
                                选择目录
                              </el-button>
                              <el-button
                                type="primary"
                                :loading="projectWorkspaceSaving"
                                @click="saveProjectWorkspaceDirectory()"
                              >
                                保存工作区
                              </el-button>
                            </div>
                            <div class="workspace-path-hint">
                              <template v-if="projectWorkspaceResolved">
                                当前已保存：{{ projectWorkspaceResolved }}
                              </template>
                              <template v-else>
                                当前项目还没有配置工作区路径，AI
                                不能直接在本机执行项目命令。
                              </template>
                              <template v-if="projectWorkspaceDirty">
                                当前输入尚未保存。
                              </template>
                            </div>
                          </div>
                        </el-form-item>

                        <el-form-item
                          v-if="hasSelectedProject && showLocalRuntimeSettings"
                        >
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
                              <template
                                v-if="
                                  projectWorkspaceDraftNormalized ||
                                  projectWorkspacePath
                                "
                              >
                                当前项目工作区：{{
                                  projectWorkspaceDraftNormalized ||
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
                      </section>
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

                  <el-tab-pane label="MCP 与护栏">
                    <el-form
                      label-position="left"
                      label-width="160px"
                      class="settings-form"
                      size="default"
                    >
                      <section class="settings-parameter-section">
                        <div class="settings-parameter-section__header">
                          <div class="settings-parameter-section__title">
                            工具使用策略
                          </div>
                          <p class="settings-parameter-section__desc">
                            默认保持纯对话。只有本轮明确允许时，系统才会按需选择工具或命令参与。
                          </p>
                        </div>
                        <div class="settings-tools-overview">
                          <div class="settings-tools-overview__item">
                            <span class="settings-tools-overview__label"
                              >当前模式</span
                            >
                            <strong class="settings-tools-overview__value">{{
                              singleRoundAnswerOnly
                                ? "仅回答"
                                : projectChatSettings.auto_use_tools
                                  ? "按需工具"
                                  : "纯文本"
                            }}</strong>
                            <span class="settings-tools-overview__meta">
                              {{
                                singleRoundAnswerOnly
                                  ? "只对下一次对话生效"
                                  : projectChatSettings.auto_use_tools
                                    ? "允许系统在必要时选择工具"
                                    : "系统不会主动调工具"
                              }}
                            </span>
                          </div>
                          <div class="settings-tools-overview__item">
                            <span class="settings-tools-overview__label"
                              >项目工具</span
                            >
                            <strong class="settings-tools-overview__value">{{
                              projectToolModules.length
                                ? `${selectedProjectToolNames.length}/${projectToolModules.length}`
                                : "0"
                            }}</strong>
                            <span class="settings-tools-overview__meta">
                              {{
                                projectToolModules.length
                                  ? "当前项目关联工具可按轮次收紧"
                                  : "当前没有项目级工具可选"
                              }}
                            </span>
                          </div>
                          <div class="settings-tools-overview__item">
                            <span class="settings-tools-overview__label"
                              >熔断后策略</span
                            >
                            <strong class="settings-tools-overview__value">{{
                              projectChatSettings.tool_budget_strategy ===
                              "stop"
                                ? "直接停止"
                                : "强制总结"
                            }}</strong>
                            <span class="settings-tools-overview__meta">
                              超过轮次或预算后的默认收口方式
                            </span>
                          </div>
                        </div>
                      </section>

                      <section class="settings-parameter-section">
                        <div class="settings-parameter-section__header">
                          <div class="settings-parameter-section__title">
                            MCP 模块范围
                          </div>
                          <p class="settings-parameter-section__desc">
                            这里控制本轮对话可见的项目工具，不会修改模块定义本身。
                          </p>
                        </div>
                        <el-form-item label="MCP 模块">
                          <div class="mcp-source-switch">
                            <button
                              type="button"
                              class="mcp-source-switch__item"
                              :class="{
                                'is-active': activeMcpSource === 'system',
                              }"
                              @click="activeMcpSource = 'system'"
                            >
                              系统提供 ({{ systemMcpTotal }})
                            </button>
                            <button
                              v-if="hasSelectedProject"
                              type="button"
                              class="mcp-source-switch__item"
                              :class="{
                                'is-active': activeMcpSource === 'external',
                              }"
                              @click="activeMcpSource = 'external'"
                            >
                              外部 ({{ externalMcpTotal }})
                            </button>
                          </div>

                          <div
                            v-show="activeMcpSource === 'system'"
                            class="mcp-source-panel"
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
                          </div>

                          <div
                            v-if="hasSelectedProject"
                            v-show="activeMcpSource === 'external'"
                            class="mcp-source-panel"
                          >
                            <ExternalMcpManager
                              :project-id="selectedProjectId"
                              @changed="handleExternalModulesChanged"
                              @count-change="handleExternalModuleCountChange"
                            />
                          </div>

                          <div v-else class="mcp-section-tip">
                            先选择项目，才能管理当前项目的外部 MCP 模块。
                          </div>
                        </el-form-item>
                      </section>

                      <section class="settings-parameter-section">
                        <div class="settings-parameter-section__header">
                          <div class="settings-parameter-section__title">
                            执行护栏
                          </div>
                          <p class="settings-parameter-section__desc">
                            这些参数只约束 AI 的循环与工具预算。`工具执行超时 =
                            0` 表示不限制。
                          </p>
                        </div>
                        <el-collapse class="settings-constraint-collapse">
                          <el-collapse-item title="高级护栏参数">
                            <div class="settings-constraint-grid">
                              <el-form-item>
                                <template #label>
                                  <span class="label-with-tooltip">
                                    工具执行超时
                                    <el-tooltip
                                      content="单个工具允许执行的最长时间（秒）。填 0 表示不限制。"
                                      placement="top"
                                    >
                                      <el-icon class="label-icon"
                                        ><InfoFilled
                                      /></el-icon>
                                    </el-tooltip>
                                  </span>
                                </template>
                                <div class="settings-field-stack">
                                  <el-input-number
                                    v-model="
                                      projectChatSettings.tool_timeout_sec
                                    "
                                    :min="0"
                                    :max="600"
                                    class="full-width"
                                  />
                                  <div class="settings-inline-helper">
                                    0 = 不限制。适合长时间
                                    MCP、CLI、终端或批处理任务。
                                  </div>
                                </div>
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
                                  v-model="
                                    projectChatSettings.max_tool_calls_per_round
                                  "
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
                                  v-model="
                                    projectChatSettings.tool_budget_strategy
                                  "
                                  class="full-width"
                                >
                                  <el-option
                                    label="强制收敛回答 (Finalize)"
                                    value="finalize"
                                  />
                                  <el-option
                                    label="直接停止 (Stop)"
                                    value="stop"
                                  />
                                </el-select>
                              </el-form-item>
                            </div>
                          </el-collapse-item>
                        </el-collapse>
                      </section>
                    </el-form>
                  </el-tab-pane>
                </el-tabs>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="settings-center-stage__body">
          <router-view />
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
// ============================================================
// ProjectChat.vue — AI 员工工厂项目聊天主页面（路由编排页）
// 职责：路由参数读取、模块级 composable 初始化、跨模块事件编排
// 业务逻辑已迁入 src/modules/project-chat/ 下各 composable/service/mapper
// CSS 通过 15 个 scoped 外部文件加载（src/modules/project-chat/styles/）
// ============================================================
// 基础框架 & UI 库
// ============================================================
import {
  computed,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
  nextTick,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ElementEasyForm } from "element-easy-form";
import "element-easy-form/dist/style.css";
import ExternalMcpManager from "@/components/ExternalMcpManager.vue";
import ProjectEmployeeDraftCreateDialog from "@/components/ProjectEmployeeDraftCreateDialog.vue";
import ProjectMaterialSaveDialog from "@/components/ProjectMaterialSaveDialog.vue";
import UnifiedMcpAccessDialog from "@/components/UnifiedMcpAccessDialog.vue";
import ChatComposer from "@/modules/project-chat/components/composer/ChatComposer.vue";
import ChatMediaParameterPopover from "@/modules/project-chat/components/composer/ChatMediaParameterPopover.vue";
import ChatContextBar from "@/modules/project-chat/components/layout/ChatContextBar.vue";
import ChatMessageList from "@/modules/project-chat/components/messages/ChatMessageList.vue";
import GroupChatDialog from "@/modules/project-chat/components/sessions/GroupChatDialog.vue";
import ProjectConversationSidebar from "@/modules/project-chat/components/sessions/ProjectConversationSidebar.vue";
import ChatTaskTreePanel from "@/modules/project-chat/components/task-tree/ChatTaskTreePanel.vue";
import TerminalApprovalDialog from "@/modules/project-chat/components/terminal/TerminalApprovalDialog.vue";
import CodePreviewDialog from "@/modules/project-chat/components/code-preview/CodePreviewDialog.vue";
import SkillResourceDialog from "@/modules/project-chat/components/skill-resource/SkillResourceDialog.vue";
import { useProjectChatComposer } from "@/modules/project-chat/composables/useProjectChatComposer.js";
import { useProjectChatPendingRequests } from "@/modules/project-chat/composables/useProjectChatPendingRequests.js";
import { useProjectChatNativeAgent } from "@/modules/project-chat/composables/useProjectChatNativeAgent.js";
import { useProjectChatWorkspaceFiles } from "@/modules/project-chat/composables/useProjectChatWorkspaceFiles.js";
import { useProjectChatSettings } from "@/modules/project-chat/composables/useProjectChatSettings.js";
import { useProjectChatTerminal } from "@/modules/project-chat/composables/useProjectChatTerminal.js";
import { useProjectChatTransport } from "@/modules/project-chat/composables/useProjectChatTransport.js";
import api from "@/utils/api.js";
// ============================================================
// 权限、认证、字典、项目
// ============================================================
import { hasPermission, isSuperAdmin } from "@/utils/permissions.js";
import {
  clearAuthSession,
  getStoredAuthProfile,
  getStoredToken,
} from "@/utils/auth-storage.js";
import { fetchDictionary } from "@/utils/dictionaries.js";
import { fetchAllVisibleProjects } from "@/utils/projects.js";
import {
  Delete,
  DocumentCopy,
  CollectionTag,
  EditPen,
  Files,
  RefreshRight,
  InfoFilled,
  CircleCheck,
  List,
} from "@element-plus/icons-vue";
import { extractTextFromFile } from "@/utils/file-extractor.js";
import { buildRuntimeUrl } from "@/utils/runtime-url.js";
import { formatRelativeDateTime } from "@/utils/date.js";
import { openRouteInDesktop } from "@/utils/desktop-app-bridge.js";
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
} from "@/utils/workspace-picker.js";
import {
  classifyNativeRunnerCommand,
  cancelNativeExternalAgentSession,
  detectNativeExecutors,
  getNativeExternalAgentSession,
  getNativeRuntimeInfo,
  hardKillNativeExternalAgentSession,
  hasNativeDesktopBridge,
  listNativeExternalAgentSessions,
  listNativeRunnerPermissionDecisions,
  listNativeWorkspaceFiles,
  prepareNativeExternalAgentLaunch,
  prepareNativeWorkspaceFileWrite,
  previewNativeWorkspaceDiff,
  readNativeWorkspaceFile,
  recordNativeRunnerPermissionDecision,
  runNativeRunnerCommand,
  startNativeExternalAgentSession as startNativeExternalAgentSessionCommand,
  subscribeNativeExternalAgentSessionEvents,
  writeNativeExternalAgentSessionInput,
} from "@/utils/native-desktop-bridge.js";
import {
  buildChatSettingsRoute,
  inferSettingsPanelFromPath,
  isChatSettingsRoutePath,
  resolveSettingsAwarePanelPath,
  stripChatSettingsPrefix,
} from "@/utils/chat-settings-route.js";
import {
  CHAT_BASE_ROUTE_PATH,
  EMPLOYEE_DRAFT_BLOCK_RE,
  HOST_RUN_COMMAND,
  HOST_RUN_COMMAND_ALIASES,
  LARK_CLI_COMMAND,
  LARK_CLI_COMMAND_ALIASES,
  LARK_CLI_SKILL_ROOT_RELATIVE,
  PLUGIN_INSTALL_DRAFT_QUERY_KEY,
  PROJECT_STATS_COMMAND,
  PROJECT_STATS_COMMAND_ALIASES,
  PROJECT_STATS_REPORT_DAYS,
  STATISTICS_ANALYSIS_DRAFT_QUERY_KEY,
} from "@/modules/project-chat/constants/projectChatConstants.js";
import {
  escapeHtml,
  isPreviewableCodeBlock,
  normalizeCodeLanguage,
  renderProjectChatMarkdown,
} from "@/modules/project-chat/services/projectChatMarkdown.js";
import {
  buildCodePreviewTitle,
  buildHtmlPreviewSrcdoc,
  buildVuePreviewSrcdoc,
} from "@/modules/project-chat/services/projectChatCodePreview.js";
import {
  installVettSkillResource,
  searchSkillResourceItems,
} from "@/modules/project-chat/services/projectChatSkillResources.js";
import {
  createProjectMaterial,
} from "@/modules/project-chat/services/projectChatMaterialsApi.js";
import {
  submitAgentRuntimePermissionActionRequest,
  trustAgentRuntimeWorkspaceRequest,
} from "@/modules/project-chat/services/projectChatAgentRuntimeApi.js";
import {
  createEmployeeFromDraft as createEmployeeFromDraftRequest,
  fetchEmployeeDraftCatalog,
  generateEmployeeDraft,
} from "@/modules/project-chat/services/projectChatEmployeeDraftApi.js";
import {
  fetchProjectChatProviders,
  saveProjectChatSettings as saveProjectChatSettingsRequest,
} from "@/modules/project-chat/services/projectChatSettingsApi.js";
import {
  formatAgentRuntimeEventPhase,
  formatAgentRuntimeEventSummary,
  formatAgentRuntimeTranscriptEntry,
} from "@/modules/project-chat/mappers/agentRuntimeMappers.js";
import {
  buildMessageOperation,
  findMessageOperationMatchIndex,
  formatChatPlatformLabel,
  formatChatSessionSourceLabel,
  isGroupChatSession,
  mapHistoryMessage,
  mergeMessageOperations,
  normalizeChatSession,
  normalizeChatSourceContext,
  normalizeOperationActionType,
  normalizeOperationPhase,
  normalizeProcessLogLevel,
  normalizeStringList,
  resolveChatSessionGroupLabel,
} from "@/modules/project-chat/mappers/messageMappers.js";
import {
  attachmentTagType,
  attachmentTypeLabel,
  clipText,
  collectArtifactImageUrls,
  collectArtifactVideoUrls,
  extractAttachments,
  extractImages,
  extractVideos,
  formatFileType,
  isAllowedFileType,
  isImageFile,
  mergeImageUrls,
  mergeVideoUrls,
} from "@/modules/project-chat/mappers/mediaMappers.js";
import {
  buildExternalAgentWarmupKey,
  buildNativeExternalAgentCommandPreview,
  buildNativeRunnerSelfCheckCommands,
  formatDurationMs,
  isLiveNativeExternalAgentStatus,
  isNativeExternalAgentInternalDiagnostic,
  nativeExternalAgentRecordStatusLabel,
  nativeExternalAgentRecordSummary,
  nativeExternalAgentRecordTagType,
  nativeExternalAgentRecordTime,
  nativeExecutorOptionLabel,
  normalizeNativeExternalAgentRuntimeSnapshot,
  normalizeNativeExternalAgentSessionId,
  normalizeNativeRunnerSelfCheckItem,
  runnerPermissionDecisionLabel,
  runnerPermissionRecordSummary,
  runnerPermissionRecordTime,
  runnerSelfCheckStatusLabel,
  runnerSelfCheckTagType,
  shouldShowNativeExternalAgentBlockedReason,
} from "@/modules/project-chat/mappers/nativeAgentMappers.js";
import {
  buildNativeExternalAgentDiagnosticItems,
  buildNativeExternalAgentDiagnosticText,
  buildNativeExternalAgentFileEvidenceItems,
  buildNativeExternalAgentFullLogText,
  buildNativeExternalAgentSessionErrorText,
  buildNativeExternalAgentSessionOutputText,
  buildNativeExternalAgentStdoutText,
  buildNativeExternalAgentVerificationItems,
  calculateNativeExternalAgentLogStats,
  filterNativeExternalAgentSessionPermissionRecords,
  formatNativeExternalAgentTerminalStatusText,
  resolveNativeExternalAgentFinalAnswerText,
  runnerEvidenceMetaText,
} from "@/modules/project-chat/mappers/native-agent/nativeAgentDetailMappers.js";
import {
  normalizeAiEntryFileForSave,
} from "@/modules/project-chat/mappers/workspaceMappers.js";
import {
  chatRuntimeRemoteFingerprint,
  chatRuntimeStorageKey,
  clearPersistedChatRuntime as clearLocalPersistedChatRuntime,
  readPersistedChatRuntime as readLocalPersistedChatRuntime,
  writePersistedChatRuntime as writeLocalPersistedChatRuntime,
} from "@/modules/project-chat/services/projectChatRuntimeStorage.js";
import {
  listProjectWorkspaceFiles,
  readProjectWorkspaceFile,
  saveProjectWorkspaceFile,
} from "@/modules/project-chat/services/projectChatWorkspaceApi.js";
import {
  upsertProjectChatRequirementRecord as upsertProjectChatRequirementRecordRequest,
} from "@/modules/project-chat/services/projectChatRequirementRecord.js";
import {
  clearChatSessionMemory,
  clearSelectedProjectId,
  clearTaskTreeSessionMemory,
  clearWorkSessionMemory,
  consumePluginInstallDraft,
  consumeStatisticsAnalysisDraft,
  hasSeenGuideTour,
  markGuideTourSeen,
  rememberChatSession,
  readPreferredLocalConnectorId,
  readPreferredLocalWorkspacePath,
  readPreferredSkillResourceDirectory,
  readSelectedProjectId,
  resolveCurrentUsername,
  restoreChatSession,
  writePreferredLocalConnectorId,
  writePreferredLocalWorkspacePath,
  writePreferredSkillResourceDirectory,
  writeSelectedProjectId,
} from "@/modules/project-chat/services/projectChatStorage.js";
import {
  buildBackgroundTaskStateOperation,
  buildWaitingBackgroundOperation,
  formatGuardSummary,
  interactionSubmitAckPayload,
  interactionSubmitAckSummary,
  isBackgroundOperationEvent,
  isCompletedOperationEvent,
  isInteractionSubmitAckDone,
  isProjectChatHeartbeatEvent,
  isResumeStartedEvent,
  isTaskStateEvent,
  isTerminalMirrorControlRequest,
  isWaitingOperationEvent,
  normalizeDoneEventExecutionState,
  normalizeProjectChatWsEvent,
} from "@/modules/project-chat/services/projectChatWsProtocol.js";
import { CHAT_SETTINGS_DEFAULTS } from "@/modules/project-chat/constants/chatSettingsDefaults.js";
import {
  isTaskTreeArchivedOrDone,
  resolveTaskTreeEventPayload,
} from "@/modules/project-chat/mappers/taskTreeMappers.js";
import {
  hasAuthorizationPromptText,
  hasLarkAuthBusinessDomainPromptText,
  hasTerminalChoiceControlSignal,
  inferTerminalChoiceType,
  parseTerminalChoiceLine,
  sanitizeTerminalOutputLines,
  stripTerminalControlSequences,
  terminalChoiceDescription,
  TERMINAL_CHOICE_FALLBACK_PROVIDERS,
} from "@/modules/project-chat/mappers/terminalMappers.js";
import { useProjectChatTaskTreeState } from "@/modules/project-chat/composables/useProjectChatTaskTreeState.js";
import { useProjectChatTaskTreeActions } from "@/modules/project-chat/composables/useProjectChatTaskTreeActions.js";
import { HIGH_RISK_RULES } from "@/modules/project-chat/constants/highRiskRules.js";
import {
  CHAT_PARAMETER_SECTION_CONFIG,
  ROLE_LABEL_MAP,
  SETTINGS_CENTER_ITEM_DEFS,
  SETTINGS_CENTER_PANEL_META,
  SETTINGS_GUIDE_REASON_MAP,
} from "@/modules/project-chat/constants/settingsCenterConfig.js";

const CREATE_CHAT_SESSION_QUERY_KEY = "create_chat_session";

const route = useRoute();
const router = useRouter();
const rawLocalRuntimeSettingsFlag = String(
  import.meta.env.VITE_SHOW_LOCAL_RUNTIME_SETTINGS ?? "",
).trim();
const showLocalRuntimeSettingsDefault = import.meta.env.DEV;
const showLocalRuntimeSettings =
  rawLocalRuntimeSettingsFlag === ""
    ? showLocalRuntimeSettingsDefault
    : ["1", "true", "yes", "on"].includes(
        rawLocalRuntimeSettingsFlag.toLowerCase(),
      );
const EMPLOYEE_DRAFT_AUTO_RULE_SOURCE_LABELS = {
  prompts_chat_curated: "系统规则源",
};

// 开放未选择项目时的通用对话模式，复用现有 sendGlobalChatWithoutProject 逻辑。
const ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT = true;
const PROJECT_CREATED_EVENT = "project-created";
function formatRoleLabel(roleId) {
  const normalized = String(roleId || "")
    .trim()
    .toLowerCase();
  if (!normalized) return "当前用户";
  if (ROLE_LABEL_MAP[normalized]) return ROLE_LABEL_MAP[normalized];
  return normalized.replace(/[_-]+/g, " ");
}

function resolveTourTarget(targetRef) {
  const raw = targetRef?.value;
  if (!raw) return document.body;
  return raw.$el || raw;
}

function applyLocalConnectorRuntimeSettings(baseSettings) {
  return normalizeDictionaryBackedChatSettings(
    normalizeProjectChatSettings(
      baseSettings && typeof baseSettings === "object" ? baseSettings : {},
    ),
  );
}

// ============================================================
// 页面级状态（加载、项目、提供方、连接器）
// ============================================================
const loading = ref(false);
const chatLoading = ref(false);
const workspaceTrustSaving = ref(false);
const projectWorkspaceSaving = ref(false);
const autoSaveState = ref("idle");
const autoSaveUpdatedAt = ref("");
const projectSettingsHydrating = ref(false);
const projectSettingsHydratedProjectId = ref("");

const projects = ref([]);
const providers = ref([]);
const localConnectors = ref([]);
const botPlatformConnectors = ref([]);
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
  execution_mode: "local",
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
const DESKTOP_EXTERNAL_AGENT_OPTIONS = [
  {
    agent_type: "codex_cli",
    label: "Codex CLI",
    nativeKey: "codex",
    runtime_model_name: "codex-cli",
  },
  {
    agent_type: "hermes",
    label: "Hermes",
    nativeKey: "hermes",
    runtime_model_name: "hermes",
  },
  {
    agent_type: "claude_code",
    label: "Claude Code",
    nativeKey: "claudeCode",
    runtime_model_name: "claude-code",
  },
];
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
const formJsonArtifactCache = new Map();
const chatSessions = ref([]);
const chatSessionsLoading = ref(false);
const groupChatDialogVisible = ref(false);
const groupChatCreating = ref(false);
const groupChatResolving = ref(false);
const groupChatEditingSessionId = ref("");
const groupChatLiveStatuses = ref({});
const groupChatDraft = ref({
  title: "",
  platform: "feishu",
  connector_id: "",
  external_chat_name: "",
  resolve_identity: "bot",
});
const groupChatPlatformOptions = [
  { label: "飞书", value: "feishu" },
  { label: "微信/企微", value: "wechat" },
  { label: "QQ", value: "qq" },
];
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
const projectWorkspacePicking = ref(false);
const codePreviewVisible = ref(false);
const codePreviewTitle = ref("代码预览");
const codePreviewSrcdoc = ref("");
const codePreviewError = ref("");

const selectedProjectId = ref("");
let selectedProjectConversationLoadingKey = "";
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
const projectWorkspacePath = ref("");
const projectWorkspaceDraft = ref("");
const projectAiEntryFile = ref("");
const aiEntryFileDraft = ref("");
const singleRoundAnswerOnly = ref(false);
const employeeCreateSubmitting = ref(false);
const activeComposerAssist = ref("");
const externalMcpTotal = ref(0);
const agentStatusExpanded = ref(false);
const currentChatSessionId = ref("");
const chatTaskTree = ref(null);
const taskTreePanelVisible = ref(false);
const taskTreeLoading = ref(false);
const taskTreeSaving = ref(false);
const selectedTaskTreeNodeId = ref("");
const taskTreeStatusDraft = ref("pending");
const taskTreeVerificationDraft = ref("");
const taskTreeSummaryDraft = ref("");
const currentWorkSessionId = ref("");
const ongoingTaskRestoreNotice = ref(null);
const creatingChatSession = ref(false);
const deletingChatSessionId = ref("");
const downloadingDesktopArtifactKey = ref("");
const localConnectorRefreshing = ref(false);
const localConnectorPairing = ref(false);
const aiEntryFilePicking = ref(false);
const aiEntryFileSaving = ref(false);
let connectorPollTimer = null;
let terminalApprovalFallbackTimer = null;
let chatRuntimePersistTimer = null;
let chatRuntimeRemotePersistTimer = null;
let externalAgentStatusRefreshTimer = null;
let lastChatRuntimeRemotePersistKey = "";
let lastChatRuntimeRemotePersistFingerprint = "";
let terminalRestoreAttemptKey = "";
let terminalStructuredInteractionRefreshPending = false;
let externalAgentStatusRefreshKey = "";

// ============================================================
// Composable 初始化（pending requests、native agent、workspace、terminal、settings、transport）
// 各模块的状态管理已迁入 src/modules/project-chat/composables/
// ============================================================
const {
  pendingRequests,
  activeGenerationRequestId,
  hasPendingRequestForChatSession,
  getActiveRequestId,
  trackPendingRequest,
  cleanupRequest,
  rejectAndCleanupRequest,
  rejectAndCleanupAllRequests,
} = useProjectChatPendingRequests({
  currentChatSessionId,
});
const {
  projectChatSettings,
  settingsSaving,
} = useProjectChatSettings();
const {
  nativeExternalAgentLaunchingChatSessionIds,
  nativeExternalAgentBackgroundedChatSessionIds,
  nativeExternalAgentPersistedSessions,
  nativeExternalAgentFinalizedSessionIds,
  nativeExternalAgentFastKilledSessionIds,
  nativeExternalAgentCancelledSessionIds,
  nativeExternalAgentDeferredCleanupTimers,
  nativeExternalAgentSession,
  nativeExternalAgentSessionLogs,
  nativeExternalAgentMessageId,
  nativeExternalAgentChatSessionId,
  nativeExternalAgentSessionsById,
  nativeExternalAgentSessionLogsById,
  nativeExternalAgentRunnerSessionByChatSessionId,
  nativeExternalAgentChatSessionByRunnerSessionId,
  nativeExternalAgentMessageByRunnerSessionId,
  setNativeExternalAgentLaunching: markNativeExternalAgentLaunching,
  setNativeExternalAgentBackgrounded: markNativeExternalAgentBackgrounded,
  rememberNativeExternalAgentSessionBinding,
  getNativeExternalAgentRunnerSessionIdForChatSession,
  getNativeExternalAgentChatSessionIdForRunnerSession,
  getNativeExternalAgentMessageIdForRunnerSession,
  clearAgentSessionBinding,
  computeRunningFlag,
  syncSessionPanel,
} = useProjectChatNativeAgent();
const {
  workspaceFileTreeLoading,
  workspaceFileTreePath,
  workspaceFileItems,
  workspaceFileLoading,
  workspaceFileSaving,
  activeWorkspaceFilePath,
  workspaceFileDraft,
  workspaceFileOriginal,
  workspaceDiffLoading,
  workspaceDiffPreview,
  workspacePathDraft,
  workspacePathPicking,
  workspacePathSaving,
  workspacePathTesting,
  workspacePathDraftNormalized,
  resetWorkspaceFilePanel,
} = useProjectChatWorkspaceFiles();
const {
  terminalPanelExpanded,
  terminalPanelLines,
  terminalPanelStatus,
  terminalPanelRef,
  terminalMirrorConnected,
  hostTerminalSessionId,
  hostTerminalWorkspacePath,
  activeTerminalMirrorAssistantIndex,
  terminalApprovalDialogVisible,
  terminalApprovalHandledKey,
  terminalApprovalFallbackPrompt,
  terminalStructuredInteraction,
  terminalStructuredFormModel,
  terminalDismissedStructuredInteractionKeys,
  terminalStructuredSubmissionHint,
  clearExecutionTransportState,
  appendTerminalPanelLineState,
  resetTerminalPanelState,
} = useProjectChatTerminal();
const {
  wsConnected,
  wsClient,
  wsProjectId,
  wsStatusText,
  wsStatusType,
  disconnectWs,
  ensureWsClient,
} = useProjectChatTransport({
  getToken: getStoredToken,
  onMessage: handleSocketMessage,
  onDisconnect: (reason) => {
    terminalMirrorConnected.value = false;
    rejectPendingAgentPrepares(reason || "连接已断开");
  },
  onUnexpectedClose: (reason) => {
    rejectPendingRequests(reason);
    ElMessage.warning(`WebSocket 断开：${reason}`);
  },
});
const chatSessionMessageCache = new Map();
const queuedFollowupMessages = ref([]);
let followupQueueDraining = false;
let activeFollowupAssistantMessageId = "";
const workingStatusStartedAt = ref(0);
const workingStatusNow = ref(Date.now());
const workingStatusStartedAtBySession = new Map();
let workingStatusTimer = null;
let lastNoActiveGenerationWarningAt = 0;
const pendingAgentPrepares = new Map();
const activeApprovalIds = new Set();
const activeReviewIds = new Set();
const externalAgentWarmupLoading = ref(false);
const externalAgentWarmupKey = ref("");
const nativeDesktopBridgeAvailable = ref(hasNativeDesktopBridge());
const nativeExecutorStatus = ref(null);
const nativeExecutorDetecting = ref(false);
const nativeRuntimeInfo = ref(null);
const nativeRunnerSelfChecking = ref(false);
const nativeRunnerSelfCheckResults = ref([]);
const nativeExternalAgentLaunchPlanning = ref(false);
const nativeExternalAgentLaunchPlan = ref(null);
const nativeExternalAgentRunning = ref(false);
let nativeExternalAgentSessionPollTimer = null;
const nativeExternalAgentSessionPollTimers = new Map();
let nativeExternalAgentSessionEventUnlisten = null;
const nativeExternalAgentSessionRecords = ref([]);
const nativeExternalAgentSessionRecordsLoading = ref(false);
const selectedNativeExternalAgentRecordId = ref("");
const nativeExternalAgentSessionDetailVisible = ref(false);
const nativeExternalAgentDetailActiveTab = ref("terminal");
const nativeExternalAgentTerminalRef = ref(null);
const nativeExternalAgentStdinDraft = ref("");
const nativeExternalAgentStdinSending = ref(false);
const nativeExternalAgentInteractionModel = ref({
  decision: "yes",
  choice: "",
  choices: [],
  text: "",
});
const nativeExternalAgentInteractionDismissedKey = ref("");
const nativeExternalAgentInteractionSubmittedKey = ref("");
const nativeRunnerPermissionRecords = ref([]);
const nativeRunnerPermissionRecordsLoading = ref(false);
const operationInteractionFormModels = ref({});
const dismissedOperationInteractionIds = ref(new Set());
const operationInteractionSubmissionHints = ref({});
const terminalActiveCommand = ref("");

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
const conversationSidebarRef = ref(null);
const chatSettingsButtonRef = computed(
  () => conversationSidebarRef.value?.settingsButtonRef || null,
);
const chatContextBarHostRef = ref(null);
const chatGuideButtonRef = computed(
  () => chatContextBarHostRef.value?.guideButtonRef || null,
);
const chatContextBarRef = computed(
  () => chatContextBarHostRef.value?.contextBarRef || null,
);
const chatComposerRef = ref(null);
const settingsSidebarRef = ref(null);
const settingsGuideButtonRef = ref(null);
const settingsContextBarRef = ref(null);
const settingsMainCardRef = ref(null);

const hasSelectedProject = computed(() =>
  Boolean(String(selectedProjectId.value || "").trim()),
);
const mcpDialogProjectId = computed(() => {
  const activeProjectId = String(selectedProjectId.value || "").trim();
  if (activeProjectId) return activeProjectId;
  const routeProjectId = String(routeChatTarget().projectId || "").trim();
  if (routeProjectId) return routeProjectId;
  return readSelectedProjectId();
});
const mcpDialogProjectLabel = computed(() => {
  const projectId = String(mcpDialogProjectId.value || "").trim();
  if (!projectId) return "";
  const matched = (projects.value || []).find(
    (item) => String(item?.id || "").trim() === projectId,
  );
  return String(matched?.name || projectId).trim();
});
const chatSurface = computed(() => {
  return "main-chat";
});
const isLocalRunnerSurface = computed(
  () => chatSurface.value === "local-runner",
);
const chatSurfaceMark = computed(() =>
  isLocalRunnerSurface.value ? "LR" : "AI",
);
const chatSurfaceName = computed(() =>
  isLocalRunnerSurface.value ? "本地运行" : "AI 对话",
);
const chatSurfaceMeta = computed(() =>
  isLocalRunnerSurface.value ? "系统模型 · 本机执行" : "项目会话",
);
const canUseExternalAgent = computed(
  () =>
    hasSelectedProject.value &&
    Boolean(externalAgentInfo.value.implemented) &&
    externalAgentOptions.value.some((item) => item?.implemented),
);
const isChatSettingsDisplayReady = computed(() => {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return true;
  return (
    !projectSettingsHydrating.value &&
    projectSettingsHydratedProjectId.value === projectId
  );
});
const isExternalAgentMode = computed(
  () =>
    isChatSettingsDisplayReady.value &&
    canUseExternalAgent.value &&
    String(projectChatSettings.value.chat_mode || "").trim() ===
      "external_agent",
);
const chatModeLabel = computed(() => {
  if (isLocalRunnerSurface.value) return "本地运行";
  if (!isChatSettingsDisplayReady.value) return "";
  if (isExternalAgentMode.value) return "外部 Agent";
  return "系统对话";
});
const projectWorkspaceResolved = computed(() =>
  String(projectWorkspacePath.value || "").trim(),
);
const projectWorkspaceDraftNormalized = computed(() =>
  String(projectWorkspaceDraft.value || "").trim(),
);
const workspacePathResolved = computed(() =>
  String(externalAgentInfo.value.workspace_path || "").trim(),
);
const agentRuntimeWorkspaceTrustPath = computed(() =>
  String(
    projectWorkspaceResolved.value || workspacePathResolved.value || "",
  ).trim(),
);
const canTrustAgentRuntimeWorkspace = computed(
  () =>
    hasSelectedProject.value && Boolean(agentRuntimeWorkspaceTrustPath.value),
);
const executionWorkspacePath = computed(() =>
  String(
    workspacePathDraftNormalized.value ||
      workspacePathResolved.value ||
      projectWorkspaceResolved.value ||
      "",
  ).trim(),
);

/** 页面包装：标记 chatSession 的 external agent 启动状态 + 同步运行标记和加载态 */
function setNativeExternalAgentLaunching(chatSessionId, launching) {
  markNativeExternalAgentLaunching(chatSessionId, launching);
  syncNativeExternalAgentRunningFlag();
  syncChatLoadingWithCurrentSession();
}

/** 页面包装：标记 chatSession 的 external agent 后台状态 + 同步运行标记和加载态 */
function setNativeExternalAgentBackgrounded(chatSessionId, backgrounded) {
  markNativeExternalAgentBackgrounded(chatSessionId, backgrounded);
  syncNativeExternalAgentRunningFlag();
  syncChatLoadingWithCurrentSession();
}

function clearActiveNativeExternalAgentSessionBinding(
  sessionId = "",
  chatSessionId = "",
) {
  clearAgentSessionBinding(sessionId, chatSessionId);
  syncNativeExternalAgentRunningFlag();
  syncChatLoadingWithCurrentSession();
}

function clearActiveExecutionTransportState(assistantIndex = -1) {
  clearExecutionTransportState(assistantIndex);
  terminalStructuredInteractionRefreshPending = false;
}

/** 同步 nativeExternalAgentRunning 标记：当前 chatSession 是否正在运行 native external agent */
function syncNativeExternalAgentRunningFlag() {
  nativeExternalAgentRunning.value = computeRunningFlag(
    currentChatSessionId.value,
  );
}

/** 同步 native external agent 会话面板：选择当前活跃 session 并回填 session/logs/messageId/chatSessionId */
function syncNativeExternalAgentSessionPanel(preferredSessionId = "") {
  syncSessionPanel(
    currentChatSessionId.value,
    selectedNativeExternalAgentRecordId.value,
    preferredSessionId,
  );
  syncNativeExternalAgentRunningFlag();
}

const nativeExternalAgentSessionOutput = computed(() =>
  buildNativeExternalAgentSessionOutputText(nativeExternalAgentSessionLogs.value),
);
const nativeExternalAgentSessionError = computed(() =>
  buildNativeExternalAgentSessionErrorText(nativeExternalAgentSessionLogs.value),
);
const nativeExternalAgentCommandText = computed(() => {
  return buildNativeExternalAgentCommandPreview(
    nativeExternalAgentSession.value || {},
  );
});
const nativeExternalAgentStdoutText = computed(() =>
  buildNativeExternalAgentStdoutText(nativeExternalAgentSessionLogs.value),
);
const nativeExternalAgentDiagnosticText = computed(() =>
  buildNativeExternalAgentDiagnosticText(nativeExternalAgentSessionLogs.value),
);
const nativeExternalAgentFinalAnswerText = computed(() => {
  return resolveNativeExternalAgentFinalAnswerText(
    nativeExternalAgentSession.value || {},
    nativeExternalAgentSessionLogs.value,
    nativeExternalAgentStdoutText.value,
  );
});
const nativeExternalAgentFileEvidenceItems = computed(() => {
  return buildNativeExternalAgentFileEvidenceItems(
    nativeExternalAgentSession.value || {},
  );
});

const nativeExternalAgentVerificationItems = computed(() => {
  return buildNativeExternalAgentVerificationItems(
    nativeExternalAgentSession.value || {},
    nativeRunnerSelfCheckResults.value || [],
  );
});

const nativeExternalAgentSessionPermissionRecords = computed(() => {
  return filterNativeExternalAgentSessionPermissionRecords(
    nativeExternalAgentSession.value || {},
    nativeRunnerPermissionRecords.value || [],
  );
});

const nativeExternalAgentDiagnosticItems = computed(() => {
  return buildNativeExternalAgentDiagnosticItems(
    nativeExternalAgentSession.value || {},
  );
});
const nativeExternalAgentFullLogText = computed(() =>
  buildNativeExternalAgentFullLogText(nativeExternalAgentSessionLogs.value),
);
const nativeExternalAgentTerminalControls = [
  { key: "ctrl_c", label: "Ctrl+C", content: "\u0003", type: "danger" },
  { key: "enter", label: "回车", content: "\r" },
  { key: "space", label: "空格", content: " " },
  { key: "up", label: "↑", content: "\u001b[A" },
  { key: "down", label: "↓", content: "\u001b[B" },
];
const nativeExternalAgentTerminalStatusText = computed(() => {
  return formatNativeExternalAgentTerminalStatusText(
    nativeExternalAgentSession.value?.status,
    canWriteNativeExternalAgentStdin.value,
  );
});
const nativeExternalAgentTerminalText = computed(() => {
  const rows = nativeExternalAgentSessionLogs.value
    .map((item) => {
      const stream = String(item.stream || "stdout")
        .trim()
        .toLowerCase();
      const content = stripTerminalControlSequences(String(item.content || ""));
      if (!content.trim()) return "";
      if (stream === "final") return "";
      if (isNativeExternalAgentInternalDiagnostic(stream, content)) return "";
      if (stream === "stdin") return `\n${content}`;
      if (stream === "system") return `\n[system] ${content}`;
      if (stream === "stderr") return `\n[stderr] ${content}`;
      return content;
    })
    .filter(Boolean);
  const text = rows.join("");
  const limit = 20000;
  if (text.length <= limit) return text.trim();
  return `[只显示最近输出]\n${text.slice(text.length - limit).trim()}`;
});
const nativeExternalAgentLogStats = computed(() => {
  return calculateNativeExternalAgentLogStats(
    nativeExternalAgentSessionLogs.value,
  );
});
const canWriteNativeExternalAgentStdin = computed(() => {
  const status = String(nativeExternalAgentSession.value?.status || "").trim();
  return (
    Boolean(nativeExternalAgentSession.value?.stdinOpen) &&
    (status === "running" || status === "cancelling")
  );
});
const nativeExternalAgentInteractionPrompt = computed(() => {
  if (!canWriteNativeExternalAgentStdin.value) return null;
  const text = nativeExternalAgentSessionLogs.value
    .slice(-12)
    .map((item) => String(item.content || ""))
    .join("")
    .slice(-2400);
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const pseudoRow = {
    terminalLog: lines.map((line) => ({ content: line })),
  };
  const choiceInteraction = detectTerminalChoiceInteraction(pseudoRow, -1);
  if (choiceInteraction) {
    const key = `${nativeExternalAgentSession.value?.sessionId || ""}:choice:${choiceInteraction.key}`;
    if (nativeExternalAgentInteractionDismissedKey.value === key) return null;
    if (nativeExternalAgentInteractionSubmittedKey.value === key) return null;
    return {
      ...choiceInteraction,
      key,
      kind: "choice",
      title: "Runner 需要选择",
      description: terminalChoiceDescription(choiceInteraction.type),
    };
  }
  const promptLine =
    [...lines]
      .reverse()
      .find((line) =>
        /(\(y\/n\)|\[y\/n\]|yes\/no|y\/N|Y\/n|是否继续|确认继续|继续执行|proceed|continue\?)/i.test(
          line,
        ),
      ) || "";
  if (!promptLine) return null;
  const textInputLine =
    /(?:请输入|输入|enter|input|type).*(?:[:：]|\?)?$/i.test(promptLine) &&
    !/(\(y\/n\)|\[y\/n\]|yes\/no|y\/N|Y\/n)/i.test(promptLine);
  const key = `${nativeExternalAgentSession.value?.sessionId || ""}:${
    textInputLine ? "text" : "confirm"
  }:${promptLine}`;
  if (nativeExternalAgentInteractionDismissedKey.value === key) return null;
  if (nativeExternalAgentInteractionSubmittedKey.value === key) return null;
  if (textInputLine) {
    return {
      key,
      kind: "text",
      title: "Runner 需要输入",
      description: promptLine,
      fieldLabel: promptLine,
    };
  }
  return {
    key,
    kind: "confirm",
    title: "Runner 需要确认",
    description: promptLine,
  };
});
const nativeExternalAgentInteractionFormJson = computed(() => {
  const interaction = nativeExternalAgentInteractionPrompt.value;
  const kind = String(interaction?.kind || "confirm");
  const isMulti = interaction?.type === "checkbox";
  let schema = [];
  if (kind === "choice") {
    schema = [
      {
        label: interaction.fieldLabel || "选择选项",
        prop: isMulti ? "choices" : "choice",
        componentName: isMulti ? "ElCheckboxGroup" : "ElRadioGroup",
        colAttrs: { span: 24 },
        rules: [
          isMulti
            ? {
                required: true,
                type: "array",
                min: 1,
                message: "请至少选择一项",
                trigger: "change",
              }
            : { required: true, message: "请选择一项", trigger: "change" },
        ],
        children: (interaction.options || []).map((item) => ({
          componentName: isMulti ? "ElCheckbox" : "ElRadio",
          attrs: {
            label: item.value,
            value: item.value,
          },
          children: item.label,
        })),
      },
    ];
  } else if (kind === "text") {
    schema = [
      {
        label: interaction.fieldLabel || "输入内容",
        prop: "text",
        componentName: "ElInput",
        colAttrs: { span: 24 },
        attrs: { clearable: true },
        rules: [{ required: true, message: "请输入内容", trigger: "blur" }],
      },
    ];
  } else {
    schema = [
      {
        label: "选择操作",
        prop: "decision",
        componentName: "ElRadioGroup",
        colAttrs: { span: 24 },
        rules: [{ required: true, message: "请选择操作", trigger: "change" }],
        children: [
          {
            componentName: "ElRadio",
            attrs: { label: "yes", value: "yes" },
            children: "继续",
          },
          {
            componentName: "ElRadio",
            attrs: { label: "no", value: "no" },
            children: "取消",
          },
        ],
      },
    ];
  }
  return {
    rowAttrs: { gutter: 12 },
    formAttrs: { "label-position": "top" },
    model: nativeExternalAgentInteractionModel.value,
    schema,
  };
});
const aiEntryFileResolved = computed(() =>
  String(projectAiEntryFile.value || "").trim(),
);
const aiEntryFileDraftNormalized = computed(() =>
  String(aiEntryFileDraft.value || "").trim(),
);
const workspacePathConfigured = computed(
  () => Boolean(executionWorkspacePath.value),
);
const projectWorkspaceDirty = computed(
  () =>
    projectWorkspaceDraftNormalized.value !== projectWorkspaceResolved.value,
);
const canUseHostTerminal = computed(
  () =>
    hasSelectedProject.value &&
    Boolean(executionWorkspacePath.value) &&
    Boolean(String(currentChatSessionId.value || "").trim()),
);
const canUseWorkspaceFiles = computed(
  () => hasSelectedProject.value && Boolean(projectWorkspaceResolved.value),
);
const workspaceFileReadOnly = computed(
  () => nativeDesktopBridgeAvailable.value,
);
const workspaceFileBridgeLabel = computed(() =>
  nativeDesktopBridgeAvailable.value
    ? "桌面端原生只读文件桥：可浏览目录和预览 1MB 内文本文件，写入仍需后续权限流程。"
    : "服务端工作区文件接口：沿用当前项目工作区读写能力。",
);
const canPreviewWorkspaceDiff = computed(
  () =>
    nativeDesktopBridgeAvailable.value &&
    Boolean(projectWorkspaceResolved.value),
);
const workspaceDiffTargetLabel = computed(() =>
  activeWorkspaceFilePath.value
    ? `当前文件：${activeWorkspaceFilePath.value}`
    : "整个工作区",
);
const workspaceDiffStatusLabel = computed(() => {
  if (!canPreviewWorkspaceDiff.value) return "桌面端可用";
  if (workspaceDiffLoading.value) return "读取中";
  const preview = workspaceDiffPreview.value;
  if (!preview) return "未预览";
  if (!preview.available) return "不可用";
  if (!preview.diff && !preview.status && !preview.summary) return "无差异";
  return preview.truncated ? "已截断" : "已生成";
});
const workspaceParentPath = computed(() => {
  const current = String(workspaceFileTreePath.value || "").trim();
  if (!current) return "";
  const parts = current.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
});
const workspaceFileDirty = computed(
  () => workspaceFileDraft.value !== workspaceFileOriginal.value,
);
const externalAgentConnectorRequired = computed(() => {
  if (!isExternalAgentMode.value) return false;
  if (nativeDesktopBridgeAvailable.value) return false;
  return !String(projectChatSettings.value.local_connector_id || "").trim();
});
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
const usingNativeDesktopRuntime = computed(() =>
  Boolean(nativeDesktopBridgeAvailable.value),
);
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
const selectedExternalAgentOption = computed(() => {
  const agentType = String(
    projectChatSettings.value.external_agent_type || "codex_cli",
  ).trim();
  return (
    (externalAgentOptions.value || []).find(
      (item) => String(item?.agent_type || "").trim() === agentType,
    ) || null
  );
});
const externalAgentDisplayLabel = computed(
  () =>
    String(
      selectedExternalAgentOption.value?.label ||
        externalAgentInfo.value.label ||
        "外部 Agent",
    ).trim() || "外部 Agent",
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
      selectedExternalAgentOption.value?.runtime_model_name ||
        externalAgentInfo.value.runtime_model_name ||
        externalAgentInfo.value.agent_type ||
        "external-agent",
    ).trim() || "external-agent",
);
const externalAgentStatusSummary = computed(() => {
  const parts = [
    externalAgentDisplayLabel.value,
    externalAgentRuntimeLabel.value,
    nativeDesktopBridgeAvailable.value ? "桌面端原生桥" : "本地连接器",
    String(externalAgentInfo.value.sandbox_mode || "workspace-write").trim() ||
      "workspace-write",
  ];
  if (
    !nativeDesktopBridgeAvailable.value &&
    externalAgentInfo.value.local_connector_name
  ) {
    parts.push(externalAgentInfo.value.local_connector_name);
  }
  if (externalAgentInfo.value.thread_id) {
    parts.push(`Thread ${shortThreadId.value}`);
  }
  return parts.filter(Boolean).join(" · ");
});
const executionRuntimeTitle = computed(() => {
  if (!hasSelectedProject.value) return "未选择项目";
  if (!isChatSettingsDisplayReady.value) return "项目配置加载中";
  if (!isExternalAgentMode.value) return "系统对话";
  if (
    externalAgentConnectorRequired.value &&
    !usingNativeDesktopRuntime.value
  ) {
    return "外部 Agent 未就绪";
  }
  if (!workspacePathConfigured.value) {
    return nativeDesktopBridgeAvailable.value
      ? "待选择本机工作区"
      : "待配置本地连接器工作区";
  }
  if (workspacePathDirty.value) return "工作区未保存";
  if (externalAgentWarmupLoading.value) return "外部 Agent 预热中";
  if (externalAgentInfo.value.ready) {
    return `${externalAgentDisplayLabel.value} 已就绪`;
  }
  if (nativeDesktopBridgeAvailable.value && nativeRunnerSelfCheckPassed.value) {
    return `${externalAgentDisplayLabel.value} 自检通过`;
  }
  return `${externalAgentDisplayLabel.value} 待检查`;
});
const executionRuntimeDescription = computed(() => {
  if (!hasSelectedProject.value) return "选择项目后才能绑定执行环境。";
  if (!isChatSettingsDisplayReady.value) {
    return "正在读取项目执行方式，加载完成前不会显示系统对话或外部 Agent 状态。";
  }
  if (!isExternalAgentMode.value) {
    return currentModelSummary.value || "使用服务端模型和项目工具回答。";
  }
  if (externalAgentConnectorRequired.value) {
    return "网页模式需要本地连接器；桌面端不需要此选项。";
  }
  if (nativeDesktopBridgeAvailable.value) {
    if (nativeRunnerSelfCheckPassed.value) {
      return "Runner 自检已通过；本机基础命令和工作区检查可用，可继续启动外部 Agent。";
    }
    return "桌面端已接入原生桥，可选择本机目录并检测 Codex / Hermes；完整执行仍需后续接入本地 Runner / PTY。";
  }
  if (!workspacePathConfigured.value) {
    return "这是运行执行器的那台电脑上的绝对路径。";
  }
  if (workspacePathDirty.value) {
    return "保存工作区后才能继续环境检查和执行。";
  }
  const parts = [
    externalAgentRuntimeLabel.value,
    nativeDesktopBridgeAvailable.value
      ? nativeDesktopRuntimeLabel.value
      : localConnectorSummary.value,
    workspacePathResolved.value,
  ].filter(Boolean);
  return parts.join(" · ") || externalAgentStatusSummary.value;
});
const executionRuntimeActionLabel = computed(() => {
  if (!hasSelectedProject.value) return "选择项目";
  if (!isChatSettingsDisplayReady.value) return "加载中";
  if (!isExternalAgentMode.value) return "切换执行方式";
  if (externalAgentConnectorRequired.value) return "连接本机";
  if (!workspacePathConfigured.value || workspacePathDirty.value)
    return "配置工作区";
  return nativeDesktopBridgeAvailable.value ? "检查环境" : "环境设置";
});
const composerExecutionStatusTagType = computed(() => {
  const tone = String(executionRuntimeToneClass.value || "").trim();
  if (tone === "is-danger") return "danger";
  if (tone === "is-warning" || tone === "is-pending") return "warning";
  if (tone === "is-ready") return "success";
  if (tone === "is-running") return "primary";
  return "info";
});
const composerExecutionStatusLabel = computed(() => {
  if (!isChatSettingsDisplayReady.value) return "加载中";
  if (!isExternalAgentMode.value) return "系统对话";
  if (externalAgentUnavailable.value) return "不可用";
  if (externalAgentConnectorRequired.value || !workspacePathConfigured.value) {
    return "未就绪";
  }
  if (workspacePathDirty.value) return "待保存";
  if (externalAgentWarmupLoading.value || nativeExternalAgentRunning.value) {
    return "运行中";
  }
  if (externalAgentInfo.value.ready || nativeRunnerSelfCheckPassed.value) {
    return "已就绪";
  }
  return "待检查";
});
const composerExecutionRuntimeLocation = computed(() => {
  if (!isChatSettingsDisplayReady.value) return "读取配置";
  if (!isExternalAgentMode.value) return "服务端模型";
  if (nativeDesktopBridgeAvailable.value) return "桌面端原生桥";
  if (usingLocalConnector.value) return "本地连接器";
  return "网页模式";
});
const composerExecutionSummaryItems = computed(() => [
  {
    label: "运行位置",
    value: composerExecutionRuntimeLocation.value,
  },
  {
    label: "执行器",
    value: isExternalAgentMode.value
      ? externalAgentDisplayLabel.value
      : currentModelSummary.value || "系统模型",
  },
  {
    label: "工作区",
    value: executionWorkspaceLabel.value,
  },
]);
const composerExecutionDetailAvailable = computed(
  () =>
    Boolean(nativeExternalAgentSession.value?.sessionId) ||
    hasChatTaskTree.value ||
    terminalPanelLineCount.value > 0 ||
    Boolean(terminalApprovalPrompt.value),
);
const nativeRunnerSelfCheckPassed = computed(() => {
  const results = nativeRunnerSelfCheckResults.value || [];
  return (
    results.length > 0 && results.every((item) => item?.tone === "success")
  );
});
const externalAgentUnavailable = computed(() => {
  if (!isChatSettingsDisplayReady.value) return false;
  if (!isExternalAgentMode.value) return false;
  if (externalAgentWarmupLoading.value || externalAgentInfo.value.ready) {
    return false;
  }
  if (nativeDesktopBridgeAvailable.value && nativeRunnerSelfCheckPassed.value) {
    return false;
  }
  if (externalAgentConnectorRequired.value || !workspacePathConfigured.value) {
    return false;
  }
  const commandSource = String(externalAgentInfo.value.command_source || "")
    .trim()
    .toLowerCase();
  return (
    externalAgentInfo.value.implemented === false ||
    (!externalAgentInfo.value.available &&
      !externalAgentInfo.value.installed) ||
    commandSource === "missing" ||
    commandSource === "unavailable" ||
    commandSource === "unsupported" ||
    commandSource === "error"
  );
});
const executionRuntimeToneClass = computed(() => {
  if (!hasSelectedProject.value) return "is-muted";
  if (!isChatSettingsDisplayReady.value) return "is-muted";
  if (!isExternalAgentMode.value) return "is-system";
  if (externalAgentUnavailable.value) return "is-danger";
  if (
    (externalAgentConnectorRequired.value &&
      !usingNativeDesktopRuntime.value) ||
    !workspacePathConfigured.value ||
    workspacePathDirty.value
  ) {
    return "is-warning";
  }
  if (externalAgentWarmupLoading.value) return "is-running";
  if (externalAgentInfo.value.ready) return "is-ready";
  if (nativeDesktopBridgeAvailable.value && nativeRunnerSelfCheckPassed.value) {
    return "is-ready";
  }
  return "is-pending";
});
const composerExecutionChipLabel = computed(() => {
  if (!isChatSettingsDisplayReady.value) return "项目配置加载中";
  if (!isExternalAgentMode.value)
    return `系统对话 · ${currentModelSummary.value}`;
  if (externalAgentInfo.value.ready) {
    return `${externalAgentDisplayLabel.value} · 本机就绪`;
  }
  if (nativeDesktopBridgeAvailable.value && nativeRunnerSelfCheckPassed.value) {
    return `${externalAgentDisplayLabel.value} · 自检通过`;
  }
  if (nativeDesktopBridgeAvailable.value) return "桌面端原生桥已接入";
  if (externalAgentConnectorRequired.value) return "外部 Agent 未就绪";
  if (!workspacePathConfigured.value) return "请选择工作区";
  if (workspacePathDirty.value) return "工作区未保存";
  if (externalAgentWarmupLoading.value) return "环境检查中";
  if (externalAgentUnavailable.value)
    return `${externalAgentDisplayLabel.value} 不可用`;
  return "外部 Agent 待检查";
});
const executionTaskTreeTitle = computed(() =>
  clipText(
    String(
      displayedChatTaskTree.value?.root_goal ||
        displayedChatTaskTree.value?.title ||
        "当前任务",
    ).trim(),
    72,
  ),
);
const executionTaskNodes = computed(() => {
  const nodes = Array.isArray(displayedChatTaskTree.value?.nodes)
    ? displayedChatTaskTree.value.nodes
    : [];
  return nodes
    .filter((node) => String(node?.node_kind || "").trim() !== "goal")
    .slice(0, 8);
});
const executionWorkspaceLabel = computed(() => {
  return executionWorkspacePath.value || "未配置工作区";
});
const executionFileItems = computed(() =>
  (Array.isArray(workspaceFileItems.value)
    ? workspaceFileItems.value
    : []
  ).slice(0, 8),
);
const executionLogItems = computed(() => {
  const items = [];
  const phase = String(agentWorkflowState.value.phase || "idle").trim();
  if (phase !== "idle") {
    items.push({
      key: `workflow-${phase}`,
      tone:
        phase === "failed" || phase === "blocked"
          ? "danger"
          : phase === "waiting_user"
            ? "warning"
            : "info",
      text: [agentWorkflowState.value.title, agentWorkflowState.value.detail]
        .filter(Boolean)
        .join(" · "),
    });
  }
  if (terminalApprovalPrompt.value) {
    items.push({
      key: "terminal-approval",
      tone: "warning",
      text: terminalApprovalPrompt.value.title || "有命令等待确认",
    });
  }
  if (terminalPanelStatus.value !== "idle" || terminalMirrorConnected.value) {
    items.push({
      key: "terminal-status",
      tone: terminalPanelStatus.value === "error" ? "danger" : "info",
      text: `终端：${terminalPanelStatusText.value}`,
    });
  }
  if (!items.length) {
    items.push({
      key: "idle",
      tone: "muted",
      text: "暂无执行日志；开始任务后会同步显示关键事件。",
    });
  }
  return items;
});
const executionVerificationItems = computed(() => {
  const nodes = executionTaskNodes.value;
  const doneCount = nodes.filter(
    (node) => String(node?.status || "") === "done",
  ).length;
  const verifyingCount = nodes.filter(
    (node) => String(node?.status || "") === "verifying",
  ).length;
  return [
    {
      label: hasChatTaskTree.value
        ? `任务节点完成 ${doneCount} / ${nodes.length}`
        : "任务树尚未生成",
      tone: doneCount && doneCount === nodes.length ? "success" : "muted",
    },
    {
      label: verifyingCount
        ? `${verifyingCount} 个节点正在验证`
        : "暂无验证中的节点",
      tone: verifyingCount ? "warning" : "muted",
    },
    {
      label:
        terminalPanelStatus.value === "error"
          ? "终端验证异常"
          : "终端状态可查看",
      tone: terminalPanelStatus.value === "error" ? "danger" : "muted",
    },
  ];
});
const executionPermissionItems = computed(() => [
  {
    label: "执行来源",
    value: isExternalAgentMode.value
      ? nativeDesktopBridgeAvailable.value
        ? "桌面端原生桥"
        : usingLocalConnector.value
          ? "本地连接器"
          : "外部 Agent"
      : "服务端模型",
  },
  {
    label: "权限模式",
    value: String(
      projectChatSettings.value.connector_sandbox_mode ||
        externalAgentInfo.value.sandbox_mode ||
        "workspace-write",
    ).trim(),
  },
  {
    label: "工作区授权",
    value: canTrustAgentRuntimeWorkspace.value ? "可授权" : "未配置",
  },
  {
    label: "命令审批",
    value: terminalApprovalPrompt.value ? "等待确认" : "空闲",
  },
  {
    label: "原生桥",
    value: nativeDesktopRuntimeLabel.value,
  },
]);
const chatHeaderStatusText = computed(() => {
  if (!isChatSettingsDisplayReady.value) return "配置加载中";
  if (!isExternalAgentMode.value) return wsStatusText.value;
  if (externalAgentConnectorRequired.value) return "未选择本地连接器";
  if (nativeDesktopBridgeAvailable.value && !workspacePathConfigured.value)
    return "待选择本机工作区";
  if (!workspacePathConfigured.value) return "未配置工作区";
  if (workspacePathDirty.value) return "工作区未保存";
  if (externalAgentWarmupLoading.value) return "预热中";
  if (externalAgentInfo.value.ready) return "已就绪";
  return "未就绪";
});
const chatHeaderStatusType = computed(() => {
  if (!isChatSettingsDisplayReady.value) return "info";
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
  if (!isChatSettingsDisplayReady.value) {
    return "正在加载项目执行配置";
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
    nativeDesktopBridgeAvailable.value ? "桌面端原生桥" : "本地连接器",
  ];
  if (
    !nativeDesktopBridgeAvailable.value &&
    externalAgentConnectorRequired.value
  ) {
    parts.push("待选择连接器");
  }
  if (
    !nativeDesktopBridgeAvailable.value &&
    externalAgentInfo.value.local_connector_name
  ) {
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
    String(getStoredAuthProfile().role || "user")
      .trim()
      .toLowerCase() || "user",
);
const currentRoleLabel = computed(() => formatRoleLabel(currentRoleId.value));
const {
  displayedChatTaskTree,
  hasChatTaskTree,
  taskTreeIsReadonly,
  taskTreeTreeData,
  taskTreeProgressLabel,
  displayedChatTaskTreeHealth,
  taskTreeSelectedNode,
  taskTreeSelectedNodeChildCount,
  taskTreeVerificationPlaceholder,
  taskTreeSaveHint,
  getTaskTreeChildNodes,
} = useProjectChatTaskTreeState({ chatTaskTree, selectedTaskTreeNodeId });
const {
  applyTaskTreePayload,
  applyWorkSessionPayload,
  clearOngoingTaskRestoreNotice,
  deleteCurrentTaskTree,
  fetchChatTaskTree,
  handleTaskTreeNodeClick,
  openTaskTreePanel,
  restoreOngoingTaskFromServer,
  resumeOngoingTaskFromNotice,
  saveTaskTreeNode,
  setOngoingTaskRestoreNotice,
} = useProjectChatTaskTreeActions({
  chatTaskTree,
  selectedTaskTreeNodeId,
  taskTreeStatusDraft,
  taskTreeVerificationDraft,
  taskTreeSummaryDraft,
  taskTreeLoading,
  taskTreeSaving,
  taskTreePanelVisible,
  currentWorkSessionId,
  ongoingTaskRestoreNotice,
  selectedProjectId,
  currentChatSessionId,
  displayedChatTaskTree,
  taskTreeIsReadonly,
  taskTreeSelectedNode,
  getTaskTreeChildNodes,
  chatLoading,
  fetchChatHistory,
});
const taskTreeStatusOptions = [
  { value: "pending", label: "待开始" },
  { value: "in_progress", label: "进行中" },
  { value: "blocked", label: "阻塞" },
  { value: "verifying", label: "验证中" },
  { value: "done", label: "已完成" },
];

function openTaskTreeDetail(node) {
  const nodeId = String(node?.id || "").trim();
  if (nodeId) {
    selectedTaskTreeNodeId.value = nodeId;
  }
  taskTreePanelVisible.value = true;
}

function nativeExecutorLabel(key) {
  if (!nativeDesktopBridgeAvailable.value) return "待桌面端接入";
  const status = nativeExecutorStatus.value?.[key];
  if (!status) return nativeExecutorDetecting.value ? "检查中" : "未检查";
  if (status.installed) {
    return status.version ? `已安装 ${status.version}` : "已安装";
  }
  return status.reason || "未检测到";
}

const nativeDesktopRuntimeLabel = computed(() => {
  if (!nativeDesktopBridgeAvailable.value) return "网页模式";
  const info = nativeRuntimeInfo.value || {};
  const platform = [info.platform, info.arch].filter(Boolean).join("/");
  const version = info.desktopBridgeVersion
    ? `v${info.desktopBridgeVersion}`
    : "";
  return ["已接入", platform, version].filter(Boolean).join(" · ");
});

const nativeWorkspaceStatusLabel = computed(() => {
  const workspace = nativeExecutorStatus.value?.workspace;
  if (!workspace || !workspace.configured) return "";
  if (workspace.exists && workspace.isDirectory) {
    return `本机工作区可访问：${workspace.path}`;
  }
  if (!workspace.exists) {
    return `本机工作区不存在：${workspace.path}`;
  }
  if (!workspace.isDirectory) {
    return `本机工作区不是目录：${workspace.path}`;
  }
  return workspace.reason || "";
});

function resolveNativeRuntimeWorkspacePath() {
  return executionWorkspacePath.value;
}

function resolveNativeAgentOptionByType(agentType = "") {
  const normalizedType = String(agentType || "codex_cli").trim() || "codex_cli";
  return (
    DESKTOP_EXTERNAL_AGENT_OPTIONS.find(
      (item) => item.agent_type === normalizedType,
    ) || DESKTOP_EXTERNAL_AGENT_OPTIONS[0]
  );
}

function applyNativeExecutorStatusToExternalAgentInfo(executorStatus) {
  const agentType =
    String(projectChatSettings.value.external_agent_type || "").trim() ||
    String(externalAgentInfo.value.agent_type || "codex_cli").trim() ||
    "codex_cli";
  const agentOption = resolveNativeAgentOptionByType(agentType);
  const nativeStatus = executorStatus?.[agentOption.nativeKey] || null;
  const installed = Boolean(nativeStatus?.installed);
  const workspacePath = resolveNativeRuntimeWorkspacePath();
  externalAgentInfo.value = normalizeExternalAgentInfo({
    ...externalAgentInfo.value,
    agent_type: agentOption.agent_type,
    label: nativeExecutorOptionLabel(agentOption.label, nativeStatus),
    command:
      agentOption.agent_type === "hermes"
        ? "hermes"
        : agentOption.agent_type === "claude_code"
          ? "claude"
          : "codex",
    resolved_command: String(nativeStatus?.path || "").trim(),
    command_source: installed ? "native_desktop" : "missing",
    runtime_model_name: agentOption.runtime_model_name,
    available: installed,
    installed,
    implemented: true,
    reason: installed ? "" : String(nativeStatus?.reason || "未检测到").trim(),
    workspace_path: workspacePath,
    workspace_access: {
      configured: Boolean(workspacePath),
      exists: Boolean(executorStatus?.workspace?.exists),
      is_dir: Boolean(executorStatus?.workspace?.isDirectory),
      read_ok: Boolean(
        executorStatus?.workspace?.exists &&
        executorStatus?.workspace?.isDirectory,
      ),
      write_ok: false,
      source: "native_desktop",
      sandbox_mode:
        String(
          projectChatSettings.value.external_agent_sandbox_mode ||
            projectChatSettings.value.connector_sandbox_mode ||
            externalAgentInfo.value.sandbox_mode ||
            "workspace-write",
        ).trim() || "workspace-write",
      reason: String(executorStatus?.workspace?.reason || "").trim(),
    },
  });
}

async function refreshNativeExternalAgentSessionRecords(options = {}) {
  const silent = Boolean(options?.silent);
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) {
    nativeExternalAgentSessionRecords.value = [];
    if (!silent) {
      ElMessage.info(
        "当前是网页模式；桌面端原生桥接入后可读取 Runner 运行记录。",
      );
    }
    return;
  }
  nativeExternalAgentSessionRecordsLoading.value = true;
  try {
    nativeExternalAgentSessionRecords.value =
      await listNativeExternalAgentSessions({ limit: 12 });
  } catch (err) {
    nativeExternalAgentSessionRecords.value = [];
    if (!silent) {
      ElMessage.warning(err?.message || "读取 Runner 运行记录失败");
    }
  } finally {
    nativeExternalAgentSessionRecordsLoading.value = false;
  }
}

async function selectNativeExternalAgentSessionRecord(record) {
  const sessionId = String(record?.sessionId || "").trim();
  if (!sessionId) return;
  selectedNativeExternalAgentRecordId.value = sessionId;
  try {
    const snapshot = await getNativeExternalAgentSession({
      sessionId,
      sinceSeq: 0,
    });
    applyNativeExternalAgentSessionSnapshot(snapshot, { select: true });
    nativeExternalAgentDetailActiveTab.value = "terminal";
    nativeExternalAgentSessionDetailVisible.value = true;
    if (snapshot.status === "running" || snapshot.status === "cancelling") {
      stopNativeExternalAgentSessionPolling(sessionId);
      void pollNativeExternalAgentSession(sessionId);
    }
  } catch (err) {
    ElMessage.warning(err?.message || "读取 Runner 会话详情失败");
  }
}

function resolveNativeExternalAgentSessionIdFromMessage(message) {
  const directContext =
    message?.source_context && typeof message.source_context === "object"
      ? message.source_context
      : message?.sourceContext && typeof message.sourceContext === "object"
        ? message.sourceContext
        : {};
  const directSessionId = String(
    directContext.runner_session_id ||
      directContext.runnerSessionId ||
      directContext.session_id ||
      directContext.sessionId ||
      "",
  ).trim();
  if (directSessionId) return directSessionId;
  for (const operation of rawMessageOperations(message)) {
    const operationId = String(
      operation?.operationId || operation?.id || "",
    ).trim();
    if (operationId.startsWith("native-external-agent:")) {
      return operationId.replace("native-external-agent:", "").trim();
    }
    const meta =
      operation?.meta && typeof operation.meta === "object"
        ? operation.meta
        : {};
    const metaSessionId = String(
      meta.session_id ||
        meta.sessionId ||
        meta.runner_session_id ||
        meta.runnerSessionId ||
        "",
    ).trim();
    if (
      String(meta.source || "").trim() === "tauri_external_agent_runner" &&
      metaSessionId
    ) {
      return metaSessionId;
    }
  }
  return "";
}

async function openNativeExternalAgentSessionDetailFromMessage(message) {
  const sessionId = resolveNativeExternalAgentSessionIdFromMessage(message);
  if (!sessionId) {
    ElMessage.warning("这条消息没有关联 Runner 会话");
    return;
  }
  await selectNativeExternalAgentSessionRecord({ sessionId });
}

async function refreshNativeRunnerPermissionRecords() {
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) {
    nativeRunnerPermissionRecords.value = [];
    return;
  }
  nativeRunnerPermissionRecordsLoading.value = true;
  try {
    nativeRunnerPermissionRecords.value =
      await listNativeRunnerPermissionDecisions({ limit: 6 });
  } catch (err) {
    nativeRunnerPermissionRecords.value = [];
    ElMessage.warning(err?.message || "读取 Runner 审批记录失败");
  } finally {
    nativeRunnerPermissionRecordsLoading.value = false;
  }
}

async function recordDesktopAuditEvent(payload = {}) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return null;
  const taskTree =
    displayedChatTaskTree.value &&
    typeof displayedChatTaskTree.value === "object"
      ? displayedChatTaskTree.value
      : null;
  const selectedNode =
    taskTreeSelectedNode.value && typeof taskTreeSelectedNode.value === "object"
      ? taskTreeSelectedNode.value
      : null;
  const chatSessionId = String(
    currentChatSessionId.value || taskTree?.chat_session_id || "",
  ).trim();
  const taskTreeChatSessionId = String(
    taskTree?.chat_session_id || chatSessionId || "",
  ).trim();
  const body = {
    session_id: String(currentWorkSessionId.value || "").trim(),
    chat_session_id: chatSessionId,
    task_tree_session_id: String(taskTree?.id || "").trim(),
    task_tree_chat_session_id: taskTreeChatSessionId,
    task_node_id: String(payload.task_node_id ?? selectedNode?.id ?? "").trim(),
    task_node_title: String(
      payload.task_node_title ?? selectedNode?.title ?? "",
    ).trim(),
    event_type: String(payload.event_type || "desktop_audit").trim(),
    phase: String(payload.phase || "desktop_runtime").trim(),
    step: String(payload.step || "").trim(),
    status: String(payload.status || "done").trim(),
    goal: String(
      payload.goal || taskTree?.root_goal || taskTree?.title || "",
    ).trim(),
    content: String(payload.content || "").trim(),
    facts: Array.isArray(payload.facts) ? payload.facts : [],
    changed_files: Array.isArray(payload.changed_files)
      ? payload.changed_files
      : [],
    verification: Array.isArray(payload.verification)
      ? payload.verification
      : [],
    risks: Array.isArray(payload.risks) ? payload.risks : [],
    next_steps: Array.isArray(payload.next_steps) ? payload.next_steps : [],
  };
  try {
    const data = await api.post(
      `/projects/${encodeURIComponent(projectId)}/chat/desktop-audit-events`,
      body,
    );
    applyWorkSessionPayload(data?.session, {
      projectId,
      taskTree,
    });
    return data;
  } catch (err) {
    console.warn("record desktop audit event failed", err);
    return null;
  }
}

async function recordNativeTerminalApprovalDecision(choice, prompt) {
  if (!hasNativeDesktopBridge()) return;
  const normalizedChoice = String(choice || "").trim();
  const decision =
    normalizedChoice === "1"
      ? "approve_once"
      : normalizedChoice === "2"
        ? "approve_session"
        : "reject";
  const title = String(prompt?.title || "").trim();
  const message = String(prompt?.message || "").trim();
  const workspacePath = String(
    workspacePathDraftNormalized.value ||
      workspacePathResolved.value ||
      projectWorkspaceResolved.value ||
      "",
  ).trim();
  try {
    await recordNativeRunnerPermissionDecision({
      command: "terminal_approval",
      args: title ? [title] : [],
      workspacePath,
      decision,
      reason: String(prompt?.description || message.split(/\r?\n/)[0] || "")
        .trim()
        .slice(0, 500),
      scope:
        decision === "approve_session" ? "current_session" : "current_request",
      source: "project_chat_terminal_approval",
      riskLevel: "approval_required",
    });
    await refreshNativeRunnerPermissionRecords();
    void recordDesktopAuditEvent({
      event_type: "desktop_runner_permission_decision",
      step: "Runner 权限决定",
      status: decision === "reject" ? "rejected" : "done",
      content: `桌面端记录 Runner 权限决定：${runnerPermissionDecisionLabel({
        decision,
      })}${title ? ` · ${title}` : ""}`,
      facts: [
        `decision=${decision}`,
        workspacePath ? `workspace=${workspacePath}` : "",
        title ? `prompt=${title}` : "",
      ].filter(Boolean),
      risks: decision === "reject" ? ["用户拒绝本次终端执行授权"] : [],
    });
  } catch (err) {
    ElMessage.warning(err?.message || "Runner 审批记录写入失败");
  }
}

async function refreshNativeExecutorStatus(options = {}) {
  const silent = Boolean(options?.silent);
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) {
    nativeExecutorStatus.value = null;
    nativeRuntimeInfo.value = null;
    if (!silent) {
      ElMessage.info(
        "当前是网页模式；桌面端原生桥接入后可直接检测 Codex / Hermes。",
      );
    }
    return;
  }
  nativeExecutorDetecting.value = true;
  try {
    const workspacePath = resolveNativeRuntimeWorkspacePath();
    const [runtimeInfo, executorStatus] = await Promise.all([
      getNativeRuntimeInfo(),
      detectNativeExecutors({ workspacePath }),
    ]);
    nativeRuntimeInfo.value = runtimeInfo;
    nativeExecutorStatus.value = executorStatus;
    applyNativeExecutorStatusToExternalAgentInfo(executorStatus);
    if (!silent) {
      ElMessage.success("本机执行器环境已检查");
    }
  } catch (err) {
    if (!silent) {
      ElMessage.error(err?.message || "检查本机执行器失败");
    }
  } finally {
    nativeExecutorDetecting.value = false;
  }
}

async function runNativeRunnerSelfCheck(options = {}) {
  const silent = Boolean(options?.silent);
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) {
    nativeRunnerSelfCheckResults.value = [];
    if (!silent) {
      ElMessage.info("当前是网页模式；桌面端原生桥接入后可运行 Runner 自检。");
    }
    return;
  }
  nativeRunnerSelfChecking.value = true;
  try {
    const workspacePath = resolveNativeRuntimeWorkspacePath();
    const [runtimeInfo, executorStatus] = await Promise.all([
      getNativeRuntimeInfo(),
      detectNativeExecutors({ workspacePath }),
    ]);
    nativeRuntimeInfo.value = runtimeInfo;
    nativeExecutorStatus.value = executorStatus;
    applyNativeExecutorStatusToExternalAgentInfo(executorStatus);

    const results = [];
    for (const definition of buildNativeRunnerSelfCheckCommands(
      workspacePath,
    )) {
      const payload = {
        command: definition.command,
        args: definition.args,
        workspacePath,
        timeoutMs: 5000,
      };
      const classification = await classifyNativeRunnerCommand(payload);
      const result = classification.allowed
        ? await runNativeRunnerCommand(payload)
        : null;
      results.push(
        normalizeNativeRunnerSelfCheckItem(definition, classification, result),
      );
    }
    nativeRunnerSelfCheckResults.value = results;
    const failed = results.filter((item) => item.tone !== "success");
    if (failed.length) {
      if (!silent) {
        ElMessage.warning("Runner 自检完成，存在需要处理的项目");
      }
      return;
    }
    if (!silent) {
      ElMessage.success("Runner 自检通过");
    }
  } catch (err) {
    if (!silent) {
      ElMessage.error(err?.message || "Runner 自检失败");
    }
  } finally {
    nativeRunnerSelfChecking.value = false;
  }
}

/** 清除 external agent 状态刷新定时器 */
function clearExternalAgentStatusRefreshTimer() {
  if (externalAgentStatusRefreshTimer !== null) {
    window.clearTimeout(externalAgentStatusRefreshTimer);
    externalAgentStatusRefreshTimer = null;
  }
}

/** 构建 external agent 状态刷新的去重 key（基于项目/模式/agent类型/工作区/桥接状态） */
function buildExternalAgentStatusRefreshKey() {
  return JSON.stringify({
    projectId: String(selectedProjectId.value || "").trim(),
    chatMode: String(projectChatSettings.value.chat_mode || "").trim(),
    surface: isLocalRunnerSurface.value ? "local-runner" : "main-chat",
    agentType: String(
      projectChatSettings.value.external_agent_type || "codex_cli",
    ).trim(),
    workspacePath: resolveNativeRuntimeWorkspacePath(),
    nativeBridge: Boolean(nativeDesktopBridgeAvailable.value),
  });
}

/** 静默刷新 external agent 状态：检测桌面桥接可用性 → runner 自检（key 去重） */
async function refreshExternalAgentStatusSilently({ force = false } = {}) {
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) {
    nativeExecutorStatus.value = null;
    nativeRuntimeInfo.value = null;
    externalAgentStatusRefreshKey = "";
    return;
  }
  if (!selectedProjectId.value) return;
  if (!isExternalAgentMode.value && !isLocalRunnerSurface.value) return;
  if (nativeRunnerSelfChecking.value || nativeExecutorDetecting.value) return;
  const refreshKey = buildExternalAgentStatusRefreshKey();
  if (!force && refreshKey && refreshKey === externalAgentStatusRefreshKey) {
    return;
  }
  externalAgentStatusRefreshKey = refreshKey;
  await runNativeRunnerSelfCheck({ silent: true });
}

/** 延迟调度 external agent 状态刷新（默认 250ms），多次调用去重 */
function scheduleExternalAgentStatusRefresh(options = {}) {
  clearExternalAgentStatusRefreshTimer();
  externalAgentStatusRefreshTimer = window.setTimeout(
    () => {
      externalAgentStatusRefreshTimer = null;
      void refreshExternalAgentStatusSilently(options).catch((err) => {
        console.warn("silent external agent status refresh failed", err);
        externalAgentStatusRefreshKey = "";
      });
    },
    Number(options?.delayMs ?? 250),
  );
}

async function prepareNativeExternalAgentLaunchPlan() {
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) {
    nativeExternalAgentLaunchPlan.value = null;
    ElMessage.info("当前是网页模式；桌面端原生桥接入后可生成启动计划。");
    return;
  }
  nativeExternalAgentLaunchPlanning.value = true;
  try {
    const workspacePath = String(
      workspacePathDraftNormalized.value ||
        workspacePathResolved.value ||
        projectWorkspaceResolved.value ||
        "",
    ).trim();
    if (!workspacePath) {
      ElMessage.warning("请先配置本机工作区");
      return;
    }
    const [runtimeInfo, executorStatus, launchPlan] = await Promise.all([
      getNativeRuntimeInfo(),
      detectNativeExecutors({ workspacePath }),
      prepareNativeExternalAgentLaunch({
        agentType: projectChatSettings.value.external_agent_type || "codex_cli",
        workspacePath,
        prompt: "",
      }),
    ]);
    nativeRuntimeInfo.value = runtimeInfo;
    nativeExecutorStatus.value = executorStatus;
    applyNativeExecutorStatusToExternalAgentInfo(executorStatus);
    nativeExternalAgentLaunchPlan.value = launchPlan;
    if (launchPlan.canLaunch) {
      ElMessage.success("外部 Agent 启动计划已生成");
      return;
    }
    ElMessage.warning(launchPlan.blockedReason || "启动计划存在阻塞项");
  } catch (err) {
    nativeExternalAgentLaunchPlan.value = null;
    ElMessage.error(err?.message || "生成启动计划失败");
  } finally {
    nativeExternalAgentLaunchPlanning.value = false;
  }
}

function stopNativeExternalAgentSessionPolling(sessionId = "") {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  if (normalizedSessionId) {
    const timer = nativeExternalAgentSessionPollTimers.get(normalizedSessionId);
    if (timer) {
      window.clearTimeout(timer);
      nativeExternalAgentSessionPollTimers.delete(normalizedSessionId);
    }
    if (
      nativeExternalAgentSessionPollTimer &&
      normalizeNativeExternalAgentSessionId(
        nativeExternalAgentSession.value,
      ) === normalizedSessionId
    ) {
      window.clearTimeout(nativeExternalAgentSessionPollTimer);
      nativeExternalAgentSessionPollTimer = null;
    }
    return;
  }
  nativeExternalAgentSessionPollTimers.forEach((timer) => {
    window.clearTimeout(timer);
  });
  nativeExternalAgentSessionPollTimers.clear();
  if (nativeExternalAgentSessionPollTimer) {
    window.clearTimeout(nativeExternalAgentSessionPollTimer);
    nativeExternalAgentSessionPollTimer = null;
  }
}

function stopNativeExternalAgentSessionEventSubscription() {
  const unlisten = nativeExternalAgentSessionEventUnlisten;
  nativeExternalAgentSessionEventUnlisten = null;
  if (typeof unlisten !== "function") return;
  try {
    const result = unlisten();
    if (result && typeof result.catch === "function") {
      result.catch((err) => {
        console.warn(
          "unsubscribe native external agent session events failed",
          err,
        );
      });
    }
  } catch (err) {
    console.warn(
      "unsubscribe native external agent session events failed",
      err,
    );
  }
}

async function startNativeExternalAgentSessionEventSubscription() {
  if (nativeExternalAgentSessionEventUnlisten) return;
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) return;
  nativeExternalAgentSessionEventUnlisten =
    await subscribeNativeExternalAgentSessionEvents((event) => {
      void handleNativeExternalAgentSessionEvent(event);
    });
}

function getNativeExternalAgentSessionLogs(sessionId = "") {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  if (normalizedSessionId) {
    const logs = nativeExternalAgentSessionLogsById.get(normalizedSessionId);
    return Array.isArray(logs) ? logs : [];
  }
  return Array.isArray(nativeExternalAgentSessionLogs.value)
    ? nativeExternalAgentSessionLogs.value
    : [];
}

/** 将 native external agent 运行态快照应用到组件状态（session/logs/sessionsById 回填） */
function applyNativeExternalAgentSessionSnapshot(snapshot, options = {}) {
  const sessionId = normalizeNativeExternalAgentSessionId(snapshot);
  if (!sessionId) return;
  const chatSessionId = String(
    options.chatSessionId ||
      snapshot.chatSessionId ||
      snapshot.chat_session_id ||
      getNativeExternalAgentChatSessionIdForRunnerSession(sessionId) ||
      "",
  ).trim();
  const messageId = String(
    options.messageId ||
      snapshot.messageId ||
      snapshot.message_id ||
      getNativeExternalAgentMessageIdForRunnerSession(sessionId) ||
      "",
  ).trim();
  rememberNativeExternalAgentSessionBinding({
    sessionId,
    chatSessionId,
    messageId,
  });
  nativeExternalAgentSessionsById.set(sessionId, snapshot);
  const existingLogs = getNativeExternalAgentSessionLogs(sessionId);
  const existingSeqs = new Set(existingLogs.map((item) => item.seq));
  const nextLogs = Array.isArray(snapshot.logs)
    ? snapshot.logs.filter((item) => !existingSeqs.has(item.seq))
    : [];
  if (Array.isArray(snapshot.logs) && !existingLogs.length) {
    nativeExternalAgentSessionLogsById.set(
      sessionId,
      snapshot.logs.slice(-500),
    );
  }
  if (nextLogs.length) {
    nativeExternalAgentSessionLogsById.set(
      sessionId,
      [...existingLogs, ...nextLogs].slice(-500),
    );
  }
  const shouldSyncPanel =
    Boolean(options.select) ||
    sessionId ===
      getNativeExternalAgentRunnerSessionIdForChatSession(
        currentChatSessionId.value,
      ) ||
    sessionId ===
      String(selectedNativeExternalAgentRecordId.value || "").trim();
  if (shouldSyncPanel) {
    syncNativeExternalAgentSessionPanel(sessionId);
  } else {
    syncNativeExternalAgentRunningFlag();
  }
}

function isTerminalNativeExternalAgentSessionStatus(status) {
  return [
    "blocked",
    "completed",
    "failed",
    "cancelled",
    "unavailable",
  ].includes(String(status || "").trim());
}

function shouldApplyNativeExternalAgentSessionEvent(event) {
  const eventSessionId = String(event?.sessionId || "").trim();
  if (!eventSessionId) return false;
  return true;
}

/** 终结 native external agent 会话：finalized 集合去重、标记持久化、清理启动/后台标记、触发任务恢复 */
function finalizeNativeExternalAgentSessionOnce(snapshot, chatSessionId = "") {
  const sessionId = String(snapshot?.sessionId || "").trim();
  if (!sessionId) {
    finalizeNativeExternalAgentMessage(snapshot, chatSessionId);
    return true;
  }
  const status = String(snapshot?.status || "").trim();
  if (
    (nativeExternalAgentFastKilledSessionIds.has(sessionId) ||
      nativeExternalAgentCancelledSessionIds.has(sessionId)) &&
    status !== "cancelled"
  ) {
    return false;
  }
  if (nativeExternalAgentFinalizedSessionIds.has(sessionId)) return false;
  if (!findNativeExternalAgentMessage(sessionId)) return false;
  nativeExternalAgentFinalizedSessionIds.add(sessionId);
  finalizeNativeExternalAgentMessage(snapshot, chatSessionId);
  return true;
}

async function handleNativeExternalAgentSessionEvent(event) {
  const snapshot = event?.snapshot;
  if (
    !snapshot?.sessionId ||
    !shouldApplyNativeExternalAgentSessionEvent(event)
  ) {
    return;
  }
  const status = String(snapshot.status || "").trim();
  if (
    nativeExternalAgentFastKilledSessionIds.has(
      String(snapshot.sessionId).trim(),
    ) ||
    nativeExternalAgentCancelledSessionIds.has(
      String(snapshot.sessionId).trim(),
    )
  ) {
    const cancelledSnapshot = buildFastKilledNativeExternalAgentSnapshot(
      snapshot.sessionId,
    );
    applyNativeExternalAgentSessionSnapshot(cancelledSnapshot);
    markNativeExternalAgentOperationCancelledFast(snapshot.sessionId);
    stopNativeExternalAgentSessionPolling(snapshot.sessionId);
    syncChatLoadingWithCurrentSession();
    scheduleNativeExternalAgentDeferredCleanup(
      snapshot.sessionId,
      getNativeExternalAgentChatSessionIdForRunnerSession(snapshot.sessionId),
      cancelledSnapshot,
    );
    return;
  }
  applyNativeExternalAgentSessionSnapshot(snapshot);
  upsertNativeExternalAgentMessageOperation(snapshot);
  if (!isTerminalNativeExternalAgentSessionStatus(status)) {
    syncChatLoadingWithCurrentSession();
    schedulePersistChatRuntime();
    return;
  }
  stopNativeExternalAgentSessionPolling(snapshot.sessionId);
  releaseNativeExternalAgentTurnIfTerminal(
    snapshot.sessionId,
    getNativeExternalAgentChatSessionIdForRunnerSession(snapshot.sessionId),
    snapshot,
  );
  syncChatLoadingWithCurrentSession();
  finalizeNativeExternalAgentSessionOnce(
    snapshot,
    getNativeExternalAgentChatSessionIdForRunnerSession(snapshot.sessionId),
  );
  schedulePersistChatRuntime();
  await Promise.allSettled([
    refreshNativeRunnerPermissionRecords(),
    refreshNativeExternalAgentSessionRecords({ silent: true }),
  ]);
}

function buildNativeExternalAgentLogPreview(limit = 12000, sessionId = "") {
  const text = getNativeExternalAgentSessionLogs(sessionId)
    .map((item) => {
      const stream = String(item.stream || "stdout").trim();
      const content = String(item.content || "");
      if (stream === "final") return "";
      if (isNativeExternalAgentInternalDiagnostic(stream, content)) return "";
      const prefix =
        stream === "stderr"
          ? "[stderr] "
          : stream === "system"
            ? "[system] "
            : "";
      return `${prefix}${content}`;
    })
    .join("");
  if (text.length <= limit) return text;
  return `${text.slice(text.length - limit)}\n[output truncated]`;
}

function buildNativeExternalAgentDiagnosticPreview(
  limit = 4000,
  sessionId = "",
) {
  const text = getNativeExternalAgentSessionLogs(sessionId)
    .filter((item) => {
      const stream = String(item.stream || "").trim();
      return stream !== "final";
    })
    .map((item) => {
      const stream = String(item.stream || "stdout").trim();
      const content = String(item.content || "");
      if (!content.trim()) return "";
      const prefix =
        stream === "stderr"
          ? "[stderr] "
          : stream === "system"
            ? "[system] "
            : "";
      return `${prefix}${content}`;
    })
    .join("");
  if (text.length <= limit) return text;
  return `${text.slice(text.length - limit)}\n[diagnostic output truncated]`;
}

/** 解析 native external agent 最终输出：提取 session 日志最后 N 行作为对话展示 */
function resolveNativeExternalAgentFinalOutput(snapshot) {
  const explicit = String(snapshot?.finalOutput || "").trim();
  if (explicit) return explicit;
  const finalLog = [
    ...getNativeExternalAgentSessionLogs(snapshot?.sessionId || ""),
  ]
    .reverse()
    .find((item) => String(item.stream || "").trim() === "final");
  if (finalLog?.content && String(finalLog.content).trim()) {
    return String(finalLog.content).trim();
  }
  return "";
}

function selectedExternalAgentEmployeeLabels() {
  const ids = normalizeStringList(selectedEmployeeIds.value || [], 20);
  if (!ids.length) return [];
  return ids.map((id) => {
    const matched = (projectEmployees.value || []).find(
      (item) => String(item?.id || "").trim() === id,
    );
    const name = String(matched?.name || "").trim();
    return name && name !== id ? `${name}(${id})` : id;
  });
}

function buildNativeExternalAgentTaskPrompt({
  userPrompt = "",
  chatSessionId = "",
  workspacePath = "",
  agentLabel = "",
  attachmentNames = [],
  slashCommandKind = "",
} = {}) {
  const normalizedUserPrompt = String(userPrompt || "").trim();
  const historyRows = toHistoryRows(messages.value, 8)
    .filter((item) => item.content !== normalizedUserPrompt)
    .slice(-6);
  const historyText = historyRows.length
    ? historyRows
        .map((item, index) => {
          const role = item.role === "user" ? "用户" : "助手";
          return `${index + 1}. ${role}: ${clipText(item.content, 700)}`;
        })
        .join("\n")
    : "无";
  const employeeText =
    selectedExternalAgentEmployeeLabels().join("、") || "自动分配";
  const projectId = String(selectedProjectId.value || "").trim();
  const activeChatSessionId = String(
    chatSessionId || currentChatSessionId.value || "",
  ).trim();
  const normalizedAttachmentNames = normalizeStringList(attachmentNames, 20);
  const normalizedSlashCommandKind = String(slashCommandKind || "").trim();
  return [
    "你正在 AI 员工工厂桌面端中作为外部 Agent Runner 执行当前用户请求。",
    "",
    "执行上下文：",
    `- 项目：${currentProjectLabel.value || projectId || "未选择项目"}`,
    `- project_id：${projectId || "unknown"}`,
    `- chat_session_id：${activeChatSessionId || "unknown"}`,
    `- 本机工作区：${workspacePath || "未配置"}`,
    `- 外部 Agent：${agentLabel || externalAgentDisplayLabel.value || "External Agent"}`,
    `- 选中员工：${employeeText}`,
    `- slash command：${normalizedSlashCommandKind || "无"}`,
    `- 附件：${normalizedAttachmentNames.join("、") || "无"}`,
    "",
    "最近对话摘要：",
    historyText,
    "",
    "用户本次任务：",
    normalizedUserPrompt,
    "",
    "执行要求：",
    "1. 直接处理“用户本次任务”，不要只回复等待用户继续说明。",
    "2. 如果需要修改代码或文件，先基于工作区检查现状，再按最小必要范围改动并验证。",
    "3. 如果当前信息不足或工具能力受限，明确说明缺什么、已确认什么、下一步需要用户提供什么。",
    "4. 最终回答只输出给用户看的结论、关键改动、验证结果和剩余风险；不要输出 tokens、rollout、内部诊断或原始执行日志。",
  ].join("\n");
}

function nativeExternalAgentRowsForSession(sessionId = "", chatSessionId = "") {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  const normalizedChatSessionId = String(
    chatSessionId ||
      getNativeExternalAgentChatSessionIdForRunnerSession(
        normalizedSessionId,
      ) ||
      nativeExternalAgentChatSessionId.value ||
      currentChatSessionId.value ||
      "",
  ).trim();
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId || !normalizedChatSessionId) return messages.value;
  if (isCurrentChatSession(projectId, normalizedChatSessionId))
    return messages.value;
  const rememberedRows = getRememberedChatSessionMessages(
    projectId,
    normalizedChatSessionId,
  );
  return Array.isArray(rememberedRows) ? rememberedRows : [];
}

function persistNativeExternalAgentRowsForSession(chatSessionId = "") {
  const projectId = String(selectedProjectId.value || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!projectId || !normalizedChatSessionId) {
    schedulePersistChatRuntime();
    return;
  }
  if (isCurrentChatSession(projectId, normalizedChatSessionId)) {
    persistCurrentChatRuntimeNow(projectId, normalizedChatSessionId);
    return;
  }
  const rows = getRememberedChatSessionMessages(
    projectId,
    normalizedChatSessionId,
  );
  if (!Array.isArray(rows)) return;
  const payload = {
    ...buildRuntimePayloadForRows(rows),
    native_external_agent:
      buildNativeExternalAgentRuntimeSnapshotForChatSession(
        normalizedChatSessionId,
      ),
    native_external_agents:
      listNativeExternalAgentRuntimeSnapshotsForCurrentProject(),
  };
  writePersistedChatRuntime(projectId, normalizedChatSessionId, payload);
  void persistChatRuntimeToServer(projectId, normalizedChatSessionId, payload);
}

function findNativeExternalAgentMessage(sessionId = "") {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  const messageId = String(
    (normalizedSessionId
      ? getNativeExternalAgentMessageIdForRunnerSession(normalizedSessionId)
      : "") ||
      nativeExternalAgentMessageId.value ||
      "",
  ).trim();
  if (!messageId) return null;
  const rows = nativeExternalAgentRowsForSession(normalizedSessionId);
  return rows.find((item) => String(item?.id || "").trim() === messageId);
}

function applyNativeExternalAgentCancellingMessage(snapshot = null) {
  const row = findNativeExternalAgentMessage(snapshot?.sessionId || "");
  if (!row) return;
  row.content = "正在取消外部 Agent Runner 会话。";
  row.displayMode = "";
  row.time = nowText();
  if (snapshot?.sessionId) {
    upsertNativeExternalAgentMessageOperation(snapshot);
  }
  persistNativeExternalAgentRowsForSession(
    getNativeExternalAgentChatSessionIdForRunnerSession(
      snapshot?.sessionId || "",
    ),
  );
}

function upsertNativeExternalAgentMessageOperation(snapshot) {
  const row = findNativeExternalAgentMessage(snapshot?.sessionId || "");
  if (!row || !snapshot?.sessionId) return;
  const status = String(snapshot.status || "").trim();
  const operationPhase =
    status === "running"
      ? "running"
      : status === "completed" ||
          status === "cancelled" ||
          status === "cancelling"
        ? "completed"
        : "failed";
  upsertMessageOperation(row, {
    operationId: `native-external-agent:${snapshot.sessionId}`,
    kind: "request",
    title: `${snapshot.label || "外部 Agent"} 执行`,
    summary:
      status === "running"
        ? "正在处理"
        : status === "cancelling"
          ? "正在取消"
          : status === "completed"
            ? "已完成"
            : status === "cancelled"
              ? "已取消"
              : "已结束",
    detail: buildNativeExternalAgentLogPreview(6000, snapshot.sessionId),
    phase: operationPhase,
    actionType: "none",
    meta: {
      session_id: snapshot.sessionId,
      source: "tauri_external_agent_runner",
      hide_in_message_process: "true",
      runner_status: status,
      agent_type: snapshot.agentType,
      command: buildNativeExternalAgentCommandPreview(snapshot),
      cwd: snapshot.workspacePath,
      exit_code: snapshot.exitCode,
      output_preview: buildNativeExternalAgentLogPreview(
        4000,
        snapshot.sessionId,
      ),
      error: snapshot.blockedReason || "",
    },
  });
}

function isNativeExternalAgentOperation(operation, sessionId = "") {
  const normalizedSessionId = String(sessionId || "").trim();
  const operationId = String(
    operation?.operationId || operation?.id || "",
  ).trim();
  if (
    operationId.startsWith("native-external-agent:") &&
    (!normalizedSessionId ||
      operationId.replace("native-external-agent:", "").trim() ===
        normalizedSessionId)
  ) {
    return true;
  }
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  if (String(meta.source || "").trim() !== "tauri_external_agent_runner") {
    return false;
  }
  const operationSessionId = String(
    meta.session_id ||
      meta.sessionId ||
      meta.runner_session_id ||
      meta.runnerSessionId ||
      "",
  ).trim();
  return (
    !normalizedSessionId ||
    !operationSessionId ||
    operationSessionId === normalizedSessionId
  );
}

function completeNativeExternalAgentRunningOperations(
  sessionId,
  summary = "外部 Agent Runner 会话已结束",
) {
  const normalizedSessionId = String(sessionId || "").trim();
  const chatSessionId =
    getNativeExternalAgentChatSessionIdForRunnerSession(normalizedSessionId);
  const rows = nativeExternalAgentRowsForSession(
    normalizedSessionId,
    chatSessionId,
  );
  let changed = false;
  rows.forEach((row) => {
    if (!row || !Array.isArray(row.operations)) return;
    row.operations = row.operations.map((operation) => {
      if (!isNativeExternalAgentOperation(operation, normalizedSessionId)) {
        return operation;
      }
      const phase = normalizeOperationPhase(
        operation?.phase || operation?.status,
      );
      if (!["running", "pending"].includes(phase)) return operation;
      changed = true;
      const meta =
        operation?.meta && typeof operation.meta === "object"
          ? operation.meta
          : {};
      return {
        ...operation,
        phase: "completed",
        actionType: "none",
        summary: String(operation?.summary || summary).trim() || summary,
        updatedAt: nowText(),
        meta: {
          ...meta,
          runner_status: String(meta.runner_status || "completed").trim(),
          hide_in_message_process: "true",
        },
      };
    });
  });
  if (changed) {
    persistNativeExternalAgentRowsForSession(chatSessionId);
  }
  return changed;
}

function markNativeExternalAgentOperationCancelledFast(
  sessionId,
  summary = "外部 Agent Runner 会话已取消",
) {
  const normalizedSessionId = String(sessionId || "").trim();
  const chatSessionId =
    getNativeExternalAgentChatSessionIdForRunnerSession(normalizedSessionId);
  const rows = nativeExternalAgentRowsForSession(
    normalizedSessionId,
    chatSessionId,
  );
  rows.forEach((row) => {
    if (!row || !Array.isArray(row.operations)) return;
    row.operations = row.operations.map((operation) => {
      if (!isNativeExternalAgentOperation(operation, normalizedSessionId)) {
        return operation;
      }
      const meta =
        operation?.meta && typeof operation.meta === "object"
          ? operation.meta
          : {};
      return {
        ...operation,
        phase: "completed",
        actionType: "none",
        summary,
        updatedAt: nowText(),
        meta: {
          ...meta,
          runner_status: "cancelled",
          hide_in_message_process: "true",
        },
      };
    });
  });
}

function buildFastKilledNativeExternalAgentSnapshot(sessionId = "") {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  const existing =
    nativeExternalAgentSessionsById.get(normalizedSessionId) ||
    nativeExternalAgentSession.value ||
    {};
  const label = String(existing.label || "外部 Agent").trim();
  return {
    ...existing,
    sessionId: normalizedSessionId,
    status: "cancelled",
    exitCode: -15,
    logs: [],
    summary: `${label} Runner 会话已取消`,
    updatedAtEpochMs: Date.now(),
  };
}

function buildUnavailableNativeExternalAgentSnapshot(
  sessionId = "",
  reason = "",
) {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  const existing =
    nativeExternalAgentSessionsById.get(normalizedSessionId) ||
    nativeExternalAgentSession.value ||
    {};
  const label = String(existing.label || "外部 Agent").trim();
  const blockedReason = String(reason || "Runner 会话状态不可确认").trim();
  return {
    ...existing,
    sessionId: normalizedSessionId,
    status: "unavailable",
    blockedReason,
    summary: `${label} Runner 会话状态不可确认`,
    updatedAtEpochMs: Date.now(),
  };
}

function scheduleNativeExternalAgentDeferredCleanup(
  sessionId = "",
  chatSessionId = "",
  snapshot = null,
) {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  if (!normalizedSessionId) return;
  const existingTimer =
    nativeExternalAgentDeferredCleanupTimers.get(normalizedSessionId);
  if (existingTimer) {
    window.clearTimeout(existingTimer);
  }
  const timer = window.setTimeout(() => {
    nativeExternalAgentDeferredCleanupTimers.delete(normalizedSessionId);
    const latestSnapshot =
      snapshot ||
      nativeExternalAgentSessionsById.get(normalizedSessionId) ||
      buildFastKilledNativeExternalAgentSnapshot(normalizedSessionId);
    finalizeNativeExternalAgentSessionOnce(
      latestSnapshot,
      chatSessionId ||
        getNativeExternalAgentChatSessionIdForRunnerSession(
          normalizedSessionId,
        ),
    );
    clearActiveNativeExternalAgentSessionBinding(
      normalizedSessionId,
      chatSessionId ||
        getNativeExternalAgentChatSessionIdForRunnerSession(
          normalizedSessionId,
        ),
    );
    schedulePersistChatRuntime();
    void Promise.allSettled([
      refreshNativeRunnerPermissionRecords(),
      refreshNativeExternalAgentSessionRecords({ silent: true }),
    ]);
  }, 650);
  nativeExternalAgentDeferredCleanupTimers.set(normalizedSessionId, timer);
}

function releaseNativeExternalAgentTurnIfTerminal(
  sessionId = "",
  chatSessionId = "",
  snapshot = null,
) {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(
    sessionId || snapshot,
  );
  const normalizedChatSessionId = String(
    chatSessionId ||
      snapshot?.chatSessionId ||
      snapshot?.chat_session_id ||
      getNativeExternalAgentChatSessionIdForRunnerSession(
        normalizedSessionId,
      ) ||
      currentChatSessionId.value ||
      "",
  ).trim();
  if (normalizedChatSessionId) {
    setNativeExternalAgentLaunching(normalizedChatSessionId, false);
  }
  syncNativeExternalAgentRunningFlag();
  syncChatLoadingWithCurrentSession();
}

function applyNativeExternalAgentFastKilledSession(
  sessionId = "",
  chatSessionId = "",
) {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  if (!normalizedSessionId) return null;
  const normalizedChatSessionId = String(
    chatSessionId ||
      getNativeExternalAgentChatSessionIdForRunnerSession(
        normalizedSessionId,
      ) ||
      currentChatSessionId.value ||
      "",
  ).trim();
  nativeExternalAgentFastKilledSessionIds.add(normalizedSessionId);
  nativeExternalAgentCancelledSessionIds.add(normalizedSessionId);
  stopNativeExternalAgentSessionPolling(normalizedSessionId);
  if (normalizedChatSessionId) {
    const nextLaunching = new Set(
      nativeExternalAgentLaunchingChatSessionIds.value,
    );
    nextLaunching.delete(normalizedChatSessionId);
    nativeExternalAgentLaunchingChatSessionIds.value = nextLaunching;
    const nextBackgrounded = new Set(
      nativeExternalAgentBackgroundedChatSessionIds.value,
    );
    nextBackgrounded.delete(normalizedChatSessionId);
    nativeExternalAgentBackgroundedChatSessionIds.value = nextBackgrounded;
  }
  const snapshot =
    buildFastKilledNativeExternalAgentSnapshot(normalizedSessionId);
  applyNativeExternalAgentSessionSnapshot(snapshot, {
    chatSessionId: normalizedChatSessionId,
    select: true,
  });
  markNativeExternalAgentOperationCancelledFast(
    normalizedSessionId,
    "外部 Agent Runner 会话已取消",
  );
  const row = findNativeExternalAgentMessage(normalizedSessionId);
  if (row) {
    row.displayMode = "";
    row.content =
      String(row.content || "").trim() || "本次外部 Agent 执行已取消。";
    row.time = nowText();
    completeFinishedMessageOperations(row, "外部 Agent Runner 会话已取消");
    closeOpenAgentRuntimeOperationsForCompletedTurn(
      row,
      "外部 Agent Runner 会话已取消",
    );
  }
  const rowIndex = row ? messages.value.findIndex((item) => item === row) : -1;
  clearActiveExecutionTransportState(rowIndex);
  clearActiveNativeExternalAgentSessionBinding(
    normalizedSessionId,
    normalizedChatSessionId,
  );
  syncChatLoadingWithCurrentSession();
  schedulePersistChatRuntime();
  window.setTimeout(() => {
    scheduleNativeExternalAgentDeferredCleanup(
      normalizedSessionId,
      normalizedChatSessionId,
      snapshot,
    );
  }, 0);
  return snapshot;
}

function appendNativeExternalAgentMessages(
  prompt,
  snapshot,
  chatSessionId = "",
  taskPrompt = "",
  runContext = {},
) {
  const projectId = String(selectedProjectId.value || "").trim();
  const normalizedChatSessionId = String(
    chatSessionId || currentChatSessionId.value || "",
  ).trim();
  const userMessage = {
    id: createLocalMessageId(),
    role: "user",
    content: prompt,
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
    displayMode: "external-agent-waiting",
    effectiveTools: [],
    effectiveToolTotal: 0,
    terminalLog: [],
    processExpanded: false,
    audit: null,
    taskTreeAudit: null,
    statusNotes: [],
    operations: [],
    time: nowText(),
  };
  rememberNativeExternalAgentSessionBinding({
    sessionId: snapshot?.sessionId,
    chatSessionId: normalizedChatSessionId,
    messageId: assistantMessage.id,
  });
  if (isCurrentChatSession(projectId, normalizedChatSessionId)) {
    nativeExternalAgentMessageId.value = assistantMessage.id;
    nativeExternalAgentChatSessionId.value = normalizedChatSessionId;
  }
  const targetRows = isCurrentChatSession(projectId, normalizedChatSessionId)
    ? messages.value
    : getRememberedChatSessionMessages(projectId, normalizedChatSessionId) ||
      [];
  targetRows.push(userMessage);
  targetRows.push(assistantMessage);
  if (!isCurrentChatSession(projectId, normalizedChatSessionId)) {
    rememberChatSessionMessages(projectId, normalizedChatSessionId, targetRows);
  }
  upsertNativeExternalAgentMessageOperation(snapshot);
  persistNativeExternalAgentRowsForSession(normalizedChatSessionId);
  void upsertProjectChatRequirementRecord({
    chatSessionId: normalizedChatSessionId,
    status: "in_progress",
    rootGoal: prompt,
    messageId: userMessage.id,
    assistantMessageId: assistantMessage.id,
    runnerSessionId: snapshot?.sessionId,
    runnerAgentType: snapshot?.agentType,
    source: "tauri_external_agent_runner",
    sourceContext: {
      runner_status: String(snapshot?.status || "").trim(),
      runner_label: String(snapshot?.label || "").trim(),
      workspace_path: String(snapshot?.workspacePath || "").trim(),
      task_prompt_preview: clipText(taskPrompt, 1200),
      slash_command: String(runContext?.slashCommandKind || "").trim(),
      attachment_names: normalizeStringList(
        runContext?.attachmentNames || [],
        20,
      ),
      command: buildNativeExternalAgentCommandPreview(snapshot),
    },
  });
  if (isCurrentChatSession(projectId, normalizedChatSessionId)) {
    scrollToBottom();
  }
}

function finalizeNativeExternalAgentMessage(snapshot, chatSessionId = "") {
  const sessionId = normalizeNativeExternalAgentSessionId(snapshot);
  const normalizedChatSessionId = String(
    chatSessionId ||
      getNativeExternalAgentChatSessionIdForRunnerSession(sessionId) ||
      "",
  ).trim();
  const row = findNativeExternalAgentMessage(sessionId);
  if (!row || !snapshot) return;
  const status = String(snapshot.status || "").trim();
  completeNativeExternalAgentRunningOperations(
    snapshot.sessionId,
    status === "cancelled"
      ? "外部 Agent Runner 会话已取消"
      : "外部 Agent Runner 会话已结束",
  );
  const finalOutput = resolveNativeExternalAgentFinalOutput(snapshot);
  const blockedReason = shouldShowNativeExternalAgentBlockedReason(
    snapshot,
    finalOutput,
  )
    ? String(snapshot.blockedReason || "").trim()
    : "";
  const headerLines = [
    blockedReason ? `执行未完成：${blockedReason}` : "",
  ].filter(Boolean);
  const outputLines = finalOutput
    ? [finalOutput]
    : [
        status === "cancelled"
          ? "本次外部 Agent 执行已取消。"
          : "外部 Agent 没有返回可展示的最终回答。",
      ];
  row.content = [...headerLines, ...outputLines].join("\n");
  row.displayMode = "";
  row.time = nowText();
  upsertNativeExternalAgentMessageOperation(snapshot);
  persistNativeExternalAgentRowsForSession(normalizedChatSessionId);
  if (isCurrentChatSession(selectedProjectId.value, normalizedChatSessionId)) {
    scrollToBottom();
  }
  const rows = nativeExternalAgentRowsForSession(
    sessionId,
    normalizedChatSessionId,
  );
  const assistantIndex = rows.findIndex(
    (item) => String(item?.id || "").trim() === String(row.id || "").trim(),
  );
  const userMessage = assistantIndex > 0 ? rows[assistantIndex - 1] : null;
  const rootGoal =
    userMessage?.role === "user"
      ? String(userMessage.content || "").trim()
      : "";
  void upsertProjectChatRequirementRecord({
    chatSessionId: normalizedChatSessionId,
    status: status === "completed" ? "done" : "blocked",
    rootGoal,
    messageId: userMessage?.id || "",
    assistantMessageId: row.id,
    resultSummary: row.content,
    verificationResult:
      status === "completed"
        ? "外部 Agent 已返回最终回答并写入当前聊天。"
        : blockedReason || "外部 Agent 未完成，已写入当前聊天。",
    runnerSessionId: snapshot.sessionId,
    runnerAgentType: snapshot.agentType,
    source: "tauri_external_agent_runner",
    sourceContext: {
      runner_status: status,
      runner_exit_code: snapshot.exitCode ?? null,
      runner_label: snapshot.label || "",
      workspace_path: snapshot.workspacePath || "",
      blocked_reason: snapshot.blockedReason || "",
      shown_blocked_reason: blockedReason,
      diagnostics: buildNativeExternalAgentDiagnosticPreview(3000, sessionId),
    },
  });
  void persistNativeExternalAgentFinalMessages(
    snapshot,
    row,
    normalizedChatSessionId,
  );
}

async function persistNativeExternalAgentChatMessage(
  message,
  snapshot,
  role,
  chatSessionId = "",
) {
  const projectId = String(selectedProjectId.value || "").trim();
  const normalizedChatSessionId = String(
    chatSessionId ||
      getNativeExternalAgentChatSessionIdForRunnerSession(
        snapshot?.sessionId,
      ) ||
      currentChatSessionId.value ||
      "",
  ).trim();
  if (!projectId || !normalizedChatSessionId || !message?.content) return null;
  try {
    const data = await api.post(
      `/projects/${encodeURIComponent(projectId)}/chat/history/messages`,
      {
        chat_session_id: normalizedChatSessionId,
        message_id: String(message.id || "").trim(),
        role,
        content: String(message.content || ""),
        display_mode: String(message.displayMode || "").trim(),
        source_context: {
          source: "tauri_external_agent_runner",
          runner_session_id: String(snapshot?.sessionId || "").trim(),
          runner_agent_type: String(snapshot?.agentType || "").trim(),
          runner_status: String(snapshot?.status || "").trim(),
          runner_exit_code: snapshot?.exitCode ?? null,
          agent_runtime_trace: {
            operations: Array.isArray(message.operations)
              ? message.operations.map((operation) => ({
                  ...operation,
                  meta: {
                    ...(operation?.meta && typeof operation.meta === "object"
                      ? operation.meta
                      : {}),
                    source: "tauri_external_agent_runner",
                    hide_in_message_process: "true",
                  },
                }))
              : [],
          },
        },
      },
    );
    return data?.message || null;
  } catch (err) {
    console.warn("persist native external agent message failed", err);
    return null;
  }
}

async function persistNativeExternalAgentFinalMessages(
  snapshot,
  assistantMessage,
  chatSessionId = "",
) {
  const sessionId = String(snapshot?.sessionId || "").trim();
  if (!sessionId || nativeExternalAgentPersistedSessions.value.has(sessionId)) {
    return;
  }
  nativeExternalAgentPersistedSessions.value = new Set([
    ...nativeExternalAgentPersistedSessions.value,
    sessionId,
  ]);
  const normalizedChatSessionId = String(
    chatSessionId ||
      getNativeExternalAgentChatSessionIdForRunnerSession(sessionId) ||
      "",
  ).trim();
  const rows = nativeExternalAgentRowsForSession(
    sessionId,
    normalizedChatSessionId,
  );
  const assistantIndex = rows.findIndex(
    (item) =>
      String(item?.id || "").trim() ===
      String(assistantMessage?.id || "").trim(),
  );
  const userMessage = assistantIndex > 0 ? rows[assistantIndex - 1] : null;
  if (userMessage?.role === "user") {
    await persistNativeExternalAgentChatMessage(
      userMessage,
      snapshot,
      "user",
      normalizedChatSessionId,
    );
  }
  await persistNativeExternalAgentChatMessage(
    assistantMessage,
    snapshot,
    "assistant",
    normalizedChatSessionId,
  );
  void refreshChatSessionsKeepingCurrent();
}

async function pollNativeExternalAgentSession(sessionId) {
  const normalizedSessionId = String(sessionId || "").trim();
  if (!normalizedSessionId) return;
  stopNativeExternalAgentSessionPolling(normalizedSessionId);
  try {
    const lastSeq = getNativeExternalAgentSessionLogs(
      normalizedSessionId,
    ).reduce((maxSeq, item) => Math.max(maxSeq, Number(item.seq || 0)), 0);
    const snapshot = await getNativeExternalAgentSession({
      sessionId: normalizedSessionId,
      sinceSeq: lastSeq,
    });
    if (
      nativeExternalAgentFastKilledSessionIds.has(normalizedSessionId) ||
      nativeExternalAgentCancelledSessionIds.has(normalizedSessionId)
    ) {
      const cancelledSnapshot =
        buildFastKilledNativeExternalAgentSnapshot(normalizedSessionId);
      applyNativeExternalAgentSessionSnapshot(cancelledSnapshot);
      markNativeExternalAgentOperationCancelledFast(normalizedSessionId);
      stopNativeExternalAgentSessionPolling(normalizedSessionId);
      syncChatLoadingWithCurrentSession();
      scheduleNativeExternalAgentDeferredCleanup(
        normalizedSessionId,
        getNativeExternalAgentChatSessionIdForRunnerSession(
          normalizedSessionId,
        ),
        cancelledSnapshot,
      );
      return;
    }
    applyNativeExternalAgentSessionSnapshot(snapshot);
    upsertNativeExternalAgentMessageOperation(snapshot);
    if (snapshot.status === "running" || snapshot.status === "cancelling") {
      syncChatLoadingWithCurrentSession();
      const timer = window.setTimeout(
        () => void pollNativeExternalAgentSession(normalizedSessionId),
        800,
      );
      nativeExternalAgentSessionPollTimers.set(normalizedSessionId, timer);
      if (
        normalizeNativeExternalAgentSessionId(
          nativeExternalAgentSession.value,
        ) === normalizedSessionId
      ) {
        nativeExternalAgentSessionPollTimer = timer;
      }
      return;
    }
    releaseNativeExternalAgentTurnIfTerminal(
      normalizedSessionId,
      getNativeExternalAgentChatSessionIdForRunnerSession(normalizedSessionId),
      snapshot,
    );
    syncChatLoadingWithCurrentSession();
    finalizeNativeExternalAgentSessionOnce(
      snapshot,
      getNativeExternalAgentChatSessionIdForRunnerSession(normalizedSessionId),
    );
    await refreshNativeRunnerPermissionRecords();
    await refreshNativeExternalAgentSessionRecords({ silent: true });
  } catch (err) {
    const unavailableSnapshot = buildUnavailableNativeExternalAgentSnapshot(
      normalizedSessionId,
      err?.message || "读取 Runner 会话失败",
    );
    applyNativeExternalAgentSessionSnapshot(unavailableSnapshot);
    upsertNativeExternalAgentMessageOperation(unavailableSnapshot);
    releaseNativeExternalAgentTurnIfTerminal(
      normalizedSessionId,
      getNativeExternalAgentChatSessionIdForRunnerSession(normalizedSessionId),
      unavailableSnapshot,
    );
    syncChatLoadingWithCurrentSession();
    ElMessage.warning(err?.message || "读取 Runner 会话失败");
  }
}

async function startNativeExternalAgentSession(
  chatSessionId = "",
  options = {},
) {
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) {
    ElMessage.info("当前是网页模式；桌面端原生桥接入后可启动 Runner。");
    return false;
  }
  const effectiveChatSessionId = String(
    chatSessionId || currentChatSessionId.value || "",
  ).trim();
  if (isNativeExternalAgentRunningForChatSession(effectiveChatSessionId)) {
    ElMessage.warning("当前对话已有外部 Agent Runner 正在执行");
    return false;
  }
  const workspacePath = String(
    workspacePathDraftNormalized.value ||
      workspacePathResolved.value ||
      projectWorkspaceResolved.value ||
      "",
  ).trim();
  if (!workspacePath) {
    ElMessage.warning("请先配置本机工作区");
    return false;
  }
  const agentType = String(
    projectChatSettings.value.external_agent_type || "codex_cli",
  ).trim();
  const agentLabel = externalAgentDisplayLabel.value || agentType;
  const displayPrompt = String(
    options.displayPrompt || options.userPrompt || draftText.value || "",
  ).trim();
  const executionPrompt = String(
    options.executionPrompt || options.userPrompt || displayPrompt || "",
  ).trim();
  if (!displayPrompt && !executionPrompt) {
    ElMessage.warning("请先在输入框写明要交给外部 Agent 的任务");
    return false;
  }
  const taskPrompt = buildNativeExternalAgentTaskPrompt({
    userPrompt: executionPrompt || displayPrompt,
    chatSessionId: effectiveChatSessionId,
    workspacePath,
    agentLabel,
    attachmentNames: options.attachmentNames || [],
    slashCommandKind: options.slashCommandKind || "",
  });
  if (
    String(currentChatSessionId.value || "").trim() === effectiveChatSessionId
  ) {
    nativeExternalAgentRunning.value = true;
    nativeExternalAgentChatSessionId.value = effectiveChatSessionId;
    nativeExternalAgentSession.value = null;
    nativeExternalAgentSessionLogs.value = [];
  }
  setNativeExternalAgentBackgrounded(effectiveChatSessionId, false);
  setNativeExternalAgentLaunching(effectiveChatSessionId, true);
  try {
    const snapshot = await startNativeExternalAgentSessionCommand({
      agentType,
      workspacePath,
      prompt: taskPrompt,
    });
    applyNativeExternalAgentSessionSnapshot(snapshot, {
      chatSessionId: effectiveChatSessionId,
      select:
        String(currentChatSessionId.value || "").trim() ===
        effectiveChatSessionId,
    });
    selectedNativeExternalAgentRecordId.value = String(
      snapshot.sessionId || "",
    ).trim();
    appendNativeExternalAgentMessages(
      displayPrompt || executionPrompt,
      snapshot,
      effectiveChatSessionId,
      taskPrompt,
      {
        attachmentNames: options.attachmentNames || [],
        slashCommandKind: options.slashCommandKind || "",
      },
    );
    schedulePersistChatRuntime();
    void refreshNativeExternalAgentSessionRecords({ silent: true });
    resetDraft();
    void Promise.allSettled([
      getNativeRuntimeInfo(),
      detectNativeExecutors({ workspacePath }),
    ]).then(([runtimeInfoResult, executorStatusResult]) => {
      nativeRuntimeInfo.value =
        runtimeInfoResult.status === "fulfilled"
          ? runtimeInfoResult.value
          : null;
      nativeExecutorStatus.value =
        executorStatusResult.status === "fulfilled"
          ? executorStatusResult.value
          : null;
      if (nativeExecutorStatus.value) {
        applyNativeExecutorStatusToExternalAgentInfo(
          nativeExecutorStatus.value,
        );
      }
    });
    void recordNativeRunnerPermissionDecision({
      command: snapshot.command || "external_agent",
      args: Array.isArray(snapshot.args)
        ? snapshot.args
            .slice(0, 8)
            .map((arg) =>
              String(arg || "").includes("用户本次任务：")
                ? "<task-prompt>"
                : arg,
            )
        : [],
      workspacePath,
      decision: snapshot.status === "running" ? "approve_once" : "reject",
      reason: snapshot.summary || "外部 Agent Runner 会话",
      scope: "current_request",
      source: "project_chat_external_agent_session",
      riskLevel: "approval_required",
    }).catch((err) => {
      console.warn("record native external agent permission failed", err);
    });
    void recordDesktopAuditEvent({
      event_type: "desktop_external_agent_session_start",
      step: "外部 Agent Runner 会话启动",
      status: snapshot.status === "running" ? "running" : "failed",
      content: `${snapshot.label || agentLabel} Runner 会话：${
        snapshot.summary || "已启动"
      }`,
      facts: [
        `agent=${snapshot.agentType || agentType}`,
        `session=${snapshot.sessionId || ""}`,
        `status=${snapshot.status || ""}`,
        workspacePath ? `workspace=${workspacePath}` : "",
      ].filter(Boolean),
      risks:
        snapshot.status === "running"
          ? []
          : [snapshot.blockedReason || "Runner 会话未启动"],
    });
    if (snapshot.status === "running") {
      ElMessage.success("外部 Agent Runner 已启动");
      void pollNativeExternalAgentSession(snapshot.sessionId);
      return true;
    }
    releaseNativeExternalAgentTurnIfTerminal(
      snapshot.sessionId,
      effectiveChatSessionId,
      snapshot,
    );
    syncChatLoadingWithCurrentSession();
    finalizeNativeExternalAgentSessionOnce(snapshot, effectiveChatSessionId);
    ElMessage.warning(
      snapshot.blockedReason || snapshot.summary || "外部 Agent Runner 未启动",
    );
    return false;
  } catch (err) {
    releaseNativeExternalAgentTurnIfTerminal("", effectiveChatSessionId);
    syncChatLoadingWithCurrentSession();
    ElMessage.error(err?.message || "外部 Agent Runner 启动失败");
    return false;
  } finally {
    setNativeExternalAgentLaunching(effectiveChatSessionId, false);
  }
}

function cancelActiveNativeExternalAgentSession() {
  const sessionId = String(
    nativeExternalAgentSession.value?.sessionId ||
      getNativeExternalAgentRunnerSessionIdForChatSession(
        currentChatSessionId.value,
      ) ||
      "",
  ).trim();
  return cancelNativeExternalAgentSessionById(sessionId);
}

function cancelNativeExternalAgentSessionById(sessionId = "") {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  if (!normalizedSessionId) return false;
  const chatSessionId =
    getNativeExternalAgentChatSessionIdForRunnerSession(normalizedSessionId) ||
    String(currentChatSessionId.value || "").trim();
  applyNativeExternalAgentFastKilledSession(normalizedSessionId, chatSessionId);
  ElMessage.success("已终止 Runner 会话");
  void hardKillNativeExternalAgentSession({ sessionId: normalizedSessionId })
    .then(() => {
      scheduleNativeExternalAgentDeferredCleanup(
        normalizedSessionId,
        chatSessionId,
        buildFastKilledNativeExternalAgentSnapshot(normalizedSessionId),
      );
    })
    .catch((err) => {
      console.warn("hard kill Runner session failed, fallback to cancel", err);
      void cancelNativeExternalAgentSession({ sessionId: normalizedSessionId })
        .then(() => {
          scheduleNativeExternalAgentDeferredCleanup(
            normalizedSessionId,
            chatSessionId,
            buildFastKilledNativeExternalAgentSnapshot(normalizedSessionId),
          );
        })
        .catch((fallbackErr) => {
          ElMessage.error(fallbackErr?.message || "终止 Runner 会话失败");
        });
    });
  return true;
}

function backgroundCurrentNativeExternalAgentSession() {
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  if (!chatSessionId) return false;
  const runnerSessionId =
    getNativeExternalAgentRunnerSessionIdForChatSession(chatSessionId);
  const snapshot = runnerSessionId
    ? nativeExternalAgentSessionsById.get(runnerSessionId)
    : null;
  if (!runnerSessionId || !isLiveNativeExternalAgentStatus(snapshot?.status)) {
    return false;
  }
  setNativeExternalAgentBackgrounded(chatSessionId, true);
  persistCurrentChatRuntimeNow(selectedProjectId.value, chatSessionId);
  ElMessage.info("已转入后台运行，任务不会取消");
  return true;
}

async function hydrateNativeDesktopRuntimeInfo() {
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) {
    nativeRuntimeInfo.value = null;
    return;
  }
  try {
    nativeRuntimeInfo.value = await getNativeRuntimeInfo();
  } catch {
    nativeRuntimeInfo.value = null;
  }
}

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
  clearAuthSession();
  router.replace("/login");
}

const localConnectorSummary = computed(() => {
  if (!isExternalAgentMode.value) {
    return projectWorkspaceResolved.value ? "项目工作区可用" : "未配置工作区";
  }
  if (externalAgentConnectorRequired.value) {
    return "待配置本机运行";
  }
  if (!activeLocalConnector.value) {
    return projectWorkspaceResolved.value ? "本机运行" : "未配置工作区";
  }
  const connectorName = String(
    activeLocalConnector.value.connector_name ||
      activeLocalConnector.value.id ||
      "",
  ).trim();
  const onlineText = activeLocalConnector.value.online ? "在线" : "离线";
  return [connectorName || "旧版本地连接器", onlineText]
    .filter(Boolean)
    .join(" · ");
});
const localRunnerSummary = computed(() => {
  if (!showLocalRuntimeSettings) return "当前部署已隐藏本机控制项";
  if (!isLocalRunnerSurface.value) {
    return projectWorkspaceResolved.value ? "项目工作区可用" : "未配置工作区";
  }
  if (!hasSelectedProject.value) return "待选择项目";
  if (!projectWorkspaceResolved.value) return "待配置工作区";
  return "系统模型 · 本机执行";
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
const settingsCenterItems = computed(() => SETTINGS_CENTER_ITEM_DEFS);
const settingsInternalItems = computed(() => settingsCenterItems.value);
const activeSettingsPanelMeta = computed(() => {
  const panelId = String(activeSettingsPanel.value || "").trim() || "chat";
  return (
    SETTINGS_CENTER_PANEL_META[panelId] ||
    settingsCenterItems.value.find((item) => item.id === panelId) ||
    SETTINGS_CENTER_PANEL_META.chat
  );
});
const isSettingsCenterRoute = computed(() =>
  isChatSettingsRoutePath(route.path),
);
const roleAccessNarrative = computed(() => {
  return "这里仅调整当前对话上下文，不承载平台级菜单。";
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
    title: `${item.label}：当前项目会话配置`,
    description: item.intro,
    target: () => resolveTourTarget(settingsSidebarRef),
    placement: "right-start",
  })),
  {
    title: "这里只改当前对话",
    description:
      "这里不会再展示平台菜单。改完当前对话配置后，回到 AI 对话立即验证，最容易看出配置是否真的生效。",
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
  if (!selectedCount) return `自动分配 (${total} 名可用员工)`;
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
const currentChatSessionSourceLabel = computed(() =>
  formatChatSessionSourceLabel(currentChatSession.value),
);
const groupChatDialogTitle = computed(() =>
  groupChatEditingSessionId.value ? "编辑机器人对话" : "新建机器人对话",
);
const groupChatEditingSession = computed(
  () =>
    (chatSessions.value || []).find(
      (item) =>
        item.id === String(groupChatEditingSessionId.value || "").trim(),
    ) || null,
);
const groupChatEditingSource = computed(() =>
  normalizeChatSourceContext(groupChatEditingSession.value || {}),
);
const groupChatEditingResolved = computed(() =>
  Boolean(groupChatEditingSource.value.external_chat_id),
);
const groupChatDialogStatus = computed(() => {
  const sessionId = String(groupChatEditingSessionId.value || "").trim();
  const live = sessionId ? groupChatLiveStatuses.value[sessionId] : null;
  if (live?.message) {
    const status = String(live.status || "")
      .trim()
      .toLowerCase();
    return {
      title: status === "processing" ? "机器人通讯中" : "机器人对话状态",
      text: String(live.message || "").trim(),
      type: status === "processing" ? "success" : "info",
    };
  }
  const source = groupChatEditingSource.value;
  if (source.external_chat_id) {
    return {
      title: "机器人对话状态",
      text: "当前机器人对话已额外绑定外部群上下文，群内 @ 机器人时可同步到这个 AI 对话。",
      type: "success",
    };
  }
  if (source.connector_id || groupChatDraft.value.connector_id) {
    return {
      title: "机器人对话状态",
      text: "当前将直接创建机器人对话，不再要求先绑定群。只有需要同步真实群消息时，才需要后续补群上下文。",
      type: "success",
    };
  }
  return {
    title: "机器人对话状态",
    text: "先选择平台和机器人即可创建机器人对话；群绑定不再是必填前置条件。",
    type: "info",
  };
});
function normalizeBotPlatformConnector(item) {
  const raw =
    item && typeof item === "object" && !Array.isArray(item) ? item : {};
  return {
    id: String(raw.id || "").trim(),
    enabled: raw.enabled !== false,
    platform: String(raw.platform || "")
      .trim()
      .toLowerCase(),
    name: String(raw.name || "").trim(),
    agent_name: String(raw.agent_name || "").trim(),
    description: String(raw.description || "").trim(),
    app_id: String(raw.app_id || "").trim(),
    app_secret: String(raw.app_secret || "").trim(),
    project_id: String(raw.project_id || "").trim(),
  };
}

const groupBotConnectorOptions = computed(() => {
  const platform = String(groupChatDraft.value.platform || "")
    .trim()
    .toLowerCase();
  const projectId = String(selectedProjectId.value || "").trim();
  if (!platform) return [];
  return (botPlatformConnectors.value || [])
    .map(normalizeBotPlatformConnector)
    .filter((item) => {
      if (!item.id || !item.enabled || item.platform !== platform) return false;
      if (!item.app_id || !item.app_secret) return false;
      return !item.project_id || !projectId || item.project_id === projectId;
    })
    .map((item) => {
      const name =
        item.name ||
        item.agent_name ||
        `${formatChatPlatformLabel(item.platform)}机器人`;
      const scope = item.project_id ? "当前项目" : "全局配置";
      return {
        value: item.id,
        label: name,
        name,
        description: `${scope} · 配置ID：${item.id}`,
      };
    });
});

const groupBotConnectorHint = computed(() => {
  const platformLabel = formatChatPlatformLabel(groupChatDraft.value.platform);
  if (groupBotConnectorOptions.value.length) {
    return "选择后会写入当前机器人对话的 source_context.connector_id；创建后即可直接开始对话。";
  }
  return `当前项目没有可用的${platformLabel}机器人，请先到第三方机器人接入页面添加并关联项目。`;
});

const groupChatResolveIdentityOptions = [
  {
    label: "机器人",
    value: "bot",
    description: "使用应用身份解析群 ID，适合机器人可见的群。",
  },
  {
    label: "用户",
    value: "user",
    description: "使用当前登录用户身份解析群 ID，适合用户授权可见的群。",
  },
];

const canSubmitGroupChatDialog = computed(
  () =>
    Boolean(
      String(
        groupChatDraft.value.title ||
          groupBotConnectorOptions.value.find(
            (item) =>
              item.value ===
              String(groupChatDraft.value.connector_id || "").trim(),
          )?.name ||
          "",
      ).trim(),
    ) &&
    Boolean(String(groupChatDraft.value.platform || "").trim()) &&
    Boolean(String(groupChatDraft.value.connector_id || "").trim()) &&
    !groupChatCreating.value,
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
const externalAgentOptions = computed(() => {
  const optionsByType = new Map();
  for (const item of DESKTOP_EXTERNAL_AGENT_OPTIONS) {
    const nativeStatus = nativeExecutorStatus.value?.[item.nativeKey] || null;
    optionsByType.set(item.agent_type, {
      agent_type: item.agent_type,
      label: nativeExecutorOptionLabel(item.label, nativeStatus),
      available: Boolean(nativeStatus?.installed),
      installed: Boolean(nativeStatus?.installed),
      implemented: true,
      reason: nativeStatus?.installed
        ? ""
        : String(nativeStatus?.reason || "").trim(),
      runtime_model_name: item.runtime_model_name,
    });
  }
  const remoteOptions = Array.isArray(externalAgentInfo.value.agent_types)
    ? externalAgentInfo.value.agent_types
    : [];
  for (const item of remoteOptions) {
    const agentType = String(item?.agent_type || "").trim();
    if (!agentType || item?.implemented === false) continue;
    const existing = optionsByType.get(agentType) || {};
    optionsByType.set(agentType, {
      ...item,
      ...existing,
      agent_type: agentType,
      label: existing.label || String(item?.label || agentType).trim(),
      implemented: true,
      available: Boolean(existing.available || item?.available),
      installed: Boolean(
        existing.installed || item?.installed || item?.available,
      ),
      reason: existing.reason || String(item?.reason || "").trim(),
    });
  }
  return DESKTOP_EXTERNAL_AGENT_OPTIONS.map((item) =>
    optionsByType.get(item.agent_type),
  ).filter(Boolean);
});
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
  if (isLocalRunnerSurface.value) {
    return [
      "检查当前工作区状态并给出下一步",
      "帮我执行一个需要本机环境的任务",
      "用系统模型分析并调用本地工具处理",
    ];
  }
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
  if (isLocalRunnerSurface.value) return "启动本地运行窗口";
  if (!hasAccessibleProjects.value) return "暂无可访问项目";
  if (!hasSelectedProject.value) {
    return ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
      ? "开始一轮通用对话"
      : "先选择一个项目";
  }
  return "开始一轮新的对话";
});
const emptyStateText = computed(() => {
  if (isLocalRunnerSurface.value) {
    return hasSelectedProject.value
      ? "当前入口复用系统已配置的大模型 Provider，不使用 Ollama；需要执行命令、读写文件或调用飞书时，会通过本机运行环境和审批流程推进。"
      : "选择项目后可带入项目工作区、员工、规则和工具；模型仍使用系统供应商配置，本地窗口只负责执行和权限边界。";
  }
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
  isTerminalInteractionMode.value
    ? "项目终端已连接，直接输入命令或交互内容，按 Enter 发送。"
    : agentWorkflowState.value.phase === "waiting_user"
      ? "请先在消息卡片完成确认或授权；完成后系统会自动继续执行。"
      : agentWorkflowState.value.phase === "running"
        ? "智能体正在执行；输入补充会排队，并在当前回合结束后自动合并。"
        : agentWorkflowState.value.phase === "queued"
          ? "已有补充排队，继续输入可追加更多上下文。"
          : ["blocked", "failed"].includes(agentWorkflowState.value.phase)
            ? "当前执行未完成，可补充处理意见后重新发送。"
            : isAwaitingCardActionInteraction.value
              ? "请点击消息卡片中的授权按钮；授权后 AI 会自动继续执行。"
              : isAwaitingUserInteraction.value
                ? "当前有交互等待处理，可补充下一条消息，按 Enter 发送。"
                : !hasAccessibleProjects.value
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
                    : !isChatSettingsDisplayReady.value
                      ? "正在加载项目配置，完成后即可发送。"
                    : "输入你的问题，按 Enter 发送，Shift + Enter 换行。输入 / 可查看可用命令。",
);
const composerHintText = computed(() => {
  if (isTerminalInteractionMode.value) {
    return "当前主输入框已切换为项目终端输入，Enter 发送";
  }
  if (agentWorkflowState.value.phase === "waiting_user") {
    return "等待你在消息卡片确认，完成后自动继续";
  }
  if (agentWorkflowState.value.phase === "running") {
    return "执行中，补充内容会自动排队";
  }
  if (agentWorkflowState.value.phase === "queued") {
    return "补充已排队，等待当前回合结束";
  }
  if (agentWorkflowState.value.phase === "blocked") {
    return "执行已阻断，请查看等待项";
  }
  if (agentWorkflowState.value.phase === "failed") {
    return "执行失败，可补充修复要求后继续";
  }
  if (isAwaitingCardActionInteraction.value) {
    return "等待授权，点击消息卡片按钮后自动继续";
  }
  if (isAwaitingUserInteraction.value) {
    return "当前处于交互等待状态，可补充下一条消息";
  }
  if (hasSelectedProject.value && !isChatSettingsDisplayReady.value) {
    return "正在加载项目执行配置";
  }
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
  return "Enter 发送，Shift + Enter 换行，/ 查看命令";
});
const shortThreadId = computed(() => {
  const value = String(externalAgentInfo.value.thread_id || "").trim();
  return value ? value.slice(0, 8) : "";
});
function isTerminalInputCandidateRow(row) {
  if (!row || String(row.role || "assistant") !== "assistant") return false;
  const terminalOperations = (
    Array.isArray(row.operations) ? row.operations : []
  ).filter(
    (operation) =>
      String(operation?.kind || "")
        .trim()
        .toLowerCase() === "terminal",
  );
  if (terminalOperations.length) {
    return terminalOperations.some((operation) => {
      const phase = normalizeOperationPhase(
        operation?.phase || operation?.status,
      );
      return !["completed", "failed", "blocked"].includes(phase);
    });
  }
  return (
    String(row.displayMode || "").trim() === "terminal" &&
    terminalPanelStatus.value === "running"
  );
}

function completeTerminalInputOperations(row, summary = "终端交互已结束") {
  if (!row || !Array.isArray(row.operations) || !row.operations.length)
    return false;
  let changed = false;
  row.operations = row.operations.map((operation) => {
    const kind = String(operation?.kind || "")
      .trim()
      .toLowerCase();
    if (kind !== "terminal") return operation;
    const phase = normalizeOperationPhase(
      operation?.phase || operation?.status,
    );
    if (["completed", "failed", "blocked"].includes(phase)) return operation;
    changed = true;
    return {
      ...operation,
      phase: "completed",
      summary: String(operation?.summary || summary).trim() || summary,
    };
  });
  return changed;
}

function completeFinishedMessageOperations(row, summary = "本轮执行已结束") {
  if (!row || !Array.isArray(row.operations) || !row.operations.length) {
    return false;
  }
  const finalSummary = String(summary || "").trim() || "本轮执行已结束";
  let changed = false;
  row.operations = row.operations.map((operation) => {
    const phase = normalizeOperationPhase(
      operation?.phase || operation?.status,
    );
    if (!["running", "pending"].includes(phase)) {
      return operation;
    }
    changed = true;
    return {
      ...operation,
      phase: "completed",
      actionType: "none",
      summary: String(operation?.summary || "").trim() || finalSummary,
      updatedAt: nowText(),
    };
  });
  return changed;
}

function isLiveTerminalOperation(operation) {
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  if (kind !== "terminal") return false;
  const phase = normalizeOperationPhase(operation?.phase || operation?.status);
  return !["completed", "failed", "blocked"].includes(phase);
}

function hasLiveTerminalOperation(row) {
  return (Array.isArray(row?.operations) ? row.operations : []).some(
    (operation) => isLiveTerminalOperation(operation),
  );
}

function hasActiveTerminalTransport() {
  return Boolean(
    terminalMirrorConnected.value || terminalPanelStatus.value === "running",
  );
}

function markTerminalOperationsWaitingForInput(
  row,
  summary = "等待你在对话框继续终端登录操作",
) {
  if (!row || !Array.isArray(row.operations) || !row.operations.length) {
    return false;
  }
  let changed = false;
  row.operations = row.operations.map((operation) => {
    if (!isLiveTerminalOperation(operation)) return operation;
    changed = true;
    return {
      ...operation,
      title: "需要你继续操作",
      phase: "waiting_user",
      actionType: "enter_text",
      summary: String(operation?.summary || summary).trim() || summary,
      detail:
        String(operation?.detail || "").trim() ||
        "终端会话仍在等待输入，主输入框会继续发送到项目终端。",
      updatedAt: nowText(),
    };
  });
  return changed;
}

function shouldPreserveTerminalInteractionAfterDone(row, pending) {
  const assistantIndex = Number(pending?.assistantIndex ?? -1);
  if (!row || assistantIndex < 0) return false;
  const activeIndex = Number(activeTerminalMirrorAssistantIndex.value ?? -1);
  if (activeIndex !== assistantIndex) return false;
  const hasLiveSession = hasActiveTerminalTransport();
  if (!hasLiveSession) return false;
  const interaction = terminalStructuredInteraction.value;
  const hasStructuredInteraction = Boolean(
    interaction && Number(interaction.assistantIndex) === assistantIndex,
  );
  const submissionHint = terminalStructuredSubmissionHint.value;
  const hasSubmittedStructuredInteraction = Boolean(
    submissionHint && Number(submissionHint.assistantIndex) === assistantIndex,
  );
  return Boolean(
    hasStructuredInteraction ||
    hasSubmittedStructuredInteraction ||
    hasLiveTerminalOperation(row) ||
    String(row.displayMode || "").trim() === "terminal",
  );
}

function findLatestTerminalInputAssistantIndex(rows) {
  for (let index = (rows || []).length - 1; index >= 0; index -= 1) {
    if (isTerminalInputCandidateRow(rows[index])) return index;
  }
  return -1;
}

const latestTerminalInputAssistantIndex = computed(() =>
  findLatestTerminalInputAssistantIndex(messages.value),
);

const activeTerminalInputTargetIndex = computed(() => {
  const activeIndex = Number(activeTerminalMirrorAssistantIndex.value ?? -1);
  const activeRow =
    activeIndex >= 0 && activeIndex < messages.value.length
      ? messages.value[activeIndex]
      : null;
  if (isTerminalInputCandidateRow(activeRow)) {
    return activeIndex;
  }
  return Number(latestTerminalInputAssistantIndex.value ?? -1);
});

function ensureActiveTerminalInputTarget() {
  const fallbackIndex = Number(activeTerminalInputTargetIndex.value ?? -1);
  if (fallbackIndex >= 0) {
    activeTerminalMirrorAssistantIndex.value = fallbackIndex;
  }
  return fallbackIndex;
}

const hasLiveTerminalSession = computed(() => {
  if (!String(selectedProjectId.value || "").trim()) return false;
  return hasActiveTerminalTransport();
});
const activePendingInteraction = computed(() => {
  const requestId = getActiveRequestId();
  if (requestId) {
    const pending = pendingRequests.get(requestId);
    if (!pending) return null;
    const row = messages.value[pending.assistantIndex];
    const operation = pickAwaitingInteractionOperation(row, {
      allowTerminal: true,
    });
    if (!row || !operation) return null;
    return {
      requestId,
      pending,
      row,
      operation,
    };
  }
  const restorable = findLatestAwaitingInteractionMessage(messages.value);
  if (!restorable?.row || !restorable?.operation) return null;
  return {
    requestId: "",
    pending: null,
    row: restorable.row,
    operation: restorable.operation,
  };
});
const isAwaitingUserInteraction = computed(() =>
  Boolean(activePendingInteraction.value?.operation),
);
const isAwaitingCardActionInteraction = computed(() => {
  const operation = activePendingInteraction.value?.operation;
  if (!operation) return false;
  if (canSupersedePendingInteraction(activePendingInteraction.value)) {
    return false;
  }
  return operationActionButtons(operation).length > 0;
});
const isTerminalInteractionMode = computed(() => {
  if (!String(selectedProjectId.value || "").trim()) return false;
  if (
    hasLiveTerminalSession.value &&
    activeTerminalInputTargetIndex.value >= 0
  ) {
    return true;
  }
  if (!String(activePendingInteraction.value?.requestId || "").trim()) {
    return false;
  }
  if (canSupersedePendingInteraction(activePendingInteraction.value)) {
    return false;
  }
  const operation = activePendingInteraction.value?.operation;
  if (operation) {
    const actionType = normalizeOperationActionType(operation?.actionType);
    const kind = String(operation?.kind || "")
      .trim()
      .toLowerCase();
    if (actionType === "enter_text" || kind === "terminal") {
      return hasLiveTerminalSession.value;
    }
    return false;
  }
  return false;
});

function findLatestAgentWorkflowOperation(phaseNames = []) {
  const phases = new Set(
    (Array.isArray(phaseNames) ? phaseNames : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  );
  for (let rowIndex = messages.value.length - 1; rowIndex >= 0; rowIndex -= 1) {
    const row = messages.value[rowIndex];
    if (!row || String(row.role || "") !== "assistant") continue;
    const operations = messageProcessOperations(row);
    for (let opIndex = operations.length - 1; opIndex >= 0; opIndex -= 1) {
      const operation = operations[opIndex];
      const phase = normalizeOperationPhase(
        operation?.phase || operation?.status,
      );
      if (!phases.size || phases.has(phase)) {
        return { row, rowIndex, operation, phase };
      }
    }
  }
  return null;
}

function summarizeAgentWorkflowOperation(operation) {
  if (!operation) return "";
  return clipText(
    [
      String(operation?.summary || "").trim(),
      String(operation?.title || "").trim(),
    ]
      .filter(Boolean)
      .join(" · "),
    72,
  );
}

const agentWorkflowState = computed(() => {
  const queuedCount = queuedFollowupMessages.value.length;
  const waiting = findLatestAgentWorkflowOperation(["waiting_user"]);
  if (waiting) {
    return {
      phase: "waiting_user",
      title: "等待你确认后继续",
      detail:
        summarizeAgentWorkflowOperation(waiting.operation) ||
        "在消息卡片完成确认或授权后，系统会自动继续执行。",
      actionLabel: "查看等待项",
      waitingCount: 1,
      runningCount: 0,
      queuedCount,
    };
  }

  const blocked = findLatestAgentWorkflowOperation(["blocked"]);
  if (blocked) {
    return {
      phase: "blocked",
      title: "执行已阻断",
      detail:
        summarizeAgentWorkflowOperation(blocked.operation) ||
        "当前步骤需要处理阻塞原因后才能继续。",
      actionLabel: "查看阻塞项",
      waitingCount: 0,
      runningCount: 0,
      queuedCount,
    };
  }

  const failed = findLatestAgentWorkflowOperation(["failed"]);
  if (failed && !chatLoading.value && pendingRequests.size === 0) {
    return {
      phase: "failed",
      title: "执行失败",
      detail:
        summarizeAgentWorkflowOperation(failed.operation) ||
        "当前回合有步骤失败，请查看运行轨迹。",
      actionLabel: "查看失败项",
      waitingCount: 0,
      runningCount: 0,
      queuedCount,
    };
  }

  const running = findLatestAgentWorkflowOperation(["running", "pending"]);
  const hasCurrentPendingRequest = hasPendingRequestForChatSession(
    currentChatSessionId.value,
  );
  const isRunning = Boolean(
    running ||
    chatLoading.value ||
    hasCurrentPendingRequest ||
    currentChatSessionNativeExternalAgentRunning.value ||
    backgroundTerminalCount.value > 0,
  );
  if (isRunning) {
    const isNativeExternalAgentRunning =
      currentChatSessionNativeExternalAgentRunning.value;
    return {
      phase: "running",
      title: isNativeExternalAgentRunning
        ? "外部 Agent Runner 运行中"
        : backgroundTerminalCount.value > 0 && !chatLoading.value
          ? "项目终端运行中"
          : "智能体执行中",
      detail: isNativeExternalAgentRunning
        ? nativeExternalAgentSession.value?.summary ||
          "外部 Agent 正在本机工作区执行。"
        : summarizeAgentWorkflowOperation(running?.operation) ||
          (queuedCount
            ? "补充内容已排队，当前步骤结束后会自动合并。"
            : "正在执行工具、命令或等待运行结果。"),
      actionLabel: running ? "查看轨迹" : "",
      waitingCount: 0,
      runningCount: 1,
      queuedCount,
    };
  }

  if (queuedCount) {
    return {
      phase: "queued",
      title: "补充已排队",
      detail: "当前回合结束后会自动合并补充内容并重新规划。",
      actionLabel: "",
      waitingCount: 0,
      runningCount: 0,
      queuedCount,
    };
  }

  return {
    phase: "idle",
    title: "",
    detail: "",
    actionLabel: "",
    waitingCount: 0,
    runningCount: 0,
    queuedCount: 0,
  };
});

const showAgentWorkflowStatusStrip = computed(
  () =>
    Boolean(String(selectedProjectId.value || "").trim()) &&
    agentWorkflowState.value.phase !== "idle",
);

const agentWorkflowMetaItems = computed(() => {
  const state = agentWorkflowState.value;
  const items = [];
  if (state.phase === "running") {
    items.push(workingStatusElapsedLabel.value);
  }
  if (state.waitingCount) {
    items.push(`${state.waitingCount} 个等待项`);
  }
  if (state.runningCount) {
    items.push("执行中");
  }
  if (state.queuedCount) {
    items.push(`已排队 ${state.queuedCount} 条补充`);
  }
  if (state.phase === "blocked") {
    items.push("需要处理阻塞");
  }
  if (state.phase === "failed") {
    items.push("查看失败原因");
  }
  return items;
});

function focusAgentWorkflowOperation() {
  const matched =
    findLatestAgentWorkflowOperation(["waiting_user", "blocked", "failed"]) ||
    findLatestAgentWorkflowOperation(["running", "pending"]);
  if (matched?.row) {
    matched.row.processExpanded = true;
  }
  scrollToBottom({ smooth: true });
}

const showPauseGenerationButton = computed(
  () =>
    (Boolean(getActiveRequestId()) ||
      currentChatSessionNativeExternalAgentRunning.value) &&
    (chatLoading.value || currentChatSessionNativeExternalAgentRunning.value) &&
    !isAwaitingUserInteraction.value &&
    !isTerminalInteractionMode.value,
);

const backgroundTerminalCount = computed(() => {
  if (!String(selectedProjectId.value || "").trim()) return 0;
  return hasLiveTerminalSession.value ? 1 : 0;
});

const currentChatSessionNativeExternalAgentRunning = computed(() =>
  isNativeExternalAgentRunningForChatSession(currentChatSessionId.value),
);

const showWorkingStatusBar = computed(() => {
  if (!String(selectedProjectId.value || "").trim()) return false;
  if (isAwaitingUserInteraction.value) return false;
  return Boolean(
    chatLoading.value ||
    hasPendingRequestForChatSession(currentChatSessionId.value) ||
    currentChatSessionNativeExternalAgentRunning.value ||
    backgroundTerminalCount.value > 0,
  );
});

const workingStatusElapsedSeconds = computed(() => {
  const startedAt = Number(workingStatusStartedAt.value || 0);
  if (!startedAt) return 0;
  return Math.max(
    0,
    Math.floor(
      (Number(workingStatusNow.value || Date.now()) - startedAt) / 1000,
    ),
  );
});

const workingStatusElapsedLabel = computed(
  () => `(${formatWorkingDuration(workingStatusElapsedSeconds.value)})`,
);

const workingStatusTitle = computed(() => {
  if (backgroundTerminalCount.value > 0 && !chatLoading.value) {
    return "Terminal running";
  }
  return "Working";
});

const workingStatusMetaItems = computed(() => {
  const items = ["esc to interrupt"];
  const terminalCount = Number(backgroundTerminalCount.value || 0);
  if (terminalCount > 0) {
    items.push(
      `${terminalCount} background terminal${terminalCount === 1 ? "" : "s"} running`,
    );
  }
  items.push("/ps to view", "/stop to close");
  return items;
});

function formatWorkingDuration(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds || 0));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;
  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${String(remainingSeconds).padStart(2, "0")}s`;
  }
  return `${remainingSeconds}s`;
}

function workingStatusSessionKey(chatSessionId = currentChatSessionId.value) {
  return String(chatSessionId || "").trim() || "__current__";
}

function clearWorkingStatusStartForChatSession(chatSessionId = "") {
  const key = workingStatusSessionKey(chatSessionId);
  workingStatusStartedAtBySession.delete(key);
  if (key === workingStatusSessionKey()) {
    workingStatusStartedAt.value = 0;
    workingStatusNow.value = Date.now();
  }
}

function startWorkingStatusTimer() {
  const key = workingStatusSessionKey();
  let startedAt = Number(workingStatusStartedAtBySession.get(key) || 0);
  if (!startedAt) {
    startedAt = Date.now();
    workingStatusStartedAtBySession.set(key, startedAt);
  }
  workingStatusStartedAt.value = startedAt;
  workingStatusNow.value = Date.now();
  if (workingStatusTimer !== null) return;
  workingStatusTimer = window.setInterval(() => {
    workingStatusNow.value = Date.now();
  }, 1000);
}

function stopWorkingStatusTimer() {
  if (workingStatusTimer !== null) {
    window.clearInterval(workingStatusTimer);
    workingStatusTimer = null;
  }
  workingStatusStartedAt.value = 0;
  workingStatusNow.value = Date.now();
}

function handleWorkingStatusKeydown(event) {
  if (event?.key !== "Escape") return;
  if (!showWorkingStatusBar.value) return;
  if (isAwaitingUserInteraction.value) return;
  event.preventDefault();
  stopGeneration();
}

function canSupersedePendingInteraction(interaction) {
  const operation = interaction?.operation;
  if (!operation) return false;
  const actionType = normalizeOperationActionType(operation?.actionType);
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  if (String(meta.approval_id || meta.review_id || "").trim()) {
    return false;
  }
  if (String(meta.approval_mode || "").trim() === "terminal") {
    return false;
  }
  return (
    ["open_url", "enter_text", "select"].includes(actionType) || kind === "auth"
  );
}

function isInteractionContinuationAck(text) {
  const normalized = String(text || "")
    .trim()
    .replace(/\s+/g, "")
    .toLowerCase();
  return [
    "好了",
    "好啦",
    "已好了",
    "完成了",
    "已完成",
    "授权了",
    "已授权",
    "我已授权",
    "登录好了",
    "登录完成",
    "done",
    "ok",
  ].includes(normalized);
}

function isInteractionContinueIntent(text) {
  const normalized = String(text || "")
    .trim()
    .replace(/\s+/g, "")
    .toLowerCase();
  return [
    "继续",
    "继续执行",
    "继续吧",
    "接着",
    "接着执行",
    "下一步",
    "continue",
    "resume",
  ].includes(normalized);
}

async function submitPendingInteractionAckIfNeeded(text) {
  const interaction = activePendingInteraction.value;
  const normalizedText = String(text || "").trim();
  if (
    !interaction?.operation ||
    (!isInteractionContinuationAck(normalizedText) &&
      !isInteractionContinueIntent(normalizedText))
  ) {
    return false;
  }
  const operation = interaction.operation;
  const schema = operationInteractionSchema(operation);
  if (schema) {
    if (!canSubmitOperationInteraction(operation)) {
      ElMessage.warning("请先完成消息卡片里的必填项");
      resetDraft();
      return true;
    }
    resetDraft();
    await submitOperationInteraction(operation);
    scrollToBottom();
    return true;
  }
  const actionType = normalizeOperationActionType(operation?.actionType);
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  if (actionType === "open_url" || kind === "auth") {
    resetDraft();
    if (isInteractionContinueIntent(normalizedText)) {
      const buttons = operationActionButtons(operation);
      if (buttons.length) {
        await handleOperationAction(operation, buttons[0].key);
      } else {
        ElMessage.info("当前授权任务仍在等待处理，请在浏览器完成授权");
      }
    } else {
      ElMessage.info("已收到授权完成提示，系统检测通过后会自动继续");
    }
    scrollToBottom();
    return true;
  }
  if (isInteractionContinueIntent(normalizedText)) {
    ElMessage.warning("当前等待的是确认类操作，请先使用消息卡片里的按钮继续");
    resetDraft();
    return true;
  }
  scrollToBottom();
  return false;
}

function releasePendingInteractionForFollowup(followupText = "") {
  const interaction = activePendingInteraction.value;
  if (!interaction || !canSupersedePendingInteraction(interaction)) {
    return false;
  }
  const requestId = String(interaction.requestId || "").trim();
  const pending = interaction.pending;
  const row = interaction.row;
  const operation = interaction.operation;
  if (!row || !operation) return false;
  const preview = clipText(String(followupText || "").trim(), 80);
  const summary = preview ? `已收到继续指令：${preview}` : "已切换为下一轮继续";
  upsertMessageOperation(row, {
    ...operation,
    summary,
    phase: "completed",
  });
  appendAssistantStatusNote(
    row,
    "> ↻ 已结束当前等待状态，转到下一轮继续处理。",
  );
  if (requestId && pending) {
    pending.followupReleased = true;
    resolvePendingRequest(requestId, pending, row.content || summary);
  }
  return true;
}

const terminalPanelStatusText = computed(() => {
  if (terminalPanelStatus.value === "error") return "异常";
  if (
    terminalMirrorConnected.value &&
    terminalPanelStatus.value === "running"
  ) {
    return "运行中";
  }
  if (terminalMirrorConnected.value) {
    return "待命";
  }
  if (!hasSelectedProject.value) return "未启用";
  if (!canUseHostTerminal.value) return "未配置";
  return "未启动";
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
  return [
    "# 项目终端",
    canUseHostTerminal.value
      ? "# 点击“启动终端”后可继续执行交互式命令…"
      : "# 先保存项目工作区后再启动终端…",
  ]
    .filter(Boolean)
    .join("\n");
});
const terminalPanelLineCount = computed(() =>
  Array.isArray(terminalPanelLines.value)
    ? terminalPanelLines.value
        .map((line) => String(line || "").trim())
        .filter(Boolean).length
    : 0,
);
const localRunnerProcessStatusTagType = computed(() => {
  if (terminalPanelStatus.value === "error") return "danger";
  if (terminalApprovalPrompt.value) return "warning";
  if (
    terminalMirrorConnected.value ||
    terminalPanelStatus.value === "running"
  ) {
    return "primary";
  }
  return "info";
});
const activeTerminalMirrorRow = computed(() => {
  const index = Number(activeTerminalMirrorAssistantIndex.value);
  if (!Number.isInteger(index) || index < 0) return null;
  return messages.value[index] || null;
});
const localRunnerProcessItems = computed(() => {
  const row = activeTerminalMirrorRow.value;
  const index = Number(activeTerminalMirrorAssistantIndex.value);
  const liveItems = row ? messageLiveProgressItems(row, index) : [];
  if (liveItems.length) return liveItems;
  if (terminalApprovalPrompt.value) {
    return [
      {
        id: "approval",
        phase: "waiting_user",
        title: terminalApprovalPrompt.value.title || "等待命令审批",
        summary: terminalApprovalPrompt.value.description || "",
        phaseLabel: "待处理",
      },
    ];
  }
  if (
    terminalMirrorConnected.value ||
    terminalPanelStatus.value === "running"
  ) {
    return [
      {
        id: "terminal-running",
        phase: "running",
        title: terminalActiveCommand.value || "项目终端运行中",
        summary:
          hostTerminalWorkspacePath.value ||
          projectWorkspaceResolved.value ||
          "",
        phaseLabel: "进行中",
      },
    ];
  }
  const recentLines = Array.isArray(terminalPanelLines.value)
    ? terminalPanelLines.value
        .map((line) => String(line || "").trim())
        .filter(Boolean)
        .slice(-4)
    : [];
  if (recentLines.length) {
    return recentLines.map((line, index) => ({
      id: `terminal-line-${index}`,
      phase: "completed",
      title: clipText(line, 140),
      summary: "",
      phaseLabel: "已记录",
    }));
  }
  return [
    {
      id: "idle",
      phase: "pending",
      title: "等待执行任务",
      summary: canUseHostTerminal.value
        ? "启动终端或运行外部 Agent 后会显示过程细节"
        : "先保存项目工作区后再启动终端",
      phaseLabel: "待命",
    },
  ];
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
function buildAssistSlashCommand(actionId) {
  const normalized = String(actionId || "")
    .trim()
    .toLowerCase();
  if (!normalized) return "/";
  if (normalized === "employee_create") return "/employee-create";
  if (normalized === "prompt_search") return "/prompt-search";
  if (normalized === "prompt_improve") return "/prompt-improve";
  if (normalized === "skill_search") return "/skill-search";
  return `/${normalized.replace(/_/g, "-")}`;
}

const composerSlashCommands = computed(() => {
  const commands = [
    {
      id: "stats_report",
      kind: "stats_report",
      command: PROJECT_STATS_COMMAND,
      aliases: PROJECT_STATS_COMMAND_ALIASES,
      label: "项目统计报表",
      description:
        "把当前项目统计 AI 报表注入聊天，让模型继续分析优化方向和升级重点。",
      assistActionId: "",
    },
    {
      id: "host_run",
      kind: "host_run",
      command: HOST_RUN_COMMAND,
      aliases: HOST_RUN_COMMAND_ALIASES,
      label: "本机命令",
      description:
        "让 AI 直接在当前电脑执行命令并返回实际结果，例如 /run lark-cli auth status。",
      assistActionId: "",
    },
    {
      id: "lark_cli",
      kind: "lark_cli",
      command: LARK_CLI_COMMAND,
      aliases: LARK_CLI_COMMAND_ALIASES,
      label: "飞书 CLI",
      description:
        "强制优先使用 lark-cli 执行飞书相关操作，例如 /lark-cli auth status 或 /feishucli 给某人发 test。",
      assistActionId: "",
    },
    {
      id: "form_json",
      kind: "form_json",
      command: "/form-json",
      aliases: ["/form", "/表单", "/表单数据"],
      label: "表单数据",
      description:
        "让大模型根据字段描述生成 ElementEasyForm formJson，并在消息里长期保留预览和复制入口。",
      assistActionId: "",
    },
  ];
  for (const action of composerAssistActions.value) {
    commands.push({
      id: `assist_${action.id}`,
      kind: "assist",
      command: buildAssistSlashCommand(action.id),
      aliases: [],
      label: String(action.label || "").trim() || "未命名命令",
      description: String(
        action.shortDesc || action.activeText || action.instruction || "",
      ).trim(),
      assistActionId: String(action.id || "").trim(),
    });
  }
  return commands;
});

function normalizeSlashCommandToken(value) {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function parseSlashCommandDraft(text) {
  const raw = String(text || "");
  const normalized = raw.replace(/^\s+/, "");
  if (!normalized.startsWith("/")) return null;
  const firstLine = normalized.split("\n")[0];
  const match = firstLine.match(/^(\/[^\s]*)/);
  if (!match) return null;
  return {
    token: normalizeSlashCommandToken(match[1]),
    query: normalizeSlashCommandToken(match[1]).replace(/^\//, ""),
    isCommandPhase: !/\s/.test(firstLine),
  };
}

const messagesContainer = ref(null);
const projectSwitcherRef = computed(
  () => conversationSidebarRef.value?.projectSwitcherRef || null,
);
const draftText = ref("");
const slashCommandHighlightIndex = ref(0);
const editorComposing = ref(false);
const uploadFiles = ref([]);
const inputFocused = ref(false);
const isDragging = ref(false);
const {
  rememberCurrentChatSessionComposerState,
  applyChatSessionComposerState,
  clearCurrentChatSessionComposerState,
} = useProjectChatComposer({
  selectedProjectId,
  currentChatSessionId,
  draftText,
  uploadFiles,
  activeComposerAssist,
  singleRoundAnswerOnly,
  slashCommandHighlightIndex,
  getCacheKey: chatSessionMessageCacheKey,
});

const currentSlashDraftState = computed(() =>
  parseSlashCommandDraft(draftText.value),
);
const filteredSlashCommands = computed(() => {
  const state = currentSlashDraftState.value;
  if (!state?.isCommandPhase) return [];
  const query = String(state.query || "").trim();
  if (!query) {
    return composerSlashCommands.value;
  }
  return composerSlashCommands.value.filter((item) => {
    const haystacks = [
      item.command,
      ...(Array.isArray(item.aliases) ? item.aliases : []),
      item.label,
      item.description,
    ]
      .map((value) => normalizeSlashCommandToken(value))
      .filter(Boolean);
    return haystacks.some((value) => value.includes(query));
  });
});
const isSlashCommandMenuVisible = computed(() =>
  Boolean(
    inputFocused.value &&
    currentSlashDraftState.value?.isCommandPhase &&
    filteredSlashCommands.value.length,
  ),
);

watch(
  () => filteredSlashCommands.value.map((item) => item.id).join("|"),
  () => {
    slashCommandHighlightIndex.value = 0;
  },
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
const CHAT_BOTTOM_STICKY_THRESHOLD = 72;

let autoSaveTimer = null;
let lastAutoSavedFingerprint = "";
let highlightedMessageTimer = null;
let messageListResizeObserver = null;
let pendingScrollToBottomFrame = null;
const shouldStickMessagesToBottom = ref(true);
const CHAT_HISTORY_PAGE_SIZE = 120;
const chatHistoryLoadedCount = ref(0);
const chatHistoryLoading = ref(false);
const chatHistoryLoadingMore = ref(false);
const chatHistoryReachedEnd = ref(false);
let activeChatHistoryLoadingKey = "";
const AGENTIC_OPERATION_TOOL_NAMES = ["project_host_run_command"];

const ACTIONABLE_OPERATION_HINT_RE =
  /(帮我|替我|给我|你来|请你|直接|现在|马上|代办|执行|运行|跑一下|检查|检测|查一下|查询一下|查看一下|创建|修改|更新|修复|部署|安装|登录|登陆|授权|认证|鉴权|发送|发一条|同步|拉取|提交|构建|测试|验证)/i;
const ACTIONABLE_OPERATION_TARGET_RE =
  /(lark-cli|飞书|feishu|lark|终端|命令|脚本|接口|api|数据库|文件|项目|代码|git|npm|pnpm|yarn|uv|python|docker|登录|登陆|授权|认证|鉴权|oauth|auth|login|sign in)/i;
const EXPLANATION_ONLY_OPERATION_RE =
  /(怎么|如何|怎样|教程|步骤|说明|文档|用法|命令是什么|应该怎么|how\s+to|what\s+command|docs?|guide|manual)/i;
const IMPERATIVE_OPERATION_RE =
  /(帮我|替我|你来|请你|直接|现在|马上|代办|执行|运行|跑一下|登录一下|登陆一下|授权一下|检查一下|检测一下|处理一下|做一下)/i;
const LARK_OPERATION_RE = /(lark-cli|飞书|feishu|\blark\b)/i;

function rememberRemotePersistedChatRuntime(projectId, chatSessionId, payload) {
  lastChatRuntimeRemotePersistKey = chatRuntimeStorageKey(
    projectId,
    chatSessionId,
  );
  lastChatRuntimeRemotePersistFingerprint = chatRuntimeRemoteFingerprint(
    projectId,
    chatSessionId,
    payload,
  );
}

function clearRemotePersistedChatRuntimeState(projectId, chatSessionId = "") {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId) {
    lastChatRuntimeRemotePersistKey = "";
    lastChatRuntimeRemotePersistFingerprint = "";
    return;
  }
  if (normalizedChatSessionId) {
    const key = chatRuntimeStorageKey(
      normalizedProjectId,
      normalizedChatSessionId,
    );
    if (lastChatRuntimeRemotePersistKey === key) {
      lastChatRuntimeRemotePersistKey = "";
      lastChatRuntimeRemotePersistFingerprint = "";
    }
    return;
  }
  const prefix = `project_chat_runtime_${normalizedProjectId}_`;
  if (lastChatRuntimeRemotePersistKey.startsWith(prefix)) {
    lastChatRuntimeRemotePersistKey = "";
    lastChatRuntimeRemotePersistFingerprint = "";
  }
}

function chatSessionMessageCacheKey(projectId, chatSessionId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return "";
  return `${normalizedProjectId}:${normalizedChatSessionId}`;
}

function isCurrentChatSession(projectId, chatSessionId) {
  return (
    String(projectId || "").trim() ===
      String(selectedProjectId.value || "").trim() &&
    String(chatSessionId || "").trim() ===
      String(currentChatSessionId.value || "").trim()
  );
}

function rememberChatSessionMessages(projectId, chatSessionId, rows) {
  const key = chatSessionMessageCacheKey(projectId, chatSessionId);
  if (!key || !Array.isArray(rows)) return;
  chatSessionMessageCache.set(key, rows);
}

function rememberCurrentChatSessionMessages() {
  const projectId = String(selectedProjectId.value || "").trim();
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  if (!projectId || !chatSessionId) return;
  rememberChatSessionMessages(projectId, chatSessionId, messages.value);
}

function getRememberedChatSessionMessages(projectId, chatSessionId) {
  const key = chatSessionMessageCacheKey(projectId, chatSessionId);
  if (!key) return null;
  const rows = chatSessionMessageCache.get(key);
  return Array.isArray(rows) ? rows : null;
}

function isNativeExternalAgentRunningForChatSession(chatSessionId) {
  const normalizedSessionId = String(chatSessionId || "").trim();
  if (!normalizedSessionId) return false;
  if (
    nativeExternalAgentBackgroundedChatSessionIds.value.has(normalizedSessionId)
  ) {
    return false;
  }
  if (
    nativeExternalAgentLaunchingChatSessionIds.value.has(normalizedSessionId)
  ) {
    return true;
  }
  const runnerSessionId =
    getNativeExternalAgentRunnerSessionIdForChatSession(normalizedSessionId);
  const snapshot = runnerSessionId
    ? nativeExternalAgentSessionsById.get(runnerSessionId)
    : null;
  if (snapshot) {
    return isLiveNativeExternalAgentStatus(snapshot.status);
  }
  return (
    String(nativeExternalAgentChatSessionId.value || "").trim() ===
      normalizedSessionId &&
    isLiveNativeExternalAgentStatus(nativeExternalAgentSession.value?.status)
  );
}

function isChatSessionBusy(chatSessionId = currentChatSessionId.value) {
  const normalizedSessionId = String(chatSessionId || "").trim();
  if (!normalizedSessionId) return false;
  return (
    hasPendingRequestForChatSession(normalizedSessionId) ||
    (isExternalAgentMode.value &&
      isNativeExternalAgentRunningForChatSession(normalizedSessionId))
  );
}

function syncChatLoadingWithCurrentSession() {
  chatLoading.value = isChatSessionBusy();
}

function buildRuntimePayloadForRows(rows) {
  return {
    version: 1,
    updated_at: new Date().toISOString(),
    messages: (Array.isArray(rows) ? rows : [])
      .map(normalizeRuntimeMessageSnapshot)
      .filter(Boolean),
  };
}

function persistRememberedChatSessionMessages(projectId, chatSessionId) {
  const rows = isCurrentChatSession(projectId, chatSessionId)
    ? messages.value
    : getRememberedChatSessionMessages(projectId, chatSessionId);
  if (!Array.isArray(rows) || !rows.length) return;
  const payload = isCurrentChatSession(projectId, chatSessionId)
    ? buildPersistedChatRuntimePayload()
    : buildRuntimePayloadForRows(rows);
  writePersistedChatRuntime(projectId, chatSessionId, payload);
  void persistChatRuntimeToServer(projectId, chatSessionId, payload);
}

function resolvePendingRequestRow(pending) {
  if (!pending) return null;
  const projectId = String(
    pending.projectId || selectedProjectId.value || "",
  ).trim();
  const chatSessionId = String(
    pending.chatSessionId || currentChatSessionId.value || "",
  ).trim();
  const rows = isCurrentChatSession(projectId, chatSessionId)
    ? messages.value
    : getRememberedChatSessionMessages(projectId, chatSessionId);
  if (!Array.isArray(rows)) return null;
  const assistantMessageId = String(pending.assistantMessageId || "").trim();
  if (assistantMessageId) {
    const matched = rows.find(
      (item) => String(item?.id || "").trim() === assistantMessageId,
    );
    if (matched) return matched;
  }
  return rows[Number(pending.assistantIndex ?? -1)] || null;
}

function readPersistedChatRuntime(projectId, chatSessionId) {
  return readLocalPersistedChatRuntime(projectId, chatSessionId);
}

function writePersistedChatRuntime(projectId, chatSessionId, payload) {
  writeLocalPersistedChatRuntime(projectId, chatSessionId, payload);
}

function clearPersistedChatRuntime(projectId, chatSessionId = "") {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedProjectId) return;
  clearRemotePersistedChatRuntimeState(
    normalizedProjectId,
    normalizedChatSessionId,
  );
  clearLocalPersistedChatRuntime(normalizedProjectId, normalizedChatSessionId);
}

async function fetchPersistedChatRuntime(projectId, chatSessionId) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  const localPayload = readPersistedChatRuntime(
    normalizedProjectId,
    normalizedChatSessionId,
  );
  if (!normalizedProjectId || !normalizedChatSessionId) {
    return localPayload;
  }
  try {
    const data = await api.get(
      `/projects/${encodeURIComponent(normalizedProjectId)}/chat/runtime`,
      {
        params: {
          chat_session_id: normalizedChatSessionId,
        },
      },
    );
    const payload =
      data?.snapshot?.payload && typeof data.snapshot.payload === "object"
        ? data.snapshot.payload
        : null;
    if (payload) {
      writePersistedChatRuntime(
        normalizedProjectId,
        normalizedChatSessionId,
        payload,
      );
      rememberRemotePersistedChatRuntime(
        normalizedProjectId,
        normalizedChatSessionId,
        payload,
      );
      return payload;
    }
  } catch (_error) {
    // 服务端快照读取失败时保留本地兜底，不中断聊天恢复。
  }
  return localPayload;
}

async function persistChatRuntimeToServer(projectId, chatSessionId, payload) {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (
    !normalizedProjectId ||
    !normalizedChatSessionId ||
    !payload ||
    typeof payload !== "object"
  ) {
    return;
  }
  const key = chatRuntimeStorageKey(
    normalizedProjectId,
    normalizedChatSessionId,
  );
  const fingerprint = chatRuntimeRemoteFingerprint(
    normalizedProjectId,
    normalizedChatSessionId,
    payload,
  );
  if (
    key &&
    key === lastChatRuntimeRemotePersistKey &&
    fingerprint &&
    fingerprint === lastChatRuntimeRemotePersistFingerprint
  ) {
    return;
  }
  try {
    await api.put(
      `/projects/${encodeURIComponent(normalizedProjectId)}/chat/runtime`,
      {
        chat_session_id: normalizedChatSessionId,
        payload,
      },
    );
    rememberRemotePersistedChatRuntime(
      normalizedProjectId,
      normalizedChatSessionId,
      payload,
    );
  } catch (_error) {
    // 服务端持久化失败时保留本地快照，避免阻塞当前交互。
  }
}

function normalizeRuntimeMessageSnapshot(row) {
  if (!row || typeof row !== "object") return null;
  const id = String(row.id || "").trim();
  if (!id) return null;
  return {
    id,
    role: String(row.role || "assistant"),
    content: String(row.content || ""),
    images: Array.isArray(row.images) ? row.images.slice() : [],
    videos: Array.isArray(row.videos) ? row.videos.slice() : [],
    attachments: Array.isArray(row.attachments) ? row.attachments.slice() : [],
    time: String(row.time || ""),
    displayMode: String(row.displayMode || ""),
    effectiveTools: Array.isArray(row.effectiveTools)
      ? row.effectiveTools.slice()
      : [],
    effectiveToolTotal: Number(row.effectiveToolTotal || 0),
    terminalLog: Array.isArray(row.terminalLog) ? row.terminalLog.slice() : [],
    processExpanded: Boolean(row.processExpanded),
    audit: row.audit && typeof row.audit === "object" ? row.audit : null,
    taskTreeAudit:
      row.taskTreeAudit && typeof row.taskTreeAudit === "object"
        ? row.taskTreeAudit
        : null,
    processLog: Array.isArray(row.processLog) ? row.processLog.slice() : [],
    statusNotes: Array.isArray(row.statusNotes) ? row.statusNotes.slice() : [],
    operations: Array.isArray(row.operations) ? row.operations.slice() : [],
    source_context:
      row.source_context && typeof row.source_context === "object"
        ? row.source_context
        : row.sourceContext && typeof row.sourceContext === "object"
          ? row.sourceContext
          : null,
  };
}

function buildNativeExternalAgentRuntimeSnapshotForSession(sessionId = "") {
  const normalizedSessionId = normalizeNativeExternalAgentSessionId(sessionId);
  if (!normalizedSessionId) return null;
  const snapshot = nativeExternalAgentSessionsById.get(normalizedSessionId);
  if (!snapshot) return null;
  return normalizeNativeExternalAgentRuntimeSnapshot({
    session_id: normalizedSessionId,
    chat_session_id:
      getNativeExternalAgentChatSessionIdForRunnerSession(normalizedSessionId),
    message_id:
      getNativeExternalAgentMessageIdForRunnerSession(normalizedSessionId),
    running: isLiveNativeExternalAgentStatus(snapshot.status),
    session: snapshot,
    logs: getNativeExternalAgentSessionLogs(normalizedSessionId).slice(-500),
  });
}

function buildNativeExternalAgentRuntimeSnapshotForChatSession(
  chatSessionId = "",
) {
  const runnerSessionId =
    getNativeExternalAgentRunnerSessionIdForChatSession(chatSessionId);
  if (runnerSessionId) {
    return buildNativeExternalAgentRuntimeSnapshotForSession(runnerSessionId);
  }
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (
    normalizedChatSessionId &&
    String(nativeExternalAgentChatSessionId.value || "").trim() ===
      normalizedChatSessionId
  ) {
    return normalizeNativeExternalAgentRuntimeSnapshot({
      session_id: String(
        nativeExternalAgentSession.value?.sessionId || "",
      ).trim(),
      chat_session_id: normalizedChatSessionId,
      message_id: String(nativeExternalAgentMessageId.value || "").trim(),
      running: isLiveNativeExternalAgentStatus(
        nativeExternalAgentSession.value?.status,
      ),
      session:
        nativeExternalAgentSession.value &&
        typeof nativeExternalAgentSession.value === "object"
          ? nativeExternalAgentSession.value
          : null,
      logs: Array.isArray(nativeExternalAgentSessionLogs.value)
        ? nativeExternalAgentSessionLogs.value.slice(-500)
        : [],
    });
  }
  return null;
}

function listNativeExternalAgentRuntimeSnapshotsForCurrentProject() {
  return Array.from(nativeExternalAgentSessionsById.keys())
    .map((sessionId) =>
      buildNativeExternalAgentRuntimeSnapshotForSession(sessionId),
    )
    .filter(Boolean);
}

function buildPersistedChatRuntimePayload() {
  const activeIndex = Number(activeTerminalMirrorAssistantIndex.value ?? -1);
  const activeRow =
    activeIndex >= 0 && activeIndex < messages.value.length
      ? messages.value[activeIndex]
      : null;
  return {
    version: 1,
    updated_at: new Date().toISOString(),
    messages: (messages.value || [])
      .map(normalizeRuntimeMessageSnapshot)
      .filter(Boolean),
    terminal: {
      panel_status: String(terminalPanelStatus.value || "idle"),
      panel_expanded: Boolean(terminalPanelExpanded.value),
      panel_lines: Array.isArray(terminalPanelLines.value)
        ? terminalPanelLines.value.slice(-400)
        : [],
      mirror_connected: Boolean(terminalMirrorConnected.value),
      host_terminal_session_id: String(
        hostTerminalSessionId.value || "",
      ).trim(),
      host_terminal_workspace_path: String(
        hostTerminalWorkspacePath.value || "",
      ).trim(),
      active_assistant_index: activeIndex,
      active_assistant_message_id: String(activeRow?.id || "").trim(),
    },
    native_external_agent:
      buildNativeExternalAgentRuntimeSnapshotForChatSession(
        currentChatSessionId.value,
      ),
    native_external_agents:
      listNativeExternalAgentRuntimeSnapshotsForCurrentProject(),
  };
}

function shouldKeepRuntimeOnlyMessage(row) {
  if (!row) return false;
  if (String(row.displayMode || "").trim() === "external-agent-waiting") {
    return true;
  }
  if (resolveNativeExternalAgentSessionIdFromMessage(row)) return true;
  if (isTerminalInputCandidateRow(row)) return true;
  if (Array.isArray(row.terminalLog) && row.terminalLog.length) return true;
  if (Array.isArray(row.operations) && row.operations.length) return true;
  return String(row.displayMode || "").trim() === "terminal";
}

function applyPersistedChatRuntimeRows(historyRows, runtimePayload) {
  const rows = Array.isArray(historyRows) ? historyRows : [];
  const runtimeRows = Array.isArray(runtimePayload?.messages)
    ? runtimePayload.messages
        .map(normalizeRuntimeMessageSnapshot)
        .filter(Boolean)
    : [];
  if (!runtimeRows.length) return rows;
  const runtimeById = new Map(runtimeRows.map((item) => [item.id, item]));
  const historyIds = new Set(rows.map((row) => String(row?.id || "").trim()));
  const mergedRows = rows.map((row) => {
    const runtimeRow = runtimeById.get(String(row?.id || "").trim());
    return runtimeRow ? { ...row, ...runtimeRow } : row;
  });
  const keepRuntimeOnlyIds = new Set();
  runtimeRows.forEach((row, index) => {
    const id = String(row?.id || "").trim();
    if (!id || !shouldKeepRuntimeOnlyMessage(row)) return;
    keepRuntimeOnlyIds.add(id);
    const previousRow = runtimeRows[index - 1];
    const previousId = String(previousRow?.id || "").trim();
    if (previousId && String(previousRow?.role || "").trim() === "user") {
      keepRuntimeOnlyIds.add(previousId);
    }
  });
  const runtimeOnlyRows = runtimeRows.filter((row) => {
    const id = String(row?.id || "").trim();
    return id && !historyIds.has(id) && keepRuntimeOnlyIds.has(id);
  });
  if (mergedRows.length) return [...mergedRows, ...runtimeOnlyRows];
  return runtimeRows;
}

function findNativeExternalAgentRuntimeMessage(runtimeSnapshot = null) {
  const messageId = String(runtimeSnapshot?.message_id || "").trim();
  if (messageId) {
    const matched = messages.value.find(
      (item) => String(item?.id || "").trim() === messageId,
    );
    if (matched) return matched;
  }
  const sessionId = String(runtimeSnapshot?.session_id || "").trim();
  if (sessionId) {
    const matched = messages.value.find(
      (item) =>
        item?.role !== "user" &&
        resolveNativeExternalAgentSessionIdFromMessage(item) === sessionId,
    );
    if (matched) return matched;
  }
  return (
    [...messages.value]
      .reverse()
      .find(
        (item) =>
          item?.role !== "user" &&
          (String(item?.displayMode || "").trim() ===
            "external-agent-waiting" ||
            resolveNativeExternalAgentSessionIdFromMessage(item)),
      ) || null
  );
}

async function restoreNativeExternalAgentRuntime(
  projectId,
  chatSessionId,
  runtimePayload,
) {
  const activeProjectId = String(selectedProjectId.value || "").trim();
  const activeChatSessionId = String(currentChatSessionId.value || "").trim();
  if (
    String(projectId || "").trim() !== activeProjectId ||
    String(chatSessionId || "").trim() !== activeChatSessionId
  ) {
    return;
  }
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (!nativeDesktopBridgeAvailable.value) return;
  const runtimeSnapshots = [
    ...(Array.isArray(runtimePayload?.native_external_agents)
      ? runtimePayload.native_external_agents
      : []),
    runtimePayload?.native_external_agent,
  ]
    .map(normalizeNativeExternalAgentRuntimeSnapshot)
    .filter(Boolean)
    .filter((item, index, list) => {
      const sessionId = String(item.session_id || "").trim();
      if (!sessionId) return false;
      return (
        list.findIndex(
          (candidate) =>
            String(candidate?.session_id || "").trim() === sessionId,
        ) === index
      );
    })
    .filter((item) => {
      const snapshotChatSessionId = String(item.chat_session_id || "").trim();
      return (
        !snapshotChatSessionId || snapshotChatSessionId === activeChatSessionId
      );
    });
  for (const runtimeSnapshot of runtimeSnapshots) {
    rememberNativeExternalAgentSessionBinding({
      sessionId: runtimeSnapshot.session_id,
      chatSessionId: activeChatSessionId,
      messageId: runtimeSnapshot.message_id,
    });
    if (runtimeSnapshot.logs.length) {
      nativeExternalAgentSessionLogsById.set(
        runtimeSnapshot.session_id,
        runtimeSnapshot.logs.slice(-500),
      );
    }
    if (runtimeSnapshot.session) {
      nativeExternalAgentSessionsById.set(
        runtimeSnapshot.session_id,
        runtimeSnapshot.session,
      );
    }
    const restoredMessage =
      findNativeExternalAgentRuntimeMessage(runtimeSnapshot);
    const restoredSessionId =
      String(runtimeSnapshot?.session_id || "").trim() ||
      resolveNativeExternalAgentSessionIdFromMessage(restoredMessage);
    if (!restoredSessionId || !restoredMessage) continue;
    rememberNativeExternalAgentSessionBinding({
      sessionId: restoredSessionId,
      chatSessionId: activeChatSessionId,
      messageId: restoredMessage.id,
    });
    syncNativeExternalAgentSessionPanel(restoredSessionId);

    let snapshot = null;
    try {
      snapshot = await getNativeExternalAgentSession({
        sessionId: restoredSessionId,
        sinceSeq: 0,
      });
    } catch (err) {
      console.warn("restore native external agent session failed", err);
    }
    if (snapshot?.sessionId) {
      applyNativeExternalAgentSessionSnapshot(snapshot, {
        chatSessionId: activeChatSessionId,
        messageId: restoredMessage.id,
        select: true,
      });
      upsertNativeExternalAgentMessageOperation(snapshot);
      if (snapshot.status === "running" || snapshot.status === "cancelling") {
        restoredMessage.displayMode =
          snapshot.status === "running"
            ? String(restoredMessage.displayMode || "").trim() ||
              "external-agent-waiting"
            : "";
        if (snapshot.status === "cancelling") {
          restoredMessage.content =
            String(restoredMessage.content || "").trim() ||
            "正在取消外部 Agent Runner 会话。";
          completeNativeExternalAgentRunningOperations(
            restoredSessionId,
            "外部 Agent Runner 会话正在取消",
          );
        }
        syncChatLoadingWithCurrentSession();
        void pollNativeExternalAgentSession(restoredSessionId);
        continue;
      }
      releaseNativeExternalAgentTurnIfTerminal(
        restoredSessionId,
        activeChatSessionId,
        snapshot,
      );
      syncChatLoadingWithCurrentSession();
      completeNativeExternalAgentRunningOperations(
        restoredSessionId,
        "外部 Agent Runner 会话已结束",
      );
      finalizeNativeExternalAgentMessage(snapshot, activeChatSessionId);
      continue;
    }

    if (runtimeSnapshot?.running) {
      const unavailableSnapshot = buildUnavailableNativeExternalAgentSnapshot(
        restoredSessionId,
        "外部 Agent Runner 会话状态不可确认，已停止恢复为进行中",
      );
      applyNativeExternalAgentSessionSnapshot(unavailableSnapshot, {
        chatSessionId: activeChatSessionId,
        messageId: restoredMessage.id,
        select: true,
      });
      upsertNativeExternalAgentMessageOperation(unavailableSnapshot);
      restoredMessage.displayMode = "";
      restoredMessage.content =
        String(restoredMessage.content || "").trim() ||
        "外部 Agent Runner 会话状态不可确认，已停止恢复为进行中。";
      releaseNativeExternalAgentTurnIfTerminal(
        restoredSessionId,
        activeChatSessionId,
        unavailableSnapshot,
      );
      syncChatLoadingWithCurrentSession();
      completeNativeExternalAgentRunningOperations(
        restoredSessionId,
        "外部 Agent Runner 会话状态不可确认，已停止恢复为进行中",
      );
      schedulePersistChatRuntime();
    }
  }
  syncNativeExternalAgentSessionPanel();
  syncChatLoadingWithCurrentSession();
}

async function restoreInteractiveChatRuntime(
  projectId,
  chatSessionId,
  rows,
  runtimePayload,
) {
  const activeProjectId = String(selectedProjectId.value || "").trim();
  const activeChatSessionId = String(currentChatSessionId.value || "").trim();
  if (
    String(projectId || "").trim() !== activeProjectId ||
    String(chatSessionId || "").trim() !== activeChatSessionId
  ) {
    return;
  }
  const terminal =
    runtimePayload?.terminal && typeof runtimePayload.terminal === "object"
      ? runtimePayload.terminal
      : null;
  if (!terminal) return;
  const restoredPanelStatus = String(terminal.panel_status || "idle").trim();
  terminalPanelStatus.value =
    restoredPanelStatus === "running" ? "idle" : restoredPanelStatus;
  terminalPanelExpanded.value = Boolean(terminal.panel_expanded);
  terminalPanelLines.value = Array.isArray(terminal.panel_lines)
    ? terminal.panel_lines.slice(-400)
    : [];
  terminalMirrorConnected.value = false;
  hostTerminalSessionId.value = "";
  hostTerminalWorkspacePath.value = String(
    terminal.host_terminal_workspace_path || "",
  ).trim();
  activeTerminalMirrorAssistantIndex.value = -1;
  await restoreNativeExternalAgentRuntime(
    projectId,
    chatSessionId,
    runtimePayload,
  );
  await nextTick();
  scrollTerminalPanelBottom();
}

function schedulePersistChatRuntime() {
  const projectId = String(selectedProjectId.value || "").trim();
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  if (!projectId || !chatSessionId) return;
  if (chatRuntimePersistTimer) {
    clearTimeout(chatRuntimePersistTimer);
  }
  chatRuntimePersistTimer = window.setTimeout(() => {
    chatRuntimePersistTimer = null;
    const activeProjectId = String(selectedProjectId.value || "").trim();
    const activeChatSessionId = String(currentChatSessionId.value || "").trim();
    if (
      activeProjectId !== projectId ||
      activeChatSessionId !== chatSessionId
    ) {
      return;
    }
    persistCurrentChatRuntimeNow(projectId, chatSessionId);
  }, 300);
}

function persistCurrentChatRuntimeNow(projectId = "", chatSessionId = "") {
  const normalizedProjectId = String(
    projectId || selectedProjectId.value || "",
  ).trim();
  const normalizedChatSessionId = String(
    chatSessionId || currentChatSessionId.value || "",
  ).trim();
  if (!normalizedProjectId || !normalizedChatSessionId) return;
  if (!isCurrentChatSession(normalizedProjectId, normalizedChatSessionId))
    return;
  if (chatRuntimePersistTimer) {
    clearTimeout(chatRuntimePersistTimer);
    chatRuntimePersistTimer = null;
  }
  const payload = buildPersistedChatRuntimePayload();
  writePersistedChatRuntime(
    normalizedProjectId,
    normalizedChatSessionId,
    payload,
  );
  void persistChatRuntimeToServer(
    normalizedProjectId,
    normalizedChatSessionId,
    payload,
  );
}

const chatHistoryHasMore = computed(() => {
  if (chatHistoryReachedEnd.value) return false;
  const total = Number(currentChatSession.value?.message_count || 0);
  if (total > 0) {
    return chatHistoryLoadedCount.value < total;
  }
  return chatHistoryLoadedCount.value >= CHAT_HISTORY_PAGE_SIZE;
});

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
    const projectId = String(selectedProjectId.value || "").trim();
    if (!projectId) {
      throw new Error("WebSocket 未连接");
    }
    await ensureWsClient(projectId);
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
    const projectId = String(selectedProjectId.value || "").trim();
    if (!projectId) {
      throw new Error("WebSocket 未连接");
    }
    await ensureWsClient(projectId);
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
  upsertMessageOperation(row, {
    operationId: `approval:${approvalId}`,
    kind: "approval",
    title: String(eventData?.title || "操作审批").trim() || "操作审批",
    summary: "等待你确认后继续",
    detail: formatApprovalMessage(eventData),
    phase: "waiting_user",
    actionType: "approve",
    meta: {
      request_id: requestId,
      approval_id: approvalId,
      message: String(eventData?.message || "").trim(),
      risk_signals: Array.isArray(eventData?.risk_signals)
        ? eventData.risk_signals
        : [],
    },
  });
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
  upsertMessageOperation(row, {
    operationId: `review:${reviewId}`,
    kind: "approval",
    title: String(eventData?.title || "文件变更审查").trim() || "文件变更审查",
    summary: "等待你确认是否保留当前改动",
    detail: formatFileReviewMessage(eventData),
    phase: "waiting_user",
    actionType: "approve",
    meta: {
      request_id: requestId,
      review_id: reviewId,
      diff_summary:
        eventData?.diff_summary && typeof eventData.diff_summary === "object"
          ? eventData.diff_summary
          : null,
      message: String(eventData?.message || "").trim(),
    },
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
    execution_mode: String(source.execution_mode || "local").trim() || "local",
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
      local_connector: "旧版本地连接器",
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
      local_connector: "info",
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
  const autoUseToolsExplicit = Boolean(source.auto_use_tools_explicit);
  return {
    ...CHAT_SETTINGS_DEFAULTS,
    ...source,
    chat_mode:
      chatMode === "external_agent" || chatMode === "system"
        ? chatMode
        : CHAT_SETTINGS_DEFAULTS.chat_mode,
    external_agent_type: String(
      source.external_agent_type || CHAT_SETTINGS_DEFAULTS.external_agent_type,
    ).trim(),
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
    auto_use_tools_explicit: autoUseToolsExplicit,
    auto_use_tools: autoUseToolsExplicit
      ? coerceBooleanSetting(
          source.auto_use_tools,
          CHAT_SETTINGS_DEFAULTS.auto_use_tools,
        )
      : false,
    image_generate_four_views: coerceBooleanSetting(
      source.image_generate_four_views,
      CHAT_SETTINGS_DEFAULTS.image_generate_four_views,
    ),
    task_tree_enabled: coerceBooleanSetting(
      source.task_tree_enabled,
      CHAT_SETTINGS_DEFAULTS.task_tree_enabled,
    ),
    task_tree_auto_generate: coerceBooleanSetting(
      source.task_tree_auto_generate,
      CHAT_SETTINGS_DEFAULTS.task_tree_auto_generate,
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

function resolveNumericChatSetting(
  value,
  fallback,
  { min = 0, max = null } = {},
) {
  const parsed = Number(value);
  const fallbackValue = Number(fallback);
  const safeFallback = Number.isFinite(fallbackValue) ? fallbackValue : 0;
  const base = Number.isFinite(parsed) ? parsed : safeFallback;
  if (Number.isFinite(min) && base < min) {
    return min;
  }
  if (Number.isFinite(max) && base > max) {
    return max;
  }
  return base;
}

function projectChatToolsExplicitlyEnabled() {
  return Boolean(projectChatSettings.value.auto_use_tools_explicit)
    ? Boolean(projectChatSettings.value.auto_use_tools)
    : false;
}

function normalizeChatSelectedEmployeeIds(
  selectedIds,
  availableEmployeeIds = [],
) {
  const available = normalizeStringList(availableEmployeeIds || [], 200);
  const validSelected = normalizeStringList(selectedIds || [], 200).filter(
    (id) => !available.length || available.includes(id),
  );
  if (!validSelected.length || !available.length) {
    return validSelected;
  }
  return validSelected.length >= available.length ? [] : validSelected;
}

function formatCompactSessionId(value) {
  const normalized = String(value || "").trim();
  if (!normalized || normalized.length <= 22) {
    return normalized;
  }
  return `${normalized.slice(0, 14)}...${normalized.slice(-6)}`;
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
  if (isTerminalInteractionMode.value) {
    return Boolean(
      String(draftText.value || "").trim() || hasLiveTerminalSession.value,
    );
  }
  if (hasSelectedProject.value && !isChatSettingsDisplayReady.value) {
    return false;
  }
  if (
    isExternalAgentMode.value &&
    isNativeExternalAgentRunningForChatSession(currentChatSessionId.value)
  ) {
    return false;
  }
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
  if (isTerminalInteractionMode.value) return false;
  if (isProjectOptionalEmployeeCreate.value) return false;
  if (hasSelectedProject.value && !isChatSettingsDisplayReady.value) {
    return true;
  }
  if (!ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT) {
    return !selectedProjectId.value;
  }
  return false;
});

function formatContent(text) {
  const displayText = stripInternalProtocolContentForDisplay(
    stripEmployeeDraftBlock(text),
  );
  if (!displayText) return "";
  try {
    return renderProjectChatMarkdown(displayText);
  } catch (e) {
    return displayText;
  }
}

function stripInternalProtocolContentForDisplay(text) {
  let output = String(text || "");
  if (!output) return "";
  output = output
    .replace(
      /<\uFF5C\uFF5CDSML\uFF5C\uFF5Ctool_calls\b[^>]*>[\s\S]*?<\/\uFF5C\uFF5CDSML\uFF5C\uFF5Ctool_calls>/gi,
      "",
    )
    .replace(
      /<(tool_call|tool_calls|tool_result|function_call|function_calls)\b[^>]*>[\s\S]*?<\/\1>/gi,
      "",
    )
    .replace(
      /(^|[\n\r.!?:])[ \t]*<function\b[^>]*\bname\s*=[^>]*>[\s\S]*?<\/function>/gi,
      "$1",
    );
  const harmonyMatch = output.match(
    /(?:^|[\s>|])to=functions\.[A-Za-z_][\w.]*/i,
  );
  if (harmonyMatch && typeof harmonyMatch.index === "number") {
    const prefix = output.slice(0, harmonyMatch.index).trim();
    output = ["assistant", "commentary", "<|channel|>commentary"].includes(
      prefix.toLowerCase(),
    )
      ? ""
      : prefix;
  }
  return output.trim();
}

function extractFormJsonCodeBlocks(text) {
  const blocks = [];
  const pattern = /```([^\n`]*)\n([\s\S]*?)```/g;
  for (const match of String(text || "").matchAll(pattern)) {
    const language = normalizeCodeLanguage(match?.[1] || "");
    if (!["form-json", "formjson", "element-easy-form"].includes(language)) {
      continue;
    }
    const content = String(match?.[2] || "").trim();
    if (content) blocks.push(content);
  }
  return blocks;
}

function normalizeFormJsonArtifact(rawJson) {
  let parsed = null;
  try {
    parsed = JSON.parse(String(rawJson || "").trim());
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const model =
    parsed.model &&
    typeof parsed.model === "object" &&
    !Array.isArray(parsed.model)
      ? parsed.model
      : {};
  const schema = Array.isArray(parsed.schema) ? parsed.schema : [];
  if (!schema.length) return null;
  const formJson = reactive({
    model,
    formAttrs:
      parsed.formAttrs && typeof parsed.formAttrs === "object"
        ? parsed.formAttrs
        : { "label-position": "top", "status-icon": true },
    rowAttrs:
      parsed.rowAttrs && typeof parsed.rowAttrs === "object"
        ? parsed.rowAttrs
        : { gutter: 16 },
    schema,
  });
  return {
    formJson,
    rawText: JSON.stringify(
      {
        model,
        formAttrs:
          parsed.formAttrs && typeof parsed.formAttrs === "object"
            ? parsed.formAttrs
            : { "label-position": "top", "status-icon": true },
        rowAttrs:
          parsed.rowAttrs && typeof parsed.rowAttrs === "object"
            ? parsed.rowAttrs
            : { gutter: 16 },
        schema,
      },
      null,
      2,
    ),
  };
}

function getFormJsonArtifactCacheKey(item, block, index) {
  const messageKey = String(
    item?.id || item?.created_at || item?.time || "",
  ).trim();
  if (messageKey) return `${messageKey}:${index}:${block}`;
  return `${String(item?.role || "assistant")}:${index}:${block}`;
}

function formJsonArtifactsForMessage(item) {
  if (String(item?.role || "").trim() === "user") return [];
  return extractFormJsonCodeBlocks(item?.content)
    .map((block, index) => {
      const cacheKey = getFormJsonArtifactCacheKey(item, block, index);
      const cached = formJsonArtifactCache.get(cacheKey);
      if (cached) return cached;
      const artifact = normalizeFormJsonArtifact(block);
      if (artifact) {
        formJsonArtifactCache.set(cacheKey, artifact);
      }
      return artifact;
    })
    .filter(Boolean)
    .map((artifact, index) => ({
      ...artifact,
      title: index === 0 ? "表单数据预览" : `表单数据预览 ${index + 1}`,
      fieldCount: artifact.formJson.schema.length,
    }));
}

async function copyFormJsonArtifact(artifact) {
  const formJson = artifact?.formJson;
  const content = formJson
    ? JSON.stringify(formJson, null, 2)
    : String(artifact?.rawText || "").trim();
  if (!content) {
    ElMessage.warning("当前表单 JSON 无法复制");
    return;
  }
  try {
    await writeClipboardText(content);
    ElMessage.success("已复制表单 JSON");
  } catch {
    ElMessage.error("复制失败");
  }
}

function scrollTerminalPanelBottom() {
  nextTick(() => {
    if (terminalPanelRef.value) {
      terminalPanelRef.value.scrollTop = terminalPanelRef.value.scrollHeight;
    }
  });
}

function focusTerminalPanelInput() {
  if (!isTerminalInteractionMode.value) return;
  void focusChatComposerTextarea();
}

function pickAwaitingInteractionOperation(row, options = {}) {
  if (!row) return null;
  const operations = [...messageOperations(row)].reverse().filter((item) => {
    if (!isOperationAwaitingInteraction(item)) return false;
    if (options?.allowTerminal !== false) return true;
    const actionType = normalizeOperationActionType(item?.actionType);
    const kind = String(item?.kind || "")
      .trim()
      .toLowerCase();
    return actionType !== "enter_text" && kind !== "terminal";
  });
  if (!operations.length) return null;
  if (options?.allowTerminal === false) return operations[0];
  if (!hasLiveTerminalSession.value) return operations[0];
  return (
    operations.find((item) => {
      const actionType = normalizeOperationActionType(item?.actionType);
      const kind = String(item?.kind || "")
        .trim()
        .toLowerCase();
      return actionType === "enter_text" || kind === "terminal";
    }) || operations[0]
  );
}

function findLatestAwaitingInteractionMessage(rows) {
  if (!Array.isArray(rows)) return null;
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const row = rows[index];
    if (String(row?.role || "").trim() !== "assistant") continue;
    const operation = pickAwaitingInteractionOperation(row, {
      allowTerminal: false,
    });
    if (operation) return { index, row, operation };
  }
  return null;
}

async function openExternalUrlViaSystem(url) {
  const normalizedUrl = String(url || "").trim();
  if (!normalizedUrl) return false;
  try {
    const response = await api.post("/projects/external-url/open", {
      url: normalizedUrl,
    });
    return Boolean(response?.opened);
  } catch (err) {
    return false;
  }
}

function appendTerminalPanelLine(text) {
  appendTerminalPanelLineState(text);
  scrollTerminalPanelBottom();
}

function clearTerminalPanel() {
  terminalPanelLines.value = [];
  scrollTerminalPanelBottom();
}

function resetTerminalPanel() {
  resetTerminalPanelState();
  clearTerminalApprovalFallback();
  scrollTerminalPanelBottom();
}

async function openWorkspaceDirectory(path = "") {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId || !projectWorkspaceResolved.value) {
    resetWorkspaceFilePanel();
    return;
  }
  workspaceFileTreeLoading.value = true;
  try {
    const data = nativeDesktopBridgeAvailable.value
      ? await listNativeWorkspaceFiles({
          workspacePath: projectWorkspaceResolved.value,
          path: String(path || "").trim(),
        })
      : await listProjectWorkspaceFiles(projectId, path);
    workspaceFileTreePath.value = String(data?.path || "").trim();
    workspaceFileItems.value = Array.isArray(data?.items) ? data.items : [];
    if (nativeDesktopBridgeAvailable.value) {
      void refreshWorkspaceDiffPreview({
        path: activeWorkspaceFilePath.value || "",
      });
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载工作区文件失败");
  } finally {
    workspaceFileTreeLoading.value = false;
  }
}

async function refreshWorkspaceFileTree() {
  await openWorkspaceDirectory(workspaceFileTreePath.value);
}

async function refreshWorkspaceDiffPreview(options = {}) {
  if (!canPreviewWorkspaceDiff.value) {
    workspaceDiffPreview.value = null;
    return;
  }
  const targetPath =
    options?.path === null
      ? ""
      : String(options?.path ?? activeWorkspaceFilePath.value ?? "").trim();
  workspaceDiffLoading.value = true;
  try {
    const data = await previewNativeWorkspaceDiff({
      workspacePath: projectWorkspaceResolved.value,
      path: targetPath,
    });
    workspaceDiffPreview.value = data;
    const summaryLine = String(data?.summary || data?.status || "")
      .split(/\r?\n/)
      .map((item) => item.trim())
      .find(Boolean);
    void recordDesktopAuditEvent({
      event_type: "desktop_workspace_diff_preview",
      step: targetPath ? "预览文件差异" : "预览工作区差异",
      status: data?.available === false ? "unavailable" : "done",
      content: `桌面端只读预览工作区差异${targetPath ? `：${targetPath}` : ""}${
        summaryLine ? ` · ${summaryLine}` : ""
      }`,
      changed_files: targetPath ? [targetPath] : [],
      verification: [
        `available=${data?.available === false ? "false" : "true"}`,
        `truncated=${data?.truncated ? "true" : "false"}`,
        Number.isFinite(Number(data?.exitCode))
          ? `exitCode=${Number(data.exitCode)}`
          : "",
      ].filter(Boolean),
      risks:
        data?.available === false
          ? [String(data?.reason || "").trim()].filter(Boolean)
          : [],
    });
  } catch (err) {
    workspaceDiffPreview.value = {
      available: false,
      reason: err?.message || "读取工作区差异失败",
      summary: "",
      diff: "",
      status: "",
      truncated: false,
    };
    void recordDesktopAuditEvent({
      event_type: "desktop_workspace_diff_preview",
      step: targetPath ? "预览文件差异" : "预览工作区差异",
      status: "failed",
      content: `桌面端工作区差异预览失败${targetPath ? `：${targetPath}` : ""}`,
      changed_files: targetPath ? [targetPath] : [],
      risks: [String(err?.message || "读取工作区差异失败").trim()].filter(
        Boolean,
      ),
    });
  } finally {
    workspaceDiffLoading.value = false;
  }
}

async function openWorkspaceFile(path = "") {
  const projectId = String(selectedProjectId.value || "").trim();
  const normalizedPath = String(path || "").trim();
  if (!projectId || !normalizedPath) return;
  workspaceFileLoading.value = true;
  try {
    const data = nativeDesktopBridgeAvailable.value
      ? await readNativeWorkspaceFile({
          workspacePath: projectWorkspaceResolved.value,
          path: normalizedPath,
        })
      : await readProjectWorkspaceFile(projectId, normalizedPath);
    activeWorkspaceFilePath.value = String(data?.path || normalizedPath).trim();
    workspaceFileDraft.value = String(data?.content || "");
    workspaceFileOriginal.value = workspaceFileDraft.value;
    if (nativeDesktopBridgeAvailable.value) {
      void recordDesktopAuditEvent({
        event_type: "desktop_workspace_file_read",
        step: "只读预览工作区文件",
        status: "done",
        content: `桌面端只读预览工作区文件：${activeWorkspaceFilePath.value}`,
        changed_files: [activeWorkspaceFilePath.value],
        verification: [
          `bytes=${Number(data?.size || workspaceFileDraft.value.length || 0)}`,
          data?.truncated ? "truncated=true" : "truncated=false",
        ],
      });
    }
    if (nativeDesktopBridgeAvailable.value) {
      void refreshWorkspaceDiffPreview({
        path: activeWorkspaceFilePath.value,
      });
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "读取工作区文件失败");
  } finally {
    workspaceFileLoading.value = false;
  }
}

function handleWorkspaceFileClick(item) {
  const itemPath = String(item?.path || "").trim();
  if (!itemPath && String(item?.kind || "") !== "directory") return;
  if (String(item?.kind || "").trim() === "directory") {
    void openWorkspaceDirectory(itemPath);
    return;
  }
  void openWorkspaceFile(itemPath);
}

function workspaceWriteRiskLabel(value) {
  const risk = String(value || "").trim();
  if (risk === "high") return "高风险";
  if (risk === "medium") return "中风险";
  if (risk === "low") return "低风险";
  return "待确认";
}

async function prepareDesktopWorkspaceFileWrite(path) {
  if (!nativeDesktopBridgeAvailable.value) return false;
  const normalizedPath = String(path || "").trim();
  if (!normalizedPath || !projectWorkspaceResolved.value) return false;
  workspaceFileSaving.value = true;
  try {
    const preparation = await prepareNativeWorkspaceFileWrite({
      workspacePath: projectWorkspaceResolved.value,
      path: normalizedPath,
      content: workspaceFileDraft.value,
    });
    const summary = String(preparation?.summary || "").trim();
    const reason = String(preparation?.reason || "").trim();
    const riskLevel = String(preparation?.riskLevel || "medium").trim();
    const changed = Boolean(preparation?.changed);
    const facts = [
      `risk=${riskLevel}`,
      `changed=${changed ? "true" : "false"}`,
      `exists=${preparation?.exists ? "true" : "false"}`,
      `currentSize=${Number(preparation?.currentSize || 0)}`,
      `nextSize=${Number(preparation?.nextSize || 0)}`,
      `currentLines=${Number(preparation?.currentLineCount || 0)}`,
      `nextLines=${Number(preparation?.nextLineCount || 0)}`,
    ];
    if (!changed) {
      ElMessage.info("文件内容没有变化，无需写入。");
      void recordDesktopAuditEvent({
        event_type: "desktop_workspace_file_write_prepare",
        step: "准备写入工作区文件",
        status: "skipped",
        content: summary || `桌面端准备写入：${normalizedPath}`,
        changed_files: [normalizedPath],
        facts,
      });
      return true;
    }
    await ElMessageBox.confirm(
      [
        summary || `准备写入工作区文件：${normalizedPath}`,
        `风险级别：${workspaceWriteRiskLabel(riskLevel)}`,
        reason,
        "当前阶段只记录确认与审计，不会执行真实写入。",
      ]
        .filter(Boolean)
        .join("\n"),
      "写入前确认",
      {
        confirmButtonText: "记录确认",
        cancelButtonText: "取消",
        type: riskLevel === "high" ? "warning" : "info",
      },
    );
    await recordNativeRunnerPermissionDecision({
      command: "workspace_file_write",
      args: [normalizedPath],
      workspacePath: projectWorkspaceResolved.value,
      decision: "approve_once",
      reason: summary || "准备写入工作区文件",
      scope: "current_request",
      source: "project_chat_workspace_write_prepare",
      riskLevel,
    });
    await refreshNativeRunnerPermissionRecords();
    void recordDesktopAuditEvent({
      event_type: "desktop_workspace_file_write_prepare",
      step: "准备写入工作区文件",
      status: "approval_recorded",
      content: summary || `桌面端准备写入：${normalizedPath}`,
      changed_files: [normalizedPath],
      facts,
      verification: ["write_executed=false", "approval_recorded=true"],
      next_steps: ["后续接入真实写入时必须复用本次确认摘要和 diff 预览"],
    });
    ElMessage.success("已记录写入前确认；当前阶段不会执行真实写入。");
    void refreshWorkspaceDiffPreview({ path: normalizedPath });
    return true;
  } catch (err) {
    if (err === "cancel" || err?.message === "cancel") {
      await recordNativeRunnerPermissionDecision({
        command: "workspace_file_write",
        args: [normalizedPath],
        workspacePath: projectWorkspaceResolved.value,
        decision: "reject",
        reason: "用户取消写入前确认",
        scope: "current_request",
        source: "project_chat_workspace_write_prepare",
        riskLevel: "medium",
      }).catch(() => null);
      await refreshNativeRunnerPermissionRecords();
      void recordDesktopAuditEvent({
        event_type: "desktop_workspace_file_write_prepare",
        step: "准备写入工作区文件",
        status: "rejected",
        content: `用户取消桌面端写入前确认：${normalizedPath}`,
        changed_files: [normalizedPath],
        risks: ["用户取消写入前确认"],
      });
      return false;
    }
    ElMessage.error(err?.message || "准备写入确认失败");
    void recordDesktopAuditEvent({
      event_type: "desktop_workspace_file_write_prepare",
      step: "准备写入工作区文件",
      status: "failed",
      content: `桌面端写入前确认失败：${normalizedPath}`,
      changed_files: [normalizedPath],
      risks: [String(err?.message || "准备写入确认失败").trim()].filter(
        Boolean,
      ),
    });
    return false;
  } finally {
    workspaceFileSaving.value = false;
  }
}

async function saveActiveWorkspaceFile() {
  const projectId = String(selectedProjectId.value || "").trim();
  const path = String(activeWorkspaceFilePath.value || "").trim();
  if (!projectId || !path) return;
  if (workspaceFileReadOnly.value) {
    await prepareDesktopWorkspaceFileWrite(path);
    return;
  }
  workspaceFileSaving.value = true;
  try {
    const data = await saveProjectWorkspaceFile(projectId, {
      path,
      content: workspaceFileDraft.value,
    });
    activeWorkspaceFilePath.value = String(data?.path || path).trim();
    workspaceFileOriginal.value = workspaceFileDraft.value;
    await openWorkspaceDirectory(workspaceFileTreePath.value);
    ElMessage.success("文件已保存");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存工作区文件失败");
  } finally {
    workspaceFileSaving.value = false;
  }
}

async function startTerminalMirror(options = {}) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return false;
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  if (!chatSessionId) {
    if (!options?.silent) {
      ElMessage.warning("请先创建或切换到一个项目对话");
    }
    return false;
  }
  if (!canUseHostTerminal.value && !options?.attachOnly) {
    if (!options?.silent) {
      ElMessage.warning("请先保存项目工作区路径");
    }
    return false;
  }
  if (typeof options?.assistantIndex === "number") {
    activeTerminalMirrorAssistantIndex.value = options.assistantIndex;
  }
  terminalPanelStatus.value = "running";
  terminalPanelExpanded.value = true;
  const client = await ensureWsClient(projectId);
  client.send({
    type: "terminal_mirror_start",
    request_id: `mirror-start-${Date.now()}`,
    chat_mode: "host_terminal",
    chat_session_id: chatSessionId,
    initial_command: String(options?.initialCommand || "").trim(),
    attach_only: Boolean(options?.attachOnly),
  });
  return true;
}

async function stopTerminalMirror() {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId || !wsClient.value) return;
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  if (!chatSessionId) return;
  wsClient.value.send({
    type: "terminal_mirror_stop",
    request_id: `mirror-stop-${Date.now()}`,
    chat_mode: "host_terminal",
    chat_session_id: chatSessionId,
  });
  terminalMirrorConnected.value = false;
}

async function sendTerminalMirrorInput() {
  ensureActiveTerminalInputTarget();
  const rawContent = String(draftText.value ?? "");
  const content = rawContent.trim();
  const sent = content
    ? await sendTerminalMirrorContent(content)
    : await sendTerminalMirrorContent("\r", {
        appendNewline: false,
        allowBlank: true,
        echoLabel: "回车",
      });
  if (!sent) return;
  draftText.value = "";
  focusTerminalPanelInput();
}

async function waitForTerminalMirrorReady(timeoutMs = 5000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (terminalMirrorConnected.value) {
      return true;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 120));
  }
  return false;
}

async function sendTerminalMirrorContent(content, options = {}) {
  const rawContent = String(content ?? "");
  const shouldPreserveContent =
    Boolean(options?.allowBlank) || options?.appendNewline === false;
  const normalizedContent = shouldPreserveContent
    ? rawContent
    : rawContent.trim();
  if (!normalizedContent && !options?.allowBlank) return false;
  const projectId = String(selectedProjectId.value || "").trim();
  const chatSessionId = String(currentChatSessionId.value || "").trim();
  if (!chatSessionId) return false;
  if (!projectId) return false;
  const client = await ensureWsClient(projectId);
  if (!terminalMirrorConnected.value) {
    const hasRememberedSession = Boolean(
      String(hostTerminalSessionId.value || "").trim(),
    );
    await startTerminalMirror({
      attachOnly: hasRememberedSession,
      silent: hasRememberedSession,
    });
    const ready = await waitForTerminalMirrorReady();
    if (!ready) {
      if (hasRememberedSession) {
        terminalMirrorConnected.value = false;
        hostTerminalSessionId.value = "";
        terminalPanelStatus.value = "idle";
        ElMessage.warning("项目终端连接已失效，请重新执行命令");
      } else {
        ElMessage.warning("项目终端仍在连接中，请稍后再试");
      }
      return false;
    }
  }
  if (options?.echo !== false) {
    const echoText = String(options?.echoLabel ?? normalizedContent).trim();
    if (echoText) {
      const inputLine = `› ${echoText}`;
      appendTerminalPanelLine(inputLine);
      const targetIndex = ensureActiveTerminalInputTarget();
      const targetRow = messages.value[Number(targetIndex)];
      if (targetRow) {
        targetRow.displayMode = "terminal";
        targetRow.processExpanded = true;
        appendTerminalLog(targetRow, inputLine, { mirrorToPanel: false });
        upsertMessageOperation(targetRow, {
          operationId: `terminal:${String(hostTerminalSessionId.value || chatSessionId || "active").trim()}`,
          kind: "terminal",
          title: "需要你继续操作",
          summary: "已发送输入，等待终端输出",
          detail: "主输入框内容已发送到项目终端。",
          phase: "running",
          actionType: "enter_text",
        });
      }
    }
  }
  client.send({
    type: "terminal_mirror_input",
    request_id: `mirror-input-${Date.now()}`,
    chat_mode: "host_terminal",
    chat_session_id: chatSessionId,
    session_id: String(hostTerminalSessionId.value || "").trim(),
    content:
      options?.appendNewline === false
        ? normalizedContent
        : `${normalizedContent}\r`,
  });
  return true;
}

async function sendTerminalApprovalChoice(choice) {
  const activePrompt = terminalApprovalPrompt.value;
  const activePromptKey = String(activePrompt?.key || "").trim();
  if (activePromptKey) {
    terminalApprovalHandledKey.value = activePromptKey;
  }
  await recordNativeTerminalApprovalDecision(choice, activePrompt);
  clearTerminalApprovalFallback();
  terminalApprovalDialogVisible.value = false;
  const sent = await sendTerminalMirrorContent(String(choice || "").trim());
  if (!sent) return;
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
  const notes = Array.isArray(row.statusNotes) ? row.statusNotes.slice() : [];
  if (notes.includes(note)) {
    return;
  }
  notes.push(note);
  row.statusNotes = notes;
  if (row.processExpanded !== false) {
    row.processExpanded = true;
  }
}

function removeAssistantStatusNotes(row, predicate) {
  if (!row || typeof predicate !== "function") return;
  const notes = Array.isArray(row.statusNotes) ? row.statusNotes.slice() : [];
  row.statusNotes = notes.filter(
    (note) => !predicate(String(note || "").trim()),
  );
}

function isTransientExecutionStatusNote(note) {
  const normalized = String(note || "").trim();
  return /有执行步骤未完成，正在等待模型给出下一步|执行过程中出现提示，正在等待后续处理/i.test(
    normalized,
  );
}

function isInternalStatusNote(note) {
  const normalized = String(note || "").trim();
  return (
    /工具调用|正在调用工具|tokens\s+in=|正在处理任务|命令已进入交互模式|已切换到项目终端/i.test(
      normalized,
    ) || isTransientExecutionStatusNote(normalized)
  );
}

function messageStatusNotes(row) {
  return Array.isArray(row?.statusNotes)
    ? row.statusNotes
        .map((item) => String(item || "").trim())
        .filter((item) => item && !isInternalStatusNote(item))
    : [];
}

function appendMessageProcessLog(row, source = {}) {
  if (!row) return null;
  const text = String(source?.text || source?.content || "").trim();
  if (!text) return null;
  const logs = Array.isArray(row.processLog) ? row.processLog.slice() : [];
  const entry = {
    id:
      String(source?.id || "").trim() ||
      `process-log-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    text,
    level: normalizeProcessLogLevel(source?.level),
    createdAt: String(
      source?.createdAt || source?.created_at || nowText(),
    ).trim(),
  };
  const lastEntry = logs[logs.length - 1];
  if (
    lastEntry &&
    String(lastEntry.text || "").trim() === entry.text &&
    String(lastEntry.level || "").trim() === entry.level
  ) {
    return lastEntry;
  }
  logs.push(entry);
  if (logs.length > 80) {
    logs.splice(0, logs.length - 80);
  }
  row.processLog = logs;
  if (row.processExpanded !== false) {
    row.processExpanded = true;
  }
  return entry;
}

function isCompletedDoneProcessLog(entry) {
  const text = String(entry?.text || entry?.content || "").trim();
  if (!text) return false;
  return /^本轮执行已结束[。.]?$/.test(text);
}

function shouldHideProcessLogEntry(row, entry) {
  return (
    hasNonTerminalUserWaitingOperation(row) && isCompletedDoneProcessLog(entry)
  );
}

function messageProcessLogEntries(row) {
  return Array.isArray(row?.processLog)
    ? row.processLog.filter(
        (item) =>
          String(item?.text || "").trim() &&
          !shouldHideProcessLogEntry(row, item),
      )
    : [];
}

function messageProcessLogSummary(row) {
  const entries = messageProcessLogEntries(row);
  if (!entries.length) return [];
  const latestPerLevel = [];
  const seenLevels = new Set();
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index];
    const level = String(entry?.level || "info").trim();
    if (seenLevels.has(level)) continue;
    seenLevels.add(level);
    latestPerLevel.unshift(entry);
    if (latestPerLevel.length >= 3) break;
  }
  return latestPerLevel;
}

function rawMessageOperations(row) {
  return Array.isArray(row?.operations)
    ? row.operations.filter((item) => item && item.title)
    : [];
}

function isVisibleProcessOperation(operation) {
  if (!operation) return false;
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  if (String(meta.hide_in_message_process || "").trim() === "true") {
    return false;
  }
  if (String(meta.source || "").trim() === "tauri_external_agent_runner") {
    return false;
  }
  if (
    String(operation?.operationId || operation?.id || "").startsWith(
      "native-external-agent:",
    )
  ) {
    return false;
  }
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  if (kind === "plan") return true;
  const phase = normalizeOperationPhase(operation?.phase || operation?.status);
  if (
    ["tool", "terminal", "auth", "approval", "verification"].includes(kind) &&
    phase !== "pending"
  ) {
    return true;
  }
  if (
    kind === "request" &&
    (phase !== "pending" ||
      String(meta.agent_runtime_event || "").trim() === "true" ||
      String(meta.agent_runtime_permission || "").trim() === "true" ||
      String(meta.run_id || "").trim())
  ) {
    return true;
  }
  return Boolean(
    operationCommand(operation) ||
    operationOutput(operation) ||
    String(operation?.summary || "").trim() ||
    String(operation?.detail || "").trim(),
  );
}

function isCompletedRequestSummaryOperation(operation, row) {
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  const phase = normalizeOperationPhase(operation?.phase);
  return (
    kind === "request" &&
    phase === "completed" &&
    (messageProcessLogEntries(row).length > 0 ||
      hasNonTerminalUserWaitingOperation(row))
  );
}

function shouldShowInlineThinkingState(row, idx) {
  return (
    chatLoading.value === true &&
    idx === messages.value.length - 1 &&
    !String(row?.content || "").trim()
  );
}

function messageBodyHtml(row, idx) {
  const content = formatContent(row?.content);
  if (content) return content;
  if (
    shouldShowInlineThinkingState(row, idx) &&
    !shouldShowMessageProcess(row, idx)
  ) {
    return "思考中...";
  }
  return "";
}

function messageProcessStepCount(row, idx) {
  const operationCount = messageProcessOperations(row).length;
  const logCount = messageProcessLogEntries(row).length;
  return operationCount + logCount;
}

function shouldShowMessageProcess(row, idx) {
  return (
    messageProcessOperations(row).length > 0 ||
    messageProcessLogEntries(row).length > 0
  );
}

function messageProcessLifecyclePhase(row, idx) {
  const operations = messageProcessOperations(row);
  const phases = operations.map((item) =>
    normalizeOperationPhase(item?.phase || item?.status),
  );
  if (phases.includes("waiting_user")) return "waiting_user";
  if (phases.includes("blocked")) return "blocked";
  if (phases.includes("failed")) return "failed";
  if (phases.includes("running")) return "running";
  if (phases.includes("completed")) return "completed";
  const logs = messageProcessLogEntries(row);
  const latestLogLevel = String(logs[logs.length - 1]?.level || "").trim();
  if (latestLogLevel === "error") return "failed";
  if (latestLogLevel === "warning") return "blocked";
  if (latestLogLevel === "success") return "completed";
  if (
    chatLoading.value === true &&
    idx === messages.value.length - 1 &&
    logs.length
  ) {
    return "running";
  }
  return "pending";
}

function primaryMessageProcessOperation(row) {
  const operations = messageProcessOperations(row);
  return (
    operations.find(
      (item) => normalizeOperationPhase(item?.phase) === "waiting_user",
    ) ||
    operations.find(
      (item) => normalizeOperationPhase(item?.phase) === "blocked",
    ) ||
    operations.find(
      (item) => normalizeOperationPhase(item?.phase) === "running",
    ) ||
    operations[operations.length - 1] ||
    null
  );
}

function messageProcessEyebrow(row, idx) {
  return "执行过程";
}

function messageProcessStateTone(row, idx) {
  const phase = messageProcessLifecyclePhase(row, idx);
  if (phase === "waiting_user") return "waiting";
  if (phase === "blocked" || phase === "failed") return "danger";
  if (phase === "running") return "running";
  if (phase === "completed") return "success";
  return "neutral";
}

function messageProcessStateLabel(row, idx) {
  const phase = messageProcessLifecyclePhase(row, idx);
  if (phase === "waiting_user") return "待处理";
  if (phase === "blocked") return "已阻塞";
  if (phase === "failed") return "失败";
  if (phase === "running") return "进行中";
  if (phase === "completed") return "已完成";
  return "";
}

function messageProcessTitle(row, idx) {
  const primaryOperation = primaryMessageProcessOperation(row);
  const phase = normalizeOperationPhase(primaryOperation?.phase);
  const title = String(primaryOperation?.title || "").trim();
  const summary = String(primaryOperation?.summary || "").trim();
  const detail = String(primaryOperation?.detail || "").trim();
  const logs = messageProcessLogEntries(row);
  const latestLogText = String(logs[logs.length - 1]?.text || "").trim();
  if (phase === "waiting_user") {
    return summary || title || detail || "等待你的处理";
  }
  if (phase === "blocked") {
    return summary || title || detail || "当前步骤已阻塞";
  }
  if (phase === "failed") {
    return summary || title || detail || "执行出现异常";
  }
  if (phase === "running") {
    return summary || title || detail || "正在执行中";
  }
  if (phase === "completed") {
    return summary || title || detail || "已完成本轮执行";
  }
  if (latestLogText) {
    return latestLogText;
  }
  return "执行过程";
}

function messageLiveProgressOperationTitle(operation) {
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  const title = String(operation?.title || "").trim();
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  if (
    kind === "request" &&
    (String(meta.agent_runtime_event || "").trim() === "true" ||
      String(meta.run_id || "").trim())
  ) {
    return title || "Agent Runtime";
  }
  if (kind === "tool") return title || "工具调用";
  if (kind === "auth") return title || "授权操作";
  if (kind === "terminal") return title || "项目终端";
  if (kind === "verification") return title || "验证结果";
  if (kind === "plan") return title || "执行计划";
  return title || "执行步骤";
}

function messageLiveProgressOperationSummary(operation) {
  const summary = String(operation?.summary || "").trim();
  const detail = String(operation?.detail || "").trim();
  if (summary) return summary;
  if (detail) return clipText(detail, 120);
  const command = operationCommand(operation);
  if (command) return clipText(command, 120);
  const output = operationOutput(operation);
  if (output) return clipText(output, 120);
  return "";
}

function messageLiveProgressItems(row, idx) {
  const items = [];
  const seen = new Set();
  for (const operation of messageOperations(row)) {
    if (!isVisibleProcessOperation(operation)) continue;
    const phase = normalizeOperationPhase(
      operation?.phase || operation?.status,
    );
    const id =
      String(operation?.id || "").trim() || `operation-${items.length}`;
    const title = messageLiveProgressOperationTitle(operation);
    const summary = messageLiveProgressOperationSummary(operation);
    const signature = `${title}\n${summary}\n${phase}`;
    if (seen.has(signature)) continue;
    seen.add(signature);
    items.push({
      id: `op:${id}`,
      phase,
      title,
      summary,
      phaseLabel: operationPhaseLabel(operation),
    });
  }
  const latestLogs = messageProcessLogEntries(row).slice(-4);
  for (const entry of latestLogs) {
    const text = String(entry?.text || "").trim();
    if (!text) continue;
    const level = normalizeProcessLogLevel(entry?.level);
    const phase =
      level === "success"
        ? "completed"
        : level === "error"
          ? "failed"
          : level === "warning"
            ? "blocked"
            : "running";
    const title = clipText(text, 140);
    const signature = `${title}\n\n${phase}`;
    if (seen.has(signature)) continue;
    seen.add(signature);
    items.push({
      id: `log:${String(entry?.id || items.length).trim()}`,
      phase,
      title,
      summary: "",
      phaseLabel:
        phase === "completed"
          ? "已完成"
          : phase === "failed"
            ? "失败"
            : phase === "blocked"
              ? "提示"
              : "进行中",
    });
  }
  if (!items.length && shouldShowInlineThinkingState(row, idx)) {
    items.push({
      id: "thinking",
      phase: "running",
      title: "模型正在生成回复",
      summary: "",
      phaseLabel: "进行中",
    });
  }
  return items.slice(-8);
}

function agentRuntimeCommandSignatureFromArgs(args = {}) {
  const command = String(args?.command || "").trim();
  if (!command) return "";
  const tokens = command
    .split(" ")
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const larkCliIndex = tokens.findIndex(
    (item) => item.split("/").pop() === "lark-cli",
  );
  if (
    larkCliIndex >= 0 &&
    tokens[larkCliIndex + 1] === "auth" &&
    ["status", "login"].includes(tokens[larkCliIndex + 2])
  ) {
    return `lark-cli auth ${tokens[larkCliIndex + 2]}`;
  }
  const normalized = tokens.join(" ");
  return normalized;
}

function agentRuntimePermissionOperationId(
  runId,
  callId,
  commandSignature = "",
) {
  const normalizedRunId = String(runId || "").trim();
  const normalizedCallId = String(callId || "").trim();
  const normalizedSignature = String(commandSignature || "").trim();
  if (normalizedRunId && normalizedSignature) {
    return `agent-runtime-permission:${normalizedRunId}:command:${normalizedSignature}`;
  }
  return `agent-runtime-permission:${normalizedRunId}:${normalizedCallId}`;
}

/** 向消息行追加/更新 operation 状态（授权、工作流、终端等），按 operationId 去重覆盖 */
function upsertMessageOperation(row, source = {}) {
  if (!row) return null;
  const operation = buildMessageOperation(source);
  const items = Array.isArray(row.operations) ? row.operations.slice() : [];
  const matchIndex = findMessageOperationMatchIndex(items, operation);
  if (matchIndex >= 0) {
    const existingMeta =
      items[matchIndex]?.meta && typeof items[matchIndex].meta === "object"
        ? items[matchIndex].meta
        : {};
    const operationMeta =
      operation?.meta && typeof operation.meta === "object"
        ? operation.meta
        : {};
    items[matchIndex] = {
      ...items[matchIndex],
      ...operation,
      id: items[matchIndex].operationId ? items[matchIndex].id : operation.id,
      operationId: items[matchIndex].operationId || operation.operationId,
      createdAt: items[matchIndex].createdAt || operation.createdAt,
      updatedAt: operation.updatedAt || nowText(),
      meta: {
        ...existingMeta,
        ...operationMeta,
        command:
          String(operationMeta.command || "").trim() ||
          String(existingMeta.command || "").trim(),
        cwd:
          String(operationMeta.cwd || "").trim() ||
          String(existingMeta.cwd || "").trim(),
        arguments_preview:
          String(operationMeta.arguments_preview || "").trim() ||
          String(existingMeta.arguments_preview || "").trim(),
        output_preview:
          String(operationMeta.output_preview || "").trim() ||
          String(existingMeta.output_preview || "").trim(),
        stdout_preview:
          String(operationMeta.stdout_preview || "").trim() ||
          String(existingMeta.stdout_preview || "").trim(),
        stderr_preview:
          String(operationMeta.stderr_preview || "").trim() ||
          String(existingMeta.stderr_preview || "").trim(),
        error:
          String(operationMeta.error || "").trim() ||
          String(existingMeta.error || "").trim(),
        risk_level:
          String(operationMeta.risk_level || "").trim() ||
          String(existingMeta.risk_level || "").trim(),
        authorization_url:
          String(operationMeta.authorization_url || "").trim() ||
          String(existingMeta.authorization_url || "").trim(),
        interaction_schema:
          operationMeta.interaction_schema ||
          existingMeta.interaction_schema ||
          null,
      },
    };
  } else {
    items.push(operation);
  }
  row.operations = items.slice(-24);
  const phase = normalizeOperationPhase(operation?.phase);
  if (["waiting_user", "blocked", "failed"].includes(phase)) {
    row.processExpanded = true;
  } else if (typeof row.processExpanded !== "boolean") {
    row.processExpanded = phase === "running";
  }
  return operation;
}

function appendAgentRuntimePermissionOperations(row, eventData = {}) {
  const runtime =
    eventData?.agent_runtime && typeof eventData.agent_runtime === "object"
      ? eventData.agent_runtime
      : {};
  const runId = String(runtime?.run_id || "").trim();
  const observations = Array.isArray(runtime?.observations)
    ? runtime.observations
    : [];
  observations.forEach((observation) => {
    const raw =
      observation?.raw_result && typeof observation.raw_result === "object"
        ? observation.raw_result
        : {};
    const decision =
      raw?.permission_decision && typeof raw.permission_decision === "object"
        ? raw.permission_decision
        : null;
    if (!decision) return;
    const behavior = String(decision.behavior || "")
      .trim()
      .toLowerCase();
    if (!["ask", "deny"].includes(behavior)) return;
    const callId = String(
      observation?.call_id || decision.call_id || "",
    ).trim();
    const toolName = String(
      observation?.tool_name || decision.tool_name || "",
    ).trim();
    if (!runId || !callId || !toolName) return;
    const toolArgs =
      raw?.tool_args && typeof raw.tool_args === "object" ? raw.tool_args : {};
    const toolEntry =
      raw?.tool_entry && typeof raw.tool_entry === "object"
        ? raw.tool_entry
        : {};
    const commandSignature = agentRuntimeCommandSignatureFromArgs(toolArgs);
    const permissionPatch = {
      title: behavior === "deny" ? "工具调用已拒绝" : "工具调用需要授权",
      summary:
        behavior === "deny"
          ? "权限策略拒绝了本次工具调用"
          : "等待你选择本次工具调用的授权范围",
      detail: String(observation?.summary || raw?.summary || "").trim(),
      phase: behavior === "deny" ? "blocked" : "waiting_user",
      actionType: behavior === "deny" ? "none" : "approve",
      meta: {
        agent_runtime_permission: "true",
        run_id: runId,
        call_id: callId,
        tool_name: toolName,
        tool_args: toolArgs,
        command_signature: commandSignature,
        chat_session_id: String(currentChatSessionId.value || "").trim(),
        assistant_message_id: String(row?.id || "").trim(),
        permission_decision: decision,
        tool_entry: toolEntry,
        risk_level:
          String(decision?.risk_level || "").trim() ||
          String(toolEntry?.risk_level || "").trim(),
        permission_scope: String(toolEntry?.permission_scope || "").trim(),
        execution_backend: String(toolEntry?.execution_backend || "").trim(),
        audit_policy: String(toolEntry?.audit_policy || "").trim(),
      },
    };
    if (
      updateAgentRuntimePermissionOperations(
        row,
        runId,
        callId,
        permissionPatch,
      )
    ) {
      return;
    }
    const existingPermission = (
      Array.isArray(row?.operations) ? row.operations : []
    ).find((operation) => {
      const meta =
        operation?.meta && typeof operation.meta === "object"
          ? operation.meta
          : {};
      const sameCommand =
        commandSignature &&
        String(meta.command_signature || "").trim() === commandSignature;
      return (
        String(meta.agent_runtime_permission || "").trim() === "true" &&
        String(meta.run_id || "").trim() === runId &&
        (String(meta.call_id || "").trim() === callId || sameCommand) &&
        normalizeOperationPhase(operation?.phase) !== "waiting_user"
      );
    });
    if (existingPermission) return;
    upsertMessageOperation(row, {
      operationId: agentRuntimePermissionOperationId(
        runId,
        callId,
        commandSignature,
      ),
      kind: "approval",
      ...permissionPatch,
    });
  });
}

function completeAgentRuntimeOperations(
  row,
  runId,
  summary = "运行任务已结束",
) {
  if (!row || !Array.isArray(row.operations) || !row.operations.length) {
    return false;
  }
  const normalizedRunId = String(runId || "").trim();
  if (!normalizedRunId) return false;
  let changed = false;
  row.operations = row.operations.map((operation) => {
    const meta =
      operation?.meta && typeof operation.meta === "object"
        ? operation.meta
        : {};
    if (
      String(meta.agent_runtime_event || "").trim() !== "true" ||
      String(meta.run_id || "").trim() !== normalizedRunId
    ) {
      return operation;
    }
    const phase = normalizeOperationPhase(
      operation?.phase || operation?.status,
    );
    if (["completed", "failed", "blocked"].includes(phase)) {
      return operation;
    }
    changed = true;
    return {
      ...operation,
      summary:
        String(operation?.summary || "").trim() ||
        String(summary || "").trim() ||
        "运行任务已结束",
      phase: "completed",
      actionType: "none",
      updatedAt: nowText(),
      meta: {
        ...meta,
        event_type: String(meta.event_type || "run_finished").trim(),
      },
    };
  });
  return changed;
}

function applyInteractionSubmitAckToSourceOperation(eventData = {}) {
  const ack = interactionSubmitAckPayload(eventData);
  const operationId = String(
    ack.operation_id ||
      eventData?.interaction_operation_id ||
      eventData?.operation_id ||
      eventData?.interaction_id ||
      "",
  ).trim();
  const taskId = String(ack.task_id || eventData?.task_id || "").trim();
  const chatSessionId = String(
    ack.chat_session_id || eventData?.chat_session_id || "",
  ).trim();
  let matched = findMessageOperationById(operationId);
  if (!matched && taskId) {
    matched = findAssistantRowByOperationTaskId(taskId, chatSessionId);
  }
  if (!matched?.row) return false;
  const existing = matched.operation || {};
  const existingMeta =
    existing?.meta && typeof existing.meta === "object" ? existing.meta : {};
  const summary = interactionSubmitAckSummary(eventData);
  upsertMessageOperation(matched.row, {
    operationId: existing.operationId || operationId,
    kind: existing.kind || "request",
    title: existing.title || String(ack.title || "操作").trim() || "操作",
    summary,
    detail: "",
    phase: "running",
    actionType: "none",
    meta: {
      ...existingMeta,
      task_id: String(existingMeta.task_id || taskId).trim(),
      chat_session_id: String(
        existingMeta.chat_session_id || chatSessionId,
      ).trim(),
      interaction_ack: true,
      interaction_submitted: true,
    },
  });
  appendMessageProcessLog(matched.row, {
    level: "info",
    text: summary,
  });
  matched.row.processExpanded = true;
  return true;
}

function removeTransientInteractionAckRow(row, pending) {
  if (!row) return false;
  const index = messages.value.findIndex((item) => item === row);
  if (index < 0) return false;
  const hasVisibleContent = Boolean(String(row.content || "").trim());
  const hasOperations =
    Array.isArray(row.operations) && row.operations.length > 0;
  const hasProcessLog =
    Array.isArray(row.processLog) && row.processLog.length > 0;
  const hasStatusNotes =
    Array.isArray(row.statusNotes) && row.statusNotes.length > 0;
  if (hasVisibleContent || hasOperations || hasProcessLog || hasStatusNotes) {
    row.meta = {
      ...(row.meta && typeof row.meta === "object" ? row.meta : {}),
      interaction_submit_ack_hidden: true,
    };
    return false;
  }
  messages.value.splice(index, 1);
  pendingRequests.forEach((entry) => {
    if (Number(entry?.assistantIndex ?? -1) > index) {
      entry.assistantIndex = Number(entry.assistantIndex) - 1;
    }
  });
  if (Number(activeTerminalMirrorAssistantIndex.value) > index) {
    activeTerminalMirrorAssistantIndex.value -= 1;
  }
  if (pending && Number(pending.assistantIndex ?? -1) === index) {
    pending.assistantIndex = -1;
  }
  return true;
}

function hasOpenAgentRuntimeExecution(row) {
  if (!row || !Array.isArray(row.operations)) return false;
  return row.operations.some((operation) => {
    const phase = normalizeOperationPhase(
      operation?.phase || operation?.status,
    );
    if (!["running", "waiting_user", "pending"].includes(phase)) return false;
    const meta =
      operation?.meta && typeof operation.meta === "object"
        ? operation.meta
        : {};
    return (
      String(meta.agent_runtime_event || "").trim() === "true" ||
      String(meta.agent_runtime_permission || "").trim() === "true" ||
      Boolean(String(meta.run_id || "").trim())
    );
  });
}

/** 完成后台 pending request 中的 operation，标记为 completed 阶段 */
function completeBackgroundPendingRequestOperation(
  row,
  { taskId = "", chatSessionId = "", phase = "completed", summary = "" } = {},
) {
  if (!row || !Array.isArray(row.operations) || !row.operations.length) {
    return false;
  }
  const normalizedTaskId = String(taskId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  const nextPhase = normalizeOperationPhase(phase);
  const nextSummary =
    String(summary || "").trim() ||
    (nextPhase === "failed" ? "后台任务未完成" : "后台任务已完成");
  let changed = false;
  row.operations = row.operations.map((operation) => {
    const meta =
      operation?.meta && typeof operation.meta === "object"
        ? operation.meta
        : {};
    if (
      String(operation?.kind || "")
        .trim()
        .toLowerCase() !== "request" ||
      normalizeOperationPhase(operation?.phase || operation?.status) !==
        "running" ||
      String(meta.completed_reason || "").trim() !== "background_task_pending"
    ) {
      return operation;
    }
    const operationTaskId = String(meta.task_id || "").trim();
    const operationChatSessionId = String(meta.chat_session_id || "").trim();
    if (
      normalizedTaskId &&
      operationTaskId &&
      operationTaskId !== normalizedTaskId
    ) {
      return operation;
    }
    if (
      !normalizedTaskId &&
      normalizedChatSessionId &&
      operationChatSessionId &&
      operationChatSessionId !== normalizedChatSessionId
    ) {
      return operation;
    }
    changed = true;
    return {
      ...operation,
      summary: nextSummary,
      phase: nextPhase,
      updatedAt: nowText(),
      meta: {
        ...meta,
        background_task_closed: "true",
      },
    };
  });
  return changed;
}

function applyAgentRuntimeEvent(row, eventData = {}) {
  if (!row) return false;
  const runId = String(eventData?.run_id || "").trim();
  const eventType = String(eventData?.event_type || "").trim();
  if (!runId || !eventType) return false;
  const summary = formatAgentRuntimeEventSummary(eventData);
  const phase = formatAgentRuntimeEventPhase(eventData);
  if (["query_engine_completed", "run_finished"].includes(eventType)) {
    completeAgentRuntimeOperations(row, runId, summary);
    completeAgentRuntimeOperationsForRun(row, runId);
    completePendingRequestForAssistantRow(row);
  }
  const shouldUpdateRuntimeOperation = [
    "permission_decision",
    "query_engine_waiting_operation",
    "query_engine_blocked",
    "query_engine_completed",
    "query_engine_failed",
    "run_failed",
    "run_finished",
  ].includes(eventType);
  if (shouldUpdateRuntimeOperation) {
    upsertMessageOperation(row, {
      operationId: `agent-runtime:${runId}`,
      kind: "request",
      title: "Agent Runtime",
      summary,
      detail: "",
      phase,
      actionType: "none",
      meta: {
        agent_runtime_event: "true",
        run_id: runId,
        event_type: eventType,
        chat_session_id: String(eventData?.chat_session_id || "").trim(),
      },
    });
  }
  const transcriptEntry = formatAgentRuntimeTranscriptEntry(eventData);
  if (transcriptEntry) {
    appendMessageProcessLog(row, transcriptEntry);
  }
  row.processExpanded = false;
  return true;
}

function applyPlanCreatedEvent(row, eventData = {}, requestId = "") {
  if (!row) return;
  const planId = String(eventData?.plan_id || requestId || "active").trim();
  const steps = Array.isArray(eventData?.steps) ? eventData.steps : [];
  const detail = formatPlanStepsDetail(steps);
  upsertMessageOperation(row, {
    operationId: `plan:${planId}`,
    kind: "plan",
    title: "执行计划",
    summary: steps.length ? `已生成 ${steps.length} 个步骤` : "已生成执行计划",
    detail,
    phase: "running",
    actionType: "none",
    meta: {
      request_id: String(requestId || eventData?.request_id || "").trim(),
      plan_id: planId,
      intent: String(eventData?.intent || "").trim(),
      task_type: String(eventData?.task_type || "").trim(),
      steps,
    },
  });
  row.processExpanded = true;
}

function formatPlanStepsDetail(steps) {
  return (Array.isArray(steps) ? steps : [])
    .map((step, index) => {
      const title = String(step?.title || `步骤 ${index + 1}`).trim();
      const status = String(step?.status || "pending").trim();
      const summary = String(step?.summary || "").trim();
      return `${index + 1}. ${title} [${status}]${summary ? `\n   ${summary}` : ""}`;
    })
    .join("\n");
}

function operationPlanSteps(operation) {
  if (
    String(operation?.kind || "")
      .trim()
      .toLowerCase() !== "plan"
  ) {
    return [];
  }
  const steps = operationMeta(operation).steps;
  return Array.isArray(steps)
    ? steps.filter((step) => step && typeof step === "object")
    : [];
}

function planStepPhase(step = {}) {
  const status = String(step?.status || "")
    .trim()
    .toLowerCase();
  if (["completed", "done", "skipped"].includes(status)) return "completed";
  if (["running", "in_progress", "verifying"].includes(status))
    return "running";
  if (["blocked", "failed"].includes(status)) return status;
  return "pending";
}

function planStepStatusLabel(step = {}) {
  const phase = planStepPhase(step);
  if (phase === "completed") return "已完成";
  if (phase === "running") return "进行中";
  if (phase === "blocked") return "已阻塞";
  if (phase === "failed") return "失败";
  return "待开始";
}

function updatePlanOperationStep(row, planId, stepId, patch = {}) {
  const normalizedPlanId = String(planId || "").trim();
  const normalizedStepId = String(stepId || "").trim();
  if (
    !row ||
    !normalizedPlanId ||
    !normalizedStepId ||
    !Array.isArray(row.operations)
  ) {
    return false;
  }
  let changed = false;
  row.operations = row.operations.map((operation) => {
    const meta = operationMeta(operation);
    if (
      String(operation?.kind || "")
        .trim()
        .toLowerCase() !== "plan" ||
      String(meta.plan_id || "").trim() !== normalizedPlanId
    ) {
      return operation;
    }
    const steps = Array.isArray(meta.steps) ? meta.steps.slice() : [];
    const targetIndex = steps.findIndex(
      (step) => String(step?.step_id || "").trim() === normalizedStepId,
    );
    const targetStep = targetIndex >= 0 ? steps[targetIndex] : null;
    const targetStage = String(targetStep?.stage_key || "")
      .trim()
      .toLowerCase();
    const targetLooksLikeVerify =
      normalizedStepId.endsWith("-verify") ||
      ["verification", "verify"].includes(targetStage);
    const patchPhase = planStepPhase({ status: patch.status });
    const shouldCompletePrevious =
      targetIndex > 0 &&
      targetLooksLikeVerify &&
      ["running", "completed"].includes(patchPhase);
    const nextSteps = steps.map((step, index) => {
      if (shouldCompletePrevious && index < targetIndex) {
        const previousPhase = planStepPhase(step);
        if (["pending", "running"].includes(previousPhase)) {
          changed = true;
          return {
            ...step,
            status: "completed",
          };
        }
      }
      if (String(step?.step_id || "").trim() !== normalizedStepId) return step;
      changed = true;
      return {
        ...step,
        ...patch,
        status: String(patch.status || step?.status || "").trim() || "pending",
      };
    });
    if (!changed) return operation;
    const hasRunning = nextSteps.some(
      (step) => String(step?.status || "").trim() === "running",
    );
    const hasFailed = nextSteps.some((step) =>
      ["failed", "blocked"].includes(String(step?.status || "").trim()),
    );
    const allDone =
      nextSteps.length > 0 &&
      nextSteps.every((step) =>
        ["completed", "skipped"].includes(String(step?.status || "").trim()),
      );
    return {
      ...operation,
      summary: allDone
        ? "计划步骤已完成"
        : hasFailed
          ? "计划执行遇到阻塞"
          : hasRunning
            ? "计划执行中"
            : operation.summary,
      detail: formatPlanStepsDetail(nextSteps),
      phase: allDone ? "completed" : hasFailed ? "blocked" : "running",
      updatedAt: nowText(),
      meta: {
        ...meta,
        steps: nextSteps,
      },
    };
  });
  return changed;
}

function applyVerificationStartedEvent(row, eventData = {}, requestId = "") {
  if (!row) return;
  const planId = String(eventData?.plan_id || "").trim();
  const stepId = String(eventData?.step_id || "").trim();
  if (planId && stepId) {
    updatePlanOperationStep(row, planId, stepId, {
      status: "running",
      summary: String(eventData?.summary || "正在验证执行结果").trim(),
    });
  }
  upsertMessageOperation(row, {
    operationId: `verification:${String(planId || requestId || eventData?.request_id || "active").trim()}`,
    kind: "verification",
    title: "验证结果",
    summary: String(eventData?.summary || "正在验证执行结果").trim(),
    detail: "",
    phase: "running",
    actionType: "none",
    meta: {
      request_id: String(requestId || eventData?.request_id || "").trim(),
      plan_id: planId,
      step_id: stepId,
    },
  });
  row.processExpanded = true;
}

function applyVerificationFinishedEvent(row, eventData = {}, requestId = "") {
  if (!row) return;
  const planId = String(eventData?.plan_id || "").trim();
  const stepId = String(eventData?.step_id || "").trim();
  const status = String(eventData?.status || "")
    .trim()
    .toLowerCase();
  const passed = status === "passed";
  const evidence = Array.isArray(eventData?.evidence)
    ? eventData.evidence
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  const summary =
    String(eventData?.summary || "").trim() ||
    (passed ? "验证通过" : "验证未完全通过");
  if (planId && stepId) {
    updatePlanOperationStep(row, planId, stepId, {
      status: passed ? "completed" : "blocked",
      summary,
    });
  }
  upsertMessageOperation(row, {
    operationId: `verification:${String(planId || requestId || eventData?.request_id || "active").trim()}`,
    kind: "verification",
    title: "验证结果",
    summary,
    detail: evidence.length
      ? evidence.map((item, index) => `${index + 1}. ${item}`).join("\n")
      : "",
    phase: passed ? "completed" : "blocked",
    actionType: "none",
    meta: {
      request_id: String(requestId || eventData?.request_id || "").trim(),
      plan_id: planId,
      step_id: stepId,
      status,
      evidence,
      guard_reason: String(eventData?.guard_reason || "").trim(),
      guard_message: String(eventData?.guard_message || "").trim(),
    },
  });
  row.processExpanded = true;
}

function projectChatActionOperationId(eventData = {}) {
  const toolName = String(eventData?.tool_name || "tool").trim() || "tool";
  const toolIndex = Number(eventData?.tool_index || 0) || 0;
  const command = eventCommand(eventData);
  if (command) {
    return `command:${command.slice(0, 180)}`;
  }
  const callId = String(
    eventData?.call_id ||
      eventData?.tool_call_id ||
      eventData?.operation_id ||
      eventData?.task_id ||
      "",
  ).trim();
  if (callId) {
    return `tool:${toolName}:${callId}`;
  }
  return `tool:${toolName}:${toolIndex}`;
}

function applyPlannedActionEvent(row, eventData = {}, requestId = "") {
  if (!row) return;
  const eventType = String(eventData?.type || "")
    .trim()
    .toLowerCase();
  const isCommand =
    eventType === "command_planned" || Boolean(eventCommand(eventData));
  const toolName =
    String(eventData?.tool_name || (isCommand ? "命令" : "工具")).trim() ||
    (isCommand ? "命令" : "工具");
  const label = toolProgressLabel(eventData, toolName);
  const command = eventCommand(eventData);
  const cwd = String(eventData?.cwd || eventData?.workspace_path || "").trim();
  const argumentsPreview = formatToolArgumentsPreview(eventData);
  const planId = String(eventData?.plan_id || "").trim();
  const stepId = String(eventData?.step_id || "").trim();
  if (planId && stepId) {
    updatePlanOperationStep(row, planId, stepId, {
      status: "pending",
      summary: isCommand
        ? `准备执行命令：${command || toolName}`
        : `准备调用工具：${toolName}`,
    });
  }
  appendMessageProcessLog(row, {
    level: "info",
    text: isCommand
      ? `准备执行命令：${command || toolName}`
      : argumentsPreview
        ? `准备调用 ${label}：${argumentsPreview}`
        : `准备调用 ${label}`,
  });
  upsertMessageOperation(row, {
    operationId: projectChatActionOperationId(eventData),
    kind: "tool",
    title: label,
    summary: isCommand ? "准备执行命令" : "准备调用工具",
    detail: isCommand ? "" : argumentsPreview,
    phase: "pending",
    actionType: "none",
    meta: {
      request_id: String(requestId || eventData?.request_id || "").trim(),
      tool_name: toolName,
      command,
      cwd,
      arguments_preview: argumentsPreview,
      risk_level: String(eventData?.risk_level || "").trim(),
      plan_id: planId,
      step_id: stepId,
      tool_index: Number(eventData?.tool_index || 0) || 0,
      tool_count: Number(eventData?.tool_count || 0) || 0,
    },
  });
  row.processExpanded = false;
}

function messageOperations(row) {
  return rawMessageOperations(row).filter(
    (item) =>
      !isCompletedRequestSummaryOperation(item, row) &&
      !shouldHideGenericRequestLifecycleOperation(item, row) &&
      !shouldHideStaleRunningOperation(item, row),
  );
}

function messageProcessOperations(row) {
  return messageOperations(row).filter((item) =>
    isVisibleProcessOperation(item),
  );
}

function isOperationAwaitingInteraction(operation) {
  if (!operation) return false;
  const phase = normalizeOperationPhase(operation?.phase || operation?.status);
  if (phase !== "waiting_user") return false;
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  if (meta.interaction_schema && typeof meta.interaction_schema === "object") {
    return true;
  }
  const actionType = normalizeOperationActionType(operation?.actionType);
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  if (actionType === "open_url") {
    return Boolean(extractOperationUrl(operation));
  }
  if (["approve", "enter_text", "select"].includes(actionType)) {
    return true;
  }
  if (kind === "auth") {
    return Boolean(extractOperationUrl(operation));
  }
  return ["approval", "terminal"].includes(kind);
}

function isNonTerminalUserWaitingOperation(operation) {
  if (!operation) return false;
  const phase = normalizeOperationPhase(operation?.phase || operation?.status);
  if (phase !== "waiting_user") return false;
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  if (kind === "terminal") return false;
  return (
    isOperationAwaitingInteraction(operation) ||
    ["auth", "approval", "request"].includes(kind)
  );
}

function hasNonTerminalUserWaitingOperation(row) {
  return (Array.isArray(row?.operations) ? row.operations : []).some(
    (operation) => isNonTerminalUserWaitingOperation(operation),
  );
}

function isGenericRequestLifecycleOperation(operation) {
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  if (kind !== "request") return false;
  const title = String(operation?.title || "").trim();
  if (title !== "本轮执行") return false;
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  return !(
    String(meta.agent_runtime_event || "").trim() ||
    String(meta.agent_runtime_permission || "").trim() ||
    String(meta.run_id || "").trim()
  );
}

function shouldHideGenericRequestLifecycleOperation(operation, row) {
  const phase = normalizeOperationPhase(operation?.phase || operation?.status);
  if (phase === "waiting_user") return false;
  return (
    hasNonTerminalUserWaitingOperation(row) &&
    isGenericRequestLifecycleOperation(operation)
  );
}

function isCurrentChatTaskTreeDone() {
  const taskTree = displayedChatTaskTree.value;
  if (!taskTree || typeof taskTree !== "object") return false;
  const taskTreeChatSessionId = String(taskTree.chat_session_id || "").trim();
  const currentSessionId = String(currentChatSessionId.value || "").trim();
  if (
    taskTreeChatSessionId &&
    currentSessionId &&
    taskTreeChatSessionId !== currentSessionId
  ) {
    return false;
  }
  return isTaskTreeArchivedOrDone(taskTree);
}

function hasLiveExecutionActivity() {
  return Boolean(
    chatLoading.value ||
    hasPendingRequestForChatSession(currentChatSessionId.value) ||
    Boolean(getActiveRequestId()) ||
    externalAgentWarmupLoading.value ||
    currentChatSessionNativeExternalAgentRunning.value ||
    backgroundTerminalCount.value > 0 ||
    terminalMirrorConnected.value ||
    terminalPanelStatus.value === "running",
  );
}

function operationBelongsToCurrentChat(operation) {
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  const operationChatSessionId = String(meta.chat_session_id || "").trim();
  const currentSessionId = String(currentChatSessionId.value || "").trim();
  return (
    !operationChatSessionId ||
    !currentSessionId ||
    operationChatSessionId === currentSessionId
  );
}

function shouldHideStaleRunningOperation(operation) {
  const phase = normalizeOperationPhase(operation?.phase || operation?.status);
  if (phase !== "running" && phase !== "pending") return false;
  if (hasLiveExecutionActivity()) return false;
  return operationBelongsToCurrentChat(operation);
}

function operationPhaseLabel(operation) {
  const phase = normalizeOperationPhase(operation?.phase);
  if (phase === "running") return "进行中";
  if (phase === "waiting_user") return "等你处理";
  if (phase === "blocked") return "已阻塞";
  if (phase === "completed") return "已完成";
  if (phase === "failed") return "失败";
  return "待开始";
}

function operationRiskTone(operation) {
  const riskLevel = String(operationMeta(operation).risk_level || "")
    .trim()
    .toLowerCase();
  if (riskLevel === "high") return "high";
  if (riskLevel === "medium") return "medium";
  return "";
}

function operationRiskLabel(operation) {
  const tone = operationRiskTone(operation);
  if (tone === "high") return "高风险命令，执行前请重点核对";
  if (tone === "medium") return "中风险命令，请核对执行范围";
  return "";
}

function operationRuntimeMetaTags(operation) {
  const meta = operationMeta(operation);
  const tags = [];
  const backend = runtimeMetaValueLabel(meta.execution_backend, {
    project_host: "项目主机",
    local_connector: "本机连接器",
    browser: "浏览器",
    mcp: "MCP",
    project: "项目工具",
    cli: "CLI",
  });
  const scope = runtimeMetaValueLabel(meta.permission_scope, {
    project: "项目范围",
    workspace: "工作区范围",
    global: "全局范围",
    host: "主机范围",
    local: "本机范围",
  });
  const audit = runtimeMetaValueLabel(meta.audit_policy, {
    full: "完整审计",
    standard: "标准审计",
    summary: "摘要审计",
  });
  if (backend) tags.push(backend);
  if (scope) tags.push(scope);
  if (audit) tags.push(audit);
  return tags;
}

function runtimeMetaValueLabel(value, labels = {}) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (!normalized) return "";
  return labels[normalized] || normalized;
}

function operationActionHint(operation) {
  const schema = operationInteractionSchema(operation);
  if (schema) {
    if (operationInteractionSubmittedHint(operation)) {
      return "已提交结构化交互，等待后续授权或操作完成。";
    }
    return operationInteractionCanFallbackToTerminal(operation)
      ? "优先使用当前表单继续；如果协议不完整，也可以切回终端兜底。"
      : "请完成当前结构化表单后继续。";
  }
  const actionType = normalizeOperationActionType(operation?.actionType);
  if (actionType === "open_url") {
    if (!extractOperationUrl(operation)) return "";
    return "需要在浏览器完成操作，然后回到对话框继续。";
  }
  if (actionType === "approve") {
    return "等待你确认或批准后继续。";
  }
  if (actionType === "enter_text") {
    const kind = String(operation?.kind || "")
      .trim()
      .toLowerCase();
    if (kind === "terminal") {
      if (terminalStructuredSubmissionHint.value) {
        return "已提交表单，终端已继续执行；如已打开浏览器授权，请完成后回到这里。";
      }
      if (terminalStructuredInteraction.value) {
        return "已识别为可表单化交互，请在终端输出下方的表单里选择并确认。";
      }
      return "无法识别为表单时，下方会显示清洗后的真实终端输出作为兜底。";
    }
    return "等待你在当前输入框继续输入。";
  }
  if (actionType === "select") {
    return "等待你从候选对象里选择一个目标。";
  }
  return "";
}

function extractOperationUrl(operation) {
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  return String(meta.authorization_url || "").trim();
}

function operationPrimaryActionLabel(operation) {
  const buttons = operationActionButtons(operation);
  return buttons.length ? buttons[0].label : "";
}

function messageFooterActionOperation(row) {
  return pickAwaitingInteractionOperation(row, {
    allowTerminal: false,
  });
}

function messageFooterInteractionOperation(row) {
  const operation = messageFooterActionOperation(row);
  if (!operation) return null;
  return messageOperationInteractionFormJson(operation) ? operation : null;
}

function messageFooterButtonActionOperation(row) {
  const operation = messageFooterActionOperation(row);
  if (!operation) return null;
  if (messageOperationInteractionFormJson(operation)) return null;
  return operationActionButtons(operation).length ? operation : null;
}

function isMessageFooterActionOperation(row, operation) {
  const footerOperation = messageFooterActionOperation(row);
  if (!footerOperation || !operation) return false;
  return (
    String(footerOperation.id || "").trim() ===
    String(operation.id || "").trim()
  );
}

function findAssistantRowByOperationTaskId(taskId, chatSessionId = "") {
  const normalizedTaskId = String(taskId || "").trim();
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (!normalizedTaskId && !normalizedChatSessionId) return null;
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    const row = messages.value[index];
    if (String(row?.role || "").trim() !== "assistant") continue;
    const operations = messageOperations(row);
    const matched = operations.find((item) => {
      const meta = item?.meta && typeof item.meta === "object" ? item.meta : {};
      const operationTaskId = String(meta.task_id || "").trim();
      const operationChatSessionId = String(meta.chat_session_id || "").trim();
      return (
        (normalizedTaskId && operationTaskId === normalizedTaskId) ||
        (normalizedChatSessionId &&
          operationChatSessionId === normalizedChatSessionId &&
          ["auth", "request", "approval"].includes(
            String(item?.kind || "")
              .trim()
              .toLowerCase(),
          ))
      );
    });
    if (matched) {
      return { row, index, operation: matched };
    }
  }
  return null;
}

function completePendingExternalOperationRequest(matched, message) {
  if (!matched?.row || !message) return;
  const normalizedMessage = String(message || "").trim();
  if (!normalizedMessage) return;
  if (!String(matched.row.content || "").trim()) {
    matched.row.content = normalizedMessage;
  }
  const entries = Array.from(pendingRequests.entries());
  for (const [requestId, pending] of entries) {
    if (Number(pending?.assistantIndex ?? -1) !== Number(matched.index)) {
      continue;
    }
    const row = messages.value[pending.assistantIndex];
    if (row !== matched.row) continue;
    completeTerminalInputOperations(row, normalizedMessage);
    resolvePendingRequest(requestId, pending, row.content || normalizedMessage);
    syncChatLoadingWithCurrentSession();
    break;
  }
}

function isTransientAuthOperationContent(content) {
  const normalized = String(content || "").trim();
  if (!normalized || normalized.length > 220) return false;
  return /(?:已创建内部授权任务|内部授权任务已创建|内部授权流程已启动|授权流程已启动|授权任务已创建|等待返回授权链接|等待结构化授权链接|正在等待返回下一步操作|正在检测授权状态)/.test(
    normalized,
  );
}

/** 替换消息行中临时的授权操作提示内容（如"等待授权..."）为完成消息 */
function replaceTransientAuthOperationContent(row, message) {
  if (!row) return false;
  const normalizedMessage = String(message || "").trim();
  if (!normalizedMessage || !isTransientAuthOperationContent(row.content)) {
    return false;
  }
  row.content = normalizedMessage;
  removeAssistantStatusNotes(row, isTransientExecutionStatusNote);
  return true;
}

function completePendingExternalOperationRequestByRow(
  row,
  message,
  { reject = false } = {},
) {
  if (!row) return false;
  const normalizedMessage = String(message || "").trim();
  let changed = false;
  const entries = Array.from(pendingRequests.entries());
  for (const [requestId, pending] of entries) {
    const pendingRow = messages.value[Number(pending?.assistantIndex ?? -1)];
    if (pendingRow !== row) continue;
    changed = true;
    if (reject) {
      rejectPendingRequest(
        requestId,
        pending,
        new Error(normalizedMessage || "操作未完成"),
      );
    } else {
      resolvePendingRequest(
        requestId,
        pending,
        row.content || normalizedMessage,
      );
    }
  }
  if (changed) {
    syncChatLoadingWithCurrentSession();
  }
  return changed;
}

function buildOperationResumeUserPrompt(resumeCommand, workflowKind = "") {
  const normalizedCommand = String(resumeCommand || "").trim();
  const normalizedWorkflowKind = String(workflowKind || "").trim();
  const completionText =
    normalizedWorkflowKind === "auth_login"
      ? "授权完成，检测通过。"
      : "操作完成。";
  if (!normalizedCommand) {
    return `${completionText}请继续刚才的任务。`;
  }
  return [
    completionText,
    "请不要再要求我重复完成同一个操作。",
    `直接继续执行之前待恢复的命令：${normalizedCommand}`,
  ].join("\n");
}

const findAssistantRowByAuthTaskId = findAssistantRowByOperationTaskId;
const completePendingAuthLoginRequest = completePendingExternalOperationRequest;
const buildAuthResumeUserPrompt = buildOperationResumeUserPrompt;

function buildTerminalChoiceChildren(componentName) {
  const interaction = terminalStructuredInteraction.value;
  return (interaction?.options || []).map((item) => ({
    componentName,
    attrs: {
      label: item.value,
      value: item.value,
    },
    children: item.label,
  }));
}

function cloneInteractionValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => cloneInteractionValue(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        cloneInteractionValue(item),
      ]),
    );
  }
  return value;
}

function normalizeInteractionSchema(rawSchema) {
  if (!rawSchema || typeof rawSchema !== "object") return null;
  const schema = Array.isArray(rawSchema.schema) ? rawSchema.schema : [];
  if (!schema.length) return null;
  const model =
    rawSchema.model && typeof rawSchema.model === "object"
      ? cloneInteractionValue(rawSchema.model)
      : {};
  return {
    title: String(
      rawSchema.title || rawSchema.label || "需要你继续操作",
    ).trim(),
    description: String(
      rawSchema.description || rawSchema.summary || "请完成下列表单后继续。",
    ).trim(),
    submitLabel: String(
      rawSchema.submit_label || rawSchema.submitLabel || "确认并继续",
    ).trim(),
    fallbackLabel: String(
      rawSchema.fallback_label || rawSchema.fallbackLabel || "使用终端兜底",
    ).trim(),
    responseMode: String(
      rawSchema.response_mode || rawSchema.responseMode || "",
    )
      .trim()
      .toLowerCase(),
    responseTemplate: String(
      rawSchema.response_template || rawSchema.responseTemplate || "",
    ).trim(),
    terminalSubmitContent: String(
      rawSchema.terminal_submit_content ||
        rawSchema.terminalSubmitContent ||
        "",
    ).trim(),
    rowAttrs:
      rawSchema.rowAttrs && typeof rawSchema.rowAttrs === "object"
        ? { ...rawSchema.rowAttrs }
        : { gutter: 12 },
    formAttrs:
      rawSchema.formAttrs && typeof rawSchema.formAttrs === "object"
        ? { ...rawSchema.formAttrs }
        : { "label-position": "top" },
    schema: cloneInteractionValue(schema),
    model,
  };
}

function operationInteractionSchema(operation) {
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  const rawSchema = meta.interaction_schema;
  return normalizeInteractionSchema(rawSchema);
}

function operationInteractionId(operation) {
  return String(operation?.id || operation?.operationId || "").trim();
}

function findMessageRowByOperationId(operationId) {
  return findMessageOperationById(operationId)?.row || null;
}

function findMessageOperationById(operationId) {
  const normalizedId = String(operationId || "").trim();
  if (!normalizedId) return null;
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    const row = messages.value[index];
    if (!Array.isArray(row?.operations)) continue;
    const operation = row.operations.find(
      (entry) =>
        String(entry?.id || "").trim() === normalizedId ||
        String(entry?.operationId || "").trim() === normalizedId,
    );
    if (operation) {
      return { row, index, operation };
    }
  }
  return null;
}

function agentRuntimeResumeToolArgs(toolCall) {
  const rawArguments = String(toolCall?.arguments || "").trim();
  if (!rawArguments) return {};
  try {
    const parsed = JSON.parse(rawArguments);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed
      : {};
  } catch (_error) {
    return {};
  }
}

function agentRuntimeResumeFirstRecord(resume) {
  const records = Array.isArray(resume?.records) ? resume.records : [];
  return records.find((item) => item && typeof item === "object") || null;
}

function agentRuntimeResumeAuthStatusLabel(rawResult = {}) {
  const stdout = String(rawResult?.stdout || "").trim();
  const stderr = String(rawResult?.stderr || rawResult?.error || "").trim();
  const text = [stdout, stderr].filter(Boolean).join("\n").toLowerCase();
  let payload = {};
  if (stdout) {
    try {
      const parsed = JSON.parse(stdout);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        payload = parsed;
      }
    } catch (_error) {
      payload = {};
    }
  }
  const statusValue = String(payload.status || payload.login_status || "")
    .trim()
    .toLowerCase();
  if (
    payload.ok === false ||
    payload.authenticated === false ||
    payload.logged_in === false ||
    ["unauthenticated", "not_logged_in", "logged_out", "invalid"].includes(
      statusValue,
    ) ||
    text.includes("not logged") ||
    text.includes("unauthenticated") ||
    text.includes("login required") ||
    text.includes("未登录")
  ) {
    return "未登录";
  }
  if (
    payload.ok === true ||
    payload.authenticated === true ||
    payload.logged_in === true ||
    ["authenticated", "logged_in", "valid", "success", "ok"].includes(
      statusValue,
    )
  ) {
    return "已登录";
  }
  const exitCode = Number(rawResult?.exit_code);
  if (Number.isFinite(exitCode) && exitCode === 0) {
    return "已登录";
  }
  return "未确认";
}

function agentRuntimeResumeFallbackContent(resume) {
  const record = agentRuntimeResumeFirstRecord(resume);
  if (!record) return "";
  const rawResult =
    record.raw_result && typeof record.raw_result === "object"
      ? record.raw_result
      : {};
  const toolCall =
    record.tool_call && typeof record.tool_call === "object"
      ? record.tool_call
      : {};
  const args = agentRuntimeResumeToolArgs(toolCall);
  const command = String(args.command || rawResult.command || "").trim();
  const signature = agentRuntimeCommandSignatureFromArgs({ command });
  const stdout = String(rawResult.stdout || "").trim();
  const stderr = String(rawResult.stderr || rawResult.error || "").trim();
  const output = stdout || stderr;
  if (signature === "lark-cli auth status") {
    const lines = [
      `登录状态：${agentRuntimeResumeAuthStatusLabel(rawResult)}。`,
    ];
    if (command) {
      lines.push(`已执行命令：\`${command}\`。`);
    }
    if (output) {
      lines.push(`命令输出：${output}`);
    }
    return lines.join("\n").trim();
  }
  if (!command && !output) return "";
  const lines = [];
  if (command) {
    lines.push(`授权后已执行命令：\`${command}\`。`);
  }
  if (rawResult.exit_code !== undefined && rawResult.exit_code !== null) {
    lines.push(`退出码：${rawResult.exit_code}。`);
  }
  if (output) {
    lines.push(`输出：${output}`);
  }
  return lines.join("\n").trim();
}

function agentRuntimeResumeIsProcessOnlyContent(content) {
  const normalized = String(content || "").replace(/\s+/g, "");
  return (
    !normalized ||
    [
      "本轮执行已结束",
      "工具调用权限已确认",
      "工具调用授权已保存",
      "运行任务已结束",
      "运行任务已完成",
      "后台执行已完成",
    ].includes(normalized)
  );
}

function agentRuntimeResumeIsStableToolAnswer(resume, fallbackContent) {
  if (!fallbackContent) return false;
  const record = agentRuntimeResumeFirstRecord(resume);
  if (!record) return false;
  const rawResult =
    record.raw_result && typeof record.raw_result === "object"
      ? record.raw_result
      : {};
  const toolCall =
    record.tool_call && typeof record.tool_call === "object"
      ? record.tool_call
      : {};
  const args = agentRuntimeResumeToolArgs(toolCall);
  const command = String(args.command || rawResult.command || "").trim();
  return (
    agentRuntimeCommandSignatureFromArgs({ command }) === "lark-cli auth status"
  );
}

function agentRuntimeResumeFinalContent(resume) {
  const continuation =
    resume?.continuation && typeof resume.continuation === "object"
      ? resume.continuation
      : null;
  const continuationContent = String(continuation?.final_content || "").trim();
  if (
    continuationContent &&
    !agentRuntimeResumeIsProcessOnlyContent(continuationContent)
  ) {
    return continuationContent;
  }
  return "";
}

function agentRuntimeResumeStatus(resume) {
  const status = String(resume?.status || "")
    .trim()
    .toLowerCase();
  if (status) return status;
  const continuation =
    resume?.continuation && typeof resume.continuation === "object"
      ? resume.continuation
      : null;
  return String(continuation?.status || "")
    .trim()
    .toLowerCase();
}

function agentRuntimeResumeMissingFinalAnswer(resume) {
  const continuation =
    resume?.continuation && typeof resume.continuation === "object"
      ? resume.continuation
      : null;
  const decision =
    continuation?.completion_decision &&
    typeof continuation.completion_decision === "object"
      ? continuation.completion_decision
      : null;
  const reasons = Array.isArray(decision?.reasons)
    ? decision.reasons.map((item) => String(item || "").trim())
    : [];
  return (
    agentRuntimeResumeStatus(resume) === "failed" &&
    reasons.includes("missing_final_response_after_tool")
  );
}

function agentRuntimeMissingFinalAnswerMessage() {
  return "工具执行已经完成，但模型没有继续生成最终回答。本轮未完成，请重新运行或检查模型续写链路。";
}

function completePendingRequestForAssistantRow(row) {
  if (!row) return;
  const entries = Array.from(pendingRequests.entries());
  for (const [requestId, pending] of entries) {
    const pendingRow = messages.value[Number(pending?.assistantIndex ?? -1)];
    if (pendingRow !== row) continue;
    resolvePendingRequest(requestId, pending, row.content || "");
  }
  syncChatLoadingWithCurrentSession();
}

function completeAgentRuntimeOperationsForRun(row, runId) {
  const normalizedRunId = String(runId || "").trim();
  if (!row || !normalizedRunId || !Array.isArray(row.operations)) return;
  row.operations = row.operations.map((operation) => {
    const meta =
      operation?.meta && typeof operation.meta === "object"
        ? operation.meta
        : {};
    if (String(meta.run_id || "").trim() !== normalizedRunId) {
      return operation;
    }
    const phase = normalizeOperationPhase(operation?.phase);
    if (!["running", "waiting_user"].includes(phase)) {
      return operation;
    }
    return {
      ...operation,
      phase: "completed",
      actionType: "none",
      updatedAt: nowText(),
    };
  });
}

function closeOpenAgentRuntimeOperationsForCompletedTurn(
  sourceRow,
  summary = "",
) {
  const finalSummary = String(summary || "").trim() || "本轮执行已结束";
  const sourceIndex = messages.value.findIndex((item) => item === sourceRow);
  const sourceChatSessionId = String(currentChatSessionId.value || "").trim();
  let changed = false;
  const closeRow = (row) => {
    if (
      !row ||
      String(row.role || "").trim() !== "assistant" ||
      !Array.isArray(row.operations)
    ) {
      return false;
    }
    let rowChanged = false;
    row.operations = row.operations.map((operation) => {
      const phase = normalizeOperationPhase(
        operation?.phase || operation?.status,
      );
      if (!["running", "pending"].includes(phase)) return operation;
      const meta =
        operation?.meta && typeof operation.meta === "object"
          ? operation.meta
          : {};
      const operationChatSessionId = String(meta.chat_session_id || "").trim();
      const isRuntimeOperation =
        String(meta.agent_runtime_event || "").trim() === "true" ||
        Boolean(String(meta.run_id || "").trim());
      if (!isRuntimeOperation) return operation;
      if (
        sourceChatSessionId &&
        operationChatSessionId &&
        operationChatSessionId !== sourceChatSessionId
      ) {
        return operation;
      }
      rowChanged = true;
      changed = true;
      return {
        ...operation,
        phase: "completed",
        actionType: "none",
        summary: finalSummary,
        updatedAt: nowText(),
      };
    });
    if (rowChanged && row !== sourceRow) {
      appendMessageProcessLog(row, {
        level: "success",
        text: finalSummary,
      });
    }
    return rowChanged;
  };
  changed = closeRow(sourceRow) || changed;
  const startIndex =
    sourceIndex >= 0
      ? Math.min(sourceIndex - 1, messages.value.length - 1)
      : messages.value.length - 1;
  for (let index = startIndex; index >= 0; index -= 1) {
    const row = messages.value[index];
    if (closeRow(row)) {
      changed = true;
      break;
    }
  }
  return changed;
}

function findMessageRowByAgentRuntimePermission(
  runId,
  callId,
  commandSignature = "",
) {
  const normalizedRunId = String(runId || "").trim();
  const normalizedCallId = String(callId || "").trim();
  const normalizedSignature = String(commandSignature || "").trim();
  if (!normalizedRunId || (!normalizedCallId && !normalizedSignature))
    return null;
  return (
    messages.value.find((item) =>
      Array.isArray(item?.operations)
        ? item.operations.some((operation) => {
            const meta =
              operation?.meta && typeof operation.meta === "object"
                ? operation.meta
                : {};
            return (
              String(meta.agent_runtime_permission || "").trim() === "true" &&
              String(meta.run_id || "").trim() === normalizedRunId &&
              (String(meta.call_id || "").trim() === normalizedCallId ||
                (normalizedSignature &&
                  String(meta.command_signature || "").trim() ===
                    normalizedSignature))
            );
          })
        : false,
    ) || null
  );
}

function findAgentRuntimePermissionOperation(
  row,
  runId,
  callId,
  commandSignature = "",
) {
  const normalizedRunId = String(runId || "").trim();
  const normalizedCallId = String(callId || "").trim();
  const normalizedSignature = String(commandSignature || "").trim();
  if (!row || !Array.isArray(row.operations) || !normalizedRunId) return null;
  return (
    row.operations.find((operation) => {
      const meta =
        operation?.meta && typeof operation.meta === "object"
          ? operation.meta
          : {};
      return (
        String(meta.agent_runtime_permission || "").trim() === "true" &&
        String(meta.run_id || "").trim() === normalizedRunId &&
        (String(meta.call_id || "").trim() === normalizedCallId ||
          (normalizedSignature &&
            String(meta.command_signature || "").trim() ===
              normalizedSignature))
      );
    }) || null
  );
}

function latestAgentRuntimePermissionOperation(operation) {
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  const row =
    findMessageRowByAgentRuntimePermission(
      meta.run_id,
      meta.call_id,
      meta.command_signature,
    ) || findMessageRowByOperationId(operation?.id);
  return (
    findAgentRuntimePermissionOperation(
      row,
      meta.run_id,
      meta.call_id,
      meta.command_signature,
    ) || operation
  );
}

function updateAgentRuntimePermissionOperations(row, runId, callId, patch) {
  const normalizedRunId = String(runId || "").trim();
  const normalizedCallId = String(callId || "").trim();
  const normalizedSignature = String(
    patch?.meta?.command_signature || patch?.command_signature || "",
  ).trim();
  if (!row || !normalizedRunId || (!normalizedCallId && !normalizedSignature))
    return false;
  const items = Array.isArray(row.operations) ? row.operations.slice() : [];
  let changed = false;
  row.operations = items.map((operation) => {
    const meta =
      operation?.meta && typeof operation.meta === "object"
        ? operation.meta
        : {};
    const matched =
      String(meta.agent_runtime_permission || "").trim() === "true" &&
      String(meta.run_id || "").trim() === normalizedRunId &&
      (String(meta.call_id || "").trim() === normalizedCallId ||
        (normalizedSignature &&
          String(meta.command_signature || "").trim() === normalizedSignature));
    if (!matched) return operation;
    changed = true;
    return {
      ...operation,
      ...patch,
      meta: {
        ...meta,
        ...(patch?.meta && typeof patch.meta === "object" ? patch.meta : {}),
      },
      updatedAt: nowText(),
    };
  });
  return changed;
}

function applyAgentRuntimeResumeToAssistantMessage(row, resume, options = {}) {
  const finalContent = agentRuntimeResumeFinalContent(resume);
  if (!row || !finalContent) return false;
  row.content = finalContent;
  removeAssistantStatusNotes(row, isTransientExecutionStatusNote);
  completeAgentRuntimeOperationsForRun(row, options.runId);
  row.processExpanded = false;
  completePendingRequestForAssistantRow(row);
  return true;
}

function applyRealtimeChatMessagePayload(eventData) {
  const messagePayload =
    eventData?.message && typeof eventData.message === "object"
      ? eventData.message
      : null;
  const chatSessionId = String(
    eventData?.chat_session_id || messagePayload?.chat_session_id || "",
  ).trim();
  if (eventData?.session) {
    upsertChatSessionFromRealtime(eventData.session);
  }
  if (
    !messagePayload ||
    !chatSessionId ||
    chatSessionId !== String(currentChatSessionId.value || "").trim()
  ) {
    return null;
  }
  const row = mapHistoryMessage(messagePayload);
  if (!row.id) return null;
  const existingIndex = messages.value.findIndex(
    (item) => String(item?.id || "") === row.id,
  );
  if (existingIndex >= 0) {
    const existing = messages.value[existingIndex];
    const hasNextContent = Boolean(String(row.content || "").trim());
    const nextOperations = mergeMessageOperations(
      existing.operations,
      row.operations,
    );
    const nextProcessLog = row.processLog.length
      ? row.processLog
      : Array.isArray(existing.processLog)
        ? existing.processLog
        : [];
    messages.value[existingIndex] = {
      ...existing,
      ...row,
      operations: nextOperations,
      terminalLog: row.terminalLog.length
        ? row.terminalLog
        : Array.isArray(existing.terminalLog)
          ? existing.terminalLog
          : [],
      processLog: nextProcessLog,
      statusNotes: Array.isArray(existing.statusNotes)
        ? existing.statusNotes
        : row.statusNotes,
      processExpanded: hasNextContent
        ? Boolean(nextProcessLog.length || nextOperations.length)
        : Boolean(existing.processExpanded || row.processExpanded),
    };
    if (hasNextContent) {
      completePendingRequestForAssistantRow(messages.value[existingIndex]);
    }
    return messages.value[existingIndex];
  }
  messages.value = [...messages.value, row];
  chatHistoryLoadedCount.value = messages.value.length;
  return row;
}

function operationInteractionModel(operation) {
  const interactionId = operationInteractionId(operation);
  if (!interactionId) return {};
  const current = operationInteractionFormModels.value[interactionId];
  if (current && typeof current === "object") {
    return current;
  }
  const schema = operationInteractionSchema(operation);
  const nextModel =
    schema?.model && typeof schema.model === "object"
      ? cloneInteractionValue(schema.model)
      : {};
  operationInteractionFormModels.value = {
    ...operationInteractionFormModels.value,
    [interactionId]: nextModel,
  };
  return nextModel;
}

function syncOperationInteractionModel(operation) {
  const interactionId = operationInteractionId(operation);
  const schema = operationInteractionSchema(operation);
  if (!interactionId || !schema) return null;
  const current = operationInteractionFormModels.value[interactionId];
  if (current && typeof current === "object") {
    return current;
  }
  return operationInteractionModel(operation);
}

function operationInteractionSubmittedHint(operation) {
  const interactionId = operationInteractionId(operation);
  if (!interactionId) return "";
  return String(
    operationInteractionSubmissionHints.value[interactionId] || "",
  ).trim();
}

function setOperationInteractionSubmittedHint(operation, text) {
  const interactionId = operationInteractionId(operation);
  if (!interactionId) return;
  operationInteractionSubmissionHints.value = {
    ...operationInteractionSubmissionHints.value,
    [interactionId]: String(text || "").trim(),
  };
}

function dismissOperationInteractionForm(operation) {
  const interactionId = operationInteractionId(operation);
  if (!interactionId) return;
  const next = new Set(dismissedOperationInteractionIds.value);
  next.add(interactionId);
  dismissedOperationInteractionIds.value = next;
}

function operationInteractionCanFallbackToTerminal(operation) {
  const actionType = normalizeOperationActionType(operation?.actionType);
  const kind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  return actionType === "enter_text" || kind === "terminal";
}

function operationInteractionTitle(operation) {
  const schema = operationInteractionSchema(operation);
  return (
    String(schema?.title || operation?.title || "需要你继续操作").trim() ||
    "需要你继续操作"
  );
}

function operationInteractionDescription(operation) {
  const schema = operationInteractionSchema(operation);
  return (
    String(
      schema?.description || operation?.summary || "请完成当前交互后继续。",
    ).trim() || "请完成当前交互后继续。"
  );
}

function operationInteractionSubmitLabel(operation) {
  const schema = operationInteractionSchema(operation);
  return String(schema?.submitLabel || "确认并继续").trim() || "确认并继续";
}

function operationInteractionFallbackLabel(operation) {
  const schema = operationInteractionSchema(operation);
  return (
    String(schema?.fallbackLabel || "使用终端兜底").trim() || "使用终端兜底"
  );
}

function messageOperationInteractionFormJson(operation) {
  const interactionId = operationInteractionId(operation);
  if (!interactionId) return null;
  if (dismissedOperationInteractionIds.value.has(interactionId)) {
    return null;
  }
  const schema = operationInteractionSchema(operation);
  if (!schema) return null;
  if (!isOperationAwaitingInteraction(operation)) return null;
  return {
    rowAttrs: schema.rowAttrs,
    formAttrs: schema.formAttrs,
    model: syncOperationInteractionModel(operation),
    schema: schema.schema,
  };
}

function isEmptyInteractionValue(value) {
  if (Array.isArray(value)) return value.length === 0;
  if (value && typeof value === "object")
    return Object.keys(value).length === 0;
  return String(value ?? "").trim() === "";
}

function canSubmitOperationInteraction(operation) {
  const schema = operationInteractionSchema(operation);
  if (!schema) return false;
  const model = operationInteractionModel(operation);
  const requiredProps = schema.schema
    .filter((item) => item && item.required)
    .map((item) => String(item.prop || "").trim())
    .filter(Boolean);
  if (requiredProps.length) {
    return requiredProps.every(
      (prop) => !isEmptyInteractionValue(model?.[prop]),
    );
  }
  return schema.schema.some((item) => {
    const prop = String(item?.prop || "").trim();
    return prop ? !isEmptyInteractionValue(model?.[prop]) : false;
  });
}

function formatOperationInteractionPayload(operation) {
  const schema = operationInteractionSchema(operation);
  const model = operationInteractionModel(operation);
  if (!schema) return "";
  if (schema.terminalSubmitContent) {
    return schema.terminalSubmitContent;
  }
  if (schema.responseTemplate) {
    return schema.responseTemplate.replace(
      /\{\{\s*([\w.-]+)\s*\}\}/g,
      (_match, token) => {
        const value = model?.[token];
        return Array.isArray(value) ? value.join("、") : String(value ?? "");
      },
    );
  }
  const actionTitle = operationInteractionTitle(operation);
  const lines = [`${actionTitle}：`];
  schema.schema.forEach((item) => {
    const prop = String(item?.prop || "").trim();
    if (!prop) return;
    const label = String(item?.label || prop).trim();
    const value = model?.[prop];
    if (isEmptyInteractionValue(value)) return;
    lines.push(
      `${label}：${Array.isArray(value) ? value.join("、") : String(value ?? "").trim()}`,
    );
  });
  return lines.join("\n");
}

const terminalInteractionFormJson = computed(() => {
  const interaction = terminalStructuredInteraction.value;
  const isMulti = interaction?.type === "checkbox";
  return {
    rowAttrs: { gutter: 12 },
    formAttrs: { "label-position": "top" },
    model: terminalStructuredFormModel.value,
    schema: interaction
      ? [
          {
            label: interaction.fieldLabel || "请选择",
            prop: isMulti ? "choices" : "choice",
            componentName: isMulti ? "ElCheckboxGroup" : "ElRadioGroup",
            colAttrs: { span: 24 },
            attrs: {
              class: isMulti
                ? "message-terminal-form__checkbox-group"
                : "message-terminal-form__radio-group",
            },
            rules: [
              isMulti
                ? {
                    required: true,
                    type: "array",
                    min: 1,
                    message: "请至少选择一项",
                    trigger: "change",
                  }
                : {
                    required: true,
                    message: "请选择一项",
                    trigger: "change",
                  },
            ],
            children: buildTerminalChoiceChildren(
              isMulti ? "ElCheckbox" : "ElRadio",
            ),
          },
        ]
      : [],
  };
});

const canSubmitTerminalStructuredInteraction = computed(() => {
  const interaction = terminalStructuredInteraction.value;
  if (!interaction) return false;
  if (interaction.type === "checkbox") {
    const choices = Array.isArray(terminalStructuredFormModel.value?.choices)
      ? terminalStructuredFormModel.value.choices
      : [];
    return Boolean(choices.length);
  }
  return Boolean(
    String(terminalStructuredFormModel.value?.choice || "").trim(),
  );
});

function terminalInteractionDismissKey(interaction) {
  if (!interaction) return "";
  return `${Number(interaction.assistantIndex)}:${String(interaction.type || "choice")}:${String(interaction.key || "")}`;
}

function rememberDismissedTerminalStructuredInteraction(interaction) {
  const dismissKey = terminalInteractionDismissKey(interaction);
  if (!dismissKey) return;
  const nextKeys = new Set(terminalDismissedStructuredInteractionKeys.value);
  nextKeys.add(dismissKey);
  terminalDismissedStructuredInteractionKeys.value = nextKeys;
}

function scheduleTerminalStructuredInteractionRefresh(row, index) {
  if (!row || terminalStructuredInteractionRefreshPending) return;
  terminalStructuredInteractionRefreshPending = true;
  Promise.resolve().then(() => {
    terminalStructuredInteractionRefreshPending = false;
    if (!terminalStructuredInteraction.value) {
      refreshTerminalStructuredInteraction(row, index);
    }
  });
}

function terminalStructuredSubmissionHintForMessage(index) {
  const hint = terminalStructuredSubmissionHint.value;
  if (!hint) return "";
  return Number(hint.assistantIndex) === Number(index)
    ? String(hint.text || "")
    : "";
}

function terminalInteractionFormForMessage(row, index) {
  if (!terminalStructuredInteraction.value && row) {
    scheduleTerminalStructuredInteractionRefresh(row, index);
  }
  const interaction = terminalStructuredInteraction.value;
  if (!interaction) return false;
  return Number(interaction.assistantIndex) === Number(index);
}

function markTerminalInteractionOperationRunning(assistantIndex) {
  const row = messages.value[Number(assistantIndex)];
  if (!row || !Array.isArray(row.operations)) return;
  row.operations = row.operations.map((operation) => {
    if (
      String(operation?.kind || "")
        .trim()
        .toLowerCase() !== "terminal"
    ) {
      return operation;
    }
    const phase = normalizeOperationPhase(
      operation?.phase || operation?.status,
    );
    if (!["waiting_user", "running"].includes(phase)) return operation;
    return {
      ...operation,
      title: "终端继续执行中",
      phase: "running",
      actionType: "none",
      summary: "已提交选择，正在等待后续输出",
      detail: "",
      updatedAt: nowText(),
    };
  });
}

function markTerminalInteractionContentSubmitted(assistantIndex) {
  const row = messages.value[Number(assistantIndex)];
  if (!row) return;
  const current = String(row.content || "").trim();
  const submittedText =
    "已提交表单选择，终端正在继续执行；如果打开了浏览器授权，请在浏览器完成后回到这里。";
  if (
    !current ||
    /请根据下方表单或终端提示完成交互|命令已进入交互模式|需要你继续操作/.test(
      current,
    )
  ) {
    row.content = submittedText;
  }
}

function dismissTerminalStructuredInteraction() {
  rememberDismissedTerminalStructuredInteraction(
    terminalStructuredInteraction.value,
  );
  terminalStructuredInteraction.value = null;
}

function detectTerminalChoiceInteraction(row, assistantIndex) {
  const lines = terminalLogLines(row);
  if (!lines.length) return null;
  const recentLines = lines.slice(-80);
  const text = recentLines.join("\n");
  const activeCommand = String(terminalActiveCommand.value || "").trim();
  const fallbackProvider = TERMINAL_CHOICE_FALLBACK_PROVIDERS.find((provider) =>
    provider.match({ text, lines: recentLines, activeCommand, row }),
  );
  let parsedOptions = [];
  let highlightedIndex = 0;
  if (fallbackProvider) {
    parsedOptions = fallbackProvider.options({
      text,
      lines: recentLines,
      activeCommand,
      row,
    });
  } else {
    if (
      !/(选择|请选择|至少选择|select|choose|toggle|enter confirm)/i.test(text)
    ) {
      return null;
    }
    if (!hasTerminalChoiceControlSignal(recentLines, text)) {
      return null;
    }
    recentLines.forEach((line) => {
      const option = parseTerminalChoiceLine(line);
      if (!option) return;
      if (parsedOptions.some((item) => item.value === option.value)) return;
      if (option.highlighted) highlightedIndex = parsedOptions.length;
      parsedOptions.push(option);
    });
  }
  if (parsedOptions.length < 2) return null;
  const selectedValues = parsedOptions
    .filter((item) => item.selected)
    .map((item) => item.value);
  const interactionType = inferTerminalChoiceType(text, parsedOptions);
  const selectedValue =
    selectedValues[0] ||
    parsedOptions.find((item) => item.highlighted)?.value ||
    parsedOptions[0]?.value ||
    "";
  const promptLine = [...recentLines]
    .reverse()
    .find((line) => /(选择|请选择|至少选择|select|choose)/i.test(line));
  return {
    key: parsedOptions.map((item) => item.value).join("|"),
    assistantIndex: Number(assistantIndex),
    type: interactionType,
    title: "需要你选择后继续",
    description: terminalChoiceDescription(interactionType),
    fieldLabel: String(promptLine || "选择选项")
      .replace(/^\*\s*/, "")
      .trim(),
    options: parsedOptions,
    selectedValues,
    selectedValue,
    highlightedIndex,
  };
}

function refreshTerminalStructuredInteraction(
  row,
  assistantIndexOverride = null,
) {
  const fallbackIndex = Number(activeTerminalMirrorAssistantIndex.value ?? -1);
  const assistantIndex =
    assistantIndexOverride === null || assistantIndexOverride === undefined
      ? fallbackIndex
      : Number(assistantIndexOverride);
  if (assistantIndex < 0) {
    return;
  }
  const interaction = detectTerminalChoiceInteraction(row, assistantIndex);
  if (!interaction) {
    return;
  }
  if (
    terminalDismissedStructuredInteractionKeys.value.has(
      terminalInteractionDismissKey(interaction),
    )
  ) {
    return;
  }
  const current = terminalStructuredInteraction.value;
  const currentChoices = Array.isArray(
    terminalStructuredFormModel.value?.choices,
  )
    ? terminalStructuredFormModel.value.choices
    : [];
  const currentChoice = String(
    terminalStructuredFormModel.value?.choice || "",
  ).trim();
  terminalStructuredSubmissionHint.value = null;
  terminalStructuredInteraction.value = interaction;
  if (interaction.type === "checkbox") {
    terminalStructuredFormModel.value = {
      choices:
        current?.key === interaction.key && currentChoices.length
          ? currentChoices.filter((item) =>
              interaction.options.some((option) => option.value === item),
            )
          : interaction.selectedValues,
      choice: "",
    };
    return;
  }
  terminalStructuredFormModel.value = {
    choices: [],
    choice:
      current?.key === interaction.key &&
      currentChoice &&
      interaction.options.some((option) => option.value === currentChoice)
        ? currentChoice
        : interaction.selectedValue,
  };
}

async function submitTerminalStructuredInteraction() {
  const interaction = terminalStructuredInteraction.value;
  if (!interaction) return;
  const isMulti = interaction.type === "checkbox";
  const choices = Array.isArray(terminalStructuredFormModel.value?.choices)
    ? terminalStructuredFormModel.value.choices.map((item) =>
        String(item || "").trim(),
      )
    : [];
  const choice = String(terminalStructuredFormModel.value?.choice || "").trim();
  if (isMulti ? !choices.length : !choice) {
    ElMessage.warning(isMulti ? "请至少选择一项" : "请选择一项");
    return;
  }
  let content = "";
  const upCount = Math.max(0, Number(interaction.highlightedIndex || 0));
  content += "\u001b[A".repeat(upCount);
  if (isMulti) {
    const selectedSet = new Set(choices);
    interaction.options.forEach((option, index) => {
      const shouldSelect = selectedSet.has(option.value);
      if (Boolean(option.selected) !== shouldSelect) {
        content += " ";
      }
      if (index < interaction.options.length - 1) {
        content += "\u001b[B";
      }
    });
  } else {
    const targetIndex = Math.max(
      0,
      interaction.options.findIndex((option) => option.value === choice),
    );
    content += "\u001b[B".repeat(targetIndex);
  }
  content += "\r";
  const sent = await sendTerminalMirrorContent(content, {
    appendNewline: false,
    allowBlank: true,
    echo: false,
  });
  if (!sent) return;
  rememberDismissedTerminalStructuredInteraction(interaction);
  terminalStructuredSubmissionHint.value = {
    assistantIndex: Number(interaction.assistantIndex),
    text: "已提交选择，终端已继续执行；如果弹出浏览器授权，请在浏览器完成后回到这里。",
  };
  markTerminalInteractionOperationRunning(interaction.assistantIndex);
  markTerminalInteractionContentSubmitted(interaction.assistantIndex);
}

async function continueChatWithInteractionPayload(payloadText) {
  const text = String(payloadText || "").trim();
  if (!text) return false;
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return false;
  let activeChatSessionId = String(currentChatSessionId.value || "").trim();
  if (!activeChatSessionId) {
    const created = await createChatSession({ switchTo: true });
    activeChatSessionId = String(created?.id || "").trim();
    if (!activeChatSessionId) {
      return false;
    }
  }
  const activeSessionSourceContext = normalizeChatSourceContext(
    currentChatSession.value || {},
  );
  const historyRows = toHistoryRows(messages.value, historyLimit.value);
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
    effectiveTools: [],
    effectiveToolTotal: 0,
    terminalLog: [],
    processExpanded: false,
    audit: null,
    taskTreeAudit: null,
    statusNotes: [],
    operations: [],
    time: nowText(),
  };
  messages.value.push(userMessage);
  messages.value.push(assistantMessage);
  const assistantIndex = messages.value.length - 1;
  chatLoading.value = true;
  scrollToBottom();
  try {
    await sendProjectChatRequest({
      projectId,
      activeChatSessionId,
      userMessageId: userMessage.id,
      assistantMessage,
      assistantIndex,
      finalUserPrompt: appendModelGenerationInstruction(text),
      activeSessionSourceContext,
      historyRows,
      effectiveAutoUseTools: projectChatToolsExplicitlyEnabled(),
      effectiveToolPriority: mergeToolPriority(
        projectChatSettings.value.tool_priority || [],
        [],
      ),
      assistAction: null,
      assistToolNames: [],
    });
    return true;
  } catch (err) {
    messages.value[assistantIndex].content =
      `请求失败：${err?.message || "未知错误"}`;
    ElMessage.error(err?.message || "交互提交失败");
    return false;
  } finally {
    syncChatLoadingWithCurrentSession();
    scrollToBottom();
  }
}

async function sendInteractionSubmitRequest(operation, payloadText) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return false;
  let activeChatSessionId = String(currentChatSessionId.value || "").trim();
  if (!activeChatSessionId) {
    const created = await createChatSession({ switchTo: true });
    activeChatSessionId = String(created?.id || "").trim();
    if (!activeChatSessionId) {
      return false;
    }
  }
  const interactionId = operationInteractionId(operation);
  const sourceRow = findMessageRowByOperationId(interactionId);
  const schema = operationInteractionSchema(operation);
  const model = cloneInteractionValue(operationInteractionModel(operation));
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
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
    taskTreeAudit: null,
    statusNotes: [],
    operations: [],
    time: nowText(),
  };
  messages.value.push(assistantMessage);
  const assistantIndex = messages.value.length - 1;
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const client = await ensureWsClient(projectId);
  const donePromise = new Promise((resolve, reject) => {
    pendingRequests.set(requestId, {
      resolve,
      reject,
      requestId,
      projectId,
      chatSessionId: activeChatSessionId,
      chatMode: "system",
      assistantMessageId: String(assistantMessage?.id || "").trim(),
      assistantIndex,
      userPrompt: payloadText,
      mcpApprovalCancelled: false,
      awaitingTerminalApproval: false,
      handoffTriggered: false,
      projectHostTerminalHandoffTriggered: false,
      lastToolName: "",
    });
    trackPendingRequest(requestId);
  });
  chatLoading.value = true;
  scrollToBottom();
  client.send({
    type: "interaction_submit",
    request_id: requestId,
    assistant_message_id: String(assistantMessage?.id || "").trim(),
    chat_session_id: activeChatSessionId,
    chat_mode: "system",
    chat_surface: chatSurface.value,
    source_context: normalizeChatSourceContext(currentChatSession.value || {}),
    skill_resource_directory: String(
      skillResourceDirectoryResolved.value || "",
    ).trim(),
    employee_ids: normalizeStringList(selectedEmployeeIds.value || []),
    employee_id:
      normalizeStringList(selectedEmployeeIds.value || []).length === 1
        ? normalizeStringList(selectedEmployeeIds.value || [])[0]
        : undefined,
    employee_coordination_mode: String(
      projectChatSettings.value.employee_coordination_mode ||
        CHAT_SETTINGS_DEFAULTS.employee_coordination_mode,
    )
      .trim()
      .toLowerCase(),
    history: toHistoryRows(messages.value.slice(0, -1), historyLimit.value),
    provider_id: selectedProviderId.value || undefined,
    model_name: selectedModelName.value || undefined,
    temperature: Number(temperature.value),
    max_tokens: Number(chatMaxTokens.value || 512),
    system_prompt: systemPrompt.value || undefined,
    auto_use_tools: projectChatToolsExplicitlyEnabled(),
    tool_priority: mergeToolPriority(
      projectChatSettings.value.tool_priority || [],
      [],
    ),
    max_tool_calls_per_round: resolveNumericChatSetting(
      projectChatSettings.value.max_tool_calls_per_round,
      CHAT_SETTINGS_DEFAULTS.max_tool_calls_per_round,
      { min: 1, max: 30 },
    ),
    max_loop_rounds: resolveNumericChatSetting(
      projectChatSettings.value.max_loop_rounds,
      CHAT_SETTINGS_DEFAULTS.max_loop_rounds,
      { min: 1, max: 60 },
    ),
    max_tool_rounds: resolveNumericChatSetting(
      projectChatSettings.value.max_tool_rounds,
      CHAT_SETTINGS_DEFAULTS.max_tool_rounds,
      { min: 1, max: 30 },
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
    history_limit: resolveNumericChatSetting(
      projectChatSettings.value.history_limit,
      CHAT_SETTINGS_DEFAULTS.history_limit,
      { min: 1, max: 50 },
    ),
    tool_timeout_sec: resolveNumericChatSetting(
      projectChatSettings.value.tool_timeout_sec,
      CHAT_SETTINGS_DEFAULTS.tool_timeout_sec,
      { min: 0, max: 600 },
    ),
    tool_retry_count: resolveNumericChatSetting(
      projectChatSettings.value.tool_retry_count,
      CHAT_SETTINGS_DEFAULTS.tool_retry_count,
      { min: 0, max: 5 },
    ),
    answer_style: String(
      projectChatSettings.value.answer_style ||
        CHAT_SETTINGS_DEFAULTS.answer_style,
    ),
    prefer_conclusion_first: Boolean(
      projectChatSettings.value.prefer_conclusion_first ??
      CHAT_SETTINGS_DEFAULTS.prefer_conclusion_first,
    ),
    enabled_project_tool_names: normalizeStringList(
      selectedProjectToolNames.value || [],
      200,
    ),
    interaction_id: interactionId,
    interaction_operation_id: String(
      operation?.operationId || interactionId,
    ).trim(),
    interaction_title: operationInteractionTitle(operation),
    interaction_action_type: normalizeOperationActionType(
      operation?.actionType,
    ),
    interaction_message: payloadText,
    interaction_schema: schema ? cloneInteractionValue(schema) : null,
    interaction_data: model,
    workflow_kind: String(meta.workflow_kind || "").trim(),
    workflow_state:
      meta.workflow_state && typeof meta.workflow_state === "object"
        ? cloneInteractionValue(meta.workflow_state)
        : null,
    resume_command: String(meta.resume_command || "").trim(),
  });
  try {
    await donePromise;
    return true;
  } catch (err) {
    assistantMessage.content = `请求失败：${err?.message || "未知错误"}`;
    ElMessage.error(err?.message || "交互提交失败");
    return false;
  } finally {
    syncChatLoadingWithCurrentSession();
    if (sourceRow) {
      sourceRow.processExpanded = true;
    }
    scrollToBottom();
  }
}

async function submitOperationInteraction(operation) {
  const schema = operationInteractionSchema(operation);
  if (!schema) return;
  if (!canSubmitOperationInteraction(operation)) {
    ElMessage.warning("请先完成必填项");
    return;
  }
  const payloadText = formatOperationInteractionPayload(operation);
  if (!payloadText) {
    ElMessage.warning("当前交互内容为空，无法继续");
    return;
  }
  let submitted = false;
  if (operationInteractionCanFallbackToTerminal(operation)) {
    submitted = await sendTerminalMirrorContent(payloadText, {
      echo: false,
    });
  } else {
    submitted = await sendInteractionSubmitRequest(operation, payloadText);
  }
  if (!submitted) return;
  setOperationInteractionSubmittedHint(
    operation,
    operationInteractionCanFallbackToTerminal(operation)
      ? "已提交结构化交互，等待终端后续输出。"
      : "已提交结构化表单，等待后续授权或操作完成。",
  );
  dismissOperationInteractionForm(operation);
  upsertMessageOperation(findMessageRowByOperationId(operation.id), {
    ...operation,
    phase: "running",
    summary: operationInteractionCanFallbackToTerminal(operation)
      ? "已提交结构化交互，等待终端后续输出"
      : "已提交结构化交互，等待后续授权或操作完成",
    detail: "",
    actionType: "none",
  });
}

async function handleOperationPrimaryAction(operation) {
  const buttons = operationActionButtons(operation);
  if (!buttons.length) return;
  await handleOperationAction(operation, buttons[0].key);
}

function operationActionButtons(operation) {
  const actionType = normalizeOperationActionType(operation?.actionType);
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  if (actionType === "open_url" && extractOperationUrl(operation)) {
    return [{ key: "open_url", label: "打开链接" }];
  }
  if (actionType === "enter_text") {
    const kind = String(operation?.kind || "")
      .trim()
      .toLowerCase();
    if (kind === "terminal") {
      if (terminalStructuredInteraction.value) return [];
      return [{ key: "terminal_ctrl_c", label: "中止", type: "danger" }];
    }
  }
  if (actionType === "approve") {
    if (String(meta.agent_runtime_permission || "").trim() === "true") {
      return [
        { key: "agent_runtime_allow_once", label: "允许一次" },
        { key: "agent_runtime_allow_session", label: "本会话允许" },
        { key: "agent_runtime_allow_always", label: "始终允许" },
        { key: "agent_runtime_deny", label: "拒绝", type: "danger" },
      ];
    }
    if (String(meta.approval_mode || "").trim() === "terminal") {
      return [
        { key: "terminal_approve_once", label: "批准一次" },
        { key: "terminal_approve_session", label: "本会话批准" },
        { key: "terminal_cancel", label: "取消", type: "danger" },
      ];
    }
    if (String(meta.approval_id || "").trim()) {
      return [
        { key: "approval_approve", label: "批准" },
        { key: "approval_reject", label: "拒绝", type: "danger" },
      ];
    }
    if (String(meta.review_id || "").trim()) {
      return [
        { key: "review_approve", label: "允许保留" },
        { key: "review_reject", label: "拒绝变更", type: "danger" },
      ];
    }
  }
  return [];
}

async function handleOperationAction(operation, actionKey) {
  const normalizedActionKey = String(actionKey || "").trim();
  if (!normalizedActionKey) return;
  const actionType = normalizeOperationActionType(operation?.actionType);
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  if (normalizedActionKey === "open_url" && actionType === "open_url") {
    const url = extractOperationUrl(operation);
    if (!url) return;
    let opened = false;
    try {
      opened = await openExternalUrlViaSystem(url);
    } catch (_error) {
      opened = false;
    }
    if (!opened) {
      try {
        opened = Boolean(window.open(url, "_blank", "noopener,noreferrer"));
      } catch (_error) {
        opened = false;
      }
    }
    if (!opened) {
      ElMessage.warning("自动打开失败，请手动复制链接继续");
    }
    return;
  }
  if (
    [
      "agent_runtime_allow_once",
      "agent_runtime_allow_session",
      "agent_runtime_allow_always",
      "agent_runtime_deny",
    ].includes(normalizedActionKey)
  ) {
    await submitAgentRuntimePermissionAction(operation, normalizedActionKey);
    return;
  }
  if (
    normalizedActionKey === "approval_approve" ||
    normalizedActionKey === "approval_reject"
  ) {
    const requestId = String(meta.request_id || "").trim();
    const approvalId = String(meta.approval_id || "").trim();
    if (!requestId || !approvalId) {
      ElMessage.warning("缺少审批上下文，无法继续");
      return;
    }
    await sendApprovalDecision(
      requestId,
      approvalId,
      normalizedActionKey === "approval_approve",
    );
    return;
  }
  if (
    normalizedActionKey === "review_approve" ||
    normalizedActionKey === "review_reject"
  ) {
    const requestId = String(meta.request_id || "").trim();
    const reviewId = String(meta.review_id || "").trim();
    if (!requestId || !reviewId) {
      ElMessage.warning("缺少审查上下文，无法继续");
      return;
    }
    await sendFileReviewDecision(
      requestId,
      reviewId,
      normalizedActionKey === "review_approve",
    );
    return;
  }
  if (
    [
      "terminal_arrow_up",
      "terminal_arrow_down",
      "terminal_space",
      "terminal_enter",
      "terminal_ctrl_c",
    ].includes(normalizedActionKey)
  ) {
    const controlMap = {
      terminal_arrow_up: { content: "\u001b[A", label: "↑" },
      terminal_arrow_down: { content: "\u001b[B", label: "↓" },
      terminal_space: { content: " ", label: "空格" },
      terminal_enter: { content: "\r", label: "回车" },
      terminal_ctrl_c: { content: "\u0003", label: "Ctrl+C" },
    };
    const control = controlMap[normalizedActionKey];
    if (!control) return;
    await sendTerminalMirrorContent(control.content, {
      appendNewline: false,
      allowBlank: true,
      echoLabel: control.label,
    });
    return;
  }
  if (
    [
      "terminal_approve_once",
      "terminal_approve_session",
      "terminal_cancel",
    ].includes(normalizedActionKey)
  ) {
    const choiceMap = {
      terminal_approve_once: "1",
      terminal_approve_session: "2",
      terminal_cancel: "3",
    };
    await sendTerminalApprovalChoice(choiceMap[normalizedActionKey]);
  }
}

function agentRuntimePermissionActionValue(actionKey) {
  const mapping = {
    agent_runtime_allow_once: "allow_once",
    agent_runtime_allow_session: "allow_session",
    agent_runtime_allow_always: "allow_always",
    agent_runtime_deny: "deny",
  };
  return mapping[String(actionKey || "").trim()] || "";
}

function markAgentRuntimePermissionActionPending(operation, action) {
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  const row =
    findMessageRowByAgentRuntimePermission(
      meta.run_id,
      meta.call_id,
      meta.command_signature,
    ) || findMessageRowByOperationId(operation?.id);
  if (!row) return null;
  const nextSummary =
    action === "deny"
      ? "正在拒绝本次工具调用"
      : "已提交授权，运行时正在继续执行";
  updateAgentRuntimePermissionOperations(row, meta.run_id, meta.call_id, {
    phase: "running",
    summary: nextSummary,
    detail: String(operation?.detail || "").trim(),
    actionType: "none",
    meta,
  });
  return upsertMessageOperation(row, {
    ...operation,
    phase: "running",
    summary: nextSummary,
    detail: String(operation?.detail || "").trim(),
    actionType: "none",
  });
}

function restoreAgentRuntimePermissionAction(operation) {
  const meta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  const row =
    findMessageRowByAgentRuntimePermission(
      meta.run_id,
      meta.call_id,
      meta.command_signature,
    ) || findMessageRowByOperationId(operation?.id);
  if (!row) return;
  updateAgentRuntimePermissionOperations(row, meta.run_id, meta.call_id, {
    phase: "waiting_user",
    summary:
      String(operation?.summary || "").trim() ||
      "等待你选择本次工具调用的授权范围",
    actionType: "approve",
    meta,
  });
  upsertMessageOperation(row, {
    ...operation,
    phase: "waiting_user",
    summary:
      String(operation?.summary || "").trim() ||
      "等待你选择本次工具调用的授权范围",
    actionType: "approve",
  });
}

async function submitAgentRuntimePermissionAction(operation, actionKey) {
  const action = agentRuntimePermissionActionValue(actionKey);
  const projectId = String(selectedProjectId.value || "").trim();
  const currentOperation = latestAgentRuntimePermissionOperation(operation);
  const meta =
    currentOperation?.meta && typeof currentOperation.meta === "object"
      ? currentOperation.meta
      : {};
  const decision =
    meta.permission_decision && typeof meta.permission_decision === "object"
      ? meta.permission_decision
      : {};
  const runId = String(meta.run_id || decision.run_id || "").trim();
  const callId = String(meta.call_id || decision.call_id || "").trim();
  const toolName = String(meta.tool_name || decision.tool_name || "").trim();
  if (!projectId || !action || !runId || !callId || !toolName) {
    ElMessage.warning("缺少权限上下文，无法继续");
    return;
  }
  const originalOperation = { ...currentOperation };
  const row =
    findMessageRowByAgentRuntimePermission(
      runId,
      callId,
      meta.command_signature,
    ) || findMessageRowByOperationId(currentOperation.id);
  markAgentRuntimePermissionActionPending(currentOperation, action);
  try {
    const response = await submitAgentRuntimePermissionActionRequest(projectId, {
      action,
      run_id: runId,
      call_id: callId,
      tool_name: toolName,
      args:
        meta.tool_args && typeof meta.tool_args === "object"
          ? meta.tool_args
          : {},
      chat_session_id: String(
        meta.chat_session_id || currentChatSessionId.value || "",
      ).trim(),
      assistant_message_id: String(meta.assistant_message_id || row?.id || "").trim(),
    });
    const resume =
      response?.resume && typeof response.resume === "object"
        ? response.resume
        : null;
    const resumed = Boolean(resume?.resumed);
    const observations = Array.isArray(resume?.observations)
      ? resume.observations
      : [];
    const observationSummary = observations
      .map((item) => String(item?.summary || item?.status || "").trim())
      .filter(Boolean)
      .join("\n");
    const continuationContent = agentRuntimeResumeFinalContent(resume);
    const continuation = continuationContent ? resume?.continuation : null;
    const missingFinalAnswer = agentRuntimeResumeMissingFinalAnswer(resume);
    const resumeDetail =
      continuationContent ||
      (missingFinalAnswer
        ? agentRuntimeMissingFinalAnswerMessage()
        : observationSummary);
    const currentRow =
      findMessageRowByAgentRuntimePermission(
        runId,
        callId,
        meta.command_signature,
      ) ||
      findMessageRowByOperationId(currentOperation.id) ||
      row;
    upsertMessageOperation(currentRow, {
      ...currentOperation,
      phase: action === "deny" ? "blocked" : "completed",
      summary:
        action === "deny"
          ? "已拒绝，本次工具调用不会执行"
          : resumed
            ? continuation
              ? "已保存授权并继续运行"
              : missingFinalAnswer
                ? "工具已执行，但模型未返回最终回答"
                : "已保存授权并恢复执行"
            : "已保存授权，等待运行时继续执行",
      detail: resumeDetail,
      actionType: "none",
    });
    const assistantMessage =
      response?.assistant_message &&
      typeof response.assistant_message === "object"
        ? response.assistant_message
        : null;
    if (assistantMessage) {
      applyRealtimeChatMessagePayload({
        chat_session_id: String(
          meta.chat_session_id || currentChatSessionId.value || "",
        ).trim(),
        message: assistantMessage,
      });
    }
    applyAgentRuntimeResumeToAssistantMessage(currentRow, resume, { runId });
    ElMessage.success(
      action === "deny"
        ? "已拒绝"
        : resumed
          ? continuation
            ? "已继续运行"
            : missingFinalAnswer
              ? "工具已执行，但模型未返回最终回答"
              : "已恢复执行"
          : "已保存授权",
    );
  } catch (err) {
    restoreAgentRuntimePermissionAction(originalOperation);
    ElMessage.error(err?.detail || err?.message || "保存授权失败");
  }
}

function applyAgentRuntimePermissionActionResult(eventData = {}) {
  const runId = String(eventData?.run_id || "").trim();
  const callId = String(eventData?.call_id || "").trim();
  if (!runId || !callId) return false;
  const operationId = `agent-runtime-permission:${runId}:${callId}`;
  const commandSignature = String(eventData?.command_signature || "").trim();
  const row =
    findMessageRowByAgentRuntimePermission(runId, callId, commandSignature) ||
    findMessageRowByOperationId(operationId);
  if (!row) return false;
  const resume =
    eventData?.resume && typeof eventData.resume === "object"
      ? eventData.resume
      : null;
  const resumed = Boolean(resume?.resumed);
  const observations = Array.isArray(resume?.observations)
    ? resume.observations
    : [];
  const observationSummary = observations
    .map((item) => String(item?.summary || item?.status || "").trim())
    .filter(Boolean)
    .join("\n");
  const continuationContent = agentRuntimeResumeFinalContent(resume);
  const continuation = continuationContent ? resume?.continuation : null;
  const missingFinalAnswer = agentRuntimeResumeMissingFinalAnswer(resume);
  const action = String(eventData?.action || "")
    .trim()
    .toLowerCase();
  const nextPermissionState = {
    title: action === "deny" ? "工具调用已拒绝" : "工具调用授权",
    summary:
      action === "deny"
        ? "已拒绝，本次工具调用不会执行"
        : resumed
          ? continuation
            ? "已保存授权并继续运行"
            : missingFinalAnswer
              ? "工具已执行，但模型未返回最终回答"
              : "已保存授权并恢复执行"
          : "已保存授权，运行时正在继续执行",
    detail:
      continuationContent ||
      (missingFinalAnswer
        ? agentRuntimeMissingFinalAnswerMessage()
        : observationSummary),
    phase:
      action === "deny" || missingFinalAnswer
        ? "blocked"
        : resumed
          ? "completed"
          : "running",
    actionType: "none",
    meta: {
      command_signature: commandSignature,
    },
  };
  updateAgentRuntimePermissionOperations(
    row,
    runId,
    callId,
    nextPermissionState,
  );
  upsertMessageOperation(row, {
    operationId: agentRuntimePermissionOperationId(
      runId,
      callId,
      commandSignature,
    ),
    kind: "approval",
    ...nextPermissionState,
    meta: {
      agent_runtime_permission: "true",
      run_id: runId,
      call_id: callId,
      tool_name: String(eventData?.tool_name || "").trim(),
      chat_session_id: String(eventData?.chat_session_id || "").trim(),
      command_signature: commandSignature,
      resume,
    },
  });
  const assistantMessage =
    eventData?.assistant_message &&
    typeof eventData.assistant_message === "object"
      ? eventData.assistant_message
      : null;
  if (assistantMessage) {
    applyRealtimeChatMessagePayload({
      ...eventData,
      message: assistantMessage,
    });
  }
  if (!applyAgentRuntimeResumeToAssistantMessage(row, resume, { runId })) {
    row.processExpanded = true;
  }
  return true;
}

function applyAgentRuntimeOperationResumeResult(eventData = {}) {
  const runId = String(eventData?.run_id || "").trim();
  const taskId = String(eventData?.task_id || "").trim();
  const resume =
    eventData?.resume && typeof eventData.resume === "object"
      ? eventData.resume
      : null;
  if (!runId || !taskId || !resume) return false;
  const operationId = `workflow:auth_login:${taskId}`;
  const row = findMessageRowByOperationId(operationId);
  if (!row) return false;
  const resumed = Boolean(resume?.resumed);
  const observations = Array.isArray(resume?.observations)
    ? resume.observations
    : [];
  const observationSummary = observations
    .map((item) => String(item?.summary || item?.status || "").trim())
    .filter(Boolean)
    .join("\n");
  const continuation =
    resume?.continuation && typeof resume.continuation === "object"
      ? resume.continuation
      : null;
  const continuationContent = agentRuntimeResumeFinalContent(resume);
  const missingFinalAnswer = agentRuntimeResumeMissingFinalAnswer(resume);
  upsertMessageOperation(row, {
    operationId,
    kind: "auth",
    title: "操作恢复",
    summary: resumed
      ? continuation
        ? "操作完成，已继续运行"
        : missingFinalAnswer
          ? "操作完成，但模型未返回最终回答"
          : "操作完成，已恢复执行"
      : "操作完成，等待运行时继续执行",
    detail:
      continuationContent ||
      (missingFinalAnswer
        ? agentRuntimeMissingFinalAnswerMessage()
        : observationSummary) ||
      String(resume?.reason || "").trim(),
    phase: missingFinalAnswer ? "blocked" : resumed ? "completed" : "running",
    actionType: "none",
    meta: {
      agent_runtime_operation_resume: "true",
      run_id: runId,
      task_id: taskId,
      chat_session_id: String(eventData?.chat_session_id || "").trim(),
      resume,
    },
  });
  row.processExpanded = true;
  return true;
}

async function trustAgentRuntimeWorkspace() {
  const projectId = String(selectedProjectId.value || "").trim();
  const workspacePath = String(
    agentRuntimeWorkspaceTrustPath.value || "",
  ).trim();
  if (!projectId || !workspacePath) {
    ElMessage.warning("缺少工作区路径");
    return;
  }
  workspaceTrustSaving.value = true;
  try {
    await trustAgentRuntimeWorkspaceRequest(projectId, {
      workspace_path: workspacePath,
      trusted: true,
      metadata: {
        chat_session_id: String(currentChatSessionId.value || "").trim(),
        source: "project-chat",
      },
    });
    ElMessage.success("已信任当前工作区");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "信任工作区失败");
  } finally {
    workspaceTrustSaving.value = false;
  }
}

function appendTerminalLog(row, text, options = {}) {
  if (!row || row.displayMode !== "terminal") return;
  const linesToAppend = sanitizeTerminalOutputLines(text);
  if (!linesToAppend.length) return;
  const logs = Array.isArray(row.terminalLog) ? row.terminalLog.slice() : [];
  linesToAppend.forEach((line) => {
    if (!line || (logs.length && logs[logs.length - 1] === line)) return;
    logs.push(line);
  });
  if (logs.length > 160) {
    logs.splice(0, logs.length - 160);
  }
  row.terminalLog = logs;
  if (options?.mirrorToPanel !== false) {
    appendTerminalPanelLine(linesToAppend.join("\n"));
  }
}

function ensureProcessLogVisible(row) {
  if (!row) return;
  if (row.displayMode !== "terminal") {
    row.displayMode = "terminal";
  }
  if (row.processExpanded !== true) {
    row.processExpanded = false;
  }
}

function toolProgressLabel(eventData, toolName) {
  const index = Number(eventData?.tool_index || 0);
  const total = Number(eventData?.tool_count || 0);
  if (index > 0 && total > 0) {
    return `${toolName} (${index}/${total})`;
  }
  return toolName;
}

function formatToolArgumentsPreview(eventData) {
  const preview = String(eventData?.arguments_preview || "").trim();
  if (!preview) return "";
  return preview.replace(/\s+/g, " ").trim();
}

function eventArgumentsObject(eventData) {
  const direct = eventData?.arguments;
  if (direct && typeof direct === "object" && !Array.isArray(direct)) {
    return direct;
  }
  const raw = String(direct || eventData?.args || "").trim();
  if (!raw || raw[0] !== "{") return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed
      : {};
  } catch {
    return {};
  }
}

function eventCommand(eventData) {
  const direct = String(eventData?.command || "").trim();
  if (direct) return direct;
  const args = eventArgumentsObject(eventData);
  return String(args.command || "").trim();
}

function appendToolStartLogs(row, eventData) {
  if (!row) return;
  const toolName = String(eventData?.tool_name || "工具").trim() || "工具";
  const label = toolProgressLabel(eventData, toolName);
  const argumentsPreview = formatToolArgumentsPreview(eventData);
  const command = eventCommand(eventData);
  const cwd = String(eventData?.cwd || eventData?.workspace_path || "").trim();
  const planId = String(eventData?.plan_id || "").trim();
  const stepId = String(eventData?.step_id || "").trim();
  if (planId && stepId) {
    updatePlanOperationStep(row, planId, stepId, {
      status: "running",
      summary: command
        ? `正在执行命令：${command}`
        : `正在调用工具：${toolName}`,
    });
  }
  const operationId = projectChatActionOperationId(eventData);
  appendMessageProcessLog(row, {
    level: "info",
    text: argumentsPreview
      ? `调用 ${label}：${argumentsPreview}`
      : `调用 ${label}`,
  });
  upsertMessageOperation(row, {
    operationId,
    kind: "tool",
    title: label,
    summary: command ? "正在执行命令" : "正在调用工具",
    detail: command ? "" : argumentsPreview,
    phase: "running",
    meta: {
      tool_name: toolName,
      command,
      cwd,
      arguments_preview: argumentsPreview,
      plan_id: planId,
      step_id: stepId,
      tool_index: Number(eventData?.tool_index || 0) || 0,
      tool_count: Number(eventData?.tool_count || 0) || 0,
    },
  });
}

function appendToolResultLogs(row, eventData) {
  if (!row) return;
  const toolName = String(eventData?.tool_name || "工具").trim() || "工具";
  const label = toolProgressLabel(eventData, toolName);
  const statusText =
    String(eventData?.status || "completed").trim() || "completed";
  const normalizedStatus = statusText.toLowerCase();
  const outputPreview = clipText(buildProjectHostCommandOutput(eventData), 240);
  const command = eventCommand(eventData);
  const cwd = String(eventData?.cwd || eventData?.workspace_path || "").trim();
  const exitCode =
    eventData?.exit_code === null || eventData?.exit_code === undefined
      ? ""
      : String(eventData.exit_code).trim();
  const planId = String(eventData?.plan_id || "").trim();
  const stepId = String(eventData?.step_id || "").trim();
  if (planId && stepId) {
    updatePlanOperationStep(row, planId, stepId, {
      status: normalizedStatus === "error" ? "failed" : "completed",
      summary:
        normalizedStatus === "error"
          ? "工具或命令执行未完成"
          : "工具或命令执行完成",
    });
  }
  const operationId = projectChatActionOperationId(eventData);
  appendMessageProcessLog(row, {
    level: normalizedStatus === "error" ? "error" : "success",
    text: outputPreview
      ? `${label} ${
          normalizedStatus === "error" ? "执行未完成" : "已完成"
        }：${outputPreview}`
      : `${label} ${normalizedStatus === "error" ? "执行未完成" : "已完成"}`,
  });
  upsertMessageOperation(row, {
    operationId,
    kind: "tool",
    title: label,
    summary: normalizedStatus === "error" ? "执行未完成" : "已完成",
    detail: command ? "" : outputPreview,
    phase: normalizedStatus === "error" ? "failed" : "completed",
    meta: {
      tool_name: toolName,
      command,
      cwd,
      exit_code: exitCode,
      output_preview: outputPreview,
      stdout_preview: String(eventData?.stdout_preview || "").trim(),
      stderr_preview: String(eventData?.stderr_preview || "").trim(),
      error: String(eventData?.error || "").trim(),
      duration_ms:
        eventData?.duration_ms === null || eventData?.duration_ms === undefined
          ? ""
          : String(eventData.duration_ms).trim(),
      plan_id: planId,
      step_id: stepId,
      tool_index: Number(eventData?.tool_index || 0) || 0,
      tool_count: Number(eventData?.tool_count || 0) || 0,
    },
  });
}

function operationMeta(operation) {
  return operation?.meta && typeof operation.meta === "object"
    ? operation.meta
    : {};
}

function operationCommand(operation) {
  return String(operationMeta(operation).command || "").trim();
}

function operationCwd(operation) {
  return String(operationMeta(operation).cwd || "").trim();
}

function operationExitCode(operation) {
  return String(operationMeta(operation).exit_code || "").trim();
}

function operationOutput(operation) {
  const meta = operationMeta(operation);
  return clipText(
    [meta.stdout_preview, meta.stderr_preview, meta.output_preview, meta.error]
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .join("\n"),
    900,
  );
}

function buildProjectHostCommandOutput(eventData) {
  return [
    eventData?.stdout_preview,
    eventData?.stderr_preview,
    eventData?.output_preview,
    eventData?.error,
  ]
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .join("\n");
}

function shouldAutoHandoffProjectHostCommand() {
  return false;
}

async function handoffProjectHostCommandToTerminal(row, pending, eventData) {
  if (!row || !pending || pending.projectHostTerminalHandoffTriggered) {
    return false;
  }
  const command = eventCommand(eventData);
  if (!command) return false;
  pending.projectHostTerminalHandoffTriggered = true;
  terminalActiveCommand.value = command;
  row.displayMode = "terminal";
  ensureProcessLogVisible(row);
  activeTerminalMirrorAssistantIndex.value = Number(
    pending.assistantIndex ?? -1,
  );
  row.terminalLog = [];
  row.processExpanded = true;
  appendTerminalLog(row, `# 正在连接项目终端并接管交互\n$ ${command}`, {
    mirrorToPanel: false,
  });
  upsertMessageOperation(row, {
    operationId: `terminal:handoff:${Number(pending.assistantIndex ?? -1)}`,
    kind: "terminal",
    title: "正在连接项目终端",
    summary: "命令需要交互，正在切换到项目终端",
    detail: command,
    phase: "running",
    actionType: "enter_text",
  });
  try {
    await startTerminalMirror({
      assistantIndex: pending.assistantIndex,
      initialCommand: command,
    });
    return true;
  } catch (err) {
    appendTerminalLog(
      row,
      `! 自动切换项目终端失败：${String(err?.message || err || "未知错误").trim()}`,
    );
    return false;
  }
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
    const sent = await sendTerminalMirrorContent(userPrompt);
    if (!sent) {
      requestMeta.handoffTriggered = false;
      return false;
    }
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

function isExternalAgentWaitingMessage(item) {
  return (
    String(item?.displayMode || "").trim() === "external-agent-waiting" &&
    !String(item?.content || "").trim()
  );
}

function isBackgroundedNativeExternalAgentMessage(item) {
  const runnerSessionId = resolveNativeExternalAgentSessionIdFromMessage(item);
  if (!runnerSessionId) return false;
  const chatSessionId =
    getNativeExternalAgentChatSessionIdForRunnerSession(runnerSessionId);
  return (
    Boolean(chatSessionId) &&
    nativeExternalAgentBackgroundedChatSessionIds.value.has(chatSessionId)
  );
}

function externalAgentWaitingMessageTitle(item) {
  return isBackgroundedNativeExternalAgentMessage(item)
    ? "外部任务已转入后台"
    : "外部模型正在生成回复";
}

function externalAgentWaitingMessageDescription(item) {
  return isBackgroundedNativeExternalAgentMessage(item)
    ? "后台继续执行，完成后会自动写回这条消息"
    : "已连接执行器，正在等待模型返回结果";
}

function messageRoleName(item) {
  if (String(item?.role || "").trim() === "user") return "登录用户";
  if (String(item?.displayMode || "").trim() === "terminal") {
    return `机器人 · ${externalAgentDisplayLabel.value}`;
  }
  return "机器人";
}

function avatarLabel(item) {
  if (String(item?.role || "").trim() === "user") return "登";
  const source = String(
    String(item?.displayMode || "").trim() === "terminal" ? "机器人" : "机器人",
  ).trim();
  return source.slice(0, 1).toUpperCase() || "机";
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

async function copyNativeExternalAgentFinalAnswer() {
  try {
    await writeClipboardText(nativeExternalAgentFinalAnswerText.value);
    ElMessage.success("已复制最终回答");
  } catch {
    ElMessage.warning("当前没有可复制的最终回答");
  }
}

async function copyNativeExternalAgentFullLog() {
  try {
    await writeClipboardText(nativeExternalAgentFullLogText.value);
    ElMessage.success("已复制完整日志");
  } catch {
    ElMessage.warning("当前没有可复制的 Runner 日志");
  }
}

async function sendNativeExternalAgentStdin() {
  await sendNativeExternalAgentInputContent(
    nativeExternalAgentStdinDraft.value,
    {
      appendNewline: true,
      clearDraft: true,
    },
  );
}

async function sendNativeExternalAgentControl(content) {
  await sendNativeExternalAgentInputContent(content, {
    appendNewline: false,
    allowBlank: true,
    clearDraft: false,
    silent: true,
  });
}

async function sendNativeExternalAgentInputContent(content, options = {}) {
  const sessionId = String(
    nativeExternalAgentSession.value?.sessionId || "",
  ).trim();
  const input = String(content || "");
  if (!sessionId) {
    ElMessage.warning("当前没有 Runner 会话");
    return;
  }
  if (!canWriteNativeExternalAgentStdin.value) {
    ElMessage.warning("当前 Runner 会话不支持继续输入");
    return;
  }
  if (!input.trim() && !options.allowBlank) {
    ElMessage.warning("请输入要发送给 Runner 的内容");
    return false;
  }
  nativeExternalAgentStdinSending.value = true;
  try {
    const snapshot = await writeNativeExternalAgentSessionInput({
      sessionId,
      input,
      appendNewline: options.appendNewline ?? true,
    });
    if (options.clearDraft !== false) {
      nativeExternalAgentStdinDraft.value = "";
    }
    applyNativeExternalAgentSessionSnapshot(snapshot);
    upsertNativeExternalAgentMessageOperation(snapshot);
    persistNativeExternalAgentRowsForSession(
      getNativeExternalAgentChatSessionIdForRunnerSession(sessionId),
    );
    if (!options.silent) {
      ElMessage.success("已发送到 Runner");
    }
    if (String(snapshot.status || "").trim() === "running") {
      stopNativeExternalAgentSessionPolling(sessionId);
      void pollNativeExternalAgentSession(sessionId);
    }
    return true;
  } catch (err) {
    ElMessage.error(err?.message || "发送 Runner 输入失败");
    return false;
  } finally {
    nativeExternalAgentStdinSending.value = false;
  }
}

async function submitNativeExternalAgentInteraction() {
  const interaction = nativeExternalAgentInteractionPrompt.value;
  if (!interaction) return;
  const kind = String(interaction.kind || "confirm");
  let content = "";
  let appendNewline = true;
  if (kind === "choice") {
    appendNewline = false;
    const isMulti = interaction.type === "checkbox";
    const upCount = Math.max(0, Number(interaction.highlightedIndex || 0));
    content += "\u001b[A".repeat(upCount);
    if (isMulti) {
      const choices = Array.isArray(
        nativeExternalAgentInteractionModel.value?.choices,
      )
        ? nativeExternalAgentInteractionModel.value.choices
        : [];
      const selectedSet = new Set(
        choices.map((item) => String(item || "").trim()),
      );
      interaction.options.forEach((option, index) => {
        const shouldSelect = selectedSet.has(option.value);
        if (Boolean(option.selected) !== shouldSelect) {
          content += " ";
        }
        if (index < interaction.options.length - 1) {
          content += "\u001b[B";
        }
      });
    } else {
      const choice = String(
        nativeExternalAgentInteractionModel.value?.choice ||
          interaction.selectedValue ||
          "",
      ).trim();
      if (!choice) {
        ElMessage.warning("请选择一项");
        return;
      }
      const targetIndex = Math.max(
        0,
        interaction.options.findIndex((option) => option.value === choice),
      );
      content += "\u001b[B".repeat(targetIndex);
    }
    content += "\r";
  } else if (kind === "text") {
    content = String(
      nativeExternalAgentInteractionModel.value?.text || "",
    ).trim();
    if (!content) {
      ElMessage.warning("请输入内容");
      return;
    }
  } else {
    const decision = String(
      nativeExternalAgentInteractionModel.value?.decision || "yes",
    ).trim();
    content = decision === "no" ? "n" : "y";
  }
  nativeExternalAgentInteractionSubmittedKey.value = interaction.key;
  await sendNativeExternalAgentInputContent(content, {
    appendNewline,
    allowBlank: kind === "choice",
    clearDraft: false,
  });
}

function dismissNativeExternalAgentInteraction() {
  const interaction = nativeExternalAgentInteractionPrompt.value;
  if (!interaction) return;
  nativeExternalAgentInteractionDismissedKey.value = interaction.key;
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

function countUserMessagesBefore(messageIndex) {
  const normalizedIndex = Number(messageIndex);
  if (!Number.isInteger(normalizedIndex) || normalizedIndex < 0) return -1;
  let count = 0;
  for (let index = 0; index < normalizedIndex; index += 1) {
    if (String(messages.value[index]?.role || "").trim() === "user") {
      count += 1;
    }
  }
  return count;
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
      fallbackUserContent: String(item?.content || "").trim(),
      fallbackUserTurnIndex: countUserMessagesBefore(normalizedIndex),
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
    fallbackUserContent: String(source?.item?.content || "").trim(),
    fallbackUserTurnIndex: countUserMessagesBefore(source.index),
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

function isChatHistoryTruncateNotFound(err) {
  if (Number(err?.status || 0) !== 404) return false;
  const detail = String(err?.detail || err?.message || "")
    .trim()
    .toLowerCase();
  return (
    !detail ||
    detail.includes("not found") ||
    detail.includes("message not found")
  );
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
        fallback_user_content: String(source.item?.content || "").trim(),
        fallback_user_turn_index: countUserMessagesBefore(source.index),
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
        fallback_user_content: String(target?.fallbackUserContent || "").trim(),
        fallback_user_turn_index: Number.isInteger(
          Number(target?.fallbackUserTurnIndex),
        )
          ? Number(target.fallbackUserTurnIndex)
          : undefined,
      },
    );
    applyDeleteTargetLocally(target);
    ElMessage.success(buildDeleteSuccessText(item));
  } catch (err) {
    if (isChatHistoryTruncateNotFound(err)) {
      applyDeleteTargetLocally(target);
      clearPersistedChatRuntime(projectId, chatSessionId);
      rememberCurrentChatSessionMessages();
      ElMessage.success(buildDeleteSuccessText(item));
      return;
    }
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
  if (resolveNativeExternalAgentSessionIdFromMessage(item)) {
    actions.push({
      key: "runner_detail",
      tooltip: "查看运行详情",
      icon: List,
    });
  }
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
    case "runner_detail":
      void openNativeExternalAgentSessionDetailFromMessage(item);
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

function isMessagesViewportNearBottom(container = messagesContainer.value) {
  if (!container) return true;
  const scrollHeight = Number(container.scrollHeight || 0);
  const clientHeight = Number(container.clientHeight || 0);
  const scrollTop = Number(container.scrollTop || 0);
  return (
    scrollHeight - clientHeight - scrollTop <= CHAT_BOTTOM_STICKY_THRESHOLD
  );
}

function updateMessagesBottomStickiness(container = messagesContainer.value) {
  shouldStickMessagesToBottom.value = isMessagesViewportNearBottom(container);
}

function cancelScheduledScrollToBottom() {
  if (pendingScrollToBottomFrame !== null) {
    window.cancelAnimationFrame(pendingScrollToBottomFrame);
    pendingScrollToBottomFrame = null;
  }
}

function scrollToBottom(options = {}) {
  const force = options.force !== false;
  nextTick(() => {
    const container = messagesContainer.value;
    if (!container) return;
    if (!force && !shouldStickMessagesToBottom.value) return;
    cancelScheduledScrollToBottom();
    pendingScrollToBottomFrame = window.requestAnimationFrame(() => {
      pendingScrollToBottomFrame = null;
      const activeContainer = messagesContainer.value;
      if (!activeContainer) return;
      if (
        !force &&
        !shouldStickMessagesToBottom.value &&
        !isMessagesViewportNearBottom(activeContainer)
      ) {
        return;
      }
      activeContainer.scrollTop = activeContainer.scrollHeight;
      updateMessagesBottomStickiness(activeContainer);
    });
  });
}

function handleMessagesScroll() {
  updateMessagesBottomStickiness();
}

function disconnectMessageListResizeObserver() {
  if (messageListResizeObserver) {
    messageListResizeObserver.disconnect();
    messageListResizeObserver = null;
  }
}

function bindMessageListResizeObserver() {
  disconnectMessageListResizeObserver();
  const container = messagesContainer.value;
  if (!container || typeof ResizeObserver === "undefined") return;
  const target = container.querySelector?.(".message-list-inner") || container;
  updateMessagesBottomStickiness(container);
  messageListResizeObserver = new ResizeObserver(() => {
    if (!shouldStickMessagesToBottom.value) return;
    scrollToBottom({ force: false });
  });
  messageListResizeObserver.observe(target);
}

function clearHighlightedMessage() {
  if (highlightedMessageTimer !== null) {
    window.clearTimeout(highlightedMessageTimer);
    highlightedMessageTimer = null;
  }
  highlightedMessageId.value = "";
}

function resolveSettingsRouteProjectId() {
  if (!isChatSettingsRoutePath(route.path)) {
    return "";
  }
  const routeParamProjectId = String(route.params.id || "").trim();
  if (!routeParamProjectId) {
    return "";
  }
  const scopedPath = stripChatSettingsPrefix(route.path);
  if (
    scopedPath === `/projects/${routeParamProjectId}` ||
    scopedPath.startsWith(`/projects/${routeParamProjectId}/`)
  ) {
    return routeParamProjectId;
  }
  return "";
}

function routeChatTarget() {
  const routeProjectId = String(route.query.project_id || "").trim();
  const createNewSession =
    String(route.query[CREATE_CHAT_SESSION_QUERY_KEY] || "").trim() === "1";
  return {
    projectId: routeProjectId || resolveSettingsRouteProjectId(),
    chatSessionId: String(route.query.chat_session_id || "").trim(),
    createNewSession,
    messageId: String(route.query.message_id || "").trim(),
  };
}

function replaceRouteWithChatSession(chatSessionId) {
  const normalizedSessionId = String(chatSessionId || "").trim();
  if (!normalizedSessionId) return;
  const nextQuery = {
    ...route.query,
    chat_session_id: normalizedSessionId,
  };
  delete nextQuery[CREATE_CHAT_SESSION_QUERY_KEY];
  delete nextQuery.message_id;
  void router.replace({ query: nextQuery }).catch(() => {});
}

async function focusChatComposerTextarea() {
  await nextTick();
  const textarea = chatComposerRef.value?.querySelector?.("textarea");
  if (!textarea) return;
  textarea.focus();
  inputFocused.value = true;
  const textLength = String(textarea.value || "").length;
  if (typeof textarea.setSelectionRange === "function") {
    textarea.setSelectionRange(textLength, textLength);
  }
}

async function applyStatisticsAnalysisDraftFromRoute() {
  const draftKey = String(
    route.query[STATISTICS_ANALYSIS_DRAFT_QUERY_KEY] || "",
  ).trim();
  if (!draftKey) return;
  const payload = consumeStatisticsAnalysisDraft(draftKey);
  const prompt = String(payload?.prompt || "").trim();
  if (prompt) {
    draftText.value = String(draftText.value || "").trim()
      ? `${String(draftText.value || "").trim()}\n\n${prompt}`
      : prompt;
    scrollToBottom();
    await focusChatComposerTextarea();
    ElMessage.success("统计分析请求已填入输入框");
  }
  const nextQuery = { ...route.query };
  delete nextQuery[STATISTICS_ANALYSIS_DRAFT_QUERY_KEY];
  await router.replace({ query: nextQuery });
}

async function applyPluginInstallDraftFromRoute() {
  const draftKey = String(
    route.query[PLUGIN_INSTALL_DRAFT_QUERY_KEY] || "",
  ).trim();
  if (!draftKey) return;
  const payload = consumePluginInstallDraft(draftKey);
  const prompt = String(payload?.prompt || "").trim();
  if (prompt) {
    draftText.value = String(draftText.value || "").trim()
      ? `${String(draftText.value || "").trim()}\n\n${prompt}`
      : prompt;
    scrollToBottom();
    await focusChatComposerTextarea();
    ElMessage.success("插件安装请求已填入输入框");
  }
  const nextQuery = { ...route.query };
  delete nextQuery[PLUGIN_INSTALL_DRAFT_QUERY_KEY];
  await router.replace({ query: nextQuery });
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

watch(
  messagesContainer,
  () => {
    nextTick(() => {
      bindMessageListResizeObserver();
      updateMessagesBottomStickiness();
    });
  },
  { flush: "post" },
);

async function upsertProjectChatRequirementRecord({
  chatSessionId = "",
  ...payload
} = {}) {
  const projectId = String(selectedProjectId.value || "").trim();
  const activeChatSessionId = String(
    chatSessionId || currentChatSessionId.value || "",
  ).trim();
  try {
    return await upsertProjectChatRequirementRecordRequest(projectId, {
      ...payload,
      chatSessionId: activeChatSessionId,
    });
  } catch (err) {
    console.warn("upsert project chat requirement record failed", err);
    return null;
  }
}

function resolveSlashCommand(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed.startsWith("/")) {
    return null;
  }
  const match = trimmed.match(/^(\/[^\s]+)(?:\s+([\s\S]*))?$/);
  if (!match) {
    return null;
  }
  const token = normalizeSlashCommandToken(match[1]);
  const prompt = String(match[2] || "").trim();
  const entry =
    composerSlashCommands.value.find((item) => {
      const tokens = [
        item.command,
        ...(Array.isArray(item.aliases) ? item.aliases : []),
      ];
      return tokens.some(
        (candidate) => normalizeSlashCommandToken(candidate) === token,
      );
    }) || null;
  if (!entry) {
    return null;
  }
  return {
    entry,
    token,
    prompt,
  };
}

function isActionableOperationPrompt(text) {
  const normalized = String(text || "").trim();
  if (!normalized) return false;
  const explanationOnly =
    EXPLANATION_ONLY_OPERATION_RE.test(normalized) &&
    !IMPERATIVE_OPERATION_RE.test(normalized);
  if (explanationOnly) return false;
  return (
    ACTIONABLE_OPERATION_HINT_RE.test(normalized) &&
    ACTIONABLE_OPERATION_TARGET_RE.test(normalized)
  );
}

function isLarkOperationPrompt(text) {
  return LARK_OPERATION_RE.test(String(text || "").trim());
}

function buildAgenticOperationInstruction(sourcePrompt) {
  const original = String(sourcePrompt || "").trim();
  return [
    "本轮用户意图：代办执行请求。",
    "执行要求：",
    "- 你必须优先使用当前项目可用工具或项目终端完成操作，不要只给用户命令、步骤或教程。",
    "- 如果需要登录、授权或认证，先检查当前状态；未登录时直接发起登录/授权流程，并把授权链接或交互卡片返回给前端等待用户完成。",
    "- 授权完成后继续执行原始任务；不要要求用户重复输入同一条命令。",
    "- 只有在工具不可用、权限不足或缺少必要信息时，才说明阻塞原因和需要用户提供的具体信息。",
    "- 最终回复必须基于真实工具执行结果，说明已完成什么、还有什么未完成。",
    original ? `原始用户请求：${original}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function appendAgenticOperationInstruction(prompt, sourcePrompt) {
  return [
    String(prompt || "").trim(),
    "",
    buildAgenticOperationInstruction(sourcePrompt),
  ]
    .filter(Boolean)
    .join("\n");
}

function applySlashCommandSelection(item) {
  if (!item?.command) return;
  draftText.value = `${item.command} `;
  slashCommandHighlightIndex.value = 0;
}

async function fetchProjectStatsAiReport(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) {
    throw new Error("缺少项目 ID，无法加载统计 AI 报表");
  }
  const response = await api.get("/statistics/overview", {
    params: {
      days: PROJECT_STATS_REPORT_DAYS,
      project_id: normalizedProjectId,
    },
  });
  const report = response?.ai_report || null;
  const markdown = String(report?.markdown || "").trim();
  if (!markdown) {
    throw new Error("当前项目暂无可读取的统计 AI 报表");
  }
  return {
    days: Number(response?.days || PROJECT_STATS_REPORT_DAYS),
    summary: String(report?.summary || "").trim(),
    conclusion: String(report?.conclusion || "").trim(),
    markdown,
  };
}

function buildProjectStatsCommandPrompt({
  projectLabel,
  commandPrompt,
  reportDays,
  reportSummary,
  reportConclusion,
  reportMarkdown,
  docsText,
  attachmentNames,
}) {
  const analysisRequest =
    String(commandPrompt || "").trim() ||
    "请基于这份报表判断当前项目最值得优先优化的 3 个方向，给出优先级、原因、预期收益，以及下一步建议补齐的统计项。";
  const attachmentHint =
    Array.isArray(attachmentNames) && attachmentNames.length
      ? `补充附件：${attachmentNames.join("、")}。`
      : "";
  return [
    `你现在在分析项目「${String(projectLabel || "当前项目").trim() || "当前项目"}」的统计 AI 报表。`,
    `统计窗口：近 ${Number(reportDays || PROJECT_STATS_REPORT_DAYS)} 天。`,
    reportSummary ? `报表摘要：${reportSummary}` : "",
    reportConclusion ? `报表结论：${reportConclusion}` : "",
    "",
    "任务要求：",
    analysisRequest,
    attachmentHint,
    docsText ? `补充材料：\n${docsText}` : "",
    "",
    "以下是当前项目统计 AI 报表：",
    reportMarkdown,
  ]
    .filter(Boolean)
    .join("\n");
}

function resolveLarkCliSkillDirectory() {
  const stored = String(skillResourceDirectoryResolved.value || "").trim();
  if (stored) return stored;
  const workspaceRoot = String(
    projectWorkspaceDraftNormalized.value ||
      projectWorkspaceResolved.value ||
      "",
  ).trim();
  if (!workspaceRoot) return LARK_CLI_SKILL_ROOT_RELATIVE;
  return `${workspaceRoot.replace(/\/+$/g, "")}/${LARK_CLI_SKILL_ROOT_RELATIVE}`;
}

function buildFormJsonCommandPrompt(commandPrompt) {
  const normalizedPrompt = String(commandPrompt || "").trim();
  return [
    "请根据下面的字段或表单需求，生成 element-easy-form 的 ElementEasyForm 可直接渲染的 formJson。",
    "",
    "输出要求：",
    "- 必须输出一个严格 JSON 代码块，代码块语言标记必须是 form-json。",
    "- JSON 顶层必须包含 model、formAttrs、rowAttrs、schema。",
    "- schema[].componentName 只允许使用 ElInput、ElInputNumber、ElSelect、ElOption、ElDatePicker、ElSwitch、ElRadioGroup、ElRadioButton、ElCheckboxGroup、ElCheckbox。",
    "- 允许输出 element-easy-form/drag-form 支持的动态能力：hidden、rules、events；不要输出 render、renderLabel 或自定义组件。",
    '- 需要动态显示/隐藏时，必须给目标字段配置 schema[].hidden。优先使用 hidden.type="function" 和 hidden.dataJs，格式固定为：function hidden(config,data){ return <布尔表达式>; }，返回 true 表示隐藏，返回 false 表示显示。',
    "- hidden.dataJs 只能访问 config 和 data，不能访问 window、document、localStorage、fetch、XMLHttpRequest、eval、Function、import、globalThis、this、prototype、constructor，也不能写异步代码或副作用代码。",
    '- 简单条件也可以使用 hidden.type="select"，格式为 {"matchPattern":"&&","type":"select","dataSelect":[{"prop":"字段prop","type":"string","compare":"!=","value":""}],"value":false}；value=false 表示条件成立时显示、条件不成立时隐藏。',
    '- 需要联动、格式化或清空依赖字段时，可以输出 events 数组；事件函数必须是字符串形式的 Element Plus 事件处理函数，例如 {"prop":"change","defaultValue":"function event(config,data,val){ data.department = \'\'; }"}，同样不能访问浏览器全局对象或执行副作用。',
    "- 校验规则使用 Element Plus rules；必填字段必须输出 rules，非必填字段不要加 required。",
    "- model 必须包含每个 schema 字段的初始值。",
    "- schema[].prop 必须和 model 字段一一对应，字段名使用英文 snake_case。",
    "- 下拉、单选、多选必须提供 children，并给子组件 attrs.label 和 attrs.value。",
    "- ElInput 建议 attrs.clearable=true；ElSelect 建议 attrs.clearable=true、filterable=true；ElDatePicker 建议提供 type 和 value-format；ElSwitch 初始值必须是 boolean。",
    "- 表单属性建议使用 label-position、status-icon；布局建议 rowAttrs.gutter=16，字段 colAttrs 使用 xs/sm/span。",
    "- 除 JSON 代码块外，可以在前面用一句话说明生成结果，但不要把 JSON 拆成多个代码块。",
    "",
    "示例输出格式：",
    "```form-json",
    "{",
    '  "model": { "name": "" },',
    '  "formAttrs": { "label-position": "top", "status-icon": true },',
    '  "rowAttrs": { "gutter": 16 },',
    '  "schema": [',
    '    { "label": "姓名", "prop": "name", "componentName": "ElInput", "attrs": { "placeholder": "请输入姓名", "clearable": true }, "rules": [{ "required": true, "message": "请输入姓名", "trigger": "blur" }], "colAttrs": { "xs": 24, "sm": 12 } },',
    '    { "label": "部门", "prop": "department", "componentName": "ElSelect", "attrs": { "placeholder": "请选择部门", "clearable": true, "filterable": true }, "children": [{ "componentName": "ElOption", "attrs": { "label": "研发部", "value": "rd" } }], "hidden": { "matchPattern": "&&", "type": "function", "dataSelect": [], "value": false, "dataJs": "function hidden(config,data){ return !data.phone; }" }, "colAttrs": { "xs": 24, "sm": 12 } }',
    "  ]",
    "}",
    "```",
    "",
    "用户字段/需求：",
    normalizedPrompt || "请先根据常见业务表单生成一个包含 5 个字段的示例表单。",
  ].join("\n");
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
    await createProjectMaterial(projectId, {
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
  const { skills, rules } = await fetchEmployeeDraftCatalog();
  employeeDraftCatalog.value = {
    skills: (skills || [])
      .filter(isReusableEmployeeDraftSkill)
      .map((skill) => ({
        id: String(skill.id || "").trim(),
        name: String(skill.name || skill.id || "").trim(),
        description: String(skill.description || "").trim(),
        tags: Array.isArray(skill.tags) ? skill.tags : [],
      })),
    rules: (rules || []).map((rule) => ({
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
  void openRouteInDesktop(
    router,
    { path: "/materials", query: { project_id: projectId } },
    {
      mode: "new-window",
      appId: "materials",
      title: "素材库",
      eyebrow: "Asset Workspace",
      summary: "项目素材库作为桌面应用窗口打开，和 AI 对话并行处理素材。",
    },
  );
}

function openCurrentProjectDetail() {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    ElMessage.warning("请先选择项目");
    return;
  }
  void openRouteInDesktop(
    router,
    `/projects/${encodeURIComponent(projectId)}`,
    {
      mode: "new-window",
      appId: "projects",
      title: currentProjectLabel.value || "项目详情",
      eyebrow: "Project Workspace",
      summary: "项目详情作为独立桌面窗口打开，避免在 AI 对话窗口里吞掉上下文。",
    },
  );
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
  skillResourceSearchLoading.value = true;
  try {
    const { resolvedQueries, results } = await searchSkillResourceItems(query, {
      externalSkillSites: employeeDraftExternalSkillSites.value,
      preferredSites: skillResourceSites.value,
    });
    skillResourceSearchResolvedQueries.value = resolvedQueries;
    skillResourceSearchResults.value = results;
  } catch (err) {
    skillResourceSearchResults.value = [];
    skillResourceSearchResolvedQueries.value = [];
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
    const result = await installVettSkillResource(slug, {
      version,
      installDir,
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

function applyStarterPrompt(prompt) {
  draftText.value = String(prompt || "").trim();
  rememberCurrentChatSessionComposerState();
}

function handleFileChange(file) {
  const raw = file.raw;
  if (!raw) return;
  const isImage = isImageFile(raw);
  if (!isAllowedFileType(raw, allowedFileTypes.value)) {
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
  rememberCurrentChatSessionComposerState();
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
  if (isSlashCommandMenuVisible.value) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      slashCommandHighlightIndex.value =
        (slashCommandHighlightIndex.value + 1) %
        filteredSlashCommands.value.length;
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      slashCommandHighlightIndex.value =
        (slashCommandHighlightIndex.value -
          1 +
          filteredSlashCommands.value.length) %
        filteredSlashCommands.value.length;
      return;
    }
    if (
      (event.key === "Enter" || event.key === "Tab") &&
      !event.shiftKey &&
      !isImeComposing
    ) {
      event.preventDefault();
      applySlashCommandSelection(
        filteredSlashCommands.value[slashCommandHighlightIndex.value] || null,
      );
      return;
    }
  }
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
  rememberCurrentChatSessionComposerState();
}

function resetDraft() {
  draftText.value = "";
  uploadFiles.value = [];
  clearCurrentChatSessionComposerState();
}

function currentActiveAssistantRow() {
  const requestId = getActiveRequestId();
  const pending = requestId ? pendingRequests.get(requestId) : null;
  if (!pending) return null;
  return messages.value[Number(pending.assistantIndex ?? -1)] || null;
}

function followupFileNames(files = []) {
  return (Array.isArray(files) ? files : [])
    .map((item) => String(item?.name || item?.raw?.name || "").trim())
    .filter(Boolean);
}

function followupQueueItemsForAssistant(assistantMessageId) {
  const normalizedAssistantMessageId = String(assistantMessageId || "").trim();
  if (!normalizedAssistantMessageId) return [];
  return queuedFollowupMessages.value.filter(
    (item) =>
      String(item?.assistantMessageId || "").trim() ===
      normalizedAssistantMessageId,
  );
}

function formatFollowupMergeDetail(queueItems = [], activeStatus = "pending") {
  const count = Array.isArray(queueItems) ? queueItems.length : 0;
  const hasFiles = (queueItems || []).some(
    (item) => followupFileNames(item?.files).length > 0,
  );
  return [
    `1. 接收补充内容 [completed]${count ? `\n   已收到 ${count} 条补充` : ""}`,
    "2. 合并到当前任务上下文 [completed]",
    `3. 重新理解并更新计划 [${activeStatus}]${hasFiles ? "\n   包含附件补充" : ""}`,
  ].join("\n");
}

function enqueueFollowupMessage() {
  const text = String(draftText.value || "").trim();
  const files = uploadFiles.value.slice();
  if (!text && !files.length) return false;
  const activeRow = currentActiveAssistantRow();
  const assistantMessageId = String(activeRow?.id || "").trim();
  if (!activeRow || !assistantMessageId) return false;
  const queueItem = {
    id: createLocalMessageId(),
    text,
    files,
    queuedAt: nowText(),
    assistantMessageId,
  };
  queuedFollowupMessages.value.push(queueItem);
  if (activeRow) {
    activeFollowupAssistantMessageId = assistantMessageId;
    const queueItems = followupQueueItemsForAssistant(assistantMessageId);
    upsertMessageOperation(activeRow, {
      operationId: `plan:followup:${assistantMessageId || queueItem.id}`,
      kind: "plan",
      title: "补充需求",
      summary: `已合并到当前任务，等待当前步骤结束后重新理解`,
      detail: formatFollowupMergeDetail(queueItems, "pending"),
      phase: "running",
      actionType: "none",
      meta: {
        followup_queue_id: queueItem.id,
        followup_queue_ids: queueItems
          .map((item) => String(item?.id || "").trim())
          .filter(Boolean),
        assistant_message_id: assistantMessageId,
        queued_at: queueItem.queuedAt,
      },
    });
    appendMessageProcessLog(activeRow, {
      level: "info",
      text: "已收到补充需求，将合并到当前任务并重新审查前序结果。",
    });
    activeRow.processExpanded = true;
  }
  resetDraft();
  scrollToBottom();
  return true;
}

async function drainQueuedFollowupMessages() {
  if (followupQueueDraining || pendingRequests.size > 0) return;
  const targetAssistantMessageId =
    String(activeFollowupAssistantMessageId || "").trim() ||
    String(queuedFollowupMessages.value[0]?.assistantMessageId || "").trim();
  const queuedForTarget = targetAssistantMessageId
    ? queuedFollowupMessages.value.filter(
        (item) =>
          String(item?.assistantMessageId || "").trim() ===
          targetAssistantMessageId,
      )
    : queuedFollowupMessages.value.slice();
  if (!queuedForTarget.length) return;
  followupQueueDraining = true;
  try {
    queuedFollowupMessages.value = queuedFollowupMessages.value.filter(
      (item) => !queuedForTarget.includes(item),
    );
    await sendMergedFollowupRequest(queuedForTarget, targetAssistantMessageId);
  } finally {
    followupQueueDraining = false;
    if (
      targetAssistantMessageId &&
      String(activeFollowupAssistantMessageId || "").trim() ===
        targetAssistantMessageId
    ) {
      activeFollowupAssistantMessageId = "";
    }
    if (queuedFollowupMessages.value.length && pendingRequests.size === 0) {
      void drainQueuedFollowupMessages();
    }
  }
}

async function buildFollowupFilePayload(queueItems = []) {
  const uploadItems = (Array.isArray(queueItems) ? queueItems : [])
    .flatMap((item) => (Array.isArray(item?.files) ? item.files : []))
    .filter(Boolean);
  const files = uploadItems.map((item) => item.raw).filter(Boolean);
  const imageFiles = files.filter((file) => isImageFile(file));
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
  for (const file of docFiles) {
    const content = await extractTextFromFile(file);
    if (content) {
      const clipped = clipText(content, docMaxCharsPerFile.value);
      docsText += `\n\n【补充附件：${file.name}】\n${clipped}`;
    }
    if (docsText.length >= docMaxCharsTotal.value) {
      docsText = clipText(docsText, docMaxCharsTotal.value);
      break;
    }
  }
  return {
    attachmentNames,
    base64Images,
    docsText,
  };
}

function buildMergedFollowupPrompt(queueItems = [], docsText = "") {
  const followupBlocks = (Array.isArray(queueItems) ? queueItems : [])
    .map((item, index) => {
      const text = String(item?.text || "").trim();
      const names = followupFileNames(item?.files);
      return [
        `补充 ${index + 1}：`,
        text || "（补充了附件）",
        names.length ? `附件：${names.join("、")}` : "",
      ]
        .filter(Boolean)
        .join("\n");
    })
    .filter(Boolean);
  return [
    "用户在当前任务执行期间追加了新要求。请把这些补充合并到当前任务上下文，重新理解目标，审查此前已完成的步骤是否仍满足最新要求，并按最新要求继续处理。",
    "",
    "追加内容：",
    followupBlocks.join("\n\n"),
    docsText,
  ]
    .filter(Boolean)
    .join("\n");
}

async function sendMergedFollowupRequest(
  queueItems = [],
  assistantMessageId = "",
) {
  if (!queueItems.length || !selectedProjectId.value) return;
  let activeChatSessionId = String(currentChatSessionId.value || "").trim();
  if (!activeChatSessionId) return;
  const normalizedAssistantMessageId = String(assistantMessageId || "").trim();
  const assistantIndex = messages.value.findIndex(
    (item) => String(item?.id || "").trim() === normalizedAssistantMessageId,
  );
  const assistantMessage =
    assistantIndex >= 0 ? messages.value[assistantIndex] : null;
  if (!assistantMessage) return;

  const followupIds = queueItems
    .map((item) => String(item?.id || "").trim())
    .filter(Boolean);
  upsertMessageOperation(assistantMessage, {
    operationId: `plan:followup:${normalizedAssistantMessageId || followupIds.join(":")}`,
    kind: "plan",
    title: "补充需求",
    summary: "正在重新理解并更新计划",
    detail: formatFollowupMergeDetail(queueItems, "running"),
    phase: "running",
    actionType: "none",
    meta: {
      assistant_message_id: normalizedAssistantMessageId,
      followup_queue_ids: followupIds,
    },
  });
  appendMessageProcessLog(assistantMessage, {
    level: "info",
    text: "补充需求已合并到当前任务，正在重新理解并更新计划。",
  });
  assistantMessage.content = "";
  assistantMessage.processExpanded = true;

  const filePayload = await buildFollowupFilePayload(queueItems);
  const activeSessionSourceContext = normalizeChatSourceContext(
    currentChatSession.value || {},
  );
  activeSessionSourceContext.followup_replan = {
    merged: true,
    assistant_message_id: normalizedAssistantMessageId,
    queue_ids: followupIds,
    queued_at: queueItems
      .map((item) => String(item?.queuedAt || "").trim())
      .filter(Boolean),
  };

  const finalUserPrompt = appendModelGenerationInstruction(
    buildMergedFollowupPrompt(queueItems, filePayload.docsText),
  );
  const effectiveAutoUseTools = singleRoundAnswerOnly.value
    ? false
    : projectChatToolsExplicitlyEnabled();
  const effectiveSelectedProjectToolNames = effectiveAutoUseTools
    ? selectedProjectToolNames.value
    : [];
  chatLoading.value = true;
  scrollToBottom();
  let requestCancelled = false;
  try {
    const sendResult = await sendProjectChatRequest({
      projectId: selectedProjectId.value,
      activeChatSessionId,
      userMessageId: "",
      assistantMessage,
      assistantIndex,
      finalUserPrompt,
      activeSessionSourceContext,
      attachmentNames: filePayload.attachmentNames,
      base64Images: filePayload.base64Images,
      historyRows: toHistoryRows(messages.value, historyLimit.value),
      effectiveAutoUseTools,
      effectiveToolPriority: projectChatSettings.value.tool_priority || [],
      enabledProjectToolNames: effectiveSelectedProjectToolNames,
      requestKind: "followup_replan",
      replaceAssistantContentOnDone: true,
    });
    requestCancelled = Boolean(sendResult?.cancelled);
    if (requestCancelled) return;
  } catch (err) {
    assistantMessage.content = `请求失败：${err?.message || "未知错误"}`;
    ElMessage.error(err?.message || "追加需求处理失败");
  } finally {
    syncChatLoadingWithCurrentSession();
    singleRoundAnswerOnly.value = false;
    if (selectedProjectId.value && !requestCancelled) {
      await fetchChatSessions(selectedProjectId.value, activeChatSessionId);
    }
    scrollToBottom();
  }
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
  selectedProjectToolNames.value = kept;
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
  activeSettingsPanel.value = inferSettingsPanelFromPath(route.path);
}

function openSettingsCenter(panelId = "chat") {
  const normalizedPanelId = String(panelId || "").trim() || "chat";
  activeSettingsPanel.value = normalizedPanelId;
  const targetPath = isSettingsCenterRoute.value
    ? resolveSettingsAwarePanelPath(route.path, normalizedPanelId, "/chat")
    : buildChatSettingsRoute("/chat");
  void router.push(targetPath);
}

function openComposerExecutionDetail() {
  const runnerSessionId = String(
    nativeExternalAgentSession.value?.sessionId || "",
  ).trim();
  if (runnerSessionId) {
    nativeExternalAgentDetailActiveTab.value = "terminal";
    nativeExternalAgentSessionDetailVisible.value = true;
    return;
  }
  if (hasChatTaskTree.value) {
    void openTaskTreePanel();
    return;
  }
  if (terminalApprovalPrompt.value) {
    terminalApprovalDialogVisible.value = true;
    return;
  }
  openSettingsCenter("chat");
}

async function handleComposerExecutionPrimaryAction() {
  if (!hasSelectedProject.value) {
    ElMessage.warning("请先选择项目");
    return;
  }
  if (!isExternalAgentMode.value) {
    openSettingsCenter("chat");
    return;
  }
  if (
    externalAgentConnectorRequired.value ||
    !workspacePathConfigured.value ||
    workspacePathDirty.value ||
    !nativeDesktopBridgeAvailable.value
  ) {
    openSettingsCenter("chat");
    return;
  }
  await runNativeRunnerSelfCheck({ silent: false });
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
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) return;
  const nextQuery = { ...route.query, project_id: normalizedProjectId };
  delete nextQuery.chat_session_id;
  delete nextQuery.message_id;
  void router.replace({ query: nextQuery }).catch(() => {});
  selectedProjectId.value = normalizedProjectId;
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
    botPlatformConnectors.value = Array.isArray(
      data?.config?.bot_platform_connectors,
    )
      ? data.config.bot_platform_connectors.map(normalizeBotPlatformConnector)
      : [];
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
    botPlatformConnectors.value = [];
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
  projects.value = await fetchAllVisibleProjects();
  if (!projects.value.length) {
    clearSelectedProjectId();
    return;
  }
  const savedProjectId = readSelectedProjectId();
  if (
    savedProjectId &&
    !(projects.value || []).some((item) => item.id === savedProjectId)
  ) {
    clearSelectedProjectId();
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
  const savedProjectId = readSelectedProjectId();
  const initialProjectId = resolveAvailableProjectId(
    routeProjectId || savedProjectId,
  );
  if (initialProjectId) {
    selectedProjectId.value = initialProjectId;
    writeSelectedProjectId(initialProjectId);
    return initialProjectId;
  }
  clearSelectedProjectState();
  return "";
}

async function handleProjectCreated(event) {
  const createdProjectId = String(event?.detail?.projectId || "").trim();
  await fetchProjects();
  const nextProjectId = resolveAvailableProjectId(
    createdProjectId || readSelectedProjectId(),
  );
  if (!nextProjectId) return;
  if (nextProjectId === String(selectedProjectId.value || "").trim()) {
    writeSelectedProjectId(nextProjectId);
    return;
  }
  selectedProjectId.value = nextProjectId;
}

async function fetchProvidersByProject(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  projectSettingsHydrating.value = true;
  if (
    projectSettingsHydratedProjectId.value &&
    projectSettingsHydratedProjectId.value !== normalizedProjectId
  ) {
    projectSettingsHydratedProjectId.value = "";
  }
  if (!normalizedProjectId) {
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
    projectWorkspaceDraft.value = "";
    workspacePathDraft.value = "";
    projectAiEntryFile.value = "";
    aiEntryFileDraft.value = "";
    chatSessions.value = [];
    currentChatSessionId.value = "";
    applyTaskTreePayload(null);
    taskTreePanelVisible.value = false;
    autoSaveState.value = "idle";
    autoSaveUpdatedAt.value = "";
    lastAutoSavedFingerprint = "";
    projectSettingsHydratedProjectId.value = "";
    await fetchGlobalProviders();
    projectChatSettings.value = applyLocalConnectorRuntimeSettings({
      ...CHAT_SETTINGS_DEFAULTS,
    });
    projectSettingsHydrating.value = false;
    return;
  }
  let hydrated = false;
  try {
    const data = await fetchProjectChatProviders(normalizedProjectId);
    const rawSettings =
      data?.chat_settings && typeof data.chat_settings === "object"
        ? data.chat_settings
        : {};
    providers.value = data.providers || [];
    localConnectors.value = Array.isArray(data?.local_connectors)
      ? data.local_connectors
      : [];
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
    projectWorkspaceDraft.value = projectWorkspacePath.value;
    projectAiEntryFile.value = String(data?.project_ai_entry_file || "").trim();
    aiEntryFileDraft.value = projectAiEntryFile.value;
    workspacePathDraft.value = String(
      settings.connector_workspace_path ||
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
    selectedEmployeeIds.value = normalizeChatSelectedEmployeeIds(
      settings.selected_employee_ids || [],
      allEmployeeIds,
    );

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
    if (
      hydrated &&
      normalizedProjectId === String(selectedProjectId.value || "").trim()
    ) {
      await nextTick();
      markAutoSaveSynced();
      projectSettingsHydratedProjectId.value = normalizedProjectId;
      autoSaveState.value = "saved";
      scheduleExternalAgentStatusRefresh({ force: true });
    }
    projectSettingsHydrating.value = false;
  }
}

async function handleQuickCreateEmployee(payload) {
  employeeCreateSubmitting.value = true;
  try {
    const employeeRes = await createEmployeeFromDraftRequest({
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
  const employeeIds = normalizeChatSelectedEmployeeIds(
    selectedEmployeeIds.value || [],
    (projectEmployees.value || []).map((item) => String(item?.id || "").trim()),
  );
  const requestedChatMode = String(
    projectChatSettings.value.chat_mode || CHAT_SETTINGS_DEFAULTS.chat_mode,
  )
    .trim()
    .toLowerCase();
  return applyLocalConnectorRuntimeSettings({
    ...projectChatSettings.value,
    chat_mode:
      requestedChatMode === "external_agent" ? "external_agent" : "system",
    external_agent_type: String(
      projectChatSettings.value.external_agent_type ||
        CHAT_SETTINGS_DEFAULTS.external_agent_type,
    ).trim(),
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
    auto_use_tools_explicit: Boolean(
      projectChatSettings.value.auto_use_tools_explicit,
    ),
    enabled_project_tool_names: [...selectedProjectToolNames.value],
  });
}

const autoSaveFingerprint = computed(() => {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId || projectSettingsHydrating.value) return "";
  if (projectSettingsHydratedProjectId.value !== projectId) return "";
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
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId || projectSettingsHydrating.value) return;
  if (projectSettingsHydratedProjectId.value !== projectId) return;
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
  if (
    projectSettingsHydrating.value ||
    projectSettingsHydratedProjectId.value !== projectId
  ) {
    if (!silent) {
      ElMessage.warning("项目对话设置仍在加载，请稍后再保存");
    }
    return;
  }
  clearAutoSaveTimer();
  autoSaveState.value = "saving";
  settingsSaving.value = true;
  try {
    const payload = buildProjectChatSettingsPayload();
    const data = await saveProjectChatSettingsRequest(projectId, payload);
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

function upsertChatSessionFromRealtime(sessionPayload) {
  const session = normalizeChatSession(sessionPayload || {});
  if (!session.id) return null;
  chatSessions.value = [
    session,
    ...chatSessions.value.filter((item) => item.id !== session.id),
  ];
  return session;
}

function setGroupChatLiveStatus(eventData) {
  const sessionId = String(eventData?.chat_session_id || "").trim();
  if (!sessionId) return;
  groupChatLiveStatuses.value = {
    ...groupChatLiveStatuses.value,
    [sessionId]: {
      status: String(eventData?.status || "").trim(),
      message: String(eventData?.message || "").trim(),
      updated_at: new Date().toISOString(),
      source_context: normalizeChatSourceContext(
        eventData?.source_context || {},
      ),
    },
  };
}

function appendRealtimeChatMessage(eventData) {
  if (applyRealtimeChatMessagePayload(eventData)) {
    scrollToBottom();
  }
}

async function fetchChatSessions(
  projectId,
  preferredSessionId = "",
  options = {},
) {
  if (!projectId) {
    chatSessionsLoading.value = false;
    chatSessions.value = [];
    currentChatSessionId.value = "";
    messages.value = [];
    draftText.value = "";
    uploadFiles.value = [];
    chatHistoryLoadedCount.value = 0;
    return "";
  }
  chatSessionsLoading.value = true;
  try {
    const data = await api.get(
      `/projects/${encodeURIComponent(projectId)}/chat/sessions`,
      {
        params: { limit: 50 },
      },
    );
    chatSessions.value = (data.sessions || []).map(normalizeChatSession);
    const remembered =
      options.useRemembered === false ? "" : restoreChatSession(projectId);
    const preferred = String(preferredSessionId || "").trim() || remembered;
    const excludedSessionIds = new Set(
      (Array.isArray(options.excludeSessionIds)
        ? options.excludeSessionIds
        : []
      )
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    );
    const fallback =
      options.allowFallback === false
        ? ""
        : String(
            chatSessions.value.find(
              (item) => !excludedSessionIds.has(String(item?.id || "").trim()),
            )?.id || "",
          ).trim();
    const resolved =
      [preferred, fallback].find(
        (candidate) =>
          candidate &&
          !excludedSessionIds.has(candidate) &&
          chatSessions.value.some((item) => item.id === candidate),
      ) || "";
    rememberCurrentChatSessionMessages();
    rememberCurrentChatSessionComposerState();
    currentChatSessionId.value = resolved;
    applyChatSessionComposerState(projectId, resolved);
    rememberChatSession(projectId, resolved);
    return resolved;
  } catch (err) {
    chatSessions.value = [];
    currentChatSessionId.value = "";
    draftText.value = "";
    uploadFiles.value = [];
    chatHistoryLoadedCount.value = 0;
    ElMessage.error(err?.detail || err?.message || "加载会话列表失败");
    return "";
  } finally {
    chatSessionsLoading.value = false;
  }
}

async function refreshChatSessionsKeepingCurrent() {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) return;
  const currentId = String(currentChatSessionId.value || "").trim();
  await fetchChatSessions(projectId, currentId, { useRemembered: false });
}

async function fetchChatHistory(
  projectId,
  chatSessionId = currentChatSessionId.value,
  options = {},
) {
  const append = options.append === true;
  if (!projectId) {
    activeChatHistoryLoadingKey = "";
    chatHistoryLoading.value = false;
    messages.value = [];
    draftText.value = "";
    uploadFiles.value = [];
    chatHistoryLoadedCount.value = 0;
    chatHistoryReachedEnd.value = false;
    applyTaskTreePayload(null);
    resetTerminalPanel();
    return;
  }
  const normalizedSessionId = String(chatSessionId || "").trim();
  if (!append) {
    rememberCurrentChatSessionMessages();
    rememberCurrentChatSessionComposerState();
  }
  currentChatSessionId.value = normalizedSessionId;
  if (!append) {
    applyChatSessionComposerState(projectId, normalizedSessionId);
  }
  syncChatLoadingWithCurrentSession();
  if (!normalizedSessionId) {
    activeChatHistoryLoadingKey = "";
    chatHistoryLoading.value = false;
    messages.value = [];
    chatHistoryLoadedCount.value = 0;
    chatHistoryReachedEnd.value = false;
    applyTaskTreePayload(null);
    resetTerminalPanel();
    return;
  }
  const loadingKey = [
    String(projectId || "").trim(),
    normalizedSessionId,
    append ? "append" : "replace",
    Date.now(),
  ].join("|");
  if (!append) {
    activeChatHistoryLoadingKey = loadingKey;
    chatHistoryLoading.value = true;
  }
  const offset = Math.max(0, Number(options.offset ?? 0) || 0);
  const limit = Math.max(
    1,
    Number(options.limit || CHAT_HISTORY_PAGE_SIZE) || CHAT_HISTORY_PAGE_SIZE,
  );
  const container = messagesContainer.value;
  const previousScrollHeight = Number(container?.scrollHeight || 0);
  const previousScrollTop = Number(container?.scrollTop || 0);
  try {
    const [data, runtimePayload] = await Promise.all([
      api.get(`/projects/${encodeURIComponent(projectId)}/chat/history`, {
        params: {
          limit,
          offset,
          chat_session_id: normalizedSessionId,
        },
      }),
      append
        ? Promise.resolve(null)
        : fetchPersistedChatRuntime(projectId, normalizedSessionId),
    ]);
    const historyRows = (data.messages || []).map(mapHistoryMessage);
    chatHistoryReachedEnd.value = historyRows.length < limit;
    if (append) {
      messages.value = [...historyRows, ...messages.value];
    } else {
      const liveRows = hasPendingRequestForChatSession(normalizedSessionId)
        ? getRememberedChatSessionMessages(projectId, normalizedSessionId)
        : null;
      messages.value =
        Array.isArray(liveRows) && liveRows.length
          ? liveRows
          : applyPersistedChatRuntimeRows(historyRows, runtimePayload);
    }
    rememberChatSessionMessages(projectId, normalizedSessionId, messages.value);
    chatHistoryLoadedCount.value = messages.value.length;
    rememberChatSession(projectId, normalizedSessionId);
    await fetchChatTaskTree(projectId, normalizedSessionId, { silent: true });
    if (!append) {
      await restoreInteractiveChatRuntime(
        projectId,
        normalizedSessionId,
        messages.value,
        runtimePayload,
      );
    }
    if (append) {
      nextTick(() => {
        if (!messagesContainer.value) return;
        const nextScrollHeight = Number(
          messagesContainer.value.scrollHeight || 0,
        );
        messagesContainer.value.scrollTop =
          nextScrollHeight - previousScrollHeight + previousScrollTop;
        updateMessagesBottomStickiness(messagesContainer.value);
      });
    } else {
      scrollToBottom();
    }
  } catch (err) {
    if (!append) {
      messages.value = [];
      chatHistoryLoadedCount.value = 0;
      chatHistoryReachedEnd.value = false;
    }
    ElMessage.error(
      err?.detail ||
        err?.message ||
        (append ? "加载更早消息失败" : "加载聊天记录失败"),
    );
  } finally {
    if (!append && activeChatHistoryLoadingKey === loadingKey) {
      activeChatHistoryLoadingKey = "";
      chatHistoryLoading.value = false;
    }
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
    const body =
      options.sourceContext && typeof options.sourceContext === "object"
        ? {
            source_context: options.sourceContext,
            title: String(options.title || "").trim(),
          }
        : {};
    const data = await api.post(
      `/projects/${encodeURIComponent(projectId)}/chat/sessions`,
      body,
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
      rememberCurrentChatSessionMessages();
      rememberCurrentChatSessionComposerState();
      currentChatSessionId.value = session.id;
      applyChatSessionComposerState(projectId, session.id);
      rememberChatSession(projectId, session.id);
      clearTaskTreeSessionMemory(projectId);
      clearWorkSessionMemory(projectId);
      currentWorkSessionId.value = "";
      clearOngoingTaskRestoreNotice();
      messages.value = [];
      chatHistoryLoadedCount.value = 0;
      applyTaskTreePayload(null);
      resetTerminalPanel();
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

async function updateChatSession(chatSessionId, options = {}) {
  const projectId = String(selectedProjectId.value || "").trim();
  const normalizedSessionId = String(chatSessionId || "").trim();
  if (!projectId || !normalizedSessionId) {
    return null;
  }
  try {
    const data = await api.patch(
      `/projects/${encodeURIComponent(projectId)}/chat/sessions/${encodeURIComponent(normalizedSessionId)}`,
      {
        title: String(options.title || "").trim(),
        source_context:
          options.sourceContext && typeof options.sourceContext === "object"
            ? options.sourceContext
            : {},
      },
    );
    const session = normalizeChatSession(data.session || {});
    if (!session.id) {
      throw new Error("更新会话失败");
    }
    chatSessions.value = [
      session,
      ...chatSessions.value.filter((item) => item.id !== session.id),
    ];
    if (currentChatSessionId.value === session.id) {
      rememberChatSession(projectId, session.id);
    }
    return session;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "更新会话失败");
    return null;
  }
}

async function resolveGroupChatSourceId() {
  const projectId = String(selectedProjectId.value || "").trim();
  const sessionId = String(groupChatEditingSessionId.value || "").trim();
  if (!projectId || !sessionId) return;
  if (groupChatResolving.value) return;
  groupChatResolving.value = true;
  try {
    await refreshChatSessionsKeepingCurrent();
    const data = await api.post(
      `/projects/${encodeURIComponent(projectId)}/chat/sessions/${encodeURIComponent(sessionId)}/resolve-source`,
      {
        identity:
          String(groupChatDraft.value.resolve_identity || "bot").trim() ===
          "user"
            ? "user"
            : "bot",
      },
    );
    const session = normalizeChatSession(data.session || {});
    if (!session.id) {
      throw new Error("解析群 ID 失败");
    }
    chatSessions.value = [
      session,
      ...chatSessions.value.filter((item) => item.id !== session.id),
    ];
    groupChatDraft.value = {
      ...groupChatDraft.value,
      title: String(session.title || groupChatDraft.value.title || "").trim(),
      platform:
        session.source_context.platform ||
        groupChatDraft.value.platform ||
        "feishu",
      connector_id:
        session.source_context.connector_id ||
        groupChatDraft.value.connector_id ||
        "",
      external_chat_name:
        session.source_context.external_chat_name ||
        groupChatDraft.value.external_chat_name ||
        "",
      resolve_identity:
        session.source_context.resolve_identity ||
        groupChatDraft.value.resolve_identity ||
        "bot",
    };
    ElMessage.success(
      data.resolved === false ? "群 ID 已是解析状态" : "群 ID 已解析并绑定",
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "解析群 ID 失败");
  } finally {
    groupChatResolving.value = false;
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

function resetGroupChatDraft() {
  if (groupChatCreating.value) return;
  groupChatEditingSessionId.value = "";
  groupChatDraft.value = {
    title: "",
    platform: "feishu",
    connector_id: "",
    external_chat_name: "",
    resolve_identity: "bot",
  };
}

function openGroupChatDialog(session = null) {
  if (chatLoading.value) {
    ElMessage.warning("当前回答进行中，暂时不能新建机器人对话");
    return;
  }
  if (!hasSelectedProject.value) {
    ElMessage.warning("请先选择项目");
    return;
  }
  if (
    session &&
    typeof session === "object" &&
    String(session.id || "").trim()
  ) {
    const source = normalizeChatSourceContext(session);
    groupChatEditingSessionId.value = String(session.id || "").trim();
    groupChatDraft.value = {
      title: String(session.title || "").trim(),
      platform: source.platform || "feishu",
      connector_id: source.connector_id,
      external_chat_name: source.external_chat_name,
      resolve_identity: source.resolve_identity || "bot",
    };
  } else {
    resetGroupChatDraft();
  }
  groupChatDialogVisible.value = true;
}

async function submitGroupChatDialog() {
  const platform = String(groupChatDraft.value.platform || "").trim();
  const connectorId = String(groupChatDraft.value.connector_id || "").trim();
  const externalChatName = String(
    groupChatDraft.value.external_chat_name || "",
  ).trim();
  if (!platform || !connectorId) {
    ElMessage.warning("请选择平台并绑定机器人");
    return;
  }
  groupChatCreating.value = true;
  try {
    const wasEditing = Boolean(groupChatEditingSessionId.value);
    const hasLinkedGroup = Boolean(externalChatName);
    const title = String(groupChatDraft.value.title || "").trim();
    const sourceContext = {
      source_type: hasLinkedGroup ? "group_message" : "manual_ai_chat",
      platform,
      connector_id: connectorId,
      external_chat_name: externalChatName,
      resolve_identity:
        String(groupChatDraft.value.resolve_identity || "bot").trim() === "user"
          ? "user"
          : "bot",
    };
    const connectorOption = groupBotConnectorOptions.value.find(
      (item) => item.value === connectorId,
    );
    const defaultTitle = hasLinkedGroup
      ? `${formatChatPlatformLabel(platform)}群：${externalChatName}`
      : `${formatChatPlatformLabel(platform)}机器人对话${
          connectorOption?.name ? ` · ${connectorOption.name}` : ""
        }`;
    let session = null;
    if (groupChatEditingSessionId.value) {
      session = await updateChatSession(groupChatEditingSessionId.value, {
        title: title || defaultTitle,
        sourceContext,
      });
    } else {
      session = await createChatSession({
        switchTo: true,
        title: title || defaultTitle,
        sourceContext,
      });
    }
    if (!session) return;
    groupChatDialogVisible.value = false;
    resetGroupChatDraft();
    ElMessage.success(
      wasEditing
        ? "机器人对话已更新"
        : hasLinkedGroup
          ? "已创建机器人对话，并保留群上下文"
          : "已创建机器人对话",
    );
  } finally {
    groupChatCreating.value = false;
  }
}

async function handleCreateNewConversation() {
  if (chatSessionsLoading.value || chatHistoryLoading.value) {
    ElMessage.warning("对话记录加载中，请稍后再新建对话");
    return;
  }
  if (
    !String(selectedProjectId.value || "").trim() &&
    ENABLE_GLOBAL_CHAT_WITHOUT_PROJECT
  ) {
    currentChatSessionId.value = "";
    messages.value = [];
    chatHistoryLoadedCount.value = 0;
    chatHistoryReachedEnd.value = false;
    activeComposerAssist.value = "";
    resetDraft();
    scrollToBottom();
    return;
  }
  if ((chatSessions.value || []).length) {
    const projectId = String(selectedProjectId.value || "").trim();
    rememberCurrentChatSessionMessages();
    rememberCurrentChatSessionComposerState();
    currentChatSessionId.value = "";
    rememberChatSession(projectId, "");
    clearTaskTreeSessionMemory(projectId);
    clearWorkSessionMemory(projectId);
    currentWorkSessionId.value = "";
    clearOngoingTaskRestoreNotice();
    messages.value = [];
    chatHistoryLoadedCount.value = 0;
    chatHistoryReachedEnd.value = false;
    activeComposerAssist.value = "";
    resetDraft();
    applyTaskTreePayload(null);
    resetTerminalPanel();
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
    clearPersistedChatRuntime(projectId, chatSessionId);
    const isCurrentSession = currentChatSessionId.value === chatSessionId;
    if (isCurrentSession) {
      clearChatSessionMemory(projectId);
      clearTaskTreeSessionMemory(projectId);
      clearWorkSessionMemory(projectId);
      currentWorkSessionId.value = "";
      clearOngoingTaskRestoreNotice();
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
  const currentTitle = String(
    activeChatSessionTitle.value || "当前会话",
  ).trim();
  try {
    await ElMessageBox.confirm(
      `确认清空「${currentTitle}」吗？当前会话的聊天记录会被删除，且不可恢复。`,
      "清空当前会话",
      {
        confirmButtonText: "清空",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
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
    clearPersistedChatRuntime(projectId, chatSessionId);
    clearChatSessionMemory(projectId);
    clearTaskTreeSessionMemory(projectId);
    clearWorkSessionMemory(projectId);
    currentWorkSessionId.value = "";
    clearOngoingTaskRestoreNotice();
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

// ============================================================
// WebSocket 事件分发主入口（~1333行，待迁入 realtimeEventMappers.js / composable）
// 处理：心跳、后台操作、pending request 结算、终端镜像、agent 就绪、工作流状态
// ============================================================
async function handleSocketMessage(eventData) {
  const { eventType, requestId } = normalizeProjectChatWsEvent(eventData);
  if (isProjectChatHeartbeatEvent(eventType)) {
    return;
  }
  if (isBackgroundOperationEvent(eventType)) {
    const matched = findAssistantRowByOperationTaskId(
      String(eventData?.task_id || "").trim(),
      String(eventData?.chat_session_id || "").trim(),
    );
    if (matched?.row) {
      const taskId = String(eventData?.task_id || "").trim();
      const chatSessionId = String(eventData?.chat_session_id || "").trim();
      const resumeCommand = String(eventData?.resume_command || "").trim();
      if (isTaskStateEvent(eventType)) {
        const { context, taskStatus, operation } =
          buildBackgroundTaskStateOperation({
            eventData,
            eventType,
            taskId,
            chatSessionId,
            resumeCommand,
          });
        upsertMessageOperation(matched.row, operation);
        if (
          ["succeeded", "failed", "timeout", "cancelled"].includes(
            taskStatus,
          ) &&
          !context.hasAuthPrompt &&
          !resumeCommand
        ) {
          completePendingExternalOperationRequestByRow(
            matched.row,
            String(eventData?.summary || eventData?.message || "").trim() ||
              (taskStatus === "succeeded" ? "操作已完成" : "操作未完成"),
            { reject: taskStatus !== "succeeded" },
          );
        }
      } else if (isWaitingOperationEvent(eventType)) {
        const { operation } = buildWaitingBackgroundOperation({
          eventData,
          taskId,
          chatSessionId,
          resumeCommand,
        });
        upsertMessageOperation(matched.row, operation);
      } else if (isCompletedOperationEvent(eventType)) {
        const workflowKind = String(eventData?.workflow_kind || "").trim();
        const isAuthOperation =
          eventType === "authorization_completed" ||
          workflowKind === "auth_login";
        const completionSummary = resumeCommand
          ? isAuthOperation
            ? "授权完成，正在自动继续"
            : "操作完成，正在自动继续"
          : isAuthOperation
            ? "授权完成"
            : "操作完成";
        const completionNote = resumeCommand
          ? `> ✅ ${isAuthOperation ? "授权完成" : "操作完成"}，系统正在自动继续。`
          : `> ✅ ${isAuthOperation ? "授权完成，检测通过" : "操作完成"}。`;
        const completionMessage = String(
          eventData?.message ||
            (resumeCommand
              ? isAuthOperation
                ? "授权完成，检测通过，系统正在自动继续上一条待执行命令。"
                : "操作完成，系统正在自动继续上一条待执行命令。"
              : isAuthOperation
                ? "授权完成，检测通过。"
                : "操作完成。"),
        ).trim();
        upsertMessageOperation(matched.row, {
          operationId: isAuthOperation
            ? `auth:${taskId || "active"}`
            : `workflow:${workflowKind || "external_operation"}:${taskId || "active"}`,
          kind: isAuthOperation ? "auth" : "request",
          title: isAuthOperation ? "授权状态" : "操作状态",
          summary: completionSummary,
          detail: completionMessage,
          phase: "completed",
          meta: {
            task_id: taskId,
            chat_session_id: chatSessionId,
            resume_command: resumeCommand,
          },
        });
        const replacedTransientContent = isAuthOperation
          ? replaceTransientAuthOperationContent(matched.row, completionMessage)
          : false;
        if (!replacedTransientContent) {
          appendAssistantStatusNote(matched.row, completionNote);
        }
        completeBackgroundPendingRequestOperation(matched.row, {
          taskId,
          chatSessionId,
          summary: completionSummary,
        });
        if (!resumeCommand) {
          completePendingExternalOperationRequest(matched, completionMessage);
        }
      } else if (isResumeStartedEvent(eventType)) {
        const workflowKind = String(eventData?.workflow_kind || "").trim();
        const isAuthOperation =
          eventType === "authorization_resume_started" ||
          workflowKind === "auth_login";
        completeBackgroundPendingRequestOperation(matched.row, {
          taskId,
          chatSessionId,
          summary: isAuthOperation
            ? "授权完成，已转入自动继续"
            : "操作完成，已转入自动继续",
        });
        const existingResumeRunning = messageOperations(matched.row).some(
          (item) =>
            String(item?.kind || "")
              .trim()
              .toLowerCase() === "request" &&
            String(item?.summary || "").includes("授权完成，正在自动继续"),
        );
        upsertMessageOperation(matched.row, {
          operationId: isAuthOperation
            ? `auth:${taskId || "active"}`
            : `workflow:${workflowKind || "external_operation"}:${taskId || "active"}`,
          kind: isAuthOperation ? "auth" : "request",
          title: isAuthOperation ? "授权状态" : "操作状态",
          summary: isAuthOperation
            ? "授权完成，已转入自动继续"
            : "操作完成，已转入自动继续",
          detail: String(
            eventData?.message ||
              "操作完成，系统正在自动继续上一条待执行命令。",
          ).trim(),
          phase: "completed",
          meta: {
            task_id: taskId,
            chat_session_id: chatSessionId,
            resume_command: resumeCommand,
          },
        });
        upsertMessageOperation(matched.row, {
          operationId: `request:${String(eventData?.resume_request_id || requestId || chatSessionId || "resume").trim()}`,
          kind: "request",
          title: "本轮执行",
          summary: isAuthOperation
            ? "授权完成，正在自动继续"
            : "操作完成，正在自动继续",
          detail: String(
            eventData?.message ||
              "操作完成，系统正在自动继续上一条待执行命令。",
          ).trim(),
          phase: "running",
          actionType: "none",
          meta: {
            task_id: taskId,
            chat_session_id: chatSessionId,
            resume_command: resumeCommand,
          },
        });
        matched.row.processExpanded = true;
        const projectId = String(selectedProjectId.value || "").trim();
        const currentSessionId = String(
          currentChatSessionId.value || "",
        ).trim();
        if (
          projectId &&
          chatSessionId &&
          chatSessionId === currentSessionId &&
          resumeCommand &&
          !existingResumeRunning
        ) {
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
            processExpanded: true,
            audit: null,
            taskTreeAudit: null,
            statusNotes: [],
            operations: [],
            time: nowText(),
          };
          messages.value.push(assistantMessage);
          const assistantIndex = messages.value.length - 1;
          chatLoading.value = true;
          try {
            await sendProjectChatRequest({
              projectId,
              activeChatSessionId: chatSessionId,
              assistantMessage,
              assistantIndex,
              finalUserPrompt: appendModelGenerationInstruction(
                buildOperationResumeUserPrompt(resumeCommand, workflowKind),
              ),
              activeSessionSourceContext: normalizeChatSourceContext(
                currentChatSession.value || {},
              ),
              attachmentNames: [],
              base64Images: [],
              historyRows: toHistoryRows(
                messages.value.slice(0, -1),
                historyLimit.value,
              ),
              effectiveAutoUseTools: true,
              effectiveToolPriority: mergeToolPriority(
                projectChatSettings.value.tool_priority || [],
                [],
              ),
              assistAction: null,
              assistToolNames: [],
            });
          } catch (error) {
            assistantMessage.content = `自动继续失败：${error?.message || "未知错误"}`;
          } finally {
            syncChatLoadingWithCurrentSession();
          }
        }
      }
      scrollToBottom();
    }
    if (!requestId) {
      return;
    }
  }
  if (eventType === "error" && isTerminalMirrorControlRequest(requestId)) {
    const message = String(eventData?.message || "项目终端请求失败").trim();
    appendTerminalPanelLine(`! ${message}`);
    const mirrorRow = messages.value[activeTerminalMirrorAssistantIndex.value];
    if (mirrorRow) {
      mirrorRow.displayMode = "terminal";
      mirrorRow.processExpanded = true;
      appendTerminalLog(mirrorRow, `! ${message}`, { mirrorToPanel: false });
      upsertMessageOperation(mirrorRow, {
        operationId: `terminal-error:${requestId}`,
        kind: "terminal",
        title: "项目终端异常",
        summary: message,
        detail: "当前终端会话不可用，请重新执行命令以创建新的项目终端。",
        phase: "failed",
        actionType: "enter_text",
      });
    }
    if (/not running|not found|closed|不可用|未运行/i.test(message)) {
      terminalMirrorConnected.value = false;
      hostTerminalSessionId.value = "";
      terminalPanelStatus.value = "idle";
      activeTerminalMirrorAssistantIndex.value = -1;
    } else {
      terminalPanelStatus.value = "error";
    }
    ElMessage.error(message);
    scrollToBottom();
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
    terminalPanelStatus.value = "running";
    hostTerminalSessionId.value = String(eventData?.session_id || "").trim();
    hostTerminalWorkspacePath.value = String(
      eventData?.workspace_path ||
        hostTerminalWorkspacePath.value ||
        projectWorkspaceResolved.value ||
        "",
    ).trim();
    terminalPanelExpanded.value = true;
    terminalActiveCommand.value = String(
      eventData?.command || terminalActiveCommand.value || "",
    ).trim();
    const connectedSummary = "# 项目终端已连接，完整交互会显示在这里";
    appendTerminalPanelLine(connectedSummary);
    const mirrorRow = messages.value[activeTerminalMirrorAssistantIndex.value];
    if (mirrorRow) {
      mirrorRow.displayMode = "terminal";
      mirrorRow.processExpanded = true;
      appendTerminalLog(mirrorRow, connectedSummary, { mirrorToPanel: false });
      ensureProcessLogVisible(mirrorRow);
      upsertMessageOperation(mirrorRow, {
        operationId: `terminal:${String(eventData?.session_id || eventData?.chat_session_id || "active").trim()}`,
        kind: "terminal",
        title: "需要你继续操作",
        summary: "命令已进入交互模式",
        detail: "能识别的选择题会自动转成表单；无法识别时再查看下方终端输出。",
        phase: "running",
        actionType: "enter_text",
      });
    }
    focusTerminalPanelInput();
    return;
  }
  if (eventType === "workflow_state") {
    const workflowKind = String(eventData?.workflow_kind || "").trim();
    if (workflowKind === "terminal_interaction") {
      const sessionKey = String(
        eventData?.session_id ||
          eventData?.thread_id ||
          eventData?.workflow_id ||
          eventData?.chat_session_id ||
          "active",
      ).trim();
      const mirrorRow =
        messages.value[activeTerminalMirrorAssistantIndex.value];
      if (mirrorRow) {
        upsertMessageOperation(mirrorRow, {
          operationId: `terminal:${sessionKey}`,
          kind: "terminal",
          title:
            String(
              eventData?.status_label ||
                eventData?.workflow_label ||
                "项目终端",
            ).trim() || "项目终端",
          summary:
            String(eventData?.summary || "").trim() || "终端工作流进行中",
          detail: String(eventData?.detail || eventData?.message || "").trim(),
          phase:
            String(eventData?.status || "").trim() === "failed"
              ? "failed"
              : String(eventData?.status || "").trim() === "succeeded"
                ? "completed"
                : "running",
          actionType:
            String(eventData?.action_type || "").trim() || "enter_text",
          meta: {
            session_id: sessionKey,
            workflow_kind: workflowKind,
            workflow_id: String(eventData?.workflow_id || "").trim(),
            chat_session_id: String(eventData?.chat_session_id || "").trim(),
          },
        });
        scrollToBottom();
      }
    }
  }
  if (eventType === "terminal_mirror_stopped") {
    terminalMirrorConnected.value = false;
    terminalPanelStatus.value = "idle";
    hostTerminalSessionId.value = "";
    terminalActiveCommand.value = "";
    terminalStructuredInteraction.value = null;
    const exitCode = eventData?.exit_code;
    appendTerminalPanelLine(
      exitCode === null || exitCode === undefined
        ? "# 项目终端已停止"
        : `# 项目终端已停止 · exit=${exitCode}`,
    );
    const mirrorRow = messages.value[activeTerminalMirrorAssistantIndex.value];
    if (mirrorRow) {
      upsertMessageOperation(mirrorRow, {
        operationId: `terminal:${String(eventData?.session_id || eventData?.chat_session_id || "active").trim()}`,
        kind: "terminal",
        title: "项目终端",
        summary:
          exitCode === null || exitCode === undefined
            ? "终端会话已停止"
            : `终端已结束 · exit=${exitCode}`,
        detail: "",
        phase:
          exitCode === null || exitCode === undefined || Number(exitCode) === 0
            ? "completed"
            : "failed",
      });
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
      mirrorRow.displayMode = "terminal";
      mirrorRow.processExpanded = true;
      appendTerminalLog(mirrorRow, chunk, { mirrorToPanel: false });
      refreshTerminalStructuredInteraction(
        mirrorRow,
        activeTerminalMirrorAssistantIndex.value,
      );
    }
    return;
  }
  if (eventType === "terminal_approval_required") {
    const mirrorRow = messages.value[activeTerminalMirrorAssistantIndex.value];
    if (mirrorRow) {
      upsertMessageOperation(mirrorRow, {
        operationId: `approval:${String(eventData?.key || eventData?.chat_session_id || "terminal").trim()}`,
        kind: "approval",
        title: String(eventData?.title || "终端审批").trim() || "终端审批",
        summary: "等待你确认后继续",
        detail: String(
          eventData?.description || eventData?.message || "",
        ).trim(),
        phase: "waiting_user",
        actionType: "approve",
        meta: {
          prompt_key: String(
            eventData?.key || eventData?.chat_session_id || "terminal",
          ).trim(),
          approval_mode: "terminal",
          message: String(eventData?.message || "").trim(),
          description: String(eventData?.description || "").trim(),
        },
      });
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
  if (
    eventType === "chat_message_created" ||
    eventType === "chat_message_updated"
  ) {
    appendRealtimeChatMessage(eventData);
    return;
  }
  if (eventType === "chat_session_updated") {
    if (eventData?.session) {
      upsertChatSessionFromRealtime(eventData.session);
    }
    setGroupChatLiveStatus(eventData);
    return;
  }
  if (eventType === "agent_runtime_permission_action_result") {
    if (applyAgentRuntimePermissionActionResult(eventData)) {
      scrollToBottom();
    }
    return;
  }
  if (eventType === "agent_runtime_operation_resume_result") {
    if (applyAgentRuntimeOperationResumeResult(eventData)) {
      scrollToBottom();
    }
    return;
  }
  if (eventType === "group_chat_status") {
    if (eventData?.session) {
      upsertChatSessionFromRealtime(eventData.session);
    }
    setGroupChatLiveStatus(eventData);
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
  const row = resolvePendingRequestRow(pending);
  if (!row) {
    rejectAndCleanupRequest(requestId, pending, new Error("消息上下文已失效"));
    syncChatLoadingWithCurrentSession();
    return;
  }
  const isPendingCurrentSession = isCurrentChatSession(
    pending.projectId,
    pending.chatSessionId,
  );
  if (eventType === "operation_event") {
    upsertMessageOperation(row, eventData);
    scrollToBottom();
    return;
  }
  if (eventType === "agent_runtime_event") {
    if (applyAgentRuntimeEvent(row, eventData)) {
      scrollToBottom();
    }
    return;
  }
  if (eventType === "intent_classified") {
    scrollToBottom();
    return;
  }
  if (eventType === "plan_created") {
    applyPlanCreatedEvent(row, eventData, requestId);
    scrollToBottom();
    return;
  }
  if (eventType === "verification_started") {
    if (!String(eventData?.plan_id || "").trim()) {
      scrollToBottom();
      return;
    }
    applyVerificationStartedEvent(row, eventData, requestId);
    scrollToBottom();
    return;
  }
  if (eventType === "verification_finished") {
    if (!String(eventData?.plan_id || "").trim()) {
      scrollToBottom();
      return;
    }
    applyVerificationFinishedEvent(row, eventData, requestId);
    scrollToBottom();
    return;
  }
  if (eventType === "command_planned" || eventType === "tool_planned") {
    applyPlannedActionEvent(row, eventData, requestId);
    scrollToBottom();
    return;
  }
  if (eventType === "start") {
    terminalPanelStatus.value = "running";
    const taskTreePayload = eventData
      ? resolveTaskTreeEventPayload(eventData)
      : null;
    if (
      isPendingCurrentSession &&
      eventData &&
      (Object.prototype.hasOwnProperty.call(eventData, "task_tree") ||
        Object.prototype.hasOwnProperty.call(eventData, "history_task_tree"))
    ) {
      applyTaskTreePayload(taskTreePayload);
    }
    if (
      isPendingCurrentSession &&
      eventData?.work_session &&
      taskTreePayload &&
      !isTaskTreeArchivedOrDone(taskTreePayload)
    ) {
      applyWorkSessionPayload(eventData.work_session, {
        taskTree: taskTreePayload,
      });
    }
    row.displayMode =
      String(eventData?.chat_mode || "").trim() === "external_agent"
        ? "terminal"
        : "";
    row.effectiveTools = normalizeEffectiveTools(eventData?.effective_tools);
    row.effectiveToolTotal = Number(
      eventData?.effective_tool_total || row.effectiveTools.length || 0,
    );
    if (String(eventData?.chat_mode || "").trim() === "external_agent") {
      upsertMessageOperation(row, {
        operationId: `thinking:${requestId}`,
        kind: "thinking",
        title: "连接 Agent",
        summary: "正在连接外部 Agent",
        detail: "",
        phase: "running",
        actionType: "none",
        meta: {
          request_id: requestId,
        },
      });
    }
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
    upsertMessageOperation(row, {
      operationId: `approval:${String(eventData?.approval_id || requestId).trim()}`,
      kind: "approval",
      title: String(eventData?.title || "操作审批").trim() || "操作审批",
      summary: "等待你确认后继续",
      detail: String(eventData?.message || "").trim(),
      phase: "waiting_user",
      actionType: "approve",
      meta: {
        request_id: String(eventData?.request_id || requestId).trim(),
        approval_id: String(eventData?.approval_id || "").trim(),
        message: String(eventData?.message || "").trim(),
        risk_signals: Array.isArray(eventData?.risk_signals)
          ? eventData.risk_signals
          : [],
      },
    });
    void handleApprovalRequired(eventData, row);
    return;
  }
  if (eventType === "approval_resolved") {
    const approved = Boolean(eventData?.approved);
    terminalApprovalDialogVisible.value = false;
    upsertMessageOperation(row, {
      operationId: `approval:${String(eventData?.approval_id || requestId).trim()}`,
      kind: "approval",
      title: "操作审批",
      summary: approved ? "已批准，继续执行" : "已拒绝，本次取消",
      detail: "",
      phase: approved ? "completed" : "blocked",
    });
    appendAssistantStatusNote(
      row,
      approved ? "> ✅ 已批准，继续执行" : "> ❌ 已拒绝，本次执行取消",
    );
    scrollToBottom();
    return;
  }
  if (eventType === "file_review_required") {
    upsertMessageOperation(row, {
      operationId: `review:${String(eventData?.review_id || requestId).trim()}`,
      kind: "approval",
      title:
        String(eventData?.title || "文件变更审查").trim() || "文件变更审查",
      summary: "等待你确认是否保留当前改动",
      detail: formatFileReviewMessage(eventData),
      phase: "waiting_user",
      actionType: "approve",
      meta: {
        request_id: String(eventData?.request_id || requestId).trim(),
        review_id: String(eventData?.review_id || "").trim(),
        diff_summary:
          eventData?.diff_summary && typeof eventData.diff_summary === "object"
            ? eventData.diff_summary
            : null,
        message: String(eventData?.message || "").trim(),
      },
    });
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
    appendAssistantStatusNote(
      row,
      approved ? "> ✅ 文件变更已审查通过" : "> ❌ 文件变更未通过审查",
    );
    scrollToBottom();
    return;
  }
  if (eventType === "external_executor_event") {
    row.displayMode = "terminal";
    row.processExpanded = true;
    const event =
      eventData?.event && typeof eventData.event === "object"
        ? eventData.event
        : {};
    const executorType = String(event.executor_type || "external_agent").trim();
    const eventStatus = String(event.status || "in_progress").trim();
    const eventMessage = String(event.message || "").trim();
    if (eventMessage) {
      appendTerminalLog(row, eventMessage);
    }
    upsertMessageOperation(row, {
      operationId: `external-agent:${String(eventData?.session_id || requestId).trim()}`,
      kind: "request",
      title: externalAgentDisplayLabel.value,
      summary:
        eventStatus === "completed"
          ? "外部 Agent 执行完成"
          : eventStatus === "failed"
            ? "外部 Agent 执行失败"
            : "外部 Agent 执行中",
      detail: eventMessage,
      phase:
        eventStatus === "completed"
          ? "completed"
          : eventStatus === "failed"
            ? "failed"
            : "running",
      actionType: "none",
      meta: {
        executor_type: executorType,
        task_node_id: String(event.task_node_id || "").trim(),
      },
    });
    scrollToBottom();
    return;
  }
  if (eventType === "status") {
    appendMessageProcessLog(row, {
      level: "info",
      text: "正在处理任务…",
    });
    appendAssistantStatusNote(row, "> ⏳ 正在处理任务…");
    scrollToBottom();
    return;
  }
  if (eventType === "stderr") {
    appendMessageProcessLog(row, {
      level: "warning",
      text: clipText(
        String(
          eventData?.stderr_preview ||
            eventData?.message ||
            "执行过程中出现提示",
        ).trim(),
        220,
      ),
    });
    appendAssistantStatusNote(
      row,
      "> ⚠️ 执行过程中出现提示，正在等待后续处理。",
    );
    scrollToBottom();
    return;
  }
  if (eventType === "command_start") {
    row.processExpanded = true;
    const command = eventCommand(eventData);
    const cwd = String(
      eventData?.cwd || eventData?.workspace_path || "",
    ).trim();
    const toolName = String(eventData?.tool_name || "命令").trim() || "命令";
    const planId = String(eventData?.plan_id || "").trim();
    const stepId = String(eventData?.step_id || "").trim();
    if (planId && stepId) {
      updatePlanOperationStep(row, planId, stepId, {
        status: "running",
        summary: command ? `正在执行命令：${command}` : "正在执行命令",
      });
    }
    appendMessageProcessLog(row, {
      level: "info",
      text: command ? `开始执行命令：${command}` : "开始执行命令",
    });
    upsertMessageOperation(row, {
      operationId: projectChatActionOperationId(eventData),
      kind: "tool",
      title: toolProgressLabel(eventData, toolName),
      summary: "正在执行命令",
      detail: "",
      phase: "running",
      actionType: "none",
      meta: {
        tool_name: toolName,
        command,
        cwd,
        plan_id: planId,
        step_id: stepId,
        tool_index: Number(eventData?.tool_index || 0) || 0,
        tool_count: Number(eventData?.tool_count || 0) || 0,
      },
    });
    appendAssistantStatusNote(row, "> ⏳ 正在执行必要步骤…");
    scrollToBottom();
    return;
  }
  if (eventType === "command_result") {
    const statusText =
      String(eventData?.status || "completed")
        .trim()
        .toLowerCase() || "completed";
    const outputPreview = String(eventData?.output_preview || "").trim();
    const command = eventCommand(eventData);
    const cwd = String(
      eventData?.cwd || eventData?.workspace_path || "",
    ).trim();
    const toolName = String(eventData?.tool_name || "命令").trim() || "命令";
    const planId = String(eventData?.plan_id || "").trim();
    const stepId = String(eventData?.step_id || "").trim();
    if (
      outputPreview &&
      isMcpApprovalCancelledMessage(outputPreview) &&
      pending
    ) {
      pending.mcpApprovalCancelled = true;
    }
    const exitCode = eventData?.exit_code;
    const succeeded =
      (exitCode === null || exitCode === undefined || Number(exitCode) === 0) &&
      ["success", "completed", "ok"].includes(statusText);
    appendMessageProcessLog(row, {
      level: succeeded ? "success" : "warning",
      text: clipText(
        [
          command
            ? `命令${succeeded ? "完成" : "未完成"}：${command}`
            : `命令${succeeded ? "完成" : "未完成"}`,
          outputPreview,
        ]
          .filter(Boolean)
          .join(" · "),
        260,
      ),
    });
    if (planId && stepId) {
      updatePlanOperationStep(row, planId, stepId, {
        status: succeeded ? "completed" : "failed",
        summary: succeeded ? "命令执行完成" : "命令执行未完成",
      });
    }
    upsertMessageOperation(row, {
      operationId: projectChatActionOperationId(eventData),
      kind: "tool",
      title: toolProgressLabel(eventData, toolName),
      summary: succeeded ? "命令执行完成" : "命令执行未完成",
      detail: "",
      phase: succeeded ? "completed" : "failed",
      actionType: "none",
      meta: {
        tool_name: toolName,
        command,
        cwd,
        exit_code:
          exitCode === null || exitCode === undefined
            ? ""
            : String(exitCode).trim(),
        output_preview: outputPreview,
        stdout_preview: String(eventData?.stdout_preview || "").trim(),
        stderr_preview: String(eventData?.stderr_preview || "").trim(),
        error: String(eventData?.error || "").trim(),
        plan_id: planId,
        step_id: stepId,
        tool_index: Number(eventData?.tool_index || 0) || 0,
        tool_count: Number(eventData?.tool_count || 0) || 0,
      },
    });
    if (!succeeded) {
      appendAssistantStatusNote(
        row,
        "> ⚠️ 有执行步骤未完成，正在等待模型给出下一步。",
      );
    }
    scrollToBottom();
    return;
  }
  if (eventType === "usage") {
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
    row.processExpanded = true;
    const toolName = String(eventData?.tool_name || "工具");
    if (pending) {
      pending.lastToolName = toolName;
    }
    appendToolStartLogs(row, eventData);
    appendAssistantStatusNote(row, "> ⏳ 正在处理任务…");
    scrollToBottom();
    return;
  }
  if (eventType === "tool_result") {
    const toolName = String(eventData?.tool_name || "工具");
    const statusText = String(eventData?.status || "")
      .trim()
      .toLowerCase();
    const taskStatus = String(eventData?.task_status || eventData?.status || "")
      .trim()
      .toLowerCase();
    const outputPreview = String(eventData?.output_preview || "").trim();
    const taskId = String(eventData?.task_id || "").trim();
    const authorizationUrl = String(eventData?.authorization_url || "").trim();
    const interactionSchema =
      eventData?.interaction_schema &&
      typeof eventData.interaction_schema === "object"
        ? eventData.interaction_schema
        : null;
    const nextStep = String(eventData?.next_step || "").trim();
    const rawDetail = stripTerminalControlSequences(
      String(eventData?.detail || "").trim() ||
        String(eventData?.output_preview || "").trim() ||
        [authorizationUrl, nextStep].filter(Boolean).join("\n"),
    ).trim();
    if (
      ["operation_wait_task", "cli_plugin_login_task"].includes(
        String(eventData?.source || "").trim(),
      ) &&
      taskId
    ) {
      const workflowKind = String(
        eventData?.operation_kind || eventData?.workflow_kind || "",
      ).trim();
      const isAuthOperation =
        workflowKind === "auth_login" ||
        String(eventData?.source || "").trim() === "cli_plugin_login_task" ||
        Boolean(authorizationUrl);
      const hasAuthPrompt =
        isAuthOperation && hasAuthorizationPromptText(eventData, rawDetail);
      let summary = isAuthOperation
        ? "授权任务已创建，等待后续结果"
        : "操作已创建，等待后续结果";
      let phase = "running";
      if (taskStatus === "queued") {
        summary = isAuthOperation
          ? "授权任务已创建，等待返回授权链接"
          : "操作已创建，等待后续结果";
      } else if (taskStatus === "running") {
        summary = isAuthOperation
          ? "授权流程已启动，正在等待后续结果"
          : "操作已启动，正在等待后续结果";
      } else if (taskStatus === "waiting_user_action") {
        summary =
          isAuthOperation && authorizationUrl
            ? "等待你在浏览器完成授权"
            : interactionSchema
              ? "等待你选择授权业务域"
              : isAuthOperation
                ? "授权流程已启动，等待结构化授权链接返回"
                : "等待你完成操作";
        phase =
          isAuthOperation && !authorizationUrl && !interactionSchema
            ? "running"
            : "waiting_user";
      } else if (taskStatus === "succeeded") {
        summary = isAuthOperation ? "授权完成，检测通过" : "操作完成";
        phase = "completed";
      } else if (["failed", "timeout"].includes(taskStatus)) {
        if (hasAuthPrompt) {
          summary = "等待你在浏览器完成授权";
          phase = "waiting_user";
        } else {
          summary = isAuthOperation ? "授权流程未完成" : "操作未完成";
          phase = "failed";
        }
      }
      upsertMessageOperation(row, {
        operationId: isAuthOperation
          ? `auth:${taskId}`
          : `workflow:${workflowKind || "external_operation"}:${taskId}`,
        kind: isAuthOperation ? "auth" : "request",
        title:
          String(
            eventData?.status_label ||
              eventData?.operation_label ||
              (isAuthOperation ? "网页登录授权" : "操作"),
          ).trim() || (isAuthOperation ? "网页登录授权" : "操作"),
        summary,
        detail: rawDetail,
        phase,
        actionType: authorizationUrl
          ? "open_url"
          : interactionSchema
            ? "interaction_form"
            : "none",
        meta: {
          task_id: taskId,
          authorization_url: authorizationUrl,
          interaction_schema: interactionSchema,
        },
      });
    }
    const success =
      !statusText || ["success", "completed", "ok"].includes(statusText);
    const approvalPending = isMcpApprovalCancelledMessage(outputPreview);
    if (approvalPending && pending) {
      pending.mcpApprovalCancelled = true;
      pending.lastToolName = toolName;
    }
    if (
      isPendingCurrentSession &&
      eventData &&
      Object.prototype.hasOwnProperty.call(eventData, "task_tree")
    ) {
      applyTaskTreePayload(eventData.task_tree);
    }
    appendToolResultLogs(row, eventData);
    if (shouldAutoHandoffProjectHostCommand(eventData)) {
      const handedOff = await handoffProjectHostCommandToTerminal(
        row,
        pending,
        eventData,
      );
      if (handedOff && pending) {
        row.content =
          String(row.content || "").trim() ||
          "命令已接入项目终端；如出现可识别交互，会在终端输出下方显示表单。";
        const activeClient = wsClient.value;
        if (activeClient && typeof activeClient.send === "function") {
          activeClient.send({ type: "cancel", request_id: requestId });
        }
        resolvePendingRequest(requestId, pending, row.content || "");
        scrollToBottom();
        return;
      }
    }
    if (approvalPending) {
      appendAssistantStatusNote(row, "> ⏳ 等待你确认后继续。");
    } else if (!success) {
      appendAssistantStatusNote(
        row,
        "> ⚠️ 有执行步骤未完成，正在等待模型给出下一步。",
      );
    }
    scrollToBottom();
    return;
  }
  if (eventType === "auto_continue") {
    const message =
      String(eventData?.message || "系统已自动继续执行后续步骤。").trim() ||
      "系统已自动继续执行后续步骤。";
    appendMessageProcessLog(row, {
      level: "info",
      text: message,
    });
    appendAssistantStatusNote(row, `> ↻ ${message}`);
    scrollToBottom();
    return;
  }
  if (eventType === "done") {
    let keepRequestOpenAfterDone = false;
    try {
      if (isInteractionSubmitAckDone(eventData)) {
        applyInteractionSubmitAckToSourceOperation(eventData);
        removeTransientInteractionAckRow(row, pending);
        return;
      }
      const doneState = normalizeDoneEventExecutionState(eventData);
      const doneContent = String(eventData?.content || "").trim();
      const hasFinalAnswer = Boolean(
        doneContent || String(row.content || "").trim(),
      );
      const planId = String(eventData?.plan_id || "").trim();
      const stepId = String(eventData?.step_id || "").trim();
      if (planId && stepId) {
        updatePlanOperationStep(row, planId, stepId, {
          status:
            doneState.phase === "completed" ? "completed" : doneState.phase,
          summary: doneState.summary,
        });
      }
      keepRequestOpenAfterDone =
        doneState.keepExecutionOpen ||
        (!hasFinalAnswer && hasOpenAgentRuntimeExecution(row));
      const preserveTerminalInteraction =
        shouldPreserveTerminalInteractionAfterDone(row, pending);
      if (!keepRequestOpenAfterDone && !preserveTerminalInteraction) {
        terminalPanelStatus.value = "idle";
      }
      const guardSummary = formatGuardSummary(eventData);
      if (guardSummary) {
        removeAssistantStatusNotes(row, isTransientExecutionStatusNote);
      }
      appendAgentRuntimePermissionOperations(row, eventData);
      const shouldPreserveUserWaitingOperationAfterDone =
        !keepRequestOpenAfterDone &&
        !preserveTerminalInteraction &&
        doneState.phase === "completed" &&
        hasNonTerminalUserWaitingOperation(row);
      if (
        !keepRequestOpenAfterDone &&
        !shouldPreserveUserWaitingOperationAfterDone
      ) {
        upsertMessageOperation(row, {
          operationId: `request:${requestId}`,
          kind: "request",
          title: "本轮执行",
          summary: doneState.summary,
          detail: String(eventData?.content || "").trim(),
          phase: doneState.phase,
          meta: {
            request_id: requestId,
            completed_reason: String(eventData?.completed_reason || "").trim(),
            task_id: String(eventData?.task_id || "").trim(),
            chat_session_id: String(eventData?.chat_session_id || "").trim(),
            authorization_url: String(
              eventData?.authorization_url || "",
            ).trim(),
            action_type: String(eventData?.action_type || "").trim(),
            plan_id: planId,
            step_id: stepId,
          },
        });
      }
      if (guardSummary) {
        appendAssistantStatusNote(row, `> ⚠️ ${guardSummary}`);
      }
      const doneLogSummary =
        keepRequestOpenAfterDone && !doneState.keepExecutionOpen
          ? "运行仍在继续，等待最终结果"
          : doneState.summary;
      if (!shouldPreserveUserWaitingOperationAfterDone) {
        appendMessageProcessLog(row, {
          level: doneState.level,
          text: doneLogSummary,
        });
      }
      row.images = mergeImageUrls(
        extractImages(row),
        collectArtifactImageUrls(eventData),
      );
      row.videos = mergeVideoUrls(
        extractVideos(row),
        collectArtifactVideoUrls(eventData),
      );
      const currentContent = String(row.content || "").trim();
      if (!currentContent) {
        row.content = doneContent || guardSummary;
      } else if (doneContent && currentContent !== doneContent) {
        if (
          isIntentOnlyReply(currentContent) ||
          /达到最大处理轮次|已停止生成/.test(doneContent)
        ) {
          row.content = doneContent;
        }
      }
      const taskTreePayload = eventData
        ? resolveTaskTreeEventPayload(eventData)
        : null;
      if (
        isPendingCurrentSession &&
        eventData &&
        (Object.prototype.hasOwnProperty.call(eventData, "task_tree") ||
          Object.prototype.hasOwnProperty.call(eventData, "history_task_tree"))
      ) {
        applyTaskTreePayload(taskTreePayload);
      }
      if (
        isPendingCurrentSession &&
        eventData?.work_session &&
        taskTreePayload &&
        !isTaskTreeArchivedOrDone(taskTreePayload)
      ) {
        applyWorkSessionPayload(eventData.work_session, {
          taskTree: taskTreePayload,
        });
      }
      row.taskTreeAudit = normalizeTaskTreeAuditPayload(
        eventData?.task_tree_audit,
      );
      if (row.taskTreeAudit) {
        appendAssistantStatusNote(row, `> ⚠️ ${row.taskTreeAudit.message}`);
      }
      if (pending?.mcpApprovalCancelled) {
        const handedOff = await handoffExternalAgentRequestToTerminal(
          row,
          pending,
        );
        if (handedOff) {
          pending.awaitingTerminalApproval = false;
          row.content =
            String(row.content || "").trim() ||
            "命令已接入项目终端；如出现可识别交互，会在终端输出下方显示表单。";
          resolvePendingRequest(requestId, pending, row.content || "");
          scrollToBottom();
          return;
        }
      }
      if (keepRequestOpenAfterDone) {
        row.processExpanded = true;
      } else if (preserveTerminalInteraction) {
        terminalPanelStatus.value = "running";
        activeTerminalMirrorAssistantIndex.value = Number(
          pending?.assistantIndex ?? activeTerminalMirrorAssistantIndex.value,
        );
        markTerminalOperationsWaitingForInput(row);
        row.displayMode = "terminal";
        row.processExpanded = true;
      } else {
        completeTerminalInputOperations(row, "本轮执行已结束");
        completeFinishedMessageOperations(row, doneState.summary);
        closeOpenAgentRuntimeOperationsForCompletedTurn(row, doneState.summary);
        if (
          Number(activeTerminalMirrorAssistantIndex.value) ===
          Number(pending?.assistantIndex ?? -1)
        ) {
          activeTerminalMirrorAssistantIndex.value = -1;
        }
        terminalMirrorConnected.value = false;
        hostTerminalSessionId.value = "";
        terminalStructuredInteraction.value = null;
      }
    } finally {
      if (!keepRequestOpenAfterDone) {
        resolvePendingRequest(requestId, pending, row.content || "");
      } else {
        syncChatLoadingWithCurrentSession();
      }
      scrollToBottom();
    }
    return;
  }
  if (eventType === "error") {
    terminalPanelStatus.value = "error";
    const message = String(eventData?.message || "未知错误");
    appendMessageProcessLog(row, {
      level: "error",
      text: `执行失败：${message}`,
    });
    upsertMessageOperation(row, {
      operationId: `request:${requestId}`,
      kind: "request",
      title: "本轮执行",
      summary: "执行失败",
      detail: message,
      phase: "failed",
    });
    appendTerminalPanelLine(`! ${message}`);
    row.content = `对话失败：${message}`;
    rejectPendingRequest(requestId, pending, new Error(message));
    scrollToBottom();
  }
}

function resolvePendingRequest(requestId, pending, content = "") {
  if (!pending || !requestId) return;
  const { chatSessionId } = cleanupRequest(requestId, pending);
  if (!hasPendingRequestForChatSession(chatSessionId)) {
    clearWorkingStatusStartForChatSession(chatSessionId);
  }
  persistRememberedChatSessionMessages(
    pending.projectId,
    chatSessionId,
  );
  syncChatLoadingWithCurrentSession();
  pending.resolve(String(content || "").trim());
}

function rejectPendingRequest(requestId, pending, error) {
  if (!pending || !requestId) return;
  const { chatSessionId } = rejectAndCleanupRequest(requestId, pending, error);
  if (!hasPendingRequestForChatSession(chatSessionId)) {
    clearWorkingStatusStartForChatSession(chatSessionId);
  }
  persistRememberedChatSessionMessages(
    pending.projectId,
    chatSessionId,
  );
  syncChatLoadingWithCurrentSession();
}

function rejectPendingRequests(reason) {
  const message = String(reason || "连接已断开").trim();
  const items = rejectAndCleanupAllRequests(reason);
  for (const { requestId, pending } of items) {
    const row = resolvePendingRequestRow(pending);
    if (row && !String(row.content || "").trim()) {
      row.content = `请求失败：${message}`;
    }
    if (!hasPendingRequestForChatSession(pending.chatSessionId)) {
      clearWorkingStatusStartForChatSession(pending.chatSessionId);
    }
    persistRememberedChatSessionMessages(
      pending.projectId,
      pending.chatSessionId,
    );
  }
  syncChatLoadingWithCurrentSession();
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

async function promptProjectWorkspacePath() {
  if (nativeDesktopBridgeAvailable.value) {
    workspacePathPicking.value = true;
    try {
      const pickedPath = await pickWorkspaceDirectory(
        workspacePathDraftNormalized.value ||
          workspacePathResolved.value ||
          projectWorkspaceResolved.value ||
          "",
        {
          title: `选择项目工作区目录 · ${String(currentProjectLabel.value || "").trim() || "AI 对话中心"}`,
          placeholder: "/Volumes/work_mac_1_5T/self/ai-employee",
        },
      );
      if (!pickedPath) {
        return;
      }
      workspacePathDraft.value = pickedPath;
      await saveProjectWorkspacePath(pickedPath);
      void refreshNativeExecutorStatus();
    } catch (err) {
      ElMessage.error(err?.detail || err?.message || "打开本机目录选择器失败");
    } finally {
      workspacePathPicking.value = false;
    }
    return;
  }
  if (!usingLocalConnector.value) {
    ElMessage.warning(
      "浏览器模式请先选择本地连接器，再填写连接器所在电脑上的工作区绝对路径",
    );
    return;
  }
  const connectorId = String(
    projectChatSettings.value.local_connector_id || "",
  ).trim();
  if (!connectorId) {
    ElMessage.warning("浏览器模式请先选择本地连接器");
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

async function promptProjectWorkspaceDirectory() {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    ElMessage.warning("请先选择项目");
    return;
  }
  projectWorkspacePicking.value = true;
  try {
    const pickedPath = await pickWorkspaceDirectory(
      projectWorkspaceDraftNormalized.value ||
        projectWorkspaceResolved.value ||
        "",
      {
        title: `选择项目工作区目录 · ${String(currentProjectLabel.value || "").trim() || "AI 对话中心"}`,
        placeholder: "/Volumes/苹果1_5T/self/ai-employee",
      },
    );
    if (!pickedPath) {
      return;
    }
    projectWorkspaceDraft.value = pickedPath;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "打开目录选择器失败");
  } finally {
    projectWorkspacePicking.value = false;
  }
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
        basePath:
          projectWorkspaceDraftNormalized.value || projectWorkspacePath.value,
      },
    );
    if (!pickedPath) {
      return;
    }
    aiEntryFileDraft.value = normalizeAiEntryFileForSave(
      pickedPath,
      projectWorkspaceDraftNormalized.value || projectWorkspacePath.value,
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "打开文件选择器失败");
  } finally {
    aiEntryFilePicking.value = false;
  }
}

async function saveProjectWorkspaceDirectory(workspacePathOverride = null) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    ElMessage.warning("请先选择项目");
    return;
  }
  projectWorkspaceSaving.value = true;
  try {
    const normalizedOverride =
      typeof Event !== "undefined" && workspacePathOverride instanceof Event
        ? null
        : workspacePathOverride;
    const workspacePath = String(
      normalizedOverride ?? projectWorkspaceDraft.value ?? "",
    ).trim();
    const data = await api.patch(`/projects/${encodeURIComponent(projectId)}`, {
      workspace_path: workspacePath,
    });
    const persisted = String(
      data?.project?.workspace_path || workspacePath,
    ).trim();
    projectWorkspacePath.value = persisted;
    projectWorkspaceDraft.value = persisted;
    projects.value = (projects.value || []).map((item) =>
      String(item?.id || "").trim() === projectId
        ? { ...item, workspace_path: persisted }
        : item,
    );
    if (!usingLocalConnector.value) {
      externalAgentInfo.value = normalizeExternalAgentInfo({
        ...externalAgentInfo.value,
        workspace_path: persisted,
      });
    }
    ElMessage.success(
      persisted ? "项目工作区路径已保存" : "已清空项目工作区路径",
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存项目工作区路径失败");
  } finally {
    projectWorkspaceSaving.value = false;
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
      projectWorkspaceDraftNormalized.value || projectWorkspacePath.value,
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

/** 保存项目工作区路径配置到服务端，同步更新本地运行时上下文和执行工作区路径 */
async function saveProjectWorkspacePath(workspacePathOverride = null) {
  const projectId = String(selectedProjectId.value || "").trim();
  if (!projectId) {
    ElMessage.warning("请先选择项目");
    return;
  }
  if (
    projectSettingsHydrating.value ||
    projectSettingsHydratedProjectId.value !== projectId
  ) {
    ElMessage.warning("项目对话设置仍在加载，请稍后再保存");
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
    if (!usingLocalConnector.value && !nativeDesktopBridgeAvailable.value) {
      ElMessage.warning("浏览器模式请先选择本地连接器");
      return;
    }
    const connectorId = String(
      projectChatSettings.value.local_connector_id || "",
    ).trim();
    workspacePathDraft.value = workspacePath;
    writePreferredLocalWorkspacePath(projectId, connectorId, workspacePath);
    projectChatSettings.value = applyLocalConnectorRuntimeSettings({
      ...projectChatSettings.value,
      connector_workspace_path: workspacePath,
    });
    clearAutoSaveTimer();
    autoSaveState.value = "saving";
    const payload = buildProjectChatSettingsPayload();
    const data = await saveProjectChatSettingsRequest(projectId, payload);
    projectChatSettings.value = applyLocalConnectorRuntimeSettings(
      data?.settings || payload,
    );
    await fetchProvidersByProject(projectId);
    markAutoSaveSynced();
    autoSaveState.value = "saved";
    autoSaveUpdatedAt.value = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    externalAgentWarmupKey.value = "";
    externalAgentInfo.value = normalizeExternalAgentInfo({
      ...externalAgentInfo.value,
      ready: false,
      session_id: "",
      thread_id: "",
      workspace_path: workspacePath,
    });
    if (nativeDesktopBridgeAvailable.value) {
      void refreshNativeExecutorStatus();
    }
    ElMessage.success(
      workspacePath
        ? nativeDesktopBridgeAvailable.value
          ? "本机工作区路径已保存"
          : "本地连接器工作区路径已保存"
        : nativeDesktopBridgeAvailable.value
          ? "已清空本机工作区路径"
          : "已清空本地连接器工作区路径",
    );
  } catch (err) {
    autoSaveState.value = "error";
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
    if (!nativeDesktopBridgeAvailable.value) {
      ElMessage.warning("浏览器模式请先选择本地连接器");
      return;
    }
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
    if (nativeDesktopBridgeAvailable.value) {
      await refreshNativeExecutorStatus();
      const workspace = nativeExecutorStatus.value?.workspace;
      if (
        workspace?.configured &&
        (!workspace.exists || !workspace.isDirectory)
      ) {
        throw new Error(nativeWorkspaceStatusLabel.value || "工作区不可访问");
      }
      ElMessage.success("工作区可用，桌面端已完成本机路径检查");
      return;
    }
    await fetchProvidersByProject(projectId);
    if (!externalAgentInfo.value.workspace_access?.read_ok) {
      throw new Error(
        String(
          externalAgentInfo.value.workspace_access?.reason || "工作区不可访问",
        ),
      );
    }
    ElMessage.success("工作区可用，本地连接器文件工具已可在该目录使用");
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
  if (nativeDesktopBridgeAvailable.value) {
    throw new Error(
      "桌面端原生桥已接入，但交互式本地 Runner / PTY 尚未完成；当前可先检测环境和 Runner 自检。",
    );
  }
  if (!usingLocalConnector.value) {
    throw new Error("浏览器模式请先选择本地连接器");
  }
  const preparedWorkspacePath = String(
    workspacePathDraftNormalized.value ||
      projectChatSettings.value.connector_workspace_path ||
      workspacePathResolved.value ||
      "",
  ).trim();
  if (!preparedWorkspacePath) {
    throw new Error("浏览器模式请先配置本地连接器工作区");
  }

  const warmupKey = buildExternalAgentWarmupKey({
    projectId,
    agentType: projectChatSettings.value.external_agent_type || "codex_cli",
    localConnectorId: projectChatSettings.value.local_connector_id || "",
    workspacePath: workspacePathDraftNormalized.value || workspacePathResolved.value,
    sandboxMode:
      projectChatSettings.value.external_agent_sandbox_mode ||
      "workspace-write",
    skillResourceDirectory: skillResourceDirectoryResolved.value || "",
    systemPrompt: systemPrompt.value || "",
    employeeIds: selectedEmployeeIds.value || [],
  });
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
      chat_session_id: String(currentChatSessionId.value || "").trim(),
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
      connector_workspace_path: preparedWorkspacePath,
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

async function sendProjectChatRequest({
  projectId,
  activeChatSessionId,
  userMessageId = "",
  assistantMessage,
  assistantIndex,
  finalUserPrompt,
  activeSessionSourceContext,
  attachmentNames = [],
  base64Images = [],
  historyRows = [],
  effectiveAutoUseTools = true,
  effectiveToolPriority = [],
  enabledProjectToolNames = selectedProjectToolNames.value,
  assistAction = null,
  assistToolNames = [],
  onAfterDone = null,
  requestKind = "user_message",
  replaceAssistantContentOnDone = false,
}) {
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const client = await ensureWsClient(projectId);
  const requestChatMode = isExternalAgentMode.value
    ? "external_agent"
    : "system";
  let pendingState = null;
  const donePromise = new Promise((resolve, reject) => {
    pendingState = {
      resolve,
      reject,
      requestId,
      projectId,
      chatSessionId: activeChatSessionId,
      chatMode: requestChatMode,
      assistantMessageId: String(assistantMessage?.id || "").trim(),
      assistantIndex,
      userPrompt: finalUserPrompt,
      mcpApprovalCancelled: false,
      awaitingTerminalApproval: false,
      handoffTriggered: false,
      projectHostTerminalHandoffTriggered: false,
      lastToolName: "",
      cancelled: false,
    };
    pendingRequests.set(requestId, pendingState);
    trackPendingRequest(requestId);
  });
  const employeeIds = normalizeStringList(selectedEmployeeIds.value || []);
  const requestPayload = {
    request_id: requestId,
    message_id: String(userMessageId || "").trim(),
    assistant_message_id: String(assistantMessage?.id || "").trim(),
    chat_session_id: activeChatSessionId,
    request_kind:
      String(requestKind || "user_message").trim() || "user_message",
    chat_mode: requestChatMode,
    chat_surface: chatSurface.value,
    source_context: activeSessionSourceContext,
    external_agent_type: String(
      projectChatSettings.value.external_agent_type ||
        CHAT_SETTINGS_DEFAULTS.external_agent_type,
    ).trim(),
    local_connector_id: String(
      projectChatSettings.value.local_connector_id || "",
    ).trim(),
    connector_workspace_path: String(
      workspacePathDraftNormalized.value ||
        projectChatSettings.value.connector_workspace_path ||
        workspacePathResolved.value ||
        "",
    ).trim(),
    connector_sandbox_mode: String(
      projectChatSettings.value.connector_sandbox_mode || "workspace-write",
    ).trim(),
    connector_sandbox_mode_explicit: true,
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
    max_tool_calls_per_round: resolveNumericChatSetting(
      projectChatSettings.value.max_tool_calls_per_round,
      CHAT_SETTINGS_DEFAULTS.max_tool_calls_per_round,
      { min: 1, max: 30 },
    ),
    max_loop_rounds: resolveNumericChatSetting(
      projectChatSettings.value.max_loop_rounds,
      CHAT_SETTINGS_DEFAULTS.max_loop_rounds,
      { min: 1, max: 60 },
    ),
    max_tool_rounds: resolveNumericChatSetting(
      projectChatSettings.value.max_tool_rounds,
      CHAT_SETTINGS_DEFAULTS.max_tool_rounds,
      { min: 1, max: 30 },
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
    history_limit: resolveNumericChatSetting(
      projectChatSettings.value.history_limit,
      CHAT_SETTINGS_DEFAULTS.history_limit,
      { min: 1, max: 50 },
    ),
    tool_timeout_sec: resolveNumericChatSetting(
      projectChatSettings.value.tool_timeout_sec,
      CHAT_SETTINGS_DEFAULTS.tool_timeout_sec,
      { min: 0, max: 600 },
    ),
    tool_retry_count: resolveNumericChatSetting(
      projectChatSettings.value.tool_retry_count,
      CHAT_SETTINGS_DEFAULTS.tool_retry_count,
      { min: 0, max: 5 },
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
      ...enabledProjectToolNames,
      ...(assistAction?.id === "employee_create" ? assistToolNames : []),
    ],
    200,
  );
  client.send(requestPayload);
  await donePromise;
  if (pendingState?.cancelled) {
    return {
      requestId,
      cancelled: true,
    };
  }
  if (replaceAssistantContentOnDone) {
    const row = assistantMessage;
    const finalContent = String(row?.content || "").trim();
    const followupPlanId = String(assistantMessage?.id || "").trim();
    if (row && followupPlanId) {
      upsertMessageOperation(row, {
        operationId: `plan:followup:${followupPlanId}`,
        kind: "plan",
        title: "补充需求",
        summary: finalContent ? "已按补充需求更新结果" : "补充需求处理完成",
        detail: "",
        phase: "completed",
        actionType: "none",
        meta: {
          assistant_message_id: followupPlanId,
        },
      });
    }
  }
  if (
    !String(assistantMessage?.content || "").trim() &&
    !messageOperations(assistantMessage).length
  ) {
    assistantMessage.content = "模型未返回内容。";
  } else if (!String(assistantMessage?.content || "").trim()) {
    assistantMessage.content = "模型未返回最终回答，请检查本轮执行过程。";
  }
  if (typeof onAfterDone === "function") {
    await onAfterDone();
  }
  return {
    requestId,
    cancelled: false,
  };
}

function resolvePendingRequestFast(requestId, pending, content = "") {
  if (!pending || !requestId) return;
  const { chatSessionId } = cleanupRequest(requestId, pending);
  if (!hasPendingRequestForChatSession(chatSessionId)) {
    clearWorkingStatusStartForChatSession(chatSessionId);
  }
  syncChatLoadingWithCurrentSession();
  persistRememberedChatSessionMessages(
    pending.projectId,
    chatSessionId,
  );
  pending.resolve(String(content || "").trim());
}

function cancelPendingChatRequestFast(requestId, pending) {
  if (!pending || !requestId) return false;
  pending.cancelled = true;
  const row = resolvePendingRequestRow(pending);
  const message = "已停止生成。";
  queuedFollowupMessages.value = [];
  activeFollowupAssistantMessageId = "";
  if (row) {
    row.displayMode = "";
    row.content = String(row.content || "").trim() || message;
    row.time = nowText();
    completeFinishedMessageOperations(row, message);
    closeOpenAgentRuntimeOperationsForCompletedTurn(row, message);
    upsertMessageOperation(row, {
      operationId: `request:${requestId}`,
      kind: "request",
      title: "本轮执行",
      summary: message,
      detail: "",
      phase: "completed",
      actionType: "none",
      meta: {
        request_id: requestId,
        cancelled: true,
      },
    });
    appendMessageProcessLog(row, {
      level: "info",
      text: message,
    });
  }
  clearActiveExecutionTransportState(pending?.assistantIndex ?? -1);
  resolvePendingRequestFast(requestId, pending, row?.content || message);
  scrollToBottom();
  return true;
}

function sendCancelRequestNow(requestId) {
  const normalizedRequestId = String(requestId || "").trim();
  if (!normalizedRequestId) return false;
  const activeClient = wsClient.value;
  if (!activeClient || !activeClient.isOpen()) return false;
  try {
    activeClient.send({ type: "cancel", request_id: normalizedRequestId });
    return true;
  } catch (err) {
    console.warn("send cancel request failed", err);
    return false;
  }
}

function sendCancelRequestInBackground(requestId) {
  const normalizedRequestId = String(requestId || "").trim();
  if (!normalizedRequestId) return;
  window.setTimeout(() => {
    sendCancelRequestNow(normalizedRequestId);
  }, 0);
}

function closeIdleChatWsAfterFastCancel() {
  if (!wsClient.value || pendingRequests.size > 0) return;
  wsClient.value.close(1000, "generation cancelled");
  terminalMirrorConnected.value = false;
  wsClient.value = null;
  wsConnected.value = false;
  wsProjectId.value = "";
}

function stopGeneration() {
  const currentRequestId = getActiveRequestId();
  if (currentRequestId) {
    const pending = pendingRequests.get(currentRequestId);
    if (cancelPendingChatRequestFast(currentRequestId, pending)) {
      sendCancelRequestNow(currentRequestId);
      closeIdleChatWsAfterFastCancel();
      ElMessage.info("已停止生成");
      return;
    }
    sendCancelRequestInBackground(currentRequestId);
    ElMessage.info("已发送停止指令");
    return;
  }
  if (currentChatSessionNativeExternalAgentRunning.value) {
    if (cancelActiveNativeExternalAgentSession()) {
      return;
    }
  }
  const now = Date.now();
  if (now - lastNoActiveGenerationWarningAt < 1200) return;
  lastNoActiveGenerationWarningAt = now;
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
    taskTreeAudit: null,
    processLog: [],
    statusNotes: [],
    operations: [],
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
  void upsertProjectChatRequirementRecord({
    chatSessionId: activeChatSessionId,
    status: "in_progress",
    rootGoal: displayUserMessageContent,
    messageId: userMessage.id,
    assistantMessageId: assistantMessage.id,
    source: isExternalAgentMode.value
      ? "external_agent_connector"
      : "project_chat",
    sourceContext: {
      chat_mode: isExternalAgentMode.value ? "external_agent" : "system",
      surface: chatSurface.value,
      slash_command: slashCommand?.entry?.kind || "",
      attachment_names: attachmentNames,
      employee_ids: normalizeStringList(selectedEmployeeIds.value || [], 20),
    },
  });

  const assistantIndex = messages.value.length - 1;
  chatLoading.value = true;
  resetDraft();
  scrollToBottom();

  try {
    await ensureEmployeeDraftCatalog();
    const response = await generateEmployeeDraft({
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
    taskTreeAudit: null,
    processLog: [],
    statusNotes: [],
    operations: [],
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

function explainBlockedSend() {
  if (hasSelectedProject.value && !isChatSettingsDisplayReady.value) {
    ElMessage.warning("项目配置仍在加载，请稍后再发送");
    return;
  }
  if (
    isExternalAgentMode.value &&
    isNativeExternalAgentRunningForChatSession(currentChatSessionId.value)
  ) {
    ElMessage.warning("外部 Agent 仍在处理或状态恢复中，请先暂停或稍后再发送");
    return;
  }
  if (!String(selectedProjectId.value || "").trim()) {
    ElMessage.warning("请先选择项目");
    return;
  }
  if (!String(draftText.value || "").trim() && !uploadFiles.value.length) {
    ElMessage.warning("请输入消息内容");
  }
}

async function doSend(options = {}) {
  if (!canSend.value) {
    explainBlockedSend();
    return;
  }

  if (isTerminalInteractionMode.value) {
    if (uploadFiles.value.length) {
      ElMessage.warning("项目终端模式下不支持通过主输入框发送附件");
      return;
    }
    await sendTerminalMirrorInput();
    scrollToBottom();
    return;
  }

  if (chatLoading.value) {
    if (isAwaitingUserInteraction.value) {
      const text = String(draftText.value || "").trim();
      if (await submitPendingInteractionAckIfNeeded(text)) {
        return;
      }
      if (!canSupersedePendingInteraction(activePendingInteraction.value)) {
        ElMessage.warning(
          "这一步需要你在消息卡片确认；确认后系统会自动继续执行",
        );
        return;
      }
      releasePendingInteractionForFollowup(text);
    }
    if (enqueueFollowupMessage()) {
      ElMessage.info("已加入追加需求队列，当前回合结束后会重新规划");
    }
    return;
  }

  if (isAwaitingUserInteraction.value) {
    const text = String(draftText.value || "").trim();
    if (await submitPendingInteractionAckIfNeeded(text)) {
      return;
    }
    if (!canSupersedePendingInteraction(activePendingInteraction.value)) {
      ElMessage.warning("这一步需要你在消息卡片确认；确认后系统会自动继续执行");
      return;
    }
    releasePendingInteractionForFollowup(text);
  }

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
  nativeDesktopBridgeAvailable.value = hasNativeDesktopBridge();
  if (isExternalAgentMode.value) {
    if (!nativeDesktopBridgeAvailable.value) {
      try {
        await prepareExternalAgentSession({ force: false, silent: false });
      } catch {
        return;
      }
    }
  }
  const files = uploadFiles.value.map((item) => item.raw).filter(Boolean);
  const imageFiles = files.filter((file) => isImageFile(file));

  const activeSessionSourceContext = normalizeChatSourceContext(
    currentChatSession.value || {},
  );
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

  const slashCommand = resolveSlashCommand(text);
  const slashAssistAction =
    slashCommand?.entry?.kind === "assist"
      ? composerAssistActions.value.find(
          (item) => item.id === slashCommand.entry.assistActionId,
        ) || null
      : null;
  const effectiveAssistAction =
    slashAssistAction || activeComposerAssistMeta.value;
  let userPrompt = "";
  if (slashCommand?.entry?.kind === "stats_report") {
    try {
      const projectStatsReport = await fetchProjectStatsAiReport(
        selectedProjectId.value,
      );
      userPrompt = buildProjectStatsCommandPrompt({
        projectLabel: currentProjectLabel.value,
        commandPrompt: slashCommand.prompt,
        reportDays: projectStatsReport.days,
        reportSummary: projectStatsReport.summary,
        reportConclusion: projectStatsReport.conclusion,
        reportMarkdown: projectStatsReport.markdown,
        docsText,
        attachmentNames,
      });
    } catch (err) {
      ElMessage.error(err?.message || "项目统计 AI 报表加载失败");
      return;
    }
  } else if (slashCommand?.entry?.kind === "host_run") {
    if (!slashCommand.prompt) {
      ElMessage.warning("请在 /run 后输入要执行的命令");
      return;
    }
    userPrompt = `${slashCommand.entry.command} ${slashCommand.prompt}`;
  } else if (slashCommand?.entry?.kind === "lark_cli") {
    if (!slashCommand.prompt) {
      ElMessage.warning(
        "请在 /lark-cli 后输入目标，例如 auth status 或 给屈行行发 test",
      );
      return;
    }
    if (!String(skillResourceDirectoryResolved.value || "").trim()) {
      setSkillResourceDirectory(resolveLarkCliSkillDirectory(), {
        silent: true,
      });
    }
    userPrompt = `${slashCommand.entry.command} ${slashCommand.prompt}`;
  } else if (slashCommand?.entry?.kind === "form_json") {
    if (!slashCommand.prompt) {
      ElMessage.warning("请在 /form-json 后输入字段或表单需求");
      return;
    }
    userPrompt = buildFormJsonCommandPrompt(slashCommand.prompt);
  } else if (slashCommand?.entry?.kind === "assist") {
    userPrompt =
      slashCommand.prompt || String(slashAssistAction?.seedText || "").trim();
    if (!userPrompt) {
      ElMessage.warning("请在命令后补充内容");
      return;
    }
  } else {
    userPrompt =
      text ||
      (attachmentNames.length
        ? `我上传了附件：${attachmentNames.join("、")}。请先给我处理建议。`
        : "");
    if (docsText) {
      userPrompt += `${docsText}\n\n请先给简要结论：最多 5 条，每条不超过 40 字。`;
    }
  }
  const assistAction = effectiveAssistAction;
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
  const slashCommandRequiresTools = ["host_run", "lark_cli"].includes(
    String(slashCommand?.entry?.kind || "").trim(),
  );
  const shouldUseAgenticOperation =
    !slashCommand &&
    !shouldInjectAssistPrompt &&
    !singleRoundAnswerOnly.value &&
    isActionableOperationPrompt(userPrompt);
  if (
    shouldUseAgenticOperation &&
    isLarkOperationPrompt(userPrompt) &&
    !String(skillResourceDirectoryResolved.value || "").trim()
  ) {
    setSkillResourceDirectory(resolveLarkCliSkillDirectory(), {
      silent: true,
    });
  }
  const operationToolNames = shouldUseAgenticOperation
    ? AGENTIC_OPERATION_TOOL_NAMES
    : [];
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
  const executionUserPrompt = shouldUseAgenticOperation
    ? appendAgenticOperationInstruction(effectiveUserPrompt, userPrompt)
    : effectiveUserPrompt;
  const finalUserPrompt = appendModelGenerationInstruction(executionUserPrompt);
  const effectiveToolPriority = mergeToolPriority(
    projectChatSettings.value.tool_priority || [],
    [...operationToolNames, ...assistToolNames],
  );
  const effectiveAutoUseTools =
    slashCommandRequiresTools ||
    shouldUseAgenticOperation ||
    (assistAction && assistToolNames.length)
      ? true
      : singleRoundAnswerOnly.value
        ? false
        : projectChatToolsExplicitlyEnabled();
  const effectiveSelectedProjectToolNames = effectiveAutoUseTools
    ? normalizeStringList([
        ...selectedProjectToolNames.value,
        ...(slashCommandRequiresTools ? AGENTIC_OPERATION_TOOL_NAMES : []),
        ...operationToolNames,
      ])
    : [];
  const displayUserMessageContent = slashCommand
    ? slashCommand.prompt
      ? `${slashCommand.entry.command} ${slashCommand.prompt}`
      : `${slashCommand.entry.command} ${slashCommand.entry.label}`
    : text || "（发送了附件）";
  if (isExternalAgentMode.value && nativeDesktopBridgeAvailable.value) {
    await startNativeExternalAgentSession(activeChatSessionId, {
      displayPrompt: displayUserMessageContent,
      executionPrompt: finalUserPrompt,
      attachmentNames,
      slashCommandKind: slashCommand?.entry?.kind || "",
    });
    return;
  }
  const userMessage = {
    id: createLocalMessageId(),
    role: "user",
    content: displayUserMessageContent,
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
    taskTreeAudit: null,
    statusNotes: [],
    operations: [],
    time: nowText(),
  };
  messages.value.push(userMessage);
  messages.value.push(assistantMessage);

  const assistantIndex = messages.value.length - 1;
  chatLoading.value = true;
  resetDraft();
  scrollToBottom();

  let requestCancelled = false;
  try {
    const sendResult = await sendProjectChatRequest({
      projectId: selectedProjectId.value,
      activeChatSessionId,
      userMessageId: userMessage.id,
      assistantMessage,
      assistantIndex,
      finalUserPrompt,
      activeSessionSourceContext,
      attachmentNames,
      base64Images,
      historyRows,
      effectiveAutoUseTools,
      effectiveToolPriority,
      enabledProjectToolNames: effectiveSelectedProjectToolNames,
      assistAction,
      assistToolNames,
      onAfterDone:
        assistAction?.id === "employee_create"
          ? async () => {
              await autoCreateEmployeeFromDraftMessage(
                messages.value[assistantIndex],
                {
                  resetAssist: true,
                },
              );
            }
          : null,
    });
    requestCancelled = Boolean(sendResult?.cancelled);
    if (requestCancelled) return;
    const finalAssistantContent = String(assistantMessage.content || "").trim();
    await upsertProjectChatRequirementRecord({
      chatSessionId: activeChatSessionId,
      status: "done",
      rootGoal: displayUserMessageContent,
      messageId: userMessage.id,
      assistantMessageId: assistantMessage.id,
      resultSummary: finalAssistantContent,
      verificationResult: "AI 对话已返回最终回答并写入当前聊天。",
      source: isExternalAgentMode.value
        ? "external_agent_connector"
        : "project_chat",
      sourceContext: {
        chat_mode: isExternalAgentMode.value ? "external_agent" : "system",
        surface: chatSurface.value,
        slash_command: slashCommand?.entry?.kind || "",
        attachment_names: attachmentNames,
        employee_ids: normalizeStringList(selectedEmployeeIds.value || [], 20),
      },
    });
  } catch (err) {
    assistantMessage.content = `请求失败：${err?.message || "未知错误"}`;
    void upsertProjectChatRequirementRecord({
      chatSessionId: activeChatSessionId,
      status: "blocked",
      rootGoal: displayUserMessageContent,
      messageId: userMessage.id,
      assistantMessageId: assistantMessage.id,
      resultSummary: assistantMessage.content,
      verificationResult: err?.message || "AI 对话请求失败。",
      source: isExternalAgentMode.value
        ? "external_agent_connector"
        : "project_chat",
      sourceContext: {
        chat_mode: isExternalAgentMode.value ? "external_agent" : "system",
        surface: chatSurface.value,
        error: err?.detail || err?.message || "",
      },
    });
    ElMessage.error(err?.message || "对话失败");
  } finally {
    syncChatLoadingWithCurrentSession();
    singleRoundAnswerOnly.value = false;
    if (selectedProjectId.value && !requestCancelled) {
      const sessionToKeep =
        String(currentChatSessionId.value || "").trim() || activeChatSessionId;
      await fetchChatSessions(selectedProjectId.value, sessionToKeep, {
        useRemembered: false,
      });
      syncChatLoadingWithCurrentSession();
    }
    if (
      !requestCancelled &&
      pendingRequests.size === 0 &&
      queuedFollowupMessages.value.length
    ) {
      void drainQueuedFollowupMessages();
    }
    scrollToBottom();
  }
}

watch(
  () =>
    String(projectChatSettings.value.external_agent_type || "codex_cli").trim(),
  () => {
    const fallbackType = String(
      externalAgentOptions.value[0]?.agent_type || "codex_cli",
    ).trim();
    const requestedType = String(
      projectChatSettings.value.external_agent_type || fallbackType,
    ).trim();
    const option =
      (externalAgentOptions.value || []).find(
        (item) => item.agent_type === requestedType,
      ) || {};
    const nextType = String(option.agent_type || fallbackType).trim();
    if (
      nextType &&
      nextType !==
        String(projectChatSettings.value.external_agent_type || "").trim()
    ) {
      projectChatSettings.value.external_agent_type = nextType;
    }
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
    scheduleExternalAgentStatusRefresh({ force: true });
  },
);

watch(
  () => [
    Boolean(nativeExternalAgentSessionDetailVisible.value),
    String(nativeExternalAgentTerminalText.value || ""),
  ],
  async () => {
    if (!nativeExternalAgentSessionDetailVisible.value) return;
    await nextTick();
    const el = nativeExternalAgentTerminalRef.value;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  },
);

watch(
  () => [
    String(selectedProjectId.value || "").trim(),
    String(projectChatSettings.value.chat_mode || "").trim(),
    String(projectChatSettings.value.external_agent_type || "codex_cli").trim(),
    String(projectChatSettings.value.connector_workspace_path || "").trim(),
    String(workspacePathDraftNormalized.value || "").trim(),
    String(projectWorkspaceResolved.value || "").trim(),
    nativeDesktopBridgeAvailable.value ? "native" : "web",
    isLocalRunnerSurface.value ? "local-runner" : "main-chat",
  ],
  () => {
    if (projectSettingsHydrating.value) return;
    scheduleExternalAgentStatusRefresh();
    if (isLocalRunnerSurface.value) {
      void refreshNativeExternalAgentSessionRecords({ silent: true });
    }
  },
  { immediate: true },
);

watch(selectedProviderId, () => {
  handleProviderChange();
});

watch(
  () => [
    String(groupChatDraft.value.platform || "").trim(),
    String(selectedProjectId.value || "").trim(),
    groupBotConnectorOptions.value.map((item) => item.value).join("|"),
  ],
  () => {
    const currentConnectorId = String(
      groupChatDraft.value.connector_id || "",
    ).trim();
    const options = groupBotConnectorOptions.value;
    if (
      currentConnectorId &&
      options.some((item) => item.value === currentConnectorId)
    ) {
      return;
    }
    groupChatDraft.value.connector_id = options[0]?.value || "";
  },
  { immediate: true },
);

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
    isLocalRunnerSurface.value ? "local-runner" : "main-chat",
    String(selectedProjectId.value || "").trim(),
    String(projectWorkspaceResolved.value || "").trim(),
  ],
  ([surface]) => {
    if (surface !== "local-runner") return;
    void refreshNativeRunnerPermissionRecords();
    if (!canUseWorkspaceFiles.value) {
      resetWorkspaceFilePanel();
      return;
    }
    void openWorkspaceDirectory(workspaceFileTreePath.value);
  },
  { immediate: true },
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

watch(
  messages,
  () => {
    schedulePersistChatRuntime();
  },
  { deep: true },
);

watch(
  showWorkingStatusBar,
  (visible) => {
    if (visible) {
      startWorkingStatusTimer();
    } else {
      stopWorkingStatusTimer();
    }
  },
  { immediate: true },
);

watch(
  () => [
    String(selectedProjectId.value || "").trim(),
    String(currentChatSessionId.value || "").trim(),
    String(terminalPanelStatus.value || "").trim(),
    String(hostTerminalSessionId.value || "").trim(),
    String(hostTerminalWorkspacePath.value || "").trim(),
    Boolean(terminalPanelExpanded.value),
    Number(activeTerminalMirrorAssistantIndex.value || -1),
    Array.isArray(terminalPanelLines.value)
      ? terminalPanelLines.value.join("\n")
      : "",
  ],
  () => {
    schedulePersistChatRuntime();
  },
);

watch(
  () => [
    String(selectedProjectId.value || "").trim(),
    String(currentChatSessionId.value || "").trim(),
  ],
  () => {
    terminalRestoreAttemptKey = "";
  },
);

function clearSelectedProjectState() {
  clearChatSessionMemory(selectedProjectId.value);
  clearTaskTreeSessionMemory(selectedProjectId.value);
  clearWorkSessionMemory(selectedProjectId.value);
  selectedProjectId.value = "";
  clearSelectedProjectId();
  currentChatSessionId.value = "";
  currentWorkSessionId.value = "";
  clearOngoingTaskRestoreNotice();
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

async function loadSelectedProjectConversation(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) return;
  const {
    chatSessionId: routeChatSessionId,
    createNewSession: routeCreateNewSession,
  } = routeChatTarget();
  const shouldCreateWindowSession =
    routeCreateNewSession && !routeChatSessionId;
  const loadingKey = [
    normalizedProjectId,
    String(routeChatSessionId || "").trim(),
    shouldCreateWindowSession ? "new" : "existing",
  ].join("|");
  if (selectedProjectConversationLoadingKey === loadingKey) return;
  selectedProjectConversationLoadingKey = loadingKey;
  agentStatusExpanded.value = false;
  try {
    await fetchProvidersByProject(normalizedProjectId);
    if (normalizedProjectId !== String(selectedProjectId.value || "").trim())
      return;
    const restoredTask =
      routeChatSessionId || shouldCreateWindowSession
        ? null
        : await restoreOngoingTaskFromServer(normalizedProjectId, {
            silent: true,
          });
    if (normalizedProjectId !== String(selectedProjectId.value || "").trim())
      return;
    let chatSessionId = await fetchChatSessions(
      normalizedProjectId,
      routeChatSessionId || "",
      {
        allowFallback: !shouldCreateWindowSession,
        excludeSessionIds: restoredTask?.chatSessionId
          ? [restoredTask.chatSessionId]
          : [],
        useRemembered: !shouldCreateWindowSession,
      },
    );
    if (restoredTask?.chatSessionId) {
      const restoredChatSessionId = String(
        restoredTask.chatSessionId || "",
      ).trim();
      if (
        restoredChatSessionId &&
        !chatSessions.value.some((item) => item.id === restoredChatSessionId)
      ) {
        chatSessions.value = [
          {
            id: restoredChatSessionId,
            title:
              String(
                restoredTask.taskTree?.title ||
                  restoredTask.taskTree?.root_goal ||
                  "进行中的任务",
              ).trim() || "进行中的任务",
            preview: String(
              restoredTask.taskTree?.current_node?.title ||
                restoredTask.taskTree?.root_goal ||
                "",
            ).trim(),
            message_count: 0,
            created_at: String(restoredTask.taskTree?.created_at || "").trim(),
            updated_at: String(restoredTask.taskTree?.updated_at || "").trim(),
            last_message_at: String(
              restoredTask.taskTree?.updated_at ||
                restoredTask.taskTree?.created_at ||
                "",
            ).trim(),
          },
          ...chatSessions.value.filter(
            (item) => item.id !== restoredChatSessionId,
          ),
        ];
      }
    }
    if (normalizedProjectId !== String(selectedProjectId.value || "").trim())
      return;
    if (shouldCreateWindowSession) {
      const created = await createChatSession({
        switchTo: true,
        sourceContext: {
          project_id: normalizedProjectId,
          opened_from: "project-detail-window",
          window_scoped: true,
        },
      });
      chatSessionId = String(created?.id || "").trim();
      if (chatSessionId) {
        replaceRouteWithChatSession(chatSessionId);
      }
    } else if (!chatSessionId) {
      const existingSessionId = String(chatSessions.value[0]?.id || "").trim();
      if (existingSessionId) {
        chatSessionId = existingSessionId;
        currentChatSessionId.value = existingSessionId;
        rememberChatSession(normalizedProjectId, existingSessionId);
      } else {
        const created = await createChatSession({ switchTo: true });
        chatSessionId = String(created?.id || "").trim();
      }
    }
    if (
      !chatSessionId ||
      normalizedProjectId !== String(selectedProjectId.value || "").trim()
    ) {
      return;
    }
    await fetchChatHistory(normalizedProjectId, chatSessionId);
    void ensureWsClient(normalizedProjectId).catch(() => {});
    if (restoredTask?.chatSessionId) {
      setOngoingTaskRestoreNotice(
        restoredTask.taskTree,
        restoredTask.workSession,
      );
    }
    await applyRouteMessageFocus();
  } finally {
    if (selectedProjectConversationLoadingKey === loadingKey) {
      selectedProjectConversationLoadingKey = "";
    }
  }
}

watch(selectedProjectId, async (value) => {
  const projectId = String(value || "").trim();
  projectSettingsHydratedProjectId.value = "";
  if (projectId) {
    writeSelectedProjectId(projectId);
  } else {
    clearSelectedProjectId();
  }
  clearOngoingTaskRestoreNotice();
  currentWorkSessionId.value = "";
  if (!projectId) {
    rejectPendingRequests("已切换项目，当前请求取消");
    disconnectWs("switch project");
    singleRoundAnswerOnly.value = false;
    resetWorkspaceFilePanel();
    await fetchProvidersByProject("");
    return;
  }
  rejectPendingRequests("已切换项目，当前请求取消");
  disconnectWs("switch project");
  singleRoundAnswerOnly.value = false;
  currentChatSessionId.value = "";
  messages.value = [];
  chatHistoryLoadedCount.value = 0;
  applyTaskTreePayload(null);
  resetTerminalPanel();
  resetWorkspaceFilePanel();
  try {
    await loadSelectedProjectConversation(projectId);
  } catch (err) {
    const isAccessError =
      err?.status === 403 ||
      err?.status === 404 ||
      String(err?.detail || "").includes("Project access denied");
    if (isAccessError) {
      await fetchProjects();
      const fallbackProjectId = resolveAvailableProjectId();
      if (fallbackProjectId && fallbackProjectId !== projectId) {
        selectedProjectId.value = fallbackProjectId;
        writeSelectedProjectId(fallbackProjectId);
      } else if (!fallbackProjectId) {
        clearSelectedProjectState();
      }
      await fetchProvidersByProject("");
      messages.value = [];
    }
    ElMessage.error(err?.detail || err?.message || "切换项目失败");
  }
});

watch(
  () => String(currentChatSessionId.value || "").trim(),
  (sessionId) => {
    syncNativeExternalAgentSessionPanel();
    syncChatLoadingWithCurrentSession();
    if (showWorkingStatusBar.value) {
      startWorkingStatusTimer();
    }
    const noticeSessionId = String(
      ongoingTaskRestoreNotice.value?.chat_session_id || "",
    ).trim();
    if (noticeSessionId && sessionId && noticeSessionId !== sessionId) {
      clearOngoingTaskRestoreNotice();
    }
  },
);

watch(
  () => [
    String(routeChatTarget().projectId || "").trim(),
    String(route.query.chat_session_id || "").trim(),
    String(route.query[CREATE_CHAT_SESSION_QUERY_KEY] || "").trim(),
    String(route.query.message_id || "").trim(),
  ],
  async (
    [
      routeProjectId,
      routeChatSessionId,
      routeCreateChatSession,
      routeMessageId,
    ],
    previous,
  ) => {
    const previousKey = Array.isArray(previous) ? previous.join("|") : "";
    const currentKey = [
      routeProjectId,
      routeChatSessionId,
      routeCreateChatSession,
      routeMessageId,
    ].join("|");
    if (currentKey === previousKey) return;
    const activeProjectId = String(selectedProjectId.value || "").trim();
    if (routeProjectId && routeProjectId !== activeProjectId) {
      selectedProjectId.value = resolveAvailableProjectId(routeProjectId);
      return;
    }
    if (!activeProjectId) return;
    if (routeCreateChatSession === "1" && !routeChatSessionId) {
      await loadSelectedProjectConversation(activeProjectId);
      return;
    }
    if (
      routeChatSessionId &&
      routeChatSessionId !== String(currentChatSessionId.value || "").trim()
    ) {
      await fetchChatHistory(activeProjectId, routeChatSessionId);
    }
    await applyRouteMessageFocus();
  },
);

watch(
  () => String(route.query[STATISTICS_ANALYSIS_DRAFT_QUERY_KEY] || "").trim(),
  async (draftKey, previousKey) => {
    if (!draftKey || draftKey === previousKey) return;
    await applyStatisticsAnalysisDraftFromRoute();
  },
);

watch(
  () => String(route.query[PLUGIN_INSTALL_DRAFT_QUERY_KEY] || "").trim(),
  async (draftKey, previousKey) => {
    if (!draftKey || draftKey === previousKey) return;
    await applyPluginInstallDraftFromRoute();
  },
);

onMounted(async () => {
  loading.value = true;
  window.addEventListener(PROJECT_CREATED_EVENT, handleProjectCreated);
  window.addEventListener("keydown", handleWorkingStatusKeydown);
  void startNativeExternalAgentSessionEventSubscription();
  void hydrateNativeDesktopRuntimeInfo();
  window.setTimeout(() => {
    void hydrateNativeDesktopRuntimeInfo();
  }, 300);
  try {
    await Promise.all([
      fetchSystemConfig(),
      fetchProjects(),
      fetchModelTypeOptions(),
      fetchChatParameterOptions(),
      fetchGlobalProviders(),
    ]);
    const projectIdBeforeRouteSync = String(
      selectedProjectId.value || "",
    ).trim();
    const initialProjectId = syncProjectFromRoute();
    if (
      initialProjectId &&
      initialProjectId === projectIdBeforeRouteSync &&
      !selectedProjectConversationLoadingKey
    ) {
      await loadSelectedProjectConversation(initialProjectId);
    }
    await applyStatisticsAnalysisDraftFromRoute();
    await applyPluginInstallDraftFromRoute();
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
  await applyStatisticsAnalysisDraftFromRoute();
});

onUnmounted(() => {
  window.removeEventListener(PROJECT_CREATED_EVENT, handleProjectCreated);
  window.removeEventListener("keydown", handleWorkingStatusKeydown);
  if (connectorPollTimer !== null) {
    clearInterval(connectorPollTimer);
    connectorPollTimer = null;
  }
  clearExternalAgentStatusRefreshTimer();
  stopNativeExternalAgentSessionPolling();
  stopNativeExternalAgentSessionEventSubscription();
  nativeExternalAgentDeferredCleanupTimers.forEach((timer) => {
    window.clearTimeout(timer);
  });
  nativeExternalAgentDeferredCleanupTimers.clear();
  stopWorkingStatusTimer();
  if (chatRuntimePersistTimer !== null) {
    window.clearTimeout(chatRuntimePersistTimer);
    chatRuntimePersistTimer = null;
  }
  if (chatRuntimeRemotePersistTimer !== null) {
    window.clearTimeout(chatRuntimeRemotePersistTimer);
    chatRuntimeRemotePersistTimer = null;
  }
  cancelScheduledScrollToBottom();
  disconnectMessageListResizeObserver();
  clearHighlightedMessage();
  clearAutoSaveTimer();
  rejectPendingRequests("页面已关闭");
  disconnectWs("page closed");
});
</script>

<style scoped src="../../modules/project-chat/styles/project-chat-style-01.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-02.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-03.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-04.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-05.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-06.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-07.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-08.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-09.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-10.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-11.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-12.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-13.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-14.css"></style>
<style scoped src="../../modules/project-chat/styles/project-chat-style-15.css"></style>
