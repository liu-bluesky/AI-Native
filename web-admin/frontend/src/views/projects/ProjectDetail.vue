<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>项目详情</h3>
      <div class="toolbar-actions">
        <el-button type="warning" @click="openEditDialog">编辑项目</el-button>
        <el-button v-if="canOpenProjectChat" type="primary" @click="openProjectChat"
          >AI 对话</el-button
        >
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
      <el-descriptions-item label="工作区路径" :span="2">{{
        project.workspace_path || "-"
      }}</el-descriptions-item>
      <el-descriptions-item label="AI 入口文件" :span="2">{{
        project.ai_entry_file || "-"
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
        <h4>可见用户</h4>
        <el-button
          type="primary"
          size="small"
          :disabled="!canManageProjectUsers"
          @click="openAddUserDialog"
          >添加用户</el-button
        >
      </div>

      <el-table :data="projectUsers" stripe>
        <el-table-column prop="username" label="用户名" width="180" />
        <el-table-column prop="role" label="项目角色" width="120" />
        <el-table-column prop="user_role" label="系统角色" width="140">
          <template #default="{ row }">
            <span>{{ row.user_role || "-" }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">{{
              row.enabled ? "启用" : "停用"
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="用户存在" width="120">
          <template #default="{ row }">
            <el-tag :type="row.user_exists ? 'success' : 'danger'">{{
              row.user_exists ? "正常" : "已删除"
            }}</el-tag>
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
              :disabled="!canManageProjectUsers"
              @click="removeProjectUser(row)"
              >移除</el-button
            >
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!projectUsers.length" description="暂无可见用户" />
    </div>

    <div class="block">
      <div class="block-header">
        <h4>成员管理</h4>
        <el-button
          type="primary"
          size="small"
          :disabled="!canManageProjectUsers"
          @click="openAddMember"
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
        <h4>项目记忆</h4>
      </div>
      <div class="memory-filters">
        <el-input
          v-model="memoryFilters.query"
          clearable
          placeholder="按内容关键词筛选"
          style="width: 240px"
          @keyup.enter="fetchProjectMemories"
        />
        <el-select
          v-model="memoryFilters.employeeId"
          clearable
          filterable
          placeholder="全部员工"
          style="width: 220px"
        >
          <el-option
            v-for="item in members"
            :key="item.employee_id"
            :label="`${item.employee_name || item.employee_id} (${item.employee_id})`"
            :value="item.employee_id"
          />
        </el-select>
        <el-select
          v-model="memoryFilters.type"
          clearable
          placeholder="全部类型"
          style="width: 180px"
        >
          <el-option
            v-for="item in memoryTypeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="memoryFilters.limit" style="width: 140px">
          <el-option
            v-for="size in memoryLimitOptions"
            :key="size"
            :label="`每人 ${size} 条`"
            :value="size"
          />
        </el-select>
        <el-button type="primary" :loading="memoryLoading" @click="fetchProjectMemories"
          >筛选</el-button
        >
        <el-button :disabled="memoryLoading" @click="resetMemoryFilters"
          >重置</el-button
        >
      </div>

      <el-table :data="filteredMemoryRows" stripe v-loading="memoryLoading">
        <el-table-column prop="employee_name" label="员工" width="180">
          <template #default="{ row }">
            <span>{{ row.employee_name || row.employee_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="employee_id" label="员工 ID" width="150" />
        <el-table-column prop="type" label="类型" width="150">
          <template #default="{ row }">
            {{ getMemoryTypeLabel(row.type) }}
          </template>
        </el-table-column>
        <el-table-column prop="content" label="内容" min-width="320" show-overflow-tooltip />
        <el-table-column prop="importance" label="重要度" width="90" />
        <el-table-column prop="scope" label="作用域" width="140" />
        <el-table-column prop="created_at" label="创建时间" min-width="180" />
      </el-table>
      <el-empty
        v-if="!filteredMemoryRows.length && !memoryLoading"
        description="暂无匹配的项目记忆"
      />
    </div>

    <div class="block">
      <div class="block-header">
        <h4>项目 MCP 地址</h4>
      </div>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="SSE">
          <code>{{ projectMcpSseUrl }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="HTTP">
          <code>{{ projectMcpHttpUrl }}</code>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="block">
      <div class="block-header">
        <h4>外部 MCP</h4>
      </div>
      <ExternalMcpManager
        :project-id="project.id || projectId"
        tip="项目侧也可直接维护外部 MCP；该配置会与 AI 对话页共用。"
      />
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

    <el-dialog v-model="showAddUserDialog" title="添加可见用户" width="520px">
      <el-form :model="userForm" label-width="100px">
        <el-form-item label="用户" required>
          <el-select
            v-model="userForm.usernames"
            multiple
            collapse-tags
            collapse-tags-tooltip
            filterable
            placeholder="请选择用户（可多选）"
            style="width: 100%"
          >
            <el-option
              v-for="item in availableUserOptions"
              :key="item.username"
              :label="`${item.username} (${item.role_name || item.role || '-'})`"
              :value="item.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="项目角色">
          <el-input v-model="userForm.role" placeholder="member / owner" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="userForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddUserDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="addProjectUsers"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑项目" width="520px">
      <el-form :model="editForm" label-width="110px">
        <el-form-item label="项目名称" required>
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="项目描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="工作区路径">
          <el-input v-model="editForm.workspace_path" placeholder="可手动输入或点击选择目录">
            <template #append>
              <el-button @click="selectWorkspaceDirectory">选择目录</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="AI 入口文件">
          <el-input v-model="editForm.ai_entry_file" placeholder="如 .ai/ENTRY.md 或 /abs/path/to/ENTRY.md">
            <template #append>
              <el-button @click="selectAiEntryFile">选择文件</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="启用 MCP">
          <el-switch v-model="editForm.mcp_enabled" />
        </el-form-item>
        <el-form-item label="反馈升级">
          <el-switch v-model="editForm.feedback_upgrade_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
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
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { marked } from "marked";
import ExternalMcpManager from "@/components/ExternalMcpManager.vue";
import api from "@/utils/api.js";
import {
  pickWorkspaceDirectory as openWorkspaceDirectoryPicker,
  pickWorkspaceFile as openWorkspaceFilePicker,
  toWorkspaceRelativePath,
} from "@/utils/workspace-picker.js";
import { hasPermission } from "@/utils/permissions.js";
import { buildRuntimeUrl } from "@/utils/runtime-url.js";

const route = useRoute();
const router = useRouter();
const projectId = String(route.params.id || "");

const loading = ref(false);
const saving = ref(false);
const showAddDialog = ref(false);
const showAddUserDialog = ref(false);
const showEditDialog = ref(false);
const showManualDialog = ref(false);
const manualDialogTitle = ref("项目手册");
const manualLoading = ref(false);
const generatedManual = ref("");
const manualMode = ref("generate");
const systemConfig = ref({
  enable_project_manual_generation: false,
  enable_employee_manual_generation: false,
});
const memoryLoading = ref(false);

const project = ref({});
const projectUsers = ref([]);
const members = ref([]);
const employeeOptions = ref([]);
const userOptions = ref([]);
const projectMemories = ref([]);
const canManageProjectUsers = ref(false);
const memoryLimitOptions = [20, 50, 100];
const MEMORY_TYPE_LABELS = {
  "project-context": "项目上下文",
  "user-preference": "用户偏好",
  "key-event": "关键事件",
  "learned-pattern": "学习模式",
  "long-term-goal": "长期目标",
  taboo: "禁忌项",
  "stable-preference": "稳定偏好",
  "decision-pattern": "决策模式",
};
const memoryFilters = ref({
  query: "",
  employeeId: "",
  type: "",
  limit: 20,
});

const addForm = ref({
  employee_ids: [],
  role: "member",
  enabled: true,
});

const userForm = ref({
  usernames: [],
  role: "member",
  enabled: true,
});

const editForm = ref({
  name: "",
  description: "",
  workspace_path: "",
  ai_entry_file: "",
  mcp_enabled: true,
  feedback_upgrade_enabled: true,
});

const memberIdSet = computed(() => {
  return new Set(
    (members.value || [])
      .map((item) => String(item.employee_id || "").trim())
      .filter(Boolean),
  );
});

const projectUserSet = computed(() => {
  return new Set(
    (projectUsers.value || [])
      .map((item) => String(item.username || "").trim())
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

const availableUserOptions = computed(() => {
  const currentUsers = projectUserSet.value;
  return (userOptions.value || []).filter((item) => {
    const username = String(item.username || "").trim();
    return username && !currentUsers.has(username);
  });
});

const projectManualEnabled = computed(
  () => !!systemConfig.value.enable_project_manual_generation,
);
const canOpenProjectChat = computed(() => hasPermission("button.project.chat"));
const projectMcpSseUrl = computed(() => {
  if (!project.value?.id) return "";
  return buildRuntimeUrl(`/mcp/projects/${project.value.id}/sse?key=YOUR_API_KEY`);
});
const projectMcpHttpUrl = computed(() => {
  if (!project.value?.id) return "";
  return buildRuntimeUrl(`/mcp/projects/${project.value.id}/mcp?key=YOUR_API_KEY`);
});

const renderedManualHtml = computed(() => {
  if (!generatedManual.value) return "";
  try {
    return marked.parse(generatedManual.value);
  } catch {
    return generatedManual.value.replace(/\n/g, "<br>");
  }
});

const memberNameMap = computed(() => {
  const result = new Map();
  (members.value || []).forEach((item) => {
    const id = String(item.employee_id || "").trim();
    if (!id) return;
    result.set(id, String(item.employee_name || "").trim());
  });
  return result;
});

const memoryTypeOptions = computed(() => {
  const rawTypes = Array.from(
    new Set(
      (projectMemories.value || [])
        .map((item) => String(item.type || "").trim())
        .filter(Boolean),
    ),
  );
  return rawTypes.map((type) => ({
    value: type,
    label: MEMORY_TYPE_LABELS[type] || type,
  }));
});

const filteredMemoryRows = computed(() => {
  const selectedType = String(memoryFilters.value.type || "").trim();
  if (!selectedType) return projectMemories.value || [];
  return (projectMemories.value || []).filter(
    (item) => String(item.type || "").trim() === selectedType,
  );
});

function resetAddForm() {
  addForm.value = {
    employee_ids: [],
    role: "member",
    enabled: true,
  };
}

function resetUserForm() {
  userForm.value = {
    usernames: [],
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

async function fetchProjectUsers() {
  const data = await api.get(`/projects/${projectId}/users`);
  projectUsers.value = data.members || [];
  userOptions.value = data.all_users || [];
  canManageProjectUsers.value = !!data.can_manage;
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

function normalizeMemory(memory, employeeId = "") {
  const currentEmployeeId = String(memory?.employee_id || employeeId || "").trim();
  return {
    id: String(memory?.id || ""),
    employee_id: currentEmployeeId,
    employee_name: memberNameMap.value.get(currentEmployeeId) || "",
    project_name: String(memory?.project_name || ""),
    type: String(memory?.type || ""),
    content: String(memory?.content || ""),
    importance: Number(memory?.importance ?? 0),
    scope: String(memory?.scope || ""),
    created_at: String(memory?.created_at || ""),
  };
}

function getMemoryTypeLabel(type) {
  const key = String(type || "").trim();
  return MEMORY_TYPE_LABELS[key] || key || "-";
}

async function fetchProjectMemories() {
  memoryLoading.value = true;
  try {
    const currentMembers = (members.value || [])
      .map((item) => String(item.employee_id || "").trim())
      .filter(Boolean);
    if (!currentMembers.length) {
      projectMemories.value = [];
      return;
    }

    const query = String(memoryFilters.value.query || "").trim();
    const limitValue = Number(memoryFilters.value.limit || 20);
    const safeLimit = Number.isFinite(limitValue) && limitValue > 0 ? limitValue : 20;
    const selectedEmployeeId = String(memoryFilters.value.employeeId || "").trim();
    const targetEmployeeIds = selectedEmployeeId
      ? [selectedEmployeeId]
      : currentMembers;

    const responses = await Promise.allSettled(
      targetEmployeeIds.map(async (employeeId) => {
        const params = { limit: safeLimit };
        if (query) {
          params.query = query;
        }
        const data = await api.get(`/memory/${employeeId}`, { params });
        return (data.memories || []).map((item) => normalizeMemory(item, employeeId));
      }),
    );

    const failedCount = responses.filter((item) => item.status === "rejected").length;
    if (failedCount > 0) {
      ElMessage.warning(`部分员工记忆加载失败（${failedCount} 个）`);
    }

    const currentProjectName = String(project.value?.name || "").trim();
    const memoryMap = new Map();
    responses.forEach((item) => {
      if (item.status !== "fulfilled") return;
      item.value.forEach((memory) => {
        if (currentProjectName && memory.project_name !== currentProjectName) return;
        const key = String(memory.id || `${memory.employee_id}_${memory.created_at}`);
        if (!memoryMap.has(key)) {
          memoryMap.set(key, memory);
        }
      });
    });
    projectMemories.value = Array.from(memoryMap.values()).sort((a, b) =>
      String(b.created_at || "").localeCompare(String(a.created_at || "")),
    );
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载项目记忆失败");
    projectMemories.value = [];
  } finally {
    memoryLoading.value = false;
  }
}

async function resetMemoryFilters() {
  memoryFilters.value = {
    query: "",
    employeeId: "",
    type: "",
    limit: 20,
  };
  await fetchProjectMemories();
}

async function refresh() {
  loading.value = true;
  try {
    await Promise.all([
      fetchProject(),
      fetchProjectUsers(),
      fetchMembers(),
      fetchEmployees(),
      fetchSystemConfig(),
    ]);
    await fetchProjectMemories();
  } catch (err) {
    const message = err?.detail || err?.message || "加载失败";
    ElMessage.error(message);
    if (String(err?.detail || "").includes("Project access denied")) {
      router.push("/projects");
    }
  } finally {
    loading.value = false;
  }
}

function openProjectChat() {
  const currentProjectId = String(project.value?.id || projectId || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("当前项目 ID 无效");
    return;
  }
  const target = `/ai/chat?project_id=${encodeURIComponent(currentProjectId)}`;
  window.location.hash = `#${target}`;
}

function openAddMember() {
  resetAddForm();
  showAddDialog.value = true;
}

function openAddUserDialog() {
  resetUserForm();
  showAddUserDialog.value = true;
}

function openEditDialog() {
  editForm.value = {
    name: project.value.name || "",
    description: project.value.description || "",
    workspace_path: project.value.workspace_path || "",
    ai_entry_file: project.value.ai_entry_file || "",
    mcp_enabled: project.value.mcp_enabled ?? true,
    feedback_upgrade_enabled: project.value.feedback_upgrade_enabled ?? true,
  };
  showEditDialog.value = true;
}

async function selectWorkspaceDirectory() {
  const picked = await pickWorkspaceDirectory(editForm.value.workspace_path);
  if (picked === null) return;
  editForm.value.workspace_path = picked;
}

async function selectAiEntryFile() {
  const picked = await pickAiEntryFile(
    editForm.value.ai_entry_file,
    editForm.value.workspace_path,
  );
  if (picked === null) return;
  editForm.value.ai_entry_file = picked;
}

async function pickWorkspaceDirectory(currentPath = "") {
  return await openWorkspaceDirectoryPicker(currentPath, {
    title: "选择项目工作区目录",
  });
}

async function pickAiEntryFile(currentPath = "", workspacePath = "") {
  const picked = await openWorkspaceFilePicker(currentPath, {
    title: "选择 AI 入口文件",
    placeholder: ".ai/ENTRY.md",
    basePath: workspacePath,
  });
  if (picked === null) return null;
  return toWorkspaceRelativePath(picked, workspacePath) || String(picked || "").trim();
}

async function saveEdit() {
  const name = String(editForm.value.name || "").trim();
  if (!name) {
    ElMessage.warning("请输入项目名称");
    return;
  }
  saving.value = true;
  try {
    await api.put(`/projects/${projectId}`, editForm.value);
    ElMessage.success("项目已更新");
    showEditDialog.value = false;
    await fetchProject();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "更新失败");
  } finally {
    saving.value = false;
  }
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
    await fetchProjectMemories();
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

async function addProjectUsers() {
  const selected = [
    ...new Set(
      (userForm.value.usernames || [])
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  ];
  if (!selected.length) {
    ElMessage.warning("请选择用户");
    return;
  }
  const existingSet = projectUserSet.value;
  const toAdd = selected.filter((username) => !existingSet.has(username));
  const skipped = selected.filter((username) => existingSet.has(username));
  if (!toAdd.length) {
    ElMessage.warning("所选用户都已添加，无需重复添加");
    return;
  }
  saving.value = true;
  try {
    const roleValue = String(userForm.value.role || "member").trim() || "member";
    const results = await Promise.allSettled(
      toAdd.map((username) =>
        api.post(`/projects/${projectId}/users`, {
          username,
          role: roleValue,
          enabled: !!userForm.value.enabled,
        }),
      ),
    );
    const successCount = results.filter(
      (item) => item.status === "fulfilled",
    ).length;
    const failCount = results.length - successCount;
    await fetchProjectUsers();
    if (failCount === 0) {
      const extra = skipped.length ? `，已忽略重复 ${skipped.length} 人` : "";
      ElMessage.success(`成功添加 ${successCount} 人${extra}`);
      showAddUserDialog.value = false;
      return;
    }
    if (successCount > 0) {
      ElMessage.warning(`成功添加 ${successCount} 人，失败 ${failCount} 人`);
      return;
    }
    ElMessage.error("可见用户保存失败");
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
    await fetchProjectMemories();
  } catch {
    ElMessage.error("移除失败");
  }
}

async function removeProjectUser(row) {
  await ElMessageBox.confirm(
    `确定移除用户 ${row.username} 的项目访问权限？`,
    "确认",
    { type: "warning" },
  );
  try {
    await api.delete(`/projects/${projectId}/users/${encodeURIComponent(row.username)}`);
    ElMessage.success("用户访问权限已移除");
    await fetchProjectUsers();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "移除失败");
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

.memory-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
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
