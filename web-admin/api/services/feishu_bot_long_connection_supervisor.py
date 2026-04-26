"""Supervisor for Feishu bot long-connection worker processes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from services.bot_connector_service import list_bot_connectors


class FeishuBotLongConnectionSupervisor:
    def __init__(self, *, api_root: Path, connector_ids: list[str] | None = None) -> None:
        self._api_root = Path(api_root)
        self._connector_ids = {str(item).strip() for item in (connector_ids or []) if str(item).strip()}
        self._processes: dict[str, subprocess.Popen] = {}

    def _desired_connectors(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for connector in list_bot_connectors():
            if str(connector.get("platform") or "").strip().lower() != "feishu":
                continue
            connector_id = str(connector.get("id") or "").strip()
            if not connector_id or connector.get("enabled") is False:
                continue
            if self._connector_ids and connector_id not in self._connector_ids:
                continue
            if str(connector.get("event_receive_mode") or "").strip().lower() != "long_connection":
                continue
            if not self._connector_ids and connector.get("auto_start_worker") is not True:
                continue
            items.append(dict(connector))
        return items

    def start(self) -> None:
        for connector in self._desired_connectors():
            connector_id = str(connector.get("id") or "").strip()
            if not connector_id:
                continue
            existing = self._processes.get(connector_id)
            if existing is not None and existing.poll() is None:
                continue
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self._api_root) + os.pathsep + env.get("PYTHONPATH", "")
            process = subprocess.Popen(
                [sys.executable, str(self._api_root / "scripts" / "feishu_long_connection_worker.py"), "--connector-id", connector_id],
                cwd=str(self._api_root),
                env=env,
            )
            self._processes[connector_id] = process

    async def stop(self) -> None:
        for process in self._processes.values():
            if process.poll() is None:
                process.terminate()
        for process in self._processes.values():
            if process.poll() is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        self._processes.clear()

    def restart(self) -> None:
        for process in self._processes.values():
            if process.poll() is None:
                process.terminate()
        self._processes.clear()
        self.start()

    def status(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for connector in self._desired_connectors():
            connector_id = str(connector.get("id") or "").strip()
            process = self._processes.get(connector_id)
            return_code = process.poll() if process is not None else None
            result[connector_id] = {
                "connector_id": connector_id,
                "running": bool(process is not None and return_code is None),
                "pid": process.pid if process is not None and return_code is None else None,
                "return_code": return_code,
            }
        return result
