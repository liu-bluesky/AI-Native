import { canAccessPath } from "@/utils/permissions.js";

const PROJECT_CONTEXT_STORAGE_KEY = "project_id";
export const DESKTOP_WALLPAPER_STORAGE_KEY = "desktop_wallpaper_config";
export const DESKTOP_WINDOW_SESSION_STORAGE_KEY = "desktop_window_session";
const DESKTOP_DOCK_APP_IDS_STORAGE_KEY = "desktop_dock_app_ids";
const DESKTOP_DOCK_ORDER_STORAGE_KEY = "desktop_dock_order";
const DESKTOP_REQUIRED_DOCK_APP_IDS = ["chat", "tasks", "workbench"];

export const DESKTOP_WALLPAPER_PRESETS = [
  {
    id: "sky-glass",
    label: "晨雾玻璃",
    thumbnail:
      "linear-gradient(135deg, rgba(125, 211, 252, 0.92), rgba(248, 250, 252, 0.98) 52%, rgba(103, 232, 249, 0.8))",
    background:
      "radial-gradient(circle at 12% 0%, rgba(125, 211, 252, 0.2), transparent 26%), radial-gradient(circle at 88% 10%, rgba(103, 232, 249, 0.16), transparent 22%), linear-gradient(180deg, #f5f4ef 0%, #f8fafc 40%, #edf2f7 100%)",
    ambientLeft: "rgba(125, 211, 252, 0.28)",
    ambientRight: "rgba(103, 232, 249, 0.2)",
    meshOpacity: 1,
    luminance: 0.92,
  },
  {
    id: "sunset-satin",
    label: "日落缎面",
    thumbnail:
      "linear-gradient(135deg, rgba(251, 191, 36, 0.86), rgba(255, 255, 255, 0.92) 48%, rgba(251, 146, 60, 0.74))",
    background:
      "radial-gradient(circle at 18% 12%, rgba(251, 191, 36, 0.22), transparent 24%), radial-gradient(circle at 78% 10%, rgba(251, 146, 60, 0.18), transparent 20%), linear-gradient(180deg, #f8f2e8 0%, #fff7ed 42%, #f4f1ea 100%)",
    ambientLeft: "rgba(251, 191, 36, 0.22)",
    ambientRight: "rgba(251, 146, 60, 0.18)",
    meshOpacity: 0.84,
    luminance: 0.84,
  },
  {
    id: "midnight-aurora",
    label: "夜幕极光",
    thumbnail:
      "linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(56, 189, 248, 0.76) 48%, rgba(103, 232, 249, 0.66))",
    background:
      "radial-gradient(circle at 18% 0%, rgba(56, 189, 248, 0.24), transparent 24%), radial-gradient(circle at 82% 18%, rgba(103, 232, 249, 0.16), transparent 22%), linear-gradient(180deg, #020617 0%, #0f172a 42%, #172554 100%)",
    ambientLeft: "rgba(56, 189, 248, 0.22)",
    ambientRight: "rgba(103, 232, 249, 0.18)",
    meshOpacity: 0.46,
    luminance: 0.16,
  },
  {
    id: "forest-mist",
    label: "森林薄雾",
    thumbnail:
      "linear-gradient(135deg, rgba(16, 185, 129, 0.86), rgba(248, 250, 252, 0.94) 52%, rgba(45, 212, 191, 0.76))",
    background:
      "radial-gradient(circle at 14% 0%, rgba(16, 185, 129, 0.2), transparent 24%), radial-gradient(circle at 84% 16%, rgba(45, 212, 191, 0.16), transparent 22%), linear-gradient(180deg, #edf7f1 0%, #f8fafc 46%, #e8f5f0 100%)",
    ambientLeft: "rgba(16, 185, 129, 0.2)",
    ambientRight: "rgba(45, 212, 191, 0.16)",
    meshOpacity: 0.72,
    luminance: 0.81,
  },
];

function clampNumber(value, min, max) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return min;
  return Math.min(max, Math.max(min, numeric));
}

const DESKTOP_APP_ICON_THEMES = {
  chat: ["#22d3ee", "#2563eb"],
  workbench: ["#f59e0b", "#ef4444"],
  tasks: ["#6366f1", "#2563eb"],
  projects: ["#38bdf8", "#0f766e"],
  "project-detail": ["#60a5fa", "#4f46e5"],
  materials: ["#34d399", "#059669"],
  market: ["#fb7185", "#f97316"],
  "settings-home": ["#94a3b8", "#475569"],
  "settings-user": ["#818cf8", "#4f46e5"],
  "settings-users": ["#38bdf8", "#0284c7"],
  "settings-roles": ["#f97316", "#dc2626"],
  "settings-employees": ["#2dd4bf", "#0f766e"],
  "settings-agent-templates": ["#c084fc", "#7c3aed"],
  "settings-skills": ["#22c55e", "#15803d"],
  "settings-skill-resources": ["#14b8a6", "#0f766e"],
  "settings-rules": ["#facc15", "#ca8a04"],
  "settings-bot-connectors": ["#2dd4bf", "#0f766e"],
  "settings-system": ["#64748b", "#1e293b"],
  "settings-changelog": ["#fb923c", "#ea580c"],
  "settings-work-sessions": ["#38bdf8", "#2563eb"],
  "settings-statistics": ["#f97316", "#ea580c"],
  "settings-dictionaries": ["#a78bfa", "#6d28d9"],
  "settings-providers": ["#06b6d4", "#0891b2"],
  "settings-api-keys": ["#fbbf24", "#d97706"],
  "settings-wallpaper": ["#67e8f9", "#0ea5e9"],
  "settings-online-users": ["#4ade80", "#16a34a"],
  "settings-mcp-monitor": ["#f472b6", "#be185d"],
};

function resolveDesktopAppIcon(config = {}) {
  const colors = DESKTOP_APP_ICON_THEMES[String(config.id || "").trim()] || [
    "#94a3b8",
    "#475569",
  ];
  return {
    label: String(config.shortLabel || config.label || "").slice(0, 2),
    top: colors[0],
    bottom: colors[1],
    text: "#ffffff",
    glow: `${colors[1]}55`,
  };
}

function resolveDockToneTokens(luminance = 0.8) {
  const normalized = clampNumber(luminance, 0, 1);
  if (normalized <= 0.34) {
    return {
      luminance: normalized,
      surfaceBorder: "rgba(255, 255, 255, 0.18)",
      surfaceTop: "rgba(34, 48, 78, 0.72)",
      surfaceMid: "rgba(24, 36, 64, 0.52)",
      surfaceBottom: "rgba(16, 24, 42, 0.44)",
      surfaceShadow: "rgba(2, 6, 23, 0.28)",
      ambientShadow: "rgba(15, 23, 42, 0.24)",
      innerHighlight: "rgba(255, 255, 255, 0.22)",
      edgeShade: "rgba(15, 23, 42, 0.24)",
      itemTop: "rgba(255, 255, 255, 0.18)",
      itemBottom: "rgba(255, 255, 255, 0.08)",
      itemHoverTop: "rgba(255, 255, 255, 0.3)",
      itemHoverBottom: "rgba(255, 255, 255, 0.16)",
      itemBorder: "rgba(255, 255, 255, 0.22)",
      labelColor: "#e2e8f0",
      iconBorder: "rgba(255, 255, 255, 0.16)",
      iconTop: "rgba(248, 250, 252, 0.32)",
      iconBottom: "rgba(148, 163, 184, 0.2)",
      iconText: "#f8fafc",
      indicator: "rgba(255, 255, 255, 0.72)",
    };
  }
  if (normalized <= 0.64) {
    return {
      luminance: normalized,
      surfaceBorder: "rgba(255, 255, 255, 0.34)",
      surfaceTop: "rgba(255, 255, 255, 0.42)",
      surfaceMid: "rgba(208, 220, 236, 0.32)",
      surfaceBottom: "rgba(148, 163, 184, 0.22)",
      surfaceShadow: "rgba(15, 23, 42, 0.18)",
      ambientShadow: "rgba(30, 41, 59, 0.16)",
      innerHighlight: "rgba(255, 255, 255, 0.42)",
      edgeShade: "rgba(71, 85, 105, 0.16)",
      itemTop: "rgba(255, 255, 255, 0.24)",
      itemBottom: "rgba(255, 255, 255, 0.1)",
      itemHoverTop: "rgba(255, 255, 255, 0.44)",
      itemHoverBottom: "rgba(255, 255, 255, 0.18)",
      itemBorder: "rgba(255, 255, 255, 0.34)",
      labelColor: "#e2e8f0",
      iconBorder: "rgba(255, 255, 255, 0.2)",
      iconTop: "rgba(248, 250, 252, 0.44)",
      iconBottom: "rgba(203, 213, 225, 0.22)",
      iconText: "#f8fafc",
      indicator: "rgba(255, 255, 255, 0.76)",
    };
  }
  return {
    luminance: normalized,
    surfaceBorder: "rgba(255, 255, 255, 0.58)",
    surfaceTop: "rgba(255, 255, 255, 0.62)",
    surfaceMid: "rgba(255, 255, 255, 0.4)",
    surfaceBottom: "rgba(230, 236, 245, 0.34)",
    surfaceShadow: "rgba(15, 23, 42, 0.12)",
    ambientShadow: "rgba(148, 163, 184, 0.12)",
    innerHighlight: "rgba(255, 255, 255, 0.72)",
    edgeShade: "rgba(148, 163, 184, 0.16)",
    itemTop: "rgba(255, 255, 255, 0.14)",
    itemBottom: "rgba(255, 255, 255, 0.04)",
    itemHoverTop: "rgba(255, 255, 255, 0.66)",
    itemHoverBottom: "rgba(255, 255, 255, 0.3)",
    itemBorder: "rgba(255, 255, 255, 0.48)",
    labelColor: "#526071",
    iconBorder: "rgba(148, 163, 184, 0.14)",
    iconTop: "rgba(250, 252, 255, 0.96)",
    iconBottom: "rgba(232, 238, 246, 0.74)",
    iconText: "#0f172a",
    indicator: "rgba(15, 23, 42, 0.58)",
  };
}

function canUseWindow() {
  return typeof window !== "undefined";
}

function createApp(config) {
  return {
    dock: false,
    launcher: true,
    width: 1040,
    height: 720,
    category: "workspace",
    categoryLabel: "工作应用",
    ...config,
    icon: resolveDesktopAppIcon(config),
  };
}

const DESKTOP_APP_ITEMS = [
  createApp({
    id: "chat",
    label: "AI 对话",
    shortLabel: "AI",
    path: "/ai/chat",
    summary: "围绕当前项目运行 AI 对话、任务树和协作工具。",
    eyebrow: "AI Workspace",
    width: 1260,
    height: 820,
    dock: true,
    match: (path) => String(path || "").startsWith("/ai/chat"),
  }),
  createApp({
    id: "workbench",
    label: "工作台",
    shortLabel: "WB",
    path: "/workbench",
    summary: "桌面里的总控应用，集中打开其他小应用。",
    eyebrow: "Desktop Workbench",
    width: 1120,
    height: 760,
    dock: true,
    match: (path) =>
      String(path || "") === "/desktop" ||
      String(path || "").startsWith("/workbench"),
  }),
  createApp({
    id: "tasks",
    label: "任务",
    shortLabel: "TS",
    path: "/tasks",
    summary: "集中管理任务，可由系统状态助手按描述快速创建。",
    eyebrow: "Task Center",
    width: 1080,
    height: 760,
    dock: true,
    match: (path) => String(path || "").startsWith("/tasks"),
  }),
  createApp({
    id: "projects",
    label: "项目",
    shortLabel: "PR",
    path: "/projects",
    summary: "管理项目列表、详情和项目上下文。",
    eyebrow: "Project Space",
    width: 1120,
    height: 760,
    dock: true,
    match: (path) =>
      String(path || "") === "/projects" ||
      String(path || "") === "/ai/chat/settings/projects",
  }),
  createApp({
    id: "project-detail",
    label: "项目详情",
    shortLabel: "PD",
    path: "/projects",
    summary: "查看单个项目的详情、成员、规则与工作轨迹。",
    eyebrow: "Project Workspace",
    width: 1180,
    height: 800,
    launcher: false,
    match: (path) =>
      /^\/projects\/[^/]+/.test(String(path || "")) ||
      /^\/ai\/chat\/settings\/projects\/[^/]+/.test(String(path || "")),
  }),
  createApp({
    id: "materials",
    label: "素材",
    shortLabel: "MT",
    path: "/materials",
    summary: "围绕项目资产、工作流和内容产出管理素材应用。",
    eyebrow: "Asset Workspace",
    width: 1180,
    height: 780,
    dock: true,
    match: (path) => String(path || "").startsWith("/materials"),
  }),
  createApp({
    id: "market",
    label: "市场",
    shortLabel: "MK",
    path: "/market",
    summary: "浏览技能、员工和规则资源。",
    eyebrow: "Capability Market",
    width: 1040,
    height: 720,
    dock: true,
    match: (path) => String(path || "").startsWith("/market"),
  }),
  createApp({
    id: "settings-home",
    label: "设置中心",
    shortLabel: "SC",
    path: "/settings-center",
    summary: "以桌面应用列表的方式打开设置子应用，而不是在当前页内继续跳转。",
    eyebrow: "Settings Center",
    width: 1080,
    height: 740,
    dock: true,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => {
      const normalized = String(path || "");
      return normalized.startsWith("/settings-center");
    },
  }),
  createApp({
    id: "settings-user",
    label: "用户设置",
    shortLabel: "US",
    path: "/user/settings",
    summary: "管理当前账号的个人偏好和默认行为。",
    eyebrow: "User Settings",
    width: 980,
    height: 720,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/user/settings"),
  }),
  createApp({
    id: "settings-users",
    label: "用户管理",
    shortLabel: "UM",
    path: "/users",
    summary: "维护平台用户、账号状态与访问入口。",
    eyebrow: "User Registry",
    width: 1120,
    height: 760,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/users"),
  }),
  createApp({
    id: "settings-roles",
    label: "角色管理",
    shortLabel: "RL",
    path: "/roles",
    summary: "维护角色权限和平台访问边界。",
    eyebrow: "Role Access",
    width: 1080,
    height: 740,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/roles"),
  }),
  createApp({
    id: "settings-employees",
    label: "员工管理",
    shortLabel: "EM",
    path: "/employees",
    summary: "管理平台员工、能力说明和使用统计。",
    eyebrow: "Employee Registry",
    width: 1180,
    height: 780,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/employees"),
  }),
  createApp({
    id: "settings-agent-templates",
    label: "模板库",
    shortLabel: "AT",
    path: "/agent-templates",
    summary: "维护行业智能体和角色模板。",
    eyebrow: "Agent Templates",
    width: 1140,
    height: 760,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/agent-templates"),
  }),
  createApp({
    id: "settings-skills",
    label: "技能管理",
    shortLabel: "SK",
    path: "/skills",
    summary: "维护技能、代理入口和技能配置。",
    eyebrow: "Skill Registry",
    width: 1180,
    height: 780,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/skills"),
  }),
  createApp({
    id: "settings-skill-resources",
    label: "技能资源",
    shortLabel: "SR",
    path: "/skill-resources",
    summary: "管理外部技能资源目录与详情入口。",
    eyebrow: "Skill Resources",
    width: 1120,
    height: 760,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/skill-resources"),
  }),
  createApp({
    id: "settings-rules",
    label: "规则管理",
    shortLabel: "RG",
    path: "/rules",
    summary: "维护项目规则、经验规则和可复用约束。",
    eyebrow: "Rule Registry",
    width: 1160,
    height: 780,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/rules"),
  }),
  createApp({
    id: "settings-bot-connectors",
    label: "机器人",
    shortLabel: "RB",
    path: "/system/bot-connectors",
    summary: "配置飞书、QQ、微信机器人并关联项目。",
    eyebrow: "Robot Connectors",
    width: 1200,
    height: 820,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/system/bot-connectors"),
  }),
  createApp({
    id: "settings-system",
    label: "系统配置",
    shortLabel: "SY",
    path: "/system/config",
    summary: "维护全局系统配置。",
    eyebrow: "System Config",
    width: 1200,
    height: 820,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/system/config"),
  }),
  createApp({
    id: "settings-changelog",
    label: "更新日志",
    shortLabel: "CL",
    path: "/changelog-entries",
    summary: "维护版本更新日志条目。",
    eyebrow: "Changelog",
    width: 1040,
    height: 720,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/changelog-entries"),
  }),
  createApp({
    id: "settings-work-sessions",
    label: "工作会话",
    shortLabel: "WS",
    path: "/work-sessions",
    summary: "查看与筛选工作会话。",
    eyebrow: "Work Sessions",
    width: 1180,
    height: 780,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/work-sessions"),
  }),
  createApp({
    id: "settings-statistics",
    label: "统计",
    shortLabel: "ST",
    path: "/statistics",
    summary: "直接在工作台里看 MCP 活跃度、会话闭环和当前观测盲区。",
    eyebrow: "Operations Insight",
    width: 1220,
    height: 820,
    launcher: true,
    category: "workspace",
    categoryLabel: "工作应用",
    match: (path) => String(path || "").startsWith("/statistics"),
  }),
  createApp({
    id: "settings-dictionaries",
    label: "字典管理",
    shortLabel: "DC",
    path: "/dictionaries",
    summary: "维护模型类型等全局字典。",
    eyebrow: "Dictionary Manager",
    width: 1120,
    height: 760,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/dictionaries"),
  }),
  createApp({
    id: "settings-providers",
    label: "模型供应商",
    shortLabel: "LL",
    path: "/llm/providers",
    summary: "管理平台模型源。",
    eyebrow: "LLM Providers",
    width: 1180,
    height: 780,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/llm/providers"),
  }),
  createApp({
    id: "settings-api-keys",
    label: "API Key",
    shortLabel: "AK",
    path: "/usage/keys",
    summary: "管理平台 API Key 和外部访问凭据。",
    eyebrow: "Access Tokens",
    width: 1060,
    height: 720,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/usage/keys"),
  }),
  createApp({
    id: "settings-wallpaper",
    label: "桌面背景",
    shortLabel: "BG",
    path: "/desktop/background",
    summary: "像操作系统一样切换桌面壁纸和背景氛围。",
    eyebrow: "Desktop Wallpaper",
    width: 1080,
    height: 760,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/desktop/background"),
  }),
  createApp({
    id: "settings-online-users",
    label: "在线用户",
    shortLabel: "OU",
    path: "/online-users",
    summary: "查看当前在线账号和最近访问位置。",
    eyebrow: "Online Users",
    width: 1080,
    height: 720,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/online-users"),
  }),
  createApp({
    id: "settings-mcp-monitor",
    label: "MCP 监控",
    shortLabel: "MP",
    path: "/mcp-monitor",
    summary: "查看 MCP 入口接入和使用情况。",
    eyebrow: "MCP Monitor",
    width: 1180,
    height: 780,
    launcher: false,
    category: "settings",
    categoryLabel: "设置应用",
    match: (path) => String(path || "").startsWith("/mcp-monitor"),
  }),
];

export const DESKTOP_DOCK_ITEMS = DESKTOP_REQUIRED_DOCK_APP_IDS
  .map((appId) => DESKTOP_APP_ITEMS.find((item) => item.id === appId))
  .filter(Boolean);
export const DESKTOP_LAUNCHER_ITEMS = DESKTOP_APP_ITEMS.filter((item) => item.launcher);
export const DESKTOP_SETTINGS_ITEMS = DESKTOP_APP_ITEMS.filter(
  (item) => item.category === "settings" && item.id !== "settings-home",
);
const DESKTOP_OPTIONAL_DOCK_APP_IDS = DESKTOP_APP_ITEMS
  .map((item) => item.id)
  .filter((appId) => !DESKTOP_REQUIRED_DOCK_APP_IDS.includes(appId));

function normalizeStoredDockAppIds(appIds = []) {
  const seen = new Set();
  return (Array.isArray(appIds) ? appIds : [])
    .map((item) => String(item || "").trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      if (DESKTOP_REQUIRED_DOCK_APP_IDS.includes(item)) return false;
      if (!DESKTOP_APP_ITEMS.some((app) => app.id === item)) return false;
      seen.add(item);
      return true;
    });
}

function normalizeStoredDockOrder(appIds = []) {
  const seen = new Set();
  const normalized = [];
  for (const item of Array.isArray(appIds) ? appIds : []) {
    const appId = String(item || "").trim();
    if (!appId || seen.has(appId)) continue;
    if (!DESKTOP_APP_ITEMS.some((app) => app.id === appId)) continue;
    seen.add(appId);
    normalized.push(appId);
  }
  for (const appId of DESKTOP_REQUIRED_DOCK_APP_IDS) {
    if (seen.has(appId)) continue;
    normalized.push(appId);
    seen.add(appId);
  }
  return normalized;
}

export function getStoredProjectContextId() {
  if (!canUseWindow()) return "";
  return String(window.localStorage.getItem(PROJECT_CONTEXT_STORAGE_KEY) || "").trim();
}

export function getStoredDesktopDockAppIds() {
  if (!canUseWindow()) return [];
  const raw = window.localStorage.getItem(DESKTOP_DOCK_APP_IDS_STORAGE_KEY);
  if (raw === null) {
    return [];
  }
  try {
    const parsed = JSON.parse(String(raw || "[]"));
    if (!Array.isArray(parsed)) return [];
    return normalizeStoredDockAppIds(parsed);
  } catch {
    return [];
  }
}

export function setStoredDesktopDockAppIds(appIds = []) {
  if (!canUseWindow()) return [];
  const normalized = normalizeStoredDockAppIds(appIds);
  window.localStorage.setItem(
    DESKTOP_DOCK_APP_IDS_STORAGE_KEY,
    JSON.stringify(normalized),
  );
  return normalized;
}

export function getStoredDesktopDockOrder() {
  if (!canUseWindow()) {
    return [...DESKTOP_REQUIRED_DOCK_APP_IDS];
  }
  const raw = window.localStorage.getItem(DESKTOP_DOCK_ORDER_STORAGE_KEY);
  if (raw === null) {
    return [...DESKTOP_REQUIRED_DOCK_APP_IDS];
  }
  try {
    const parsed = JSON.parse(String(raw || "[]"));
    if (!Array.isArray(parsed)) {
      return [...DESKTOP_REQUIRED_DOCK_APP_IDS];
    }
    return normalizeStoredDockOrder(parsed);
  } catch {
    return [...DESKTOP_REQUIRED_DOCK_APP_IDS];
  }
}

export function setStoredDesktopDockOrder(appIds = []) {
  if (!canUseWindow()) return [...DESKTOP_REQUIRED_DOCK_APP_IDS];
  const normalized = normalizeStoredDockOrder(appIds);
  window.localStorage.setItem(
    DESKTOP_DOCK_ORDER_STORAGE_KEY,
    JSON.stringify(normalized),
  );
  return normalized;
}

export function getStoredDesktopWindowSession() {
  if (!canUseWindow()) return null;
  const raw = window.localStorage.getItem(DESKTOP_WINDOW_SESSION_STORAGE_KEY);
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(String(raw || "{}"));
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function setStoredDesktopWindowSession(session = {}) {
  if (!canUseWindow()) return null;
  const normalized = session && typeof session === "object" ? session : {};
  window.localStorage.setItem(
    DESKTOP_WINDOW_SESSION_STORAGE_KEY,
    JSON.stringify(normalized),
  );
  return normalized;
}

export function clearStoredDesktopWindowSession() {
  if (!canUseWindow()) return;
  window.localStorage.removeItem(DESKTOP_WINDOW_SESSION_STORAGE_KEY);
}

function getWallpaperPresetById(presetId) {
  const normalizedPresetId = String(presetId || "").trim();
  return (
    DESKTOP_WALLPAPER_PRESETS.find((item) => item.id === normalizedPresetId)
    || DESKTOP_WALLPAPER_PRESETS[0]
  );
}

export function setStoredProjectContextId(projectId) {
  if (!canUseWindow()) return;
  const normalizedProjectId = String(projectId || "").trim();
  if (normalizedProjectId) {
    window.localStorage.setItem(PROJECT_CONTEXT_STORAGE_KEY, normalizedProjectId);
    return;
  }
  window.localStorage.removeItem(PROJECT_CONTEXT_STORAGE_KEY);
}

export function clearDesktopRuntimeStorage(options = {}) {
  if (!canUseWindow()) return;
  const preserveWallpaper = options?.preserveWallpaper !== false;
  const preserveDock = options?.preserveDock === true;
  window.localStorage.removeItem(PROJECT_CONTEXT_STORAGE_KEY);
  clearStoredDesktopWindowSession();
  if (!preserveWallpaper) {
    window.localStorage.removeItem(DESKTOP_WALLPAPER_STORAGE_KEY);
  }
  if (!preserveDock) {
    window.localStorage.removeItem(DESKTOP_DOCK_APP_IDS_STORAGE_KEY);
    window.localStorage.removeItem(DESKTOP_DOCK_ORDER_STORAGE_KEY);
  }
}

export function getDesktopWallpaperConfig() {
  const fallbackPreset = getWallpaperPresetById("");
  if (!canUseWindow()) {
    return {
      mode: "preset",
      presetId: fallbackPreset.id,
      customImage: "",
      customLuminance: Number(fallbackPreset.luminance || 0.82),
      updatedAt: "",
    };
  }
  try {
    const parsed = JSON.parse(
      String(window.localStorage.getItem(DESKTOP_WALLPAPER_STORAGE_KEY) || "{}"),
    );
    const preset = getWallpaperPresetById(parsed?.presetId);
    const mode = String(parsed?.mode || "preset").trim() === "custom" ? "custom" : "preset";
    const customImage = String(parsed?.customImage || "").trim();
    return {
      mode: mode === "custom" && customImage ? "custom" : "preset",
      presetId: preset.id,
      customImage,
      customLuminance: clampNumber(
        parsed?.customLuminance ?? preset.luminance ?? 0.82,
        0,
        1,
      ),
      updatedAt: String(parsed?.updatedAt || "").trim(),
    };
  } catch {
    return {
      mode: "preset",
      presetId: fallbackPreset.id,
      customImage: "",
      customLuminance: Number(fallbackPreset.luminance || 0.82),
      updatedAt: "",
    };
  }
}

export function setDesktopWallpaperConfig(input = {}) {
  if (!canUseWindow()) return getDesktopWallpaperConfig();
  const preset = getWallpaperPresetById(input?.presetId);
  const customImage = String(input?.customImage || "").trim();
  const mode = String(input?.mode || "preset").trim() === "custom" && customImage
    ? "custom"
    : "preset";
  const nextConfig = {
    mode,
    presetId: preset.id,
    customImage: mode === "custom" ? customImage : "",
    customLuminance: mode === "custom"
      ? clampNumber(input?.customLuminance ?? preset.luminance ?? 0.82, 0, 1)
      : Number(preset.luminance || 0.82),
    updatedAt: new Date().toISOString(),
  };
  try {
    window.localStorage.setItem(
      DESKTOP_WALLPAPER_STORAGE_KEY,
      JSON.stringify(nextConfig),
    );
  } catch (err) {
    const error = new Error("桌面背景保存失败，可能是图片过大或浏览器本地存储空间不足");
    error.cause = err;
    throw error;
  }
  return nextConfig;
}

export function resolveDesktopWallpaperAppearance(config = {}) {
  const normalizedConfig = config?.presetId ? config : getDesktopWallpaperConfig();
  const preset = getWallpaperPresetById(normalizedConfig?.presetId);
  const customImage = String(normalizedConfig?.customImage || "").trim();
  const isCustom = String(normalizedConfig?.mode || "").trim() === "custom" && customImage;
  const luminance = isCustom
    ? clampNumber(normalizedConfig?.customLuminance ?? preset.luminance ?? 0.82, 0, 1)
    : clampNumber(preset.luminance ?? 0.82, 0, 1);
  return {
    id: isCustom ? "custom" : preset.id,
    label: isCustom ? "自定义壁纸" : preset.label,
    isCustom,
    background: isCustom
      ? `linear-gradient(rgba(15, 23, 42, 0.18), rgba(15, 23, 42, 0.32)), url("${customImage}") center / cover no-repeat`
      : preset.background,
    thumbnail: isCustom
      ? `linear-gradient(rgba(15, 23, 42, 0.12), rgba(15, 23, 42, 0.24)), url("${customImage}") center / cover no-repeat`
      : preset.thumbnail,
    ambientLeft: isCustom ? "rgba(15, 23, 42, 0.18)" : preset.ambientLeft,
    ambientRight: isCustom ? "rgba(255, 255, 255, 0.1)" : preset.ambientRight,
    meshOpacity: isCustom ? 0.18 : Number(preset.meshOpacity || 1),
    dockTone: resolveDockToneTokens(luminance),
  };
}

export function getDesktopAppById(appId) {
  const normalizedId = String(appId || "").trim();
  return DESKTOP_APP_ITEMS.find((item) => item.id === normalizedId) || DESKTOP_APP_ITEMS[0];
}

export function canAccessDesktopApp(target) {
  const app = typeof target === "string" ? getDesktopAppById(target) : target;
  return canAccessPath(app?.path || "");
}

export function isRequiredDesktopDockApp(appId) {
  return DESKTOP_REQUIRED_DOCK_APP_IDS.includes(String(appId || "").trim());
}

export function canPinDesktopApp(appId) {
  const normalizedId = String(appId || "").trim();
  if (!normalizedId) return false;
  if (isRequiredDesktopDockApp(normalizedId)) return false;
  return DESKTOP_OPTIONAL_DOCK_APP_IDS.includes(normalizedId);
}

export function resolveDesktopAppMeta(pathname) {
  const normalizedPath = String(pathname || "").trim() || "/";
  const activeItem = DESKTOP_APP_ITEMS.find((item) => item.match?.(normalizedPath)) || DESKTOP_APP_ITEMS[0];

  return {
    appId: activeItem.id,
    appName: activeItem.label,
    appEyebrow: activeItem.eyebrow || "Desktop App",
    appSummary: activeItem.summary || "当前页面作为桌面系统中的一个独立应用运行。",
    width: Number(activeItem.width || 1040),
    height: Number(activeItem.height || 720),
    path: activeItem.path,
  };
}

export function resolveDesktopLaunchPath(appId) {
  const app = getDesktopAppById(appId);
  const projectId = getStoredProjectContextId();
  if (app.id === "chat" && projectId) {
    return `/ai/chat?project_id=${encodeURIComponent(projectId)}`;
  }
  if (app.id === "materials" && projectId) {
    return `/materials?project_id=${encodeURIComponent(projectId)}`;
  }
  return app.path;
}

export function buildEmbeddedAppUrl(pathname, options = {}) {
  const normalizedPath = String(pathname || "").trim() || "/";
  const routePath = normalizedPath.startsWith("/") ? normalizedPath : `/${normalizedPath}`;
  const params = new URLSearchParams();
  params.set("embedded", "1");
  const windowId = String(options.windowId || "").trim();
  if (windowId) {
    params.set("desktop_window_id", windowId);
  }
  const reloadKey = String(options.reloadKey || "").trim();
  if (reloadKey) {
    params.set("desktop_reload_key", reloadKey);
  }
  const rootQuery = params.toString();
  return `/${rootQuery ? `?${rootQuery}` : ""}#${routePath}`;
}
