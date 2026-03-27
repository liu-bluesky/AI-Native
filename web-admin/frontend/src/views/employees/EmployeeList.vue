<template>
  <div>
    <div class="toolbar">
      <h3>AI 员工列表</h3>
      <div class="toolbar-actions">
        <el-button
          v-if="canCreateEmployeeEntry"
          plain
          @click="goToAgentTemplates"
          >行业智能体模板</el-button
        >
        <el-button
          v-if="canCreateEmployeeEntry"
          type="primary"
          @click="$router.push('/employees/create')"
          >创建员工</el-button
        >
      </div>
    </div>
    <el-alert
      class="usage-alert"
      type="info"
      :closable="false"
      show-icon
      title="功能说明：反馈=提交/反思/发布（需开启反馈升级）；记忆=查看与检索员工记忆（含自动写入的用户提问）；同步=查看同步事件。"
    />
    <el-table :data="employees" v-loading="loading" stripe class="employee-table">
      <el-table-column prop="id" label="ID" width="140" />
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column label="创建人" width="120">
        <template #default="{ row }">
          {{ formatRecordOwner(row) }}
        </template>
      </el-table-column>
      <el-table-column label="可见范围" width="140">
        <template #default="{ row }">
          {{ formatRecordVisibility(row) }}
        </template>
      </el-table-column>
      <el-table-column label="描述" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="employee-description-cell">{{ row.description || "-" }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="tone" label="语调" width="100" />
      <el-table-column prop="verbosity" label="风格" width="100" />
      <el-table-column label="反馈升级" width="100">
        <template #default="{ row }">
          <el-tag
            :type="row.feedback_upgrade_enabled ? 'success' : 'info'"
            size="small"
          >
            {{ row.feedback_upgrade_enabled ? "已开" : "已关" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="技能数" width="80">
        <template #default="{ row }">{{ row.skills?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="360" fixed="right">
        <template #default="{ row }">
          <div class="employee-actions-cell">
            <el-button
              v-for="action in getPrimaryEmployeeActions(row)"
              :key="`${row.id}-${action.key}`"
              text
              :type="action.type"
              @click="handleEmployeeAction(row, action.key)"
            >
              {{ action.label }}
            </el-button>
            <el-dropdown
              v-if="getOverflowEmployeeActions(row).length"
              trigger="click"
              @command="(actionKey) => handleEmployeeAction(row, actionKey)"
            >
              <el-button text type="primary" size="small">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="action in getOverflowEmployeeActions(row)"
                    :key="`${row.id}-${action.key}`"
                    :command="action.key"
                  >
                    {{ action.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showMcpConfig" :title="mcpDialogTitle" width="600px">
      <div class="mcp-desc">
        <p>{{ mcpDialogDesc }}</p>
      </div>

      <el-tabs v-model="mcpTab" class="mcp-tabs">
        <el-tab-pane label="SSE (网络接入)" name="sse">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpSseConfig }}</code></pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="HTTP (Inspector 桥接)" name="http">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpHttpConfig }}</code></pre>
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button type="primary" @click="copyActiveMcpConfig"
          >复制当前配置</el-button
        >
        <el-button @click="showMcpConfig = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showConfigTestDialog"
      :title="testDialogTitle"
      width="760px"
    >
      <div v-loading="testLoading">
        <el-alert
          v-if="testResult"
          :title="testSummaryText"
          :type="testAlertType"
          show-icon
          :closable="false"
        />

        <el-row :gutter="16" class="test-stats-row" v-if="testResult">
          <el-col :span="6">
            <el-statistic
              title="技能总数"
              :value="testResult.summary.skills_total"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic
              title="技能可用"
              :value="testResult.summary.skills_available"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic
              title="脚本可执行"
              :value="testResult.summary.skills_executable"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic
              title="规则匹配领域"
              :value="testResult.summary.rule_domains_matched"
            />
          </el-col>
        </el-row>

        <h4 class="test-section-title">技能检查</h4>
        <el-table
          :data="testResult?.skills || []"
          stripe
          size="small"
          v-if="testResult"
        >
          <el-table-column prop="skill_id" label="技能 ID" width="120" />
          <el-table-column prop="name" label="名称" width="130" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="checkTagType(row.status)" size="small">{{
                row.status
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="entry_count"
            label="脚本数"
            width="80"
            align="center"
          />
          <el-table-column label="样例脚本" show-overflow-tooltip>
            <template #default="{ row }">{{
              (row.sample_entries || []).join(" | ") || "-"
            }}</template>
          </el-table-column>
          <el-table-column prop="message" label="结果" width="180" />
        </el-table>
        <el-empty v-else description="暂无测试结果" :image-size="50" />

        <h4 class="test-section-title">规则检查</h4>
        <el-table
          :data="testResult?.rule_domains || []"
          stripe
          size="small"
          v-if="testResult"
        >
          <el-table-column prop="domain" label="规则领域" width="130" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="checkTagType(row.status)" size="small">{{
                row.status
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="matched_rule_count"
            label="匹配规则数"
            width="110"
            align="center"
          />
          <el-table-column label="样例标题" show-overflow-tooltip>
            <template #default="{ row }">{{
              (row.sample_titles || []).join(" / ") || "-"
            }}</template>
          </el-table-column>
          <el-table-column prop="message" label="结果" width="180" />
        </el-table>
        <el-empty v-else description="暂无测试结果" :image-size="50" />

        <h4 class="test-section-title">MCP 接口测试</h4>
        <el-alert
          v-if="mcpTestResult"
          :title="mcpTestResult.message"
          :type="mcpTestAlertType"
          show-icon
          :closable="false"
        />
        <el-empty v-else description="暂无测试结果" :image-size="50" />

        <h4 class="test-section-title">问题清单</h4>
        <div
          class="issue-list"
          v-if="testResult && (blockingIssues.length || warningIssues.length)"
        >
          <el-tag
            v-for="item in blockingIssues"
            :key="`block-${item}`"
            type="danger"
            class="issue-tag"
          >
            阻塞: {{ item }}
          </el-tag>
          <el-tag
            v-for="item in warningIssues"
            :key="`warn-${item}`"
            type="warning"
            class="issue-tag"
          >
            警告: {{ item }}
          </el-tag>
        </div>
        <el-empty v-else description="未发现问题" :image-size="50" />
      </div>

      <template #footer>
        <el-button type="primary" :loading="testLoading" @click="runConfigTest"
          >重新测试</el-button
        >
        <el-button @click="showConfigTestDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showManualDialog"
      :title="manualDialogTitle"
      width="700px"
    >
      <div v-loading="manualLoading">
        <el-alert
          v-if="generatedManual"
          title="使用手册加载成功"
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
          :image-size="50"
        />
      </div>

      <template #footer>
        <el-button v-if="generatedManual" type="primary" @click="copyManual"
          >复制使用手册</el-button
        >
        <el-button
          type="success"
          :loading="manualLoading"
          @click="loadEmployeeManual"
          >加载使用手册</el-button
        >
        <el-button @click="showManualDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showTemplateImportDialog"
      class="template-import-dialog"
      modal-class="template-import-overlay"
      fullscreen
      append-to-body
      :show-close="false"
      :z-index="4000"
      destroy-on-close
      @closed="resetTemplateImportDialog"
    >
      <div class="template-import-shell">
        <div class="template-import-hero">
          <div class="template-import-hero__copy">
            <div class="template-import-hero__eyebrow">Employee Import</div>
            <div class="template-import-hero__title">从 Agent 模板导入员工</div>
            <div class="template-import-hero__text">
              直接读取 Git 仓库或本地目录中的 Markdown agent 文件，映射成员工草稿后再创建到员工列表。
            </div>
          </div>
          <div class="template-import-hero__actions">
            <div class="template-import-hero__status">
              {{ templateImportStatusText }}
            </div>
            <el-button @click="showTemplateImportDialog = false">关闭</el-button>
            <el-button
              type="primary"
              :disabled="!selectedImportedDraftEntries.length"
              :loading="templateImportCreating"
              @click="confirmTemplateImport"
            >
              {{ templateImportSubmitText }}
            </el-button>
          </div>
        </div>

        <div class="template-import-layout">
          <div class="template-import-source">
              <div class="template-import-section__head">
                <div class="template-import-section__title">模板来源</div>
                <div class="template-import-section__hint">
                  支持 Git 仓库 URL、本地目录，也支持直接粘贴 GitHub 的 `tree/...` 子目录网页链接。
                </div>
              </div>
              <el-form label-position="top" class="template-import-form">
                <el-form-item label="来源类型">
                  <el-radio-group v-model="templateImportForm.source_type">
                    <el-radio-button label="git">Git 仓库</el-radio-button>
                    <el-radio-button label="local">本地目录</el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item
                  :label="templateImportForm.source_type === 'git' ? '仓库地址' : '目录路径'"
                >
                  <el-input
                    v-model="templateImportForm.source"
                    :placeholder="
                      templateImportForm.source_type === 'git'
                        ? '例如：https://github.com/msitarzewski/agency-agents/tree/main/engineering'
                        : '例如：./agents 或 /abs/path/to/templates'
                    "
                  />
                </el-form-item>
                <div class="template-import-source__row">
                  <el-form-item label="子目录">
                    <el-input
                      v-model="templateImportForm.subdirectory"
                      placeholder="可选，例如：engineering"
                    />
                  </el-form-item>
                  <el-form-item
                    v-if="templateImportForm.source_type === 'git'"
                    label="分支"
                  >
                    <el-input
                      v-model="templateImportForm.branch"
                      placeholder="可选"
                    />
                  </el-form-item>
                  <el-form-item v-else label="读取上限">
                    <el-input-number
                      v-model="templateImportForm.limit"
                      :min="1"
                      :max="80"
                    />
                  </el-form-item>
                </div>
                <el-form-item
                  v-if="templateImportForm.source_type === 'git'"
                  label="读取上限"
                >
                  <el-input-number
                    v-model="templateImportForm.limit"
                    :min="1"
                    :max="80"
                  />
                </el-form-item>
              </el-form>
              <div class="template-import-source__actions">
                <el-button
                  type="primary"
                  :loading="templateImportLoading"
                  @click="loadTemplateCandidates"
                  >读取模板</el-button
                >
                <span class="template-import-source__status">
                  读取后直接在右侧勾选要导入的模板。
                </span>
              </div>
          </div>

          <div class="template-import-main">
            <div class="template-import-candidates">
              <div class="template-import-section__head">
                <div class="template-import-section__title">模板列表</div>
                <div class="template-import-section__hint">
                  共 {{ importedTemplates.length }} 个候选模板。勾选要导入的项，点击卡片可在右侧预览映射结果。
                </div>
              </div>
              <div
                v-if="importedTemplates.length"
                class="template-import-candidates__toolbar"
              >
                <div class="template-import-candidates__selection">
                  待导入 {{ selectedImportedTemplateCount }} 个
                </div>
                <div class="template-import-candidates__actions">
                  <el-button link type="primary" @click="selectAllImportedTemplates"
                    >全选</el-button
                  >
                  <el-button link @click="clearImportedTemplateSelection"
                    >清空</el-button
                  >
                </div>
              </div>
              <div
                v-loading="templateImportLoading"
                class="template-import-candidates__list"
              >
                <el-empty
                  v-if="!importedTemplates.length"
                  description="尚未读取到模板"
                  :image-size="56"
                />
                <div
                  v-for="item in importedTemplates"
                  :key="item.id"
                  class="template-candidate-card"
                  :class="{
                    'is-active': selectedImportedTemplateId === item.id,
                    'is-selected': isImportedTemplateSelected(item.id),
                  }"
                  @click="selectedImportedTemplateId = item.id"
                >
                  <div class="template-candidate-card__select" @click.stop>
                    <el-checkbox
                      :model-value="isImportedTemplateSelected(item.id)"
                      @change="(checked) => setImportedTemplateSelection(item.id, checked)"
                    />
                  </div>
                  <div class="template-candidate-card__body">
                    <div class="template-candidate-card__head">
                      <span class="template-candidate-card__name">{{ item.name }}</span>
                      <span class="template-candidate-card__path">{{
                        item.relative_path
                      }}</span>
                    </div>
                    <div class="template-candidate-card__desc">
                      {{ item.description || "暂无描述" }}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="template-import-preview">
              <div class="template-import-section__head">
                <div class="template-import-section__title">待导入草稿</div>
                <div class="template-import-section__hint">
                  勾选的模板会汇总到这里。你可以先确认导入范围，再点击详情查看完整字段。
                </div>
              </div>

              <div
                v-if="selectedImportedDraftEntries.length"
                class="template-import-preview__body"
              >
                <div class="template-import-preview__selected">
                  <div class="template-import-preview__selected-head">
                    <div class="template-import-preview__selected-title">
                      已勾选 {{ selectedImportedTemplateCount }} 个草稿
                    </div>
                    <div class="template-import-preview__selected-hint">
                      点击“详情”查看导入后的完整员工字段。
                    </div>
                  </div>
                  <div class="template-import-preview__selected-list">
                    <div
                      v-for="entry in selectedImportedDraftEntries"
                      :key="entry.id"
                      class="template-import-preview__selected-card"
                      :class="{ 'is-active': selectedImportedPreviewId === entry.id }"
                    >
                      <div class="template-import-preview__selected-main">
                        <div class="template-import-preview__selected-name">
                          {{ entry.draft.name || entry.name || "未命名模板" }}
                        </div>
                        <div class="template-import-preview__selected-meta">
                          <span>{{ entry.draft.template_relative_path || "-" }}</span>
                          <span>{{ entry.draft.template_source_name || "-" }}</span>
                        </div>
                      </div>
                      <div class="template-import-preview__selected-actions">
                        <el-button
                          link
                          type="primary"
                          @click="showImportedTemplateDetail(entry.id)"
                          >详情</el-button
                        >
                        <el-button
                          link
                          @click="setImportedTemplateSelection(entry.id, false)"
                          >移除</el-button
                        >
                      </div>
                    </div>
                  </div>
                </div>

                <div class="template-import-preview__options">
                  <el-checkbox v-model="templateImportAutoCreateSkills">
                    自动补齐缺失技能
                  </el-checkbox>
                  <el-checkbox v-model="templateImportAutoCreateRules">
                    自动补齐缺失规则
                  </el-checkbox>
                </div>

                <div
                  v-if="selectedImportedDraft"
                  class="template-import-preview__detail"
                >
                  <div class="template-import-preview__summary">
                    <div class="template-import-preview__summary-main">
                      <div class="template-import-preview__title">
                        {{ selectedImportedDraft.name || "未命名模板" }}
                      </div>
                      <div class="template-import-preview__meta">
                        <span>来源：{{ selectedImportedDraft.template_source_name || "-" }}</span>
                        <span>路径：{{ selectedImportedDraft.template_relative_path || "-" }}</span>
                      </div>
                    </div>
                    <div class="template-import-preview__summary-side">
                      <div class="template-import-preview__pill">
                        {{ selectedImportedDraft.language || "en-US" }}
                      </div>
                      <div class="template-import-preview__pill">
                        {{ selectedImportedDraft.tone || "professional" }}
                      </div>
                      <div class="template-import-preview__pill">
                        {{ selectedImportedDraft.verbosity || "concise" }}
                      </div>
                    </div>
                  </div>

                  <div class="template-import-preview__lead">
                    {{ selectedImportedDraft.description || "暂无描述" }}
                  </div>

                  <div class="template-import-preview__focus">
                    <div class="template-import-preview__focus-label">核心目标</div>
                    <div class="template-import-preview__focus-text">
                      {{ selectedImportedDraft.goal || "-" }}
                    </div>
                  </div>

                  <div class="template-import-preview__grid">
                    <div class="template-import-preview__panel">
                      <div class="template-import-preview__panel-title">规则领域</div>
                      <div class="template-import-preview__field-inline">
                        {{ selectedImportedDraft.rule_domains?.join(" / ") || "未识别" }}
                      </div>
                    </div>

                    <div class="template-import-preview__panel">
                      <div class="template-import-preview__panel-title">工作流</div>
                      <ul
                        v-if="selectedImportedDraft.default_workflow?.length"
                        class="template-import-preview__list"
                      >
                        <li
                          v-for="item in selectedImportedDraft.default_workflow"
                          :key="item"
                        >
                          {{ item }}
                        </li>
                      </ul>
                      <div v-else class="template-import-preview__empty">
                        未提取到显式工作流
                      </div>
                    </div>

                    <div class="template-import-preview__panel">
                      <div class="template-import-preview__panel-title">风格提示</div>
                      <div
                        v-if="selectedImportedDraft.style_hints?.length"
                        class="template-import-preview__tags"
                      >
                        <el-tag
                          v-for="item in selectedImportedDraft.style_hints"
                          :key="item"
                          size="small"
                          type="info"
                        >
                          {{ item }}
                        </el-tag>
                      </div>
                      <div v-else class="template-import-preview__empty">
                        未提取到显式风格提示
                      </div>
                    </div>

                    <div class="template-import-preview__panel">
                      <div class="template-import-preview__panel-title">执行约束</div>
                      <pre class="template-import-preview__policy">{{
                        selectedImportedDraft.tool_usage_policy || "未提取到显式执行约束"
                      }}</pre>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="template-import-preview__empty-state">
                <div class="template-import-preview__empty-title">等待勾选模板</div>
                <div class="template-import-preview__empty-text">
                  先读取模板，再勾选要导入的模板。已勾选项会汇总到这里，之后可点击详情查看。
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { marked } from "marked";
import api from "@/utils/api.js";
import {
  formatRecordVisibility,
  formatRecordOwner,
  getOwnershipDeniedMessage,
} from "@/utils/ownership.js";
import {
  canCreateEmployee,
  canDeleteEmployee,
  canUpdateEmployee,
} from "@/utils/employee-permissions.js";
import { buildRuntimeUrl } from "@/utils/runtime-url.js";
import { resolveSettingsAwarePanelPath } from "@/utils/chat-settings-route.js";

const route = useRoute();
const router = useRouter();

const employees = ref([]);
const loading = ref(false);
const showMcpConfig = ref(false);
const mcpTab = ref("sse");
const currentEmployee = ref(null);
const mcpDialogTitle = ref("员工 MCP 接入");
const mcpDialogDesc = ref(
  "将该员工配置挂载到 AI 编辑器后，模型即可按员工配置读取技能、规则和记忆。",
);
const showConfigTestDialog = ref(false);
const testDialogTitle = ref("员工配置测试");
const testLoading = ref(false);
const testTargetEmployee = ref(null);
const testResult = ref(null);
const mcpTestResult = ref(null);
const showManualDialog = ref(false);
const manualDialogTitle = ref("使用手册");
const manualLoading = ref(false);
const manualTargetEmployee = ref(null);
const generatedManual = ref("");
const showTemplateImportDialog = ref(false);
const templateImportLoading = ref(false);
const templateImportCreating = ref(false);
const importedTemplates = ref([]);
const selectedImportedTemplateId = ref("");
const selectedImportedTemplateIds = ref([]);
const templateImportAutoCreateSkills = ref(true);
const templateImportAutoCreateRules = ref(true);
const templateImportForm = ref({
  source_type: "git",
  source: "",
  subdirectory: "",
  branch: "",
  limit: 40,
});

function goToAgentTemplates() {
  void router.push(
    resolveSettingsAwarePanelPath(route.path, "agent-templates", "/agent-templates"),
  );
}

function normalizeImportedDraftPayload(draft) {
  if (!draft || typeof draft !== "object") return null;
  return {
    ...draft,
    style_hints: Array.isArray(draft.style_hints) ? draft.style_hints : [],
    default_workflow: Array.isArray(draft.default_workflow)
      ? draft.default_workflow
      : [],
    rule_drafts: Array.isArray(draft.rule_drafts) ? draft.rule_drafts : [],
    rule_domains: Array.isArray(draft.rule_domains) ? draft.rule_domains : [],
    skills: Array.isArray(draft.skills) ? draft.skills : [],
  };
}
const selectedImportedTemplate = computed(() =>
  importedTemplates.value.find((item) => item.id === selectedImportedTemplateId.value) ||
  null,
);
const selectedImportedDraftEntries = computed(() =>
  importedTemplates.value
    .filter((item) => selectedImportedTemplateIds.value.includes(item.id))
    .map((item) => ({
      id: item.id,
      name: item.name || item.id,
      draft: normalizeImportedDraftPayload(item.draft),
    }))
    .filter((item) => item.draft),
);
const selectedImportedPreviewId = computed(() => {
  if (!selectedImportedDraftEntries.value.length) return "";
  const matched = selectedImportedDraftEntries.value.find(
    (item) => item.id === selectedImportedTemplateId.value,
  );
  return matched?.id || selectedImportedDraftEntries.value[0]?.id || "";
});
const selectedImportedDraft = computed(() => {
  const matched = selectedImportedDraftEntries.value.find(
    (item) => item.id === selectedImportedPreviewId.value,
  );
  return matched?.draft || null;
});
const selectedImportedTemplateCount = computed(
  () => selectedImportedDraftEntries.value.length,
);
const templateImportSubmitText = computed(() => {
  if (!selectedImportedTemplateCount.value) return "创建到员工列表";
  return `创建到员工列表（${selectedImportedTemplateCount.value}）`;
});
const templateImportStatusText = computed(() => {
  if (templateImportLoading.value) return "正在扫描模板...";
  if (!importedTemplates.value.length) return "输入来源后读取模板";
  return `已读取 ${importedTemplates.value.length} 个模板，待导入 ${selectedImportedTemplateCount.value} 个`;
});

const renderedManualHtml = computed(() => {
  if (!generatedManual.value) return "";
  try {
    return marked.parse(generatedManual.value);
  } catch (e) {
    return generatedManual.value.replace(/\n/g, "<br>");
  }
});

const mcpSseConfig = computed(() => {
  if (!currentEmployee.value) return "";
  const serverName = `employee-${currentEmployee.value.id}`;
  return JSON.stringify(
    {
      mcpServers: {
        [serverName]: {
          type: "sse",
          url: buildRuntimeUrl(
            `/mcp/employees/${currentEmployee.value.id}/sse?key=YOUR_API_KEY&project_id=default`,
          ),
        },
      },
    },
    null,
    2,
  );
});

const mcpHttpConfig = computed(() => {
  if (!currentEmployee.value) return "";
  const serverName = `employee-${currentEmployee.value.id}`;
  return JSON.stringify(
    {
      mcpServers: {
        [serverName]: {
          command: "npx",
          args: [
            "-y",
            "@modelcontextprotocol/inspector",
            buildRuntimeUrl(
              `/mcp/employees/${currentEmployee.value.id}/mcp?key=YOUR_API_KEY&project_id=default`,
            ),
          ],
        },
      },
    },
    null,
    2,
  );
});

const blockingIssues = computed(() => testResult.value?.blocking_issues || []);
const warningIssues = computed(() => testResult.value?.warning_issues || []);
const testAlertType = computed(() => {
  const status = testResult.value?.summary?.overall_status;
  return (
    { healthy: "success", warning: "warning", failed: "error" }[status] ||
    "info"
  );
});
const testSummaryText = computed(() => {
  const summary = testResult.value?.summary;
  if (!summary) return "等待测试";
  if (summary.overall_status === "healthy")
    return "配置测试通过：技能与规则均可用";
  if (summary.overall_status === "warning") return "配置测试通过，但存在警告项";
  return "配置测试失败：存在阻塞问题";
});
const mcpTestAlertType = computed(() => {
  const status = mcpTestResult.value?.status;
  if (status === "success") return "success";
  if (status === "disabled") return "warning";
  return "error";
});

const canCreateEmployeeEntry = computed(() => canCreateEmployee());

function canManageRow(row) {
  return canUpdateRow(row);
}

function canUpdateRow(row) {
  return canUpdateEmployee(row);
}

function canDeleteRow(row) {
  return canDeleteEmployee(row);
}

function getEmployeeActions(row) {
  const actions = [
    { key: "detail", label: "详情", type: "primary" },
  ];
  if (canUpdateRow(row)) {
    actions.push({ key: "edit", label: "编辑", type: "primary" });
  }
  if (row.mcp_enabled) {
    actions.push({ key: "mcp-config", label: "接入", type: "success" });
    if (canUpdateRow(row)) {
      actions.push({ key: "disable-mcp", label: "关闭 MCP", type: "warning" });
    }
  } else if (canUpdateRow(row)) {
    actions.push({ key: "enable-mcp", label: "开启 MCP", type: "warning" });
  }
  actions.push({ key: "config-test", label: "测试", type: "info" });
  actions.push({ key: "manual", label: "使用手册", type: "success" });
  actions.push({ key: "usage", label: "统计", type: "primary" });
  if (row.feedback_upgrade_enabled) {
    actions.push({ key: "feedback", label: "反馈", type: "primary" });
    if (canUpdateRow(row)) {
      actions.push({
        key: "disable-feedback",
        label: "关闭反馈",
        type: "warning",
      });
    }
  } else if (canUpdateRow(row)) {
    actions.push({ key: "enable-feedback", label: "开启反馈", type: "primary" });
  }
  actions.push({ key: "memory", label: "记忆" });
  actions.push({ key: "sync", label: "同步" });
  if (canDeleteRow(row)) {
    actions.push({ key: "delete", label: "删除", type: "danger" });
  }
  return actions;
}

function getPrimaryEmployeeActions(row) {
  return getEmployeeActions(row).slice(0, 3);
}

function getOverflowEmployeeActions(row) {
  return getEmployeeActions(row).slice(3);
}

function handleEmployeeAction(row, actionKey) {
  switch (actionKey) {
    case "detail":
      router.push(`/employees/${row.id}`);
      break;
    case "edit":
      router.push(`/employees/${row.id}/edit`);
      break;
    case "mcp-config":
      showEmployeeMcpConfig(row);
      break;
    case "enable-mcp":
      void enableEmployeeMcp(row);
      break;
    case "disable-mcp":
      void disableEmployeeMcp(row);
      break;
    case "config-test":
      void showEmployeeConfigTest(row);
      break;
    case "manual":
      void showEmployeeManual(row);
      break;
    case "usage":
      router.push(`/employees/${row.id}/usage`);
      break;
    case "feedback":
      router.push(`/feedback/${row.id}`);
      break;
    case "enable-feedback":
      void enableFeedbackUpgrade(row);
      break;
    case "disable-feedback":
      void disableFeedbackUpgrade(row);
      break;
    case "memory":
      router.push(`/memory/${row.id}`);
      break;
    case "sync":
      router.push(`/sync/${row.id}`);
      break;
    case "delete":
      void handleDelete(row);
      break;
    default:
      break;
  }
}

async function fetchList() {
  loading.value = true;
  try {
    const { employees: list } = await api.get("/employees");
    employees.value = list;
  } catch {
    ElMessage.error("加载失败");
  } finally {
    loading.value = false;
  }
}

function resetTemplateImportDialog() {
  templateImportLoading.value = false;
  templateImportCreating.value = false;
  importedTemplates.value = [];
  selectedImportedTemplateId.value = "";
  selectedImportedTemplateIds.value = [];
  templateImportAutoCreateSkills.value = true;
  templateImportAutoCreateRules.value = true;
}

function openTemplateImportDialog() {
  resetTemplateImportDialog();
  templateImportForm.value = {
    source_type: "git",
    source: "",
    subdirectory: "",
    branch: "",
    limit: 40,
  };
  showTemplateImportDialog.value = true;
}

function isImportedTemplateSelected(templateId) {
  return selectedImportedTemplateIds.value.includes(templateId);
}

function setImportedTemplateSelection(templateId, checked) {
  const normalizedId = String(templateId || "").trim();
  if (!normalizedId) return;
  if (checked) {
    if (!selectedImportedTemplateIds.value.includes(normalizedId)) {
      selectedImportedTemplateIds.value = [
        ...selectedImportedTemplateIds.value,
        normalizedId,
      ];
    }
    if (!selectedImportedTemplateId.value) {
      selectedImportedTemplateId.value = normalizedId;
    }
    return;
  }
  selectedImportedTemplateIds.value = selectedImportedTemplateIds.value.filter(
    (item) => item !== normalizedId,
  );
  if (selectedImportedTemplateId.value === normalizedId) {
    selectedImportedTemplateId.value = selectedImportedTemplateIds.value[0] || "";
  }
}

function selectAllImportedTemplates() {
  selectedImportedTemplateIds.value = importedTemplates.value.map((item) => item.id);
  if (!selectedImportedTemplateId.value && importedTemplates.value.length) {
    selectedImportedTemplateId.value = importedTemplates.value[0].id;
  }
}

function clearImportedTemplateSelection() {
  selectedImportedTemplateIds.value = [];
  selectedImportedTemplateId.value = "";
}

function showImportedTemplateDetail(templateId) {
  const normalizedId = String(templateId || "").trim();
  if (!normalizedId) return;
  selectedImportedTemplateId.value = normalizedId;
}

async function loadTemplateCandidates() {
  const payload = {
    source_type: String(templateImportForm.value.source_type || "git").trim(),
    source: String(templateImportForm.value.source || "").trim(),
    subdirectory: String(templateImportForm.value.subdirectory || "").trim(),
    branch: String(templateImportForm.value.branch || "").trim(),
    limit: Number(templateImportForm.value.limit || 40),
  };
  if (!payload.source) {
    ElMessage.warning(
      payload.source_type === "git" ? "请先输入仓库地址" : "请先输入目录路径",
    );
    return;
  }
  templateImportLoading.value = true;
  try {
    const data = await api.post("/employees/import-agent-templates", payload);
    importedTemplates.value = Array.isArray(data?.templates) ? data.templates : [];
    selectedImportedTemplateId.value = importedTemplates.value[0]?.id || "";
    selectedImportedTemplateIds.value = [];
    if (!importedTemplates.value.length) {
      ElMessage.warning("没有找到可导入的 Markdown agent 模板");
      return;
    }
    ElMessage.success(`已读取 ${importedTemplates.value.length} 个模板`);
  } catch (e) {
    importedTemplates.value = [];
    selectedImportedTemplateId.value = "";
    selectedImportedTemplateIds.value = [];
    ElMessage.error(e.detail || "模板读取失败");
  } finally {
    templateImportLoading.value = false;
  }
}

async function confirmTemplateImport() {
  if (!selectedImportedDraftEntries.value.length) {
    ElMessage.warning("请先勾选要导入的模板");
    return;
  }
  templateImportCreating.value = true;
  try {
    const createdNames = [];
    const failedEntries = [];
    for (const entry of selectedImportedDraftEntries.value) {
      const payload = {
        ...entry.draft,
        auto_create_missing_skills: templateImportAutoCreateSkills.value,
        auto_create_missing_rules: templateImportAutoCreateRules.value,
      };
      try {
        const data = await api.post("/employees/create-from-draft", payload);
        createdNames.push(data?.employee?.name || entry.draft.name || entry.name);
      } catch (e) {
        failedEntries.push({
          id: entry.id,
          name: entry.draft.name || entry.name || "员工",
          detail: e.detail || "创建员工失败",
        });
      }
    }
    if (createdNames.length) {
      await fetchList();
    }
    if (!failedEntries.length) {
      ElMessage.success(`已创建 ${createdNames.length} 个员工`);
      showTemplateImportDialog.value = false;
      return;
    }
    selectedImportedTemplateIds.value = failedEntries.map((item) => item.id);
    selectedImportedTemplateId.value =
      failedEntries[0]?.id || importedTemplates.value[0]?.id || "";
    if (createdNames.length) {
      ElMessage.warning(
        `已创建 ${createdNames.length} 个员工，仍有 ${failedEntries.length} 个导入失败`,
      );
      return;
    }
    ElMessage.error(`${failedEntries[0].name} 导入失败：${failedEntries[0].detail}`);
  } catch (e) {
    ElMessage.error(e.detail || "创建员工失败");
  } finally {
    templateImportCreating.value = false;
  }
}

async function handleDelete(row) {
  if (!canDeleteRow(row)) {
    ElMessage.warning(getOwnershipDeniedMessage(row, "删除"));
    return;
  }
  await ElMessageBox.confirm(`确定删除员工「${row.name}」？`, "确认");
  try {
    await api.delete(`/employees/${row.id}`);
    ElMessage.success("已删除");
    fetchList();
  } catch {
    ElMessage.error("删除失败");
  }
}

function showEmployeeMcpConfig(row) {
  currentEmployee.value = row;
  mcpTab.value = "sse";
  mcpDialogTitle.value = `员工接入: ${row.name}`;
  showMcpConfig.value = true;
}

async function enableEmployeeMcp(row) {
  if (!canUpdateRow(row)) {
    ElMessage.warning(getOwnershipDeniedMessage(row, "编辑"));
    return;
  }
  try {
    loading.value = true;
    await api.put(`/employees/${row.id}`, { mcp_enabled: true });
    ElMessage.success("已开启员工 MCP 服务");
    await fetchList();
    const updated = employees.value.find((item) => item.id === row.id) || row;
    showEmployeeMcpConfig(updated);
  } catch (e) {
    ElMessage.error(e.detail || "开启 MCP 失败");
  } finally {
    loading.value = false;
  }
}

async function disableEmployeeMcp(row) {
  if (!canUpdateRow(row)) {
    ElMessage.warning(getOwnershipDeniedMessage(row, "编辑"));
    return;
  }
  await ElMessageBox.confirm(
    `确定关闭员工「${row.name}」的 MCP 服务？`,
    "确认",
  );
  try {
    loading.value = true;
    await api.put(`/employees/${row.id}`, { mcp_enabled: false });
    ElMessage.success("已关闭员工 MCP 服务");
    await fetchList();
    if (currentEmployee.value?.id === row.id) {
      showMcpConfig.value = false;
      currentEmployee.value = null;
    }
  } catch (e) {
    ElMessage.error(e.detail || "关闭 MCP 失败");
  } finally {
    loading.value = false;
  }
}

async function enableFeedbackUpgrade(row) {
  if (!canUpdateRow(row)) {
    ElMessage.warning(getOwnershipDeniedMessage(row, "编辑"));
    return;
  }
  try {
    loading.value = true;
    await api.put(`/employees/${row.id}`, { feedback_upgrade_enabled: true });
    ElMessage.success("已开启反馈升级");
    await fetchList();
  } catch (e) {
    ElMessage.error(e.detail || "开启反馈失败");
  } finally {
    loading.value = false;
  }
}

async function disableFeedbackUpgrade(row) {
  if (!canUpdateRow(row)) {
    ElMessage.warning(getOwnershipDeniedMessage(row, "编辑"));
    return;
  }
  await ElMessageBox.confirm(
    `确定关闭员工「${row.name}」的反馈升级模块？`,
    "确认",
  );
  try {
    loading.value = true;
    await api.put(`/employees/${row.id}`, { feedback_upgrade_enabled: false });
    ElMessage.success("已关闭反馈升级");
    await fetchList();
  } catch (e) {
    ElMessage.error(e.detail || "关闭反馈失败");
  } finally {
    loading.value = false;
  }
}

function checkTagType(status) {
  return (
    { ok: "success", warning: "warning", missing: "danger" }[status] || "info"
  );
}

async function runConfigTest() {
  if (!testTargetEmployee.value?.id) return;
  testLoading.value = true;
  try {
    const data = await api.get(
      `/employees/${testTargetEmployee.value.id}/config-test`,
    );
    testResult.value = data;
    if (data.summary?.overall_status === "failed") {
      ElMessage.error("配置测试发现阻塞问题");
    } else if (data.summary?.overall_status === "warning") {
      ElMessage.warning("配置测试通过，但存在警告项");
    } else {
      ElMessage.success("配置测试通过");
    }

    await runMcpTest();
  } catch (e) {
    ElMessage.error(e.detail || "配置测试失败");
  } finally {
    testLoading.value = false;
  }
}

async function runMcpTest() {
  if (!testTargetEmployee.value?.id) return;
  try {
    const data = await api.post(
      `/employees/${testTargetEmployee.value.id}/mcp-test`,
    );
    mcpTestResult.value = data;
  } catch (e) {
    mcpTestResult.value = {
      status: "error",
      message: e.detail || "MCP 测试失败",
    };
  }
}

async function showEmployeeConfigTest(row) {
  testTargetEmployee.value = row;
  testDialogTitle.value = `配置测试: ${row.name}`;
  testResult.value = null;
  mcpTestResult.value = null;
  showConfigTestDialog.value = true;
  await runConfigTest();
}

async function showEmployeeManual(row) {
  manualTargetEmployee.value = row;
  manualDialogTitle.value = `使用手册: ${row.name}`;
  generatedManual.value = "";
  showManualDialog.value = true;
  await loadEmployeeManual();
}

async function loadEmployeeManual() {
  if (!manualTargetEmployee.value?.id) return;
  manualLoading.value = true;
  try {
    const data = await api.get(
      `/employees/${manualTargetEmployee.value.id}/manual-template`,
    );
    generatedManual.value = data.template || "";
    ElMessage.success("使用手册加载成功");
  } catch (e) {
    ElMessage.error(e.detail || "加载使用手册失败");
  } finally {
    manualLoading.value = false;
  }
}

async function copyManual() {
  try {
    await navigator.clipboard.writeText(generatedManual.value);
    ElMessage.success("使用手册已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败");
  }
}

async function copyActiveMcpConfig() {
  const content =
    mcpTab.value === "sse" ? mcpSseConfig.value : mcpHttpConfig.value;
  try {
    await navigator.clipboard.writeText(content);
    ElMessage.success("配置已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败");
  }
}

onMounted(async () => {
  await fetchList();
});
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.usage-alert {
  margin-bottom: 12px;
}

.employee-description-cell {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.employee-actions-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  white-space: nowrap;
  scrollbar-width: thin;
}

.employee-actions-cell :deep(.el-button) {
  margin-left: 0;
}

.employee-table :deep(.el-table__cell) {
  vertical-align: middle;
}

.toolbar h3 {
  margin: 0;
}

:global(.template-import-overlay) {
  z-index: 4000 !important;
  background:
    radial-gradient(circle at top left, rgba(255, 244, 214, 0.5), transparent 24%),
    linear-gradient(180deg, #f6f3ee 0%, #f7f7f8 32%, #f5f5f6 100%);
}

:global(.template-import-overlay .el-overlay-dialog) {
  padding: 0;
}

:global(.template-import-dialog) {
  margin: 0;
  width: 100vw;
  height: 100dvh;
  max-width: none;
  max-height: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

:global(.template-import-dialog .el-dialog__header) {
  display: none;
}

:global(.template-import-dialog .el-dialog__body) {
  padding: 0;
  height: 100%;
}

.template-import-shell {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  padding: 14px 16px 16px;
  box-sizing: border-box;
  gap: 18px;
}

.template-import-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 8px 24px 6px;
}

.template-import-hero__copy {
  min-width: 0;
  max-width: 760px;
}

.template-import-hero__eyebrow {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #8b7355;
}

.template-import-hero__title {
  margin-top: 10px;
  font-size: clamp(28px, 3vw, 38px);
  line-height: 1.08;
  font-weight: 600;
  color: #161616;
}

.template-import-hero__text {
  margin-top: 10px;
  font-size: 14px;
  line-height: 1.7;
  color: #5f6368;
}

.template-import-hero__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.template-import-hero__status {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}

.template-import-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 18px;
}

.template-import-main {
  min-width: 0;
  min-height: 0;
  max-height: calc(100dvh - 176px);
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 18px;
}

.template-import-source,
.template-import-candidates,
.template-import-preview {
  min-width: 0;
  border: 1px solid rgba(229, 231, 235, 0.88);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(14px);
}

.template-import-source,
.template-import-candidates {
  padding: 18px;
}

.template-import-preview {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 176px);
  padding: 18px max(20px, calc((100% - 920px) / 2)) 22px;
  overflow: hidden;
}

.template-import-section__head {
  margin-bottom: 12px;
}

.template-import-section__title {
  font-size: 15px;
  font-weight: 600;
  color: #161616;
}

.template-import-section__hint {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.6;
  color: #6b7280;
}

.template-import-form {
  margin-top: 14px;
}

.template-import-source__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.template-import-source__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.template-import-source__status {
  font-size: 12px;
  line-height: 1.5;
  color: #6b7280;
}

.template-import-candidates {
  min-height: 0;
  max-height: calc(100dvh - 176px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.template-import-candidates__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.template-import-candidates__selection {
  font-size: 12px;
  color: #6b7280;
}

.template-import-candidates__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.template-import-candidates__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.template-candidate-card {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid transparent;
  border-radius: 20px;
  background: transparent;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    transform 0.2s ease;
}

.template-candidate-card:hover {
  background: rgba(17, 24, 39, 0.04);
}

.template-candidate-card.is-selected {
  border-color: rgba(59, 130, 246, 0.24);
  background: rgba(219, 234, 254, 0.42);
}

.template-candidate-card.is-active {
  background: rgba(17, 24, 39, 0.08);
  transform: translateY(-1px);
}

.template-candidate-card__select {
  flex-shrink: 0;
  padding-top: 2px;
}

.template-candidate-card__body {
  min-width: 0;
  flex: 1;
}

.template-candidate-card__head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.template-candidate-card__name {
  font-size: 14px;
  font-weight: 600;
  color: #161616;
}

.template-candidate-card__path {
  font-size: 12px;
  color: #7a7f87;
}

.template-candidate-card__desc {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.55;
  color: #4b5563;
}

.template-import-preview__body {
  width: min(100%, 920px);
  margin: 0 auto;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
}

.template-import-preview__selected {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: min(36dvh, 320px);
  padding: 14px 16px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.56);
  border: 1px solid rgba(229, 231, 235, 0.84);
  overflow: hidden;
}

.template-import-preview__selected-head {
  display: grid;
  gap: 4px;
}

.template-import-preview__selected-title {
  font-size: 14px;
  font-weight: 600;
  color: #161616;
}

.template-import-preview__selected-hint {
  font-size: 12px;
  line-height: 1.6;
  color: #6b7280;
}

.template-import-preview__selected-list {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  padding-right: 4px;
}

.template-import-preview__selected-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(229, 231, 235, 0.9);
  background: rgba(255, 255, 255, 0.72);
}

.template-import-preview__selected-card.is-active {
  border-color: rgba(59, 130, 246, 0.28);
  background: rgba(219, 234, 254, 0.42);
}

.template-import-preview__selected-main {
  min-width: 0;
  flex: 1;
}

.template-import-preview__selected-name {
  font-size: 14px;
  font-weight: 600;
  color: #161616;
}

.template-import-preview__selected-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: #7a7f87;
}

.template-import-preview__selected-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.template-import-preview__detail {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.template-import-preview__summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 0 10px;
  border-bottom: 1px solid rgba(229, 231, 235, 0.88);
}

.template-import-preview__summary-main {
  min-width: 0;
}

.template-import-preview__summary-side {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.template-import-preview__title {
  font-size: 28px;
  line-height: 1.14;
  font-weight: 600;
  color: #161616;
}

.template-import-preview__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  font-size: 12px;
  color: #6b7280;
}

.template-import-preview__pill {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(17, 24, 39, 0.05);
  font-size: 12px;
  color: #374151;
}

.template-import-preview__lead {
  font-size: 15px;
  line-height: 1.9;
  color: #374151;
}

.template-import-preview__focus {
  display: grid;
  gap: 8px;
  padding: 14px 18px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.56);
  border: 1px solid rgba(229, 231, 235, 0.84);
}

.template-import-preview__focus-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #8b7355;
}

.template-import-preview__focus-text {
  font-size: 16px;
  line-height: 1.8;
  color: #111827;
}

.template-import-preview__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.template-import-preview__panel {
  padding: 14px 16px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(229, 231, 235, 0.84);
}

.template-import-preview__panel-title {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #161616;
}

.template-import-preview__field-inline {
  font-size: 14px;
  line-height: 1.7;
  color: #374151;
}

.template-import-preview__list {
  margin: 0;
  padding-left: 18px;
  font-size: 14px;
  line-height: 1.8;
  color: #374151;
}

.template-import-preview__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.template-import-preview__tags :deep(.el-tag) {
  max-width: 100%;
  height: auto;
  white-space: normal;
  line-height: 1.5;
  align-items: flex-start;
  padding-top: 6px;
  padding-bottom: 6px;
}

.template-import-preview__tags :deep(.el-tag__content) {
  display: block;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.template-import-preview__policy {
  margin: 0;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.8;
  color: #374151;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

.template-import-preview__empty {
  font-size: 13px;
  color: #9ca3af;
}

.template-import-preview__options {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  padding-top: 4px;
}

.template-import-preview__empty-state {
  width: min(100%, 780px);
  margin: auto;
  text-align: center;
  padding: 64px 24px;
}

.template-import-preview__empty-title {
  font-size: 30px;
  line-height: 1.12;
  font-weight: 600;
  color: #161616;
}

.template-import-preview__empty-text {
  margin-top: 12px;
  font-size: 15px;
  line-height: 1.8;
  color: #6b7280;
}

.mcp-desc {
  margin-bottom: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.mcp-code-wrap {
  background: #1e1e1e;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}

.mcp-code {
  margin: 0;
  color: #d4d4d4;
  font-family: "Courier New", Courier, monospace;
  font-size: 13px;
  line-height: 1.4;
}

.test-stats-row {
  margin: 16px 0;
}

.test-section-title {
  margin: 16px 0 8px;
}

.issue-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.issue-tag {
  margin-right: 0;
}

.prompt-content {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 16px;
  max-height: 500px;
  overflow-y: auto;
}

.prompt-rendered {
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
}

.prompt-rendered h1,
.prompt-rendered h2,
.prompt-rendered h3,
.prompt-rendered h4 {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: 600;
}

.prompt-rendered h1 {
  font-size: 20px;
}
.prompt-rendered h2 {
  font-size: 18px;
}
.prompt-rendered h3 {
  font-size: 16px;
}
.prompt-rendered h4 {
  font-size: 14px;
}

.prompt-rendered ul,
.prompt-rendered ol {
  margin: 8px 0;
  padding-left: 24px;
}

.prompt-rendered li {
  margin: 4px 0;
}

.prompt-rendered code {
  background: #e6e8eb;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: "Courier New", Courier, monospace;
  font-size: 13px;
}

.prompt-rendered pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.prompt-rendered pre code {
  background: transparent;
  padding: 0;
  color: inherit;
}

.prompt-rendered p {
  margin: 8px 0;
}

.prompt-rendered strong {
  font-weight: 600;
}

@media (max-width: 1180px) {
  .template-import-shell {
    padding: 12px 14px 14px;
  }

  .template-import-hero {
    padding: 6px 12px 4px;
    flex-direction: column;
  }

  .template-import-hero__actions {
    width: 100%;
    justify-content: space-between;
  }

  .template-import-layout {
    grid-template-columns: 1fr;
  }

  .template-import-main {
    grid-template-columns: 1fr;
    max-height: none;
  }

  .template-import-preview {
    max-height: none;
    padding: 18px;
  }

  .template-import-candidates {
    max-height: min(44dvh, 420px);
  }

  .template-import-preview__grid {
    grid-template-columns: 1fr;
  }

  .template-import-preview__selected-list {
    flex: 1;
  }
}

@media (max-width: 720px) {
  .template-import-source__row {
    grid-template-columns: 1fr;
  }

  .template-import-hero__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .template-import-hero__status {
    white-space: normal;
  }

  .template-import-preview__summary {
    flex-direction: column;
  }

  .template-import-preview__summary-side {
    justify-content: flex-start;
  }

  .template-import-preview__title {
    font-size: 24px;
  }

  .template-import-candidates__toolbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .template-import-preview__selected-card {
    flex-direction: column;
  }

  .template-import-preview__selected-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
