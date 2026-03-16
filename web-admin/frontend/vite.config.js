import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
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

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {}
  const values = {}
  const content = fs.readFileSync(filePath, 'utf8')
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#') || !line.includes('=')) continue
    const [rawKey, ...rawValueParts] = line.split('=')
    const key = rawKey.trim()
    if (!key) continue
    let value = rawValueParts.join('=').trim()
    if (value.length >= 2 && value[0] === value[value.length - 1] && `"'`.includes(value[0])) {
      value = value.slice(1, -1)
    }
    values[key] = value
  }
  return values
}

function resolveApiRuntimeConfig() {
  const envPaths = [
    fileURLToPath(new URL('../api/.env', import.meta.url)),
    fileURLToPath(new URL('../api/.env.local', import.meta.url)),
  ]
  const fileEnv = envPaths.reduce((acc, filePath) => ({ ...acc, ...parseEnvFile(filePath) }), {})
  const rawHost = process.env.API_HOST || fileEnv.API_HOST || ''
  const apiPort = process.env.API_PORT || fileEnv.API_PORT || '8000'
  const normalizedHost =
    !rawHost || rawHost === '0.0.0.0' || rawHost === '::' ? '127.0.0.1' : rawHost
  return {
    host: normalizedHost,
    port: apiPort,
  }
}

const apiRuntimeConfig = resolveApiRuntimeConfig()
const proxyTarget =
  process.env.VITE_API_PROXY_TARGET || `http://${apiRuntimeConfig.host}:${apiRuntimeConfig.port}`
const proxyConfig = {
  target: proxyTarget,
  changeOrigin: true,
  ws: true,
}
console.log('first', proxyTarget)
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
      '/api': proxyConfig,
      '/mcp': proxyConfig,
    },
  },
})
