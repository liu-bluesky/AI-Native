<template>
  <el-drawer
    v-model="visibleModel"
    class="file-changes-drawer"
    size="min(980px, 92vw)"
    append-to-body
  >
    <template #header>
      <div class="file-changes-header">
        <div class="file-changes-header__title">
          <span class="file-changes-header__icon"><el-icon><Document /></el-icon></span>
          <div>
            <strong>{{ contextTitle || "文件变更审查" }}</strong>
            <small>检查修改内容，确认后再写入工作区</small>
          </div>
        </div>
        <div class="file-changes-header__stats">
          <span><b>{{ items.length }}</b> 个文件</span>
          <span class="file-changes-header__dot" />
          <span>{{ pendingCount }} 待确认</span>
        </div>
      </div>
    </template>

    <div class="file-changes-shell" v-loading="loading">
      <div class="file-changes-toolbar">
        <div class="file-changes-toolbar__scope">
          <button
            type="button"
            :class="['scope-button', { active: scopeMode !== 'message' }]"
            @click="scopeMode === 'message' ? emit('show-all') : undefined"
          >
            <el-icon><Files /></el-icon>
            全部变更
            <em>{{ allLabelCount }}</em>
          </button>
          <button
            v-if="contextTitle && messageScopeAvailable"
            type="button"
            :class="['scope-button', { active: scopeMode === 'message' }]"
            @click="scopeMode === 'message' ? undefined : emit('show-message')"
          >
            <el-icon><ChatLineSquare /></el-icon>
            当前回答
            <em>{{ messageLabelCount }}</em>
          </button>
        </div>
        <div class="file-changes-toolbar__actions">
          <span v-if="selectedPendingPaths.length" class="file-changes-selection-count">
            已选 {{ selectedPendingPaths.length }} 个
          </span>
          <el-button
            v-if="selectedPendingPaths.length"
            size="small"
            type="primary"
            :loading="saving"
            @click="acceptSelected"
          >
            批量保存
          </el-button>
          <el-button
            v-if="pendingCount"
            size="small"
            type="success"
            plain
            :loading="saving"
            @click="acceptAll"
          >
            全部保存
          </el-button>
          <el-button class="file-changes-toolbar__refresh" text @click="emit('refresh')">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div class="file-changes-layout">
        <aside class="file-changes-list">
          <div class="file-changes-list__head">
            <label class="file-changes-select-all" @click.stop>
              <el-checkbox
                :model-value="allPendingSelected"
                :indeterminate="selectedPendingPaths.length > 0 && !allPendingSelected"
                :disabled="!pendingPaths.length"
                @change="toggleSelectAll"
              />
              <span>变更文件</span>
            </label>
            <small>{{ scopeMode === "message" ? "当前回答" : "工作区" }}</small>
          </div>
          <button
            v-for="item in items"
            :key="item.path"
            type="button"
            :class="['file-change-item', { active: activePath === item.path }]"
            @click="emit('select', item.path)"
          >
            <el-checkbox
              v-if="item.reviewStatus !== 'accepted'"
              class="file-change-item__checkbox"
              :model-value="isSelected(item.path)"
              @click.stop
              @change="toggleSelected(item.path)"
            />
            <span :class="['file-change-item__status', statusClass(item.changeType || item.status)]">
              {{ statusLabel(item.changeType || item.status) }}
            </span>
            <span class="file-change-item__content">
              <strong :title="item.path">{{ fileName(item.path) }}</strong>
              <small :title="item.path">{{ fileDirectory(item.path) }}</small>
            </span>
            <span :class="['file-change-item__review', item.reviewStatus === 'accepted' ? 'is-accepted' : 'is-pending']">
              {{ item.reviewStatus === 'accepted' ? '已保存' : '待确认' }}
            </span>
          </button>
          <div v-if="!items.length" class="file-changes-empty">
            <el-empty :image-size="72" description="当前没有检测到文件变更" />
          </div>
        </aside>

        <main class="file-changes-preview">
          <div v-if="activeItem" class="file-changes-preview__head">
            <div class="file-changes-preview__file">
              <span :class="['file-changes-preview__status', statusClass(activeItem.changeType || activeItem.status)]">
                {{ statusLabel(activeItem.changeType || activeItem.status) }}
              </span>
              <div>
                <strong :title="activeItem.path">{{ fileName(activeItem.path) }}</strong>
                <small :title="activeItem.path">{{ activeItem.path }}</small>
              </div>
            </div>
            <div class="file-changes-preview__actions">
              <el-button size="small" plain @click="emit('revert')">
                {{ activeItem.reviewStatus === "accepted" ? "撤回保存" : "放弃修改" }}
              </el-button>
              <el-button
                v-if="activeItem.reviewStatus !== 'accepted'"
                size="small"
                type="primary"
                :loading="saving"
                @click="emit('accept')"
              >
                确认保存
              </el-button>
            </div>
          </div>
          <div v-else class="file-changes-preview__blank">
            <el-icon><DocumentChecked /></el-icon>
            <strong>选择一个文件查看变更</strong>
            <span>左侧选择文件后，这里会显示具体差异内容</span>
          </div>
          <div v-if="activeItem" class="file-changes-preview__meta">
            <span>{{ preview?.summary || preview?.reason || "文件差异" }}</span>
            <span v-if="preview?.diff || preview?.status">文本差异</span>
          </div>
          <div v-if="activeItem" class="file-changes-diff">
            <div
              v-for="(line, index) in diffLines"
              :key="`${index}-${line.text}`"
              :class="['file-changes-diff__line', `is-${line.type}`]"
            >
              <span class="file-changes-diff__number">{{ line.number }}</span>
              <span class="file-changes-diff__content">{{ line.text || " " }}</span>
            </div>
          </div>
        </main>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import {
  ChatLineSquare,
  Document,
  DocumentChecked,
  Files,
  Refresh,
} from "@element-plus/icons-vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  contextTitle: { type: String, default: "" },
  scopeMode: { type: String, default: "all" },
  messageScopeAvailable: { type: Boolean, default: false },
  items: { type: Array, default: () => [] },
  activePath: { type: String, default: "" },
  activeItem: { type: Object, default: null },
  preview: { type: Object, default: null },
  targetLabel: { type: String, default: "整个工作区" },
  loading: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
});

const emit = defineEmits([
  "update:modelValue",
  "refresh",
  "show-all",
  "show-message",
  "select",
  "accept",
  "accept-batch",
  "revert",
]);
const visibleModel = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});
const pendingCount = computed(
  () => props.items.filter((item) => item.reviewStatus !== "accepted").length,
);
const selectedPaths = ref([]);
const pendingPaths = computed(() =>
  props.items
    .filter((item) => item.reviewStatus !== "accepted")
    .map((item) => String(item.path || "").trim())
    .filter(Boolean),
);
const selectedPendingPaths = computed(() =>
  selectedPaths.value.filter((path) => pendingPaths.value.includes(path)),
);
const allPendingSelected = computed(
  () =>
    pendingPaths.value.length > 0 &&
    pendingPaths.value.every((path) => selectedPendingPaths.value.includes(path)),
);
const allLabelCount = computed(() => props.items.length);
const messageLabelCount = computed(() =>
  props.scopeMode === "message" ? props.items.length : "可用",
);
const diffLines = computed(() => {
  const text = String(props.preview?.diff || props.preview?.status || "").trimEnd();
  if (!text) return [{ number: "", text: "暂无可展示的文本差异", type: "empty" }];
  return text.split(/\r?\n/).map((line, index) => ({
    number: String(index + 1).padStart(4, " "),
    text: line,
    type: line.startsWith("+") && !line.startsWith("+++")
      ? "added"
      : line.startsWith("-") && !line.startsWith("---")
        ? "deleted"
        : line.startsWith("@@")
          ? "hunk"
          : line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("---") || line.startsWith("+++")
            ? "header"
            : "context",
  }));
});

function fileName(path = "") {
  const normalized = String(path || "").replace(/\\/g, "/");
  return normalized.split("/").filter(Boolean).pop() || "未命名文件";
}

function fileDirectory(path = "") {
  const normalized = String(path || "").replace(/\\/g, "/");
  const segments = normalized.split("/").filter(Boolean);
  return segments.length > 1 ? segments.slice(0, -1).join("/") : "工作区根目录";
}

function statusLabel(status = "") {
  const normalized = String(status || "").trim().toUpperCase();
  return { A: "新增", M: "修改", D: "删除", R: "重命名" }[normalized] || normalized || "变更";
}

function statusClass(status = "") {
  const normalized = String(status || "").trim().toUpperCase();
  return {
    A: "is-added",
    M: "is-modified",
    D: "is-deleted",
    R: "is-renamed",
  }[normalized] || "is-modified";
}

function isSelected(path = "") {
  return selectedPendingPaths.value.includes(path);
}

function toggleSelected(path = "") {
  if (!path || !pendingPaths.value.includes(path)) return;
  selectedPaths.value = isSelected(path)
    ? selectedPaths.value.filter((item) => item !== path)
    : [...selectedPaths.value, path];
}

function toggleSelectAll() {
  selectedPaths.value = allPendingSelected.value ? [] : [...pendingPaths.value];
}

function acceptSelected() {
  if (!selectedPendingPaths.value.length) return;
  emit("accept-batch", [...selectedPendingPaths.value]);
}

function acceptAll() {
  if (!pendingPaths.value.length) return;
  emit("accept-batch", [...pendingPaths.value]);
}

watch(
  () => props.items,
  () => {
    const available = new Set(pendingPaths.value);
    selectedPaths.value = selectedPaths.value.filter((path) => available.has(path));
  },
  { deep: true },
);
</script>

<style scoped>
:deep(.el-drawer__header) { margin-bottom: 0; padding: 18px 22px 16px; border-bottom: 1px solid #e7edf5; }
:deep(.el-drawer__body) { padding: 0; background: #f6f8fb; }
.file-changes-header, .file-changes-toolbar, .file-changes-preview__head, .file-changes-preview__file { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.file-changes-header__title { display: flex; align-items: center; gap: 11px; min-width: 0; }
.file-changes-header__icon { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 10px; color: #2563eb; background: #eaf1ff; font-size: 18px; }
.file-changes-header strong { display: block; color: #172033; font-size: 16px; line-height: 1.3; }
.file-changes-header small { display: block; margin-top: 3px; color: #7b879b; font-size: 12px; font-weight: 400; }
.file-changes-header__stats { display: inline-flex; align-items: center; gap: 9px; color: #6b778c; font-size: 12px; white-space: nowrap; }
.file-changes-header__stats b { color: #172033; font-size: 15px; }
.file-changes-header__dot { width: 4px; height: 4px; border-radius: 50%; background: #c4ccd8; }
.file-changes-shell { display: flex; flex-direction: column; height: calc(100vh - 108px); min-height: 560px; }
.file-changes-toolbar { min-height: 58px; padding: 10px 18px; border-bottom: 1px solid #e7edf5; background: #fff; }
.file-changes-toolbar__scope { display: inline-flex; align-items: center; gap: 4px; padding: 3px; border: 1px solid #e3e9f2; border-radius: 9px; background: #f6f8fb; }
.scope-button { display: inline-flex; align-items: center; gap: 7px; min-height: 30px; padding: 0 11px; border: 0; border-radius: 7px; color: #6b778c; background: transparent; cursor: pointer; font: inherit; font-size: 12px; }
.scope-button:hover { color: #2563eb; }
.scope-button.active { color: #1d4ed8; background: #fff; box-shadow: 0 1px 3px rgba(22, 44, 85, .12); font-weight: 600; }
.scope-button em { min-width: 18px; padding: 1px 5px; border-radius: 10px; color: inherit; background: rgba(37, 99, 235, .1); font-style: normal; font-size: 11px; text-align: center; }
.file-changes-toolbar__actions { display: inline-flex; align-items: center; gap: 8px; }
.file-changes-selection-count { color: #64748b; font-size: 11px; }
.file-changes-toolbar__refresh { color: #64748b; }
.file-changes-layout { display: grid; grid-template-columns: 296px minmax(0, 1fr); flex: 1; min-height: 0; margin: 14px 18px 18px; overflow: hidden; border: 1px solid #e3e9f2; border-radius: 12px; background: #fff; box-shadow: 0 8px 30px rgba(31, 51, 85, .06); }
.file-changes-list { min-width: 0; overflow: auto; background: #fbfcfe; border-right: 1px solid #e7edf5; }
.file-changes-list__head { display: flex; align-items: center; justify-content: space-between; padding: 11px 15px 7px 9px; color: #364152; font-size: 12px; font-weight: 700; }
.file-changes-select-all { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.file-changes-select-all .el-checkbox { margin-right: 1px; }
.file-changes-select-all :deep(.el-checkbox__inner), .file-change-item__checkbox :deep(.el-checkbox__inner) { width: 16px; height: 16px; border: 1px solid #94a3b8; border-radius: 4px; background: #fff; box-shadow: 0 0 0 2px rgba(255, 255, 255, .9); }
.file-changes-select-all :deep(.el-checkbox__inner::after), .file-change-item__checkbox :deep(.el-checkbox__inner::after) { border-width: 2px; }
.file-changes-select-all :deep(.el-checkbox__input.is-checked .el-checkbox__inner), .file-change-item__checkbox :deep(.el-checkbox__input.is-checked .el-checkbox__inner) { border-color: #2563eb; background: #2563eb; box-shadow: 0 0 0 2px rgba(37, 99, 235, .12); }
.file-changes-select-all :deep(.el-checkbox__input.is-indeterminate .el-checkbox__inner), .file-change-item__checkbox :deep(.el-checkbox__input.is-indeterminate .el-checkbox__inner) { border-color: #2563eb; background: #2563eb; }
.file-changes-list__head small { color: #98a3b5; font-size: 11px; font-weight: 400; }
.file-change-item { position: relative; display: grid; grid-template-columns: 34px minmax(0, 1fr); grid-template-areas: "status content" "status review"; width: calc(100% - 12px); margin: 3px 6px; padding: 10px 9px 10px 40px; border: 1px solid transparent; border-radius: 9px; background: transparent; text-align: left; cursor: pointer; }
.file-change-item__checkbox { position: absolute; top: 10px; left: 8px; z-index: 1; padding: 2px; border-radius: 5px; background: #fff; }
.file-change-item:hover { background: #f3f6fb; }
.file-change-item.active { border-color: #cfe0ff; background: #eef5ff; box-shadow: none; }
.file-change-item__status, .file-changes-preview__status { display: inline-flex; align-items: center; justify-content: center; width: 29px; height: 22px; border-radius: 5px; font-size: 10px; font-weight: 700; }
.file-change-item__status { grid-area: status; align-self: start; margin-top: 1px; }
.is-added { color: #15803d; background: #dcfce7; }
.is-modified { color: #b45309; background: #fef3c7; }
.is-deleted { color: #b91c1c; background: #fee2e2; }
.is-renamed { color: #6d28d9; background: #ede9fe; }
.file-change-item__content { grid-area: content; min-width: 0; }
.file-change-item__content strong, .file-change-item__content small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-change-item__content strong { color: #253047; font-size: 12px; font-weight: 600; line-height: 1.35; }
.file-change-item__content small { margin-top: 3px; color: #8793a6; font-size: 10px; }
.file-change-item__review { grid-area: review; justify-self: start; margin-top: 5px; color: #9aa5b5; font-size: 10px; }
.file-change-item__review.is-accepted { color: #16804a; }
.file-change-item__review.is-pending { color: #b7791f; }
.file-changes-empty { padding: 36px 10px; }
.file-changes-preview { display: flex; min-width: 0; min-height: 0; flex-direction: column; background: #fff; }
.file-changes-preview__head { min-height: 68px; padding: 13px 17px; border-bottom: 1px solid #e7edf5; }
.file-changes-preview__file { justify-content: flex-start; min-width: 0; }
.file-changes-preview__file > div { min-width: 0; }
.file-changes-preview__file strong, .file-changes-preview__file small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-changes-preview__file strong { max-width: 430px; color: #253047; font-size: 13px; }
.file-changes-preview__file small { max-width: 430px; margin-top: 4px; color: #8793a6; font: 11px/1.3 ui-monospace, SFMono-Regular, Menlo, monospace; }
.file-changes-preview__actions { display: inline-flex; flex-shrink: 0; gap: 7px; }
.file-changes-preview__meta { display: flex; justify-content: space-between; gap: 12px; padding: 10px 17px; border-bottom: 1px solid #202d43; color: #aebbd0; background: #172238; font-size: 11px; }
.file-changes-preview__meta span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-changes-preview__meta span:last-child { color: #7dd3fc; white-space: nowrap; }
.file-changes-preview__blank { display: flex; flex: 1; align-items: center; justify-content: center; flex-direction: column; gap: 8px; color: #9aa5b5; }
.file-changes-preview__blank .el-icon { margin-bottom: 4px; color: #b9c7da; font-size: 34px; }
.file-changes-preview__blank strong { color: #536176; font-size: 14px; }
.file-changes-preview__blank span { font-size: 12px; }
.file-changes-diff { flex: 1; min-height: 0; margin: 0; padding: 10px 0; overflow: auto; color: #dbe7f5; background: #101a2c; font: 12px/1.65 ui-monospace, SFMono-Regular, Menlo, monospace; tab-size: 2; }
.file-changes-diff__line { display: grid; grid-template-columns: 42px minmax(0, 1fr); min-width: max-content; padding-right: 18px; }
.file-changes-diff__number { padding-right: 10px; color: #62718a; text-align: right; user-select: none; }
.file-changes-diff__content { padding: 0 12px; white-space: pre; }
.file-changes-diff__line.is-added { color: #c9f7d3; background: rgba(34, 197, 94, .15); }
.file-changes-diff__line.is-deleted { color: #ffd1d1; background: rgba(239, 68, 68, .16); }
.file-changes-diff__line.is-hunk { color: #9dd7ff; background: rgba(59, 130, 246, .13); }
.file-changes-diff__line.is-header { color: #aebbd0; background: rgba(148, 163, 184, .08); }
.file-changes-diff__line.is-empty { display: block; padding: 24px; color: #94a3b8; }
@media (max-width: 900px) { .file-changes-shell { height: calc(100vh - 116px); } .file-changes-layout { grid-template-columns: 1fr; grid-template-rows: minmax(170px, 32%) minmax(0, 1fr); margin: 10px; } .file-changes-list { border-right: 0; border-bottom: 1px solid #e7edf5; } .file-changes-toolbar { padding: 9px 10px; } .file-changes-header { align-items: flex-start; flex-direction: column; gap: 8px; } .file-changes-header__stats { padding-left: 45px; } .file-changes-preview__head { align-items: flex-start; flex-direction: column; } .file-changes-preview__actions { width: 100%; } .file-changes-preview__actions .el-button { flex: 1; } .file-changes-preview__file small, .file-changes-preview__file strong { max-width: calc(100vw - 100px); } }
@media (max-width: 520px) { .file-changes-header, .file-changes-toolbar { padding-left: 2px; padding-right: 2px; } .file-changes-toolbar__scope { max-width: calc(100vw - 100px); overflow-x: auto; } .scope-button { padding: 0 8px; } .file-changes-layout { margin: 8px 0 0; border-radius: 0; border-right: 0; border-left: 0; } }
</style>
