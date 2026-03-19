<template>
  <div class="intro-page">
    <div class="intro-page__ambient intro-page__ambient--left" aria-hidden="true" />
    <div class="intro-page__ambient intro-page__ambient--right" aria-hidden="true" />
    <div class="intro-page__mesh" aria-hidden="true" />

    <header class="site-nav">
      <button type="button" class="site-brand" @click="scrollToSection('hero')">
        <span class="site-brand__mark">AI</span>
        <span class="site-brand__body">
          <span class="site-brand__name">AI 员工工厂</span>
          <span class="site-brand__meta">对话、生成、沉淀，进入同一项目</span>
        </span>
      </button>

      <nav class="site-nav__links" aria-label="官网导航">
        <button
          v-for="item in navItems"
          :key="item.id"
          type="button"
          class="site-nav__anchor"
          @click="scrollToSection(item.id)"
        >
          {{ item.label }}
        </button>
      </nav>

      <div class="site-nav__actions">
        <el-button text class="site-nav__link" @click="router.push('/login')">
          登录
        </el-button>
        <el-button type="primary" class="site-nav__primary" @click="router.push('/register')">
          立即开始
        </el-button>
      </div>
    </header>

    <main class="site-main">
      <section id="hero" class="hero-section">
        <div class="hero-copy">
          <div class="hero-copy__eyebrow">AI Operating System</div>
          <h1 class="hero-copy__title">让 AI 真正进入生产。</h1>
          <p class="hero-copy__text">
            一个项目，串起对话、生成与沉淀。
          </p>

          <div class="hero-copy__actions">
            <el-button
              type="primary"
              size="large"
              class="site-nav__primary hero-copy__button"
              @click="router.push('/register')"
            >
              立即开始
            </el-button>
            <el-button
              size="large"
              class="hero-copy__secondary"
              @click="scrollToSection('workflow')"
            >
              查看流程
            </el-button>
          </div>

          <div class="hero-copy__signals" aria-label="核心能力">
            <span v-for="signal in heroSignals" :key="signal">{{ signal }}</span>
          </div>
        </div>

        <div class="hero-stage" data-reveal>
          <div class="hero-stage__shell">
            <div class="hero-stage__field" aria-hidden="true">
              <div class="hero-stage__halo" />
              <div class="hero-stage__lane" />

              <div class="hero-core">
                <div class="hero-core__ring hero-core__ring--outer" />
                <div class="hero-core__ring hero-core__ring--inner" />
                <div class="hero-core__pulse" />
                <div class="hero-core__body">
                  <div class="hero-core__eyebrow">Single Project</div>
                  <div class="hero-core__title">项目中枢</div>
                  <p class="hero-core__text">AI 在同一上下文持续工作</p>
                </div>
              </div>

              <div class="hero-stage__nodes">
                <article
                  v-for="(node, index) in heroNodes"
                  :key="node.label"
                  class="hero-node"
                  :class="`hero-node--${node.tone}`"
                  data-reveal
                  :style="{
                    '--node-x': node.x,
                    '--node-y': node.y,
                    '--node-float-delay': node.floatDelay,
                    '--reveal-delay': `${120 + index * 100}ms`,
                  }"
                >
                  <div class="hero-node__label">{{ node.label }}</div>
                  <h2 class="hero-node__title">{{ node.title }}</h2>
                </article>
              </div>

              <div class="hero-stage__footer">
                <span>对话</span>
                <span>图像</span>
                <span>视频</span>
                <span>资产</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="principles" class="content-section" data-reveal>
        <div class="section-heading section-heading--center">
          <div class="section-heading__eyebrow">Principles</div>
          <h2 class="section-heading__title">更短的路径，而不是更多页面。</h2>
          <p class="section-heading__text">
            以项目为中心组织生产，减少切换，保留连续性。
          </p>
        </div>

        <div class="principle-grid">
          <article
            v-for="(item, index) in principles"
            :key="item.label"
            class="principle-card"
            data-reveal
            :style="{ '--reveal-delay': `${index * 90}ms` }"
          >
            <div class="principle-card__label">{{ item.label }}</div>
            <h3 class="principle-card__title">{{ item.title }}</h3>
            <p class="principle-card__text">{{ item.text }}</p>
          </article>
        </div>
      </section>

      <section id="workflow" class="content-section workflow-section" data-reveal>
        <div class="section-heading section-heading--center">
          <div class="section-heading__eyebrow">Workflow</div>
          <h2 class="section-heading__title">四步进入生产。</h2>
          <p class="section-heading__text">
            路径固定，节奏清晰，结果可继续复用。
          </p>
        </div>

        <div class="workflow-panel">
          <div class="workflow-panel__line" aria-hidden="true" />
          <article
            v-for="(item, index) in workflowItems"
            :key="item.step"
            class="workflow-card"
            data-reveal
            :style="{ '--reveal-delay': `${index * 90}ms` }"
          >
            <div class="workflow-card__step">{{ item.step }}</div>
            <h3 class="workflow-card__title">{{ item.title }}</h3>
            <p class="workflow-card__text">{{ item.text }}</p>
          </article>
        </div>
      </section>

      <section class="cta-section" data-reveal>
        <div class="section-heading section-heading--center">
          <div class="section-heading__eyebrow">Start</div>
          <div class="cta-section__title">从一个项目开始。</div>
          <div class="cta-section__text">创建项目后，AI 员工即可进入生产流程。</div>
        </div>

        <div class="cta-section__actions">
          <el-button type="primary" class="site-nav__primary cta-section__button" @click="router.push('/register')">
            创建账号
          </el-button>
          <el-button class="hero-copy__secondary cta-section__button" @click="router.push('/login')">
            已有账号，去登录
          </el-button>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
let sectionObserver

const navItems = [
  { id: 'principles', label: '能力' },
  { id: 'workflow', label: '流程' },
]

const heroSignals = [
  '项目上下文',
  '统一生成',
  '资产复用',
]

const heroNodes = [
  {
    label: '输入',
    title: '需求进入项目',
    tone: 'soft',
    x: '15%',
    y: '59%',
    floatDelay: '-0.6s',
  },
  {
    label: '生成',
    title: '图像与视频输出',
    tone: 'bright',
    x: '76%',
    y: '27%',
    floatDelay: '-2.1s',
  },
  {
    label: '沉淀',
    title: '结果回到资产',
    tone: 'warm',
    x: '77%',
    y: '73%',
    floatDelay: '-3.4s',
  },
]

const principles = [
  {
    label: '同一项目',
    title: '不切上下文。',
    text: '需求、历史、规则都围绕同一项目继续推进。',
  },
  {
    label: '多模态',
    title: '同步生成。',
    text: '文字、图片、分镜、视频沿同一路径协作输出。',
  },
  {
    label: '可复用',
    title: '结果沉淀。',
    text: '生成结果进入项目资产，后续制作无需重来。',
  },
]

const workflowItems = [
  {
    step: '01',
    title: '创建项目',
    text: '建立上下文。',
  },
  {
    step: '02',
    title: '发起对话',
    text: '明确目标。',
  },
  {
    step: '03',
    title: '生成结果',
    text: '同步推进。',
  },
  {
    step: '04',
    title: '继续制作',
    text: '资产复用。',
  },
]

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

onMounted(() => {
  document.title = 'AI 员工工厂 | 官网首页'

  const sections = document.querySelectorAll('[data-reveal]')
  if (!sections.length) {
    return
  }

  sectionObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) {
          return
        }
        entry.target.classList.add('is-visible')
        sectionObserver?.unobserve(entry.target)
      })
    },
    {
      threshold: 0.16,
      rootMargin: '0px 0px -8% 0px',
    },
  )

  sections.forEach((section) => sectionObserver?.observe(section))
})

onBeforeUnmount(() => {
  sectionObserver?.disconnect()
  sectionObserver = null
})
</script>

<style scoped>
.intro-page {
  --page-bg:
    radial-gradient(circle at 18% 0%, rgba(125, 211, 252, 0.16), transparent 26%),
    radial-gradient(circle at 82% 14%, rgba(103, 232, 249, 0.12), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%);
  --page-text: #0f172a;
  --page-text-muted: #475569;
  --page-text-soft: #7c8aa0;
  --page-border: rgba(15, 23, 42, 0.08);
  --page-border-strong: rgba(15, 23, 42, 0.12);
  --page-surface: rgba(255, 255, 255, 0.72);
  --page-surface-strong: rgba(255, 255, 255, 0.84);
  --page-shadow: 0 24px 64px rgba(15, 23, 42, 0.08);
  --page-shadow-soft: 0 14px 34px rgba(15, 23, 42, 0.06);
  --page-accent: #0f172a;
  --page-accent-soft: #38bdf8;
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

.intro-page__ambient,
.intro-page__mesh {
  position: absolute;
  pointer-events: none;
}

.intro-page__ambient {
  width: 32rem;
  height: 32rem;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.74;
  animation: glowPulse 14s ease-in-out infinite;
}

.intro-page__ambient--left {
  top: -11rem;
  left: -14rem;
  background: rgba(125, 211, 252, 0.36);
}

.intro-page__ambient--right {
  top: 3rem;
  right: -12rem;
  background: rgba(103, 232, 249, 0.24);
  animation-delay: -5s;
}

.intro-page__mesh {
  inset: 0;
  opacity: 0.34;
  background:
    linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
  background-size: 88px 88px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.72), transparent 78%);
}

.site-nav,
.site-main {
  position: relative;
  z-index: 1;
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto;
}

.site-nav {
  position: sticky;
  top: 12px;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 18px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: var(--page-radius-pill);
  background: rgba(248, 250, 252, 0.58);
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(18px);
}

.site-brand {
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

.site-brand__mark {
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

.site-brand__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.site-brand__name,
.hero-copy__title,
.hero-node__title,
.hero-core__title,
.section-heading__title,
.principle-card__title,
.workflow-card__title,
.cta-section__title {
  font-family: 'Avenir Next', 'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.site-brand__name {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.1;
}

.site-brand__meta {
  margin-top: 2px;
  color: var(--page-text-muted);
  font-size: 11px;
  line-height: 1.3;
}

.site-nav__links,
.site-nav__actions {
  display: flex;
  align-items: center;
}

.site-nav__links {
  gap: 8px;
  padding: 6px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: var(--page-radius-pill);
  background: rgba(255, 255, 255, 0.46);
  backdrop-filter: blur(14px);
}

.site-nav__anchor {
  min-height: 34px;
  padding: 0 14px;
  border: 0;
  border-radius: var(--page-radius-pill);
  background: transparent;
  color: var(--page-text-muted);
  font-size: 13px;
  transition:
    color var(--page-transition),
    background-color var(--page-transition);
  cursor: pointer;
}

.site-nav__anchor:hover {
  background: rgba(255, 255, 255, 0.78);
  color: var(--page-text);
}

.site-nav__actions {
  gap: 10px;
}

.site-nav__link,
.hero-copy__secondary {
  color: var(--page-text);
}

.site-nav__primary {
  --el-button-bg-color: #0f172a;
  --el-button-border-color: #0f172a;
  --el-button-hover-bg-color: #1e293b;
  --el-button-hover-border-color: #1e293b;
  --el-button-active-bg-color: #020617;
  --el-button-active-border-color: #020617;
  position: relative;
  overflow: hidden;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.16);
}

.site-nav__primary::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 20%, rgba(255, 255, 255, 0.26) 50%, transparent 80%);
  transform: translateX(-130%);
  animation: buttonSweep 5.2s ease-in-out infinite;
}

.site-main {
  padding: 28px 0 56px;
}

.hero-section {
  display: grid;
  gap: 28px;
  justify-items: center;
  padding-top: 28px;
}

.hero-copy {
  width: 100%;
  max-width: 1080px;
  text-align: center;
  animation: fadeUp 0.8s cubic-bezier(0.2, 0.8, 0.2, 1) both;
}

.hero-copy__eyebrow,
.section-heading__eyebrow,
.principle-card__label,
.hero-node__label,
.hero-core__eyebrow {
  color: var(--page-text-soft);
  font-size: 12px;
  line-height: 1;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.hero-copy__title {
  max-width: 10.5em;
  margin: 18px auto 0;
  font-size: clamp(56px, 7.2vw, 98px);
  line-height: 0.92;
  letter-spacing: -0.07em;
  text-wrap: balance;
}

.hero-copy__text,
.section-heading__text,
.principle-card__text,
.workflow-card__text,
.cta-section__text,
.hero-core__text {
  color: var(--page-text-muted);
  font-size: 16px;
  line-height: 1.85;
}

.hero-copy__text {
  max-width: 700px;
  margin: 24px auto 0;
}

.hero-copy__actions,
.cta-section__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
  margin-top: 30px;
}

.hero-copy__button,
.cta-section__button {
  min-width: 138px;
}

.hero-copy__secondary {
  border-color: rgba(255, 255, 255, 0.86);
  background: rgba(255, 255, 255, 0.58);
  backdrop-filter: blur(14px);
}

.hero-copy__signals {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  width: min(100%, 860px);
  margin: 30px auto 0;
  color: var(--page-text-soft);
  font-size: 13px;
}

.hero-copy__signals span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 48px;
  padding: 0 18px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.54);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(14px);
}

.hero-copy__signals span::before {
  content: '';
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(56, 189, 248, 0.72);
  box-shadow: 0 0 16px rgba(56, 189, 248, 0.42);
}

.hero-stage {
  width: min(100%, 1040px);
}

.hero-stage__shell,
.principle-card,
.workflow-panel,
.cta-section {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: var(--page-surface);
  box-shadow: var(--page-shadow-soft);
  backdrop-filter: blur(20px);
}

.hero-stage__shell {
  padding: 24px;
}

.hero-stage__shell::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 50% 18%, rgba(255, 255, 255, 0.86), transparent 34%),
    linear-gradient(180deg, rgba(125, 211, 252, 0.08), transparent 46%);
  pointer-events: none;
}

.hero-stage__shell::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 18%, rgba(255, 255, 255, 0.34) 50%, transparent 82%);
  transform: translateX(-140%);
  animation: stageSweep 6.8s ease-in-out infinite;
  pointer-events: none;
}

.hero-stage__field {
  position: relative;
  min-height: 520px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 28px;
  background:
    linear-gradient(180deg, rgba(252, 254, 255, 0.88), rgba(239, 245, 251, 0.92)),
    rgba(255, 255, 255, 0.48);
  overflow: hidden;
}

.hero-stage__field::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(rgba(15, 23, 42, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.035) 1px, transparent 1px);
  background-size: 84px 84px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.5), transparent 86%);
  opacity: 0.42;
}

.hero-stage__field::after {
  content: '';
  position: absolute;
  inset: 14% 12%;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(125, 211, 252, 0.14), transparent 62%);
  filter: blur(18px);
}

.hero-stage__halo,
.hero-stage__lane,
.hero-core,
.hero-core__ring,
.hero-core__pulse,
.hero-node {
  position: absolute;
}

.hero-stage__halo {
  inset: 50% auto auto 50%;
  width: 520px;
  height: 260px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(125, 211, 252, 0.16), transparent 68%);
  transform: translate(-50%, -50%);
  filter: blur(22px);
}

.hero-stage__lane {
  top: 50%;
  left: 10%;
  right: 10%;
  height: 2px;
  border-radius: 999px;
  background: linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.8), transparent);
  box-shadow:
    0 0 26px rgba(56, 189, 248, 0.24),
    0 0 48px rgba(103, 232, 249, 0.12);
  overflow: hidden;
}

.hero-stage__lane::before,
.hero-stage__lane::after {
  content: '';
  position: absolute;
  inset: -10px auto -10px -12%;
  width: 26%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.72), transparent);
  filter: blur(6px);
  animation: dataFlow 5.4s ease-in-out infinite;
}

.hero-stage__lane::after {
  width: 16%;
  inset: -8px auto -8px 24%;
  animation-delay: -2.4s;
}

.hero-core {
  top: 50%;
  left: 50%;
  width: 236px;
  height: 236px;
  transform: translate(-50%, -50%);
}

.hero-core__ring,
.hero-core__pulse {
  inset: 50% auto auto 50%;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

.hero-core__ring--outer {
  width: 236px;
  height: 236px;
  border: 1px solid rgba(56, 189, 248, 0.22);
  animation: rotateSlow 20s linear infinite;
}

.hero-core__ring--inner {
  width: 176px;
  height: 176px;
  border: 1px solid rgba(56, 189, 248, 0.34);
  animation: rotateSlow 11s linear infinite reverse;
}

.hero-core__pulse {
  width: 120px;
  height: 120px;
  background: radial-gradient(circle at center, rgba(125, 211, 252, 0.28), transparent 68%);
  animation: pulseGlow 3.2s ease-in-out infinite;
}

.hero-core__body {
  position: absolute;
  inset: 50% auto auto 50%;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  width: 160px;
  height: 160px;
  padding: 20px;
  border: 1px solid rgba(255, 255, 255, 0.92);
  border-radius: 34px;
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 18px 40px rgba(56, 189, 248, 0.12);
  text-align: center;
  transform: translate(-50%, -50%);
}

.hero-core__title {
  position: relative;
  margin-top: 10px;
  font-size: 30px;
  line-height: 1;
  letter-spacing: -0.06em;
}

.hero-core__text {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.7;
}

.hero-stage__nodes {
  position: absolute;
  inset: 0;
}

.hero-node {
  left: var(--node-x);
  top: var(--node-y);
  min-width: 188px;
  padding: 18px 18px 16px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(18px);
  transform: translate(-50%, -50%);
  transition:
    transform var(--page-transition),
    border-color var(--page-transition),
    box-shadow var(--page-transition);
  animation: nodeFloat 7s ease-in-out infinite;
  animation-delay: var(--node-float-delay);
}

.hero-node:hover,
.principle-card:hover,
.workflow-card:hover {
  transform: translate(-50%, calc(-50% - 6px));
  border-color: rgba(125, 211, 252, 0.26);
  box-shadow: 0 20px 42px rgba(15, 23, 42, 0.08);
}

.hero-node--soft {
  border-color: rgba(255, 255, 255, 0.9);
}

.hero-node--bright {
  border-color: rgba(56, 189, 248, 0.26);
  background: rgba(239, 249, 255, 0.78);
}

.hero-node--warm {
  border-color: rgba(251, 191, 36, 0.24);
  background: rgba(255, 252, 244, 0.78);
}

.hero-node__title {
  margin: 12px 0 0;
  font-size: 24px;
  line-height: 1.14;
  letter-spacing: -0.05em;
}

.hero-stage__footer {
  position: absolute;
  left: 50%;
  bottom: 26px;
  z-index: 1;
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  transform: translateX(-50%);
}

.hero-stage__footer span {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: var(--page-radius-pill);
  background: rgba(255, 255, 255, 0.56);
  color: #475569;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

[data-reveal] {
  opacity: 0;
  transform: translate3d(0, 28px, 0);
  transition:
    opacity 720ms cubic-bezier(0.2, 0.8, 0.2, 1),
    transform 720ms cubic-bezier(0.2, 0.8, 0.2, 1);
  transition-delay: var(--reveal-delay, 0ms);
}

[data-reveal].is-visible {
  opacity: 1;
  transform: translate3d(0, 0, 0);
}

.content-section {
  margin-top: 92px;
}

.section-heading {
  max-width: 760px;
}

.section-heading--center {
  margin: 0 auto;
  text-align: center;
}

.section-heading__title,
.cta-section__title {
  margin: 18px 0 0;
  font-size: clamp(34px, 4.6vw, 60px);
  line-height: 1.02;
  letter-spacing: -0.06em;
  text-wrap: balance;
}

.section-heading__text,
.cta-section__text {
  max-width: 520px;
  margin: 18px auto 0;
}

.principle-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 32px;
}

.principle-card {
  min-height: 220px;
  padding: 24px;
  transition:
    transform var(--page-transition),
    border-color var(--page-transition),
    box-shadow var(--page-transition);
}

.principle-card__title {
  margin: 16px 0 0;
  font-size: 28px;
  line-height: 1.08;
  letter-spacing: -0.05em;
}

.principle-card__text {
  margin: 16px 0 0;
}

.workflow-section {
  position: relative;
}

.workflow-panel {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 32px;
  padding: 24px;
}

.workflow-panel__line {
  position: absolute;
  top: 72px;
  left: 10%;
  right: 10%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(15, 23, 42, 0.12), transparent);
  pointer-events: none;
}

.workflow-card {
  position: relative;
  min-height: 192px;
  padding: 22px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.72);
  transition:
    transform var(--page-transition),
    border-color var(--page-transition),
    box-shadow var(--page-transition);
}

.workflow-card__step {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: var(--page-radius-pill);
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
}

.workflow-card__title {
  margin: 22px 0 0;
  font-size: 28px;
  line-height: 1.08;
  letter-spacing: -0.05em;
}

.workflow-card__text {
  margin: 12px 0 0;
}

.cta-section {
  margin-top: 96px;
  padding: 34px 26px;
  text-align: center;
}

@media (max-width: 1180px) {
  .site-nav {
    flex-wrap: wrap;
    border-radius: 30px;
  }

  .principle-grid,
  .workflow-panel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workflow-panel__line {
    display: none;
  }
}

@media (max-width: 860px) {
  .site-nav,
  .site-main {
    width: min(100%, calc(100% - 28px));
  }

  .site-nav__links {
    order: 3;
    width: 100%;
    justify-content: center;
  }

  .hero-copy__title,
  .section-heading__title,
  .cta-section__title {
    max-width: none;
  }

  .hero-copy__signals {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: min(100%, 620px);
  }

  .hero-stage__field {
    min-height: auto;
    padding: 28px 16px 20px;
  }

  .principle-grid,
  .workflow-panel {
    grid-template-columns: 1fr;
  }

  .hero-stage__halo,
  .hero-stage__lane {
    display: none;
  }

  .hero-core {
    position: relative;
    top: auto;
    left: auto;
    transform: none;
    margin: 0 auto;
  }

  .hero-stage__nodes {
    position: relative;
    inset: auto;
    display: grid;
    gap: 12px;
    margin-top: 24px;
  }

  .hero-node {
    position: relative;
    left: auto;
    top: auto;
    transform: none;
    min-width: 0;
    animation: none;
  }

  .hero-node:hover {
    transform: translate3d(0, -4px, 0);
  }

  .hero-stage__footer {
    position: relative;
    left: auto;
    bottom: auto;
    width: 100%;
    margin-top: 18px;
    transform: none;
  }

  .principle-card,
  .workflow-card {
    min-height: auto;
  }
}

@media (max-width: 640px) {
  .site-nav {
    gap: 14px;
    padding: 12px 14px;
  }

  .site-nav__actions {
    width: 100%;
    justify-content: flex-end;
  }

  .hero-section {
    gap: 24px;
    padding-top: 20px;
  }

  .hero-copy__title {
    font-size: clamp(42px, 16vw, 64px);
  }

  .hero-copy__text,
  .section-heading__text,
  .principle-card__text,
  .workflow-card__text,
  .cta-section__text,
  .hero-core__text {
    font-size: 15px;
    line-height: 1.8;
  }

  .hero-stage__shell,
  .principle-card,
  .workflow-panel,
  .workflow-card,
  .cta-section {
    padding: 20px;
  }

  .hero-stage__field {
    min-height: 540px;
  }

  .hero-copy__signals {
    grid-template-columns: 1fr;
    width: min(100%, 320px);
  }

  .hero-stage__halo {
    width: 360px;
    height: 200px;
  }

  .hero-stage__lane {
    left: 6%;
    right: 6%;
  }

  .hero-core {
    width: 200px;
    height: 200px;
  }

  .hero-core__ring--outer {
    width: 200px;
    height: 200px;
  }

  .hero-core__ring--inner {
    width: 150px;
    height: 150px;
  }

  .hero-core__body {
    width: 142px;
    height: 142px;
    border-radius: 28px;
  }

  .hero-core__title {
    font-size: 26px;
  }

  .hero-node {
    min-width: 164px;
    padding: 16px;
  }

  .hero-node__title,
  .principle-card__title,
  .workflow-card__title {
    font-size: 26px;
  }

  .hero-stage__footer {
    bottom: 20px;
    width: calc(100% - 40px);
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation: none !important;
    transition: none !important;
    scroll-behavior: auto !important;
  }
}

@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translate3d(0, 24px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

@keyframes glowPulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.54;
  }
  50% {
    transform: scale(1.06);
    opacity: 0.74;
  }
}

@keyframes rotateSlow {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulseGlow {
  0%,
  100% {
    transform: scale(0.92);
    opacity: 0.44;
  }
  50% {
    transform: scale(1.08);
    opacity: 0.76;
  }
}

@keyframes nodeFloat {
  0%,
  100% {
    transform: translate(-50%, -50%) translateY(0);
  }
  50% {
    transform: translate(-50%, -50%) translateY(-8px);
  }
}

@keyframes buttonSweep {
  0%,
  72%,
  100% {
    transform: translateX(-130%);
  }
  88% {
    transform: translateX(130%);
  }
}

@keyframes stageSweep {
  0%,
  78%,
  100% {
    transform: translateX(-140%);
  }
  90% {
    transform: translateX(140%);
  }
}

@keyframes dataFlow {
  0% {
    transform: translateX(-22%);
    opacity: 0;
  }
  18%,
  82% {
    opacity: 1;
  }
  100% {
    transform: translateX(460%);
    opacity: 0;
  }
}
</style>
