<template>
  <router-view />
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from './utils/api.js'
import { clearPermissionArray, setPermissionArray } from './utils/permissions.js'

const router = useRouter()

onMounted(async () => {
  const currentPath = router.currentRoute.value.path
  const publicPaths = new Set(['/intro', '/login', '/register'])
  const initBypassPaths = new Set(['/intro'])

  try {
    const { initialized } = await api.get('/init/status')
    if (!initialized && !initBypassPaths.has(currentPath)) {
      router.replace('/init')
      return
    }

    const token = localStorage.getItem('token')
    if (!token && !publicPaths.has(currentPath)) {
      router.replace('/login')
      return
    }
    if (token) {
      try {
        const data = await api.get('/auth/me')
        localStorage.setItem('username', data?.username || '')
        localStorage.setItem('role', data?.role || 'user')
        setPermissionArray(data?.permissions || [])
      } catch {
        localStorage.removeItem('token')
        localStorage.removeItem('username')
        localStorage.removeItem('role')
        clearPermissionArray()
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
