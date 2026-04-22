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
        <el-tab-pane label="CLI" name="cli">
          <div class="unified-mcp-access__prompt-card">
            适合放进 CLI 入口文件。这里默认提供短引导提示词，详细规则通过 `query://...` 资源按需读取。
          </div>
          <details class="unified-mcp-access__details">
            <summary>展开引导提示词预览</summary>
            <div class="unified-mcp-access__code-wrap unified-mcp-access__code-wrap--prompt">
              <pre class="unified-mcp-access__code"><code>{{ cliPrompt }}</code></pre>
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
const runtimeAccess = ref({
  sseUrl: '',
  httpUrl: '',
  cliPrompt: '',
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
  return `统一查询 MCP 入口（server 名：${QUERY_CENTER_SERVER_NAME}），提供项目/员工/规则查询、任务分析、上下文聚合、执行规划、任务树推进、工作轨迹和交付报告能力。注意：description 只是接入说明；真正绑定靠 URL 参数提供的默认上下文，以及 MCP 方法 bind_project_context 写入当前会话绑定。`
})

function buildFallbackCliPrompt() {
  const sections = [
    '你已接入统一查询 MCP。',
    '',
    '开始执行前必须读取这些资源：',
    '- `query://usage-guide`',
    '- `query://client-profile/codex` 或 `query://client-profile/claude-code`',
    '',
    '强制接入步骤：',
    '1. 先读取 `query://usage-guide`；当前是 Codex / Claude 这类代码 CLI 时，再读取对应的 client profile。',
    '2. 初始化不是只检查技能；先以当前 CLI 工作区为准，显式初始化本地 `.ai-employee/`，至少确保 `.ai-employee/skills/`、`.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/active/`、`.ai-employee/query-mcp/session-history/` 与 `.ai-employee/requirements/<project_id>/` 可用。',
    '3. 再检查 `.ai-employee/skills/query-mcp-workflow/` 是否已存在；缺失时先从系统技能库同步或创建到当前工作区，已存在则直接复用。',
    '4. 通用场景下，统一查询 MCP 工作流技能应位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；优先读取本地副本中的 `SKILL.md`、`manifest.json`。只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。',
    '5. 若系统曾把 `.ai-employee` 或 `query-mcp-workflow` 隐式落到其他子目录，只能视为历史状态，不能替代当前 CLI 工作区初始化；当前入口仍要补齐。',
    '6. 实现型需求优先调用 `start_project_workflow(...)` 作为固定入口；若暂不适合走固定入口，至少补齐 `search_ids -> get_manual_content -> analyze_task -> resolve_relevant_context -> generate_execution_plan`。',
    '7. 仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或需要跨项目检索时，再调用 `search_ids(keyword="<用户原始问题>")`；已明确当前项目且在项目内执行时可直接读取上下文或进入本地实现。',
    '8. 不要依赖 description、项目说明或“当前项目”文字做绑定；需要项目绑定或续接任务树时，显式调用 `bind_project_context(...)`。',
    '9. 当前任务先在项目本地推进：先完成分析、改动、验证和本地记录，再通过 MCP 回写任务树、工作事实和交付结果。',
    '10. 每个需求都要维护 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`；对象至少保留 `workflow_skill`、`record_path`、`storage_scope`、`task_tree`、`current_task_node`、`task_branches`、`history`。',
    '11. 长任务先调用 `start_work_session` 获取 `session_id`，后续复用同一个 `chat_session_id/session_id`，并用 `save_work_facts`、`append_session_event` 维护轨迹。',
    '12. 如宿主支持任务树，执行前先读取 `get_current_task_tree`；开始节点用 `update_task_node_status`，完成节点时必须用 `complete_task_node_with_verification` 补验证结果后再结束。',
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
    '- `chat_session_id` 生成后要立即持久化；优先写项目目录 `.ai-employee/query-mcp/active-sessions/<chat_session_id>.json`，并同步维护 `.ai-employee/query-mcp/active/<project_id>.json` 与 `.ai-employee/query-mcp/session-history/<project_id>__<chat_session_id>.json`。',
    '- requirement 本地对象与 query-mcp canonical 状态要同时维护；不要只写 session 文件而缺失 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。',
    '- 如果自动 bootstrap 把状态写到了别的服务子目录，不能把它当成当前仓库根目录已初始化；入口提示词必须以当前 CLI 工作区为准重新核对。',
    `- 若当前还没有 \`session_id\`，调用 \`start_work_session\` 后也要立刻持久化；工作轨迹 \`session_id\` 建议按 \`${sessionIdFormatHint.value}\` 规则生成并全程复用。`,
    '- 中断恢复顺序固定为 `bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)`；若项目工作区不可解析，再退回当前 CLI 自己的本地存储。',
    '- 不要新写 `current-session.json`、`chat_session_id.txt`、`session_id.txt`、`session.env`、`current-query-session.json`、`current-work-session.json` 这类 legacy 文件。',
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
  return buildFallbackCliPrompt()
})
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
const copyButtonText = computed(() => (activeTab.value === 'cli' ? '复制引导提示词' : '复制当前配置'))

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
    }
  } catch {
    runtimeAccess.value = {
      sseUrl: '',
      httpUrl: '',
      cliPrompt: '',
    }
  }
}

async function copyCurrentContent() {
  const content =
    activeTab.value === 'http'
      ? httpConfig.value
      : activeTab.value === 'cli'
        ? cliPrompt.value
        : sseConfig.value
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success(activeTab.value === 'cli' ? '引导提示词已复制' : '配置已复制')
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
