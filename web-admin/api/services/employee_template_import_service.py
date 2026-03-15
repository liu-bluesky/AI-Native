"""Import external Markdown agent templates and map them into employee drafts."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MARKDOWN_SUFFIXES = {".md", ".markdown"}
_DEFAULT_LIMIT = 40
_MAX_LIMIT = 80
_COMMON_CATEGORY_DOMAINS = {
    "engineering": "engineering",
    "design": "design",
    "marketing": "marketing",
    "product": "product",
    "sales": "sales",
    "testing": "testing",
    "operations": "operations",
    "support": "support",
    "research": "research",
    "data": "data",
    "security": "security",
}
_IGNORE_NAMES = {
    "readme.md",
    "license.md",
    "changelog.md",
    "contributing.md",
    "code_of_conduct.md",
    "pull_request_template.md",
    "pull_request_template.markdown",
    "issue_template.md",
    "issue_template.markdown",
}
_IGNORE_DIRS = {
    "node_modules",
    ".git",
    ".github",
    "dist",
    "build",
    "docs",
    "doc",
    "__tests__",
    "test",
    "tests",
}


def _normalize_text_value(value: Any, *, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _normalize_text_list(
    values: list[str] | None,
    *,
    limit: int = 20,
    item_limit: int = 240,
) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values or []:
        text = _normalize_text_value(item, limit=item_limit)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _normalize_match_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_limit(value: Any) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = _DEFAULT_LIMIT
    return max(1, min(numeric, _MAX_LIMIT))


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    stripped = text.lstrip()
    if not stripped.startswith("---\n"):
        return {}, text
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    data: dict[str, str] = {}
    closing_index = -1
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = idx
            break
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        data[key.strip().lower()] = raw_value.strip().strip("\"'")
    if closing_index < 0:
        return {}, text
    body = "\n".join(lines[closing_index + 1 :]).lstrip()
    return data, body


def _extract_markdown_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _extract_intro_description(text: str) -> str:
    lines = text.splitlines()
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not stripped:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        current.append(stripped.lstrip("> ").strip())
    if current:
        paragraphs.append(" ".join(current).strip())
    for paragraph in paragraphs:
        if paragraph and not paragraph.lower().startswith("tags:"):
            return paragraph[:600]
    return ""


def _extract_sections(text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        heading_match = re.match(r"^(#{2,6})\s+(.*)$", stripped)
        if heading_match:
            if current_title or current_lines:
                sections.append(
                    {
                        "title": current_title,
                        "content": "\n".join(current_lines).strip(),
                    }
                )
            current_title = heading_match.group(2).strip()
            current_lines = []
            continue
        current_lines.append(line.rstrip())
    if current_title or current_lines:
        sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
    return sections


def _extract_list_items(text: str, *, limit: int = 8) -> list[str]:
    items: list[str] = []
    ordered = 1
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        bullet = re.match(r"^[-*+]\s+(.*)$", stripped)
        ordered_match = re.match(rf"^{ordered}[.)]\s+(.*)$", stripped)
        if bullet:
            items.append(bullet.group(1).strip())
        elif ordered_match:
            items.append(ordered_match.group(1).strip())
            ordered += 1
        if len(items) >= limit:
            break
    return _normalize_text_list(items, limit=limit, item_limit=240)


def _extract_sentences(text: str, *, limit: int = 6) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", normalized)
    return _normalize_text_list(parts, limit=limit, item_limit=240)


def _find_best_section(sections: list[dict[str, str]], keywords: list[str]) -> dict[str, str] | None:
    normalized_keywords = [_normalize_match_key(item) for item in keywords if _normalize_match_key(item)]
    if not normalized_keywords:
        return None
    best: dict[str, str] | None = None
    best_score = 0
    for section in sections:
        title = _normalize_match_key(section.get("title"))
        content = _normalize_match_key(section.get("content"))
        score = 0
        for keyword in normalized_keywords:
            if keyword and keyword in title:
                score += 3
            if keyword and keyword in content:
                score += 1
        if score > best_score:
            best = section
            best_score = score
    return best


def _derive_rule_domain(path: Path) -> str:
    parts = [_normalize_match_key(item) for item in path.parts[:-1]]
    for item in parts:
        domain = _COMMON_CATEGORY_DOMAINS.get(item)
        if domain:
            return domain
    return ""


def _guess_tone(text: str) -> str:
    lower = _normalize_match_key(text)
    if any(token in lower for token in ("friendly", "warm", "empathetic", "supportive")):
        return "friendly"
    if any(token in lower for token in ("strict", "precise", "critical", "rigorous")):
        return "serious"
    return "professional"


def _guess_verbosity(text: str) -> str:
    lower = _normalize_match_key(text)
    if any(token in lower for token in ("detailed", "thorough", "comprehensive", "step-by-step")):
        return "detailed"
    if any(token in lower for token in ("brief", "concise", "short", "direct")):
        return "concise"
    return "concise"


def _guess_language(text: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", str(text or "")):
        return "zh-CN"
    return "en-US"


def _build_tool_usage_policy(section: dict[str, str] | None) -> str:
    if not section:
        return ""
    list_items = _extract_list_items(section.get("content", ""), limit=8)
    if list_items:
        return "\n".join(f"- {item}" for item in list_items)[:2000]
    sentences = _extract_sentences(section.get("content", ""), limit=5)
    return "\n".join(f"- {item}" for item in sentences)[:2000]


def _build_rule_drafts(
    *,
    name: str,
    domain: str,
    policy_section: dict[str, str] | None,
    source_url: str,
) -> list[dict[str, str]]:
    policy_content = _build_tool_usage_policy(policy_section)
    if not policy_content:
        return []
    title = f"{name} 执行约束"
    return [
        {
            "title": title[:160],
            "domain": domain or "通用",
            "content": policy_content[:8000],
            "source_label": "agency-agent-template",
            "source_url": source_url[:400],
        }
    ]


def _build_employee_draft(
    *,
    relative_path: Path,
    source_name: str,
    source_url: str,
    text: str,
) -> dict[str, Any]:
    frontmatter, body = _parse_frontmatter(text)
    title = (
        _normalize_text_value(frontmatter.get("title"), limit=120)
        or _normalize_text_value(frontmatter.get("name"), limit=120)
        or _normalize_text_value(_extract_markdown_title(body), limit=120)
        or relative_path.stem.replace("-", " ").replace("_", " ").strip().title()
    )
    description = (
        _normalize_text_value(frontmatter.get("description"), limit=2000)
        or _normalize_text_value(_extract_intro_description(body), limit=2000)
        or f"Imported from {relative_path.as_posix()}"
    )
    sections = _extract_sections(body)
    goal_section = _find_best_section(sections, ["mission", "goal", "objective", "purpose"])
    workflow_section = _find_best_section(
        sections,
        ["workflow", "process", "approach", "execution", "methodology", "how you work"],
    )
    style_section = _find_best_section(
        sections,
        ["communication style", "tone", "voice", "personality", "working style", "style"],
    )
    policy_section = _find_best_section(
        sections,
        ["constraints", "guardrails", "rules", "non-goals", "boundaries", "limitations"],
    )
    domain = _derive_rule_domain(relative_path)
    combined_text = "\n".join(
        [
            title,
            description,
            goal_section.get("content", "") if goal_section else "",
            style_section.get("content", "") if style_section else "",
        ]
    )
    style_hints = _extract_list_items(style_section.get("content", ""), limit=6) if style_section else []
    if not style_hints and style_section:
        style_hints = _extract_sentences(style_section.get("content", ""), limit=4)
    workflow = _extract_list_items(workflow_section.get("content", ""), limit=8) if workflow_section else []
    if not workflow and workflow_section:
        workflow = _extract_sentences(workflow_section.get("content", ""), limit=5)
    goal = (
        _normalize_text_value(goal_section.get("content"), limit=2000)
        if goal_section
        else ""
    )
    if goal:
        goal = (_extract_list_items(goal, limit=3) or _extract_sentences(goal, limit=2) or [goal])[0]
    if not goal:
        goal = description[:300]
    return {
        "name": title,
        "description": description,
        "goal": goal,
        "skills": [],
        "selected_system_mcp_servers": [],
        "rule_ids": [],
        "rule_titles": [],
        "rule_domains": [domain] if domain else [],
        "rule_drafts": _build_rule_drafts(
            name=title,
            domain=domain,
            policy_section=policy_section,
            source_url=source_url,
        ),
        "memory_scope": "project",
        "memory_retention_days": 90,
        "tone": _guess_tone(combined_text),
        "verbosity": _guess_verbosity(combined_text),
        "language": _guess_language(body),
        "style_hints": style_hints,
        "default_workflow": workflow,
        "tool_usage_policy": _build_tool_usage_policy(policy_section),
        "auto_evolve": True,
        "evolve_threshold": 0.8,
        "mcp_enabled": True,
        "feedback_upgrade_enabled": False,
        "template_source_name": source_name,
        "template_source_url": source_url,
        "template_relative_path": relative_path.as_posix(),
    }


def _is_candidate_template(path: Path) -> bool:
    if path.suffix.lower() not in _MARKDOWN_SUFFIXES:
        return False
    if path.name.lower() in _IGNORE_NAMES:
        return False
    parts = {_normalize_match_key(item) for item in path.parts}
    if parts & _IGNORE_DIRS:
        return False
    return True


def _resolve_local_root(source: str, subdirectory: str) -> tuple[Path, str]:
    raw = _normalize_text_value(source, limit=1000)
    if not raw:
        raise HTTPException(400, "source is required")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        root = (PROJECT_ROOT / root).resolve()
    else:
        root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(400, f"Directory not found: {root}")
    resolved = root
    nested = _normalize_text_value(subdirectory, limit=400)
    if nested:
        resolved = (root / nested).resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise HTTPException(400, f"Subdirectory not found: {resolved}")
    return resolved, root.as_posix()


def _split_tree_subpath(parts: list[str]) -> tuple[str, str]:
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    best_branch = ""
    best_subdir = ""
    for idx in range(1, len(parts) + 1):
        branch_candidate = "/".join(parts[:idx]).strip("/")
        subdir_candidate = "/".join(parts[idx:]).strip("/")
        if not branch_candidate:
            continue
        best_branch = branch_candidate
        best_subdir = subdir_candidate
        if subdir_candidate:
            break
    return best_branch, best_subdir


def _parse_supported_git_tree_url(source: str) -> dict[str, str] | None:
    raw = _normalize_text_value(source, limit=1000)
    if not raw or "://" not in raw:
        return None
    parsed = urlparse(raw)
    host = _normalize_match_key(parsed.netloc)
    if host not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if len(parts) == 2:
        return {
            "clone_url": f"{parsed.scheme}://{parsed.netloc}/{owner}/{repo}",
            "branch": "",
            "subdirectory": "",
        }
    if len(parts) >= 4 and parts[2] == "tree":
        branch, nested = _split_tree_subpath(parts[3:])
        return {
            "clone_url": f"{parsed.scheme}://{parsed.netloc}/{owner}/{repo}",
            "branch": branch,
            "subdirectory": nested,
        }
    return None


def _normalize_git_source_input(
    source: str,
    branch: str,
    subdirectory: str,
) -> tuple[str, str, str]:
    parsed = _parse_supported_git_tree_url(source)
    if parsed is None:
        return (
            _normalize_text_value(source, limit=1000),
            _normalize_text_value(branch, limit=120),
            _normalize_text_value(subdirectory, limit=400),
        )
    resolved_branch = _normalize_text_value(branch, limit=120) or parsed["branch"]
    resolved_subdirectory = _normalize_text_value(subdirectory, limit=400) or parsed["subdirectory"]
    return parsed["clone_url"], resolved_branch, resolved_subdirectory


def _clone_git_repo(source: str, branch: str) -> tuple[Path, str]:
    url = _normalize_text_value(source, limit=1000)
    if not url:
        raise HTTPException(400, "source is required")
    temp_root = Path(tempfile.mkdtemp(prefix="employee-agent-import-"))
    target = temp_root / "repo"
    cmd = ["git", "clone", "--depth", "1"]
    branch_name = _normalize_text_value(branch, limit=120)
    if branch_name:
        cmd.extend(["--branch", branch_name])
    cmd.extend([url, str(target)])
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise HTTPException(504, f"Clone timed out: {url}") from exc
    except FileNotFoundError as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise HTTPException(500, "git command not found on server") from exc
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise HTTPException(400, f"Failed to clone repository: {message[:400]}") from exc
    return target, url


def _resolve_source_root(
    *,
    source_type: str,
    source: str,
    subdirectory: str,
    branch: str,
) -> tuple[Path, str, Path | None]:
    normalized_type = _normalize_match_key(source_type) or "git"
    if normalized_type == "local":
        resolved, source_name = _resolve_local_root(source, subdirectory)
        return resolved, source_name, None
    if normalized_type == "git":
        normalized_source, normalized_branch, normalized_subdirectory = _normalize_git_source_input(
            source,
            branch,
            subdirectory,
        )
        repo_root, source_name = _clone_git_repo(normalized_source, normalized_branch)
        resolved = repo_root
        nested = normalized_subdirectory
        if nested:
            resolved = (repo_root / nested).resolve()
            if not resolved.exists() or not resolved.is_dir():
                shutil.rmtree(repo_root.parent, ignore_errors=True)
                raise HTTPException(400, f"Subdirectory not found in repository: {nested}")
        return resolved, source_name, repo_root.parent
    raise HTTPException(400, f"Unsupported source_type: {source_type}")


def import_agent_templates(
    *,
    source_type: str,
    source: str,
    subdirectory: str = "",
    branch: str = "",
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    resolved_root, source_name, cleanup_root = _resolve_source_root(
        source_type=source_type,
        source=source,
        subdirectory=subdirectory,
        branch=branch,
    )
    try:
        files = [
            path
            for path in sorted(resolved_root.rglob("*"))
            if path.is_file() and _is_candidate_template(path.relative_to(resolved_root))
        ]
        if not files:
            raise HTTPException(404, "No Markdown agent templates found in source")
        results: list[dict[str, Any]] = []
        for file_path in files[: _normalize_limit(limit)]:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                continue
            relative_path = file_path.relative_to(resolved_root)
            draft = _build_employee_draft(
                relative_path=relative_path,
                source_name=source_name,
                source_url=source_name,
                text=text,
            )
            results.append(
                {
                    "id": f"{relative_path.as_posix()}::{draft['name']}",
                    "name": draft["name"],
                    "description": draft["description"],
                    "content": text,
                    "relative_path": relative_path.as_posix(),
                    "source_name": source_name,
                    "source_url": source_name,
                    "draft": draft,
                    }
                )
        if not results:
            raise HTTPException(404, "No valid Markdown agent templates found in source")
        return results
    finally:
        if cleanup_root is not None:
            shutil.rmtree(cleanup_root, ignore_errors=True)
