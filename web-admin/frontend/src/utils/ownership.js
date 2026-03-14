export function canManageRecord(record) {
  return !!record?.can_manage;
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
