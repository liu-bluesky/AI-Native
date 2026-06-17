---
name: project-deploy-artifact
description: Use when a project chat request needs to package code, push a deploy artifact to the project deploy artifact module, or trigger artifact-based auto deployment.
---

# Project Deploy Artifact

Use this skill for project chat requests such as “打包部署”, “发布测试环境”, “推送部署产物”, “指定压缩包部署”, or “执行部署产物 AI 自动部署”.

## Responsibility Boundary

- Project chat external agent: may run explicitly authorized local build/package commands through the desktop Runner when a package must be generated on the user's computer.
- Client AI: builds or reads the requested package, then pushes the package to the server-side project deploy artifact module through MCP/project API capability. For client-local files, use the `scripts/push_local_artifact.py` bridge or read the file and pass `artifact_content_base64` to `push_project_deploy_artifact`; never pass a Windows/macOS client path as `artifact_path`.
- MCP/server: stores the deploy artifact record and file, owns deployment settings, and runs artifact-based auto deployment when requested.
- Deploy artifact AI: deploys from the server-side artifact and project deploy settings; it must not rely on client-local FTP files, local credentials, historical CI config, or ad hoc transfer steps.
- UI/manual operation: users may upload files from the deploy artifact list when local command execution is unavailable or the artifact is already on another computer.

## Required Flow

1. If packaging requires a local command, confirm project chat has a selected external agent running in the desktop Runner for the target computer and workspace.
2. Before local packaging, state the exact command, working directory, expected output artifact, affected local files, and recoverability.
3. For local packaging commands, obtain explicit user authorization before running the command.
4. Build the package or use the user-specified zip/file/directory without scanning historical release config, CI files, local credentials, remote scripts, or environment variables.
5. Resolve `project_id` from the current project context before upload. If the entry prompt, URL default context, MCP binding, or rendered CLI prompt provides a default project ID, use it directly; do not ask the user to repeat `project_id` after they already confirmed deployment.
6. Push the resulting artifact to the server-side deploy artifact module. If the artifact path is local to the current Codex/Runner host, prefer `scripts/push_local_artifact.py --project-id <project_id> --file <path> --profile <profile> --component <component>` because it reads the file locally and uses the multipart upload route; the script triggers deployment by default and `--no-auto-deploy` means upload only. If calling MCP directly, include `profile`, `component`, `artifact_name`, `artifact_kind`, `artifact_content_base64`, `auto_deploy`, `chat_session_id`, and `task_tree_node_id` when available. Default `auto_deploy` to true when the user says “推送到服务端部署” or “部署” without extra qualifiers; only keep it false when the user explicitly says “只上传”.
7. Only call `deploy_project_deploy_artifact` when the user explicitly provides an `artifact_id` or explicitly asks to deploy an existing server artifact. If the user refers to a local zip, new code, a rebuilt bundle, upload deployment, or push deployment, first upload the current file content with `push_project_deploy_artifact` to create a new artifact; never reuse a historical artifact as a shortcut. If `auto_deploy` is enabled or the user explicitly requests deployment, prefer the AI-driven execution path (`POST /api/projects/{project_id}/deploy-artifacts/{artifact_id}/deploy/ai-execute`) and pass `requirement` / `plan` so the deployment AI can decide whether to extract, upload as archive, recurse a directory, or upload a plain file. Use plain `POST /api/projects/{project_id}/deploy-artifacts/{artifact_id}/deploy` only for explicit non-AI fallback.
8. Report the server artifact ID, upload status, deployment status, stdout/stderr or run logs returned by the deployment capability, and any blocked/missing reason. When the package is already local, do not ask the user to re-upload just because the prompt lacks a `project_id`; derive it from the current project context and proceed with the upload route.
9. If the package is on another computer or the desktop Runner is unavailable, stop local command execution and direct the user to upload through the deploy artifact list.

## Forbidden Client Behavior

- Do not make client-local FTP upload the main deployment path.
- Do not scan or reuse historical publish configuration, CI files, local deploy scripts, local CLI login state, or environment variables as the execution basis.
- Do not search for FTP, SSH, SFTP, CDN, token, key, or password values on the client machine.
- Do not ask the user for server credentials in chat when the project deploy settings should own them.
- Do not give the external agent a long-lived API key, user token, FTP/SSH credential, or local environment secret.
- Do not read or reuse local config files as the credential source.
- Do not deploy directly from remote shell, file transfer, CDN, provider CLIs, or ad hoc FTP scripts as a substitute for the deploy artifact module.
- Do not treat client-local FTP as a normal deployment path. Use it only if the project deploy settings and server capability explicitly require it, and never as a replacement for the artifact upload/deploy routes above.
- Do not infer `remote_path` from built files, `.env*`, API domains, package names, or old release notes.
- Do not call `push_project_deploy_artifact` with a client-local `artifact_path`. `artifact_path` is a server-readable REST compatibility field, not the remote MCP upload path.
- Do not mark deployment successful unless the server-side artifact deployment capability reports success and the deployed target is reachable or verified by the configured deployment result.

## Missing Capability Messages

- Missing external agent: `当前项目聊天未选择外部智能体，不能执行本地打包/部署命令。`
- Missing desktop Runner: `外部智能体只支持桌面端 Runner，不能在网页模式执行当前电脑上的本地打包命令。`
- Missing artifact push capability: `当前缺少部署产物上传能力，不能把本地打包产物推送到项目部署产物模块。`
- Missing local upload bridge: `当前缺少本地文件上传桥，不能把本地打包产物读取并上传到部署产物模块。`
- Missing deploy capability: `当前缺少部署产物自动部署能力，artifact 已保存但不能自动部署。`
- Manual upload required: `当前电脑不可由外部智能体访问，请在部署产物列表使用页面手动上传。`

## Deleting Packaged Files

Deleting a packaged file means deleting the server-side deploy artifact file and its `ProjectDeployArtifact` record. It must not delete external chat messages or remote server deployed directories.
