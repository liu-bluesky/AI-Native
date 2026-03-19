<template>
  <div class="register-page">
    <div class="register-shell">
      <section class="register-hero">
        <div class="register-brand">
          <div class="register-brand__mark">AI</div>
          <div>
            <div class="register-brand__name">AI 员工工厂</div>
            <div class="register-brand__meta">新账号接入</div>
          </div>
        </div>

        <div class="register-hero__copy">
          <h1 class="register-hero__title">创建你的协作账号</h1>
          <p class="register-hero__text">
            创建完成后回到登录页，随后进入 AI 对话、项目协作和技能资源能力面板。
          </p>
        </div>

        <div class="register-hero__panel">
          <div class="register-hero__panel-title">账号要求</div>
          <div class="register-hero__chips">
            <span class="register-hero__chip">使用邮箱注册</span>
            <span class="register-hero__chip">校验邮箱格式</span>
            <span class="register-hero__chip">密码至少 6 位</span>
          </div>
          <div class="register-hero__summary">
            注册完成后会回到登录页，你可以直接用新账号进入 AI 对话。
          </div>
          <div class="register-hero__list">
            <div class="register-hero__item">
              <div class="register-hero__item-name">推荐做法</div>
              <div class="register-hero__item-text">
                使用常用邮箱完成注册，密码避免与常用密码重复。
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="register-panel">
        <div class="register-panel__header">
          <div class="register-panel__eyebrow">创建账号</div>
          <div class="register-panel__title">开始使用</div>
          <div class="register-panel__text">填写基础信息后创建一个新的平台账号。</div>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          class="register-form"
        >
          <el-form-item label="邮箱" prop="email">
            <el-input
              v-model="form.email"
              type="email"
              placeholder="请输入邮箱地址"
              autocomplete="email"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              placeholder="请输入密码（至少 6 位）"
              autocomplete="new-password"
            />
          </el-form-item>

          <el-form-item label="确认密码" prop="confirmPassword">
            <el-input
              v-model="form.confirmPassword"
              type="password"
              show-password
              placeholder="请再次输入密码"
              autocomplete="new-password"
              @keyup.enter="handleRegister"
            />
          </el-form-item>

          <div class="register-form__hint">
            创建成功后不会自动登录，会先跳回登录页完成验证。
          </div>

          <el-form-item class="register-form__submit">
            <el-button
              type="primary"
              :loading="loading"
              class="register-submit"
              @click="handleRegister"
            >
              创建账号
            </el-button>
          </el-form-item>
        </el-form>

        <div class="register-panel__footer">
          <span class="register-panel__footer-text">已有账号？</span>
          <el-button text class="register-panel__link" @click="router.replace('/login')">
            去登录
          </el-button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import api from "@/utils/api.js";

const router = useRouter();
const loading = ref(false);
const formRef = ref(null);
const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
const form = reactive({
  email: "",
  password: "",
  confirmPassword: "",
});

const validateConfirmPassword = (_rule, value, callback) => {
  if (!value) {
    callback(new Error("请再次输入密码"));
    return;
  }
  if (value !== form.password) {
    callback(new Error("两次输入的密码不一致"));
    return;
  }
  callback();
};

const rules = {
  email: [
    { required: true, message: "请输入邮箱地址", trigger: "blur" },
    {
      pattern: EMAIL_PATTERN,
      message: "请输入正确的邮箱地址",
      trigger: "blur",
    },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, message: "密码至少 6 位", trigger: "blur" },
  ],
  confirmPassword: [{ validator: validateConfirmPassword, trigger: "blur" }],
};

async function handleRegister() {
  await formRef.value.validate();
  loading.value = true;
  try {
    const email = form.email.trim();
    await api.post("/auth/register", {
      email,
      password: form.password,
    });
    ElMessage.success("注册成功，请登录");
    await router.replace("/login");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "注册失败");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.register-page {
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
    radial-gradient(circle at 16% 0%, rgba(125, 211, 252, 0.22), transparent 28%),
    radial-gradient(circle at 84% 16%, rgba(103, 232, 249, 0.16), transparent 24%),
    linear-gradient(180deg, #f6f4ef 0%, #f7f8fa 34%, #eef2f7 100%);
}

.register-page::before,
.register-page::after {
  content: "";
  position: absolute;
  border-radius: 50%;
  filter: blur(72px);
  pointer-events: none;
  opacity: 0.7;
}

.register-page::before {
  top: -9rem;
  left: -10rem;
  width: 28rem;
  height: 28rem;
  background: rgba(125, 211, 252, 0.42);
}

.register-page::after {
  right: -8rem;
  top: 8rem;
  width: 24rem;
  height: 24rem;
  background: rgba(103, 232, 249, 0.28);
}

.register-shell {
  position: relative;
  z-index: 1;
  width: min(1120px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(320px, clamp(360px, 37vw, 430px));
  gap: clamp(12px, 1.8vw, 18px);
  align-items: stretch;
  animation: registerFadeUp 0.7s cubic-bezier(0.2, 0.8, 0.2, 1) both;
}

:where(.register-hero, .register-panel) {
  min-width: 0;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.76);
  box-shadow:
    0 28px 74px rgba(15, 23, 42, 0.08),
    0 6px 18px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(18px);
}

.register-hero {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: clamp(580px, 74vh, 660px);
  padding: clamp(20px, 2.2vw, 28px);
  border-radius: 34px;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.98), transparent 34%),
    radial-gradient(circle at 78% 18%, rgba(125, 211, 252, 0.14), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(241, 246, 251, 0.84));
  overflow: hidden;
}

.register-hero::after {
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

.register-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.register-brand__mark {
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

.register-brand__name {
  color: #111827;
  font-size: 16px;
  line-height: 1.2;
  font-weight: 600;
  font-family: "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.register-brand__meta {
  margin-top: 2px;
  color: #8b8d93;
  font-size: 11px;
  line-height: 1.3;
}

.register-hero__copy {
  width: min(100%, 560px);
  margin: 48px 0 28px;
  min-width: 0;
}

.register-hero__title {
  margin: 0;
  color: #111827;
  font-size: clamp(34px, 4vw, 52px);
  line-height: 1.04;
  font-weight: 700;
  letter-spacing: -0.04em;
  text-wrap: balance;
}

.register-hero__text {
  max-width: 520px;
  margin: 18px 0 0;
  color: #5b6470;
  font-size: 16px;
  line-height: 1.8;
}

.register-hero__panel {
  position: relative;
  width: min(100%, 520px);
  padding: 18px 18px 8px;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.76);
  background: rgba(255, 255, 255, 0.62);
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(16px);
}

.register-hero__panel-title {
  margin-bottom: 12px;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.register-hero__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.register-hero__chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(17, 24, 39, 0.06);
  background: rgba(255, 255, 255, 0.78);
  color: #4b5563;
  font-size: 12px;
  font-weight: 500;
}

.register-hero__summary {
  margin-top: 12px;
  color: #6b7280;
  font-size: 13px;
  line-height: 1.65;
}

.register-hero__list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.register-hero__item {
  padding-top: 14px;
  border-top: 1px solid rgba(17, 24, 39, 0.06);
}

.register-hero__item-name {
  color: #111827;
  font-size: 14px;
  font-weight: 600;
}

.register-hero__item-text {
  margin-top: 4px;
  color: #7a838f;
  font-size: 13px;
  line-height: 1.65;
}

.register-panel {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: clamp(580px, 74vh, 660px);
  padding: clamp(22px, 2.4vw, 34px) clamp(18px, 2.2vw, 30px);
  border-radius: 30px;
  background:
    radial-gradient(circle at top right, rgba(125, 211, 252, 0.12), transparent 28%),
    rgba(255, 255, 255, 0.78);
}

.register-panel__header {
  margin-bottom: 22px;
}

.register-panel__eyebrow {
  color: #8b8d93;
  font-size: 11px;
  line-height: 1.4;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.register-panel__title {
  margin-top: 10px;
  color: #111827;
  font-size: 30px;
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.03em;
  text-wrap: balance;
}

.register-panel__text {
  margin-top: 10px;
  color: #6b7280;
  font-size: 13px;
  line-height: 1.7;
}

.register-form {
  width: 100%;
  min-width: 0;
}

.register-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.register-form :deep(.el-form-item__label) {
  padding-bottom: 8px;
  color: #111827;
  font-size: 13px;
  font-weight: 600;
}

.register-form :deep(.el-input__wrapper) {
  min-height: 48px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: inset 0 0 0 1px rgba(17, 24, 39, 0.08);
}

.register-form :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    inset 0 0 0 1px rgba(17, 24, 39, 0.14),
    0 8px 18px rgba(15, 23, 42, 0.04);
}

.register-form__hint {
  margin: 2px 0 18px;
  color: #8b8d93;
  font-size: 12px;
  line-height: 1.6;
}

.register-form__submit {
  margin-top: 10px;
  margin-bottom: 0;
}

.register-submit {
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

.register-submit:hover {
  background: #0f172a !important;
}

.register-submit::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 16%, rgba(255, 255, 255, 0.3) 50%, transparent 84%);
  transform: translateX(-130%);
  animation: registerButtonSweep 5s ease-in-out infinite;
}

:is(.register-submit, .register-panel__link):focus-visible {
  outline: 2px solid rgba(17, 24, 39, 0.24);
  outline-offset: 3px;
}

.register-panel__footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin-top: 18px;
  color: #8b8d93;
  font-size: 13px;
}

.register-panel__footer-text {
  color: #8b8d93;
}

.register-panel__link {
  padding: 0 4px !important;
  color: #111827 !important;
  font-weight: 600;
}

@container (max-width: 920px) {
  .register-shell {
    grid-template-columns: 1fr;
  }

  .register-hero,
  .register-panel {
    min-height: auto;
  }

  .register-hero {
    padding: 24px;
  }

  .register-hero__copy {
    margin: 34px 0 22px;
  }

  .register-panel {
    padding: 28px 22px;
  }
}

@container (max-width: 620px) {
  .register-hero,
  .register-panel {
    border-radius: 24px;
  }

  .register-hero {
    padding: 20px;
  }

  .register-panel {
    padding: 22px 18px;
  }

  .register-hero__title {
    font-size: 34px;
  }

  .register-hero__text {
    font-size: 15px;
  }
}

@keyframes registerFadeUp {
  from {
    opacity: 0;
    transform: translate3d(0, 20px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

@keyframes registerButtonSweep {
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
