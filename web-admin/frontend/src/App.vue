<template>
  <router-view />
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import api from './utils/api.js'
import { syncCurrentUser } from './utils/auth.js'
import { clearAuthSession, getStoredToken } from './utils/auth-storage.js'

const router = useRouter()

onMounted(async () => {
  await router.isReady()

  const currentPath = router.currentRoute.value.path
  const publicPaths = new Set(['/intro', '/market', '/login', '/register'])
  const initBypassPaths = new Set(['/intro', '/market'])

  try {
    const { initialized } = await api.get('/init/status')
    if (!initialized && !initBypassPaths.has(currentPath)) {
      router.replace('/init')
      return
    }

    const token = getStoredToken()
    if (!token && !publicPaths.has(currentPath)) {
      router.replace('/login')
      return
    }
    if (token) {
      try {
        await syncCurrentUser()
      } catch {
        clearAuthSession()
        if (!publicPaths.has(currentPath)) {
          router.replace('/login')
        }
        return
      }
    }
  } catch {
    if (!initBypassPaths.has(currentPath)) {
      router.replace('/login')
    }
  }
})
</script>
