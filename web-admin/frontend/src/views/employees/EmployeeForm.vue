<template>
  <div class="employee-create" v-loading="pageLoading">
    <h3>{{ pageTitle }}</h3>
    <p class="page-hint">{{ pageHint }}</p>

    <el-steps :active="currentStep" finish-status="success" class="steps">
      <el-step title="基础信息" description="名称与定位" />
      <el-step title="能力绑定" description="技能与规则" />
      <el-step title="人设与进化" description="行为风格与学习策略" />
    </el-steps>

    <el-form
      :model="form"
      :rules="rules"
      ref="formRef"
      label-width="120px"
      class="form-wrap"
    >
      <template v-if="currentStep === 0">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：前端专家小王" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="描述这个员工擅长什么、在什么场景下使用"
          />
          <div class="field-hint">用于团队识别员工职责，不填也可创建。</div>
        </el-form-item>
        <el-form-item label="核心目标">
          <el-input
            v-model="form.goal"
            type="textarea"
            :rows="3"
            placeholder="例如：优先把模糊需求收敛成可执行方案，并给出风险与边界。"
          />
          <div class="field-hint">
            定义该员工判断任务和输出结果时最优先追求的目标。
          </div>
        </el-form-item>
      </template>

      <template v-else-if="currentStep === 1">
        <el-form-item label="技能配置">
          <el-select
            v-model="form.skills"
            class="select-wide"
            multiple
            filterable
            clearable
            collapse-tags
            collapse-tags-tooltip
            :disabled="optionsLoading"
            placeholder="从系统技能目录选择技能"
          >
            <el-option
              v-for="s in availableSkills"
              :key="s.id"
              :label="`${s.name} (${s.id})`"
              :value="s.id"
            />
          </el-select>
          <div class="field-hint">技能决定该员工可调用的能力。</div>
          <div class="field-hint">
            当前已选 {{ form.skills.length }} 项，共 {{ availableSkills.length }} 项可选。
          </div>
          <div
            v-if="!optionsLoading && !availableSkills.length"
            class="empty-action"
          >
            <span>暂无可选技能。</span>
            <el-button link type="primary" @click="goToSkills"
              >去导入技能</el-button
            >
          </div>
        </el-form-item>

        <el-form-item label="已选技能">
          <div class="selected-line">
            <el-tag
              v-for="skill in selectedSkills"
              :key="skill.id"
              closable
              class="selected-tag"
              @close="removeSelectedSkill(skill.id)"
            >
              {{ skill.name }} ({{ skill.id }})
            </el-tag>
            <span v-if="!selectedSkills.length" class="preview-empty">未选择</span>
          </div>
          <div class="field-hint">可直接点击标签关闭，快速取消已选技能。</div>
        </el-form-item>

        <el-form-item label="规则绑定">
          <div class="rule-bind-box">
            <div class="rule-bind-section">
              <div class="rule-bind-label">先筛选领域（可多选）</div>
              <el-checkbox-group
                v-model="ruleDomainFilters"
                class="domain-checkbox-group"
                :disabled="optionsLoading"
              >
                <el-checkbox
                  v-for="d in availableDomains"
                  :key="d"
                  :label="d"
                  :value="d"
                  class="domain-checkbox"
                >
                  {{ d }}
                </el-checkbox>
              </el-checkbox-group>
              <div class="field-hint">不勾选任何领域时，默认显示全部领域规则。</div>
            </div>

            <div class="rule-bind-section">
              <div class="rule-bind-label">再选择规则标题</div>
              <el-select
                v-model="selectedRuleIds"
                class="select-wide"
                multiple
                filterable
                clearable
                collapse-tags
                collapse-tags-tooltip
                :disabled="optionsLoading"
                :placeholder="ruleSelectPlaceholder"
              >
                <el-option
                  v-for="rule in ruleSelectOptions"
                  :key="rule.id"
                  :label="rule.title"
                  :value="rule.id"
                />
              </el-select>
            </div>
          </div>
          <div class="rule-action-row">
            <el-button
              size="small"
              text
              type="primary"
              :disabled="!filteredRules.length"
              @click="selectAllFilteredRules"
            >
              全选当前筛选
            </el-button>
            <el-button
              size="small"
              text
              :disabled="!selectedRuleIds.length"
              @click="clearAllSelectedRules"
            >
              清空已选
            </el-button>
          </div>
          <div class="field-hint">
            同一字段内完成筛选与绑定：领域仅用于筛选，实际提交字段为 rule_bindings。
            <span class="count-text">当前可选 {{ filteredRules.length }} 条。</span>
          </div>
          <div
            v-if="!optionsLoading && !filteredRules.length"
            class="empty-action"
          >
            <span>当前筛选下暂无可选规则。</span>
            <el-button link type="primary" @click="goToRuleCreate"
              >去创建规则</el-button
            >
          </div>
        </el-form-item>

        <el-form-item label="已选规则">
          <div v-if="selectedRules.length" class="selected-rules-panel">
            <div class="selected-rules-head">共 {{ selectedRules.length }} 条</div>
            <el-table
              :data="selectedRules"
              size="small"
              border
              class="selected-rules-table"
            >
              <el-table-column type="index" label="#" width="52" />
              <el-table-column prop="title" label="规则标题" min-width="280" show-overflow-tooltip />
              <el-table-column prop="domain" label="领域" width="160" show-overflow-tooltip />
              <el-table-column prop="id" label="规则 ID" min-width="150" show-overflow-tooltip />
              <el-table-column label="操作" width="78" fixed="right">
                <template #default="{ row }">
                  <el-button text type="danger" @click="removeSelectedRule(row.id)">移除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <span v-else class="preview-empty">未选择</span>
          <div class="field-hint">支持完整查看已选规则，避免标签折叠导致信息不全。</div>
        </el-form-item>

        <el-form-item label="记忆作用域">
          <el-radio-group v-model="form.memory_scope">
            <el-radio value="project">项目级别</el-radio>
            <el-radio value="global">全局</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="记忆保留天数">
          <el-input-number
            v-model="form.memory_retention_days"
            :min="7"
            :max="365"
          />
        </el-form-item>
      </template>

      <template v-else>
        <el-form-item label="语调">
          <el-select v-model="form.tone">
            <el-option label="专业" value="professional" />
            <el-option label="友好" value="friendly" />
            <el-option label="严格" value="strict" />
            <el-option label="导师" value="mentor" />
          </el-select>
        </el-form-item>

        <el-form-item label="风格">
          <el-select v-model="form.verbosity">
            <el-option label="详细" value="verbose" />
            <el-option label="简洁" value="concise" />
            <el-option label="极简" value="minimal" />
          </el-select>
        </el-form-item>

        <el-form-item label="语言">
          <el-select v-model="form.language">
            <el-option label="简体中文" value="zh-CN" />
            <el-option label="English" value="en-US" />
          </el-select>
        </el-form-item>

        <el-form-item label="风格提示">
          <div class="field-hint style-hint-desc">
            用于约束回答表达方式（不是业务规则），例如“先结论后步骤”“输出清单化”。
          </div>
          <div class="style-preset-row">
            <el-tag
              v-for="preset in styleHintPresets"
              :key="preset"
              class="style-preset-tag"
              :type="form.style_hints.includes(preset) ? 'success' : 'info'"
              @click="addStyleHintPreset(preset)"
            >
              {{ preset }}
            </el-tag>
          </div>
          <div v-for="(hint, i) in form.style_hints" :key="i" class="hint-row">
            <el-input
              v-model="form.style_hints[i]"
              size="small"
              placeholder="例如：先给结论，再给操作步骤"
            />
            <el-button
              text
              type="danger"
              size="small"
              @click="removeStyleHint(i)"
              >删除</el-button
            >
          </div>
          <el-button
            text
            type="primary"
            size="small"
            @click="addStyleHintRow()"
            >+ 添加提示</el-button
          >
          <div class="field-hint">获取方式：可从团队写作规范、评审高频意见、优秀历史回复中提炼。</div>
        </el-form-item>

        <el-form-item label="默认工作流">
          <div class="field-hint style-hint-desc">
            定义该员工处理任务时优先遵循的步骤顺序。
          </div>
          <div class="style-preset-row">
            <el-tag
              v-for="preset in workflowPresets"
              :key="preset"
              class="style-preset-tag"
              :type="form.default_workflow.includes(preset) ? 'success' : 'info'"
              @click="addWorkflowPreset(preset)"
            >
              {{ preset }}
            </el-tag>
          </div>
          <div
            v-for="(step, i) in form.default_workflow"
            :key="`workflow-${i}`"
            class="hint-row"
          >
            <el-input
              v-model="form.default_workflow[i]"
              size="small"
              placeholder="例如：先确认目标与约束"
            />
            <el-button
              text
              type="danger"
              size="small"
              @click="removeWorkflowStep(i)"
              >删除</el-button
            >
          </div>
          <el-button
            text
            type="primary"
            size="small"
            @click="addWorkflowRow()"
            >+ 添加步骤</el-button
          >
        </el-form-item>

        <el-form-item label="工具使用策略">
          <el-input
            v-model="form.tool_usage_policy"
            type="textarea"
            :rows="4"
            placeholder="例如：遇到项目上下文、规则、MCP、真实配置时优先查工具，不要凭空假设。"
          />
          <div class="field-hint">
            用来约束员工何时主动调用技能、规则或 MCP 工具。
          </div>
        </el-form-item>

        <el-form-item label="自动学习">
          <el-switch v-model="form.auto_evolve" />
        </el-form-item>

        <el-form-item label="反馈升级">
          <el-switch v-model="form.feedback_upgrade_enabled" />
          <div class="field-hint">
            开启后会在员工 MCP 中暴露反馈闭环工具（提交反馈、反思、审核、发布、回滚）。
          </div>
        </el-form-item>

        <el-form-item label="入库阈值" v-if="form.auto_evolve">
          <el-slider
            v-model="form.evolve_threshold"
            :min="0.5"
            :max="1"
            :step="0.05"
            show-input
          />
          <div class="field-hint">
            阈值越低越激进，阈值越高越保守。推荐值：0.80。
          </div>
        </el-form-item>

        <el-card class="preview-card" shadow="never">
          <template #header>{{ previewTitle }}</template>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="名称">{{
              form.name || "-"
            }}</el-descriptions-item>
            <el-descriptions-item label="核心目标">{{
              form.goal || "-"
            }}</el-descriptions-item>
            <el-descriptions-item label="语调">{{
              form.tone
            }}</el-descriptions-item>
            <el-descriptions-item label="技能数">{{
              form.skills.length
            }}</el-descriptions-item>
            <el-descriptions-item label="规则数">{{
              selectedRuleIds.length
            }}</el-descriptions-item>
            <el-descriptions-item label="规则领域数">{{
              selectedRuleDomains.length
            }}</el-descriptions-item>
            <el-descriptions-item label="记忆作用域">{{
              form.memory_scope
            }}</el-descriptions-item>
            <el-descriptions-item label="自动学习">{{
              form.auto_evolve ? "开启" : "关闭"
            }}</el-descriptions-item>
            <el-descriptions-item label="反馈升级">{{
              form.feedback_upgrade_enabled ? "开启" : "关闭"
            }}</el-descriptions-item>
          </el-descriptions>
          <div class="preview-tags">
            <span class="preview-label">技能：</span>
            <el-tag
              v-for="label in selectedSkillLabels"
              :key="label"
              size="small"
              class="preview-tag"
            >
              {{ label }}
            </el-tag>
            <span v-if="!selectedSkillLabels.length" class="preview-empty"
              >未选择</span
            >
          </div>
          <div class="preview-tags">
            <span class="preview-label">规则标题：</span>
            <el-tag
              v-for="title in selectedRuleTitles"
              :key="title"
              size="small"
              class="preview-tag"
            >
              {{ title }}
            </el-tag>
            <span v-if="!selectedRuleTitles.length" class="preview-empty"
              >未选择</span
            >
          </div>
          <div class="preview-tags">
            <span class="preview-label">规则领域：</span>
            <el-tag
              v-for="domain in selectedRuleDomains"
              :key="domain"
              size="small"
              class="preview-tag"
            >
              {{ domain }}
            </el-tag>
            <span v-if="!selectedRuleDomains.length" class="preview-empty"
              >未选择</span
            >
          </div>
          <div class="preview-tags">
            <span class="preview-label">默认工作流：</span>
            <el-tag
              v-for="step in normalizedWorkflow"
              :key="step"
              size="small"
              class="preview-tag"
            >
              {{ step }}
            </el-tag>
            <span v-if="!normalizedWorkflow.length" class="preview-empty"
              >未设置</span
            >
          </div>
        </el-card>
      </template>

      <el-form-item class="step-actions">
        <el-button v-if="currentStep > 0" @click="prevStep">上一步</el-button>
        <el-button v-if="currentStep < 2" type="primary" @click="nextStep"
          >下一步</el-button
        >
        <el-button
          v-else
          type="primary"
          :loading="submitting"
          @click="handleSubmit"
          >{{ submitLabel }}</el-button
        >
        <el-button @click="$router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import api from "@/utils/api.js";
import { getOwnershipDeniedMessage } from "@/utils/ownership.js";
import { canCreateEmployee, canUpdateEmployee } from "@/utils/employee-permissions.js";

const route = useRoute();
const router = useRouter();

const isEdit = computed(() => Boolean(route.params.id));
const pageTitle = computed(() => (isEdit.value ? "编辑 AI 员工" : "创建 AI 员工"));
const pageHint = computed(() =>
  isEdit.value
    ? "按 3 步完成修改：基础信息、能力绑定、人设与进化。"
    : "按 3 步完成配置：基础信息、能力绑定、人设与进化。"
);
const previewTitle = computed(() => (isEdit.value ? "修改预览" : "创建预览"));
const submitLabel = computed(() => (isEdit.value ? "保存修改" : "创建 AI 员工"));

const formRef = ref(null);
const pageLoading = ref(false);
const submitting = ref(false);
const optionsLoading = ref(false);
const currentStep = ref(0);
const availableSkills = ref([]);
const availableRules = ref([]);
const ruleDomainFilters = ref([]);
const selectedRuleIds = ref([]);
const initialRuleIds = ref([]);

const form = reactive({
  name: "",
  description: "",
  goal: "",
  skills: [],
  memory_scope: "project",
  memory_retention_days: 90,
  tone: "professional",
  verbosity: "concise",
  language: "zh-CN",
  style_hints: [],
  default_workflow: [],
  tool_usage_policy: "",
  auto_evolve: true,
  evolve_threshold: 0.8,
  feedback_upgrade_enabled: false,
});

const rules = {
  name: [{ required: true, message: "请输入员工名称", trigger: "blur" }],
};

const styleHintPresets = [
  "先给结论后给步骤",
  "输出结构化清单",
  "标注风险与前置条件",
  "给出可执行命令示例",
  "默认使用简洁中文",
];

const workflowPresets = [
  "先确认目标与约束",
  "先检索上下文再判断",
  "先给结论再展开步骤",
  "先标风险再给建议",
  "结尾补充下一步行动",
];

const selectedSkillLabels = computed(() => {
  const map = new Map(availableSkills.value.map((s) => [s.id, s.name]));
  return form.skills.map((id) => `${map.get(id) || id} (${id})`);
});

const selectedSkills = computed(() => {
  const map = new Map(availableSkills.value.map((s) => [s.id, s.name]));
  return form.skills.map((id) => ({
    id,
    name: map.get(id) || id,
  }));
});

const ruleMap = computed(() =>
  new Map(availableRules.value.map((rule) => [rule.id, rule]))
);

function normalizeDomain(domain) {
  return String(domain || "")
    .trim()
    .toLowerCase();
}

function normalizeStyleHints(hints) {
  const seen = new Set();
  const result = [];
  for (const item of hints || []) {
    const value = String(item || "").trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}

function normalizeWorkflow(steps) {
  const seen = new Set();
  const result = [];
  for (const item of steps || []) {
    const value = String(item || "").trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}

const normalizedWorkflow = computed(() => normalizeWorkflow(form.default_workflow));

function extractRuleIdsFromBindings(ruleBindings) {
  if (!Array.isArray(ruleBindings)) return [];
  const ids = [];
  for (const item of ruleBindings) {
    if (typeof item === "string") {
      const ruleId = String(item || "").trim();
      if (ruleId) ids.push(ruleId);
      continue;
    }
    if (item && typeof item === "object") {
      const ruleId = String(item.id || "").trim();
      if (ruleId) ids.push(ruleId);
    }
  }
  return Array.from(new Set(ids));
}

function ensureOptionCoverage() {
  const skillIds = new Set(availableSkills.value.map((s) => s.id));
  for (const skillId of form.skills || []) {
    if (!skillIds.has(skillId)) {
      availableSkills.value.push({ id: skillId, name: `${skillId} (历史配置)` });
      skillIds.add(skillId);
    }
  }
}

const availableDomains = computed(() => {
  const seen = new Set();
  const domains = [];
  for (const rule of availableRules.value) {
    const domain = String(rule.domain || "").trim();
    const normalized = normalizeDomain(domain);
    if (!domain || seen.has(normalized)) continue;
    seen.add(normalized);
    domains.push(domain);
  }
  return domains;
});

const filteredRules = computed(() => {
  if (!ruleDomainFilters.value.length) return availableRules.value;
  const targets = new Set(
    ruleDomainFilters.value.map(normalizeDomain).filter(Boolean)
  );
  return availableRules.value.filter((rule) =>
    targets.has(normalizeDomain(rule.domain))
  );
});

const selectedRules = computed(() =>
  selectedRuleIds.value
    .map((id) => ruleMap.value.get(id))
    .filter(Boolean)
);

const selectedRuleTitles = computed(() =>
  selectedRules.value.map((rule) => rule.title)
);

const selectedRuleDomains = computed(() => {
  const seen = new Set();
  const domains = [];
  for (const rule of selectedRules.value) {
    const domain = String(rule?.domain || "").trim();
    const normalized = normalizeDomain(domain);
    if (!domain || seen.has(normalized)) continue;
    seen.add(normalized);
    domains.push(domain);
  }
  return domains;
});

const ruleSelectOptions = computed(() => {
  const map = new Map();
  for (const rule of filteredRules.value) {
    map.set(rule.id, rule);
  }
  for (const rule of selectedRules.value) {
    map.set(rule.id, rule);
  }
  return Array.from(map.values());
});

const ruleSelectPlaceholder = computed(() =>
  optionsLoading.value
    ? "规则加载中..."
    : `从系统规则中选择标题（当前可选 ${filteredRules.value.length} 条）`
);

async function nextStep() {
  if (currentStep.value === 0) {
    try {
      await formRef.value.validateField(["name"]);
    } catch {
      return;
    }
  }
  if (currentStep.value < 2) {
    currentStep.value += 1;
  }
}

function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value -= 1;
  }
}

function goToSkills() {
  router.push("/skills/create");
}

function goToRuleCreate() {
  router.push("/rules/create");
}

function removeSelectedSkill(skillId) {
  form.skills = form.skills.filter((id) => id !== skillId);
}

function removeSelectedRule(ruleId) {
  selectedRuleIds.value = selectedRuleIds.value.filter((id) => id !== ruleId);
}

function selectAllFilteredRules() {
  const idSet = new Set(selectedRuleIds.value);
  for (const rule of filteredRules.value) {
    idSet.add(rule.id);
  }
  selectedRuleIds.value = Array.from(idSet);
}

function clearAllSelectedRules() {
  selectedRuleIds.value = [];
}

function addStyleHintRow() {
  form.style_hints.push("");
}

function removeStyleHint(index) {
  form.style_hints.splice(index, 1);
}

function addStyleHintPreset(preset) {
  if (form.style_hints.includes(preset)) return;
  form.style_hints.push(preset);
}

function addWorkflowRow() {
  form.default_workflow.push("");
}

function removeWorkflowStep(index) {
  form.default_workflow.splice(index, 1);
}

function addWorkflowPreset(preset) {
  if (form.default_workflow.includes(preset)) return;
  form.default_workflow.push(preset);
}

async function fetchDetail() {
  const employeeId = String(route.params.id || "");
  if (!employeeId) return true;
  const { employee } = await api.get(`/employees/${employeeId}`);
  if (!canUpdateEmployee(employee)) {
    ElMessage.warning(getOwnershipDeniedMessage(employee, "编辑"));
    await router.replace(`/employees/${employeeId}`);
    return false;
  }
  Object.assign(form, {
    name: employee.name || "",
    description: employee.description || "",
    goal: employee.goal || "",
    skills: employee.skills || [],
    memory_scope: employee.memory_scope || "project",
    memory_retention_days: employee.memory_retention_days ?? 90,
    tone: employee.tone || "professional",
    verbosity: employee.verbosity || "concise",
    language: employee.language || "zh-CN",
    style_hints: employee.style_hints || [],
    default_workflow: employee.default_workflow || [],
    tool_usage_policy: employee.tool_usage_policy || "",
    auto_evolve: employee.auto_evolve ?? true,
    evolve_threshold: employee.evolve_threshold ?? 0.8,
    feedback_upgrade_enabled: employee.feedback_upgrade_enabled ?? false,
  });
  initialRuleIds.value = extractRuleIdsFromBindings(employee.rule_bindings);
  return true;
}

async function fetchSelectionOptions() {
  optionsLoading.value = true;
  try {
    const [skillsRes, rulesRes] = await Promise.all([
      api.get("/skills"),
      api.get("/rules"),
    ]);
    availableSkills.value = (skillsRes.skills || []).map((s) => ({
      id: s.id,
      name: s.name || s.id,
    }));
    availableRules.value = (rulesRes.rules || []).map((rule) => ({
      id: rule.id,
      title: String(rule.title || rule.id || "").trim(),
      domain: String(rule.domain || "").trim(),
    }));
    ensureOptionCoverage();
    if (initialRuleIds.value.length) {
      const knownRuleIds = new Set(availableRules.value.map((rule) => rule.id));
      for (const ruleId of initialRuleIds.value) {
        if (knownRuleIds.has(ruleId)) continue;
        availableRules.value.push({
          id: ruleId,
          title: `${ruleId} (历史配置)`,
          domain: "",
        });
        knownRuleIds.add(ruleId);
      }
      selectedRuleIds.value = Array.from(
        new Set(initialRuleIds.value.map((item) => String(item || "").trim()).filter(Boolean))
      );
      if (!ruleDomainFilters.value.length && selectedRuleDomains.value.length) {
        const targetDomains = new Set(selectedRuleDomains.value.map(normalizeDomain));
        ruleDomainFilters.value = availableDomains.value.filter((domain) =>
          targetDomains.has(normalizeDomain(domain))
        );
      }
    }
  } finally {
    optionsLoading.value = false;
  }
}

async function handleSubmit() {
  await formRef.value.validate();
  submitting.value = true;
  try {
    const payload = {
      ...form,
      rule_bindings: selectedRuleIds.value.map((ruleId) => {
        const rule = ruleMap.value.get(ruleId);
        return {
          id: ruleId,
          title: String(rule?.title || "").trim(),
          domain: String(rule?.domain || "").trim(),
        };
      }),
      style_hints: normalizeStyleHints(form.style_hints),
      default_workflow: normalizeWorkflow(form.default_workflow),
    };
    if (isEdit.value) {
      const employeeId = String(route.params.id || "");
      await api.put(`/employees/${employeeId}`, payload);
      ElMessage.success("员工已保存");
      router.push(`/employees/${employeeId}`);
    } else {
      const { employee } = await api.post("/employees", payload);
      ElMessage.success(`员工「${employee.name}」创建成功`);
      router.push("/employees");
    }
  } catch (e) {
    ElMessage.error(e.detail || (isEdit.value ? "保存失败" : "创建失败"));
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  pageLoading.value = true;
  try {
    if (!isEdit.value && !canCreateEmployee()) {
      ElMessage.warning("当前角色没有创建员工权限");
      await router.replace("/employees");
      return;
    }
    if (isEdit.value) {
      const ok = await fetchDetail();
      if (!ok) return;
    }
    await fetchSelectionOptions();
  } catch {
    ElMessage.error(isEdit.value ? "加载员工数据失败" : "加载技能/规则选项失败");
  } finally {
    pageLoading.value = false;
  }
});
</script>

<style scoped>
.employee-create {
  width: 100%;
  max-width: 980px;
  margin: 0 auto;
  padding: 24px 28px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 8px;
  background: var(--color-bg-container);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.page-hint {
  margin: 0 0 16px;
  color: var(--color-text-secondary);
}

.steps {
  margin-bottom: 20px;
}

.form-wrap {
  max-width: 760px;
}

.select-wide {
  width: 100%;
}

.field-hint {
  margin-top: 8px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.count-text {
  margin-left: 6px;
}

.rule-bind-box {
  width: 100%;
}

.rule-bind-section + .rule-bind-section {
  margin-top: 8px;
}

.rule-bind-label {
  margin-bottom: 6px;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.domain-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.domain-checkbox {
  margin-right: 0;
}

.rule-action-row {
  margin-top: 6px;
}

.selected-line {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  overflow-x: auto;
  white-space: nowrap;
  padding-bottom: 2px;
}

.selected-rule-line {
  border: 1px solid var(--color-border-secondary);
  border-radius: 6px;
  padding: 6px 8px;
  background: var(--color-primary-1);
}

.selected-tag {
  flex: 0 0 auto;
}

.selected-rules-panel {
  width: 100%;
}

.selected-rules-head {
  margin-bottom: 8px;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.selected-rules-table {
  width: 100%;
}

.empty-action {
  margin-top: 8px;
  color: var(--el-color-warning);
  display: flex;
  align-items: center;
  gap: 8px;
}

.hint-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.style-hint-desc {
  margin-bottom: 6px;
}

.style-preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.style-preset-tag {
  cursor: pointer;
}

.preview-card {
  margin-top: 16px;
}

.preview-tags {
  margin-top: 12px;
}

.preview-label {
  color: var(--color-text-secondary);
  margin-right: 8px;
}

.preview-tag {
  margin-right: 6px;
  margin-bottom: 6px;
}

.preview-empty {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.step-actions {
  margin-top: 16px;
}

:deep(h3) {
  color: var(--color-text-primary);
}

:deep(.el-form-item__label),
:deep(.el-step__title.is-process),
:deep(.el-step__title.is-wait),
:deep(.el-step__description) {
  color: var(--color-text-secondary);
}

:deep(.el-divider__text) {
  color: var(--color-text-primary);
  background: var(--color-bg-container);
}

:deep(.el-card.preview-card) {
  background: var(--color-bg-container);
  border-color: var(--color-border-secondary);
}

:deep(.el-card.preview-card .el-card__header),
:deep(.el-card.preview-card .el-descriptions__label),
:deep(.el-card.preview-card .el-descriptions__content) {
  color: var(--color-text-primary);
}

:deep(.step-actions .el-button--primary) {
  background: var(--color-primary-6);
  border-color: var(--color-primary-6);
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.28);
}

:deep(.step-actions .el-button--primary:hover) {
  background: var(--color-primary-5);
  border-color: var(--color-primary-5);
  box-shadow: 0 6px 16px rgba(22, 119, 255, 0.34);
}

:deep(.step-actions .el-button--primary:active) {
  background: var(--color-primary-7);
  border-color: var(--color-primary-7);
}
</style>
