<template>
  <section class="assistant-voice-panel">
    <div class="assistant-voice-panel__head">
      <div>
        <h4>浏览器麦克风诊断</h4>
        <p>在这里校准浏览器真实使用的输入设备，录音前先确认浏览器拿到的是正确麦克风。</p>
      </div>

      <div class="assistant-voice-panel__actions">
        <el-button
          text
          type="primary"
          :loading="voiceDeviceRefreshLoading"
          :disabled="isMonitoring"
          @click="rescanVoiceInputDevices"
        >
          重新扫描
        </el-button>
        <el-button
          round
          :type="isMonitoring ? 'danger' : 'primary'"
          @click="toggleMonitoring"
        >
          {{ isMonitoring ? "停止测试" : "开始测试" }}
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="!browserAudioCaptureSupported()"
      title="当前浏览器暂不支持麦克风诊断"
      type="warning"
      :closable="false"
      show-icon
    />

    <template v-else>
      <div class="assistant-voice-panel__row">
        <span class="assistant-voice-panel__label">浏览器麦克风</span>
        <span class="assistant-voice-panel__value">
          {{ selectedVoiceInputDeviceLabel }}
        </span>
      </div>

      <el-select
        v-model="selectedVoiceInputDeviceId"
        class="assistant-voice-panel__select"
        placeholder="选择输入设备"
        :disabled="isMonitoring"
        @visible-change="handleVoiceDeviceSelectVisibility"
      >
        <el-option
          label="跟随浏览器默认设备（推荐）"
          :value="VOICE_INPUT_DEFAULT_VALUE"
        />
        <el-option
          v-for="device in voiceInputDevices"
          :key="device.deviceId"
          :label="device.label"
          :value="device.deviceId"
        />
      </el-select>

      <div class="assistant-voice-meter">
        <div class="assistant-voice-meter__track">
          <div
            class="assistant-voice-meter__fill"
            :style="{ width: `${voiceMeterPercent}%` }"
          />
        </div>
        <span class="assistant-voice-meter__text">
          {{ voiceMeterHint }} · 峰值 {{ voiceMeterPeakLabel }}
        </span>
      </div>

      <div v-if="monitorStatusText" class="assistant-voice-panel__status">
        {{ monitorStatusText }}
      </div>

      <div
        v-if="voiceActiveTrackSummaryRows.length"
        class="assistant-voice-track"
      >
        <div
          v-for="item in voiceActiveTrackCompactRows"
          :key="item.label"
          class="assistant-voice-track__row"
        >
          <span class="assistant-voice-track__label">{{ item.label }}</span>
          <span class="assistant-voice-track__value">{{ item.value }}</span>
        </div>

        <el-button
          v-if="voiceActiveTrackDetailRows.length"
          text
          type="primary"
          class="assistant-voice-track__toggle"
          @click="voiceTrackDetailsExpanded = !voiceTrackDetailsExpanded"
        >
          {{ voiceTrackDetailsExpanded ? "收起详细音轨信息" : "查看详细音轨信息" }}
        </el-button>

        <div
          v-for="item in voiceTrackDetailsExpanded ? voiceActiveTrackDetailRows : []"
          :key="item.label"
          class="assistant-voice-track__row"
        >
          <span class="assistant-voice-track__label">{{ item.label }}</span>
          <span class="assistant-voice-track__value">{{ item.value }}</span>
        </div>
      </div>

      <div v-if="voiceDeviceWarningText" class="assistant-voice-warning">
        {{ voiceDeviceWarningText }}
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";

const VOICE_INPUT_DEVICE_STORAGE_KEY = "global-ai-assistant-voice-device-id";
const VOICE_INPUT_DEFAULT_VALUE = "__browser_default__";

const voiceInputDevices = ref([]);
const selectedVoiceInputDeviceId = ref(VOICE_INPUT_DEFAULT_VALUE);
const voiceMeterLevel = ref(0);
const voiceMeterPeakValue = ref(0);
const voiceDeviceRefreshLoading = ref(false);
const voiceActiveTrackInfo = ref(createEmptyVoiceTrackInfo());
const voiceTrackDetailsExpanded = ref(false);
const isMonitoring = ref(false);
const monitorStatusText = ref("");

let mediaStream = null;
let voiceAudioContext = null;
let voiceSourceNode = null;
let voiceProcessorNode = null;
let voiceMuteNode = null;
let voiceMeterDecayTimer = null;

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
  const suspiciousVirtualDevice =
    /(virtual|oray|loopback|blackhole|soundflower|vb-audio|aggregate)/i;
  if (suspiciousVirtualDevice.test(label)) {
    return "当前浏览器正在使用虚拟音频输入，不是耳机麦克风。请先到系统声音输入切回真实麦克风，再重新扫描。";
  }
  if (voiceInputDevices.value.length === 1) {
    return "浏览器当前只检测到一个输入设备。若你正在使用耳机麦克风，请先在系统里切换默认输入后重试。";
  }
  return "";
});

const voiceMeterPercent = computed(() =>
  resolveVoiceMeterPercent(voiceMeterLevel.value),
);
const voiceMeterPeakLabel = computed(() =>
  Number(voiceMeterPeakValue.value || 0).toFixed(4),
);
const voiceMeterHint = computed(() => {
  if (isMonitoring.value) {
    if (voiceMeterLevel.value >= 0.16) return "语音输入正常";
    if (voiceMeterLevel.value >= 0.05) return "已检测到声音，仍可再靠近一些";
    return "浏览器已开始监听，请对着当前设备说话";
  }
  if (!voiceInputDevices.value.length) {
    return "浏览器暂未返回可用输入设备";
  }
  return "开始测试后，音量条会跟随真实输入变化";
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

function browserAudioCaptureSupported() {
  if (typeof window === "undefined") return false;
  return Boolean(
    window.navigator?.mediaDevices?.getUserMedia &&
      (window.AudioContext || window.webkitAudioContext),
  );
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
  if (typeof window === "undefined") return "";
  return String(
    window.localStorage?.getItem(VOICE_INPUT_DEVICE_STORAGE_KEY) || "",
  ).trim();
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
  if (typeof window === "undefined") return;
  const normalized = String(deviceId || "").trim();
  if (!normalized || normalized === VOICE_INPUT_DEFAULT_VALUE) {
    window.localStorage?.removeItem(VOICE_INPUT_DEVICE_STORAGE_KEY);
    return;
  }
  window.localStorage?.setItem(VOICE_INPUT_DEVICE_STORAGE_KEY, normalized);
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
    const nextSelectedId = preserveSelection
      ? String(
          selectedVoiceInputDeviceId.value || loadStoredVoiceInputDeviceId(),
        ).trim()
      : VOICE_INPUT_DEFAULT_VALUE;
    selectedVoiceInputDeviceId.value = audioInputs.some(
      (item) => item.deviceId === nextSelectedId,
    )
      ? nextSelectedId
      : VOICE_INPUT_DEFAULT_VALUE;
  } catch {
    voiceInputDevices.value = [];
  }
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

function stopMediaStream() {
  if (!mediaStream) return;
  mediaStream.getTracks().forEach((track) => track.stop());
  mediaStream = null;
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
  voiceMeterPeakValue.value = peak;
  if (peak > voiceMeterLevel.value) {
    voiceMeterLevel.value = Math.min(1, peak);
  }
}

function teardownAudioProcessingGraph() {
  stopVoiceMeterDecay();
  voiceMeterLevel.value = 0;
  voiceMeterPeakValue.value = 0;
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

async function rescanVoiceInputDevices() {
  if (!browserAudioCaptureSupported()) return;
  voiceDeviceRefreshLoading.value = true;
  let tempStream = null;
  try {
    tempStream = await requestVoiceInputStream();
    updateVoiceActiveTrackInfo(tempStream);
    await refreshVoiceInputDevices();
    monitorStatusText.value = "设备列表已刷新";
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

async function startMonitoring() {
  if (!browserAudioCaptureSupported()) {
    ElMessage.warning("当前浏览器暂不支持录音");
    return;
  }
  monitorStatusText.value = "正在请求麦克风权限...";
  try {
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
      if (!isMonitoring.value) return;
      const channelData = event.inputBuffer.getChannelData(0);
      if (!channelData?.length) return;
      updateVoiceMeterLevel(channelData);
    };
    voiceSourceNode.connect(voiceProcessorNode);
    voiceProcessorNode.connect(voiceMuteNode);
    voiceMuteNode.connect(voiceAudioContext.destination);
    isMonitoring.value = true;
    voiceMeterLevel.value = 0;
    voiceMeterPeakValue.value = 0;
    monitorStatusText.value = "正在测试浏览器当前真实输入设备...";
    startVoiceMeterDecay();
  } catch (err) {
    teardownAudioProcessingGraph();
    stopMediaStream();
    isMonitoring.value = false;
    monitorStatusText.value = "麦克风权限被拒绝";
    ElMessage.warning(err?.message || "请允许浏览器访问麦克风后再试");
  }
}

function stopMonitoring() {
  teardownAudioProcessingGraph();
  stopMediaStream();
  isMonitoring.value = false;
  monitorStatusText.value = "测试已结束";
}

function toggleMonitoring() {
  if (isMonitoring.value) {
    stopMonitoring();
    return;
  }
  void startMonitoring();
}

watch(selectedVoiceInputDeviceId, (value) => {
  persistVoiceInputDeviceId(value);
});

onMounted(() => {
  selectedVoiceInputDeviceId.value = normalizeVoiceInputSelectionValue(
    loadStoredVoiceInputDeviceId(),
  );
  if (window.navigator?.mediaDevices?.addEventListener) {
    window.navigator.mediaDevices.addEventListener(
      "devicechange",
      refreshVoiceInputDevices,
    );
  }
  void refreshVoiceInputDevices();
});

onBeforeUnmount(() => {
  if (window.navigator?.mediaDevices?.removeEventListener) {
    window.navigator.mediaDevices.removeEventListener(
      "devicechange",
      refreshVoiceInputDevices,
    );
  }
  stopMonitoring();
});
</script>

<style scoped>
.assistant-voice-panel {
  margin-top: 16px;
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.92)
  );
}

.assistant-voice-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.assistant-voice-panel__head h4 {
  margin: 0;
  color: #1f2a37;
  font-size: 15px;
}

.assistant-voice-panel__head p {
  margin: 6px 0 0;
  color: #637083;
  font-size: 12px;
  line-height: 1.6;
}

.assistant-voice-panel__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.assistant-voice-panel__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}

.assistant-voice-panel__label {
  color: #637083;
  flex: 0 0 auto;
}

.assistant-voice-panel__value {
  color: #1f2a37;
  font-weight: 600;
  text-align: right;
  flex: 1 1 auto;
  min-width: 0;
  word-break: break-word;
}

.assistant-voice-panel__select {
  width: 100%;
}

.assistant-voice-panel__status {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(30, 106, 168, 0.08);
  color: #1e6aa8;
  font-size: 12px;
  line-height: 1.6;
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
  color: #637083;
}

.assistant-voice-track {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.92);
  min-width: 0;
  max-height: 220px;
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

@media (max-width: 900px) {
  .assistant-voice-panel__head {
    flex-direction: column;
  }

  .assistant-voice-panel__actions {
    width: 100%;
  }
}
</style>
