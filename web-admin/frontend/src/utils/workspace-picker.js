import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

function normalizePathLike(value = '') {
  return String(value || '').trim().replace(/\\/g, '/').replace(/\/+$/, '')
}

export function resolveWorkspaceRelativePath(reference = '', workspacePath = '') {
  const rawReference = String(reference || '').trim()
  if (!rawReference) return ''
  const normalizedWorkspacePath = normalizePathLike(workspacePath)
  if (!normalizedWorkspacePath) return rawReference
  if (/^(?:[A-Za-z]:[\\/]|\/|\\\\)/.test(rawReference)) return rawReference
  return `${normalizedWorkspacePath}/${rawReference}`.replace(/\/+/g, '/')
}

export function toWorkspaceRelativePath(targetPath = '', workspacePath = '') {
  const normalizedTarget = normalizePathLike(targetPath)
  const normalizedWorkspacePath = normalizePathLike(workspacePath)
  if (!normalizedTarget || !normalizedWorkspacePath) return String(targetPath || '').trim()
  if (normalizedTarget === normalizedWorkspacePath) return ''
  const prefix = `${normalizedWorkspacePath}/`
  if (!normalizedTarget.startsWith(prefix)) {
    return String(targetPath || '').trim()
  }
  return normalizedTarget.slice(prefix.length)
}

export async function pickWorkspaceDirectory(currentPath = '', options = {}) {
  const initialPath = String(currentPath || '').trim()
  const title = String(options?.title || '选择工作区目录').trim() || '选择工作区目录'
  const fallbackPlaceholder =
    String(options?.placeholder || '/Users/yourname/project').trim() || '/Users/yourname/project'

  try {
    const data = await api.post('/projects/workspace-directory/pick', {
      initial_path: initialPath,
      title,
    })
    if (data?.cancelled) {
      return null
    }
    const picked = String(data?.path || '').trim()
    if (picked) {
      return picked
    }
  } catch (err) {
    ElMessage.warning(err?.detail || err?.message || '系统目录选择器不可用，改为手动填写路径')
  }

  try {
    const { value } = await ElMessageBox.prompt(
      '当前环境无法弹出系统目录选择器，请手动输入工作区绝对路径。',
      title,
      {
        inputValue: initialPath,
        inputPlaceholder: fallbackPlaceholder,
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      },
    )
    return String(value || '').trim()
  } catch {
    return null
  }
}

export async function pickWorkspaceFile(currentPath = '', options = {}) {
  const rawCurrentPath = String(currentPath || '').trim()
  const basePath = String(options?.basePath || '').trim()
  const initialPath = resolveWorkspaceRelativePath(rawCurrentPath, basePath)
  const title = String(options?.title || '选择文件').trim() || '选择文件'
  const fallbackPlaceholder =
    String(options?.placeholder || '.ai/ENTRY.md').trim() || '.ai/ENTRY.md'

  try {
    const data = await api.post('/projects/workspace-file/pick', {
      initial_path: initialPath,
      title,
    })
    if (data?.cancelled) {
      return null
    }
    const picked = String(data?.path || '').trim()
    if (picked) {
      return picked
    }
  } catch (err) {
    ElMessage.warning(err?.detail || err?.message || '系统文件选择器不可用，改为手动填写路径')
  }

  try {
    const { value } = await ElMessageBox.prompt(
      '当前环境无法弹出系统文件选择器，请手动输入 AI 入口文件路径。支持相对项目工作区路径或绝对路径。',
      title,
      {
        inputValue: rawCurrentPath,
        inputPlaceholder: fallbackPlaceholder,
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      },
    )
    return String(value || '').trim()
  } catch {
    return null
  }
}
