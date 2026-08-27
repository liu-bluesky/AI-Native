export function isWorkspaceFileMissing(error) {
  return /not found|no such file|enoent|os error 2|cannot find the (?:file|path) specified|系统找不到指定的(?:文件|路径)|找不到指定的(?:文件|路径)|不存在/i.test(
    String(error?.detail || error?.message || error || ""),
  );
}
