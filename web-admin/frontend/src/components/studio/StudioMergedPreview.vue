<template>
  <section class="studio-preview-card">
    <div class="studio-preview-card__head">
      <div>
        <div class="studio-preview-card__title">合并预览</div>
        <div class="studio-preview-card__subtitle">
          深色时间线编辑器，支持播放、拖拽排序、时间轴缩放和右键删除。
        </div>
      </div>
      <span class="studio-preview-card__time">{{ formattedDuration }}</span>
    </div>

    <div class="studio-preview-card__stage-shell">
      <div class="studio-preview-card__screen">
        <video
          v-if="previewClipVideoUrl"
          ref="activeVideoRef"
          class="studio-preview-card__video"
          :src="previewClipVideoUrl"
          :poster="previewClipPosterUrl"
          preload="metadata"
          playsinline
          @click="togglePlayback"
          @timeupdate="handlePlayerTimeUpdate"
          @play="handlePlayerPlay"
          @pause="handlePlayerPause"
        />
        <div v-else-if="previewClip" class="studio-preview-card__screen-copy">
          <div class="studio-preview-card__screen-kicker">当前片段</div>
          <div class="studio-preview-card__screen-title">
            {{ previewClip.title }}
          </div>
          <div class="studio-preview-card__screen-meta">
            {{ previewClipMeta }}
          </div>
        </div>
        <div v-else class="studio-preview-card__play">预览</div>
      </div>
      <audio
        v-if="activeVoiceSourceUrl"
        ref="voiceAudioRef"
        class="studio-preview-card__bgm-audio"
        :src="activeVoiceSourceUrl"
        preload="auto"
      />
      <audio
        v-if="bgmTrackSourceUrl"
        ref="bgmAudioRef"
        class="studio-preview-card__bgm-audio"
        :src="bgmTrackSourceUrl"
        preload="auto"
        loop
      />

      <div class="studio-preview-card__transport-bar">
        <div class="studio-preview-card__transport-actions">
          <button
            type="button"
            class="studio-preview-card__transport-button studio-preview-card__transport-button--ghost"
            :disabled="!hasPrevClip"
            @click="jumpToAdjacentClip(-1)"
          >
            上一段
          </button>
          <button
            type="button"
            class="studio-preview-card__transport-button studio-preview-card__transport-button--primary"
            :disabled="!clips.length"
            @click="togglePlayback"
          >
            {{ isPlaying ? "暂停播放" : "开始播放" }}
          </button>
          <button
            type="button"
            class="studio-preview-card__transport-button studio-preview-card__transport-button--ghost"
            :disabled="!hasNextClip"
            @click="jumpToAdjacentClip(1)"
          >
            下一段
          </button>
          <button
            type="button"
            class="studio-preview-card__transport-button studio-preview-card__transport-button--ghost"
            :disabled="!clips.length"
            @click="restartPlayback"
          >
            回到开头
          </button>
        </div>
        <div class="studio-preview-card__transport-copy">
          <strong>{{ previewClipTitle }}</strong>
          <span>{{ previewClipMeta }} · 共 {{ clips.length }} 段</span>
        </div>
      </div>

    </div>

    <div class="studio-editor">
      <div class="studio-editor__toolbar">
        <div>
          <div class="studio-editor__title">时间线编辑器</div>
          <div class="studio-editor__caption">{{ editorSummary }}</div>
        </div>
        <div class="studio-editor__toolbar-actions">
          <div
            v-if="clips.length > 1"
            class="studio-editor__zoom-controls"
          >
            <button
              type="button"
              class="studio-editor__toolbar-button"
              :disabled="timelineZoom <= TIMELINE_ZOOM_MIN"
              @click="adjustTimelineZoom(-TIMELINE_ZOOM_STEP)"
            >
              缩小
            </button>
            <span class="studio-editor__zoom-label">{{ timelineZoomLabel }}</span>
            <button
              type="button"
              class="studio-editor__toolbar-button"
              :disabled="timelineZoom >= 1"
              @click="resetTimelineZoom"
            >
              还原
            </button>
          </div>
          <StudioActionMenu
            trigger-text="添加音频"
            :actions="audioTrackActionItems"
            @select="handleAudioTrackAction"
          />
          <button
            v-if="hasBgmTrack"
            type="button"
            class="studio-editor__toolbar-button"
            @click="toggleBgmTrackVisibility"
          >
            {{ showBgmTrack ? "隐藏背景音乐" : "显示背景音乐" }}
          </button>
        </div>
      </div>

      <div class="studio-editor__grid">
        <div class="studio-editor__row studio-editor__row--ruler">
          <div class="studio-editor__track-label studio-editor__track-label--ghost">
            时间
          </div>
          <div
            ref="rulerScrollRef"
            class="studio-editor__timeline-scroll-shell studio-editor__timeline-scroll-shell--ruler"
            @scroll="handleRulerScroll"
          >
            <div
              class="studio-track__ruler studio-track__ruler--editor"
              :style="timelineCanvasStyle"
              @click="handleRulerClick"
            >
              <span
                v-for="(mark, index) in timelineMarks"
                :key="`mark-${mark.second}`"
                class="studio-track__tick"
                :class="{
                  'is-edge-start': index === 0,
                  'is-edge-end': index === timelineMarks.length - 1,
                }"
                :style="{ left: `${mark.left}%` }"
              >
                {{ mark.label }}
              </span>
              <div
                class="studio-track__playhead studio-track__playhead--ruler"
                :style="{ left: `${playheadLeft}%` }"
                @mousedown.stop.prevent="startPlayheadDrag"
              >
                <span>{{ currentTimeLabel }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="studio-editor__timeline-shell">
          <div class="studio-editor__timeline-labels">
            <div
              class="studio-editor__track-label studio-editor__track-label--video studio-editor__track-label--with-control"
              :class="{
                'is-muted': resolveAudioChannelControl('video')?.muted,
                'is-disabled': !resolveAudioChannelControl('video')?.enabled,
              }"
            >
              <span class="studio-editor__track-label-text">视频</span>
              <button
                type="button"
                class="studio-editor__track-audio-trigger"
                :class="{ 'is-muted': resolveAudioChannelControl('video')?.muted }"
                :disabled="!resolveAudioChannelControl('video')?.enabled"
                :title="resolveAudioChannelControl('video')?.muted ? '解除视频静音' : '静音视频'"
                :aria-label="resolveAudioChannelControl('video')?.muted ? '解除视频静音' : '静音视频'"
                @click.stop="toggleChannelMute('video')"
              >
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path d="M4 8.2h3.1l3.8-3.2a.8.8 0 0 1 1.31.61v8.8a.8.8 0 0 1-1.31.61L7.1 11.8H4a.8.8 0 0 1-.8-.8V9a.8.8 0 0 1 .8-.8Z" />
                  <path
                    class="studio-editor__track-audio-wave"
                    d="M14.2 7.1a4.1 4.1 0 0 1 0 5.8M15.9 5.4a6.5 6.5 0 0 1 0 9.2"
                  />
                  <path
                    class="studio-editor__track-audio-mute"
                    d="M14.2 6l3.8 8"
                  />
                </svg>
              </button>
              <div
                class="studio-editor__track-audio-panel"
                @click.stop
                @mousedown.stop
                @pointerdown.stop
              >
                <input
                  class="studio-editor__track-audio-slider"
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  :disabled="!resolveAudioChannelControl('video')?.enabled"
                  :value="Math.round((resolveAudioChannelControl('video')?.volume || 0) * 100)"
                  aria-label="视频音量"
                  @input="handleChannelVolumeInput('video', $event)"
                />
              </div>
            </div>
            <div
              v-for="track in displayAudioTracks"
              :key="`label-${track.id}`"
              class="studio-editor__track-label studio-editor__track-label--audio studio-editor__track-label--with-control"
              :class="{
                'is-muted': resolveAudioChannelControl(track.kind)?.muted,
                'is-disabled': !resolveAudioChannelControl(track.kind)?.enabled,
              }"
            >
              <span class="studio-editor__track-label-text">{{ track.label }}</span>
              <button
                type="button"
                class="studio-editor__track-audio-trigger"
                :class="{ 'is-muted': resolveAudioChannelControl(track.kind)?.muted }"
                :disabled="!resolveAudioChannelControl(track.kind)?.enabled"
                :title="
                  resolveAudioChannelControl(track.kind)?.muted
                    ? `解除${track.label}静音`
                    : `静音${track.label}`
                "
                :aria-label="
                  resolveAudioChannelControl(track.kind)?.muted
                    ? `解除${track.label}静音`
                    : `静音${track.label}`
                "
                @click.stop="toggleChannelMute(track.kind)"
              >
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path d="M4 8.2h3.1l3.8-3.2a.8.8 0 0 1 1.31.61v8.8a.8.8 0 0 1-1.31.61L7.1 11.8H4a.8.8 0 0 1-.8-.8V9a.8.8 0 0 1 .8-.8Z" />
                  <path
                    class="studio-editor__track-audio-wave"
                    d="M14.2 7.1a4.1 4.1 0 0 1 0 5.8M15.9 5.4a6.5 6.5 0 0 1 0 9.2"
                  />
                  <path
                    class="studio-editor__track-audio-mute"
                    d="M14.2 6l3.8 8"
                  />
                </svg>
              </button>
              <div
                class="studio-editor__track-audio-panel"
                @click.stop
                @mousedown.stop
                @pointerdown.stop
              >
                <input
                  class="studio-editor__track-audio-slider"
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  :disabled="!resolveAudioChannelControl(track.kind)?.enabled"
                  :value="Math.round((resolveAudioChannelControl(track.kind)?.volume || 0) * 100)"
                  :aria-label="`${track.label}音量`"
                  @input="handleChannelVolumeInput(track.kind, $event)"
                />
              </div>
            </div>
          </div>

          <div
            ref="bodyScrollRef"
            class="studio-editor__timeline-body-shell"
            @scroll="handleTimelineBodyScroll"
          >
            <div
              ref="timelineBodyRef"
              class="studio-editor__timeline-canvas"
              :style="timelineCanvasStyle"
            >
              <div
                v-if="clips.length"
                class="studio-editor__timeline-playhead"
                :style="{ left: `${playheadLeft}%` }"
                @mousedown.stop.prevent="startPlayheadDrag"
              />

              <div
                v-if="clips.length"
                ref="laneRef"
                class="studio-track__lane"
                @click="handleLaneClick"
                @dragover.prevent="handleLaneDragOver"
                @drop.prevent="handleLaneDrop"
              >
                <div class="studio-track__lane-grid" aria-hidden="true">
                  <span
                    v-for="(mark, index) in timelineMarks"
                    :key="`lane-mark-${mark.second}`"
                    class="studio-track__lane-tick"
                    :class="{
                      'is-edge-start': index === 0,
                      'is-edge-end': index === timelineMarks.length - 1,
                    }"
                    :style="{ left: `${mark.left}%` }"
                  />
                </div>
                <div
                  v-if="insertIndicatorLeft !== null"
                  class="studio-track__insert-indicator"
                  :style="{ left: `${insertIndicatorLeft}%` }"
                >
                  <span>{{ insertIndicatorLabel }}</span>
                </div>
                <div
                  v-for="clip in clips"
                  :key="clip.id"
                  class="studio-track__clip"
                  :class="{
                    'is-active': clip.id === previewClip?.id,
                    'is-drop-target': clip.id === hoverClipId,
                    'is-dragging': clip.id === draggingClipId,
                    'is-compact': clipUsesCompactLayout(clip),
                    'is-condensed': clipUsesCondensedLayout(clip),
                    'has-floating-label': clipNeedsFloatingLabel(clip),
                  }"
                  role="button"
                  tabindex="0"
                  :draggable="props.clips.length > 1"
                  :title="`${clip.title} · ${formatSeconds(clip.startSeconds || 0)} - ${formatSeconds(clip.endSeconds || 0)}`"
                  :style="clipStyle(clip)"
                  @dragstart="handleDragStart($event, clip.id)"
                  @dragover.prevent="handleLaneDragOver"
                  @drop.prevent="handleLaneDrop"
                  @dragend="resetDragState"
                  @click.stop="handleClipSelect(clip.id)"
                  @contextmenu.prevent.stop="openClipContextMenu($event, clip)"
                  @keydown.enter.stop.prevent="handleClipSelect(clip.id)"
                  @keydown.space.stop.prevent="handleClipSelect(clip.id)"
                >
                  <span
                    v-if="clipNeedsFloatingLabel(clip)"
                    class="studio-track__clip-floating-label"
                  >
                    {{ clip.title }}
                  </span>
                  <div class="studio-track__clip-surface">
                    <span
                      v-if="clip.sourceType === 'material' && !clipUsesCompactLayout(clip)"
                      class="studio-track__clip-source"
                    >
                      素材视频
                    </span>
                    <span
                      v-if="!clipNeedsFloatingLabel(clip)"
                      class="studio-track__clip-title"
                    >
                      {{ clip.title }}
                    </span>
                  </div>
                </div>
                <div
                  v-if="draggingClipId"
                  class="studio-track__drop-tail"
                  :class="{ 'is-active': hoverClipId === '__tail__' }"
                  @dragover.prevent="handleLaneDragOver"
                  @drop.prevent="handleDropToEnd"
                >
                  追加到末尾
                </div>
              </div>
              <div v-else class="studio-track__line">
                <span class="studio-track__empty">还没有可预览的视频片段</span>
              </div>

              <div
                v-for="track in displayAudioTracks"
                :key="track.id"
                class="studio-track__audio-body"
                @click="handleLaneClick"
              >
                <div class="studio-track__audio-grid" aria-hidden="true">
                  <span
                    v-for="(mark, index) in timelineMarks"
                    :key="`audio-mark-${track.id}-${mark.second}`"
                    class="studio-track__audio-tick"
                    :class="{
                      'is-edge-start': index === 0,
                      'is-edge-end': index === timelineMarks.length - 1,
                    }"
                    :style="{ left: `${mark.left}%` }"
                  />
                </div>
                <template v-if="track.segments.length">
                  <div
                    v-for="segment in track.segments"
                    :key="segment.id"
                    class="studio-track__audio-segment"
                    :class="audioSegmentClass(track.kind)"
                    :style="audioSegmentStyle(segment)"
                    @contextmenu.prevent.stop="
                      openAudioSegmentContextMenu($event, track, segment)
                    "
                  >
                    <span class="studio-track__audio-segment-label">
                      {{ segment.label }}
                    </span>
                  </div>
                </template>
                <span v-else class="studio-track__empty studio-track__empty--inline">
                  {{ trackPlaceholderText(track) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <StudioContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :items="contextMenu.items"
      @close="closeContextMenu"
      @select="handleContextMenuSelect"
    />
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import StudioActionMenu from "@/components/studio/StudioActionMenu.vue";
import StudioContextMenu from "@/components/studio/StudioContextMenu.vue";

const props = defineProps({
  clips: {
    type: Array,
    default: () => [],
  },
  duration: {
    type: Number,
    default: 0,
  },
  audioTracks: {
    type: Array,
    default: () => [],
  },
  audioMix: {
    type: Object,
    default: () => ({}),
  },
  activeClipId: {
    type: String,
    default: "",
  },
});

const emit = defineEmits([
  "focus-clip",
  "reorder-clips",
  "remove-clip",
  "remove-audio-segment",
  "request-audio-upload",
  "update-audio-mix",
]);

const TIMELINE_ZOOM_MIN = 0.6;
const TIMELINE_ZOOM_MAX = 1;
const TIMELINE_ZOOM_STEP = 0.1;

const activeVideoRef = ref(null);
const voiceAudioRef = ref(null);
const bgmAudioRef = ref(null);
const laneRef = ref(null);
const rulerScrollRef = ref(null);
const bodyScrollRef = ref(null);
const timelineBodyRef = ref(null);
const timelineViewportWidth = ref(0);
const draggingClipId = ref("");
const hoverClipId = ref("");
const hoverClipInsertMode = ref("tail");
const currentTime = ref(0);
const isPlaying = ref(false);
const playbackFrameId = ref(0);
const playbackLastTimestamp = ref(0);
const syncingPlayer = ref(false);
const playerSourceSwitching = ref(false);
const playerSourceSwitchTimer = ref(0);
const syncingFocusFromTimeline = ref(false);
const playheadDragging = ref(false);
const showBgmTrack = ref(true);
const timelineZoom = ref(1);
const syncingTimelineScroll = ref(false);
const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  items: [],
  payload: null,
});
const audioMixer = reactive({
  videoMuted: false,
  videoVolume: 1,
  voiceMuted: false,
  voiceVolume: 1,
  bgmMuted: false,
  bgmVolume: 0.56,
});

function normalizeAudioMixVolume(value, fallback = 1) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return fallback;
  return Math.max(0, Math.min(1, numericValue));
}

function syncAudioMixerFromProps(audioMix) {
  const source = audioMix && typeof audioMix === "object" ? audioMix : {};
  audioMixer.videoMuted = Boolean(source.videoMuted);
  audioMixer.videoVolume = normalizeAudioMixVolume(source.videoVolume, 1);
  audioMixer.voiceMuted = Boolean(source.voiceMuted);
  audioMixer.voiceVolume = normalizeAudioMixVolume(source.voiceVolume, 1);
  audioMixer.bgmMuted = Boolean(source.bgmMuted);
  audioMixer.bgmVolume = normalizeAudioMixVolume(source.bgmVolume, 0.56);
}

function emitAudioMixChange() {
  emit("update-audio-mix", {
    videoMuted: audioMixer.videoMuted,
    videoVolume: audioMixer.videoVolume,
    voiceMuted: audioMixer.voiceMuted,
    voiceVolume: audioMixer.voiceVolume,
    bgmMuted: audioMixer.bgmMuted,
    bgmVolume: audioMixer.bgmVolume,
  });
}

const totalDuration = computed(() => Math.max(0, Number(props.duration || 0)));
const timelineVisualDuration = computed(() =>
  Math.max(
    1,
    totalDuration.value /
      Math.max(TIMELINE_ZOOM_MIN, Math.min(TIMELINE_ZOOM_MAX, timelineZoom.value || 1)),
  ),
);
const timelineCanvasStyle = computed(() => ({
  width: "100%",
  maxWidth: "100%",
}));
const timelineCanvasPixelWidth = computed(() =>
  Math.max(0, Number(timelineViewportWidth.value || 0)),
);
const timelineZoomLabel = computed(
  () => `${Math.round(timelineZoom.value * 100)}%`,
);
const currentTimeLabel = computed(() => formatSeconds(currentTime.value));
const formattedDuration = computed(
  () =>
    `${formatSeconds(currentTime.value)} / ${formatSeconds(totalDuration.value)}`,
);
const selectedClip = computed(
  () => props.clips.find((item) => item.id === props.activeClipId) || null,
);
const timelineClip = computed(
  () =>
    resolveClipAtTime(currentTime.value) ||
    selectedClip.value ||
    props.clips[0] ||
    null,
);
const previewClip = computed(() => timelineClip.value);
const previewClipTitle = computed(
  () => previewClip.value?.title || "当前没有可播放片段",
);
const previewClipMeta = computed(() => {
  if (!previewClip.value) return "时间线为空";
  return `${formatSeconds(previewClip.value.startSeconds || 0)} - ${formatSeconds(previewClip.value.endSeconds || 0)}`;
});
const previewClipIndex = computed(() =>
  props.clips.findIndex((item) => item.id === previewClip.value?.id),
);
const hasPrevClip = computed(() => previewClipIndex.value > 0);
const hasNextClip = computed(
  () =>
    previewClipIndex.value >= 0 &&
    previewClipIndex.value < props.clips.length - 1,
);
const previewClipVideoUrl = computed(() =>
  resolvePlayableVideoUrl(previewClip.value),
);
const previewClipPosterUrl = computed(() => {
  const previewUrl = String(previewClip.value?.previewUrl || "").trim();
  if (!previewUrl || previewUrl === previewClipVideoUrl.value) return "";
  return previewUrl;
});
const audioTrackMap = computed(() => {
  const map = new Map();
  for (const track of props.audioTracks) {
    const kind = String(track?.kind || "").trim();
    if (!kind) continue;
    map.set(kind, track);
  }
  return map;
});
const voiceTrack = computed(() => audioTrackMap.value.get("voice") || {});
const bgmTrackSourceUrl = computed(() => {
  const track = audioTrackMap.value.get("bgm") || {};
  return resolveAudioSourceUrl(track);
});
const audioTrackRows = computed(() => {
  const voiceTrackRow = voiceTrack.value || {};
  const bgmTrack = audioTrackMap.value.get("bgm") || {};
  return [
    {
      id: String(voiceTrackRow.id || "audio-track-voice"),
      kind: "voice",
      label: "旁白",
      segments: Array.isArray(voiceTrackRow.segments) ? voiceTrackRow.segments : [],
    },
    {
      id: String(bgmTrack.id || "audio-track-bgm"),
      kind: "bgm",
      label: "背景音乐",
      segments: Array.isArray(bgmTrack.segments) ? bgmTrack.segments : [],
    },
  ];
});
const hasBgmTrack = computed(
  () =>
    audioTrackRows.value.find((track) => track.kind === "bgm")?.segments.length > 0,
);
const displayAudioTracks = computed(() =>
  audioTrackRows.value.filter(
    (track) => showBgmTrack.value || String(track.kind || "").trim() !== "bgm",
  ),
);
const voiceSegments = computed(() =>
  (Array.isArray(voiceTrack.value?.segments) ? voiceTrack.value.segments : []).filter(
    (segment) => resolveAudioSourceUrl(segment),
  ),
);
const activeVoiceSegment = computed(() => {
  const time = Number(currentTime.value || 0);
  return (
    voiceSegments.value.find((segment) => {
      const start = Math.max(0, Number(segment?.startSeconds || 0));
      const duration = Math.max(0, Number(segment?.durationSeconds || 0));
      const end = start + duration;
      return time >= start && time < end;
    }) || null
  );
});
const activeVoiceSourceUrl = computed(() =>
  resolveAudioSourceUrl(activeVoiceSegment.value),
);
const audioTrackActionItems = computed(() => [
  {
    id: "upload-bgm",
    label: hasBgmTrack.value ? "替换背景音乐" : "上传背景音乐",
    description: "选择本地音频文件并写入当前项目，作为导出用背景音乐",
  },
]);
const editorSummary = computed(() => {
  const voiceCount =
    audioTrackRows.value.find((track) => track.kind === "voice")?.segments.length || 0;
  const bgmCount =
    audioTrackRows.value.find((track) => track.kind === "bgm")?.segments.length || 0;
  return `视频 ${props.clips.length} 段 · 旁白 ${voiceCount} 段 · 背景音乐 ${bgmCount ? "已添加" : "未添加"} · 右键内容可删除`;
});
const audioChannelControls = computed(() => [
  {
    id: "video",
    label: "视频",
    enabled: Boolean(previewClipVideoUrl.value),
    muted: audioMixer.videoMuted,
    volume: audioMixer.videoVolume,
  },
  {
    id: "voice",
    label: "旁白",
    enabled: voiceSegments.value.length > 0,
    muted: audioMixer.voiceMuted,
    volume: audioMixer.voiceVolume,
  },
  {
    id: "bgm",
    label: "背景音乐",
    enabled: Boolean(bgmTrackSourceUrl.value),
    muted: audioMixer.bgmMuted,
    volume: audioMixer.bgmVolume,
  },
]);
const timelineMarks = computed(() => {
  const total = Math.max(1, timelineVisualDuration.value);
  const step = resolveTimelineMarkStep(total, timelineCanvasPixelWidth.value);
  const marks = [];
  for (let second = 0; second <= total; second += step) {
    marks.push({
      second,
      left: (second / total) * 100,
      label: formatSeconds(second),
    });
  }
  if (marks[marks.length - 1]?.second !== total) {
    marks.push({
      second: total,
      left: 100,
      label: formatSeconds(total),
    });
  }
  return marks;
});
const playheadLeft = computed(() => {
  const total = Math.max(1, timelineVisualDuration.value);
  return (Math.max(0, Math.min(total, currentTime.value)) / total) * 100;
});
const insertIndicatorLeft = computed(() => {
  if (!draggingClipId.value || !hoverClipId.value) return null;
  if (hoverClipInsertMode.value === "tail" || hoverClipId.value === "__tail__") {
    return 100;
  }
  const target = props.clips.find((item) => item.id === hoverClipId.value);
  if (!target) return null;
  if (hoverClipInsertMode.value === "after") {
    return secondsToPercent(Number(target.endSeconds || 0));
  }
  return secondsToPercent(Number(target.startSeconds || 0));
});
const insertIndicatorLabel = computed(() => {
  if (hoverClipInsertMode.value === "tail" || hoverClipId.value === "__tail__") {
    return "追加到末尾";
  }
  return hoverClipInsertMode.value === "after" ? "插入到后面" : "插入到前面";
});

function formatSeconds(value) {
  const total = Math.max(0, Math.round(Number(value || 0)));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function resolvePlayableVideoUrl(clip) {
  const sourceType = String(clip?.sourceType || "").trim();
  const contentUrl = String(clip?.contentUrl || "").trim();
  const previewUrl = String(clip?.previewUrl || "").trim();
  const mimeType = String(clip?.mimeType || "").trim().toLowerCase();
  if (contentUrl && sourceType === "material") return contentUrl;
  if (contentUrl && mimeType.startsWith("video/")) return contentUrl;
  if (contentUrl && isLikelyVideoUrl(contentUrl)) return contentUrl;
  if (previewUrl && isLikelyVideoUrl(previewUrl)) return previewUrl;
  return "";
}

function resolveAudioSourceUrl(payload) {
  return String(
    payload?.source_url ||
      payload?.sourceUrl ||
      payload?.content_url ||
      payload?.contentUrl ||
      "",
  ).trim();
}

function resolveBgmPlaybackTime(audio) {
  const rawTime = Math.max(0, Number(currentTime.value || 0));
  const audioDuration = Number(audio?.duration || 0);
  if (!Number.isFinite(audioDuration) || audioDuration <= 0) {
    return rawTime;
  }
  if (rawTime <= audioDuration) {
    return rawTime;
  }
  return rawTime % audioDuration;
}

function resolveVoicePlaybackTime(audio, segment = activeVoiceSegment.value) {
  if (!segment) return 0;
  const start = Math.max(0, Number(segment?.startSeconds || 0));
  const offset = Math.max(0, Number(currentTime.value || 0) - start);
  const audioDuration = Number(audio?.duration || 0);
  if (!Number.isFinite(audioDuration) || audioDuration <= 0) {
    return offset;
  }
  return Math.max(0, Math.min(offset, Math.max(0, audioDuration - 0.05)));
}

function isLikelyVideoUrl(url) {
  const normalized = String(url || "").trim().toLowerCase();
  if (!normalized) return false;
  return [".mp4", ".webm", ".mov", ".m4v", ".m3u8", ".ogg"].some((suffix) =>
    normalized.includes(suffix),
  );
}

function resolveTimelineMarkStep(totalSeconds, pixelWidth = 0) {
  const total = Math.max(1, Math.ceil(Number(totalSeconds || 0)));
  const preferredSteps = [1, 2, 5, 10, 15, 30, 60];
  const effectiveWidth = Math.max(240, Number(pixelWidth || 0));
  const targetMarkCount = Math.max(3, Math.floor(effectiveWidth / 84));
  return (
    preferredSteps.find((step) => Math.ceil(total / step) <= targetMarkCount) ||
    Math.max(10, Math.ceil(total / targetMarkCount / 10) * 10)
  );
}

function secondsToPercent(seconds) {
  const total = Math.max(1, timelineVisualDuration.value);
  return (Math.max(0, Math.min(total, Number(seconds || 0))) / total) * 100;
}

function resolveTimelineSpanStyle(startSeconds, durationSeconds) {
  const left = secondsToPercent(startSeconds);
  const maxWidth = Math.max(0, 100 - left);
  const naturalWidth = secondsToPercent(durationSeconds);
  const minWidth = Math.min(maxWidth, 2.4);
  const width = Math.max(minWidth, Math.min(maxWidth, naturalWidth));
  return {
    left: `${left}%`,
    width: `${width}%`,
  };
}

function clipStyle(clip) {
  return resolveTimelineSpanStyle(clip.startSeconds || 0, clip.durationSeconds || 1);
}

function resolveClipWidthPercent(clip) {
  const left = secondsToPercent(clip?.startSeconds || 0);
  const maxWidth = Math.max(0, 100 - left);
  const naturalWidth = secondsToPercent(clip?.durationSeconds || 1);
  const minWidth = Math.min(maxWidth, 2.4);
  return Math.max(minWidth, Math.min(maxWidth, naturalWidth));
}

function clipNeedsFloatingLabel(clip) {
  return resolveClipWidthPercent(clip) < 18;
}

function clipUsesCompactLayout(clip) {
  return resolveClipWidthPercent(clip) < 24;
}

function clipUsesCondensedLayout(clip) {
  return resolveClipWidthPercent(clip) < 12;
}

function audioSegmentClass(kind) {
  return kind === "bgm"
    ? "studio-track__audio-segment--bgm"
    : "studio-track__audio-segment--voice";
}

function audioSegmentStyle(segment) {
  return resolveTimelineSpanStyle(
    segment.startSeconds || 0,
    segment.durationSeconds || 1,
  );
}

function trackPlaceholderText(track) {
  return `未添加${String(track?.label || "音频").trim()}`;
}

function resolveClipAtTime(time) {
  if (!props.clips.length) return null;
  const normalized = Math.max(0, Number(time || 0));
  const hit = props.clips.find((clip) => {
    const start = Math.max(0, Number(clip.startSeconds || 0));
    const end = Math.max(start, Number(clip.endSeconds || start));
    return normalized >= start && normalized < end;
  });
  if (hit) return hit;
  if (normalized >= totalDuration.value) {
    return props.clips[props.clips.length - 1] || null;
  }
  return props.clips[0] || null;
}

function openContextMenu(event, items, payload) {
  contextMenu.value = {
    visible: true,
    x: Number(event?.clientX || 0),
    y: Number(event?.clientY || 0),
    items,
    payload,
  };
}

function closeContextMenu() {
  contextMenu.value = {
    visible: false,
    x: 0,
    y: 0,
    items: [],
    payload: null,
  };
}

function openClipContextMenu(event, clip) {
  openContextMenu(
    event,
    [
      {
        id: "remove",
        label: "删除片段",
        description: `将「${String(clip?.title || "当前片段").trim()}」移出视频轨道并立即保存`,
        danger: true,
      },
    ],
    {
      type: "clip",
      clipId: String(clip?.id || "").trim(),
    },
  );
}

function openAudioSegmentContextMenu(event, track, segment) {
  const kind = String(track?.kind || "").trim();
  if (!["bgm", "voice"].includes(kind)) return;
  const segmentLabel =
    String(segment?.label || "").trim() ||
    (kind === "bgm" ? "当前背景音乐" : "当前旁白");
  openContextMenu(
    event,
    [
      {
        id: "remove",
        label: kind === "bgm" ? "删除背景音乐" : "删除旁白",
        description: `移除「${segmentLabel}」并立即保存`,
        danger: true,
      },
    ],
    {
      type: "audio-segment",
      trackId: String(track?.id || "").trim(),
      kind: String(track?.kind || "").trim(),
      segmentId: String(segment?.id || "").trim(),
      storyboardId: String(segment?.storyboardId || "").trim(),
      label: String(segment?.label || "").trim(),
    },
  );
}

function handleContextMenuSelect(actionId) {
  const payload = contextMenu.value.payload || {};
  closeContextMenu();
  if (actionId !== "remove") return;
  if (payload.type === "clip" && payload.clipId) {
    pausePlayback();
    emit("remove-clip", payload.clipId);
    return;
  }
  if (payload.type === "audio-segment" && payload.segmentId) {
    pausePlayback();
    emit("remove-audio-segment", {
      trackId: payload.trackId,
      kind: payload.kind,
      segmentId: payload.segmentId,
      storyboardId: payload.storyboardId,
      label: payload.label,
    });
  }
}

function stopPlaybackLoop() {
  if (playbackFrameId.value) {
    cancelAnimationFrame(playbackFrameId.value);
    playbackFrameId.value = 0;
  }
  playbackLastTimestamp.value = 0;
}

function setPlayerSourceSwitching(value) {
  playerSourceSwitching.value = Boolean(value);
  if (!playerSourceSwitchTimer.value || typeof window === "undefined") return;
  window.clearTimeout(playerSourceSwitchTimer.value);
  playerSourceSwitchTimer.value = 0;
}

function releasePlayerSourceSwitching(delay = 220) {
  if (typeof window === "undefined") {
    playerSourceSwitching.value = false;
    return;
  }
  if (playerSourceSwitchTimer.value) {
    window.clearTimeout(playerSourceSwitchTimer.value);
  }
  playerSourceSwitchTimer.value = window.setTimeout(() => {
    playerSourceSwitching.value = false;
    playerSourceSwitchTimer.value = 0;
  }, delay);
}

function applyAudioLevel(media, volume, muted) {
  if (!media) return;
  media.muted = Boolean(muted);
  media.volume = Boolean(muted) ? 0 : Math.max(0, Math.min(1, Number(volume || 0)));
}

function applyAudioMix() {
  applyAudioLevel(activeVideoRef.value, audioMixer.videoVolume, audioMixer.videoMuted);
  applyAudioLevel(voiceAudioRef.value, audioMixer.voiceVolume, audioMixer.voiceMuted);
  applyAudioLevel(bgmAudioRef.value, audioMixer.bgmVolume, audioMixer.bgmMuted);
}

function syncVoiceTimeToTimeline({ force = false } = {}) {
  const audio = voiceAudioRef.value;
  const segment = activeVoiceSegment.value;
  if (!audio || !segment || !activeVoiceSourceUrl.value) return;
  const targetTime = resolveVoicePlaybackTime(audio, segment);
  if (!force && Math.abs(Number(audio.currentTime || 0) - targetTime) <= 0.35) {
    return;
  }
  try {
    audio.currentTime = targetTime;
  } catch {
    return;
  }
}

function syncVoicePlaybackDriver() {
  const audio = voiceAudioRef.value;
  if (!audio || !activeVoiceSegment.value || !activeVoiceSourceUrl.value) {
    voiceAudioRef.value?.pause?.();
    return;
  }
  applyAudioMix();
  if (!isPlaying.value) {
    audio.pause?.();
    syncVoiceTimeToTimeline({ force: true });
    return;
  }
  try {
    syncVoiceTimeToTimeline({ force: true });
    const playPromise = audio.play?.();
    playPromise?.catch?.(() => {});
  } catch {
    return;
  }
}

function syncBgmTimeToTimeline({ force = false } = {}) {
  const audio = bgmAudioRef.value;
  if (!audio || !bgmTrackSourceUrl.value) return;
  const targetTime = resolveBgmPlaybackTime(audio);
  if (!force && Math.abs(Number(audio.currentTime || 0) - targetTime) <= 0.35) {
    return;
  }
  try {
    audio.currentTime = targetTime;
  } catch {
    return;
  }
}

function syncBgmPlaybackDriver() {
  const audio = bgmAudioRef.value;
  if (!audio) return;
  if (!bgmTrackSourceUrl.value) {
    audio.pause?.();
    return;
  }
  applyAudioMix();
  if (!isPlaying.value) {
    audio.pause?.();
    syncBgmTimeToTimeline({ force: true });
    return;
  }
  try {
    syncBgmTimeToTimeline({ force: true });
    const playPromise = audio.play?.();
    playPromise?.catch?.(() => {});
  } catch {
    return;
  }
}

function syncPlayerTimeToTimeline({ force = false } = {}) {
  const player = activeVideoRef.value;
  const clip = previewClip.value;
  const videoUrl = previewClipVideoUrl.value;
  if (!player || !clip || !videoUrl) return;
  const clipOffset = Math.max(
    0,
    currentTime.value - Number(clip.startSeconds || 0),
  );
  const applyCurrentTime = () => {
    if (
      !force &&
      Math.abs(Number(player.currentTime || 0) - clipOffset) <= 0.35
    ) {
      return;
    }
    player.currentTime = clipOffset;
  };
  if (player.readyState >= 1) {
    applyCurrentTime();
    return;
  }
  const handleLoadedMetadata = () => {
    player.removeEventListener("loadedmetadata", handleLoadedMetadata);
    try {
      applyCurrentTime();
    } catch {
      return;
    }
  };
  player.addEventListener("loadedmetadata", handleLoadedMetadata, {
    once: true,
  });
}

function syncPlaybackDriver() {
  const player = activeVideoRef.value;
  const videoUrl = previewClipVideoUrl.value;
  applyAudioMix();
  if (!isPlaying.value) {
    stopPlaybackLoop();
    player?.pause?.();
    syncVoicePlaybackDriver();
    syncBgmPlaybackDriver();
    return;
  }
  if (videoUrl && player) {
    stopPlaybackLoop();
    try {
      syncingPlayer.value = true;
      syncPlayerTimeToTimeline({ force: true });
      const playPromise = player.play?.();
      playPromise?.catch?.(() => {});
    } finally {
      setTimeout(() => {
        syncingPlayer.value = false;
      }, 0);
    }
    syncVoicePlaybackDriver();
    syncBgmPlaybackDriver();
    return;
  }
  player?.pause?.();
  stopPlaybackLoop();
  syncVoicePlaybackDriver();
  syncBgmPlaybackDriver();
  playbackFrameId.value = requestAnimationFrame(stepPlayback);
}

function pausePlayback() {
  isPlaying.value = false;
  syncPlaybackDriver();
}

function syncFocusedClipByTime(time) {
  const clip = resolveClipAtTime(time);
  if (!clip || clip.id === props.activeClipId) return;
  syncingFocusFromTimeline.value = true;
  emit("focus-clip", clip.id);
  setTimeout(() => {
    syncingFocusFromTimeline.value = false;
  }, 0);
}

function setCurrentTime(value, { syncFocus = true } = {}) {
  const maxDuration = totalDuration.value;
  const normalized = Math.max(0, Math.min(maxDuration, Number(value || 0)));
  currentTime.value = normalized;
  if (syncFocus) {
    syncFocusedClipByTime(normalized);
  }
}

function stepPlayback(timestamp) {
  if (!isPlaying.value) return;
  if (!playbackLastTimestamp.value) {
    playbackLastTimestamp.value = timestamp;
    playbackFrameId.value = requestAnimationFrame(stepPlayback);
    return;
  }
  const deltaSeconds = (timestamp - playbackLastTimestamp.value) / 1000;
  playbackLastTimestamp.value = timestamp;
  const nextTime = currentTime.value + deltaSeconds;
  if (nextTime >= totalDuration.value) {
    setCurrentTime(totalDuration.value);
    pausePlayback();
    return;
  }
  setCurrentTime(nextTime);
  playbackFrameId.value = requestAnimationFrame(stepPlayback);
}

function startPlayback() {
  if (!props.clips.length) return;
  if (currentTime.value >= totalDuration.value) {
    setCurrentTime(0);
  }
  isPlaying.value = true;
  syncPlaybackDriver();
}

function togglePlayback() {
  if (isPlaying.value) {
    pausePlayback();
    return;
  }
  startPlayback();
}

function handleClipSelect(clipId) {
  closeContextMenu();
  const clip = props.clips.find((item) => item.id === clipId);
  if (!clip) return;
  emit("focus-clip", clip.id);
  setCurrentTime(Number(clip.startSeconds || 0), { syncFocus: false });
}

function focusClipAtIndex(index) {
  const clip = props.clips[index];
  if (!clip) return;
  pausePlayback();
  emit("focus-clip", clip.id);
  setCurrentTime(Number(clip.startSeconds || 0), { syncFocus: false });
}

function jumpToAdjacentClip(offset) {
  if (previewClipIndex.value < 0) return;
  focusClipAtIndex(previewClipIndex.value + offset);
}

function restartPlayback() {
  if (!props.clips.length) return;
  emit("focus-clip", props.clips[0].id);
  setCurrentTime(0, { syncFocus: false });
  startPlayback();
}

function toggleChannelMute(channelId) {
  const normalized = String(channelId || "").trim();
  if (!normalized) return;
  const mutedKey = `${normalized}Muted`;
  if (!(mutedKey in audioMixer)) return;
  audioMixer[mutedKey] = !audioMixer[mutedKey];
  emitAudioMixChange();
}

function handleChannelVolumeInput(channelId, event) {
  const normalized = String(channelId || "").trim();
  const volumeKey = `${normalized}Volume`;
  const mutedKey = `${normalized}Muted`;
  if (!(volumeKey in audioMixer) || !(mutedKey in audioMixer)) return;
  const nextVolume = Math.max(
    0,
    Math.min(1, Number(event?.target?.value || 0) / 100),
  );
  audioMixer[volumeKey] = nextVolume;
  if (nextVolume > 0 && audioMixer[mutedKey]) {
    audioMixer[mutedKey] = false;
  }
  emitAudioMixChange();
}

function resolveAudioChannelControl(channelId) {
  return (
    audioChannelControls.value.find(
      (channel) => String(channel.id || "").trim() === String(channelId || "").trim(),
    ) || null
  );
}

function clampTimelineZoom(value) {
  const numericValue = Number(value || TIMELINE_ZOOM_MIN);
  if (!Number.isFinite(numericValue)) return TIMELINE_ZOOM_MIN;
  return Math.min(
    TIMELINE_ZOOM_MAX,
    Math.max(
      TIMELINE_ZOOM_MIN,
      Math.round(numericValue / TIMELINE_ZOOM_STEP) * TIMELINE_ZOOM_STEP,
    ),
  );
}

function updateTimelineZoom(value) {
  timelineZoom.value = clampTimelineZoom(value);
}

function adjustTimelineZoom(delta) {
  updateTimelineZoom(timelineZoom.value + Number(delta || 0));
}

function resetTimelineZoom() {
  timelineZoom.value = 1;
}

function updateTimelineViewportWidth() {
  timelineViewportWidth.value = Math.max(
    Number(bodyScrollRef.value?.clientWidth || 0),
    Number(rulerScrollRef.value?.clientWidth || 0),
    0,
  );
}

function syncTimelineScroll(source) {
  if (syncingTimelineScroll.value) return;
  const sourceNode =
    source === "ruler" ? rulerScrollRef.value : bodyScrollRef.value;
  const targetNode =
    source === "ruler" ? bodyScrollRef.value : rulerScrollRef.value;
  if (!sourceNode || !targetNode) return;
  syncingTimelineScroll.value = true;
  targetNode.scrollLeft = sourceNode.scrollLeft;
  requestAnimationFrame(() => {
    syncingTimelineScroll.value = false;
  });
}

function handleRulerScroll() {
  syncTimelineScroll("ruler");
}

function handleTimelineBodyScroll() {
  syncTimelineScroll("body");
}

function toggleBgmTrackVisibility() {
  if (!hasBgmTrack.value) return;
  showBgmTrack.value = !showBgmTrack.value;
}

function handleAudioTrackAction(actionId) {
  if (actionId !== "upload-bgm") return;
  emit("request-audio-upload");
}

function resolveTimeByClientX(
  clientX,
  container = timelineBodyRef.value || laneRef.value,
  duration = timelineVisualDuration.value,
) {
  if (!container) return 0;
  const rect = container.getBoundingClientRect();
  if (!rect.width) return 0;
  const pointerX = Math.min(rect.right, Math.max(rect.left, Number(clientX || 0)));
  const ratio = (pointerX - rect.left) / rect.width;
  return Math.max(0, Number(duration || 0)) * ratio;
}

function handleLaneClick(event) {
  closeContextMenu();
  if (draggingClipId.value || playheadDragging.value) return;
  setCurrentTime(resolveTimeByClientX(event?.clientX, event.currentTarget));
}

function handleRulerClick(event) {
  closeContextMenu();
  setCurrentTime(resolveTimeByClientX(event?.clientX, event.currentTarget));
}

function handleDragStart(event, clipId) {
  closeContextMenu();
  if (props.clips.length < 2) return;
  pausePlayback();
  event?.dataTransfer?.setData("text/plain", clipId);
  if (event?.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
  }
  event?.dataTransfer?.setDragImage?.(event.currentTarget, 24, 20);
  draggingClipId.value = clipId;
  hoverClipId.value = clipId;
}

function timelineClipsWithoutDragging(sourceClipId = draggingClipId.value) {
  const normalizedId = String(sourceClipId || "").trim();
  if (!normalizedId) return [...props.clips];
  return props.clips.filter((item) => item.id !== normalizedId);
}

function resolveInsertionTarget(clientX) {
  const orderedClips = timelineClipsWithoutDragging();
  if (!orderedClips.length) {
    return {
      clipId: "__tail__",
      insertMode: "tail",
    };
  }
  const pointerSeconds = resolveTimeByClientX(clientX);
  for (const clip of orderedClips) {
    const start = Math.max(0, Number(clip.startSeconds || 0));
    const duration = Math.max(1, Number(clip.durationSeconds || 1));
    const midpoint = start + duration / 2;
    const end = Math.max(start, Number(clip.endSeconds || start + duration));
    if (pointerSeconds <= midpoint) {
      return {
        clipId: clip.id,
        insertMode: "before",
      };
    }
    if (pointerSeconds < end) {
      return {
        clipId: clip.id,
        insertMode: "after",
      };
    }
  }
  return {
    clipId: "__tail__",
    insertMode: "tail",
  };
}

function applyHoverInsertion(clientX) {
  const target = resolveInsertionTarget(clientX);
  hoverClipId.value = target.clipId;
  hoverClipInsertMode.value = target.insertMode;
}

function resolveDropTargetClipId(sourceClipId, targetClipId, insertMode) {
  if (insertMode === "tail" || targetClipId === "__tail__") return "";
  if (insertMode === "before") return targetClipId;
  const orderedClips = timelineClipsWithoutDragging(sourceClipId);
  const targetIndex = orderedClips.findIndex((item) => item.id === targetClipId);
  if (targetIndex < 0) return "";
  return String(orderedClips[targetIndex + 1]?.id || "").trim();
}

function commitClipReorder(sourceClipId, targetClipId, insertMode) {
  const resolvedTarget = resolveDropTargetClipId(
    sourceClipId,
    targetClipId,
    insertMode,
  );
  if (!resolvedTarget) {
    emit("reorder-clips", sourceClipId, "");
    return;
  }
  if (resolvedTarget === sourceClipId) return;
  emit("reorder-clips", sourceClipId, resolvedTarget);
}

function handleDrop(targetClipId) {
  if (!draggingClipId.value || draggingClipId.value === targetClipId) return;
  commitClipReorder(draggingClipId.value, targetClipId, hoverClipInsertMode.value);
  resetDragState();
}

function handleDropToEnd() {
  if (!draggingClipId.value) return;
  emit("reorder-clips", draggingClipId.value, "");
  resetDragState();
}

function handleLaneDragOver(event) {
  if (!draggingClipId.value) return;
  applyHoverInsertion(event?.clientX);
}

function handleLaneDrop(event) {
  if (!draggingClipId.value) return;
  applyHoverInsertion(event?.clientX);
  if (hoverClipInsertMode.value === "tail" || hoverClipId.value === "__tail__") {
    handleDropToEnd();
    return;
  }
  handleDrop(hoverClipId.value);
}

function resetDragState() {
  draggingClipId.value = "";
  hoverClipId.value = "";
  hoverClipInsertMode.value = "tail";
}

function stopPlayheadDrag() {
  if (typeof window === "undefined") return;
  window.removeEventListener("mousemove", handleWindowPointerMove);
  window.removeEventListener("mouseup", stopPlayheadDrag);
  const wasDragging = playheadDragging.value;
  playheadDragging.value = false;
  if (!wasDragging) return;
  void nextTick(() => {
    syncPlayerTimeToTimeline({ force: true });
    syncVoiceTimeToTimeline({ force: true });
    syncBgmTimeToTimeline({ force: true });
  });
}

function handleWindowPointerMove(event) {
  if (!playheadDragging.value) return;
  event?.preventDefault?.();
  setCurrentTime(resolveTimeByClientX(event?.clientX));
}

function startPlayheadDrag(event) {
  closeContextMenu();
  pausePlayback();
  playheadDragging.value = true;
  setCurrentTime(resolveTimeByClientX(event?.clientX));
  if (typeof window === "undefined") return;
  window.addEventListener("mousemove", handleWindowPointerMove);
  window.addEventListener("mouseup", stopPlayheadDrag);
}

function handlePlayerTimeUpdate(event) {
  if (syncingPlayer.value || playerSourceSwitching.value) return;
  const player = event?.target;
  const clip = previewClip.value;
  if (!player || !clip) return;
  setCurrentTime(
    Number(clip.startSeconds || 0) + Number(player.currentTime || 0),
  );
}

function handlePlayerPlay() {
  if (playerSourceSwitching.value) {
    setPlayerSourceSwitching(false);
  }
  if (syncingPlayer.value) return;
  isPlaying.value = true;
  stopPlaybackLoop();
}

function handlePlayerPause() {
  if (syncingPlayer.value || playerSourceSwitching.value) return;
  isPlaying.value = false;
  stopPlaybackLoop();
}

watch(
  () => props.clips.length,
  (count) => {
    if (count <= 1) {
      resetTimelineZoom();
    }
  },
  { immediate: true },
);

watch(
  () => totalDuration.value,
  (duration) => {
    if (!duration) {
      currentTime.value = 0;
      pausePlayback();
      return;
    }
    if (currentTime.value > duration) {
      setCurrentTime(duration);
    }
  },
  { immediate: true },
);

watch(
  () => props.activeClipId,
  (clipId) => {
    if (syncingFocusFromTimeline.value || isPlaying.value) return;
    const clip = props.clips.find((item) => item.id === clipId);
    if (!clip) return;
    const start = Number(clip.startSeconds || 0);
    const end = Math.max(start, Number(clip.endSeconds || start));
    if (currentTime.value >= start && currentTime.value < end) return;
    setCurrentTime(start, { syncFocus: false });
  },
);

watch(
  () => [
    props.audioMix?.videoMuted,
    props.audioMix?.videoVolume,
    props.audioMix?.voiceMuted,
    props.audioMix?.voiceVolume,
    props.audioMix?.bgmMuted,
    props.audioMix?.bgmVolume,
  ],
  () => {
    syncAudioMixerFromProps(props.audioMix);
  },
  { immediate: true },
);

watch(
  () => [previewClip.value?.id, previewClipVideoUrl.value],
  async () => {
    await nextTick();
    if (playheadDragging.value) return;
    const player = activeVideoRef.value;
    const clip = previewClip.value;
    const videoUrl = previewClipVideoUrl.value;
    if (!clip) {
      setPlayerSourceSwitching(false);
      stopPlaybackLoop();
      return;
    }
    if (!player || !videoUrl) {
      setPlayerSourceSwitching(false);
      syncPlaybackDriver();
      return;
    }
    const shouldPreservePlayback = isPlaying.value;
    if (shouldPreservePlayback) {
      setPlayerSourceSwitching(true);
    }
    try {
      syncingPlayer.value = true;
      player.pause();
      syncPlayerTimeToTimeline({ force: true });
    } catch {
      return;
    } finally {
      setTimeout(() => {
        syncingPlayer.value = false;
      }, 0);
    }
    syncPlaybackDriver();
    if (shouldPreservePlayback) {
      releasePlayerSourceSwitching();
    } else {
      setPlayerSourceSwitching(false);
    }
  },
);

watch(
  () => [activeVoiceSegment.value?.id, activeVoiceSourceUrl.value],
  async () => {
    await nextTick();
    if (playheadDragging.value) return;
    syncVoicePlaybackDriver();
  },
);

watch(
  () => bgmTrackSourceUrl.value,
  async () => {
    await nextTick();
    syncBgmPlaybackDriver();
  },
);

watch(
  () => currentTime.value,
  async () => {
    if (playheadDragging.value) return;
    try {
      if (previewClipVideoUrl.value) {
        syncingPlayer.value = true;
        syncPlayerTimeToTimeline();
      }
      syncVoiceTimeToTimeline();
      syncBgmTimeToTimeline();
    } catch {
      return;
    } finally {
      if (previewClipVideoUrl.value) {
        setTimeout(() => {
          syncingPlayer.value = false;
        }, 0);
      }
    }
  },
);

watch(
  () => [
    audioMixer.videoMuted,
    audioMixer.videoVolume,
    audioMixer.voiceMuted,
    audioMixer.voiceVolume,
    audioMixer.bgmMuted,
    audioMixer.bgmVolume,
  ],
  () => {
    applyAudioMix();
  },
  { immediate: true },
);

watch(
  () => isPlaying.value,
  () => {
    syncPlaybackDriver();
  },
);

watch(
  () => hasBgmTrack.value,
  (value) => {
    if (!value) {
      showBgmTrack.value = true;
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  closeContextMenu();
  pausePlayback();
  setPlayerSourceSwitching(false);
  stopPlayheadDrag();
  if (typeof window !== "undefined") {
    window.removeEventListener("resize", updateTimelineViewportWidth);
  }
});

onMounted(() => {
  updateTimelineViewportWidth();
  if (typeof window !== "undefined") {
    window.addEventListener("resize", updateTimelineViewportWidth);
  }
});
</script>

<style scoped>
.studio-preview-card {
  display: flex;
  flex-direction: column;
  gap: 18px;
  height: 100%;
  padding: 20px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 28px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.98));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.72),
    0 24px 64px rgba(15, 23, 42, 0.1);
  box-sizing: border-box;
}

.studio-preview-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.studio-preview-card__title {
  color: #0f172a;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.25;
}

.studio-preview-card__subtitle,
.studio-preview-card__time {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.studio-preview-card__stage-shell {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.studio-preview-card__screen {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: min(100%, 960px);
  height: clamp(320px, 34vw, 520px);
  margin: 0 auto;
  padding: 14px;
  border-radius: 22px;
  overflow: hidden;
  background:
    linear-gradient(180deg, rgba(30, 41, 59, 0.92), rgba(2, 6, 23, 0.96)),
    #020617;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12);
  box-sizing: border-box;
}

.studio-preview-card__video {
  display: block;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  object-fit: contain !important;
  background: #000;
  border-radius: 16px;
}

.studio-preview-card__bgm-audio {
  display: none;
}

.studio-preview-card__screen-copy {
  display: grid;
  gap: 12px;
  max-width: min(76%, 520px);
  text-align: center;
}

.studio-preview-card__screen-kicker {
  color: rgba(148, 163, 184, 0.88);
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.studio-preview-card__screen-title {
  color: #f8fafc;
  font-size: 28px;
  font-weight: 700;
  line-height: 1.3;
}

.studio-preview-card__screen-meta,
.studio-preview-card__play {
  color: rgba(191, 219, 254, 0.88);
  font-size: 14px;
  line-height: 1.7;
}

.studio-preview-card__transport-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.96);
  box-shadow:
    inset 0 0 0 1px rgba(148, 163, 184, 0.14),
    0 10px 24px rgba(15, 23, 42, 0.06);
}

.studio-preview-card__transport-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.studio-preview-card__transport-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 92px;
  min-height: 38px;
  padding: 0 16px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: #ffffff;
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease;
}

.studio-preview-card__transport-button:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgba(96, 165, 250, 0.42);
  background: #eff6ff;
}

.studio-preview-card__transport-button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.studio-preview-card__transport-button--primary {
  border-color: rgba(249, 115, 22, 0.52);
  background: linear-gradient(135deg, #f97316, #fb923c);
  color: #fff7ed;
}

.studio-preview-card__transport-button--primary:hover:not(:disabled) {
  border-color: rgba(249, 115, 22, 0.68);
  background: linear-gradient(135deg, #ea580c, #f97316);
  color: #fff7ed;
  box-shadow: 0 10px 22px rgba(249, 115, 22, 0.22);
}

.studio-preview-card__transport-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
  text-align: right;
}

.studio-preview-card__transport-copy strong {
  color: #0f172a;
  font-size: 13px;
  line-height: 1.4;
  word-break: break-all;
}

.studio-preview-card__transport-copy span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.studio-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.92), rgba(2, 6, 23, 0.98)),
    #020617;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.studio-editor__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.studio-editor__title {
  color: #f8fafc;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.3;
}

.studio-editor__caption {
  margin-top: 4px;
  color: rgba(148, 163, 184, 0.86);
  font-size: 12px;
  line-height: 1.6;
}

.studio-editor__toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.studio-editor__zoom-controls {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.studio-editor__toolbar-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  padding: 0 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  background: rgba(30, 41, 59, 0.9);
  color: #e2e8f0;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.studio-editor__toolbar-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.studio-editor__zoom-label {
  min-width: 44px;
  color: rgba(191, 219, 254, 0.92);
  font-size: 12px;
  font-weight: 700;
  text-align: center;
}

.studio-editor__grid {
  display: grid;
  gap: 0;
  min-width: 0;
}

.studio-editor__timeline-shell {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
  min-width: 0;
}

.studio-editor__timeline-labels,
.studio-editor__timeline-body-shell {
  display: grid;
  gap: 0;
  min-width: 0;
}

.studio-editor__timeline-body-shell {
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}

.studio-editor__timeline-scroll-shell {
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}

.studio-editor__timeline-canvas {
  position: relative;
}

.studio-editor__row {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
  min-width: 0;
}

.studio-editor__track-label {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 24px;
  align-items: center;
  gap: 6px;
  min-height: 56px;
  padding-right: 10px;
  box-sizing: border-box;
  overflow: visible;
  color: rgba(191, 219, 254, 0.84);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.studio-editor__track-label--ghost {
  color: rgba(148, 163, 184, 0.84);
}

.studio-editor__track-label--video {
  min-height: 92px;
}

.studio-editor__track-label--audio {
  min-height: 72px;
}

.studio-editor__track-label--with-control {
  position: relative;
}

.studio-editor__track-label.is-disabled {
  color: rgba(148, 163, 184, 0.66);
}

.studio-editor__track-label.is-muted .studio-editor__track-label-text {
  color: #fda4af;
}

.studio-editor__track-label-text {
  position: relative;
  z-index: 2;
  min-width: 0;
  white-space: nowrap;
}

.studio-editor__track-audio-panel {
  position: absolute;
  left: calc(100% - 2px);
  top: 50%;
  display: inline-flex;
  align-items: center;
  gap: 0;
  min-width: 108px;
  padding: 8px 10px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.96);
  box-shadow:
    inset 0 0 0 1px rgba(148, 163, 184, 0.14),
    0 14px 28px rgba(2, 6, 23, 0.28);
  opacity: 0;
  pointer-events: none;
  transform: translateY(-50%) translateX(-6px);
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
  z-index: 8;
}

.studio-editor__track-audio-panel::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: -12px;
  width: 14px;
}

.studio-editor__track-label--with-control:hover .studio-editor__track-audio-panel,
.studio-editor__track-label--with-control:focus-within .studio-editor__track-audio-panel {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(-50%) translateX(0);
}

.studio-editor__track-audio-slider {
  width: 88px;
  accent-color: #f97316;
}

.studio-editor__track-audio-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  background: rgba(30, 41, 59, 0.72);
  color: rgba(226, 232, 240, 0.94);
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease;
}

.studio-editor__track-audio-trigger:hover:not(:disabled),
.studio-editor__track-label--with-control:focus-within .studio-editor__track-audio-trigger {
  border-color: rgba(251, 146, 60, 0.4);
  background: rgba(249, 115, 22, 0.14);
}

.studio-editor__track-audio-trigger:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.studio-editor__track-audio-trigger svg {
  width: 14px;
  height: 14px;
  fill: currentColor;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}

.studio-editor__track-audio-wave {
  fill: none;
  opacity: 1;
}

.studio-editor__track-audio-mute {
  fill: none;
  opacity: 0;
}

.studio-editor__track-audio-trigger.is-muted {
  color: #fda4af;
  border-color: rgba(244, 114, 182, 0.28);
  background: rgba(127, 29, 29, 0.22);
}

.studio-editor__track-audio-trigger.is-muted .studio-editor__track-audio-wave {
  opacity: 0;
}

.studio-editor__track-audio-trigger.is-muted .studio-editor__track-audio-mute {
  opacity: 1;
}

.studio-track__ruler,
.studio-track__lane,
.studio-track__line,
.studio-track__audio-body {
  position: relative;
  border-radius: 18px;
  background:
    linear-gradient(180deg, rgba(30, 41, 59, 0.88), rgba(15, 23, 42, 0.96)),
    #0f172a;
  box-shadow:
    inset 0 0 0 1px rgba(148, 163, 184, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.studio-track__ruler {
  min-height: 36px;
  padding: 0;
  overflow: hidden;
}

.studio-track__ruler--editor {
  cursor: pointer;
}

.studio-track__tick {
  position: absolute;
  top: 0;
  bottom: 0;
  display: inline-flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 10px;
  transform: translateX(-50%);
  color: rgba(148, 163, 184, 0.88);
  font-size: 11px;
  line-height: 1;
  white-space: nowrap;
  pointer-events: none;
}

.studio-track__tick::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 1px;
  background: rgba(148, 163, 184, 0.26);
  transform: translateX(-0.5px);
}

.studio-track__tick.is-edge-start {
  left: 0 !important;
  transform: translateX(0);
}

.studio-track__tick.is-edge-end {
  left: 100% !important;
  transform: translateX(-100%);
}

.studio-track__tick.is-edge-start::before {
  left: 0;
  transform: none;
}

.studio-track__tick.is-edge-end::before {
  left: auto;
  right: 0;
  transform: none;
}

.studio-track__lane {
  min-height: 92px;
  padding: 28px 0 10px;
  box-sizing: border-box;
  overflow: hidden;
  flex: none;
  width: 100%;
  min-width: 0;
}

.studio-track__audio-body {
  min-height: 72px;
  padding: 8px 0;
  box-sizing: border-box;
  overflow: hidden;
  flex: none;
  width: 100%;
  min-width: 0;
}

.studio-track__line {
  display: flex;
  align-items: center;
  min-height: 72px;
  padding: 0 14px;
}

.studio-track__lane-grid,
.studio-track__audio-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 3;
}

.studio-track__lane-tick,
.studio-track__audio-tick {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: rgba(148, 163, 184, 0.34);
  transform: translateX(-0.5px);
}

.studio-track__lane-tick.is-edge-start,
.studio-track__audio-tick.is-edge-start {
  left: 0 !important;
  transform: translateX(0);
}

.studio-track__lane-tick.is-edge-end,
.studio-track__audio-tick.is-edge-end {
  left: 100% !important;
  transform: translateX(-1px);
}

.studio-editor__timeline-playhead,
.studio-track__playhead {
  position: absolute;
  width: 2px;
  border-radius: 999px;
  background: linear-gradient(180deg, #fb923c, #f97316);
  box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.16);
  transform: translateX(-50%);
}

.studio-editor__timeline-playhead {
  top: 0;
  bottom: 0;
  z-index: 4;
  cursor: ew-resize;
}

.studio-editor__timeline-playhead::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 18px;
  transform: translateX(-50%);
}

.studio-track__playhead {
  top: 28px;
  bottom: 10px;
  z-index: 4;
}

.studio-track__playhead--ruler {
  top: 0;
  bottom: 0;
  width: 0;
  background: transparent;
  box-shadow: none;
  cursor: ew-resize;
}

.studio-track__playhead--ruler::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 20px;
  transform: translateX(-50%);
}

.studio-track__playhead--ruler span {
  position: absolute;
  top: 6px;
  left: 50%;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: linear-gradient(135deg, #f97316, #fb923c);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.studio-track__playhead--audio {
  top: 6px;
  bottom: 6px;
}

.studio-track__insert-indicator {
  position: absolute;
  top: 28px;
  bottom: 10px;
  width: 2px;
  background: linear-gradient(180deg, #38bdf8, #0ea5e9);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.18);
  border-radius: 999px;
  transform: translateX(-50%);
  z-index: 4;
}

.studio-track__insert-indicator span {
  position: absolute;
  top: -28px;
  left: 50%;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.96);
  color: #eff6ff;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.studio-track__clip {
  position: absolute;
  top: 28px;
  bottom: 10px;
  min-width: 0;
  cursor: grab;
  box-sizing: border-box;
  overflow: visible;
  user-select: none;
  z-index: 2;
  max-width: 100%;
}

.studio-track__clip-surface {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 4px;
  min-width: 0;
  padding: 8px 18px 8px 10px;
  border-radius: 16px;
  background: linear-gradient(
    135deg,
    rgba(30, 41, 59, 0.84),
    rgba(51, 65, 85, 0.88)
  );
  box-shadow:
    inset 0 0 0 1px rgba(148, 163, 184, 0.12),
    0 8px 18px rgba(2, 6, 23, 0.34);
  color: #f8fafc;
  overflow: hidden;
  backdrop-filter: blur(6px);
}

.studio-track__clip.is-dragging {
  opacity: 0.56;
  cursor: grabbing;
}

.studio-track__clip.is-active .studio-track__clip-surface {
  box-shadow:
    inset 0 0 0 1px rgba(251, 146, 60, 0.4),
    0 0 0 2px rgba(249, 115, 22, 0.3),
    0 12px 24px rgba(2, 6, 23, 0.4);
}

.studio-track__clip.is-drop-target .studio-track__clip-surface {
  box-shadow:
    inset 0 0 0 1px rgba(56, 189, 248, 0.4),
    0 0 0 2px rgba(56, 189, 248, 0.26);
}

.studio-track__clip-source {
  display: inline-flex;
  max-width: 100%;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  color: rgba(226, 232, 240, 0.88);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.05em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.studio-track__clip-floating-label {
  position: absolute;
  top: -22px;
  left: 6px;
  right: 22px;
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(226, 232, 240, 0.14);
  color: rgba(226, 232, 240, 0.92);
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
}

.studio-track__clip-title {
  color: #f8fafc;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: normal;
  word-break: break-word;
}

.studio-track__clip.is-compact .studio-track__clip-surface {
  padding-right: 16px;
  justify-content: center;
}

.studio-track__clip.is-compact .studio-track__clip-source {
  font-size: 8px;
}

.studio-track__clip.is-compact .studio-track__clip-title {
  font-size: 11px;
  -webkit-line-clamp: 2;
}

.studio-track__clip.has-floating-label .studio-track__clip-surface {
  justify-content: center;
  gap: 2px;
}

.studio-track__clip.is-condensed .studio-track__clip-surface {
  padding: 8px 14px 8px 8px;
  justify-content: center;
}

.studio-track__clip.has-floating-label .studio-track__clip-title,
.studio-track__clip.is-condensed .studio-track__clip-title {
  -webkit-line-clamp: 1;
}

.studio-track__drop-tail {
  position: absolute;
  top: 28px;
  right: 12px;
  bottom: 10px;
  width: 88px;
  border: 1px dashed rgba(148, 163, 184, 0.4);
  border-radius: 16px;
  color: rgba(148, 163, 184, 0.9);
  font-size: 11px;
  line-height: 1.5;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  background: rgba(15, 23, 42, 0.3);
  z-index: 1;
}

.studio-track__drop-tail.is-active {
  border-color: rgba(56, 189, 248, 0.72);
  background: rgba(14, 165, 233, 0.16);
  color: #bae6fd;
}

.studio-track__audio-segment {
  position: absolute;
  top: 10px;
  bottom: 10px;
  display: inline-flex;
  align-items: center;
  min-width: 0;
  padding: 0 12px;
  border-radius: 14px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  box-sizing: border-box;
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.06),
    0 8px 16px rgba(2, 6, 23, 0.24);
  z-index: 2;
  max-width: 100%;
}

.studio-track__audio-segment-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.studio-track__audio-segment--bgm {
  background: linear-gradient(135deg, #059669, #10b981);
}

.studio-track__audio-segment--voice {
  background: linear-gradient(135deg, #2563eb, #38bdf8);
}

.studio-track__empty {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  color: rgba(148, 163, 184, 0.86);
  font-size: 12px;
  line-height: 1.6;
}

.studio-track__empty--inline {
  position: relative;
  z-index: 1;
  padding-left: 2px;
}

@media (max-width: 1080px) {
  .studio-preview-card__transport-bar,
  .studio-editor__toolbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .studio-preview-card__transport-copy {
    width: 100%;
    text-align: left;
  }
}

@media (max-width: 960px) {
  .studio-preview-card {
    padding: 16px;
  }

  .studio-preview-card__screen {
    width: 100%;
    height: clamp(220px, 56vw, 320px);
  }

  .studio-editor__row,
  .studio-editor__timeline-shell {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .studio-editor__track-label {
    min-height: auto;
  }

  .studio-editor__timeline-labels,
  .studio-editor__timeline-body-shell {
    gap: 8px;
  }

  .studio-editor__track-audio-panel {
    left: 0;
    top: calc(100% + 6px);
    transform: translateY(0);
  }

  .studio-editor__track-audio-panel::before {
    top: -10px;
    bottom: auto;
    left: 0;
    width: 100%;
    height: 10px;
  }

  .studio-editor__track-label--with-control:hover .studio-editor__track-audio-panel,
  .studio-editor__track-label--with-control:focus-within .studio-editor__track-audio-panel {
    transform: translateY(0);
  }
}
</style>
