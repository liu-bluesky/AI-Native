<template>
  <teleport to="body">
    <div
      v-if="visible"
      ref="menuRef"
      class="studio-context-menu"
      :style="menuStyle"
      @contextmenu.prevent
    >
      <button
        v-for="item in items"
        :key="item.id"
        type="button"
        class="studio-context-menu__item"
        :class="{ 'is-danger': item.danger }"
        :disabled="item.disabled"
        @click.stop="handleSelect(item)"
      >
        <span class="studio-context-menu__label">{{ item.label }}</span>
        <span
          v-if="item.description"
          class="studio-context-menu__description"
        >
          {{ item.description }}
        </span>
      </button>
    </div>
  </teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  x: {
    type: Number,
    default: 0,
  },
  y: {
    type: Number,
    default: 0,
  },
  width: {
    type: Number,
    default: 224,
  },
  items: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["close", "select"]);
const menuRef = ref(null);

const menuStyle = computed(() => {
  if (typeof window === "undefined") {
    return {
      left: `${props.x}px`,
      top: `${props.y}px`,
      width: `${props.width}px`,
    };
  }
  const maxLeft = Math.max(12, window.innerWidth - Number(props.width || 224) - 12);
  const maxTop = Math.max(12, window.innerHeight - 12);
  return {
    left: `${Math.min(Math.max(12, Number(props.x || 0)), maxLeft)}px`,
    top: `${Math.min(Math.max(12, Number(props.y || 0)), maxTop)}px`,
    width: `${props.width}px`,
  };
});

function cleanupListeners() {
  if (typeof window === "undefined") return;
  window.removeEventListener("pointerdown", handleWindowPointerDown, true);
  window.removeEventListener("resize", handleWindowViewportChange);
  window.removeEventListener("scroll", handleWindowViewportChange, true);
  window.removeEventListener("blur", handleWindowViewportChange);
  window.removeEventListener("keydown", handleWindowKeyDown);
}

function bindListeners() {
  if (typeof window === "undefined") return;
  cleanupListeners();
  window.addEventListener("pointerdown", handleWindowPointerDown, true);
  window.addEventListener("resize", handleWindowViewportChange);
  window.addEventListener("scroll", handleWindowViewportChange, true);
  window.addEventListener("blur", handleWindowViewportChange);
  window.addEventListener("keydown", handleWindowKeyDown);
}

function handleWindowPointerDown(event) {
  if (menuRef.value?.contains(event.target)) return;
  emit("close");
}

function handleWindowViewportChange() {
  emit("close");
}

function handleWindowKeyDown(event) {
  if (event?.key !== "Escape") return;
  emit("close");
}

function handleSelect(item) {
  if (!item || item.disabled) return;
  emit("select", item.id, item);
}

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      bindListeners();
      return;
    }
    cleanupListeners();
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  cleanupListeners();
});
</script>

<style scoped>
.studio-context-menu {
  position: fixed;
  z-index: 4000;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  border-radius: 16px;
  border: 1px solid rgba(30, 41, 59, 0.18);
  background: rgba(255, 255, 255, 0.98);
  box-shadow:
    0 22px 44px rgba(15, 23, 42, 0.18),
    0 10px 24px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(14px);
}

.studio-context-menu__item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  padding: 10px 12px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.18s ease;
}

.studio-context-menu__item:hover {
  background: rgba(15, 23, 42, 0.05);
}

.studio-context-menu__item:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.studio-context-menu__item.is-danger .studio-context-menu__label {
  color: #dc2626;
}

.studio-context-menu__label {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
}

.studio-context-menu__description {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}
</style>
