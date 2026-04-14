export interface TaskTreeHealthIssue {
  code: string;
  severity: string;
  category: string;
  message: string;
  recommended_action: string;
  evidence: string[];
}

export interface TaskTreeHealth {
  detected_intent: string;
  health_score: number;
  issue_count: number;
  rebuild_recommended: boolean;
  rebuild_reason: string;
  safe_to_display: boolean;
  issues: TaskTreeHealthIssue[];
}

export function normalizeTaskTreeHealth(raw: unknown): TaskTreeHealth | null {
  if (!raw || typeof raw !== "object") return null;
  const issues = Array.isArray((raw as { issues?: unknown[] }).issues)
    ? ((raw as { issues: unknown[] }).issues || [])
        .map((item) => {
          if (!item || typeof item !== "object") return null;
          const code = String((item as { code?: unknown }).code || "").trim();
          if (!code) return null;
          return {
            code,
            severity: String((item as { severity?: unknown }).severity || "medium").trim().toLowerCase(),
            category: String((item as { category?: unknown }).category || "").trim(),
            message: String((item as { message?: unknown }).message || "").trim(),
            recommended_action: String(
              (item as { recommended_action?: unknown }).recommended_action || "",
            ).trim(),
            evidence: Array.isArray((item as { evidence?: unknown[] }).evidence)
              ? ((item as { evidence: unknown[] }).evidence || [])
                  .map((entry) => String(entry || "").trim())
                  .filter(Boolean)
              : [],
          };
        })
        .filter(Boolean)
    : [];
  return {
    detected_intent: String((raw as { detected_intent?: unknown }).detected_intent || "").trim(),
    health_score: Number((raw as { health_score?: unknown }).health_score || 0),
    issue_count: Number((raw as { issue_count?: unknown }).issue_count || issues.length),
    rebuild_recommended: Boolean(
      (raw as { rebuild_recommended?: unknown }).rebuild_recommended,
    ),
    rebuild_reason: String((raw as { rebuild_reason?: unknown }).rebuild_reason || "").trim(),
    safe_to_display: Boolean((raw as { safe_to_display?: unknown }).safe_to_display),
    issues: issues as TaskTreeHealthIssue[],
  };
}

export function getTaskTreeHealthTone(health: TaskTreeHealth | null | undefined): string {
  if (health?.rebuild_recommended) return "danger";
  if (health && health.safe_to_display === false) return "warning";
  if (Number(health?.issue_count || 0) > 0) return "info";
  return "success";
}

export function getTaskTreeHealthTagType(health: TaskTreeHealth | null | undefined): string {
  const tone = getTaskTreeHealthTone(health);
  if (tone === "danger") return "danger";
  if (tone === "warning") return "warning";
  if (tone === "info") return "info";
  return "success";
}

export function getTaskTreeHealthLabel(health: TaskTreeHealth | null | undefined): string {
  if (health?.rebuild_recommended) return "建议重建任务树";
  if (health && health.safe_to_display === false) return "当前任务树存在高风险问题";
  if (Number(health?.issue_count || 0) > 0) return "当前任务树有待关注项";
  return "当前任务树健康";
}

export function getTaskTreeHealthSummary(health: TaskTreeHealth | null | undefined): string {
  if (!health) return "";
  if (health.rebuild_recommended) {
    return (
      String(health.rebuild_reason || "").trim()
      || String(health.issues?.[0]?.message || "").trim()
      || "当前任务树和真实目标不一致，建议先重建再继续。"
    );
  }
  if (health.safe_to_display === false) {
    return (
      String(health.issues?.[0]?.message || "").trim()
      || "当前任务树还不适合直接作为稳定执行路径展示。"
    );
  }
  if (Number(health.issue_count || 0) > 0) {
    return "当前任务树可以继续使用，但还存在少量待关注问题。";
  }
  return "当前任务树生成结果和目标基本一致，可以继续按节点推进。";
}
