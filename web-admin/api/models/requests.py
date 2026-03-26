"""Pydantic 请求模型"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class InitSetupReq(BaseModel):
    username: str
    password: str


class LoginReq(BaseModel):
    username: str
    password: str


class RegisterReq(BaseModel):
    username: str = ""
    email: str = ""
    password: str


class UserCreateReq(BaseModel):
    username: str
    password: str
    role: str = "user"


class UserPasswordUpdateReq(BaseModel):
    password: str


class UserSettingsUpdateReq(BaseModel):
    default_ai_provider_id: str = ""


class RoleCreateReq(BaseModel):
    id: str
    name: str
    description: str = ""
    permissions: list[str] = []


class RoleUpdateReq(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


class EmployeeCreateReq(BaseModel):
    name: str
    description: str = ""
    goal: str = ""
    share_scope: str = "private"
    shared_with_usernames: list[str] = []
    skills: list[str] = []
    rule_bindings: list[dict[str, Any] | str] = []
    rule_ids: list[str] = []
    rule_domains: list[str] = []
    memory_scope: str = "project"
    memory_retention_days: int = 90
    tone: str = "professional"
    verbosity: str = "concise"
    language: str = "zh-CN"
    style_hints: list[str] = []
    default_workflow: list[str] = []
    tool_usage_policy: str = ""
    auto_evolve: bool = True
    evolve_threshold: float = 0.8
    mcp_enabled: bool = True
    feedback_upgrade_enabled: bool = False


class EmployeeUpdateReq(BaseModel):
    name: str | None = None
    description: str | None = None
    goal: str | None = None
    share_scope: str | None = None
    shared_with_usernames: list[str] | None = None
    skills: list[str] | None = None
    rule_bindings: list[dict[str, Any] | str] | None = None
    rule_ids: list[str] | None = None
    rule_domains: list[str] | None = None
    memory_scope: str | None = None
    memory_retention_days: int | None = None
    tone: str | None = None
    verbosity: str | None = None
    language: str | None = None
    style_hints: list[str] | None = None
    default_workflow: list[str] | None = None
    tool_usage_policy: str | None = None
    auto_evolve: bool | None = None
    evolve_threshold: float | None = None
    mcp_enabled: bool | None = None
    feedback_upgrade_enabled: bool | None = None


class EmployeeDraftGenerateReq(BaseModel):
    message: str
    history: list[dict[str, Any]] = []
    system_prompt: str | None = None
    provider_id: str = ""
    model_name: str = ""
    temperature: float | None = None


class EmployeeAgentTemplateImportReq(BaseModel):
    source_type: str = "git"
    source: str = ""
    subdirectory: str = ""
    branch: str = ""
    limit: int = 40


class AgentTemplateSaveReq(BaseModel):
    name: str = ""
    name_zh: str = ""
    description: str = ""
    content: str = ""
    source_name: str = ""
    source_url: str = ""
    relative_path: str = ""
    draft: dict[str, Any] = {}


class AgentTemplateBatchSaveReq(BaseModel):
    templates: list[AgentTemplateSaveReq] = []


class AgentTemplateBatchDeleteReq(BaseModel):
    template_ids: list[str] = []


class AgentTemplateDeduplicateReq(BaseModel):
    template_ids: list[str] = []
    source_type: str = "internal"
    provider_id: str = ""
    model_name: str = ""
    local_connector_id: str = ""
    temperature: float | None = None
    apply: bool = True


class AgentTemplateTranslateNamesReq(BaseModel):
    template_ids: list[str] = []
    source_type: str = "internal"
    provider_id: str = ""
    model_name: str = ""
    local_connector_id: str = ""
    force: bool = False


class EmployeeExternalSkillSuggestReq(BaseModel):
    name: str = ""
    description: str = ""
    goal: str = ""
    industry: str = ""
    source_filters: list[str] = []
    skills: list[str] = []
    rule_titles: list[str] = []
    rule_domains: list[str] = []
    style_hints: list[str] = []
    default_workflow: list[str] = []
    tool_usage_policy: str = ""


class EmployeeExternalRuleSuggestReq(BaseModel):
    name: str = ""
    description: str = ""
    goal: str = ""
    industry: str = ""
    source_filters: list[str] = []
    skills: list[str] = []
    rule_titles: list[str] = []
    rule_domains: list[str] = []
    style_hints: list[str] = []
    default_workflow: list[str] = []
    tool_usage_policy: str = ""


class EmployeeRuleDraftReq(BaseModel):
    title: str = ""
    domain: str = ""
    content: str = ""
    source_label: str = ""
    source_url: str = ""


class EmployeeDraftCreateReq(BaseModel):
    name: str
    description: str = ""
    goal: str = ""
    skills: list[str] = []
    selected_system_mcp_servers: list[str] = []
    rule_ids: list[str] = []
    rule_titles: list[str] = []
    rule_domains: list[str] = []
    rule_drafts: list[EmployeeRuleDraftReq] = []
    memory_scope: str = "project"
    memory_retention_days: int = 90
    tone: str = "professional"
    verbosity: str = "concise"
    language: str = "zh-CN"
    style_hints: list[str] = []
    default_workflow: list[str] = []
    tool_usage_policy: str = ""
    auto_evolve: bool = True
    evolve_threshold: float = 0.8
    mcp_enabled: bool = True
    feedback_upgrade_enabled: bool = False
    auto_create_missing_skills: bool = True
    auto_create_missing_rules: bool = True


class ProjectCreateReq(BaseModel):
    name: str
    description: str = ""
    type: Literal["image", "storyboard_video", "mixed"] = "mixed"
    mcp_instruction: str = ""
    workspace_path: str = ""
    ai_entry_file: str = ""
    mcp_enabled: bool = True
    feedback_upgrade_enabled: bool = True


class ProjectUpdateReq(BaseModel):
    name: str | None = None
    description: str | None = None
    type: Literal["image", "storyboard_video", "mixed"] | None = None
    mcp_instruction: str | None = None
    workspace_path: str | None = None
    ai_entry_file: str | None = None
    mcp_enabled: bool | None = None
    feedback_upgrade_enabled: bool | None = None


class ProjectMaterialAssetCreateReq(BaseModel):
    asset_type: Literal["image", "storyboard", "video", "audio"]
    title: str
    summary: str = ""
    source_message_id: str = ""
    source_chat_session_id: str = ""
    source_username: str = ""
    preview_url: str = ""
    content_url: str = ""
    mime_type: str = ""
    status: str = "ready"
    structured_content: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class ProjectMaterialAssetUpdateReq(BaseModel):
    title: str | None = None
    summary: str | None = None
    preview_url: str | None = None
    content_url: str | None = None
    mime_type: str | None = None
    status: str | None = None
    structured_content: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class StudioClipTransformReq(BaseModel):
    fit: Literal["cover", "contain", "stretch"] = "cover"
    align: Literal["center", "top", "bottom", "left", "right"] = "center"
    background: str = "#000000"


class StudioClipReq(BaseModel):
    id: str
    type: Literal["image", "video"] = "video"
    title: str = ""
    durationSeconds: float = Field(default=1, gt=0)
    startSeconds: float = Field(default=0, ge=0)
    asset_id: str = ""
    storage_path: str = ""
    content_url: str = ""
    preview_url: str = ""
    mime_type: str = ""
    original_filename: str = ""
    source_type: Literal["project_material", "studio_draft", "external_url", "ai_generated"] = "project_material"
    transform: StudioClipTransformReq = Field(default_factory=StudioClipTransformReq)
    meta: dict[str, Any] = Field(default_factory=dict)


class StudioTimelineSummaryReq(BaseModel):
    title: str = ""
    timelineDurationSeconds: float = Field(default=0, ge=0)
    clipCount: int = Field(default=0, ge=0)


class StudioTimelinePayloadReq(BaseModel):
    version: Literal["studio-export-v2"] = "studio-export-v2"
    summary: StudioTimelineSummaryReq = Field(default_factory=StudioTimelineSummaryReq)
    clips: list[StudioClipReq] = Field(default_factory=list)


class StudioAudioTrackReq(BaseModel):
    id: str
    kind: Literal["voice", "bgm", "sfx"]
    title: str = ""
    startSeconds: float = Field(default=0, ge=0)
    durationSeconds: float = Field(default=0, ge=0)
    volume: float = Field(default=1, ge=0, le=1.5)
    asset_id: str = ""
    storage_path: str = ""
    content_url: str = ""
    mime_type: str = ""
    original_filename: str = ""
    required: bool = False
    bind_clip_id: str = ""


class StudioAudioPayloadReq(BaseModel):
    version: Literal["studio-audio-v2"] = "studio-audio-v2"
    tracks: list[StudioAudioTrackReq] = Field(default_factory=list)


class ProjectStudioExportCreateReq(BaseModel):
    title: str = ""
    export_format: Literal["mp4-h264", "mp4-h265"] = "mp4-h264"
    export_resolution: Literal["720p", "1080p", "4K"] = "1080p"
    aspect_ratio: str = "16:9"
    timeline_payload: dict[str, Any] | StudioTimelinePayloadReq = Field(default_factory=dict)
    audio_payload: dict[str, Any] | StudioAudioPayloadReq = Field(default_factory=dict)


class ProjectStudioExportUpdateReq(BaseModel):
    status: str | None = None
    progress: int | None = None
    result_asset_id: str | None = None
    result_work_id: str | None = None
    cover_asset_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None


class ProjectStudioDraftSaveReq(BaseModel):
    job_id: str = ""
    title: str = ""
    snapshot: dict[str, Any] = {}


class ProjectStudioExtractionRunReq(BaseModel):
    provider_id: str = ""
    model_name: str = ""
    focus_kind: Literal["role", "scene", "prop"] = "role"
    duration: str = ""
    quality: str = ""
    script_content: str = ""
    styles: list[str] = Field(default_factory=list)
    chapters: list[dict[str, Any]] = Field(default_factory=list)


class ProjectStudioStoryboardGenerateReq(BaseModel):
    provider_id: str = ""
    model_name: str = ""
    chapter_id: str = ""
    chapter_title: str = ""
    chapter_content: str = ""
    duration: str = ""
    quality: str = ""
    sfx: bool = False
    styles: list[str] = Field(default_factory=list)
    elements: list[dict[str, Any]] = Field(default_factory=list)


class ProjectMemberAddReq(BaseModel):
    employee_id: str
    role: str = "member"
    enabled: bool = True


class ProjectUserAddReq(BaseModel):
    username: str
    role: str = "member"
    enabled: bool = True


class ProjectChatReq(BaseModel):
    message: str = ""
    message_id: str = ""
    assistant_message_id: str = ""
    chat_session_id: str = ""
    chat_mode: str = "system"
    local_connector_id: str = ""
    connector_workspace_path: str = ""
    connector_sandbox_mode: str | None = None
    connector_sandbox_mode_explicit: bool | None = None
    skill_resource_directory: str = ""
    employee_id: str = ""
    employee_ids: list[str] = []
    employee_coordination_mode: str | None = None
    history: list[dict] = []
    provider_id: str = ""
    model_name: str = ""
    temperature: float = 0.2
    max_tokens: int | None = None
    system_prompt: str | None = None
    attachment_names: list[str] = []
    images: list[str] = []
    enabled_project_tool_names: list[str] = []
    auto_use_tools: bool | None = None
    tool_priority: list[str] = []
    max_tool_calls_per_round: int | None = None
    max_loop_rounds: int | None = None
    max_tool_rounds: int | None = None
    repeated_tool_call_threshold: int | None = None
    tool_only_threshold: int | None = None
    tool_budget_strategy: str | None = None
    history_limit: int | None = None
    tool_timeout_sec: int | None = None
    tool_retry_count: int | None = None
    answer_style: str | None = None
    prefer_conclusion_first: bool | None = None


class ProjectChatHistoryTruncateReq(BaseModel):
    chat_session_id: str = ""
    message_id: str = ""
    system_prompt: str | None = None


class ProjectChatSettingsUpdateReq(BaseModel):
    settings: dict[str, Any]


class DictionaryOptionReq(BaseModel):
    id: str
    label: str = ""
    description: str = ""
    chat_parameter_mode: str = ""


class DictionaryUpdateReq(BaseModel):
    label: str = ""
    description: str = ""
    default_value: str = ""
    options: list[DictionaryOptionReq] = []


class DictionaryCreateReq(DictionaryUpdateReq):
    key: str


class ExternalMcpModuleCreateReq(BaseModel):
    name: str
    description: str = ""
    endpoint_http: str = ""
    endpoint_sse: str = ""
    auth_type: str = "none"
    project_id: str = ""
    enabled: bool = True


class ExternalMcpModuleUpdateReq(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint_http: str | None = None
    endpoint_sse: str | None = None
    auth_type: str | None = None
    project_id: str | None = None
    enabled: bool | None = None


class ExternalMcpModuleTestReq(BaseModel):
    endpoint_http: str = ""
    endpoint_sse: str = ""
    timeout_sec: int = 8


class WorkspaceDirectoryPickReq(BaseModel):
    initial_path: str = ""
    title: str = "选择工作区目录"


class WorkspaceFilePickReq(BaseModel):
    initial_path: str = ""
    title: str = "选择文件"


class ProjectAiEntryFileUpdateReq(BaseModel):
    ai_entry_file: str = ""


class LocalConnectorPairCodeCreateReq(BaseModel):
    note: str = ""
    ttl_minutes: int = 10
    permanent: bool = False


class LocalConnectorPairActivateReq(BaseModel):
    pair_code: str
    connector_name: str = ""
    device_fingerprint: str = ""
    device_label: str = ""
    platform: str = ""
    app_version: str = ""
    advertised_url: str = ""
    manifest: dict[str, Any] = {}
    health: dict[str, Any] = {}


class LocalConnectorHeartbeatReq(BaseModel):
    advertised_url: str = ""
    manifest: dict[str, Any] = {}
    health: dict[str, Any] = {}
    status: str = "online"
    last_error: str = ""


class LocalConnectorWorkspacePickConsumeReq(BaseModel):
    session_id: str
    session_token: str


class LocalConnectorLlmSharingUpdateReq(BaseModel):
    llm_shared_with_usernames: list[str] = []
    llm_shared_with_roles: list[str] = []


class SystemConfigUpdateReq(BaseModel):
    enable_project_manual_generation: bool | None = None
    enable_employee_manual_generation: bool | None = None
    enable_user_register: bool | None = None
    chat_upload_max_limit: int | None = None
    chat_max_tokens: int | None = None
    default_chat_system_prompt: str | None = None
    employee_auto_rule_generation_enabled: bool | None = None
    employee_auto_rule_generation_source_filters: list[str] | None = None
    employee_auto_rule_generation_max_count: int | None = None
    employee_auto_rule_generation_prompt: str | None = None
    employee_external_skill_sites: list[dict[str, Any]] | None = None
    skill_registry_sources: dict[str, Any] | None = None
    dictionaries: dict[str, Any] | None = None
    mcp_config: dict[str, Any] | None = None


class ReviewReq(BaseModel):
    reviewed_by: str
    action: str
    edits: str = ""


class FeedbackBugCreateReq(BaseModel):
    employee_id: str
    title: str
    symptom: str
    expected: str
    category: str = "general"
    severity: str = "medium"
    session_id: str = ""
    rule_id: str = ""
    reporter: str = ""
    source_context: dict = {}


class FeedbackCandidateReviewReq(BaseModel):
    reviewed_by: str
    action: str
    comment: str = ""
    edited_content: str = ""
    edited_executable_content: str = ""


class FeedbackCandidatePublishReq(BaseModel):
    published_by: str = ""
    comment: str = ""


class FeedbackCandidateRollbackReq(BaseModel):
    rolled_back_by: str = ""
    comment: str = ""


class FeedbackManualCandidateCreateReq(BaseModel):
    employee_id: str
    category: str = "general"
    proposed_rule_content: str
    executable_rule_content: str = ""
    target_rule_id: str = ""
    risk_level: str = "medium"
    confidence: float = 0.8
    feedback_ids: list[str] = []
    comment: str = ""


class FeedbackBugBatchDeleteReq(BaseModel):
    feedback_ids: list[str]
    employee_id: str = ""


class FeedbackAnalyzeReq(BaseModel):
    provider_id: str = ""
    model_name: str = ""
    temperature: float | None = None


class FeedbackBatchAnalyzeReq(BaseModel):
    feedback_ids: list[str]
    target_rule_id: str
    provider_id: str = ""
    model_name: str = ""
    temperature: float | None = None


class FeedbackReflectionConfigUpdateReq(BaseModel):
    employee_id: str
    provider_id: str
    model_name: str = ""
    temperature: float = 0.2


class FeedbackProjectConfigUpdateReq(BaseModel):
    enabled: bool


class SkillInstallReq(BaseModel):
    skill_id: str
    enabled_tools: list[str] = []


class SkillResourceResolveReq(BaseModel):
    input: str


class SkillResourceInstallReq(BaseModel):
    version: str
    install_dir: str = ""
    import_to_library: bool = True


class RuleUsageReq(BaseModel):
    adopted: bool


class CompressReq(BaseModel):
    keep_top: int = 50


class MemoryBatchDeleteReq(BaseModel):
    memory_ids: list[str]
    employee_id: str = ""


# ── Skill ──

class SkillCreateReq(BaseModel):
    source_dir: str
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    share_scope: str = "private"
    shared_with_usernames: list[str] = []
    mcp_service: str = ""
    tags: list[str] = []
    mcp_enabled: bool = False


class SkillUpdateReq(BaseModel):
    name: str | None = None
    version: str | None = None
    description: str | None = None
    share_scope: str | None = None
    shared_with_usernames: list[str] | None = None
    mcp_service: str | None = None
    tags: list[str] | None = None
    mcp_enabled: bool | None = None


# ── Rule ──

class RuleCreateReq(BaseModel):
    domain: str
    title: str
    content: str
    share_scope: str = "private"
    shared_with_usernames: list[str] = []
    severity: str = "recommended"
    risk_domain: str = "low"
    mcp_enabled: bool = False
    mcp_service: str = ""
    bound_employees: list[str] = []


class RuleUpdateReq(BaseModel):
    domain: str | None = None
    title: str | None = None
    content: str | None = None
    share_scope: str | None = None
    shared_with_usernames: list[str] | None = None
    severity: str | None = None
    risk_domain: str | None = None
    mcp_enabled: bool | None = None
    mcp_service: str | None = None
    bound_employees: list[str] | None = None


# ── Usage ──

class CreateApiKeyReq(BaseModel):
    developer_name: str


# ── LLM Provider ──

class LlmProviderModelConfigReq(BaseModel):
    name: str
    model_type: str = "text_generation"


class LlmProviderCreateReq(BaseModel):
    name: str
    provider_type: str = "openai-compatible"
    base_url: str
    api_key: str = ""
    models: list[str] = []
    model_configs: list[LlmProviderModelConfigReq] = []
    default_model: str = ""
    enabled: bool = True
    extra_headers: dict = {}
    shared_usernames: list[str] = []


class LlmProviderUpdateReq(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    models: list[str] | None = None
    model_configs: list[LlmProviderModelConfigReq] | None = None
    default_model: str | None = None
    enabled: bool | None = None
    extra_headers: dict | None = None
    shared_usernames: list[str] | None = None


class LlmProviderTestReq(BaseModel):
    model_name: str = ""


# ── Persona ──

class PersonaCreateReq(BaseModel):
    name: str
    tone: str = "professional"
    verbosity: str = "concise"
    language: str = "zh-CN"
    behaviors: list[str] = []
    style_hints: list[str] = []
    decision_policy: dict | None = None
    drift_control: dict | None = None


class PersonaUpdateReq(BaseModel):
    name: str | None = None
    tone: str | None = None
    verbosity: str | None = None
    language: str | None = None
    behaviors: list[str] | None = None
    style_hints: list[str] | None = None
    decision_policy: dict | None = None
    drift_control: dict | None = None
