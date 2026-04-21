<template>
  <AuthDesktopShell
    eyebrow="Desktop Access"
    title="进入你的 AI 桌面系统"
    description="登录后进入统一工作桌面，在同一套系统窗口里继续项目、素材、能力市场和 AI 工作台。"
    panel-title="Sign In"
    :features="loginFeatures"
    :dock-items="dockPreview"
  >
    <div class="login-panel__header">
      <div class="login-panel__eyebrow">账号登录</div>
      <div class="login-panel__title">欢迎回来</div>
      <div class="login-panel__text">输入账号和密码后进入桌面工作区。</div>
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
          登录并进入桌面
        </el-button>
      </el-form-item>
    </el-form>

    <div class="login-panel__footer">
      <span class="login-panel__footer-text">还没有账号？</span>
      <el-button text class="login-panel__link" @click="router.replace('/register')">
        去注册
      </el-button>
    </div>
  </AuthDesktopShell>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import AuthDesktopShell from "@/components/auth/AuthDesktopShell.vue";
import { loginWithPassword, resolveSafeRedirectPath } from "@/utils/auth.js";

const route = useRoute();
const router = useRouter();
const formRef = ref(null);
const loading = ref(false);

const dockPreview = ["AI", "PR", "MT", "MK", "SE"];
const loginFeatures = [
  {
    title: "AI 工作台",
    text: "继续当前项目的对话、执行链路和工作上下文。",
  },
  {
    title: "项目应用",
    text: "把项目、素材和设置都收束成桌面里的独立小应用。",
  },
  {
    title: "连续状态",
    text: "登录后保留统一入口和桌面式系统感，不再跳散页。",
  },
];

const form = reactive({ username: "", password: "" });
const rules = {
  username: [{ required: true, message: "请输入账号", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

async function handleLogin() {
  await formRef.value.validate();
  loading.value = true;
  try {
    await loginWithPassword({
      username: form.username.trim(),
      password: form.password,
    });
    ElMessage.success("登录成功");
    await router.replace(resolveSafeRedirectPath(route.query.redirect, "/workbench"));
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "账号或密码错误");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-panel__header {
  margin-bottom: 18px;
}

.login-panel__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #64748b;
}

.login-panel__title {
  margin-top: 8px;
  font-size: 28px;
  line-height: 1.1;
  font-weight: 700;
  color: #111827;
}

.login-panel__text {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #64748b;
}

.login-form :deep(.el-form-item__label) {
  color: #334155;
  font-weight: 600;
}

.login-form__submit {
  margin-top: 8px;
  margin-bottom: 0;
}

.login-submit {
  width: 100%;
  height: 44px;
  border-radius: 14px;
  border: 0;
  background: linear-gradient(180deg, #111827, #1f2937);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.16);
}

.login-panel__footer {
  margin-top: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
}

.login-panel__footer-text {
  color: #64748b;
}

.login-panel__link {
  font-weight: 600;
}
</style>
