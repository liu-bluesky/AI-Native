<template>
  <main class="admin-feedback-page">
    <section class="admin-hero">
      <div>
        <div class="admin-eyebrow">FEEDBACK OPERATIONS</div>
        <h1>反馈处理中心</h1>
        <p>
          统一受理产品体验、系统稳定性和 AI 相关反馈，完成分派、流转和用户回复。
        </p>
      </div>
      <el-button :loading="loading" @click="refresh">刷新数据</el-button>
    </section>

    <section class="summary-grid">
      <article class="summary-card">
        <span>全部反馈</span>
        <strong>{{ summary.total || 0 }}</strong>
      </article>
      <article class="summary-card summary-card--blue">
        <span>待受理</span>
        <strong>{{ summary.by_status?.submitted || 0 }}</strong>
      </article>
      <article class="summary-card summary-card--amber">
        <span>处理中</span>
        <strong>{{ summary.by_status?.processing || 0 }}</strong>
      </article>
      <article class="summary-card summary-card--green">
        <span>已解决</span>
        <strong>{{ summary.by_status?.resolved || 0 }}</strong>
      </article>
    </section>

    <section class="admin-panel filter-panel">
      <div class="filter-grid">
        <el-input
          v-model="filters.keyword"
          clearable
          placeholder="搜索编号、标题、描述或用户"
          @keyup.enter="loadTickets"
        />
        <el-select
          v-model="filters.status"
          clearable
          placeholder="全部状态"
          @change="loadTickets"
        >
          <el-option
            v-for="item in FEEDBACK_STATUSES"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select
          v-model="filters.category"
          clearable
          placeholder="全部类型"
          @change="loadTickets"
        >
          <el-option
            v-for="item in FEEDBACK_CATEGORIES"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select
          v-model="filters.priority"
          clearable
          placeholder="全部优先级"
          @change="loadTickets"
        >
          <el-option
            v-for="item in FEEDBACK_PRIORITIES"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-button type="primary" @click="loadTickets">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
    </section>

    <section class="admin-panel table-panel">
      <div class="table-panel__head">
        <div>
          <div class="admin-eyebrow">TICKET QUEUE</div>
          <h2>反馈工单</h2>
        </div>
        <span>共 {{ tickets.length }} 条</span>
      </div>
      <el-table
        v-loading="loading"
        :data="tickets"
        stripe
        @row-click="openDetail"
      >
        <el-table-column prop="id" label="反馈编号" width="165" />
        <el-table-column label="类型" width="170">
          <template #default="{ row }">{{
            feedbackCategoryLabel(row.category)
          }}</template>
        </el-table-column>
        <el-table-column label="标题与提交人" min-width="300">
          <template #default="{ row }">
            <div class="title-cell">
              <strong>{{ row.title }}</strong>
              <span>{{ row.reporter_name_snapshot || row.reporter_id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="100">
          <template #default="{ row }">{{
            priorityLabel(row.priority)
          }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="feedbackStatusMeta(row.status).type">{{
              feedbackStatusMeta(row.status).label
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{
            formatDateTime(row.updated_at)
          }}</template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!loading && !tickets.length"
        description="暂无匹配的反馈工单"
      />
    </section>

    <el-drawer
      v-model="detailVisible"
      size="min(1260px, 96vw)"
      title="反馈处理详情"
    >
      <div v-if="selectedTicket" class="detail-layout">
        <section class="detail-header">
          <div>
            <span>{{ selectedTicket.id }}</span>
            <h2>{{ selectedTicket.title }}</h2>
            <p>
              {{
                selectedTicket.reporter_name_snapshot ||
                selectedTicket.reporter_id
              }}
              · {{ formatDateTime(selectedTicket.created_at) }}
            </p>
          </div>
          <el-tag
            :type="feedbackStatusMeta(selectedTicket.status).type"
            size="large"
          >
            {{ feedbackStatusMeta(selectedTicket.status).label }}
          </el-tag>
        </section>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="反馈类型">{{
            feedbackCategoryLabel(selectedTicket.category)
          }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{
            selectedTicket.source_entry
          }}</el-descriptions-item>
          <el-descriptions-item label="影响程度">{{
            selectedTicket.impact_level
          }}</el-descriptions-item>
          <el-descriptions-item label="发生频率">{{
            selectedTicket.frequency
          }}</el-descriptions-item>
          <el-descriptions-item label="详细描述" :span="2">{{
            selectedTicket.description
          }}</el-descriptions-item>
          <el-descriptions-item label="期望结果" :span="2">{{
            selectedTicket.expected_result || "-"
          }}</el-descriptions-item>
        </el-descriptions>

        <section class="process-card">
          <div class="process-card__head">
            <div>
              <strong>工单处理</strong>
              <p>更新负责人、优先级和处理状态。</p>
            </div>
          </div>
          <div class="process-grid">
            <el-form-item label="负责人">
              <el-input
                v-model="processForm.assignee_id"
                placeholder="输入负责人用户名"
              />
            </el-form-item>
            <el-form-item label="优先级">
              <el-select v-model="processForm.priority">
                <el-option
                  v-for="item in FEEDBACK_PRIORITIES"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="处理状态">
              <el-select v-model="processForm.status">
                <el-option
                  v-for="item in FEEDBACK_STATUSES"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <div class="process-actions">
              <el-button :loading="saving" @click="saveAssignment"
                >保存负责人</el-button
              >
              <el-button
                type="primary"
                :loading="saving"
                @click="saveTransition"
                >更新状态</el-button
              >
            </div>
          </div>
        </section>

        <section v-if="hasAiEvidence" class="evidence-card">
          <div class="process-card__head">
            <div>
              <strong>AI 回答与执行证据</strong>
              <p>回答 ID 与执行记录是辅助定位信息，不影响普通反馈受理。</p>
            </div>
          </div>
          <div class="evidence-grid">
            <div>
              <span>回答 ID</span>
              <el-button
                v-if="selectedTicket.ai_evidence.assistant_message_id"
                link
                type="primary"
                @click="openSupervision"
                >{{
                  selectedTicket.ai_evidence.assistant_message_id
                }}</el-button
              >
              <strong v-else>-</strong>
            </div>
            <div>
              <span>执行 ID</span
              ><strong>{{
                selectedTicket.ai_evidence.execution_id || "-"
              }}</strong>
            </div>
            <div>
              <span>会话 ID</span
              ><strong>{{
                selectedTicket.ai_evidence.chat_session_id || "-"
              }}</strong>
            </div>
          </div>
          <el-button
            v-if="selectedTicket.ai_evidence.assistant_message_id"
            type="primary"
            plain
            @click="openSupervision"
            >查看执行监管</el-button
          >
        </section>

        <section class="process-card">
          <div class="process-card__head">
            <div>
              <strong>回复用户</strong>
              <p>回复内容会在用户的“我的反馈”详情中展示。</p>
            </div>
          </div>
          <el-input
            v-model="replyContent"
            type="textarea"
            :rows="5"
            placeholder="说明处理结果、临时方案或需要用户补充的信息"
          />
          <div class="reply-actions">
            <el-button type="primary" :loading="saving" @click="sendReply"
              >发送回复</el-button
            >
          </div>
        </section>

        <section class="context-card">
          <strong>提交环境</strong>
          <pre>{{ formattedContext }}</pre>
        </section>
      </div>
    </el-drawer>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import api from "@/utils/api.js";
import { formatDateTime } from "@/utils/date.js";
import {
  FEEDBACK_CATEGORIES,
  FEEDBACK_PRIORITIES,
  FEEDBACK_STATUSES,
  feedbackCategoryLabel,
  feedbackStatusMeta,
} from "@/utils/user-feedback.js";

const router = useRouter();
const loading = ref(false);
const saving = ref(false);
const tickets = ref([]);
const summary = ref({ total: 0, by_status: {}, by_category: {} });
const selectedTicket = ref(null);
const detailVisible = ref(false);
const replyContent = ref("");
const filters = reactive({
  keyword: "",
  status: "",
  category: "",
  priority: "",
});
const processForm = reactive({
  assignee_id: "",
  priority: "normal",
  status: "submitted",
});
const hasAiEvidence = computed(() =>
  Boolean(
    selectedTicket.value?.ai_evidence &&
    Object.keys(selectedTicket.value.ai_evidence).length,
  ),
);
const formattedContext = computed(() =>
  JSON.stringify(selectedTicket.value?.context || {}, null, 2),
);

function priorityLabel(value) {
  return (
    FEEDBACK_PRIORITIES.find((item) => item.value === value)?.label ||
    value ||
    "普通"
  );
}

async function loadTickets() {
  loading.value = true;
  try {
    const data = await api.get("/admin/user-feedback", { params: filters });
    tickets.value = Array.isArray(data.items) ? data.items : [];
  } catch (error) {
    tickets.value = [];
    ElMessage.error(error?.detail || error?.message || "加载反馈工单失败");
  } finally {
    loading.value = false;
  }
}

async function loadSummary() {
  const data = await api.get("/admin/user-feedback/summary");
  summary.value = data.summary || { total: 0, by_status: {}, by_category: {} };
}

async function refresh() {
  await Promise.all([loadTickets(), loadSummary()]);
}

function resetFilters() {
  Object.assign(filters, {
    keyword: "",
    status: "",
    category: "",
    priority: "",
  });
  loadTickets();
}

async function openDetail(row) {
  try {
    const data = await api.get(
      `/admin/user-feedback/${encodeURIComponent(row.id)}`,
    );
    selectedTicket.value = data.item;
    processForm.assignee_id = String(data.item.assignee_id || "");
    processForm.priority = String(data.item.priority || "normal");
    processForm.status = String(data.item.status || "submitted");
    replyContent.value = String(data.item.public_reply || "");
    detailVisible.value = true;
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "加载反馈详情失败");
  }
}

async function saveAssignment() {
  saving.value = true;
  try {
    const data = await api.post(
      `/admin/user-feedback/${encodeURIComponent(selectedTicket.value.id)}/assign`,
      { assignee_id: processForm.assignee_id },
    );
    selectedTicket.value = data.item;
    ElMessage.success("负责人已更新");
    await refresh();
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "更新负责人失败");
  } finally {
    saving.value = false;
  }
}

async function saveTransition() {
  saving.value = true;
  try {
    const data = await api.post(
      `/admin/user-feedback/${encodeURIComponent(selectedTicket.value.id)}/transition`,
      { status: processForm.status, priority: processForm.priority },
    );
    selectedTicket.value = data.item;
    ElMessage.success("工单状态已更新");
    await refresh();
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "更新工单状态失败");
  } finally {
    saving.value = false;
  }
}

async function sendReply() {
  saving.value = true;
  try {
    const data = await api.post(
      `/admin/user-feedback/${encodeURIComponent(selectedTicket.value.id)}/reply`,
      { content: replyContent.value },
    );
    selectedTicket.value = data.item;
    ElMessage.success("回复已发送");
    await refresh();
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "发送回复失败");
  } finally {
    saving.value = false;
  }
}

function openSupervision() {
  router.push({
    path: "/ai/supervision",
    query: { answer_id: selectedTicket.value.ai_evidence.assistant_message_id },
  });
}

onMounted(refresh);
</script>

<style scoped>
.admin-feedback-page {
  min-height: 100%;
  padding: 26px;
  background: #f3f6fb;
  color: #0f172a;
}
.admin-hero,
.admin-panel,
.summary-card {
  border: 1px solid rgba(255, 255, 255, 0.9);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.07);
}
.admin-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 26px 28px;
}
.admin-hero h1 {
  margin: 6px 0 10px;
  font-size: 30px;
}
.admin-hero p {
  margin: 0;
  color: #64748b;
  line-height: 1.7;
}
.admin-eyebrow {
  color: #4f46e5;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.16em;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin: 18px 0;
}
.summary-card {
  display: grid;
  gap: 10px;
  padding: 20px;
}
.summary-card span {
  color: #64748b;
}
.summary-card strong {
  font-size: 30px;
}
.summary-card--blue {
  background: linear-gradient(145deg, #eff6ff, #fff);
}
.summary-card--amber {
  background: linear-gradient(145deg, #fffbeb, #fff);
}
.summary-card--green {
  background: linear-gradient(145deg, #ecfdf5, #fff);
}
.admin-panel {
  padding: 20px;
  margin-top: 16px;
}
.filter-grid {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) repeat(
      3,
      minmax(150px, 1fr)
    ) auto auto;
  gap: 10px;
}
.table-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 16px;
}
.table-panel__head h2 {
  margin: 5px 0 0;
}
.table-panel__head > span {
  color: #64748b;
}
.title-cell {
  display: grid;
  gap: 5px;
  cursor: pointer;
}
.title-cell span {
  color: #64748b;
  font-size: 13px;
}
.detail-layout {
  display: grid;
  gap: 20px;
}
.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}
.detail-header span,
.detail-header p {
  color: #64748b;
}
.detail-header h2 {
  margin: 6px 0;
}
.process-card,
.evidence-card,
.context-card {
  padding: 20px;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  background: #fff;
}
.process-card__head p {
  margin: 6px 0 16px;
  color: #64748b;
}
.process-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 14px;
}
.process-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}
.evidence-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0;
}
.evidence-grid > div {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 14px;
  background: #f8fafc;
}
.evidence-grid span {
  color: #64748b;
  font-size: 12px;
}
.evidence-grid strong {
  word-break: break-all;
}
.reply-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.context-card pre {
  overflow: auto;
  max-height: 300px;
  padding: 14px;
  border-radius: 14px;
  background: #0f172a;
  color: #dbeafe;
  font-size: 12px;
}
@media (max-width: 1100px) {
  .filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 680px) {
  .admin-feedback-page {
    padding: 14px;
  }
  .admin-hero,
  .detail-header {
    flex-direction: column;
  }
  .summary-grid,
  .filter-grid,
  .process-grid,
  .evidence-grid {
    grid-template-columns: 1fr;
  }
}
</style>
