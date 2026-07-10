import { getStoredToken } from "@/utils/auth-storage.js";
import { resolveServerOrigin } from "@/utils/server-profile.js";

export function resolveVoiceResourceUrl(url) {
  const normalized = String(url || "").trim();
  if (!normalized) return "";
  if (
    normalized.startsWith("data:") ||
    normalized.startsWith("blob:") ||
    normalized.startsWith("file://")
  ) {
    return normalized;
  }
  const token = typeof window !== "undefined" ? getStoredToken() : "";
  try {
    const base =
      typeof window !== "undefined"
        ? resolveServerOrigin()
        : "http://localhost";
    const resolved = new URL(normalized, base);
    const isSameOrigin =
      typeof window === "undefined"
        ? normalized.startsWith("/")
        : resolved.origin === resolveServerOrigin();
    if (isSameOrigin && resolved.pathname.startsWith("/api/") && token) {
      resolved.searchParams.set("token", token);
    }
    return resolved.toString();
  } catch {
    return normalized;
  }
}
