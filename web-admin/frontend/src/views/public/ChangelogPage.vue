<template>
  <div class="updates-page" v-loading="loading">
    <div class="updates-page__ambient updates-page__ambient--left" aria-hidden="true" />
    <div class="updates-page__ambient updates-page__ambient--right" aria-hidden="true" />
    <div class="updates-page__mesh" aria-hidden="true" />

    <header class="updates-nav">
      <button type="button" class="updates-brand" @click="router.push('/intro')">
        <span class="updates-brand__mark">AI</span>
        <span class="updates-brand__body">
          <span class="updates-brand__name">AI 员工工厂</span>
          <span class="updates-brand__meta">产品变更记录</span>
        </span>
      </button>

      <nav class="updates-nav__links" aria-label="更新日志导航">
        <button type="button" class="updates-nav__anchor" @click="scrollToSection('latest')">
          最新发布
        </button>
        <button type="button" class="updates-nav__anchor" @click="scrollToSection('timeline')">
          时间线
        </button>
      </nav>

      <div class="updates-nav__actions">
        <el-button text class="updates-nav__link" @click="router.push('/intro')">返回首页</el-button>
        <el-button type="primary" class="updates-nav__primary" @click="handlePrimaryAction">
          {{ authenticated ? '进入工作台' : '立即开始' }}
        </el-button>
      </div>
    </header>

    <main class="updates-main">
      <section class="updates-hero">
        <div class="updates-hero__copy">
          <h1 class="updates-hero__title">更新日志</h1>
        </div>

        <div id="latest" class="updates-hero__surface">
          <template v-if="latestRelease">
            <div class="release-spotlight__title">{{ latestRelease.title }}</div>
            <div class="release-spotlight__meta">
              <span v-if="latestRelease.version">{{ latestRelease.version }}</span>
              <span>{{ latestRelease.date || '持续更新' }}</span>
            </div>

            <div class="release-spotlight__list" v-if="latestHighlights.length">
              <span v-for="(item, index) in latestHighlights" :key="`highlight-${index}`">
                {{ item }}
              </span>
            </div>
          </template>

          <template v-else>
            <div class="release-spotlight__title">暂无更新</div>
          </template>
        </div>
      </section>

      <section v-if="errorMessage" class="updates-status">
        <el-alert
          :title="errorMessage"
          type="warning"
          :closable="false"
          show-icon
        />
      </section>

      <section id="timeline" class="timeline-section">
        <template v-if="releaseSections.length">
          <article
            v-for="(section, index) in releaseSections"
            :key="section.id"
            class="timeline-card"
            :style="{ '--card-delay': `${index * 80}ms` }"
          >
            <div class="timeline-card__rail">
              <span class="timeline-card__index">{{ String(index + 1).padStart(2, '0') }}</span>
              <span class="timeline-card__line" aria-hidden="true" />
            </div>

            <div class="timeline-card__body">
              <div class="timeline-card__head">
                <div>
                  <h2 class="timeline-card__title">{{ section.title }}</h2>
                </div>
                <div class="timeline-card__meta">
                  <span v-if="section.version">{{ section.version }}</span>
                  <span>{{ section.date || '未填写日期' }}</span>
                </div>
              </div>

              <div class="timeline-card__blocks">
                <template v-for="(block, blockIndex) in section.blocks" :key="`${section.id}-${blockIndex}`">
                  <h3 v-if="block.type === 'subheading'" class="timeline-block__title">
                    {{ block.text }}
                  </h3>
                  <p v-else-if="block.type === 'paragraph'" class="timeline-block__text">
                    {{ block.text }}
                  </p>
                  <div v-else-if="block.type === 'note'" class="timeline-block__note">
                    {{ block.text }}
                  </div>
                  <ul v-else-if="block.type === 'list'" class="timeline-block__list">
                    <li v-for="(item, itemIndex) in block.items" :key="`${section.id}-${blockIndex}-${itemIndex}`">
                      {{ item }}
                    </li>
                  </ul>
                </template>
              </div>
            </div>
          </article>
        </template>

        <div v-else class="timeline-empty">
          <el-empty description="暂无记录" :image-size="72" />
        </div>
      </section>

    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '@/utils/api.js'
import { authStateVersion, hasStoredToken } from '@/utils/auth-storage.js'

const router = useRouter()

const loading = ref(false)
const errorMessage = ref('')
const entries = ref([])

const authenticated = computed(() => {
  authStateVersion.value
  return hasStoredToken()
})

const releaseSections = computed(() =>
  (Array.isArray(entries.value) ? entries.value : []).map((entry, index) =>
    normalizeRelease(entry, index),
  ),
)

const latestRelease = computed(() => releaseSections.value[0] || null)

const latestHighlights = computed(() => extractHighlights(latestRelease.value, 2))

function normalizeDateLabel(value) {
  const raw = String(value || '').trim()
  if (!raw) {
    return ''
  }
  const normalized = raw.replace(/[/.]/g, '-')
  const date = new Date(`${normalized}T00:00:00`)
  if (Number.isNaN(date.getTime())) {
    return raw
  }
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function appendContentBlocks(blocks, value) {
  const source = String(value || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
  if (!source) {
    return
  }
  let paragraphBuffer = []
  let listBuffer = []

  const flushParagraph = () => {
    if (!paragraphBuffer.length) {
      return
    }
    blocks.push({
      type: 'paragraph',
      text: paragraphBuffer.join(' '),
    })
    paragraphBuffer = []
  }

  const flushList = () => {
    if (!listBuffer.length) {
      return
    }
    blocks.push({
      type: 'list',
      items: [...listBuffer],
    })
    listBuffer = []
  }

  for (const rawLine of source.split('\n')) {
    const line = rawLine.trim()
    if (!line) {
      flushParagraph()
      flushList()
      continue
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/)
    if (headingMatch) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'subheading', text: headingMatch[2].trim() })
      continue
    }

    const listMatch = line.match(/^[-*]\s+(.+)$/)
    if (listMatch) {
      flushParagraph()
      listBuffer.push(listMatch[1].trim())
      continue
    }

    const noteMatch = line.match(/^>\s+(.+)$/)
    if (noteMatch) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'note', text: noteMatch[1].trim() })
      continue
    }

    paragraphBuffer.push(line)
  }

  flushParagraph()
  flushList()
}

function resolveTitle(entry) {
  const title = String(entry?.title || '').trim()
  if (title) {
    return title
  }
  const version = String(entry?.version || '').trim()
  if (version) {
    return version
  }
  return '未命名更新'
}

function normalizeRelease(entry, index) {
  const blocks = []
  const summary = String(entry?.summary || '').trim()
  if (summary) {
    blocks.push({ type: 'paragraph', text: summary })
  }
  appendContentBlocks(blocks, entry?.content)
  return {
    id: String(entry?.id || `release-${index + 1}`),
    title: resolveTitle(entry),
    version: String(entry?.version || '').trim(),
    date: normalizeDateLabel(entry?.release_date),
    blocks,
  }
}

function extractHighlights(section, limit = 3) {
  if (!section?.blocks?.length) {
    return []
  }
  const items = []
  for (const block of section.blocks) {
    if (block.type === 'list') {
      items.push(...block.items)
    } else if (block.type === 'paragraph' || block.type === 'note') {
      items.push(block.text)
    }
    if (items.length >= limit) {
      break
    }
  }
  return items.slice(0, limit)
}

function scrollToSection(id) {
  const element = document.getElementById(id)
  if (!element) {
    return
  }
  element.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

function handlePrimaryAction() {
  router.push(authenticated.value ? '/ai/chat' : '/register')
}

async function fetchPublicChangelog() {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await api.get('/changelog-entries/public')
    entries.value = Array.isArray(data?.items) ? data.items : []
  } catch (err) {
    entries.value = []
    errorMessage.value = err?.detail || err?.message || '加载更新日志失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  document.title = 'AI 员工工厂 | 更新日志'
  fetchPublicChangelog()
})
</script>

<style scoped>
.updates-page {
  --page-bg:
    radial-gradient(circle at 16% 2%, rgba(125, 211, 252, 0.18), transparent 24%),
    radial-gradient(circle at 88% 12%, rgba(249, 168, 212, 0.14), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 42%, #edf2f7 100%);
  --page-text: #0f172a;
  --page-text-muted: #526173;
  --page-text-soft: #8291a4;
  --page-border: rgba(15, 23, 42, 0.08);
  --page-surface: rgba(255, 255, 255, 0.74);
  --page-surface-strong: rgba(255, 255, 255, 0.86);
  --page-shadow: 0 24px 64px rgba(15, 23, 42, 0.08);
  --page-shadow-soft: 0 14px 34px rgba(15, 23, 42, 0.06);
  --page-radius-xl: 34px;
  --page-radius-lg: 24px;
  --page-radius-md: 18px;
  --page-radius-pill: 999px;
  --page-transition: 260ms ease;
  position: relative;
  min-height: 100dvh;
  overflow: clip;
  color: var(--page-text);
  background: var(--page-bg);
}

.updates-page__ambient,
.updates-page__mesh {
  position: absolute;
  pointer-events: none;
}

.updates-page__ambient {
  width: 28rem;
  height: 28rem;
  border-radius: 50%;
  filter: blur(72px);
  opacity: 0.76;
}

.updates-page__ambient--left {
  top: -10rem;
  left: -12rem;
  background: rgba(125, 211, 252, 0.34);
}

.updates-page__ambient--right {
  top: 5rem;
  right: -10rem;
  background: rgba(251, 191, 36, 0.16);
}

.updates-page__mesh {
  inset: 0;
  opacity: 0.34;
  background:
    linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
  background-size: 88px 88px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.78), transparent 84%);
}

.updates-nav,
.updates-main {
  position: relative;
  z-index: 1;
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto;
}

.updates-nav {
  position: sticky;
  top: 12px;
  z-index: 8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 18px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: var(--page-radius-pill);
  background: rgba(248, 250, 252, 0.6);
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(18px);
}

.updates-brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.updates-brand__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  background: #0f172a;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
}

.updates-brand__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.updates-brand__name,
.updates-hero__title,
.release-spotlight__title,
.timeline-card__title,
.updates-cta__title {
  font-family: 'Avenir Next', 'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.updates-brand__name {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.1;
}

.updates-brand__meta {
  margin-top: 2px;
  color: var(--page-text-muted);
  font-size: 11px;
  line-height: 1.3;
}

.updates-nav__links,
.updates-nav__actions {
  display: flex;
  align-items: center;
}

.updates-nav__links {
  gap: 8px;
  padding: 6px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: var(--page-radius-pill);
  background: rgba(255, 255, 255, 0.48);
  backdrop-filter: blur(14px);
}

.updates-nav__anchor {
  min-height: 34px;
  padding: 0 14px;
  border: 0;
  border-radius: var(--page-radius-pill);
  background: transparent;
  color: var(--page-text-muted);
  font-size: 13px;
  cursor: pointer;
  transition:
    color var(--page-transition),
    background-color var(--page-transition);
}

.updates-nav__anchor:hover {
  background: rgba(255, 255, 255, 0.82);
  color: var(--page-text);
}

.updates-nav__actions {
  gap: 10px;
}

.updates-nav__link {
  color: var(--page-text);
}

.updates-nav__primary {
  --el-button-bg-color: #0f172a;
  --el-button-border-color: #0f172a;
  --el-button-hover-bg-color: #1e293b;
  --el-button-hover-border-color: #1e293b;
  --el-button-active-bg-color: #020617;
  --el-button-active-border-color: #020617;
  box-shadow: var(--page-shadow-soft);
}

.updates-main {
  padding: 28px 0 56px;
}

.updates-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 420px);
  gap: 24px;
  align-items: stretch;
  padding-top: 28px;
}

.updates-hero__copy,
.updates-hero__surface,
.timeline-card,
.updates-status,
.timeline-empty {
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: var(--page-surface);
  box-shadow: var(--page-shadow-soft);
  backdrop-filter: blur(20px);
}

.updates-hero__copy,
.updates-hero__surface {
  position: relative;
  overflow: hidden;
}

.updates-hero__copy,
.updates-hero__surface {
  padding: 30px;
}

.updates-hero__copy::before,
.updates-hero__surface::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.72), transparent 32%),
    linear-gradient(180deg, rgba(125, 211, 252, 0.08), transparent 48%);
}

.updates-hero__eyebrow,
.release-spotlight__eyebrow,
.timeline-card__eyebrow {
  color: var(--page-text-soft);
  font-size: 12px;
  line-height: 1;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.updates-hero__title {
  max-width: 10em;
  margin: 18px 0 0;
  font-size: clamp(48px, 6vw, 82px);
  line-height: 0.95;
  letter-spacing: -0.07em;
  text-wrap: balance;
}

.updates-hero__text,
.release-spotlight__summary,
.timeline-block__text,
.updates-cta__text {
  color: var(--page-text-muted);
  font-size: 16px;
  line-height: 1.8;
}

.updates-hero__text {
  max-width: 340px;
  margin: 20px 0 0;
}

.release-spotlight__title {
  margin-top: 18px;
  font-size: clamp(28px, 4vw, 42px);
  line-height: 1.04;
  letter-spacing: -0.04em;
}

.release-spotlight__meta,
.timeline-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
  color: var(--page-text-soft);
  font-size: 13px;
}

.release-spotlight__meta span,
.timeline-card__meta span,
.release-spotlight__list span {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 14px;
  border-radius: var(--page-radius-pill);
  background: rgba(255, 255, 255, 0.62);
  border: 1px solid rgba(255, 255, 255, 0.84);
}

.release-spotlight__summary {
  margin: 18px 0 0;
}

.release-spotlight__list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 24px;
}

.updates-status {
  margin-top: 24px;
  padding: 18px;
}

.timeline-section {
  display: grid;
  gap: 18px;
  margin-top: 24px;
}

.timeline-card {
  display: grid;
  grid-template-columns: 86px minmax(0, 1fr);
  gap: 0;
  padding: 0;
  overflow: hidden;
  animation: cardFadeUp 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: var(--card-delay);
}

.timeline-card__rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 30px 0 24px;
  background: rgba(255, 255, 255, 0.34);
}

.timeline-card__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  border-radius: 16px;
  background: #0f172a;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.timeline-card__line {
  flex: 1;
  width: 1px;
  margin-top: 14px;
  background: linear-gradient(180deg, rgba(56, 189, 248, 0.44), rgba(15, 23, 42, 0.08));
}

.timeline-card__body {
  padding: 28px 30px 30px;
}

.timeline-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.timeline-card__title {
  margin: 14px 0 0;
  font-size: clamp(24px, 3.2vw, 34px);
  line-height: 1.08;
  letter-spacing: -0.04em;
}

.timeline-card__blocks {
  margin-top: 20px;
}

.timeline-card__blocks > * + * {
  margin-top: 14px;
}

.timeline-block__title {
  margin: 6px 0 0;
  font-size: 17px;
  line-height: 1.3;
}

.timeline-block__text {
  margin: 0;
}

.timeline-block__note {
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  padding: 0 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.05);
  color: var(--page-text-muted);
  font-size: 14px;
}

.timeline-block__list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.timeline-block__list li {
  position: relative;
  padding: 14px 16px 14px 42px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(255, 255, 255, 0.84);
  color: var(--page-text);
  line-height: 1.7;
}

.timeline-block__list li::before {
  content: '';
  position: absolute;
  top: 22px;
  left: 18px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #38bdf8;
  box-shadow: 0 0 0 6px rgba(56, 189, 248, 0.12);
}

.timeline-empty {
  padding: 36px;
}

@keyframes cardFadeUp {
  from {
    opacity: 0;
    transform: translate3d(0, 20px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

@media (max-width: 980px) {
  .updates-nav {
    flex-wrap: wrap;
  }

  .updates-hero {
    grid-template-columns: 1fr;
  }

}

@media (max-width: 720px) {
  .updates-nav,
  .updates-main {
    width: min(1180px, calc(100% - 24px));
  }

  .updates-nav {
    gap: 12px;
    padding: 12px;
    border-radius: 26px;
  }

  .updates-nav__links,
  .updates-nav__actions {
    width: 100%;
    justify-content: space-between;
  }

  .updates-nav__links {
    order: 3;
  }

  .updates-hero__copy,
  .updates-hero__surface,
  .timeline-card__body,
  .timeline-empty {
    padding: 22px;
  }

  .timeline-card {
    grid-template-columns: 1fr;
  }

  .timeline-card__rail {
    flex-direction: row;
    justify-content: flex-start;
    gap: 14px;
    padding: 20px 22px 0;
    background: transparent;
  }

  .timeline-card__line {
    height: 1px;
    width: auto;
    margin-top: 0;
  }

  .timeline-card__head {
    flex-direction: column;
  }
}
</style>
