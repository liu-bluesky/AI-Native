<template>
  <div v-if="isEmbeddedMode" class="embedded-layout">
    <router-view />
  </div>

  <div
    v-else-if="isChatRoute || isMaterialRoute"
    :class="isChatRoute ? 'chat-route-layout' : 'material-route-layout'"
  >
    <router-view />
  </div>

  <div v-else class="default-route-layout">
    <div class="page-content">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const isChatRoute = computed(() => route.path.startsWith("/ai/chat"));
const isMaterialRoute = computed(() => route.path === "/materials");
const isEmbeddedMode = computed(() => {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("embedded") === "1";
});
</script>

<style scoped>
.embedded-layout,
.chat-route-layout,
.material-route-layout {
  min-height: 100vh;
  height: 100vh;
}

.embedded-layout {
  overflow: auto;
  background: #f8fafc;
}

.chat-route-layout {
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.98), transparent 32%),
    linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
}

.material-route-layout {
  overflow: auto;
  background:
    radial-gradient(circle at top left, rgba(255, 250, 240, 0.95), transparent 28%),
    radial-gradient(circle at top right, rgba(219, 234, 254, 0.72), transparent 28%),
    linear-gradient(180deg, #f5f7fb 0%, #edf2f7 100%);
  padding: 18px;
  box-sizing: border-box;
}

.default-route-layout {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 20px;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.98), transparent 32%),
    linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
}

.page-content {
  min-height: calc(100vh - 40px);
  background: rgba(255, 255, 255, 0.86);
  border-radius: 24px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  box-shadow:
    0 16px 48px rgba(15, 23, 42, 0.04),
    0 2px 8px rgba(15, 23, 42, 0.03);
  padding: 24px;
  box-sizing: border-box;
  overflow: auto;
}

@media (max-width: 960px) {
  .default-route-layout {
    padding: 14px;
  }

  .page-content {
    padding: 16px;
    border-radius: 18px;
  }
}
</style>
