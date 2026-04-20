# Query MCP Workflow

## Purpose

Use this skill when a project relies on Unified Query MCP for requirement handling, task recovery, task tree updates, and verifiable delivery.

This skill is an instruction asset, not a CLI wrapper. It tells the AI how to use existing MCP tools and system APIs consistently. It does not replace backend validation.

## Required Workflow

1. Read the Unified Query MCP usage guide before execution.
2. For Codex-style coding clients, also read the Codex client profile.
3. Search IDs with the user's original request text, not a shorthand label.
4. Read project manual content before project-specific execution.
5. For implementation tasks, run task analysis, relevant context resolution, and execution planning before editing code.
6. If a task spans multiple turns, persist and reuse the same chat session and work session.
7. Before continuing after interruption, recover state in this order: bind project context, resume work session, summarize checkpoint.
8. Do not treat natural language progress as task closure. Completion requires tool-visible status and verification where the host exposes those tools.

## Three-Layer Contract

The skill layer tells the AI what to do.

The tool/script layer should package repeated steps and reduce prompt-dependent behavior.

The backend validation layer must enforce task ownership, session continuity, allowed transitions, and verification requirements.

## Expected User Feedback

When a recoverable task exists, tell the user it can continue and name the current phase or next action.

When only orphaned local or MCP state exists, tell the user the system found historical state but cannot guarantee it belongs to the current active task unless the project/session binding is restored.

When task tree tools are unavailable in the current host, say that task-tree closure is not complete instead of claiming completion.

## Boundaries

Do not ask the user to download this skill into every project. It should be enabled from the system skill library and referenced through project or employee skill indexes.

Do not create or rely on ad-hoc legacy session files. Use the canonical query-mcp session state paths or the backend state service.
