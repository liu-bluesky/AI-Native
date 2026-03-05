import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/init', component: () => import('../views/auth/InitPage.vue') },
  { path: '/login', component: () => import('../views/auth/LoginPage.vue') },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/employees',
    children: [
      { path: 'projects', component: () => import('../views/projects/ProjectList.vue') },
      { path: 'projects/:id', component: () => import('../views/projects/ProjectDetail.vue') },
      { path: 'system/config', component: () => import('../views/system/SystemConfig.vue') },
      { path: 'employees', component: () => import('../views/employees/EmployeeList.vue') },
      { path: 'employees/create', component: () => import('../views/employees/EmployeeForm.vue') },
      { path: 'employees/:id/edit', component: () => import('../views/employees/EmployeeForm.vue') },
      { path: 'employees/:id/usage', component: () => import('../views/employees/EmployeeUsage.vue') },
      { path: 'employees/:id', component: () => import('../views/employees/EmployeeDetail.vue') },
      { path: 'skills', component: () => import('../views/skills/SkillList.vue') },
      { path: 'skills/create', component: () => import('../views/skills/SkillCreate.vue') },
      { path: 'skills/:id/edit', component: () => import('../views/skills/SkillEdit.vue') },
      { path: 'skills/:id', component: () => import('../views/skills/SkillDetail.vue') },
      { path: 'rules', component: () => import('../views/rules/RuleList.vue') },
      { path: 'rules/create', component: () => import('../views/rules/RuleCreate.vue') },
      { path: 'rules/:id/edit', component: () => import('../views/rules/RuleEdit.vue') },
      { path: 'rules/:id', component: () => import('../views/rules/RuleDetail.vue') },
      { path: 'memory/:id', component: () => import('../views/memory/MemoryManager.vue') },
      { path: 'personas', component: () => import('../views/personas/PersonaList.vue') },
      { path: 'personas/create', component: () => import('../views/personas/PersonaCreate.vue') },
      { path: 'personas/:id/edit', component: () => import('../views/personas/PersonaEdit.vue') },
      { path: 'personas/:id', component: () => import('../views/personas/PersonaDetail.vue') },
      { path: 'sync/:id', component: () => import('../views/sync/SyncStatus.vue') },
      { path: 'usage/keys', component: () => import('../views/usage/ApiKeyList.vue') },
      { path: 'llm/providers', component: () => import('../views/llm/ModelProviderManager.vue') },
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

export default router
