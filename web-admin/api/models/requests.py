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


class EmployeeUpdateReq(BaseModel):
    name: str | None = None
    description: str | None = None
    skills: list[str] | None = None
    rule_domains: list[str] | None = None
    tone: str | None = None
    verbosity: str | None = None
    style_hints: list[str] | None = None
    auto_evolve: bool | None = None
    evolve_threshold: float | None = None


class ReviewReq(BaseModel):
    reviewed_by: str
    action: str
    edits: str = ""


class SkillInstallReq(BaseModel):
    skill_id: str
    enabled_tools: list[str] = []


class RuleUsageReq(BaseModel):
    adopted: bool


class CompressReq(BaseModel):
    keep_top: int = 50


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
