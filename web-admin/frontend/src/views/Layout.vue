<template>
  <div v-if="isEmbeddedMode" class="embedded-layout">
    <router-view />
  </div>

  <div v-else-if="isChatRoute" class="chat-route-layout">
    <router-view />
  </div>

  <el-container v-else class="layout">
    <el-header class="layout-header" :class="{ 'is-chat-route': isChatRoute }">
      <div class="layout-header__left">
        <div class="logo">AI 员工工厂</div>
        <div v-if="isChatRoute" class="chat-quick-nav">
          <button
            v-for="item in chatQuickNavItems"
            :key="item.path"
            type="button"
            class="chat-quick-nav__button"
            :class="{ 'is-active': isChatQuickNavActive(item.path) }"
            @click="router.push(item.path)"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </button>
        </div>
        <el-menu
          v-else
          :default-active="route.path"
          mode="horizontal"
          router
          class="top-menu"
          :ellipsis="false"
        >
          <el-sub-menu index="group-org">
            <template #title>
              <span class="top-menu__group">
                <el-icon><User /></el-icon>
                <span>组织管理</span>
              </span>
            </template>
            <el-menu-item v-if="canMenu('menu.projects')" index="/projects">
              <el-icon><Folder /></el-icon>
              <span>项目管理</span>
            </el-menu-item>
            <el-menu-item v-if="canMenu('menu.employees')" index="/employees">
              <el-icon><User /></el-icon>
              <span>员工管理</span>
            </el-menu-item>
            <el-menu-item
              v-if="canMenu('menu.employees')"
              index="/agent-templates"
            >
              <el-icon><Document /></el-icon>
              <span>智能体模板</span>
            </el-menu-item>
            <el-menu-item
              v-if="canMenu('menu.employees.create')"
              index="/employees/create"
            >
              <el-icon><Plus /></el-icon>
              <span>创建员工</span>
            </el-menu-item>
            <el-menu-item v-if="canMenu('menu.users')" index="/users">
              <el-icon><UserFilled /></el-icon>
              <span>用户管理</span>
            </el-menu-item>
            <el-menu-item v-if="canMenu('menu.roles')" index="/roles">
              <el-icon><Document /></el-icon>
              <span>角色管理</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="group-capability">
            <template #title>
              <span class="top-menu__group">
                <el-icon><ChatDotRound /></el-icon>
                <span>能力中心</span>
              </span>
            </template>
            <el-menu-item v-if="canMenu('menu.ai.chat')" index="/ai/chat">
              <el-icon><ChatDotRound /></el-icon>
              <span>AI 对话</span>
            </el-menu-item>
            <el-menu-item v-if="canMenu('menu.skills')" index="/skills">
              <el-icon><SetUp /></el-icon>
              <span>技能目录</span>
            </el-menu-item>
            <el-menu-item v-if="canMenu('menu.skills')" index="/skill-resources">
              <el-icon><SetUp /></el-icon>
              <span>技能资源</span>
            </el-menu-item>
            <el-menu-item v-if="canMenu('menu.rules')" index="/rules">
              <el-icon><Document /></el-icon>
              <span>规则管理</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="group-system">
            <template #title>
              <span class="top-menu__group">
                <el-icon><SetUp /></el-icon>
                <span>系统设置</span>
              </span>
            </template>
            <el-menu-item index="/user/settings">
              <el-icon><UserFilled /></el-icon>
              <span>用户设置</span>
            </el-menu-item>
            <el-menu-item
              v-if="canMenu('menu.system.config')"
              index="/system/config"
            >
              <el-icon><SetUp /></el-icon>
              <span>系统配置</span>
            </el-menu-item>
            <el-menu-item
              v-if="canMenu('menu.llm.providers')"
              index="/llm/providers"
            >
              <el-icon><SetUp /></el-icon>
              <span>模型供应商</span>
            </el-menu-item>
            <el-menu-item v-if="canMenu('menu.usage.keys')" index="/usage/keys">
              <el-icon><Key /></el-icon>
              <span>API Key</span>
            </el-menu-item>
          </el-sub-menu>
        </el-menu>
      </div>

      <div class="layout-header__right">
        <span class="layout-user">{{ username }}</span>
        <el-button text @click="logout">退出</el-button>
      </div>
    </el-header>

    <el-main class="layout-main">
      <div class="page-content" :class="{ 'is-chat-page': isChatRoute }">
        <router-view />
      </div>
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  User,
  UserFilled,
  Folder,
  Plus,
  SetUp,
  Document,
  Key,
  ChatDotRound,
} from "@element-plus/icons-vue";
import { clearPermissionArray, hasPermission } from "@/utils/permissions.js";

const route = useRoute();
const router = useRouter();
const username = computed(() => localStorage.getItem("username") || "admin");
const isChatRoute = computed(() => route.path.startsWith("/ai/chat"));
const isEmbeddedMode = computed(() => {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("embedded") === "1";
});
const chatQuickNavItems = computed(() =>
  [
    { path: "/ai/chat", label: "AI 对话", icon: ChatDotRound, permission: "menu.ai.chat" },
    { path: "/user/settings", label: "设置", icon: UserFilled, permission: "" },
    { path: "/projects", label: "项目", icon: Folder, permission: "menu.projects" },
    { path: "/agent-templates", label: "模板", icon: Document, permission: "menu.employees" },
    { path: "/employees", label: "员工", icon: User, permission: "menu.employees" },
    { path: "/skills", label: "技能", icon: SetUp, permission: "menu.skills" },
    { path: "/skill-resources", label: "资源", icon: SetUp, permission: "menu.skills" },
    { path: "/rules", label: "规则", icon: Document, permission: "menu.rules" },
    { path: "/system/config", label: "系统", icon: Key, permission: "menu.system.config" },
  ].filter((item) => canMenu(item.permission)),
);

function canMenu(permissionKey) {
  return hasPermission(permissionKey);
}

function isChatQuickNavActive(path) {
  const normalized = String(path || "").trim();
  if (!normalized) return false;
  if (normalized === "/ai/chat") {
    return route.path.startsWith("/ai/chat");
  }
  return route.path === normalized;
}

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("username");
  localStorage.removeItem("role");
  clearPermissionArray();
  router.replace("/login");
}
</script>

<style scoped>
.embedded-layout,
.chat-route-layout {
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

.layout {
  height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.98), transparent 32%),
    linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
}

.layout-header {
  height: 68px;
  padding: 0 24px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(14px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.layout-header.is-chat-route {
  height: 64px;
  padding: 0 18px;
  gap: 16px;
}

.layout-header__left {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 28px;
}

.layout-header__right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.layout-user {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}

.logo {
  flex-shrink: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #2563eb;
}

.top-menu {
  min-width: 0;
  flex: 1;
  border-bottom: 0;
  background: transparent;
}

.chat-quick-nav {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.chat-quick-nav__button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.68);
  color: #475569;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    color 0.18s ease,
    border-color 0.18s ease,
    transform 0.18s ease;
  white-space: nowrap;
}

.chat-quick-nav__button:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.18);
  background: rgba(255, 255, 255, 0.9);
  color: #1e293b;
}

.chat-quick-nav__button.is-active {
  border-color: rgba(37, 99, 235, 0.2);
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.98), rgba(219, 234, 254, 0.92));
  color: #1d4ed8;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.12);
}

.top-menu__group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

:deep(.top-menu .el-menu-item),
:deep(.top-menu .el-sub-menu__title) {
  height: 68px;
  line-height: 68px;
  border-bottom: 2px solid transparent !important;
  color: #475569;
  font-size: 14px;
}

:deep(.top-menu .el-menu-item.is-active),
:deep(.top-menu .el-sub-menu.is-active > .el-sub-menu__title) {
  color: #111827 !important;
  border-bottom-color: #2563eb !important;
}

:deep(.top-menu .el-menu--horizontal > .el-sub-menu .el-sub-menu__icon-arrow) {
  margin-top: -1px;
}

.layout-main {
  padding: 20px;
  overflow: auto;
  min-height: 0;
}

.layout-header.is-chat-route + .layout-main {
  padding: 12px;
}

.page-content {
  min-height: calc(100% - 40px);
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

.page-content.is-chat-page {
  height: 100%;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.72);
}

@media (max-width: 960px) {
  .layout-header {
    height: auto;
    padding: 12px 16px;
    align-items: flex-start;
    flex-direction: column;
  }

  .layout-header__left {
    width: 100%;
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .chat-quick-nav {
    width: 100%;
    flex-wrap: nowrap;
  }

  .layout-header__right {
    width: 100%;
    justify-content: flex-end;
  }

  :deep(.top-menu .el-menu-item),
  :deep(.top-menu .el-sub-menu__title) {
    height: 48px;
    line-height: 48px;
  }

  .layout-main {
    padding: 14px;
  }

  .page-content {
    padding: 16px;
    border-radius: 18px;
  }

  .page-content.is-chat-page {
    padding: 0;
  }
}
</style>
