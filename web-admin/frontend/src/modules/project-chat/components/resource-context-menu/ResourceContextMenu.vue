<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="resource-context-menu"
      :style="{ left: `${x}px`, top: `${y}px` }"
      role="menu"
      @contextmenu.prevent
    >
      <button v-if="canAppend" type="button" role="menuitem" @click="$emit('append')">
        <span>添加到 liuAgent 对话</span>
      </button>
      <div v-if="canAppend && hasResourceActions" class="resource-context-menu__divider" />
      <button v-if="canOpen" type="button" role="menuitem" @click="$emit('open')">
        <span>{{ openLabel }}</span>
      </button>
      <button
        v-if="canRemove"
        type="button"
        role="menuitem"
        class="resource-context-menu__danger"
        @click="$emit('remove')"
      >
        <span>{{ removeLabel }}</span>
      </button>
      <button v-if="canDownload" type="button" role="menuitem" @click="$emit('download')">
        <span>下载 / 另存为</span>
      </button>
      <button v-if="canCopyAddress" type="button" role="menuitem" @click="$emit('copy-address')">
        <span>复制地址</span>
      </button>
      <button v-if="canCopyFile" type="button" role="menuitem" @click="$emit('copy-file')">
        <span>复制文件本身</span>
      </button>
      <button v-if="canCopyContent" type="button" role="menuitem" @click="$emit('copy-content')">
        <span>复制内容</span>
      </button>
    </div>
  </Teleport>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  visible: { type: Boolean, default: false },
  x: { type: Number, default: 0 },
  y: { type: Number, default: 0 },
  canAppend: { type: Boolean, default: false },
  canOpen: { type: Boolean, default: false },
  openLabel: { type: String, default: "在新窗口打开" },
  canRemove: { type: Boolean, default: false },
  removeLabel: { type: String, default: "移除" },
  canDownload: { type: Boolean, default: false },
  canCopyAddress: { type: Boolean, default: false },
  canCopyFile: { type: Boolean, default: false },
  canCopyContent: { type: Boolean, default: false },
});

defineEmits([
  "append",
  "open",
  "remove",
  "download",
  "copy-address",
  "copy-file",
  "copy-content",
]);

const hasResourceActions = computed(
  () =>
    props.canOpen ||
    props.canDownload ||
    props.canCopyAddress ||
    props.canCopyFile ||
    props.canCopyContent,
);
</script>

<style scoped>
.resource-context-menu {
  position: fixed;
  z-index: 5000;
  width: 220px;
  padding: 6px;
  border: 1px solid rgba(148, 163, 184, 0.32);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.2);
  backdrop-filter: blur(14px);
}

.resource-context-menu button {
  display: flex;
  width: 100%;
  min-width: 0;
  padding: 9px 10px;
  align-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #172033;
  cursor: pointer;
  text-align: left;
}

.resource-context-menu button:hover {
  background: #eef4ff;
}

.resource-context-menu button.resource-context-menu__danger {
  color: #dc2626;
}

.resource-context-menu button.resource-context-menu__danger:hover {
  background: #fef2f2;
}

.resource-context-menu button span {
  font-size: 13px;
  font-weight: 600;
}

.resource-context-menu__divider {
  height: 1px;
  margin: 5px 4px;
  background: #e2e8f0;
}
</style>
