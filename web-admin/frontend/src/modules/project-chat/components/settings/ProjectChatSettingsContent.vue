<template>
  <div v-loading="loading" class="settings-center-page">
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
              v-if="settingsInternalItems.length > 1"
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
                <div class="settings-module-workspace">
                  <nav class="settings-module-tabs" aria-label="对话设置模块">
                    <button
                      v-for="item in visibleSettingsModuleNavItems"
                      :key="item.id"
                      type="button"
                      class="settings-module-tab"
                      :class="{ 'is-active': activeSettingsModule === item.id }"
                      @click="activeSettingsModule = item.id"
                    >
                      <span class="settings-module-tab__label">
                        {{ item.label }}
                      </span>
                      <span class="settings-module-tab__meta">
                        {{ item.meta }}
                      </span>
                    </button>
                    <el-empty
                      v-if="!visibleSettingsModuleNavItems.length"
                      description="没有匹配的设置模块"
                      :image-size="42"
                    />
                  </nav>

                  <section class="settings-module-toolbar">
                    <el-input
                      v-model="settingsModuleSearchQuery"
                      clearable
                      placeholder="搜索设置、工具、MCP、模型参数"
                      class="settings-module-toolbar__search"
                    />
                    <el-segmented
                      v-model="settingsModuleScope"
                      :options="settingsModuleScopeOptions"
                      class="settings-module-toolbar__scope"
                    />
                  </section>

                  <div class="settings-module-list">
                    <section
                      v-show="
                        activeSettingsModule === 'context' &&
                        settingsModuleMatches(
                          '项目 上下文 工作区 AIENTRY 入口 文件 workspace ai entry',
                          'project',
                        )
                      "
                      class="settings-module-section"
                    >
                      <div class="settings-module-section__head">
                        <div>
                          <strong>项目上下文</strong>
                          <span
                            >工作区和入口文件决定桌面智能体在本机如何理解项目。</span
                          >
                        </div>
                      </div>
                      <article
                        v-if="hasSelectedProject"
                        class="settings-module-row settings-module-row--stacked"
                      >
                        <div class="settings-module-row__icon">
                          <el-icon><Files /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>项目工作区</strong>
                          <span
                            >本机真实目录；命令执行和相对路径解析会以这里为基准。</span
                          >
                          <el-input
                            v-model="projectWorkspaceDraft"
                            class="settings-module-row__input"
                            placeholder="/Volumes/work/project"
                          />
                          <div class="settings-module-row__hint">
                            <template v-if="projectWorkspaceResolved">
                              已保存：{{ projectWorkspaceResolved }}
                            </template>
                            <template v-else>
                              当前项目还没有配置工作区路径。
                            </template>
                            <template v-if="projectWorkspaceDirty">
                              当前输入尚未保存。
                            </template>
                          </div>
                        </div>
                        <div class="settings-module-row__actions">
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
                            保存
                          </el-button>
                        </div>
                      </article>
                      <article
                        v-if="hasSelectedProject"
                        class="settings-module-row settings-module-row--stacked"
                      >
                        <div class="settings-module-row__icon">
                          <el-icon><DocumentCopy /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>AI 入口文件</strong>
                          <span
                            >项目级规则入口；未设置时继续使用内置统一入口。</span
                          >
                          <el-input
                            v-model="aiEntryFileDraft"
                            class="settings-module-row__input"
                            placeholder="AIENTRY.md"
                          />
                          <div class="settings-module-row__hint">
                            <template v-if="aiEntryFileResolved">
                              已保存：{{ aiEntryFileResolved }}
                            </template>
                            <template v-if="aiEntryFileDirty">
                              当前输入尚未保存。
                            </template>
                          </div>
                        </div>
                        <div class="settings-module-row__actions">
                          <el-button
                            @click="promptProjectAiEntryFile"
                            :loading="aiEntryFilePicking"
                          >
                            选择文件
                          </el-button>
                          <el-button
                            :loading="aiEntryFileCreating"
                            @click="createDefaultAiEntryFile"
                          >
                            创建
                          </el-button>
                          <el-button
                            type="primary"
                            :loading="aiEntryFileSaving"
                            @click="saveProjectAiEntryFile()"
                          >
                            保存
                          </el-button>
                        </div>
                      </article>
                      <article v-else class="settings-module-row">
                        <div class="settings-module-row__icon">
                          <el-icon><InfoFilled /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>尚未选择项目</strong>
                          <span>选择项目后才能配置项目工作区和入口文件。</span>
                        </div>
                      </article>
                    </section>

                    <section
                      v-show="
                        activeSettingsModule === 'execution' &&
                        settingsModuleMatches(
                          '执行 智能体 协作 模式 历史 消息 本轮 仅回答',
                          'project',
                        )
                      "
                      class="settings-module-section"
                    >
                      <div class="settings-module-section__head">
                        <div>
                          <strong>执行策略</strong>
                          <span
                            >控制本轮对话如何分配智能体、使用历史和选择工具边界。</span
                          >
                        </div>
                      </div>
                      <article class="settings-module-row">
                        <div class="settings-module-row__icon">
                          <el-icon><CollectionTag /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>智能体目录</strong>
                          <span
                            >桌面运行会从该目录读取项目智能体定义、提示词和脚本。</span
                          >
                        </div>
                        <div class="settings-module-row__control">
                          <el-input
                            v-model="projectChatSettings.agent_directory"
                            clearable
                            placeholder="例如 /workspace/.ai-employee/agents"
                            :disabled="!selectedProjectId"
                          >
                            <template #append>
                              <el-button
                                :loading="agentDirectoryPicking"
                                :disabled="
                                  !selectedProjectId ||
                                  skillDirectoryPicking ||
                                  ruleDirectoryPicking
                                "
                                @click="pickChatRuntimeDirectory('agent')"
                              >
                                选择目录
                              </el-button>
                            </template>
                          </el-input>
                        </div>
                      </article>
                      <article class="settings-module-row">
                        <div class="settings-module-row__icon">
                          <el-icon><FolderOpened /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>技能目录</strong>
                          <span
                            >桌面智能体会优先从该目录读取
                            SKILL.md、模板和脚本。</span
                          >
                        </div>
                        <div class="settings-module-row__control">
                          <el-input
                            v-model="projectChatSettings.skill_directory"
                            clearable
                            placeholder="例如 /workspace/.ai-employee/skills"
                            :disabled="!selectedProjectId"
                          >
                            <template #append>
                              <el-button
                                :loading="skillDirectoryPicking"
                                :disabled="
                                  !selectedProjectId || ruleDirectoryPicking
                                "
                                @click="pickChatRuntimeDirectory('skill')"
                              >
                                选择目录
                              </el-button>
                            </template>
                          </el-input>
                        </div>
                      </article>
                      <article class="settings-module-row">
                        <div class="settings-module-row__icon">
                          <el-icon><Document /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>规则目录</strong>
                          <span
                            >桌面智能体会按当前任务从该目录加载相关规则正文。</span
                          >
                        </div>
                        <div class="settings-module-row__control">
                          <el-input
                            v-model="projectChatSettings.rule_directory"
                            clearable
                            placeholder="例如 /workspace/.ai-employee/rules"
                            :disabled="!selectedProjectId"
                          >
                            <template #append>
                              <el-button
                                :loading="ruleDirectoryPicking"
                                :disabled="
                                  !selectedProjectId || skillDirectoryPicking
                                "
                                @click="pickChatRuntimeDirectory('rule')"
                              >
                                选择目录
                              </el-button>
                            </template>
                          </el-input>
                        </div>
                      </article>
                      <article class="settings-module-row">
                        <div class="settings-module-row__icon">
                          <el-icon><EditPen /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>历史消息条数</strong>
                          <span>控制发送给模型的上下文消息数量。</span>
                        </div>
                        <div class="settings-module-row__control">
                          <el-input-number
                            v-model="projectChatSettings.history_limit"
                            :min="1"
                            :max="50"
                          />
                        </div>
                      </article>
                      <article class="settings-module-row">
                        <div class="settings-module-row__icon">
                          <el-icon><RefreshRight /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>可恢复问题最大修复轮数</strong>
                          <span
                            >技能内容缺失、参数不完整等可恢复问题会交给 AI
                            继续处理；不可恢复错误仍会停止。</span
                          >
                        </div>
                        <div class="settings-module-row__control">
                          <el-input-number
                            v-model="
                              projectChatSettings.recoverable_issue_max_attempts
                            "
                            :min="1"
                            :max="50"
                            :step="1"
                            controls-position="right"
                          />
                        </div>
                      </article>
                      <article class="settings-module-row">
                        <div class="settings-module-row__icon">
                          <el-icon><InfoFilled /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>单轮仅回答</strong>
                          <span>只对下一次对话生效，不主动调用工具。</span>
                        </div>
                        <el-switch v-model="singleRoundAnswerOnly" />
                      </article>
                    </section>

                    <section
                      v-show="
                        activeSettingsModule === 'generation' &&
                        settingsModuleMatches(
                          '生成 回答 模型 温度 风格 图片 视频 参数 结论',
                          'all',
                        )
                      "
                      class="settings-module-section"
                    >
                      <div class="settings-module-section__head">
                        <div>
                          <strong>生成回答</strong>
                          <span
                            >当前模型类型：{{ currentModelTypeLabel }}。{{
                              currentModelTypeDescription ||
                              "参数面板会跟随当前模型类型切换。"
                            }}</span
                          >
                        </div>
                      </div>
                      <template v-if="currentModelParameterMode === 'text'">
                        <article class="settings-module-row">
                          <div class="settings-module-row__icon">
                            <el-icon><EditPen /></el-icon>
                          </div>
                          <div class="settings-module-row__main">
                            <strong>回答风格</strong>
                            <span>偏好 AI 返回内容的详细程度。</span>
                          </div>
                          <div class="settings-module-row__control">
                            <el-select
                              v-model="projectChatSettings.answer_style"
                              class="settings-module-row__select"
                            >
                              <el-option label="简洁" value="concise" />
                              <el-option label="平衡" value="balanced" />
                              <el-option label="详细" value="detailed" />
                            </el-select>
                          </div>
                        </article>
                        <article
                          class="settings-module-row settings-module-row--stacked"
                        >
                          <div class="settings-module-row__icon">
                            <el-icon><RefreshRight /></el-icon>
                          </div>
                          <div class="settings-module-row__main">
                            <strong>温度</strong>
                            <span>值越小越稳，值越大越发散。</span>
                            <el-slider
                              v-model="temperature"
                              :min="0"
                              :max="2"
                              :step="0.1"
                              show-input
                              :show-input-controls="false"
                            />
                          </div>
                        </article>
                        <article class="settings-module-row">
                          <div class="settings-module-row__icon">
                            <el-icon><Cpu /></el-icon>
                          </div>
                          <div class="settings-module-row__main">
                            <strong>思考模式</strong>
                            <span
                              >兼容模型会返回独立的思考过程；关闭时不发送思考参数。</span
                            >
                          </div>
                          <div class="settings-module-row__control">
                            <el-switch
                              v-model="projectChatSettings.thinking_mode"
                              active-value="enabled"
                              inactive-value="disabled"
                            />
                          </div>
                        </article>
                        <article
                          v-if="projectChatSettings.thinking_mode === 'enabled'"
                          class="settings-module-row"
                        >
                          <div class="settings-module-row__icon">
                            <el-icon><Operation /></el-icon>
                          </div>
                          <div class="settings-module-row__main">
                            <strong>思考强度</strong>
                            <span
                              >通过 reasoning_effort 传给 DeepSeek
                              等兼容模型。</span
                            >
                          </div>
                          <div class="settings-module-row__control">
                            <el-select
                              v-model="projectChatSettings.reasoning_effort"
                              class="settings-module-row__select"
                            >
                              <el-option label="低" value="low" />
                              <el-option label="中" value="medium" />
                              <el-option label="高" value="high" />
                            </el-select>
                          </div>
                        </article>
                        <article class="settings-module-row">
                          <div class="settings-module-row__icon">
                            <el-icon><CircleCheck /></el-icon>
                          </div>
                          <div class="settings-module-row__main">
                            <strong>先结论后步骤</strong>
                            <span>长回答优先给出核心结论。</span>
                          </div>
                          <el-switch
                            v-model="
                              projectChatSettings.prefer_conclusion_first
                            "
                          />
                        </article>
                      </template>
                      <template
                        v-else-if="
                          currentModelParameterMode === 'image' ||
                          currentModelParameterMode === 'video'
                        "
                      >
                        <article
                          v-for="section in currentModelParameterSections"
                          :key="`settings-module-${section.key}`"
                          class="settings-module-row"
                        >
                          <div class="settings-module-row__icon">
                            <el-icon><EditPen /></el-icon>
                          </div>
                          <div class="settings-module-row__main">
                            <strong>{{ section.label }}</strong>
                            <span>{{ section.helper || "模型参数" }}</span>
                          </div>
                          <div class="settings-module-row__control">
                            <el-segmented
                              v-if="section.useSegmented"
                              :model-value="section.modelValue"
                              :options="
                                section.options.map((item) => ({
                                  label: item.label,
                                  value: item.value,
                                }))
                              "
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
                              class="settings-module-row__select"
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
                          </div>
                        </article>
                      </template>
                    </section>

                    <section
                      v-show="
                        activeSettingsModule === 'tools' &&
                        settingsModuleMatches(
                          '插件 项目管理 部署 发布 媒体 图片 视频 音频 工具 MCP 护栏 web search extract provider firecrawl tavily exa parallel managed',
                          'all',
                        )
                      "
                      class="settings-module-section"
                    >
                      <div class="settings-module-section__head">
                        <div>
                          <strong>插件与工具</strong>
                          <span
                            >按项目启用扩展能力；未启用的插件不会进入 AI
                            工具列表。MCP registry 和 Web 搜索 provider。</span
                          >
                        </div>
                      </div>
                      <article
                        v-for="plugin in builtinPluginCatalog"
                        :key="plugin.id"
                        class="settings-module-row"
                      >
                        <div class="settings-module-row__icon">
                          <el-icon><CollectionTag /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>{{ plugin.label }}插件</strong>
                          <span>{{ plugin.description }}</span>
                        </div>
                        <el-switch
                          :model-value="isBuiltinPluginEnabled(plugin.id)"
                          @change="toggleBuiltinPlugin(plugin.id, $event)"
                        />
                      </article>
                      <article
                        v-for="plugin in localPluginCatalog"
                        :key="`local-${plugin.id}-${plugin.source}`"
                        class="settings-module-row"
                      >
                        <div class="settings-module-row__icon">
                          <el-icon><Connection /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>{{ plugin.name || plugin.id }}插件</strong>
                          <span>
                            {{ plugin.description || "本机声明式 MCP 插件" }} ·
                            {{
                              plugin.source === "project" ? "项目" : "用户"
                            }}级
                            <template v-if="plugin.version">
                              · v{{ plugin.version }}</template
                            >
                            <template v-if="plugin.error">
                              · {{ plugin.error }}</template
                            >
                          </span>
                        </div>
                        <el-switch
                          :model-value="isLocalPluginEnabled(plugin)"
                          :disabled="Boolean(plugin.error) || !plugin.server"
                          @change="toggleLocalPlugin(plugin, $event)"
                        />
                      </article>
                      <div
                        v-if="!localPluginCatalog.length"
                        class="settings-module-hint"
                      >
                        将插件放入
                        `.ai-employee/plugins/&lt;plugin-id&gt;/plugin.json`，重新打开设置即可发现。
                      </div>
                      <article class="settings-module-row">
                        <div class="settings-module-row__icon">
                          <el-icon><CollectionTag /></el-icon>
                        </div>
                        <div class="settings-module-row__main">
                          <strong>按需启用工具</strong>
                          <span>{{
                            projectChatSettings.auto_use_tools
                              ? "允许系统在必要时选择工具"
                              : "系统不会主动调工具"
                          }}</span>
                        </div>
                        <el-switch
                          v-model="projectChatSettings.auto_use_tools"
                          @change="
                            projectChatSettings.auto_use_tools_explicit = true
                          "
                        />
                      </article>
                      <div class="settings-module-subsection">
                        <div class="settings-module-subsection__head">
                          <strong>MCP 模块</strong>
                          <div class="settings-module-row__actions">
                            <el-button
                              size="small"
                              @click="openMcpServerDialog('project')"
                            >
                              添加项目 Server
                            </el-button>
                            <el-button
                              size="small"
                              @click="openMcpServerDialog('global')"
                            >
                              添加全局 Server
                            </el-button>
                            <el-button
                              size="small"
                              type="primary"
                              :loading="projectMcpConfigSaving"
                              @click="saveProjectMcpConfig"
                            >
                              保存项目文件
                            </el-button>
                          </div>
                        </div>
                        <div class="mcp-server-table">
                          <article
                            v-for="server in effectiveMcpServerRows"
                            :key="`${server.scope}:${server.name}`"
                            class="mcp-server-row"
                          >
                            <div class="mcp-server-row__main">
                              <strong>{{ server.name }}</strong>
                              <span
                                >{{ server.type }} ·
                                {{ server.endpoint || "未配置入口" }}</span
                              >
                            </div>
                            <el-tag
                              size="small"
                              :type="
                                server.scope === 'project' ? 'warning' : 'info'
                              "
                            >
                              {{ server.scope === "project" ? "项目" : "全局" }}
                            </el-tag>
                            <el-tag
                              size="small"
                              :type="server.enabled ? 'success' : 'info'"
                            >
                              {{ server.enabled ? "启用" : "停用" }}
                            </el-tag>
                            <div class="mcp-server-row__actions">
                              <el-button
                                size="small"
                                @click="testMcpServer(server)"
                              >
                                测试
                              </el-button>
                              <el-button
                                size="small"
                                @click="editMcpServer(server)"
                              >
                                编辑
                              </el-button>
                              <el-button
                                size="small"
                                type="danger"
                                plain
                                @click="removeMcpServer(server)"
                              >
                                删除
                              </el-button>
                            </div>
                          </article>
                          <el-empty
                            v-if="!effectiveMcpServerRows.length"
                            description="暂无 MCP server"
                            :image-size="48"
                          />
                        </div>
                        <details class="mcp-json-details">
                          <summary>查看 MCP JSON</summary>
                          <el-input
                            v-model="projectMcpConfigText"
                            type="textarea"
                            :rows="8"
                            resize="vertical"
                            spellcheck="false"
                          />
                          <div class="mcp-local-editor__actions">
                            <el-button
                              size="small"
                              @click="formatProjectMcpConfigText"
                            >
                              格式化 JSON
                            </el-button>
                            <el-button
                              size="small"
                              @click="resetProjectMcpConfigText"
                            >
                              清空项目配置
                            </el-button>
                          </div>
                        </details>
                      </div>
                      <div class="settings-module-subsection">
                        <div class="settings-module-subsection__head">
                          <strong>Web 搜索 Provider</strong>
                          <el-segmented
                            v-model="webToolsConfigScope"
                            :options="webToolsScopeOptions"
                          />
                        </div>
                        <div
                          v-if="
                            hasSelectedProject ||
                            webToolsConfigScope === 'global'
                          "
                          class="web-tools-provider-table"
                        >
                          <article
                            v-for="provider in webToolsProviderRows"
                            :key="`${webToolsConfigScope}:${provider.id}`"
                            class="web-tools-provider-row"
                          >
                            <div class="web-tools-provider-row__icon">
                              <el-icon><CollectionTag /></el-icon>
                            </div>
                            <div class="web-tools-provider-row__main">
                              <strong>{{ provider.label }}</strong>
                              <span>{{ provider.description }}</span>
                            </div>
                            <el-tag
                              v-if="provider.selected"
                              size="small"
                              type="success"
                            >
                              当前
                            </el-tag>
                            <el-tag
                              v-else-if="provider.inherited"
                              size="small"
                              type="info"
                            >
                              继承
                            </el-tag>
                            <el-tag
                              v-else-if="provider.configured"
                              size="small"
                              type="warning"
                            >
                              已配置
                            </el-tag>
                            <el-switch
                              :model-value="provider.selected"
                              :disabled="
                                webToolsConfigScope === 'project' &&
                                !hasSelectedProject
                              "
                              @change="
                                (value) =>
                                  setWebToolProviderEnabled(provider.id, value)
                              "
                            />
                            <el-button
                              size="small"
                              :icon="EditPen"
                              circle
                              @click="openWebToolsProviderDialog(provider.id)"
                            />
                          </article>
                        </div>
                        <div v-else class="mcp-section-tip">
                          先选择项目，才能管理当前项目 web-tools 配置。
                        </div>
                        <details class="mcp-json-details">
                          <summary>高级 web-tools JSON</summary>
                          <el-input
                            v-if="webToolsConfigScope === 'global'"
                            v-model="globalWebToolsConfigText"
                            type="textarea"
                            :rows="8"
                            resize="vertical"
                            spellcheck="false"
                          />
                          <el-input
                            v-else
                            v-model="projectWebToolsConfigText"
                            type="textarea"
                            :rows="8"
                            resize="vertical"
                            spellcheck="false"
                          />
                          <div class="mcp-local-editor__actions">
                            <el-button
                              size="small"
                              @click="formatActiveWebToolsConfigText"
                            >
                              格式化 JSON
                            </el-button>
                            <el-button
                              v-if="webToolsConfigScope === 'project'"
                              size="small"
                              @click="resetProjectWebToolsConfigText"
                            >
                              清空项目配置
                            </el-button>
                            <el-button
                              size="small"
                              type="primary"
                              :loading="activeWebToolsConfigSaving"
                              @click="saveActiveWebToolsConfig"
                            >
                              保存文件
                            </el-button>
                          </div>
                        </details>
                      </div>
                    </section>
                    <el-empty
                      v-if="!visibleSettingsModuleNavItems.length"
                      description="调整搜索词或范围后继续配置"
                      :image-size="56"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="settings-center-stage__body">
          <component
            :is="settingsChildComponent"
            v-if="settingsChildComponent"
          />
        </div>
      </section>
    </div>
  </div>
</template>

<script>
import {
  CircleCheck,
  CollectionTag,
  Connection,
  Cpu,
  Document,
  DocumentCopy,
  EditPen,
  Files,
  FolderOpened,
  InfoFilled,
  Operation,
  RefreshRight,
} from "@element-plus/icons-vue";

export default {
  name: "ProjectChatSettingsContent",
  components: {
    CircleCheck,
    CollectionTag,
    Connection,
    Cpu,
    Document,
    DocumentCopy,
    EditPen,
    Files,
    FolderOpened,
    InfoFilled,
    Operation,
    RefreshRight,
  },
  props: {
    context: {
      type: Object,
      required: true,
    },
  },
  setup(props) {
    return props.context || {};
  },
};
</script>

<style scoped src="../../styles/project-chat-style-01.css"></style>

<style scoped src="../../styles/project-chat-style-02.css"></style>

<style scoped src="../../styles/project-chat-style-03.css"></style>

<style scoped src="../../styles/project-chat-style-04.css"></style>

<style scoped src="../../styles/project-chat-style-05.css"></style>

<style scoped src="../../styles/project-chat-style-06.css"></style>

<style scoped src="../../styles/project-chat-style-07.css"></style>

<style scoped src="../../styles/project-chat-style-08.css"></style>

<style scoped src="../../styles/project-chat-style-09.css"></style>

<style scoped src="../../styles/project-chat-style-10.css"></style>

<style scoped src="../../styles/project-chat-style-11.css"></style>

<style scoped src="../../styles/project-chat-style-12.css"></style>

<style scoped src="../../styles/project-chat-style-13.css"></style>

<style scoped src="../../styles/project-chat-style-14.css"></style>

<style scoped src="../../styles/project-chat-style-15.css"></style>

<style scoped>
.settings-center-stage__body--chat .settings-chat-main-card {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  height: auto;
  min-height: 100%;
  overflow: visible;
  gap: 14px;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid rgba(226, 232, 240, 0.84);
  background: rgba(255, 255, 255, 0.78);
  box-shadow: none;
}

.settings-center-stage__body--chat {
  overflow-x: hidden;
  overflow-y: auto !important;
  overscroll-behavior-y: contain;
  -webkit-overflow-scrolling: touch;
}

.settings-center-stage__body--chat .settings-chat-layout--single,
.settings-center-stage__body--chat .settings-chat-main,
.settings-center-stage__body--chat .settings-chat-main--wide {
  min-height: 0;
  height: auto;
}

.settings-center-stage__body--chat .settings-module-workspace {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  width: 100%;
  min-height: auto;
  gap: 12px;
  overflow: visible;
}

.settings-center-stage__body--chat .settings-module-tabs {
  display: flex;
  flex: 0 0 auto;
  gap: 6px;
  min-width: 0;
  overflow-x: auto;
  padding: 4px;
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.92);
  scrollbar-width: none;
}

.settings-center-stage__body--chat .settings-module-tabs::-webkit-scrollbar {
  display: none;
}

.settings-module-tab {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #64748b;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  cursor: pointer;
}

.settings-module-tab:hover {
  color: #0f172a;
  background: rgba(255, 255, 255, 0.82);
}

.settings-module-tab.is-active {
  color: #0f172a;
  background: #fff;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
}

.settings-module-tab__meta {
  color: #94a3b8;
  font-size: 10px;
  font-weight: 600;
}

.settings-module-tab.is-active .settings-module-tab__meta {
  color: #2563eb;
}

.settings-center-stage__body--chat .settings-module-toolbar {
  flex: 0 0 auto;
}

.settings-center-stage__body--chat .settings-module-list {
  flex: 0 0 auto;
  min-height: auto;
  overflow-x: hidden;
  overflow-y: visible;
  padding-right: 4px;
  scrollbar-gutter: stable;
  scrollbar-width: auto;
  scrollbar-color: rgba(100, 116, 139, 0.46) transparent;
}

.settings-center-stage__body--chat .settings-module-list::-webkit-scrollbar {
  width: 10px;
}

.settings-center-stage__body--chat
  .settings-module-list::-webkit-scrollbar-thumb {
  border: 3px solid transparent;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.46);
  background-clip: padding-box;
}

.settings-center-stage__body--chat .settings-chat-quick-overview {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.settings-center-stage__body--chat .settings-chat-quick-overview__card {
  gap: 3px;
  min-height: 74px;
  padding: 10px 12px;
  border-radius: 8px;
  border-color: rgba(226, 232, 240, 0.86);
  background: #fff;
  box-shadow: none;
}

.settings-center-stage__body--chat .settings-chat-quick-overview__label {
  color: #64748b;
  font-size: 11px;
  letter-spacing: 0;
}

.settings-center-stage__body--chat .settings-chat-quick-overview__value {
  color: #111827;
  font-size: 13px;
  line-height: 1.35;
}

.settings-center-stage__body--chat .settings-chat-quick-overview__meta {
  font-size: 12px;
  line-height: 1.45;
}

.settings-module-toolbar {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.68);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.settings-module-toolbar__search {
  min-width: 0;
}

.settings-module-toolbar__scope {
  justify-self: end;
}

.settings-module-workspace {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  align-items: start;
  height: auto;
  min-width: 0;
  min-height: 0;
  gap: 18px;
}

.settings-module-menu {
  position: sticky;
  top: 0;
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.58);
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.06);
}

.settings-module-menu__item {
  width: 100%;
  min-height: 82px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 8px;
  padding: 13px 14px;
  border: 1px solid transparent;
  border-radius: 16px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 160ms ease,
    background-color 160ms ease,
    transform 160ms ease;
}

.settings-module-menu__item:hover {
  background: rgba(248, 250, 252, 0.88);
  transform: translateY(-1px);
}

.settings-module-menu__item.is-active {
  border-color: rgba(56, 189, 248, 0.34);
  background: linear-gradient(
    180deg,
    rgba(239, 246, 255, 0.96),
    rgba(224, 242, 254, 0.74)
  );
  box-shadow: 0 8px 18px rgba(14, 116, 144, 0.08);
}

.settings-module-menu__title {
  min-width: 0;
  color: #111827;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
}

.settings-module-menu__desc {
  grid-column: 1 / -1;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.settings-module-menu__meta {
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(226, 232, 240, 0.78);
  color: #475569;
  font-size: 11px;
  line-height: 1.4;
}

.settings-module-list {
  min-width: 0;
  min-height: auto;
  height: auto;
  max-height: none;
  display: grid;
  gap: 12px;
  overflow: visible;
}

.settings-module-section {
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 24px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.88),
    rgba(248, 250, 252, 0.74)
  );
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.settings-module-section__head,
.settings-module-subsection__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 60px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.72);
  background: rgba(248, 250, 252, 0.52);
}

.settings-module-section__head > div,
.settings-module-subsection__head > div {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.settings-module-section__head strong,
.settings-module-subsection__head strong {
  color: #111827;
  font-size: 13px;
  line-height: 1.35;
}

.settings-module-section__head span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.settings-module-row {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) minmax(180px, auto);
  align-items: center;
  gap: 12px;
  min-height: 72px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.76);
}

.settings-module-row:last-child {
  border-bottom: 0;
}

.settings-module-row--stacked {
  align-items: start;
}

.settings-module-row__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  color: #334155;
  background: rgba(241, 245, 249, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.9);
}

.settings-module-row__main {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.settings-module-row__main strong {
  color: #111827;
  font-size: 13px;
  line-height: 1.35;
}

.settings-module-row__main span,
.settings-module-row__hint {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.settings-module-row__input {
  width: min(100%, 720px);
  margin-top: 6px;
}

.settings-module-row__control {
  justify-self: end;
  min-width: 180px;
}

.settings-module-row__select {
  width: min(320px, 32vw);
  min-width: 220px;
}

.settings-module-row__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.settings-module-subsection {
  border-top: 1px solid rgba(226, 232, 240, 0.76);
}

.settings-module-subsection:first-of-type {
  border-top: 0;
}

.settings-module-subsection__head {
  min-height: 52px;
  background: rgba(255, 255, 255, 0.42);
}

.settings-module-subsection__head strong {
  font-size: 12px;
}

.settings-module-subsection .mcp-server-table,
.settings-module-subsection .web-tools-provider-table,
.settings-module-subsection .mcp-section-tip {
  margin: 12px 14px 0;
}

.settings-module-subsection .mcp-json-details {
  margin: 12px 14px 14px;
}

.mcp-file-manager {
  width: 100%;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.64);
}

.mcp-file-manager__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.mcp-file-manager__head strong {
  display: block;
  color: #1f2937;
  font-size: 13px;
  word-break: break-all;
}

.mcp-file-manager__head p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.mcp-file-manager__actions,
.mcp-server-row__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.mcp-server-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.web-tools-provider-table {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.78);
}

.mcp-server-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.78);
}

.web-tools-provider-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 10px;
  min-height: 64px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.web-tools-provider-row:last-child {
  border-bottom: 0;
}

.web-tools-provider-row__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 7px;
  background: rgba(59, 130, 246, 0.12);
  color: #2563eb;
}

.mcp-server-row__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.web-tools-provider-row__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.mcp-server-row__main strong {
  color: #111827;
  font-size: 13px;
}

.web-tools-provider-row__main strong {
  color: #111827;
  font-size: 13px;
}

.mcp-server-row__main span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-all;
}

.web-tools-provider-row__main span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.mcp-json-details {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px dashed rgba(148, 163, 184, 0.34);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
}

.mcp-json-details summary {
  cursor: pointer;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.mcp-json-details :deep(.el-textarea) {
  margin-top: 10px;
}

@media (max-width: 900px) {
  .mcp-server-form {
    grid-template-columns: 1fr;
  }

  .web-tools-provider-form {
    grid-template-columns: 1fr;
  }

  .settings-module-toolbar {
    grid-template-columns: 1fr;
  }

  .settings-module-toolbar__scope {
    justify-self: stretch;
  }

  .settings-module-workspace {
    grid-template-columns: 1fr;
  }

  .settings-module-menu {
    position: static;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .settings-module-row {
    grid-template-columns: 32px minmax(0, 1fr);
    align-items: start;
  }

  .settings-module-row > .el-switch,
  .settings-module-row__control,
  .settings-module-row__actions {
    grid-column: 2;
    justify-self: start;
    min-width: 0;
  }

  .settings-module-row__select {
    width: min(100%, 320px);
    min-width: 0;
  }

  .settings-center-stage__body--chat .settings-chat-quick-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mcp-file-manager__head,
  .mcp-server-row,
  .web-tools-provider-row {
    display: flex;
    flex-direction: column;
    align-items: stretch;
  }

  .mcp-file-manager__actions,
  .mcp-server-row__actions {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .settings-center-stage__body--chat .settings-chat-main-card {
    padding: 12px;
  }

  .settings-center-stage__body--chat .settings-chat-quick-overview {
    grid-template-columns: 1fr;
  }

  .settings-module-section__head,
  .settings-module-subsection__head {
    align-items: stretch;
    flex-direction: column;
  }

  .settings-module-row {
    padding: 10px 12px;
  }

  .settings-module-menu {
    grid-template-columns: 1fr;
  }
}
</style>
