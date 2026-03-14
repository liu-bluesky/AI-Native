<template>
  <div v-loading="loading" class="detail-page">
    <div class="toolbar">
      <div>
        <h3>技能资源详情</h3>
        <p class="toolbar-desc">{{ detail.skill?.slug || "-" }}</p>
      </div>
      <div class="toolbar-actions">
        <el-button @click="$router.push('/skill-resources')">返回资源列表</el-button>
        <el-button @click="$router.push('/skills')">查看本地技能</el-button>
      </div>
    </div>

    <el-descriptions v-if="detail.skill" :column="2" border>
      <el-descriptions-item label="名称">{{ detail.skill.name || "-" }}</el-descriptions-item>
      <el-descriptions-item label="Slug">{{ detail.skill.slug || "-" }}</el-descriptions-item>
      <el-descriptions-item label="Owner">{{ detail.skill.owner || "-" }}</el-descriptions-item>
      <el-descriptions-item label="Repo">{{ detail.skill.repo || "-" }}</el-descriptions-item>
      <el-descriptions-item label="安装量">{{ detail.skill.install_count || 0 }}</el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ detail.skill.created_at || "-" }}</el-descriptions-item>
      <el-descriptions-item label="描述" :span="2">{{ detail.skill.description || "-" }}</el-descriptions-item>
      <el-descriptions-item label="来源地址" :span="2">
        <el-link v-if="detail.skill.source_url" :href="detail.skill.source_url" target="_blank" type="primary">
          {{ detail.skill.source_url }}
        </el-link>
        <span v-else>-</span>
      </el-descriptions-item>
    </el-descriptions>

    <div class="section-head">
      <h4>版本列表</h4>
      <span class="section-desc">安装时会重新拉取临时下载地址，并校验 hash。</span>
    </div>

    <el-table v-if="detail.versions.length" :data="detail.versions" stripe>
      <el-table-column prop="version" label="版本" width="110" />
      <el-table-column label="风险" width="110">
        <template #default="{ row }">
          <el-tag :type="riskTagType(row.risk)">{{ row.risk || "-" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="扫描状态" width="120">
        <template #default="{ row }">
          <el-tag :type="scanTagType(row.scan_status)">{{ row.scan_status || "-" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="commit_sha" label="Commit SHA" min-width="150" show-overflow-tooltip />
      <el-table-column prop="hash" label="Hash" min-width="220" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button
            text
            type="success"
            size="small"
            :disabled="!canInstall(row)"
            @click="handleInstall(row)"
          >
            安装此版本
          </el-button>
          <el-button text type="info" size="small" @click="openVersionSource(row)">来源</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="暂无版本信息" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import api from "@/utils/api.js";

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const detail = reactive({
  source: "vett",
  skill: null,
  versions: [],
});

const source = computed(() => String(route.params.source || "vett").trim() || "vett");
const slug = computed(() => String(route.params.slug || "").replace(/^\/+|\/+$/g, ""));

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
  const action = String(version?.policy_action || "").toLowerCase();
  const scanStatus = String(version?.scan_status || "").toLowerCase();
  return scanStatus === "completed" && action !== "deny" && action !== "blocked";
}

async function fetchDetail() {
  loading.value = true;
  try {
    const data = await api.get(`/skill-resources/${source.value}/${slug.value}`);
    detail.source = data?.source || source.value;
    detail.skill = data?.skill || null;
    detail.versions = Array.isArray(data?.versions) ? data.versions : [];
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载技能详情失败");
  } finally {
    loading.value = false;
  }
}

function openVersionSource(row) {
  const target = String(row?.source_url || detail.skill?.source_url || "").trim();
  if (!target) {
    ElMessage.warning("该版本未提供来源地址");
    return;
  }
  window.open(target, "_blank", "noopener");
}

async function handleInstall(version) {
  if (!canInstall(version)) {
    ElMessage.warning("当前版本不可安装");
    return;
  }
  if (String(version?.policy_action || "").toLowerCase() === "review") {
    await ElMessageBox.confirm(
      `版本 ${version.version} 被标记为需要人工确认，确定继续安装？`,
      "高风险确认",
      { type: "warning" },
    );
  }
  try {
    const result = await api.post(`/skill-resources/${source.value}/${slug.value}/install`, {
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

onMounted(fetchDetail);
watch([source, slug], () => {
  fetchDetail();
});
</script>

<style scoped>
.detail-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
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
}

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}

.section-head h4 {
  margin: 0;
}

.section-desc {
  color: #64748b;
  font-size: 13px;
}
</style>
