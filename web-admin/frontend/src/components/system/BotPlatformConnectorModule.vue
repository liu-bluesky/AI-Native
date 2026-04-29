<template>
  <section :class="['bot-connectors', { 'bot-connectors--compact': compact }]">
    <div v-if="!compact" class="bot-connectors__hero">
      <div>
        <p class="bot-connectors__eyebrow">Robot Hub</p>
        <h3>第三方机器人接入</h3>
        <p class="bot-connectors__desc">
          把 QQ、飞书、微信等机器人配置收敛到一个独立模块里，支持同一平台添加多个机器人实例。当前页面负责凭证、项目关联、提示词和接入说明，不代表平台消息已经全部接通。
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
            <span>接入智能体</span>
            <strong>{{ connector.agent_name || '未设置' }}</strong>
          </div>
          <div class="bot-card__meta-item">
            <span>关联项目</span>
            <strong>{{ connector.project_label || '未关联' }}</strong>
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
                  <div class="connector-dialog__switch-title">允许后端启动长连接 worker</div>
                  <div class="connector-dialog__switch-desc">
                    仍需要在系统配置页打开“飞书长连接 worker”总开关，保存后后端才会托管启动。
                  </div>
                </div>
                <el-switch v-model="draft.auto_start_worker" />
              </div>
            </el-form-item>
            <el-form-item label="接入智能体">
              <el-select
                v-model="draft.agent_name"
                filterable
                allow-create
                default-first-option
                :reserve-keyword="false"
                placeholder="选填，用于备注当前机器人对应的智能体"
              />
              <div class="connector-dialog__hint">
                当前系统里这个字段只做标注用途，不填也可以保存。
              </div>
            </el-form-item>
            <el-form-item label="关联项目">
              <el-select
                v-model="draft.project_id"
                filterable
                clearable
                placeholder="选择机器人接入的项目"
              >
                <el-option
                  v-for="item in normalizedProjectOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
              <div class="connector-dialog__hint">
                {{
                  draft.project_id
                    ? `当前关联项目：${findProjectLabel(draft.project_id)}`
                    : '未关联时只保留系统级接入配置。'
                }}
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
              :rows="5"
              resize="vertical"
              maxlength="4000"
              show-word-limit
              placeholder="选填。用于约束当前机器人在飞书群里回复时的身份、语气、边界和输出格式。"
            />
            <div class="connector-dialog__hint">
              这个字段会作为当前机器人的系统提示词参与 AI 回复；留空时使用项目 AI 对话默认提示词。
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
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "@/utils/api.js";

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  projectOptions: {
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
  http_callback: "平台会把事件 POST 到系统公网回调地址，适合已有公网域名的部署。",
  long_connection: "后端 worker 主动连接平台事件网关，飞书推荐此方式，不需要公网回调域名。",
  polling: "由后端定时拉取平台消息，适合少量不支持事件推送的平台。",
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
    agent_name: String(raw.agent_name || "").trim().slice(0, 120),
    description: String(raw.description || "").trim().slice(0, 280),
    system_prompt: String(raw.system_prompt || "").trim().slice(0, 4000),
    app_id: String(raw.app_id || "").trim().slice(0, 160),
    app_secret: String(raw.app_secret || "").trim().slice(0, 200),
    verification_token: String(raw.verification_token || "").trim().slice(0, 200),
    encrypt_key: String(raw.encrypt_key || "").trim().slice(0, 200),
    event_receive_mode: normalizeReceiveMode(raw.event_receive_mode, preset),
    auto_start_worker: raw.auto_start_worker === true,
    reply_identity: ["bot", "user"].includes(String(raw.reply_identity || "").trim().toLowerCase())
      ? String(raw.reply_identity || "").trim().toLowerCase()
      : "bot",
    project_id: String(raw.project_id || "").trim().slice(0, 80),
    guide_url: String(raw.guide_url || "").trim().slice(0, 500),
    sort_order: Math.min(999, Math.max(0, Number(raw.sort_order || 0) || 0)),
    display_name: String(raw.name || raw.agent_name || preset?.name || id || "机器人").trim(),
  };
}

const normalizedProjectOptions = computed(() =>
  Array.isArray(props.projectOptions)
    ? props.projectOptions
        .map((item) => ({
          value: String(item?.value || item?.id || "").trim(),
          label: String(item?.label || item?.name || "").trim(),
        }))
        .filter((item) => item.value && item.label)
    : [],
);

const projectLabelMap = computed(() =>
  normalizedProjectOptions.value.reduce((accumulator, item) => {
    accumulator[item.value] = item.label;
    return accumulator;
  }, {}),
);

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
      display_name: connector.name || connector.agent_name || `${preset.name || "机器人"}配置`,
      project_label:
        projectLabelMap.value[connector.project_id] ||
        connector.project_id ||
        "",
      connected: Boolean(
        connector.enabled &&
          connector.app_id &&
          connector.app_secret,
      ),
      event_url:
        connector.event_receive_mode === "long_connection"
          ? "长连接 worker"
          : connector.platform === "feishu" && connector.event_receive_mode === "http_callback"
            ? `/api/bot-events/feishu/${connector.id}/event`
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
    diagnosePayload.value = await api.post(`/bot-connectors/${encodeURIComponent(connectorId)}/diagnose`, {});
    diagnoseDialogVisible.value = true;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "机器人安装诊断失败");
  } finally {
    diagnosingConnectorId.value = "";
  }
}

function findProjectLabel(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) {
    return "";
  }
  return projectLabelMap.value[normalizedProjectId] || normalizedProjectId;
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
    name: `${source.name || source.agent_name || preset?.name || "机器人"} 副本`,
    sort_order: Math.min(999, Number(source.sort_order || 0) + 1),
  });
  await persistNextConnectors(
    [...normalizedConnectors.value, nextItem],
    "机器人配置已复制",
  );
}
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
