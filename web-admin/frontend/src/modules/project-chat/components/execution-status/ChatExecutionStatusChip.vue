<template>
  <button
    type="button"
    class="execution-status-chip"
    :class="toneClass"
    :title="chipLabel"
    aria-label="打开执行状态"
  >
    <span class="execution-status-chip__dot"></span>
    <span>{{ chipLabel }}</span>
  </button>
</template>

<script setup>
defineProps({
  chipLabel: {
    type: String,
    default: "",
  },
  toneClass: {
    type: String,
    default: "",
  },
});
</script>

<style scoped>
.execution-status-chip {
  min-width: 0;
  max-width: 260px;
  min-height: 34px;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 11px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 999px;
  background: rgba(248, 250, 252, 0.92);
  color: #334155;
  font-size: 12px;
  line-height: 1.3;
  font-weight: 700;
  cursor: pointer;
  transition:
    border-color 160ms ease,
    background 160ms ease,
    box-shadow 160ms ease,
    transform 160ms ease;
}

.execution-status-chip:hover,
.execution-status-chip:focus-visible {
  border-color: rgba(100, 116, 139, 0.34);
  background: #fff;
  box-shadow: 0 6px 14px rgba(15, 23, 42, 0.08);
}

.execution-status-chip:active {
  transform: translateY(1px);
}

.execution-status-chip:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.24);
  outline-offset: 2px;
}

.execution-status-chip span:last-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.execution-status-chip__dot {
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #94a3b8;
}

.execution-status-chip.is-muted {
  border-color: rgba(148, 163, 184, 0.28);
  background: rgba(248, 250, 252, 0.94);
  color: #475569;
}

.execution-status-chip.is-muted .execution-status-chip__dot {
  background: #94a3b8;
}

.execution-status-chip.is-ready {
  border-color: rgba(34, 197, 94, 0.26);
  background: rgba(240, 253, 244, 0.94);
  color: #166534;
}

.execution-status-chip.is-ready .execution-status-chip__dot {
  background: #22c55e;
}

.execution-status-chip.is-warning {
  border-color: rgba(245, 158, 11, 0.32);
  background: rgba(255, 251, 235, 0.94);
  color: #92400e;
}

.execution-status-chip.is-warning .execution-status-chip__dot {
  background: #f59e0b;
}

.execution-status-chip.is-pending {
  border-color: rgba(168, 85, 247, 0.24);
  background: rgba(250, 245, 255, 0.92);
  color: #6b21a8;
}

.execution-status-chip.is-pending .execution-status-chip__dot {
  background: #a855f7;
}

.execution-status-chip.is-running {
  border-color: rgba(14, 165, 233, 0.28);
  background: rgba(240, 249, 255, 0.94);
  color: #075985;
}

.execution-status-chip.is-running .execution-status-chip__dot {
  background: #0ea5e9;
}

.execution-status-chip.is-system {
  border-color: rgba(99, 102, 241, 0.22);
  background: rgba(238, 242, 255, 0.9);
  color: #3730a3;
}

.execution-status-chip.is-system .execution-status-chip__dot {
  background: #6366f1;
}

.execution-status-chip.is-danger {
  border-color: rgba(239, 68, 68, 0.28);
  background: rgba(254, 242, 242, 0.94);
  color: #b91c1c;
}

.execution-status-chip.is-danger .execution-status-chip__dot {
  background: #ef4444;
}

@media (max-width: 860px) {
  .execution-status-chip {
    max-width: 100%;
  }
}
</style>
