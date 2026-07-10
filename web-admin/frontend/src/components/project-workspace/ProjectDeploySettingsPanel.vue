<template>
  <ProjectWorkspaceBlock eyebrow="Deploy" title="部署配置">
    <template #actions>
      <el-button :loading="validating" @click="validateSettings">校验配置</el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!canManageProject"
        @click="saveSettings"
      >
        保存配置
      </el-button>
    </template>

    <el-alert
      title="此处只维护项目对话部署所需配置，不包含部署执行、产物或运行操作。"
      type="info"
      :closable="false"
      show-icon
      class="deploy-settings-panel__notice"
    />

    <el-form label-position="top" class="deploy-settings-panel__form">
      <div class="deploy-settings-panel__summary">
        <el-form-item label="启用部署">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="默认环境">
          <el-select v-model="form.default_profile" placeholder="选择默认环境">
            <el-option
              v-for="profile in form.profiles"
              :key="profile.id"
              :label="profile.name || profile.id"
              :value="profile.id"
            />
          </el-select>
        </el-form-item>
      </div>

      <div class="deploy-settings-panel__layout">
        <aside class="deploy-settings-panel__sidebar">
          <div class="deploy-settings-panel__sidebar-head">
            <strong>环境档位</strong>
            <el-button text type="primary" :disabled="!canManageProject" @click="addProfile">
              新增
            </el-button>
          </div>
          <button
            v-for="profile in form.profiles"
            :key="profile.id"
            type="button"
            class="deploy-settings-panel__nav-item"
            :class="{ 'is-active': profile.id === activeProfileId }"
            @click="selectProfile(profile.id)"
          >
            <span>{{ profile.name || profile.id }}</span>
            <small>{{ profile.environment || profile.id }}</small>
          </button>
        </aside>

        <section v-if="activeProfile" class="deploy-settings-panel__editor">
          <div class="deploy-settings-panel__section-head">
            <div>
              <strong>环境信息</strong>
              <p>项目对话部署会先读取这里的档位、组件与服务器目标。</p>
            </div>
            <el-button
              text
              type="danger"
              :disabled="!canManageProject || form.profiles.length <= 1"
              @click="removeProfile(activeProfile.id)"
            >
              删除环境
            </el-button>
          </div>

          <div class="deploy-settings-panel__grid three-columns">
            <el-form-item label="环境 ID">
              <el-input :model-value="activeProfile.id" @update:model-value="syncActiveProfileId" />
            </el-form-item>
            <el-form-item label="环境名称">
              <el-input v-model="activeProfile.name" />
            </el-form-item>
            <el-form-item label="环境标识">
              <el-input v-model="activeProfile.environment" placeholder="prod / test" />
            </el-form-item>
          </div>

          <div class="deploy-settings-panel__component-tabs">
            <el-segmented
              v-model="activeComponentId"
              :options="componentOptions"
              @change="selectComponent"
            />
            <el-button text type="primary" :disabled="!canManageProject" @click="addComponent">
              新增部署单元
            </el-button>
          </div>

          <section v-if="activeComponent" class="deploy-settings-panel__component">
            <div class="deploy-settings-panel__section-head compact">
              <strong>部署单元</strong>
              <el-button
                text
                type="danger"
                :disabled="!canManageProject || activeProfile.components.length <= 1"
                @click="removeComponent(activeComponent.id)"
              >
                删除部署单元
              </el-button>
            </div>

            <div class="deploy-settings-panel__grid three-columns">
              <el-form-item label="单元 ID">
                <el-input :model-value="activeComponent.id" @update:model-value="syncActiveComponentId" />
              </el-form-item>
              <el-form-item label="单元名称">
                <el-input v-model="activeComponent.name" />
              </el-form-item>
              <el-form-item label="产物类型">
                <el-select v-model="activeComponent.artifact_kind">
                  <el-option label="源码包" value="source-bundle" />
                  <el-option label="前端产物" value="frontend-dist" />
                  <el-option label="后端产物" value="backend-dist" />
                  <el-option label="单文件" value="file" />
                </el-select>
              </el-form-item>
            </div>

            <div class="deploy-settings-panel__grid two-columns">
              <el-form-item label="本地打包命令">
                <el-input
                  v-model="activeComponent.package.command"
                  placeholder="例如 npm run build"
                />
              </el-form-item>
              <el-form-item label="产物路径">
                <el-input
                  v-model="activeComponent.package.artifact_path"
                  placeholder="例如 dist 或 release.zip"
                />
              </el-form-item>
            </div>

            <div class="deploy-settings-panel__switches">
              <el-checkbox v-model="activeComponent.safety.auto_deploy_on_artifact_update">
                上传产物后自动部署
              </el-checkbox>
              <el-checkbox v-model="activeComponent.notify.enabled">启用部署通知</el-checkbox>
            </div>

            <el-form-item v-if="activeComponent.notify.enabled" label="通知模板">
              <el-input
                v-model="activeComponent.notify.template"
                type="textarea"
                :rows="2"
                placeholder="{project_name} {profile} 部署状态：{status_label}"
              />
            </el-form-item>

            <div class="deploy-settings-panel__targets-head">
              <div>
                <strong>服务器目标</strong>
                <p>凭据只选择全局 FTP 连接，不在项目中保存账号密码。</p>
              </div>
              <el-button :disabled="!canManageProject" @click="addTarget">新增服务器</el-button>
            </div>

            <el-table :data="activeComponent.targets" stripe class="deploy-settings-panel__targets">
              <el-table-column label="目标 ID" min-width="130">
                <template #default="{ row }"><el-input v-model="row.id" size="small" /></template>
              </el-table-column>
              <el-table-column label="名称" min-width="140">
                <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
              </el-table-column>
              <el-table-column label="FTP 连接" min-width="230">
                <template #default="{ row }">
                  <el-select
                    v-model="row.ftp_credential_id"
                    size="small"
                    filterable
                    :loading="ftpLoading"
                    placeholder="选择全局 FTP 连接"
                  >
                    <el-option
                      v-for="credential in ftpOptions"
                      :key="credential.value"
                      :label="credential.label"
                      :value="credential.value"
                      :disabled="credential.disabled"
                    />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="远端目录" min-width="190">
                <template #default="{ row }">
                  <el-input v-model="row.remote_path" size="small" placeholder="/opt/app" />
                </template>
              </el-table-column>
              <el-table-column label="部署命令" min-width="220">
                <template #default="{ row }">
                  <el-input v-model="row.deploy_command" size="small" placeholder="./deploy.sh up" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="76" fixed="right">
                <template #default="{ $index }">
                  <el-button
                    text
                    type="danger"
                    :disabled="!canManageProject || activeComponent.targets.length <= 1"
                    @click="removeTarget($index)"
                  >删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </section>
        </section>
      </div>
    </el-form>

    <el-alert
      v-if="validation"
      :title="validation.valid ? '部署配置校验通过' : firstValidationMessage"
      :type="validation.valid ? 'success' : 'warning'"
      :closable="false"
      show-icon
      class="deploy-settings-panel__validation"
    />
    <ul v-if="validation?.issues?.length" class="deploy-settings-panel__issues">
      <li v-for="issue in validation.issues" :key="`${issue.path}-${issue.message}`">
        {{ issue.message }}
      </li>
    </ul>
  </ProjectWorkspaceBlock>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import ProjectWorkspaceBlock from "@/components/project-workspace/ProjectWorkspaceBlock.vue";
import api from "@/utils/api.js";

const props = defineProps({
  projectId: { type: String, required: true },
  project: { type: Object, default: null },
  canManageProject: { type: Boolean, default: false },
  manageBlockedMessage: { type: String, default: "当前账号无权修改项目" },
});

const emit = defineEmits(["project-updated"]);
const saving = ref(false);
const validating = ref(false);
const ftpLoading = ref(false);
const ftpCredentials = ref([]);
const validation = ref(null);
const form = ref(createDefaultSettings());
const activeProfileId = ref("prod");
const activeComponentId = ref("app");

const activeProfile = computed(() =>
  form.value.profiles.find((item) => item.id === activeProfileId.value) || form.value.profiles[0] || null,
);
const activeComponent = computed(() =>
  activeProfile.value?.components?.find((item) => item.id === activeComponentId.value)
  || activeProfile.value?.components?.[0]
  || null,
);
const componentOptions = computed(() =>
  (activeProfile.value?.components || []).map((item) => ({ label: item.name || item.id, value: item.id })),
);
const ftpOptions = computed(() =>
  ftpCredentials.value.map((item) => ({
    value: String(item.id || "").trim(),
    label: [item.name || item.id, item.host, item.username].filter(Boolean).join(" · "),
    disabled: item.enabled === false,
  })).filter((item) => item.value),
);
const firstValidationMessage = computed(() => validation.value?.issues?.[0]?.message || "部署配置仍需补充");

function defaultNotifyTemplate() {
  return "{project_name} {profile} 部署状态：{status_label}，产物：{artifact_name}，运行：{run_id}";
}

function safeId(value, fallback) {
  return String(value || "").trim().replace(/\s+/g, "-") || fallback;
}

function createDefaultTarget(index = 1) {
  return {
    id: `target-${index}`,
    name: `服务器 ${index}`,
    enabled: true,
    transport_mode: "ftp",
    ftp_credential_id: "",
    remote_path: "",
    deploy_command: "",
    remote_executor: {},
    health_check: {},
  };
}

function createDefaultComponent(index = 0) {
  return {
    id: index === 0 ? "app" : `component-${index + 1}`,
    name: index === 0 ? "默认服务" : `部署单元 ${index + 1}`,
    enabled: true,
    artifact_kind: "source-bundle",
    package: {},
    safety: { auto_deploy_on_artifact_update: false, dry_run_default: false },
    notify: { enabled: false, template: defaultNotifyTemplate(), targets: [] },
    targets: [createDefaultTarget()],
  };
}

function createDefaultProfile(index = 0) {
  return {
    id: index === 0 ? "prod" : `env-${index + 1}`,
    name: index === 0 ? "生产环境" : `环境 ${index + 1}`,
    environment: index === 0 ? "prod" : `env-${index + 1}`,
    artifact_kind: "source-bundle",
    enabled: true,
    package: {},
    transport: {},
    remote_executor: {},
    notify: { enabled: false, template: defaultNotifyTemplate(), targets: [] },
    safety: { auto_deploy_on_artifact_update: false, dry_run_default: false },
    components: [createDefaultComponent()],
  };
}

function createDefaultSettings() {
  return { version: "2", enabled: false, default_profile: "prod", profiles: [createDefaultProfile()] };
}

function normalizeTarget(value, index) {
  const source = value && typeof value === "object" ? value : {};
  const transport = source.transport && typeof source.transport === "object" ? source.transport : {};
  const executor = source.remote_executor && typeof source.remote_executor === "object" ? source.remote_executor : {};
  return {
    ...createDefaultTarget(index + 1),
    ...source,
    id: safeId(source.id, `target-${index + 1}`),
    name: String(source.name || source.id || `服务器 ${index + 1}`).trim(),
    enabled: source.enabled !== false,
    transport_mode: "ftp",
    ftp_credential_id: String(source.ftp_credential_id || transport.ftp_credential_id || "").trim(),
    remote_path: String(source.remote_path || transport.remote_path || "").trim(),
    deploy_command: String(source.deploy_command || executor.deploy_command || "").trim(),
    remote_executor: { ...executor },
    health_check: source.health_check && typeof source.health_check === "object" ? { ...source.health_check } : {},
  };
}

function normalizeComponent(value, index, legacyProfile = {}) {
  const source = value && typeof value === "object" ? value : {};
  const safety = source.safety && typeof source.safety === "object" ? source.safety : legacyProfile.safety || {};
  const notify = source.notify && typeof source.notify === "object" ? source.notify : legacyProfile.notify || {};
  const rawTargets = Array.isArray(source.targets) ? source.targets : [];
  return {
    ...createDefaultComponent(index),
    ...source,
    id: safeId(source.id, index === 0 ? "app" : `component-${index + 1}`),
    name: String(source.name || source.id || (index === 0 ? "默认服务" : `部署单元 ${index + 1}`)).trim(),
    enabled: source.enabled !== false,
    artifact_kind: String(source.artifact_kind || legacyProfile.artifact_kind || "source-bundle").trim(),
    package: source.package && typeof source.package === "object" ? { ...source.package } : {},
    safety: {
      auto_deploy_on_artifact_update: Boolean(safety.auto_deploy_on_artifact_update),
      dry_run_default: Boolean(safety.dry_run_default),
    },
    notify: {
      ...notify,
      enabled: Boolean(notify.enabled),
      template: String(notify.template || defaultNotifyTemplate()).trim(),
      targets: Array.isArray(notify.targets) ? notify.targets.map((item) => ({ ...item })) : [],
    },
    targets: rawTargets.length
      ? rawTargets.map((item, targetIndex) => normalizeTarget(item, targetIndex))
      : [normalizeTarget({
          id: "primary",
          name: "主服务器",
          transport: legacyProfile.transport,
          remote_executor: legacyProfile.remote_executor,
        }, 0)],
  };
}

function normalizeProfile(value, index) {
  const source = value && typeof value === "object" ? value : {};
  const rawComponents = Array.isArray(source.components) ? source.components : [];
  return {
    ...createDefaultProfile(index),
    ...source,
    id: safeId(source.id, index === 0 ? "prod" : `env-${index + 1}`),
    name: String(source.name || source.id || (index === 0 ? "生产环境" : `环境 ${index + 1}`)).trim(),
    environment: String(source.environment || source.id || (index === 0 ? "prod" : `env-${index + 1}`)).trim(),
    enabled: source.enabled !== false,
    components: rawComponents.length
      ? rawComponents.map((item, componentIndex) => normalizeComponent(item, componentIndex))
      : [normalizeComponent({}, 0, source)],
  };
}

function normalizeSettings(value) {
  const source = value && typeof value === "object" ? value : {};
  const profiles = Array.isArray(source.profiles)
    ? source.profiles.map((item, index) => normalizeProfile(item, index))
    : [];
  const nextProfiles = profiles.length ? profiles : [createDefaultProfile()];
  const defaultProfile = nextProfiles.some((item) => item.id === source.default_profile)
    ? source.default_profile
    : nextProfiles[0].id;
  return {
    ...createDefaultSettings(),
    ...source,
    version: "2",
    enabled: Boolean(source.enabled),
    default_profile: defaultProfile,
    profiles: nextProfiles,
  };
}

function syncFromProject(settings) {
  form.value = normalizeSettings(settings);
  activeProfileId.value = form.value.default_profile || form.value.profiles[0]?.id || "prod";
  activeComponentId.value = activeProfile.value?.components?.[0]?.id || "app";
  validation.value = null;
}

function selectProfile(profileId) {
  activeProfileId.value = profileId;
  activeComponentId.value = activeProfile.value?.components?.[0]?.id || "app";
}

function selectComponent(componentId) {
  activeComponentId.value = componentId;
}

function addProfile() {
  const profile = createDefaultProfile(form.value.profiles.length);
  form.value.profiles.push(profile);
  selectProfile(profile.id);
}

function removeProfile(profileId) {
  if (form.value.profiles.length <= 1) return;
  form.value.profiles = form.value.profiles.filter((item) => item.id !== profileId);
  if (form.value.default_profile === profileId) form.value.default_profile = form.value.profiles[0].id;
  selectProfile(form.value.default_profile);
}

function addComponent() {
  if (!activeProfile.value) return;
  const component = createDefaultComponent(activeProfile.value.components.length);
  activeProfile.value.components.push(component);
  activeComponentId.value = component.id;
}

function removeComponent(componentId) {
  if (!activeProfile.value || activeProfile.value.components.length <= 1) return;
  activeProfile.value.components = activeProfile.value.components.filter((item) => item.id !== componentId);
  activeComponentId.value = activeProfile.value.components[0].id;
}

function addTarget() {
  activeComponent.value?.targets.push(createDefaultTarget((activeComponent.value?.targets.length || 0) + 1));
}

function removeTarget(index) {
  if (!activeComponent.value || activeComponent.value.targets.length <= 1) return;
  activeComponent.value.targets.splice(index, 1);
}

function syncActiveProfileId(nextId) {
  const previousId = activeProfileId.value;
  const normalized = safeId(nextId, previousId);
  const profile = form.value.profiles.find((item) => item.id === previousId);
  if (!profile) return;
  profile.id = normalized;
  activeProfileId.value = normalized;
  if (form.value.default_profile === previousId) form.value.default_profile = normalized;
}

function syncActiveComponentId(nextId) {
  const previousId = activeComponentId.value;
  const normalized = safeId(nextId, previousId);
  const component = activeProfile.value?.components?.find((item) => item.id === previousId);
  if (!component) return;
  component.id = normalized;
  activeComponentId.value = normalized;
}

async function fetchFtpCredentials() {
  ftpLoading.value = true;
  try {
    const data = await api.get("/ftp-credentials");
    ftpCredentials.value = Array.isArray(data?.items) ? data.items : [];
  } catch (error) {
    ftpCredentials.value = [];
    ElMessage.error(error?.detail || error?.message || "加载 FTP 连接失败");
  } finally {
    ftpLoading.value = false;
  }
}

async function validateSettings({ notify = true } = {}) {
  validating.value = true;
  try {
    const data = await api.post(`/projects/${props.projectId}/deploy-settings/validate`, {
      deploy_settings: normalizeSettings(form.value),
    });
    validation.value = { valid: Boolean(data?.valid), issues: Array.isArray(data?.issues) ? data.issues : [] };
    if (notify) ElMessage[validation.value.valid ? "success" : "warning"](
      validation.value.valid ? "部署配置校验通过" : firstValidationMessage.value,
    );
    return validation.value.valid;
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "校验部署配置失败");
    return false;
  } finally {
    validating.value = false;
  }
}

async function saveSettings() {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  if (!(await validateSettings({ notify: false }))) {
    ElMessage.warning(firstValidationMessage.value);
    return;
  }
  saving.value = true;
  try {
    await api.put(`/projects/${props.projectId}`, { deploy_settings: normalizeSettings(form.value) });
    ElMessage.success("部署配置已保存");
    emit("project-updated");
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "保存部署配置失败");
  } finally {
    saving.value = false;
  }
}

watch(() => props.project?.deploy_settings, (settings) => syncFromProject(settings || {}), { immediate: true });
onMounted(fetchFtpCredentials);
</script>

<style scoped>
.deploy-settings-panel__notice,
.deploy-settings-panel__validation {
  margin-bottom: 16px;
}

.deploy-settings-panel__summary,
.deploy-settings-panel__grid {
  display: grid;
  gap: 16px;
}

.deploy-settings-panel__summary,
.deploy-settings-panel__grid.two-columns {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.deploy-settings-panel__grid.three-columns {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.deploy-settings-panel__layout {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.deploy-settings-panel__sidebar,
.deploy-settings-panel__editor,
.deploy-settings-panel__component {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-bg-color);
}

.deploy-settings-panel__sidebar {
  padding: 12px;
}

.deploy-settings-panel__sidebar-head,
.deploy-settings-panel__section-head,
.deploy-settings-panel__component-tabs,
.deploy-settings-panel__targets-head,
.deploy-settings-panel__switches {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.deploy-settings-panel__nav-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  margin-top: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
}

.deploy-settings-panel__nav-item small,
.deploy-settings-panel__section-head p,
.deploy-settings-panel__targets-head p {
  color: var(--el-text-color-secondary);
  margin: 0;
  font-size: 12px;
}

.deploy-settings-panel__nav-item.is-active {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.deploy-settings-panel__editor {
  padding: 20px;
}

.deploy-settings-panel__section-head {
  margin-bottom: 16px;
}

.deploy-settings-panel__section-head.compact {
  margin-bottom: 12px;
}

.deploy-settings-panel__component-tabs,
.deploy-settings-panel__targets-head {
  margin: 8px 0 16px;
}

.deploy-settings-panel__component {
  padding: 16px;
}

.deploy-settings-panel__switches {
  justify-content: flex-start;
  margin-bottom: 16px;
}

.deploy-settings-panel__issues {
  margin: -8px 0 0;
  padding-left: 22px;
  color: var(--el-color-warning-dark-2);
  line-height: 1.7;
}

@media (max-width: 980px) {
  .deploy-settings-panel__layout,
  .deploy-settings-panel__summary,
  .deploy-settings-panel__grid.two-columns,
  .deploy-settings-panel__grid.three-columns {
    grid-template-columns: 1fr;
  }
}
</style>
