const TOOL_VARIANTS = {
  terminal: ["terminal", "command", "bash", "shell", "exec", "powershell", "pwsh"],
  edit: ["edit", "write", "patch", "apply_patch", "replace", "create_file", "delete_file", "delete_local_resource"],
  read: ["read", "cat", "view", "open_file", "read_file"],
  search: ["search", "grep", "rg", "find", "glob", "list_files"],
  web: ["web", "http", "fetch", "browser", "url", "exa", "perplexity"],
};

function normalizedToolIdentity(operation = {}) {
  const meta = operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  return [
    operation?.kind,
    operation?.title,
    meta.tool_name,
    meta.toolName,
    meta.command,
  ]
    .map((value) => String(value || "").trim().toLowerCase())
    .filter(Boolean)
    .join(" ");
}

export function classifyChatTool(operation = {}) {
  const identity = normalizedToolIdentity(operation);
  for (const [variant, keywords] of Object.entries(TOOL_VARIANTS)) {
    if (keywords.some((keyword) => identity.includes(keyword))) return variant;
  }
  return "generic";
}

export function normalizeChatToolState(value) {
  const phase = String(value || "").trim().toLowerCase();
  if (["pending", "running"].includes(phase)) return "running";
  if (phase === "completed") return "ok";
  if (phase === "skipped") return "skipped";
  if (phase === "waiting_user") return "waiting";
  if (["failed", "blocked"].includes(phase)) return "error";
  return "stopped";
}

export function chatToolStateLabel(state) {
  if (state === "running") return "运行中";
  if (state === "ok") return "已完成";
  if (state === "skipped") return "已跳过";
  if (state === "waiting") return "等待操作";
  if (state === "error") return "执行失败";
  return "已停止";
}

export function splitToolOutputLines(value, limit = 160) {
  return String(value || "")
    .split(/\r?\n/)
    .slice(0, limit)
    .map((text, index) => ({ id: `${index}:${text}`, number: index + 1, text }));
}

export function diffLineTone(text) {
  if (text.startsWith("+++") || text.startsWith("---")) return "meta";
  if (text.startsWith("@@")) return "hunk";
  if (text.startsWith("+")) return "add";
  if (text.startsWith("-")) return "remove";
  return "context";
}
