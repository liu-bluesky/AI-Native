<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>项目详情</h3>
      <div class="toolbar-actions">
        <el-button
          type="success"
          :loading="manualLoading"
          @click="showProjectManualTemplate"
          >手册模板</el-button
        >
        <el-button
          v-if="projectManualEnabled"
          type="primary"
          :loading="manualLoading"
          @click="showGenerateProjectManual"
          >生成使用手册</el-button
        >
        <el-button v-else type="info" disabled>大模型生成已禁用</el-button>
        <el-button @click="$router.push('/projects')">返回列表</el-button>
        <el-button @click="refresh">刷新</el-button>
      </div>
    </div>

    <el-descriptions :column="2" border v-if="project.id">
      <el-descriptions-item label="项目 ID">{{
        project.id
      }}</el-descriptions-item>
      <el-descriptions-item label="项目名称">{{
        project.name
      }}</el-descriptions-item>
      <el-descriptions-item label="MCP">
        <el-tag :type="project.mcp_enabled ? 'success' : 'info'">
          {{ project.mcp_enabled ? "开启" : "关闭" }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="反馈升级">
        <el-tag :type="project.feedback_upgrade_enabled ? 'success' : 'info'">
          {{ project.feedback_upgrade_enabled ? "开启" : "关闭" }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="描述" :span="2">{{
        project.description || "-"
      }}</el-descriptions-item>
    </el-descriptions>

    <div class="block">
      <div class="block-header">
        <h4>成员管理</h4>
        <el-button type="primary" size="small" @click="openAddMember"
          >添加成员</el-button
        >
      </div>

      <el-table :data="members" stripe>
        <el-table-column prop="employee_id" label="员工 ID" width="150" />
        <el-table-column prop="employee_name" label="员工名称" width="180" />
        <el-table-column prop="role" label="角色" width="120" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">{{
              row.enabled ? "启用" : "停用"
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="员工 MCP" width="120">
          <template #default="{ row }">
            <el-tag :type="row.employee_mcp_enabled ? 'success' : 'warning'">
              {{ row.employee_mcp_enabled ? "可用" : "关闭" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="加入时间" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.joined_at || "-" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button
              text
              type="danger"
              size="small"
              @click="removeMember(row)"
              >移除</el-button
            >
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!members.length" description="暂无成员" />
    </div>

    <div class="block">
      <div class="block-header">
        <h4>项目 MCP 地址</h4>
      </div>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="SSE">
          <code
            >http://localhost:8000/mcp/projects/{{
              project.id
            }}/sse?key=YOUR_API_KEY</code
          >
        </el-descriptions-item>
        <el-descriptions-item label="HTTP">
          <code
            >http://localhost:8000/mcp/projects/{{
              project.id
            }}/mcp?key=YOUR_API_KEY</code
          >
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <el-dialog v-model="showAddDialog" title="添加项目成员" width="520px">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="员工" required>
          <el-select
            v-model="addForm.employee_ids"
            multiple
            collapse-tags
            collapse-tags-tooltip
            filterable
            placeholder="请选择员工（可多选）"
            style="width: 100%"
          >
            <el-option
              v-for="item in availableEmployeeOptions"
              :key="item.id"
              :label="`${item.name} (${item.id})`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-input v-model="addForm.role" placeholder="member / owner" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="addForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="addMember"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="showManualDialog"
      :title="manualDialogTitle"
      width="760px"
    >
      <div v-loading="manualLoading">
        <el-alert
          v-if="generatedManual"
          :title="
            manualMode === 'template'
              ? '项目手册模板加载成功'
              : '项目使用手册生成成功'
          "
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
          :description="
            manualMode === 'template'
              ? '点击下方按钮加载手册模板'
              : '点击下方按钮生成使用手册'
          "
          :image-size="60"
        />
      </div>
      <template #footer>
        <el-button v-if="generatedManual" type="primary" @click="copyManual"
          >{{ manualMode === "template" ? "复制手册模板" : "复制使用手册" }}</el-button
        >
        <el-button
          type="success"
          :loading="manualLoading"
          @click="
            manualMode === 'template'
              ? showProjectManualTemplate()
              : runGenerateProjectManual()
          "
          >{{ manualMode === "template" ? "加载手册模板" : "生成使用手册" }}</el-button
        >
        <el-button @click="showManualDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { marked } from "marked";
import api from "@/utils/api.js";

const route = useRoute();
const projectId = String(route.params.id || "");

const loading = ref(false);
const saving = ref(false);
const showAddDialog = ref(false);
const showManualDialog = ref(false);
const manualDialogTitle = ref("项目手册");
const manualLoading = ref(false);
const generatedManual = ref("");
const manualMode = ref("generate");
const systemConfig = ref({
  enable_project_manual_generation: false,
  enable_employee_manual_generation: false,
});

const project = ref({});
const members = ref([]);
const employeeOptions = ref([]);

const addForm = ref({
  employee_ids: [],
  role: "member",
  enabled: true,
});

const memberIdSet = computed(() => {
  return new Set(
    (members.value || [])
      .map((item) => String(item.employee_id || "").trim())
      .filter(Boolean),
  );
});

const availableEmployeeOptions = computed(() => {
  const currentMembers = memberIdSet.value;
  return (employeeOptions.value || []).filter((item) => {
    const employeeId = String(item.id || "").trim();
    return employeeId && !currentMembers.has(employeeId);
  });
});

const projectManualEnabled = computed(
  () => !!systemConfig.value.enable_project_manual_generation,
);

const renderedManualHtml = computed(() => {
  if (!generatedManual.value) return "";
  try {
    return marked.parse(generatedManual.value);
  } catch {
    return generatedManual.value.replace(/\n/g, "<br>");
  }
});

function resetAddForm() {
  addForm.value = {
    employee_ids: [],
    role: "member",
    enabled: true,
  };
}

async function fetchEmployees() {
  try {
    const data = await api.get("/employees");
    employeeOptions.value = data.employees || [];
  } catch {
    employeeOptions.value = [];
  }
}

async function fetchProject() {
  const data = await api.get(`/projects/${projectId}`);
  project.value = data.project || {};
}

async function fetchMembers() {
  const data = await api.get(`/projects/${projectId}/members`);
  members.value = data.members || [];
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

async function refresh() {
  loading.value = true;
  try {
    await Promise.all([
      fetchProject(),
      fetchMembers(),
      fetchEmployees(),
      fetchSystemConfig(),
    ]);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

function openAddMember() {
  resetAddForm();
  showAddDialog.value = true;
}

async function showGenerateProjectManual() {
  if (!projectManualEnabled.value) {
    ElMessage.warning("项目手册功能已被系统配置禁用");
    return;
  }
  manualMode.value = "generate";
  manualDialogTitle.value = `生成使用手册: ${project.value?.name || projectId}`;
  generatedManual.value = "";
  showManualDialog.value = true;
  await runGenerateProjectManual();
}

async function runGenerateProjectManual() {
  if (!projectManualEnabled.value) {
    ElMessage.warning("项目手册功能已被系统配置禁用");
    return;
  }
  manualLoading.value = true;
  try {
    const data = await api.post(`/projects/${projectId}/generate-manual`);
    generatedManual.value = data.manual || "";
    ElMessage.success("项目使用手册生成成功");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "生成使用手册失败");
  } finally {
    manualLoading.value = false;
  }
}

async function showProjectManualTemplate() {
  manualLoading.value = true;
  try {
    const data = await api.get(`/projects/${projectId}/manual-template`);
    generatedManual.value = data.template || "";
    manualMode.value = "template";
    manualDialogTitle.value = `项目手册模板: ${project.value?.name || projectId}`;
    showManualDialog.value = true;
    ElMessage.success("项目手册模板加载成功");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载项目手册模板失败");
  } finally {
    manualLoading.value = false;
  }
}

async function copyManual() {
  try {
    await navigator.clipboard.writeText(generatedManual.value || "");
    ElMessage.success("内容已复制到剪贴板");
  } catch {
    ElMessage.error("复制失败");
  }
}

async function addMember() {
  const selected = [
    ...new Set(
      (addForm.value.employee_ids || [])
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  ];
  if (!selected.length) {
    ElMessage.warning("请选择员工");
    return;
  }
  const existingSet = memberIdSet.value;
  const toAdd = selected.filter((id) => !existingSet.has(id));
  const skipped = selected.filter((id) => existingSet.has(id));
  if (!toAdd.length) {
    ElMessage.warning("所选员工都已添加，无需重复添加");
    return;
  }
  saving.value = true;
  try {
    const roleValue = String(addForm.value.role || "member").trim() || "member";
    const results = await Promise.allSettled(
      toAdd.map((employeeId) =>
        api.post(`/projects/${projectId}/members`, {
          employee_id: employeeId,
          role: roleValue,
          enabled: !!addForm.value.enabled,
        }),
      ),
    );
    const successCount = results.filter(
      (item) => item.status === "fulfilled",
    ).length;
    const failCount = results.length - successCount;
    await fetchMembers();
    if (failCount === 0) {
      const extra = skipped.length ? `，已忽略重复 ${skipped.length} 人` : "";
      ElMessage.success(`成功添加 ${successCount} 人${extra}`);
      showAddDialog.value = false;
      return;
    }
    if (successCount > 0) {
      ElMessage.warning(`成功添加 ${successCount} 人，失败 ${failCount} 人`);
      return;
    }
    ElMessage.error("成员保存失败");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function removeMember(row) {
  await ElMessageBox.confirm(
    `确定移除成员 ${row.employee_name || row.employee_id}？`,
    "确认",
    { type: "warning" },
  );
  try {
    await api.delete(`/projects/${projectId}/members/${row.employee_id}`);
    ElMessage.success("成员已移除");
    await fetchMembers();
  } catch {
    ElMessage.error("移除失败");
  }
}

onMounted(refresh);
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

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.block {
  margin-top: 20px;
}

.block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.block-header h4 {
  margin: 0;
}

code {
  background: #f6f8fa;
  padding: 2px 6px;
  border-radius: 4px;
}

.prompt-content {
  max-height: 60vh;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px;
  background: #fff;
}

.prompt-rendered {
  line-height: 1.7;
  color: #1f2937;
  font-size: 14px;
  word-break: break-word;
}

.prompt-rendered :deep(pre) {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
}
</style>
