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

  <div v-else-if="isProjectListRoute" class="project-list-route-layout">
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
const isMaterialRoute = computed(() => route.path.startsWith("/materials"));
const isProjectListRoute = computed(() =>
  route.path === "/projects" || route.path === "/ai/chat/settings/projects",
);
const isEmbeddedMode = computed(() => {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("embedded") === "1";
});
</script>

<style scoped>
.embedded-layout,
.chat-route-layout,
.material-route-layout,
.project-list-route-layout {
  min-height: 100vh;
  height: 100vh;
}

.embedded-layout {
  overflow: auto;
  background: #f8fafc;
}

.chat-route-layout {
  overflow: hidden;
  background: var(--page-bg);
}

.material-route-layout {
  overflow: hidden;
  background: var(--page-bg);
  box-sizing: border-box;
}

.project-list-route-layout {
  overflow: auto;
  padding: 18px 20px 24px;
  box-sizing: border-box;
  background:
    radial-gradient(circle at 12% 0%, rgba(125, 211, 252, 0.18), transparent 24%),
    radial-gradient(circle at 88% 10%, rgba(103, 232, 249, 0.14), transparent 20%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 40%, #edf2f7 100%);
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
  .project-list-route-layout {
    padding: 14px 14px 18px;
  }

  .default-route-layout {
    padding: 14px;
  }

  .page-content {
    padding: 16px;
    border-radius: 18px;
  }
}
</style>
