import { ref } from "vue";
import { CHAT_SETTINGS_DEFAULTS } from "@/modules/project-chat/constants/chatSettingsDefaults.js";

/**
 * 管理项目聊天设置表单状态和保存标记。
 * 项目聊天设置只持有本机表单状态，持久化由 ProjectChat 写入本地项目关系。
 */
export function useProjectChatSettings() {
  const projectChatSettings = ref({ ...CHAT_SETTINGS_DEFAULTS });
  const settingsSaving = ref(false);

  return {
    projectChatSettings,
    settingsSaving,
  };
}
