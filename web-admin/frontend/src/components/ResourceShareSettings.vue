<template>
  <el-divider content-position="left">数据权限</el-divider>
  <el-form-item label="可见范围">
    <el-radio-group v-model="form.share_scope">
      <el-radio value="private">仅自己</el-radio>
      <el-radio value="selected_users">指定用户</el-radio>
      <el-radio value="all_users">所有人</el-radio>
    </el-radio-group>
    <div class="hint">
      你创建的数据默认仅自己可见。共享员工后，该员工绑定的规则和技能会自动对相同范围可见。
    </div>
  </el-form-item>

  <el-form-item v-if="form.share_scope === 'selected_users'" label="共享给用户">
    <el-select
      v-model="form.shared_with_usernames"
      multiple
      collapse-tags
      collapse-tags-tooltip
      filterable
      clearable
      placeholder="选择可访问该数据的用户"
      style="width: 100%"
      :loading="loading"
    >
      <el-option
        v-for="item in shareUserOptions"
        :key="item.username"
        :label="item.label"
        :value="item.username"
      />
    </el-select>
    <div class="hint">
      仅被选中的用户名可查看该数据；他们仍不能编辑或删除。
    </div>
  </el-form-item>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import api from "@/utils/api.js";

const props = defineProps({
  form: {
    type: Object,
    required: true,
  },
});

const shareUserOptions = ref([]);
const loading = ref(false);

async function fetchShareOptions() {
  loading.value = true;
  try {
    const data = await api.get("/users/share-options");
    shareUserOptions.value = Array.isArray(data?.users)
      ? data.users.map((item) => {
          const username = String(item?.username || "").trim();
          const role = String(item?.role || "").trim();
          return {
            username,
            label: role ? `${username} (${role})` : username,
          };
        })
      : [];
  } catch (e) {
    shareUserOptions.value = [];
    ElMessage.error(e.detail || "加载共享用户失败");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  if (!props.form.share_scope) {
    props.form.share_scope = "private";
  }
  if (!Array.isArray(props.form.shared_with_usernames)) {
    props.form.shared_with_usernames = [];
  }
  fetchShareOptions();
});
</script>

<style scoped>
.hint {
  margin-top: 6px;
  color: var(--color-text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}
</style>
