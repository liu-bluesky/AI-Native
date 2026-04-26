"""Bot connector installer manifests and diagnostics."""

from __future__ import annotations

from typing import Any

from stores.factory import system_config_store
from services.bot_connector_service import get_bot_connector
from services.feishu_bot_service import (
    check_feishu_connector_credentials,
    get_feishu_sdk_error_message,
    is_feishu_sdk_available,
)


def _check(check_id: str, title: str, ok: bool, message: str, *, action: str = "") -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "ok": bool(ok),
        "status": "passed" if ok else "failed",
        "message": message,
        "action": action,
    }


def bot_connector_platform_manifests() -> list[dict[str, Any]]:
    return [
        {
            "platform": "feishu",
            "name": "飞书",
            "supported_receive_modes": ["http_callback", "long_connection"],
            "recommended_receive_mode": "long_connection",
            "required_fields": ["app_id", "app_secret"],
            "optional_fields": ["verification_token", "encrypt_key"],
            "required_events": ["im.message.receive_v1"],
            "required_permissions": ["im:message:receive_as_bot", "im:chat:read"],
            "install_steps": [
                "在飞书开放平台创建或选择应用，并复制 App ID / App Secret。",
                "事件订阅选择“使用长连接接收事件”或 HTTP 回调；推荐长连接。",
                "添加事件 im.message.receive_v1，并开通机器人接收消息权限。",
                "把机器人添加到目标群，在系统里保存连接器后运行诊断。",
                "若使用长连接，后端需启动飞书长连接 worker。",
            ],
        },
        {
            "platform": "wechat",
            "name": "微信 / 企业微信",
            "supported_receive_modes": ["http_callback", "polling", "manual"],
            "recommended_receive_mode": "http_callback",
            "required_fields": ["app_id", "app_secret"],
            "optional_fields": ["verification_token", "encrypt_key"],
            "required_events": [],
            "required_permissions": [],
            "install_steps": [
                "保存微信侧应用凭证。",
                "按平台要求配置回调 URL、Token 和 EncodingAESKey。",
                "通过诊断确认凭证、回调和消息路由。",
            ],
        },
        {
            "platform": "qq",
            "name": "QQ",
            "supported_receive_modes": ["long_connection", "http_callback", "manual"],
            "recommended_receive_mode": "long_connection",
            "required_fields": ["app_id", "app_secret"],
            "optional_fields": [],
            "required_events": [],
            "required_permissions": [],
            "install_steps": [
                "保存 QQ 机器人应用凭证。",
                "按 QQ 开放平台选择事件网关或回调模式。",
                "通过统一事件适配层把群 ID、用户 ID 和消息正文映射到内部格式。",
            ],
        },
    ]


def get_bot_connector_platform_manifest(platform: str) -> dict[str, Any] | None:
    normalized = str(platform or "").strip().lower()
    for manifest in bot_connector_platform_manifests():
        if manifest.get("platform") == normalized:
            return dict(manifest)
    return None


def diagnose_bot_connector(connector_id: str, *, worker_status: dict[str, Any] | None = None) -> dict[str, Any]:
    connector = get_bot_connector(connector_id)
    checks: list[dict[str, Any]] = []
    if connector is None:
        return {
            "connector_id": str(connector_id or "").strip(),
            "ok": False,
            "platform": "",
            "receive_mode": "",
            "checks": [
                _check("connector_exists", "连接器存在", False, "没有找到这个机器人连接器", action="先在机器人接入页保存连接器"),
            ],
            "manifest": None,
            "next_actions": ["先保存机器人连接器"],
        }

    platform = str(connector.get("platform") or "").strip().lower()
    receive_mode = str(connector.get("event_receive_mode") or "").strip().lower()
    manifest = get_bot_connector_platform_manifest(platform)
    supported_modes = set(manifest.get("supported_receive_modes") or []) if manifest else set()
    app_id = str(connector.get("app_id") or "").strip()
    app_secret = str(connector.get("app_secret") or "").strip()

    checks.append(_check("connector_exists", "连接器存在", True, "已找到连接器"))
    checks.append(_check("connector_enabled", "连接器已启用", connector.get("enabled") is not False, "连接器已启用" if connector.get("enabled") is not False else "连接器当前停用", action="打开启用开关"))
    checks.append(_check("credentials_present", "应用凭证已填写", bool(app_id and app_secret), "App ID / App Secret 已填写" if app_id and app_secret else "缺少 App ID 或 App Secret", action="补齐平台应用凭证"))
    checks.append(_check("receive_mode_supported", "接收方式受支持", bool(manifest and receive_mode in supported_modes), f"当前接收方式：{receive_mode or '未设置'}" if manifest else "平台暂未注册安装清单", action="选择当前平台支持的接收方式"))

    next_actions: list[str] = []
    if platform == "feishu":
        checks.append(_check("feishu_sdk_available", "飞书 SDK 可用", is_feishu_sdk_available(), "lark_oapi 已安装" if is_feishu_sdk_available() else get_feishu_sdk_error_message(), action="安装 lark-oapi 依赖并重启 API"))
        if app_id and app_secret:
            try:
                result = check_feishu_connector_credentials(connector)
                checks.append(_check("feishu_credentials_valid", "飞书凭证有效", bool(result.get("ok", True)), str(result.get("message") or "飞书凭证校验通过")))
            except Exception as exc:  # noqa: BLE001 - surface platform diagnostic message
                checks.append(_check("feishu_credentials_valid", "飞书凭证有效", False, str(exc), action="检查 App ID / App Secret 与应用状态"))
        else:
            checks.append(_check("feishu_credentials_valid", "飞书凭证有效", False, "缺少凭证，跳过飞书 token 校验", action="补齐 App ID / App Secret 后重新诊断"))
        if receive_mode == "long_connection":
            system_worker_enabled = bool(
                getattr(
                    system_config_store.get_global(),
                    "feishu_bot_long_connection_worker_enabled",
                    False,
                )
            )
            checks.append(_check("feishu_system_worker_enabled", "系统已启用长连接 worker", system_worker_enabled, "系统配置已启用飞书长连接 worker" if system_worker_enabled else "系统配置未启用飞书长连接 worker", action="到系统配置页打开“飞书长连接 worker”开关并保存"))
            auto_start = connector.get("auto_start_worker") is True
            checks.append(_check("feishu_auto_start_worker", "连接器允许托管 worker", auto_start, "连接器允许后端托管长连接 worker" if auto_start else "连接器未开启 worker 托管开关", action="在连接器编辑里打开长连接 worker 开关"))
            running = bool((worker_status or {}).get("running"))
            checks.append(_check("feishu_long_connection_worker", "长连接 worker 运行中", running, "worker 正在运行" if running else "worker 未运行或未由当前 API 进程托管", action="打开系统配置开关并保存；若仍未运行，点击 worker 重启或手动运行 worker 脚本"))
            next_actions.append("在飞书开放平台把事件订阅方式设为长连接，并添加 im.message.receive_v1")
            next_actions.append("到系统配置页打开“飞书长连接 worker”开关并保存，系统会尝试启动/停止 worker")
        else:
            next_actions.append("若使用 HTTP 回调，在飞书后台配置 /api/bot-events/feishu/{connector_id}/event 公网 URL")
        next_actions.append("在目标项目对话里绑定飞书群来源后，把机器人加入目标群并 @ 机器人发送测试消息")
    else:
        next_actions.append("当前平台已保留安装清单，事件适配 worker / callback 可按 manifest 继续实现")

    ok = all(item.get("ok") for item in checks)
    return {
        "connector_id": connector.get("id"),
        "platform": platform,
        "receive_mode": receive_mode,
        "ok": ok,
        "checks": checks,
        "manifest": manifest,
        "next_actions": next_actions,
    }
