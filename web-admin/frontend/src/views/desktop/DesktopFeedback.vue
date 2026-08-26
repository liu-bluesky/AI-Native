<template>
  <section class="desktop-feedback" :class="{ 'is-embedded': embeddedMode }">
    <div class="desktop-feedback__ambient" aria-hidden="true" />

    <header class="desktop-feedback__hero">
      <h1>提交反馈</h1>
      <button
        type="button"
        class="desktop-feedback__refresh"
        :disabled="loading"
        @click="openHistory"
      >
        {{ loading ? "正在读取..." : "查看记录" }}
      </button>
    </header>

    <div class="desktop-feedback__content">
      <section class="desktop-feedback__card desktop-feedback__form-card">
        <div class="desktop-feedback__section-head">
          <div>
            <span>PRODUCT FEEDBACK</span>
            <h2>告诉我们，怎样做得更好。</h2>
          </div>
          <span class="desktop-feedback__category">产品建议</span>
        </div>

        <p class="desktop-feedback__intro">
          你的反馈会直接提交给产品团队，处理进度可以通过“刷新记录”查看。
        </p>

        <el-form
          :model="form"
          label-position="top"
          @submit.prevent="submitFeedback"
        >
          <el-form-item label="反馈主题" required>
            <el-input
              v-model.trim="form.title"
              maxlength="80"
              show-word-limit
              placeholder="用一句话概括你的建议或问题"
            />
          </el-form-item>
          <el-form-item label="详细说明" required>
            <el-input
              v-model.trim="form.content"
              type="textarea"
              :rows="6"
              maxlength="2000"
              show-word-limit
              placeholder="请描述使用场景、遇到的问题或改进建议，至少 10 个字。"
            />
          </el-form-item>
          <el-form-item label="联系方式">
            <el-input
              v-model.trim="form.contact"
              maxlength="100"
              placeholder="选填，便于我们进一步联系你"
            />
          </el-form-item>
          <el-button type="primary" native-type="submit" :loading="submitting">
            提交反馈
          </el-button>
        </el-form>
      </section>
    </div>

    <el-dialog
      v-model="historyVisible"
      title="我的反馈记录"
      width="min(680px, calc(100vw - 32px))"
    >
      <div v-if="loading" class="desktop-feedback__status">
        正在读取反馈记录...
      </div>
      <el-empty
        v-else-if="!feedbackItems.length"
        description="还没有提交过反馈"
        :image-size="76"
      />
      <div v-else class="desktop-feedback__list">
        <article
          v-for="item in feedbackItems"
          :key="item.id"
          class="desktop-feedback__item"
        >
          <div class="desktop-feedback__item-head">
            <div>
              <h3>{{ item.title }}</h3>
              <span
                >{{ item.category || "产品建议" }} ·
                {{ formatDate(item.created_at) }}</span
              >
            </div>
            <el-tag :type="statusType(item.status)">{{
              statusLabel(item.status)
            }}</el-tag>
          </div>
          <p>{{ item.content }}</p>
          <div v-if="item.reply" class="desktop-feedback__reply">
            <b>平台回复</b>
            <span>{{ item.reply }}</span>
            <small v-if="item.reviewed_at">{{
              formatDate(item.reviewed_at)
            }}</small>
          </div>
        </article>
      </div>
    </el-dialog>
  </section>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import api from "@/utils/api.js";
import {
  getStoredAuthProfile,
  isExternalAuthSession,
} from "@/utils/auth-storage.js";
import { DEFAULT_BACKEND_API_ORIGIN } from "@/utils/backend-endpoints.js";
import { isEmbeddedDesktopApp } from "@/utils/desktop-app-bridge.js";

const router = useRouter();
const embeddedMode =
  isEmbeddedDesktopApp() ||
  Boolean(router?.__aiEmployeeDesktopWindow?.windowId);
const loading = ref(false);
const submitting = ref(false);
const historyVisible = ref(false);
const feedbackItems = ref([]);
const form = reactive({
  title: "",
  content: "",
  contact: "",
});

function statusLabel(status) {
  if (status === "resolved") return "已处理";
  if (status === "rejected") return "已驳回";
  return "待处理";
}

function statusType(status) {
  if (status === "resolved") return "success";
  if (status === "rejected") return "danger";
  return "warning";
}

function formatDate(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

async function requestFeedback(method, payload) {
  if (!isExternalAuthSession()) {
    return method === "GET"
      ? api.get("/user/feedback")
      : api.post("/user/feedback", payload);
  }

  const username = String(getStoredAuthProfile()?.username || "").trim();
  if (!username) throw new Error("登录信息缺失，请重新登录");

  const response = await fetch(
    `${DEFAULT_BACKEND_API_ORIGIN}/api/user/feedback`,
    {
      method,
      headers: {
        Authorization: `Bearer ${encodeURIComponent(username)}`,
        ...(payload ? { "Content-Type": "application/json" } : {}),
      },
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    },
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "用户反馈请求失败");
  return data;
}

async function loadFeedback() {
  loading.value = true;
  try {
    const data = await requestFeedback("GET");
    feedbackItems.value = Array.isArray(data?.list) ? data.list : [];
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "读取反馈记录失败");
  } finally {
    loading.value = false;
  }
}

async function openHistory() {
  historyVisible.value = true;
  await loadFeedback();
}

async function submitFeedback() {
  if (!form.title) {
    ElMessage.warning("请填写反馈主题");
    return;
  }
  if (form.content.length < 10) {
    ElMessage.warning("详细说明至少需要 10 个字");
    return;
  }
  submitting.value = true;
  try {
    await requestFeedback("POST", {
      title: form.title,
      category: "产品建议",
      content: form.content,
      contact: form.contact,
    });
    form.title = "";
    form.content = "";
    form.contact = "";
    ElMessage.success("感谢你的反馈，我们会尽快处理");
    await loadFeedback();
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "提交反馈失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.desktop-feedback {
  position: relative;
  min-height: 100vh;
  padding: 34px;
  overflow-x: hidden;
  overflow-y: auto;
  box-sizing: border-box;
  background:
    radial-gradient(circle at 8% 0%, rgba(56, 189, 248, 0.2), transparent 24%),
    radial-gradient(
      circle at 92% 16%,
      rgba(168, 85, 247, 0.13),
      transparent 25%
    ),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 42%, #edf2f7 100%);
}

.desktop-feedback.is-embedded {
  height: 100vh;
}

.desktop-feedback__ambient {
  position: absolute;
  top: 12%;
  left: 50%;
  width: 34rem;
  height: 34rem;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.1);
  filter: blur(88px);
  pointer-events: none;
  transform: translateX(-50%);
}

.desktop-feedback__hero,
.desktop-feedback__content {
  position: relative;
}

.desktop-feedback__hero {
  display: flex;
  gap: 24px;
  align-items: end;
  justify-content: space-between;
  margin-bottom: 28px;
}

.desktop-feedback__eyebrow,
.desktop-feedback__section-head span {
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.desktop-feedback h1,
.desktop-feedback h2,
.desktop-feedback h3,
.desktop-feedback p {
  margin: 0;
}

.desktop-feedback h1 {
  margin: 0;
  color: #0f172a;
  font-size: clamp(28px, 4vw, 44px);
  line-height: 1.15;
  letter-spacing: -0.06em;
}

.desktop-feedback__intro {
  margin: -4px 0 22px;
  color: #475569;
  line-height: 1.75;
}

.desktop-feedback__refresh {
  flex: none;
  min-height: 36px;
  padding: 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.38);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: #334155;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
}

.desktop-feedback__refresh:disabled {
  cursor: wait;
  opacity: 0.62;
}

.desktop-feedback__content {
  display: grid;
  grid-template-columns: minmax(300px, 680px);
  align-items: start;
  justify-content: center;
}

.desktop-feedback__card {
  padding: 22px;
  border: 1px solid rgba(255, 255, 255, 0.88);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.7);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.07);
  backdrop-filter: blur(20px);
}

.desktop-feedback__section-head,
.desktop-feedback__item-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.desktop-feedback__section-head {
  margin-bottom: 20px;
}

.desktop-feedback__section-head h2 {
  margin-top: 6px;
  color: #0f172a;
  font-size: 20px;
}

.desktop-feedback__section-head strong {
  color: #0f766e;
  font-size: 24px;
}

.desktop-feedback__category {
  padding: 6px 9px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.12);
  color: #0369a1 !important;
  letter-spacing: 0 !important;
}

.desktop-feedback__status {
  padding: 48px 0;
  color: #64748b;
  text-align: center;
}

.desktop-feedback__list {
  display: grid;
  gap: 12px;
}

.desktop-feedback__item {
  padding: 16px;
  border: 1px solid rgba(203, 213, 225, 0.72);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.66);
}

.desktop-feedback__item h3 {
  color: #1e293b;
  font-size: 15px;
}

.desktop-feedback__item-head span,
.desktop-feedback__item small {
  display: block;
  margin-top: 5px;
  color: #94a3b8;
  font-size: 12px;
}

.desktop-feedback__item > p {
  margin-top: 12px;
  color: #475569;
  line-height: 1.7;
  white-space: pre-wrap;
}

.desktop-feedback__reply {
  display: grid;
  gap: 6px;
  margin-top: 14px;
  padding: 12px;
  border-radius: 12px;
  background: #eff6ff;
  color: #1e40af;
  font-size: 13px;
}

.desktop-feedback__reply span {
  line-height: 1.7;
  white-space: pre-wrap;
}

@media (max-width: 880px) {
  .desktop-feedback {
    padding: 24px;
  }

  .desktop-feedback__hero,
  .desktop-feedback__content {
    grid-template-columns: 1fr;
  }

  .desktop-feedback__hero {
    align-items: start;
    flex-direction: column;
  }
}
</style>
