<template>
  <div class="ftp-credentials-page" v-loading="loading">
    <section class="page-header">
      <div>
        <p class="page-header__eyebrow">FTP Connections</p>
        <h2>FTP 连接</h2>
        <p class="page-header__desc">
          全局维护 FTP
          服务器地址、端口和登录账户。部署配置只选择连接，不重复保存服务器和账号密码。
        </p>
      </div>
      <div class="page-header__actions">
        <el-button :loading="loading" @click="fetchCredentials">刷新</el-button>
        <el-button type="primary" @click="openCreateDialog">新增连接</el-button>
      </div>
    </section>

    <section class="page-panel">
      <el-table :data="credentials" stripe class="ftp-table">
        <el-table-column label="连接名称" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="ftp-table__main">
              <strong>{{ row.name || row.id }}</strong>
              <span>{{ row.id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="服务器地址" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.host || "-" }}</template>
        </el-table-column>
        <el-table-column label="端口" width="80" align="center">
          <template #default="{ row }">{{ row.port || "21" }}</template>
        </el-table-column>
        <el-table-column
          prop="username"
          label="登录账号"
          min-width="120"
          show-overflow-tooltip
        />
        <el-table-column label="最大线程" width="90" align="center">
          <template #default="{ row }">{{
            row.max_upload_threads || 4
          }}</template>
        </el-table-column>
        <el-table-column label="密码" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              :type="row.has_password ? 'success' : 'warning'"
              effect="plain"
            >
              {{ row.has_password ? "已配置" : "未配置" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="创建人"
          width="100"
          align="center"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ row.created_by || "-" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag
              :type="row.enabled === false ? 'info' : 'success'"
              effect="plain"
            >
              {{ row.enabled === false ? "停用" : "启用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :disabled="!row.can_manage"
              @click="openEditDialog(row)"
              >编辑</el-button
            >
            <el-popconfirm
              title="删除后部署配置中引用该连接的服务器将无法通过校验。"
              @confirm="deleteCredential(row)"
            >
              <template #reference>
                <el-button
                  size="small"
                  type="danger"
                  text
                  :disabled="!row.can_manage"
                  >删除</el-button
                >
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!loading && !credentials.length"
        description="暂无 FTP 连接"
        :image-size="64"
      />
    </section>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑 FTP 连接' : '新增 FTP 连接'"
      width="560px"
    >
      <el-form label-position="top" class="credential-form">
        <el-form-item label="连接名称">
          <el-input v-model="draft.name" placeholder="生产 FTP" />
        </el-form-item>
        <el-form-item label="服务器地址（IP / 域名）">
          <el-input
            v-model="draft.host"
            placeholder="ftp.example.com 或 10.0.0.1"
          />
        </el-form-item>
        <el-form-item label="端口号">
          <el-input-number
            v-model="draft.port"
            :min="1"
            :max="65535"
            :step="1"
            :controls="false"
            placeholder="默认 21，可不填"
            class="credential-form__port"
          />
        </el-form-item>
        <el-form-item label="登录账号">
          <el-input v-model="draft.username" placeholder="ftp-user" />
        </el-form-item>
        <el-form-item label="登录密码">
          <el-input
            v-model="draft.password"
            type="password"
            show-password
            :placeholder="editingId ? '留空则保持原密码' : '请输入 FTP 密码'"
          />
        </el-form-item>
        <el-form-item label="最大上传线程数">
          <el-input-number
            v-model="draft.max_upload_threads"
            :min="1"
            :max="32"
            :step="1"
            class="credential-form__port"
          />
          <div class="credential-form__hint">
            按上传目录根层的文件和文件夹生成任务，同时运行数量不超过此值。
          </div>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch
            v-model="draft.enabled"
            active-text="启用"
            inactive-text="停用"
          />
        </el-form-item>
        <el-alert
          v-if="testResult.message"
          :title="testResult.message"
          :type="testResult.ok ? 'success' : 'error'"
          show-icon
          :closable="false"
        />
      </el-form>
      <template #footer>
        <el-button :loading="testing" :disabled="saving" @click="testCredential"
          >检查本地配置</el-button
        >
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCredential"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  readLocalEntities,
  removeLocalEntity,
  upsertLocalEntity,
} from "@/services/local-project-repository.js";

const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const credentials = ref([]);
const dialogVisible = ref(false);
const editingId = ref("");
const draft = ref(createDraft());
const testResult = ref({ ok: false, message: "" });

function createDraft(item = null) {
  return {
    name: String(item?.name || "").trim(),
    host: String(item?.host || "").trim(),
    port: item?.port ? Number(item.port) : null,
    username: String(item?.username || "").trim(),
    password: "",
    max_upload_threads: Math.max(
      1,
      Math.min(32, Number(item?.max_upload_threads || 4)),
    ),
    enabled: item?.enabled !== false,
  };
}

function normalizeCredential(item = {}) {
  const password = String(item?.password || "");
  return {
    ...item,
    id: String(item?.id || "").trim(),
    name: String(item?.name || item?.id || "").trim(),
    host: String(item?.host || "").trim(),
    username: String(item?.username || "").trim(),
    enabled: item?.enabled !== false,
    can_manage: item?.can_manage !== false,
    has_password: Boolean(password) || Boolean(item?.has_password),
  };
}

function findEditingCredential() {
  const id = String(editingId.value || "").trim();
  return id ? credentials.value.find((item) => item.id === id) || null : null;
}

function createCredentialId() {
  const namePart =
    String(draft.value.name || "ftp")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "ftp";
  return `local-ftp-${namePart}-${Date.now().toString(36)}`;
}

async function fetchCredentials() {
  loading.value = true;
  try {
    credentials.value = readLocalEntities("ftp_credentials")
      .map((item) => normalizeCredential(item))
      .filter((item) => item.id);
  } finally {
    loading.value = false;
  }
}

function openCreateDialog() {
  editingId.value = "";
  draft.value = createDraft();
  testResult.value = { ok: false, message: "" };
  dialogVisible.value = true;
}

function openEditDialog(item) {
  editingId.value = String(item?.id || "").trim();
  draft.value = createDraft(item);
  testResult.value = { ok: false, message: "" };
  dialogVisible.value = true;
}

function normalizePortForSubmit() {
  return draft.value.port === null ||
    draft.value.port === undefined ||
    draft.value.port === ""
    ? ""
    : String(Math.trunc(Number(draft.value.port)));
}

function validatePortValue(normalizedPort) {
  if (!normalizedPort) return true;
  const portValue = Number(normalizedPort);
  if (!Number.isInteger(portValue) || portValue < 1 || portValue > 65535) {
    ElMessage.warning("FTP 端口号必须是 1-65535，可不填");
    return false;
  }
  return true;
}

function buildCredentialPayload({
  requireName = false,
  requirePassword = false,
} = {}) {
  const name = String(draft.value.name || "").trim();
  const host = String(draft.value.host || "").trim();
  const username = String(draft.value.username || "").trim();
  const password = String(draft.value.password || "").trim();
  if (requireName && !name) {
    ElMessage.warning("请填写 FTP 连接名称");
    return null;
  }
  if (!host) {
    ElMessage.warning("请填写 FTP 服务器地址");
    return null;
  }
  if (!username) {
    ElMessage.warning("请填写 FTP 登录账号");
    return null;
  }
  if (requirePassword && !password) {
    ElMessage.warning("请填写 FTP 登录密码");
    return null;
  }
  const normalizedPort = normalizePortForSubmit();
  if (!validatePortValue(normalizedPort)) return null;
  return {
    ...draft.value,
    name,
    host,
    port: normalizedPort,
    username,
    password,
    enabled: draft.value.enabled !== false,
  };
}

async function testCredential() {
  const payload = buildCredentialPayload({ requireName: false });
  if (!payload) return;
  const existing = findEditingCredential();
  const password = String(payload.password || existing?.password || "").trim();
  if (!password) {
    ElMessage.warning("请填写 FTP 登录密码");
    return;
  }
  testing.value = true;
  testResult.value = { ok: false, message: "" };
  try {
    const message = "本地配置完整，未执行 FTP 网络连接测试";
    testResult.value = { ok: true, message };
    ElMessage.success(message);
  } finally {
    testing.value = false;
  }
}

async function saveCredential() {
  const payload = buildCredentialPayload({ requireName: true });
  if (!payload) return;
  saving.value = true;
  try {
    const existing = findEditingCredential();
    const password = String(
      payload.password || existing?.password || "",
    ).trim();
    if (!password) {
      ElMessage.warning("请填写 FTP 登录密码");
      return;
    }
    const now = new Date().toISOString();
    upsertLocalEntity(
      "ftp_credentials",
      normalizeCredential({
        ...existing,
        ...payload,
        id: editingId.value || createCredentialId(),
        password,
        has_password: true,
        can_manage: true,
        created_at: existing?.created_at || now,
        updated_at: now,
        created_by: existing?.created_by || "local",
      }),
    );
    await fetchCredentials();
    dialogVisible.value = false;
    ElMessage.success("FTP 连接已保存");
  } finally {
    saving.value = false;
  }
}

async function deleteCredential(item) {
  const id = String(item?.id || "").trim();
  if (!id) return;
  removeLocalEntity("ftp_credentials", id);
  credentials.value = credentials.value.filter((entry) => entry.id !== id);
  ElMessage.success("FTP 连接已删除");
}

function handleLocalEntityUpdate(event) {
  if (String(event?.detail?.entityName || "").trim() === "ftp_credentials") {
    void fetchCredentials();
  }
}

onMounted(() => {
  void fetchCredentials();
  window.addEventListener("local-entities-updated", handleLocalEntityUpdate);
});

onBeforeUnmount(() => {
  window.removeEventListener("local-entities-updated", handleLocalEntityUpdate);
});
</script>

<style scoped>
.ftp-credentials-page {
  min-height: 100%;
  padding: 20px;
  display: grid;
  align-content: start;
  gap: 16px;
  background: #f8fafc;
}

.page-header,
.page-panel {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 22px;
}

.page-header__eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0;
  text-transform: uppercase;
  color: #7c8aa0;
}

.page-header h2 {
  margin: 0;
  font-size: 22px;
  color: #0f172a;
}

.page-header__desc {
  max-width: 760px;
  margin: 8px 0 0;
  color: #475569;
  line-height: 1.6;
}

.page-header__actions {
  display: flex;
  gap: 10px;
}

.page-panel {
  padding: 18px;
  /* grid 子项默认 min-width:auto 会被表格最小内容宽度撑开，
     置为 0 让窄窗口时滚动收敛在表格内部而不是整个页面溢出。 */
  min-width: 0;
  overflow: hidden;
}

.ftp-table {
  width: 100%;
}

.ftp-table__main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.ftp-table__main strong,
.ftp-table__main span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ftp-table__main span {
  color: #64748b;
  font-size: 12px;
}

.credential-form {
  display: grid;
  gap: 2px;
}

.credential-form__port {
  width: 100%;
}

.credential-form__hint {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 900px) {
  .ftp-credentials-page {
    padding: 16px;
  }

  .page-header {
    flex-direction: column;
  }
}
</style>
