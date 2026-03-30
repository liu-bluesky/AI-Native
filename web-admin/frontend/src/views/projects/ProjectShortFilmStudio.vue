<template>
  <div class="studio-workbench">
    <input
      ref="exportBgmFileInputRef"
      type="file"
      accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg,.flac"
      class="studio-hidden-input"
      @change="handleExportBgmFileChange"
    />
    <div
      class="studio-workbench__ambient studio-workbench__ambient--left"
      aria-hidden="true"
    />
    <div
      class="studio-workbench__ambient studio-workbench__ambient--right"
      aria-hidden="true"
    />
    <div class="studio-workbench__mesh" aria-hidden="true" />

    <section class="studio-stepper-panel">
      <div class="studio-stepper-panel__head">
        <div>
          <div class="studio-stepper-panel__eyebrow">Workflow Navigation</div>
          <div class="studio-stepper-panel__title">四步进入生产</div>
        </div>
        <div class="studio-stepper-panel__progress">
          <span class="studio-stepper-panel__progress-label">制作进度</span>
          <strong>
            {{ String(activeStepIndex + 1).padStart(2, "0") }} /
            {{ String(stepItems.length).padStart(2, "0") }}
          </strong>
        </div>
      </div>

      <div class="studio-stepper">
        <button
          v-for="(step, index) in stepItems"
          :key="step.id"
          type="button"
          class="studio-stepper__item"
          :class="`is-${stepStatus(step.id)}`"
          @click="switchStep(step.id)"
        >
          <span class="studio-stepper__index">
            {{ String(index + 1).padStart(2, "0") }}
          </span>
          <span class="studio-stepper__copy">
            <span class="studio-stepper__title-row">
              <span class="studio-stepper__title">{{ step.title }}</span>
              <span class="studio-stepper__state">
                {{ stepStatusLabel(step.id) }}
              </span>
            </span>
            <span class="studio-stepper__desc">{{ step.description }}</span>
          </span>
        </button>
      </div>
    </section>

    <section v-if="showStudioDraftResume" class="studio-draft-banner">
      <div class="studio-draft-banner__copy">
        <strong>发现上次编辑草稿</strong>
        <span>
          保存于 {{ pendingStudioDraftSavedLabel }}，可恢复到
          {{ pendingStudioDraftStepLabel }} 继续制作。
        </span>
      </div>
      <div class="studio-draft-banner__actions">
        <el-button plain size="small" @click="dismissStudioDraftResume">
          暂不恢复
        </el-button>
        <el-button type="primary" size="small" @click="resumeStudioDraft">
          继续编辑
        </el-button>
      </div>
    </section>

    <section class="studio-stage">
      <div class="studio-surface studio-surface--main">
        <template v-if="activeStep === 'script'">
          <div class="studio-surface__head">
            <div>
              <div class="studio-surface__eyebrow">Step 01</div>
              <div class="studio-surface__title">剧本创作</div>
              <div class="studio-surface__subtitle">
                先把故事输入进来，再拆成可推进的章节结构。
              </div>
            </div>
            <div class="studio-surface__toolbar">
              <span class="studio-pill">{{ scriptLength }} / 25000 字</span>
              <input
                ref="scriptFileInputRef"
                class="studio-hidden-input"
                type="file"
                accept=".txt,.md"
                @change="handleScriptFileChange"
              />
              <el-button size="small" plain @click="openScriptFilePicker">
                导入剧本
              </el-button>
            </div>
          </div>

          <div class="studio-script-panel">
            <el-input
              v-model="scriptDraft.content"
              type="textarea"
              :autosize="{ minRows: 14, maxRows: 20 }"
              maxlength="25000"
              show-word-limit
              placeholder="请在这里输入剧本。建议按段落描述情节、角色和场景。"
              class="studio-script-panel__textarea"
            />
            <div class="studio-control-row">
              <div class="studio-control-row__group">
                <span class="studio-control-row__label">画面比例</span>
                <div class="studio-chip-group">
                  <button
                    v-for="option in aspectRatioOptions"
                    :key="option"
                    type="button"
                    class="studio-chip"
                    :class="{ 'is-active': scriptDraft.aspectRatio === option }"
                    @click="scriptDraft.aspectRatio = option"
                  >
                    {{ option }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <template v-else-if="activeStep === 'art'">
          <div class="studio-surface__head">
            <div>
              <div class="studio-surface__eyebrow">Step 02</div>
              <div class="studio-surface__title">美术设定</div>
              <div class="studio-surface__subtitle">
                用风格、角色、场景和道具把全局视觉设定先稳定下来。
              </div>
            </div>
            <div class="studio-surface__toolbar">
              <span class="studio-pill">已选风格 {{ selectedStyleCount }}</span>
              <span class="studio-pill">元素 {{ detectedElementCount }}</span>
            </div>
          </div>

          <div class="studio-section-grid">
            <section class="studio-card">
              <div class="studio-card__head">
                <div class="studio-card__title">风格选择</div>
                <div class="studio-card__meta">可多选</div>
              </div>
              <div class="studio-style-grid">
                <button
                  v-for="style in styles"
                  :key="style.id"
                  type="button"
                  class="studio-style-card"
                  :class="{ 'is-active': style.selected }"
                  @click="toggleStyle(style.id)"
                >
                  {{ style.label }}
                </button>
              </div>
            </section>

            <section class="studio-card">
              <div class="studio-card__head">
                <div class="studio-card__title">元素提取</div>
                <div class="studio-card__meta">一次提取整套基础设定</div>
              </div>

              <div class="studio-tab-row">
                <button
                  v-for="kind in elementKinds"
                  :key="kind.value"
                  type="button"
                  class="studio-tab"
                  :class="{ 'is-active': artSettings.kind === kind.value }"
                  @click="artSettings.kind = kind.value"
                >
                  {{ kind.label }}
                  <span class="studio-tab__count">
                    {{ elementCountByKind(kind.value) }}
                  </span>
                </button>
              </div>

              <div class="studio-form-grid studio-form-grid--triple">
                <label class="studio-field">
                  <span class="studio-field__label">模型源</span>
                  <el-select
                    v-model="artSettings.providerId"
                    :loading="loadingStudioModelSources"
                    placeholder="选择模型源"
                  >
                    <el-option
                      v-for="option in artModelProviderOptions"
                      :key="option.id"
                      :label="option.name"
                      :value="option.id"
                    />
                  </el-select>
                </label>
                <label class="studio-field">
                  <span class="studio-field__label">模型</span>
                  <el-select
                    v-model="artSettings.model"
                    :loading="loadingStudioModelSources"
                    placeholder="选择模型"
                  >
                    <el-option
                      v-for="option in artModelOptions"
                      :key="`${artSettings.providerId}-${option}`"
                      :label="option"
                      :value="option"
                    />
                  </el-select>
                </label>
                <label class="studio-field">
                  <span class="studio-field__label">时长</span>
                  <el-select v-model="artSettings.duration">
                    <el-option
                      v-for="option in artDurationOptions"
                      :key="option"
                      :label="option"
                      :value="option"
                    />
                  </el-select>
                </label>
                <label class="studio-field">
                  <span class="studio-field__label">画质</span>
                  <el-select v-model="artSettings.quality">
                    <el-option
                      v-for="option in qualityOptions"
                      :key="option"
                      :label="option"
                      :value="option"
                    />
                  </el-select>
                </label>
              </div>

              <div class="studio-inline-note">
                这里会统一提取角色、场景和道具。分类切换只用于查看结果和手动补录当前分类。
              </div>

              <div class="studio-card__actions">
                <el-button
                  type="primary"
                  :loading="extracting"
                  @click="startExtraction"
                >
                  开始提取
                </el-button>
                <el-button plain @click="addManualElement(artSettings.kind)">
                  手动新增当前分类
                </el-button>
              </div>
            </section>

            <section class="studio-card studio-card--wide">
              <div class="studio-card__head">
                <div class="studio-card__title">
                  {{ activeElementKindLabel }}资产
                </div>
                <div class="studio-card__meta">
                  先稳定设定，再进入分镜生成。
                </div>
              </div>

              <div v-if="activeElements.length" class="studio-element-grid">
                <article
                  v-for="element in activeElements"
                  :key="element.id"
                  class="studio-element-card"
                >
                  <div class="studio-element-card__visual">
                    <span>{{ element.name }}</span>
                  </div>
                  <div class="studio-element-card__body">
                    <div class="studio-element-card__title">
                      {{ element.name }}
                    </div>
                    <div class="studio-element-card__meta">
                      {{ elementStatusLabel(element.status) }}
                    </div>
                  </div>
                  <div class="studio-element-card__footer">
                    <el-button
                      v-if="element.kind === 'role'"
                      text
                      type="primary"
                      size="small"
                      @click="openCharacterConfig(element)"
                    >
                      角色配置
                    </el-button>
                    <el-button
                      text
                      type="warning"
                      size="small"
                      @click="markElementPending(element.id)"
                    >
                      标记待确认
                    </el-button>
                    <el-button
                      text
                      type="danger"
                      size="small"
                      @click="removeElement(element)"
                    >
                      删除
                    </el-button>
                  </div>
                </article>
              </div>

              <div v-else class="studio-empty-state">
                <el-empty
                  description="当前分类还没有提取结果"
                  :image-size="60"
                />
              </div>
            </section>
          </div>
        </template>

        <template v-else-if="activeStep === 'storyboard'">
          <div class="studio-surface__head">
            <div>
              <div class="studio-surface__eyebrow">Step 03</div>
              <div class="studio-surface__title">分镜制作</div>
              <div class="studio-surface__subtitle">
                以章节为单位生成分镜，补齐配音后再进入导出集合。
              </div>
            </div>
            <div class="studio-surface__toolbar">
              <span class="studio-pill"
                >可选分镜 {{ voicedStoryboardCount }}</span
              >
              <span class="studio-pill"
                >已选 {{ selectedStoryboards.length }}</span
              >
            </div>
          </div>

          <div class="studio-card studio-card--stack">
            <div class="studio-form-grid studio-form-grid--storyboard">
              <label class="studio-field">
                <span class="studio-field__label">章节</span>
                <el-select v-model="storyboardSettings.chapterId">
                  <el-option
                    v-for="chapter in chapters"
                    :key="chapter.id"
                    :label="chapter.title"
                    :value="chapter.id"
                  />
                </el-select>
              </label>
              <label class="studio-field">
                <span class="studio-field__label">模型源</span>
                <el-select
                  v-model="storyboardSettings.providerId"
                  :loading="loadingStudioModelSources"
                  placeholder="选择模型源"
                >
                  <el-option
                    v-for="option in storyboardModelProviderOptions"
                    :key="option.id"
                    :label="option.name"
                    :value="option.id"
                  />
                </el-select>
              </label>
              <label class="studio-field">
                <span class="studio-field__label">模型</span>
                <el-select
                  v-model="storyboardSettings.model"
                  :loading="loadingStudioModelSources"
                  placeholder="选择模型"
                >
                  <el-option
                    v-for="option in storyboardModelOptions"
                    :key="`${storyboardSettings.providerId}-${option}`"
                    :label="option"
                    :value="option"
                  />
                </el-select>
              </label>
              <label class="studio-field">
                <span class="studio-field__label">时长</span>
                <el-select v-model="storyboardSettings.duration">
                  <el-option
                    v-for="option in storyboardDurationOptions"
                    :key="option"
                    :label="option"
                    :value="option"
                  />
                </el-select>
              </label>
              <label class="studio-field">
                <span class="studio-field__label">画质</span>
                <el-select v-model="storyboardSettings.quality">
                  <el-option
                    v-for="option in qualityOptions"
                    :key="option"
                    :label="option"
                    :value="option"
                  />
                </el-select>
              </label>
            </div>

            <div class="studio-toggle-row">
              <span class="studio-inline-note">
                当前分镜只保留视频和旁白，背景音乐统一在导出阶段单独添加。
              </span>
              <el-button
                type="primary"
                :loading="generatingStoryboards"
                @click="generateStoryboardsForChapter"
              >
                生成当前章节分镜
              </el-button>
            </div>
          </div>

          <div
            v-if="currentChapterStoryboards.length"
            class="studio-storyboard-grid"
          >
            <article
              v-for="board in currentChapterStoryboards"
              :key="board.id"
              class="studio-storyboard-card"
            >
              <div class="studio-storyboard-card__preview">
                <div class="studio-storyboard-card__badge-group">
                  <el-tag
                    size="small"
                    effect="dark"
                    :type="board.hasVoice ? 'success' : 'info'"
                  >
                    {{ board.hasVoice ? "已配音" : "待配音" }}
                  </el-tag>
                  <el-tag
                    size="small"
                    effect="dark"
                    :type="board.status === 'ready' ? 'success' : 'warning'"
                  >
                    {{ storyboardStatusLabel(board.status) }}
                  </el-tag>
                </div>
                <div class="studio-storyboard-card__placeholder">
                  {{ board.title }}
                </div>
              </div>

              <div class="studio-storyboard-card__body">
                <div class="studio-storyboard-card__title">
                  {{ board.title }}
                </div>
                <div class="studio-storyboard-card__meta">
                  {{ chapterTitleById(board.chapterId) }}
                </div>
                <div
                  class="studio-duration-control studio-duration-control--card"
                >
                  <span>时长</span>
                  <strong class="studio-duration-control__value">
                    {{ board.durationSeconds }}
                  </strong>
                  <span>秒</span>
                </div>
                <div class="studio-storyboard-card__actions">
                  <el-button
                    text
                    type="primary"
                    size="small"
                    @click="openVoiceDialog(board)"
                  >
                    {{ board.hasVoice ? "编辑旁白" : "上传旁白" }}
                  </el-button>
                  <el-button
                    text
                    type="warning"
                    size="small"
                    @click="regenerateStoryboard(board.id)"
                  >
                    重生成
                  </el-button>
                </div>
              </div>

              <label
                class="studio-storyboard-card__select"
                :class="{ 'is-disabled': !board.hasVoice }"
              >
                <input
                  :checked="board.selected"
                  :disabled="!board.hasVoice"
                  type="checkbox"
                  @change="toggleStoryboardSelection(board.id, $event)"
                />
                <span>加入导出集合</span>
              </label>
            </article>
          </div>

          <div v-else class="studio-empty-state">
            <el-empty description="先选择章节，再生成分镜" :image-size="60" />
          </div>
        </template>

        <template v-else>
          <div class="studio-surface__head">
            <div>
              <div class="studio-surface__eyebrow">Step 04</div>
              <div class="studio-surface__title">导出视频</div>
            </div>
          </div>

          <div class="studio-section-grid studio-section-grid--export">
            <StudioMergedPreview
              :clips="visibleTimelineClips"
              :duration="timelineDuration"
              :audio-tracks="timelineAudioTracks"
              :audio-mix="studioAudioMix"
              :active-clip-id="activeTimelineClipId"
              @focus-clip="setActiveTimelineClip"
              @reorder-clips="moveVisibleTimelineClip"
              @remove-clip="removeTimelineClip"
              @remove-audio-segment="removeTimelineAudioSegment"
              @request-audio-upload="openExportBgmFilePicker"
              @update-audio-mix="handleStudioAudioMixChange"
            />
          </div>
        </template>
      </div>

      <aside class="studio-surface studio-surface--side">
        <div class="studio-side__panel-head">
          <div class="studio-side__eyebrow">Support Panel</div>
          <div class="studio-side__headline">{{ activeStepMeta.title }}</div>
          <div class="studio-side__caption">{{ footerSummary }}</div>
        </div>

        <template v-if="activeStep === 'script'">
          <div class="studio-side__section">
            <div class="studio-side__title">章节列表</div>
            <div v-if="chapters.length" class="studio-chapter-list">
              <article
                v-for="chapter in chapters"
                :key="chapter.id"
                class="studio-chapter-card"
              >
                <div class="studio-chapter-card__head">
                  <span class="studio-chapter-card__index">
                    {{ String(chapter.index).padStart(2, "0") }}
                  </span>
                  <div class="studio-chapter-card__title">
                    {{ chapter.title }}
                  </div>
                </div>
                <div class="studio-chapter-card__summary">
                  {{ chapter.summary }}
                </div>
                <div class="studio-chapter-card__footer">
                  <el-button
                    text
                    type="primary"
                    size="small"
                    @click="openChapterPreview(chapter.id)"
                  >
                    预览
                  </el-button>
                </div>
              </article>
            </div>
            <div v-else class="studio-empty-state studio-empty-state--compact">
              <el-empty description="分章结果会出现在这里" :image-size="48" />
            </div>
          </div>
        </template>

        <template v-else-if="activeStep === 'art'">
          <div class="studio-side__section">
            <div class="studio-side__title">设定进度</div>
            <div class="studio-progress-list">
              <div class="studio-progress-item">
                <span>风格选择</span>
                <strong>{{ selectedStyleCount }}/{{ styles.length }}</strong>
              </div>
              <div class="studio-progress-item">
                <span>元素提取</span>
                <strong>{{ detectedElementCount }}</strong>
              </div>
              <div class="studio-progress-item">
                <span>角色配置</span>
                <strong>{{ configuredRoleCount }}</strong>
              </div>
            </div>
            <div class="studio-note-card">
              这里优先把全局风格和基础元素稳定下来，再进入分镜生成，避免后续镜头风格漂移。
            </div>
          </div>
        </template>

        <template v-else-if="activeStep === 'storyboard'">
          <div class="studio-side__section">
            <div class="studio-side__title">生成历史</div>
            <div v-if="storyboardHistory.length" class="studio-history-list">
              <article
                v-for="item in storyboardHistory"
                :key="`log-${item.id}`"
                class="studio-history-log"
              >
                <div class="studio-history-log__title">{{ item.title }}</div>
                <div class="studio-history-log__meta">
                  {{ formatTime(item.updatedAt) }}
                </div>
              </article>
            </div>
            <div v-else class="studio-empty-state studio-empty-state--compact">
              <el-empty description="生成记录会出现在这里" :image-size="48" />
            </div>
            <div class="studio-note-card">
              规则：未配音分镜不可加入导出集合。先完成分镜，再补齐声音。
            </div>
          </div>
        </template>

        <template v-else>
          <StudioTimelineEditor
            :clips="timelineClips"
            :active-clip-id="activeTimelineClipId"
            :resolve-chapter-title="chapterTitleById"
            @open-history="openHistoryDialog"
            @normalize-duration="normalizeClipDuration"
            @set-visibility="setClipVisibility"
            @focus-clip="setActiveTimelineClip"
            @reorder-clips="moveTimelineClip"
            @move-clip-up="moveTimelineClipUp"
            @move-clip-down="moveTimelineClipDown"
            @remove-clip="removeTimelineClip"
          />
          <div class="studio-side__section">
            <div
              class="studio-dialog-section__head studio-dialog-section__head--stacked"
            >
              <div>
                <div class="studio-side__title">导出任务</div>
                <div class="studio-dialog-section__desc">
                  任务记录会保留在项目里，刷新后也能继续查看状态和结果。
                </div>
              </div>
              <el-button
                plain
                size="small"
                :loading="loadingStudioExportJobs"
                @click="fetchStudioExportJobs"
              >
                刷新任务
              </el-button>
            </div>
            <div v-if="studioExportJobs.length" class="studio-export-jobs-toolbar">
              <el-input
                v-model="studioExportJobSearchKeyword"
                clearable
                size="small"
                placeholder="按任务名、ID、状态、报错搜索"
                class="studio-export-jobs-toolbar__search"
              />
              <span class="studio-export-jobs-toolbar__summary">
                {{ filteredStudioExportJobs.length }} / {{ studioExportJobs.length }}
              </span>
            </div>
            <div
              v-if="filteredStudioExportJobs.length"
              class="studio-history-list studio-history-list--exports"
            >
              <article
                v-for="job in filteredStudioExportJobs"
                :key="`studio-export-${job.id}`"
                class="studio-history-log studio-history-log--export"
              >
                <div class="studio-history-log__head">
                  <div class="studio-history-log__title">
                    {{ job.title || job.id }}
                  </div>
                  <el-tag
                    size="small"
                    :type="getStudioExportJobStatusTagType(job.status)"
                  >
                    {{
                      job.status_label ||
                      getStudioExportJobStatusLabel(job.status)
                    }}
                  </el-tag>
                </div>
                <div class="studio-history-log__meta">
                  {{ buildStudioExportJobMeta(job) }}
                </div>
                <div
                  v-if="job.failure_diagnostic"
                  class="studio-export-failure-card"
                >
                  <div class="studio-export-failure-card__title">
                    {{ job.failure_diagnostic.title }}
                  </div>
                  <div
                    v-if="job.failure_diagnostic.sourceTarget"
                    class="studio-export-failure-card__line"
                  >
                    片段：{{ job.failure_diagnostic.sourceTarget }}
                  </div>
                  <div class="studio-export-failure-card__line">
                    原因：{{ job.failure_diagnostic.reason }}
                  </div>
                  <div
                    v-if="job.failure_diagnostic.suggestion"
                    class="studio-export-failure-card__hint"
                  >
                    {{ job.failure_diagnostic.suggestion }}
                  </div>
                </div>
                <div
                  v-if="job.error_message"
                  class="studio-history-log__meta studio-history-log__meta--error"
                >
                  {{ job.error_message }}
                </div>
                <div class="studio-history-log__footer">
                  <span>{{ formatTime(job.updated_at || job.created_at) }}</span>
                  <div class="studio-history-log__actions">
                    <el-button
                      v-if="job.failure_diagnostic?.clipId"
                      text
                      size="small"
                      @click="focusStudioExportFailureClip(job)"
                    >
                      定位片段
                    </el-button>
                    <el-button
                      v-if="job.failure_diagnostic?.action === 'open-materials'"
                      text
                      size="small"
                      @click="openProjectMaterialsLibrary(job)"
                    >
                      检查素材
                    </el-button>
                    <el-button
                      v-if="job.result_asset_id"
                      text
                      type="primary"
                      size="small"
                      @click="openStudioExportResult(job)"
                    >
                      查看结果
                    </el-button>
                    <el-button
                      v-if="job.can_retry"
                      text
                      size="small"
                      @click="retryStudioExportJob(job)"
                    >
                      重试
                    </el-button>
                    <el-button
                      v-if="isStudioExportJobCancelable(job)"
                      text
                      size="small"
                      @click="cancelStudioExportJob(job)"
                    >
                      取消
                    </el-button>
                    <el-button
                      v-if="isStudioExportJobDeletable(job)"
                      text
                      type="danger"
                      size="small"
                      @click="deleteStudioExportJob(job)"
                    >
                      删除
                    </el-button>
                  </div>
                </div>
              </article>
            </div>
            <div
              v-else-if="studioExportJobs.length"
              class="studio-empty-state studio-empty-state--compact"
            >
              <el-empty description="没有匹配的导出任务" :image-size="48" />
            </div>
            <div v-else class="studio-empty-state studio-empty-state--compact">
              <el-empty description="导出任务会显示在这里" :image-size="48" />
            </div>
            <div class="studio-note-card">
              当前任务记录已持久化；真正后台无感继续执行，要等后端正式渲染接入后再完全成立。
            </div>
          </div>
        </template>
      </aside>
    </section>

    <section class="studio-action-bar">
      <div class="studio-action-bar__summary">
        {{ footerSummary }}
        <span v-if="studioDraftSavedAtLabel" class="studio-action-bar__draft">
          草稿已保存于 {{ studioDraftSavedAtLabel }}
        </span>
      </div>
      <div class="studio-action-bar__buttons">
        <el-button plain :disabled="activeStepIndex === 0" @click="goPrevStep">
          上一步
        </el-button>
        <el-button plain @click="pauseStudioEditing">暂停制作</el-button>
        <el-button
          v-if="activeStep !== 'art'"
          type="primary"
          :loading="primaryActionLoading"
          @click="runPrimaryAction"
        >
          {{ primaryActionLabel }}
        </el-button>
        <el-button plain :disabled="!canMoveForward" @click="goNextStep">
          {{ activeStep === "export" ? "保持当前步骤" : "下一步" }}
        </el-button>
      </div>
    </section>

    <el-dialog
      v-model="chapterPreviewVisible"
      class="studio-dialog"
      width="min(760px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div v-if="previewChapter" class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Chapter Preview</div>
            <div class="studio-dialog-headline">{{ previewChapter.title }}</div>
            <div class="studio-dialog-copy">
              {{ previewChapter.summary }}
            </div>
          </div>
          <div class="studio-dialog-hero__meta">
            <span
              >章节 {{ String(previewChapter.index).padStart(2, "0") }}</span
            >
            <span>字数 {{ previewChapterWordCount }}</span>
            <span>比例 {{ scriptDraft.aspectRatio }}</span>
          </div>
        </div>
      </template>
      <div v-if="previewChapter" class="studio-dialog-body">
        <section class="studio-dialog-panel">
          <div class="studio-dialog-panel__head">
            <div class="studio-card__title">章节内容</div>
            <div class="studio-card__meta">用于后续设定与分镜生成</div>
          </div>
          <div class="studio-dialog-rich-copy">
            {{ previewChapter.content }}
          </div>
        </section>
      </div>
    </el-dialog>

    <el-dialog
      v-model="extractionDialogVisible"
      class="studio-dialog studio-dialog--extraction"
      width="min(920px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Foundation Extraction</div>
            <div class="studio-dialog-headline">基础元素提取结果</div>
            <div class="studio-dialog-copy">
              已根据当前剧本章节统一生成角色、场景和道具候选项，确认后会一并写入基础设定区。
            </div>
          </div>
          <div class="studio-dialog-hero__meta">
            <span>{{ extractionScopeLabel }}</span>
            <span>{{ artSettings.model }}</span>
            <span>{{ artSettings.duration }}</span>
            <span>{{ artSettings.quality }}</span>
          </div>
        </div>
      </template>

      <div class="studio-dialog-body studio-dialog-body--extraction">
        <section class="studio-dialog-panel">
          <div class="studio-dialog-panel__head">
            <div class="studio-card__title">本次任务摘要</div>
            <div class="studio-card__meta">用于本轮 AI 提取</div>
          </div>
          <div class="studio-dialog-summary-grid">
            <div class="studio-dialog-summary-card">
              <span>涉及章节</span>
              <strong>{{ chapters.length }}</strong>
            </div>
            <div class="studio-dialog-summary-card">
              <span>已选风格</span>
              <strong>{{ selectedStyleCount }}</strong>
            </div>
            <div class="studio-dialog-summary-card">
              <span>候选总数</span>
              <strong>{{ extractionResults.length }}</strong>
            </div>
            <div class="studio-dialog-summary-card">
              <span>覆盖分类</span>
              <strong>{{ extractionResultGroups.length }}</strong>
            </div>
            <div class="studio-dialog-summary-card">
              <span>待确认项</span>
              <strong>{{ extractionPendingResults.length }}</strong>
            </div>
          </div>
        </section>

        <section
          v-for="group in extractionResultGroups"
          :key="group.value"
          class="studio-dialog-section"
        >
          <div class="studio-dialog-section__head">
            <div>
              <div class="studio-card__title">{{ group.label }}</div>
              <div class="studio-card__meta">
                写入后会进入对应分类的基础设定区
              </div>
            </div>
            <span class="studio-pill">{{ group.items.length }} 项</span>
          </div>
          <div
            class="studio-dialog-summary-grid studio-dialog-summary-grid--compact"
          >
            <div class="studio-dialog-summary-card">
              <span>已识别</span>
              <strong>{{ group.detectedCount }}</strong>
            </div>
            <div class="studio-dialog-summary-card">
              <span>待确认</span>
              <strong>{{ group.pendingCount }}</strong>
            </div>
          </div>
          <div class="studio-result-grid studio-result-grid--dialog">
            <article
              v-for="item in group.items"
              :key="item.id"
              class="studio-result-card studio-result-card--extraction"
            >
              <div class="studio-result-card__top">
                <span class="studio-result-card__kind">{{ group.label }}</span>
                <span
                  class="studio-result-card__status"
                  :class="
                    item.status === 'pending' ? 'is-pending' : 'is-detected'
                  "
                >
                  {{ elementStatusLabel(item.status) }}
                </span>
              </div>
              <div class="studio-result-card__title">{{ item.name }}</div>
              <div class="studio-result-card__meta">
                {{
                  item.status === "pending"
                    ? "会保留为待确认状态，写入后可继续补充或替换。"
                    : "会直接沉淀为本轮基础设定候选。"
                }}
              </div>
            </article>
          </div>
        </section>

        <div class="studio-dialog-note">
          写入后会覆盖现有 AI
          提取结果，但会保留你已经手动补录的角色、场景和道具项。
        </div>
      </div>
      <template #footer>
        <div class="studio-dialog-footer">
          <div class="studio-dialog-footer__hint">
            确认无误后再统一写入基础设定
          </div>
          <el-button @click="extractionDialogVisible = false"
            >返回调整</el-button
          >
          <el-button type="primary" @click="confirmExtraction">
            写入基础设定
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="characterDialogVisible"
      class="studio-dialog studio-dialog--character"
      width="min(1240px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div v-if="activeCharacter" class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Character Config</div>
            <div class="studio-dialog-headline">{{ activeCharacter.name }}</div>
            <div class="studio-dialog-copy">
              为角色稳定四视图和角色级音色，避免后续镜头和配音设定漂移。
            </div>
          </div>
          <div class="studio-dialog-hero__meta">
            <span>{{ elementStatusLabel(activeCharacter.status) }}</span>
          </div>
        </div>
      </template>
      <div
        v-if="activeCharacter"
        class="studio-dialog-body studio-dialog-body--character-form"
      >
        <section class="studio-dialog-section">
          <div
            class="studio-dialog-section__head studio-dialog-section__head--stacked"
          >
            <div>
              <div class="studio-dialog-section__title">角色级音色配置</div>
              <div class="studio-dialog-section__desc">
                这里决定角色在整条短片里的默认配音气质。
              </div>
            </div>
          </div>
          <div class="studio-voice-grid studio-voice-grid--character">
            <button
              type="button"
              class="studio-voice-card"
              :class="{ 'is-active': !characterForm.voiceRecordId && !characterForm.voicePreset }"
              @click="clearCharacterVoiceSelection"
            >
              <span class="studio-voice-card__title">暂不绑定</span>
              <span class="studio-voice-card__meta">
                分镜阶段再为单个镜头单独选择旁白音色
              </span>
            </button>
            <button
              v-for="option in characterVoiceOptions"
              :key="option.id"
              type="button"
              class="studio-voice-card"
              :class="{ 'is-active': characterForm.voiceRecordId === option.id }"
              @click="selectCharacterVoiceOption(option)"
            >
              <span class="studio-voice-card__title">{{ option.name }}</span>
              <span class="studio-voice-card__meta">{{ option.hint }}</span>
            </button>
          </div>
          <div
            v-if="!loadingStudioProjectVoices && !characterVoiceOptions.length"
            class="studio-inline-note"
          >
            当前项目还没有可复用音色，请先在项目音色库创建，再回到这里绑定角色默认配音。
          </div>
          <div
            v-else-if="characterForm.voicePreset && !characterForm.voiceRecordId"
            class="studio-inline-note"
          >
            当前角色沿用了旧音色标记「{{ characterForm.voicePreset }}」，建议改绑到项目音色库里的真实音色。
          </div>
        </section>

        <section class="studio-dialog-section">
          <div class="studio-dialog-section__head">
            <div>
              <div class="studio-dialog-section__title">角色四视图参考</div>
              <div class="studio-dialog-section__desc">
                正面、背面、左侧、右侧分别单独维护；先绑定至少一张参考图后，才会开放 AI 补全生成。
              </div>
            </div>
            <span class="studio-pill">
              已配置 {{ activeCharacterReferenceCount }} /
              {{ characterViews.length }}
            </span>
          </div>
          <div class="studio-character-list">
            <article
              v-for="view in characterViews"
              :key="view.value"
              class="studio-character-row"
            >
              <div class="studio-character-row__label">
                <span class="studio-character-row__name">{{ view.label }}</span>
                <span class="studio-character-row__caption"
                  >统一角色形象参考</span
                >
              </div>
              <div class="studio-character-row__body">
                <div class="studio-character-row__preview">
                  <img
                    v-if="resolveCharacterReferencePreview(view.value)"
                    :src="resolveCharacterReferencePreview(view.value)"
                    :alt="`${activeCharacter.name}-${view.label}`"
                    class="studio-character-row__image"
                  />
                  <div v-else class="studio-character-row__placeholder">
                    暂未绑定参考图
                  </div>
                </div>
                <div class="studio-character-row__content">
                  <div class="studio-character-row__head">
                    <div class="studio-character-row__title">
                      {{ view.label }}视图
                    </div>
                    <span
                      class="studio-character-row__status"
                      :class="{
                        'is-bound': resolveCharacterReference(view.value),
                      }"
                    >
                      {{
                        resolveCharacterReference(view.value)
                          ? "已绑定"
                          : "待配置"
                      }}
                    </span>
                  </div>
                  <div class="studio-character-row__meta">
                    {{
                      resolveCharacterReference(view.value)?.title ||
                      "可从当前项目素材库选择，或本地上传后自动入库"
                    }}
                  </div>
                  <div class="studio-character-row__actions">
                    <el-button
                      v-if="canGenerateCharacterReferences"
                      type="primary"
                      plain
                      size="small"
                      @click="openCharacterGenerateDialog(view.value)"
                    >
                      AI 生成
                    </el-button>
                    <el-button
                      plain
                      size="small"
                      @click="openCharacterMaterialPicker(view.value)"
                    >
                      从素材库选择
                    </el-button>
                    <el-button
                      plain
                      size="small"
                      @click="openCharacterUploadDialog(view.value)"
                    >
                      上传并入库
                    </el-button>
                    <el-button
                      v-if="resolveCharacterReference(view.value)"
                      text
                      type="danger"
                      size="small"
                      @click="clearCharacterReference(view.value)"
                    >
                      清空
                    </el-button>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </section>
      </div>
      <template #footer>
        <div class="studio-dialog-footer">
          <div class="studio-dialog-footer__hint">保存后将写入当前角色设定</div>
          <el-button @click="characterDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="saveCharacterConfig">
            保存配置
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="characterMaterialDialogVisible"
      class="studio-dialog studio-dialog--reference"
      width="min(960px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Reference Library</div>
            <div class="studio-dialog-headline">
              {{ activeCharacterReferenceView.label }}参考图选择
            </div>
            <div class="studio-dialog-copy">
              从当前项目素材库选择图片素材，绑定到角色四视图参考。
            </div>
          </div>
          <div class="studio-dialog-hero__meta">
            <span>{{ activeCharacter?.name || "当前角色" }}</span>
            <span>图片素材 {{ characterReferenceMaterials.length }}</span>
          </div>
        </div>
      </template>
      <div class="studio-dialog-body studio-dialog-body--split">
        <div class="studio-dialog-column studio-dialog-column--side">
          <section class="studio-dialog-panel">
            <div class="studio-reference-toolbar">
              <el-input
                v-model="characterMaterialSearch"
                placeholder="搜索素材标题"
                clearable
                @keyup.enter="fetchCharacterReferenceMaterials"
              />
              <el-button
                plain
                :loading="loadingCharacterReferenceMaterials"
                @click="fetchCharacterReferenceMaterials"
              >
                刷新
              </el-button>
              <el-button plain @click="openMaterialLibrary">
                打开素材库
              </el-button>
              <el-button
                type="primary"
                plain
                @click="openCharacterUploadDialog(characterReferenceViewKey)"
              >
                上传并入库
              </el-button>
            </div>
          </section>
        </div>
        <div class="studio-dialog-column studio-dialog-column--main">
          <section
            v-if="characterReferenceMaterials.length"
            class="studio-reference-grid"
          >
            <article
              v-for="material in characterReferenceMaterials"
              :key="material.id"
              class="studio-reference-card"
              :class="{
                'is-active': isCharacterReferenceSelected(
                  characterReferenceViewKey,
                  material.id,
                ),
              }"
            >
              <div class="studio-reference-card__preview">
                <img
                  v-if="resolveMaterialPreview(material)"
                  :src="resolveMaterialPreview(material)"
                  :alt="material.title || material.id"
                  class="studio-reference-card__image"
                />
                <div v-else class="studio-reference-card__placeholder">
                  无预览
                </div>
              </div>
              <div class="studio-reference-card__body">
                <div class="studio-reference-card__title">
                  {{ material.title || material.id }}
                </div>
                <div class="studio-reference-card__meta">
                  {{ material.summary || "项目图片素材" }}
                </div>
              </div>
              <div class="studio-reference-card__actions">
                <el-button
                  type="primary"
                  size="small"
                  @click="
                    applyCharacterReference(characterReferenceViewKey, material)
                  "
                >
                  选择这张
                </el-button>
              </div>
            </article>
          </section>

          <div v-else class="studio-empty-state studio-empty-state--compact">
            <el-empty
              description="当前项目还没有可选图片素材"
              :image-size="56"
            />
          </div>
        </div>
      </div>
    </el-dialog>

    <el-dialog
      v-model="characterGenerateDialogVisible"
      class="studio-dialog studio-dialog--upload"
      width="min(760px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Generate Reference</div>
            <div class="studio-dialog-headline">
              AI 生成{{ activeCharacterReferenceView.label }}参考图
            </div>
            <div class="studio-dialog-copy">
              基于当前已绑定的参考图补齐目标视图，勾选“角色四视图”后会一次返回
              front / back / left / right 四张图并自动绑定。
            </div>
          </div>
          <div class="studio-dialog-hero__meta">
            <span>{{ activeCharacter?.name || "当前角色" }}</span>
            <span>{{ characterGenerateForm.generateAllViews ? "角色四视图" : activeCharacterReferenceView.label }}</span>
          </div>
        </div>
      </template>
      <div class="studio-dialog-body">
        <section class="studio-dialog-panel">
          <div class="studio-form-grid">
            <label class="studio-field">
              <span class="studio-field__label">模型源</span>
              <el-select
                v-model="characterGenerateForm.providerId"
                :loading="loadingStudioModelSources"
                placeholder="选择图片模型源"
              >
                <el-option
                  v-for="option in artModelProviderOptions"
                  :key="option.id"
                  :label="option.name"
                  :value="option.id"
                />
              </el-select>
            </label>
            <label class="studio-field">
              <span class="studio-field__label">模型</span>
              <el-select
                v-model="characterGenerateForm.model"
                :loading="loadingStudioModelSources"
                placeholder="选择图片模型"
              >
                <el-option
                  v-for="option in characterGenerateModelOptions"
                  :key="option"
                  :label="option"
                  :value="option"
                />
              </el-select>
            </label>
          </div>
          <div class="studio-form-grid">
            <label class="studio-field studio-field--wide">
              <span class="studio-field__label">角色描述 / 提示词</span>
              <el-input
                v-model="characterGenerateForm.prompt"
                type="textarea"
                :rows="6"
                placeholder="输入可直接用于角色生图的提示词。建议写清年龄、服装、发型、画风和人物特征。"
              />
            </label>
          </div>
          <div class="studio-toggle-row">
            <el-checkbox v-model="characterGenerateForm.generateAllViews">
              角色四视图
            </el-checkbox>
            <span class="studio-inline-note">
              固定参数：1024x1024，1:1，自动风格，高质量。
            </span>
          </div>
          <div class="studio-inline-note">
            当前会参考已绑定的 {{ activeCharacterReferenceCount }} 张图片，尽量保持同一角色形象一致。
          </div>
          <div class="studio-inline-note">
            未勾选时只生成当前{{ activeCharacterReferenceView.label }}视图；勾选后会分别生成正面、背面、左侧、右侧四张图。
          </div>
        </section>
      </div>
      <template #footer>
        <div class="studio-dialog-footer">
          <div class="studio-dialog-footer__hint">
            生成结果会自动入项目素材库并回填角色参考图
          </div>
          <el-button @click="characterGenerateDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="generatingCharacterReferences"
            @click="submitCharacterReferenceGeneration"
          >
            开始生成
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="characterUploadDialogVisible"
      class="studio-dialog studio-dialog--upload"
      width="min(760px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Upload To Library</div>
            <div class="studio-dialog-headline">
              上传{{ activeCharacterReferenceView.label }}参考图
            </div>
            <div class="studio-dialog-copy">
              本地图片会先加入当前项目素材库，再自动绑定到当前视图。
            </div>
          </div>
          <div class="studio-dialog-hero__meta">
            <span>{{ activeCharacter?.name || "当前角色" }}</span>
            <span>{{ characterUploadFileName || "未选择文件" }}</span>
          </div>
        </div>
      </template>
      <div class="studio-dialog-body studio-dialog-body--split">
        <div class="studio-dialog-column studio-dialog-column--side">
          <section class="studio-dialog-panel">
            <div class="studio-reference-upload-head">
              <input
                ref="characterUploadFileInputRef"
                class="studio-hidden-input"
                type="file"
                accept="image/*"
                @change="handleCharacterUploadFileChange"
              />
              <el-button plain @click="triggerCharacterUploadFilePicker">
                {{ characterUploadFileName ? "重新选择图片" : "选择本地图片" }}
              </el-button>
              <span class="studio-reference-upload-hint">
                建议上传角色标准视图图，后续分镜会直接复用这组参考。
              </span>
            </div>
            <div
              v-if="characterUploadForm.preview_url"
              class="studio-reference-upload-preview"
            >
              <img
                :src="characterUploadForm.preview_url"
                :alt="characterUploadForm.title || '角色参考图'"
                class="studio-reference-upload-preview__image"
              />
            </div>
          </section>
        </div>
        <div class="studio-dialog-column studio-dialog-column--main">
          <section class="studio-dialog-panel">
            <ProjectMaterialFormFields
              :form="characterUploadForm"
              :label-width="108"
              :asset-type-options="[{ value: 'image', label: '图片' }]"
              :mime-type-options="imageMimeTypeOptions"
              :show-asset-type="false"
              :show-link-fields="false"
              context-note="上传后会直接保存到当前项目素材库，并绑定到当前角色视图。"
            />
          </section>
        </div>
      </div>
      <template #footer>
        <div class="studio-dialog-footer">
          <div class="studio-dialog-footer__hint">
            保存后会自动写入素材库并选中当前视图
          </div>
          <el-button @click="characterUploadDialogVisible = false"
            >取消</el-button
          >
          <el-button
            type="primary"
            :loading="uploadingCharacterMaterial"
            @click="submitCharacterUpload"
          >
            保存并绑定
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="voiceDialogVisible"
      class="studio-dialog"
      width="min(560px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Voice Upload</div>
            <div class="studio-dialog-headline">
              {{ voiceTargetBoard?.title || "配置分镜旁白" }}
            </div>
            <div class="studio-dialog-copy">
              上传后该分镜会标记为可导出，并自动进入当前导出集合。
            </div>
          </div>
          <div v-if="voiceTargetBoard" class="studio-dialog-hero__meta">
            <span>{{ chapterTitleById(voiceTargetBoard.chapterId) }}</span>
            <span>{{ voiceTargetBoard.durationSeconds }} 秒</span>
            <span>
              {{
                voiceTargetBoard.hasVoice ? "当前已配置旁白" : "当前未配置旁白"
              }}
            </span>
          </div>
        </div>
      </template>
      <div class="studio-dialog-body">
        <section v-if="voiceTargetBoard" class="studio-dialog-panel">
          <div
            class="studio-dialog-summary-grid studio-dialog-summary-grid--compact"
          >
            <div class="studio-dialog-summary-card">
              <span>章节</span>
              <strong>{{
                chapterTitleById(voiceTargetBoard.chapterId)
              }}</strong>
            </div>
            <div class="studio-dialog-summary-card">
              <span>镜头时长</span>
              <strong>{{ voiceTargetBoard.durationSeconds }} 秒</strong>
            </div>
          </div>
        </section>
        <div class="studio-form-grid">
          <label class="studio-field">
            <span class="studio-field__label">模型源</span>
            <el-select
              v-model="voiceForm.providerId"
              :loading="loadingStudioModelSources"
              placeholder="选择模型源"
            >
              <el-option
                v-for="option in audioModelProviderOptions"
                :key="option.id"
                :label="option.name"
                :value="option.id"
              />
            </el-select>
          </label>
          <label class="studio-field">
            <span class="studio-field__label">配音模型</span>
            <el-select
              v-model="voiceForm.model"
              :loading="loadingStudioModelSources"
              placeholder="选择模型"
            >
              <el-option
                v-for="option in voiceModelOptions"
                :key="option"
                :label="option"
                :value="option"
              />
            </el-select>
          </label>
          <label class="studio-field">
            <span class="studio-field__label">音色</span>
            <el-select
              v-model="voiceForm.voice"
              :loading="loadingStudioProjectVoices"
              placeholder="选择音色"
            >
              <el-option
                v-for="option in voiceSelectableOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </label>
        </div>
        <div class="studio-form-grid">
          <label class="studio-field studio-field--wide">
            <span class="studio-field__label">旁白文本</span>
            <el-input
              v-model="voiceForm.text"
              type="textarea"
              :rows="4"
              placeholder="输入要生成的旁白文本"
            />
          </label>
          <label class="studio-field">
            <span class="studio-field__label">语速</span>
            <el-select v-model="voiceForm.speed">
              <el-option
                v-for="option in voiceSpeedOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </label>
        </div>
        <section v-if="voiceTargetBoard" class="studio-dialog-panel">
          <div class="studio-card__head">
            <div>
              <div class="studio-card__title">旁白音频</div>
              <div class="studio-card__meta">
                可直接生成，也可以上传真实旁白文件；正式导出会优先使用这里绑定的音频
              </div>
            </div>
          </div>
          <div class="studio-audio-source">
            <div class="studio-audio-source__summary">
              <strong>{{ voiceTargetBoardVoiceDisplayName }}</strong>
              <span v-if="voiceTargetBoardVoiceMimeType">
                {{ voiceTargetBoardVoiceMimeType }}
              </span>
              <span v-if="selectedVoiceOption?.label">
                {{ selectedVoiceOption.label }}
              </span>
            </div>
            <div class="studio-inline-actions">
              <el-button
                size="small"
                type="primary"
                :loading="generatingVoiceAudio"
                @click="generateVoiceAudio"
              >
                生成旁白
              </el-button>
              <el-button
                size="small"
                :loading="uploadingVoiceAudio"
                @click="openVoiceFilePicker"
              >
                {{ voiceTargetBoardHasRealAudio ? "替换旁白" : "上传旁白" }}
              </el-button>
              <el-button
                v-if="voiceTargetBoardHasRealAudio"
                size="small"
                text
                type="danger"
                @click="clearVoiceAudioAndPersist"
              >
                删除旁白
              </el-button>
            </div>
          </div>
          <div class="studio-card__meta">
            {{ voiceTargetBoardHasRealAudio ? "已绑定真实旁白音频" : "当前还没有真实旁白音频" }}
          </div>
          <input
            ref="voiceFileInputRef"
            class="studio-hidden-input"
            type="file"
            accept="audio/*"
            @change="handleVoiceFileChange"
          />
        </section>
      </div>
      <template #footer>
        <div class="studio-dialog-footer">
          <div class="studio-dialog-footer__hint">
            保存后该分镜会同步到导出集合
          </div>
          <el-button @click="voiceDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmVoiceGeneration">
            保存旁白
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="timelineAddDialogVisible"
      class="studio-dialog"
      width="min(520px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Timeline Add</div>
            <div class="studio-dialog-headline">
              {{ timelineCandidateTitle || "添加到视频轨道" }}
            </div>
            <div class="studio-dialog-copy">
              确认后会直接进入当前时间线，并同步到预览播放器。
            </div>
          </div>
          <div v-if="timelineCandidateMetaPrimary" class="studio-dialog-hero__meta">
            <span>{{ timelineCandidateMetaPrimary }}</span>
            <span>{{ timelineCandidateDurationSeconds }} 秒</span>
          </div>
        </div>
      </template>
      <div class="studio-dialog-body">
        <section v-if="timelineCandidateTitle" class="studio-dialog-panel">
          <div
            class="studio-dialog-summary-grid studio-dialog-summary-grid--compact"
          >
            <div class="studio-dialog-summary-card">
              <span>当前时间线</span>
              <strong>{{ timelineClips.length }} 段</strong>
            </div>
            <div class="studio-dialog-summary-card">
              <span>加入后总时长</span>
              <strong
                >{{
                  timelineDuration + timelineCandidateDurationSeconds
                }}
                秒</strong
              >
            </div>
            <div
              v-if="timelineCandidateMetaSecondary"
              class="studio-dialog-summary-card"
            >
              <span>来源</span>
              <strong>{{ timelineCandidateMetaSecondary }}</strong>
            </div>
          </div>
        </section>
      </div>
      <template #footer>
        <div class="studio-dialog-footer">
          <div class="studio-dialog-footer__hint">该操作会立即影响当前时间线</div>
          <el-button @click="timelineAddDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmAddToTimeline">
            确认添加
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="historyDialogVisible"
      class="studio-dialog studio-dialog--reference"
      width="min(920px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Reusable Clips</div>
            <div class="studio-dialog-headline">可回添片段</div>
            <div class="studio-dialog-copy">
              这里展示可重新加入当前时间线的历史分镜和素材库视频，素材库视频支持重复加入多个片段实例。
            </div>
          </div>
          <div class="studio-dialog-hero__meta">
            <span>候选 {{ availableTimelineCandidatesCount }} 个</span>
            <span>当前时间线 {{ timelineClips.length }} 段</span>
          </div>
        </div>
      </template>
      <div class="studio-dialog-body">
        <section
          v-if="availableHistoryStoryboards.length"
          class="studio-dialog-section"
        >
          <div class="studio-dialog-section__head">
            <div>
              <div class="studio-dialog-section__title">历史分镜</div>
              <div class="studio-dialog-section__desc">
                已配音但未在当前时间线中的分镜，可直接回添。
              </div>
            </div>
            <span class="studio-dialog-footer__hint">
              {{ availableHistoryStoryboards.length }} 个候选
            </span>
          </div>
          <div class="studio-history-grid">
            <button
              v-for="board in availableHistoryStoryboards"
              :key="`history-dialog-${board.id}`"
              type="button"
              class="studio-history-card"
              @click="openTimelineAddDialog('storyboard', board.id)"
            >
              <span class="studio-history-card__title">{{ board.title }}</span>
              <span class="studio-history-card__meta">
                {{ chapterTitleById(board.chapterId) }} ·
                {{ board.durationSeconds }} 秒
              </span>
            </button>
          </div>
        </section>

        <section
          v-if="availableTimelineVideoMaterials.length"
          class="studio-dialog-section"
        >
          <div class="studio-dialog-section__head">
            <div>
              <div class="studio-dialog-section__title">素材库视频</div>
              <div class="studio-dialog-section__desc">
                项目素材库中的视频资产，可直接作为现成片段加入时间线，并可重复使用。
              </div>
            </div>
            <span class="studio-dialog-footer__hint">
              {{ availableTimelineVideoMaterials.length }} 个候选
            </span>
          </div>
          <div class="studio-history-grid">
            <button
              v-for="material in availableTimelineVideoMaterials"
              :key="`history-dialog-material-${material.id}`"
              type="button"
              class="studio-history-card"
              @click="openTimelineAddDialog('material', material.id)"
            >
              <span class="studio-history-card__title">{{ material.title }}</span>
              <span class="studio-history-card__meta">
                {{ buildTimelineMaterialHistoryMeta(material) }}
              </span>
            </button>
          </div>
        </section>

        <div
          v-if="loadingTimelineVideoMaterials"
          class="studio-note-card"
        >
          正在加载素材库视频…
        </div>

        <div
          v-if="!availableTimelineCandidatesCount && !loadingTimelineVideoMaterials"
          class="studio-empty-state studio-empty-state--compact"
        >
          <el-empty description="当前没有可回添的分镜或素材视频" :image-size="48" />
        </div>
      </div>
      <template #footer>
        <div class="studio-dialog-footer">
          <div class="studio-dialog-footer__hint">
            需要时再回添，当前时间线不会自动变动
          </div>
          <el-button @click="historyDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="exportDialogVisible"
      class="studio-dialog studio-dialog--export"
      width="min(1160px, calc(100vw - 32px))"
      destroy-on-close
    >
      <template #header>
        <div class="studio-dialog-hero">
          <div class="studio-dialog-hero__copy">
            <div class="studio-dialog-hero__eyebrow">Video Export</div>
            <div class="studio-dialog-headline">导出视频</div>
            <div class="studio-dialog-copy">
              在这里统一编排导出镜头、调整时长，并确认输出格式与清晰度。
            </div>
          </div>
        </div>
      </template>
      <div class="studio-dialog-body studio-dialog-body--export">
        <section class="studio-card studio-card--timeline studio-dialog-panel">
          <div class="studio-card__head">
            <div class="studio-card__title">导出准备</div>
            <div class="studio-card__meta">
              确认进入本次导出的分镜，并在提交前核对时长
            </div>
          </div>

          <div v-if="visibleTimelineClips.length" class="studio-timeline-list">
            <article
              v-for="clip in visibleTimelineClips"
              :key="clip.id"
              class="studio-timeline-item"
            >
              <div>
                <div class="studio-timeline-item__title">
                  {{ clip.title }}
                </div>
                <div class="studio-timeline-item__meta">
                  {{ chapterTitleById(clip.chapterId) }}
                </div>
                <div class="studio-timeline-item__time">
                  {{ formatTimelineRange(clip) }}
                </div>
              </div>
              <div class="studio-duration-control">
                <span>时长</span>
                <strong class="studio-duration-control__value">
                  {{ clip.durationSeconds }}
                </strong>
                <span>秒</span>
              </div>
            </article>
          </div>

          <div v-else class="studio-empty-state studio-empty-state--compact">
            <el-empty description="当前没有导出分镜" :image-size="48" />
          </div>
        </section>

        <div
          class="studio-dialog-body studio-dialog-body--split studio-dialog-body--export-settings"
        >
          <div class="studio-dialog-column studio-dialog-column--main">
            <section class="studio-dialog-panel">
              <div class="studio-card__head">
                <div>
                  <div class="studio-card__title">导出设置</div>
                  <div class="studio-card__meta">
                    当前导出配置会作用到本次任务
                  </div>
                </div>
              </div>
              <div class="studio-form-grid studio-form-grid--export-dialog">
                <label class="studio-field">
                  <span class="studio-field__label">编码格式</span>
                  <el-select v-model="exportConfig.format">
                    <el-option
                      v-for="option in exportFormatOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </label>
                <label class="studio-field">
                  <span class="studio-field__label">清晰度</span>
                  <el-select v-model="exportConfig.resolution">
                    <el-option
                      v-for="option in exportResolutionOptions"
                      :key="option"
                      :label="option"
                      :value="option"
                    />
                  </el-select>
                </label>
              </div>
            </section>
          </div>

          <div class="studio-dialog-column studio-dialog-column--side">
            <section class="studio-dialog-panel">
              <div class="studio-card__head">
                <div>
                  <div class="studio-card__title">导出信息</div>
                  <div class="studio-card__meta">
                    提交前最后确认本次任务规模
                  </div>
                </div>
              </div>
              <div class="studio-summary-list">
                <div class="studio-summary-item">
                  <span>总时长</span>
                  <strong>{{ timelineDuration }} 秒</strong>
                </div>
                <div class="studio-summary-item">
                  <span>分镜数量</span>
                  <strong>{{ visibleTimelineClips.length }} 个</strong>
                </div>
                <div class="studio-summary-item">
                  <span>预计消耗</span>
                  <strong>{{ estimatedCredits }} 积分</strong>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="studio-dialog-footer">
          <div class="studio-dialog-footer__hint">
            确认后会创建正式导出任务，结果完成后自动进入项目素材库
          </div>
          <el-button @click="exportDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="exporting" @click="submitExport">
            提交导出
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import StudioActionMenu from "@/components/studio/StudioActionMenu.vue";
import StudioMergedPreview from "@/components/studio/StudioMergedPreview.vue";
import StudioTimelineEditor from "@/components/studio/StudioTimelineEditor.vue";
import ProjectMaterialFormFields from "@/components/ProjectMaterialFormFields.vue";
import api from "@/utils/api.js";
import { normalizeProviderModelConfigs } from "@/utils/llm-models.js";
import {
  MATERIAL_MIME_TYPE_OPTIONS,
  readVideoDurationFromUrl,
  resolveMaterialResourceUrl,
} from "@/utils/project-materials.js";

const route = useRoute();
const STUDIO_DRAFT_STORAGE_PREFIX = "studio.workbench.draft";

const stepItems = [
  {
    id: "script",
    title: "剧本创作",
    description: "输入内容并拆成章节",
  },
  {
    id: "art",
    title: "美术设定",
    description: "稳定风格和基础元素",
  },
  {
    id: "storyboard",
    title: "分镜制作",
    description: "生成镜头并补齐配音",
  },
  {
    id: "export",
    title: "导出视频",
    description: "编排时间线和导出参数",
  },
];

const aspectRatioOptions = ["16:9", "9:16", "1:1", "3:2", "2:3"];
const artDurationOptions = ["3秒", "5秒", "10秒"];
const storyboardDurationOptions = ["5秒", "8秒", "10秒"];
const qualityOptions = ["标准 (720p)", "高清 (1080p)", "超清 (4K)"];
const systemVoiceOptions = [
  { value: "tongtong", label: "通通", hint: "明亮女声" },
  { value: "xiaochen", label: "小辰", hint: "自然女声" },
  { value: "chuichui", label: "吹吹", hint: "轻快童声" },
  { value: "jam", label: "Jam", hint: "温和男声" },
  { value: "kazi", label: "卡兹", hint: "沉稳男声" },
  { value: "douji", label: "豆吉", hint: "亲和中性" },
  { value: "luodo", label: "洛朵", hint: "叙事感女声" },
];
const voiceSpeedOptions = [
  { value: 0.8, label: "0.8x 慢速" },
  { value: 1, label: "1.0x 标准" },
  { value: 1.2, label: "1.2x 快速" },
];
const exportFormatOptions = [
  { value: "mp4-h264", label: "MP4 (H.264)" },
  { value: "mp4-h265", label: "MP4 (H.265)" },
];
const exportResolutionOptions = ["720p", "1080p", "4K"];
const characterViews = [
  { value: "front", label: "正面" },
  { value: "back", label: "背面" },
  { value: "left", label: "左侧" },
  { value: "right", label: "右侧" },
];
const styleLabels = [
  "水墨",
  "3D国潮",
  "电影超写实",
  "卡通",
  "赛博朋克",
  "油画",
  "水彩",
  "像素风",
];
const elementKinds = [
  { value: "role", label: "角色" },
  { value: "scene", label: "场景" },
  { value: "prop", label: "道具" },
];
const projectTypeOptions = [
  { value: "image", label: "图片项目" },
  { value: "storyboard_video", label: "分镜视频项目" },
  { value: "mixed", label: "综合项目" },
];
const STUDIO_EXPORT_VIDEO_MIME_CANDIDATES = [
  "video/webm;codecs=vp9",
  "video/webm;codecs=vp8",
  "video/webm",
  "video/mp4",
];

let uid = 0;

function createId(prefix) {
  uid += 1;
  return `${prefix}-${uid}`;
}

function sanitizeExportFilename(value, fallback, extension) {
  const raw = String(value || "").trim() || fallback;
  const sanitized = raw.replace(/[^A-Za-z0-9\u4e00-\u9fa5._-]+/g, "-").replace(/^-+|-+$/g, "");
  return `${sanitized || fallback}.${extension}`;
}

function studioExportTimestamp() {
  const now = new Date();
  const date = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(
    now.getDate(),
  ).padStart(2, "0")}`;
  const time = `${String(now.getHours()).padStart(2, "0")}${String(
    now.getMinutes(),
  ).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`;
  return `${date}-${time}`;
}

function normalizeStudioModelProviders(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => {
      const modelConfigs = normalizeProviderModelConfigs(item)
        .map((model) => ({
          name: String(model?.name || "").trim(),
          modelType: String(model?.model_type || "").trim(),
        }))
        .filter((model) => model.name);
      const models = modelConfigs.map((model) => model.name);
      const defaultModel =
        String(item?.default_model || "").trim() || modelConfigs[0]?.name || "";
      return {
        id: String(item?.id || "").trim(),
        name: String(item?.name || item?.id || "未命名模型源").trim(),
        modelConfigs,
        models,
        defaultModel,
        isDefault: item?.is_default === true,
      };
    })
    .filter((item) => item.id && item.models.length);
}

function filterStudioModelProvidersByType(items, allowedModelTypes) {
  const allowedTypes = new Set(
    (Array.isArray(allowedModelTypes) ? allowedModelTypes : [allowedModelTypes])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  );
  if (!allowedTypes.size) {
    return Array.isArray(items) ? items : [];
  }
  return (Array.isArray(items) ? items : [])
    .map((provider) => {
      const modelConfigs = (
        Array.isArray(provider?.modelConfigs) ? provider.modelConfigs : []
      ).filter((item) => allowedTypes.has(String(item?.modelType || "").trim()));
      if (!modelConfigs.length) {
        return null;
      }
      const models = modelConfigs.map((item) => item.name);
      const defaultModel =
        modelConfigs.find(
          (item) => item.name === String(provider?.defaultModel || "").trim(),
        )?.name ||
        modelConfigs[0]?.name ||
        "";
      return {
        ...provider,
        modelConfigs,
        models,
        defaultModel,
      };
    })
    .filter(Boolean);
}

function resolveStudioProvider(providerId, providerOptions = studioModelProviderOptions.value) {
  const normalizedProviderId = String(providerId || "").trim();
  return (
    providerOptions.find((item) => item.id === normalizedProviderId) ||
    providerOptions.find((item) => item.isDefault) ||
    providerOptions[0] ||
    null
  );
}

function resolveStudioProviderModels(
  providerId,
  providerOptions = studioModelProviderOptions.value,
) {
  return resolveStudioProvider(providerId, providerOptions)?.models || [];
}

function normalizeStudioProjectVoices(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => {
      const sampleAudio =
        item?.sample_audio && typeof item.sample_audio === "object"
          ? item.sample_audio
          : {};
      const voiceId = String(item?.voice_id || "").trim();
      if (!voiceId) return null;
      return {
        id: String(item?.id || "").trim(),
        name: String(item?.name || item?.provider_voice_name || voiceId).trim(),
        voiceId,
        providerId: String(item?.provider_id || "").trim(),
        modelName: String(item?.model_name || "").trim(),
        description: String(item?.description || "").trim(),
        previewText: String(item?.preview_text || "").trim(),
        sampleAudio,
      };
    })
    .filter(Boolean);
}

function buildEmptyCharacterVoiceSelection() {
  return {
    voicePreset: "",
    voiceRecordId: "",
    voiceId: "",
    providerId: "",
    modelName: "",
    voiceLabel: "",
  };
}

function readCharacterVoiceSelection(source) {
  const container = source && typeof source === "object" ? source : {};
  const characterVoice =
    container.characterVoice && typeof container.characterVoice === "object"
      ? container.characterVoice
      : container;
  return {
    voicePreset: String(container.voicePreset || characterVoice.voicePreset || "").trim(),
    voiceRecordId: String(
      characterVoice.voiceRecordId || characterVoice.voice_record_id || "",
    ).trim(),
    voiceId: String(
      characterVoice.voiceId || characterVoice.voice_id || characterVoice.voice || "",
    ).trim(),
    providerId: String(
      characterVoice.providerId || characterVoice.provider_id || "",
    ).trim(),
    modelName: String(
      characterVoice.modelName || characterVoice.model_name || characterVoice.model || "",
    ).trim(),
    voiceLabel: String(
      characterVoice.voiceLabel || characterVoice.voice_label || "",
    ).trim(),
  };
}

function resolveStudioProjectVoiceMatch(selection) {
  const normalized = readCharacterVoiceSelection(selection);
  if (normalized.voiceRecordId) {
    const exact = studioProjectVoices.value.find(
      (item) => item.id === normalized.voiceRecordId,
    );
    if (exact) return exact;
  }
  if (normalized.providerId && normalized.voiceId) {
    const exact = studioProjectVoices.value.find(
      (item) =>
        item.providerId === normalized.providerId &&
        item.voiceId === normalized.voiceId,
    );
    if (exact) return exact;
  }
  const legacyLabel = normalized.voiceLabel || normalized.voicePreset;
  if (!legacyLabel) return null;
  return (
    studioProjectVoices.value.find(
      (item) => String(item.name || "").trim() === legacyLabel,
    ) || null
  );
}

function normalizeCharacterVoiceSelection(selection) {
  const normalized = {
    ...buildEmptyCharacterVoiceSelection(),
    ...readCharacterVoiceSelection(selection),
  };
  const matchedVoice = resolveStudioProjectVoiceMatch(normalized);
  if (matchedVoice) {
    return {
      voicePreset: matchedVoice.name,
      voiceRecordId: matchedVoice.id,
      voiceId: matchedVoice.voiceId,
      providerId: matchedVoice.providerId,
      modelName: matchedVoice.modelName,
      voiceLabel: matchedVoice.name,
    };
  }
  const fallbackLabel = normalized.voiceLabel || normalized.voicePreset;
  return {
    ...normalized,
    voicePreset: fallbackLabel,
    voiceLabel: fallbackLabel,
  };
}

function serializeCharacterVoiceSelection(selection) {
  const normalized = normalizeCharacterVoiceSelection(selection);
  return {
    voicePreset: normalized.voicePreset,
    characterVoice: normalized.voiceRecordId
      ? {
          voiceRecordId: normalized.voiceRecordId,
          voiceId: normalized.voiceId,
          providerId: normalized.providerId,
          modelName: normalized.modelName,
          voiceLabel: normalized.voiceLabel,
        }
      : {},
  };
}

function hasCharacterVoiceSelection(selection) {
  const normalized = normalizeCharacterVoiceSelection(selection);
  return Boolean(normalized.voiceRecordId || normalized.voicePreset);
}

function resolveVoiceSpeedValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return voiceSpeedOptions[1]?.value || 1;
  }
  return Math.max(0.5, Math.min(2, numeric));
}

function filterVoiceGenerationModels(items) {
  const values = (Array.isArray(items) ? items : []).map((item) =>
    String(item || "").trim(),
  ).filter(Boolean);
  const nonCloneModels = values.filter((item) => !/clone/i.test(item));
  return nonCloneModels.length ? nonCloneModels : values;
}

function syncStudioModelSelection(target, providerOptions = studioModelProviderOptions.value) {
  if (!target || typeof target !== "object") return;
  const provider = resolveStudioProvider(target.providerId, providerOptions);
  if (!provider) {
    target.providerId = "";
    target.model = "";
    return;
  }
  target.providerId = provider.id;
  const currentModel = String(target.model || "").trim();
  const availableModels = Array.isArray(provider.models) ? provider.models : [];
  if (availableModels.includes(currentModel)) return;
  target.model = provider.defaultModel || availableModels[0] || "";
}

function resolveStudioExportCanvasSize(aspectRatio, resolution) {
  const normalizedRatio = String(aspectRatio || "16:9").trim() || "16:9";
  const [rawWidth, rawHeight] = normalizedRatio.split(":");
  const ratioWidth = Math.max(1, Number.parseInt(rawWidth, 10) || 16);
  const ratioHeight = Math.max(1, Number.parseInt(rawHeight, 10) || 9);
  const longEdge =
    resolution === "4K" ? 1120 : resolution === "1080p" ? 920 : 720;
  if (ratioWidth >= ratioHeight) {
    return {
      width: longEdge,
      height: Math.max(360, Math.round((longEdge * ratioHeight) / ratioWidth)),
    };
  }
  return {
    width: Math.max(360, Math.round((longEdge * ratioWidth) / ratioHeight)),
    height: longEdge,
  };
}

function chooseStudioExportVideoMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  if (typeof MediaRecorder.isTypeSupported !== "function") {
    return STUDIO_EXPORT_VIDEO_MIME_CANDIDATES[0];
  }
  return (
    STUDIO_EXPORT_VIDEO_MIME_CANDIDATES.find((item) =>
      MediaRecorder.isTypeSupported(item),
    ) || ""
  );
}

function wrapStudioCanvasText(ctx, text, maxWidth, maxLines = 2) {
  const source = String(text || "").trim();
  if (!source) return [];
  const chars = Array.from(source);
  const lines = [];
  let current = "";
  for (const char of chars) {
    const candidate = `${current}${char}`;
    if (ctx.measureText(candidate).width <= maxWidth) {
      current = candidate;
      continue;
    }
    if (current) {
      lines.push(current);
    }
    current = char;
    if (lines.length >= maxLines - 1) break;
  }
  if (current && lines.length < maxLines) {
    const remaining =
      lines.length === maxLines - 1 && chars.join("").length > lines.join("").length + current.length;
    lines.push(remaining && current.length > 1 ? `${current.slice(0, -1)}…` : current);
  }
  return lines.slice(0, maxLines);
}

function renderStudioExportCanvas(canvas, payload) {
  const width = Number(canvas?.width || 0);
  const height = Number(canvas?.height || 0);
  const ctx = canvas?.getContext?.("2d");
  if (!ctx || !width || !height) return;

  const progress = Math.max(0, Math.min(1, Number(payload?.progress ?? 1)));
  const title = String(payload?.title || "短片导出预览").trim() || "短片导出预览";
  const subtitle = String(payload?.subtitle || "").trim();
  const clipTitles = Array.isArray(payload?.clipTitles) ? payload.clipTitles : [];
  const meta = Array.isArray(payload?.meta) ? payload.meta.filter(Boolean) : [];

  const gradient = ctx.createLinearGradient(0, 0, width, height);
  gradient.addColorStop(0, "#0f172a");
  gradient.addColorStop(0.55, "#164e63");
  gradient.addColorStop(1, "#f59e0b");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);

  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.beginPath();
  ctx.arc(width * 0.12, height * 0.18, Math.min(width, height) * 0.22, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(width * 0.86, height * 0.28, Math.min(width, height) * 0.18, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "rgba(255,255,255,0.14)";
  ctx.fillRect(width * 0.08, height * 0.78, width * 0.84, 8);
  ctx.fillStyle = "#f8fafc";
  ctx.fillRect(width * 0.08, height * 0.78, width * 0.84 * progress, 8);

  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.font = `600 ${Math.max(18, Math.round(width * 0.028))}px sans-serif`;
  ctx.fillText("Studio Export Preview", width * 0.08, height * 0.16);

  ctx.fillStyle = "#ffffff";
  ctx.font = `700 ${Math.max(28, Math.round(width * 0.06))}px sans-serif`;
  const titleLines = wrapStudioCanvasText(ctx, title, width * 0.7, 2);
  titleLines.forEach((line, index) => {
    ctx.fillText(line, width * 0.08, height * (0.3 + index * 0.11));
  });

  if (subtitle) {
    ctx.fillStyle = "rgba(255,255,255,0.88)";
    ctx.font = `500 ${Math.max(18, Math.round(width * 0.026))}px sans-serif`;
    const subtitleLines = wrapStudioCanvasText(ctx, subtitle, width * 0.74, 2);
    subtitleLines.forEach((line, index) => {
      ctx.fillText(line, width * 0.08, height * (0.53 + index * 0.06));
    });
  }

  if (clipTitles.length) {
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.font = `500 ${Math.max(16, Math.round(width * 0.022))}px sans-serif`;
    clipTitles.slice(0, 3).forEach((line, index) => {
      ctx.fillText(`· ${line}`, width * 0.08, height * (0.66 + index * 0.05));
    });
  }

  if (meta.length) {
    ctx.fillStyle = "rgba(255,255,255,0.82)";
    ctx.font = `500 ${Math.max(16, Math.round(width * 0.02))}px sans-serif`;
    ctx.fillText(meta.join(" / "), width * 0.08, height * 0.75);
  }

  ctx.fillStyle = "#0f172a";
  ctx.globalAlpha = 0.18;
  ctx.fillRect(width * 0.76, height * 0.14, width * 0.14, width * 0.14);
  ctx.globalAlpha = 1;
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve, reject) => {
    if (!canvas?.toBlob) {
      reject(new Error("当前环境不支持画布导出"));
      return;
    }
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("生成预览文件失败"));
          return;
        }
        resolve(blob);
      },
      type,
      quality,
    );
  });
}

async function buildStudioExportArtifacts(payload) {
  if (typeof window === "undefined" || typeof document === "undefined") {
    throw new Error("当前环境不支持导出预览生成");
  }
  if (typeof HTMLCanvasElement === "undefined") {
    throw new Error("当前浏览器不支持画布导出");
  }
  if (typeof MediaRecorder === "undefined") {
    throw new Error("当前浏览器不支持视频导出预览");
  }

  const mimeType = chooseStudioExportVideoMimeType();
  if (!mimeType) {
    throw new Error("当前浏览器不支持可用的视频编码格式");
  }

  const { width, height } = resolveStudioExportCanvasSize(
    payload.aspectRatio,
    payload.resolution,
  );
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  renderStudioExportCanvas(canvas, {
    ...payload,
    progress: 0,
  });

  const stream = canvas.captureStream(12);
  const recorder = new MediaRecorder(stream, { mimeType });
  const chunks = [];
  const stopPromise = new Promise((resolve, reject) => {
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        chunks.push(event.data);
      }
    };
    recorder.onerror = (event) => {
      reject(event?.error || new Error("录制导出预览失败"));
    };
    recorder.onstop = () => resolve();
  });

  const durationMs = 1400;
  recorder.start(200);
  const startedAt = performance.now();
  await new Promise((resolve) => {
    const tick = (timestamp) => {
      const elapsed = timestamp - startedAt;
      const progress = Math.min(1, elapsed / durationMs);
      renderStudioExportCanvas(canvas, {
        ...payload,
        progress,
      });
      if (progress >= 1) {
        resolve();
        return;
      }
      window.requestAnimationFrame(tick);
    };
    window.requestAnimationFrame(tick);
  });
  recorder.stop();
  await stopPromise;
  stream.getTracks().forEach((track) => track.stop());

  const videoBlob = new Blob(chunks, { type: recorder.mimeType || mimeType });
  if (!videoBlob.size) {
    throw new Error("导出预览内容为空");
  }
  renderStudioExportCanvas(canvas, {
    ...payload,
    progress: 1,
  });
  const coverBlob = await canvasToBlob(canvas, "image/png");

  const normalizedMimeType = String(videoBlob.type || recorder.mimeType || mimeType).trim();
  const extension = normalizedMimeType.includes("mp4") ? "mp4" : "webm";
  const timestamp = studioExportTimestamp();
  const baseName = sanitizeExportFilename(payload.title, `studio-export-${timestamp}`, extension);
  const coverName = sanitizeExportFilename(`${payload.title || "studio-export"}-cover`, `studio-export-cover-${timestamp}`, "png");

  return {
    videoFile: new File([videoBlob], baseName, {
      type: normalizedMimeType,
      lastModified: Date.now(),
    }),
    coverFile: new File([coverBlob], coverName, {
      type: "image/png",
      lastModified: Date.now(),
    }),
  };
}

function normalizeCharacterReferenceItem(item) {
  if (!item || typeof item !== "object") return null;
  const previewUrl = resolveMaterialResourceUrl(
    item.previewUrl ||
      item.preview_url ||
      item.contentUrl ||
      item.content_url ||
      "",
  );
  const contentUrl = resolveMaterialResourceUrl(
    item.contentUrl ||
      item.content_url ||
      item.previewUrl ||
      item.preview_url ||
      "",
  );
  return {
    ...item,
    assetId: String(item.assetId || item.asset_id || "").trim(),
    title: String(item.title || "").trim(),
    previewUrl,
    contentUrl,
    mimeType: String(item.mimeType || item.mime_type || "").trim(),
    summary: String(item.summary || "").trim(),
  };
}

function cloneCharacterReferenceViews(source) {
  return characterViews.reduce((accumulator, view) => {
    const item = normalizeCharacterReferenceItem(source?.[view.value]);
    if (item) accumulator[view.value] = item;
    return accumulator;
  }, {});
}

function buildCharacterUploadForm() {
  return {
    asset_type: "image",
    title: "",
    summary: "",
    preview_url: "",
    content_url: "",
    mime_type: "",
    structured_content_text: "",
    metadata_text: "",
  };
}

function buildCharacterGenerateForm() {
  return {
    providerId: "",
    model: "",
    prompt: "",
    generateAllViews: false,
  };
}

const projectId = computed(() => String(route.query.project_id || "").trim());
const requestedStudioDraftJobId = computed(() =>
  String(route.query.draft_job_id || "").trim(),
);
const requestedStudioExportJobId = computed(() =>
  String(route.query.export_job_id || "").trim(),
);

const activeStep = ref("script");
const scriptFileInputRef = ref(null);
const scriptDraft = reactive({
  content:
    "清晨的城市被晨光缓慢点亮，主角带着一个秘密任务走进街角咖啡馆。\n\n她需要在今天之内找到失联的旧友，并弄清楚一段被隐藏的视频记录。\n\n随着故事推进，城市、人物和道具都会逐步进入同一条镜头线索。",
  sourceFileName: "",
  aspectRatio: "16:9",
});
const styles = ref(
  styleLabels.map((label, index) => ({
    id: `style-${index + 1}`,
    label,
    selected: index === 0 || index === 2,
  })),
);
const chapters = ref([]);
const previewChapterId = ref("");
const chapterPreviewVisible = ref(false);
const studioModelProviders = ref([]);
const studioProjectVoices = ref([]);
const loadingStudioModelSources = ref(false);
const loadingStudioProjectVoices = ref(false);

const artSettings = reactive({
  kind: "role",
  providerId: "",
  model: "",
  duration: artDurationOptions[1],
  quality: qualityOptions[1],
});
const elements = ref([]);
const extractionDialogVisible = ref(false);
const extractionResults = ref([]);
const extracting = ref(false);

const activeCharacterId = ref("");
const characterDialogVisible = ref(false);
const characterForm = reactive({
  ...buildEmptyCharacterVoiceSelection(),
  referenceViews: {},
});
const characterReferenceMaterials = ref([]);
const loadingCharacterReferenceMaterials = ref(false);
const characterMaterialDialogVisible = ref(false);
const characterReferenceViewKey = ref(characterViews[0].value);
const characterMaterialSearch = ref("");
const characterGenerateDialogVisible = ref(false);
const generatingCharacterReferences = ref(false);
const characterUploadDialogVisible = ref(false);
const characterUploadFileInputRef = ref(null);
const characterUploadFileName = ref("");
const characterUploadSelectedFile = ref(null);
const uploadingCharacterMaterial = ref(false);
const characterGenerateForm = reactive(buildCharacterGenerateForm());
const characterUploadForm = reactive(buildCharacterUploadForm());

const storyboardSettings = reactive({
  chapterId: "",
  providerId: "",
  model: "",
  duration: storyboardDurationOptions[1],
  quality: qualityOptions[1],
  sfx: false,
});
const storyboards = ref([]);
const generatingStoryboards = ref(false);
const timelineVideoMaterials = ref([]);
const loadingTimelineVideoMaterials = ref(false);
const resolvingTimelineMaterialDurationIds = new Set();

const voiceDialogVisible = ref(false);
const voiceTargetId = ref("");
const voiceFileInputRef = ref(null);
const uploadingVoiceAudio = ref(false);
const generatingVoiceAudio = ref(false);
const voiceForm = reactive({
  providerId: "",
  model: "",
  voice: systemVoiceOptions[0].value,
  text: "",
  speed: voiceSpeedOptions[1].value,
});

const timelineClips = ref([]);
const timelineAudioTracks = ref([]);
const activeTimelineClipId = ref("");
const historyDialogVisible = ref(false);
const timelineAddDialogVisible = ref(false);
const timelineCandidateSourceType = ref("storyboard");
const timelineCandidateId = ref("");
const exportDialogVisible = ref(false);
const exportBgmFileInputRef = ref(null);
const uploadingExportBgm = ref(false);
const exportConfig = reactive({
  format: exportFormatOptions[0].value,
  resolution: exportResolutionOptions[1],
  bgmEnabled: false,
  bgmSourceType: "",
  bgmTitle: "",
  bgmUrl: "",
  bgmFileName: "",
  bgmMimeType: "",
  bgmStoragePath: "",
  videoMuted: false,
  videoVolume: 1,
  voiceMuted: false,
  voiceVolume: 1,
  bgmMuted: false,
  bgmVolume: 0.56,
});
const exporting = ref(false);
const studioExportJobs = ref([]);
const studioExportJobSearchKeyword = ref("");
const loadingStudioExportJobs = ref(false);
const pendingStudioDraft = ref(null);
const studioDraftWorkId = ref("");
const studioDraftSavedAt = ref("");
const studioDraftResumeDismissed = ref(false);
const hydratingStudioDraft = ref(false);
const studioDraftAutosaveReady = ref(false);
let studioDraftAutosaveTimer = 0;
let studioExportJobsPollTimer = 0;

const activeStepIndex = computed(() =>
  stepItems.findIndex((item) => item.id === activeStep.value),
);
const activeStepMeta = computed(
  () => stepItems[activeStepIndex.value] || stepItems[0],
);
const showStudioDraftResume = computed(
  () => Boolean(pendingStudioDraft.value) && !studioDraftResumeDismissed.value,
);
const pendingStudioDraftSavedLabel = computed(() =>
  pendingStudioDraft.value?.savedAt
    ? formatTime(pendingStudioDraft.value.savedAt)
    : "刚刚",
);
const pendingStudioDraftStepLabel = computed(() => {
  const stepId = String(pendingStudioDraft.value?.activeStep || "").trim();
  return stepItems.find((item) => item.id === stepId)?.title || "当前步骤";
});
const studioDraftSavedAtLabel = computed(() =>
  studioDraftSavedAt.value ? formatTime(studioDraftSavedAt.value) : "",
);
const scriptLength = computed(() => String(scriptDraft.content || "").length);
const selectedStyleCount = computed(
  () => styles.value.filter((item) => item.selected).length,
);
const selectedStyleLabels = computed(() =>
  styles.value
    .filter((item) => item.selected)
    .map((item) => String(item.label || "").trim())
    .filter(Boolean),
);
const studioModelProviderOptions = computed(() =>
  (Array.isArray(studioModelProviders.value) ? studioModelProviders.value : []).filter(
    (item) => String(item.id || "").trim(),
  ),
);
const artModelProviderOptions = computed(() =>
  filterStudioModelProvidersByType(studioModelProviderOptions.value, "image_generation"),
);
const storyboardModelProviderOptions = computed(() =>
  filterStudioModelProvidersByType(studioModelProviderOptions.value, "video_generation"),
);
const audioModelProviderOptions = computed(() =>
  filterStudioModelProvidersByType(studioModelProviderOptions.value, "audio_generation"),
);
const artModelOptions = computed(() =>
  resolveStudioProviderModels(artSettings.providerId, artModelProviderOptions.value),
);
const characterGenerateModelOptions = computed(() =>
  resolveStudioProviderModels(
    characterGenerateForm.providerId,
    artModelProviderOptions.value,
  ),
);
const storyboardModelOptions = computed(() =>
  resolveStudioProviderModels(
    storyboardSettings.providerId,
    storyboardModelProviderOptions.value,
  ),
);
const voiceModelOptions = computed(() =>
  filterVoiceGenerationModels(
    resolveStudioProviderModels(voiceForm.providerId, audioModelProviderOptions.value),
  ),
);
const availableProjectVoiceOptions = computed(() =>
  studioProjectVoices.value
    .filter((item) => item.providerId === String(voiceForm.providerId || "").trim())
    .map((item) => ({
      value: item.voiceId,
      label: item.name,
      hint: item.description || "项目自定义音色",
      sourceType: "project",
      voiceRecordId: item.id,
      providerId: item.providerId,
      modelName: item.modelName,
    })),
);
const characterVoiceOptions = computed(() =>
  studioProjectVoices.value.map((item) => ({
    id: item.id,
    name: item.name,
    voiceId: item.voiceId,
    providerId: item.providerId,
    modelName: item.modelName,
    hint:
      item.description ||
      [String(item.providerId || "").trim(), String(item.modelName || "").trim()]
        .filter(Boolean)
        .join(" · ") ||
      "项目音色库",
  })),
);
const currentVoiceProvider = computed(
  () =>
    audioModelProviderOptions.value.find(
      (item) => item.id === String(voiceForm.providerId || "").trim(),
    ) || null,
);
const currentProviderSupportsSystemVoices = computed(() =>
  Boolean(
    currentVoiceProvider.value?.models?.some((item) =>
      /^glm-tts/i.test(String(item || "").trim()),
    ),
  ),
);
const voiceSelectableOptions = computed(() => [
  ...availableProjectVoiceOptions.value,
  ...(currentProviderSupportsSystemVoices.value
    ? systemVoiceOptions.map((item) => ({
        ...item,
        sourceType: "system",
        voiceRecordId: "",
      }))
    : []),
]);
const detectedElementCount = computed(
  () => elements.value.filter((item) => item.status !== "pending").length,
);
const activeElements = computed(() =>
  elements.value.filter((item) => item.kind === artSettings.kind),
);
const extractionResultGroups = computed(() =>
  elementKinds
    .map((kind) => {
      const items = extractionResults.value.filter(
        (item) => item.kind === kind.value,
      );
      if (!items.length) return null;
      return {
        ...kind,
        items,
        detectedCount: items.filter((item) => item.status !== "pending").length,
        pendingCount: items.filter((item) => item.status === "pending").length,
      };
    })
    .filter(Boolean),
);
const extractionPendingResults = computed(() =>
  extractionResults.value.filter((item) => item.status === "pending"),
);
const extractionScopeLabel = computed(() =>
  elementKinds.map((item) => item.label).join(" / "),
);
const activeElementKindLabel = computed(
  () =>
    elementKinds.find((item) => item.value === artSettings.kind)?.label ||
    "角色",
);
const configuredRoleCount = computed(
  () =>
    elements.value.filter(
      (item) => item.kind === "role" && hasCharacterVoiceSelection(item.metadata),
    ).length,
);
const currentChapterStoryboards = computed(() =>
  storyboards.value.filter(
    (item) =>
      item.chapterId === String(storyboardSettings.chapterId || "").trim(),
  ),
);
const storyboardHistory = computed(() =>
  [...storyboards.value]
    .sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)))
    .slice(0, 8),
);
const voicedStoryboardCount = computed(
  () => storyboards.value.filter((item) => item.hasVoice).length,
);
const selectedStoryboards = computed(() =>
  storyboards.value.filter((item) => item.hasVoice && item.selected),
);
const visibleTimelineClips = computed(() =>
  timelineClips.value.filter((item) => item.visible !== false),
);
const timelineDuration = computed(() =>
  visibleTimelineClips.value.reduce(
    (total, item) => total + Number(item.durationSeconds || 0),
    0,
  ),
);
const estimatedCredits = computed(() =>
  Math.max(0, timelineDuration.value * 30),
);
const exportBgmResolvedUrl = computed(() =>
  resolveMaterialResourceUrl(exportConfig.bgmUrl || ""),
);
const exportBgmDisplayName = computed(
  () =>
    String(exportConfig.bgmTitle || "").trim() ||
    String(exportConfig.bgmFileName || "").trim() ||
    "背景音乐",
);
const studioAudioMix = computed(() => ({
  videoMuted: Boolean(exportConfig.videoMuted),
  videoVolume: normalizeStudioAudioMixVolume(exportConfig.videoVolume, 1),
  voiceMuted: Boolean(exportConfig.voiceMuted),
  voiceVolume: normalizeStudioAudioMixVolume(exportConfig.voiceVolume, 1),
  bgmMuted: Boolean(exportConfig.bgmMuted),
  bgmVolume: normalizeStudioAudioMixVolume(exportConfig.bgmVolume, 0.56),
}));
const exportBgmActionItems = computed(() => {
  const items = [
    {
      id: "upload",
      label: exportConfig.bgmUrl ? "替换背景音乐" : "上传背景音乐",
      description: "选择本地音频文件并保存到当前项目",
      disabled: uploadingExportBgm.value,
    },
  ];
  if (exportConfig.bgmUrl) {
    items.push({
      id: "clear",
      label: "删除当前背景音乐",
      description: "移除当前 BGM 并立即保存草稿",
      danger: true,
    });
  }
  return items;
});
const voiceTargetBoard = computed(
  () =>
    storyboards.value.find((item) => item.id === voiceTargetId.value) || null,
);
const voiceTargetBoardHasRealAudio = computed(() =>
  Boolean(resolveStoryboardVoiceResolvedUrl(voiceTargetBoard.value)),
);
const voiceTargetBoardVoiceDisplayName = computed(
  () =>
    resolveStoryboardVoiceDisplayName(voiceTargetBoard.value) || "尚未上传旁白音频",
);
const voiceTargetBoardVoiceMimeType = computed(() =>
  resolveStoryboardVoiceMimeType(voiceTargetBoard.value),
);
const selectedVoiceOption = computed(
  () =>
    voiceSelectableOptions.value.find(
      (item) => item.value === String(voiceForm.voice || "").trim(),
    ) || null,
);
const availableHistoryStoryboards = computed(() => {
  const timelineIds = new Set(
    timelineClips.value
      .filter((item) => String(item.sourceType || "storyboard").trim() !== "material")
      .map((item) => String(item.storyboardId || item.sourceId || "").trim()),
  );
  return storyboards.value.filter(
    (item) => item.hasVoice && !timelineIds.has(String(item.id || "").trim()),
  );
});
const availableTimelineVideoMaterials = computed(() => {
  return timelineVideoMaterials.value.filter(
    (item) =>
      String(item.status || "ready").trim() === "ready" &&
      Boolean(
        resolveMaterialResourceUrl(item.content_url || item.preview_url || ""),
      ),
  );
});
const availableTimelineCandidatesCount = computed(
  () =>
    availableHistoryStoryboards.value.length +
    availableTimelineVideoMaterials.value.length,
);
const hasRunningStudioExportJobs = computed(() =>
  studioExportJobs.value.some((item) =>
    ["queued", "processing"].includes(String(item.status || "").trim()),
  ),
);
const filteredStudioExportJobs = computed(() => {
  const keyword = String(studioExportJobSearchKeyword.value || "")
    .trim()
    .toLowerCase();
  if (!keyword) return studioExportJobs.value;
  return studioExportJobs.value.filter((job) => {
    const diagnostic = job?.failure_diagnostic || {};
    const haystacks = [
      job?.title,
      job?.id,
      job?.status,
      job?.status_label,
      job?.error_message,
      diagnostic?.title,
      diagnostic?.sourceTarget,
      diagnostic?.reason,
      diagnostic?.assetId,
      diagnostic?.clipId,
      buildStudioExportJobMeta(job),
    ]
      .map((value) => String(value || "").trim().toLowerCase())
      .filter(Boolean);
    return haystacks.some((value) => value.includes(keyword));
  });
});
const timelineCandidateTitle = computed(() => {
  if (timelineCandidateSourceType.value === "material") {
    return timelineCandidateMaterial.value?.title || "";
  }
  return timelineCandidateBoard.value?.title || "";
});
const previewChapter = computed(
  () =>
    chapters.value.find((item) => item.id === previewChapterId.value) || null,
);
const previewChapterWordCount = computed(
  () => String(previewChapter.value?.content || "").replace(/\s+/g, "").length,
);
const activeCharacter = computed(
  () =>
    elements.value.find((item) => item.id === activeCharacterId.value) || null,
);
const activeCharacterReferenceCount = computed(
  () =>
    Object.values(characterForm.referenceViews || {}).filter(
      (item) =>
        item && typeof item === "object" && String(item.assetId || "").trim(),
    ).length,
);
const activeCharacterReferenceSourceUrls = computed(() => {
  const urls = [];
  const seen = new Set();
  for (const item of Object.values(characterForm.referenceViews || {})) {
    const normalized = normalizeCharacterReferenceItem(item);
    if (!normalized) continue;
    for (const candidate of [normalized.contentUrl, normalized.previewUrl]) {
      const resolved = String(candidate || "").trim();
      if (!resolved || seen.has(resolved)) continue;
      seen.add(resolved);
      urls.push(resolved);
    }
  }
  return urls;
});
const canGenerateCharacterReferences = computed(
  () => activeCharacterReferenceSourceUrls.value.length > 0,
);
const activeCharacterReferenceView = computed(
  () =>
    characterViews.find(
      (item) => item.value === characterReferenceViewKey.value,
    ) || characterViews[0],
);
const imageMimeTypeOptions = computed(() =>
  MATERIAL_MIME_TYPE_OPTIONS.filter((item) =>
    String(item.value || "").startsWith("image/"),
  ),
);
const timelineCandidateBoard = computed(
  () =>
    storyboards.value.find((item) => item.id === timelineCandidateId.value) ||
    null,
);
const timelineCandidateMaterial = computed(
  () =>
    timelineVideoMaterials.value.find(
      (item) => String(item.id || "").trim() === timelineCandidateId.value,
    ) || null,
);
const timelineCandidateDurationSeconds = computed(() => {
  if (timelineCandidateSourceType.value === "material") {
    return resolveTimelineMaterialDurationSeconds(timelineCandidateMaterial.value);
  }
  return Number(timelineCandidateBoard.value?.durationSeconds || 0);
});
const timelineCandidateMetaPrimary = computed(() => {
  if (timelineCandidateSourceType.value === "material") {
    return "素材库视频";
  }
  if (timelineCandidateBoard.value) {
    return chapterTitleById(timelineCandidateBoard.value.chapterId);
  }
  return "";
});
const timelineCandidateMetaSecondary = computed(() => {
  if (timelineCandidateSourceType.value === "material") {
    return buildTimelineMaterialSourceLabel(timelineCandidateMaterial.value);
  }
  return "历史分镜";
});
const timelineMaterialLibraryChapterId = "__material_library__";
const footerSummary = computed(() => {
  if (activeStep.value === "script") {
    return chapters.value.length
      ? `已拆分 ${chapters.value.length} 个章节，可进入设定阶段。`
      : "先输入剧本，再把故事拆成可推进的章节。";
  }
  if (activeStep.value === "art") {
    return detectedElementCount.value
      ? `已沉淀 ${detectedElementCount.value} 个基础元素，可进入分镜阶段。`
      : "先统一提取角色、场景和道具，再推进镜头生成。";
  }
  if (activeStep.value === "storyboard") {
    return selectedStoryboards.value.length
      ? `已有 ${selectedStoryboards.value.length} 个已配音分镜进入导出集合。`
      : "至少选择 1 个已配音分镜，才能进入导出阶段。";
  }
  return `当前展示 ${visibleTimelineClips.value.length} 个片段，总时长 ${timelineDuration.value} 秒。`;
});
const canMoveForward = computed(() => {
  if (activeStep.value === "script") return chapters.value.length > 0;
  if (activeStep.value === "art") return detectedElementCount.value > 0;
  if (activeStep.value === "storyboard")
    return selectedStoryboards.value.length > 0;
  return true;
});
const primaryActionLabel = computed(() => {
  if (activeStep.value === "script") return "智能分章";
  if (activeStep.value === "art") return "开始提取";
  if (activeStep.value === "storyboard") return "生成当前章节分镜";
  return exporting.value ? "导出中..." : "打开导出面板";
});
const primaryActionLoading = computed(() => {
  if (activeStep.value === "art") return extracting.value;
  if (activeStep.value === "storyboard") return generatingStoryboards.value;
  if (activeStep.value === "export") return exporting.value;
  return false;
});

function chapterTitleById(chapterId) {
  if (String(chapterId || "").trim() === timelineMaterialLibraryChapterId) {
    return "素材库视频";
  }
  return (
    chapters.value.find((item) => item.id === chapterId)?.title || "未命名章节"
  );
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(
    date.getMinutes(),
  ).padStart(2, "0")}`;
}

function getStudioExportJobStatusLabel(status) {
  if (status === "processing") return "处理中";
  if (status === "succeeded") return "已完成";
  if (status === "failed") return "失败";
  if (status === "canceled") return "已取消";
  return "排队中";
}

function getStudioExportJobStatusTagType(status) {
  if (status === "processing") return "warning";
  if (status === "succeeded") return "success";
  if (status === "failed") return "danger";
  if (status === "canceled") return "info";
  return "";
}

function normalizeStudioExportErrorMessage(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function getStudioExportJobFailureDiagnostic(job) {
  const errorDetails =
    job?.error_details && typeof job.error_details === "object"
      ? job.error_details
      : null;
  if (errorDetails?.kind === "unresolved_visual_source") {
    return {
      kind: "source_missing",
      title: "未找到真实素材",
      clipId: String(errorDetails.clip_id || "").trim(),
      assetId: String(errorDetails.asset_id || "").trim(),
      sourceTarget:
        String(errorDetails.clip_title || "").trim() ||
        String(errorDetails.clip_id || "").trim(),
      reason:
        String(errorDetails.reason || "").trim() ||
        normalizeStudioExportErrorMessage(job?.error_message),
      suggestion: "请检查素材库文件、素材链接或重新上传后再重试。",
      action: "open-materials",
    };
  }
  if (errorDetails?.kind === "ffmpeg_missing") {
    return {
      kind: "ffmpeg_missing",
      title: "服务器缺少渲染依赖",
      clipId: "",
      assetId: "",
      sourceTarget: "",
      reason:
        String(errorDetails.reason || "").trim() ||
        normalizeStudioExportErrorMessage(job?.error_message),
      suggestion: "需要先在服务端安装 FFmpeg，导出任务才能继续执行。",
      action: "",
    };
  }
  const errorMessage = normalizeStudioExportErrorMessage(job?.error_message);
  if (!errorMessage) return null;
  const unresolvedMatch = errorMessage.match(
    /^片段\s+(.+?)\s+缺少可渲染素材：(.+)$/,
  );
  if (unresolvedMatch) {
    return {
      kind: "source_missing",
      title: "未找到真实素材",
      clipId: "",
      assetId: "",
      sourceTarget: String(unresolvedMatch[1] || "").trim(),
      reason: String(unresolvedMatch[2] || "").trim() || errorMessage,
      suggestion: "请检查素材库文件、素材链接或重新上传后再重试。",
      action: "open-materials",
    };
  }
  if (errorMessage.includes("FFmpeg")) {
    return {
      kind: "ffmpeg_missing",
      title: "服务器缺少渲染依赖",
      clipId: "",
      assetId: "",
      sourceTarget: "",
      reason: errorMessage,
      suggestion: "需要先在服务端安装 FFmpeg，导出任务才能继续执行。",
      action: "",
    };
  }
  return null;
}

function normalizeStudioExportJob(job) {
  if (!job || typeof job !== "object") return job;
  return {
    ...job,
    failure_diagnostic: getStudioExportJobFailureDiagnostic(job),
  };
}

function isStudioExportListJob(job) {
  const sourceType = String(job?.source_type || "").trim();
  const status = String(job?.status || "").trim();
  return sourceType !== "studio_draft" && status !== "draft";
}

function buildStudioExportJobMeta(job) {
  const formatLabel =
    String(job?.export_format_label || "").trim() ||
    exportFormatOptions.find((item) => item.value === job?.export_format)?.label ||
    "MP4";
  const segments = [
    formatLabel,
    String(job?.export_resolution || "").trim(),
    `${Number(job?.progress || 0)}%`,
  ].filter(Boolean);
  if (Number(job?.timeline_duration_seconds || 0) > 0) {
    segments.push(`${job.timeline_duration_seconds} 秒`);
  }
  if (Number(job?.clip_count || 0) > 0) {
    segments.push(`${job.clip_count} 个分镜`);
  }
  return segments.join(" · ");
}

async function fetchStudioExportJobs() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    studioExportJobs.value = [];
    return;
  }
  loadingStudioExportJobs.value = true;
  try {
    const previousResultAssetIds = new Set(
      studioExportJobs.value
        .filter((item) => String(item?.status || "").trim() === "succeeded")
        .map((item) => String(item?.result_asset_id || "").trim())
        .filter(Boolean),
    );
    const data = await api.get(`/projects/${currentProjectId}/studio/exports`, {
      params: {
        source_type: "studio_export",
        limit: 20,
      },
    });
    const nextItems = Array.isArray(data?.items)
      ? data.items
          .map((item) => normalizeStudioExportJob(item))
          .filter((item) => isStudioExportListJob(item))
      : [];
    studioExportJobs.value = nextItems;
    const hasNewSucceededAsset = nextItems.some((item) => {
      if (String(item?.status || "").trim() !== "succeeded") return false;
      const assetId = String(item?.result_asset_id || "").trim();
      return assetId && !previousResultAssetIds.has(assetId);
    });
    if (hasNewSucceededAsset) {
      await fetchTimelineVideoMaterials();
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载导出任务失败");
  } finally {
    loadingStudioExportJobs.value = false;
  }
}

function startStudioExportJobsPolling() {
  if (typeof window === "undefined" || studioExportJobsPollTimer) return;
  studioExportJobsPollTimer = window.setInterval(() => {
    void fetchStudioExportJobs();
  }, 10000);
}

function stopStudioExportJobsPolling() {
  if (typeof window === "undefined" || !studioExportJobsPollTimer) return;
  window.clearInterval(studioExportJobsPollTimer);
  studioExportJobsPollTimer = 0;
}

function isStudioExportJobCancelable(job) {
  if (!isStudioExportListJob(job)) return false;
  const status = String(job?.status || "").trim();
  return status === "queued" || status === "processing";
}

function isStudioExportJobDeletable(job) {
  if (!isStudioExportListJob(job)) return false;
  const status = String(job?.status || "").trim();
  return Boolean(status) && !isStudioExportJobCancelable(job);
}

async function cancelStudioExportJob(job) {
  const currentProjectId = String(projectId.value || "").trim();
  const jobId = String(job?.id || "").trim();
  const jobTitle = String(job?.title || "").trim() || jobId;
  if (!currentProjectId || !jobId) return;
  try {
    await ElMessageBox.confirm(
      `确认取消导出任务「${jobTitle}」？`,
      "取消任务",
      {
        type: "warning",
        customClass: "studio-message-box",
      },
    );
  } catch {
    return;
  }
  try {
    await api.post(`/projects/${currentProjectId}/studio/exports/${jobId}/cancel`);
    await fetchStudioExportJobs();
    ElMessage.success("导出任务已取消");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "取消导出任务失败");
  }
}

async function retryStudioExportJob(job) {
  const currentProjectId = String(projectId.value || "").trim();
  const jobId = String(job?.id || "").trim();
  if (!currentProjectId || !jobId) return;
  try {
    await api.post(`/projects/${currentProjectId}/studio/exports/${jobId}/retry`);
    await fetchStudioExportJobs();
    ElMessage.success("已创建重试任务");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "重试导出任务失败");
  }
}

async function deleteStudioExportJob(job) {
  const currentProjectId = String(projectId.value || "").trim();
  const jobId = String(job?.id || "").trim();
  const jobTitle = String(job?.title || "").trim() || jobId;
  if (!currentProjectId || !jobId) return;
  try {
    await ElMessageBox.confirm(
      `确认删除导出任务「${jobTitle}」？删除后将无法恢复该记录。`,
      "删除任务",
      {
        type: "warning",
        customClass: "studio-message-box",
      },
    );
  } catch {
    return;
  }
  try {
    await api.delete(`/projects/${currentProjectId}/studio/exports/${jobId}`);
    studioExportJobs.value = studioExportJobs.value.filter(
      (item) => String(item?.id || "").trim() !== jobId,
    );
    ElMessage.success("导出任务已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除导出任务失败");
  }
}

function openStudioExportResult(job) {
  const assetId = String(job?.result_asset_id || "").trim();
  if (!assetId) return;
  const existingMaterial = timelineVideoMaterials.value.find(
    (item) => String(item.id || "").trim() === assetId,
  );
  const targetUrl = resolveMaterialResourceUrl(
    existingMaterial?.content_url || existingMaterial?.preview_url || "",
  );
  if (targetUrl && typeof window !== "undefined") {
    window.open(targetUrl, "_blank", "noopener");
    return;
  }
  router.push({
    path: "/materials",
    query: {
      project_id: String(projectId.value || "").trim(),
    },
  });
}

function openProjectMaterialsLibrary(job = null) {
  const currentProjectId = String(projectId.value || "").trim();
  const focusAssetId = String(job?.failure_diagnostic?.assetId || "").trim();
  router.push({
    path: "/materials",
    query: {
      project_id: currentProjectId,
      ...(focusAssetId ? { focus_asset_id: focusAssetId } : {}),
    },
  });
}

async function focusStudioExportFailureClip(job) {
  const clipId = String(job?.failure_diagnostic?.clipId || "").trim();
  if (!clipId) return;
  const exists = timelineClips.value.some(
    (item) => String(item?.id || "").trim() === clipId,
  );
  if (!exists) {
    ElMessage.warning("当前时间线里已找不到这个失败片段，请检查素材后重新整理导出片段。");
    return;
  }
  activeStep.value = "export";
  setActiveTimelineClip(clipId);
  await nextTick();
  if (typeof document === "undefined") return;
  const target = Array.from(
    document.querySelectorAll("[data-studio-timeline-clip-id]"),
  ).find((node) => node.dataset.studioTimelineClipId === clipId);
  if (typeof target?.scrollIntoView === "function") {
    target.scrollIntoView({
      behavior: "smooth",
      block: "center",
      inline: "nearest",
    });
  }
}

function studioDraftStorageKey(currentProjectId) {
  const normalizedProjectId = String(currentProjectId || "").trim() || "default";
  return `${STUDIO_DRAFT_STORAGE_PREFIX}.${normalizedProjectId}`;
}

function cloneStudioDraftValue(value, fallback) {
  if (value === undefined) return fallback;
  return JSON.parse(JSON.stringify(value));
}

function buildStudioDraftSnapshot() {
  const characterVoiceSelection = normalizeCharacterVoiceSelection(characterForm);
  const snapshot = {
    version: 1,
    projectId: String(projectId.value || "").trim(),
    workId: String(studioDraftWorkId.value || "").trim(),
    savedAt: new Date().toISOString(),
    activeStep: activeStep.value,
    scriptDraft: cloneStudioDraftValue(scriptDraft, {}),
    styles: cloneStudioDraftValue(styles.value, []),
    chapters: cloneStudioDraftValue(chapters.value, []),
    artSettings: cloneStudioDraftValue(artSettings, {}),
    elements: cloneStudioDraftValue(elements.value, []),
    extractionResults: cloneStudioDraftValue(extractionResults.value, []),
    characterForm: cloneStudioDraftValue(
      {
        ...characterVoiceSelection,
        referenceViews: characterForm.referenceViews,
      },
      {},
    ),
    storyboardSettings: cloneStudioDraftValue(storyboardSettings, {}),
    storyboards: cloneStudioDraftValue(storyboards.value, []),
    timelineClips: cloneStudioDraftValue(timelineClips.value, []),
    activeTimelineClipId: String(activeTimelineClipId.value || "").trim(),
    exportConfig: cloneStudioDraftValue(exportConfig, {}),
  };
  return sanitizeStudioDraftSnapshot(snapshot).snapshot;
}

function readStudioDraft() {
  if (typeof window === "undefined") return null;
  const key = studioDraftStorageKey(projectId.value);
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeStudioDraft(snapshot, { announce = false } = {}) {
  if (typeof window === "undefined") return;
  const key = studioDraftStorageKey(projectId.value);
  window.localStorage.setItem(key, JSON.stringify(snapshot));
  studioDraftWorkId.value = String(snapshot?.workId || "").trim();
  pendingStudioDraft.value = snapshot;
  studioDraftSavedAt.value = String(snapshot.savedAt || "").trim();
  studioDraftResumeDismissed.value = true;
  if (announce) {
    ElMessage.success("已保存制作草稿，下次可继续编辑");
  }
}

async function persistStudioDraftSilently(snapshot = buildStudioDraftSnapshot()) {
  const normalizedSnapshot = sanitizeStudioDraftSnapshot(snapshot).snapshot;
  try {
    if (String(studioDraftWorkId.value || normalizedSnapshot.workId || "").trim()) {
      const persistedSnapshot = await saveStudioDraftToWorks(normalizedSnapshot);
      writeStudioDraft(persistedSnapshot, { announce: false });
      return persistedSnapshot;
    }
  } catch {
    // Keep local draft even if remote save fails.
  }
  writeStudioDraft(normalizedSnapshot, { announce: false });
  return normalizedSnapshot;
}

function scheduleStudioDraftAutosave() {
  if (!studioDraftAutosaveReady.value || hydratingStudioDraft.value) return;
  if (typeof window === "undefined") return;
  window.clearTimeout(studioDraftAutosaveTimer);
  studioDraftAutosaveTimer = window.setTimeout(() => {
    writeStudioDraft(buildStudioDraftSnapshot());
  }, 600);
}

function applyStudioDraft(snapshot, { announce = false } = {}) {
  if (!snapshot || typeof snapshot !== "object") return;
  const normalizedSnapshot = sanitizeStudioDraftSnapshot(snapshot).snapshot;
  hydratingStudioDraft.value = true;
  try {
    activeStep.value =
      stepItems.find((item) => item.id === normalizedSnapshot.activeStep)?.id ||
      stepItems[0].id;

    Object.assign(scriptDraft, {
      content:
        typeof normalizedSnapshot.scriptDraft?.content === "string"
          ? normalizedSnapshot.scriptDraft.content
          : "",
      sourceFileName: String(normalizedSnapshot.scriptDraft?.sourceFileName || "").trim(),
      aspectRatio:
        aspectRatioOptions.find(
          (item) => item === String(normalizedSnapshot.scriptDraft?.aspectRatio || "").trim(),
        ) || aspectRatioOptions[0],
    });

    styles.value = Array.isArray(normalizedSnapshot.styles)
      ? cloneStudioDraftValue(normalizedSnapshot.styles, [])
      : [];
    chapters.value = Array.isArray(normalizedSnapshot.chapters)
      ? cloneStudioDraftValue(normalizedSnapshot.chapters, [])
      : [];

    Object.assign(artSettings, {
      kind:
        String(normalizedSnapshot.artSettings?.kind || artSettings.kind).trim() || "role",
      providerId: String(
        normalizedSnapshot.artSettings?.providerId ||
          normalizedSnapshot.artSettings?.provider_id ||
          "",
      ).trim(),
      model: String(normalizedSnapshot.artSettings?.model || "").trim(),
      duration:
        artDurationOptions.find(
          (item) => item === String(normalizedSnapshot.artSettings?.duration || "").trim(),
        ) || artDurationOptions[1],
      quality:
        qualityOptions.find(
          (item) => item === String(normalizedSnapshot.artSettings?.quality || "").trim(),
        ) || qualityOptions[1],
    });
    syncStudioModelSelection(artSettings);

    elements.value = Array.isArray(normalizedSnapshot.elements)
      ? cloneStudioDraftValue(normalizedSnapshot.elements, [])
      : [];
    extractionResults.value = Array.isArray(normalizedSnapshot.extractionResults)
      ? cloneStudioDraftValue(normalizedSnapshot.extractionResults, [])
      : [];

    Object.assign(
      characterForm,
      normalizeCharacterVoiceSelection(normalizedSnapshot.characterForm || {}),
    );
    characterForm.referenceViews = cloneStudioDraftValue(
      normalizedSnapshot.characterForm?.referenceViews || {},
      {},
    );

    Object.assign(storyboardSettings, {
      chapterId: String(normalizedSnapshot.storyboardSettings?.chapterId || "").trim(),
      providerId: String(
        normalizedSnapshot.storyboardSettings?.providerId ||
          normalizedSnapshot.storyboardSettings?.provider_id ||
          "",
      ).trim(),
      model: String(normalizedSnapshot.storyboardSettings?.model || "").trim(),
      duration:
        storyboardDurationOptions.find(
          (item) =>
            item === String(normalizedSnapshot.storyboardSettings?.duration || "").trim(),
        ) || storyboardDurationOptions[1],
      quality:
        qualityOptions.find(
          (item) =>
            item === String(normalizedSnapshot.storyboardSettings?.quality || "").trim(),
        ) || qualityOptions[1],
      sfx: Boolean(normalizedSnapshot.storyboardSettings?.sfx),
    });
    syncStudioModelSelection(storyboardSettings);

    storyboards.value = Array.isArray(normalizedSnapshot.storyboards)
      ? cloneStudioDraftValue(normalizedSnapshot.storyboards, [])
      : [];
    normalizeTimelineSequence(
      Array.isArray(normalizedSnapshot.timelineClips)
        ? cloneStudioDraftValue(normalizedSnapshot.timelineClips, [])
        : [],
    );

    Object.assign(exportConfig, {
      format:
        exportFormatOptions.find(
          (item) =>
            item.value === String(normalizedSnapshot.exportConfig?.format || "").trim(),
        )?.value || exportFormatOptions[0].value,
      resolution:
        exportResolutionOptions.find(
          (item) =>
            item === String(normalizedSnapshot.exportConfig?.resolution || "").trim(),
        ) || exportResolutionOptions[1],
      bgmEnabled: Boolean(
        String(normalizedSnapshot.exportConfig?.bgmUrl || "").trim() ||
          String(normalizedSnapshot.exportConfig?.bgmFileName || "").trim() ||
          normalizedSnapshot.exportConfig?.bgmEnabled === true ||
          (normalizedSnapshot.exportConfig?.bgmEnabled == null &&
            normalizedSnapshot.storyboardSettings?.bgm === true),
      ),
      bgmSourceType: String(normalizedSnapshot.exportConfig?.bgmSourceType || "").trim(),
      bgmTitle: String(normalizedSnapshot.exportConfig?.bgmTitle || "").trim(),
      bgmUrl: String(normalizedSnapshot.exportConfig?.bgmUrl || "").trim(),
      bgmFileName: String(normalizedSnapshot.exportConfig?.bgmFileName || "").trim(),
      bgmMimeType: String(normalizedSnapshot.exportConfig?.bgmMimeType || "").trim(),
      bgmStoragePath: String(normalizedSnapshot.exportConfig?.bgmStoragePath || "").trim(),
      videoMuted: Boolean(normalizedSnapshot.exportConfig?.videoMuted),
      videoVolume: normalizeStudioAudioMixVolume(
        normalizedSnapshot.exportConfig?.videoVolume,
        1,
      ),
      voiceMuted: Boolean(normalizedSnapshot.exportConfig?.voiceMuted),
      voiceVolume: normalizeStudioAudioMixVolume(
        normalizedSnapshot.exportConfig?.voiceVolume,
        1,
      ),
      bgmMuted: Boolean(normalizedSnapshot.exportConfig?.bgmMuted),
      bgmVolume: normalizeStudioAudioMixVolume(
        normalizedSnapshot.exportConfig?.bgmVolume,
        0.56,
      ),
    });

    activeTimelineClipId.value = String(
      normalizedSnapshot.activeTimelineClipId || activeTimelineClipId.value || "",
    ).trim();
    studioDraftWorkId.value = String(normalizedSnapshot.workId || "").trim();
    ensureActiveTimelineClip();
    syncTimelineAudioTracks([...timelineClips.value]);

    const savedAt = String(normalizedSnapshot.savedAt || "").trim();
    studioDraftSavedAt.value = savedAt;
    pendingStudioDraft.value = normalizedSnapshot;
    studioDraftResumeDismissed.value = true;
    studioDraftAutosaveReady.value = true;

    if (!chapters.value.length && String(scriptDraft.content || "").trim()) {
      splitScriptIntoChapters();
    }
    if (activeStep.value === "export") {
      void fetchTimelineVideoMaterials();
    }
    if (announce) {
      ElMessage.success("已恢复上次编辑草稿");
    }
  } finally {
    hydratingStudioDraft.value = false;
  }
}

async function saveStudioDraftToWorks(snapshot) {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    throw new Error("缺少项目 ID");
  }
  const payload = {
    job_id: String(studioDraftWorkId.value || snapshot?.workId || "").trim(),
    title: "",
    snapshot,
  };
  const data = await api.post(`/projects/${currentProjectId}/studio/drafts`, payload);
  const job = data?.job || null;
  if (!job || !String(job.id || "").trim()) {
    throw new Error("草稿作品保存失败");
  }
  return {
    ...snapshot,
    workId: String(job.id || "").trim(),
    savedAt: String(job.updated_at || snapshot?.savedAt || new Date().toISOString()).trim(),
  };
}

async function fetchStudioDraftFromWorks(jobId) {
  const currentProjectId = String(projectId.value || "").trim();
  const targetJobId = String(jobId || "").trim();
  if (!currentProjectId || !targetJobId) return null;
  const data = await api.get(`/projects/${currentProjectId}/studio/exports/${targetJobId}`);
  const job = data?.job || null;
  const snapshot =
    job?.timeline_payload?.draft_snapshot ||
    job?.timeline_payload?.draftSnapshot ||
    null;
  if (!snapshot || typeof snapshot !== "object") {
    throw new Error("草稿内容不存在或已损坏");
  }
  return {
    ...snapshot,
    workId: String(job.id || targetJobId).trim(),
    savedAt: String(job.updated_at || snapshot.savedAt || "").trim(),
  };
}

async function focusStudioExportJob(jobId, { announce = false } = {}) {
  const currentProjectId = String(projectId.value || "").trim();
  const targetJobId = String(jobId || "").trim();
  if (!currentProjectId || !targetJobId) return null;
  const data = await api.get(`/projects/${currentProjectId}/studio/exports/${targetJobId}`);
  const job = normalizeStudioExportJob(data?.job || null);
  if (!job || !String(job.id || "").trim()) {
    throw new Error("导出任务不存在或已失效");
  }
  activeStep.value = "export";
  await Promise.all([fetchStudioExportJobs(), fetchTimelineVideoMaterials()]);
  if (announce) {
    ElMessage.success("已切到导出步骤并定位任务记录");
  }
  return job;
}

async function pauseStudioEditing() {
  const snapshot = buildStudioDraftSnapshot();
  try {
    const persistedSnapshot = await saveStudioDraftToWorks(snapshot);
    writeStudioDraft(persistedSnapshot, { announce: false });
    ElMessage.success("已保存到我的作品，可稍后继续编辑");
  } catch (err) {
    writeStudioDraft(snapshot, { announce: false });
    ElMessage.error(err?.detail || err?.message || "保存草稿到我的作品失败");
  }
}

function resumeStudioDraft() {
  if (!pendingStudioDraft.value) return;
  applyStudioDraft(pendingStudioDraft.value, { announce: true });
}

function dismissStudioDraftResume() {
  studioDraftResumeDismissed.value = true;
  studioDraftAutosaveReady.value = true;
}

function handleStudioDraftBeforeUnload() {
  if (hydratingStudioDraft.value || !studioDraftAutosaveReady.value) return;
  writeStudioDraft(buildStudioDraftSnapshot());
}

function formatSecondsLabel(value) {
  const total = Math.max(0, Number(value || 0));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatTimelineRange(clip) {
  const start = Number(clip?.startSeconds || 0);
  const end =
    clip?.visible === false
      ? start
      : Number(clip?.endSeconds || start + Number(clip?.durationSeconds || 0));
  return `${formatSecondsLabel(start)} - ${formatSecondsLabel(end)}`;
}

function resolveTimelineMaterialDurationSeconds(material) {
  const metadata = material?.metadata;
  const candidates = [
    metadata?.duration_seconds,
    metadata?.durationSeconds,
    metadata?.video_duration_seconds,
    metadata?.videoDurationSeconds,
  ];
  for (const candidate of candidates) {
    const parsed = Number.parseInt(String(candidate || ""), 10);
    if (Number.isFinite(parsed) && parsed > 0) {
      return clampDuration(parsed);
    }
  }
  return 8;
}

function buildTimelineVideoMaterialMap(materials = timelineVideoMaterials.value) {
  return new Map(
    (Array.isArray(materials) ? materials : []).map((item) => [
      String(item?.id || "").trim(),
      item,
    ]),
  );
}

function resolveTimelineMaterialExportResolution(material) {
  const metadata = material?.metadata;
  const candidates = [
    metadata?.requested_export_resolution,
    metadata?.export_resolution,
    metadata?.resolution,
  ];
  for (const candidate of candidates) {
    const normalized = String(candidate || "").trim();
    if (normalized) return normalized;
  }
  return "";
}

function buildTimelineMaterialSourceLabel(material) {
  const artifactSource = String(material?.metadata?.artifact_source || "").trim();
  if (artifactSource === "studio-export-preview") {
    const resolution = resolveTimelineMaterialExportResolution(material);
    return resolution ? `短片导出预览 · ${resolution}` : "短片导出预览";
  }
  if (artifactSource === "studio-export-final") {
    const resolution = resolveTimelineMaterialExportResolution(material);
    return resolution ? `正式导出 · ${resolution}` : "正式导出";
  }
  const sourceType = String(material?.source_type || "").trim();
  if (sourceType === "ai_generated") return "AI 生成";
  if (sourceType === "manual_upload") return "手动上传";
  if (sourceType === "manual_collect") return "手动收藏";
  if (sourceType === "studio_export") return "正式导出";
  return "项目素材库";
}

function buildTimelineMaterialHistoryMeta(material) {
  const segments = [buildTimelineMaterialSourceLabel(material)];
  segments.push(`${resolveTimelineMaterialDurationSeconds(material)} 秒`);
  return segments.filter(Boolean).join(" · ");
}

function normalizeTimelineMaterialDurationSeconds(value) {
  const duration = Number(value || 0);
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  return Math.max(1, Math.round(duration));
}

function mergeTimelineMaterialDurationMetadata(metadata, durationSeconds) {
  const normalizedDuration =
    normalizeTimelineMaterialDurationSeconds(durationSeconds);
  if (!normalizedDuration) {
    return typeof metadata === "object" && metadata ? { ...metadata } : {};
  }
  return {
    ...(typeof metadata === "object" && metadata ? metadata : {}),
    duration_seconds: normalizedDuration,
    durationSeconds: normalizedDuration,
    video_duration_seconds: normalizedDuration,
    videoDurationSeconds: normalizedDuration,
  };
}

async function hydrateTimelineVideoMaterialDuration(material) {
  const materialId = String(material?.id || "").trim();
  const metadata = material?.metadata;
  const hasStoredDuration = [
    metadata?.duration_seconds,
    metadata?.durationSeconds,
    metadata?.video_duration_seconds,
    metadata?.videoDurationSeconds,
  ].some((value) => normalizeTimelineMaterialDurationSeconds(value) > 0);
  if (
    !materialId ||
    hasStoredDuration ||
    resolvingTimelineMaterialDurationIds.has(materialId)
  ) {
    return material;
  }
  const videoUrl = resolveMaterialResourceUrl(
    material?.content_url || material?.preview_url || "",
  );
  if (!videoUrl) return material;
  resolvingTimelineMaterialDurationIds.add(materialId);
  try {
    const durationSeconds = normalizeTimelineMaterialDurationSeconds(
      await readVideoDurationFromUrl(videoUrl),
    );
    if (!durationSeconds) return material;
    const metadata = mergeTimelineMaterialDurationMetadata(
      material?.metadata,
      durationSeconds,
    );
    try {
      await api.patch(
        `/projects/${String(projectId.value || "").trim()}/materials/${materialId}`,
        { metadata },
      );
    } catch {
      // Keep local fallback even if persistence fails.
    }
    return {
      ...material,
      metadata,
    };
  } catch {
    return material;
  } finally {
    resolvingTimelineMaterialDurationIds.delete(materialId);
  }
}

async function hydrateTimelineVideoMaterialsDuration(items) {
  if (!Array.isArray(items) || !items.length) return items;
  return Promise.all(items.map((item) => hydrateTimelineVideoMaterialDuration(item)));
}

function repairTimelineMaterialClips(clips, materialMap = buildTimelineVideoMaterialMap()) {
  if (!Array.isArray(clips) || !clips.length || !(materialMap instanceof Map) || !materialMap.size) {
    return { clips: Array.isArray(clips) ? clips : [], repaired: false };
  }
  let repaired = false;
  const nextClips = clips.map((clip) => {
    if (String(clip?.sourceType || "").trim() !== "material") return clip;
    const materialId = String(clip?.materialId || clip?.sourceId || "").trim();
    if (!materialId) return clip;
    const material = materialMap.get(materialId);
    if (!material) return clip;
    const sourceDuration = resolveTimelineMaterialDurationSeconds(material);
    if (!sourceDuration) return clip;
    const currentDuration = normalizeTimelineMaterialDurationSeconds(
      clip?.durationSeconds,
    );
    if (currentDuration > sourceDuration) {
      repaired = true;
      return {
        ...clip,
        durationSeconds: sourceDuration,
      };
    }
    if (clip?.userAdjustedDuration === true) return clip;
    if (!sourceDuration || sourceDuration <= currentDuration || currentDuration > 1) {
      return clip;
    }
    repaired = true;
    return {
      ...clip,
      durationSeconds: sourceDuration,
    };
  });
  return { clips: nextClips, repaired };
}

function sanitizeStudioDraftSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") {
    return { snapshot, repaired: false };
  }
  const timelineClips = Array.isArray(snapshot.timelineClips) ? snapshot.timelineClips : [];
  const { clips, repaired } = repairTimelineMaterialClips(timelineClips);
  if (!repaired) {
    return { snapshot, repaired: false };
  }
  return {
    snapshot: {
      ...snapshot,
      timelineClips: clips,
    },
    repaired: true,
  };
}

function buildStoryboardTimelineClip(item, existingState = {}) {
  const savedDuration = Number(existingState.durationSeconds || 0);
  const sourceDuration = Number(
    item.generatedDurationSeconds || item.durationSeconds || 5,
  );
  const contentUrl = resolveMaterialResourceUrl(
    item.contentUrl ||
      item.content_url ||
      existingState.contentUrl ||
      existingState.content_url ||
      item.previewUrl ||
      item.preview_url ||
      existingState.previewUrl ||
      existingState.preview_url ||
      "",
  );
  const previewUrl = resolveMaterialResourceUrl(
    item.previewUrl ||
      item.preview_url ||
      existingState.previewUrl ||
      existingState.preview_url ||
      item.contentUrl ||
      item.content_url ||
      existingState.contentUrl ||
      existingState.content_url ||
      "",
  );
  const storyboardMetadata = item.metadata || {};
  const existingMetadata = existingState.metadata || {};
  return {
    id: `clip-${item.id}`,
    sourceType: "storyboard",
    sourceId: item.id,
    storyboardId: item.id,
    materialId: "",
    chapterId: item.chapterId,
    title: item.title,
    durationSeconds:
      savedDuration > 0
        ? savedDuration
        : isStoryboardDurationLocked(item)
          ? sourceDuration
          : Number(item.durationSeconds || 5),
    durationLocked: isStoryboardDurationLocked(item),
    visible: existingState.visible ?? true,
    track: "video",
    contentUrl,
    previewUrl,
    mimeType: String(
      item.mimeType ||
        item.mime_type ||
        existingState.mimeType ||
        existingState.mime_type ||
        storyboardMetadata.mime_type ||
        existingMetadata.mime_type ||
        "",
    ).trim(),
    storagePath: String(
      item.storagePath ||
        item.storage_path ||
        existingState.storagePath ||
        existingState.storage_path ||
        storyboardMetadata.storage_path ||
        existingMetadata.storage_path ||
        "",
    ).trim(),
    originalFilename: String(
      item.originalFilename ||
        item.original_filename ||
        existingState.originalFilename ||
        existingState.original_filename ||
        storyboardMetadata.original_filename ||
        existingMetadata.original_filename ||
        "",
    ).trim(),
  };
}

function buildMaterialTimelineClip(material, existingState = {}) {
  const materialId = String(material?.id || "").trim();
  const sourceDurationSeconds = resolveTimelineMaterialDurationSeconds(material);
  const contentUrl = resolveMaterialResourceUrl(
    material?.content_url || material?.preview_url || "",
  );
  const previewUrl = resolveMaterialResourceUrl(
    material?.preview_url || material?.content_url || "",
  );
  return {
    id:
      String(existingState.id || "").trim() ||
      createId(`clip-material-${materialId || "video"}`),
    sourceType: "material",
    sourceId: materialId,
    storyboardId: "",
    materialId,
    chapterId: timelineMaterialLibraryChapterId,
    title: String(material?.title || "").trim() || "素材库视频",
    durationSeconds: existingState.durationSeconds ?? sourceDurationSeconds,
    sourceDurationSeconds,
    durationLocked: false,
    userAdjustedDuration: existingState.userAdjustedDuration === true,
    visible: existingState.visible ?? true,
    track: "video",
    contentUrl,
    previewUrl,
    mimeType: String(material?.mime_type || "").trim(),
    storagePath: String(material?.metadata?.storage_path || "").trim(),
    originalFilename: String(material?.original_filename || "").trim(),
  };
}

function stepStatus(stepId) {
  const index = stepItems.findIndex((item) => item.id === stepId);
  if (index < activeStepIndex.value) return "completed";
  if (stepId === activeStep.value) return "active";
  return canEnterStep(stepId, false) ? "pending" : "blocked";
}

function stepStatusLabel(stepId) {
  const status = stepStatus(stepId);
  if (status === "completed") return "已完成";
  if (status === "active") return "进行中";
  if (status === "blocked") return "未解锁";
  return "待开始";
}

function canEnterStep(stepId, showMessage = true) {
  if (stepId === "script") return true;
  if (stepId === "art" && chapters.value.length > 0) return true;
  if (
    stepId === "storyboard" &&
    chapters.value.length > 0 &&
    detectedElementCount.value > 0
  ) {
    return true;
  }
  if (
    stepId === "export" &&
    chapters.value.length > 0 &&
    detectedElementCount.value > 0 &&
    selectedStoryboards.value.length > 0
  ) {
    return true;
  }
  if (showMessage) {
    if (stepId === "art") {
      ElMessage.warning("请先完成剧本分章");
    } else if (stepId === "storyboard") {
      ElMessage.warning("请先完成基础设定和元素提取");
    } else if (stepId === "export") {
      ElMessage.warning("请先选择至少一个已配音分镜");
    }
  }
  return false;
}

function switchStep(stepId) {
  if (!canEnterStep(stepId, true)) return;
  activeStep.value = stepId;
  if (stepId === "export") {
    syncTimelineFromSelection();
  }
}

function goPrevStep() {
  if (activeStepIndex.value <= 0) return;
  activeStep.value = stepItems[activeStepIndex.value - 1].id;
}

function goNextStep() {
  if (!canMoveForward.value) {
    canEnterStep(stepItems[Math.min(activeStepIndex.value + 1, 3)].id, true);
    return;
  }
  if (activeStep.value === "export") return;
  const nextStep = stepItems[activeStepIndex.value + 1];
  if (!nextStep) return;
  switchStep(nextStep.id);
}

function runPrimaryAction() {
  if (activeStep.value === "script") {
    splitScriptIntoChapters();
    return;
  }
  if (activeStep.value === "art") {
    void startExtraction();
    return;
  }
  if (activeStep.value === "storyboard") {
    void generateStoryboardsForChapter();
    return;
  }
  openExportDialog();
}

function buildChapterTitle(index, content) {
  const summary = String(content || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 8);
  return `第${index}章：${summary || "故事推进"}`;
}

function splitScriptIntoChapters() {
  const content = String(scriptDraft.content || "").trim();
  if (!content) {
    ElMessage.warning("请先输入剧本内容");
    return;
  }
  const segments = content
    .split(/\n+/)
    .map((item) => item.trim())
    .filter(Boolean);
  const baseSegments =
    segments.length >= 3
      ? segments.slice(0, 4)
      : [
          content.slice(0, 40),
          content.slice(40, 80),
          content.slice(80, 120),
        ].filter(Boolean);

  chapters.value = baseSegments.map((item, index) => ({
    id: createId("chapter"),
    index: index + 1,
    title: buildChapterTitle(index + 1, item),
    summary: `${String(item).slice(0, 32)}${String(item).length > 32 ? "..." : ""}`,
    content: item,
  }));

  storyboardSettings.chapterId = chapters.value[0]?.id || "";
  resetDownstreamFromScript();
  ElMessage.success(`已拆分 ${chapters.value.length} 个章节`);
}

function resetDownstreamFromScript() {
  elements.value = [];
  storyboards.value = [];
  timelineClips.value = [];
  timelineAudioTracks.value = [];
  extractionResults.value = [];
  activeStep.value = "script";
}

function toggleStyle(styleId) {
  const target = styles.value.find((item) => item.id === styleId);
  if (!target) return;
  target.selected = !target.selected;
}

function elementCountByKind(kind) {
  return elements.value.filter((item) => item.kind === kind).length;
}

function buildExtractionResults(kind) {
  const chapterSeed = chapters.value
    .map((item) => item.title.replace(/^第\d+章：/, ""))
    .slice(0, 3);
  if (kind === "role") {
    return [
      {
        id: createId("role"),
        kind,
        name: "主角A",
        status: "detected",
        metadata: {},
      },
      {
        id: createId("role"),
        kind,
        name: "主角B",
        status: "detected",
        metadata: {},
      },
      {
        id: createId("role"),
        kind,
        name: "关键路人",
        status: "pending",
        metadata: {},
      },
    ];
  }
  if (kind === "scene") {
    return chapterSeed.map((name, index) => ({
      id: createId("scene"),
      kind,
      name: name || `场景 ${index + 1}`,
      status: index === 2 ? "pending" : "detected",
      metadata: {},
    }));
  }
  return [
    {
      id: createId("prop"),
      kind,
      name: "手机",
      status: "detected",
      metadata: {},
    },
    {
      id: createId("prop"),
      kind,
      name: "咖啡杯",
      status: "detected",
      metadata: {},
    },
    {
      id: createId("prop"),
      kind,
      name: "旧录像带",
      status: "pending",
      metadata: {},
    },
  ];
}

function buildFoundationExtractionResults() {
  return elementKinds.flatMap((kind) => buildExtractionResults(kind.value));
}

async function startExtraction() {
  if (!chapters.value.length) {
    ElMessage.warning("请先完成剧本分章");
    return;
  }
  if (!String(artSettings.providerId || "").trim() || !String(artSettings.model || "").trim()) {
    ElMessage.warning("请先选择可用模型");
    return;
  }
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  extracting.value = true;
  try {
    const data = await api.post(`/projects/${currentProjectId}/studio/extractions`, {
      provider_id: String(artSettings.providerId || "").trim(),
      model_name: String(artSettings.model || "").trim(),
      focus_kind: String(artSettings.kind || "role").trim() || "role",
      duration: String(artSettings.duration || "").trim(),
      quality: String(artSettings.quality || "").trim(),
      script_content: String(scriptDraft.content || "").trim(),
      styles: selectedStyleLabels.value,
      chapters: chapters.value.map((item) => ({
        id: String(item.id || "").trim(),
        title: String(item.title || "").trim(),
        content: String(item.content || "").trim(),
      })),
    });
    extractionResults.value = Array.isArray(data?.items) ? data.items : [];
    extractionDialogVisible.value = true;
    ElMessage.success("基础元素提取完成");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "基础元素提取失败");
  } finally {
    extracting.value = false;
  }
}

function confirmExtraction() {
  const manualItems = elements.value.filter((item) => item.status === "manual");
  elements.value = [...manualItems, ...extractionResults.value];
  extractionDialogVisible.value = false;
  ElMessage.success("基础元素提取结果已写入设定");
}

function addManualElement(kind) {
  const label =
    elementKinds.find((item) => item.value === kind)?.label || "元素";
  const count = elements.value.filter((item) => item.kind === kind).length + 1;
  elements.value.push({
    id: createId(kind),
    kind,
    name: `手动${label}${count}`,
    status: "manual",
    metadata: {},
  });
  ElMessage.success(`已新增${label}`);
}

function elementStatusLabel(status) {
  if (status === "manual") return "手动补录";
  if (status === "pending") return "待确认";
  return "已识别";
}

function markElementPending(elementId) {
  const target = elements.value.find((item) => item.id === elementId);
  if (!target) return;
  target.status = "pending";
}

function getCharacterViewLabel(viewValue) {
  return (
    characterViews.find((item) => item.value === String(viewValue || "").trim())
      ?.label || "参考图"
  );
}

function resolveCharacterReference(viewValue) {
  return normalizeCharacterReferenceItem(characterForm.referenceViews?.[viewValue]);
}

function resolveCharacterReferencePreview(viewValue) {
  return String(
    resolveCharacterReference(viewValue)?.previewUrl ||
      resolveCharacterReference(viewValue)?.contentUrl ||
      "",
  ).trim();
}

function resolveMaterialPreview(material) {
  return resolveMaterialResourceUrl(material?.preview_url || material?.content_url || "");
}

function isCharacterReferenceSelected(viewValue, materialId) {
  return (
    String(resolveCharacterReference(viewValue)?.assetId || "").trim() ===
    String(materialId || "").trim()
  );
}

function resetCharacterUploadForm(viewValue) {
  const viewLabel = getCharacterViewLabel(viewValue);
  const characterName =
    String(activeCharacter.value?.name || "角色").trim() || "角色";
  clearCharacterUploadSelection();
  Object.assign(characterUploadForm, buildCharacterUploadForm(), {
    title: `${characterName}-${viewLabel}参考图`,
    summary: `${characterName}${viewLabel}统一角色形象参考`,
    metadata_text: JSON.stringify(
      {
        source: "studio-character-reference",
        character_id: activeCharacterId.value,
        character_name: characterName,
        view: viewValue,
        view_label: viewLabel,
      },
      null,
      2,
    ),
  });
}

function buildDefaultCharacterReferencePrompt(viewValue) {
  const characterName =
    String(activeCharacter.value?.name || "角色").trim() || "角色";
  const styleHint = selectedStyleLabels.value.length
    ? `，${selectedStyleLabels.value.join("、")}风格`
    : "";
  return `${characterName}${styleHint}，单人角色参考图，人物完整，服装和发型清晰，适合短片制作设定。`;
}

function resetCharacterGenerateForm(viewValue) {
  Object.assign(characterGenerateForm, buildCharacterGenerateForm(), {
    providerId: String(artSettings.providerId || "").trim(),
    model: String(artSettings.model || "").trim(),
    prompt: buildDefaultCharacterReferencePrompt(viewValue),
  });
  syncStudioModelSelection(characterGenerateForm, artModelProviderOptions.value);
}

function openCharacterGenerateDialog(viewValue) {
  if (!canGenerateCharacterReferences.value) {
    ElMessage.warning("请先上传或绑定至少一张角色参考图");
    return;
  }
  characterReferenceViewKey.value = viewValue;
  characterMaterialDialogVisible.value = false;
  characterUploadDialogVisible.value = false;
  resetCharacterGenerateForm(viewValue);
  characterGenerateDialogVisible.value = true;
}

function openCharacterMaterialPicker(viewValue) {
  characterReferenceViewKey.value = viewValue;
  characterMaterialDialogVisible.value = true;
  void fetchCharacterReferenceMaterials();
}

function openCharacterUploadDialog(viewValue) {
  characterReferenceViewKey.value = viewValue;
  characterMaterialDialogVisible.value = false;
  characterGenerateDialogVisible.value = false;
  resetCharacterUploadForm(viewValue);
  characterUploadDialogVisible.value = true;
}

function clearCharacterReference(viewValue) {
  const nextViews = { ...characterForm.referenceViews };
  delete nextViews[viewValue];
  characterForm.referenceViews = nextViews;
}

function applyCharacterReference(viewValue, material, options = {}) {
  if (!material) return;
  characterForm.referenceViews = {
    ...characterForm.referenceViews,
    [viewValue]: {
      assetId: String(material.id || "").trim(),
      title: String(material.title || "").trim() || "未命名素材",
      previewUrl: resolveMaterialPreview(material),
      contentUrl: resolveMaterialResourceUrl(
        material.content_url || material.preview_url || "",
      ),
      mimeType: String(material.mime_type || "").trim(),
      summary: String(material.summary || "").trim(),
    },
  };
  characterMaterialDialogVisible.value = false;
  if (!options.silent) {
    ElMessage.success(`${getCharacterViewLabel(viewValue)}参考图已更新`);
  }
}

function applyGeneratedCharacterReferences(items) {
  for (const entry of Array.isArray(items) ? items : []) {
    const viewValue = String(entry?.view || "").trim();
    if (!viewValue || !entry?.item) continue;
    applyCharacterReference(viewValue, entry.item, { silent: true });
  }
}

async function fetchCharacterReferenceMaterials() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    characterReferenceMaterials.value = [];
    return;
  }
  loadingCharacterReferenceMaterials.value = true;
  try {
    const data = await api.get(`/projects/${currentProjectId}/materials`, {
      params: {
        asset_type: "image",
        query: characterMaterialSearch.value,
      },
    });
    characterReferenceMaterials.value = data.items || [];
  } catch (err) {
    characterReferenceMaterials.value = [];
    ElMessage.error(err?.detail || err?.message || "加载角色参考素材失败");
  } finally {
    loadingCharacterReferenceMaterials.value = false;
  }
}

async function fetchStudioModelSources() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    studioModelProviders.value = [];
    return;
  }
  loadingStudioModelSources.value = true;
  try {
    const data = await api.get(`/projects/${currentProjectId}/studio/model-sources`);
    studioModelProviders.value = normalizeStudioModelProviders(data?.providers || []);
    syncStudioModelSelection(artSettings, artModelProviderOptions.value);
    syncStudioModelSelection(
      storyboardSettings,
      storyboardModelProviderOptions.value,
    );
  } catch (err) {
    studioModelProviders.value = [];
    ElMessage.error(err?.detail || err?.message || "加载短片模型列表失败");
  } finally {
    loadingStudioModelSources.value = false;
  }
}

async function fetchStudioProjectVoices() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    studioProjectVoices.value = [];
    return;
  }
  loadingStudioProjectVoices.value = true;
  try {
    const data = await api.get(`/projects/${currentProjectId}/studio/voices`);
    studioProjectVoices.value = normalizeStudioProjectVoices(data?.items || []);
  } catch (err) {
    studioProjectVoices.value = [];
    ElMessage.error(err?.detail || err?.message || "加载项目音色失败");
  } finally {
    loadingStudioProjectVoices.value = false;
  }
}

function clearCharacterVoiceSelection() {
  Object.assign(characterForm, buildEmptyCharacterVoiceSelection());
}

function selectCharacterVoiceOption(option) {
  Object.assign(
    characterForm,
    normalizeCharacterVoiceSelection({
      voiceRecordId: option?.id,
      voiceId: option?.voiceId,
      providerId: option?.providerId,
      modelName: option?.modelName,
      voiceLabel: option?.name,
      voicePreset: option?.name,
    }),
  );
}

function triggerCharacterUploadFilePicker() {
  characterUploadFileInputRef.value?.click?.();
}

function clearCharacterUploadSelection() {
  if (String(characterUploadForm.preview_url || "").startsWith("blob:")) {
    URL.revokeObjectURL(characterUploadForm.preview_url);
  }
  characterUploadSelectedFile.value = null;
  characterUploadFileName.value = "";
  characterUploadForm.preview_url = "";
  characterUploadForm.content_url = "";
}

function handleCharacterUploadFileChange(event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  clearCharacterUploadSelection();
  characterUploadSelectedFile.value = file;
  characterUploadFileName.value = file.name;
  characterUploadForm.preview_url = URL.createObjectURL(file);
  characterUploadForm.mime_type =
    String(file.type || "").trim() || "image/png";
  if (!String(characterUploadForm.title || "").trim()) {
    characterUploadForm.title = file.name.replace(/\.[^.]+$/, "");
  }
  if (event?.target) event.target.value = "";
}

function safeParseObject(text, fieldLabel) {
  const source = String(text || "").trim();
  if (!source) return {};
  try {
    const parsed = JSON.parse(source);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
    throw new Error("not object");
  } catch {
    throw new Error(`${fieldLabel} 必须是合法 JSON 对象`);
  }
}

async function submitCharacterUpload() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  const title = String(characterUploadForm.title || "").trim();
  if (!title) {
    ElMessage.warning("请先填写素材标题");
    return;
  }
  if (!characterUploadSelectedFile.value) {
    ElMessage.warning("请先选择本地图片");
    return;
  }
  let structuredContent;
  let metadata;
  try {
    structuredContent = safeParseObject(
      characterUploadForm.structured_content_text,
      "结构化内容",
    );
    metadata = safeParseObject(characterUploadForm.metadata_text, "元数据");
  } catch (err) {
    ElMessage.error(err?.message || "JSON 格式错误");
    return;
  }
  uploadingCharacterMaterial.value = true;
  try {
    const formData = new FormData();
    formData.append("file", characterUploadSelectedFile.value);
    formData.append("asset_type", "image");
    formData.append("title", title);
    formData.append("summary", String(characterUploadForm.summary || ""));
    formData.append("mime_type", String(characterUploadForm.mime_type || ""));
    formData.append(
      "structured_content",
      JSON.stringify(structuredContent || {}),
    );
    formData.append("metadata", JSON.stringify(metadata || {}));
    const data = await api.post(`/projects/${currentProjectId}/materials/upload`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    const createdItem = data.item || null;
    if (createdItem) {
      applyCharacterReference(characterReferenceViewKey.value, createdItem, {
        silent: true,
      });
    }
    characterUploadDialogVisible.value = false;
    clearCharacterUploadSelection();
    await fetchCharacterReferenceMaterials();
    ElMessage.success("角色参考图已入素材库");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存角色参考素材失败");
  } finally {
    uploadingCharacterMaterial.value = false;
  }
}

async function submitCharacterReferenceGeneration() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  if (!activeCharacterReferenceSourceUrls.value.length) {
    ElMessage.warning("请先上传或绑定至少一张角色参考图");
    return;
  }
  if (!String(characterGenerateForm.providerId || "").trim() || !String(characterGenerateForm.model || "").trim()) {
    ElMessage.warning("请先选择图片模型");
    return;
  }
  if (!String(characterGenerateForm.prompt || "").trim()) {
    ElMessage.warning("请先填写角色提示词");
    return;
  }
  generatingCharacterReferences.value = true;
  try {
    const data = await api.post(
      `/projects/${currentProjectId}/studio/character-references/generate`,
      {
        provider_id: String(characterGenerateForm.providerId || "").trim(),
        model_name: String(characterGenerateForm.model || "").trim(),
        prompt: String(characterGenerateForm.prompt || "").trim(),
        character_id: String(activeCharacterId.value || "").trim(),
        character_name: String(activeCharacter.value?.name || "").trim(),
        reference_image_urls: activeCharacterReferenceSourceUrls.value,
        target_view: characterReferenceViewKey.value,
        generate_all_views: Boolean(characterGenerateForm.generateAllViews),
        image_size: "1024x1024",
        image_style: "auto",
        image_quality: "high",
      },
    );
    const items = Array.isArray(data?.items) ? data.items : [];
    if (!items.length) {
      ElMessage.warning("模型没有返回可用参考图");
      return;
    }
    applyGeneratedCharacterReferences(items);
    characterGenerateDialogVisible.value = false;
    await fetchCharacterReferenceMaterials();
    ElMessage.success(
      characterGenerateForm.generateAllViews
        ? "角色四视图已生成并绑定"
        : `${activeCharacterReferenceView.value.label}参考图已生成并绑定`,
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "生成角色参考图失败");
  } finally {
    generatingCharacterReferences.value = false;
  }
}

async function removeElement(element) {
  const targetId = String(element?.id || "").trim();
  if (!targetId) return;
  const kindLabel =
    elementKinds.find((item) => item.value === element?.kind)?.label || "元素";
  const targetName = String(element?.name || "").trim() || `${kindLabel}资产`;
  try {
    await ElMessageBox.confirm(
      `确认删除${kindLabel}「${targetName}」？`,
      "删除资产",
      {
        type: "warning",
        customClass: "studio-message-box",
      },
    );
  } catch {
    return;
  }
  elements.value = elements.value.filter((item) => item.id !== targetId);
  if (activeCharacterId.value === targetId) {
    activeCharacterId.value = "";
    characterDialogVisible.value = false;
  }
  ElMessage.success(`${kindLabel}已删除`);
}

async function openCharacterConfig(element) {
  activeCharacterId.value = element.id;
  Object.assign(
    characterForm,
    normalizeCharacterVoiceSelection(element.metadata || {}),
  );
  characterForm.referenceViews = cloneCharacterReferenceViews(
    element.metadata?.referenceViews,
  );
  characterMaterialSearch.value = "";
  await fetchCharacterReferenceMaterials();
  characterDialogVisible.value = true;
}

function saveCharacterConfig() {
  const target = elements.value.find(
    (item) => item.id === activeCharacterId.value,
  );
  if (!target) return;
  const characterVoiceSelection = serializeCharacterVoiceSelection(characterForm);
  target.metadata = {
    ...(target.metadata || {}),
    ...characterVoiceSelection,
    referenceViews: cloneCharacterReferenceViews(characterForm.referenceViews),
  };
  characterDialogVisible.value = false;
  ElMessage.success("角色配置已保存");
}

function buildMockStoryboards(chapterId) {
  const chapterTitle = chapterTitleById(chapterId).replace(/^第\d+章：/, "");
  const duration =
    Number.parseInt(String(storyboardSettings.duration || "8"), 10) || 8;
  return [
    { title: `${chapterTitle} · 场景建立`, durationOffset: 0 },
    { title: `${chapterTitle} · 关键对话`, durationOffset: 1 },
    { title: `${chapterTitle} · 情绪转折`, durationOffset: -1 },
  ].map((item, index) => {
    const durationSeconds = Math.max(3, duration + item.durationOffset);
    return {
      id: createId("storyboard"),
      chapterId,
      title: item.title,
      durationSeconds,
      generatedDurationSeconds: durationSeconds,
      durationLocked: true,
      hasVoice: false,
      selected: false,
      status: "draft",
      updatedAt: new Date(Date.now() - index * 60000).toISOString(),
    };
  });
}

async function generateStoryboardsForChapter() {
  const chapterId = String(storyboardSettings.chapterId || "").trim();
  if (!chapterId) {
    ElMessage.warning("请先选择章节");
    return;
  }
  if (!String(storyboardSettings.providerId || "").trim() || !String(storyboardSettings.model || "").trim()) {
    ElMessage.warning("请先选择可用模型");
    return;
  }
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  const chapter = chapters.value.find((item) => String(item.id || "").trim() === chapterId);
  if (!chapter) {
    ElMessage.warning("当前章节不存在");
    return;
  }
  generatingStoryboards.value = true;
  try {
    const data = await api.post(`/projects/${currentProjectId}/studio/storyboards/generate`, {
      provider_id: String(storyboardSettings.providerId || "").trim(),
      model_name: String(storyboardSettings.model || "").trim(),
      chapter_id: chapterId,
      chapter_title: String(chapter.title || "").trim(),
      chapter_content: String(chapter.content || "").trim(),
      duration: String(storyboardSettings.duration || "").trim(),
      quality: String(storyboardSettings.quality || "").trim(),
      sfx: Boolean(storyboardSettings.sfx),
      styles: selectedStyleLabels.value,
      elements: elements.value.map((item) => ({
        kind: String(item.kind || "").trim(),
        name: String(item.name || "").trim(),
      })),
    });
    const others = storyboards.value.filter(
      (item) => item.chapterId !== chapterId,
    );
    const generated = Array.isArray(data?.items) ? data.items : [];
    storyboards.value = [...others, ...generated];
    ElMessage.success("当前章节分镜已生成");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "当前章节分镜生成失败");
  } finally {
    generatingStoryboards.value = false;
  }
}

function storyboardStatusLabel(status) {
  if (status === "failed") return "待重试";
  if (status === "ready") return "可导出";
  return "草稿";
}

function isStoryboardDurationLocked(board) {
  return Boolean(board) && board.durationLocked !== false;
}

function resolveStoryboardVoiceNarrationText(board) {
  if (!board) return "";
  const stored = String(board?.metadata?.voiceConfig?.text || "").trim();
  if (stored) return stored;
  return String(board.title || "").trim();
}

function syncVoiceModelSelection() {
  const provider =
    audioModelProviderOptions.value.find(
      (item) => item.id === String(voiceForm.providerId || "").trim(),
    ) ||
    audioModelProviderOptions.value[0] ||
    null;
  if (!provider) {
    voiceForm.providerId = "";
    voiceForm.model = "";
    voiceForm.voice = systemVoiceOptions[0]?.value || "";
    return;
  }
  voiceForm.providerId = provider.id;
  voiceForm.model = provider.models.includes(String(voiceForm.model || "").trim())
    ? String(voiceForm.model || "").trim()
    : provider.defaultModel || provider.models[0] || "";
  const currentVoice = String(voiceForm.voice || "").trim();
  if (voiceSelectableOptions.value.some((item) => item.value === currentVoice)) return;
  voiceForm.voice = voiceSelectableOptions.value[0]?.value || systemVoiceOptions[0]?.value || "";
}

function resolveStoryboardCharacterVoice(board) {
  const haystack = `${String(board?.title || "").trim()} ${String(board?.summary || "").trim()}`.toLowerCase();
  const configuredRoles = elements.value
    .filter((item) => item.kind === "role")
    .map((item) => ({
      name: String(item?.name || "").trim(),
      voice: normalizeCharacterVoiceSelection(item?.metadata || {}),
    }))
    .filter((item) => item.name && item.voice.voiceId);
  if (!configuredRoles.length) return null;
  if (haystack) {
    const matchedRoles = configuredRoles.filter((item) =>
      haystack.includes(item.name.toLowerCase()),
    );
    if (matchedRoles.length === 1) {
      return matchedRoles[0].voice;
    }
  }
  return configuredRoles.length === 1 ? configuredRoles[0].voice : null;
}

function openVoiceDialog(board) {
  const storedVoiceConfig =
    board?.metadata?.voiceConfig && typeof board.metadata.voiceConfig === "object"
      ? board.metadata.voiceConfig
      : {};
  const storedVoice = normalizeCharacterVoiceSelection(storedVoiceConfig);
  const fallbackVoice = storedVoice.voiceId ? null : resolveStoryboardCharacterVoice(board);
  const resolvedVoice = storedVoice.voiceId ? storedVoice : fallbackVoice;
  const storedProviderId = resolvedVoice?.providerId || "";
  const storedModel = resolvedVoice?.modelName || String(storedVoiceConfig?.model || "").trim();
  if (storedProviderId) {
    voiceForm.providerId = storedProviderId;
  }
  if (storedModel) {
    voiceForm.model = storedModel;
  }
  syncVoiceModelSelection();
  voiceTargetId.value = board.id;
  voiceForm.text = resolveStoryboardVoiceNarrationText(board);
  voiceForm.speed = resolveVoiceSpeedValue(board?.metadata?.voiceConfig?.speed);
  const nextVoice = resolvedVoice?.voiceId || String(storedVoiceConfig?.voice || "").trim();
  if (nextVoice) {
    voiceForm.voice = nextVoice;
  }
  voiceDialogVisible.value = true;
}

function confirmVoiceGeneration() {
  const target = storyboards.value.find(
    (item) => item.id === voiceTargetId.value,
  );
  if (!target) return;
  if (!resolveStoryboardVoiceResolvedUrl(target)) {
    ElMessage.warning("请先生成或上传旁白音频");
    return;
  }
  target.hasVoice = true;
  target.selected = true;
  target.status = "ready";
  target.updatedAt = new Date().toISOString();
  voiceDialogVisible.value = false;
  syncTimelineFromSelection();
  ElMessage.success(`分镜「${target.title}」旁白已保存`);
}

async function generateVoiceAudio() {
  const target = voiceTargetBoard.value;
  const currentProjectId = String(projectId.value || "").trim();
  if (!target || !currentProjectId) {
    ElMessage.warning("缺少项目上下文");
    return;
  }
  if (!String(voiceForm.providerId || "").trim() || !String(voiceForm.model || "").trim()) {
    ElMessage.warning("请先选择配音模型源");
    return;
  }
  if (!String(voiceForm.voice || "").trim()) {
    ElMessage.warning("请选择音色");
    return;
  }
  if (!String(voiceForm.text || "").trim()) {
    ElMessage.warning("请填写旁白文本");
    return;
  }
  generatingVoiceAudio.value = true;
  try {
    const selectedProjectVoiceRecordId =
      selectedVoiceOption.value?.sourceType === "project"
        ? String(selectedVoiceOption.value.voiceRecordId || "").trim()
        : "";
    const data = await api.post(`/projects/${currentProjectId}/studio/voiceovers/generate`, {
      provider_id: String(voiceForm.providerId || "").trim(),
      model_name: String(voiceForm.model || "").trim(),
      voice: String(voiceForm.voice || "").trim(),
      text: String(voiceForm.text || "").trim(),
      title: `${String(target.title || "分镜").trim()} 旁白`,
      voice_record_id: selectedProjectVoiceRecordId,
      response_format: "wav",
      speed: resolveVoiceSpeedValue(voiceForm.speed),
    });
    const item = data.item || {};
    if (data?.voice_item && typeof data.voice_item === "object") {
      const normalizedVoice = normalizeStudioProjectVoices([data.voice_item])[0];
      if (normalizedVoice) {
        const voiceIndex = studioProjectVoices.value.findIndex(
          (entry) => entry.id === normalizedVoice.id,
        );
        if (voiceIndex >= 0) {
          studioProjectVoices.value.splice(voiceIndex, 1, normalizedVoice);
        } else {
          studioProjectVoices.value.unshift(normalizedVoice);
        }
      }
    }
    target.metadata = {
      ...(target.metadata || {}),
      voiceConfig: {
        providerId: String(voiceForm.providerId || "").trim(),
        model: String(voiceForm.model || "").trim(),
        voice: String(voiceForm.voice || "").trim(),
        voiceRecordId: selectedProjectVoiceRecordId,
        voiceLabel: selectedVoiceOption.value?.label || String(voiceForm.voice || "").trim(),
        text: String(voiceForm.text || "").trim(),
        speed: resolveVoiceSpeedValue(voiceForm.speed),
      },
      voiceAudio: {
        title: String(item.title || `${String(target.title || "分镜").trim()} 旁白`).trim(),
        content_url: String(item.content_url || "").trim(),
        mime_type: String(item.mime_type || "").trim(),
        original_filename: String(item.original_filename || "").trim(),
        storage_path: String(item.storage_path || "").trim(),
        source_type: "tts_generation",
      },
    };
    target.hasVoice = true;
    target.selected = true;
    target.status = "ready";
    target.updatedAt = new Date().toISOString();
    syncTimelineFromSelection();
    ElMessage.success("旁白已生成，可直接保存");
    void persistStudioDraftSilently();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "生成旁白失败");
  } finally {
    generatingVoiceAudio.value = false;
  }
}

function regenerateStoryboard(storyboardId) {
  const target = storyboards.value.find((item) => item.id === storyboardId);
  if (!target) return;
  target.status = "draft";
  target.hasVoice = false;
  target.selected = false;
  clearStoryboardVoiceAudio(target);
  target.updatedAt = new Date().toISOString();
  syncTimelineFromSelection();
  ElMessage.success(`已重置分镜「${target.title}」`);
}

function toggleStoryboardSelection(storyboardId, event) {
  const target = storyboards.value.find((item) => item.id === storyboardId);
  if (!target) return;
  if (!target.hasVoice) {
    ElMessage.warning("请先上传旁白");
    return;
  }
  target.selected = Boolean(event?.target?.checked);
  syncTimelineFromSelection();
}

function normalizeTimelineSequence(clips) {
  let cursor = 0;
  const normalized = clips.map((clip, index) => {
    const durationSeconds = clampDuration(clip.durationSeconds);
    const visible = clip.visible !== false;
    const startSeconds = cursor;
    const endSeconds = visible ? startSeconds + durationSeconds : startSeconds;
    if (visible) {
      cursor = endSeconds;
    }
    return {
      ...clip,
      order: index,
      track: clip.track || "video",
      durationSeconds,
      visible,
      startSeconds,
      endSeconds,
    };
  });
  timelineClips.value = normalized;
  syncTimelineAudioTracks(normalized);
  ensureActiveTimelineClip();
}

function ensureActiveTimelineClip() {
  if (!timelineClips.value.length) {
    activeTimelineClipId.value = "";
    return;
  }
  const current = timelineClips.value.find(
    (item) => item.id === activeTimelineClipId.value,
  );
  if (current && current.visible !== false) return;
  activeTimelineClipId.value =
    visibleTimelineClips.value[0]?.id || timelineClips.value[0]?.id || "";
}

function normalizeStudioAudioMixVolume(value, fallback = 1) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return fallback;
  return Math.max(0, Math.min(1.5, numericValue));
}

function resolveStudioAudioMixChannel(channelId, fallback = 1) {
  const normalized = String(channelId || "").trim().toLowerCase();
  const volumeKey = `${normalized}Volume`;
  const mutedKey = `${normalized}Muted`;
  const baseVolume = normalizeStudioAudioMixVolume(exportConfig[volumeKey], fallback);
  return exportConfig[mutedKey] ? 0 : baseVolume;
}

function resolveStudioExportTrackVolume(segment, track, fallback = 1) {
  const candidates = [segment?.volume, track?.volume];
  for (const candidate of candidates) {
    if (candidate === undefined || candidate === null || candidate === "") continue;
    return normalizeStudioAudioMixVolume(candidate, fallback);
  }
  return normalizeStudioAudioMixVolume(fallback, fallback);
}

function buildTimelineAudioTracks(clips) {
  const visibleClips = clips.filter((item) => item.visible !== false);
  const totalDuration = visibleClips.reduce(
    (total, item) => total + Number(item.durationSeconds || 0),
    0,
  );
  const storyboardMap = new Map(
    storyboards.value.map((item) => [String(item.id || "").trim(), item]),
  );
  const tracks = [];
  const voiceVolume = resolveStudioAudioMixChannel("voice", 1);
  const bgmVolume = resolveStudioAudioMixChannel("bgm", 0.56);
  const voiceSegments = visibleClips
    .filter(
      (clip) =>
        storyboardMap.get(String(clip.storyboardId || "").trim())?.hasVoice,
    )
    .map((clip) => {
      const board = storyboardMap.get(String(clip.storyboardId || "").trim());
      return {
        id: `voice-${clip.id}`,
        label: clip.title,
        title: clip.title,
        startSeconds: Number(clip.startSeconds || 0),
        durationSeconds: Number(clip.durationSeconds || 0),
        bind_clip_id: String(clip.id || "").trim(),
        storyboardId: clip.storyboardId,
        source_url: resolveStoryboardVoiceResolvedUrl(board),
        storage_path: resolveStoryboardVoiceStoragePath(board),
        mime_type: resolveStoryboardVoiceMimeType(board),
        original_filename: resolveStoryboardVoiceOriginalFilename(board),
        volume: voiceVolume,
      };
    });
  if (voiceSegments.length) {
    tracks.push({
      id: "audio-track-voice",
      kind: "voice",
      label: "旁白",
      volume: voiceVolume,
      segments: voiceSegments,
    });
  }
  if (exportBgmResolvedUrl.value && totalDuration > 0) {
    tracks.push({
      id: "audio-track-bgm",
      kind: "bgm",
      label: "背景音乐",
      volume: bgmVolume,
      source_url: exportBgmResolvedUrl.value,
      storage_path: String(exportConfig.bgmStoragePath || "").trim(),
      mime_type: String(exportConfig.bgmMimeType || "").trim(),
      original_filename: String(exportConfig.bgmFileName || "").trim(),
      segments: [
        {
          id: "bgm-main",
          label: exportBgmDisplayName.value,
          startSeconds: 0,
          durationSeconds: totalDuration,
          volume: bgmVolume,
        },
      ],
    });
  }
  return tracks;
}

function syncTimelineAudioTracks(clips = timelineClips.value) {
  timelineAudioTracks.value = buildTimelineAudioTracks(clips);
}

function handleStudioAudioMixChange(nextMix) {
  if (!nextMix || typeof nextMix !== "object") return;
  const normalizedMix = {
    videoMuted: Boolean(nextMix.videoMuted),
    videoVolume: normalizeStudioAudioMixVolume(nextMix.videoVolume, 1),
    voiceMuted: Boolean(nextMix.voiceMuted),
    voiceVolume: normalizeStudioAudioMixVolume(nextMix.voiceVolume, 1),
    bgmMuted: Boolean(nextMix.bgmMuted),
    bgmVolume: normalizeStudioAudioMixVolume(nextMix.bgmVolume, 0.56),
  };
  if (
    exportConfig.videoMuted === normalizedMix.videoMuted &&
    exportConfig.videoVolume === normalizedMix.videoVolume &&
    exportConfig.voiceMuted === normalizedMix.voiceMuted &&
    exportConfig.voiceVolume === normalizedMix.voiceVolume &&
    exportConfig.bgmMuted === normalizedMix.bgmMuted &&
    exportConfig.bgmVolume === normalizedMix.bgmVolume
  ) {
    return;
  }
  exportConfig.videoMuted = normalizedMix.videoMuted;
  exportConfig.videoVolume = normalizedMix.videoVolume;
  exportConfig.voiceMuted = normalizedMix.voiceMuted;
  exportConfig.voiceVolume = normalizedMix.voiceVolume;
  exportConfig.bgmMuted = normalizedMix.bgmMuted;
  exportConfig.bgmVolume = normalizedMix.bgmVolume;
  syncTimelineAudioTracks([...timelineClips.value]);
}

function inferStudioExportClipType(clip) {
  const mimeType = String(clip?.mimeType || "").trim().toLowerCase();
  const locator = [
    String(clip?.contentUrl || "").trim().toLowerCase(),
    String(clip?.previewUrl || "").trim().toLowerCase(),
    String(clip?.storagePath || "").trim().toLowerCase(),
    String(clip?.originalFilename || "").trim().toLowerCase(),
  ].join(" ");
  if (mimeType.startsWith("image/")) return "image";
  if (mimeType.startsWith("video/")) return "video";
  if (
    [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"].some((suffix) =>
      locator.includes(suffix),
    )
  ) {
    return "image";
  }
  return "video";
}

function normalizeStudioExportSourceType(clip) {
  const raw = String(clip?.sourceType || "").trim().toLowerCase();
  if (raw === "material") return "project_material";
  const contentUrl = String(clip?.contentUrl || "").trim();
  if (/^(https?:|data:)/i.test(contentUrl)) return "external_url";
  if (raw === "ai_generated") return "ai_generated";
  return "studio_draft";
}

function buildStudioExportClipsV2(clips) {
  return clips.map((clip, index) => {
    const clipId = String(clip?.id || "").trim() || `clip-${index + 1}`;
    const clipType = inferStudioExportClipType(clip);
    const sourceType = normalizeStudioExportSourceType(clip);
    const materialId = String(clip?.materialId || "").trim();
    const sourceId = String(
      clip?.sourceId || clip?.storyboardId || materialId || clipId,
    ).trim();
    return {
      id: clipId,
      type: clipType,
      title: String(clip?.title || "").trim() || `片段 ${index + 1}`,
      durationSeconds: Number(clip?.durationSeconds || 0),
      startSeconds: Number(clip?.startSeconds || 0),
      asset_id: materialId || (sourceType === "project_material" ? sourceId : ""),
      storage_path: String(clip?.storagePath || "").trim(),
      content_url: String(clip?.contentUrl || "").trim(),
      preview_url: String(clip?.previewUrl || "").trim(),
      mime_type: String(clip?.mimeType || "").trim(),
      original_filename: String(clip?.originalFilename || "").trim(),
      source_type: sourceType,
      transform: {
        fit: "cover",
        align: "center",
        background: "#000000",
      },
      meta: {
        order: index + 1,
        chapter_id: String(clip?.chapterId || "").trim(),
        chapter_title: chapterTitleById(clip?.chapterId),
        source_id: sourceId,
        source_type_raw: String(clip?.sourceType || "").trim() || "storyboard",
      },
    };
  });
}

function buildStudioExportAudioTracksV2(tracks) {
  const normalizedTracks = [];
  (Array.isArray(tracks) ? tracks : []).forEach((track, trackIndex) => {
    const kind = String(track?.kind || "").trim().toLowerCase();
    if (!["voice", "bgm", "sfx"].includes(kind)) return;
    const baseTitle = String(track?.title || track?.label || "").trim() || `音轨 ${trackIndex + 1}`;
    const segments = Array.isArray(track?.segments) && track.segments.length ? track.segments : [track];
    segments.forEach((segment, segmentIndex) => {
      const durationSeconds = Number(segment?.durationSeconds || segment?.duration_seconds || 0);
      if (!(durationSeconds > 0)) return;
      normalizedTracks.push({
        id:
          String(segment?.id || "").trim() ||
          String(track?.id || "").trim() ||
          `${kind}-${trackIndex + 1}-${segmentIndex + 1}`,
        kind,
        title: String(segment?.title || segment?.label || "").trim() || baseTitle,
        startSeconds: Number(segment?.startSeconds || segment?.start_seconds || 0),
        durationSeconds,
        volume: resolveStudioExportTrackVolume(
          segment,
          track,
          kind === "bgm" ? 0.6 : 1,
        ),
        asset_id: String(segment?.asset_id || segment?.assetId || track?.asset_id || track?.assetId || "").trim(),
        storage_path: String(segment?.storage_path || segment?.storagePath || track?.storage_path || track?.storagePath || "").trim(),
        content_url: String(segment?.content_url || segment?.contentUrl || segment?.source_url || segment?.sourceUrl || track?.content_url || track?.contentUrl || track?.source_url || track?.sourceUrl || "").trim(),
        mime_type: String(segment?.mime_type || segment?.mimeType || track?.mime_type || track?.mimeType || "").trim(),
        original_filename: String(segment?.original_filename || segment?.originalFilename || track?.original_filename || track?.originalFilename || "").trim(),
        required: kind === "voice",
        bind_clip_id: String(segment?.bind_clip_id || segment?.bindClipId || track?.bind_clip_id || track?.bindClipId || "").trim(),
      });
    });
  });
  return normalizedTracks;
}

function deriveAudioDisplayName(fileName, fallbackTitle = "背景音乐") {
  const normalized = String(fileName || "").trim();
  if (!normalized) return fallbackTitle;
  return normalized.replace(/\.[^.]+$/, "").trim() || fallbackTitle;
}

function resolveStoryboardVoiceSource(board) {
  const metadata = board?.metadata || {};
  if (!metadata || typeof metadata !== "object") return {};
  return metadata.voiceAudio && typeof metadata.voiceAudio === "object"
    ? metadata.voiceAudio
    : {};
}

function resolveStoryboardVoiceResolvedUrl(board) {
  const payload = resolveStoryboardVoiceSource(board);
  return resolveMaterialResourceUrl(payload.content_url || "");
}

function resolveStoryboardVoiceStoragePath(board) {
  const payload = resolveStoryboardVoiceSource(board);
  return String(payload.storage_path || "").trim();
}

function resolveStoryboardVoiceMimeType(board) {
  const payload = resolveStoryboardVoiceSource(board);
  return String(payload.mime_type || "").trim();
}

function resolveStoryboardVoiceOriginalFilename(board) {
  const payload = resolveStoryboardVoiceSource(board);
  return String(payload.original_filename || "").trim();
}

function resolveStoryboardVoiceDisplayName(board) {
  const payload = resolveStoryboardVoiceSource(board);
  return (
    String(payload.title || "").trim() ||
    deriveAudioDisplayName(payload.original_filename || "", "旁白")
  );
}

function resetVoiceFileInput() {
  if (voiceFileInputRef.value) {
    voiceFileInputRef.value.value = "";
  }
}

function openVoiceFilePicker() {
  voiceFileInputRef.value?.click?.();
}

function clearStoryboardVoiceAudio(board) {
  if (!board) return;
  board.metadata = {
    ...(board.metadata || {}),
    voiceAudio: {},
    voiceConfig: {},
  };
}

function clearVoiceAudioAndPersist() {
  const target = voiceTargetBoard.value;
  if (!target || !resolveStoryboardVoiceResolvedUrl(target)) return;
  clearStoryboardVoiceAudio(target);
  target.hasVoice = false;
  target.selected = false;
  target.status = "draft";
  target.updatedAt = new Date().toISOString();
  syncTimelineFromSelection();
  ElMessage.success("已移除旁白音频");
  resetVoiceFileInput();
  void persistStudioDraftSilently();
}

async function handleVoiceFileChange(event) {
  const file = event?.target?.files?.[0];
  const target = voiceTargetBoard.value;
  if (!file || !target) return;
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    resetVoiceFileInput();
    return;
  }
  uploadingVoiceAudio.value = true;
  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", `${String(target.title || "分镜").trim()} 旁白`);
    formData.append("mime_type", String(file.type || ""));
    const data = await api.post(`/projects/${currentProjectId}/studio/audio/upload`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    const item = data.item || {};
    target.metadata = {
      ...(target.metadata || {}),
      voiceConfig: {
        providerId: String(voiceForm.providerId || "").trim(),
        model: String(voiceForm.model || "").trim(),
        voice: String(voiceForm.voice || "").trim(),
        voiceRecordId:
          selectedVoiceOption.value?.sourceType === "project"
            ? String(selectedVoiceOption.value.voiceRecordId || "").trim()
            : "",
        voiceLabel: selectedVoiceOption.value?.label || String(voiceForm.voice || "").trim(),
        text: String(voiceForm.text || "").trim(),
        speed: resolveVoiceSpeedValue(voiceForm.speed),
      },
      voiceAudio: {
        title: String(item.title || deriveAudioDisplayName(file.name, "旁白")).trim(),
        content_url: String(item.content_url || "").trim(),
        mime_type: String(item.mime_type || file.type || "").trim(),
        original_filename: String(item.original_filename || file.name || "").trim(),
        storage_path: String(item.storage_path || "").trim(),
        source_type: "upload",
      },
    };
    target.hasVoice = true;
    target.selected = true;
    target.status = "ready";
    target.updatedAt = new Date().toISOString();
    syncTimelineFromSelection();
    ElMessage.success("旁白音频已上传");
    void persistStudioDraftSilently();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "上传旁白音频失败");
  } finally {
    uploadingVoiceAudio.value = false;
    resetVoiceFileInput();
  }
}

function resetExportBgmFileInput() {
  if (exportBgmFileInputRef.value) {
    exportBgmFileInputRef.value.value = "";
  }
}

function openExportBgmFilePicker() {
  exportBgmFileInputRef.value?.click?.();
}

function clearExportBgm() {
  exportConfig.bgmEnabled = false;
  exportConfig.bgmSourceType = "";
  exportConfig.bgmTitle = "";
  exportConfig.bgmUrl = "";
  exportConfig.bgmFileName = "";
  exportConfig.bgmMimeType = "";
  exportConfig.bgmStoragePath = "";
  resetExportBgmFileInput();
}

function clearExportBgmAndPersist() {
  const hasBgm =
    Boolean(String(exportConfig.bgmUrl || "").trim()) ||
    Boolean(String(exportConfig.bgmFileName || "").trim());
  if (!hasBgm) return;
  clearExportBgm();
  syncTimelineAudioTracks([...timelineClips.value]);
  ElMessage.success("已移除背景音乐");
  void persistStudioDraftSilently();
}

function handleExportBgmAction(actionId) {
  if (actionId === "upload") {
    openExportBgmFilePicker();
    return;
  }
  if (actionId === "clear") {
    clearExportBgmAndPersist();
  }
}

async function handleExportBgmFileChange(event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    resetExportBgmFileInput();
    return;
  }
  uploadingExportBgm.value = true;
  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", deriveAudioDisplayName(file.name));
    formData.append("mime_type", String(file.type || ""));
    const data = await api.post(`/projects/${currentProjectId}/studio/audio/upload`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    const item = data.item || {};
    exportConfig.bgmEnabled = true;
    exportConfig.bgmSourceType = "upload";
    exportConfig.bgmTitle =
      String(exportConfig.bgmTitle || "").trim() ||
      String(item.title || deriveAudioDisplayName(file.name)).trim();
    exportConfig.bgmUrl = String(item.content_url || "").trim();
    exportConfig.bgmFileName = String(item.original_filename || file.name || "").trim();
    exportConfig.bgmMimeType = String(item.mime_type || file.type || "").trim();
    exportConfig.bgmStoragePath = String(item.storage_path || "").trim();
    ElMessage.success("背景音乐已上传");
    syncTimelineAudioTracks([...timelineClips.value]);
    void persistStudioDraftSilently();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "上传背景音乐失败");
  } finally {
    uploadingExportBgm.value = false;
    resetExportBgmFileInput();
  }
}

function syncTimelineFromSelection() {
  const existingStoryboardClipMap = new Map(
    timelineClips.value
      .filter((item) => String(item.sourceType || "storyboard").trim() !== "material")
      .map((item) => [
        `storyboard:${String(item.storyboardId || item.sourceId || item.id || "").trim()}`,
        {
          id: item.id,
          durationSeconds: item.durationSeconds,
          userAdjustedDuration: item.userAdjustedDuration === true,
          visible: item.visible !== false,
          order: Number(item.order ?? Number.MAX_SAFE_INTEGER),
        },
      ]),
  );
  const materialMap = new Map(
    timelineVideoMaterials.value.map((item) => [String(item.id || "").trim(), item]),
  );
  const orderedSelection = [...selectedStoryboards.value].sort((left, right) => {
    const leftOrder = existingStoryboardClipMap.get(`storyboard:${left.id}`)?.order;
    const rightOrder = existingStoryboardClipMap.get(`storyboard:${right.id}`)?.order;
    if (Number.isFinite(leftOrder) && Number.isFinite(rightOrder)) {
      return leftOrder - rightOrder;
    }
    if (Number.isFinite(leftOrder)) return -1;
    if (Number.isFinite(rightOrder)) return 1;
    return 0;
  });
  const storyboardClips = orderedSelection.map((item) =>
    buildStoryboardTimelineClip(
      item,
      existingStoryboardClipMap.get(`storyboard:${item.id}`),
    ),
  );
  const materialClips = timelineClips.value
    .filter((item) => String(item.sourceType || "").trim() === "material")
    .map((item) => {
      const material = materialMap.get(
        String(item.materialId || item.sourceId || "").trim(),
      );
      if (!material) return item;
      return {
        ...item,
        ...buildMaterialTimelineClip(material, {
          id: item.id,
          durationSeconds: item.durationSeconds,
          userAdjustedDuration: item.userAdjustedDuration === true,
          visible: item.visible !== false,
        }),
        order: Number(item.order ?? Number.MAX_SAFE_INTEGER),
        startSeconds: item.startSeconds,
        endSeconds: item.endSeconds,
      };
    });
  const nextClips = [...storyboardClips, ...materialClips].sort((left, right) => {
    const leftOrder = Number(
      Number.isFinite(left?.order) ? left.order : Number.MAX_SAFE_INTEGER,
    );
    const rightOrder = Number(
      Number.isFinite(right?.order) ? right.order : Number.MAX_SAFE_INTEGER,
    );
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;
    return String(left.title || "").localeCompare(String(right.title || ""));
  });
  normalizeTimelineSequence(nextClips);
}

function clampDuration(value) {
  return Math.min(
    30,
    Math.max(1, Number.parseInt(String(value || 1), 10) || 1),
  );
}

function normalizeStoryboardDuration(storyboardId) {
  const target = storyboards.value.find((item) => item.id === storyboardId);
  if (!target) return;
  if (isStoryboardDurationLocked(target)) {
    target.durationSeconds = Number(
      target.generatedDurationSeconds || target.durationSeconds || 5,
    );
    return;
  }
  target.durationSeconds = clampDuration(target.durationSeconds);
  target.updatedAt = new Date().toISOString();
  const clip = timelineClips.value.find(
    (item) => item.storyboardId === storyboardId,
  );
  if (clip) {
    clip.durationSeconds = target.durationSeconds;
    normalizeTimelineSequence([...timelineClips.value]);
  }
}

function normalizeClipDuration(clipId) {
  const target = timelineClips.value.find((item) => item.id === clipId);
  if (!target) return;
  if (String(target.sourceType || "").trim() === "material") {
    target.durationSeconds = Math.min(
      clampDuration(target.sourceDurationSeconds || target.durationSeconds),
      clampDuration(target.durationSeconds),
    );
    normalizeTimelineSequence([...timelineClips.value]);
    return;
  }
  if (target.durationLocked !== false) {
    const source = storyboards.value.find(
      (item) => item.id === target.storyboardId,
    );
    target.durationSeconds = Number(
      source?.generatedDurationSeconds || source?.durationSeconds || 5,
    );
    normalizeTimelineSequence([...timelineClips.value]);
    return;
  }
  target.durationSeconds = clampDuration(target.durationSeconds);
  normalizeTimelineSequence([...timelineClips.value]);
  const source = storyboards.value.find(
    (item) => item.id === target.storyboardId,
  );
  if (source) {
    source.durationSeconds = target.durationSeconds;
    source.updatedAt = new Date().toISOString();
  }
}

function setClipVisibility(clipId, visible) {
  const target = timelineClips.value.find((item) => item.id === clipId);
  if (!target) return;
  target.visible = Boolean(visible);
  normalizeTimelineSequence([...timelineClips.value]);
}

function setActiveTimelineClip(clipId) {
  activeTimelineClipId.value = String(clipId || "").trim();
}

function moveTimelineClip(sourceClipId, targetClipId) {
  const nextClips = [...timelineClips.value];
  const sourceIndex = nextClips.findIndex((item) => item.id === sourceClipId);
  if (sourceIndex < 0) return;
  const [movedClip] = nextClips.splice(sourceIndex, 1);
  if (!targetClipId) {
    nextClips.push(movedClip);
  } else {
    const targetIndex = nextClips.findIndex((item) => item.id === targetClipId);
    if (targetIndex < 0) {
      nextClips.push(movedClip);
    } else {
      nextClips.splice(targetIndex, 0, movedClip);
    }
  }
  normalizeTimelineSequence(nextClips);
  activeTimelineClipId.value = movedClip.id;
}

function moveVisibleTimelineClip(sourceClipId, targetClipId) {
  const visibleClips = timelineClips.value.filter((item) => item.visible !== false);
  const sourceIndex = visibleClips.findIndex((item) => item.id === sourceClipId);
  if (sourceIndex < 0) return;
  const nextVisibleClips = [...visibleClips];
  const [movedClip] = nextVisibleClips.splice(sourceIndex, 1);
  if (!targetClipId) {
    nextVisibleClips.push(movedClip);
  } else {
    const targetIndex = nextVisibleClips.findIndex(
      (item) => item.id === targetClipId,
    );
    if (targetIndex < 0) {
      nextVisibleClips.push(movedClip);
    } else {
      nextVisibleClips.splice(targetIndex, 0, movedClip);
    }
  }
  let visibleCursor = 0;
  const nextClips = timelineClips.value.map((item) =>
    item.visible === false ? item : nextVisibleClips[visibleCursor++],
  );
  normalizeTimelineSequence(nextClips);
  activeTimelineClipId.value = movedClip.id;
}

function moveTimelineClipByOffset(clipId, offset) {
  const nextClips = [...timelineClips.value];
  const sourceIndex = nextClips.findIndex((item) => item.id === clipId);
  if (sourceIndex < 0) return;
  const targetIndex = Math.min(
    nextClips.length - 1,
    Math.max(0, sourceIndex + offset),
  );
  if (sourceIndex === targetIndex) return;
  const [movedClip] = nextClips.splice(sourceIndex, 1);
  nextClips.splice(targetIndex, 0, movedClip);
  normalizeTimelineSequence(nextClips);
  activeTimelineClipId.value = movedClip.id;
}

function moveTimelineClipUp(clipId) {
  moveTimelineClipByOffset(clipId, -1);
}

function moveTimelineClipDown(clipId) {
  moveTimelineClipByOffset(clipId, 1);
}

function removeTimelineClip(clipId) {
  const target = timelineClips.value.find((item) => item.id === clipId);
  if (!target) return;
  if (String(target.sourceType || "").trim() === "material") {
    normalizeTimelineSequence(
      timelineClips.value.filter((item) => item.id !== clipId),
    );
    ElMessage.success(`已将「${target.title}」移出当前时间线`);
    void persistStudioDraftSilently();
    return;
  }
  const source = storyboards.value.find(
    (item) => item.id === target.storyboardId,
  );
  if (source) {
    source.selected = false;
    source.updatedAt = new Date().toISOString();
    syncTimelineFromSelection();
  } else {
    normalizeTimelineSequence(
      timelineClips.value.filter((item) => item.id !== clipId),
    );
  }
  ElMessage.success(`已将「${target.title}」移出当前时间线`);
  void persistStudioDraftSilently();
}

function removeTimelineAudioSegment(payload) {
  const kind = String(payload?.kind || "").trim();
  if (kind === "bgm") {
    if (!exportBgmResolvedUrl.value) return;
    clearExportBgmAndPersist();
    return;
  }
  if (kind !== "voice") return;
  const storyboardId = String(payload?.storyboardId || "").trim();
  if (!storyboardId) return;
  const board = storyboards.value.find((item) => item.id === storyboardId);
  if (!board || !resolveStoryboardVoiceResolvedUrl(board)) return;
  clearStoryboardVoiceAudio(board);
  board.hasVoice = false;
  board.selected = false;
  board.status = "draft";
  board.updatedAt = new Date().toISOString();
  syncTimelineFromSelection();
  ElMessage.success(`已移除「${board.title}」旁白`);
  void persistStudioDraftSilently();
}

async function fetchTimelineVideoMaterials() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    timelineVideoMaterials.value = [];
    return;
  }
  loadingTimelineVideoMaterials.value = true;
  try {
    const data = await api.get(`/projects/${currentProjectId}/materials`, {
      params: {
        asset_type: "video",
      },
    });
    timelineVideoMaterials.value = await hydrateTimelineVideoMaterialsDuration(
      data.items || [],
    );
    const materialMap = new Map(
      timelineVideoMaterials.value.map((item) => [String(item.id || "").trim(), item]),
    );
    const refreshedClips = timelineClips.value.map((clip) => {
      if (String(clip.sourceType || "").trim() !== "material") return clip;
      const material = materialMap.get(String(clip.materialId || clip.sourceId || "").trim());
      if (!material) return clip;
      return {
        ...clip,
        ...buildMaterialTimelineClip(material, {
          id: clip.id,
          durationSeconds: clip.durationSeconds,
          userAdjustedDuration: clip.userAdjustedDuration === true,
          visible: clip.visible !== false,
        }),
        startSeconds: clip.startSeconds,
        endSeconds: clip.endSeconds,
        order: clip.order,
      };
    });
    const {
      clips: nextClips,
      repaired: repairedMaterialClipDuration,
    } = repairTimelineMaterialClips(refreshedClips, materialMap);
    if (nextClips.some((item, index) => item !== timelineClips.value[index])) {
      normalizeTimelineSequence(nextClips);
      if (repairedMaterialClipDuration) {
        void persistStudioDraftSilently();
      }
    }
  } catch (err) {
    timelineVideoMaterials.value = [];
    ElMessage.error(err?.detail || err?.message || "加载素材库视频失败");
  } finally {
    loadingTimelineVideoMaterials.value = false;
  }
}

function openTimelineAddDialog(sourceType, sourceId) {
  timelineCandidateSourceType.value = String(sourceType || "storyboard").trim() || "storyboard";
  timelineCandidateId.value = String(sourceId || "").trim();
  historyDialogVisible.value = false;
  timelineAddDialogVisible.value = true;
}

async function openHistoryDialog() {
  historyDialogVisible.value = true;
  await fetchTimelineVideoMaterials();
}

function confirmAddToTimeline() {
  if (timelineCandidateSourceType.value === "material") {
    const material = timelineVideoMaterials.value.find(
      (item) => String(item.id || "").trim() === timelineCandidateId.value,
    );
    if (!material) return;
    const nextClip = buildMaterialTimelineClip(material, {
      visible: true,
      durationSeconds: resolveTimelineMaterialDurationSeconds(material),
    });
    normalizeTimelineSequence([...timelineClips.value, nextClip]);
    activeTimelineClipId.value = nextClip.id;
    timelineAddDialogVisible.value = false;
    ElMessage.success(`已将素材视频「${material.title}」添加到时间线`);
    return;
  }
  const target = storyboards.value.find(
    (item) => item.id === timelineCandidateId.value,
  );
  if (!target) return;
  target.selected = true;
  target.hasVoice = true;
  target.status = "ready";
  target.updatedAt = new Date().toISOString();
  syncTimelineFromSelection();
  timelineAddDialogVisible.value = false;
  ElMessage.success(`已将「${target.title}」添加到时间线`);
}

function openExportDialog() {
  if (!visibleTimelineClips.value.length) {
    ElMessage.warning("请先准备导出分镜");
    return;
  }
  syncTimelineFromSelection();
  exportDialogVisible.value = true;
}

async function submitExport() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  if (!visibleTimelineClips.value.length) {
    ElMessage.warning("请先准备导出分镜");
    return;
  }
  const exportClips = buildStudioExportClipsV2(visibleTimelineClips.value);
  const exportAudioTracks = buildStudioExportAudioTracksV2(timelineAudioTracks.value);
  const formatLabel =
    exportFormatOptions.find((item) => item.value === exportConfig.format)
      ?.label || "MP4";
  const aspectRatio = String(scriptDraft.aspectRatio || "").trim() || "16:9";
  const baseTitle =
    String(scriptDraft.sourceFileName || "")
      .trim()
      .replace(/\.[^.]+$/, "") ||
    String(chapters.value[0]?.title || "").trim() ||
    "短片工作台";
  const exportTitle = `${baseTitle} 正式导出`;
  exporting.value = true;
  try {
    const exportJobResponse = await api.post(
      `/projects/${currentProjectId}/studio/exports`,
      {
        title: exportTitle,
        export_format: exportConfig.format,
        export_resolution: exportConfig.resolution,
        aspect_ratio: aspectRatio,
        timeline_payload: {
          version: "studio-export-v2",
          clips: exportClips,
          summary: {
            title: exportTitle,
            timelineDurationSeconds: Number(timelineDuration.value || 0),
            clipCount: exportClips.length,
          },
        },
        audio_payload: {
          version: "studio-audio-v2",
          mixer: {
            video_volume: resolveStudioAudioMixChannel("video", 1),
            voice_volume: resolveStudioAudioMixChannel("voice", 1),
            bgm_volume: resolveStudioAudioMixChannel("bgm", 0.56),
          },
          tracks: exportAudioTracks,
        },
      },
    );
    const exportJob = normalizeStudioExportJob(exportJobResponse.job || null);
    if (exportJob?.id) {
      studioExportJobs.value = [
        exportJob,
        ...studioExportJobs.value.filter(
          (item) => String(item.id || "").trim() !== String(exportJob.id || "").trim(),
        ),
      ];
    }
    await fetchStudioExportJobs();
    exportDialogVisible.value = false;
    ElMessage.success(`正式导出任务已创建：${formatLabel} / ${exportConfig.resolution}`);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "创建正式导出任务失败");
  } finally {
    exporting.value = false;
  }
}

function openChapterPreview(chapterId) {
  previewChapterId.value = chapterId;
  chapterPreviewVisible.value = true;
}

function openScriptFilePicker() {
  scriptFileInputRef.value?.click?.();
}

function handleScriptFileChange(event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    scriptDraft.content = String(reader.result || "");
    scriptDraft.sourceFileName = file.name;
  };
  reader.readAsText(file);
}

watch(characterDialogVisible, (visible) => {
  if (visible) return;
  characterMaterialDialogVisible.value = false;
  characterGenerateDialogVisible.value = false;
  characterUploadDialogVisible.value = false;
  clearCharacterUploadSelection();
});

watch(
  () => artSettings.providerId,
  () => {
    syncStudioModelSelection(artSettings, artModelProviderOptions.value);
  },
);

watch(
  () => characterGenerateForm.providerId,
  () => {
    syncStudioModelSelection(characterGenerateForm, artModelProviderOptions.value);
  },
);

watch(
  () => storyboardSettings.providerId,
  () => {
    syncStudioModelSelection(
      storyboardSettings,
      storyboardModelProviderOptions.value,
    );
  },
);

watch(
  () => voiceForm.providerId,
  () => {
    syncVoiceModelSelection();
  },
);

watch(
  () => activeStep.value,
  (value) => {
    if (hydratingStudioDraft.value) return;
    if (value === "export") {
      syncTimelineFromSelection();
      void fetchTimelineVideoMaterials();
      void fetchStudioExportJobs();
    }
  },
);

watch(
  () => [
    exportBgmResolvedUrl.value,
    exportBgmDisplayName.value,
    storyboardSettings.sfx,
  ],
  () => {
    syncTimelineAudioTracks([...timelineClips.value]);
  },
);

watch(
  () => requestedStudioDraftJobId.value,
  async (jobId, previousJobId) => {
    const normalizedJobId = String(jobId || "").trim();
    if (!normalizedJobId || normalizedJobId === String(previousJobId || "").trim()) {
      return;
    }
    try {
      const snapshot = await fetchStudioDraftFromWorks(normalizedJobId);
      if (!snapshot) return;
      applyStudioDraft(snapshot, { announce: true });
    } catch (err) {
      ElMessage.error(err?.detail || err?.message || "加载作品草稿失败");
    }
  },
);

watch(
  () => requestedStudioExportJobId.value,
  async (jobId, previousJobId) => {
    const normalizedJobId = String(jobId || "").trim();
    if (!normalizedJobId || normalizedJobId === String(previousJobId || "").trim()) {
      return;
    }
    try {
      await focusStudioExportJob(normalizedJobId, { announce: true });
    } catch (err) {
      ElMessage.error(err?.detail || err?.message || "加载导出任务失败");
    }
  },
);

watch(
  () => ({
    activeStep: activeStep.value,
    scriptDraft: {
      content: scriptDraft.content,
      sourceFileName: scriptDraft.sourceFileName,
      aspectRatio: scriptDraft.aspectRatio,
    },
    styles: styles.value,
    chapters: chapters.value,
    artSettings: {
      kind: artSettings.kind,
      providerId: artSettings.providerId,
      model: artSettings.model,
      duration: artSettings.duration,
      quality: artSettings.quality,
    },
    elements: elements.value,
    extractionResults: extractionResults.value,
    characterForm: {
      voicePreset: characterForm.voicePreset,
      voiceRecordId: characterForm.voiceRecordId,
      voiceId: characterForm.voiceId,
      providerId: characterForm.providerId,
      modelName: characterForm.modelName,
      voiceLabel: characterForm.voiceLabel,
      referenceViews: characterForm.referenceViews,
    },
    storyboardSettings: {
      chapterId: storyboardSettings.chapterId,
      providerId: storyboardSettings.providerId,
      model: storyboardSettings.model,
      duration: storyboardSettings.duration,
      quality: storyboardSettings.quality,
      sfx: storyboardSettings.sfx,
    },
    storyboards: storyboards.value,
    timelineClips: timelineClips.value,
    activeTimelineClipId: activeTimelineClipId.value,
    exportConfig: {
      format: exportConfig.format,
      resolution: exportConfig.resolution,
      bgmEnabled: Boolean(exportBgmResolvedUrl.value),
      bgmSourceType: exportConfig.bgmSourceType,
      bgmTitle: exportConfig.bgmTitle,
      bgmUrl: exportConfig.bgmUrl,
      bgmFileName: exportConfig.bgmFileName,
      bgmMimeType: exportConfig.bgmMimeType,
      bgmStoragePath: exportConfig.bgmStoragePath,
      videoMuted: exportConfig.videoMuted,
      videoVolume: exportConfig.videoVolume,
      voiceMuted: exportConfig.voiceMuted,
      voiceVolume: exportConfig.voiceVolume,
      bgmMuted: exportConfig.bgmMuted,
      bgmVolume: exportConfig.bgmVolume,
    },
  }),
  () => {
    scheduleStudioDraftAutosave();
  },
  { deep: true },
);

onMounted(async () => {
  splitScriptIntoChapters();
  await fetchStudioModelSources();
  await fetchStudioProjectVoices();
  syncVoiceModelSelection();
  pendingStudioDraft.value = readStudioDraft();
  if (!pendingStudioDraft.value) {
    studioDraftAutosaveReady.value = true;
  }
  if (requestedStudioDraftJobId.value) {
    try {
      const snapshot = await fetchStudioDraftFromWorks(requestedStudioDraftJobId.value);
      if (snapshot) {
        applyStudioDraft(snapshot, { announce: true });
      }
    } catch (err) {
      ElMessage.error(err?.detail || err?.message || "加载作品草稿失败");
    }
  }
  if (typeof window !== "undefined") {
    window.addEventListener("beforeunload", handleStudioDraftBeforeUnload);
  }
  await fetchStudioExportJobs();
  if (requestedStudioExportJobId.value) {
    try {
      await focusStudioExportJob(requestedStudioExportJobId.value, { announce: true });
    } catch (err) {
      ElMessage.error(err?.detail || err?.message || "加载导出任务失败");
    }
  }
  startStudioExportJobsPolling();
});

onBeforeUnmount(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("beforeunload", handleStudioDraftBeforeUnload);
    window.clearTimeout(studioDraftAutosaveTimer);
  }
  stopStudioExportJobsPolling();
});
</script>

<style>
.studio-message-box {
  border: 1px solid rgba(226, 232, 240, 0.96) !important;
  border-radius: 24px !important;
  background:
    radial-gradient(
      circle at top right,
      rgba(186, 230, 253, 0.18),
      transparent 26%
    ),
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.99),
      rgba(248, 250, 252, 0.98)
    ) !important;
  box-shadow:
    0 28px 72px rgba(15, 23, 42, 0.16),
    0 12px 28px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.88) !important;
  backdrop-filter: none !important;
}

.studio-message-box .el-message-box__header {
  padding: 20px 20px 16px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.studio-message-box .el-message-box__content {
  padding: 18px 20px;
  background: transparent;
}

.studio-message-box .el-message-box__container,
.studio-message-box .el-message-box__status,
.studio-message-box .el-message-box__message,
.studio-message-box .el-message-box__btns {
  background: transparent;
}

.studio-message-box .el-message-box__message {
  color: #334155;
  font-size: 14px;
  line-height: 1.75;
}

.studio-message-box .el-message-box__btns {
  padding: 18px 20px 20px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
}
</style>

<style scoped>
.studio-workbench {
  --studio-border: rgba(255, 255, 255, 0.92);
  --studio-panel: rgba(255, 255, 255, 0.78);
  --studio-panel-strong: rgba(255, 255, 255, 0.92);
  --studio-line: rgba(15, 23, 42, 0.08);
  --studio-line-strong: rgba(15, 23, 42, 0.12);
  --studio-text: #0f172a;
  --studio-muted: #516071;
  --studio-subtle: #7c8aa0;
  position: relative;
  isolation: isolate;
  width: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 18px 18px 22px;
  box-sizing: border-box;
  background: transparent;
  overflow: hidden;
}

.studio-workbench__ambient,
.studio-workbench__mesh {
  position: absolute;
  pointer-events: none;
}

.studio-workbench__ambient {
  z-index: 0;
  width: 28rem;
  height: 28rem;
  border-radius: 50%;
  filter: blur(72px);
  opacity: 0.72;
}

.studio-workbench__ambient--left {
  top: -10rem;
  left: -12rem;
  background: rgba(125, 211, 252, 0.26);
}

.studio-workbench__ambient--right {
  top: 4rem;
  right: -11rem;
  background: rgba(103, 232, 249, 0.22);
}

.studio-workbench__mesh {
  inset: 0;
  z-index: 0;
  opacity: 0.22;
  background:
    linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
  background-size: 88px 88px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.82), transparent 84%);
}

.studio-stepper-panel,
.studio-surface,
.studio-action-bar {
  position: relative;
  z-index: 1;
  border: 1px solid var(--studio-border);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.9)
  );
  box-shadow:
    0 24px 64px rgba(15, 23, 42, 0.08),
    0 12px 28px rgba(15, 23, 42, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(18px);
}

.studio-draft-banner {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid rgba(249, 115, 22, 0.18);
  border-radius: 24px;
  background: linear-gradient(
    135deg,
    rgba(255, 247, 237, 0.96),
    rgba(255, 255, 255, 0.92)
  );
  box-shadow:
    0 18px 44px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.studio-draft-banner__copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.studio-draft-banner__copy strong {
  color: #9a3412;
  font-size: 14px;
  font-weight: 700;
}

.studio-draft-banner__copy span {
  color: #7c2d12;
  font-size: 12px;
  line-height: 1.7;
}

.studio-draft-banner__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.studio-surface__eyebrow,
.studio-stepper-panel__eyebrow,
.studio-side__eyebrow {
  color: #7c8aa0;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.studio-pill {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 6px 13px;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  background: rgba(255, 255, 255, 0.7);
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  box-sizing: border-box;
}

.studio-stepper-panel {
  padding: 18px 18px 16px;
  border-radius: 30px;
}

.studio-stepper-panel__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 0 4px;
}

.studio-stepper-panel__title {
  margin-top: 6px;
  color: var(--studio-text);
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
}

.studio-stepper-panel__progress {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(255, 255, 255, 0.68);
}

.studio-stepper-panel__progress-label {
  color: var(--studio-subtle);
  font-size: 12px;
  font-weight: 600;
}

.studio-stepper-panel__progress strong {
  color: var(--studio-text);
  font-size: 18px;
  font-weight: 600;
}

.studio-stepper {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.studio-stepper__item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
  padding: 16px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 22px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.88),
    rgba(248, 250, 252, 0.72)
  );
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease;
}

.studio-stepper__item:hover {
  transform: translateY(-2px);
  border-color: rgba(15, 23, 42, 0.12);
  box-shadow: 0 16px 30px rgba(15, 23, 42, 0.06);
}

.studio-stepper__item.is-active {
  border-color: rgba(56, 189, 248, 0.28);
  background:
    radial-gradient(
      circle at top right,
      rgba(125, 211, 252, 0.24),
      transparent 40%
    ),
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.98),
      rgba(240, 249, 255, 0.92)
    );
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.08);
}

.studio-stepper__item.is-completed {
  border-color: rgba(34, 197, 94, 0.14);
  background: linear-gradient(
    180deg,
    rgba(240, 253, 244, 0.84),
    rgba(255, 255, 255, 0.88)
  );
}

.studio-stepper__item.is-blocked {
  opacity: 0.72;
}

.studio-stepper__index {
  flex: none;
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: linear-gradient(135deg, #0f172a, #334155);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18);
}

.studio-stepper__item.is-completed .studio-stepper__index {
  background: linear-gradient(135deg, #059669, #34d399);
}

.studio-stepper__item.is-blocked .studio-stepper__index {
  background: rgba(148, 163, 184, 0.2);
  color: #64748b;
  box-shadow: none;
}

.studio-stepper__copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.studio-stepper__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.studio-stepper__title {
  color: var(--studio-text);
  font-size: 14px;
  font-weight: 600;
}

.studio-stepper__state {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
  font-size: 11px;
  font-weight: 700;
}

.studio-stepper__item.is-active .studio-stepper__state {
  background: rgba(56, 189, 248, 0.14);
  color: #0369a1;
}

.studio-stepper__item.is-completed .studio-stepper__state {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.studio-stepper__desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.studio-stage {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(300px, 0.9fr);
  gap: 16px;
  min-height: 0;
}

.studio-surface {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 20px;
  border-radius: 30px;
  box-sizing: border-box;
}

.studio-surface--main {
  overflow: hidden;
}

.studio-surface--side {
  overflow: auto;
  background:
    radial-gradient(
      circle at top right,
      rgba(186, 230, 253, 0.22),
      transparent 34%
    ),
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.96),
      rgba(248, 250, 252, 0.92)
    );
}

.studio-surface__head,
.studio-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.studio-surface__head {
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.studio-surface__title {
  margin-top: 6px;
  color: var(--studio-text);
  font-size: 24px;
  font-weight: 600;
  line-height: 1.3;
}

.studio-surface__subtitle,
.studio-dialog-copy {
  margin-top: 8px;
  color: #5b6678;
  font-size: 13px;
  line-height: 1.75;
}

.studio-surface__toolbar,
.studio-card__actions,
.studio-action-bar__buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.studio-card,
.studio-note-card {
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 24px;
  background: var(--studio-panel);
  box-shadow:
    0 14px 34px rgba(15, 23, 42, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.55);
  box-sizing: border-box;
}

.studio-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px;
}

.studio-card--wide {
  grid-column: 1 / -1;
}

.studio-card--stack {
  gap: 14px;
}

.studio-card--timeline,
.studio-card--history {
  height: 100%;
}

.studio-card__title,
.studio-side__title,
.studio-dialog-headline {
  color: #0f172a;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.3;
}

.studio-card__meta,
.studio-history-log__meta,
.studio-element-card__meta,
.studio-storyboard-card__meta,
.studio-history-card__meta {
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.6;
}

.studio-script-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.studio-hidden-input {
  display: none;
}

.studio-control-row,
.studio-toggle-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.studio-control-row__group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.studio-control-row__label,
.studio-field__label {
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.studio-chip-group,
.studio-tab-row,
.studio-style-grid,
.studio-voice-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.studio-chip,
.studio-tab,
.studio-style-card,
.studio-voice-card,
.studio-history-card {
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  color: #516071;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease;
}

.studio-chip,
.studio-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 13px;
  font-size: 12px;
  font-weight: 600;
}

.studio-chip.is-active,
.studio-tab.is-active,
.studio-style-card.is-active,
.studio-voice-card.is-active {
  border-color: rgba(56, 189, 248, 0.24);
  background: rgba(240, 249, 255, 0.92);
  color: #0f172a;
}

.studio-tab__count {
  color: #7c8aa0;
}

.studio-style-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.studio-style-card {
  min-height: 52px;
  padding: 12px;
  border-radius: 18px;
  font-size: 13px;
  font-weight: 600;
}

.studio-form-grid {
  display: grid;
  gap: 12px;
}

.studio-form-grid--triple {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.studio-form-grid--storyboard {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.studio-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.studio-field--wide {
  grid-column: 1 / -1;
}

.studio-card__actions--compact {
  justify-content: flex-start;
}

.studio-field :deep(.el-input__wrapper),
.studio-field :deep(.el-select__wrapper),
.studio-script-panel__textarea :deep(.el-textarea__inner) {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow:
    0 0 0 1px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.6);
}

.studio-script-panel__textarea :deep(.el-textarea__inner) {
  min-height: 340px;
  padding: 16px;
  line-height: 1.8;
}

.studio-section-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.studio-section-grid--export {
  grid-template-columns: 1fr;
}

.studio-element-grid,
.studio-storyboard-grid,
.studio-history-grid,
.studio-result-grid,
.studio-chapter-list,
.studio-history-list {
  display: grid;
  gap: 12px;
  min-height: 0;
}

.studio-element-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.studio-storyboard-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.studio-history-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.studio-result-grid {
  margin-top: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.studio-element-card,
.studio-storyboard-card,
.studio-result-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 22px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.92);
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.studio-element-card:hover,
.studio-storyboard-card:hover {
  transform: translateY(-2px);
  border-color: rgba(15, 23, 42, 0.12);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.06);
}

.studio-element-card__visual,
.studio-storyboard-card__preview,
.studio-character-view {
  display: grid;
  place-items: center;
  border-radius: 22px 22px 0 0;
  background:
    linear-gradient(
      135deg,
      rgba(244, 244, 245, 0.96),
      rgba(250, 250, 250, 0.98)
    ),
    #f8fafc;
}

.studio-element-card__visual {
  min-height: 148px;
  color: #64748b;
  font-size: 14px;
  font-weight: 600;
  background:
    radial-gradient(circle at top, rgba(125, 211, 252, 0.2), transparent 54%),
    linear-gradient(
      135deg,
      rgba(244, 244, 245, 0.96),
      rgba(250, 250, 250, 0.98)
    );
}

.studio-storyboard-card__preview {
  position: relative;
  min-height: 190px;
  padding: 16px;
  box-sizing: border-box;
  background:
    radial-gradient(
      circle at top right,
      rgba(125, 211, 252, 0.28),
      transparent 38%
    ),
    linear-gradient(
      135deg,
      rgba(244, 244, 245, 0.96),
      rgba(250, 250, 250, 0.98)
    );
}

.studio-storyboard-card__badge-group {
  position: absolute;
  top: 16px;
  left: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.studio-storyboard-card__placeholder {
  color: #334155;
  font-size: 15px;
  font-weight: 600;
  text-align: center;
}

.studio-element-card__body,
.studio-storyboard-card__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
}

.studio-element-card__title,
.studio-storyboard-card__title,
.studio-result-card__title,
.studio-history-log__title,
.studio-history-card__title,
.studio-timeline-item__title,
.studio-chapter-card__title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}

.studio-element-card__footer,
.studio-storyboard-card__actions,
.studio-chapter-card__footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.studio-storyboard-card__select {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px 16px;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.studio-storyboard-card__select.is-disabled {
  color: #94a3b8;
}

.studio-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  border-radius: 28px;
  border: 1px dashed rgba(15, 23, 42, 0.08);
  background:
    radial-gradient(circle at top, rgba(186, 230, 253, 0.22), transparent 48%),
    rgba(255, 255, 255, 0.46);
}

.studio-empty-state--compact {
  min-height: 160px;
}

.studio-side__panel-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 18px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.studio-side__headline {
  color: var(--studio-text);
  font-size: 22px;
  font-weight: 600;
  line-height: 1.3;
}

.studio-side__caption {
  color: var(--studio-muted);
  font-size: 13px;
  line-height: 1.75;
}

.studio-side__section {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.studio-export-jobs-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.studio-export-jobs-toolbar__search {
  flex: 1;
  min-width: 0;
}

.studio-export-jobs-toolbar__summary {
  flex: none;
  color: #7c8aa0;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.studio-history-list--exports {
  max-height: min(52vh, 560px);
  overflow: auto;
  padding-right: 4px;
  overscroll-behavior: contain;
}

.studio-history-list--exports::-webkit-scrollbar {
  width: 8px;
}

.studio-history-list--exports::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(124, 138, 160, 0.45);
}

.studio-history-list--exports::-webkit-scrollbar-track {
  background: transparent;
}

.studio-chapter-card,
.studio-history-log,
.studio-note-card,
.studio-summary-item,
.studio-progress-item {
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(255, 255, 255, 0.74);
  box-sizing: border-box;
}

.studio-chapter-card,
.studio-history-log,
.studio-note-card {
  padding: 14px;
}

.studio-chapter-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.studio-history-log__head,
.studio-history-log__footer,
.studio-history-log__actions {
  display: flex;
  align-items: center;
}

.studio-history-log__head,
.studio-history-log__footer {
  justify-content: space-between;
  gap: 12px;
}

.studio-history-log__actions {
  gap: 4px;
  flex-wrap: wrap;
}

.studio-history-log--export {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.studio-history-log__meta--error {
  color: #b91c1c;
}

.studio-export-failure-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 16px;
  border: 1px solid rgba(248, 113, 113, 0.22);
  background:
    radial-gradient(circle at top right, rgba(254, 202, 202, 0.32), transparent 42%),
    rgba(254, 242, 242, 0.9);
}

.studio-export-failure-card__title {
  color: #991b1b;
  font-size: 12px;
  font-weight: 700;
}

.studio-export-failure-card__line {
  color: #7f1d1d;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.studio-export-failure-card__hint {
  color: #b45309;
  font-size: 12px;
  line-height: 1.5;
}

.studio-chapter-card__index {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.08);
  color: #0f172a;
  font-size: 11px;
  font-weight: 700;
}

.studio-chapter-card__summary,
.studio-note-card {
  color: #516071;
  font-size: 12px;
  line-height: 1.7;
}

.studio-progress-list,
.studio-summary-list {
  display: grid;
  gap: 10px;
}

.studio-progress-item,
.studio-summary-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 48px;
  padding: 0 14px;
  color: #475569;
  font-size: 13px;
}

.studio-progress-item strong,
.studio-summary-item strong {
  color: #0f172a;
  font-size: 13px;
}

.studio-timeline-list {
  display: grid;
  gap: 10px;
}

.studio-timeline-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(255, 255, 255, 0.76);
}

.studio-timeline-item__meta {
  margin-top: 4px;
  color: #7c8aa0;
  font-size: 12px;
}

.studio-timeline-item__time {
  margin-top: 4px;
  color: #94a3b8;
  font-size: 11px;
}

.studio-duration-control {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #475569;
  font-size: 12px;
}

.studio-duration-control--card {
  margin-top: 2px;
}

.studio-duration-control__value {
  min-width: 32px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  text-align: center;
}

.studio-dialog-body--export {
  gap: 16px;
}

.studio-dialog-body--export-settings {
  grid-template-columns: minmax(0, 1fr) minmax(280px, 320px);
}

.studio-form-grid--export-dialog {
  margin-top: 14px;
}

.studio-history-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  min-height: 88px;
  padding: 14px;
  border-radius: 18px;
  text-align: left;
}

.studio-history-card:hover,
.studio-voice-card:hover,
.studio-style-card:hover {
  transform: translateY(-1px);
}

.studio-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.studio-dialog-body--split {
  display: grid;
  grid-template-columns: minmax(240px, 280px) minmax(0, 1fr);
  align-items: flex-start;
  gap: 16px;
  overflow-x: hidden;
}

.studio-dialog-body--character-form {
  gap: 18px;
}

.studio-dialog-column {
  min-width: 0;
}

.studio-dialog-column--side {
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-self: start;
  min-width: 0;
}

.studio-dialog-column--main {
  min-width: 0;
  overflow-x: hidden;
}

:deep(.studio-dialog) {
  --el-dialog-bg-color: rgba(252, 253, 255, 0.98);
  --el-dialog-padding-primary: 20px;
  margin-top: 10vh;
  max-height: min(calc(100vh - 32px), 920px);
  border: 1px solid rgba(226, 232, 240, 0.96);
  border-radius: 28px;
  box-shadow:
    0 28px 72px rgba(15, 23, 42, 0.14),
    0 12px 28px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.86);
  backdrop-filter: none;
}

:deep(.studio-dialog.el-dialog) {
  display: flex;
  flex-direction: column;
}

:deep(.studio-dialog .el-dialog__header) {
  flex: none;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

:deep(.studio-dialog .el-dialog__body) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-top: 18px;
}

:deep(.studio-dialog .el-dialog__footer) {
  flex: none;
  padding-top: 18px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
}

:deep(.studio-dialog .el-dialog__headerbtn) {
  top: 8px;
  right: 8px;
}

:deep(.studio-dialog--extraction) {
  --el-dialog-bg-color:
    radial-gradient(
      circle at top right,
      rgba(186, 230, 253, 0.18),
      transparent 24%
    ),
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.99),
      rgba(248, 250, 252, 0.98)
    );
}

.studio-dialog-body--extraction {
  gap: 18px;
}

:deep(.studio-dialog--reference .el-dialog__body),
:deep(.studio-dialog--upload .el-dialog__body) {
  max-height: calc(100vh - 224px);
}

:deep(.studio-dialog--character .el-dialog__body) {
  background:
    radial-gradient(
      circle at top right,
      rgba(186, 230, 253, 0.12),
      transparent 24%
    ),
    linear-gradient(
      180deg,
      rgba(249, 250, 251, 0.96),
      rgba(248, 250, 252, 0.92)
    );
  max-height: calc(100vh - 240px);
}

.studio-dialog-hero {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.studio-dialog-hero__copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.studio-dialog-hero__eyebrow {
  color: var(--studio-subtle);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.studio-dialog-hero__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.studio-dialog-hero__meta span {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(248, 250, 252, 0.9);
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.studio-dialog-panel,
.studio-dialog-section,
.studio-dialog-note {
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 22px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.94),
    rgba(248, 250, 252, 0.88)
  );
  box-shadow:
    0 14px 30px rgba(15, 23, 42, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.studio-dialog-panel,
.studio-dialog-section {
  padding: 16px;
}

.studio-dialog-panel__head,
.studio-dialog-section__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.studio-dialog-section__head--stacked {
  justify-content: flex-start;
}

.studio-dialog-section__title {
  color: var(--studio-text);
  font-size: 16px;
  font-weight: 700;
  line-height: 1.45;
}

.studio-dialog-section__desc {
  margin-top: 4px;
  color: var(--studio-subtle);
  font-size: 12px;
  line-height: 1.7;
}

.studio-dialog-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.studio-dialog-summary-grid--compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 0;
}

.studio-dialog-summary-grid--character {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.studio-dialog-summary-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 92px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background:
    radial-gradient(
      circle at top right,
      rgba(186, 230, 253, 0.22),
      transparent 38%
    ),
    rgba(255, 255, 255, 0.84);
}

.studio-dialog-summary-card span {
  color: var(--studio-subtle);
  font-size: 12px;
  font-weight: 600;
}

.studio-dialog-summary-card strong {
  color: var(--studio-text);
  font-size: 28px;
  font-weight: 600;
  line-height: 1;
}

.studio-dialog-summary-grid--compact .studio-dialog-summary-card {
  min-height: 0;
}

.studio-dialog-summary-grid--compact .studio-dialog-summary-card strong {
  font-size: 18px;
  line-height: 1.35;
}

.studio-result-grid--dialog {
  margin-top: 14px;
}

.studio-result-card--extraction {
  gap: 12px;
  padding: 14px;
}

.studio-result-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.studio-result-card__kind,
.studio-result-card__status {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.studio-result-card__kind {
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
}

.studio-result-card__status.is-detected {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.studio-result-card__status.is-pending {
  background: rgba(245, 158, 11, 0.16);
  color: #b45309;
}

.studio-dialog-note {
  padding: 14px 16px;
  color: var(--studio-muted);
  font-size: 12px;
  line-height: 1.8;
}

.studio-dialog-rich-copy {
  color: var(--studio-text);
  font-size: 14px;
  line-height: 1.9;
  white-space: pre-wrap;
}

.studio-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.studio-dialog-footer__hint {
  color: var(--studio-subtle);
  font-size: 12px;
  line-height: 1.6;
}

.studio-dialog-footer > :last-child,
.studio-dialog-footer > :nth-last-child(2) {
  flex: none;
}

.studio-character-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.studio-character-row {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.studio-character-row + .studio-character-row {
  padding-top: 12px;
  border-top: 1px solid rgba(226, 232, 240, 0.72);
}

.studio-character-row__label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 12px;
}

.studio-character-row__name {
  color: #0f172a;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.4;
}

.studio-character-row__caption {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.studio-character-row__body {
  display: grid;
  grid-template-columns: 212px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  min-width: 0;
  padding: 16px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 20px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.92)
  );
  box-shadow:
    0 14px 24px rgba(15, 23, 42, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.76);
}

.studio-character-row__preview {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 158px;
  aspect-ratio: 4 / 3;
  border-radius: 16px;
  background:
    radial-gradient(circle at top, rgba(186, 230, 253, 0.16), transparent 44%),
    #f8fafc;
}

.studio-character-row__image,
.studio-reference-card__image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.studio-character-row__placeholder,
.studio-reference-card__placeholder {
  color: #64748b;
  font-size: 13px;
  font-weight: 600;
}

.studio-character-row__content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.studio-character-row__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.studio-character-row__title {
  color: #0f172a;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.45;
}

.studio-character-row__status {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.14);
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.studio-character-row__status.is-bound {
  background: rgba(16, 185, 129, 0.16);
  color: #047857;
}

.studio-character-row__meta {
  color: #516071;
  font-size: 12px;
  line-height: 1.7;
  min-width: 0;
}

.studio-character-row__actions,
.studio-reference-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-start;
}

.studio-reference-toolbar {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.studio-reference-toolbar > * {
  min-width: 0;
}

.studio-reference-toolbar :deep(.el-button) {
  width: 100%;
  margin: 0;
  justify-content: center;
}

.studio-reference-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
  min-height: 0;
}

.studio-reference-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-radius: 20px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  box-shadow:
    0 12px 24px rgba(15, 23, 42, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
  min-width: 0;
}

.studio-reference-card.is-active {
  border-color: rgba(14, 165, 233, 0.36);
  box-shadow: 0 0 0 1px rgba(14, 165, 233, 0.12);
}

.studio-reference-card__preview {
  position: relative;
  overflow: hidden;
  width: 100%;
  min-height: 164px;
  aspect-ratio: 4 / 3;
  border-radius: 16px;
  background:
    radial-gradient(circle at top, rgba(186, 230, 253, 0.14), transparent 44%),
    #f8fafc;
}

.studio-reference-card__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
}

.studio-reference-card__title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
}

.studio-reference-card__meta,
.studio-reference-upload-hint {
  color: #64748b;
  font-size: 12px;
  line-height: 1.7;
}

.studio-reference-upload-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.studio-reference-upload-preview {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  margin-top: 14px;
  min-height: 220px;
  max-height: 260px;
  border-radius: 18px;
  background: #f8fafc;
}

.studio-reference-upload-preview__image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.studio-voice-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.studio-voice-grid--character {
  margin-top: 14px;
}

.studio-voice-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px;
  border-radius: 18px;
  text-align: left;
}

.studio-voice-card__title {
  color: inherit;
  font-size: 13px;
  font-weight: 600;
}

.studio-voice-card__meta {
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.6;
}

.studio-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 30px;
  position: sticky;
  bottom: 0;
  z-index: 2;
}

.studio-action-bar__summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--studio-muted);
  font-size: 13px;
  line-height: 1.7;
}

.studio-action-bar__draft {
  color: #64748b;
  font-size: 12px;
}

@media (max-width: 1200px) {
  .studio-stage {
    grid-template-columns: 1fr;
  }

  .studio-style-grid,
  .studio-element-grid,
  .studio-result-grid,
  .studio-reference-grid,
  .studio-voice-grid,
  .studio-dialog-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .studio-dialog-summary-grid--character {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .studio-form-grid--storyboard {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .studio-workbench {
    padding: 14px 14px 18px;
    gap: 12px;
  }

  .studio-stepper-panel,
  .studio-surface,
  .studio-action-bar {
    padding: 16px;
    border-radius: 24px;
  }

  .studio-action-bar {
    flex-direction: column;
    align-items: flex-start;
  }

  .studio-draft-banner {
    flex-direction: column;
    align-items: flex-start;
  }

  .studio-draft-banner__actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .studio-stepper-panel__head {
    flex-direction: column;
    align-items: flex-start;
  }

  .studio-stepper {
    grid-template-columns: 1fr;
  }

  .studio-section-grid,
  .studio-style-grid,
  .studio-element-grid,
  .studio-storyboard-grid,
  .studio-result-grid,
  .studio-history-grid,
  .studio-reference-grid,
  .studio-voice-grid,
  .studio-dialog-summary-grid,
  .studio-form-grid--triple,
  .studio-form-grid--storyboard {
    grid-template-columns: 1fr;
  }

  .studio-dialog-body--split {
    grid-template-columns: 1fr;
  }

  .studio-character-row {
    grid-template-columns: 1fr;
  }

  .studio-character-row__label {
    padding-top: 0;
  }

  .studio-character-row__body {
    grid-template-columns: 1fr;
  }

  :deep(.studio-dialog--character .el-dialog__body) {
    background: transparent;
  }

  .studio-surface__title {
    font-size: 20px;
  }

  .studio-side__headline {
    font-size: 20px;
  }

  .studio-timeline-item {
    grid-template-columns: 1fr;
  }

  .studio-dialog-panel__head,
  .studio-dialog-section__head,
  .studio-dialog-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  :deep(.studio-dialog) {
    max-height: calc(100vh - 20px);
    margin-top: 2vh;
  }

  :deep(.studio-dialog--character .el-dialog__body),
  :deep(.studio-dialog--reference .el-dialog__body),
  :deep(.studio-dialog--upload .el-dialog__body) {
    max-height: calc(100vh - 210px);
  }
}
</style>
