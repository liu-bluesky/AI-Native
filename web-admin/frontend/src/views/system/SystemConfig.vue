<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3>系统配置</h3>
      <el-button type="primary" :loading="saving" @click="saveConfig"
        >保存配置</el-button
      >
    </div>

    <el-alert
      title="这两个开关仅控制员工/项目页面中的“大模型生成内容”按钮，不影响手册模板查看与复制。"
      type="info"
      :closable="false"
      show-icon
      class="tips"
    />

    <el-form label-width="220px" class="config-form">
      <el-form-item label="允许生成项目使用手册">
        <el-switch v-model="form.enable_project_manual_generation" />
      </el-form-item>

      <el-form-item label="允许生成员工手册">
        <el-switch v-model="form.enable_employee_manual_generation" />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "@/utils/api.js";

const loading = ref(false);
const saving = ref(false);

const form = ref({
  enable_project_manual_generation: false,
  enable_employee_manual_generation: false,
});

async function fetchConfig() {
  loading.value = true;
  try {
    const data = await api.get("/system-config");
    form.value = {
      enable_project_manual_generation:
        !!data?.config?.enable_project_manual_generation,
      enable_employee_manual_generation:
        !!data?.config?.enable_employee_manual_generation,
    };
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载系统配置失败");
  } finally {
    loading.value = false;
  }
}

async function saveConfig() {
  saving.value = true;
  try {
    await api.patch("/system-config", {
      enable_project_manual_generation:
        !!form.value.enable_project_manual_generation,
      enable_employee_manual_generation:
        !!form.value.enable_employee_manual_generation,
    });
    ElMessage.success("系统配置已保存");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存系统配置失败");
  } finally {
    saving.value = false;
  }
}

onMounted(fetchConfig);
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

.tips {
  margin-bottom: 18px;
}

.config-form {
  max-width: 720px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px;
}
</style>
