const LANGUAGE_DEFINITIONS = {
  "zh-CN": { label: "简体中文", reasoningLabel: "简体中文" },
  "zh-TW": { label: "繁体中文", reasoningLabel: "繁体中文" },
  en: { label: "English", reasoningLabel: "English" },
  ja: { label: "日本語", reasoningLabel: "日本語" },
  ko: { label: "한국어", reasoningLabel: "한국어" },
};

const EXPLICIT_LANGUAGE_PATTERNS = [
  { code: "zh-TW", pattern: /(?:请|請)?(?:用|使用|以).{0,8}(?:繁体中文|繁體中文|繁体|繁體)|(?:respond|answer|reply|write)\s+in\s+traditional\s+chinese/i },
  { code: "zh-CN", pattern: /(?:请|請)?(?:用|使用|以).{0,8}(?:简体中文|簡體中文|(?<!繁体)(?<!繁體)中文|汉语|漢語)|(?:respond|answer|reply|write)\s+in\s+(?:simplified\s+)?chinese/i },
  { code: "en", pattern: /(?:请|請)?(?:用|使用|以).{0,8}(?:英文|英语|英語)|(?:respond|answer|reply|write)\s+in\s+english/i },
  { code: "ja", pattern: /(?:请|請)?(?:用|使用|以).{0,8}(?:日文|日语|日語|日本語)|(?:respond|answer|reply|write)\s+in\s+japanese/i },
  { code: "ko", pattern: /(?:请|請)?(?:用|使用|以).{0,8}(?:韩文|韓文|韩语|韓語|한국어)|(?:respond|answer|reply|write)\s+in\s+korean/i },
];

function normalizeLanguageSource(value) {
  return String(value || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`[^`]*`/g, " ")
    .replace(/https?:\/\/\S+/gi, " ")
    .replace(/(?:[A-Za-z]:\\|\.{0,2}\/)[^\s]+/g, " ")
    .trim();
}

function countMatches(text, pattern) {
  return (text.match(pattern) || []).length;
}

export function detectChatResponseLanguage(value) {
  const text = normalizeLanguageSource(value);
  let explicitMatch = null;
  for (const item of EXPLICIT_LANGUAGE_PATTERNS) {
    const match = text.match(item.pattern);
    if (!match || Number(match.index) < 0) continue;
    if (!explicitMatch || Number(match.index) >= explicitMatch.index) {
      explicitMatch = { code: item.code, index: Number(match.index) };
    }
  }
  if (explicitMatch) {
    return {
      code: explicitMatch.code,
      explicit: true,
      ...LANGUAGE_DEFINITIONS[explicitMatch.code],
    };
  }

  const japaneseCount = countMatches(text, /[\u3040-\u30ff]/g);
  const koreanCount = countMatches(text, /[\uac00-\ud7af]/g);
  const hanCount = countMatches(text, /[\u3400-\u4dbf\u4e00-\u9fff]/g);
  const latinCount = countMatches(text, /[A-Za-z]/g);
  const cjkCount = japaneseCount + koreanCount + hanCount;

  let code = "zh-CN";
  if (japaneseCount >= 2 && japaneseCount >= koreanCount) {
    code = "ja";
  } else if (koreanCount >= 2) {
    code = "ko";
  } else if (hanCount >= 2 && hanCount >= latinCount / 4) {
    code = "zh-CN";
  } else if (latinCount > 0 && cjkCount === 0) {
    code = "en";
  }
  return { code, explicit: false, ...LANGUAGE_DEFINITIONS[code] };
}

export function buildChatResponseLanguageInstruction(value) {
  const language = detectChatResponseLanguage(value);
  return [
    "本轮语言规则：",
    `- 用户本轮要求或主要使用的语言是：${language.label}。`,
    `- 内部思考内容（reasoning/thinking）和最终回答都必须使用${language.reasoningLabel}。`,
    "- 代码、命令、文件路径、日志原文、接口字段和专有名词保持原样，不要为了统一语言而翻译或改写。",
    "- 如果用户在本轮明确指定另一种输出语言，以用户的明确指定为最高优先级。",
  ].join("\n");
}

export function appendChatResponseLanguageInstruction(prompt, languageSource = prompt) {
  return [
    String(prompt || "").trim(),
    "",
    buildChatResponseLanguageInstruction(languageSource),
  ]
    .filter(Boolean)
    .join("\n");
}
