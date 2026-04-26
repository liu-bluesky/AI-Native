// Frontend hints for commands that should receive extra confirmation.

export const HIGH_RISK_RULES = [
  {
    id: "delete_force",
    label: "删除类命令",
    severity: "high",
    pattern: /\brm\s+-rf\b|\bdel\s+\/[qsf]\b/i,
  },
  {
    id: "git_hard_reset",
    label: "Git 强制回滚",
    severity: "high",
    pattern: /\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-fd/i,
  },
  {
    id: "shell_pipe_remote",
    label: "远程脚本直执行",
    severity: "high",
    pattern: /(?:curl|wget)[^\n|]*\|\s*(?:sh|bash|zsh)/i,
  },
  {
    id: "network_transfer",
    label: "网络传输/外发",
    severity: "medium",
    pattern: /\b(?:scp|rsync|curl|wget)\b/i,
  },
];
