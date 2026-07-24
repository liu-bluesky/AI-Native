<template>
  <el-drawer
    v-model="visibleModel"
    :title="contextTitle || '文件变更审查'"
    size="min(980px, 92vw)"
    append-to-body
  >
    <div class="file-changes-layout" v-loading="loading">
      <aside class="file-changes-list">
        <div class="file-changes-summary">
          <div>
            <strong>{{ items.length }} 个文件</strong>
            <small v-if="contextTitle">仅展示该回答关联的修改</small>
          </div>
          <el-button text size="small" @click="emit('refresh')">刷新</el-button>
        </div>
        <button
          v-for="item in items"
          :key="item.path"
          type="button"
          :class="['file-change-item', { active: activePath === item.path }]"
          @click="emit('select', item.path)"
        >
          <span class="file-change-item__status">{{ item.status }}</span>
          <span class="file-change-item__path">{{ item.path }}</span>
          <small>{{ item.reviewStatus === 'accepted' ? '已保存' : '待确认' }}</small>
        </button>
        <el-empty v-if="!items.length" description="当前没有检测到文件变更" />
      </aside>
      <main class="file-changes-preview">
        <div class="file-changes-preview__head">
          <div>
            <strong>{{ targetLabel }}</strong>
            <small>{{ preview?.summary || preview?.reason || "选择文件查看差异" }}</small>
          </div>
          <div v-if="activeItem" class="file-changes-preview__actions">
            <el-button size="small" type="warning" plain @click="emit('revert')">
              {{ activeItem.reviewStatus === "accepted" ? "撤回已保存" : "放弃修改" }}
            </el-button>
            <el-button
              v-if="activeItem.reviewStatus !== 'accepted'"
              size="small"
              type="primary"
              :loading="saving"
              @click="emit('accept')"
            >确认保存</el-button>
          </div>
        </div>
        <pre class="file-changes-diff">{{ preview?.diff || preview?.status || "暂无可展示的文本差异" }}</pre>
      </main>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  contextTitle: { type: String, default: "" },
  items: { type: Array, default: () => [] },
  activePath: { type: String, default: "" },
  activeItem: { type: Object, default: null },
  preview: { type: Object, default: null },
  targetLabel: { type: String, default: "整个工作区" },
  loading: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "refresh", "select", "accept", "revert"]);
const visibleModel = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});
</script>

<style scoped>
.file-changes-layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); min-height: 70vh; border: 1px solid rgba(148, 163, 184, .25); border-radius: 14px; overflow: hidden; }
.file-changes-list { padding: 12px; overflow: auto; background: #f8fafc; border-right: 1px solid rgba(148, 163, 184, .25); }
.file-changes-summary, .file-changes-preview__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.file-changes-summary small { display: block; margin-top: 3px; color: #64748b; }
.file-change-item { width: 100%; display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; gap: 8px; padding: 10px; margin-top: 6px; border: 0; border-radius: 9px; background: transparent; text-align: left; cursor: pointer; }
.file-change-item:hover, .file-change-item.active { background: white; box-shadow: 0 1px 4px rgba(15, 23, 42, .08); }
.file-change-item__status { font-weight: 700; color: #b45309; }
.file-change-item__path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-change-item small { color: #64748b; }
.file-changes-preview { min-width: 0; display: flex; flex-direction: column; }
.file-changes-preview__head { padding: 14px 16px; border-bottom: 1px solid rgba(148, 163, 184, .25); }
.file-changes-preview__head small { display: block; margin-top: 4px; color: #64748b; white-space: pre-line; }
.file-changes-diff { flex: 1; margin: 0; padding: 16px; overflow: auto; background: #0f172a; color: #e2e8f0; font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre; }
@media (max-width: 900px) { .file-changes-layout { grid-template-columns: 1fr; } .file-changes-list { max-height: 220px; border-right: 0; border-bottom: 1px solid rgba(148, 163, 184, .25); } }
</style>
