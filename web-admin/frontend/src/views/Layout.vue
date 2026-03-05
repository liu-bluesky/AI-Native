<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">AI 员工工厂</div>
      <el-menu :default-active="route.path" router class="menu">
        <el-menu-item index="/employees">
          <el-icon><User /></el-icon>
          <span>员工管理</span>
        </el-menu-item>
        <el-menu-item index="/projects">
          <el-icon><Folder /></el-icon>
          <span>项目管理</span>
        </el-menu-item>
        <el-menu-item index="/system/config">
          <el-icon><SetUp /></el-icon>
          <span>系统配置</span>
        </el-menu-item>
        <el-menu-item index="/employees/create">
          <el-icon><Plus /></el-icon>
          <span>创建员工</span>
        </el-menu-item>
        <el-menu-item index="/skills">
          <el-icon><SetUp /></el-icon>
          <span>技能目录</span>
        </el-menu-item>
        <el-menu-item index="/rules">
          <el-icon><Document /></el-icon>
          <span>规则管理</span>
        </el-menu-item>
        <el-menu-item index="/usage/keys">
          <el-icon><Key /></el-icon>
          <span>API Key</span>
        </el-menu-item>
        <el-menu-item index="/llm/providers">
          <el-icon><SetUp /></el-icon>
          <span>模型供应商</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span>{{ username }}</span>
        <el-button text @click="logout">退出</el-button>
      </el-header>
      <el-main>
        <div class="page-content">
          <router-view />
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, Folder, Plus, SetUp, Document, Key } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const username = computed(() => localStorage.getItem('username') || 'admin')

function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
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
}

.page-content {
  background: var(--color-bg-container);
  border-radius: var(--radius-lg);
  padding: 24px;
  min-height: calc(100% - 40px);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
  box-sizing: border-box;
}
</style>
