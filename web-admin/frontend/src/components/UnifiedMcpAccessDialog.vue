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
            适合放进 CLI 入口文件。点击下方可展开预览，复制按钮会复制完整提示词。
          </div>
          <details class="unified-mcp-access__details">
            <summary>展开完整提示词预览</summary>
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
import { buildRuntimeUrl } from '@/utils/runtime-url.js'

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

const normalizedProjectId = computed(() => String(props.projectId || '').trim())
const normalizedProjectLabel = computed(() => String(props.projectLabel || '').trim())
const normalizedChatSessionId = computed(() => String(props.chatSessionId || '').trim())
const hasProject = computed(() => Boolean(normalizedProjectId.value))
const hasChatSession = computed(() => Boolean(normalizedChatSessionId.value))
const sessionIdFormatHint = computed(() =>
  hasProject.value
    ? `ws_${normalizedProjectId.value}_<employee_id|team>_<YYYYMMDDTHHMMSS>_<rand4>`
    : 'ws_<project_id>_<employee_id|team>_<YYYYMMDDTHHMMSS>_<rand4>',
)
const runtimeQueryString = computed(() => {
  const params = new URLSearchParams({ key: 'YOUR_API_KEY' })
  if (normalizedProjectId.value) {
    params.set('project_id', normalizedProjectId.value)
  }
  if (normalizedChatSessionId.value) {
    params.set('chat_session_id', normalizedChatSessionId.value)
  }
  return params.toString()
})
const sseRuntimeUrl = computed(() => buildRuntimeUrl(`/mcp/query/sse?${runtimeQueryString.value}`))
const httpRuntimeUrl = computed(() => buildRuntimeUrl(`/mcp/query/mcp?${runtimeQueryString.value}`))
const queryCenterDescription = computed(() => {
  return '统一查询 MCP 入口，提供项目/员工/规则查询、任务分析、上下文聚合、执行规划、任务树推进、工作轨迹和交付报告能力。注意：description 只是接入说明；真正绑定靠 URL 参数提供的默认上下文，以及 MCP 方法 bind_project_context 写入当前会话绑定。'
})
const cliPrompt = computed(() => {
  const lines = [
    '你已接入统一查询 MCP，可用于查询项目、员工、规则，并补充任务分析、执行规划、工作轨迹与交付能力。',
    '',
    '最少执行规则：',
    '1. 先读取 `query://usage-guide`；当前是 Codex / Claude 这类代码 CLI 时，再补读对应的 `query://client-profile/...`。',
    '2. `description`、项目说明、“当前项目”这类文字都不参与真正绑定；真正生效的是 URL 里的 `project_id` / `chat_session_id` 默认上下文，以及首轮 `bind_project_context(...)` 写入的 MCP 会话绑定。',
    '3. 若接入地址缺少 `project_id`，或需要续接任务树但缺少 `chat_session_id`，首轮立即调用 `bind_project_context(project_id="<项目ID>", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")`；不要只依赖 description 里的项目说明。',
    '4. 如果当前 CLI 没有活跃 MCP session，只要显式传了 `project_id + chat_session_id`，`bind_project_context(...)` 也会先建立 detached 任务树；后续所有工具继续显式复用同一个 `chat_session_id`。',
    '5. 首轮查询必须把用户原始问题原文放进 `search_ids(keyword="<用户原始问题>")`；不要只写“当前项目”“这个规则”“项目手册”这类代称。',
    '6. 需要规则或项目上下文时，先 `get_manual_content`，再按需调用 `get_content`；不要跳过 ID 定位直接臆造项目、员工、规则 ID。',
    '7. 实现型需求必须遵守任务树闭环：先 `analyze_task -> resolve_relevant_context -> generate_execution_plan`，再 `get_current_task_tree` 确认节点；执行中用 `update_task_node_status` 回写状态，完成时必须 `complete_task_node_with_verification` 填写验证结果。',
    '8. 只有所有计划节点完成且验证结果齐全后，当前需求才算结束；中途不得提前写“最终结论”。',
    '9. 查询型问题（谁 / 哪些 / 多少 / 从哪里）保持单检索节点，不要误拆成实现步骤；检索完成后应让任务树归档。',
    '10. 多轮任务先 `start_work_session`；后续复用同一个 `chat_session_id` / `session_id`，并用 `save_work_facts`、`append_session_event`、`resume_work_session`、`summarize_checkpoint` 维护轨迹。',
    '11. `save_project_memory` 只在补充稳定结论或关键决策时使用；不要在同一需求的每个中间步骤重复补记。',
    '12. 若用户在“已完成”后发现错误，必须重新起一轮修复计划并继续回写轨迹与验证，不得直接覆盖上一轮结论。',
    '13. 回答必须基于 MCP 查询结果，并尽量保留项目 / 员工 / 规则 ID 方便追溯。',
  ]
  if (hasProject.value) {
    lines.push(
      `14. 当前默认项目是 \`${normalizedProjectId.value}\`（${normalizedProjectLabel.value || normalizedProjectId.value}）；涉及当前项目时优先显式传 \`project_id=${normalizedProjectId.value}\`。`,
      `15. 第一次处理当前项目相关请求时，先执行 \`bind_project_context(project_id="${normalizedProjectId.value}", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")\` 或确认 URL 已带上稳定上下文，再执行 \`search_ids(keyword="<用户原始问题>", project_id="${normalizedProjectId.value}")\`。`,
      hasChatSession.value
        ? `16. 当前接入地址已自动附带 \`chat_session_id=${normalizedChatSessionId.value}\`；本轮任务树、项目记忆和工作轨迹都应继续复用这条会话线索，但首轮仍建议显式调用一次 \`bind_project_context(...)\` 固化绑定。`
        : '16. 若当前是新开的 CLI 会话且 URL 未附带 `chat_session_id`，先生成新的 `chat_session_id` 并调用 `bind_project_context(...)`；同一窗口内不要再次更换。',
      `17. 如暂不方便先调用 \`start_work_session\`，工作轨迹 \`session_id\` 至少按 \`${sessionIdFormatHint.value}\` 规则生成并全程复用。`,
    )
  } else {
    lines.push(
      '14. 当前未预设默认项目；如果任务明显属于某个项目，先用 `search_ids` 定位项目 ID，再调用 `bind_project_context(project_id="<project_id>", chat_session_id="<聊天会话ID>", root_goal="<用户原始问题>")`。',
      '15. 如果需要统一查询 MCP 自动续接任务树，但当前地址没有 `project_id` / `chat_session_id`，第一步就先调用 `bind_project_context(...)`，不要依赖 description 或宿主注释。',
      `16. 若当前是新开的 CLI 会话且 URL 未附带 \`chat_session_id\`，先生成新的 \`chat_session_id\`；工作轨迹 \`session_id\` 则按 \`${sessionIdFormatHint.value}\` 规则生成并全程复用。`,
      '17. 如宿主只接统一入口且任务需要项目协作，先用 `search_ids` 确认项目 ID，再调用 `execute_project_collaboration(project_id="<project_id>", task="<用户原始任务>")`；具体是否多人协作由 AI 自主判断。',
    )
  }
  lines.push(
    '',
    '回答要求：',
    '- 先基于 MCP 查询结果回答，不要把猜测写成事实。',
    '- 若信息来自 MCP，尽量保留对应的项目 / 员工 / 规则标识，方便追溯。',
    '- 若入口文件或宿主系统还有额外约束，优先遵守宿主入口文件约定。',
  )
  return lines.join('\n')
})
const sseConfig = computed(() =>
  JSON.stringify(
    {
      mcpServers: {
        'query-center': {
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
        'query-center': {
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
const copyButtonText = computed(() => (activeTab.value === 'cli' ? '复制提示词' : '复制当前配置'))

watch(
  () => props.modelValue,
  (value) => {
    if (!value) return
    activeTab.value = 'sse'
  },
)

function handleVisibleChange(value) {
  emit('update:modelValue', value)
}

function handleClose() {
  emit('close')
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
    ElMessage.success(activeTab.value === 'cli' ? '提示词已复制' : '配置已复制')
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
