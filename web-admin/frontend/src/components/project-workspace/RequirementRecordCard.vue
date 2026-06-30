<template>
  <article class="requirement-record">
    <div class="requirement-record__hero">
      <div class="requirement-record__hero-copy">
        <div class="requirement-record__eyebrow">Requirement</div>
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
      <span>{{ record.actorLabel || "需求记录" }}</span>
      <span>{{ formatDateTime(record.updatedAt || record.createdAt) }}</span>
    </div>

    <div class="requirement-record__lineage">
      <section class="requirement-record__lineage-item">
        <span>当前状态</span>
        <strong>{{ record.statusLabel }}</strong>
        <small>{{ record.summaryText || record.completionGate }}</small>
      </section>
      <section class="requirement-record__lineage-item">
        <span>记录时间</span>
        <strong>{{ formatDateTime(record.createdAt) }}</strong>
        <small>只保存需求内容</small>
      </section>
      <section class="requirement-record__lineage-item">
        <span>需求内容</span>
        <strong>{{ record.currentFocus }}</strong>
        <small>{{ record.rootGoal }}</small>
      </section>
    </div>

  </article>
</template>

<script setup>
import { formatDateTime } from "@/utils/date.js";

defineProps({
  record: {
    type: Object,
    required: true,
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
});

defineEmits([
  "delete",
  "toggle-select",
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
  min-width: 0;
  overflow: hidden;
}

.requirement-record__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.requirement-record__hero-copy,
.requirement-record__hero-actions,
.requirement-record__supporting span,
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
  overflow-wrap: anywhere;
}

.requirement-record__hero-copy p {
  margin: 0;
  color: #475569;
  line-height: 1.65;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
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
  max-width: 100%;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.14);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  overflow: hidden;
}

.requirement-record__lineage-item strong {
  display: block;
  margin-top: 8px;
  overflow: hidden;
  color: #0f172a;
  line-height: 1.45;
  word-break: break-word;
  overflow-wrap: anywhere;
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
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
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
  .requirement-record {
    padding: 14px;
    border-radius: 22px;
  }

  .requirement-record__hero-actions {
    width: 100%;
    justify-content: stretch;
  }

  .requirement-record__hero-actions :deep(.el-button) {
    flex: 1 1 calc(50% - 8px);
    min-width: 0;
  }

  .requirement-record__hero-actions :deep(.el-button > span),
  .requirement-record__hero-actions :deep(.el-checkbox__label),
  .requirement-record__hero-actions :deep(.el-tag__content) {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .requirement-record__supporting span {
    flex: 1 1 100%;
  }
}
</style>
