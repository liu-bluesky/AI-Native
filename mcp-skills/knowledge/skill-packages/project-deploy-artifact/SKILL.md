---
name: project-deploy-artifact
description: Use when a project needs build/package artifact deployment through MCP or the server. The client AI must only build/package locally, compute artifact metadata, push the artifact to the server, and let the server deploy from project deploy_settings.
---

# Project Deploy Artifact

Use this skill for project deployment requests, including “打包部署”, “自动部署”, “部署产物”, “手动部署”, “发布测试环境”, or “推送构建包”.

## Responsibility Boundary

- Client AI: build or package locally, compute artifact metadata, and push the artifact to MCP/server.
- MCP/server: create `ProjectDeployArtifact`, read project `deploy_settings`, upload to the configured remote target, create `ProjectDeployRun`, and report deploy status.
- UI/manual operation: when auto deploy is disabled, the pushed artifact appears in the deploy artifact list and the user can click the artifact `部署` button.

## Required Flow

1. Check available project MCP tools before deploying. `push_project_deploy_artifact` must exist; if it does not, stop and tell the user the client lacks the artifact push tool or authenticated server API.
2. Read only the current project deploy settings and the user request. Do not infer server target, credentials, or remote paths from repository files.
3. If no artifact exists, run the project build/package command that belongs to the requested component.
4. Compute artifact metadata: `artifact_name`, `artifact_kind`, `manifest.checksum`, `manifest.size`, and optional `manifest.version`.
5. Push the artifact with `push_project_deploy_artifact` or the equivalent server HTTP artifact push endpoint. Include `profile`, `component`, `artifact_path` or `artifact_content_base64`, `auto_deploy`, `chat_session_id`, and `task_tree_node_id` when available.
6. If auto deploy is enabled, report the server returned deploy run status. If auto deploy is disabled, report that the artifact was pushed and can be deployed from the deploy artifact list.
7. If deployment is explicitly requested for an existing artifact and policy allows it, use `deploy_project_deploy_artifact`; otherwise leave deployment to the UI button.
8. If the server returns `blocked`, `missing`, or `failed`, relay the missing fields and server message directly. Do not reinterpret it as local deploy work.

## Forbidden Client Behavior

- Do not scan or reuse historical publish configuration, CI files, local deploy scripts, local CLI login state, or environment variables as the execution basis.
- Do not search for FTP, SSH, SFTP, CDN, token, key, or password values on the client machine.
- Do not ask the user for server credentials in chat when the project deploy settings should own them.
- Do not deploy directly from the client with remote shell, file transfer, CDN, or provider CLIs.
- Do not infer `remote_path` from built files, `.env*`, API domains, package names, or old release notes.
- Do not mark deployment successful unless the server returns a successful or queued deploy status.

## Missing Capability Messages

- Missing push tool/API: `当前客户端未暴露 push_project_deploy_artifact 或服务端 artifact 推送 API 登录态，无法部署。请先在项目 MCP 工具或服务端 API 中开放部署产物推送入口。`
- Missing project deploy settings: `服务端部署配置不完整，无法部署。缺失项：<server missing list>。`
- Auto deploy disabled: `部署产物已推送，当前项目未开启自动部署。可在部署配置的部署产物列表点击该产物的“部署”按钮手动触发。`

## Deleting Packaged Files

Deleting a packaged file means deleting the server-side deploy artifact file and its `ProjectDeployArtifact` record. It must not delete external chat messages or remote server deployed directories.
