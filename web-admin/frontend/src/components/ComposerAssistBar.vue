<template>
  <div v-if="actions.length" class="composer-assist">
    <div class="composer-assist-strip">
      <button
        v-for="action in visibleActions"
        :key="action.id"
        type="button"
        class="composer-assist-chip"
        :class="{ 'is-active': activeActionId === action.id }"
        @click="$emit('toggle', action.id)"
      >
        <el-icon class="composer-assist-chip-icon">
          <component :is="resolveIcon(action.icon)" />
        </el-icon>
        <span class="composer-assist-chip-label">{{ action.label }}</span>
      </button>

      <el-popover
        v-if="overflowActions.length"
        placement="top-end"
        :width="220"
        trigger="click"
        popper-class="composer-assist-popover"
      >
        <template #reference>
          <button
            type="button"
            class="composer-assist-chip composer-assist-chip-more"
          >
            <el-icon class="composer-assist-chip-icon">
              <MoreFilled />
            </el-icon>
            <span class="composer-assist-chip-label">更多</span>
          </button>
        </template>

        <div class="composer-assist-menu">
          <button
            v-for="action in overflowActions"
            :key="`overflow-${action.id}`"
            type="button"
            class="composer-assist-menu-item"
            :class="{ 'is-active': activeActionId === action.id }"
            @click="$emit('toggle', action.id)"
          >
            <el-icon class="composer-assist-menu-icon">
              <component :is="resolveIcon(action.icon)" />
            </el-icon>
            <span class="composer-assist-menu-label">{{ action.label }}</span>
            <span
              v-if="action.shortDesc"
              class="composer-assist-menu-desc"
            >
              {{ action.shortDesc }}
            </span>
          </button>
        </div>
      </el-popover>
    </div>

  </div>
</template>

<script setup>
import { computed } from "vue";
import {
  Search,
  MagicStick,
  Files,
  User,
  MoreFilled,
  EditPen,
  Grid,
} from "@element-plus/icons-vue";

const props = defineProps({
  actions: {
    type: Array,
    default: () => [],
  },
  activeActionId: {
    type: String,
    default: "",
  },
  maxVisible: {
    type: Number,
    default: 5,
  },
});

defineEmits(["toggle"]);

const iconMap = {
  search: Search,
  improve: MagicStick,
  skill: Files,
  employee: User,
  edit: EditPen,
  grid: Grid,
};

const visibleActions = computed(() =>
  props.actions.slice(0, Math.max(1, Number(props.maxVisible || 5))),
);

const overflowActions = computed(() =>
  props.actions.slice(Math.max(1, Number(props.maxVisible || 5))),
);

function resolveIcon(iconKey) {
  return iconMap[String(iconKey || "").trim()] || Grid;
}
</script>

<style scoped>
.composer-assist {
  display: flex;
  flex-direction: column;
}

.composer-assist-strip {
  display: flex;
  gap: 4px;
  padding: 0 14px 10px;
  flex-wrap: wrap;
  align-items: center;
}

.composer-assist-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #1f2937;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease;
}

.composer-assist-chip:hover {
  background: rgba(15, 23, 42, 0.05);
}

.composer-assist-chip.is-active {
  background: rgba(15, 23, 42, 0.08);
  color: #111827;
}

.composer-assist-chip-icon {
  font-size: 15px;
}

.composer-assist-chip-label {
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
}

.composer-assist-chip-more {
  background: rgba(15, 23, 42, 0.04);
}

.composer-assist-menu {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 0;
}

.composer-assist-menu-item {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 10px;
  align-items: center;
  width: 100%;
  padding: 10px 12px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.18s ease;
}

.composer-assist-menu-item:hover,
.composer-assist-menu-item.is-active {
  background: rgba(15, 23, 42, 0.05);
}

.composer-assist-menu-icon {
  font-size: 15px;
  color: #111827;
}

.composer-assist-menu-label {
  display: block;
  color: #111827;
  font-size: 14px;
  line-height: 1.2;
}

.composer-assist-menu-desc {
  display: block;
  margin-top: 3px;
  color: #6b7280;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 768px) {
  .composer-assist-strip {
    padding-left: 14px;
    padding-right: 14px;
  }

  .composer-assist-chip-label {
    font-size: 13px;
  }
}
</style>
