const LARK_AUTH_DOMAIN_OPTIONS = [
  "approval",
  "attendance",
  "base",
  "calendar",
  "contact",
  "docs",
  "drive",
  "im",
  "mail",
  "minutes",
  "okr",
  "sheets",
  "task",
  "vc",
  "wiki",
];

export function stripTerminalControlSequences(value) {
  return String(value || "")
    .replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\x1B\][^\x07]*(?:\x07|\x1B\\)/g, "")
    .replace(/\x1B/g, "");
}

export function hasLarkAuthBusinessDomainPromptText(value) {
  const text = stripTerminalControlSequences(value).toLowerCase();
  return Boolean(/业务域/.test(text) && /选择|请选择|select|choose/.test(text));
}

export function hasAuthorizationPromptText(payload = {}, detailText = "") {
  return Boolean(
    String(payload?.authorization_url || "").trim() ||
      (payload?.interaction_schema &&
        typeof payload.interaction_schema === "object"),
  );
}

// 设备授权 / OAuth 登录是 agent 无关能力：从输出文本里识别授权链接，
// 渲染成统一的授权卡片。provider 顺序敏感：先匹配平台专用域，最后回退到
// 通用 device-code 模式（必须带 user_code 参数，避免误伤普通链接）。
// URL 按 RFC 3986 只含 ASCII：字符类一旦遇到空白、引号、括号、CJK 汉字或
// 全角标点就停下，避免把链接后紧跟（无空格）的中文文案一起吞进 URL。
const DEVICE_AUTH_URL_TAIL = "[^\\s\"'<>，。；、（）【】「」\\u4e00-\\u9fff\\uff00-\\uffef]";
const DEVICE_AUTH_PROVIDERS = [
  {
    key: "lark",
    label: "飞书",
    qrHint: "飞书 CLI 授权二维码",
    urlRe: new RegExp(
      `https://accounts\\.feishu\\.cn/oauth/v1/device/verify\\?${DEVICE_AUTH_URL_TAIL}+`,
      "i",
    ),
  },
  {
    key: "github",
    label: "GitHub",
    qrHint: "GitHub 设备授权页",
    urlRe: new RegExp(
      `https://github\\.com/login/device(?:/${DEVICE_AUTH_URL_TAIL}*)?`,
      "i",
    ),
  },
  {
    key: "google",
    label: "Google",
    qrHint: "Google 设备授权页",
    urlRe: new RegExp(
      `https://(?:www\\.)?google\\.com/device${DEVICE_AUTH_URL_TAIL}*`,
      "i",
    ),
  },
  {
    key: "device-code",
    label: "设备",
    qrHint: "设备授权页",
    urlRe: new RegExp(
      `https?://${DEVICE_AUTH_URL_TAIL}+[?&]user_code=${DEVICE_AUTH_URL_TAIL}+`,
      "i",
    ),
  },
];

const DEVICE_AUTH_USER_CODE_TEXT_RE =
  /(?:user[\s_-]?code|验证码|配对码|授权码)\s*[:：]?\s*([A-Z0-9][A-Z0-9-]{3,})/i;

function cleanDeviceAuthUrl(value) {
  return String(value || "")
    .trim()
    .replace(/[)\]}>"'，。；、]+$/g, "");
}

function matchDeviceAuthProvider(text) {
  for (const provider of DEVICE_AUTH_PROVIDERS) {
    const match = text.match(provider.urlRe);
    if (match?.[0]) {
      return { provider, authorizationUrl: cleanDeviceAuthUrl(match[0]) };
    }
  }
  return null;
}

export function extractDeviceAuthUrl(value) {
  const text = stripTerminalControlSequences(value);
  return matchDeviceAuthProvider(text)?.authorizationUrl || "";
}
export function extractDeviceAuthUserCode(authorizationUrl = "", rawText = "") {
  const url = String(authorizationUrl || "").trim();
  if (url) {
    try {
      const fromUrl = String(
        new URL(url).searchParams.get("user_code") || "",
      ).trim();
      if (fromUrl) return fromUrl;
    } catch (_) {
      const match = url.match(/[?&]user_code=([^&#\s]+)/i);
      if (match?.[1]) {
        try {
          return decodeURIComponent(match[1]).trim();
        } catch (_) {
          return String(match[1]).trim();
        }
      }
    }
  }
  // URL 不携带 user_code 时（GitHub/Google 设备流），从输出文本里兜底识别。
  const textMatch = stripTerminalControlSequences(rawText).match(
    DEVICE_AUTH_USER_CODE_TEXT_RE,
  );
  return String(textMatch?.[1] || "").trim();
}

export function extractDeviceAuthReply(value) {
  const text = stripTerminalControlSequences(value);
  const matched = matchDeviceAuthProvider(text);
  if (!matched) return null;
  const { provider, authorizationUrl } = matched;
  const userCode = extractDeviceAuthUserCode(authorizationUrl, text);
  const replyText = [
    `打开这个链接完成${provider.label}授权：`,
    "",
    authorizationUrl,
    ...(userCode ? ["", `授权码：${userCode}`] : []),
    "",
    provider.qrHint,
    "",
    "授权有效期通常 10 分钟。完成后回来告诉我“已授权完成”，我会继续执行后续命令。",
  ].join("\n");
  return {
    provider: provider.key,
    providerLabel: provider.label,
    authorizationUrl,
    userCode,
    replyText,
  };
}

export const TERMINAL_CHOICE_FALLBACK_PROVIDERS = [
  {
    key: "lark-auth-domain",
    match({ text, activeCommand }) {
      const terminalText = stripTerminalControlSequences(text).trim();
      const command = String(activeCommand || "").trim();
      const hasAuthLoginCommand = /\blark-cli\s+auth\s+login\b/.test(command);
      const hasDomainPrompt =
        /(?:请选择|选择|select|choose).{0,30}业务域|业务域.{0,30}(?:请选择|选择|select|choose|enter confirm)/i.test(
          terminalText,
        );
      // Lark CLI 授权域选择不会总是输出结构化 schema，这里保留文本兜底识别。
      return Boolean(
        hasDomainPrompt ||
          (hasAuthLoginCommand &&
            /业务域/.test(terminalText) &&
            /选择|select|choose|enter confirm|上下键|方向键|回车/i.test(
              terminalText,
            )),
      );
    },
    options() {
      return LARK_AUTH_DOMAIN_OPTIONS.map((value) => ({
        label: value,
        value,
        selected: false,
        highlighted: false,
      }));
    },
  },
];

export function inferTerminalChoiceType(text, options) {
  if (/至少选择|多选|复选|toggle|select all|ctrl\+a|space|空格/i.test(text)) {
    return "checkbox";
  }
  if ((options || []).filter((item) => item.selected).length > 1) {
    return "checkbox";
  }
  return "radio";
}

export function terminalChoiceDescription(type) {
  if (type === "checkbox") {
    return "已识别到终端里的多选题，直接勾选选项后确认即可，不需要手动按方向键。";
  }
  return "已识别到终端里的单选题，直接选择一项后确认即可，不需要手动按方向键。";
}

export function hasTerminalChoiceControlSignal(lines, text) {
  const terminalText = String(text || "").trim();
  if (!terminalText) return false;
  const hasVisibleChoiceMarker = (lines || []).some((line) =>
    /^\s*(?:[>❯]\s*)?(?:\[[ xX]\]|[◉●○◯◎✓✔])\s*\S+/u.test(String(line || "")),
  );
  if (hasVisibleChoiceMarker) return true;
  return /enter confirm|enter to (?:select|confirm)|use .*arrow|arrow keys|press .*enter|上下键|方向键|回车(?:确认|选择)|空格(?:选择|切换)|select one|choose one|choose from|请选择以下/i.test(
    terminalText,
  );
}

export function isPlainTerminalChoiceLabel(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  if (/\s/.test(text)) return false;
  if (/[，。；：、,.!?！？*`#()[\]{}<>]/.test(text)) return false;
  return (
    /^[A-Za-z][\w:-]{1,40}$/.test(text) || /^[\u4e00-\u9fff]{1,12}$/u.test(text)
  );
}

export function parseTerminalChoiceLine(line) {
  const raw = String(line || "").trim();
  if (!raw) return null;
  if (
    /toggle|enter confirm|ctrl\+a|filter|请至少选择|选择要|select all/i.test(raw)
  ) {
    return null;
  }
  if (/^(?:[#>$]|---|\/|```|[-*+]\s+|\d+[.)、]\s+|\*\s*请)/.test(raw)) {
    return null;
  }
  const match = raw.match(
    /^(?<cursor>[>❯])?\s*(?<marker>\[[ xX]\]|[◉●○◯◎✓✔•])?\s*(?<label>[A-Za-z][\w:-]{1,80}|[\u4e00-\u9fff][^\s]{0,40})(?:\s.*)?$/u,
  );
  if (!match?.groups?.label) return null;
  const cursor = String(match.groups.cursor || "").trim();
  const marker = String(match.groups.marker || "").trim();
  const label = String(match.groups.label || "").trim();
  if (!label || ["RUN", "pwd", "echo", "login", "auth"].includes(label))
    return null;
  if (!cursor && !marker && !isPlainTerminalChoiceLabel(raw)) return null;
  return {
    label,
    value: label,
    selected: /\[[xX]\]|[◉●✓✔]/.test(marker),
    highlighted: Boolean(cursor),
  };
}

export function sanitizeTerminalOutputLines(text) {
  const raw = String(text || "");
  if (!raw) return [];
  const clean = raw
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b[PX^_].*?\x1b\\/gs, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\x1b[@-Z\\-_]/g, "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");
  return clean
    .split("\n")
    .map((line) => line.replace(/\s+$/g, "").trim())
    .filter((line) => {
      if (!line) return false;
      if (/^[%$#>]$/.test(line)) return false;
      if (/^[^\s@]+@[^\s]+\s+[^%]*%$/.test(line)) return false;
      if (/^[^\s@]+@[^\s]+\s+[^%]*%\s+.+/.test(line)) return false;
      return true;
    });
}
