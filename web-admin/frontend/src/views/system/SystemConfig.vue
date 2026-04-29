<template>
  <div class="system-config-page" v-loading="loading">
    <section class="hero">
      <div class="hero-body">
        <p class="hero-eyebrow">System Control</p>
        <h2>系统配置与 MCP</h2>
        <p class="hero-desc">
          在这里维护系统级开关、默认 MCP 配置，以及当前远程 MCP 服务暴露出的能力状态。
        </p>
        <div class="hero-highlights">
          <span class="hero-highlight">系统默认项</span>
          <span class="hero-highlight">全局助手语音</span>
          <span class="hero-highlight">MCP 服务探测</span>
        </div>
      </div>
      <div class="hero-actions">
        <el-button :loading="refreshingPanels" @click="refreshAllPanels"
          >刷新状态</el-button
        >
        <el-button type="primary" :loading="saving" @click="saveConfig"
          >保存配置</el-button
        >
      </div>
    </section>

    <section class="overview-grid">
      <article class="metric-card">
        <span class="metric-label">MCP 服务数</span>
        <strong class="metric-value">{{ mcpServers.length }}</strong>
        <span class="metric-foot">读取自系统级 `mcpServers`</span>
      </article>
      <article class="metric-card">
        <span class="metric-label">已发现能力</span>
        <strong class="metric-value">{{ totalSkillCount }}</strong>
        <span class="metric-foot">tools + prompts + resources</span>
      </article>
      <article class="metric-card">
        <span class="metric-label">探测异常</span>
        <strong class="metric-value">{{ totalErrorCount }}</strong>
        <span class="metric-foot">协议不兼容或服务不可达时出现</span>
      </article>
    </section>

    <section class="system-config-tabs-shell">
      <div class="system-config-tabs-shell__header">
        <div>
          <p class="panel-kicker">Workspace View</p>
          <h3>按工作区切换配置</h3>
          <p>把默认项、助手、生态和 MCP 运行面板拆开，避免在同一页里来回滚动。</p>
        </div>
      </div>

      <el-tabs v-model="activeTab" class="system-config-tabs">
        <el-tab-pane name="defaults">
          <template #label>
            <span class="system-config-tab-label">
              <span class="system-config-tab-label__title">默认项</span>
              <span class="system-config-tab-label__meta">系统开关与员工规则</span>
            </span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="assistant">
          <template #label>
            <span class="system-config-tab-label">
              <span class="system-config-tab-label__title">全局助手</span>
              <span class="system-config-tab-label__meta">语音、模型与欢迎语</span>
            </span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="ecosystem">
          <template #label>
            <span class="system-config-tab-label">
              <span class="system-config-tab-label__title">技能生态</span>
              <span class="system-config-tab-label__meta">站点、官网与 registry</span>
            </span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="mcp-config">
          <template #label>
            <span class="system-config-tab-label">
              <span class="system-config-tab-label__title">MCP 配置</span>
              <span class="system-config-tab-label__meta">地址、开关与 JSON</span>
            </span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="mcp-discovery">
          <template #label>
            <span class="system-config-tab-label">
              <span class="system-config-tab-label__title">MCP 探测</span>
              <span class="system-config-tab-label__meta">能力与连通结果</span>
            </span>
          </template>
        </el-tab-pane>
      </el-tabs>
    </section>

    <div
      v-show="activeTab !== 'mcp-discovery'"
      :class="['content-grid', { 'content-grid--single': activeTab === 'mcp-config' }]"
    >
      <div v-show="activeTab !== 'mcp-config'" class="content-main">
        <section v-show="activeTab === 'defaults'" class="panel">
          <div class="panel-head">
            <div>
              <p class="panel-kicker">Defaults</p>
              <h3>系统默认项</h3>
              <p>集中维护系统级开关、上传限制和默认系统提示词。</p>
            </div>
          </div>

          <el-alert
            title="这些开关只影响系统级默认行为，不会修改既有业务数据。"
            type="info"
            :closable="false"
            show-icon
            class="inline-alert"
          />

          <el-form label-position="top" class="switch-form">
            <div class="switch-list">
              <div class="switch-card">
                <div>
                  <div class="switch-title">项目手册旧开关</div>
                  <div class="switch-desc">
                    兼容保留字段，当前项目使用手册已改为直接读取内容，不再调用大模型。
                  </div>
                </div>
                <el-switch v-model="form.enable_project_manual_generation" />
              </div>

              <div class="switch-card">
                <div>
                  <div class="switch-title">员工手册旧开关</div>
                  <div class="switch-desc">
                    兼容保留字段，当前员工使用手册已改为直接读取内容，不再调用大模型。
                  </div>
                </div>
                <el-switch v-model="form.enable_employee_manual_generation" />
              </div>
            </div>

            <div class="number-grid">
              <el-form-item label="单次对话最大上传文件数">
                <el-input-number
                  v-model="form.chat_upload_max_limit"
                  :min="1"
                  :max="20"
                />
                <div class="field-desc">
                  限制 AI 对话里一次最多上传的文件数量。
                </div>
              </el-form-item>

              <el-form-item label="模型默认 Max Tokens">
                <el-input-number
                  v-model="form.chat_max_tokens"
                  :min="128"
                  :max="8192"
                  :step="64"
                />
                <div class="field-desc">控制 AI 对话默认最大输出长度。</div>
              </el-form-item>
            </div>

            <el-form-item label="AI 对话中心默认系统提示词">
              <el-input
                v-model="form.default_chat_system_prompt"
                type="textarea"
                :rows="8"
                resize="vertical"
                placeholder="为空时使用系统内置默认提示词；填写后会作为项目聊天未单独配置 system prompt 时的默认值。"
              />
              <div class="field-desc">
                当项目聊天没有单独填写 `system_prompt` 时，会自动回退到这里。
              </div>
            </el-form-item>
          </el-form>
        </section>

        <section v-show="activeTab === 'defaults'" class="panel">
          <div class="panel-head">
            <div>
              <p class="panel-kicker">Employees</p>
              <h3>AI 员工规则策略</h3>
              <p>把自动生成规则的开关、来源和内部策略提示词收拢到同一块。</p>
            </div>
          </div>

          <el-form label-position="top" class="switch-form">
            <div class="switch-card employee-rule-config-card">
              <div>
                <div class="switch-title">AI 员工规则自动生成</div>
                <div class="switch-desc">
                  创建 AI 员工时，系统会基于系统级 MCP 规则源自动补全规则草稿，再落地为本地规则并绑定给员工；对话页不再展示规则来源选择。
                </div>
              </div>
              <el-switch
                v-model="form.employee_auto_rule_generation_enabled"
              />
            </div>

            <div class="number-grid">
              <el-form-item label="自动生成规则上限">
                <el-input-number
                  v-model="form.employee_auto_rule_generation_max_count"
                  :min="1"
                  :max="6"
                />
                <div class="field-desc">
                  每次创建员工最多补全多少条规则草稿。
                </div>
              </el-form-item>

              <el-form-item label="规则来源">
                <el-checkbox-group
                  v-model="form.employee_auto_rule_generation_source_filters"
                  class="employee-rule-source-group"
                >
                  <el-checkbox
                    v-for="option in EMPLOYEE_AUTO_RULE_SOURCE_OPTIONS"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </el-checkbox>
                </el-checkbox-group>
                <div class="field-desc">
                  当前先支持系统内置的 prompts.chat curated 规则源。
                </div>
              </el-form-item>
            </div>

            <el-form-item label="规则生成策略提示词">
              <el-input
                v-model="form.employee_auto_rule_generation_prompt"
                type="textarea"
                :rows="6"
                resize="vertical"
                placeholder="用于约束系统在员工创建时优先生成哪类规则。"
              />
              <div class="field-desc">
                这是后台自动生成规则时使用的内部策略提示词，不直接展示给终端用户。
              </div>
            </el-form-item>
          </el-form>
        </section>

        <section v-show="activeTab === 'assistant'" class="panel">
          <div class="panel-head">
            <div>
              <p class="panel-kicker">Assistant</p>
              <h3>全局助手语音与欢迎语</h3>
              <p>统一配置开放范围、模型选择、播报音色和首次欢迎语。</p>
            </div>
          </div>

          <el-form label-position="top" class="switch-form">
            <div class="employee-skill-site-card voice-config-card">
              <div class="voice-config-section">
                <div class="voice-config-section__head">
                  <div class="employee-skill-site-card__title">统一开放范围</div>
                  <div class="switch-desc">
                    下面这组账号范围同时用于语音输入和语音播报。留空时，默认对所有拥有 `menu.ai.chat` 的登录用户开放。
                  </div>
                </div>

                <div class="employee-skill-site-card__grid">
                  <el-form-item label="开放用户">
                    <el-select
                      v-model="form.voice_input_allowed_usernames"
                      multiple
                      collapse-tags
                      collapse-tags-tooltip
                      clearable
                      filterable
                      style="width: 100%"
                      placeholder="留空表示不按用户单独限制"
                    >
                      <el-option
                        v-for="item in voiceUserOptions"
                        :key="item.username"
                        :label="item.username"
                        :value="item.username"
                      />
                    </el-select>
                  </el-form-item>

                  <el-form-item label="开放角色">
                    <el-select
                      v-model="form.voice_input_allowed_role_ids"
                      multiple
                      collapse-tags
                      collapse-tags-tooltip
                      clearable
                      style="width: 100%"
                      placeholder="留空表示不按角色单独限制"
                    >
                      <el-option
                        v-for="item in voiceRoleOptions"
                        :key="item.id"
                        :label="`${item.name} (${item.id})`"
                        :value="item.id"
                      />
                    </el-select>
                  </el-form-item>
                </div>
              </div>

              <div class="voice-config-divider" />

                <div class="voice-config-section">
                  <div class="voice-config-section__head">
                    <div class="employee-skill-site-card__title">问题求解</div>
                    <div class="switch-desc">
                      为全局助手回答系统问题单独指定对话模型，这组模型和语音转写模型分开管理。
                    </div>
                  </div>

                  <div class="switch-card">
                    <div>
                      <div class="switch-title">启用全局助手悬浮窗</div>
                      <div class="switch-desc">
                        关闭后，页面右下角的全局助手入口和悬浮弹框都会隐藏，语音与欢迎语也不会主动启动。
                      </div>
                    </div>
                    <el-switch v-model="form.global_assistant_enabled" />
                  </div>

                <el-alert
                  v-if="!globalAssistantChatProviderOptions.length"
                  title="当前没有可用的全局助手对话模型，请先在模型供应商页配置 `text_generation` 或 `multimodal_chat` 类型模型。"
                  type="warning"
                  :closable="false"
                  show-icon
                  class="inline-alert"
                />

                <div class="employee-skill-site-card__grid">
                  <el-form-item label="问题求解供应商">
                    <el-select
                      v-model="form.global_assistant_chat_provider_id"
                      style="width: 100%"
                      clearable
                      placeholder="请选择全局助手对话供应商"
                      :disabled="!globalAssistantChatProviderOptions.length"
                      @change="handleGlobalAssistantChatProviderChange"
                    >
                      <el-option
                        v-for="item in globalAssistantChatProviderOptions"
                        :key="item.id"
                        :label="item.name"
                        :value="item.id"
                      />
                    </el-select>
                    <div class="field-desc">
                      留空时仍会走系统默认模型；选中后，全局助手会优先使用这里的模型回答问题。
                    </div>
                  </el-form-item>

                  <el-form-item label="问题求解模型">
                    <el-select
                      v-model="form.global_assistant_chat_model_name"
                      style="width: 100%"
                      clearable
                      placeholder="请选择全局助手对话模型"
                      :disabled="!selectedGlobalAssistantChatProviderModels.length"
                    >
                      <el-option
                        v-for="item in selectedGlobalAssistantChatProviderModels"
                        :key="`${form.global_assistant_chat_provider_id}-${item.name}`"
                        :label="item.name"
                        :value="item.name"
                      />
                    </el-select>
                    <div class="field-desc">
                      这组模型负责理解你的问题、调用工具并生成助手回复，不参与录音转写。
                    </div>
                  </el-form-item>
                </div>
              </div>

              <div class="voice-config-divider" />

              <div class="voice-config-section">
                <div class="voice-config-section__head">
                  <div class="employee-skill-site-card__title">语音输入</div>
                  <div class="switch-desc">
                    为助手录音配置真实转写模型，启用后将通过后端转写接口识别，不再依赖浏览器内置识别。
                  </div>
                </div>

                <div class="switch-card">
                  <div>
                    <div class="switch-title">启用语音输入</div>
                    <div class="switch-desc">
                      开启后，助手录音会走后端转写接口。
                    </div>
                  </div>
                  <el-switch v-model="form.voice_input_enabled" />
                </div>

                <el-alert
                  v-if="form.voice_input_enabled && !voiceProviderOptions.length"
                  title="当前没有可用的音频转写模型，请先在模型供应商页配置 `audio_transcription` 类型模型。"
                  type="warning"
                  :closable="false"
                  show-icon
                  class="inline-alert"
                />

                <div class="employee-skill-site-card__grid">
                  <el-form-item label="语音供应商">
                    <el-select
                      v-model="form.voice_input_provider_id"
                      style="width: 100%"
                      clearable
                      placeholder="请选择语音转写供应商"
                      :disabled="!voiceProviderOptions.length"
                      @change="handleVoiceProviderChange"
                    >
                      <el-option
                        v-for="item in voiceProviderOptions"
                        :key="item.id"
                        :label="item.name"
                        :value="item.id"
                      />
                    </el-select>
                  </el-form-item>

                  <el-form-item label="语音模型">
                    <el-select
                      v-model="form.voice_input_model_name"
                      style="width: 100%"
                      clearable
                      placeholder="请选择语音转写模型"
                      :disabled="!selectedVoiceProviderModels.length"
                    >
                      <el-option
                        v-for="item in selectedVoiceProviderModels"
                        :key="`${form.voice_input_provider_id}-${item.name}`"
                        :label="item.name"
                        :value="item.name"
                      />
                    </el-select>
                  </el-form-item>
                </div>
              </div>

              <div class="voice-config-divider" />

              <div class="voice-config-section">
                <div class="voice-config-section__head">
                  <div class="employee-skill-site-card__title">语音播报</div>
                  <div class="switch-desc">
                    为 AI 助手回答配置真实 TTS 模型和固定音色，启用后优先走后端播报。
                  </div>
                </div>

                <div class="switch-card">
                  <div>
                    <div class="switch-title">启用语音播报</div>
                    <div class="switch-desc">
                      开启后，AI 助手的“语音播放”会优先走系统配置的后端语音模型，不再依赖浏览器内置声音。
                    </div>
                  </div>
                  <el-switch v-model="form.voice_output_enabled" />
                </div>

                <el-alert
                  v-if="form.voice_output_enabled && !voiceOutputProviderOptions.length"
                  title="当前没有可用的语音生成模型，请先在模型供应商页配置 `audio_generation` 类型模型。"
                  type="warning"
                  :closable="false"
                  show-icon
                  class="inline-alert"
                />

                <div class="employee-skill-site-card__grid">
                  <el-form-item label="播报供应商">
                    <el-select
                      v-model="form.voice_output_provider_id"
                      style="width: 100%"
                      clearable
                      placeholder="请选择语音播报供应商"
                      :disabled="!voiceOutputProviderOptions.length"
                      @change="handleVoiceOutputProviderChange"
                    >
                      <el-option
                        v-for="item in voiceOutputProviderOptions"
                        :key="item.id"
                        :label="item.name"
                        :value="item.id"
                      />
                    </el-select>
                  </el-form-item>

                  <el-form-item label="播报模型">
                    <el-select
                      v-model="form.voice_output_model_name"
                      style="width: 100%"
                      clearable
                      placeholder="请选择语音播报模型"
                      :disabled="!selectedVoiceOutputProviderModels.length"
                    >
                      <el-option
                        v-for="item in selectedVoiceOutputProviderModels"
                        :key="`${form.voice_output_provider_id}-${item.name}`"
                        :label="item.name"
                        :value="item.name"
                      />
                    </el-select>
                  </el-form-item>
                </div>

                <el-form-item label="播报音色">
                  <div class="voice-output-voice-field">
                    <el-select
                      v-model="form.voice_output_voice"
                      filterable
                      allow-create
                      default-first-option
                      clearable
                      style="width: 100%"
                      placeholder="选择或直接输入 voice id"
                      :loading="voiceOutputVoiceCatalogLoading"
                    >
                      <el-option
                        v-for="item in normalizedVoiceOutputVoiceOptions"
                        :key="item.voice"
                        :label="item.voice_type ? `${item.voice_name} · ${item.voice_type}` : item.voice_name"
                        :value="item.voice"
                      />
                    </el-select>
                    <el-button
                      text
                      type="primary"
                      :loading="voiceOutputVoiceCatalogLoading"
                      :disabled="!form.voice_output_provider_id"
                      @click="fetchVoiceOutputVoices()"
                    >
                      刷新音色
                    </el-button>
                  </div>
                  <div class="field-desc">
                    {{ voiceOutputVoiceHelperText }}
                  </div>
                </el-form-item>

                <el-form-item label="提醒音量">
                  <el-input-number
                    v-model="form.voice_output_reminder_volume"
                    :min="0"
                    :max="100"
                    :step="5"
                  />
                  <div class="field-desc">
                    后台提醒使用系统原生播报时临时设置的输出音量，默认 40。
                  </div>
                </el-form-item>

                <div class="voice-config-divider" />

                <div class="voice-config-section__head">
                  <div class="employee-skill-site-card__title">首次欢迎语</div>
                  <div class="switch-desc">
                    用户第一次进入系统页面时，全局助手会用这段文案做自我介绍，并准备进入默认实时通话状态。
                  </div>
                </div>

                <div class="switch-card">
                  <div>
                    <div class="switch-title">启用首次欢迎语</div>
                    <div class="switch-desc">
                      关闭后，全局助手仍会自动准备实时通话，但不主动做欢迎介绍。
                    </div>
                  </div>
                  <el-switch v-model="form.global_assistant_greeting_enabled" />
                </div>

                <el-form-item label="欢迎语内容">
                  <el-input
                    v-model="form.global_assistant_greeting_text"
                    type="textarea"
                    :rows="4"
                    resize="vertical"
                    maxlength="1000"
                    show-word-limit
                    placeholder="例如：你好，我是系统状态助手，我会默认保持实时通话，随时帮你观察当前页面和系统状态。"
                  />
                </el-form-item>

                <el-form-item label="助手系统提示词">
                  <el-input
                    v-model="form.global_assistant_system_prompt"
                    type="textarea"
                    :rows="6"
                    resize="vertical"
                    maxlength="8000"
                    show-word-limit
                    placeholder="用于约束全局助手如何回答系统状态、页面和功能相关问题。留空将使用系统内置提示词。"
                  />
                  <div class="field-desc">
                    控制 AI 助手回答时的角色、边界和工具使用策略。
                  </div>
                </el-form-item>

                <el-form-item label="语音转写提示词">
                  <el-input
                    v-model="form.global_assistant_transcription_prompt"
                    type="textarea"
                    :rows="4"
                    resize="vertical"
                    maxlength="1000"
                    show-word-limit
                    placeholder="用于约束语音识别只逐字转写，不补词、不总结。留空将使用系统内置提示词。"
                  />
                  <div class="field-desc">
                    控制语音转写模型如何理解你的录音内容。
                  </div>
                </el-form-item>

                <div class="employee-skill-site-card__grid">
                  <el-form-item label="唤醒语句">
                    <el-input
                      v-model="form.global_assistant_wake_phrase"
                      maxlength="80"
                      show-word-limit
                      placeholder="例如：你好助手"
                    />
                    <div class="field-desc">
                      全局助手处于待机监听时，识别到这句后才会开始接收新指令。
                    </div>
                  </el-form-item>

                  <el-form-item label="空闲待机秒数">
                    <el-input-number
                      v-model="form.global_assistant_idle_timeout_sec"
                      :min="3"
                      :max="30"
                    />
                    <div class="field-desc">
                      实时通话模式下，超过这段时间没有新内容，就自动回到待机并等待下一次唤醒。
                    </div>
                  </el-form-item>
                </div>
              </div>
            </div>
          </el-form>
        </section>

        <section v-show="activeTab === 'ecosystem'" class="panel">
          <div class="panel-head">
            <div>
              <p class="panel-kicker">Discovery</p>
              <h3>外部技能网站目录</h3>
              <p>创建 AI 员工时，这些站点会展示在“外部技能候选”区域。</p>
            </div>
            <div class="panel-actions">
              <el-button @click="addEmployeeExternalSkillSite">新增站点</el-button>
            </div>
          </div>

          <el-form label-position="top" class="switch-form">
            <div class="employee-skill-site-list">
              <div
                v-for="(item, index) in form.employee_external_skill_sites"
                :key="item.id || `site-${index}`"
                class="employee-skill-site-card"
              >
                <div class="employee-skill-site-card__top">
                  <div class="employee-skill-site-card__title">
                    站点 {{ index + 1 }}
                  </div>
                  <div class="employee-skill-site-card__actions">
                    <el-button
                      text
                      type="danger"
                      @click="removeEmployeeExternalSkillSite(index)"
                    >
                      删除
                    </el-button>
                  </div>
                </div>
                <div class="employee-skill-site-card__grid">
                  <el-form-item label="名称">
                    <el-input
                      v-model="item.title"
                      placeholder="例如：Vue 深度应用"
                    />
                  </el-form-item>
                </div>
                <el-form-item label="跳转地址">
                  <el-input
                    v-model="item.url"
                    placeholder="https://example.com/skills/vue"
                  />
                </el-form-item>
                <el-form-item label="描述">
                  <el-input
                    v-model="item.description"
                    type="textarea"
                    :rows="3"
                    resize="vertical"
                    placeholder="简短说明这个站点适合补哪些技能。"
                  />
                </el-form-item>
              </div>
            </div>
          </el-form>
        </section>

        <section v-show="activeTab === 'ecosystem'" class="panel">
          <div class="panel-head">
            <div>
              <p class="panel-kicker">Public</p>
              <h3>官网联系方式</h3>
              <p>官网 `/intro` 会展示这里启用的联系方式，当前先支持 QQ 群。</p>
            </div>
            <div class="panel-actions">
              <el-button @click="addPublicContactChannel">新增联系方式</el-button>
            </div>
          </div>

          <el-form label-position="top" class="switch-form">
            <div class="employee-skill-site-list">
              <div
                v-for="(item, index) in form.public_contact_channels"
                :key="item.id || `contact-${index}`"
                class="employee-skill-site-card"
              >
                <div class="employee-skill-site-card__top">
                  <div class="employee-skill-site-card__title">
                    联系方式 {{ index + 1 }}
                  </div>
                  <div class="employee-skill-site-card__actions">
                    <el-tag size="small" type="info">QQ群</el-tag>
                    <el-button text type="danger" @click="removePublicContactChannel(index)">
                      删除
                    </el-button>
                  </div>
                </div>

                <div class="switch-card">
                  <div>
                    <div class="switch-title">官网展示</div>
                    <div class="switch-desc">
                      关闭后仍保留配置，但官网不会展示这条联系方式。
                    </div>
                  </div>
                  <el-switch v-model="item.enabled" />
                </div>

                <div class="employee-skill-site-card__grid">
                  <el-form-item label="标题">
                    <el-input
                      v-model="item.title"
                      placeholder="例如：加入用户交流群"
                    />
                  </el-form-item>
                  <el-form-item label="QQ群号">
                    <el-input
                      v-model="item.qq_group_number"
                      placeholder="例如：123456789"
                    />
                  </el-form-item>
                  <el-form-item label="排序">
                    <el-input-number
                      v-model="item.sort_order"
                      :min="0"
                      :max="999"
                    />
                  </el-form-item>
                  <el-form-item label="按钮文案">
                    <el-input
                      v-model="item.button_text"
                      placeholder="默认：复制群号"
                    />
                  </el-form-item>
                </div>

                <el-form-item label="描述">
                  <el-input
                    v-model="item.description"
                    type="textarea"
                    :rows="3"
                    resize="vertical"
                    placeholder="简短说明这个 QQ 群适合做什么。"
                  />
                </el-form-item>

                <el-form-item label="加群引导">
                  <el-input
                    v-model="item.guide_text"
                    placeholder="例如：打开 QQ，搜索群号加入。"
                  />
                </el-form-item>

                <div class="employee-skill-site-card__grid">
                  <el-form-item label="加群链接（可选）">
                    <el-input
                      v-model="item.join_link"
                      placeholder="https://qm.qq.com/..."
                    />
                  </el-form-item>
                  <el-form-item label="二维码图片 URL（可选）">
                    <el-input
                      v-model="item.qr_image_url"
                      placeholder="https://example.com/qq-group.png"
                    />
                  </el-form-item>
                </div>
              </div>
            </div>
          </el-form>
        </section>

        <section v-show="activeTab === 'ecosystem'" class="panel">
          <div class="panel-head">
            <div>
              <p class="panel-kicker">Registry</p>
              <h3>技能资源源</h3>
              <p>配置外部技能 registry，安装时再动态换取真实下载地址。</p>
            </div>
          </div>

          <el-form label-position="top" class="switch-form">
            <div class="employee-skill-site-card">
              <div class="switch-card">
                <div>
                  <div class="switch-title">启用 Vett Registry</div>
                  <div class="switch-desc">
                    开启后，前端“技能资源”页面会通过该源搜索和安装技能。
                  </div>
                </div>
                <el-switch v-model="form.skill_registry_sources.vett.enabled" />
              </div>

              <div class="employee-skill-site-card__grid registry-grid">
                <el-form-item label="Base URL">
                  <el-input
                    v-model="form.skill_registry_sources.vett.base_url"
                    placeholder="https://vett.sh/api/v1"
                  />
                </el-form-item>
                <el-form-item label="超时 (ms)">
                  <el-input-number
                    v-model="form.skill_registry_sources.vett.timeout_ms"
                    :min="1000"
                    :max="60000"
                    :step="1000"
                  />
                </el-form-item>
              </div>

              <div class="registry-risk-grid">
                <el-form-item label="允许安装风险">
                  <el-checkbox-group v-model="form.skill_registry_sources.vett.risk_policy.allow">
                    <el-checkbox
                      v-for="item in RISK_LEVEL_OPTIONS"
                      :key="`allow-${item}`"
                      :value="item"
                    >
                      {{ item }}
                    </el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="需人工确认">
                  <el-checkbox-group v-model="form.skill_registry_sources.vett.risk_policy.review">
                    <el-checkbox
                      v-for="item in RISK_LEVEL_OPTIONS"
                      :key="`review-${item}`"
                      :value="item"
                    >
                      {{ item }}
                    </el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="直接拦截">
                  <el-checkbox-group v-model="form.skill_registry_sources.vett.risk_policy.deny">
                    <el-checkbox
                      v-for="item in RISK_LEVEL_OPTIONS"
                      :key="`deny-${item}`"
                      :value="item"
                    >
                      {{ item }}
                    </el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
              </div>
              <div class="field-desc">
                这里保存的是 registry API 地址，不是最终 artifact 下载地址。实际下载链接会在安装时实时换取。
              </div>
            </div>
          </el-form>
        </section>

      </div>

      <aside v-show="activeTab === 'mcp-config'" class="content-aside">
        <section class="panel panel--accent panel--sticky">
          <div class="panel-head">
            <div>
              <p class="panel-kicker">MCP Workspace</p>
              <h3>系统 MCP 配置</h3>
              <p>把服务开关、对外地址和 JSON 编辑器集中到一个独立工作区。</p>
            </div>
            <div class="panel-actions">
              <el-button @click="formatMcpConfigText">格式化 JSON</el-button>
              <el-button @click="resetMcpConfig">恢复默认</el-button>
            </div>
          </div>

          <div class="mcp-summary-grid">
            <article class="mcp-summary-card">
              <span>服务</span>
              <strong>{{ editableMcpServers.length }}</strong>
            </article>
            <article class="mcp-summary-card">
              <span>行数</span>
              <strong>{{ configLineCount }}</strong>
            </article>
            <article class="mcp-summary-card">
              <span>异常</span>
              <strong>{{ totalErrorCount }}</strong>
            </article>
          </div>

          <div class="server-switch-list">
            <div
              v-for="server in editableMcpServers"
              :key="`edit-${server.name}`"
              class="server-switch-item"
            >
              <div class="server-switch-meta">
                <div class="server-switch-name">{{ server.name }}</div>
                <div class="server-switch-url">{{ server.url || "未配置 URL" }}</div>
              </div>
              <div class="server-switch-actions">
                <el-tag size="small" :type="server.enabled ? 'success' : 'info'">
                  {{ server.enabled ? "已启用" : "已停用" }}
                </el-tag>
                <el-switch
                  :model-value="server.enabled"
                  @change="(value) => toggleMcpServer(server.name, value)"
                />
              </div>
            </div>
          </div>

          <el-alert
            v-if="configParseError"
            class="inline-alert"
            type="warning"
            :closable="false"
            show-icon
            :title="configParseError"
          />

          <el-form label-position="top" class="switch-form">
            <div class="employee-skill-site-card voice-config-card">
              <div class="voice-config-section__head">
                <div>
                  <div class="employee-skill-site-card__title">飞书长连接 worker</div>
                  <div class="switch-desc">
                    开启后，后端会托管已配置为长连接且允许托管的飞书机器人 worker；保存配置会立即尝试启动或停止。
                  </div>
                </div>
                <el-switch v-model="form.feishu_bot_long_connection_worker_enabled" />
              </div>
              <div class="field-desc field-desc-block">
                这个开关替代原来的 FEISHU_BOT_LONG_CONNECTION_WORKER_ENABLED 环境变量；仍需要在机器人接入页选择“长连接”并打开对应连接器的 worker 托管开关。
              </div>
            </div>

            <el-form-item label="统一 MCP 对外地址">
              <el-input
                v-model="form.query_mcp_public_base_url"
                placeholder="例如：https://mcp.example.com:9443 或 https://example.com/console"
              />
              <div class="field-desc">
                统一 MCP 接入弹窗会优先使用这里生成 `query-center` 的 SSE / HTTP 地址。留空时，后端会继续按当前请求的 Host 与转发头自动推断。
              </div>
            </el-form-item>

            <el-form-item label="统一查询 MCP 清晰度确认阈值">
              <el-input-number
                v-model="form.query_mcp_clarity_confirm_threshold"
                :min="1"
                :max="5"
                :step="1"
              />
              <div class="field-desc">
                宿主会按 1-5 估计需求清晰度；分数低于该阈值，或存在多种合理理解时，先确认再执行。阈值越高越谨慎，默认 3。
              </div>
            </el-form-item>

            <el-form-item label="CLI Bootstrap 提示词模板">
              <el-input
                v-model="form.query_mcp_bootstrap_prompt_template"
                type="textarea"
                :rows="10"
                resize="vertical"
                placeholder="用于生成对外 CLI 的引导提示词模板。支持 {{clarity_threshold}} / {{project_context_block}} / {{chat_session_block}}。"
              />
              <div class="field-desc">
                用于 `/query-mcp/runtime` 返回的 `cli_prompt`。建议保留 `{{clarity_threshold}}`、`{{project_context_block}}`、`{{chat_session_block}}` 三个变量。
              </div>
            </el-form-item>

            <el-form-item label="Usage Guide 模板">
              <el-input
                v-model="form.query_mcp_usage_guide_template"
                type="textarea"
                :rows="10"
                resize="vertical"
                placeholder="用于生成 query://usage-guide 的模板。支持清晰度相关占位符。"
              />
              <div class="field-desc">
                用于生成 `query://usage-guide`。建议保留 `{{clarity_threshold_line}}`、`{{clarity_direct_line}}`、`{{clarity_confirm_line}}`、`{{clarity_repeat_line}}`。
              </div>
            </el-form-item>

            <el-form-item label="Client Profile 模板">
              <el-input
                v-model="form.query_mcp_client_profile_template"
                type="textarea"
                :rows="6"
                resize="vertical"
                placeholder="用于生成 query://client-profile/* 的模板。支持 {{client_title}} / {{focus_lines}}。"
              />
              <div class="field-desc">
                当前各客户端的差异化内容仍由后端组装，模板只负责最终外层结构。建议保留 `{{client_title}}` 和 `{{focus_lines}}`。
              </div>
            </el-form-item>

            <div class="employee-skill-site-card voice-config-card">
              <div class="voice-config-section__head">
                <div class="employee-skill-site-card__title">回答风格提示</div>
                <div class="switch-desc">
                  控制运行时 `concise / balanced / detailed` 三档回答风格的提示文案。
                </div>
              </div>

              <div
                v-for="styleKey in ['concise', 'balanced', 'detailed']"
                :key="styleKey"
                class="employee-skill-site-card"
              >
                <div class="employee-skill-site-card__title">{{ styleKey }}</div>
                <div class="employee-skill-site-card__grid">
                  <el-form-item label="风格提示">
                    <el-input
                      v-model="form.chat_style_hints[styleKey].style_hint"
                      type="textarea"
                      :rows="2"
                      resize="vertical"
                    />
                  </el-form-item>
                  <el-form-item label="结论优先顺序提示">
                    <el-input
                      v-model="form.chat_style_hints[styleKey].order_hint"
                      type="textarea"
                      :rows="2"
                      resize="vertical"
                    />
                  </el-form-item>
                </div>
              </div>
            </div>
          </el-form>

          <div class="editor-shell">
            <div class="editor-toolbar">
              <span>mcpServers.json</span>
              <span class="editor-meta">{{ configLineCount }} 行</span>
            </div>
            <el-input
              v-model="form.mcp_config_text"
              type="textarea"
              :rows="16"
              spellcheck="false"
              resize="none"
              class="mcp-config-input"
            />
          </div>
          <p class="field-desc field-desc-block">
            当前页面会基于这里的 `url` 自动调用
            `tools/list`、`prompts/list`、`resources/list` 进行探测。
          </p>
        </section>
      </aside>
    </div>

    <section v-show="activeTab === 'mcp-discovery'" class="panel skill-panel">
      <div class="panel-head">
        <div>
          <h3>当前 MCP 技能</h3>
          <p>
            下方展示每个系统级 MCP 服务返回的能力列表，以及每次探测的技术结果。
          </p>
        </div>
      </div>

      <div v-loading="skillsLoading" class="server-list">
        <el-empty
          v-if="!mcpServers.length && !skillsLoading"
          description="暂无可展示的 MCP 服务"
          :image-size="64"
        />

        <article
          v-for="server in mcpServers"
          :key="server.name"
          class="server-card"
        >
          <div class="server-head">
            <div>
              <div class="server-title-row">
                <h4>{{ server.name }}</h4>
                <el-tag
                  size="small"
                  :type="!server.enabled ? 'info' : server.errors?.length ? 'warning' : 'success'"
                >
                  {{ !server.enabled ? "已停用" : server.errors?.length ? "探测异常" : "正常" }}
                </el-tag>
              </div>
              <p class="server-url">{{ server.url || "未配置 URL" }}</p>
            </div>
            <div class="server-summary">{{ server.summary || "未探测" }}</div>
          </div>

          <div class="capsule-row">
            <span class="capsule capsule-tool"
              >Tools {{ server.tools?.length || 0 }}</span
            >
            <span class="capsule capsule-prompt"
              >Prompts {{ server.prompts?.length || 0 }}</span
            >
            <span class="capsule capsule-resource"
              >Resources {{ server.resources?.length || 0 }}</span
            >
            <span
              v-if="server.source === 'documentation_fallback'"
              class="capsule capsule-fallback"
              >文档兜底</span
            >
          </div>

          <el-alert
            v-if="server.notice"
            class="server-notice"
            type="info"
            :closable="false"
            show-icon
            :title="server.notice"
          />

          <div class="skill-section-grid">
            <div class="skill-box">
              <div class="skill-box-title">Tools</div>
              <div v-if="server.tools?.length" class="skill-list">
                <div
                  v-for="item in server.tools"
                  :key="`tool-${server.name}-${item.name}`"
                  class="skill-item"
                >
                  <span class="skill-name">{{ item.name }}</span>
                  <span v-if="item.description" class="skill-desc">{{
                    item.description
                  }}</span>
                </div>
              </div>
              <div v-else class="skill-empty">暂无 tools</div>
            </div>

            <div class="skill-box">
              <div class="skill-box-title">Prompts</div>
              <div v-if="server.prompts?.length" class="skill-list">
                <div
                  v-for="item in server.prompts"
                  :key="`prompt-${server.name}-${item.name}`"
                  class="skill-item"
                >
                  <span class="skill-name">{{ item.name }}</span>
                  <span v-if="item.description" class="skill-desc">{{
                    item.description
                  }}</span>
                </div>
              </div>
              <div v-else class="skill-empty">暂无 prompts</div>
            </div>

            <div class="skill-box">
              <div class="skill-box-title">Resources</div>
              <div v-if="server.resources?.length" class="skill-list">
                <div
                  v-for="item in server.resources"
                  :key="`resource-${server.name}-${item.name}`"
                  class="skill-item"
                >
                  <span class="skill-name">{{ item.name }}</span>
                  <span v-if="item.description" class="skill-desc">{{
                    item.description
                  }}</span>
                </div>
              </div>
              <div v-else class="skill-empty">暂无 resources</div>
            </div>
          </div>

          <div v-if="server.checks?.length" class="check-block">
            <div class="check-title">探测结果</div>
            <div class="check-list">
              <div
                v-for="check in server.checks"
                :key="`${server.name}-${check.method}`"
                class="check-item"
              >
                <div class="check-item-top">
                  <div class="check-method">{{ check.method }}</div>
                  <el-tag size="small" :type="check.ok ? 'success' : 'danger'">
                    {{ check.ok ? "成功" : "失败" }}
                  </el-tag>
                </div>
                <div class="check-message">
                  {{ check.message || "无返回信息" }}
                </div>
                <pre v-if="check.body_preview" class="check-preview">{{
                  check.body_preview
                }}</pre>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";
import api from "@/utils/api.js";
import { resolveSettingsAwarePath } from "@/utils/chat-settings-route.js";

const DEFAULT_MCP_CONFIG = {
  mcpServers: {
    "prompts.chat": {
      url: "https://prompts.chat/api/mcp",
      enabled: true,
    },
  },
};
const DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT =
  "你好，我是系统状态助手。我会默认保持实时通话，随时帮你观察当前页面、系统状态和功能是否可用。";
const DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT = `你是系统状态助手。
你的职责是基于当前页面、实时系统快照和本轮对话消息，直接回答系统状态、当前页面、当前项目、当前账号、功能可用性相关问题。
你已经拿到本轮对话历史和实时快照；禁止回答“我无法访问之前的对话历史”或“我没有上下文”。
如果答案就在本轮消息或快照里，直接给结论；如果快照里没有，就明确说明“当前快照里没有这项数据”，并指出缺少什么信息。
不要把用户打回去重新描述，除非用户问题本身含糊到无法判断目标。
当用户询问这个系统做什么、有哪些功能、怎么使用、去哪里配置、哪个页面负责什么时，先调用 global_assistant_system_guide 再回答。
当用户询问当前页面接口状态、最近请求、响应数据、报错接口或页面是否真的拿到数据时，优先调用 global_assistant_browser_requests。
当用户要求你检查页面元素、读取页面文字、点击、输入、选择、滚动、按键、切换页面、跳转路由或直接执行页面脚本时，优先调用 global_assistant_browser_actions。
执行 click、fill、select 前，如果页面里是图标按钮或存在多个相邻按钮，先用 query_dom 查看候选元素，并优先使用 data-testid、id、aria-label、title 这些唯一标识来构造 selector；不要猜测或使用过宽的 .el-button、button:nth-child(...) 之类 selector。`;
const DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT =
  "请严格逐字转写用户原话，只输出识别到的中文文本；不要补充、不要改写、不要总结、不要猜测、不要重复上一句；听不清就留空。";
const DEFAULT_SKILL_REGISTRY_SOURCES = {
  vett: {
    enabled: true,
    base_url: "https://vett.sh/api/v1",
    timeout_ms: 10000,
    risk_policy: {
      allow: ["none", "low", "medium"],
      review: ["high"],
      deny: ["critical"],
    },
  },
};
const DEFAULT_BOT_PLATFORM_CONNECTORS = [];
const DEFAULT_PUBLIC_CONTACT_CHANNELS = [];
const DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT =
  "基于员工职责、目标、技能建议和 prompts.chat MCP 相关能力，为员工自动补全 1 到 3 条可直接落地的执行规则。优先生成问题排查、输出规范、风险控制、技术选型相关规则；规则内容必须具体、可执行、可绑定。";
const DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE = `你已接入统一查询 MCP。

详细规则不要直接内联到宿主提示词；但开始执行前必须按需读取这些资源：
- \`query://usage-guide\`
- \`query://client-profile/codex\`

强制接入步骤：
1. 先读取 \`query://usage-guide\`；当前是 Codex CLI 时，再读取 \`query://client-profile/codex\`。
2. 初始化不是只检查技能；先以当前 CLI 工作区为准，显式初始化本地 \`.ai-employee/\`，至少确保 \`.ai-employee/skills/\`、\`.ai-employee/query-mcp/active-sessions/\`、\`.ai-employee/query-mcp/active/\`、\`.ai-employee/query-mcp/session-history/\` 与 \`.ai-employee/requirements/<project_id>/\` 可用。
3. 再检查 \`.ai-employee/skills/query-mcp-workflow/\` 是否已存在；缺失时先通过 MCP 从服务端技能库同步或创建到当前工作区，已存在则直接复用，禁止重复创建。
4. 通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 \`.ai-employee/skills/query-mcp-workflow/\`；核心文件优先读取本地副本中的 \`SKILL.md\` 与 \`manifest.json\`。只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 \`mcp-skills/knowledge/skills/query-mcp-workflow.json\` 与 \`mcp-skills/knowledge/skill-packages/query-mcp-workflow/\` 作为回源比对位置。
5. 若系统曾把 \`.ai-employee\` 或 \`query-mcp-workflow\` 隐式落到其他子目录，只能视为历史状态，不能替代当前 CLI 工作区初始化；当前入口仍要在当前工作区补齐。
6. 若当前任务是更新工作流规范或技能包，优先在本地技能副本、提示词模板和同步策略上修改；只有本地缺失或需要回源比对时，才从服务端技能库同步。
7. 实现型需求优先调用 \`start_project_workflow(...)\` 作为固定入口；若宿主暂不适合走固定入口，至少按 \`search_ids -> get_manual_content -> analyze_task -> resolve_relevant_context -> generate_execution_plan\` 的顺序补齐前置步骤。
8. 仅在缺少明确的 \`project_id\` / \`employee_id\` / \`rule_id\`，或需要跨项目检索时，再调用 \`search_ids(keyword="<用户原始问题>")\`；已明确当前项目且在项目内执行时可直接读取上下文或进入本地实现。
9. 不要依赖 description、项目说明或“当前项目”文字做绑定；如需项目绑定或续接任务树，显式调用 \`bind_project_context(...)\`。
10. 当前任务先在项目本地推进：先在工作区完成分析、改动、验证和本地记录，再通过 MCP 回写任务树、工作事实、交付结论或记忆到服务端。
11. 每个需求必须维护 1 个本地 requirement 对象；项目工作区可解析时，写入 \`.ai-employee/requirements/<project_id>/<chat_session_id>.json\`。对象内至少保留 \`workflow_skill\`、\`record_path\`、\`storage_scope\`、\`task_tree\`、\`current_task_node\`、\`task_branches\`、\`history\` 等字段，避免只在服务端推进看不到本地状态。
12. 当前全局清晰度确认阈值为 {{clarity_threshold}}/5；先按 1-5 分估计用户需求清晰度。
13. 若目标、对象、范围和预期结果足够清晰，且清晰度分数 >= {{clarity_threshold}}，直接处理，不主动要求确认计划。
14. 若清晰度分数 < {{clarity_threshold}}、需求表述模糊、对象或范围不明确，或存在两种及以上合理理解，先输出你的理解、计划摘要和可能误解点，再请求用户确认后再执行；同一轮已确认后不要重复确认；查询型、客服型问题不要默认升级成计划审批流程。
15. 长任务先调用 \`start_work_session\` 获取 \`session_id\`，后续复用同一个 \`chat_session_id/session_id\`，并用 \`save_work_facts\`、\`append_session_event\` 维护轨迹。
16. 如宿主支持任务树，\`bind_project_context(...)\` 后立刻读取 \`get_current_task_tree\`，核对 \`root_goal/title/current_node\` 是否属于当前问题；若明显属于旧任务树，停止复用当前 \`chat_session_id\`，改为新建并持久化新的 \`chat_session_id\` 后重新绑定。
17. 真正进入执行前，再读取一次 \`get_current_task_tree\` 确认当前节点；开始节点用 \`update_task_node_status\`，完成节点必须用 \`complete_task_node_with_verification\` 补验证结果后再结束。
18. 如果当前宿主拿不到上述任务树工具，只能明确说明“任务树闭环未完成”，不要把自然语言进度当成已闭环。

当前接入上下文：
{{project_context_block}}
{{chat_session_block}}
- \`chat_session_id\` 生成后要立即持久化；优先写项目目录 \`.ai-employee/query-mcp/active-sessions/<chat_session_id>.json\`，并同步维护 \`.ai-employee/query-mcp/active/<project_id>.json\` 与 \`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json\`。
- requirement 本地对象与 query-mcp canonical 状态要同时维护；不要只写 session 文件而缺失 \`.ai-employee/requirements/<project_id>/<chat_session_id>.json\`。
- 如果自动 bootstrap 把状态写到了别的服务子目录，不能把它当成当前仓库根目录已初始化；入口提示词必须以当前 CLI 工作区为准重新核对。
- 若当前还没有 \`session_id\`，调用 \`start_work_session\` 后也要立刻持久化；中断恢复顺序固定为 \`bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)\`。
- 若项目工作区不可解析，再退回当前 CLI 自己的本地存储；不要新写 \`current-session.json\`、\`chat_session_id.txt\`、\`session_id.txt\`、\`session.env\` 这类 legacy 文件。

回答要求：
- 先基于 MCP 查询结果和本地技能内容回答，不要把猜测写成事实。
- 若信息来自 MCP，尽量保留对应的项目 / 员工 / 规则 ID，方便追溯。
- 若引用技能内容，优先注明技能 ID、包路径或本地目录位置，方便追溯。
- 若入口文件或宿主系统还有额外约束，优先遵守宿主入口文件约定。`;
const DEFAULT_QUERY_MCP_USAGE_GUIDE_TEMPLATE = `# Unified Query MCP

- 统一入口路径: /mcp/query
- 目标: 提供项目/员工/规则查询、任务分析、上下文聚合、执行规划、任务树推进、工作轨迹、需求历史查询和交付报告能力。
- 推荐工具: start_project_workflow / bind_project_context / search_ids / get_content / get_manual_content / analyze_task / resolve_relevant_context / generate_execution_plan / get_current_task_tree / update_task_node_status / complete_task_node_with_verification / classify_command_risk / check_workspace_scope / resolve_execution_mode / check_operation_policy / start_work_session / save_work_facts / append_session_event / resume_work_session / summarize_checkpoint / list_recent_project_requirements / get_requirement_history / build_delivery_report / generate_release_note_entry / save_project_memory

## 最少执行规则
1. 先读取 query://usage-guide；当前是 Codex / Claude 这类代码 CLI 时，再补读 query://client-profile/codex 或 query://client-profile/claude-code。
1.1 实现型需求优先调用 start_project_workflow(...) 作为固定入口，不要手动拼接十几个前置查询步骤。
1.2 统一查询工作流默认先检查项目本地 \`.ai-employee/skills/query-mcp-workflow/\`；若不存在，再从系统技能库同步或创建到本地；已存在则直接复用，禁止重复创建。
1.3 通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 \`.ai-employee/skills/query-mcp-workflow/\`；优先读取本地副本中的 \`SKILL.md\` 与 \`manifest.json\`。只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 \`mcp-skills/knowledge/skills/query-mcp-workflow.json\` 与 \`mcp-skills/knowledge/skill-packages/query-mcp-workflow/\` 作为回源比对位置。
2. MCP 配置里的 description、项目说明和“当前项目”这类文字都不参与真正绑定；真正生效的是 URL 里的 project_id / chat_session_id 默认上下文，以及 bind_project_context(...) 写入的 MCP 会话绑定。
3. 若接入地址缺少 project_id，或需要续接任务树但缺少 chat_session_id，首轮立即调用 bind_project_context(project_id, chat_session_id?, root_goal?)；不要只依赖 description 里的项目说明。
4. 如果当前 CLI 没有活跃 MCP session，只要显式传了 project_id + chat_session_id，bind_project_context(...) 也会走 detached 绑定并先建任务树；后续所有工具继续显式复用同一个 chat_session_id。
4.0 如果 direct CLI fallback 已先生成临时 \`query-cli.*\` 会话，后续再用显式 \`cli.*\` 会话调用 bind_project_context(...) 时，系统会自动把影子任务树迁到正式会话；但最佳实践仍然是首轮就传稳定 chat_session_id。
4.1 每个 CLI 会话都应持久化自己生成的 chat_session_id；如能解析项目工作区，优先写到项目目录 \`.ai-employee/query-mcp/\`，否则再退回 CLI 自己的本地存储。同一轮任务固定复用，只有新开的并行 CLI 或全新任务才重新生成。
4.2 query-mcp 本地持久化必须使用唯一文件规范：每进程会话文件为 \`.ai-employee/query-mcp/active-sessions/<chat_session_id>.json\`（每个 CLI 进程写自己的独立文件，避免多进程冲突）；项目级权威状态文件为 \`.ai-employee/query-mcp/active/<project_id>.json\` 与 \`.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json\`。除兼容历史数据时只读外，禁止新写 \`current-session.json\`、\`chat_session_id.txt\`、\`session_id.txt\`、\`chat_session_id\`、\`session_id\`、\`session.env\`、\`current-query-session.json\`、\`current-work-session.json\` 这类分叉文件。
4.3 每个需求还必须单独维护 \`.ai-employee/requirements/<project_id>/<chat_session_id>.json\`；一条需求一个对象，不要把多个需求混写到同一聚合文件。
4.4 requirement 对象应至少记录 \`workflow_skill\`、\`record_path\`、\`storage_scope\`、\`task_tree\`、\`current_task_node\`、\`task_branches\`、\`history\`，保证本地推进和服务端任务树都能追溯到同一条需求。
5. type=sse 的客户端可能直接使用 POST /mcp/query/sse 作为 JSON-RPC bridge，而不是先 GET /sse 再 /messages；这类接法若要自动创建项目任务树，首轮也必须显式提供 project_id，建议同时提供 chat_session_id 并调用 bind_project_context。
6. 仅在缺少明确的 project_id / employee_id / rule_id，或需要跨项目检索时，再调用 search_ids(keyword="<用户原始问题>")；已明确当前项目且在项目内执行时，可直接 get_manual_content、start_project_workflow 或进入本地实现。
7. 需要规则或项目上下文时，先 get_manual_content，再按需调用 get_content；不要跳过 ID 定位直接臆造项目、员工、规则 ID。
7.0 项目型问题优先使用项目绑定员工、规则和技能；先判断项目内现成能力能否闭环，只有项目能力不足时才自行补足。
7.0.1 每次新请求进入分析、实现或排查前，重新获取与当前任务直接相关的规则正文；不要只看规则标题，也不要把无关规则机械带入当前问题。
7.0.2 实现型任务先在项目本地推进：先完成本地分析、改动、验证和 requirement 记录，再通过 MCP 回写任务树、工作事实、交付结论与记忆。
7.0.3 {{clarity_threshold_line}}
7.0.4 {{clarity_direct_line}}
7.0.5 {{clarity_confirm_line}}
7.0.6 {{clarity_repeat_line}}
7.1 记忆检索不是每轮固定步骤；仅在新需求开始、续跑恢复、修复旧问题或当前问题明显依赖历史经验时，再调用 recall_project_memory 或 recall_employee_memory。
7.2 同一任务轮若已生成任务树并进入执行，后续默认依赖当前会话、任务树和工作轨迹，不要重复检索同一批项目记忆。`;
const DEFAULT_QUERY_MCP_CLIENT_PROFILE_TEMPLATE = `# {{client_title}} Client Profile

{{focus_lines}}`;
const DEFAULT_CHAT_STYLE_HINTS = {
  concise: {
    style_hint: "输出风格：简洁，避免冗长。",
    order_hint: "回答顺序：先给结论再给步骤。",
  },
  balanced: {
    style_hint: "输出风格：平衡，先结论后关键步骤。",
    order_hint: "回答顺序：先给结论再给步骤。",
  },
  detailed: {
    style_hint: "输出风格：详细，覆盖关键前提、步骤与风险。",
    order_hint: "回答顺序：先给结论再给步骤。",
  },
};
const SYSTEM_CONFIG_TAB_NAMES = [
  "defaults",
  "assistant",
  "ecosystem",
  "mcp-config",
  "mcp-discovery",
];
const EMPLOYEE_AUTO_RULE_SOURCE_OPTIONS = [
  {
    label: "prompts.chat curated 规则源",
    value: "prompts_chat_curated",
  },
];
const RISK_LEVEL_OPTIONS = ["none", "low", "medium", "high", "critical"];
const DESKTOP_ARTIFACT_TARGET_OPTIONS = [
  {
    label: "Windows 安装版",
    value: "windows:setup",
    platform: "windows",
    variant: "setup",
    accept: ".exe",
    hint: "上传 `.exe` 安装包。新文件会覆盖之前的 Windows 安装版。",
  },
  {
    label: "Windows 便携版",
    value: "windows:portable",
    platform: "windows",
    variant: "portable",
    accept: ".exe",
    hint: "上传 `.exe` 便携包。新文件会覆盖之前的 Windows 便携版。",
  },
  {
    label: "macOS 安装包",
    value: "macos:dmg",
    platform: "macos",
    variant: "dmg",
    accept: ".dmg",
    hint: "上传 `.dmg` 文件。新文件会覆盖之前的 macOS 安装包。",
  },
];

function cloneConfig(value) {
  return JSON.parse(JSON.stringify(value));
}

const loading = ref(false);
const saving = ref(false);
const activeTab = ref("defaults");
const route = useRoute();
const router = useRouter();
const skillsLoading = ref(false);
const connectorsLoading = ref(false);
const uploadingDesktopArtifact = ref(false);
const downloadingDesktopArtifactKey = ref("");
const deletingConnectorId = ref("");
const connectorShareOptionsLoading = ref(false);
const savingConnectorLlmSharing = ref(false);
const refreshingPanels = ref(false);
const mcpServers = ref([]);
const connectorItems = ref([]);
const desktopArtifactItems = ref([]);
const desktopArtifactUploadRef = ref(null);
const desktopArtifactUploadFile = ref(null);
const desktopArtifactUploadFileList = ref([]);
const showConnectorLlmSharingDialog = ref(false);
const connectorShareUserOptions = ref([]);
const connectorShareRoleOptions = ref([]);
const globalAssistantChatProviderOptions = ref([]);
const voiceProviderOptions = ref([]);
const voiceUserOptions = ref([]);
const voiceRoleOptions = ref([]);
const voiceOutputProviderOptions = ref([]);
const voiceOutputVoiceOptions = ref([]);
const projectOptions = ref([]);
const voiceOutputVoiceCatalogLoading = ref(false);
const voiceOutputVoiceCatalogMessage = ref("");
const desktopArtifactUploadForm = ref({
  target: "windows:setup",
  version: "",
});
const connectorLlmSharingForm = ref({
  connector_id: "",
  connector_name: "",
  llm_shared_with_usernames: [],
  llm_shared_with_roles: [],
});

const form = ref({
  enable_project_manual_generation: false,
  enable_employee_manual_generation: false,
  chat_upload_max_limit: 6,
  chat_max_tokens: 512,
  default_chat_system_prompt: "",
  employee_auto_rule_generation_enabled: true,
  employee_auto_rule_generation_source_filters: ["prompts_chat_curated"],
  employee_auto_rule_generation_max_count: 3,
  employee_auto_rule_generation_prompt:
    DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT,
  employee_external_skill_sites: [],
  voice_input_enabled: false,
  voice_input_provider_id: "",
  voice_input_model_name: "",
  voice_input_allowed_usernames: [],
  voice_input_allowed_role_ids: [],
  voice_output_enabled: false,
  voice_output_provider_id: "",
  voice_output_model_name: "",
  voice_output_voice: "",
  voice_output_reminder_volume: 40,
  global_assistant_enabled: true,
  global_assistant_greeting_enabled: true,
  global_assistant_greeting_text: DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
  global_assistant_chat_provider_id: "",
  global_assistant_chat_model_name: "",
  global_assistant_system_prompt: DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT,
  global_assistant_transcription_prompt:
    DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
  global_assistant_wake_phrase: "你好助手",
  global_assistant_idle_timeout_sec: 5,
  bot_platform_connectors: cloneConfig(DEFAULT_BOT_PLATFORM_CONNECTORS),
  feishu_bot_long_connection_worker_enabled: false,
  public_contact_channels: cloneConfig(DEFAULT_PUBLIC_CONTACT_CHANNELS),
  query_mcp_public_base_url: "",
  query_mcp_clarity_confirm_threshold: 3,
  query_mcp_bootstrap_prompt_template:
    DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE,
  query_mcp_usage_guide_template: DEFAULT_QUERY_MCP_USAGE_GUIDE_TEMPLATE,
  query_mcp_client_profile_template:
    DEFAULT_QUERY_MCP_CLIENT_PROFILE_TEMPLATE,
  chat_style_hints: cloneConfig(DEFAULT_CHAT_STYLE_HINTS),
  skill_registry_sources: cloneConfig(DEFAULT_SKILL_REGISTRY_SOURCES),
  mcp_config_text: JSON.stringify(DEFAULT_MCP_CONFIG, null, 2),
});

const totalSkillCount = computed(() =>
  mcpServers.value.reduce(
    (sum, item) =>
      sum +
      Number(item?.tools?.length || 0) +
      Number(item?.prompts?.length || 0) +
      Number(item?.resources?.length || 0),
    0,
  ),
);

const totalErrorCount = computed(() =>
  mcpServers.value.reduce(
    (sum, item) => sum + Number(item?.errors?.length || 0),
    0,
  ),
);
const onlineConnectorCount = computed(
  () => connectorItems.value.filter((item) => item?.online).length,
);
const selectedDesktopArtifactTarget = computed(() =>
  DESKTOP_ARTIFACT_TARGET_OPTIONS.find(
    (item) => item.value === desktopArtifactUploadForm.value.target,
  ) || DESKTOP_ARTIFACT_TARGET_OPTIONS[0],
);
const desktopArtifactUploadAccept = computed(
  () => selectedDesktopArtifactTarget.value?.accept || ".exe,.dmg",
);
const canUploadDesktopArtifact = computed(
  () =>
    !!desktopArtifactUploadFile.value &&
    !!String(desktopArtifactUploadForm.value.version || "").trim() &&
    !!selectedDesktopArtifactTarget.value,
);

const configLineCount = computed(
  () => String(form.value.mcp_config_text || "").split("\n").length,
);
const configParseError = computed(() => {
  try {
    parseMcpConfigText();
    return "";
  } catch (err) {
    return String(err?.message || "MCP 配置格式错误");
  }
});
const editableMcpServers = computed(() => {
  try {
    const parsed = parseMcpConfigText();
    const servers = parsed?.mcpServers;
    if (!servers || typeof servers !== "object" || Array.isArray(servers)) {
      return [];
    }
    return Object.entries(servers)
      .map(([name, value]) => ({
        name: String(name || "").trim(),
        url:
          value && typeof value === "object" && !Array.isArray(value)
            ? String(value.url || "").trim()
            : "",
        enabled:
          !(value && typeof value === "object" && !Array.isArray(value)) ||
          Boolean(value.enabled ?? true),
      }))
      .filter((item) => item.name);
  } catch {
    return [];
  }
});
const selectedVoiceProvider = computed(
  () =>
    voiceProviderOptions.value.find(
      (item) => item.id === form.value.voice_input_provider_id,
    ) || null,
);
const selectedGlobalAssistantChatProvider = computed(
  () =>
    globalAssistantChatProviderOptions.value.find(
      (item) => item.id === form.value.global_assistant_chat_provider_id,
    ) || null,
);
const selectedGlobalAssistantChatProviderModels = computed(() =>
  Array.isArray(selectedGlobalAssistantChatProvider.value?.model_configs)
    ? selectedGlobalAssistantChatProvider.value.model_configs
    : [],
);
const selectedVoiceProviderModels = computed(() =>
  Array.isArray(selectedVoiceProvider.value?.model_configs)
    ? selectedVoiceProvider.value.model_configs
    : [],
);
const selectedVoiceOutputProvider = computed(
  () =>
    voiceOutputProviderOptions.value.find(
      (item) => item.id === form.value.voice_output_provider_id,
    ) || null,
);
const selectedVoiceOutputProviderModels = computed(() =>
  Array.isArray(selectedVoiceOutputProvider.value?.model_configs)
    ? selectedVoiceOutputProvider.value.model_configs
    : [],
);
const normalizedVoiceOutputVoiceOptions = computed(() => {
  const items = [];
  const seen = new Set();
  for (const rawItem of Array.isArray(voiceOutputVoiceOptions.value) ? voiceOutputVoiceOptions.value : []) {
    const voice = String(rawItem?.voice || "").trim();
    if (!voice || seen.has(voice)) {
      continue;
    }
    seen.add(voice);
    items.push({
      voice,
      voice_name: String(rawItem?.voice_name || voice).trim(),
      voice_type: String(rawItem?.voice_type || "").trim(),
    });
  }
  const currentVoice = String(form.value.voice_output_voice || "").trim();
  if (currentVoice && !seen.has(currentVoice)) {
    items.unshift({
      voice: currentVoice,
      voice_name: currentVoice,
      voice_type: "",
    });
  }
  return items;
});
const voiceOutputVoiceHelperText = computed(() => {
  const message = String(voiceOutputVoiceCatalogMessage.value || "").trim();
  if (message) return message;
  if (!String(form.value.voice_output_provider_id || "").trim()) {
    return "先选择播报供应商，再读取可用音色。";
  }
  if (normalizedVoiceOutputVoiceOptions.value.length) {
    return "优先选择系统读取到的音色；如果供应商未返回列表，也可以直接输入 voice id。";
  }
  return "如果当前供应商不支持音色目录接口，可直接手动输入 voice id。";
});
function normalizeEmployeeExternalSkillSites(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  const items = [];
  const seen = new Set();
  for (const rawItem of value) {
    if (!rawItem || typeof rawItem !== "object" || Array.isArray(rawItem)) {
      continue;
    }
    const item = {
      id: String(rawItem.id || "").trim().slice(0, 80),
      title: String(rawItem.title || "").trim().slice(0, 120),
      description: String(rawItem.description || "").trim().slice(0, 280),
      url: String(rawItem.url || "").trim().slice(0, 500),
    };
    const dedupeKey = (
      item.id ||
      item.title ||
      item.url ||
      `site-${items.length + 1}`
    ).toLowerCase();
    if (!dedupeKey || seen.has(dedupeKey)) {
      continue;
    }
    seen.add(dedupeKey);
    items.push(item);
    if (items.length >= 20) {
      break;
    }
  }
  return items;
}

function normalizePublicContactChannels(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  const items = [];
  const seen = new Set();
  for (const rawItem of value) {
    if (!rawItem || typeof rawItem !== "object" || Array.isArray(rawItem)) {
      continue;
    }
    const qqGroupNumber = String(rawItem.qq_group_number || "")
      .replace(/\D+/g, "")
      .slice(0, 32);
    const sortOrder = Math.min(
      999,
      Math.max(0, Number(rawItem.sort_order || 0)),
    );
    const item = {
      id: String(rawItem.id || "").trim().slice(0, 80),
      enabled: rawItem.enabled !== false,
      type: "qq_group",
      title: String(rawItem.title || "").trim().slice(0, 120),
      description: String(rawItem.description || "").trim().slice(0, 280),
      qq_group_number: qqGroupNumber,
      button_text: String(rawItem.button_text || "").trim().slice(0, 40),
      guide_text: String(rawItem.guide_text || "").trim().slice(0, 160),
      join_link: String(rawItem.join_link || "").trim().slice(0, 500),
      qr_image_url: String(rawItem.qr_image_url || "").trim().slice(0, 500),
      sort_order: Number.isFinite(sortOrder) ? sortOrder : 0,
    };
    const dedupeKey = (
      item.id ||
      item.qq_group_number ||
      item.title ||
      `contact-${items.length + 1}`
    ).toLowerCase();
    if (!dedupeKey || seen.has(dedupeKey)) {
      continue;
    }
    seen.add(dedupeKey);
    items.push(item);
    if (items.length >= 10) {
      break;
    }
  }
  return items;
}

function normalizeBotConnectorId(value, fallback) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 80);
  return normalized || fallback;
}

function normalizeBotPlatformConnectors(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  const items = [];
  const seen = new Set();
  for (const rawItem of value) {
    if (!rawItem || typeof rawItem !== "object" || Array.isArray(rawItem)) {
      continue;
    }
    const platform = String(rawItem.platform || "").trim().toLowerCase();
    if (!["qq", "feishu", "wechat"].includes(platform)) {
      continue;
    }
    const id = normalizeBotConnectorId(
      rawItem.id,
      `${platform}-connector-${items.length + 1}`,
    );
    if (seen.has(id)) {
      continue;
    }
    seen.add(id);
    items.push({
      id,
      enabled: rawItem.enabled !== false,
      platform,
      name: String(rawItem.name || "").trim().slice(0, 120),
      agent_name: String(rawItem.agent_name || "").trim().slice(0, 120),
      description: String(rawItem.description || "").trim().slice(0, 280),
      app_id: String(rawItem.app_id || "").trim().slice(0, 160),
      app_secret: String(rawItem.app_secret || "").trim().slice(0, 200),
      verification_token: String(rawItem.verification_token || "").trim().slice(0, 200),
      encrypt_key: String(rawItem.encrypt_key || "").trim().slice(0, 200),
      project_id: String(rawItem.project_id || "").trim().slice(0, 80),
      guide_url: String(rawItem.guide_url || "").trim().slice(0, 500),
      sort_order: Math.min(
        999,
        Math.max(0, Number(rawItem.sort_order || 0) || 0),
      ),
    });
  }
  return items.sort(
    (a, b) =>
      a.sort_order - b.sort_order ||
      a.platform.localeCompare(b.platform) ||
      String(a.name || "").localeCompare(String(b.name || "")) ||
      a.id.localeCompare(b.id),
  );
}

function normalizeRiskLevelList(value, fallback = []) {
  if (!Array.isArray(value)) {
    return [...fallback];
  }
  const items = [];
  const seen = new Set();
  for (const rawItem of value) {
    const item = String(rawItem || "").trim().toLowerCase();
    if (!item || seen.has(item)) {
      continue;
    }
    seen.add(item);
    items.push(item);
  }
  return items.length ? items : [...fallback];
}

function normalizeSkillRegistrySources(value) {
  const defaults = cloneConfig(DEFAULT_SKILL_REGISTRY_SOURCES);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return defaults;
  }
  const rawVett =
    value.vett && typeof value.vett === "object" && !Array.isArray(value.vett)
      ? value.vett
      : {};
  const rawPolicy =
    rawVett.risk_policy &&
    typeof rawVett.risk_policy === "object" &&
    !Array.isArray(rawVett.risk_policy)
      ? rawVett.risk_policy
      : {};
  return {
    vett: {
      enabled: rawVett.enabled !== false,
      base_url:
        String(rawVett.base_url || defaults.vett.base_url).trim() ||
        defaults.vett.base_url,
      timeout_ms: Math.min(
        60000,
        Math.max(1000, Number(rawVett.timeout_ms || defaults.vett.timeout_ms)),
      ),
      risk_policy: {
        allow: normalizeRiskLevelList(
          rawPolicy.allow,
          defaults.vett.risk_policy.allow,
        ),
        review: normalizeRiskLevelList(
          rawPolicy.review,
          defaults.vett.risk_policy.review,
        ),
        deny: normalizeRiskLevelList(
          rawPolicy.deny,
          defaults.vett.risk_policy.deny,
        ),
      },
    },
  };
}

function normalizeStringList(value) {
  return Array.isArray(value)
    ? Array.from(
        new Set(
          value
            .map((item) => String(item || "").trim())
            .filter(Boolean),
        ),
      )
    : [];
}

function normalizeChatStyleHints(value) {
  const source =
    value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const normalized = {};
  for (const [key, defaults] of Object.entries(DEFAULT_CHAT_STYLE_HINTS)) {
    const item =
      source[key] && typeof source[key] === "object" && !Array.isArray(source[key])
        ? source[key]
        : {};
    normalized[key] = {
      style_hint: String(item.style_hint || defaults.style_hint).trim(),
      order_hint: String(item.order_hint || defaults.order_hint).trim(),
    };
  }
  return normalized;
}

function addEmployeeExternalSkillSite() {
  form.value.employee_external_skill_sites = [
    ...normalizeEmployeeExternalSkillSites(form.value.employee_external_skill_sites),
    {
      id: `site-${Date.now()}`,
      title: "",
      description: "",
      url: "",
    },
  ];
}

function addPublicContactChannel() {
  form.value.public_contact_channels = [
    ...normalizePublicContactChannels(form.value.public_contact_channels),
    {
      id: `contact-${Date.now()}`,
      enabled: true,
      type: "qq_group",
      title: "",
      description: "",
      qq_group_number: "",
      button_text: "复制群号",
      guide_text: "打开 QQ，搜索群号加入。",
      join_link: "",
      qr_image_url: "",
      sort_order: 10,
    },
  ];
}

function removeEmployeeExternalSkillSite(index) {
  form.value.employee_external_skill_sites = normalizeEmployeeExternalSkillSites(
    form.value.employee_external_skill_sites,
  ).filter((_, currentIndex) => currentIndex !== index);
}

function removePublicContactChannel(index) {
  form.value.public_contact_channels = normalizePublicContactChannels(
    form.value.public_contact_channels,
  ).filter((_, currentIndex) => currentIndex !== index);
}

function ensureGlobalAssistantChatModelSelection() {
  if (!String(form.value.global_assistant_chat_provider_id || "").trim()) {
    form.value.global_assistant_chat_model_name = "";
    return;
  }
  if (!selectedGlobalAssistantChatProvider.value) {
    return;
  }
  const models = selectedGlobalAssistantChatProviderModels.value;
  if (!models.length) {
    form.value.global_assistant_chat_model_name = "";
    return;
  }
  const currentModel = String(
    form.value.global_assistant_chat_model_name || "",
  ).trim();
  if (models.some((item) => item.name === currentModel)) {
    return;
  }
  form.value.global_assistant_chat_model_name = String(
    selectedGlobalAssistantChatProvider.value?.default_model || models[0]?.name || "",
  ).trim();
}

function handleGlobalAssistantChatProviderChange(value) {
  form.value.global_assistant_chat_provider_id = String(value || "").trim();
  ensureGlobalAssistantChatModelSelection();
}

function ensureVoiceModelSelection() {
  if (!String(form.value.voice_input_provider_id || "").trim()) {
    form.value.voice_input_model_name = "";
    return;
  }
  if (!selectedVoiceProvider.value) {
    return;
  }
  const models = selectedVoiceProviderModels.value;
  if (!models.length) {
    form.value.voice_input_model_name = "";
    return;
  }
  const currentModel = String(form.value.voice_input_model_name || "").trim();
  if (models.some((item) => item.name === currentModel)) {
    return;
  }
  form.value.voice_input_model_name = String(
    selectedVoiceProvider.value?.default_model || models[0]?.name || "",
  ).trim();
}

function handleVoiceProviderChange(value) {
  form.value.voice_input_provider_id = String(value || "").trim();
  ensureVoiceModelSelection();
}

function ensureVoiceOutputModelSelection() {
  if (!String(form.value.voice_output_provider_id || "").trim()) {
    form.value.voice_output_model_name = "";
    return;
  }
  if (!selectedVoiceOutputProvider.value) {
    return;
  }
  const models = selectedVoiceOutputProviderModels.value;
  if (!models.length) {
    form.value.voice_output_model_name = "";
    return;
  }
  const currentModel = String(form.value.voice_output_model_name || "").trim();
  if (models.some((item) => item.name === currentModel)) {
    return;
  }
  form.value.voice_output_model_name = String(
    selectedVoiceOutputProvider.value?.default_model || models[0]?.name || "",
  ).trim();
}

async function fetchVoiceOutputVoices(providerId = form.value.voice_output_provider_id) {
  const normalizedProviderId = String(providerId || "").trim();
  if (!normalizedProviderId) {
    voiceOutputVoiceOptions.value = [];
    voiceOutputVoiceCatalogMessage.value = "";
    return;
  }
  voiceOutputVoiceCatalogLoading.value = true;
  try {
    const data = await api.get("/system-config/voice-output/voices", {
      params: { provider_id: normalizedProviderId },
    });
    voiceOutputVoiceOptions.value = Array.isArray(data?.items) ? data.items : [];
    voiceOutputVoiceCatalogMessage.value = String(data?.message || "");
  } catch (err) {
    voiceOutputVoiceOptions.value = [];
    voiceOutputVoiceCatalogMessage.value =
      err?.detail || err?.message || "读取播报音色失败，请稍后重试";
  } finally {
    voiceOutputVoiceCatalogLoading.value = false;
  }
}

async function handleVoiceOutputProviderChange(value) {
  form.value.voice_output_provider_id = String(value || "").trim();
  ensureVoiceOutputModelSelection();
  await fetchVoiceOutputVoices(form.value.voice_output_provider_id);
}

function applyConfigToForm(config, options = {}) {
  const payload =
    config && typeof config === "object" && !Array.isArray(config) ? config : {};
  const preservePrompt = Boolean(options.preservePrompt);
  const preserveMcpConfig = Boolean(options.preserveMcpConfig);
  const hasPrompt = Object.prototype.hasOwnProperty.call(
    payload,
    "default_chat_system_prompt",
  );
  const hasEmployeeRulePrompt = Object.prototype.hasOwnProperty.call(
    payload,
    "employee_auto_rule_generation_prompt",
  );
  const hasMcpConfig = Object.prototype.hasOwnProperty.call(payload, "mcp_config");

  form.value = {
    ...form.value,
    enable_project_manual_generation:
      !!payload.enable_project_manual_generation,
    enable_employee_manual_generation:
      !!payload.enable_employee_manual_generation,
    chat_upload_max_limit: Number(payload.chat_upload_max_limit || 6),
    chat_max_tokens: Number(payload.chat_max_tokens || 512),
    default_chat_system_prompt:
      hasPrompt || !preservePrompt
        ? String(payload.default_chat_system_prompt || "")
        : String(form.value.default_chat_system_prompt || ""),
    employee_auto_rule_generation_enabled:
      !Object.prototype.hasOwnProperty.call(
        payload,
        "employee_auto_rule_generation_enabled",
      ) || !!payload.employee_auto_rule_generation_enabled,
    employee_auto_rule_generation_source_filters: Array.isArray(
      payload.employee_auto_rule_generation_source_filters,
    ) && payload.employee_auto_rule_generation_source_filters.length
      ? payload.employee_auto_rule_generation_source_filters
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      : ["prompts_chat_curated"],
    employee_auto_rule_generation_max_count: Math.min(
      6,
      Math.max(1, Number(payload.employee_auto_rule_generation_max_count || 3)),
    ),
    employee_auto_rule_generation_prompt:
      hasEmployeeRulePrompt || !preservePrompt
        ? String(
            payload.employee_auto_rule_generation_prompt ||
              DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT,
          )
        : String(
            form.value.employee_auto_rule_generation_prompt ||
              DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT,
          ),
    employee_external_skill_sites: normalizeEmployeeExternalSkillSites(
      payload.employee_external_skill_sites,
    ),
    voice_input_enabled: !!payload.voice_input_enabled,
    voice_input_provider_id: String(payload.voice_input_provider_id || ""),
    voice_input_model_name: String(payload.voice_input_model_name || ""),
    voice_input_allowed_usernames: normalizeStringList(
      payload.voice_input_allowed_usernames,
    ),
    voice_input_allowed_role_ids: normalizeStringList(
      payload.voice_input_allowed_role_ids,
    ),
    voice_output_enabled: !!payload.voice_output_enabled,
    voice_output_provider_id: String(payload.voice_output_provider_id || ""),
    voice_output_model_name: String(payload.voice_output_model_name || ""),
    voice_output_voice: String(payload.voice_output_voice || ""),
    voice_output_reminder_volume: Math.max(
      0,
      Math.min(100, Number(payload.voice_output_reminder_volume ?? 40) || 40),
    ),
    global_assistant_enabled: payload.global_assistant_enabled !== false,
    global_assistant_greeting_enabled:
      payload.global_assistant_greeting_enabled !== false,
    global_assistant_greeting_text: String(
      payload.global_assistant_greeting_text ||
        DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
    ),
    global_assistant_chat_provider_id: String(
      payload.global_assistant_chat_provider_id || "",
    ),
    global_assistant_chat_model_name: String(
      payload.global_assistant_chat_model_name || "",
    ),
    global_assistant_system_prompt: String(
      payload.global_assistant_system_prompt ||
        DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT,
    ),
    global_assistant_transcription_prompt: String(
      payload.global_assistant_transcription_prompt ||
        DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
    ),
    global_assistant_wake_phrase: String(
      payload.global_assistant_wake_phrase || "你好助手",
    ),
    global_assistant_idle_timeout_sec: Math.max(
      3,
      Math.min(30, Number(payload.global_assistant_idle_timeout_sec || 5) || 5),
    ),
    bot_platform_connectors: normalizeBotPlatformConnectors(
      payload.bot_platform_connectors,
    ),
    feishu_bot_long_connection_worker_enabled: Boolean(
      payload.feishu_bot_long_connection_worker_enabled,
    ),
    public_contact_channels: normalizePublicContactChannels(
      payload.public_contact_channels,
    ),
    query_mcp_public_base_url: String(payload.query_mcp_public_base_url || ""),
    query_mcp_clarity_confirm_threshold: Math.max(
      1,
      Math.min(
        5,
        Number(payload.query_mcp_clarity_confirm_threshold || 3) || 3,
      ),
    ),
    query_mcp_bootstrap_prompt_template: String(
      payload.query_mcp_bootstrap_prompt_template ||
        DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE,
    ),
    query_mcp_usage_guide_template: String(
      payload.query_mcp_usage_guide_template ||
        DEFAULT_QUERY_MCP_USAGE_GUIDE_TEMPLATE,
    ),
    query_mcp_client_profile_template: String(
      payload.query_mcp_client_profile_template ||
        DEFAULT_QUERY_MCP_CLIENT_PROFILE_TEMPLATE,
    ),
    chat_style_hints: normalizeChatStyleHints(payload.chat_style_hints),
    skill_registry_sources: normalizeSkillRegistrySources(
      payload.skill_registry_sources,
    ),
    mcp_config_text:
      hasMcpConfig || !preserveMcpConfig
        ? formatMcpConfig(payload.mcp_config)
        : String(form.value.mcp_config_text || formatMcpConfig(DEFAULT_MCP_CONFIG)),
  };
  ensureVoiceModelSelection();
  ensureVoiceOutputModelSelection();
}

function formatMcpConfig(value) {
  const config =
    value && typeof value === "object" ? value : DEFAULT_MCP_CONFIG;
  return JSON.stringify(config, null, 2);
}

function parseMcpConfigText() {
  let parsed;
  try {
    parsed = JSON.parse(
      String(form.value.mcp_config_text || "").trim() || "{}",
    );
  } catch (err) {
    throw new Error(`MCP 配置 JSON 解析失败：${err?.message || "格式错误"}`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("MCP 配置必须是 JSON 对象");
  }
  return parsed;
}

function updateMcpConfig(mutator) {
  const parsed = parseMcpConfigText();
  mutator(parsed);
  form.value.mcp_config_text = formatMcpConfig(parsed);
}

function formatMcpConfigText() {
  try {
    form.value.mcp_config_text = formatMcpConfig(parseMcpConfigText());
    ElMessage.success("JSON 已格式化");
  } catch (err) {
    ElMessage.error(err?.message || "MCP 配置格式错误");
  }
}

function resetMcpConfig() {
  form.value.mcp_config_text = formatMcpConfig(DEFAULT_MCP_CONFIG);
}

function toggleMcpServer(serverName, enabled) {
  try {
    updateMcpConfig((config) => {
      config.mcpServers =
        config.mcpServers && typeof config.mcpServers === "object"
          ? config.mcpServers
          : {};
      const current =
        config.mcpServers[serverName] &&
        typeof config.mcpServers[serverName] === "object" &&
        !Array.isArray(config.mcpServers[serverName])
          ? { ...config.mcpServers[serverName] }
          : {};
      current.enabled = Boolean(enabled);
      config.mcpServers[serverName] = current;
    });
  } catch (err) {
    ElMessage.error(err?.message || "切换 MCP 服务状态失败");
  }
}

function parseDateTime(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value) {
  const date = parseDateTime(value);
  if (!date) {
    return "-";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function formatPlatform(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) {
    return "-";
  }
  if (raw === "macos" || raw === "darwin") {
    return "macOS";
  }
  if (raw === "windows" || raw === "win32" || raw === "nt") {
    return "Windows";
  }
  return raw;
}

function formatFileSize(value) {
  const size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) {
    return "-";
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  if (size < 1024 * 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function handleDesktopArtifactFileChange(uploadFile, uploadFiles) {
  desktopArtifactUploadFileList.value = uploadFiles.slice(-1);
  desktopArtifactUploadFile.value = uploadFile?.raw || null;
}

function handleDesktopArtifactFileRemove() {
  desktopArtifactUploadFileList.value = [];
  desktopArtifactUploadFile.value = null;
}

function handleDesktopArtifactFileExceed() {
  ElMessage.warning("每次只能上传一个安装包文件");
}

function resetDesktopArtifactUploadForm(options = {}) {
  const preserveTarget = options.preserveTarget !== false;
  const nextTarget = preserveTarget
    ? String(desktopArtifactUploadForm.value.target || "windows:setup")
    : "windows:setup";
  desktopArtifactUploadForm.value = {
    target: nextTarget,
    version: "",
  };
  desktopArtifactUploadFile.value = null;
  desktopArtifactUploadFileList.value = [];
  desktopArtifactUploadRef.value?.clearFiles?.();
}

function connectorCapabilityLabels(item) {
  const capabilities =
    item?.capabilities && typeof item.capabilities === "object"
      ? item.capabilities
      : {};
  const labels = [];
  if (capabilities.workspace) {
    labels.push("本地目录");
  }
  if (capabilities.exec_stream) {
    labels.push("命令执行");
  }
  if (capabilities.pty) {
    labels.push("终端 PTY");
  }
  if (capabilities.local_llm_bridge) {
    labels.push("本地模型桥接");
  }
  return labels.length ? labels : ["已注册"];
}

function connectorLlmSharingSummary(item) {
  const usernames = Array.isArray(item?.llm_shared_with_usernames)
    ? item.llm_shared_with_usernames
        .map((entry) => String(entry || "").trim())
        .filter(Boolean)
    : [];
  const roleIds = Array.isArray(item?.llm_shared_with_roles)
    ? item.llm_shared_with_roles
        .map((entry) => String(entry || "").trim())
        .filter(Boolean)
    : [];
  if (!usernames.length && !roleIds.length) {
    return "未共享";
  }
  const parts = [];
  if (usernames.length) {
    parts.push(`用户 ${usernames.join("、")}`);
  }
  if (roleIds.length) {
    const roleNames = roleIds.map((roleId) => {
      const matched = connectorShareRoleOptions.value.find((item) => item.id === roleId);
      return matched?.name || roleId;
    });
    parts.push(`角色 ${roleNames.join("、")}`);
  }
  return parts.join("；");
}

async function copyText(value) {
  const text = String(value || "").trim();
  if (!text) {
    ElMessage.warning("没有可复制的内容");
    return;
  }
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    ElMessage.success("已复制");
  } catch {
    ElMessage.error("复制失败，请手动复制");
  }
}

async function fetchLocalConnectors(options = {}) {
  connectorItems.value = [];
  desktopArtifactItems.value = [];
  connectorsLoading.value = false;
}

async function ensureConnectorShareOptionsLoaded() {
  if (connectorShareUserOptions.value.length || connectorShareRoleOptions.value.length) {
    return;
  }
  connectorShareOptionsLoading.value = true;
  try {
    const data = await api.get("/local-connectors/llm-share-options");
    connectorShareUserOptions.value = Array.isArray(data?.users) ? data.users : [];
    connectorShareRoleOptions.value = Array.isArray(data?.roles) ? data.roles : [];
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载共享范围失败");
    throw err;
  } finally {
    connectorShareOptionsLoading.value = false;
  }
}

async function openConnectorLlmSharingDialog(item) {
  if (!item?.can_manage_llm_sharing) {
    return;
  }
  try {
    await ensureConnectorShareOptionsLoaded();
  } catch {
    return;
  }
  connectorLlmSharingForm.value = {
    connector_id: String(item?.id || "").trim(),
    connector_name: String(item?.connector_name || item?.id || "").trim(),
    llm_shared_with_usernames: Array.isArray(item?.llm_shared_with_usernames)
      ? item.llm_shared_with_usernames
          .map((entry) => String(entry || "").trim())
          .filter(Boolean)
      : [],
    llm_shared_with_roles: Array.isArray(item?.llm_shared_with_roles)
      ? item.llm_shared_with_roles
          .map((entry) => String(entry || "").trim())
          .filter(Boolean)
      : [],
  };
  showConnectorLlmSharingDialog.value = true;
}

async function saveConnectorLlmSharing() {
  const connectorId = String(connectorLlmSharingForm.value.connector_id || "").trim();
  if (!connectorId) {
    ElMessage.warning("缺少连接器 ID");
    return;
  }
  savingConnectorLlmSharing.value = true;
  try {
    const data = await api.patch(
      `/local-connectors/${encodeURIComponent(connectorId)}/llm-sharing`,
      {
        llm_shared_with_usernames: connectorLlmSharingForm.value.llm_shared_with_usernames,
        llm_shared_with_roles: connectorLlmSharingForm.value.llm_shared_with_roles,
      },
    );
    const updatedConnector = data?.connector;
    if (updatedConnector?.id) {
      connectorItems.value = connectorItems.value.map((item) =>
        item.id === updatedConnector.id ? updatedConnector : item,
      );
    }
    showConnectorLlmSharingDialog.value = false;
    ElMessage.success("本地模型共享设置已更新");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存共享设置失败");
  } finally {
    savingConnectorLlmSharing.value = false;
  }
}

async function downloadDesktopArtifact(item) {
  const filename = String(item?.filename || "").trim();
  if (!filename) {
    ElMessage.warning("缺少桌面包文件名");
    return;
  }
  downloadingDesktopArtifactKey.value = filename;
  try {
    const response = await api.get("/local-connectors/desktop-artifacts/download", {
      params: { name: filename },
      responseType: "blob",
    });
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

async function uploadDesktopArtifact() {
  const target = selectedDesktopArtifactTarget.value;
  const version = String(desktopArtifactUploadForm.value.version || "").trim();
  const file = desktopArtifactUploadFile.value;
  if (!target) {
    ElMessage.warning("请选择安装包类型");
    return;
  }
  if (!version) {
    ElMessage.warning("请输入版本号");
    return;
  }
  if (!file) {
    ElMessage.warning("请先选择安装包文件");
    return;
  }
  if (!String(file.name || "").toLowerCase().endsWith(target.accept.toLowerCase())) {
    ElMessage.warning(`当前类型只支持上传 ${target.accept} 文件`);
    return;
  }

  uploadingDesktopArtifact.value = true;
  try {
    const payload = new FormData();
    payload.append("platform", target.platform);
    payload.append("variant", target.variant);
    payload.append("version", version);
    payload.append("file", file);
    await api.post("/local-connectors/desktop-artifacts/upload", payload, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    resetDesktopArtifactUploadForm();
    await fetchLocalConnectors({ silent: true });
    ElMessage.success(`${target.label} 已上传，旧包已覆盖`);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "上传桌面安装包失败");
  } finally {
    uploadingDesktopArtifact.value = false;
  }
}

async function deleteConnector(item) {
  const connectorId = String(item?.id || "").trim();
  if (!connectorId) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定删除本地连接器「${item?.connector_name || connectorId}」？`,
      "删除连接器",
      {
        type: "warning",
      },
    );
  } catch {
    return;
  }
  deletingConnectorId.value = connectorId;
  try {
    await api.delete(`/local-connectors/${connectorId}`);
    connectorItems.value = connectorItems.value.filter((entry) => entry.id !== connectorId);
    ElMessage.success("连接器已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除连接器失败");
  } finally {
    deletingConnectorId.value = "";
  }
}

async function refreshMcpSkills() {
  skillsLoading.value = true;
  try {
    const data = await api.get("/system-config/mcp-skills");
    mcpServers.value = Array.isArray(data?.servers) ? data.servers : [];
  } catch (err) {
    mcpServers.value = [];
    ElMessage.error(err?.detail || err?.message || "加载 MCP 技能失败");
  } finally {
    skillsLoading.value = false;
  }
}

async function fetchVoiceInputOptions() {
  try {
    const data = await api.get("/system-config/voice-input/options");
    voiceProviderOptions.value = Array.isArray(data?.providers)
      ? data.providers
      : [];
    voiceUserOptions.value = Array.isArray(data?.users) ? data.users : [];
    voiceRoleOptions.value = Array.isArray(data?.roles) ? data.roles : [];
    ensureVoiceModelSelection();
  } catch (err) {
    voiceProviderOptions.value = [];
    voiceUserOptions.value = [];
    voiceRoleOptions.value = [];
    ElMessage.error(err?.detail || err?.message || "加载语音输入配置选项失败");
  }
}

async function fetchGlobalAssistantChatOptions() {
  try {
    const data = await api.get("/system-config/global-assistant-chat/options");
    globalAssistantChatProviderOptions.value = Array.isArray(data?.providers)
      ? data.providers
      : [];
    ensureGlobalAssistantChatModelSelection();
  } catch (err) {
    globalAssistantChatProviderOptions.value = [];
    ElMessage.error(
      err?.detail || err?.message || "加载全局助手对话模型选项失败",
    );
  }
}

async function fetchVoiceOutputOptions() {
  try {
    const data = await api.get("/system-config/voice-output/options");
    voiceOutputProviderOptions.value = Array.isArray(data?.providers)
      ? data.providers
      : [];
    ensureVoiceOutputModelSelection();
    await fetchVoiceOutputVoices();
  } catch (err) {
    voiceOutputProviderOptions.value = [];
    voiceOutputVoiceOptions.value = [];
    voiceOutputVoiceCatalogMessage.value = "";
    ElMessage.error(err?.detail || err?.message || "加载语音播报配置选项失败");
  }
}

async function refreshAllPanels() {
  refreshingPanels.value = true;
  try {
    await Promise.all([
      refreshMcpSkills(),
      fetchGlobalAssistantChatOptions(),
      fetchVoiceInputOptions(),
      fetchVoiceOutputOptions(),
    ]);
  } finally {
    refreshingPanels.value = false;
  }
}

async function fetchConfig() {
  loading.value = true;
  try {
    const data = await api.get("/system-config");
    applyConfigToForm(data?.config);
    await Promise.all([
      refreshMcpSkills(),
      fetchGlobalAssistantChatOptions(),
      fetchVoiceInputOptions(),
      fetchVoiceOutputOptions(),
    ]);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载系统配置失败");
  } finally {
    loading.value = false;
  }
}

async function fetchProjectOptions() {
  try {
    const data = await api.get("/projects");
    projectOptions.value = Array.isArray(data?.projects)
      ? data.projects
          .map((item) => ({
            value: String(item?.id || "").trim(),
            label: String(item?.name || item?.id || "").trim(),
          }))
          .filter((item) => item.value && item.label)
      : [];
  } catch {
    projectOptions.value = [];
  }
}

function normalizeSystemConfigTab(value) {
  const normalized = String(value || "").trim();
  return SYSTEM_CONFIG_TAB_NAMES.includes(normalized) ? normalized : "defaults";
}

function syncActiveTabFromRoute() {
  if (String(route.query.tab || "").trim() === "bot-platforms") {
    void router.replace({
      path: resolveSettingsAwarePath(
        route.path,
        "/system/bot-connectors",
        "/system/bot-connectors",
      ),
    });
    return;
  }
  activeTab.value = normalizeSystemConfigTab(route.query.tab);
}

async function saveConfig() {
  let mcpConfig;
  try {
    mcpConfig = parseMcpConfigText();
  } catch (err) {
    ElMessage.error(err?.message || "MCP 配置格式错误");
    return;
  }

  saving.value = true;
  try {
    const data = await api.patch("/system-config", {
      enable_project_manual_generation:
        !!form.value.enable_project_manual_generation,
      enable_employee_manual_generation:
        !!form.value.enable_employee_manual_generation,
      chat_upload_max_limit: Number(form.value.chat_upload_max_limit || 6),
      chat_max_tokens: Number(form.value.chat_max_tokens || 512),
      default_chat_system_prompt: String(
        form.value.default_chat_system_prompt || "",
      ),
      employee_auto_rule_generation_enabled: Boolean(
        form.value.employee_auto_rule_generation_enabled,
      ),
      employee_auto_rule_generation_source_filters: Array.isArray(
        form.value.employee_auto_rule_generation_source_filters,
      )
        ? form.value.employee_auto_rule_generation_source_filters
            .map((item) => String(item || "").trim())
            .filter(Boolean)
        : ["prompts_chat_curated"],
      employee_auto_rule_generation_max_count: Number(
        form.value.employee_auto_rule_generation_max_count || 3,
      ),
      employee_auto_rule_generation_prompt: String(
        form.value.employee_auto_rule_generation_prompt ||
          DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT,
      ),
      employee_external_skill_sites: normalizeEmployeeExternalSkillSites(
        form.value.employee_external_skill_sites,
      ),
      voice_input_enabled: Boolean(form.value.voice_input_enabled),
      voice_input_provider_id: String(form.value.voice_input_provider_id || ""),
      voice_input_model_name: String(form.value.voice_input_model_name || ""),
      voice_input_allowed_usernames: normalizeStringList(
        form.value.voice_input_allowed_usernames,
      ),
      voice_input_allowed_role_ids: normalizeStringList(
        form.value.voice_input_allowed_role_ids,
      ),
      voice_output_enabled: Boolean(form.value.voice_output_enabled),
      voice_output_provider_id: String(form.value.voice_output_provider_id || ""),
      voice_output_model_name: String(form.value.voice_output_model_name || ""),
      voice_output_voice: String(form.value.voice_output_voice || "").trim(),
      voice_output_reminder_volume: Math.max(
        0,
        Math.min(
          100,
          Number(form.value.voice_output_reminder_volume ?? 40) || 40,
        ),
      ),
      global_assistant_enabled: Boolean(form.value.global_assistant_enabled),
      global_assistant_greeting_enabled: Boolean(
        form.value.global_assistant_greeting_enabled,
      ),
      global_assistant_greeting_text: String(
        form.value.global_assistant_greeting_text || "",
      ).trim(),
      global_assistant_chat_provider_id: String(
        form.value.global_assistant_chat_provider_id || "",
      ).trim(),
      global_assistant_chat_model_name: String(
        form.value.global_assistant_chat_model_name || "",
      ).trim(),
      global_assistant_system_prompt: String(
        form.value.global_assistant_system_prompt || "",
      ).trim(),
      global_assistant_transcription_prompt: String(
        form.value.global_assistant_transcription_prompt || "",
      ).trim(),
      global_assistant_wake_phrase: String(
        form.value.global_assistant_wake_phrase || "",
      ).trim(),
      global_assistant_idle_timeout_sec: Math.max(
        3,
        Math.min(
          30,
          Number(form.value.global_assistant_idle_timeout_sec || 5) || 5,
        ),
      ),
      bot_platform_connectors: normalizeBotPlatformConnectors(
        form.value.bot_platform_connectors,
      ),
      feishu_bot_long_connection_worker_enabled: Boolean(
        form.value.feishu_bot_long_connection_worker_enabled,
      ),
      public_contact_channels: normalizePublicContactChannels(
        form.value.public_contact_channels,
      ),
      query_mcp_public_base_url: String(
        form.value.query_mcp_public_base_url || "",
      ).trim(),
      query_mcp_clarity_confirm_threshold: Math.max(
        1,
        Math.min(
          5,
          Number(form.value.query_mcp_clarity_confirm_threshold || 3) || 3,
        ),
      ),
      query_mcp_bootstrap_prompt_template: String(
        form.value.query_mcp_bootstrap_prompt_template ||
          DEFAULT_QUERY_MCP_BOOTSTRAP_PROMPT_TEMPLATE,
      ),
      query_mcp_usage_guide_template: String(
        form.value.query_mcp_usage_guide_template ||
          DEFAULT_QUERY_MCP_USAGE_GUIDE_TEMPLATE,
      ),
      query_mcp_client_profile_template: String(
        form.value.query_mcp_client_profile_template ||
          DEFAULT_QUERY_MCP_CLIENT_PROFILE_TEMPLATE,
      ),
      chat_style_hints: normalizeChatStyleHints(form.value.chat_style_hints),
      skill_registry_sources: normalizeSkillRegistrySources(
        form.value.skill_registry_sources,
      ),
      mcp_config: mcpConfig,
    });
    applyConfigToForm(data?.config, {
      preservePrompt: true,
      preserveMcpConfig: true,
    });
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("system-config-updated", {
          detail: { config: data?.config || {} },
        }),
      );
    }
    await Promise.all([
      refreshMcpSkills(),
      fetchGlobalAssistantChatOptions(),
      fetchVoiceInputOptions(),
      fetchVoiceOutputOptions(),
    ]);
    ElMessage.success("系统配置已保存");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存系统配置失败");
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  syncActiveTabFromRoute();
  fetchConfig();
  fetchProjectOptions();
});

watch(
  () => route.query.tab,
  () => {
    syncActiveTabFromRoute();
  },
);

watch(activeTab, (value) => {
  const normalizedTab = normalizeSystemConfigTab(value);
  if (String(route.query.tab || "") === normalizedTab) {
    return;
  }
  router.replace({
    query: {
      ...route.query,
      tab: normalizedTab,
    },
  });
});

</script>

<style scoped>
.system-config-page {
  --page-bg: linear-gradient(180deg, #f5f7fb 0%, #eef2f7 100%);
  --panel-bg: rgba(255, 255, 255, 0.92);
  --panel-border: rgba(112, 128, 144, 0.14);
  --panel-shadow: 0 18px 48px rgba(32, 56, 85, 0.08);
  --text-main: #1f2a37;
  --text-muted: #637083;
  --accent: #1e6aa8;
  --accent-soft: rgba(30, 106, 168, 0.1);
  --green-soft: rgba(55, 146, 98, 0.12);
  --amber-soft: rgba(191, 130, 44, 0.14);
  min-height: 100%;
  padding: 24px;
  background: var(--page-bg);
}

.hero,
.panel,
.metric-card {
  border: 1px solid var(--panel-border);
  box-shadow: var(--panel-shadow);
  backdrop-filter: blur(12px);
}

.hero {
  display: flex;
  position: relative;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  padding: 24px 28px;
  border-radius: 24px;
  background:
    radial-gradient(
      circle at top right,
      rgba(30, 106, 168, 0.14),
      transparent 32%
    ),
    linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.98),
      rgba(246, 249, 252, 0.94)
    );
}

.hero-body {
  min-width: 0;
}

.hero-eyebrow {
  margin: 0 0 10px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hero h2 {
  margin: 0;
  color: var(--text-main);
  font-size: 28px;
  line-height: 1.2;
}

.hero-desc {
  margin: 12px 0 0;
  max-width: 720px;
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.7;
}

.hero-highlights {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

.hero-highlight {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(30, 106, 168, 0.14);
  color: var(--accent);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 20px;
  border-radius: 18px;
  background: var(--panel-bg);
}

.metric-label {
  color: var(--text-muted);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.metric-value {
  color: var(--text-main);
  font-size: 32px;
  line-height: 1;
}

.metric-foot {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.86fr);
  gap: 16px;
  margin-top: 16px;
  align-items: start;
}

.content-grid--single {
  grid-template-columns: minmax(0, 1fr);
}

.content-grid--single .content-aside {
  grid-column: 1 / -1;
}

.content-main,
.content-aside {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  padding: 20px;
  border-radius: 24px;
  background: var(--panel-bg);
}

.panel--accent {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(244, 248, 252, 0.94)),
    var(--panel-bg);
}

.panel--sticky {
  position: sticky;
  top: 108px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.panel-head h3 {
  margin: 0;
  color: var(--text-main);
  font-size: 18px;
}

.panel-head p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.panel-kicker {
  margin: 0 0 8px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.panel-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.inline-alert {
  margin-bottom: 16px;
}

.switch-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.switch-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.switch-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(245, 248, 251, 0.9);
  border: 1px solid rgba(112, 128, 144, 0.12);
}

.switch-title {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 600;
}

.switch-desc {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.number-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.field-desc {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.field-desc-block {
  margin-bottom: 0;
}

.employee-rule-config-card {
  margin-top: 12px;
}

.employee-rule-source-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.employee-skill-site-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.registry-head {
  margin-top: 8px;
}

.guide-modules-head {
  margin-top: 4px;
}

.employee-skill-site-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 520px;
  overflow-y: auto;
  padding-right: 4px;
}

.employee-skill-site-card {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: rgba(248, 250, 252, 0.9);
}

.voice-config-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.voice-config-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.voice-config-section__head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.voice-config-divider {
  height: 1px;
  background: rgba(112, 128, 144, 0.14);
}

.employee-skill-site-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.employee-skill-site-card__title {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 600;
}

.employee-skill-site-card__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.employee-skill-site-card__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.guide-module-meta-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr) 140px;
  gap: 12px;
}

.guide-module-switch-grid {
  margin-bottom: 12px;
}

.voice-output-voice-field {
  display: flex;
  align-items: center;
  gap: 12px;
}

.registry-grid {
  margin-top: 14px;
}

.registry-risk-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.server-switch-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.server-switch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: rgba(245, 248, 251, 0.9);
}

.server-switch-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.server-switch-name {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 600;
}

.server-switch-url {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}

.server-switch-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.editor-shell {
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid rgba(112, 128, 144, 0.16);
  background: #0f1720;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  color: rgba(234, 239, 245, 0.86);
  font-size: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

.editor-meta {
  color: rgba(234, 239, 245, 0.58);
}

.mcp-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.mcp-summary-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(112, 128, 144, 0.12);
  background: rgba(248, 251, 254, 0.96);
}

.mcp-summary-card span {
  color: var(--text-muted);
  font-size: 12px;
}

.mcp-summary-card strong {
  color: var(--text-main);
  font-size: 28px;
  line-height: 1;
}

:deep(.mcp-config-input .el-textarea__inner) {
  min-height: 380px !important;
  padding: 18px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #edf2f7;
  font-size: 13px;
  line-height: 1.7;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  box-shadow: none;
}

.skill-panel {
  margin-top: 16px;
}

.connector-panel {
  margin-top: 16px;
}

.connector-metric-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.connector-metric {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: rgba(248, 250, 252, 0.9);
}

.connector-metric span {
  color: var(--text-muted);
  font-size: 12px;
}

.connector-metric strong {
  color: var(--text-main);
  font-size: 28px;
  line-height: 1;
}

.connector-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr);
  gap: 16px;
}

.connector-column {
  min-width: 0;
}

.connector-subhead {
  margin-bottom: 14px;
}

.connector-subhead h4 {
  margin: 0;
  color: var(--text-main);
  font-size: 15px;
}

.connector-subhead p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.pair-create-card,
.pair-code-card,
.connector-device-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.92)
  );
}

.pair-create-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 14px;
}

.pair-create-row {
  display: flex;
  gap: 10px;
}

.pair-ttl-select {
  flex: 1;
}

.pair-custom-ttl-input {
  width: 160px;
  flex-shrink: 0;
}

.pair-code-list,
.connector-card-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pair-code-top,
.connector-device-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.pair-code-value,
.connector-device-title {
  color: var(--text-main);
  font-size: 15px;
  font-weight: 700;
}

.pair-code-meta,
.connector-device-subtitle {
  margin-top: 6px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.pair-code-info,
.connector-device-info {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
  margin-top: 14px;
}

.pair-code-info span,
.connector-device-info span {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.pair-code-actions,
.connector-device-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.connector-device-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.connector-capability-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.connector-share-summary {
  margin-top: 12px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
  word-break: break-word;
}

.connector-error {
  margin-top: 14px;
}

.connector-sharing-copy {
  margin-bottom: 16px;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.7;
}

.connector-sharing-form {
  display: grid;
  gap: 4px;
}

.server-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.server-card {
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.92)
  );
}

.server-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.server-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.server-title-row h4 {
  margin: 0;
  color: var(--text-main);
  font-size: 17px;
}

.server-url {
  margin: 8px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}

.server-summary {
  padding: 9px 12px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
}

.capsule-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.capsule {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.capsule-tool {
  background: var(--accent-soft);
  color: var(--accent);
}

.capsule-prompt {
  background: var(--green-soft);
  color: #2f7c57;
}

.capsule-resource {
  background: var(--amber-soft);
  color: #9a6518;
}

.capsule-fallback {
  background: rgba(90, 95, 160, 0.12);
  color: #4852a3;
}

.server-notice {
  margin-top: 14px;
}

.skill-section-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.skill-box {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: rgba(248, 250, 252, 0.9);
}

.skill-box-title {
  margin-bottom: 10px;
  color: var(--text-main);
  font-size: 13px;
  font-weight: 700;
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.skill-name {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 600;
  word-break: break-word;
}

.skill-desc {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.skill-empty {
  color: var(--text-muted);
  font-size: 12px;
}

.check-block {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed rgba(112, 128, 144, 0.2);
}

.check-title {
  margin-bottom: 10px;
  color: var(--text-main);
  font-size: 13px;
  font-weight: 700;
}

.check-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.check-item {
  padding: 12px;
  border-radius: 14px;
  background: #f7f9fb;
  border: 1px solid rgba(112, 128, 144, 0.14);
}

.desktop-artifact-card {
  margin-bottom: 16px;
}

.desktop-artifact-card__head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.desktop-artifact-card__title {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 700;
}

.desktop-artifact-card__desc {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.desktop-artifact-upload-form {
  margin-bottom: 14px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: rgba(247, 249, 251, 0.92);
}

.desktop-artifact-upload-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.desktop-artifact-upload {
  width: 100%;
}

.desktop-artifact-upload__hint {
  margin-top: 6px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.desktop-artifact-upload-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.desktop-artifact-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.desktop-artifact-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  text-align: left;
  border: 1px solid rgba(112, 128, 144, 0.14);
  border-radius: 14px;
  background: #f7f9fb;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.desktop-artifact-item:hover {
  border-color: rgba(40, 94, 255, 0.28);
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(28, 55, 90, 0.08);
}

.desktop-artifact-item:disabled {
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
  box-shadow: none;
}

.desktop-artifact-item__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.desktop-artifact-item__label {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 700;
}

.desktop-artifact-item__size,
.desktop-artifact-item__meta {
  color: var(--text-muted);
  font-size: 12px;
}

.desktop-artifact-item__desc {
  color: var(--text-main);
  font-size: 12px;
  line-height: 1.5;
}

.check-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.check-method {
  color: var(--text-main);
  font-size: 12px;
  font-weight: 700;
}

.check-message {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.check-preview {
  margin: 10px 0 0;
  padding: 10px;
  border-radius: 12px;
  background: #101922;
  color: #dbe6ef;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

@media (max-width: 1100px) {
  .content-grid,
  .connector-grid,
  .connector-metric-row,
  .employee-skill-site-card__grid,
  .guide-module-meta-grid,
  .desktop-artifact-upload-grid,
  .skill-section-grid,
  .check-list,
  .overview-grid,
  .mcp-summary-grid {
    grid-template-columns: 1fr;
  }

  .panel--sticky {
    position: static;
  }
}

@media (max-width: 768px) {
  .system-config-page {
    padding: 16px;
  }

  .hero,
  .panel {
    padding: 18px;
    border-radius: 18px;
  }

  .hero,
  .panel-head,
  .server-head,
  .switch-card,
  .voice-output-voice-field,
  .employee-skill-site-card__top,
  .server-switch-item,
  .pair-code-top,
  .connector-device-top {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-actions,
  .panel-actions {
    width: 100%;
  }

  .number-grid,
  .pair-code-info,
  .connector-device-info,
  .desktop-artifact-list {
    grid-template-columns: 1fr;
  }

  .server-switch-actions,
  .pair-create-row {
    justify-content: space-between;
  }

  .server-summary {
    white-space: normal;
  }

  .desktop-artifact-upload-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-highlights {
    display: flex;
    gap: 8px;
  }
}
</style>
