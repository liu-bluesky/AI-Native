<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>使用统计: {{ employeeId }}</h3>
      <div>
        <el-select v-model="days" style="width: 120px; margin-right: 8px" @change="fetchStats">
          <el-option :value="1" label="最近 1 天" />
          <el-option :value="7" label="最近 7 天" />
          <el-option :value="30" label="最近 30 天" />
        </el-select>
        <el-button :loading="skillConfigLoading" @click="fetchSkillConfigs">刷新技能配置</el-button>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-row :gutter="16" class="stat-cards">
      <el-col :span="8">
        <el-statistic title="总事件数" :value="stats.total_events || 0" />
      </el-col>
      <el-col :span="8">
        <el-statistic title="工具调用" :value="stats.tool_calls || 0" />
      </el-col>
      <el-col :span="8">
        <el-statistic title="活跃用户" :value="stats.active_developers || 0" />
      </el-col>
    </el-row>

    <h4 class="section-title">按用户统计</h4>
    <el-table :data="stats.by_developer || []" stripe size="small">
      <el-table-column prop="developer_name" label="用户" width="140" />
      <el-table-column prop="api_key" label="Key" width="300" />
      <el-table-column prop="cnt" label="事件数" width="100" />
      <el-table-column label="最近活跃">
        <template #default="{ row }">{{ formatDateTime(row.last_seen) }}</template>
      </el-table-column>
    </el-table>

    <h4 class="section-title">按工具统计</h4>
    <el-table :data="stats.by_tool || []" stripe size="small">
      <el-table-column prop="tool_name" label="工具名" />
      <el-table-column prop="cnt" label="调用次数" width="100" />
    </el-table>

    <h4 class="section-title">技能配置（按用户）</h4>
    <div class="checked-skills">
      <span class="checked-skills-label">已检查技能：</span>
      <el-tag v-for="s in checkedSkills" :key="s.id" size="small" class="checked-skill-tag">
        {{ s.name }}
      </el-tag>
      <span v-if="!checkedSkills.length" class="checked-skills-empty">未绑定技能</span>
    </div>
    <el-table :data="skillConfigs" stripe size="small" v-loading="skillConfigLoading">
      <el-table-column prop="user" label="用户" width="120" />
      <el-table-column prop="skill_name" label="技能" width="180" />
      <el-table-column prop="file" label="配置文件" width="240" />
      <el-table-column label="连接信息" min-width="260">
        <template #default="{ row }">
          {{ connectionSummary(row.config) }}
        </template>
      </el-table-column>
      <el-table-column label="项目/库信息" min-width="180">
        <template #default="{ row }">
          {{ projectSummary(row.config) }}
        </template>
      </el-table-column>
      <el-table-column label="详情" width="90">
        <template #default="{ row }">
          <el-popover placement="left" trigger="click" width="420">
            <template #reference>
              <el-button text size="small">查看</el-button>
            </template>
            <pre class="config-json">{{ formatConfig(row.config) }}</pre>
          </el-popover>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!skillConfigLoading && !skillConfigs.length" description="暂无技能配置" :image-size="60" />

    <h4 class="section-title">最近事件</h4>
    <el-table :data="stats.recent || []" stripe size="small">
      <el-table-column prop="developer_name" label="用户" width="120" />
      <el-table-column prop="event_type" label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="row.event_type === 'tool_call' ? 'warning' : 'info'" size="small">
            {{ row.event_type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="tool_name" label="工具" width="160" />
      <el-table-column prop="client_ip" label="IP" width="120" />
      <el-table-column label="时间">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && !(stats.recent || []).length" description="暂无使用记录" :image-size="60" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'

const route = useRoute()
const employeeId = computed(() => route.params.id)
const loading = ref(false)
const days = ref(7)
const stats = reactive({})
const skillConfigLoading = ref(false)
const checkedSkills = ref([])
const skillConfigs = ref([])

function connectionSummary(config) {
  const type = String(config?.type || 'db')
  const host = String(config?.host || '-')
  const port = String(config?.port || '-')
  const database = String(config?.database || '-')
  return `${type}://${host}:${port}/${database}`
}

function projectSummary(config) {
  if (Array.isArray(config?.projects) && config.projects.length) {
    return config.projects.join(', ')
  }
  if (config?.projects && typeof config.projects === 'object') {
    const names = Object.keys(config.projects)
    if (names.length) return names.join(', ')
  }
  if (Array.isArray(config?.databases) && config.databases.length) {
    return config.databases.join(', ')
  }
  if (config?.databases && typeof config.databases === 'object') {
    const names = Object.keys(config.databases)
    if (names.length) return names.join(', ')
  }
  if (config?.project) return String(config.project)
  if (config?.database) return String(config.database)
  return '-'
}

function formatConfig(config) {
  return JSON.stringify(config || {}, null, 2)
}

async function fetchStats() {
  loading.value = true
  try {
    const data = await api.get(`/usage/employees/${employeeId.value}/stats?days=${days.value}`)
    Object.assign(stats, data)
  } catch {
    ElMessage.error('加载统计失败')
  } finally {
    loading.value = false
  }
}

async function fetchSkillConfigs() {
  skillConfigLoading.value = true
  skillConfigs.value = []
  checkedSkills.value = []
  try {
    const [employeeRes, bindingsRes, skillsRes] = await Promise.all([
      api.get(`/employees/${employeeId.value}`),
      api.get(`/employees/${employeeId.value}/skills`).catch(() => ({ bindings: [] })),
      api.get('/skills').catch(() => ({ skills: [] })),
    ])

    const skillNameMap = new Map((skillsRes.skills || []).map((s) => [s.id, s.name || s.id]))
    const skillIds = new Set()
    for (const skillId of employeeRes.employee?.skills || []) {
      if (skillId) skillIds.add(skillId)
    }
    for (const binding of bindingsRes.bindings || []) {
      if (binding?.skill_id) skillIds.add(binding.skill_id)
    }

    const ids = Array.from(skillIds)
    checkedSkills.value = ids.map((id) => ({ id, name: skillNameMap.get(id) || id }))
    if (!ids.length) return

    const configResults = await Promise.all(
      ids.map(async (skillId) => {
        try {
          const { configs } = await api.get(`/skills/${skillId}/configs`)
          return { skillId, skillName: skillNameMap.get(skillId) || skillId, configs: configs || [] }
        } catch {
          return { skillId, skillName: skillNameMap.get(skillId) || skillId, configs: [] }
        }
      }),
    )

    const rows = []
    for (const item of configResults) {
      for (const conf of item.configs) {
        rows.push({
          user: conf.user || '默认',
          file: conf.file || '-',
          config: conf.config || {},
          skill_id: item.skillId,
          skill_name: item.skillName,
        })
      }
    }
    rows.sort((a, b) => `${a.user}-${a.skill_name}`.localeCompare(`${b.user}-${b.skill_name}`, 'zh-Hans-CN'))
    skillConfigs.value = rows
  } catch {
    ElMessage.error('加载技能配置失败')
  } finally {
    skillConfigLoading.value = false
  }
}

async function initPage() {
  await Promise.all([fetchStats(), fetchSkillConfigs()])
}

onMounted(initPage)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 { margin: 0; }
.stat-cards { margin-bottom: 16px; }
.section-title { margin: 20px 0 8px; }

.checked-skills {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.checked-skills-label {
  color: var(--color-text-secondary);
  font-size: 13px;
}

.checked-skill-tag {
  margin-right: 2px;
}

.checked-skills-empty {
  color: var(--color-text-tertiary);
  font-size: 13px;
}

.config-json {
  margin: 0;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
}
</style>
