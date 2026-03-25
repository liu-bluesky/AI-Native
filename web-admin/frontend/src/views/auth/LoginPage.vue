<template>
  <div class="login-page">
    <div class="login-shell">
      <section class="login-hero">
        <div class="login-brand">
          <div class="login-brand__mark">AI</div>
          <div>
            <div class="login-brand__name">AI 员工工厂</div>
            <div class="login-brand__meta">对话、员工与能力协同</div>
          </div>
        </div>

        <div class="login-hero__copy">
          <h1 class="login-hero__title">进入你的 AI 工作台</h1>
          <p class="login-hero__text">
            登录后直接进入 AI 对话，继续项目会话、调用技能资源，并管理员工与规则。
          </p>
        </div>

        <div class="login-hero__panel">
          <div class="login-hero__panel-title">登录后可继续</div>
          <div class="login-hero__list">
            <div class="login-hero__item">
              <div class="login-hero__item-name">项目对话</div>
              <div class="login-hero__item-text">保留当前项目上下文与历史会话</div>
            </div>
            <div class="login-hero__item">
              <div class="login-hero__item-name">技能资源</div>
              <div class="login-hero__item-text">搜索、下载并接入本地技能目录</div>
            </div>
            <div class="login-hero__item">
              <div class="login-hero__item-name">员工协作</div>
              <div class="login-hero__item-text">继续使用员工、规则和工具链配置</div>
            </div>
          </div>
        </div>
      </section>

      <section class="login-panel">
        <div class="login-panel__header">
          <div class="login-panel__eyebrow">账号登录</div>
          <div class="login-panel__title">欢迎回来</div>
          <div class="login-panel__text">输入账号和密码后进入 AI 对话。</div>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          class="login-form"
        >
          <el-form-item label="账号" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入账号"
              autocomplete="username"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              placeholder="请输入密码"
              autocomplete="current-password"
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item class="login-form__submit">
            <el-button
              type="primary"
              :loading="loading"
              class="login-submit"
              @click="handleLogin"
            >
              登录并进入对话
            </el-button>
          </el-form-item>
        </el-form>

        <div class="login-panel__footer">
          <span class="login-panel__footer-text">还没有账号？</span>
          <el-button text class="login-panel__link" @click="router.replace('/register')">
            去注册
          </el-button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ElMessage } from 'element-plus'

import { loginWithPassword, resolveSafeRedirectPath } from '@/utils/auth.js'

const route = useRoute()
const router = useRouter()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  await formRef.value.validate()
  loading.value = true
  try {
    await loginWithPassword({
      username: form.username.trim(),
      password: form.password,
    })
    ElMessage.success('登录成功')
    await router.replace(resolveSafeRedirectPath(route.query.redirect, '/ai/chat'))
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '账号或密码错误')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  position: relative;
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: clamp(12px, 2vw, 24px);
  box-sizing: border-box;
  overflow: clip;
  isolation: isolate;
  container-type: inline-size;
  background:
    radial-gradient(circle at 18% 0%, rgba(125, 211, 252, 0.16), transparent 26%),
    radial-gradient(circle at 82% 14%, rgba(103, 232, 249, 0.12), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%);
}

.login-page::before,
.login-page::after {
  content: "";
  position: absolute;
  border-radius: 50%;
  filter: blur(72px);
  pointer-events: none;
  opacity: 0.7;
}

.login-page::before {
  top: -9rem;
  left: -10rem;
  width: 28rem;
  height: 28rem;
  background: rgba(125, 211, 252, 0.36);
}

.login-page::after {
  right: -8rem;
  top: 8rem;
  width: 24rem;
  height: 24rem;
  background: rgba(103, 232, 249, 0.24);
}

.login-shell {
  position: relative;
  z-index: 1;
  width: min(1120px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(320px, clamp(360px, 36vw, 420px));
  gap: clamp(12px, 1.8vw, 18px);
  align-items: stretch;
  animation: loginFadeUp 0.7s cubic-bezier(0.2, 0.8, 0.2, 1) both;
}

:where(.login-hero, .login-panel) {
  min-width: 0;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.76);
  box-shadow:
    0 28px 74px rgba(15, 23, 42, 0.08),
    0 6px 18px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(18px);
}

.login-hero {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: clamp(560px, 72vh, 620px);
  padding: clamp(20px, 2.2vw, 28px);
  border-radius: 34px;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.98), transparent 34%),
    radial-gradient(circle at 78% 18%, rgba(125, 211, 252, 0.14), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(241, 246, 251, 0.84));
  overflow: hidden;
}

.login-hero::after {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.66), transparent 80%);
  pointer-events: none;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.login-brand__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  background: #111827;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.login-brand__name {
  color: #111827;
  font-size: 16px;
  line-height: 1.2;
  font-weight: 600;
  font-family: "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.login-brand__meta {
  margin-top: 2px;
  color: #8b8d93;
  font-size: 11px;
  line-height: 1.3;
}

.login-hero__copy {
  width: min(100%, 560px);
  margin: 48px 0 28px;
  min-width: 0;
}

.login-hero__title {
  margin: 0;
  color: #111827;
  font-size: clamp(34px, 4vw, 52px);
  line-height: 1.04;
  font-weight: 700;
  letter-spacing: -0.04em;
  text-wrap: balance;
}

.login-hero__text {
  max-width: 520px;
  margin: 18px 0 0;
  color: #5b6470;
  font-size: 16px;
  line-height: 1.8;
}

.login-hero__panel {
  position: relative;
  width: min(100%, 520px);
  padding: 18px 18px 8px;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.76);
  background: rgba(255, 255, 255, 0.62);
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(16px);
}

.login-hero__panel-title {
  margin-bottom: 12px;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.login-hero__list {
  display: grid;
  gap: 14px;
}

.login-hero__item {
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(17, 24, 39, 0.06);
}

.login-hero__item:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.login-hero__item-name {
  color: #111827;
  font-size: 14px;
  font-weight: 600;
}

.login-hero__item-text {
  margin-top: 4px;
  color: #7a838f;
  font-size: 13px;
  line-height: 1.65;
}

.login-panel {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: clamp(560px, 72vh, 620px);
  padding: clamp(22px, 2.4vw, 34px) clamp(18px, 2.2vw, 30px);
  border-radius: 30px;
  background:
    radial-gradient(circle at top right, rgba(125, 211, 252, 0.12), transparent 28%),
    rgba(255, 255, 255, 0.78);
}

.login-panel__header {
  margin-bottom: 22px;
}

.login-panel__eyebrow {
  color: #8b8d93;
  font-size: 11px;
  line-height: 1.4;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.login-panel__title {
  margin-top: 10px;
  color: #111827;
  font-size: 30px;
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.03em;
  text-wrap: balance;
}

.login-panel__text {
  margin-top: 10px;
  color: #6b7280;
  font-size: 13px;
  line-height: 1.7;
}

.login-form {
  width: 100%;
  min-width: 0;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.login-form :deep(.el-form-item__label) {
  padding-bottom: 8px;
  color: #111827;
  font-size: 13px;
  font-weight: 600;
}

.login-form :deep(.el-input__wrapper) {
  min-height: 48px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: inset 0 0 0 1px rgba(17, 24, 39, 0.08);
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    inset 0 0 0 1px rgba(17, 24, 39, 0.14),
    0 8px 18px rgba(15, 23, 42, 0.04);
}

.login-form__submit {
  margin-top: 10px;
  margin-bottom: 0;
}

.login-submit {
  position: relative;
  overflow: hidden;
  width: 100%;
  min-height: 46px;
  border: 0 !important;
  border-radius: 18px !important;
  background: #111827 !important;
  color: #fff !important;
  font-weight: 600 !important;
  box-shadow: 0 14px 30px rgba(15, 23, 42, 0.14) !important;
}

.login-submit:hover {
  background: #0f172a !important;
}

.login-submit::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 16%, rgba(255, 255, 255, 0.3) 50%, transparent 84%);
  transform: translateX(-130%);
  animation: loginButtonSweep 5s ease-in-out infinite;
}

:is(.login-submit, .login-panel__link):focus-visible {
  outline: 2px solid rgba(17, 24, 39, 0.24);
  outline-offset: 3px;
}

.login-panel__footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin-top: 18px;
  color: #8b8d93;
  font-size: 13px;
}

.login-panel__footer-text {
  color: #8b8d93;
}

.login-panel__link {
  padding: 0 4px !important;
  color: #111827 !important;
  font-weight: 600;
}

@container (max-width: 920px) {
  .login-shell {
    grid-template-columns: 1fr;
  }

  .login-hero,
  .login-panel {
    min-height: auto;
  }

  .login-hero {
    padding: 24px;
  }

  .login-hero__copy {
    margin: 34px 0 22px;
  }

  .login-panel {
    padding: 28px 22px;
  }
}

@container (max-width: 620px) {
  .login-hero,
  .login-panel {
    border-radius: 24px;
  }

  .login-hero {
    padding: 20px;
  }

  .login-panel {
    padding: 22px 18px;
  }

  .login-hero__title {
    font-size: 34px;
  }

  .login-hero__text {
    font-size: 15px;
  }
}

@keyframes loginFadeUp {
  from {
    opacity: 0;
    transform: translate3d(0, 20px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

@keyframes loginButtonSweep {
  0%,
  72%,
  100% {
    transform: translateX(-130%);
  }
  88% {
    transform: translateX(130%);
  }
}
</style>
