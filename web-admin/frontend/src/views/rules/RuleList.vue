<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>规则管理</h3>
      <div class="toolbar-right">
        <el-select
          v-model="filterDomain"
          placeholder="按领域筛选"
          clearable
          size="small"
          class="filter-domain"
        >
          <el-option v-for="d in domains" :key="d" :label="d" :value="d" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="搜索关键词"
          size="small"
          class="filter-keyword"
          @keyup.enter="doSearch"
          clearable
        />
        <el-button size="small" type="primary" @click="doSearch"
          >搜索</el-button
        >
        <el-button
          size="small"
          type="primary"
          @click="$router.push('/rules/create')"
          >新建规则</el-button
        >
      </div>
    </div>

    <el-table :data="rules" stripe>
      <el-table-column prop="domain" label="领域" />
      <el-table-column prop="title" label="标题" show-overflow-tooltip />

      <el-table-column prop="severity" label="级别" width="100">
        <template #default="{ row }">
          <el-tag :type="sevColor(row.severity)" size="small">{{
            row.severity
          }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="confidence"
        label="置信度"
        width="90"
        align="center"
      />
      <el-table-column
        prop="use_count"
        label="使用次数"
        width="90"
        align="center"
      />
      <el-table-column prop="version" label="版本" width="80" />
      <el-table-column label="操作" width="320" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.mcp_enabled"
            text
            type="success"
            size="small"
            @click="showSingleMcpConfig(row)"
            >接入</el-button
          >
          <el-button
            v-if="row.mcp_enabled"
            text
            type="warning"
            size="small"
            @click="disableMcp(row)"
            >关闭 MCP</el-button
          >
          <el-button
            v-else
            text
            type="warning"
            size="small"
            @click="enableMcp(row)"
            >开启 MCP</el-button
          >
          <el-button
            text
            type="primary"
            size="small"
            @click="$router.push(`/rules/${row.id}`)"
            >详情</el-button
          >
          <el-button
            text
            type="primary"
            size="small"
            @click="$router.push(`/rules/${row.id}/edit`)"
            >编辑</el-button
          >
          <el-button
            text
            type="danger"
            size="small"
            @click="handleDelete(row.id)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!rules.length && !loading" description="暂无规则" />

    <el-dialog v-model="showMcpConfig" :title="mcpDialogTitle" width="600px">
      <div class="mcp-desc">
        <p>{{ mcpDialogDesc }}</p>
      </div>

      <el-tabs v-model="mcpTab" class="mcp-tabs">
        <el-tab-pane label="Stdio (本地脚本)" name="stdio" v-if="!isSingleMcp">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpStdioConfig }}</code></pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="SSE (网络接入)" name="sse" v-if="isSingleMcp">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpSseConfig }}</code></pre>
          </div>
          <div class="hint mt-2">
            提示：绝大多数现代 MCP 客户端（如 Cursor）原生支持 SSE URL。
          </div>
        </el-tab-pane>
        <el-tab-pane
          label="HTTP (Inspector 桥接)"
          name="http"
          v-if="isSingleMcp"
        >
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpHttpConfig }}</code></pre>
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button @click="copyActiveMcpConfig" type="primary"
          >复制当前配置</el-button
        >
        <el-button @click="showMcpConfig = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import api from "@/utils/api.js";

const loading = ref(false);
const rules = ref([]);
const domains = ref([]);
const filterDomain = ref("");
const keyword = ref("");
const showMcpConfig = ref(false);
const isAdmin = computed(() => localStorage.getItem("role") === "admin");

const mcpDialogTitle = ref("接入 MCP 服务");
const mcpDialogDesc = ref(
  "将以下配置添加到支持 MCP 的 AI 平台中，即可无缝接入。",
);
const mcpTab = ref("stdio");
const isSingleMcp = ref(false);
const currentRule = ref(null);

const mcpStdioConfig = computed(() => {
  return JSON.stringify(
    {
      mcpServers: {
        "ai-employee-rules": {
          command: "uv",
          args: [
            "run",
            "/Users/liulantian/self/ai设计规范/mcp-rules/server.py",
          ],
        },
      },
    },
    null,
    2,
  );
});

const mcpSseConfig = computed(() => {
  if (!currentRule.value) return "";
  const serviceName = currentRule.value.mcp_service || currentRule.value.id;
  return JSON.stringify(
    {
      mcpServers: {
        [serviceName]: {
          type: "sse",
          url: `http://localhost:8000/mcp/rules/${currentRule.value.id}/sse`,
        },
      },
    },
    null,
    2,
  );
});

const mcpHttpConfig = computed(() => {
  if (!currentRule.value) return "";
  const serviceName = currentRule.value.mcp_service || currentRule.value.id;
  return JSON.stringify(
    {
      mcpServers: {
        [serviceName]: {
          command: "npx",
          args: [
            "-y",
            "@modelcontextprotocol/inspector",
            `http://localhost:8000/mcp/rules/${currentRule.value.id}/mcp`,
          ],
        },
      },
    },
    null,
    2,
  );
});

async function enableMcp(rule) {
  try {
    loading.value = true;
    await api.put(`/rules/${rule.id}`, { mcp_enabled: true });
    ElMessage.success("已开启独立 MCP 服务");
    await fetchRules();

    // Auto show the config after enabling
    const updatedRule = rules.value.find((r) => r.id === rule.id) || rule;
    showSingleMcpConfig(updatedRule);
  } catch {
    ElMessage.error("开启 MCP 失败");
  } finally {
    loading.value = false;
  }
}

async function disableMcp(rule) {
  await ElMessageBox.confirm(`确定关闭规则「${rule.title}」的 MCP 服务？`, "确认");
  try {
    loading.value = true;
    await api.put(`/rules/${rule.id}`, { mcp_enabled: false });
    ElMessage.success("已关闭独立 MCP 服务");
    await fetchRules();
    if (currentRule.value?.id === rule.id) {
      showMcpConfig.value = false;
      currentRule.value = null;
    }
  } catch {
    ElMessage.error("关闭 MCP 失败");
  } finally {
    loading.value = false;
  }
}

function showGlobalMcpConfig() {
  isSingleMcp.value = false;
  mcpTab.value = "stdio";
  mcpDialogTitle.value = "全局规则库接入";
  mcpDialogDesc.value = "通过 Stdio 挂载本地全量规则管理服务：";
  showMcpConfig.value = true;
}

function showSingleMcpConfig(rule) {
  isSingleMcp.value = true;
  mcpTab.value = "sse";
  currentRule.value = rule;
  mcpDialogTitle.value = `独立规则接入: ${rule.title}`;
  mcpDialogDesc.value = "此规则已开启独立网络访问，无需本地环境即可挂载：";
  showMcpConfig.value = true;
}

async function copyActiveMcpConfig() {
  let content = "";
  if (!isSingleMcp.value) {
    content = mcpStdioConfig.value;
  } else if (mcpTab.value === "sse") {
    content = mcpSseConfig.value;
  } else {
    content = mcpHttpConfig.value;
  }

  try {
    await navigator.clipboard.writeText(content);
    ElMessage.success("配置已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败");
  }
}

function sevColor(s) {
  return (
    { required: "danger", recommended: "warning", optional: "info" }[s] ||
    "info"
  );
}

async function fetchDomains() {
  try {
    const data = await api.get("/rules/domains");
    domains.value = data.domains || [];
  } catch {
    /* ignore */
  }
}

async function fetchRules() {
  loading.value = true;
  try {
    const data = await api.get("/rules");
    rules.value = data.rules || [];
  } catch {
    ElMessage.error("加载规则失败");
  } finally {
    loading.value = false;
  }
}

async function doSearch() {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    if (keyword.value) params.set("keyword", keyword.value);
    if (filterDomain.value) params.set("domain", filterDomain.value);
    const data = await api.get(`/rules/search?${params}`);
    rules.value = data.rules || [];
  } catch {
    ElMessage.error("搜索失败");
  } finally {
    loading.value = false;
  }
}

async function handleDelete(ruleId) {
  await ElMessageBox.confirm("确定删除该规则？", "确认");
  try {
    await api.delete(`/rules/${ruleId}`);
    ElMessage.success("已删除");
    fetchRules();
  } catch {
    ElMessage.error("删除失败");
  }
}

onMounted(() => {
  fetchRules();
  fetchDomains();
});
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 {
  margin: 0;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-domain {
  width: 150px;
}

.filter-keyword {
  width: 180px;
}

.mcp-desc {
  margin-bottom: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.mcp-code-wrap {
  background: #1e1e1e;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}

.mcp-code {
  margin: 0;
  color: #d4d4d4;
  font-family: "Courier New", Courier, monospace;
  font-size: 13px;
  line-height: 1.4;
}
</style>
