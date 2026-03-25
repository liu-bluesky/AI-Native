<template>
  <el-dialog
    :model-value="modelValue"
    width="760px"
    align-center
    class="auth-dialog"
    @close="handleClose"
  >
    <div class="auth-dialog__shell">
      <section class="auth-dialog__hero">
        <div class="auth-dialog__eyebrow">Access</div>
        <h2 class="auth-dialog__title">{{ title }}</h2>
        <p class="auth-dialog__text">{{ description }}</p>

        <div class="auth-dialog__signals">
          <span v-for="item in highlights" :key="item">{{ item }}</span>
        </div>
      </section>

      <section class="auth-dialog__panel">
        <div class="auth-dialog__tabs">
          <button
            v-for="item in tabOptions"
            :key="item.value"
            type="button"
            class="auth-dialog__tab"
            :class="{ 'is-active': activeTab === item.value }"
            @click="activeTab = item.value"
          >
            {{ item.label }}
          </button>
        </div>

        <div v-if="activeTab === 'login'" class="auth-dialog__form-wrap">
          <div class="auth-dialog__form-header">
            <div class="auth-dialog__form-title">登录后继续</div>
            <div class="auth-dialog__form-text">输入账号和密码后继续当前入口。</div>
          </div>

          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            label-position="top"
            class="auth-dialog__form"
          >
            <el-form-item label="账号" prop="username">
              <el-input
                v-model="loginForm.username"
                placeholder="请输入账号"
                autocomplete="username"
              />
            </el-form-item>

            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                show-password
                placeholder="请输入密码"
                autocomplete="current-password"
                @keyup.enter="handleLogin"
              />
            </el-form-item>

            <el-button
              type="primary"
              :loading="loginLoading"
              class="auth-dialog__submit"
              @click="handleLogin"
            >
              登录并继续
            </el-button>
          </el-form>
        </div>

        <div v-else class="auth-dialog__form-wrap">
          <div class="auth-dialog__form-header">
            <div class="auth-dialog__form-title">创建新账号</div>
            <div class="auth-dialog__form-text">注册完成后可直接回到当前入口继续浏览。</div>
          </div>

          <el-form
            ref="registerFormRef"
            :model="registerForm"
            :rules="registerRules"
            label-position="top"
            class="auth-dialog__form"
          >
            <el-form-item label="邮箱" prop="email">
              <el-input
                v-model="registerForm.email"
                type="email"
                placeholder="请输入邮箱地址"
                autocomplete="email"
              />
            </el-form-item>

            <el-form-item label="密码" prop="password">
              <el-input
                v-model="registerForm.password"
                type="password"
                show-password
                placeholder="请输入密码（至少 6 位）"
                autocomplete="new-password"
              />
            </el-form-item>

            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input
                v-model="registerForm.confirmPassword"
                type="password"
                show-password
                placeholder="请再次输入密码"
                autocomplete="new-password"
                @keyup.enter="handleRegister"
              />
            </el-form-item>

            <el-button
              type="primary"
              :loading="registerLoading"
              class="auth-dialog__submit"
              @click="handleRegister"
            >
              注册并返回登录
            </el-button>
          </el-form>
        </div>
      </section>
    </div>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ElMessage } from 'element-plus'

import { loginWithPassword, registerWithEmail, resolveSafeRedirectPath } from '@/utils/auth.js'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  defaultMode: {
    type: String,
    default: 'login',
  },
  title: {
    type: String,
    default: '登录后进入市场',
  },
  description: {
    type: String,
    default: '技能、员工和规则统一进入一个目录。登录后继续浏览与接入。',
  },
  successPath: {
    type: String,
    default: '',
  },
  highlights: {
    type: Array,
    default: () => ['技能目录', '员工模板', '规则标准'],
  },
})

const emit = defineEmits(['success', 'update:modelValue'])

const router = useRouter()
const loginFormRef = ref(null)
const registerFormRef = ref(null)
const loginLoading = ref(false)
const registerLoading = ref(false)
const activeTab = ref(props.defaultMode === 'register' ? 'register' : 'login')
const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/

const tabOptions = [
  { label: '登录', value: 'login' },
  { label: '注册', value: 'register' },
]

const loginForm = reactive({
  username: '',
  password: '',
})

const registerForm = reactive({
  email: '',
  password: '',
  confirmPassword: '',
})

const loginRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function validateConfirmPassword(_rule, value, callback) {
  if (!value) {
    callback(new Error('请再次输入密码'))
    return
  }
  if (value !== registerForm.password) {
    callback(new Error('两次输入的密码不一致'))
    return
  }
  callback()
}

const registerRules = {
  email: [
    { required: true, message: '请输入邮箱地址', trigger: 'blur' },
    {
      pattern: EMAIL_PATTERN,
      message: '请输入正确的邮箱地址',
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirmPassword: [{ validator: validateConfirmPassword, trigger: 'blur' }],
}

function resetTransientState() {
  loginLoading.value = false
  registerLoading.value = false
}

function handleClose() {
  emit('update:modelValue', false)
}

async function handleLogin() {
  await loginFormRef.value?.validate()
  loginLoading.value = true
  try {
    await loginWithPassword({
      username: loginForm.username.trim(),
      password: loginForm.password,
    })
    ElMessage.success('登录成功')
    emit('success')
    emit('update:modelValue', false)
    if (props.successPath) {
      await router.replace(resolveSafeRedirectPath(props.successPath, '/market'))
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '登录失败')
  } finally {
    loginLoading.value = false
  }
}

async function handleRegister() {
  await registerFormRef.value?.validate()
  registerLoading.value = true
  try {
    const email = registerForm.email.trim()
    await registerWithEmail({
      email,
      password: registerForm.password,
    })
    loginForm.username = email
    loginForm.password = ''
    activeTab.value = 'login'
    ElMessage.success('注册成功，请登录')
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || '注册失败')
  } finally {
    registerLoading.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) {
      return
    }
    activeTab.value = props.defaultMode === 'register' ? 'register' : 'login'
    resetTransientState()
  },
)
</script>

<style scoped>
.auth-dialog__shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.92fr);
  gap: 14px;
  min-height: 520px;
}

.auth-dialog__hero,
.auth-dialog__panel {
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.76);
  box-shadow:
    0 24px 60px rgba(15, 23, 42, 0.08),
    0 6px 16px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(18px);
}

.auth-dialog__hero {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 28px;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.98), transparent 34%),
    radial-gradient(circle at 78% 16%, rgba(125, 211, 252, 0.14), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(241, 246, 251, 0.84));
}

.auth-dialog__hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
  background-size: 68px 68px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.64), transparent 82%);
  pointer-events: none;
}

.auth-dialog__eyebrow {
  position: relative;
  z-index: 1;
  color: #7c8aa0;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.auth-dialog__title {
  position: relative;
  z-index: 1;
  max-width: 9em;
  margin: 18px 0 0;
  color: #0f172a;
  font-size: clamp(34px, 4vw, 52px);
  line-height: 0.98;
  letter-spacing: -0.06em;
  font-family: 'Avenir Next', 'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.auth-dialog__text {
  position: relative;
  z-index: 1;
  max-width: 460px;
  margin: 18px 0 0;
  color: #475569;
  font-size: 15px;
  line-height: 1.8;
}

.auth-dialog__signals {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 10px;
  margin-top: 28px;
}

.auth-dialog__signals span {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 0 16px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.58);
  color: #475569;
  font-size: 13px;
}

.auth-dialog__panel {
  display: flex;
  flex-direction: column;
  padding: 18px;
}

.auth-dialog__tabs {
  display: inline-flex;
  gap: 8px;
  padding: 6px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.62);
}

.auth-dialog__tab {
  min-height: 36px;
  padding: 0 18px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #64748b;
  font-size: 13px;
  cursor: pointer;
  transition:
    color 220ms ease,
    background-color 220ms ease,
    box-shadow 220ms ease;
}

.auth-dialog__tab.is-active {
  background: #0f172a;
  color: #fff;
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.14);
}

.auth-dialog__form-wrap {
  display: grid;
  gap: 20px;
  margin-top: 20px;
  padding: 12px 8px 4px;
}

.auth-dialog__form-header {
  display: grid;
  gap: 8px;
}

.auth-dialog__form-title {
  color: #0f172a;
  font-size: 28px;
  line-height: 1;
  letter-spacing: -0.05em;
  font-family: 'Avenir Next', 'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.auth-dialog__form-text {
  color: #64748b;
  font-size: 14px;
  line-height: 1.7;
}

.auth-dialog__form {
  display: grid;
}

.auth-dialog__submit {
  min-height: 44px;
  margin-top: 8px;
  --el-button-bg-color: #0f172a;
  --el-button-border-color: #0f172a;
  --el-button-hover-bg-color: #1e293b;
  --el-button-hover-border-color: #1e293b;
  --el-button-active-bg-color: #020617;
  --el-button-active-border-color: #020617;
}

@media (max-width: 860px) {
  .auth-dialog__shell {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .auth-dialog__hero {
    min-height: 240px;
  }
}
</style>
