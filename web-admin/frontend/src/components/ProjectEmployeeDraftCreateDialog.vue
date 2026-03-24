<template>
  <el-dialog
    :model-value="modelValue"
    title="确认创建 AI 员工"
    width="min(880px, calc(100vw - 32px))"
    destroy-on-close
    class="employee-draft-create-dialog"
    @update:model-value="handleVisibleChange"
    @close="handleClose"
  >
    <div
      v-if="payload"
      class="employee-draft-dialog"
      v-loading="loading"
    >
      <div class="employee-draft-dialog__summary">
        <div class="employee-draft-dialog__title">
          {{ payload.name || "未命名员工" }}
        </div>
        <div
          v-if="payload.description"
          class="employee-draft-dialog__desc"
        >
          {{ payload.description }}
        </div>
        <div class="employee-draft-dialog__meta">
          <span>核心目标：{{ payload.goal || "-" }}</span>
          <span>
            风格：{{ payload.tone || "professional" }} /
            {{ payload.verbosity || "concise" }}
          </span>
          <span>
            记忆：{{ payload.memory_scope || "project" }} /
            {{ payload.memory_retention_days || 90 }} 天
          </span>
        </div>
      </div>

      <div class="employee-draft-dialog__section">
        <div class="employee-draft-dialog__section-title">本地已匹配能力</div>
        <div class="employee-draft-dialog__grid">
          <div class="employee-draft-dialog__panel">
            <div class="employee-draft-dialog__panel-title">
              技能 {{ matchedSkillLabels.length }}
            </div>
            <div class="employee-draft-dialog__tag-list">
              <el-tag
                v-for="label in matchedSkillLabels"
                :key="`employee-draft-skill-${label}`"
                size="small"
                effect="plain"
              >
                {{ label }}
              </el-tag>
              <span
                v-if="!matchedSkillLabels.length"
                class="employee-draft-dialog__empty"
              >
                暂无可直接匹配的本地技能，将按下面开关决定是否自动补齐。
              </span>
            </div>
          </div>
          <div class="employee-draft-dialog__panel">
            <div class="employee-draft-dialog__panel-title">
              规则 {{ matchedRuleLabels.length }}
            </div>
            <div class="employee-draft-dialog__tag-list">
              <el-tag
                v-for="label in matchedRuleLabels"
                :key="`employee-draft-rule-${label}`"
                size="small"
                effect="plain"
                type="success"
              >
                {{ label }}
              </el-tag>
              <span
                v-if="!matchedRuleLabels.length"
                class="employee-draft-dialog__empty"
              >
                暂无可直接匹配的本地规则，将按下面开关决定是否自动补齐。
              </span>
            </div>
            <div
              v-if="ruleDraftLabels.length"
              class="employee-draft-dialog__subsection"
            >
              <div class="employee-draft-dialog__subsection-title">
                待落地规则草稿 {{ ruleDraftLabels.length }}
              </div>
              <div class="employee-draft-dialog__tag-list">
                <el-tag
                  v-for="label in ruleDraftLabels"
                  :key="`employee-draft-rule-draft-${label}`"
                  size="small"
                  effect="plain"
                  type="warning"
                >
                  {{ label }}
                </el-tag>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="employee-draft-dialog__section">
        <div class="employee-draft-dialog__section-head">
          <div class="employee-draft-dialog__section-title">规则自动生成</div>
          <el-tag
            size="small"
            effect="plain"
            :type="autoRuleGenerationEnabled ? 'success' : 'info'"
          >
            {{ autoRuleGenerationEnabled ? "系统已启用" : "系统已停用" }}
          </el-tag>
        </div>
        <div class="employee-draft-dialog__section-hint">
          规则不再由当前页面手动选择。创建时系统会按后台配置自动补全规则草稿，再落地并绑定到当前员工。
        </div>
        <div class="employee-draft-dialog__grid">
          <div class="employee-draft-dialog__panel">
            <div class="employee-draft-dialog__panel-title">当前策略</div>
            <div class="employee-draft-dialog__tag-list">
              <el-tag
                size="small"
                effect="plain"
                :type="autoRuleGenerationEnabled ? 'success' : 'info'"
              >
                {{
                  autoRuleGenerationEnabled
                    ? "自动生成已启用"
                    : "自动生成已停用"
                }}
              </el-tag>
              <el-tag
                v-if="autoRuleGenerationEnabled"
                size="small"
                effect="plain"
                type="warning"
              >
                最多 {{ autoRuleGenerationMaxCount }} 条
              </el-tag>
              <el-tag
                v-for="label in autoRuleSourceLabels"
                :key="`employee-draft-rule-source-${label}`"
                size="small"
                effect="plain"
              >
                {{ label }}
              </el-tag>
            </div>
            <div class="employee-draft-dialog__empty">
              {{
                autoRuleGenerationEnabled
                  ? "系统会结合员工描述、已选技能和系统规则源自动补全规则。"
                  : "当前系统配置已关闭自动补规则，仅使用已匹配规则和已有规则草稿。"
              }}
            </div>
          </div>
        </div>
      </div>

      <div class="employee-draft-dialog__section">
        <div class="employee-draft-dialog__section-title">创建策略</div>
        <div class="employee-draft-dialog__section-hint">
          员工技能仍以草稿内容和系统自动补齐为准。规则来源不在这里选择，而是由系统按后台配置自动生成。
        </div>
        <div class="employee-draft-dialog__switches">
          <el-switch
            v-model="autoCreateSkills"
            inline-prompt
            active-text="自动补技能"
            inactive-text="手动处理技能"
          />
          <el-switch
            v-model="autoCreateRules"
            inline-prompt
            active-text="自动补规则"
            inactive-text="手动处理规则"
          />
          <el-switch
            v-model="addToProject"
            inline-prompt
            active-text="加入当前项目"
            inactive-text="仅创建员工"
            :disabled="!canAddToProject"
          />
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleVisibleChange(false)">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!payload"
        @click="handleConfirm"
      >
        创建并绑定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  submitting: {
    type: Boolean,
    default: false,
  },
  payload: {
    type: Object,
    default: null,
  },
  matchedSkillLabels: {
    type: Array,
    default: () => [],
  },
  matchedRuleLabels: {
    type: Array,
    default: () => [],
  },
  ruleDraftLabels: {
    type: Array,
    default: () => [],
  },
  autoRuleGenerationEnabled: {
    type: Boolean,
    default: true,
  },
  autoRuleGenerationMaxCount: {
    type: Number,
    default: 3,
  },
  autoRuleSourceLabels: {
    type: Array,
    default: () => [],
  },
  canAddToProject: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["update:modelValue", "confirm", "close"]);

const autoCreateSkills = ref(true);
const autoCreateRules = ref(true);
const addToProject = ref(false);

watch(
  () => [props.modelValue, props.payload, props.canAddToProject],
  ([visible]) => {
    if (!visible) return;
    autoCreateSkills.value = true;
    autoCreateRules.value = true;
    addToProject.value = Boolean(props.canAddToProject);
  },
  { immediate: true, deep: true },
);

function handleVisibleChange(value) {
  emit("update:modelValue", Boolean(value));
}

function handleClose() {
  emit("close");
}

function handleConfirm() {
  emit("confirm", {
    auto_create_missing_skills: autoCreateSkills.value,
    auto_create_missing_rules: autoCreateRules.value,
    add_to_current_project: addToProject.value,
  });
}
</script>

<style scoped>
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

@media (max-width: 767px) {
  .employee-draft-dialog__grid {
    grid-template-columns: 1fr;
  }
}
</style>
