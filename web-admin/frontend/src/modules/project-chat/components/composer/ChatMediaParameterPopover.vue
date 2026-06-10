<template>
  <el-popover
    v-if="visible"
    v-model:visible="modelVisible"
    trigger="click"
    placement="top-start"
    :width="mode === 'image' ? 460 : 420"
    :teleported="false"
  >
    <template #reference>
      <el-button
        class="chat-media-parameter-trigger"
        text
        :disabled="disabled"
      >
        <el-icon class="chat-media-parameter-trigger__icon">
          <component :is="triggerIcon" />
        </el-icon>
        <span class="chat-media-parameter-trigger__label">
          {{ triggerLabel }}
        </span>
      </el-button>
    </template>

    <div class="chat-media-parameter-panel">
      <div class="chat-media-parameter-panel__head">
        <div class="chat-media-parameter-panel__eyebrow">
          {{ triggerLabel }}
        </div>
        <div class="chat-media-parameter-panel__title">
          {{ panelTitle }}
        </div>
        <div class="chat-media-parameter-panel__summary">
          {{ modelSummary }}
        </div>
      </div>

      <div class="chat-media-parameter-panel__sections">
        <section
          v-for="section in sections"
          :key="`popover-${section.key}`"
          class="chat-media-parameter-section"
        >
          <div class="chat-media-parameter-section__label">
            {{ section.label }}
          </div>
          <div
            v-if="section.helper"
            class="chat-media-parameter-section__helper"
          >
            {{ section.helper }}
          </div>
          <div
            class="chat-media-parameter-section__options"
            :class="{
              'is-aspect':
                section.key === 'image_aspect_ratio' ||
                section.key === 'video_aspect_ratio',
              'is-resolution': section.key === 'image_resolution',
            }"
          >
            <button
              v-for="option in section.options"
              :key="`${section.key}-${option.id}`"
              type="button"
              class="chat-media-parameter-option"
              :class="{
                'is-active': option.value === section.modelValue,
                'is-resolution': section.key === 'image_resolution',
              }"
              @click="$emit('select-parameter', section.key, option.value)"
            >
              <span class="chat-media-parameter-option__label">
                {{ option.label }}
              </span>
            </button>
          </div>
        </section>
      </div>

      <section
        v-if="showFourViewsOption"
        class="chat-media-parameter-section chat-media-parameter-section--toggle"
      >
        <div class="chat-media-parameter-section__label">四视图</div>
        <div class="chat-media-parameter-section__helper">
          勾选后会自动要求输出同一角色的正面、背面、左侧、右侧四视图。
        </div>
        <button
          type="button"
          class="chat-media-toggle-card"
          :class="{ 'is-active': fourViewsEnabled }"
          @click="$emit('toggle-four-views')"
        >
          <div class="chat-media-toggle-card__content">
            <span class="chat-media-toggle-card__title">
              自动生成四视图
            </span>
            <span class="chat-media-toggle-card__description">
              适合角色设定图和素材前置统一。
            </span>
          </div>
          <span
            class="chat-media-toggle-card__indicator"
            :class="{ 'is-active': fourViewsEnabled }"
          >
            {{ fourViewsEnabled ? "已开启" : "未开启" }}
          </span>
        </button>
      </section>
    </div>
  </el-popover>
</template>

<script setup>
import { computed } from "vue";
import { CollectionTag, Picture } from "@element-plus/icons-vue";

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  modelValue: {
    type: Boolean,
    default: false,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  mode: {
    type: String,
    default: "image",
  },
  triggerLabel: {
    type: String,
    default: "",
  },
  panelTitle: {
    type: String,
    default: "",
  },
  modelSummary: {
    type: String,
    default: "",
  },
  sections: {
    type: Array,
    default: () => [],
  },
  showFourViewsOption: {
    type: Boolean,
    default: false,
  },
  fourViewsEnabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits([
  "select-parameter",
  "toggle-four-views",
  "update:modelValue",
]);

const modelVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", Boolean(value)),
});

const triggerIcon = computed(() =>
  props.mode === "video" ? CollectionTag : Picture,
);
</script>

<style scoped>
.chat-media-parameter-trigger {
  width: auto !important;
  min-width: 0;
  padding: 0 12px !important;
  border-radius: 999px !important;
  border: 1px solid rgba(15, 23, 42, 0.06) !important;
  background: rgba(255, 255, 255, 0.78) !important;
  color: #374151 !important;
  gap: 6px;
}

.chat-media-parameter-trigger:hover {
  border-color: rgba(56, 189, 248, 0.22) !important;
  background: rgba(240, 249, 255, 0.96) !important;
  color: #0f172a !important;
}

.chat-media-parameter-trigger__icon {
  font-size: 14px;
}

.chat-media-parameter-trigger__label {
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
}

.chat-media-parameter-panel {
  display: grid;
  gap: 16px;
}

.chat-media-parameter-panel__head {
  display: grid;
  gap: 4px;
}

.chat-media-parameter-panel__eyebrow {
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  color: #7c8aa0;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.chat-media-parameter-panel__title {
  color: #0f172a;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.2;
}

.chat-media-parameter-panel__summary {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.chat-media-parameter-panel__sections {
  display: grid;
  gap: 14px;
}

.chat-media-parameter-section {
  display: grid;
  gap: 8px;
}

.chat-media-parameter-section--toggle {
  padding-top: 2px;
  margin-top: 2px;
}

.chat-media-parameter-section__label {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
}

.chat-media-parameter-section__helper {
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.5;
}

.chat-media-parameter-section__options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chat-media-parameter-section__options.is-aspect {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.chat-media-parameter-section__options.is-resolution {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.chat-media-parameter-option {
  min-height: 40px;
  padding: 0 12px;
  color: #475569;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.3;
  cursor: pointer;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 14px;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.chat-media-parameter-option:hover {
  color: #0f172a;
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(56, 189, 248, 0.22);
  transform: translateY(-1px);
}

.chat-media-parameter-option.is-active {
  color: #0f172a;
  background: rgba(240, 249, 255, 0.96);
  border-color: rgba(56, 189, 248, 0.24);
  box-shadow: 0 10px 24px rgba(56, 189, 248, 0.12);
}

.chat-media-parameter-option.is-resolution {
  justify-content: center;
  min-height: 44px;
}

.chat-media-parameter-option__label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  text-align: center;
}

.chat-media-toggle-card {
  display: flex;
  gap: 14px;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 14px 16px;
  color: #0f172a;
  text-align: left;
  cursor: pointer;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.chat-media-toggle-card:hover {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(56, 189, 248, 0.22);
  transform: translateY(-1px);
}

.chat-media-toggle-card.is-active {
  background: rgba(240, 249, 255, 0.96);
  border-color: rgba(56, 189, 248, 0.24);
  box-shadow: 0 10px 24px rgba(56, 189, 248, 0.12);
}

.chat-media-toggle-card__content {
  display: grid;
  gap: 4px;
}

.chat-media-toggle-card__title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
}

.chat-media-toggle-card__description {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.chat-media-toggle-card__indicator {
  flex-shrink: 0;
  min-width: 64px;
  padding: 7px 10px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  text-align: center;
  background: rgba(15, 23, 42, 0.06);
  border-radius: 999px;
}

.chat-media-toggle-card__indicator.is-active {
  color: #ffffff;
  background: linear-gradient(180deg, #0f172a, #1e293b);
}
</style>
