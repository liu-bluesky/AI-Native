<template>
  <section :class="['bot-connectors', { 'bot-connectors--compact': compact }]">
    <div v-if="!compact" class="bot-connectors__hero">
      <div>
        <p class="bot-connectors__eyebrow">Robot Hub</p>
        <h3>第三方机器人接入</h3>
        <p class="bot-connectors__desc">
          把 QQ、飞书、微信等机器人配置保存到本机全局存储，支持同一平台添加多个机器人实例。机器人提示词只来自当前配置，业务处理由桌面智能体执行。
        </p>
      </div>
      <el-tag type="info" effect="plain">按机器人实例管理</el-tag>
    </div>

    <div class="bot-connectors__toolbar">
      <div>
        <div class="bot-connectors__toolbar-title">机器人配置列表</div>
        <p class="bot-connectors__toolbar-desc">
          每个配置都有独立 ID，可用于区分不同飞书应用、不同项目或不同自动回复场景。
        </p>
      </div>
      <div class="bot-connectors__toolbar-actions">
        <el-button
          v-for="preset in PLATFORM_PRESETS"
          :key="preset.platform"
          type="primary"
          plain
          @click="openDialog(preset.platform)"
        >
          添加{{ preset.name }}机器人
        </el-button>
      </div>
    </div>

    <el-empty
      v-if="!connectorCards.length"
      class="bot-connectors__empty"
      description="还没有第三方机器人配置"
    >
      <template #extra>
        <div class="bot-connectors__empty-actions">
          <el-button
            v-for="preset in PLATFORM_PRESETS"
            :key="preset.platform"
            type="primary"
            @click="openDialog(preset.platform)"
          >
            添加{{ preset.name }}机器人
          </el-button>
        </div>
      </template>
    </el-empty>

    <div v-else class="bot-connectors__grid">
      <article
        v-for="connector in connectorCards"
        :key="connector.id"
        class="bot-card"
      >
        <div class="bot-card__top">
          <div class="bot-card__identity">
            <span class="bot-card__icon">{{ connector.icon }}</span>
            <div>
              <div class="bot-card__title">{{ connector.display_name }}</div>
              <div class="bot-card__subtitle">
                {{ connector.name }} · {{ connector.id }}
              </div>
            </div>
          </div>
          <div class="bot-card__badges">
            <el-tag size="small" type="info" effect="plain">
              {{ connector.name }}
            </el-tag>
            <el-tag
              size="small"
              :type="connector.connected ? 'success' : 'info'"
              effect="plain"
            >
              {{ connector.connected ? '已配置' : '待补凭证' }}
            </el-tag>
            <el-tag
              v-if="connector.enabled === false"
              size="small"
              type="warning"
              effect="plain"
            >
              已停用
            </el-tag>
          </div>
        </div>

        <p class="bot-card__summary">{{ connector.description || connector.summary }}</p>

        <div class="bot-card__meta">
          <div class="bot-card__meta-item">
            <span>回复方式</span>
            <strong>{{ connector.chat_mode_label }}</strong>
          </div>
          <div class="bot-card__meta-item">
            <span>对话模型</span>
            <strong>{{ connector.model_label }}</strong>
          </div>
          <div class="bot-card__meta-item">
            <span>App ID</span>
            <strong>{{ connector.app_id || '未填写' }}</strong>
          </div>
          <div class="bot-card__meta-item">
            <span>接收方式</span>
            <strong>{{ receiveModeLabel(connector.event_receive_mode) }}</strong>
          </div>
          <div class="bot-card__meta-item">
            <span>接收入口</span>
            <strong>{{ connector.event_url || '暂未接入' }}</strong>
          </div>
        </div>

        <div class="bot-card__actions">
          <el-button
            type="primary"
            plain
            :loading="diagnosingConnectorId === connector.id"
            @click="openDiagnose(connector)"
          >
            安装诊断
          </el-button>
          <el-button
            plain
            :loading="scanningConnectorId === connector.id"
            @click="openChatScan(connector)"
          >
            扫描群列表
          </el-button>
          <el-button @click="openDialog(connector.platform, connector)">
            编辑配置
          </el-button>
          <el-button text @click="duplicateConnector(connector)">
            复制
          </el-button>
          <el-button
            text
            :disabled="!connector.guide_url"
            @click="openGuide(connector.guide_url)"
          >
            指南
          </el-button>
          <el-popconfirm
            title="确定删除这个机器人配置吗？"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="deleteConnector(connector.id)"
          >
            <template #reference>
              <el-button text type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </article>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      :width="dialogWidth"
      top="5vh"
      class="bot-connector-edit-dialog"
      append-to-body
      destroy-on-close
    >
      <div class="connector-dialog" v-if="editingPreset">
        <div class="connector-dialog__intro">
          <span class="connector-dialog__icon">{{ editingPreset.icon }}</span>
          <div>
            <div class="connector-dialog__name">{{ editingPreset.name }}机器人配置</div>
            <p class="connector-dialog__text">{{ editingPreset.summary }}</p>
          </div>
        </div>

        <el-form label-position="top" class="connector-dialog__form">
          <div class="connector-dialog__switch">
            <div>
              <div class="connector-dialog__switch-title">启用当前机器人</div>
              <div class="connector-dialog__switch-desc">
                关闭后保留配置，但不会作为机器人接入候选。
              </div>
            </div>
            <el-switch v-model="draft.enabled" />
          </div>

          <div class="connector-dialog__section">
            <div class="connector-dialog__section-title">连接配置</div>
            <el-button
              text
              :disabled="!draft.guide_url"
              @click="openGuide(draft.guide_url)"
            >
              查看配置指南
            </el-button>
          </div>

          <div class="connector-dialog__grid">
            <el-form-item label="机器人名称">
              <el-input
                v-model="draft.name"
                placeholder="例如：需求沟通机器人 / 测试用例机器人"
              />
            </el-form-item>
            <el-form-item label="配置 ID *">
              <el-input
                v-model="draft.id"
                placeholder="用于事件回调和区分多个机器人"
              />
              <div class="connector-dialog__hint">
                同一平台可以有多个配置，但配置 ID 必须唯一。
              </div>
            </el-form-item>
            <el-form-item :label="appIdLabel">
              <el-input
                v-model="draft.app_id"
                :placeholder="appIdPlaceholder"
              />
            </el-form-item>
            <el-form-item :label="appSecretLabel">
              <el-input
                v-model="draft.app_secret"
                :placeholder="appSecretPlaceholder"
                show-password
              />
            </el-form-item>
            <el-form-item v-if="showReceiveModeField" label="事件接收方式">
              <el-radio-group v-model="draft.event_receive_mode" class="connector-dialog__radio-group">
                <el-radio-button
                  v-for="mode in receiveModeOptions"
                  :key="mode.value"
                  :label="mode.value"
                >
                  {{ mode.label }}
                </el-radio-button>
              </el-radio-group>
              <div class="connector-dialog__hint">
                {{ receiveModeHint }}
              </div>
            </el-form-item>
            <el-form-item v-if="showAutoStartWorkerField" label="长连接 worker">
              <div class="connector-dialog__switch connector-dialog__switch--inline">
                <div>
                  <div class="connector-dialog__switch-title">允许桌面端启动长连接监听</div>
                  <div class="connector-dialog__switch-desc">
                    保存后由桌面端机器人模块读取本机配置并监听平台事件，不把机器人业务托管给后端服务。
                  </div>
                </div>
                <el-switch v-model="draft.auto_start_worker" />
              </div>
            </el-form-item>
            <el-form-item label="回复方式">
              <el-radio-group v-model="draft.chat_mode" class="connector-dialog__radio-group">
                <el-radio-button label="desktop_local_agent">桌面本地智能体</el-radio-button>
              </el-radio-group>
              <div class="connector-dialog__hint">
                机器人消息只声明本地智能体运行目标；实际模型调用和工具执行应由桌面端本地智能体完成。
              </div>
            </el-form-item>
            <el-form-item label="桌面本地智能体模型">
              <el-select
                v-model="selectedBotModelOptionValue"
                filterable
                clearable
                :loading="loadingBotChatModelOptions"
                placeholder="请选择回复使用的模型"
              >
                <el-option-group
                  v-for="group in botProviderModelGroups"
                  :key="group.providerId"
                  :label="group.label"
                >
                  <el-option
                    v-for="item in group.options"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  >
                    <span>{{ item.modelName }}</span>
                    <span class="connector-dialog__model-provider">
                      {{ item.providerLabel }}
                    </span>
                  </el-option>
                </el-option-group>
              </el-select>
              <div class="connector-dialog__hint">
                这里保存桌面本地智能体要使用的模型目标；留空时由桌面端运行时按账号默认模型解析。
              </div>
            </el-form-item>
            <el-form-item v-if="showVerificationTokenField" label="Verification Token">
              <el-input
                v-model="draft.verification_token"
                placeholder="请输入飞书事件订阅 Verification Token"
              />
              <div class="connector-dialog__hint">
                飞书事件订阅校验会用到这个字段，不会展示在机器人卡片摘要中。
              </div>
            </el-form-item>
            <el-form-item v-if="showEncryptKeyField" label="Encrypt Key">
              <el-input
                v-model="draft.encrypt_key"
                placeholder="请输入飞书事件订阅 Encrypt Key"
                show-password
              />
              <div class="connector-dialog__hint">
                开启飞书消息加密后必填；未开启时可以留空。
              </div>
            </el-form-item>
          </div>
          <el-form-item label="配置说明">
            <el-input
              v-model="draft.description"
              type="textarea"
              :rows="3"
              resize="vertical"
              placeholder="简短说明这个机器人负责什么场景。"
            />
          </el-form-item>
          <el-form-item label="机器人提示词">
            <el-input
              v-model="draft.system_prompt"
              type="textarea"
              :rows="10"
              resize="vertical"
              maxlength="4000"
              show-word-limit
              placeholder="选填。用于约束当前机器人在飞书群里回复时的身份、语气、边界和输出格式。"
            />
            <div class="connector-dialog__hint">
              这个字段会作为当前机器人的系统提示词参与飞书群回复；保存后运行时只读取这里的内容。
            </div>
          </el-form-item>
          <el-form-item label="回复身份">
            <el-select v-model="draft.reply_identity" placeholder="选择回复身份">
              <el-option label="机器人" value="bot" />
              <el-option label="当前登录人" value="user" />
            </el-select>
            <div class="connector-dialog__hint">
              长连接接收消息仍使用机器人能力；最终回复统一通过 lark-cli 发送，可按场景选择机器人或已授权用户身份。
            </div>
          </el-form-item>
          <el-form-item label="配置指南链接">
            <el-input
              v-model="draft.guide_url"
              placeholder="https://example.com/docs"
            />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <div class="connector-dialog__footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="isSaving"
            :disabled="isSaving || !canSaveDraft"
            @click="saveDraft"
          >
            保存接入
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="diagnoseDialogVisible"
      title="机器人安装诊断"
      width="760px"
      append-to-body
      destroy-on-close
    >
      <div class="diagnose-dialog" v-if="diagnosePayload">
        <el-alert
          :title="diagnosePayload.ok ? '配置检查通过' : '还有配置项需要处理'"
          :type="diagnosePayload.ok ? 'success' : 'warning'"
          :closable="false"
          show-icon
        />
        <div class="diagnose-dialog__summary">
          <span>平台：{{ diagnosePayload.platform || '-' }}</span>
          <span>接收方式：{{ receiveModeLabel(diagnosePayload.receive_mode) }}</span>
        </div>
        <div class="diagnose-dialog__checks">
          <div
            v-for="check in diagnosePayload.checks || []"
            :key="check.id"
            class="diagnose-dialog__check"
          >
            <el-tag :type="check.ok ? 'success' : 'warning'" effect="plain">
              {{ check.ok ? '通过' : '待处理' }}
            </el-tag>
            <div>
              <strong>{{ check.title }}</strong>
              <p>{{ check.message }}</p>
              <small v-if="check.action">建议：{{ check.action }}</small>
            </div>
          </div>
        </div>
        <div v-if="diagnosePayload.manifest" class="diagnose-dialog__manifest">
          <h4>平台安装清单</h4>
          <ul>
            <li v-for="step in diagnosePayload.manifest.install_steps || []" :key="step">
              {{ step }}
            </li>
          </ul>
          <p v-if="diagnosePayload.manifest.required_events?.length">
            事件：{{ diagnosePayload.manifest.required_events.join('、') }}
          </p>
          <p v-if="diagnosePayload.manifest.required_permissions?.length">
            权限：{{ diagnosePayload.manifest.required_permissions.join('、') }}
          </p>
        </div>
        <div v-if="diagnosePayload.next_actions?.length" class="diagnose-dialog__next">
          <h4>下一步</h4>
          <ul>
            <li v-for="action in diagnosePayload.next_actions" :key="action">
              {{ action }}
            </li>
          </ul>
        </div>
      </div>
      <el-empty v-else description="暂无诊断结果" />
      <template #footer>
        <el-button @click="diagnoseDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="chatScanDialogVisible"
      title="机器人所在群"
      width="760px"
      append-to-body
      destroy-on-close
    >
      <div class="diagnose-dialog" v-if="chatScanPayload">
        <el-alert
          :title="chatScanPayload.message || scanStatusLabel(chatScanPayload.status)"
          :type="chatScanPayload.status === 'scanned' ? 'success' : 'warning'"
          :closable="false"
          show-icon
        />
        <div class="diagnose-dialog__summary">
          <span>平台：{{ chatScanPayload.platform || '-' }}</span>
          <span>连接器：{{ chatScanPayload.connector_id || '-' }}</span>
          <span>群数量：{{ chatScanPayload.count || 0 }}</span>
        </div>
        <el-table
          v-if="chatScanPayload.items?.length"
          :data="chatScanPayload.items"
          stripe
          class="bot-chat-scan-table"
        >
          <el-table-column label="群名称" min-width="180">
            <template #default="{ row }">{{ row.chat_name || '-' }}</template>
          </el-table-column>
          <el-table-column label="群 ID" min-width="220">
            <template #default="{ row }">
              <code>{{ row.chat_id }}</code>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="120">
            <template #default="{ row }">{{ row.chat_type || row.chat_mode || '-' }}</template>
          </el-table-column>
          <el-table-column label="来源" width="160">
            <template #default="{ row }">{{ row.source || '-' }}</template>
          </el-table-column>
        </el-table>
        <div v-if="chatScanPayload.missing?.length" class="diagnose-dialog__next">
          <h4>缺少信息</h4>
          <ul>
            <li v-for="item in chatScanPayload.missing" :key="item">{{ item }}</li>
          </ul>
        </div>
      </div>
      <el-empty v-else description="暂无扫描结果" />
      <template #footer>
        <el-button @click="chatScanDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "@/utils/api.js";
import {
  FALLBACK_MODEL_TYPE_OPTIONS,
  normalizeProviderModelConfigs as normalizeLlmProviderModelConfigs,
} from "@/utils/llm-models.js";
import {
  hasNativeDesktopBridge,
  scanNativeFeishuBotChats,
} from "@/utils/native-desktop-bridge.js";

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  compact: {
    type: Boolean,
    default: false,
  },
  saving: {
    type: Boolean,
    default: false,
  },
  persistConnectors: {
    type: Function,
    default: null,
  },
});

const emit = defineEmits(["update:modelValue"]);

const PLATFORM_PRESETS = [
  {
    platform: "qq",
    icon: "QQ",
    name: "QQ",
    subtitle: "QQ群与 QQ 机器人",
    summary: "管理 QQ 机器人的凭证、项目归属和配置备注。",
    receive_modes: ["manual", "long_connection", "http_callback"],
    default_receive_mode: "manual",
    app_id_label: "QQ 机器人 App ID *",
    app_id_placeholder: "请输入 QQ 开放平台 App ID",
    app_secret_label: "QQ 机器人 App Secret *",
    app_secret_placeholder: "请输入 QQ 开放平台 App Secret",
  },
  {
    platform: "feishu",
    icon: "飞",
    name: "飞书",
    subtitle: "飞书应用机器人",
    summary: "管理飞书机器人的凭证、项目归属、事件订阅和配置备注。",
    receive_modes: ["long_connection", "http_callback"],
    default_receive_mode: "long_connection",
    app_id_label: "飞书应用 App ID *",
    app_id_placeholder: "请输入飞书开放平台 App ID",
    app_secret_label: "飞书应用 App Secret *",
    app_secret_placeholder: "请输入飞书开放平台 App Secret",
  },
  {
    platform: "wechat",
    icon: "微",
    name: "微信",
    subtitle: "企业微信 / 微信机器人",
    summary: "管理微信侧机器人的凭证、项目归属和配置备注。",
    receive_modes: ["http_callback", "polling", "manual"],
    default_receive_mode: "http_callback",
    app_id_label: "微信应用 App ID *",
    app_id_placeholder: "请输入微信开放平台 App ID",
    app_secret_label: "微信应用 App Secret *",
    app_secret_placeholder: "请输入微信开放平台 App Secret",
  },
];

const SUPPORTED_PLATFORMS = PLATFORM_PRESETS.map((item) => item.platform);
const RECEIVE_MODE_LABELS = {
  http_callback: "HTTP 回调",
  long_connection: "长连接",
  polling: "轮询",
  manual: "手动配置",
};
const RECEIVE_MODE_HINTS = {
  http_callback: "平台会把事件 POST 到公网回调入口；该入口只负责收事件，业务处理仍交给桌面智能体。",
  long_connection: "桌面端机器人模块主动连接平台事件网关，飞书推荐此方式，不需要公网回调域名。",
  polling: "由桌面端机器人模块定时拉取平台消息，适合少量不支持事件推送的平台。",
  manual: "先保存凭证和说明，事件适配后续再接入。",
};
function findPreset(platform) {
  const normalizedPlatform = String(platform || "").trim().toLowerCase();
  return PLATFORM_PRESETS.find((item) => item.platform === normalizedPlatform) || null;
}

function normalizeConnectorId(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 80);
}

function createConnectorId(platform) {
  const normalizedPlatform = String(platform || "connector").trim().toLowerCase() || "connector";
  const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  return normalizeConnectorId(`${normalizedPlatform}-${suffix}`);
}

function receiveModeLabel(mode) {
  return RECEIVE_MODE_LABELS[String(mode || "").trim().toLowerCase()] || "未设置";
}

function normalizeReceiveMode(value, preset) {
  const allowedModes = Array.isArray(preset?.receive_modes) ? preset.receive_modes : ["manual"];
  const normalized = String(value || preset?.default_receive_mode || allowedModes[0] || "manual")
    .trim()
    .toLowerCase();
  return allowedModes.includes(normalized) ? normalized : allowedModes[0] || "manual";
}

function normalizeChatMode(value) {
  return "desktop_local_agent";
}

function normalizeExternalAgentType(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return ["codex_cli", "hermes", "claude_code"].includes(normalized)
    ? normalized
    : "codex_cli";
}

function normalizeScannedChats(value) {
  const items = Array.isArray(value) ? value : [];
  const seen = new Set();
  const normalized = [];
  for (const item of items) {
    const chatId = String(item?.chat_id || item?.chatId || "").trim().slice(0, 200);
    if (!chatId || seen.has(chatId)) continue;
    seen.add(chatId);
    normalized.push({
      chat_id: chatId,
      chat_name: String(item?.chat_name || item?.chatName || item?.name || "")
        .trim()
        .slice(0, 200),
      chat_type: String(item?.chat_type || item?.chatType || item?.chat_mode || "group")
        .trim()
        .slice(0, 80),
      chat_mode: String(item?.chat_mode || item?.chatMode || "").trim().slice(0, 80),
      source: String(item?.source || "").trim().slice(0, 200),
      scanned_at: String(item?.scanned_at || item?.scannedAt || "").trim().slice(0, 80),
    });
    if (normalized.length >= 500) break;
  }
  return normalized;
}

function normalizeConnector(item) {
  const raw = item && typeof item === "object" && !Array.isArray(item) ? item : {};
  const platform = String(raw.platform || "").trim().toLowerCase();
  const preset = findPreset(platform);
  const id = normalizeConnectorId(raw.id || `${platform || "connector"}-connector`);
  return {
    id,
    enabled: raw.enabled !== false,
    platform,
    name: String(raw.name || "").trim().slice(0, 120),
    agent_name: "",
    description: String(raw.description || "").trim().slice(0, 280),
    system_prompt: String(raw.system_prompt || "").trim().slice(0, 4000),
    chat_mode: normalizeChatMode(raw.chat_mode),
    external_agent_type: normalizeExternalAgentType(raw.external_agent_type),
    provider_id: String(raw.provider_id || "").trim().slice(0, 120),
    model_name: String(raw.model_name || "").trim().slice(0, 160),
    model_runtime:
      raw.model_runtime && typeof raw.model_runtime === "object"
        ? { ...raw.model_runtime }
        : raw.modelRuntime && typeof raw.modelRuntime === "object"
          ? { ...raw.modelRuntime }
          : null,
    app_id: String(raw.app_id || "").trim().slice(0, 160),
    app_secret: String(raw.app_secret || "").trim().slice(0, 200),
    verification_token: String(raw.verification_token || "").trim().slice(0, 200),
    encrypt_key: String(raw.encrypt_key || "").trim().slice(0, 200),
    event_receive_mode: normalizeReceiveMode(raw.event_receive_mode, preset),
    auto_start_worker: raw.auto_start_worker === true,
    reply_identity: ["bot", "user"].includes(String(raw.reply_identity || "").trim().toLowerCase())
      ? String(raw.reply_identity || "").trim().toLowerCase()
      : "bot",
    project_id: "",
    guide_url: String(raw.guide_url || "").trim().slice(0, 500),
    sort_order: Math.min(999, Math.max(0, Number(raw.sort_order || 0) || 0)),
    scanned_chats: normalizeScannedChats(raw.scanned_chats || raw.scannedChats),
    display_name: String(raw.name || preset?.name || id || "机器人").trim(),
  };
}

const botChatProviderOptions = ref([]);
const loadingBotChatModelOptions = ref(false);
const botChatProviderMap = computed(() =>
  botChatProviderOptions.value.reduce((accumulator, item) => {
    accumulator[String(item.id || "").trim()] = item;
    return accumulator;
  }, {}),
);

const botProviderModelGroups = computed(() =>
  botChatProviderOptions.value
    .map((provider) => {
      const providerId = String(provider?.id || "").trim();
      const providerLabel = String(provider?.name || providerId || "未命名供应商").trim();
      const models = normalizeProviderModelConfigs(provider);
      return {
        providerId,
        label: providerLabel,
        options: models.map((item) => ({
          value: `${providerId}::${item.name}`,
          providerId,
          providerLabel,
          modelName: item.name,
          modelType: item.model_type,
          label: `${item.name} · ${providerLabel}`,
        })),
      };
    })
    .filter((group) => group.providerId && group.options.length),
);

const selectedBotModelOptionValue = computed({
  get() {
    const providerId = String(draft.value.provider_id || "").trim();
    const modelName = String(draft.value.model_name || "").trim();
    if (!providerId || !modelName) {
      return "";
    }
    return `${providerId}::${modelName}`;
  },
  set(value) {
    const normalized = String(value || "").trim();
    if (!normalized) {
      draft.value.provider_id = "";
      draft.value.model_name = "";
      return;
    }
    const separatorIndex = normalized.indexOf("::");
    if (separatorIndex < 0) {
      return;
    }
    draft.value.provider_id = normalized.slice(0, separatorIndex);
    draft.value.model_name = normalized.slice(separatorIndex + 2);
  },
});

const normalizedConnectors = computed(() => {
  if (!Array.isArray(props.modelValue)) {
    return [];
  }
  const items = [];
  const seen = new Set();
  for (const rawItem of props.modelValue) {
    const item = normalizeConnector(rawItem);
    if (!SUPPORTED_PLATFORMS.includes(item.platform) || !item.id) {
      continue;
    }
    const uniqueKey = item.id.toLowerCase();
    if (seen.has(uniqueKey)) {
      continue;
    }
    seen.add(uniqueKey);
    items.push(item);
  }
  return items.sort(
    (a, b) => a.sort_order - b.sort_order || a.platform.localeCompare(b.platform) || a.id.localeCompare(b.id),
  );
});

const connectorCards = computed(() =>
  normalizedConnectors.value.map((connector) => {
    const preset = findPreset(connector.platform) || {};
    return {
      ...preset,
      ...connector,
      display_name: connector.name || `${preset.name || "机器人"}配置`,
      chat_mode_label: botChatModeLabel(connector),
      model_label: botChatModelLabel(connector),
      connected: Boolean(
        connector.enabled &&
          connector.app_id &&
          connector.app_secret,
      ),
      event_url:
        connector.event_receive_mode === "long_connection"
          ? "桌面长连接监听"
          : connector.platform === "feishu" && connector.event_receive_mode === "http_callback"
            ? "公网事件入口仅转发到桌面队列"
            : "待平台适配",
    };
  }),
);

const dialogVisible = ref(false);
const editingPlatform = ref("");
const editingConnectorId = ref("");
const draft = ref({
  id: "",
  enabled: true,
  platform: "",
  name: "",
  agent_name: "",
  description: "",
  system_prompt: "",
  chat_mode: "desktop_local_agent",
  external_agent_type: "codex_cli",
  provider_id: "",
  model_name: "",
  app_id: "",
  app_secret: "",
  verification_token: "",
  encrypt_key: "",
  event_receive_mode: "manual",
  auto_start_worker: false,
  reply_identity: "bot",
  project_id: "",
  guide_url: "",
  sort_order: 0,
});

const editingPreset = computed(() => findPreset(editingPlatform.value));
const dialogTitle = computed(() => {
  if (!editingPreset.value) {
    return "机器人接入";
  }
  return editingConnectorId.value
    ? `编辑${editingPreset.value.name}机器人`
    : `添加${editingPreset.value.name}机器人`;
});
const compact = computed(() => props.compact === true);
const isSaving = computed(() => props.saving === true);
const dialogWidth = computed(() => (compact.value ? "920px" : "760px"));
const appIdLabel = computed(() => editingPreset.value?.app_id_label || "App ID *");
const appIdPlaceholder = computed(
  () => editingPreset.value?.app_id_placeholder || "请输入 App ID",
);
const appSecretLabel = computed(
  () => editingPreset.value?.app_secret_label || "App Secret *",
);
const appSecretPlaceholder = computed(
  () => editingPreset.value?.app_secret_placeholder || "请输入 App Secret",
);
const showVerificationTokenField = computed(
  () => editingPlatform.value === "feishu",
);
const showEncryptKeyField = computed(
  () => editingPlatform.value === "feishu",
);
const showReceiveModeField = computed(() => Boolean(editingPreset.value));
const receiveModeOptions = computed(() =>
  (editingPreset.value?.receive_modes || ["manual"]).map((value) => ({
    value,
    label: receiveModeLabel(value),
  })),
);
const receiveModeHint = computed(
  () => RECEIVE_MODE_HINTS[draft.value.event_receive_mode] || "选择当前平台的事件接收方式。",
);
const showAutoStartWorkerField = computed(
  () => editingPlatform.value === "feishu" && draft.value.event_receive_mode === "long_connection",
);
const diagnoseDialogVisible = ref(false);
const diagnosePayload = ref(null);
const diagnosingConnectorId = ref("");
const chatScanDialogVisible = ref(false);
const chatScanPayload = ref(null);
const scanningConnectorId = ref("");
const canSaveDraft = computed(
  () =>
    Boolean(
      normalizeConnectorId(draft.value.id) &&
        String(draft.value.app_id || "").trim() &&
        String(draft.value.app_secret || "").trim(),
    ),
);

function nextSortOrder(platform) {
  const samePlatformItems = normalizedConnectors.value.filter(
    (item) => item.platform === platform,
  );
  if (!samePlatformItems.length) {
    const platformIndex = Math.max(0, SUPPORTED_PLATFORMS.indexOf(platform));
    return (platformIndex + 1) * 100;
  }
  return Math.min(
    999,
    Math.max(...samePlatformItems.map((item) => Number(item.sort_order || 0))) + 1,
  );
}

function openDialog(platform, connector = null) {
  const normalizedPlatform = String(platform || "").trim().toLowerCase();
  const preset = findPreset(normalizedPlatform);
  if (!preset) {
    return;
  }
  editingPlatform.value = normalizedPlatform;
  editingConnectorId.value = connector?.id ? String(connector.id).trim() : "";
  draft.value = normalizeConnector(
    connector || {
      id: createConnectorId(normalizedPlatform),
      enabled: true,
      platform: normalizedPlatform,
      name: `${preset.name}机器人${normalizedConnectors.value.filter((item) => item.platform === normalizedPlatform).length + 1}`,
      agent_name: "",
      description: "",
      system_prompt: "",
      provider_id: "",
      model_name: "",
      app_id: "",
      app_secret: "",
      verification_token: "",
      encrypt_key: "",
      event_receive_mode: preset.default_receive_mode || "manual",
      auto_start_worker: false,
      reply_identity: "bot",
      project_id: "",
      guide_url: "",
      sort_order: nextSortOrder(normalizedPlatform),
    },
  );
  dialogVisible.value = true;
}

function openGuide(url) {
  const resolved = String(url || "").trim();
  if (!resolved) {
    ElMessage.warning("当前还没有配置平台指南链接");
    return;
  }
  window.open(resolved, "_blank", "noopener,noreferrer");
}

async function openDiagnose(connector) {
  const connectorId = String(connector?.id || "").trim();
  if (!connectorId) {
    ElMessage.warning("请先保存机器人配置");
    return;
  }
  diagnosingConnectorId.value = connectorId;
  try {
    diagnosePayload.value = buildLocalDiagnosePayload(connector);
    diagnoseDialogVisible.value = true;
  } catch (err) {
    ElMessage.error(err?.message || "机器人安装诊断失败");
  } finally {
    diagnosingConnectorId.value = "";
  }
}

async function openChatScan(connector) {
  const connectorId = String(connector?.id || "").trim();
  if (!connectorId) {
    ElMessage.warning("请先保存机器人配置");
    return;
  }
  scanningConnectorId.value = connectorId;
  try {
    chatScanPayload.value = await buildLocalChatScanPayload(connector);
    if (chatScanPayload.value?.status === "scanned") {
      await persistConnectorChatScan(connectorId, chatScanPayload.value);
    }
    chatScanDialogVisible.value = true;
  } catch (err) {
    ElMessage.error(err?.message || "扫描机器人所在群失败");
  } finally {
    scanningConnectorId.value = "";
  }
}

async function persistConnectorChatScan(connectorId, payload) {
  const scannedAt = new Date().toISOString();
  const scannedChats = normalizeScannedChats(
    (Array.isArray(payload?.items) ? payload.items : []).map((item) => ({
      ...item,
      scanned_at: scannedAt,
    })),
  );
  const nextConnectors = normalizedConnectors.value.map((item) =>
    item.id === connectorId
      ? normalizeConnector({
          ...item,
          scanned_chats: scannedChats,
        })
      : item,
  );
  await persistNextConnectors(nextConnectors, "群列表已写入本机机器人配置");
}

function buildLocalDiagnosePayload(connector) {
  const item = normalizeConnector(connector);
  const checks = [
    {
      id: "local_config",
      ok: Boolean(item.id && item.platform),
      title: "本机全局配置",
      message: item.id && item.platform ? "机器人配置已在本机全局文件中维护" : "缺少机器人配置 ID 或平台",
      action: item.id && item.platform ? "" : "补齐配置 ID 与平台后保存",
    },
    {
      id: "credentials",
      ok: Boolean(item.app_id && item.app_secret),
      title: "平台凭证",
      message: item.app_id && item.app_secret ? "已填写平台 App ID 和 App Secret" : "缺少平台 App ID 或 App Secret",
      action: item.app_id && item.app_secret ? "" : "在连接配置里补齐平台凭证",
    },
    {
      id: "runtime",
      ok: item.chat_mode === "desktop_local_agent",
      title: "运行位置",
      message: "机器人业务逻辑配置为桌面本地智能体执行",
      action: "",
    },
    {
      id: "lark_cli_identity",
      ok: item.platform !== "feishu" || hasNativeDesktopBridge(),
      title: "飞书本机身份",
      message: item.platform === "feishu"
        ? "桌面长连接使用本机 lark-cli 当前 bot 身份；App ID / Secret 用于配置记录和人工核对，不会自动切换 lark-cli 应用身份。"
        : "当前平台暂未接入本机身份检查。",
      action: item.platform === "feishu"
        ? "如需多个飞书应用隔离，请先切换本机 lark-cli 应用配置，或后续接入原生 OpenAPI 长连接客户端。"
        : "",
    },
    {
      id: "prompt_policy",
      ok: true,
      title: "提示词来源",
      message: item.system_prompt ? "运行时只使用当前机器人配置里的提示词" : "未填写机器人提示词，运行时不会注入内置机器人提示词",
      action: "",
    },
  ];
  return {
    ok: checks.every((check) => check.ok),
    platform: item.platform,
    receive_mode: item.event_receive_mode,
    checks,
    manifest: {
      install_steps: [
        "在机器人平台创建应用并填写 App ID / App Secret",
        "桌面端读取本机全局机器人配置",
        "桌面智能体执行消息处理、工具调用和命令确认",
      ],
      required_events: item.platform === "feishu" ? ["im.message.receive_v1"] : [],
      required_permissions: item.platform === "feishu" ? ["im:message", "im:chat"] : [],
    },
    next_actions: item.event_receive_mode === "http_callback"
      ? ["HTTP 回调只作为事件入口；业务处理仍需桌面端在线并领取任务。"]
      : ["启动桌面端机器人监听后再测试平台消息。"],
  };
}

async function buildLocalChatScanPayload(connector) {
  const item = normalizeConnector(connector);
  if (item.platform === "feishu") {
    if (!hasNativeDesktopBridge()) {
      return {
        status: "unsupported",
        message: "群扫描需要在桌面端运行，当前浏览器环境不可用。",
        platform: item.platform,
        connector_id: item.id,
        count: 0,
        items: [],
        missing: ["桌面端 Tauri 运行时"],
      };
    }
    const result = await scanNativeFeishuBotChats({
      identity: item.reply_identity || "bot",
      pageSize: 100,
      pageLimit: 10,
    });
    const items = (Array.isArray(result?.items) ? result.items : []).map((row) => ({
      chat_id: String(row.chat_id || row.chatId || "").trim(),
      chat_name: String(row.name || row.chat_name || row.chatName || "").trim(),
      chat_type: String(row.chat_mode || row.chat_type || row.chatMode || "group").trim(),
      chat_mode: String(row.chat_mode || row.chatMode || "").trim(),
      source: `lark-cli --as ${result?.identity || item.reply_identity || "bot"}`,
    })).filter((row) => row.chat_id);
    return {
      status: "scanned",
      message: result?.message || "桌面端已扫描机器人所在群",
      platform: item.platform,
      connector_id: item.id,
      count: items.length,
      items,
      missing: [],
    };
  }
  return {
    status: "unsupported",
    message: "当前平台缺少桌面端本地群扫描适配器。",
    platform: item.platform,
    connector_id: item.id,
    count: 0,
    items: [],
    missing: [
      "桌面端本地群扫描适配器",
      "平台授权后的本地扫描命令",
    ],
  };
}

function scanStatusLabel(status) {
  const normalized = String(status || "").trim();
  const labels = {
    scanned: "群列表扫描完成",
    unsupported: "当前平台暂不支持全量扫描",
    missing_credentials: "缺少平台凭证",
    missing_connector: "机器人配置不存在",
    disabled: "机器人配置已停用",
  };
  return labels[normalized] || "群列表扫描未完成";
}

function normalizeProviderModelConfigs(provider) {
  return normalizeLlmProviderModelConfigs(provider, FALLBACK_MODEL_TYPE_OPTIONS);
}

function normalizeBotChatProvider(provider) {
  if (!provider || typeof provider !== "object" || Array.isArray(provider)) {
    return null;
  }
  const id = String(provider.id || "").trim();
  if (!id) {
    return null;
  }
  const modelConfigs = normalizeProviderModelConfigs(provider);
  return {
    ...provider,
    id,
    name: String(provider.name || id).trim(),
    provider_type: String(provider.provider_type || "").trim(),
    default_model: String(provider.default_model || modelConfigs[0]?.name || "").trim(),
    model_configs: modelConfigs,
  };
}

function mergeBotChatProviders(providers) {
  const merged = [];
  const seen = new Set();
  const add = (provider) => {
    const normalized = normalizeBotChatProvider(provider);
    if (!normalized || seen.has(normalized.id)) {
      return;
    }
    seen.add(normalized.id);
    merged.push(normalized);
  };
  (Array.isArray(providers) ? providers : []).forEach(add);
  return merged;
}

function botChatModeLabel(connector) {
  return "桌面本地智能体";
}

function botChatModelLabel(connector) {
  const providerId = String(connector?.provider_id || "").trim();
  const modelName = String(connector?.model_name || "").trim();
  if (!providerId) {
    return "按账号默认";
  }
  const provider = botChatProviderMap.value[providerId] || null;
  const providerName = String(provider?.name || providerId).trim();
  const modelLabel = modelName || String(provider?.default_model || "").trim() || "模型默认";
  return `${providerName} · ${modelLabel}`;
}

async function fetchBotChatModelOptions(options = {}) {
  const preserveSelection = options.preserveSelection !== false;
  const currentProviderId = String(draft.value.provider_id || "").trim();
  const currentModelName = String(draft.value.model_name || "").trim();
  loadingBotChatModelOptions.value = true;
  try {
    const llmProviderData = await api.get("/llm/providers", {
      params: { enabled_only: true },
    });
    botChatProviderOptions.value = mergeBotChatProviders([
      ...(Array.isArray(llmProviderData?.providers) ? llmProviderData.providers : []),
    ]);
    if (preserveSelection && currentProviderId) {
      const provider = botChatProviderOptions.value.find((item) => item.id === currentProviderId);
      if (!provider) {
        draft.value.provider_id = "";
        draft.value.model_name = "";
      } else if (currentModelName) {
        const modelNames = normalizeProviderModelConfigs(provider).map((item) => item.name);
        if (!modelNames.includes(currentModelName)) {
          draft.value.model_name = "";
        }
      }
    }
  } catch {
    botChatProviderOptions.value = [];
  } finally {
    loadingBotChatModelOptions.value = false;
  }
}

async function persistNextConnectors(nextConnectors, successMessage) {
  if (typeof props.persistConnectors === "function") {
    await props.persistConnectors(nextConnectors);
  } else {
    emit("update:modelValue", nextConnectors);
    ElMessage.success(successMessage);
  }
}

async function saveDraft() {
  const nextItem = normalizeConnector({
    ...draft.value,
    id: normalizeConnectorId(draft.value.id),
    platform: editingPlatform.value,
    agent_name: "",
    project_id: "",
  });
  const duplicate = normalizedConnectors.value.find(
    (item) =>
      item.id.toLowerCase() === nextItem.id.toLowerCase() &&
      item.id !== editingConnectorId.value,
  );
  if (duplicate) {
    ElMessage.warning("配置 ID 已存在，请换一个 ID");
    return;
  }
  const retained = normalizedConnectors.value.filter(
    (item) => item.id !== (editingConnectorId.value || nextItem.id),
  );
  const nextConnectors = [...retained, nextItem];
  await persistNextConnectors(nextConnectors, `${editingPreset.value?.name || "平台"}机器人配置已保存`);
  dialogVisible.value = false;
}

async function deleteConnector(connectorId) {
  const normalizedId = String(connectorId || "").trim();
  if (!normalizedId) {
    return;
  }
  const nextConnectors = normalizedConnectors.value.filter(
    (item) => item.id !== normalizedId,
  );
  await persistNextConnectors(nextConnectors, "机器人配置已删除");
}

async function duplicateConnector(connector) {
  const source = normalizeConnector(connector);
  const preset = findPreset(source.platform);
  const nextItem = normalizeConnector({
    ...source,
    id: createConnectorId(source.platform),
    name: `${source.name || preset?.name || "机器人"} 副本`,
    sort_order: Math.min(999, Number(source.sort_order || 0) + 1),
  });
  await persistNextConnectors(
    [...normalizedConnectors.value, nextItem],
    "机器人配置已复制",
  );
}

onMounted(() => {
  fetchBotChatModelOptions();
});
</script>

<style scoped>
.bot-connectors {
  display: grid;
  gap: 24px;
}

.bot-connectors--compact {
  gap: 18px;
}

.bot-connectors__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 28px 30px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.bot-connectors__eyebrow {
  margin: 0 0 10px;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.bot-connectors__hero h3 {
  margin: 0;
  font-size: 30px;
  color: #0f172a;
}

.bot-connectors__desc {
  max-width: 760px;
  margin: 10px 0 0;
  color: #475569;
  line-height: 1.7;
}

.bot-connectors__toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.68);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
}

.bot-connectors__toolbar-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.bot-connectors__toolbar-desc {
  margin: 6px 0 0;
  color: #64748b;
  line-height: 1.6;
}

.bot-connectors__toolbar-actions,
.bot-connectors__empty-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.bot-connectors__empty {
  padding: 42px 24px;
  border: 1px dashed rgba(148, 163, 184, 0.5);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.64);
}

.bot-connectors__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 18px;
}

.bot-card {
  display: grid;
  gap: 18px;
  padding: 24px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.74);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.bot-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.bot-card__identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.bot-card__badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.bot-card__icon,
.connector-dialog__icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 16px;
  background:
    radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.26), transparent 58%),
    rgba(15, 23, 42, 0.92);
  color: #f8fafc;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.bot-card__title,
.connector-dialog__name {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.bot-card__subtitle {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
  word-break: break-all;
}

.bot-card__summary,
.connector-dialog__text {
  margin: 0;
  color: #475569;
  line-height: 1.7;
}

.bot-card__meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.bot-card__meta-item {
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.7);
}

.bot-card__meta-item span {
  display: block;
  color: #7c8aa0;
  font-size: 12px;
  margin-bottom: 6px;
}

.bot-card__meta-item strong {
  display: block;
  color: #0f172a;
  font-size: 13px;
  word-break: break-all;
}

.bot-card__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.connector-dialog {
  display: grid;
  gap: 18px;
}

.connector-dialog__intro {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 18px 20px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 22px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.88) 0%,
    rgba(248, 250, 252, 0.72) 100%
  );
}

.connector-dialog__form {
  display: grid;
  gap: 12px;
}

.connector-dialog__switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 20px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 22px;
  background: rgba(248, 250, 252, 0.68);
}

.connector-dialog__switch-title,
.connector-dialog__section-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.connector-dialog__switch-desc,
.connector-dialog__hint {
  margin-top: 6px;
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.6;
}

.connector-dialog__model-provider {
  float: right;
  margin-left: 18px;
  color: #94a3b8;
  font-size: 12px;
}

.connector-dialog__section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 4px;
}

.connector-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.connector-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.connector-dialog__radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.connector-dialog__switch--inline {
  width: 100%;
  margin: 0;
}

.diagnose-dialog {
  display: grid;
  gap: 16px;
}

.diagnose-dialog__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.diagnose-dialog__summary span {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.diagnose-dialog__checks {
  display: grid;
  gap: 10px;
}

.diagnose-dialog__check {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: flex-start;
  padding: 12px;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.86);
}

.diagnose-dialog__check strong {
  color: #0f172a;
}

.diagnose-dialog__check p {
  margin: 4px 0;
  color: #475569;
}

.diagnose-dialog__check small {
  color: #64748b;
}

.diagnose-dialog__manifest,
.diagnose-dialog__next {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(239, 246, 255, 0.78);
}

.diagnose-dialog__manifest h4,
.diagnose-dialog__next h4 {
  margin: 0 0 8px;
  color: #0f172a;
}

.diagnose-dialog__manifest ul,
.diagnose-dialog__next ul {
  margin: 0;
  padding-left: 20px;
  color: #334155;
}

.diagnose-dialog__manifest p {
  margin: 8px 0 0;
  color: #475569;
}

@media (max-width: 1080px) {
  .connector-dialog__grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .bot-connectors__hero,
  .bot-connectors__toolbar,
  .bot-card__top {
    flex-direction: column;
  }

  .bot-connectors__toolbar-actions,
  .bot-card__badges {
    justify-content: flex-start;
  }

  .bot-card__meta {
    grid-template-columns: 1fr;
  }
}
</style>
