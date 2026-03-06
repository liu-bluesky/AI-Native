import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import os from 'node:os'

function resolveLanIp() {
  const interfaces = os.networkInterfaces()
  for (const items of Object.values(interfaces)) {
    for (const item of items || []) {
      if (!item || item.family !== 'IPv4' || item.internal) continue
      if (item.address.startsWith('192.168.') || item.address.startsWith('10.')) return item.address
      if (item.address.startsWith('172.')) {
        const second = Number(item.address.split('.')[1] || '0')
        if (second >= 16 && second <= 31) return item.address
      }
    }
  }
  return '127.0.0.1'
}

const proxyTarget = process.env.VITE_API_PROXY_TARGET || `http://${resolveLanIp()}:8000`

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
