<template>
  <div v-loading="loading" class="resource-page">
    <div class="toolbar">
      <div>
        <h3>技能资源</h3>
        <p class="toolbar-desc">浏览外部技能仓库，按版本和风险评估后安装到本地技能库。</p>
      </div>
      <div class="toolbar-actions">
        <el-button @click="$router.push('/skills')">本地技能</el-button>
        <el-button type="primary" @click="fetchResources">刷新</el-button>
      </div>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" class="filter-form" @submit.prevent>
        <el-form-item label="来源">
          <el-select v-model="filters.source" style="width: 120px">
            <el-option label="Vett" value="vett" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="filters.q"
            placeholder="名称、描述、owner"
            clearable
            style="width: 260px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="风险">
          <el-select v-model="filters.risk" clearable placeholder="全部" style="width: 140px">
            <el-option v-for="item in RISK_OPTIONS" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-select v-model="filters.sort_by" style="width: 160px">
            <el-option label="安装量" value="installs" />
            <el-option label="最新" value="newest" />
            <el-option label="趋势" value="trending" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="items" stripe>
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="slug" label="Slug" min-width="220" show-overflow-tooltip />
      <el-table-column prop="description" label="描述" min-width="260" show-overflow-tooltip />
      <el-table-column label="最新版本" width="110">
        <template #default="{ row }">{{ row.latest_version?.version || "-" }}</template>
      </el-table-column>
      <el-table-column label="风险" width="110">
        <template #default="{ row }">
          <el-tag :type="riskTagType(row.latest_version?.risk)">{{ row.latest_version?.risk || "-" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="扫描状态" width="120">
        <template #default="{ row }">
          <el-tag :type="scanTagType(row.latest_version?.scan_status)">
            {{ row.latest_version?.scan_status || "-" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="install_count" label="安装量" width="100" align="right" />
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="goToDetail(row)">详情</el-button>
          <el-button text type="info" size="small" @click="openSource(row)">来源</el-button>
          <el-button
            text
            type="success"
            size="small"
            :disabled="!canInstall(row.latest_version)"
            @click="handleInstall(row)"
          >
            安装
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!items.length && !loading" description="暂无技能资源" />

    <div class="pagination-wrap" v-if="pagination.total > 0">
      <el-pagination
        background
        layout="total, prev, pager, next, jumper"
        :total="pagination.total"
        :page-size="pagination.limit"
        :current-page="currentPage"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import api from "@/utils/api.js";

const router = useRouter();
const RISK_OPTIONS = ["none", "low", "medium", "high", "critical"];

const loading = ref(false);
const items = ref([]);
const pagination = reactive({
  limit: 20,
  offset: 0,
  total: 0,
});
const filters = reactive({
  source: "vett",
  q: "",
  risk: "",
  sort_by: "installs",
});

const currentPage = computed(() => Math.floor(pagination.offset / pagination.limit) + 1);

function riskTagType(risk) {
  return (
    {
      none: "success",
      low: "success",
      medium: "warning",
      high: "danger",
      critical: "danger",
    }[String(risk || "").toLowerCase()] || "info"
  );
}

function scanTagType(status) {
  return (
    {
      completed: "success",
      processing: "warning",
      pending: "warning",
      failed: "danger",
    }[String(status || "").toLowerCase()] || "info"
  );
}

function canInstall(version) {
  if (!version || typeof version !== "object") return false;
  const action = String(version.policy_action || "").toLowerCase();
  const scanStatus = String(version.scan_status || "").toLowerCase();
  return scanStatus === "completed" && action !== "deny" && action !== "blocked";
}

async function fetchResources() {
  loading.value = true;
  try {
    const data = await api.get("/skill-resources", {
      params: {
        source: filters.source,
        q: String(filters.q || "").trim(),
        risk: filters.risk || undefined,
        sort_by: filters.sort_by,
        limit: pagination.limit,
        offset: pagination.offset,
      },
    });
    items.value = Array.isArray(data?.items) ? data.items : [];
    pagination.limit = Number(data?.pagination?.limit || pagination.limit || 20);
    pagination.offset = Number(data?.pagination?.offset || 0);
    pagination.total = Number(data?.pagination?.total || 0);
  } catch (err) {
    items.value = [];
    pagination.total = 0;
    ElMessage.error(err?.detail || err?.message || "加载技能资源失败");
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  pagination.offset = 0;
  fetchResources();
}

function resetFilters() {
  filters.source = "vett";
  filters.q = "";
  filters.risk = "";
  filters.sort_by = "installs";
  pagination.offset = 0;
  fetchResources();
}

function handlePageChange(page) {
  pagination.offset = (Math.max(1, Number(page || 1)) - 1) * pagination.limit;
  fetchResources();
}

function goToDetail(row) {
  router.push(`/skill-resources/${filters.source}/${row.slug}`);
}

function openSource(row) {
  const target = String(row?.source_url || "").trim();
  if (!target) {
    ElMessage.warning("该技能未提供来源地址");
    return;
  }
  window.open(target, "_blank", "noopener");
}

async function handleInstall(row) {
  const version = row?.latest_version;
  if (!canInstall(version)) {
    ElMessage.warning("当前版本尚不可安装");
    return;
  }
  if (String(version?.policy_action || "").toLowerCase() === "review") {
    await ElMessageBox.confirm(
      `技能「${row.name}」的最新版本被标记为需要人工确认，确定继续安装？`,
      "高风险确认",
      { type: "warning" },
    );
  }
  try {
    const result = await api.post(`/skill-resources/${filters.source}/${row.slug}/install`, {
      version: version.version,
    });
    ElMessage.success(result?.status === "already_installed" ? "技能已存在于本地技能库" : "技能已导入本地技能库");
    const localSkillId = String(result?.local_skill?.id || "").trim();
    if (localSkillId) {
      router.push(`/skills/${localSkillId}`);
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "安装失败");
  }
}

onMounted(fetchResources);
</script>

<style scoped>
.resource-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.toolbar h3 {
  margin: 0 0 6px;
}

.toolbar-desc {
  margin: 0;
  color: #64748b;
  line-height: 1.5;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.filter-card {
  border-radius: 18px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
}
</style>
