<template>
  <div class="auth-desktop">
    <div
      class="auth-desktop__wallpaper"
      :style="wallpaperStyle"
      aria-hidden="true"
    />
    <div class="auth-desktop__ambient auth-desktop__ambient--left" aria-hidden="true" />
    <div class="auth-desktop__ambient auth-desktop__ambient--right" aria-hidden="true" />
    <div class="auth-desktop__grid" aria-hidden="true" />

    <div class="auth-desktop__window">
      <section class="auth-desktop__hero">
        <div class="auth-desktop__brand">
          <div class="auth-desktop__brand-mark">AI</div>
          <div>
            <div class="auth-desktop__brand-name">{{ brandName }}</div>
            <div class="auth-desktop__brand-meta">{{ brandMeta }}</div>
          </div>
        </div>

        <div class="auth-desktop__hero-copy">
          <div class="auth-desktop__eyebrow">{{ eyebrow }}</div>
          <h1 class="auth-desktop__title">{{ title }}</h1>
          <p class="auth-desktop__text">{{ description }}</p>
        </div>

        <div class="auth-desktop__feature-list">
          <article
            v-for="item in features"
            :key="item.title"
            class="auth-desktop__feature"
          >
            <div class="auth-desktop__feature-name">{{ item.title }}</div>
            <div class="auth-desktop__feature-text">{{ item.text }}</div>
          </article>
        </div>

        <div class="auth-desktop__dock">
          <span
            v-for="item in dockItems"
            :key="item"
            class="auth-desktop__dock-item"
          >
            {{ item }}
          </span>
        </div>
      </section>

      <section class="auth-desktop__panel">
        <div class="auth-desktop__panel-bar">
          <span class="auth-desktop__traffic auth-desktop__traffic--close" />
          <span class="auth-desktop__traffic auth-desktop__traffic--min" />
          <span class="auth-desktop__traffic auth-desktop__traffic--max" />
          <div class="auth-desktop__panel-title">{{ panelTitle }}</div>
        </div>

        <div class="auth-desktop__panel-body">
          <slot />
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  DESKTOP_WALLPAPER_STORAGE_KEY,
  getDesktopWallpaperConfig,
  resolveDesktopWallpaperAppearance,
} from "@/utils/desktop-shell.js";

const props = defineProps({
  eyebrow: {
    type: String,
    default: "Desktop Access",
  },
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    required: true,
  },
  panelTitle: {
    type: String,
    required: true,
  },
  features: {
    type: Array,
    default: () => [],
  },
  dockItems: {
    type: Array,
    default: () => [],
  },
  brandName: {
    type: String,
    default: "AI 员工工厂",
  },
  brandMeta: {
    type: String,
    default: "桌面式协作系统",
  },
});

const wallpaperConfig = ref(getDesktopWallpaperConfig());

const wallpaperAppearance = computed(() =>
  resolveDesktopWallpaperAppearance(wallpaperConfig.value),
);

const wallpaperStyle = computed(() => ({
  background:
    String(wallpaperAppearance.value?.background || "").trim() || undefined,
}));

function syncWallpaperConfig() {
  wallpaperConfig.value = getDesktopWallpaperConfig();
}

function handleWallpaperStorage(event) {
  if (!event || event.key === DESKTOP_WALLPAPER_STORAGE_KEY) {
    syncWallpaperConfig();
  }
}

onMounted(() => {
  syncWallpaperConfig();
  window.addEventListener("storage", handleWallpaperStorage);
});

onBeforeUnmount(() => {
  window.removeEventListener("storage", handleWallpaperStorage);
});
</script>

<style scoped>
.auth-desktop {
  position: relative;
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: clamp(12px, 2vw, 24px);
  overflow: clip;
  background:
    radial-gradient(circle at 12% 0%, rgba(125, 211, 252, 0.2), transparent 24%),
    radial-gradient(circle at 88% 10%, rgba(103, 232, 249, 0.18), transparent 22%),
    linear-gradient(180deg, #f2efe6 0%, #f6f8fb 42%, #e9eef5 100%);
}

.auth-desktop__wallpaper {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 12% 0%, rgba(125, 211, 252, 0.2), transparent 24%),
    radial-gradient(circle at 88% 10%, rgba(103, 232, 249, 0.18), transparent 22%),
    linear-gradient(180deg, #f2efe6 0%, #f6f8fb 42%, #e9eef5 100%);
  background-size: cover;
  background-position: center;
  pointer-events: none;
}

.auth-desktop__ambient {
  position: absolute;
  border-radius: 999px;
  filter: blur(72px);
  opacity: 0.72;
  pointer-events: none;
}

.auth-desktop__ambient--left {
  width: 24rem;
  height: 24rem;
  top: -8rem;
  left: -10rem;
  background: rgba(125, 211, 252, 0.34);
}

.auth-desktop__ambient--right {
  width: 20rem;
  height: 20rem;
  right: -6rem;
  top: 8rem;
  background: rgba(103, 232, 249, 0.22);
}

.auth-desktop__grid {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(rgba(15, 23, 42, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
  background-size: 56px 56px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.58), transparent 84%);
  pointer-events: none;
}

.auth-desktop__window {
  position: relative;
  z-index: 1;
  width: min(1180px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(320px, 420px);
  gap: 16px;
  align-items: stretch;
}

.auth-desktop__hero,
.auth-desktop__panel {
  min-width: 0;
  border: 1px solid rgba(255, 255, 255, 0.86);
  background: rgba(255, 255, 255, 0.72);
  box-shadow:
    0 28px 74px rgba(15, 23, 42, 0.08),
    0 6px 18px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(18px);
}

.auth-desktop__hero {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: clamp(560px, 72vh, 640px);
  padding: clamp(20px, 2.4vw, 30px);
  border-radius: 34px;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.96), transparent 34%),
    radial-gradient(circle at 80% 18%, rgba(125, 211, 252, 0.16), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(241, 246, 251, 0.84));
}

.auth-desktop__brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.auth-desktop__brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #111827;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.auth-desktop__brand-name {
  font-size: 16px;
  line-height: 1.2;
  font-weight: 600;
  color: #111827;
  font-family: "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.auth-desktop__brand-meta {
  margin-top: 2px;
  color: #8b8d93;
  font-size: 11px;
}

.auth-desktop__hero-copy {
  width: min(100%, 560px);
  margin: 44px 0 24px;
}

.auth-desktop__eyebrow {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #526071;
}

.auth-desktop__title {
  margin: 14px 0 0;
  font-size: clamp(38px, 5vw, 58px);
  line-height: 0.98;
  letter-spacing: -0.04em;
  color: #111827;
}

.auth-desktop__text {
  margin: 18px 0 0;
  max-width: 38rem;
  font-size: 16px;
  line-height: 1.7;
  color: #526071;
}

.auth-desktop__feature-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.auth-desktop__feature {
  padding: 14px;
  border-radius: 20px;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(255, 255, 255, 0.72);
}

.auth-desktop__feature-name {
  font-size: 13px;
  font-weight: 700;
  color: #111827;
}

.auth-desktop__feature-text {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

.auth-desktop__dock {
  margin-top: 18px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.08);
  align-self: flex-start;
}

.auth-desktop__dock-item {
  min-width: 42px;
  height: 42px;
  padding: 0 14px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(226, 232, 240, 0.82));
  border: 1px solid rgba(148, 163, 184, 0.18);
  font-size: 11px;
  font-weight: 700;
  color: #334155;
}

.auth-desktop__panel {
  border-radius: 28px;
  overflow: hidden;
}

.auth-desktop__panel-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.8);
  background: rgba(255, 255, 255, 0.72);
}

.auth-desktop__traffic {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  display: inline-block;
}

.auth-desktop__traffic--close {
  background: #fb7185;
}

.auth-desktop__traffic--min {
  background: #fbbf24;
}

.auth-desktop__traffic--max {
  background: #4ade80;
}

.auth-desktop__panel-title {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #526071;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.auth-desktop__panel-body {
  padding: 22px;
}

@media (max-width: 960px) {
  .auth-desktop__window {
    grid-template-columns: 1fr;
  }

  .auth-desktop__hero {
    min-height: auto;
  }

  .auth-desktop__feature-list {
    grid-template-columns: 1fr;
  }
}
</style>
