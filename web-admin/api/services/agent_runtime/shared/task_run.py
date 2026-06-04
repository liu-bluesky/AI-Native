"""Compatibility shim for relocated TaskRun models."""

from services.agent_runtime.core.task_run import TaskRun, new_run_id, utc_now_iso

__all__ = ["TaskRun", "new_run_id", "utc_now_iso"]
