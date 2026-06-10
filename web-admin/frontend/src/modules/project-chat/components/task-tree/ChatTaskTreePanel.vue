<template>
  <el-drawer
    v-model="visibleModel"
    size="min(560px, calc(100vw - 24px))"
    title="当前执行任务"
    class="task-tree-drawer"
  >
    <div v-loading="loading" class="task-tree-panel">
      <div class="task-tree-panel__hero">
        <div>
          <div class="task-tree-panel__eyebrow">
            {{ readonly ? "Task Snapshot" : "Task Flow" }}
          </div>
          <div class="task-tree-panel__title">
            {{ taskTree?.root_goal || "当前会话还没有任务树" }}
          </div>
          <div class="task-tree-panel__meta">
            <span>状态 {{ taskTree?.status || "pending" }}</span>
            <span>进度 {{ progressLabel }}</span>
            <span v-if="taskTree?.stats?.leaf_total">
              已完成 {{ taskTree?.stats?.done_leaf_total || 0 }} /
              {{ taskTree?.stats?.leaf_total || 0 }}
            </span>
            <span v-if="readonly">只读快照</span>
          </div>
        </div>
        <div v-if="hasTaskTree && !readonly" class="task-tree-panel__actions">
          <el-button
            text
            type="danger"
            :icon="Delete"
            :disabled="saving"
            @click="$emit('delete-current')"
          >
            删除任务推进
          </el-button>
        </div>
      </div>

      <TaskTreeFeedbackBanner v-if="health" :health="health" />

      <div v-if="hasTaskTree" class="task-tree-panel__body">
        <div class="task-tree-panel__outline">
          <div class="task-tree-panel__section-head">
            <div>
              <div class="task-tree-panel__section-eyebrow">Task Nodes</div>
              <div class="task-tree-panel__section-title">执行路径</div>
            </div>
            <div class="task-tree-panel__section-meta">
              {{ taskTree?.stats?.leaf_total || 0 }} 个执行节点
            </div>
          </div>
          <el-tree
            :data="treeData"
            node-key="id"
            default-expand-all
            highlight-current
            :expand-on-click-node="false"
            :current-node-key="selectedNodeId"
            class="task-tree-panel__tree"
            @node-click="$emit('node-click', $event)"
          >
            <template #default="{ data }">
              <div class="task-tree-node">
                <div class="task-tree-node__copy">
                  <span class="task-tree-node__title" :title="data.title">
                    {{ data.title }}
                  </span>
                  <span v-if="isNodeCurrent(data)" class="task-tree-node__current">
                    当前
                  </span>
                </div>
                <el-tag
                  size="small"
                  effect="plain"
                  class="task-tree-node__status"
                  :type="statusTagType(data.status)"
                >
                  {{ formatStatusLabel(data.status) }}
                </el-tag>
              </div>
            </template>
          </el-tree>
        </div>

        <div v-if="selectedNode" class="task-tree-editor">
          <div class="task-tree-editor__head">
            <div>
              <div class="task-tree-editor__eyebrow">需求详情</div>
              <div class="task-tree-editor__title">
                {{ selectedNode.title }}
              </div>
            </div>
            <div class="task-tree-editor__meta">
              <span class="task-tree-editor__pill">
                {{ formatStatusLabel(selectedNode.status) }}
              </span>
              <span
                v-if="isNodeCurrent(selectedNode)"
                class="task-tree-editor__pill task-tree-editor__pill--current"
              >
                当前节点
              </span>
              <span v-if="selectedNodeChildCount" class="task-tree-editor__pill">
                {{ selectedNodeChildCount }} 个子节点
              </span>
            </div>
          </div>
          <p v-if="selectedNode.description" class="task-tree-editor__desc">
            {{ selectedNode.description }}
          </p>
          <div
            v-if="selectedNode.done_definition"
            class="task-tree-editor__section"
          >
            <div class="task-tree-editor__section-label">完成条件</div>
            <p>{{ selectedNode.done_definition }}</p>
          </div>
          <div
            v-if="selectedNode.verification_items?.length"
            class="task-tree-editor__section"
          >
            <div class="task-tree-editor__section-label">验证要求</div>
            <div class="task-tree-editor__checks">
              <div
                v-for="item in selectedNode.verification_items"
                :key="`${selectedNode.id}-${item}`"
                class="task-tree-editor__check"
              >
                <el-icon><CircleCheck /></el-icon>
                <span>{{ item }}</span>
              </div>
            </div>
          </div>
          <template v-if="readonly">
            <div
              v-if="selectedNode.verification_result"
              class="task-tree-editor__section task-tree-editor__section--result"
            >
              <div class="task-tree-editor__section-label">验证结果</div>
              <p>{{ selectedNode.verification_result }}</p>
            </div>
            <div
              v-if="selectedNode.summary_for_model"
              class="task-tree-editor__section"
            >
              <div class="task-tree-editor__section-label">节点摘要</div>
              <p>{{ selectedNode.summary_for_model }}</p>
            </div>
            <p
              v-if="
                !selectedNode.verification_result &&
                !selectedNode.summary_for_model
              "
              class="task-tree-editor__empty"
            >
              这个节点还没有补充验证结论。
            </p>
          </template>
          <template v-else>
            <div class="task-tree-editor__field">
              <div class="task-tree-editor__field-label">节点状态</div>
              <el-select v-model="statusDraftModel" class="task-tree-editor__select">
                <el-option
                  v-for="option in statusOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </div>
            <div class="task-tree-editor__field">
              <div class="task-tree-editor__field-label">验证结果</div>
              <el-input
                v-model="verificationDraftModel"
                type="textarea"
                :rows="4"
                :placeholder="verificationPlaceholder"
              />
            </div>
            <div class="task-tree-editor__hint">
              {{ saveHint }}
            </div>
            <div class="task-tree-editor__field">
              <div class="task-tree-editor__field-label">节点摘要</div>
              <el-input
                v-model="summaryDraftModel"
                type="textarea"
                :rows="3"
                placeholder="给模型的当前节点摘要，可填写已完成范围、剩余风险或下一步。"
              />
            </div>
            <div class="task-tree-editor__actions">
              <el-button
                text
                :icon="List"
                @click="$emit('save-node', { setCurrentOnly: true })"
              >
                设为当前
              </el-button>
              <el-button
                type="primary"
                :loading="saving"
                @click="$emit('save-node')"
              >
                保存节点状态
              </el-button>
            </div>
          </template>
        </div>
        <div v-else class="task-tree-editor task-tree-editor--empty">
          <div class="task-tree-editor__eyebrow">需求详情</div>
          <div class="task-tree-editor__title">选择一个节点</div>
          <p class="task-tree-editor__empty">
            左侧只保留执行路径，点击节点后再看当前目标、验证要求和结果。
          </p>
        </div>
      </div>

      <el-empty
        v-else
        description="发送首条任务消息后，系统会自动生成结构化执行树。"
        :image-size="72"
      />
    </div>
  </el-drawer>
</template>

<script setup>
import { computed } from "vue";
import { CircleCheck, Delete, List } from "@element-plus/icons-vue";
import TaskTreeFeedbackBanner from "@/modules/task-tree-feedback/TaskTreeFeedbackBanner.vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  taskTree: { type: Object, default: null },
  health: { type: Object, default: null },
  hasTaskTree: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
  progressLabel: { type: String, default: "未拆解" },
  treeData: { type: Array, default: () => [] },
  selectedNodeId: { type: String, default: "" },
  selectedNode: { type: Object, default: null },
  selectedNodeChildCount: { type: Number, default: 0 },
  statusOptions: { type: Array, default: () => [] },
  statusDraft: { type: String, default: "pending" },
  verificationDraft: { type: String, default: "" },
  summaryDraft: { type: String, default: "" },
  verificationPlaceholder: { type: String, default: "" },
  saveHint: { type: String, default: "" },
});

const emit = defineEmits([
  "update:modelValue",
  "update:statusDraft",
  "update:verificationDraft",
  "update:summaryDraft",
  "delete-current",
  "node-click",
  "save-node",
]);

const visibleModel = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

const statusDraftModel = computed({
  get: () => props.statusDraft,
  set: (value) => emit("update:statusDraft", value),
});

const verificationDraftModel = computed({
  get: () => props.verificationDraft,
  set: (value) => emit("update:verificationDraft", value),
});

const summaryDraftModel = computed({
  get: () => props.summaryDraft,
  set: (value) => emit("update:summaryDraft", value),
});

function formatStatusLabel(status) {
  const normalized = String(status || "").trim();
  const matched = props.statusOptions.find(
    (option) => option.value === normalized,
  );
  return matched?.label || normalized || "待开始";
}

function isNodeCurrent(node) {
  const currentNodeId = String(props.taskTree?.current_node_id || "").trim();
  if (!currentNodeId) return false;
  return currentNodeId === String(node?.id || "").trim();
}

function statusTagType(status) {
  const normalized = String(status || "").trim();
  if (normalized === "done") return "success";
  if (normalized === "blocked") return "danger";
  if (normalized === "verifying") return "warning";
  if (normalized === "in_progress") return "";
  return "info";
}
</script>

<style scoped src="./ChatTaskTreePanel.css"></style>
