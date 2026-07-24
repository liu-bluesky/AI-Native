<template>
  <div v-if="results.length" class="capability-results">
    <article
      v-for="result in results"
      :key="result.model_tested || 'default'"
      class="capability-result-card"
    >
      <div class="capability-result-card__head">
        <div>
          <div class="capability-result-card__title">{{ result.model_tested || '默认配置' }}</div>
          <div class="capability-result-card__meta">
            {{ formatModelTypeLabel(result.model_type) }} ·
            {{ formatDateTime(result.tested_at, { withSeconds: true }) }} ·
            {{ result.latency_ms || 0 }} ms
          </div>
        </div>
        <div class="capability-result-card__tags">
          <el-tag :type="result.reachable ? 'success' : 'danger'" size="small">
            {{ result.reachable ? '能力测试成功' : '能力测试失败' }}
          </el-tag>
          <el-tag
            v-if="result.model_available !== null && result.model_available !== undefined"
            :type="result.model_available ? 'success' : 'warning'"
            size="small"
            effect="plain"
          >
            {{ result.model_available ? '/models 已包含' : '/models 未返回' }}
          </el-tag>
        </div>
      </div>
      <p class="capability-result-card__message">{{ result.message || '-' }}</p>
      <p v-if="result.output_text" class="capability-result-card__text">{{ result.output_text }}</p>
      <div v-if="normalizeArtifacts(result).length" class="capability-result-card__artifacts">
        <template
          v-for="(artifact, artifactIndex) in normalizeArtifacts(result)"
          :key="`${result.model_tested || 'default'}-${artifactIndex}`"
        >
          <el-image
            v-if="artifact.asset_type === 'image'"
            :src="artifact.preview_url || artifact.content_url"
            :preview-src-list="[artifact.content_url || artifact.preview_url]"
            fit="contain"
            class="capability-result-card__image"
            :alt="artifact.title || `${result.model_tested} 测试图片`"
          />
          <video
            v-else-if="artifact.asset_type === 'video'"
            :src="artifact.content_url"
            controls
            preload="metadata"
            class="capability-result-card__video"
          />
          <audio
            v-else-if="artifact.asset_type === 'audio'"
            :src="artifact.content_url"
            controls
            preload="metadata"
            class="capability-result-card__audio"
          />
          <el-link
            v-else-if="artifact.content_url"
            :href="artifact.content_url"
            target="_blank"
            type="primary"
          >
            {{ artifact.title || '打开测试结果' }}
          </el-link>
        </template>
      </div>
      <div v-if="result.probe_url" class="capability-result-card__endpoint">
        实际测试端点：{{ result.probe_url }}
      </div>
    </article>
  </div>
</template>

<script setup>
import { formatDateTime } from '@/utils/date.js'

defineProps({
  results: {
    type: Array,
    default: () => [],
  },
  formatModelTypeLabel: {
    type: Function,
    required: true,
  },
})

function normalizeArtifacts(result) {
  return Array.isArray(result?.artifacts)
    ? result.artifacts.filter((item) => item && typeof item === 'object')
    : []
}
</script>

<style scoped>
.capability-results {
  display: grid;
  gap: 12px;
  margin-bottom: 16px;
}

.capability-result-card {
  display: grid;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-blank);
}

.capability-result-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.capability-result-card__title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}

.capability-result-card__meta,
.capability-result-card__endpoint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.capability-result-card__tags {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.capability-result-card__message,
.capability-result-card__text {
  margin: 0;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.capability-result-card__text {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  white-space: pre-wrap;
}

.capability-result-card__artifacts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 320px));
  gap: 12px;
}

.capability-result-card__image,
.capability-result-card__video {
  width: 100%;
  min-height: 180px;
  max-height: 320px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
}

.capability-result-card__video {
  object-fit: contain;
}

.capability-result-card__audio {
  width: min(100%, 420px);
}

@media (max-width: 960px) {
  .capability-result-card__head {
    flex-direction: column;
  }

  .capability-result-card__tags {
    justify-content: flex-start;
  }
}
</style>
