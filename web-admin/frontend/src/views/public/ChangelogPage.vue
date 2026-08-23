<template>
  <div class="update-page">
    <header class="update-header">
      <button type="button" class="update-brand" @click="router.push('/intro')">
        <span class="update-brand__mark" aria-hidden="true">AI</span>
        <span class="update-brand__copy">
          <strong>AI 智能体工厂</strong>
          <span>桌面端</span>
        </span>
      </button>

      <div class="update-header__actions">
        <el-button text class="update-header__back" @click="router.push('/intro')">
          <el-icon><ArrowLeft /></el-icon>
          返回首页
        </el-button>
        <el-button
          v-if="authenticated"
          type="primary"
          class="update-header__workspace"
          @click="router.push('/ai/chat')"
        >
          进入工作台
        </el-button>
      </div>
    </header>

    <main class="update-main">
      <section class="update-intro">
        <div class="update-intro__eyebrow">软件更新</div>
        <h1>版本更新</h1>
        <p>检查当前版本，下载对应系统的最新版本。</p>
        <div class="update-platform" :class="{ 'update-platform--desktop': isDesktop }">
          <el-icon><Monitor /></el-icon>
          <span>{{ isDesktop ? '桌面应用' : '浏览器访问' }}</span>
        </div>
      </section>

      <section class="update-panel" aria-live="polite">
        <div class="update-panel__heading">
          <div class="update-panel__status-icon" :class="`is-${status}`">
            <el-icon size="22">
              <CircleCheck v-if="status === 'latest'" />
              <Download v-else-if="status === 'available'" />
              <WarningFilled v-else-if="status === 'error'" />
              <Monitor v-else />
            </el-icon>
          </div>
          <div class="update-panel__heading-copy">
            <span class="update-panel__eyebrow">UPDATE STATUS</span>
            <h2>{{ statusLabel }}</h2>
          </div>
          <el-tag :type="statusTagType" effect="plain" class="update-panel__tag">
            {{ statusLabel }}
          </el-tag>
        </div>

        <div class="update-version-grid">
          <div class="update-version">
            <span class="update-version__label">当前版本</span>
            <strong>{{ currentVersion || '未读取' }}</strong>
            <span class="update-version__hint">本机已安装版本</span>
          </div>
          <div class="update-version update-version--latest">
            <span class="update-version__label">最新版本</span>
            <strong>{{ latestVersion }}</strong>
            <span class="update-version__hint">{{ latestVersionHint }}</span>
          </div>
        </div>

        <div v-if="status === 'available'" class="update-release">
          <div class="update-release__heading">
            <div>
              <span class="update-release__eyebrow">NEW RELEASE</span>
              <h3>发现新版本 {{ availableUpdate.version }}</h3>
            </div>
            <span v-if="availableUpdate.pubDate" class="update-release__date">{{ formatDate(availableUpdate.pubDate) }}</span>
          </div>
          <p v-if="availableUpdate.notes" class="update-release__notes">{{ availableUpdate.notes }}</p>
          <p v-else class="update-release__notes update-release__notes--muted">本次版本没有附加更新说明。</p>
        </div>

        <div v-if="status === 'error' || status === 'unavailable'" class="update-message" :class="`update-message--${status}`">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ errorMessage }}</span>
        </div>

        <div v-if="status === 'unsupported'" class="update-message update-message--info">
          <el-icon><Monitor /></el-icon>
          <span>请打开桌面应用检查和安装版本更新。</span>
        </div>

        <div class="update-actions">
          <el-button
            class="update-check-button"
            :loading="checking"
            :disabled="downloading || !canCheck"
            @click="checkForUpdate({ manual: true })"
          >
            <el-icon v-if="!checking"><Refresh /></el-icon>
            {{ checking ? '正在检查' : '检查版本更新' }}
          </el-button>
          <el-button
            v-if="status === 'available'"
            type="primary"
            class="update-install-button"
            :loading="downloading"
            :disabled="checking"
            @click="confirmAndDownload(availableUpdate, { manual: true })"
          >
            <el-icon v-if="!downloading"><Download /></el-icon>
            {{ downloading ? '正在打开下载' : '下载更新' }}
          </el-button>
        </div>

        <div v-if="lastCheckedAt" class="update-panel__footer">
          <span>上次检查：{{ lastCheckedAt }}</span>
        </div>
      </section>

      <section class="update-info-strip">
        <div class="update-info-strip__icon" aria-hidden="true">
          <el-icon><InfoFilled /></el-icon>
        </div>
        <div>
          <strong>版本更新服务</strong>
          <p>发布新版本后，客户端启动时会自动检查；确认后将在系统浏览器中下载对应版本。</p>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, CircleCheck, Download, InfoFilled, Monitor, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'

import { authStateVersion, hasStoredToken } from '@/utils/auth-storage.js'
import {
  canUseDesktopUpdater,
  checkDesktopUpdate,
  getDesktopVersion,
  downloadDesktopUpdate,
  resolveDesktopUpdateEndpoint,
} from '@/utils/desktop-updater.js'
import { hasNativeDesktopBridge } from '@/utils/native-desktop-bridge.js'

const router = useRouter()
const loading = ref(true)
const checking = ref(false)
const downloading = ref(false)
const status = ref('checking')
const currentVersion = ref('')
const availableUpdate = ref(null)
const errorMessage = ref('')
const lastCheckedAt = ref('')

const authenticated = computed(() => {
  authStateVersion.value
  return hasStoredToken()
})

const isDesktop = computed(() => hasNativeDesktopBridge())
const canCheck = computed(() => Boolean(isDesktop.value && canUseDesktopUpdater()))
const latestVersion = computed(() => {
  if (availableUpdate.value?.version) return availableUpdate.value.version
  if (status.value === 'latest') return currentVersion.value || '已是最新'
  return '--'
})
const latestVersionHint = computed(() => {
  if (status.value === 'available') return '有可下载版本'
  if (status.value === 'latest') return '当前已是最新版本'
  if (status.value === 'checking') return '正在获取版本信息'
  return '等待检查'
})
const statusLabel = computed(() => {
  if (!isDesktop.value) return '不支持浏览器更新'
  if (status.value === 'checking') return '正在检查版本'
  if (status.value === 'available') return '有可用更新'
  if (status.value === 'latest') return '已是最新版本'
  if (status.value === 'unsupported') return '桌面更新不可用'
  if (status.value === 'unavailable') return '未配置服务地址'
  if (status.value === 'error') return '检查失败'
  return '等待检查'
})
const statusTagType = computed(() => {
  if (status.value === 'latest') return 'success'
  if (status.value === 'available') return 'warning'
  if (status.value === 'error' || status.value === 'unavailable') return 'danger'
  return 'info'
})
function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value || '')
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
}

function formatError(error) {
  const detail = String(error?.detail || error?.message || error || '').trim()
  return detail || '检查版本更新失败，请稍后重试。'
}

function markChecked() {
  lastCheckedAt.value = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date())
}

function wasPrompted(version) {
  try {
    return window.sessionStorage.getItem(`desktop_update_prompted:${version}`) === '1'
  } catch {
    return false
  }
}

function markPrompted(version) {
  try {
    window.sessionStorage.setItem(`desktop_update_prompted:${version}`, '1')
  } catch {
    // Session storage is optional; the status page remains usable without it.
  }
}

async function confirmAndDownload(update, options = {}) {
  const version = String(update?.version || '').trim()
  if (!version || downloading.value) return
  if (!options.manual && wasPrompted(version)) return
  markPrompted(version)
  try {
    const notes = String(update?.notes || '').trim()
    const message = notes ? `发现新版本 ${version}\n\n${notes}` : `发现新版本 ${version}`
    await ElMessageBox.confirm(message, '版本更新', {
      type: 'info',
      confirmButtonText: '打开下载',
      cancelButtonText: '稍后处理',
      distinguishCancelAndClose: true,
    })
  } catch {
    return
  }

  downloading.value = true
  try {
    await downloadDesktopUpdate(update)
    ElMessage.success('已打开系统浏览器，请下载对应版本的安装包')
  } catch (error) {
    ElMessage.error(formatError(error))
  } finally {
    downloading.value = false
  }
}

async function checkForUpdate(options = {}) {
  if (checking.value || downloading.value) return
  const manual = Boolean(options.manual)
  checking.value = true
  loading.value = !manual && !currentVersion.value
  availableUpdate.value = null
  errorMessage.value = ''
  status.value = isDesktop.value ? 'checking' : 'unsupported'

  try {
    if (!isDesktop.value) return
    if (!currentVersion.value) {
      currentVersion.value = await getDesktopVersion() || ''
    }
    const endpoint = resolveDesktopUpdateEndpoint()
    if (!endpoint) {
      status.value = 'unavailable'
      errorMessage.value = '未找到后台服务地址，请先配置服务器地址。'
      return
    }
    if (!canUseDesktopUpdater()) {
      status.value = 'unavailable'
      errorMessage.value = '桌面更新功能暂不可用，请重启应用后重试。'
      return
    }
    const update = await checkDesktopUpdate()
    if (update?.currentVersion && !currentVersion.value) {
      currentVersion.value = update.currentVersion
    }
    availableUpdate.value = update?.version ? update : null
    markChecked()
    if (availableUpdate.value) {
      status.value = 'available'
      if (!manual) {
        await confirmAndDownload(availableUpdate.value)
      }
    } else {
      status.value = 'latest'
      if (manual) ElMessage.success('当前已是最新版本')
    }
  } catch (error) {
    status.value = 'error'
    errorMessage.value = formatError(error)
    if (manual) ElMessage.error(errorMessage.value)
  } finally {
    checking.value = false
    loading.value = false
  }
}

onMounted(() => {
  document.title = 'AI 智能体工厂 | 版本更新'
  void checkForUpdate()
})

</script>

<style scoped>
 .update-page {
  min-height: 100dvh;
  color: #182230;
  background: #f5f7fa;
}

 .update-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 68px;
  padding: 12px clamp(20px, 5vw, 72px);
  border-bottom: 1px solid #e4e9ef;
  background: #ffffff;
}

 .update-brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

 .update-brand__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: #1f2937;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

 .update-brand__copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
}

 .update-brand__copy strong {
  font-size: 15px;
  font-weight: 650;
}

 .update-brand__copy span {
  color: #8390a0;
  font-size: 12px;
}

 .update-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

 .update-header__back {
  color: #5f6b7a;
}

 .update-header__workspace {
  --el-button-bg-color: #1f2937;
  --el-button-border-color: #1f2937;
  --el-button-hover-bg-color: #374151;
  --el-button-hover-border-color: #374151;
}

 .update-main {
  display: grid;
  grid-template-columns: minmax(250px, 0.76fr) minmax(0, 1.45fr);
  gap: 28px;
  width: min(1120px, calc(100% - 40px));
  margin: 0 auto;
  padding: 56px 0 64px;
}

 .update-intro {
  align-self: start;
  padding: 18px 0;
}

 .update-intro__eyebrow,
 .update-panel__eyebrow,
 .update-release__eyebrow {
  color: #8a96a5;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.update-intro h1 {
  margin: 18px 0 16px;
  color: #17202c;
  font-size: 56px;
  font-weight: 680;
  line-height: 1.02;
  letter-spacing: 0;
}

 .update-intro p {
  max-width: 300px;
  margin: 0;
  color: #627083;
  font-size: 15px;
  line-height: 1.7;
}

 .update-platform {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-top: 28px;
  color: #7f8b99;
  font-size: 12px;
}

 .update-platform--desktop {
  color: #2563a8;
}

 .update-panel {
  min-width: 0;
  padding: clamp(22px, 4vw, 36px);
  border: 1px solid #e1e7ee;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 16px 42px rgba(31, 41, 55, 0.07);
}

 .update-panel__heading {
  display: flex;
  align-items: center;
  gap: 14px;
}

 .update-panel__status-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  border-radius: 8px;
  background: #eef2f6;
  color: #718096;
}

 .update-panel__status-icon.is-latest {
  background: #ecfdf3;
  color: #17804b;
}

 .update-panel__status-icon.is-available {
  background: #fff7e6;
  color: #b76a00;
}

 .update-panel__status-icon.is-error,
 .update-panel__status-icon.is-unavailable {
  background: #fff1f0;
  color: #c2413b;
}

 .update-panel__heading-copy {
  min-width: 0;
}

 .update-panel__heading-copy h2 {
  margin: 5px 0 0;
  color: #17202c;
  font-size: 22px;
  font-weight: 650;
  line-height: 1.2;
}

 .update-panel__tag {
  margin-left: auto;
}

 .update-version-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 28px;
}

 .update-version {
  display: flex;
  flex-direction: column;
  min-height: 130px;
  padding: 18px;
  border: 1px solid #e7ebf0;
  border-radius: 8px;
  background: #fafbfd;
}

 .update-version--latest {
  border-color: #d7e7f7;
  background: #f5faff;
}

 .update-version__label {
  color: #778496;
  font-size: 12px;
}

 .update-version strong {
  margin-top: 12px;
  color: #17202c;
  font-size: 28px;
  font-weight: 650;
  line-height: 1.1;
  overflow-wrap: anywhere;
}

 .update-version__hint {
  margin-top: auto;
  color: #8c98a7;
  font-size: 12px;
}

 .update-release {
  margin-top: 22px;
  padding: 20px;
  border-left: 3px solid #e0a11a;
  background: #fffaf0;
}

 .update-release__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

 .update-release h3 {
  margin: 8px 0 0;
  color: #3a2b0e;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.4;
}

 .update-release__date {
  flex: 0 0 auto;
  color: #8e7441;
  font-size: 12px;
}

 .update-release__notes {
  margin: 14px 0 0;
  color: #604c24;
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

 .update-release__notes--muted {
  color: #8e7441;
}

 .update-message {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 20px;
  padding: 12px 14px;
  border: 1px solid #dbe4ee;
  color: #526174;
  font-size: 13px;
  line-height: 1.6;
}

 .update-message--error,
 .update-message--unavailable {
  border-color: #f2c7c3;
  background: #fff8f7;
  color: #a53b36;
}

 .update-message--info {
  background: #f5f9fd;
  color: #35658d;
}

 .update-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 28px;
}

 .update-check-button {
  min-width: 156px;
}

 .update-install-button {
  min-width: 132px;
  --el-button-bg-color: #2563a8;
  --el-button-border-color: #2563a8;
  --el-button-hover-bg-color: #1d4f86;
  --el-button-hover-border-color: #1d4f86;
}

 .update-panel__footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 18px;
  color: #9aa5b2;
  font-size: 12px;
}

 .update-info-strip {
  grid-column: 1 / -1;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid #e4e9ef;
  color: #607083;
}

 .update-info-strip__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  border-radius: 50%;
  background: #e9f2fb;
  color: #3973a7;
}

 .update-info-strip strong {
  color: #354255;
  font-size: 13px;
}

 .update-info-strip p {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.6;
}

 @media (max-width: 780px) {
  .update-header {
    align-items: flex-start;
    padding: 12px 16px;
  }

  .update-header__actions {
    gap: 0;
  }

  .update-header__workspace {
    display: none;
  }

  .update-header__back {
    padding-right: 0;
  }

  .update-main {
    display: block;
    width: min(100% - 28px, 620px);
    padding: 34px 0 44px;
  }

  .update-intro {
    padding: 8px 0 28px;
  }

  .update-intro h1 {
    margin-top: 14px;
    font-size: 44px;
  }

  .update-version-grid {
    grid-template-columns: 1fr;
  }

  .update-panel__footer {
    flex-direction: column;
  }

  .update-release__heading {
    flex-direction: column;
    gap: 8px;
  }

  .update-actions {
    flex-direction: column-reverse;
  }

  .update-actions .el-button {
    width: 100%;
    margin-left: 0;
  }
}
</style>
