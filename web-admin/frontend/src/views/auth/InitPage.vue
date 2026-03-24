<template>
  <div class="init-page">
    <div class="init-shell">
      <section class="init-hero">
        <div class="init-brand">
          <div class="init-brand__mark">AI</div>
          <div>
            <div class="init-brand__name">AI 员工工厂</div>
            <div class="init-brand__meta">首次初始化</div>
          </div>
        </div>

        <div class="init-hero__copy">
          <h1 class="init-hero__title">先完成系统初始化</h1>
          <p class="init-hero__text">
            为平台创建第一个管理员账号，初始化完成后即可登录并进入 AI 对话与管理功能。
          </p>
        </div>

        <div class="init-hero__panel">
          <div class="init-hero__panel-title">初始化会完成</div>
          <div class="init-hero__list">
            <div class="init-hero__item">
              <div class="init-hero__item-name">管理员账号</div>
              <div class="init-hero__item-text">创建首个可登录的系统管理员用户。</div>
            </div>
            <div class="init-hero__item">
              <div class="init-hero__item-name">基础入口</div>
              <div class="init-hero__item-text">完成登录、项目、员工和能力管理的起始配置。</div>
            </div>
            <div class="init-hero__item">
              <div class="init-hero__item-name">后续流程</div>
              <div class="init-hero__item-text">初始化成功后会直接跳转登录页。</div>
            </div>
          </div>
        </div>
      </section>

      <section class="init-panel">
        <div class="init-panel__header">
          <div class="init-panel__eyebrow">系统初始化</div>
          <div class="init-panel__title">创建管理员</div>
          <div class="init-panel__text">填写管理员账号和密码，完成首次系统启动。</div>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          class="init-form"
        >
          <el-form-item label="管理员账号" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入管理员账号"
              autocomplete="username"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              placeholder="至少 6 位"
              autocomplete="new-password"
            />
          </el-form-item>

          <el-form-item label="确认密码" prop="confirm">
            <el-input
              v-model="form.confirm"
              type="password"
              show-password
              placeholder="再次输入密码"
              autocomplete="new-password"
              @keyup.enter="handleSubmit"
            />
          </el-form-item>

          <el-form-item class="init-form__submit">
            <el-button
              type="primary"
              :loading="loading"
              class="init-submit"
              @click="handleSubmit"
            >
              初始化系统
            </el-button>
          </el-form-item>
        </el-form>
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
const formRef = ref(null);
const loading = ref(false);

const form = reactive({
  username: "admin",
  password: "",
  confirm: "",
});

const rules = {
  username: [{ required: true, message: "请输入账号", trigger: "blur" }],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, message: "密码至少6位", trigger: "blur" },
  ],
  confirm: [
    { required: true, message: "请确认密码", trigger: "blur" },
    {
      validator: (_, val, cb) => {
        val === form.password ? cb() : cb(new Error("两次密码不一致"));
      },
      trigger: "blur",
    },
  ],
};

async function handleSubmit() {
  await formRef.value.validate();
  loading.value = true;
  try {
    await api.post("/init/setup", {
      username: form.username,
      password: form.password,
    });
    ElMessage.success("初始化成功，请登录");
    router.replace("/login");
  } catch (e) {
    ElMessage.error(e.detail || "初始化失败");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.init-page {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background:
    radial-gradient(circle at 18% 0%, rgba(125, 211, 252, 0.16), transparent 26%),
    radial-gradient(circle at 82% 14%, rgba(103, 232, 249, 0.12), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%);
}

.init-shell {
  width: min(1120px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(360px, 430px);
  gap: 18px;
  align-items: stretch;
}

.init-hero,
.init-panel {
  border: 1px solid rgba(255, 255, 255, 0.96);
  background: rgba(255, 255, 255, 0.82);
  box-shadow:
    0 26px 64px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(14px);
}

.init-hero {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 640px;
  padding: 28px;
  border-radius: 34px;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.98), transparent 34%),
    radial-gradient(circle at 78% 18%, rgba(125, 211, 252, 0.14), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(241, 246, 251, 0.84));
}

.init-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.init-brand__mark {
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

.init-brand__name {
  color: #111827;
  font-size: 16px;
  line-height: 1.2;
  font-weight: 600;
  font-family: "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.init-brand__meta {
  margin-top: 2px;
  color: #8b8d93;
  font-size: 11px;
  line-height: 1.3;
}

.init-hero__copy {
  max-width: 560px;
  margin: 48px 0 28px;
}

.init-hero__title {
  margin: 0;
  color: #111827;
  font-size: clamp(34px, 4vw, 52px);
  line-height: 1.04;
  font-weight: 700;
  letter-spacing: -0.04em;
}

.init-hero__text {
  max-width: 520px;
  margin: 18px 0 0;
  color: #5b6470;
  font-size: 16px;
  line-height: 1.8;
}

.init-hero__panel {
  max-width: 520px;
  padding: 18px 18px 8px;
  border-radius: 24px;
  border: 1px solid rgba(17, 24, 39, 0.06);
  background: rgba(255, 255, 255, 0.72);
}

.init-hero__panel-title {
  margin-bottom: 12px;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.init-hero__list {
  display: grid;
  gap: 14px;
}

.init-hero__item {
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(17, 24, 39, 0.06);
}

.init-hero__item:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.init-hero__item-name {
  color: #111827;
  font-size: 14px;
  font-weight: 600;
}

.init-hero__item-text {
  margin-top: 4px;
  color: #7a838f;
  font-size: 13px;
  line-height: 1.65;
}

.init-panel {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 640px;
  padding: 34px 30px;
  border-radius: 30px;
}

.init-panel__header {
  margin-bottom: 22px;
}

.init-panel__eyebrow {
  color: #8b8d93;
  font-size: 11px;
  line-height: 1.4;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.init-panel__title {
  margin-top: 10px;
  color: #111827;
  font-size: 30px;
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.init-panel__text {
  margin-top: 10px;
  color: #6b7280;
  font-size: 13px;
  line-height: 1.7;
}

.init-form {
  width: 100%;
}

.init-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.init-form :deep(.el-form-item__label) {
  padding-bottom: 8px;
  color: #111827;
  font-size: 13px;
  font-weight: 600;
}

.init-form :deep(.el-input__wrapper) {
  min-height: 48px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: inset 0 0 0 1px rgba(17, 24, 39, 0.08);
}

.init-form :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    inset 0 0 0 1px rgba(17, 24, 39, 0.14),
    0 8px 18px rgba(15, 23, 42, 0.04);
}

.init-form__submit {
  margin-top: 10px;
  margin-bottom: 0;
}

.init-submit {
  width: 100%;
  min-height: 46px;
  border: 0 !important;
  border-radius: 18px !important;
  background: #111827 !important;
  color: #fff !important;
  font-weight: 600 !important;
  box-shadow: 0 14px 30px rgba(15, 23, 42, 0.14) !important;
}

.init-submit:hover {
  background: #0f172a !important;
}

@media (max-width: 960px) {
  .init-page {
    padding: 16px;
  }

  .init-shell {
    grid-template-columns: 1fr;
  }

  .init-hero,
  .init-panel {
    min-height: auto;
  }

  .init-hero {
    padding: 24px;
  }

  .init-hero__copy {
    margin: 34px 0 22px;
  }

  .init-panel {
    padding: 28px 22px;
  }
}

@media (max-width: 640px) {
  .init-page {
    padding: 12px;
  }

  .init-hero,
  .init-panel {
    border-radius: 24px;
  }

  .init-hero {
    padding: 20px;
  }

  .init-panel {
    padding: 22px 18px;
  }

  .init-hero__title {
    font-size: 34px;
  }

  .init-hero__text {
    font-size: 15px;
  }
}
</style>
