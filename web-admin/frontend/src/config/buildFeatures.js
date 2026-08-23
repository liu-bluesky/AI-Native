// Build-time feature switches. They are resolved by Vite and are not user settings.

const buildEnv = import.meta.env || {};

function readBuildFlag(name, fallback) {
  const value = buildEnv[name];
  if (value === undefined || value === null || value === "") return fallback;
  return ["1", "true", "yes", "on"].includes(
    String(value).trim().toLowerCase(),
  );
}

export const MEDIA_BUILD_FEATURES = Object.freeze({
  image: readBuildFlag("VITE_ENABLE_MEDIA_IMAGE", true),
  video: readBuildFlag("VITE_ENABLE_MEDIA_VIDEO", true),
  audioGeneration: readBuildFlag("VITE_ENABLE_MEDIA_AUDIO_GENERATION", false),
  audioTranscription: readBuildFlag(
    "VITE_ENABLE_MEDIA_AUDIO_TRANSCRIPTION",
    false,
  ),
});

export const GLOBAL_ASSISTANT_BUILD_FEATURES = Object.freeze({
  voice: readBuildFlag("VITE_ENABLE_GLOBAL_ASSISTANT_VOICE", false),
  greeting: readBuildFlag("VITE_ENABLE_GLOBAL_ASSISTANT_GREETING", false),
});

export function isMediaBuildFeatureEnabled(feature) {
  return Boolean(MEDIA_BUILD_FEATURES[String(feature || "").trim()]);
}
