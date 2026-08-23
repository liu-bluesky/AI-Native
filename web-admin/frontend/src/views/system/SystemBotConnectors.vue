<template>
  <div class="bot-connectors-page" v-loading="loading">
    <section class="page-header">
      <div class="page-header__copy">
        <p class="page-header__eyebrow">Robot Connectors</p>
        <div class="page-header__title-row">
          <h2>第三方机器人接入</h2>
          <div class="page-header__stats">
            <span>{{ platformCount }} 个平台</span>
            <span>{{ configuredConnectorCount }} 个已配置</span>
            <span>{{ connectorConfigPath }}</span>
          </div>
        </div>
        <p class="page-header__desc">
          这里管理机器人凭证、连接配置和机器人可切换的项目工作区。配置保存到本机全局存储，项目选择不依赖桌面当前登录用户。
        </p>
      </div>
      <div class="page-header__actions">
        <el-button :loading="loading" @click="refreshPage">刷新</el-button>
      </div>
    </section>

    <section class="page-panel">
      <BotPlatformConnectorModule
        v-model="connectors"
        :saving="saving"
        :persist-connectors="saveConnectors"
        compact
      />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import BotPlatformConnectorModule from "@/components/system/BotPlatformConnectorModule.vue";
import {
  DEFAULT_BOT_CONNECTOR_CONFIG,
  globalBotConnectorConfigPathLabel,
  readGlobalBotConnectorConfigFile,
  writeGlobalBotConnectorConfigFile,
} from "@/modules/project-chat/services/projectChatStorage.js";

const SUPPORTED_PLATFORMS = ["qq", "feishu", "wechat"];

const loading = ref(false);
const saving = ref(false);
const connectors = ref([]);
const connectorConfigPath = ref(globalBotConnectorConfigPathLabel());

const platformCount = SUPPORTED_PLATFORMS.length;
const configuredConnectorCount = computed(() =>
  connectors.value.filter((item) => {
    const platform = String(item?.platform || "").trim().toLowerCase();
    return (
      SUPPORTED_PLATFORMS.includes(platform) &&
      item?.enabled !== false &&
      String(item?.app_id || "").trim() &&
      String(item?.app_secret || "").trim()
    );
  }).length,
);

async function fetchConfig() {
  const data = await readGlobalBotConnectorConfigFile();
  connectorConfigPath.value = String(data?.path || globalBotConnectorConfigPathLabel()).trim();
  connectors.value = Array.isArray(data?.config?.connectors)
    ? data.config.connectors
    : [];
}

async function refreshPage() {
  loading.value = true;
  try {
    await fetchConfig();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载机器人接入配置失败");
  } finally {
    loading.value = false;
  }
}

async function saveConnectors(nextItems) {
  saving.value = true;
  try {
    const items = Array.isArray(nextItems) ? nextItems : connectors.value;
    const data = await writeGlobalBotConnectorConfigFile({
      ...DEFAULT_BOT_CONNECTOR_CONFIG,
      connectors: items,
    });
    connectorConfigPath.value = String(data?.path || globalBotConnectorConfigPathLabel()).trim();
    connectors.value = Array.isArray(data?.config?.connectors)
      ? data.config.connectors
      : [];
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("local-bot-connectors-config-updated"));
      window.dispatchEvent(
        new CustomEvent("system-config-updated", {
          detail: {
            config: {
              bot_platform_connectors: connectors.value,
            },
          },
        }),
      );
    }
    ElMessage.success(`机器人接入配置已保存：${connectorConfigPath.value}`);
    return connectors.value;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存机器人接入配置失败");
    throw err;
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void refreshPage();
});
</script>

<style scoped>
.bot-connectors-page {
  min-height: 100%;
  padding: 20px;
  display: grid;
  gap: 16px;
  background:
    radial-gradient(circle at 0% 0%, rgba(45, 212, 191, 0.12), transparent 24%),
    radial-gradient(circle at 100% 18%, rgba(56, 189, 248, 0.14), transparent 20%),
    linear-gradient(180deg, #f8fafc 0%, #eef6ff 100%);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 22px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(20px);
}

.page-header__copy {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.page-header__eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.page-header__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 28px;
  color: #0f172a;
}

.page-header__desc {
  max-width: 760px;
  margin: 0;
  color: #475569;
  line-height: 1.6;
}

.page-header__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.page-header__stats span {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.05);
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.page-header__actions {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.page-panel {
  padding: 18px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.68);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(20px);
}

@media (max-width: 960px) {
  .bot-connectors-page {
    padding: 16px;
  }

  .page-header,
  .page-header__title-row {
    flex-direction: column;
  }
}
</style>
