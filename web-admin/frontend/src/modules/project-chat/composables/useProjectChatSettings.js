import { ref } from "vue";
import { CHAT_SETTINGS_DEFAULTS } from "@/modules/project-chat/constants/chatSettingsDefaults.js";

/**
 * 管理项目聊天设置表单状态和保存标记。
 * API 调用已迁入 `services/projectChatSettingsApi.js`，本 composable 只持有表单状态。
 */
export function useProjectChatSettings() {
  const projectChatSettings = ref({ ...CHAT_SETTINGS_DEFAULTS });
  const settingsSaving = ref(false);

  return {
    projectChatSettings,
    settingsSaving,
  };
}
