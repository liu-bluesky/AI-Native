// Shared constants for the ProjectChat view while it is being split into modules.

export const CODE_COPY_ICON_HTML =
  '<span class="el-icon chat-code-block__icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><path fill="currentColor" d="M128 320v576h576V320zm-32-64h640a32 32 0 0 1 32 32v640a32 32 0 0 1-32 32H96a32 32 0 0 1-32-32V288a32 32 0 0 1 32-32M960 96v704a32 32 0 0 1-32 32h-96v-64h64V128H384v64h-64V96a32 32 0 0 1 32-32h576a32 32 0 0 1 32 32M256 672h320v64H256zm0-192h320v64H256z" /></svg></span>';
export const CODE_COPIED_ICON_HTML =
  '<span class="el-icon chat-code-block__icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><path fill="currentColor" d="M406.656 706.944 195.84 496.256a32 32 0 1 0-45.248 45.248l256 256 512-512a32 32 0 0 0-45.248-45.248L406.592 706.944z" /></svg></span>';
export const CODE_PREVIEW_ICON_HTML =
  '<span class="el-icon chat-code-block__icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><path fill="currentColor" d="M942.2 486.2C847.4 334.6 691 224 512 224S176.6 334.6 81.8 486.2a48.9 48.9 0 0 0 0 51.6C176.6 689.4 333 800 512 800s335.4-110.6 430.2-262.2a48.9 48.9 0 0 0 0-51.6M512 736c-147.8 0-279-88.5-363.1-224C233 376.5 364.2 288 512 288s279 88.5 363.1 224C791 647.5 659.8 736 512 736m0-352a128 128 0 1 0 0 256 128 128 0 0 0 0-256m0 192a64 64 0 1 1 0-128 64 64 0 0 1 0 128" /></svg></span>';
export const EMPLOYEE_DRAFT_BLOCK_RE = /```employee-draft\s*([\s\S]*?)```/i;
export const PREVIEWABLE_CODE_LANGUAGES = new Set(["vue", "html", "htm"]);
export const PROJECT_STATS_COMMAND = "/stats-report";
export const PROJECT_STATS_COMMAND_ALIASES = [];
export const HOST_RUN_COMMAND = "/run";
export const HOST_RUN_COMMAND_ALIASES = ["/host-run", "/shell"];
export const LARK_CLI_COMMAND = "/lark-cli";
export const LARK_CLI_COMMAND_ALIASES = ["/larkcli", "/feishucli", "/feishu-cli"];
export const LARK_CLI_SKILL_ROOT_RELATIVE = ".ai-employee/skills/host-marketplace";
export const PROJECT_STATS_REPORT_DAYS = 7;
export const STATISTICS_ANALYSIS_DRAFT_STORAGE_PREFIX = "statistics_analysis_draft:";
export const STATISTICS_ANALYSIS_DRAFT_QUERY_KEY = "statistics_analysis_draft_key";
export const PLUGIN_INSTALL_DRAFT_STORAGE_PREFIX = "plugin-install-draft:";
export const PLUGIN_INSTALL_DRAFT_QUERY_KEY = "plugin_install_draft_key";
export const CHAT_BASE_ROUTE_PATH = "/ai/chat";
