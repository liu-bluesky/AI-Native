<template>
  <router-view />
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from './utils/api.js'

const router = useRouter()

onMounted(async () => {
  try {
    const { initialized } = await api.get('/init/status')
    if (!initialized) {
      router.replace('/init')
      return
    }
    const token = localStorage.getItem('token')
    if (!token && router.currentRoute.value.path !== '/login') {
      router.replace('/login')
    }
  } catch {
    router.replace('/login')
  }
})
</script>
