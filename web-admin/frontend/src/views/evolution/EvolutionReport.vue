<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>进化报告: {{ employeeId }}</h3>
      <el-button @click="$router.back()">返回</el-button>
    </div>

    <el-row :gutter="16" v-if="report.summary">
      <el-col :span="6">
        <el-statistic title="待审候选" :value="report.summary.pending_count" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="已通过" :value="report.summary.approved_count" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="已拒绝" :value="report.summary.rejected_count" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="近期事件" :value="report.summary.recent_events" />
      </el-col>
    </el-row>

    <h4 class="section-title-lg">待审候选规则</h4>
    <el-table :data="report.pending_candidates" stripe v-if="report.pending_candidates?.length">
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="confidence" label="置信度" width="100" />
      <el-table-column prop="risk_domain" label="风险域" width="100" />
      <el-table-column prop="status" label="状态" width="100" />
      <el-table-column label="操作" min-width="100" class-name="table-action-column">
        <template #default="{ row }">
          <el-button text type="primary" @click="$router.push(`/review/${employeeId}?cid=${row.id}`)">
            审核
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="暂无待审候选" :image-size="60" />

    <h4 class="section-title-lg">近期事件</h4>
    <el-timeline v-if="report.recent_events?.length">
      <el-timeline-item
        v-for="evt in report.recent_events"
        :key="evt.id"
        :timestamp="formatDateTime(evt.created_at)"
        placement="top"
      >
        {{ evt.type }} — {{ evt.target }}
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else description="暂无事件" :image-size="60" />

    <!-- 使用模式分析 -->
    <h4 class="section-title-lg">使用模式分析</h4>
    <div v-if="patterns.total_logs > 0">
      <el-row :gutter="16" class="patterns-stats-row">
        <el-col :span="8">
          <el-statistic title="日志总数" :value="patterns.total_logs" />
        </el-col>
        <el-col :span="8">
          <el-statistic title="纠正率" :value="(patterns.correction_rate * 100).toFixed(1) + '%'" />
        </el-col>
      </el-row>

      <el-descriptions title="动作分布" :column="3" size="small" border v-if="patterns.action_distribution">
        <el-descriptions-item v-for="(count, action) in patterns.action_distribution" :key="action" :label="action">
          {{ count }}
        </el-descriptions-item>
      </el-descriptions>

      <h5 class="section-title-sm">高频规则 Top 10</h5>
      <el-table :data="patterns.top_rules" stripe size="small" v-if="patterns.top_rules?.length">
        <el-table-column prop="rule_id" label="规则 ID" />
        <el-table-column prop="count" label="命中次数" width="100" align="center" />
      </el-table>
      <el-empty v-else description="暂无高频规则" :image-size="40" />
    </div>
    <el-empty v-else description="暂无使用日志" :image-size="60" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'
import { formatDateTime } from '@/utils/date.js'

const route = useRoute()
const loading = ref(false)
const employeeId = computed(() => route.params.id)
const report = reactive({})
const patterns = reactive({ total_logs: 0, correction_rate: 0, action_distribution: {}, top_rules: [] })

async function fetchReport() {
  loading.value = true
  try {
    const data = await api.get(`/evolution/${employeeId.value}/report`)
    Object.assign(report, data)
  } catch {
    ElMessage.error('加载进化报告失败')
  } finally {
    loading.value = false
  }
}

async function fetchPatterns() {
  try {
    const data = await api.get(`/evolution/${employeeId.value}/patterns`)
    Object.assign(patterns, data)
  } catch { /* ignore */ }
}

onMounted(() => {
  fetchReport()
  fetchPatterns()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 { margin: 0; }

.section-title-lg {
  margin-top: 24px;
}

.section-title-sm {
  margin-top: 12px;
}

.patterns-stats-row {
  margin-bottom: 12px;
}
</style>
