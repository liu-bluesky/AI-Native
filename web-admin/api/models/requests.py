"""Pydantic 请求模型"""

from __future__ import annotations

from pydantic import BaseModel


class InitSetupReq(BaseModel):
    username: str
    password: str


class LoginReq(BaseModel):
    username: str
    password: str


class EmployeeCreateReq(BaseModel):
    name: str
    description: str = ""
    skills: list[str] = []
    rule_domains: list[str] = []
    memory_scope: str = "project"
    memory_retention_days: int = 90
    tone: str = "professional"
    verbosity: str = "concise"
    language: str = "zh-CN"
    style_hints: list[str] = []
    auto_evolve: bool = True
    evolve_threshold: float = 0.8
    mcp_enabled: bool = True
    feedback_upgrade_enabled: bool = False


class EmployeeUpdateReq(BaseModel):
    name: str | None = None
    description: str | None = None
    skills: list[str] | None = None
    rule_domains: list[str] | None = None
    memory_scope: str | None = None
    memory_retention_days: int | None = None
    tone: str | None = None
    verbosity: str | None = None
    language: str | None = None
    style_hints: list[str] | None = None
    auto_evolve: bool | None = None
    evolve_threshold: float | None = None
    mcp_enabled: bool | None = None
    feedback_upgrade_enabled: bool | None = None


class ProjectCreateReq(BaseModel):
    name: str
    description: str = ""
    mcp_enabled: bool = True
    feedback_upgrade_enabled: bool = True


class ProjectUpdateReq(BaseModel):
    name: str | None = None
    description: str | None = None
    mcp_enabled: bool | None = None
    feedback_upgrade_enabled: bool | None = None


class ProjectMemberAddReq(BaseModel):
    employee_id: str
    role: str = "member"
    enabled: bool = True


class SystemConfigUpdateReq(BaseModel):
    enable_project_manual_generation: bool | None = None
    enable_employee_manual_generation: bool | None = None


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
    mcp_service: str = ""
    tags: list[str] = []
    mcp_enabled: bool = False


class SkillUpdateReq(BaseModel):
    name: str | None = None
    version: str | None = None
    description: str | None = None
    mcp_service: str | None = None
    tags: list[str] | None = None
    mcp_enabled: bool | None = None


# ── Rule ──

class RuleCreateReq(BaseModel):
    domain: str
    title: str
    content: str
    severity: str = "recommended"
    risk_domain: str = "low"
    mcp_enabled: bool = False
    mcp_service: str = ""


class RuleUpdateReq(BaseModel):
    domain: str | None = None
    title: str | None = None
    content: str | None = None
    severity: str | None = None
    risk_domain: str | None = None
    mcp_enabled: bool | None = None
    mcp_service: str | None = None


# ── Usage ──

class CreateApiKeyReq(BaseModel):
    developer_name: str
    created_by: str = ""


# ── LLM Provider ──

class LlmProviderCreateReq(BaseModel):
    name: str
    provider_type: str = "openai-compatible"
    base_url: str
    api_key: str = ""
    models: list[str] = []
    default_model: str = ""
    enabled: bool = True
    extra_headers: dict = {}


class LlmProviderUpdateReq(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    models: list[str] | None = None
    default_model: str | None = None
    enabled: bool | None = None
    extra_headers: dict | None = None


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
