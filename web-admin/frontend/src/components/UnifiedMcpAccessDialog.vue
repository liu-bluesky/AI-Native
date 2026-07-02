<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    :width="width"
    destroy-on-close
    @update:model-value="handleVisibleChange"
    @close="handleClose"
  >
    <div class="unified-mcp-access">
      <el-tabs v-model="activeTab" class="unified-mcp-access__tabs">
        <el-tab-pane label="SSE" name="sse">
          <div class="unified-mcp-access__tab-tip">推荐直接接入 SSE 地址，复制后即可使用。</div>
          <div class="unified-mcp-access__code-wrap">
            <pre class="unified-mcp-access__code"><code>{{ sseConfig }}</code></pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="HTTP" name="http">
          <div class="unified-mcp-access__tab-tip">适合原生支持 Streamable HTTP 的 MCP 客户端。</div>
          <div class="unified-mcp-access__code-wrap">
            <pre class="unified-mcp-access__code"><code>{{ httpConfig }}</code></pre>
          </div>
        </el-tab-pane>
        <el-tab-pane
          v-for="item in cliPromptCategories"
          :key="item.key"
          :label="item.label"
          :name="getCliTabName(item.key)"
        >
          <div class="unified-mcp-access__prompt-card">
            {{ resolvePromptCardText(item) }}
          </div>
          <details class="unified-mcp-access__details" open>
            <summary>展开引导提示词预览</summary>
            <div class="unified-mcp-access__code-wrap unified-mcp-access__code-wrap--prompt">
              <pre class="unified-mcp-access__code"><code>{{ item.prompt }}</code></pre>
            </div>
          </details>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <el-button type="primary" @click="copyCurrentContent">{{ copyButtonText }}</el-button>
      <el-button @click="handleVisibleChange(false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'
import { buildRuntimeUrl, setConfiguredRuntimeOrigin } from '@/utils/runtime-url.js'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: '统一 MCP 接入',
  },
  width: {
    type: String,
    default: '720px',
  },
  projectId: {
    type: String,
    default: '',
  },
  projectLabel: {
    type: String,
    default: '',
  },
  chatSessionId: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:modelValue', 'close'])

const activeTab = ref('sse')
const QUERY_CENTER_SERVER_NAME = 'query-center'
const CLI_TAB_PREFIX = 'cli:'
const runtimeAccess = ref({
  sseUrl: '',
  httpUrl: '',
  cliPrompt: '',
  cliPrompts: [],
})

const normalizedProjectId = computed(() => String(props.projectId || '').trim())
const normalizedProjectLabel = computed(() => String(props.projectLabel || '').trim())
const normalizedChatSessionId = computed(() => String(props.chatSessionId || '').trim())
const hasProject = computed(() => Boolean(normalizedProjectId.value))
const hasChatSession = computed(() => Boolean(normalizedChatSessionId.value))
const chatSessionIdFormatHint = computed(() =>
  hasProject.value
    ? `cli.${normalizedProjectId.value}.<YYYYMMDDTHHMMSS>.<host6>.<pid>.<rand6>`
    : 'cli.<project_id>.<YYYYMMDDTHHMMSS>.<host6>.<pid>.<rand6>',
)
const sessionIdFormatHint = computed(() =>
  hasProject.value
    ? `ws_${normalizedProjectId.value}_<employee_id|team>_<YYYYMMDDTHHMMSS>_<rand4>`
    : 'ws_<project_id>_<employee_id|team>_<YYYYMMDDTHHMMSS>_<rand4>',
)
const fallbackCliProfiles = [
  {
    key: 'codex',
    label: 'Codex CLI',
    resource: 'query://client-profile/codex',
    clientDesc: 'Codex CLI',
  },
  {
    key: 'hermes',
    label: 'Hermes',
    resource: 'query://client-profile/hermes',
    clientDesc: 'Hermes',
  },
  {
    key: 'claude-code',
    label: 'Claude Code',
    resource: 'query://client-profile/claude-code',
    clientDesc: 'Claude Code',
  },
  {
    key: 'desktop-agent',
    label: '桌面智能体',
    resource: 'query://client-profile/desktop-agent',
    clientDesc: '桌面智能体',
  },
]
const runtimeQueryString = computed(() => {
  const params = new URLSearchParams({ key: 'YOUR_API_KEY' })
  if (normalizedProjectId.value) params.set('project_id', normalizedProjectId.value)
  if (normalizedChatSessionId.value) params.set('chat_session_id', normalizedChatSessionId.value)
  return params.toString()
})
const fallbackSseRuntimeUrl = computed(() => buildRuntimeUrl(`/mcp/query/sse?${runtimeQueryString.value}`))
const fallbackHttpRuntimeUrl = computed(() => buildRuntimeUrl(`/mcp/query/mcp?${runtimeQueryString.value}`))
const sseRuntimeUrl = computed(() => runtimeAccess.value.sseUrl || fallbackSseRuntimeUrl.value)
const httpRuntimeUrl = computed(() => runtimeAccess.value.httpUrl || fallbackHttpRuntimeUrl.value)
const queryCenterDescription = computed(() => {
  return `统一查询 MCP 入口（server 名：${QUERY_CENTER_SERVER_NAME}），提供项目/员工/规则查询、任务分析、上下文聚合、执行规划、任务树推进、本地运行轨迹和交付报告能力。注意：description 只是接入说明；真正绑定靠 URL 参数提供的默认上下文，以及 MCP 方法 bind_project_context 写入当前会话绑定。`
})

function getFallbackCliProfile(profileKey = 'codex') {
  return fallbackCliProfiles.find((item) => item.key === profileKey) || fallbackCliProfiles[0]
}

function resolvePromptCardText(item) {
  if (item?.key === 'desktop-agent') {
    return '桌面智能体运行时入口预览。AIENTRY.md 是项目入口文档，Client Profile 是接入画像；这里展示的是可直接读取的最终结果。'
  }
  return '适合放进当前客户端入口文件。每个客户端只展示自己的接入画像；详细规则通过 `query://...` 资源按需读取。'
}

function buildFallbackCliPrompt(profileKey = 'codex') {
  const profile = getFallbackCliProfile(profileKey)
  const sections = [
    '你已接入统一查询 MCP。',
    '',
    '开始执行前必须读取这些资源：',
    '- `query://usage-guide`',
    `- \`${profile.resource}\`（${profile.clientDesc}）`,
    '',
    '强制接入步骤：',
    `1. 先读取 \`query://usage-guide\`；当前客户端是 ${profile.label}，再读取对应画像 \`${profile.resource}\`。`,
    '1.1 `list_mcp_resources` 只用于发现资源目录，不等于读取资源；同一轮最多调用一次。资源 URI 已知时，必须直接用 `read_mcp_resource` 读取 `query://usage-guide` 和对应 client profile，禁止反复调用 `list_mcp_resources`。',
    '1.2 对“有几个员工 / 有哪些员工 / 有哪些工具 / 有哪些规则”这类简单查询，且 `project_id` 已明确时，直接调用对应业务工具（如 `list_project_members(project_id=...)`、`list_project_proxy_tools(...)`），不要为了满足 bootstrap 机械列资源目录。',
    '2. 初始化不是只检查技能；先以当前 CLI 工作区为准，显式初始化本地 `.ai-employee/`，至少确保 `.ai-employee/skills/`、`.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/session-history/` 与 `.ai-employee/requirements/<project_id>/` 可用；canonical session 状态只使用 `active-sessions/<chat_session_id>.json` 与 `session-history/<project_id>__<chat_session_id>.json`。',
    '3. 再检查 `.ai-employee/skills/query-mcp-workflow/` 是否已存在；缺失时先从系统技能库同步或创建到当前工作区，已存在则直接复用。',
    '4. 通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；优先读取本地副本中的 `SKILL.md`、`manifest.json`。只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。',
    '5. 若系统曾把 `.ai-employee` 或 `query-mcp-workflow` 隐式落到其他子目录，只能视为历史状态，不能替代当前 CLI 工作区初始化；当前入口仍要补齐。',
    '6. 实现型需求优先调用 `start_project_workflow(...)` 作为固定入口；若暂不适合走固定入口，至少补齐 `search_ids -> get_manual_content -> analyze_task -> resolve_relevant_context -> generate_execution_plan`。',
    '7. 仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或需要跨项目检索时，再调用 `search_ids(keyword="<用户原始问题>")`；已明确当前项目且在项目内执行时可直接读取上下文或进入本地实现。',
    '8. 不要依赖 description、项目说明或“当前项目”文字做绑定；需要项目绑定或续接任务树时，显式调用 `bind_project_context(...)`。',
    '9. 当前任务先在项目本地推进：先完成分析、改动、验证和本地记录，再通过 MCP 回写任务树和交付结果；详细执行轨迹留在本地 runtime。',
    '10. 每个需求都要维护 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`；对象只记录需求内容和必要定位字段，不记录任务树、任务节点、执行历史或项目智能体上下文。',
    '11. 若只是查询、解释或客服型问题，且目标、对象、范围和预期结果足够清晰，可直接回答；凡涉及开发、实现、修改、写入或其他会改变项目状态的需求，先判断本轮用户是否已经给出明确执行指令；“修复”“开始”“继续”“按这个做”“修改”“执行”“开始改”等表达视为对当前清晰范围的确认，可直接进入执行，不要再次请求一般计划确认。',
    '12. 若目标、对象、范围或预期结果不清晰，仍需先输出需求理解、计划摘要和可能误解点并请求确认；任何删除、移除、清空、覆盖、部署、发布、外部系统写入、凭据暴露或不可逆操作必须单独说明对象、影响范围和可恢复性，并取得用户明确确认。',
    '13. 一旦用户已确认计划或已明确要求执行，后续按已生成计划连续推进到完成；阶段之间只更新任务树、验证结果和必要进度，本地执行轨迹由本地 runtime 保存，不再停下来请求“是否继续”。只有遇到破坏性/不可逆操作、权限或环境阻塞、需求范围变化、验证无法推进，或必须由用户做业务决策时，才暂停并明确说明阻塞点。',
    '14. 长任务先调用 `record_requirement` 记录服务端需求本体；后续复用同一个 `chat_session_id/session_id`，详细执行轨迹由本地 runtime 保存。',
    '15. 如宿主支持任务树，执行前先读取 `get_current_task_tree`；开始节点用 `update_task_node_status`，完成节点时必须用 `complete_task_node_with_verification` 补验证结果后再结束。',
    '16. 禁止以兜底、兼容、静默降级或重复写入多份状态来掩盖问题；遇到异常、缺失、路径不一致、状态不一致或接口不匹配时，优先定位并修正根因，收敛到唯一规范入口和 canonical 状态。',
    '',
    '当前接入上下文：',
  ]

  if (hasProject.value) {
    sections.push(
      `- 默认项目: \`${normalizedProjectId.value}\``,
      `- 涉及当前项目时，若项目和对象已明确，可直接 \`get_manual_content(project_id="${normalizedProjectId.value}")\` 或进入 \`start_project_workflow(...)\`；仅在缺少 ID 或需要跨项目定位时，再调用 \`search_ids(keyword="<用户原始问题>", project_id="${normalizedProjectId.value}")\`。`,
      `- 若要创建或续接当前项目任务树，优先显式调用 \`bind_project_context(project_id="${normalizedProjectId.value}", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")\`。`,
    )
  } else {
    sections.push('- 当前未预设默认项目；若任务明显属于某个项目，先定位项目 ID，再调用 `bind_project_context(...)`；需要跨项目或缺少 ID 时，再调用 `search_ids`。')
  }

    sections.push(
      hasChatSession.value
      ? `- 当前页面已有 \`chat_session_id=${normalizedChatSessionId.value}\`；仅在明确要续接当前任务树时复用，否则新开的并行 CLI 应重新生成自己的 \`chat_session_id\`。`
      : `- 若当前是新开的 CLI 会话且 URL 未附带 \`chat_session_id\`，先按 \`${chatSessionIdFormatHint.value}\` 规则生成新的 \`chat_session_id\`。`,
    '- `chat_session_id` 生成后要立即持久化；优先写项目目录 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`，并同步维护 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。',
    '- requirement 本地对象与 query-mcp canonical 状态要同时维护；不要只写 session 文件而缺失 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。',
    '- 如果自动 bootstrap 把状态写到了别的服务子目录，不能把它当成当前仓库根目录已初始化；入口提示词必须以当前 CLI 工作区为准重新核对。',
    `- 若当前还没有 \`session_id\`，调用 \`record_requirement\` 后也要立刻持久化；本地运行轨迹 \`session_id\` 建议按 \`${sessionIdFormatHint.value}\` 规则生成并全程复用。`,
    '- 中断恢复先读取本地 runtime 状态，再调用 `bind_project_context(...)` 并读取当前任务树；若项目工作区不可解析，再退回当前 CLI 自己的本地存储。',
    '- 不要在项目工作区写入分叉会话状态文件。',
    '',
    '回答要求：',
    '- 先基于 MCP 查询结果和本地技能内容回答，不要把猜测写成事实。',
    '- 若信息来自 MCP，尽量保留对应的项目 / 员工 / 规则 ID，方便追溯。',
    '- 若引用技能内容，优先注明技能 ID、包路径或本地目录位置，方便追溯。',
  )

  return sections.join('\n')
}

const cliPrompt = computed(() => {
  const runtimePrompt = String(runtimeAccess.value.cliPrompt || '').trim()
  if (runtimePrompt) return runtimePrompt
  return buildFallbackCliPrompt('codex')
})
const cliPromptCategories = computed(() => {
  const list = Array.isArray(runtimeAccess.value.cliPrompts) ? runtimeAccess.value.cliPrompts : []
  const normalized = list
    .map((item) => ({
      key: String(item?.key || '').trim(),
      label: String(item?.label || item?.key || '').trim(),
      prompt: String(item?.prompt || '').trim(),
    }))
    .filter((item) => item.key && item.prompt)
  if (normalized.length) return normalized
  return fallbackCliProfiles.map((item) => ({
    key: item.key,
    label: item.label,
    prompt: buildFallbackCliPrompt(item.key),
  }))
})
const isCliPromptTab = computed(() => activeTab.value.startsWith(CLI_TAB_PREFIX))
const activeCliProfileKey = computed(() => {
  if (!isCliPromptTab.value) return ''
  return activeTab.value.slice(CLI_TAB_PREFIX.length)
})
const activeCliPromptItem = computed(() => {
  const categories = cliPromptCategories.value
  return (
    categories.find((item) => item.key === activeCliProfileKey.value) || categories[0] || null
  )
})
const activeCliPromptText = computed(() => activeCliPromptItem.value?.prompt || cliPrompt.value)
const sseConfig = computed(() =>
  JSON.stringify(
    {
      mcpServers: {
        [QUERY_CENTER_SERVER_NAME]: {
          type: 'sse',
          url: sseRuntimeUrl.value,
          description: queryCenterDescription.value,
        },
      },
    },
    null,
    2,
  ),
)
const httpConfig = computed(() =>
  JSON.stringify(
    {
      mcpServers: {
        [QUERY_CENTER_SERVER_NAME]: {
          type: 'streamable-http',
          url: httpRuntimeUrl.value,
          description: queryCenterDescription.value,
        },
      },
    },
    null,
    2,
  ),
)
const copyButtonText = computed(() => {
  if (!isCliPromptTab.value) return '复制当前配置'
  const label = activeCliPromptItem.value?.label || ''
  return label ? `复制 ${label} 提示词` : '复制引导提示词'
})

watch(
  () => props.modelValue,
  (value) => {
    if (!value) return
    activeTab.value = 'sse'
    void fetchQueryMcpRuntime()
  },
)

watch([normalizedProjectId, normalizedChatSessionId], () => {
  if (!props.modelValue) return
  void fetchQueryMcpRuntime()
})

function handleVisibleChange(value) {
  emit('update:modelValue', value)
}

function handleClose() {
  emit('close')
}

async function fetchQueryMcpRuntime() {
  try {
    const data = await api.get('/projects/query-mcp/runtime', {
      params: {
        project_id: normalizedProjectId.value || undefined,
        chat_session_id: normalizedChatSessionId.value || undefined,
      },
    })
    const runtime = data?.runtime && typeof data.runtime === 'object' ? data.runtime : {}
    setConfiguredRuntimeOrigin(runtime.origin || '')
    runtimeAccess.value = {
      sseUrl: String(runtime.sse_url || '').trim(),
      httpUrl: String(runtime.http_url || '').trim(),
      cliPrompt: String(runtime.cli_prompt || '').trim(),
      cliPrompts: Array.isArray(runtime.cli_prompts) ? runtime.cli_prompts : [],
    }
    syncActiveCliTab()
  } catch {
    runtimeAccess.value = {
      sseUrl: '',
      httpUrl: '',
      cliPrompt: '',
      cliPrompts: [],
    }
    syncActiveCliTab()
  }
}

function getCliTabName(profileKey) {
  return `${CLI_TAB_PREFIX}${profileKey}`
}

function syncActiveCliTab() {
  if (!isCliPromptTab.value) return
  const categories = cliPromptCategories.value
  if (!categories.length) {
    activeTab.value = 'sse'
    return
  }
  if (!categories.some((item) => item.key === activeCliProfileKey.value)) {
    activeTab.value = getCliTabName(categories[0].key)
  }
}

async function copyCurrentContent() {
  const content =
    activeTab.value === 'http'
      ? httpConfig.value
      : isCliPromptTab.value
        ? activeCliPromptText.value
        : sseConfig.value
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success(isCliPromptTab.value ? '引导提示词已复制' : '配置已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.unified-mcp-access {
  display: grid;
  gap: 12px;
}

.unified-mcp-access__tabs {
  margin-top: -8px;
}

.unified-mcp-access__code-wrap {
  max-height: 360px;
  overflow: auto;
  padding: 14px;
  border-radius: 14px;
  background: #0f172a;
}

.unified-mcp-access__code-wrap--prompt {
  margin-top: 12px;
}

.unified-mcp-access__tab-tip,
.unified-mcp-access__prompt-card {
  margin-bottom: 10px;
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #f8fafc;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.unified-mcp-access__details {
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: #fff;
  overflow: hidden;
}

.unified-mcp-access__details summary {
  cursor: pointer;
  padding: 12px 14px;
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  list-style: none;
}

.unified-mcp-access__details summary::-webkit-details-marker {
  display: none;
}

.unified-mcp-access__code {
  margin: 0;
  color: #e2e8f0;
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 760px) {
  .unified-mcp-access__code-wrap {
    max-height: 320px;
  }
}
</style>
