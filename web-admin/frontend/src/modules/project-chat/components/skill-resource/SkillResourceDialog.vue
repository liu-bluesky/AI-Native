<template>
  <el-dialog
    v-model="visibleModel"
    title="技能资源"
    width="min(880px, calc(100vw - 32px))"
    destroy-on-close
    class="skill-resource-dialog"
  >
    <div class="skill-resource-dialog__body">
      <div class="skill-resource-dialog__hint">
        对话里发现当前项目缺技能时，可以先选好本地下载目录，再打开下面的网站自己下载技能包或模板。保存后，当前对话会把这个目录当作优先参考的本地技能来源，但不会自动绑定到系统。
      </div>

      <div class="skill-resource-dialog__directory">
        <div class="skill-resource-dialog__directory-head">
          <div class="skill-resource-dialog__section-title">本地技能目录</div>
          <div class="skill-resource-dialog__directory-actions">
            <el-button
              size="small"
              :disabled="!workspacePathResolved"
              @click="$emit('use-workspace')"
            >
              使用当前工作区
            </el-button>
            <el-button
              size="small"
              :loading="directoryPicking"
              @click="$emit('pick-directory')"
            >
              选择目录
            </el-button>
            <el-button
              size="small"
              text
              :disabled="!directoryResolved"
              @click="$emit('copy-directory')"
            >
              复制路径
            </el-button>
          </div>
        </div>
        <div
          class="skill-resource-dialog__directory-value"
          :class="{ 'is-empty': !directoryResolved }"
        >
          {{
            directoryResolved ||
            "还没有选择目录。建议先选择本地技能下载目录。"
          }}
        </div>
        <div class="skill-resource-dialog__directory-meta">
          优先使用当前项目工作区，也可以单独指定一个技能下载目录。
        </div>
      </div>

      <div class="skill-resource-dialog__hint">
        在线技能市场搜索与自动安装已移除。请将技能包保存到上方目录，再在项目对话设置中配置技能目录。
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  workspacePathResolved: { type: String, default: "" },
  directoryResolved: { type: String, default: "" },
  directoryPicking: { type: Boolean, default: false },
});

const emit = defineEmits([
  "update:modelValue",
  "use-workspace",
  "pick-directory",
  "copy-directory",
]);

const visibleModel = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

</script>

<style scoped src="./SkillResourceDialog.css"></style>
