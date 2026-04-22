import { createRouter, createWebHashHistory } from 'vue-router'
import { getFallbackPath, hasPermission, isSuperAdmin, pathPermission } from '@/utils/permissions.js'
import { isChatSettingsRoutePath, resolveSettingsAwarePath } from '@/utils/chat-settings-route.js'

const SettingsCenterChatStub = { render: () => null }

const routes = [
  { path: '/init', component: () => import('../views/auth/InitPage.vue') },
  { path: '/intro', component: () => import('../views/public/IntroPage.vue') },
  { path: '/market', component: () => import('../views/public/MarketPage.vue') },
  { path: '/updates', component: () => import('../views/public/ChangelogPage.vue') },
  { path: '/login', component: () => import('../views/auth/LoginPage.vue') },
  { path: '/register', component: () => import('../views/auth/RegisterPage.vue') },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/intro',
    children: [
      { path: 'workbench', component: () => import('../views/desktop/DesktopWorkbench.vue') },
      { path: 'settings-center', component: () => import('../views/desktop/SettingsLauncher.vue') },
      { path: 'desktop/background', component: () => import('../views/desktop/DesktopWallpaperSettings.vue') },
      { path: 'desktop', redirect: '/workbench' },
      { path: 'ai/chat', component: () => import('../views/projects/ProjectChat.vue') },
      {
        path: 'ai/chat/settings',
        component: () => import('../views/projects/ProjectChat.vue'),
        children: [
          { path: '', redirect: '/ai/chat/settings/chat' },
          { path: 'chat', component: SettingsCenterChatStub },
          { path: 'user/settings', component: () => import('../views/users/UserSettings.vue') },
          { path: 'system/config', component: () => import('../views/system/SystemConfig.vue') },
          { path: 'desktop/background', component: () => import('../views/desktop/DesktopWallpaperSettings.vue') },
          { path: 'changelog-entries', component: () => import('../views/system/ChangelogManager.vue') },
          { path: 'work-sessions', component: () => import('../views/system/WorkSessionManager.vue') },
          { path: 'statistics', component: () => import('../views/system/StatisticsDashboard.vue') },
          { path: 'online-users', component: () => import('../views/system/OnlineUserManager.vue'), meta: { superAdminOnly: true } },
          { path: 'mcp-monitor', component: () => import('../views/system/McpMonitorManager.vue'), meta: { superAdminOnly: true } },
          { path: 'dictionaries', component: () => import('../views/system/DictionaryManager.vue') },
          { path: 'llm/providers', component: () => import('../views/llm/ModelProviderManager.vue') },
          { path: 'projects', component: () => import('../views/projects/ProjectList.vue') },
          { path: 'projects/:id', component: () => import('../views/projects/ProjectDetail.vue') },
          { path: 'agent-templates', component: () => import('../views/agent-templates/AgentTemplateList.vue') },
          { path: 'employees', component: () => import('../views/employees/EmployeeList.vue') },
          { path: 'employees/create', component: () => import('../views/employees/EmployeeForm.vue') },
          { path: 'employees/:id/edit', component: () => import('../views/employees/EmployeeForm.vue') },
          { path: 'employees/:id/usage', component: () => import('../views/employees/EmployeeUsage.vue') },
          { path: 'employees/:id', component: () => import('../views/employees/EmployeeDetail.vue') },
          { path: 'skill-resources', component: () => import('../views/skills/SkillResourceList.vue') },
          { path: 'skill-resources/:source/:slug(.*)', component: () => import('../views/skills/SkillResourceDetail.vue') },
          { path: 'skills', component: () => import('../views/skills/SkillList.vue') },
          { path: 'skills/create', component: () => import('../views/skills/SkillCreate.vue') },
          { path: 'skills/:id/edit', component: () => import('../views/skills/SkillEdit.vue') },
          { path: 'skills/:id', component: () => import('../views/skills/SkillDetail.vue') },
          { path: 'rules', component: () => import('../views/rules/RuleList.vue') },
          { path: 'rules/create', component: () => import('../views/rules/RuleCreate.vue') },
          { path: 'rules/:id/edit', component: () => import('../views/rules/RuleEdit.vue') },
          { path: 'rules/:id', component: () => import('../views/rules/RuleDetail.vue') },
          { path: 'memory/:id', component: () => import('../views/memory/MemoryManager.vue') },
          { path: 'sync/:id', component: () => import('../views/sync/SyncStatus.vue') },
          { path: 'usage/keys', component: () => import('../views/usage/ApiKeyList.vue') },
          { path: 'feedback/:id', component: () => import('../views/evolution/FeedbackTicketList.vue') },
          { path: 'feedback/:id/batch-analyze', component: () => import('../views/evolution/FeedbackBatchAnalyze.vue') },
          { path: 'feedback/:id/:feedbackId', component: () => import('../views/evolution/FeedbackDetail.vue') },
          { path: 'users', component: () => import('../views/users/UserList.vue') },
          { path: 'roles', component: () => import('../views/users/RoleList.vue') },
        ],
      },
      { path: 'users', component: () => import('../views/users/UserList.vue') },
      { path: 'roles', component: () => import('../views/users/RoleList.vue') },
      { path: 'user/settings', component: () => import('../views/users/UserSettings.vue') },
      { path: 'projects', component: () => import('../views/projects/ProjectList.vue') },
      { path: 'projects/:id', component: () => import('../views/projects/ProjectDetail.vue') },
      {
        path: 'materials',
        component: () => import('../views/projects/ProjectCreationWorkspace.vue'),
        children: [
          { path: '', component: () => import('../views/projects/ProjectMaterialLibrary.vue') },
          { path: 'studio', component: () => import('../views/projects/ProjectShortFilmStudio.vue') },
          { path: 'voices', component: () => import('../views/projects/ProjectVoiceLibrary.vue') },
          { path: 'works', component: () => import('../views/projects/ProjectWorksGallery.vue') },
        ],
      },
      { path: 'system/config', component: () => import('../views/system/SystemConfig.vue') },
      { path: 'changelog-entries', component: () => import('../views/system/ChangelogManager.vue') },
      { path: 'work-sessions', component: () => import('../views/system/WorkSessionManager.vue') },
      { path: 'statistics', component: () => import('../views/system/StatisticsDashboard.vue') },
      { path: 'online-users', component: () => import('../views/system/OnlineUserManager.vue'), meta: { superAdminOnly: true } },
      { path: 'mcp-monitor', component: () => import('../views/system/McpMonitorManager.vue'), meta: { superAdminOnly: true } },
      { path: 'dictionaries', component: () => import('../views/system/DictionaryManager.vue') },
      { path: 'employees', component: () => import('../views/employees/EmployeeList.vue') },
      { path: 'agent-templates', component: () => import('../views/agent-templates/AgentTemplateList.vue') },
      { path: 'employees/create', component: () => import('../views/employees/EmployeeForm.vue') },
      { path: 'employees/:id/edit', component: () => import('../views/employees/EmployeeForm.vue') },
      { path: 'employees/:id/usage', component: () => import('../views/employees/EmployeeUsage.vue') },
      { path: 'employees/:id', component: () => import('../views/employees/EmployeeDetail.vue') },
      { path: 'skill-resources', component: () => import('../views/skills/SkillResourceList.vue') },
      { path: 'skill-resources/:source/:slug(.*)', component: () => import('../views/skills/SkillResourceDetail.vue') },
      { path: 'skills', component: () => import('../views/skills/SkillList.vue') },
      { path: 'skills/create', component: () => import('../views/skills/SkillCreate.vue') },
      { path: 'skills/:id/edit', component: () => import('../views/skills/SkillEdit.vue') },
      { path: 'skills/:id', component: () => import('../views/skills/SkillDetail.vue') },
      { path: 'rules', component: () => import('../views/rules/RuleList.vue') },
      { path: 'rules/create', component: () => import('../views/rules/RuleCreate.vue') },
      { path: 'rules/:id/edit', component: () => import('../views/rules/RuleEdit.vue') },
      { path: 'rules/:id', component: () => import('../views/rules/RuleDetail.vue') },
      { path: 'memory/:id', component: () => import('../views/memory/MemoryManager.vue') },
      { path: 'sync/:id', component: () => import('../views/sync/SyncStatus.vue') },
      { path: 'usage/keys', component: () => import('../views/usage/ApiKeyList.vue') },
      { path: 'llm/providers', component: () => import('../views/llm/ModelProviderManager.vue') },
      { path: 'market', component: () => import('../views/public/MarketPage.vue') },
      { path: 'evolution/:id', component: () => import('../views/evolution/EvolutionReport.vue') },
      { path: 'review/:id', component: () => import('../views/evolution/CandidateReview.vue') },
      { path: 'feedback/:id', component: () => import('../views/evolution/FeedbackTicketList.vue') },
      { path: 'feedback/:id/batch-analyze', component: () => import('../views/evolution/FeedbackBatchAnalyze.vue') },
      { path: 'feedback/:id/:feedbackId', component: () => import('../views/evolution/FeedbackDetail.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

const PUBLIC_PATHS = new Set(['/init', '/intro', '/market', '/updates', '/login', '/register'])
router.beforeEach((to, from) => {
  const normalizedPath = String(to.path || '').trim() || '/'
  if (normalizedPath === '/') {
    return '/intro'
  }

  const token = localStorage.getItem('token')
  const isPublic = PUBLIC_PATHS.has(normalizedPath)

  if (!token && !isPublic) {
    return '/login'
  }

  if (token && (normalizedPath === '/login' || normalizedPath === '/register')) {
    return getFallbackPath()
  }

  if (
    isChatSettingsRoutePath(from.path) &&
    !isChatSettingsRoutePath(to.path) &&
    to.path.startsWith('/') &&
    to.path !== '/ai/chat'
    && to.path !== '/workbench'
  ) {
    const rewritten = resolveSettingsAwarePath(from.path, to.path, to.path)
    if (rewritten !== to.path) {
      return {
        path: rewritten,
        query: to.query,
        hash: to.hash,
      }
    }
  }

  const requiredPermission = pathPermission(to.path)
  if (requiredPermission && !hasPermission(requiredPermission)) {
    const fallback = getFallbackPath()
    if (fallback === to.path) {
      return '/login'
    }
    return fallback
  }

  if (to.matched.some((record) => record.meta?.superAdminOnly) && !isSuperAdmin()) {
    const fallback = getFallbackPath()
    if (fallback === to.path) {
      return '/ai/chat'
    }
    return fallback
  }

  return true
})

export default router
