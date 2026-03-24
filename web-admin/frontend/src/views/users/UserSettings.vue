<template>
  <div class="user-settings-page" v-loading="loading">
    <header class="settings-context">
      <div class="settings-context__main">
        <div class="settings-context__eyebrow">Account Preferences</div>
        <div class="settings-context__title">用户设置</div>
        <p class="settings-context__summary">
          统一当前账号的默认模型来源，让设置中心里的对话入口和个人偏好保持一致。
        </p>
        <div class="settings-context__meta">
          <span>{{ form.username || "-" }}</span>
          <span>{{ roleLabel }}</span>
          <span>{{
            selectedProvider ? `默认 AI：${selectedProvider.name}` : "默认 AI：未指定"
          }}</span>
        </div>
      </div>
      <div class="settings-context__actions">
        <el-button class="settings-context__button" @click="fetchSettings">
          刷新
        </el-button>
        <el-button
          class="settings-context__button settings-context__button--primary"
          :loading="saving"
          @click="saveSettings"
        >
          保存设置
        </el-button>
      </div>
    </header>

    <section class="settings-layout">
      <aside class="account-rail">
        <div class="account-rail__head">
          <div class="account-rail__avatar">{{ usernameInitial }}</div>
          <div class="account-rail__summary">
            <div class="account-rail__name">{{ form.username || "-" }}</div>
            <div class="account-rail__hint">当前登录账号</div>
          </div>
        </div>
        <div class="account-rail__facts">
          <div class="account-fact">
            <span class="account-fact__label">角色</span>
            <span class="account-fact__value">{{ roleLabel }}</span>
          </div>
          <div class="account-fact">
            <span class="account-fact__label">创建时间</span>
            <span class="account-fact__value">{{ createdAtText }}</span>
          </div>
          <div class="account-fact">
            <span class="account-fact__label">可选模型源</span>
            <span class="account-fact__value">{{ providerOptions.length }}</span>
          </div>
        </div>
      </aside>

      <article class="settings-panel">
        <div class="settings-panel__head">
          <div class="settings-panel__eyebrow">Default AI</div>
          <h3>默认模型供应商</h3>
          <p>这里决定当前账号优先使用哪一个模型供应商。</p>
        </div>

        <div v-if="!providerOptions.length" class="settings-empty">
          当前没有可用的已启用模型供应商，请先创建供应商或让其他用户共享给你。
        </div>

        <el-form v-else label-position="top" class="settings-form">
          <el-form-item label="默认模型供应商">
            <el-select
              v-model="form.default_ai_provider_id"
              filterable
              clearable
              placeholder="未设置时自动回退到可见列表的第一个供应商"
              class="settings-select"
            >
              <el-option
                v-for="item in providerOptions"
                :key="item.id"
                :label="item.label"
                :value="item.id"
              >
                <div class="provider-option">
                  <span class="provider-option__name">{{ item.name }}</span>
                  <span class="provider-option__meta">
                    {{ item.defaultModel || "-" }} ·
                    {{ item.ownerUsername || "当前用户" }}
                  </span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>
        </el-form>

        <div v-if="selectedProvider" class="provider-preview">
          <div class="provider-preview__head">
            <div class="provider-preview__title">当前已选择</div>
            <div class="provider-preview__badge">已生效</div>
          </div>
          <div class="provider-preview__row">
            <span class="provider-preview__label">当前选择</span>
            <span class="provider-preview__value">{{ selectedProvider.name }}</span>
          </div>
          <div class="provider-preview__row">
            <span class="provider-preview__label">默认模型</span>
            <span class="provider-preview__value">{{ selectedProvider.defaultModel || "-" }}</span>
          </div>
          <div class="provider-preview__row">
            <span class="provider-preview__label">创建人</span>
            <span class="provider-preview__value">{{ selectedProvider.ownerUsername || "当前用户" }}</span>
          </div>
        </div>

        <div class="settings-note">
          仅可选择你当前有权限使用且已启用的模型供应商；这些供应商可以是你自己创建的，也可以是他人共享给你的。
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "@/utils/api.js";
import { formatDateTime } from "@/utils/date.js";

const loading = ref(false);
const saving = ref(false);
const providers = ref([]);
const form = reactive({
  username: "",
  role: "",
  created_at: "",
  default_ai_provider_id: "",
});

const usernameInitial = computed(
  () =>
    String(form.username || "?")
      .trim()
      .slice(0, 1)
      .toUpperCase() || "?",
);

const roleLabel = computed(() => {
  const role = String(form.role || "").trim();
  if (!role) return "-";
  if (role === "admin") return "管理员";
  if (role === "user") return "普通用户";
  return role;
});

const createdAtText = computed(() => {
  return formatDateTime(form.created_at);
});

const providerOptions = computed(() =>
  (Array.isArray(providers.value) ? providers.value : [])
    .map((item) => {
      const id = String(item?.id || "").trim();
      const name = String(item?.name || id || "未命名供应商").trim();
      const defaultModel = String(item?.default_model || "").trim();
      const ownerUsername = String(item?.owner_username || "").trim();
      return {
        id,
        name,
        defaultModel,
        ownerUsername,
        label: ownerUsername ? `${name} (${ownerUsername})` : name,
      };
    })
    .filter((item) => item.id),
);

const selectedProvider = computed(() =>
  providerOptions.value.find(
    (item) => item.id === String(form.default_ai_provider_id || "").trim(),
  ) || null,
);

async function fetchSettings() {
  loading.value = true;
  try {
    const data = await api.get("/users/me/settings");
    const settings = data?.settings || {};
    form.username = String(settings.username || "");
    form.role = String(settings.role || "");
    form.created_at = String(settings.created_at || "");
    form.default_ai_provider_id = String(settings.default_ai_provider_id || "");
    providers.value = Array.isArray(data?.providers) ? data.providers : [];
  } catch (err) {
    providers.value = [];
    ElMessage.error(err?.detail || err?.message || "加载用户设置失败");
  } finally {
    loading.value = false;
  }
}

async function saveSettings() {
  saving.value = true;
  try {
    const data = await api.put("/users/me/settings", {
      default_ai_provider_id: String(form.default_ai_provider_id || "").trim(),
    });
    const settings = data?.settings || {};
    form.default_ai_provider_id = String(settings.default_ai_provider_id || "");
    ElMessage.success("用户设置已保存");
    await fetchSettings();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存用户设置失败");
  } finally {
    saving.value = false;
  }
}

onMounted(fetchSettings);
</script>

<style scoped>
.user-settings-page {
  min-height: 100%;
  padding: 4px 0 0;
  background: transparent;
}

.settings-context {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 18px;
  padding: 18px 20px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 28px;
  background:
    radial-gradient(circle at top right, rgba(103, 232, 249, 0.12), transparent 34%),
    radial-gradient(circle at top left, rgba(125, 211, 252, 0.12), transparent 26%),
    rgba(255, 255, 255, 0.54);
  box-shadow:
    0 24px 64px rgba(15, 23, 42, 0.08),
    0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.settings-context__main {
  min-width: 0;
  flex: 1;
}

.settings-context__eyebrow {
  color: #7c8aa0;
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.settings-context__title {
  margin: 0;
  margin-top: 10px;
  color: #0f172a;
  font-size: clamp(28px, 3.6vw, 36px);
  line-height: 1.04;
  font-weight: 600;
  letter-spacing: -0.03em;
  font-family: "Avenir Next", "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.settings-context__summary {
  max-width: 560px;
  margin: 10px 0 0;
  color: #475569;
  font-size: 14px;
  line-height: 1.7;
}

.settings-context__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.settings-context__meta span {
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.68);
  font-size: 12px;
  color: #64748b;
}

.settings-context__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  flex-shrink: 0;
  align-self: center;
}

.settings-context__button {
  min-height: 36px;
  padding: 0 14px !important;
  border-radius: 999px !important;
  border-color: rgba(15, 23, 42, 0.08) !important;
  background: rgba(255, 255, 255, 0.72) !important;
  color: #374151 !important;
  font-weight: 600;
  box-shadow: none !important;
}

.settings-context__button:hover {
  border-color: rgba(56, 189, 248, 0.24) !important;
  background: rgba(255, 255, 255, 0.9) !important;
  color: #0f172a !important;
}

.settings-context__button--primary {
  border-color: transparent !important;
  background: linear-gradient(180deg, #0f172a, #1e293b) !important;
  color: #fff !important;
  box-shadow: 0 18px 28px rgba(15, 23, 42, 0.14) !important;
}

.settings-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.account-rail,
.settings-panel {
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.76);
  background: rgba(255, 255, 255, 0.58);
  backdrop-filter: blur(20px);
  box-shadow:
    0 24px 64px rgba(15, 23, 42, 0.08),
    0 14px 34px rgba(15, 23, 42, 0.06);
}

.account-rail {
  padding: 22px 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.account-rail__head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.account-rail__avatar {
  width: 56px;
  height: 56px;
  border-radius: 20px;
  background: linear-gradient(180deg, #0f172a, #1e293b);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 700;
  box-shadow: 0 16px 28px rgba(15, 23, 42, 0.16);
}

.account-rail__summary {
  min-width: 0;
}

.account-rail__name {
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}

.account-rail__hint {
  margin-top: 4px;
  font-size: 12px;
  color: #7c8aa0;
}

.account-rail__facts {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.account-fact {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 0;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.account-fact__label {
  font-size: 12px;
  color: #7c8aa0;
}

.account-fact__value {
  font-size: 14px;
  color: #0f172a;
  text-align: right;
  word-break: break-word;
}

.settings-panel {
  padding: 24px 24px 22px;
}

.settings-panel__head {
  margin-bottom: 18px;
}

.settings-panel__eyebrow {
  color: #7c8aa0;
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.settings-panel__head h3 {
  margin: 10px 0 0;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: #0f172a;
}

.settings-panel__head p {
  max-width: 560px;
  margin: 8px 0 0;
  font-size: 14px;
  color: #475569;
  line-height: 1.7;
}

.settings-form {
  max-width: 720px;
}

.settings-form :deep(.el-form-item__label) {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
}

.settings-select {
  width: min(720px, 100%);
}

.settings-select :deep(.el-select__wrapper) {
  min-height: 46px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.06);
}

.settings-select :deep(.el-select__wrapper.is-focused) {
  box-shadow:
    inset 0 0 0 1px rgba(56, 189, 248, 0.22),
    0 0 0 4px rgba(103, 232, 249, 0.12);
}

.settings-empty {
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid rgba(245, 158, 11, 0.16);
  background: rgba(255, 251, 235, 0.82);
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.provider-option {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.provider-option__name {
  color: #0f172a;
}

.provider-option__meta {
  color: #7c8aa0;
  font-size: 12px;
}

.provider-preview {
  display: grid;
  gap: 12px;
  max-width: 720px;
  margin-top: 12px;
  padding: 18px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  background:
    radial-gradient(circle at top right, rgba(103, 232, 249, 0.1), transparent 42%),
    rgba(255, 255, 255, 0.72);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.84);
}

.provider-preview__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.provider-preview__title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

.provider-preview__badge {
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.78);
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.provider-preview__row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 12px;
}

.provider-preview__label {
  font-size: 12px;
  color: #7c8aa0;
}

.provider-preview__value {
  min-width: 0;
  color: #0f172a;
  word-break: break-word;
}

.settings-note {
  max-width: 720px;
  margin-top: 16px;
  font-size: 12px;
  color: #7c8aa0;
  line-height: 1.7;
}

@media (max-width: 1120px) {
  .settings-context {
    flex-direction: column;
    align-items: stretch;
  }

  .settings-context__actions {
    align-self: flex-start;
  }

  .settings-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .user-settings-page {
    padding-top: 0;
  }

  .settings-context,
  .account-rail__head,
  .settings-context__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .settings-panel,
  .account-rail {
    padding: 16px;
    border-radius: 24px;
  }

  .settings-context {
    padding: 16px;
    margin-bottom: 14px;
  }

  .settings-context__title {
    font-size: 30px;
  }

  .account-fact {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .account-fact__value {
    text-align: left;
  }

  .provider-preview__row {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .settings-context__actions {
    align-items: stretch;
  }
}
</style>
