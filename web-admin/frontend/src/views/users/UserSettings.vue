<template>
  <div class="user-settings-page" v-loading="loading">
    <header class="settings-context">
      <div class="settings-context__main">
        <div class="settings-context__title">用户设置</div>
        <div class="settings-context__meta">
          <span>{{ form.username || "-" }}</span>
          <span>{{ roleLabel }}</span>
          <span>{{ selectedProvider ? `默认 AI：${selectedProvider.name}` : "默认 AI：未指定" }}</span>
        </div>
      </div>
      <div class="settings-context__actions">
        <el-button @click="fetchSettings">刷新</el-button>
        <el-button type="primary" :loading="saving" @click="saveSettings">
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
          <div>
            <h3>默认 AI</h3>
            <p>这里决定当前账号优先使用哪一个模型供应商。</p>
          </div>
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
  const raw = String(form.created_at || "").trim();
  if (!raw) return "-";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
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
  padding: 14px 16px 16px;
  background:
    radial-gradient(circle at top left, rgba(255, 244, 214, 0.5), transparent 24%),
    linear-gradient(180deg, #f6f3ee 0%, #f7f7f8 32%, #f5f5f6 100%);
}

.settings-context {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 18px;
  padding: 2px 4px 0;
}

.settings-context__main {
  min-width: 0;
}

.settings-context__title {
  margin: 0;
  font-size: 24px;
  line-height: 1.2;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.88);
}

.settings-context__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.settings-context__meta span {
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  color: rgba(0, 0, 0, 0.65);
}

.settings-context__actions {
  display: flex;
  gap: 8px;
}

.settings-layout {
  display: grid;
  grid-template-columns: 272px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.account-rail,
.settings-panel {
  border-radius: 24px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(10px);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.account-rail {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.account-rail__head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.account-rail__avatar {
  width: 56px;
  height: 56px;
  border-radius: 18px;
  background: linear-gradient(135deg, #1f2937, #4b5563);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 700;
}

.account-rail__summary {
  min-width: 0;
}

.account-rail__name {
  font-size: 16px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.88);
}

.account-rail__hint {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

.account-rail__facts {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.account-fact {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.account-fact__label {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

.account-fact__value {
  font-size: 14px;
  color: rgba(0, 0, 0, 0.78);
  word-break: break-word;
}

.settings-panel {
  padding: 20px 22px;
}

.settings-panel__head {
  margin-bottom: 14px;
}

.settings-panel__head h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.88);
}

.settings-panel__head p {
  margin: 6px 0 0;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.45);
}

.settings-form {
  max-width: 720px;
}

.settings-select {
  width: min(720px, 100%);
}

.settings-empty {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(250, 204, 21, 0.1);
  color: rgba(0, 0, 0, 0.65);
  font-size: 13px;
  line-height: 1.6;
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
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}

.provider-preview {
  display: grid;
  gap: 10px;
  max-width: 720px;
  margin-top: 6px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(255, 255, 255, 0.5);
}

.provider-preview__row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 12px;
}

.provider-preview__label {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

.provider-preview__value {
  min-width: 0;
  color: rgba(0, 0, 0, 0.78);
  word-break: break-word;
}

.settings-note {
  max-width: 720px;
  margin-top: 14px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
  line-height: 1.6;
}

@media (max-width: 1120px) {
  .settings-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .user-settings-page {
    padding: 12px;
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
    border-radius: 20px;
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
