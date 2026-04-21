<template>
  <article
    class="requirement-record"
    :class="{ 'requirement-record--expanded': expanded }"
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
          :model-value="selected"
          :disabled="deleting"
          @change="$emit('toggle-select', $event)"
        >
          选择
        </el-checkbox>
        <el-tag :type="record.statusTagType">
          {{ record.statusLabel }}
        </el-tag>
        <el-button plain size="small" @click="$emit('toggle-expand')">
          {{ expanded ? "收起详情" : "展开详情" }}
        </el-button>
        <el-button text @click="$emit('open-detail')">查看整轮</el-button>
        <el-button
          v-if="canManageProject"
          type="danger"
          plain
          size="small"
          :loading="deleting"
          @click="$emit('delete')"
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
              ? roundKindLabel
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
      <div v-show="expanded" class="requirement-record__detail-shell">
        <div class="requirement-record__tree-board" v-loading="treeLoading">
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
            @select="$emit('open-node-detail', $event)"
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
</template>

<script setup>
import RequirementTreeNode from "@/components/RequirementTreeNode.vue";
import { formatDateTime } from "@/utils/date.js";

defineProps({
  record: {
    type: Object,
    required: true,
  },
  expanded: {
    type: Boolean,
    default: false,
  },
  selected: {
    type: Boolean,
    default: false,
  },
  canManageProject: {
    type: Boolean,
    default: false,
  },
  deleting: {
    type: Boolean,
    default: false,
  },
  treeLoading: {
    type: Boolean,
    default: false,
  },
  roundKindLabel: {
    type: String,
    default: "",
  },
});

defineEmits([
  "toggle-expand",
  "open-detail",
  "delete",
  "toggle-select",
  "open-node-detail",
]);
</script>

<style scoped>
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
  margin-top: 8px;
  overflow: hidden;
  color: #0f172a;
  line-height: 1.45;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.requirement-record__lineage-item small {
  display: block;
  margin-top: 8px;
  overflow: hidden;
  color: #64748b;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
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

@media (max-width: 900px) {
  .requirement-record__hero {
    flex-direction: column;
  }

  .requirement-record__lineage {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .requirement-record__hero-actions {
    width: 100%;
  }

  .requirement-record__hero-actions :deep(.el-button) {
    flex: 1 1 calc(50% - 8px);
  }
}
</style>
