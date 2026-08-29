<template>
  <div class="email-page" v-loading="loading">
    <section class="page-header">
      <div>
        <p class="page-header__eyebrow">Email Center</p>
        <h2>QQ 邮箱</h2>
        <p class="page-header__desc">配置 QQ 邮箱 SMTP 授权码后，即可从桌面端发送邮件。配置只保存在当前电脑，不上传到服务端。</p>
      </div>
      <div class="page-header__actions">
        <el-tag :type="config.enabled ? 'success' : 'info'" effect="plain">{{ config.enabled ? '已启用' : '未启用' }}</el-tag>
        <el-button :loading="loading" @click="loadConfig">刷新</el-button>
      </div>
    </section>

    <div class="email-grid">
      <section class="page-panel">
        <div class="panel-heading">
          <div>
            <h3>发件账号</h3>
            <p>QQ 邮箱的 SMTP 服务使用“授权码”，不是 QQ 登录密码。</p>
          </div>
          <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
        </div>
        <el-form label-position="top" class="email-form">
          <el-form-item label="账号名称">
            <el-input v-model="config.name" placeholder="例如：工作邮箱" />
          </el-form-item>
          <el-form-item label="QQ 邮箱地址">
            <el-input v-model="config.address" type="email" placeholder="your-name@qq.com" autocomplete="email" />
          </el-form-item>
          <el-form-item label="SMTP 授权码">
            <el-input v-model="config.authorizationCode" type="password" show-password placeholder="在 QQ 邮箱设置中生成" autocomplete="new-password" />
            <p class="field-hint">QQ 邮箱网页版：设置 → 账户 → 开启 SMTP 服务并生成授权码。</p>
          </el-form-item>
          <el-form-item>
            <el-switch v-model="config.enabled" active-text="启用此发件账号" />
          </el-form-item>
        </el-form>
      </section>

      <section class="page-panel">
        <div class="panel-heading">
          <div>
            <h3>发送邮件</h3>
            <p>支持多个收件人，使用逗号、分号或换行分隔。</p>
          </div>
          <el-tag v-if="lastSentAt" type="success" effect="plain">最近发送 {{ lastSentAt }}</el-tag>
        </div>
        <el-form label-position="top" class="email-form">
          <el-form-item label="收件人" required>
            <el-input v-model="draft.to" type="textarea" :rows="2" placeholder="recipient@example.com" />
          </el-form-item>
          <el-form-item label="抄送">
            <el-input v-model="draft.cc" placeholder="可选" />
          </el-form-item>
          <el-form-item label="主题" required>
            <el-input v-model="draft.subject" placeholder="邮件主题" />
          </el-form-item>
          <el-form-item label="正文" required>
            <el-input v-model="draft.content" type="textarea" :rows="7" placeholder="请输入邮件正文" />
          </el-form-item>
          <div class="send-actions">
            <span class="send-hint">当前发件人：{{ config.address || '尚未配置' }}</span>
            <el-button type="primary" :loading="sending" :disabled="!config.enabled" @click="sendEmail">发送邮件</el-button>
          </div>
        </el-form>
      </section>
    </div>
    <section v-if="errorDetail" class="error-panel" role="alert">
      <strong>最近一次完整错误信息</strong>
      <pre>{{ errorDetail }}</pre>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  readNativeGlobalQqEmailConfigFile,
  sendNativeQqEmail,
  writeNativeGlobalQqEmailConfigFile,
} from "@/utils/native-desktop-bridge.js";

const loading = ref(false);
const saving = ref(false);
const sending = ref(false);
const lastSentAt = ref("");
const errorDetail = ref("");
const config = reactive({ version: 1, enabled: false, name: "", address: "", authorizationCode: "" });
const draft = reactive({ to: "", cc: "", subject: "", content: "" });

function extractErrorMessage(error, fallback) {
  if (typeof error === "string" && error.trim()) return error.trim();
  if (error?.message && String(error.message).trim()) return String(error.message).trim();
  if (error?.error && String(error.error).trim()) return String(error.error).trim();
  try {
    const serialized = JSON.stringify(error);
    if (serialized && serialized !== "{}") return serialized;
  } catch {}
  return fallback;
}

async function showErrorDetail(error, fallback) {
  const message = extractErrorMessage(error, fallback);
  errorDetail.value = message;
  try {
    await ElMessageBox.alert(message, "操作失败（完整错误信息）", {
      type: "error",
      confirmButtonText: "知道了",
      closeOnClickModal: false,
    });
  } catch {}
}

function parseConfig(content) {
  try {
    const value = JSON.parse(String(content || "{}"));
    Object.assign(config, {
      version: 1,
      enabled: value.enabled === true,
      name: String(value.name || ""),
      address: String(value.address || ""),
      authorizationCode: String(value.authorizationCode || ""),
    });
  } catch (error) {
    void showErrorDetail(error, "QQ 邮箱配置读取失败");
  }
}

async function loadConfig() {
  loading.value = true;
  try {
    const result = await readNativeGlobalQqEmailConfigFile();
    if (result?.content) parseConfig(result.content);
  } catch (error) {
    void showErrorDetail(error, "无法读取 QQ 邮箱配置");
  } finally {
    loading.value = false;
  }
}

function normalizedConfig() {
  return {
    version: 1,
    enabled: config.enabled === true,
    name: config.name.trim(),
    address: config.address.trim(),
    authorizationCode: config.authorizationCode.trim(),
  };
}

async function saveConfig(showMessage = true) {
  const payload = normalizedConfig();
  if (!payload.address || !payload.address.includes("@")) {
    ElMessage.warning("请填写有效的 QQ 邮箱地址");
    return false;
  }
  if (!payload.authorizationCode) {
    ElMessage.warning("请填写 QQ 邮箱授权码");
    return false;
  }
  saving.value = true;
  try {
    const result = await writeNativeGlobalQqEmailConfigFile(JSON.stringify(payload));
    if (!result) throw new Error("桌面邮箱配置能力不可用");
    parseConfig(result.content);
    if (showMessage) ElMessage.success("QQ 邮箱配置已保存");
    return true;
  } catch (error) {
    void showErrorDetail(error, "QQ 邮箱配置保存失败");
    return false;
  } finally {
    saving.value = false;
  }
}

async function sendEmail() {
  if (!draft.to.trim() || !draft.subject.trim() || !draft.content.trim()) {
    ElMessage.warning("请填写收件人、主题和正文");
    return;
  }
  if (!(await saveConfig(false))) return;
  sending.value = true;
  try {
    await sendNativeQqEmail(draft);
    lastSentAt.value = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    ElMessage.success("邮件已发送");
    Object.assign(draft, { to: "", cc: "", subject: "", content: "" });
  } catch (error) {
    void showErrorDetail(error, "邮件发送失败");
  } finally {
    sending.value = false;
  }
}

onMounted(loadConfig);
</script>

<style scoped>
.email-page { min-height: 100%; padding: 20px; display: grid; align-content: start; gap: 16px; background: #f8fafc; }
.page-header, .page-panel { border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding: 20px 22px; }
.page-header__eyebrow { margin: 0 0 8px; color: #7c8aa0; font-size: 12px; letter-spacing: .12em; text-transform: uppercase; }
.page-header h2, .panel-heading h3 { margin: 0; color: #0f172a; }
.page-header h2 { font-size: 22px; }
.page-header__desc, .panel-heading p, .field-hint { color: #475569; line-height: 1.6; }
.page-header__desc { max-width: 720px; margin: 8px 0 0; }
.page-header__actions, .send-actions { display: flex; align-items: center; gap: 10px; }
.email-grid { display: grid; grid-template-columns: minmax(300px, .8fr) minmax(420px, 1.2fr); gap: 16px; }
.page-panel { min-width: 0; padding: 20px; }
.panel-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
.panel-heading p { margin: 7px 0 0; font-size: 13px; }
.email-form { display: grid; gap: 2px; }
.field-hint, .send-hint { margin: 6px 0 0; font-size: 12px; }
.send-actions { justify-content: space-between; margin-top: 4px; }
.send-hint { color: #64748b; }
.error-panel { border: 1px solid #fca5a5; border-radius: 12px; padding: 16px 18px; background: #fff1f2; color: #991b1b; }
.error-panel strong { display: block; margin-bottom: 8px; }
.error-panel pre { margin: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; color: #7f1d1d; font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
@media (max-width: 900px) { .email-page { padding: 16px; } .page-header, .panel-heading { flex-direction: column; } .email-grid { grid-template-columns: 1fr; } .page-header__actions { width: 100%; justify-content: space-between; } }
</style>
