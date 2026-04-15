<template>
  <div
    v-loading="loading"
    :class="[
      'project-detail-page',
      { 'project-detail-page--memory-focus': isMemoryTabActive },
    ]"
  >
    <div class="project-detail-shell">
      <section class="project-hero">
        <div class="project-hero__copy">
          <div class="project-hero__eyebrow">Project Settings</div>
          <div class="project-hero__signals">
            <el-tag
              v-for="item in projectHeroSignals"
              :key="item.key"
              size="small"
              effect="plain"
              :type="item.type"
            >
              {{ item.label }}
            </el-tag>
          </div>
          <div class="project-hero__heading">
            <h3>{{ project.name || "项目详情" }}</h3>
            <p>{{ projectHeroDescription }}</p>
          </div>
          <div v-if="!isMemoryTabActive" class="project-hero__stats">
            <div
              v-for="item in projectHeroStats"
              :key="item.label"
              class="project-hero__stats-card"
            >
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </div>
        <div class="project-hero__panel">
          <div class="project-hero__panel-copy">
            <div class="project-hero__panel-eyebrow">Quick Actions</div>
            <h4>{{ projectHeroPanelTitle }}</h4>
            <p>{{ projectHeroPanelDescription }}</p>
          </div>
          <div class="project-hero__actions">
            <div class="project-hero__actions-primary">
              <el-button v-if="canOpenProjectChat" type="primary" @click="openProjectChat"
                >AI 对话</el-button
              >
              <el-button type="primary" plain @click="openMaterialLibrary">素材库</el-button>
            </div>
            <div class="project-hero__actions-secondary">
              <el-button
                v-if="canManageProject"
                :loading="experienceSummaryLoading"
                plain
                @click="openExperienceSummaryDialog"
                >总结经验</el-button
              >
              <el-button v-if="canManageProject" plain @click="openEditDialog">编辑项目</el-button>
              <el-button
                :loading="manualLoading"
                plain
                @click="showProjectManual"
                >使用手册</el-button
              >
              <el-button @click="$router.push('/projects')">返回列表</el-button>
              <el-button @click="refresh">刷新</el-button>
            </div>
          </div>
        </div>
      </section>

      <section class="project-detail-tabs-shell">
        <div class="project-detail-tabs-shell__header">
          <div>
            <div class="block-eyebrow">Workspace</div>
            <h4>同一路由内切换项目设置</h4>
          </div>
          <p>把概览、协作和记忆收进同一层 tabs，减少在列表和详情之间反复返回。</p>
        </div>

        <el-tabs v-model="activeProjectTab" class="project-detail-tabs">
          <el-tab-pane name="overview">
            <template #label>
              <span class="project-detail-tab-label">
                <span class="project-detail-tab-label__title">项目概览</span>
                <span class="project-detail-tab-label__meta">
                  {{ boundUiRules.length }} 条规则
                </span>
              </span>
            </template>

            <div class="project-detail-tab-pane">
              <div v-if="project.id" class="block block--overview">
                <div class="block-header">
                  <div>
                    <div class="block-eyebrow">Overview</div>
                    <h4>项目概览</h4>
                  </div>
                </div>
                <el-descriptions :column="2" border class="project-descriptions">
                  <el-descriptions-item label="项目 ID">{{
                    project.id
                  }}</el-descriptions-item>
                  <el-descriptions-item label="项目名称">{{
                    project.name
                  }}</el-descriptions-item>
                  <el-descriptions-item label="项目类型">
                    <el-tag :type="getProjectTypeTagType(project.type)">
                      {{ getProjectTypeLabel(project.type) }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="创建人">{{
                    project.created_by || "-"
                  }}</el-descriptions-item>
                  <el-descriptions-item
                    v-if="showProjectLocationFields"
                    label="工作区路径"
                    :span="2"
                  >
                    {{ project.workspace_path || "-" }}
                  </el-descriptions-item>
                  <el-descriptions-item
                    v-if="showProjectLocationFields"
                    label="AI 入口文件"
                    :span="2"
                  >
                    {{ project.ai_entry_file || "-" }}
                  </el-descriptions-item>
                  <el-descriptions-item label="MCP">
                    <el-tag :type="project.mcp_enabled ? 'success' : 'info'">
                      {{ project.mcp_enabled ? "开启" : "关闭" }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="反馈升级">
                    <el-tag :type="project.feedback_upgrade_enabled ? 'success' : 'info'">
                      {{ project.feedback_upgrade_enabled ? "开启" : "关闭" }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="描述" :span="2">{{
                    project.description || "-"
                  }}</el-descriptions-item>
                  <el-descriptions-item label="MCP 使用说明" :span="2">{{
                    project.mcp_instruction || "-"
                  }}</el-descriptions-item>
                </el-descriptions>
              </div>

              <div class="block">
                <div class="block-header">
                  <div>
                    <div class="block-eyebrow">UI Rules</div>
                    <h4>UI 规则绑定</h4>
                  </div>
                  <el-button
                    type="primary"
                    size="small"
                    :disabled="!canManageProject"
                    @click="openUiRuleDialog"
                    >编辑绑定</el-button
                  >
                </div>
                <el-alert
                  class="section-alert"
                  title="项目聊天会优先注入这里绑定的 UI 规则，优先级高于员工个人规则。"
                  type="info"
                  :closable="false"
                  show-icon
                />
                <div v-if="boundUiRules.length" class="ui-rule-list">
                  <div v-for="rule in boundUiRules" :key="rule.id" class="ui-rule-card">
                    <div class="ui-rule-card__title">{{ rule.title || rule.id }}</div>
                    <div class="ui-rule-card__meta">
                      <span>{{ rule.id }}</span>
                      <span>{{ rule.domain || "未分类" }}</span>
                    </div>
                  </div>
                </div>
                <el-empty v-else description="当前项目未绑定 UI 规则" :image-size="60" />
              </div>

              <div class="block">
                <div class="block-header">
                  <div>
                    <div class="block-eyebrow">Experience Rules</div>
                    <h4>经验规则</h4>
                  </div>
                  <div v-if="canManageProject" class="block-header__actions">
                    <el-button
                      v-if="hasLegacyProjectExperienceRules"
                      size="small"
                      :loading="experienceRuleMigrating"
                      @click="handleMigrateExperienceRulesToDevelopment"
                      >迁移旧项目经验</el-button
                    >
                    <el-button
                      v-if="boundExperienceRules.length > 1"
                      size="small"
                      :loading="experienceRuleConsolidating"
                      @click="handleConsolidateExperienceRules"
                      >汇总成一条</el-button
                    >
                    <el-button
                      type="primary"
                      size="small"
                      :loading="experienceSummaryLoading"
                      @click="openExperienceSummaryDialog"
                      >总结为开发经验</el-button
                    >
                  </div>
                </div>
                <el-alert
                  class="section-alert"
                  title="这里展示项目引用的经验规则；当前默认会把需求记录沉淀为可复用的开发经验，并把项目绑定到对应规则。"
                  type="info"
                  :closable="false"
                  show-icon
                />
                <div v-if="boundExperienceRules.length" class="ui-rule-list">
                  <div
                    v-for="rule in boundExperienceRules"
                    :key="rule.id"
                    class="ui-rule-card"
                  >
                    <div class="ui-rule-card__title">{{ rule.displayTitle || rule.title || rule.id }}</div>
                    <div class="ui-rule-card__meta">
                      <span>{{ rule.id }}</span>
                      <span>{{ rule.domain || "项目经验" }}</span>
                      <span>{{ rule.systemSource === "project_experience" ? "项目私有" : "开发经验" }}</span>
                    </div>
                    <p v-if="rule.preview" class="experience-rule-card__preview">
                      {{ rule.preview }}
                    </p>
                    <div v-if="canManageProject" class="experience-rule-card__actions">
                      <el-button
                        text
                        type="primary"
                        size="small"
                        :loading="experienceRuleEditingLoading && editingExperienceRuleId === rule.id"
                        @click="openExperienceRuleEditDialog(rule)"
                        >编辑规则</el-button
                      >
                      <el-button
                        text
                        type="danger"
                        size="small"
                        :loading="experienceRuleDeletingLoading && deletingExperienceRuleId === rule.id"
                        @click="handleDeleteExperienceRule(rule)"
                        >删除规则</el-button
                      >
                    </div>
                  </div>
                </div>
                <el-empty v-else description="当前项目还没有沉淀经验规则" :image-size="60" />
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane name="access">
            <template #label>
              <span class="project-detail-tab-label">
                <span class="project-detail-tab-label__title">协作设置</span>
                <span class="project-detail-tab-label__meta">
                  {{ accessTabMeta }}
                </span>
              </span>
            </template>

            <div class="project-detail-tab-pane">
              <div class="block">
                <div class="block-header">
                  <div>
                    <div class="block-eyebrow">Access</div>
                    <h4>可见用户</h4>
                  </div>
                  <el-button
                    type="primary"
                    size="small"
                    :disabled="!canManageProjectUsers"
                    @click="openAddUserDialog"
                    >添加用户</el-button
                  >
                </div>

                <el-table :data="pagedProjectUsers" stripe class="section-table">
                  <el-table-column prop="username" label="用户名" width="180" />
                  <el-table-column prop="role" label="项目角色" width="120" />
                  <el-table-column prop="user_role" label="系统角色" width="140">
                    <template #default="{ row }">
                      <span>{{ row.user_role || "-" }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="状态" width="120">
                    <template #default="{ row }">
                      <el-tag :type="row.enabled ? 'success' : 'info'">{{
                        row.enabled ? "启用" : "停用"
                      }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="用户存在" width="120">
                    <template #default="{ row }">
                      <el-tag :type="row.user_exists ? 'success' : 'danger'">{{
                        row.user_exists ? "正常" : "已删除"
                      }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="加入时间" min-width="220" show-overflow-tooltip>
                    <template #default="{ row }">{{ row.joined_at || "-" }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="140" fixed="right">
                    <template #default="{ row }">
                      <el-button
                        text
                        type="danger"
                        size="small"
                        :disabled="!canManageProjectUsers"
                        @click="removeProjectUser(row)"
                        >移除</el-button
                      >
                    </template>
                  </el-table-column>
                </el-table>

                <div v-if="projectUsers.length" class="table-panel__pagination">
                  <el-pagination
                    v-model:current-page="projectUsersPage"
                    v-model:page-size="projectUsersPageSize"
                    background
                    layout="total, prev, pager, next, jumper, sizes"
                    :total="projectUsers.length"
                    :page-sizes="[10, 20, 50]"
                  />
                </div>

                <el-empty v-if="!projectUsers.length" description="暂无可见用户" />
              </div>

              <div class="block">
                <div class="block-header">
                  <div>
                    <div class="block-eyebrow">Members</div>
                    <h4>成员管理</h4>
                  </div>
                  <el-button
                    type="primary"
                    size="small"
                    :disabled="!canManageProjectUsers"
                    @click="openAddMember"
                    >添加成员</el-button
                  >
                </div>

                <el-table :data="pagedMembers" stripe class="section-table">
                  <el-table-column prop="employee_id" label="员工 ID" width="150" />
                  <el-table-column label="员工名称" width="180">
                    <template #default="{ row }">
                      <el-button
                        text
                        type="primary"
                        :disabled="!row.employee_id"
                        @click="openEmployeeDetail(row)"
                      >
                        {{ row.employee_name || row.employee_id || "-" }}
                      </el-button>
                    </template>
                  </el-table-column>
                  <el-table-column prop="role" label="角色" width="120" />
                  <el-table-column label="状态" width="120">
                    <template #default="{ row }">
                      <el-tag :type="row.enabled ? 'success' : 'info'">{{
                        row.enabled ? "启用" : "停用"
                      }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="员工 MCP" width="120">
                    <template #default="{ row }">
                      <el-tag :type="row.employee_mcp_enabled ? 'success' : 'warning'">
                        {{ row.employee_mcp_enabled ? "可用" : "关闭" }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="加入时间" min-width="220" show-overflow-tooltip>
                    <template #default="{ row }">{{ row.joined_at || "-" }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="190" fixed="right">
                    <template #default="{ row }">
                      <el-button
                        text
                        type="primary"
                        size="small"
                        :disabled="!row.employee_id"
                        @click="openEmployeeDetail(row)"
                        >详情</el-button
                      >
                      <el-button
                        text
                        type="danger"
                        size="small"
                        :disabled="!canManageProjectUsers"
                        @click="removeMember(row)"
                        >移除</el-button
                      >
                    </template>
                  </el-table-column>
                </el-table>

                <div v-if="members.length" class="table-panel__pagination">
                  <el-pagination
                    v-model:current-page="membersPage"
                    v-model:page-size="membersPageSize"
                    background
                    layout="total, prev, pager, next, jumper, sizes"
                    :total="members.length"
                    :page-sizes="[10, 20, 50]"
                  />
                </div>

                <el-empty v-if="!members.length" description="暂无成员" />
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane name="memory">
            <template #label>
                <span class="project-detail-tab-label">
                  <span class="project-detail-tab-label__title">需求记录</span>
                  <span class="project-detail-tab-label__meta">
                  {{ requirementRecordTabMeta }}
                  </span>
                </span>
              </template>

            <div class="project-detail-tab-pane">
              <div class="block block--memory-primary">
                <div class="block-header block-header--memory">
                  <div>
                    <div class="block-eyebrow">Requirement Records</div>
                    <h4>需求记录</h4>
                  </div>
                  <div class="toolbar-actions">
                    <el-tag size="small" effect="plain" :type="taskTreeStorageBackendTagType">
                      {{ taskTreeStorageBackendLabel }}
                    </el-tag>
                    <el-button
                      text
                      size="small"
                      :loading="loading || taskSessionsLoading || taskTreeDetailsLoading"
                      @click="refreshRequirementRecords"
                    >
                      刷新映射
                    </el-button>
                  </div>
                </div>
                <div class="memory-overview-strip">
                  <div
                    v-for="item in memoryOverviewItems"
                    :key="item.label"
                    class="memory-overview-card"
                  >
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                    <small>{{ item.meta }}</small>
                  </div>
                </div>
                <div v-if="requirementRecords.length" class="memory-health-shell">
                  <div class="memory-health-shell__head">
                    <div>
                      <div class="block-eyebrow">Action Queue</div>
                      <h5>待处理事项</h5>
                    </div>
                    <p>这里不再只做分类统计，直接给出继续处理、重建任务树和清空入口。</p>
                  </div>
                  <div class="memory-health-strip">
                    <div
                      v-for="item in taskActionOverviewItems"
                      :key="item.label"
                      class="memory-health-card"
                      :class="`is-${item.tone}`"
                    >
                      <span>{{ item.label }}</span>
                      <strong>{{ item.value }}</strong>
                      <small>{{ item.meta }}</small>
                    </div>
                  </div>
                  <div v-if="taskActionItems.length" class="memory-health-grid">
                    <article
                      v-for="item in taskActionItems"
                      :key="item.key"
                      class="memory-health-highlight"
                      :class="`is-${item.tone}`"
                    >
                      <div class="memory-health-highlight__head">
                        <div>
                          <div class="memory-health-highlight__eyebrow">
                            {{ item.eyebrow }}
                          </div>
                          <h6>{{ item.title }}</h6>
                        </div>
                        <el-tag size="small" effect="plain" :type="item.tagType">
                          {{ item.label }}
                        </el-tag>
                      </div>
                      <p>{{ item.summary }}</p>
                      <div class="memory-health-highlight__meta">
                        <span>{{ item.progress }}</span>
                        <span>{{ item.focus }}</span>
                      </div>
                      <div class="memory-health-highlight__actions">
                        <el-button plain size="small" @click="focusRequirementRecord(item.record)">
                          定位需求
                        </el-button>
                        <el-button
                          v-if="item.canContinue"
                          type="primary"
                          plain
                          size="small"
                          @click="openProjectChat(item.round.chatSessionId)"
                        >
                          继续处理
                        </el-button>
                        <el-button
                          v-if="canManageProject && item.canRebuildTaskTree"
                          type="warning"
                          plain
                          size="small"
                          :loading="isRequirementRecordTaskTreeRegenerating(item.record)"
                          @click="handleRegenerateRequirementRecordTaskTree(item.record)"
                        >
                          重建任务树
                        </el-button>
                        <el-button
                          v-if="canManageProject && item.canClearTaskTree"
                          plain
                          size="small"
                          :loading="isRequirementRecordTaskTreeClearing(item.record)"
                          @click="handleClearRequirementRecordTaskTree(item.record)"
                        >
                          清空任务树
                        </el-button>
                        <el-button
                          v-if="canManageProject"
                          type="danger"
                          plain
                          size="small"
                          :loading="requirementRecordDeleting"
                          @click="handleDeleteRequirementRecord(item.record)"
                        >
                          删除整条
                        </el-button>
                      </div>
                    </article>
                  </div>
                  <el-empty
                    v-else
                    description="当前没有需要手动处理的需求"
                    :image-size="56"
                  />
                </div>
                <div class="memory-toolbar-shell">
                  <div class="memory-toolbar-shell__copy">
                    <p>
                      这里按“需求主记录 + 计划节点 + 进展记录”统一展示。未完成的需求只显示计划和状态，全部完成并验证后才显示最终结论。
                    </p>
                  </div>
                  <div class="memory-filters">
                    <el-input
                      class="memory-filter-control memory-filter-control--search"
                      v-model="memoryFilters.query"
                      clearable
                      placeholder="按内容关键词筛选"
                      @keyup.enter="applyMemoryFilters"
                    />
                    <el-select
                      class="memory-filter-control memory-filter-control--employee"
                      v-model="memoryFilters.employeeId"
                      clearable
                      filterable
                      placeholder="全部员工"
                    >
                      <el-option
                        v-for="item in members"
                        :key="item.employee_id"
                        :label="`${item.employee_name || item.employee_id} (${item.employee_id})`"
                        :value="item.employee_id"
                      />
                    </el-select>
                    <el-select
                      class="memory-filter-control memory-filter-control--type"
                      v-model="memoryFilters.type"
                      clearable
                      placeholder="全部类型"
                    >
                      <el-option
                        v-for="item in memoryTypeOptions"
                        :key="item.value"
                        :label="item.label"
                        :value="item.value"
                      />
                    </el-select>
                    <el-select
                      class="memory-filter-control memory-filter-control--limit"
                      v-model="memoryFilters.limit"
                    >
                      <el-option
                        v-for="size in memoryLimitOptions"
                        :key="size"
                        :label="`最近 ${size} 条`"
                        :value="size"
                      />
                    </el-select>
                  <div class="memory-filters__actions">
                      <el-button
                        type="primary"
                        :loading="taskSessionsLoading"
                        @click="applyMemoryFilters"
                        >刷新结果</el-button
                      >
                      <el-button
                        plain
                        :loading="memoryLoading || workSessionLoading"
                        @click="exportProjectMemories"
                        >导出</el-button
                      >
                      <el-button :disabled="taskSessionsLoading" @click="resetMemoryFilters"
                        >重置</el-button
                      >
                    </div>
                  </div>
                  <div v-if="memoryWindowHint" class="memory-filters__hint">
                    {{ memoryWindowHint }}
                  </div>
                </div>
                <div
                  v-if="canManageProject"
                  class="requirement-record-toolbar"
                >
                  <div class="requirement-record-toolbar__copy">
                    <el-tag effect="plain" type="info">
                      已选 {{ selectedRequirementRecordCount }} / {{ requirementRecords.length }}
                    </el-tag>
                    <span>删除全部仅作用于当前筛选结果。</span>
                  </div>
                  <div class="requirement-record-toolbar__actions">
                    <el-button
                      v-if="canManageProject"
                      type="primary"
                      size="small"
                      :loading="experienceSummaryLoading"
                      :disabled="!requirementRecords.length || requirementRecordDeleting"
                      @click="openExperienceSummaryDialog"
                    >
                      总结为开发经验
                    </el-button>
                    <el-button
                      size="small"
                      :disabled="!requirementRecords.length || requirementRecordDeleting"
                      @click="toggleSelectAllRequirementRecords"
                    >
                      {{ allRequirementRecordsSelected ? "取消全选" : "全选当前结果" }}
                    </el-button>
                    <el-button
                      plain
                      type="danger"
                      size="small"
                      :loading="requirementRecordDeleting"
                      :disabled="!selectedRequirementRecordCount"
                      @click="handleBatchDeleteRequirementRecords"
                    >
                      删除所选
                    </el-button>
                    <el-button
                      type="danger"
                      size="small"
                      :loading="requirementRecordDeleting"
                      :disabled="!requirementRecords.length"
                      @click="handleDeleteAllRequirementRecords"
                    >
                      删除当前结果
                    </el-button>
                  </div>
                </div>

                <div
                  class="requirement-records"
                  v-loading="taskSessionsLoading || taskTreeDetailsLoading"
                >
                  <article
                    v-for="record in pagedRequirementRecords"
                    :key="record.id"
                    :id="`requirement-record-${record.id}`"
                    class="requirement-record"
                    :class="{ 'requirement-record--expanded': isRequirementRecordExpanded(record) }"
                  >
                    <div class="requirement-record__hero">
                      <div class="requirement-record__hero-copy">
                        <div class="requirement-record__eyebrow">Requirement Chain</div>
                        <h5>{{ record.rootGoal || "未命名需求" }}</h5>
                        <p>{{ record.summaryText || record.currentFocus || record.completionGate }}</p>
                      </div>
                      <div class="requirement-record__hero-actions">
                        <el-checkbox
                          v-if="canManageProject"
                          :model-value="isRequirementRecordSelected(record)"
                          :disabled="requirementRecordDeleting"
                          @change="toggleRequirementRecordSelection(record.id, $event)"
                        >
                          选择
                        </el-checkbox>
                        <el-tag :type="record.statusTagType">
                          {{ record.statusLabel }}
                        </el-tag>
                        <el-button
                          plain
                          size="small"
                          @click="toggleRequirementRecordExpansion(record)"
                        >
                          {{ isRequirementRecordExpanded(record) ? "收起详情" : "展开详情" }}
                        </el-button>
                        <el-button text @click="openRequirementRecordDetail(record)">
                          查看整轮
                        </el-button>
                        <el-button
                          v-if="canManageProject"
                          type="danger"
                          plain
                          size="small"
                          :loading="requirementRecordDeleting"
                          @click="handleDeleteRequirementRecord(record)"
                        >
                          删除
                        </el-button>
                      </div>
                    </div>

                    <div class="requirement-record__supporting">
                      <el-tag effect="plain" type="success">
                        {{ Number(record.progressPercent || 0) }}%
                      </el-tag>
                      <el-tag
                        v-if="record.repairRoundCount"
                        effect="plain"
                        type="warning"
                      >
                        {{ record.repairRoundCount }} 次修复
                      </el-tag>
                      <el-tag
                        v-if="record.activeRoundCount"
                        effect="plain"
                        type="info"
                      >
                        {{ record.activeRoundCount }} 轮进行中
                      </el-tag>
                      <span>{{ record.actorLabel }}</span>
                      <span>{{ record.roundDigest }}</span>
                      <span>{{ formatDateTime(record.updatedAt || record.createdAt) }}</span>
                    </div>

                    <div class="requirement-record__lineage">
                      <section class="requirement-record__lineage-item">
                        <span>当前状态</span>
                        <strong>{{ record.statusLabel }}</strong>
                        <small>{{ record.summaryText || record.completionGate }}</small>
                      </section>
                      <section class="requirement-record__lineage-item">
                        <span>当前轮次</span>
                        <strong>
                          {{
                            record.detailRound
                              ? `第 ${record.detailRound.roundIndex} 轮`
                              : "等待建立轮次"
                          }}
                        </strong>
                        <small>
                          {{
                            record.detailRound
                              ? getRequirementRecordKindLabel(record.detailRound.recordKind)
                              : "主需求轮次"
                          }}
                        </small>
                      </section>
                      <section class="requirement-record__lineage-item">
                        <span>当前焦点</span>
                        <strong>{{ record.currentFocus }}</strong>
                        <small>
                          {{
                            `${record.progressDigest} · ${
                              record.detailWorkSessionCount
                                ? `${record.detailWorkSessionCount} 条轨迹`
                                : "暂无轨迹"
                            }`
                          }}
                        </small>
                      </section>
                    </div>

                    <el-collapse-transition>
                      <div
                        v-show="isRequirementRecordExpanded(record)"
                        class="requirement-record__detail-shell"
                      >
                        <div
                          class="requirement-record__tree-board"
                          v-loading="isRequirementRoundTaskTreeLoading(record.detailRound)"
                        >
                          <div class="requirement-record__detail-head">
                            <div>
                              <div class="requirement-record__detail-eyebrow">On Demand</div>
                              <h6>任务树与执行细节</h6>
                            </div>
                            <p>点击节点再看工作细节和测试结果。</p>
                          </div>
                          <div class="requirement-record__tree-hint">
                            当前只保留主链结构，详细过程统一收进节点弹窗，避免列表里堆太多文字。
                          </div>
                          <RequirementTreeNode
                            v-if="record.detailRound?.rootNode"
                            :node="record.detailRound.rootNode"
                            :current-node-id="record.detailRound.currentNodeId"
                            @select="openRequirementNodeDetail($event, record.detailRound)"
                          />
                          <el-empty
                            v-else
                            description="当前需求还没有可展示的任务树"
                            :image-size="56"
                          />
                        </div>
                      </div>
                    </el-collapse-transition>
                  </article>

                  <el-empty
                    v-if="!requirementRecords.length && !memoryLoading"
                    description="暂无匹配的需求记录"
                  />
                </div>

                <div v-if="requirementRecords.length" class="table-panel__pagination">
                  <el-pagination
                    v-model:current-page="requirementRecordsPage"
                    v-model:page-size="requirementRecordsPageSize"
                    background
                    layout="total, prev, pager, next, jumper, sizes"
                    :total="requirementRecords.length"
                    :page-sizes="[10, 20, 50]"
                  />
                </div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane v-if="showProjectAddressFields" name="mcp">
            <template #label>
              <span class="project-detail-tab-label">
                <span class="project-detail-tab-label__title">MCP 接入</span>
                <span class="project-detail-tab-label__meta">SSE / HTTP</span>
              </span>
            </template>

            <div class="project-detail-tab-pane">
              <div class="block">
                <div class="block-header">
                  <div>
                    <div class="block-eyebrow">MCP</div>
                    <h4>项目 MCP 地址</h4>
                  </div>
                </div>
                <el-descriptions :column="1" border class="project-descriptions">
                  <el-descriptions-item label="SSE">
                    <code>{{ projectMcpSseUrl }}</code>
                  </el-descriptions-item>
                  <el-descriptions-item label="HTTP">
                    <code>{{ projectMcpHttpUrl }}</code>
                  </el-descriptions-item>
                </el-descriptions>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>

    <el-dialog v-model="showAddDialog" title="添加项目成员" width="520px">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="员工" required>
          <el-select
            v-model="addForm.employee_ids"
            multiple
            collapse-tags
            collapse-tags-tooltip
            filterable
            placeholder="请选择员工（可多选）"
            style="width: 100%"
          >
            <el-option
              v-for="item in availableEmployeeOptions"
              :key="item.id"
              :label="`${item.name} (${item.id})`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-input v-model="addForm.role" placeholder="member / owner" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="addForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="addMember"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog v-model="showAddUserDialog" title="添加可见用户" width="520px">
      <el-form :model="userForm" label-width="100px">
        <el-form-item label="用户" required>
          <el-select
            v-model="userForm.usernames"
            multiple
            collapse-tags
            collapse-tags-tooltip
            filterable
            placeholder="请选择用户（可多选）"
            style="width: 100%"
          >
            <el-option
              v-for="item in availableUserOptions"
              :key="item.username"
              :label="`${item.username} (${item.role_name || item.role || '-'})`"
              :value="item.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="项目角色">
          <el-input v-model="userForm.role" placeholder="member / owner" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="userForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddUserDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="addProjectUsers"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog v-model="showUiRuleDialog" title="UI 规则绑定" width="620px">
      <el-form :model="uiRuleForm" label-width="100px">
        <el-form-item label="绑定规则">
          <el-select
            v-model="uiRuleForm.rule_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="请选择项目级 UI 规则"
            style="width: 100%"
          >
            <el-option
              v-for="item in ruleOptions"
              :key="item.id"
              :label="item.domain ? `${item.title} (${item.domain})` : item.title"
              :value="item.id"
            />
          </el-select>
          <div class="ui-rule-help">
            这里只绑定项目级 UI 规范。保存后，项目聊天会优先注入这些规则。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUiRuleDialog = false">取消</el-button>
        <el-button type="primary" :loading="uiRuleSaving" @click="saveUiRuleBindings"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑项目" width="520px">
      <el-form :model="editForm" label-width="110px">
        <el-form-item label="项目名称" required>
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="项目描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="项目类型">
          <el-select v-model="editForm.type" style="width: 100%">
            <el-option
              v-for="item in projectTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            >
              <div class="project-type-option">
                <div class="project-type-option__label">{{ item.label }}</div>
                <div class="project-type-option__desc">{{ item.description }}</div>
              </div>
            </el-option>
          </el-select>
          <div class="project-type-help">{{ getProjectTypeDescription(editForm.type) }}</div>
        </el-form-item>
        <el-form-item label="MCP 使用说明">
          <el-input
            v-model="editForm.mcp_instruction"
            type="textarea"
            :rows="4"
            placeholder="给外部模型看的接入说明，例如先读 usage guide，再看项目成员和工具"
          />
        </el-form-item>
        <el-form-item v-if="showProjectLocationFields" label="工作区路径">
          <el-input v-model="editForm.workspace_path" placeholder="可手动输入或点击选择目录">
            <template #append>
              <el-button @click="selectWorkspaceDirectory">选择目录</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item v-if="showProjectLocationFields" label="AI 入口文件">
          <el-input v-model="editForm.ai_entry_file" placeholder="如 .ai/ENTRY.md 或 /abs/path/to/ENTRY.md">
            <template #append>
              <el-button @click="selectAiEntryFile">选择文件</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="启用 MCP">
          <el-switch v-model="editForm.mcp_enabled" />
        </el-form-item>
        <el-form-item label="反馈升级">
          <el-switch v-model="editForm.feedback_upgrade_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showManualDialog"
      :title="manualDialogTitle"
      width="760px"
    >
      <div v-loading="manualLoading">
        <el-alert
          v-if="generatedManual"
          title="项目使用手册加载成功"
          type="success"
          show-icon
          :closable="false"
          style="margin-bottom: 16px"
        />
        <div v-if="generatedManual" class="prompt-content">
          <div class="prompt-rendered" v-html="renderedManualHtml"></div>
        </div>
        <el-empty
          v-else
          description="点击下方按钮加载使用手册"
          :image-size="60"
        />
      </div>
      <template #footer>
        <el-button v-if="generatedManual" type="primary" @click="copyManual"
          >复制使用手册</el-button
        >
        <el-button
          type="success"
          :loading="manualLoading"
          @click="showProjectManual"
          >加载使用手册</el-button
        >
        <el-button @click="showManualDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <ModelProviderPickerDialog
      v-model="showExperienceSummaryDialog"
      title="选择总结模型"
      :description="experienceSummaryDialogDescription"
      confirm-text="开启总结经验工作流"
      :internal-providers="experienceProviderOptions"
      :loading="experienceProvidersLoading || experienceSummaryLoading"
      :provider-id="experienceSummaryProviderId"
      :model-name="experienceSummaryModelName"
      @update:provider-id="experienceSummaryProviderId = $event"
      @update:model-name="experienceSummaryModelName = $event"
      @confirm="handleConfirmExperienceSummary"
    />

    <el-dialog
      v-model="showExperienceRuleEditDialog"
      title="编辑经验规则"
      width="760px"
    >
      <el-form label-width="92px">
        <el-form-item label="标题">
          <el-input
            v-model="experienceRuleEditForm.title"
            placeholder="输入经验规则标题"
          />
        </el-form-item>
        <el-form-item label="内容">
          <el-input
            v-model="experienceRuleEditForm.content"
            type="textarea"
            :rows="18"
            placeholder="输入经验规则正文"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showExperienceRuleEditDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="experienceRuleEditSaving"
          @click="handleSaveExperienceRuleEdit"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="showRequirementNodeDetailDialog"
      class="memory-detail-dialog"
      width="920px"
      top="8vh"
    >
      <template #header>
        <div class="memory-detail-dialog__header">
          <div>
            <div class="memory-detail-dialog__eyebrow">
              {{ selectedRequirementNodeIsRoot ? "Requirement Chain" : "Task Node Detail" }}
            </div>
            <h3>{{ selectedRequirementNodeDetailTitle }}</h3>
          </div>
          <div class="memory-detail-dialog__header-tags">
            <el-tag
              v-if="selectedRequirementNode"
              effect="plain"
              :type="getTaskSessionStatusTagType(selectedRequirementNode.status)"
            >
              {{ getTaskSessionStatusLabel(selectedRequirementNode.status) }}
            </el-tag>
            <el-tag
              v-if="selectedRequirementNodeRound"
              effect="plain"
              :type="getRequirementRecordKindTagType(selectedRequirementNodeRound.recordKind)"
            >
              {{ getRequirementRecordKindLabel(selectedRequirementNodeRound.recordKind) }}
            </el-tag>
          </div>
        </div>
      </template>
      <div v-loading="requirementNodeDetailLoading">
        <template v-if="selectedRequirementNode">
          <div class="memory-detail-shell">
            <section class="memory-detail-hero">
              <div class="memory-detail-hero__content">
                <div class="memory-detail-hero__eyebrow">
                  {{ selectedRequirementNodeIsRoot ? "Requirement Chain" : "Task Node" }}
                </div>
                <h4>{{ selectedRequirementNode.title || "-" }}</h4>
                <p>{{ selectedRequirementNodeDescriptionText }}</p>
              </div>
              <div class="memory-detail-hero__status">
                <div class="memory-detail-status-card">
                  <span>所属轮次</span>
                  <strong>{{ selectedRequirementNodeRoundLabel }}</strong>
                </div>
                <div class="memory-detail-status-card">
                  <span>工作细节</span>
                  <strong>{{ selectedRequirementNodeEvents.length }} 条</strong>
                </div>
                <div class="memory-detail-status-card">
                  <span>测试结果</span>
                  <strong>{{ selectedRequirementNodeVerificationItems.length }} 条</strong>
                </div>
              </div>
            </section>

            <section class="memory-detail-meta-grid">
              <div class="memory-detail-meta-card">
                <span class="memory-detail-meta-card__label">完成条件</span>
                <strong>{{ selectedRequirementNode.completion_criteria || "-" }}</strong>
              </div>
              <div class="memory-detail-meta-card">
                <span class="memory-detail-meta-card__label">验证方式</span>
                <strong>{{ selectedRequirementNodeVerificationMethodText || "-" }}</strong>
              </div>
              <div class="memory-detail-meta-card">
                <span class="memory-detail-meta-card__label">当前结果</span>
                <strong>{{ selectedRequirementNodeOutcomeText }}</strong>
              </div>
              <div class="memory-detail-meta-card">
                <span class="memory-detail-meta-card__label">验证结果</span>
                <strong>{{ selectedRequirementNodeVerificationResultText }}</strong>
              </div>
            </section>

            <section class="memory-detail-section">
              <div class="memory-detail-section__header">
                <div>
                  <div class="memory-detail-section__eyebrow">Execution Detail</div>
                  <h4>工作细节</h4>
                </div>
              </div>
              <div v-if="selectedRequirementNodeEvents.length" class="memory-detail-task-events">
                <div
                  v-for="event in selectedRequirementNodeEvents"
                  :key="event.id || `${event.session_id}-${event.created_at}`"
                  class="memory-detail-plan__event"
                >
                  <div class="memory-detail-plan__event-row">
                    <div class="memory-detail-plan__event-title">
                      {{ event.phase || event.event_type || "工作轨迹" }}
                      <template v-if="event.step"> / {{ event.step }}</template>
                    </div>
                    <el-tag
                      size="small"
                      effect="plain"
                      :type="getWorkSessionStatusTagType(event.status)"
                    >
                      {{ event.status || event.event_type || "-" }}
                    </el-tag>
                  </div>
                  <p>{{ summarizeProjectWorkEvent(event) }}</p>
                  <div v-if="event.changed_files?.length" class="memory-detail-plan__event-meta">
                    文件：{{ event.changed_files.join(" / ") }}
                  </div>
                  <div class="memory-detail-plan__event-meta">
                    {{ event.session_id || "-" }} · {{ event.employee_name || "-" }} ·
                    {{ formatDateTime(event.created_at) }}
                  </div>
                </div>
              </div>
              <el-empty
                v-else
                :description="selectedRequirementNodeIsRoot ? '当前总目标还没有汇总出整轮工作细节' : '当前节点还没有写入工作细节'"
                :image-size="56"
              />
            </section>

            <section class="memory-detail-section">
              <div class="memory-detail-section__header">
                <div>
                  <div class="memory-detail-section__eyebrow">Verification</div>
                  <h4>测试结果</h4>
                </div>
              </div>
              <div v-if="selectedRequirementNodeVerificationItems.length" class="memory-detail-tags">
                <el-tag
                  v-for="(item, index) in selectedRequirementNodeVerificationItems"
                  :key="`${selectedRequirementNode?.id || 'node'}-${index}`"
                  effect="plain"
                  type="success"
                >
                  {{ item }}
                </el-tag>
              </div>
              <div v-else class="memory-detail-block">
                {{ selectedRequirementNodeIsRoot ? "当前总目标还没有汇总出测试结果。" : "当前节点还没有测试结果。" }}
              </div>
            </section>
          </div>
        </template>
        <el-empty v-else description="未加载到节点详情" :image-size="56" />
      </div>
      <template #footer>
        <el-button @click="showRequirementNodeDetailDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showMemoryDetailDialog"
      class="memory-detail-dialog"
      width="960px"
      top="6vh"
    >
      <template #header>
        <div class="memory-detail-dialog__header">
          <div>
            <div class="memory-detail-dialog__eyebrow">Requirement Detail</div>
            <h3>需求详情</h3>
          </div>
          <div class="memory-detail-dialog__header-tags">
            <el-tag
              v-if="selectedMemoryDetail"
              effect="plain"
              :type="getMemorySolveStatusTagType(selectedMemoryDetail.solve_status)"
            >
              {{ getMemorySolveStatusLabel(selectedMemoryDetail.solve_status) }}
            </el-tag>
            <el-tag v-if="selectedMemoryHasTaskTree" effect="plain" type="success">
              已关联任务树
            </el-tag>
          </div>
        </div>
      </template>
      <template v-if="selectedMemoryDetail">
        <div class="memory-detail-shell">
          <section class="memory-detail-hero memory-detail-hero--story">
            <div class="memory-detail-hero__content">
              <div class="memory-detail-hero__eyebrow">Requirement Record</div>
              <h4>{{ selectedMemoryQuestionText || "未提取到结构化问题" }}</h4>
              <p>
                {{
                  selectedMemorySolutionText
                    || selectedMemoryConclusionText
                    || selectedMemoryProcessSummary
                    || "这条需求记录保留了本轮会话的核心内容和任务映射。"
                }}
              </p>
              <div class="memory-detail-hero__meta">
                <span class="memory-detail-hero__meta-item">
                  <span>执行人</span>
                  <strong>{{ selectedMemoryDetail.employee_name || selectedMemoryDetail.employee_id || "-" }}</strong>
                </span>
                <span class="memory-detail-hero__meta-item">
                  <span>记录类型</span>
                  <strong>{{ getMemoryTypeLabel(selectedMemoryDetail.type) }}</strong>
                </span>
                <span class="memory-detail-hero__meta-item">
                  <span>任务树</span>
                  <strong>{{ selectedMemoryTaskSessionLabel }}</strong>
                </span>
                <span class="memory-detail-hero__meta-item">
                  <span>记录时间</span>
                  <strong>{{ formatDateTime(selectedMemoryDetail.created_at) }}</strong>
                </span>
              </div>
              <div
                v-if="selectedMemoryDetail.purpose_tags?.length"
                class="memory-detail-hero__tags"
              >
                <el-tag
                  v-for="tag in selectedMemoryDetail.purpose_tags"
                  :key="`${selectedMemoryDetail.id}-${tag}`"
                  size="small"
                  effect="plain"
                >
                  {{ tag }}
                </el-tag>
              </div>
            </div>
            <div class="memory-detail-hero__status">
              <div class="memory-detail-status-card">
                <span>解决状态</span>
                <strong>{{ getMemorySolveStatusLabel(selectedMemoryDetail.solve_status) }}</strong>
              </div>
              <div class="memory-detail-status-card">
                <span>任务树绑定</span>
                <strong>{{ selectedMemoryTaskSessionLabel }}</strong>
              </div>
              <div class="memory-detail-status-card">
                <span>进展记录</span>
                <strong>{{ Number(memoryDetailWorkEvents.length || 0) }}</strong>
              </div>
            </div>
          </section>

          <section class="memory-detail-task-tree">
            <div class="memory-detail-section__header">
              <div>
                <div class="memory-detail-section__eyebrow">Plan Nodes First</div>
                <h4>执行谱系</h4>
              </div>
              <div v-if="memoryDetailTaskTree" class="memory-detail-task-tree__summary-tag">
                <el-tag effect="plain" :type="getTaskSessionStatusTagType(memoryDetailTaskTree.status)">
                  {{ memoryDetailTaskTree.is_archived ? "已归档完成" : memoryDetailTaskTree.status || "进行中" }}
                </el-tag>
              </div>
            </div>
            <div v-loading="memoryDetailTaskTreeLoading">
              <template v-if="memoryDetailTaskTree">
                <div class="memory-detail-task-tree__hero">
                  <div class="memory-detail-task-tree__goal">
                    <span>主链目标</span>
                    <strong>{{ memoryDetailTaskTree.root_goal || "-" }}</strong>
                    <p>{{ selectedMemoryProcessSummary || "当前按任务树节点逐项推进。" }}</p>
                  </div>
                  <div class="memory-detail-task-tree__stats">
                    <div class="memory-detail-task-tree__stat">
                      <span>进度</span>
                      <strong>{{ resolveTaskTreeProgressPercent(memoryDetailTaskTree) }}%</strong>
                    </div>
                    <div class="memory-detail-task-tree__stat">
                      <span>节点完成</span>
                      <strong>
                        {{ Number(memoryDetailTaskTree.done_leaf_total || 0) }}/{{ Number(memoryDetailTaskTree.leaf_total || 0) }}
                      </strong>
                    </div>
                    <div class="memory-detail-task-tree__stat">
                      <span>当前焦点</span>
                      <strong>{{ memoryDetailTaskTree.current_node?.title || "-" }}</strong>
                    </div>
                    <div class="memory-detail-task-tree__stat">
                      <span>轨迹</span>
                      <strong>{{ Number(memoryDetailWorkEvents.length || 0) }}</strong>
                    </div>
                  </div>
                </div>
                <div class="memory-detail-plan">
                  <div
                    v-for="(node, index) in memoryDetailTaskNodes"
                    :key="node.id"
                    class="memory-detail-plan__item"
                  >
                    <div class="memory-detail-plan__row">
                      <div class="memory-detail-plan__title-group">
                        <span class="memory-detail-plan__index">{{
                          formatTaskTreeStepIndex(node, index)
                        }}</span>
                        <strong>{{ node.title }}</strong>
                      </div>
                      <el-tag
                        size="small"
                        effect="plain"
                        :type="getTaskSessionStatusTagType(node.status)"
                      >
                        {{ node.status }}
                      </el-tag>
                    </div>
                    <div v-if="node.objective || node.description" class="memory-detail-plan__desc">
                      {{ node.objective || node.description }}
                    </div>
                    <div class="memory-detail-plan__summary">
                      <span>{{ getMemoryDetailNodeWorkEvents(node).length }} 条轨迹</span>
                      <span>
                        {{
                          node.verification_result
                            ? "已写验证结果"
                            : node.latest_outcome
                              ? "已有阶段结果"
                              : "等待结果"
                        }}
                      </span>
                    </div>
                    <div
                      v-if="node.verification_result || node.latest_outcome"
                      class="memory-detail-plan__verification"
                    >
                      <span>{{ node.verification_result ? "验证结果" : "当前结果" }}</span>
                      <p>{{ node.verification_result || node.latest_outcome }}</p>
                    </div>
                    <div
                      v-if="getMemoryDetailNodeWorkEvents(node).length"
                      class="memory-detail-plan__events"
                    >
                      <div class="memory-detail-plan__events-head">
                        <span>关联轨迹</span>
                        <strong>{{ getMemoryDetailNodeWorkEvents(node).length }} 条</strong>
                      </div>
                      <div
                        v-for="event in getMemoryDetailNodeWorkEvents(node)"
                        :key="event.id || `${node.id}-${event.session_id}-${event.created_at}`"
                        class="memory-detail-plan__event"
                      >
                        <div class="memory-detail-plan__event-row">
                          <div class="memory-detail-plan__event-title">
                            {{ event.phase || event.event_type || "工作轨迹" }}
                            <template v-if="event.step"> / {{ event.step }}</template>
                          </div>
                          <el-tag
                            size="small"
                            effect="plain"
                            :type="getWorkSessionStatusTagType(event.status)"
                          >
                            {{ event.status || event.event_type || "-" }}
                          </el-tag>
                        </div>
                        <p>{{ summarizeProjectWorkEvent(event) }}</p>
                        <div class="memory-detail-plan__event-meta">
                          {{ event.session_id || "-" }} · {{ event.employee_name || "-" }} ·
                          {{ formatDateTime(event.created_at) }}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div
                  v-if="memoryDetailWorkEventsLoading || memoryDetailUnassignedWorkEvents.length"
                  class="memory-detail-task-events"
                  v-loading="memoryDetailWorkEventsLoading"
                >
                  <div class="memory-detail-task-events__head">
                    <div>
                      <div class="memory-detail-section__eyebrow">Execution Trace</div>
                      <h4>未归属到具体节点的轨迹</h4>
                    </div>
                    <el-tag
                      v-if="memoryDetailUnassignedWorkEvents.length"
                      size="small"
                      effect="plain"
                      type="info"
                    >
                      {{ memoryDetailUnassignedWorkEvents.length }} 条
                    </el-tag>
                  </div>
                  <div
                    v-for="event in memoryDetailUnassignedWorkEvents"
                    :key="event.id || `${event.session_id}-${event.created_at}`"
                    class="memory-detail-plan__event"
                  >
                    <div class="memory-detail-plan__event-row">
                      <div class="memory-detail-plan__event-title">
                        {{ event.phase || event.event_type || "工作轨迹" }}
                        <template v-if="event.step"> / {{ event.step }}</template>
                      </div>
                      <el-tag
                        size="small"
                        effect="plain"
                        :type="getWorkSessionStatusTagType(event.status)"
                      >
                        {{ event.status || event.event_type || "-" }}
                      </el-tag>
                    </div>
                    <p>{{ summarizeProjectWorkEvent(event) }}</p>
                    <div class="memory-detail-plan__event-meta">
                      {{ event.session_id || "-" }} · {{ event.employee_name || "-" }} ·
                      {{ formatDateTime(event.created_at) }}
                    </div>
                  </div>
                </div>
              </template>
              <template v-else-if="memoryDetailWorkEventsLoading || memoryDetailWorkEvents.length">
                <div class="memory-detail-task-events" v-loading="memoryDetailWorkEventsLoading">
                  <div class="memory-detail-task-events__head">
                    <div>
                      <div class="memory-detail-section__eyebrow">Execution Trace</div>
                      <h4>关联工作轨迹</h4>
                    </div>
                    <el-tag
                      v-if="memoryDetailWorkEvents.length"
                      size="small"
                      effect="plain"
                      type="info"
                    >
                      {{ memoryDetailWorkEvents.length }} 条
                    </el-tag>
                  </div>
                  <div
                    v-for="event in memoryDetailWorkEvents"
                    :key="event.id || `${event.session_id}-${event.created_at}`"
                    class="memory-detail-plan__event"
                  >
                    <div class="memory-detail-plan__event-row">
                      <div class="memory-detail-plan__event-title">
                        {{ event.phase || event.event_type || "工作轨迹" }}
                        <template v-if="event.step"> / {{ event.step }}</template>
                      </div>
                      <el-tag
                        size="small"
                        effect="plain"
                        :type="getWorkSessionStatusTagType(event.status)"
                      >
                        {{ event.status || event.event_type || "-" }}
                      </el-tag>
                    </div>
                    <p>{{ summarizeProjectWorkEvent(event) }}</p>
                    <div class="memory-detail-plan__event-meta">
                      {{ event.session_id || "-" }} · {{ event.employee_name || "-" }} ·
                      {{ formatDateTime(event.created_at) }}
                    </div>
                  </div>
                </div>
              </template>
              <el-empty
                v-else
                description="这条需求记录没有关联到可读取的任务树"
                :image-size="64"
              />
            </div>
          </section>

          <section class="memory-detail-content-stack">
            <article class="memory-detail-section">
              <div class="memory-detail-section__header">
                <div>
                  <div class="memory-detail-section__eyebrow">Process</div>
                  <h4>过程脉络</h4>
                </div>
              </div>
              <div class="memory-detail-block">
                {{ selectedMemoryProcessSummary || "-" }}
              </div>
            </article>

            <article class="memory-detail-section">
              <div class="memory-detail-section__header">
                <div>
                  <div class="memory-detail-section__eyebrow">Approach</div>
                  <h4>解决方案</h4>
                </div>
              </div>
              <div class="memory-detail-block">
                {{ selectedMemorySolutionText || "-" }}
              </div>
            </article>

            <article class="memory-detail-section">
              <div class="memory-detail-section__header">
                <div>
                  <div class="memory-detail-section__eyebrow">Outcome</div>
                  <h4>最终结论</h4>
                </div>
              </div>
              <div class="memory-detail-block">
                {{ selectedMemoryConclusionText || "-" }}
              </div>
            </article>

            <article
              v-if="selectedMemoryRawContentText"
              class="memory-detail-section"
            >
              <div class="memory-detail-section__header">
                <div>
                  <div class="memory-detail-section__eyebrow">Source</div>
                  <h4>原始内容</h4>
                </div>
              </div>
              <div class="memory-detail-block">
                {{ selectedMemoryRawContentText }}
              </div>
            </article>
          </section>
        </div>
      </template>
      <template #footer>
        <el-button @click="showMemoryDetailDialog = false">关闭</el-button>
        <el-button
          plain
          :disabled="!(selectedMemoryDetail?.linked_work_session?.session_id || selectedMemoryDetail?.execution_session_id)"
          @click="openMemoryLinkedWorkSession()"
        >
          查看轨迹
        </el-button>
        <el-button
          type="primary"
          :disabled="!canOpenProjectChat || !(selectedMemoryDetail?.chat_session_id)"
          @click="openProjectChat(selectedMemoryDetail?.chat_session_id || '')"
        >
          打开会话
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showWorkSessionDetailDialog"
      class="memory-detail-dialog"
      width="960px"
      top="6vh"
    >
      <template #header>
        <div class="memory-detail-dialog__header">
          <div>
            <div class="memory-detail-dialog__eyebrow">Execution Trace</div>
            <h3>工作轨迹详情</h3>
          </div>
          <div class="memory-detail-dialog__header-tags">
            <el-tag
              v-if="selectedWorkSession"
              effect="plain"
              :type="getWorkSessionStatusTagType(selectedWorkSession.latest_status)"
            >
              {{ selectedWorkSession?.latest_status || "-" }}
            </el-tag>
          </div>
        </div>
      </template>
      <div v-loading="workSessionDetailLoading">
        <template v-if="selectedWorkSession">
          <WorkSessionDetailPanel
            :session="selectedWorkSession"
            :events="selectedWorkSessionEvents"
          />
        </template>
        <el-empty v-else description="未加载到工作轨迹详情" :image-size="60" />
      </div>
      <template #footer>
        <el-button @click="showWorkSessionDetailDialog = false">关闭</el-button>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { marked } from "marked";
import ModelProviderPickerDialog from "@/components/ModelProviderPickerDialog.vue";
import RequirementTreeNode from "@/components/RequirementTreeNode.vue";
import WorkSessionDetailPanel from "@/components/WorkSessionDetailPanel.vue";
import { normalizeTaskTreeHealth } from "@/modules/task-tree-feedback/taskTreeFeedback";
import api from "@/utils/api.js";
import { formatDateTime } from "@/utils/date.js";
import {
  pickWorkspaceDirectory as openWorkspaceDirectoryPicker,
  pickWorkspaceFile as openWorkspaceFilePicker,
  toWorkspaceRelativePath,
} from "@/utils/workspace-picker.js";
import { hasPermission } from "@/utils/permissions.js";
import { buildRuntimeUrl, fetchConfiguredRuntimeOrigin } from "@/utils/runtime-url.js";

const route = useRoute();
const router = useRouter();
const projectId = computed(() => String(route.params.id || "").trim());
const showProjectLocationFields = false;
const showProjectAddressFields = false;
const activeProjectTab = ref("overview");
const runtimeOrigin = ref("");
const projectTypeOptions = [
  {
    value: "image",
    label: "图片项目",
    description: "适合海报、KV、插画、商品图等以图片产出为主的项目。",
  },
  {
    value: "storyboard_video",
    label: "分镜视频项目",
    description: "适合镜头脚本、分镜规划、视频生成等以视频产出为主的项目。",
  },
  {
    value: "mixed",
    label: "综合项目",
    description: "适合图文混合或方向未定的项目，默认工作流更中性。",
  },
];

const loading = ref(false);
const saving = ref(false);
const showAddDialog = ref(false);
const showAddUserDialog = ref(false);
const showUiRuleDialog = ref(false);
const showEditDialog = ref(false);
const showManualDialog = ref(false);
const showExperienceSummaryDialog = ref(false);
const showExperienceRuleEditDialog = ref(false);
const manualDialogTitle = ref("项目手册");
const manualLoading = ref(false);
const generatedManual = ref("");
const experienceProvidersLoading = ref(false);
const experienceSummaryLoading = ref(false);
const experienceRuleMigrating = ref(false);
const experienceRuleConsolidating = ref(false);
const experienceRuleEditingLoading = ref(false);
const experienceRuleDeletingLoading = ref(false);
const experienceRuleEditSaving = ref(false);
const experienceProviderOptions = ref([]);
const experienceSummaryProviderId = ref("");
const experienceSummaryModelName = ref("");
const editingExperienceRuleId = ref("");
const deletingExperienceRuleId = ref("");
const experienceRuleEditForm = ref({
  title: "",
  content: "",
});
const memoryLoading = ref(false);
const workSessionLoading = ref(false);
const uiRuleSaving = ref(false);
const taskSessionsLoading = ref(false);

const project = ref({});
const projectUsers = ref([]);
const members = ref([]);
const employeeOptions = ref([]);
const userOptions = ref([]);
const ruleOptions = ref([]);
const projectMemories = ref([]);
const projectMemoryTotal = ref(0);
const projectMemoryHasMore = ref(false);
const projectWorkSessions = ref([]);
const projectRequirementRecords = ref([]);
const projectTaskSessions = ref([]);
const projectTaskTreeDetails = ref({});
const selectedMemoryDetail = ref(null);
const selectedWorkSession = ref(null);
const selectedWorkSessionEvents = ref([]);
const selectedRequirementNode = ref(null);
const selectedRequirementNodeRound = ref(null);
const selectedRequirementNodeEvents = ref([]);
const selectedRequirementRecordIds = ref([]);
const expandedRequirementRecordId = ref("");
const memoryDetailWorkEvents = ref([]);
const taskTreeStorageBackend = ref("");
const memoryDetailTaskTree = ref(null);
const memoryDetailTaskTreeLoading = ref(false);
const memoryDetailWorkEventsLoading = ref(false);
const taskTreeDetailsLoading = ref(false);
const requirementNodeDetailLoading = ref(false);
const requirementRoundTaskTreeLoadingMap = ref({});
const workSessionDetailLoading = ref(false);
const requirementRecordDeleting = ref(false);
const requirementRecordTaskTreeClearingMap = ref({});
const requirementRecordTaskTreeRegeneratingMap = ref({});
const requirementRecordsLoaded = ref(false);
const projectUsersPage = ref(1);
const projectUsersPageSize = ref(10);
const membersPage = ref(1);
const membersPageSize = ref(10);
const requirementRecordsPage = ref(1);
const requirementRecordsPageSize = ref(10);
const showMemoryDetailDialog = ref(false);
const showWorkSessionDetailDialog = ref(false);
const showRequirementNodeDetailDialog = ref(false);
const canManageProjectUsers = ref(false);
const tabDataLoaded = ref({
  overview: false,
  access: false,
  memory: false,
});
const tabDataPromises = {
  overview: null,
  access: null,
  memory: null,
};
const memoryLimitOptions = [20, 50, 100];
const PROJECT_TASK_SESSION_FETCH_LIMIT = 300;
const MEMORY_TYPE_LABELS = {
  "project-context": "项目上下文",
  "user-preference": "用户偏好",
  "key-event": "关键事件",
  "learned-pattern": "学习模式",
  "long-term-goal": "长期目标",
  taboo: "禁忌项",
  "stable-preference": "稳定偏好",
  "decision-pattern": "决策模式",
};
const INTERNAL_AUTO_QUERY_RESULT_TOOL_TAGS = new Set([
  "mcp:tools/call:search_ids",
  "mcp:tools/call:list_recent_project_requirements",
  "mcp:tools/call:get_requirement_history",
]);
const memoryFilters = ref({
  query: "",
  employeeId: "",
  type: "",
  limit: 20,
});

const addForm = ref({
  employee_ids: [],
  role: "member",
  enabled: true,
});

const userForm = ref({
  usernames: [],
  role: "member",
  enabled: true,
});

const editForm = ref({
  name: "",
  description: "",
  type: "mixed",
  mcp_instruction: "",
  workspace_path: "",
  ai_entry_file: "",
  mcp_enabled: true,
  feedback_upgrade_enabled: true,
});

const uiRuleForm = ref({
  rule_ids: [],
});

function resetProjectScopedState() {
  project.value = {};
  projectUsers.value = [];
  members.value = [];
  projectMemories.value = [];
  projectMemoryTotal.value = 0;
  projectMemoryHasMore.value = false;
  projectWorkSessions.value = [];
  projectRequirementRecords.value = [];
  projectTaskSessions.value = [];
  projectTaskTreeDetails.value = {};
  selectedRequirementRecordIds.value = [];
  expandedRequirementRecordId.value = "";
  requirementRoundTaskTreeLoadingMap.value = {};
  requirementRecordTaskTreeClearingMap.value = {};
  requirementRecordTaskTreeRegeneratingMap.value = {};
  requirementRecordsLoaded.value = false;
  tabDataLoaded.value = {
    overview: false,
    access: false,
    memory: false,
  };
  tabDataPromises.overview = null;
  tabDataPromises.access = null;
  tabDataPromises.memory = null;
}

const memberIdSet = computed(() => {
  return new Set(
    (members.value || [])
      .map((item) => String(item.employee_id || "").trim())
      .filter(Boolean),
  );
});

const projectUserSet = computed(() => {
  return new Set(
    (projectUsers.value || [])
      .map((item) => String(item.username || "").trim())
      .filter(Boolean),
  );
});

const availableEmployeeOptions = computed(() => {
  const currentMembers = memberIdSet.value;
  return (employeeOptions.value || []).filter((item) => {
    const employeeId = String(item.id || "").trim();
    return employeeId && !currentMembers.has(employeeId);
  });
});

const availableUserOptions = computed(() => {
  const currentUsers = projectUserSet.value;
  return (userOptions.value || []).filter((item) => {
    const username = String(item.username || "").trim();
    return username && !currentUsers.has(username);
  });
});

const canOpenProjectChat = computed(() => hasPermission("button.project.chat"));
const canManageProject = computed(() => !!project.value?.can_manage);
const ruleMap = computed(
  () => new Map((ruleOptions.value || []).map((item) => [item.id, item])),
);
const projectMcpSseUrl = computed(() => {
  if (!project.value?.id) return "";
  return buildRuntimeUrl(
    `/mcp/projects/${project.value.id}/sse?key=YOUR_API_KEY`,
    runtimeOrigin.value,
  );
});

function manageBlockedMessage() {
  const creator = String(project.value?.created_by || "").trim();
  if (creator) {
    return `仅项目创建者可编辑，当前创建者为 ${creator}`;
  }
  return "仅项目创建者可编辑";
}
const projectMcpHttpUrl = computed(() => {
  if (!project.value?.id) return "";
  return buildRuntimeUrl(
    `/mcp/projects/${project.value.id}/mcp?key=YOUR_API_KEY`,
    runtimeOrigin.value,
  );
});

async function fetchRuntimeOrigin() {
  runtimeOrigin.value = await fetchConfiguredRuntimeOrigin();
}

const taskTreeStorageBackendLabel = computed(() => {
  const normalized = String(taskTreeStorageBackend.value || "").trim().toLowerCase();
  if (normalized === "postgres") return "任务存储: Postgres";
  if (normalized) return `任务存储: ${normalized}`;
  return "任务存储: 未知";
});

const taskTreeStorageBackendTagType = computed(() => {
  return String(taskTreeStorageBackend.value || "").trim().toLowerCase() === "postgres"
    ? "success"
    : "warning";
});

const isMemoryTabActive = computed(() => activeProjectTab.value === "memory");

const projectHeroPanelTitle = computed(() =>
  isMemoryTabActive.value ? "先看记忆，再决定是否下钻。" : "先进入项目，再做管理。",
);

const projectHeroPanelDescription = computed(() =>
  isMemoryTabActive.value
    ? "当前视图改为先看需求链和计划树，工作轨迹退到轮次详情里，避免主界面继续混用旧的记忆/轨迹模型。"
    : "保留一个主操作，其余入口退到次级层，信息和动作不再挤在同一列里。",
);

const projectHeroDescription = computed(() => {
  const description = String(project.value?.description || "").trim();
  if (description) return description;
  return `${getProjectTypeDescription(project.value?.type)} 当前页面用于整理成员、规则、需求记录与 MCP 配置。`;
});

const projectHeroSignals = computed(() => [
  {
    key: "type",
    label: getProjectTypeLabel(project.value?.type),
    type: getProjectTypeTagType(project.value?.type) || "info",
  },
  {
    key: "mcp",
    label: project.value?.mcp_enabled ? "MCP 已开启" : "MCP 未开启",
    type: project.value?.mcp_enabled ? "success" : "info",
  },
  {
    key: "feedback",
    label: project.value?.feedback_upgrade_enabled ? "反馈升级开启" : "反馈升级关闭",
    type: project.value?.feedback_upgrade_enabled ? "success" : "info",
  },
]);

const projectMemberCount = computed(() => {
  if (tabDataLoaded.value.access || members.value.length) {
    return members.value.length;
  }
  return Math.max(
    0,
    Number(project.value?.active_member_count ?? project.value?.member_count ?? 0),
  );
});

const projectUserCount = computed(() => {
  if (tabDataLoaded.value.access || projectUsers.value.length) {
    return projectUsers.value.length;
  }
  return Math.max(0, Number(project.value?.active_user_count ?? project.value?.user_count ?? 0));
});

function resolveDeferredCountLabel(value, unit, loaded, loadingState) {
  if (loaded) {
    return `${Math.max(0, Number(value || 0))} ${unit}`;
  }
  return loadingState ? "加载中" : "待加载";
}

const visibleProjectMemories = computed(() => {
  const grouped = new Map();
  for (const memory of projectMemories.value || []) {
    const sections = parseMemorySections(memory.content || "");
    if (
      isInternalAutoQuestionSnapshot(memory) ||
      isInternalAutoQueryResultSnapshot(memory) ||
      isTransientQuestionSnapshot(memory, sections) ||
      isTrajectoryMemory(memory)
    ) {
      continue;
    }
    const groupKey = getProjectMemoryGroupKey(memory, sections);
    const currentItems = grouped.get(groupKey) || [];
    currentItems.push(memory);
    grouped.set(groupKey, currentItems);
  }
  return Array.from(grouped.values())
    .map((items) => pickPrimaryProjectMemory(items))
    .filter(Boolean)
    .sort((a, b) => String(b?.created_at || "").localeCompare(String(a?.created_at || "")));
});

const projectHeroStats = computed(() => [
  {
    label: "成员",
    value: `${projectMemberCount.value} 名`,
  },
  {
    label: "UI 规则",
    value: `${boundUiRules.value.length} 条`,
  },
  {
    label: "需求记录",
    value: resolveDeferredCountLabel(
      requirementRecords.value.length,
      "条",
      tabDataLoaded.value.memory,
      memoryLoading.value || taskSessionsLoading.value || workSessionLoading.value,
    ),
  },
  {
    label: "工作轨迹",
    value: resolveDeferredCountLabel(
      projectWorkSessions.value.length,
      "条",
      tabDataLoaded.value.memory,
      workSessionLoading.value,
    ),
  },
]);

const accessTabMeta = computed(() => `${projectUserCount.value} 用户 · ${projectMemberCount.value} 成员`);

const availableProjectDetailTabs = computed(() => {
  const tabs = ["overview", "access", "memory"];
  if (showProjectAddressFields) {
    tabs.push("mcp");
  }
  return tabs;
});

const renderedManualHtml = computed(() => {
  if (!generatedManual.value) return "";
  try {
    return marked.parse(generatedManual.value);
  } catch {
    return generatedManual.value.replace(/\n/g, "<br>");
  }
});

const memberNameMap = computed(() => {
  const result = new Map();
  (members.value || []).forEach((item) => {
    const id = String(item.employee_id || "").trim();
    if (!id) return;
    result.set(id, String(item.employee_name || "").trim());
  });
  return result;
});

const memoryTypeOptions = computed(() => {
  const rawTypes = Array.from(
    new Set(
      (visibleProjectMemories.value || [])
        .map((item) => String(item.type || "").trim())
        .filter(Boolean),
    ),
  );
  return rawTypes.map((type) => ({
    value: type,
    label: MEMORY_TYPE_LABELS[type] || type,
  }));
});

const filteredMemoryRows = computed(() => {
  const selectedType = String(memoryFilters.value.type || "").trim();
  if (!selectedType) return enrichedProjectMemories.value || [];
  return (enrichedProjectMemories.value || []).filter(
    (item) => String(item.type || "").trim() === selectedType,
  );
});

const visibleRequirementRecordIds = computed(() =>
  (requirementRecords.value || [])
    .map((item) => String(item?.id || "").trim())
    .filter(Boolean),
);

const selectedRequirementRecordIdSet = computed(() => new Set(selectedRequirementRecordIds.value || []));

const selectedRequirementRecordCount = computed(() =>
  visibleRequirementRecordIds.value.filter((item) => selectedRequirementRecordIdSet.value.has(item)).length,
);

const allRequirementRecordsSelected = computed(() =>
  visibleRequirementRecordIds.value.length > 0
  && visibleRequirementRecordIds.value.every((item) => selectedRequirementRecordIdSet.value.has(item)),
);

const derivedRequirementRecords = computed(() => {
  const detailMap = projectTaskTreeDetails.value || {};
  const grouped = new Map();

  for (const summary of projectTaskSessions.value || []) {
    const sessionId = String(summary?.id || "").trim();
    if (!sessionId) continue;
    const taskTreeSummary = normalizeTaskTreePayload(summary);
    const taskTree = detailMap[sessionId] && typeof detailMap[sessionId] === "object"
      ? detailMap[sessionId]
      : taskTreeSummary;
    const sourceSessionId = String(taskTree?.source_session_id || summary?.source_session_id || "").trim();
    const chatSessionId = String(
      taskTree?.source_chat_session_id
      || taskTree?.chat_session_id
      || summary?.source_chat_session_id
      || summary?.chat_session_id
      || "",
    ).trim();
    const memoryMatches = (filteredMemoryRows.value || []).filter((item) => {
      const memoryTaskSessionId = String(item?.task_session_id || item?.task_tree_session_id || "").trim();
      const memoryChatSessionId = String(item?.task_tree_chat_session_id || item?.chat_session_id || "").trim();
      return (
        (memoryTaskSessionId && memoryTaskSessionId === sessionId)
        || (chatSessionId && memoryChatSessionId === chatSessionId)
      );
    });
    const workSessions = (projectWorkSessions.value || [])
      .filter((item) => {
        const primaryTaskSessionId = String(item?.task_tree_session_id || "").trim();
        const taskSessionIds = Array.isArray(item?.task_tree_session_ids)
          ? item.task_tree_session_ids
          : [];
        const workChatSessionId = String(item?.task_tree_chat_session_id || "").trim();
        return (
          (primaryTaskSessionId && primaryTaskSessionId === sessionId)
          || taskSessionIds.includes(sessionId)
          || (chatSessionId && workChatSessionId === chatSessionId)
        );
      })
      .slice()
      .sort(compareTaskSessionByCreatedAtDesc);
    const primaryMemory = memoryMatches
      .slice()
      .sort((left, right) => String(right?.created_at || "").localeCompare(String(left?.created_at || "")))[0]
      || null;
    const round = {
      id: sessionId,
      sessionId,
      sourceSessionId,
      chatSessionId,
      taskTree,
      rootNode: taskTree?.tree?.[0] || null,
      rootGoal: String(taskTree?.root_goal || summary?.root_goal || summary?.title || "").trim(),
      title: String(taskTree?.title || summary?.title || "").trim(),
      recordKind: String(taskTree?.record_kind || summary?.record_kind || "requirement").trim() || "requirement",
      roundIndex: Math.max(1, Number(taskTree?.round_index || summary?.round_index || 1)),
      status: String(taskTree?.status || summary?.status || "pending").trim(),
      progressPercent: Number(resolveTaskTreeProgressPercent(taskTree || summary)),
      currentNodeId: String(taskTree?.current_node_id || summary?.current_node_id || "").trim(),
      currentNodeTitle: String(
        taskTree?.current_node?.title || summary?.current_node?.title || summary?.current_node_title || "",
      ).trim(),
      leafTotal: Number(taskTree?.leaf_total ?? taskTree?.stats?.leaf_total ?? summary?.leaf_total ?? 0),
      doneLeafTotal: Number(
        taskTree?.done_leaf_total ?? taskTree?.stats?.done_leaf_total ?? summary?.done_leaf_total ?? 0,
      ),
      nodeTotal: Number(taskTree?.node_total ?? taskTree?.stats?.node_total ?? summary?.node_total ?? 0),
      isArchived: Boolean(taskTree?.is_archived || summary?.is_archived),
      createdAt: String(taskTree?.created_at || summary?.created_at || "").trim(),
      updatedAt: String(taskTree?.updated_at || summary?.updated_at || "").trim(),
      primaryMemory,
      workSessions,
      primaryWorkSession: workSessions[0] || null,
      isFinalized: isTaskTreeFinalized(taskTree || summary),
    };
    round.displayStatus = resolveRequirementRoundDisplayStatus(round);
    const summaryText = round.isFinalized
      ? (
        primaryMemory?.conclusion_preview
        || primaryMemory?.solution_preview
        || String(taskTree?.current_node?.latest_outcome || "").trim()
        || "全部计划节点已完成并写入验证结果。"
      )
      : (
        primaryMemory?.solution_preview
        || primaryMemory?.display_preview
        || round.currentNodeTitle
        || "计划已入树，当前按节点推进并逐项验证。"
      );
    round.summaryText = String(summaryText || "").trim();
    const chainKey = sourceSessionId || sessionId;
    const currentItems = grouped.get(chainKey) || [];
    currentItems.push(round);
    grouped.set(chainKey, currentItems);
  }

  const query = String(memoryFilters.value.query || "").trim().toLowerCase();
  const selectedEmployeeId = String(memoryFilters.value.employeeId || "").trim();
  const selectedType = String(memoryFilters.value.type || "").trim();

  return Array.from(grouped.entries())
    .map(([chainId, rounds]) => {
      const sortedRounds = rounds.slice().sort((left, right) => {
        if (left.roundIndex !== right.roundIndex) {
          return left.roundIndex - right.roundIndex;
        }
        return String(left.createdAt || "").localeCompare(String(right.createdAt || ""));
      });
      const latestRound = sortedRounds[sortedRounds.length - 1] || null;
      let currentRound = latestRound;
      for (let index = sortedRounds.length - 1; index >= 0; index -= 1) {
        if (!sortedRounds[index].isFinalized) {
          currentRound = sortedRounds[index];
          break;
        }
      }
      if (isRequirementRoundPlaceholder(currentRound)) {
        const activeRoundWithProgress = sortedRounds
          .slice()
          .reverse()
          .find((item) => !item.isFinalized && !isRequirementRoundPlaceholder(item));
        const finalizedRound = sortedRounds
          .slice()
          .reverse()
          .find((item) => item.isFinalized);
        currentRound = activeRoundWithProgress || finalizedRound || currentRound;
      }
      const actorNames = Array.from(
        new Set(
          sortedRounds.flatMap((item) => [
            String(item.primaryMemory?.employee_name || item.primaryMemory?.employee_id || "").trim(),
            ...item.workSessions.map((entry) => String(entry.employee_name || entry.employee_id || "").trim()),
          ]),
        ),
      ).filter(Boolean);
      const memoryTypes = Array.from(
        new Set(
          sortedRounds
            .map((item) => String(item.primaryMemory?.type || "").trim())
            .filter(Boolean),
        ),
      );
      return {
        id: chainId,
        rootGoal: currentRound?.rootGoal || latestRound?.rootGoal || "",
        actorNames,
        actorLabel: actorNames.length ? actorNames.join(" / ") : "未绑定执行人",
        latestRound,
        currentRound,
        detailRound: currentRound || latestRound || null,
        rounds: sortedRounds,
        repairRoundCount: sortedRounds.filter((item) => item.recordKind === "repair").length,
        activeRoundCount: sortedRounds.filter(
          (item) => !item.isFinalized && !isRequirementRoundPlaceholder(item),
        ).length,
        memoryTypes,
        status: String(currentRound?.displayStatus || latestRound?.displayStatus || "pending").trim(),
        statusLabel: getTaskSessionStatusLabel(currentRound?.displayStatus || latestRound?.displayStatus),
        statusTagType: getTaskSessionStatusTagType(currentRound?.displayStatus || latestRound?.displayStatus),
        progressPercent: Number(currentRound?.progressPercent || latestRound?.progressPercent || 0),
        currentFocus: currentRound?.currentNodeTitle || latestRound?.currentNodeTitle || "等待进入计划节点",
        completionGate: currentRound?.isFinalized
          ? "全部计划节点已完成并通过验证，本轮可视为结束。"
          : "只有所有计划节点完成并写入验证结果，需求才算真正结束。",
        summaryText: currentRound?.summaryText || latestRound?.summaryText || "",
        roundDigest: sortedRounds.length > 1
          ? `${(currentRound || latestRound)?.isFinalized ? "最近" : "当前"}第 ${
            Math.max(1, Number((currentRound || latestRound)?.roundIndex || sortedRounds.length || 1))
          } 轮，共 ${sortedRounds.length} 轮`
          : "单轮处理",
        progressDigest: `${
          Math.max(0, Number((currentRound || latestRound)?.doneLeafTotal || 0))
        }/${
          Math.max(
            0,
            Number(
              (currentRound || latestRound)?.leafTotal
              || (currentRound || latestRound)?.nodeTotal
              || 0,
            ),
          )
        } 已完成`,
        detailWorkSessionCount: Number((currentRound || latestRound)?.workSessions?.length || 0),
        updatedAt: String(currentRound?.updatedAt || latestRound?.updatedAt || "").trim(),
        createdAt: String(sortedRounds[0]?.createdAt || "").trim(),
      };
    })
    .filter((record) => {
      if (selectedType && !record.memoryTypes.includes(selectedType)) {
        return false;
      }
      if (selectedEmployeeId) {
        const hasEmployee = record.rounds.some((round) => {
          if (String(round.primaryMemory?.employee_id || "").trim() === selectedEmployeeId) {
            return true;
          }
          return round.workSessions.some(
            (entry) => String(entry.employee_id || "").trim() === selectedEmployeeId,
          );
        });
        if (!hasEmployee) {
          return false;
        }
      }
      if (!query) {
        return true;
      }
      const searchValues = [
        record.rootGoal,
        record.summaryText,
        record.currentFocus,
        record.actorLabel,
        ...record.rounds.flatMap((round) => [
          round.rootGoal,
          round.title,
          round.currentNodeTitle,
          round.summaryText,
          String(round.primaryMemory?.content || "").trim(),
          ...round.workSessions.flatMap((entry) => [
            String(entry.goal || "").trim(),
            ...entry.steps,
            ...entry.verification,
            ...entry.next_steps,
          ]),
        ]),
      ]
        .map((item) => String(item || "").trim().toLowerCase())
        .filter(Boolean);
      return searchValues.some((item) => item.includes(query));
    })
    .sort((left, right) => {
      const leftUpdatedAt = parseComparableTimestamp(left.updatedAt || left.createdAt);
      const rightUpdatedAt = parseComparableTimestamp(right.updatedAt || right.createdAt);
      if (Number.isFinite(leftUpdatedAt) || Number.isFinite(rightUpdatedAt)) {
        if (!Number.isFinite(leftUpdatedAt)) return 1;
        if (!Number.isFinite(rightUpdatedAt)) return -1;
        if (leftUpdatedAt !== rightUpdatedAt) {
          return rightUpdatedAt - leftUpdatedAt;
        }
      }
      return String(right.id || "").localeCompare(String(left.id || ""));
    });
});

function hydrateRequirementRound(round) {
  if (!round || typeof round !== "object") {
    return null;
  }
  const sessionId = String(round.sessionId || round.id || "").trim();
  const detailTaskTree = sessionId && projectTaskTreeDetails.value?.[sessionId]
    ? normalizeTaskTreePayload(projectTaskTreeDetails.value[sessionId])
    : null;
  const fallbackTaskTree = round.taskTree && typeof round.taskTree === "object"
    ? normalizeTaskTreePayload(round.taskTree)
    : null;
  const taskTree = detailTaskTree || fallbackTaskTree || null;
  const workSessions = Array.isArray(round.workSessions)
    ? round.workSessions.map((item) => normalizeWorkSessionSummary(item))
    : [];
  const primaryWorkSessionSource = round.primaryWorkSession && typeof round.primaryWorkSession === "object"
    ? round.primaryWorkSession
    : workSessions[0] || null;
  const primaryWorkSession = primaryWorkSessionSource
    ? normalizeWorkSessionSummary(primaryWorkSessionSource)
    : null;
  const primaryMemory = round.primaryMemory && typeof round.primaryMemory === "object"
    ? {
        ...normalizeMemory(round.primaryMemory, round.primaryMemory.employee_id || ""),
        ...round.primaryMemory,
      }
    : null;
  const hydrated = {
    ...round,
    sessionId: sessionId || String(round.sessionId || round.id || "").trim(),
    id: String(round.id || sessionId || "").trim(),
    sourceSessionId: String(round.sourceSessionId || "").trim(),
    chatSessionId: String(
      round.chatSessionId
      || taskTree?.source_chat_session_id
      || taskTree?.chat_session_id
      || "",
    ).trim(),
    taskTree,
    rootNode: taskTree?.tree?.[0] || null,
    currentNodeId: String(round.currentNodeId || taskTree?.current_node_id || "").trim(),
    currentNodeTitle: String(
      round.currentNodeTitle
      || taskTree?.current_node?.title
      || "",
    ).trim(),
    primaryMemory,
    workSessions,
    primaryWorkSession,
    isFinalized: typeof round.isFinalized === "boolean"
      ? round.isFinalized
      : isTaskTreeFinalized(taskTree || round),
  };
  hydrated.displayStatus = String(
    round.displayStatus || resolveRequirementRoundDisplayStatus(hydrated),
  ).trim();
  return hydrated;
}

function hydrateRequirementRecord(record) {
  if (!record || typeof record !== "object") {
    return null;
  }
  const rounds = Array.isArray(record.rounds)
    ? record.rounds.map((item) => hydrateRequirementRound(item)).filter(Boolean)
    : [];
  const latestRoundId = String(record.latestRound?.sessionId || record.latestRound?.id || "").trim();
  const currentRoundId = String(record.currentRound?.sessionId || record.currentRound?.id || "").trim();
  const detailRoundId = String(record.detailRound?.sessionId || record.detailRound?.id || "").trim();
  const latestRound = rounds.find((item) => String(item?.sessionId || item?.id || "").trim() === latestRoundId)
    || rounds[rounds.length - 1]
    || null;
  const currentRound = rounds.find((item) => String(item?.sessionId || item?.id || "").trim() === currentRoundId)
    || latestRound;
  const detailRound = rounds.find((item) => String(item?.sessionId || item?.id || "").trim() === detailRoundId)
    || currentRound
    || latestRound
    || null;
  return {
    ...record,
    latestRound,
    currentRound,
    detailRound,
    rounds,
    updatedAt: String(record.updatedAt || currentRound?.updatedAt || latestRound?.updatedAt || "").trim(),
    createdAt: String(record.createdAt || rounds[0]?.createdAt || "").trim(),
  };
}

const requirementRecords = computed(() => {
  if (!requirementRecordsLoaded.value) {
    return [];
  }
  return (projectRequirementRecords.value || []).map((item) => hydrateRequirementRecord(item)).filter(Boolean);
});

const pagedRequirementRecords = computed(() => {
  const start = Math.max(0, (requirementRecordsPage.value - 1) * requirementRecordsPageSize.value);
  return requirementRecords.value.slice(start, start + requirementRecordsPageSize.value);
});

const requirementRecordTabMeta = computed(() =>
  tabDataLoaded.value.memory
    ? `${requirementRecords.value.length} 条记录`
    : (
      taskSessionsLoading.value
        ? "加载中"
        : "待加载"
    ),
);

const memoryWindowHint = computed(() => {
  if (!projectMemoryHasMore.value) {
    return "";
  }
  const limitValue = Number(memoryFilters.value.limit || 20);
  const safeLimit = Number.isFinite(limitValue) && limitValue > 0 ? limitValue : 20;
  const total = Math.max(projectMemoryTotal.value, safeLimit);
  return `当前只展示最近 ${safeLimit} 条命中的项目记忆，现有命中 ${total} 条。删除后若还有更早记录，会自动补位，所以当前结果数可能保持不变。`;
});

const memoryOverviewItems = computed(() => {
  const rounds = requirementRecords.value.flatMap((item) => item.rounds);
  const repairRounds = rounds.filter((item) => item.recordKind === "repair").length;
  const activeRounds = rounds.filter((item) => !item.isFinalized).length;
  const completedRecords = requirementRecords.value.filter(
    (item) => item.currentRound?.isFinalized,
  ).length;
  return [
    {
      label: "需求主链",
      value: `${requirementRecords.value.length} 条`,
      meta: "每条需求按轮次和任务树自上而下展开",
    },
    {
      label: "进行中轮次",
      value: `${activeRounds} 轮`,
      meta: activeRounds ? "仍有节点待完成或待验证" : "当前没有进行中轮次",
    },
    {
      label: "修复记录",
      value: `${repairRounds} 轮`,
      meta: repairRounds ? "问题回归后会继续挂到原需求链上" : "当前没有修复轮次",
    },
    {
      label: "已闭环",
      value: `${completedRecords} 条`,
      meta: completedRecords ? "已经完成全部节点并写入验证结果" : "当前还没有完整闭环的需求",
    },
  ];
});

const taskHealthEntries = computed(() =>
  requirementRecords.value
    .map((record) => {
      const round = record?.currentRound || record?.latestRound || null;
      if (!round) return null;
      const health = resolveRequirementRoundHealth(round);
      return {
        key: `${record.id}:${round.sessionId}:${health.state}`,
        record,
        round,
        health,
      };
    })
    .filter(Boolean),
);

const taskActionOverviewItems = computed(() => {
  const entries = taskHealthEntries.value;
  const pendingActionCount = entries.filter((item) =>
    ["needs_rebuild", "needs_verification", "needs_closure", "placeholder"].includes(item.health.state),
  ).length;
  const resumableCount = entries.filter((item) =>
    ["resumable", "active"].includes(item.health.state),
  ).length;
  const archivedCount = entries.filter((item) => item.health.state === "archived").length;
  return [
    {
      label: "待手动处理",
      value: `${pendingActionCount} 条`,
      meta: pendingActionCount ? "优先处理待验证、待收口、空挂和建议重建的需求。" : "当前没有必须手动修复的需求。",
      tone: pendingActionCount ? "danger" : "neutral",
    },
    {
      label: "可继续推进",
      value: `${resumableCount} 条`,
      meta: resumableCount ? "会话锚点和任务树都还在，可以直接进入对话继续处理。" : "当前没有可直接续跑的需求。",
      tone: resumableCount ? "info" : "neutral",
    },
    {
      label: "已归档",
      value: `${archivedCount} 条`,
      meta: archivedCount ? "任务树已完成闭环，可以直接回看历史。" : "当前还没有完成归档的任务链。",
      tone: archivedCount ? "success" : "neutral",
    },
  ];
});

const taskActionItems = computed(() =>
  taskHealthEntries.value
    .filter((item) => item.health.state !== "archived")
    .slice()
    .sort((left, right) => {
      if (left.health.priority !== right.health.priority) {
        return left.health.priority - right.health.priority;
      }
      return String(right.round.updatedAt || "").localeCompare(String(left.round.updatedAt || ""));
    })
    .slice(0, 6)
    .map((item) => ({
      key: item.key,
      record: item.record,
      round: item.round,
      tone: item.health.tone,
      tagType: item.health.tagType,
      label: item.health.label,
      eyebrow: item.record.roundDigest || "当前轮次",
      title: item.record.rootGoal || item.record.currentFocus || "未命名任务链",
      summary: item.health.summary,
      progress: item.record.progressDigest || "暂无节点进度",
      focus: item.record.currentFocus || "等待进入计划节点",
      canContinue: Boolean(String(item.round.chatSessionId || "").trim()),
      canClearTaskTree: canClearRequirementRecordTaskTree(item.record),
      canRebuildTaskTree: canRegenerateRequirementRecordTaskTree(item.record),
    })),
);

watch(
  requirementRecords,
  (records) => {
    const visibleIds = new Set(
      (records || [])
        .map((item) => String(item?.id || "").trim())
        .filter(Boolean),
    );
    selectedRequirementRecordIds.value = (selectedRequirementRecordIds.value || []).filter((item) =>
      visibleIds.has(String(item || "").trim()),
    );
    const totalPages = Math.max(
      1,
      Math.ceil(visibleIds.size / Math.max(1, Number(requirementRecordsPageSize.value || 10))),
    );
    if (requirementRecordsPage.value > totalPages) {
      requirementRecordsPage.value = totalPages;
    }
    if (!expandedRequirementRecordId.value) return;
    const stillExists = (records || []).some(
      (item) => String(item?.id || "").trim() === expandedRequirementRecordId.value,
    );
    if (!stillExists) {
      expandedRequirementRecordId.value = "";
    }
  },
  { immediate: true },
);

watch(
  () => requirementRecordsPageSize.value,
  () => {
    requirementRecordsPage.value = 1;
  },
);

const selectedRequirementNodeRoundLabel = computed(() => {
  const round = selectedRequirementNodeRound.value;
  if (!round) return "-";
  return `第 ${Math.max(1, Number(round.roundIndex || 1))} 轮 · ${getRequirementRecordKindLabel(round.recordKind)}`;
});

const selectedRequirementNodeIsRoot = computed(() => (
  isTaskTreeRootNode(selectedRequirementNode.value, selectedRequirementNodeRound.value)
));

const selectedRequirementNodeDetailTitle = computed(() => {
  if (!selectedRequirementNode.value) return "节点详情";
  if (selectedRequirementNodeIsRoot.value) {
    return selectedRequirementNode.value?.title || selectedRequirementNodeRound.value?.rootGoal || "需求总览";
  }
  return selectedRequirementNode.value?.title || "节点详情";
});

const selectedRequirementNodeDescriptionText = computed(() => {
  const node = selectedRequirementNode.value;
  const round = selectedRequirementNodeRound.value;
  if (!node) return "该节点暂无目标描述。";
  const directText = String(node.objective || node.description || "").trim();
  if (directText) return directText;
  if (selectedRequirementNodeIsRoot.value) {
    return String(
      round?.summaryText
      || round?.rootGoal
      || round?.currentNodeTitle
      || "当前总目标暂无描述，后续会随着子任务推进逐步沉淀整轮结果。",
    ).trim();
  }
  return "该节点暂无目标描述。";
});

const selectedRequirementNodeVerificationMethodText = computed(() => {
  const node = selectedRequirementNode.value;
  if (Array.isArray(node?.verification_method)) {
    return node.verification_method.map((item) => String(item || "").trim()).filter(Boolean).join(" / ");
  }
  return String(node?.verification_method || "").trim();
});

const selectedRequirementNodeVerificationItems = computed(() => {
  const items = [];
  const seen = new Set();
  const pushItem = (value) => {
    const text = String(value || "").trim();
    if (!text || seen.has(text)) return;
    seen.add(text);
    items.push(text);
  };
  pushItem(selectedRequirementNode.value?.verification_result);
  for (const event of selectedRequirementNodeEvents.value || []) {
    for (const entry of Array.isArray(event?.verification) ? event.verification : []) {
      pushItem(entry);
    }
  }
  return items;
});

const selectedRequirementNodeOutcomeText = computed(() => {
  const node = selectedRequirementNode.value;
  const round = selectedRequirementNodeRound.value;
  const text = String(node?.latest_outcome || node?.summary_for_model || "").trim();
  if (text) return text;
  if (selectedRequirementNodeIsRoot.value) {
    return String(round?.summaryText || round?.currentNodeTitle || round?.rootGoal || "-").trim() || "-";
  }
  return "-";
});

const selectedRequirementNodeVerificationResultText = computed(() => {
  const text = String(selectedRequirementNode.value?.verification_result || "").trim();
  if (text) return text;
  if (selectedRequirementNodeIsRoot.value && selectedRequirementNodeVerificationItems.value.length) {
    return `已汇总 ${selectedRequirementNodeVerificationItems.value.length} 条验证结果`;
  }
  return "-";
});

const selectedMemorySections = computed(() =>
  parseMemorySections(selectedMemoryDetail.value?.content || ""),
);

function isCompletedLikeStatus(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized === "completed" || normalized === "done";
}

function resolveRequirementRoundDisplayStatus(round) {
  const rawStatus = String(round?.status || "").trim().toLowerCase();
  if (!round) {
    return "pending";
  }
  if (round.isFinalized || rawStatus === "done") {
    return "done";
  }
  if (rawStatus === "blocked") {
    return "blocked";
  }
  const workSessionStatus = String(round?.primaryWorkSession?.latest_status || "").trim().toLowerCase();
  if (
    (rawStatus === "pending" || rawStatus === "in_progress" || rawStatus === "verifying")
    && isCompletedLikeStatus(workSessionStatus)
  ) {
    return "paused";
  }
  return rawStatus || "pending";
}

function isRequirementRoundPlaceholder(round) {
  if (!round || round.isFinalized) {
    return false;
  }
  const rawStatus = String(round.status || "").trim().toLowerCase();
  if (rawStatus !== "pending") {
    return false;
  }
  if (Number(round.progressPercent || 0) > 0) {
    return false;
  }
  if (round.primaryMemory) {
    return false;
  }
  return !(Array.isArray(round.workSessions) && round.workSessions.length);
}

function resolveRequirementRoundHealth(round) {
  if (!round) {
    return {
      state: "unknown",
      label: "待同步",
      summary: "当前轮次还没有足够的任务树信息。",
      tone: "neutral",
      tagType: "info",
      priority: 5,
    };
  }
  const taskStatus = String(round.status || "").trim().toLowerCase();
  const currentNodeStatus = String(round.taskTree?.current_node?.status || "").trim().toLowerCase();
  const workSessionStatus = String(round.primaryWorkSession?.latest_status || "").trim().toLowerCase();
  const taskTreeHealth = round.taskTree?.task_tree_health || null;
  const hasResumeAnchor = Boolean(
    round.primaryWorkSession?.session_id || round.sessionId || round.chatSessionId,
  );
  if (!round.isFinalized && taskTreeHealth?.rebuild_recommended) {
    return {
      state: "needs_rebuild",
      label: "建议重建",
      summary: String(
        taskTreeHealth.rebuild_reason
        || taskTreeHealth.issues?.[0]?.message
        || "当前任务树和真实目标不匹配，建议先重建后再继续。",
      ).trim(),
      tone: "danger",
      tagType: "danger",
      priority: 0,
    };
  }
  if (round.isFinalized) {
    return {
      state: "archived",
      label: "已归档",
      summary: "任务树和验证结果已经闭环完成，这条链路可以直接当历史查看。",
      tone: "success",
      tagType: "success",
      priority: 5,
    };
  }
  if (currentNodeStatus === "verifying" || taskStatus === "verifying") {
    return {
      state: "needs_verification",
      label: "待补验证",
      summary: "当前节点已经进入验证阶段，补齐验证结果后才能真正完成本轮任务。",
      tone: "warning",
      tagType: "warning",
      priority: 0,
    };
  }
  if (isCompletedLikeStatus(workSessionStatus) && !round.isFinalized) {
    return {
      state: "needs_closure",
      label: "待收口",
      summary: "工作轨迹显示本轮已跑完，但任务树还没有完成归档，建议优先收口。",
      tone: "danger",
      tagType: "danger",
      priority: 1,
    };
  }
  if (isRequirementRoundPlaceholder(round)) {
    return {
      state: "placeholder",
      label: "空挂占位",
      summary: "当前只挂上了会话，还没有形成有效节点进展或执行轨迹。",
      tone: "warning",
      tagType: "warning",
      priority: 2,
    };
  }
  if (
    hasResumeAnchor
    && (taskStatus === "pending" || taskStatus === "in_progress" || currentNodeStatus === "in_progress")
  ) {
    return {
      state: "resumable",
      label: "可恢复",
      summary: "任务树、聊天会话和工作轨迹锚点都还在，中断后可以直接继续执行。",
      tone: "info",
      tagType: "info",
      priority: 3,
    };
  }
  return {
    state: "active",
    label: getTaskSessionStatusLabel(taskStatus || currentNodeStatus || "pending"),
    summary: "当前轮次正在正常推进，没有发现需要优先处理的健康信号。",
    tone: "neutral",
    tagType: getTaskSessionStatusTagType(taskStatus || currentNodeStatus || "pending") || "info",
    priority: 4,
  };
}

function isTaskTreeFinalized(taskTree) {
  if (!taskTree || typeof taskTree !== "object") {
    return false;
  }
  const status = String(taskTree.status || "").trim().toLowerCase();
  const progressPercent = Number(taskTree.progress_percent || 0);
  const stats = taskTree.stats && typeof taskTree.stats === "object" ? taskTree.stats : {};
  const leafTotal = Number(taskTree.leaf_total ?? stats.leaf_total ?? 0);
  const doneLeafTotal = Number(taskTree.done_leaf_total ?? stats.done_leaf_total ?? 0);
  if (Boolean(taskTree.is_archived) && status === "done") {
    return true;
  }
  if (status !== "done") {
    return false;
  }
  if (progressPercent >= 100) {
    return true;
  }
  return leafTotal > 0 && doneLeafTotal >= leafTotal;
}

function resolveTaskTreeProgressPercent(taskTree) {
  if (!taskTree || typeof taskTree !== "object") {
    return 0;
  }
  const explicitProgress = Number(taskTree.progress_percent || 0);
  if (explicitProgress > 0) {
    return explicitProgress;
  }
  if (isTaskTreeFinalized(taskTree)) {
    return 100;
  }
  const stats = taskTree.stats && typeof taskTree.stats === "object" ? taskTree.stats : {};
  const leafTotal = Number(taskTree.leaf_total ?? stats.leaf_total ?? 0);
  const doneLeafTotal = Number(taskTree.done_leaf_total ?? stats.done_leaf_total ?? 0);
  if (leafTotal > 0 && doneLeafTotal > 0) {
    return Math.round((doneLeafTotal / leafTotal) * 100);
  }
  return 0;
}

const selectedMemoryHasTaskTree = computed(() =>
  Boolean(
    memoryDetailTaskTree.value
    || selectedMemoryDetail.value?.task_tree_session_id
    || selectedMemoryDetail.value?.task_tree_chat_session_id,
  ),
);

const selectedMemoryTaskSessionLabel = computed(() => {
  if (!selectedMemoryHasTaskTree.value) {
    return "未关联";
  }
  return (
    String(memoryDetailTaskTree.value?.id || "").trim()
    || String(selectedMemoryDetail.value?.task_session_id || "").trim()
    || String(selectedMemoryDetail.value?.task_tree_session_id || "").trim()
    || "已关联"
  );
});

const selectedMemoryQuestionText = computed(() => {
  return (
    selectedMemorySections.value.question
    || String(
      selectedMemoryDetail.value?.question_preview
      || selectedMemoryDetail.value?.root_goal
      || selectedMemoryDetail.value?.title
      || "",
    ).trim()
  );
});

const selectedMemoryTaskTreeFallbackText = computed(() =>
  extractTaskTreeFallbackText(memoryDetailTaskTree.value),
);

const selectedMemoryWorkEventFallbackText = computed(() =>
  summarizeMemoryFallbackWorkEvent(memoryDetailWorkEvents.value),
);

const selectedMemorySolutionText = computed(() => {
  if (selectedMemorySections.value.solution) {
    return selectedMemorySections.value.solution;
  }
  if (!selectedMemoryIsFinalized.value) {
    return "执行计划已写入任务树，当前按计划逐项推进：完成一个节点、补一次验证，再进入下一步。";
  }
  if (selectedMemorySections.value.conclusion) {
    return selectedMemorySections.value.conclusion;
  }
  return (
    selectedMemoryTaskTreeFallbackText.value
    || selectedMemoryWorkEventFallbackText.value
    || selectedMemoryRawContentText.value
    || ""
  );
});

const selectedMemoryIsFinalized = computed(() => {
  if (selectedMemorySections.value.conclusion) {
    return true;
  }
  if (isTaskTreeFinalized(memoryDetailTaskTree.value)) {
    return true;
  }
  if (isCompletedLikeStatus(selectedMemoryDetail.value?.linked_work_session?.latest_status)) {
    return true;
  }
  return String(selectedMemoryDetail.value?.solve_status || "").trim().toLowerCase() === "resolved";
});

const selectedMemoryConclusionText = computed(() => {
  if (selectedMemorySections.value.conclusion) {
    return selectedMemorySections.value.conclusion;
  }
  if (!selectedMemoryIsFinalized.value) {
    return "当前需求尚未全部完成，最终结论会在所有计划项完成并完成验证后生成。";
  }
  return (
    selectedMemoryWorkEventFallbackText.value
    || selectedMemoryTaskTreeFallbackText.value
    || selectedMemoryRawContentText.value
    || ""
  );
});

const selectedMemoryRawContentText = computed(() => {
  return shouldDisplayRawMemoryContent(selectedMemoryDetail.value, selectedMemorySections.value)
    ? String(selectedMemoryDetail.value?.content || "").trim()
    : "";
});

function parseComparableTimestamp(value) {
  const timestamp = Date.parse(String(value || "").trim());
  return Number.isFinite(timestamp) ? timestamp : NaN;
}

function compareTaskSessionByCreatedAtDesc(left, right) {
  const leftCreatedAt = parseComparableTimestamp(left?.created_at);
  const rightCreatedAt = parseComparableTimestamp(right?.created_at);
  if (Number.isFinite(leftCreatedAt) || Number.isFinite(rightCreatedAt)) {
    if (!Number.isFinite(leftCreatedAt)) return 1;
    if (!Number.isFinite(rightCreatedAt)) return -1;
    if (leftCreatedAt !== rightCreatedAt) {
      return rightCreatedAt - leftCreatedAt;
    }
  }
  const leftUpdatedAt = parseComparableTimestamp(left?.updated_at);
  const rightUpdatedAt = parseComparableTimestamp(right?.updated_at);
  if (Number.isFinite(leftUpdatedAt) || Number.isFinite(rightUpdatedAt)) {
    if (!Number.isFinite(leftUpdatedAt)) return 1;
    if (!Number.isFinite(rightUpdatedAt)) return -1;
    if (leftUpdatedAt !== rightUpdatedAt) {
      return rightUpdatedAt - leftUpdatedAt;
    }
  }
  return String(right?.id || "").localeCompare(String(left?.id || ""));
}

function compareTaskSessionByCreatedAtAsc(left, right) {
  return compareTaskSessionByCreatedAtDesc(right, left);
}

function findLinkedWorkSessionForMemory(memory) {
  const sections = parseMemorySections(memory?.content || "");
  const questionText = String(sections?.question || "").replace(/\s+/g, " ").trim();
  if (!questionText) {
    return null;
  }
  const candidates = (projectWorkSessions.value || [])
    .filter((item) => String(item?.goal || "").replace(/\s+/g, " ").trim() === questionText)
    .slice()
    .sort(compareTaskSessionByCreatedAtDesc);
  if (!candidates.length) {
    return null;
  }
  const completedCandidates = candidates.filter((item) => isCompletedLikeStatus(item?.latest_status));
  const memoryCreatedAt = parseComparableTimestamp(memory?.created_at);
  if (!Number.isFinite(memoryCreatedAt)) {
    return completedCandidates[0] || candidates[0] || null;
  }
  const futureCompletedCandidates = completedCandidates
    .filter((item) => {
      const sessionCreatedAt = parseComparableTimestamp(item?.created_at);
      return Number.isFinite(sessionCreatedAt) && sessionCreatedAt >= memoryCreatedAt;
    })
    .slice()
    .sort(compareTaskSessionByCreatedAtAsc);
  if (futureCompletedCandidates.length) {
    return futureCompletedCandidates[0];
  }
  const historyCompletedCandidates = completedCandidates.filter((item) => {
    const sessionCreatedAt = parseComparableTimestamp(item?.created_at);
    return Number.isFinite(sessionCreatedAt) && sessionCreatedAt <= memoryCreatedAt;
  });
  return historyCompletedCandidates[0] || completedCandidates[0] || candidates[0] || null;
}

function findLinkedTaskSessionForMemory(memory, linkedWorkSession = null) {
  const explicitTaskSessionId = String(memory?.task_tree_session_id || "").trim();
  if (explicitTaskSessionId) {
    const exactMatch = (projectTaskSessions.value || []).find(
      (item) => String(item?.id || "").trim() === explicitTaskSessionId,
    );
    if (exactMatch) {
      return exactMatch;
    }
  }
  const chatSessionId = String(memory?.chat_session_id || "").trim();
  if (!chatSessionId) {
    return null;
  }
  const sections = parseMemorySections(memory?.content || "");
  const questionText = String(sections?.question || "").trim();
  const explicitTaskTreeChatSessionId = String(memory?.task_tree_chat_session_id || "").trim();
  let candidates = (projectTaskSessions.value || [])
    .filter((item) => {
      const itemChatSessionId = String(item?.chat_session_id || "").trim();
      const itemSourceChatSessionId = String(item?.source_chat_session_id || "").trim();
      return chatSessionId === itemChatSessionId || chatSessionId === itemSourceChatSessionId;
    })
    .slice()
    .sort(compareTaskSessionByCreatedAtDesc);
  if (explicitTaskTreeChatSessionId) {
    const scopedCandidates = candidates.filter((item) => {
      const itemChatSessionId = String(item?.chat_session_id || "").trim();
      const itemSourceChatSessionId = String(item?.source_chat_session_id || "").trim();
      return (
        explicitTaskTreeChatSessionId === itemChatSessionId
        || explicitTaskTreeChatSessionId === itemSourceChatSessionId
      );
    });
    if (scopedCandidates.length) {
      candidates = scopedCandidates;
    }
  }
  if (questionText) {
    const normalizedQuestion = questionText.replace(/\s+/g, " ").trim();
    const matchedByGoal = candidates.filter((item) => {
      const rootGoal = String(item?.root_goal || item?.title || "").replace(/\s+/g, " ").trim();
      return rootGoal === normalizedQuestion;
    });
    if (matchedByGoal.length) {
      candidates = matchedByGoal;
    }
  }
  if (!candidates.length) {
    return null;
  }
  const archivedCandidates = candidates
    .filter(
      (item) =>
        Boolean(item?.is_archived) || String(item?.status || "").trim().toLowerCase() === "done",
    )
    .slice()
    .sort(compareTaskSessionByCreatedAtDesc);
  if (
    !explicitTaskSessionId
    && !archivedCandidates.length
    && linkedWorkSession
    && isCompletedLikeStatus(linkedWorkSession?.latest_status)
  ) {
    return null;
  }
  const memoryCreatedAt = parseComparableTimestamp(memory?.created_at);
  const isQuestionSnapshot = !hasConversationMemorySections(sections);
  if (isQuestionSnapshot && Number.isFinite(memoryCreatedAt)) {
    const futureArchivedCandidates = archivedCandidates
      .filter((item) => {
        const sessionCreatedAt = parseComparableTimestamp(item?.created_at);
        return Number.isFinite(sessionCreatedAt) && sessionCreatedAt >= memoryCreatedAt;
      })
      .slice()
      .sort(compareTaskSessionByCreatedAtAsc);
    if (futureArchivedCandidates.length) {
      return futureArchivedCandidates[0];
    }
  }
  if (!Number.isFinite(memoryCreatedAt)) {
    return archivedCandidates[0] || candidates[0];
  }
  const historyCandidates = candidates.filter((item) => {
    const sessionCreatedAt = parseComparableTimestamp(item?.created_at);
    return Number.isFinite(sessionCreatedAt) && sessionCreatedAt <= memoryCreatedAt;
  });
  return historyCandidates[0] || archivedCandidates[0] || candidates[0] || null;
}

const enrichedProjectMemories = computed(() =>
  (visibleProjectMemories.value || []).map((memory) => {
    const linkedWorkSession = findLinkedWorkSessionForMemory(memory);
    const linkedTask = findLinkedTaskSessionForMemory(memory, linkedWorkSession);
    const sections = parseMemorySections(memory.content || "");
    const solveStatus = deriveMemorySolveStatus(memory, linkedTask, linkedWorkSession, sections);
    const rawPreview = shouldDisplayRawMemoryContent(memory, sections)
      ? clipText(memory.content || "", 160)
      : "";
    const workSessionStatus = String(linkedWorkSession?.latest_status || "").trim();
    const workSessionStep = Array.isArray(linkedWorkSession?.steps)
      ? linkedWorkSession.steps.find((item) => String(item || "").trim())
      : "";
    return {
      ...memory,
      question_preview: sections.question || "",
      solution_preview: sections.solution || "",
      conclusion_preview: sections.conclusion || "",
      display_preview: sections.solution || sections.conclusion || sections.process || rawPreview,
      solve_status: solveStatus,
      task_status: String(linkedTask?.status || workSessionStatus || "").trim(),
      task_status_label: linkedTask?.status || workSessionStatus || "-",
      task_session_id: String(linkedTask?.id || "").trim(),
      current_node_title: String(linkedTask?.current_node_title || workSessionStep || "").trim(),
      progress_percent: Number(
        resolveTaskTreeProgressPercent(linkedTask)
        || (isCompletedLikeStatus(workSessionStatus) ? 100 : 0),
      ),
      has_task_tree: Boolean(linkedTask),
      has_execution_session: Boolean(linkedWorkSession),
      execution_session_id: String(linkedWorkSession?.session_id || "").trim(),
      linked_task_session: linkedTask || null,
      linked_work_session: linkedWorkSession || null,
    };
  }),
);

const selectedMemoryProcessSummary = computed(() => {
  if (selectedMemorySections.value.process) {
    return selectedMemorySections.value.process;
  }
  if (shouldDisplayRawMemoryContent(selectedMemoryDetail.value, selectedMemorySections.value)) {
    return "";
  }
  if (
    memoryDetailTaskTree.value
    && (
      Boolean(memoryDetailTaskTree.value?.is_archived)
      || String(memoryDetailTaskTree.value?.status || "").trim().toLowerCase() === "done"
    )
  ) {
    const doneLeafTotal = Number(memoryDetailTaskTree.value?.done_leaf_total || 0);
    const leafTotal = Number(memoryDetailTaskTree.value?.leaf_total || 0);
    return `可结合关联任务树回看本轮处理过程，本轮任务已归档完成，已完成 ${doneLeafTotal}/${leafTotal} 个叶子节点。`;
  }
  if (memoryDetailTaskTree.value?.current_node?.title) {
    const doneLeafTotal = Number(memoryDetailTaskTree.value?.done_leaf_total || 0);
    const leafTotal = Number(memoryDetailTaskTree.value?.leaf_total || 0);
    return `可结合关联任务树回看本轮处理过程，当前节点为“${memoryDetailTaskTree.value.current_node.title}”，已完成 ${doneLeafTotal}/${leafTotal} 个叶子节点。`;
  }
  if (selectedMemoryHasTaskTree.value) {
    return "当前需求记录未单独写入过程摘要，可结合下方关联任务树回看本轮处理过程。";
  }
  if (memoryDetailWorkEvents.value.length) {
    return "当前需求记录未保留可读取任务树，已根据关联工作轨迹恢复本轮处理过程。";
  }
  if (selectedMemoryDetail.value?.chat_session_id) {
    return "当前需求记录已绑定会话，但没有可读取的任务树；这通常表示该轮只留下了会话快照，未成功生成或保留任务树。";
  }
  return "当前需求记录未单独写入过程摘要，且未关联任务树。";
});

const memoryDetailTaskNodes = computed(() => {
  const nodes = Array.isArray(memoryDetailTaskTree.value?.nodes)
    ? memoryDetailTaskTree.value.nodes
    : [];
  return nodes.filter((item) => Number(item?.level || 0) > 0);
});

const memoryDetailWorkEventsByNodeId = computed(() => {
  const result = new Map();
  for (const item of memoryDetailWorkEvents.value || []) {
    const taskNodeId = String(item?.task_node_id || "").trim();
    if (!taskNodeId) continue;
    if (!result.has(taskNodeId)) {
      result.set(taskNodeId, []);
    }
    result.get(taskNodeId).push(item);
  }
  return result;
});

const memoryDetailUnassignedWorkEvents = computed(() =>
  (memoryDetailWorkEvents.value || []).filter((item) => !String(item?.task_node_id || "").trim()),
);

const pagedProjectUsers = computed(() => {
  const start = (projectUsersPage.value - 1) * projectUsersPageSize.value;
  return (projectUsers.value || []).slice(start, start + projectUsersPageSize.value);
});

const pagedMembers = computed(() => {
  const start = (membersPage.value - 1) * membersPageSize.value;
  return (members.value || []).slice(start, start + membersPageSize.value);
});

function normalizeProjectDetailTab(value) {
  const normalized = String(value || "").trim();
  return availableProjectDetailTabs.value.includes(normalized)
    ? normalized
    : availableProjectDetailTabs.value[0] || "overview";
}

watch([projectUsersPageSize, projectUsers], () => {
  projectUsersPage.value = 1;
});

watch(
  () => projectId.value,
  async (nextProjectId, previousProjectId) => {
    if (nextProjectId === previousProjectId && previousProjectId !== undefined) {
      return;
    }
    resetProjectScopedState();
    if (!nextProjectId) {
      loading.value = false;
      return;
    }
    await refresh(nextProjectId);
  },
  { immediate: true },
);

watch(
  () => [route.query.tab, availableProjectDetailTabs.value.join("|")],
  () => {
    const nextTab = normalizeProjectDetailTab(route.query.tab);
    if (activeProjectTab.value !== nextTab) {
      activeProjectTab.value = nextTab;
    }
  },
  { immediate: true },
);

watch(activeProjectTab, (value) => {
  const normalized = normalizeProjectDetailTab(value);
  if (normalized !== value) {
    activeProjectTab.value = normalized;
    return;
  }
  void ensureProjectTabData(normalized);
  const defaultTab = availableProjectDetailTabs.value[0] || "overview";
  const currentTab = String(route.query.tab || "").trim();
  if ((normalized === defaultTab && !currentTab) || currentTab === normalized) {
    return;
  }
  const nextQuery = { ...route.query };
  if (normalized === defaultTab) {
    delete nextQuery.tab;
  } else {
    nextQuery.tab = normalized;
  }
  void router.replace({
    path: route.path,
    query: nextQuery,
    hash: route.hash,
  });
});

watch([membersPageSize, members], () => {
  membersPage.value = 1;
});

const boundUiRules = computed(() => {
  const bindings = Array.isArray(project.value?.ui_rule_bindings)
    ? project.value.ui_rule_bindings
    : [];
  if (bindings.length) {
    return bindings.map((item) => ({
      id: String(item.id || "").trim(),
      title: String(item.title || item.id || "").trim(),
      domain: String(item.domain || "").trim(),
    }));
  }
  return normalizeStringList(project.value?.ui_rule_ids || []).map((ruleId) => {
    const matched = ruleMap.value.get(ruleId);
    return {
      id: ruleId,
      title: matched?.title || `${ruleId} (历史配置)`,
      domain: matched?.domain || "",
    };
  });
});

const boundExperienceRules = computed(() => {
  const bindings = Array.isArray(project.value?.experience_rule_bindings)
    ? project.value.experience_rule_bindings
    : [];
  if (bindings.length) {
    return bindings.map((item) => ({
      id: String(item.id || "").trim(),
      title: String(item.title || item.id || "").trim(),
      displayTitle: stripExperienceRuleTitlePrefix(String(item.title || item.id || "").trim()),
      domain: String(item.domain || "").trim(),
      preview: String(item.preview || "").trim(),
      experienceScope: String(item.experience_scope || "").trim(),
      systemSource: String(item.system_source || "").trim(),
    }));
  }
  return normalizeStringList(project.value?.experience_rule_ids || []).map((ruleId) => ({
    id: ruleId,
    title: `${ruleId} (历史配置)`,
    displayTitle: `${ruleId} (历史配置)`,
    domain: "项目经验",
    preview: "",
    experienceScope: "project",
    systemSource: "project_experience",
  }));
});

const hasLegacyProjectExperienceRules = computed(() =>
  boundExperienceRules.value.some((item) => item.systemSource === "project_experience"),
);

const experienceSummaryDialogDescription = computed(() => {
  const targetIds = getExperienceSummaryTargetRecordIds();
  const targetCount = targetIds.length;
  if (!targetCount) {
    return getExperienceSummaryUnavailableMessage();
  }
  const selectedCount = selectedRequirementRecordCount.value;
  const scopeText = selectedCount
    ? `将优先总结已选中的 ${selectedCount} 条需求记录`
    : `将总结当前筛选结果中的 ${targetCount} 条需求记录`;
  return `${scopeText}，生成可复用开发经验卡片，写入开发经验库，并把当前项目绑定到对应规则，成功后会清空这批记录。`;
});

const hasActiveRequirementRecordFilters = computed(() =>
  Boolean(
    String(memoryFilters.value.query || "").trim()
    || String(memoryFilters.value.employeeId || "").trim()
    || String(memoryFilters.value.type || "").trim(),
  ),
);

function normalizeStringList(values) {
  return Array.from(
    new Set(
      (Array.isArray(values) ? values : [])
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  );
}

function stripExperienceRuleTitlePrefix(value) {
  const title = String(value || "").trim();
  for (const prefix of ["经验卡片 · ", "开发经验 · "]) {
    if (title.startsWith(prefix)) {
      return title.slice(prefix.length).trim() || title;
    }
  }
  return title;
}

function ensureUiRuleOptionCoverage() {
  const next = [...(ruleOptions.value || [])];
  const known = new Set(next.map((item) => String(item.id || "").trim()).filter(Boolean));
  for (const item of boundUiRules.value) {
    const ruleId = String(item.id || "").trim();
    if (!ruleId || known.has(ruleId)) continue;
    next.push({
      id: ruleId,
      title: String(item.title || ruleId).trim(),
      domain: String(item.domain || "").trim(),
    });
    known.add(ruleId);
  }
  ruleOptions.value = next;
}

function resetAddForm() {
  addForm.value = {
    employee_ids: [],
    role: "member",
    enabled: true,
  };
}

function resetUserForm() {
  userForm.value = {
    usernames: [],
    role: "member",
    enabled: true,
  };
}

async function fetchEmployees() {
  try {
    const data = await api.get("/employees");
    employeeOptions.value = data.employees || [];
  } catch {
    employeeOptions.value = [];
  }
}

async function fetchRules() {
  try {
    const data = await api.get("/rules");
    ruleOptions.value = (data.rules || []).map((rule) => ({
      id: String(rule.id || "").trim(),
      title: String(rule.title || rule.id || "").trim(),
      domain: String(rule.domain || "").trim(),
    }));
  } catch {
    ruleOptions.value = [];
  } finally {
    ensureUiRuleOptionCoverage();
  }
}

async function fetchProject(targetProjectId = projectId.value) {
  const effectiveProjectId = String(targetProjectId || "").trim();
  if (!effectiveProjectId) return;
  const data = await api.get(`/projects/${effectiveProjectId}`);
  if (effectiveProjectId !== projectId.value) return;
  project.value = {
    ...(data.project || {}),
    type: normalizeProjectType(data.project?.type),
    ui_rule_ids: normalizeStringList(data.project?.ui_rule_ids || []),
    experience_rule_ids: normalizeStringList(data.project?.experience_rule_ids || []),
  };
  ensureUiRuleOptionCoverage();
}

async function fetchExperienceProviders() {
  experienceProvidersLoading.value = true;
  try {
    const data = await api.get("/llm/providers", {
      params: { enabled_only: true },
    });
    const providers = Array.isArray(data?.providers) ? data.providers : [];
    experienceProviderOptions.value = providers
      .map((item) => ({
        id: String(item.id || "").trim(),
        name: String(item.name || item.id || "未命名模型源").trim(),
        models: Array.isArray(item.models)
          ? item.models.map((model) => String(model || "").trim()).filter(Boolean)
          : [],
        default_model: String(item.default_model || "").trim(),
        is_default: !!item.is_default,
      }))
      .filter((item) => item.id && item.models.length);
    const preferred =
      experienceProviderOptions.value.find((item) => item.id === experienceSummaryProviderId.value)
      || experienceProviderOptions.value.find((item) => item.is_default)
      || experienceProviderOptions.value[0]
      || null;
    experienceSummaryProviderId.value = preferred?.id || "";
    const availableModels = preferred?.models || [];
    if (!availableModels.includes(String(experienceSummaryModelName.value || "").trim())) {
      experienceSummaryModelName.value =
        preferred?.default_model || availableModels[0] || "";
    }
  } catch (err) {
    experienceProviderOptions.value = [];
    experienceSummaryProviderId.value = "";
    experienceSummaryModelName.value = "";
    ElMessage.error(err?.detail || err?.message || "加载模型列表失败");
  } finally {
    experienceProvidersLoading.value = false;
  }
}

function normalizeProjectType(value) {
  const normalized = String(value || "").trim();
  return projectTypeOptions.some((item) => item.value === normalized)
    ? normalized
    : "mixed";
}

function getProjectTypeLabel(value) {
  const matched = projectTypeOptions.find(
    (item) => item.value === normalizeProjectType(value),
  );
  return matched?.label || "综合项目";
}

function getProjectTypeDescription(value) {
  const matched = projectTypeOptions.find(
    (item) => item.value === normalizeProjectType(value),
  );
  return matched?.description || "适合图文混合或方向未定的项目，默认工作流更中性。";
}

function getProjectTypeTagType(value) {
  const normalized = normalizeProjectType(value);
  if (normalized === "image") return "success";
  if (normalized === "storyboard_video") return "warning";
  return "info";
}

function getTaskSessionStatusTagType(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "done") return "success";
  if (normalized === "blocked") return "danger";
  if (normalized === "verifying") return "warning";
  if (normalized === "paused") return "info";
  if (normalized === "in_progress") return "";
  return "info";
}

function getTaskSessionStatusLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "done") return "已完成";
  if (normalized === "blocked") return "阻塞";
  if (normalized === "verifying") return "验证中";
  if (normalized === "paused") return "已暂停";
  if (normalized === "in_progress") return "进行中";
  if (normalized === "pending") return "待开始";
  return String(value || "待开始").trim() || "待开始";
}

function getRequirementRecordKindLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "repair") return "修复记录";
  return "需求主记录";
}

function getRequirementRecordKindTagType(value) {
  return String(value || "").trim().toLowerCase() === "repair" ? "warning" : "info";
}

function formatTaskTreeStepIndex(node, index = 0) {
  const sortOrder = Number(node?.sort_order || 0);
  const fallbackIndex = Number(index) + 1;
  const safeIndex = sortOrder > 0 ? sortOrder : fallbackIndex;
  return String(Math.max(1, safeIndex)).padStart(2, "0");
}

function getWorkSessionStatusTagType(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "completed" || normalized === "done") return "success";
  if (normalized === "blocked" || normalized === "failed") return "danger";
  if (normalized === "in_progress" || normalized === "verifying") return "warning";
  return "info";
}

async function openMemoryDetail(row) {
  selectedMemoryDetail.value = row && typeof row === "object" ? { ...row } : null;
  showMemoryDetailDialog.value = true;
  memoryDetailTaskTree.value = null;
  memoryDetailWorkEvents.value = [];
  const explicitTaskSessionId = String(selectedMemoryDetail.value?.task_tree_session_id || "").trim();
  const taskSessionId = String(
    selectedMemoryDetail.value?.task_session_id
    || explicitTaskSessionId
    || "",
  ).trim();
  const chatSessionId = String(selectedMemoryDetail.value?.chat_session_id || "").trim();
  const linkedWorkSessionId = String(
    selectedMemoryDetail.value?.linked_work_session?.session_id || "",
  ).trim();
  const shouldPreferWorkSessionFallback =
    !explicitTaskSessionId
    && linkedWorkSessionId
    && isCompletedLikeStatus(selectedMemoryDetail.value?.linked_work_session?.latest_status)
    && !selectedMemoryDetail.value?.has_task_tree;
  if (shouldPreferWorkSessionFallback) {
    await fetchMemoryDetailWorkEvents(null, { sessionId: linkedWorkSessionId });
    return;
  }
  if (!taskSessionId && !chatSessionId) {
    if (linkedWorkSessionId) {
      await fetchMemoryDetailWorkEvents(null, { sessionId: linkedWorkSessionId });
    }
    return;
  }
  memoryDetailTaskTreeLoading.value = true;
  try {
    const params = {};
    if (taskSessionId) {
      params.session_id = taskSessionId;
    } else if (chatSessionId) {
      params.chat_session_id = chatSessionId;
    }
    const data = await api.get(`/projects/${projectId.value}/chat/task-tree`, {
      params,
    });
    memoryDetailTaskTree.value = normalizeTaskTreePayload(resolveTaskTreeResponsePayload(data));
    await fetchMemoryDetailWorkEvents(memoryDetailTaskTree.value);
  } catch (err) {
    memoryDetailTaskTree.value = null;
    memoryDetailWorkEvents.value = [];
    ElMessage.error(err?.detail || err?.message || "加载关联任务树失败");
  } finally {
    memoryDetailTaskTreeLoading.value = false;
  }
}

async function fetchMemoryDetailWorkEvents(taskTree, options = {}) {
  const sessionId = String(options?.sessionId || "").trim();
  const taskTreeSessionId = String(taskTree?.id || "").trim();
  const taskTreeChatSessionId = String(
    taskTree?.source_chat_session_id
    || taskTree?.chat_session_id
    || selectedMemoryDetail.value?.task_tree_chat_session_id
    || "",
  ).trim();
  if (!sessionId && !taskTreeSessionId && !taskTreeChatSessionId) {
    memoryDetailWorkEvents.value = [];
    return;
  }
  memoryDetailWorkEventsLoading.value = true;
  try {
    const params = { limit: 200 };
    if (sessionId) {
      params.session_id = sessionId;
    }
    if (taskTreeSessionId) {
      params.task_tree_session_id = taskTreeSessionId;
    }
    if (taskTreeChatSessionId) {
      params.task_tree_chat_session_id = taskTreeChatSessionId;
    }
    const data = await api.get(`/projects/${projectId.value}/work-session-events`, { params });
    memoryDetailWorkEvents.value = Array.isArray(data?.items)
      ? data.items.map((item) => normalizeProjectWorkEvent(item))
      : [];
  } catch (err) {
    memoryDetailWorkEvents.value = [];
    ElMessage.error(err?.detail || err?.message || "加载关联工作轨迹失败");
  } finally {
    memoryDetailWorkEventsLoading.value = false;
  }
}

async function openWorkSessionDetail(row) {
  const sessionId = String(row?.session_id || "").trim();
  if (!sessionId) return;
  showWorkSessionDetailDialog.value = true;
  workSessionDetailLoading.value = true;
  selectedWorkSession.value = normalizeWorkSessionSummary(row);
  selectedWorkSessionEvents.value = [];
  try {
    const data = await api.get(`/projects/${projectId.value}/work-sessions/${encodeURIComponent(sessionId)}`, {
      params: {
        employee_id: row?.employee_id || undefined,
      },
    });
    selectedWorkSession.value = normalizeWorkSessionSummary(data?.session || row);
    selectedWorkSessionEvents.value = Array.isArray(data?.items)
      ? data.items.map((item) => ({
          ...item,
          employee_name:
            String(item?.employee_name || "").trim()
            || memberNameMap.value.get(String(item?.employee_id || "").trim())
            || String(item?.employee_id || "").trim(),
          verification: Array.isArray(item?.verification)
            ? item.verification.map((entry) => String(entry || "").trim()).filter(Boolean)
            : [],
          facts: Array.isArray(item?.facts)
            ? item.facts.map((entry) => String(entry || "").trim()).filter(Boolean)
            : [],
        }))
      : [];
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载工作轨迹详情失败");
    showWorkSessionDetailDialog.value = false;
  } finally {
    workSessionDetailLoading.value = false;
  }
}

function buildSyntheticMemoryFromRound(round) {
  if (!round || typeof round !== "object") {
    return null;
  }
  return {
    id: `task-tree:${round.sessionId || round.id || ""}`,
    employee_id: String(round.primaryMemory?.employee_id || round.primaryWorkSession?.employee_id || "").trim(),
    employee_name: String(
      round.primaryMemory?.employee_name
      || round.primaryWorkSession?.employee_name
      || round.primaryMemory?.employee_id
      || round.primaryWorkSession?.employee_id
      || "",
    ).trim(),
    type: String(round.primaryMemory?.type || "").trim(),
    content: "",
    purpose_tags: [round.recordKind === "repair" ? "repair-record" : "requirement-record"],
    chat_session_id: String(round.chatSessionId || "").trim(),
    task_tree_session_id: String(round.sessionId || round.id || "").trim(),
    task_tree_chat_session_id: String(round.chatSessionId || "").trim(),
    task_session_id: String(round.sessionId || round.id || "").trim(),
    question_preview: String(round.rootGoal || round.title || "").trim(),
    display_preview: String(round.summaryText || round.currentNodeTitle || "").trim(),
    solve_status: round.isFinalized ? "resolved" : "processing",
    progress_percent: Number(round.progressPercent || 0),
    has_task_tree: true,
    has_execution_session: Boolean(round.primaryWorkSession),
    execution_session_id: String(round.primaryWorkSession?.session_id || "").trim(),
    linked_work_session: round.primaryWorkSession || null,
    root_goal: String(round.rootGoal || round.title || "").trim(),
    title: String(round.title || round.rootGoal || "").trim(),
    created_at: String(round.createdAt || "").trim(),
  };
}

function openRequirementRoundDetail(round) {
  const syntheticMemory = buildSyntheticMemoryFromRound(round);
  if (round?.primaryMemory) {
    void openMemoryDetail({
      ...round.primaryMemory,
      ...(syntheticMemory || {}),
    });
    return;
  }
  if (!syntheticMemory) return;
  void openMemoryDetail(syntheticMemory);
}

function openRequirementRecordDetail(record) {
  const targetRound = record?.detailRound || record?.currentRound || record?.latestRound || null;
  if (!targetRound) return;
  openRequirementRoundDetail(targetRound);
}

function getRequirementRecordActionRound(record) {
  return record?.detailRound || record?.currentRound || record?.latestRound || null;
}

function getRequirementRecordActionKey(record) {
  const round = getRequirementRecordActionRound(record);
  return String(record?.id || round?.sessionId || round?.chatSessionId || "").trim();
}

function getRequirementRecordActionChatSessionId(record) {
  const round = getRequirementRecordActionRound(record);
  return String(round?.chatSessionId || "").trim();
}

function getRequirementRecordActionRootGoal(record) {
  const round = getRequirementRecordActionRound(record);
  return String(record?.rootGoal || round?.rootGoal || "").trim();
}

function canClearRequirementRecordTaskTree(record) {
  return Boolean(getRequirementRecordActionChatSessionId(record));
}

function canRegenerateRequirementRecordTaskTree(record) {
  return Boolean(
    getRequirementRecordActionChatSessionId(record)
    && getRequirementRecordActionRootGoal(record),
  );
}

function isRequirementRecordTaskTreeClearing(record) {
  const actionKey = getRequirementRecordActionKey(record);
  return Boolean(actionKey) && Boolean(requirementRecordTaskTreeClearingMap.value?.[actionKey]);
}

function isRequirementRecordTaskTreeRegenerating(record) {
  const actionKey = getRequirementRecordActionKey(record);
  return Boolean(actionKey) && Boolean(requirementRecordTaskTreeRegeneratingMap.value?.[actionKey]);
}

function pruneRequirementRecordTaskTreeDetails(record) {
  const nextDetails = { ...(projectTaskTreeDetails.value || {}) };
  for (const round of Array.isArray(record?.rounds) ? record.rounds : []) {
    const sessionId = String(round?.sessionId || round?.id || "").trim();
    if (sessionId) {
      delete nextDetails[sessionId];
    }
  }
  projectTaskTreeDetails.value = nextDetails;
}

function focusRequirementRecord(record) {
  const recordId = String(record?.id || "").trim();
  if (!recordId) return;
  expandedRequirementRecordId.value = recordId;
  const target = document.getElementById(`requirement-record-${recordId}`);
  target?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function isRequirementRoundTaskTreeLoading(round) {
  const sessionId = String(round?.sessionId || round?.id || "").trim();
  return Boolean(sessionId) && Boolean(requirementRoundTaskTreeLoadingMap.value?.[sessionId]);
}

async function ensureRequirementRoundTaskTree(round, options = {}) {
  const sessionId = String(round?.sessionId || round?.id || "").trim();
  const force = Boolean(options?.force);
  if (!sessionId) {
    return null;
  }
  if (!force && projectTaskTreeDetails.value?.[sessionId]) {
    return projectTaskTreeDetails.value[sessionId];
  }
  if (isRequirementRoundTaskTreeLoading(round)) {
    return null;
  }
  requirementRoundTaskTreeLoadingMap.value = {
    ...requirementRoundTaskTreeLoadingMap.value,
    [sessionId]: true,
  };
  try {
    const data = await api.get(`/projects/${projectId.value}/chat/task-tree`, {
      params: { session_id: sessionId },
    });
    const payload = normalizeTaskTreePayload(resolveTaskTreeResponsePayload(data));
    if (payload) {
      projectTaskTreeDetails.value = {
        ...(projectTaskTreeDetails.value || {}),
        [sessionId]: payload,
      };
      return payload;
    }
    return null;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载任务树详情失败");
    return null;
  } finally {
    const nextLoadingMap = { ...(requirementRoundTaskTreeLoadingMap.value || {}) };
    delete nextLoadingMap[sessionId];
    requirementRoundTaskTreeLoadingMap.value = nextLoadingMap;
  }
}

function isRequirementRecordSelected(record) {
  const recordId = String(record?.id || "").trim();
  return Boolean(recordId) && selectedRequirementRecordIdSet.value.has(recordId);
}

function toggleRequirementRecordSelection(recordId, checked = undefined) {
  const normalizedRecordId = String(recordId || "").trim();
  if (!normalizedRecordId) return;
  const nextSelected = new Set(selectedRequirementRecordIds.value || []);
  const shouldSelect =
    typeof checked === "boolean"
      ? checked
      : !nextSelected.has(normalizedRecordId);
  if (shouldSelect) {
    nextSelected.add(normalizedRecordId);
  } else {
    nextSelected.delete(normalizedRecordId);
  }
  selectedRequirementRecordIds.value = Array.from(nextSelected);
}

function toggleSelectAllRequirementRecords() {
  if (allRequirementRecordsSelected.value) {
    selectedRequirementRecordIds.value = [];
    return;
  }
  selectedRequirementRecordIds.value = visibleRequirementRecordIds.value.slice();
}

function isRequirementRecordExpanded(record) {
  const recordId = String(record?.id || "").trim();
  return Boolean(recordId) && recordId === expandedRequirementRecordId.value;
}

function toggleRequirementRecordExpansion(record) {
  const recordId = String(record?.id || "").trim();
  if (!recordId) return;
  const shouldExpand = expandedRequirementRecordId.value !== recordId;
  expandedRequirementRecordId.value = shouldExpand ? recordId : "";
  if (!shouldExpand) {
    return;
  }
  const targetRound = record?.detailRound || record?.currentRound || record?.latestRound || null;
  void ensureRequirementRoundTaskTree(targetRound);
}

async function openRequirementNodeDetail(node, round) {
  const taskTreeSessionId = String(round?.sessionId || round?.id || "").trim();
  const taskNodeId = String(node?.id || "").trim();
  if (!taskTreeSessionId || !taskNodeId) return;
  const shouldLoadWholeRound = isTaskTreeRootNode(node, round);
  selectedRequirementNode.value = node && typeof node === "object" ? { ...node } : null;
  selectedRequirementNodeRound.value = round && typeof round === "object" ? { ...round } : null;
  selectedRequirementNodeEvents.value = [];
  showRequirementNodeDetailDialog.value = true;
  requirementNodeDetailLoading.value = true;
  try {
    const params = {
      task_tree_session_id: taskTreeSessionId,
      limit: 200,
    };
    if (!shouldLoadWholeRound) {
      params.task_node_id = taskNodeId;
    }
    const data = await api.get(`/projects/${projectId.value}/work-session-events`, {
      params,
    });
    selectedRequirementNodeEvents.value = Array.isArray(data?.items)
      ? data.items.map((item) => normalizeProjectWorkEvent(item))
      : [];
  } catch (err) {
    selectedRequirementNodeEvents.value = [];
    ElMessage.error(err?.detail || err?.message || "加载节点工作细节失败");
  } finally {
    requirementNodeDetailLoading.value = false;
  }
}

function openMemoryLinkedWorkSession() {
  const linkedSession = selectedMemoryDetail.value?.linked_work_session;
  const fallbackSessionId = String(selectedMemoryDetail.value?.execution_session_id || "").trim();
  if (linkedSession?.session_id) {
    void openWorkSessionDetail(linkedSession);
    return;
  }
  if (!fallbackSessionId) return;
  void openWorkSessionDetail({
    session_id: fallbackSessionId,
    employee_id: selectedMemoryDetail.value?.employee_id || "",
    employee_name: selectedMemoryDetail.value?.employee_name || "",
  });
}

async function fetchProjectUsers(targetProjectId = projectId.value) {
  const effectiveProjectId = String(targetProjectId || "").trim();
  if (!effectiveProjectId) return;
  const data = await api.get(`/projects/${effectiveProjectId}/users`);
  if (effectiveProjectId !== projectId.value) return;
  projectUsers.value = data.members || [];
  userOptions.value = data.all_users || [];
  canManageProjectUsers.value = !!data.can_manage;
}

async function fetchMembers(targetProjectId = projectId.value) {
  const effectiveProjectId = String(targetProjectId || "").trim();
  if (!effectiveProjectId) return;
  const data = await api.get(`/projects/${effectiveProjectId}/members`);
  if (effectiveProjectId !== projectId.value) return;
  members.value = data.members || [];
}

async function fetchProjectTaskSessions(targetProjectId = projectId.value) {
  const effectiveProjectId = String(targetProjectId || "").trim();
  if (!effectiveProjectId) return;
  taskSessionsLoading.value = true;
  try {
    const data = await api.get(`/projects/${effectiveProjectId}/chat/task-tree/sessions`, {
      params: { limit: PROJECT_TASK_SESSION_FETCH_LIMIT },
    });
    if (effectiveProjectId !== projectId.value) return;
    projectTaskSessions.value = Array.isArray(data.items) ? data.items : [];
    taskTreeStorageBackend.value = String(data.storage_backend || "").trim();
    const validSessionIds = new Set(
      (projectTaskSessions.value || [])
        .map((item) => String(item?.id || "").trim())
        .filter(Boolean),
    );
    projectTaskTreeDetails.value = Object.fromEntries(
      Object.entries(projectTaskTreeDetails.value || {}).filter(([sessionId]) => validSessionIds.has(sessionId)),
    );
  } catch (err) {
    if (effectiveProjectId !== projectId.value) return;
    projectTaskSessions.value = [];
    projectTaskTreeDetails.value = {};
    taskTreeStorageBackend.value = "";
    ElMessage.error(err?.detail || err?.message || "加载任务推进列表失败");
  } finally {
    if (effectiveProjectId === projectId.value) {
      taskSessionsLoading.value = false;
    }
  }
}

async function fetchRequirementRecords(targetProjectId = projectId.value) {
  const effectiveProjectId = String(targetProjectId || "").trim();
  if (!effectiveProjectId) return;
  taskSessionsLoading.value = true;
  requirementRecordsLoaded.value = false;
  try {
    const query = String(memoryFilters.value.query || "").trim();
    const selectedEmployeeId = String(memoryFilters.value.employeeId || "").trim();
    const selectedType = String(memoryFilters.value.type || "").trim();
    const data = await api.get(`/projects/${effectiveProjectId}/requirement-records`, {
      params: {
        limit: PROJECT_TASK_SESSION_FETCH_LIMIT,
        query: query || undefined,
        employee_id: selectedEmployeeId || undefined,
        memory_type: selectedType || undefined,
      },
    });
    if (effectiveProjectId !== projectId.value) return;
    projectRequirementRecords.value = Array.isArray(data?.items) ? data.items : [];
    projectTaskSessions.value = Array.isArray(data?.task_sessions) ? data.task_sessions : [];
    taskTreeStorageBackend.value = String(data?.storage_backend || "").trim();
    const validSessionIds = new Set(
      (projectTaskSessions.value || [])
        .map((item) => String(item?.id || "").trim())
        .filter(Boolean),
    );
    projectTaskTreeDetails.value = Object.fromEntries(
      Object.entries(projectTaskTreeDetails.value || {}).filter(([sessionId]) => validSessionIds.has(sessionId)),
    );
  } catch (err) {
    if (effectiveProjectId !== projectId.value) return;
    projectRequirementRecords.value = [];
    projectTaskSessions.value = [];
    projectTaskTreeDetails.value = {};
    taskTreeStorageBackend.value = "";
    ElMessage.error(err?.detail || err?.message || "加载需求记录失败");
  } finally {
    if (effectiveProjectId === projectId.value) {
      requirementRecordsLoaded.value = true;
      taskSessionsLoading.value = false;
    }
  }
}

async function fetchProjectWorkSessions(targetProjectId = projectId.value) {
  const effectiveProjectId = String(targetProjectId || "").trim();
  if (!effectiveProjectId) return;
  workSessionLoading.value = true;
  try {
    const query = String(memoryFilters.value.query || "").trim();
    const limitValue = Number(memoryFilters.value.limit || 20);
    const safeLimit = Number.isFinite(limitValue) && limitValue > 0 ? limitValue : 20;
    const selectedEmployeeId = String(memoryFilters.value.employeeId || "").trim();
    const params = { limit: safeLimit };
    if (query) {
      params.query = query;
    }
    if (selectedEmployeeId) {
      params.employee_id = selectedEmployeeId;
    }
    const data = await api.get(`/projects/${effectiveProjectId}/work-sessions`, { params });
    if (effectiveProjectId !== projectId.value) return;
    projectWorkSessions.value = Array.isArray(data?.items)
      ? data.items.map((item) => normalizeWorkSessionSummary(item))
      : [];
  } catch (err) {
    if (effectiveProjectId !== projectId.value) return;
    ElMessage.error(err?.detail || err?.message || "加载工作轨迹失败");
    projectWorkSessions.value = [];
  } finally {
    if (effectiveProjectId === projectId.value) {
      workSessionLoading.value = false;
    }
  }
}

function normalizeMemory(memory, employeeId = "") {
  const currentEmployeeId = String(memory?.employee_id || employeeId || "").trim();
  const scope = String(memory?.scope || "").trim();
  const purposeTags = Array.isArray(memory?.purpose_tags)
    ? memory.purpose_tags
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  const chatSessionId = extractMemoryChatSessionId(memory, purposeTags);
  const trajectory = parseMemoryTrajectory(memory?.content || "");
  const employeeName =
    scope === "team-shared"
      ? "团队共享"
      : memberNameMap.value.get(currentEmployeeId) || "";
  return {
    id: String(memory?.id || ""),
    employee_id: currentEmployeeId,
    employee_name: employeeName,
    project_name: String(memory?.project_name || ""),
    type: String(memory?.type || ""),
    content: String(memory?.content || ""),
    importance: Number(memory?.importance ?? 0),
    scope,
    classification: String(memory?.classification || ""),
    purpose_tags: purposeTags,
    access_count: Number(memory?.access_count ?? 0),
    last_accessed: String(memory?.last_accessed || ""),
    ttl_days: Number(memory?.ttl_days ?? 0),
    related_rules: Array.isArray(memory?.related_rules)
      ? memory.related_rules.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    related_memories: Array.isArray(memory?.related_memories)
      ? memory.related_memories.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    expires_at: String(memory?.expires_at || ""),
    chat_session_id: chatSessionId,
    task_tree_session_id: String(memory?.task_tree_session_id || trajectory?.task_tree_session_id || "").trim(),
    task_tree_chat_session_id: String(memory?.task_tree_chat_session_id || trajectory?.task_tree_chat_session_id || "").trim(),
    task_node_id: String(memory?.task_node_id || trajectory?.task_node_id || "").trim(),
    task_node_title: String(memory?.task_node_title || trajectory?.task_node_title || "").trim(),
    trajectory,
    created_at: String(memory?.created_at || ""),
  };
}

function normalizeWorkSessionSummary(session) {
  const currentEmployeeId = String(session?.employee_id || "").trim();
  return {
    session_id: String(session?.session_id || "").trim(),
    project_id: String(session?.project_id || "").trim(),
    project_name: String(session?.project_name || "").trim(),
    employee_id: currentEmployeeId,
    employee_name:
      String(session?.employee_name || "").trim()
      || memberNameMap.value.get(currentEmployeeId)
      || currentEmployeeId,
    latest_status: String(session?.latest_status || "").trim(),
    latest_event_type: String(session?.latest_event_type || "").trim(),
    goal: String(session?.goal || "").trim(),
    task_tree_session_id: String(session?.task_tree_session_id || "").trim(),
    task_tree_chat_session_id: String(session?.task_tree_chat_session_id || "").trim(),
    task_node_id: String(session?.task_node_id || "").trim(),
    task_node_title: String(session?.task_node_title || "").trim(),
    task_tree_session_ids: Array.isArray(session?.task_tree_session_ids)
      ? session.task_tree_session_ids.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    task_node_titles: Array.isArray(session?.task_node_titles)
      ? session.task_node_titles.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    phases: Array.isArray(session?.phases)
      ? session.phases.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    steps: Array.isArray(session?.steps)
      ? session.steps.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    event_types: Array.isArray(session?.event_types)
      ? session.event_types.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    changed_files: Array.isArray(session?.changed_files)
      ? session.changed_files.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    verification: Array.isArray(session?.verification)
      ? session.verification.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    risks: Array.isArray(session?.risks)
      ? session.risks.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    next_steps: Array.isArray(session?.next_steps)
      ? session.next_steps.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    event_count: Number(session?.event_count || 0),
    updated_at: String(session?.updated_at || ""),
    created_at: String(session?.created_at || ""),
  };
}

function normalizeProjectWorkEvent(item) {
  const currentEmployeeId = String(item?.employee_id || "").trim();
  const facts = Array.isArray(item?.facts)
    ? item.facts.map((entry) => String(entry || "").trim()).filter(Boolean)
    : [];
  const verification = Array.isArray(item?.verification)
    ? item.verification.map((entry) => String(entry || "").trim()).filter(Boolean)
    : [];
  return {
    id: String(item?.id || "").trim(),
    session_id: String(item?.session_id || "").trim(),
    project_id: String(item?.project_id || "").trim(),
    project_name: String(item?.project_name || "").trim(),
    employee_id: currentEmployeeId,
    employee_name:
      String(item?.employee_name || "").trim()
      || memberNameMap.value.get(currentEmployeeId)
      || currentEmployeeId
      || "团队协作",
    source_kind: String(item?.source_kind || "").trim(),
    event_type: String(item?.event_type || "").trim(),
    phase: String(item?.phase || "").trim(),
    step: String(item?.step || "").trim(),
    status: String(item?.status || "").trim(),
    goal: String(item?.goal || "").trim(),
    content: String(item?.content || "").trim(),
    facts,
    verification,
    task_tree_session_id: String(item?.task_tree_session_id || "").trim(),
    task_tree_chat_session_id: String(item?.task_tree_chat_session_id || "").trim(),
    task_node_id: String(item?.task_node_id || "").trim(),
    task_node_title: String(item?.task_node_title || "").trim(),
    created_at: String(item?.created_at || "").trim(),
  };
}

function summarizeProjectWorkEvent(item) {
  return (
    String(item?.content || "").trim()
    || (Array.isArray(item?.facts) ? item.facts.join(" / ") : "")
    || String(item?.goal || "").trim()
    || "-"
  );
}

function getMemoryDetailNodeWorkEvents(node) {
  const nodeId = String(node?.id || "").trim();
  return memoryDetailWorkEventsByNodeId.value.get(nodeId) || [];
}

function parseMemorySections(content) {
  const text = String(content || "");
  return {
    question:
      text.match(/\[(?:用户问题|用户提问)\]\s*([\s\S]*?)(?:\n\[[^\n]+\]|$)/)?.[1]?.trim() || "",
    process:
      text.match(/\[(?:处理过程|过程摘要)\]\s*([\s\S]*?)(?:\n\[[^\n]+\]|$)/)?.[1]?.trim() || "",
    solution:
      text.match(/\[解决方案\]\s*([\s\S]*?)(?:\n\[[^\n]+\]|$)/)?.[1]?.trim() || "",
    conclusion:
      text.match(/\[最终结论\]\s*([\s\S]*?)(?:\n\[[^\n]+\]|$)/)?.[1]?.trim() || "",
    solveStatus:
      text.match(/\[解决状态\]\s*([\s\S]*?)(?:\n\[[^\n]+\]|$)/)?.[1]?.trim() || "",
    chatSessionId:
      text.match(/\[关联会话\]\s*([^\n]+)/)?.[1]?.trim() || "",
  };
}

function parseMemoryTrajectory(content) {
  const text = String(content || "");
  const matched = text.match(/\[执行轨迹JSON\]\s*([^\n]+)/);
  if (!matched?.[1]) {
    return {};
  }
  try {
    const decoded = JSON.parse(matched[1]);
    return decoded && typeof decoded === "object" ? decoded : {};
  } catch {
    return {};
  }
}

function clipText(value, limit = 120) {
  const text = String(value || "").trim();
  if (!text) return "";
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(1, limit - 1))}…`;
}

function getTaskTreeRootNode(taskTree) {
  const nodes = Array.isArray(taskTree?.nodes) ? taskTree.nodes : [];
  return nodes.find((item) => Number(item?.level || 0) === 0) || null;
}

function isTaskTreeRootNode(node, round = null) {
  if (!node || typeof node !== "object") return false;
  const nodeId = String(node?.id || "").trim();
  const roundRootId = String(round?.rootNode?.id || round?.taskTree?.tree?.[0]?.id || "").trim();
  if (nodeId && roundRootId) {
    return nodeId === roundRootId;
  }
  const parentId = String(node?.parent_id || "").trim();
  if (!parentId) {
    return Number(node?.level || 0) === 0;
  }
  return false;
}

function extractAnswerSummaryFromText(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const matched = text.match(/回答摘要[:：]\s*([\s\S]*?)(?:\s+(?:执行证据|问题目标)[:：]|$)/);
  return matched?.[1]?.trim() || "";
}

function extractTaskTreeFallbackText(taskTree) {
  if (!taskTree || typeof taskTree !== "object") {
    return "";
  }
  const rootNode = getTaskTreeRootNode(taskTree);
  const nodes = Array.isArray(taskTree?.nodes) ? taskTree.nodes : [];
  const completedLeafNodes = nodes.filter((item) => {
    const level = Number(item?.level || 0);
    const status = String(item?.status || "").trim().toLowerCase();
    return level > 0 && status === "done";
  });
  const candidates = [
    extractAnswerSummaryFromText(rootNode?.verification_result),
    extractAnswerSummaryFromText(completedLeafNodes[0]?.verification_result),
    String(rootNode?.verification_result || "").trim(),
    String(completedLeafNodes[0]?.summary_for_model || "").trim(),
    String(completedLeafNodes[0]?.verification_result || "").trim(),
  ];
  return candidates.find((item) => String(item || "").trim()) || "";
}

function summarizeMemoryFallbackWorkEvent(events) {
  const items = Array.isArray(events) ? events.filter(Boolean) : [];
  if (!items.length) {
    return "";
  }
  const ranked = items.slice().sort((left, right) => {
    const leftDone = ["completed", "done"].includes(String(left?.status || "").trim().toLowerCase());
    const rightDone = ["completed", "done"].includes(String(right?.status || "").trim().toLowerCase());
    if (leftDone !== rightDone) {
      return rightDone ? 1 : -1;
    }
    return String(right?.created_at || "").localeCompare(String(left?.created_at || ""));
  });
  for (const item of ranked) {
    const factSummary = Array.isArray(item?.facts)
      ? item.facts.map((entry) => String(entry || "").trim()).filter(Boolean).join(" / ")
      : "";
    const verificationSummary = Array.isArray(item?.verification)
      ? item.verification.map((entry) => String(entry || "").trim()).filter(Boolean).join(" / ")
      : "";
    const contentSummary = String(item?.content || "").trim();
    const goalSummary = String(item?.goal || "").trim();
    const summary = factSummary || verificationSummary || contentSummary || goalSummary;
    if (summary) {
      return summary;
    }
  }
  return "";
}

function deriveMemorySolveStatus(memory, linkedTask, linkedWorkSession, sections) {
  const explicit = String(sections?.solveStatus || "").trim();
  if (explicit.includes("已解决")) return "resolved";
  if (explicit.includes("部分")) return "partial";
  if (explicit.includes("阻塞") || explicit.includes("未解决")) return "unresolved";
  const taskStatus = String(linkedTask?.status || "").trim().toLowerCase();
  if (taskStatus === "done") return "resolved";
  if (taskStatus === "blocked") return "unresolved";
  if (taskStatus === "verifying" || taskStatus === "in_progress") return "processing";
  const workSessionStatus = String(linkedWorkSession?.latest_status || "").trim().toLowerCase();
  if (workSessionStatus === "completed" || workSessionStatus === "done") return "resolved";
  if (workSessionStatus === "blocked" || workSessionStatus === "failed") return "unresolved";
  if (workSessionStatus === "verifying" || workSessionStatus === "in_progress") return "processing";
  if (memory?.chat_session_id) return "tracked";
  return "untracked";
}

function isAutoQuestionSnapshot(memory) {
  const tags = new Set(
    (Array.isArray(memory?.purpose_tags) ? memory.purpose_tags : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  );
  return tags.has("auto-capture") && tags.has("user-question");
}

function isInternalAutoQuestionSnapshot(memory) {
  if (!isAutoQuestionSnapshot(memory)) {
    return false;
  }
  const tags = new Set(
    (Array.isArray(memory?.purpose_tags) ? memory.purpose_tags : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  );
  return [
    "mcp:tools/call:bind_project_context",
    "mcp:tools/call:start_work_session",
    "mcp:tools/call:save_work_facts",
    "mcp:tools/call:append_session_event",
    "mcp:tools/call:resume_work_session",
    "mcp:tools/call:summarize_checkpoint",
    "mcp:tools/call:list_recent_project_requirements",
    "mcp:tools/call:get_requirement_history",
    "mcp:tools/call:build_delivery_report",
    "mcp:tools/call:generate_release_note_entry",
    "mcp:tools/call:save_project_memory",
  ].some((tag) => tags.has(tag));
}

function isInternalAutoQueryResultSnapshot(memory) {
  const tags = new Set(
    (Array.isArray(memory?.purpose_tags) ? memory.purpose_tags : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  );
  if (!tags.has("auto-capture") || !tags.has("query-result")) {
    return false;
  }
  return Array.from(INTERNAL_AUTO_QUERY_RESULT_TOOL_TAGS).some((tag) => tags.has(tag));
}

function hasConversationMemorySections(sections) {
  return Boolean(
    String(sections?.question || "").trim() ||
      String(sections?.process || "").trim() ||
      String(sections?.solution || "").trim() ||
      String(sections?.conclusion || "").trim() ||
      String(sections?.solveStatus || "").trim(),
  );
}

function getProjectMemoryGroupKey(memory, sections) {
  const chatSessionId = String(memory?.chat_session_id || "").trim();
  const question = String(sections?.question || "").trim();
  if (chatSessionId && question) {
    return `chat:${chatSessionId}:question:${question}`;
  }
  if (chatSessionId) {
    return `chat:${chatSessionId}`;
  }
  if (question) {
    return `question:${question}`;
  }
  return `memory:${String(memory?.id || "").trim()}`;
}

function getProjectMemoryDisplayScore(memory, sections) {
  let score = 0;
  const tags = new Set(
    (Array.isArray(memory?.purpose_tags) ? memory.purpose_tags : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  );
  if (hasConversationMemorySections(sections)) score += 10;
  if (tags.has("manual-write")) score += 8;
  if (!isAutoQuestionSnapshot(memory)) score += 4;
  if (String(memory?.chat_session_id || "").trim()) score += 2;
  score += Number(memory?.importance || 0);
  return score;
}

function pickPrimaryProjectMemory(items) {
  const candidates = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!candidates.length) return null;
  return candidates
    .slice()
    .sort((left, right) => {
      const leftSections = parseMemorySections(left.content || "");
      const rightSections = parseMemorySections(right.content || "");
      const scoreDiff = getProjectMemoryDisplayScore(right, rightSections) - getProjectMemoryDisplayScore(left, leftSections);
      if (scoreDiff !== 0) {
        return scoreDiff;
      }
      return String(right?.created_at || "").localeCompare(String(left?.created_at || ""));
    })[0];
}

function shouldDisplayRawMemoryContent(memory, sections) {
  const text = String(memory?.content || "").trim();
  if (!text) {
    return false;
  }
  if (isAutoQuestionSnapshot(memory)) {
    return false;
  }
  return !hasConversationMemorySections(sections);
}

function isTransientQuestionSnapshot(memory, sections) {
  if (!isAutoQuestionSnapshot(memory)) {
    return false;
  }
  return !(
    String(sections?.process || "").trim() ||
    String(sections?.solution || "").trim() ||
    String(sections?.conclusion || "").trim() ||
    String(memory?.chat_session_id || "").trim()
  );
}

function isTrajectoryMemory(memory) {
  const tags = new Set(
    (Array.isArray(memory?.purpose_tags) ? memory.purpose_tags : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  );
  if (tags.has("work-facts") || tags.has("session-event")) {
    return true;
  }
  const text = String(memory?.content || "").trim();
  return text.startsWith("[工作事实]") || text.startsWith("[会话事件]");
}

function normalizeTaskTreeNode(node) {
  if (!node || typeof node !== "object") {
    return null;
  }
  const verificationMethod = Array.isArray(node.verification_method)
    ? node.verification_method
    : Array.isArray(node.verification_items)
      ? node.verification_items
      : [];
  return {
    ...node,
    node_kind: String(node.node_kind || (Number(node.level || 0) === 0 ? "goal" : "plan_step")).trim(),
    stage_key: String(node.stage_key || "").trim(),
    objective: String(node.objective || node.description || "").trim(),
    completion_criteria: String(node.completion_criteria || node.done_definition || "").trim(),
    verification_method: verificationMethod
      .map((item) => String(item || "").trim())
      .filter(Boolean),
    latest_outcome: String(
      node.latest_outcome
      || node.summary_for_model
      || node.verification_result
      || "",
    ).trim(),
    children: Array.isArray(node.children)
      ? node.children.map((item) => normalizeTaskTreeNode(item)).filter(Boolean)
      : [],
  };
}

function normalizeTaskTreePayload(taskTree) {
  if (!taskTree || typeof taskTree !== "object") {
    return null;
  }
  const nodes = Array.isArray(taskTree.nodes)
    ? taskTree.nodes.map((item) => normalizeTaskTreeNode(item)).filter(Boolean)
    : [];
  const tree = Array.isArray(taskTree.tree)
    ? taskTree.tree.map((item) => normalizeTaskTreeNode(item)).filter(Boolean)
    : [];
  const currentNodeId = String(taskTree.current_node_id || "").trim();
  const stats = taskTree.stats && typeof taskTree.stats === "object" ? taskTree.stats : {};
  const normalizedCurrentNode = normalizeTaskTreeNode(taskTree.current_node);
  return {
    ...taskTree,
    current_node_id: currentNodeId,
    progress_percent: resolveTaskTreeProgressPercent(taskTree),
    node_total: Number(taskTree.node_total ?? stats.node_total ?? nodes.length),
    leaf_total: Number(taskTree.leaf_total ?? stats.leaf_total ?? 0),
    done_leaf_total: Number(taskTree.done_leaf_total ?? stats.done_leaf_total ?? 0),
    nodes,
    tree,
    task_tree_health: normalizeTaskTreeHealth(taskTree.task_tree_health),
    current_node:
      normalizedCurrentNode
        ? normalizedCurrentNode
        : nodes.find((item) => String(item?.id || "").trim() === currentNodeId) || null,
  };
}

function resolveTaskTreeResponsePayload(payload) {
  if (!payload || typeof payload !== "object") {
    return payload ?? null;
  }
  if (payload.task_tree && typeof payload.task_tree === "object") {
    return payload.task_tree;
  }
  if (payload.history_task_tree && typeof payload.history_task_tree === "object") {
    return payload.history_task_tree;
  }
  if (
    Object.prototype.hasOwnProperty.call(payload, "task_tree")
    || Object.prototype.hasOwnProperty.call(payload, "history_task_tree")
  ) {
    return null;
  }
  return payload;
}

function getMemorySolveStatusLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "resolved") return "已解决";
  if (normalized === "partial") return "部分解决";
  if (normalized === "unresolved") return "未解决";
  if (normalized === "processing") return "处理中";
  if (normalized === "tracked") return "已记录";
  return "未关联";
}

function getMemorySolveStatusTagType(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "resolved") return "success";
  if (normalized === "partial") return "warning";
  if (normalized === "unresolved") return "danger";
  if (normalized === "processing") return "";
  if (normalized === "tracked") return "info";
  return "info";
}

function extractMemoryChatSessionId(memory, purposeTags = []) {
  const fromTag = purposeTags.find((item) => item.startsWith("chat-session:"));
  if (fromTag) {
    return String(fromTag.slice("chat-session:".length) || "").trim();
  }
  return parseMemorySections(memory?.content || "").chatSessionId;
}

function getMemoryTypeLabel(type) {
  const key = String(type || "").trim();
  return MEMORY_TYPE_LABELS[key] || key || "-";
}

function buildMemoryExportFilename() {
  const projectName = String(project.value?.name || projectId.value || "project").trim() || "project";
  const safeProjectName = projectName.replace(/[\\/:*?"<>|]+/g, "-");
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `${safeProjectName}-project-memories-${timestamp}.csv`;
}

function escapeCsvField(value) {
  const text = String(value ?? "");
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function buildMemoryExportCsv(rows) {
  const headers = ["员工", "员工ID", "类型", "内容", "重要度", "作用域", "项目名称", "创建时间"];
  const lines = rows.map((row) =>
    [
      row.employee_name || row.employee_id || "",
      row.employee_id || "",
      getMemoryTypeLabel(row.type),
      row.content || "",
      row.importance ?? "",
      row.scope || "",
      row.project_name || "",
      row.created_at || "",
    ]
      .map((item) => escapeCsvField(item))
      .join(","),
  );
  return `\uFEFF${headers.join(",")}\n${lines.join("\n")}`;
}

function downloadTextFile(content, filename, mimeType = "text/plain;charset=utf-8;") {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function exportProjectMemories() {
  await Promise.all([
    fetchProjectMemories(projectId.value),
    fetchProjectWorkSessions(projectId.value),
  ]);
  if (!filteredMemoryRows.value.length) {
    ElMessage.warning("暂无可导出的项目记忆");
    return;
  }
  try {
    const content = buildMemoryExportCsv(filteredMemoryRows.value);
    downloadTextFile(content, buildMemoryExportFilename(), "text/csv;charset=utf-8;");
    ElMessage.success(`已导出 ${filteredMemoryRows.value.length} 条项目记忆`);
  } catch {
    ElMessage.error("导出项目记忆失败");
  }
}

async function fetchProjectMemories(targetProjectId = projectId.value) {
  const effectiveProjectId = String(targetProjectId || "").trim();
  if (!effectiveProjectId) return;
  memoryLoading.value = true;
  try {
    const query = String(memoryFilters.value.query || "").trim();
    const limitValue = Number(memoryFilters.value.limit || 20);
    const safeLimit = Number.isFinite(limitValue) && limitValue > 0 ? limitValue : 20;
    const selectedEmployeeId = String(memoryFilters.value.employeeId || "").trim();
    const params = { limit: safeLimit };
    if (query) {
      params.query = query;
    }
    if (selectedEmployeeId) {
      params.employee_id = selectedEmployeeId;
    }
    const data = await api.get(`/projects/${effectiveProjectId}/memories`, { params });
    if (effectiveProjectId !== projectId.value) return;
    projectMemories.value = Array.isArray(data?.items)
      ? data.items.map((item) => normalizeMemory(item))
      : [];
    projectMemoryTotal.value = Number(data?.total || 0);
    projectMemoryHasMore.value = Boolean(data?.has_more);
  } catch (err) {
    if (effectiveProjectId !== projectId.value) return;
    ElMessage.error(err?.detail || err?.message || "加载项目记忆失败");
    projectMemories.value = [];
    projectMemoryTotal.value = 0;
    projectMemoryHasMore.value = false;
  } finally {
    if (effectiveProjectId === projectId.value) {
      memoryLoading.value = false;
    }
  }
}

async function applyMemoryFilters(targetProjectId = projectId.value) {
  await fetchRequirementRecords(targetProjectId);
}

async function refreshRequirementRecords() {
  await ensureMemoryTabData(projectId.value, { force: true });
}

async function handleClearRequirementRecordTaskTree(record) {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  const chatSessionId = getRequirementRecordActionChatSessionId(record);
  if (!chatSessionId) {
    ElMessage.warning("当前需求没有可清空的任务树会话");
    return;
  }
  try {
    await ElMessageBox.confirm(
      "清空后只会删除当前 chat_session 对应的任务树，需求记录本身仍会保留，后续可以重新生成。是否继续？",
      "清空任务树",
      {
        type: "warning",
        confirmButtonText: "清空",
      },
    );
  } catch {
    return;
  }
  const actionKey = getRequirementRecordActionKey(record);
  requirementRecordTaskTreeClearingMap.value = {
    ...requirementRecordTaskTreeClearingMap.value,
    [actionKey]: true,
  };
  try {
    await api.delete(`/projects/${projectId.value}/chat/task-tree`, {
      params: { chat_session_id: chatSessionId },
    });
    pruneRequirementRecordTaskTreeDetails(record);
    ElMessage.success("已清空任务树");
    await refreshRequirementRecords();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "清空任务树失败");
  } finally {
    const nextMap = { ...(requirementRecordTaskTreeClearingMap.value || {}) };
    delete nextMap[actionKey];
    requirementRecordTaskTreeClearingMap.value = nextMap;
  }
}

async function handleRegenerateRequirementRecordTaskTree(record) {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  const chatSessionId = getRequirementRecordActionChatSessionId(record);
  const rootGoal = getRequirementRecordActionRootGoal(record);
  if (!chatSessionId || !rootGoal) {
    ElMessage.warning("当前需求缺少 chat_session_id 或根目标，无法重建任务树");
    return;
  }
  try {
    await ElMessageBox.confirm(
      "会基于当前需求重新生成任务树，并覆盖现有节点结构。适合处理分类错乱、空挂或重建建议场景。",
      "重建任务树",
      {
        type: "warning",
        confirmButtonText: "重建",
      },
    );
  } catch {
    return;
  }
  const actionKey = getRequirementRecordActionKey(record);
  requirementRecordTaskTreeRegeneratingMap.value = {
    ...requirementRecordTaskTreeRegeneratingMap.value,
    [actionKey]: true,
  };
  try {
    await api.post(`/projects/${projectId.value}/chat/task-tree/generate`, {
      chat_session_id: chatSessionId,
      message: rootGoal,
      force: true,
    });
    pruneRequirementRecordTaskTreeDetails(record);
    ElMessage.success("已重建任务树");
    await refreshRequirementRecords();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "重建任务树失败");
  } finally {
    const nextMap = { ...(requirementRecordTaskTreeRegeneratingMap.value || {}) };
    delete nextMap[actionKey];
    requirementRecordTaskTreeRegeneratingMap.value = nextMap;
  }
}

async function deleteRequirementRecords(recordIds, successLabel = "需求记录") {
  const normalizedIds = [...new Set(
    (Array.isArray(recordIds) ? recordIds : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  )];
  if (!normalizedIds.length) {
    ElMessage.warning("请先选择要删除的需求记录");
    return null;
  }
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return null;
  }
  requirementRecordDeleting.value = true;
  try {
    const data = await api.post(`/projects/${projectId.value}/requirement-records/batch-delete`, {
      record_ids: normalizedIds,
    });
    const deletedIds = Array.isArray(data?.deleted_record_ids) ? data.deleted_record_ids : [];
    selectedRequirementRecordIds.value = (selectedRequirementRecordIds.value || []).filter(
      (item) => !deletedIds.includes(item),
    );
    if (expandedRequirementRecordId.value && deletedIds.includes(expandedRequirementRecordId.value)) {
      expandedRequirementRecordId.value = "";
    }
    const deletedCount = Number(data?.deleted_count || 0);
    if (deletedCount > 0) {
      ElMessage.success(`已删除 ${deletedCount} 条${successLabel}`);
    } else {
      ElMessage.warning("没有可删除的需求记录");
    }
    await refreshRequirementRecords();
    return data;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除需求记录失败");
    return null;
  } finally {
    requirementRecordDeleting.value = false;
  }
}

async function handleDeleteRequirementRecord(record) {
  if (!record?.id) return;
  try {
    await ElMessageBox.confirm(
      "删除后将同时移除该需求链关联的任务树、工作轨迹与记忆记录，是否继续？",
      "确认删除",
      {
        type: "warning",
        confirmButtonText: "删除",
      },
    );
  } catch {
    return;
  }
  await deleteRequirementRecords([record.id], "需求记录");
}

async function handleBatchDeleteRequirementRecords() {
  const selectedIds = visibleRequirementRecordIds.value.filter((item) =>
    selectedRequirementRecordIdSet.value.has(item),
  );
  if (!selectedIds.length) {
    ElMessage.warning("请先选择要删除的需求记录");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定删除已选中的 ${selectedIds.length} 条需求记录吗？这会同时清理关联的任务树、工作轨迹与记忆。`,
      "批量删除",
      {
        type: "warning",
        confirmButtonText: "删除",
      },
    );
  } catch {
    return;
  }
  await deleteRequirementRecords(selectedIds, "需求记录");
}

async function handleDeleteAllRequirementRecords() {
  const currentIds = visibleRequirementRecordIds.value.slice();
  if (!currentIds.length) {
    ElMessage.warning("当前筛选结果下没有可删除的需求记录");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定删除当前筛选结果中的 ${currentIds.length} 条需求记录吗？这只会删除当前列表结果，并同步清理关联的任务树、工作轨迹与记忆。`,
      "删除当前结果",
      {
        type: "warning",
        confirmButtonText: "删除",
      },
    );
  } catch {
    return;
  }
  await deleteRequirementRecords(currentIds, "需求记录");
}

async function resetMemoryFilters() {
  memoryFilters.value = {
    query: "",
    employeeId: "",
    type: "",
    limit: 20,
  };
  await applyMemoryFilters();
}

function setTabDataLoaded(tab, loaded = true) {
  tabDataLoaded.value = {
    ...tabDataLoaded.value,
    [tab]: loaded,
  };
}

async function ensureOverviewTabData(targetProjectId = projectId.value, options = {}) {
  const force = Boolean(options?.force);
  if (!force && tabDataLoaded.value.overview) {
    return;
  }
  if (tabDataPromises.overview) {
    return tabDataPromises.overview;
  }
  tabDataPromises.overview = (async () => {
    await fetchRules();
    setTabDataLoaded("overview", true);
  })().finally(() => {
    tabDataPromises.overview = null;
  });
  return tabDataPromises.overview;
}

async function ensureAccessTabData(targetProjectId = projectId.value, options = {}) {
  const force = Boolean(options?.force);
  if (!force && tabDataLoaded.value.access) {
    return;
  }
  if (tabDataPromises.access) {
    return tabDataPromises.access;
  }
  tabDataPromises.access = (async () => {
    await Promise.all([
      fetchProjectUsers(targetProjectId),
      fetchMembers(targetProjectId),
      fetchEmployees(),
    ]);
    setTabDataLoaded("access", true);
  })().finally(() => {
    tabDataPromises.access = null;
  });
  return tabDataPromises.access;
}

async function ensureMemoryTabData(targetProjectId = projectId.value, options = {}) {
  const force = Boolean(options?.force);
  if (!force && tabDataLoaded.value.memory) {
    return;
  }
  if (tabDataPromises.memory) {
    return tabDataPromises.memory;
  }
  tabDataPromises.memory = (async () => {
    await Promise.all([
      fetchMembers(targetProjectId),
      fetchRequirementRecords(targetProjectId),
    ]);
    setTabDataLoaded("memory", true);
  })().finally(() => {
    tabDataPromises.memory = null;
  });
  return tabDataPromises.memory;
}

async function ensureProjectTabData(tab = activeProjectTab.value, targetProjectId = projectId.value, options = {}) {
  const normalizedTab = normalizeProjectDetailTab(tab);
  const effectiveProjectId = String(targetProjectId || "").trim();
  if (!effectiveProjectId) {
    return;
  }
  if (normalizedTab === "memory") {
    await ensureMemoryTabData(effectiveProjectId, options);
    return;
  }
  if (normalizedTab === "access") {
    await ensureAccessTabData(effectiveProjectId, options);
    return;
  }
  await ensureOverviewTabData(effectiveProjectId, options);
}

async function refresh(targetProjectId = projectId.value) {
  const effectiveProjectId = String(targetProjectId || "").trim();
  if (!effectiveProjectId) return;
  loading.value = true;
  try {
    await fetchProject(effectiveProjectId);
    await ensureProjectTabData(route.query.tab || activeProjectTab.value, effectiveProjectId, {
      force: true,
    });
  } catch (err) {
    if (effectiveProjectId !== projectId.value) return;
    const message = err?.detail || err?.message || "加载失败";
    ElMessage.error(message);
    if (String(err?.detail || "").includes("Project access denied")) {
      router.push("/projects");
    }
  } finally {
    if (effectiveProjectId === projectId.value) {
      loading.value = false;
    }
  }
}

function openProjectChat(chatSessionId = "") {
  const currentProjectId = String(project.value?.id || projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("当前项目 ID 无效");
    return;
  }
  const query = {
    project_id: currentProjectId,
  };
  const normalizedChatSessionId = String(chatSessionId || "").trim();
  if (normalizedChatSessionId) {
    query.chat_session_id = normalizedChatSessionId;
  }
  void router.push({
    path: "/ai/chat",
    query,
  });
}

function openMaterialLibrary() {
  const currentProjectId = String(project.value?.id || projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("当前项目 ID 无效");
    return;
  }
  void router.push({ path: "/materials", query: { project_id: currentProjectId } });
}

function openAddMember() {
  if (!canManageProjectUsers.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  resetAddForm();
  showAddDialog.value = true;
}

function openEmployeeDetail(row) {
  const employeeId = String(row?.employee_id || "").trim();
  if (!employeeId) {
    ElMessage.warning("当前员工 ID 无效");
    return;
  }
  void router.push(`/employees/${employeeId}`);
}

function openAddUserDialog() {
  if (!canManageProjectUsers.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  resetUserForm();
  showAddUserDialog.value = true;
}

function openUiRuleDialog() {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  uiRuleForm.value = {
    rule_ids: normalizeStringList(project.value?.ui_rule_ids || []),
  };
  showUiRuleDialog.value = true;
}

function getExperienceSummaryTargetRecordIds() {
  const selectedIds = visibleRequirementRecordIds.value.filter((item) =>
    selectedRequirementRecordIdSet.value.has(item),
  );
  if (selectedIds.length) {
    return selectedIds;
  }
  return visibleRequirementRecordIds.value.slice();
}

function getExperienceSummaryUnavailableMessage() {
  if (hasActiveRequirementRecordFilters.value) {
    return "当前筛选条件下没有可总结的需求记录，请先清空筛选条件再试。";
  }
  if (boundExperienceRules.value.length) {
    return "当前没有新的需求记录可总结；此前需求记录已沉淀为经验规则，可直接复用、编辑或汇总。";
  }
  return "当前没有可总结的需求记录。";
}

async function openExperienceSummaryDialog() {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  if (!requirementRecordsLoaded.value) {
    await fetchRequirementRecords(projectId.value);
  }
  if (!getExperienceSummaryTargetRecordIds().length) {
    ElMessage.warning(getExperienceSummaryUnavailableMessage());
    return;
  }
  await fetchExperienceProviders();
  if (!experienceProviderOptions.value.length) {
    ElMessage.warning("当前没有可用模型，无法开启开发经验沉淀流程");
    return;
  }
  showExperienceSummaryDialog.value = true;
}

async function openExperienceRuleEditDialog(rule) {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  const ruleId = String(rule?.id || "").trim();
  if (!ruleId) {
    ElMessage.warning("当前经验规则缺少 ID");
    return;
  }
  experienceRuleEditingLoading.value = true;
  editingExperienceRuleId.value = ruleId;
  try {
    const data = await api.get(`/rules/${ruleId}`);
    const currentRule = data?.rule || {};
    experienceRuleEditForm.value = {
      title: stripExperienceRuleTitlePrefix(currentRule.title || rule.title || ""),
      content: String(currentRule.content || "").trim(),
    };
    showExperienceRuleEditDialog.value = true;
  } catch (err) {
    editingExperienceRuleId.value = "";
    ElMessage.error(err?.detail || err?.message || "加载经验规则失败");
  } finally {
    experienceRuleEditingLoading.value = false;
  }
}

async function handleSaveExperienceRuleEdit() {
  const ruleId = String(editingExperienceRuleId.value || "").trim();
  const title = String(experienceRuleEditForm.value.title || "").trim();
  const content = String(experienceRuleEditForm.value.content || "").trim();
  if (!ruleId) {
    ElMessage.warning("当前没有可保存的经验规则");
    return;
  }
  if (!title) {
    ElMessage.warning("请输入经验规则标题");
    return;
  }
  if (!content) {
    ElMessage.warning("请输入经验规则内容");
    return;
  }
  experienceRuleEditSaving.value = true;
  try {
    await api.put(`/projects/${projectId.value}/experience-rules/${ruleId}`, {
      title,
      content,
    });
    await fetchProject();
    ElMessage.success("经验规则已更新");
    editingExperienceRuleId.value = "";
    showExperienceRuleEditDialog.value = false;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存经验规则失败");
  } finally {
    experienceRuleEditSaving.value = false;
  }
}

async function handleDeleteExperienceRule(rule) {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  const ruleId = String(rule?.id || "").trim();
  if (!ruleId) {
    ElMessage.warning("当前经验规则缺少 ID");
    return;
  }
  const scopeLabel = rule?.systemSource === "project_experience" ? "项目私有经验" : "开发经验";
  const deleteMessage = rule?.systemSource === "development_experience"
    ? "如果还有其他项目引用这条开发经验，只会移除当前项目绑定；没有其他引用时才会真正删除规则。"
    : "删除后会从当前项目移除这条项目私有经验规则。";
  try {
    await ElMessageBox.confirm(
      `确定删除「${rule.displayTitle || rule.title || ruleId}」？\n${deleteMessage}`,
      `删除${scopeLabel}`,
      {
        type: "warning",
        confirmButtonText: "删除",
      },
    );
  } catch {
    return;
  }
  experienceRuleDeletingLoading.value = true;
  deletingExperienceRuleId.value = ruleId;
  try {
    const data = await api.delete(`/projects/${projectId.value}/experience-rules/${ruleId}`);
    await fetchProject();
    const remainingCount = Number(data?.remaining_project_binding_count || 0);
    if (data?.rule_deleted) {
      ElMessage.success("经验规则已删除");
    } else if (remainingCount > 0) {
      ElMessage.success(`已移除当前项目引用，该经验仍被 ${remainingCount} 个其他项目使用`);
    } else {
      ElMessage.success("已从当前项目移除经验规则");
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除经验规则失败");
  } finally {
    experienceRuleDeletingLoading.value = false;
    deletingExperienceRuleId.value = "";
  }
}

async function handleMigrateExperienceRulesToDevelopment() {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  if (!hasLegacyProjectExperienceRules.value) {
    ElMessage.warning("当前没有需要迁移的旧项目经验规则");
    return;
  }
  try {
    await ElMessageBox.confirm(
      "会把当前项目下旧的项目私有经验升级为开发经验，并按主题归并到开发经验库；项目仍会保留规则引用。是否继续？",
      "迁移旧项目经验",
      {
        type: "warning",
        confirmButtonText: "开始迁移",
      },
    );
  } catch {
    return;
  }
  experienceRuleMigrating.value = true;
  try {
    const data = await api.post(`/projects/${projectId.value}/experience-rules/migrate-to-development`);
    await fetchProject();
    const createdCount = Array.isArray(data?.created_rule_ids) ? data.created_rule_ids.length : 0;
    const updatedCount = Array.isArray(data?.updated_rule_ids) ? data.updated_rule_ids.length : 0;
    const deletedCount = Array.isArray(data?.deleted_rule_ids) ? data.deleted_rule_ids.length : 0;
    ElMessage.success(
      `迁移完成：新增 ${createdCount} 条，归并更新 ${updatedCount} 条，清理 ${deletedCount} 条旧规则`,
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "迁移旧项目经验失败");
  } finally {
    experienceRuleMigrating.value = false;
  }
}

async function handleConsolidateExperienceRules() {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  if (boundExperienceRules.value.length <= 1) {
    ElMessage.warning("当前经验规则已经是单条，无需再汇总");
    return;
  }
  try {
    await ElMessageBox.confirm(
      "会按主题合并重复经验规则，保留不同主题的规则，并清理多余重复项。是否继续？",
      "汇总经验规则",
      {
        type: "warning",
        confirmButtonText: "开始汇总",
      },
    );
  } catch {
    return;
  }
  experienceRuleConsolidating.value = true;
  try {
    const data = await api.post(`/projects/${projectId.value}/experience-rules/consolidate`);
    await fetchProject();
    const deletedCount = Array.isArray(data?.deleted_rule_ids) ? data.deleted_rule_ids.length : 0;
    const consolidatedCount = Array.isArray(data?.consolidated_rule_ids) ? data.consolidated_rule_ids.length : 0;
    const remainingCount = Number(data?.remaining_rule_count || 0);
    if (!consolidatedCount && !deletedCount) {
      ElMessage.success(`未发现可合并的重复主题，当前保留 ${remainingCount} 条经验规则`);
      return;
    }
    ElMessage.success(`已按主题汇总 ${consolidatedCount} 组经验规则，当前保留 ${remainingCount} 条，清理 ${deletedCount} 条重复规则`);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "汇总经验规则失败");
  } finally {
    experienceRuleConsolidating.value = false;
  }
}

function openEditDialog() {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  editForm.value = {
    name: project.value.name || "",
    description: project.value.description || "",
    type: normalizeProjectType(project.value.type),
    mcp_instruction: project.value.mcp_instruction || "",
    workspace_path: project.value.workspace_path || "",
    ai_entry_file: project.value.ai_entry_file || "",
    mcp_enabled: project.value.mcp_enabled ?? true,
    feedback_upgrade_enabled: project.value.feedback_upgrade_enabled ?? true,
  };
  showEditDialog.value = true;
}

async function selectWorkspaceDirectory() {
  const picked = await pickWorkspaceDirectory(editForm.value.workspace_path);
  if (picked === null) return;
  editForm.value.workspace_path = picked;
}

async function selectAiEntryFile() {
  const picked = await pickAiEntryFile(
    editForm.value.ai_entry_file,
    editForm.value.workspace_path,
  );
  if (picked === null) return;
  editForm.value.ai_entry_file = picked;
}

async function pickWorkspaceDirectory(currentPath = "") {
  return await openWorkspaceDirectoryPicker(currentPath, {
    title: "选择项目工作区目录",
  });
}

async function pickAiEntryFile(currentPath = "", workspacePath = "") {
  const picked = await openWorkspaceFilePicker(currentPath, {
    title: "选择 AI 入口文件",
    placeholder: ".ai/ENTRY.md",
    basePath: workspacePath,
  });
  if (picked === null) return null;
  return toWorkspaceRelativePath(picked, workspacePath) || String(picked || "").trim();
}

async function saveEdit() {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    showEditDialog.value = false;
    return;
  }
  const name = String(editForm.value.name || "").trim();
  if (!name) {
    ElMessage.warning("请输入项目名称");
    return;
  }
  saving.value = true;
  try {
    await api.put(`/projects/${projectId.value}`, editForm.value);
    ElMessage.success("项目已更新");
    showEditDialog.value = false;
    await fetchProject();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "更新失败");
  } finally {
    saving.value = false;
  }
}

async function saveUiRuleBindings() {
  if (!canManageProject.value) {
    ElMessage.warning(manageBlockedMessage());
    showUiRuleDialog.value = false;
    return;
  }
  uiRuleSaving.value = true;
  try {
    await api.put(`/projects/${projectId.value}`, {
      ui_rule_ids: normalizeStringList(uiRuleForm.value.rule_ids || []),
    });
    await fetchProject();
    ElMessage.success("UI 规则绑定已更新");
    showUiRuleDialog.value = false;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存 UI 规则绑定失败");
  } finally {
    uiRuleSaving.value = false;
  }
}

async function showProjectManual() {
  manualLoading.value = true;
  try {
    const data = await api.get(`/projects/${projectId.value}/manual-template`);
    generatedManual.value = data.template || "";
    manualDialogTitle.value = `项目使用手册: ${project.value?.name || projectId.value}`;
    showManualDialog.value = true;
    ElMessage.success("项目使用手册加载成功");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载项目使用手册失败");
  } finally {
    manualLoading.value = false;
  }
}

async function handleConfirmExperienceSummary() {
  const targetRecordIds = getExperienceSummaryTargetRecordIds();
  if (!targetRecordIds.length) {
    ElMessage.warning(getExperienceSummaryUnavailableMessage());
    return;
  }
  try {
    await ElMessageBox.confirm(
      `本次会总结 ${targetRecordIds.length} 条需求记录，生成可复用的开发经验规则，并在成功后清空这批记录。是否继续？`,
      "开启开发经验沉淀",
      {
        type: "warning",
        confirmButtonText: "开始总结",
      },
    );
  } catch {
    return;
  }
  experienceSummaryLoading.value = true;
  try {
    const data = await api.post(`/projects/${projectId.value}/experience-summary-jobs`, {
      provider_id: String(experienceSummaryProviderId.value || "").trim(),
      model_name: String(experienceSummaryModelName.value || "").trim(),
      record_ids: targetRecordIds,
      clear_requirement_records: true,
      experience_scope: "development",
    });
    await Promise.all([fetchProject(), refreshRequirementRecords()]);
    const createdCount = Array.isArray(data?.created_rule_ids) ? data.created_rule_ids.length : 0;
    const updatedCount = Array.isArray(data?.updated_rule_ids) ? data.updated_rule_ids.length : 0;
    const clearCount = Number(data?.clear_result?.deleted_count || 0);
    ElMessage.success(
      `经验总结完成：新增 ${createdCount} 条，更新 ${updatedCount} 条，清空 ${clearCount} 条记录`,
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "总结经验失败");
  } finally {
    experienceSummaryLoading.value = false;
  }
}

async function copyManual() {
  try {
    await navigator.clipboard.writeText(generatedManual.value || "");
    ElMessage.success("内容已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败");
  }
}

async function addMember() {
  if (!canManageProjectUsers.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  const selected = [
    ...new Set(
      (addForm.value.employee_ids || [])
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  ];
  if (!selected.length) {
    ElMessage.warning("请选择员工");
    return;
  }
  const existingSet = memberIdSet.value;
  const toAdd = selected.filter((id) => !existingSet.has(id));
  const skipped = selected.filter((id) => existingSet.has(id));
  if (!toAdd.length) {
    ElMessage.warning("所选员工都已添加，无需重复添加");
    return;
  }
  saving.value = true;
  try {
    const roleValue = String(addForm.value.role || "member").trim() || "member";
    const results = await Promise.allSettled(
      toAdd.map((employeeId) =>
        api.post(`/projects/${projectId.value}/members`, {
          employee_id: employeeId,
          role: roleValue,
          enabled: !!addForm.value.enabled,
        }),
      ),
    );
    const successCount = results.filter(
      (item) => item.status === "fulfilled",
    ).length;
    const failCount = results.length - successCount;
    await fetchMembers();
    await fetchProjectMemories();
    if (failCount === 0) {
      const extra = skipped.length ? `，已忽略重复 ${skipped.length} 人` : "";
      ElMessage.success(`成功添加 ${successCount} 人${extra}`);
      showAddDialog.value = false;
      return;
    }
    if (successCount > 0) {
      ElMessage.warning(`成功添加 ${successCount} 人，失败 ${failCount} 人`);
      return;
    }
    ElMessage.error("成员保存失败");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function addProjectUsers() {
  if (!canManageProjectUsers.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  const selected = [
    ...new Set(
      (userForm.value.usernames || [])
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  ];
  if (!selected.length) {
    ElMessage.warning("请选择用户");
    return;
  }
  const existingSet = projectUserSet.value;
  const toAdd = selected.filter((username) => !existingSet.has(username));
  const skipped = selected.filter((username) => existingSet.has(username));
  if (!toAdd.length) {
    ElMessage.warning("所选用户都已添加，无需重复添加");
    return;
  }
  saving.value = true;
  try {
    const roleValue = String(userForm.value.role || "member").trim() || "member";
    const results = await Promise.allSettled(
      toAdd.map((username) =>
        api.post(`/projects/${projectId.value}/users`, {
          username,
          role: roleValue,
          enabled: !!userForm.value.enabled,
        }),
      ),
    );
    const successCount = results.filter(
      (item) => item.status === "fulfilled",
    ).length;
    const failCount = results.length - successCount;
    await fetchProjectUsers();
    if (failCount === 0) {
      const extra = skipped.length ? `，已忽略重复 ${skipped.length} 人` : "";
      ElMessage.success(`成功添加 ${successCount} 人${extra}`);
      showAddUserDialog.value = false;
      return;
    }
    if (successCount > 0) {
      ElMessage.warning(`成功添加 ${successCount} 人，失败 ${failCount} 人`);
      return;
    }
    ElMessage.error("可见用户保存失败");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function removeMember(row) {
  if (!canManageProjectUsers.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  await ElMessageBox.confirm(
    `确定移除成员 ${row.employee_name || row.employee_id}？`,
    "确认",
    { type: "warning" },
  );
  try {
    await api.delete(`/projects/${projectId.value}/members/${row.employee_id}`);
    ElMessage.success("成员已移除");
    await fetchMembers();
    await fetchProjectMemories();
  } catch {
    ElMessage.error("移除失败");
  }
}

async function removeProjectUser(row) {
  if (!canManageProjectUsers.value) {
    ElMessage.warning(manageBlockedMessage());
    return;
  }
  await ElMessageBox.confirm(
    `确定移除用户 ${row.username} 的项目访问权限？`,
    "确认",
    { type: "warning" },
  );
  try {
    await api.delete(`/projects/${projectId.value}/users/${encodeURIComponent(row.username)}`);
    ElMessage.success("用户访问权限已移除");
    await fetchProjectUsers();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "移除失败");
  }
}

onMounted(async () => {
  await fetchRuntimeOrigin();
});
</script>

<style scoped>
.project-detail-page {
  --project-detail-page-gutter: clamp(16px, 3vw, 32px);
  --project-detail-block-padding: clamp(18px, 2vw, 28px);
  --project-detail-surface-radius: 28px;
  --project-detail-soft-border: rgba(15, 23, 42, 0.08);
  min-height: 100%;
  padding: 24px 0 40px;
  background:
    radial-gradient(circle at 18% 0%, rgba(125, 211, 252, 0.16), transparent 26%),
    radial-gradient(circle at 82% 14%, rgba(103, 232, 249, 0.12), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%);
}

.project-detail-shell {
  width: calc(100% - (var(--project-detail-page-gutter) * 2));
  max-width: none;
  margin: 0 auto;
}

.project-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.52fr) minmax(280px, 0.88fr);
  align-items: start;
  gap: 18px;
  padding: clamp(20px, 2.4vw, 28px);
  margin-bottom: 20px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.project-hero__copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.project-hero__copy > * {
  min-width: 0;
}

.project-hero__signals {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.project-hero__eyebrow,
.block-eyebrow,
.project-hero__panel-eyebrow {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.project-hero__heading {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.project-hero__heading h3 {
  margin: 0;
  max-width: 12ch;
  font-size: clamp(26px, 3.6vw, 36px);
  line-height: 1.04;
  letter-spacing: -0.03em;
  color: #0f172a;
}

.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 10px;
}

.project-hero__heading p {
  max-width: 54ch;
  margin: 0;
  font-size: 14px;
  line-height: 1.65;
  color: #475569;
}

.project-hero__panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(125, 211, 252, 0.16), transparent 34%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.9), rgba(248, 250, 252, 0.84));
}

.project-hero__panel-copy {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-hero__panel-copy h4 {
  margin: 0;
  font-size: 20px;
  line-height: 1.15;
  color: #0f172a;
}

.project-hero__panel-copy p {
  margin: 0;
  color: #475569;
  line-height: 1.7;
}

.project-hero__actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.project-hero__actions-primary,
.project-hero__actions-secondary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.project-hero__actions-primary {
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.project-hero__actions :deep(.el-button) {
  margin-left: 0;
}

.project-hero__stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.project-hero__stats-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 78px;
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.78);
}

.project-hero__stats-card span {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.project-hero__stats-card strong {
  font-size: clamp(18px, 1.8vw, 22px);
  line-height: 1.15;
  color: #0f172a;
}

.project-detail-tabs-shell {
  padding: clamp(18px, 2vw, 28px);
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.68);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.project-detail-tabs-shell__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.project-detail-tabs-shell__header h4 {
  margin: 8px 0 0;
  font-size: clamp(24px, 3vw, 30px);
  line-height: 1.15;
  color: #0f172a;
}

.project-detail-tabs-shell__header p {
  max-width: 54ch;
  margin: 0;
  color: #475569;
  line-height: 1.7;
}

.project-detail-page--memory-focus .project-hero {
  gap: 20px;
  padding: 24px 28px;
}

.project-detail-page--memory-focus .project-hero__heading h3 {
  max-width: 14ch;
}

.project-detail-page--memory-focus .project-hero__panel {
  background:
    radial-gradient(circle at top left, rgba(125, 211, 252, 0.12), transparent 32%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.86), rgba(248, 250, 252, 0.8));
}

.project-detail-page--memory-focus .project-detail-tabs-shell__header p {
  max-width: 46ch;
}

.project-detail-tabs {
  width: 100%;
}

.project-detail-tabs :deep(.el-tabs__header) {
  margin: 0 0 22px;
}

.project-detail-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.project-detail-tabs :deep(.el-tabs__nav-wrap),
.project-detail-tabs :deep(.el-tabs__nav-scroll) {
  display: flex;
  align-items: center;
}

.project-detail-tabs :deep(.el-tabs__nav) {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 8px;
  padding: 6px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.8);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.84);
}

.project-detail-tabs :deep(.el-tabs__item) {
  height: auto;
  padding: 0;
  border: 0;
  color: inherit;
  background: transparent;
}

.project-detail-tabs :deep(.el-tabs__item.is-active),
.project-detail-tabs :deep(.el-tabs__item:hover) {
  color: inherit;
}

.project-detail-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

.project-detail-tab-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 160px;
  padding: 12px 16px;
  border-radius: 22px;
  color: #64748b;
  transition:
    background 180ms ease,
    box-shadow 180ms ease,
    color 180ms ease,
    transform 180ms ease;
}

.project-detail-tab-label__title {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.25;
}

.project-detail-tab-label__meta {
  font-size: 11px;
  line-height: 1.4;
  color: inherit;
  opacity: 0.8;
}

.project-detail-tabs :deep(.el-tabs__item.is-active) .project-detail-tab-label {
  color: #fff;
  background: linear-gradient(180deg, #0f172a, #1e293b);
  box-shadow: 0 18px 28px rgba(15, 23, 42, 0.14);
}

.project-detail-tabs :deep(.el-tabs__item:not(.is-active):hover) .project-detail-tab-label {
  background: rgba(248, 250, 252, 0.92);
  transform: translateY(-1px);
}

.project-detail-tabs :deep(.el-tabs__content) {
  overflow: visible;
}

.project-detail-tabs :deep(.el-tab-pane) {
  width: 100%;
}

.project-detail-tab-pane {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.project-detail-tab-pane > .block:first-child {
  margin-top: 0;
}

.project-type-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.project-type-option__label {
  font-weight: 600;
  color: #111827;
}

.project-type-option__desc {
  font-size: 12px;
  line-height: 1.4;
  color: #6b7280;
}

.project-type-help {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: #6b7280;
}

.block {
  margin-top: 22px;
  min-width: 0;
  padding: var(--project-detail-block-padding);
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: var(--project-detail-surface-radius);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.block--overview {
  margin-top: 0;
}

.block--memory-primary {
  margin-top: 0;
}

.block-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.block-header > * {
  min-width: 0;
}

.block-header h4 {
  margin: 0;
  font-size: 22px;
  line-height: 1.2;
  color: #0f172a;
}

.project-descriptions {
  overflow: hidden;
  border-radius: 22px;
  width: 100%;
}

.block :deep(.el-descriptions__body),
.memory-detail-task-tree :deep(.el-descriptions__body) {
  border-radius: 22px;
}

.block :deep(.el-descriptions__table),
.memory-detail-task-tree :deep(.el-descriptions__table) {
  background: rgba(255, 255, 255, 0.68);
 }

.block :deep(.el-descriptions__label),
.memory-detail-task-tree :deep(.el-descriptions__label) {
  width: 148px;
}

.section-alert {
  margin-bottom: 16px;
}

.block-header__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ui-rule-list {
  display: grid;
  gap: 14px;
  margin-top: 16px;
}

.ui-rule-card {
  padding: 16px 18px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.62);
}

.ui-rule-card__title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.ui-rule-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
  font-size: 12px;
  color: #7c8aa0;
}

.experience-rule-card__preview {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: #475569;
}

.experience-rule-card__actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.ui-rule-help {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.5;
  color: #6b7280;
}

.section-table {
  margin-top: 8px;
  width: 100%;
}

.block :deep(.el-table),
.block :deep(.el-table__inner-wrapper) {
  border-radius: 20px;
  overflow: hidden;
  width: 100%;
}

.block :deep(.el-table th.el-table__cell) {
  height: 54px;
  background: rgba(248, 250, 252, 0.9);
  color: #475569;
}

.block :deep(.el-table td.el-table__cell) {
  padding-top: 14px;
  padding-bottom: 14px;
}

.block :deep(.el-table__body-wrapper),
.block :deep(.el-table__header-wrapper) {
  width: 100%;
}

.block :deep(.el-table .cell) {
  min-width: 0;
}

.task-session-subtext {
  margin-top: 6px;
  font-size: 12px;
  color: #7c8aa0;
}

.memory-table-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.memory-table-main__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.memory-table-main__title {
  color: #0f172a;
  font-weight: 600;
  line-height: 1.5;
}

.memory-table-main__meta,
.memory-table-progress__head,
.memory-table-progress__node {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.memory-table-main__meta {
  font-size: 12px;
  color: #7c8aa0;
}

.memory-table-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.memory-table-progress__node {
  color: #0f172a;
  font-weight: 600;
  line-height: 1.5;
}

.task-session-goal {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

.table-panel__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}

.memory-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px;
  margin: 0;
}

.memory-overview-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.memory-overview-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  background: rgba(248, 250, 252, 0.78);
}

.memory-overview-card span {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.memory-overview-card strong {
  color: #0f172a;
  font-size: 20px;
  line-height: 1.1;
}

.memory-overview-card small {
  color: #64748b;
  line-height: 1.5;
}

.memory-health-shell {
  margin-bottom: 16px;
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(125, 211, 252, 0.12), transparent 30%),
    rgba(248, 250, 252, 0.8);
}

.memory-health-shell__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.memory-health-shell__head h5 {
  margin: 8px 0 0;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.3;
}

.memory-health-shell__head p {
  margin: 0;
  max-width: 30ch;
  color: #64748b;
  line-height: 1.6;
  text-align: right;
}

.memory-health-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.memory-health-card,
.memory-health-highlight {
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.78);
}

.memory-health-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
}

.memory-health-card.is-warning {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(255, 251, 235, 0.9);
}

.memory-health-card.is-danger {
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(255, 247, 245, 0.92);
}

.memory-health-card.is-info {
  border-color: rgba(56, 189, 248, 0.18);
  background: rgba(248, 251, 255, 0.92);
}

.memory-health-card.is-success {
  border-color: rgba(16, 185, 129, 0.18);
  background: rgba(240, 253, 250, 0.92);
}

.memory-health-card span,
.memory-health-highlight__eyebrow {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.memory-health-card strong {
  color: #0f172a;
  font-size: 20px;
  line-height: 1.1;
}

.memory-health-card small {
  color: #64748b;
  line-height: 1.55;
}

.memory-health-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.memory-health-highlight {
  padding: 16px;
}

.memory-health-highlight.is-warning {
  border-color: rgba(245, 158, 11, 0.2);
}

.memory-health-highlight.is-danger {
  border-color: rgba(239, 68, 68, 0.18);
}

.memory-health-highlight.is-info {
  border-color: rgba(56, 189, 248, 0.16);
}

.memory-health-highlight__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.memory-health-highlight__head h6 {
  margin: 8px 0 0;
  color: #0f172a;
  font-size: 16px;
  line-height: 1.4;
}

.memory-health-highlight p {
  margin: 12px 0 0;
  color: #475569;
  line-height: 1.65;
}

.memory-health-highlight__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.memory-health-highlight__meta span {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(248, 250, 252, 0.9);
  color: #475569;
  font-size: 12px;
  line-height: 1.4;
}

.memory-health-highlight__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.memory-toolbar-shell {
  margin-bottom: 18px;
  padding: 16px 18px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 24px;
  background: rgba(248, 250, 252, 0.82);
}

.memory-toolbar-shell__copy {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.memory-toolbar-shell__copy p {
  max-width: 60ch;
  margin: 0;
  color: #475569;
  line-height: 1.65;
}

.memory-filter-control {
  min-width: 0;
}

.memory-filter-control--search {
  flex: 1 1 280px;
}

.memory-filter-control--employee {
  flex: 1 1 240px;
}

.memory-filter-control--type {
  flex: 0 1 180px;
}

.memory-filter-control--limit {
  flex: 0 1 140px;
}

.memory-filters__actions {
  display: flex;
  flex: 1 1 260px;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  min-width: 0;
}

.memory-filters__hint {
  width: 100%;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.requirement-record-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.82);
}

.requirement-record-toolbar__copy,
.requirement-record-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.requirement-record-toolbar__copy {
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.requirement-record-toolbar__actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.requirement-records {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.requirement-record {
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(125, 211, 252, 0.12), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(248, 250, 252, 0.9));
  transition:
    border-color 180ms ease,
    box-shadow 180ms ease,
    transform 180ms ease;
}

.requirement-record--expanded {
  border-color: rgba(14, 116, 144, 0.24);
  box-shadow: 0 20px 38px rgba(14, 116, 144, 0.1);
}

.requirement-record__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.requirement-record__hero-copy,
.requirement-record__hero-actions,
.requirement-record__lineage-item {
  min-width: 0;
}

.requirement-record__eyebrow,
.requirement-record__lineage-item span {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.requirement-record__hero-copy h5 {
  margin: 8px 0 10px;
  color: #0f172a;
  font-size: clamp(20px, 2.4vw, 28px);
  line-height: 1.18;
}

.requirement-record__hero-copy p {
  margin: 0;
  color: #475569;
  line-height: 1.65;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.requirement-record__hero-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.requirement-record__supporting {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  font-size: 12px;
  color: #7c8aa0;
}

.requirement-record__supporting span {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.requirement-record__lineage {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.requirement-record__lineage-item {
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 22px;
  background: rgba(248, 250, 252, 0.84);
}

.requirement-record__lineage-item strong {
  display: block;
  color: #0f172a;
  margin-top: 8px;
  line-height: 1.45;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.requirement-record__lineage-item small {
  display: block;
  margin-top: 8px;
  color: #64748b;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.requirement-record__detail-shell {
  margin-top: 16px;
}

.requirement-record__tree-board {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 16px;
  padding: 20px 18px 16px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(103, 232, 249, 0.1), transparent 32%),
    linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(241, 245, 249, 0.94));
  overflow: visible;
}

.requirement-record__detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.requirement-record__detail-eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #0f766e;
}

.requirement-record__detail-head h6 {
  margin: 8px 0 0;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.3;
}

.requirement-record__detail-head p {
  margin: 0;
  max-width: 26ch;
  color: #64748b;
  line-height: 1.6;
  text-align: right;
}

.requirement-record__tree-hint {
  width: 100%;
  max-width: 720px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.76);
  color: #475569;
  line-height: 1.6;
  text-align: left;
}

:deep(.memory-detail-dialog) {
  width: min(960px, calc(100vw - 28px)) !important;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 34px;
  background:
    radial-gradient(circle at top left, rgba(125, 211, 252, 0.18), transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(248, 250, 252, 0.9));
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.08);
  overflow: hidden;
  backdrop-filter: blur(24px);
}

:deep(.memory-detail-dialog .el-dialog__header) {
  margin-right: 0;
  padding: 26px 28px 0;
}

:deep(.memory-detail-dialog .el-dialog__body) {
  padding: 18px 28px 12px;
}

:deep(.memory-detail-dialog .el-dialog__footer) {
  padding: 0 28px 28px;
}

.memory-detail-dialog__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.memory-detail-dialog__eyebrow,
.memory-detail-hero__eyebrow,
.memory-detail-section__eyebrow {
  font-size: 11px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: #0f766e;
}

.memory-detail-dialog__header h3 {
  margin: 8px 0 0;
  font-size: clamp(24px, 3vw, 32px);
  line-height: 1.1;
  color: #0f172a;
}

.memory-detail-dialog__header-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.memory-detail-shell {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.memory-detail-hero,
.memory-detail-section,
.memory-detail-task-tree {
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.memory-detail-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.9fr);
  gap: 18px;
  padding: 24px;
}

.memory-detail-hero__content h4 {
  margin: 10px 0 12px;
  font-size: clamp(24px, 3.2vw, 34px);
  line-height: 1.15;
  color: #0f172a;
}

.memory-detail-hero__content p {
  margin: 0;
  max-width: 62ch;
  color: #475569;
  line-height: 1.75;
}

.memory-detail-hero__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

.memory-detail-hero__meta-item {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  min-width: 140px;
  padding: 10px 12px;
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.84);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.memory-detail-hero__meta-item span {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.memory-detail-hero__meta-item strong {
  color: #0f172a;
  line-height: 1.45;
  word-break: break-word;
}

.memory-detail-hero__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.memory-detail-hero__status,
.memory-detail-meta-grid,
.memory-detail-task-tree__stats {
  display: grid;
  gap: 12px;
}

.memory-detail-hero__status {
  grid-template-columns: repeat(1, minmax(0, 1fr));
}

.memory-detail-status-card,
.memory-detail-meta-card,
.memory-detail-task-tree__stat {
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background: rgba(248, 250, 252, 0.86);
}

.memory-detail-status-card span,
.memory-detail-meta-card__label,
.memory-detail-task-tree__goal span,
.memory-detail-task-tree__stat span,
.memory-detail-plan__verification span {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.memory-detail-status-card strong,
.memory-detail-meta-card strong,
.memory-detail-task-tree__goal strong,
.memory-detail-task-tree__stat strong {
  display: block;
  color: #0f172a;
  line-height: 1.5;
  word-break: break-word;
}

.memory-detail-meta-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.memory-detail-section,
.memory-detail-task-tree {
  padding: 22px 24px;
}

.memory-detail-section__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.memory-detail-section__header h4 {
  margin: 8px 0 0;
  font-size: 22px;
  line-height: 1.2;
  color: #0f172a;
}

.memory-detail-content-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.memory-detail-block {
  min-height: 72px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
  color: #334155;
}

.memory-detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.memory-detail-task-tree {
  position: relative;
}

.memory-detail-task-tree__summary-tag {
  display: flex;
  align-items: center;
}

.memory-detail-task-tree__hero {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 16px;
  padding: 18px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(103, 232, 249, 0.14), transparent 32%),
    linear-gradient(135deg, rgba(248, 250, 252, 0.96), rgba(241, 245, 249, 0.92));
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.memory-detail-task-tree__goal {
  padding-right: 12px;
}

.memory-detail-task-tree__goal p {
  margin: 10px 0 0;
  color: #475569;
  line-height: 1.7;
}

.memory-detail-task-tree__stats {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.memory-detail-plan {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 18px;
}

.memory-detail-plan__item {
  position: relative;
  padding: 18px 18px 18px 22px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 24px;
  background: rgba(248, 250, 252, 0.88);
}

.memory-detail-plan__item::before {
  content: "";
  position: absolute;
  left: 10px;
  top: 18px;
  bottom: 18px;
  width: 3px;
  border-radius: 999px;
  background: linear-gradient(180deg, rgba(15, 118, 110, 0.72), rgba(125, 211, 252, 0.36));
}

.memory-detail-plan__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.memory-detail-plan__title-group {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.memory-detail-plan__title-group strong {
  color: #0f172a;
}

.memory-detail-plan__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.1);
  color: #115e59;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.memory-detail-plan__desc {
  margin-top: 10px;
  color: #475569;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-detail-plan__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  font-size: 12px;
  color: #7c8aa0;
}

.memory-detail-plan__verification {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
}

.memory-detail-plan__verification p {
  margin: 0;
  color: #334155;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-detail-plan__events,
.memory-detail-task-events {
  margin-top: 14px;
  padding: 14px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.memory-detail-plan__events-head,
.memory-detail-task-events__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.memory-detail-plan__events-head span,
.memory-detail-task-events__head .memory-detail-section__eyebrow {
  margin: 0;
}

.memory-detail-task-events__head h4 {
  margin: 8px 0 0;
  color: #0f172a;
}

.memory-detail-plan__events-head strong {
  color: #0f172a;
}

.memory-detail-plan__event {
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.memory-detail-plan__event + .memory-detail-plan__event {
  margin-top: 10px;
}

.memory-detail-plan__event-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.memory-detail-plan__event-title {
  color: #0f172a;
  font-weight: 600;
}

.memory-detail-plan__event p {
  margin: 8px 0 0;
  color: #475569;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-detail-plan__event-meta {
  margin-top: 8px;
  font-size: 12px;
  color: #7c8aa0;
}

code {
  background: #f6f8fa;
  padding: 2px 6px;
  border-radius: 4px;
}

.prompt-content {
  max-height: 60vh;
  overflow-y: auto;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 20px;
  padding: 18px 20px;
  background: rgba(255, 255, 255, 0.86);
}

.prompt-rendered {
  line-height: 1.7;
  color: #1f2937;
  font-size: 14px;
  word-break: break-word;
}

.prompt-rendered :deep(pre) {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
}

@media (max-width: 980px) {
  .project-detail-page {
    padding-top: 18px;
  }

  .project-hero {
    grid-template-columns: 1fr;
    gap: 18px;
    padding: 22px 20px;
  }

  .project-detail-tabs-shell__header {
    flex-direction: column;
  }

  .project-hero__heading h3 {
    max-width: none;
  }

  .project-hero__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .memory-detail-hero,
  .memory-detail-task-tree__hero {
    grid-template-columns: 1fr;
  }

  .memory-overview-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .memory-health-strip,
  .memory-health-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .memory-health-highlight__actions :deep(.el-button) {
    flex: 1 1 calc(50% - 4px);
  }

  .requirement-record__hero {
    flex-direction: column;
    align-items: stretch;
  }

  .requirement-record-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .requirement-record-toolbar__copy,
  .requirement-record-toolbar__actions {
    width: 100%;
    justify-content: space-between;
  }

  .requirement-record__hero-actions {
    justify-content: space-between;
  }

  .requirement-record__lineage {
    grid-template-columns: 1fr;
  }

  .requirement-record__detail-head {
    flex-direction: column;
  }

  .requirement-record__detail-head p {
    max-width: none;
    text-align: left;
  }

  .memory-detail-hero__meta-item {
    flex: 1 1 calc(50% - 10px);
  }

  .memory-detail-meta-grid,
  .memory-detail-task-tree__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .project-detail-page {
    --project-detail-page-gutter: 12px;
    --project-detail-block-padding: 18px;
  }

  .block {
    border-radius: 24px;
  }

  .project-hero__panel {
    padding: 16px;
  }

  .project-detail-tabs-shell {
    border-radius: 24px;
  }

  .block-header {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-actions {
    width: 100%;
  }

  .project-hero__signals,
  .project-hero__actions-primary,
  .project-hero__actions-secondary {
    flex-direction: column;
    align-items: stretch;
  }

  .project-hero__stats {
    grid-template-columns: 1fr;
  }

  .project-hero__actions :deep(.el-button) {
    width: 100%;
  }

  .project-detail-tabs :deep(.el-tabs__nav) {
    width: 100%;
  }

  .project-detail-tabs :deep(.el-tabs__item) {
    flex: 1 1 100%;
  }

  .project-detail-tab-label {
    min-width: 0;
  }

  .memory-filters {
    flex-direction: column;
  }

  .memory-overview-strip {
    grid-template-columns: 1fr;
  }

  .memory-health-shell {
    padding: 14px;
    border-radius: 20px;
  }

  .memory-health-shell__head {
    flex-direction: column;
  }

  .memory-health-shell__head p {
    max-width: none;
    text-align: left;
  }

  .memory-health-strip,
  .memory-health-grid {
    grid-template-columns: 1fr;
  }

  .memory-health-highlight__actions {
    flex-direction: column;
  }

  .memory-health-highlight__actions :deep(.el-button) {
    width: 100%;
  }

  .memory-filter-control,
  .memory-filters__actions {
    width: 100%;
    flex-basis: 100%;
  }

  .requirement-record {
    padding: 16px;
  }

  .requirement-record__hero-actions {
    flex-wrap: wrap;
  }

  .requirement-record__hero-actions :deep(.el-button) {
    flex: 1 1 auto;
  }

  .requirement-record-toolbar__actions :deep(.el-button) {
    flex: 1 1 auto;
  }

  .memory-filters__actions {
    justify-content: stretch;
  }

  .memory-toolbar-shell {
    padding: 14px;
    border-radius: 20px;
  }

  .memory-toolbar-shell__copy {
    margin-bottom: 12px;
  }

  .memory-filters__actions :deep(.el-button) {
    flex: 1 1 auto;
  }

  :deep(.memory-detail-dialog .el-dialog__header) {
    padding: 22px 20px 0;
  }

  :deep(.memory-detail-dialog .el-dialog__body) {
    padding: 16px 20px 10px;
  }

  :deep(.memory-detail-dialog .el-dialog__footer) {
    padding: 0 20px 22px;
  }

  .memory-detail-dialog__header {
    flex-direction: column;
  }

  .memory-detail-dialog__header-tags {
    justify-content: flex-start;
  }

  .memory-detail-hero,
  .memory-detail-section,
  .memory-detail-task-tree {
    border-radius: 24px;
  }

  .memory-detail-hero,
  .memory-detail-section,
  .memory-detail-task-tree {
    padding: 18px;
  }

  .memory-detail-hero__meta-item {
    flex-basis: 100%;
  }

  .memory-detail-meta-grid,
  .memory-detail-task-tree__stats {
    grid-template-columns: 1fr;
  }

  .memory-detail-plan__row,
  .memory-detail-plan__title-group {
    align-items: flex-start;
  }

  .memory-detail-plan__row {
    flex-direction: column;
  }

  .block :deep(.el-descriptions__label),
  .memory-detail-task-tree :deep(.el-descriptions__label) {
    width: 118px;
  }
}
</style>
