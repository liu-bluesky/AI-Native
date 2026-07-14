import api from "@/utils/api.js";

const skillResourceIntentAliasGroups = [
  {
    match: [
      "java开发",
      "java后端",
      "java",
      "后端",
      "backend",
      "spring",
      "springboot",
      "spring boot",
      "jvm",
    ],
    queries: ["java", "spring", "spring boot", "backend", "jvm"],
  },
  {
    match: [
      "界面设计",
      "ui设计",
      "界面",
      "ui",
      "视觉",
      "交互",
      "排版",
      "设计系统",
      "frontend",
      "interface",
      "design system",
      "design-system",
    ],
    queries: ["ui", "frontend", "design", "interface", "design system"],
  },
  {
    match: [
      "css",
      "样式",
      "布局",
      "响应式",
      "动画",
      "style",
      "responsive",
      "animation",
    ],
    queries: ["css", "style", "responsive", "animation"],
  },
  {
    match: ["vue", "vue3", "composition api", "composition-api"],
    queries: ["vue", "vue3", "composition api"],
  },
  {
    match: [
      "浏览器",
      "调试",
      "性能",
      "chrome",
      "devtools",
      "browser",
      "performance",
    ],
    queries: ["chrome", "devtools", "browser", "performance"],
  },
  {
    match: [
      "架构",
      "架构设计",
      "技术选型",
      "系统设计",
      "architect",
      "architecture",
      "system design",
      "software architect",
    ],
    queries: [
      "software architect",
      "architecture",
      "architect",
      "system design",
    ],
  },
  {
    match: [
      "node",
      "nodejs",
      "node.js",
      "javascript",
      "js",
      "工程实践",
      "工具链",
    ],
    queries: ["nodejs", "node", "javascript", "js"],
  },
];

function normalizeMatchKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function normalizeSearchAliasKey(value) {
  return normalizeMatchKey(value).replace(/[\s._/+-]+/g, "");
}

function pushSkillResourceSearchQuery(buffer, seen, value) {
  const text = String(value || "").trim();
  const key = normalizeMatchKey(text);
  if (!text || !key || seen.has(key)) {
    return;
  }
  seen.add(key);
  buffer.push(text);
}

export function buildSkillResourceSearchQueries(query) {
  const rawQuery = String(query || "").trim();
  const normalized = normalizeMatchKey(rawQuery);
  const compact = normalizeSearchAliasKey(rawQuery);
  const queries = [];
  const seen = new Set();
  pushSkillResourceSearchQuery(queries, seen, rawQuery);
  const asciiTokens = rawQuery.match(/[A-Za-z][A-Za-z0-9.+#-]*/g) || [];
  asciiTokens.forEach((token) =>
    pushSkillResourceSearchQuery(queries, seen, token),
  );
  skillResourceIntentAliasGroups.forEach((group) => {
    const matched = group.match.some((token) => {
      const compactToken = normalizeSearchAliasKey(token);
      return (
        (normalized && normalized.includes(normalizeMatchKey(token))) ||
        (compact && compactToken && compact.includes(compactToken))
      );
    });
    if (!matched) {
      return;
    }
    group.queries.forEach((token) =>
      pushSkillResourceSearchQuery(queries, seen, token),
    );
  });
  return queries.slice(0, 6);
}

function buildVettSkillPageUrl(slug) {
  const normalized = String(slug || "")
    .trim()
    .replace(/^\/+|\/+$/g, "");
  return normalized ? `https://vett.sh/skills/${normalized}` : "";
}

function inferChineseSkillSummary(raw) {
  const name = String(raw?.name || raw?.slug || "").trim();
  const slug = String(raw?.slug || "")
    .trim()
    .toLowerCase();
  const description = String(raw?.description || "").trim();
  const joined = `${name} ${slug} ${description}`.toLowerCase();
  if (joined.includes("ui") || joined.includes("interface")) {
    return "适合界面审美、排版层级、交互一致性和设计系统类智能体。";
  }
  if (
    joined.includes("css") ||
    joined.includes("style") ||
    joined.includes("responsive")
  ) {
    return "适合布局系统、响应式、动画和样式治理相关任务。";
  }
  if (joined.includes("vue")) {
    return "适合 Vue 组件设计、Composition API 和工程实践相关任务。";
  }
  if (
    joined.includes("chrome") ||
    joined.includes("devtools") ||
    joined.includes("browser")
  ) {
    return "适合浏览器调试、渲染链路分析和性能定位相关任务。";
  }
  if (joined.includes("architect") || joined.includes("architecture")) {
    return "适合系统拆分、技术选型、边界设计和架构治理相关任务。";
  }
  if (
    joined.includes("node") ||
    joined.includes("javascript") ||
    joined.includes("js")
  ) {
    return "适合 JS 工具链、构建脚本、运行时治理和工程交付相关任务。";
  }
  if (joined.includes("frontend") || joined.includes("design")) {
    return "适合前端界面、组件设计和交付规范相关任务。";
  }
  return "适合相关技能补强场景，建议结合原始说明和来源页面进一步判断是否匹配当前任务。";
}

function resolveLocalizedSkillSummary(raw, url, externalSkillSites) {
  const normalizedUrl = String(url || "").trim();
  const matched = (externalSkillSites || []).find(
    (item) => String(item?.url || "").trim() === normalizedUrl,
  );
  if (matched?.description) {
    return String(matched.description || "").trim();
  }
  return inferChineseSkillSummary(raw);
}

function normalizeSkillResourceSearchItem(raw, options = {}) {
  const latestVersion =
    raw?.latest_version && typeof raw.latest_version === "object"
      ? raw.latest_version
      : {};
  const risk = String(latestVersion.risk || "")
    .trim()
    .toLowerCase();
  const scanStatus = String(latestVersion.scan_status || "")
    .trim()
    .toLowerCase();
  const policyAction = String(latestVersion.policy_action || "")
    .trim()
    .toLowerCase();
  const latestVersionNumber = String(latestVersion.version || "").trim();
  const installCount =
    Number(raw?.install_count ?? raw?.installCount ?? 0) || 0;
  const pageUrl =
    buildVettSkillPageUrl(raw?.slug) || String(raw?.source_url || "").trim();
  return {
    id: String(raw?.id || "").trim(),
    slug: String(raw?.slug || "").trim(),
    title: String(raw?.name || raw?.slug || "").trim(),
    description: String(raw?.description || "").trim(),
    url: pageUrl,
    localizedDescription: resolveLocalizedSkillSummary(
      raw,
      pageUrl,
      options.externalSkillSites,
    ),
    latestVersionLabel: latestVersionNumber ? `v${latestVersionNumber}` : "",
    canInstall:
      !!latestVersionNumber &&
      scanStatus === "completed" &&
      policyAction !== "deny" &&
      policyAction !== "blocked",
    requiresReview: policyAction === "review",
    risk,
    scanStatus,
    version: latestVersionNumber,
    installCount,
  };
}

function scoreSkillResourceSearchItem(
  item,
  rawQuery,
  matchedQuery,
  queryIndex,
  preferredSites,
) {
  const joined = normalizeMatchKey(
    `${item?.title || ""} ${item?.slug || ""} ${item?.description || ""}`,
  );
  const raw = normalizeMatchKey(rawQuery);
  const matched = normalizeMatchKey(matchedQuery);
  let score = 120 - queryIndex * 12;
  if (matched && joined.includes(matched)) {
    score += 36;
  }
  if (raw && joined.includes(raw)) {
    score += 48;
  }
  if (matched && normalizeMatchKey(item?.title || "") === matched) {
    score += 18;
  }
  if (item?.canInstall) {
    score += 6;
  }
  if ((preferredSites || []).some((site) => site.url === item?.url)) {
    score += 14;
  }
  score += Math.min(18, Math.log10((Number(item?.installCount) || 0) + 1) * 8);
  return score;
}

function mergeSkillResourceSearchResults(groups, rawQuery, options = {}) {
  const merged = new Map();
  groups.forEach(({ query, items, index }) => {
    items.forEach((rawItem) => {
      const item = normalizeSkillResourceSearchItem(rawItem, options);
      if (!item.slug || !item.url) {
        return;
      }
      const score = scoreSkillResourceSearchItem(
        item,
        rawQuery,
        query,
        index,
        options.preferredSites,
      );
      const existing = merged.get(item.slug);
      if (!existing || score > existing.searchScore) {
        merged.set(item.slug, {
          ...item,
          searchScore: score,
          matchedQuery: query,
        });
      }
    });
  });
  return Array.from(merged.values())
    .sort((left, right) => {
      if (right.searchScore !== left.searchScore) {
        return right.searchScore - left.searchScore;
      }
      if (right.installCount !== left.installCount) {
        return right.installCount - left.installCount;
      }
      return left.title.localeCompare(right.title);
    })
    .slice(0, 18);
}

async function fetchSkillResourceSearchItems(query) {
  const data = await api.get("/skill-resources", {
    params: {
      source: "vett",
      q: query,
      limit: 8,
      offset: 0,
    },
  });
  return Array.isArray(data?.items) ? data.items : [];
}

export async function searchSkillResourceItems(query, options = {}) {
  const expandedQueries = buildSkillResourceSearchQueries(query);
  if (!expandedQueries.length) {
    return { resolvedQueries: [], results: [] };
  }
  const settled = await Promise.allSettled(
    expandedQueries.map((searchQuery) =>
      fetchSkillResourceSearchItems(searchQuery),
    ),
  );
  const groups = settled
    .map((entry, index) => {
      if (entry.status !== "fulfilled") {
        return null;
      }
      return {
        query: expandedQueries[index],
        index,
        items: Array.isArray(entry.value) ? entry.value : [],
      };
    })
    .filter(Boolean);
  if (!groups.length) {
    const failed = settled.find((entry) => entry.status === "rejected");
    throw failed?.reason || new Error("搜索技能资源失败");
  }
  return {
    resolvedQueries: expandedQueries,
    results: mergeSkillResourceSearchResults(groups, query, options),
  };
}

export function installVettSkillResource(slug, options = {}) {
  // Service 只封装安装协议，风险确认和消息提示仍由页面层控制。
  return api.post(`/skill-resources/vett/${encodeURIComponent(slug)}/install`, {
    version: String(options.version || "").trim(),
    install_dir: String(options.installDir || "").trim(),
    import_to_library: false,
  });
}
