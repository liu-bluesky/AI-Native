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
      <el-alert
        title="MCP 仅使用本机进程"
        type="info"
        :closable="false"
        show-icon
      />
      <p class="unified-mcp-access__copy">
        当前项目不提供 HTTP 或 SSE 接入地址。请在项目 MCP 配置中添加本机
        <code>stdio</code> Server，并指定其命令、参数和工作目录。
      </p>
      <div class="unified-mcp-access__code-wrap">
        <pre class="unified-mcp-access__code"><code>{{ stdioConfig }}</code></pre>
      </div>
    </div>

    <template #footer>
      <el-button type="primary" @click="copyConfig">复制示例</el-button>
      <el-button @click="handleVisibleChange(false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from "vue";
import { ElMessage } from "element-plus";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: "MCP 配置" },
  width: { type: String, default: "720px" },
  projectId: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue", "close"]);

const stdioConfig = computed(() =>
  JSON.stringify(
    {
      "local-mcp-server": {
        description: "本机 MCP Server",
        type: "stdio",
        command: "/absolute/path/to/mcp-server",
        args: ["--stdio"],
        cwd: String(props.projectId || "").trim() || "/absolute/path/to/project",
      },
    },
    null,
    2,
  ),
);

async function copyConfig() {
  try {
    await navigator.clipboard.writeText(stdioConfig.value);
    ElMessage.success("本机 MCP 配置示例已复制");
  } catch {
    ElMessage.warning("复制失败，请手动复制配置内容");
  }
}

function handleVisibleChange(value) {
  emit("update:modelValue", value);
}

function handleClose() {
  emit("close");
}
</script>
