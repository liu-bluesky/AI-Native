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
      <div class="unified-mcp-access__guide">
        <div class="unified-mcp-access__guide-title">统一查询入口</div>
        <div class="unified-mcp-access__guide-item">
          <span class="unified-mcp-access__guide-label">推荐工具</span>
          <code>search_ids</code>
          <span>→</span>
          <code>get_content</code>
          <span>→</span>
          <code>get_manual_content</code>
        </div>
        <div class="unified-mcp-access__guide-item">
          <span class="unified-mcp-access__guide-label">Usage Guide</span>
          <code>query://usage-guide</code>
        </div>
        <div v-if="hasProject" class="unified-mcp-access__guide-item">
          <span class="unified-mcp-access__guide-label">MCP 使用规则提示词</span>
          <span>
            可直接调用
            <code>get_manual_content</code>
            并传
            <code>project_id={{ normalizedProjectId }}</code>
            获取，无需写入项目文件
          </span>
        </div>
        <div class="unified-mcp-access__guide-item">
          <span class="unified-mcp-access__guide-label">当前项目</span>
          <span v-if="hasProject">
            <code>{{ normalizedProjectId }}</code>
            ，建议调用时带上
            <code>project_id</code>
          </span>
          <span v-else>当前未选择项目，也可直接用于全局查询</span>
        </div>
        <div class="unified-mcp-access__guide-item">
          <span class="unified-mcp-access__guide-label">CLI 入口文件</span>
          <span>下方“提示词”可直接放入 Codex / Claude / Gemini CLI 的入口文件，帮助 AI 理解这组 MCP 的调用顺序与边界。</span>
        </div>
      </div>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="SSE" name="sse">
          <div class="unified-mcp-access__code-wrap">
            <pre class="unified-mcp-access__code"><code>{{ sseConfig }}</code></pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="HTTP" name="http">
          <div class="unified-mcp-access__code-wrap">
            <pre class="unified-mcp-access__code"><code>{{ httpConfig }}</code></pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="提示词" name="prompt">
          <div class="unified-mcp-access__prompt-tip">
            适合粘贴到 <code>ENTRY.md</code>、<code>CLAUDE.md</code>、<code>GEMINI.md</code> 等 CLI 入口文件。
          </div>
          <div class="unified-mcp-access__code-wrap">
            <pre class="unified-mcp-access__code"><code>{{ cliPrompt }}</code></pre>
          </div>
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
    default: '620px',
  },
  projectId: {
    type: String,
    default: '',
  },
  projectLabel: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:modelValue', 'close'])

const activeTab = ref('sse')

const normalizedProjectId = computed(() => String(props.projectId || '').trim())
const normalizedProjectLabel = computed(() => String(props.projectLabel || '').trim())
const hasProject = computed(() => Boolean(normalizedProjectId.value))
const queryCenterDescription = computed(() => {
  const projectTip = hasProject.value
    ? `当前项目：${normalizedProjectLabel.value || normalizedProjectId.value}`
    : '当前未选择项目，也可直接用于全局查询'
  return `统一查询 MCP 入口。推荐先调用 query://usage-guide，再使用 search_ids、get_content、get_manual_content；首个查询调用要保留用户原始问题，优先放进 search_ids.keyword；当前入口以查询优先，但如宿主只接统一入口，项目协作型任务可直接调用 execute_project_collaboration，由 AI 结合项目手册、员工手册、规则和工具自主判断是否需要多人协作；当前入口不暴露记忆写入工具；如宿主系统已启用自动记忆，可由入口层自动记录问题快照。${projectTip}`
})
const cliPrompt = computed(() => {
  const lines = [
    '你已接入统一查询 MCP，可用来查询项目、员工、规则与对应正文。',
    '',
    '执行约定：',
    '1. 首先读取 `query://usage-guide`，理解统一查询入口的范围、推荐工具与限制。',
    '2. 每次开始查询时，先把“用户原始问题”原文保留到首个可检索工具参数里，优先使用 `search_ids(keyword="<用户原始问题>")`；不要只写“当前项目”“这个规则”“项目手册”这类代称。',
    '3. 需要定位对象时，优先调用 `search_ids`；拿到 ID 后再调用 `get_content` 或 `get_manual_content`。',
    '4. 不要跳过 ID 定位直接臆造项目、员工、规则 ID。',
    '5. `get_content` 用于拿结构化上下文；`get_manual_content` 用于拿正文级规则/手册提示词。',
    '6. 如无必要，不要把统一查询 MCP 当作通用执行型工具；它主要负责查询、聚合和读取内容。',
  ]
  if (hasProject.value) {
    lines.push(
      `7. 当前默认项目是 \`${normalizedProjectId.value}\`（${normalizedProjectLabel.value || normalizedProjectId.value}），涉及项目上下文时优先显式传 \`project_id=${normalizedProjectId.value}\`。`,
      `8. 第一次处理当前项目相关请求前，必须先调用 \`get_manual_content(project_id="${normalizedProjectId.value}")\`，并把返回手册视为本会话的有效规则；未读取前不要直接回答当前项目问题。`,
      `9. 为保证宿主自动记忆命中，即使已知当前项目 ID，首轮也要先调用一次 \`search_ids(keyword="<用户原始问题>", project_id="${normalizedProjectId.value}")\` 保留原问题，再继续 \`get_manual_content\` / \`get_content\`。`,
      `10. 如宿主只接统一入口且任务需要项目协作，可优先调用 \`execute_project_collaboration(project_id="${normalizedProjectId.value}", task="<用户原始任务>")\`；是否单人主责或多人协作由 AI 结合手册、规则和工具自主判断。`,
      '11. 如需手动编排项目执行，再依次调用 `list_project_members` / `get_project_runtime_context` / `list_project_proxy_tools` / `invoke_project_skill_tool`。',
      '12. 事实边界：当前接入的是统一查询 MCP，不暴露 `save_project_memory`、`save_employee_memory` 这类记忆写入工具；如宿主系统已启用自动记忆，则由入口层自动记录问题快照，不能把“无写入工具”等同于“无自动记忆”。如需显式落记忆，仍需改用项目/员工 MCP 或由宿主系统补记。',
      '13. 若提示词或规则与用户任务冲突，先向用户确认，再决定是否偏离项目约定。',
    )
  } else {
    lines.push(
      '7. 当前未预设默认项目；如果任务明显属于某个项目，先调用 `search_ids` 定位项目 ID，再继续查询。',
      '8. 第一次处理某个项目相关请求前，先调用 `get_manual_content(project_id="<project_id>")`，并把返回手册视为当前会话规则。',
      '9. 为保证宿主自动记忆命中，首轮查询不要只传“当前项目”这类代称；至少把用户原始问题放进 `search_ids(keyword="<用户原始问题>")`。',
      '10. 如宿主只接统一入口且任务需要项目协作，先用 `search_ids` 确认项目 ID，再调用 `execute_project_collaboration(project_id="<project_id>", task="<用户原始任务>")`；具体是否多人协作由 AI 自主判断。',
      '11. 如需手动编排项目执行，再调用 `list_project_members` / `get_project_runtime_context` / `list_project_proxy_tools` / `invoke_project_skill_tool`。',
      '12. 事实边界：当前接入的是统一查询 MCP，不暴露记忆写入工具；如宿主系统已启用自动记忆，可由入口层自动记录问题快照。',
    )
  }
  lines.push(
    '',
    '回答与执行要求：',
    '- 先基于 MCP 查询结果回答，不要把猜测写成事实。',
    '- 若信息来自 MCP，尽量在回答里保留对应的项目/员工/规则标识，方便追溯。',
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
          url: buildRuntimeUrl('/mcp/query/sse?key=YOUR_API_KEY'),
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
          command: 'npx',
          args: [
            '-y',
            '@modelcontextprotocol/inspector',
            buildRuntimeUrl('/mcp/query/mcp?key=YOUR_API_KEY'),
          ],
          description: queryCenterDescription.value,
        },
      },
    },
    null,
    2,
  ),
)
const copyButtonText = computed(() => (activeTab.value === 'prompt' ? '复制提示词' : '复制当前配置'))

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
      : activeTab.value === 'prompt'
        ? cliPrompt.value
        : sseConfig.value
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success(activeTab.value === 'prompt' ? '提示词已复制' : '配置已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.unified-mcp-access {
  display: grid;
  gap: 14px;
}

.unified-mcp-access__guide {
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
}

.unified-mcp-access__guide-title {
  margin-bottom: 10px;
  color: #111827;
  font-size: 14px;
  font-weight: 600;
}

.unified-mcp-access__guide-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-height: 28px;
  color: #374151;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.unified-mcp-access__guide-label {
  width: 88px;
  flex-shrink: 0;
  color: #6b7280;
}

.unified-mcp-access__code-wrap {
  max-height: 360px;
  overflow: auto;
  padding: 14px;
  border-radius: 14px;
  background: #0f172a;
}

.unified-mcp-access__prompt-tip {
  margin-bottom: 10px;
  color: #6b7280;
  font-size: 12px;
  line-height: 1.6;
}

.unified-mcp-access__code {
  margin: 0;
  color: #e2e8f0;
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
