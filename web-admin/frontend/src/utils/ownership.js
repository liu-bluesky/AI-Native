export function canManageRecord(record) {
  const currentRole = String(localStorage.getItem("role") || "").trim().toLowerCase();
  if (currentRole === "admin") {
    return true;
  }
  if (typeof record?.can_manage === "boolean") {
    return record.can_manage;
  }
  const currentUsername = String(localStorage.getItem("username") || "").trim();
  const owner = String(record?.created_by || record?.owner_username || "").trim();
  return !!currentUsername && !!owner && currentUsername === owner;
}

export function formatSharedUsers(usernames) {
  const items = Array.isArray(usernames)
    ? usernames.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  return items.length ? items.join("、") : "未指定";
}

export function formatRecordVisibility(record) {
  if (!String(record?.created_by || "").trim()) {
    return "系统共享";
  }
  const scope = String(record?.share_scope || "private").trim();
  if (scope === "all_users") {
    return "所有人";
  }
  if (scope === "selected_users") {
    const sharedUsers = Array.isArray(record?.shared_with_usernames)
      ? record.shared_with_usernames.filter(Boolean)
      : [];
    return sharedUsers.length ? `指定用户(${sharedUsers.length})` : "指定用户";
  }
  const sharedViaEmployees = Array.isArray(record?.shared_via_employees)
    ? record.shared_via_employees.filter((item) => item?.id)
    : [];
  if (sharedViaEmployees.length) {
    return `通过员工共享(${sharedViaEmployees.length})`;
  }
  return "仅自己";
}

export function formatRecordOwner(record) {
  const owner = String(record?.created_by || "").trim();
  return owner || "共享";
}

export function getOwnershipDeniedMessage(record, action = "操作") {
  const owner = String(record?.created_by || "").trim();
  if (owner) {
    return `该数据由 ${owner} 创建，你只能使用，不能${action}`;
  }
  return `该数据是共享数据，你只能使用，不能${action}`;
}
