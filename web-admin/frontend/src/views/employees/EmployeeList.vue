<template>
  <div>
    <div class="toolbar">
      <h3>AI 员工列表</h3>
      <el-button type="primary" @click="$router.push('/employees/create')"
        >创建员工</el-button
      >
    </div>
    <el-alert
      class="usage-alert"
      type="info"
      :closable="false"
      show-icon
      title="功能说明：反馈=提交/反思/发布（需开启反馈升级）；记忆=查看与检索员工记忆（含自动写入的用户提问）；同步=查看同步事件。"
    />
    <el-table :data="employees" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="140" />
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="description" label="描述" />
      <el-table-column prop="tone" label="语调" width="100" />
      <el-table-column prop="verbosity" label="风格" width="100" />
      <el-table-column label="反馈升级" width="100">
        <template #default="{ row }">
          <el-tag
            :type="row.feedback_upgrade_enabled ? 'success' : 'info'"
            size="small"
          >
            {{ row.feedback_upgrade_enabled ? "已开" : "已关" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="技能数" width="80">
        <template #default="{ row }">{{ row.skills?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="800" fixed="right">
        <template #default="{ row }">
          <el-button
            text
            type="primary"
            @click="$router.push(`/employees/${row.id}`)"
            >详情</el-button
          >
          <el-button
            text
            type="primary"
            @click="$router.push(`/employees/${row.id}/edit`)"
            >编辑</el-button
          >
          <el-button
            v-if="row.mcp_enabled"
            text
            type="success"
            @click="showEmployeeMcpConfig(row)"
            >接入</el-button
          >
          <el-button
            v-if="row.mcp_enabled"
            text
            type="warning"
            @click="disableEmployeeMcp(row)"
            >关闭 MCP</el-button
          >
          <el-button v-else text type="warning" @click="enableEmployeeMcp(row)"
            >开启 MCP</el-button
          >
          <el-button text type="info" @click="showEmployeeConfigTest(row)"
            >测试</el-button
          >
          <el-button text type="success" @click="showGenerateManual(row)"
            >使用手册</el-button
          >
          <el-button
            text
            type="primary"
            @click="$router.push(`/employees/${row.id}/usage`)"
            >统计</el-button
          >
          <el-button
            v-if="row.feedback_upgrade_enabled"
            text
            type="primary"
            @click="$router.push(`/feedback/${row.id}`)"
          >
            反馈
          </el-button>
          <el-button
            v-if="!row.feedback_upgrade_enabled"
            text
            type="primary"
            @click="enableFeedbackUpgrade(row)"
          >
            开启反馈
          </el-button>
          <el-button
            v-else
            text
            type="warning"
            @click="disableFeedbackUpgrade(row)"
          >
            关闭反馈
          </el-button>
          <el-button text @click="$router.push(`/memory/${row.id}`)"
            >记忆</el-button
          >
          <el-button text @click="$router.push(`/sync/${row.id}`)"
            >同步</el-button
          >
          <el-button text type="danger" @click="handleDelete(row)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showMcpConfig" :title="mcpDialogTitle" width="600px">
      <div class="mcp-desc">
        <p>{{ mcpDialogDesc }}</p>
      </div>

      <el-tabs v-model="mcpTab" class="mcp-tabs">
        <el-tab-pane label="SSE (网络接入)" name="sse">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpSseConfig }}</code></pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="HTTP (Inspector 桥接)" name="http">
          <div class="mcp-code-wrap">
            <pre class="mcp-code"><code>{{ mcpHttpConfig }}</code></pre>
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button type="primary" @click="copyActiveMcpConfig"
          >复制当前配置</el-button
        >
        <el-button @click="showMcpConfig = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showConfigTestDialog"
      :title="testDialogTitle"
      width="760px"
    >
      <div v-loading="testLoading">
        <el-alert
          v-if="testResult"
          :title="testSummaryText"
          :type="testAlertType"
          show-icon
          :closable="false"
        />

        <el-row :gutter="16" class="test-stats-row" v-if="testResult">
          <el-col :span="6">
            <el-statistic
              title="技能总数"
              :value="testResult.summary.skills_total"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic
              title="技能可用"
              :value="testResult.summary.skills_available"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic
              title="脚本可执行"
              :value="testResult.summary.skills_executable"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic
              title="规则匹配领域"
              :value="testResult.summary.rule_domains_matched"
            />
          </el-col>
        </el-row>

        <h4 class="test-section-title">技能检查</h4>
        <el-table
          :data="testResult?.skills || []"
          stripe
          size="small"
          v-if="testResult"
        >
          <el-table-column prop="skill_id" label="技能 ID" width="120" />
          <el-table-column prop="name" label="名称" width="130" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="checkTagType(row.status)" size="small">{{
                row.status
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="entry_count"
            label="脚本数"
            width="80"
            align="center"
          />
          <el-table-column label="样例脚本" show-overflow-tooltip>
            <template #default="{ row }">{{
              (row.sample_entries || []).join(" | ") || "-"
            }}</template>
          </el-table-column>
          <el-table-column prop="message" label="结果" width="180" />
        </el-table>
        <el-empty v-else description="暂无测试结果" :image-size="50" />

        <h4 class="test-section-title">规则检查</h4>
        <el-table
          :data="testResult?.rule_domains || []"
          stripe
          size="small"
          v-if="testResult"
        >
          <el-table-column prop="domain" label="规则领域" width="130" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="checkTagType(row.status)" size="small">{{
                row.status
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="matched_rule_count"
            label="匹配规则数"
            width="110"
            align="center"
          />
          <el-table-column label="样例标题" show-overflow-tooltip>
            <template #default="{ row }">{{
              (row.sample_titles || []).join(" / ") || "-"
            }}</template>
          </el-table-column>
          <el-table-column prop="message" label="结果" width="180" />
        </el-table>
        <el-empty v-else description="暂无测试结果" :image-size="50" />

        <h4 class="test-section-title">MCP 接口测试</h4>
        <el-alert
          v-if="mcpTestResult"
          :title="mcpTestResult.message"
          :type="mcpTestAlertType"
          show-icon
          :closable="false"
        />
        <el-empty v-else description="暂无测试结果" :image-size="50" />

        <h4 class="test-section-title">问题清单</h4>
        <div
          class="issue-list"
          v-if="testResult && (blockingIssues.length || warningIssues.length)"
        >
          <el-tag
            v-for="item in blockingIssues"
            :key="`block-${item}`"
            type="danger"
            class="issue-tag"
          >
            阻塞: {{ item }}
          </el-tag>
          <el-tag
            v-for="item in warningIssues"
            :key="`warn-${item}`"
            type="warning"
            class="issue-tag"
          >
            警告: {{ item }}
          </el-tag>
        </div>
        <el-empty v-else description="未发现问题" :image-size="50" />
      </div>

      <template #footer>
        <el-button type="primary" :loading="testLoading" @click="runConfigTest"
          >重新测试</el-button
        >
        <el-button @click="showConfigTestDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showPromptDialog"
      :title="promptDialogTitle"
      width="700px"
    >
      <div v-loading="promptLoading">
        <el-tabs v-model="promptTab">
          <el-tab-pane label="生成使用手册" name="generate">
            <el-alert
              v-if="generatedPrompt"
              title="使用手册生成成功"
              type="success"
              show-icon
              :closable="false"
              style="margin-bottom: 16px"
            >
              <template #default>
                <div style="margin-top: 8px; font-size: 13px">
                  供应商: {{ promptProvider }} | 模型: {{ promptModel }}
                </div>
              </template>
            </el-alert>

            <div v-if="generatedPrompt" class="prompt-content">
              <div class="prompt-rendered" v-html="renderedPromptHtml"></div>
            </div>
            <el-empty
              v-else
              description="点击下方按钮生成员工使用手册"
              :image-size="50"
            />
          </el-tab-pane>

          <el-tab-pane label="历史记录" name="history">
            <el-table
              :data="promptHistory"
              stripe
              size="small"
              v-loading="historyLoading"
            >
              <el-table-column prop="created_at" label="生成时间" width="160" />
              <el-table-column prop="provider" label="供应商" width="120" />
              <el-table-column prop="model" label="模型" width="120" />
              <el-table-column label="操作" width="150">
                <template #default="{ row }">
                  <el-button text type="primary" @click="viewHistoryPrompt(row)"
                    >查看</el-button
                  >
                  <el-button
                    text
                    type="danger"
                    @click="deleteHistoryPrompt(row)"
                    >删除</el-button
                  >
                </template>
              </el-table-column>
            </el-table>
            <el-empty
              v-if="!promptHistory.length && !historyLoading"
              description="暂无历史记录"
              :image-size="50"
            />
          </el-tab-pane>
        </el-tabs>
      </div>

      <template #footer>
        <el-button v-if="generatedPrompt" type="primary" @click="copyPrompt"
          >复制手册</el-button
        >
        <el-button type="info" @click="copyTemplate">复制提示词模板</el-button>
        <el-button
          v-if="employeeManualEnabled"
          type="success"
          :loading="promptLoading"
          @click="runGeneratePrompt"
          >生成使用手册</el-button
        >
        <el-button v-else type="info" disabled>大模型生成已禁用</el-button>
        <el-button @click="showPromptDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showManualDialog"
      :title="manualDialogTitle"
      width="700px"
    >
      <div v-loading="manualLoading">
        <el-alert
          v-if="generatedManual"
          title="使用手册模板加载成功"
          type="success"
          show-icon
          :closable="false"
          style="margin-bottom: 16px"
        />

        <div v-if="generatedManual" class="prompt-content">
          <div class="prompt-rendered" v-html="renderedManualHtml"></div>
        </div>
        <el-empty
          v-else
          description="点击下方按钮加载手册模板"
          :image-size="50"
        />
      </div>

      <template #footer>
        <el-button v-if="generatedManual" type="primary" @click="copyManual"
          >复制手册模板</el-button
        >
        <el-button
          type="success"
          :loading="manualLoading"
          @click="runGenerateManual"
          >加载手册模板</el-button
        >
        <el-button @click="showManualDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { marked } from "marked";
import api from "@/utils/api.js";

const employees = ref([]);
const loading = ref(false);
const showMcpConfig = ref(false);
const mcpTab = ref("sse");
const currentEmployee = ref(null);
const mcpDialogTitle = ref("员工 MCP 接入");
const mcpDialogDesc = ref(
  "将该员工配置挂载到 AI 编辑器后，模型即可按员工配置读取技能、规则和记忆。",
);
const showConfigTestDialog = ref(false);
const testDialogTitle = ref("员工配置测试");
const testLoading = ref(false);
const testTargetEmployee = ref(null);
const testResult = ref(null);
const mcpTestResult = ref(null);
const showPromptDialog = ref(false);
const promptDialogTitle = ref("生成员工使用手册");
const promptLoading = ref(false);
const promptTargetEmployee = ref(null);
const generatedPrompt = ref("");
const promptProvider = ref("");
const promptModel = ref("");
const promptTab = ref("generate");
const promptHistory = ref([]);
const historyLoading = ref(false);
const showManualDialog = ref(false);
const manualDialogTitle = ref("使用手册模板");
const manualLoading = ref(false);
const manualTargetEmployee = ref(null);
const generatedManual = ref("");
const systemConfig = ref({
  enable_project_manual_generation: false,
  enable_employee_manual_generation: false,
});
const employeeManualEnabled = computed(
  () => !!systemConfig.value.enable_employee_manual_generation,
);

const renderedPromptHtml = computed(() => {
  if (!generatedPrompt.value) return "";
  try {
    return marked.parse(generatedPrompt.value);
  } catch (e) {
    return generatedPrompt.value.replace(/\n/g, "<br>");
  }
});

const renderedManualHtml = computed(() => {
  if (!generatedManual.value) return "";
  try {
    return marked.parse(generatedManual.value);
  } catch (e) {
    return generatedManual.value.replace(/\n/g, "<br>");
  }
});

const mcpSseConfig = computed(() => {
  if (!currentEmployee.value) return "";
  const serverName = `employee-${currentEmployee.value.id}`;
  return JSON.stringify(
    {
      mcpServers: {
        [serverName]: {
          type: "sse",
          url: `http://localhost:8000/mcp/employees/${currentEmployee.value.id}/sse?key=YOUR_API_KEY&project_id=default`,
        },
      },
    },
    null,
    2,
  );
});

const mcpHttpConfig = computed(() => {
  if (!currentEmployee.value) return "";
  const serverName = `employee-${currentEmployee.value.id}`;
  return JSON.stringify(
    {
      mcpServers: {
        [serverName]: {
          command: "npx",
          args: [
            "-y",
            "@modelcontextprotocol/inspector",
            `http://localhost:8000/mcp/employees/${currentEmployee.value.id}/mcp?key=YOUR_API_KEY&project_id=default`,
          ],
        },
      },
    },
    null,
    2,
  );
});

const blockingIssues = computed(() => testResult.value?.blocking_issues || []);
const warningIssues = computed(() => testResult.value?.warning_issues || []);
const testAlertType = computed(() => {
  const status = testResult.value?.summary?.overall_status;
  return (
    { healthy: "success", warning: "warning", failed: "error" }[status] ||
    "info"
  );
});
const testSummaryText = computed(() => {
  const summary = testResult.value?.summary;
  if (!summary) return "等待测试";
  if (summary.overall_status === "healthy")
    return "配置测试通过：技能与规则均可用";
  if (summary.overall_status === "warning") return "配置测试通过，但存在警告项";
  return "配置测试失败：存在阻塞问题";
});
const mcpTestAlertType = computed(() => {
  const status = mcpTestResult.value?.status;
  if (status === "success") return "success";
  if (status === "disabled") return "warning";
  return "error";
});

async function fetchList() {
  loading.value = true;
  try {
    const { employees: list } = await api.get("/employees");
    employees.value = list;
  } catch {
    ElMessage.error("加载失败");
  } finally {
    loading.value = false;
  }
}

async function fetchSystemConfig() {
  try {
    const data = await api.get("/system-config");
    systemConfig.value = {
      enable_project_manual_generation:
        !!data?.config?.enable_project_manual_generation,
      enable_employee_manual_generation:
        !!data?.config?.enable_employee_manual_generation,
    };
  } catch {
    systemConfig.value = {
      enable_project_manual_generation: false,
      enable_employee_manual_generation: false,
    };
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除员工「${row.name}」？`, "确认");
  try {
    await api.delete(`/employees/${row.id}`);
    ElMessage.success("已删除");
    fetchList();
  } catch {
    ElMessage.error("删除失败");
  }
}

function showEmployeeMcpConfig(row) {
  currentEmployee.value = row;
  mcpTab.value = "sse";
  mcpDialogTitle.value = `员工接入: ${row.name}`;
  showMcpConfig.value = true;
}

async function enableEmployeeMcp(row) {
  try {
    loading.value = true;
    await api.put(`/employees/${row.id}`, { mcp_enabled: true });
    ElMessage.success("已开启员工 MCP 服务");
    await fetchList();
    const updated = employees.value.find((item) => item.id === row.id) || row;
    showEmployeeMcpConfig(updated);
  } catch (e) {
    ElMessage.error(e.detail || "开启 MCP 失败");
  } finally {
    loading.value = false;
  }
}

async function disableEmployeeMcp(row) {
  await ElMessageBox.confirm(
    `确定关闭员工「${row.name}」的 MCP 服务？`,
    "确认",
  );
  try {
    loading.value = true;
    await api.put(`/employees/${row.id}`, { mcp_enabled: false });
    ElMessage.success("已关闭员工 MCP 服务");
    await fetchList();
    if (currentEmployee.value?.id === row.id) {
      showMcpConfig.value = false;
      currentEmployee.value = null;
    }
  } catch (e) {
    ElMessage.error(e.detail || "关闭 MCP 失败");
  } finally {
    loading.value = false;
  }
}

async function enableFeedbackUpgrade(row) {
  try {
    loading.value = true;
    await api.put(`/employees/${row.id}`, { feedback_upgrade_enabled: true });
    ElMessage.success("已开启反馈升级");
    await fetchList();
  } catch (e) {
    ElMessage.error(e.detail || "开启反馈失败");
  } finally {
    loading.value = false;
  }
}

async function disableFeedbackUpgrade(row) {
  await ElMessageBox.confirm(
    `确定关闭员工「${row.name}」的反馈升级模块？`,
    "确认",
  );
  try {
    loading.value = true;
    await api.put(`/employees/${row.id}`, { feedback_upgrade_enabled: false });
    ElMessage.success("已关闭反馈升级");
    await fetchList();
  } catch (e) {
    ElMessage.error(e.detail || "关闭反馈失败");
  } finally {
    loading.value = false;
  }
}

function checkTagType(status) {
  return (
    { ok: "success", warning: "warning", missing: "danger" }[status] || "info"
  );
}

async function runConfigTest() {
  if (!testTargetEmployee.value?.id) return;
  testLoading.value = true;
  try {
    const data = await api.get(
      `/employees/${testTargetEmployee.value.id}/config-test`,
    );
    testResult.value = data;
    if (data.summary?.overall_status === "failed") {
      ElMessage.error("配置测试发现阻塞问题");
    } else if (data.summary?.overall_status === "warning") {
      ElMessage.warning("配置测试通过，但存在警告项");
    } else {
      ElMessage.success("配置测试通过");
    }

    await runMcpTest();
  } catch (e) {
    ElMessage.error(e.detail || "配置测试失败");
  } finally {
    testLoading.value = false;
  }
}

async function runMcpTest() {
  if (!testTargetEmployee.value?.id) return;
  try {
    const data = await api.post(
      `/employees/${testTargetEmployee.value.id}/mcp-test`,
    );
    mcpTestResult.value = data;
  } catch (e) {
    mcpTestResult.value = {
      status: "error",
      message: e.detail || "MCP 测试失败",
    };
  }
}

async function showEmployeeConfigTest(row) {
  testTargetEmployee.value = row;
  testDialogTitle.value = `配置测试: ${row.name}`;
  testResult.value = null;
  mcpTestResult.value = null;
  showConfigTestDialog.value = true;
  await runConfigTest();
}

async function showGeneratePrompt(row) {
  if (!employeeManualEnabled.value) {
    ElMessage.warning("员工手册功能已被系统配置禁用");
    return;
  }
  promptTargetEmployee.value = row;
  promptDialogTitle.value = `生成使用手册: ${row.name}`;
  generatedPrompt.value = "";
  promptProvider.value = "";
  promptModel.value = "";
  promptTab.value = "generate";
  showPromptDialog.value = true;
  await fetchPromptHistory();
}

async function fetchPromptHistory() {
  if (!promptTargetEmployee.value?.id) return;
  historyLoading.value = true;
  try {
    const data = await api.get(
      `/employees/${promptTargetEmployee.value.id}/prompt-history`,
    );
    promptHistory.value = data.history || [];
  } catch (e) {
    promptHistory.value = [];
  } finally {
    historyLoading.value = false;
  }
}

function viewHistoryPrompt(row) {
  generatedPrompt.value = row.prompt || "";
  promptProvider.value = row.provider || "";
  promptModel.value = row.model || "";
  promptTab.value = "generate";
}

async function deleteHistoryPrompt(row) {
  await ElMessageBox.confirm("确定删除此历史记录？", "确认");
  try {
    await api.delete(
      `/employees/${promptTargetEmployee.value.id}/prompt-history/${row.id}`,
    );
    ElMessage.success("已删除");
    await fetchPromptHistory();
  } catch (e) {
    ElMessage.error(e.detail || "删除失败");
  }
}

async function runGeneratePrompt() {
  if (!employeeManualEnabled.value) {
    ElMessage.warning("员工手册功能已被系统配置禁用");
    return;
  }
  if (!promptTargetEmployee.value?.id) return;
  promptLoading.value = true;
  try {
    const data = await api.post(
      `/employees/${promptTargetEmployee.value.id}/generate-manual`,
    );
    generatedPrompt.value = data.manual || "";
    promptProvider.value = data.provider || "";
    promptModel.value = data.model || "";
    ElMessage.success("使用手册生成成功");
  } catch (e) {
    ElMessage.error(e.detail || "生成使用手册失败");
  } finally {
    promptLoading.value = false;
  }
}

async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(generatedPrompt.value);
    ElMessage.success("使用手册已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败");
  }
}

async function copyTemplate() {
  if (!promptTargetEmployee.value?.id) return;
  try {
    const data = await api.get(
      `/employees/${promptTargetEmployee.value.id}/manual-template`,
    );
    await navigator.clipboard.writeText(data.template || "");
    ElMessage.success("提示词模板已复制，可粘贴到任何 AI 使用");
  } catch (e) {
    ElMessage.error(e.detail || "复制失败");
  }
}

async function showGenerateManual(row) {
  manualTargetEmployee.value = row;
  manualDialogTitle.value = `使用手册模板: ${row.name}`;
  generatedManual.value = "";
  showManualDialog.value = true;
  await runGenerateManual();
}

async function runGenerateManual() {
  if (!manualTargetEmployee.value?.id) return;
  manualLoading.value = true;
  try {
    const data = await api.get(
      `/employees/${manualTargetEmployee.value.id}/manual-template`,
    );
    generatedManual.value = data.template || "";
    ElMessage.success("使用手册模板加载成功");
  } catch (e) {
    ElMessage.error(e.detail || "加载使用手册模板失败");
  } finally {
    manualLoading.value = false;
  }
}

async function copyManual() {
  try {
    await navigator.clipboard.writeText(generatedManual.value);
    ElMessage.success("手册模板已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败");
  }
}

async function copyActiveMcpConfig() {
  const content =
    mcpTab.value === "sse" ? mcpSseConfig.value : mcpHttpConfig.value;
  try {
    await navigator.clipboard.writeText(content);
    ElMessage.success("配置已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败");
  }
}

function copyManualTemplate(row) {
  manualTargetEmployee.value = row;
  manualDialogTitle.value = `使用手册模板: ${row.name}`;

  // 生成模板内容
  const skillsText = row.skills?.length
    ? row.skills
        .map((s) => `- ${s.name || s}：${s.description || ""}`)
        .join("\n")
    : "无";
  const domainsText = (() => {
    const seen = new Set();
    const domains = [];
    for (const item of row.rule_bindings || []) {
      const domain = String(item?.domain || "").trim();
      const key = domain.toLowerCase();
      if (!domain || seen.has(key)) continue;
      seen.add(key);
      domains.push(domain);
    }
    return domains.length ? domains.map((d) => `- ${d}`).join("\n") : "无";
  })();
  const styleHintsText = row.style_hints?.length
    ? row.style_hints.map((h) => `- ${h}`).join("\n")
    : "无";

  generatedManual.value = `请为以下 AI 员工生成一份使用手册，面向接入方 AI 平台。

员工信息：
- ID：${row.id}
- 名称：${row.name}
- 描述：${row.description || ""}
- 语调：${row.tone || ""}
- 风格：${row.verbosity || ""}
- 语言：${row.language || ""}

绑定技能：
${skillsText}

规则领域：
${domainsText}

风格提示：
${styleHintsText}

记忆配置：
- 作用域：${row.memory_scope || ""}
- 保留期：${row.memory_retention_days || 0}天

手册要求：
1. 员工简介（定位、适用场景）
2. MCP 接入配置（SSE 和 HTTP 两种方式，使用 \`\`\`json 代码块）
3. 项目配置（重要）
   - 在项目根目录创建 .mcp-project.json 文件
   - 配置示例（\`\`\`json 代码块）：
     {
       "project_name": "Your Project Name",
       "description": "项目描述（可选）"
     }
   - 参考示例文件：.mcp-project.json.example
   - 如果不传 project_name 参数，系统会自动读取此文件
   - 如果文件不存在，系统会自动创建默认配置（project_name: "default"）
4. 核心功能：
   - 技能列表（列出每个技能及用途）
   - 规则领域（列出每个领域及适用场景）
   - 风格约束（列出风格提示）
   - 记忆功能：recall_employee_memory(query, project_name)，作用域 ${row.memory_scope || ""}，保留 ${row.memory_retention_days || 0}天
     调用示例（\`\`\`json 代码块）：
     {
       "name": "recall_employee_memory",
       "arguments": {
         "query": "登录页改版决策",
         "project_name": "my-project"
       }
     }
     注意：project_name 可省略，系统会自动从 .mcp-project.json 读取
   - 反馈工单：submit_feedback_bug(title, symptom, expected, project_name, category, severity, session_id, rule_id, source_context)
     调用示例（\`\`\`json 代码块）：
     {
       "name": "submit_feedback_bug",
       "arguments": {
         "title": "登录按钮样式错误",
         "symptom": "按钮颜色与设计稿不符",
         "expected": "按钮应为主题色",
         "project_name": "my-project",
         "category": "frontend",
         "severity": "medium"
       }
     }
     注意：project_name 可省略，系统会自动从 .mcp-project.json 读取
5. 使用建议（project_name 作用、推荐工作流、注意事项）

格式：标准 Markdown，所有 JSON 用 \`\`\`json 代码块`;

  showManualDialog.value = true;
}

onMounted(async () => {
  await Promise.all([fetchList(), fetchSystemConfig()]);
});
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.usage-alert {
  margin-bottom: 12px;
}
.toolbar h3 {
  margin: 0;
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

.test-stats-row {
  margin: 16px 0;
}

.test-section-title {
  margin: 16px 0 8px;
}

.issue-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.issue-tag {
  margin-right: 0;
}

.prompt-content {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 16px;
  max-height: 500px;
  overflow-y: auto;
}

.prompt-rendered {
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
}

.prompt-rendered h1,
.prompt-rendered h2,
.prompt-rendered h3,
.prompt-rendered h4 {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: 600;
}

.prompt-rendered h1 {
  font-size: 20px;
}
.prompt-rendered h2 {
  font-size: 18px;
}
.prompt-rendered h3 {
  font-size: 16px;
}
.prompt-rendered h4 {
  font-size: 14px;
}

.prompt-rendered ul,
.prompt-rendered ol {
  margin: 8px 0;
  padding-left: 24px;
}

.prompt-rendered li {
  margin: 4px 0;
}

.prompt-rendered code {
  background: #e6e8eb;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: "Courier New", Courier, monospace;
  font-size: 13px;
}

.prompt-rendered pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.prompt-rendered pre code {
  background: transparent;
  padding: 0;
  color: inherit;
}

.prompt-rendered p {
  margin: 8px 0;
}

.prompt-rendered strong {
  font-weight: 600;
}
</style>
