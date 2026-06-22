"""liuAgent V0.1 runtime contract primitives.

This package is intentionally small: it keeps protocol validation reusable by
CLI, Web, Desktop, and the existing v2 runtime without creating a second engine.
"""

from services.agent_runtime.contract.schema import (
    APPROVAL_DECISION_TO_SCOPE,
    IDEMPOTENT_COMMAND_TYPES,
    ContractError,
    build_agent_event,
    validate_adapter_command,
    validate_agent_event,
    validate_permission_decision_against_options,
    validate_permission_option,
    validate_state_changed_payload,
)

__all__ = [
    "APPROVAL_DECISION_TO_SCOPE",
    "IDEMPOTENT_COMMAND_TYPES",
    "ContractError",
    "build_agent_event",
    "validate_adapter_command",
    "validate_agent_event",
    "validate_permission_decision_against_options",
    "validate_permission_option",
    "validate_state_changed_payload",
]
