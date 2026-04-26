"""web-admin API store factory and lazy proxies."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Callable

from core.config import get_api_data_dir, get_settings


class _StoreProxy:
    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._instance: Any = None
        self._lock = Lock()

    def _get_instance(self) -> Any:
        if self._instance is not None:
            return self._instance
        with self._lock:
            if self._instance is None:
                self._instance = self._factory()
        return self._instance

    def __getattr__(self, item: str) -> Any:
        return getattr(self._get_instance(), item)


def _missing_driver(setting_name: str) -> RuntimeError:
    return RuntimeError(
        f"{setting_name}=postgres 但未安装 PostgreSQL 驱动。"
        "请安装依赖: psycopg[binary]>=3.2。"
    )


def _data_dir() -> Path:
    return get_api_data_dir()


def _create_user_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import UserStore

        return UserStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.user_store import UserStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return UserStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_changelog_entry_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import ChangelogEntryStore

        return ChangelogEntryStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.changelog_entry_store import ChangelogEntryStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return ChangelogEntryStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_employee_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import EmployeeStore

        return EmployeeStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.employee_store import EmployeeStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return EmployeeStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_agent_template_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import AgentTemplateStore

        return AgentTemplateStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.agent_template_store import AgentTemplateStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return AgentTemplateStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_role_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import RoleStore

        return RoleStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.role_store import RoleStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return RoleStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_project_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import ProjectStore

        return ProjectStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.project_store import ProjectStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return ProjectStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_project_chat_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import ProjectChatStore

        return ProjectChatStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.project_chat_store import ProjectChatStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return ProjectChatStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_project_chat_runtime_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import ProjectChatRuntimeStore

        return ProjectChatRuntimeStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.project_chat_runtime_store import (
                ProjectChatRuntimeStorePostgres,
            )
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return ProjectChatRuntimeStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_project_chat_task_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import ProjectChatTaskStore

        return ProjectChatTaskStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.project_chat_task_store import ProjectChatTaskStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return ProjectChatTaskStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_project_material_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import ProjectMaterialStore

        return ProjectMaterialStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.project_material_store import ProjectMaterialStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return ProjectMaterialStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_project_experience_summary_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import ProjectExperienceSummaryStore

        return ProjectExperienceSummaryStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.project_experience_summary_store import (
                ProjectExperienceSummaryStorePostgres,
            )
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return ProjectExperienceSummaryStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_project_studio_export_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import ProjectStudioExportStore

        return ProjectStudioExportStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.project_studio_export_store import (
                ProjectStudioExportStorePostgres,
            )
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return ProjectStudioExportStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_system_config_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import SystemConfigStore

        return SystemConfigStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.system_config_store import SystemConfigStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return SystemConfigStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_bot_connector_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import BotConnectorStore

        return BotConnectorStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.bot_connector_store import BotConnectorStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return BotConnectorStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_external_mcp_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import ExternalMcpStore

        return ExternalMcpStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.external_mcp_store import ExternalMcpStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return ExternalMcpStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_local_connector_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import LocalConnectorStore

        return LocalConnectorStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.local_connector_store import LocalConnectorStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return LocalConnectorStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_usage_store() -> Any:
    settings = get_settings()
    if settings.usage_store_backend == "sqlite":
        from stores.json import UsageStore

        return UsageStore(_data_dir() / "usage.db")
    if settings.usage_store_backend == "postgres":
        try:
            from stores.postgres.usage_store import UsageStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("USAGE_STORE_BACKEND") from exc
        return UsageStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported USAGE_STORE_BACKEND: {settings.usage_store_backend}")


def _create_work_session_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import WorkSessionStore

        return WorkSessionStore(_data_dir())
    if settings.core_store_backend == "postgres":
        try:
            from stores.postgres.work_session_store import WorkSessionStorePostgres
        except ModuleNotFoundError as exc:
            raise _missing_driver("CORE_STORE_BACKEND") from exc
        return WorkSessionStorePostgres(settings.database_url)
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


def _create_task_tree_evolution_store() -> Any:
    settings = get_settings()
    if settings.core_store_backend == "json":
        from stores.json import TaskTreeEvolutionStore

        return TaskTreeEvolutionStore(_data_dir())
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {settings.core_store_backend}")


user_store = _StoreProxy(_create_user_store)
changelog_entry_store = _StoreProxy(_create_changelog_entry_store)
role_store = _StoreProxy(_create_role_store)
employee_store = _StoreProxy(_create_employee_store)
agent_template_store = _StoreProxy(_create_agent_template_store)
project_store = _StoreProxy(_create_project_store)
project_chat_store = _StoreProxy(_create_project_chat_store)
project_chat_runtime_store = _StoreProxy(_create_project_chat_runtime_store)
project_chat_task_store = _StoreProxy(_create_project_chat_task_store)
project_material_store = _StoreProxy(_create_project_material_store)
project_experience_summary_store = _StoreProxy(_create_project_experience_summary_store)
project_studio_export_store = _StoreProxy(_create_project_studio_export_store)
system_config_store = _StoreProxy(_create_system_config_store)
bot_connector_store = _StoreProxy(_create_bot_connector_store)
usage_store = _StoreProxy(_create_usage_store)
external_mcp_store = _StoreProxy(_create_external_mcp_store)
local_connector_store = _StoreProxy(_create_local_connector_store)
work_session_store = _StoreProxy(_create_work_session_store)
task_tree_evolution_store = _StoreProxy(_create_task_tree_evolution_store)


__all__ = [
    "user_store",
    "changelog_entry_store",
    "role_store",
    "employee_store",
    "agent_template_store",
    "project_store",
    "project_chat_store",
    "project_chat_runtime_store",
    "project_chat_task_store",
    "project_material_store",
    "project_studio_export_store",
    "system_config_store",
    "bot_connector_store",
    "usage_store",
    "external_mcp_store",
    "local_connector_store",
    "work_session_store",
    "task_tree_evolution_store",
]
