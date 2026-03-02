<template>
  <div class="init-page">
    <el-card class="init-card">
      <template #header>
        <h2>AI 员工工厂 — 系统初始化</h2>
      </template>
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="管理员账号" prop="username">
          <el-input v-model="form.username" placeholder="请输入管理员账号" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="至少6位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="form.confirm" type="password" show-password placeholder="再次输入密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSubmit">初始化系统</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  username: 'admin',
  password: '',
  confirm: '',
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_, val, cb) => {
        val === form.password ? cb() : cb(new Error('两次密码不一致'))
      },
      trigger: 'blur',
    },
  ],
}

async function handleSubmit() {
  await formRef.value.validate()
  loading.value = true
  try {
    await api.post('/init/setup', {
      username: form.username,
      password: form.password,
    })
    ElMessage.success('初始化成功，请登录')
    router.replace('/login')
  } catch (e) {
    ElMessage.error(e.detail || '初始化失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.init-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-layout);
}
.init-card {
  width: 460px;
}
.init-card h2 {
  margin: 0;
  font-size: 20px;
  text-align: center;
  color: var(--color-text-primary);
}
</style>
