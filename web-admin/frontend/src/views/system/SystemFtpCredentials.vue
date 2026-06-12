<template>
  <div class="ftp-credentials-page" v-loading="loading">
    <section class="page-header">
      <div>
        <p class="page-header__eyebrow">FTP Connections</p>
        <h2>FTP 连接</h2>
        <p class="page-header__desc">
          全局维护 FTP 服务器地址、端口和登录账户。部署配置只选择连接，不重复保存服务器和账号密码。
        </p>
      </div>
      <div class="page-header__actions">
        <el-button :loading="loading" @click="fetchCredentials">刷新</el-button>
        <el-button type="primary" @click="openCreateDialog">新增连接</el-button>
      </div>
    </section>

    <section class="page-panel">
      <el-table :data="credentials" stripe class="ftp-table">
        <el-table-column label="连接名称" min-width="180">
          <template #default="{ row }">
            <div class="ftp-table__main">
              <strong>{{ row.name || row.id }}</strong>
              <span>{{ row.id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="服务器地址" min-width="170">
          <template #default="{ row }">{{ row.host || "-" }}</template>
        </el-table-column>
        <el-table-column label="端口" width="100">
          <template #default="{ row }">{{ row.port || "21" }}</template>
        </el-table-column>
        <el-table-column prop="username" label="登录账号" min-width="160" />
        <el-table-column label="密码" width="110">
          <template #default="{ row }">
            <el-tag :type="row.has_password ? 'success' : 'warning'" effect="plain">
              {{ row.has_password ? "已配置" : "未配置" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建人" width="130">
          <template #default="{ row }">{{ row.created_by || "-" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.enabled === false ? 'info' : 'success'" effect="plain">
              {{ row.enabled === false ? "停用" : "启用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :disabled="!row.can_manage" @click="openEditDialog(row)">编辑</el-button>
            <el-popconfirm
              title="删除后部署配置中引用该连接的服务器将无法通过校验。"
              @confirm="deleteCredential(row)"
            >
              <template #reference>
                <el-button size="small" type="danger" text :disabled="!row.can_manage">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !credentials.length" description="暂无 FTP 连接" :image-size="64" />
    </section>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑 FTP 连接' : '新增 FTP 连接'" width="560px">
      <el-form label-position="top" class="credential-form">
        <el-form-item label="连接名称">
          <el-input v-model="draft.name" placeholder="生产 FTP" />
        </el-form-item>
        <el-form-item label="服务器地址（IP / 域名）">
          <el-input v-model="draft.host" placeholder="ftp.example.com 或 10.0.0.1" />
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
        <el-form-item label="状态">
          <el-switch v-model="draft.enabled" active-text="启用" inactive-text="停用" />
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
        <el-button :loading="testing" :disabled="saving" @click="testCredential">测试连接</el-button>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCredential">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "@/utils/api.js";

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
    enabled: item?.enabled !== false,
  };
}

async function fetchCredentials() {
  loading.value = true;
  try {
    const data = await api.get("/ftp-credentials");
    credentials.value = Array.isArray(data?.items) ? data.items : [];
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载 FTP 连接失败");
    credentials.value = [];
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
  return draft.value.port === null || draft.value.port === undefined || draft.value.port === ""
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

function buildCredentialPayload({ requireName = false, requirePassword = false } = {}) {
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
  const payload = buildCredentialPayload({
    requireName: false,
    requirePassword: !editingId.value,
  });
  if (!payload) return;
  if (editingId.value) {
    payload.credential_id = editingId.value;
  }
  testing.value = true;
  testResult.value = { ok: false, message: "" };
  try {
    const data = await api.post("/ftp-credentials/test", payload);
    const message = data?.message || (data?.ok ? "FTP 连接成功" : "FTP 连接测试失败");
    testResult.value = { ok: Boolean(data?.ok), message };
    ElMessage[data?.ok ? "success" : "warning"](message);
  } catch (err) {
    const message = err?.detail || err?.message || "FTP 连接测试失败";
    testResult.value = { ok: false, message };
    ElMessage.error(message);
  } finally {
    testing.value = false;
  }
}

async function saveCredential() {
  const payload = buildCredentialPayload({
    requireName: true,
    requirePassword: !editingId.value,
  });
  if (!payload) return;
  saving.value = true;
  try {
    if (editingId.value && !String(payload.password || "").trim()) {
      delete payload.password;
    }
    if (editingId.value) {
      await api.put(`/ftp-credentials/${encodeURIComponent(editingId.value)}`, payload);
    } else {
      await api.post("/ftp-credentials", payload);
    }
    await fetchCredentials();
    dialogVisible.value = false;
    ElMessage.success("FTP 连接已保存");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存 FTP 连接失败");
  } finally {
    saving.value = false;
  }
}

async function deleteCredential(item) {
  const id = String(item?.id || "").trim();
  if (!id) return;
  try {
    await api.delete(`/ftp-credentials/${encodeURIComponent(id)}`);
    credentials.value = credentials.value.filter((entry) => entry.id !== id);
    ElMessage.success("FTP 连接已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除 FTP 连接失败");
  }
}

onMounted(() => {
  void fetchCredentials();
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

@media (max-width: 900px) {
  .ftp-credentials-page {
    padding: 16px;
  }

  .page-header {
    flex-direction: column;
  }
}
</style>
