<template>
  <div class="project-deploy-panel">
    <ProjectWorkspaceBlock eyebrow="Deploy" title="部署配置">
      <template #actions>
        <div class="project-deploy-panel__actions">
          <el-button size="small" :loading="deployValidating" @click="validateDeploySettings">
            校验配置
          </el-button>
          <el-button
            type="primary"
            size="small"
            :disabled="!canManageProject"
            :loading="deploySaving"
            @click="saveDeploySettings"
          >
            保存配置
          </el-button>
        </div>
      </template>

      <div class="deploy-topbar">
        <el-switch v-model="deploySettingsForm.enabled" active-text="启用部署" />
        <el-select v-model="deploySettingsForm.default_profile" class="deploy-topbar__select">
          <el-option
            v-for="profile in deploySettingsForm.profiles"
            :key="profile.id"
            :label="profile.name || profile.id"
            :value="profile.id"
          />
        </el-select>
      </div>

      <div class="deploy-layout">
        <aside class="deploy-list">
          <div class="deploy-list__head">
            <span>环境档位</span>
            <el-button size="small" text @click="addDeployProfile">新增</el-button>
          </div>
          <button
            v-for="profile in deploySettingsForm.profiles"
            :key="profile.id"
            type="button"
            class="deploy-list__item"
            :class="{ 'is-active': profile.id === activeProfileId }"
            @click="selectDeployProfile(profile.id)"
          >
            <strong>{{ profile.name || profile.id }}</strong>
            <span>{{ profile.environment || profile.id }}</span>
          </button>
        </aside>

        <section v-if="activeProfile" class="deploy-editor">
          <div class="deploy-editor__header">
            <div>
              <strong>{{ activeProfile.name || activeProfile.id }}</strong>
              <span>{{ activeProfile.components.length }} 个部署单元</span>
            </div>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="deploySettingsForm.profiles.length <= 1"
              @click="removeDeployProfile(activeProfile.id)"
            >
              删除环境
            </el-button>
          </div>

          <el-form label-position="top" class="deploy-form">
            <div class="deploy-form__grid">
              <el-form-item label="档位 ID">
                <el-input v-model="activeProfile.id" @change="normalizeActiveProfileId" />
              </el-form-item>
              <el-form-item label="档位名称">
                <el-input v-model="activeProfile.name" />
              </el-form-item>
              <el-form-item label="运行环境">
                <el-input v-model="activeProfile.environment" />
              </el-form-item>
            </div>
          </el-form>

          <div class="deploy-subgrid">
            <aside class="deploy-list deploy-list--nested">
              <div class="deploy-list__head">
                <span>部署单元</span>
                <el-button size="small" text @click="addDeployComponent">新增</el-button>
              </div>
              <button
                v-for="component in activeProfile.components"
                :key="component.id"
                type="button"
                class="deploy-list__item"
                :class="{ 'is-active': component.id === activeComponentId }"
                @click="selectDeployComponent(component.id)"
              >
                <strong>{{ component.name || component.id }}</strong>
                <span>{{ component.targets.length }} 台服务器</span>
              </button>
            </aside>

            <section v-if="activeComponent" class="deploy-component">
              <div class="deploy-editor__header">
                <div>
                  <strong>{{ activeComponent.name || activeComponent.id }}</strong>
                  <span>{{ activeComponent.targets.length }} 台服务器</span>
                </div>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="activeProfile.components.length <= 1"
                  @click="removeDeployComponent(activeComponent.id)"
                >
                  删除单元
                </el-button>
              </div>

              <el-form label-position="top" class="deploy-form">
                <div class="deploy-form__grid">
                  <el-form-item label="单元 ID">
                    <el-input v-model="activeComponent.id" @change="normalizeActiveComponentId" />
                  </el-form-item>
                  <el-form-item label="单元名称">
                    <el-input v-model="activeComponent.name" />
                  </el-form-item>
                  <el-form-item label="自动执行部署命令">
                    <el-switch
                      v-model="activeComponent.safety.auto_deploy_on_artifact_update"
                      active-text="上传产物后执行"
                    />
                  </el-form-item>
                  <el-form-item label="通知">
                    <el-switch v-model="activeComponent.notify.enabled" />
                  </el-form-item>
                  <el-form-item label="通知平台">
                    <el-select
                      v-model="notifyTargetForm.platform"
                      style="width: 100%"
                      @change="onNotifyPlatformChange"
                    >
                      <el-option label="飞书" value="feishu" />
                      <el-option label="微信" value="wechat" />
                      <el-option label="QQ" value="qq" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="通知机器人">
                    <el-select
                      v-model="notifyTargetForm.connector_id"
                      :loading="deployNotifyOptionsLoading"
                      filterable
                      clearable
                      placeholder="选择机器人"
                      style="width: 100%"
                      @change="onNotifyConnectorChange"
                    >
                      <el-option
                        v-for="item in notifyConnectorOptions"
                        :key="item.id"
                        :label="item.label"
                        :value="item.id"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="通知群">
                    <el-select
                      v-model="notifyTargetForm.chat_id"
                      :loading="deployNotifyOptionsLoading"
                      filterable
                      clearable
                      placeholder="选择已识别群"
                      style="width: 100%"
                      @change="onNotifyChatChange"
                    >
                      <el-option
                        v-for="item in notifyChatOptions"
                        :key="item.chat_id"
                        :label="item.label"
                        :value="item.chat_id"
                      />
                    </el-select>
                  </el-form-item>
                </div>
                <div v-if="notifyTargetForm.platform === 'feishu'" class="deploy-notify-resolver">
                  <el-input
                    v-model="notifyChatName"
                    placeholder="输入飞书群名称"
                    clearable
                    @keyup.enter="resolveNotifyChatByName"
                  />
                  <el-button
                    :loading="deployNotifyResolving"
                    :disabled="!notifyTargetForm.connector_id || !notifyChatName.trim()"
                    @click="resolveNotifyChatByName"
                  >
                    解析群
                  </el-button>
                </div>
              </el-form>

              <div class="deploy-targets">
                <div class="deploy-targets__head">
                  <strong>服务器目标</strong>
                  <el-button size="small" @click="addDeployTarget">新增服务器</el-button>
                </div>
                <el-table :data="activeComponent.targets" stripe class="section-table">
                  <el-table-column label="启用" width="78">
                    <template #default="{ row }">
                      <el-switch v-model="row.enabled" />
                    </template>
                  </el-table-column>
                  <el-table-column label="名称" min-width="140">
                    <template #default="{ row }">
                      <el-input v-model="row.name" size="small" />
                    </template>
                  </el-table-column>
                  <el-table-column label="方式" width="90">
                    <template #default>
                      <el-tag size="small" effect="plain">FTP</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="FTP 连接" min-width="260">
                    <template #default="{ row }">
                      <el-select
                        v-model="row.ftp_credential_id"
                        size="small"
                        filterable
                        placeholder="选择全局 FTP 连接"
                        class="deploy-targets__credential-select"
                      >
                        <el-option
                          v-for="credential in ftpCredentialOptions"
                          :key="credential.id"
                          :label="credential.label"
                          :value="credential.id"
                          :disabled="credential.enabled === false"
                        />
                      </el-select>
                    </template>
                  </el-table-column>
                  <el-table-column label="远端目录" min-width="180">
                    <template #default="{ row }">
                      <el-input v-model="row.remote_path" size="small" placeholder="/opt/app/releases" />
                    </template>
                  </el-table-column>
                  <el-table-column label="部署命令" min-width="220">
                    <template #default="{ row, $index }">
                      <div class="deploy-targets__command-cell">
                        <el-input v-model="row.deploy_command" size="small" placeholder="./deploy.sh up" />
                        <el-button
                          size="small"
                          :loading="deployCommandGeneratingKey === deployTargetRowKey(row, $index)"
                          :disabled="!canManageProject"
                          @click="generateDeployCommand(row, $index)"
                        >
                          AI 生成
                        </el-button>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="82" fixed="right">
                    <template #default="{ $index }">
                      <el-button
                        size="small"
                        type="danger"
                        text
                        :disabled="activeComponent.targets.length <= 1"
                        @click="removeDeployTarget($index)"
                      >
                        删除
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </section>
          </div>
        </section>
      </div>

      <div v-if="deployValidation" class="project-deploy-panel__validation">
        <el-alert
          :title="deployValidation.valid ? '部署配置校验通过' : '部署配置仍需补充'"
          :type="deployValidation.valid ? 'success' : 'warning'"
          :closable="false"
          show-icon
        />
        <ul v-if="deployValidation.issues?.length">
          <li v-for="issue in deployValidation.issues" :key="`${issue.path}-${issue.message}`">
            <span>{{ issue.message }}</span>
          </li>
        </ul>
      </div>
    </ProjectWorkspaceBlock>

    <ProjectWorkspaceBlock eyebrow="Artifacts" title="部署产物">
      <template #actions>
        <el-button
          size="small"
          :loading="deployArtifactsLoading || deployRunsLoading"
          @click="refreshDeployStatus"
        >
          刷新状态
        </el-button>
      </template>
      <el-table v-loading="deployArtifactsLoading" :data="deployArtifacts" stripe class="section-table">
        <el-table-column label="产物" min-width="240">
          <template #default="{ row }">
            <div class="project-deploy-panel__table-main">
              <strong>{{ row.artifact_name || row.id }}</strong>
              <span>{{ row.version || "未标记版本" }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="环境" width="120">
          <template #default="{ row }">
            <el-tag effect="plain" type="info">{{ row.profile || "-" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="部署单元" width="130">
          <template #default="{ row }">{{ row.component || "-" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="getDeployStatusTagType(row.status)">
              {{ getDeployStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="120">
          <template #default="{ row }">{{ formatFileSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="上传时间" min-width="150">
          <template #default="{ row }">{{ formatRelativeTime(row.uploaded_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <div class="project-deploy-panel__row-actions">
              <el-button
                text
                type="primary"
                :loading="deployingArtifactId === row.id"
                :disabled="!canManageProject || deletingArtifactId === row.id"
                @click="deployArtifact(row)"
              >
                部署
              </el-button>
              <el-popconfirm
                title="确定删除这个打包产物文件吗？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="deleteDeployArtifact(row)"
              >
                <template #reference>
                  <el-button
                    text
                    type="danger"
                    :loading="deletingArtifactId === row.id"
                    :disabled="!canManageProject || deployingArtifactId === row.id"
                  >
                    删除
                  </el-button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!deployArtifactsLoading && !deployArtifacts.length"
        description="暂无部署产物"
        :image-size="60"
      />
    </ProjectWorkspaceBlock>

    <ProjectWorkspaceBlock eyebrow="Runs" title="部署运行">
      <el-table v-loading="deployRunsLoading" :data="deployRuns" stripe class="section-table">
        <el-table-column label="运行 ID" min-width="180">
          <template #default="{ row }">
            <code>{{ row.id }}</code>
          </template>
        </el-table-column>
        <el-table-column label="环境" width="110">
          <template #default="{ row }">{{ row.profile || "-" }}</template>
        </el-table-column>
        <el-table-column label="部署单元" width="130">
          <template #default="{ row }">{{ row.component || "-" }}</template>
        </el-table-column>
        <el-table-column label="阶段" min-width="180">
          <template #default="{ row }">
            <div class="project-deploy-panel__table-main">
              <strong>{{ getDeployStatusLabel(row.status) }}</strong>
              <span>{{ row.stage || "-" }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="通知" min-width="170">
          <template #default="{ row }">
            <div class="project-deploy-panel__notify-tags">
              <el-tag
                v-for="item in row.notify_result || []"
                :key="`${item.platform}-${item.chat_id}`"
                size="small"
                effect="plain"
                :type="item.status === 'preview' ? 'success' : 'info'"
              >
                {{ getDeployNotifyLabel(item) }}
              </el-tag>
              <span v-if="!row.notify_result?.length">-</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="日志摘要" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.log_excerpt || "-" }}</template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="150">
          <template #default="{ row }">{{ formatRelativeTime(row.updated_at) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!deployRunsLoading && !deployRuns.length" description="暂无部署运行记录" :image-size="60" />
    </ProjectWorkspaceBlock>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import ProjectWorkspaceBlock from "@/components/project-workspace/ProjectWorkspaceBlock.vue";
import api from "@/utils/api.js";

const props = defineProps({
  projectId: {
    type: String,
    required: true,
  },
  project: {
    type: Object,
    default: () => ({}),
  },
  canManageProject: {
    type: Boolean,
    default: false,
  },
  manageBlockedMessage: {
    type: String,
    default: "仅项目创建者可编辑",
  },
});

const emit = defineEmits(["project-updated"]);

const deploySaving = ref(false);
const deployValidating = ref(false);
const deployArtifactsLoading = ref(false);
const deployRunsLoading = ref(false);
const ftpCredentialsLoading = ref(false);
const deployNotifyOptionsLoading = ref(false);
const deployNotifyResolving = ref(false);
const deployCommandGeneratingKey = ref("");
const deletingArtifactId = ref("");
const deployingArtifactId = ref("");
const deployArtifacts = ref([]);
const deployRuns = ref([]);
const ftpCredentials = ref([]);
const deployNotifyConnectors = ref([]);
const deployNotifyChats = ref([]);
const deployValidation = ref(null);
const deploySettingsForm = ref(createDefaultDeploySettings());
const activeProfileId = ref("prod");
const activeComponentId = ref("app");
const activeProfileObject = ref(null);
const activeComponentObject = ref(null);
const notifyTargetForm = ref(createDefaultDeployNotifyTarget());
const notifyChatName = ref("");

const activeProfile = computed(() => {
  const profiles = deploySettingsForm.value.profiles || [];
  return profiles.find((profile) => profile.id === activeProfileId.value)
    || (profiles.includes(activeProfileObject.value) ? activeProfileObject.value : null);
});

const activeComponent = computed(() => {
  const components = activeProfile.value?.components || [];
  return components.find((component) => component.id === activeComponentId.value)
    || (components.includes(activeComponentObject.value) ? activeComponentObject.value : null);
});

const ftpCredentialOptions = computed(() =>
  ftpCredentials.value
    .map((item) => ({
      id: String(item?.id || "").trim(),
      label: [
        String(item?.name || item?.id || "").trim(),
        String(item?.host || "").trim()
          ? `${String(item.host).trim()}${item?.port ? `:${String(item.port).trim()}` : ""}`
          : "",
        item?.username ? `账号 ${item.username}` : "",
      ].filter(Boolean).join(" · "),
      enabled: item?.enabled !== false,
    }))
    .filter((item) => item.id && item.label),
);

const notifyConnectorOptions = computed(() =>
  deployNotifyConnectors.value
    .filter((item) => item.platform === notifyTargetForm.value.platform)
    .map((item) => ({
      ...item,
      label: [
        String(item.name || item.id || "").trim(),
        String(item.agent_name || "").trim(),
      ].filter(Boolean).join(" · "),
    }))
    .filter((item) => item.id && item.label),
);

const notifyChatOptions = computed(() =>
  deployNotifyChats.value
    .filter((item) =>
      item.platform === notifyTargetForm.value.platform
      && item.connector_id === notifyTargetForm.value.connector_id
    )
    .map((item) => ({
      ...item,
      label: [
        String(item.chat_name || "").trim(),
        String(item.chat_id || "").trim(),
      ].filter(Boolean).join(" · "),
    }))
    .filter((item) => item.chat_id && item.label),
);

const selectedNotifyConnector = computed(() =>
  deployNotifyConnectors.value.find((item) =>
    item.platform === notifyTargetForm.value.platform
    && item.id === notifyTargetForm.value.connector_id
  ) || null,
);

function formatRelativeTime(isoString) {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "";
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatFileSize(value) {
  const size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let current = size;
  let unitIndex = 0;
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024;
    unitIndex += 1;
  }
  const precision = unitIndex === 0 || current >= 10 ? 0 : 1;
  return `${current.toFixed(precision)} ${units[unitIndex]}`;
}

function safeId(value, fallback) {
  return String(value || "").trim().replace(/\s+/g, "-") || fallback;
}

function createDefaultDeployNotifyTarget() {
  return {
    platform: "feishu",
    connector_id: "",
    chat_id: "",
    chat_name: "",
    resolve_identity: "bot",
  };
}

function createDefaultDeployTarget(index = 1) {
  return {
    id: `target-${index}`,
    name: `服务器 ${index}`,
    enabled: true,
    transport_mode: "ftp",
    ftp_credential_id: "",
    remote_path: "",
    deploy_command: "",
    health_check: {},
  };
}

function createDefaultDeployComponent() {
  return {
    id: "app",
    name: "默认服务",
    enabled: true,
    artifact_kind: "source-bundle",
    package: {},
    safety: {
      auto_deploy_on_artifact_update: false,
      dry_run_default: false,
    },
    notify: {
      enabled: false,
      targets: [],
    },
    targets: [createDefaultDeployTarget()],
  };
}

function createDefaultDeployProfile() {
  return {
    id: "prod",
    name: "生产环境",
    environment: "prod",
    artifact_kind: "source-bundle",
    enabled: true,
    package: {},
    transport: {},
    remote_executor: {},
    notify: { enabled: false, targets: [] },
    safety: { auto_deploy_on_artifact_update: false, dry_run_default: false },
    components: [createDefaultDeployComponent()],
  };
}

function createDefaultDeploySettings() {
  return {
    version: "2",
    enabled: false,
    default_profile: "prod",
    profiles: [createDefaultDeployProfile()],
  };
}

function normalizeDeployNotifyTarget(item) {
  const source = item && typeof item === "object" ? item : {};
  return {
    ...createDefaultDeployNotifyTarget(),
    ...source,
    platform: String(source.platform || "feishu").trim(),
    connector_id: String(source.connector_id || "").trim(),
    chat_id: String(source.chat_id || "").trim(),
    chat_name: String(source.chat_name || "").trim(),
    resolve_identity: String(source.resolve_identity || "bot").trim(),
  };
}

function normalizeDeployTarget(item, index = 0) {
  const source = item && typeof item === "object" ? item : {};
  const transport = source.transport && typeof source.transport === "object" ? source.transport : {};
  const remoteExecutor = source.remote_executor && typeof source.remote_executor === "object" ? source.remote_executor : {};
  return {
    ...createDefaultDeployTarget(index + 1),
    ...source,
    id: safeId(source.id, `target-${index + 1}`),
    name: String(source.name || source.id || `服务器 ${index + 1}`).trim(),
    enabled: true,
    transport_mode: "ftp",
    ftp_credential_id: String(source.ftp_credential_id || source.ftpCredentialId || transport.ftp_credential_id || "").trim(),
    remote_path: String(source.remote_path || transport.remote_path || "").trim(),
    deploy_command: String(source.deploy_command || remoteExecutor.deploy_command || "").trim(),
    health_check: source.health_check && typeof source.health_check === "object" ? { ...source.health_check } : {},
  };
}

function normalizeDeployComponent(item, index = 0, legacyProfile = null) {
  const source = item && typeof item === "object" ? item : {};
  const legacy = legacyProfile && typeof legacyProfile === "object" ? legacyProfile : {};
  const rawTargets = Array.isArray(source.targets) ? source.targets : [];
  const targets = rawTargets.length
    ? rawTargets.map((target, targetIndex) => normalizeDeployTarget(target, targetIndex))
    : [normalizeDeployTarget({
        id: "primary",
        name: "主服务器",
        transport: legacy.transport,
        remote_executor: legacy.remote_executor,
      })];
  const notify = source.notify && typeof source.notify === "object" ? source.notify : legacy.notify || {};
  const safety = source.safety && typeof source.safety === "object" ? source.safety : legacy.safety || {};
  return {
    ...createDefaultDeployComponent(),
    ...source,
    id: safeId(source.id, index === 0 ? "app" : `component-${index + 1}`),
    name: String(source.name || source.id || (index === 0 ? "默认服务" : `部署单元 ${index + 1}`)).trim(),
    enabled: true,
    artifact_kind: String(source.artifact_kind || legacy.artifact_kind || "source-bundle").trim(),
    package: source.package && typeof source.package === "object" ? { ...source.package } : {},
    safety: {
      ...createDefaultDeployComponent().safety,
      ...safety,
      auto_deploy_on_artifact_update: Boolean(safety.auto_deploy_on_artifact_update),
      dry_run_default: Boolean(safety.dry_run_default),
    },
    notify: {
      enabled: Boolean(notify.enabled),
      targets: Array.isArray(notify.targets)
        ? notify.targets.map((target) => normalizeDeployNotifyTarget(target))
        : [],
    },
    targets,
  };
}

function normalizeDeployProfile(item, index = 0) {
  const source = item && typeof item === "object" ? item : {};
  const rawComponents = Array.isArray(source.components) ? source.components : [];
  const components = rawComponents.length
    ? rawComponents.map((component, componentIndex) => normalizeDeployComponent(component, componentIndex))
    : [normalizeDeployComponent({}, 0, source)];
  return {
    ...createDefaultDeployProfile(),
    ...source,
    id: safeId(source.id, index === 0 ? "prod" : `profile-${index + 1}`),
    name: String(source.name || source.id || (index === 0 ? "生产环境" : `环境 ${index + 1}`)).trim(),
    environment: String(source.environment || source.id || (index === 0 ? "prod" : `env-${index + 1}`)).trim(),
    enabled: source.enabled !== false,
    components,
  };
}

function normalizeDeploySettings(item) {
  const fallback = createDefaultDeploySettings();
  const source = item && typeof item === "object" ? item : {};
  const profiles = Array.isArray(source.profiles)
    ? source.profiles.map((profile, index) => normalizeDeployProfile(profile, index))
    : [];
  const nextProfiles = profiles.length ? profiles : [createDefaultDeployProfile()];
  const defaultProfile = String(source.default_profile || "").trim() || nextProfiles[0].id || "prod";
  return {
    ...fallback,
    ...source,
    version: "2",
    enabled: Boolean(source.enabled),
    default_profile: defaultProfile,
    profiles: nextProfiles,
  };
}

function syncDeployFormsFromSettings(rawSettings) {
  const settings = normalizeDeploySettings(rawSettings);
  deploySettingsForm.value = settings;
  activeProfileId.value = settings.profiles.some((profile) => profile.id === activeProfileId.value)
    ? activeProfileId.value
    : settings.default_profile || settings.profiles[0].id;
  const profile = activeProfile.value || settings.profiles[0];
  activeProfileObject.value = profile;
  activeComponentId.value = profile.components.some((component) => component.id === activeComponentId.value)
    ? activeComponentId.value
    : profile.components[0]?.id || "app";
  activeComponentObject.value = profile.components.find((component) => component.id === activeComponentId.value)
    || profile.components[0]
    || null;
  syncNotifyTargetForm();
}

function syncNotifyTargetForm() {
  notifyTargetForm.value = normalizeDeployNotifyTarget(activeComponent.value?.notify?.targets?.[0]);
  notifyChatName.value = notifyTargetForm.value.chat_name || getNotifyChatName(notifyTargetForm.value.chat_id);
}

function applyNotifyTargetToActiveComponent() {
  if (!activeComponent.value) return;
  const target = normalizeDeployNotifyTarget(notifyTargetForm.value);
  activeComponent.value.notify.targets =
    activeComponent.value.notify.enabled && target.platform && (target.connector_id || target.chat_id)
      ? [target]
      : [];
}

function normalizeDeployNotifyConnector(item) {
  const source = item && typeof item === "object" ? item : {};
  return {
    id: String(source.id || "").trim(),
    platform: String(source.platform || "").trim(),
    name: String(source.name || source.id || "").trim(),
    agent_name: String(source.agent_name || "").trim(),
    description: String(source.description || "").trim(),
    reply_identity: String(source.reply_identity || "bot").trim(),
    project_id: String(source.project_id || "").trim(),
  };
}

function normalizeDeployNotifyChat(item) {
  const source = item && typeof item === "object" ? item : {};
  return {
    platform: String(source.platform || "").trim(),
    connector_id: String(source.connector_id || "").trim(),
    chat_id: String(source.chat_id || "").trim(),
    chat_name: String(source.chat_name || "").trim(),
    session_id: String(source.session_id || "").trim(),
    source_type: String(source.source_type || "").trim(),
    chat_type: String(source.chat_type || "").trim(),
    scanned_at: String(source.scanned_at || "").trim(),
  };
}

function getNotifyChatName(chatId) {
  const normalized = String(chatId || "").trim();
  if (!normalized) return "";
  const match = deployNotifyChats.value.find((item) =>
    item.platform === notifyTargetForm.value.platform
    && item.connector_id === notifyTargetForm.value.connector_id
    && item.chat_id === normalized
  );
  return match?.chat_name || "";
}

function upsertNotifyChat(chat) {
  const item = normalizeDeployNotifyChat(chat);
  if (!item.platform || !item.connector_id || !item.chat_id) return;
  const index = deployNotifyChats.value.findIndex((current) =>
    current.platform === item.platform
    && current.connector_id === item.connector_id
    && current.chat_id === item.chat_id
  );
  if (index >= 0) {
    deployNotifyChats.value[index] = { ...deployNotifyChats.value[index], ...item };
  } else {
    deployNotifyChats.value.unshift(item);
  }
}

function onNotifyPlatformChange() {
  notifyTargetForm.value.connector_id = "";
  notifyTargetForm.value.chat_id = "";
  notifyTargetForm.value.chat_name = "";
  notifyTargetForm.value.resolve_identity = "bot";
  notifyChatName.value = "";
  applyNotifyTargetToActiveComponent();
}

function onNotifyConnectorChange() {
  const connector = selectedNotifyConnector.value;
  notifyTargetForm.value.chat_id = "";
  notifyTargetForm.value.chat_name = "";
  notifyTargetForm.value.resolve_identity = connector?.reply_identity || "bot";
  notifyChatName.value = "";
  applyNotifyTargetToActiveComponent();
}

function onNotifyChatChange(value) {
  const chatName = getNotifyChatName(value);
  notifyTargetForm.value.chat_name = chatName;
  notifyChatName.value = chatName;
  applyNotifyTargetToActiveComponent();
}

function buildDeploySettingsPayload() {
  applyNotifyTargetToActiveComponent();
  return normalizeDeploySettings(deploySettingsForm.value);
}

function firstDeployValidationMessage() {
  const issue = Array.isArray(deployValidation.value?.issues) ? deployValidation.value.issues[0] : null;
  return issue?.message || "部署配置未通过校验，请补齐标出的字段";
}

function selectDeployProfile(profileId) {
  applyNotifyTargetToActiveComponent();
  const profile = deploySettingsForm.value.profiles.find((item) => item.id === profileId);
  if (!profile) return;
  activeProfileId.value = profile.id;
  activeProfileObject.value = profile;
  activeComponentObject.value = profile.components?.[0] || null;
  activeComponentId.value = activeComponentObject.value?.id || "app";
  syncNotifyTargetForm();
}

function selectDeployComponent(componentId) {
  applyNotifyTargetToActiveComponent();
  const component = activeProfile.value?.components?.find((item) => item.id === componentId);
  if (!component) return;
  activeComponentId.value = component.id;
  activeComponentObject.value = component;
  syncNotifyTargetForm();
}

function addDeployProfile() {
  const index = deploySettingsForm.value.profiles.length + 1;
  const profile = normalizeDeployProfile({ id: `env-${index}`, name: `环境 ${index}`, environment: `env-${index}` }, index);
  deploySettingsForm.value.profiles.push(profile);
  selectDeployProfile(profile.id);
}

function removeDeployProfile(profileId) {
  if (deploySettingsForm.value.profiles.length <= 1) return;
  deploySettingsForm.value.profiles = deploySettingsForm.value.profiles.filter((profile) => profile.id !== profileId);
  if (deploySettingsForm.value.default_profile === profileId) {
    deploySettingsForm.value.default_profile = deploySettingsForm.value.profiles[0]?.id || "prod";
  }
  selectDeployProfile(deploySettingsForm.value.default_profile);
}

function addDeployComponent() {
  if (!activeProfile.value) return;
  const index = activeProfile.value.components.length + 1;
  const component = normalizeDeployComponent({ id: `component-${index}`, name: `部署单元 ${index}` }, index);
  activeProfile.value.components.push(component);
  selectDeployComponent(component.id);
}

function removeDeployComponent(componentId) {
  if (!activeProfile.value || activeProfile.value.components.length <= 1) return;
  activeProfile.value.components = activeProfile.value.components.filter((component) => component.id !== componentId);
  selectDeployComponent(activeProfile.value.components[0]?.id || "app");
}

function addDeployTarget() {
  if (!activeComponent.value) return;
  activeComponent.value.targets.push(createDefaultDeployTarget(activeComponent.value.targets.length + 1));
}

function removeDeployTarget(index) {
  if (!activeComponent.value || activeComponent.value.targets.length <= 1) return;
  activeComponent.value.targets.splice(index, 1);
}

function deployTargetRowKey(row, index = 0) {
  return [
    String(activeProfileId.value || "").trim(),
    String(activeComponentId.value || "").trim(),
    String(row?.id || index).trim(),
  ].join(":");
}

async function generateDeployCommand(row, index = 0) {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  if (!props.projectId || !activeProfile.value || !activeComponent.value || !row) return;
  const rowKey = deployTargetRowKey(row, index);
  deployCommandGeneratingKey.value = rowKey;
  try {
    const data = await api.post(`/projects/${props.projectId}/deploy-command/generate`, {
      profile: {
        id: activeProfile.value.id,
        name: activeProfile.value.name,
        environment: activeProfile.value.environment,
      },
      component: {
        id: activeComponent.value.id,
        name: activeComponent.value.name,
        artifact_kind: activeComponent.value.artifact_kind,
        package: activeComponent.value.package || {},
        safety: activeComponent.value.safety || {},
      },
      target: {
        id: row.id,
        name: row.name,
        remote_path: row.remote_path,
        deploy_command: row.deploy_command,
      },
      artifact_kind: activeComponent.value.artifact_kind || activeProfile.value.artifact_kind || "source-bundle",
      artifact_path: String(
        activeComponent.value.package?.artifact_path || activeComponent.value.package?.output_path || "",
      ).trim(),
    });
    row.deploy_command = String(data?.deploy_command || "").trim();
    ElMessage.success("部署命令已生成，保存配置后后续部署会直接复用");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "AI 生成部署命令失败");
  } finally {
    deployCommandGeneratingKey.value = "";
  }
}

function normalizeActiveProfileId() {
  const profile = activeProfile.value;
  if (!profile) return;
  const wasDefault = deploySettingsForm.value.default_profile === activeProfileId.value;
  profile.id = safeId(profile.id, "prod");
  activeProfileId.value = profile.id;
  activeProfileObject.value = profile;
  if (wasDefault || !deploySettingsForm.value.default_profile) {
    deploySettingsForm.value.default_profile = profile.id;
  }
}

function normalizeActiveComponentId() {
  const component = activeComponent.value;
  if (!component) return;
  component.id = safeId(component.id, "app");
  activeComponentId.value = component.id;
  activeComponentObject.value = component;
}

function normalizeDeployArtifact(item) {
  return {
    id: String(item?.id || "").trim(),
    project_id: String(item?.project_id || "").trim(),
    profile: String(item?.profile || "").trim(),
    component: String(item?.component || "").trim(),
    artifact_name: String(item?.artifact_name || "").trim(),
    artifact_kind: String(item?.artifact_kind || "").trim(),
    version: String(item?.version || "").trim(),
    checksum: String(item?.checksum || "").trim(),
    size: Number(item?.size || 0),
    status: String(item?.status || "").trim(),
    uploaded_at: String(item?.uploaded_at || "").trim(),
  };
}

function normalizeDeployRun(item) {
  return {
    id: String(item?.id || "").trim(),
    profile: String(item?.profile || "").trim(),
    component: String(item?.component || "").trim(),
    status: String(item?.status || "").trim(),
    stage: String(item?.stage || "").trim(),
    log_excerpt: String(item?.log_excerpt || "").trim(),
    notify_result: Array.isArray(item?.notify_result) ? item.notify_result : [],
    updated_at: String(item?.updated_at || "").trim(),
  };
}

async function fetchDeployArtifacts() {
  if (!props.projectId) {
    deployArtifacts.value = [];
    return;
  }
  deployArtifactsLoading.value = true;
  try {
    const data = await api.get(`/projects/${props.projectId}/deploy-artifacts`);
    deployArtifacts.value = (data.artifacts || [])
      .map((item) => normalizeDeployArtifact(item))
      .filter((item) => item.id);
  } catch (err) {
    deployArtifacts.value = [];
    ElMessage.error(err?.detail || err?.message || "加载部署产物失败");
  } finally {
    deployArtifactsLoading.value = false;
  }
}

async function deleteDeployArtifact(row) {
  const artifactId = String(row?.id || "").trim();
  if (!artifactId || !props.projectId) {
    return;
  }
  deletingArtifactId.value = artifactId;
  try {
    await api.delete(`/projects/${props.projectId}/deploy-artifacts/${encodeURIComponent(artifactId)}`);
    deployArtifacts.value = deployArtifacts.value.filter((item) => item.id !== artifactId);
    ElMessage.success("打包产物文件已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除打包产物失败");
  } finally {
    deletingArtifactId.value = "";
  }
}

async function deployArtifact(row) {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  const artifactId = String(row?.id || "").trim();
  if (!artifactId || !props.projectId) {
    return;
  }
  deployingArtifactId.value = artifactId;
  try {
    const data = await api.post(
      `/projects/${props.projectId}/deploy-artifacts/${encodeURIComponent(artifactId)}/deploy`,
      {},
    );
    const status = String(data?.deployment?.status || data?.status || "").trim().toLowerCase();
    const statusLabel = getDeployStatusLabel(status);
    if (status === "failed") {
      ElMessage.error(`部署失败：${statusLabel}`);
    } else if (status === "blocked") {
      ElMessage.warning(`部署已阻塞：${statusLabel}`);
    } else {
      ElMessage.success(`已触发部署：${statusLabel}`);
    }
    await Promise.all([fetchDeployArtifacts(), fetchDeployRuns()]);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "触发部署失败");
  } finally {
    deployingArtifactId.value = "";
  }
}

async function fetchDeployRuns() {
  if (!props.projectId) {
    deployRuns.value = [];
    return;
  }
  deployRunsLoading.value = true;
  try {
    const data = await api.get(`/projects/${props.projectId}/deploy-runs`);
    deployRuns.value = (data.runs || []).map((item) => normalizeDeployRun(item)).filter((item) => item.id);
  } catch (err) {
    deployRuns.value = [];
    ElMessage.error(err?.detail || err?.message || "加载部署运行失败");
  } finally {
    deployRunsLoading.value = false;
  }
}

async function fetchFtpCredentials() {
  ftpCredentialsLoading.value = true;
  try {
    const data = await api.get("/ftp-credentials");
    ftpCredentials.value = Array.isArray(data?.items) ? data.items : [];
  } catch (err) {
    ftpCredentials.value = [];
    ElMessage.error(err?.detail || err?.message || "加载 FTP 连接失败");
  } finally {
    ftpCredentialsLoading.value = false;
  }
}

async function fetchDeployNotifyOptions() {
  if (!props.projectId) {
    deployNotifyConnectors.value = [];
    deployNotifyChats.value = [];
    return;
  }
  deployNotifyOptionsLoading.value = true;
  try {
    const data = await api.get(`/projects/${props.projectId}/deploy-notify-options`);
    deployNotifyConnectors.value = Array.isArray(data?.connectors)
      ? data.connectors.map((item) => normalizeDeployNotifyConnector(item)).filter((item) => item.id)
      : [];
    deployNotifyChats.value = Array.isArray(data?.chats)
      ? data.chats.map((item) => normalizeDeployNotifyChat(item)).filter((item) => item.chat_id)
      : [];
    if (notifyTargetForm.value.chat_id && !notifyTargetForm.value.chat_name) {
      notifyTargetForm.value.chat_name = getNotifyChatName(notifyTargetForm.value.chat_id);
      notifyChatName.value = notifyTargetForm.value.chat_name;
    }
  } catch (err) {
    deployNotifyConnectors.value = [];
    deployNotifyChats.value = [];
    ElMessage.error(err?.detail || err?.message || "加载通知机器人失败");
  } finally {
    deployNotifyOptionsLoading.value = false;
  }
}

async function refreshDeployStatus() {
  await Promise.all([fetchDeployArtifacts(), fetchDeployRuns(), fetchFtpCredentials(), fetchDeployNotifyOptions()]);
}

async function resolveNotifyChatByName() {
  if (!props.projectId || notifyTargetForm.value.platform !== "feishu") return;
  const chatName = notifyChatName.value.trim();
  if (!notifyTargetForm.value.connector_id) {
    ElMessage.warning("请先选择通知机器人");
    return;
  }
  if (!chatName) {
    ElMessage.warning("请输入飞书群名称");
    return;
  }
  deployNotifyResolving.value = true;
  try {
    const connector = selectedNotifyConnector.value;
    const data = await api.post(`/projects/${props.projectId}/deploy-notify-chat/resolve`, {
      platform: notifyTargetForm.value.platform,
      connector_id: notifyTargetForm.value.connector_id,
      chat_name: chatName,
      identity: connector?.reply_identity || notifyTargetForm.value.resolve_identity || "bot",
    });
    const chat = normalizeDeployNotifyChat(data?.chat);
    upsertNotifyChat(chat);
    notifyTargetForm.value.chat_id = chat.chat_id;
    notifyTargetForm.value.chat_name = chat.chat_name || chatName;
    notifyTargetForm.value.resolve_identity = data?.chat?.resolve_identity || connector?.reply_identity || "bot";
    notifyChatName.value = notifyTargetForm.value.chat_name;
    applyNotifyTargetToActiveComponent();
    await fetchDeployNotifyOptions();
    ElMessage.success("飞书群已解析");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "解析飞书群失败");
  } finally {
    deployNotifyResolving.value = false;
  }
}

async function validateDeploySettings() {
  if (!props.projectId) return false;
  deployValidating.value = true;
  try {
    const data = await api.post(`/projects/${props.projectId}/deploy-settings/validate`, {
      deploy_settings: buildDeploySettingsPayload(),
    });
    deployValidation.value = {
      valid: Boolean(data?.valid),
      issues: Array.isArray(data?.issues) ? data.issues : [],
    };
    ElMessage[deployValidation.value.valid ? "success" : "warning"](
      deployValidation.value.valid ? "部署配置校验通过" : firstDeployValidationMessage(),
    );
    return deployValidation.value.valid;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "校验部署配置失败");
    return false;
  } finally {
    deployValidating.value = false;
  }
}

async function saveDeploySettings() {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  if (!props.projectId) return;
  deploySaving.value = true;
  try {
    const payload = buildDeploySettingsPayload();
    const validation = await api.post(`/projects/${props.projectId}/deploy-settings/validate`, {
      deploy_settings: payload,
    });
    deployValidation.value = {
      valid: Boolean(validation?.valid),
      issues: Array.isArray(validation?.issues) ? validation.issues : [],
    };
    if (!deployValidation.value.valid) {
      ElMessage.warning(firstDeployValidationMessage());
      return;
    }
    await api.put(`/projects/${props.projectId}`, { deploy_settings: payload });
    ElMessage.success("部署配置已保存");
    emit("project-updated");
    await refreshDeployStatus();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存部署配置失败");
  } finally {
    deploySaving.value = false;
  }
}

function getDeployStatusTagType(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (["ready", "queued", "deploy_queued"].includes(normalized)) return "success";
  if (["failed", "blocked"].includes(normalized)) return "danger";
  if (["uploading", "running"].includes(normalized)) return "warning";
  return "info";
}

function getDeployStatusLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "uploading") return "上传中";
  if (normalized === "ready") return "已就绪";
  if (normalized === "queued" || normalized === "deploy_queued") return "已排队";
  if (normalized === "running") return "执行中";
  if (normalized === "blocked") return "已阻塞";
  if (normalized === "failed") return "失败";
  return String(value || "未知").trim() || "未知";
}

function getDeployNotifyLabel(item) {
  const platform = String(item?.platform || "").trim() || "unknown";
  const status = String(item?.status || "").trim() || "pending";
  return `${platform} · ${status}`;
}

watch(
  () => props.project?.deploy_settings,
  (settings) => {
    syncDeployFormsFromSettings(settings || {});
  },
  { immediate: true },
);

watch(activeComponentId, () => {
  syncNotifyTargetForm();
});

watch(
  () => props.projectId,
  () => {
    deployValidation.value = null;
    void refreshDeployStatus();
  },
);

onMounted(() => {
  void refreshDeployStatus();
});
</script>

<style scoped>
.project-deploy-panel {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.project-deploy-panel__actions,
.project-deploy-panel__notify-tags,
.deploy-topbar,
.deploy-targets__head,
.deploy-editor__header,
.deploy-list__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.project-deploy-panel__actions,
.project-deploy-panel__notify-tags {
  flex-wrap: wrap;
}

.deploy-topbar {
  justify-content: space-between;
  margin-top: 10px;
}

.deploy-topbar__select {
  width: 220px;
}

.deploy-layout,
.deploy-subgrid {
  display: grid;
  gap: 16px;
  margin-top: 16px;
}

.deploy-layout {
  grid-template-columns: 220px minmax(0, 1fr);
}

.deploy-subgrid {
  grid-template-columns: 190px minmax(0, 1fr);
}

.deploy-list,
.deploy-editor,
.deploy-component {
  min-width: 0;
}

.deploy-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.deploy-list__head,
.deploy-editor__header,
.deploy-targets__head {
  justify-content: space-between;
}

.deploy-list__head {
  color: #475569;
  font-size: 13px;
  font-weight: 600;
}

.deploy-list__item {
  display: grid;
  gap: 4px;
  width: 100%;
  min-height: 54px;
  padding: 9px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  color: #0f172a;
  text-align: left;
  cursor: pointer;
}

.deploy-list__item.is-active {
  border-color: #2563eb;
  background: #eff6ff;
}

.deploy-list__item strong,
.deploy-list__item span,
.deploy-editor__header strong,
.deploy-editor__header span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deploy-list__item span,
.deploy-editor__header span {
  color: #64748b;
  font-size: 12px;
}

.deploy-editor,
.deploy-component {
  display: grid;
  gap: 14px;
}

.deploy-editor__header {
  min-height: 42px;
}

.deploy-editor__header > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.deploy-form__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  column-gap: 14px;
}

.deploy-notify-resolver {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  max-width: 520px;
}

.deploy-targets {
  display: grid;
  gap: 8px;
}

.deploy-targets__credential-select {
  width: 100%;
}

.deploy-targets__command-cell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.project-deploy-panel__validation {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.project-deploy-panel__validation ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 12px 14px;
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 8px;
  background: rgba(255, 251, 235, 0.72);
  list-style: none;
}

.project-deploy-panel__validation li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #92400e;
  font-size: 13px;
  line-height: 1.5;
}

.section-table {
  margin-top: 8px;
  width: 100%;
}

.project-deploy-panel :deep(.el-table),
.project-deploy-panel :deep(.el-table__inner-wrapper) {
  border-radius: 8px;
  overflow: hidden;
  width: 100%;
}

.project-deploy-panel :deep(.el-table th.el-table__cell) {
  height: 48px;
  background: rgba(248, 250, 252, 0.9);
  color: #475569;
}

.project-deploy-panel :deep(.el-table td.el-table__cell) {
  padding-top: 10px;
  padding-bottom: 10px;
}

.project-deploy-panel :deep(.el-table .cell) {
  min-width: 0;
}

.project-deploy-panel__table-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.project-deploy-panel__table-main strong,
.project-deploy-panel__table-main span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-deploy-panel__table-main strong {
  color: #0f172a;
  font-weight: 600;
}

.project-deploy-panel__table-main span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.project-deploy-panel__row-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

@media (max-width: 980px) {
  .deploy-layout,
  .deploy-subgrid,
  .deploy-form__grid {
    grid-template-columns: 1fr;
  }

  .deploy-notify-resolver {
    grid-template-columns: 1fr;
    max-width: none;
  }

  .deploy-topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .deploy-topbar__select {
    width: 100%;
  }
}
</style>
