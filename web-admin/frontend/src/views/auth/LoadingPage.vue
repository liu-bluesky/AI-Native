<template>
  <div class="loading-page">
    <div class="loading-shell">
      <div class="loading-brand">
        <div class="loading-brand__mark">AI</div>
        <div>
          <div class="loading-brand__name">AI 员工工厂</div>
          <div class="loading-brand__meta">正在检查系统状态</div>
        </div>
      </div>

      <div class="loading-orbit" aria-hidden="true">
        <span class="loading-orbit__ring" />
        <span class="loading-orbit__dot" />
      </div>

      <div class="loading-copy">
        <h1>正在进入系统</h1>
        <p>{{ statusText }}</p>
      </div>

      <button v-if="errorText" class="loading-retry" type="button" @click="checkStatus">
        重试
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '@/utils/api.js'
import { getStoredToken } from '@/utils/auth-storage.js'

const router = useRouter()
const statusText = ref('正在确认是否需要初始化')
const errorText = ref('')

function resolveSetupRequired(payload = {}) {
  return payload.setup_required === true || payload.initialized === false
}

async function checkStatus() {
  errorText.value = ''
  statusText.value = '正在确认是否需要初始化'
  try {
    const status = await api.get('/init/status')
    if (resolveSetupRequired(status)) {
      statusText.value = '正在打开初始化页面'
      await router.replace('/init')
      return
    }
    statusText.value = '正在打开登录入口'
    await router.replace(getStoredToken() ? '/workbench' : '/login')
  } catch (err) {
    errorText.value = err?.detail || err?.message || '系统状态检查失败'
    statusText.value = errorText.value
  }
}

onMounted(() => {
  void checkStatus()
})
</script>

<style scoped>
.loading-page {
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(circle at 18% 10%, rgba(125, 211, 252, 0.2), transparent 26%),
    radial-gradient(circle at 82% 18%, rgba(45, 212, 191, 0.16), transparent 24%),
    linear-gradient(180deg, #f2efe6 0%, #f7fafc 44%, #e8edf5 100%);
}

.loading-shell {
  width: min(420px, 100%);
  min-height: 420px;
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 22px;
  padding: 32px 24px;
  text-align: center;
}

.loading-brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.loading-brand__mark {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: #111827;
  color: #f8fafc;
  font-size: 13px;
  font-weight: 800;
}

.loading-brand__name {
  text-align: left;
  font-size: 15px;
  font-weight: 800;
  color: #111827;
}

.loading-brand__meta {
  margin-top: 2px;
  text-align: left;
  font-size: 12px;
  color: #64748b;
}

.loading-orbit {
  position: relative;
  width: 86px;
  height: 86px;
}

.loading-orbit__ring {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-top-color: #111827;
  animation: loading-spin 0.9s linear infinite;
}

.loading-orbit__dot {
  position: absolute;
  inset: 24px;
  border-radius: 999px;
  background: linear-gradient(180deg, #ffffff, #e2e8f0);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 16px 32px rgba(15, 23, 42, 0.12);
}

.loading-copy h1 {
  margin: 0;
  font-size: 28px;
  line-height: 1.2;
  color: #111827;
}

.loading-copy p {
  margin: 10px 0 0;
  font-size: 14px;
  line-height: 1.6;
  color: #64748b;
}

.loading-retry {
  min-width: 112px;
  height: 40px;
  border: 0;
  border-radius: 12px;
  background: #111827;
  color: #f8fafc;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}

@keyframes loading-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
