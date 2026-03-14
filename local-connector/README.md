# Local Connector

`local-connector` is the long-term path for remote users.

It runs on the user's own machine and exposes a small, controlled HTTP API for:

- local workspace access
- local command execution
- PTY terminal mirroring
- local LLM bridge

This is different from the current server-side runner:

- server-side runner: runs next to the API service
- local connector: runs on the end user's macOS / Windows machine

## What It Solves

For remote users, the browser cannot safely provide a usable absolute path for the server.
The platform also cannot directly access the user's local CLI tools or local models.

The connector fixes that by making the user's machine the execution host.

It can bridge:

- local project folders
- local Codex / Claude / Gemini CLI
- local OpenAI-compatible model endpoints such as Ollama / LM Studio / vLLM

## Scope of Phase 1

This directory contains the first-stage foundation:

- a standalone Node.js connector service
- cross-platform start scripts
- runner-compatible endpoints for workspace + exec + PTY
- local LLM bridge endpoints for future platform integration

What is not wired yet:

- reverse connection / websocket tunnel
- multi-user connector routing on the server side
- UI onboarding flow for connector install / pairing

## Endpoints

Phase 1 exposes these endpoints:

- `GET /health`
- `GET /manifest`
- `POST /probe-workspace`
- `POST /workspace/materialize`
- `POST /exec/stream`
- `POST /exec/cancel/{exec_id}`
- `POST /pty/open`
- `GET /pty/stream/{session_id}`
- `POST /pty/input/{session_id}`
- `POST /pty/close/{session_id}`
- `GET /llm/models`
- `POST /llm/chat/completions`

The workspace / exec / PTY API is intentionally aligned with the existing host runner protocol so the server can reuse it with minimal changes later.

## Platform Pairing

Phase 2 adds the first pairing foundation.

Server side:

- create pair code
- connector activates with pair code
- connector receives `connector_id` + `connector_token`
- connector sends periodic heartbeat

Connector env vars:

- `LOCAL_CONNECTOR_PLATFORM_URL`
- `LOCAL_CONNECTOR_PAIR_CODE`
- `LOCAL_CONNECTOR_NAME`
- `LOCAL_CONNECTOR_ADVERTISED_URL`
- `LOCAL_CONNECTOR_HEARTBEAT_SEC`

This is enough for basic registration and presence reporting.
It is not yet enough for full remote execution through NAT/firewall without an additional reverse-connect channel.

## Local LLM Bridge

The connector can proxy a local OpenAI-compatible endpoint.

Environment variables:

- `LOCAL_CONNECTOR_LLM_BASE_URL`
- `LOCAL_CONNECTOR_LLM_API_KEY`
- `LOCAL_CONNECTOR_LLM_MODELS`
- `LOCAL_CONNECTOR_LLM_DEFAULT_MODEL`

Examples:

- Ollama via OpenAI-compatible gateway
- LM Studio local server
- vLLM running on the user's machine

If these variables are not configured, the LLM bridge endpoints return a clear error.

## Start

For non-technical users, the recommended path is now:

1. Generate a pair code in the platform.
2. Download the platform-generated macOS / Windows starter package.
3. Let the user unzip it and double-click the included launcher.

The launcher will:

- run directly with Node.js 18+
- install runtime dependencies automatically on first run
- inject the platform URL + pair code automatically
- start the connector service directly
- keep the console window open so users can see progress and errors
- open a local status page at `http://127.0.0.1:3931`
- write logs to `logs/bootstrap.log` and `logs/connector.log`

Advanced manual startup remains available below.

macOS / Linux:

```bash
cd local-connector
node launcher.js
```

Windows PowerShell:

```powershell
cd local-connector
node .\launcher.js
```

Windows CMD:

```bat
cd local-connector
node launcher.js
```

Default address:

- `http://127.0.0.1:3931`

After startup, open the address above in the local browser to confirm:

- paired / not paired
- last heartbeat time
- recent heartbeat error
- Codex / Claude / Gemini CLI detection

## Electron Desktop

If you want a GUI wrapper instead of a console window, use the Electron shell under `local-connector/desktop`.

Development:

```bash
cd local-connector/desktop
npm install
npm run dev
```

What it does:

- wraps the current Node connector core
- starts / stops the connector from a desktop UI
- shows pairing + heartbeat status
- streams runtime logs in the app window
- provides shortcuts to open the local status page, log folder and data folder
- packaged desktop apps bundle connector runtime dependencies and should not run `npm install` on the end user's machine

Packaged runtime behavior:

- connector runtime files are bundled into `resources/connector`
- mutable data is written into `userData/connector-runtime`
- packaged desktop builds do not require the end user to install Node.js

Build commands:

```bash
cd local-connector/desktop
npm install
npm run dist:mac
npm run dist:win
```

More details:

- see `local-connector/desktop/README.md`

Current limitation:

- the raw script installer still requires Node.js 18+ on the user's machine
- the Electron desktop package can avoid that because it bundles its own runtime
- real PTY now prefers `@homebridge/node-pty-prebuilt-multiarch`; if install失败，会回退到普通进程镜像模式

## Notes

- Phase 1 is intentionally local-only.
- The central platform still needs a pairing / reverse-connect layer before remote users can use this without manual network setup.
- That pairing layer should be the next implementation phase.
