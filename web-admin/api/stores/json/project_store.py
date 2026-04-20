"""项目存储层"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProjectConfig:
    id: str
    name: str
    description: str = ""
    created_by: str = ""
    type: str = "mixed"
    ui_rule_ids: list[str] = field(default_factory=list)
    experience_rule_ids: list[str] = field(default_factory=list)
    workflow_skill_ids: list[str] = field(default_factory=list)
    default_workflow_skill_id: str = ""
    mcp_instruction: str = ""
    workspace_path: str = ""
    ai_entry_file: str = ""
    mcp_enabled: bool = True
    feedback_upgrade_enabled: bool = True
    chat_settings: dict[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class ProjectMember:
    project_id: str
    employee_id: str
    role: str = "member"
    enabled: bool = True
    joined_at: str = field(default_factory=_now_iso)


@dataclass
class ProjectUserMember:
    project_id: str
    username: str
    role: str = "member"
    enabled: bool = True
    joined_at: str = field(default_factory=_now_iso)


class ProjectStore:
    def __init__(self, data_dir: Path) -> None:
        self._projects_dir = data_dir / "projects"
        self._projects_dir.mkdir(parents=True, exist_ok=True)
        self._members_dir = data_dir / "project-members"
        self._members_dir.mkdir(parents=True, exist_ok=True)
        self._user_members_dir = data_dir / "project-user-members"
        self._user_members_dir.mkdir(parents=True, exist_ok=True)

    def _project_path(self, project_id: str) -> Path:
        return self._projects_dir / f"{project_id}.json"

    def _members_path(self, project_id: str) -> Path:
        return self._members_dir / f"{project_id}.json"

    def _user_members_path(self, project_id: str) -> Path:
        return self._user_members_dir / f"{project_id}.json"

    def save(self, project: ProjectConfig) -> None:
        self._project_path(project.id).write_text(
            json.dumps(asdict(project), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, project_id: str) -> ProjectConfig | None:
        path = self._project_path(project_id)
        if not path.exists():
            return None
        return ProjectConfig(**json.loads(path.read_text(encoding="utf-8")))

    def list_all(self) -> list[ProjectConfig]:
        items: list[ProjectConfig] = []
        for path in sorted(self._projects_dir.glob("*.json")):
            items.append(ProjectConfig(**json.loads(path.read_text(encoding="utf-8"))))
        return items

    def delete(self, project_id: str) -> bool:
        path = self._project_path(project_id)
        if not path.exists():
            return False
        path.unlink()
        members_path = self._members_path(project_id)
        if members_path.exists():
            members_path.unlink()
        user_members_path = self._user_members_path(project_id)
        if user_members_path.exists():
            user_members_path.unlink()
        return True

    def new_id(self) -> str:
        return f"proj-{uuid.uuid4().hex[:8]}"

    def list_members(self, project_id: str) -> list[ProjectMember]:
        path = self._members_path(project_id)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [ProjectMember(**item) for item in data]

    def get_member(self, project_id: str, employee_id: str) -> ProjectMember | None:
        for member in self.list_members(project_id):
            if member.employee_id == employee_id:
                return member
        return None

    def upsert_member(self, member: ProjectMember) -> None:
        items = self.list_members(member.project_id)
        updated = [m for m in items if m.employee_id != member.employee_id]
        updated.append(member)
        self._members_path(member.project_id).write_text(
            json.dumps([asdict(item) for item in updated], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def remove_member(self, project_id: str, employee_id: str) -> bool:
        items = self.list_members(project_id)
        updated = [item for item in items if item.employee_id != employee_id]
        if len(updated) == len(items):
            return False
        self._members_path(project_id).write_text(
            json.dumps([asdict(item) for item in updated], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True

    def remove_employee_from_all_projects(self, employee_id: str) -> list[str]:
        removed_project_ids: list[str] = []
        for project in self.list_all():
            if self.remove_member(project.id, employee_id):
                removed_project_ids.append(project.id)
        return removed_project_ids

    def list_user_members(self, project_id: str) -> list[ProjectUserMember]:
        path = self._user_members_path(project_id)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [ProjectUserMember(**item) for item in data]

    @staticmethod
    def _normalize_project_ids(project_ids: list[str] | tuple[str, ...] | set[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in project_ids:
            project_id = str(item or "").strip()
            if not project_id or project_id in seen:
                continue
            seen.add(project_id)
            normalized.append(project_id)
        return normalized

    def list_user_memberships(
        self,
        username: str,
        project_ids: list[str] | tuple[str, ...] | set[str],
    ) -> dict[str, ProjectUserMember]:
        normalized_username = str(username or "").strip()
        if not normalized_username:
            return {}
        memberships: dict[str, ProjectUserMember] = {}
        for project_id in self._normalize_project_ids(project_ids):
            member = self.get_user_member(project_id, normalized_username)
            if member is not None:
                memberships[project_id] = member
        return memberships

    def list_member_counts(
        self,
        project_ids: list[str] | tuple[str, ...] | set[str],
    ) -> dict[str, int]:
        return {
            project_id: len(self.list_members(project_id))
            for project_id in self._normalize_project_ids(project_ids)
        }

    def list_user_member_counts(
        self,
        project_ids: list[str] | tuple[str, ...] | set[str],
    ) -> dict[str, int]:
        return {
            project_id: len(self.list_user_members(project_id))
            for project_id in self._normalize_project_ids(project_ids)
        }

    def list_owner_usernames(
        self,
        project_ids: list[str] | tuple[str, ...] | set[str],
    ) -> dict[str, str]:
        owners: dict[str, str] = {}
        for project_id in self._normalize_project_ids(project_ids):
            owner_members = [
                item
                for item in self.list_user_members(project_id)
                if bool(getattr(item, "enabled", True))
                and str(getattr(item, "role", "") or "").strip().lower() == "owner"
                and str(getattr(item, "username", "") or "").strip()
            ]
            owner_members.sort(key=lambda item: str(getattr(item, "joined_at", "") or ""))
            if owner_members:
                owners[project_id] = str(getattr(owner_members[0], "username", "") or "").strip()
        return owners

    def get_user_member(self, project_id: str, username: str) -> ProjectUserMember | None:
        for member in self.list_user_members(project_id):
            if member.username == username:
                return member
        return None

    def upsert_user_member(self, member: ProjectUserMember) -> None:
        items = self.list_user_members(member.project_id)
        updated = [m for m in items if m.username != member.username]
        updated.append(member)
        self._user_members_path(member.project_id).write_text(
            json.dumps([asdict(item) for item in updated], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def remove_user_member(self, project_id: str, username: str) -> bool:
        items = self.list_user_members(project_id)
        updated = [item for item in items if item.username != username]
        if len(updated) == len(items):
            return False
        self._user_members_path(project_id).write_text(
            json.dumps([asdict(item) for item in updated], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True

    def remove_user_from_all_projects(self, username: str) -> list[str]:
        removed_project_ids: list[str] = []
        for project in self.list_all():
            if self.remove_user_member(project.id, username):
                removed_project_ids.append(project.id)
        return removed_project_ids
