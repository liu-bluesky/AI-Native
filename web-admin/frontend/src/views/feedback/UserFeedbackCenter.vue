<template>
  <main class="feedback-page">
    <section class="feedback-hero">
      <div>
        <div class="feedback-eyebrow">USER FEEDBACK</div>
        <h1>用户反馈中心</h1>
        <p>产品体验、系统 Bug、AI 回答与执行问题都可以在这里提交并持续跟进。</p>
      </div>
      <div class="feedback-hero__actions">
        <el-button @click="activateMine">我的反馈</el-button>
        <el-button type="primary" @click="activateCreate">提交反馈</el-button>
      </div>
    </section>

    <el-tabs
      v-model="activeTab"
      class="feedback-tabs"
      @tab-change="handleTabChange"
    >
      <el-tab-pane label="提交反馈" name="create">
        <section class="feedback-panel feedback-form-panel">
          <div class="section-heading">
            <div>
              <span>01</span>
              <div>
                <h2>选择反馈类型</h2>
                <p>选择最接近的问题类型，系统会展示对应字段。</p>
              </div>
            </div>
          </div>

          <div class="category-grid">
            <button
              v-for="category in FEEDBACK_CATEGORIES"
              :key="category.value"
              type="button"
              class="category-card"
              :class="{ 'is-active': form.category === category.value }"
              @click="form.category = category.value"
            >
              <span class="category-card__icon">{{ category.icon }}</span>
              <strong>{{ category.label }}</strong>
              <small>{{ category.short }}</small>
            </button>
          </div>

          <div class="section-heading section-heading--form">
            <div>
              <span>02</span>
              <div>
                <h2>描述你的反馈</h2>
                <p>请提供可复现的信息，不要粘贴密码、密钥或其他敏感数据。</p>
              </div>
            </div>
          </div>

          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            label-position="top"
            class="feedback-form"
          >
            <div class="feedback-form__grid">
              <el-form-item label="反馈标题" prop="title" class="span-2">
                <el-input
                  v-model="form.title"
                  maxlength="180"
                  show-word-limit
                  placeholder="一句话概括问题"
                />
              </el-form-item>
              <el-form-item label="发生频率">
                <el-select v-model="form.frequency">
                  <el-option label="总是发生" value="always" />
                  <el-option label="经常发生" value="often" />
                  <el-option label="偶尔发生" value="sometimes" />
                  <el-option label="只发生一次" value="once" />
                  <el-option label="不确定" value="unknown" />
                </el-select>
              </el-form-item>
              <el-form-item label="影响程度">
                <el-select v-model="form.impact_level">
                  <el-option label="轻微影响" value="minor" />
                  <el-option label="一般影响" value="general" />
                  <el-option label="严重影响" value="major" />
                  <el-option label="完全无法使用" value="blocked" />
                </el-select>
              </el-form-item>
              <el-form-item label="详细描述" prop="description" class="span-2">
                <el-input
                  v-model="form.description"
                  type="textarea"
                  :rows="6"
                  maxlength="12000"
                  show-word-limit
                  placeholder="发生了什么？你做了哪些操作？实际结果是什么？"
                />
              </el-form-item>
              <el-form-item label="期望结果" class="span-2">
                <el-input
                  v-model="form.expected_result"
                  type="textarea"
                  :rows="3"
                  placeholder="你希望系统如何表现或改进？"
                />
              </el-form-item>
            </div>

            <section v-if="isAiFeedback" class="ai-evidence-card">
              <div class="ai-evidence-card__head">
                <div>
                  <strong>关联 AI 证据</strong>
                  <p>
                    可选。关联后处理人员可以按回答 ID 查看对应执行监管信息。
                  </p>
                </div>
                <el-tag type="info" effect="plain">仅 AI 类反馈</el-tag>
              </div>
              <div class="feedback-form__grid">
                <el-form-item label="回答 ID">
                  <el-input
                    v-model="form.assistant_message_id"
                    placeholder="assistant_message_id"
                  />
                </el-form-item>
                <el-form-item label="执行 ID">
                  <el-input
                    v-model="form.execution_id"
                    placeholder="execution_id / run_id"
                  />
                </el-form-item>
                <el-form-item label="聊天会话 ID" class="span-2">
                  <el-input
                    v-model="form.chat_session_id"
                    placeholder="chat_session_id"
                  />
                </el-form-item>
              </div>
            </section>

            <section class="diagnostic-card">
              <div>
                <strong>诊断信息授权</strong>
                <p>
                  基础页面、设备和窗口信息会帮助定位问题；不会自动采集密码、密钥和输入框内容。
                </p>
              </div>
              <el-checkbox v-model="form.basic_context"
                >附带基础环境信息</el-checkbox
              >
            </section>

            <div class="submit-bar">
              <span>提交后可在“我的反馈”中查看处理状态与回复。</span>
              <el-button
                type="primary"
                size="large"
                :loading="submitting"
                @click="submitFeedback"
              >
                提交反馈
              </el-button>
            </div>
          </el-form>
        </section>
      </el-tab-pane>

      <el-tab-pane label="我的反馈" name="mine">
        <section class="feedback-panel">
          <div class="list-toolbar">
            <div>
              <div class="feedback-eyebrow">MY TICKETS</div>
              <h2>我的反馈</h2>
            </div>
            <div class="list-toolbar__filters">
              <el-select
                v-model="filters.status"
                clearable
                placeholder="全部状态"
                @change="loadMine"
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
                @change="loadMine"
              >
                <el-option
                  v-for="item in FEEDBACK_CATEGORIES"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
              <el-button :loading="loadingMine" @click="loadMine"
                >刷新</el-button
              >
            </div>
          </div>

          <el-table
            v-loading="loadingMine"
            :data="tickets"
            stripe
            @row-click="openDetail"
          >
            <el-table-column prop="id" label="反馈编号" width="165" />
            <el-table-column label="反馈内容" min-width="300">
              <template #default="{ row }">
                <div class="ticket-title-cell">
                  <strong>{{ row.title }}</strong>
                  <span>{{ feedbackCategoryLabel(row.category) }}</span>
                </div>
              </template>
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
            v-if="!loadingMine && !tickets.length"
            description="还没有提交过反馈"
          />
        </section>
      </el-tab-pane>
    </el-tabs>

    <el-drawer
      v-model="detailVisible"
      size="min(1260px, 92vw)"
      title="反馈详情"
    >
      <div v-if="selectedTicket" class="ticket-detail">
        <div class="ticket-detail__head">
          <div>
            <span>{{ selectedTicket.id }}</span>
            <h2>{{ selectedTicket.title }}</h2>
          </div>
          <el-tag :type="feedbackStatusMeta(selectedTicket.status).type">
            {{ feedbackStatusMeta(selectedTicket.status).label }}
          </el-tag>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="类型">{{
            feedbackCategoryLabel(selectedTicket.category)
          }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{
            formatDateTime(selectedTicket.created_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="详细描述" :span="2">{{
            selectedTicket.description
          }}</el-descriptions-item>
          <el-descriptions-item label="期望结果" :span="2">{{
            selectedTicket.expected_result || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="处理回复" :span="2">{{
            selectedTicket.public_reply || "暂未回复"
          }}</el-descriptions-item>
        </el-descriptions>
        <div
          v-if="
            selectedTicket.ai_evidence &&
            Object.keys(selectedTicket.ai_evidence).length
          "
          class="detail-card"
        >
          <strong>AI 关联证据</strong>
          <p>
            回答 ID：
            <el-button
              v-if="selectedTicket.ai_evidence.assistant_message_id"
              link
              type="primary"
              @click="
                openSupervision(selectedTicket.ai_evidence.assistant_message_id)
              "
              >{{ selectedTicket.ai_evidence.assistant_message_id }}</el-button
            >
            <span v-else>-</span>
          </p>
          <p>执行 ID：{{ selectedTicket.ai_evidence.execution_id || "-" }}</p>
        </div>
        <div class="detail-actions">
          <el-button
            v-if="['resolved', 'closed'].includes(selectedTicket.status)"
            type="primary"
            @click="reopenTicket"
            >重新打开</el-button
          >
          <el-button
            v-if="
              !['resolved', 'closed', 'withdrawn'].includes(
                selectedTicket.status,
              )
            "
            @click="withdrawTicket"
            >撤回反馈</el-button
          >
        </div>
      </div>
    </el-drawer>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import api from "@/utils/api.js";
import { formatDateTime } from "@/utils/date.js";
import {
  FEEDBACK_CATEGORIES,
  FEEDBACK_STATUSES,
  collectFeedbackContext,
  createIdempotencyKey,
  feedbackCategoryLabel,
  feedbackStatusMeta,
} from "@/utils/user-feedback.js";

const route = useRoute();
const router = useRouter();
const activeTab = ref(route.query.mode === "mine" ? "mine" : "create");
const formRef = ref();
const submitting = ref(false);
const loadingMine = ref(false);
const tickets = ref([]);
const selectedTicket = ref(null);
const detailVisible = ref(false);
const filters = reactive({ status: "", category: "" });
const form = reactive({
  category: "product_bug",
  title: "",
  description: "",
  expected_result: "",
  impact_level: "general",
  frequency: "unknown",
  assistant_message_id: String(route.query.answer_id || ""),
  execution_id: String(route.query.execution_id || ""),
  chat_session_id: String(route.query.chat_session_id || ""),
  basic_context: true,
});
const rules = {
  title: [{ required: true, message: "请填写反馈标题", trigger: "blur" }],
  description: [{ required: true, message: "请填写详细描述", trigger: "blur" }],
};
const isAiFeedback = computed(() =>
  ["ai_answer", "ai_execution"].includes(form.category),
);

function activateCreate() {
  activeTab.value = "create";
}

function activateMine() {
  activeTab.value = "mine";
  loadMine();
}

function handleTabChange(name) {
  router.replace({
    query: { ...route.query, mode: name === "mine" ? "mine" : "create" },
  });
  if (name === "mine") loadMine();
}

function resetForm() {
  form.title = "";
  form.description = "";
  form.expected_result = "";
  form.assistant_message_id = "";
  form.execution_id = "";
  form.chat_session_id = "";
}

async function submitFeedback() {
  await formRef.value?.validate();
  submitting.value = true;
  try {
    const aiEvidence = isAiFeedback.value
      ? {
          assistant_message_id: form.assistant_message_id,
          execution_id: form.execution_id,
          chat_session_id: form.chat_session_id,
        }
      : {};
    const data = await api.post(
      "/user-feedback",
      {
        category: form.category,
        title: form.title,
        description: form.description,
        expected_result: form.expected_result,
        impact_level: form.impact_level,
        frequency: form.frequency,
        source_entry: String(route.query.source || "global_menu"),
        project_id: localStorage.getItem("project_id") || "",
        context: form.basic_context ? collectFeedbackContext(route) : {},
        ai_evidence: aiEvidence,
        diagnostic_consent: {
          basic_context: form.basic_context,
          ai_context: isAiFeedback.value,
        },
      },
      { headers: { "Idempotency-Key": createIdempotencyKey() } },
    );
    ElMessage.success(`反馈已提交：${data.item.id}`);
    resetForm();
    activeTab.value = "mine";
    await loadMine();
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "提交反馈失败");
  } finally {
    submitting.value = false;
  }
}

async function loadMine() {
  loadingMine.value = true;
  try {
    const data = await api.get("/user-feedback/mine", { params: filters });
    tickets.value = Array.isArray(data.items) ? data.items : [];
  } catch (error) {
    tickets.value = [];
    ElMessage.error(error?.detail || error?.message || "加载我的反馈失败");
  } finally {
    loadingMine.value = false;
  }
}

async function openDetail(row) {
  try {
    const data = await api.get(`/user-feedback/${encodeURIComponent(row.id)}`);
    selectedTicket.value = data.item;
    detailVisible.value = true;
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "加载反馈详情失败");
  }
}

async function reopenTicket() {
  const data = await api.post(
    `/user-feedback/${encodeURIComponent(selectedTicket.value.id)}/reopen`,
  );
  selectedTicket.value = data.item;
  ElMessage.success("反馈已重新打开");
  await loadMine();
}

async function withdrawTicket() {
  await ElMessageBox.confirm(
    "撤回后处理人员将停止跟进，确定继续？",
    "撤回反馈",
    { type: "warning" },
  );
  const data = await api.post(
    `/user-feedback/${encodeURIComponent(selectedTicket.value.id)}/withdraw`,
  );
  selectedTicket.value = data.item;
  ElMessage.success("反馈已撤回");
  await loadMine();
}

function openSupervision(answerId) {
  router.push({ path: "/ai/supervision", query: { answer_id: answerId } });
}

watch(
  () => route.query.mode,
  (value) => {
    activeTab.value = value === "mine" ? "mine" : "create";
  },
);

onMounted(() => {
  if (activeTab.value === "mine") loadMine();
});
</script>

<style scoped>
.feedback-page {
  min-height: 100%;
  padding: 26px;
  background: linear-gradient(145deg, #f8fafc, #eef4ff);
  color: #0f172a;
}
.feedback-hero,
.feedback-panel {
  border: 1px solid rgba(255, 255, 255, 0.9);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 20px 55px rgba(30, 64, 175, 0.09);
  backdrop-filter: blur(18px);
}
.feedback-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 28px 30px;
}
.feedback-hero h1 {
  margin: 6px 0 10px;
  font-size: 32px;
}
.feedback-hero p {
  margin: 0;
  max-width: 650px;
  color: #64748b;
  line-height: 1.7;
}
.feedback-eyebrow {
  color: #2563eb;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
}
.feedback-hero__actions,
.list-toolbar__filters,
.detail-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.feedback-tabs {
  margin-top: 20px;
}
.feedback-panel {
  padding: 26px;
}
.section-heading > div {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.section-heading span {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 13px;
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 800;
}
.section-heading h2,
.list-toolbar h2 {
  margin: 0 0 6px;
  font-size: 22px;
}
.section-heading p {
  margin: 0;
  color: #64748b;
}
.section-heading--form {
  margin-top: 32px;
}
.category-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 20px;
}
.category-card {
  display: grid;
  gap: 8px;
  min-height: 150px;
  padding: 18px;
  text-align: left;
  border: 1px solid #dbe4f0;
  border-radius: 20px;
  background: #fff;
  color: #0f172a;
  cursor: pointer;
  transition: 0.2s ease;
}
.category-card:hover {
  transform: translateY(-2px);
  border-color: #93c5fd;
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.1);
}
.category-card.is-active {
  border-color: #2563eb;
  background: linear-gradient(145deg, #eff6ff, #fff);
  box-shadow: inset 0 0 0 1px #2563eb;
}
.category-card__icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: #e0e7ff;
  color: #3730a3;
  font-size: 12px;
  font-weight: 800;
}
.category-card small {
  color: #64748b;
  line-height: 1.5;
}
.feedback-form {
  margin-top: 22px;
}
.feedback-form__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}
.span-2 {
  grid-column: span 2;
}
.ai-evidence-card,
.diagnostic-card,
.detail-card {
  padding: 20px;
  border: 1px solid #dbeafe;
  border-radius: 20px;
  background: #f8fbff;
}
.ai-evidence-card__head,
.diagnostic-card,
.list-toolbar,
.ticket-detail__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}
.ai-evidence-card p,
.diagnostic-card p {
  margin: 6px 0 0;
  color: #64748b;
}
.diagnostic-card {
  margin-top: 18px;
  align-items: center;
}
.submit-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #e2e8f0;
  color: #64748b;
}
.list-toolbar {
  align-items: center;
  margin-bottom: 18px;
}
.list-toolbar__filters :deep(.el-select) {
  width: 160px;
}
.ticket-title-cell {
  display: grid;
  gap: 5px;
  cursor: pointer;
}
.ticket-title-cell span {
  color: #64748b;
  font-size: 13px;
}
.ticket-detail {
  display: grid;
  gap: 20px;
}
.ticket-detail__head span {
  color: #64748b;
  font-size: 13px;
}
.ticket-detail__head h2 {
  margin: 6px 0 0;
}
.detail-card p {
  margin: 8px 0 0;
  color: #475569;
}
@media (max-width: 980px) {
  .category-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 680px) {
  .feedback-page {
    padding: 14px;
  }
  .feedback-hero,
  .list-toolbar,
  .submit-bar,
  .diagnostic-card {
    flex-direction: column;
  }
  .category-grid,
  .feedback-form__grid {
    grid-template-columns: 1fr;
  }
  .span-2 {
    grid-column: span 1;
  }
  .feedback-hero__actions,
  .list-toolbar__filters {
    width: 100%;
  }
  .list-toolbar__filters :deep(.el-select) {
    width: 100%;
  }
}
</style>
