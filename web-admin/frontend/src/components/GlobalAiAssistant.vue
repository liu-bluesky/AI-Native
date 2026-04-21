<template>
  <div v-if="shouldRender" class="global-ai-assistant">
    <transition name="assistant-panel">
      <section
        v-if="panelOpen"
        class="assistant-shell"
        :class="{ 'assistant-shell--fullscreen': panelFullscreen }"
        data-testid="assistant-shell-panel"
        aria-label="AI 助手弹框"
      >
        <header class="assistant-header">
          <div class="assistant-header__copy">
            <span class="assistant-header__eyebrow">System Monitor</span>
            <h2>系统状态助手</h2>
            <p>{{ headerSummary }}</p>
          </div>

          <div class="assistant-header__actions">
            <el-button
              circle
              text
              :icon="Setting"
              class="assistant-header__toggle"
              :class="{ 'is-active': settingsDialogOpen }"
              :title="settingsDialogOpen ? '关闭语音设置' : '打开语音设置'"
              :aria-label="settingsDialogOpen ? '关闭语音设置' : '打开语音设置'"
              data-testid="assistant-shell-settings-button"
              @click="toggleAssistantSettingsPanel"
            />
            <el-button
              circle
              text
              :icon="Headset"
              :title="autoPlayAssistantSpeechToggleTitle"
              :aria-label="autoPlayAssistantSpeechToggleTitle"
              class="assistant-header__toggle"
              :class="{ 'is-active': autoPlayAssistantSpeech }"
              data-testid="assistant-shell-speech-button"
              @click="toggleAutoPlayAssistantSpeech"
            />
            <el-button
              circle
              text
              :icon="FullScreen"
              class="assistant-header__toggle"
              :class="{ 'is-active': panelFullscreen }"
              :title="panelFullscreen ? '退出全屏' : '全屏展开'"
              :aria-label="panelFullscreen ? '退出全屏' : '全屏展开'"
              data-testid="assistant-shell-fullscreen-button"
              @click="togglePanelFullscreen"
            />
            <el-button
              circle
              text
              :icon="Close"
              title="关闭助手弹框"
              aria-label="关闭助手弹框"
              data-testid="assistant-shell-close-button"
              @click="closeAssistantPanel"
            />
          </div>
        </header>

        <section class="assistant-call-entry" :class="voiceSurfaceStateClass">
          <div class="assistant-call-entry__copy">
            <span class="assistant-call-entry__badge">{{ voiceUiState.label }}</span>
            <strong>实时通话</strong>
            <p>{{ voiceSettingsSummary }}</p>
          </div>
          <div class="assistant-call-entry__actions">
            <el-button
              round
              class="assistant-voice-trigger assistant-call-entry__trigger"
              :class="voiceTriggerStateClass"
              :type="voiceTriggerButtonType"
              :loading="isStoppingVoiceInput"
              :disabled="voiceButtonDisabled"
              :aria-label="`${voiceUiState.label}，${voiceUiState.detail}`"
              :style="voiceTriggerButtonStyle"
              @click="handleVoiceSettingsTrigger"
            >
              <span class="assistant-voice-trigger__body">
                <el-icon class="assistant-voice-trigger__icon"><Microphone /></el-icon>
                <span class="assistant-voice-trigger__label">{{ voiceActionLabel }}</span>
              </span>
            </el-button>
          </div>
        </section>

        <div ref="messageContainerRef" class="assistant-messages">
          <div v-if="bootstrapping" class="assistant-empty">
            <strong>助手初始化中</strong>
            <span>对话会缓存在当前浏览器，并按当前登录账号隔离，退出登录后自动清空。</span>
          </div>

          <div
            v-else-if="errorText"
            class="assistant-empty assistant-empty--error"
          >
            <strong>助手暂时不可用</strong>
            <span>{{ errorText }}</span>
          </div>

          <div v-else-if="!messages.length" class="assistant-empty">
            <strong>对话已就绪</strong>
            <span>当前助手会参考真实系统快照，并恢复当前账号在本浏览器内的临时对话。</span>
          </div>

          <article
            v-for="message in messages"
            :key="message.id"
            class="assistant-message"
            :class="`assistant-message--${message.role}`"
          >
            <div class="assistant-message__meta">
              <span class="assistant-message__role">{{
                roleLabel(message.role)
              }}</span>
              <span>{{
                formatRelativeDateTime(message.created_at || message.time)
              }}</span>
            </div>
            <div class="assistant-message__content">
              {{ message.content || "..." }}
            </div>
            <div
              v-if="
                message.status &&
                message.role === 'assistant' &&
                (message.isStreaming || !message.content)
              "
              class="assistant-message__status"
            >
              {{ message.status }}
            </div>
            <div
              v-if="message.role === 'assistant' && message.content"
              class="assistant-message__actions"
            >
              <button
                type="button"
                class="assistant-message__icon-button"
                :class="{ 'is-active': isSpeakingMessage(message) }"
                :title="isSpeakingMessage(message) ? '暂停播报' : '播放播报'"
                @click="toggleAssistantMessageSpeech(message)"
              >
                <el-icon>
                  <component :is="isSpeakingMessage(message) ? VideoPause : Headset" />
                </el-icon>
              </button>
              <button
                type="button"
                class="assistant-message__icon-button"
                title="复制回复"
                @click="copyAssistantMessage(message)"
              >
                <el-icon><DocumentCopy /></el-icon>
              </button>
            </div>
            <div v-if="message.images.length" class="assistant-message__images">
              <img
                v-for="imageUrl in message.images"
                :key="imageUrl"
                :src="imageUrl"
                alt="assistant artifact"
              />
            </div>
          </article>

          <article
            v-if="shouldShowVoiceDraftMessage"
            class="assistant-message assistant-message--user assistant-message--draft"
          >
            <div class="assistant-message__meta">
              <span class="assistant-message__role">你</span>
              <span>语音输入中</span>
            </div>
            <div class="assistant-message__content">
              {{ voiceConversationDraftText }}
            </div>
            <div class="assistant-message__status">
              识别完成后会自动作为你的消息发送到当前对话
            </div>
          </article>
        </div>

        <div class="assistant-composer assistant-composer--single">
          <section class="assistant-input-card assistant-input-card--typed">
            <div class="assistant-input-card__head">
              <div>
                <span class="assistant-input-card__eyebrow">Text Input</span>
                <h3>手动输入</h3>
                <p>实时通话继续在后台待机，打字消息在这里单独发送。</p>
              </div>
            </div>

            <el-input
              v-model="typedDraftText"
              type="textarea"
              resize="none"
              :autosize="{ minRows: 3, maxRows: panelFullscreen ? 10 : 6 }"
              :maxlength="4000"
              show-word-limit
              :placeholder="composerPlaceholder"
              :disabled="bootstrapping || loading"
              @keydown="handleComposerKeydown"
            />

            <div class="assistant-input-card__footer">
              <span class="assistant-input-card__hint">{{ typedComposerHint }}</span>
              <div class="assistant-input-card__actions">
                <el-button
                  text
                  :disabled="!canClearAssistantConversation"
                  @click="clearAssistantConversation"
                >
                  清空对话
                </el-button>
                <el-button
                  :type="loading ? 'danger' : 'primary'"
                  :disabled="loading ? !canStopCurrentReply : !canSend"
                  @click="loading ? stopCurrentReply() : sendCurrentDraft()"
                >
                  {{ loading ? "停止" : "发送" }}
                </el-button>
              </div>
            </div>
          </section>
        </div>
      </section>
    </transition>

    <el-dialog
      v-model="settingsDialogOpen"
      class="assistant-settings-dialog"
      width="min(720px, calc(100vw - 24px))"
      top="8vh"
      :z-index="3600"
      append-to-body
      destroy-on-close
      title="语音设置"
    >
      <div class="assistant-settings-layout assistant-settings-layout--dialog">
          <section class="assistant-settings-group assistant-settings-group--status">
            <div class="assistant-settings-group__head">
              <div>
                <h4>实时通话状态</h4>
                <p>{{ voiceSettingsSummary }}</p>
              </div>
              <div class="assistant-settings-group__actions assistant-settings-group__actions--hint">
                在主面板中开启或关闭
              </div>
            </div>

            <div class="assistant-voice-live" :class="voiceSurfaceStateClass">
              <div class="assistant-voice-live__meta">
                <span class="assistant-voice-live__badge">{{ voiceUiState.label }}</span>
                <span class="assistant-voice-live__countdown">{{ fabVoiceSubLabel }}</span>
              </div>
              <div class="assistant-voice-live__text">
                {{ voiceDraftPreviewText }}
              </div>
              <div class="assistant-voice-meter assistant-voice-meter--inline">
                <div class="assistant-voice-meter__track">
                  <div
                    class="assistant-voice-meter__fill"
                    :style="{ width: `${voiceMeterPercent}%` }"
                  />
                </div>
                <span class="assistant-voice-meter__text">
                  {{ voiceMeterHint }}
                </span>
              </div>
            </div>

            <div v-if="voiceDeviceWarningText" class="assistant-voice-warning">
              {{ voiceDeviceWarningText }}
            </div>
          </section>

          <section class="assistant-settings-group">
            <div class="assistant-settings-group__head">
              <div>
                <h4>回复播报声音</h4>
                <p>
                  {{
                    backendSpeechPlaybackEnabled
                      ? "当前助手已切到系统级语音播报，音色由系统设置统一控制。"
                      : "从当前浏览器可用的人声里选择一个更顺耳的音色。"
                  }}
                </p>
              </div>
              <div class="assistant-settings-group__actions">
                <el-button
                  v-if="!backendSpeechPlaybackEnabled"
                  text
                  type="primary"
                  :loading="speechVoiceLoading"
                  :disabled="!browserSpeechPlaybackSupported()"
                  @click="refreshSpeechVoiceOptions({ forceRetry: true })"
                >
                  重新读取
                </el-button>
                <el-button
                  v-else
                  text
                  type="primary"
                  :loading="speechRuntimeLoading"
                  @click="fetchSpeechRuntime"
                >
                  刷新配置
                </el-button>
                <el-button
                  text
                  type="primary"
                  :disabled="!assistantSpeechPlaybackSupported()"
                  @click="previewSelectedSpeechVoice"
                >
                  {{ speakingMessageId === SPEECH_PREVIEW_MESSAGE_ID ? "停止试听" : "试听声音" }}
                </el-button>
              </div>
            </div>

            <el-alert
              v-if="backendSpeechPlaybackEnabled"
              title="当前已启用系统级语音播报"
              type="success"
              :closable="false"
              show-icon
            >
              <template #default>
                <div class="assistant-settings-group__alert-body">
                  <div>供应商：{{ speechRuntime.provider_name || speechRuntime.provider_id || "未命名供应商" }}</div>
                  <div>模型：{{ speechRuntime.model_name || "未配置" }}</div>
                  <div>音色：{{ speechRuntime.voice || "未配置" }}</div>
                </div>
              </template>
            </el-alert>

            <el-alert
              v-else-if="browserSpeechPlaybackSupported() && !speechVoiceOptions.length"
              title="当前浏览器还没有返回可用播报声音"
              type="warning"
              :closable="false"
              show-icon
            >
              <template #default>
                <div class="assistant-settings-group__alert-body">
                  <div>这份列表来自浏览器和系统内置语音，不是后台模型配置。</div>
                  <div>可以先点“重新读取”；如果还是为空，请到操作系统里安装或启用中文朗读声音后重开浏览器。</div>
                </div>
              </template>
            </el-alert>

            <el-alert
              v-else-if="!browserSpeechPlaybackSupported()"
              title="当前浏览器暂不支持语音播放设置"
              type="warning"
              :closable="false"
              show-icon
            />

            <template v-else-if="!backendSpeechPlaybackEnabled">
              <el-select
                v-model="selectedSpeechVoiceUri"
                class="assistant-settings-group__select"
                placeholder="选择回复播报声音"
              >
                <el-option
                  label="跟随浏览器推荐中文声音"
                  value=""
                />
                <el-option
                  v-for="item in speechVoiceOptions"
                  :key="item.voiceURI"
                  :label="item.label"
                  :value="item.voiceURI"
                />
              </el-select>
              <div class="assistant-settings-group__desc">
                当前选择：{{ selectedSpeechVoiceLabel }}
              </div>
            </template>
          </section>

          <AssistantVoiceDiagnosticsPanel />
      </div>
    </el-dialog>

    <div class="assistant-fab-shell" :style="assistantFabShellStyle">
      <button
        ref="assistantFabRef"
        type="button"
        class="assistant-fab"
        :class="[fabVoiceStateClass, { 'is-dragging': assistantFabDragging }]"
        :style="fabVoiceStyle"
        @click="handleAssistantFabClick"
        @pointerdown="handleAssistantFabPointerDown"
      >
        <span class="assistant-fab__orbit assistant-fab__orbit--outer" />
        <span class="assistant-fab__orbit assistant-fab__orbit--inner" />
        <span class="assistant-fab__wave assistant-fab__wave--one" />
        <span class="assistant-fab__wave assistant-fab__wave--two" />
        <span class="assistant-fab__pulse" />
        <span class="assistant-fab__meta">
          <span class="assistant-fab__eyebrow">Live Call</span>
          <span class="assistant-fab__label">{{ fabVoiceLabel }}</span>
          <span class="assistant-fab__sub">{{ fabVoiceSubLabel }}</span>
        </span>
        <span class="assistant-fab__meter">
          <span
            class="assistant-fab__meter-fill"
            :style="{ transform: `scaleX(${Math.max(0.08, voiceMeterPercent / 100)})` }"
          />
        </span>
      </button>
    </div>
  </div>
</template>

<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Close,
  DocumentCopy,
  FullScreen,
  Headset,
  Microphone,
  Setting,
  VideoPause,
} from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";

import AssistantVoiceDiagnosticsPanel from "@/components/AssistantVoiceDiagnosticsPanel.vue";
import api from "@/utils/api.js";
import {
  authStateVersion,
  getStoredAuthProfile,
  getStoredToken,
} from "@/utils/auth-storage.js";
import { formatRelativeDateTime } from "@/utils/date.js";
import { hasPermission } from "@/utils/permissions.js";
import {
  ensureAssistantBrowserBridgeInstalled,
  executeAssistantBrowserToolCall,
} from "@/utils/assistant-browser-bridge.js";
import { isEmbeddedDesktopApp } from "@/utils/desktop-app-bridge.js";
import { createGlobalAssistantWsClient } from "@/utils/ws-chat.js";

const FALLBACK_OPEN_WIDTH = 1080;
const GLOBAL_ASSISTANT_STORAGE_PREFIX = "global_ai_assistant.";
const ASSISTANT_CHAT_CACHE_STORAGE_SUFFIX = "chat-cache";
const VOICE_INPUT_DEVICE_STORAGE_SUFFIX = "voice-device-id";
const VOICE_INPUT_DEFAULT_VALUE = "__browser_default__";
const LEGACY_VOICE_INPUT_DEVICE_STORAGE_KEY = "global-ai-assistant-voice-device-id";
const SPEECH_VOICE_STORAGE_SUFFIX = "speech-voice-uri";
const LEGACY_SPEECH_VOICE_STORAGE_KEY = "global-ai-assistant-speech-voice-uri";
const SPEECH_AUTO_PLAY_STORAGE_SUFFIX = "speech-auto-play";
const ASSISTANT_GREETING_SEEN_STORAGE_SUFFIX = "greeting-seen";
const ASSISTANT_FAB_POSITION_STORAGE_SUFFIX = "fab-position";
const SPEECH_PREVIEW_MESSAGE_ID = "__speech_preview__";
const SPEECH_AUDIO_CACHE_LIMIT = 24;
const SPEECH_VOICE_RETRY_DELAY_MS = 700;
const SPEECH_VOICE_MAX_RETRIES = 6;
const SYSTEM_CONFIG_UPDATED_EVENT = "system-config-updated";
const ASSISTANT_FAB_DRAG_THRESHOLD_PX = 6;
const ASSISTANT_FAB_DESKTOP_OFFSET_PX = 20;
const ASSISTANT_FAB_MOBILE_OFFSET_PX = 12;
const ASSISTANT_FAB_DESKTOP_SIZE_PX = 132;
const ASSISTANT_FAB_MOBILE_SIZE_PX = 108;
const HIDDEN_PATHS = new Set(["/login"]);
const DIRECT_ROUTE_COMMANDS = [
  {
    path: "/market",
    label: "市场",
    aliases: ["市场", "市场页", "能力市场", "官网市场", "官网市场页"],
  },
];

const route = useRoute();
const router = useRouter();

const messages = ref([]);
const currentChatSessionId = ref("");
const bootstrapping = ref(false);
const loading = ref(false);
const errorText = ref("");
const wsClient = ref(null);
const wsConnected = ref(false);
const panelOpen = ref(resolveInitialPanelOpen());
const panelFullscreen = ref(false);
const settingsDialogOpen = ref(false);
const typedDraftText = ref("");
const voiceDraftText = ref("");
const messageContainerRef = ref(null);
const assistantFabRef = ref(null);
const speakingMessageId = ref("");
const speechVoiceOptions = ref([]);
const selectedSpeechVoiceUri = ref("");
const autoPlayAssistantSpeech = ref(false);
const speechVoiceLoading = ref(false);
const isListening = ref(false);
const voiceStatusText = ref("");
const voiceUiStage = ref("idle");
const recognizedVoiceDraft = ref("");
const liveVoiceTranscript = ref("");
const confirmedVoiceSegments = ref([]);
const voiceRuntime = ref({
  enabled: false,
  available: false,
  mode: "",
  reason: "",
  greeting_enabled: false,
  greeting_text: DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
  transcription_prompt: DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
  wake_phrase: "你好助手",
  idle_timeout_sec: 5,
});
const voiceRuntimeLoading = ref(false);
const speechRuntime = ref({
  enabled: false,
  available: false,
  mode: "",
  reason: "",
  provider_id: "",
  provider_name: "",
  model_name: "",
  voice: "",
  greeting_audio_available: false,
  greeting_audio_signature: "",
});
const speechRuntimeLoading = ref(false);
const voiceInputDevices = ref([]);
const selectedVoiceInputDeviceId = ref(VOICE_INPUT_DEFAULT_VALUE);
const voiceMeterLevel = ref(0);
const voiceAutoSendCountdownMs = ref(0);
const voiceGreetingStarting = ref(false);
const voiceRequestedStartMode = ref("standby");
const voiceWakeState = ref("standby");
const voiceWakeScanBuffer = ref("");
const voiceStandbyHeardText = ref("");
const voiceDeviceRefreshLoading = ref(false);
const voiceActiveTrackInfo = ref(createEmptyVoiceTrackInfo());
const voiceTrackDetailsExpanded = ref(false);
const voiceListeningSuspendedBySpeech = ref(false);
const activePendingRequestId = ref("");
const assistantFabPosition = ref(null);
const assistantFabDragging = ref(false);
const suppressAssistantFabClick = ref(false);

const pendingRequests = new Map();
let mediaStream = null;
let voiceAudioContext = null;
let voiceSourceNode = null;
let voiceProcessorNode = null;
let voiceMuteNode = null;
let voiceFlushTimer = null;
let voiceCapturedFrames = [];
let voiceCapturedSampleCount = 0;
let voiceObservedSampleCount = 0;
let voiceDetectedPeakLevel = 0;
let voiceDetectedSpeechFrameCount = 0;
let voiceVadPreRollFrames = [];
let voiceVadPreRollSampleCount = 0;
let voiceVadActiveFrames = [];
let voiceVadActiveSampleCount = 0;
let voiceVadSpeechCandidateCount = 0;
let voiceVadSilenceFrameCount = 0;
let voiceVadNoiseFloor = 0.003;
let voiceTranscriptionQueue = [];
let voiceTranscriptionProcessing = false;
let voiceTranscriptionEpoch = 0;
const isStoppingVoiceInput = ref(false);
let voiceStreamRequestId = "";
let voiceStreamChunkIndex = 0;
const voicePendingRequestIds = new Set();
let voiceMeterDecayTimer = null;
let voiceAutoSendTimer = null;
let voiceAutoSendCountdownTimer = null;
let voiceStartAfterGreetingTimer = null;
let shouldAutoSubmitVoiceAfterStop = false;
let speechUtterance = null;
let speechVoiceRetryTimer = null;
let speechVoiceRetryCount = 0;
let speechAudioElement = null;
let speechAudioObjectUrl = "";
let activeSpeechPlaybackInterrupt = null;
let speechPlaybackToken = 0;
let speechQueueProcessing = false;
let speechSegmentQueue = [];
let voiceListeningResumeMode = "standby";
let pendingGreetingMessageId = "";
let hasAssistantInteractionGesture = false;
let assistantFabPointerId = null;
let assistantFabDragOffsetX = 0;
let assistantFabDragOffsetY = 0;
let assistantFabDragStartX = 0;
let assistantFabDragStartY = 0;
let assistantFabDidMove = false;
let assistantFabResizeRafId = 0;
const speechAudioBlobCache = new Map();
const speechAudioPendingRequests = new Map();
const speechStreamingProgress = new Map();
const suppressedAutoPlayMessageIds = new Set();
const globalAssistantEnabled = ref(true);
const VOICE_TARGET_SAMPLE_RATE = 16000;
const VOICE_FLUSH_INTERVAL_MS = 180;
const VOICE_MIN_CHUNK_MS = 220;
const VOICE_SPEECH_PEAK_THRESHOLD = 0.01;
const VOICE_LOW_VOLUME_PEAK_THRESHOLD = 0.006;
const VOICE_SAMPLE_NOISE_GATE_THRESHOLD = 0.008;
const VOICE_NORMALIZE_MAX_GAIN = 3;
const VOICE_MIN_FINALIZE_MS = 240;
const VOICE_AUTO_SEND_IDLE_MS = 5000;
const VOICE_VAD_PREROLL_MS = 260;
const VOICE_VAD_START_FRAMES = 2;
const VOICE_VAD_END_SILENCE_MS = 720;
const VOICE_VAD_MIN_UTTERANCE_MS = 420;
const VOICE_VAD_MAX_UTTERANCE_MS = 12000;
const VOICE_VAD_MIN_RMS_THRESHOLD = 0.0095;
const VOICE_VAD_CONTINUE_RMS_THRESHOLD = 0.0065;
const DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT =
  "你好，我是系统状态助手。我会默认保持实时通话，随时帮你观察当前页面、系统状态和功能是否可用。";
const DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT =
  "请严格逐字转写用户原话，只输出识别到的中文文本；不要补充、不要改写、不要总结、不要猜测、不要重复上一句；听不清就留空。";

const normalizedRoutePath = computed(() => {
  const hashPath = String(window.location.hash || "")
    .replace(/^#/, "")
    .trim();
  const routePath = String(route.path || "").trim();
  if (hashPath && hashPath !== "/") {
    return hashPath;
  }
  return routePath;
});
const currentRouteLabel = computed(
  () =>
    String(route.meta?.title || route.name || route.path || "/").trim() || "/",
);
const hasRecognizedVoiceDraft = computed(() =>
  Boolean(String(recognizedVoiceDraft.value || "").trim()),
);
const voiceRuntimeAvailable = computed(() =>
  Boolean(voiceRuntime.value?.available),
);
const voiceGreetingEnabled = computed(
  () => voiceRuntime.value?.greeting_enabled !== false,
);
const voiceGreetingText = computed(
  () =>
    String(
      voiceRuntime.value?.greeting_text || DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
    ).trim() || DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
);
const voiceTranscriptionPrompt = computed(
  () =>
    String(
      voiceRuntime.value?.transcription_prompt ||
        DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
    ).trim() || DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
);
const voiceWakePhrase = computed(
  () => String(voiceRuntime.value?.wake_phrase || "你好助手").trim() || "你好助手",
);
const voiceIdleTimeoutMs = computed(() => {
  const timeoutSec = Number(voiceRuntime.value?.idle_timeout_sec || 5) || 5;
  return Math.max(3000, Math.min(30000, timeoutSec * 1000));
});
const speechRuntimeAvailable = computed(() =>
  Boolean(speechRuntime.value?.available),
);
const backendSpeechPlaybackEnabled = computed(
  () => speechRuntimeAvailable.value && speechRuntime.value?.mode === "backend",
);
const speechRuntimeCacheSignature = computed(() =>
  [
    String(speechRuntime.value?.provider_id || "").trim(),
    String(speechRuntime.value?.model_name || "").trim(),
    String(speechRuntime.value?.voice || "").trim(),
  ].join("::"),
);
const greetingAudioCacheSignature = computed(() =>
  [
    speechRuntimeCacheSignature.value,
    String(speechRuntime.value?.greeting_audio_signature || "").trim(),
  ].join("::"),
);
const selectedVoiceInputDeviceLabel = computed(() => {
  if (selectedVoiceInputDeviceId.value === VOICE_INPUT_DEFAULT_VALUE) {
    return "跟随浏览器默认设备";
  }
  const device = voiceInputDevices.value.find(
    (item) => item.deviceId === selectedVoiceInputDeviceId.value,
  );
  if (device) return device.label;
  return "跟随浏览器默认设备";
});
const voiceDeviceWarningText = computed(() => {
  const label = String(
    voiceActiveTrackInfo.value?.label || selectedVoiceInputDeviceLabel.value || "",
  ).trim();
  if (!label) return "";
  const suspiciousVirtualDevice = /(virtual|oray|loopback|blackhole|soundflower|vb-audio|aggregate)/i;
  if (suspiciousVirtualDevice.test(label)) {
    return "当前浏览器正在使用虚拟音频输入，不是耳机麦克风。请先到系统声音输入或关闭远控/虚拟声卡后再重试。";
  }
  if (voiceInputDevices.value.length === 1) {
    return "浏览器当前只检测到一个输入设备。若你正在使用耳机麦克风，请先到系统里切换默认输入后刷新页面。";
  }
  return "";
});
const voiceMeterPercent = computed(() =>
  resolveVoiceMeterPercent(voiceMeterLevel.value),
);
const voiceMeterHint = computed(() => {
  if (isListening.value) {
    if (voiceMeterLevel.value >= 0.16) return "语音输入正常";
    if (voiceMeterLevel.value >= 0.05) return "已检测到声音，仍可再靠近一些";
    return "浏览器已开始录音，请对着当前设备说话";
  }
  if (!voiceInputDevices.value.length) {
    return "浏览器暂未返回可用输入设备";
  }
  return "录音前先确认设备和音量条是否正常";
});
const voiceLiveFeedback = computed(() => {
  if (!isListening.value) return "";
  if (voiceMeterLevel.value >= 0.18) return "声音清晰，继续说";
  if (voiceMeterLevel.value >= 0.08) return "已经听到你了，再稳定一些";
  if (voiceMeterLevel.value >= 0.03) return "声音偏小，再靠近麦克风";
  return "几乎没有听到声音，请直接对着麦克风说话";
});
const voiceActiveTrackSummaryRows = computed(() => {
  const info = voiceActiveTrackInfo.value || {};
  return [
    { label: "实际音轨", value: String(info.label || "").trim() },
    { label: "deviceId", value: String(info.deviceId || "").trim() },
    { label: "groupId", value: String(info.groupId || "").trim() },
    {
      label: "采样率",
      value: info.sampleRate ? `${info.sampleRate} Hz` : "",
    },
    {
      label: "声道数",
      value: info.channelCount ? String(info.channelCount) : "",
    },
    {
      label: "降噪/回声消除",
      value: resolveVoiceTrackProcessingLabel(info),
    },
  ].filter((item) => String(item.value || "").trim());
});
const voiceActiveTrackCompactRows = computed(() =>
  voiceActiveTrackSummaryRows.value.filter((item) =>
    ["实际音轨", "采样率", "声道数"].includes(item.label),
  ),
);
const voiceActiveTrackDetailRows = computed(() =>
  voiceActiveTrackSummaryRows.value.filter(
    (item) => !["实际音轨", "采样率", "声道数"].includes(item.label),
  ),
);
const composerPlaceholder = computed(() =>
  "输入问题，回车发送",
);
const typedComposerHint = computed(() => {
  if (isVoiceExecutionPending.value) {
    return "当前指令执行中，请等待完成后再说下一句";
  }
  if (loading.value) return "AI 正在回复中";
  return isListening.value
    ? `实时通话保持待机中，说“${voiceWakePhrase.value}”即可唤醒`
    : "Enter 发送，Shift + Enter 换行";
});
const isVoiceExecutionPending = computed(() => isListening.value && loading.value);
const hasVoiceDraft = computed(() =>
  Boolean(String(voiceDraftText.value || "").trim()),
);
const voiceConversationDraftText = computed(
  () => String(voiceDraftText.value || "").trim(),
);
const shouldShowVoiceDraftMessage = computed(
  () =>
    Boolean(voiceConversationDraftText.value) &&
    (isListening.value || voiceUiStage.value === "recognizing"),
);
const voiceDraftPreviewText = computed(() => {
  if (hasVoiceDraft.value) return String(voiceDraftText.value || "").trim();
  if (voiceGreetingStarting.value) {
    return "欢迎语播放中，结束后会自动进入实时通话待机。";
  }
  if (isVoiceExecutionPending.value) {
    return (
      String(voiceStatusText.value || "").trim() ||
      "当前指令执行中，请等待完成后再说下一句。"
    );
  }
  if (isListening.value && voiceWakeState.value === "active") {
    return "已唤醒，请直接说完整指令；一句结束后会自动识别并发送。";
  }
  if (isListening.value) {
    return `实时通话待机中，说“${voiceWakePhrase.value}”即可唤醒。`;
  }
  if (voiceUiStage.value === "recognizing") {
    return "正在整理最后一段语音，请稍候。";
  }
  return "实时通话已关闭，可在上方重新开启。";
});
const voiceAutoSendHint = computed(() => {
  if (!voiceAutoSendCountdownMs.value || voiceWakeState.value !== "active") return "";
  return `${Math.max(1, Math.ceil(voiceAutoSendCountdownMs.value / 1000))}s 后回待机`;
});
const voiceDeviceSummary = computed(() => {
  const activeTrackLabel = String(voiceActiveTrackInfo.value?.label || "").trim();
  if (activeTrackLabel) return `当前设备：${activeTrackLabel}`;
  return `当前设备：${selectedVoiceInputDeviceLabel.value}`;
});
const voiceSurfaceStateClass = computed(() => ({
  "is-listening": voiceUiStage.value === "listening",
  "is-processing":
    isVoiceExecutionPending.value ||
    voiceUiStage.value === "requesting" ||
    voiceUiStage.value === "stopping" ||
    voiceUiStage.value === "recognizing",
  "is-error": voiceUiStage.value === "error",
  "is-ready": voiceUiStage.value === "ready",
}));
const fabVoiceStateClass = computed(() => ({
  "is-listening": voiceUiStage.value === "listening",
  "is-processing":
    isVoiceExecutionPending.value ||
    voiceUiStage.value === "requesting" ||
    voiceUiStage.value === "stopping" ||
    voiceUiStage.value === "recognizing",
  "is-error": voiceUiStage.value === "error",
  "is-loud": isListening.value && voiceMeterLevel.value >= 0.18,
  "is-medium":
    isListening.value &&
    voiceMeterLevel.value >= 0.08 &&
    voiceMeterLevel.value < 0.18,
  "is-quiet": isListening.value && voiceMeterLevel.value < 0.08,
}));
const fabVoiceStyle = computed(() => {
  const normalized = Math.max(
    0.08,
    Math.min(1, Number(voiceMeterPercent.value || 0) / 100),
  );
  return {
    "--assistant-fab-level": normalized.toFixed(3),
  };
});
const assistantFabShellStyle = computed(() => {
  if (!assistantFabPosition.value) return {};
  return {
    left: `${assistantFabPosition.value.x}px`,
    top: `${assistantFabPosition.value.y}px`,
    right: "auto",
    bottom: "auto",
  };
});
const fabVoiceLabel = computed(() => {
  if (voiceGreetingStarting.value) return "欢迎中";
  if (isStoppingVoiceInput.value) return "关闭中";
  if (voiceUiStage.value === "error") return "重连通话";
  if (isVoiceExecutionPending.value) return "执行中";
  if (isListening.value && voiceWakeState.value === "active") return "通话中";
  if (isListening.value) return "待唤醒";
  return "打开助手";
});
const fabVoiceSubLabel = computed(() => {
  if (voiceGreetingStarting.value) {
    return "欢迎语播放后会自动开始实时通话";
  }
  if (isVoiceExecutionPending.value) {
    return "当前指令执行中，完成后会自动回到待机";
  }
  if (isListening.value && voiceWakeState.value === "active") {
    return voiceAutoSendHint.value || `一句说完自动发送，${voiceIdleTimeoutMs.value / 1000}s 无新内容后待机`;
  }
  if (isListening.value) {
    return `说“${voiceWakePhrase.value}”唤醒`;
  }
  if (voiceGreetingText.value && !loadGreetingSeenState()) {
    return "打开面板后可在设置里开始实时通话";
  }
  return "点击展开助手弹框";
});
const voiceButtonDisabled = computed(() => {
  if (bootstrapping.value || voiceRuntimeLoading.value) return true;
  if (voiceGreetingStarting.value) return true;
  if (isStoppingVoiceInput.value) return true;
  if (isListening.value) return false;
  if (!browserAudioCaptureSupported()) return true;
  return !voiceRuntimeAvailable.value;
});
const voiceTriggerButtonType = computed(() => {
  if (voiceGreetingStarting.value) return "warning";
  if (isListening.value) return "danger";
  if (
    voiceUiStage.value === "requesting" ||
    voiceUiStage.value === "stopping" ||
    voiceUiStage.value === "recognizing"
  ) {
    return "warning";
  }
  if (voiceUiStage.value === "ready") return "success";
  return "default";
});
const voiceActionLabel = computed(() => {
  if (voiceRuntimeLoading.value) return "加载语音";
  if (voiceGreetingStarting.value) return "播放欢迎语";
  if (voiceUiStage.value === "requesting") return "准备录音";
  if (isListening.value) return "关闭实时通话";
  if (isStoppingVoiceInput.value || voiceUiStage.value === "stopping")
    return "关闭中";
  if (voiceUiStage.value === "recognizing") return "识别中";
  if (voiceUiStage.value === "ready") return "开启实时通话";
  if (voiceUiStage.value === "error") return "重试通话";
  if (!browserAudioCaptureSupported()) return "设备不支持";
  if (!voiceRuntimeAvailable.value) return "语音未开放";
  return "开启实时通话";
});
const voiceTriggerStateClass = computed(() => ({
  "is-listening": voiceUiStage.value === "listening",
  "is-processing":
    voiceUiStage.value === "requesting" ||
    voiceUiStage.value === "stopping" ||
    voiceUiStage.value === "recognizing",
  "is-error": voiceUiStage.value === "error",
}));
const voiceTriggerButtonStyle = computed(() => {
  if (voiceUiStage.value !== "listening") return {};
  const normalized = Math.max(
    0,
    Math.min(1, Number(voiceMeterPercent.value || 0) / 100),
  );
  return {
    "--assistant-voice-trigger-level": normalized.toFixed(3),
    "--assistant-voice-trigger-glow": (0.2 + normalized * 0.55).toFixed(3),
  };
});
const voiceUiState = computed(() => {
  if (voiceRuntimeLoading.value) {
    return {
      tone: "processing",
      label: "正在加载语音",
      detail: "正在读取当前账号的语音输入能力。",
    };
  }
  if (voiceGreetingStarting.value) {
    return {
      tone: "processing",
      label: "欢迎语播放中",
      detail: "欢迎语结束后会自动开始实时通话。",
    };
  }
  if (!browserAudioCaptureSupported()) {
    return {
      tone: "warning",
      label: "当前设备不支持录音",
      detail: "请改用支持麦克风采集的浏览器或设备。",
    };
  }
  if (!voiceRuntimeAvailable.value) {
    return {
      tone: "warning",
      label: "语音输入未开放",
      detail: String(
        voiceRuntime.value?.reason || "当前账号暂时不能使用语音输入。",
      ).trim(),
    };
  }
  if (voiceUiStage.value === "requesting") {
    return {
      tone: "processing",
      label: "正在准备录音",
      detail: "请留意浏览器权限弹窗，并允许访问麦克风。",
    };
  }
  if (voiceUiStage.value === "listening") {
    if (isVoiceExecutionPending.value) {
      return {
        tone: "processing",
        label: "执行中",
        detail:
          String(voiceStatusText.value || "").trim() ||
          "当前指令执行中，请等待完成后再说下一句。",
      };
    }
    if (voiceWakeState.value === "active") {
      return {
        tone: "recording",
        label: "实时通话中",
        detail:
          voiceAutoSendHint.value ||
          "请直接说完整一句，结束后会自动识别并发送。",
      };
    }
    return {
      tone: "recording",
      label: "待机监听中",
      detail: `说“${voiceWakePhrase.value}”即可唤醒。`,
    };
  }
  if (voiceUiStage.value === "stopping") {
    return {
      tone: "processing",
      label: "正在结束录音",
      detail: "已停止收音，正在提交最后一段语音。",
    };
  }
  if (voiceUiStage.value === "recognizing") {
    return {
      tone: "processing",
      label: "正在识别",
      detail:
        String(voiceStatusText.value || "").trim() || "正在整理你的语音内容。",
    };
  }
  if (voiceUiStage.value === "ready") {
    return {
      tone: "success",
      label: "识别完成",
      detail:
        String(voiceStatusText.value || "").trim() || "文字已准备好，将直接进入发送流程。",
    };
  }
  if (voiceUiStage.value === "error") {
    return {
      tone: "danger",
      label: "录音失败",
      detail:
        String(voiceStatusText.value || "").trim() || "请检查麦克风权限后重试。",
    };
  }
  return {
    tone: "idle",
    label: "待开始",
    detail:
      String(voiceStatusText.value || "").trim() ||
      "点击开启实时通话后，助手会保持后台待机监听。",
  };
});

const shouldRender = computed(() => {
  authStateVersion.value;
  if (!getStoredToken()) return false;
  if (isEmbeddedDesktopApp()) return false;
  if (HIDDEN_PATHS.has(normalizedRoutePath.value)) return false;
  if (!globalAssistantEnabled.value) return false;
  return hasPermission("menu.ai.chat");
});

const canSend = computed(() => {
  if (bootstrapping.value || loading.value || isStoppingVoiceInput.value) {
    return false;
  }
  return Boolean(String(typedDraftText.value || "").trim());
});

const canStopCurrentReply = computed(() => {
  if (!loading.value) return false;
  return Boolean(String(activePendingRequestId.value || "").trim());
});

const headerSummary = computed(() => {
  if (voiceStatusText.value) {
    return `${currentRouteLabel.value} · ${voiceStatusText.value}`;
  }
  if (
    voiceRuntime.value?.enabled &&
    !voiceRuntimeAvailable.value &&
    voiceRuntime.value?.reason
  ) {
    return `${currentRouteLabel.value} · ${voiceRuntime.value.reason}`;
  }
  if (loading.value) {
    return `${currentRouteLabel.value} · 正在结合实时快照分析系统状态。`;
  }
  if (isListening.value && voiceWakeState.value === "active") {
    return `${currentRouteLabel.value} · 实时通话已唤醒，说完整一句后会自动识别并发送。`;
  }
  if (isListening.value) {
    return `${currentRouteLabel.value} · 实时通话待机中，说“${voiceWakePhrase.value}”即可唤醒。`;
  }
  if (wsConnected.value) {
    return `${currentRouteLabel.value} · 当前对话仅缓存在本浏览器当前账号下，退出登录自动清空。`;
  }
  return `${currentRouteLabel.value} · 已启用浏览器本地临时缓存。`;
});
const voiceSettingsSummary = computed(() => {
  if (!voiceRuntimeAvailable.value) {
    return String(voiceRuntime.value?.reason || "当前账号暂时不能使用实时通话。").trim();
  }
  if (voiceGreetingStarting.value) {
    return "正在播放欢迎语，结束后会自动开始实时通话。";
  }
  if (isVoiceExecutionPending.value) {
    return "当前指令执行中，完成后会自动回到待机监听。";
  }
  if (isListening.value && voiceWakeState.value === "active") {
    return `当前已唤醒，说完整一句后自动发送；${voiceIdleTimeoutMs.value / 1000}s 无新内容后回待机。`;
  }
  if (isListening.value) {
    return `当前处于待机监听状态，说“${voiceWakePhrase.value}”即可开始新指令。`;
  }
  return "当前实时通话已关闭，可在这里重新开启。";
});
const selectedSpeechVoiceLabel = computed(() => {
  if (backendSpeechPlaybackEnabled.value) {
    const providerName = String(speechRuntime.value?.provider_name || "系统配置").trim();
    const modelName = String(speechRuntime.value?.model_name || "").trim();
    const voice = String(speechRuntime.value?.voice || "").trim();
    return [providerName, modelName, voice].filter(Boolean).join(" · ") || "系统配置播报音色";
  }
  const selected = speechVoiceOptions.value.find(
    (item) => item.voiceURI === selectedSpeechVoiceUri.value,
  );
  if (selected) return selected.label;
  return "跟随浏览器推荐中文声音";
});
const autoPlayAssistantSpeechToggleTitle = computed(() =>
  autoPlayAssistantSpeech.value ? "点击关闭回复自动播报" : "点击开启回复自动播报",
);
const canClearAssistantConversation = computed(() =>
  Boolean(
    messages.value.length ||
      String(typedDraftText.value || "").trim() ||
      String(voiceDraftText.value || "").trim() ||
      String(currentChatSessionId.value || "").trim(),
  ),
);

function resolveAssistantStorageScope() {
  if (typeof window === "undefined") return "";
  const profile = getStoredAuthProfile();
  const username = String(profile?.username || "").trim().toLowerCase();
  if (!username) return "";
  return encodeURIComponent(username);
}

function buildAssistantStorageKey(suffix) {
  const scope = resolveAssistantStorageScope();
  const normalizedSuffix = String(suffix || "").trim();
  if (!scope || !normalizedSuffix) return "";
  return `${GLOBAL_ASSISTANT_STORAGE_PREFIX}${scope}.${normalizedSuffix}`;
}

function loadAssistantStorageValue(suffix, legacyKey = "") {
  if (typeof window === "undefined") return "";
  const storageKey = buildAssistantStorageKey(suffix);
  const scopedValue = storageKey
    ? String(window.localStorage?.getItem(storageKey) || "").trim()
    : "";
  if (scopedValue) return scopedValue;
  if (!legacyKey) return "";
  return String(window.localStorage?.getItem(legacyKey) || "").trim();
}

function persistAssistantStorageValue(suffix, value, legacyKey = "") {
  if (typeof window === "undefined") return;
  const storageKey = buildAssistantStorageKey(suffix);
  const normalized = String(value || "").trim();
  if (legacyKey) {
    window.localStorage?.removeItem(legacyKey);
  }
  if (!storageKey) return;
  if (!normalized) {
    window.localStorage?.removeItem(storageKey);
    return;
  }
  window.localStorage?.setItem(storageKey, normalized);
}

function removeAssistantStorageValue(suffix, legacyKey = "") {
  if (typeof window === "undefined") return;
  const storageKey = buildAssistantStorageKey(suffix);
  if (legacyKey) {
    window.localStorage?.removeItem(legacyKey);
  }
  if (!storageKey) return;
  window.localStorage?.removeItem(storageKey);
}

function resolveAssistantFabViewportOffset() {
  if (typeof window === "undefined") return ASSISTANT_FAB_DESKTOP_OFFSET_PX;
  return window.innerWidth <= 960
    ? ASSISTANT_FAB_MOBILE_OFFSET_PX
    : ASSISTANT_FAB_DESKTOP_OFFSET_PX;
}

function resolveAssistantFabSize(rect = null) {
  const width =
    Number(rect?.width) ||
    (typeof window !== "undefined" && window.innerWidth <= 960
      ? ASSISTANT_FAB_MOBILE_SIZE_PX
      : ASSISTANT_FAB_DESKTOP_SIZE_PX);
  const height =
    Number(rect?.height) ||
    (typeof window !== "undefined" && window.innerWidth <= 960
      ? ASSISTANT_FAB_MOBILE_SIZE_PX
      : ASSISTANT_FAB_DESKTOP_SIZE_PX);
  return {
    width,
    height,
  };
}

function clampAssistantFabPosition(position, rect = null) {
  if (typeof window === "undefined") return { x: 0, y: 0 };
  const offset = resolveAssistantFabViewportOffset();
  const { width, height } = resolveAssistantFabSize(rect);
  const maxX = Math.max(offset, window.innerWidth - width - offset);
  const maxY = Math.max(offset, window.innerHeight - height - offset);
  return {
    x: Math.min(Math.max(Number(position?.x) || 0, offset), maxX),
    y: Math.min(Math.max(Number(position?.y) || 0, offset), maxY),
  };
}

function resolveDefaultAssistantFabPosition(rect = null) {
  if (typeof window === "undefined") return { x: 0, y: 0 };
  const offset = resolveAssistantFabViewportOffset();
  const { width, height } = resolveAssistantFabSize(rect);
  return {
    x: Math.max(offset, window.innerWidth - width - offset),
    y: Math.max(offset, window.innerHeight - height - offset),
  };
}

function loadStoredAssistantFabPosition() {
  const rawValue = loadAssistantStorageValue(ASSISTANT_FAB_POSITION_STORAGE_SUFFIX);
  if (!rawValue) return null;
  try {
    const parsed = JSON.parse(rawValue);
    const x = Number(parsed?.x);
    const y = Number(parsed?.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return { x, y };
  } catch {
    return null;
  }
}

function persistAssistantFabPosition(position) {
  if (!position) {
    removeAssistantStorageValue(ASSISTANT_FAB_POSITION_STORAGE_SUFFIX);
    return;
  }
  persistAssistantStorageValue(
    ASSISTANT_FAB_POSITION_STORAGE_SUFFIX,
    JSON.stringify({
      x: Math.round(Number(position.x) || 0),
      y: Math.round(Number(position.y) || 0),
    }),
  );
}

function syncAssistantFabPosition({ preferStored = false } = {}) {
  if (typeof window === "undefined") return;
  const rect = assistantFabRef.value?.getBoundingClientRect?.() || null;
  const basePosition =
    (preferStored ? loadStoredAssistantFabPosition() : null) ||
    assistantFabPosition.value ||
    resolveDefaultAssistantFabPosition(rect);
  assistantFabPosition.value = clampAssistantFabPosition(basePosition, rect);
}

function loadGreetingSeenState() {
  if (typeof window === "undefined") return false;
  const storageKey = buildAssistantStorageKey(
    ASSISTANT_GREETING_SEEN_STORAGE_SUFFIX,
  );
  if (!storageKey) return false;
  return window.sessionStorage?.getItem(storageKey) === "1";
}

function persistGreetingSeenState(value) {
  if (typeof window === "undefined") return;
  const storageKey = buildAssistantStorageKey(
    ASSISTANT_GREETING_SEEN_STORAGE_SUFFIX,
  );
  if (!storageKey) return;
  if (!value) {
    window.sessionStorage?.removeItem(storageKey);
    return;
  }
  window.sessionStorage?.setItem(storageKey, "1");
}

function canAttemptGreetingAutoPlayOnVisit() {
  if (typeof window === "undefined") return false;
  if (hasAssistantInteractionGesture) return true;
  return Boolean(window.navigator?.userActivation?.isActive);
}

function loadAssistantCache() {
  if (typeof window === "undefined") return null;
  const storageKey = buildAssistantStorageKey(ASSISTANT_CHAT_CACHE_STORAGE_SUFFIX);
  if (!storageKey) return null;
  const raw = String(window.localStorage?.getItem(storageKey) || "").trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    window.localStorage?.removeItem(storageKey);
    return null;
  }
}

function persistAssistantCache() {
  if (typeof window === "undefined") return;
  removeAssistantStorageValue(ASSISTANT_CHAT_CACHE_STORAGE_SUFFIX);
}

function restoreAssistantCache(payload) {
  void payload;
}

function resetAssistantConversationState() {
  stopAssistantSpeech();
  clearSpeechAudioCache();
  cancelActiveVoiceStream();
  teardownAudioProcessingGraph();
  stopMediaStream();
  rejectPendingRequests("当前对话已清空");
  disconnectWs("conversation-cleared");
  loading.value = false;
  errorText.value = "";
  pendingGreetingMessageId = "";
  messages.value = [];
  currentChatSessionId.value = "";
  typedDraftText.value = "";
  settingsDialogOpen.value = false;
  resetVoiceCapture();
}

function replayGreetingAfterConversationCleared() {
  persistGreetingSeenState(false);
  const greetingText = voiceGreetingText.value;
  if (!voiceGreetingEnabled.value || !greetingText) {
    return;
  }
  appendAssistantGreetingMessage(greetingText, {
    playImmediately: assistantSpeechPlaybackSupported(),
  });
  persistGreetingSeenState(true);
}

async function clearAssistantConversation() {
  if (!canClearAssistantConversation.value) return;
  try {
    await ElMessageBox.confirm(
      "确认清空当前 AI 助手临时对话记录吗？当前浏览器内该账号的助手草稿与会话将一并清空。",
      "清空对话",
      {
        confirmButtonText: "清空",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  resetAssistantConversationState();
  removeAssistantStorageValue(ASSISTANT_CHAT_CACHE_STORAGE_SUFFIX);
  replayGreetingAfterConversationCleared();
  ElMessage.success("AI 助手对话已清空");
}

function resolveInitialPanelOpen() {
  void FALLBACK_OPEN_WIDTH;
  return false;
}

function removeAssistantFabDragListeners() {
  if (typeof window === "undefined") return;
  window.removeEventListener("pointermove", handleAssistantFabPointerMove);
  window.removeEventListener("pointerup", handleAssistantFabPointerUp);
  window.removeEventListener("pointercancel", handleAssistantFabPointerUp);
}

function stopAssistantFabDrag({ persist = false } = {}) {
  removeAssistantFabDragListeners();
  if (
    assistantFabPointerId !== null &&
    assistantFabRef.value?.releasePointerCapture
  ) {
    try {
      assistantFabRef.value.releasePointerCapture(assistantFabPointerId);
    } catch {
      // Ignore release failures when capture has already been cleared.
    }
  }
  if (persist && assistantFabDidMove && assistantFabPosition.value) {
    persistAssistantFabPosition(assistantFabPosition.value);
  }
  assistantFabPointerId = null;
  assistantFabDragging.value = false;
  assistantFabDidMove = false;
}

function handleAssistantFabClick() {
  if (suppressAssistantFabClick.value) {
    suppressAssistantFabClick.value = false;
    return;
  }
  openAssistantPanel();
}

function handleAssistantFabPointerDown(event) {
  if (event.button !== 0 || typeof window === "undefined") return;
  const rect = assistantFabRef.value?.getBoundingClientRect?.();
  const currentPosition =
    assistantFabPosition.value || resolveDefaultAssistantFabPosition(rect);
  assistantFabPosition.value = clampAssistantFabPosition(currentPosition, rect);
  assistantFabPointerId = event.pointerId;
  assistantFabDragging.value = true;
  suppressAssistantFabClick.value = false;
  assistantFabDidMove = false;
  assistantFabDragStartX = event.clientX;
  assistantFabDragStartY = event.clientY;
  assistantFabDragOffsetX = event.clientX - assistantFabPosition.value.x;
  assistantFabDragOffsetY = event.clientY - assistantFabPosition.value.y;
  event.preventDefault();
  if (event.currentTarget?.setPointerCapture) {
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Ignore capture failures and fall back to window listeners.
    }
  }
  removeAssistantFabDragListeners();
  window.addEventListener("pointermove", handleAssistantFabPointerMove);
  window.addEventListener("pointerup", handleAssistantFabPointerUp);
  window.addEventListener("pointercancel", handleAssistantFabPointerUp);
}

function handleAssistantFabPointerMove(event) {
  if (event.pointerId !== assistantFabPointerId) return;
  const rect = assistantFabRef.value?.getBoundingClientRect?.() || null;
  const movedDistance = Math.hypot(
    event.clientX - assistantFabDragStartX,
    event.clientY - assistantFabDragStartY,
  );
  if (movedDistance >= ASSISTANT_FAB_DRAG_THRESHOLD_PX) {
    assistantFabDidMove = true;
  }
  assistantFabPosition.value = clampAssistantFabPosition(
    {
      x: event.clientX - assistantFabDragOffsetX,
      y: event.clientY - assistantFabDragOffsetY,
    },
    rect,
  );
}

function handleAssistantFabPointerUp(event) {
  if (event.pointerId !== assistantFabPointerId) return;
  suppressAssistantFabClick.value = assistantFabDidMove;
  stopAssistantFabDrag({ persist: true });
}

function handleAssistantFabWindowResize() {
  if (typeof window === "undefined") return;
  if (assistantFabResizeRafId) {
    window.cancelAnimationFrame(assistantFabResizeRafId);
  }
  assistantFabResizeRafId = window.requestAnimationFrame(() => {
    assistantFabResizeRafId = 0;
    syncAssistantFabPosition();
  });
}

function togglePanelFullscreen() {
  panelFullscreen.value = !panelFullscreen.value;
}

function openAssistantPanel() {
  markAssistantInteractionGesture();
  if (panelOpen.value) {
    closeAssistantPanel();
    return;
  }
  panelOpen.value = true;
}

function toggleAssistantPanel() {
  panelOpen.value = !panelOpen.value;
}

function toggleAssistantSettingsPanel() {
  markAssistantInteractionGesture();
  settingsDialogOpen.value = !settingsDialogOpen.value;
}

function closeAssistantPanel() {
  panelOpen.value = false;
  settingsDialogOpen.value = false;
}

function handleVoiceSettingsTrigger() {
  markAssistantInteractionGesture();
  if (loading.value && !isListening.value) {
    ElMessage.warning("请等待当前回答完成后再发起语音输入");
    return;
  }
  if (voiceGreetingStarting.value) {
    return;
  }
  if (isListening.value) {
    void stopVoiceInput({ autoSubmit: false });
    return;
  }
  const greetingDelayMs = maybePlayAssistantGreetingForVoiceStart();
  if (greetingDelayMs > 0) {
    clearPendingVoiceStartTimer();
    voiceGreetingStarting.value = true;
    voiceStatusText.value = "正在播放欢迎语...";
    voiceStartAfterGreetingTimer = window.setTimeout(() => {
      voiceStartAfterGreetingTimer = null;
      voiceGreetingStarting.value = false;
      if (!shouldRender.value) return;
      if (isListening.value || isStoppingVoiceInput.value || loading.value) return;
      void startVoiceInput({ activate: true });
    }, greetingDelayMs);
    return;
  }
  void startVoiceInput({ activate: true });
}

function roleLabel(role) {
  if (role === "user") return "你";
  if (role === "assistant") return "AI";
  if (role === "system") return "系统";
  return "消息";
}

function browserSpeechPlaybackSupported() {
  if (typeof window === "undefined") return false;
  return Boolean(window.speechSynthesis && window.SpeechSynthesisUtterance);
}

function loadStoredSpeechVoiceUri() {
  return loadAssistantStorageValue(
    SPEECH_VOICE_STORAGE_SUFFIX,
    LEGACY_SPEECH_VOICE_STORAGE_KEY,
  );
}

function persistSpeechVoiceUri(value) {
  persistAssistantStorageValue(
    SPEECH_VOICE_STORAGE_SUFFIX,
    value,
    LEGACY_SPEECH_VOICE_STORAGE_KEY,
  );
}

function loadStoredAutoPlayAssistantSpeech() {
  return loadAssistantStorageValue(SPEECH_AUTO_PLAY_STORAGE_SUFFIX) === "1";
}

function persistAutoPlayAssistantSpeech(value) {
  persistAssistantStorageValue(
    SPEECH_AUTO_PLAY_STORAGE_SUFFIX,
    value ? "1" : "",
  );
}

function normalizeSpeechVoiceOptions(voices) {
  return voices
    .filter((item) => item?.voiceURI)
    .map((item) => ({
      voiceURI: String(item.voiceURI || "").trim(),
      name: String(item.name || "").trim(),
      lang: String(item.lang || "").trim(),
      default: Boolean(item.default),
      label: `${String(item.name || "未命名声音").trim()} · ${String(item.lang || "unknown").trim()}${item.default ? " · 系统默认" : ""}`,
    }))
    .filter((item) => item.voiceURI);
}

function sortSpeechVoiceOptions(list) {
  list.sort((left, right) => {
    const leftZh = /^zh(-|_)?/i.test(left.lang);
    const rightZh = /^zh(-|_)?/i.test(right.lang);
    if (leftZh !== rightZh) return leftZh ? -1 : 1;
    if (left.default !== right.default) return left.default ? -1 : 1;
    return left.label.localeCompare(right.label, "zh-CN");
  });
  return list;
}

function stopSpeechVoiceRetry() {
  if (!speechVoiceRetryTimer) return;
  window.clearTimeout(speechVoiceRetryTimer);
  speechVoiceRetryTimer = null;
}

function applySpeechVoiceOptions(normalizedVoices) {
  speechVoiceOptions.value = normalizedVoices;
  if (
    selectedSpeechVoiceUri.value &&
    normalizedVoices.some((item) => item.voiceURI === selectedSpeechVoiceUri.value)
  ) {
    return;
  }
  const stored = loadStoredSpeechVoiceUri();
  if (
    stored &&
    normalizedVoices.some((item) => item.voiceURI === stored)
  ) {
    selectedSpeechVoiceUri.value = stored;
    return;
  }
  selectedSpeechVoiceUri.value = "";
}

function scheduleSpeechVoiceRetry() {
  if (typeof window === "undefined") return;
  if (speechVoiceRetryTimer || speechVoiceRetryCount >= SPEECH_VOICE_MAX_RETRIES) {
    speechVoiceLoading.value = false;
    return;
  }
  speechVoiceRetryTimer = window.setTimeout(() => {
    speechVoiceRetryTimer = null;
    speechVoiceRetryCount += 1;
    refreshSpeechVoiceOptions();
  }, SPEECH_VOICE_RETRY_DELAY_MS);
}

function refreshSpeechVoiceOptions(options = {}) {
  const forceRetry = Boolean(options?.forceRetry);
  if (!browserSpeechPlaybackSupported()) {
    stopSpeechVoiceRetry();
    speechVoiceRetryCount = 0;
    speechVoiceLoading.value = false;
    speechVoiceOptions.value = [];
    selectedSpeechVoiceUri.value = "";
    return;
  }
  if (forceRetry) {
    stopSpeechVoiceRetry();
    speechVoiceRetryCount = 0;
  }
  speechVoiceLoading.value = true;
  const voices = Array.isArray(window.speechSynthesis.getVoices())
    ? window.speechSynthesis.getVoices()
    : [];
  const normalizedVoices = sortSpeechVoiceOptions(normalizeSpeechVoiceOptions(voices));
  applySpeechVoiceOptions(normalizedVoices);
  if (normalizedVoices.length) {
    stopSpeechVoiceRetry();
    speechVoiceRetryCount = 0;
    speechVoiceLoading.value = false;
    return;
  }
  scheduleSpeechVoiceRetry();
}

function resolveAssistantSpeechVoice() {
  if (!browserSpeechPlaybackSupported()) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!Array.isArray(voices) || !voices.length) {
    return null;
  }
  const selectedVoiceUri = String(selectedSpeechVoiceUri.value || "").trim();
  if (selectedVoiceUri) {
    const selectedVoice = voices.find(
      (item) => String(item?.voiceURI || "").trim() === selectedVoiceUri,
    );
    if (selectedVoice) return selectedVoice;
  }
  return (
    voices.find((item) => /^zh(-|_)?/i.test(String(item?.lang || "").trim())) ||
    voices[0] ||
    null
  );
}

function assistantSpeechPlaybackSupported() {
  return backendSpeechPlaybackEnabled.value || browserSpeechPlaybackSupported();
}

function cleanupAssistantAudioPlayback() {
  if (speechAudioElement) {
    speechAudioElement.pause();
    speechAudioElement.currentTime = 0;
    speechAudioElement.onended = null;
    speechAudioElement.onerror = null;
    speechAudioElement.src = "";
    speechAudioElement = null;
  }
  if (speechAudioObjectUrl) {
    URL.revokeObjectURL(speechAudioObjectUrl);
    speechAudioObjectUrl = "";
  }
}

function clearActiveSpeechPlaybackInterrupt(handler = null) {
  if (!handler || activeSpeechPlaybackInterrupt === handler) {
    activeSpeechPlaybackInterrupt = null;
  }
}

function registerActiveSpeechPlaybackInterrupt(handler) {
  activeSpeechPlaybackInterrupt = typeof handler === "function" ? handler : null;
  return activeSpeechPlaybackInterrupt;
}

function interruptActiveSpeechPlayback() {
  const handler = activeSpeechPlaybackInterrupt;
  activeSpeechPlaybackInterrupt = null;
  if (typeof handler === "function") {
    handler();
  }
}

function clearSpeechAudioCache() {
  speechAudioBlobCache.clear();
  speechAudioPendingRequests.clear();
}

function rememberSpeechAudioBlob(cacheKey, audioBlob) {
  if (!cacheKey || !(audioBlob instanceof Blob)) {
    return audioBlob;
  }
  if (speechAudioBlobCache.has(cacheKey)) {
    speechAudioBlobCache.delete(cacheKey);
  }
  speechAudioBlobCache.set(cacheKey, audioBlob);
  while (speechAudioBlobCache.size > SPEECH_AUDIO_CACHE_LIMIT) {
    const oldestCacheKey = speechAudioBlobCache.keys().next().value;
    if (!oldestCacheKey) break;
    speechAudioBlobCache.delete(oldestCacheKey);
  }
  return audioBlob;
}

function buildSpeechAudioCacheKey(text) {
  const normalizedText = String(text || "").trim();
  if (!normalizedText || !backendSpeechPlaybackEnabled.value) return "";
  return JSON.stringify([speechRuntimeCacheSignature.value, normalizedText]);
}

function buildGreetingAudioCacheKey() {
  if (!backendSpeechPlaybackEnabled.value) return "";
  if (!Boolean(speechRuntime.value?.greeting_audio_available)) return "";
  const signature = String(greetingAudioCacheSignature.value || "").trim();
  if (!signature) return "";
  return JSON.stringify(["greeting", signature]);
}

function normalizeSpeechAudioBlob(payload) {
  return payload instanceof Blob
    ? payload
    : new Blob([payload], { type: "audio/wav" });
}

async function fetchSpeechAudioBlob(text) {
  const normalizedText = String(text || "").trim();
  if (!normalizedText) {
    throw new Error("语音内容为空");
  }
  const cacheKey = buildSpeechAudioCacheKey(normalizedText);
  if (cacheKey && speechAudioBlobCache.has(cacheKey)) {
    const cachedBlob = speechAudioBlobCache.get(cacheKey);
    speechAudioBlobCache.delete(cacheKey);
    speechAudioBlobCache.set(cacheKey, cachedBlob);
    return cachedBlob;
  }
  if (cacheKey && speechAudioPendingRequests.has(cacheKey)) {
    return speechAudioPendingRequests.get(cacheKey);
  }
  const requestPromise = (async () => {
    const payload = await api.post(
      "/projects/chat/global/voice-output/speech",
      { text: normalizedText },
      { responseType: "blob" },
    );
    const audioBlob = normalizeSpeechAudioBlob(payload);
    if (cacheKey) {
      rememberSpeechAudioBlob(cacheKey, audioBlob);
    }
    return audioBlob;
  })().finally(() => {
    if (cacheKey) {
      speechAudioPendingRequests.delete(cacheKey);
    }
  });
  if (cacheKey) {
    speechAudioPendingRequests.set(cacheKey, requestPromise);
  }
  return requestPromise;
}

async function fetchGreetingAudioBlob() {
  const cacheKey = buildGreetingAudioCacheKey();
  if (!cacheKey) return null;
  if (speechAudioBlobCache.has(cacheKey)) {
    const cachedBlob = speechAudioBlobCache.get(cacheKey);
    speechAudioBlobCache.delete(cacheKey);
    speechAudioBlobCache.set(cacheKey, cachedBlob);
    return cachedBlob;
  }
  if (speechAudioPendingRequests.has(cacheKey)) {
    return speechAudioPendingRequests.get(cacheKey);
  }
  const requestPromise = (async () => {
    try {
      const payload = await api.get(
        "/projects/chat/global/voice-output/greeting-audio",
        { responseType: "blob" },
      );
      const audioBlob = normalizeSpeechAudioBlob(payload);
      rememberSpeechAudioBlob(cacheKey, audioBlob);
      return audioBlob;
    } catch (err) {
      const status = Number(err?.status || err?.response?.status || 0);
      if (status === 404) return null;
      throw err;
    }
  })().finally(() => {
    speechAudioPendingRequests.delete(cacheKey);
  });
  speechAudioPendingRequests.set(cacheKey, requestPromise);
  return requestPromise;
}

function stopAssistantSpeech(options = {}) {
  const cancelGreetingStart = Boolean(options?.cancelGreetingStart);
  const preferStandbyAfterStop = Boolean(options?.preferStandbyAfterStop);
  speechPlaybackToken += 1;
  speechSegmentQueue = [];
  speechStreamingProgress.clear();
  speechQueueProcessing = false;
  cleanupAssistantAudioPlayback();
  if (browserSpeechPlaybackSupported()) {
    window.speechSynthesis.cancel();
  }
  interruptActiveSpeechPlayback();
  speechUtterance = null;
  speakingMessageId.value = "";
  if (cancelGreetingStart) {
    clearPendingVoiceStartTimer();
  }
  resumeVoiceListeningAfterAssistantSpeech();
  clearAssistantSpeechUiState({ preferStandbyAfterStop });
}

function consumeSpeakableSpeechSegments(text, options = {}) {
  const source = String(text || "");
  const flush = Boolean(options?.flush);
  const segments = [];
  let buffer = "";
  let consumedLength = 0;

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    buffer += char;
    const trimmed = buffer.trim();
    if (!trimmed) continue;
    const strongBoundary = /[。！？!?；;\n]/.test(char);
    const softBoundary = /[，、,：:]/.test(char) && trimmed.length >= 24;
    const longBoundary = trimmed.length >= 72;
    if (!strongBoundary && !softBoundary && !longBoundary) continue;
    segments.push(trimmed);
    consumedLength = index + 1;
    buffer = "";
  }

  if (flush) {
    const tail = buffer.trim();
    if (tail) {
      segments.push(tail);
      consumedLength = source.length;
    }
  }

  return { segments, consumedLength };
}

async function playSpeechSegmentViaBrowser(segment, playbackToken) {
  if (!browserSpeechPlaybackSupported()) {
    throw new Error("当前浏览器暂不支持语音播放");
  }
  suspendVoiceListeningForAssistantSpeech();
  await new Promise((resolve, reject) => {
    let settled = false;
    const finalizeResolve = () => {
      if (settled) return;
      settled = true;
      clearActiveSpeechPlaybackInterrupt(interruptPlayback);
      resolve();
    };
    const finalizeReject = (error) => {
      if (settled) return;
      settled = true;
      clearActiveSpeechPlaybackInterrupt(interruptPlayback);
      reject(error);
    };
    const utterance = new window.SpeechSynthesisUtterance(segment.text);
    const voice = resolveAssistantSpeechVoice();
    utterance.lang = String(voice?.lang || "zh-CN").trim() || "zh-CN";
    if (voice) {
      utterance.voice = voice;
    }
    utterance.rate = 1;
    utterance.pitch = 1;
    const interruptPlayback = registerActiveSpeechPlaybackInterrupt(() => {
      utterance.onend = null;
      utterance.onerror = null;
      if (speechUtterance === utterance) {
        speechUtterance = null;
      }
      finalizeResolve();
    });
    utterance.onend = () => {
      if (speechUtterance === utterance) {
        speechUtterance = null;
      }
      finalizeResolve();
    };
    utterance.onerror = () => {
      if (speechUtterance === utterance) {
        speechUtterance = null;
      }
      finalizeReject(new Error("语音播放失败，请稍后重试"));
    };
    if (speechPlaybackToken !== playbackToken) {
      finalizeResolve();
      return;
    }
    speechUtterance = utterance;
    window.speechSynthesis.speak(utterance);
  });
  if (speechPlaybackToken === playbackToken) {
    resumeVoiceListeningAfterAssistantSpeech();
  }
}

async function playSpeechSegmentViaBackend(segment, playbackToken) {
  suspendVoiceListeningForAssistantSpeech();
  const audioBlob = await fetchSpeechAudioBlob(segment.text);
  if (speechPlaybackToken !== playbackToken) {
    resumeVoiceListeningAfterAssistantSpeech();
    return;
  }
  const objectUrl = URL.createObjectURL(audioBlob);
  const audio = new Audio(objectUrl);
  speechAudioElement = audio;
  speechAudioObjectUrl = objectUrl;
  await new Promise((resolve, reject) => {
    let settled = false;
    const finalizeResolve = () => {
      if (settled) return;
      settled = true;
      clearActiveSpeechPlaybackInterrupt(interruptPlayback);
      resolve();
    };
    const finalizeReject = (error) => {
      if (settled) return;
      settled = true;
      clearActiveSpeechPlaybackInterrupt(interruptPlayback);
      reject(error);
    };
    const interruptPlayback = registerActiveSpeechPlaybackInterrupt(() => {
      cleanupAssistantAudioPlayback();
      finalizeResolve();
    });
    audio.onended = () => {
      cleanupAssistantAudioPlayback();
      finalizeResolve();
    };
    audio.onerror = () => {
      cleanupAssistantAudioPlayback();
      finalizeReject(new Error("语音播放失败，请稍后重试"));
    };
    void audio.play().catch((err) => {
      cleanupAssistantAudioPlayback();
      finalizeReject(
        err instanceof Error ? err : new Error("语音播放失败，请稍后重试"),
      );
    });
  });
  if (speechPlaybackToken === playbackToken) {
    resumeVoiceListeningAfterAssistantSpeech();
  }
}

async function drainSpeechSegmentQueue() {
  if (speechQueueProcessing || !speechSegmentQueue.length) return;
  speechQueueProcessing = true;
  const playbackToken = speechPlaybackToken;
  try {
    while (speechSegmentQueue.length) {
      if (speechPlaybackToken !== playbackToken) return;
      const segment = speechSegmentQueue.shift();
      if (!segment?.text) continue;
      speakingMessageId.value = String(segment.messageId || "").trim();
      if (backendSpeechPlaybackEnabled.value) {
        await playSpeechSegmentViaBackend(segment, playbackToken);
      } else {
        await playSpeechSegmentViaBrowser(segment, playbackToken);
      }
    }
  } catch (err) {
    if (speechPlaybackToken === playbackToken) {
      stopAssistantSpeech();
      ElMessage.warning(err?.message || "语音播放失败，请稍后重试");
    }
  } finally {
    speechQueueProcessing = false;
    if (
      speechPlaybackToken === playbackToken &&
      !speechSegmentQueue.length &&
      !speechUtterance &&
      !speechAudioElement
    ) {
      speakingMessageId.value = "";
    }
  }
}

function enqueueSpeechSegments(messageId, segments) {
  const normalizedMessageId = String(messageId || "").trim();
  const normalizedSegments = (Array.isArray(segments) ? segments : [])
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  if (!normalizedMessageId || !normalizedSegments.length) return;
  const hasOtherMessageQueued = speechSegmentQueue.some(
    (item) => String(item?.messageId || "").trim() !== normalizedMessageId,
  );
  const activeMessageId = String(speakingMessageId.value || "").trim();
  if (
    (activeMessageId && activeMessageId !== normalizedMessageId) ||
    hasOtherMessageQueued
  ) {
    stopAssistantSpeech();
  }
  speechSegmentQueue.push(
    ...normalizedSegments.map((text) => ({
      messageId: normalizedMessageId,
      text,
    })),
  );
  void drainSpeechSegmentQueue();
}

function scheduleStreamingAssistantSpeech(message, options = {}) {
  if (!autoPlayAssistantSpeech.value || !assistantSpeechPlaybackSupported()) return;
  const messageId = String(message?.id || "").trim();
  if (!messageId || suppressedAutoPlayMessageIds.has(messageId)) return;
  const content = String(message?.content || "");
  if (!content.trim()) return;
  const progress = speechStreamingProgress.get(messageId) || { consumedLength: 0 };
  const remaining = content.slice(Number(progress.consumedLength || 0));
  if (!remaining) return;
  const { segments, consumedLength } = consumeSpeakableSpeechSegments(remaining, options);
  if (!consumedLength || !segments.length) return;
  const nextConsumedLength = Number(progress.consumedLength || 0) + consumedLength;
  if (Boolean(options?.flush) && nextConsumedLength >= content.length) {
    speechStreamingProgress.delete(messageId);
  } else {
    speechStreamingProgress.set(messageId, {
      consumedLength: nextConsumedLength,
    });
  }
  enqueueSpeechSegments(messageId, segments);
}

function playAssistantSpeechViaBrowser(message) {
  const text = String(message?.content || "").trim();
  if (!text) return;
  if (!browserSpeechPlaybackSupported()) {
    ElMessage.warning("当前浏览器暂不支持语音播放");
    return;
  }
  const utterance = new window.SpeechSynthesisUtterance(text);
  const voice = resolveAssistantSpeechVoice();
  utterance.lang = String(voice?.lang || "zh-CN").trim() || "zh-CN";
  if (voice) {
    utterance.voice = voice;
  }
  utterance.rate = 1;
  utterance.pitch = 1;
  const interruptPlayback = () => {
    utterance.onend = null;
    utterance.onerror = null;
    if (speechUtterance === utterance) {
      speechUtterance = null;
    }
  };
  utterance.onend = () => {
    if (speechUtterance !== utterance) return;
    clearActiveSpeechPlaybackInterrupt(interruptPlayback);
    speechUtterance = null;
    speakingMessageId.value = "";
    resumeVoiceListeningAfterAssistantSpeech();
  };
  utterance.onerror = () => {
    if (speechUtterance !== utterance) return;
    clearActiveSpeechPlaybackInterrupt(interruptPlayback);
    speechUtterance = null;
    speakingMessageId.value = "";
    resumeVoiceListeningAfterAssistantSpeech();
    ElMessage.warning("语音播放失败，请稍后重试");
  };
  stopAssistantSpeech();
  suspendVoiceListeningForAssistantSpeech();
  registerActiveSpeechPlaybackInterrupt(interruptPlayback);
  speechUtterance = utterance;
  speakingMessageId.value = String(message.id || "").trim();
  window.speechSynthesis.speak(utterance);
}

async function playAssistantSpeechViaBackend(message, options = {}) {
  const text = String(message?.content || "").trim();
  if (!text) return;
  const playbackToken = speechPlaybackToken + 1;
  let interruptPlayback = null;
  stopAssistantSpeech();
  speechPlaybackToken = playbackToken;
  speakingMessageId.value = String(message.id || "").trim();
  try {
    suspendVoiceListeningForAssistantSpeech();
    const audioBlob =
      (options?.preferGreetingCache ? await fetchGreetingAudioBlob() : null) ||
      (await fetchSpeechAudioBlob(text));
    if (speechPlaybackToken !== playbackToken) {
      resumeVoiceListeningAfterAssistantSpeech();
      return;
    }
    const objectUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(objectUrl);
    speechAudioElement = audio;
    speechAudioObjectUrl = objectUrl;
    interruptPlayback = registerActiveSpeechPlaybackInterrupt(() => {
      cleanupAssistantAudioPlayback();
      speakingMessageId.value = "";
      resumeVoiceListeningAfterAssistantSpeech();
    });
    audio.onended = () => {
      if (speechPlaybackToken !== playbackToken) return;
      clearActiveSpeechPlaybackInterrupt(interruptPlayback);
      cleanupAssistantAudioPlayback();
      speakingMessageId.value = "";
      resumeVoiceListeningAfterAssistantSpeech();
    };
    audio.onerror = () => {
      if (speechPlaybackToken !== playbackToken) return;
      clearActiveSpeechPlaybackInterrupt(interruptPlayback);
      cleanupAssistantAudioPlayback();
      speakingMessageId.value = "";
      resumeVoiceListeningAfterAssistantSpeech();
      ElMessage.warning("语音播放失败，请稍后重试");
    };
    await audio.play();
  } catch (err) {
    if (speechPlaybackToken !== playbackToken) return;
    clearActiveSpeechPlaybackInterrupt(interruptPlayback);
    cleanupAssistantAudioPlayback();
    speakingMessageId.value = "";
    resumeVoiceListeningAfterAssistantSpeech();
    ElMessage.warning(err?.detail || err?.message || "语音播放失败，请稍后重试");
  }
}

function playAssistantSpeech(message, options = {}) {
  const messageId = String(message?.id || "").trim();
  suppressedAutoPlayMessageIds.delete(messageId);
  if (messageId && Boolean(message?.isStreaming)) {
    speechStreamingProgress.set(messageId, {
      consumedLength: String(message?.content || "").length,
    });
  }
  if (backendSpeechPlaybackEnabled.value) {
    void playAssistantSpeechViaBackend(message, options);
    return;
  }
  playAssistantSpeechViaBrowser(message);
}

function markAssistantInteractionGesture() {
  hasAssistantInteractionGesture = true;
  if (!pendingGreetingMessageId) return;
  if (!assistantSpeechPlaybackSupported()) return;
  const greetingMessage = messages.value.find(
    (item) => String(item?.id || "").trim() === pendingGreetingMessageId,
  );
  if (!greetingMessage?.content) return;
  pendingGreetingMessageId = "";
  playAssistantSpeech(greetingMessage, { preferGreetingCache: true });
}

function toggleAutoPlayAssistantSpeech() {
  const nextValue = !autoPlayAssistantSpeech.value;
  autoPlayAssistantSpeech.value = nextValue;
  if (!nextValue) {
    suppressedAutoPlayMessageIds.clear();
    stopAssistantSpeech();
  }
  ElMessage.success(nextValue ? "已开启回复自动播报" : "已关闭回复自动播报");
}

function isSpeakingMessage(message) {
  const messageId = String(message?.id || "").trim();
  return Boolean(messageId) && speakingMessageId.value === messageId;
}

async function pauseAssistantSpeechToWakeStandby() {
  const shouldStartStandby =
    !isListening.value &&
    shouldRender.value &&
    voiceRuntimeAvailable.value &&
    browserAudioCaptureSupported();
  stopAssistantSpeech({
    cancelGreetingStart: true,
    preferStandbyAfterStop: true,
  });
  if (!shouldStartStandby || isStoppingVoiceInput.value) {
    return;
  }
  await startVoiceInput({ activate: false });
}

function toggleAssistantMessageSpeech(message) {
  if (!String(message?.content || "").trim()) return;
  if (isSpeakingMessage(message)) {
    suppressedAutoPlayMessageIds.add(String(message?.id || "").trim());
    void pauseAssistantSpeechToWakeStandby();
    return;
  }
  playAssistantSpeech(message);
}

async function copyAssistantMessage(message) {
  const text = String(message?.content || "").trim();
  if (!text) return;
  try {
    if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
      throw new Error("clipboard_unavailable");
    }
    await navigator.clipboard.writeText(text);
    ElMessage.success("回复已复制");
  } catch {
    ElMessage.warning("复制失败，请稍后重试");
  }
}

function previewSelectedSpeechVoice() {
  if (!assistantSpeechPlaybackSupported()) {
    ElMessage.warning("当前暂不支持语音播放");
    return;
  }
  if (speakingMessageId.value === SPEECH_PREVIEW_MESSAGE_ID) {
    stopAssistantSpeech();
    return;
  }
  playAssistantSpeech({
    id: SPEECH_PREVIEW_MESSAGE_ID,
    content: "你好，现在是 AI 助手回复播报声音试听。",
  });
}

function createEmptyVoiceTrackInfo() {
  return {
    label: "",
    deviceId: "",
    groupId: "",
    sampleRate: "",
    channelCount: "",
    echoCancellation: null,
    noiseSuppression: null,
    autoGainControl: null,
  };
}

function resolveVoiceTrackProcessingLabel(info) {
  const flags = [];
  if (typeof info?.noiseSuppression === "boolean") {
    flags.push(info.noiseSuppression ? "降噪开" : "降噪关");
  }
  if (typeof info?.echoCancellation === "boolean") {
    flags.push(info.echoCancellation ? "回声消除开" : "回声消除关");
  }
  if (typeof info?.autoGainControl === "boolean") {
    flags.push(info.autoGainControl ? "自动增益开" : "自动增益关");
  }
  return flags.join(" / ");
}

function loadStoredVoiceInputDeviceId() {
  return loadAssistantStorageValue(
    VOICE_INPUT_DEVICE_STORAGE_SUFFIX,
    LEGACY_VOICE_INPUT_DEVICE_STORAGE_KEY,
  );
}

function normalizeVoiceInputSelectionValue(deviceId) {
  const normalized = String(deviceId || "").trim();
  return normalized || VOICE_INPUT_DEFAULT_VALUE;
}

function resolveSelectedVoiceInputDeviceId() {
  const normalized = String(selectedVoiceInputDeviceId.value || "").trim();
  if (!normalized || normalized === VOICE_INPUT_DEFAULT_VALUE) {
    return "";
  }
  return normalized;
}

function persistVoiceInputDeviceId(deviceId) {
  const normalized = String(deviceId || "").trim();
  persistAssistantStorageValue(
    VOICE_INPUT_DEVICE_STORAGE_SUFFIX,
    normalized === VOICE_INPUT_DEFAULT_VALUE ? "" : normalized,
    LEGACY_VOICE_INPUT_DEVICE_STORAGE_KEY,
  );
}

async function refreshVoiceInputDevices({ preserveSelection = true } = {}) {
  if (
    typeof window === "undefined" ||
    !window.navigator?.mediaDevices?.enumerateDevices
  ) {
    voiceInputDevices.value = [];
    selectedVoiceInputDeviceId.value = VOICE_INPUT_DEFAULT_VALUE;
    return;
  }
  try {
    const devices = await window.navigator.mediaDevices.enumerateDevices();
    const audioInputs = devices
      .filter((item) => item.kind === "audioinput")
      .map((item, index) => ({
        deviceId: String(item.deviceId || "").trim(),
        label: String(item.label || "").trim() || `麦克风 ${index + 1}`,
      }))
      .filter((item) => item.deviceId);
    voiceInputDevices.value = audioInputs;
    if (!audioInputs.length) {
      selectedVoiceInputDeviceId.value = VOICE_INPUT_DEFAULT_VALUE;
      return;
    }
    let nextSelectedId = preserveSelection
      ? String(selectedVoiceInputDeviceId.value || loadStoredVoiceInputDeviceId()).trim()
      : VOICE_INPUT_DEFAULT_VALUE;
    const matched = audioInputs.find((item) => item.deviceId === nextSelectedId);
    const suspiciousVirtualDevice = /(virtual|oray|loopback|blackhole|soundflower|vb-audio|aggregate)/i;
    const hasNonVirtualAlternative = audioInputs.some(
      (item) => !suspiciousVirtualDevice.test(String(item.label || "").trim()),
    );
    if (
      matched &&
      hasNonVirtualAlternative &&
      suspiciousVirtualDevice.test(String(matched.label || "").trim())
    ) {
      nextSelectedId = VOICE_INPUT_DEFAULT_VALUE;
    }
    selectedVoiceInputDeviceId.value = audioInputs.some(
      (item) => item.deviceId === nextSelectedId,
    )
      ? nextSelectedId
      : VOICE_INPUT_DEFAULT_VALUE;
  } catch {}
}

function updateVoiceActiveTrackInfo(stream) {
  const track = stream?.getAudioTracks?.()?.[0];
  if (!track) {
    voiceActiveTrackInfo.value = createEmptyVoiceTrackInfo();
    return;
  }
  const settings =
    typeof track.getSettings === "function" ? track.getSettings() || {} : {};
  voiceActiveTrackInfo.value = {
    label: String(track.label || "").trim(),
    deviceId: String(settings.deviceId || "").trim(),
    groupId: String(settings.groupId || "").trim(),
    sampleRate: Number(settings.sampleRate || 0) || "",
    channelCount: Number(settings.channelCount || 0) || "",
    echoCancellation:
      typeof settings.echoCancellation === "boolean"
        ? settings.echoCancellation
        : null,
    noiseSuppression:
      typeof settings.noiseSuppression === "boolean"
        ? settings.noiseSuppression
        : null,
    autoGainControl:
      typeof settings.autoGainControl === "boolean"
        ? settings.autoGainControl
        : null,
  };
}

async function rescanVoiceInputDevices() {
  if (!browserAudioCaptureSupported()) return;
  voiceDeviceRefreshLoading.value = true;
  let tempStream = null;
  try {
    tempStream = await requestVoiceInputStream();
    updateVoiceActiveTrackInfo(tempStream);
    await refreshVoiceInputDevices();
  } catch (err) {
    ElMessage.warning(err?.message || "重新扫描麦克风失败");
  } finally {
    tempStream?.getTracks?.().forEach((track) => track.stop());
    voiceDeviceRefreshLoading.value = false;
  }
}

function handleVoiceDeviceSelectVisibility(open) {
  if (!open) return;
  void refreshVoiceInputDevices();
}

function resolveVoiceMeterPercent(level) {
  const normalized = Math.max(0, Number(level || 0));
  if (!normalized) return 0;
  if (normalized >= 0.18) return 100;
  return Math.max(
    3,
    Math.min(100, Math.round((Math.sqrt(normalized) / Math.sqrt(0.18)) * 100)),
  );
}

function startVoiceMeterDecay() {
  if (voiceMeterDecayTimer) return;
  voiceMeterDecayTimer = window.setInterval(() => {
    if (voiceMeterLevel.value <= 0.01) {
      voiceMeterLevel.value = 0;
      return;
    }
    voiceMeterLevel.value = Math.max(0, voiceMeterLevel.value * 0.76);
  }, 90);
}

function stopVoiceMeterDecay() {
  if (!voiceMeterDecayTimer) return;
  window.clearInterval(voiceMeterDecayTimer);
  voiceMeterDecayTimer = null;
}

function updateVoiceMeterLevel(samples) {
  let peak = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const value = Math.abs(samples[index] || 0);
    if (value > peak) {
      peak = value;
    }
  }
  if (peak > voiceMeterLevel.value) {
    voiceMeterLevel.value = Math.min(1, peak);
  }
}

function sanitizeAssistantErrorMessage(
  rawMessage,
  fallback = "操作失败，请稍后重试",
) {
  const message = String(rawMessage || "").trim();
  if (!message) return fallback;
  const lowered = message.toLowerCase();
  if (
    message.includes("transcriptions不支持当前文件格式") ||
    lowered.includes('"code":"1214"') ||
    message.includes("当前录音格式暂不支持")
  ) {
    return "当前录音格式暂不支持，请重新录音后再试";
  }
  if (
    message.includes("语音转写结果为空") ||
    lowered.includes("no audio segment found")
  ) {
    return "未识别到有效语音，请重新录音";
  }
  if (
    message.includes("LLM request failed") ||
    lowered.includes("http 4") ||
    lowered.includes("http 5")
  ) {
    return fallback;
  }
  return message;
}

function createLocalMessageId() {
  return `ga-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createEphemeralSessionId() {
  return `ga-session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeMessage(item) {
  return {
    id: String(item?.id || createLocalMessageId()).trim(),
    role:
      String(item?.role || "assistant")
        .trim()
        .toLowerCase() || "assistant",
    content: String(item?.content || "").trim(),
    created_at: String(
      item?.created_at || item?.time || new Date().toISOString(),
    ).trim(),
    images: normalizeUrlList(item?.images),
    videos: normalizeUrlList(item?.videos),
    attachments: normalizeUrlList(item?.attachments),
    status: String(item?.status || "").trim(),
    isStreaming: Boolean(item?.isStreaming),
  };
}

function normalizeUrlList(values) {
  return (Array.isArray(values) ? values : [])
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function mergeUrlList(current, next) {
  return Array.from(
    new Set([...normalizeUrlList(current), ...normalizeUrlList(next)]),
  );
}

function toHistoryRows(list) {
  return list
    .slice(-12)
    .map((item) => ({
      role: String(item?.role || "").trim(),
      content: String(item?.content || "").trim(),
    }))
    .filter(
      (item) => ["user", "assistant"].includes(item.role) && item.content,
    );
}

function scrollToBottom() {
  nextTick(() => {
    if (!messageContainerRef.value) return;
    messageContainerRef.value.scrollTop =
      messageContainerRef.value.scrollHeight;
  });
}

async function initializeAssistant() {
  if (!shouldRender.value) {
    teardownAssistant();
    return;
  }
  bootstrapping.value = true;
  errorText.value = "";
  try {
    selectedVoiceInputDeviceId.value = normalizeVoiceInputSelectionValue(
      loadStoredVoiceInputDeviceId(),
    );
    selectedSpeechVoiceUri.value = loadStoredSpeechVoiceUri();
    autoPlayAssistantSpeech.value = loadStoredAutoPlayAssistantSpeech();
    removeAssistantStorageValue(ASSISTANT_CHAT_CACHE_STORAGE_SUFFIX);
    messages.value = [];
    typedDraftText.value = "";
    currentChatSessionId.value = "";
    await fetchAssistantConfig();
    if (!globalAssistantEnabled.value) {
      teardownAssistant();
      return;
    }
    await Promise.all([fetchVoiceRuntime(), fetchSpeechRuntime(), refreshVoiceInputDevices()]);
    if (!String(currentChatSessionId.value || "").trim()) {
      currentChatSessionId.value = createEphemeralSessionId();
    }
    maybeRunInitialGreetingOnVisit();
  } catch (err) {
    errorText.value = err?.detail || err?.message || "初始化失败";
  } finally {
    bootstrapping.value = false;
  }
}

async function fetchAssistantConfig() {
  try {
    const data = await api.get("/system-config");
    const config =
      data?.config && typeof data.config === "object" ? data.config : {};
    globalAssistantEnabled.value = config.global_assistant_enabled !== false;
  } catch {
    globalAssistantEnabled.value = true;
  }
}

async function fetchVoiceRuntime() {
  voiceRuntimeLoading.value = true;
  try {
    const data = await api.get("/projects/chat/global/voice-input/runtime");
    const runtime =
      data?.runtime && typeof data.runtime === "object" ? data.runtime : {};
    voiceRuntime.value = {
      enabled: Boolean(runtime.enabled),
      available: Boolean(runtime.available),
      mode: String(runtime.mode || "").trim(),
      reason: String(runtime.reason || "").trim(),
      global_assistant_enabled: runtime.global_assistant_enabled !== false,
      provider_id: String(runtime.provider_id || "").trim(),
      provider_name: String(runtime.provider_name || "").trim(),
      model_name: String(runtime.model_name || "").trim(),
      greeting_enabled: Boolean(runtime.greeting_enabled),
      greeting_text:
        String(runtime.greeting_text || "").trim() ||
        DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
      transcription_prompt:
        String(runtime.transcription_prompt || "").trim() ||
        DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
      wake_phrase: String(runtime.wake_phrase || "你好助手").trim() || "你好助手",
      idle_timeout_sec: Math.max(
        3,
        Math.min(30, Number(runtime.idle_timeout_sec || 5) || 5),
      ),
    };
    globalAssistantEnabled.value = runtime.global_assistant_enabled !== false;
  } catch (err) {
    voiceRuntime.value = {
      enabled: false,
      available: false,
      mode: "",
      reason: sanitizeAssistantErrorMessage(
        err?.detail || err?.message,
        "语音能力加载失败",
      ),
      global_assistant_enabled: true,
      greeting_enabled: false,
      greeting_text: DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
      transcription_prompt: DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
      wake_phrase: "你好助手",
      idle_timeout_sec: 5,
    };
  } finally {
    voiceRuntimeLoading.value = false;
  }
}

async function fetchSpeechRuntime() {
  speechRuntimeLoading.value = true;
  try {
    const data = await api.get("/projects/chat/global/voice-output/runtime");
    const runtime =
      data?.runtime && typeof data.runtime === "object" ? data.runtime : {};
    speechRuntime.value = {
      enabled: Boolean(runtime.enabled),
      available: Boolean(runtime.available),
      mode: String(runtime.mode || "").trim(),
      reason: String(runtime.reason || "").trim(),
      provider_id: String(runtime.provider_id || "").trim(),
      provider_name: String(runtime.provider_name || "").trim(),
      model_name: String(runtime.model_name || "").trim(),
      voice: String(runtime.voice || "").trim(),
      greeting_audio_available: Boolean(runtime.greeting_audio_available),
      greeting_audio_signature: String(runtime.greeting_audio_signature || "").trim(),
    };
  } catch (err) {
    speechRuntime.value = {
      enabled: false,
      available: false,
      mode: "",
      reason: sanitizeAssistantErrorMessage(
        err?.detail || err?.message,
        "语音播报能力加载失败",
      ),
      provider_id: "",
      provider_name: "",
      model_name: "",
      voice: "",
      greeting_audio_available: false,
      greeting_audio_signature: "",
    };
  } finally {
    speechRuntimeLoading.value = false;
  }
}

function estimateGreetingDelayMs(text) {
  const length = Math.max(1, String(text || "").trim().length);
  return Math.min(6400, Math.max(1800, length * 180));
}

function clearPendingVoiceStartTimer() {
  if (voiceStartAfterGreetingTimer) {
    window.clearTimeout(voiceStartAfterGreetingTimer);
    voiceStartAfterGreetingTimer = null;
  }
  voiceGreetingStarting.value = false;
}

function appendAssistantGreetingMessage(text, options = {}) {
  const content = String(text || "").trim();
  if (!content) return;
  const greetingMessage = normalizeMessage({
    id: createLocalMessageId(),
    role: "assistant",
    content,
    created_at: new Date().toISOString(),
  });
  messages.value.push(greetingMessage);
  scrollToBottom();
  if (options?.playImmediately && assistantSpeechPlaybackSupported()) {
    playAssistantSpeech(greetingMessage, { preferGreetingCache: true });
    return;
  }
  pendingGreetingMessageId = String(greetingMessage.id || "").trim();
}

function findRecentGreetingMessage(text) {
  const normalizedText = String(text || "").trim();
  if (!normalizedText) return null;
  const latestMessage = messages.value[messages.value.length - 1];
  if (
    String(latestMessage?.role || "").trim() !== "assistant" ||
    String(latestMessage?.content || "").trim() !== normalizedText
  ) {
    return null;
  }
  const createdAt = Date.parse(String(latestMessage?.created_at || "").trim());
  if (!Number.isFinite(createdAt)) {
    return latestMessage;
  }
  return Date.now() - createdAt <= 15000 ? latestMessage : null;
}

function maybeRunInitialGreetingOnVisit() {
  const greetingText = voiceGreetingText.value;
  if (
    !voiceGreetingEnabled.value ||
    !greetingText ||
    loadGreetingSeenState()
  ) {
    return;
  }
  appendAssistantGreetingMessage(greetingText, {
    playImmediately: canAttemptGreetingAutoPlayOnVisit(),
  });
  persistGreetingSeenState(true);
}

function maybePlayAssistantGreetingForVoiceStart() {
  const greetingText = voiceGreetingText.value;
  if (voiceGreetingEnabled.value && greetingText) {
    const canPlayImmediately = assistantSpeechPlaybackSupported();
    const recentGreetingMessage = findRecentGreetingMessage(greetingText);
    if (recentGreetingMessage) {
      if (canPlayImmediately) {
        playAssistantSpeech(recentGreetingMessage, {
          preferGreetingCache: true,
        });
      }
      persistGreetingSeenState(true);
      return canPlayImmediately ? estimateGreetingDelayMs(greetingText) : 0;
    }
    appendAssistantGreetingMessage(greetingText, {
      playImmediately: canPlayImmediately,
    });
    persistGreetingSeenState(true);
    return canPlayImmediately ? estimateGreetingDelayMs(greetingText) : 0;
  }
  return 0;
}

async function ensureWsClient() {
  if (wsClient.value?.isOpen()) {
    return wsClient.value;
  }

  disconnectWs("reconnect");
  const token = getStoredToken();
  if (!token) {
    throw new Error("登录状态已失效");
  }

  const client = createGlobalAssistantWsClient({
    token,
    onOpen: () => {
      wsConnected.value = true;
    },
    onMessage: (payload) => {
      void handleSocketMessage(payload);
    },
    onError: () => {
      wsConnected.value = false;
      handleVoiceSocketDisconnect("语音连接已断开，请重新录音");
    },
    onClose: (event) => {
      const code = Number(event?.code || 1000);
      wsClient.value = null;
      wsConnected.value = false;
      if (code !== 1000) {
        handleVoiceSocketDisconnect(
          String(event?.reason || "").trim() || `连接关闭(${code})`,
        );
      }
      if (code !== 1000) {
        rejectPendingRequests(
          String(event?.reason || "").trim() || `连接关闭(${code})`,
        );
      }
    },
  });
  wsClient.value = client;
  await client.ready;
  wsConnected.value = true;
  return client;
}

function disconnectWs(reason = "") {
  if (wsClient.value) {
    wsClient.value.close(1000, reason || "client close");
  }
  wsClient.value = null;
  wsConnected.value = false;
}

function findMessageIndex(messageId) {
  return messages.value.findIndex((item) => item.id === messageId);
}

function syncPendingRequestUiState() {
  const entries = Array.from(pendingRequests.entries());
  const [requestId] = entries[entries.length - 1] || [];
  activePendingRequestId.value = String(requestId || "").trim();
  loading.value = entries.length > 0;
}

function rejectPendingRequests(reason) {
  const message = String(reason || "连接已断开").trim();
  for (const [requestId, pending] of Array.from(pendingRequests.entries())) {
    const index = findMessageIndex(pending.assistantMessageId);
    if (index >= 0) {
      messages.value[index] = {
        ...messages.value[index],
        content: messages.value[index].content || `请求失败：${message}`,
        status: "",
        isStreaming: false,
      };
    }
    pending.reject(new Error(message));
    pendingRequests.delete(requestId);
  }
  syncPendingRequestUiState();
}

function getActivePendingRequest() {
  const entries = Array.from(pendingRequests.entries());
  if (!entries.length) return null;
  const [requestId, pending] = entries[entries.length - 1];
  return {
    requestId,
    pending,
  };
}

function stopCurrentReply() {
  const active = getActivePendingRequest();
  if (!active?.requestId || !wsClient.value?.isOpen?.()) {
    ElMessage.warning("当前没有可停止的回复");
    return;
  }
  const index = findMessageIndex(active.pending.assistantMessageId);
  if (index >= 0) {
    messages.value[index] = {
      ...messages.value[index],
      status: "已发送停止指令...",
      isStreaming: true,
    };
  }
  wsClient.value.send({
    type: "cancel",
    request_id: active.requestId,
  });
  syncPendingRequestUiState();
  ElMessage.info("已发送停止指令");
}

function handleVoiceSocketDisconnect(reason) {
  if (
    !voiceStreamRequestId &&
    !isListening.value &&
    !isStoppingVoiceInput.value
  ) {
    return;
  }
  voiceTranscriptionEpoch += 1;
  voiceTranscriptionQueue = [];
  voiceTranscriptionProcessing = false;
  resetVoiceVadState();
  teardownAudioProcessingGraph();
  stopMediaStream();
  resetCapturedVoiceFrames();
  voiceStreamRequestId = "";
  voiceStreamChunkIndex = 0;
  isListening.value = false;
  isStoppingVoiceInput.value = false;
  voiceWakeState.value = "standby";
  voiceWakeScanBuffer.value = "";
  voiceStatusText.value = sanitizeAssistantErrorMessage(
    reason,
    "语音连接已断开，请重新录音",
  );
}

async function handleSocketMessage(eventData) {
  const eventType = String(eventData?.type || "")
    .trim()
    .toLowerCase();
  const requestId = String(eventData?.request_id || "").trim();
  if (eventType === "ready" || eventType === "pong") {
    return;
  }
  if (eventType.startsWith("voice_")) {
    await handleVoiceSocketMessage(eventData, eventType, requestId);
    return;
  }
  if (eventType === "browser_tool_call") {
    await handleBrowserToolCall(eventData);
    return;
  }

  if (!requestId) {
    if (eventType === "error") {
      ElMessage.error(String(eventData?.message || "对话异常"));
    }
    return;
  }

  const pending = pendingRequests.get(requestId);
  if (!pending) return;
  const index = findMessageIndex(pending.assistantMessageId);
  if (index < 0) {
    pending.reject(new Error("助手消息上下文已失效"));
    pendingRequests.delete(requestId);
    syncPendingRequestUiState();
    return;
  }

  const row = messages.value[index];

  if (eventType === "start") {
    messages.value[index] = {
      ...row,
      status: "正在建立实时上下文...",
      isStreaming: true,
    };
    scrollToBottom();
    return;
  }

  if (eventType === "status") {
    messages.value[index] = {
      ...row,
      status:
        String(eventData?.message || "AI 正在处理...").trim() ||
        "AI 正在处理...",
      isStreaming: true,
    };
    scrollToBottom();
    return;
  }

  if (eventType === "delta") {
    const nextRow = {
      ...row,
      content: `${row.content || ""}${String(eventData?.content || "")}`,
      status: "AI 正在输出...",
      isStreaming: true,
    };
    messages.value[index] = nextRow;
    scheduleStreamingAssistantSpeech(nextRow);
    scrollToBottom();
    return;
  }

  if (eventType === "done") {
    const nextContent = String(eventData?.content || "").trim();
    const nextRow = {
      ...row,
      content: row.content || nextContent,
      status: "",
      isStreaming: false,
      images: mergeUrlList(row.images, eventData?.images),
      videos: mergeUrlList(row.videos, eventData?.videos),
    };
    messages.value[index] = nextRow;
    pending.resolve(nextRow);
    pendingRequests.delete(requestId);
    syncPendingRequestUiState();
    if (isListening.value && !voiceListeningSuspendedBySpeech.value) {
      enterVoiceStandbyMode();
    }
    scrollToBottom();
    if (autoPlayAssistantSpeech.value && nextRow.content) {
      scheduleStreamingAssistantSpeech(nextRow, { flush: true });
    }
    return;
  }

  if (eventType === "error") {
    const message = sanitizeAssistantErrorMessage(
      eventData?.message,
      "对话失败，请稍后重试",
    );
    messages.value[index] = {
      ...row,
      content: row.content || `对话失败：${message}`,
      status: "",
      isStreaming: false,
    };
    speechStreamingProgress.delete(String(row?.id || "").trim());
    suppressedAutoPlayMessageIds.delete(String(row?.id || "").trim());
    pending.reject(new Error(message));
    pendingRequests.delete(requestId);
    syncPendingRequestUiState();
    if (isListening.value && !voiceListeningSuspendedBySpeech.value) {
      enterVoiceStandbyMode();
    }
    ElMessage.error(message);
    scrollToBottom();
  }
}

async function handleBrowserToolCall(eventData) {
  const callId = String(eventData?.call_id || "").trim();
  if (!callId || !wsClient.value?.isOpen()) return;
  try {
    const result = await executeAssistantBrowserToolCall(eventData);
    wsClient.value.send({
      type: "browser_tool_result",
      call_id: callId,
      request_id: String(eventData?.request_id || "").trim(),
      tool_name: String(eventData?.tool_name || "").trim(),
      ok: true,
      result,
    });
  } catch (err) {
    wsClient.value.send({
      type: "browser_tool_result",
      call_id: callId,
      request_id: String(eventData?.request_id || "").trim(),
      tool_name: String(eventData?.tool_name || "").trim(),
      ok: false,
      error: String(err?.message || "浏览器工具执行失败").trim(),
    });
  }
}

async function handleVoiceSocketMessage(eventData, eventType, requestId) {
  const normalizedRequestId = String(requestId || "").trim();
  if (normalizedRequestId && !voicePendingRequestIds.has(normalizedRequestId)) {
    return;
  }

  if (eventType === "voice_ready") {
    voiceUiStage.value = "listening";
    if (voiceRequestedStartMode.value === "active" || voiceWakeState.value === "active") {
      enterVoiceActiveMode();
    } else {
      enterVoiceStandbyMode();
    }
    return;
  }

  if (eventType === "voice_status") {
    if (isListening.value && voiceWakeState.value === "standby") {
      voiceUiStage.value = "listening";
      voiceStatusText.value = resolveVoiceStandbyMessage();
      return;
    }
    voiceUiStage.value = isListening.value ? "listening" : "recognizing";
    voiceStatusText.value =
      String(eventData?.message || "").trim() || "正在识别语音...";
    return;
  }

  if (eventType === "voice_transcript") {
    const transcriptText = String(eventData?.text || "").trim();
    if (!transcriptText) return;
    if (voiceWakeState.value === "standby") {
      if (loading.value) return;
      const wakeResult = detectWakePhraseFromTranscript(transcriptText);
      if (!wakeResult.matched) {
        if (
          await tryHandleDirectRouteCommand(transcriptText, {
            openPanel: false,
            recordConversation: true,
          })
        ) {
          return;
        }
        const heardText = String(wakeResult.heardText || "").trim();
        if (heardText) {
          voiceStandbyHeardText.value = heardText;
          voiceStatusText.value = resolveVoiceStandbyMessage();
        }
        return;
      }
      enterVoiceActiveMode(wakeResult.remainder);
      return;
    }
    if (Boolean(eventData?.is_final)) {
      replaceVoiceTranscriptWithFinalText(transcriptText);
    } else {
      updateVoiceTranscriptPreview(transcriptText);
    }
    voiceUiStage.value = isListening.value ? "listening" : "recognizing";
    voiceStatusText.value = isListening.value
      ? `正在接收语音指令，${voiceIdleTimeoutMs.value / 1000}s 无新内容后自动发送`
      : "正在整理语音结果...";
    return;
  }

  if (eventType === "voice_stopped") {
    if (normalizedRequestId) {
      voicePendingRequestIds.delete(normalizedRequestId);
    }
    if (normalizedRequestId === voiceStreamRequestId) {
      voiceStreamRequestId = "";
      voiceStreamChunkIndex = 0;
    }
    replaceVoiceTranscriptWithFinalText(eventData?.text);
    isStoppingVoiceInput.value = false;
    if (recognizedVoiceDraft.value && shouldAutoSubmitVoiceAfterStop) {
      voiceStatusText.value = "识别完成，正在自动发送...";
      await submitVoiceDraft();
      return;
    }
    voiceUiStage.value = "idle";
    voiceStatusText.value = recognizedVoiceDraft.value
      ? "实时通话已关闭"
      : resolveVoiceEmptyResultMessage();
    clearVoiceAutoSendTimers();
    shouldAutoSubmitVoiceAfterStop = false;
    voiceWakeState.value = "standby";
    voiceWakeScanBuffer.value = "";
    return;
  }

  if (eventType === "voice_error") {
    let message = sanitizeAssistantErrorMessage(
      eventData?.message,
      "语音转写暂时不可用，请稍后重试",
    );
    if (
      message === "未识别到有效语音，请重新录音" &&
      !String(recognizedVoiceDraft.value || "").trim()
    ) {
      message = resolveVoiceEmptyResultMessage();
    }
    if (normalizedRequestId) {
      voicePendingRequestIds.delete(normalizedRequestId);
    }
    if (normalizedRequestId === voiceStreamRequestId) {
      voiceStreamRequestId = "";
      voiceStreamChunkIndex = 0;
    }
    teardownAudioProcessingGraph();
    stopMediaStream();
    resetCapturedVoiceFrames();
    clearVoiceAutoSendTimers();
    isListening.value = false;
    isStoppingVoiceInput.value = false;
    voiceUiStage.value = "error";
    voiceStatusText.value = message;
    voiceWakeState.value = "standby";
    voiceWakeScanBuffer.value = "";
    ElMessage.error(message);
  }
}

function handleComposerKeydown(event) {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  void sendCurrentDraft();
}

async function sendCurrentDraft() {
  await sendMessage(String(typedDraftText.value || "").trim());
}

async function submitVoiceDraft() {
  const text = String(voiceDraftText.value || "").trim();
  clearVoiceAutoSendTimers();
  shouldAutoSubmitVoiceAfterStop = false;
  if (!text || loading.value || isStoppingVoiceInput.value) {
    return;
  }
  await sendMessage(text, { openPanel: false, fromVoice: true });
}

async function sendMessage(rawText, options = {}) {
  const text = String(rawText || "").trim();
  if (!text || loading.value) return;
  if (await tryHandleDirectRouteCommand(text, options)) return;

  let sessionId = String(currentChatSessionId.value || "").trim();
  if (!sessionId) {
    sessionId = createEphemeralSessionId();
    currentChatSessionId.value = sessionId;
  }

  if (options?.openPanel !== false) {
    panelOpen.value = true;
  }

  const history = toHistoryRows(messages.value);
  const userMessage = normalizeMessage({
    id: createLocalMessageId(),
    role: "user",
    content: text,
    created_at: new Date().toISOString(),
  });
  const assistantMessage = normalizeMessage({
    id: createLocalMessageId(),
    role: "assistant",
    content: "",
    created_at: new Date().toISOString(),
    status: "等待 AI 响应...",
    isStreaming: true,
  });
  speechStreamingProgress.delete(assistantMessage.id);
  suppressedAutoPlayMessageIds.delete(assistantMessage.id);

  messages.value.push(userMessage);
  messages.value.push(assistantMessage);
  typedDraftText.value = "";
  clearVoiceDraftBuffer();
  if (isListening.value) {
    enterVoiceExecutionMode();
  } else {
    resetVoiceCapture();
  }
  loading.value = true;
  scrollToBottom();

  const requestId = createLocalMessageId();
  try {
    const client = await ensureWsClient();
    await new Promise((resolve, reject) => {
      pendingRequests.set(requestId, {
        requestId,
        resolve,
        reject,
        sessionId,
        assistantMessageId: assistantMessage.id,
      });
      syncPendingRequestUiState();
      client.send({
        request_id: requestId,
        message_id: userMessage.id,
        assistant_message_id: assistantMessage.id,
        chat_session_id: sessionId,
        chat_mode: "system",
        chat_surface: "global-assistant",
        message: text,
        history,
        route_path: normalizedRoutePath.value,
        route_title: currentRouteLabel.value,
      });
    });
  } catch (err) {
    speechStreamingProgress.delete(assistantMessage.id);
    suppressedAutoPlayMessageIds.delete(assistantMessage.id);
    const index = findMessageIndex(assistantMessage.id);
    const message = sanitizeAssistantErrorMessage(
      err?.detail || err?.message,
      "发送失败，请稍后重试",
    );
    if (index >= 0) {
      messages.value[index] = {
        ...messages.value[index],
        content: `请求失败：${message}`,
        status: "",
        isStreaming: false,
      };
    }
    if (isListening.value && !voiceListeningSuspendedBySpeech.value) {
      enterVoiceStandbyMode();
    }
    ElMessage.error(message);
  } finally {
    pendingRequests.delete(requestId);
    syncPendingRequestUiState();
    scrollToBottom();
  }
}

function browserAudioCaptureSupported() {
  if (typeof window === "undefined") return false;
  return Boolean(
    window.navigator?.mediaDevices?.getUserMedia &&
    (window.AudioContext || window.webkitAudioContext),
  );
}

function clearVoiceAutoSendTimers(options = {}) {
  const preservePending = Boolean(options?.preservePending);
  if (voiceAutoSendTimer) {
    window.clearTimeout(voiceAutoSendTimer);
    voiceAutoSendTimer = null;
  }
  if (voiceAutoSendCountdownTimer) {
    window.clearInterval(voiceAutoSendCountdownTimer);
    voiceAutoSendCountdownTimer = null;
  }
  voiceAutoSendCountdownMs.value = 0;
  if (!preservePending) {
    shouldAutoSubmitVoiceAfterStop = false;
  }
}

function clearVoiceDraftBuffer() {
  recognizedVoiceDraft.value = "";
  liveVoiceTranscript.value = "";
  voiceDraftText.value = "";
  confirmedVoiceSegments.value = [];
}

function suspendVoiceListeningForAssistantSpeech() {
  if (!isListening.value || voiceListeningSuspendedBySpeech.value) return;
  voiceListeningResumeMode =
    voiceWakeState.value === "active" ? "active" : "standby";
  voiceListeningSuspendedBySpeech.value = true;
  clearVoiceAutoSendTimers();
  clearVoiceDraftBuffer();
  resetCapturedVoiceFrames();
  resetVoiceVadState();
  voiceWakeScanBuffer.value = "";
  voiceStandbyHeardText.value = "";
  voiceMeterLevel.value = 0;
  voiceUiStage.value = "listening";
  voiceStatusText.value = "AI 正在朗读，已暂停麦克风监听";
}

function clearAssistantSpeechUiState(options = {}) {
  const preferStandbyAfterStop = Boolean(options?.preferStandbyAfterStop);
  const currentStatus = String(voiceStatusText.value || "").trim();
  if (!currentStatus.includes("朗读") && !currentStatus.includes("欢迎语")) {
    if (preferStandbyAfterStop && isListening.value) {
      enterVoiceStandbyMode();
    }
    return;
  }
  if (preferStandbyAfterStop && isListening.value) {
    enterVoiceStandbyMode();
    return;
  }
  if (!isListening.value) {
    voiceStatusText.value = "";
    return;
  }
  if (voiceWakeState.value === "active") {
    voiceStatusText.value = `已恢复通话，请继续说完整指令；${voiceIdleTimeoutMs.value / 1000}s 无新内容后回待机`;
    return;
  }
  voiceStatusText.value = resolveVoiceStandbyMessage();
}

function resumeVoiceListeningAfterAssistantSpeech() {
  if (!voiceListeningSuspendedBySpeech.value) return;
  voiceListeningSuspendedBySpeech.value = false;
  resetCapturedVoiceFrames();
  resetVoiceVadState();
  voiceMeterLevel.value = 0;
  if (!isListening.value) {
    voiceListeningResumeMode = "standby";
    return;
  }
  if (voiceListeningResumeMode === "active") {
    voiceWakeState.value = "active";
    voiceWakeScanBuffer.value = "";
    voiceStandbyHeardText.value = "";
    clearVoiceDraftBuffer();
    voiceUiStage.value = "listening";
    voiceStatusText.value = `已恢复通话，请继续说完整指令；${voiceIdleTimeoutMs.value / 1000}s 无新内容后回待机`;
    scheduleVoiceAutoSend();
  } else {
    enterVoiceStandbyMode();
  }
  voiceListeningResumeMode = "standby";
}

function resolveVoiceStandbyMessage() {
  const heardText = String(voiceStandbyHeardText.value || "").trim();
  if (heardText) {
    return `已听到“${heardText}”，等待唤醒词“${voiceWakePhrase.value}”`;
  }
  return `实时通话待机中，说“${voiceWakePhrase.value}”即可唤醒`;
}

function enterVoiceStandbyMode() {
  voiceWakeState.value = "standby";
  voiceWakeScanBuffer.value = "";
  voiceStandbyHeardText.value = "";
  clearVoiceAutoSendTimers();
  clearVoiceDraftBuffer();
  if (isListening.value) {
    voiceUiStage.value = "listening";
    voiceStatusText.value = resolveVoiceStandbyMessage();
  }
}

function enterVoiceExecutionMode() {
  voiceWakeState.value = "standby";
  voiceWakeScanBuffer.value = "";
  voiceStandbyHeardText.value = "";
  clearVoiceAutoSendTimers();
  clearVoiceDraftBuffer();
  if (isListening.value) {
    voiceUiStage.value = "listening";
    voiceStatusText.value = "AI 正在执行中，请等待当前指令完成。";
  }
}

async function playVoiceReadyPromptTone() {
  if (typeof window === "undefined") return;
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) return;
  let audioContext = voiceAudioContext;
  let shouldCloseAfterPlayback = false;
  if (!audioContext) {
    audioContext = new AudioContextCtor();
    shouldCloseAfterPlayback = true;
  }
  try {
    if (typeof audioContext.resume === "function" && audioContext.state === "suspended") {
      await audioContext.resume();
    }
    const now = Number(audioContext.currentTime || 0);
    const gainNode = audioContext.createGain();
    gainNode.gain.setValueAtTime(0.0001, now);
    gainNode.gain.exponentialRampToValueAtTime(1, now + 0.02);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.26);
    gainNode.connect(audioContext.destination);

    const oscillatorA = audioContext.createOscillator();
    oscillatorA.type = "sine";
    oscillatorA.frequency.setValueAtTime(880, now);
    oscillatorA.connect(gainNode);
    oscillatorA.start(now);
    oscillatorA.stop(now + 0.12);

    const oscillatorB = audioContext.createOscillator();
    oscillatorB.type = "sine";
    oscillatorB.frequency.setValueAtTime(1174, now + 0.12);
    oscillatorB.connect(gainNode);
    oscillatorB.start(now + 0.12);
    oscillatorB.stop(now + 0.26);

    oscillatorB.onended = () => {
      try {
        oscillatorA.disconnect();
        oscillatorB.disconnect();
        gainNode.disconnect();
      } catch {}
      if (shouldCloseAfterPlayback && audioContext && typeof audioContext.close === "function") {
        void audioContext.close().catch(() => {});
      }
    };
  } catch {
    if (shouldCloseAfterPlayback && audioContext && typeof audioContext.close === "function") {
      void audioContext.close().catch(() => {});
    }
  }
}

function enterVoiceActiveMode(initialText = "") {
  const shouldPlayPromptTone = voiceWakeState.value !== "active";
  voiceWakeState.value = "active";
  voiceWakeScanBuffer.value = "";
  voiceStandbyHeardText.value = "";
  clearVoiceDraftBuffer();
  voiceUiStage.value = "listening";
  voiceStatusText.value = `已唤醒，请直接说完整指令；${voiceIdleTimeoutMs.value / 1000}s 无新内容后回待机`;
  const normalizedInitialText = sanitizeVoiceTranscriptText(initialText);
  if (normalizedInitialText) {
    liveVoiceTranscript.value = normalizedInitialText;
    rebuildDraftFromVoiceTranscript();
  }
  if (shouldPlayPromptTone) {
    void playVoiceReadyPromptTone();
  }
  scheduleVoiceAutoSend();
}

async function finalizeWakeInstructionFromIdle() {
  enterVoiceStandbyMode();
}

function scheduleVoiceAutoSend() {
  clearVoiceAutoSendTimers({ preservePending: true });
  if (!isListening.value || voiceWakeState.value !== "active") {
    return;
  }
  shouldAutoSubmitVoiceAfterStop = false;
  const idleMs = voiceIdleTimeoutMs.value || VOICE_AUTO_SEND_IDLE_MS;
  const deadline = Date.now() + idleMs;
  voiceAutoSendCountdownMs.value = idleMs;
  voiceAutoSendCountdownTimer = window.setInterval(() => {
    voiceAutoSendCountdownMs.value = Math.max(0, deadline - Date.now());
  }, 120);
  voiceAutoSendTimer = window.setTimeout(() => {
    clearVoiceAutoSendTimers({ preservePending: true });
    void finalizeWakeInstructionFromIdle();
  }, idleMs);
}

function resetVoiceCapture(options = {}) {
  const { preserveStatus = false } = options;
  clearVoiceAutoSendTimers();
  clearVoiceDraftBuffer();
  voiceWakeScanBuffer.value = "";
  voiceStandbyHeardText.value = "";
  voiceWakeState.value = "standby";
  voiceRequestedStartMode.value = "standby";
  voicePendingRequestIds.clear();
  voiceTranscriptionEpoch += 1;
  voiceTranscriptionQueue = [];
  voiceTranscriptionProcessing = false;
  voiceListeningSuspendedBySpeech.value = false;
  voiceListeningResumeMode = "standby";
  voiceStreamRequestId = "";
  voiceStreamChunkIndex = 0;
  isStoppingVoiceInput.value = false;
  resetVoiceDetectionMetrics();
  resetVoiceVadState();
  if (!preserveStatus) {
    voiceUiStage.value = "idle";
    voiceStatusText.value = "";
  }
}

function clearVoiceTranscript() {
  clearVoiceDraftBuffer();
  if (isListening.value) {
    enterVoiceStandbyMode();
    return;
  }
  resetVoiceCapture({ preserveStatus: false });
}

function resetCapturedVoiceFrames() {
  voiceCapturedFrames = [];
  voiceCapturedSampleCount = 0;
}

function resetVoiceDetectionMetrics() {
  voiceObservedSampleCount = 0;
  voiceDetectedPeakLevel = 0;
  voiceDetectedSpeechFrameCount = 0;
}

function resetVoiceVadState() {
  voiceVadPreRollFrames = [];
  voiceVadPreRollSampleCount = 0;
  voiceVadActiveFrames = [];
  voiceVadActiveSampleCount = 0;
  voiceVadSpeechCandidateCount = 0;
  voiceVadSilenceFrameCount = 0;
  voiceVadNoiseFloor = 0.003;
}

function resolveVoiceFramePeak(frame) {
  let peak = 0;
  for (let index = 0; index < frame.length; index += 1) {
    const magnitude = Math.abs(Number(frame[index] || 0));
    if (magnitude > peak) peak = magnitude;
  }
  return peak;
}

function resolveVoiceFrameRms(frame) {
  if (!frame?.length) return 0;
  let sum = 0;
  for (let index = 0; index < frame.length; index += 1) {
    const value = Number(frame[index] || 0);
    sum += value * value;
  }
  return Math.sqrt(sum / frame.length);
}

function trackVoiceFrameMetrics(frame) {
  if (!frame?.length) return;
  voiceObservedSampleCount += frame.length;
  const peak = resolveVoiceFramePeak(frame);
  if (peak > voiceDetectedPeakLevel) {
    voiceDetectedPeakLevel = peak;
  }
  if (peak >= VOICE_SPEECH_PEAK_THRESHOLD) {
    voiceDetectedSpeechFrameCount += 1;
  }
}

function resolveVoiceEmptyResultMessage() {
  if (!voiceObservedSampleCount) {
    return "未检测到麦克风输入，请检查浏览器录音权限和输入设备";
  }
  if (!voiceDetectedSpeechFrameCount) {
    if (voiceDetectedPeakLevel <= VOICE_LOW_VOLUME_PEAK_THRESHOLD) {
      return "麦克风音量过小，请靠近设备后重试";
    }
    return "未检测到清晰语音，请说话更清楚一些后重试";
  }
  return "已录到语音，但暂未识别出文字，请重试";
}

function cloneVoiceFrame(frame) {
  return new Float32Array(frame);
}

function trimVoiceVadPreRoll(sampleRate) {
  const maxSamples = Math.max(
    1,
    Math.floor((sampleRate * VOICE_VAD_PREROLL_MS) / 1000),
  );
  while (
    voiceVadPreRollFrames.length &&
    voiceVadPreRollSampleCount > maxSamples
  ) {
    const dropped = voiceVadPreRollFrames.shift();
    voiceVadPreRollSampleCount -= dropped?.length || 0;
  }
}

function appendVoiceVadPreRoll(frame, sampleRate) {
  const cloned = cloneVoiceFrame(frame);
  voiceVadPreRollFrames.push(cloned);
  voiceVadPreRollSampleCount += cloned.length;
  trimVoiceVadPreRoll(sampleRate);
}

function appendVoiceVadActiveFrame(frame) {
  const cloned = cloneVoiceFrame(frame);
  voiceVadActiveFrames.push(cloned);
  voiceVadActiveSampleCount += cloned.length;
}

function startVoiceVadUtterance(frame, sampleRate) {
  voiceVadActiveFrames = voiceVadPreRollFrames.map((item) => cloneVoiceFrame(item));
  voiceVadActiveSampleCount = voiceVadActiveFrames.reduce(
    (sum, item) => sum + item.length,
    0,
  );
  voiceVadSilenceFrameCount = 0;
  voiceVadSpeechCandidateCount = 0;
  if (voiceWakeState.value === "active") {
    clearVoiceAutoSendTimers({ preservePending: true });
  }
  voiceUiStage.value = "listening";
  voiceStatusText.value =
    voiceWakeState.value === "active"
      ? "已检测到语音，等待你说完整句子..."
      : `正在监听唤醒词“${voiceWakePhrase.value}”`;
}

function buildVoiceWavBlob(pcmBytes, sampleRate) {
  const buffer = new ArrayBuffer(44 + pcmBytes.length);
  const view = new DataView(buffer);
  const writeAscii = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };
  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + pcmBytes.length, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(36, "data");
  view.setUint32(40, pcmBytes.length, true);
  new Uint8Array(buffer, 44).set(pcmBytes);
  return new Blob([buffer], { type: "audio/wav" });
}

async function transcribeVoiceVadUtterance(samples, sourceSampleRate) {
  if (!samples?.length) return "";
  const normalizedSamples = downsampleAudioBuffer(
    samples,
    Number(sourceSampleRate || VOICE_TARGET_SAMPLE_RATE),
    VOICE_TARGET_SAMPLE_RATE,
  );
  const pcmBytes = float32ToPcm16Bytes(normalizeVoiceSamples(normalizedSamples));
  if (!pcmBytes.length) return "";
  const formData = new FormData();
  formData.append(
    "audio",
    buildVoiceWavBlob(pcmBytes, VOICE_TARGET_SAMPLE_RATE),
    "global-assistant-utterance.wav",
  );
  formData.append("language", "zh");
  formData.append("prompt", voiceTranscriptionPrompt.value);
  formData.append("is_final", "true");
  const payload = await api.post("/projects/chat/global/voice-input/transcriptions", formData);
  return sanitizeVoiceTranscriptText(payload?.text || "");
}

function sanitizeVoiceTranscriptText(text) {
  let normalized = String(text || "")
    .replace(/[#＃]+/g, "")
    .replace(/\s*\n+\s*/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  let previous = "";
  while (normalized && normalized !== previous) {
    previous = normalized;
    normalized = normalized.replace(/(.{3,}?)\1+/g, "$1").trim();
  }
  return normalized;
}

function buildVoiceTranscriptDisplayText() {
  const parts = [
    ...confirmedVoiceSegments.value.map((item) =>
      sanitizeVoiceTranscriptText(item),
    ),
    sanitizeVoiceTranscriptText(liveVoiceTranscript.value),
  ].filter(Boolean);
  return parts.join("");
}

function rebuildDraftFromVoiceTranscript() {
  recognizedVoiceDraft.value = confirmedVoiceSegments.value
    .map((item) => sanitizeVoiceTranscriptText(item))
    .filter(Boolean)
    .join("");
  voiceDraftText.value = buildVoiceTranscriptDisplayText();
}

function canonicalizeVoiceTranscriptText(text) {
  return sanitizeVoiceTranscriptText(text)
    .replace(/\s+/g, "")
    .replace(/[，。！？、,.!?]/g, "")
    .trim();
}

function resolveDirectRouteCommand(text) {
  let normalized = canonicalizeVoiceTranscriptText(text);
  if (!normalized) return null;
  const wakeCanonical = canonicalizeVoiceTranscriptText(voiceWakePhrase.value);
  if (wakeCanonical && normalized.startsWith(wakeCanonical)) {
    normalized = normalized.slice(wakeCanonical.length);
  }
  normalized = normalized.replace(/^(请|请你|帮我|麻烦|你帮我|给我|你)/, "");
  if (!normalized) return null;
  const navigationVerb = /^(进入|打开|去|前往|跳到|切到|切换到)/;
  for (const item of DIRECT_ROUTE_COMMANDS) {
    const aliases = Array.isArray(item.aliases) ? item.aliases : [];
    for (const alias of aliases) {
      const aliasCanonical = canonicalizeVoiceTranscriptText(alias);
      if (!aliasCanonical) continue;
      if (
        normalized === aliasCanonical ||
        normalized === `${aliasCanonical}页面` ||
        normalized === `${aliasCanonical}页` ||
        normalized === `到${aliasCanonical}` ||
        normalized === `去到${aliasCanonical}` ||
        normalized === `前往${aliasCanonical}` ||
        normalized === `打开${aliasCanonical}` ||
        normalized === `进入${aliasCanonical}` ||
        normalized === `跳到${aliasCanonical}` ||
        normalized === `切到${aliasCanonical}` ||
        normalized === `切换到${aliasCanonical}` ||
        normalized === `${aliasCanonical}打开` ||
        navigationVerb.test(normalized) &&
          normalized.replace(navigationVerb, "") === aliasCanonical
      ) {
        return item;
      }
    }
  }
  return null;
}

async function tryHandleDirectRouteCommand(text, options = {}) {
  const matched = resolveDirectRouteCommand(text);
  if (!matched) return false;
  const normalizedText = String(text || "").trim();
  const currentPath = String(route.path || "").trim();
  if (options?.openPanel !== false) {
    panelOpen.value = true;
  }
  if (options?.recordConversation !== false && normalizedText) {
    messages.value.push(
      normalizeMessage({
        id: createLocalMessageId(),
        role: "user",
        content: normalizedText,
        created_at: new Date().toISOString(),
      }),
    );
  }
  try {
    if (currentPath !== matched.path) {
      await router.push(matched.path);
    }
  } catch {}
  const assistantText =
    currentPath === matched.path
      ? `当前已在${matched.label}页面。`
      : `已打开${matched.label}页面（${matched.path}）。`;
  if (options?.recordConversation !== false) {
    messages.value.push(
      normalizeMessage({
        id: createLocalMessageId(),
        role: "assistant",
        content: assistantText,
        created_at: new Date().toISOString(),
      }),
    );
  }
  if (isListening.value) {
    enterVoiceStandbyMode();
    voiceStatusText.value = `${assistantText} 说“${voiceWakePhrase.value}”即可继续。`;
  } else {
    ElMessage.success(assistantText);
  }
  scrollToBottom();
  return true;
}

function mergeVoiceTranscriptText(currentText, nextText) {
  const current = sanitizeVoiceTranscriptText(currentText);
  const next = sanitizeVoiceTranscriptText(nextText);
  const currentCanonical = canonicalizeVoiceTranscriptText(current);
  const nextCanonical = canonicalizeVoiceTranscriptText(next);
  if (!nextCanonical) return current;
  if (!currentCanonical) return next;
  if (currentCanonical === nextCanonical) {
    return next.length >= current.length ? next : current;
  }
  if (nextCanonical.includes(currentCanonical)) {
    return next;
  }
  if (currentCanonical.includes(nextCanonical)) {
    return current;
  }
  const overlapLength = resolveVoiceTranscriptOverlapLength(current, next);
  if (overlapLength > 0) {
    return `${current}${next.slice(overlapLength)}`;
  }
  return `${current}${next}`;
}

function resolveVoiceTranscriptOverlapLength(currentText, nextText) {
  const current = String(currentText || "");
  const next = String(nextText || "");
  const maxLength = Math.min(current.length, next.length);
  for (let size = maxLength; size > 0; size -= 1) {
    const currentSuffix = current.slice(-size);
    const nextPrefix = next.slice(0, size);
    if (currentSuffix === nextPrefix) {
      return size;
    }
    const currentCanonical = canonicalizeVoiceTranscriptText(currentSuffix);
    const nextCanonical = canonicalizeVoiceTranscriptText(nextPrefix);
    if (currentCanonical && currentCanonical === nextCanonical) {
      return size;
    }
  }
  return 0;
}

function detectWakePhraseFromTranscript(text) {
  const normalized = sanitizeVoiceTranscriptText(text);
  if (!normalized) {
    return { matched: false, remainder: "", heardText: "" };
  }
  voiceWakeScanBuffer.value = mergeVoiceTranscriptText(
    voiceWakeScanBuffer.value,
    normalized,
  ).slice(-96);
  const wakeCanonical = canonicalizeVoiceTranscriptText(voiceWakePhrase.value);
  const bufferCanonical = canonicalizeVoiceTranscriptText(voiceWakeScanBuffer.value);
  if (!wakeCanonical) {
    return { matched: false, remainder: "", heardText: normalized };
  }
  let matchedIndex = bufferCanonical.lastIndexOf(wakeCanonical);
  if (matchedIndex < 0 && wakeCanonical.length >= 4) {
    const wakePrefix = wakeCanonical.slice(0, Math.ceil(wakeCanonical.length / 2));
    const wakeSuffix = wakeCanonical.slice(Math.floor(wakeCanonical.length / 2));
    const prefixIndex = bufferCanonical.lastIndexOf(wakePrefix);
    if (prefixIndex >= 0) {
      const suffixIndex = bufferCanonical.indexOf(
        wakeSuffix,
        prefixIndex + Math.max(1, wakePrefix.length - 1),
      );
      if (suffixIndex >= 0) {
        matchedIndex = prefixIndex;
      }
    }
  }
  if (matchedIndex < 0) {
    return { matched: false, remainder: "", heardText: normalized };
  }
  const remainder = bufferCanonical
    .slice(matchedIndex + wakeCanonical.length)
    .trim();
  return { matched: true, remainder, heardText: normalized };
}

function updateVoiceTranscriptPreview(text) {
  const normalized = sanitizeVoiceTranscriptText(text);
  if (!normalized) return;
  liveVoiceTranscript.value = mergeVoiceTranscriptText(
    liveVoiceTranscript.value,
    normalized,
  );
  rebuildDraftFromVoiceTranscript();
  scheduleVoiceAutoSend();
}

function replaceVoiceTranscriptWithFinalText(text) {
  const candidate = sanitizeVoiceTranscriptText(text);
  if (!candidate) return;
  confirmedVoiceSegments.value = [candidate];
  liveVoiceTranscript.value = "";
  rebuildDraftFromVoiceTranscript();
  if (isListening.value && voiceWakeState.value === "active") {
    scheduleVoiceAutoSend();
  }
}

function stopMediaStream() {
  if (!mediaStream) return;
  mediaStream.getTracks().forEach((track) => track.stop());
  mediaStream = null;
}

function teardownAudioProcessingGraph() {
  if (voiceFlushTimer) {
    window.clearInterval(voiceFlushTimer);
    voiceFlushTimer = null;
  }
  stopVoiceMeterDecay();
  voiceMeterLevel.value = 0;
  if (voiceProcessorNode) {
    try {
      voiceProcessorNode.disconnect();
    } catch {}
  }
  if (voiceSourceNode) {
    try {
      voiceSourceNode.disconnect();
    } catch {}
  }
  if (voiceMuteNode) {
    try {
      voiceMuteNode.disconnect();
    } catch {}
  }
  voiceProcessorNode = null;
  voiceSourceNode = null;
  voiceMuteNode = null;
  if (voiceAudioContext) {
    try {
      voiceAudioContext.close();
    } catch {}
  }
  voiceAudioContext = null;
}

function mergeFloat32Chunks(chunks) {
  const totalLength = chunks.reduce((sum, item) => sum + item.length, 0);
  const merged = new Float32Array(totalLength);
  let offset = 0;
  chunks.forEach((item) => {
    merged.set(item, offset);
    offset += item.length;
  });
  return merged;
}

function downsampleAudioBuffer(buffer, sourceRate, targetRate) {
  if (!buffer.length) return new Float32Array(0);
  if (targetRate >= sourceRate) return buffer;
  const ratio = sourceRate / targetRate;
  const nextLength = Math.max(1, Math.round(buffer.length / ratio));
  const result = new Float32Array(nextLength);
  let offset = 0;
  for (let index = 0; index < nextLength; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(buffer.length, Math.floor((index + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let pointer = start; pointer < end; pointer += 1) {
      sum += buffer[pointer];
      count += 1;
    }
    result[offset] = count ? sum / count : buffer[start] || 0;
    offset += 1;
  }
  return result;
}

function float32ToPcm16Bytes(samples) {
  const buffer = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buffer);
  samples.forEach((sample, index) => {
    const normalized = Math.max(-1, Math.min(1, sample));
    view.setInt16(
      index * 2,
      normalized < 0 ? normalized * 0x8000 : normalized * 0x7fff,
      true,
    );
  });
  return new Uint8Array(buffer);
}

function normalizeVoiceSamples(samples) {
  if (!samples.length) return samples;
  const gated = new Float32Array(samples.length);
  let peak = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const rawValue = Number(samples[index] || 0);
    const magnitude = Math.abs(rawValue);
    if (magnitude < VOICE_SAMPLE_NOISE_GATE_THRESHOLD) {
      gated[index] = 0;
      continue;
    }
    const adjustedValue =
      rawValue > 0
        ? rawValue - VOICE_SAMPLE_NOISE_GATE_THRESHOLD * 0.35
        : rawValue + VOICE_SAMPLE_NOISE_GATE_THRESHOLD * 0.35;
    gated[index] = adjustedValue;
    const adjustedMagnitude = Math.abs(adjustedValue);
    if (adjustedMagnitude > peak) {
      peak = adjustedMagnitude;
    }
  }
  if (!peak || peak >= 0.75) {
    return gated;
  }
  const gain = Math.min(VOICE_NORMALIZE_MAX_GAIN, 0.82 / peak);
  if (gain <= 1.05) {
    return gated;
  }
  const normalized = new Float32Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    normalized[index] = Math.max(-1, Math.min(1, gated[index] * gain));
  }
  return normalized;
}

function resetVoiceVadActiveUtterance() {
  voiceVadActiveFrames = [];
  voiceVadActiveSampleCount = 0;
  voiceVadSilenceFrameCount = 0;
  voiceVadSpeechCandidateCount = 0;
}

function resolveVoiceVadThresholds() {
  const noiseFloor = Math.max(0.0025, voiceVadNoiseFloor);
  return {
    startPeak: Math.max(VOICE_SPEECH_PEAK_THRESHOLD, noiseFloor * 5.2),
    continuePeak: Math.max(VOICE_LOW_VOLUME_PEAK_THRESHOLD, noiseFloor * 3.6),
    startRms: Math.max(VOICE_VAD_MIN_RMS_THRESHOLD, noiseFloor * 2.8),
    continueRms: Math.max(VOICE_VAD_CONTINUE_RMS_THRESHOLD, noiseFloor * 1.9),
  };
}

function queueVoiceVadUtterance(samples, sourceSampleRate, modeSnapshot) {
  voiceTranscriptionQueue.push({
    epoch: voiceTranscriptionEpoch,
    samples,
    sourceSampleRate,
    modeSnapshot,
  });
  void processVoiceVadTranscriptionQueue();
}

async function handleVoiceVadTranscript(text, modeSnapshot) {
  const normalized = sanitizeVoiceTranscriptText(text);
  if (!normalized) {
    if (isListening.value && voiceWakeState.value === "active") {
      voiceUiStage.value = "listening";
      voiceStatusText.value = "已听到语音，但未识别清楚，请再说一次。";
      scheduleVoiceAutoSend();
    } else if (isListening.value) {
      voiceUiStage.value = "listening";
      voiceStatusText.value = resolveVoiceStandbyMessage();
    }
    return;
  }
  if (modeSnapshot === "standby") {
    if (loading.value) {
      voiceUiStage.value = "listening";
      voiceStatusText.value = "AI 正在回复中，暂不处理新的语音指令。";
      return;
    }
    const wakeResult = detectWakePhraseFromTranscript(normalized);
    if (!wakeResult.matched) {
      if (
        await tryHandleDirectRouteCommand(normalized, {
          openPanel: false,
          recordConversation: true,
        })
      ) {
        return;
      }
      voiceStandbyHeardText.value = normalized;
      voiceUiStage.value = "listening";
      voiceStatusText.value = resolveVoiceStandbyMessage();
      return;
    }
    const remainder = sanitizeVoiceTranscriptText(wakeResult.remainder);
    if (!remainder) {
      enterVoiceActiveMode();
      return;
    }
    replaceVoiceTranscriptWithFinalText(remainder);
    voiceStatusText.value = "识别完成，正在自动发送...";
    await sendMessage(remainder, { openPanel: false, fromVoice: true });
    return;
  }
  if (loading.value) {
    voiceUiStage.value = "listening";
    voiceStatusText.value = "AI 正在回复中，请稍候再说下一句。";
    return;
  }
  replaceVoiceTranscriptWithFinalText(normalized);
  voiceStatusText.value = "识别完成，正在自动发送...";
  await sendMessage(normalized, { openPanel: false, fromVoice: true });
}

async function processVoiceVadTranscriptionQueue() {
  if (voiceTranscriptionProcessing) return;
  voiceTranscriptionProcessing = true;
  try {
    while (voiceTranscriptionQueue.length) {
      const item = voiceTranscriptionQueue.shift();
      if (!item || item.epoch !== voiceTranscriptionEpoch) continue;
      try {
        voiceUiStage.value = isListening.value ? "listening" : "recognizing";
        voiceStatusText.value =
          item.modeSnapshot === "standby"
            ? `正在识别唤醒语句“${voiceWakePhrase.value}”...`
            : "正在识别语音指令...";
        const transcriptText = await transcribeVoiceVadUtterance(
          item.samples,
          item.sourceSampleRate,
        );
        if (item.epoch !== voiceTranscriptionEpoch) continue;
        await handleVoiceVadTranscript(transcriptText, item.modeSnapshot);
      } catch (err) {
        if (item.epoch !== voiceTranscriptionEpoch) continue;
        const message = sanitizeAssistantErrorMessage(
          err?.detail || err?.message,
          "语音转写暂时不可用，请稍后重试",
        );
        if (isListening.value && voiceWakeState.value === "active") {
          voiceUiStage.value = "listening";
          voiceStatusText.value = message;
          scheduleVoiceAutoSend();
        } else if (isListening.value) {
          voiceUiStage.value = "listening";
          voiceStatusText.value = message;
        } else {
          voiceUiStage.value = "error";
          voiceStatusText.value = message;
        }
      }
    }
  } finally {
    voiceTranscriptionProcessing = false;
    if (!isListening.value) return;
    if (voiceWakeState.value === "active") {
      if (!loading.value) {
        voiceUiStage.value = "listening";
        voiceStatusText.value =
          String(voiceStatusText.value || "").trim() ||
          `已唤醒，请直接说完整指令；${voiceIdleTimeoutMs.value / 1000}s 无新内容后回待机`;
      }
      scheduleVoiceAutoSend();
      return;
    }
    voiceUiStage.value = "listening";
    if (
      !String(voiceStatusText.value || "").trim() ||
      String(voiceStatusText.value || "").includes("正在识别")
    ) {
      voiceStatusText.value = resolveVoiceStandbyMessage();
    }
  }
}

function finalizeVoiceVadUtterance(sampleRate) {
  if (!voiceVadActiveSampleCount || !voiceVadActiveFrames.length) {
    resetVoiceVadActiveUtterance();
    return false;
  }
  const minSamples = Math.max(
    1,
    Math.floor((sampleRate * VOICE_VAD_MIN_UTTERANCE_MS) / 1000),
  );
  if (voiceVadActiveSampleCount < minSamples) {
    resetVoiceVadActiveUtterance();
    if (isListening.value && voiceWakeState.value === "active") {
      voiceStatusText.value = "已检测到较短语音，请再说完整一点。";
      scheduleVoiceAutoSend();
    }
    return false;
  }
  const modeSnapshot = voiceWakeState.value === "active" ? "active" : "standby";
  const mergedSamples = mergeFloat32Chunks(voiceVadActiveFrames);
  resetVoiceVadActiveUtterance();
  queueVoiceVadUtterance(mergedSamples, sampleRate, modeSnapshot);
  return true;
}

function processVoiceVadFrame(frame, sampleRate) {
  if (!isListening.value) return;
  appendVoiceVadPreRoll(frame, sampleRate);
  const peak = resolveVoiceFramePeak(frame);
  const rms = resolveVoiceFrameRms(frame);
  const thresholds = resolveVoiceVadThresholds();
  const isSpeechFrame =
    voiceVadActiveSampleCount > 0
      ? peak >= thresholds.continuePeak || rms >= thresholds.continueRms
      : peak >= thresholds.startPeak || rms >= thresholds.startRms;

  if (voiceVadActiveSampleCount <= 0 && !isSpeechFrame) {
    voiceVadNoiseFloor = voiceVadNoiseFloor * 0.92 + rms * 0.08;
  }

  if (!voiceVadActiveSampleCount) {
    if (loading.value && voiceWakeState.value === "standby") {
      voiceVadSpeechCandidateCount = 0;
      return;
    }
    if (isSpeechFrame) {
      voiceVadSpeechCandidateCount += 1;
      if (voiceVadSpeechCandidateCount >= VOICE_VAD_START_FRAMES) {
        startVoiceVadUtterance(frame, sampleRate);
      }
      return;
    }
    voiceVadSpeechCandidateCount = 0;
    return;
  }

  appendVoiceVadActiveFrame(frame);
  if (isSpeechFrame) {
    voiceVadSilenceFrameCount = 0;
  } else {
    voiceVadSilenceFrameCount += frame.length;
  }

  const maxUtteranceSamples = Math.max(
    1,
    Math.floor((sampleRate * VOICE_VAD_MAX_UTTERANCE_MS) / 1000),
  );
  const endSilenceSamples = Math.max(
    1,
    Math.floor((sampleRate * VOICE_VAD_END_SILENCE_MS) / 1000),
  );

  if (voiceVadActiveSampleCount >= maxUtteranceSamples) {
    void finalizeVoiceVadUtterance(sampleRate);
    return;
  }
  if (voiceVadSilenceFrameCount >= endSilenceSamples) {
    void finalizeVoiceVadUtterance(sampleRate);
  }
}

function encodeBase64Bytes(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return window.btoa(binary);
}

async function requestVoiceInputStream() {
  const selectedDeviceId = resolveSelectedVoiceInputDeviceId();
  const baseAudioOptions = {
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: selectedDeviceId
        ? {
            ...baseAudioOptions,
            deviceId: { exact: selectedDeviceId },
          }
        : baseAudioOptions,
    });
  } catch (err) {
    const errorName = String(err?.name || "").trim();
    if (!selectedDeviceId) {
      throw err;
    }
    if (!["OverconstrainedError", "NotFoundError"].includes(errorName)) {
      throw err;
    }
    selectedVoiceInputDeviceId.value = VOICE_INPUT_DEFAULT_VALUE;
    return navigator.mediaDevices.getUserMedia({
      audio: baseAudioOptions,
    });
  }
}

async function flushCapturedVoiceChunk(isFinal = false) {
  if (!voiceCapturedFrames.length) return;
  const sourceSampleRate = Number(
    voiceAudioContext?.sampleRate || VOICE_TARGET_SAMPLE_RATE,
  );
  const minSampleCount = Math.max(
    1,
    Math.floor((sourceSampleRate * VOICE_MIN_CHUNK_MS) / 1000),
  );
  if (!isFinal && voiceCapturedSampleCount < minSampleCount) return;
  const chunkFrames = voiceCapturedFrames;
  resetCapturedVoiceFrames();
  const merged = mergeFloat32Chunks(chunkFrames);
  const samples = downsampleAudioBuffer(
    merged,
    Number(sourceSampleRate || VOICE_TARGET_SAMPLE_RATE),
    VOICE_TARGET_SAMPLE_RATE,
  );
  const pcmBytes = float32ToPcm16Bytes(normalizeVoiceSamples(samples));
  if (!pcmBytes.length || !voiceStreamRequestId) return;
  const client = await ensureWsClient();
  voiceStreamChunkIndex += 1;
  client.send({
    type: "voice_chunk",
    request_id: voiceStreamRequestId,
    chunk_index: voiceStreamChunkIndex,
    sample_rate: VOICE_TARGET_SAMPLE_RATE,
    audio_base64: encodeBase64Bytes(pcmBytes),
    is_final: Boolean(isFinal),
  });
}

function cancelActiveVoiceStream() {
  clearVoiceAutoSendTimers();
  voiceTranscriptionEpoch += 1;
  voiceTranscriptionQueue = [];
  voiceTranscriptionProcessing = false;
  resetVoiceVadState();
  voicePendingRequestIds.clear();
  if (!voiceStreamRequestId || !wsClient.value?.isOpen()) {
    voiceStreamRequestId = "";
    voiceStreamChunkIndex = 0;
    return;
  }
  wsClient.value.send({
    type: "voice_cancel",
    request_id: voiceStreamRequestId,
  });
  voiceStreamRequestId = "";
  voiceStreamChunkIndex = 0;
}

async function startVoiceInput(options = {}) {
  clearPendingVoiceStartTimer();
  const activateOnStart = Boolean(options?.activate);
  voiceRequestedStartMode.value = activateOnStart ? "active" : "standby";
  if (!browserAudioCaptureSupported()) {
    ElMessage.warning("当前浏览器暂不支持录音");
    return;
  }
  if (!voiceRuntimeAvailable.value) {
    ElMessage.warning(voiceRuntime.value?.reason || "当前账号不可使用语音输入");
    return;
  }
  let sessionId = String(currentChatSessionId.value || "").trim();
  if (!sessionId) {
    sessionId = createEphemeralSessionId();
    currentChatSessionId.value = sessionId;
  }
  resetVoiceCapture({ preserveStatus: true });
  resetCapturedVoiceFrames();
  resetVoiceDetectionMetrics();
  resetVoiceVadState();
  isStoppingVoiceInput.value = false;
  voiceUiStage.value = "requesting";
  voiceStatusText.value = "正在请求麦克风权限...";
  try {
    voicePendingRequestIds.clear();
    voiceWakeState.value = "standby";
    voiceWakeScanBuffer.value = "";
    mediaStream = await requestVoiceInputStream();
    updateVoiceActiveTrackInfo(mediaStream);
    await refreshVoiceInputDevices();
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    voiceAudioContext = new AudioContextCtor();
    if (typeof voiceAudioContext.resume === "function") {
      await voiceAudioContext.resume();
    }
    voiceSourceNode = voiceAudioContext.createMediaStreamSource(mediaStream);
    voiceProcessorNode = voiceAudioContext.createScriptProcessor(4096, 1, 1);
    voiceMuteNode = voiceAudioContext.createGain();
    voiceMuteNode.gain.value = 0;
    voiceProcessorNode.onaudioprocess = (event) => {
      if (!isListening.value || voiceListeningSuspendedBySpeech.value) return;
      const channelData = event.inputBuffer.getChannelData(0);
      if (!channelData?.length) return;
      const cloned = new Float32Array(channelData);
      trackVoiceFrameMetrics(cloned);
      updateVoiceMeterLevel(cloned);
      processVoiceVadFrame(cloned, Number(voiceAudioContext?.sampleRate || VOICE_TARGET_SAMPLE_RATE));
    };
    voiceSourceNode.connect(voiceProcessorNode);
    voiceProcessorNode.connect(voiceMuteNode);
    voiceMuteNode.connect(voiceAudioContext.destination);
    isListening.value = true;
    voiceUiStage.value = "listening";
    voiceMeterLevel.value = 0;
    startVoiceMeterDecay();
    if (activateOnStart) {
      enterVoiceActiveMode();
    } else {
      enterVoiceStandbyMode();
    }
  } catch (err) {
    cancelActiveVoiceStream();
    teardownAudioProcessingGraph();
    stopMediaStream();
    isListening.value = false;
    voiceUiStage.value = "error";
    voiceStatusText.value = "麦克风权限被拒绝";
    voiceRequestedStartMode.value = "standby";
    ElMessage.warning(err?.message || "请允许浏览器访问麦克风后再试");
  }
}

async function stopVoiceInput(options = {}) {
  if (!isListening.value && !voiceAudioContext) return;
  shouldAutoSubmitVoiceAfterStop = Boolean(options?.autoSubmit ?? true);
  clearVoiceAutoSendTimers({ preservePending: shouldAutoSubmitVoiceAfterStop });
  isStoppingVoiceInput.value = true;
  voiceUiStage.value = "stopping";
  voiceStatusText.value = "结束收音中...";
  const sourceSampleRate = Number(
    voiceAudioContext?.sampleRate || VOICE_TARGET_SAMPLE_RATE,
  );
  const minFinalizeSamples = Math.max(
    1,
    Math.floor((sourceSampleRate * VOICE_VAD_MIN_UTTERANCE_MS) / 1000),
  );
  const shouldFinalizeOnStop =
    shouldAutoSubmitVoiceAfterStop &&
    voiceVadActiveSampleCount >= minFinalizeSamples;
  try {
    if (voiceFlushTimer) {
      window.clearInterval(voiceFlushTimer);
      voiceFlushTimer = null;
    }
    if (shouldFinalizeOnStop) {
      finalizeVoiceVadUtterance(sourceSampleRate);
    } else {
      voiceTranscriptionEpoch += 1;
      voiceTranscriptionQueue = [];
    }
    teardownAudioProcessingGraph();
    stopMediaStream();
    isListening.value = false;
    voiceListeningSuspendedBySpeech.value = false;
    voiceListeningResumeMode = "standby";
    resetVoiceVadState();
    voicePendingRequestIds.clear();
    voiceStreamRequestId = "";
    voiceStreamChunkIndex = 0;
    isStoppingVoiceInput.value = false;
    voiceUiStage.value = shouldFinalizeOnStop ? "recognizing" : "idle";
    voiceStatusText.value = shouldFinalizeOnStop
      ? "正在识别最后一句语音..."
      : "实时通话已关闭";
    voiceWakeState.value = "standby";
    voiceWakeScanBuffer.value = "";
  } catch (err) {
    cancelActiveVoiceStream();
    teardownAudioProcessingGraph();
    stopMediaStream();
    clearVoiceAutoSendTimers();
    isListening.value = false;
    isStoppingVoiceInput.value = false;
    voiceListeningSuspendedBySpeech.value = false;
    voiceListeningResumeMode = "standby";
    voiceUiStage.value = "error";
    voiceStatusText.value = "结束录音失败";
    ElMessage.warning(err?.message || "结束录音失败");
  }
}

function toggleVoiceInput() {
  markAssistantInteractionGesture();
  if (loading.value && !isListening.value) {
    ElMessage.warning("请等待当前回答完成后再发起语音输入");
    return;
  }
  if (isListening.value) {
    void stopVoiceInput({ autoSubmit: false });
    return;
  }
  void startVoiceInput();
}

function teardownAssistant() {
  stopAssistantFabDrag();
  if (typeof window !== "undefined" && assistantFabResizeRafId) {
    window.cancelAnimationFrame(assistantFabResizeRafId);
    assistantFabResizeRafId = 0;
  }
  clearPendingVoiceStartTimer();
  stopAssistantSpeech();
  clearSpeechAudioCache();
  suppressedAutoPlayMessageIds.clear();
  stopSpeechVoiceRetry();
  speechVoiceLoading.value = false;
  speechVoiceRetryCount = 0;
  pendingGreetingMessageId = "";
  hasAssistantInteractionGesture = false;
  teardownAudioProcessingGraph();
  stopMediaStream();
  cancelActiveVoiceStream();
  rejectPendingRequests("助手已关闭");
  disconnectWs("teardown");
  messages.value = [];
  currentChatSessionId.value = "";
  typedDraftText.value = "";
  panelOpen.value = false;
  settingsDialogOpen.value = false;
  panelFullscreen.value = false;
  voiceRuntime.value = {
    enabled: false,
    available: false,
    mode: "",
    reason: "",
    global_assistant_enabled: globalAssistantEnabled.value,
    greeting_enabled: false,
    greeting_text: DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
    transcription_prompt: DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
    wake_phrase: "你好助手",
    idle_timeout_sec: 5,
  };
  speechRuntime.value = {
    enabled: false,
    available: false,
    mode: "",
    reason: "",
    provider_id: "",
    provider_name: "",
    model_name: "",
    voice: "",
    greeting_audio_available: false,
    greeting_audio_signature: "",
  };
  voiceInputDevices.value = [];
  selectedVoiceInputDeviceId.value = normalizeVoiceInputSelectionValue(
    loadStoredVoiceInputDeviceId(),
  );
  voiceActiveTrackInfo.value = createEmptyVoiceTrackInfo();
  voiceTrackDetailsExpanded.value = false;
  if (!getStoredToken()) {
    persistGreetingSeenState(false);
  }
  resetVoiceCapture();
}

watch(selectedVoiceInputDeviceId, (value) => {
  persistVoiceInputDeviceId(value);
});

watch(selectedSpeechVoiceUri, (value) => {
  persistSpeechVoiceUri(value);
  clearSpeechAudioCache();
});

watch(autoPlayAssistantSpeech, (value) => {
  persistAutoPlayAssistantSpeech(value);
});

watch(speechRuntimeCacheSignature, (value, oldValue) => {
  if (value === oldValue) return;
  clearSpeechAudioCache();
});

watch(backendSpeechPlaybackEnabled, (value, oldValue) => {
  if (value === oldValue) return;
  clearSpeechAudioCache();
});

watch(
  [messages, currentChatSessionId, typedDraftText, panelOpen],
  () => {
    persistAssistantCache();
  },
  { deep: true },
);

watch(
  () => panelOpen.value,
  (value) => {
    if (!value) {
      settingsDialogOpen.value = false;
      return;
    }
    if (!shouldRender.value) return;
    void fetchSpeechRuntime();
    if (!backendSpeechPlaybackEnabled.value) {
      refreshSpeechVoiceOptions({ forceRetry: true });
    }
    void refreshVoiceInputDevices();
  },
);

watch(
  () => settingsDialogOpen.value,
  (value) => {
    if (!value) return;
    void fetchSpeechRuntime();
    void refreshVoiceInputDevices();
    if (!backendSpeechPlaybackEnabled.value) {
      refreshSpeechVoiceOptions({ forceRetry: true });
    }
  },
);

watch(
  () => authStateVersion.value,
  () => {
    nextTick(() => {
      syncAssistantFabPosition({ preferStored: true });
    });
    if (!shouldRender.value) {
      teardownAssistant();
      return;
    }
    void initializeAssistant();
  },
);

watch(
  () => shouldRender.value,
  (value) => {
    if (!value) {
      teardownAssistant();
      return;
    }
    nextTick(() => {
      syncAssistantFabPosition({ preferStored: true });
    });
    void initializeAssistant();
  },
);

function handleSystemConfigUpdated(event) {
  const config =
    event?.detail?.config && typeof event.detail.config === "object"
      ? event.detail.config
      : {};
  globalAssistantEnabled.value = config.global_assistant_enabled !== false;
  if (!globalAssistantEnabled.value) {
    teardownAssistant();
    return;
  }
  if (getStoredToken()) {
    void initializeAssistant();
  }
}

onMounted(() => {
  window.addEventListener("resize", handleAssistantFabWindowResize);
  window.addEventListener(SYSTEM_CONFIG_UPDATED_EVENT, handleSystemConfigUpdated);
  if (!shouldRender.value) return;
  ensureAssistantBrowserBridgeInstalled();
  selectedVoiceInputDeviceId.value = normalizeVoiceInputSelectionValue(
    loadStoredVoiceInputDeviceId(),
  );
  selectedSpeechVoiceUri.value = loadStoredSpeechVoiceUri();
  autoPlayAssistantSpeech.value = loadStoredAutoPlayAssistantSpeech();
  if (window.navigator?.mediaDevices?.addEventListener) {
    window.navigator.mediaDevices.addEventListener("devicechange", refreshVoiceInputDevices);
  }
  if (window.speechSynthesis?.addEventListener) {
    window.speechSynthesis.addEventListener("voiceschanged", refreshSpeechVoiceOptions);
  }
  refreshSpeechVoiceOptions({ forceRetry: true });
  nextTick(() => {
    syncAssistantFabPosition({ preferStored: true });
  });
  void initializeAssistant();
});

onBeforeUnmount(() => {
  window.removeEventListener(SYSTEM_CONFIG_UPDATED_EVENT, handleSystemConfigUpdated);
  stopSpeechVoiceRetry();
  if (window.navigator?.mediaDevices?.removeEventListener) {
    window.navigator.mediaDevices.removeEventListener("devicechange", refreshVoiceInputDevices);
  }
  if (window.speechSynthesis?.removeEventListener) {
    window.speechSynthesis.removeEventListener("voiceschanged", refreshSpeechVoiceOptions);
  }
  window.removeEventListener("resize", handleAssistantFabWindowResize);
  stopAssistantFabDrag();
  if (typeof window !== "undefined" && assistantFabResizeRafId) {
    window.cancelAnimationFrame(assistantFabResizeRafId);
    assistantFabResizeRafId = 0;
  }
  teardownAssistant();
});
</script>

<style scoped>
.global-ai-assistant {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 3200;
}

.assistant-shell {
  width: min(560px, calc(100vw - 24px));
  min-width: min(440px, calc(100vw - 24px));
  min-height: 620px;
  max-width: calc(100vw - 24px);
  max-height: min(86vh, 920px);
  display: grid;
  grid-template-rows: auto minmax(180px, 1fr) auto;
  gap: 12px;
  padding: 18px;
  border-radius: 28px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background:
    radial-gradient(
      circle at top right,
      rgba(14, 165, 233, 0.2),
      transparent 34%
    ),
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.96) 0%,
      rgba(241, 245, 249, 0.98) 100%
    );
  box-shadow:
    0 28px 80px rgba(15, 23, 42, 0.16),
    0 8px 24px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(18px);
  overflow: hidden;
  resize: both;
}

.assistant-shell--fullscreen {
  width: min(calc(100vw - 24px), 1440px);
  min-width: min(calc(100vw - 24px), 1440px);
  height: calc(100vh - 24px);
  max-height: calc(100vh - 24px);
  resize: none;
}

.assistant-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.assistant-header__copy {
  min-width: 0;
}

.assistant-header__actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.assistant-header__toggle {
  position: relative;
  color: #64748b;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.assistant-header__toggle:hover {
  transform: translateY(-1px);
  color: #0f172a;
  background: rgba(255, 255, 255, 0.94);
  border-color: rgba(100, 116, 139, 0.24);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.1);
}

.assistant-header__toggle.is-active {
  color: #0f766e;
  background: rgba(15, 118, 110, 0.12);
  border-color: rgba(15, 118, 110, 0.2);
  box-shadow: 0 10px 24px rgba(15, 118, 110, 0.12);
}

.assistant-header__toggle.is-active:hover {
  color: #115e59;
  background: rgba(15, 118, 110, 0.16);
}

.assistant-header__toggle.is-active::after {
  content: "";
  position: absolute;
  top: 8px;
  right: 8px;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
}

.assistant-header__toggle:deep(.el-icon) {
  font-size: 15px;
}

.assistant-header__copy h2 {
  margin: 4px 0 6px;
  font-size: 20px;
  line-height: 1.1;
  color: #0f172a;
}

.assistant-header__copy p {
  margin: 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
}

.assistant-header__eyebrow {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.12);
  color: #0369a1;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.assistant-messages {
  overflow: auto;
  min-height: 180px;
  min-width: 0;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  scrollbar-gutter: stable;
}

.assistant-empty {
  display: grid;
  gap: 6px;
  padding: 20px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px dashed rgba(148, 163, 184, 0.65);
  color: #475569;
}

.assistant-empty--error {
  border-style: solid;
  border-color: rgba(248, 113, 113, 0.45);
  background: rgba(254, 242, 242, 0.88);
}

.assistant-message {
  max-width: 92%;
  display: grid;
  gap: 8px;
  padding: 14px 14px 12px;
  border-radius: 20px;
  color: #0f172a;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.assistant-message--assistant {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.92);
}

.assistant-message--user {
  align-self: flex-end;
  background: linear-gradient(135deg, #0f766e 0%, #0369a1 100%);
  color: #f8fafc;
}

.assistant-message--draft {
  opacity: 0.92;
}

.assistant-message--draft .assistant-message__content {
  min-height: 22px;
}

.assistant-message__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 11px;
  opacity: 0.78;
}

.assistant-message__role {
  font-weight: 700;
}

.assistant-message__content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  font-size: 13px;
}

.assistant-message__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.assistant-message__icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.14);
  color: #64748b;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease;
}

.assistant-message__icon-button:hover {
  transform: translateY(-1px);
  background: rgba(148, 163, 184, 0.22);
  color: #0f172a;
}

.assistant-message__icon-button.is-active {
  background: rgba(15, 118, 110, 0.14);
  color: #0f766e;
}

.assistant-message__icon-button .el-icon {
  font-size: 14px;
}

.assistant-message__status {
  font-size: 12px;
  color: #0f766e;
}

.assistant-message__images {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.assistant-message__images img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  border-radius: 16px;
  border: 1px solid rgba(226, 232, 240, 0.95);
}

.assistant-composer {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr);
  min-width: 0;
}

.assistant-composer--single {
  grid-template-columns: 1fr;
}

.assistant-input-card {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 16px;
  border-radius: 22px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.94));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.assistant-input-card--voice {
  background:
    radial-gradient(circle at top right, rgba(14, 165, 233, 0.14), transparent 34%),
    linear-gradient(180deg, rgba(241, 245, 249, 0.98), rgba(226, 232, 240, 0.9));
}

.assistant-input-card--call {
  background:
    radial-gradient(circle at top right, rgba(14, 165, 233, 0.18), transparent 30%),
    radial-gradient(circle at bottom left, rgba(15, 118, 110, 0.14), transparent 32%),
    linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(226, 232, 240, 0.92));
}

.assistant-input-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.assistant-input-card__eyebrow {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.assistant-input-card__head h3 {
  margin: 6px 0 4px;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.1;
}

.assistant-input-card__head p {
  margin: 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.assistant-input-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.assistant-input-card__actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.assistant-input-card__hint {
  color: #64748b;
  font-size: 12px;
}

.assistant-voice-diagnostics {
  display: grid;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(255, 255, 255, 0.74);
  min-width: 0;
  overflow: hidden;
}

.assistant-voice-diagnostics__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.assistant-voice-diagnostics__toolbar-title {
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
  min-width: 0;
}

.assistant-voice-diagnostics__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}

.assistant-voice-diagnostics__label {
  color: #475569;
  flex: 0 0 auto;
}

.assistant-voice-diagnostics__value {
  color: #0f172a;
  font-weight: 600;
  text-align: right;
  flex: 1 1 auto;
  min-width: 0;
  word-break: break-word;
}

.assistant-voice-device-select {
  width: 100%;
}

.assistant-voice-meter {
  display: grid;
  gap: 6px;
}

.assistant-voice-meter__track {
  position: relative;
  overflow: hidden;
  height: 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.18);
}

.assistant-voice-meter__fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0f766e 0%, #0ea5e9 52%, #f59e0b 100%);
  transition: width 0.1s ease-out;
}

.assistant-voice-meter__text {
  font-size: 12px;
  color: #475569;
}

.assistant-voice-track {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.92);
  min-width: 0;
  max-height: 180px;
  overflow: auto;
  scrollbar-gutter: stable;
}

.assistant-voice-track__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}

.assistant-voice-track__label {
  color: #64748b;
}

.assistant-voice-track__value {
  color: #0f172a;
  font-weight: 600;
  text-align: right;
  word-break: break-all;
}

.assistant-voice-track__toggle {
  justify-self: start;
  padding: 0;
}

.assistant-voice-warning {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 247, 237, 0.92);
  border: 1px solid rgba(251, 146, 60, 0.32);
  color: #9a3412;
  font-size: 12px;
  line-height: 1.5;
}

.assistant-composer__actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.assistant-composer__aux {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.assistant-voice-control {
  display: grid;
  gap: 8px;
  width: 100%;
}

.assistant-voice-live {
  display: grid;
  gap: 10px;
  min-width: 0;
  min-height: 154px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.8);
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.assistant-voice-live--call {
  min-height: 200px;
}

.assistant-voice-live.is-listening {
  border-color: rgba(14, 165, 233, 0.28);
  box-shadow: 0 14px 30px rgba(14, 165, 233, 0.12);
  transform: translateY(-1px);
}

.assistant-voice-live.is-processing {
  border-color: rgba(245, 158, 11, 0.28);
}

.assistant-voice-live.is-ready {
  border-color: rgba(15, 118, 110, 0.28);
}

.assistant-voice-live.is-error {
  border-color: rgba(239, 68, 68, 0.28);
}

.assistant-voice-live__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.assistant-voice-live__badge {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
}

.assistant-voice-live__countdown {
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
}

.assistant-voice-live__text {
  min-height: 64px;
  color: #0f172a;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.assistant-voice-live__device {
  color: #64748b;
  font-size: 12px;
  text-align: right;
  word-break: break-word;
}

.assistant-call-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
}

.assistant-call-actions__hint {
  color: #64748b;
  font-size: 12px;
  text-align: right;
  word-break: break-word;
}

.assistant-voice-meter--inline {
  padding: 8px 10px;
  border-radius: 16px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(248, 250, 252, 0.9);
}

.assistant-voice-trigger {
  --assistant-voice-trigger-level: 0;
  --assistant-voice-trigger-glow: 0.18;
  position: relative;
  width: 100%;
  min-width: 0;
  justify-content: center;
  overflow: hidden;
  isolation: isolate;
  transition:
    transform 0.16s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease,
    background-color 0.18s ease;
}

.assistant-voice-trigger::before,
.assistant-voice-trigger::after {
  content: "";
  position: absolute;
  inset: 1px;
  border-radius: inherit;
  pointer-events: none;
}

.assistant-voice-trigger::before {
  opacity: 0;
  background: linear-gradient(
    115deg,
    transparent 0%,
    rgba(255, 255, 255, 0.18) 42%,
    rgba(255, 255, 255, 0.44) 50%,
    transparent 58%
  );
}

.assistant-voice-trigger::after {
  inset: -16%;
  opacity: 0;
  background: radial-gradient(
    circle,
    rgba(248, 113, 113, var(--assistant-voice-trigger-glow)),
    transparent 62%
  );
  transform: scale(calc(0.94 + var(--assistant-voice-trigger-level) * 0.2));
}

.assistant-voice-trigger:hover {
  transform: translateY(-1px);
}

.assistant-voice-trigger.is-listening {
  box-shadow:
    0 14px 26px rgba(248, 113, 113, 0.16),
    0 6px 12px rgba(15, 23, 42, 0.08);
  transform: translateY(-1px);
}

.assistant-voice-trigger.is-listening::before {
  opacity: 1;
  animation: assistantVoiceTriggerSweep 1.6s linear infinite;
}

.assistant-voice-trigger.is-listening::after {
  opacity: 1;
  animation: assistantVoiceTriggerPulse 1.05s ease-in-out infinite;
}

.assistant-voice-trigger.is-listening .assistant-voice-trigger__icon {
  animation: assistantVoiceTriggerIcon 0.9s ease-in-out infinite;
}

.assistant-voice-trigger.is-listening .assistant-voice-trigger__label {
  font-weight: 700;
}

.assistant-voice-trigger.is-processing::before {
  opacity: 0.92;
  animation: assistantVoiceTriggerSweep 1.3s linear infinite;
}

.assistant-voice-trigger.is-error {
  box-shadow: 0 0 0 1px rgba(239, 68, 68, 0.12);
}

.assistant-voice-trigger__body {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.assistant-voice-trigger__icon {
  flex: 0 0 auto;
}

.assistant-composer__actions .el-button--primary {
  min-width: 88px;
}

.assistant-voice-trigger__label {
  min-width: 0;
}

.assistant-settings-layout {
  min-height: 0;
  overflow: auto;
  display: grid;
  gap: 12px;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.assistant-settings-layout--dialog {
  max-height: min(72vh, 760px);
  padding-right: 8px;
}

.assistant-settings-group--status {
  background:
    radial-gradient(circle at top right, rgba(14, 165, 233, 0.14), transparent 34%),
    linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(241, 245, 249, 0.94));
}

.assistant-fab-shell {
  position: fixed;
  right: 20px;
  bottom: 20px;
  display: grid;
  justify-items: end;
  padding: 10px;
  border-radius: 42px;
  z-index: 3201;
  isolation: isolate;
  animation: assistantFabReveal 720ms cubic-bezier(0.22, 1, 0.36, 1);
}

.assistant-fab-shell::before,
.assistant-fab-shell::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
}

.assistant-fab-shell::before {
  background:
    linear-gradient(160deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.34)),
    radial-gradient(circle at top right, rgba(103, 232, 249, 0.22), transparent 48%);
  border: 1px solid rgba(255, 255, 255, 0.74);
  box-shadow:
    0 18px 42px rgba(15, 23, 42, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(18px);
  z-index: -2;
}

.assistant-fab-shell::after {
  inset: -14px;
  background:
    radial-gradient(circle at 24% 20%, rgba(56, 189, 248, 0.22), transparent 34%),
    radial-gradient(circle at 82% 76%, rgba(103, 232, 249, 0.18), transparent 30%);
  filter: blur(18px);
  opacity: 0.9;
  z-index: -3;
  animation: assistantFabHalo 14s ease-in-out infinite;
}

.assistant-fab {
  --assistant-fab-level: 0.08;
  position: relative;
  width: 132px;
  height: 132px;
  border: 1px solid rgba(255, 255, 255, 0.86);
  border-radius: 34px;
  display: grid;
  place-items: center;
  background:
    radial-gradient(
      circle at top left,
      rgba(255, 255, 255, calc(0.9 - var(--assistant-fab-level) * 0.24)),
      transparent 48%
    ),
    linear-gradient(155deg, rgba(255, 255, 255, 0.92) 0%, rgba(235, 246, 252, 0.88) 52%, rgba(225, 239, 248, 0.92) 100%);
  color: #0f172a;
  box-shadow:
    0 24px 54px rgba(15, 23, 42, 0.1),
    0 12px 30px rgba(56, 189, 248, 0.14),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
  cursor: pointer;
  overflow: hidden;
  isolation: isolate;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  backdrop-filter: blur(22px);
  transition:
    transform 0.22s ease,
    box-shadow 0.22s ease,
    border-color 0.22s ease,
    background 0.22s ease;
}

.assistant-fab::before,
.assistant-fab::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.assistant-fab::before {
  inset: -24% 36%;
  background: linear-gradient(
    115deg,
    transparent 0%,
    rgba(255, 255, 255, 0.12) 38%,
    rgba(255, 255, 255, 0.72) 50%,
    rgba(255, 255, 255, 0.12) 62%,
    transparent 100%
  );
  opacity: 0;
  transform: translateX(-132%) rotate(10deg);
}

.assistant-fab::after {
  inset: 7px;
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.48);
  opacity: calc(0.52 + var(--assistant-fab-level) * 0.18);
}

.assistant-fab.is-listening {
  box-shadow:
    0 28px 64px rgba(15, 23, 42, 0.14),
    0 14px 34px rgba(56, 189, 248, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
  border-color: rgba(125, 211, 252, 0.92);
}

.assistant-fab.is-listening .assistant-fab__pulse {
  animation-duration: 7.4s;
}

.assistant-fab.is-processing .assistant-fab__pulse {
  animation-duration: 5.2s;
}

.assistant-fab.is-processing::before,
.assistant-fab.is-listening::before {
  opacity: 0.72;
  animation: assistantFabSweep 3.8s linear infinite;
}

.assistant-fab.is-error {
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.88), transparent 46%),
    linear-gradient(155deg, rgba(255, 247, 247, 0.96) 0%, rgba(254, 226, 226, 0.9) 52%, rgba(255, 228, 230, 0.94) 100%);
  border-color: rgba(252, 165, 165, 0.92);
  color: #7f1d1d;
}

.assistant-fab:hover {
  transform: translateY(-3px);
  box-shadow:
    0 28px 58px rgba(15, 23, 42, 0.12),
    0 14px 32px rgba(56, 189, 248, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
}

.assistant-fab.is-dragging,
.assistant-fab.is-dragging:hover {
  cursor: grabbing;
  transform: scale(1.02);
  transition: none;
}

.assistant-fab__meta {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 5px;
  text-align: center;
  padding: 0 16px;
}

.assistant-fab__eyebrow {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  opacity: 0.5;
}

.assistant-fab__label {
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.assistant-fab__sub {
  max-width: 102px;
  font-size: 10px;
  line-height: 1.45;
  color: rgba(15, 23, 42, 0.62);
}

.assistant-fab__pulse {
  position: absolute;
  inset: 10px;
  border-radius: 28px;
  background:
    radial-gradient(circle at 22% 18%, rgba(255, 255, 255, 0.74), transparent 36%),
    radial-gradient(circle at 80% 78%, rgba(103, 232, 249, calc(0.08 + var(--assistant-fab-level) * 0.16)), transparent 34%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.36), transparent 70%);
  opacity: 0.92;
  animation: assistantFabGlow 8.8s ease-in-out infinite;
}

.assistant-fab__wave {
  position: absolute;
  inset: calc(12px - var(--assistant-fab-level) * 4px);
  border-radius: 30px;
  border: 1px solid rgba(56, 189, 248, 0.18);
  opacity: 0;
  pointer-events: none;
}

.assistant-fab.is-listening .assistant-fab__wave {
  opacity: 0.92;
}

.assistant-fab__wave--one {
  animation: assistantFabWave 3.8s ease-out infinite;
}

.assistant-fab__wave--two {
  animation: assistantFabWave 3.8s ease-out infinite 1.9s;
}

.assistant-fab__meter {
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 14px;
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.16);
}

.assistant-fab__meter-fill {
  width: 100%;
  height: 100%;
  transform-origin: left center;
  border-radius: inherit;
  background: linear-gradient(90deg, #38bdf8 0%, #67e8f9 54%, #0f172a 100%);
  box-shadow: 0 0 12px rgba(56, 189, 248, 0.28);
  transition: transform 0.16s ease-out;
}

.assistant-fab__orbit {
  position: absolute;
  inset: 9px;
  border-radius: 30px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  pointer-events: none;
}

.assistant-fab__orbit--outer {
  animation: assistantFabContour 12s ease-in-out infinite;
}

.assistant-fab__orbit--inner {
  inset: 22px;
  border-radius: 22px;
  border-color: rgba(255, 255, 255, 0.56);
  animation: assistantFabContour 9s ease-in-out infinite reverse;
}

.assistant-panel-enter-active,
.assistant-panel-leave-active {
  transition: all 0.24s ease;
}

.assistant-panel-enter-from,
.assistant-panel-leave-to {
  opacity: 0;
  transform: translateY(16px) scale(0.98);
}

:deep(.assistant-settings-dialog .el-dialog__body) {
  padding-top: 8px;
}

.assistant-settings-group {
  display: grid;
  gap: 12px;
  margin-bottom: 14px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.92)
  );
}

.assistant-settings-group__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.assistant-settings-group__actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.assistant-settings-group__head h4 {
  margin: 0;
  color: #1f2a37;
  font-size: 15px;
}

.assistant-settings-group__head p {
  margin: 6px 0 0;
  color: #637083;
  font-size: 12px;
  line-height: 1.6;
}

.assistant-settings-group__select {
  width: 100%;
}

.assistant-settings-group__desc {
  color: #637083;
  font-size: 12px;
  line-height: 1.6;
}

.assistant-settings-group__alert-body {
  display: grid;
  gap: 6px;
  line-height: 1.6;
}

@keyframes assistantFabReveal {
  0% {
    opacity: 0;
    transform: translateY(18px) scale(0.96);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes assistantFabHalo {
  0%,
  100% {
    opacity: 0.72;
    transform: scale(0.98);
  }
  50% {
    opacity: 1;
    transform: scale(1.04);
  }
}

@keyframes assistantFabGlow {
  0%,
  100% {
    opacity: 0.84;
    transform: scale(0.98);
  }
  50% {
    opacity: 1;
    transform: scale(calc(1 + var(--assistant-fab-level) * 0.028));
  }
}

@keyframes assistantFabContour {
  0%,
  100% {
    opacity: 0.24;
    transform: scale(0.985);
  }
  50% {
    opacity: 0.62;
    transform: scale(1.02);
  }
}

@keyframes assistantFabWave {
  0% {
    transform: scale(0.92);
    opacity: 0;
  }
  18% {
    opacity: 0.38;
  }
  100% {
    transform: scale(1.08);
    opacity: 0;
  }
}

@keyframes assistantFabSweep {
  0% {
    transform: translateX(-132%) rotate(10deg);
  }
  100% {
    transform: translateX(132%) rotate(10deg);
  }
}

@keyframes assistantVoiceStatusPulse {
  0%,
  100% {
    transform: scale(0.88);
    opacity: 0.52;
  }
  50% {
    transform: scale(1.12);
    opacity: 1;
  }
}

@keyframes assistantVoiceTriggerSweep {
  0% {
    transform: translateX(-135%);
  }
  100% {
    transform: translateX(135%);
  }
}

@keyframes assistantVoiceTriggerPulse {
  0%,
  100% {
    transform: scale(calc(0.94 + var(--assistant-voice-trigger-level) * 0.12));
    opacity: 0.34;
  }
  50% {
    transform: scale(calc(1 + var(--assistant-voice-trigger-level) * 0.22));
    opacity: 0.92;
  }
}

@keyframes assistantVoiceTriggerIcon {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(calc(1.04 + var(--assistant-voice-trigger-level) * 0.16));
  }
}

@media (max-width: 960px) {
  .global-ai-assistant {
    right: 12px;
    left: 12px;
    bottom: 12px;
  }

  .assistant-fab-shell {
    right: 12px;
    bottom: 12px;
    padding: 8px;
  }

  .assistant-fab {
    width: 108px;
    height: 108px;
    border-radius: 30px;
  }

  .assistant-fab::after {
    inset: 6px;
    border-radius: 24px;
  }

  .assistant-fab__meta {
    gap: 4px;
    padding: 0 12px;
  }

  .assistant-fab__label {
    font-size: 16px;
  }

  .assistant-fab__sub {
    max-width: 82px;
    font-size: 9px;
  }

  .assistant-fab__meter {
    left: 14px;
    right: 14px;
    bottom: 12px;
    height: 6px;
  }

  .assistant-fab__orbit--inner {
    inset: 18px;
    border-radius: 18px;
  }

  .assistant-shell {
    width: 100%;
    min-width: 100%;
    min-height: 0;
    max-height: min(82vh, 860px);
    border-radius: 24px;
    padding: 16px;
    resize: none;
  }

  .assistant-shell--fullscreen {
    width: 100%;
    min-width: 100%;
    height: calc(100vh - 24px);
    max-height: calc(100vh - 24px);
  }

  .assistant-header {
    flex-direction: column;
  }

  .assistant-header__actions {
    align-self: flex-end;
  }

  .assistant-header__toggle {
    flex: 0 0 auto;
  }

  .assistant-composer__actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .assistant-composer {
    grid-template-columns: 1fr;
  }

  .assistant-composer__actions,
  .assistant-composer__aux,
  .assistant-voice-control,
  .assistant-voice-device-select,
  .assistant-composer__actions .el-button--primary {
    width: 100%;
  }

  .assistant-composer__actions {
    grid-template-columns: 1fr;
  }

  .assistant-composer__aux :deep(.el-button) {
    flex: 1 1 0;
  }

  .assistant-composer__actions .el-button--primary {
    margin-left: 0;
  }

  .assistant-input-card__footer {
    flex-direction: column;
    align-items: stretch;
  }

  .assistant-input-card__actions {
    justify-content: space-between;
    width: 100%;
  }

  .assistant-voice-live__device {
    text-align: left;
  }
}

@media (prefers-reduced-motion: reduce) {
  .assistant-fab-shell,
  .assistant-fab-shell::after,
  .assistant-fab,
  .assistant-fab::before,
  .assistant-fab__pulse,
  .assistant-fab__wave,
  .assistant-fab__orbit {
    animation: none !important;
    transition: none !important;
  }
}
</style>
