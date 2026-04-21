<template>
  <AuthDesktopShell
    eyebrow="Create Access"
    title="创建进入桌面系统的账号"
    description="先完成账号接入，再回到登录页进入统一桌面。后续工作台、项目和市场会共用这一套系统入口。"
    panel-title="Create Account"
    :features="registerFeatures"
    :dock-items="dockPreview"
  >
    <div class="register-panel__header">
      <div class="register-panel__eyebrow">创建账号</div>
      <div class="register-panel__title">开始使用</div>
      <div class="register-panel__text">填写基础信息后创建新的平台账号。</div>
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
        创建成功后不会自动登录，会先返回登录页。
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
  </AuthDesktopShell>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import AuthDesktopShell from "@/components/auth/AuthDesktopShell.vue";
import { registerWithEmail, resolveSafeRedirectPath } from "@/utils/auth.js";

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const formRef = ref(null);
const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

const dockPreview = ["AI", "PR", "MT", "MK", "SE"];
const registerFeatures = [
  {
    title: "统一入口",
    text: "认证完成后回到同一套桌面系统，不为不同应用重复接入。",
  },
  {
    title: "系统账号",
    text: "账号用于连接项目、能力市场和后续桌面式系统导航。",
  },
  {
    title: "轻量流程",
    text: "注册路径保持克制，把认知焦点放在进入系统，而不是堆表单说明。",
  },
];

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
    await registerWithEmail({
      email,
      password: form.password,
    });
    ElMessage.success("注册成功，请登录");
    const redirect = resolveSafeRedirectPath(route.query.redirect, "");
    await router.replace(
      redirect ? { path: "/login", query: { redirect } } : "/login",
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "注册失败");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.register-panel__header {
  margin-bottom: 18px;
}

.register-panel__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #64748b;
}

.register-panel__title {
  margin-top: 8px;
  font-size: 28px;
  line-height: 1.1;
  font-weight: 700;
  color: #111827;
}

.register-panel__text {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #64748b;
}

.register-form :deep(.el-form-item__label) {
  color: #334155;
  font-weight: 600;
}

.register-form__hint {
  margin-top: -4px;
  margin-bottom: 14px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

.register-form__submit {
  margin-bottom: 0;
}

.register-submit {
  width: 100%;
  height: 44px;
  border-radius: 14px;
  border: 0;
  background: linear-gradient(180deg, #111827, #1f2937);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.16);
}

.register-panel__footer {
  margin-top: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
}

.register-panel__footer-text {
  color: #64748b;
}

.register-panel__link {
  font-weight: 600;
}
</style>
