import { EXTERNAL_LOGIN_ENDPOINT } from './backend-endpoints.js'

const EXTERNAL_LOGIN_URL = EXTERNAL_LOGIN_ENDPOINT

const PASSWORD_PUBLIC_KEY = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqVNFLqJPwFF8Q5K/oQI/
/BmcH762vgcITJ1kZtiCWiNL3I+uxydi1RfTvJo4uAidscOhYONWMgpK4hW+3yQD
rXe3z4RyIONfQp3GMasXx98J7LHV4noJ3Rz1njBPKwjq4ezBRkziJmDL57Xz3iZd
wHzXVDOB8aWsJSl13qbBmRvFDn1vNs5KSXD2uzrSg5Zo6sopgWCLwjl5fs/S21M4
whZjg1E6oqp9SSrZp+irj4g0gj3Cej7u3x0aStRRLcRv99g6SNdzwtvgPy9Zlu+H
T2D4L2msGOAp9zqHn5ofw7rX5s/hmrPO7UDoBhx/LxNuqCh6Ye88Mix5SYPkSrgh
lQIDAQAB
-----END PUBLIC KEY-----`

function pemToBytes(pem) {
  const binary = atob(pem.replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s/g, ''))
  return Uint8Array.from(binary, (character) => character.charCodeAt(0))
}

function bytesToBase64(bytes) {
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

let publicKeyPromise

async function encryptPassword(password) {
  publicKeyPromise ||= crypto.subtle.importKey(
    'spki',
    pemToBytes(PASSWORD_PUBLIC_KEY).buffer,
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt'],
  )
  const encrypted = await crypto.subtle.encrypt(
    { name: 'RSA-OAEP' },
    await publicKeyPromise,
    new TextEncoder().encode(password),
  )
  return bytesToBase64(new Uint8Array(encrypted))
}

export async function loginWithExternalAccount({ account, password }) {
  const response = await fetch(EXTERNAL_LOGIN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ account, password: await encryptPassword(password) }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.error || '账号或密码错误')
  return {
    token: `external:${data.username || account}`,
    username: data.username || account,
    display_name: data.nickname || data.username || account,
    role: data.role || 'user',
    role_ids: data.roles || [],
    permissions: [],
  }
}
