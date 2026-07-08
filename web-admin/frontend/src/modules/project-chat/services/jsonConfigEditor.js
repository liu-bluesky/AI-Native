export function cloneJson(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function isMissingConfigText(value) {
  const raw = String(value ?? "").trim();
  return !raw || raw.toLowerCase() === "undefined";
}

export function normalizeJsonConfigText(text, fallbackText = "{}") {
  return isMissingConfigText(text) ? String(fallbackText ?? "{}") : String(text);
}

export function normalizeConfigFileContent(text, fallbackContent = "{}") {
  return isMissingConfigText(text) ? String(fallbackContent ?? "{}") : String(text);
}

function normalizePath(value, fallback) {
  return String(value || fallback || "").trim();
}

export function createJsonConfigEditor(options = {}) {
  const label = String(options.label || "配置").trim();
  const globalPathLabel = String(options.globalPathLabel || "").trim();
  const projectPathLabel = String(options.projectPathLabel || "").trim();
  const normalize =
    typeof options.normalize === "function" ? options.normalize : (value) => value;
  const hasNative =
    typeof options.hasNative === "function" ? options.hasNative : () => false;
  const globalDefaultConfig = options.globalDefaultConfig ?? {};
  const projectDefaultConfig = options.projectDefaultConfig ?? {};

  const format = (value) => JSON.stringify(normalize(value), null, 2);

  const parse = (text) => {
    let parsed;
    try {
      parsed = JSON.parse(normalizeJsonConfigText(text));
    } catch (err) {
      throw new Error(`${label} JSON 解析失败：${err?.message || "格式错误"}`);
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error(`${label} 必须是 JSON 对象`);
    }
    return normalize(parsed, {});
  };

  const normalizeResult = (result, fallback = {}) => {
    const scope = fallback.scope === "project" ? "project" : "global";
    const fallbackConfig =
      fallback.config ??
      (scope === "project" ? projectDefaultConfig : globalDefaultConfig);
    const fallbackContent = fallback.content ?? format(fallbackConfig);
    const content = normalizeConfigFileContent(result?.content, fallbackContent);
    return {
      scope,
      path: normalizePath(
        result?.path,
        fallback.path || (scope === "project" ? projectPathLabel : globalPathLabel),
      ),
      exists: Boolean(result?.exists ?? fallback.exists),
      content,
      config: parse(content),
      native: Boolean(fallback.native),
    };
  };

  const readGlobal = async () => {
    if (!hasNative()) {
      return normalizeResult(null, {
        scope: "global",
        path: globalPathLabel,
        exists: false,
        config: cloneJson(globalDefaultConfig),
        native: false,
      });
    }
    return normalizeResult(await options.readNativeGlobal(), {
      scope: "global",
      path: globalPathLabel,
      exists: false,
      config: cloneJson(globalDefaultConfig),
      native: true,
    });
  };

  const writeGlobal = async (config) => {
    if (!hasNative()) {
      throw new Error(`当前不是桌面端，无法写入全局 ${label}文件`);
    }
    const content = format(config);
    return normalizeResult(await options.writeNativeGlobal(content), {
      scope: "global",
      path: globalPathLabel,
      exists: true,
      content,
      native: true,
    });
  };

  const readProject = async (workspacePath = "") => {
    const normalizedWorkspacePath = String(workspacePath || "").trim();
    if (!normalizedWorkspacePath || !hasNative()) {
      return normalizeResult(null, {
        scope: "project",
        path: projectPathLabel,
        exists: false,
        config: cloneJson(projectDefaultConfig),
        native: false,
      });
    }
    return normalizeResult(
      await options.readNativeProject(normalizedWorkspacePath),
      {
        scope: "project",
        path: projectPathLabel,
        exists: false,
        config: cloneJson(projectDefaultConfig),
        native: true,
      },
    );
  };

  const writeProject = async (workspacePath = "", config) => {
    const normalizedWorkspacePath = String(workspacePath || "").trim();
    if (!normalizedWorkspacePath) {
      throw new Error(`缺少项目工作区路径，无法写入项目 ${label}文件`);
    }
    if (!hasNative()) {
      throw new Error(`当前不是桌面端，无法写入项目 ${label}文件`);
    }
    const content = format(config);
    return normalizeResult(
      await options.writeNativeProject(normalizedWorkspacePath, content),
      {
        scope: "project",
        path: projectPathLabel,
        exists: true,
        content,
        native: true,
      },
    );
  };

  return {
    format,
    parse,
    normalizeResult,
    readGlobal,
    writeGlobal,
    readProject,
    writeProject,
  };
}
