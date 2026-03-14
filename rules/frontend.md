# 前端编码规范

> 适用于 web-admin/frontend/，Vue 3 + Element Plus + Vite 技术栈。

## 技术栈约束

- Vue 3.5+ Composition API（`<script setup>` 语法）
- Element Plus 2.9+（中文 locale：zh-CN）
- vue-router 4.5+（hash 模式）
- axios 1.7+（封装于 `utils/api.js`）
- Vite 构建，开发端口 3000，`/api` 与 `/mcp` 代理到 `vite.config.js` 解析出的 API 地址

## 组件结构

### 单文件组件顺序

```vue
<template>
  <!-- 模板 -->
</template>

<script setup>
// 1. 导入
// 2. 路由/状态
// 3. 响应式数据
// 4. 计算属性
// 5. 函数
// 6. 生命周期
</script>

<style scoped>
/* 局部样式 */
</style>
```

### 导入规范

```js
// 1. Vue 核心
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// 2. Element Plus（按需）
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, Plus, SetUp } from '@element-plus/icons-vue'

// 3. 本地模块（使用 @ 别名，指向 src/）
import api from '@/utils/api.js'
```

### 响应式数据模式

```js
// 简单值用 ref
const loading = ref(false)
const employees = ref([])

// 对象用 reactive（适合表单）
const form = reactive({
  name: '',
  description: '',
  skills: [],
})

// 路由参数用 computed
const employeeId = computed(() => route.params.id)
```

## API 调用模式

统一使用 `utils/api.js` 封装的 axios 实例：

```js
async function fetchList() {
  loading.value = true
  try {
    const { employees: list } = await api.get('/employees')
    employees.value = list
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}
```

关键约束：
- 响应已自动解包为 `res.data`，直接解构业务字段
- 401 自动跳转登录页，无需手动处理
- 错误提示用 `ElMessage.error()`
- 加载状态用 `loading` ref + `v-loading` 指令

## 路由约定

### 结构

```js
// hash 模式，懒加载，视图按域分组
const routes = [
  { path: '/init', component: () => import('../views/auth/InitPage.vue') },
  { path: '/login', component: () => import('../views/auth/LoginPage.vue') },
  { path: '/register', component: () => import('../views/auth/RegisterPage.vue') },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/employees',
    children: [
      { path: 'projects', component: () => import('../views/projects/ProjectList.vue') },
      { path: 'system/config', component: () => import('../views/system/SystemConfig.vue') },
      { path: 'employees', component: () => import('../views/employees/EmployeeList.vue') },
      { path: 'employees/:id', component: () => import('../views/employees/EmployeeDetail.vue') },
    ],
  },
]
```

### 目录结构

```
views/
├── Layout.vue              ← 全局布局（不归属任何域）
├── auth/                   ← 认证相关
├── employees/              ← 员工管理
├── projects/               ← 项目列表 / 详情 / 聊天
├── skills/                 ← 技能管理
├── rules/                  ← 规则管理
├── memory/                 ← 记忆管理
├── personas/               ← 人设管理
├── evolution/              ← 进化引擎 + 候选审核
└── sync/                   ← 同步状态
```

当前还包含这些视图域：

- `llm/`：模型供应商管理
- `system/`：系统配置
- `usage/`：API Key 等使用控制
- `users/`：用户与角色

### 命名约定

- 视图文件：`PascalCase`，放在对应域子目录下
- 列表页：`XxxList.vue`
- 详情页：`XxxDetail.vue`
- 创建页：`XxxCreate.vue`
- 管理页：`XxxManager.vue`
- 公共页面（init/login）放在 `auth/` 目录，不嵌套在 Layout 下

## Element Plus 使用规范

### 布局

- 主布局用 `el-container` + `el-aside` + `el-header` + `el-main`
- 侧边栏宽度固定 200px
- 导航用 `el-menu` 配合 `router` 属性实现路由联动

### 表格

```vue
<el-table :data="list" v-loading="loading" stripe>
  <el-table-column prop="id" label="ID" width="140" />
  <el-table-column label="操作" width="200" fixed="right">
    <template #default="{ row }">
      <el-button text type="primary" @click="handleView(row)">详情</el-button>
    </template>
  </el-table-column>
</el-table>
```

### 表单

- 表单验证用 `el-form` 的 `:rules` + `formRef.value.validate()`
- 提交前必须 `await formRef.value.validate()`

### 反馈组件

| 场景 | 组件 |
|------|------|
| 操作成功/失败 | `ElMessage.success()` / `ElMessage.error()` |
| 危险操作确认 | `ElMessageBox.confirm()` |
| 标签展示 | `el-tag`，按语义着色：success/warning/danger/info |
| 空状态 | `el-empty` 配合 `:image-size="60"` |
| 详情展示 | `el-descriptions` + `el-descriptions-item` |

### 颜色语义映射

```js
// 风险等级
function riskColor(domain) {
  return { low: 'success', medium: 'warning', high: 'danger' }[domain] || 'info'
}

// 严重程度
function severityColor(sev) {
  return { required: 'danger', recommended: 'warning', optional: 'info' }[sev] || ''
}
```

## 状态管理

当前项目不使用 Vuex/Pinia，状态管理策略：

- 组件内状态：`ref` / `reactive`
- 跨页面状态：`localStorage`（token、username、role、permissions）
- 服务端状态：每次进入页面 `onMounted` 重新拉取

## 样式规范

- 所有组件样式使用 `<style scoped>`
- 工具栏布局统一模式：

```css
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
```

- 详细的 UI 设计规范（色彩/字体/间距/圆角）见 `rules/ui-design.md`

## 禁止事项

- 禁止使用 Options API（data/methods/computed 选项式写法）
- 禁止全局状态管理库（当前规模不需要）
- 禁止直接操作 DOM（用 ref + template ref 代替）
- 禁止在 template 中写复杂逻辑（提取为 computed 或函数）
- 禁止裸 axios 调用（必须通过 `utils/api.js`）
