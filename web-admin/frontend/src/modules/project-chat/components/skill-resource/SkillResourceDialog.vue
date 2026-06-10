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

      <div class="skill-resource-dialog__section-title">推荐网站</div>
      <div class="skill-resource-search">
        <el-input
          v-model="searchQueryModel"
          placeholder="搜索技能资源，例如 Java 开发、界面设计、浏览器调试"
          clearable
          @keyup.enter="$emit('search')"
        >
          <template #append>
            <el-button :loading="searchLoading" @click="$emit('search')">
              搜索
            </el-button>
          </template>
        </el-input>
        <div class="skill-resource-search__meta">
          <span>支持中文搜索，结果会下载到下方选择的本地技能目录。</span>
          <el-button
            v-if="searchQuery || searchResults.length"
            text
            size="small"
            @click="$emit('reset-search')"
          >
            清空结果
          </el-button>
        </div>
        <div v-if="resolvedQueries.length > 1" class="skill-resource-search__expanded">
          已自动扩展英文关键词：
          {{ resolvedQueries.join(" / ") }}
        </div>
      </div>

      <div
        v-if="searchResults.length"
        class="skill-resource-site-list skill-resource-site-list--search"
      >
        <article
          v-for="site in searchResults"
          :key="site.id || site.slug"
          class="skill-resource-site-card"
        >
          <div class="skill-resource-site-card__head">
            <div class="skill-resource-site-card__title-wrap">
              <div class="skill-resource-site-card__title">
                {{ site.title }}
              </div>
            </div>
            <el-tag
              v-if="site.latestVersionLabel"
              size="small"
              effect="plain"
              type="success"
            >
              {{ site.latestVersionLabel }}
            </el-tag>
          </div>
          <div v-if="site.description" class="skill-resource-site-card__desc">
            {{ site.description }}
          </div>
          <div
            v-if="site.localizedDescription"
            class="skill-resource-site-card__desc skill-resource-site-card__desc--localized"
          >
            {{ site.localizedDescription }}
          </div>
          <div class="skill-resource-site-card__url">{{ site.url }}</div>
          <div class="skill-resource-site-card__actions">
            <el-link :href="site.url" target="_blank" rel="noopener noreferrer">
              打开网站
            </el-link>
            <el-button
              text
              size="small"
              type="success"
              :loading="installingSlug === site.slug"
              :disabled="!site.canInstall"
              @click="$emit('install-site', site)"
            >
              下载到本地技能目录
            </el-button>
          </div>
        </article>
      </div>
      <el-empty
        v-else-if="searchQuery && !searchLoading"
        description="没有找到匹配的技能资源"
        :image-size="56"
      />
      <div
        v-if="
          searchQuery &&
          !searchLoading &&
          !searchResults.length &&
          resolvedQueries.length > 1
        "
        class="skill-resource-search__expanded skill-resource-search__expanded--empty"
      >
        已尝试关键词：{{ resolvedQueries.join(" / ") }}
      </div>

      <div v-if="sites.length" class="skill-resource-site-list">
        <article
          v-for="site in sites"
          :key="site.id"
          class="skill-resource-site-card"
        >
          <div class="skill-resource-site-card__head">
            <div class="skill-resource-site-card__title">{{ site.title }}</div>
            <div class="skill-resource-site-card__badge">推荐</div>
          </div>
          <div v-if="site.description" class="skill-resource-site-card__desc">
            {{ site.description }}
          </div>
          <div class="skill-resource-site-card__url">{{ site.url }}</div>
          <div class="skill-resource-site-card__actions">
            <el-link :href="site.url" target="_blank" rel="noopener noreferrer">
              打开网站
            </el-link>
            <el-button text size="small" @click="$emit('copy-site', site)">
              复制地址
            </el-button>
          </div>
        </article>
      </div>
      <el-empty v-else description="当前还没有配置技能网站" :image-size="56" />
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
  searchQuery: { type: String, default: "" },
  searchLoading: { type: Boolean, default: false },
  searchResults: { type: Array, default: () => [] },
  resolvedQueries: { type: Array, default: () => [] },
  sites: { type: Array, default: () => [] },
  installingSlug: { type: String, default: "" },
});

const emit = defineEmits([
  "update:modelValue",
  "update:searchQuery",
  "use-workspace",
  "pick-directory",
  "copy-directory",
  "search",
  "reset-search",
  "install-site",
  "copy-site",
]);

const visibleModel = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

const searchQueryModel = computed({
  get: () => props.searchQuery,
  set: (value) => emit("update:searchQuery", value),
});
</script>

<style scoped src="./SkillResourceDialog.css"></style>
