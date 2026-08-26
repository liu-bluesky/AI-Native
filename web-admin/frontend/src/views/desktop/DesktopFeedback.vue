<template>
  <section class="desktop-feedback" :class="{ 'is-embedded': embeddedMode }">
    <div class="desktop-feedback__ambient" aria-hidden="true" />

    <header class="desktop-feedback__hero">
      <div>
        <div class="desktop-feedback__eyebrow">Product Feedback</div>
        <h1>告诉我们，怎样做得更好。</h1>
        <p>你的反馈会直接提交给产品团队。反馈类型默认是“产品建议”，处理进度会同步显示在这里。</p>
      </div>
      <button type="button" class="desktop-feedback__refresh" :disabled="loading" @click="loadFeedback">
        {{ loading ? "正在刷新..." : "刷新记录" }}
      </button>
    </header>

    <div class="desktop-feedback__content">
      <section class="desktop-feedback__card desktop-feedback__form-card">
        <div class="desktop-feedback__section-head">
          <div>
            <span>NEW FEEDBACK</span>
            <h2>提交反馈</h2>
          </div>
          <span class="desktop-feedback__category">产品建议</span>
        </div>

        <el-form :model="form" label-position="top" @submit.prevent="submitFeedback">
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

      <section class="desktop-feedback__card desktop-feedback__history-card">
        <div class="desktop-feedback__section-head">
          <div>
            <span>MY HISTORY</span>
            <h2>我的反馈记录</h2>
          </div>
          <strong>{{ feedbackItems.length }}</strong>
        </div>

        <div v-if="loading" class="desktop-feedback__status">正在读取反馈记录...</div>
        <el-empty
          v-else-if="!feedbackItems.length"
          description="还没有提交过反馈"
          :image-size="76"
        />
        <div v-else class="desktop-feedback__list">
          <article v-for="item in feedbackItems" :key="item.id" class="desktop-feedback__item">
            <div class="desktop-feedback__item-head">
              <div>
                <h3>{{ item.title }}</h3>
                <span>{{ item.category || "产品建议" }} · {{ formatDate(item.created_at) }}</span>
              </div>
              <el-tag :type="statusType(item.status)">{{ statusLabel(item.status) }}</el-tag>
            </div>
            <p>{{ item.content }}</p>
            <div v-if="item.reply" class="desktop-feedback__reply">
              <b>平台回复</b>
              <span>{{ item.reply }}</span>
              <small v-if="item.reviewed_at">{{ formatDate(item.reviewed_at) }}</small>
            </div>
          </article>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import api from "@/utils/api.js";
import { isEmbeddedDesktopApp } from "@/utils/desktop-app-bridge.js";

const router = useRouter();
const embeddedMode = isEmbeddedDesktopApp() || Boolean(router?.__aiEmployeeDesktopWindow?.windowId);
const loading = ref(false);
const submitting = ref(false);
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

async function loadFeedback() {
  loading.value = true;
  try {
    const data = await api.get("/user/feedback");
    feedbackItems.value = Array.isArray(data?.list) ? data.list : [];
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "读取反馈记录失败");
  } finally {
    loading.value = false;
  }
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
    await api.post("/user/feedback", {
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

onMounted(() => {
  void loadFeedback();
});
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
    radial-gradient(circle at 92% 16%, rgba(168, 85, 247, 0.13), transparent 25%),
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
  max-width: 12ch;
  margin-top: 10px;
  color: #0f172a;
  font-size: clamp(40px, 6.5vw, 72px);
  line-height: 0.98;
  letter-spacing: -0.06em;
}

.desktop-feedback__hero p {
  max-width: 60ch;
  margin-top: 16px;
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
  grid-template-columns: minmax(300px, 0.9fr) minmax(360px, 1.1fr);
  gap: 16px;
  align-items: start;
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
