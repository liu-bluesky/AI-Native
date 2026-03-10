<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">AI 员工工厂</div>
      <el-menu
        :default-active="route.path"
        :default-openeds="defaultOpeneds"
        router
        class="menu"
      >
        <el-sub-menu index="group-org">
          <template #title>
            <el-icon><User /></el-icon>
            <span>组织管理</span>
          </template>
          <el-menu-item v-if="canMenu('menu.projects')" index="/projects">
            <el-icon><Folder /></el-icon>
            <span>项目管理</span>
          </el-menu-item>
          <el-menu-item v-if="canMenu('menu.employees')" index="/employees">
            <el-icon><User /></el-icon>
            <span>员工管理</span>
          </el-menu-item>
          <el-menu-item v-if="canMenu('menu.employees.create')" index="/employees/create">
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
            <el-icon><Document /></el-icon>
            <span>能力中心</span>
          </template>
          <el-menu-item v-if="canMenu('menu.ai.chat')" index="/ai/chat">
            <el-icon><ChatDotRound /></el-icon>
            <span>AI 对话</span>
          </el-menu-item>
          <el-menu-item v-if="canMenu('menu.skills')" index="/skills">
            <el-icon><SetUp /></el-icon>
            <span>技能目录</span>
          </el-menu-item>
          <el-menu-item v-if="canMenu('menu.rules')" index="/rules">
            <el-icon><Document /></el-icon>
            <span>规则管理</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="group-system">
          <template #title>
            <el-icon><SetUp /></el-icon>
            <span>系统设置</span>
          </template>
          <el-menu-item v-if="canMenu('menu.system.config')" index="/system/config">
            <el-icon><SetUp /></el-icon>
            <span>系统配置</span>
          </el-menu-item>
          <el-menu-item v-if="canMenu('menu.llm.providers')" index="/llm/providers">
            <el-icon><SetUp /></el-icon>
            <span>模型供应商</span>
          </el-menu-item>
          <el-menu-item v-if="canMenu('menu.usage.keys')" index="/usage/keys">
            <el-icon><Key /></el-icon>
            <span>API Key</span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span>{{ username }}</span>
        <el-button text @click="logout">退出</el-button>
      </el-header>
      <el-main>
        <div class="page-content" :class="{ 'is-chat-page': isChatRoute }">
          <router-view />
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, UserFilled, Folder, Plus, SetUp, Document, Key, ChatDotRound } from '@element-plus/icons-vue'
import { clearPermissionArray, hasPermission } from '@/utils/permissions.js'

const route = useRoute()
const router = useRouter()
const username = computed(() => localStorage.getItem('username') || 'admin')
const defaultOpeneds = ['group-org', 'group-capability', 'group-system']
const isChatRoute = computed(() => route.path === '/ai/chat')

function canMenu(permissionKey) {
  return hasPermission(permissionKey)
}

function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  localStorage.removeItem('role')
  clearPermissionArray()
  router.replace('/login')
}
</script>

<style scoped>
.layout {
  height: 100vh;
  overflow: hidden;
}

.aside {
  background: var(--color-bg-container);
  border-right: 1px solid var(--color-border-secondary);
  display: flex;
  flex-direction: column;
}

.menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
}

.logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-primary-6);
  border-bottom: 1px solid var(--color-border-secondary);
  background: var(--color-bg-container);
  flex-shrink: 0;
}

.header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  border-bottom: 1px solid var(--color-border-secondary);
  background: var(--color-bg-container);
}

:deep(.el-main) {
  padding: 20px;
  background: var(--color-bg-layout);
  overflow-y: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.page-content {
  background: var(--color-bg-container);
  border-radius: var(--radius-lg);
  padding: 24px;
  min-height: calc(100% - 40px);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
  box-sizing: border-box;
}

.page-content.is-chat-page {
  flex: 1;
  min-height: 0;
  height: 100%;
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
