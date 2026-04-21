<template>
  <div class="desktop-wallpaper-page">
    <section class="wallpaper-hero">
      <div class="wallpaper-hero__content">
        <div class="wallpaper-hero__eyebrow">Desktop Wallpaper</div>
        <h1>桌面背景</h1>
        <p>
          这里可以切换系统预设，也可以上传一张本地图片作为桌面背景。应用后会立即同步到底层桌面壳。
        </p>
      </div>
      <div class="wallpaper-hero__actions">
        <el-button @click="resetToPreset">恢复预设</el-button>
        <el-button type="primary" @click="applyConfig">应用当前背景</el-button>
      </div>
    </section>

    <section class="wallpaper-layout">
      <article class="wallpaper-panel wallpaper-panel--preview">
        <div class="wallpaper-panel__head">
          <div>
            <div class="wallpaper-panel__eyebrow">Live Preview</div>
            <h2>桌面预览</h2>
          </div>
          <span class="wallpaper-mode-badge">
            {{ draftConfig.mode === "custom" ? "自定义图片" : "系统预设" }}
          </span>
        </div>

        <div class="wallpaper-preview-shell">
          <div class="wallpaper-preview" :style="previewStyle">
            <div class="wallpaper-preview__ambient wallpaper-preview__ambient--left" :style="{ background: previewAppearance.ambientLeft }" />
            <div class="wallpaper-preview__ambient wallpaper-preview__ambient--right" :style="{ background: previewAppearance.ambientRight }" />
            <div class="wallpaper-preview__dock">
              <span>AI</span>
              <span>WB</span>
              <span>PR</span>
              <span>MT</span>
            </div>
          </div>
        </div>

        <div class="wallpaper-preview-meta">
          <span>当前预览：{{ previewAppearance.label }}</span>
          <span v-if="draftConfig.updatedAt">最近修改：{{ formattedUpdatedAt }}</span>
        </div>
      </article>

      <article class="wallpaper-panel">
        <div class="wallpaper-panel__head">
          <div>
            <div class="wallpaper-panel__eyebrow">Preset Library</div>
            <h2>系统预设</h2>
          </div>
        </div>

        <div class="wallpaper-preset-grid">
          <button
            v-for="preset in presets"
            :key="preset.id"
            type="button"
            class="wallpaper-preset-card"
            :class="{ 'is-active': draftConfig.mode === 'preset' && draftConfig.presetId === preset.id }"
            @click="selectPreset(preset.id)"
          >
            <span class="wallpaper-preset-card__thumb" :style="{ background: preset.thumbnail }" />
            <strong>{{ preset.label }}</strong>
          </button>
        </div>
      </article>

      <article class="wallpaper-panel">
        <div class="wallpaper-panel__head">
          <div>
            <div class="wallpaper-panel__eyebrow">Custom Upload</div>
            <h2>上传本地图片</h2>
          </div>
        </div>

        <el-upload
          class="wallpaper-upload"
          drag
          action="#"
          :auto-upload="false"
          :show-file-list="false"
          accept="image/png,image/jpeg,image/webp,image/avif"
          :on-change="handleWallpaperFileChange"
        >
          <div class="wallpaper-upload__title">拖拽图片到这里，或点击选择文件</div>
          <div class="wallpaper-upload__hint">
            支持 PNG、JPG、WEBP、AVIF。图片只保存在当前浏览器本地，用于桌面背景预览和展示。
          </div>
        </el-upload>

        <div class="wallpaper-upload-actions">
          <el-button @click="triggerPresetMode">只用系统预设</el-button>
          <el-button
            type="primary"
            plain
            :disabled="draftConfig.mode !== 'custom' || !draftConfig.customImage"
            @click="applyConfig"
          >
            应用上传图片
          </el-button>
        </div>

        <div v-if="selectedFileName" class="wallpaper-upload-meta">
          <span>已选择：{{ selectedFileName }}</span>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  DESKTOP_WALLPAPER_PRESETS,
  getDesktopWallpaperConfig,
  resolveDesktopWallpaperAppearance,
  setDesktopWallpaperConfig,
} from "@/utils/desktop-shell.js";
import { notifyDesktopWallpaperChange } from "@/utils/desktop-app-bridge.js";

const presets = DESKTOP_WALLPAPER_PRESETS;
const savedConfig = getDesktopWallpaperConfig();
const draftConfig = reactive({
  mode: savedConfig.mode,
  presetId: savedConfig.presetId,
  customImage: savedConfig.customImage,
  customLuminance: savedConfig.customLuminance,
  updatedAt: savedConfig.updatedAt,
});
const selectedFileName = ref("");

const previewAppearance = computed(() =>
  resolveDesktopWallpaperAppearance(draftConfig),
);

const previewStyle = computed(() => ({
  background: previewAppearance.value.background,
}));

const formattedUpdatedAt = computed(() => {
  const value = String(draftConfig.updatedAt || "").trim();
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
});

function resolveImageLuminance(dataUrl) {
  return new Promise((resolve) => {
    if (typeof Image === "undefined" || typeof document === "undefined") {
      resolve(0.82);
      return;
    }
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      const width = 24;
      const height = Math.max(
        1,
        Math.round((image.naturalHeight / Math.max(image.naturalWidth, 1)) * width),
      );
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) {
        resolve(0.82);
        return;
      }
      context.drawImage(image, 0, 0, width, height);
      const { data } = context.getImageData(0, 0, width, height);
      let total = 0;
      let pixels = 0;
      for (let index = 0; index < data.length; index += 4) {
        const alpha = Number(data[index + 3] || 0) / 255;
        if (alpha <= 0) continue;
        const red = Number(data[index] || 0) / 255;
        const green = Number(data[index + 1] || 0) / 255;
        const blue = Number(data[index + 2] || 0) / 255;
        total += (0.2126 * red + 0.7152 * green + 0.0722 * blue) * alpha;
        pixels += alpha;
      }
      if (!pixels) {
        resolve(0.82);
        return;
      }
      resolve(Math.min(1, Math.max(0, total / pixels)));
    };
    image.onerror = () => resolve(0.82);
    image.src = dataUrl;
  });
}

function selectPreset(presetId) {
  draftConfig.mode = "preset";
  draftConfig.presetId = String(presetId || "").trim() || presets[0]?.id || "";
  draftConfig.customImage = "";
  draftConfig.customLuminance = 0.82;
}

function triggerPresetMode() {
  selectedFileName.value = "";
  if (!draftConfig.presetId) {
    draftConfig.presetId = presets[0]?.id || "";
  }
  draftConfig.mode = "preset";
  draftConfig.customImage = "";
  draftConfig.customLuminance = 0.82;
}

function handleWallpaperFileChange(uploadFile) {
  const file = uploadFile?.raw;
  if (!(file instanceof File)) {
    ElMessage.error("读取图片失败，请重新选择文件");
    return;
  }
  if (!String(file.type || "").startsWith("image/")) {
    ElMessage.warning("只能上传图片文件");
    return;
  }

  const reader = new FileReader();
  reader.onload = async () => {
    const result = String(reader.result || "").trim();
    if (!result) {
      ElMessage.error("图片预览生成失败，请重新上传");
      return;
    }
    const luminance = await resolveImageLuminance(result);
    draftConfig.mode = "custom";
    draftConfig.customImage = result;
    draftConfig.customLuminance = luminance;
    draftConfig.updatedAt = new Date().toISOString();
    selectedFileName.value = String(file.name || "").trim();
    ElMessage.success("背景图片已载入预览，点击“应用当前背景”后生效");
  };
  reader.onerror = () => {
    ElMessage.error("读取图片失败，请更换文件后重试");
  };
  reader.readAsDataURL(file);
}

function applyConfig() {
  try {
    const nextConfig = setDesktopWallpaperConfig({
      mode: draftConfig.mode,
      presetId: draftConfig.presetId,
      customImage: draftConfig.customImage,
      customLuminance: draftConfig.customLuminance,
    });
    draftConfig.mode = nextConfig.mode;
    draftConfig.presetId = nextConfig.presetId;
    draftConfig.customImage = nextConfig.customImage;
    draftConfig.customLuminance = nextConfig.customLuminance;
    draftConfig.updatedAt = nextConfig.updatedAt;
    notifyDesktopWallpaperChange();
    ElMessage.success("桌面背景已更新");
  } catch (err) {
    ElMessage.error(err?.message || "桌面背景保存失败，请更换更小的图片后重试");
  }
}

function resetToPreset() {
  selectedFileName.value = "";
  const nextPresetId = presets[0]?.id || "";
  try {
    const nextConfig = setDesktopWallpaperConfig({
      mode: "preset",
      presetId: nextPresetId,
      customImage: "",
      customLuminance: 0.82,
    });
    draftConfig.mode = nextConfig.mode;
    draftConfig.presetId = nextConfig.presetId;
    draftConfig.customImage = nextConfig.customImage;
    draftConfig.customLuminance = nextConfig.customLuminance;
    draftConfig.updatedAt = nextConfig.updatedAt;
    notifyDesktopWallpaperChange();
    ElMessage.success("已恢复为系统预设背景");
  } catch (err) {
    ElMessage.error(err?.message || "恢复系统预设背景失败");
  }
}
</script>

<style scoped>
.desktop-wallpaper-page {
  min-height: 100vh;
  padding: 34px;
  box-sizing: border-box;
  background:
    radial-gradient(circle at 10% 0%, rgba(125, 211, 252, 0.18), transparent 24%),
    radial-gradient(circle at 88% 18%, rgba(103, 232, 249, 0.14), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 42%, #edf2f7 100%);
}

.wallpaper-hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-end;
  margin-bottom: 28px;
}

.wallpaper-hero__eyebrow,
.wallpaper-panel__eyebrow {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #64748b;
}

.wallpaper-hero h1,
.wallpaper-panel h2 {
  margin: 10px 0 0;
  color: #0f172a;
}

.wallpaper-hero h1 {
  font-size: clamp(42px, 7vw, 74px);
  line-height: 0.96;
  letter-spacing: -0.06em;
}

.wallpaper-hero p {
  max-width: 56ch;
  margin: 16px 0 0;
  color: #475569;
  font-size: 15px;
  line-height: 1.75;
}

.wallpaper-hero__actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.wallpaper-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 18px;
}

.wallpaper-panel {
  padding: 22px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.68);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.wallpaper-panel--preview {
  grid-row: span 2;
}

.wallpaper-panel__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.wallpaper-mode-badge {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.08);
  color: #0f172a;
  font-size: 12px;
  font-weight: 800;
}

.wallpaper-preview-shell {
  padding: 16px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.54);
}

.wallpaper-preview {
  position: relative;
  min-height: 420px;
  border-radius: 24px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.72);
}

.wallpaper-preview__ambient {
  position: absolute;
  top: 12%;
  width: 12rem;
  height: 12rem;
  border-radius: 999px;
  filter: blur(72px);
}

.wallpaper-preview__ambient--left {
  left: 8%;
}

.wallpaper-preview__ambient--right {
  right: 8%;
}

.wallpaper-preview__dock {
  position: absolute;
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  display: inline-flex;
  gap: 12px;
  padding: 12px 18px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.5);
  backdrop-filter: blur(14px);
  box-shadow: 0 14px 30px rgba(15, 23, 42, 0.14);
}

.wallpaper-preview__dock span {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.78);
  color: #0f172a;
  font-size: 12px;
  font-weight: 900;
}

.wallpaper-preview-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
  color: #526071;
  font-size: 13px;
}

.wallpaper-preset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.wallpaper-preset-card {
  padding: 12px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
  cursor: pointer;
  text-align: left;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.wallpaper-preset-card:hover,
.wallpaper-preset-card.is-active {
  transform: translateY(-2px);
  box-shadow: 0 16px 34px rgba(15, 23, 42, 0.08);
  border-color: rgba(15, 23, 42, 0.2);
}

.wallpaper-preset-card__thumb {
  display: block;
  height: 84px;
  border-radius: 16px;
  margin-bottom: 10px;
}

.wallpaper-upload :deep(.el-upload-dragger) {
  width: 100%;
  padding: 28px 20px;
  border-radius: 22px;
  border: 1px dashed rgba(15, 23, 42, 0.18);
  background: rgba(255, 255, 255, 0.58);
}

.wallpaper-upload__title {
  color: #0f172a;
  font-size: 15px;
  font-weight: 800;
}

.wallpaper-upload__hint {
  margin-top: 8px;
  color: #526071;
  font-size: 13px;
  line-height: 1.7;
}

.wallpaper-upload-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.wallpaper-upload-meta {
  margin-top: 12px;
  color: #526071;
  font-size: 13px;
}

@media (max-width: 980px) {
  .wallpaper-layout {
    grid-template-columns: 1fr;
  }

  .wallpaper-panel--preview {
    grid-row: auto;
  }

  .wallpaper-preview {
    min-height: 320px;
  }

  .wallpaper-hero {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
