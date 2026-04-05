<template>
  <div
    class="requirement-tree-node"
    :class="{
      'requirement-tree-node--current': isCurrent,
      'requirement-tree-node--done': normalizedStatus === 'done',
      'requirement-tree-node--goal': normalizedKind === 'goal',
    }"
    :style="treeStyleVars"
  >
    <article
      class="requirement-tree-node__card"
      role="button"
      tabindex="0"
      @click="emit('select', props.node)"
      @keydown.enter.prevent="emit('select', props.node)"
      @keydown.space.prevent="emit('select', props.node)"
    >
      <div class="requirement-tree-node__head">
        <div class="requirement-tree-node__head-copy">
          <span class="requirement-tree-node__eyebrow">{{ kindLabel }}</span>
          <h5>{{ nodeTitle }}</h5>
        </div>
        <div class="requirement-tree-node__head-tags">
          <span
            v-if="childCount"
            class="requirement-tree-node__branch-badge"
          >
            {{ childCount }} 个子节点
          </span>
          <el-tag
            size="small"
            effect="plain"
            :type="statusTagType"
          >
            {{ statusLabel }}
          </el-tag>
          <el-tag
            v-if="isCurrent"
            size="small"
            effect="plain"
            type="warning"
          >
            当前节点
          </el-tag>
        </div>
      </div>

      <p v-if="objectiveText" class="requirement-tree-node__objective">
        {{ objectiveText }}
      </p>

      <div class="requirement-tree-node__signals">
        <span v-if="childCount">{{ childCount }} 个子节点</span>
        <span v-if="completionSignalText">{{ completionSignalText }}</span>
        <span v-if="verificationCount">{{ verificationCount }} 条验证</span>
        <span v-if="outcomeSignalText">{{ outcomeSignalText }}</span>
      </div>

      <div
        v-if="showExpandedSections && completionText"
        class="requirement-tree-node__section"
      >
        <span>完成条件</span>
        <p>{{ completionText }}</p>
      </div>

      <div
        v-if="showExpandedSections && verificationText"
        class="requirement-tree-node__section"
      >
        <span>验证方式</span>
        <p>{{ verificationText }}</p>
      </div>

      <div
        v-if="showExpandedSections && outcomeText"
        class="requirement-tree-node__section requirement-tree-node__section--result"
      >
        <span>{{ outcomeLabel }}</span>
        <p>{{ outcomeText }}</p>
      </div>
    </article>

    <div v-if="childNodes.length" class="requirement-tree-node__children">
      <div class="requirement-tree-node__branch-label">子节点</div>
      <div class="requirement-tree-node__child-list">
        <RequirementTreeNode
          v-for="child in childNodes"
          :key="child.id"
          :node="child"
          :current-node-id="currentNodeId"
          :level="level + 1"
          :show-details="showDetails"
          @select="emit('select', $event)"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

defineOptions({
  name: "RequirementTreeNode",
});

const props = defineProps({
  node: {
    type: Object,
    required: true,
  },
  currentNodeId: {
    type: String,
    default: "",
  },
  level: {
    type: Number,
    default: 0,
  },
  showDetails: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["select"]);

const childNodes = computed(() =>
  Array.isArray(props.node?.children) ? props.node.children.filter(Boolean) : [],
);

const childCount = computed(() => childNodes.value.length);
const normalizedStatus = computed(() => String(props.node?.status || "").trim().toLowerCase());
const normalizedKind = computed(() => String(props.node?.node_kind || "").trim().toLowerCase());
const isCurrent = computed(() => String(props.node?.id || "").trim() === String(props.currentNodeId || "").trim());
const treeStyleVars = computed(() => ({
  "--requirement-tree-level": String(Math.max(0, Number(props.level || 0))),
}));
const nodeTitle = computed(() => String(props.node?.title || "未命名节点").trim() || "未命名节点");
const objectiveText = computed(() =>
  String(props.node?.objective || props.node?.description || "").trim(),
);
const completionText = computed(() =>
  String(props.node?.completion_criteria || props.node?.done_definition || "").trim(),
);
const verificationItems = computed(() =>
  Array.isArray(props.node?.verification_method)
    ? props.node.verification_method.map((item) => String(item || "").trim()).filter(Boolean)
    : [],
);
const verificationText = computed(() => verificationItems.value.join("\n"));
const verificationCount = computed(() => verificationItems.value.length);
const outcomeText = computed(() =>
  String(
    props.node?.verification_result
    || props.node?.latest_outcome
    || props.node?.summary_for_model
    || "",
  ).trim(),
);
const outcomeLabel = computed(() =>
  String(props.node?.verification_result || "").trim() ? "验证结果" : "当前结果",
);
const completionSignalText = computed(() => (completionText.value ? "已设完成条件" : ""));
const outcomeSignalText = computed(() => (outcomeText.value ? outcomeLabel.value : ""));
const showExpandedSections = computed(() => props.showDetails && (props.level === 0 || isCurrent.value));

const kindLabel = computed(() => {
  const stageKey = String(props.node?.stage_key || "").trim();
  const stageLabelMap = {
    goal: "总目标",
    analysis: "分析阶段",
    implementation: "执行阶段",
    verification: "验证阶段",
    repair: "修复阶段",
    context: "上下文整理",
    rule: "规则校验",
    execution: "执行步骤",
  };
  if (stageKey && stageLabelMap[stageKey]) {
    return stageLabelMap[stageKey];
  }
  if (normalizedKind.value === "goal") return "总目标";
  if (normalizedKind.value === "repair") return "修复阶段";
  if (normalizedKind.value === "verification") return "验证阶段";
  return props.level <= 1 ? "计划节点" : `第 ${props.level} 层节点`;
});

const statusLabel = computed(() => {
  if (normalizedStatus.value === "done") return "已完成";
  if (normalizedStatus.value === "blocked") return "阻塞";
  if (normalizedStatus.value === "verifying") return "验证中";
  if (normalizedStatus.value === "in_progress") return "进行中";
  if (normalizedStatus.value === "pending") return "待开始";
  return String(props.node?.status || "待开始").trim() || "待开始";
});

const statusTagType = computed(() => {
  if (normalizedStatus.value === "done") return "success";
  if (normalizedStatus.value === "blocked") return "danger";
  if (normalizedStatus.value === "verifying") return "warning";
  if (normalizedStatus.value === "in_progress") return "";
  return "info";
});
</script>

<style scoped>
.requirement-tree-node {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: 100%;
  min-width: 0;
  padding-left: calc(var(--requirement-tree-level, 0) * 14px);
}

.requirement-tree-node__card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: min(100%, 760px);
  padding: 16px 18px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.9));
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
  cursor: pointer;
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    border-color 180ms ease,
    background 180ms ease;
}

.requirement-tree-node__card:hover,
.requirement-tree-node__card:focus-visible {
  transform: translateY(-2px);
  border-color: rgba(14, 116, 144, 0.24);
  box-shadow: 0 20px 36px rgba(14, 116, 144, 0.12);
  outline: none;
}

.requirement-tree-node--goal .requirement-tree-node__card {
  background:
    radial-gradient(circle at top left, rgba(103, 232, 249, 0.14), transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(241, 245, 249, 0.96));
  border-color: rgba(148, 163, 184, 0.16);
}

.requirement-tree-node--current .requirement-tree-node__card {
  border-color: rgba(217, 119, 6, 0.24);
  box-shadow: 0 18px 36px rgba(217, 119, 6, 0.12);
}

.requirement-tree-node--done .requirement-tree-node__card {
  border-color: rgba(15, 118, 110, 0.2);
}

.requirement-tree-node__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.requirement-tree-node__head-copy {
  min-width: 0;
}

.requirement-tree-node__eyebrow,
.requirement-tree-node__section span {
  display: block;
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.requirement-tree-node__head-copy h5 {
  margin: 0;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.3;
}

.requirement-tree-node__head-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.requirement-tree-node__branch-badge {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(240, 249, 255, 0.88);
  color: #0f766e;
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
}

.requirement-tree-node__objective {
  margin: 12px 0 0;
  color: #475569;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.requirement-tree-node__signals {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.requirement-tree-node__signals span {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(241, 245, 249, 0.92);
  color: #475569;
  font-size: 12px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.requirement-tree-node__section {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.88);
}

.requirement-tree-node__section--result {
  background: rgba(236, 253, 245, 0.72);
}

.requirement-tree-node__section p {
  margin: 0;
  color: #334155;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.requirement-tree-node__children {
  position: relative;
  width: 100%;
  margin-top: 10px;
  padding-left: 10px;
}

.requirement-tree-node__branch-label {
  margin: 0 0 8px 22px;
  color: #7c8aa0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.requirement-tree-node__child-list {
  position: relative;
  display: flex;
  width: 100%;
  flex-direction: column;
  align-items: stretch;
  gap: 14px;
  padding: 0 0 0 22px;
  border-left: 1px solid rgba(148, 163, 184, 0.34);
}

.requirement-tree-node__child-list > .requirement-tree-node {
  padding-left: calc(var(--requirement-tree-level, 0) * 10px);
}

.requirement-tree-node__child-list > .requirement-tree-node::before {
  content: "";
  position: absolute;
  top: 24px;
  left: -22px;
  width: 14px;
  height: 1px;
  background: rgba(148, 163, 184, 0.52);
}

.requirement-tree-node__child-list > .requirement-tree-node::after {
  content: "";
  position: absolute;
  top: 20px;
  left: -10px;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: rgba(103, 232, 249, 0.78);
  box-shadow: 0 0 0 4px rgba(240, 249, 255, 0.92);
}

@media (max-width: 720px) {
  .requirement-tree-node {
    min-width: 100%;
    padding-left: 0;
  }

  .requirement-tree-node__card {
    width: 100%;
    padding: 15px 16px;
  }

  .requirement-tree-node__head {
    flex-direction: column;
  }

  .requirement-tree-node__head-tags {
    justify-content: flex-start;
  }

  .requirement-tree-node__child-list {
    align-items: stretch;
    padding-left: 16px;
  }

  .requirement-tree-node__child-list > .requirement-tree-node {
    padding-left: 0;
  }

  .requirement-tree-node__child-list > .requirement-tree-node::before {
    left: -16px;
    width: 10px;
  }

  .requirement-tree-node__child-list > .requirement-tree-node::after {
    left: -8px;
  }
}
</style>
