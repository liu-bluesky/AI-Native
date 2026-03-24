<template>
  <section class="studio-timeline-editor">
    <div class="studio-timeline-editor__head">
      <div>
        <div class="studio-timeline-editor__title">时间线编辑</div>
        <div class="studio-timeline-editor__meta">
          控制显隐、调整顺序，并从历史分镜或素材库视频补充到当前时间线。
        </div>
      </div>
      <el-button plain size="small" @click="$emit('open-history')">
        添加到时间线
      </el-button>
    </div>

    <div v-if="clips.length" class="studio-timeline-editor__list">
      <div
        v-if="draggingClipId"
        class="studio-timeline-editor__drop-hint"
      >
        拖到目标片段上方即可插入，拖到列表底部可追加到末尾
      </div>
      <article
        v-for="(clip, index) in clips"
        :key="`editor-${clip.id}`"
        class="studio-timeline-editor__item"
        :data-studio-timeline-clip-id="clip.id"
        :class="{
          'is-hidden': clip.visible === false,
          'is-active': clip.id === activeClipId,
          'is-drop-target': clip.id === hoverClipId,
        }"
        draggable="true"
        @click="$emit('focus-clip', clip.id)"
        @dragstart="handleDragStart($event, clip.id)"
        @dragend="resetDragState"
        @dragover.prevent="setHoverClip(clip.id)"
        @dragleave="clearHoverClip(clip.id)"
        @drop.prevent="handleDrop(clip.id)"
      >
        <div class="studio-timeline-editor__item-head">
          <div class="studio-timeline-editor__identity">
            <span class="studio-timeline-editor__index">
              {{ String(index + 1).padStart(2, "0") }}
            </span>
            <div>
              <div class="studio-timeline-editor__item-title">{{ clip.title }}</div>
              <div class="studio-timeline-editor__item-meta">
                {{ resolveChapterTitle(clip.chapterId) }}
              </div>
              <div class="studio-timeline-editor__item-time">
                {{ formatSeconds(clip.startSeconds || 0) }} - {{ formatSeconds(clip.endSeconds || 0) }}
              </div>
            </div>
          </div>
          <span class="studio-timeline-editor__status">
            {{ clip.visible === false ? "已隐藏" : "显示中" }}
          </span>
        </div>

        <div class="studio-timeline-editor__controls">
          <label class="studio-timeline-editor__duration">
            <span>时长</span>
            <strong class="studio-timeline-editor__duration-value">
              {{ clip.durationSeconds }}
            </strong>
            <span>秒</span>
          </label>

          <div class="studio-timeline-editor__actions">
            <el-button
              text
              size="small"
              :disabled="index === 0"
              @click.stop="$emit('move-clip-up', clip.id)"
            >
              上移
            </el-button>
            <el-button
              text
              size="small"
              :disabled="index === clips.length - 1"
              @click.stop="$emit('move-clip-down', clip.id)"
            >
              下移
            </el-button>
            <el-button
              text
              type="danger"
              size="small"
              @click.stop="$emit('remove-clip', clip.id)"
            >
              删除
            </el-button>
            <el-switch
              :model-value="clip.visible !== false"
              inline-prompt
              active-text="显示"
              inactive-text="隐藏"
              @change="$emit('set-visibility', clip.id, $event)"
            />
          </div>
        </div>
      </article>
      <button
        type="button"
        class="studio-timeline-editor__tail"
        :class="{ 'is-active': hoverClipId === '__tail__' }"
        @dragover.prevent="setHoverClip('__tail__')"
        @dragleave="clearHoverClip('__tail__')"
        @drop.prevent="handleDropToEnd"
      >
        拖到这里可放到末尾
      </button>
    </div>

    <div v-else class="studio-timeline-editor__empty">
      <el-empty description="当前还没有导入分镜" :image-size="48" />
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  clips: {
    type: Array,
    default: () => [],
  },
  resolveChapterTitle: {
    type: Function,
    default: () => "未命名章节",
  },
  activeClipId: {
    type: String,
    default: "",
  },
});

const emit = defineEmits([
  "open-history",
  "normalize-duration",
  "set-visibility",
  "reorder-clips",
  "focus-clip",
  "move-clip-up",
  "move-clip-down",
  "remove-clip",
]);

const draggingClipId = ref("");
const hoverClipId = ref("");

function formatSeconds(value) {
  const total = Math.max(0, Number(value || 0));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function handleDragStart(event, clipId) {
  event?.dataTransfer?.setData("text/plain", clipId);
  event?.dataTransfer?.setDragImage?.(event.currentTarget, 24, 20);
  draggingClipId.value = clipId;
  hoverClipId.value = clipId;
}

function handleDrop(targetClipId) {
  if (!draggingClipId.value || draggingClipId.value === targetClipId) return;
  emit("reorder-clips", draggingClipId.value, targetClipId);
  resetDragState();
}

function handleDropToEnd() {
  if (!draggingClipId.value) return;
  emit("reorder-clips", draggingClipId.value, "");
  resetDragState();
}

function setHoverClip(clipId) {
  if (!draggingClipId.value) return;
  hoverClipId.value = clipId;
}

function clearHoverClip(clipId) {
  if (hoverClipId.value === clipId) {
    hoverClipId.value = "";
  }
}

function resetDragState() {
  draggingClipId.value = "";
  hoverClipId.value = "";
}
</script>

<style scoped>
.studio-timeline-editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.studio-timeline-editor__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.studio-timeline-editor__title {
  color: #0f172a;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.3;
}

.studio-timeline-editor__meta {
  margin-top: 6px;
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.7;
}

.studio-timeline-editor__list {
  display: grid;
  gap: 12px;
}

.studio-timeline-editor__drop-hint {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(224, 242, 254, 0.86);
  color: #0369a1;
  font-size: 12px;
  line-height: 1.6;
}

.studio-timeline-editor__item {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(255, 255, 255, 0.78);
  box-sizing: border-box;
  cursor: pointer;
}

.studio-timeline-editor__item.is-active {
  border-color: rgba(56, 189, 248, 0.24);
  box-shadow:
    0 10px 22px rgba(14, 165, 233, 0.08),
    0 0 0 1px rgba(56, 189, 248, 0.14);
}

.studio-timeline-editor__item.is-hidden {
  border-style: dashed;
  background: rgba(248, 250, 252, 0.72);
}

.studio-timeline-editor__item.is-drop-target {
  border-color: rgba(14, 165, 233, 0.36);
  background: rgba(240, 249, 255, 0.9);
}

.studio-timeline-editor__item-head,
.studio-timeline-editor__controls,
.studio-timeline-editor__identity,
.studio-timeline-editor__duration {
  display: flex;
  align-items: center;
  gap: 12px;
}

.studio-timeline-editor__item-head,
.studio-timeline-editor__controls {
  justify-content: space-between;
}

.studio-timeline-editor__controls {
  flex-wrap: wrap;
}

.studio-timeline-editor__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.studio-timeline-editor__identity {
  min-width: 0;
}

.studio-timeline-editor__index {
  flex: none;
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.08);
  color: #0f172a;
  font-size: 11px;
  font-weight: 700;
}

.studio-timeline-editor__item-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
}

.studio-timeline-editor__item-meta {
  margin-top: 4px;
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.6;
}

.studio-timeline-editor__item-time {
  margin-top: 4px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.6;
}

.studio-timeline-editor__status {
  flex: none;
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.12);
  color: #0369a1;
  font-size: 12px;
  font-weight: 700;
}

.studio-timeline-editor__item.is-hidden .studio-timeline-editor__status {
  background: rgba(148, 163, 184, 0.14);
  color: #64748b;
}

.studio-timeline-editor__duration {
  color: #475569;
  font-size: 12px;
}

.studio-timeline-editor__duration-value {
  min-width: 32px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  text-align: center;
}

.studio-timeline-editor__empty {
  min-height: 160px;
}

.studio-timeline-editor__tail {
  min-height: 44px;
  border: 1px dashed rgba(148, 163, 184, 0.5);
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.72);
  color: #94a3b8;
  font-size: 12px;
}

.studio-timeline-editor__tail.is-active {
  border-color: rgba(14, 165, 233, 0.72);
  background: rgba(224, 242, 254, 0.88);
  color: #0369a1;
}

@media (max-width: 960px) {
  .studio-timeline-editor__head,
  .studio-timeline-editor__item-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .studio-timeline-editor__identity {
    width: 100%;
  }

  .studio-timeline-editor__actions {
    justify-content: flex-start;
  }
}
</style>
